"""Unit tests for マイナンバー recognizer."""

from __future__ import annotations

import pytest

from aegis_pii_jp.recognizers.my_number import (
    JapaneseMyNumberRecognizer,
    is_valid_mynumber,
)


# 公開チェックデジット検証用のサンプル値。実在のマイナンバーではない。
# 本体11桁 → チェックデジット を計算して連結したテスト値
VALID_NUMBERS = [
    "123456789018",
    "012345678906",
    "987654321094",
]

INVALID_NUMBERS = [
    "123456789012",  # チェックデジット不一致
    "999999999999",  # 全部9
    "00000000000",   # 11桁
    "0000000000000",  # 13桁
    "12345678901a",  # 非数字
]


@pytest.mark.parametrize("value", VALID_NUMBERS)
def test_validator_accepts_valid(value: str) -> None:
    assert is_valid_mynumber(value)


@pytest.mark.parametrize("value", INVALID_NUMBERS)
def test_validator_rejects_invalid(value: str) -> None:
    assert not is_valid_mynumber(value)


def test_recognizer_basic_match() -> None:
    rec = JapaneseMyNumberRecognizer()
    # 文中に有効なマイナンバー
    text = f"マイナンバーは {VALID_NUMBERS[0]} です"
    results = rec.analyze(text=text, entities=["JP_MY_NUMBER"], nlp_artifacts=None)
    assert results, "should detect the valid mynumber"
    assert results[0].entity_type == "JP_MY_NUMBER"


def test_recognizer_validates_check_digit() -> None:
    """無効なチェックデジットの12桁は通さない."""
    rec = JapaneseMyNumberRecognizer()
    text = "個人番号 999999999999"
    results = rec.analyze(text=text, entities=["JP_MY_NUMBER"], nlp_artifacts=None)
    assert results == [] or all(r.score < 0.6 for r in results)


def test_recognizer_with_hyphens() -> None:
    rec = JapaneseMyNumberRecognizer()
    digits = VALID_NUMBERS[0]
    text = f"マイナンバー：{digits[:4]}-{digits[4:8]}-{digits[8:]}"
    results = rec.analyze(text=text, entities=["JP_MY_NUMBER"], nlp_artifacts=None)
    assert results
