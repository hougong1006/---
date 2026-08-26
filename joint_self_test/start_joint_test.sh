#!/bin/bash

set -u

SELF_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_PROGRAM="$SELF_TEST_DIR/joint_self_test.py"
PID_FILE="/tmp/dofbot_joint_self_test.pid"
LOG_FILE="/tmp/dofbot_joint_self_test.log"

echo "=========================================="
echo " Dofbot Pro 六关节通信与运动自检"
echo "=========================================="

if [ ! -f "$TEST_PROGRAM" ]; then
    echo "[失败] 找不到自检程序: $TEST_PROGRAM"
    exit 1
fi

if [ -s "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null)"
    if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
        old_cmd="$(tr '\0' ' ' < "/proc/$old_pid/cmdline" 2>/dev/null)"
        if [[ "$old_cmd" == *"joint_self_test.py"* ]]; then
            echo "[提示] 关节自检已经在运行，PID: $old_pid"
            echo "[日志] $LOG_FILE"
            exit 0
        fi
    fi
fi

conflict_patterns=(
    "dofbot_pro_driver arm_driver"
    "arm_driver_node"
    "yolov11_sortation"
    "/yolov11.py"
    "msgToimg"
    "dabai_dcw2.launch.py"
    "kinemarics_dofbot"
)

for pattern in "${conflict_patterns[@]}"; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
        echo "[拒绝启动] 检测到冲突进程: $pattern"
        pgrep -af "$pattern" || true
        echo "请先停止分拣系统: bash ~/stop_sorting.sh"
        exit 2
    fi
done

: > "$LOG_FILE"
nohup /usr/bin/python3 "$TEST_PROGRAM" >> "$LOG_FILE" 2>&1 &
launch_pid=$!

for _ in {1..20}; do
    if [ -s "$PID_FILE" ]; then
        running_pid="$(cat "$PID_FILE" 2>/dev/null)"
        if [[ "$running_pid" =~ ^[0-9]+$ ]] && kill -0 "$running_pid" 2>/dev/null; then
            echo "[启动成功] PID: $running_pid"
            echo "[实时日志] tail -f $LOG_FILE"
            echo "[安全停止] bash $SELF_TEST_DIR/stop_joint_test.sh"
            exit 0
        fi
    fi
    if ! kill -0 "$launch_pid" 2>/dev/null; then
        echo "[启动失败] 自检程序已退出，日志如下:"
        tail -n 30 "$LOG_FILE"
        exit 1
    fi
    sleep 0.1
done

echo "[启动失败] 等待自检进程创建PID文件超时"
tail -n 30 "$LOG_FILE"
exit 1
