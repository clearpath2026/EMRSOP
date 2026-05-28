from __future__ import annotations
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from agent.redaction.recognizers import OHIPRecognizer, CanadianPostalCodeRecognizer

_OPERATOR_CONFIG = {
    "PERSON": OperatorConfig("replace", {"new_value": "[REDACTED_NAME]"}),
    "OHIP_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_ID]"}),
    "CA_POSTAL_CODE": OperatorConfig("replace", {"new_value": "[REDACTED_ADDR]"}),
    "DATE_TIME": OperatorConfig("replace", {"new_value": "[REDACTED_DOB]"}),
    "LOCATION": OperatorConfig("replace", {"new_value": "[REDACTED_ADDR]"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_PHONE]"}),
    "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED_TEXT]"}),
}


class RedactionEngine:
    def __init__(self):
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()
        registry.add_recognizer(OHIPRecognizer())
        registry.add_recognizer(CanadianPostalCodeRecognizer())
        self._analyzer = AnalyzerEngine(registry=registry)
        self._anonymizer = AnonymizerEngine()

    def redact(self, text: str, language: str = "en") -> str:
        if not text or not text.strip():
            return text
        results = self._analyzer.analyze(text=text, language=language)
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=_OPERATOR_CONFIG,
        )
        return anonymized.text
