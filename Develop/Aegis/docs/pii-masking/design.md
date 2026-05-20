# PIIマスキング 日本語対応 設計書

**ステータス**: Draft v0.1
**作成日**: 2026-05-14
**前提**: Microsoft Presidio 2.x、Python 3.12、spaCy `ja_core_news_md`

---

## 1. 目的とスコープ

### 1.1 目的

Aegisが顧客から受け取るLLMプロンプト・LLMからのレスポンスに含まれる個人情報（PII）を検出し、設定ポリシーに従いマスク・ブロック・タグ付けする。

### 1.2 スコープ

- 日本固有のPIIエンティティ8種類の検出
- 既存PresidioのグローバルエンティティとPI連携
- リクエスト/レスポンス両方向への適用
- テナント別ポリシー設定
- パフォーマンス（プロキシレイテンシ +50ms 以内、p99）

### 1.3 スコープ外

- 完全な日本語NER（ja_core_news_lg は重いため md ベース）
- 画像・PDF内テキストのOCR後マスキング（v2）
- フェデレーテッドな学習・モデル再学習

---

## 2. 検出対象エンティティ

### 2.1 日本固有エンティティ（新規実装）

| Entity Type | 説明 | 例 | 検証方法 |
|---|---|---|---|
| `JP_MY_NUMBER` | マイナンバー（個人番号、12桁） | `1234 5678 9012` | チェックデジット検証 |
| `JP_CORPORATE_NUMBER` | 法人番号（13桁） | `1234567890123` | チェックデジット検証 |
| `JP_POSTAL_CODE` | 郵便番号 | `100-0001`, `1000001` | 形式マッチ + 既知範囲 |
| `JP_PHONE_NUMBER` | 日本国内電話番号 | `03-1234-5678`, `090-1234-5678` | 形式マッチ + 市外局番リスト |
| `JP_DRIVERS_LICENSE` | 運転免許証番号（12桁） | `123456789012` | 形式マッチ |
| `JP_HEALTH_INSURANCE` | 健康保険証記号番号 | `保険者番号 12345678` | コンテキスト + 形式 |
| `JP_BANK_ACCOUNT` | 銀行口座番号 | `銀行コード4桁 + 支店3桁 + 口座7桁` | コンテキスト + 形式 |
| `JP_ADDRESS` | 日本式住所 | `東京都千代田区...` | 都道府県 + 市区町村辞書 |
| `JP_PERSON_NAME` | 日本人氏名 | `山田 太郎` | spaCy NER（ja） |
| `JP_WAREKI_DATE` | 和暦日付 | `令和7年5月14日`、`昭和60年` | 形式マッチ |

### 2.2 既存Presidioエンティティを継続利用

| Entity Type | コメント |
|---|---|
| `EMAIL_ADDRESS` | 標準のまま |
| `CREDIT_CARD` | 標準のまま（Luhn検証付き） |
| `IP_ADDRESS` | 標準のまま |
| `URL` | 標準のまま |
| `IBAN_CODE` | 国際口座（海外取引対応時のみ有効化） |
| `DATE_TIME` | グレゴリオ暦 |

---

## 3. アーキテクチャ

### 3.1 構成

```
┌─────────────────────────────────────────────────────────┐
│ LiteLLM Proxy (FastAPI)                                  │
│                                                           │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Pre-Call Hook                                       │ │
│  │  └→ PIIScanner.scan_request()                       │ │
│  │       ├→ AnalyzerEngine (Presidio + Custom JP)     │ │
│  │       └→ AnonymizerEngine (per-tenant policy)      │ │
│  └────────────────────────────────────────────────────┘ │
│                          │                                │
│                          ▼                                │
│              リクエスト本文をマスク済みに置換               │
│                          │                                │
│                          ▼                                │
│              LLMプロバイダへ転送                          │
│                          │                                │
│                          ▼                                │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Post-Call Hook (async)                              │ │
│  │  └→ PIIScanner.scan_response()                      │ │
│  │       ├→ S3監査ログにマスク済み版を保存             │ │
│  │       └→ メトリクス: pii_detected_total++           │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 3.2 PIIScanner クラス（中核）

```
class PIIScanner:
    def __init__(self, analyzer, anonymizer, policy_loader)
    def scan_request(self, request: dict, tenant_id: str) -> ScanResult
    def scan_response(self, response: dict, tenant_id: str) -> ScanResult
```

`ScanResult`:
- `original_text`: 元テキスト
- `masked_text`: マスク後テキスト
- `entities`: 検出エンティティのリスト（種別・位置・信頼度）
- `policy_action`: `mask` / `redact` / `block` / `tag_only` / `pass`
- `should_block`: ブロックすべきか

### 3.3 マスキング戦略

| 戦略 | 動作 | 用途 |
|---|---|---|
| `replace` | プレースホルダに置換（`<JP_MY_NUMBER>`） | 機密度高 |
| `mask` | 一部マスク（`****-****-9012`） | 中度、コンテキスト維持 |
| `hash` | 決定的ハッシュ（HMAC-SHA256） | 同一値を識別したい場合 |
| `tag_only` | 検出だけしてマスクしない | ロギング・分析のみ |
| `block` | リクエストを拒絶 | 超機密（マイナンバー等のデフォルト） |

### 3.4 テナント別ポリシー

YAML / JSONで定義：

```yaml
default:
  entities:
    JP_MY_NUMBER: { action: block }
    CREDIT_CARD:  { action: replace }
    EMAIL_ADDRESS: { action: mask, keep_chars: 2 }
    JP_PHONE_NUMBER: { action: mask, keep_chars: 4 }
    JP_PERSON_NAME: { action: replace }
    JP_ADDRESS: { action: replace }

tenants:
  tenant_abc123:
    overrides:
      JP_PHONE_NUMBER: { action: pass }   # 電話番号を意図的に通す
      JP_WAREKI_DATE:  { action: replace }
```

---

## 4. 性能要件と最適化

| 指標 | 目標 |
|---|---|
| プロキシ追加レイテンシ p99 | < 50ms（1KB プロンプト） |
| スループット | 1 instance あたり 50 req/s |
| メモリ | 1 instance あたり 1GB 以内 |

### 最適化手法

1. **NLPエンジンの事前ロード**: spaCy ja_core_news_md をプロセス起動時にロード
2. **正規表現のコンパイルキャッシュ**: 認識子インスタンスは1個のみ
3. **テナント設定キャッシュ**: 5分TTLのin-memory
4. **大きすぎるテキストの分割**: 32KB超は4KB単位に分割して並列スキャン
5. **オプトアウト**: テキスト長 < 10文字は明らかにPII無しならスキャン省略（高速判定）

---

## 5. 安全装置

### 5.1 PIIスキャナ自体の障害時

- **デフォルト動作**: `BLOCK` — スキャナが落ちたらリクエストを拒絶する（fail-secure）
- **設定でオーバーライド可**: テナントが `fail_open=true` を選択した場合のみ、警告ヘッダ付きで通過

### 5.2 検知漏れリスク

- **多段検証**: pattern + context + (一部) ML
- **誤検知許容**: false positive を多めに検知し、ポリシーで `mask` するのが安全寄り
- **顧客側でのレビュー機能**: 観測ダッシュボードに「マスクされた候補テキスト」を表示し、誤検知を顧客が確認可能（マスク済みのみ表示し本物は表示しない）

### 5.3 検出ログの取扱い

- PII種別・位置・件数のみ記録
- **マスク前の本文はストレージに保存しない**（顧客が要求した場合のみ短期保管、別Keyで暗号化）
- 個別レコード分析時はテナント管理者にのみ表示

---

## 6. テスト戦略

### 6.1 ユニットテスト

各カスタム認識子に対し以下：
- 正例 50〜200ケース
- 負例（似て非なる文字列）50〜100ケース
- チェックデジット検証の境界
- コンテキスト依存（前後の単語）

### 6.2 統合テスト

PIIScanner 全体に対し：
- ポリシー切替
- 複数エンティティ同時検出
- 多言語混在
- 長文・短文・絵文字
- ステートフル動作（同一テキストの繰り返し）

### 6.3 ゴールデンセット

実際の業務文書を匿名化したフィクスチャ：
- 議事録風
- 契約書風
- メール風
- 顧客問合せ風
- 求人エントリー風

### 6.4 性能テスト

- 1KB / 10KB / 100KB プロンプトのレイテンシ
- 並列100スレッドでスループット計測
- メモリリークの長時間テスト（24h）

---

## 7. デプロイ・運用

### 7.1 配布

- Pythonパッケージ `aegis_pii_jp` として LiteLLM のコンテナに同梱
- spaCyモデル `ja_core_news_md` も Docker image に含める（~200MB）

### 7.2 設定管理

- グローバルデフォルト：Gitリポ管理、PR レビュー必須
- テナント別オーバーライド：Aegis 管理画面から変更、操作ログを取得

### 7.3 メトリクス

| メトリクス | 用途 |
|---|---|
| `pii_scan_duration_seconds` | レイテンシ監視 |
| `pii_entities_detected_total{entity, tenant}` | 検出率 |
| `pii_actions_total{action, tenant}` | ポリシー適用 |
| `pii_scan_errors_total` | スキャナ障害 |
| `pii_blocked_requests_total` | ブロックされたリクエスト |

---

## 8. ライセンスと依存関係

| パッケージ | ライセンス | 役割 |
|---|---|---|
| `presidio-analyzer` | MIT | 検出エンジン |
| `presidio-anonymizer` | MIT | マスク処理 |
| `spacy` | MIT | NLP |
| `ja_core_news_md` | CC BY-SA 4.0 | 日本語spaCyモデル |
| `regex` | Apache-2.0 | 高度な正規表現 |

CC BY-SA 4.0 のモデルは「派生著作物の同一ライセンス公開」を要するが、推論結果（メタデータ）は派生著作物に該当しない判断。モデルファイル自体を改変・再配布する場合のみ義務発生。**当社はモデルを改変しない**前提。

---

## 9. 既知の限界

1. **氏名検出の精度**: spaCy ja_core_news_md の人名認識は精度70〜85%、レアな氏名は取りこぼし
2. **文脈依存PII**: 「会員番号」「口座番号」など、フォーマットだけでは特定できないものはコンテキスト必須
3. **画像内テキスト**: スコープ外（v2でOCR連携）
4. **ストリーミングレスポンス**: チャンク単位でのスキャンは現実装では不可、累積バッファ方式へ
5. **多言語混在**: 日本語＋英語混在のPII（例：英文住所）は精度低下

---

## 10. 今後の拡張

- v1.1: 業種別カスタムエンティティ（医療：レセプト番号、金融：口座番号フォーマット個別対応）
- v1.2: LLM-as-a-Judge による誤検知レビュー
- v2: 画像・PDFのOCR連携
- v2: 多言語並行検出（英・中・韓）
