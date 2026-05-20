# OSSライセンス・コンプライアンス方針

**ステータス**: Draft v0.1 / **要弁護士レビュー**
**作成日**: 2026-05-14
**対象**: Aegis Managed AI Operations Platform

---

## 0. 重要な前提と免責

- 本文書はサービスを開発・運営する**社内の方針整理**であり、弁護士の法律意見書ではない。
- AGPL-3.0およびLGPL/MIT/Apacheの各ライセンス解釈は判例が少なく、特に「SaaSとしての提供」の扱いに**未確定領域**がある。
- 必ず**SaaS/OSSライセンスに通じた弁護士**（候補：TMI総合法律事務所、シティユーワ、TheCorporateLawyer等のIT特化部門）のレビューを受ける。
- 海外OSSプロジェクトとの**直接の商用ライセンス契約**は英文で締結されるため、英文契約のレビュー経験のある法律事務所が望ましい。

---

## 1. 利用OSS一覧と分類

### 1.1 MVPで利用するOSS

| OSS | バージョン | ライセンス | 利用形態 | 改変有無 | 配布有無 |
|---|---|---|---|---|---|
| **LiteLLM** | 1.x（最新stable） | **MIT** | プロキシ層として自社環境で実行 | 設定ファイルのみ、ソース改変なし | なし（SaaS提供のみ） |
| **Langfuse** | 2.x（OSS Core） | **MIT** | 観測バックエンドとして自社環境で実行 | 改変なし | なし |
| **PostgreSQL** | 16 | **PostgreSQL License**（BSD-like） | DBエンジン | なし | なし |
| **ClickHouse** | 24.x | **Apache-2.0** | イベントストア | なし | なし |
| **Redis** | 7（OSS版） | **RSAL/SSPL注意** | キャッシュ | なし | なし |
| **Presidio** | 2.x | **MIT** | PII検知 | カスタム認識子（日本語）を追加予定 | なし |
| **Promptfoo** | 0.x | **MIT** | Eval実行 | 設定ファイルのみ | なし |
| **FastAPI** | 0.11x | **MIT** | Webフレームワーク | なし | なし |
| **Next.js** | 15 | **MIT** | フロントエンド | なし | クライアント配信 |
| **WeasyPrint** | 65.x | **BSD-3-Clause** | PDF生成 | なし | なし |
| **Celery** | 5.x | **BSD-3-Clause** | ジョブキュー | なし | なし |
| **Terraform** | 1.x | **BUSL-1.1**（注意） | IaC（社内利用） | なし | なし |
| **Grafana** | 10.x（OSS版は11以前確認） | **AGPL-3.0** | 内部監視ダッシュボード | なし | なし |
| **Prometheus** | 2.x | **Apache-2.0** | メトリクス収集 | なし | なし |

### 1.2 ライセンスごとの義務概要

| ライセンス | 主な義務 | SaaS提供時の影響 |
|---|---|---|
| **MIT** | 著作権表示・ライセンス文の維持 | 影響なし。改変・組込・SaaS提供すべて自由 |
| **Apache-2.0** | 同上 + 変更通知 + 特許条項 | 影響なし |
| **BSD-3-Clause** | 著作権表示・ライセンス文の維持・推奨文言禁止 | 影響なし |
| **PostgreSQL License** | 著作権表示の維持 | 影響なし |
| **AGPL-3.0** | ネットワーク経由で利用させる場合、**ユーザーにソースコード開示義務** | **要注意**（詳細§2） |
| **BUSL-1.1**（Terraform） | 競合SaaSとしての提供禁止、4年後にApache-2.0化 | 社内利用のみなら影響なし |
| **SSPL** / **RSAL**（Redis 7.4以降） | DBaaSとして提供する場合に制約 | キャッシュとしての社内利用は影響なし（要確認） |
| **Elastic License v2** | 「アズアサービス」提供禁止 | 該当OSSなしの想定 |

---

## 2. AGPL-3.0 リスクの分析（最重要）

### 2.1 AGPL-3.0 第13条の要点

> "Notwithstanding any other provision of this License, **if you modify the Program, your modified version must prominently offer all users interacting with it remotely through a computer network ... an opportunity to receive the Corresponding Source** of your version..."

要約：**AGPLライセンスのソフトウェアを改変し、ネットワーク経由でユーザーに利用させる場合、ユーザーにソースコードを提供する義務が発生する**。

### 2.2 MVPでのAGPL対象

MVPの構成で**AGPLライセンスのソフトウェアは Grafana のみ**（社内オペレーター用の監視ダッシュボード）。

- **Langfuse は MIT** （Core部分。EE機能のみ別ライセンス。後述）
- **LiteLLM は MIT**
- **Grafana は社内利用のみ**（顧客には公開しない）。AGPLの「ユーザーに利用させる」に**顧客は該当しない**と整理。

→ **MVPはAGPL義務をほぼ回避できる構成**。ただし以下を遵守：

1. Grafanaを社内ネットワーク内に閉じ、顧客の認証ユーザーに直接公開しない
2. Grafanaのソースは改変しない
3. 万一改変した場合、改変箇所のソースを公開する用意（GitHub privateでも開示要求時に提供可能な体制）

### 2.3 Langfuse のライセンス構造（要慎重確認）

Langfuseは**dual license**を採用している期間があり、執筆時点（2026-05）の最新リリースを必ず**直接確認**する必要がある。

- **Core**（基本機能）: MIT
- **Enterprise Edition (EE) 機能**: Commercial License（SSO、Fine-grained RBAC、データマスキング、Audit Log等の高度機能）

#### MVPでの判断
- MVPは**Core機能（MIT）のみ**を利用する設計。
- EE機能は使わない。SSOは自社実装（Auth0/Cognito）でカバー。
- v1で Audit Log 高度版が必要になった場合のみ、Langfuse社と商用契約を締結。

#### 確認・遵守事項
- [ ] 利用するLangfuseバージョンの `LICENSE` ファイルをコミット時点でアーカイブ保存（バージョン固定）
- [ ] EEディレクトリ（`/ee` または該当）のコードを誤って組み込まない CI チェック
- [ ] バージョンアップ時にライセンス変更を都度確認（OSS→Source-Availableへの変更例：HashiCorp、Elastic、Redis）

### 2.4 もしAGPLを"フォアグラウンドで"使う場合の対策（参考）

将来 Langfuse の AGPL コンポーネント等を組み込む必要が生じた場合の選択肢：

| 選択肢 | 内容 | 推奨度 |
|---|---|---|
| **A. 商用ライセンス購入** | 本家から商用ライセンスを購入（Langfuse社、Grafana Labs等は提供あり） | ◎ 推奨 |
| **B. プロセス分離** | AGPLソフトを別プロセス・別コンテナで動かし、HTTP APIで結合。"派生著作物"性を弱める | △（法的判断は弁護士に） |
| **C. ソース開示** | 自社改変部分含めGitHubで公開 | × ビジネス上不可 |
| **D. 代替OSSへ移行** | MIT/Apache系の同等品へ | ○ |
| **E. 自前実装** | 機能を自社開発 | △（コスト次第） |

---

## 3. LiteLLM・Langfuseとの関係整理

### 3.1 LiteLLM（MIT）

- 完全にMITで利用可能
- 商用利用、SaaS提供、改変、再配布すべて自由
- **義務**：ソースコード配布時に LICENSE と Copyright 表示維持（SaaSとしての提供は配布に該当しないと整理）
- **オプション**：LiteLLM Cloud との関係は競合になり得るため、機能模倣（API互換性以外）は避ける

### 3.2 Langfuse Core（MIT）

- 同上、MITで利用可能
- セルフホスト版を自社で運用してSaaS提供OK
- **義務**：Copyright表示維持
- **配慮**：Langfuse Cloudと直接競合する形（汎用観測SaaSとしての提供）は避け、**「日本SMB向けマネージドサービス + 運用代行」**として明確に差別化

### 3.3 リスクヘッジ：商用契約の検討タイミング

| タイミング | 検討内容 |
|---|---|
| MVP〜v1 | OSS範囲のみ。商用契約不要 |
| v1（180日目） | Langfuse Cloud Enterprise / Self-hosted EE のライセンス費用を比較。SOC2取得時に審査負担を減らす目的で契約検討 |
| v2（360日目） | エンタープライズ顧客の要求（SSO、Audit）が出たら商用版へ移行 |

予算目安：Langfuse商用ライセンス 年間 $5,000〜$30,000 程度（規模次第）

---

## 4. 必要な表記・通知

### 4.1 顧客向け「OSS Acknowledgements」ページ

サービス内（管理画面 footer や `/legal/oss-licenses` URL）に**利用OSS一覧と各ライセンス全文へのリンク**を掲載。

最小限の記載例：

```
本サービスは以下のオープンソースソフトウェアを利用しています：

- LiteLLM (MIT License) — Copyright (c) BerriAI
- Langfuse (MIT License) — Copyright (c) Langfuse GmbH
- Presidio (MIT License) — Copyright (c) Microsoft Corporation
- ClickHouse (Apache License 2.0) — Copyright (c) Yandex LLC
- PostgreSQL (PostgreSQL License) — Copyright (c) PostgreSQL Global Development Group
- (... 全OSS)

各ライセンスの全文：https://aegis.jp/legal/oss-licenses
```

### 4.2 ソースコード配布時の義務（該当なしの想定）

- SaaS提供のみのため、エンドユーザーへのバイナリ・ソース配布は発生しない
- 例外：もし顧客向けSDK / Chrome拡張等を将来配布する場合、配布物に含まれるOSSのライセンス・著作権表示を同梱する

---

## 5. CI/CDでの自動チェック

ライセンス遵守を継続するため、以下をCIに組み込む：

| ツール | 目的 |
|---|---|
| **FOSSA** または **Snyk License Compliance** | 依存OSSのライセンス自動検出と方針違反検知 |
| **scancode-toolkit** | コード内のライセンス文ヘッダースキャン |
| **OSS Review Toolkit (ORT)** | 依存ツリー全体の SBOM 生成 |
| **license-checker (npm)** | フロントエンドの依存チェック |
| **pip-licenses (python)** | バックエンド依存チェック |

ポリシー例：
- 許可：MIT / Apache-2.0 / BSD-2/3 / ISC / PostgreSQL
- 要レビュー：AGPL / GPL / LGPL / MPL / EPL / BUSL / SSPL
- 禁止：明示なし、Proprietary、Custom（個別判断）

CIで「要レビュー」「禁止」が検出されたらPR ブロック。

---

## 6. SBOM（ソフトウェア部品表）の整備

- **目的**：脆弱性管理、顧客への透明性、SOC2/ISMS監査対応、PSIRT対応
- **形式**：CycloneDX または SPDX
- **生成**：CI で `syft` を実行し、リリースごとに保管
- **公開**：顧客（特にエンタープライズ）からの要求時に NDA 締結のうえ提供

---

## 7. 商標・ロゴの取扱い

| 項目 | 方針 |
|---|---|
| LiteLLM / Langfuse の名称 | 「使用しています」「ベース」と事実陳述は OK。「公式パートナー」「公認」は禁止 |
| LLMプロバイダ名（Anthropic, OpenAI 等） | 「対応プロバイダ」として記載は OK。ロゴは公式ガイドラインに従う |
| 自社の「Aegis」 | 商標登録の検討（35類：SaaS、42類：ソフトウェア）。商標調査必須 |

商標調査：J-PlatPat で「Aegis」「イージス」「Aegis Cloud」等の先願を確認 → 弁理士依頼（10〜30万円）。

---

## 8. 法務タスクのチェックリスト

### MVP前

- [ ] 弁護士選定（IT/SaaS/OSSに強い事務所、初回相談済み）
- [ ] LiteLLM・Langfuse 利用バージョンの LICENSE ファイル取得・保管
- [ ] OSS Acknowledgements ページの作成
- [ ] CIにライセンスチェック組込（FOSSA / Snyk / scancode）
- [ ] SBOM 生成パイプライン
- [ ] 商標調査（Aegis）
- [ ] AGPL対象（Grafana等）を顧客非公開ネットワーク内に閉じる構成確認

### v1（180日）まで

- [ ] Langfuse EE / 商用版の必要性判断（必要なら契約締結）
- [ ] 商標出願
- [ ] 弁護士による OSS Compliance 全体レビュー
- [ ] 顧客向けSBOM開示ポリシー策定

### v2（360日）まで

- [ ] SOC2 Type 1 取得時のOSS監査対応
- [ ] 海外展開を視野に入れた場合の各国ライセンス整合性確認

---

## 9. 想定リスクと残課題

| リスク | 評価 | 対応 |
|---|---|---|
| LangfuseのライセンスがAGPL/SSPL等に変更される | 中 | バージョン固定運用、四半期ごとに確認、代替OSS（Helicone等）の評価並走 |
| LiteLLMが類似変更 | 低 | 同上 |
| 顧客が「ソースコード開示」を要求 | 低〜中 | 利用規約で開示義務なき旨明記、ただしSBOM/監査資料は NDA 下で提供 |
| 海外OSSコミュニティとの関係悪化（パッチを当てた等） | 低 | アップストリームへ可能な範囲でcontribution、依存度を分散 |
| 商標係争 | 低〜中 | サービス名は商標調査済みで決定 |

---

## 10. 結論（経営判断）

1. **MVP〜v1までは MIT/Apache 範囲で完全に組成可能**。AGPLの実質的影響なし。
2. **Langfuseのライセンスをバージョンごとに確認**することが最重要。CIで自動化。
3. 商標は**サービス名確定前**に弁理士相談。
4. 弁護士相談は**ローンチ前に必ず1回**実施し、本文書をレビューしてもらう。費用 30〜80万円目安。
