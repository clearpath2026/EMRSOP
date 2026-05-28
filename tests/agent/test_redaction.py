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

@pytest.fixture
def engine(shared_redaction_engine):
    return shared_redaction_engine

def test_engine_redacts_person_name(engine):
    result = engine.redact("Patient John Smith called today about his appointment.")
    assert "John Smith" not in result
    assert "[REDACTED_NAME]" in result

def test_engine_redacts_ohip_number(engine):
    result = engine.redact("OHIP: 1234 567 890")
    assert "1234 567 890" not in result
    assert "[REDACTED_ID]" in result

def test_engine_redacts_phone_number(engine):
    result = engine.redact("Call back at 416-555-0123 for the appointment.")
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
