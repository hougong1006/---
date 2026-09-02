#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================
# 修改说明：
#   1. 新增 Jetson GPIO 控制：BCM6(停传送带) / BCM13(启传送带)
#   2. 两阶段分拣：Phase1 极速停带 → Phase2 重新检测精确坐标后夹取
#   3. 机械臂归位到位后才启动传送带，确保安全
#   4. 完整自动化分拣闭环，无需手动操作
# ============================================================
import rclpy
import cv2
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
import numpy as np
from std_msgs.msg import Float32, Bool, Int8
from std_srvs.srv import Trigger
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
import cv2 as cv
import time
import math

from message_filters import ApproximateTimeSynchronizer

from dofbot_pro_interface.msg import *
from dofbot_pro_interface.srv import *

import transforms3d as tfs
import tf_transformations as tf
import threading

from ament_index_python import get_package_share_directory
import yaml
import os
from Arm_Lib import Arm_Device

# ==================== GPIO 初始化 ====================
import Jetson.GPIO as GPIO

# BCM编号：对应40pin排针的物理引脚
BCM_STOP  = 6    # Pin 31 → STM32 PA0 → 停止传送带
BCM_START = 13   # Pin 33 → STM32 PA1 → 启动传送带

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(BCM_STOP,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(BCM_START, GPIO.OUT, initial=GPIO.LOW)
print("[GPIO] BCM6(停止) 和 BCM13(启动) 已配置为输出模式")
# =====================================================

pkg_path = get_package_share_directory('dofbot_pro_driver')
offset_file = os.path.join(pkg_path, 'config', 'offset_value.yaml')

with open(offset_file, 'r') as file:
    offset_config = yaml.safe_load(file)
print(offset_config)
print("----------------------------")
print("x_offset: ", offset_config.get('x_offset'))
print("y_offset: ", offset_config.get('y_offset'))
print("z_offset: ", offset_config.get('z_offset'))
encoding = ['16UC1', '32FC1']


class Yolov11GraspNode(Node):
    def __init__(self):
        super().__init__('yolov11_grap')
        self.cx = 0
        self.cy = 0
        self.Arm = Arm_Device()
        self.sub_joint5 = self.create_subscription(Float32, "adjust_joint5", self.get_joint5Callback, qos_profile=1)
        # 发布器
        self.pubPoint = self.create_publisher(ArmJoint, "TargetAngle", qos_profile=10)
        self.pubGraspStatus = self.create_publisher(Bool, "grasp_done", qos_profile=10)
        self.pub_playID = self.create_publisher(Int8, "player_id", qos_profile=10)
        # 订阅器
        self.subDetect = self.create_subscription(Yolov11Detect, "Yolov11DetectInfo", self.getDetectInfoCallback, qos_profile=10)
        # 深度订阅使用 BEST_EFFORT 以匹配 orbbec 相机发布端 QoS
        depth_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST
        )
        self.depth_image_sub = self.create_subscription(Image, '/camera/depth/image_raw', self.getDepthCallback, qos_profile=depth_qos)
        self.sub_SortFlag = self.create_subscription(Bool, 'sort_flag', self.getSortFlagCallback, qos_profile=10)
        # 服务客户端
        self.client = self.create_client(Kinemarics, "dofbot_kinemarics")

        self.color_x = 0.0
        self.color_y = 0.0
        self.color_z = 0.15
        self.grasp_flag = True
        self.init_joints = [90.0, 113.0, 29.0, -18.0, 90.0, 30.0]
        self.down_joint = [130.0, 55.0, 34.0, 16.0, 90.0, 125.0]
        self.set_joint = [90.0, 120.0, 0.0, 0.0, 90.0, 90.0]
        self.gripper_joint = 90.0
        # Joint6: smaller angles open the gripper. Pre-close it at a safe
        # height before descending into the tray, then keep this width fixed.
        self.GRIPPER_APPROACH_ANGLE = 60.0
        self.GRIPPER_CLOSED_ANGLE = 150.0
        self.GRIPPER_RELEASE_ANGLE = 30.0
        self.depth_bridge = CvBridge()
        self.start_sort = False
        self.CurEndPos = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.camera_info_K = [477.57421875, 0.0, 319.3820495605469, 0.0, 477.55718994140625, 238.64108276367188, 0.0, 0.0, 1.0]
        self.EndToCamMat = np.array([[1.00000000e+00, 0.00000000e+00, 0.00000000e+00, 0.00000000e+00],
                                     [0.00000000e+00, 7.96326711e-04, 9.99999683e-01, -9.90000000e-02],
                                     [0.00000000e+00, -9.99999683e-01, 7.96326711e-04, 4.90000000e-02],
                                     [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]])
        self.get_current_end_pos()

        self.name = None

        self.x_offset = offset_config.get('x_offset')
        self.y_offset = offset_config.get('y_offset')
        self.z_offset = offset_config.get('z_offset')

        # ===== 传送带控制状态标志 =====
        self.conveyor_stopped = False   # 传送带是否已停止
        self.waiting_redetect = False   # 是否正在等待Phase2重新检测
        self.detected_name = None       # Phase1记住的物体名称
        self.external_stop_requested = False
        self.gpio_lock = threading.Lock()

        # The process owning BCM6 handles the stop pulse. This avoids a second
        # Jetson.GPIO process failing with "Device or resource busy".
        self.stop_conveyor_service = self.create_service(
            Trigger, 'stop_conveyor', self.stopConveyorServiceCallback)

        # ===== 重检测信号发布器 =====
        self.pub_redetect = self.create_publisher(Bool, 'redetect_signal', qos_profile=10)

        self.play_id = Int8()
        # ===== 分拣物品：3类菌菇（标签顺序: 0=chengshujinju, 1=fulanjinju, 2=qingjinju）=====
        self.sort_items = {
            'biaozhunketi': {'joint': [178, 59, 20, 59, 90, 30], 'id': 1},  # 标准件
            'quexianketi': {'joint': [222, 12, 72, 75, 89, 29], 'id': 2},   # 缺陷件
        }
        self.Arm.Arm_serial_servo_write6_array(self.init_joints, 2000)
        print("Current_End_Pose: ", self.CurEndPos)
        print("Init Done")

    # ==================== GPIO 控制函数 ====================
    def send_stop_conveyor(self):
        """BCM6 短脉冲 → STM32 PA0(EXTI边沿触发) → 停止传送带"""
        with self.gpio_lock:
            GPIO.output(BCM_STOP, GPIO.HIGH)
            time.sleep(0.05)
            GPIO.output(BCM_STOP, GPIO.LOW)

    def send_start_conveyor(self):
        """BCM13 短脉冲 → STM32 PA1(EXTI边沿触发) → 启动传送带"""
        if self.external_stop_requested:
            print("[传送带] 系统停止锁定生效，忽略启动信号")
            return False
        with self.gpio_lock:
            # Recheck after acquiring the lock in case a stop arrived while
            # another conveyor operation was finishing.
            if self.external_stop_requested:
                print("[传送带] 系统停止锁定生效，忽略启动信号")
                return False
            GPIO.output(BCM_START, GPIO.HIGH)
            time.sleep(0.05)
            GPIO.output(BCM_START, GPIO.LOW)
        return True

    def stopConveyorServiceCallback(self, _request, response):
        """Stop the conveyor from the GPIO-owning process and acknowledge it."""
        self.external_stop_requested = True
        self.start_sort = False
        self.grasp_flag = False
        self.waiting_redetect = False
        try:
            self.send_stop_conveyor()
            self.conveyor_stopped = True
            response.success = True
            response.message = 'BCM6 stop pulse sent by sortation node'
            print("[传送带] 收到系统停止服务，BCM6停止信号已发送")
        except Exception as exc:
            response.success = False
            response.message = str(exc)
            print(f"[警告] 系统停止服务发送BCM6失败: {exc}")
        return response

    def do_grasp(self, cx, cy, name, dist):
        """Phase2: 传送带已停止，使用重新检测的精确坐标进行夹取"""
        print(f"[Phase2] 传送带已停，使用重检坐标夹取: {name} ({cx}, {cy}), 深度: {dist:.3f}m")

        try:
            camera_location = self.pixel_to_camera_depth((cx, cy), dist)
            PoseEndMat = np.matmul(self.EndToCamMat, self.xyz_euler_to_mat(camera_location, (0, 0, 0)))
            EndPointMat = self.get_end_point_mat()
            WorldPose = np.matmul(EndPointMat, PoseEndMat)
            pose_T, pose_R = self.mat_to_xyz_euler(WorldPose)
            pose_T[0] = pose_T[0] + self.x_offset
            pose_T[1] = pose_T[1] + self.y_offset
            pose_T[2] = pose_T[2] + self.z_offset

            self.name = name
            print(f"[夹取] 开始夹取: {name}")
            self.grasp(pose_T)
        except Exception as e:
            print(f"[错误] 坐标计算异常: {e}")
            self._reset_for_next_cycle()

    def getDetectInfoCallback(self, msg):
        self.cx = int(msg.centerx)
        self.cy = int(msg.centery)
        self.name = msg.result

        # ===== Phase1: 检测到物体就立即停带（右边缘过滤已在YOLO端完成）=====
        if self.start_sort and self.grasp_flag and not self.waiting_redetect:
            if self.cx != 0 and self.cy != 0 and self.name is not None:
                self.start_sort = False
                self.grasp_flag = False  # 防止重入
                self.detected_name = self.name
                print(f"[Phase1] 检测到: {self.name} ({self.cx},{self.cy}) → 立即停带！")
                self.send_stop_conveyor()  # 50ms GPIO脉冲，极速
                self.conveyor_stopped = True
                # 清除坐标，等待YOLO重新检测静止后的精确位置
                self.cx = 0
                self.cy = 0
                self.name = None
                self.waiting_redetect = True
                # 通知YOLO重新检测一次
                redetect = Bool()
                redetect.data = True
                self.pub_redetect.publish(redetect)

    def getDepthCallback(self, msg):
        depth_image = self.depth_bridge.imgmsg_to_cv2(msg, encoding[1])
        # 打印一次原始深度图信息用于调试
        if not hasattr(self, '_depth_dbg_done'):
            self._depth_dbg_done = True
            print(f"[深度调试] 原始shape={depth_image.shape}, dtype={depth_image.dtype}, "
                  f"min={np.min(depth_image):.2f}, max={np.max(depth_image):.2f}, "
                  f"nonzero={np.count_nonzero(depth_image)}/{depth_image.size}")
        frame = cv.resize(depth_image, (640, 480))
        depth_image_info = frame.astype(np.float32)
        if self.cy != 0 and self.cx != 0:
            # 从中心点周围逐步扩大搜索有效深度（10→30→60→100→150像素半径）
            self.dist = 0.0
            used_r = 0
            for r in [10, 30, 60, 100, 150]:
                y1 = max(0, self.cy - r)
                y2 = min(479, self.cy + r)
                x1 = max(0, self.cx - r)
                x2 = min(639, self.cx + r)
                region = depth_image_info[y1:y2+1, x1:x2+1]
                valid = region[region > 0]
                if len(valid) > 0:
                    self.dist = float(np.median(valid)) / 1000
                    used_r = r
                    break

            if self.dist != 0 and self.name is not None:
                if self.waiting_redetect:
                    # ===== Phase2: 传送带已停止，收到重新检测的精确坐标+深度 → 夹取 =====
                    self.waiting_redetect = False
                    print(f"[Phase2] 重新检测: {self.name} ({self.cx},{self.cy}) d={self.dist:.3f}m r={used_r} → 开始夹取")
                    threading.Thread(target=self.do_grasp,
                                     args=(self.cx, self.cy, self.name, self.dist)).start()

            elif self.waiting_redetect and self.name is not None:
                if not hasattr(self, '_last_dbg') or time.time() - self._last_dbg > 2.0:
                    self._last_dbg = time.time()
                    print(f"[Phase2等待] 深度无效: {self.name} ({self.cx},{self.cy}) 搜索半径150仍无效，继续等待...")

    def getSortFlagCallback(self, msg):
        if msg.data == True and not self.external_stop_requested:
            self.start_sort = True
            print(f"[分拣] 收到分拣信号，开始扫描... (start_sort={self.start_sort})")

    def get_current_end_pos(self):
        if not self.client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error("Service 'dofbot_kinematics' not available!")
            return
        request = Kinemarics.Request()
        request.cur_joint1 = self.init_joints[0]
        request.cur_joint2 = self.init_joints[1]
        request.cur_joint3 = self.init_joints[2]
        request.cur_joint4 = self.init_joints[3]
        request.cur_joint5 = self.init_joints[4]
        request.kin_name = "fk"

        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        response = future.result()
        # print(response)
        if isinstance(response, Kinemarics.Response):
            self.CurEndPos[0] = response.x
            self.CurEndPos[1] = response.y
            self.CurEndPos[2] = response.z
            self.CurEndPos[3] = response.roll
            self.CurEndPos[4] = response.pitch
            self.CurEndPos[5] = response.yaw

    def get_joint5Callback(self,msg):
        self.gripper_joint = msg.data

    def _reset_for_next_cycle(self):
        """异常恢复：重置所有状态，启动传送带，发布 grasp_done"""
        print("[错误恢复] 正在重置状态...")
        try:
            conveyor_started = self.send_start_conveyor()
        except Exception:
            conveyor_started = False
        self.conveyor_stopped = not conveyor_started
        self.grasp_flag = not self.external_stop_requested
        self.name = None
        self.cx = 0
        self.cy = 0
        self.start_sort = False
        self.waiting_redetect = False
        self.detected_name = None
        grasp_done = Bool()
        grasp_done.data = True
        self.pubGraspStatus.publish(grasp_done)
        print("[错误恢复] 状态已重置，等待下一轮分拣")

    def grasp(self, pose_T):
        print("------------------------------------------------")
        print("pose_T: ", pose_T)

        request = Kinemarics.Request()
        request.tar_x = pose_T[0]
        request.tar_y = pose_T[1]
        request.tar_z = pose_T[2]
        request.kin_name = "ik"
        request.roll = -1.0

        try:
            future = self.client.call_async(request)
            # 轮询等待 IK 结果，不使用 spin_until_future_complete（避免破坏主线程执行器）
            start_time = time.time()
            while not future.done():
                time.sleep(0.02)
                if time.time() - start_time > 5.0:
                    print("[错误] IK 服务调用超时(5s)")
                    self._reset_for_next_cycle()
                    return

            response = future.result()
            if response is None:
                print("[错误] IK 服务返回 None")
                self._reset_for_next_cycle()
                return

            joints = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            joints[0] = response.joint1
            joints[1] = response.joint2
            joints[2] = response.joint3
            if response.joint4 > 90:
                joints[3] = 90
            else:
                joints[3] = response.joint4
            joints[4] = 90
            joints[5] = self.GRIPPER_APPROACH_ANGLE

            # 先在托盘上方收至安全开度，避免夹爪以最大开度边下落边收拢。
            self.Arm.Arm_serial_servo_write(
                6, self.GRIPPER_APPROACH_ANGLE, 400)
            time.sleep(0.5)
            self.pubTargetArm(joints, runtime=1500)
            time.sleep(1.8)
            self.move()

        except Exception as e:
            print(f"[错误] 夹取过程异常: {e}")
            self._reset_for_next_cycle()

    def move(self):

        self.Arm.Arm_serial_servo_write(5, self.gripper_joint, 500)
        time.sleep(0.5)
        self.Arm.Arm_serial_servo_write(
            6, self.GRIPPER_CLOSED_ANGLE, 600)
        time.sleep(0.7)
        self.Arm.Arm_serial_servo_write6(
            90.0, 120.0, 0.0, 0.0, self.GRIPPER_CLOSED_ANGLE, 1000)
        time.sleep(1.2)
        print("name",self.name)

        if self.name in self.sort_items:
            item = self.sort_items[self.name]
            print(f"分拣: {self.name} → 位置 ID={item['id']}")
            self.play_id.data = item['id']
            self.pub_playID.publish(self.play_id)
            self.set_joint = item['joint']
        else:
            print(f"[警告] 未知物品: {self.name}，使用默认位置")
            self.set_joint = [90, 50, 60, 2, 90.0, 120]


        # 先用夹紧状态运动到放置位置（Joint6保持150夹紧）
        place_joint = list(self.set_joint)
        place_joint[5] = self.GRIPPER_CLOSED_ANGLE
        self.Arm.Arm_serial_servo_write6_array(place_joint, 1200)
        time.sleep(1.5)
        # 到位后再松开夹爪
        self.Arm.Arm_serial_servo_write(
            6, self.GRIPPER_RELEASE_ANGLE, 400)
        time.sleep(0.5)

        # ===== 平滑归位：分两步走，避免多关节同时大幅运动导致顿挫 =====
        # 第一步：保持底座不动，先收回手臂（关节2/3/4回到归位姿态）
        lift_joint = list(place_joint)
        lift_joint[1] = self.init_joints[1]   # 抬臂
        lift_joint[2] = self.init_joints[2]   # 收回
        lift_joint[3] = self.init_joints[3]   # 收回
        lift_joint[4] = self.init_joints[4]
        lift_joint[5] = self.init_joints[5]   # 夹爪张开
        self.Arm.Arm_serial_servo_write6_array(lift_joint, 1200)
        time.sleep(1.4)

        # 第二步：臂已收回，旋转底座归位（惯性小，运动平稳）
        self.Arm.Arm_serial_servo_write6_array(self.init_joints, 1200)
        print("[夹取] 放置完成，等待机械臂归位...")
        time.sleep(1.8)

        # ===== 归位到位后，启动传送带 =====
        if self.send_start_conveyor():
            self.conveyor_stopped = False
            print("[传送带] 机械臂已归位，传送带启动")
        else:
            self.conveyor_stopped = True
            print("[传送带] 系统停止锁定，归位后保持传送带停止")

        # 重置所有状态
        self.name = None
        self.cx = 0
        self.cy = 0
        self.start_sort = False
        self.grasp_flag = True  # 允许下一轮夹取
        self.waiting_redetect = False
        self.detected_name = None

        # 发布夹取完成信号，触发下一轮检测
        grasp_done = Bool()
        grasp_done.data = True
        self.pubGraspStatus.publish(grasp_done)
        print("[分拣] ===== 本轮分拣完成，等待下一个物体 =====")

    def get_end_point_mat(self):
        print("Get the current pose is ",self.CurEndPos)
        end_w,end_x,end_y,end_z = self.euler_to_quaternion(self.CurEndPos[3],self.CurEndPos[4],self.CurEndPos[5])
        endpoint_mat = self.xyz_quat_to_mat([self.CurEndPos[0],self.CurEndPos[1],self.CurEndPos[2]],[end_w,end_x,end_y,end_z])
        print("endpoint_mat: ",endpoint_mat)
        return endpoint_mat



    #像素坐标转换到深度相机三维坐标坐标，也就是深度相机坐标系下的抓取点三维坐标
    def pixel_to_camera_depth(self,pixel_coords, depth):
        fx, fy, cx, cy = self.camera_info_K[0],self.camera_info_K[4],self.camera_info_K[2],self.camera_info_K[5]
        px, py = pixel_coords
        x = (px - cx) * depth / fx
        y = (py - cy) * depth / fy
        z = depth
        return np.array([x, y, z])

    #通过平移向量和旋转的欧拉角得到变换矩阵
    def xyz_euler_to_mat(self,xyz, euler, degrees=False):
        if degrees:
            mat = tfs.euler.euler2mat(math.radians(euler[0]), math.radians(euler[1]), math.radians(euler[2]))
        else:
            mat = tfs.euler.euler2mat(euler[0], euler[1], euler[2])
        mat = tfs.affines.compose(np.squeeze(np.asarray(xyz)), mat, [1, 1, 1])
        return mat

    #欧拉角转四元数
    def euler_to_quaternion(self,roll,pitch, yaw):
        quaternion = tf.quaternion_from_euler(roll, pitch, yaw)
        qw = quaternion[3]
        qx = quaternion[0]
        qy = quaternion[1]
        qz = quaternion[2]
        #print("quaternion: ",quaternion )
        return np.array([qw, qx, qy, qz])

    #通过平移向量和旋转的四元数得到变换矩阵
    def xyz_quat_to_mat(self,xyz, quat):
        mat = tfs.quaternions.quat2mat(np.asarray(quat))
        mat = tfs.affines.compose(np.squeeze(np.asarray(xyz)), mat, [1, 1, 1])
        return mat

    #把旋转变换矩阵转换成平移向量和欧拉角
    def mat_to_xyz_euler(self,mat, degrees=False):
        t, r, _, _ = tfs.affines.decompose(mat)
        if degrees:
            euler = np.degrees(tfs.euler.mat2euler(r))
        else:
            euler = tfs.euler.mat2euler(r)
        return t, euler

    def pubTargetArm(self, joints, id=6, angle=180.0, runtime=2000):
        print(joints)
        self.Arm.Arm_serial_servo_write6(joints[0],joints[1],joints[2],joints[3],joints[4],joints[5],runtime)

    def pubArm(self, joints, id=1, angle=90.0, run_time=2000):
        armjoint = ArmJoint()
        armjoint.run_time = run_time
        if len(joints) != 0: armjoint.joints = joints
        else:
            armjoint.id = id
            armjoint.angle = angle
        self.pubPoint.publish(armjoint)

def main(args=None):
    rclpy.init(args=args)
    yolov11_grasp = Yolov11GraspNode()
    yolov11_grasp.pubArm(yolov11_grasp.init_joints)
    try:
        rclpy.spin(yolov11_grasp)
    except KeyboardInterrupt:
        pass
    finally:
        # 节点退出前保持设备安全：先停止传送带，再清理GPIO资源。
        # 这是stop_sorting.sh独立停止脉冲之外的第二层退出保护。
        print("[传送带] 分拣节点退出，发送停止信号...")
        try:
            yolov11_grasp.send_stop_conveyor()
            print("[传送带] 退出停止信号已发送")
        except Exception as e:
            print(f"[警告] 退出停止信号发送失败: {e}")

        # GPIO 清理
        print("[GPIO] 清理 GPIO 资源...")
        GPIO.output(BCM_STOP, GPIO.LOW)
        GPIO.output(BCM_START, GPIO.LOW)
        GPIO.cleanup()
        yolov11_grasp.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
