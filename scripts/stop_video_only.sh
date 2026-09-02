#!/bin/bash
# Stop only processes started by start_video_only.sh.

set -u
PID_FILE="/tmp/dofbot_video_only_pids.txt"

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

terminate_pid_or_group() {
    local pid=$1
    local signal=$2
    local pgid
    if kill -0 -- "-$pid" 2>/dev/null; then
        kill "-$signal" -- "-$pid" 2>/dev/null || true
        return
    fi
    pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')
    if [ "$pgid" = "$pid" ]; then
        kill "-$signal" -- "-$pid" 2>/dev/null || kill "-$signal" "$pid" 2>/dev/null || true
    else
        kill "-$signal" "$pid" 2>/dev/null || true
    fi
}

echo "[VIDEO] Stopping video-only service"
validated_pids=()
validated_names=()
if [ -s "$PID_FILE" ]; then
    while read -r pid name; do
        marker=$(marker_for_name "$name" 2>/dev/null || true)
        if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null && \
                [ -n "$marker" ] && process_has_token "$pid" "$marker"; then
            echo "[VIDEO] Stopping ${name} process group (PID/PGID $pid)"
            terminate_pid_or_group "$pid" TERM
            validated_pids+=("$pid")
            validated_names+=("$name")
        fi
    done < "$PID_FILE"
fi

sleep 2

if [ "${#validated_pids[@]}" -gt 0 ]; then
    for index in "${!validated_pids[@]}"; do
        pid=${validated_pids[$index]}
        name=${validated_names[$index]}
        if [ -n "${pid:-}" ] && \
                { kill -0 -- "-$pid" 2>/dev/null || kill -0 "$pid" 2>/dev/null; }; then
            echo "[VIDEO] Force stopping ${name} process group (PID/PGID $pid)"
            terminate_pid_or_group "$pid" KILL
        fi
    done
fi

# If an interrupted launcher lost its PID file, recover only when the full
# sortation node is not running. This avoids stopping video owned by full mode.
if [ -z "$(find_processes_by_token yolov11_sortation)" ]; then
    for token in dabai_dcw2.launch.py '__node:=camera_container' \
            orbbec_camera_node msgToimg yolov11.py; do
        fallback_pids=$(find_processes_by_token "$token")
        while read -r pid; do
            if [ -n "$pid" ]; then
                echo "[VIDEO] Cleaning unrecorded $token process (PID $pid)"
                terminate_pid_or_group "$pid" TERM
            fi
        done <<< "$fallback_pids"
    done
    sleep 1
    for token in dabai_dcw2.launch.py '__node:=camera_container' \
            orbbec_camera_node msgToimg yolov11.py; do
        fallback_pids=$(find_processes_by_token "$token")
        while read -r pid; do
            [ -n "$pid" ] && terminate_pid_or_group "$pid" KILL
        done <<< "$fallback_pids"
    done
else
    echo "[VIDEO] Full sortation is running; skipped unrecorded-process fallback"
fi

> "$PID_FILE"

if [ -z "$(find_processes_by_token yolov11_sortation)" ]; then
    remaining=""
    for token in dabai_dcw2.launch.py '__node:=camera_container' \
            orbbec_camera_node msgToimg yolov11.py; do
        pids=$(find_processes_by_token "$token")
        [ -n "$pids" ] && remaining="$remaining $token:$pids"
    done
    if [ -n "$remaining" ]; then
        echo "[VIDEO][ERROR] Video process cleanup is incomplete:$remaining"
        exit 1
    fi
    if ss -ltn 2>/dev/null | grep -q ':8765 '; then
        echo "[VIDEO][ERROR] Port 8765 is still occupied after cleanup"
        exit 1
    fi
fi

echo "[VIDEO] Video-only service stopped"
