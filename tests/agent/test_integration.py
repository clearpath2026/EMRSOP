"""
End-to-end: simulate a sequence of EMR window events through the full
local pipeline and verify a redacted JSON workflow file is written to disk.
No Windows APIs called — all mocked.
"""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from agent.service.config import Config
from agent.redaction.engine import RedactionEngine
from agent.tracker.emr_detector import EMRDetector
from agent.tracker.uia_tracker import UIATracker
from agent.session.aggregator import SessionAggregator
from agent.storage.db import Database
from agent.storage.audit_log import AuditLogger

FIXTURE_EMR_MODULES = {
    "accuro": {
        "patient_search": ["Patient Search"],
        "appointment_scheduling": ["Appointment", "Schedule"],
        "billing": ["Billing"],
    }
}
FIXTURE_EMR_PROCESSES = {
    "accuro": {
        "process_names": ["chrome.exe"],
        "window_title_patterns": ["Accuro"],
    }
}

WINDOW_SEQUENCE = [
    (100, "Accuro - Patient Search",      "chrome.exe"),
    (200, "Accuro - Appointment Schedule", "chrome.exe"),
    (200, "Accuro - Appointment Schedule", "chrome.exe"),  # duplicate — same hwnd+title, no event
    (300, "Accuro - Billing",              "chrome.exe"),
]


def test_full_pipeline_produces_json(tmp_path, shared_redaction_engine):
    config = Config(
        agent_id="vm-integration-test",
        data_dir=str(tmp_path),
        workflows_dir=str(tmp_path / "workflows"),
        screenshots_dir=str(tmp_path / "screenshots"),
        db_path=str(tmp_path / "test.db"),
        audit_log_path=str(tmp_path / "audit.log"),
        poll_interval=0.02,
        idle_timeout=900,
        emr_modules=FIXTURE_EMR_MODULES,
        emr_processes=FIXTURE_EMR_PROCESSES,
    )

    db = Database(config.db_path)
    audit = AuditLogger(config.audit_log_path)
    redaction = shared_redaction_engine
    detector = EMRDetector(config.emr_modules, config.emr_processes)
    aggregator = SessionAggregator(
        agent_id=config.agent_id,
        redaction_engine=redaction,
        db=db,
        audit=audit,
        config=config,
    )
    tracker = UIATracker(
        emr_detector=detector,
        event_callback=aggregator.on_event,
        poll_interval=config.poll_interval,
    )

    hwnds = {100: ("Accuro - Patient Search", "chrome.exe"),
             200: ("Accuro - Appointment Schedule", "chrome.exe"),
             300: ("Accuro - Billing", "chrome.exe"),
             0: ("", "")}

    def fake_get_text(hwnd):
        return hwnds.get(hwnd, ("", ""))[0]

    def fake_get_pid(hwnd):
        return (1, hwnd * 10)

    class FakeProcess:
        def __init__(self, pid):
            self._name = hwnds.get(pid // 10, ("", "chrome.exe"))[1]
        def name(self):
            return self._name

    call_count = [0]
    def side_hwnd():
        idx = min(call_count[0], len(WINDOW_SEQUENCE) - 1)
        hwnd = WINDOW_SEQUENCE[idx][0]
        call_count[0] += 1
        return hwnd

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psu:

        mock_gui.GetForegroundWindow.side_effect = side_hwnd
        mock_gui.GetWindowText.side_effect = fake_get_text
        mock_proc.GetWindowThreadProcessId.side_effect = fake_get_pid
        mock_psu.Process.side_effect = FakeProcess

        tracker.start()
        time.sleep(0.3)
        tracker.stop()

    aggregator.force_close()

    # Verify JSON file exists and is well-formed
    workflow_files = list((tmp_path / "workflows").glob("*.json"))
    assert len(workflow_files) == 1, f"Expected 1 workflow file, got {len(workflow_files)}"

    data = json.loads(workflow_files[0].read_text(encoding="utf-8"))
    assert data["agent_id"] == "vm-integration-test"
    assert data["phi_redacted"] is True
    assert data["step_count"] >= 1
    assert "redaction_applied_at" in data["audit"]

    # Verify audit log was written
    audit_content = Path(config.audit_log_path).read_text(encoding="utf-8")
    assert "SESSION_START" in audit_content
    assert "SESSION_CLOSE" in audit_content

    # Verify SQLite record
    row = db.get_session(data["session_id"])
    assert row is not None
    assert row["phi_redacted"] == 1
