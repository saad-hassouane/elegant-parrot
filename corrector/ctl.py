"""elegant-parrot: control the corrector (enable/disable apps, edit settings, diagnose)."""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
import time
from pathlib import Path

import httpx
import tomlkit

from .appctx import active_window, classify
from .config import CATEGORIES, Settings, config_path, template


def _doc() -> tomlkit.TOMLDocument:
    p = config_path()
    return tomlkit.parse(p.read_text()) if p.is_file() else tomlkit.parse(template())


def _save(doc: tomlkit.TOMLDocument) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(tomlkit.dumps(doc))


def _set(doc: tomlkit.TOMLDocument, dotted: str, raw: str) -> None:
    try:
        value = tomlkit.parse(f"v = {raw}")["v"]  # true / 3 / "x" / ["a","b"]
    except Exception:  # noqa: BLE001 - bare word => string
        value = raw
    *parents, leaf = dotted.split(".")
    node = doc
    for k in parents:
        if k not in node:
            node[k] = tomlkit.table()
        node = node[k]
    node[leaf] = value


def cmd_status(_: argparse.Namespace) -> int:
    s = Settings.load()
    print(f"config: {config_path()}{'' if config_path().is_file() else '  (not created - using defaults)'}")
    print(f"global: {'ENABLED' if s.enabled else 'DISABLED'}   backend: {s.backend}   retries: {s.retries}")
    print(f"local:  {s.ollama_model} @ {s.ollama_url}")
    print(f"external: {s.external_model} @ {s.external_base_url}  (api key {'set' if s.external_api_key else 'NOT set'})")
    if s.gate_enabled:
        print(f"pii:    gate ON  languages={s.languages} detectors={s.pii['detectors']} "
              f"ner_models={ {k: v for k, v in s.pii['ner_models'].items() if v and k in s.languages} } "
              f"deny={s.pii['kinds'].get('deny', [])}")
    else:
        print("pii:    gate OFF - text goes to the model unprotected" +
              (" (REFUSED: backend is external)" if s.backend == "external" else " (local backend)"))
    print("apps:")
    for cat in CATEGORIES:
        a, eff = s.apps[cat], s.for_app(cat)
        extra = f"backend={eff.backend} model={eff.ollama_model if eff.backend == 'local' else eff.external_model}"
        print(f"  {cat:<9}{'on ' if a.get('enabled', True) else 'OFF'}  copy={a['copy_key']:<13} paste={a['paste_key']:<13} {extra}")
    return 0


def cmd_toggle(args: argparse.Namespace, on: bool) -> int:
    doc = _doc()
    for target in args.targets:
        if target == "all":
            _set(doc, "general.enabled", str(on).lower())
        elif target in CATEGORIES:
            _set(doc, f"apps.{target}.enabled", str(on).lower())
        else:
            print(f"unknown target {target!r}; use one of: all, {', '.join(CATEGORIES)}", file=sys.stderr)
            return 2
    _save(doc)
    print(("enabled " if on else "disabled ") + ", ".join(args.targets))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    doc = _doc()
    _set(doc, args.key, args.value)
    _save(doc)
    Settings.load()  # validate it still parses
    print(f"{args.key} = {args.value}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    p = config_path()
    if p.exists() and not args.force:
        print(f"{p} exists (use --force to overwrite)", file=sys.stderr)
        return 1
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(template())
    print(f"wrote {p}")
    return 0


def cmd_which_app(args: argparse.Namespace) -> int:
    print(f"focus the target window now... ({args.delay}s)")
    time.sleep(args.delay)
    s, w = Settings.load(), active_window()
    cat = classify(w, s.apps)
    print(f"class={w.wm_class!r} process={w.process!r} title={w.title!r}" if w else "no active window")
    print(f"-> category: {cat} ({'enabled' if s.apps[cat].get('enabled', True) else 'DISABLED'})")
    print(f'   to route it elsewhere add its class to [apps.<category>] wm_class, e.g.  '
          f"elegant-parrot set apps.web.wm_class '[\"firefox\", \"{w.wm_class.lower() if w else ''}\"]'")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    s, bad = Settings.load(), 0

    def check(ok: bool, label: str, fix: str = "") -> None:
        nonlocal bad
        bad += not ok
        print(f"  [{'ok' if ok else '!!'}] {label}" + (f"  -> {fix}" if not ok and fix else ""))

    from .osdep import get_platform
    plat = get_platform()
    print(f"  platform: {plat.name}")
    for ok, label, fix in plat.check_environment():
        check(ok, label, fix)
    try:
        have = {m["name"] for m in httpx.get(f"{s.ollama_url}/api/tags", timeout=3).json()["models"]}
        check(True, f"ollama reachable at {s.ollama_url}")
        wanted = {s.ollama_model} | {s.for_app(c).ollama_model for c in CATEGORIES if s.for_app(c).backend == "local"}
        for m in sorted(wanted):
            check(m in have or f"{m}:latest" in have, f"ollama model {m}", f"ollama pull {m}")
    except Exception:  # noqa: BLE001
        check(False, f"ollama reachable at {s.ollama_url}", "ollama serve")
    if "external" in {s.backend} | {s.for_app(c).backend for c in CATEGORIES}:
        check(bool(s.external_api_key), "EXTERNAL_API_KEY set", "add it to .env")
        check(s.gate_enabled, "PII gate enabled (required for the external backend)", "elegant-parrot set pii.enabled true")
    if s.use_ner:
        for lang, model in ({k: v for k, v in s.pii["ner_models"].items() if k in s.languages} if s.gate_enabled else {}).items():
            if model:
                check(importlib.util.find_spec(model) is not None, f"spaCy model {model} ({lang})",
                      f"python -m spacy download {model}")
    print("all good" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def cmd_setup(a: argparse.Namespace) -> int:
    from .wizard import run
    return run(a)


def cmd_listen(_: argparse.Namespace) -> int:
    from .listen import run
    return run()


def main() -> int:
    ap = argparse.ArgumentParser(prog="elegant-parrot", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show effective settings and per-app rules").set_defaults(fn=cmd_status)
    for name, on in (("enable", True), ("disable", False)):
        p = sub.add_parser(name, help=f"{name} the corrector for: all | {' | '.join(CATEGORIES)}")
        p.add_argument("targets", nargs="+")
        p.set_defaults(fn=lambda a, on=on: cmd_toggle(a, on))
    p = sub.add_parser("set", help="set a config value, e.g. set apps.teams.backend local")
    p.add_argument("key"); p.add_argument("value"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("init", help="write a commented default config file"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("which-app", help="show which category the focused window falls into")
    p.add_argument("--delay", type=int, default=3); p.set_defaults(fn=cmd_which_app)
    sub.add_parser("path", help="print config path").set_defaults(fn=lambda _: print(config_path()) or 0)
    sub.add_parser("doctor", help="check dependencies, models and keys").set_defaults(fn=cmd_doctor)
    p = sub.add_parser("setup", help="interactive wizard: local-only or external model with the PII gate")
    p.add_argument("--mode", choices=["local", "external"]); p.add_argument("--languages", help="comma list: en,fr,darija")
    p.add_argument("--local-model"); p.add_argument("--provider", choices=["mistral", "scaleway", "nvidia", "custom"])
    p.add_argument("--base-url"); p.add_argument("--model", help="external model name")
    p.add_argument("--api-key", help="prefer the provider's env var (e.g. MISTRAL_API_KEY) over this flag: it shows in shell history")
    p.add_argument("--yes", action="store_true", help="no questions: accept defaults / flags (for scripts)")
    p.add_argument("--no-pull", action="store_true", help="never download an Ollama model"); p.add_argument("--test", action="store_true")
    p.set_defaults(fn=cmd_setup)
    sub.add_parser("listen", help="run in the background: global hotkey (works on Linux, macOS, Windows; models stay loaded)"
                   ).set_defaults(fn=cmd_listen)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
