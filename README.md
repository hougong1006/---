# 智检护航 - 航空丝堵表面缺陷在线检测与分拣系统

本仓库保存职业院校技能大赛项目中实际使用的机械臂控制、缺陷检测和可视化监控代码。仓库从第二轮比赛准备阶段开始记录真实开发迭代，每项功能优化、参数调整和故障修复均应单独提交。

## 代码范围

- `ros2_ws/src/dofbot_pro_yolov11`：YOLO11检测、多帧投票、深度读取及分拣流程。
- `ros2_ws/src/dofbot_pro_driver`：机械臂I2C控制与设备偏移配置。
- `ros2_ws/src/dofbot_pro_info`：基于KDL的机械臂运动学求解。
- `ros2_ws/src/dofbot_pro_interface`：项目使用的ROS 2消息与服务定义。
- `ros2_ws/src/dofbot_pro_description`：运动学求解使用的机械臂URDF模型。
- `qt_arm_monitor`：基于PyQt5的设备控制与可视化监控界面。
- `scripts`：设备一键启动、停止、GPIO配置和运行监控脚本。
- `joint_self_test`：独立的六关节通信、运动与自动归位自检工具。
- `alarm_light_stm32`：独立报警灯STM32工程及Jetson状态信号接线说明。
- `docs/Jetson_YOLO11_开发参考手册.md`：与当前代码基线对应的系统架构、参数、部署和验证手册。

第三方Orbbec相机ROS驱动、Ultralytics及系统依赖不重复提交到本仓库，应在Jetson设备上单独安装。

## 当前基线

- ROS 2 Humble，`ROS_DOMAIN_ID=98`。
- 当前设备IP：`10.182.135.172`。
- 检测类别：`biaozhunketi`（标准件）、`quexianketi`（缺陷件）。
- 标准件只统计并随传送带通过，缺陷件进入抓取流程。
- 多帧投票参数：15帧窗口，至少10票通过。
- 有效检测区：检测框完整位于横向`120～520`像素内才参与计数或投票，过滤工件进出画面时的透视误判。
- 第6号舵机负责夹爪，当前闭合角度为165。
- 设备有效坐标补偿：X=-0.02754、Y=-0.030416761081137312、Z=-0.0299。

## Jetson构建

```bash
cd ~/dofbot_pro_ws
colcon build --symlink-install
source /opt/ros/humble/setup.bash
source ~/dofbot_pro_ws/install/setup.bash
```

启动和停止：

```bash
bash ~/start_sorting.sh
bash ~/stop_sorting.sh
```

停止脚本优先调用分拣节点的`/stop_conveyor`服务，由已经占用BCM6的节点发送50 ms停止脉冲，再终止ROS 2节点。若设备仍运行不支持该服务的旧分拣节点，脚本会在同一次停止流程中释放GPIO后自动补发停止脉冲。Windows可视化界面的停止按钮调用相同脚本。

启动脚本完成GPIO引脚复用配置后，会先通过BCM13向传送带控制板发送50 ms启动脉冲，再启动各ROS 2节点。Windows可视化界面的一键启动同样调用该脚本，因此界面启动和命令行启动具有一致的传送带联动行为。启动前应确保传送带检测区域内没有待检工件，防止节点初始化期间工件未经检测直接通过。

独立报警灯板不控制传送带：Jetson通过BCM5（物理29脚/GPIO01）持续输出正常运行状态，通过BCM12（物理32脚/GPIO07）持续输出缺陷抓取状态；STM32接收后控制绿灯、红灯和蜂鸣器。详细接线与状态表见`alarm_light_stm32/README.md`。

六关节自检应在分拣系统停止后单独运行：

```bash
bash ~/joint_self_test/start_joint_test.sh
bash ~/joint_self_test/stop_joint_test.sh
```

自检会逐个驱动六个关节并读取角度，正常完成或安全停止后均返回竖直姿态。详细部署和安全说明见`joint_self_test/README.md`。

## 本地凭据配置

公开仓库不保存Jetson登录密码。Windows启动可视化界面前，在当前PowerShell会话中设置：

```powershell
$env:DOFBOT_SSH_USER = 'jetson'
$env:DOFBOT_SSH_PASSWORD = '<设备密码>'
python .\qt_arm_monitor\main.py
```

设备端脚本如需自动执行GPIO的`sudo`配置，可在启动脚本前临时设置：

```bash
export DOFBOT_SUDO_PASSWORD='<设备密码>'
bash ~/start_sorting.sh
```

这些环境变量仅在当前终端会话中有效，不要把真实密码写入代码或提交到Git。

## 模型说明

`best.pt`保留训练权重，`best.engine`是当前设备运行使用的TensorRT引擎。TensorRT引擎与Jetson型号、CUDA和TensorRT版本相关，迁移设备时应使用`best.pt`在目标设备上重新导出，不应直接复用旧引擎。

## 提交约定

每次优化只解决一个明确问题，提交信息建议使用：

```text
feat: 增加某项功能
fix: 修复某项故障
perf: 优化检测或执行性能
ui: 调整可视化界面
docs: 更新说明和实验记录
```

修改前记录基线，修改后记录测试条件和结果。不要把多个无关改动合并为一次提交。

涉及模型、投票参数、坐标补偿、机械臂姿态、GPIO、ROS接口或界面统计逻辑的修改，还必须同步更新开发参考手册。
