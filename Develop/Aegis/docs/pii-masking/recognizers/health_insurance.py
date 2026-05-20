"""健康保険証記号番号 recognizer (context-heavy)."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class JapaneseHealthInsuranceRecognizer(PatternRecognizer):
    """Detects health insurance numbers when accompanied by clear context."""

    # 数字+任意の記号、保険者番号(8桁)、被保険者番号(可変)。
    # 文脈依存なのでベーススコアは低めに。
    PATTERNS = [
        Pattern(
            "JP Health Insurance - 8 digits (insurer)",
            r"\b\d{8}\b",
            0.2,
        ),
        # 記号+番号 (例：記号 123 番号 4567890)
        Pattern(
            "JP Health Insurance - 記号番号",
            r"記号\s?[A-Za-z0-9\-]+\s+番号\s?[A-Za-z0-9\-]+",
            0.7,
        ),
    ]

    CONTEXT = [
        "健康保険証",
        "健保",
        "保険者番号",
        "被保険者番号",
        "記号",
        "保険証",
        "後期高齢者",
        "国民健康保険",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_HEALTH_INSURANCE",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )
