# EMR Workflow Intelligence System — Design Spec
**Date:** 2026-05-28  
**Status:** Approved  
**Scope:** Full system (Phase 1 + Phase 2)

---

## 1. Problem Statement

A BPO operation handles Canadian clinic EMR tasks on behalf of clinics using Accuro EMR, OSCAR Pro, and PS Suite. Agents perform appointment booking, patient search, insurance verification, chart updates, and inbound call handling. Currently there is no structured capture of how agents perform these tasks, no automated SOP generation, and no QA or coaching feedback loop.

This system observes agent EMR activity, converts it into structured workflows, generates SOPs and QA reports via AI, and provides an admin dashboard for BPO operations analytics — while maintaining strict PHIPA compliance throughout.

---

## 2. Constraints & Compliance Requirements

- **PHIPA (Ontario):** No raw PHI may be stored or transmitted. All PHI must be redacted locally before touching any storage layer.
- **Data residency:** Cloud infrastructure in `northamerica-northeast1` (Montreal, GCP) or `northamerica-northeast2` (Toronto, GCP).
- **No service account key files:** GCP authentication via Workload Identity Federation (Application Default Credentials on VM).
- **Data minimization:** Only redacted, structured event data is stored. Raw field values are never captured.
- **Audit trail:** Every session, redaction pass, file write, and cloud upload is logged in an append-only audit log.
- **Access control:** Role-based (admin, supervisor, qa_reviewer, trainer). No agent can access another agent's data.

---

## 3. System Architecture

### 3.1 Overview

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT WINDOWS VM (GCP — 1 dedicated VM per agent)          │
│                                                             │
│  ┌─────────────────┐   ┌──────────────────┐                │
│  │ UIAutomation    │──▶│ PHI Redaction    │                │
│  │ Tracker         │   │ Engine (local)   │                │
│  └─────────────────┘   └────────┬─────────┘                │
│                                 │                           │
│  ┌─────────────────┐   ┌────────▼─────────┐                │
│  │ Screenshot      │   │ Session          │                │
│  │ Service         │   │ Aggregator       │                │
│  └────────┬────────┘   └────────┬─────────┘                │
│           │                     │                           │
│           └──────────┬──────────┘                           │
│                      ▼                                       │
│           ┌──────────────────────┐                          │
│           │ Local Storage        │                          │
│           │ SQLite + JSON files  │                          │
│           │ (DPAPI encrypted)    │                          │
│           └──────────┬───────────┘                          │
└──────────────────────┼──────────────────────────────────────┘
                       │ TLS 1.3 · Workload Identity
                       │ Redacted events only (Phase 2)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  GCP CLOUD LAYER (northamerica-northeast1)      [PHASE 2]   │
│                                                             │
│  FastAPI (Cloud Run) ──▶ AI SOP Engine (Claude Sonnet)      │
│  Analytics (BigQuery) ──▶ Storage (Cloud Storage + CMEK)    │
│  Audit (Cloud Audit Logs) ──▶ Secrets (Secret Manager)      │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  ADMIN DASHBOARD — React / Next.js (Cloud Run)  [PHASE 2]  │
│                                                             │
│  Agent Analytics · QA Reports · AI Coach · SOP Library     │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 EMR Target Applications

| EMR | Access Method | Tracking Approach |
|-----|--------------|-------------------|
| Accuro EMR | Web app (browser via RDP) | UIAutomation accessibility tree on Chrome/Edge |
| OSCAR Pro | Web app (browser via RDP) | UIAutomation accessibility tree on Chrome/Edge |
| PS Suite | Native Windows application | UIAutomation Win32/COM API |

All three EMRs are accessed by agents via **RDP into dedicated GCP Windows VMs**. The tracker runs as a Windows service on the VM itself, not on the agent's local machine.

---

## 4. Component Designs

### 4.1 UIAutomation Tracker (`agent/tracker/`)

**Runtime:** Python Windows service (`pywin32` ServiceFramework)  
**Libraries:** `pywinauto`, `comtypes`, `pywin32`

The tracker hooks into the Windows UIAutomation event system using `SetWinEventHook` for system-level events and `comtypes` UIAutomation for structural navigation.

**Captured events:**
- `EVENT_SYSTEM_FOREGROUND` — window focus changes
- `EVENT_OBJECT_NAMECHANGE` — control label changes (navigation updates)
- `EVENT_OBJECT_INVOKED` — button/control activation (clicks)
- `EVENT_OBJECT_FOCUS` — form field focus (captures field name + type, never value)
- `EVENT_SYSTEM_MOVESIZEEND` — window resize/move (session context)

**EMR Detection (`emr_detector.py`):**

```python
EMR_SIGNATURES = {
    "accuro": {
        "process_names": ["chrome.exe", "msedge.exe"],
        "window_title_patterns": ["Accuro", "QHR Accuro"],
    },
    "oscar": {
        "process_names": ["chrome.exe", "msedge.exe"],
        "window_title_patterns": ["OSCAR", "Oscar Pro"],
    },
    "ps_suite": {
        "process_names": ["PSS.exe", "PSSuite.exe"],
        "window_title_patterns": ["PS Suite", "PS EMR"],
    },
}
```

**Module detection:**  
EMR module (e.g., `appointment_scheduling`, `patient_search`) is derived from window title substring matching against a configurable module map per EMR. Falls back to `unknown_module` if no match.

**What is NOT captured:**
- Raw text typed into any field
- Clipboard contents
- Screenshots on keystroke
- Any field value (input, textarea, select value)

### 4.2 PHI Redaction Engine (`agent/redaction/`)

**Library:** `presidio-analyzer` + `presidio-anonymizer` (Microsoft, runs fully offline)  
**NER model:** `en_core_web_lg` (spaCy, local)

All text fields in a raw event pass through the redaction engine before being written to any storage. There is no raw events table.

**Recognizer stack:**

| PHI Type | Method | Token |
|----------|--------|-------|
| Person names | spaCy NER (`PERSON` entity) | `[REDACTED_NAME]` |
| OHIP numbers | Regex `\b\d{4}[-\s]?\d{3}[-\s]?\d{3}\b` | `[REDACTED_ID]` |
| PHN (other provinces) | Province-specific regex patterns | `[REDACTED_ID]` |
| Date of birth | Presidio `DATE_TIME` + context keywords (`dob`, `born`, `birth`) | `[REDACTED_DOB]` |
| Canadian addresses | Presidio `LOCATION` + postal code regex `[A-Z]\d[A-Z]\s?\d[A-Z]\d` | `[REDACTED_ADDR]` |
| Phone numbers | Presidio `PHONE_NUMBER` | `[REDACTED_PHONE]` |
| Free-text (catch-all) | NER over all string fields | `[REDACTED_TEXT]` |

**Redaction fields per event:**
- `window_title` — redacted
- `control_label` — redacted
- `field_name` — redacted
- `field_value_raw` — **never populated at source**

**Engine initialisation** (at service start, not per-event):
```python
analyzer = AnalyzerEngine()
analyzer.registry.add_recognizer(OHIPRecognizer())
analyzer.registry.add_recognizer(CanadianPostalCodeRecognizer())
anonymizer = AnonymizerEngine()
```

### 4.3 Screenshot Service (`agent/screenshots/`)

**Libraries:** `mss` (capture), `Pillow` (image ops), `pytesseract` (text region detection)

Screenshots are **event-triggered only** — never on a timer or on keystroke.

**Trigger conditions:**
- EMR module navigation change
- Patient chart opened
- Appointment created or modified
- Billing/insurance section accessed
- Error dialog appears

**Capture pipeline:**
1. Get active EMR window bounds via `win32gui.GetWindowRect`
2. Capture that region only (never full desktop)
3. Run `pytesseract.image_to_data` to get bounding boxes of all text regions
4. Apply `ImageFilter.GaussianBlur(radius=15)` to every text bounding box
5. Save blurred image — **original is never written to disk**
6. Attach metadata: `session_id`, `timestamp`, `module`, `event_type`, `screenshot_id`

### 4.4 Session Aggregator (`agent/session/`)

**Storage:** SQLite (encrypted via DPAPI wrapper)

The aggregator maintains an in-memory event buffer per active session and flushes to SQLite + JSON on session close.

**Session boundary detection:**

| Trigger | Action |
|---------|--------|
| Windows login (`WM_WTSSESSION_CHANGE`) | Start new session |
| EMR process opens | Start/resume EMR session |
| 15-minute idle (no UIAutomation events) | Close + flush session |
| Patient record switch (window title change pattern) | End workflow, start new |
| EMR process closes | Close + flush session |
| Windows logout / screen lock | Force-flush all open sessions |

**Workflow classification (`workflow_classifier.py`):**

Classifies a completed session into a workflow type based on the sequence of modules visited:

| Workflow Type | Module Sequence Signal |
|---------------|------------------------|
| `appointment_booking` | `patient_search` → `appointment_scheduling` → `calendar` |
| `patient_search` | `patient_search` only (no appointment) |
| `insurance_verification` | `billing` or `insurance` module present |
| `chart_update` | `clinical_notes` or `chart` module present |
| `inbound_call` | `patient_search` + short session duration (<3 min) |
| `unknown` | No match |

**Event compression:**  
Consecutive duplicate events within 500ms (e.g., rapid clicks on the same control) are compressed to a single event with a `repeat_count` field.

**JSON export (`exporter.py`):**  
Writes one `{session_id}.json` file per closed session to `/data/workflows/`. Filename pattern: `{YYYY-MM-DD}_{session_id}.json`.

### 4.5 Local Storage (`agent/storage/`)

**Layout on VM:**
```
C:\ProgramData\EMRTracker\
├── data\
│   ├── workflows\          ← redacted JSON session files
│   ├── screenshots\        ← blurred PNG files
│   ├── emr_tracker.db      ← SQLite database
│   └── audit.log           ← append-only audit trail
└── config\
    └── config.yaml         ← agent ID, EMR signatures, timeouts
```

**Encryption:**  
The `C:\ProgramData\EMRTracker\data\` folder is protected using Windows EFS (Encrypting File System) tied to the `emr-tracker-svc` service account. Only that account can read the files.

**Module-to-window-title mapping (sample, configurable in `config.yaml`):**

```yaml
emr_modules:
  accuro:
    patient_search:     ["Patient Search", "Find Patient"]
    appointment_scheduling: ["Appointment", "Schedule", "Calendar"]
    billing:            ["Billing", "Invoice", "Claims"]
    clinical_notes:     ["Chart", "Clinical Notes", "SOAP"]
  oscar:
    patient_search:     ["Search", "Patient Lookup"]
    appointment_scheduling: ["Appointments", "Scheduler"]
    billing:            ["Billing", "MSP"]
  ps_suite:
    patient_search:     ["Patient Search", "Patient List"]
    appointment_scheduling: ["Appointment Book", "Schedule"]
    billing:            ["Billing", "Insurance"]
```

**SQLite schema (core tables):**

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    emr TEXT NOT NULL,
    workflow_type TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    step_count INTEGER DEFAULT 0,
    phi_redacted INTEGER DEFAULT 1,
    uploaded INTEGER DEFAULT 0,   -- Phase 2: sync flag
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    module TEXT,
    control_label TEXT,           -- already redacted
    control_type TEXT,
    field_name TEXT,              -- already redacted
    repeat_count INTEGER DEFAULT 1
);

CREATE TABLE screenshots (
    screenshot_id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(session_id),
    file_path TEXT NOT NULL,
    module TEXT,
    event_type TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,     -- SESSION_START, REDACTION_RUN, JSON_EXPORT, etc.
    session_id TEXT,
    agent_id TEXT,
    detail TEXT
);
```

### 4.6 Cloud API (`api/`) — Phase 2

**Runtime:** FastAPI on GCP Cloud Run (`northamerica-northeast1`)  
**Auth:** GCP Identity tokens (Workload Identity — no key files)

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/sessions` | Ingest redacted workflow JSON from agent VM |
| `GET` | `/v1/sop/{session_id}` | Return generated SOP for a session |
| `POST` | `/v1/sop/generate` | Trigger Claude SOP generation for a session |
| `GET` | `/v1/analytics/agents` | Agent-level analytics summary |
| `GET` | `/v1/analytics/workflows` | Workflow efficiency metrics |
| `GET` | `/v1/coach/{agent_id}` | AI Coach report for an agent |
| `GET` | `/v1/audit` | Paginated audit log (admin only) |

**SOP Generator (`api/app/services/sop_generator.py`):**

Calls Claude Sonnet (`claude-sonnet-4-6`) with a structured prompt:

```python
SYSTEM_PROMPT = """
You are a clinical workflow analyst for a Canadian BPO handling EMR operations.
Convert the structured workflow JSON into a clear Standard Operating Procedure (SOP).

Output format:
1. Workflow title and EMR system
2. Prerequisites
3. Step-by-step procedure (numbered, imperative verbs)
4. Expected outcome
5. Common errors and how to avoid them

Rules:
- Never invent steps not present in the workflow data
- Use [REDACTED] tokens as-is — do not attempt to infer patient identity
- Flag any unusual step sequences as a QA note
"""
```

**AI Coach (`api/app/services/workflow_analyzer.py`):**

Compares agent step count and module sequence against the optimal path (stored per workflow type in Firestore). Outputs:
- Efficiency score (0–100)
- Deviation list ("step 4 skipped patient confirmation")
- Coaching recommendation

### 4.7 Admin Dashboard (`dashboard/`) — Phase 2

**Stack:** Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui  
**Auth:** Firebase Auth (Google SSO) + RBAC middleware

**Pages:**

| Route | Description |
|-------|-------------|
| `/dashboard` | Fleet overview — all agents, workflow counts, avg efficiency |
| `/dashboard/[agentId]` | Individual agent drill-down — timeline, scores, deviations |
| `/qa` | QA report list — SOP compliance scores, missing steps |
| `/coach` | AI Coach — side-by-side optimal vs actual workflow |
| `/sop` | SOP library — browse, search, export generated SOPs |
| `/audit` | Audit log viewer — filterable by date, agent, event type |

---

## 5. Data Models

### 5.1 Raw UIAutomation Event (never stored, immediately redacted)

```json
{
  "event_id": "evt_01JWX4K2M",
  "session_id": "sess_abc123",
  "agent_id": "vm-agent-01",
  "timestamp": "2026-05-28T09:14:32.441Z",
  "emr": "accuro",
  "event_type": "click",
  "window_title": "<raw — redacted before storage>",
  "control_label": "<raw — redacted before storage>",
  "control_type": "Button",
  "module": "appointment_scheduling",
  "field_name": null,
  "field_type": null,
  "field_value_raw": null
}
```

### 5.2 Redacted Workflow Session (stored + exported)

```json
{
  "session_id": "sess_abc123",
  "agent_id": "vm-agent-01",
  "emr": "accuro",
  "workflow_type": "appointment_booking",
  "started_at": "2026-05-28T09:12:05.000Z",
  "ended_at": "2026-05-28T09:18:44.000Z",
  "duration_seconds": 399,
  "step_count": 11,
  "steps": [
    {
      "step": 1,
      "action": "Opened patient search module",
      "module": "patient_search",
      "timestamp": "2026-05-28T09:12:05.000Z",
      "screenshot_id": "scr_01"
    },
    {
      "step": 2,
      "action": "Selected patient record [REDACTED_NAME]",
      "module": "patient_search",
      "timestamp": "2026-05-28T09:12:18.000Z",
      "screenshot_id": null
    }
  ],
  "screenshots": [
    {
      "screenshot_id": "scr_01",
      "file": "screenshots/sess_abc123_scr_01.png",
      "module": "patient_search",
      "event_type": "module_open"
    }
  ],
  "phi_redacted": true,
  "audit": {
    "redaction_engine_version": "1.0.0",
    "redaction_applied_at": "2026-05-28T09:18:44.100Z"
  }
}
```

---

## 6. Security Model

### Phase 1 (Local VM)

| Layer | Mechanism |
|-------|-----------|
| Data at rest | Windows EFS (Encrypting File System) on `/data/` folder, tied to `emr-tracker-svc` service account — folder-level encryption, zero key management |
| Service isolation | Dedicated Windows service account, no network access (firewall rule) |
| PHI redaction | Presidio runs locally, no external API calls |
| Screenshots | Original never written to disk; blur applied before save |
| Audit trail | Append-only flat file; no delete operations |
| Field values | Blocked at tracker level — `field_value_raw` never populated |

### Phase 2 (Cloud)

| Layer | Mechanism |
|-------|-----------|
| Transit encryption | TLS 1.3 (enforced by Cloud Run load balancer) |
| VM-to-cloud auth | GCP Workload Identity Federation (ADC on VM, no key files) |
| Cloud storage | Cloud Storage + CMEK (Cloud KMS, Canadian key ring) |
| Secrets | GCP Secret Manager (Anthropic API key, etc.) |
| Dashboard auth | Firebase Auth (Google SSO) + JWT verification middleware |
| RBAC roles | `admin`, `supervisor`, `qa_reviewer`, `trainer` |
| Audit | GCP Cloud Audit Logs + custom audit trail in Firestore |
| Data residency | Org policy enforces `northamerica-northeast1` / `northamerica-northeast2` |

---

## 7. Folder Structure

```
emrsop/
├── agent/                          ← Python Windows service
│   ├── tracker/
│   │   ├── __init__.py
│   │   ├── emr_detector.py         ← EMR app + module identification
│   │   ├── uia_tracker.py          ← UIAutomation event hook
│   │   └── event_models.py         ← Pydantic models
│   ├── redaction/
│   │   ├── engine.py               ← Presidio setup + redact()
│   │   ├── recognizers.py          ← OHIP, PHN, postal code recognizers
│   │   └── patterns.py             ← regex constants
│   ├── screenshots/
│   │   ├── capture.py              ← mss window crop
│   │   └── redactor.py             ← pytesseract + Gaussian blur
│   ├── session/
│   │   ├── aggregator.py           ← session lifecycle + event grouping
│   │   ├── workflow_classifier.py  ← module sequence → workflow type
│   │   └── exporter.py             ← JSON file writer
│   ├── storage/
│   │   ├── db.py                   ← SQLite schema + EFS folder setup helpers
│   │   ├── audit_log.py            ← append-only audit writer
│   │   └── uploader.py             ← scaffolded in Phase 1, activated in Phase 2 (GCP Storage sync)
│   ├── service/
│   │   ├── main.py                 ← Windows service entry point
│   │   ├── config.py               ← config.yaml loader
│   │   └── install_service.py      ← service registration + EFS setup
│   ├── requirements.txt
│   └── pyproject.toml
│
├── api/                            ← FastAPI (Phase 2, Cloud Run)
│   ├── app/
│   │   ├── main.py
│   │   ├── auth.py                 ← GCP Identity token middleware
│   │   ├── models.py               ← Pydantic request/response models
│   │   ├── routes/
│   │   │   ├── ingest.py
│   │   │   ├── sop.py
│   │   │   ├── analytics.py
│   │   │   └── audit.py
│   │   └── services/
│   │       ├── sop_generator.py    ← Claude Sonnet integration
│   │       ├── workflow_analyzer.py ← efficiency scoring + AI Coach
│   │       └── storage.py          ← GCP Cloud Storage + Firestore
│   ├── Dockerfile
│   ├── requirements.txt
│   └── cloudbuild.yaml
│
├── dashboard/                      ← Next.js admin (Phase 2)
│   ├── src/
│   │   ├── app/
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── qa/page.tsx
│   │   │   ├── coach/page.tsx
│   │   │   ├── sop/page.tsx
│   │   │   └── audit/page.tsx
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   └── Dockerfile
│
├── infra/                          ← GCP Terraform + scripts
│   ├── terraform/
│   └── scripts/
│
├── docs/
│   ├── superpowers/specs/          ← this file
│   └── compliance/                 ← PHIPA data flow, retention policy
│
├── .gitignore                      ← excludes /data/, *.db, .env, .superpowers/
└── README.md
```

---

## 8. Phase Breakdown

### Phase 1 — Local MVP (builds now, no cloud credentials needed)

**Deliverables:**
- [ ] `agent/tracker/` — UIAutomation event hook, EMR detection
- [ ] `agent/redaction/` — Presidio engine, OHIP/PHN recognizers
- [ ] `agent/screenshots/` — event-triggered capture, blur pipeline
- [ ] `agent/session/` — session aggregator, workflow classifier, JSON exporter
- [ ] `agent/storage/` — SQLite schema, audit log, EFS setup
- [ ] `agent/service/` — Windows service, installer, config

**Success criteria:**
- Agent opens Accuro/OSCAR/PS Suite via RDP
- Tracker captures window events, module navigation, button clicks
- All text fields redacted before storage
- Screenshots triggered on module changes, text regions blurred
- Session closed → `{date}_{session_id}.json` written to `/data/workflows/`
- Audit log records every redaction pass and file write

### Phase 2 — Cloud + AI + Dashboard

**Deliverables:**
- [ ] `agent/storage/uploader.py` — background sync from VM to GCP Storage
- [ ] `api/` — FastAPI on Cloud Run, ingest + SOP generation + analytics
- [ ] Claude Sonnet integration — workflow JSON → SOP + QA report
- [ ] `dashboard/` — Next.js admin dashboard, all 5 pages
- [ ] `infra/terraform/` — Cloud Run, Storage, Firestore, IAM, Workload Identity
- [ ] AI Coach engine — efficiency scoring + deviation detection

**Success criteria:**
- Agent VM auto-syncs completed sessions to GCP Storage
- Supervisor triggers SOP generation → receives Claude-generated SOP document
- Dashboard shows per-agent efficiency scores and QA compliance
- AI Coach identifies workflow deviations vs optimal path

---

## 9. Open Questions (resolved during spec)

| Question | Decision |
|----------|----------|
| EMR access method | RDP into dedicated GCP Windows VMs |
| EMR types | Accuro (web), OSCAR (web), PS Suite (native Win32) |
| Tracking approach | UIAutomation only (Approach B) — single unified pipeline |
| Cloud provider | GCP, Canadian region, Workload Identity (no key files) |
| AI provider | Anthropic Claude Sonnet |
| Phase 1 scope | Local-only, no cloud credentials needed |
| Data residency | `northamerica-northeast1` (Montreal) enforced at org policy |
