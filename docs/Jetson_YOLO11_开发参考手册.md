# 智检护航：航空丝堵表面缺陷在线检测与分拣系统开发手册

> 文档版本：2026-08-27
>
> 对应代码基线：`2938fea feat: 增加机械臂六关节通信自检`
>
> 适用系统：Jetson、ROS 2 Humble、YOLO11/TensorRT、Orbbec RGB-D相机、DOFBOT Pro机械臂、传送带和PyQt5监控界面。
>
> 本手册以当前正式仓库源码为依据。代码事实、现场参数和改进建议会明确区分，不能把建议当成已经实现的功能。

## 1. 项目定位与目录

系统名称：

```text
智检护航-航空丝堵表面缺陷在线检测与分拣系统监控平台
```

当前业务目标：识别航空丝堵零件中的标准件和缺陷件。标准件只统计并随传送带通过，缺陷件进入停带、复检、三维定位、机械臂抓取和分类投放流程。

### 1.1 Windows正式代码仓库

```text
E:\机械臂jetson主板上全部代码（完整拷贝）\机械臂设计代码\jixiebichengxu\航空丝堵缺陷检测_当前工程
```

后续代码修改、文档更新和Git提交均应在此目录进行。

### 1.2 Jetson运行目录

```text
/home/jetson/dofbot_pro_ws
```

设备侧常用部署位置：

```text
/home/jetson/start_sorting.sh
/home/jetson/stop_sorting.sh
/home/jetson/setup_gpio.sh
/home/jetson/monitor_sorting.sh
/home/jetson/qt_arm_monitor
/home/jetson/joint_self_test
```

### 1.3 当前保留资料

| 目录 | 用途 |
|---|---|
| `航空丝堵缺陷检测_当前工程` | 当前正式Git仓库 |
| `qt_arm_monitor` | Windows桌面“机械臂监控”快捷方式实际运行版本 |
| `可视化界面_设备端备份` | Jetson本地界面部署备份 |
| `设备完整备份_20260826` | Jetson完整备份，只用于恢复和追溯 |
| `模型备用_电脑原版_20260823_025346` | 电脑原始模型备份，不覆盖当前模型 |
| `机械臂控制板参考代码_STM32` | 控制板与传送带接口参考代码 |
| `Jetson主板配置资料` | Jetson配置资料 |
| `DOFBOT_PRO设备恢复资料` | 厂家镜像、安装和恢复工具 |

不要在完整备份中直接开发，也不要把ROS的`build`、`install`、`log`从一台设备复制到另一台设备使用。

## 2. 当前代码结构

```text
航空丝堵缺陷检测_当前工程/
├─ ros2_ws/src/
│  ├─ dofbot_pro_yolov11/      # 图像适配、YOLO检测、深度定位和抓取
│  ├─ dofbot_pro_driver/       # 机械臂驱动和坐标补偿配置
│  ├─ dofbot_pro_info/         # 正逆运动学ROS 2服务
│  ├─ dofbot_pro_interface/    # 自定义消息与服务
│  └─ dofbot_pro_description/  # DOFBOT Pro URDF
├─ qt_arm_monitor/             # 仓库中的监控界面基线
├─ scripts/                    # 一键启停、GPIO配置和日志监控
├─ joint_self_test/            # 六关节通信与运动自检
├─ docs/                       # 开发文档
├─ README.md
└─ CHANGELOG.md
```

第三方Orbbec相机驱动、Ultralytics、TensorRT、`Arm_Lib`和Jetson.GPIO由设备环境提供，不重复纳入正式仓库。

## 3. 当前系统架构

### 3.1 端到端数据链路

```text
Orbbec RGB-D相机
├─ 彩色图像 /camera/color/image_raw
│  └─ msgToimg
│     └─ /image_data
│        └─ yolov11.py
│           ├─ YOLO11 TensorRT推理
│           ├─ 标准件确认后输出计数日志
│           ├─ 缺陷件15帧/10票确认
│           ├─ 发布Yolov11DetectInfo
│           └─ 输出8765端口MJPEG标注视频
│
└─ 深度图像 /camera/depth/image_raw
   └─ yolov11_sortation.py
      ├─ Phase1收到缺陷件后输出50 ms停带脉冲
      ├─ 发布redetect_signal要求静止复检
      ├─ Phase2读取目标区域深度中位数
      ├─ 像素坐标反投影到相机三维坐标
      ├─ 相机坐标转换到机械臂坐标
      ├─ 加入X/Y/Z标定补偿
      ├─ 调用dofbot_kinemarics逆运动学服务
      ├─ Arm_Lib控制机械臂与夹爪
      ├─ 投放后分阶段归位
      └─ 输出50 ms启动脉冲并进入下一轮
```

### 3.2 当前启动顺序

`start_sorting.sh`依次启动：

1. GPIO引脚复用配置；
2. Orbbec相机：`dabai_dcw2.launch.py`；
3. 机械臂驱动：`arm_driver`；
4. 运动学服务：`kinemarics_dofbot`；
5. 图像转换：`msgToimg`；
6. 检测程序：直接执行`yolov11.py`；
7. 分拣程序：`yolov11_sortation`。

运行PID记录在`/tmp/dofbot_sorting_pids.txt`，节点日志位于`/tmp/dofbot_logs`。

## 4. 识别业务与当前参数

### 4.1 模型类别

当前模型类别表：

```python
{0: 'biaozhun', 1: 'quexian'}
```

| 类名 | 中文含义 | 当前动作 |
|---|---|---|
| `biaozhun` | 标准件 | 计数，不停带，不抓取 |
| `quexian` | 缺陷件 | 多帧确认、停带、复检、抓取和投放 |

旧的`chengshujinju`、`fulanjinju`和`qingjinju`只存在于部分兼容代码或旧注释中，不再是当前模型业务类别。

### 4.2 YOLO检测参数

| 参数 | 当前值 | 含义 |
|---|---:|---|
| `VOTE_FRAMES` | 15 | 缺陷件投票窗口长度 |
| `VOTE_THRESHOLD` | 10 | 至少10票一致才发布 |
| `MAX_NO_DETECT` | 2 | 连续无缺陷目标后清空投票的阈值 |
| `STANDARD_RELEASE_FRAMES` | 3 | 标准件离开后解除计数锁存 |
| `RIGHT_MARGIN` | 60像素 | 目标中心在画面右侧60像素内时暂不处理 |
| 自动开始延迟 | 8秒 | 等待其它节点初始化 |
| MJPEG端口 | 8765 | 输出YOLO标注画面 |
| JPEG质量 | 70 | MJPEG帧压缩质量 |
| MJPEG发送间隔 | 0.066秒 | 理论上限约15 FPS，不等于实际推理帧率 |

标准件使用`VOTE_THRESHOLD=10`累计确认，确认后输出：

```text
[COUNT] biaozhun
```

标准件计数采用锁存方式，同一零件持续出现在画面时只计一次；连续3帧未看到标准件后重新允许下一次计数。

缺陷件通过15帧/10票后发布`Yolov11DetectInfo(result, centerx, centery)`。

### 4.3 模型文件与TensorRT

运行时加载：

```text
/home/jetson/dofbot_pro_ws/src/dofbot_pro_yolov11/dofbot_pro_yolov11/best.engine
```

正式仓库同时保留`best.pt`和`best.engine`。TensorRT引擎与Jetson型号、JetPack、CUDA和TensorRT版本相关。出现以下警告时表示引擎可能不是在当前硬件环境生成：

```text
Using an engine plan file across different models of devices is not recommended
```

处理原则：保留`best.pt`，在目标Jetson上重新导出`best.engine`，不要把另一型号设备生成的引擎直接作为最终比赛版本。

## 5. 深度与三维坐标转换

分拣节点订阅`/camera/depth/image_raw`，把深度图缩放到`640 x 480`，然后以检测中心为中心按以下半径依次搜索有效深度：

```text
10 -> 30 -> 60 -> 100 -> 150像素
```

找到非零深度后取区域内有效值的中位数，并由毫米换算为米。该方法可减少单点深度空洞影响，但窗口过大时可能混入背景或传送带深度。

当前相机内参：

```python
fx = 477.57421875
fy = 477.55718994140625
cx = 319.3820495605469
cy = 238.64108276367188
```

像素点`(u, v)`和深度`Z`转换为相机坐标：

```text
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
Z = depth
```

这一步得到的是目标相对相机的位置，不能直接作为机械臂抓取坐标。当前代码继续使用固定的`EndToCamMat`、机械臂初始末端正解位姿和齐次变换矩阵，将其转换到机械臂参考坐标系，然后加入现场补偿：

```yaml
x_offset: -0.02754
y_offset: -0.030416761081137312
z_offset: -0.0299
```

逆解请求前，代码还执行：

```python
request.tar_x = pose_T[0] + 0.02
```

因此实际抓取点由相机标定变换、XYZ配置补偿和额外X方向`+0.02 m`共同决定。调整抓取位置前必须确认修改属于哪一层，避免重复补偿。

## 6. 运动学与机械臂执行

### 6.1 正逆运动学

ROS 2服务为`dofbot_kinemarics`，使用`dofbot_pro_interface/srv/Kinemarics.srv`。`kin_name="fk"`用于正运动学，`kin_name="ik"`用于逆运动学。服务端读取DOFBOT Pro URDF，对前5个运动关节求解，第6号舵机由抓取程序单独控制夹爪。

仓库代码链接外部库：

```text
/usr/lib/libdofbotpro_kinemarics.so
```

源码头文件包含KDL的`ChainIkSolverPos_LMA`和递归正解求解器，但`dofbot_getIK()`的具体实现位于外部动态库中，仓库没有该实现源码。因此当前能确认系统使用KDL接口和厂商运动学库，但仅凭仓库不能严谨证明运行时逆解一定采用LMA数值迭代法。需要查看动态库源码、符号或厂商说明后才能下结论。

### 6.2 姿态与执行流程

当前分拣程序的初始/等待姿态：

```python
[90.0, 113.0, 29.0, -18.0, 90.0, 30.0]
```

六关节自检工具定义的竖直归位姿态：

```python
[90, 90, 90, 0, 90, 30]
```

两者用途不同：分拣程序使用便于抓取的等待姿态，自检工具结束后使用竖直展示姿态。

当前抓取流程：

```text
IK求解前5关节
-> 运动到抓取点
-> 第5关节调整夹爪方向
-> 第6号舵机闭合到150
-> 抬升
-> 移动到分类投放位置
-> 第6号舵机松开到30
-> 先收臂
-> 再旋转底座归位
-> 启动传送带
```

| 项目 | 数值 |
|---|---:|
| 夹爪闭合 | 150 |
| 夹爪松开 | 30 |
| IK等待超时 | 5秒 |
| 第4关节上限处理 | 大于90时限制为90 |

分类姿态表仍保留两项，但当前检测逻辑只把缺陷件送入抓取流程：

```python
'biaozhun': [178, 59, 20, 59, 90, 30]
'quexian':  [222, 12, 72, 75, 89, 29]
```

## 7. 传送带GPIO控制

| 功能 | BCM | 物理引脚 | STM32输入 | 脉冲 |
|---|---:|---:|---|---:|
| 停止传送带 | 6 | Pin 31 | PA0 | 高电平50 ms |
| 启动传送带 | 13 | Pin 33 | PA1 | 高电平50 ms |

Jetson重启后可能需要执行：

```bash
sudo bash ~/setup_gpio.sh
```

50 ms是Jetson输出控制脉冲宽度，不等于传送带从收到命令到机械完全停止的时间。实际停止时间受STM32扫描、继电器、电机惯性、皮带负载和供电影响，必须使用高速录像、编码器或传感器实测，不能从代码推算出精确机械停止时间。

## 8. 可视化监控界面

### 8.1 当前实际使用版本

Windows桌面快捷方式：

```text
C:\Users\Lenovo\Desktop\机械臂监控.lnk
```

实际入口：

```text
E:\机械臂jetson主板上全部代码（完整拷贝）\机械臂设计代码\jixiebichengxu\qt_arm_monitor\main.py
```

该版本支持普通窗口、`--maximized`和`--fullscreen`。正式仓库中的`qt_arm_monitor`是代码基线，但当前与桌面实际运行版本存在少量差异，更新界面时应先比较并同步，不能直接删除桌面版本。

### 8.2 通信和数据来源

Windows运行时通过SSH执行`bash ~/start_sorting.sh`和`bash ~/stop_sorting.sh`，通过SSH读取`yolov11.log`与`yolov11_sortation.log`，并通过HTTP读取`http://<设备IP>:8765/`的MJPEG视频。

Jetson本地运行时使用本地子进程启停，直接`tail -F`读取日志，并从`http://127.0.0.1:8765/`读取视频。

登录凭据通过环境变量提供，不得写入仓库：

```powershell
$env:DOFBOT_SSH_USER = 'jetson'
$env:DOFBOT_SSH_PASSWORD = '<设备密码>'
```

视频与统计是两条独立通道：

```text
YOLO检测结果
├─ 标注图像 -> JPEG/MJPEG -> HTTP 8765 -> 界面视频
└─ 计数/分拣事件 -> 程序日志 -> SSH或本地tail -> 界面统计
```

因此可能出现“有视频但不计数”或“计数正常但视频不显示”，排查时要分别检查8765端口和日志链路。

### 8.3 当前统计规则

| 数据 | 触发日志 | 计数时机 |
|---|---|---|
| 标准件 | `[COUNT] biaozhun` | 检测确认后加1，不要求抓取 |
| 缺陷件 | `分拣: quexian -> 位置 ID=2` | 进入投放动作时加1 |
| 检测总数 | 标准件数 + 缺陷件数 | 任一类别计数后更新 |
| 运行速度 | 运行时间 / 检测总数 | 单位为秒/件 |

### 8.4 当前界面参数控制的限制

界面中的置信度、暂停检测、夹爪力度、XYZ偏移和分拣速度按钮目前只把值写入：

```text
/tmp/yolo_conf.txt
/tmp/yolo_pause.txt
/tmp/gripper_force.txt
/tmp/offset_x.txt
/tmp/offset_y.txt
/tmp/offset_z.txt
/tmp/sort_speed.txt
```

当前`yolov11.py`和`yolov11_sortation.py`没有读取这些文件。这些控件目前主要改变界面显示，并不会可靠改变检测或机械臂运行参数。真正生效的参数来自源码和`offset_value.yaml`。后续若启用在线调参，应增加明确的ROS参数或服务、范围校验、持久化和操作日志。

## 9. 六关节通信与运动自检

自检工具会使用`Arm_ping_servo()`检查1至6号舵机，正常响应为`0xDA`；读取当前角度；让六个关节依次小幅运动并返回；以10度为读回允许误差；并在正常结束、收到SIGTERM或异常退出时尝试回到竖直姿态。

它还会检查分拣相关进程，避免与其它程序同时占用I2C。

```bash
bash ~/joint_self_test/start_joint_test.sh
bash ~/joint_self_test/stop_joint_test.sh
tail -f /tmp/dofbot_joint_self_test.log
```

自检必须空载运行，机械臂周围不得有人员和障碍物，并且必须先停止分拣系统。

## 10. 构建、部署与运行

### 10.1 构建ROS 2工作区

```bash
cd ~/dofbot_pro_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source ~/dofbot_pro_ws/install/setup.bash
```

只构建分拣包：

```bash
colcon build --packages-select dofbot_pro_yolov11 --symlink-install
```

### 10.2 一键启停与监控

```bash
bash ~/start_sorting.sh
bash ~/stop_sorting.sh
bash ~/monitor_sorting.sh status
bash ~/monitor_sorting.sh all
bash ~/monitor_sorting.sh error
```

常用诊断：

```bash
hostname -I
ps -eo pid,lstart,args | grep -E '[y]olov11|[a]rm_driver|[k]inemarics|[m]sgToimg'
ss -ltnp | grep ':8765'
timeout 3 curl -s http://127.0.0.1:8765/ >/dev/null
ros2 node list
ros2 topic list
ros2 service list | grep kinemarics
```

检查模型类别：

```bash
python3 -c "from ultralytics import YOLO; m=YOLO('/home/jetson/dofbot_pro_ws/src/dofbot_pro_yolov11/dofbot_pro_yolov11/best.engine', task='detect'); print(m.names)"
```

检查源码语法：

```bash
python3 -m py_compile \
  ~/dofbot_pro_ws/src/dofbot_pro_yolov11/dofbot_pro_yolov11/yolov11.py \
  ~/dofbot_pro_ws/src/dofbot_pro_yolov11/dofbot_pro_yolov11/yolov11_sortation.py
```

## 11. 当前已知局限与风险

以下是当前代码事实，不表示系统无法运行，但后续优化应优先处理：

1. `yolov11.py`顶部旧注释仍写5帧/3票，实际代码是15帧/10票，以变量值为准。
2. 标准件确认是累计命中，不是严格长度为15的滑动窗口。
3. 检测推理没有显式传入置信度阈值，界面置信度按钮也未接入后端。
4. 多目标处理遇到第一个有效缺陷框后`break`，没有目标ID和跟踪关联。
5. 缺陷投票通过后使用缓冲区最后一项坐标，没有对确认坐标取中位数或均值。
6. 彩色图和深度图没有按时间戳同步，深度窗口扩大后可能取到背景。
7. 相机内参和`EndToCamMat`硬编码在Python文件中。
8. 运动学实现依赖外部动态库，仓库不足以证明具体逆解算法。
9. 分拣节点直接用`Arm_Device`控制舵机，同时启动脚本还会启动`arm_driver`，存在多个控制者共享I2C的风险。
10. 启停脚本在普通终止失败后会使用`kill -9`清理残留，不能保证机械臂在强制终止前完成安全归位。
11. 异常恢复路径会尝试重新启动传送带，但没有硬件反馈确认机械臂和传送带真实状态。
12. MJPEG服务无认证并监听`0.0.0.0`，只应在可信现场网络使用。
13. 界面统计来源是运行日志，日志重连、历史日志和重复事件需要继续防重验证。
14. 分拣等待姿态和自检竖直姿态不同，不能互相替换。

## 12. 修改与验证规范

修改前应确认设备IP、ROS_DOMAIN_ID、运行进程和Git提交；备份模型、坐标补偿与动作姿态；确认修改的是源码树还是安装树；并停止现有分拣程序。

修改后应执行静态检查、重新构建、检查源码和安装内容一致性，再依次完成无动作软件验证、传送带空载、机械臂低速空载和单个真实零件验证。最后更新`CHANGELOG.md`并创建独立Git提交。

```powershell
cd "E:\机械臂jetson主板上全部代码（完整拷贝）\机械臂设计代码\jixiebichengxu\航空丝堵缺陷检测_当前工程"
git status
git diff --check
git add <本次修改文件>
git commit -m "docs: 更新开发手册与当前程序基线"
git push origin main
```

## 13. 推荐优化顺序

1. 建立唯一机械臂控制者，消除`arm_driver`和分拣节点同时控制I2C的风险；
2. 把投票、置信度、模型路径、相机内外参、姿态和GPIO参数配置化；
3. 将界面调参控件接入ROS参数或受控服务，删除无效的`/tmp`占位控制；
4. 增加目标跟踪、坐标稳定化和RGB-D时间同步；
5. 增加深度有效性、工作空间、IK结果和关节范围校验；
6. 将抓取流程改成可观测状态机，增加超时、故障保持和人工恢复；
7. 改造停止流程，使机械臂先进入安全状态再停止进程；
8. 给视频、统计和控制接口增加健康状态与断线提示；
9. 记录每轮检测、停带、抓取、投放和归位耗时，形成可复现实验数据。

## 14. 文档维护规则

模型类别、权重、TensorRT引擎、投票参数、坐标补偿、标定、机械臂姿态、夹爪角度、GPIO、ROS接口、启动顺序、界面通信、统计逻辑或自检姿态发生变化时，都必须同步修改本手册并形成Git提交。

遇到文档与代码冲突时，以已部署设备的实际源码、当前Git提交和现场验证结果为准，并立即修正文档。
