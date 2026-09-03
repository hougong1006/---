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
{0: 'biaozhunketi', 1: 'quexianketi'}
```

| 类名 | 中文含义 | 当前动作 |
|---|---|---|
| `biaozhunketi` | 标准件 | 计数，不停带，不抓取 |
| `quexianketi` | 缺陷件 | 多帧确认、停带、复检、抓取和投放 |

旧的`chengshujinju`、`fulanjinju`和`qingjinju`只存在于部分兼容代码或旧注释中，不再是当前模型业务类别。

### 4.2 YOLO检测参数

| 参数 | 当前值 | 含义 |
|---|---:|---|
| `VOTE_FRAMES` | 15 | 缺陷件投票窗口长度 |
| `VOTE_THRESHOLD` | 10 | 至少10票一致才发布 |
| `MAX_NO_DETECT` | 2 | 连续无缺陷目标后清空投票的阈值 |
| `DEFECT_TRACK_MAX_DISTANCE` | 90像素 | 缺陷投票目标相邻帧的最大中心点距离 |
| `STANDARD_CONFIRM_FRAMES` | 3 | 标准件轨迹至少命中3帧才允许计数 |
| `STANDARD_COUNT_LINE_X` | 320像素 | 标准件从右向左越过该线时计数 |
| `STANDARD_TRACK_MAX_DISTANCE` | 70像素 | 相邻帧检测框中心的最大匹配距离 |
| `STANDARD_TRACK_MAX_MISSED` | 8帧 | 短时漏检时保留标准件轨迹的帧数 |
| `ROI_LEFT` | 120像素 | 有效判定区左边界，过滤工件即将离开画面时的透视误判 |
| `ROI_RIGHT` | 520像素 | 有效判定区右边界，过滤工件尚未完全进入画面的检测结果 |
| 自动开始延迟 | 8秒 | 等待其它节点初始化 |
| MJPEG端口 | 8765 | 输出YOLO标注画面 |
| JPEG质量 | 70 | MJPEG帧压缩质量 |
| MJPEG发送间隔 | 0.066秒 | 理论上限约15 FPS，不等于实际推理帧率 |

标准件使用独立的中心点轨迹进行去重。轨迹命中至少3帧并从右向左越过
`X=320`计数线后输出：

```text
[COUNT] biaozhunketi track=<轨迹编号> hits=<命中帧数>
```

每条轨迹只计数一次，因此同一画面中的多个标准件可以分别统计，同一标准件
持续出现或在计数线左侧短暂丢失后重新出现也不会重复统计。缺陷抓取暂停期间
不老化标准件轨迹，恢复检测后不会把停在原位的工件再次计数。

缺陷件在移动检测阶段通过15帧/10票后发布`Yolov11DetectInfo(result, centerx, centery)`。
托盘内同时出现多个缺陷框时，程序优先选择ROI中心附近的一个目标，并在
后续帧中按照中心点距离持续跟踪该目标。ROI外的其他工件不会再清空当前
目标的投票缓冲。Phase1停带后，Phase2复检优先匹配Phase1发布的位置，
采用5帧/3票快速确认。复检期间暂停标准件轨迹更新，避免缺陷目标短暂误识别
为标准件时造成错误计数，也避免停带期间已有轨迹老化。

界面的缺陷件和检测总数在`[Phase1] 检测到:`事件到达时各增加一次；后续
`分拣:`日志只更新当前对象显示，不再重复计数。因此检测统计不依赖抓取是否
最终完成，Phase2复检也不会造成同一缺陷件增加两次。

标准件计数和缺陷件第一次移动检测均要求检测框完整位于横向`120～520`像素有效区内。工件从右向左运动，刚进入右侧或即将离开左侧时，只在MJPEG画面显示检测框和`WAIT ROI`提示，不计数、不投票、不发布抓取坐标。缺陷件完成第一次确认并停带后，二次复检允许检测框部分越界，但要求目标中心仍在有效区内，并且与第一次确认位置的中心距离不超过90像素。这样既保留第一次检测的边缘误判过滤，又能容纳停带惯性造成的小幅位移。

二次复检超过4秒仍没有可靠结果时，分拣节点先确认机械臂仍处于初始检测姿态，再重新启动传送带；YOLO延迟2秒恢复检测，使未确认的边缘目标先离开有效区，避免永久停带和立即重复触发。若归位校验或启动信号失败，系统仍保持安全停机。视频中两条黄色竖线及`ACTIVE ROI`文字用于标识有效区，可根据实机视角调整两个边界参数。

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
[89.0, 56.0, 94.0, -36.0, 90.0, 30.0]
```

六关节自检工具定义的竖直归位姿态：

```python
[90, 90, 90, 0, 90, 30]
```

两者用途不同：分拣程序使用便于抓取的等待姿态，自检工具结束后使用竖直展示姿态。

当前抓取流程：

```text
IK求解前5关节
-> 在托盘上方将夹爪预收至100度
-> 保持100度安全开度运动到抓取点
-> 第5关节调整夹爪方向
-> 第6号舵机闭合到165
-> 保持抓取点X/Y不变，将Z增加50 mm并重新求解IK
-> 保持夹紧状态竖直上抬50 mm，脱离托盘卡位
-> 移动到分类投放位置
-> 第6号舵机松开到30
-> 先收臂
-> 再旋转底座归位
-> 读取1、2、3、5号关节角度并连续两次确认归位
-> 归位校验通过后启动传送带
-> 发布grasp_done进入下一轮
```

| 项目 | 数值 |
|---|---:|
| 托盘下落安全开度 | 100 |
| 夹爪闭合 | 165 |
| 夹爪松开 | 30 |
| 夹紧后竖直上抬 | 50毫米 |
| IK等待超时 | 5秒 |
| 第4关节上限处理 | 大于90时限制为90 |
| 归位角度容差 | 8度 |
| 归位校验超时 | 6秒 |
| 连续通过次数 | 2次 |
| 二次复检确认 | 5帧/3票 |
| 二次复检超时 | 4秒 |
| 超时后检测延迟 | 2秒 |

第6号舵机角度越小，夹爪开度越大。托盘下落安全开度集中配置为
`GRIPPER_APPROACH_ANGLE`：现场应先在托盘上方空载测试，再以5度为步长
微调；增大该值会缩小开口，减小该值会扩大开口。夹紧角和投放松开角
分别由`GRIPPER_CLOSED_ANGLE`和`GRIPPER_RELEASE_ANGLE`独立配置。

夹紧后的脱盘高度由`POST_GRASP_LIFT_HEIGHT`配置，当前为`0.05`米。程序使用
抓取点相同的X/Y坐标，仅增加Z坐标并重新调用逆运动学，等待上抬动作完成后
才转向投放位置；这与直接跳到固定关节姿态不同，可减少夹爪或工件横向拖动
时被托盘底部结构卡住的风险。

传送带启动采用失效安全联锁。正常流程下，归位命令完成后读取1、2、3、5号
舵机角度，只有全部处于目标角度正负8度内且连续两次通过，才临时打开
`conveyor_start_permitted`并输出BCM13启动脉冲。第4关节的当前归位目标为负角度，
底层`Arm_serial_servo_read()`无法可靠读回负值，因此不纳入反馈校验，但仍等待
完整的归位指令运行时间。抓取异常、读数失败或校验超时均补发停止信号并保持
安全停机，不发布`grasp_done`，需要排查后重新启动系统。

分类姿态表仍保留两项，但当前检测逻辑只把缺陷件送入抓取流程：

```python
'biaozhunketi': [178, 59, 20, 59, 90, 30]
'quexianketi':  [211, 62, 41, 43, 90, 29]
```

缺陷件投放姿态的第1关节使用360度底座舵机，`Arm_Lib`允许范围为
0～360度，因此222度属于合法角度，不应强制改为180度。程序在每次投放前
调用`validate_place_joint()`检查六个关节范围；第1关节为0～360度、第5关节
为0～270度，其余关节为0～180度，任何
超限姿态都会进入安全停机流程，不会再出现投放命令静默失效。

六关节抬升调用必须同时提供关节1～6和运行时间，共7个位置参数。当前抬升
命令为`Arm_serial_servo_write6(90, 120, 0, 0, 90, 165, 1000)`；其中第5
关节固定为90度，第6关节保持165度夹紧，运行时间为1000毫秒。

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

传送带控制板采用上升沿中断和两级软件过滤：同一路输入距离上一次有效触发必须超过300 ms；中断触发后等待约1～2 ms并再次读取引脚，仍为高电平才执行命令。Jetson的50 ms脉冲能够覆盖二次确认时间。此前尝试的1 ms连续采样、连续高15 ms确认方案在实机测试中未能可靠控制传送带，现已恢复现场验证通过的中断版本。软件过滤不能代替共地、电源去耦、信号线隔离和必要的硬件RC或施密特滤波。

系统停止采用传送带联停保护：`stop_sorting.sh`会在终止ROS 2节点前，独立通过BCM6输出一次50 ms停止脉冲；分拣节点正常退出时也会在GPIO清理前再次输出停止脉冲。Windows可视化界面的停止按钮调用同一个停止脚本，因此界面停止与命令行`bash ~/stop_sorting.sh`行为一致。如果脚本提示停止信号发送失败，应立即使用硬件急停并检查GPIO配置及控制板连接。

系统启动采用传送带联动控制：`start_sorting.sh`完成GPIO引脚复用配置后，先通过BCM13独立输出一次50 ms启动脉冲，再依次启动相机、机械臂驱动、运动学、图像转换、YOLO和分拣节点。Windows可视化界面的一键启动与命令行`bash ~/start_sorting.sh`共用该流程。如果启动信号发送失败，脚本会输出明确警告。由于启动脉冲早于视觉节点就绪，启动前必须清空检测区域，待界面显示系统运行正常后再放入工件。

### 7.1 独立报警灯状态输出

报警灯STM32板与传送带控制板是两块独立硬件。BCM6、BCM13仍只向传送带板发送50 ms启停脉冲；报警灯板使用另外两路持续状态电平：

| Jetson状态信号 | BCM编号 | 物理引脚 | 报警板输入 | 含义 |
|---|---:|---:|---|---|
| GPIO01 | 5 | Pin 29 | PA0 | 高电平表示系统正常运行 |
| GPIO07 | 12 | Pin 32 | PA1 | 高电平表示检测到缺陷件并执行夹取 |

报警板PB0驱动绿灯继电器，PB1驱动红灯继电器，PB10驱动蜂鸣器继电器。PA1报警输入优先：PA1为高时关闭绿灯并打开红灯与蜂鸣器；机械臂完成投放且归位校验通过、传送带重新启动后，程序撤销GPIO07并恢复GPIO01；系统停止或异常时两路状态信号均为低。

报警板以10 ms周期采样输入并执行连续稳定判定：PA0高低变化均需稳定200 ms；PA1需连续高100 ms才进入报警，连续低300 ms才解除报警。非对称消抖使报警能够较快进入，同时过滤机械臂运动期间可能出现的短暂低电平干扰。继电器仅在最终状态发生变化时更新。

GPIO01/GPIO07必须配置为普通GPIO输出，且两块控制板必须与Jetson共地。当前雅博载板已通过`jetson-gpio-pinmux-lookup`确认：Pin 29寄存器为`0x02430068`，Pin 32寄存器为`0x02434080`。`setup_gpio.sh`在每次启动时向两处写入`0x004`并读回校验；不能复用BCM6/BCM13的寄存器地址。

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
| 标准件 | `[COUNT] biaozhunketi` | 检测确认后加1，不要求抓取 |
| 缺陷件 | `分拣: quexianketi -> 位置 ID=2` | 进入投放动作时加1 |
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

它还会按完整程序参数检查分拣相关进程，避免与其它程序同时占用I2C，并避免将`tail`日志读取进程误判为机械臂控制程序。短命令`ceshi`以前台阻塞方式运行，只有测试和竖直归位全部完成后才返回命令行。

```bash
bash ~/joint_self_test/start_joint_test.sh
bash ~/joint_self_test/stop_joint_test.sh
tail -f /tmp/dofbot_joint_self_test.log
```

自检必须空载运行，机械臂周围不得有人员和障碍物，并且必须先停止分拣系统。

### 9.1 缺陷件投放姿态重新示教

投放姿态不能根据画面方向直接估算，应停止分拣系统后使用`place_pose_capture`工具读取。工具关闭舵机扭矩前要求操作者托住机械臂；手动移动到新投放位置后连续读取5组关节角度，任一关节波动超过4度则拒绝结果。第1关节为360度底座舵机，合法范围是0～360度；第5关节为0～270度，其余关节为0～180度。读取完成后先手动摆回竖直姿态，再恢复扭矩。

```bash
bash ~/stop_sorting.sh
bash ~/place_pose_capture/capture_place_pose.sh
```

工具输出`[待写入代码] quexianketi joint: [...]`，同时保存到`/tmp/dofbot_place_pose.json`。应将该数组带回开发机审核后，再替换`sort_items['quexianketi']['joint']`。投放流程会将第6关节覆盖为夹紧角165度，因此重新示教主要使用关节1至5的读数。

初始检测等待姿态应使用`bash ~/place_pose_capture/capture_initial_pose.sh`采集。该模式允许当前设备实际使用的第4关节负角（范围-90～180度），并输出`[待写入代码] init_joints: [...]`；第6关节固定为检测等待张开角30度。初始姿态同时用于启动、抓取后归位和归位校验，不能与缺陷件投放数组混用。

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

启动脚本会在覆盖PID文件前检查并清理上一次分拣或纯视频模式的残留进程；检测到六关节自检仍在运动时会拒绝启动。各节点使用独立进程组，停止脚本同时终止组内子进程。启动和停止使用运行令牌协调，因此在28秒初始化阶段按下停止后，旧启动流程不会继续启动剩余节点。

比赛演示建议严格按以下顺序执行：传送带短命令`qidong/tingzhi`测试两轮；执行`ceshi`并等待出现自检和归位完成提示；命令行启动/停止完整分拣系统两轮；在独立视频界面停止视频服务；最后使用综合可视化平台一键启动和一键停止。每一步确认完成提示后再进入下一步。

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
