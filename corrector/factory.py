from __future__ import annotations

import logging

from pii_gate.sensitive import QuasiDetector, SensitiveDetector
from pii_gate import CompositeDetector, FilteredDetector, Gate, MoroccanDetector, PresidioDetector, RegexDetector, TracerDetector

from .config import Settings

log = logging.getLogger(__name__)


def build_gate(s: Settings) -> Gate:
    """Build the PII gate from [pii] config. Fails closed: no usable detector => error."""
    pii = s.pii
    deny = list(pii.get("kinds", {}).get("deny", []))
    dets = []
    for name in pii["detectors"]:
        if name == "regex":
            d = RegexDetector(extra=pii.get("extra_patterns") or {})
        elif name == "names":  # EN/FR/Darija cues + gazetteer + addresses (see pii_gate/multilingual.py)
            d = MoroccanDetector(pii.get("extra_names") or [], pii.get("extra_places") or [], languages=s.languages)
        elif name == "tracer":  # on-device PII-Tracer classifier (opt-in; needs torch + a one-off model download)
            d = TracerDetector(include_dates=bool(pii.get("tracer_dates", False)))
        elif name == "presidio":
            models = {k: v for k, v in pii["ner_models"].items() if v and k in s.languages}  # spaCy: en / fr only
            if not models:
                log.info("no spaCy model for languages %s - skipping the statistical NER", s.languages)
                continue
            try:
                d = PresidioDetector(models, float(pii["ner_threshold"]))
            except Exception as exc:  # noqa: BLE001
                log.warning("NER unavailable (%s) - continuing with remaining detectors", exc)
                continue
        else:
            raise ValueError(f"unknown PII detector {name!r} (use 'regex', 'names', 'tracer' or 'presidio')")
        dets.append(FilteredDetector(d, deny=deny))
    if not dets:
        raise ValueError("no PII detectors available - refusing to run unprotected")
    if s.backend == "external" and pii.get("strict_external", True):
        # precise rule detectors outrank statistical NER on overlaps: insert right after the first two
        dets[2:2] = [QuasiDetector(), SensitiveDetector()]  # longer phrases (ROLE) first
    return Gate(CompositeDetector(dets))
