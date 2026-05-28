import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
import yaml

DEFAULT_CONFIG_PATH = Path("C:/ProgramData/EMRTracker/config/config.yaml")


@dataclass
class Config:
    agent_id: str
    data_dir: str
    workflows_dir: str
    screenshots_dir: str
    db_path: str
    audit_log_path: str
    poll_interval: float
    idle_timeout: int
    emr_modules: Dict[str, Dict[str, List[str]]]
    emr_processes: Dict[str, Dict]
    rdp_processes: List[str] = field(default_factory=lambda: ["mstsc.exe"])
    rdp_ocr_interval: float = 2.0


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data.get("agent_id") == "vm-agent-01":
        data["agent_id"] = socket.gethostname()
    return Config(**data)
