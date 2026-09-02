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
RUN_TOKEN_FILE="/tmp/dofbot_sorting_run.token"
RUN_TOKEN="start-$$-$(date +%s%N)"

printf '%s\n' "$RUN_TOKEN" > "$RUN_TOKEN_FILE"

ensure_start_current() {
    local current_token=""
    [ -f "$RUN_TOKEN_FILE" ] && current_token=$(cat "$RUN_TOKEN_FILE" 2>/dev/null || true)
    if [ "$current_token" != "$RUN_TOKEN" ]; then
        echo "[启动取消] 已收到更新的停止/启动命令，本次旧启动流程不再继续"
        return 1
    fi
}

abort_start() {
    echo ""
    echo "[启动回滚] 启动被取消或节点失败，清理本次已经启动的所有进程..."
    if [ -f "$HOME/stop_sorting.sh" ]; then
        bash "$HOME/stop_sorting.sh" || true
    fi
    exit 1
}

# 创建日志目录
mkdir -p "$LOG_DIR"

# Match an executable/script token exactly. Log paths such as
# yolov11_sortation.log therefore cannot be mistaken for a running node.
find_processes_by_token() {
    local target=$1
    local proc pid arg base matched

    for proc in /proc/[0-9]*; do
        pid=${proc##*/}
        [ "$pid" = "$$" ] && continue
        matched=0
        while IFS= read -r -d '' arg; do
            base=${arg##*/}
            if [ "$arg" = "$target" ] || [ "$base" = "$target" ]; then
                matched=1
                break
            fi
        done < "$proc/cmdline" 2>/dev/null || true
        [ "$matched" -eq 1 ] && printf '%s\n' "$pid"
    done
    return 0
}

SORTING_TOKENS=(
    "dabai_dcw2.launch.py"
    "__node:=camera_container"
    "orbbec_camera_node"
    "arm_driver"
    "arm_driver_node"
    "kinemarics_dofbot"
    "msgToimg"
    "yolov11.py"
    "yolov11_sortation"
)

# Never start an ROS 2 arm driver while the independent joint test is moving.
joint_test_pids=$(find_processes_by_token "joint_self_test.py")
if [ -n "$joint_test_pids" ]; then
    echo "[拒绝启动] 六关节自检仍在运行 (PIDs: $joint_test_pids)"
    echo "请等待命令3测试和归位完成，或安全执行:"
    echo "  bash ~/joint_self_test/stop_joint_test.sh"
    exit 2
fi

# Clean processes left by an interrupted sorting/video-only run before the PID
# file is reset. This makes repeated CLI and GUI start/stop cycles deterministic.
residual_pids=""
for token in "${SORTING_TOKENS[@]}"; do
    found=$(find_processes_by_token "$token")
    [ -n "$found" ] && residual_pids="$residual_pids $found"
done

if [ -n "$residual_pids" ]; then
    echo "[启动前清理] 检测到上一次分拣或视频进程:$residual_pids"
    if [ ! -f "$HOME/stop_sorting.sh" ]; then
        echo "[启动失败] 找不到 $HOME/stop_sorting.sh，无法安全清理残留进程"
        exit 3
    fi
    DOFBOT_PRESTART_CLEANUP=1 bash "$HOME/stop_sorting.sh"
    ensure_start_current || exit 5

    for token in "${SORTING_TOKENS[@]}"; do
        found=$(find_processes_by_token "$token")
        if [ -n "$found" ]; then
            echo "[启动失败] 清理后仍存在 $token 进程 (PIDs: $found)"
            exit 4
        fi
    done
    echo "[启动前清理] 残留进程已清理"
fi

# It is now safe to replace stale PID records.
> "$PID_FILE"
ensure_start_current || exit 5

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
ensure_start_current || exit 5
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
ensure_start_current || abort_start

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

    ensure_start_current || return 2
    echo "[${step}/7] 启动 ${name}..."
    echo "      命令: ${cmd}"

    # 在子shell中source环境并执行命令，输出重定向到日志
    setsid bash -c "source '$ROS_SETUP' && source '$WS_SETUP' && exec $cmd" \
        > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid $name" >> "$PID_FILE"
    echo "      PID: $pid | 日志: $log_file"

    # 等待节点初始化
    if [ "$delay" -gt 0 ]; then
        echo "      等待 ${delay}s 初始化..."
        sleep "$delay"
    fi

    ensure_start_current || return 2

    # 检查进程是否还活着
    if kill -0 "$pid" 2>/dev/null; then
        echo "      ? ${name} 启动成功"
    else
        echo "      ? ${name} 启动失败！请检查日志: $log_file"
        echo "      最后10行日志:"
        tail -10 "$log_file" 2>/dev/null | sed 's/^/        /'
        return 1
    fi
    echo ""
}

# ==================== 2-7. 按序启动所有节点 ====================

# source环境（当前shell用于检查）
source_env || abort_start

# 2. 启动相机
launch_node "2" "camera" \
    "ros2 launch orbbec_camera dabai_dcw2.launch.py" 5 || abort_start

# 3. 启动底层控制（机械臂驱动）
launch_node "3" "arm_driver" \
    "ros2 run dofbot_pro_driver arm_driver" 3 || abort_start

# 4. 启动逆解程序（运动学求解）
launch_node "4" "kinemarics" \
    "ros2 run dofbot_pro_info kinemarics_dofbot" 3 || abort_start

# 5. 启动图像转换程序
launch_node "5" "msgToimg" \
    "ros2 run dofbot_pro_yolov11 msgToimg" 3 || abort_start

# 6. 启动YOLOv11识别程序（需要显示窗口）
echo "[6/7] 启动 YOLOv11 识别程序..."
echo "      命令: python3 $YOLO_SCRIPT"
ensure_start_current || abort_start
setsid bash -c "source '$ROS_SETUP' && source '$WS_SETUP' && exec python3 '$YOLO_SCRIPT'" \
    > "$LOG_DIR/yolov11.log" 2>&1 &
YOLO_PID=$!
echo "$YOLO_PID yolov11" >> "$PID_FILE"
echo "      PID: $YOLO_PID | 日志: $LOG_DIR/yolov11.log"
echo "      等待 5s YOLO模型加载..."
sleep 5
ensure_start_current || abort_start
if kill -0 "$YOLO_PID" 2>/dev/null; then
    echo "      ? YOLOv11 启动成功"
else
    echo "      ? YOLOv11 启动失败！请检查日志"
    tail -10 "$LOG_DIR/yolov11.log" 2>/dev/null | sed 's/^/        /'
    abort_start
fi
echo ""

# 7. 启动机械臂分拣程序（GPIO传送带控制）
launch_node "7" "yolov11_sortation" \
    "ros2 run dofbot_pro_yolov11 yolov11_sortation" 3 || abort_start

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
    trap - SIGINT SIGTERM
    echo ""
    echo "[关闭] 收到终止信号，执行统一安全停止流程..."
    bash "$HOME/stop_sorting.sh" || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持脚本运行，等待用户Ctrl+C
wait
