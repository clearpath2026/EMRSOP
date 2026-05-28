import json
from datetime import datetime, timezone
from pathlib import Path
from agent.tracker.event_models import WorkflowSession


def export_session(session: WorkflowSession, output_dir: str | Path) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    date_prefix = session.started_at.strftime("%Y-%m-%d")
    filename = f"{date_prefix}_{session.session_id}.json"
    file_path = output_path / filename

    session.audit["redaction_applied_at"] = datetime.now(timezone.utc).isoformat()
    session.audit["redaction_engine_version"] = "1.0.0"

    data = json.loads(session.model_dump_json())
    file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return file_path
