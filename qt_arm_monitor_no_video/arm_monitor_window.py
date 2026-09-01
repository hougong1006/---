# -*- coding: utf-8 -*-
"""Arm Monitor Window - Cyber Style Chinese UI with SSH Log"""
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QGroupBox, QGridLayout, QTextEdit,
    QPushButton, QLineEdit, QSplitter, QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import (QFont, QTextCursor,
                          QPainter, QColor, QPen, QLinearGradient)
import base64 as _b64
import paramiko
import re
import os
import sys
import time
import math
import html as _html
import json
import subprocess
import yaml
import threading
from datetime import datetime
from collections import deque

import matplotlib
matplotlib.use('Qt5Agg')
# Cross-platform font: Windows uses Microsoft YaHei, Linux uses WenQuanYi/Noto
if sys.platform == 'linux':
    matplotlib.rcParams['font.sans-serif'] = [
        'Noto Sans CJK JP', 'Droid Sans Fallback', 'DejaVu Sans']
else:
    matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# Cross-platform preferred font name
_FONT = ('Noto Sans CJK JP' if sys.platform == 'linux' else 'Microsoft YaHei')
# Detect if running locally on Jetson (Linux)
_IS_LOCAL = sys.platform == 'linux'
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

def _t(s):
    return _b64.b64decode(s).decode('utf-8')

# All Chinese strings decoded at runtime (avoids Windows encoding issues)
_TX = {
    'TITLE': _t('5aOz5L2T6KGo6Z2i57y66Zm35pm66IO95YiG5ouj57O757uf5Y+v6KeG5YyW55uR5o6n5bmz5Y+w'),
    'BTN_LAUNCH': _t('5LiA6ZSu5ZCv5Yqo'),
    'BTN_STOP_SYS': _t('5YGc5q2i57O757uf'),
    'LAUNCHING': _t('5ZCv5Yqo5Lit77yM6K+356iN5YCZLi4u'),
    'STOPPING': _t('5YGc5q2i5Lit77yM6K+356iN5YCZLi4u'),
    'LAUNCHED': _t('5YiG5ouj57O757uf5bey5ZCv5Yqo'),
    'SYS_STOPPED': _t('57O757uf5bey5YGc5q2i'),
    'LAUNCH_ERR': _t('5ZCv5Yqo5aSx6LSl'),
    'JOINTS': _t('44CQIOWFs+iKguinkuW6piDjgJE='),
    'GRASP': _t('44CQIOaKk+WPlueKtuaAgSDjgJE='),
    'OFFSET': _t('44CQIOWBj+enu+mHj+mFjee9riDjgJE='),
    'LOG': _t('44CQIOWunuaXtuaXpeW/lyDjgJE='),
    'J1': _t('5YWz6IqCMSAo5bqV5bqn5peL6L2sKQ=='),
    'J2': _t('5YWz6IqCMiAo6IKp6YOoKQ=='),
    'J3': _t('5YWz6IqCMyAo6IKY6YOoKQ=='),
    'J4': _t('5YWz6IqCNCAo6IWV6YOoKQ=='),
    'J5': _t('5YWz6IqCNSAo5omL6IWV5peL6L2sKQ=='),
    'J6': _t('5YWz6IqCNiAo5aS554iqKQ=='),
    'OBJ': _t('5qOA5rWL54mp5L2TOg=='),
    '3D': _t('M0TlnZDmoIc6'),
    'STS': _t('5YiG5ouj54q25oCBOg=='),
    'CVR': _t('5Lyg6YCB5bimOg=='),
    'IDLE': _t('562J5b6F5Lit'),
    'DET': _t('5qOA5rWL5Yiw55uu5qCH'),
    'GRAB': _t('5q2j5Zyo5oqT5Y+W'),
    'DONE': _t('5oqT5Y+W5a6M5oiQ'),
    'RUN': _t('6L+Q6KGM5Lit'),
    'STOP': _t('5bey5YGc5q2i'),
    'SYS': _t('57O757uf5ZCv5Yqo77yM562J5b6F6L+e5o6lLi4u'),
    'STAT': _t('44CQIOajgOa1i+e7n+iuoSDjgJE='),
    'CUR_OBJ': _t('5b2T5YmN5qOA5rWLOg=='),
    'TOTAL': _t('57Sv6K6h5qOA5rWLOg=='),
    'RIPE': _t('5qCH5YeG5Lu2Og=='),
    'GREEN': _t('6Z2S6YeR5qmYOg=='),
    'ROTTEN': _t('57y66Zm35Lu2Og=='),
    'ANALYSIS': _t('44CQIOWTgei0qOWIhuaekCDjgJE='),
    'RIPE_RATE': _t('5qCH5YeG546HOg=='),
    'GREEN_RATE': _t('6Z2S5p6c546HOg=='),
    'ROT_RATE': _t('57y66Zm3546HOg=='),
    'QUALITY': _t('57u85ZCI5ZOB6LSoOg=='),
    'Q_EXCELLENT': _t('5LyY56eA'),
    'Q_GOOD': _t('6Imv5aW9'),
    'Q_FAIR': _t('5LiA6Iis'),
    'Q_POOR': _t('6L6D5beu'),
    'NO_DATA': _t('5pqC5peg5pWw5o2u'),
    'EFFICIENCY': _t('44CQIOWIhuaLo+aViOeOhyDjgJE='),
    'SORT_SPEED': _t('5YiG5ouj6YCf5bqmOg=='),
    'AVG_TIME': _t('5bmz5Z2H6ICX5pe2Og=='),
    'UPTIME': _t('6L+Q6KGM5pe26ZW/Og=='),
    'TOTAL_SORT': _t('5bey5YiG5oujOg=='),
    'PER_MIN': _t('5LiqL+WIhumSnw=='),
    'SEC_EACH': _t('56eSL+S4qg=='),
    'PIE_TITLE': _t('5ZOB6LSo5YiG5biD'),
    'CAMERA': _t('44CQIOaRhOWDj+WktOeUu+mdoiDjgJE='),
    'ARM3D': _t('44CQIDNE5py65qKw6IeCIOOAkQ=='),
    'WAIT_CAM': _t('562J5b6F55S76Z2iLi4u'),
    'CAM_ERR': _t('6L+e5o6l5aSx6LSl'),
    'OFFLINE': _t('5pyq6L+e5o6l'),
    'CONNECTING': _t('5q2j5Zyo6L+e5o6lLi4u'),
    'ONLINE': _t('5bey6L+e5o6l'),
    'CONN_ERR': _t('6L+e5o6l5aSx6LSl'),
    'BTN_CONN': _t('6L+e5o6l6K6+5aSH'),
    'BTN_DISC': _t('5pat5byA6L+e5o6l'),
    'CTRL': _t('44CQIOWPguaVsOaOp+WItiDjgJE='),
    'CONF_LBL': _t('572u5L+h5bqmOg=='),
    'DET_CTRL_LBL': _t('5qOA5rWL5o6n5Yi2Og=='),
    'DET_PAUSE': _t('5pqC5YGc5qOA5rWL'),
    'DET_RESUME': _t('5oGi5aSN5qOA5rWL'),
    'GRIP_LBL': _t('5aS554iq5Yqb5bqmOg=='),
    'DET_RUNNING': _t('6L+Q6KGM5Lit'),
    'DET_PAUSED': _t('5bey5pqC5YGc'),
}

STYLE_SHEET = """
QMainWindow {
    background-color: #f0f2f5;
}
QWidget#centralWidget {
    background-color: #f0f2f5;
}
QLabel {
    color: #3d4f5f;
    background: transparent;
}
QTextEdit {
    background-color: #ffffff;
    color: #2d3748;
    border: 1px solid #e4e8ee;
    border-radius: 8px;
    padding: 6px;
    font-size: 11px;
}
QLineEdit {
    background-color: rgba(255,255,255,0.92);
    color: #2d3748;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 5px 10px;
}
QPushButton {
    background: #4361ee;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background: #5a7bff;
}
QPushButton:pressed {
    background: #3a52d4;
}
QPushButton:disabled {
    background-color: #c1c8d1;
    color: #8a95a5;
}
"""


class LocalLogWorker(QThread):
    """Background thread: locally tail -F log files (for running on Jetson itself)."""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, log_files):
        super().__init__()
        self.log_files = log_files  # space-separated file paths
        self._running = True
        self._proc = None

    def run(self):
        cmd = f'tail -n 50 -F {self.log_files}'
        try:
            self._proc = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace'
            )
            self.status_signal.emit('connected')
            for line in self._proc.stdout:
                if not self._running:
                    break
                line = line.rstrip()
                if line:
                    self.log_signal.emit(line)
        except Exception as e:
            self.status_signal.emit(f'error:{e}')
            return
        self.status_signal.emit('disconnected')

    def stop(self):
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass


class SSHCmdWorker(QThread):
    """Background thread: run a command over SSH, stream stdout/stderr to log."""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)  # 'started' / 'finished' / 'error:xxx'

    def __init__(self, host, user, password, cmd):
        super().__init__()
        self.host = host
        self.user = user
        self.password = password
        self.cmd = cmd
        self._running = True

    @staticmethod
    def _decode_line(data: bytes) -> str:
        """Try UTF-8 first, fall back to GBK for legacy scripts."""
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            return data.decode('gbk', errors='replace')

    def run(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(self.host, username=self.user,
                           password=self.password, timeout=8)
        except Exception as e:
            self.status_signal.emit(f'error:{e}')
            return

        try:
            transport = client.get_transport()
            channel = transport.open_session()
            channel.get_pty()  # allocate pseudo-tty so sudo prompts work
            channel.exec_command(self.cmd)
            channel.settimeout(1.0)
            byte_buf = b''
            while self._running:
                try:
                    data = channel.recv(4096)
                    if not data:
                        break
                    byte_buf += data
                    while b'\n' in byte_buf:
                        line_bytes, byte_buf = byte_buf.split(b'\n', 1)
                        line = self._decode_line(line_bytes).strip()
                        if line:
                            self.log_signal.emit(line)
                except Exception:
                    if channel.exit_status_ready():
                        break
            self.status_signal.emit('finished')
        except Exception as e:
            self.status_signal.emit(f'error:{e}')
        finally:
            client.close()

    def stop(self):
        self._running = False


class LocalCmdWorker(QThread):
    """Background thread: run a shell command locally (for Jetson local mode)."""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self._proc = None
        self._running = True

    def run(self):
        try:
            self._proc = subprocess.Popen(
                self.cmd, shell=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace',
                start_new_session=True
            )
            self.status_signal.emit('started')
            for line in self._proc.stdout:
                line = line.rstrip()
                if line:
                    self.log_signal.emit(line)
                if not self._running:
                    break
            self._proc.wait()
            self.status_signal.emit('finished')
        except Exception as e:
            self.status_signal.emit(f'error:{e}')

    def stop(self):
        self._running = False
        if self._proc:
            try:
                import os, signal
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass


class SSHLogWorker(QThread):
    """Background thread: SSH into Jetson, tail -f sortation.log"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)  # 'connected' / 'disconnected' / 'error:xxx'

    def __init__(self, host, user, password, log_path):
        super().__init__()
        self.host = host
        self.user = user
        self.password = password
        self.log_path = log_path
        self._running = True

    def run(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(self.host, username=self.user,
                           password=self.password, timeout=8)
            self.status_signal.emit('connected')
        except Exception as e:
            self.status_signal.emit(f'error:{e}')
            return

        try:
            while self._running:
                transport = client.get_transport()
                if not transport or not transport.is_active():
                    break  # SSH connection truly lost
                cmd = f'tail -n 50 -F {self.log_path}'
                channel = transport.open_session()
                channel.exec_command(cmd)
                channel.settimeout(1.0)

                byte_buf = b''
                while self._running:
                    try:
                        data = channel.recv(4096)
                        if not data:
                            break  # tail exited, will retry
                        byte_buf += data
                        while b'\n' in byte_buf:
                            line_bytes, byte_buf = byte_buf.split(b'\n', 1)
                            try:
                                line = line_bytes.decode('utf-8').strip()
                            except UnicodeDecodeError:
                                line = line_bytes.decode('gbk', errors='replace').strip()
                            if line:
                                self.log_signal.emit(line)
                    except Exception:
                        pass
                # tail exited but we're still running → wait and retry
                if self._running:
                    time.sleep(2)
        except Exception as e:
            self.status_signal.emit(f'error:{e}')
        finally:
            client.close()
            if self._running:
                # Unexpected disconnection (SSH connection lost)
                self.status_signal.emit('disconnected')

    def stop(self):
        self._running = False


def _make_glow(widget, color='#00e5ff', radius=15):
    """Apply a neon glow (drop-shadow) effect to a widget."""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(radius)
    eff.setColor(QColor(color))
    eff.setOffset(0, 0)
    widget.setGraphicsEffect(eff)


class CyberGroupBox(QGroupBox):
    """GroupBox with subtle corner decorations."""

    def __init__(self, title='', parent=None):
        super().__init__(title, parent)
        self._corner_color = QColor('#3182ce')
        self._corner_len = 12

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._corner_color, 2)
        p.setPen(pen)
        w, h = self.width(), self.height()
        c = self._corner_len
        # Top-left
        p.drawLine(1, 1, c, 1); p.drawLine(1, 1, 1, c)
        # Top-right
        p.drawLine(w - 2, 1, w - c - 1, 1); p.drawLine(w - 2, 1, w - 2, c)
        # Bottom-left
        p.drawLine(1, h - 2, c, h - 2); p.drawLine(1, h - 2, 1, h - c - 1)
        # Bottom-right
        p.drawLine(w - 2, h - 2, w - c - 1, h - 2); p.drawLine(w - 2, h - 2, w - 2, h - c - 1)
        p.end()


class ScanLineOverlay(QWidget):
    """Transparent overlay with animated sweeping scan-line effect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._y = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def _tick(self):
        h = self.height()
        if h > 0:
            self._y = (self._y + 2) % (h + 80)
        self.update()

    def paintEvent(self, event):
        h = self.height()
        if h <= 0:
            return
        p = QPainter(self)
        # Sweeping cyan band
        band = 60
        top = self._y - band
        grad = QLinearGradient(0, top, 0, float(self._y))
        grad.setColorAt(0.0, QColor(0, 229, 255, 0))
        grad.setColorAt(0.5, QColor(0, 229, 255, 18))
        grad.setColorAt(1.0, QColor(0, 229, 255, 0))
        p.fillRect(0, max(0, top), self.width(), band, grad)
        # Subtle horizontal CRT scan lines
        pen = QPen(QColor(255, 255, 255, 6))
        p.setPen(pen)
        for y in range(0, h, 4):
            p.drawLine(0, y, self.width(), y)
        p.end()


class ArmMonitorWindow(QMainWindow):
    device_offsets_signal = pyqtSignal(float, float, float)
    device_offsets_error_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(_TX['TITLE'])
        self.setGeometry(100, 100, 1280, 800)
        self.setStyleSheet(STYLE_SHEET)

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        ml = QVBoxLayout(central)
        ml.setSpacing(12)
        ml.setContentsMargins(16, 12, 16, 16)

        # ===== Top Banner (Blue Header) =====
        banner = QWidget()
        banner.setFixedHeight(56)
        banner.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ffffff, stop:0.15 #f0f4ff, stop:0.5 #e8eeff, stop:0.85 #f0f4ff, stop:1 #ffffff);
            border-radius: 10px;
            border: 1px solid #dce3f0;
        """)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel(_TX['TITLE'])
        title.setFont(QFont(_FONT, 17, QFont.Bold))
        title.setStyleSheet("color: #2d3a5c; background: transparent; letter-spacing: 0px;")
        title.setAlignment(Qt.AlignCenter)
        banner_layout.addStretch()
        banner_layout.addWidget(title)
        banner_layout.addStretch()

        # Right side: IP + buttons
        ip_label = QLabel("IP:")
        ip_label.setFont(QFont(_FONT, 10))
        ip_label.setStyleSheet("color: #5a6a7e;")
        banner_layout.addWidget(ip_label)

        # Load saved IP or use default
        self._settings = QSettings('DofbotPro', 'ArmMonitor')
        saved_ip = self._settings.value('last_ip', '10.182.135.172')
        if saved_ip in ('10.229.42.172', '10.178.59.172',
                        '10.182.135.194', '192.168.8.88'):
            saved_ip = '10.182.135.172'
            self._settings.setValue('last_ip', saved_ip)
        self.ip_input = QLineEdit(saved_ip)
        self.ip_input.setFont(QFont("Consolas", 9))
        self.ip_input.setFixedWidth(220)
        self.ip_input.textChanged.connect(self._save_ip)
        banner_layout.addWidget(self.ip_input)

        self.btn_connect = QPushButton(_TX['BTN_CONN'])
        self.btn_connect.setFont(QFont(_FONT, 9))
        self.btn_connect.setStyleSheet("""
            QPushButton { background: #4361ee; color: white; border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background: #5a7bff; }
        """)
        self.btn_connect.clicked.connect(self._toggle_ssh)
        banner_layout.addWidget(self.btn_connect)

        self.label_conn_status = QLabel(_TX['OFFLINE'])
        self.label_conn_status.setFont(QFont(_FONT, 9))
        self.label_conn_status.setStyleSheet("color: #7a8a9e;")
        banner_layout.addWidget(self.label_conn_status)

        self.btn_launch = QPushButton(_TX['BTN_LAUNCH'])
        self.btn_launch.setFont(QFont(_FONT, 9))
        self.btn_launch.setStyleSheet("""
            QPushButton { background: #22c55e; color: white; border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background: #34d972; }
            QPushButton:disabled { background: #c1c8d1; color: #8a95a5; }
        """)
        self.btn_launch.setEnabled(False)
        self.btn_launch.clicked.connect(self._launch_system)
        banner_layout.addWidget(self.btn_launch)

        self.btn_stop_sys = QPushButton(_TX['BTN_STOP_SYS'])
        self.btn_stop_sys.setFont(QFont(_FONT, 9))
        self.btn_stop_sys.setStyleSheet("""
            QPushButton { background: #ef4444; color: white; border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background: #f87171; }
            QPushButton:disabled { background: #c1c8d1; color: #8a95a5; }
        """)
        self.btn_stop_sys.setEnabled(False)
        self.btn_stop_sys.clicked.connect(self._stop_system)
        banner_layout.addWidget(self.btn_stop_sys)

        self.label_sys_status = QLabel("")
        self.label_sys_status.setFont(QFont(_FONT, 8))
        self.label_sys_status.setStyleSheet("color: #7a8a9e;")
        # Removed from banner, will be placed elsewhere later

        ml.addWidget(banner)

        # ===== Helper: Create white card =====
        def make_card():
            from PyQt5.QtWidgets import QFrame
            w = QFrame()
            w.setFrameShape(QFrame.StyledPanel)
            w.setAutoFillBackground(True)
            pal = w.palette()
            pal.setColor(w.backgroundRole(), QColor(255, 255, 255))
            w.setPalette(pal)
            w.setStyleSheet("""
                QFrame {
                    background-color: #ffffff;
                    border-radius: 14px;
                    border: none;
                }
            """)
            shadow = QGraphicsDropShadowEffect(w)
            shadow.setBlurRadius(24)
            shadow.setColor(QColor(0, 0, 0, 22))
            shadow.setOffset(0, 2)
            w.setGraphicsEffect(shadow)
            return w

        def make_section_title(text, dot_color="#4361ee"):
            """Create a section title with colored dot indicator."""
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 6)
            hl.setSpacing(8)
            dot = QLabel("\u25cf")
            dot.setFont(QFont("Arial", 10))
            dot.setStyleSheet(f"color: {dot_color}; background: transparent;")
            dot.setFixedWidth(14)
            hl.addWidget(dot)
            lbl = QLabel(text)
            lbl.setFont(QFont(_FONT, 13, QFont.Bold))
            lbl.setStyleSheet("color: #1e293b; background: transparent;")
            hl.addWidget(lbl)
            hl.addStretch()
            return container

        # ===== MIDDLE AREA: 3-Column =====
        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        # ========== LEFT COLUMN ==========
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # --- Detection Statistics ---
        det_card = make_card()
        det_vl = QVBoxLayout(det_card)
        det_vl.setContentsMargins(16, 12, 16, 12)
        det_vl.addWidget(make_section_title("检测统计", "#4361ee"))
        det_grid = QGridLayout()
        det_grid.setSpacing(10)

        def make_mini_stat(title, color="#4361ee", icon_char="\u25a0"):
            w = QWidget()
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            w.setStyleSheet(f"""
                background: #f8f9fc;
                border-radius: 10px; border: 1px solid #eef0f5;
            """)
            vl = QVBoxLayout(w)
            vl.setContentsMargins(14, 12, 14, 12)
            vl.setSpacing(8)
            vl.addStretch(1)
            # Title row with icon
            title_row = QHBoxLayout()
            title_row.setSpacing(4)
            icon = QLabel(icon_char)
            icon.setFont(QFont("Arial", 9))
            icon.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            icon.setFixedWidth(14)
            title_row.addWidget(icon)
            t = QLabel(title)
            t.setFont(QFont(_FONT, 11))
            t.setStyleSheet("color: #7b8794; background: transparent; border: none;")
            title_row.addWidget(t)
            title_row.addStretch()
            vl.addLayout(title_row)
            v = QLabel("0")
            v.setFont(QFont(_FONT, 24, QFont.Bold))
            v.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            v.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            v.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            vl.addWidget(v)
            vl.addStretch(1)
            return w, v

        w1, self.label_total = make_mini_stat("检测总数", "#4361ee", "\u25c6")
        w2, self.label_ripe = make_mini_stat("标准件", "#22c55e", "\u25cf")
        w4, self.label_rotten = make_mini_stat("缺陷件", "#ef4444", "\u25cf")
        # Keep the legacy green counter for chart/log compatibility, but do not
        # expose it as a separate statistic tile.
        self.label_green = QLabel("0", det_card)
        self.label_green.hide()
        det_grid.addWidget(w1, 0, 0, 2, 1)
        det_grid.addWidget(w2, 0, 1)
        det_grid.addWidget(w4, 1, 1)
        det_vl.addLayout(det_grid, 1)
        left_col.addWidget(det_card, 1)

        # --- Quality Analysis (2x2 grid) ---
        qa_card = make_card()
        qa_vl = QVBoxLayout(qa_card)
        qa_vl.setContentsMargins(16, 12, 16, 12)
        qa_vl.addWidget(make_section_title("品质分析", "#8b5cf6"))
        qa_grid = QGridLayout()
        qa_grid.setSpacing(10)

        w5, self.label_ripe_rate = make_mini_stat("标准率", "#22c55e", "\u25b2")
        w7, self.label_rot_rate = make_mini_stat("缺陷率", "#ef4444", "\u25bc")
        w8, self.label_quality = make_mini_stat("综合品质", "#4361ee", "\u2605")
        # Keep the legacy green-rate value for analysis compatibility, but do
        # not expose it as a separate quality tile.
        self.label_green_rate = QLabel("--%", qa_card)
        self.label_green_rate.hide()
        self.label_ripe_rate.setText("--%")
        self.label_rot_rate.setText("--%")
        self.label_quality.setText("正常")
        qa_grid.addWidget(w5, 0, 0)
        qa_grid.addWidget(w7, 1, 0)
        qa_grid.addWidget(w8, 0, 1, 2, 1)
        qa_vl.addLayout(qa_grid, 1)
        left_col.addWidget(qa_card, 1)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        main_row.addWidget(left_widget, 1)  # equal stretch

        # ========== CENTER COLUMN: Video-free placeholder ==========
        center_col = QVBoxLayout()
        center_col.setSpacing(8)

        video_card = make_card()
        video_vl = QVBoxLayout(video_card)
        video_vl.setContentsMargins(14, 10, 14, 10)
        # Keep the original layout without creating an MJPEG connection.
        video_header = QHBoxLayout()
        video_header.setSpacing(8)
        cam_dot = QLabel("\u25cf")
        cam_dot.setFont(QFont("Arial", 10))
        cam_dot.setStyleSheet("color: #94a3b8; background: transparent;")
        cam_dot.setFixedWidth(14)
        video_header.addWidget(cam_dot)
        video_t = QLabel("缺陷检测显示区域")
        video_t.setFont(QFont(_FONT, 13, QFont.Bold))
        video_t.setStyleSheet("color: #1e293b; background: transparent;")
        video_header.addWidget(video_t)
        video_header.addStretch()
        online_badge = QLabel(" 未启用视频 ")
        online_badge.setFont(QFont(_FONT, 8, QFont.Bold))
        online_badge.setFixedHeight(20)
        online_badge.setStyleSheet(
            "background-color: #e2e8f0; color: #475569;"
            "border-radius: 10px; padding: 2px 10px;"
        )
        video_header.addWidget(online_badge)
        video_vl.addLayout(video_header)

        self.camera_label = QLabel(
            "无视频流版本\n\n"
            "设备控制、检测统计、运行状态和日志功能正常运行")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setFont(QFont(_FONT, 13))
        self.camera_label.setMinimumSize(360, 220)
        self.camera_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.camera_label.setStyleSheet("""
            background-color: #1a1f2e; color: #8b95a5;
            border: none; border-radius: 10px;
        """)
        self.camera_label.setWordWrap(True)
        video_vl.addWidget(self.camera_label, 1)
        center_col.addWidget(video_card, 1)

        center_widget = QWidget()
        center_widget.setLayout(center_col)
        main_row.addWidget(center_widget, 2)  # center gets more space

        # ========== RIGHT COLUMN ==========
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        # --- Device Status ---
        status_card = make_card()
        status_vl = QVBoxLayout(status_card)
        status_vl.setContentsMargins(18, 14, 18, 14)
        status_vl.setSpacing(10)
        status_vl.addWidget(make_section_title("设备运行状态", "#f59e0b"))

        def make_status_row(name):
            row_w = QWidget()
            row_w.setStyleSheet("background: #f8f9fc; border-radius: 10px; border: 1px solid #eef0f5;")
            row_w.setMinimumHeight(42)
            row_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            row = QHBoxLayout(row_w)
            row.setContentsMargins(14, 0, 14, 0)
            row.setSpacing(8)
            lbl = QLabel(name)
            lbl.setFont(QFont(_FONT, 11))
            lbl.setStyleSheet("color: #7b8794; background: transparent; border: none;")
            row.addWidget(lbl)
            val = QLabel("--")
            val.setFont(QFont(_FONT, 11, QFont.Bold))
            val.setStyleSheet("color: #2d3748; background: transparent; border: none;")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(val)
            return row_w, val

        r1, self.label_conveyor = make_status_row("传送带状态")
        r2, self.label_status = make_status_row("分拣状态")
        r3, self.label_sort_speed_disp = make_status_row("运行速度")
        r4, self.label_uptime = make_status_row("运行时间")
        self.label_status.setText("等待中")
        self.label_uptime.setText("00:00:00")
        status_vl.addWidget(r1, 1)
        status_vl.addWidget(r2, 1)
        status_vl.addWidget(r3, 1)
        status_vl.addWidget(r4, 1)
        right_col.addWidget(status_card, 1)

        # --- Device Parameters ---
        param_card = make_card()
        param_vl = QVBoxLayout(param_card)
        param_vl.setContentsMargins(18, 14, 18, 14)
        param_vl.setSpacing(10)
        param_vl.addWidget(make_section_title("设备参数", "#ef4444"))

        def make_param_display(name):
            row_w = QWidget()
            row_w.setStyleSheet("background: #f8f9fc; border-radius: 10px; border: 1px solid #eef0f5;")
            row_w.setMinimumHeight(42)
            row_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            row = QHBoxLayout(row_w)
            row.setContentsMargins(14, 0, 14, 0)
            row.setSpacing(8)
            lbl = QLabel(name)
            lbl.setFont(QFont(_FONT, 11))
            lbl.setStyleSheet("color: #7b8794; background: transparent; border: none;")
            row.addWidget(lbl)
            val = QLabel("--")
            val.setFont(QFont(_FONT, 11, QFont.Bold))
            val.setStyleSheet("color: #4361ee; background: transparent; border: none;")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(val)
            return row_w, val

        self._conf_value = 0.65
        pw1, self.label_conf = make_param_display("置信度")
        self.label_conf.setText(f"{self._conf_value:.2f}")

        self._offset_x = 0
        pw2, self.label_offset_x = make_param_display("偏移X")
        self.label_offset_x.setText("0")

        self._offset_y = 0
        pw3, self.label_offset_y = make_param_display("偏移Y")
        self.label_offset_y.setText("0")

        self._offset_z = 0
        pw4, self.label_offset_z = make_param_display("偏移Z")
        self.label_offset_z.setText("0")

        self._grip_value = 135
        pw5, self.label_grip = make_param_display("夹爪力度")
        self.label_grip.setText("135")

        self._sort_speed = 50
        pw6, self.label_sort_speed = make_param_display("分拣速度")
        self.label_sort_speed.setText("50")

        param_vl.addWidget(pw1, 1)
        param_vl.addWidget(pw2, 1)
        param_vl.addWidget(pw3, 1)
        param_vl.addWidget(pw4, 1)
        param_vl.addWidget(pw5, 1)
        param_vl.addWidget(pw6, 1)

        right_col.addWidget(param_card, 1)

        right_widget = QWidget()
        right_widget.setLayout(right_col)
        main_row.addWidget(right_widget, 1)  # equal stretch

        ml.addLayout(main_row, 3)

        # ===== BOTTOM ROW: 3 columns =====
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        # --- Bottom-Left: Bar Chart (detection stats) ---
        bar_card = make_card()
        bar_vl = QVBoxLayout(bar_card)
        bar_vl.setContentsMargins(14, 10, 14, 10)
        bar_vl.addWidget(make_section_title("检测统计趋势", "#22c55e"))

        self._chart_max_points = 12
        self._chart_data_ripe = deque([0] * self._chart_max_points, maxlen=self._chart_max_points)
        self._chart_data_green = deque([0] * self._chart_max_points, maxlen=self._chart_max_points)
        self._chart_data_rotten = deque([0] * self._chart_max_points, maxlen=self._chart_max_points)
        self._chart_data_total = deque([0] * self._chart_max_points, maxlen=self._chart_max_points)

        self.figure = Figure(dpi=110)
        self.figure.patch.set_facecolor('#ffffff')
        self.figure.subplots_adjust(left=0.08, right=0.97, top=0.92, bottom=0.12)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = self.figure.add_subplot(111)
        self._setup_chart_style()
        bar_vl.addWidget(self.canvas, 1)
        bottom_row.addWidget(bar_card, 1)

        # --- Bottom-Center: Log Display ---
        log_card = make_card()
        log_vl = QVBoxLayout(log_card)
        log_vl.setContentsMargins(14, 10, 14, 10)
        log_vl.setSpacing(6)
        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_dot = QLabel("\u25cf")
        log_dot.setFont(QFont("Arial", 10))
        log_dot.setStyleSheet("color: #f59e0b; background: transparent;")
        log_dot.setFixedWidth(14)
        log_header.addWidget(log_dot)
        log_title = QLabel("运行日志")
        log_title.setFont(QFont(_FONT, 13, QFont.Bold))
        log_title.setStyleSheet("color: #1e293b; background: transparent;")
        log_header.addWidget(log_title)
        self.log_line_count = QLabel("0 lines")
        self.log_line_count.setFont(QFont("Consolas", 10))
        self.log_line_count.setStyleSheet("color: #94a3b8; background: transparent;")
        log_header.addWidget(self.log_line_count)
        log_header.addStretch()
        btn_clear = QPushButton("清空")
        btn_clear.setFixedHeight(24)
        btn_clear.setStyleSheet("""
            QPushButton { background: #f1f5f9; color: #475569; border-radius: 6px;
                          font-size: 10px; padding: 0 12px; border: 1px solid #e2e8f0; }
            QPushButton:hover { background: #e2e8f0; }
        """)
        btn_clear.clicked.connect(self._clear_log)
        log_header.addWidget(btn_clear)
        log_vl.addLayout(log_header)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 12))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8fafc; 
                color: #334155;
                border: 1px solid #e4e8ee; 
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas;
                font-size: 11pt;
            }
        """)
        log_vl.addWidget(self.log_text, 1)
        bottom_row.addWidget(log_card, 1)

        # --- Bottom-Right: Pie Chart (quality distribution) ---
        pie_card = make_card()
        pie_vl = QVBoxLayout(pie_card)
        pie_vl.setContentsMargins(14, 10, 14, 10)
        pie_vl.addWidget(make_section_title("品质分布", "#8b5cf6"))
        self.pie_figure = Figure(dpi=110)
        self.pie_figure.patch.set_facecolor('#ffffff')
        self.pie_figure.subplots_adjust(left=0.28, right=0.95, top=0.95, bottom=0.05)
        self.pie_canvas = FigureCanvas(self.pie_figure)
        self.pie_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax_pie = self.pie_figure.add_subplot(111)
        self._setup_pie_chart()
        pie_vl.addWidget(self.pie_canvas, 1)
        bottom_row.addWidget(pie_card, 1)

        ml.addLayout(bottom_row, 2)

        # Compatibility labels
        self.label_object = QLabel("--")
        self.label_coord = QLabel("--")
        self.label_cur_obj = QLabel("--")
        self.label_avg_time = QLabel("--")
        self.label_total_sort = QLabel("0")
        self._det_paused = False
        self.label_det_status = QLabel("运行中")

        # ===== Scan Line Overlay (disabled for industrial style) =====
        # self._scan_overlay = ScanLineOverlay(central)
        # self._scan_overlay.raise_()

        # SSH worker
        self.ssh_worker = None
        self._ssh_connected = False  # Track SSH connection state
        self._system_stopped = False
        self._log_count = 0
        self._LOG_MAX_LINES = 500
        self._cmd_worker = None  # SSHCmdWorker / LocalCmdWorker

        # ===== Log parser state =====
        self._sort_ripe = 0
        self._sort_green = 0
        self._sort_rotten = 0
        self._sort_total = 0
        self._grasp_times = []       # timestamps of each Grasp done
        self._counting_active = False  # only count after explicit launch
        self._connect_time = None    # when SSH connected
        self._uptime_timer = QTimer()
        self._uptime_timer.timeout.connect(self._tick_uptime)
        self._uptime_timer.setInterval(1000)
        self.device_offsets_signal.connect(self._apply_device_offsets)
        self.device_offsets_error_signal.connect(self._on_device_offsets_error)

        self.add_log("[SYS] " + _TX['SYS'])

        # If running on Jetson locally, auto-connect on start
        if _IS_LOCAL:
            self.ip_input.setVisible(False)
            ip_label.setVisible(False)
            QTimer.singleShot(500, self._toggle_ssh)

    def _vl(self, text):
        lb = QLabel(text)
        lb.setFont(QFont("Consolas", 13, QFont.Bold))
        lb.setStyleSheet("color: #4361ee;")
        return lb

    # ===== Public API =====

    def update_joints(self, angles):
        pass  # Joint angle display removed from UI

    def update_grasp_status(self, obj_name=None, coord=None, status=None, conveyor=None):
        if obj_name is not None:
            self.label_object.setText(obj_name)
        if coord is not None:
            self.label_coord.setText(
                f"({coord[0]:.4f}, {coord[1]:.4f}, {coord[2]:.4f})")
        if status is not None:
            self.label_status.setText(status)
            colors = {
                _TX['IDLE']: "#64748b", _TX['DET']: "#f59e0b",
                _TX['GRAB']: "#ef4444", _TX['DONE']: "#22c55e"
            }
            c = colors.get(status, "#4361ee")
            self.label_status.setStyleSheet(f"color: {c}; font-weight: bold;")
        if conveyor is not None:
            self.label_conveyor.setText(conveyor)
            if conveyor == _TX['STOP']:
                self.label_conveyor.setStyleSheet("color: #ef4444; font-weight: bold;")
            else:
                self.label_conveyor.setStyleSheet("color: #22c55e; font-weight: bold;")

    def update_detection_stats(self, cur_obj=None, total=None, ripe=None, green=None, rotten=None):
        if cur_obj is not None:
            self.label_cur_obj.setText(cur_obj)
        if total is not None:
            self.label_total.setText(str(total))
            self._chart_data_total.append(int(total))
        if ripe is not None:
            self.label_ripe.setText(str(ripe))
            self._chart_data_ripe.append(int(ripe))
        if green is not None:
            self.label_green.setText(str(green))
            self._chart_data_green.append(int(green))
        if rotten is not None:
            self.label_rotten.setText(str(rotten))
            self._chart_data_rotten.append(int(rotten))
        # refresh chart if any numeric data updated
        if any(v is not None for v in [total, ripe, green, rotten]):
            self._refresh_chart()
            self._refresh_analysis()
            self._refresh_pie()

    def update_efficiency(self, speed=None, avg_time=None, total_sorted=None, uptime=None):
        if speed is not None:
            self.label_sort_speed_disp.setText(f"{speed:.1f} 秒/件")
            self.label_sort_speed_disp.setStyleSheet("color: #4361ee; font-weight: bold;")
        if avg_time is not None:
            self.label_avg_time.setText(f"{avg_time:.1f} {_TX['SEC_EACH']}")
            self.label_avg_time.setStyleSheet("color: #4361ee; font-weight: bold;")
        if total_sorted is not None:
            self.label_total_sort.setText(str(total_sorted))
            self.label_total_sort.setStyleSheet("color: #4361ee; font-weight: bold;")
        if uptime is not None:
            self.label_uptime.setText(uptime)
            self.label_uptime.setStyleSheet("color: #4361ee; font-weight: bold;")

    def _refresh_analysis(self):
        try:
            t = int(self.label_total.text())
            r = int(self.label_ripe.text())
            g = int(self.label_green.text())
            rot = int(self.label_rotten.text())
        except (ValueError, TypeError):
            return
        if t <= 0:
            self.label_ripe_rate.setText("--")
            self.label_green_rate.setText("--")
            self.label_rot_rate.setText("--")
            self.label_quality.setText(_TX['NO_DATA'])
            self.label_quality.setStyleSheet("color: #64748b; font-weight: bold;")
            return
        ripe_pct = r / t * 100
        green_pct = g / t * 100
        rot_pct = rot / t * 100
        self.label_ripe_rate.setText(f"{ripe_pct:.1f}%")
        self.label_ripe_rate.setStyleSheet("color: #22c55e; font-weight: bold;")
        self.label_green_rate.setText(f"{green_pct:.1f}%")
        self.label_green_rate.setStyleSheet("color: #22c55e; font-weight: bold;")
        self.label_rot_rate.setText(f"{rot_pct:.1f}%")
        self.label_rot_rate.setStyleSheet("color: #ef4444; font-weight: bold;")
        # quality grade based on ripe rate and rot rate
        if ripe_pct >= 80 and rot_pct <= 5:
            q_text = _TX['Q_EXCELLENT']
            q_color = '#22c55e'
        elif ripe_pct >= 60 and rot_pct <= 15:
            q_text = _TX['Q_GOOD']
            q_color = '#4361ee'
        elif ripe_pct >= 40 and rot_pct <= 30:
            q_text = _TX['Q_FAIR']
            q_color = '#f59e0b'
        else:
            q_text = _TX['Q_POOR']
            q_color = '#ef4444'
        self.label_quality.setText(q_text)
        self.label_quality.setFont(QFont(_FONT, 24, QFont.Bold))
        self.label_quality.setStyleSheet(f"color: {q_color};")

    @staticmethod
    def _strip_ansi(text):
        """Remove ANSI escape sequences from text."""
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    def add_log(self, msg):
        # Strip ANSI escape codes and escape HTML entities
        msg = self._strip_ansi(msg)
        msg_escaped = _html.escape(msg)
        ts = datetime.now().strftime('%H:%M:%S')
        color = '#475569'  # default dark slate
        tag_color = '#94a3b8'
        # detect tag and assign color
        if '[SYS]' in msg:
            color = '#4361ee'; tag_color = '#4361ee'
        elif '[SSH]' in msg:
            color = '#6366f1'; tag_color = '#6366f1'
        elif 'Error' in msg or 'error' in msg or 'ERROR' in msg:
            color = '#ef4444'; tag_color = '#ef4444'
        elif 'WARN' in msg or 'warn' in msg:
            color = '#f59e0b'; tag_color = '#f59e0b'
        elif 'grasp' in msg.lower() or 'grab' in msg.lower():
            color = '#f59e0b'
        elif 'detect' in msg.lower() or 'name=' in msg.lower():
            color = '#22c55e'
        line_html = (f'<span style="color:#94a3b8;">{ts}</span> '
                     f'<span style="color:{color};">{msg_escaped}</span>')
        self.log_text.append(line_html)
        self._log_count += 1
        # trim old lines if exceeding limit
        if self._log_count > self._LOG_MAX_LINES:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 50)
            cursor.removeSelectedText()
            cursor.deleteChar()
            self._log_count -= 50
        # auto-scroll to bottom
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.log_line_count.setText(f"{self._log_count} lines")

    def _clear_log(self):
        self.log_text.clear()
        self._log_count = 0
        self.log_line_count.setText("0 lines")

    # ===== Remote Parameter Control =====

    def _ssh_quick_cmd(self, cmd):
        """Fire-and-forget SSH command to device."""
        if _IS_LOCAL:
            subprocess.Popen(cmd, shell=True)
            return
        host = self.ip_input.text().strip()
        if not host:
            return
        def _run():
            try:
                c = paramiko.SSHClient()
                c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                c.connect(host, username='jetson', password='yahboom', timeout=5)
                c.exec_command(cmd)
                time.sleep(0.3)
                c.close()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def _save_ip(self, text):
        """Save IP to settings when changed"""
        self._settings.setValue('last_ip', text)

    def _read_device_offsets(self):
        """Read offset_value.yaml from Jetson and update UI offset labels."""
        host = self.ip_input.text().strip()
        if not host:
            return
        yaml_path = '/home/jetson/dofbot_pro_ws/install/dofbot_pro_driver/share/dofbot_pro_driver/config/offset_value.yaml'
        def _run():
            try:
                c = paramiko.SSHClient()
                c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                c.connect(host, username='jetson', password='yahboom', timeout=5)
                _, stdout, _ = c.exec_command(f'cat {yaml_path}')
                content = stdout.read().decode('utf-8', errors='replace')
                c.close()
                cfg = yaml.safe_load(content)
                if cfg:
                    ox = float(cfg.get('x_offset', 0))
                    oy = float(cfg.get('y_offset', 0))
                    oz = float(cfg.get('z_offset', 0))
                    self.device_offsets_signal.emit(ox, oy, oz)
            except Exception as e:
                self.device_offsets_error_signal.emit(str(e))
        threading.Thread(target=_run, daemon=True).start()

    def _apply_device_offsets(self, ox, oy, oz):
        """Apply values in the Qt main thread after SSH reading completes."""
        self._offset_x = ox
        self._offset_y = oy
        self._offset_z = oz
        self.label_offset_x.setText(f"{ox:.4f}")
        self.label_offset_y.setText(f"{oy:.4f}")
        self.label_offset_z.setText(f"{oz:.4f}")
        self.add_log(f"[SYS] Device offsets: X={ox}, Y={oy}, Z={oz}")

    def _on_device_offsets_error(self, error):
        self.add_log(f"[SYS] Failed to read offsets: {error}")

    def _conf_dec(self):
        self._conf_value = max(0.05, round(self._conf_value - 0.05, 2))
        self.label_conf.setText(f"{self._conf_value:.2f}")
        self._ssh_quick_cmd(f"echo {self._conf_value} > /tmp/yolo_conf.txt")
        self.add_log(f"[CTRL] Confidence -> {self._conf_value:.2f}")

    def _conf_inc(self):
        self._conf_value = min(0.95, round(self._conf_value + 0.05, 2))
        self.label_conf.setText(f"{self._conf_value:.2f}")
        self._ssh_quick_cmd(f"echo {self._conf_value} > /tmp/yolo_conf.txt")
        self.add_log(f"[CTRL] Confidence -> {self._conf_value:.2f}")

    def _det_do_pause(self):
        self._det_paused = True
        self.label_det_status.setText(_TX['DET_PAUSED'])
        self.label_det_status.setStyleSheet("color: #ef4444; background: transparent;")
        self._ssh_quick_cmd("echo 1 > /tmp/yolo_pause.txt")
        self.add_log("[CTRL] Detection PAUSED")

    def _det_do_resume(self):
        self._det_paused = False
        self.label_det_status.setText(_TX['DET_RUNNING'])
        self.label_det_status.setStyleSheet("color: #22c55e; background: transparent;")
        self._ssh_quick_cmd("echo 0 > /tmp/yolo_pause.txt")
        self.add_log("[CTRL] Detection RESUMED")

    def _grip_dec(self):
        self._grip_value = max(30, self._grip_value - 5)
        self.label_grip.setText(f"{self._grip_value}\u00b0")
        self._ssh_quick_cmd(f"echo {self._grip_value} > /tmp/gripper_force.txt")
        self.add_log(f"[CTRL] Gripper force -> {self._grip_value}\u00b0")

    def _grip_inc(self):
        self._grip_value = min(180, self._grip_value + 5)
        self.label_grip.setText(f"{self._grip_value}")
        self._ssh_quick_cmd(f"echo {self._grip_value} > /tmp/gripper_force.txt")
        self.add_log(f"[CTRL] Gripper force -> {self._grip_value}")
    
    # Offset X
    def _offset_x_dec(self):
        self._offset_x = max(-50, self._offset_x - 1)
        self.label_offset_x.setText(str(self._offset_x))
        self._ssh_quick_cmd(f"echo {self._offset_x} > /tmp/offset_x.txt")
        self.add_log(f"[CTRL] Offset X -> {self._offset_x}")
    
    def _offset_x_inc(self):
        self._offset_x = min(50, self._offset_x + 1)
        self.label_offset_x.setText(str(self._offset_x))
        self._ssh_quick_cmd(f"echo {self._offset_x} > /tmp/offset_x.txt")
        self.add_log(f"[CTRL] Offset X -> {self._offset_x}")
    
    # Offset Y
    def _offset_y_dec(self):
        self._offset_y = max(-50, self._offset_y - 1)
        self.label_offset_y.setText(str(self._offset_y))
        self._ssh_quick_cmd(f"echo {self._offset_y} > /tmp/offset_y.txt")
        self.add_log(f"[CTRL] Offset Y -> {self._offset_y}")
    
    def _offset_y_inc(self):
        self._offset_y = min(50, self._offset_y + 1)
        self.label_offset_y.setText(str(self._offset_y))
        self._ssh_quick_cmd(f"echo {self._offset_y} > /tmp/offset_y.txt")
        self.add_log(f"[CTRL] Offset Y -> {self._offset_y}")
    
    # Offset Z
    def _offset_z_dec(self):
        self._offset_z = max(-50, self._offset_z - 1)
        self.label_offset_z.setText(str(self._offset_z))
        self._ssh_quick_cmd(f"echo {self._offset_z} > /tmp/offset_z.txt")
        self.add_log(f"[CTRL] Offset Z -> {self._offset_z}")
    
    def _offset_z_inc(self):
        self._offset_z = min(50, self._offset_z + 1)
        self.label_offset_z.setText(str(self._offset_z))
        self._ssh_quick_cmd(f"echo {self._offset_z} > /tmp/offset_z.txt")
        self.add_log(f"[CTRL] Offset Z -> {self._offset_z}")
    
    # Sort speed
    def _speed_dec(self):
        self._sort_speed = max(10, self._sort_speed - 5)
        self.label_sort_speed.setText(str(self._sort_speed))
        self._ssh_quick_cmd(f"echo {self._sort_speed} > /tmp/sort_speed.txt")
        self.add_log(f"[CTRL] Sort speed -> {self._sort_speed}")
    
    def _speed_inc(self):
        self._sort_speed = min(100, self._sort_speed + 5)
        self.label_sort_speed.setText(str(self._sort_speed))
        self._ssh_quick_cmd(f"echo {self._sort_speed} > /tmp/sort_speed.txt")
        self.add_log(f"[CTRL] Sort speed -> {self._sort_speed}")
    
    # ===== Chart =====

    def _setup_chart_style(self):
        ax = self.ax
        ax.set_facecolor('#fafbfe')
        ax.tick_params(colors='#94a3b8', labelsize=12)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('#e4e8ee')
        ax.spines['left'].set_color('#e4e8ee')

        n = self._chart_max_points
        x = np.arange(n)
        w = 0.34

        self._bar_x = x
        self._bar_w = w
        self._bars_ripe = ax.bar(x - w / 2, [0]*n, w, color='#f59e0b',
                                  label=_TX.get('RIPE', '标准件'),
                                  alpha=0.85, edgecolor='white', linewidth=0.5, zorder=2)
        self._bars_rotten = ax.bar(x + w / 2, [0]*n, w, color='#ef4444',
                                    label=_TX.get('ROTTEN', '缺陷件'),
                                    alpha=0.85, edgecolor='white', linewidth=0.5, zorder=2)
        ax.set_xlim(-0.5, n - 0.5)
        ax.set_ylim(0, 5)
        ax.set_xticks([])
        ax.grid(True, axis='y', color='#eef0f5', linewidth=0.5, alpha=0.8)
        ax.legend(loc='upper left', fontsize=11, framealpha=0.95,
                  labelcolor='#475569', facecolor='white',
                  edgecolor='#e4e8ee', ncol=2, handlelength=1.2)

    def _setup_pie_chart(self):
        ax = self.ax_pie
        ax.set_facecolor('white')
        self._pie_colors = ['#f59e0b', '#ef4444']
        self._pie_labels = ['标准件', '缺陷件']
        # Draw empty donut ring
        wedges, _ = ax.pie(
            [1], colors=['#eef0f5'], startangle=90,
            wedgeprops=dict(width=0.38, edgecolor='white', linewidth=2))
        ax.text(0, 0, '0', ha='center', va='center',
                fontsize=28, fontweight='bold', color='#94a3b8')
        ax.text(0, -0.22, '总计', ha='center', va='center',
                fontsize=13, color='#94a3b8')
        ax.set_aspect('equal')
        ax.axis('off')

    def _refresh_chart(self):
        ripe = list(self._chart_data_ripe)
        rotten = list(self._chart_data_rotten)
        # Update bar heights
        for bar, val in zip(self._bars_ripe, ripe):
            bar.set_height(val)
        for bar, val in zip(self._bars_rotten, rotten):
            bar.set_height(val)
        # Auto-scale Y axis
        all_vals = ripe + rotten
        max_v = max(all_vals) if all_vals else 5
        self.ax.set_ylim(0, max(5, max_v + 2))
        self.canvas.draw_idle()

    def _refresh_pie(self):
        try:
            r = int(self.label_ripe.text())
            rot = int(self.label_rotten.text())
        except (ValueError, TypeError):
            return
        total = r + rot
        if total <= 0:
            return
        ax = self.ax_pie
        ax.clear()
        ax.set_facecolor('white')
        sizes = [r, rot]
        # Donut chart
        wedges, _ = ax.pie(
            sizes, colors=self._pie_colors, startangle=90,
            wedgeprops=dict(width=0.38, edgecolor='white', linewidth=2))
        # Center text: total count
        ax.text(0, 0, str(total), ha='center', va='center',
                fontsize=30, fontweight='bold', color='#1e293b')
        ax.text(0, -0.22, '总计', ha='center', va='center',
                fontsize=13, color='#94a3b8')
        # Legend with counts
        legend_labels = [f'{label}  {value}' for label, value in zip(self._pie_labels, sizes)]
        leg = ax.legend(wedges, legend_labels, loc='center left',
                        bbox_to_anchor=(-0.35, 0.5), fontsize=12,
                        frameon=False, labelcolor='#475569',
                        handlelength=1.2, handleheight=1.2)
        ax.set_aspect('equal')
        self.pie_canvas.draw_idle()

    # ===== SSH Control =====

    def _toggle_ssh(self):
        if self.ssh_worker and self.ssh_worker.isRunning():
            self.ssh_worker.stop()
            self.ssh_worker.wait(3000)
            self.ssh_worker = None
            # Immediately update UI to disconnected state
            self._ssh_connected = False
            self._counting_active = False
            self.label_conn_status.setText(_TX['OFFLINE'])
            self.label_conn_status.setStyleSheet("color: #64748b;")
            self.btn_connect.setText(_TX['BTN_CONN'])
            self.btn_connect.setStyleSheet("""
                QPushButton { background: #4361ee; color: white; border-radius: 6px; padding: 6px 14px; }
                QPushButton:hover { background: #5a7bff; }
            """)
            self._set_sys_buttons_enabled(False)
            self._uptime_timer.stop()
            self.add_log("[SSH] Disconnected")
        else:
            # 实际系统日志路径（两个核心节点）
            log_files = '/tmp/dofbot_logs/yolov11.log /tmp/dofbot_logs/yolov11_sortation.log'
            self.label_conn_status.setText(_TX['CONNECTING'])
            self.label_conn_status.setStyleSheet("color: #f59e0b;")
            self.btn_connect.setEnabled(False)
            if _IS_LOCAL:
                # Running on Jetson itself: tail log files directly
                self.ssh_worker = LocalLogWorker(log_files)
                self.ssh_worker.log_signal.connect(self._on_ssh_log)
                self.ssh_worker.status_signal.connect(self._on_ssh_status)
                self.ssh_worker.start()
                self.add_log("[LOCAL] Reading log locally...")
            else:
                # Running on Windows: SSH into Jetson
                host = self.ip_input.text().strip()
                if not host:
                    return
                self.ssh_worker = SSHLogWorker(host, 'jetson', 'yahboom', log_files)
                self.ssh_worker.log_signal.connect(self._on_ssh_log)
                self.ssh_worker.status_signal.connect(self._on_ssh_status)
                self.ssh_worker.start()

    def _set_sys_buttons_enabled(self, connected: bool):
        """Enable/disable system control buttons based on SSH connection."""
        self.btn_launch.setEnabled(connected)
        self.btn_stop_sys.setEnabled(connected)

    def _launch_system(self):
        """One-click launch: SSH exec start_sorting.sh in background."""
        if self._cmd_worker and self._cmd_worker.isRunning():
            self.add_log("[SYS] Command busy, please wait...")
            return

        self._system_stopped = False  # Clear stop flag on launch
        self.btn_launch.setEnabled(False)
        self.label_sys_status.setText(_TX['LAUNCHING'])
        self.label_sys_status.setStyleSheet("color: #f59e0b;")
        self.add_log("[SYS] Launching sortation system...")

        cmd = "bash ~/start_sorting.sh"

        if _IS_LOCAL:
            self._cmd_worker = LocalCmdWorker(cmd)
        else:
            host = self.ip_input.text().strip()
            self._cmd_worker = SSHCmdWorker(host, 'jetson', 'yahboom', cmd)

        self._cmd_worker.log_signal.connect(self._on_cmd_log)
        self._cmd_worker.status_signal.connect(self._on_launch_status)
        self._cmd_worker.start()

        # start_sorting.sh blocks forever on 'wait', so _on_launch_status
        # will never fire.  Use a timer to restart camera/log after nodes
        # have had enough time to initialise (~28 s).
        self._launch_ready_timer = QTimer()
        self._launch_ready_timer.setSingleShot(True)
        self._launch_ready_timer.timeout.connect(self._on_launch_nodes_ready)
        self._launch_ready_timer.start(28000)

    def _stop_system(self):
        """One-click stop: SSH exec stop_sorting.sh."""
        # Immediately disable counting so in-flight log lines are not tallied
        self._counting_active = False
        self._system_stopped = True  # Prevent SSH reconnect from restarting camera
        # Cancel any pending launch-ready timer
        if hasattr(self, '_launch_ready_timer') and self._launch_ready_timer.isActive():
            self._launch_ready_timer.stop()
        # If a previous command is still running, disconnect its signals and let it finish on its own
        if self._cmd_worker and self._cmd_worker.isRunning():
            try:
                self._cmd_worker.log_signal.disconnect()
                self._cmd_worker.status_signal.disconnect()
            except Exception:
                pass
            self._cmd_worker = None

        # Immediately reset all UI panels (counters, charts, camera, etc.)
        # so the user sees a clean slate the moment they click Stop.
        self._reset_ui_for_stop()

        self.btn_stop_sys.setEnabled(False)
        self.label_sys_status.setText(_TX['STOPPING'])
        self.label_sys_status.setStyleSheet("color: #f59e0b;")
        self.add_log("[SYS] Stopping sortation system...")

        cmd = "bash ~/stop_sorting.sh"

        if _IS_LOCAL:
            self._cmd_worker = LocalCmdWorker(cmd)
        else:
            host = self.ip_input.text().strip()
            self._cmd_worker = SSHCmdWorker(host, 'jetson', 'yahboom', cmd)

        self._cmd_worker.log_signal.connect(self._on_cmd_log)
        self._cmd_worker.status_signal.connect(self._on_stop_status)
        self._cmd_worker.start()

    def _on_cmd_log(self, line):
        """Forward remote command output to log panel."""
        self.add_log(f"[REM] {line}")

    def _restart_ssh_log(self):
        """Restart SSH log tailing to pick up freshly truncated log file."""
        if self.ssh_worker and self.ssh_worker.isRunning():
            self.ssh_worker.stop()
            self.ssh_worker.wait(2000)
        log_files = '/tmp/dofbot_logs/yolov11.log /tmp/dofbot_logs/yolov11_sortation.log'
        if _IS_LOCAL:
            self.ssh_worker = LocalLogWorker(log_files)
        else:
            host = self.ip_input.text().strip()
            if not host:
                return
            self.ssh_worker = SSHLogWorker(host, 'jetson', 'yahboom', log_files)
        self.ssh_worker.log_signal.connect(self._on_ssh_log)
        self.ssh_worker.status_signal.connect(self._on_ssh_status)
        self.ssh_worker.start()

    def _on_launch_nodes_ready(self):
        """Timer callback: ~28 s after launch, nodes should be up. Restart UI."""
        self.label_sys_status.setText(_TX['LAUNCHED'])
        self.label_sys_status.setStyleSheet("color: #22c55e; font-weight: bold;")
        self._set_sys_buttons_enabled(self._ssh_connected)
        self.add_log("[SYS] Nodes ready — restarting log tail")
        self._restart_ssh_log()
        self._connect_time = time.time()
        self._uptime_timer.start()
        # Delay counting by 3 s so the historical tail -n 50 lines
        # are flushed before we start parsing real-time events.
        QTimer.singleShot(3000, self._enable_counting_after_connect)

    def _on_launch_status(self, status):
        """Launch command finished callback (may never fire if script blocks)."""
        self._cmd_worker = None
        self._set_sys_buttons_enabled(self._ssh_connected)
        if status == 'finished':
            # Cancel timer if command somehow finished before it
            if hasattr(self, '_launch_ready_timer') and self._launch_ready_timer.isActive():
                self._launch_ready_timer.stop()
            self.label_sys_status.setText(_TX['LAUNCHED'])
            self.label_sys_status.setStyleSheet("color: #22c55e; font-weight: bold;")
            self.add_log("[SYS] Sortation launched, reconnecting log tail...")
            self._restart_ssh_log()
            self._connect_time = time.time()
            self._uptime_timer.start()
            # Delay counting to skip historical tail lines
            QTimer.singleShot(3000, self._enable_counting_after_connect)
        elif status.startswith('error:'):
            if hasattr(self, '_launch_ready_timer') and self._launch_ready_timer.isActive():
                self._launch_ready_timer.stop()
            self.label_sys_status.setText(_TX['LAUNCH_ERR'])
            self.label_sys_status.setStyleSheet("color: #ef4444;")
            self.add_log(f"[SYS] Launch failed: {status[6:]}")

    def _reset_ui_for_stop(self):
        """Reset all UI panels for a clean state after stopping the system."""
        # --- Detection counts ---
        self._sort_ripe = 0
        self._sort_green = 0
        self._sort_rotten = 0
        self._sort_total = 0
        self._grasp_times.clear()
        # Note: do NOT reset _counting_active here — it should stay True
        # as long as SSH is connected, so new events are still counted.
        self.label_total.setText("0")
        self.label_ripe.setText("0")
        self.label_green.setText("0")
        self.label_rotten.setText("0")
        # --- Quality analysis ---
        self.label_ripe_rate.setText("--%")
        self.label_ripe_rate.setStyleSheet("color: #22c55e; font-weight: bold;")
        self.label_green_rate.setText("--%")
        self.label_green_rate.setStyleSheet("color: #22c55e; font-weight: bold;")
        self.label_rot_rate.setText("--%")
        self.label_rot_rate.setStyleSheet("color: #ef4444; font-weight: bold;")
        self.label_quality.setText(_TX['NO_DATA'])
        self.label_quality.setFont(QFont(_FONT, 24, QFont.Bold))
        self.label_quality.setStyleSheet("color: #64748b;")
        # --- Charts ---
        for d in (self._chart_data_total, self._chart_data_ripe,
                  self._chart_data_green, self._chart_data_rotten):
            d.clear()
            d.extend([0] * self._chart_max_points)
        self._refresh_chart()
        self.ax_pie.clear()
        self._setup_pie_chart()
        self.pie_canvas.draw_idle()
        # --- Efficiency / status ---
        self.label_conveyor.setText("--")
        self.label_conveyor.setStyleSheet("color: #2d3748; background: transparent; border: none;")
        self.label_sort_speed_disp.setText("--")
        self.label_sort_speed_disp.setStyleSheet("color: #2d3748; background: transparent; border: none;")
        self.label_uptime.setText("--")
        self.label_uptime.setStyleSheet("color: #2d3748; background: transparent; border: none;")
        self._connect_time = None
        self._uptime_timer.stop()
        # --- Log ---
        self._clear_log()

    def _on_stop_status(self, status):
        """Stop command finished callback."""
        self._cmd_worker = None
        self._set_sys_buttons_enabled(self._ssh_connected)
        if status == 'finished':
            self.label_sys_status.setText(_TX['SYS_STOPPED'])
            self.label_sys_status.setStyleSheet("color: #64748b;")
            self.label_status.setText("暂停分拣")
            self.label_status.setStyleSheet("color: #f59e0b; background: transparent; border: none;")
            # UI was already reset in _stop_system(); just log confirmation.
            self.add_log("[SYS] System stopped successfully")
        elif status.startswith('error:'):
            self.label_sys_status.setText(_TX['LAUNCH_ERR'])
            self.label_sys_status.setStyleSheet("color: #ef4444;")
            self.add_log(f"[SYS] Stop failed: {status[6:]}")

    def _enable_counting_after_connect(self):
        """Enable counting after connection warmup (skip historical tail lines)."""
        if self._ssh_connected and not self._counting_active:
            self._counting_active = True
            self.add_log("[SYS] Live counting enabled")

    def _on_ssh_status(self, status):
        self.btn_connect.setEnabled(True)
        if status == 'connected':
            self._ssh_connected = True
            self.label_conn_status.setText(_TX['ONLINE'])
            self.label_conn_status.setStyleSheet("color: #22c55e; font-weight: bold;")
            self.btn_connect.setText(_TX['BTN_DISC'])
            self.btn_connect.setStyleSheet("""
                QPushButton { background: #ef4444; color: white; border-radius: 6px; padding: 6px 14px; }
                QPushButton:hover { background: #f87171; }
            """)
            self.add_log("[SSH] Connected to " + self.ip_input.text())
            # Enable sys buttons after connected
            self._set_sys_buttons_enabled(True)
            # Start uptime timer
            self._connect_time = time.time()
            self._uptime_timer.start()
            # Read actual offsets from device config
            self._read_device_offsets()
            # Enable counting after a short delay so initial historical
            # tail lines (tail -n 50) are skipped but live data counts.
            if not self._counting_active:
                QTimer.singleShot(3000, self._enable_counting_after_connect)
        elif status == 'disconnected':
            self._ssh_connected = False
            self._counting_active = False
            self.label_conn_status.setText(_TX['OFFLINE'])
            self.label_conn_status.setStyleSheet("color: #64748b;")
            self.btn_connect.setText(_TX['BTN_CONN'])
            self.btn_connect.setStyleSheet("""
                QPushButton { background: #4361ee; color: white; border-radius: 6px; padding: 6px 14px; }
                QPushButton:hover { background: #5a7bff; }
            """)
            self.ssh_worker = None
            self._set_sys_buttons_enabled(False)
            self._uptime_timer.stop()
            self.add_log("[SSH] Disconnected")
        elif status.startswith('error:'):
            self._ssh_connected = False
            err = status[6:]
            self.label_conn_status.setText(_TX['CONN_ERR'])
            self.label_conn_status.setStyleSheet("color: #ef4444;")
            self.btn_connect.setText(_TX['BTN_CONN'])
            self.btn_connect.setStyleSheet("""
                QPushButton { background: #4361ee; color: white; border-radius: 6px; padding: 6px 14px; }
                QPushButton:hover { background: #5a7bff; }
            """)
            self.ssh_worker = None
            self._set_sys_buttons_enabled(False)
            self._uptime_timer.stop()
            self.add_log(f"[SSH] Error: {err}")

    def _on_ssh_log(self, line):
        if self._system_stopped:
            return  # System stopped — ignore tail log lines
        clean = self._strip_ansi(line)
        self.add_log(clean)
        try:
            self._parse_log_line(clean)
        except Exception as e:
            self.add_log(f"[UI] Log parse error ignored: {type(e).__name__}: {e}")

    def _parse_log_line(self, line):
        """Parse log lines from the actual sorting system and update UI panels.
        Only update counters when _counting_active is True (after explicit launch).

        Actual system log format (from yolov11.py & yolov11_sortation.py):
          [Phase1] 检测到: chengshujinju (320,240) → 立即停带！
          [Phase2] 重新检测: chengshujinju (321,239) d=0.250m r=10 → 开始夹取
          [夹取] 开始夹取: chengshujinju
          分拣: chengshujinju → 位置 ID=1
          pose_T:  [0.1, 0.2, 0.3]
          [夹取] 放置完成，等待机械臂归位...
          [传送带] 机械臂已归位，传送带启动
          [分拣] ===== 本轮分拣完成，等待下一个物体 =====
          [投票通过] chengshujinju (3/5) 投票详情: {...}
          Init Done
        """
        if not self._counting_active:
            return
        # --- Phase1: 检测到物体 → 停止传送带 ---
        if '[Phase1] 检测到:' in line:
            m = re.search(r'\[Phase1\] 检测到: (\S+)', line)
            if m:
                raw_name = m.group(1)
                display = self._translate_name(raw_name)
                self.update_grasp_status(obj_name=display, status=_TX['DET'], conveyor=_TX['STOP'])
                self.update_detection_stats(cur_obj=display)
            return

        # --- 投票通过: 多帧投票确认的检测结果 ---
        if '[投票通过]' in line:
            m = re.search(r'\[投票通过\] (\S+)', line)
            if m:
                display = self._translate_name(m.group(1))
                self.update_detection_stats(cur_obj=display)
            return

        # 标准件只经过检测、不进入抓取流程，由检测节点单独发送计数日志。
        if '[COUNT]' in line:
            m = re.search(r'\[COUNT\]\s+(\S+)', line)
            if m and m.group(1) in ('biaozhunketi', 'biaozhun', 'chengshujinju'):
                self._sort_ripe += 1
                self._sort_total += 1
                self.update_detection_stats(
                    cur_obj=self._translate_name(m.group(1)))
                self._update_counts()
            return

        # --- 分拣分类: 统计各类别计数 ---
        if '分拣:' in line and '位置 ID=' in line:
            m = re.search(r'分拣: (\S+)\s', line)
            if m:
                name = m.group(1)
                if name in ('biaozhunketi', 'biaozhun', 'chengshujinju'):
                    self._sort_ripe += 1
                elif name in ('quexianketi', 'quexian', 'fulanjinju'):
                    self._sort_rotten += 1
                elif name == 'qingjinju':
                    self._sort_green += 1
                self._sort_total += 1
                self._update_counts()
            return

        # --- 3D坐标: pose_T ---
        if 'pose_T:' in line:
            m = re.search(r'pose_T:\s*\[([\d.e+-]+)\s*,?\s*([\d.e+-]+)\s*,?\s*([\d.e+-]+)', line)
            if m:
                coord = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
                self.update_grasp_status(coord=coord)
            return

        # --- 夹取开始 ---
        if '[夹取] 开始夹取:' in line:
            self.update_grasp_status(status=_TX['GRAB'])
            return

        # --- 本轮分拣完成 ---
        if '本轮分拣完成' in line:
            self.update_grasp_status(status=_TX['DONE'])
            self._grasp_times.append(time.time())
            self._update_efficiency()
            return

        # --- 传送带启动 ---
        if '[传送带]' in line and '传送带启动' in line:
            self.update_grasp_status(conveyor=_TX['RUN'], status=_TX['IDLE'])
            return

        # --- Init Done ---
        if 'Init Done' in line:
            self.update_grasp_status(status=_TX['IDLE'])
            return

        # --- 关节角度 (pubTargetArm 输出的 6 个数字列表) ---
        m = re.match(r'^\s*\[([\d.e+\-,\s]+)\]\s*$', line)
        if m:
            parts = m.group(1).split(',')
            if len(parts) == 6:
                try:
                    angles = [float(p.strip()) for p in parts]
                    self.update_joints(angles)
                except ValueError:
                    pass
            return

    def _translate_name(self, raw):
        """Translate YOLO class name to display name."""
        name_map = {
            'biaozhunketi': '\u6807\u51c6\u4ef6',
            'quexianketi': '\u7f3a\u9677\u4ef6',
            'biaozhun': '\u6807\u51c6\u4ef6',
            'quexian': '\u7f3a\u9677\u4ef6',
            'chengshujinju': '\u6807\u51c6\u4ef6',
            'fulanjinju': '\u7f3a\u9677\u4ef6',
            'qingjinju': '\u9752\u91d1\u6a58',
        }
        return name_map.get(raw, raw)

    def _update_counts(self):
        """Push cumulative counts to detection stats panel."""
        self.update_detection_stats(
            total=self._sort_total,
            ripe=self._sort_ripe,
            green=self._sort_green,
            rotten=self._sort_rotten,
        )
        self._update_runtime_speed()

    def _update_runtime_speed(self, elapsed=None):
        """Display average elapsed runtime per detected part."""
        if self._connect_time is None or self._sort_total <= 0:
            self.label_sort_speed_disp.setText("--")
            return
        if elapsed is None:
            elapsed = max(0.0, time.time() - self._connect_time)
        self.update_efficiency(speed=elapsed / self._sort_total)

    def _update_efficiency(self):
        """Update the completed-grasp counter kept for compatibility."""
        n = len(self._grasp_times)
        self.update_efficiency(total_sorted=n)

    def _tick_uptime(self):
        """Update running time display every second."""
        if self._connect_time is None:
            return
        delta = int(time.time() - self._connect_time)
        h = delta // 3600
        m = (delta % 3600) // 60
        s = delta % 60
        self.update_efficiency(uptime=f"{h:02d}:{m:02d}:{s:02d}")
        self._update_runtime_speed(delta)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_scan_overlay') and self.centralWidget():
            self._scan_overlay.setGeometry(self.centralWidget().rect())

    def keyPressEvent(self, event):
        """ESC to exit fullscreen, F11 to toggle fullscreen"""
        from PyQt5.QtCore import Qt
        if event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
        elif event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._cmd_worker and self._cmd_worker.isRunning():
            self._cmd_worker.stop()
            self._cmd_worker.wait(2000)
        if self.ssh_worker and self.ssh_worker.isRunning():
            self.ssh_worker.stop()
            self.ssh_worker.wait(3000)
        event.accept()
