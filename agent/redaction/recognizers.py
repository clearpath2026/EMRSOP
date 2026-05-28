from presidio_analyzer import PatternRecognizer, Pattern
from agent.redaction.patterns import OHIP_PATTERN, CA_POSTAL_CODE_PATTERN


class OHIPRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="OHIP_NUMBER",
            patterns=[Pattern("OHIP_NUMBER_PATTERN", OHIP_PATTERN, 0.9)],
            context=["ohip", "health card", "health number", "insurance number"],
        )


class CanadianPostalCodeRecognizer(PatternRecognizer):
    def __init__(self):
        super().__init__(
            supported_entity="CA_POSTAL_CODE",
            patterns=[Pattern("CA_POSTAL_PATTERN", CA_POSTAL_CODE_PATTERN, 0.85)],
            context=["postal", "zip", "address", "code", "city"],
        )
