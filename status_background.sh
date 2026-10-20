#!/usr/bin/env bash
# Checks running status of all background assistant services

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo ""
echo "📊 AI Assistant Services Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Server check
if curl -s http://localhost:8000/api/mailer/status >/dev/null 2>&1; then
    echo "✔ Backend Server & Dashboard:  🟢 RUNNING (http://localhost:8000)"
else
    echo "❌ Backend Server & Dashboard:  🔴 STOPPED"
fi

# 2. WhatsApp Bridge check
WA_STATUS=$(curl -s http://localhost:3001/api/status 2>/dev/null)
if echo "$WA_STATUS" | grep -q '"connected":true'; then
    echo "✔ WhatsApp Bridge:             🟢 CONNECTED (Port 3001)"
elif curl -s http://localhost:3001/api/status >/dev/null 2>&1; then
    echo "⚠️ WhatsApp Bridge:             🟡 RUNNING (Needs WhatsApp Re-pair/QR)"
else
    echo "❌ WhatsApp Bridge:             🔴 STOPPED"
fi

# 3. Messenger Monitor check
if pgrep -f "bridges/messenger/monitor.py" >/dev/null 2>&1; then
    echo "✔ Messenger Monitor:           🟢 RUNNING"
else
    echo "❌ Messenger Monitor:           🔴 STOPPED"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 Commands:"
echo "   Start everything:  ./start_background.sh"
echo "   Stop everything:   ./stop_background.sh"
echo "   Check this status: ./status_background.sh"
echo "   View WhatsApp log: tail -f data/logs/whatsapp.log"
echo "   View Server log:   tail -f data/logs/server.log"
echo ""
