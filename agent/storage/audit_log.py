from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    def __init__(self, log_path: str):
        self.log_path = log_path
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, **kwargs):
        ts = datetime.now(timezone.utc).isoformat()
        parts = [ts, event_type] + [f"{k}={v}" for k, v in kwargs.items()]
        line = "  ".join(parts) + "\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)
