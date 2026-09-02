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

# The monitor runs this script through SSH. Configure pinmux before producing
# the safety stop pulse; sudo reads its password from the existing SSH PTY.
echo "[GPIO] 检查传送带停止引脚复用..."
if [ ! -f "$GPIO_SETUP" ]; then
    echo "  [警告] 未找到 $GPIO_SETUP，将直接尝试发送停止脉冲"
elif [ "$(id -u)" -eq 0 ]; then
    if bash "$GPIO_SETUP"; then
        echo "  [GPIO] 引脚复用配置完成"
    else
        echo "  [警告] GPIO配置失败，将继续尝试发送停止脉冲"
    fi
elif [ -n "${DOFBOT_SUDO_PASSWORD:-}" ]; then
    if printf '%s\n' "$DOFBOT_SUDO_PASSWORD" | \
            sudo -S -p '' bash "$GPIO_SETUP"; then
        echo "  [GPIO] 引脚复用配置完成"
    else
        echo "  [警告] GPIO配置失败，将继续尝试发送停止脉冲"
    fi
elif sudo -n true 2>/dev/null; then
    if sudo -n bash "$GPIO_SETUP"; then
        echo "  [GPIO] 引脚复用配置完成"
    else
        echo "  [警告] GPIO配置失败，将继续尝试发送停止脉冲"
    fi
else
    echo "  [警告] 未提供sudo凭据，将直接尝试发送停止脉冲"
fi
echo ""

# 在终止ROS节点前先向传送带控制板发送停止脉冲。
# 可视化界面的停止按钮和命令行停止都调用本脚本，因此统一在这里处理。
echo "[0] 发送传送带停止信号 (BCM6, 50 ms)..."
if python3 - <<'PY'
import time
import Jetson.GPIO as GPIO

BCM_STOP = 6
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
try:
    GPIO.setup(BCM_STOP, GPIO.OUT, initial=GPIO.LOW)
    GPIO.output(BCM_STOP, GPIO.HIGH)
    time.sleep(0.05)
    GPIO.output(BCM_STOP, GPIO.LOW)
finally:
    GPIO.cleanup(BCM_STOP)
PY
then
    echo "  [传送带] 停止信号已发送"
else
    echo "  [警告] 传送带停止信号发送失败，请立即使用硬件急停"
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

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║          所有节点已停止！                 ║"
echo "╚══════════════════════════════════════════╝"
echo ""
