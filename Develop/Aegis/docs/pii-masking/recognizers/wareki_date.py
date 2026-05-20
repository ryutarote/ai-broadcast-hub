"""和暦日付 recognizer.

対応元号：明治、大正、昭和、平成、令和（M/T/S/H/R 略記含む）
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class JapaneseWarekiDateRecognizer(PatternRecognizer):
    """Detects Japanese era dates."""

    PATTERNS = [
        # 漢字元号 + 年[月日]
        Pattern(
            "Wareki - Kanji era",
            r"(?:明治|大正|昭和|平成|令和)\s?(?:元|\d{1,2})\s?年"
            r"(?:\s?(?:1[0-2]|0?[1-9])\s?月)?"
            r"(?:\s?(?:[12]\d|3[01]|0?[1-9])\s?日)?",
            0.85,
        ),
        # ローマ字略記 + 年
        Pattern(
            "Wareki - Romaji era",
            r"\b[MTSHR]\.?\s?\d{1,2}\.\d{1,2}\.\d{1,2}\b",
            0.6,
        ),
    ]

    CONTEXT = [
        "和暦",
        "生年月日",
        "誕生日",
        "発行日",
        "施行日",
        "元号",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_WAREKI_DATE",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )
