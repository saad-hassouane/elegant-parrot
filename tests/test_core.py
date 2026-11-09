import json
import threading
import urllib.request

import pytest

from corrector.config import Settings
from corrector.pipeline import Corrector
from pii_gate import Gate, OutboundBlocked, ProtectedCallFailed, RegexDetector, Vault
from pii_gate.server import make_server

GATE = Gate(ner=False)
S = Settings.load()
TEXT = "Contact me at john.doe@acme.com or +33 6 12 34 56 78, IBAN FR76 3000 6000 0112 3456 7890 189. Card 4111 1111 1111 1111."


class Echo:
    name, external = "echo", False
    def correct(self, t): return t.replace("Contact", "Please contact")


class External(Echo):
    external = True


def test_roundtrip_and_removal():
    with GATE.session() as s:
        safe = s.protect(TEXT)
        for raw in ["john.doe@acme.com", "+33 6 12 34 56 78", "4111 1111 1111 1111", "FR76"]:
            assert raw not in safe
        assert s.restore(safe).text == TEXT


def test_luhn_rejects_random_digits():
    with GATE.session() as s:
        assert s.protect("order 1234 5678 9012 3456") == "order 1234 5678 9012 3456"


def test_same_value_same_token():
    with GATE.session() as s:
        safe = s.protect("a@b.com and a@b.com")
        assert len(s.vault.tokens()) == 1


def test_mangled_brackets_tolerated():
    with GATE.session() as s:
        safe = s.protect("mail a@b.com now")
        tok = s.vault.tokens()[0]
        assert s.restore(safe.replace(tok, tok.strip("⟦⟧"))).text == "mail a@b.com now"


def test_fail_closed():
    with GATE.session() as s:
        s.protect("mail a@b.com")
        assert not s.restore("nothing").ok
        assert not s.restore(f"{s.vault.tokens()[0]} ⟦EMAIL_ZZZZZ⟧").ok


def test_vault_closed_forgets():
    v = Vault(); t = v.put("EMAIL", "a@b.com"); v.close()
    assert v.get(t) is None and v.tokens() == []


def test_outbound_gate_blocks():
    with GATE.session() as s, pytest.raises(OutboundBlocked):
        s.check_outbound("hello a@b.com")


def test_custom_pattern_pluggable():
    g = Gate(RegexDetector(extra={"EMPLOYEE": r"EMP-\d{6}"}))
    with g.session() as s:
        assert "EMP-123456" not in s.protect("id EMP-123456")


def test_guard_decorator_agnostic():
    seen = []
    def llm(t): seen.append(t); return t.upper().replace("⟦EMAIL_", "⟦EMAIL_")
    out = GATE.guard(lambda t: seen.append(t) or t)("mail a@b.com")
    assert out == "mail a@b.com" and "a@b.com" not in seen[0]
    with pytest.raises(ProtectedCallFailed):
        GATE.guard(lambda t: "dropped")("mail a@b.com")
    assert GATE.guard(lambda t: "dropped", on_failure="original")("mail a@b.com") == "mail a@b.com"


def test_protect_messages():
    with GATE.session() as s:
        m = s.protect_messages([{"role": "user", "content": "hi a@b.com"}])
        assert "a@b.com" not in m[0]["content"]


def test_corrector_local_external_and_fail_safe():
    for prov in (Echo(), External()):
        res = Corrector(S, prov, GATE).correct(TEXT)
        assert res.ok and res.text == TEXT.replace("Contact", "Please contact")
    class Dropper(Echo):
        def correct(self, t): return "nothing"
    res = Corrector(S, Dropper(), GATE).correct(TEXT)
    assert not res.ok and res.text == TEXT


def test_http_sidecar():
    srv = make_server(GATE, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}{path}", json.dumps(body).encode())
        return json.load(urllib.request.urlopen(req))
    p = post("/protect", {"text": "mail a@b.com"})
    assert "a@b.com" not in p["safe_text"]
    r = post("/restore", {"session": p["session"], "text": p["safe_text"]})
    assert r["ok"] and r["text"] == "mail a@b.com"
    srv.shutdown()


def test_retry_recovers_from_flaky_model():
    calls = []
    class Flaky(Echo):
        def correct(self, t):
            calls.append(1)
            return "dropped" if len(calls) < 3 else t
    res = Corrector(S, Flaky(), GATE).correct(TEXT)
    assert res.ok and len(calls) == 3


def test_retry_exhausted_fails_safe():
    class Bad(Echo):
        def correct(self, t): return "dropped"
    res = Corrector(S, Bad(), GATE).correct(TEXT)
    assert not res.ok and res.text == TEXT


def test_composite_prefers_earlier_detector():
    from pii_gate import CompositeDetector, Span
    class Fuzzy:
        def detect(self, t): return [Span(0, len(t), "ORG")]
    d = CompositeDetector([RegexDetector(), Fuzzy()])
    spans = d.detect("mail a@b.com")
    assert [s.kind for s in spans] == ["EMAIL"]
