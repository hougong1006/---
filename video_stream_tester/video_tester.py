# -*- coding: utf-8 -*-
"""Independent MJPEG video-stream tester for the Jetson device."""

import time
import urllib.request
from collections import deque

from PyQt5.QtCore import Qt, QSettings, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class MjpegWorker(QThread):
    """Read an MJPEG stream and emit decoded JPEG frames and diagnostics."""

    frame_ready = pyqtSignal(object, int)
    state_changed = pyqtSignal(str, str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self._running = True
        self._stream = None

    def stop(self):
        self._running = False
        stream = self._stream
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass

    def run(self):
        self.state_changed.emit("connecting", "正在连接视频服务...")
        try:
            request = urllib.request.Request(
                self.url,
                headers={"User-Agent": "DOFBOT-MJPEG-Tester/1.0"},
            )
            self._stream = urllib.request.urlopen(request, timeout=5)
            status = getattr(self._stream, "status", 200)
            content_type = self._stream.headers.get("Content-Type", "unknown")
            self.state_changed.emit(
                "connected", f"HTTP {status}，Content-Type: {content_type}"
            )

            buffer = b""
            while self._running:
                chunk = self._stream.read(4096)
                if not chunk:
                    raise ConnectionError("视频服务已断开，未继续收到数据")
                buffer += chunk

                # Avoid unlimited memory growth if the stream contains no JPEG.
                if len(buffer) > 8 * 1024 * 1024:
                    buffer = buffer[-2 * 1024 * 1024:]

                while self._running:
                    start = buffer.find(b"\xff\xd8")
                    if start < 0:
                        break
                    end = buffer.find(b"\xff\xd9", start + 2)
                    if end < 0:
                        if start > 0:
                            buffer = buffer[start:]
                        break

                    jpeg = buffer[start:end + 2]
                    buffer = buffer[end + 2:]
                    image = QImage()
                    if image.loadFromData(jpeg, "JPG") and not image.isNull():
                        self.frame_ready.emit(image, len(jpeg))
                    else:
                        self.state_changed.emit(
                            "decode_error", "收到JPEG数据，但图像解码失败"
                        )
        except Exception as exc:
            if self._running:
                self.state_changed.emit("error", f"{type(exc).__name__}: {exc}")
        finally:
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass
            self._stream = None


class VideoTesterWindow(QMainWindow):
    """Standalone UI that only tests the MJPEG stream."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MJPEG视频流独立测试平台")
        self.resize(1280, 820)
        self.setMinimumSize(900, 620)

        self._settings = QSettings("DofbotPro", "VideoStreamTester")
        self._worker = None
        self._last_image = None
        self._frame_count = 0
        self._byte_count = 0
        self._frame_times = deque(maxlen=120)
        self._connected_at = None

        self._build_ui()

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(500)

    def _card(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame {background:#ffffff; border:none; border-radius:14px;}"
        )
        return frame

    def _build_ui(self):
        root = QWidget()
        root.setStyleSheet("background:#eef2f7;")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = self._card()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        title = QLabel("MJPEG视频流独立测试平台")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title.setStyleSheet("color:#172033;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        header_layout.addWidget(QLabel("设备IP："))
        saved_ip = self._settings.value("ip", "10.182.135.172")
        self.ip_edit = QLineEdit(saved_ip)
        self.ip_edit.setFixedWidth(170)
        self.ip_edit.setFont(QFont("Consolas", 11))
        header_layout.addWidget(self.ip_edit)

        header_layout.addWidget(QLabel("端口："))
        saved_port = self._settings.value("port", "8765")
        self.port_edit = QLineEdit(saved_port)
        self.port_edit.setFixedWidth(75)
        self.port_edit.setFont(QFont("Consolas", 11))
        header_layout.addWidget(self.port_edit)

        self.connect_button = QPushButton("连接视频")
        self.connect_button.clicked.connect(self.connect_stream)
        self.connect_button.setStyleSheet(
            "QPushButton{background:#4361ee;color:white;border:0;border-radius:7px;"
            "padding:8px 18px;font-weight:bold;}"
            "QPushButton:hover{background:#5873ef;}"
        )
        header_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.clicked.connect(self.disconnect_stream)
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.setStyleSheet(
            "QPushButton{background:#ef4444;color:white;border:0;border-radius:7px;"
            "padding:8px 18px;font-weight:bold;}"
            "QPushButton:disabled{background:#b9c0ca;}"
        )
        header_layout.addWidget(self.disconnect_button)
        layout.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(12)

        video_card = self._card()
        video_layout = QVBoxLayout(video_card)
        video_layout.setContentsMargins(12, 12, 12, 12)
        video_title = QLabel("实时视频画面")
        video_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        video_title.setStyleSheet("color:#1e293b;")
        video_layout.addWidget(video_title)

        self.video_label = QLabel("请输入设备IP和端口，然后点击“连接视频”")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setFont(QFont("Microsoft YaHei", 13))
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet(
            "background:#111827;color:#94a3b8;border-radius:10px;"
        )
        video_layout.addWidget(self.video_label, 1)
        body.addWidget(video_card, 4)

        info_card = self._card()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_title = QLabel("视频诊断信息")
        info_title.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        info_title.setStyleSheet("color:#1e293b;")
        info_layout.addWidget(info_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.value_labels = {}
        rows = [
            ("状态", "status", "未连接"),
            ("视频地址", "url", "--"),
            ("分辨率", "resolution", "--"),
            ("实时帧率", "fps", "0.0 FPS"),
            ("累计帧数", "frames", "0"),
            ("累计数据", "bytes", "0 KB"),
            ("运行时间", "elapsed", "00:00:00"),
            ("最近信息", "message", "等待连接"),
        ]
        for row, (name, key, initial) in enumerate(rows):
            name_label = QLabel(name)
            name_label.setStyleSheet("color:#64748b;")
            value_label = QLabel(initial)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setStyleSheet("color:#1e293b;font-weight:bold;")
            grid.addWidget(name_label, row, 0, Qt.AlignTop)
            grid.addWidget(value_label, row, 1)
            self.value_labels[key] = value_label
        grid.setColumnStretch(1, 1)
        info_layout.addLayout(grid)
        info_layout.addStretch()

        hint = QLabel(
            "本工具只访问MJPEG视频地址，不执行SSH连接、机械臂动作、"
            "传送带控制或检测统计。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "background:#eff6ff;color:#1d4ed8;border-radius:8px;padding:10px;"
        )
        info_layout.addWidget(hint)
        body.addWidget(info_card, 1)
        layout.addLayout(body, 1)

    def _stream_url(self):
        host = self.ip_edit.text().strip()
        port_text = self.port_edit.text().strip()
        if not host:
            raise ValueError("设备IP不能为空")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ValueError("端口必须在1到65535之间")
        return f"http://{host}:{port}/"

    def connect_stream(self):
        if self._worker and self._worker.isRunning():
            return
        try:
            url = self._stream_url()
        except Exception as exc:
            self._set_state("error", str(exc))
            return

        self._settings.setValue("ip", self.ip_edit.text().strip())
        self._settings.setValue("port", self.port_edit.text().strip())
        self._frame_count = 0
        self._byte_count = 0
        self._frame_times.clear()
        self._last_image = None
        self._connected_at = time.time()
        self.value_labels["url"].setText(url)
        self.value_labels["resolution"].setText("--")
        self.video_label.clear()
        self.video_label.setText("正在连接视频服务...")

        self._worker = MjpegWorker(url)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.state_changed.connect(self._set_state)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.ip_edit.setEnabled(False)
        self.port_edit.setEnabled(False)

    def disconnect_stream(self):
        worker = self._worker
        self._worker = None
        if worker:
            try:
                worker.frame_ready.disconnect(self._on_frame)
                worker.state_changed.disconnect(self._set_state)
            except Exception:
                pass
            worker.stop()
            worker.wait(3000)
        self._restore_controls()
        self._set_state("stopped", "已由用户断开视频")

    def _on_worker_finished(self):
        self._worker = None
        self._restore_controls()

    def _restore_controls(self):
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.ip_edit.setEnabled(True)
        self.port_edit.setEnabled(True)

    def _set_state(self, state, message):
        names = {
            "connecting": "正在连接",
            "connected": "已连接",
            "decode_error": "解码异常",
            "error": "连接失败",
            "stopped": "已断开",
        }
        colors = {
            "connecting": "#f59e0b",
            "connected": "#16a34a",
            "decode_error": "#f59e0b",
            "error": "#dc2626",
            "stopped": "#64748b",
        }
        self.value_labels["status"].setText(names.get(state, state))
        self.value_labels["status"].setStyleSheet(
            f"color:{colors.get(state, '#1e293b')};font-weight:bold;"
        )
        self.value_labels["message"].setText(message)
        if state == "error" and self._last_image is None:
            self.video_label.setText("视频连接失败\n\n" + message)

    def _on_frame(self, image, jpeg_bytes):
        self._last_image = image
        self._frame_count += 1
        self._byte_count += jpeg_bytes
        self._frame_times.append(time.time())
        self.value_labels["resolution"].setText(
            f"{image.width()} × {image.height()}"
        )
        self._display_image()

    def _display_image(self):
        if self._last_image is None:
            return
        pixmap = QPixmap.fromImage(self._last_image)
        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(scaled)

    def _refresh_stats(self):
        now = time.time()
        while self._frame_times and now - self._frame_times[0] > 2.0:
            self._frame_times.popleft()
        if len(self._frame_times) >= 2:
            span = self._frame_times[-1] - self._frame_times[0]
            fps = (len(self._frame_times) - 1) / span if span > 0 else 0.0
        else:
            fps = 0.0
        self.value_labels["fps"].setText(f"{fps:.1f} FPS")
        self.value_labels["frames"].setText(str(self._frame_count))
        self.value_labels["bytes"].setText(
            f"{self._byte_count / 1024 / 1024:.2f} MB"
        )
        if self._connected_at is not None:
            seconds = max(0, int(now - self._connected_at))
            self.value_labels["elapsed"].setText(
                f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._display_image()

    def closeEvent(self, event):
        self.disconnect_stream()
        event.accept()
