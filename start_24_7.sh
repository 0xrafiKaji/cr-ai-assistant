#!/usr/bin/env bash
# 24/7 TMUX Process Manager for Autonomous AI Assistant

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

SESSION_NAME="cr-assistant"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "✔ Assistant session is ALREADY RUNNING 24/7 in tmux!"
    echo "👉 To view live console: tmux attach -t $SESSION_NAME"
    echo "👉 To stop 24/7 session: tmux kill-session -t $SESSION_NAME"
    exit 0
fi

echo "🚀 Starting AI Assistant in 24/7 persistent TMUX session..."

# 1. Create session with Window 0: Backend Server & 6 AM Scheduler
tmux new-session -d -s "$SESSION_NAME" -c "$DIR" -n "server"
tmux send-keys -t "$SESSION_NAME:0" "./run.sh server" Enter

# 2. Window 1: Messenger CR Group Monitor
tmux new-window -t "$SESSION_NAME:1" -c "$DIR" -n "messenger"
tmux send-keys -t "$SESSION_NAME:1" "./run.sh messenger" Enter

# 3. Window 2: WhatsApp Bridge
tmux new-window -t "$SESSION_NAME:2" -c "$DIR" -n "whatsapp"
tmux send-keys -t "$SESSION_NAME:2" "./run.sh whatsapp" Enter

echo "🎉 ALL SERVICES STARTED SUCCESSFULLY IN 24/7 BACKGROUND SESSION!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 Web Dashboard:         http://localhost:8000"
echo "👀 View Live Terminal:     tmux attach -t $SESSION_NAME"
echo "   (Inside tmux, press 'Ctrl+B' then 'D' to detach without stopping)"
echo "🛑 Stop 24/7 Session:      tmux kill-session -t $SESSION_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
