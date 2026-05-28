# Phase 1: Agent Windows Service — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the local-only Windows service that tracks EMR activity on agent GCP VMs, redacts PHI locally, captures blurred screenshots, groups events into sessions, and exports structured workflow JSON files — with no network calls and no raw PHI ever written to disk.

**Architecture:** A Python Windows service (`EMRTrackerService`) runs on each dedicated agent VM. A polling loop checks the foreground window every 200ms, identifies the active EMR and module, pipes all text through a local Presidio redaction engine before storage, triggers blurred screenshots on module navigation changes, groups events into sessions with 15-minute idle timeout, and flushes closed sessions to SQLite + JSON files under `C:\ProgramData\EMRTracker\data\`.

**Tech Stack:** Python 3.11, pywin32, psutil, presidio-analyzer 2.x, presidio-anonymizer 2.x, spacy en_core_web_lg, mss, Pillow, pytesseract, pydantic v2, sqlite3 (stdlib), pytest, pytest-mock, pyyaml

---

## File Map

| File | Responsibility |
|------|---------------|
| `agent/tracker/event_models.py` | Pydantic models: `RawEvent`, `RedactedEvent`, `WorkflowStep`, `ScreenshotMeta`, `WorkflowSession` |
| `agent/service/config.py` | Loads `config.yaml`, exposes typed `Config` dataclass |
| `agent/tracker/emr_detector.py` | `EMRDetector.detect(title, process)` → `(emr, module)` |
| `agent/redaction/patterns.py` | Regex constants: OHIP, PHN, postal code |
| `agent/redaction/recognizers.py` | `OHIPRecognizer`, `CanadianPostalCodeRecognizer` (Presidio PatternRecognizer) |
| `agent/redaction/engine.py` | `RedactionEngine` singleton, `redact(text) -> str` |
| `agent/screenshots/capture.py` | `capture_emr_window(hwnd) -> PIL.Image` |
| `agent/screenshots/redactor.py` | `blur_text_regions(image) -> PIL.Image` |
| `agent/session/aggregator.py` | `SessionAggregator.on_event(...)` — session lifecycle |
| `agent/session/workflow_classifier.py` | `classify_workflow(modules: list[str]) -> WorkflowType` |
| `agent/session/exporter.py` | `export_session(session, output_dir)` → `{date}_{id}.json` |
| `agent/storage/db.py` | `Database` — SQLite schema init + `save_session`, `save_event` |
| `agent/storage/audit_log.py` | `AuditLogger.log(event_type, **kwargs)` — append-only |
| `agent/storage/uploader.py` | Stub only — `upload_session()` raises `NotImplementedError` |
| `agent/tracker/uia_tracker.py` | `UIATracker` — polling loop, calls `on_event` callback |
| `agent/service/main.py` | `EMRTrackerService` pywin32 `ServiceFramework` entry point |
| `agent/service/install_service.py` | CLI: `install`, `uninstall`, `start`, `stop` |
| `config/config.yaml` | Sample config (agent_id, paths, EMR module mappings) |
| `tests/conftest.py` | Windows API mocks injected via `sys.modules` |
| `tests/agent/test_event_models.py` | Model validation tests |
| `tests/agent/test_emr_detector.py` | EMR detection tests |
| `tests/agent/test_redaction.py` | Pattern, recognizer, and engine tests |
| `tests/agent/test_screenshots.py` | Capture and blur tests (mocked mss + pytesseract) |
| `tests/agent/test_session.py` | Aggregator, classifier, exporter tests |
| `tests/agent/test_storage.py` | DB and audit log tests |
| `tests/agent/test_uia_tracker.py` | Tracker polling tests (mocked win32gui) |
| `tests/agent/test_integration.py` | End-to-end: fake events → JSON file on disk |

---

## Task 1: Project Scaffold

**Files:**
- Create: `agent/__init__.py`, `agent/tracker/__init__.py`, `agent/redaction/__init__.py`, `agent/screenshots/__init__.py`, `agent/session/__init__.py`, `agent/storage/__init__.py`, `agent/service/__init__.py`
- Create: `agent/pyproject.toml`
- Create: `agent/requirements.txt`
- Create: `config/config.yaml`
- Create: `tests/__init__.py`, `tests/agent/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create all `__init__.py` files**

```bash
mkdir -p agent/tracker agent/redaction agent/screenshots agent/session agent/storage agent/service
mkdir -p tests/agent config
touch agent/__init__.py agent/tracker/__init__.py agent/redaction/__init__.py
touch agent/screenshots/__init__.py agent/session/__init__.py
touch agent/storage/__init__.py agent/service/__init__.py
touch tests/__init__.py tests/agent/__init__.py
```

- [ ] **Step 2: Create `agent/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "emr-agent"
version = "1.0.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.setuptools.packages.find]
where = ["."]
include = ["agent*"]
```

- [ ] **Step 3: Create `agent/requirements.txt`**

```
presidio-analyzer==2.2.356
presidio-anonymizer==2.2.356
spacy==3.7.4
en_core_web_lg @ https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.7.1/en_core_web_lg-3.7.1-py3-none-any.whl
pydantic>=2.0,<3.0
pyyaml>=6.0
mss>=9.0
Pillow>=10.0
pytesseract>=0.3.10
pywin32>=306
psutil>=5.9
pytest>=8.0
pytest-mock>=3.12
```

- [ ] **Step 4: Create `config/config.yaml`**

```yaml
agent_id: "vm-agent-01"

data_dir: "C:\\ProgramData\\EMRTracker\\data"
workflows_dir: "C:\\ProgramData\\EMRTracker\\data\\workflows"
screenshots_dir: "C:\\ProgramData\\EMRTracker\\data\\screenshots"
db_path: "C:\\ProgramData\\EMRTracker\\data\\emr_tracker.db"
audit_log_path: "C:\\ProgramData\\EMRTracker\\data\\audit.log"

poll_interval: 0.2
idle_timeout: 900

emr_modules:
  accuro:
    patient_search: ["Patient Search", "Find Patient"]
    appointment_scheduling: ["Appointment", "Schedule", "Calendar"]
    billing: ["Billing", "Invoice", "Claims"]
    clinical_notes: ["Chart", "Clinical Notes", "SOAP"]
  oscar:
    patient_search: ["Search", "Patient Lookup"]
    appointment_scheduling: ["Appointments", "Scheduler"]
    billing: ["Billing", "MSP"]
    clinical_notes: ["Chart", "Notes"]
  ps_suite:
    patient_search: ["Patient Search", "Patient List"]
    appointment_scheduling: ["Appointment Book", "Schedule"]
    billing: ["Billing", "Insurance"]
    clinical_notes: ["Clinical Notes", "Chart"]

emr_processes:
  accuro:
    process_names: ["chrome.exe", "msedge.exe"]
    window_title_patterns: ["Accuro", "QHR Accuro"]
  oscar:
    process_names: ["chrome.exe", "msedge.exe"]
    window_title_patterns: ["OSCAR", "Oscar Pro", "OSCAR EMR"]
  ps_suite:
    process_names: ["PSS.exe", "PSSuite.exe"]
    window_title_patterns: ["PS Suite", "PS EMR", "TELUS PS Suite"]
```

- [ ] **Step 5: Create `tests/conftest.py`** (injects Windows API mocks so tests run on any OS)

```python
import sys
from unittest.mock import MagicMock

# Inject before any agent imports touch these modules
_WIN_MODULES = [
    "win32gui", "win32process", "win32api", "win32con",
    "win32service", "win32serviceutil", "win32event",
    "servicemanager", "pywintypes", "winerror",
]
for _mod in _WIN_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Mock mss so screenshot tests don't need a display
if "mss" not in sys.modules:
    sys.modules["mss"] = MagicMock()
```

- [ ] **Step 6: Verify pytest can collect (no tests yet)**

```bash
cd C:\Users\Mark Montalbo\Documents\EMRSOP
pip install -r agent/requirements.txt
python -m spacy download en_core_web_lg
pytest --collect-only
```

Expected output: `no tests ran` (no errors)

- [ ] **Step 7: Commit**

```bash
git init
git add agent/ config/ tests/ docs/
git commit -m "feat: project scaffold — directories, deps, Windows API mocks"
```

---

## Task 2: Data Models

**Files:**
- Create: `agent/tracker/event_models.py`
- Create: `tests/agent/test_event_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_event_models.py
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_event_models.py -v
```

Expected: `ImportError: cannot import name 'EMRType' from 'agent.tracker.event_models'`

- [ ] **Step 3: Create `agent/tracker/event_models.py`**

```python
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class EMRType(str, Enum):
    ACCURO = "accuro"
    OSCAR = "oscar"
    PS_SUITE = "ps_suite"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    WINDOW_FOCUS = "window_focus"
    NAVIGATION = "navigation"
    BUTTON_CLICK = "button_click"
    FIELD_FOCUS = "field_focus"
    SCREENSHOT_TRIGGER = "screenshot_trigger"


class WorkflowType(str, Enum):
    APPOINTMENT_BOOKING = "appointment_booking"
    PATIENT_SEARCH = "patient_search"
    INSURANCE_VERIFICATION = "insurance_verification"
    CHART_UPDATE = "chart_update"
    INBOUND_CALL = "inbound_call"
    UNKNOWN = "unknown"


class RawEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:9]}")
    session_id: str
    agent_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    emr: EMRType = EMRType.UNKNOWN
    event_type: EventType
    window_title: str = ""
    control_label: str = ""
    control_type: str = ""
    module: str = "unknown_module"
    field_name: Optional[str] = None
    field_type: Optional[str] = None
    # field_value_raw is intentionally absent — never capture field values


class RedactedEvent(BaseModel):
    event_id: str
    session_id: str
    agent_id: str
    timestamp: datetime
    emr: EMRType
    event_type: EventType
    window_title: str
    control_label: str
    control_type: str
    module: str
    field_name: Optional[str] = None
    field_type: Optional[str] = None
    repeat_count: int = 1


class WorkflowStep(BaseModel):
    step: int
    action: str
    module: str
    timestamp: datetime
    screenshot_id: Optional[str] = None


class ScreenshotMeta(BaseModel):
    screenshot_id: str
    file_path: str
    module: str
    event_type: str
    timestamp: datetime


class WorkflowSession(BaseModel):
    session_id: str
    agent_id: str
    emr: EMRType
    workflow_type: WorkflowType = WorkflowType.UNKNOWN
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    step_count: int = 0
    steps: list[WorkflowStep] = Field(default_factory=list)
    screenshots: list[ScreenshotMeta] = Field(default_factory=list)
    phi_redacted: bool = True
    audit: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/agent/test_event_models.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/tracker/event_models.py tests/agent/test_event_models.py
git commit -m "feat: Pydantic data models for events, sessions, screenshots"
```

---

## Task 3: Config Loader

**Files:**
- Create: `agent/service/config.py`
- Create: `tests/agent/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_config.py
import pytest
from pathlib import Path
from agent.service.config import load_config, Config

FIXTURE_CONFIG = Path(__file__).parent.parent.parent / "config" / "config.yaml"


def test_load_config_returns_config_object():
    cfg = load_config(FIXTURE_CONFIG)
    assert isinstance(cfg, Config)


def test_load_config_emr_modules_loaded():
    cfg = load_config(FIXTURE_CONFIG)
    assert "accuro" in cfg.emr_modules
    assert "patient_search" in cfg.emr_modules["accuro"]
    assert isinstance(cfg.emr_modules["accuro"]["patient_search"], list)


def test_load_config_emr_processes_loaded():
    cfg = load_config(FIXTURE_CONFIG)
    assert "ps_suite" in cfg.emr_processes
    assert "PSS.exe" in cfg.emr_processes["ps_suite"]["process_names"]


def test_load_config_poll_interval():
    cfg = load_config(FIXTURE_CONFIG)
    assert cfg.poll_interval == 0.2


def test_load_config_idle_timeout():
    cfg = load_config(FIXTURE_CONFIG)
    assert cfg.idle_timeout == 900
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_config.py -v
```

Expected: `ImportError: cannot import name 'load_config'`

- [ ] **Step 3: Create `agent/service/config.py`**

```python
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


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data.get("agent_id") == "vm-agent-01":
        data["agent_id"] = socket.gethostname()
    return Config(**data)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/agent/test_config.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/service/config.py tests/agent/test_config.py
git commit -m "feat: config loader from config.yaml with hostname injection"
```

---

## Task 4: EMR Detector

**Files:**
- Create: `agent/tracker/emr_detector.py`
- Create: `tests/agent/test_emr_detector.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_emr_detector.py
import pytest
from pathlib import Path
from agent.service.config import load_config
from agent.tracker.emr_detector import EMRDetector

FIXTURE_CONFIG = Path(__file__).parent.parent.parent / "config" / "config.yaml"


@pytest.fixture
def detector():
    cfg = load_config(FIXTURE_CONFIG)
    return EMRDetector(cfg.emr_modules, cfg.emr_processes)


def test_detects_accuro_by_title(detector):
    emr, module = detector.detect("Accuro EMR - Patient Search", "chrome.exe")
    assert emr == "accuro"
    assert module == "patient_search"


def test_detects_oscar_appointment(detector):
    emr, module = detector.detect("OSCAR - Appointments", "chrome.exe")
    assert emr == "oscar"
    assert module == "appointment_scheduling"


def test_detects_ps_suite_billing(detector):
    emr, module = detector.detect("PS Suite - Billing Module", "PSS.exe")
    assert emr == "ps_suite"
    assert module == "billing"


def test_unknown_app_returns_none(detector):
    emr, module = detector.detect("Microsoft Excel", "excel.exe")
    assert emr is None
    assert module is None


def test_known_process_unknown_module_returns_unknown_module(detector):
    emr, module = detector.detect("QHR Accuro - Settings", "chrome.exe")
    assert emr == "accuro"
    assert module == "unknown_module"


def test_case_insensitive_title_match(detector):
    emr, module = detector.detect("accuro emr - calendar view", "chrome.exe")
    assert emr == "accuro"
    assert module == "appointment_scheduling"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_emr_detector.py -v
```

Expected: `ImportError: cannot import name 'EMRDetector'`

- [ ] **Step 3: Create `agent/tracker/emr_detector.py`**

```python
from typing import Optional, Tuple, Dict, List


class EMRDetector:
    def __init__(
        self,
        emr_modules: Dict[str, Dict[str, List[str]]],
        emr_processes: Dict[str, Dict],
    ):
        self._modules = emr_modules
        self._processes = emr_processes

    def detect(
        self, window_title: str, process_name: str
    ) -> Tuple[Optional[str], Optional[str]]:
        title_lower = window_title.lower()
        process_lower = process_name.lower()

        for emr, proc_cfg in self._processes.items():
            process_match = any(
                p.lower() == process_lower for p in proc_cfg["process_names"]
            )
            title_match = any(
                pat.lower() in title_lower
                for pat in proc_cfg["window_title_patterns"]
            )
            if not (process_match and title_match):
                continue

            # EMR identified — now find the module
            for module, keywords in self._modules.get(emr, {}).items():
                if any(kw.lower() in title_lower for kw in keywords):
                    return emr, module

            return emr, "unknown_module"

        return None, None
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/agent/test_emr_detector.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/tracker/emr_detector.py tests/agent/test_emr_detector.py
git commit -m "feat: EMR detector — identifies active EMR app and module from window title"
```

---

## Task 5: PHI Redaction — Patterns, Recognizers, Engine

**Files:**
- Create: `agent/redaction/patterns.py`
- Create: `agent/redaction/recognizers.py`
- Create: `agent/redaction/engine.py`
- Create: `tests/agent/test_redaction.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_redaction.py
import re
import pytest
from agent.redaction.patterns import OHIP_PATTERN, CA_POSTAL_CODE_PATTERN
from agent.redaction.recognizers import OHIPRecognizer, CanadianPostalCodeRecognizer
from agent.redaction.engine import RedactionEngine


# --- Pattern tests (pure regex, no Presidio) ---

def test_ohip_pattern_matches_standard():
    assert re.search(OHIP_PATTERN, "OHIP: 1234 567 890")

def test_ohip_pattern_matches_no_separators():
    assert re.search(OHIP_PATTERN, "1234567890")

def test_ohip_pattern_no_false_positive_short():
    assert not re.search(OHIP_PATTERN, "123 456")

def test_postal_code_pattern_matches_ontario():
    assert re.search(CA_POSTAL_CODE_PATTERN, "M5V 3A8")

def test_postal_code_pattern_matches_no_space():
    assert re.search(CA_POSTAL_CODE_PATTERN, "K1A0A9")

def test_postal_code_pattern_no_us_zip():
    assert not re.search(CA_POSTAL_CODE_PATTERN, "10001")


# --- Recognizer tests ---

def test_ohip_recognizer_entity_type():
    r = OHIPRecognizer()
    assert r.supported_entities == ["OHIP_NUMBER"]

def test_postal_code_recognizer_entity_type():
    r = CanadianPostalCodeRecognizer()
    assert r.supported_entities == ["CA_POSTAL_CODE"]


# --- Engine tests ---

@pytest.fixture(scope="module")
def engine():
    return RedactionEngine()

def test_engine_redacts_person_name(engine):
    result = engine.redact("Patient John Smith called today")
    assert "John Smith" not in result
    assert "[REDACTED_NAME]" in result

def test_engine_redacts_ohip_number(engine):
    result = engine.redact("OHIP: 1234 567 890")
    assert "1234 567 890" not in result
    assert "[REDACTED_ID]" in result

def test_engine_redacts_phone_number(engine):
    result = engine.redact("Call back at 416-555-0123")
    assert "416-555-0123" not in result
    assert "[REDACTED_PHONE]" in result

def test_engine_returns_empty_string_unchanged(engine):
    assert engine.redact("") == ""

def test_engine_returns_non_phi_unchanged(engine):
    result = engine.redact("Navigated to appointment scheduling tab")
    assert result == "Navigated to appointment scheduling tab"

def test_engine_redacts_postal_code(engine):
    result = engine.redact("Address: 123 Main St, Toronto, ON M5V 3A8")
    assert "M5V 3A8" not in result
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_redaction.py -v
```

Expected: `ImportError: cannot import name 'OHIP_PATTERN'`

- [ ] **Step 3: Create `agent/redaction/patterns.py`**

```python
OHIP_PATTERN = r"\b\d{4}[-\s]?\d{3}[-\s]?\d{3}\b"
CA_POSTAL_CODE_PATTERN = r"\b[A-Za-z]\d[A-Za-z][\s\-]?\d[A-Za-z]\d\b"
PHONE_CA_PATTERN = r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
DOB_CONTEXT_KEYWORDS = ["dob", "date of birth", "born", "birthdate", "birth date"]
```

- [ ] **Step 4: Create `agent/redaction/recognizers.py`**

```python
from presidio_analyzer import PatternRecognizer, Pattern
from agent.redaction.patterns import OHIP_PATTERN, CA_POSTAL_CODE_PATTERN


class OHIPRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="OHIP_NUMBER",
            patterns=[Pattern("OHIP_NUMBER_PATTERN", OHIP_PATTERN, 0.9)],
            context=["ohip", "health card", "health number", "insurance number"],
        )


class CanadianPostalCodeRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="CA_POSTAL_CODE",
            patterns=[Pattern("CA_POSTAL_PATTERN", CA_POSTAL_CODE_PATTERN, 0.85)],
            context=["postal", "zip", "address", "code", "city"],
        )
```

- [ ] **Step 5: Create `agent/redaction/engine.py`**

```python
from __future__ import annotations
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from agent.redaction.recognizers import OHIPRecognizer, CanadianPostalCodeRecognizer

_OPERATOR_CONFIG = {
    "PERSON": OperatorConfig("replace", {"new_value": "[REDACTED_NAME]"}),
    "OHIP_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_ID]"}),
    "CA_POSTAL_CODE": OperatorConfig("replace", {"new_value": "[REDACTED_ADDR]"}),
    "DATE_TIME": OperatorConfig("replace", {"new_value": "[REDACTED_DOB]"}),
    "LOCATION": OperatorConfig("replace", {"new_value": "[REDACTED_ADDR]"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_PHONE]"}),
    "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED_TEXT]"}),
}


class RedactionEngine:
    def __init__(self):
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()
        registry.add_recognizer(OHIPRecognizer())
        registry.add_recognizer(CanadianPostalCodeRecognizer())
        self._analyzer = AnalyzerEngine(registry=registry)
        self._anonymizer = AnonymizerEngine()

    def redact(self, text: str, language: str = "en") -> str:
        if not text or not text.strip():
            return text
        results = self._analyzer.analyze(text=text, language=language)
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=_OPERATOR_CONFIG,
        )
        return anonymized.text
```

- [ ] **Step 6: Run tests to verify pass**

```bash
pytest tests/agent/test_redaction.py -v
```

Expected: `13 passed`

- [ ] **Step 7: Commit**

```bash
git add agent/redaction/ tests/agent/test_redaction.py
git commit -m "feat: PHI redaction engine — Presidio + OHIP/postal code recognizers"
```

---

## Task 6: Screenshot Capture and Blur

**Files:**
- Create: `agent/screenshots/capture.py`
- Create: `agent/screenshots/redactor.py`
- Create: `tests/agent/test_screenshots.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_screenshots.py
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import numpy as np


def _make_image(width=800, height=600):
    return Image.fromarray(
        np.zeros((height, width, 3), dtype=np.uint8), mode="RGB"
    )


def test_capture_returns_pil_image():
    from agent.screenshots.capture import capture_emr_window

    mock_sct = MagicMock()
    mock_sct.__enter__ = lambda s: s
    mock_sct.__exit__ = MagicMock(return_value=False)
    mock_sct.grab.return_value = MagicMock(
        __array_interface__={
            "shape": (600, 800, 4),
            "typestr": "|u1",
            "data": bytes(600 * 800 * 4),
            "version": 3,
        }
    )

    with patch("agent.screenshots.capture.win32gui") as mock_win32:
        mock_win32.GetWindowRect.return_value = (100, 100, 900, 700)
        with patch("agent.screenshots.capture.mss.mss", return_value=mock_sct):
            img = capture_emr_window(hwnd=12345)

    assert isinstance(img, Image.Image)


def test_blur_text_regions_returns_pil_image():
    from agent.screenshots.redactor import blur_text_regions

    img = _make_image()
    fake_df = {
        "level": [5, 5],
        "left": [10, 200],
        "top": [20, 100],
        "width": [80, 120],
        "height": [20, 25],
        "text": ["John Smith", "M5V 3A8"],
        "conf": [90, 85],
    }

    with patch("agent.screenshots.redactor.pytesseract.image_to_data") as mock_ocr:
        import pandas as pd
        mock_ocr.return_value = pd.DataFrame(fake_df)
        result = blur_text_regions(img)

    assert isinstance(result, Image.Image)
    assert result.size == img.size


def test_blur_no_text_returns_original_dimensions():
    from agent.screenshots.redactor import blur_text_regions

    img = _make_image()
    with patch("agent.screenshots.redactor.pytesseract.image_to_data") as mock_ocr:
        import pandas as pd
        mock_ocr.return_value = pd.DataFrame({
            "level": [], "left": [], "top": [],
            "width": [], "height": [], "text": [], "conf": [],
        })
        result = blur_text_regions(img)

    assert result.size == img.size
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_screenshots.py -v
```

Expected: `ImportError: cannot import name 'capture_emr_window'`

- [ ] **Step 3: Create `agent/screenshots/capture.py`**

```python
from PIL import Image
import mss
import win32gui


def capture_emr_window(hwnd: int) -> Image.Image:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    region = {"top": top, "left": left, "width": right - left, "height": bottom - top}
    with mss.mss() as sct:
        raw = sct.grab(region)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
```

- [ ] **Step 4: Create `agent/screenshots/redactor.py`**

```python
from PIL import Image, ImageFilter
import pytesseract
import pandas as pd

_CONF_THRESHOLD = 60
_BLUR_RADIUS = 15


def blur_text_regions(image: Image.Image) -> Image.Image:
    data: pd.DataFrame = pytesseract.image_to_data(
        image, output_type=pytesseract.Output.DATAFRAME
    )
    result = image.copy()

    text_rows = data[(data["level"] == 5) & (data["conf"] >= _CONF_THRESHOLD)]
    for _, row in text_rows.iterrows():
        x, y, w, h = int(row["left"]), int(row["top"]), int(row["width"]), int(row["height"])
        if w <= 0 or h <= 0:
            continue
        region = result.crop((x, y, x + w, y + h))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS))
        result.paste(blurred, (x, y))

    return result
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pip install pandas numpy
pytest tests/agent/test_screenshots.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add agent/screenshots/ tests/agent/test_screenshots.py
git commit -m "feat: screenshot capture (mss) and text blur (pytesseract + Gaussian)"
```

---

## Task 7: Workflow Classifier

**Files:**
- Create: `agent/session/workflow_classifier.py`
- Create: `tests/agent/test_session.py` (partial — classifier section)

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_session.py
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_session.py -v
```

Expected: `ImportError: cannot import name 'classify_workflow'`

- [ ] **Step 3: Create `agent/session/workflow_classifier.py`**

```python
from agent.tracker.event_models import WorkflowType


def classify_workflow(modules: list[str]) -> WorkflowType:
    module_set = set(modules)

    if ({"appointment_scheduling", "calendar"} & module_set
            and "patient_search" in module_set):
        return WorkflowType.APPOINTMENT_BOOKING

    if {"billing", "insurance"} & module_set:
        return WorkflowType.INSURANCE_VERIFICATION

    if {"clinical_notes", "chart"} & module_set:
        return WorkflowType.CHART_UPDATE

    if "patient_search" in module_set:
        return WorkflowType.PATIENT_SEARCH

    return WorkflowType.UNKNOWN
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/agent/test_session.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/session/workflow_classifier.py tests/agent/test_session.py
git commit -m "feat: workflow classifier — maps module sequences to workflow types"
```

---

## Task 8: JSON Exporter

**Files:**
- Create: `agent/session/exporter.py`
- Modify: `tests/agent/test_session.py` (add exporter tests)

- [ ] **Step 1: Add failing tests to `tests/agent/test_session.py`**

```python
# Append to tests/agent/test_session.py
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_session.py -v -k "export"
```

Expected: `ImportError: cannot import name 'export_session'`

- [ ] **Step 3: Create `agent/session/exporter.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/agent/test_session.py -v
```

Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/session/exporter.py tests/agent/test_session.py
git commit -m "feat: JSON session exporter — writes redacted workflow to disk"
```

---

## Task 9: SQLite Storage and Audit Logger

**Files:**
- Create: `agent/storage/db.py`
- Create: `agent/storage/audit_log.py`
- Create: `agent/storage/uploader.py`
- Create: `tests/agent/test_storage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_storage.py
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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_storage.py -v
```

Expected: `ImportError: cannot import name 'Database'`

- [ ] **Step 3: Create `agent/storage/db.py`**

```python
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
```

- [ ] **Step 4: Create `agent/storage/audit_log.py`**

```python
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
```

- [ ] **Step 5: Create `agent/storage/uploader.py`** (stub for Phase 2)

```python
def upload_session(session_id: str, file_path: str) -> None:
    raise NotImplementedError("Phase 2: GCP Storage upload not yet implemented")
```

- [ ] **Step 6: Run tests to verify pass**

```bash
pytest tests/agent/test_storage.py -v
```

Expected: `6 passed`

- [ ] **Step 7: Commit**

```bash
git add agent/storage/ tests/agent/test_storage.py
git commit -m "feat: SQLite storage, append-only audit logger, Phase 2 uploader stub"
```

---

## Task 10: Session Aggregator

**Files:**
- Create: `agent/session/aggregator.py`
- Modify: `tests/agent/test_session.py` (add aggregator tests)

- [ ] **Step 1: Add failing tests to `tests/agent/test_session.py`**

```python
# Append to tests/agent/test_session.py
import tempfile
from unittest.mock import MagicMock, patch
from agent.session.aggregator import SessionAggregator, IDLE_TIMEOUT_SECONDS


def _make_aggregator(tmp_path_str: str) -> SessionAggregator:
    from agent.redaction.engine import RedactionEngine
    from agent.storage.db import Database
    from agent.storage.audit_log import AuditLogger
    from agent.service.config import Config

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
        redaction_engine=RedactionEngine(),
        db=Database(cfg.db_path),
        audit=AuditLogger(cfg.audit_log_path),
        config=cfg,
    )


def test_aggregator_starts_session_on_first_event(tmp_path):
    agg = _make_aggregator(str(tmp_path))
    assert agg._current_session is None
    agg.on_event(emr="accuro", module="patient_search",
                 window_title="Accuro - Patient Search", event_type="window_focus")
    assert agg._current_session is not None
    assert agg._current_session.emr.value == "accuro"


def test_aggregator_adds_step_per_event(tmp_path):
    agg = _make_aggregator(str(tmp_path))
    agg.on_event("accuro", "patient_search", "Accuro - Patient Search", "window_focus")
    agg.on_event("accuro", "appointment_scheduling", "Accuro - Appointments", "navigation")
    assert agg._current_session.step_count == 2


def test_aggregator_force_close_writes_json(tmp_path):
    agg = _make_aggregator(str(tmp_path))
    agg.on_event("accuro", "patient_search", "Accuro - Patient Search", "window_focus")
    agg.on_event("accuro", "appointment_scheduling", "Accuro - Appointments", "navigation")
    agg.force_close()
    assert agg._current_session is None
    files = list((tmp_path / "workflows").glob("*.json"))
    assert len(files) == 1


def test_aggregator_idle_timeout_closes_session(tmp_path):
    from datetime import datetime, timedelta
    agg = _make_aggregator(str(tmp_path))
    agg.on_event("accuro", "patient_search", "Accuro - Patient Search", "window_focus")
    # Fake the last event time to exceed idle timeout
    agg._last_event_time = datetime.utcnow() - timedelta(seconds=IDLE_TIMEOUT_SECONDS + 1)
    agg.on_event("accuro", "billing", "Accuro - Billing", "window_focus")
    # New session should have started
    assert agg._current_session.step_count == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_session.py -v -k "aggregator"
```

Expected: `ImportError: cannot import name 'SessionAggregator'`

- [ ] **Step 3: Create `agent/session/aggregator.py`**

```python
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
```

- [ ] **Step 4: Run all session tests**

```bash
pytest tests/agent/test_session.py -v
```

Expected: `15 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/session/aggregator.py tests/agent/test_session.py
git commit -m "feat: session aggregator — lifecycle, idle timeout, workflow classification"
```

---

## Task 11: UIAutomation Tracker

**Files:**
- Create: `agent/tracker/uia_tracker.py`
- Create: `tests/agent/test_uia_tracker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent/test_uia_tracker.py
import time
import pytest
from unittest.mock import patch, MagicMock, call
from agent.tracker.uia_tracker import UIATracker


@pytest.fixture
def callback():
    return MagicMock()


@pytest.fixture
def detector():
    m = MagicMock()
    m.detect.return_value = ("accuro", "patient_search")
    return m


def test_tracker_calls_callback_on_window_change(callback, detector):
    tracker = UIATracker(emr_detector=detector, event_callback=callback, poll_interval=0.05)

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psutil:

        mock_gui.GetForegroundWindow.side_effect = [100, 200, 200]
        mock_gui.GetWindowText.side_effect = ["Accuro - Patient Search", "Accuro - Appointments", "Accuro - Appointments"]
        mock_proc.GetWindowThreadProcessId.return_value = (1, 999)
        mock_psutil.Process.return_value.name.return_value = "chrome.exe"
        detector.detect.side_effect = [
            ("accuro", "patient_search"),
            ("accuro", "appointment_scheduling"),
        ]

        tracker.start()
        time.sleep(0.2)
        tracker.stop()

    assert callback.call_count >= 1
    first_call = callback.call_args_list[0]
    assert first_call.kwargs["emr"] == "accuro"


def test_tracker_ignores_non_emr_windows(callback, detector):
    tracker = UIATracker(emr_detector=detector, event_callback=callback, poll_interval=0.05)
    detector.detect.return_value = (None, None)

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psutil:

        mock_gui.GetForegroundWindow.return_value = 100
        mock_gui.GetWindowText.return_value = "Microsoft Excel"
        mock_proc.GetWindowThreadProcessId.return_value = (1, 888)
        mock_psutil.Process.return_value.name.return_value = "excel.exe"

        tracker.start()
        time.sleep(0.2)
        tracker.stop()

    callback.assert_not_called()


def test_tracker_stop_terminates_thread(callback, detector):
    tracker = UIATracker(emr_detector=detector, event_callback=callback, poll_interval=0.05)

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psutil:

        mock_gui.GetForegroundWindow.return_value = 0
        mock_gui.GetWindowText.return_value = ""
        mock_proc.GetWindowThreadProcessId.return_value = (1, 0)
        mock_psutil.Process.side_effect = Exception("no process")

        tracker.start()
        assert tracker._thread.is_alive()
        tracker.stop()
        tracker._thread.join(timeout=1.0)
        assert not tracker._thread.is_alive()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/agent/test_uia_tracker.py -v
```

Expected: `ImportError: cannot import name 'UIATracker'`

- [ ] **Step 3: Create `agent/tracker/uia_tracker.py`**

```python
import threading
import time
import win32gui
import win32process
import psutil
from typing import Callable, Optional


class UIATracker:
    def __init__(
        self,
        emr_detector,
        event_callback: Callable,
        poll_interval: float = 0.2,
    ):
        self._detector = emr_detector
        self._callback = event_callback
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_hwnd: int = 0
        self._last_title: str = ""

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._check_foreground()
            except Exception:
                pass
            time.sleep(self._poll_interval)

    def _check_foreground(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)

        if hwnd == self._last_hwnd and title == self._last_title:
            return

        self._last_hwnd = hwnd
        self._last_title = title

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
        except Exception:
            return

        emr, module = self._detector.detect(title, process_name)
        if emr is None:
            return

        self._callback(
            emr=emr,
            module=module,
            window_title=title,
            event_type="window_focus",
        )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/agent/test_uia_tracker.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/tracker/uia_tracker.py tests/agent/test_uia_tracker.py
git commit -m "feat: UIAutomation tracker — polling loop, foreground window detection"
```

---

## Task 12: Windows Service Entry Point

**Files:**
- Create: `agent/service/main.py`
- Create: `agent/service/install_service.py`

> Note: The Windows service framework cannot be unit tested (requires pywin32 `ServiceFramework` registration). These files wire together the tested components. Verify by installing and running on a Windows VM.

- [ ] **Step 1: Create `agent/service/main.py`**

```python
import socket
import sys
import win32event
import win32service
import win32serviceutil
import servicemanager

from agent.service.config import load_config
from agent.tracker.emr_detector import EMRDetector
from agent.tracker.uia_tracker import UIATracker
from agent.redaction.engine import RedactionEngine
from agent.session.aggregator import SessionAggregator
from agent.storage.db import Database
from agent.storage.audit_log import AuditLogger


class EMRTrackerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "EMRTrackerService"
    _svc_display_name_ = "EMR Workflow Tracker"
    _svc_description_ = (
        "Tracks EMR activity for workflow analytics. PHIPA-compliant — "
        "no raw PHI stored or transmitted."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._tracker: UIATracker | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._tracker:
            self._tracker.stop()
        win32event.SetEvent(self._stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self._run()

    def _run(self):
        config = load_config()
        db = Database(config.db_path)
        audit = AuditLogger(config.audit_log_path)
        redaction = RedactionEngine()
        detector = EMRDetector(config.emr_modules, config.emr_processes)
        aggregator = SessionAggregator(
            agent_id=config.agent_id,
            redaction_engine=redaction,
            db=db,
            audit=audit,
            config=config,
        )
        self._tracker = UIATracker(
            emr_detector=detector,
            event_callback=aggregator.on_event,
            poll_interval=config.poll_interval,
        )
        self._tracker.start()
        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)
        aggregator.force_close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(EMRTrackerService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(EMRTrackerService)
```

- [ ] **Step 2: Create `agent/service/install_service.py`**

```python
"""
Usage (run as Administrator):
  python install_service.py install
  python install_service.py start
  python install_service.py stop
  python install_service.py remove
"""
import sys
import win32serviceutil
from agent.service.main import EMRTrackerService


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "install":
        win32serviceutil.InstallService(
            pythonClassString="agent.service.main.EMRTrackerService",
            serviceName=EMRTrackerService._svc_name_,
            displayName=EMRTrackerService._svc_display_name_,
            description=EMRTrackerService._svc_description_,
            startType=win32serviceutil.win32service.SERVICE_AUTO_START,
        )
        print(f"Service '{EMRTrackerService._svc_name_}' installed.")
    elif command == "start":
        win32serviceutil.StartService(EMRTrackerService._svc_name_)
        print("Service started.")
    elif command == "stop":
        win32serviceutil.StopService(EMRTrackerService._svc_name_)
        print("Service stopped.")
    elif command == "remove":
        win32serviceutil.RemoveService(EMRTrackerService._svc_name_)
        print("Service removed.")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add agent/service/main.py agent/service/install_service.py
git commit -m "feat: Windows service entry point and install/start/stop CLI"
```

---

## Task 13: Integration Test

**Files:**
- Create: `tests/agent/test_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/agent/test_integration.py
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


def test_full_pipeline_produces_json(tmp_path):
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
    redaction = RedactionEngine()
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

    seq = iter(WINDOW_SEQUENCE)

    def fake_get_foreground():
        try:
            return next(seq)[0]
        except StopIteration:
            return 0

    hwnds = {100: ("Accuro - Patient Search", "chrome.exe"),
             200: ("Accuro - Appointment Schedule", "chrome.exe"),
             300: ("Accuro - Billing", "chrome.exe"),
             0: ("", "")}

    def fake_get_text(hwnd):
        return hwnds.get(hwnd, ("", ""))[0]

    def fake_get_pid(hwnd):
        return (1, hwnd * 10)

    import psutil as _psutil
    _orig_process = _psutil.Process

    class FakeProcess:
        def __init__(self, pid):
            self._name = hwnds.get(pid // 10, ("", "chrome.exe"))[1]
        def name(self):
            return self._name

    with patch("agent.tracker.uia_tracker.win32gui") as mock_gui, \
         patch("agent.tracker.uia_tracker.win32process") as mock_proc, \
         patch("agent.tracker.uia_tracker.psutil") as mock_psu:

        call_count = [0]
        def side_hwnd():
            idx = min(call_count[0], len(WINDOW_SEQUENCE) - 1)
            hwnd = WINDOW_SEQUENCE[idx][0]
            call_count[0] += 1
            return hwnd

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
```

- [ ] **Step 2: Run the integration test**

```bash
pytest tests/agent/test_integration.py -v
```

Expected: `1 passed`

- [ ] **Step 3: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass, 0 failures.

- [ ] **Step 4: Commit**

```bash
git add tests/agent/test_integration.py
git commit -m "test: end-to-end integration — events → redacted JSON + audit log + SQLite"
```

---

## Task 14: Wire Screenshots Into the Live Pipeline

**Files:**
- Modify: `agent/tracker/uia_tracker.py` — pass `hwnd` in callback
- Modify: `agent/session/aggregator.py` — trigger screenshot on module change
- Modify: `tests/agent/test_uia_tracker.py` — update callback assertion
- Modify: `tests/agent/test_session.py` — update aggregator tests

- [ ] **Step 1: Update `UIATracker._check_foreground` to pass `hwnd`**

Replace the `self._callback(...)` call at the bottom of `_check_foreground` with:

```python
        self._callback(
            emr=emr,
            module=module,
            window_title=title,
            event_type="window_focus",
            hwnd=hwnd,
        )
```

- [ ] **Step 2: Update `SessionAggregator.on_event` signature and add screenshot trigger**

Replace the `on_event` method in `agent/session/aggregator.py`:

```python
    def on_event(
        self,
        emr: str,
        module: str,
        window_title: str,
        event_type: str,
        hwnd: int = 0,
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

        screenshot_id = None
        if hwnd and module != "unknown_module":
            screenshot_id = self._try_capture_screenshot(hwnd, module, now)

        self._current_session.steps.append(
            WorkflowStep(
                step=step_num,
                action=action,
                module=module,
                timestamp=now,
                screenshot_id=screenshot_id,
            )
        )
        self._current_session.step_count = step_num
```

Add `_try_capture_screenshot` method to `SessionAggregator`:

```python
    def _try_capture_screenshot(
        self, hwnd: int, module: str, now: datetime
    ) -> str | None:
        try:
            from agent.screenshots.capture import capture_emr_window
            from agent.screenshots.redactor import blur_text_regions
            import uuid
            from pathlib import Path

            screenshot_id = f"scr_{uuid.uuid4().hex[:8]}"
            img = capture_emr_window(hwnd)
            blurred = blur_text_regions(img)

            screenshots_dir = Path(self._config.screenshots_dir)
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            file_path = screenshots_dir / f"{self._current_session.session_id}_{screenshot_id}.png"
            blurred.save(str(file_path))

            from agent.tracker.event_models import ScreenshotMeta
            self._current_session.screenshots.append(
                ScreenshotMeta(
                    screenshot_id=screenshot_id,
                    file_path=str(file_path),
                    module=module,
                    event_type="navigation",
                    timestamp=now,
                )
            )
            self._audit.log("SCREENSHOT_SAVED", session_id=self._current_session.session_id,
                           detail=f"module={module} file={file_path.name}")
            return screenshot_id
        except Exception:
            return None
```

- [ ] **Step 3: Update tracker test to pass `hwnd` kwarg**

In `tests/agent/test_uia_tracker.py`, update the assertion in `test_tracker_calls_callback_on_window_change`:

```python
    first_call = callback.call_args_list[0]
    assert first_call.kwargs["emr"] == "accuro"
    assert "hwnd" in first_call.kwargs
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass (the aggregator tests use `hwnd=0` default so they continue to work without screenshots).

- [ ] **Step 5: Commit**

```bash
git add agent/tracker/uia_tracker.py agent/session/aggregator.py tests/agent/
git commit -m "feat: wire screenshot capture into aggregator on module navigation events"
```

---

## Acceptance Criteria

Before Phase 1 is considered complete, verify manually on a Windows VM:

- [ ] `python agent/service/install_service.py install` registers the service in Windows Services
- [ ] `python agent/service/install_service.py start` starts the service without errors
- [ ] Open Accuro/OSCAR in Chrome or PS Suite — window title changes appear in `audit.log`
- [ ] After 2 minutes of activity, force-stop the service and verify a `.json` file appears in `C:\ProgramData\EMRTracker\data\workflows\`
- [ ] Open the JSON file — confirm no real patient names, OHIP numbers, or addresses appear anywhere
- [ ] Screenshots in `C:\ProgramData\EMRTracker\data\screenshots\` have blurred text regions
- [ ] `audit.log` contains `SESSION_START`, `REDACTION_RUN`, `SESSION_CLOSE` entries
