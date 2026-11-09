#!/usr/bin/env bash
# Runs Ollama as a systemd *user* service bound to 127.0.0.1 (no sudo needed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p ~/.config/systemd/user
cp "$ROOT/scripts/ollama.user.service" ~/.config/systemd/user/ollama.service
pkill -u "$USER" -x ollama 2>/dev/null || true; sleep 1
systemctl --user daemon-reload
systemctl --user enable --now ollama
echo "Ollama user service enabled on 127.0.0.1:11434"
