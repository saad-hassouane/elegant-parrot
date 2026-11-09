"""OS adapters: everything that differs between Linux (X11), macOS and Windows.

The gate, the models, the config and the pipeline are shared. Each adapter only provides:
clipboard, key presses, the focused window, notifications and (for `elegant-parrot doctor`) an environment check.
Linux is the reference implementation and the only one exercised on real hardware by the author;
the macOS and Windows adapters are written against documented system APIs and unit-tested with mocks."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # appctx must not import this package at module load (it imports us lazily)
    from ..appctx import WindowInfo

_MODS = {"ctrl", "control", "shift", "alt", "option", "cmd", "command", "super", "win", "meta"}


def split_keys(keys: str) -> tuple[list[str], str]:
    """'ctrl+shift+c' -> (['ctrl', 'shift'], 'c')."""
    parts = [p.strip().lower() for p in keys.split("+") if p.strip()]
    mods = [p for p in parts[:-1] if p in _MODS]
    return mods, parts[-1] if parts else ""


class Platform:
    name = "unknown"
    modifier = "ctrl"                  # the "command" key for copy/paste/select-all (cmd on macOS)
    supports_primary = False           # X11 mouse-selection buffer
    supports_inplace_notify = False    # can one notification be updated in place (animated loader)?

    def get_clipboard(self) -> str: raise NotImplementedError
    def set_clipboard(self, text: str) -> None: raise NotImplementedError
    def get_primary(self) -> str: return ""
    def release_modifiers(self) -> None: """Release keys still held from the trigger shortcut."""
    def press(self, keys: str) -> None: raise NotImplementedError
    def active_id(self) -> str: raise NotImplementedError
    def active_window(self) -> "WindowInfo | None": raise NotImplementedError
    def notify(self, msg: str, timeout_ms: int = 2500) -> None: raise NotImplementedError
    def check_environment(self) -> list[tuple[bool, str, str]]:
        """[(ok, label, fix hint)] for `elegant-parrot doctor`."""
        return []

    def select_all_key(self) -> str:
        return f"{self.modifier}+a"


_cached: Platform | None = None


def get_platform() -> Platform:
    global _cached
    if _cached is None:
        if sys.platform == "darwin":
            from .macos import MacOS
            _cached = MacOS()
        elif sys.platform in ("win32", "cygwin"):
            from .windows import Windows
            _cached = Windows()
        else:
            from .linux import Linux
            _cached = Linux()
    return _cached
