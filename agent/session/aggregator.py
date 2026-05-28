import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from agent.tracker.event_models import (
    EMRType, WorkflowSession, WorkflowStep, WorkflowType
)

IDLE_TIMEOUT_SECONDS = 900


class SessionAggregator:
    def __init__(self, agent_id: str, redaction_engine, db, audit, config):
        self._agent_id = agent_id
        self._redact = redaction_engine.redact
        self._db = db
        self._audit = audit
        self._config = config
        self._current_session: Optional[WorkflowSession] = None
        self._last_event_time: Optional[datetime] = None

    def on_event(
        self, emr: str, module: str, window_title: str, event_type: str
    ) -> None:
        now = datetime.utcnow()

        if self._current_session and self._last_event_time:
            idle = (now - self._last_event_time).total_seconds()
            if idle > IDLE_TIMEOUT_SECONDS:
                self._close_session(now)

        if not self._current_session:
            self._start_session(emr, now)

        self._last_event_time = now
        redacted_title = self._redact(window_title)
        step_num = len(self._current_session.steps) + 1
        action = f"Navigated to {module.replace('_', ' ')} — {redacted_title}"

        self._current_session.steps.append(
            WorkflowStep(step=step_num, action=action, module=module, timestamp=now)
        )
        self._current_session.step_count = step_num

    def force_close(self) -> None:
        if self._current_session:
            self._close_session(datetime.utcnow())

    def _start_session(self, emr: str, now: datetime) -> None:
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        emr_type = EMRType(emr) if emr in EMRType._value2member_map_ else EMRType.UNKNOWN
        self._current_session = WorkflowSession(
            session_id=session_id,
            agent_id=self._agent_id,
            emr=emr_type,
            started_at=now,
        )
        self._audit.log("SESSION_START", session_id=session_id, agent_id=self._agent_id)

    def _close_session(self, now: datetime) -> None:
        session = self._current_session
        session.ended_at = now
        session.duration_seconds = (now - session.started_at).total_seconds()

        from agent.session.workflow_classifier import classify_workflow
        modules = [s.module for s in session.steps]
        session.workflow_type = classify_workflow(modules)

        from agent.session.exporter import export_session
        export_session(session, self._config.workflows_dir)
        self._db.save_session(session)
        self._audit.log(
            "SESSION_CLOSE",
            session_id=session.session_id,
            agent_id=self._agent_id,
            detail=f"steps={session.step_count} workflow={session.workflow_type.value}",
        )
        self._current_session = None
        self._last_event_time = None
