# Elegant Parrot 🦜

**System-wide spelling and grammar correction for any text field, with a privacy gate in front of the model.**
Select some text (or just click in a field), press one shortcut, and the corrected text replaces it. Works in
**English, French and Darija** (Moroccan Arabic, Latin and Arabic script). Runs on **Linux, macOS and Windows**.

[![CI](https://github.com/saad-hassouane/elegant-parrot/actions/workflows/ci.yml/badge.svg)](https://github.com/saad-hassouane/elegant-parrot/actions/workflows/ci.yml)

- **Local-only mode** – the model runs on your computer through [Ollama](https://ollama.com). Nothing leaves your machine.
- **External mode** – use a hosted model (Mistral, Scaleway, any OpenAI-compatible API). Before anything is sent, the
  **PII gate** replaces names, e-mails, phone numbers, IBANs, addresses… with placeholders and puts them back afterwards.
- A **setup wizard** asks which of the two you want and configures everything.

> **Honest status.** Linux is developed and tested on real hardware. The macOS and Windows adapters are written against the
> documented system APIs and tested with mocks and CI, but **have not been run on a real Mac or Windows PC by the author yet**.
> Please open an issue if something misbehaves. See [Known limits](#known-limits).

---

## Contents
1. [How it works](#how-it-works) · 2. [Quick start](#quick-start-any-os) · 3. [Install: Linux](#linux) · [macOS](#macos) · [Windows](#windows)
4. [Setup wizard](#the-setup-wizard) · 5. [Daily use](#daily-use) · 6. [Configuration](#configuration) · 7. [Languages](#languages)
8. [The PII gate](#the-pii-gate) · 9. [Privacy and GDPR](#privacy-and-gdpr-read-this) · 10. [Troubleshooting](#troubleshooting)
11. [Development](#development) · 12. [Known limits](#known-limits) · 13. [License](#license)

---

## How it works

```
 you press the shortcut
        │
        ▼
 copy the selection ──(nothing selected? select the whole field)──► text
        │
        ▼
 ┌───────────────────────── PII gate ─────────────────────────┐
 │ regex (IDs, e-mail, IBAN…) + names/places (EN·FR·Darija)   │
 │ + spaCy NER  →  "Marie Dupont" becomes ⟦PERSON_AB3XY⟧      │
 │ originals stay in an encrypted, in-memory vault            │
 └────────────────────────────────────────────────────────────┘
        │  masked text only
        ▼
 model:  Local (Ollama)   ── or ──   External (your provider, only if you chose it)
        │
        ▼
 checks: placeholders intact? same language/script? not rewritten?
        │  (any failure → your original text is left untouched)
        ▼
 put the real values back → paste over your selection → restore your clipboard
```

The corrector only fixes spelling, grammar and punctuation. It never translates, and for Darija it does not "standardise"
dialect words. If the model rewrites too much, the tool keeps your text and tells you.

---

## Quick start (any OS)

You need three things: **Python 3.10+**, **Ollama** (for local mode), and this repository.

1. **Install Ollama** → https://ollama.com/download (macOS: `brew install ollama` · Windows: `winget install Ollama.Ollama` ·
   Linux: `curl -fsSL https://ollama.com/install.sh | sh`) and start it.
2. **Get the code and run the installer for your OS** (details below):
   ```bash
   git clone https://github.com/saad-hassouane/elegant-parrot.git
   cd elegant-parrot
   ```
   | OS | Command |
   |---|---|
   | Linux | `bash scripts/install_linux.sh` |
   | macOS | `bash scripts/install_macos.sh` |
   | Windows (PowerShell) | `powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1` |
3. **Run the wizard** and pick local-only or external:
   ```bash
   .venv/bin/elegant-parrot setup          # Windows: .venv\Scripts\elegant-parrot.exe setup
   ```
4. **Start it** and press the shortcut in any text field:
   ```bash
   .venv/bin/elegant-parrot listen         # Linux/Windows: Ctrl+Shift+E · macOS: Cmd+Shift+E
   ```
   Run `elegant-parrot doctor` any time to check that everything is in place.

(Tip: activate the virtual environment once — `source .venv/bin/activate` or `.venv\Scripts\Activate.ps1` — and just type `elegant-parrot ...`.)

---

## Install per OS

### Linux
Requires an **X11 session** (Wayland blocks the key injection this tool relies on; choose "Ubuntu on Xorg" at the login screen).
```bash
sudo apt install xclip xdotool libnotify-bin python3-venv    # Debian/Ubuntu names
bash scripts/install_linux.sh --shortcut                      # --shortcut registers Ctrl+Shift+E in GNOME
elegant-parrot setup
```
Two ways to get the shortcut: the GNOME shortcut (`--shortcut`, no background process) **or** `elegant-parrot listen`
(works on any desktop and keeps the models loaded, so presses are faster).
To keep Ollama running after you log out/in: `bash scripts/install_ollama_user_service.sh` (a systemd *user* service).

### macOS
```bash
brew install python ollama          # if you don't have them
bash scripts/install_macos.sh --autostart    # --autostart = start `listen` at login (optional)
.venv/bin/elegant-parrot setup
```
macOS asks for permission **once**: *System Settings → Privacy & Security* → **Accessibility** and **Input Monitoring** →
allow the app that runs the tool (Terminal, iTerm, or your Python). Without it the shortcut is silently ignored.
Shortcut: **Cmd+Shift+E**.

### Windows
In PowerShell (Python 3.10+ from python.org must be on PATH):
```powershell
winget install Ollama.Ollama
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 -Autostart   # -Autostart = start at login (optional)
.venv\Scripts\elegant-parrot.exe setup
```
Shortcut: **Ctrl+Shift+E**. If a corporate policy blocks scripts, run the steps inside the script by hand
(`python -m venv .venv`, `pip install -e ".[ner,corrector,desktop]"`, `python -m spacy download en_core_web_sm fr_core_news_sm`).

### Manual install (any OS)
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[ner,corrector,desktop]"
python -m spacy download en_core_web_sm fr_core_news_sm
ollama pull llama3.2:3b
elegant-parrot setup
```
Extras: `ner` = Presidio + spaCy (names/places) · `corrector` = HTTP client + config editing · `desktop` = global hotkey ·
`dev` = pytest.

---

## The setup wizard

`elegant-parrot setup` asks, in this order:

1. **Where should the model run?** *Local only (recommended)* or *External model with the PII gate*.
2. **Languages** to protect and correct: any of `en, fr, darija`.
3. **Local model** (also used as the safe route for sensitive text): `llama3.2:3b` (fast, default), `qwen2.5:3b`, `llama3:8b`
   (better but ~5× slower on a CPU) or your own. It offers to download it with `ollama pull`.
4. *If you chose external:* it shows a **GDPR notice and asks you to confirm**, then lets you pick a provider
   (Mistral EU, Scaleway EU, NVIDIA NIM trial, or any OpenAI-compatible URL), the model name and your API key.

What it does for you:
- writes `~/.config/elegant-parrot/config.toml` (your previous file is kept as `config.toml.bak`; unrelated settings survive);
- stores the API key in `~/.config/elegant-parrot/.env` with **owner-only permissions** — never in `config.toml`;
- keeps the PII gate **on** (the wizard never turns it off) and enables the strict external profile;
- can test the key with a request that sends no text.

Scripted use:
```bash
elegant-parrot setup --yes --mode local --local-model llama3.2:3b --languages en,fr
MISTRAL_API_KEY=... elegant-parrot setup --yes --mode external --provider mistral --test
```
Prefer the environment variable to `--api-key`: command-line flags end up in your shell history.

---

## Daily use

| Situation | What happens |
|---|---|
| Text selected, press the shortcut | the selection is corrected and replaced |
| Nothing selected | the whole text field is selected and corrected (not in terminals) |
| Terminal | corrects the text you **highlighted with the mouse** (Linux); pastes at the cursor — see `terminal_replace_line` |
| Model takes a while | a notification shows "Correcting…" (animated on Linux) |
| You click another window meanwhile | nothing is pasted; the correction is left on your clipboard |
| Model translates or rewrites | your text is left unchanged and you're told why |
| Text mentions health, religion… and the backend is external | blocked; nothing is sent |

Useful commands:
```bash
elegant-parrot status            # effective settings, gate state, per-app rules
elegant-parrot doctor            # checks tools, permissions, Ollama, models, keys
elegant-parrot disable terminal  # per-app switches: teams | terminal | web | native | all
elegant-parrot which-app         # which category is the window you click into?
elegant-parrot set <key> <value> # e.g. set local.model llama3.2:3b
```

---

## Configuration

Everything lives in `~/.config/elegant-parrot/config.toml` (create it with `elegant-parrot init`, edit with `elegant-parrot set`).
Precedence: defaults < config file < environment variables (`CORRECTOR_BACKEND`, `OLLAMA_MODEL`, …).

| Key | Default | Meaning |
|---|---|---|
| `general.backend` | `local` | `local` (Ollama) or `external` (hosted API) |
| `general.hotkey` | `<ctrl>+<shift>+e` (`<cmd>` on macOS) | global shortcut for `elegant-parrot listen` |
| `general.select_all_fallback` | `true` | nothing selected → correct the whole field |
| `general.max_chars` | `8000` | refuse longer text |
| `general.terminal_replace_line` | `false` | terminals: clear the line before pasting so the fix *replaces* it (deletes the whole line!) |
| `local.model` | `llama3.2:3b` | Ollama model |
| `external.base_url`, `external.model` | | any OpenAI-compatible endpoint |
| `external.api_key_env` | `EXTERNAL_API_KEY` | name of the variable that holds the key |
| `pii.enabled` | `true` | PII gate on/off — **off is refused for the external backend** |
| `pii.languages` | `["en","fr","darija"]` | languages the gate understands |
| `pii.strict_external` | `true` | external backend: also mask Art. 9 cues, job titles, family relations |
| `pii.special_category` | `block` | external backend + Art. 9 data: `block` (refuse) or `mask` |
| `pii.detectors` | `["regex","names","presidio"]` | add `"tracer"` for the on-device classifier |
| `pii.kinds.deny` | `[]` | kinds to leave untouched, e.g. `["URL"]` |
| `pii.extra_patterns.X` | | your own identifiers, e.g. `EMPLOYEE = "EMP-\\d{6}"` |

Per-app overrides: e.g. keep Teams on the local model while everything else is external —
`elegant-parrot set apps.teams.backend local`.

---

## Languages

`pii.languages` controls which language rules the gate loads:

| Code | What it enables |
|---|---|
| `en` | English spaCy model, "my name is X", Mr/Mrs/Dr |
| `fr` | French spaCy model, "je m'appelle X", M./Mme, `rue`/`avenue`/`quartier` addresses |
| `darija` | Moroccan name and city lists (Latin + Arabic script), "smiti X" / "اسمي X", `zenqa`/`derb`/`hay`/`شارع` addresses |

Structured identifiers (e-mail, IBAN, phone, card, VIN, CIN…) and the sensitive-data keywords are **always** checked.

Correction quality differs by language. English and French are good. **Darija has no standard spelling**, so the tool is
deliberately conservative there: it fixes obvious typos, spacing, capitalisation and punctuation, keeps the script and the
dialect words, and leaves the text alone when the model would rewrite it. General-purpose small models do not truly
understand Darija; a Darija-trained model (e.g. `atlas-chat-2b`) understands it but behaves like a chat model, not a proofreader.

---

## The PII gate

**Detected by rules:** e-mail · IBAN · phone · payment card (Luhn-checked) · IP · URL · SSN · VIN · account numbers ·
money amounts · street addresses · ZIP codes · Moroccan CIN / ICE / RIB.
**Detected by name/place logic:** cues ("my name is…"), Moroccan gazetteer, spaCy NER (EN/FR).
**Optional on-device classifier:** Perplexity's [PII-Tracer](https://huggingface.co/perplexity-ai/PII-Tracer) (MIT, ~600M parameters).
Enable: `pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install "transformers>=5.2"`,
`python -m pii_gate.tracer --download` (1.2 GB, once, pinned to a reviewed commit), then add `"tracer"` to `pii.detectors`.
It loads from disk only (no network at run time) and is slow to start, so it suits a long-running `listen` process.

**Strict external profile** (automatic when the backend is external): also masks health/religion/politics/union/sexual
orientation/ethnicity/biometric/criminal cues and indirect identifiers (job titles, "leads the … department", family relations);
text containing special-category cues is **blocked** from the external model.

**Fail-closed rules:** the gate refuses to run with no detector; the external backend is refused if the gate is off;
an outbound re-scan blocks text that still contains detected PII; if the model drops or invents a placeholder the text is
retried and, failing that, left untouched.

**Playground** (from a clone): `python scripts/pii_playground.py` opens a local page (127.0.0.1 only) where you can paste text
and see what is detected, what would leave your machine, whether restoring works, and timings.
It also has an experimental *anonymise-for-export* path (a local model rewrites roles/relations/health context; strict
automated checks decide, and failures stay local).

---

## Privacy and GDPR (read this)

**No software can make text "GDPR compliant" on its own.** Please understand what this tool does and does not do:

- **Local-only mode** sends nothing to a third party. It is the strongest option and needs no agreement with anyone.
- **External mode uses pseudonymisation**, not anonymisation. Placeholders can be reversed (the key is in memory on your machine),
  so the masked text is **still personal data** and you need a **data-processing agreement** with the provider and a lawful basis.
  Prefer an EU provider with a signed DPA. A provider's free tier is not automatically covered by its DPA — check.
- The detectors are heuristics (regex, small NER models, keyword lists). They **will miss things**, especially unusual names,
  rare formats, and facts that identify someone only in combination. Sensitive text → use local-only mode.
- The audit log of the export path stores **no text**; the vault key lives in memory and is dropped after use.
- Nothing is sent anywhere unless you chose the external backend. There is no telemetry.

This is not legal advice. If you handle other people's data professionally, involve your DPO.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Shortcut does nothing (macOS) | Grant **Accessibility** and **Input Monitoring** to Terminal/Python, then restart `listen` |
| Shortcut does nothing (Linux) | You're on Wayland → use an X11 session; or run `elegant-parrot doctor` |
| "No text in the active field" | The app doesn't expose a normal text field; select the text first |
| "No text selected" in a terminal | Highlight the text with the mouse first (Linux); other OSes: select, then press the shortcut |
| "Left unchanged: the model rewrote the text" | The model tried to translate or rewrite; try a different model (`set local.model …`) |
| "Aborted (PII safety check)" | The gate blocked it (placeholders lost, or special-category data with the external backend) |
| Very slow | Use `llama3.2:3b`; run `listen` so models stay loaded; Ollama keeps the model in memory for 30 min |
| `ollama` not reachable | Start Ollama (`ollama serve`), then `elegant-parrot doctor` |
| Corrected text pasted into the wrong app | It can't happen: if the focused window changes while the model runs, nothing is pasted |
| Want to see what leaves the machine | `echo "text" | pii-correct --show-tokenized` or the playground |

---

## Development

```bash
pip install -e ".[ner,corrector,desktop,dev]" && python -m spacy download en_core_web_sm fr_core_news_sm
pytest -q
```
Layout: `pii_gate/` is a standalone, provider-agnostic library (`Gate`, detectors, vault; `pip install` it in any project) ·
`corrector/` is the app (config, pipeline, providers, wizard, hotkey) · `corrector/osdep/` has one adapter per OS ·
`scripts/` has installers, the playground and benchmarks. CI runs the tests on Ubuntu, macOS and Windows.

Using the gate on its own:
```python
from pii_gate import Gate
gate = Gate()
safe_llm = gate.guard(my_llm_call)          # any str -> str callable; raises if a placeholder is lost
```

---

## Known limits
- macOS and Windows are **unverified on real hardware** (mock-tested, CI-tested). Reports and fixes welcome.
- Linux **Wayland** is not supported. The terminal mouse-selection shortcut is Linux-only; macOS/Windows show a single
  "Correcting…" notification instead of an animated one.
- Darija correction is conservative by design; there is no dedicated Darija proofreading model.
- The PII gate is not a guarantee (see above).
- First press after a cold start can be slow while the model loads; `listen` mode avoids repeated start-ups.

## License
MIT — see [LICENSE](LICENSE).
