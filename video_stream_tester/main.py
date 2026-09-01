# -*- coding: utf-8 -*-
"""Entry point for the independent MJPEG video-stream tester."""

import sys

from PyQt5.QtWidgets import QApplication

from video_tester import VideoTesterWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoTesterWindow()
    if "--fullscreen" in sys.argv:
        window.showFullScreen()
    elif "--normal" in sys.argv:
        window.show()
    else:
        window.showMaximized()
    sys.exit(app.exec_())

