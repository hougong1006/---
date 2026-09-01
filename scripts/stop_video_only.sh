#!/bin/bash
# Stop only processes started by start_video_only.sh.

set -u
PID_FILE="/tmp/dofbot_video_only_pids.txt"

if [ ! -s "$PID_FILE" ]; then
    echo "[VIDEO] No video-only process is recorded"
    exit 0
fi

echo "[VIDEO] Stopping video-only service"
while read -r pid name; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
        echo "[VIDEO] Stopping ${name} (PID $pid)"
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    fi
done < "$PID_FILE"

sleep 2

while read -r pid name; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
        echo "[VIDEO] Force stopping ${name} (PID $pid)"
        kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
done < "$PID_FILE"

> "$PID_FILE"
echo "[VIDEO] Video-only service stopped"
