# Orbbec深度检测平台

- `start_orbbec_depth_platform_exclusive.sh`：Windows端使用的独占深度平台启动器。先停止传送带并清理其他比赛模式，再将机械臂移动到等待位，启动Orbbec相机和端口8766的深度网页服务。
- `depth_web_viewer.py`：订阅ROS 2彩色图、深度图并提供网页接口。

Windows异常断开后，网页服务按`--idle-timeout`退出，启动器随后清理本次相机进程。执行`qidong`、`tingzhi`、`ceshi`、完整分拣或独立视频命令时，也会主动停止该深度平台。

非交互SSH启动需要Jetson本地文件`~/.config/dofbot/runtime.env`，权限应为`600`。该文件只保存在设备中，不提交到仓库。
