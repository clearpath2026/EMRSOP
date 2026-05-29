# EMRSOP System Tray Status UI — Design Spec

**Date:** 2026-05-29
**Status:** Approved

---

## Overview

A lightweight Windows system tray application that gives agents and supervisors a passive view of the EMRTrackerService status without interrupting workflow. The tray icon lives in the taskbar notification area, changes color based on service state, and provides a right-click menu with live status and quick controls.

---

## Architecture

Two files under `agent/tray/`:

### `agent/tray/status_reader.py`
Single responsibility: read current service and session state. Returns a `TrayStatus` dataclass.

**Service state** — runs `sc query EMRTrackerService` via subprocess, parses `STATE` line.

**Session state** — queries SQLite DB (`C:\ProgramData\EMRTracker\data\emr_tracker.db`):
- Most recent open session: EMR name, module, start time
- Count of sessions closed today (by `closed_at` date)

**Poll interval:** 3 seconds. Status reader is called on a background thread inside pystray's update loop.

### `agent/tray/tray_app.py`
Standalone script. Entry point: `python agent/tray/tray_app.py`

- Creates a `pystray.Icon` instance with a generated PIL image as the icon
- Icon color reflects service state:
  - **Green (#22c55e)** — service running, session active
  - **Yellow (#eab308)** — service running, no active session (idle)
  - **Red (#ef4444)** — service stopped or unreachable
- Rebuilds the right-click menu every 3 seconds via `pystray`'s `update_menu()`
- Runs independently of the Windows service — does not affect it on exit

---

## Tray Menu Layout

```
EMRTrackerService: RUNNING          ← non-clickable label
Current: Accuro › patient_search    ← non-clickable, or "Idle" if no session
Session: 8 min active               ← non-clickable, or blank if idle
Today: 3 sessions saved             ← non-clickable
─────────────────────────
Start Service                       ← runs: sc start EMRTrackerService (admin)
Stop Service                        ← runs: sc stop EMRTrackerService (admin)
─────────────────────────
Open Data Folder                    ← opens C:\ProgramData\EMRTracker\data\workflows\ in Explorer
View Audit Log                      ← opens audit.log in Notepad
─────────────────────────
Exit                                ← stops tray app only, service keeps running
```

Start/Stop require elevation. The script runs `subprocess` with `shell=True` using `runas` verb via `ShellExecuteEx` so UAC prompt appears correctly.

---

## Icon Generation

Icon is a 64×64 PIL image drawn at runtime — no image file needed:
- Filled circle in the status color
- White "E" letter centered (for EMR)
- Regenerated on every status change

---

## Dependencies

- `pystray>=0.19` — new pip install
- `Pillow>=10.0` — already installed
- `pywin32>=306` — already installed (for ShellExecuteEx)
- `psutil`, `sqlite3` — already available

`pystray` added to `agent/requirements.txt` and `setup.bat`.

---

## Startup Registration

`setup.bat` creates a Windows Startup shortcut so the tray app launches automatically on user login:

```bat
:: Creates shortcut in %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\EMRTray.lnk'); $s.TargetPath = 'pythonw.exe'; $s.Arguments = 'C:\EMRTracker\agent\tray\tray_app.py'; $s.Save()"
```

Uses `pythonw.exe` (no console window).

---

## Error Handling

- If DB is unavailable: show "DB unavailable" in menu, keep polling
- If `sc query` fails: icon turns red, menu shows "Service unreachable"
- If status_reader throws: log to `%TEMP%\emr_tray.log`, continue polling

---

## Files Changed

| File | Change |
|------|--------|
| `agent/tray/__init__.py` | New (empty) |
| `agent/tray/status_reader.py` | New |
| `agent/tray/tray_app.py` | New |
| `agent/requirements.txt` | Add `pystray>=0.19` |
| `setup.bat` | Add pystray install + startup shortcut creation |

No changes to the service, aggregator, or any existing agent code.
