"""Windows: ctypes (user32/kernel32) for clipboard, key presses and the focused window; a PowerShell toast
for notifications. No third-party packages. ctypes.windll is only touched inside methods, so this module
imports (and its pure helpers are unit-testable) on any OS."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from ..appctx import WindowInfo
from . import Platform, split_keys

_VK = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "option": 0x12, "win": 0x5B, "cmd": 0x5B, "super": 0x5B,
       "meta": 0x5B, "return": 0x0D, "tab": 0x09, "escape": 0x1B, "home": 0x24, "end": 0x23}
_RELEASE = (0x11, 0x10, 0x12, 0x5B, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)  # ctrl/shift/alt/win + left/right variants
_CF_UNICODETEXT, _GMEM_MOVEABLE, _KEYUP = 13, 0x0002, 0x0002

_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$n = $t.GetElementsByTagName('text')
$n.Item(0).AppendChild($t.CreateTextNode('Elegant Parrot')) > $null
$n.Item(1).AppendChild($t.CreateTextNode('__MSG__')) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($t)
$toast.Tag = 'elegant-parrot'; $toast.Group = 'elegant-parrot'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show($toast)
"""


def vk_codes(keys: str) -> list[int]:
    """'ctrl+shift+c' -> [0x11, 0x10, 0x43]  (modifiers first, the key last)."""
    mods, key = split_keys(keys)
    codes = [_VK[m] for m in mods if m in _VK]
    codes.append(_VK[key] if key in _VK else ord(key.upper()) if len(key) == 1 else 0)
    return codes


def toast_script(msg: str) -> str:
    return _TOAST.replace("__MSG__", msg.replace("'", "''").replace("\r", " ").replace("\n", " "))


class Windows(Platform):
    name = "windows"

    # --- clipboard (CF_UNICODETEXT) ---
    def _api(self):  # noqa: ANN202
        import ctypes
        from ctypes import wintypes
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        u.GetClipboardData.restype = wintypes.HANDLE
        u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u.GetForegroundWindow.restype = wintypes.HWND
        k.GlobalAlloc.argtypes, k.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
        k.GlobalLock.argtypes, k.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
        k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        k.OpenProcess.restype = wintypes.HANDLE
        return ctypes, wintypes, u, k

    def _open_clipboard(self, u) -> bool:  # noqa: ANN001
        for _ in range(20):  # another app may hold it for a few ms
            if u.OpenClipboard(None):
                return True
            time.sleep(0.01)
        return False

    def get_clipboard(self) -> str:
        ctypes, _w, u, k = self._api()
        if not self._open_clipboard(u):
            return ""
        try:
            h = u.GetClipboardData(_CF_UNICODETEXT)
            if not h:
                return ""
            p = k.GlobalLock(h)
            try:
                return ctypes.wstring_at(p)
            finally:
                k.GlobalUnlock(h)
        finally:
            u.CloseClipboard()

    def set_clipboard(self, text: str) -> None:
        ctypes, _w, u, k = self._api()
        data = (text + "\0").encode("utf-16-le")
        h = k.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        ctypes.memmove(k.GlobalLock(h), data, len(data))
        k.GlobalUnlock(h)
        if not self._open_clipboard(u):
            return
        try:
            u.EmptyClipboard()
            u.SetClipboardData(_CF_UNICODETEXT, h)  # the system owns the memory after this call
        finally:
            u.CloseClipboard()

    # --- keys ---
    def release_modifiers(self) -> None:
        import ctypes
        for vk in _RELEASE:
            ctypes.windll.user32.keybd_event(vk, 0, _KEYUP, 0)

    def press(self, keys: str) -> None:
        import ctypes
        ev, codes = ctypes.windll.user32.keybd_event, vk_codes(keys)
        for vk in codes:
            ev(vk, 0, 0, 0)
        time.sleep(0.02)
        for vk in reversed(codes):
            ev(vk, 0, _KEYUP, 0)

    # --- focused window ---
    def active_id(self) -> str:
        _c, _w, u, _k = self._api()
        return str(u.GetForegroundWindow() or "")

    def active_window(self) -> WindowInfo | None:
        ctypes, wintypes, u, k = self._api()
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return None
        title = ctypes.create_unicode_buffer(512)
        u.GetWindowTextW(hwnd, title, 512)
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = ""
        h = k.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            size, buf = wintypes.DWORD(1024), ctypes.create_unicode_buffer(1024)
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                exe = Path(buf.value).name.lower()
            k.CloseHandle(h)
        return WindowInfo(wm_class=exe, title=title.value, process=exe)

    # --- notifications ---
    def notify(self, msg: str, timeout_ms: int = 2500) -> None:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", toast_script(msg)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

    def check_environment(self) -> list[tuple[bool, str, str]]:
        return [(shutil.which("powershell") is not None, "powershell (toast notifications)", "install Windows PowerShell 5.1+")]
