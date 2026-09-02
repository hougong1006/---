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

process_has_token() {
    local pid=$1
    local target=$2
    local arg base
    [ -r "/proc/$pid/cmdline" ] || return 1
    while IFS= read -r -d '' arg; do
        base=${arg##*/}
        if [ "$arg" = "$target" ] || [ "$base" = "$target" ]; then
            return 0
        fi
    done < "/proc/$pid/cmdline" 2>/dev/null
    return 1
}

find_processes_by_token() {
    local target=$1
    local proc pid
    for proc in /proc/[0-9]*; do
        pid=${proc##*/}
        [ "$pid" = "$$" ] && continue
        process_has_token "$pid" "$target" && printf '%s\n' "$pid"
    done
}

marker_for_name() {
    case "$1" in
        camera) printf '%s\n' "dabai_dcw2.launch.py" ;;
        msgToimg) printf '%s\n' "msgToimg" ;;
        yolov11) printf '%s\n' "yolov11.py" ;;
        *) return 1 ;;
    esac
}

mode_conflicts=""
for token in joint_self_test.py arm_driver arm_driver_node \
        kinemarics_dofbot yolov11_sortation; do
    found=$(find_processes_by_token "$token")
    [ -n "$found" ] && mode_conflicts="$mode_conflicts $token:$found"
done
if [ -n "$mode_conflicts" ]; then
    echo "[VIDEO][ERROR] Arm/joint-test processes are still running:$mode_conflicts"
    echo "[VIDEO][ERROR] Wait for command 3 or run bash ~/stop_sorting.sh first"
    exit 2
fi

if ss -ltn 2>/dev/null | grep -q ':8765 '; then
    echo "[VIDEO] MJPEG service is already listening on port 8765"
    exit 0
fi

# Remove an incomplete video-only start before launching a new pipeline.
partial_pids=""
for token in dabai_dcw2.launch.py '__node:=camera_container' \
        orbbec_camera_node msgToimg yolov11.py; do
    found=$(find_processes_by_token "$token")
    [ -n "$found" ] && partial_pids="$partial_pids $found"
done
if [ -n "$partial_pids" ]; then
    echo "[VIDEO] Cleaning an incomplete previous video start:$partial_pids"
    if ! bash "$HOME/stop_video_only.sh"; then
        echo "[VIDEO][ERROR] Previous video process cleanup failed"
        exit 4
    fi
fi

# Discard stale records, but refuse to duplicate a validated live process.
if [ -f "$PID_FILE" ]; then
    while read -r pid name; do
        marker=$(marker_for_name "$name" 2>/dev/null || true)
        if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null && \
                [ -n "$marker" ] && process_has_token "$pid" "$marker"; then
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
