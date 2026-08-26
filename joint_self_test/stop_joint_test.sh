#!/bin/bash

set -u

PID_FILE="/tmp/dofbot_joint_self_test.pid"
LOG_FILE="/tmp/dofbot_joint_self_test.log"
WAIT_SECONDS=12

if [ ! -s "$PID_FILE" ]; then
    echo "[提示] 关节自检未运行"
    exit 0
fi

pid="$(cat "$PID_FILE" 2>/dev/null)"
if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    echo "[失败] PID文件内容无效: $PID_FILE"
    exit 1
fi

if ! kill -0 "$pid" 2>/dev/null; then
    echo "[提示] 自检进程已经退出"
    rm -f "$PID_FILE"
    exit 0
fi

command_line="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
if [[ "$command_line" != *"joint_self_test.py"* ]]; then
    echo "[拒绝停止] PID $pid 不属于关节自检程序"
    echo "[进程] $command_line"
    exit 2
fi

echo "[停止] 正在通知自检程序安全停止并竖直归位，PID: $pid"
kill -TERM "$pid"

for ((second = 1; second <= WAIT_SECONDS; second++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "[完成] 自检已停止，机械臂已执行竖直归位"
        tail -n 12 "$LOG_FILE" 2>/dev/null || true
        exit 0
    fi
    sleep 1
done

echo "[警告] 等待 ${WAIT_SECONDS} 秒后进程仍未退出"
echo "为保证机械臂能够归位，脚本不会强制终止进程。"
echo "请检查日志: $LOG_FILE"
exit 1
