#!/bin/bash
# Shared runtime transition and cleanup helpers for every Dofbot entry point.

RUNTIME_LOCK_FILE="/tmp/dofbot_runtime_transition.lock"
RUNTIME_SORTING_PID_FILE="/tmp/dofbot_sorting_pids.txt"
RUNTIME_VIDEO_PID_FILE="/tmp/dofbot_video_only_pids.txt"
RUNTIME_JOINT_PID_FILE="/tmp/dofbot_joint_self_test.pid"
RUNTIME_ROS_SETUP="/opt/ros/humble/setup.bash"
RUNTIME_WS_SETUP="$HOME/dofbot_pro_ws/install/setup.bash"
RUNTIME_GPIO_SETUP="$HOME/setup_gpio.sh"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-98}"

RUNTIME_TOKENS=(
    "start_sorting.sh"
    "start_video_only.sh"
    "start_orbbec_depth_platform_exclusive.sh"
    "depth_web_viewer.py"
    "dabai_dcw2.launch.py"
    "__node:=camera_container"
    "orbbec_camera_node"
    "arm_driver"
    "arm_driver_node"
    "kinemarics_dofbot"
    "msgToimg"
    "yolov11.py"
    "yolov11_sortation"
    "joint_self_test.py"
    "capture_place_pose.py"
)

runtime_transition_begin() {
    local action=${1:-运行模式切换}
    exec 9>"$RUNTIME_LOCK_FILE"
    if ! flock -w 90 9; then
        echo "[运行保护][错误] 另一个启停操作仍在执行，${action}已取消" >&2
        exec 9>&-
        return 1
    fi
    echo "[运行保护] ${action}已取得独占锁"
}

runtime_transition_end() {
    flock -u 9 2>/dev/null || true
    { exec 9>&-; } 2>/dev/null || true
}

runtime_pid_is_protected() {
    local candidate=$1
    local ancestor=$$
    local next

    while [ "$ancestor" -gt 1 ] 2>/dev/null; do
        [ "$candidate" = "$ancestor" ] && return 0
        next=$(awk '/^PPid:/ {print $2}' "/proc/$ancestor/status" 2>/dev/null) || break
        [ -n "$next" ] || break
        ancestor=$next
    done
    return 1
}

runtime_pid_has_token() {
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

runtime_pid_is_target() {
    local pid=$1
    local comm token

    runtime_pid_is_protected "$pid" && return 1
    comm=$(cat "/proc/$pid/comm" 2>/dev/null) || return 1
    case "$comm" in
        tail|less|more|grep|rg|sed|cat) return 1 ;;
    esac
    for token in "${RUNTIME_TOKENS[@]}"; do
        runtime_pid_has_token "$pid" "$token" && return 0
    done
    return 1
}

runtime_find_token_pids() {
    local target=$1
    local proc pid

    for proc in /proc/[0-9]*; do
        pid=${proc##*/}
        runtime_pid_is_protected "$pid" && continue
        runtime_pid_has_token "$pid" "$target" && printf '%s\n' "$pid"
    done
    return 0
}

runtime_collect_target_pids() {
    local proc pid ppid changed
    local -A selected=()

    for proc in /proc/[0-9]*; do
        pid=${proc##*/}
        runtime_pid_is_target "$pid" && selected[$pid]=1
    done

    # Include descendants captured before termination so launch wrappers cannot
    # leave a child process behind after they exit.
    changed=1
    while [ "$changed" -eq 1 ]; do
        changed=0
        for proc in /proc/[0-9]*; do
            pid=${proc##*/}
            [ -n "${selected[$pid]+x}" ] && continue
            runtime_pid_is_protected "$pid" && continue
            ppid=$(awk '/^PPid:/ {print $2}' "$proc/status" 2>/dev/null) || continue
            if [ -n "${selected[$ppid]+x}" ]; then
                selected[$pid]=1
                changed=1
            fi
        done
    done

    if [ "${#selected[@]}" -gt 0 ]; then
        printf '%s\n' "${!selected[@]}" | sort -n
    fi
    return 0
}

runtime_request_owner_stop() {
    local output

    [ -f "$RUNTIME_ROS_SETUP" ] || return 1
    [ -f "$RUNTIME_WS_SETUP" ] || return 1
    echo "[传送带] 请求当前分拣节点发送停止信号..."
    if output=$(timeout 8 bash -c \
            "source '$RUNTIME_ROS_SETUP' && source '$RUNTIME_WS_SETUP' && ros2 service call /stop_conveyor std_srvs/srv/Trigger '{}'" 2>&1); then
        echo "$output" | sed 's/^/  /'
        if echo "$output" | grep -Eqi 'success[=:][[:space:]]*(True|true)'; then
            echo "[传送带] 分拣节点已确认停止"
            return 0
        fi
    else
        echo "$output" | sed 's/^/  /'
    fi
    echo "[传送带][警告] 分拣节点停止服务不可用，将在释放GPIO后补发停止信号"
    return 1
}

runtime_configure_gpio() {
    if [ ! -f "$RUNTIME_GPIO_SETUP" ]; then
        echo "[GPIO][错误] 未找到 $RUNTIME_GPIO_SETUP" >&2
        return 1
    fi

    echo "[GPIO] 正在检查并配置引脚复用..."
    if [ "$(id -u)" -eq 0 ]; then
        bash "$RUNTIME_GPIO_SETUP"
    elif [ -n "${DOFBOT_SUDO_PASSWORD:-}" ]; then
        printf '%s\n' "$DOFBOT_SUDO_PASSWORD" | sudo -S -p '' bash "$RUNTIME_GPIO_SETUP"
    elif sudo -n true 2>/dev/null; then
        sudo -n bash "$RUNTIME_GPIO_SETUP"
    elif [ -t 0 ] && [ -t 1 ]; then
        sudo bash "$RUNTIME_GPIO_SETUP"
    else
        echo "[GPIO][错误] 当前为非交互运行且未提供sudo凭据" >&2
        return 1
    fi
}

runtime_send_gpio_pulse() {
    local channel=$1
    local action=$2

    python3 - "$channel" "$action" <<'PY'
import sys
import time

import Jetson.GPIO as GPIO

channel = int(sys.argv[1])
action = sys.argv[2]
configured = False
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
try:
    GPIO.setup(channel, GPIO.OUT, initial=GPIO.LOW)
    configured = True
    GPIO.output(channel, GPIO.HIGH)
    time.sleep(0.05)
    GPIO.output(channel, GPIO.LOW)
finally:
    if configured:
        try:
            GPIO.output(channel, GPIO.LOW)
        finally:
            GPIO.cleanup(channel)

print(f"[传送带] BCM{channel}已输出50 ms{action}脉冲")
PY
}

runtime_send_stop_pulse() {
    runtime_configure_gpio && runtime_send_gpio_pulse 6 "停止"
}

runtime_send_start_pulse() {
    runtime_configure_gpio && runtime_send_gpio_pulse 13 "启动"
}

runtime_stop_joint_test_safely() {
    local pids
    pids=$(runtime_find_token_pids "joint_self_test.py")
    [ -n "$pids" ] || return 0

    if [ -f "$HOME/joint_self_test/stop_joint_test.sh" ]; then
        echo "[清理] 正在安全停止关节自检并等待直立归位..."
        timeout 15 bash "$HOME/joint_self_test/stop_joint_test.sh" || true
    fi
}

runtime_terminate_all() {
    local targets remaining

    runtime_stop_joint_test_safely
    targets=$(runtime_collect_target_pids)
    if [ -z "$targets" ]; then
        echo "[清理] 未发现残留的机械臂、ROS或视频进程"
    else
        echo "[清理] 正在停止残留进程: $(echo "$targets" | tr '\n' ' ')"
        while read -r pid; do
            [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
        done <<< "$targets"
        sleep 2

        while read -r pid; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                echo "[清理] 强制终止未退出进程 PID $pid"
                kill -KILL "$pid" 2>/dev/null || true
            fi
        done <<< "$targets"
        sleep 1
    fi

    : > "$RUNTIME_SORTING_PID_FILE"
    : > "$RUNTIME_VIDEO_PID_FILE"
    rm -f "$RUNTIME_JOINT_PID_FILE"

    remaining=$(runtime_collect_target_pids)
    if [ -n "$remaining" ]; then
        echo "[清理][错误] 仍有项目进程未退出: $(echo "$remaining" | tr '\n' ' ')" >&2
        return 1
    fi
    echo "[清理] 所有项目节点和后台进程已中止"
}

runtime_stop_and_cleanup() {
    local reason=${1:-模式切换前}
    local stop_sent=0
    local owner_pids

    echo "[运行保护] ${reason}：先停止传送带并清理全部残留"
    owner_pids=$(runtime_find_token_pids "yolov11_sortation")
    if [ -n "$owner_pids" ]; then
        runtime_request_owner_stop && stop_sent=1
    else
        runtime_send_stop_pulse && stop_sent=1
    fi

    runtime_terminate_all || return 1

    if [ "$stop_sent" -eq 0 ]; then
        if runtime_send_stop_pulse; then
            stop_sent=1
            echo "[传送带] GPIO释放后已补发停止信号"
        else
            echo "[传送带][严重警告] 停止信号发送失败，请使用硬件急停" >&2
            return 2
        fi
    fi
    return 0
}
