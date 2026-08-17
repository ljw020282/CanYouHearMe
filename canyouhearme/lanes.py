from __future__ import annotations

import logging
import os
import queue
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Callable

from canyouhearme.policy import should_keep_audio
from canyouhearme.store import VoiceStore
from canyouhearme.tts_client import DashScopeTTS

logger = logging.getLogger(__name__)


class TtsLanes:
    """Live speech uses one dedicated worker; corpus scan uses two more."""

    def __init__(
        self,
        client: DashScopeTTS,
        store: VoiceStore,
        timeout: float,
        on_live_status: Callable[[str], None],
        on_live_ready: Callable[[str, bool, int], None],
        on_live_error: Callable[[str, int], None],
    ) -> None:
        self.client = client
        self.store = store
        self.timeout = timeout
        self.on_live_status = on_live_status
        self.on_live_ready = on_live_ready
        self.on_live_error = on_live_error
        self._live_q: queue.Queue = queue.Queue()
        self._scan_q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._scan_busy: set[tuple[str, str]] = set()
        self._scan_lock = threading.Lock()
        self._live_thread = threading.Thread(target=self._live_loop, name="tts-live", daemon=True)
        self._scan_threads = [
            threading.Thread(target=self._scan_loop, name=f"tts-scan-{i}", daemon=True)
            for i in range(2)
        ]
        self._live_thread.start()
        for t in self._scan_threads:
            t.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._live_q.put(None)
        for _ in self._scan_threads:
            self._scan_q.put(None)

    def speak_live(self, text: str, voice: str, keep_cfg: dict, token: int) -> str:
        cached = self.store.cached_path(text, voice)
        if cached:
            self.store.bump(text, voice)
            self.on_live_status("cached")
            self.on_live_ready(str(cached), True, token)
            return "cached"
        self.on_live_status("generating")
        while not self._live_q.empty():
            try:
                self._live_q.get_nowait()
            except queue.Empty:
                break
        self._live_q.put(("speak", text, voice, keep_cfg, token))
        return "generating"

    def enqueue_scan(self, text: str, voice: str, keep_cfg: dict) -> None:
        key = (text, voice)
        with self._scan_lock:
            if key in self._scan_busy:
                return
            if self.store.cached_path(text, voice):
                return
            self._scan_busy.add(key)
        self._scan_q.put((text, voice, keep_cfg))

    def _live_loop(self) -> None:
        while not self._stop.is_set():
            job = self._live_q.get()
            if job is None:
                break
            _, text, voice, keep_cfg, token = job
            try:
                path = self._synthesize_and_maybe_keep(text, voice, keep_cfg, bump=True)
                self.on_live_ready(str(path), False, token)
            except Exception as e:
                logger.exception("实时合成失败")
                self.on_live_error(str(e), token)

    def _scan_loop(self) -> None:
        while not self._stop.is_set():
            job = self._scan_q.get()
            if job is None:
                break
            text, voice, keep_cfg = job
            try:
                if self.store.cached_path(text, voice) is None:
                    self._synthesize_and_maybe_keep(text, voice, keep_cfg, bump=False)
            except Exception:
                logger.exception("扫库合成失败: %s", text[:40])
            finally:
                with self._scan_lock:
                    self._scan_busy.discard((text, voice))

    def _synthesize_and_maybe_keep(
        self, text: str, voice: str, keep_cfg: dict, bump: bool
    ) -> Path:
        dest = self.store.wav_path(text, voice)
        tmp = dest.with_suffix(".tmp.wav")
        self.client.synthesize(text, voice, str(tmp), timeout=self.timeout + 8)
        count = self.store.bump(text, voice) if bump else keep_cfg.get("speak_count", 0)
        if bump:
            keep = should_keep_audio(
                text,
                phrases=keep_cfg["phrases"],
                shortcut_values=keep_cfg["shortcut_values"],
                speak_count=count,
                immediate_max_chars=keep_cfg["immediate_max_chars"],
                background_hits=keep_cfg["background_hits"],
            )
        else:
            keep = True
        if keep:
            os_replace(tmp, dest)
            self.store.mark_cached(text, voice, str(dest))
            return dest
        fd, leftover_name = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        leftover = Path(leftover_name)
        os_replace(tmp, leftover)
        return leftover


def os_replace(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        src.replace(dest)
    except OSError:
        shutil.copy2(src, dest)
        src.unlink(missing_ok=True)
