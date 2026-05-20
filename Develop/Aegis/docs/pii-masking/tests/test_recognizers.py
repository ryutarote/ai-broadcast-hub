"""Smoke tests for non-MyNumber recognizers."""

from __future__ import annotations

import pytest

from aegis_pii_jp.recognizers.corporate_number import (
    JapaneseCorporateNumberRecognizer,
    is_valid_corporate_number,
)
from aegis_pii_jp.recognizers.postal_code import JapanesePostalCodeRecognizer
from aegis_pii_jp.recognizers.phone_number import JapanesePhoneNumberRecognizer
from aegis_pii_jp.recognizers.drivers_license import JapaneseDriversLicenseRecognizer
from aegis_pii_jp.recognizers.address import JapaneseAddressRecognizer
from aegis_pii_jp.recognizers.wareki_date import JapaneseWarekiDateRecognizer
from aegis_pii_jp.recognizers.normalize import normalize_for_pii


# 検証用法人番号サンプル（実在のものではないテスト用ダミー）
VALID_CORPORATE_NUMBERS = [
    # チェックディジット仕様に合うようにオフラインで生成した値を入れること
]


@pytest.mark.parametrize(
    "text",
    [
        "〒100-0001 東京都千代田区千代田1-1",
        "郵便番号 〒1000001",
        "ご住所：〒150-0002 渋谷区渋谷",
    ],
)
def test_postal_code_detected(text: str) -> None:
    rec = JapanesePostalCodeRecognizer()
    results = rec.analyze(text=text, entities=["JP_POSTAL_CODE"], nlp_artifacts=None)
    assert results, f"postal not detected in: {text}"


@pytest.mark.parametrize(
    "text",
    [
        "電話: 03-1234-5678",
        "携帯 090-1234-5678",
        "TEL (03)1234-5678",
        "フリーダイヤル 0120-123-456",
        "+81-3-1234-5678",
    ],
)
def test_phone_detected(text: str) -> None:
    rec = JapanesePhoneNumberRecognizer()
    results = rec.analyze(text=text, entities=["JP_PHONE_NUMBER"], nlp_artifacts=None)
    assert results, f"phone not detected in: {text}"


def test_phone_no_false_positive_on_long_number() -> None:
    rec = JapanesePhoneNumberRecognizer()
    text = "注文番号 12345678901234567"
    results = rec.analyze(text=text, entities=["JP_PHONE_NUMBER"], nlp_artifacts=None)
    # 17桁数字は電話として検出されないことを期待
    for r in results:
        assert r.score < 0.5


def test_drivers_license_requires_context() -> None:
    rec = JapaneseDriversLicenseRecognizer()
    digits = "234567890123"
    text_without_ctx = f"商品コード {digits}"
    text_with_ctx = f"運転免許証 {digits}"
    r1 = rec.analyze(text=text_without_ctx, entities=["JP_DRIVERS_LICENSE"], nlp_artifacts=None)
    r2 = rec.analyze(text=text_with_ctx, entities=["JP_DRIVERS_LICENSE"], nlp_artifacts=None)
    # コンテキストありの方が信頼度が上がるはず
    if r1 and r2:
        assert max(r.score for r in r2) >= max(r.score for r in r1)


def test_address_detected() -> None:
    rec = JapaneseAddressRecognizer()
    text = "お届け先：東京都千代田区千代田1-1-1 千代田ビル3階"
    results = rec.analyze(text=text, entities=["JP_ADDRESS"], nlp_artifacts=None)
    assert results
    r = results[0]
    assert "東京都" in text[r.start:r.end]


def test_wareki_date_detected() -> None:
    rec = JapaneseWarekiDateRecognizer()
    for text in [
        "令和7年5月14日",
        "昭和60年生まれ",
        "平成元年4月1日施行",
        "R5.3.15",
    ]:
        results = rec.analyze(text=text, entities=["JP_WAREKI_DATE"], nlp_artifacts=None)
        assert results, f"wareki not detected in: {text}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("〒100-0001", "〒100-0001"),
        ("12345-6789", "12345-6789"),       # 既に半角
        ("12345−6789", "12345-6789"),       # 全角ハイフン
        ("123 4567", "123 4567"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize_for_pii(raw) == expected
