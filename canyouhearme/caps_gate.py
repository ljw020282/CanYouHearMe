"""Caps Lock is overlay toggle; Alt+Caps Lock is speak/stop. Restored on exit."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
VK_CAPITAL = 0x14
VK_MENU = 0x12
LLKHF_INJECTED = 0x10

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class CapsLockGate:
    def __init__(
        self,
        on_toggle: Callable[[], None],
        on_speak_stop: Callable[[], None],
    ) -> None:
        self.on_toggle = on_toggle
        self.on_speak_stop = on_speak_stop
        self._hook = None
        self._proc = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._caps_was_on = False
        self._down = False

    def start(self) -> None:
        self._caps_was_on = bool(user32.GetKeyState(VK_CAPITAL) & 1)
        self._thread = threading.Thread(target=self._message_loop, name="caps-gate", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=2):
            raise RuntimeError("Caps Lock 钩子未能启动")

    def stop(self) -> None:
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        if self._thread and self._thread.ident:
            user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)  # WM_QUIT
        self._restore_caps()

    def _restore_caps(self) -> None:
        now = bool(user32.GetKeyState(VK_CAPITAL) & 1)
        if now != self._caps_was_on:
            user32.keybd_event(VK_CAPITAL, 0, 0, 0)
            user32.keybd_event(VK_CAPITAL, 0, 2, 0)

    def _message_loop(self) -> None:
        self._proc = HOOKPROC(self._low_level)
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0
        )
        if not self._hook:
            logger.error("SetWindowsHookEx 失败")
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _low_level(self, n_code, wparam, lparam):
        if n_code >= 0:
            info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if info.vkCode == VK_CAPITAL and not (info.flags & LLKHF_INJECTED):
                if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if not self._down:
                        self._down = True
                        alt = bool(user32.GetKeyState(VK_MENU) & 0x8000)
                        try:
                            if alt:
                                self.on_speak_stop()
                            else:
                                self.on_toggle()
                        except Exception:
                            logger.exception("热键回调失败")
                    return 1
                if wparam in (WM_KEYUP, WM_SYSKEYUP):
                    self._down = False
                    return 1
        return user32.CallNextHookEx(self._hook, n_code, wparam, lparam)
