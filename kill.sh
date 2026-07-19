#!/bin/bash

PIDS=$(pgrep -f 'uvicorn backend.main|ffmpeg')

if [ -z "$PIDS" ]; then
    echo "Процессы не найдены. Всё чисто."
    exit 0
fi

echo "Найденные процессы:"
ps -p $PIDS -o pid=,comm=,args= 2>/dev/null | while read line; do
    echo "  $line"
done

echo ""
kill $PIDS 2>/dev/null && echo "Остановлено." || echo "Не удалось остановить."
