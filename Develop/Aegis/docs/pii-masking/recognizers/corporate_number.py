"""法人番号 (Japanese Corporate Number, 13 digits) recognizer.

- 1桁目はチェックディジット、2〜13桁目（=12桁）が本体
- チェックディジット = 9 - ( Σ(i=1..12) Pi * Qi ) mod 9
  Qi は奇数桁(末尾から数えて)=1、偶数桁=2

参考：
  国税庁「法人番号の指定の概要」
"""

from __future__ import annotations

import re

from presidio_analyzer import Pattern, PatternRecognizer


def is_valid_corporate_number(digits: str) -> bool:
    if len(digits) != 13 or not digits.isdigit():
        return False
    check = int(digits[0])
    body = digits[1:]
    # 末尾から数えて奇数桁 → 1、偶数桁 → 2
    total = 0
    for i, c in enumerate(reversed(body)):
        weight = 1 if (i + 1) % 2 == 1 else 2
        total += int(c) * weight
    expected = 9 - (total % 9)
    return expected == check


class JapaneseCorporateNumberRecognizer(PatternRecognizer):
    """Detects Japanese 法人番号 (13 digits with check digit)."""

    PATTERNS = [
        Pattern("Corporate Number - 13 digits", r"\b\d{13}\b", 0.4),
    ]

    CONTEXT = [
        "法人番号",
        "国税庁法人番号",
        "Corporate Number",
        "適格請求書発行事業者",
        "T番号",
        "T+13",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_CORPORATE_NUMBER",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        digits = re.sub(r"\D", "", pattern_text)
        return is_valid_corporate_number(digits)
