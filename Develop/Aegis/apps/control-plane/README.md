# Aegis Control Plane (MVP)

FastAPI + SQLite + バニラJS UI で動く、Aegis のコアバックエンド。

## 起動

```bash
cd Develop/Aegis/apps/control-plane
export AEGIS_ADMIN_TOKEN=dev-admin-token
export AEGIS_DATABASE_URL=sqlite:///./aegis_dev.db

PYTHONPATH=src python -m uvicorn aegis.main:app --host 0.0.0.0 --port 8000 --reload
```

ブラウザで http://localhost:8000/ を開くと管理UIが見える。

## 主なエンドポイント

### 管理 API（`X-Admin-Token` 必須）

| Method | Path | 用途 |
|---|---|---|
| POST | `/api/tenants` | テナント作成 |
| GET | `/api/tenants` | テナント一覧 |
| GET | `/api/tenants/{id}` | テナント取得 |
| PATCH | `/api/tenants/{id}` | テナント更新 |
| DELETE | `/api/tenants/{id}` | テナント削除 |
| POST | `/api/tenants/{id}/api-keys` | APIキー発行 |
| GET | `/api/tenants/{id}/api-keys` | APIキー一覧 |
| DELETE | `/api/tenants/{id}/api-keys/{kid}` | APIキー失効 |

### テナント API（`Authorization: Bearer <api_key>` 必須）

| Method | Path | 用途 |
|---|---|---|
| POST | `/api/events` | LLMイベント送信（プロキシ模擬） |
| GET | `/api/usage` | 利用サマリー |
| GET | `/api/costs` | コスト集計 + 予算消費率 |
| GET | `/api/alerts` | アラート履歴 |

### 共通

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/health` | ヘルスチェック |
| GET | `/` | 管理UI |

## アラート発火条件（MVP）

| 条件 | 種別 | 重大度 |
|---|---|---|
| `pii_detected=true` のイベント受信 | `pii_detected` | warn |
| 日次予算 80% 超 | `cost_threshold_80` | warn |
| 日次予算 100% 超 | `cost_threshold_100` | critical |
| `status_code >= 500` | `provider_5xx` | warn |

同一種別は 1 時間以内の重複発火を抑止。

## 環境変数

| 名前 | 既定値 | 説明 |
|---|---|---|
| `AEGIS_DATABASE_URL` | `sqlite:///./aegis_dev.db` | SQLAlchemy DSN |
| `AEGIS_ADMIN_TOKEN` | `dev-admin-token` | `X-Admin-Token` ヘッダ |
