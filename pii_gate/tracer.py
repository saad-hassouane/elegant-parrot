"""On-device classifier layer: Perplexity's PII-Tracer (~600M params, MIT licence).

    pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU build is ~200 MB
    pip install "transformers>=5.2"
    python -m pii_gate.tracer --download                                  # once; ~1.2 GB into the HF cache

Security notes
  * The model repo ships custom Python (modeling_pii_masking.py) that transformers executes via
    trust_remote_code. We pin the exact commit that was reviewed (REVISION) so it cannot change under us.
  * At run time the model loads with local_files_only=True: no network call, nothing leaves the machine.
    Only --download touches the network.
  * Heavy: ~1.2 GB disk, a few seconds to load, ~1-2 s per text on CPU. Opt-in (pii.detectors += "tracer").
    Loading per process makes it a poor fit for the hotkey (a new process each press) - use it in a
    long-running service (playground / sidecar)."""
from __future__ import annotations

import re
import threading

from .detectors import Span

MODEL_ID = "perplexity-ai/PII-Tracer"
REVISION = "d25c16f2e57e321f6d2527715c01df9112f956f5"  # reviewed: imports only torch + transformers, no network/exec

# PII-Tracer label -> our token kind. Dates are skipped by default: masking "4:00 PM" hurts readability
# and is rarely identifying on its own (pass include_dates=True to mask them).
LABEL_KIND = {
    "private_person": "PERSON", "account_number": "ACCOUNT", "private_url": "URL", "private_address": "ADDRESS",
    "private_email": "EMAIL", "private_phone": "PHONE", "other_pii": "OTHER", "secret": "SECRET",
}
_CHUNK = 3000  # characters; the model's limit is 4096 tokens


class TracerDetector:
    """Lazy-loading wrapper; the first detect() loads the model."""

    def __init__(self, include_dates: bool = False, device: str = "cpu") -> None:
        self.include_dates, self.device = include_dates, device
        self._model = None
        self._lock = threading.Lock()

    def _load(self):  # noqa: ANN202
        with self._lock:
            if self._model is None:
                try:
                    import torch  # noqa: F401
                    from transformers import AutoModel
                except ImportError as exc:
                    raise RuntimeError("PII-Tracer needs torch and transformers>=5.2 (see pii_gate/tracer.py)") from exc
                try:
                    self._model = AutoModel.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=True,
                                                            local_files_only=True).eval().to(self.device)
                except OSError as exc:
                    raise RuntimeError("PII-Tracer is not downloaded: run `python -m pii_gate.tracer --download`") from exc
        return self._model

    def predict(self, text: str):  # noqa: ANN201
        import torch
        with torch.no_grad():
            return self._load().predict(text)[0]

    def detect(self, text: str) -> list[Span]:
        out: list[Span] = []
        for base, chunk in _chunks(text):
            for s in self.predict(chunk):
                kind = "DATE" if s.label == "private_date" else LABEL_KIND.get(s.label, "OTHER")
                if kind == "DATE" and not self.include_dates:
                    continue
                a, b = _trim(text, base + s.start, base + s.end)
                if b > a:
                    out.append(Span(a, b, kind))
        return out


def _chunks(text: str):  # noqa: ANN202
    """Split long text at whitespace so each piece stays under the model's token limit."""
    pos = 0
    while pos < len(text):
        end = min(len(text), pos + _CHUNK)
        if end < len(text):
            cut = text.rfind(" ", pos, end)
            end = cut if cut > pos else end
        yield pos, text[pos:end]
        pos = end


def _trim(text: str, a: int, b: int) -> tuple[int, int]:
    """Drop surrounding whitespace and trailing sentence punctuation the model sometimes includes."""
    while a < b and text[a].isspace():
        a += 1
    while b > a and (text[b - 1].isspace() or text[b - 1] in ".,;:!?"):
        b -= 1
    return a, b


def download() -> None:
    from huggingface_hub import snapshot_download
    path = snapshot_download(MODEL_ID, revision=REVISION)
    print("downloaded to", path)


if __name__ == "__main__":
    import sys
    if "--download" in sys.argv:
        download()
    else:
        print(__doc__)
