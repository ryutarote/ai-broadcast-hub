# Aegis インフラ詳細設計

**ステータス**: Draft v0.1

## 構成

| ファイル / ディレクトリ | 内容 |
|---|---|
| [aws-architecture.md](./aws-architecture.md) | AWSアーキテクチャ詳細書（VPC・ECS・RDS・S3・IAM・WAF・観測） |
| [cost-estimate.md](./cost-estimate.md) | MVP / v1 / v2 のコスト試算、ユニットエコノミクス、損益分岐 |
| [terraform/](./terraform/) | Terraform スケルトン（modules/, envs/staging/, envs/prod/） |

## 要点

- **東京リージョン**プライマリ、大阪は v1+ で DR 候補
- **ECS Fargate**ベース（EKS は採用しない）、Spot で Worker コスト削減
- **Aurora PostgreSQL Serverless v2**（0.5-8 ACU）でメタデータ管理
- **ClickHouse**はMVPは自前ECS、v1で Cloud 移行検討
- **MVP月額 12〜15万円**を想定。**損益分岐は Standard 12社**
- すべて Terraform で IaC、GitHub Actions OIDC でデプロイ

## デプロイ順序の要約

1. `network` モジュール
2. `security` モジュール（KMS・IAM・WAF）
3. `data` モジュール（RDS・Redis・S3）
4. `compute` モジュール（ECS）
5. `edge` モジュール（ALB・Route53・ACM）
6. `observability` モジュール（CloudWatch・GuardDuty）

## 関連

- 法務上の AWS リージョン要件は [../legal/privacy-policy.md](../legal/privacy-policy.md) を参照
- 取扱データ詳細は [../basic-design.md](../basic-design.md) §3 を参照
- データフローは [../data-flow.md](../data-flow.md) を参照
