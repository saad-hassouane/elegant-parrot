"""`elegant-parrot setup` - interactive first-run wizard (also scriptable with flags).

Asks one big question first: should the model run LOCALLY (nothing leaves the machine) or EXTERNALLY
(text is masked by the PII gate before it is sent to a provider you choose)? Then it writes
config.toml, stores any API key in an owner-only file, and checks the result."""
from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from .config import config_path, secrets_path, template
from .osdep import get_platform

LANGS = ("en", "fr", "darija")
LOCAL_MODELS = [
    ("llama3.2:3b", "fast (about 2 GB) - recommended for the hotkey"),
    ("qwen2.5:3b", "fast (about 2 GB) - good multilingual"),
    ("llama3:8b", "better quality, but 5x slower on CPU (about 5 GB)"),
]
# Suggestions only - provider catalogues change; the wizard lets you edit every value.
PROVIDERS = {
    "mistral": ("Mistral AI (EU, France)", "https://api.mistral.ai/v1", "mistral-small-latest", "MISTRAL_API_KEY"),
    "scaleway": ("Scaleway Generative APIs (EU, France)", "https://api.scaleway.ai/v1", "llama-3.1-8b-instruct", "SCALEWAY_API_KEY"),
    "nvidia": ("NVIDIA NIM free tier (US - trial service, no DPA)", "https://integrate.api.nvidia.com/v1",
               "mistralai/mistral-large-4-1t-a52b", "NVIDIA_API_KEY"),
    "custom": ("Any OpenAI-compatible endpoint", "", "", "EXTERNAL_API_KEY"),
}
GDPR_NOTICE = """\
  IMPORTANT - read before choosing the external model
  * The PII gate replaces names, e-mails, phones, IBANs, addresses... with placeholders before anything is sent.
    That is PSEUDONYMISATION: under GDPR the masked text is still personal data.
  * You still need a data-processing agreement (DPA) with the provider, and a legal basis. Prefer an EU provider.
  * Text that mentions health, religion, politics, union, sexual orientation, ethnicity, biometrics or criminal
    records is BLOCKED from the external model automatically (use the local model for it).
  * The gate is rule/NER based, so it can miss things. For sensitive text, choose local-only."""


@dataclass
class Choices:
    mode: str = "local"                    # local | external
    languages: list[str] = field(default_factory=lambda: list(LANGS))
    local_model: str = "llama3.2:3b"
    provider: str = "mistral"
    base_url: str = ""
    external_model: str = ""
    api_key: str = ""
    key_name: str = "EXTERNAL_API_KEY"


def apply(c: Choices, path: Path | None = None) -> Path:
    """Write the choices into config.toml (keeping the user's other settings and comments) and the key into the
    owner-only secrets file. Returns the config path."""
    import tomlkit

    from .ctl import _set
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        shutil.copy2(path, path.with_suffix(".toml.bak"))
        doc = tomlkit.parse(path.read_text())
    else:
        doc = tomlkit.parse(template())
    _set(doc, "general.backend", f'"{c.mode}"')
    _set(doc, "local.model", f'"{c.local_model}"')
    _set(doc, "pii.enabled", "true")  # the wizard never turns the gate off
    _set(doc, "pii.languages", "[" + ", ".join(f'"{x}"' for x in c.languages) + "]")
    if c.mode == "external":
        _set(doc, "external.base_url", f'"{c.base_url}"')
        _set(doc, "external.model", f'"{c.external_model}"')
        _set(doc, "pii.strict_external", "true")
        _set(doc, "pii.special_category", '"block"')
        if c.api_key:
            _write_secret(c.key_name, c.api_key)
            _set(doc, "external.api_key_env", f'"{c.key_name}"')
    path.write_text(tomlkit.dumps(doc))
    return path


def _write_secret(name: str, value: str) -> None:
    """Store `NAME=value` in an owner-only file. Replaces an existing line for the same name."""
    p = secrets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [ln for ln in (p.read_text().splitlines() if p.is_file() else []) if not ln.startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(p, 0o600)  # no-op semantics on Windows; the file lives in your profile folder
    except OSError:
        pass


def ollama_models(url: str = "http://127.0.0.1:11434") -> list[str] | None:
    """Installed Ollama models, or None if Ollama is not reachable."""
    try:
        return [m["name"] for m in httpx.get(f"{url}/api/tags", timeout=3).json()["models"]]
    except Exception:  # noqa: BLE001
        return None


def install_hint() -> str:
    return {"linux": "curl -fsSL https://ollama.com/install.sh | sh", "macos": "brew install ollama   (or https://ollama.com/download)",
            "windows": "winget install Ollama.Ollama   (or https://ollama.com/download)"}.get(get_platform().name, "https://ollama.com/download")


def check_external(base_url: str, key: str) -> str:
    """Validate the key with a content-free request (GET /models). Returns '' on success, else the problem."""
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"}, timeout=10)
        return "" if r.status_code < 300 else f"HTTP {r.status_code} - check the key and the base URL"
    except Exception as exc:  # noqa: BLE001
        return f"could not connect ({type(exc).__name__})"


# ---------------------------------------------------------------------------------------- interactive
def _choose(ask: Callable[[str], str], title: str, options: list[tuple[str, str]], default: int = 1) -> int:
    print(f"\n{title}")
    for i, (name, desc) in enumerate(options, 1):
        print(f"  {i}) {name}" + (f"  - {desc}" if desc else "") + ("   [default]" if i == default else ""))
    while True:
        raw = ask(f"Choose 1-{len(options)} [{default}]: ").strip() or str(default)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        print("  please enter a number from the list")


def _yes(ask: Callable[[str], str], q: str, default: bool = True) -> bool:
    raw = ask(f"{q} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not raw else raw.startswith("y")


def run(args=None, ask: Callable[[str], str] = input, secret: Callable[[str], str] = getpass.getpass) -> int:  # noqa: ANN001
    g = lambda n, d=None: getattr(args, n, d) if args is not None else d  # noqa: E731
    yes = bool(g("yes"))
    plat = get_platform()
    print("Elegant Parrot setup")
    print("====================")
    print(f"System: {plat.name}   Config file: {config_path()}")
    for ok, label, fix in plat.check_environment():
        print(f"  [{'ok' if ok else '!!'}] {label}" + ("" if ok else f"  -> {fix}"))

    c = Choices()
    mode = g("mode") or ("local" if yes else ["local", "external"][_choose(
        ask, "Where should the correction model run?",
        [("Local only (recommended)", "your text never leaves this computer; needs Ollama"),
         ("External model, with the PII gate", "text is masked first, then sent to a provider you pick")]) - 1])
    c.mode = mode

    langs = g("languages")
    if langs:
        c.languages = [x.strip() for x in langs.split(",") if x.strip()]
    elif not yes:
        raw = ask("\nLanguages to protect and correct (comma separated: en, fr, darija) [en,fr,darija]: ").strip()
        if raw:
            c.languages = [x.strip().lower() for x in raw.split(",") if x.strip()]
    bad = [x for x in c.languages if x not in LANGS]
    if bad:
        print(f"unknown language(s) {bad}; choose from {list(LANGS)}", file=sys.stderr)
        return 1

    # ---- local model (also the fallback for text the external model must never see)
    have = ollama_models()
    if have is None:
        print(f"\nOllama is not running / not installed. Install it with:\n    {install_hint()}\nthen start it and re-run this wizard "
              "(or continue - the config will be written anyway).")
    if g("local_model"):
        c.local_model = g("local_model")
    elif not yes and (mode == "local" or _yes(ask, "\nAlso set up a local model (used for sensitive text)?", True)):
        opts = [(m, d) for m, d in LOCAL_MODELS] + [("another model name", "type it")]
        i = _choose(ask, "Local model:", opts, 1)
        c.local_model = ask("Model name: ").strip() if i == len(opts) else LOCAL_MODELS[i - 1][0]
    if have is not None and c.local_model not in have and f"{c.local_model}:latest" not in have and not g("no_pull"):
        if yes or _yes(ask, f"\nModel '{c.local_model}' is not downloaded. Download it now with `ollama pull`?", True):
            print(f"Downloading {c.local_model} (this can take a few minutes)...")
            subprocess.run(["ollama", "pull", c.local_model], check=False)

    # ---- external provider
    if mode == "external":
        print("\n" + GDPR_NOTICE)
        if not (yes or _yes(ask, "\nI understand and want to use an external model", False)):
            print("Nothing changed. Re-run with the local option, or after talking to your DPO.")
            return 1
        keys = list(PROVIDERS)
        pk = g("provider") or (keys[0] if yes else keys[_choose(ask, "Provider:", [(v[0], "") for v in PROVIDERS.values()], 1) - 1])
        if pk not in PROVIDERS:
            print(f"unknown provider {pk!r}; choose from {keys}", file=sys.stderr)
            return 1
        c.provider, (_, url, model, c.key_name) = pk, PROVIDERS[pk]
        c.base_url = g("base_url") or (url if (yes and url) else ask(f"API base URL [{url}]: ").strip() or url)
        c.external_model = g("model") or (model if (yes and model) else ask(f"Model name [{model}]: ").strip() or model)
        if not (c.base_url and c.external_model):
            print("base URL and model are required for the external model", file=sys.stderr)
            return 1
        c.api_key = g("api_key") or os.environ.get(c.key_name, "") or ("" if yes else secret(f"{c.key_name} (input hidden, stored in an owner-only file): ").strip())
        if not c.api_key:
            print("No API key given: set it later in " + str(secrets_path()) + f" as {c.key_name}=...  (or export it).")

    path = apply(c)
    print(f"\nSaved {path}" + (f" and the key in {secrets_path()}" if c.api_key else ""))

    if mode == "external" and c.api_key and (g("test") or (not yes and _yes(ask, "Test the key now? (sends no text, only lists models)", True))):
        problem = check_external(c.base_url, c.api_key)
        print("  key works" if not problem else f"  key test failed: {problem}")

    print(f"""
All set. Mode: {'LOCAL ONLY' if mode == 'local' else 'EXTERNAL via PII gate (' + c.provider + ')'}   Languages: {', '.join(c.languages)}
Next steps:
  elegant-parrot doctor     check everything
  elegant-parrot listen     start the global shortcut ({plat.name}: see README for the key and permissions)
  elegant-parrot status     review the settings; change any with `elegant-parrot set <key> <value>`""")
    return 0
