#!/bin/bash
# ============================================================
#  Dofbot Pro YOLOv11 3D视觉垃圾分拣 - 一键停止脚本
#  使用方法：bash ~/stop_sorting.sh
# ============================================================

set -u

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Dofbot Pro 3D视觉垃圾分拣 - 停止所有   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

PID_FILE="/tmp/dofbot_sorting_pids.txt"
GPIO_SETUP="$HOME/setup_gpio.sh"
ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$HOME/dofbot_pro_ws/install/setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-98}"
STOP_SENT=0
RUN_TOKEN_FILE="/tmp/dofbot_sorting_run.token"

# A real user/UI stop invalidates any start script that may still be sleeping
# between node launches. Internal pre-start cleanup preserves the new token.
if [ "${DOFBOT_PRESTART_CLEANUP:-0}" != "1" ]; then
    printf '%s\n' "stopped-$$-$(date +%s%N)" > "$RUN_TOKEN_FILE"
fi

configure_gpio() {
    echo "[GPIO] 检查传送带停止引脚复用..."
    if [ ! -f "$GPIO_SETUP" ]; then
        echo "  [警告] 未找到 $GPIO_SETUP"
        return 1
    fi

    if [ "$(id -u)" -eq 0 ]; then
        bash "$GPIO_SETUP"
    elif [ -n "${DOFBOT_SUDO_PASSWORD:-}" ]; then
        printf '%s\n' "$DOFBOT_SUDO_PASSWORD" | \
            sudo -S -p '' bash "$GPIO_SETUP"
    elif sudo -n true 2>/dev/null; then
        sudo -n bash "$GPIO_SETUP"
    else
        echo "  [警告] 未提供sudo凭据，无法配置GPIO"
        return 1
    fi
}

send_direct_stop() {
    echo "[传送带] 通过独立GPIO进程发送BCM6停止脉冲..."
    python3 - <<'PY'
import time
import Jetson.GPIO as GPIO

BCM_STOP = 6
configured = False
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
try:
    GPIO.setup(BCM_STOP, GPIO.OUT, initial=GPIO.LOW)
    configured = True
    GPIO.output(BCM_STOP, GPIO.HIGH)
    time.sleep(0.05)
    GPIO.output(BCM_STOP, GPIO.LOW)
finally:
    if configured:
        try:
            GPIO.output(BCM_STOP, GPIO.LOW)
        finally:
            GPIO.cleanup(BCM_STOP)
PY
}

request_owner_stop() {
    local service_output
    echo "[传送带] 请求GPIO占用节点发送停止脉冲..."
    if service_output=$(timeout 8 bash -c \
            "source '$ROS_SETUP' && source '$WS_SETUP' && ros2 service call /stop_conveyor std_srvs/srv/Trigger '{}'" 2>&1); then
        echo "$service_output" | sed 's/^/  /'
        if echo "$service_output" | \
                grep -Eq 'success[=:][[:space:]]*True|success:[[:space:]]*true'; then
            echo "  [传送带] 分拣节点已确认停止信号"
            return 0
        fi
    else
        echo "$service_output" | sed 's/^/  /'
    fi
    echo "  [警告] 分拣节点停止服务不可用"
    return 1
}

# Match a complete executable/script token. A log path containing a node name
# is not a match, which prevents tail/grep processes from being terminated.
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

find_runtime_pids() {
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
        arm_driver) printf '%s\n' "arm_driver" ;;
        kinemarics) printf '%s\n' "kinemarics_dofbot" ;;
        msgToimg) printf '%s\n' "msgToimg" ;;
        yolov11) printf '%s\n' "yolov11.py" ;;
        yolov11_sortation) printf '%s\n' "yolov11_sortation" ;;
        *) return 1 ;;
    esac
}

terminate_pid_or_group() {
    local pid=$1
    local pgid
    pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')
    if [ "$pgid" = "$pid" ]; then
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    else
        kill -TERM "$pid" 2>/dev/null || true
    fi
}

force_pid_or_group() {
    local pid=$1
    local marker=${2:-}
    if kill -0 -- "-$pid" 2>/dev/null; then
        kill -KILL -- "-$pid" 2>/dev/null || true
    elif kill -0 "$pid" 2>/dev/null && \
            { [ -z "$marker" ] || process_has_token "$pid" "$marker"; }; then
        kill -KILL "$pid" 2>/dev/null || true
    fi
}

# When sortation is running it owns BCM6. Ask that process to send the pulse;
# opening BCM6 from a second Jetson.GPIO process would fail with EBUSY.
echo "[0] 发送传送带停止信号 (BCM6, 50 ms)..."
if [ -n "$(find_runtime_pids "yolov11_sortation")" ]; then
    if request_owner_stop; then
        STOP_SENT=1
    else
        echo "  [回退] 将先释放旧分拣节点，再在本次停止流程中补发信号"
    fi
else
    if configure_gpio && send_direct_stop; then
        STOP_SENT=1
        echo "  [传送带] 停止信号已发送"
    fi
fi
echo ""

# 方式1：通过PID文件停止
validated_pids=()
validated_names=()
validated_markers=()
if [ -f "$PID_FILE" ] && [ -s "$PID_FILE" ]; then
    echo "[1] 通过PID记录停止进程..."
    while read -r pid name; do
        if kill -0 "$pid" 2>/dev/null; then
            marker=$(marker_for_name "$name" 2>/dev/null || true)
            if [ -n "$marker" ] && process_has_token "$pid" "$marker"; then
                echo "  停止 $name 进程组 (PID/PGID: $pid)..."
                terminate_pid_or_group "$pid"
                validated_pids+=("$pid")
                validated_names+=("$name")
                validated_markers+=("$marker")
            else
                echo "  跳过 $name (PID: $pid) - PID记录失效或已被复用"
            fi
        else
            echo "  跳过 $name (PID: $pid) - 已退出"
        fi
    done < "$PID_FILE"
    sleep 2
    # 强制杀死残留
    for index in "${!validated_pids[@]}"; do
        pid=${validated_pids[$index]}
        name=${validated_names[$index]}
        marker=${validated_markers[$index]}
        if kill -0 -- "-$pid" 2>/dev/null || \
                { kill -0 "$pid" 2>/dev/null && [ -n "$marker" ] && process_has_token "$pid" "$marker"; }; then
            echo "  强制停止 $name 残留进程组 (PID/PGID: $pid)..."
            force_pid_or_group "$pid" "$marker"
        fi
    done
    > "$PID_FILE"
fi

# 方式2：通过进程名兜底清理
echo ""
echo "[2] 清理残留ROS2节点进程..."

cleanup_process() {
    local token=$1
    local name=$2
    local pids
    local pid
    pids=$(find_runtime_pids "$token")
    if [ -n "$pids" ]; then
        echo "  停止 $name (PIDs: $pids)..."
        while read -r pid; do
            [ -n "$pid" ] && terminate_pid_or_group "$pid"
        done <<< "$pids"
        sleep 1
        # 强制杀死残留
        pids=$(find_runtime_pids "$token")
        if [ -n "$pids" ]; then
            while read -r pid; do
                [ -n "$pid" ] && force_pid_or_group "$pid" "$token"
            done <<< "$pids"
        fi
    else
        echo "  $name - 未运行"
    fi
}

cleanup_process "dabai_dcw2.launch.py" "相机节点"
cleanup_process "__node:=camera_container" "相机组件容器"
cleanup_process "orbbec_camera_node" "相机独立节点"
cleanup_process "arm_driver" "底层控制"
cleanup_process "kinemarics_dofbot" "逆解程序"
cleanup_process "msgToimg" "图像转换"
cleanup_process "yolov11.py" "YOLOv11识别"
cleanup_process "yolov11_sortation" "机械臂分拣"

# Compatibility fallback for an older sortation node without /stop_conveyor.
# At this point the GPIO owner has exited, so BCM6 can be opened safely.
if [ "$STOP_SENT" -eq 0 ]; then
    echo ""
    echo "[3] GPIO释放后补发传送带停止信号..."
    if configure_gpio && send_direct_stop; then
        STOP_SENT=1
        echo "  [传送带] 补发停止信号成功"
    else
        echo "  [严重警告] 传送带停止信号发送失败，请立即使用硬件急停"
    fi
fi

echo ""
remaining=""
for token in dabai_dcw2.launch.py '__node:=camera_container' orbbec_camera_node \
        arm_driver arm_driver_node \
        kinemarics_dofbot msgToimg yolov11.py yolov11_sortation; do
    pids=$(find_runtime_pids "$token")
    [ -n "$pids" ] && remaining="$remaining $token:$pids"
done

if [ -n "$remaining" ]; then
    echo "╔══════════════════════════════════════════╗"
    echo "║      停止未完成：仍有后台进程残留         ║"
    echo "╚══════════════════════════════════════════╝"
    echo "[残留]$remaining"
    exit 1
fi

if [ "$STOP_SENT" -eq 0 ]; then
    echo "╔══════════════════════════════════════════╗"
    echo "║  软件节点已停止，但传送带停止信号未确认   ║"
    echo "╚══════════════════════════════════════════╝"
    exit 1
fi

echo "╔══════════════════════════════════════════╗"
echo "║          所有节点已停止！                 ║"
echo "╚══════════════════════════════════════════╝"
echo ""
