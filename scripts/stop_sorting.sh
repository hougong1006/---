#!/bin/bash
# ============================================================
#  Dofbot Pro YOLOv11 3D视觉垃圾分拣 - 一键停止脚本
#  使用方法：bash ~/stop_sorting.sh
# ============================================================

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Dofbot Pro 3D视觉垃圾分拣 - 停止所有   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

PID_FILE="/tmp/dofbot_sorting_pids.txt"

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
