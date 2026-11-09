from corrector.langcheck import drift, looks_darija
from corrector.pipeline import Corrector
from corrector.config import Settings
import dataclasses


def test_translation_to_english_is_rejected():
    src = "wach t9dr t3awnni f had lmochkil, rah mabghach ykhdm lprogramme dyali"
    out = "Watch the town hall meeting for Had Lmochkil, because many people will learn about the programme daily."
    assert "rewrote" in drift(src, out)


def test_script_change_is_rejected():
    assert "script" in drift("salam khouya kifach nta", "سلام خويا كيفاش نتا")


def test_normal_typo_fixes_pass():
    assert drift("Hi, I recieve teh email yesterday and it were wrong.", "Hi, I received the email yesterday and it was wrong.") == ""
    assert drift("Je suis alé au magazin avec mon ami.", "Je suis allé au magasin avec mon ami.") == ""
    assert drift("teh", "the") == ""  # too short to judge


def test_darija_detection():
    assert looks_darija("wach t9dr t3awnni f had lmochkil")
    assert looks_darija("سلام خويا كيفاش نتا")
    assert not looks_darija("Hi, I recieve teh email yesterday and it were wrong.")
    assert not looks_darija("Je suis allé au magasin avec mon ami.")


class Rewriter:
    external = False

    def correct(self, text):
        return "Completely different English sentence about something else entirely, sorry."


def test_pipeline_keeps_original_when_model_rewrites():
    st = Settings.load()
    for enabled in (True, False):
        s = dataclasses.replace(st, pii={**st.pii, "enabled": enabled})
        src = "wach t9dr t3awnni f had lmochkil, rah mabghach ykhdm lprogramme dyali"
        r = Corrector(s, provider=Rewriter()).correct(src)
        assert r.text == src and not r.changed and r.skipped
