# データフロー図：Aegis

すべて Mermaid 記法。GitHubでレンダリング可能。

---

## DFL-01：システム全体（コンテキスト図）

```mermaid
flowchart LR
    Customer["顧客<br/>(中小企業のAIアプリ)"]
    Aegis["Aegis Platform<br/>(AWS Tokyo)"]
    LLM["LLMプロバイダ<br/>Anthropic / OpenAI<br/>Bedrock / Gemini"]
    Operator["Aegis運用担当<br/>(自社オペレーター)"]
    Notification["通知チャネル<br/>Slack / Chatwork / Email"]

    Customer -- "LLMリクエスト<br/>(OpenAI互換API)" --> Aegis
    Aegis -- "プロキシ転送<br/>+ 顧客APIキー使用" --> LLM
    LLM -- "レスポンス" --> Aegis
    Aegis -- "レスポンス<br/>(PIIマスク済み)" --> Customer

    Aegis -- "管理画面<br/>レポート閲覧" --> Customer
    Aegis -- "アラート / 月次レポート" --> Notification
    Operator -- "テナント管理<br/>運用業務" --> Aegis
    Aegis -- "稼働状況<br/>アラート" --> Operator
```

---

## DFL-02：LLMリクエスト処理（同期パス）

```mermaid
sequenceDiagram
    autonumber
    participant App as 顧客AIアプリ
    participant ALB as ALB + WAF
    participant Auth as Auth Gateway
    participant Proxy as LiteLLM Proxy
    participant PII as Presidio (PII)
    participant Guard as Guardrails
    participant Sec as Secrets Manager
    participant LLM as LLMプロバイダ
    participant Bus as Event Bus
    participant CH as ClickHouse
    participant S3 as S3 (audit)

    App->>ALB: POST /v1/chat/completions<br/>Authorization: Bearer aeg_live_...
    ALB->>Auth: rate limit, WAFチェック
    Auth->>Auth: APIキー検証 (hash照合)
    Auth->>Proxy: tenant_id付与
    Proxy->>PII: リクエストPIIスキャン
    PII-->>Proxy: マスク済みリクエスト + 検出フラグ
    Proxy->>Guard: プロンプトインジェクションチェック
    Guard-->>Proxy: pass / block
    Proxy->>Sec: 顧客のLLM APIキー取得 (KMS復号)
    Sec-->>Proxy: 復号済みキー
    Proxy->>LLM: 転送 (顧客APIキー)
    LLM-->>Proxy: レスポンス + 使用トークン
    Proxy->>PII: レスポンスPIIスキャン
    PII-->>Proxy: マスク済みレスポンス
    Proxy-->>App: レスポンス返却 (p99 <50ms overhead)
    Proxy->>Bus: イベント発行(非同期)
    Bus->>CH: 集計用イベント書込
    Bus->>S3: マスク済み本文を保管
```

---

## DFL-03：コスト・予算・アラート

```mermaid
flowchart TB
    subgraph Ingestion["イベント取込"]
        Event["llm_event発生<br/>(プロキシから)"]
        Calc["コスト計算<br/>(model別単価表)"]
    end

    subgraph Storage["集計層"]
        CHRaw["ClickHouse<br/>llm_events (生)"]
        CHAgg["ClickHouse<br/>materialized view<br/>(分・時・日別)"]
    end

    subgraph AlertEngine["アラートエンジン"]
        Sched["スケジューラ<br/>(1分毎)"]
        Eval["閾値評価<br/>(daily/monthly予算)"]
        Dedup["重複抑制<br/>(同日同種は1回)"]
    end

    subgraph Delivery["配信"]
        Slack["Slack Webhook"]
        Chat["Chatwork API"]
        Mail["SES Email"]
        DBA["alerts table<br/>に永続化"]
    end

    Event --> Calc
    Calc --> CHRaw
    CHRaw --> CHAgg
    Sched --> Eval
    CHAgg --> Eval
    Eval -->|閾値超過| Dedup
    Dedup --> Slack
    Dedup --> Chat
    Dedup --> Mail
    Dedup --> DBA
```

### アラート閾値ルール

| ルールID | 条件 | severity | 通知先 |
|---|---|---|---|
| R-COST-D80 | 日次予算の80%消化 | warn | Slack |
| R-COST-D100 | 日次予算超過 | critical | Slack + Email |
| R-COST-D200 | 日次予算200%（hard cap） | critical | + 自動suspend |
| R-COST-M80 | 月次予算80% | warn | Slack |
| R-ERR-5XX | 5xxレート 5% × 5分 | warn | Slack |
| R-ERR-PROV | プロバイダ完全停止 | critical | Slack + auto-failover |
| R-PII | 高機密PII検知（マイナンバー等） | critical | Email |
| R-LAT-P99 | p99レイテンシ前日比+3σ | info | Slack |

---

## DFL-04：フェイルオーバー

```mermaid
sequenceDiagram
    autonumber
    participant App as 顧客アプリ
    participant Proxy as LiteLLM Proxy
    participant Primary as Anthropic API
    participant Secondary as AWS Bedrock<br/>(Claude)
    participant Alert as アラート

    App->>Proxy: chat/completions
    Proxy->>Primary: リクエスト
    Note over Primary: 障害 / 5xx / timeout
    Primary--xProxy: error
    Proxy->>Proxy: failover判定<br/>(同モデル別経路あるか)
    Proxy->>Secondary: 同等モデルへ転送
    Secondary-->>Proxy: 成功
    Proxy-->>App: レスポンス<br/>(X-Aegis-Failover header)
    Proxy->>Alert: provider_down イベント
    Alert->>Alert: 顧客 + 運用へ通知
```

ルーティング設定例（顧客テナント単位、YAML）：

```yaml
model_list:
  - model_name: claude-opus-4-7
    litellm_params:
      model: anthropic/claude-opus-4-7
      api_key: os.environ/CUSTOMER_ANTHROPIC_KEY
    failover:
      - model: bedrock/anthropic.claude-opus-4-7-v1:0
        api_key: os.environ/CUSTOMER_AWS_KEY
```

---

## DFL-05：月次レポート生成

```mermaid
flowchart LR
    Cron["毎月1日 03:00 JST<br/>EventBridge"]
    Worker["Report Worker<br/>(Celery task)"]
    CH["ClickHouse<br/>集計クエリ"]
    PG["PostgreSQL<br/>tenant設定"]
    Tpl["HTMLテンプレ<br/>(Jinja2)"]
    PDF["WeasyPrint<br/>HTML→PDF"]
    S3["S3<br/>reports/{tenant}/{ym}.pdf"]
    DB["reports テーブル"]
    Notify["顧客通知<br/>Slack + Email"]

    Cron --> Worker
    Worker --> PG
    Worker --> CH
    PG --> Tpl
    CH --> Tpl
    Tpl --> PDF
    PDF --> S3
    PDF --> DB
    S3 --> Notify
```

レポート生成のステップ：

1. テナント全件取得（active のみ）
2. テナントごとに前月分のClickHouse集計クエリ（コスト、呼出、エラー、レイテンシ、モデル別、user_label別）
3. インシデント一覧（alerts テーブル）取得
4. 改善提案（プランによりLLMで自動生成 + オペレーターが朱入れ）
5. HTML → PDF → S3保存
6. 顧客通知（署名URL有効期限7日）

---

## DFL-06：プロビジョニング（顧客オンボーディング）

```mermaid
sequenceDiagram
    autonumber
    participant Sales as 営業担当
    participant Admin as Aegis社内UI
    participant API as Control Plane API
    participant SM as Secrets Manager
    participant Email as 顧客連絡先
    participant Cust as 顧客CTO

    Sales->>Admin: 新規テナント作成<br/>(社名・プラン・連絡先)
    Admin->>API: POST /internal/tenants
    API->>API: tenant_id発行<br/>retention/quota設定
    API-->>Admin: tenant作成完了
    Admin->>API: POST /tenants/{id}/api-keys
    API->>API: APIキー生成<br/>(prefix + secret)
    API-->>Admin: 平文キー(1回限り表示)
    Sales->>Cust: APIキー + 接続手順送付<br/>(SECURE channel)
    Cust->>SM: LLM APIキー登録<br/>(顧客が管理画面から)
    SM-->>API: secret_ref保存
    Cust->>Cust: アプリのbase_url変更<br/>(SDK env var)
    Cust->>API: 疎通確認 POST /v1/chat/completions
    API-->>Cust: 200 OK
    Sales->>Cust: 初回キックオフMTG設定
```

---

## DFL-07：監査ログエクスポート

```mermaid
flowchart TB
    Req["顧客 / 監査要求<br/>(個情委 / 内部監査)"]
    UI["顧客管理画面<br/>or 社内画面"]
    API["GET /audit/export<br/>?from=&to=&format="]
    Auth["権限チェック<br/>(Admin/Audit Role)"]
    Job["非同期ジョブ作成"]
    Worker["Export Worker"]
    CH["ClickHouse<br/>tenant_idでフィルタ"]
    S3R["S3 audit本文取得<br/>(必要な場合)"]
    Pack["ZIP化<br/>CSV/JSON + manifest"]
    Sign["署名URL生成<br/>(有効期限24h)"]
    Notify["完了通知"]
    Audit["audit_exports テーブル<br/>に痕跡記録"]

    Req --> UI
    UI --> API
    API --> Auth
    Auth -->|OK| Job
    Job --> Worker
    Worker --> CH
    Worker --> S3R
    CH --> Pack
    S3R --> Pack
    Pack --> Sign
    Sign --> Notify
    Worker --> Audit
```

エクスポート内容：
- メタ：tenant_id、期間、リクエスト件数、エクスポート実施者、目的
- 本体：イベント一覧CSV（コスト、モデル、ステータス、user_label、PII検知フラグ）
- 本文（要求時）：S3から取得した マスク済み req/res JSON
- manifest.json：SHA256ハッシュ、件数、エクスポート時刻

---

## DFL-08：Eval自動実行（v1機能）

```mermaid
flowchart LR
    Trig1["手動トリガ<br/>(モデル評価依頼)"]
    Trig2["スケジュール<br/>(週次)"]
    Trig3["新モデルリリース検知<br/>(プロバイダAPI)"]

    Sampler["過去30日のサンプリング<br/>(50〜500件、テナント単位)"]
    Mask["PII完全マスク"]
    Promptfoo["Promptfoo実行<br/>YAML設定"]

    M1["対象モデルA<br/>(現行)"]
    M2["対象モデルB<br/>(新規)"]

    Judge["LLM-as-a-Judge<br/>(Claude Opus 4.7)"]
    Metrics["品質スコア<br/>コスト比<br/>レイテンシ比"]
    Report["評価レポート<br/>PDF"]
    Customer["顧客提案"]

    Trig1 --> Sampler
    Trig2 --> Sampler
    Trig3 --> Sampler
    Sampler --> Mask
    Mask --> Promptfoo
    Promptfoo --> M1
    Promptfoo --> M2
    M1 --> Judge
    M2 --> Judge
    Judge --> Metrics
    Metrics --> Report
    Report --> Customer
```

---

## DFL-09：データ保持・削除ライフサイクル

```mermaid
gantt
    title データ保持ライフサイクル（テナント:Standardプラン）
    dateFormat YYYY-MM-DD
    axisFormat %m/%d

    section ClickHouse Events
    Hot (即時クエリ可能)       :active, 2026-05-01, 90d
    Cold (S3パーティション)    :2026-07-30, 90d
    削除                      :crit, 2026-10-28, 1d

    section S3 リクエスト本文
    Standard Storage          :2026-05-01, 30d
    IA Storage                :2026-05-31, 60d
    Glacier                   :2026-07-30, 90d
    削除                      :crit, 2026-10-28, 1d

    section Reports PDF
    保存（解約まで）          :active, 2026-05-01, 365d
```

プラン別保持期間：

| プラン | events | 本文 |
|---|---|---|
| Lite | 90日 | 30日 |
| Standard | 180日 | 90日 |
| Pro | 365日 | 180日 |
| Pro + Audit Addon | 365日 | 365日 |

---

## DFL-10：請求フロー（freee連携、v1）

```mermaid
sequenceDiagram
    autonumber
    participant Cron as 月初バッチ
    participant Billing as Billing Service
    participant PG as PostgreSQL
    participant Freee as freee API
    participant Email as 顧客連絡先

    Cron->>Billing: 月初実行
    Billing->>PG: active tenant一覧取得
    loop 各テナント
        Billing->>Billing: 月額 + 従量超過 + スポット計算
        Billing->>Freee: 請求書作成<br/>(取引先・品目・金額)
        Freee-->>Billing: invoice_id
        Billing->>PG: invoices テーブルに記録
        Billing->>Email: 請求書PDF送付
    end
```

---

## 補足：データの境界（What goes where）

| データ種別 | 保存先 | 暗号化 | 保持 |
|---|---|---|---|
| テナントメタデータ | PostgreSQL | TDE | 解約まで |
| APIキーハッシュ | PostgreSQL | TDE | 失効まで |
| 顧客LLMプロバイダAPIキー | Secrets Manager | KMS | 解約まで |
| LLMイベント（数値メタ） | ClickHouse | 保管時暗号化 | プラン別 |
| リクエスト/レスポンス本文 | S3 | KMS Envelope | プラン別 |
| アラート履歴 | PostgreSQL | TDE | 解約まで |
| 月次レポートPDF | S3 | KMS | 解約まで |
| 監査エクスポート履歴 | PostgreSQL | TDE | 7年 |
| 顧客アプリのソースコード | ❌保管しない | - | - |
| 顧客従業員の個人情報 | ❌保管しない（PIIマスク） | - | - |
