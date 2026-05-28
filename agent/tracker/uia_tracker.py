import threading
import time
import win32gui
import win32process
import psutil
from typing import Callable, Optional


class UIATracker:
    def __init__(
        self,
        emr_detector,
        event_callback: Callable,
        poll_interval: float = 0.2,
    ):
        self._detector = emr_detector
        self._callback = event_callback
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_hwnd: int = 0
        self._last_title: str = ""

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._check_foreground()
            except Exception:
                pass
            time.sleep(self._poll_interval)

    def _check_foreground(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)

        if hwnd == self._last_hwnd and title == self._last_title:
            return

        self._last_hwnd = hwnd
        self._last_title = title

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
        except Exception:
            return

        emr, module = self._detector.detect(title, process_name)
        if emr is None:
            return

        self._callback(
            emr=emr,
            module=module,
            window_title=title,
            event_type="window_focus",
            hwnd=hwnd,
        )
