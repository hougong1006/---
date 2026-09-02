#!/bin/bash
# Send one conveyor STOP pulse only. No running ROS 2 or arm process is changed.

set -euo pipefail

GPIO_SETUP="$HOME/setup_gpio.sh"

if [ ! -f "$GPIO_SETUP" ]; then
    echo "[GPIO][错误] 未找到 $GPIO_SETUP" >&2
    echo "[GPIO][错误] 无法确认引脚复用配置，取消停止传送带" >&2
    exit 1
fi

echo "[GPIO] 正在配置BCM6和BCM13引脚复用..."
if [ "$(id -u)" -eq 0 ]; then
    bash "$GPIO_SETUP"
else
    sudo bash "$GPIO_SETUP"
fi
echo "[GPIO] 引脚复用配置完成"

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
