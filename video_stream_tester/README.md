# 完整界面视频流测试版

本版本以当前维护的`机械臂监控`完整界面为基线，布局、统计、日志和控制模块保持一致，并在顶部增加“只连接视频”按钮。

点击“只连接视频”时，只访问：

```text
http://设备IP:8765/
```

该操作不会创建SSH连接，不会启动机械臂、传送带或分拣节点。再次点击“断开视频”只关闭MJPEG读取线程。

连接过程、HTTP连接成功、收到首帧和连接错误会显示在原界面的运行日志中。

创建桌面快捷方式：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\create_shortcut.ps1
```
