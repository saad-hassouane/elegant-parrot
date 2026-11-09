"""Map the focused window (via the OS adapter) to an app category."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    wm_class: str = ""
    title: str = ""
    process: str = ""


def active_window() -> WindowInfo | None:
    from .osdep import get_platform  # lazy: osdep imports WindowInfo from this module
    return get_platform().active_window()


def classify(win: WindowInfo | None, apps: dict) -> str:
    """teams > terminal > web > native. Class/process are substring-matched, titles are regexes."""
    if win is None:
        return "native"
    ident, title = f"{win.wm_class} {win.process}".lower(), win.title
    for cat in ("teams", "terminal", "web"):
        rules = apps.get(cat, {})
        if any(k.lower() in ident for k in rules.get("wm_class", []) if k):
            return cat
        if any(re.search(p, title, re.I) for p in rules.get("title", []) if p):
            return cat
    return "native"
