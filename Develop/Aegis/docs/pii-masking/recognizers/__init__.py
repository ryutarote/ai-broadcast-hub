"""Aegis PII Recognizers for Japanese.

Exports a single helper `register_japanese_recognizers(registry)` that
attaches all Japanese-specific recognizers to a Presidio RecognizerRegistry.
"""

from .my_number import JapaneseMyNumberRecognizer
from .corporate_number import JapaneseCorporateNumberRecognizer
from .postal_code import JapanesePostalCodeRecognizer
from .phone_number import JapanesePhoneNumberRecognizer
from .drivers_license import JapaneseDriversLicenseRecognizer
from .health_insurance import JapaneseHealthInsuranceRecognizer
from .bank_account import JapaneseBankAccountRecognizer
from .address import JapaneseAddressRecognizer
from .wareki_date import JapaneseWarekiDateRecognizer


def register_japanese_recognizers(registry) -> None:
    """Register all Aegis Japanese recognizers on a Presidio registry."""
    for cls in (
        JapaneseMyNumberRecognizer,
        JapaneseCorporateNumberRecognizer,
        JapanesePostalCodeRecognizer,
        JapanesePhoneNumberRecognizer,
        JapaneseDriversLicenseRecognizer,
        JapaneseHealthInsuranceRecognizer,
        JapaneseBankAccountRecognizer,
        JapaneseAddressRecognizer,
        JapaneseWarekiDateRecognizer,
    ):
        registry.add_recognizer(cls())


__all__ = [
    "register_japanese_recognizers",
    "JapaneseMyNumberRecognizer",
    "JapaneseCorporateNumberRecognizer",
    "JapanesePostalCodeRecognizer",
    "JapanesePhoneNumberRecognizer",
    "JapaneseDriversLicenseRecognizer",
    "JapaneseHealthInsuranceRecognizer",
    "JapaneseBankAccountRecognizer",
    "JapaneseAddressRecognizer",
    "JapaneseWarekiDateRecognizer",
]
