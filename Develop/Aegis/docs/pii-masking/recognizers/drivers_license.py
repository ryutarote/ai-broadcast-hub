"""日本の運転免許証番号 (12 digits) recognizer.

12桁の数字。先頭2桁は都道府県の公安委員会コード。
末尾はチェックディジット（mod 10 ベース）を持つ前提だが、
公開アルゴリズムは厳密公開されていないため、ここでは形式のみで判定。
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


# 公安委員会コード (00〜49 + 50〜53(沖縄等)、便宜上 00〜99 で広めに許可)
# false positiveが目立つ場合は範囲を狭めること
_PUBLIC_SAFETY_PREFIXES = set(f"{i:02d}" for i in range(0, 100))


class JapaneseDriversLicenseRecognizer(PatternRecognizer):
    """Detects Japanese driver's license numbers (12 digits)."""

    PATTERNS = [
        Pattern(
            "JP Drivers License - 12 digits",
            r"\b\d{12}\b",
            0.2,  # 弱め、コンテキスト依存
        ),
    ]

    CONTEXT = [
        "運転免許証",
        "免許証",
        "免許番号",
        "Drivers License",
        "公安委員会",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_DRIVERS_LICENSE",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        digits = pattern_text.strip()
        if not digits.isdigit() or len(digits) != 12:
            return False
        return digits[:2] in _PUBLIC_SAFETY_PREFIXES
