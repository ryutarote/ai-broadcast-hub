# Aegis Terraform スケルトン

**ステータス**: Skeleton v0.1 / **実装前のひな形、Terraform validate は通る前提だが実適用前に各 TODO を埋めること**

---

## ディレクトリ構成

```
terraform/
├── README.md                ← 本ファイル
├── versions.tf              ← Terraform / Provider バージョン固定
├── providers.tf             ← AWS Provider 設定
├── backend.tf.example       ← S3 + DynamoDB バックエンドの設定例
├── modules/
│   ├── network/             ← VPC, Subnet, NAT, VPC Endpoint
│   ├── security/            ← KMS, Secrets Manager, IAM, WAF
│   ├── data/                ← RDS Aurora, ElastiCache, S3
│   ├── compute/             ← ECS Cluster, Services, Task Definitions
│   ├── edge/                ← CloudFront, ALB, Route53, ACM
│   └── observability/       ← CloudWatch, SNS, GuardDuty
└── envs/
    ├── staging/
    │   ├── main.tf          ← Staging のルートモジュール
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── terraform.tfvars.example
    └── prod/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── terraform.tfvars.example
```

---

## はじめに

このスケルトンは **AWSアーキテクチャ詳細書（../aws-architecture.md）** を Terraform で表現したものです。MVP 構築の出発点として使い、リソース ARN や追加設定は実装時に埋めてください。

---

## 前提条件

- Terraform >= 1.7
- AWS CLI v2
- AWS アカウントへの SSO ログイン（IAM Identity Center）または Access Key
- S3 バケットと DynamoDB テーブル（Remote State 用、別途手動作成 or bootstrap モジュール）

---

## 初期化手順

### 1. Remote State Bucket / DynamoDB Table の作成（手動 or bootstrap）

```bash
aws s3api create-bucket \
  --bucket aegis-tfstate-prod-{account_id} \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1

aws s3api put-bucket-versioning \
  --bucket aegis-tfstate-prod-{account_id} \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket aegis-tfstate-prod-{account_id} \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'

aws dynamodb create-table \
  --table-name aegis-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-1
```

### 2. backend.tf を作成

`envs/{env}/backend.tf` を `backend.tf.example` から作成し、{account_id} を埋める。

### 3. 初回 plan

```bash
cd envs/staging
terraform init
terraform plan -var-file=terraform.tfvars
```

---

## デプロイ順序

1. `network` — VPC、Subnet、NAT、VPC Endpoint
2. `security` — KMS、IAM、WAF
3. `data` — RDS、ElastiCache、S3
4. `compute` — ECS Cluster、Service、Task Definitions
5. `edge` — ALB、CloudFront、Route53
6. `observability` — CloudWatch、SNS、Alarms

ルートモジュール `envs/{env}/main.tf` で依存関係を表現済み。

---

## モジュール命名規則

- 入力変数：`var.{module}_{purpose}` または分かりやすい名前
- 出力：他モジュールから参照されるものは必ず `output` で公開
- タグ：全リソースに `local.common_tags` を merge

---

## TODO（実装時に埋めるべきプレースホルダ）

| ファイル | TODO |
|---|---|
| `providers.tf` | `account_id`、profile 名 |
| `modules/network/main.tf` | CIDR 確定、AZ 確定 |
| `modules/data/main.tf` | RDS マスターパスワード生成方法（Secrets Manager 連携） |
| `modules/compute/main.tf` | コンテナイメージ URI（ECR repository を別途作成） |
| `modules/edge/main.tf` | ドメイン aegis.jp の取得後に Route53 ホストゾーン ID 紐付け |
| `modules/security/main.tf` | OIDC Provider thumbprint（GitHub） |
| `envs/{env}/terraform.tfvars` | 環境固有値 |

---

## 安全装置

- `prevent_destroy = true` を設定するリソース：RDS、S3 バケット、KMS Key
- `lifecycle.ignore_changes`：ECS Task Definition の image（CI で更新するため）
- 本番 apply は GitHub Actions の Environment Protection で `1 reviewer approval` 必須

---

## コスト想定

`../cost-estimate.md` を参照。MVP 構築時で 月 12〜15 万円程度を想定。

---

## 参考

- AWS Well-Architected Framework
- AWS Security Reference Architecture (SRA)
- Terraform AWS Provider Documentation
