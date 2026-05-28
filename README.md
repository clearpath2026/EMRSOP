# EMRSOP — EMR Workflow Tracker

A PHIPA-compliant Windows service that silently captures EMR workflow activity on agent VMs, redacts PHI locally, and exports structured JSON files ready for SOP generation and QA analytics.

Built for Canadian healthcare BPO operations running **Accuro**, **OSCAR Pro**, and **PS Suite**.

---

## How it works

```
Agent opens Accuro/OSCAR/PS Suite
        ↓
UIAutomation polls foreground window every 200ms
        ↓
EMR Detector identifies app + module (patient search, billing, etc.)
        ↓
PHI Redaction (Presidio + OHIP/postal recognizers) — runs locally, offline
        ↓
Screenshot captured → text regions Gaussian-blurred
        ↓
Session Aggregator groups events (15-min idle timeout)
        ↓
On session close: JSON exported + SQLite record + audit log entry
```

No raw PHI is ever written to disk. All redaction happens in-process before any storage.

---

## Prerequisites

Install these on each agent GCP Windows VM **before running the installer**:

| Requirement | Version | Download |
|-------------|---------|----------|
| Python | 3.11+ | [python.org](https://python.org) — check "Add to PATH" |
| Tesseract OCR | 5.x | [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki) — install to `C:\Program Files\Tesseract-OCR\` |
| Git (optional) | any | [git-scm.com](https://git-scm.com) — only needed to clone this repo |

> Tesseract is required for screenshot text-blurring. The service will run without it but screenshots will not be blurred.

---

## Installation

### Step 1 — Get the code onto the VM

**Option A — Clone with Git:**
```bat
git clone https://github.com/YOUR_ORG/EMRSOP.git C:\EMRTracker
```

**Option B — Download ZIP:**
Download the ZIP from GitHub, extract to `C:\EMRTracker`.

### Step 2 — Run the installer (as Administrator)

Right-click `install.bat` → **Run as administrator**

The installer will:
1. Create `C:\ProgramData\EMRTracker\` data directories
2. Copy `config\config.yaml` to `C:\ProgramData\EMRTracker\config\` (first install only)
3. Install all Python dependencies (`pip install -r agent/requirements.txt`)
4. Download the spaCy `en_core_web_lg` model (~560 MB, one-time)
5. Register and start the `EMRTrackerService` Windows service

The service starts automatically on every VM boot after installation.

### Step 3 — Edit the config (optional)

Open `C:\ProgramData\EMRTracker\config\config.yaml` in Notepad to customise:

```yaml
agent_id: "vm-agent-01"        # Change to match your VM name / agent ID

poll_interval: 0.2              # Seconds between foreground window checks (default 200ms)
idle_timeout: 900               # Seconds of inactivity before session closes (default 15 min)

data_dir: "C:\\ProgramData\\EMRTracker\\data"
workflows_dir: "C:\\ProgramData\\EMRTracker\\data\\workflows"
screenshots_dir: "C:\\ProgramData\\EMRTracker\\data\\screenshots"
```

Restart the service after editing:
```bat
sc stop EMRTrackerService
sc start EMRTrackerService
```

---

## Verifying it works

**Check service status:**
```bat
sc query EMRTrackerService
```
Expected: `STATE: 4  RUNNING`

**Watch the audit log in real time:**
```bat
powershell Get-Content C:\ProgramData\EMRTracker\data\audit.log -Wait
```

**After an agent works in Accuro/OSCAR/PS Suite**, workflow JSON files appear in:
```
C:\ProgramData\EMRTracker\data\workflows\
```

Each file is named `YYYY-MM-DD_sess_XXXXXXXX.json` and contains:
- `session_id`, `agent_id`, `emr`, `workflow_type`
- `steps[]` — timestamped sequence of module navigations (all window titles redacted)
- `screenshots[]` — metadata for blurred screenshot files
- `phi_redacted: true`
- `audit.redaction_applied_at` — ISO timestamp proving redaction ran

---

## Output files

| Path | Contents |
|------|----------|
| `data\workflows\*.json` | Redacted workflow sessions (one file per session) |
| `data\screenshots\*.png` | Blurred screenshots (text regions Gaussian-blurred) |
| `data\emr_tracker.db` | SQLite database — session index + event records |
| `data\audit.log` | Append-only audit trail (SESSION_START, SESSION_CLOSE, SCREENSHOT_SAVED) |

---

## Supported EMRs

| EMR | Access mode | Detected by |
|-----|-------------|-------------|
| Accuro (QHR) | Chrome / Edge | Window title contains "Accuro" or "QHR Accuro" |
| OSCAR Pro | Chrome / Edge | Window title contains "OSCAR", "Oscar Pro", or "OSCAR EMR" |
| PS Suite (TELUS) | Native Win32 | Process `PSS.exe` or `PSSuite.exe` |

Add more EMRs or modules by editing the `emr_modules` and `emr_processes` sections in `config.yaml`.

---

## Service management

All commands require Administrator privileges:

```bat
:: Check status
sc query EMRTrackerService

:: Start / stop / restart
sc start EMRTrackerService
sc stop EMRTrackerService

:: Or use the installer script
python agent\service\install_service.py start
python agent\service\install_service.py stop
```

---

## Uninstalling

Right-click `uninstall.bat` → **Run as administrator**

This stops and removes the Windows service. Data in `C:\ProgramData\EMRTracker\data\` is preserved — delete it manually if you want a clean removal.

---

## Running tests

Tests run on any Windows machine (no actual EMR or display required — Windows APIs and screen capture are mocked):

```bat
cd C:\EMRTracker
pip install pytest pytest-mock
pytest tests\ -v
```

Expected: **58 passed**

---

## Project structure

```
EMRSOP\
├── install.bat                     # One-click installer (run as Admin)
├── uninstall.bat                   # Service removal
├── config\
│   └── config.yaml                 # EMR definitions and paths
├── agent\
│   ├── requirements.txt
│   ├── tracker\
│   │   ├── event_models.py         # Pydantic data models
│   │   ├── emr_detector.py         # Window title → EMR + module
│   │   └── uia_tracker.py          # 200ms polling loop
│   ├── redaction\
│   │   ├── patterns.py             # OHIP, postal code regex
│   │   ├── recognizers.py          # Presidio custom recognizers
│   │   └── engine.py               # RedactionEngine (Presidio wrapper)
│   ├── screenshots\
│   │   ├── capture.py              # mss screen capture
│   │   └── redactor.py             # Tesseract + Gaussian blur
│   ├── session\
│   │   ├── aggregator.py           # Session lifecycle + idle timeout
│   │   ├── workflow_classifier.py  # Module sequence → WorkflowType
│   │   └── exporter.py             # WorkflowSession → JSON file
│   ├── storage\
│   │   ├── db.py                   # SQLite schema + save/query
│   │   ├── audit_log.py            # Append-only audit log
│   │   └── uploader.py             # Phase 2 stub (GCP upload)
│   └── service\
│       ├── config.py               # Config loader
│       ├── main.py                 # EMRTrackerService (pywin32)
│       └── install_service.py      # install / start / stop / remove CLI
└── tests\
    ├── conftest.py                 # Windows API mocks + shared fixtures
    └── agent\
        ├── test_event_models.py
        ├── test_config.py
        ├── test_emr_detector.py
        ├── test_redaction.py
        ├── test_screenshots.py
        ├── test_session.py
        ├── test_storage.py
        ├── test_uia_tracker.py
        └── test_integration.py     # End-to-end pipeline test
```

---

## Privacy and compliance

- **No raw PHI is stored at any point.** Redaction runs in-process before any write.
- Window titles, control labels, and all text go through Microsoft Presidio (local, offline) before storage.
- Custom recognizers handle Canadian-specific identifiers: OHIP numbers and postal codes.
- Screenshots have all detected text regions Gaussian-blurred before saving.
- `phi_redacted: true` and `redaction_applied_at` are written to every JSON file as a verifiable audit trail.
- All data stays on the local VM disk (Phase 1). Phase 2 will add encrypted upload to GCP northamerica-northeast1 (Montreal) for PHIPA data residency.

---

## Phase 2 (coming next)

- FastAPI service on Cloud Run — aggregates data from all VMs
- Claude AI SOP generator — turns workflow JSON into step-by-step SOPs
- React / Next.js admin dashboard — QA analytics, workflow review
- GCP Workload Identity Federation upload — no JSON key files
- Cloud Storage (CMEK) + Firestore + BigQuery backend
