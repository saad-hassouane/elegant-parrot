import json

import pytest

from corrector import anonymize
from corrector.anonymize import AnonymizePipeline, verify_audit_chain
from corrector.generalizer import Generalized
from pii_gate import Gate

TEXT = "Our senior architect Marcus Vance (marcus@acme.com) met Dr. Aris Thorne about his treatments."


class StubGen:
    def __init__(self, out):
        self.out = out

    def generalize(self, session, masked):
        return Generalized(self.out, True, [], 1, "stub")


@pytest.fixture(autouse=True)
def audit_file(tmp_path, monkeypatch):
    monkeypatch.setattr(anonymize, "AUDIT_PATH", tmp_path / "audit.jsonl")
    return tmp_path / "audit.jsonl"


def _pipe(out):
    return AnonymizePipeline(Gate(), StubGen(out))


def test_clean_rewrite_is_released_and_vault_destroyed():
    j = _pipe("An employee met a healthcare provider about a medical matter.").start(TEXT)
    assert j.status == "RELEASED" and not j.checks
    assert j.session.vault.tokens() == []  # vault wiped


def test_leftover_placeholder_keeps_text_local():
    j = _pipe("An employee ⟦PERSON_AAAAA⟧ met a provider.").start(TEXT)
    assert j.status == "KEPT_LOCAL" and "no_placeholders" in j.checks and j.candidate == ""


def test_leaked_value_keeps_text_local():
    j = _pipe("Write to marcus@acme.com about it.").start(TEXT)
    assert j.status == "KEPT_LOCAL"


def test_long_digit_run_keeps_text_local():
    j = _pipe("The employee paid account 123456789 yesterday.").start(TEXT)
    assert j.status == "KEPT_LOCAL" and "no_digit_runs" in j.checks


def test_model_error_fails_closed():
    class Boom:
        def generalize(self, *_):
            raise RuntimeError("ollama down")

    j = AnonymizePipeline(Gate(), Boom()).start(TEXT)
    assert j.status == "KEPT_LOCAL" and j.checks == {"pipeline_error": "RuntimeError"}


def test_audit_log_has_no_content_and_chain_detects_tampering(audit_file):
    _pipe("An employee met a healthcare provider.").start(TEXT)
    raw = audit_file.read_text()
    for secret in ("Marcus", "Vance", "marcus@acme.com", "Thorne", "healthcare provider"):
        assert secret not in raw
    assert verify_audit_chain() == (True, 2)
    lines = raw.splitlines()
    rec = json.loads(lines[0]); rec["outcome"] = "tampered"
    audit_file.write_text(json.dumps(rec) + "\n" + lines[1] + "\n")
    assert verify_audit_chain()[0] is False
