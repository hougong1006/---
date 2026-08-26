#!/bin/bash
# ============================================================
# GPIO 引脚复用配置脚本 (需要 sudo 权限)
# 功能：将 BCM6(Pin31) 和 BCM13(Pin33) 配置为 GPIO 输出模式
# 用途：控制传送带启停信号输出到 STM32
#
# 使用方法：sudo bash setup_gpio.sh
# 注意：每次重启设备后需要重新执行此脚本
# ============================================================

echo "=========================================="
echo "  Jetson Orin Nano GPIO 引脚复用配置"
echo "=========================================="

# 1. 安装 busybox（如果未安装）
if ! command -v busybox &> /dev/null; then
    echo "[1/3] 正在安装 busybox..."
    apt install -y busybox
else
    echo "[1/3] busybox 已安装，跳过"
fi

# 2. 配置 BCM6 (Pin 31) 为 GPIO 模式
#    寄存器地址: 0x02430070
#    写入值: 0x004 (GPIO 功能)
echo "[2/3] 配置 BCM6 (Pin 31) → GPIO 输出模式..."
echo "      寄存器: 0x02430070"
BEFORE_BCM6=$(busybox devmem 0x02430070)
echo "      修改前: $BEFORE_BCM6"
busybox devmem 0x02430070 w 0x004
AFTER_BCM6=$(busybox devmem 0x02430070)
echo "      修改后: $AFTER_BCM6"

# 3. 配置 BCM13 (Pin 33) 为 GPIO 模式
#    寄存器地址: 0x02434040
#    写入值: 0x004 (GPIO 功能)
echo "[3/3] 配置 BCM13 (Pin 33) → GPIO 输出模式..."
echo "      寄存器: 0x02434040"
BEFORE_BCM13=$(busybox devmem 0x02434040)
echo "      修改前: $BEFORE_BCM13"
busybox devmem 0x02434040 w 0x004
AFTER_BCM13=$(busybox devmem 0x02434040)
echo "      修改后: $AFTER_BCM13"

echo ""
echo "=========================================="
echo "  GPIO 配置完成！"
echo "  BCM6  (Pin 31) → 传送带停止信号"
echo "  BCM13 (Pin 33) → 传送带启动信号"
echo "=========================================="
