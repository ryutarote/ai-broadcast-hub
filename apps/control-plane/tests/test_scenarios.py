"""10 realistic Aegis customer scenario tests.

各シナリオは、実際の顧客が経験する完結したユースケースを表現する。
HTTP API レベルでテストし、ビジネスフローが正しく動くことを確認する。

シナリオ:
  1. 新規SaaS企業オンボーディング: 登録→キー発行→疎通→1週間使用→レポート閲覧
  2. コスト暴走インシデント: 本番バグでコスト10倍→閾値超過→suspend
  3. モデル乗り換え評価: Claude 4.6 vs 4.7 を並行投入→比較レポート
  4. プロバイダ・フェイルオーバー: anthropic 障害→bedrock 切替→記録
  5. PII検出と監査ログエクスポート: PII イベント蓄積→CSV エクスポート
  6. マルチテナント分離: 医療テナントと SaaS テナントが互いに干渉しない
  7. 月次レポート生成: 月初に前月分の利用・コスト・改善提案レポート
  8. APIキー・ローテーション: 旧キー失効→新キー切替の重複期間
  9. user_label 別の部門別集計: 営業/サポート/開発のコスト按分
 10. テナント解約とデータ削除証明
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from aegis.main import app


ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def create_tenant(c: TestClient, *, name: str, **overrides) -> dict:
    payload = {
        "name": name,
        "contact_email": f"{name.lower().replace(' ', '')}@example.co.jp",
        "plan": "standard",
        "daily_budget_jpy": 50000,
        "monthly_budget_jpy": 500000,
    }
    payload.update(overrides)
    r = c.post("/api/tenants", json=payload, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


def issue_key(c: TestClient, tenant_id: str, label: str = "default") -> str:
    r = c.post(
        f"/api/tenants/{tenant_id}/api-keys",
        json={"label": label},
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    return r.json()["plaintext_key"]


def send_event(c: TestClient, key: str, **fields) -> dict:
    base = {
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_cost_jpy": "1.0",
        "latency_ms": 500,
        "status_code": 200,
        "pii_detected": False,
    }
    base.update(fields)
    r = c.post(
        "/api/events",
        json=base,
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Scenario 1: SaaSスタートアップが Aegis にオンボーディングし、1週間使う
# ---------------------------------------------------------------------------


def test_scenario_01_saas_onboarding_first_week(client: TestClient) -> None:
    """50人規模の SaaS スタートアップがAegisを導入する一連の流れ.

    1. CTOが管理画面でテナント作成（Standard プラン）
    2. APIキー発行（本番用）
    3. プロキシ疎通確認のためダミーイベント送信
    4. 1週間に渡ってさまざまな user_label でリクエストを記録
    5. usage で全体把握、costs で予算残量確認
    """
    tenant = create_tenant(
        client,
        name="ScrumWorks SaaS",
        plan="standard",
        daily_budget_jpy=20000,
        monthly_budget_jpy=200000,
    )
    key = issue_key(client, tenant["id"], "production")

    # Day 1: 疎通確認
    first = send_event(client, key, user_label="healthcheck", total_cost_jpy="0.01")
    assert first["tenant_id"] == tenant["id"]

    # Day 1-7 のさまざまな利用
    for day in range(7):
        for label in ("sales-bot", "support-bot", "internal-rag"):
            send_event(
                client,
                key,
                user_label=label,
                model="claude-opus-4-7" if label != "internal-rag" else "claude-sonnet-4-6",
                total_cost_jpy=str(50 + day * 10),
                prompt_tokens=400 + day * 50,
                completion_tokens=200,
            )

    usage = client.get(
        "/api/usage",
        headers={"Authorization": f"Bearer {key}"},
    ).json()
    # 21 normal events + 1 healthcheck
    assert usage["total_requests"] == 22
    assert set(usage["by_model"].keys()) == {"claude-opus-4-7", "claude-sonnet-4-6"}

    costs = client.get(
        "/api/costs", headers={"Authorization": f"Bearer {key}"}
    ).json()
    # 当日内の累計コストが表示される
    assert float(costs["today_cost_jpy"]) > 0
    assert costs["daily_budget_jpy"] == 20000


# ---------------------------------------------------------------------------
# Scenario 2: 本番デプロイのバグでコスト10倍に → 200%予算で auto-suspend
# ---------------------------------------------------------------------------


def test_scenario_02_cost_runaway_triggers_suspend(client: TestClient) -> None:
    tenant = create_tenant(
        client,
        name="BudgetBust Co",
        daily_budget_jpy=10000,
        monthly_budget_jpy=300000,
    )
    key = issue_key(client, tenant["id"])

    # 通常負荷
    send_event(client, key, total_cost_jpy="500")  # 5%

    # 本番バグ：プロンプトが循環参照で 30,000 yen 一発で消費
    send_event(client, key, total_cost_jpy="30000")  # ↗ 300% over budget

    alerts = client.get(
        "/api/alerts", headers={"Authorization": f"Bearer {key}"}
    ).json()
    types = {a["type"] for a in alerts}
    assert "cost_threshold_100" in types

    # 200% を超えたので auto-suspend が走るべき
    refreshed = client.get(f"/api/tenants/{tenant['id']}", headers=ADMIN).json()
    assert refreshed["status"] == "suspended", refreshed
    # suspended になった後の API は 403
    r = client.get("/api/usage", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Scenario 3: モデル乗り換え評価レポート（4.6 vs 4.7 並行投入）
# ---------------------------------------------------------------------------


def test_scenario_03_model_comparison_report(client: TestClient) -> None:
    tenant = create_tenant(client, name="ModelEval Inc")
    key = issue_key(client, tenant["id"])

    # 4.6 を 30 件、4.7 を 30 件投入
    for i in range(30):
        send_event(
            client,
            key,
            model="claude-sonnet-4-6",
            user_label="eval-baseline",
            prompt_tokens=300,
            completion_tokens=150,
            total_cost_jpy="0.8",
            latency_ms=600 + (i % 5) * 20,
        )
        send_event(
            client,
            key,
            model="claude-opus-4-7",
            user_label="eval-candidate",
            prompt_tokens=300,
            completion_tokens=150,
            total_cost_jpy="1.2",
            latency_ms=500 + (i % 5) * 15,
        )

    r = client.get(
        "/api/models/compare",
        params={"model_a": "claude-sonnet-4-6", "model_b": "claude-opus-4-7"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["a"]["model"] == "claude-sonnet-4-6"
    assert report["b"]["model"] == "claude-opus-4-7"
    assert report["a"]["requests"] == 30
    assert report["b"]["requests"] == 30
    # 4.7 のほうがコスト高、レイテンシ低
    assert float(report["b"]["avg_cost_jpy"]) > float(report["a"]["avg_cost_jpy"])
    assert report["b"]["avg_latency_ms"] < report["a"]["avg_latency_ms"]


# ---------------------------------------------------------------------------
# Scenario 4: プロバイダ・フェイルオーバー（anthropic → bedrock）
# ---------------------------------------------------------------------------


def test_scenario_04_provider_failover_recorded(client: TestClient) -> None:
    tenant = create_tenant(client, name="Failover Trading Co")
    key = issue_key(client, tenant["id"])

    # 通常時: anthropic
    send_event(client, key, provider="anthropic", model="claude-opus-4-7")
    send_event(client, key, provider="anthropic", model="claude-opus-4-7")

    # anthropic 障害 → bedrock 経由 Claude にフェイルオーバー
    # primary_provider が anthropic だったが actual_provider は bedrock
    send_event(
        client,
        key,
        provider="bedrock",
        model="claude-opus-4-7",
        primary_provider="anthropic",
        failover_reason="anthropic_5xx_burst",
    )
    send_event(
        client,
        key,
        provider="bedrock",
        model="claude-opus-4-7",
        primary_provider="anthropic",
        failover_reason="anthropic_5xx_burst",
    )

    # フェイルオーバー履歴の集計
    r = client.get(
        "/api/failovers",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text
    fo = r.json()
    assert fo["total_failovers"] == 2
    assert fo["from_provider"]["anthropic"] == 2
    assert fo["to_provider"]["bedrock"] == 2
    assert fo["reasons"]["anthropic_5xx_burst"] == 2

    # provider_failover アラートが発火
    alerts = client.get(
        "/api/alerts", headers={"Authorization": f"Bearer {key}"}
    ).json()
    assert any(a["type"] == "provider_failover" for a in alerts)


# ---------------------------------------------------------------------------
# Scenario 5: PII検出と監査ログCSVエクスポート
# ---------------------------------------------------------------------------


def test_scenario_05_pii_audit_csv_export(client: TestClient) -> None:
    tenant = create_tenant(client, name="Privacy Sensitive Co")
    key = issue_key(client, tenant["id"])

    # PII を含むイベントを 5 件、普通のものを 5 件
    for i in range(5):
        send_event(
            client,
            key,
            user_label=f"customer-{i}",
            pii_detected=True,
            pii_entities={"JP_PHONE_NUMBER": 1, "EMAIL_ADDRESS": 1},
        )
        send_event(client, key, user_label=f"product-{i}")

    # 個情委対応で過去90日のログを CSV エクスポート
    r = client.get(
        "/api/exports/events",
        params={"format": "csv"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    # ヘッダ行
    assert "occurred_at,model,user_label,pii_detected,pii_entities" in body
    # PII レコードが含まれる
    assert "JP_PHONE_NUMBER" in body
    # マスク前データは絶対に含まれない（プロンプト/レスポンス本文は保存していない）
    assert "PHONE:" not in body  # 念のため


# ---------------------------------------------------------------------------
# Scenario 6: マルチテナント分離（医療法人 vs SaaS）
# ---------------------------------------------------------------------------


def test_scenario_06_multi_tenant_isolation(client: TestClient) -> None:
    medical = create_tenant(client, name="MedicalGroup Hospital", plan="pro")
    saas = create_tenant(client, name="GenericSaaS")
    mkey = issue_key(client, medical["id"])
    skey = issue_key(client, saas["id"])

    # 医療テナントに PII イベント
    for _ in range(3):
        send_event(client, mkey, user_label="patient-records", pii_detected=True)
    # SaaS テナントに通常イベント
    for _ in range(5):
        send_event(client, skey, user_label="product-bot")

    # 医療テナントのデータは SaaS の鍵では見えない
    su = client.get(
        "/api/usage", headers={"Authorization": f"Bearer {skey}"}
    ).json()
    assert su["total_requests"] == 5
    assert su["pii_detection_rate"] == 0

    mu = client.get(
        "/api/usage", headers={"Authorization": f"Bearer {mkey}"}
    ).json()
    assert mu["total_requests"] == 3
    assert mu["pii_detection_rate"] == 1.0

    # アラートもテナント別に分離
    salerts = client.get(
        "/api/alerts", headers={"Authorization": f"Bearer {skey}"}
    ).json()
    assert all(a["tenant_id"] == saas["id"] for a in salerts)


# ---------------------------------------------------------------------------
# Scenario 7: 月次レポート生成
# ---------------------------------------------------------------------------


def test_scenario_07_monthly_report_generated(client: TestClient) -> None:
    tenant = create_tenant(
        client, name="ReportCo", daily_budget_jpy=200000, monthly_budget_jpy=2000000
    )
    key = issue_key(client, tenant["id"])
    for i in range(20):
        send_event(
            client,
            key,
            user_label=("sales" if i % 2 == 0 else "support"),
            total_cost_jpy="100",
            prompt_tokens=500,
            completion_tokens=200,
        )

    now = datetime.now(timezone.utc)
    period = f"{now.year:04d}-{now.month:02d}"

    r = client.post(
        f"/api/tenants/{tenant['id']}/reports",
        json={"period": period},
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    report = r.json()
    assert report["period"] == period
    assert report["summary"]["total_requests"] == 20
    assert float(report["summary"]["total_cost_jpy"]) == pytest.approx(2000.0, rel=1e-3)
    assert "sales" in report["summary"]["by_user_label"]
    assert "support" in report["summary"]["by_user_label"]
    assert report["summary"]["by_user_label"]["sales"]["requests"] == 10

    # 顧客がレポート一覧を取得できる
    r = client.get(
        "/api/reports", headers={"Authorization": f"Bearer {key}"}
    )
    assert r.status_code == 200
    reports = r.json()
    assert any(rep["period"] == period for rep in reports)


# ---------------------------------------------------------------------------
# Scenario 8: APIキー・ローテーション（重複期間あり）
# ---------------------------------------------------------------------------


def test_scenario_08_api_key_rotation(client: TestClient) -> None:
    tenant = create_tenant(client, name="RotateCo")
    old_key = issue_key(client, tenant["id"], "old-key")
    # 古い鍵で動作することを確認
    send_event(client, old_key)

    # ローテーション：新キー発行（旧キーはまだ有効）
    new_key = issue_key(client, tenant["id"], "new-key")
    # 重複期間中はどちらも動く
    send_event(client, old_key, user_label="legacy")
    send_event(client, new_key, user_label="new-deploy")

    # 旧キーを失効
    keys = client.get(
        f"/api/tenants/{tenant['id']}/api-keys", headers=ADMIN
    ).json()
    old_key_id = next(k for k in keys if k["label"] == "old-key")["id"]
    r = client.delete(
        f"/api/tenants/{tenant['id']}/api-keys/{old_key_id}", headers=ADMIN
    )
    assert r.status_code == 204

    # 旧キーは無効、新キーは引き続き動く
    r = client.get("/api/usage", headers={"Authorization": f"Bearer {old_key}"})
    assert r.status_code == 401
    r = client.get("/api/usage", headers={"Authorization": f"Bearer {new_key}"})
    assert r.status_code == 200
    # データはテナント単位で蓄積されている
    assert r.json()["total_requests"] == 3


# ---------------------------------------------------------------------------
# Scenario 9: user_label 別の部門別コスト按分
# ---------------------------------------------------------------------------


def test_scenario_09_user_label_breakdown(client: TestClient) -> None:
    tenant = create_tenant(client, name="DeptCharge Inc", daily_budget_jpy=500000)
    key = issue_key(client, tenant["id"])

    # 営業=50件×100円、サポート=20件×200円、開発=10件×500円
    for _ in range(50):
        send_event(client, key, user_label="sales", total_cost_jpy="100")
    for _ in range(20):
        send_event(client, key, user_label="support", total_cost_jpy="200")
    for _ in range(10):
        send_event(client, key, user_label="engineering", total_cost_jpy="500")

    r = client.get(
        "/api/usage/by-label", headers={"Authorization": f"Bearer {key}"}
    )
    assert r.status_code == 200, r.text
    breakdown = r.json()
    by = {row["user_label"]: row for row in breakdown["items"]}
    assert by["sales"]["requests"] == 50
    assert float(by["sales"]["total_cost_jpy"]) == 5000
    assert by["support"]["requests"] == 20
    assert float(by["support"]["total_cost_jpy"]) == 4000
    assert by["engineering"]["requests"] == 10
    assert float(by["engineering"]["total_cost_jpy"]) == 5000
    # 合計が正しいこと
    assert float(breakdown["total_cost_jpy"]) == 14000


# ---------------------------------------------------------------------------
# Scenario 10: テナント解約とデータ削除証明
# ---------------------------------------------------------------------------


def test_scenario_10_tenant_churn_and_deletion_certificate(client: TestClient) -> None:
    tenant = create_tenant(client, name="LeavingCo")
    key = issue_key(client, tenant["id"])
    for _ in range(3):
        send_event(client, key)

    # 解約 (status=churned)
    r = client.patch(
        f"/api/tenants/{tenant['id']}",
        json={"status": "churned"},
        headers=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "churned"
    # 解約直後は API 拒絶される（active のみ許可）
    r = client.get("/api/usage", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 403

    # データ削除（管理APIから明示確認つき）
    r = client.post(
        f"/api/tenants/{tenant['id']}/deletion",
        json={"confirm_name": "LeavingCo", "reason": "customer_churn_30_day"},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    cert = r.json()
    assert cert["tenant_id"] == tenant["id"]
    assert cert["events_deleted"] >= 3
    assert cert["api_keys_deleted"] >= 1
    assert "sha256" in cert
    assert len(cert["sha256"]) == 64

    # 削除後はテナント自体も 404
    r = client.get(f"/api/tenants/{tenant['id']}", headers=ADMIN)
    assert r.status_code == 404
