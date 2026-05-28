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


import pytest

@pytest.fixture(scope="session")
def shared_redaction_engine():
    from agent.redaction.engine import RedactionEngine
    return RedactionEngine()
