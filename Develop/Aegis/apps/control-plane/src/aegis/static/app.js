// Aegis Control Plane — MVP frontend
const API = "";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  adminToken: localStorage.getItem("aegis_admin_token") || "dev-admin-token",
  selectedTenantId: null,
  selectedTenantName: null,
  lastPlaintextKey: null,
};

// ---------- helpers ----------
function adminHeaders(extra = {}) {
  return { "Content-Type": "application/json", "X-Admin-Token": state.adminToken, ...extra };
}

async function jsonRequest(method, url, body, headers = {}) {
  const opts = { method, headers: { "Content-Type": "application/json", ...headers } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(API + url, opts);
  const text = await res.text();
  let parsed;
  try { parsed = text ? JSON.parse(text) : null; } catch { parsed = text; }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.payload = parsed;
    throw err;
  }
  return parsed;
}

function showResult(el, value) {
  $(el).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function showError(el, err) {
  const msg = err.payload ? JSON.stringify(err.payload, null, 2) : err.message;
  $(el).textContent = `ERROR: ${err.message}\n${msg}`;
}

function fmtJpy(v) {
  return "¥" + Number(v).toLocaleString("ja-JP", { maximumFractionDigits: 2 });
}

// ---------- admin token ----------
$("#adminToken").value = state.adminToken;
$("#adminSave").addEventListener("click", () => {
  state.adminToken = $("#adminToken").value.trim() || "dev-admin-token";
  localStorage.setItem("aegis_admin_token", state.adminToken);
  $("#adminStatus").textContent = "保存しました";
  setTimeout(() => ($("#adminStatus").textContent = ""), 2000);
});

// ---------- tenants ----------
async function refreshTenants() {
  try {
    const list = await jsonRequest("GET", "/api/tenants", undefined, adminHeaders());
    const tbody = $("#tenantsTable tbody");
    tbody.innerHTML = "";
    for (const t of list) {
      const tr = document.createElement("tr");
      tr.dataset.id = t.id;
      if (t.id === state.selectedTenantId) tr.classList.add("selected");
      tr.innerHTML = `
        <td><input type="radio" name="tenantSel" ${t.id === state.selectedTenantId ? "checked" : ""}/></td>
        <td><code>${t.id.slice(0, 8)}</code></td>
        <td>${t.name}</td>
        <td>${t.plan}</td>
        <td>${t.status}</td>
        <td>${fmtJpy(t.daily_budget_jpy)}</td>
      `;
      tr.addEventListener("click", () => selectTenant(t));
      tbody.appendChild(tr);
    }
  } catch (err) {
    alert("テナント一覧取得に失敗: " + (err.message || err));
  }
}

function selectTenant(t) {
  state.selectedTenantId = t.id;
  state.selectedTenantName = t.name;
  $("#selectedTenantLabel").textContent = `${t.name} (${t.id.slice(0,8)})`;
  $("#keyCreateBtn").disabled = false;
  $$("#tenantsTable tbody tr").forEach((tr) => {
    tr.classList.toggle("selected", tr.dataset.id === t.id);
    const radio = tr.querySelector("input[type=radio]");
    if (radio) radio.checked = tr.dataset.id === t.id;
  });
  loadKeys();
}

$("#refreshTenants").addEventListener("click", refreshTenants);

$("#tenantForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target).entries());
  data.daily_budget_jpy = Number(data.daily_budget_jpy);
  data.monthly_budget_jpy = Number(data.monthly_budget_jpy);
  try {
    const result = await jsonRequest("POST", "/api/tenants", data, adminHeaders());
    showResult("#tenantOut", result);
    e.target.reset();
    e.target.daily_budget_jpy.value = 50000;
    e.target.monthly_budget_jpy.value = 500000;
    await refreshTenants();
  } catch (err) {
    showError("#tenantOut", err);
  }
});

// ---------- api keys ----------
async function loadKeys() {
  if (!state.selectedTenantId) return;
  try {
    const keys = await jsonRequest(
      "GET",
      `/api/tenants/${state.selectedTenantId}/api-keys`,
      undefined,
      adminHeaders()
    );
    const tbody = $("#keysTable tbody");
    tbody.innerHTML = "";
    for (const k of keys) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${k.prefix}</code></td>
        <td>${k.label || "-"}</td>
        <td>${new Date(k.created_at).toLocaleString("ja-JP")}</td>
        <td>${k.revoked_at ? new Date(k.revoked_at).toLocaleString("ja-JP") : "active"}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    console.error(err);
  }
}

$("#keyForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.selectedTenantId) return;
  const label = e.target.label.value.trim() || null;
  try {
    const result = await jsonRequest(
      "POST",
      `/api/tenants/${state.selectedTenantId}/api-keys`,
      { label },
      adminHeaders()
    );
    state.lastPlaintextKey = result.plaintext_key;
    showResult(
      "#keyOut",
      `★ APIキー（この画面でしか表示されません）\n${result.plaintext_key}\n\n${JSON.stringify(result, null, 2)}`
    );
    // 4. のフォームへ自動投入して、即座にイベントを送れるように
    $("#eventForm").apiKey.value = result.plaintext_key;
    e.target.reset();
    await loadKeys();
  } catch (err) {
    showError("#keyOut", err);
  }
});

// ---------- events ----------
async function sendEvent(overrides = {}) {
  const f = $("#eventForm");
  const apiKey = (overrides.apiKey ?? f.apiKey.value).trim();
  if (!apiKey) throw new Error("API key is empty");
  const payload = {
    provider: f.provider.value,
    model: f.model.value,
    user_label: f.user_label.value || null,
    prompt_tokens: Number(f.prompt_tokens.value),
    completion_tokens: Number(f.completion_tokens.value),
    total_cost_jpy: f.total_cost_jpy.value, // 文字列で渡してもDecimalに変換される
    latency_ms: Number(f.latency_ms.value),
    status_code: Number(f.status_code.value),
    pii_detected: f.pii_detected.value === "true",
    ...overrides.payload,
  };
  return jsonRequest("POST", "/api/events", payload, {
    Authorization: `Bearer ${apiKey}`,
  });
}

$("#eventForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const result = await sendEvent();
    showResult("#eventOut", result);
  } catch (err) {
    showError("#eventOut", err);
  }
});

$("#burstButton").addEventListener("click", async () => {
  const results = [];
  for (let i = 0; i < 10; i++) {
    try {
      const r = await sendEvent({
        payload: {
          user_label: `burst-${i + 1}`,
          total_cost_jpy: "5000", // 大きめのコスト → 予算超過を誘発
        },
      });
      results.push({ ok: true, id: r.id });
    } catch (err) {
      results.push({ ok: false, error: err.message });
      break;
    }
  }
  showResult("#eventOut", { burst: results });
});

// ---------- usage ----------
$("#fetchUsage").addEventListener("click", async () => {
  const apiKey = ($("#eventForm").apiKey.value || "").trim();
  if (!apiKey) {
    showResult("#usageOut", "APIキーが必要です（セクション4の入力欄）");
    return;
  }
  try {
    const result = await jsonRequest("GET", "/api/usage", undefined, {
      Authorization: `Bearer ${apiKey}`,
    });
    showResult("#usageOut", result);
  } catch (err) {
    showError("#usageOut", err);
  }
});

// ---------- cost ----------
function costBars(view, c) {
  const dpct = Math.min(c.daily_consumption_pct, 200);
  const mpct = Math.min(c.monthly_consumption_pct, 200);
  const cls = (p) => (p >= 100 ? "danger" : p >= 80 ? "warn" : "");
  view.innerHTML = `
    <div class="bar-label">日次: ${fmtJpy(c.today_cost_jpy)} / ${fmtJpy(c.daily_budget_jpy)} (${c.daily_consumption_pct}%)</div>
    <div class="bar-wrap"><div class="bar ${cls(c.daily_consumption_pct)}" style="width: ${Math.min(dpct, 100)}%"></div></div>
    <div class="bar-label">月次: ${fmtJpy(c.month_cost_jpy)} / ${fmtJpy(c.monthly_budget_jpy)} (${c.monthly_consumption_pct}%)</div>
    <div class="bar-wrap"><div class="bar ${cls(c.monthly_consumption_pct)}" style="width: ${Math.min(mpct, 100)}%"></div></div>
  `;
}

$("#fetchCost").addEventListener("click", async () => {
  const apiKey = ($("#eventForm").apiKey.value || "").trim();
  if (!apiKey) {
    showResult("#costOut", "APIキーが必要です（セクション4の入力欄）");
    return;
  }
  try {
    const result = await jsonRequest("GET", "/api/costs", undefined, {
      Authorization: `Bearer ${apiKey}`,
    });
    costBars($("#costView"), result);
    showResult("#costOut", result);
  } catch (err) {
    showError("#costOut", err);
  }
});

// ---------- alerts ----------
$("#fetchAlerts").addEventListener("click", async () => {
  const apiKey = ($("#eventForm").apiKey.value || "").trim();
  if (!apiKey) return;
  try {
    const list = await jsonRequest("GET", "/api/alerts", undefined, {
      Authorization: `Bearer ${apiKey}`,
    });
    const tbody = $("#alertsTable tbody");
    tbody.innerHTML = "";
    for (const a of list) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${new Date(a.fired_at).toLocaleString("ja-JP")}</td>
        <td>${a.type}</td>
        <td>${a.severity}</td>
        <td>${a.message}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    alert("アラート取得失敗: " + err.message);
  }
});

// ---------- boot ----------
refreshTenants();
