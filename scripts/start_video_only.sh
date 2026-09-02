#!/bin/bash
# Start only the camera-to-MJPEG pipeline. This script does not start the
# conveyor, arm driver, inverse kinematics, or sortation node.

set -u
export PYTHONUNBUFFERED=1
export DISPLAY=:0
export XAUTHORITY=/home/jetson/.Xauthority

ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$HOME/dofbot_pro_ws/install/setup.bash"
YOLO_SCRIPT="$HOME/dofbot_pro_ws/src/dofbot_pro_yolov11/dofbot_pro_yolov11/yolov11.py"
PID_FILE="/tmp/dofbot_video_only_pids.txt"
LOG_DIR="/tmp/dofbot_logs"

mkdir -p "$LOG_DIR"

sortation_is_running() {
    local proc comm command
    for proc in /proc/[0-9]*; do
        comm=$(cat "$proc/comm" 2>/dev/null) || continue
        case "$comm" in
            tail|less|more|grep|sed) continue ;;
        esac
        command=$(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null) || continue
        case "$command" in
            *yolov11_sortation*) return 0 ;;
        esac
    done
    return 1
}

if ss -ltn 2>/dev/null | grep -q ':8765 '; then
    echo "[VIDEO] MJPEG service is already listening on port 8765"
    exit 0
fi

if sortation_is_running; then
    echo "[VIDEO][ERROR] Sortation node is running but port 8765 is unavailable"
    echo "[VIDEO][ERROR] Stop the sortation system before starting video-only mode"
    exit 2
fi

# Discard only stale records. Live processes from another mode are never killed.
if [ -f "$PID_FILE" ]; then
    while read -r pid _name; do
        if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
            echo "[VIDEO][ERROR] A previous video-only process is still running (PID $pid)"
            echo "[VIDEO][ERROR] Run: bash ~/stop_video_only.sh"
            exit 3
        fi
    done < "$PID_FILE"
fi
> "$PID_FILE"

launch_video_node() {
    local name=$1
    local command=$2
    local delay=$3
    local log_file="$LOG_DIR/video_only_${name}.log"

    echo "[VIDEO] Starting ${name}"
    setsid bash -c "source '$ROS_SETUP' && source '$WS_SETUP' && exec $command" \
        > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid $name" >> "$PID_FILE"
    sleep "$delay"

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "[VIDEO][ERROR] ${name} failed to start"
        tail -n 20 "$log_file" 2>/dev/null || true
        return 1
    fi
    echo "[VIDEO] ${name} started (PID $pid)"
}

cleanup_failed_start() {
    bash "$HOME/stop_video_only.sh" >/dev/null 2>&1 || true
}

launch_video_node "camera" \
    "ros2 launch orbbec_camera dabai_dcw2.launch.py" 5 || {
        cleanup_failed_start
        exit 10
    }

launch_video_node "msgToimg" \
    "ros2 run dofbot_pro_yolov11 msgToimg" 3 || {
        cleanup_failed_start
        exit 11
    }

launch_video_node "yolov11" \
    "python3 '$YOLO_SCRIPT'" 1 || {
        cleanup_failed_start
        exit 12
    }

echo "[VIDEO] Waiting for MJPEG port 8765"
for _attempt in $(seq 1 30); do
    if ss -ltn 2>/dev/null | grep -q ':8765 '; then
        echo "[VIDEO] Video-only service is ready: http://0.0.0.0:8765/"
        exit 0
    fi
    sleep 1
done

echo "[VIDEO][ERROR] Port 8765 did not open within 30 seconds"
tail -n 30 "$LOG_DIR/video_only_yolov11.log" 2>/dev/null || true
cleanup_failed_start
exit 13
