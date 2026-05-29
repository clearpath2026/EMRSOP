# System Tray Status UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Windows system tray icon that shows EMRTrackerService status, current EMR activity, and provides start/stop/open-log controls — all running as a background process independent of the service.

**Architecture:** A standalone `tray_app.py` script uses `pystray` to create a native Windows tray icon. A `status_reader.py` module polls the SQLite DB and `sc query` every 3 seconds to get current state. The icon color (green/yellow/red) reflects service health. The tray app is registered as a Windows Startup shortcut so it launches on login using `pythonw.exe`.

**Tech Stack:** pystray>=0.19, Pillow (already installed), pywin32 (already installed), sqlite3 (stdlib), subprocess (stdlib)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `agent/tray/__init__.py` | Create | Package marker |
| `agent/tray/status_reader.py` | Create | Read service + DB state, return TrayStatus |
| `agent/tray/tray_app.py` | Create | Icon, menu, polling loop, action handlers |
| `tests/agent/test_tray.py` | Create | Tests for status_reader logic |
| `agent/requirements.txt` | Modify | Add pystray>=0.19 |
| `setup.bat` | Modify | pip install pystray, create Startup shortcut |

---

### Task 1: Package scaffold + pystray dependency

**Files:**
- Create: `agent/tray/__init__.py`
- Modify: `agent/requirements.txt`
- Modify: `setup.bat`

- [ ] **Step 1: Create the tray package**

Create `agent/tray/__init__.py` with empty content:
```python
```

- [ ] **Step 2: Add pystray to requirements.txt**

In `agent/requirements.txt`, add after the `pytesseract` line:
```
pystray>=0.19
```

- [ ] **Step 3: Add pystray to setup.bat pip install block**

In `setup.bat`, find the `echo         Installing remaining packages...` block and add `"pystray>=0.19" ^` before `--quiet`:
```bat
    "pystray>=0.19" ^
    --quiet --no-warn-script-location
```

- [ ] **Step 4: Install pystray locally**

```bash
pip install "pystray>=0.19"
```

Expected output: `Successfully installed pystray-0.19.x`

- [ ] **Step 5: Verify import works**

```bash
python -c "import pystray; print(pystray.__version__)"
```

Expected: prints version number without error.

- [ ] **Step 6: Commit**

```bash
git add agent/tray/__init__.py agent/requirements.txt setup.bat
git commit -m "feat: add tray package scaffold and pystray dependency"
```

---

### Task 2: TrayStatus data class and status_reader

**Files:**
- Create: `agent/tray/status_reader.py`
- Create: `tests/agent/test_tray.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/agent/test_tray.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
from agent.tray.status_reader import TrayStatus, read_status

DB_PATH = "C:\\ProgramData\\EMRTracker\\data\\emr_tracker.db"


def test_tray_status_defaults():
    s = TrayStatus()
    assert s.service_running is False
    assert s.current_emr is None
    assert s.current_module is None
    assert s.session_minutes == 0
    assert s.sessions_today == 0


def test_read_status_service_running():
    mock_result = MagicMock()
    mock_result.stdout = "        STATE              : 4  RUNNING\n"
    with patch("agent.tray.status_reader.subprocess.run", return_value=mock_result), \
         patch("agent.tray.status_reader._query_db", return_value=(None, None, 0, 0)):
        status = read_status(DB_PATH)
    assert status.service_running is True


def test_read_status_service_stopped():
    mock_result = MagicMock()
    mock_result.stdout = "        STATE              : 1  STOPPED\n"
    with patch("agent.tray.status_reader.subprocess.run", return_value=mock_result), \
         patch("agent.tray.status_reader._query_db", return_value=(None, None, 0, 0)):
        status = read_status(DB_PATH)
    assert status.service_running is False


def test_read_status_with_active_session():
    mock_result = MagicMock()
    mock_result.stdout = "        STATE              : 4  RUNNING\n"
    with patch("agent.tray.status_reader.subprocess.run", return_value=mock_result), \
         patch("agent.tray.status_reader._query_db", return_value=("accuro", "patient_search", 7, 3)):
        status = read_status(DB_PATH)
    assert status.current_emr == "accuro"
    assert status.current_module == "patient_search"
    assert status.session_minutes == 7
    assert status.sessions_today == 3


def test_read_status_handles_sc_failure():
    with patch("agent.tray.status_reader.subprocess.run", side_effect=Exception("sc not found")), \
         patch("agent.tray.status_reader._query_db", return_value=(None, None, 0, 0)):
        status = read_status(DB_PATH)
    assert status.service_running is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/agent/test_tray.py -v
```

Expected: `ImportError` — `status_reader` does not exist yet.

- [ ] **Step 3: Implement status_reader.py**

Create `agent/tray/status_reader.py`:
```python
import subprocess
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TrayStatus:
    service_running: bool = False
    current_emr: Optional[str] = None
    current_module: Optional[str] = None
    session_minutes: int = 0
    sessions_today: int = 0


def read_status(db_path: str) -> TrayStatus:
    status = TrayStatus()
    try:
        result = subprocess.run(
            ["sc", "query", "EMRTrackerService"],
            capture_output=True, text=True, timeout=3
        )
        status.service_running = "RUNNING" in result.stdout
    except Exception:
        status.service_running = False

    try:
        emr, module, minutes, today = _query_db(db_path)
        status.current_emr = emr
        status.current_module = module
        status.session_minutes = minutes
        status.sessions_today = today
    except Exception:
        pass

    return status


def _query_db(db_path: str):
    conn = sqlite3.connect(db_path, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        # Most recent open session (no ended_at)
        row = conn.execute(
            "SELECT emr, workflow_type, started_at FROM sessions "
            "WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        emr = module = None
        minutes = 0
        if row:
            emr = row["emr"]
            module = row["workflow_type"]
            started = datetime.fromisoformat(row["started_at"])
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            minutes = max(0, int((now - started.replace(tzinfo=None)).total_seconds() / 60))

        # Sessions closed today
        today_str = datetime.now().strftime("%Y-%m-%d")
        count_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions "
            "WHERE ended_at IS NOT NULL AND ended_at LIKE ?",
            (f"{today_str}%",)
        ).fetchone()
        today_count = count_row["cnt"] if count_row else 0

        return emr, module, minutes, today_count
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/agent/test_tray.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/tray/status_reader.py tests/agent/test_tray.py
git commit -m "feat: TrayStatus dataclass and status_reader with sc query + SQLite polling"
```

---

### Task 3: Icon generator

**Files:**
- Modify: `agent/tray/tray_app.py` (create with icon function only)

- [ ] **Step 1: Write failing test for icon generator**

Add to `tests/agent/test_tray.py`:
```python
def test_make_icon_returns_pil_image():
    from PIL import Image
    from agent.tray.tray_app import make_icon
    img = make_icon("green")
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)


def test_make_icon_colors():
    from agent.tray.tray_app import make_icon, COLOR_GREEN, COLOR_YELLOW, COLOR_RED
    # Each color string maps to one of the three constants
    for color in ("green", "yellow", "red"):
        img = make_icon(color)
        assert img is not None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/agent/test_tray.py::test_make_icon_returns_pil_image tests/agent/test_tray.py::test_make_icon_colors -v
```

Expected: `ImportError` — `tray_app` does not exist yet.

- [ ] **Step 3: Create tray_app.py with icon generator**

Create `agent/tray/tray_app.py`:
```python
from PIL import Image, ImageDraw, ImageFont

COLOR_GREEN  = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED    = "#ef4444"

_COLOR_MAP = {
    "green":  COLOR_GREEN,
    "yellow": COLOR_YELLOW,
    "red":    COLOR_RED,
}


def make_icon(color: str) -> Image.Image:
    """Generate a 64x64 tray icon with a filled circle and 'E' letter."""
    hex_color = _COLOR_MAP.get(color, COLOR_RED)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Filled circle
    draw.ellipse((4, 4, 60, 60), fill=hex_color)
    # White "E" centered
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "E", font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (64 - text_w) // 2
    y = (64 - text_h) // 2
    draw.text((x, y), "E", fill="white", font=font)
    return img
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/agent/test_tray.py::test_make_icon_returns_pil_image tests/agent/test_tray.py::test_make_icon_colors -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/tray/tray_app.py tests/agent/test_tray.py
git commit -m "feat: tray icon generator with green/yellow/red status colors"
```

---

### Task 4: Full tray app — menu, polling, action handlers

**Files:**
- Modify: `agent/tray/tray_app.py` (add menu, polling, main)

- [ ] **Step 1: Write failing test for status_to_color**

Add to `tests/agent/test_tray.py`:
```python
def test_status_to_color_running_active():
    from agent.tray.tray_app import status_to_color
    from agent.tray.status_reader import TrayStatus
    s = TrayStatus(service_running=True, current_emr="accuro", session_minutes=5)
    assert status_to_color(s) == "green"


def test_status_to_color_running_idle():
    from agent.tray.tray_app import status_to_color
    from agent.tray.status_reader import TrayStatus
    s = TrayStatus(service_running=True, current_emr=None)
    assert status_to_color(s) == "yellow"


def test_status_to_color_stopped():
    from agent.tray.tray_app import status_to_color
    from agent.tray.status_reader import TrayStatus
    s = TrayStatus(service_running=False)
    assert status_to_color(s) == "red"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/agent/test_tray.py::test_status_to_color_running_active tests/agent/test_tray.py::test_status_to_color_running_idle tests/agent/test_tray.py::test_status_to_color_stopped -v
```

Expected: `ImportError` — `status_to_color` not defined yet.

- [ ] **Step 3: Implement full tray_app.py**

Replace `agent/tray/tray_app.py` entirely:
```python
import os
import subprocess
import threading
import time
import pystray
from PIL import Image, ImageDraw, ImageFont
from agent.tray.status_reader import TrayStatus, read_status

COLOR_GREEN  = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED    = "#ef4444"

_COLOR_MAP = {"green": COLOR_GREEN, "yellow": COLOR_YELLOW, "red": COLOR_RED}

DB_PATH = r"C:\ProgramData\EMRTracker\data\emr_tracker.db"
AUDIT_LOG = r"C:\ProgramData\EMRTracker\data\audit.log"
DATA_FOLDER = r"C:\ProgramData\EMRTracker\data\workflows"
POLL_SECONDS = 3


def make_icon(color: str) -> Image.Image:
    hex_color = _COLOR_MAP.get(color, COLOR_RED)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=hex_color)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "E", font=font)
    x = (64 - (bbox[2] - bbox[0])) // 2
    y = (64 - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), "E", fill="white", font=font)
    return img


def status_to_color(status: TrayStatus) -> str:
    if not status.service_running:
        return "red"
    if status.current_emr:
        return "green"
    return "yellow"


def _build_menu(status: TrayStatus) -> pystray.Menu:
    svc_label = "Service: RUNNING ✓" if status.service_running else "Service: STOPPED ✗"
    if status.current_emr and status.current_module:
        activity = f"Now: {status.current_emr} › {status.current_module}"
    else:
        activity = "Now: Idle"
    session_label = f"Session: {status.session_minutes} min active" if status.current_emr else ""
    today_label = f"Today: {status.sessions_today} sessions saved"

    items = [
        pystray.MenuItem(svc_label, None, enabled=False),
        pystray.MenuItem(activity, None, enabled=False),
    ]
    if session_label:
        items.append(pystray.MenuItem(session_label, None, enabled=False))
    items.append(pystray.MenuItem(today_label, None, enabled=False))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem("Start Service", _start_service))
    items.append(pystray.MenuItem("Stop Service", _stop_service))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem("Open Data Folder", _open_data_folder))
    items.append(pystray.MenuItem("View Audit Log", _view_audit_log))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem("Exit", _exit_app))
    return pystray.Menu(*items)


def _run_elevated(cmd: str) -> None:
    import win32api, win32con
    win32api.ShellExecute(0, "runas", "cmd.exe", f"/c {cmd}", None, win32con.SW_HIDE)


def _start_service(icon, item) -> None:
    try:
        _run_elevated("sc start EMRTrackerService")
    except Exception:
        subprocess.Popen(["sc", "start", "EMRTrackerService"], shell=True)


def _stop_service(icon, item) -> None:
    try:
        _run_elevated("sc stop EMRTrackerService")
    except Exception:
        subprocess.Popen(["sc", "stop", "EMRTrackerService"], shell=True)


def _open_data_folder(icon, item) -> None:
    os.makedirs(DATA_FOLDER, exist_ok=True)
    subprocess.Popen(["explorer", DATA_FOLDER])


def _view_audit_log(icon, item) -> None:
    subprocess.Popen(["notepad.exe", AUDIT_LOG])


def _exit_app(icon, item) -> None:
    icon.stop()


def _poll_loop(icon: pystray.Icon) -> None:
    while True:
        try:
            status = read_status(DB_PATH)
            color = status_to_color(status)
            icon.icon = make_icon(color)
            icon.menu = _build_menu(status)
            icon.update_menu()
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


def main() -> None:
    status = read_status(DB_PATH)
    color = status_to_color(status)
    icon = pystray.Icon(
        name="EMRTracker",
        icon=make_icon(color),
        title="EMR Tracker",
        menu=_build_menu(status),
    )
    t = threading.Thread(target=_poll_loop, args=(icon,), daemon=True)
    t.start()
    icon.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/agent/test_tray.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add agent/tray/tray_app.py tests/agent/test_tray.py
git commit -m "feat: full tray app with menu, polling, start/stop/open-log actions"
```

---

### Task 5: Startup shortcut in setup.bat

**Files:**
- Modify: `setup.bat`

- [ ] **Step 1: Add startup shortcut creation to setup.bat**

In `setup.bat`, after the service install and start block (after Step 7/7), add before the final `echo Setup complete!`:

```bat
:: -------------------------------------------------------
echo  Creating tray app startup shortcut...
:: -------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $startup = [Environment]::GetFolderPath('Startup'); $s = $ws.CreateShortcut($startup + '\EMRTray.lnk'); $s.TargetPath = 'pythonw.exe'; $s.Arguments = 'C:\EMRTracker\agent\tray\tray_app.py'; $s.WorkingDirectory = 'C:\EMRTracker'; $s.Description = 'EMR Tracker Status Tray'; $s.Save(); Write-Host '        Startup shortcut created.'"
```

- [ ] **Step 2: Also launch the tray app immediately after install**

Add after the shortcut creation:
```bat
echo  Launching tray app...
start "" pythonw.exe "%INSTALL_DIR%\agent\tray\tray_app.py"
echo         Tray icon should appear in taskbar notification area.
```

- [ ] **Step 3: Commit**

```bash
git add setup.bat
git commit -m "feat: setup.bat creates startup shortcut and launches tray app on install"
```

---

### Task 6: Smoke test on the VM

**No code changes — verification only.**

- [ ] **Step 1: Run the tray app manually**

```bash
python agent\tray\tray_app.py
```

Expected: A colored circle icon appears in the Windows taskbar notification area (bottom-right). No error output.

- [ ] **Step 2: Right-click the icon**

Expected menu:
```
Service: RUNNING ✓  (or STOPPED ✗)
Now: Idle  (or EMR › module if service active)
Today: N sessions saved
─────────────────
Start Service
Stop Service
─────────────────
Open Data Folder
View Audit Log
─────────────────
Exit
```

- [ ] **Step 3: Test Open Data Folder**

Click "Open Data Folder" — Windows Explorer should open `C:\ProgramData\EMRTracker\data\workflows\`.

- [ ] **Step 4: Test View Audit Log**

Click "View Audit Log" — Notepad should open `audit.log`.

- [ ] **Step 5: Test Exit**

Click "Exit" — icon disappears from tray. Running `sc query EMRTrackerService` should still show the service running.

- [ ] **Step 6: Final commit and push**

```bash
git push
```

---

## Summary

| Task | What it builds |
|------|---------------|
| 1 | Package + pystray dependency |
| 2 | TrayStatus + status_reader (service state + DB query) |
| 3 | Icon generator (green/yellow/red circle) |
| 4 | Full tray app (menu, polling, action handlers) |
| 5 | setup.bat startup shortcut + auto-launch |
| 6 | Smoke test on VM |
