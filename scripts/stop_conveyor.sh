#!/bin/bash
# Send one conveyor STOP pulse only. No running ROS 2 or arm process is changed.

set -euo pipefail

python3 - <<'PY'
import time
import Jetson.GPIO as GPIO

BCM_STOP = 6
PULSE_SECONDS = 0.05

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

try:
    GPIO.setup(BCM_STOP, GPIO.OUT, initial=GPIO.LOW)
    GPIO.output(BCM_STOP, GPIO.HIGH)
    time.sleep(PULSE_SECONDS)
    GPIO.output(BCM_STOP, GPIO.LOW)
finally:
    try:
        GPIO.output(BCM_STOP, GPIO.LOW)
    finally:
        GPIO.cleanup(BCM_STOP)

print("[传送带] BCM6已输出50 ms停止脉冲")
print("[传送带] 未启动或停止机械臂、ROS 2、相机及分拣程序")
PY
