import os
import stat
import sys

import pytest
import tomlkit

from corrector import wizard
from corrector.config import Settings, secrets_path


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEGANT_PARROT_CONFIG", str(tmp_path / "cfg" / "config.toml"))
    monkeypatch.setenv("CORRECTOR_ENV", str(tmp_path / "nonexistent.env"))
    monkeypatch.delenv("EXTERNAL_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(wizard, "ollama_models", lambda url="": None)  # no Ollama in CI
    return tmp_path


def _args(**kw):
    import argparse
    d = dict(mode=None, languages=None, local_model=None, provider=None, base_url=None, model=None, api_key=None,
             yes=True, no_pull=True, test=False)
    d.update(kw)
    return argparse.Namespace(**d)


def test_local_only_non_interactive(isolated):
    assert wizard.run(_args(mode="local", local_model="llama3.2:3b", languages="en,fr")) == 0
    s = Settings.load()
    assert s.backend == "local" and s.ollama_model == "llama3.2:3b" and s.languages == ["en", "fr"] and s.gate_enabled


def test_external_stores_key_outside_config_with_private_permissions(isolated, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test-1234567890")
    assert wizard.run(_args(mode="external", provider="mistral")) == 0
    cfg = (isolated / "cfg" / "config.toml").read_text()
    assert "sk-test-1234567890" not in cfg                       # the key never lands in config.toml
    sp = secrets_path()
    assert "MISTRAL_API_KEY=sk-test-1234567890" in sp.read_text()
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(sp).st_mode) == 0o600
    monkeypatch.delenv("MISTRAL_API_KEY")
    s = Settings.load()                                          # ...and is picked up from the secrets file
    assert s.backend == "external" and s.external_api_key == "sk-test-1234567890"
    assert s.external_base_url == "https://api.mistral.ai/v1" and s.pii["strict_external"] and s.pii["special_category"] == "block"
    assert s.gate_enabled


def test_wizard_never_disables_the_gate_and_keeps_existing_settings(isolated):
    cfg = isolated / "cfg" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[pii]\nenabled = false\n[general]\nmax_chars = 1234\n')
    assert wizard.run(_args(mode="local")) == 0
    s = Settings.load()
    assert s.gate_enabled and s.max_chars == 1234                # gate forced on; unrelated setting preserved
    assert cfg.with_suffix(".toml.bak").exists()                 # previous config backed up


def test_interactive_external_requires_explicit_consent(isolated):
    answers = iter(["2", "", "n", "n"])                          # external, default languages, no local model, NO consent
    rc = wizard.run(_args(yes=False), ask=lambda _p: next(answers), secret=lambda _p: "k")
    assert rc == 1 and not (isolated / "cfg" / "config.toml").exists()


def test_interactive_local_flow(isolated):
    answers = iter(["1", "en,darija", "2"])                      # local, languages, qwen2.5:3b
    assert wizard.run(_args(yes=False), ask=lambda _p: next(answers)) == 0
    s = Settings.load()
    assert s.backend == "local" and s.ollama_model == "qwen2.5:3b" and s.languages == ["en", "darija"]


def test_bad_language_is_rejected(isolated):
    assert wizard.run(_args(mode="local", languages="en,klingon")) == 1
