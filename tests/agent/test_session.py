import pytest
from agent.tracker.event_models import WorkflowType
from agent.session.workflow_classifier import classify_workflow


def test_classifies_appointment_booking():
    modules = ["patient_search", "appointment_scheduling", "calendar"]
    assert classify_workflow(modules) == WorkflowType.APPOINTMENT_BOOKING


def test_classifies_patient_search_only():
    modules = ["patient_search"]
    assert classify_workflow(modules) == WorkflowType.PATIENT_SEARCH


def test_classifies_insurance_verification():
    modules = ["patient_search", "billing"]
    assert classify_workflow(modules) == WorkflowType.INSURANCE_VERIFICATION


def test_classifies_chart_update():
    modules = ["patient_search", "clinical_notes"]
    assert classify_workflow(modules) == WorkflowType.CHART_UPDATE


def test_classifies_unknown_for_empty():
    assert classify_workflow([]) == WorkflowType.UNKNOWN


def test_classifies_unknown_for_unrecognised():
    assert classify_workflow(["unknown_module", "settings"]) == WorkflowType.UNKNOWN


def test_appointment_requires_patient_search():
    # appointment_scheduling alone (without patient_search) is unknown
    modules = ["appointment_scheduling"]
    result = classify_workflow(modules)
    assert result != WorkflowType.APPOINTMENT_BOOKING


import json
import tempfile
from pathlib import Path
from datetime import datetime
from agent.session.exporter import export_session
from agent.tracker.event_models import (
    WorkflowSession, WorkflowStep, EMRType, WorkflowType
)


def _make_session() -> WorkflowSession:
    return WorkflowSession(
        session_id="sess_test01",
        agent_id="vm-test",
        emr=EMRType.ACCURO,
        workflow_type=WorkflowType.APPOINTMENT_BOOKING,
        started_at=datetime(2026, 5, 28, 9, 0, 0),
        ended_at=datetime(2026, 5, 28, 9, 10, 0),
        duration_seconds=600.0,
        step_count=3,
        steps=[
            WorkflowStep(
                step=1,
                action="Opened patient search module",
                module="patient_search",
                timestamp=datetime(2026, 5, 28, 9, 0, 0),
            ),
            WorkflowStep(
                step=2,
                action="Selected patient record [REDACTED_NAME]",
                module="patient_search",
                timestamp=datetime(2026, 5, 28, 9, 0, 30),
            ),
            WorkflowStep(
                step=3,
                action="Navigated to appointment scheduling",
                module="appointment_scheduling",
                timestamp=datetime(2026, 5, 28, 9, 1, 0),
            ),
        ],
    )


def test_export_creates_json_file():
    session = _make_session()
    with tempfile.TemporaryDirectory() as tmp:
        path = export_session(session, tmp)
        assert path.exists()
        assert path.suffix == ".json"


def test_export_filename_contains_session_id():
    session = _make_session()
    with tempfile.TemporaryDirectory() as tmp:
        path = export_session(session, tmp)
        assert "sess_test01" in path.name


def test_export_json_is_valid_and_has_steps():
    session = _make_session()
    with tempfile.TemporaryDirectory() as tmp:
        path = export_session(session, tmp)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["session_id"] == "sess_test01"
        assert data["phi_redacted"] is True
        assert len(data["steps"]) == 3
        assert data["steps"][0]["step"] == 1


def test_export_json_has_audit_timestamp():
    session = _make_session()
    with tempfile.TemporaryDirectory() as tmp:
        path = export_session(session, tmp)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "redaction_applied_at" in data["audit"]


import tempfile
from unittest.mock import MagicMock, patch
from agent.session.aggregator import SessionAggregator, IDLE_TIMEOUT_SECONDS


def _make_aggregator(tmp_path_str: str, redaction_engine=None) -> SessionAggregator:
    from agent.redaction.engine import RedactionEngine
    from agent.storage.db import Database
    from agent.storage.audit_log import AuditLogger
    from agent.service.config import Config

    if redaction_engine is None:
        redaction_engine = RedactionEngine()

    cfg = Config(
        agent_id="vm-test",
        data_dir=tmp_path_str,
        workflows_dir=tmp_path_str + "/workflows",
        screenshots_dir=tmp_path_str + "/screenshots",
        db_path=tmp_path_str + "/test.db",
        audit_log_path=tmp_path_str + "/audit.log",
        poll_interval=0.2,
        idle_timeout=900,
        emr_modules={},
        emr_processes={},
    )
    return SessionAggregator(
        agent_id="vm-test",
        redaction_engine=redaction_engine,
        db=Database(cfg.db_path),
        audit=AuditLogger(cfg.audit_log_path),
        config=cfg,
    )


def test_aggregator_starts_session_on_first_event(tmp_path, shared_redaction_engine):
    agg = _make_aggregator(str(tmp_path), shared_redaction_engine)
    assert agg._current_session is None
    agg.on_event(emr="accuro", module="patient_search",
                 window_title="Accuro - Patient Search", event_type="window_focus")
    assert agg._current_session is not None
    assert agg._current_session.emr.value == "accuro"


def test_aggregator_adds_step_per_event(tmp_path, shared_redaction_engine):
    agg = _make_aggregator(str(tmp_path), shared_redaction_engine)
    agg.on_event("accuro", "patient_search", "Accuro - Patient Search", "window_focus")
    agg.on_event("accuro", "appointment_scheduling", "Accuro - Appointments", "navigation")
    assert agg._current_session.step_count == 2


def test_aggregator_force_close_writes_json(tmp_path, shared_redaction_engine):
    agg = _make_aggregator(str(tmp_path), shared_redaction_engine)
    agg.on_event("accuro", "patient_search", "Accuro - Patient Search", "window_focus")
    agg.on_event("accuro", "appointment_scheduling", "Accuro - Appointments", "navigation")
    agg.force_close()
    assert agg._current_session is None
    files = list((tmp_path / "workflows").glob("*.json"))
    assert len(files) == 1


def test_aggregator_idle_timeout_closes_session(tmp_path, shared_redaction_engine):
    from datetime import datetime, timedelta
    agg = _make_aggregator(str(tmp_path), shared_redaction_engine)
    agg.on_event("accuro", "patient_search", "Accuro - Patient Search", "window_focus")
    # Fake the last event time to exceed idle timeout
    agg._last_event_time = datetime.utcnow() - timedelta(seconds=IDLE_TIMEOUT_SECONDS + 1)
    agg.on_event("accuro", "billing", "Accuro - Billing", "window_focus")
    # New session should have started
    assert agg._current_session.step_count == 1
