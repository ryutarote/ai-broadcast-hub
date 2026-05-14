"""日本の銀行口座番号 recognizer.

代表的な日本の口座表記：
  銀行コード (4桁) + 支店コード (3桁) + 口座種別 (普通/当座) + 口座番号 (7桁)
ゆうちょ：
  記号 (5桁) - 番号 (8桁) または 13桁通帳記号

文脈依存度が高く、ベーススコアは低めに設定。
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class JapaneseBankAccountRecognizer(PatternRecognizer):
    """Detects Japanese bank account references with strong context."""

    PATTERNS = [
        # 口座番号 (7桁)
        Pattern(
            "JP Bank Account - 7 digits",
            r"\b\d{7}\b",
            0.15,
        ),
        # ゆうちょ 記号-番号
        Pattern(
            "Yucho Symbol-Number",
            r"\b\d{5}[\s\-]?\d{8}\b",
            0.5,
        ),
        # 銀行コード-支店-口座 形式
        Pattern(
            "Bank-Branch-Account",
            r"\b\d{4}[\s\-]\d{3}[\s\-]\d{7}\b",
            0.7,
        ),
    ]

    CONTEXT = [
        "銀行口座",
        "振込先",
        "口座番号",
        "普通預金",
        "当座預金",
        "支店",
        "銀行コード",
        "ゆうちょ",
        "振込",
        "送金",
    ]

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_BANK_ACCOUNT",
    ) -> None:
        super().__init__(
            supported_entity=supported_entity,
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=supported_language,
        )
