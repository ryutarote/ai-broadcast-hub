# 基本設計書：Aegis（AIエージェント運用代行サービス）

## 0. ドキュメント情報

| 項目 | 内容 |
|---|---|
| 対象システム | Aegis Managed AI Operations Platform |
| バージョン | v0.1（MVPスコープ） |
| 作成日 | 2026-05-14 |
| 関連文書 | PRD.md, data-flow.md |

---

## 1. システム構成

### 1.1 全体アーキテクチャ

```
┌────────────────────────────────────────────────────────────────┐
│ 顧客環境（Customer Environment）                                │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐                          │
│  │ 顧客AIアプリ  │───▶│ Aegis SDK     │                          │
│  │ (Claude Code  │    │ or env var    │                          │
│  │  製の自社製)  │    │  base_url     │                          │
│  └──────────────┘    └──────┬───────┘                          │
└─────────────────────────────┼───────────────────────────────────┘
                              │ HTTPS (TLS 1.3)
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ Aegis Platform（AWS東京リージョン）                              │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Edge Layer                                               │  │
│  │  ┌──────────┐  ┌─────────────┐  ┌──────────────────┐   │  │
│  │  │ CloudFront│─▶│  ALB (WAF)  │─▶│ Auth Gateway     │   │  │
│  │  └──────────┘  └─────────────┘  │ (API Key検証)    │   │  │
│  │                                  └────────┬─────────┘   │  │
│  └───────────────────────────────────────────┼─────────────┘  │
│                                              ▼                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Application Layer (ECS Fargate)                          │  │
│  │  ┌─────────────────┐  ┌─────────────────────────────┐   │  │
│  │  │ LiteLLM Proxy   │  │ Aegis Control Plane         │   │  │
│  │  │ (multi-tenant)  │  │ - Tenant API                │   │  │
│  │  │ - routing       │  │ - Admin Web UI (Next.js)    │   │  │
│  │  │ - failover      │  │ - Report Generator          │   │  │
│  │  │ - cost calc     │  │ - Alert Engine              │   │  │
│  │  └────────┬────────┘  └──────────────┬──────────────┘   │  │
│  │           │                          │                  │  │
│  │           ▼                          ▼                  │  │
│  │  ┌───────────────────┐    ┌─────────────────────┐      │  │
│  │  │ Langfuse Backend  │    │ Worker (Sidekiq互換) │      │  │
│  │  │ (observability)   │    │ - PDF gen           │      │  │
│  │  └────────┬──────────┘    │ - Eval runs         │      │  │
│  │           │                │ - Alert dispatch    │      │  │
│  │           │                └──────────┬──────────┘      │  │
│  └───────────┼───────────────────────────┼─────────────────┘  │
│              ▼                           ▼                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Data Layer                                               │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │  │
│  │  │ PostgreSQL │  │ ClickHouse   │  │ S3 (audit log) │  │  │
│  │  │ (RDS)      │  │ (events)     │  │ (KMS暗号化)    │  │  │
│  │  └────────────┘  └──────────────┘  └────────────────┘  │  │
│  │  ┌────────────┐  ┌──────────────────────────────────┐  │  │
│  │  │ Redis      │  │ Secrets Manager (顧客APIキー)    │  │  │
│  │  │ (rate lim) │  │ (envelope encryption)           │  │  │
│  │  └────────────┘  └──────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────┬─────────────────────────────────────────────┘
                   │
                   ▼ 顧客APIキー使用してLLM呼出
   ┌────────────────────────────────────────────────────┐
   │ External LLM Providers                              │
   │  Anthropic │ OpenAI │ AWS Bedrock │ Google Gemini  │
   └────────────────────────────────────────────────────┘
```

### 1.2 デプロイ構成

| レイヤー | 実体 | 冗長化 |
|---|---|---|
| Edge | CloudFront + ALB（東京） | Multi-AZ |
| App | ECS Fargate（2タスク以上） | Multi-AZ |
| DB | RDS Aurora PostgreSQL | Multi-AZ + Read Replica |
| Events | ClickHouse Cloud（東京） or 自前ECS | Replicated |
| Cache | ElastiCache Redis | Cluster |
| Object | S3（東京）+ Versioning | リージョン内冗長 |
| Secrets | AWS Secrets Manager + KMS | 標準 |

---

## 2. 技術スタック

| 層 | 技術 | 採用理由 |
|---|---|---|
| 言語（バックエンド） | Python 3.12 + FastAPI | LiteLLM/Langfuseとの親和性 |
| 言語（フロント） | TypeScript + Next.js 15 (App Router) | 管理画面の生産性 |
| プロキシ | **LiteLLM**（MIT） | OpenAI互換、マルチプロバイダ標準対応 |
| 観測 | **Langfuse**（MIT/EE） | OSS、トレーシング、Eval統合 |
| Eval | **Promptfoo**（MIT） | YAMLベース、CI連携 |
| PII検知 | **Microsoft Presidio**（MIT） | 日本語拡張可能 |
| ガードレール | **Guardrails AI / NeMo Guardrails** | OSS |
| メトリクス | Prometheus + Grafana | 標準 |
| アラート | AlertManager + 自作Webhook | Slack/Chatwork配信 |
| インフラ | AWS（Tokyo） + Terraform | IaC |
| CI/CD | GitHub Actions | 標準 |
| ジョブ | Celery + Redis（Python）または BullMQ | レポート生成・Eval実行 |
| PDF生成 | WeasyPrint or Playwright HTML→PDF | 日本語フォント対応 |

### ライセンス整理（重要）

| OSS | ライセンス | 利用形態 | 商用利用可否 |
|---|---|---|---|
| LiteLLM | MIT | 改変・組込 | ◎ |
| Langfuse Core | MIT | 改変・組込 | ◎ |
| Langfuse EE機能 | Commercial | 必要時に商用ライセンス購入 | 要契約 |
| Promptfoo | MIT | CLI/SDK | ◎ |
| Presidio | MIT | SDK | ◎ |

**結論**：MVPはMIT範囲内で完全に組成可能。EE機能（SSO、監査ログ高度版）はv1で契約検討。

---

## 3. データモデル

### 3.1 PostgreSQL（メタデータ）

#### tenants（顧客テナント）
```sql
CREATE TABLE tenants (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            VARCHAR(200) NOT NULL,
  plan            VARCHAR(20) NOT NULL,  -- 'lite' | 'standard' | 'pro'
  status          VARCHAR(20) NOT NULL,  -- 'active' | 'suspended' | 'churned'
  retention_days  INTEGER NOT NULL DEFAULT 90,
  contact_email   VARCHAR(200) NOT NULL,
  slack_webhook   TEXT,
  chatwork_token  TEXT,
  billing_amount  INTEGER,  -- 月額（円）
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### api_keys（顧客発行APIキー）
```sql
CREATE TABLE api_keys (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  key_hash      VARCHAR(128) NOT NULL UNIQUE,
  prefix        VARCHAR(12) NOT NULL,  -- 'aeg_live_xxx'
  label         VARCHAR(100),
  revoked_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON api_keys (tenant_id, revoked_at);
```

#### provider_credentials（顧客のLLMプロバイダ資格情報）
```sql
CREATE TABLE provider_credentials (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider        VARCHAR(50) NOT NULL,  -- 'anthropic' | 'openai' | 'bedrock' | 'gemini'
  secret_ref      TEXT NOT NULL,         -- Secrets Manager ARN
  is_primary      BOOLEAN NOT NULL DEFAULT false,
  failover_order  INTEGER,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### budgets（コスト予算）
```sql
CREATE TABLE budgets (
  tenant_id     UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  daily_jpy     INTEGER,
  monthly_jpy   INTEGER,
  alert_pct     INTEGER NOT NULL DEFAULT 80,  -- 80%で警告
  hard_pct      INTEGER NOT NULL DEFAULT 200, -- 200%で遮断
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### alerts（アラート発火履歴）
```sql
CREATE TABLE alerts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id),
  type         VARCHAR(50) NOT NULL,  -- 'cost_threshold' | 'error_rate' | 'provider_down' | 'pii_leak'
  severity     VARCHAR(20) NOT NULL,  -- 'info' | 'warn' | 'critical'
  payload      JSONB NOT NULL,
  delivered_to JSONB,                  -- {slack: true, email: true, chatwork: false}
  fired_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at  TIMESTAMPTZ
);
CREATE INDEX ON alerts (tenant_id, fired_at DESC);
```

#### reports（月次レポート）
```sql
CREATE TABLE reports (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id),
  period_ym    CHAR(7) NOT NULL,  -- '2026-05'
  pdf_s3_key   TEXT NOT NULL,
  summary      JSONB NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, period_ym)
);
```

### 3.2 ClickHouse（高頻度イベント）

#### llm_events（リクエスト1件1行）
```sql
CREATE TABLE llm_events (
  event_id          UUID,
  tenant_id         UUID,
  api_key_id        UUID,
  provider          LowCardinality(String),
  model             LowCardinality(String),
  endpoint          LowCardinality(String),
  request_id        String,
  user_label        String,      -- 顧客が付与する識別子
  prompt_tokens     UInt32,
  completion_tokens UInt32,
  total_cost_jpy    Decimal(12, 4),
  latency_ms        UInt32,
  status_code       UInt16,
  error_type        LowCardinality(String),
  pii_detected      UInt8,
  hallucination_score Float32,
  ts                DateTime64(3, 'Asia/Tokyo')
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(ts)
ORDER BY (tenant_id, ts);

CREATE INDEX idx_model ON llm_events (model) TYPE bloom_filter GRANULARITY 1;
```

リクエスト本文・レスポンス本文は**ClickHouseに置かず**、S3に分離保管（後述）。

### 3.3 S3（リクエスト/レスポンス本文）

```
s3://aegis-audit-jp/
  ├─ tenant_id={uuid}/
  │   └─ ts={YYYY}/{MM}/{DD}/{HH}/
  │       ├─ {event_id}.req.json.gz   # マスキング済みリクエスト
  │       └─ {event_id}.res.json.gz   # マスキング済みレスポンス
```

- KMSのカスタマー管理キーで暗号化
- バケットポリシーでテナント間アクセス遮断
- ライフサイクル：90/180/365日後にGlacier、その後削除

---

## 4. API設計

### 4.1 顧客向けAPI（プロキシ）

**ベースURL**: `https://gw.aegis.jp/v1`

LiteLLM の OpenAI互換APIをそのまま提供：

```
POST /v1/chat/completions
POST /v1/completions
POST /v1/embeddings
POST /v1/messages              # Anthropic互換
```

認証ヘッダ：
```
Authorization: Bearer aeg_live_XXXXXXXXXXXX
X-Aegis-User-Label: <任意の識別子>   # コスト分析用、optional
```

モデル指定例：
```json
{
  "model": "claude-opus-4-7",
  "messages": [...],
  "metadata": {
    "aegis_use_case": "contract_review"  // 任意タグ
  }
}
```

フェイルオーバー時：
- プライマリ失敗時、`X-Aegis-Failover: anthropic→bedrock` ヘッダで通知

### 4.2 管理API（Aegis Control Plane）

**ベースURL**: `https://api.aegis.jp/v1`

| メソッド | パス | 用途 |
|---|---|---|
| POST | `/tenants` | テナント作成（社内向け） |
| GET | `/tenants/me` | 自テナント情報取得 |
| POST | `/tenants/me/api-keys` | APIキー発行 |
| DELETE | `/tenants/me/api-keys/{id}` | APIキー失効 |
| GET | `/usage` | 利用量取得（クエリ：from, to, group_by） |
| GET | `/costs` | コスト取得 |
| POST | `/budgets` | 予算設定 |
| GET | `/alerts` | アラート履歴 |
| GET | `/reports` | レポート一覧 |
| GET | `/reports/{id}/pdf` | PDFダウンロード（署名URL） |
| GET | `/audit/export?from=&to=&format=csv` | 監査ログエクスポート |

認証：管理画面はOAuth（Google / Microsoft Entra ID）、APIは個別トークン。

### 4.3 内部API（社内オペレーション）

- `POST /internal/tenants/{id}/suspend`
- `POST /internal/billing/invoice` （freee連携）
- `POST /internal/reports/{tenant_id}/{ym}/regenerate`

---

## 5. マルチテナント設計

### 5.1 分離戦略

| レイヤー | 戦略 |
|---|---|
| LiteLLM | テナントごとに**Virtual Key**（LiteLLM標準機能）。1プロセスで全テナント共有 |
| PostgreSQL | 単一DB・単一スキーマ・`tenant_id`列で論理分離。Row Level Security有効化 |
| ClickHouse | 単一テーブル、`tenant_id`をパーティションキーに含めずORDER BYに |
| S3 | プレフィックス分離 `tenant_id={uuid}/...` |
| Secrets | テナントごとに別シークレット |
| 監査ログ | テナント単位エクスポート |

### 5.2 ノイジーネイバー対策

- LiteLLM Virtual Keyでテナント別 rate limit（既定 60 req/s/tenant）
- 月額プランに応じた上限設定
- 異常検知時、自動的にAlert + soft cap

---

## 6. セキュリティ設計

### 6.1 認証・認可

| 対象 | 方式 |
|---|---|
| 顧客APIアクセス | APIキー（bcryptハッシュで保存、表示は1回限り） |
| 顧客管理画面 | OAuth（Google / Microsoft Entra ID）+ MFA必須 |
| 社内オペレーション画面 | SSO + Role（Admin / Support / ReadOnly） |
| 内部API間通信 | mTLS + 内部VPC |

### 6.2 鍵管理

- 顧客のLLMプロバイダAPIキーはSecrets Manager + KMS Envelope暗号化
- アプリは復号権限のみ、人間は取得不可
- 監査：Secret取得は全件CloudTrailで記録

### 6.3 PII保護

リクエストボディに対し**ingressでPresidioを通す**：
1. 検出（メール、電話、マイナンバー、クレカ、住所など）
2. ポリシーに応じてマスク／ブロック／タグ付け
3. マスク結果がS3保管対象（生データは保管しない）

### 6.4 監査ログ

- API操作・管理画面操作・Secret取得・データエクスポート全てCloudTrail + 独自監査ログテーブルに記録
- 顧客向けエクスポートは「リクエスト数・コスト・エラー・モデル」レベル（プロンプト本文はオプション）

### 6.5 ネットワーク

- VPC：Private Subnet（App/DB）+ Public Subnet（ALB only）
- Egress：LLMプロバイダのみ許可（NAT Gateway + 許可リスト）
- WAF：OWASP Top10 + 異常レート制限

### 6.6 規制対応

| 規制 | 対応 |
|---|---|
| 個人情報保護法 | 委託契約、PII最小化、削除要求対応API |
| 電子帳簿保存法 | 監査ログのタイムスタンプ・改ざん検知（v1） |
| ISMS（v1〜） | 文書整備、年次内部監査 |
| SOC2 Type 1（v1） | 監査法人選定→6ヶ月運用→監査 |

---

## 7. 運用設計

### 7.1 監視

| 対象 | 監視項目 | ツール |
|---|---|---|
| LiteLLMプロキシ | p99レイテンシ、エラー率、req/s | Prometheus |
| Langfuse | ingestion lag、ストレージ使用量 | Prometheus |
| RDS | CPU、Connection、Replica lag | CloudWatch |
| ClickHouse | クエリ時間、ディスク | 内蔵metrics |
| 顧客アラート | アラート未対応SLA | 自作Dashboard |

### 7.2 オンコール

- 1人体制（MVP）：勤務時間内のみアラート対応、夜間はベストエフォート
- v1で副業1名追加し12時間カバー
- Pagerduty or Better Stack でローテーション

### 7.3 バックアップ

- RDS：自動スナップショット日次、PITR 14日
- S3：Versioning + クロスリージョン複製（大阪）はv1で
- ClickHouse：日次バックアップ、リテンション30日

### 7.4 DR（災害復旧）

- RTO：4時間（v1）/ 1時間（v2、大阪リージョン待機）
- RPO：1時間

### 7.5 顧客運用フロー

| 頻度 | 作業 | 工数目安 |
|---|---|---|
| 日次 | アラート確認・対応 | 30分 |
| 週次 | 顧客別ダッシュボード確認 | 顧客あたり10分 |
| 月次 | レポート配信、月次面談 | 顧客あたり60分 |
| 四半期 | モデル評価、改善提案 | 顧客あたり120分 |

---

## 8. レポート設計

### 8.1 月次レポートPDF（標準フォーマット）

| ページ | 内容 |
|---|---|
| 1 | 表紙：顧客名、対象期間、サマリー（コスト、呼出数、エラー率） |
| 2 | コスト推移グラフ（日次）、前月比、予算消化率 |
| 3 | モデル別利用、ユースケース別利用（user_labelで集計） |
| 4 | 品質指標：エラー率、レイテンシp50/p95/p99、ハルシネーション推定 |
| 5 | インシデント一覧と対応 |
| 6 | 改善提案（プランによって2〜10件） |
| 7 | 次月の見通し、注意点 |

WeasyPrintで日本語フォント（Noto Sans JP）対応。

### 8.2 経営者向けダッシュボード

- AI投資額 vs 推定削減効果（業務時間×時給）
- 「今月のAIによる工数削減：450時間」のようなKPI
- 部門別利用ヒートマップ

---

## 9. デプロイ・CI/CD

### 9.1 ブランチ戦略

- `main`：本番反映
- `develop`：ステージング
- 機能ブランチ：`feat/xxx`

### 9.2 パイプライン

```
PR → GitHub Actions
  ├─ Lint (ruff, eslint)
  ├─ Unit Test (pytest, vitest)
  ├─ Integration Test (docker-compose)
  ├─ Security Scan (trivy, gitleaks)
  └─ Build & Push to ECR

Merge to develop
  └─ Auto deploy to staging (ECS rolling)

Tag v* on main
  └─ Manual approve → Prod deploy (Blue/Green)
```

### 9.3 環境

| 環境 | 用途 | データ |
|---|---|---|
| dev | 開発（ローカルdocker-compose） | サンプル |
| staging | 受入テスト | 匿名化済み本番サブセット |
| prod | 本番 | 本物 |

---

## 10. 開発体制とロードマップ

### 10.1 MVP（90日）の人月

- 開発：1人（フルタイム）×3ヶ月
- インフラ：副業 0.2人月
- デザイン：副業 0.3人月
- **合計：約3.5人月**

### 10.2 マイルストーン

| 週 | 完了基準 |
|---|---|
| W1-2 | AWS基盤、Terraform雛形、LiteLLM+Langfuseがdocker-composeで動く |
| W3-4 | テナントAPI、APIキー発行、最小プロキシ通せる |
| W5-6 | ダッシュボードUI（Next.js）、コスト集計 |
| W7-8 | アラートエンジン、Slack配信、予算機能 |
| W9-10 | 月次PDFレポート生成、監査ログエクスポート |
| W11 | 知人企業3社で無料PoC開始 |
| W12 | フィードバック反映、Lite/Standardプラン提供開始 |

---

## 11. 未決事項

- [ ] Langfuse EE版の機能要否（MVPはOSS範囲で）
- [ ] ClickHouse自前運用 vs Cloud（東京リージョン提供開始確認）
- [ ] 1人運用時の長期休暇対応（業務委託 / 一時停止条項）
- [ ] freee/MFクラウド請求書連携の優先度
- [ ] 顧客側がプロキシ経由を渋った場合のFallback（SDK injection方式）
