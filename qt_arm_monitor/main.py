# -*- coding: utf-8 -*-
"""
Arm Monitor - Main Entry
"""
import faulthandler
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from arm_monitor_window import ArmMonitorWindow


_CRASH_LOG_PATH = Path(__file__).resolve().with_name('crash.log')
_CRASH_LOG_FILE = _CRASH_LOG_PATH.open('a', encoding='utf-8', buffering=1)
faulthandler.enable(file=_CRASH_LOG_FILE, all_threads=True)


def _write_exception(exc_type, exc_value, exc_traceback):
    """Keep pythonw failures visible without terminating the Qt application."""
    _CRASH_LOG_FILE.write(
        f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] Unhandled exception\n")
    traceback.print_exception(
        exc_type, exc_value, exc_traceback, file=_CRASH_LOG_FILE)
    _CRASH_LOG_FILE.flush()


def _write_thread_exception(args):
    _write_exception(args.exc_type, args.exc_value, args.exc_traceback)


sys.excepthook = _write_exception
threading.excepthook = _write_thread_exception


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ArmMonitorWindow()
    if '--fullscreen' in sys.argv:
        window.showFullScreen()
    else:
        window.show()
    sys.exit(app.exec_())
