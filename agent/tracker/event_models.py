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
    # field_value_raw intentionally absent — never capture field values


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
