#!/usr/bin/env bash
# Stops all running background services

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "🛑 Stopping all background assistant services..."

for PID_FILE in data/logs/*.pid; do
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null || true
            echo "✔ Stopped process (PID: $PID)"
        fi
        rm -f "$PID_FILE"
    fi
done

pkill -f "python main.py" 2>/dev/null || true
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "bridges/messenger/monitor.py" 2>/dev/null || true
pkill -f "bridges/whatsapp/server.js" 2>/dev/null || true
pkill -f "node server.js" 2>/dev/null || true
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3001/tcp 2>/dev/null || true
sleep 1

echo "✅ All assistant services stopped."
