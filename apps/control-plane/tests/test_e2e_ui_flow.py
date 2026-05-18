"""End-to-end test that mirrors the UI flow.

Replicates the exact request sequence the bundled HTML/JS UI performs,
asserting that data is inserted and expected values come back from the API.

Uses FastAPI's TestClient — no separate HTTP server required.
"""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from aegis.main import app


@pytest.fixture(scope="module")
def client():
    # TestClient as a context manager runs FastAPI lifespan (init_db)
    with TestClient(app) as c:
        yield c


ADMIN = {"X-Admin-Token": "test-admin-token"}


def test_ui_flow_happy_path(client: TestClient) -> None:
    """1. UIを開く → 2. テナント作る → 3. キー発行 → 4. イベント送る → 5/6/7 集計確認"""
    # 1. Home loads with HTML
    r = client.get("/")
    assert r.status_code == 200
    assert "Aegis Control Plane" in r.text
    assert "テナント作成" in r.text

    # 1.5. Health
    assert client.get("/api/health").json() == {"status": "ok"}

    # 2. Create tenant (as the UI form would)
    payload = {
        "name": "UIテスト株式会社",
        "contact_email": "qa@uitest.co.jp",
        "plan": "standard",
        "daily_budget_jpy": 10000,
        "monthly_budget_jpy": 100000,
    }
    r = client.post("/api/tenants", json=payload, headers=ADMIN)
    assert r.status_code == 201, r.text
    tenant = r.json()
    assert tenant["name"] == "UIテスト株式会社"
    assert tenant["plan"] == "standard"
    assert tenant["status"] == "active"
    tid = tenant["id"]

    # 2.1 list tenants — should include our tenant
    r = client.get("/api/tenants", headers=ADMIN)
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json())

    # 3. Create API key
    r = client.post(
        f"/api/tenants/{tid}/api-keys",
        json={"label": "ui-test"},
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    key_data = r.json()
    plaintext = key_data["plaintext_key"]
    assert plaintext.startswith("aeg_live_")
    assert key_data["prefix"].startswith("aeg_live_")

    auth = {"Authorization": f"Bearer {plaintext}"}

    # 4. Ingest 3 events: normal / pii / 5xx
    r = client.post(
        "/api/events",
        json={
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "user_label": "sales",
            "prompt_tokens": 800,
            "completion_tokens": 400,
            "total_cost_jpy": "2.5",
            "latency_ms": 1500,
            "status_code": 200,
        },
        headers=auth,
    )
    assert r.status_code == 201, r.text

    r = client.post(
        "/api/events",
        json={
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 500,
            "completion_tokens": 200,
            "total_cost_jpy": "1.2",
            "latency_ms": 900,
            "status_code": 200,
            "pii_detected": True,
            "pii_entities": {"JP_PHONE_NUMBER": 1, "EMAIL_ADDRESS": 2},
        },
        headers=auth,
    )
    assert r.status_code == 201, r.text

    r = client.post(
        "/api/events",
        json={
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_jpy": "0",
            "latency_ms": 30000,
            "status_code": 503,
            "error_type": "upstream_unavailable",
        },
        headers=auth,
    )
    assert r.status_code == 201, r.text

    # 5. Usage summary
    r = client.get("/api/usage", headers=auth)
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["total_requests"] == 3
    assert u["error_requests"] == 1
    assert u["total_prompt_tokens"] == 1300
    assert u["total_completion_tokens"] == 600
    assert float(u["total_cost_jpy"]) == pytest.approx(3.7, rel=1e-3)
    assert "claude-opus-4-7" in u["by_model"]
    assert "gpt-4o" in u["by_model"]
    assert u["by_model"]["claude-opus-4-7"]["requests"] == 2
    assert u["pii_detection_rate"] == pytest.approx(1 / 3, rel=1e-3)

    # 6. Costs
    r = client.get("/api/costs", headers=auth)
    assert r.status_code == 200, r.text
    c = r.json()
    assert float(c["today_cost_jpy"]) == pytest.approx(3.7, rel=1e-3)
    assert c["daily_budget_jpy"] == 10000
    # 3.7 / 10000 = 0.037 -> 0.04 (rounded)
    assert c["daily_consumption_pct"] < 1.0

    # 7. Alerts — at least pii_detected & provider_5xx should be present
    r = client.get("/api/alerts", headers=auth)
    assert r.status_code == 200
    types = {a["type"] for a in r.json()}
    assert "pii_detected" in types, f"missing pii_detected, got {types}"
    assert "provider_5xx" in types, f"missing provider_5xx, got {types}"


def test_burst_triggers_budget_alerts(client: TestClient) -> None:
    """予算閾値の 80% と 100% アラートを発火させる"""
    r = client.post(
        "/api/tenants",
        json={
            "name": "予算テスト",
            "contact_email": "budget@test.co.jp",
            "plan": "lite",
            "daily_budget_jpy": 10000,
            "monthly_budget_jpy": 100000,
        },
        headers=ADMIN,
    )
    tid = r.json()["id"]
    plaintext = client.post(
        f"/api/tenants/{tid}/api-keys",
        json={"label": "burst"},
        headers=ADMIN,
    ).json()["plaintext_key"]
    auth = {"Authorization": f"Bearer {plaintext}"}

    # 9,000 yen → 90% → triggers 80% warn
    r = client.post(
        "/api/events",
        json={
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "prompt_tokens": 10000,
            "completion_tokens": 5000,
            "total_cost_jpy": "9000",
            "latency_ms": 1000,
            "status_code": 200,
        },
        headers=auth,
    )
    assert r.status_code == 201

    types_80 = {a["type"] for a in client.get("/api/alerts", headers=auth).json()}
    assert "cost_threshold_80" in types_80

    # +2,000 yen → 110% → triggers 100% critical
    client.post(
        "/api/events",
        json={
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_cost_jpy": "2000",
            "latency_ms": 1000,
            "status_code": 200,
        },
        headers=auth,
    )
    types_100 = {a["type"] for a in client.get("/api/alerts", headers=auth).json()}
    assert "cost_threshold_100" in types_100, types_100


def test_auth_rejection(client: TestClient) -> None:
    """誤った admin/API key は拒絶される"""
    assert client.get("/api/tenants").status_code == 401
    assert (
        client.get("/api/tenants", headers={"X-Admin-Token": "wrong"}).status_code
        == 401
    )
    assert client.get("/api/usage").status_code == 401
    assert (
        client.get(
            "/api/usage", headers={"Authorization": "Bearer aeg_live_invalid"}
        ).status_code
        == 401
    )


def test_api_key_revoke(client: TestClient) -> None:
    r = client.post(
        "/api/tenants",
        json={"name": "失効テスト", "contact_email": "rev@test.co.jp"},
        headers=ADMIN,
    )
    tid = r.json()["id"]
    k = client.post(
        f"/api/tenants/{tid}/api-keys", json={"label": "to-revoke"}, headers=ADMIN
    ).json()
    plaintext = k["plaintext_key"]
    auth = {"Authorization": f"Bearer {plaintext}"}

    # works before revoke
    assert client.get("/api/usage", headers=auth).status_code == 200

    # revoke
    r = client.delete(
        f"/api/tenants/{tid}/api-keys/{k['id']}", headers=ADMIN
    )
    assert r.status_code == 204

    # 401 after revoke
    assert client.get("/api/usage", headers=auth).status_code == 401


def test_suspended_tenant_is_blocked(client: TestClient) -> None:
    r = client.post(
        "/api/tenants",
        json={"name": "停止テスト", "contact_email": "sus@test.co.jp"},
        headers=ADMIN,
    )
    tid = r.json()["id"]
    plaintext = client.post(
        f"/api/tenants/{tid}/api-keys", json={"label": "x"}, headers=ADMIN
    ).json()["plaintext_key"]
    auth = {"Authorization": f"Bearer {plaintext}"}

    assert client.get("/api/usage", headers=auth).status_code == 200

    # suspend tenant
    r = client.patch(
        f"/api/tenants/{tid}",
        json={"status": "suspended"},
        headers=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"

    # tenant API now 403
    assert client.get("/api/usage", headers=auth).status_code == 403
