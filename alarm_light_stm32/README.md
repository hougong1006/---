# 独立报警灯控制板

该 STM32F103C8T6 模块与传送带控制板相互独立，仅负责报警指示。

## 接线与状态逻辑

| 信号 | STM32引脚 | 功能 |
|---|---|---|
| Jetson GPIO01 | PA0 输入 | 传送带正常运行状态 |
| Jetson GPIO07 | PA1 输入 | 缺陷件夹取状态 |
| 1号继电器 | PB0 输出 | 绿灯 |
| 2号继电器 | PB1 输出 | 红灯 |
| 3号继电器 | PB10 输出 | 蜂鸣器 |

输入均采用下拉，默认低电平。报警状态优先：

- PA1=高：PB1、PB10=高，红灯亮、蜂鸣器响，PB0=低；
- PA1=低且 PA0=高：PB0=高，绿灯亮，PB1、PB10=低；
- PA0=低且 PA1=低：三路继电器全部关闭。

Jetson 端的 `GPIO01` 和 `GPIO07` 是持续状态电平，不能使用传送带启停脚本中的50 ms脉冲逻辑。传送带仍由独立的 BCM6/BCM13 信号控制。

## 工程文件

- `XHD.ioc`：CubeMX 配置；
- `Core/Src/main.c`：状态解析和继电器控制；
- `Core/Src/gpio.c`：PA0/PA1 输入、PB0/PB1/PB10 输出初始化；
- `MDK-ARM/XHD.uvprojx`：Keil 工程。

继电器若为低电平吸合，请在 `main.c` 中交换 `RELAY_ON_LEVEL` 与 `RELAY_OFF_LEVEL`。
