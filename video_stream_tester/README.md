# MJPEG视频流独立测试平台

该工具只测试Jetson设备端的MJPEG视频服务，不执行SSH连接、机械臂动作、传送带控制或检测统计。

默认视频地址：

```text
http://10.182.135.172:8765/
```

运行：

```powershell
python .\main.py
```

创建桌面快捷方式：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\create_shortcut.ps1
```

诊断信息包括HTTP连接状态、Content-Type、分辨率、实时帧率、累计帧数、累计数据量和最近一次错误。

