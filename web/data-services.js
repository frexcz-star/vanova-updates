/* ============================================================
   MAIOS Data Services — the data layer of the dashboard.

   The UI NEVER hardcodes business data. It asks DataServices for
   structured payloads. DataServices:

     1. Tries the MAIOS Cloud API (login -> JWT -> GET /api/dashboard)
     2. On success returns REAL (or connector-pushed) data.
     3. If the API is unreachable / auth fails, falls back to the
        bundled MOCK sample data, clearly labelled `dataMode: "mock"`.
     4. Empty sources are shown as "not connected" — never invented.

   This is the ONLY module allowed to fetch. Views consume `state.data`.
   ============================================================ */
(function (global) {
  "use strict";

  const CONFIG = {
    // In production set to the public MAIOS Cloud URL, e.g.
    // https://maios.moovingpaper.com
    API_BASE: global.__MAIOS_API__ || "",
    // Default fallback: same-origin (works when dashboard is served by Cloud)
    get api() {
      return this.API_BASE || (window.location.origin || "");
    },
  };

  const TOKEN_KEY = "maios_access_token";
  const REFRESH_KEY = "maios_refresh_token";
  const INSIGHT_ACTIONS_KEY = "maios_insight_actions";
  const INTEGRATIONS_KEY = "maios_integrations_local";
  const VALID_INSIGHT_ACTIONS = new Set(["approved", "rejected", "dismissed"]);
  const VALID_INTEGRATION_IDS = new Set(["shopify", "erp", "mcp", "email", "instagram", "gmail", "drive", "facturascript"]);
  const RUNTIME = global.__MAIOS_RUNTIME__ || "http://127.0.0.1:8765";

  function readInsightActionsLocal() {
    try {
      const raw = localStorage.getItem(INSIGHT_ACTIONS_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        const out = {};
        for (const [k, v] of Object.entries(parsed)) {
          if (VALID_INSIGHT_ACTIONS.has(v)) out[String(k)] = v;
        }
        return out;
      }
    } catch (e) {}
    return {};
  }

  function writeInsightActionLocal(insightId, action) {
    const actions = readInsightActionsLocal();
    actions[insightId] = action;
    localStorage.setItem(INSIGHT_ACTIONS_KEY, JSON.stringify(actions));
    return { ok: true, insight_id: insightId, action, source: "localStorage" };
  }

  function readIntegrationsLocal() {
    try {
      const raw = localStorage.getItem(INTEGRATIONS_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function normalizeIntegrationConfig(id, cfg) {
    const iid = String(id || "").toLowerCase();
    const src = cfg && typeof cfg === "object" ? cfg : {};
    const out = Object.assign({}, src);
    let url = String(out.url || out.shopUrl || out.storeUrl || "").trim();
    if (iid === "shopify" && url && !/^https?:\/\//i.test(url)) {
      url = "https://" + url.replace(/^\/+/, "");
    }
    out.url = url;
    if (out.token != null) out.token = String(out.token).trim();
    if (out.user != null) out.user = String(out.user).trim();
    const pass = out.password != null ? out.password : out.pass;
    if (pass != null) out.password = String(pass).trim();
    if (out.apiKey != null && out.api_key == null) out.api_key = String(out.apiKey).trim();
    if (out.baseUrl != null && out.base_url == null) out.base_url = String(out.baseUrl).trim();
    if (out.dbPath != null && out.db_path == null) out.db_path = String(out.dbPath).trim();
    delete out.shopUrl;
    delete out.storeUrl;
    delete out.pass;
    return out;
  }

  function writeIntegrationLocal(id, cfg) {
    const iid = String(id || "").toLowerCase();
    if (!VALID_INTEGRATION_IDS.has(iid)) {
      return { ok: false, error: "Integración no válida: " + id };
    }
    const body = normalizeIntegrationConfig(iid, cfg);
    if (iid === "shopify" && (!body.url || !body.token)) {
      return { ok: false, error: "URL y token de Shopify son obligatorios" };
    }
    const store = readIntegrationsLocal();
    store[iid] = Object.assign({}, store[iid] || {}, body, {
      connected: true,
      updatedAt: new Date().toISOString(),
    });
    localStorage.setItem(INTEGRATIONS_KEY, JSON.stringify(store));
    return {
      ok: true,
      connected: true,
      url: store[iid].url || "",
      source: "localStorage",
    };
  }

  function getIntegrationLocal(id) {
    const iid = String(id || "").toLowerCase();
    const entry = readIntegrationsLocal()[iid];
    if (!entry || !entry.connected) return { connected: false };
    const out = { connected: true };
    if (entry.url) out.url = entry.url;
    if (entry.user) out.user = entry.user;
    if (entry.token) out.tokenSet = true;
    if (entry.pass || entry.password) out.passwordSet = true;
    return out;
  }

  function isIntegrationFullyConfigured(id, cfg) {
    if (!cfg || !cfg.connected) return false;
    const iid = String(id || "").toLowerCase();
    if (iid === "shopify" || iid === "erp") {
      return !!(cfg.url && (cfg.tokenSet || cfg.token));
    }
    if (iid === "drive" || iid === "facturascript") {
      return !!cfg.url;
    }
    return true;
  }

  function sanitizeIntegrationStatus(id, cfg) {
    const out = cfg && typeof cfg === "object" ? Object.assign({}, cfg) : { connected: false };
    if (!isIntegrationFullyConfigured(id, out)) {
      return { connected: false };
    }
    return out;
  }

  function setupCompleteLocally() {
    try {
      return localStorage.getItem("maios_setup_done") === "1";
    } catch (e) {
      return false;
    }
  }

  function allowMockFallback() {
    // Mock data is for explicit dev only — never after real setup/login.
    if (setupCompleteLocally()) return false;
    if (state.token) return false;
    return !!global.__MAIOS_DEV_MOCK__;
  }

  async function loadLocalDashboard() {
    // VANOVA 3.0 (seguridad): /api/dashboard/local expone el snapshot del
    // negocio y ahora exige token — usar runtimeApi (adjunta la auth) en vez
    // de fetch directo.
    try {
      const d = await runtimeApi("/api/dashboard/local", { timeoutMs: 5000 });
      if (d && d.dataMode && d.dataMode !== "empty" && d.dataMode !== "mock") return d;
    } catch (e) {}
    return null;
  }
  const state = {
    token: null,
    user: null,
    data: null,          // last dashboard payload
    dataMode: "empty",   // real | mock | empty
    connected: false,    // API reachable?
    hermes: null,        // connector-reported hermes status
    wsState: "disconnected", // connecting | connected | reconnecting | disconnected | auth_failed
    wsError: null,
  };

  try {
    const savedToken = localStorage.getItem(TOKEN_KEY);
    if (savedToken) state.token = savedToken;
  } catch (e) {}

  async function runtimeAuthHeaders() {
    try {
      if (global.maios && typeof global.maios.getRuntimeAuthHeaders === "function") {
        const headers = await global.maios.getRuntimeAuthHeaders();
        if (headers && typeof headers === "object") return headers;
      }
    } catch (e) {}
    return {};
  }

  async function runtimeApi(path, options = {}) {
    const auth = await runtimeAuthHeaders();
    const headers = Object.assign(
      { "Content-Type": "application/json", Accept: "application/json" },
      auth,
      options.headers || {}
    );
    const timeoutMs = options.timeoutMs || 8000;
    let res = await fetch(
      RUNTIME + path,
      Object.assign({}, options, {
        headers,
        signal: AbortSignal.timeout(timeoutMs),
      })
    );
    // BUG real (Nico, logs): el runtime devolvía 401 persistente ("Unauthorized
    // read GET /api/files" x16758) porque el frontend adjuntaba un token que ya
    // no coincidía con el runtimeToken del secrets (p.ej. tras un reinicio del
    // runtime que rotó/regeneró credenciales, o desajuste de instalación). Sin
    // reintento, la sesión quedaba rota: los datos (files/products/sales) nunca
    // se cargaban y el catálogo no se actualizaba. Reintento UNA vez releyendo
    // la auth (el main process lee el token actual del secrets en cada llamada).
    if (res.status === 401 && !options._retried) {
      const auth2 = await runtimeAuthHeaders();
      const headers2 = Object.assign(
        { "Content-Type": "application/json", Accept: "application/json" },
        auth2,
        options.headers || {}
      );
      res = await fetch(
        RUNTIME + path,
        Object.assign({}, options, {
          headers: headers2,
          _retried: true,
          signal: AbortSignal.timeout(timeoutMs),
        })
      );
    }
    let body = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("json")) {
      try {
        body = await res.json();
      } catch (e) {
        body = null;
      }
    }
    if (!res.ok) {
      const msg =
        (body && (body.error || body.message)) ||
        "Runtime " + res.status + " " + res.statusText;
      const err = new Error(msg);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body != null ? body : {};
  }

  // -----------------------------------------------------------
  // Low-level fetch with auth + error handling
  // -----------------------------------------------------------
  async function api(path, options = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      options.headers || {}
    );
    if (state.token) headers["Authorization"] = "Bearer " + state.token;
    const res = await fetch(CONFIG.api + path, Object.assign({}, options, { headers }));
    if (res.status === 401 && state.token) {
      // token expired -> try refresh once
      const refreshed = await tryRefresh();
      if (refreshed) return api(path, options);
    }
    if (!res.ok) {
      throw new Error("API " + res.status + " " + res.statusText);
    }
    const ct = res.headers.get("content-type") || "";
    return ct.includes("json") ? res.json() : res.text();
  }

  // Single-flight refresh: many 401s in the same tick must share ONE refresh
  // call, otherwise the backend rate limit (429) kills every attempt and the
  // session deadlocks.
  let _refreshInFlight = null;

  async function _refreshOnce(rt) {
    const r = await fetch(CONFIG.api + "/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!r.ok) return false;
    const d = await r.json();
    state.token = d.access_token;
    localStorage.setItem(TOKEN_KEY, d.access_token);
    // The backend ROTATES the refresh token (single-use). Persist the new one,
    // otherwise every future refresh fails with 401 and the session dies.
    if (d.refresh_token) localStorage.setItem(REFRESH_KEY, d.refresh_token);
    return true;
  }

  async function tryRefresh() {
    const rt = localStorage.getItem(REFRESH_KEY);
    if (!rt) return false;
    if (_refreshInFlight) return _refreshInFlight;
    _refreshInFlight = (async () => {
      try {
        const ok = await _refreshOnce(rt);
        if (ok) return true;
        // 429 = rate limited: the token was NOT consumed, so a short backoff
        // and one retry is safe (avoiding the 401 -> refresh -> 429 loop).
        await new Promise(function (res) {
          setTimeout(res, 1500);
        });
        return _refreshOnce(localStorage.getItem(REFRESH_KEY) || rt);
      } catch (e) {
        return false;
      } finally {
        _refreshInFlight = null;
      }
    })();
    return _refreshInFlight;
  }

  // -----------------------------------------------------------
  // Public API
  // -----------------------------------------------------------
  global.DataServices = {
    state,

    /** Health check: is the MAIOS Cloud reachable? */
    async ping() {
      try {
        const r = await fetch(CONFIG.api + "/api/health", { headers: { Accept: "application/json" } });
        return r.ok;
      } catch (e) {
        return false;
      }
    },

    async login(username, password) {
      const body = new URLSearchParams();
      body.set("username", username);
      body.set("password", password);
      const res = await fetch(CONFIG.api + "/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      if (!res.ok) {
        const err = new Error(
          res.status === 429
            ? "Demasiados intentos de inicio de sesión. Espera un minuto e inténtalo de nuevo."
            : "Credenciales incorrectas"
        );
        err.status = res.status;
        throw err;
      }
      const d = await res.json();
      state.token = d.access_token;
      localStorage.setItem(TOKEN_KEY, d.access_token);
      if (d.refresh_token) localStorage.setItem(REFRESH_KEY, d.refresh_token);
      state.connected = true;
      return d;
    },

    /** Manual password login resolved by the LOCAL runtime (8765). The runtime
        holds cloud.env (the owner's real credentials) and syncs the Cloud DB
        before validating, so the manual login works even if the Cloud's local
        user DB drifted from cloud.env after an update. */
    async loginLocal(username, password) {
      const body = new URLSearchParams();
      body.set("username", username);
      body.set("password", password);
      try {
        const res = await fetch(RUNTIME + "/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
          signal: AbortSignal.timeout(15000),
        });
        if (!res.ok) {
          const err = new Error(
            res.status === 429
              ? "Demasiados intentos de inicio de sesión. Espera un minuto e inténtalo de nuevo."
              : res.status === 401 ? "Credenciales incorrectas" : "No se pudo conectar con el servicio"
          );
          err.status = res.status;
          throw err;
        }
        const d = await res.json();
        state.token = d.access_token;
        localStorage.setItem(TOKEN_KEY, d.access_token);
        if (d.refresh_token) localStorage.setItem(REFRESH_KEY, d.refresh_token);
        state.connected = true;
        return d;
      } catch (e) {
        if (e && e.status) throw e;
        const err = new Error("No se pudo conectar con el servicio");
        err.status = 0;
        throw err;
      }
    },

    /** Localhost recovery — uses runtime + cloud.env after updates (no password in browser). */
    async tryLocalSession() {
      try {
        const r = await runtimeApi("/api/auth/local-session");
        if (!r || !r.ok || !r.access_token) return { ok: false, error: (r && r.error) || "unavailable" };
        state.token = r.access_token;
        localStorage.setItem(TOKEN_KEY, r.access_token);
        if (r.refresh_token) localStorage.setItem(REFRESH_KEY, r.refresh_token);
        state.connected = true;
        return { ok: true, username: r.username || "ceo" };
      } catch (e) {
        return { ok: false, error: e && e.message ? e.message : "unavailable" };
      }
    },

    async me() {
      try {
        state.user = await api("/api/me");
        return state.user;
      } catch (e) {
        return null;
      }
    },

    /**
     * Load the dashboard payload. Returns { ok, dataMode, data, error }.
     * Falls back to bundled mock when the API is unreachable.
     */
    async loadDashboard() {
      // 1) Try the real Cloud API when authenticated
      try {
        if (!state.token) {
          state.connected = await this.ping();
          const local = await loadLocalDashboard();
          if (local) {
            state.data = local;
            state.dataMode = local.dataMode || "partial";
            state.connected = true;
            return { ok: true, dataMode: state.dataMode, data: local, source: "local" };
          }
          if (!state.connected) {
            if (allowMockFallback() && global.__MAIOS_MOCK__) {
              state.data = global.__MAIOS_MOCK__();
              state.dataMode = "mock";
            } else {
              state.data = null;
              state.dataMode = "empty";
            }
            return { ok: false, dataMode: state.dataMode, data: state.data, error: "offline" };
          }
          if (allowMockFallback() && global.__MAIOS_MOCK__) {
            state.data = global.__MAIOS_MOCK__();
            state.dataMode = "mock";
          } else {
            state.data = null;
            state.dataMode = "empty";
          }
          return { ok: false, dataMode: state.dataMode, data: state.data, error: "auth-required" };
        }
        const d = await api("/api/dashboard");
        const mode = d && d.dataMode ? d.dataMode : "empty";
        if (mode === "empty" || mode === "mock") {
          const local = await loadLocalDashboard();
          if (local) {
            state.data = local;
            state.dataMode = local.dataMode || "partial";
            state.connected = true;
            return { ok: true, dataMode: state.dataMode, data: local, source: "local" };
          }
        }
        state.data = d;
        state.dataMode = mode;
        state.connected = true;
        return { ok: true, dataMode: state.dataMode, data: d, source: "cloud" };
      } catch (e) {
        // 2) Cloud unreachable — prefer local scan snapshot over mock
        const local = await loadLocalDashboard();
        if (local) {
          state.data = local;
          state.dataMode = local.dataMode || "partial";
          state.connected = true;
          return { ok: true, dataMode: state.dataMode, data: local, source: "local" };
        }
        state.connected = false;
        if (allowMockFallback() && global.__MAIOS_MOCK__) {
          state.data = global.__MAIOS_MOCK__();
          state.dataMode = "mock";
        } else {
          state.data = null;
          state.dataMode = "empty";
        }
        return { ok: false, dataMode: state.dataMode, data: state.data, error: String(e) };
      }
    },

    /** Trigger deep system scan on the local runtime (setup/onboarding). */
    async runSetupScan() {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/setup/scan", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: "{}",
          signal: AbortSignal.timeout(8000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    /** Poll scan progress from runtime. */
    async scanStatus() {
      try {
        const res = await fetch(RUNTIME + "/api/scan/status", {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(4000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    /** Tell the runtime which folder(s) to scan (business folder), then scan. */
    async setScanFolders(folders) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/scan/folders", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ folders: folders || [] }),
          signal: AbortSignal.timeout(12000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    async listDevices() {
      try {
        return await api("/api/devices");
      } catch (e) {
        return [];
      }
    },

    async decide(decisionId, action) {
      try {
        return await api("/api/decisions/action", {
          method: "POST",
          body: JSON.stringify({ decision_id: decisionId, action }),
        });
      } catch (e) {
        return null;
      }
    },

    /** STRATI — Detector de Oportunidades de Crecimiento (vista Oportunidades). */
    async getOpportunities() {
      try {
        return await runtimeApi("/api/opportunities", { timeoutMs: 8000 });
      } catch (e) {
        return null;
      }
    },

    /** SPEC §4.1 — CTA "Marcar como hecha" de una oportunidad (action-loop). */
    async markOpportunityDone(opportunity) {
      try {
        return await runtimeApi("/api/opportunities/done", {
          method: "POST",
          body: JSON.stringify({ opportunity }),
          timeoutMs: 8000,
        });
      } catch (e) {
        return null;
      }
    },

    /** PRODUCT LEAP — Recomendaciones seguidas (ciclo recomendar→actuar→medir). */
    async getRecommendations() {
      try {
        return await runtimeApi("/api/recommendations", { timeoutMs: 8000 });
      } catch (e) {
        return null;
      }
    },

    /** SPEC STRATI §4.4 — total capturado en € (ROI visible de retención). */
    async getRecommendationsImpact() {
      try {
        return await runtimeApi("/api/recommendations/impact", { timeoutMs: 8000 });
      } catch (e) {
        return null;
      }
    },

    async setRecommendationStatus(id, status) {
      try {
        return await runtimeApi("/api/recommendations/status", {
          method: "POST",
          body: JSON.stringify({ id: id, status: status }),
          timeoutMs: 8000,
        });
      } catch (e) {
        return null;
      }
    },

    /** PRODUCT LEAP — Action Center: preparar entregables (solo lectura + audit). */
    async prepareAction(kind) {
      try {
        return await runtimeApi("/api/actions/prepare", {
          method: "POST",
          body: JSON.stringify({ kind: kind }),
          timeoutMs: 10000,
        });
      } catch (e) {
        return null;
      }
    },

    async onboardingComplete(company, companyKey) {
      try {
        return await api("/api/onboarding/complete", {
          method: "POST",
          body: JSON.stringify({ company: company || "", company_key: companyKey || "" }),
        });
      } catch (e) {
        return null;
      }
    },

    async getCompany() {
      try {
        return await api("/api/company");
      } catch (e) {
        return { company: "MOOVING PAPER", company_key: "MOOVING" };
      }
    },

    async onboardingStatus() {
      try {
        return await api("/api/onboarding/status");
      } catch (e) {
        return null;
      }
    },

    /** Local runtime setup flag (maios.json) — survives cloud DB resets. */
    async localSetupStatus() {
      const fetchOnce = async () => {
        const res = await fetch(RUNTIME + "/api/setup/status", {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(5000),
        });
        if (!res.ok) return null;
        return await res.json();
      };
      try {
        let data = await fetchOnce();
        if (!data) {
          await new Promise(function (r) {
            setTimeout(r, 400);
          });
          data = await fetchOnce();
        }
        return data;
      } catch (e) {
        return null;
      }
    },

    /** Report whether the local Hermes CLI/agent is connected (via connector). */
    async hermesStatus() {
      try {
        const local = await runtimeApi("/api/hermes/chat-ready", { timeoutMs: 5000 });
        if (local && local.ready) {
          return {
            connected: true,
            status: "online",
            chatReady: true,
            source: "runtime",
            aiProvider: local.aiProvider,
            model: local.model,
          };
        }
      } catch (e) {}
      try {
        const d = await api("/api/dashboard");
        return d && d.hermes ? d.hermes : { connected: false };
      } catch (e) {
        return null;
      }
    },

    /** Queue a question for Hermes. Prefers local runtime (NVIDIA/Ollama via Hermes CLI). */
    async askHermes(message, conversationId) {
      const payload = { message, conversation_id: conversationId || "" };
      let runtimeErr = null;
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const local = await runtimeApi("/api/hermes/ask", {
            method: "POST",
            body: JSON.stringify(payload),
            timeoutMs: attempt === 0 ? 8000 : 15000,
          });
          if (local && local.id) return local;
          if (local && local.error) return { error: local.error };
        } catch (e) {
          runtimeErr = e;
          if (attempt === 0) {
            await new Promise(function (r) {
              setTimeout(r, 800);
            });
            continue;
          }
        }
        break;
      }
      if (runtimeErr) {
        const runtimeMsg = runtimeErr.message || String(runtimeErr);
        try {
          const ready = await runtimeApi("/api/hermes/chat-ready", { timeoutMs: 5000 });
          if (ready && ready.ready) {
            return {
              error:
                "Runtime activo pero Hermes no respondió a tiempo. Inténtalo de nuevo — no es un fallo del Connector.",
            };
          }
        } catch (e) {}
        if (!state.token) {
          return {
            error:
              runtimeMsg.indexOf("fetch") !== -1 || runtimeMsg.indexOf("Runtime") !== -1
                ? "Runtime no disponible (puerto 8765). Reinicia MAIOS desde Diagnóstico."
                : runtimeMsg,
          };
        }
      }
      if (!state.token) {
        return {
          error:
            "Sesión no autenticada y runtime local no respondió. Reinicia MAIOS o inicia sesión de nuevo.",
        };
      }
      try {
        return await api("/api/hermes/ask", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } catch (e) {
        return { error: e.message || "Cloud no disponible — puerto 8000" };
      }
    },

    /** List past Hermes conversations (runtime first, then cloud). */
    async hermesConversations() {
      try {
        const local = await runtimeApi("/api/hermes/conversations");
        if (Array.isArray(local)) return local;
      } catch (e) {}
      try {
        return await api("/api/hermes/conversations");
      } catch (e) {
        return [];
      }
    },

    /** Get the message history of a conversation. */
    async hermesConversationMessages(convId) {
      try {
        const local = await runtimeApi("/api/hermes/conversations/" + convId + "/messages");
        if (Array.isArray(local)) return local;
      } catch (e) {}
      try {
        return await api("/api/hermes/conversations/" + convId + "/messages");
      } catch (e) {
        return [];
      }
    },

    /** Get products from runtime (organized files + Shopify). */
    async getProducts() {
      try {
        const local = await runtimeApi("/api/products");
        if (local && Array.isArray(local.products) && local.products.length) {
          return local;
        }
      } catch (e) {}
      try {
        return await api("/api/products");
      } catch (e) {
        return null;
      }
    },

    /** Add a product manually to the local/cloud catalog. */
    async addProduct(product) {
      let lastError = "";
      const body = {
        name: (product && product.name) || "",
        sku: (product && product.sku) || "",
        netPrice: product && product.netPrice != null ? product.netPrice : null,
        rrp: product && product.rrp != null ? product.rrp : null,
      };

      try {
        const runtime = await runtimeApi("/api/products/add", {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (runtime && runtime.ok) {
          if (state.token) {
            api("/api/products/add", {
              method: "POST",
              body: JSON.stringify(body),
            }).catch(function () {});
          }
          return runtime;
        }
        lastError = (runtime && runtime.error) || "El runtime no confirmó el producto";
      } catch (e) {
        if (e.status === 404) {
          lastError =
            "El runtime no expone /api/products/add — reinicia el runtime desde Diagnósticos";
        } else {
          lastError = e.message || String(e);
        }
      }

      if (state.token) {
        try {
          const cloud = await api("/api/products/add", {
            method: "POST",
            body: JSON.stringify(body),
          });
          if (cloud && cloud.ok) return cloud;
          if (cloud && cloud.error) lastError = cloud.error;
        } catch (e) {
          if (!lastError) lastError = e.message || String(e);
        }
      }

      return { ok: false, error: lastError || "No se pudo añadir el producto" };
    },

    /** Get sales/orders from runtime (organized files + Shopify). */
    async getSales() {
      try {
        return await runtimeApi("/api/sales");
      } catch (e) {
        return null;
      }
    },

    /** FASE 4/7 — canonical financial overview (server-computed only; the UI
        never recalculates business metrics). */
    async getFinanceOverview() {
      try {
        return await runtimeApi("/api/finance/overview");
      } catch (e) {
        return null;
      }
    },

    /** FASE 8 — business intelligence findings (deterministic engine). */
    async getBusinessFindings(status) {
      try {
        const q = status ? "?status=" + encodeURIComponent(status) : "";
        return await runtimeApi("/api/business/findings" + q);
      } catch (e) {
        return null;
      }
    },

    async analyzeBusiness() {
      try {
        return await runtimeApi("/api/business/analyze", { method: "POST" });
      } catch (e) {
        return null;
      }
    },

    async setFindingStatus(id, status) {
      try {
        return await runtimeApi("/api/business/findings/status", {
          method: "POST",
          body: JSON.stringify({ id: id, status: status }),
        });
      } catch (e) {
        return null;
      }
    },

    /** FASE 13 (P10) — «Fuentes de datos»: conectores + capabilities. */
    async getSources() {
      try {
        return await runtimeApi("/api/sources");
      } catch (e) {
        return null;
      }
    },

    /** FASE 11 — DATA QUALITY: cobertura de coste e identidad (canónica). */
    async getCoverage() {
      try {
        return await runtimeApi("/api/products/coverage");
      } catch (e) {
        return null;
      }
    },

    /** FASE 14 — Salud de los datos (estados de calidad por entidad). */
    async getDataHealth() {
      try {
        return await runtimeApi("/api/data-health");
      } catch (e) {
        return null;
      }
    },

    /** FASE 14 — auditoría de integridad manual (POST, requiere auth). */
    async runIntegrityCheck() {
      try {
        return await runtimeApi("/api/data/integrity", { method: "POST" });
      } catch (e) {
        return null;
      }
    },

    /** FASE 11 (P4) — conciliación de identidad de producto. */
    async getProductReconciliation() {
      try {
        return await runtimeApi("/api/products/reconciliation");
      } catch (e) {
        return null;
      }
    },

    /** FASE 11 (P5) — mapping manual verificado (relación de identidad). */
    async saveProductMapping(shopifySku, canonicalProductId) {
      try {
        return await runtimeApi("/api/products/match", {
          method: "POST",
          body: JSON.stringify({
            shopifySku: shopifySku,
            canonicalProductId: canonicalProductId,
            matchMethod: "manual",
            confidence: 1.0,
          }),
        });
      } catch (e) {
        return null;
      }
    },

    /** FASE 11 (P5) — eliminar un mapping manual. */
    async removeProductMapping(shopifySku) {
      try {
        return await runtimeApi("/api/products/match/remove", {
          method: "POST",
          body: JSON.stringify({ shopifySku: shopifySku }),
        });
      } catch (e) {
        return null;
      }
    },

    /** FASE 12 (P4) — exportar la reconciliación (CSV/JSON, solo lectura). */
    async exportReconciliation(fmt = "json") {
      try {
        const r = await runtimeApi("/api/products/reconciliation/export?format=" + encodeURIComponent(fmt));
        if (!r || !r.ok) return null;
        const blob = new Blob([fmt === "csv" ? r.content : JSON.stringify(r.items, null, 2)], {
          type: fmt === "csv" ? "text/csv" : "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "vanova-reconciliacion." + fmt;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        return { ok: true, rows: r.rows };
      } catch (e) {
        return null;
      }
    },

    /** FASE 12 (P3) — confirmar varios mappings a la vez (grupo seleccionado). */
    async saveProductMappingBulk(pairs) {
      try {
        let ok = 0;
        let failed = 0;
        for (const p of pairs || []) {
          const r = await this.saveProductMapping(p.shopifySku, p.canonicalProductId);
          if (r && r.ok) ok += 1;
          else failed += 1;
        }
        return { ok: true, applied: ok, failed };
      } catch (e) {
        return null;
      }
    },

    /** FASE 12 (P2) — ignorar un SKU de venta (nunca vincular; revisable). */
    async ignoreProductSku(shopifySku) {
      try {
        return await runtimeApi("/api/products/ignore", {
          method: "POST",
          body: JSON.stringify({ shopifySku: shopifySku }),
        });
      } catch (e) {
        return null;
      }
    },

    /** FASE 12 (P2) — quitar un SKU de la lista de ignorados. */
    async unignoreProductSku(shopifySku) {
      try {
        return await runtimeApi("/api/products/ignore/remove", {
          method: "POST",
          body: JSON.stringify({ shopifySku: shopifySku }),
        });
      } catch (e) {
        return null;
      }
    },

    /** FASE 12 (P3) — recuperar la identidad de variante desde Shopify. */
    async recoverVariantIdentity() {
      try {
        return await runtimeApi("/api/shopify/identity-recovery", {
          method: "POST",
          body: JSON.stringify({}),
        });
      } catch (e) {
        return null;
      }
    },

    /** FASE 12 (P6) — PREVIEW del importador de costes (nunca escribe). */
    async previewCostsImport(rows, costSource) {
      try {
        return await runtimeApi("/api/costs/import", {
          method: "POST",
          body: JSON.stringify({ rows: rows, costSource: costSource, preview: true }),
        });
      } catch (e) {
        return null;
      }
    },

    /** FASE 12 (P6) — CONFIRM → IMPORT de costes (backup automático). */
    async importCosts(rows, costSource) {
      try {
        return await runtimeApi("/api/costs/import", {
          method: "POST",
          body: JSON.stringify({ rows: rows, costSource: costSource, preview: false }),
        });
      } catch (e) {
        return null;
      }
    },

    /** Get normalized customers (explicit customer exports + orders). */
    async getCustomers() {
      try {
        const local = await runtimeApi("/api/customers");
        if (local && Array.isArray(local.customers)) return local;
      } catch (e) {}
      try {
        return await api("/api/customers");
      } catch (e) {
        return null;
      }
    },

    /** Shopify background sync status. */
    async getShopifySyncStatus() {
      try {
        return await runtimeApi("/api/shopify/sync/status");
      } catch (e) {
        return null;
      }
    },

    /** Real Hermes email-skill status for the connected Gmail account. */
    async getGmailSkillStatus() {
      try {
        return await runtimeApi("/api/gmail/skill/status");
      } catch (e) {
        return null;
      }
    },

    /** Mark setup complete in maios.json (single source of truth). */
    async markSetupComplete() {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/setup/complete", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: "{}",
          signal: AbortSignal.timeout(12000),
        });
        if (res.ok) {
          try {
            localStorage.setItem("maios_setup_done", "1");
          } catch (e) {}
          return res.json();
        }
      } catch (e) {}
      return null;
    },

    /** Task queue status from local runtime. */
    async loadTasks() {
      try {
        const data = await runtimeApi("/api/tasks");
        return data && Array.isArray(data.tasks)
          ? Object.assign({ ok: true }, data)
          : Object.assign({ ok: false, tasks: null }, data || {});
      } catch (e) {
        // Never turn a temporary runtime outage into an empty task history.
        return { ok: false, tasks: null, queued: null, running: null, pendingApprovals: null };
      }
    },

    /** Single task detail + event log (live view in the Tasks modal). */
    async loadTaskDetail(taskId) {
      try {
        return await runtimeApi("/api/tasks/" + encodeURIComponent(taskId));
      } catch (e) {
        return { task: null, events: [] };
      }
    },
    async loadTaskEvents(taskId) {
      try {
        return await runtimeApi("/api/tasks/" + encodeURIComponent(taskId) + "/events");
      } catch (e) {
        return { task: null, events: [] };
      }
    },

    /** Agent routine reports (autonomous work) — the real Insights feed. */
    async loadInsights() {
      try {
        return await runtimeApi("/api/insights");
      } catch (e) {
        return [];
      }
    },

    /** Files the scanner is unsure about — pending human approval. */
    async loadFileCandidates() {
      try {
        return await runtimeApi("/api/files/candidates");
      } catch (e) {
        return { files: [], count: 0 };
      }
    },

    async decideFileCandidate(path, approve) {
      try {
        return await runtimeApi("/api/files/candidates/decide", {
          method: "POST",
          body: JSON.stringify({ path: path, approve: !!approve }),
          timeoutMs: 15000,
        });
      } catch (e) {
        return { ok: false, error: e.message || String(e) };
      }
    },

    async retryTask(taskId) {
      try {
        return await runtimeApi("/api/tasks/retry", {
          method: "POST",
          body: JSON.stringify({ taskId: taskId }),
          timeoutMs: 12000,
        });
      } catch (e) {
        return { ok: false, error: e.message || String(e) };
      }
    },

    getRealtimeState() {
      return { state: state.wsState, error: state.wsError };
    },

    async loadApprovals() {
      try {
        return await runtimeApi("/api/approvals");
      } catch (e) {
        return [];
      }
    },

    async loadCommandCenter() {
      try {
        return await runtimeApi("/api/command-center");
      } catch (e) {
        return null;
      }
    },

    async loadAutonomy() {
      try {
        return await runtimeApi("/api/autonomy");
      } catch (e) {
        return null;
      }
    },

    async setAutonomyLevel(level) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/autonomy", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ level }),
          signal: AbortSignal.timeout(15000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    async loadIntegrationLifecycle() {
      try {
        return await runtimeApi("/api/integrations/lifecycle");
      } catch (e) {
        return null;
      }
    },

    async disconnectIntegration(integrationId) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/integrations/disconnect", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ integrationId }),
          signal: AbortSignal.timeout(15000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    async syncShopifyNow() {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/shopify/sync", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: "{}",
          signal: AbortSignal.timeout(120000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    async runBackup() {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/backups/run", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ reason: "manual" }),
          signal: AbortSignal.timeout(30000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    async getBackupStatus() {
      try {
        return await runtimeApi("/api/backups/status");
      } catch (e) {
        return null;
      }
    },

    async restorePreUpdateBackup(backupId) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/backups/restore", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ id: backupId }),
          signal: AbortSignal.timeout(30000),
        });
        return res.json();
      } catch (e) {
        return { ok: false, error: (e && e.message) || "No se pudo restaurar la copia" };
      }
    },

    async decideApproval(approvalId, decision) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/approvals/decide", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ approvalId, decision }),
          signal: AbortSignal.timeout(15000),
        });
        return res.ok ? res.json() : null;
      } catch (e) {
        return null;
      }
    },

    /** Get the scanned data files from the owner's PC. Merges cloud + runtime; runtime wins on path conflict. */
    async getFiles() {
      let cloud = null;
      let runtime = null;

      if (state.token) {
        try {
          cloud = await api("/api/files");
        } catch (e) {}
      }
      try {
        runtime = await runtimeApi("/api/files");
      } catch (e) {}

      const cloudFiles = cloud && Array.isArray(cloud.files) ? cloud.files : [];
      const runtimeFiles = runtime && Array.isArray(runtime.files) ? runtime.files : [];

      if (!cloudFiles.length && !runtimeFiles.length) {
        if (runtime) return runtime;
        if (cloud) return cloud;
        return null;
      }

      // BUG-032: el runtime es la autoridad local. Si el sync cloud de
      // removeFile falló (best-effort), el snapshot cloud sigue teniendo el
      // archivo eliminado y el merge de abajo lo reintroduciría. El runtime
      // expone sus scanExclusions (rutas que el usuario eliminó); filtrarlas
      // para que el archivo no vuelva a aparecer.
      const excluded = new Set(
        (runtime && Array.isArray(runtime.excluded) ? runtime.excluded : [])
          .map((p) => String(p || "").toLowerCase())
          .filter(Boolean)
      );

      const byPath = new Map();
      const keyOf = (f) => (f.path || f.name || "").toLowerCase();

      const addAll = (list) => {
        for (const f of list) {
          const k = keyOf(f);
          if (!k) continue;
          if (excluded.has(k)) continue;
          byPath.set(k, f);
        }
      };
      addAll(cloudFiles);
      for (const f of runtimeFiles) {
        const k = keyOf(f);
        if (!k) continue;
        if (excluded.has(k)) continue;
        byPath.set(k, Object.assign({}, byPath.get(k) || {}, f));
      }

      return { files: Array.from(byPath.values()) };
    },

    /** Add a file to the scanned inventory. Runtime is primary; cloud sync is best-effort. */
    async addFile(file) {
      let lastError = "";

      try {
        const runtime = await runtimeApi("/api/files/add", {
          method: "POST",
          body: JSON.stringify(file),
        });
        if (runtime && runtime.ok) {
          if (state.token) {
            api("/api/files/add", {
              method: "POST",
              body: JSON.stringify(file),
            }).catch(function () {});
          }
          return runtime;
        }
        lastError = (runtime && runtime.error) || "El runtime no confirmó la importación";
      } catch (e) {
        if (e.status === 404) {
          lastError =
            "El runtime no expone /api/files/add — reinicia el runtime desde Diagnósticos";
        } else {
          lastError = e.message || String(e);
        }
      }

      if (state.token) {
        try {
          const cloud = await api("/api/files/add", {
            method: "POST",
            body: JSON.stringify(file),
          });
          if (cloud && cloud.ok) return cloud;
          if (cloud && cloud.error) lastError = cloud.error;
        } catch (e) {
          if (!lastError) lastError = e.message || String(e);
        }
      }

      return { ok: false, error: lastError || "No se pudo importar el archivo" };
    },

    /** Remove a file from the scanned inventory. Runtime is primary; cloud sync is best-effort. */
    async removeFile(path) {
      let lastError = "";

      try {
        const runtime = await runtimeApi("/api/files/remove", {
          method: "POST",
          body: JSON.stringify({ path }),
        });
        if (runtime && runtime.ok) {
          if (state.token) {
            api("/api/files/remove", {
              method: "POST",
              body: JSON.stringify({ path }),
            }).catch(function () {});
          }
          return runtime;
        }
        lastError = (runtime && runtime.error) || "El runtime no confirmó la eliminación";
      } catch (e) {
        if (e.status === 404) {
          lastError =
            "El runtime no expone /api/files/remove — reinicia el runtime desde Diagnósticos";
        } else {
          lastError = e.message || String(e);
        }
      }

      if (state.token) {
        try {
          const cloud = await api("/api/files/remove", {
            method: "POST",
            body: JSON.stringify({ path }),
          });
          if (cloud && cloud.ok) return cloud;
          if (cloud && cloud.error) lastError = cloud.error;
        } catch (e) {
          if (!lastError) lastError = e.message || String(e);
        }
      }

      return { ok: false, error: lastError || "No se pudo eliminar el archivo" };
    },

    /** Get the recorded actions on insights (approved/rejected/dismissed). */
    async getInsightActions() {
      // Cloud is the cross-device fallback. Runtime is authoritative for this
      // installation, and browser storage is only the last-resort fallback
      // used while the runtime is restarting.
      const merged = {};
      if (state.token) {
        try {
          const cloud = await api("/api/insight-actions");
          if (cloud && typeof cloud === "object") Object.assign(merged, cloud);
        } catch (e) {}
      }
      try {
        const browser = readInsightActionsLocal();
        if (browser && typeof browser === "object") Object.assign(merged, browser);
      } catch (e) {}
      try {
        const local = await runtimeApi("/api/insight-actions");
        if (local && typeof local === "object" && !local.error) {
          Object.assign(merged, local);
        }
      } catch (e) {}
      return merged;
    },

    /** Record an action on an insight. */
    async setInsightAction(insightId, action) {
      if (!insightId) return { ok: false, error: "Falta el identificador del insight" };
      if (!VALID_INSIGHT_ACTIONS.has(action)) {
        return { ok: false, error: "Acción no válida: " + action };
      }

      let lastError = "";
      let runtimeResult = null;
      try {
        const local = await runtimeApi("/api/insight-actions", {
          method: "POST",
          body: JSON.stringify({ insight_id: insightId, action }),
        });
        if (local && local.ok) runtimeResult = local;
        if (local && local.error) lastError = local.error;
      } catch (e) {
        lastError = e.message || String(e);
        // Keep going to the cloud fallback for older runtimes. Browser storage
        // is used only after both canonical stores have been attempted.
      }

      if (state.token) {
        try {
          const cloud = await api("/api/insight-actions", {
            method: "POST",
            body: JSON.stringify({ insight_id: insightId, action }),
          });
          if (cloud && cloud.ok) {
            // Keep the local success as the immediate source of truth while
            // also confirming that other devices will receive the decision.
            return Object.assign({}, runtimeResult || cloud, { cloudSynced: true });
          }
          if (cloud && cloud.error) lastError = cloud.error;
        } catch (e) {
          lastError = e.message || String(e);
        }
      }

      if (runtimeResult) return runtimeResult;
      try {
        return writeInsightActionLocal(insightId, action);
      } catch (e) {
        return {
          ok: false,
          error: lastError || "No se pudo guardar la acción (runtime ni nube disponibles)",
        };
      }
    },

    /** Save the FacturaScript connection config. */
    /** Save the FacturaScript connection config (runtime local + cloud sync). */
    async saveFacturaScript(cfg) {
      return this.saveIntegration("facturascript", cfg);
    },

    /** Get the FacturaScript connection status. */
    async getFacturaScriptConfig() {
      return this.getIntegration("facturascript");
    },

    /** Post-update data validation (beta.3). */
    async dataVersionStatus() {
      try {
        return await runtimeApi("/api/data/version");
      } catch (e) {
        return null;
      }
    },
    async reimportData() {
      try {
        return await runtimeApi("/api/data/reimport", {
          method: "POST",
          body: JSON.stringify({}),
        });
      } catch (e) {
        return { ok: false, error: (e && e.message) || "Runtime no disponible" };
      }
    },
    async dismissDataReview() {
      try {
        return await runtimeApi("/api/data/review/dismiss", {
          method: "POST",
          body: JSON.stringify({}),
        });
      } catch (e) {
        return null;
      }
    },
    async rearmDataReview() {
      try {
        return await runtimeApi("/api/data/review/rearm", {
          method: "POST",
          body: JSON.stringify({}),
        });
      } catch (e) {
        return null;
      }
    },

    /** Save the Google Drive connection config (runtime local + cloud sync). */
    async saveDrive(cfg) {
      return this.saveIntegration("drive", cfg);
    },

    /** Get the Google Drive connection status. */
    async getDriveConfig() {
      return this.getIntegration("drive");
    },

    /** Save config for a generic integration (shopify, erp, mcp, email, instagram). */
    async saveIntegration(id, cfg) {
      const body = normalizeIntegrationConfig(id, cfg);
      let lastError = "";
      let runtimeUnavailable = false;

      try {
        const local = await runtimeApi("/api/integrations/" + id + "/config", {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (local && local.ok) {
          writeIntegrationLocal(id, body);
          return local;
        }
        if (local && local.error) lastError = local.error;
      } catch (e) {
        lastError = e.message || String(e);
        runtimeUnavailable = !e.status || e.status === 404 || e.status === 503;
        if (runtimeUnavailable) {
          const saved = writeIntegrationLocal(id, body);
          if (saved.ok) return saved;
          lastError = saved.error || lastError;
        }
      }

      if (state.token) {
        try {
          const cloud = await api("/api/integrations/" + id + "/config", {
            method: "POST",
            body: JSON.stringify(body),
          });
          if (cloud && cloud.ok) return cloud;
          if (cloud && cloud.error) lastError = cloud.error;
        } catch (e) {
          lastError = e.message || String(e);
        }
      }

      try {
        const saved = writeIntegrationLocal(id, body);
        if (saved.ok) return saved;
        return { ok: false, error: saved.error || lastError || "No se pudo guardar la configuración" };
      } catch (e) {
        return {
          ok: false,
          error: lastError || e.message || "No se pudo guardar la configuración",
        };
      }
    },

    /** Test an integration connection with the given config (no persistence). */
    async testIntegration(id, cfg, mode) {
      try {
        return await runtimeApi("/api/integrations/test", {
          method: "POST",
          body: JSON.stringify({ integrationId: id, config: cfg || {}, mode: mode || "web" }),
        });
      } catch (e) {
        return { ok: false, error: (e && e.message) || "El runtime no está disponible" };
      }
    },

    /** Mark an item (task/insight) as important for the agents. */
    async markImportant(kind, refId, title, body, agentId) {
      try {
        return await runtimeApi("/api/important/mark", {
          method: "POST",
          body: JSON.stringify({ kind, refId, title, body, agentId: agentId || "" }),
        });
      } catch (e) {
        return { ok: false, error: (e && e.message) || "El runtime no está disponible" };
      }
    },

    /** Remove an item from the curated important knowledge store. */
    async unmarkImportant(kind, refId) {
      try {
        return await runtimeApi("/api/important/unmark", {
          method: "POST",
          body: JSON.stringify({ kind, refId }),
        });
      } catch (e) {
        return { ok: false, error: e.message || String(e) };
      }
    },

    /** List items marked as important. */
    async listImportant() {
      try {
        return await runtimeApi("/api/important");
      } catch (e) {
        return { items: [] };
      }
    },

    /** Get the Hermes prompt to connect an integration (so the user can ask Hermes). */
    async hermesIntegrationPrompt(id, cfg, mode) {
      try {
        return await runtimeApi("/api/integrations/hermes-prompt", {
          method: "POST",
          body: JSON.stringify({ integrationId: id, config: cfg || {}, mode: mode || "web" }),
        });
      } catch (e) {
        return { error: (e && e.message) || "El runtime no está disponible" };
      }
    },

    /** Get config for a generic integration. */
    async getIntegration(id) {
      const merged = getIntegrationLocal(id);
      try {
        const local = await runtimeApi("/api/integrations/" + id + "/config");
        if (local && (local.connected || local.url || local.tokenSet)) {
          return sanitizeIntegrationStatus(id, Object.assign({}, merged, local));
        }
      } catch (e) {
        if (merged.connected) {
          return sanitizeIntegrationStatus(id, merged);
        }
      }
      if (state.token) {
        try {
          const cloud = await api("/api/integrations/" + id + "/config");
          if (cloud && cloud.connected) {
            return sanitizeIntegrationStatus(id, cloud);
          }
        } catch (e) {}
      }
      return sanitizeIntegrationStatus(id, merged.connected ? merged : { connected: false });
    },

    /** List pending guardrail approvals (destructive agent actions). */
    async getGuardrails() {
      try {
        return await api("/api/guardrails");
      } catch (e) {
        return [];
      }
    },

    /** Approve or deny a guardrail. */
    async decideGuardrail(id, decision) {
      try {
        return await api("/api/guardrails/decide", {
          method: "POST",
          body: JSON.stringify({ id, decision }),
        });
      } catch (e) {
        return null;
      }
    },

    /** Poll the status/result of a Hermes request (runtime first). */
    async hermesRequestStatus(reqId) {
      try {
        const local = await runtimeApi("/api/hermes/requests/" + reqId, { timeoutMs: 15000 });
        if (local && local.id) return local;
      } catch (e) {}
      try {
        return await api("/api/hermes/requests/" + reqId);
      } catch (e) {
        return null;
      }
    },

    /** Local Hermes chat readiness (CLI + AI provider). */
    async hermesChatReady() {
      try {
        return await runtimeApi("/api/hermes/chat-ready");
      } catch (e) {
        return { ready: false, error: e.message || String(e) };
      }
    },

    /** Live activity steps (organize, Shopify sync, chat). */
    async getHermesActivity() {
      try {
        return await runtimeApi("/api/hermes/activity", { timeoutMs: 8000 });
      } catch (e) {
        return { current: "", log: [] };
      }
    },

    /** Structured MAIOS operational context (same facts as Hermes CLI). */
    async getHermesOperationalContext() {
      try {
        return await runtimeApi("/api/hermes/operational-context", { timeoutMs: 10000 });
      } catch (e) {
        return null;
      }
    },

    /** UI preferences persisted in maios.json (runtime). */
    async getUiPrefs() {
      let localPrefs = {};
      try {
        const raw = localStorage.getItem("vanova-ui-prefs");
        const parsed = raw ? JSON.parse(raw) : {};
        if (parsed && typeof parsed === "object") localPrefs = parsed;
        const legacyFont = localStorage.getItem("vanova-font-family");
        if (legacyFont && !localPrefs.fontFamily) localPrefs.fontFamily = legacyFont;
      } catch (e) {}
      try {
        const runtime = await runtimeApi("/api/ui/prefs", { timeoutMs: 5000 });
        // The local browser preference is the latest user action on this
        // installation. Keep it over a stale runtime value after an update;
        // the runtime remains the durable backup when localStorage is empty.
        return Object.assign({}, runtime || {}, { uiPrefs: Object.assign({}, (runtime && runtime.uiPrefs) || {}, localPrefs) });
      } catch (e) {
        return { architectureDismissed: false, uiPrefs: localPrefs };
      }
    },

    /** Persist non-business UI preferences in the local runtime. */
    async saveUiPrefs(prefs) {
      try {
        try {
          localStorage.setItem("vanova-ui-prefs", JSON.stringify(prefs || {}));
          if (prefs && prefs.fontFamily) localStorage.setItem("vanova-font-family", String(prefs.fontFamily));
        } catch (e) {}
        return await runtimeApi("/api/ui/prefs", {
          method: "POST",
          body: JSON.stringify({ uiPrefs: prefs || {} }),
          timeoutMs: 8000,
        });
      } catch (e) {
        return { ok: false, error: e.message || String(e) };
      }
    },

    /** Dismiss Hermes architecture onboarding card (once per user). */
    async dismissArchitecture() {
      try {
        return await runtimeApi("/api/ui/dismiss-architecture", {
          method: "POST",
          body: JSON.stringify({}),
          timeoutMs: 8000,
        });
      } catch (e) {
        return { ok: false };
      }
    },

    /** Pre-warm Hermes service + cache chat-ready state (runtime local first). */
    async warmHermesChat() {
      try {
        const warm = await runtimeApi("/api/hermes/warm", {
          method: "POST",
          body: JSON.stringify({}),
          timeoutMs: 20000,
        });
        if (warm && (warm.ready != null || warm.chatReady != null)) return warm;
      } catch (e) {}
      return this.hermesChatReady();
    },

    /** AI provider status from runtime (reads Hermes config.yaml + maios.json). */
    async getAiProviderStatus() {
      try {
        return await runtimeApi("/api/ai/status");
      } catch (e) {
        return { configured: false, provider: "Desconocido" };
      }
    },

    /** Full Hermes config: Ollama launch, NVIDIA, models. */
    async getHermesConfig() {
      try {
        return await runtimeApi("/api/hermes/config", { timeoutMs: 12000 });
      } catch (e) {
        return null;
      }
    },

    /** Switch primary model/provider in Hermes config.yaml. */
    async selectHermesProvider(providerId, model) {
      try {
        return await runtimeApi("/api/hermes/provider/select", {
          method: "POST",
          body: JSON.stringify({ providerId: providerId || "ollama-launch", model: model || "" }),
          timeoutMs: 15000,
        });
      } catch (e) {
        return { ok: false, error: e.message || String(e) };
      }
    },

    /**
     * Open the realtime channel. Calls onEvent(evt) for each push.
     * Returns a close() function. Reports state via state.wsState / getRealtimeState().
     */
    subscribe(onEvent) {
      if (typeof WebSocket === "undefined") return () => {};
      let closed = false;
      let ws = null;
      let reconnectTimer = null;
      let attempt = 0;
      const MAX_ATTEMPTS = 8;
      const BASE_DELAY_MS = 2000;
      const MAX_DELAY_MS = 60000;

      function setWsState(next, err) {
        state.wsState = next;
        state.wsError = err || null;
        if (global.MAIOSSystemStatus && typeof global.MAIOSSystemStatus.setRealtimeState === "function") {
          global.MAIOSSystemStatus.setRealtimeState(next, err || null);
        }
      }

      async function ensureFreshToken() {
        if (!state.token) return false;
        try {
          const r = await fetch(CONFIG.api + "/api/me", {
            headers: { Authorization: "Bearer " + state.token, Accept: "application/json" },
            signal: AbortSignal.timeout(5000),
          });
          if (r.ok) return true;
        } catch (e) {}
        return tryRefresh();
      }

      function scheduleReconnect(reason) {
        if (closed) return;
        if (attempt >= MAX_ATTEMPTS) {
          setWsState("disconnected", "Tiempo real no disponible — los datos pueden estar desactualizados.");
          return;
        }
        setWsState("reconnecting", reason || null);
        const delay = Math.min(BASE_DELAY_MS * Math.pow(2, attempt), MAX_DELAY_MS);
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      }

      async function connect() {
        if (closed) return;
        if (!state.token) {
          setWsState("disconnected", null);
          return;
        }
        setWsState("connecting", null);
        const ok = await ensureFreshToken();
        if (!ok) {
          setWsState("auth_failed", "Tiempo real no disponible — los datos pueden estar desactualizados.");
          return;
        }
        const proto = CONFIG.api.startsWith("https") ? "wss" : "ws";
        const base = CONFIG.api.replace(/^https?:\/\//, "");
        try {
          ws = new WebSocket(
            proto + "://" + base + "/ws/dashboard?token=" + encodeURIComponent(state.token)
          );
        } catch (e) {
          scheduleReconnect(String(e));
          return;
        }
        ws.onopen = () => {
          attempt = 0;
          setWsState("connected", null);
        };
        ws.onmessage = (evt) => {
          try {
            const data = JSON.parse(evt.data);
            if (data.type === "auth_failed") {
              setWsState("auth_failed", data.message || "Tiempo real no disponible — los datos pueden estar desactualizados.");
              try {
                ws.close();
              } catch (e) {}
              return;
            }
            if (data.type === "connected") {
              setWsState("connected", null);
              return;
            }
            if (data.type === "activity_update" && typeof onEvent === "function") onEvent(data);
            if (data.type === "pong") return;
          } catch (e) {}
        };
        ws.onerror = () => {
          if (!closed) scheduleReconnect("Error de conexión en tiempo real");
        };
        ws.onclose = (evt) => {
          if (closed) return;
          if (evt && evt.code === 4401) {
            setWsState("auth_failed", "Tiempo real no disponible — los datos pueden estar desactualizados.");
            return;
          }
          scheduleReconnect("Canal en tiempo real desconectado");
        };
      }

      connect();
      return () => {
        closed = true;
        if (reconnectTimer) clearTimeout(reconnectTimer);
        if (ws) {
          try {
            ws.close();
          } catch (e) {}
        }
        setWsState("disconnected", null);
      };
    },

    /** Runtime API agents (local config) — used when Cloud has no agent snapshot yet. */
    async loadRuntimeAgents() {
      const runtime = global.__MAIOS_RUNTIME__ || "http://127.0.0.1:8765";
      try {
        const res = await fetch(runtime + "/api/agents", {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(4000),
        });
        if (!res.ok) return { runtimeAvailable: false, agents: [] };
        const agents = await res.json();
        return { runtimeAvailable: true, agents: Array.isArray(agents) ? agents : [] };
      } catch (e) {
        return { runtimeAvailable: false, agents: [] };
      }
    },

    /** Full agent catalog (installed + available) from the runtime. */
    async loadAgentCatalog() {
      try {
        const res = await fetch(RUNTIME + "/api/agents/catalog", {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(4000),
        });
        if (!res.ok) return [];
        const data = await res.json();
        return Array.isArray(data) ? data : [];
      } catch (e) {
        return [];
      }
    },

    /** Add agents by catalog id (merges, never removes existing agents). */
    async addAgents(agentIds) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/agents/add", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ agentIds }),
          signal: AbortSignal.timeout(15000),
        });
        if (!res.ok) return null;
        return res.json();
      } catch (e) {
        return null;
      }
    },

    /** Trigger an installed agent to run its routine analysis now. */
    async runAgent(agentId) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/agents/run", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ agentId }),
          signal: AbortSignal.timeout(15000),
        });
        if (!res.ok) return null;
        return res.json();
      } catch (e) {
        return null;
      }
    },

    /** SISTEMA DE AGENTES MVP — crear un agente personalizado desde la UI. */
    async createCustomAgent(def) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/agents/custom", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify(def || {}),
          signal: AbortSignal.timeout(15000),
        });
        if (!res.ok) return null;
        return res.json();
      } catch (e) {
        return null;
      }
    },

    /** Delegate a task to an agent: now | once | recurring. */
    async createTask(task) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/tasks/create", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify(task || {}),
          signal: AbortSignal.timeout(15000),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) return { ok: false, error: (data && data.error) || "No se pudo crear la tarea" };
        return data;
      } catch (e) {
        return { ok: false, error: e.message || "Runtime no disponible" };
      }
    },

    /** Cancel a one-time or recurring delegated schedule. */
    async deleteTaskSchedule(scheduleId) {
      try {
        const auth = await runtimeAuthHeaders();
        const res = await fetch(RUNTIME + "/api/tasks/schedule/delete", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ scheduleId }),
          signal: AbortSignal.timeout(10000),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) return { ok: false, error: (data && data.error) || "No se pudo eliminar" };
        return data;
      } catch (e) {
        return { ok: false, error: e.message || "Runtime no disponible" };
      }
    },

    /** Scheduler status + next runs for the Agents view. */
    async loadAgentScheduler() {
      try {
        const res = await fetch(RUNTIME + "/api/agents/scheduler", {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(4000),
        });
        if (!res.ok) return null;
        return res.json();
      } catch (e) {
        return null;
      }
    },
  };

  // -----------------------------------------------------------
  // Bundled MOCK data (dev fallback). Exposed as __MAIOS_MOCK__
  // so DataServices can label it and views can render it.
  // -----------------------------------------------------------
  const AGENTS = [
    { id: "trend", name: "Trend Hunter", short: "TH", color: "#0ea5e9", status: "active", autonomyLevel: "auto", description: "Detects emerging stationery and licensing trends.", currentTask: "Monitoring 14 trend sources", insightsGenerated: 142, tasksCompleted: 389, lastActivity: "12 min ago" },
    { id: "licensing", name: "Licensing Intelligence", short: "LI", color: "#8b5cf6", status: "active", autonomyLevel: "approval", description: "Analyzes performance and risk of each license.", currentTask: "Evaluating license renewal", insightsGenerated: 87, tasksCompleted: 201, lastActivity: "28 min ago" },
    { id: "product", name: "Product Designer AI", short: "PD", color: "#f43f5e", status: "monitoring", autonomyLevel: "auto", description: "Proposes product designs and concepts.", currentTask: "Generating product concepts", insightsGenerated: 64, tasksCompleted: 152, lastActivity: "1 h ago" },
    { id: "pricing", name: "Pricing AI", short: "PR", color: "#f59e0b", status: "active", autonomyLevel: "approval", description: "Recommends optimal pricing and promotions.", currentTask: "Optimizing margins by family", insightsGenerated: 120, tasksCompleted: 267, lastActivity: "9 min ago" },
    { id: "sales", name: "Sales Copilot", short: "SC", color: "#22c55e", status: "active", autonomyLevel: "auto", description: "Assists in sales and opportunity detection.", currentTask: "Analyzing sales pipeline", insightsGenerated: 198, tasksCompleted: 412, lastActivity: "5 min ago" },
    { id: "forecast", name: "Forecast AI", short: "FC", color: "#3b82f6", status: "active", autonomyLevel: "auto", description: "Predicts demand and detects stockouts.", currentTask: "Updating demand for 24 products", insightsGenerated: 76, tasksCompleted: 188, lastActivity: "15 min ago" },
    { id: "factory", name: "Factory Optimizer", short: "FO", color: "#14b8a6", status: "monitoring", autonomyLevel: "auto", description: "Maximizes production line efficiency.", currentTask: "Optimizing production line", insightsGenerated: 41, tasksCompleted: 97, lastActivity: "2 h ago" },
    { id: "procurement", name: "Procurement AI", short: "PU", color: "#a855f7", status: "needs_attention", autonomyLevel: "approval", description: "Manages purchasing and supplier risk.", currentTask: "Supplier risk detected", insightsGenerated: 58, tasksCompleted: 134, lastActivity: "32 min ago" },
    { id: "marketing", name: "Marketing Studio AI", short: "MK", color: "#ec4899", status: "active", autonomyLevel: "approval", description: "Creates campaigns and marketing content.", currentTask: "Generating 6 campaign concepts", insightsGenerated: 153, tasksCompleted: 301, lastActivity: "20 min ago" },
    { id: "customer", name: "Customer Success AI", short: "CS", color: "#6366f1", status: "active", autonomyLevel: "auto", description: "Prevents churn and improves retention.", currentTask: "Analyzing customer satisfaction", insightsGenerated: 91, tasksCompleted: 244, lastActivity: "8 min ago" },
    { id: "finance", name: "Financial Intelligence", short: "FI", color: "#10b981", status: "active", autonomyLevel: "approval", description: "Financial analysis and anomaly detection.", currentTask: "Verifying August margins", insightsGenerated: 67, tasksCompleted: 156, lastActivity: "11 min ago" },
    { id: "ceo", name: "CEO Copilot", short: "CC", color: "#dc2626", status: "active", autonomyLevel: "human", description: "Executive synthesis for leadership.", currentTask: "Preparing executive brief", insightsGenerated: 54, tasksCompleted: 129, lastActivity: "3 min ago" },
  ];

  const MOCK = {
    dataMode: "mock",
    overview: {
      revenue: 284312, revenueChange: "+12.4%", revenueUp: true,
      orders: 1247, ordersChange: "+8.1%", ordersUp: true,
      grossMargin: 21.3, grossMarginChange: "-0.8%", grossMarginUp: false,
      customers: 8942, customersChange: "+4.2%", customersUp: true,
      inventoryValue: 1203450, inventoryChange: "-2.1%", inventoryUp: false,
    },
    priorities: [
      { id: "p1", agent: "Forecast AI", type: "risk", priority: "high", title: "Possible stockout detected for Mooving Planner A5", description: "Forecast indicates current stock does not cover projected demand for back-to-school.", impact: "€12,400", confidence: "94%", recommendation: "Increase order by 500 units.", status: "open" },
      { id: "p2", agent: "Trend Hunter", type: "opportunity", priority: "medium", title: "Pastel metallic stationery trending +34%", description: "Trend detected across monitored channels.", impact: "€8,100", confidence: "89%", recommendation: "Launch a pilot line and validate.", status: "open" },
    ],
    activity: [
      { id: "a1", agent: "Forecast AI", action: "Updated demand forecast for 24 products.", status: "completed" },
      { id: "a2", agent: "Marketing Studio AI", action: "Generated 6 campaign concepts for back-to-school.", status: "completed" },
      { id: "a3", agent: "Procurement AI", action: "Detected supplier risk.", status: "needs_attention" },
      { id: "a4", agent: "Trend Hunter", action: "Detected emerging stationery trend.", status: "completed" },
      { id: "a5", agent: "Hermes", action: "Completed daily business analysis.", status: "completed" },
    ],
    agents: AGENTS,
    decisions: [
      { id: "d1", title: "Increase order quantity for Mooving Planner A5?", recommendation: "+500 units", impact: "+€12,400 revenue", confidence: "91%", autonomyLevel: "approval", status: "pending", agent: "Forecast AI" },
      { id: "d2", title: "Reevaluate pricing for the Escolar family?", recommendation: "+4% margin", impact: "+€19,300", confidence: "88%", autonomyLevel: "approval", status: "pending", agent: "Financial Intelligence" },
    ],
    automations: [
      { id: "au1", name: "Daily Executive Brief", schedule: "Every day — 07:30", agent: "CEO Copilot", status: "active" },
      { id: "au2", name: "Demand Forecast", schedule: "Every day — 06:30", agent: "Forecast AI", status: "active" },
      { id: "au3", name: "Trend Monitoring", schedule: "Every 6 hours", agent: "Trend Hunter", status: "active" },
      { id: "au4", name: "Financial Analysis", schedule: "Every day — 07:00", agent: "Financial Intelligence", status: "active" },
      { id: "au5", name: "Marketing Content Generation", schedule: "Every Monday", agent: "Marketing Studio AI", status: "active" },
    ],
    sources: [
      { id: "sales", name: "Sales", status: "connected", source: "Shopify", recordCount: 1247, dataMode: "mock" },
      { id: "products", name: "Products", status: "connected", source: "Shopify", recordCount: 320, dataMode: "mock" },
      { id: "inventory", name: "Inventory", status: "connected", source: "Shopify", recordCount: 210, dataMode: "mock" },
      { id: "customers", name: "Customers", status: "connected", source: "Shopify", recordCount: 8942, dataMode: "mock" },
      { id: "production", name: "Production", status: "needs_configuration", source: "", recordCount: 0, dataMode: "empty" },
      { id: "logistics", name: "Logistics", status: "needs_configuration", source: "", recordCount: 0, dataMode: "empty" },
      { id: "finance", name: "Finance", status: "needs_configuration", source: "", recordCount: 0, dataMode: "empty" },
      { id: "marketing", name: "Marketing", status: "connected", source: "Instagram", recordCount: 86, dataMode: "mock" },
      { id: "licensing", name: "Licensing", status: "needs_configuration", source: "", recordCount: 0, dataMode: "empty" },
    ],
  };

  global.__MAIOS_MOCK__ = function () {
    return JSON.parse(JSON.stringify(MOCK));
  };
  global.__MAIOS_AGENTS__ = AGENTS;

  // Windows notification support
  DataServices.sendNotification = function(title, body) {
    return fetch(RUNTIME + '/api/notifications/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title || 'VANOVA', body: body || '' })
    }).then(function(r) { return r.json(); }).catch(function() { return { ok: false }; });
  };
})(window);
