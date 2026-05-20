# LiteLLM 統合ガイド

**ステータス**: Draft v0.1

LiteLLMのカスタムフックを通じて、リクエスト前後でPIIスキャンを行う。

---

## 1. フックポイント

LiteLLM Proxy では以下のフックを使う：

| フック | タイミング | 用途 |
|---|---|---|
| `async_pre_call_hook` | LLM呼出前 | リクエスト本文のPIIスキャン → マスク or block |
| `async_post_call_success_hook` | LLM呼出後（成功） | レスポンス本文のPIIスキャン → マスク |
| `async_post_call_failure_hook` | LLM呼出後（失敗） | エラー時の監査ログ |

---

## 2. カスタムフック実装例

`aegis_litellm_hooks.py`:

```python
"""LiteLLM custom hooks for Aegis PII scanning."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.proxy_server import DualCache

from aegis_pii_jp.recognizers.scanner import (
    PIIScanner,
    TenantPolicy,
    Action,
    EntityPolicy,
)
from aegis_pii_jp.recognizers.normalize import normalize_for_pii

from aegis.policy_loader import load_tenant_policy  # 自社実装
from aegis.metrics import (
    pii_scan_duration,
    pii_entities_detected,
    pii_actions_total,
    pii_blocked_requests,
)


logger = logging.getLogger("aegis.litellm.hooks")


class AegisPIIHook(CustomLogger):
    """Pre/Post call hooks that run Aegis PII scanning."""

    def __init__(self) -> None:
        self._scanner: PIIScanner | None = None

    def _scanner_lazy(self) -> PIIScanner:
        if self._scanner is None:
            default = TenantPolicy(
                entities={
                    "JP_MY_NUMBER": EntityPolicy(action=Action.BLOCK),
                    "JP_DRIVERS_LICENSE": EntityPolicy(action=Action.BLOCK),
                    "JP_HEALTH_INSURANCE": EntityPolicy(action=Action.BLOCK),
                    "CREDIT_CARD": EntityPolicy(action=Action.BLOCK),
                    "JP_PERSON_NAME": EntityPolicy(action=Action.REPLACE),
                    "JP_ADDRESS": EntityPolicy(action=Action.REPLACE),
                    "JP_PHONE_NUMBER": EntityPolicy(action=Action.MASK, keep_chars=4),
                    "EMAIL_ADDRESS": EntityPolicy(action=Action.MASK, keep_chars=2),
                },
                min_score=0.4,
                fail_open=False,
            )
            self._scanner = PIIScanner(default_policy=default)
        return self._scanner

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        tenant_id = user_api_key_dict.metadata.get("tenant_id")
        if not tenant_id:
            raise HTTPException(401, "tenant_id missing")

        policy = await load_tenant_policy(tenant_id)
        scanner = self._scanner_lazy()

        messages = data.get("messages") or []
        masked_messages = []
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str) or not content:
                masked_messages.append(msg)
                continue

            normalized = normalize_for_pii(content)
            with pii_scan_duration.labels(stage="request").time():
                result = scanner.scan(normalized, tenant_policy=policy)

            for ent, cnt in result.actions_applied.items():
                pii_entities_detected.labels(entity=ent, tenant=tenant_id).inc(cnt)

            if result.blocked:
                pii_blocked_requests.labels(tenant=tenant_id).inc()
                logger.warning("PII block: tenant=%s actions=%s", tenant_id, result.actions_applied)
                raise HTTPException(
                    status_code=451,
                    detail={
                        "error": "request_blocked_by_pii_policy",
                        "blocked_entities": list(result.actions_applied.keys()),
                    },
                )

            masked_messages.append({**msg, "content": result.masked_text})

        data["messages"] = masked_messages
        return data

    async def async_post_call_success_hook(
        self,
        data: dict[str, Any],
        user_api_key_dict: UserAPIKeyAuth,
        response: Any,
    ) -> None:
        """Scan the response for PII; replace inline if found."""
        tenant_id = user_api_key_dict.metadata.get("tenant_id")
        if not tenant_id:
            return
        policy = await load_tenant_policy(tenant_id)
        scanner = self._scanner_lazy()

        try:
            choices = response.choices  # OpenAI互換
        except AttributeError:
            return

        for choice in choices:
            content = getattr(choice.message, "content", None)
            if not isinstance(content, str) or not content:
                continue
            normalized = normalize_for_pii(content)
            with pii_scan_duration.labels(stage="response").time():
                result = scanner.scan(normalized, tenant_policy=policy)
            for ent, cnt in result.actions_applied.items():
                pii_entities_detected.labels(entity=ent, tenant=tenant_id).inc(cnt)
            choice.message.content = result.masked_text
```

---

## 3. LiteLLM 設定 (config.yaml)

```yaml
general_settings:
  master_key: env/LITELLM_MASTER_KEY

  # カスタムフックを登録
  callbacks:
    - aegis_litellm_hooks.AegisPIIHook

  # フェイルオーバー設定
  routing_strategy: simple-shuffle
  num_retries: 2
  timeout: 30
  fallbacks:
    - claude-opus-4-7: ["bedrock-claude-opus-4-7"]

model_list:
  - model_name: claude-opus-4-7
    litellm_params:
      model: anthropic/claude-opus-4-7
      api_key: os.environ/CUSTOMER_ANTHROPIC_KEY  # テナント別差し替え

litellm_settings:
  drop_params: true
  set_verbose: false
  cache: true
  cache_params:
    type: redis
    host: os.environ/REDIS_HOST
    port: 6379
```

注意：実運用では **テナント別 model_list は LiteLLM の TeamModelList / Virtual Key の機能**で出し分ける。設定の YAML は最小例。

---

## 4. レスポンスストリーミング対応

`stream=true` の場合、LiteLLM は chunk を順次返す。PII スキャナを chunk 単位で実行するとレイテンシが大きく、また文脈を持たない短い chunk では誤検知/取りこぼしが多い。

### 推奨方針

**chunk バッファリング方式**：
1. chunk を一定サイズ（例：512トークン）または改行で集約
2. 集約バッファをスキャン
3. マスク済み chunk を顧客に流す
4. 最終 chunk で残バッファをスキャンしてフラッシュ

ただし、ストリーミング UX を重視する場合は **「ブロック判定のみ chunk 単位で」「マスクは最終レスポンスで」** という妥協も可。

---

## 5. パフォーマンスチューニング

### 5.1 ウォームアップ

LiteLLM起動時に `_build_analyzer()` を 1 回呼んで spaCy をロードする：

```python
@app.on_event("startup")
async def warmup():
    from aegis_pii_jp.recognizers.scanner import _build_analyzer
    _build_analyzer()
```

### 5.2 並行制御

Presidio Analyzer はスレッドセーフ。Fargate 1 タスクで 4 並列スレッドまでは線形にスケール。それ以上はタスク数を増やすこと。

### 5.3 短文最適化

```python
if len(content) < 8:
    return content  # 明らかに PII を含まないと判断
```

### 5.4 長文分割

```python
CHUNK = 8192
chunks = [content[i:i+CHUNK] for i in range(0, len(content), CHUNK)]
results = await asyncio.gather(*(scan_async(c) for c in chunks))
```

---

## 6. メトリクス・ログ仕様

| 名前 | タイプ | ラベル | 説明 |
|---|---|---|---|
| `aegis_pii_scan_duration_seconds` | Histogram | `stage` (request/response) | スキャン時間 |
| `aegis_pii_entities_detected_total` | Counter | `entity`, `tenant` | 検出件数 |
| `aegis_pii_actions_total` | Counter | `action`, `tenant` | アクション件数 |
| `aegis_pii_blocked_requests_total` | Counter | `tenant` | ブロック数 |
| `aegis_pii_scan_errors_total` | Counter | `tenant` | スキャナ障害数 |

ログ：
- `INFO`: 各リクエストの検出種別件数（本文は出さない）
- `WARN`: ブロック発火
- `ERROR`: スキャナ例外

ログには**マスク前の本文を絶対に書かない**。`SafeFormatter` 等で誤って出力されないようにする。

---

## 7. テスト導入手順

1. `pip install -e ./recognizers` （pyproject.toml ベース）
2. `python -m spacy download ja_core_news_md`
3. `pip install -e ./recognizers[dev]`
4. `pytest ../tests`
5. ローカル LiteLLM で `config.yaml` を読み込んで起動
6. curl で疑似リクエスト送信し、マスク動作を目視確認

---

## 8. デプロイチェックリスト

- [ ] Docker image に spaCy `ja_core_news_md` を同梱
- [ ] `AEGIS_PII_HMAC_KEY` を Secrets Manager 経由で設定
- [ ] スキャナ起動時ウォームアップ確認
- [ ] block時のHTTP 451メッセージを顧客向けに翻訳
- [ ] テナントのフェイルオープン設定を初期値 false
- [ ] メトリクス Grafana ダッシュボード作成
- [ ] アラート：`blocked_requests_total` 急増、`scan_errors_total` > 0
