# -*- coding: utf-8 -*-
"""
Arm Monitor - Main Entry
"""
import sys
from PyQt5.QtWidgets import QApplication
from arm_monitor_window import ArmMonitorWindow

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ArmMonitorWindow()
    if '--fullscreen' in sys.argv:
        window.showFullScreen()
    else:
        window.show()
    sys.exit(app.exec_())
