#!/bin/bash
# ============================================================
#  Dofbot Pro YOLOv11 3D视觉垃圾分拣 - 一键启动脚本
#  功能：GPIO配置 + 6个ROS2节点按序启动
#  使用方法：bash ~/start_sorting.sh
# ============================================================

set -e
export PYTHONUNBUFFERED=1

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Dofbot Pro 3D视觉垃圾分拣 - 一键启动   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ==================== 环境变量 ====================
# 设置显示环境（SSH远程启动时需要）
export DISPLAY=:0
export XAUTHORITY=/home/jetson/.Xauthority
# 禁用Python stdout缓冲，日志实时输出
export PYTHONUNBUFFERED=1

ROS_SETUP="/opt/ros/humble/setup.bash"
WS_SETUP="$HOME/dofbot_pro_ws/install/setup.bash"
YOLO_SCRIPT="$HOME/dofbot_pro_ws/src/dofbot_pro_yolov11/dofbot_pro_yolov11/yolov11.py"
PID_FILE="/tmp/dofbot_sorting_pids.txt"
LOG_DIR="/tmp/dofbot_logs"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 清空旧的PID文件
> "$PID_FILE"

# ==================== 1. GPIO Pinmux 配置 ====================
echo "[1/7] 配置 GPIO 引脚复用 (BCM6/13传送带 + BCM5/12报警灯)..."
if [ -f "$HOME/setup_gpio.sh" ]; then
    if [ -n "${DOFBOT_SUDO_PASSWORD:-}" ]; then
        printf '%s\n' "$DOFBOT_SUDO_PASSWORD" | \
            sudo -S bash "$HOME/setup_gpio.sh" 2>&1 | \
            grep -E "配置|完成|已安装|修改" || true
        echo "      GPIO 配置完成"
    elif sudo -n true 2>/dev/null; then
        sudo -n bash "$HOME/setup_gpio.sh" 2>&1 | \
            grep -E "配置|完成|已安装|修改" || true
        echo "      GPIO 配置完成"
    else
        echo "      [警告] 未提供sudo凭据，跳过GPIO配置"
        echo "      请设置DOFBOT_SUDO_PASSWORD或配置免密码sudo"
    fi
else
    echo "      [警告] setup_gpio.sh 不存在，跳过GPIO配置"
    echo "      如需GPIO功能，请先运行: sudo bash ~/setup_gpio.sh"
fi
echo ""

# 在启动ROS节点前先向传送带控制板发送启动脉冲。
# 可视化界面的一键启动和命令行启动都调用本脚本，因此统一在这里处理。
echo "[启动联动] 发送传送带启动信号 (BCM13, 50 ms)..."
if python3 - <<'PY'
import time
import Jetson.GPIO as GPIO

BCM_START = 13
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
try:
    GPIO.setup(BCM_START, GPIO.OUT, initial=GPIO.LOW)
    GPIO.output(BCM_START, GPIO.HIGH)
    time.sleep(0.05)
    GPIO.output(BCM_START, GPIO.LOW)
finally:
    GPIO.cleanup(BCM_START)
PY
then
    echo "      [传送带] 启动信号已发送"
else
    echo "      [警告] 传送带启动信号发送失败，请检查GPIO配置和控制板连接"
fi
echo ""

# ==================== 辅助函数 ====================
source_env() {
    source "$ROS_SETUP"
    source "$WS_SETUP"
}

launch_node() {
    local step=$1
    local name=$2
    local cmd=$3
    local delay=$4
    local log_file="$LOG_DIR/${name}.log"

    echo "[${step}/7] 启动 ${name}..."
    echo "      命令: ${cmd}"

    # 在子shell中source环境并执行命令，输出重定向到日志
    bash -c "source $ROS_SETUP && source $WS_SETUP && $cmd" > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid $name" >> "$PID_FILE"
    echo "      PID: $pid | 日志: $log_file"

    # 等待节点初始化
    if [ "$delay" -gt 0 ]; then
        echo "      等待 ${delay}s 初始化..."
        sleep "$delay"
    fi

    # 检查进程是否还活着
    if kill -0 "$pid" 2>/dev/null; then
        echo "      ? ${name} 启动成功"
    else
        echo "      ? ${name} 启动失败！请检查日志: $log_file"
        echo "      最后10行日志:"
        tail -10 "$log_file" 2>/dev/null | sed 's/^/        /'
    fi
    echo ""
}

# ==================== 2-7. 按序启动所有节点 ====================

# source环境（当前shell用于检查）
source_env

# 2. 启动相机
launch_node "2" "camera" \
    "ros2 launch orbbec_camera dabai_dcw2.launch.py" 5

# 3. 启动底层控制（机械臂驱动）
launch_node "3" "arm_driver" \
    "ros2 run dofbot_pro_driver arm_driver" 3

# 4. 启动逆解程序（运动学求解）
launch_node "4" "kinemarics" \
    "ros2 run dofbot_pro_info kinemarics_dofbot" 3

# 5. 启动图像转换程序
launch_node "5" "msgToimg" \
    "ros2 run dofbot_pro_yolov11 msgToimg" 3

# 6. 启动YOLOv11识别程序（需要显示窗口）
echo "[6/7] 启动 YOLOv11 识别程序..."
echo "      命令: python3 $YOLO_SCRIPT"
bash -c "source $ROS_SETUP && source $WS_SETUP && python3 $YOLO_SCRIPT" > "$LOG_DIR/yolov11.log" 2>&1 &
YOLO_PID=$!
echo "$YOLO_PID yolov11" >> "$PID_FILE"
echo "      PID: $YOLO_PID | 日志: $LOG_DIR/yolov11.log"
echo "      等待 5s YOLO模型加载..."
sleep 5
if kill -0 "$YOLO_PID" 2>/dev/null; then
    echo "      ? YOLOv11 启动成功"
else
    echo "      ? YOLOv11 启动失败！请检查日志"
    tail -10 "$LOG_DIR/yolov11.log" 2>/dev/null | sed 's/^/        /'
fi
echo ""

# 7. 启动机械臂分拣程序（GPIO传送带控制）
launch_node "7" "yolov11_sortation" \
    "ros2 run dofbot_pro_yolov11 yolov11_sortation" 3

# ==================== 启动完成 ====================
echo "╔══════════════════════════════════════════╗"
echo "║          所有节点启动完成！               ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  运行中的进程:"
echo "  ─────────────────────────────────────────"
while read -r pid name; do
    if kill -0 "$pid" 2>/dev/null; then
        echo "  ? [$pid] $name"
    else
        echo "  ? [$pid] $name (已退出)"
    fi
done < "$PID_FILE"
echo ""
echo "  日志目录: $LOG_DIR"
echo "  停止所有: bash ~/stop_sorting.sh"
echo ""
echo "  按 Ctrl+C 停止所有节点..."
echo ""

# ==================== 等待退出信号 ====================
cleanup() {
    echo ""
    echo "[关闭] 正在停止所有节点..."
    while read -r pid name; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "  停止 $name (PID: $pid)..."
            kill "$pid" 2>/dev/null
        fi
    done < "$PID_FILE"
    sleep 2
    # 强制杀死残留进程
    while read -r pid name; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "  强制停止 $name (PID: $pid)..."
            kill -9 "$pid" 2>/dev/null
        fi
    done < "$PID_FILE"
    echo "[关闭] 所有节点已停止"
    > "$PID_FILE"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持脚本运行，等待用户Ctrl+C
wait
