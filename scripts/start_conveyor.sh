#!/bin/bash
# Send one conveyor START pulse only. No ROS 2, camera, YOLO, or arm node is started.

set -euo pipefail

python3 - <<'PY'
import time
import Jetson.GPIO as GPIO

BCM_START = 13
PULSE_SECONDS = 0.05

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

try:
    GPIO.setup(BCM_START, GPIO.OUT, initial=GPIO.LOW)
    GPIO.output(BCM_START, GPIO.HIGH)
    time.sleep(PULSE_SECONDS)
    GPIO.output(BCM_START, GPIO.LOW)
finally:
    try:
        GPIO.output(BCM_START, GPIO.LOW)
    finally:
        GPIO.cleanup(BCM_START)

print("[传送带] BCM13已输出50 ms启动脉冲")
print("[传送带] 未启动机械臂、ROS 2、相机或分拣程序")
PY
