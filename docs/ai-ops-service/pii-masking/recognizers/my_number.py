"""マイナンバー (Japanese Individual Number, 12 digits) recognizer.

仕様：
- 12桁の数字。表記揺れ：連続 / スペース区切り / ハイフン区切り (4-4-4)。
- 末1桁はチェックディジット（mod 11）。
- 「マイナンバー」「個人番号」等のコンテキストが近接するとスコア上昇。

参考：
  個人番号におけるチェックデジット算出方法
  https://www.soumu.go.jp/main_content/000346273.pdf
"""

from __future__ import annotations

import re

from presidio_analyzer import Pattern, PatternRecognizer


# 公式チェックディジット重み
_MYNUMBER_WEIGHTS: tuple[int, ...] = (6, 5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def is_valid_mynumber(digits: str) -> bool:
    """Validate 12-digit MyNumber with the official check-digit algorithm."""
    if len(digits) != 12 or not digits.isdigit():
        return False
    body = digits[:11]
    check = int(digits[11])
    total = sum(int(d) * w for d, w in zip(body, _MYNUMBER_WEIGHTS))
    remainder = total % 11
    expected = 0 if remainder <= 1 else 11 - remainder
    return expected == check


class JapaneseMyNumberRecognizer(PatternRecognizer):
    """Detects Japanese MyNumber (個人番号) with check-digit validation."""

    PATTERNS: list[Pattern] = [
        # 連続 12 桁
        Pattern("MyNumber - 12 digits", r"\b\d{12}\b", 0.3),
        # ハイフン or 半角スペース区切り (4-4-4)
        Pattern(
            "MyNumber - 4-4-4 formatted",
            r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b",
            0.5,
        ),
    ]

    CONTEXT: list[str] = [
        "マイナンバー",
        "個人番号",
        "個人ナンバー",
        "個人識別番号",
        "通知カード",
        "マイナンバーカード",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_MY_NUMBER",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        """Override Presidio validation hook."""
        digits = re.sub(r"\D", "", pattern_text)
        return is_valid_mynumber(digits)
