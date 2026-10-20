#!/usr/bin/env bash
# Starts all Assistant Services in background with auto-logging

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

mkdir -p "$DIR/data/logs"

echo "🚀 Starting Autonomous AI CR Assistant in Background..."

# 1. Stop existing processes if any
"$DIR/stop_background.sh" 2>/dev/null || true

# 2. Start FastAPI Server & Scheduler
export PYTHONPATH="$DIR:${PYTHONPATH:-}"
setsid "$DIR/.venv/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 </dev/null > "$DIR/data/logs/server.log" 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > "$DIR/data/logs/server.pid"
echo "✔ Backend Server & 6:00 AM Scheduler started (PID: $SERVER_PID) -> http://localhost:8000"

# 3. Start Messenger CR Group Monitor
setsid "$DIR/.venv/bin/python" -u "$DIR/bridges/messenger/monitor.py" </dev/null > "$DIR/data/logs/messenger.log" 2>&1 &
MESSENGER_PID=$!
echo $MESSENGER_PID > "$DIR/data/logs/messenger.pid"
echo "✔ Messenger CR Group Monitor started (PID: $MESSENGER_PID)"

# Ensure persistent bot config exists and is non-empty
[ -s "$DIR/data/bot_config.json" ] || echo '{"auto_reply_enabled": true}' > "$DIR/data/bot_config.json"

# 4. Start WhatsApp Bridge (if paired)
if [ -d "$DIR/bridges/whatsapp/node_modules" ]; then
    setsid node "$DIR/bridges/whatsapp/server.js" </dev/null > "$DIR/data/logs/whatsapp.log" 2>&1 &
    WA_PID=$!
    echo $WA_PID > "$DIR/data/logs/whatsapp.pid"
    echo "✔ WhatsApp Bridge started (PID: $WA_PID)"
fi

sleep 2

echo ""
echo "🎉 ALL SERVICES ARE NOW RUNNING IN THE BACKGROUND 24/7!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 Open Web Dashboard:   http://localhost:8000"
echo "📜 View Live Server Log: tail -f data/logs/server.log"
echo "📜 View Messenger Log:   tail -f data/logs/messenger.log"
echo "🛑 Stop Everything:      ./stop_background.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
