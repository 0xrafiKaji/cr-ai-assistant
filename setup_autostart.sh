#!/usr/bin/env bash
# Sets up automatic startup for Assistant on PC boot / login

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
mkdir -p "$HOME/.config/autostart"

DESKTOP_FILE="$HOME/.config/autostart/cr-ai-assistant.desktop"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=CR AI Assistant Background
Comment=Starts Autonomous AI CR Assistant on Login
Exec=$DIR/start_background.sh
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
EOF

chmod +x "$DESKTOP_FILE"

echo "✅ Autostart configured successfully!"
echo "📍 Entry created at: $DESKTOP_FILE"
echo "🚀 Assistant will now launch automatically in background whenever system is booted!"
