#!/usr/bin/env bash
# Quick Start Script for Autonomous AI CR Assistant Agent

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:${PYTHONPATH:-}"

echo "🎓 Autonomous AI CR Assistant Agent Launcher"
echo "============================================="

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

ACTION="${1:-cli}"

case "$ACTION" in
    cli)
        echo "Starting Interactive CLI Playground..."
        python cli.py
        ;;
    server)
        echo "Starting FastAPI Core & Scheduler..."
        python main.py
        ;;
    whatsapp)
        echo "Starting Node.js WhatsApp Bridge..."
        cd bridges/whatsapp
        npm start
        ;;
    messenger)
        echo "Starting Headless Messenger CR Group Monitor..."
        python bridges/messenger/monitor.py
        ;;
    messenger-login)
        echo "Opening Browser for Facebook Login (to save session)..."
        python bridges/messenger/monitor.py --login
        ;;
    start)
        ./start_background.sh
        ;;
    stop)
        ./stop_background.sh
        ;;
    test)
        echo "Running automated test suite..."
        python -m unittest discover -s tests -p "test_*.py"
        ;;
    *)
        echo "Usage: ./run.sh [start|stop|server|cli|whatsapp|messenger|messenger-login|test]"
        ;;
esac
