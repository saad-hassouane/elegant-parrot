"""pii_gate - provider-agnostic PII tokenization gate.

    from pii_gate import Gate
    gate = Gate()
    safe_call = gate.guard(my_llm_call)      # any str -> str callable
    with gate.session() as s:                # or manual control
        safe = s.protect(text); out = call(safe); final = s.restore(out).text
"""
from .detectors import CompositeDetector, Detector, FilteredDetector, PresidioDetector, RegexDetector, Span, default_detector
from .gate import Gate, OutboundBlocked, ProtectedCallFailed, Restored, Session
from .multilingual import MoroccanDetector
from .sensitive import QuasiDetector, SensitiveDetector, SPECIAL_CATEGORY_KINDS
from .tracer import TracerDetector
from .vault import Vault

__all__ = ["Gate", "Session", "Restored", "OutboundBlocked", "ProtectedCallFailed", "Vault",
           "MoroccanDetector", "TracerDetector", "SensitiveDetector", "QuasiDetector", "SPECIAL_CATEGORY_KINDS", "Detector", "Span", "RegexDetector", "PresidioDetector", "CompositeDetector", "FilteredDetector", "default_detector"]
