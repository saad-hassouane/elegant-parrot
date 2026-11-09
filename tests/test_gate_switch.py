"""pii.enabled switch and pii.languages selection."""
import dataclasses

import pytest

from corrector import factory
from corrector.config import Settings
from corrector.pipeline import Corrector
from pii_gate import Gate, MoroccanDetector, RegexDetector
from pii_gate.detectors import CompositeDetector


class Provider:
    def __init__(self, external):
        self.external, self.seen = external, []

    def correct(self, text):
        self.seen.append(text)
        return text.replace("teh", "the")


def _settings(**pii):
    st = Settings.load()
    return dataclasses.replace(st, pii={**st.pii, **pii})


def test_gate_off_local_sends_text_as_is_and_loads_no_detectors(monkeypatch):
    monkeypatch.setattr(factory, "build_gate", lambda s: pytest.fail("detectors must not load when the gate is off"))
    monkeypatch.setattr("corrector.pipeline.build_gate", factory.build_gate)
    prov = Provider(external=False)
    res = Corrector(_settings(enabled=False), provider=prov).correct("mail marie@acme.fr about teh plan")
    assert res.ok and res.text == "mail marie@acme.fr about the plan"
    assert prov.seen == ["mail marie@acme.fr about teh plan"]  # raw text: no placeholders were used


def test_gate_off_refuses_external_backend():
    prov = Provider(external=True)
    res = Corrector(_settings(enabled=False), provider=prov).correct("mail marie@acme.fr")
    assert not res.ok and prov.seen == [] and "disabled" in res.problems[0]


def test_gate_on_masks_before_provider():
    prov = Provider(external=False)
    Corrector(_settings(enabled=True), provider=prov).correct("mail marie@acme.fr about teh plan")
    assert "marie@acme.fr" not in prov.seen[0]


def test_unknown_language_and_bad_enabled_are_rejected():
    with pytest.raises(ValueError, match="unknown"):
        _ = Settings.from_dict({**{k: dict(v) if isinstance(v, dict) else v for k, v in
                                   __import__("corrector.config", fromlist=["DEFAULTS"]).DEFAULTS.items()},
                                "pii": {**Settings.load().pii, "languages": ["en", "klingon"]}})
    with pytest.raises(ValueError):
        MoroccanDetector(languages=["klingon"])


def _masks(langs, text, needle):
    g = Gate(CompositeDetector([RegexDetector(), MoroccanDetector(languages=langs)]), ner=False)
    with g.session() as s:
        return needle not in s.protect(text)


def test_languages_switch_the_matching_rules():
    darija = "Si Mohamed Bennani habite zenqa 12 hay Riad"
    assert _masks(["darija"], darija, "Mohamed Bennani") and not _masks(["en", "fr"], darija, "Mohamed Bennani")
    assert _masks(["darija"], darija, "zenqa 12 hay Riad") and not _masks(["fr"], darija, "zenqa 12 hay Riad")
    quartier = "il habite quartier Belvedere depuis longtemps"  # French cue word, no digits: only the "fr" rules catch it
    assert _masks(["fr"], quartier, "quartier Belvedere") and not _masks(["en", "darija"], quartier, "quartier Belvedere")
    assert _masks(["en"], "my name is john smith", "john smith") and not _masks(["fr", "darija"], "my name is john smith", "john smith")
    assert _masks(["fr"], "je m'appelle karim benali", "karim benali") and not _masks(["en"], "je m'appelle karim benali", "karim benali")


def test_darija_only_skips_spacy_without_error():
    st = _settings(languages=["darija"])
    det = factory.build_gate(st).detector
    assert [type(d).__name__ for d in det.detectors] == ["FilteredDetector", "FilteredDetector"]  # regex + names, no NER
    assert {type(d.inner).__name__ for d in det.detectors} == {"RegexDetector", "MoroccanDetector"}
