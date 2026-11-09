#!/usr/bin/env bash
# Linux (X11) installer. Usage: scripts/install_linux.sh [--shortcut] [--ollama-service]
#   --shortcut         register the GNOME shortcut (Ctrl+Shift+E)      (alternative: `elegant-parrot listen`)
#   --ollama-service   run Ollama as a systemd *user* service (starts at login)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Needs: sudo apt install xclip xdotool libnotify-bin python3-venv   (X11 session; Wayland is not supported)"
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -q -e "$ROOT[ner,corrector,desktop]"
"$ROOT/.venv/bin/python" -m spacy download en_core_web_sm fr_core_news_sm
"$ROOT/.venv/bin/elegant-parrot" init || true
for a in "$@"; do
  [[ "$a" == "--shortcut" ]] && bash "$ROOT/scripts/install_shortcut.sh"
  [[ "$a" == "--ollama-service" ]] && bash "$ROOT/scripts/install_ollama_user_service.sh"
done
echo "Next: ollama pull llama3.2:3b && $ROOT/.venv/bin/elegant-parrot doctor"
