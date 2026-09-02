#!/usr/bin/env python
# coding: utf-8
# ============================================================
# 修改说明：
#   1. 去掉空格键手动触发，改为上电后自动开始检测
#   2. grasp_done 回调中自动重启下一轮检测（0.1秒延迟）
#   3. 支持重检测信号：Phase1停带后触发一次精确重检测
#   4. 未检测到目标时保持扫描（不停止）
#   5. 缺陷件使用15帧/10票确认；标准件使用多目标跟踪过线计数
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
        self.DEFECT_TRACK_MAX_DISTANCE = 90
        self.last_defect_center = None
        self.redetect_reference = None
        # 只在相机正视区域内进行最终判定。工件从右向左运动，进入或
        # 离开画面时穿线孔容易因透视和凹槽遮挡产生误判。
        self.ROI_LEFT = 120
        self.ROI_RIGHT = 520
        # 标准件不抓取，使用中心点跟踪并在越过计数线时计数。每条轨迹只
        # 计数一次，可同时处理托盘上的多个工件，也不会因检测框闪烁重复计数。
        self.STANDARD_CONFIRM_FRAMES = 3
        self.STANDARD_COUNT_LINE_X = 320
        self.STANDARD_TRACK_MAX_DISTANCE = 70
        self.STANDARD_TRACK_MAX_MISSED = 8
        self.standard_tracks = {}
        self.next_standard_track_id = 1

        # 启动 MJPEG 视频流服务（供上位机远程查看带检测框的画面）
        threading.Thread(target=_start_mjpeg_server, daemon=True).start()
        self.get_logger().info(f"MJPEG 视频流服务已启动: http://0.0.0.0:{MJPEG_PORT}/")

        # 自动启动定时器：8秒后自动开始检测（等待其他节点就绪）
        self.auto_start_timer = self.create_timer(8.0, self.auto_start_callback)
        self.get_logger().info(f"YOLOv11 检测节点初始化完成，8秒后自动开始检测（多帧投票: {self.VOTE_FRAMES}帧/{self.VOTE_THRESHOLD}票）...")

    def _update_standard_tracks(self, detections):
        """Track all standard parts and emit one count when each crosses the line."""
        for track in self.standard_tracks.values():
            track['missed'] += 1

        candidates = []
        max_distance_sq = self.STANDARD_TRACK_MAX_DISTANCE ** 2
        for detection_index, (cx, cy) in enumerate(detections):
            for track_id, track in self.standard_tracks.items():
                distance_sq = ((cx - track['cx']) ** 2 +
                               (cy - track['cy']) ** 2)
                if distance_sq <= max_distance_sq:
                    candidates.append((distance_sq, detection_index, track_id))

        matched_detections = set()
        matched_tracks = set()
        for _, detection_index, track_id in sorted(candidates):
            if (detection_index in matched_detections or
                    track_id in matched_tracks):
                continue
            cx, cy = detections[detection_index]
            track = self.standard_tracks[track_id]
            track['cx'] = cx
            track['cy'] = cy
            track['hits'] += 1
            track['missed'] = 0
            if cx > self.STANDARD_COUNT_LINE_X:
                track['seen_right'] = True
            matched_detections.add(detection_index)
            matched_tracks.add(track_id)

        for detection_index, (cx, cy) in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track_id = self.next_standard_track_id
            self.next_standard_track_id += 1
            self.standard_tracks[track_id] = {
                'cx': cx,
                'cy': cy,
                'hits': 1,
                'missed': 0,
                'seen_right': cx > self.STANDARD_COUNT_LINE_X,
                'counted': False,
            }

        stale_track_ids = [
            track_id for track_id, track in self.standard_tracks.items()
            if track['missed'] > self.STANDARD_TRACK_MAX_MISSED
        ]
        for track_id in stale_track_ids:
            del self.standard_tracks[track_id]

        for track_id, track in self.standard_tracks.items():
            if (track['missed'] == 0 and not track['counted'] and
                    track['hits'] >= self.STANDARD_CONFIRM_FRAMES and
                    track['seen_right'] and
                    track['cx'] <= self.STANDARD_COUNT_LINE_X):
                self.get_logger().info(
                    f"[COUNT] biaozhunketi track={track_id} "
                    f"hits={track['hits']}")
                track['counted'] = True

    def _select_defect_candidate(self, candidates):
        """Select one spatially consistent defect from a multi-object tray."""
        if not candidates:
            return None

        if self.vote_buffer:
            reference_x = self.vote_buffer[-1]['cx']
            reference_y = self.vote_buffer[-1]['cy']
        elif self.redetect_reference is not None:
            reference_x, reference_y = self.redetect_reference
        else:
            roi_center_x = (self.ROI_LEFT + self.ROI_RIGHT) / 2.0
            return min(
                candidates,
                key=lambda item: (abs(item['cx'] - roi_center_x),
                                  -item['confidence']))

        selected = min(
            candidates,
            key=lambda item: ((item['cx'] - reference_x) ** 2 +
                              (item['cy'] - reference_y) ** 2))
        distance_sq = ((selected['cx'] - reference_x) ** 2 +
                       (selected['cy'] - reference_y) ** 2)
        if distance_sq > self.DEFECT_TRACK_MAX_DISTANCE ** 2:
            return None
        return selected

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
        standard_detections = []
        defect_candidates = []
        scan_active = self.start_flag
        if boxes != [None] and scan_active:
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

                    continue

                if class_name == 'biaozhunketi':
                    standard_detections.append(
                        (float(center_x), float(center_y)))
                    continue

                # Only defective parts enter voting, stop-belt and grasp flow.
                if class_name != 'quexianketi':
                    continue

                defect_candidates.append({
                    'name': class_name,
                    'cx': float(center_x),
                    'cy': float(center_y),
                    'confidence': confidence,
                    'x_min': x_min,
                    'y_min': y_min,
                })

        if scan_active:
            self._update_standard_tracks(standard_detections)

            # 托盘内可能同时存在多个缺陷件。每帧只选择一个与上一帧位置
            # 连续的目标投票，其他目标和ROI外目标不能清空当前目标的缓冲。
            selected_defect = self._select_defect_candidate(defect_candidates)
            if selected_defect is not None:
                detected_this_frame = True
                self.no_detect_count = 0
                self.vote_buffer.append({
                    'name': selected_defect['name'],
                    'cx': selected_defect['cx'],
                    'cy': selected_defect['cy'],
                })

                vote_info = (
                    f"[投票 {len(self.vote_buffer)}/{self.VOTE_FRAMES}] "
                    f"{selected_defect['name']}")
                cv2.putText(
                    annotated_frame, vote_info,
                    (selected_defect['x_min'], selected_defect['y_min'] - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 2)

                if len(self.vote_buffer) >= self.VOTE_FRAMES:
                    names = [v['name'] for v in self.vote_buffer]
                    counter = Counter(names)
                    most_common_name, count = counter.most_common(1)[0]

                    if count >= self.VOTE_THRESHOLD:
                        latest = self.vote_buffer[-1]
                        self.get_logger().info(
                            f"[投票通过] {most_common_name} "
                            f"({count}/{self.VOTE_FRAMES}) "
                            f"投票详情: {dict(counter)}")
                        center = Yolov11Detect()
                        center.centerx = latest['cx']
                        center.centery = latest['cy']
                        center.result = most_common_name
                        self.last_defect_center = (
                            latest['cx'], latest['cy'])
                        self.pubDetect.publish(center)
                        self.start_flag = False
                        self.vote_buffer = []
                    else:
                        self.get_logger().info(
                            f"[投票未通过] 无共识 {dict(counter)}，"
                            "滑动窗口继续...")
                        self.vote_buffer.pop(0)

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
            self.redetect_reference = self.last_defect_center
            self.start_flag = True

    def _restart_detection(self):
        """定时器回调：重启检测循环"""
        self.restart_timer.cancel()
        self.get_logger().info(">>> 开始下一轮检测 <<<")
        self.vote_buffer = []  # 新一轮检测，清空投票
        self.no_detect_count = 0
        self.redetect_reference = None
        self.last_defect_center = None
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
