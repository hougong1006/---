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
    echo "[清理] 移除失效的关节自检PID记录"
    rm -f "$PID_FILE"
fi

conflict_tokens=(
    "arm_driver"
    "arm_driver_node"
    "yolov11_sortation"
    "yolov11.py"
    "msgToimg"
    "dabai_dcw2.launch.py"
    "__node:=camera_container"
    "orbbec_camera_node"
    "kinemarics_dofbot"
)

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

for token in "${conflict_tokens[@]}"; do
    conflict_pids=$(find_processes_by_token "$token")
    if [ -n "$conflict_pids" ]; then
        echo "[拒绝启动] 检测到冲突进程: $token (PIDs: $conflict_pids)"
        echo "请先停止分拣系统: bash ~/stop_sorting.sh"
        exit 2
    fi
done

: > "$LOG_FILE"
echo "[启动] 开始六关节自检；测试和安全归位完成后命令才会结束"
echo "[安全停止] 可在另一个终端执行: bash $SELF_TEST_DIR/stop_joint_test.sh"

set -o pipefail
/usr/bin/python3 "$TEST_PROGRAM" 2>&1 | tee "$LOG_FILE"
test_status=${PIPESTATUS[0]}

if [ "$test_status" -eq 0 ]; then
    echo "[完成] 六关节自检及安全归位全部完成"
else
    echo "[结束] 六关节自检退出，状态码: $test_status"
fi
exit "$test_status"
