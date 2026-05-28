import threading
import time
import win32gui
import win32process
import psutil
from typing import Callable, List, Optional
from agent.screenshots.capture import capture_emr_window
from agent.screenshots.ocr import get_text


class UIATracker:
    def __init__(
        self,
        emr_detector,
        event_callback: Callable,
        poll_interval: float = 0.2,
        rdp_processes: Optional[List[str]] = None,
        rdp_ocr_interval: float = 2.0,
    ):
        self._detector = emr_detector
        self._callback = event_callback
        self._poll_interval = poll_interval
        self._rdp_processes = {p.lower() for p in (rdp_processes or ["mstsc.exe"])}
        self._rdp_ocr_interval = rdp_ocr_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_hwnd: int = 0
        self._last_title: str = ""
        self._last_rdp_module: Optional[str] = None
        self._last_ocr_time: float = 0.0

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

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
        except Exception:
            return

        if process_name.lower() in self._rdp_processes:
            self._check_rdp_window(hwnd)
            return

        # Reset RDP state when leaving an RDP window
        self._last_rdp_module = None

        if hwnd == self._last_hwnd and title == self._last_title:
            return

        self._last_hwnd = hwnd
        self._last_title = title

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

    def _check_rdp_window(self, hwnd: int) -> None:
        now = time.time()
        if now - self._last_ocr_time < self._rdp_ocr_interval:
            return
        self._last_ocr_time = now

        try:
            image = capture_emr_window(hwnd)
            text = get_text(image)
        except Exception:
            return

        emr, module = self._detector.detect_from_ocr(text)
        if emr is None:
            return

        if module == self._last_rdp_module:
            return

        self._last_rdp_module = module
        self._callback(
            emr=emr,
            module=module,
            window_title=f"[RDP] {text[:80]}",
            event_type="window_focus",
            hwnd=hwnd,
        )
