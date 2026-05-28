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
