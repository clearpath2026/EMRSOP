import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from agent.storage.db import Database
from agent.storage.audit_log import AuditLogger
from agent.tracker.event_models import (
    WorkflowSession, WorkflowStep, EMRType, WorkflowType
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(str(tmp_path / "audit.log"))


def _make_session():
    return WorkflowSession(
        session_id="sess_db01",
        agent_id="vm-01",
        emr=EMRType.ACCURO,
        workflow_type=WorkflowType.PATIENT_SEARCH,
        started_at=datetime(2026, 5, 28, 9, 0, 0),
        ended_at=datetime(2026, 5, 28, 9, 5, 0),
        duration_seconds=300.0,
        step_count=2,
        steps=[
            WorkflowStep(
                step=1, action="Opened patient search",
                module="patient_search",
                timestamp=datetime(2026, 5, 28, 9, 0, 0),
            )
        ],
    )


def test_db_creates_schema(db):
    tables = db.list_tables()
    assert "sessions" in tables
    assert "events" in tables
    assert "screenshots" in tables
    assert "audit_log" in tables


def test_db_save_session(db):
    session = _make_session()
    db.save_session(session)
    row = db.get_session("sess_db01")
    assert row is not None
    assert row["session_id"] == "sess_db01"
    assert row["emr"] == "accuro"
    assert row["workflow_type"] == "patient_search"


def test_db_save_session_idempotent(db):
    session = _make_session()
    db.save_session(session)
    db.save_session(session)  # second save should not raise
    row = db.get_session("sess_db01")
    assert row is not None


def test_audit_log_writes_entry(audit, tmp_path):
    audit.log("SESSION_START", session_id="sess_001", agent_id="vm-01")
    log_path = Path(audit.log_path)
    content = log_path.read_text(encoding="utf-8")
    assert "SESSION_START" in content
    assert "sess_001" in content


def test_audit_log_is_append_only(audit, tmp_path):
    audit.log("SESSION_START", session_id="sess_001", agent_id="vm-01")
    audit.log("SESSION_CLOSE", session_id="sess_001", agent_id="vm-01")
    log_path = Path(audit.log_path)
    lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert "SESSION_START" in lines[0]
    assert "SESSION_CLOSE" in lines[1]


def test_uploader_raises_not_implemented():
    from agent.storage.uploader import upload_session
    with pytest.raises(NotImplementedError):
        upload_session("sess_001", "/path/to/file.json")
