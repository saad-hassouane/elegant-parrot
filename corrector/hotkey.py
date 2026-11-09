"""Hotkey entry point: copy the selection -> correct it -> paste it back, restoring the clipboard.
OS specifics (clipboard, key presses, focused window, notifications) live in corrector.osdep."""
from __future__ import annotations

import logging
import threading
import time

from .appctx import WindowInfo, classify
from .config import Settings
from .osdep import Platform, get_platform
from .pipeline import Corrector

log = logging.getLogger("hotkey")

_PROMPT_GLYPHS = ("❯ ", "› ")  # prompt marks a TUI draws in front of the input line (e.g. Claude Code's "❯ ")
_CORRECTORS: dict[tuple, Corrector] = {}  # kept between presses in `elegant-parrot listen` mode (models stay loaded)
_BUSY = threading.Lock()                   # one correction at a time


def plan(settings: Settings, win: WindowInfo | None) -> tuple[str, dict, str | None]:
    """-> (category, app rules, reason-if-blocked). Pure, so it is unit-testable."""
    cat = classify(win, settings.apps)
    app = settings.apps[cat]
    if not settings.enabled:
        return cat, app, "disabled globally (elegant-parrot enable all)"
    if not app.get("enabled", True):
        return cat, app, f"disabled for {cat} apps (elegant-parrot enable {cat})"
    return cat, app, None


class Loader:
    """'Working' indicator. Where the OS can update a notification in place (Linux) it animates with an elapsed
    counter; elsewhere it shows one notification up front."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, platform: Platform, label: str, enabled: bool = True) -> None:
        self.p, self.label, self.enabled = platform, label, enabled
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> "Loader":
        if not self.enabled:
            return self
        if self.p.supports_inplace_notify:
            self._t.start()
        else:
            self.p.notify(f"{self.FRAMES[0]} {self.label}", 60000)
        return self

    def _run(self) -> None:
        t0, i = time.time(), 0
        while not self._stop.is_set():
            self.p.notify(f"{self.FRAMES[i % len(self.FRAMES)]} {self.label} {int(time.time() - t0)}s", 60000)
            i += 1
            self._stop.wait(1.0)

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._t.is_alive():
            self._t.join(timeout=2)


def _corrector(settings: Settings, cat: str) -> Corrector:
    s = settings.for_app(cat)
    key = (s.backend, s.ollama_model, s.external_model, s.gate_enabled, tuple(s.languages), tuple(s.pii["detectors"]))
    if key not in _CORRECTORS:
        _CORRECTORS[key] = Corrector(s)
    return _CORRECTORS[key]


def main(platform: Platform | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    P = platform or get_platform()
    if not _BUSY.acquire(blocking=False):  # already correcting (listener mode): ignore the extra press
        return 0
    try:
        return _run(P)
    finally:
        _BUSY.release()


def _run(P: Platform) -> int:
    try:
        settings = Settings.load()
    except Exception as exc:  # noqa: BLE001 - bad config must not touch the user's text
        P.notify(f"Config error: {exc}"[:150])
        return 1
    note = lambda m: P.notify(m) if settings.notify else None  # noqa: E731
    cat, app, blocked = plan(settings, P.active_window())
    if blocked:
        note(blocked)
        return 0
    copy_key, paste_key = app["copy_key"], app["paste_key"]
    target = P.active_id()  # the window we are correcting; the model can take many seconds
    saved = P.get_clipboard()
    try:
        P.set_clipboard("")  # sentinel so we can tell whether the copy captured anything
        P.release_modifiers()  # release the trigger shortcut's modifiers
        P.press(copy_key)
        time.sleep(0.15)
        selected = P.get_clipboard()
        if not selected.strip() and settings.select_all_fallback and cat != "terminal":
            # nothing selected: take the whole active input field (select-all is "start of line" in terminals, so skipped there)
            P.set_clipboard("")
            P.press(P.select_all_key())
            time.sleep(0.1)
            P.press(copy_key)
            time.sleep(0.2)
            selected = P.get_clipboard()
        if not selected.strip() and cat == "terminal" and settings.terminal_use_primary and P.supports_primary:
            selected = P.get_primary()
            for g in _PROMPT_GLYPHS:  # the highlight usually includes the prompt glyph; it is not part of the text
                if selected.startswith(g):
                    selected = selected[len(g):]
        if not selected.strip():
            note("No text in the active field" if cat != "terminal" else "No text selected")
            return 1
        if len(selected) > settings.max_chars:
            note(f"Too long ({len(selected)} > {settings.max_chars} chars) - select less text")
            return 1
        with Loader(P, "Correcting…", settings.notify):
            res = _corrector(settings, cat).correct(selected)
        if not res.ok:
            note("Aborted (PII safety check): " + "; ".join(res.problems)[:120])
            return 2
        if res.skipped:
            note("Left unchanged: " + res.skipped)
            return 0
        if not res.changed:
            note("No corrections needed")
            return 0
        if P.active_id() != target:
            # You switched windows while the model ran: pasting now would write into the wrong app.
            P.set_clipboard(res.text)
            saved = res.text  # leave the correction on the clipboard instead of restoring the old content
            note("Window changed - not pasted. The correction is on your clipboard (paste it yourself).")
            return 3
        P.set_clipboard(res.text)
        time.sleep(0.15)  # let the new clipboard owner settle before the app asks for it
        if cat == "terminal" and settings.terminal_replace_line:
            P.press("ctrl+a")  # start of line ...
            P.press("ctrl+k")  # ... kill to end: the line is empty, the paste replaces it
            time.sleep(0.1)
        P.press(paste_key)
        time.sleep(0.5)  # slow apps read the clipboard late; restoring too early would paste the old content
        note("✓ Corrected")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("failed")
        note(f"Error: {exc}"[:150])
        return 1
    finally:
        P.set_clipboard(saved)


if __name__ == "__main__":
    raise SystemExit(main())
