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

# When sortation is running it owns BCM6. Ask that process to send the pulse;
# opening BCM6 from a second Jetson.GPIO process would fail with EBUSY.
echo "[0] 发送传送带停止信号 (BCM6, 50 ms)..."
if pgrep -f "yolov11_sortation" >/dev/null 2>&1; then
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
if [ -f "$PID_FILE" ] && [ -s "$PID_FILE" ]; then
    echo "[1] 通过PID记录停止进程..."
    while read -r pid name; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "  停止 $name (PID: $pid)..."
            kill "$pid" 2>/dev/null
        else
            echo "  跳过 $name (PID: $pid) - 已退出"
        fi
    done < "$PID_FILE"
    sleep 2
    # 强制杀死残留
    while read -r pid name; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "  强制停止 $name (PID: $pid)..."
            kill -9 "$pid" 2>/dev/null
        fi
    done < "$PID_FILE"
    > "$PID_FILE"
fi

# 方式2：通过进程名兜底清理
echo ""
echo "[2] 清理残留ROS2节点进程..."

cleanup_process() {
    local pattern=$1
    local name=$2
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "  停止 $name (PIDs: $pids)..."
        pkill -f "$pattern" 2>/dev/null
        sleep 1
        # 强制杀死残留
        pids=$(pgrep -f "$pattern" 2>/dev/null)
        if [ -n "$pids" ]; then
            pkill -9 -f "$pattern" 2>/dev/null
        fi
    else
        echo "  $name - 未运行"
    fi
}

cleanup_process "dabai_dcw2.launch.py" "相机节点"
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
echo "╔══════════════════════════════════════════╗"
echo "║          所有节点已停止！                 ║"
echo "╚══════════════════════════════════════════╝"
echo ""
