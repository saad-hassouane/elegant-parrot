from pii_gate import Gate
from pii_gate.detectors import CompositeDetector, RegexDetector
from pii_gate.tracer import TracerDetector, _chunks, _trim


class _Span:
    def __init__(self, label, start, end):
        self.label, self.start, self.end = label, start, end


class FakeTracer(TracerDetector):
    """Stands in for the real model so the test needs no torch / download."""

    def __init__(self, spans, **kw):
        super().__init__(**kw)
        self._spans = spans

    def predict(self, text):
        return [s for s in self._spans if s.end <= len(text)]


def test_label_mapping_trim_and_dates_skipped():
    text = "Call Nadia Benali on 06 12 34 56 78. at 4:00 PM"
    i = lambda sub: text.index(sub)  # noqa: E731
    det = FakeTracer([_Span("private_person", i("Nadia"), i("Nadia") + 12), _Span("private_phone", i("06"), i("at")),
                      _Span("private_date", i("4:00"), len(text))])
    got = {(text[s.start:s.end], s.kind) for s in det.detect(text)}
    assert got == {("Nadia Benali", "PERSON"), ("06 12 34 56 78", "PHONE")}  # trailing '.' trimmed, date skipped
    assert any(s.kind == "DATE" for s in FakeTracer([_Span("private_date", i("4:00"), len(text))], include_dates=True).detect(text))


def test_chunks_cover_text_without_loss():
    text = ("word " * 2000).strip()
    parts = list(_chunks(text))
    assert len(parts) > 1 and all(len(c) <= 3000 for _, c in parts)
    assert all(text[b:b + len(c)] == c for b, c in parts)


def test_trim_and_gate_integration():
    assert _trim("  hi. ", 0, 6) == (2, 4)
    g = Gate(CompositeDetector([RegexDetector(), FakeTracer([_Span("other_pii", 0, 18)])]))
    with g.session() as s:
        safe = s.protect("Multiple Sclerosis is private.")
        assert "Multiple Sclerosis" not in safe and s.restore(safe).text == "Multiple Sclerosis is private."
