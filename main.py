from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from canyouhearme.caps_gate import CapsLockGate
from canyouhearme.config import AppConfig
from canyouhearme.lanes import TtsLanes
from canyouhearme.overlay import OverlayBar
from canyouhearme.playback import DualPlayer, find_cable_input, find_default_monitor
from canyouhearme.settings import SettingsDialog
from canyouhearme.store import VoiceStore
from canyouhearme.textutil import expand
from canyouhearme.tts_client import DashScopeTTS

logger = logging.getLogger("canyouhearme")


def _tray_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#d4a017"))
    painter.setPen(QColor("#1c1710"))
    painter.drawEllipse(6, 6, 52, 52)
    painter.end()
    return QIcon(pm)


class UiBridge(QObject):
    status = pyqtSignal(str)
    ready = pyqtSignal(str, bool, int)
    error = pyqtSignal(str, int)
    toggle = pyqtSignal()
    speak_stop = pyqtSignal()


class App(QObject):
    def __init__(self, qt: QApplication) -> None:
        super().__init__()
        self.qt = qt
        self.cfg = AppConfig()
        self.store = VoiceStore(self.cfg.root)
        self.player = DualPlayer()
        self.token = 0
        self.busy = False
        self._dead = False
        self.bridge = UiBridge()
        self.overlay = OverlayBar()
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._on_timeout)
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_once)
        self.lanes = self._make_lanes()
        self._wire()
        self._apply_devices()
        self._restore_overlay()
        self._make_tray()
        self.gate = CapsLockGate(
            on_toggle=self.bridge.toggle.emit,
            on_speak_stop=self.bridge.speak_stop.emit,
        )
        self.gate.start()
        self.scan_timer.start(int(self.cfg.get("scan_interval_sec", 60)) * 1000)
        QTimer.singleShot(800, self.scan_once)

    def _make_lanes(self) -> TtsLanes:
        client = DashScopeTTS(
            self.cfg.get("dashscope_base"),
            self.cfg.get("api_key"),
            self.cfg.get("model"),
        )
        return TtsLanes(
            client,
            self.store,
            timeout=float(self.cfg.get("tts_timeout_sec", 5)),
            on_live_status=self.bridge.status.emit,
            on_live_ready=self.bridge.ready.emit,
            on_live_error=self.bridge.error.emit,
        )

    def _wire(self) -> None:
        self.bridge.status.connect(self._on_status)
        self.bridge.ready.connect(self._on_ready)
        self.bridge.error.connect(self._on_error)
        self.bridge.toggle.connect(self.toggle_overlay)
        self.bridge.speak_stop.connect(self.speak_or_stop)
        self.overlay.speak_requested.connect(self.speak)
        self.overlay.settings_requested.connect(self.open_settings)
        self.overlay.pin_changed.connect(self._on_pin)
        self.overlay.moved_to.connect(self._save_pos)
        self.qt.aboutToQuit.connect(self.shutdown)

    def _apply_devices(self) -> None:
        cable = self.cfg.get("cable_device")
        if cable is None:
            cable = find_cable_input()
            if cable is not None:
                self.cfg.set("cable_device", cable)
        monitor = self.cfg.get("monitor_device")
        if monitor is None:
            monitor = find_default_monitor(exclude=cable)
        self.player.configure(
            cable,
            monitor,
            bool(self.cfg.get("monitor_enabled", True)),
        )

    def _restore_overlay(self) -> None:
        self.overlay.set_phrases(list(self.cfg.get("phrases") or []))
        self.overlay.pin_btn.setChecked(bool(self.cfg.get("pin_overlay", True)))
        pos = self.cfg.get("overlay_pos")
        if isinstance(pos, list) and len(pos) == 2:
            self.overlay.move(int(pos[0]), int(pos[1]))
        else:
            screen = self.qt.primaryScreen().availableGeometry()
            self.overlay.move(screen.center().x() - 400, screen.top() + 48)
        self.overlay.show()
        self.overlay.input.setFocus()

    def _make_tray(self) -> None:
        self.tray = QSystemTrayIcon(_tray_icon(), self.qt)
        menu = QMenu()
        show_act = QAction("显示悬浮条", menu)
        show_act.triggered.connect(self.show_overlay)
        set_act = QAction("设置", menu)
        set_act.triggered.connect(self.open_settings)
        quit_act = QAction("退出", menu)
        quit_act.triggered.connect(self.qt.quit)
        menu.addAction(show_act)
        menu.addAction(set_act)
        menu.addSeparator()
        menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("CanYouHearMe")
        self.tray.activated.connect(self._tray_click)
        self.tray.show()

    def _tray_click(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_overlay()

    def keep_cfg(self) -> dict:
        phrases = list(self.cfg.get("phrases") or [])
        shortcuts = dict(self.cfg.get("shortcuts") or {})
        return {
            "phrases": phrases,
            "shortcut_values": list(shortcuts.values()),
            "immediate_max_chars": int(self.cfg.get("immediate_cache_max_chars", 6)),
            "background_hits": int(self.cfg.get("background_cache_hits", 3)),
        }

    def toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.show_overlay()

    def show_overlay(self) -> None:
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        self.overlay.input.setFocus()

    def _on_pin(self, on: bool) -> None:
        self.cfg.set("pin_overlay", on)

    def _save_pos(self, x: int, y: int) -> None:
        self.cfg.set("overlay_pos", [x, y])

    def speak_or_stop(self) -> None:
        if self.busy or self.player.playing:
            self.stop()
        else:
            self.speak()

    def stop(self) -> None:
        self.token += 1
        self.busy = False
        self.timeout.stop()
        self.player.stop()
        self.overlay.set_status("idle")

    def speak(self) -> None:
        raw = self.overlay.draft_text()
        text = expand(raw, dict(self.cfg.get("shortcuts") or {}))
        if not text:
            return
        if self.player.cable_id is None:
            QMessageBox.warning(
                self.overlay,
                "没有虚拟声卡",
                "没找到 CABLE Input。请先装 VB-Cable，再在设置里选设备。",
            )
            return
        self.player.stop()
        self.token += 1
        token = self.token
        self.busy = True
        self.timeout.start(int(float(self.cfg.get("tts_timeout_sec", 5)) * 1000))
        self.lanes.speak_live(text, self.cfg.get("voice"), self.keep_cfg(), token)

    def _on_status(self, state: str) -> None:
        self.overlay.set_status(state)
        if state == "cached":
            self.timeout.stop()

    def _on_timeout(self) -> None:
        if self.busy:
            self.overlay.set_status("timeout")

    def _on_ready(self, path: str, cached: bool, token: int) -> None:
        if token != self.token:
            self._maybe_unlink_temp(path)
            return
        self.timeout.stop()
        self.overlay.set_status("cached" if cached else "playing")
        self.player.enqueue(path)
        QTimer.singleShot(80, lambda: self._after_enqueue(path))

    def _after_enqueue(self, path: str) -> None:
        if not self.overlay.pin_btn.isChecked() and self.cfg.get("hide_after_speak", True):
            self.overlay.hide()
        self.overlay.clear_input()
        QTimer.singleShot(50, lambda: self._watch_playback(path))

    def _watch_playback(self, path: str) -> None:
        if self.player.playing:
            QTimer.singleShot(120, lambda: self._watch_playback(path))
            return
        self.busy = False
        self.overlay.set_status("idle")
        self._maybe_unlink_temp(path)

    def _maybe_unlink_temp(self, path: str) -> None:
        p = Path(path)
        try:
            if "voices" not in p.parts:
                p.unlink(missing_ok=True)
        except OSError:
            pass

    def _on_error(self, message: str, token: int) -> None:
        if token != self.token:
            return
        self.busy = False
        self.timeout.stop()
        self.overlay.set_status("error")
        logger.error(message)
        self.tray.showMessage("CanYouHearMe", message, QSystemTrayIcon.MessageIcon.Warning, 4000)

    def scan_once(self) -> None:
        voice = self.cfg.get("voice")
        keep = self.keep_cfg()
        pending = self.store.pending_scan(
            voice,
            keep["phrases"],
            keep["shortcut_values"],
            keep["immediate_max_chars"],
            keep["background_hits"],
        )
        for text in pending:
            self.lanes.enqueue_scan(text, voice, keep)

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg.data, self.overlay)
        if dlg.exec():
            self.cfg.data.update(dlg.result_data())
            self.cfg.save()
            self.store = VoiceStore(self.cfg.root)
            self.lanes.shutdown()
            self.lanes = self._make_lanes()
            self._apply_devices()
            self.overlay.set_phrases(list(self.cfg.get("phrases") or []))
            self.overlay.pin_btn.setChecked(bool(self.cfg.get("pin_overlay", True)))
            self.scan_timer.setInterval(int(self.cfg.get("scan_interval_sec", 60)) * 1000)

    def shutdown(self) -> None:
        if self._dead:
            return
        self._dead = True
        try:
            self.gate.stop()
        except Exception:
            logger.exception("卸钩失败")
        self.scan_timer.stop()
        self.timeout.stop()
        self.lanes.shutdown()
        self.player.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    qt = QApplication(sys.argv)
    qt.setApplicationName("CanYouHearMe")
    qt.setQuitOnLastWindowClosed(False)
    app = App(qt)
    code = qt.exec()
    app.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
