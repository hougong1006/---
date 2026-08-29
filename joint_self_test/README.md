# 六关节通信与运动自检

该目录是独立于ROS 2分拣流程的机械臂自检工具。它依次检查1至6号舵机的通信响应，让每个关节小幅运动并返回，正常结束、手动停止或程序异常时均会尝试回到竖直姿态。

竖直归位姿态为：

```text
[90, 90, 90, 0, 90, 30]
```

## 部署

在Windows PowerShell中进入仓库并上传目录：

```powershell
scp -r .\joint_self_test jetson@10.182.135.194:/home/jetson/
```

登录Jetson并设置脚本权限：

```bash
chmod +x ~/joint_self_test/*.sh ~/joint_self_test/*.py
```

## 使用

测试前确保机械臂周围无人、无障碍物，并先停止现有分拣程序。机械臂应空载运行。

一键启动：

```bash
bash ~/joint_self_test/start_joint_test.sh
```

查看实时日志：

```bash
tail -f /tmp/dofbot_joint_self_test.log
```

一键安全停止：

```bash
bash ~/joint_self_test/stop_joint_test.sh
```

自检大约在20秒内自动完成并退出。停止脚本发送`SIGTERM`，Python程序收到信号后会取消剩余测试，并在退出前执行竖直归位。停止脚本不会使用`kill -9`，避免在归位过程中强行切断程序。

如果相机、机械臂驱动、运动学、检测或分拣进程仍在运行，自检会拒绝启动，以防两个程序同时通过I2C控制机械臂。
