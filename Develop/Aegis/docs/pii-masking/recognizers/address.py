"""日本式住所 recognizer.

戦略：
  「都道府県名」を起点に、後続の市区町村+番地+建物名 までを 1 つの
  住所エンティティとして抽出する。完全な住所辞書ではなく、
  正規表現＋ヒューリスティックで「住所らしさ」を判定する。

精度・再現率は本番運用前にゴールデンセットで調整する想定。
"""

from __future__ import annotations

import re

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts


_PREFECTURES = (
    "北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|"
    "茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|"
    "新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|"
    "静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|"
    "奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|"
    "徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|"
    "熊本県|大分県|宮崎県|鹿児島県|沖縄県"
)

# 都道府県 + 市区町村 + 後続 (丁目/番地/建物)
_ADDRESS_PATTERN = re.compile(
    rf"({_PREFECTURES})"
    r"([^\s、。]{0,8}?(?:市|区|町|村|郡))"
    r"[^\s、。]{1,40}?"
    r"(?:\d+(?:[\-丁目番地号]\d*)*)?"
    r"(?:[^\s、。]{0,20}?(?:ビル|マンション|ハイツ|アパート|タワー|号室)?)?"
)


class JapaneseAddressRecognizer(EntityRecognizer):
    """Detects Japanese-style addresses anchored by prefecture names."""

    def __init__(
        self,
        supported_language: str = "ja",
        supported_entity: str = "JP_ADDRESS",
    ) -> None:
        super().__init__(
            supported_entities=[supported_entity],
            supported_language=supported_language,
            name="JapaneseAddressRecognizer",
        )

    def load(self) -> None:  # pragma: no cover - presidio interface
        return None

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: NlpArtifacts | None = None,
    ) -> list[RecognizerResult]:
        results: list[RecognizerResult] = []
        for match in _ADDRESS_PATTERN.finditer(text):
            start, end = match.span()
            # 住所文字列が極端に長い・短い場合は信頼度を下げる
            length = end - start
            if length < 6:
                continue
            score = 0.6 if length < 12 else 0.85
            results.append(
                RecognizerResult(
                    entity_type=self.supported_entities[0],
                    start=start,
                    end=end,
                    score=score,
                )
            )
        return results
