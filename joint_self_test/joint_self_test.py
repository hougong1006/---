#!/usr/bin/env python3
"""Independent six-joint communication and movement self-test for Dofbot Pro."""

import fcntl
import os
import signal
import sys
import time
import traceback
from pathlib import Path

from Arm_Lib import Arm_Device


HOME_POSE = [90, 90, 90, 0, 90, 30]
TEST_ANGLES = [120, 120, 120, 30, 120, 60]
PING_OK = 0xDA
ANGLE_TOLERANCE = 10
HOME_MOVE_MS = 3000
JOINT_MOVE_MS = 1200
READ_ATTEMPTS = 8
READ_RETRY_DELAY = 0.08
VERIFY_ATTEMPTS = 3
VERIFY_RETRY_DELAY = 0.25
MOVE_ATTEMPTS = 3
MOVE_COMMAND_GAP = 0.20
MOVE_SETTLE_MARGIN = 0.50
MOVE_RETRY_DELAY = 0.30
PID_FILE = Path("/tmp/dofbot_joint_self_test.pid")
LOCK_FILE = Path("/tmp/dofbot_joint_self_test.lock")

CONFLICT_TOKENS = (
    "arm_driver",
    "arm_driver_node",
    "yolov11_sortation",
    "yolov11.py",
    "msgToimg",
    "dabai_dcw2.launch.py",
    "__node:=camera_container",
    "orbbec_camera_node",
    "kinemarics_dofbot",
)

stop_requested = False


class StopRequested(Exception):
    """Raised after a safe stop is requested."""


def log(message):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), message, flush=True)


def handle_stop(signum, _frame):
    global stop_requested
    stop_requested = True
    log(f"[停止] 收到信号 {signum}，当前动作结束后执行竖直归位")


def interruptible_wait(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if stop_requested:
            return False
        time.sleep(min(0.1, deadline - time.monotonic()))
    return True


def find_conflicting_processes():
    conflicts = []
    current_pid = os.getpid()
    for proc_dir in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(proc_dir.name)
            if pid == current_pid:
                continue
            raw_tokens = (proc_dir / "cmdline").read_bytes().split(b"\0")
            tokens = [
                token.decode("utf-8", errors="replace")
                for token in raw_tokens
                if token
            ]
        except (OSError, ValueError):
            continue
        token_names = {Path(token).name for token in tokens}
        if any(token in token_names or token in tokens for token in CONFLICT_TOKENS):
            conflicts.append((pid, " ".join(tokens)))
    return conflicts


def acquire_instance_lock():
    lock_handle = LOCK_FILE.open("w", encoding="ascii")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        raise RuntimeError("关节自检已经在运行")
    lock_handle.write(str(os.getpid()))
    lock_handle.flush()
    return lock_handle


def write_pid_file():
    PID_FILE.write_text(f"{os.getpid()}\n", encoding="ascii")


def remove_pid_file():
    try:
        if PID_FILE.read_text(encoding="ascii").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        log(f"[警告] 无法清理PID文件: {exc}")


def raw_to_angle(joint_id, raw_value):
    """Convert the controller's raw feedback without Arm_Lib's 0-180 clamp."""
    if joint_id == 5:
        return 270.0 * (raw_value - 380) / (3700 - 380)

    angle = 180.0 * (raw_value - 900) / (3100 - 900)
    if joint_id in (2, 3, 4):
        angle = 180.0 - angle
    return angle


def read_angle(arm, joint_id):
    last_error = None
    for attempt in range(1, READ_ATTEMPTS + 1):
        try:
            arm.bus.write_byte_data(arm.addr, joint_id + 0x30, 0x00)
            time.sleep(0.005)
            raw_value = arm.bus.read_word_data(arm.addr, joint_id + 0x30)
            if raw_value != 0:
                raw_value = (
                    ((raw_value >> 8) & 0xFF)
                    | ((raw_value << 8) & 0xFF00)
                )
                return raw_to_angle(joint_id, raw_value)
            last_error = "控制器返回0"
        except Exception as exc:
            last_error = str(exc)
        if attempt < READ_ATTEMPTS:
            time.sleep(READ_RETRY_DELAY)
    raise RuntimeError(
        f"{joint_id}号关节角度读取失败（已重试{READ_ATTEMPTS}次，{last_error}）"
    )


def verify_angle(arm, joint_id, expected):
    actual = None
    difference = None
    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        actual = read_angle(arm, joint_id)
        difference = abs(actual - expected)
        if difference <= ANGLE_TOLERANCE:
            if attempt > 1:
                log(f"[复核] {joint_id}号关节第{attempt}次读回后到位")
            log(
                f"[通过] {joint_id}号关节目标={expected}°，"
                f"读回={actual:.1f}°，偏差={difference:.1f}°"
            )
            return
        if attempt < VERIFY_ATTEMPTS:
            time.sleep(VERIFY_RETRY_DELAY)
    raise RuntimeError(
        f"{joint_id}号关节角度校验失败: 目标={expected}°，"
        f"读回={actual:.1f}°，偏差={difference:.1f}°，"
        f"已复核{VERIFY_ATTEMPTS}次"
    )


def move_joint_and_verify(arm, joint_id, target, duration_ms):
    """Send a joint command again when the controller drops a write."""
    last_error = None
    for attempt in range(1, MOVE_ATTEMPTS + 1):
        if stop_requested:
            raise StopRequested("已取消剩余关节测试")

        # Give the controller time to leave feedback-read mode before writing.
        time.sleep(MOVE_COMMAND_GAP)
        if attempt > 1:
            log(
                f"[补发] {joint_id}号关节目标={target}°，"
                f"第{attempt}/{MOVE_ATTEMPTS}次发送"
            )
        arm.Arm_serial_servo_write(joint_id, target, duration_ms)
        if not interruptible_wait(duration_ms / 1000.0 + MOVE_SETTLE_MARGIN):
            raise StopRequested("当前关节动作已中断")

        try:
            verify_angle(arm, joint_id, target)
            return
        except RuntimeError as exc:
            last_error = exc
            if attempt < MOVE_ATTEMPTS:
                log(f"[重试] {exc}；准备补发动作指令")
                if not interruptible_wait(MOVE_RETRY_DELAY):
                    raise StopRequested("当前关节重试已中断")

    raise RuntimeError(
        f"{joint_id}号关节连续{MOVE_ATTEMPTS}次动作未到位: {last_error}"
    )


def move_home(arm, reason):
    log(f"[归位] {reason}，移动到竖直姿态 {HOME_POSE}")
    arm.Arm_serial_servo_write6(*HOME_POSE, HOME_MOVE_MS)
    # 归位期间不响应停止标志，确保舵机有足够时间完成动作。
    time.sleep(HOME_MOVE_MS / 1000.0 + 0.3)
    log("[归位] 竖直姿态指令执行完成")


def run_self_test():
    conflicts = find_conflicting_processes()
    if conflicts:
        log("[拒绝启动] 检测到正在占用机械臂或相机的分拣进程:")
        for pid, command in conflicts:
            log(f"  PID {pid}: {command}")
        log("请先执行 bash ~/stop_sorting.sh，再启动关节自检")
        return 3

    lock_handle = acquire_instance_lock()
    write_pid_file()
    arm = None
    test_completed = False
    result = 1
    failure = None
    try:
        log("[初始化] 创建机械臂I2C控制对象")
        arm = Arm_Device()

        log("[通信] 开始检查1至6号舵机")
        for joint_id in range(1, 7):
            response = arm.Arm_ping_servo(joint_id)
            if response != PING_OK:
                raise RuntimeError(
                    f"{joint_id}号舵机通信失败: 返回={response!r}，期望=0xDA"
                )
            log(f"[通过] {joint_id}号舵机通信正常，响应=0x{response:02X}")

        initial_angles = [read_angle(arm, joint_id) for joint_id in range(1, 7)]
        log("[状态] 初始读回角度: " + ", ".join(f"{v:.1f}°" for v in initial_angles))

        move_home(arm, "自检开始")

        for index, (home_angle, test_angle) in enumerate(
            zip(HOME_POSE, TEST_ANGLES), start=1
        ):
            if stop_requested:
                raise StopRequested("已取消剩余关节测试")

            log(f"[测试 {index}/6] {index}号关节: {home_angle}° -> {test_angle}°")
            move_joint_and_verify(arm, index, test_angle, JOINT_MOVE_MS)

            log(f"[测试 {index}/6] {index}号关节返回 {home_angle}°")
            move_joint_and_verify(arm, index, home_angle, JOINT_MOVE_MS)

        test_completed = True
        log("[结果] 6个关节通信、运动及角度读回检查全部通过")
        result = 0
    except StopRequested as exc:
        log(f"[停止] {exc}")
        result = 130
    except Exception as exc:
        failure = exc
    finally:
        if arm is not None:
            try:
                reason = "自检正常结束" if test_completed else "自检停止或异常退出"
                move_home(arm, reason)
            except Exception as exc:
                log(f"[严重警告] 自动归位失败: {exc}")
                if failure is None:
                    failure = RuntimeError(f"自动归位失败: {exc}")
            del arm
        remove_pid_file()
        lock_handle.close()
        log("[停止] 自检进程已退出")

    if failure is not None:
        raise failure
    return result


def main():
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    try:
        return run_self_test()
    except Exception as exc:
        log(f"[失败] {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
