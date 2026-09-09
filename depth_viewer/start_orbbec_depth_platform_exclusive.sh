#!/usr/bin/env bash
# Own one temporary Orbbec camera session for the Windows depth platform.
# It refuses to start if another Orbbec workflow is active. Cleanup targets
# only this script's recorded driver process group and monitor process.
set -euo pipefail

readonly DEPTH_TOPIC="/camera/depth/image_raw"
readonly COLOR_TOPIC="/camera/color/image_raw"
readonly VIEWER="$HOME/depth_viewer/depth_web_viewer.py"
readonly LOG_DIR="$HOME/.ros/log"
readonly DRIVER_LOG="$LOG_DIR/orbbec_depth_exclusive_driver.log"
readonly WEB_LOG="$LOG_DIR/orbbec_depth_exclusive_web.log"
readonly STANDBY_SCRIPT="$HOME/chushi"
readonly STANDBY_LOG="$LOG_DIR/orbbec_depth_exclusive_standby.log"
readonly READY_FILE="$LOG_DIR/orbbec_depth_exclusive.ready"
readonly PID_FILE="$LOG_DIR/orbbec_depth_exclusive.pid"
readonly RUNTIME_COMMON="$HOME/runtime_common.sh"
readonly RUNTIME_ENV="$HOME/.config/dofbot/runtime.env"

port="8766"
near="0.20"
far="3.00"
max_fps="10"
idle_timeout="45"
ros_domain="98"
run_standby_pose="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) port="$2"; shift 2 ;;
        --near) near="$2"; shift 2 ;;
        --far) far="$2"; shift 2 ;;
        --max-fps) max_fps="$2"; shift 2 ;;
        --idle-timeout) idle_timeout="$2"; shift 2 ;;
        --ros-domain) ros_domain="$2"; shift 2 ;;
        --move-arm-to-standby) run_standby_pose="1"; shift ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$LOG_DIR"
if [[ ! -f "$VIEWER" ]]; then
    echo "Depth monitor service not found: $VIEWER" >&2
    exit 1
fi
if [[ "$run_standby_pose" == "1" && ! -r "$STANDBY_SCRIPT" ]]; then
    echo "Mechanical-arm standby script not found or unreadable: $STANDBY_SCRIPT" >&2
    exit 1
fi
if [[ ! -r "$RUNTIME_COMMON" ]]; then
    echo "Shared runtime cleanup script not found: $RUNTIME_COMMON" >&2
    exit 1
fi

# The Windows launcher is non-interactive. Load optional device-local sudo
# credentials without storing them in the repository or command line.
if [[ -r "$RUNTIME_ENV" ]]; then
    set +u
    source "$RUNTIME_ENV"
    set -u
fi
source "$RUNTIME_COMMON"
runtime_transition_begin "启动独占深度平台"
trap runtime_transition_end EXIT
runtime_stop_and_cleanup "独占深度平台启动前"

# The shared cleanup above changes from the previous competition mode first.
# These checks catch an unrecognized external camera process without killing it.
if pgrep -f '[r]os2 launch orbbec_camera dabai_dcw2.launch.py' > /dev/null || \
   pgrep -f '[c]omponent_container.*__node:=camera_container' > /dev/null; then
    echo "An Orbbec camera workflow is already running. It was not changed." >&2
    echo "Stop that workflow first, then run the exclusive depth platform again." >&2
    exit 2
fi
if pgrep -f '[d]epth_web_viewer.py' > /dev/null; then
    echo "A depth monitor service is already running. It was not changed." >&2
    echo "Stop that monitor first, then run the exclusive depth platform again." >&2
    exit 2
fi

# ROS/colcon generated setup scripts are not compatible with `set -u`.
# Keep strict checks for this launcher, but disable nounset while importing ROS.
set +u
source /opt/ros/humble/setup.bash
if [[ -f "$HOME/dofbot_pro_ws/install/setup.bash" ]]; then
    source "$HOME/dofbot_pro_ws/install/setup.bash"
fi
set -u
export ROS_DOMAIN_ID="$ros_domain"

has_depth_publisher() {
    local topic_info
    topic_info="$(ros2 topic info "$DEPTH_TOPIC" 2>/dev/null || true)"
    [[ "$topic_info" =~ Publisher\ count:\ [1-9][0-9]* ]]
}

move_arm_to_standby() {
    if [[ "$run_standby_pose" != "1" ]]; then
        return 0
    fi

    echo "Moving the mechanical arm to its detection standby pose..."
    local status
    if (cd "$HOME" && /usr/bin/python3 "$STANDBY_SCRIPT") >"$STANDBY_LOG" 2>&1; then
        echo "Mechanical-arm standby pose completed."
        return 0
    else
        status=$?
    fi

    echo "Mechanical-arm standby pose failed (exit code $status); camera was not started." >&2
    tail -n 160 "$STANDBY_LOG" >&2 || true
    return "$status"
}

driver_pid=""
web_pid=""
cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM
    rm -f "$READY_FILE" "$PID_FILE"
    if [[ -n "$web_pid" ]] && kill -0 "$web_pid" 2>/dev/null; then
        kill -TERM "$web_pid" 2>/dev/null || true
    fi
    if [[ -n "$driver_pid" ]] && kill -0 "$driver_pid" 2>/dev/null; then
        echo "Stopping this exclusive Orbbec driver (process group $driver_pid)."
        kill -TERM -- "-$driver_pid" 2>/dev/null || true
        for _ in $(seq 1 30); do
            kill -0 "$driver_pid" 2>/dev/null || break
            sleep 0.1
        done
        if kill -0 "$driver_pid" 2>/dev/null; then
            kill -KILL -- "-$driver_pid" 2>/dev/null || true
        fi
    fi
    runtime_transition_end
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

rm -f "$READY_FILE" "$PID_FILE"
if ! move_arm_to_standby; then
    exit 1
fi

echo "Starting a temporary Orbbec DaBai DCW2 driver for the exclusive depth platform..."
setsid ros2 launch orbbec_camera dabai_dcw2.launch.py >"$DRIVER_LOG" 2>&1 < /dev/null &
driver_pid=$!

for _ in $(seq 1 60); do
    if has_depth_publisher; then
        break
    fi
    if ! kill -0 "$driver_pid" 2>/dev/null; then
        echo "The temporary Orbbec driver exited before publishing depth." >&2
        tail -n 160 "$DRIVER_LOG" >&2 || true
        exit 1
    fi
    sleep 1
done

if ! has_depth_publisher; then
    echo "Timed out waiting for $DEPTH_TOPIC from the temporary Orbbec driver." >&2
    tail -n 160 "$DRIVER_LOG" >&2 || true
    exit 1
fi

export DEPTH_WEB_LOG_FILES="$WEB_LOG:$DRIVER_LOG:$STANDBY_LOG"
python3 "$VIEWER" \
    --topic "$DEPTH_TOPIC" \
    --color-topic "$COLOR_TOPIC" \
    --host "0.0.0.0" \
    --port "$port" \
    --near "$near" \
    --far "$far" \
    --max-fps "$max_fps" \
    --idle-timeout "$idle_timeout" \
    >"$WEB_LOG" 2>&1 < /dev/null &
web_pid=$!

for _ in $(seq 1 80); do
    if ! kill -0 "$web_pid" 2>/dev/null; then
        echo "The exclusive depth monitor service exited during startup." >&2
        tail -n 160 "$WEB_LOG" >&2 || true
        exit 1
    fi
    if python3 - "$port" <<'PY'
import sys
from urllib.error import URLError
from urllib.request import urlopen

try:
    with urlopen(f"http://127.0.0.1:{sys.argv[1]}/status.json", timeout=0.5) as response:
        if response.status != 200:
            raise SystemExit(1)
except (OSError, URLError):
    raise SystemExit(1)
PY
    then
        printf 'driver_pid=%s\nweb_pid=%s\nport=%s\nros_domain=%s\n' \
            "$driver_pid" "$web_pid" "$port" "$ROS_DOMAIN_ID" > "$READY_FILE"
        printf '%s\n' "$driver_pid" > "$PID_FILE"
        echo "READY: Exclusive depth platform is running on port $port."
        break
    fi
    sleep 0.25
done

if [[ ! -f "$READY_FILE" ]]; then
    echo "The exclusive depth monitor service did not become reachable." >&2
    tail -n 160 "$WEB_LOG" >&2 || true
    exit 1
fi

# Startup is complete; allow qidong/tingzhi/ceshi or another platform to take
# the transition lock and stop this depth session when the operator switches.
runtime_transition_end

# Closing the Windows window requests /shutdown. An abnormal Windows exit
# triggers the idle timeout, then this supervisor cleans the temporary driver.
wait "$web_pid"
