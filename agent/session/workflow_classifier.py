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
