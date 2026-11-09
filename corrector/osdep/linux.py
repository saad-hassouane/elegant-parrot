"""Linux / X11: xclip, xdotool, notify-send. (Wayland blocks xdotool-style key injection - not supported.)"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..appctx import WindowInfo
from . import Platform

_SYNC = "string:x-canonical-private-synchronous:elegant-parrot"  # same key => replaces the previous bubble


def _run(*cmd: str, inp: str | None = None) -> str:
    return subprocess.run(cmd, input=inp, capture_output=True, text=True, check=True).stdout


def _xdo(*args: str) -> str:
    try:
        return subprocess.run(["xdotool", *args], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


class Linux(Platform):
    name = "linux"
    supports_primary = True
    supports_inplace_notify = True

    def get_clipboard(self) -> str:
        try:
            return _run("xclip", "-selection", "clipboard", "-o")
        except (subprocess.CalledProcessError, OSError):
            return ""

    def set_clipboard(self, text: str) -> None:
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, text=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.communicate(text)

    def get_primary(self) -> str:
        """The mouse-highlighted text (PRIMARY) - works even when an app swallows Ctrl+Shift+C."""
        try:
            return _run("xclip", "-selection", "primary", "-o")
        except (subprocess.CalledProcessError, OSError):
            return ""

    def release_modifiers(self) -> None:
        _run("xdotool", "keyup", "ctrl", "shift", "alt", "super")

    def press(self, keys: str) -> None:
        _run("xdotool", "key", "--clearmodifiers", keys)

    def active_id(self) -> str:
        return _xdo("getactivewindow")

    def active_window(self) -> WindowInfo | None:
        if not _xdo("getactivewindow"):
            return None
        process, pid = "", _xdo("getactivewindow", "getwindowpid")
        if pid.isdigit():
            try:
                process = Path(f"/proc/{pid}/comm").read_text().strip()
            except OSError:
                pass
        return WindowInfo(_xdo("getactivewindow", "getwindowclassname"), _xdo("getactivewindow", "getwindowname"), process)

    def notify(self, msg: str, timeout_ms: int = 2500) -> None:
        subprocess.run(["notify-send", "-t", str(timeout_ms), "-h", _SYNC, "Elegant Parrot", msg], check=False)

    def check_environment(self) -> list[tuple[bool, str, str]]:
        out = [(shutil.which(t) is not None, t, f"sudo apt install {pkg}")
               for t, pkg in (("xclip", "xclip"), ("xdotool", "xdotool"), ("notify-send", "libnotify-bin"))]
        wayland = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        out.append((not wayland, "X11 session (Wayland blocks key injection)", "log in with 'Ubuntu on Xorg' / an X11 session"))
        return out
