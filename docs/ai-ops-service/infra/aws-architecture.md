# AWS アーキテクチャ詳細設計

**ステータス**: Draft v0.1
**対象環境**: prod (Tokyo) / staging (Tokyo)
**作成日**: 2026-05-14

---

## 1. アカウント構成

### 1.1 マルチアカウント戦略

```
Aegis AWS Organization
├── Management (root)             # 請求・SSO・Organizations 管理のみ
├── Security                      # GuardDuty・Security Hub 集約
├── Logs                          # CloudTrail / VPC Flow Logs 集約
├── Prod                          # 本番ワークロード
├── Staging                       # ステージング
└── Sandbox                       # 開発者個別検証
```

MVP段階は **Prod + Staging の2アカウント**から開始。顧客数が増えたら Organizations へ移行。

### 1.2 共通設定

- **リージョン**: ap-northeast-1（東京、プライマリ）/ ap-northeast-3（大阪、DR候補）
- **IAM Identity Center**（旧SSO）でアカウント間ログイン統一
- **CloudTrail**：全アカウント・全リージョンで有効、S3集中保管
- **AWS Config**：本番アカウントで有効、変更履歴の取得
- **GuardDuty**：全アカウントで有効

---

## 2. ネットワーク設計（VPC）

### 2.1 VPC レイアウト（本番アカウント）

```
VPC: aegis-prod (10.0.0.0/16)
├── Public Subnets   (ALB / NAT GW 用)
│   ├── 10.0.0.0/24  (ap-northeast-1a)
│   ├── 10.0.1.0/24  (ap-northeast-1c)
│   └── 10.0.2.0/24  (ap-northeast-1d)
├── Private App Subnets   (ECS / Lambda)
│   ├── 10.0.10.0/24 (ap-northeast-1a)
│   ├── 10.0.11.0/24 (ap-northeast-1c)
│   └── 10.0.12.0/24 (ap-northeast-1d)
├── Private Data Subnets  (RDS / ClickHouse / Redis)
│   ├── 10.0.20.0/24 (ap-northeast-1a)
│   ├── 10.0.21.0/24 (ap-northeast-1c)
│   └── 10.0.22.0/24 (ap-northeast-1d)
└── Egress Subnets (NAT Gateway 配置先)
    ├── 10.0.30.0/24 (ap-northeast-1a)
    └── 10.0.31.0/24 (ap-northeast-1c)
```

### 2.2 NAT Gateway 戦略

| フェーズ | 構成 | 月額（参考） |
|---|---|---|
| MVP | NAT Gateway 1台（1a） | 約7,500円 |
| v1 | NAT Gateway 2台（1a/1c） | 約15,000円 |
| v2 | VPC Endpoint 拡充 + NAT 2台 | 約15,000円 |

**コスト最適化**：S3/ECR/Secrets Manager 等の VPC Endpoint を有効化し、NAT Gateway 通信量を減らす（重要）。

### 2.3 アウトバウンド許可ドメイン

LLMプロバイダAPIのみ許可リスト：

| プロバイダ | エンドポイント |
|---|---|
| Anthropic | `api.anthropic.com` |
| OpenAI | `api.openai.com` |
| AWS Bedrock | `bedrock-runtime.*.amazonaws.com`（VPC Endpoint） |
| Google Vertex | `*.googleapis.com` |
| Azure OpenAI | `*.openai.azure.com` |

NAT 経由のアウトバウンドは AWS Network Firewall または Squid Proxy + 許可リストで制限する（v1で導入推奨）。

---

## 3. コンピュート（ECS Fargate）

### 3.1 クラスタ構成

`aegis-prod` 単一クラスタに以下のサービスをデプロイ：

| サービス名 | 役割 | タスク数 | スペック | スケール戦略 |
|---|---|---|---|---|
| `litellm-proxy` | LLMプロキシ | 2〜10 | 1 vCPU / 2 GB | CPU 70% / req/s |
| `control-plane` | 管理API + Web | 2〜4 | 0.5 vCPU / 1 GB | CPU 60% |
| `langfuse-web` | 観測UI | 2 | 1 vCPU / 2 GB | 固定 |
| `langfuse-worker` | 観測ingest | 2〜6 | 1 vCPU / 2 GB | キュー長 |
| `aegis-worker` | レポート/Eval | 1〜4 | 0.5 vCPU / 1 GB | キュー長 |
| `clickhouse` | イベントDB | 1 | 2 vCPU / 8 GB | 固定 |

### 3.2 タスク定義のポイント

- **Fargate Spot** を `*-worker` で利用してコスト半減
- `litellm-proxy` `control-plane` は **Fargate (On-Demand)** で安定性確保
- `clickhouse` は **EBS バックEFS or EBS Volume**（永続化）。データロストリスク回避のため EBS gp3 を ECS task に attach
- すべてのタスクは **awsvpc network mode**、private subnetに配置

### 3.3 オートスケーリング

- Target Tracking で CPU/メモリ/カスタムメトリクス（req/s, queue length）
- Cooldown 60秒、Scale-in 5分

### 3.4 デプロイ戦略

- **Blue/Green**（ECS CodeDeploy 連携）
- ヘルスチェック失敗時自動ロールバック
- カナリア 10% → 50% → 100%

---

## 4. データ層

### 4.1 RDS Aurora PostgreSQL Serverless v2

| 項目 | 値 |
|---|---|
| エンジン | Aurora PostgreSQL 16.x |
| 構成 | Multi-AZ (1 writer + 1 reader) |
| 容量 | Serverless v2 (0.5 - 8 ACU) |
| バックアップ | 自動、保持14日、PITR有効 |
| 暗号化 | KMS Customer Managed Key |
| パラメータ | `rds.force_ssl=1`, `log_statement=ddl` |
| Performance Insights | 有効 |

### 4.2 ClickHouse

#### MVP（自前ECS運用）
- 単一ノード、ECS Task に EBS gp3 100GB attach
- データ：パーティション月次、TTL 90/180/365日（プラン別）
- バックアップ：日次 `clickhouse-backup` で S3 へ

#### v1〜（移行候補）
- **ClickHouse Cloud（東京リージョン）** へ移行検討
- メリット：運用負荷削減、自動スケール、レプリケーション標準
- デメリット：コスト上昇（最低 $200/月 程度）、第三者データ取扱

### 4.3 ElastiCache Redis

| 項目 | 値 |
|---|---|
| エンジン | Redis 7.x（OSS版） |
| ノードタイプ | MVP: `cache.t4g.micro` / v1: `cache.t4g.small` |
| Multi-AZ | v1で有効化 |
| AUTH | 有効 |
| 暗号化 | 通信時・保管時とも有効 |
| 用途 | LiteLLMキャッシュ、レート制限、Celeryブローカー |

### 4.4 S3バケット設計

| バケット | 用途 | 暗号化 | バージョニング | ライフサイクル |
|---|---|---|---|---|
| `aegis-prod-audit-{account}` | リクエスト/レスポンス本文 | KMS CMK | 有効 | 30→IA→Glacier、保持期間でDelete |
| `aegis-prod-reports-{account}` | 月次PDFレポート | KMS CMK | 有効 | 無期限保持 |
| `aegis-prod-backups-{account}` | DBバックアップ | KMS CMK | 有効 | 30日後Glacier |
| `aegis-prod-terraform-state-{account}` | TF state | KMS CMK | 有効 | バージョン1年保持 |
| `aegis-prod-logs-{account}` | アクセスログ・VPC Flow | KMS CMK | 有効 | 90日後Glacier |

すべて **Block Public Access 有効**、**バケットポリシーで CloudTrail 集約アカウント以外からの List/Get 拒否**。

---

## 5. セキュリティ層

### 5.1 KMS Key 設計

| Key Alias | 用途 | ローテーション |
|---|---|---|
| `alias/aegis-prod-rds` | RDS暗号化 | 自動 |
| `alias/aegis-prod-s3` | S3バケット暗号化 | 自動 |
| `alias/aegis-prod-secrets` | Secrets Manager暗号化 | 自動 |
| `alias/aegis-prod-ebs` | ECSタスクのEBS | 自動 |
| `alias/aegis-prod-customer-payload` | **顧客ペイロード（特に機密）専用** | 自動 |

顧客ペイロード用キーは**バウンダリ KMS Policy** で `iam:Role/aegis-llm-proxy` のみ Decrypt 許可。

### 5.2 Secrets Manager

階層：

```
/aegis/prod/litellm/master           # LiteLLM管理者キー
/aegis/prod/langfuse/db              # Langfuse DB資格情報
/aegis/prod/db/main                  # メインDB資格情報
/aegis/prod/tenants/{tenant_id}/anthropic   # 顧客のAnthropic API key
/aegis/prod/tenants/{tenant_id}/openai
/aegis/prod/tenants/{tenant_id}/bedrock     # IAM Role ARN（顧客アカウント）
/aegis/prod/tenants/{tenant_id}/azure
```

**自動ローテーション**：
- DB資格情報は90日ごと自動ローテーション
- 顧客APIキーは顧客側ローテーションをUIで促す

### 5.3 IAM Role 設計

主要ロール（最小権限）：

| ロール | 主な権限 |
|---|---|
| `aegis-litellm-proxy-task` | `/aegis/prod/tenants/*` の Read のみ、KMS Decrypt（顧客ペイロード Key） |
| `aegis-control-plane-task` | RDS 接続、Secrets Manager 限定、S3 reports Read/Write |
| `aegis-worker-task` | ClickHouse 接続、S3 audit Read、reports Write |
| `aegis-langfuse-task` | RDS 接続（Langfuse専用DB） |
| `aegis-deploy-github` | OIDC 連携、ECR Push、ECS Deploy |
| `aegis-readonly-support` | CloudWatch Logs / X-Ray 参照のみ |
| `aegis-break-glass` | フル権限、MFA + Slack通知必須、Tickets参照のみ起動 |

### 5.4 WAF / Shield

- **AWS WAFv2** を CloudFront と ALB 両方に適用
- AWS マネージドルール：`Core rule set`, `Known bad inputs`, `IP reputation`, `SQLi`, `XSS`
- カスタムルール：
  - レート制限：5,000 req/5min/IP
  - 認証エンドポイント：100 req/min/IP
- **AWS Shield Standard**（無料）有効
- **Shield Advanced** は v2 で検討（年間 $3,000/月）

### 5.5 GuardDuty / Security Hub

- GuardDuty 有効化、Findings は Security アカウントに集約
- Security Hub で AWS基本ベストプラクティス、CIS、PCI のフレームワークモニタ
- 重大 Findings は SNS → Slack へ自動通知

---

## 6. エッジ・配信層

### 6.1 Route 53

| ドメイン | 用途 |
|---|---|
| `aegis.jp` | コーポレートサイト |
| `app.aegis.jp` | 管理画面（CloudFront） |
| `gw.aegis.jp` | プロキシエンドポイント（ALB直 or CloudFront） |
| `api.aegis.jp` | Control Plane API |
| `status.aegis.jp` | ステータスページ（外部SaaS） |

- ヘルスチェック + フェイルオーバールーティング
- DNSSEC 有効化（v1）

### 6.2 CloudFront

- 管理画面・コーポレートサイトに利用
- WAF アタッチ
- Origin: ALB（プライベート、Origin Access Identity / Custom Header）
- TLS: ACM 証明書 (us-east-1 必須)

### 6.3 ALB

- `gw.aegis.jp` 用：プロキシ層（ECS LiteLLM）
- `api.aegis.jp` 用：API + 管理画面（ECS Control Plane）
- TLS: ACM 証明書（ap-northeast-1）
- WAF アタッチ
- アクセスログ → S3 logs バケット

### 6.4 ACM 証明書

- `*.aegis.jp` 用（DNS検証、自動更新）
- 東京・バージニア（CloudFront用）両方発行

---

## 7. 観測・監視

### 7.1 CloudWatch

| 内容 | 設定 |
|---|---|
| アプリログ | 全 ECS タスクの stdout/stderr を Log Group へ。保持30日（コスト最適化のため Firehose 経由で S3 long-term） |
| メトリクス | デフォルト + カスタム（req/s, queue length） |
| アラーム | 重要メトリクス10〜20項目を SNS → Slack |
| Synthetics | gw.aegis.jp の死活監視（1分間隔） |

### 7.2 Prometheus + Grafana（社内監視）

- AWS Managed Prometheus（AMP）or 自前 Prometheus on ECS
- Grafana は ECS（AGPL注意、社内のみアクセス）
- ダッシュボード：
  - System Overview（全テナント横断）
  - Tenant View（テナント別ドリルダウン）
  - Cost Tracking
  - SLO Burn Rate

### 7.3 分散トレーシング

- AWS X-Ray または OpenTelemetry → Langfuse
- LLM呼出のレイテンシ・エラーをエンドツーエンドで追跡

### 7.4 アラート配信

- SNS Topic：`aegis-prod-alerts-critical` / `aegis-prod-alerts-warn`
- Subscriber：Slack（自社）、Pagerduty / Better Stack
- 顧客向けアラートは Control Plane の Alert Engine から個別配信

---

## 8. CI/CD

### 8.1 GitHub Actions

ブランチ戦略：
- `main` → prod 自動デプロイ（タグリリース時）
- `develop` → staging 自動デプロイ
- PR → lint, test, security scan のみ

OIDC連携：
- AWS IAM Role に GitHub Actions OIDC Provider 経由でAssumeRole
- 長期 Access Key を保持しない

ステップ概要：
```
1. Setup (Python/Node)
2. Lint (ruff, eslint, terraform fmt)
3. Test (pytest, vitest)
4. Security (Snyk, Trivy, gitleaks, FOSSA)
5. Build & Push to ECR
6. Terraform Plan (PR)
7. Terraform Apply (merge to main)
8. ECS Service Update (Blue/Green)
9. Smoke Test
10. Rollback on failure
```

### 8.2 デプロイ承認

- 本番デプロイは GitHub Environment Protection Rule で `1 reviewer approval` 必須
- インフラ変更は Terraform Plan を PR レビューで確認

---

## 9. 災害復旧 (DR)

### 9.1 RTO / RPO

| データ種別 | RTO | RPO |
|---|---|---|
| PostgreSQL | 4 hours | 5 min（PITR） |
| ClickHouse | 4 hours | 1 day（日次バックアップ） |
| S3 | 即時 | 0（複数AZ標準） |
| Secrets | 即時 | 0（Multi-AZ標準） |

### 9.2 DR シナリオ

| シナリオ | 対応 |
|---|---|
| 単一AZ障害 | Multi-AZ構成で自動切替（手動操作不要） |
| 東京リージョン全体障害 | S3 Cross-Region Replication（大阪）から手動復旧、RTO 4-24時間 |
| データ破壊（操作ミス） | PITR で5分前まで巻き戻し |
| ランサムウェア | S3 Object Lock（v1）+ KMS Key Policy で破壊耐性 |

### 9.3 DR 訓練

- 四半期に1回、Game Day 実施（Chaos Engineering）

---

## 10. ガバナンス・コスト管理

### 10.1 タグ戦略

全リソースに付与：
```
Project    = aegis
Env        = prod | staging | sandbox
Owner      = engineering
CostCenter = ai-ops
Tier       = critical | normal | dev
```

### 10.2 Cost Allocation

- Cost Explorer で Tag-based 集計
- Budget Alarm：月額予算の80% / 100% / 120% で通知
- Reserved Instance / Savings Plans：v1 で1年コミット検討

### 10.3 リソース命名規則

```
aegis-{env}-{component}-{resource_type}-{purpose}
例: aegis-prod-litellm-ecs-service
    aegis-prod-control-rds-cluster
    aegis-prod-audit-s3-bucket
```

---

## 11. 環境差分（prod / staging）

| 項目 | Prod | Staging |
|---|---|---|
| Multi-AZ | 全コンポーネント | App層のみ（DB Single-AZ） |
| Aurora | Serverless v2 (0.5-8 ACU) | Serverless v2 (0.5-1 ACU) |
| NAT GW | 2台 | 1台 |
| WAF | 全機能 | 最小ルール |
| Backup | 14日PITR | 7日PITR |
| ログ保持 | 30日（CW） + S3永続 | 7日 |
| 監視 | フル | 最小 |
| データ | 本番 | 匿名化済みサブセット |

---

## 12. 採用しない（または将来検討）技術

| 技術 | 理由 |
|---|---|
| Kubernetes (EKS) | ECS Fargateで十分、運用工数が小さい |
| Lambda | 長時間プロキシ・Server-Sent Events に不向き |
| DynamoDB | リレーショナルな顧客管理にはPGの方が適する |
| Aurora Global Database | コストに対し効果が薄い、東京＋大阪のCRRで十分 |
| Bedrock Knowledge Base | 顧客のLLM呼出を中継するのが本業、自社RAGは不要 |
| AWS Direct Connect | SMB顧客は使わない |

---

## 13. オープン課題

- [ ] ClickHouse: 自前運用 vs ClickHouse Cloud の最終判断（コスト・運用工数）
- [ ] Network Firewall vs Squid Proxy + ALB の選定
- [ ] Shield Advanced 加入タイミング
- [ ] Aurora I/O-Optimized への切替（高IO時のコスト最適化）
- [ ] FedRAMP / ISMAP を視野に入れる場合の AWS GovCloud 検討（先の話）
