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
