#!/usr/bin/env bash
# Registers a GNOME custom shortcut (default Ctrl+Shift+E) that runs the hotkey script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BINDING="${1:-<Ctrl><Shift>e}"
BASE=/org/gnome/settings-daemon/plugins/media-keys
KEY="$BASE/custom-keybindings/pii-corrector/"
cur=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)
if [[ "$cur" != *"pii-corrector"* ]]; then
  new=$(python3 - "$cur" "$KEY" <<'PY'
import ast, sys
cur = sys.argv[1]
lst = ast.literal_eval(cur.replace("@as ", ""))
lst.append(sys.argv[2]); print(lst)
PY
)
  gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$new"
fi
S="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$KEY"
gsettings set "$S" name "Elegant Parrot"
gsettings set "$S" command "$ROOT/.venv/bin/python -m corrector.hotkey"
gsettings set "$S" binding "$BINDING"
echo "Shortcut $BINDING installed."
