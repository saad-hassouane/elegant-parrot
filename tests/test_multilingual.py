"""Labelled EN / FR / Darija cases: every `secret` must be masked, every `keep` must survive."""
import pytest

from pii_gate import Gate

CASES = [
    # --- English ---
    ("Marcus Vance (SSN: 452-00-8192) lives at 742 Evergreen Terrace, Seattle, WA 98101.",
     ["Marcus Vance", "452-00-8192", "742 Evergreen Terrace", "98101"], ["SSN"]),
    ("Account #8839-2041-9921 holds $142,500.00 and the VIN is 5YJYGDEE8NF123456.",
     ["8839-2041-9921", "$142,500.00", "5YJYGDEE8NF123456"], ["Account"]),
    ("Hi, I am Marie Dupont, please wire 1200 EUR. Afterward I will call.",
     ["Marie Dupont", "1200 EUR"], ["Hi", "Afterward", "please wire"]),
    ("My name is john smith and my number is +1 415 555 0199.",
     ["john smith"], ["My name is"]),
    # --- French ---
    ("Bonjour, je m'appelle Karim Benali, j'habite 12 bis rue de la Paix, Paris.",
     ["Karim Benali", "12 bis rue de la Paix"], ["Bonjour", "j'habite"]),
    ("Mme Sophie Martin a payé 350 euros, IBAN FR76 3000 6000 0112 3456 7890 189.",
     ["Sophie Martin", "350 euros", "FR76 3000 6000 0112 3456 7890 189"], ["a payé"]),
    ("Je suis allé au magasin avec mon ami Pierre Durand.",
     ["Pierre Durand"], ["Je suis allé au magasin"]),
    # --- Darija, Latin script (lowercase chat style) ---
    ("salam, smiti youssef alaoui w ana sakn f Casablanca, tel 06 61 23 45 67",
     ["youssef alaoui", "Casablanca", "06 61 23 45 67"], ["salam", "sakn"]),
    ("ana smiti Fatima Zahra, CIN BE123456, kanskn f zenqa 12 hay Riad Rabat",
     ["Fatima Zahra", "BE123456", "zenqa 12 hay Riad"], ["kanskn"]),
    ("Si Mohamed Bennani 3endo compte RIB 007 780 0001234567890123 45 f Marrakech",
     ["Mohamed Bennani", "007 780 0001234567890123 45", "Marrakech"], ["compte"]),
    ("khasni nkhlles 2500 DH l Lalla Khadija Tazi bach t3awnni",
     ["2500 DH", "Khadija Tazi"], ["khasni nkhlles", "bach"]),
    # --- Darija, Arabic script ---
    ("اسمي يوسف العلوي وساكن في الدار البيضاء",
     ["يوسف العلوي", "الدار البيضاء"], ["وساكن"]),
    ("السيد محمد بناني يسكن في شارع محمد الخامس بالرباط، هاتفه +212 661 234 567",
     ["محمد بناني", "شارع محمد الخامس", "الرباط", "+212 661 234 567"], ["يسكن"]),
    ("للا فاطمة الزهراء حولت 3000 DH إلى حسابها",
     ["فاطمة", "3000 DH"], ["حولت"]),
]


def _gate() -> Gate:
    return Gate()  # regex + names + spaCy NER (arbitrary EN/FR names)


@pytest.mark.parametrize("text,secrets,keep", CASES, ids=[c[0][:30] for c in CASES])
def test_masks_secrets_keeps_prose(text, secrets, keep):
    with _gate().session() as s:
        safe = s.protect(text)
        assert s.restore(safe).text == text  # lossless round trip
    leaks = [x for x in secrets if x in safe]
    assert not leaks, f"leaked {leaks!r} in: {safe}"
    lost = [k for k in keep if k not in safe]
    assert not lost, f"over-masked {lost!r} in: {safe}"


# ---- strict profile: special-category data + indirect identifiers --------------------------------
from corrector.config import Settings  # noqa: E402
from corrector.factory import build_gate  # noqa: E402
from corrector.pipeline import Corrector  # noqa: E402
from pii_gate import SPECIAL_CATEGORY_KINDS  # noqa: E402

STRICT = [
    ("He discussed his ongoing treatments for Multiple Sclerosis.", "HEALTH"),
    ("Il suit un traitement contre le cancer à l'hôpital.", "HEALTH"),
    ("kayakhod 3ilaj f sbitar", "HEALTH"),
    ("هو مريض ويتلقى علاج في المستشفى", "HEALTH"),
    ("She is an active member of the trade union.", "UNION"),
    ("He was convicted last year.", "CRIMINAL"),
]


class _FakeProvider:
    external = True

    def __init__(self):
        self.called = False

    def correct(self, text):
        self.called = True
        return text


def _external_settings(**pii):
    st = Settings.load()
    from dataclasses import replace
    return replace(st, backend="external", pii={**st.pii, **pii})


@pytest.mark.parametrize("text,kind", STRICT)
def test_special_category_blocked_externally(text, kind):
    st = _external_settings()
    prov = _FakeProvider()
    res = Corrector(st, provider=prov, gate=build_gate(st)).correct(text)
    assert not res.ok and kind in " ".join(res.problems) and not prov.called


def test_indirect_identifiers_masked_in_strict_profile():
    st = _external_settings(special_category="mask")
    with build_gate(st).session() as s:
        safe = s.protect("Our senior cloud architect and his sister, who leads the pediatric surgery department, met.")
    for leaked in ("senior cloud architect", "his sister", "pediatric surgery department"):
        assert leaked not in safe, safe


def test_local_backend_unaffected():
    st = Settings.load()
    assert st.backend == "local"
    with build_gate(st).session() as s:
        assert "treatments" in s.protect("He discussed his ongoing treatments.")  # local text is not over-masked
    assert SPECIAL_CATEGORY_KINDS >= {"HEALTH", "RELIGION"}
