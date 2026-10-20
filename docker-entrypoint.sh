#!/usr/bin/env bash
set -e

echo "=================================================="
echo "🚀 Starting Autonomous AI Assistant Container"
echo "=================================================="

# 1. Start WhatsApp Bridge in background
echo "📱 Starting WhatsApp Bridge on port 3001..."
cd /app/bridges/whatsapp
node server.js &
NODE_PID=$!

# Wait 2 seconds for Node server to bind port
sleep 2

# 2. Start FastAPI Core Server in foreground
echo "⚡ Starting FastAPI Core & Scheduler on port 8000..."
cd /app
python main.py &
PYTHON_PID=$!

# Handle graceful shutdown
trap "echo '🛑 Stopping processes...'; kill -TERM $NODE_PID $PYTHON_PID; exit 0" SIGTERM SIGINT

wait $PYTHON_PID $NODE_PID
