"""Anonymise-before-export pipeline: automated checks decide, failures stay local.

    raw --strict mask--> masked --local LLM rewrite--> candidate --guardrails--> RELEASED --> may be sent
                                                              any failure --> KEPT_LOCAL (stays on this machine)

Guarantees this code enforces (and the limits - read them):
  * the rewrite runs on the LOCAL model only (see generalizer.py);
  * the candidate must contain ZERO placeholders, no vaulted value, nothing the strict detectors still
    flag, no long digit runs and no dense proper-noun fingerprint;
  * a candidate is released only if every automated check passes (otherwise it stays local), and the
    vault is destroyed on release, failure or expiry;
  * the audit log holds metadata only (never text), hash-chained so edits are detectable.
It does NOT prove the text is anonymous in the legal sense (Recital 26): the checks are heuristics, so
nobody has formally signed off - decide with your DPO whether that is enough to skip a DPA. Python cannot guarantee memory is zeroised; the vault drops its key and data."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from pii_gate.gate import TOKEN_RE, Gate, Session

from .generalizer import Generalizer

AUDIT_PATH = Path(os.environ.get("ELEGANT_PARROT_AUDIT", Path.home() / ".local/state/elegant-parrot/audit.jsonl"))
_audit_lock = threading.Lock()


def audit(event: str, job: str, **meta: object) -> None:
    """Append one content-free JSON line; each line carries the hash of the previous one."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _audit_lock:
        prev = "0" * 64
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size:
            with open(AUDIT_PATH, "rb") as f:
                f.seek(max(0, f.seek(0, 2) - 4096))
                last = f.read().splitlines()[-1]
            prev = json.loads(last)["hash"]
        rec = {"ts": round(time.time(), 3), "job": job, "event": event, **meta, "prev": prev}
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
        fd = os.open(AUDIT_PATH, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(rec) + "\n")


def verify_audit_chain() -> tuple[bool, int]:
    """True if no audit line was altered or removed from the middle. (Tail truncation is not detectable.)"""
    prev, n = "0" * 64, 0
    if not AUDIT_PATH.exists():
        return True, 0
    for line in AUDIT_PATH.read_text().splitlines():
        rec = json.loads(line)
        h = rec.pop("hash")
        if rec["prev"] != prev or hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest() != h:
            return False, n
        prev, n = h, n + 1
    return True, n


# ---- guardrails -------------------------------------------------------------------------------------
def guardrails(session: Session, strict_gate: Gate, original: str, candidate: str) -> dict[str, str]:
    """-> {check name: failure reason}; empty dict means every automated check passed."""
    fails: dict[str, str] = {}
    words = candidate.split()
    if not candidate.strip():
        return {"non_empty": "rewrite is empty"}
    if TOKEN_RE.search(candidate) or re.search(r"\b[A-Z]{3,}_[A-Z2-9]{5}\b", candidate):
        fails["no_placeholders"] = "placeholders remain, so the text is still pseudonymous"
    for orig in session.vault.originals():
        if orig in candidate:
            fails["no_vaulted_values"] = "a masked original value reappears"
            break
    spans = strict_gate.detector.detect(candidate)
    if spans:
        fails["detectors_clean"] = f"detectors still flag: {sorted({s.kind for s in spans})}"
    if re.search(r"\d{4,}", re.sub(r"[ .,-]", "", candidate)) and re.search(r"\d[\d .,-]{3,}\d", candidate):
        fails["no_digit_runs"] = "long digit sequence remains"
    # entity density: capitalised words that are not sentence-initial are proper-noun fingerprints
    proper = [w for i, w in enumerate(words) if i and w[:1].isupper() and not re.search(r"[.!?:]$", words[i - 1])]
    if len(words) >= 8 and len(proper) / len(words) > 0.12:
        fails["entity_density"] = f"{len(proper)} proper-noun-like words in {len(words)} - possible fingerprint"
    if len(candidate) > len(original):
        fails["not_longer"] = "rewrite is longer than the input (model added content)"
    return fails


@dataclass
class Job:
    id: str
    session: Session
    created: float
    status: str = "RUNNING"          # KEPT_LOCAL | RELEASED | EXPIRED | SENT
    candidate: str = ""
    checks: dict[str, str] = field(default_factory=dict)
    kinds: dict[str, int] = field(default_factory=dict)
    ms: int = 0
    model: str = ""

    def destroy(self) -> None:
        self.session.close()
        self.candidate = "" if self.status != "RELEASED" else self.candidate


class AnonymizePipeline:
    """Holds jobs in memory only; nothing is written except the content-free audit log."""

    def __init__(self, gate_strict: Gate, generalizer: Generalizer, ttl: float = 900.0) -> None:
        self.gate, self.gen, self.ttl = gate_strict, generalizer, ttl
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def _sweep(self) -> None:
        now = time.time()
        for j in list(self.jobs.values()):
            if now - j.created > self.ttl and j.status == "RUNNING":
                j.status = "EXPIRED"
                j.destroy()
                audit("expired", j.id)
            if now - j.created > self.ttl * 4:
                self.jobs.pop(j.id, None)

    def start(self, text: str) -> Job:
        job = Job(secrets.token_urlsafe(8), self.gate.session(), time.time())
        with self.lock:
            self._sweep()
            self.jobs[job.id] = job
        try:
            masked = job.session.protect(text)
            job.kinds = {}
            for k, _ in TOKEN_RE.findall(masked):
                job.kinds[k] = job.kinds.get(k, 0) + 1
            g = self.gen.generalize(job.session, masked)
            job.ms, job.model, job.candidate = g.ms, g.model, g.text
            job.checks = guardrails(job.session, self.gate, text, g.text)
            for p in g.problems:  # generalizer's own verification failures count as failed checks too
                job.checks.setdefault("rewrite_verification", p)
        except Exception as exc:  # noqa: BLE001 - any error keeps the text local
            job.checks = {"pipeline_error": type(exc).__name__}
        job.status = "RELEASED" if not job.checks else "KEPT_LOCAL"
        audit("evaluated", job.id, outcome=job.status, failed_checks=sorted(job.checks), kinds=job.kinds, model=job.model, ms=job.ms)
        if job.status == "KEPT_LOCAL":
            job.candidate = ""
            job.destroy()
        else:  # every check passed: release; the vault is destroyed now
            job.session.close()
            audit("released", job.id)
        return job

    def mark_sent(self, job_id: str, provider: str) -> str:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.status != "RELEASED":
                raise KeyError("only a released job can be sent")
            text, job.status, job.candidate = job.candidate, "SENT", ""
            audit("sent", job.id, provider=provider)
            return text
