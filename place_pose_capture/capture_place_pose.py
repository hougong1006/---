#!/usr/bin/env python3
"""Safely capture a manually taught Dofbot placement pose."""

import fcntl
import json
import os
import statistics
import sys
import time
from pathlib import Path

from Arm_Lib import Arm_Device


LOCK_FILE = Path("/tmp/dofbot_place_pose_capture.lock")
RESULT_FILE = Path("/tmp/dofbot_place_pose.json")
SAMPLE_COUNT = 5
MAX_SAMPLE_SPREAD_DEG = 4
PING_OK = 0xDA

CONFLICT_PATTERNS = (
    "dofbot_pro_driver arm_driver",
    "arm_driver_node",
    "yolov11_sortation",
    "/yolov11.py",
    "joint_self_test.py",
)


def log(message):
    print(message, flush=True)


def find_conflicting_processes():
    conflicts = []
    current_pid = os.getpid()
    for proc_dir in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(proc_dir.name)
            if pid == current_pid:
                continue
            command = (proc_dir / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except (OSError, ValueError):
            continue
        if any(pattern in command for pattern in CONFLICT_PATTERNS):
            conflicts.append((pid, command.strip()))
    return conflicts


def acquire_lock():
    handle = LOCK_FILE.open("w", encoding="ascii")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("投放位置采集工具已经在运行") from exc
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle


def check_servo_communication(arm):
    for joint_id in range(1, 7):
        response = arm.Arm_ping_servo(joint_id)
        if response != PING_OK:
            raise RuntimeError(
                f"{joint_id}号舵机通信异常: 返回={response!r}，期望=0xDA"
            )
    log("[通过] 1至6号舵机通信正常")


def read_joint(arm, joint_id):
    value = arm.Arm_serial_servo_read(joint_id)
    if value is None:
        raise RuntimeError(f"{joint_id}号关节角度读取失败")
    return float(value)


def capture_stable_pose(arm):
    samples = [[] for _ in range(6)]
    for sample_index in range(SAMPLE_COUNT):
        for joint_id in range(1, 7):
            samples[joint_id - 1].append(read_joint(arm, joint_id))
            time.sleep(0.04)
        log(f"[采样] 已完成 {sample_index + 1}/{SAMPLE_COUNT}")

    unstable = []
    for joint_id, values in enumerate(samples, start=1):
        spread = max(values) - min(values)
        if spread > MAX_SAMPLE_SPREAD_DEG:
            unstable.append(f"关节{joint_id}波动{spread:.1f}°")
    if unstable:
        raise RuntimeError("姿态不稳定，请扶稳后重试: " + "，".join(unstable))

    return [int(round(statistics.median(values))) for values in samples]


def run():
    conflicts = find_conflicting_processes()
    if conflicts:
        log("[拒绝启动] 以下程序正在占用机械臂:")
        for pid, command in conflicts:
            log(f"  PID {pid}: {command}")
        log("请先执行 bash ~/stop_sorting.sh，确认机械臂完全停止后重试。")
        return 2

    lock_handle = acquire_lock()
    arm = None
    torque_released = False
    try:
        arm = Arm_Device()
        check_servo_communication(arm)

        log("\n[安全提示] 请先托住机械臂，防止关闭扭矩后突然下落。")
        input("托稳后按 Enter 关闭舵机扭矩...")
        arm.Arm_serial_set_torque(0)
        torque_released = True
        time.sleep(0.2)

        log("\n请用手缓慢移动机械臂到新的缺陷件投放位置。")
        log("重点调整关节1至5；程序投放时会把关节6保持为夹紧角165°。")
        input("到达目标位置并扶稳后按 Enter 开始读取...")

        pose = capture_stable_pose(arm)
        result = {
            "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "joints": pose,
            "sort_item_value": pose[:5] + [29],
            "note": "Joint 6 is replaced by GRIPPER_CLOSED_ANGLE during placement.",
        }
        RESULT_FILE.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        log("\n[读取完成] 六关节角度: " + str(pose))
        log("[待写入代码] quexianketi joint: " + str(result["sort_item_value"]))
        log(f"[结果文件] {RESULT_FILE}")

        log("\n请继续托住机械臂，并缓慢将机械臂摆回安全的竖直初始姿态。")
        input("摆回竖直并扶稳后按 Enter 恢复舵机扭矩...")
        arm.Arm_serial_set_torque(1)
        torque_released = False
        log("[完成] 舵机扭矩已恢复，采集工具退出。")
        return 0
    finally:
        if arm is not None and torque_released:
            try:
                arm.Arm_serial_set_torque(1)
                log("[保护] 退出前已恢复舵机扭矩。")
            except Exception as exc:
                log(f"[严重警告] 恢复舵机扭矩失败: {exc}")
        if arm is not None:
            del arm
        lock_handle.close()


def main():
    try:
        return run()
    except KeyboardInterrupt:
        log("\n[取消] 用户终止采集。")
        return 130
    except Exception as exc:
        log(f"[失败] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
