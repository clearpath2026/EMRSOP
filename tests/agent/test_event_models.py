import pytest
from datetime import datetime
from agent.tracker.event_models import (
    EMRType, EventType, WorkflowType,
    RawEvent, RedactedEvent, WorkflowStep,
    ScreenshotMeta, WorkflowSession,
)


def test_raw_event_auto_generates_id():
    ev = RawEvent(session_id="s1", agent_id="a1", event_type=EventType.WINDOW_FOCUS)
    assert ev.event_id.startswith("evt_")
    assert len(ev.event_id) > 4


def test_raw_event_has_no_field_value():
    ev = RawEvent(session_id="s1", agent_id="a1", event_type=EventType.WINDOW_FOCUS)
    assert not hasattr(ev, "field_value_raw") or ev.field_value_raw is None


def test_redacted_event_repeat_count_default():
    ev = RedactedEvent(
        event_id="evt_abc",
        session_id="s1",
        agent_id="a1",
        timestamp=datetime.utcnow(),
        emr=EMRType.ACCURO,
        event_type=EventType.WINDOW_FOCUS,
        window_title="[REDACTED]",
        control_label="",
        control_type="",
        module="patient_search",
    )
    assert ev.repeat_count == 1


def test_workflow_session_defaults():
    session = WorkflowSession(
        session_id="sess_001",
        agent_id="vm-01",
        emr=EMRType.OSCAR,
        started_at=datetime.utcnow(),
    )
    assert session.phi_redacted is True
    assert session.steps == []
    assert session.screenshots == []
    assert session.workflow_type == WorkflowType.UNKNOWN


def test_workflow_session_duration():
    start = datetime(2026, 5, 28, 9, 0, 0)
    end = datetime(2026, 5, 28, 9, 6, 30)
    session = WorkflowSession(
        session_id="sess_002",
        agent_id="vm-01",
        emr=EMRType.PS_SUITE,
        started_at=start,
        ended_at=end,
        duration_seconds=(end - start).total_seconds(),
    )
    assert session.duration_seconds == 390.0
