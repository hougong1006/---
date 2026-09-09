#!/usr/bin/env python3
"""Serve an existing ROS 2 depth topic to a Windows monitoring client."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


DEFAULT_LOG_FILES = (
    "/home/jetson/.ros/log/orbbec_depth_web.log",
    "/home/jetson/.ros/log/orbbec_depth_web_launcher.log",
    "/home/jetson/.ros/log/orbbec_depth_driver.log",
    "/home/jetson/.ros/log/orbbec_depth_display.log",
)


def depth_to_meters(raw_depth: np.ndarray) -> np.ndarray:
    depth_meters = raw_depth.astype(np.float32)
    if raw_depth.dtype == np.uint16:
        depth_meters *= 0.001  # Orbbec 16UC1 publishes millimetres.
    return depth_meters


def render_pseudocolor(
    raw_depth: np.ndarray, near_meters: float, far_meters: float, point: tuple[int, int] | None
) -> tuple[np.ndarray, float | None, tuple[int, int]]:
    depth_meters = depth_to_meters(raw_depth)
    valid = np.isfinite(depth_meters)
    valid &= depth_meters >= near_meters
    valid &= depth_meters <= far_meters

    normalized = np.zeros(depth_meters.shape, dtype=np.uint8)
    normalized[valid] = np.clip(
        (depth_meters[valid] - near_meters) * 255.0 / (far_meters - near_meters),
        0,
        255,
    ).astype(np.uint8)

    image = cv2.applyColorMap(255 - normalized, cv2.COLORMAP_JET)
    image = cv2.addWeighted(image, 0.32, np.full_like(image, 255), 0.68, 0)
    image[~valid] = (0, 0, 0)

    height, width = depth_meters.shape[:2]
    if point is None:
        point_x, point_y = width // 2, height // 2
    else:
        point_x = min(max(point[0], 0), width - 1)
        point_y = min(max(point[1], 0), height - 1)

    samples = depth_meters[
        max(0, point_y - 2):min(height, point_y + 3),
        max(0, point_x - 2):min(width, point_x + 3),
    ]
    samples = samples[np.isfinite(samples)]
    samples = samples[(samples >= near_meters) & (samples <= far_meters)]
    distance = float(np.median(samples)) if samples.size else None

    cv2.drawMarker(image, (point_x, point_y), (255, 255, 255), cv2.MARKER_CROSS, 24, 2)
    cv2.drawMarker(image, (point_x, point_y), (0, 0, 0), cv2.MARKER_CROSS, 18, 1)
    label = "Distance: no valid depth" if distance is None else f"Distance: {distance:.2f} m"
    cv2.rectangle(image, (10, 10), (410, 58), (0, 0, 0), -1)
    cv2.putText(image, label, (20, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return image, distance, (point_x, point_y)


class DepthWebViewer(Node):
    def __init__(
        self,
        topic: str,
        color_topic: str,
        near_meters: float,
        far_meters: float,
        max_fps: float,
        idle_timeout: float,
    ) -> None:
        super().__init__("depth_web_viewer")
        self.bridge = CvBridge()
        self.topic = topic
        self.color_topic = color_topic
        self.near_meters = near_meters
        self.far_meters = far_meters
        self.minimum_interval = 1.0 / max_fps
        self.idle_timeout = idle_timeout
        self.lock = threading.Lock()
        self.shutdown_requested = threading.Event()
        self.last_client_monotonic = time.monotonic()
        self.jpeg: bytes | None = None
        self.color_jpeg: bytes | None = None
        self.frame_sequence = 0
        self.color_frame_sequence = 0
        self.frame_count = 0
        self.color_frame_count = 0
        self.point: tuple[int, int] | None = None
        self.last_distance: float | None = None
        self.last_point: tuple[int, int] | None = None
        self.last_shape: tuple[int, int] | None = None
        self.last_color_shape: tuple[int, int] | None = None
        self.last_frame_monotonic: float | None = None
        self.last_frame_utc: str | None = None
        self.last_error: str | None = None
        self.last_color_error: str | None = None
        self.last_encode_monotonic = 0.0
        self.last_color_encode_monotonic = 0.0
        self.create_subscription(Image, topic, self.on_depth, qos_profile_sensor_data)
        self.create_subscription(Image, color_topic, self.on_color, qos_profile_sensor_data)
        self.get_logger().info(f"Waiting for depth topic: {topic}")
        self.get_logger().info(f"Waiting for RGB topic: {color_topic}")

    def set_point(self, x: int, y: int) -> None:
        with self.lock:
            self.point = (x, y)

    def touch_client(self) -> None:
        with self.lock:
            self.last_client_monotonic = time.monotonic()

    def idle_seconds(self) -> float:
        with self.lock:
            return time.monotonic() - self.last_client_monotonic

    def get_frame(self) -> tuple[bytes | None, int]:
        with self.lock:
            return self.jpeg, self.frame_sequence

    def get_color_frame(self) -> tuple[bytes | None, int]:
        with self.lock:
            return self.color_jpeg, self.color_frame_sequence

    def get_status(self) -> dict:
        with self.lock:
            frame_age = None
            if self.last_frame_monotonic is not None:
                frame_age = round(max(0.0, time.monotonic() - self.last_frame_monotonic), 3)
            width, height = (None, None) if self.last_shape is None else self.last_shape
            color_width, color_height = (None, None) if self.last_color_shape is None else self.last_color_shape
            return {
                "topic": self.topic,
                "has_frame": self.jpeg is not None,
                "frame_count": self.frame_count,
                "frame_age_s": frame_age,
                "last_frame_utc": self.last_frame_utc,
                "center_or_selected_distance_m": None if self.last_distance is None else round(self.last_distance, 3),
                "selected_point": self.last_point,
                "display_range_m": {"near": self.near_meters, "far": self.far_meters},
                "image_width": width,
                "image_height": height,
                "last_error": self.last_error,
                "color": {
                    "topic": self.color_topic,
                    "has_frame": self.color_jpeg is not None,
                    "frame_count": self.color_frame_count,
                    "image_width": color_width,
                    "image_height": color_height,
                    "last_error": self.last_color_error,
                },
            }

    def on_depth(self, message: Image) -> None:
        now = time.monotonic()
        if now - self.last_encode_monotonic < self.minimum_interval:
            return
        try:
            raw_depth = self.bridge.imgmsg_to_cv2(message, desired_encoding="passthrough")
            with self.lock:
                point = self.point
            image, distance, sampled_point = render_pseudocolor(
                raw_depth, self.near_meters, self.far_meters, point
            )
            encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not encoded:
                raise RuntimeError("OpenCV could not encode the pseudocolor JPEG")
            with self.lock:
                self.jpeg = jpeg.tobytes()
                self.frame_sequence += 1
                self.frame_count += 1
                self.last_distance = distance
                self.last_point = sampled_point
                self.last_shape = (int(image.shape[1]), int(image.shape[0]))
                self.last_frame_monotonic = now
                self.last_frame_utc = datetime.now(timezone.utc).isoformat()
                self.last_error = None
                self.last_encode_monotonic = now
        except Exception as error:
            message_text = str(error)
            with self.lock:
                self.last_error = message_text
            self.get_logger().error(f"Could not process one depth frame: {message_text}")

    def on_color(self, message: Image) -> None:
        now = time.monotonic()
        if now - self.last_color_encode_monotonic < self.minimum_interval:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not encoded:
                raise RuntimeError("OpenCV could not encode the RGB JPEG")
            with self.lock:
                self.color_jpeg = jpeg.tobytes()
                self.color_frame_sequence += 1
                self.color_frame_count += 1
                self.last_color_shape = (int(image.shape[1]), int(image.shape[0]))
                self.last_color_error = None
                self.last_color_encode_monotonic = now
        except Exception as error:
            message_text = str(error)
            with self.lock:
                self.last_color_error = message_text
            self.get_logger().error(f"Could not process one RGB frame: {message_text}")


def read_tail(path: Path, max_bytes: int) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            length = handle.tell()
            handle.seek(max(length - max_bytes, 0), os.SEEK_SET)
            payload = handle.read()
        return payload.decode("utf-8", errors="replace")
    except OSError as error:
        return f"[unavailable] {error}"


def make_handler(viewer: DepthWebViewer, log_files: tuple[Path, ...]):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args) -> None:
            return

        def send_json(self, payload: dict, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def send_jpeg(self, frame: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(frame)

        def do_GET(self) -> None:
            request = urlparse(self.path)
            if request.path == "/status.json":
                viewer.touch_client()
                self.send_json(viewer.get_status())
                return

            if request.path == "/logs":
                viewer.touch_client()
                values = parse_qs(request.query)
                try:
                    requested_bytes = int(values.get("bytes", ["48000"])[0])
                except ValueError:
                    requested_bytes = 48000
                max_bytes = min(max(requested_bytes, 1024), 131072)
                self.send_json(
                    {
                        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "sources": [
                            {"name": log_file.name, "text": read_tail(log_file, max_bytes)}
                            for log_file in log_files
                        ],
                    }
                )
                return

            if request.path == "/point":
                viewer.touch_client()
                values = parse_qs(request.query)
                try:
                    viewer.set_point(int(values["x"][0]), int(values["y"][0]))
                    self.send_json({"ok": True}, status=202)
                except (KeyError, ValueError):
                    self.send_json({"ok": False, "error": "x and y must be integers"}, status=400)
                return

            if request.path == "/snapshot.jpg":
                viewer.touch_client()
                frame, _sequence = viewer.get_frame()
                if frame is None:
                    self.send_json({"error": "Waiting for depth frames"}, status=503)
                else:
                    self.send_jpeg(frame)
                return

            if request.path == "/color.jpg":
                viewer.touch_client()
                frame, _sequence = viewer.get_color_frame()
                if frame is None:
                    self.send_json({"error": "Waiting for RGB frames"}, status=503)
                else:
                    self.send_jpeg(frame)
                return

            if request.path == "/stream.mjpg":
                viewer.touch_client()
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                previous_sequence = -1
                try:
                    while rclpy.ok() and not viewer.shutdown_requested.is_set():
                        frame, sequence = viewer.get_frame()
                        if frame is not None and sequence != previous_sequence:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                            self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                            self.wfile.write(frame + b"\r\n")
                            previous_sequence = sequence
                        time.sleep(0.01)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    return
                return

            if request.path == "/shutdown":
                viewer.touch_client()
                viewer.shutdown_requested.set()
                self.send_json({"ok": True})
                return

            self.send_json({"error": "Not found"}, status=404)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orbbec depth web monitor service.")
    parser.add_argument("--topic", default=os.environ.get("DEPTH_WEB_TOPIC", "/camera/depth/image_raw"))
    parser.add_argument("--color-topic", default=os.environ.get("DEPTH_WEB_COLOR_TOPIC", "/camera/color/image_raw"))
    parser.add_argument("--host", default=os.environ.get("DEPTH_WEB_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DEPTH_WEB_PORT", "8766")))
    parser.add_argument("--near", type=float, default=0.20)
    parser.add_argument("--far", type=float, default=3.00)
    parser.add_argument("--max-fps", type=float, default=10.0)
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=0.0,
        help="Stop the service after this many seconds without a client; 0 disables the timeout.",
    )
    parser.add_argument("--log-file", action="append", default=None)
    return parser.parse_args()


def resolve_log_files(arguments: argparse.Namespace) -> tuple[Path, ...]:
    configured = arguments.log_file
    if not configured:
        configured = [item for item in os.environ.get("DEPTH_WEB_LOG_FILES", "").split(":") if item]
    if not configured:
        configured = list(DEFAULT_LOG_FILES)
    unique_paths: list[Path] = []
    for item in configured:
        path = Path(item)
        if path not in unique_paths:
            unique_paths.append(path)
    return tuple(unique_paths)


def main() -> None:
    arguments = parse_args()
    if arguments.near <= 0 or arguments.far <= arguments.near:
        raise SystemExit("--near must be positive and less than --far")
    if not 1 <= arguments.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if arguments.max_fps <= 0:
        raise SystemExit("--max-fps must be positive")
    if arguments.idle_timeout < 0:
        raise SystemExit("--idle-timeout must be zero or positive")

    rclpy.init()
    viewer = DepthWebViewer(
        arguments.topic,
        arguments.color_topic,
        arguments.near,
        arguments.far,
        arguments.max_fps,
        arguments.idle_timeout,
    )
    server = ThreadingHTTPServer((arguments.host, arguments.port), make_handler(viewer, resolve_log_files(arguments)))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="depth-web-http", daemon=True).start()
    print(
        "Depth monitor service listening on "
        f"http://{arguments.host}:{arguments.port}; depth={arguments.topic}; color={arguments.color_topic}",
        flush=True,
    )
    try:
        while rclpy.ok() and not viewer.shutdown_requested.is_set():
            rclpy.spin_once(viewer, timeout_sec=0.2)
            if arguments.idle_timeout and viewer.idle_seconds() >= arguments.idle_timeout:
                viewer.get_logger().info(
                    f"No desktop client for {arguments.idle_timeout:.0f} seconds; stopping depth monitor service."
                )
                break
    finally:
        server.shutdown()
        server.server_close()
        viewer.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
