# マスキングポリシー設計

**ステータス**: Draft v0.1

ポリシーは「テナント別」と「グローバルデフォルト」の2層で管理。

---

## 1. 設定モデル

```yaml
default:
  min_score: 0.4
  fail_open: false
  entities:
    JP_MY_NUMBER:       { action: block }
    JP_CORPORATE_NUMBER: { action: replace }
    JP_DRIVERS_LICENSE: { action: block }
    JP_HEALTH_INSURANCE: { action: block }
    JP_BANK_ACCOUNT:    { action: replace }
    JP_ADDRESS:         { action: replace }
    JP_PHONE_NUMBER:    { action: mask, keep_chars: 4 }
    JP_POSTAL_CODE:     { action: mask, keep_chars: 0 }
    JP_PERSON_NAME:     { action: replace }
    JP_WAREKI_DATE:     { action: replace }
    EMAIL_ADDRESS:      { action: mask, keep_chars: 2 }
    CREDIT_CARD:        { action: block }
    IP_ADDRESS:         { action: tag_only }

tenants:
  acme_corp:
    overrides:
      JP_PHONE_NUMBER: { action: pass }  # 電話番号は通す
      JP_ADDRESS: { action: hash }       # ハッシュで同一性のみ保つ
```

---

## 2. アクション説明

| Action | 効果 | LLMへの送信 | 監査ログ |
|---|---|---|---|
| `pass` | 何もしない | 元のまま | 元のまま |
| `tag_only` | 検出のみ、本文無変更 | 元のまま | タグ付き |
| `mask` | 部分マスク（`****-1234`） | マスク済み | マスク済み |
| `replace` | プレースホルダ置換（`<JP_MY_NUMBER>`） | プレースホルダ | プレースホルダ |
| `hash` | 決定的ハッシュ（同一値→同一ハッシュ） | `<HASH:abc123>` | `<HASH:abc123>` |
| `block` | リクエスト拒絶（HTTP 451） | 送信されない | エラー記録 |

---

## 3. 推奨デフォルト方針

機密度を 3 段階に分類：

### 機密度 S（送信禁止デフォルト）
`block` 推奨。誤検知の方が事故より安全。

- マイナンバー
- 運転免許証
- 健康保険証
- クレジットカード
- パスポート番号（v1.1）

### 機密度 A（プレースホルダ置換）
`replace` 推奨。コンテキストを完全に消す。

- 個人名（JP_PERSON_NAME）
- 住所
- 生年月日（和暦）

### 機密度 B（部分マスク）
`mask` 推奨。コンテキストは維持。

- 電話番号（末4桁残す）
- メールアドレス（先頭2文字残す）
- 法人番号

### 機密度 C（タグ付け）
`tag_only` または `pass`。

- 郵便番号
- IPアドレス

---

## 4. テナント別オーバーライドの判断基準

### 4.1 「pass」を許容する条件

以下のすべてを満たすテナントに限り、特定エンティティを通過可能：

- 利用規約上、自社で個人情報の処理委託先として整理されている
- LLM プロバイダとの間で DPA 締結済み
- データ最小化原則に対する社内ポリシーが明文化
- 法務担当者の承認サイン入りオーバーライド申請

### 4.2 「hash」が有用な場面

- マーケティング分析：同じ顧客の発話を集計したいが、本人特定はしたくない
- セッション分析：話者単位の発話集約
- 監査：同じデータが何度送信されたか集計

---

## 5. 監査要件

| 項目 | 内容 |
|---|---|
| ポリシー変更ログ | who/when/before/after を不可変ログに記録 |
| 例外オーバーライド | 申請者・承認者・期限・理由を必須項目化 |
| 月次レビュー | テナント別のポリシー一覧を月次レポートに同梱 |
| 顧客側 self-service | 管理画面で現行ポリシーを閲覧、変更は申請式 |

---

## 6. テナントへの提示テンプレ

新規顧客に対しては「推奨パッケージ」をプリセットで提示：

| パッケージ | 想定業界 | 主な差分 |
|---|---|---|
| **Standard** | 一般SaaS | 上記デフォルト |
| **Medical** | 医療・介護 | 健康保険証/患者情報を全block、3省2GL準拠 |
| **Financial** | 金融・FinTech | 口座番号/金額を全block、FISC準拠 |
| **Legal** | 士業 | 個人名/住所を全block、契約書テンプレ語彙を保護 |
| **HR** | 人材・採用 | 個人名はhash、面接書き起こし向け |
| **Permissive** | 開発/検証 | block無し、tag_only中心 |

UIで「業界選択 → プリセット適用 → 細部チューニング」のフローで設定可能にする。

---

## 7. 未決事項

- [ ] ハッシュキーのテナント別ローテーション戦略
- [ ] レスポンスマスキングを request と同じポリシーで行うか別運用か
- [ ] tag_only での「タグ付き本文」の保存先（S3 metadata? 別 column?）
- [ ] バルクオーバーライド機能（管理画面UI）
