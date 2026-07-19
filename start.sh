#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/.venv"
LOG="/tmp/yummyanime.log"

if [ ! -d "$VENV" ]; then
    echo "venv не найден, создаю..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r "$DIR/requirements.txt"
    "$VENV/bin/playwright" install chromium
fi

if pgrep -f 'uvicorn backend.main' > /dev/null 2>&1; then
    echo "Сервер уже запущен. http://localhost:8000"
    exit 0
fi

cd "$DIR"
nohup "$VENV/bin/python" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > "$LOG" 2>&1 &
sleep 2

if curl -s -o /dev/null -w '' http://localhost:8000 2>/dev/null; then
    echo "Сервер запущен → http://localhost:8000"
else
    echo "Ошибка! Лог: $LOG"
    tail -5 "$LOG"
fi
