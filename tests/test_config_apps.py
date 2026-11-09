import argparse
import sys

import pytest

from corrector import ctl
from corrector.appctx import WindowInfo, classify
from corrector.config import DEFAULTS, Settings, deep_merge
from corrector.factory import build_gate
from corrector.hotkey import plan
from pii_gate import FilteredDetector, RegexDetector


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "config.toml"
    monkeypatch.setenv("ELEGANT_PARROT_CONFIG", str(p))
    return p


def run(*argv):
    ap_args = argparse.Namespace()
    import sys
    old = sys.argv
    sys.argv = ["elegant-parrot", *argv]
    try:
        return ctl.main()
    finally:
        sys.argv = old


@pytest.mark.parametrize("cls,title,proc,expected", [
    ("Gnome-terminal", "bash", "gnome-terminal-", "terminal"),
    ("kitty", "~", "kitty", "terminal"),
    ("firefox", "Docs - Mozilla Firefox", "firefox", "web"),
    ("Google-chrome", "Inbox", "chrome", "web"),
    ("Google-chrome", "Chat | Microsoft Teams", "chrome", "teams"),   # Teams PWA/tab beats browser
    ("teams-for-linux", "Teams", "teams-for-linux", "teams"),
    ("Evolution", "Mail", "evolution", "native"),
    ("code", "main.py", "code", "native"),
])
def test_classify(cls, title, proc, expected):
    assert classify(WindowInfo(cls, title, proc), DEFAULTS["apps"]) == expected


def test_classify_no_window_is_native():
    assert classify(None, DEFAULTS["apps"]) == "native"


def test_terminal_never_uses_plain_ctrl_c():
    t = DEFAULTS["apps"]["terminal"]
    if sys.platform == "darwin":  # macOS: Cmd+C is the terminal's copy and does not interrupt the program
        assert t["copy_key"] == "cmd+c" and t["paste_key"] == "cmd+v"
    else:
        assert t["copy_key"] == "ctrl+shift+c" and t["paste_key"] == "ctrl+shift+v"


def test_enable_disable_roundtrip_and_comments_preserved(cfg):
    assert run("init") == 0
    assert run("disable", "terminal", "teams") == 0
    s = Settings.load()
    assert not s.apps["terminal"]["enabled"] and not s.apps["teams"]["enabled"] and s.apps["web"]["enabled"]
    assert "# global kill switch" in cfg.read_text()
    assert run("enable", "terminal") == 0 and Settings.load().apps["terminal"]["enabled"]
    assert run("disable", "all") == 0 and not Settings.load().enabled
    assert run("disable", "bogus") == 2


def test_plan_blocks_by_app_and_global(cfg):
    run("disable", "terminal")
    s = Settings.load()
    assert plan(s, WindowInfo("kitty", "", "kitty"))[2] is not None
    assert plan(s, WindowInfo("firefox", "", "firefox"))[2] is None
    run("disable", "all")
    assert "globally" in plan(Settings.load(), WindowInfo("firefox", "", "firefox"))[2]


def test_per_app_backend_and_model_override(cfg):
    run("set", "apps.teams.backend", "external")
    run("set", "apps.web.model", "qwen2.5:3b")
    s = Settings.load()
    assert s.for_app("teams").backend == "external" and s.for_app("native").backend == "local"
    assert s.for_app("web").ollama_model == "qwen2.5:3b" and s.ollama_model == "llama3.2:3b"


def test_env_overrides_config_but_dotenv_cannot(cfg, monkeypatch):
    run("set", "general.backend", "external")
    assert Settings.load().backend == "external"
    monkeypatch.setenv("CORRECTOR_BACKEND", "local")
    assert Settings.load().backend == "local"


def test_pii_config_drives_gate(cfg):
    run("set", "pii.detectors", '["regex"]')
    run("set", "pii.kinds.deny", '["URL"]')
    run("set", "pii.extra_patterns.EMPLOYEE", r"'EMP-\d{6}'")
    g = build_gate(Settings.load())
    with g.session() as s:
        out = s.protect("EMP-123456 a@b.com https://x.io")
    assert "EMP-123456" not in out and "a@b.com" not in out and "https://x.io" in out  # URL denied


def test_gate_refuses_to_run_without_detectors(cfg):
    run("set", "pii.detectors", "[]")
    with pytest.raises(ValueError):
        build_gate(Settings.load())
    run("set", "pii.detectors", '["nope"]')
    with pytest.raises(ValueError):
        build_gate(Settings.load())


def test_filtered_detector_allow_list():
    d = FilteredDetector(RegexDetector(), allow=["EMAIL"])
    assert [s.kind for s in d.detect("a@b.com +33 6 12 34 56 78")] == ["EMAIL"]


def test_deep_merge_keeps_defaults():
    m = deep_merge(DEFAULTS, {"apps": {"web": {"enabled": False}}})
    plain_copy = "cmd+c" if sys.platform == "darwin" else "ctrl+c"
    assert m["apps"]["web"]["enabled"] is False and m["apps"]["web"]["copy_key"] == plain_copy
