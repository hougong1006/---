# 设备脚本

- `start_sorting.sh`：先拒绝与正在运动的关节自检并发，自动清理上一次分拣或独立视频残留，再完成GPIO配置、传送带启动和六个节点顺序启动。任一节点失败会回滚本次已启动进程。
- `stop_sorting.sh`：立即取消尚未完成的旧启动流程；分拣节点运行时调用其`/stop_conveyor`服务，再按已验证PID终止整个进程组并进行特征匹配兜底清理。可视化停止按钮和命令行停止共用该脚本。
- `qidong`：独立启动传送带。先调用`setup_gpio.sh`配置引脚复用，再由BCM13输出一次50 ms启动脉冲；不启动ROS 2、相机、YOLO、机械臂或分拣程序。
- `tingzhi`：独立停止传送带。先调用`setup_gpio.sh`配置引脚复用，再由BCM6输出一次50 ms停止脉冲；不改变机械臂及ROS 2进程状态。
- `3`：以前台阻塞方式运行六关节通信与运动自检；只有测试结束并完成竖直归位后才返回命令行，防止操作者过早启动分拣程序。
- `setup_gpio.sh`：配置传送带启停使用的BCM6/BCM13，以及独立报警灯状态输出使用的BCM5/BCM12；配置后会读回寄存器校验。
- `monitor_sorting.sh`：查看节点、进程和日志状态。

部署到Jetson用户目录后使用，例如：

```bash
chmod +x ~/start_sorting.sh ~/stop_sorting.sh ~/qidong ~/tingzhi ~/3 ~/setup_gpio.sh ~/monitor_sorting.sh
```

脚本每次运行都会通过`sudo`自动配置GPIO引脚复用，随后独立控制传送带；命令行可能要求输入Jetson密码：

```bash
qidong
tingzhi
~/3
```
