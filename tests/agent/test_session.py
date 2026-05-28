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
