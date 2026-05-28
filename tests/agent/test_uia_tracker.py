import time
import pytest
from unittest.mock import patch, MagicMock, call
from agent.tracker.uia_tracker import UIATracker


@pytest.fixture
def callback():
    return MagicMock()


@pytest.fixture
def detector():
    m = MagicMock()
    m.detect.return_value = ("accuro", "patient_search")
    return m


def test_tracker_calls_callback_on_window_change(callback, detector):
    tracker = UIATracker(emr_detector=detector, event_callback=callback, poll_interval=0.05)

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psutil:

        mock_gui.GetForegroundWindow.side_effect = [100, 200, 200]
        mock_gui.GetWindowText.side_effect = ["Accuro - Patient Search", "Accuro - Appointments", "Accuro - Appointments"]
        mock_proc.GetWindowThreadProcessId.return_value = (1, 999)
        mock_psutil.Process.return_value.name.return_value = "chrome.exe"
        detector.detect.side_effect = [
            ("accuro", "patient_search"),
            ("accuro", "appointment_scheduling"),
        ]

        tracker.start()
        time.sleep(0.2)
        tracker.stop()

    assert callback.call_count >= 1
    first_call = callback.call_args_list[0]
    assert first_call.kwargs["emr"] == "accuro"
    assert "hwnd" in first_call.kwargs


def test_tracker_ignores_non_emr_windows(callback, detector):
    tracker = UIATracker(emr_detector=detector, event_callback=callback, poll_interval=0.05)
    detector.detect.return_value = (None, None)

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psutil:

        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Microsoft Excel"
        mock_proc.GetWindowThreadProcessId.return_value = (1, 888)
        mock_psutil.Process.return_value.name.return_value = "excel.exe"

        tracker.start()
        time.sleep(0.2)
        tracker.stop()

    callback.assert_not_called()


def test_tracker_stop_terminates_thread(callback, detector):
    tracker = UIATracker(emr_detector=detector, event_callback=callback, poll_interval=0.05)

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psutil:

        mock_gui.GetForegroundWindow.return_value = 0
        mock_gui.GetWindowText.return_value = ""
        mock_proc.GetWindowThreadProcessId.return_value = (1, 0)
        mock_psutil.Process.side_effect = Exception("no process")

        tracker.start()
        assert tracker._thread.is_alive()
        tracker.stop()
        tracker._thread.join(timeout=1.0)
        assert not tracker._thread.is_alive()
