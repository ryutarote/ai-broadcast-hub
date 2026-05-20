"""日本国内電話番号 recognizer.

カバー範囲：
- 固定電話：03-XXXX-XXXX / (03)XXXX-XXXX
- 携帯電話：070/080/090-XXXX-XXXX
- フリーダイヤル：0120-XXX-XXX
- IP電話：050-XXXX-XXXX
- 国際表記：+81-3-XXXX-XXXX

過剰検知を避けるため、市外局番先頭ゼロを必須にしている。
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class JapanesePhoneNumberRecognizer(PatternRecognizer):
    """Detects Japanese phone numbers."""

    # 局番桁数の異なる代表的なパターン
    PATTERNS = [
        # 国際 +81 表記
        Pattern(
            "JP Phone international",
            r"\+81[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{3,4}",
            0.75,
        ),
        # 携帯 070/080/090
        Pattern(
            "JP Mobile",
            r"\b0[7-9]0[\s\-]?\d{4}[\s\-]?\d{4}\b",
            0.85,
        ),
        # IP電話 050
        Pattern(
            "JP IP Phone",
            r"\b050[\s\-]?\d{4}[\s\-]?\d{4}\b",
            0.85,
        ),
        # フリーダイヤル
        Pattern(
            "JP Freedial",
            r"\b0120[\s\-]?\d{3}[\s\-]?\d{3}\b",
            0.9,
        ),
        # 固定電話 (3 or 2 area code) - parenthesized
        Pattern(
            "JP Landline parens",
            r"\(0\d{1,4}\)[\s\-]?\d{1,4}[\s\-]?\d{3,4}",
            0.75,
        ),
        # 固定電話 (general)
        Pattern(
            "JP Landline hyphen",
            r"\b0\d{1,4}[\s\-]\d{1,4}[\s\-]\d{3,4}\b",
            0.5,
        ),
    ]

    CONTEXT = [
        "電話番号",
        "電話",
        "Tel",
        "TEL",
        "携帯",
        "ご連絡先",
        "連絡先",
        "Phone",
        "Mobile",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_PHONE_NUMBER",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )
