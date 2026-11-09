"""Hotkey flow against a fake OS adapter that models a text field, clipboard, PRIMARY and notifications."""
import dataclasses

import pytest

import corrector.hotkey as hk
from corrector.appctx import WindowInfo
from corrector.config import Settings
from corrector.osdep import Platform


class FakePlatform(Platform):
    """A text input: select-all selects, copy copies the selection, paste replaces it."""

    name = "fake"
    supports_primary = True

    def __init__(self, text, selected=False, primary="", modifier="ctrl", inplace=False):
        self.text, self.sel, self.clip = text, text if selected else "", "ORIGINAL CLIPBOARD"
        self.primary, self.keys, self.notes, self.window = primary, [], [], "w1"
        self.modifier, self.supports_inplace_notify = modifier, inplace

    def get_clipboard(self): return self.clip
    def set_clipboard(self, text): self.clip = text
    def get_primary(self): return self.primary
    def active_id(self): return self.window
    def active_window(self): return WindowInfo(wm_class="gedit", title="t", process="gedit")
    def notify(self, msg, timeout_ms=2500): self.notes.append(msg)

    def press(self, keys):
        self.keys.append(keys)
        if keys.endswith("+a"):
            self.sel = self.text
        elif keys == "ctrl+k":
            self.text = ""  # kill to end of line (cursor was moved to the start by ctrl+a)
        elif keys.endswith("+c"):
            if self.sel:
                self.clip = self.sel
        elif keys.endswith("+v"):
            self.text = self.clip if self.sel or not self.text else self.text + self.clip
            self.sel = ""


class FakeCorrector:
    def correct(self, text):
        class R:
            ok, changed, problems, skipped = True, True, [], ""
        R.text = text.replace("recieve", "receive").replace("teh", "the")
        return R


@pytest.fixture
def env(monkeypatch):
    def install(plat, category=None, **overrides):
        s = dataclasses.replace(Settings.load(), **overrides)
        monkeypatch.setattr(hk.Settings, "load", classmethod(lambda cls, path=None: s))
        monkeypatch.setattr(hk, "_corrector", lambda settings, cat: FakeCorrector())
        monkeypatch.setattr(hk.time, "sleep", lambda *_: None)
        if category:
            monkeypatch.setattr(hk, "classify", lambda win, apps: category)
        return s
    return install


def test_selected_text_is_replaced_and_clipboard_restored(env):
    f = FakePlatform("I recieve teh email", selected=True)
    env(f)
    assert hk.main(f) == 0
    assert f.text == "I receive the email" and f.clip == "ORIGINAL CLIPBOARD"
    assert "ctrl+a" not in f.keys                      # a selection existed: no select-all
    assert any("Correcting" in n for n in f.notes) and f.notes[-1] == "✓ Corrected"


def test_nothing_selected_corrects_the_whole_input_field(env):
    f = FakePlatform("I recieve teh email")
    env(f)
    assert hk.main(f) == 0 and "ctrl+a" in f.keys and f.text == "I receive the email"


def test_macos_uses_cmd_for_select_all(env):
    f = FakePlatform("I recieve teh email", modifier="cmd")
    env(f)
    assert hk.main(f) == 0 and "cmd+a" in f.keys and "ctrl+a" not in f.keys


def test_animated_loader_only_where_notifications_update_in_place(env):
    anim = FakePlatform("a recieve", selected=True, inplace=True)
    env(anim)
    hk.main(anim)
    assert any(n.startswith("⠋ Correcting") for n in anim.notes)


def test_terminal_never_gets_select_all(env):
    f = FakePlatform("I recieve teh email")
    env(f, category="terminal")
    assert hk.main(f) == 1 and "ctrl+a" not in f.keys and f.notes[-1] == "No text selected"


def test_too_long_text_is_refused(env):
    f = FakePlatform("x" * 9000, selected=True)
    env(f)
    assert hk.main(f) == 1 and f.text == "x" * 9000 and "Too long" in f.notes[-1]


def test_terminal_reads_primary_selection_and_strips_prompt_glyph(env, monkeypatch):
    f = FakePlatform("old line", primary="❯ donott swetch the modal")
    env(f, category="terminal")
    seen = {}

    class C:
        def correct(self, t):
            seen["t"] = t
            return FakeCorrector().correct(t)

    monkeypatch.setattr(hk, "_corrector", lambda s, c: C())
    assert hk.main(f) == 0
    assert seen["t"] == "donott swetch the modal" and "ctrl+k" not in f.keys


def test_terminal_primary_is_skipped_where_the_os_has_none(env):
    f = FakePlatform("x", primary="secret old selection")
    f.supports_primary = False
    env(f, category="terminal")
    assert hk.main(f) == 1 and f.notes[-1] == "No text selected"


def test_terminal_replace_line_mode_clears_the_line_first(env):
    f = FakePlatform("I recieve teh email", primary="I recieve teh email")
    env(f, category="terminal", terminal_replace_line=True)
    assert hk.main(f) == 0
    assert f.keys.index("ctrl+k") < len(f.keys) - 1 and f.text == "I receive the email"


def test_window_switch_during_correction_does_not_paste(env, monkeypatch):
    f = FakePlatform("I recieve teh email", selected=True)
    env(f)

    class Switching(FakeCorrector):
        def correct(self, text):
            f.window = "other-window"  # the user clicked elsewhere while the model was running
            return super().correct(text)

    monkeypatch.setattr(hk, "_corrector", lambda s, c: Switching())
    assert hk.main(f) == 3
    assert f.text == "I recieve teh email" and f.clip == "I receive the email" and "Window changed" in f.notes[-1]


def test_second_press_while_busy_is_ignored(env):
    f = FakePlatform("I recieve teh email", selected=True)
    env(f)
    assert hk._BUSY.acquire(blocking=False)
    try:
        assert hk.main(f) == 0 and f.text == "I recieve teh email" and not f.keys
    finally:
        hk._BUSY.release()
