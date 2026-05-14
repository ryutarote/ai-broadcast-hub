# PIIマスキング 日本語対応（`aegis-pii-jp`）

**ステータス**: Draft v0.1
**目的**: LiteLLM Proxy にフックして、日本語特有のPIIを検出・マスキングする

---

## 構成

| パス | 内容 |
|---|---|
| [design.md](./design.md) | 設計書（対象エンティティ、アーキ、性能、安全装置） |
| [policies.md](./policies.md) | マスキングポリシー（アクション、業界別プリセット） |
| [integration.md](./integration.md) | LiteLLM 統合ガイド（フック実装、config、運用） |
| [operations.md](./operations.md) | 運用ガイド（監視、アラート、障害対応、監査） |
| [recognizers/](./recognizers/) | Python 実装（カスタム認識子 9 種 + Scanner） |
| [tests/](./tests/) | pytest スイート（認識子個別 + Scanner E2E） |
| [fixtures/](./fixtures/) | テスト用サンプルデータと期待マスク結果 |

---

## 実装ファイル一覧

```
recognizers/
├── __init__.py              # register_japanese_recognizers()
├── my_number.py             # JP_MY_NUMBER（チェックデジット検証）
├── corporate_number.py      # JP_CORPORATE_NUMBER（13桁、チェックデジット）
├── postal_code.py           # JP_POSTAL_CODE
├── phone_number.py          # JP_PHONE_NUMBER（固定/携帯/IP/0120/国際）
├── drivers_license.py       # JP_DRIVERS_LICENSE
├── health_insurance.py      # JP_HEALTH_INSURANCE
├── bank_account.py          # JP_BANK_ACCOUNT
├── address.py               # JP_ADDRESS（都道府県起点）
├── wareki_date.py           # JP_WAREKI_DATE
├── normalize.py             # NFKC正規化＋ハイフン統一
├── scanner.py               # PIIScanner / TenantPolicy / Action
└── pyproject.toml           # パッケージ定義
```

---

## ローカル開発

```bash
cd recognizers
pip install -e .[dev]
python -m spacy download ja_core_news_md
python -m spacy download en_core_web_sm
cd ..
pytest tests
```

---

## 検出対象エンティティ

| エンティティ | 機密度 | デフォルトアクション |
|---|---|---|
| `JP_MY_NUMBER` | S | block |
| `JP_CORPORATE_NUMBER` | B | mask |
| `JP_DRIVERS_LICENSE` | S | block |
| `JP_HEALTH_INSURANCE` | S | block |
| `JP_BANK_ACCOUNT` | A | replace |
| `JP_ADDRESS` | A | replace |
| `JP_PHONE_NUMBER` | B | mask (keep 4) |
| `JP_POSTAL_CODE` | C | tag_only |
| `JP_PERSON_NAME`（spaCy NER） | A | replace |
| `JP_WAREKI_DATE` | A | replace |

加えて Presidio 標準の `EMAIL_ADDRESS` / `CREDIT_CARD` / `IP_ADDRESS` / `URL` などを併用。

---

## 性能目標

- プロキシ追加レイテンシ p99 < 50ms（1KB プロンプト）
- 1インスタンス 50 req/s
- 32KB 超は分割処理

---

## ライセンス上の注意

- 認識子コード：社内（Proprietary）
- 依存：Presidio (MIT)、spaCy (MIT)、`ja_core_news_md` (CC BY-SA 4.0)
- モデルは**改変しない**前提で再配布義務を回避

詳細は [legal/oss-license-compliance.md](../legal/oss-license-compliance.md) を参照。

---

## 関連

- 設計上の位置づけ：[basic-design.md](../basic-design.md) §6.3
- データフロー：[data-flow.md](../data-flow.md) DFL-02
- 個情法・委託契約上の位置づけ：[legal/dpa-template.md](../legal/dpa-template.md) §5
