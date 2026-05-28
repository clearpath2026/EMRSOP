import sqlite3
from pathlib import Path
from typing import Optional
from agent.tracker.event_models import WorkflowSession

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    emr TEXT NOT NULL,
    workflow_type TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_seconds REAL,
    step_count INTEGER DEFAULT 0,
    phi_redacted INTEGER DEFAULT 1,
    uploaded INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    module TEXT,
    control_label TEXT,
    control_type TEXT,
    field_name TEXT,
    repeat_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS screenshots (
    screenshot_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    file_path TEXT NOT NULL,
    module TEXT,
    event_type TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    session_id TEXT,
    agent_id TEXT,
    detail TEXT
);
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def list_tables(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        return [r["name"] for r in rows]

    def save_session(self, session: WorkflowSession):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                  (session_id, agent_id, emr, workflow_type,
                   started_at, ended_at, duration_seconds, step_count, phi_redacted)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    session.session_id,
                    session.agent_id,
                    session.emr.value,
                    session.workflow_type.value,
                    session.started_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.duration_seconds,
                    session.step_count,
                    1 if session.phi_redacted else 0,
                ),
            )

    def get_session(self, session_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None
