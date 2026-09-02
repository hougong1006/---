#!/bin/bash

set -u

PID_FILE="/tmp/dofbot_joint_self_test.pid"
LOG_FILE="/tmp/dofbot_joint_self_test.log"
WAIT_SECONDS=12

process_is_joint_test() {
    local proc_pid=$1
    local arg base
    [ -r "/proc/$proc_pid/cmdline" ] || return 1
    while IFS= read -r -d '' arg; do
        base=${arg##*/}
        [ "$base" = "joint_self_test.py" ] && return 0
    done < "/proc/$proc_pid/cmdline" 2>/dev/null
    return 1
}

find_joint_test_pids() {
    local proc proc_pid
    for proc in /proc/[0-9]*; do
        proc_pid=${proc##*/}
        [ "$proc_pid" = "$$" ] && continue
        if process_is_joint_test "$proc_pid"; then
            printf '%s\n' "$proc_pid"
        fi
    done
}

pid=""
if [ -s "$PID_FILE" ]; then
    recorded_pid="$(cat "$PID_FILE" 2>/dev/null)"
    if [[ "$recorded_pid" =~ ^[0-9]+$ ]] && kill -0 "$recorded_pid" 2>/dev/null; then
        if process_is_joint_test "$recorded_pid"; then
            pid="$recorded_pid"
        else
            echo "[清理] PID记录已被其他进程复用，不会终止该进程"
        fi
    fi
fi

if [ -z "$pid" ]; then
    fallback_pids=$(find_joint_test_pids)
    if [ -z "$fallback_pids" ]; then
        echo "[提示] 关节自检未运行"
        rm -f "$PID_FILE"
        exit 0
    fi
    pid=$(printf '%s\n' "$fallback_pids" | head -n 1)
    echo "[恢复] PID记录缺失，已找到关节自检进程: $pid"
fi

if ! kill -0 "$pid" 2>/dev/null; then
    echo "[提示] 自检进程已经退出"
    rm -f "$PID_FILE"
    exit 0
fi

command_line="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
if ! process_is_joint_test "$pid"; then
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
