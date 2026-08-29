# 设备脚本

- `start_sorting.sh`：按顺序启动相机、机械臂驱动、KDL运动学、图像转换、YOLO检测和分拣节点。
- `stop_sorting.sh`：先向BCM6输出50 ms停止脉冲，再停止分拣相关进程并清理运行状态。可视化停止按钮和命令行停止共用该脚本。
- `setup_gpio.sh`：配置传送带启停使用的Jetson GPIO。
- `monitor_sorting.sh`：查看节点、进程和日志状态。

部署到Jetson用户目录后使用，例如：

```bash
chmod +x ~/start_sorting.sh ~/stop_sorting.sh ~/setup_gpio.sh ~/monitor_sorting.sh
```
