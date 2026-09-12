# 设备脚本

- `runtime_common.sh`：所有运行入口共用的模式切换锁、传送带安全停止和残留进程清理逻辑。按完整命令参数识别进程，不会把查看日志的`tail`误判为节点。
- `start_sorting.sh`：先停止上一运行模式并清理分拣、视频、自检残留，再完成GPIO配置、传送带启动和六个节点顺序启动。
- `stop_sorting.sh`：先停止传送带，再中止分拣、视频和关节自检的全部项目进程。可视化停止按钮和命令行停止共用该脚本。
- `start_video_only.sh`：先停止传送带并清理上一运行模式，再只启动相机、图像转换和MJPEG视频链路。
- `stop_video_only.sh`：停止视频时也执行全项目清理，避免独立视频和完整分拣互相留下后台进程。
- `../depth_viewer/start_orbbec_depth_platform_exclusive.sh`：深度平台启动前也调用统一清理；切换到其他命令时，其启动器、网页服务及相机节点会一并停止。
- `qidong`：先停止上一运行模式并清理全部残留，再由BCM13输出一次150 ms启动脉冲；只启动传送带。
- `tingzhi`：先通过分拣节点服务或BCM6输出停止信号，再清理全部项目进程。
- `ceshi`：先停止传送带并清理全部残留，再以前台阻塞方式运行六关节通信与运动自检；测试结束后完成竖直归位。
- `chushi`：不启动ROS 2、相机、YOLO或传送带，仅将机械臂移动到检测等待姿态`[89, 56, 94, -36, 90, 30]`并读取关节反馈校验。
- `bianyi`：修改YOLO检测或机械臂分拣源码后，一键执行Python语法检查、ROS 2软件包编译和可执行入口验证；不启动任何设备。
- `setup_gpio.sh`：配置传送带启停使用的BCM6/BCM13，以及独立报警灯状态输出使用的BCM5/BCM12；配置后会读回寄存器校验。
- `monitor_sorting.sh`：查看节点、进程和日志状态。

部署到Jetson用户目录后使用，例如：

```bash
chmod +x ~/runtime_common.sh ~/start_sorting.sh ~/stop_sorting.sh ~/start_video_only.sh ~/stop_video_only.sh ~/qidong ~/tingzhi ~/ceshi ~/chushi ~/bianyi ~/setup_gpio.sh ~/monitor_sorting.sh
sudo ln -sf /home/jetson/bianyi /usr/local/bin/bianyi
```

脚本每次运行都会通过`sudo`自动配置GPIO引脚复用，随后独立控制传送带；命令行可能要求输入Jetson密码：

```bash
qidong
tingzhi
ceshi
chushi
bianyi
```
