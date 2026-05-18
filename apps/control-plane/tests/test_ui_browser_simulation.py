"""Simulate the UI button-click sequence by inspecting app.js semantics.

The UI in static/app.js performs these fetch calls in response to button
clicks. This test sends the SAME HTTP requests (headers, payload shape)
the browser would send, and asserts the database ends in the expected state.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aegis.main import app


def test_full_ui_click_simulation() -> None:
    """各UIボタンが行う fetch を逐次再生する.

    シナリオ：
      1. ページ読込（GET /）
      2. 「Admin Token 保存」ボタン → state.adminToken 設定
      3. 「テナント作成」フォーム送信
      4. 「テナント一覧 再読込」ボタン
      5. テナント行クリック（selectTenant）→ GET keys
      6. 「キー発行」フォーム送信
      7. 「イベント送信」フォーム × 1 (normal)
      8. 「10連投」ボタン → 10件送信、コスト超過誘発
      9. 「利用状況 取得」
      10. 「コスト 取得」 → 予算超過 (110%) 確認
      11. 「アラート 取得」 → 80% / 100% アラート確認
    """
    with TestClient(app) as c:
        # 1
        r = c.get("/")
        assert r.status_code == 200
        for needed in ["adminToken", "tenantForm", "keyForm", "eventForm", "burstButton"]:
            assert needed in r.text, f"UI missing element: {needed}"

        # 2  (clientside only; ヘッダ X-Admin-Token に反映される)
        admin_headers = {"X-Admin-Token": "test-admin-token"}

        # 3 — "テナント作成" submit
        r = c.post(
            "/api/tenants",
            json={
                "name": "クリックシミュレーション社",
                "contact_email": "qa@click.co.jp",
                "plan": "standard",
                "daily_budget_jpy": 50000,
                "monthly_budget_jpy": 500000,
            },
            headers=admin_headers,
        )
        assert r.status_code == 201
        tenant = r.json()
        tid = tenant["id"]

        # 4 — "再読込"
        r = c.get("/api/tenants", headers=admin_headers)
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()]
        assert tid in ids

        # 5 — テナント行クリック → loadKeys()
        r = c.get(f"/api/tenants/{tid}/api-keys", headers=admin_headers)
        assert r.status_code == 200
        assert r.json() == []  # まだキーゼロ

        # 6 — "キー発行" submit
        r = c.post(
            f"/api/tenants/{tid}/api-keys",
            json={"label": "click-sim"},
            headers=admin_headers,
        )
        assert r.status_code == 201
        plaintext = r.json()["plaintext_key"]
        auth = {"Authorization": f"Bearer {plaintext}"}

        # 6.1 — UIは発行後にloadKeysを自動コール
        r = c.get(f"/api/tenants/{tid}/api-keys", headers=admin_headers)
        assert len(r.json()) == 1

        # 7 — "イベント送信" submit (normal)
        r = c.post(
            "/api/events",
            json={
                "provider": "anthropic",
                "model": "claude-opus-4-7",
                "user_label": "manual",
                "prompt_tokens": 800,
                "completion_tokens": 400,
                "total_cost_jpy": "2.5",
                "latency_ms": 1500,
                "status_code": 200,
                "pii_detected": False,
            },
            headers=auth,
        )
        assert r.status_code == 201

        # 8 — "10連投" ボタン: 10 × ¥5000 = ¥50,000 (= 500% of 10,000 budget)
        for i in range(10):
            r = c.post(
                "/api/events",
                json={
                    "provider": "anthropic",
                    "model": "claude-opus-4-7",
                    "user_label": f"burst-{i+1}",
                    "prompt_tokens": 800,
                    "completion_tokens": 400,
                    "total_cost_jpy": "5000",
                    "latency_ms": 1500,
                    "status_code": 200,
                    "pii_detected": False,
                },
                headers=auth,
            )
            assert r.status_code == 201

        # 9 — Usage
        u = c.get("/api/usage", headers=auth).json()
        assert u["total_requests"] == 11
        assert float(u["total_cost_jpy"]) > 50000

        # 10 — Cost (with bar visualization data)
        cost = c.get("/api/costs", headers=auth).json()
        # 11 events × ~5000 yen each ≈ ¥50,002 — at or just above 100% of 50000 budget
        assert cost["daily_consumption_pct"] >= 100.0
        assert float(cost["today_cost_jpy"]) > 50000

        # 11 — Alerts: イベント8件目で80%を、10件目で100%を踏み越える
        alerts = c.get("/api/alerts", headers=auth).json()
        types = {a["type"] for a in alerts}
        assert "cost_threshold_80" in types, f"missing 80% alert, types={types}"
        assert "cost_threshold_100" in types, f"missing 100% alert, types={types}"
        # 同種重複が抑止されていること
        assert sum(1 for a in alerts if a["type"] == "cost_threshold_100") == 1
        assert sum(1 for a in alerts if a["type"] == "cost_threshold_80") == 1
