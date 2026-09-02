#!/bin/bash
# ============================================================
# GPIO 引脚复用配置脚本 (需要 sudo 权限)
# 功能：配置传送带控制和独立报警灯状态输出使用的4路GPIO
# 用途：BCM6/BCM13控制传送带，BCM5/BCM12输出报警灯状态
#
# 使用方法：sudo bash setup_gpio.sh
# 注意：每次重启设备后需要重新执行此脚本
# ============================================================

echo "=========================================="
echo "  Jetson Orin Nano GPIO 引脚复用配置"
echo "=========================================="

# 1. 安装 busybox（如果未安装）
if ! command -v busybox &> /dev/null; then
    echo "[1/5] 正在安装 busybox..."
    apt install -y busybox
else
    echo "[1/5] busybox 已安装，跳过"
fi

# 2. 配置 BCM6 (Pin 31) 为 GPIO 模式
#    寄存器地址: 0x02430070
#    写入值: 0x004 (GPIO 功能)
echo "[2/5] 配置 BCM6 (Pin 31) → GPIO 输出模式..."
echo "      寄存器: 0x02430070"
BEFORE_BCM6=$(busybox devmem 0x02430070)
echo "      修改前: $BEFORE_BCM6"
busybox devmem 0x02430070 w 0x004
AFTER_BCM6=$(busybox devmem 0x02430070)
echo "      修改后: $AFTER_BCM6"

# 3. 配置 BCM13 (Pin 33) 为 GPIO 模式
#    寄存器地址: 0x02434040
#    写入值: 0x004 (GPIO 功能)
echo "[3/5] 配置 BCM13 (Pin 33) → GPIO 输出模式..."
echo "      寄存器: 0x02434040"
BEFORE_BCM13=$(busybox devmem 0x02434040)
echo "      修改前: $BEFORE_BCM13"
busybox devmem 0x02434040 w 0x004
AFTER_BCM13=$(busybox devmem 0x02434040)
echo "      修改后: $AFTER_BCM13"

# 4. 配置 BCM5 (Pin 29 / GPIO01) 为报警板运行状态输出
#    地址由当前雅博载板上的 jetson-gpio-pinmux-lookup 实测确认
echo "[4/5] 配置 BCM5 (Pin 29 / GPIO01) → GPIO 输出模式..."
echo "      寄存器: 0x02430068"
BEFORE_BCM5=$(busybox devmem 0x02430068)
echo "      修改前: $BEFORE_BCM5"
busybox devmem 0x02430068 w 0x004
AFTER_BCM5=$(busybox devmem 0x02430068)
echo "      修改后: $AFTER_BCM5"

# 5. 配置 BCM12 (Pin 32 / GPIO07) 为报警板缺陷状态输出
#    Pin 32原带PWM复用，必须在每次设备重启后恢复为GPIO模式
echo "[5/5] 配置 BCM12 (Pin 32 / GPIO07) → GPIO 输出模式..."
echo "      寄存器: 0x02434080"
BEFORE_BCM12=$(busybox devmem 0x02434080)
echo "      修改前: $BEFORE_BCM12"
busybox devmem 0x02434080 w 0x004
AFTER_BCM12=$(busybox devmem 0x02434080)
echo "      修改后: $AFTER_BCM12"

for value in "$AFTER_BCM6" "$AFTER_BCM13" "$AFTER_BCM5" "$AFTER_BCM12"; do
    if [ "$value" != "0x00000004" ]; then
        echo "[错误] GPIO引脚复用配置校验失败，实际值: $value" >&2
        exit 1
    fi
done

echo ""
echo "=========================================="
echo "  GPIO 配置完成！"
echo "  BCM6  (Pin 31) → 传送带停止信号"
echo "  BCM13 (Pin 33) → 传送带启动信号"
echo "  BCM5  (Pin 29) → 报警板正常运行状态"
echo "  BCM12 (Pin 32) → 报警板缺陷夹取状态"
echo "=========================================="
