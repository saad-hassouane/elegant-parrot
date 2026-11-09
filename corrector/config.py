"""Settings: built-in defaults < ~/.config/elegant-parrot/config.toml < real environment variables.
Secrets (EXTERNAL_API_KEY) are read from the environment / .env only, never from config.toml."""
from __future__ import annotations

import copy
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import tomlkit

CATEGORIES = ("teams", "terminal", "web", "native")  # match precedence; native = fallback

DEFAULTS: dict[str, Any] = {
    "general": {"enabled": True, "backend": "local", "retries": 3, "timeout": 120.0, "notify": True,
                "select_all_fallback": True, "max_chars": 8000,
                "terminal_use_primary": True, "terminal_replace_line": False},
    "local": {"url": "http://127.0.0.1:11434", "model": "llama3.2:3b"},
    "external": {"base_url": "https://integrate.api.nvidia.com/v1",
                 "model": "mistralai/mistral-large-4-1t-a52b", "reasoning_effort": "low",
                 "api_key_env": "EXTERNAL_API_KEY"},  # name of the env var / secrets-file entry that holds the key
    "pii": {
        "enabled": True,                # master switch for the PII gate (see README: refused for the external backend)
        "languages": ["en", "fr", "darija"],
        "detectors": ["regex", "names", "presidio"],
        "ner_models": {"en": "en_core_web_sm", "fr": "fr_core_news_sm"},
        "ner_threshold": 0.5,
        "kinds": {"deny": []},
        "extra_patterns": {},
        "tracer_dates": False,          # PII-Tracer: also mask dates/times (hurts readability)
        "strict_external": True,        # external backend: also mask special-category + indirect identifiers
        "special_category": "block",    # external backend + Art.9 data found: "block" (refuse) | "mask"
    },
    "apps": {},  # set below by default_apps(): copy/paste keys and window names differ per operating system
}


_TERMINALS = ["gnome-terminal", "kitty", "alacritty", "xterm", "konsole", "tilix", "terminator", "wezterm", "foot", "urxvt",
              "xfce4-terminal", "ghostty", "terminology", "st-256color", "lxterminal",          # Linux
              "windowsterminal", "wt.exe", "cmd.exe", "powershell", "pwsh", "conhost",           # Windows
              "com.apple.terminal", "com.googlecode.iterm2", "iterm", "warp"]                    # macOS
_BROWSERS = ["firefox", "chrome", "google-chrome", "chromium", "brave", "microsoft-edge", "vivaldi", "opera", "librewolf", "zen",
             "epiphany", "chrome.exe", "msedge", "firefox.exe", "brave.exe", "com.google.chrome", "com.apple.safari",
             "org.mozilla.firefox", "company.thebrowser.browser"]


def default_apps(plat: str | None = None) -> dict:
    """Per-app copy/paste keys and window-name matchers. macOS uses Cmd; terminals never use a bare Ctrl+C
    (it would interrupt the running program): Ctrl+Shift+C/V on Linux and Windows Terminal, Cmd+C/V on macOS."""
    plat = plat or sys.platform
    mac = plat == "darwin"
    plain = ("cmd+c", "cmd+v") if mac else ("ctrl+c", "ctrl+v")
    term = ("cmd+c", "cmd+v") if mac else ("ctrl+shift+c", "ctrl+shift+v")
    return {
        "teams": {"enabled": True, "copy_key": plain[0], "paste_key": plain[1],
                  "wm_class": ["teams-for-linux", "microsoft teams", "teams", "ms-teams", "com.microsoft.teams2"],
                  "title": [r"\| microsoft teams"]},
        "terminal": {"enabled": True, "copy_key": term[0], "paste_key": term[1], "wm_class": list(_TERMINALS), "title": []},
        "web": {"enabled": True, "copy_key": plain[0], "paste_key": plain[1], "wm_class": list(_BROWSERS), "title": []},
        "native": {"enabled": True, "copy_key": plain[0], "paste_key": plain[1], "wm_class": [], "title": []},
    }


def default_hotkey(plat: str | None = None) -> str:
    return "<cmd>+<shift>+e" if (plat or sys.platform) == "darwin" else "<ctrl>+<shift>+e"


DEFAULTS["apps"] = default_apps()
DEFAULTS["general"]["hotkey"] = default_hotkey()  # used by `elegant-parrot listen` (pynput syntax)

TEMPLATE = '''\
# elegant-parrot configuration. List only what you want to change; everything else uses defaults.
# Edit by hand, or:  elegant-parrot set <key> <value> | enable <app> | disable <app> | status
# Secrets (EXTERNAL_API_KEY) belong in .env or the environment, never in this file.

[general]
enabled = true        # global kill switch (elegant-parrot disable all)
backend = "local"     # "local" = Ollama, nothing leaves the device | "external" = tokenized text only
retries = 3           # attempts when a model mangles a placeholder (fresh tokens each time)
timeout = 120
notify = true
hotkey = "__HOTKEY__"        # global shortcut for `elegant-parrot listen` (pynput syntax: <ctrl>, <shift>, <cmd>, <alt>)
select_all_fallback = true  # nothing selected -> select the whole input field (Ctrl+A) and correct all of it (not in terminals)
max_chars = 8000            # refuse longer text (protects against selecting a whole page)
terminal_use_primary = true   # terminals: if Ctrl+Shift+C copies nothing, read the mouse selection (PRIMARY) directly
terminal_replace_line = false # terminals: clear the current input line (Ctrl+A, Ctrl+K) before pasting, so the correction REPLACES it.
                              # Only safe when you select the whole line; otherwise the rest of the line is deleted.

[local]
url = "http://127.0.0.1:11434"
model = "llama3.2:3b"

[external]
base_url = "https://integrate.api.nvidia.com/v1"
model = "mistralai/mistral-large-4-1t-a52b"
reasoning_effort = "low"
api_key_env = "EXTERNAL_API_KEY"    # which environment variable holds the key (`elegant-parrot setup` stores it for you)

[pii]
enabled = true                      # PII gate on/off. Off = text goes to the model as-is (LOCAL backend only: the external
                                    # backend is refused while the gate is off, so raw personal data cannot leave the machine)
languages = ["en", "fr", "darija"]  # which languages the gate understands: "en", "fr", "darija" (Moroccan Arabic, Latin + Arabic script)
                                    # drives the spaCy models, the name/address cues and the Moroccan gazetteer.
                                    # Structured IDs (email, IBAN, phone, card...) and the Art. 9 keywords are always checked.
detectors = ["regex", "names", "presidio"]   # "names" = EN/FR/Darija cues + gazetteer; drop "presidio" for faster, no statistical NER
ner_threshold = 0.5

[pii.ner_models]                    # spaCy model per language; only languages listed in `languages` are loaded ("darija" has none)
en = "en_core_web_sm"
fr = "fr_core_news_sm"

# On-device classifier (opt-in): add "tracer" to detectors after `python -m pii_gate.tracer --download`.
# ~1.2 GB, a few seconds to load, 1-2 s per text on CPU - use it in a long-running service, not the hotkey.
tracer_dates = false                # also mask dates/times

# Strict profile for the EXTERNAL backend only (local-only text is never touched by it):
strict_external = true              # also mask Art.9 cues (health, religion, ...) and job titles / family relations
special_category = "block"          # "block" = refuse to send text with Art.9 data externally | "mask" = tokenise and send

[pii.kinds]
deny = []                           # kinds NOT to tokenize, e.g. ["URL", "LOC"]

[pii.extra_patterns]                # your own identifiers; the key is the UPPERCASE kind name
# EMPLOYEE = "EMP-\\\\d{6}"

# Per-app rules. Precedence: teams > terminal > web > native (fallback for everything else).
# wm_class entries match the window class / process name, case-insensitive substring.
# Optional per-app overrides: backend = "local"|"external", model = "<ollama model>", external_model = "..."
# Find an app's class with:  elegant-parrot which-app

[apps.teams]
enabled = true

[apps.terminal]
enabled = true
copy_key = "__TERM_COPY__"           # plain Ctrl+C would interrupt the running program!
paste_key = "__TERM_PASTE__"

[apps.web]
enabled = true

[apps.native]
enabled = true
'''


def template(plat: str | None = None) -> str:
    """The commented default config, with this OS's keys filled in."""
    t = default_apps(plat)["terminal"]
    return (TEMPLATE.replace("__TERM_COPY__", t["copy_key"]).replace("__TERM_PASTE__", t["paste_key"])
            .replace("__HOTKEY__", default_hotkey(plat)))


def config_path() -> Path:
    return Path(os.environ.get("ELEGANT_PARROT_CONFIG", Path.home() / ".config/elegant-parrot/config.toml"))


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def read_user_config(path: Path | None = None) -> dict:
    path = path or config_path()
    return tomlkit.parse(path.read_text()).unwrap() if path.is_file() else {}


def secrets_path() -> Path:
    """Where `elegant-parrot setup` stores the external API key (owner-only file next to config.toml)."""
    return config_path().parent / ".env"


def _load_secrets() -> None:
    """Keys ending in API_KEY only, so a secrets file can't silently override config.toml.
    Lookup order: $CORRECTOR_ENV, the user config dir, then a repo-root .env (development)."""
    candidates = [Path(p) for p in [os.environ.get("CORRECTOR_ENV")] if p]
    candidates += [secrets_path(), Path(__file__).resolve().parent.parent / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            k, _, v = line.strip().partition("=")
            if k.strip().endswith("API_KEY") and v:
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_ENV = {  # env var -> (section, key, cast)
    "CORRECTOR_BACKEND": ("general", "backend", str.lower), "CORRECTOR_RETRIES": ("general", "retries", int),
    "CORRECTOR_TIMEOUT": ("general", "timeout", float), "OLLAMA_URL": ("local", "url", str),
    "OLLAMA_MODEL": ("local", "model", str), "EXTERNAL_BASE_URL": ("external", "base_url", str),
    "EXTERNAL_MODEL": ("external", "model", str), "EXTERNAL_REASONING_EFFORT": ("external", "reasoning_effort", str),
}


@dataclass(frozen=True)
class Settings:
    enabled: bool
    notify: bool
    backend: str
    retries: int
    timeout: float
    ollama_url: str
    ollama_model: str
    external_base_url: str
    external_model: str
    external_api_key: str
    external_reasoning_effort: str
    pii: dict
    apps: dict
    select_all_fallback: bool = True
    max_chars: int = 8000
    terminal_use_primary: bool = True
    terminal_replace_line: bool = False
    hotkey: str = "<ctrl>+<shift>+e"

    @property
    def gate_enabled(self) -> bool:
        return bool(self.pii.get("enabled", True))

    @property
    def languages(self) -> list[str]:
        return list(self.pii.get("languages", ["en", "fr", "darija"]))

    @property
    def use_ner(self) -> bool:
        return "presidio" in self.pii["detectors"]

    @classmethod
    def from_dict(cls, c: dict, api_key: str = "") -> "Settings":
        g, lo, ex = c["general"], c["local"], c["external"]
        langs = c["pii"].get("languages", ["en", "fr", "darija"])
        bad = sorted(set(langs) - {"en", "fr", "darija"})
        if bad:
            raise ValueError(f"[pii] languages: unknown {bad}; choose from ['en', 'fr', 'darija']")
        if not isinstance(c["pii"].get("enabled", True), bool):
            raise ValueError("[pii] enabled must be true or false")
        return cls(enabled=bool(g["enabled"]), notify=bool(g["notify"]), backend=str(g["backend"]).lower(),
                   retries=int(g["retries"]), timeout=float(g["timeout"]),
                   ollama_url=lo["url"], ollama_model=lo["model"],
                   external_base_url=ex["base_url"], external_model=ex["model"], external_api_key=api_key,
                   external_reasoning_effort=ex["reasoning_effort"], pii=c["pii"], apps=c["apps"],
                   select_all_fallback=bool(g.get("select_all_fallback", True)), max_chars=int(g.get("max_chars", 8000)),
                   terminal_use_primary=bool(g.get("terminal_use_primary", True)),
                   terminal_replace_line=bool(g.get("terminal_replace_line", False)),
                   hotkey=str(g.get("hotkey", default_hotkey())))

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        _load_secrets()
        c = deep_merge(DEFAULTS, read_user_config(path))
        for var, (sec, key, cast) in _ENV.items():
            if os.environ.get(var):
                c[sec][key] = cast(os.environ[var])
        if os.environ.get("USE_NER") == "0":
            c["pii"]["detectors"] = [d for d in c["pii"]["detectors"] if d != "presidio"]
        key_env = str(c["external"].get("api_key_env") or "EXTERNAL_API_KEY")
        return cls.from_dict(c, os.environ.get(key_env) or os.environ.get("EXTERNAL_API_KEY", ""))

    def for_app(self, category: str) -> "Settings":
        """Apply per-app overrides (backend / model / external_model)."""
        a = self.apps.get(category, {})
        return replace(self, backend=str(a.get("backend", self.backend)).lower(),
                       ollama_model=a.get("model", self.ollama_model),
                       external_model=a.get("external_model", self.external_model))
