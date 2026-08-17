from __future__ import annotations

import ctypes
import logging
import queue
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)


def list_output_devices() -> list[dict]:
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] > 0:
            devices.append({"id": idx, "name": dev["name"]})
    return devices


def find_cable_input() -> Optional[int]:
    ranked = []
    for dev in list_output_devices():
        n = dev["name"].lower()
        if "cable input" in n and "16ch" not in n:
            return dev["id"]
        if "cable input" in n or "vb-audio" in n or "vb-cable" in n:
            ranked.append(dev["id"])
    return ranked[0] if ranked else None


def find_default_monitor(exclude: Optional[int] = None) -> Optional[int]:
    try:
        default = sd.default.device[1]
        if isinstance(default, int) and default != exclude:
            return default
    except Exception:
        pass
    for dev in list_output_devices():
        if dev["id"] != exclude:
            return dev["id"]
    return None


def _com_init() -> None:
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass


def _com_uninit() -> None:
    try:
        ctypes.windll.ole32.CoUninitialize()
    except Exception:
        pass


class DualPlayer:
    """Play the same wav to VB-Cable and, optionally, a local monitor device."""

    def __init__(self) -> None:
        self.cable_id: Optional[int] = None
        self.monitor_id: Optional[int] = None
        self.monitor_enabled = True
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self.playing = False
        self._thread = threading.Thread(target=self._loop, name="audio-out", daemon=True)
        self._thread.start()

    def configure(
        self,
        cable_id: Optional[int],
        monitor_id: Optional[int],
        monitor_enabled: bool,
    ) -> None:
        self.cable_id = cable_id
        self.monitor_id = monitor_id
        self.monitor_enabled = monitor_enabled

    def enqueue(self, path: str) -> None:
        self._q.put(path)

    def stop(self) -> None:
        self._stop.set()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except Exception:
                break

    def shutdown(self) -> None:
        self.stop()
        self._q.put(None)
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        _com_init()
        try:
            while True:
                path = self._q.get()
                if path is None:
                    break
                self._stop.clear()
                self.playing = True
                try:
                    self._play_file(path)
                except Exception:
                    logger.exception("播放失败 %s", path)
                finally:
                    self.playing = False
        finally:
            _com_uninit()

    def _play_file(self, path: str) -> None:
        data, sr = sf.read(path, dtype="float32")
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        devices: list[int] = []
        if self.cable_id is not None:
            devices.append(self.cable_id)
        if self.monitor_enabled and self.monitor_id is not None:
            if self.monitor_id not in devices:
                devices.append(self.monitor_id)
        if not devices:
            raise RuntimeError("未选择播放设备")
        streams = []
        try:
            for dev in devices:
                info = sd.query_devices(dev)
                channels = min(data.shape[1], int(info["max_output_channels"]) or 1)
                streams.append(
                    sd.OutputStream(
                        device=dev,
                        samplerate=sr,
                        channels=channels,
                        dtype="float32",
                    )
                )
            for stream in streams:
                stream.start()
            chunk = 2048
            offset = 0
            while offset < len(data):
                if self._stop.is_set():
                    break
                block = data[offset : offset + chunk]
                for stream in streams:
                    ch = stream.channels
                    if block.shape[1] == 1 and ch > 1:
                        out = np.repeat(block, ch, axis=1)
                    elif block.shape[1] < ch:
                        out = np.zeros((len(block), ch), dtype=np.float32)
                        out[:, : block.shape[1]] = block
                    else:
                        out = block[:, :ch]
                    stream.write(out)
                offset += chunk
            # drain a little so the last block is not cut
            if not self._stop.is_set():
                time.sleep(0.04)
        finally:
            for stream in streams:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
