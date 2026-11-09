from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pii_gate import Gate
from pii_gate.gate import TOKEN_RE
from pii_gate.sensitive import SPECIAL_CATEGORY_KINDS

from .config import Settings
from .factory import build_gate
from .langcheck import drift
from .providers import Provider, extract, make_provider

log = logging.getLogger(__name__)


@dataclass
class Result:
    text: str
    changed: bool
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    skipped: str = ""  # model output rejected (translated / rewrote the text): the original is returned untouched


class Corrector:
    """Grammar correction on top of pii_gate."""

    def __init__(self, settings: Settings | None = None, provider: Provider | None = None,
                 gate: Gate | None = None) -> None:
        self.settings = settings or Settings.load()
        self.provider = provider or make_provider(self.settings)
        # Gate off: do not even load the detectors (spaCy etc.) - the text goes to the model unmodified.
        self.gate = gate or (build_gate(self.settings) if self.settings.gate_enabled else None)

    def correct(self, raw: str) -> Result:
        """Up to `retries` attempts, each in a fresh session (new random tokens), because small
        models occasionally mangle a placeholder. Never injects output with lost/unknown tokens."""
        if not raw.strip():
            return Result(raw, False)
        if not self.settings.gate_enabled:
            if self.provider.external:  # fail closed: switching the gate off must never expose raw data to a third party
                return Result(raw, False, False, ["PII gate is disabled (pii.enabled = false): refusing the external backend"])
            out = extract(self.provider.correct(raw))
            if (why := drift(raw, out)):
                return Result(raw, False, skipped=why)
            return Result(out, out != raw)
        problems: list[str] = []
        for attempt in range(1, max(1, self.settings.retries) + 1):
            with self.gate.session() as s:
                safe = s.protect(raw)
                if self.provider.external:
                    found = sorted({k for k, _ in TOKEN_RE.findall(safe)} & SPECIAL_CATEGORY_KINDS)
                    if found and self.settings.pii.get("special_category", "block") == "block":
                        # GDPR Art. 9/10: never send special-category data to an external processor
                        return Result(raw, False, False, [f"special-category data ({', '.join(found)}) - "
                                                          "use the local backend for this text"])
                    s.check_outbound(safe)  # raises OutboundBlocked - never retried
                r = s.restore(self.provider.correct(safe))
            if r.ok:
                if (why := drift(raw, r.text)):  # translated / script change / rewrite: keep the user's text
                    log.warning("model output rejected: %s", why)
                    return Result(raw, False, skipped=why)
                return Result(r.text, r.text != raw)
            problems = r.problems
            log.warning("attempt %d/%d: restoration failed: %s", attempt, self.settings.retries, problems)
        return Result(raw, False, False, problems)  # fail safe
