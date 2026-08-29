#!/usr/bin/env python
# coding: utf-8
# ============================================================
# 修改说明：
#   1. 去掉空格键手动触发，改为上电后自动开始检测
#   2. grasp_done 回调中自动重启下一轮检测（0.1秒延迟）
#   3. 支持重检测信号：Phase1停带后触发一次精确重检测
#   4. 未检测到目标时保持扫描（不停止）
#   5. 多帧投票：连续5帧检测，>=3帧一致才发布，防止误分类
# ============================================================
from collections import Counter
import rclpy
from rclpy.node import Node
import os
import time
import cv2
import numpy as np
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from std_msgs.msg import Float32, Bool, String
from dofbot_pro_yolov11.fps import FPS
from ultralytics import YOLO
from dofbot_pro_interface.msg import *
encoding = ['16UC1', '32FC1']

# ===== MJPEG 视频流服务（供上位机远程查看带检测框的画面） =====
_latest_frame_jpg = None       # 最新帧的 JPEG 字节
_frame_lock = threading.Lock()
MJPEG_PORT = 8765


class _MJPEGHandler(BaseHTTPRequestHandler):
    """Serve annotated YOLO frames as MJPEG stream for remote monitoring."""

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()
        try:
            while True:
                with _frame_lock:
                    jpg_bytes = _latest_frame_jpg
                if jpg_bytes is not None:
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpg_bytes)}\r\n'.encode())
                    self.wfile.write(b'\r\n')
                    self.wfile.write(jpg_bytes)
                    self.wfile.write(b'\r\n')
                time.sleep(0.066)  # ~15fps
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, format, *args):
        pass  # suppress HTTP logs


def _start_mjpeg_server():
    server = ThreadingHTTPServer(('0.0.0.0', MJPEG_PORT), _MJPEGHandler)
    server.serve_forever()


class Yolov11DetectNode(Node):
    def __init__(self):
        super().__init__('detect_node')

        self.pr_time = time.time()
        self.image_sub = self.create_subscription(ImageMsg, "/image_data", self.image_sub_callback, qos_profile=1)
        self.img = np.zeros((480, 640, 3), dtype=np.uint8)
        self.init_joints = [90.0, 113.0, 29.0, -18.0, 90.0, 30.0]
        self.pubPoint = self.create_publisher(ArmJoint, "TargetAngle", 10)
        self.pubDetect = self.create_publisher(Yolov11Detect, "Yolov11DetectInfo", 10)
        self.pub_SortFlag = self.create_publisher(Bool, 'sort_flag', 10)
        self.grasp_status_sub = self.create_subscription(Bool, 'grasp_done', self.GraspStatusCallback, qos_profile=1)
        self.redetect_sub = self.create_subscription(Bool, 'redetect_signal', self.RedetectCallback, qos_profile=1)
        self.largemodel_arm_done_pub = self.create_publisher(String, '/largemodel_arm_done', 1)
        self.start_flag = False
        self.yolo_model = YOLO("/home/jetson/dofbot_pro_ws/src/dofbot_pro_yolov11/dofbot_pro_yolov11/best.engine", task='detect')
        self.fps = FPS()

        # ===== 多帧投票参数 =====
        self.vote_buffer = []       # 投票缓冲区: [{'name': str, 'cx': float, 'cy': float}, ...]
        self.VOTE_FRAMES =15         # 累积帧数
        self.VOTE_THRESHOLD = 10     # 至少N帧一致才发布
        self.no_detect_count = 0    # 连续无检测帧计数
        self.MAX_NO_DETECT = 2      # 连续无检测超过此值则清空缓冲区
        # 只在相机正视区域内进行最终判定。工件从右向左运动，进入或
        # 离开画面时穿线孔容易因透视和凹槽遮挡产生误判。
        self.ROI_LEFT = 120
        self.ROI_RIGHT = 520
        # Standard parts pass through without grasping. Count one part after
        # VOTE_THRESHOLD confirmed frames, then wait until it leaves before rearming.
        self.standard_vote_count = 0
        self.standard_count_latched = False
        self.standard_absent_count = 0
        self.STANDARD_RELEASE_FRAMES = 3

        # 启动 MJPEG 视频流服务（供上位机远程查看带检测框的画面）
        threading.Thread(target=_start_mjpeg_server, daemon=True).start()
        self.get_logger().info(f"MJPEG 视频流服务已启动: http://0.0.0.0:{MJPEG_PORT}/")

        # 自动启动定时器：8秒后自动开始检测（等待其他节点就绪）
        self.auto_start_timer = self.create_timer(8.0, self.auto_start_callback)
        self.get_logger().info(f"YOLOv11 检测节点初始化完成，8秒后自动开始检测（多帧投票: {self.VOTE_FRAMES}帧/{self.VOTE_THRESHOLD}票）...")

    def auto_start_callback(self):
        """上电后自动开始检测，无需按空格"""
        self.auto_start_timer.cancel()
        self.get_logger().info(">>> 自动启动检测 <<<")
        start_flag = Bool()
        start_flag.data = True
        self.pub_SortFlag.publish(start_flag)
        self.start_flag = True

    def image_sub_callback(self, data):
        image = np.ndarray(shape=(data.height, data.width, data.channels), dtype=np.uint8, buffer=data.data)
        self.img[:, :, 0], self.img[:, :, 1], self.img[:, :, 2] = image[:, :, 2], image[:, :, 1], image[:, :, 0]

        results = self.yolo_model(self.img, save=False, verbose=False)
        annotated_frame = results[0].plot(
            labels=True,
            conf=False,
            boxes=True,
        )
        boxes = results[0].boxes
        key = cv2.waitKey(10)

        # 在视频流中标出有效判定区，便于现场调整边界。
        cv2.line(annotated_frame, (self.ROI_LEFT, 0),
                 (self.ROI_LEFT, 479), (0, 255, 255), 2)
        cv2.line(annotated_frame, (self.ROI_RIGHT, 0),
                 (self.ROI_RIGHT, 479), (0, 255, 255), 2)
        cv2.putText(annotated_frame, "ACTIVE ROI",
                    (self.ROI_LEFT + 8, 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 255), 2)

        detected_this_frame = False
        standard_seen_this_frame = False
        if boxes != [None] and self.start_flag == True:
            for box in boxes:
                x_min, y_min, x_max, y_max = map(int, box.xyxy[0])
                class_id = int(box.cls)
                confidence = float(box.conf)
                class_name = str(self.yolo_model.names[class_id])
                label = f"{self.yolo_model.names[class_id]} {confidence:.2f}"
                center_x = (x_min + x_max) // 2
                center_y = (y_min + y_max) // 2

                # 整个检测框必须位于有效区内。右侧刚进入或左侧即将离开时，
                # 只显示检测结果，不计数、不投票、不发送抓取坐标。
                box_in_roi = (x_min >= self.ROI_LEFT and
                              x_max <= self.ROI_RIGHT)
                if not box_in_roi:
                    cv2.putText(annotated_frame, label,
                                (x_min, max(18, y_min - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (128, 128, 128), 2)
                    cv2.putText(annotated_frame, "WAIT ROI",
                                (x_min, max(36, y_min + 12)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (0, 255, 255), 2)

                    # 工件从左侧离开有效区时，丢弃尚未完成的缺陷投票，
                    # 防止孔洞被凹槽侧壁遮挡后累积成错误抓取指令。
                    if (class_name == 'quexianketi' and
                            x_min < self.ROI_LEFT and self.vote_buffer):
                        self.get_logger().info(
                            f"[ROI重置] 目标离开左侧有效区，清空缺陷投票"
                            f"({len(self.vote_buffer)}帧)")
                        self.vote_buffer = []
                        self.no_detect_count = 0
                    continue

                if class_name == 'biaozhunketi':
                    standard_seen_this_frame = True
                    self.standard_absent_count = 0
                    if not self.standard_count_latched:
                        self.standard_vote_count += 1
                        if self.standard_vote_count >= self.VOTE_THRESHOLD:
                            self.get_logger().info('[COUNT] biaozhunketi')
                            self.standard_count_latched = True
                            self.standard_vote_count = 0
                    continue

                # Only defective parts enter voting, stop-belt and grasp flow.
                if class_name != 'quexianketi':
                    continue

                detected_this_frame = True
                self.no_detect_count = 0

                # ===== 多帧投票：累积检测结果 =====
                self.vote_buffer.append({
                    'name': class_name,
                    'cx': float(center_x),
                    'cy': float(center_y)
                })

                vote_info = f"[投票 {len(self.vote_buffer)}/{self.VOTE_FRAMES}] {class_name}"
                cv2.putText(annotated_frame, vote_info, (x_min, y_min - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 2)
                cv2.putText(annotated_frame, label, (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                if len(self.vote_buffer) >= self.VOTE_FRAMES:
                    # 投票：统计各类别出现次数
                    names = [v['name'] for v in self.vote_buffer]
                    counter = Counter(names)
                    most_common_name, count = counter.most_common(1)[0]

                    if count >= self.VOTE_THRESHOLD:
                        # 投票通过！使用最新位置 + 投票结果发布
                        self.get_logger().info(
                            f"[投票通过] {most_common_name} ({count}/{self.VOTE_FRAMES}) 投票详情: {dict(counter)}")
                        center = Yolov11Detect()
                        center.centerx = self.vote_buffer[-1]['cx']
                        center.centery = self.vote_buffer[-1]['cy']
                        center.result = most_common_name
                        self.pubDetect.publish(center)
                        self.start_flag = False
                        self.vote_buffer = []
                    else:
                        # 未达成共识，移除最旧的一帧继续
                        self.get_logger().info(
                            f"[投票未通过] 无共识 {dict(counter)}，滑动窗口继续...")
                        self.vote_buffer.pop(0)
                break

        if not standard_seen_this_frame:
            self.standard_absent_count += 1
            if self.standard_absent_count >= self.STANDARD_RELEASE_FRAMES:
                self.standard_count_latched = False
                self.standard_vote_count = 0

        # 未检测到目标时：连续无检测超过阈值则清空投票缓冲
        if not detected_this_frame and self.start_flag == True:
            self.no_detect_count += 1
            if self.no_detect_count > self.MAX_NO_DETECT and len(self.vote_buffer) > 0:
                self.get_logger().info(f"[投票重置] 连续{self.no_detect_count}帧无检测，清空投票缓冲({len(self.vote_buffer)}帧)")
                self.vote_buffer = []
                self.no_detect_count = 0

        cur_time = time.time()
        elapsed = cur_time - self.pr_time
        fps = str(int(1 / elapsed)) if elapsed > 0 else "0"
        self.pr_time = cur_time
        cv2.putText(annotated_frame, fps, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # 更新 MJPEG 视频流缓冲（供上位机远程查看）
        global _latest_frame_jpg
        _, _jpg_buf = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        with _frame_lock:
            _latest_frame_jpg = _jpg_buf.tobytes()

        # The annotated frame is displayed by the monitoring UI via MJPEG.

        # 保留空格键作为手动触发选项
        if key == 32:
            print("手动触发检测信号")
            start_flag = Bool()
            start_flag.data = True
            self.pub_SortFlag.publish(start_flag)
            self.start_flag = True

    def pub_arm(self, joints, id=6, angle=180.0, runtime=1500):
        arm_joint = ArmJoint()
        arm_joint.id = id
        arm_joint.angle = angle
        arm_joint.run_time = runtime
        arm_joint.joints = joints
        self.pubPoint.publish(arm_joint)

    def GraspStatusCallback(self, msg):
        """夹取完成 → 极短延迟后立即开始下一轮检测"""
        if msg.data == True:
            self.get_logger().info("夹取完成！0.1秒后开始下一轮检测...")
            self.restart_timer = self.create_timer(0.1, self._restart_detection)

    def RedetectCallback(self, msg):
        """Phase1停带后 → 立即重新启用检测，获取物体静止后的精确位置"""
        if msg.data == True:
            self.get_logger().info("[重检测] 收到信号，重新启用检测以获取精确位置")
            self.vote_buffer = []  # 清空投票，重新开始
            self.no_detect_count = 0
            self.start_flag = True

    def _restart_detection(self):
        """定时器回调：重启检测循环"""
        self.restart_timer.cancel()
        self.get_logger().info(">>> 开始下一轮检测 <<<")
        self.vote_buffer = []  # 新一轮检测，清空投票
        self.no_detect_count = 0
        start_flag = Bool()
        start_flag.data = True
        self.pub_SortFlag.publish(start_flag)
        self.start_flag = True


def main(args=None):
    rclpy.init(args=args)
    yolov11_detect = Yolov11DetectNode()
    yolov11_detect.pub_arm(yolov11_detect.init_joints)
    try:
        rclpy.spin(yolov11_detect)
    except KeyboardInterrupt:
        pass
    finally:
        yolov11_detect.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
