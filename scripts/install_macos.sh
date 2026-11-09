#!/usr/bin/env bash
# macOS installer. Usage: scripts/install_macos.sh [--autostart]
#   --autostart   write a LaunchAgent so `elegant-parrot listen` starts at login (opt-in)
# NOTE: written against documented macOS tools (pbcopy, osascript); not yet run on real hardware.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v python3 >/dev/null || { echo "Install Python 3.10+ first (https://www.python.org or: brew install python)"; exit 1; }
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -q -e "$ROOT[ner,corrector,desktop]"
"$ROOT/.venv/bin/python" -m spacy download en_core_web_sm fr_core_news_sm
"$ROOT/.venv/bin/elegant-parrot" init || true
command -v ollama >/dev/null || echo "Install Ollama: brew install ollama   (or https://ollama.com/download), then: ollama pull llama3.2:3b"
if [[ "${1:-}" == "--autostart" ]]; then
  PLIST="$HOME/Library/LaunchAgents/com.elegantparrot.listen.plist"
  mkdir -p "$(dirname "$PLIST")"
  cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.elegantparrot.listen</string>
  <key>ProgramArguments</key><array><string>$ROOT/.venv/bin/elegant-parrot</string><string>listen</string></array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
PL
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "LaunchAgent installed: $PLIST"
fi
cat <<MSG
Last step (macOS asks once): System Settings > Privacy & Security > Accessibility AND Input Monitoring:
allow Terminal (or the app/Python that runs 'elegant-parrot listen'). Then run:
  $ROOT/.venv/bin/elegant-parrot doctor
  $ROOT/.venv/bin/elegant-parrot listen        # shortcut: Cmd+Shift+E
MSG
