"""日本の郵便番号 (Japanese Postal Code) recognizer.

形式：
- 〒999-9999 / 999-9999 / 9999999 / 〒9999999
- 全角ハイフン・全角数字も許容するため事前正規化を呼び出し側で行う
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class JapanesePostalCodeRecognizer(PatternRecognizer):
    """Detects Japanese postal codes (3+4 digits)."""

    PATTERNS = [
        # 〒 + 3-4 (Strong)
        Pattern(
            "Postal with mark and hyphen",
            r"〒\s?\d{3}-\d{4}\b",
            0.85,
        ),
        # 〒 + 7 digits
        Pattern(
            "Postal with mark, 7 digits",
            r"〒\s?\d{7}\b",
            0.75,
        ),
        # 3-4 without mark (Medium - needs context)
        Pattern(
            "Postal 3-4 without mark",
            r"\b\d{3}-\d{4}\b",
            0.4,
        ),
    ]

    CONTEXT = [
        "郵便番号",
        "〒",
        "住所",
        "ご住所",
        "所在地",
        "ZIP",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_POSTAL_CODE",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )
