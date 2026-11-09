"""`elegant-parrot listen`: a small background process that owns the global hotkey on every OS and keeps the
models loaded between presses (no ~5 s start-up per press). Needs `pip install "elegant-parrot[desktop]"`.

Linux can also use the GNOME shortcut (scripts/install_shortcut.sh); macOS and Windows use this listener."""
from __future__ import annotations

import logging
import sys
import threading

from .config import Settings
from .osdep import get_platform

log = logging.getLogger("listen")


def run() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        from pynput import keyboard
    except ImportError:
        print('pynput is not installed: pip install "elegant-parrot[desktop]"', file=sys.stderr)
        return 1
    from . import hotkey
    s = Settings.load()
    plat = get_platform()
    print(f"elegant-parrot listening on {plat.name}: press {s.hotkey} in any text field (Ctrl+C here to stop)")
    if plat.name == "macos":
        print("macOS: allow this terminal/Python under System Settings > Privacy & Security > Accessibility "
              "and Input Monitoring, otherwise the shortcut is silently ignored.")

    def trigger() -> None:
        threading.Thread(target=hotkey.main, daemon=True).start()  # never block the key listener

    # Warm up: load the detectors/models now so the first press is as fast as the rest.
    threading.Thread(target=lambda: hotkey._corrector(s, "native"), daemon=True).start()
    try:
        with keyboard.GlobalHotKeys({s.hotkey: trigger}) as h:
            h.join()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
