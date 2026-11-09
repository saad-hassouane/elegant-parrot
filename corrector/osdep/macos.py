"""macOS: pbcopy/pbpaste, AppleScript (osascript) for key presses, focused app and notifications.

Needs a one-off permission: System Settings > Privacy & Security > Accessibility - allow the app that runs the
shortcut (Terminal / iTerm / the Python you launch `elegant-parrot listen` from)."""
from __future__ import annotations

import shutil
import subprocess

from ..appctx import WindowInfo
from . import Platform, split_keys

_AS_MODS = {"cmd": "command down", "command": "command down", "ctrl": "control down", "control": "control down",
            "alt": "option down", "option": "option down", "shift": "shift down"}
_KEYCODES = {"return": 36, "tab": 48, "escape": 53, "home": 115, "end": 119}


def _osa(script: str, timeout: float = 5) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise subprocess.CalledProcessError(r.returncode, "osascript", r.stdout, r.stderr)
    return r.stdout.strip()


def key_script(keys: str) -> str:
    """'cmd+c' -> AppleScript that presses it."""
    mods, key = split_keys(keys)
    action = f"key code {_KEYCODES[key]}" if key in _KEYCODES else f'keystroke "{key}"'
    using = ""
    if mods:
        using = " using {" + ", ".join(_AS_MODS[m] for m in mods if m in _AS_MODS) + "}"
    return f'tell application "System Events" to {action}{using}'


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


_FRONT = '''tell application "System Events"
  set p to first application process whose frontmost is true
  set wtitle to ""
  try
    set wtitle to name of front window of p
  end try
  return (name of p) & "||" & (bundle identifier of p) & "||" & wtitle & "||" & (unix id of p)
end tell'''


class MacOS(Platform):
    name = "macos"
    modifier = "cmd"

    def get_clipboard(self) -> str:
        try:
            return subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout
        except (subprocess.CalledProcessError, OSError):
            return ""

    def set_clipboard(self, text: str) -> None:
        subprocess.run(["pbcopy"], input=text, text=True, check=True, env={"LANG": "en_US.UTF-8"})

    def press(self, keys: str) -> None:
        _osa(key_script(keys))

    def active_id(self) -> str:
        try:
            return _osa(_FRONT).split("||")[-1]  # pid of the frontmost app (window titles change while typing)
        except (subprocess.SubprocessError, OSError):
            return ""

    def active_window(self) -> WindowInfo | None:
        try:
            name, bundle, title, _pid = (_osa(_FRONT).split("||") + ["", "", "", ""])[:4]
        except (subprocess.SubprocessError, OSError):
            return None
        return WindowInfo(wm_class=bundle, title=title, process=name)

    def notify(self, msg: str, timeout_ms: int = 2500) -> None:
        subprocess.run(["osascript", "-e", f'display notification "{_q(msg)}" with title "Elegant Parrot"'], check=False)

    def check_environment(self) -> list[tuple[bool, str, str]]:
        out = [(shutil.which(t) is not None, t, "built into macOS - is PATH broken?") for t in ("pbcopy", "pbpaste", "osascript")]
        try:
            _osa('tell application "System Events" to get name of first application process')
            ok = True
        except (subprocess.SubprocessError, OSError):
            ok = False
        out.append((ok, "Accessibility permission (System Events)",
                    "System Settings > Privacy & Security > Accessibility: allow Terminal / your Python"))
        return out
