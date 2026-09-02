# 设备脚本

- `start_sorting.sh`：完成GPIO配置后先由BCM13输出50 ms启动脉冲，再按顺序启动相机、机械臂驱动、KDL运动学、图像转换、YOLO检测和分拣节点。
- `stop_sorting.sh`：先配置GPIO引脚复用，再向BCM6输出50 ms停止脉冲，最后停止分拣相关进程并清理运行状态。可视化停止按钮和命令行停止共用该脚本。
- `1`：独立启动传送带。先调用`setup_gpio.sh`配置引脚复用，再由BCM13输出一次50 ms启动脉冲；不启动ROS 2、相机、YOLO、机械臂或分拣程序。
- `2`：独立停止传送带。先调用`setup_gpio.sh`配置引脚复用，再由BCM6输出一次50 ms停止脉冲；不改变机械臂及ROS 2进程状态。
- `3`：启动现有六关节通信与运动自检，保留冲突检查、安全停止、自动竖直归位和日志功能。
- `setup_gpio.sh`：配置传送带启停使用的Jetson GPIO。
- `monitor_sorting.sh`：查看节点、进程和日志状态。

部署到Jetson用户目录后使用，例如：

```bash
chmod +x ~/start_sorting.sh ~/stop_sorting.sh ~/1 ~/2 ~/3 ~/setup_gpio.sh ~/monitor_sorting.sh
```

脚本每次运行都会通过`sudo`自动配置GPIO引脚复用，随后独立控制传送带；命令行可能要求输入Jetson密码：

```bash
~/1
~/2
~/3
```
