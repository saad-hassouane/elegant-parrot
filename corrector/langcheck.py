"""Guard against a proofreading model that translates, changes script or rewrites instead of fixing typos."""
from __future__ import annotations

import re

from pii_gate.gate import TOKEN_RE

_WORD = re.compile(r"[\w'’]+", re.UNICODE)
_AR = re.compile(r"[؀-ۿ]")
_LAT = re.compile(r"[A-Za-zÀ-ÿ]")
# Common Darija words in Latin script (arabizi) + the digit-letters 2,3,5,7,9 used for Arabic sounds (t3awnni, 9dr).
_DARIJA_LAT = {"wach", "kifach", "khouya", "khoya", "ghadi", "bghit", "bghiti", "mzyan", "dyal", "dyali", "daba", "ghda",
               "mabghach", "safi", "bzaf", "bzzaf", "hamdullah", "hamdulillah", "salam", "labas", "fin", "chno", "shno",
               "wakha", "mashi", "makaynch", "kayn", "rah", "hna", "nta", "nti", "howa", "hiya", "3afak", "inchallah"}
_DIGIT_LETTER = re.compile(r"\b[a-z]*[23579][a-z]+\b|\b[a-z]+[23579][a-z]*\b")


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(TOKEN_RE.sub(" ", text))]


def arabic_ratio(text: str) -> float:
    a, l = len(_AR.findall(text)), len(_LAT.findall(text))
    return a / (a + l) if a + l else 0.0


def looks_darija(text: str) -> bool:
    """Heuristic: Arabic script, or Latin text with Darija vocabulary / digit-letters (3, 7, 9...)."""
    if arabic_ratio(text) > 0.3:
        return True
    low = text.lower()
    hits = sum(w in _DARIJA_LAT for w in _words(low))
    digits = len([m for m in _DIGIT_LETTER.findall(low) if not m.isdigit()])
    return hits >= 2 or digits >= 2 or (hits >= 1 and digits >= 1)


def drift(src: str, out: str) -> str:
    """'' if `out` is an acceptable proofread of `src`; otherwise a short reason (the caller keeps `src`)."""
    if abs(arabic_ratio(src) - arabic_ratio(out)) > 0.5:
        return "the model changed the script (Arabic <-> Latin)"
    a, b = _words(src), set(_words(out))
    if len(a) < 4:
        return ""  # too short to judge by word overlap
    kept = sum(w in b for w in a) / len(a)
    need = 0.6 if looks_darija(src) else 0.5  # dialect text has no standard spelling: be stricter about rewrites
    if kept < need:
        return f"the model rewrote the text ({kept:.0%} of the words kept, need {need:.0%})"
    return ""
