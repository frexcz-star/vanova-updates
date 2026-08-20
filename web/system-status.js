/* MAIOS System Status — real-time health polling for dashboard UI */
(function (global) {
  "use strict";

  const RUNTIME = global.__MAIOS_RUNTIME__ || "http://127.0.0.1:8765";
  const POLL_MS = 30000;
  const DIAG_POLL_MS = 60000;
  const FETCH_TIMEOUT_MS = 8000;
  const DIAG_TOTAL_TIMEOUT_MS = 8000;
  const DIAG_FETCH_MS = Math.max(FETCH_TIMEOUT_MS + 4000, 12000);
  const IPC_TIMEOUT_MS = 2000;
  const AUTO_RECOVERY_AFTER_MS = 120000;
  const AUTO_RECOVERY_COOLDOWN_MS = 300000;
  const AUTO_RECOVERY_MAX_ATTEMPTS = 3;
  let diagLoadGen = 0;
  let diagPollTimer = null;
  let diagPanelReady = false;
  let lastBannerSignature = null;
  const autoRecovery = {
    cloudDownSince: null,
    connectorDownSince: null,
    lastAttempt: {},
    attemptCounts: {},
    inFlight: false,
    gaveUp: {},
  };

  const STALE_RUNTIME_MSG = "Runtime desactualizado — reiniciar";

  const state = {
    overall: "checking",
    components: {},
    ports: null,
    lastCheck: null,
    polling: false,
    runtimeAvailable: false,
    runtimeStale: false,
    runtimeReachable: false,
    lastError: null,
    diagLoading: false,
    diagError: null,
    realtimeState: "disconnected",
    realtimeError: null,
  };

  const REALTIME_LABELS = {
    connecting: "Conectando tiempo real…",
    connected: "Tiempo real activo",
    reconnecting: "Reconectando tiempo real…",
    disconnected: "Tiempo real desconectado",
    auth_failed: "Tiempo real no disponible",
  };

  function setRealtimeState(next, err) {
    state.realtimeState = next || "disconnected";
    state.realtimeError = err || null;
  }

  function fetchWithTimeout(url, options, ms) {
    const timeoutMs = ms || FETCH_TIMEOUT_MS;
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      return fetch(url, Object.assign({}, options || {}, { signal: AbortSignal.timeout(timeoutMs) }));
    }
    const controller = new AbortController();
    const timer = setTimeout(function () {
      controller.abort();
    }, timeoutMs);
    return fetch(url, Object.assign({}, options || {}, { signal: controller.signal })).finally(function () {
      clearTimeout(timer);
    });
  }

  function promiseWithTimeout(promise, ms, message) {
    return Promise.race([
      promise,
      new Promise(function (_, reject) {
        setTimeout(function () {
          reject(new Error(message || "Tiempo de espera agotado"));
        }, ms);
      }),
    ]);
  }

  function abortErrorMessage(e) {
    if (e && e.name === "AbortError") return "Tiempo de espera agotado — el servicio tardó demasiado en responder";
    const msg = String((e && e.message) || e || "Error de conexión");
    if (/ECONNREFUSED|Failed to fetch|NetworkError|fetch failed|ERR_CONNECTION/i.test(msg)) {
      return "VANOVA Runtime no responde — reinicia la aplicación o el servicio local";
    }
    if (/401|Unauthorized/i.test(msg)) return "Sesión expirada — vuelve a iniciar sesión";
    if (/429|rate limit|too many/i.test(msg)) return "Demasiadas solicitudes — espera un momento";
    return msg;
  }

  /** Runtime is healthy only when health, setup/configPath, and /api/files all respond. */
  async function probeRuntimeHealthy() {
    try {
      const healthRes = await fetchWithTimeout(RUNTIME + "/api/health", {}, FETCH_TIMEOUT_MS);
      if (!healthRes.ok) return { ok: false, reachable: false, reason: "health_http_" + healthRes.status };
      const health = await healthRes.json();
      if (!health || (health.service !== "vanova-desktop-runtime" && health.service !== "maios-desktop-runtime")) {
        return { ok: false, reachable: false, reason: "wrong_service" };
      }

      const setupRes = await fetchWithTimeout(RUNTIME + "/api/setup/status", {}, FETCH_TIMEOUT_MS);
      if (!setupRes.ok) {
        return { ok: false, reachable: true, stale: true, reason: "setup_http_" + setupRes.status };
      }
      const setup = await setupRes.json();
      if (!setup || !("configPath" in setup)) {
        return { ok: false, reachable: true, stale: true, reason: "missing_configPath" };
      }

      const filesRes = await fetchWithTimeout(RUNTIME + "/api/files", {}, FETCH_TIMEOUT_MS);
      // P2-1: /api/files exige token de instalación. Un 401 SIN token prueba
      // que el servidor está vivo y es NUESTRO runtime protegido — cuenta como
      // sano (mismo criterio que port_utils.probe_runtime). Antes este probe
      // marcaba cualquier runtime protegido como "desactualizado".
      if (filesRes.status !== 200 && filesRes.status !== 401) {
        return { ok: false, reachable: true, stale: true, reason: "files_http_" + filesRes.status };
      }

      return { ok: true, reachable: true, stale: false };
    } catch (e) {
      return { ok: false, reachable: false, reason: "unreachable", error: abortErrorMessage(e) };
    }
  }

  function staleRuntimeComponent() {
    return {
      status: "warning",
      label: "Runtime",
      message: STALE_RUNTIME_MSG,
      action: "restart",
      stale: true,
    };
  }

  function applyStaleRuntimeState(partialComponents) {
    state.runtimeAvailable = false;
    state.runtimeStale = true;
    state.runtimeReachable = true;
    state.overall = "degraded";
    state.components = Object.assign({}, partialComponents || {}, {
      runtime: staleRuntimeComponent(),
    });
    state.lastError = STALE_RUNTIME_MSG + " (faltan /api/files o configPath)";
    state.lastCheck = Date.now();
    state.ports = {
      overall: "degraded",
      runtime: {
        port: 8765,
        label: "Runtime",
        status: "offline",
        message: STALE_RUNTIME_MSG,
        hint: "Reinicia el runtime desde Diagnóstico para habilitar importación de archivos.",
      },
    };
    return { overall: state.overall, components: state.components, ports: state.ports, stale: true };
  }

  async function fetchRuntimeHealth() {
    const res = await fetchWithTimeout(
      RUNTIME + "/api/health/all",
      {},
      FETCH_TIMEOUT_MS,
    );
    if (!res.ok) throw new Error("runtime health failed");
    return res.json();
  }

  async function fetchPortStatus() {
    const res = await fetchWithTimeout(
      RUNTIME + "/api/health/ports",
      {},
      FETCH_TIMEOUT_MS,
    );
    if (!res.ok) throw new Error("port status failed");
    return res.json();
  }

  async function fetchCloudHealth() {
    const res = await fetchWithTimeout(
      "/api/health",
      {},
      FETCH_TIMEOUT_MS,
    );
    if (!res.ok) {
      throw new Error("Cloud no responde en puerto 8000 (HTTP " + res.status + ")");
    }
    return { ok: true };
  }

  function offlineHealthSnapshot(message) {
    return {
      overall: state.overall || "critical",
      components: state.components,
      ports: state.ports,
      error: message || state.lastError,
    };
  }

  function offlineHealthForDiagnostics(message) {
    const msg = message || "Runtime no responde en puerto 8765";
    return {
      overall: "critical",
      components: {
        runtime: { status: "critical", label: "Runtime", message: msg },
        cloud: { status: "warning", label: "Cloud", message: "Sin datos de puertos" },
        connector: { status: "warning", label: "Connector", message: "Runtime offline" },
        hermes: { status: "warning", label: "Hermes", message: "Desconocido" },
        aiProvider: { status: "warning", label: "AI Provider", message: "Desconocido" },
      },
      ports: null,
      error: msg,
    };
  }

  function staticDiagnosticsFallback(errorMsg) {
    return {
      version: "—",
      source: "electron",
      updates: { state: "—" },
      offlineMessage: errorMsg || "Runtime no responde en puerto 8765",
    };
  }

  function forceDiagnosticsPanelIfStillLoading(errMsg) {
    const host = document.getElementById("diag-panel");
    if (!host) return;
    if (host.textContent.indexOf("Cargando diagnóstico") === -1) return;
    const health = offlineHealthForDiagnostics(errMsg || "Runtime no responde en puerto 8765");
    const fallback = staticDiagnosticsFallback(errMsg);
    renderDiagnosticsPanel(health, fallback, {
      diagnosticsError: errMsg || "Runtime no responde en puerto 8765",
    });
  }

  async function fetchHealth() {
    state.lastError = null;
    state.runtimeStale = false;
    state.runtimeReachable = false;

    const probe = await probeRuntimeHealthy();
    if (probe.ok) {
      try {
        const results = await Promise.allSettled([fetchRuntimeHealth(), fetchPortStatus()]);
        const healthResult = results[0];
        if (healthResult.status !== "fulfilled") throw healthResult.reason;

        const data = healthResult.value;
        state.runtimeAvailable = true;
        state.runtimeStale = false;
        state.runtimeReachable = true;
        state.overall = data.overall || "degraded";
        state.components = data.components || {};
        state.components.runtime = Object.assign({}, state.components.runtime || {}, {
          status: "ok",
          label: "Runtime",
          message: "Online",
        });
        if (state.overall === "healthy" && state.components.runtime.status !== "ok") {
          state.overall = "degraded";
        }
        state.ports = results[1].status === "fulfilled" ? results[1].value : null;
        state.lastCheck = Date.now();
        return { overall: state.overall, components: state.components, ports: state.ports };
      } catch (runtimeErr) {
        state.runtimeAvailable = false;
        state.ports = null;
      }
    } else if (probe.stale || probe.reachable) {
      let partial = null;
      try {
        partial = await fetchRuntimeHealth();
      } catch (_) {}
      return applyStaleRuntimeState(partial && partial.components);
    } else {
      state.runtimeAvailable = false;
      state.runtimeStale = false;
      state.runtimeReachable = false;
      state.ports = null;
    }

    try {
      const cloud = await fetchCloudHealth();
      state.overall = cloud.ok ? "degraded" : "critical";
      state.components = {
        cloud: { status: cloud.ok ? "ok" : "critical", label: "Cloud", message: "Cloud activo" },
        runtime: {
          status: "critical",
          label: "Runtime",
          message: "Runtime no disponible — puerto 8765",
        },
        connector: { status: "warning", label: "Connector", message: "Runtime no disponible" },
        hermes: { status: "warning", label: "Hermes", message: "Desconocido" },
      };
      state.lastError = "Runtime no disponible — puerto 8765";
      state.lastCheck = Date.now();
      return { overall: state.overall, components: state.components, ports: state.ports };
    } catch (cloudErr) {
      state.overall = "critical";
      state.components = {
        cloud: { status: "critical", label: "Cloud", message: abortErrorMessage(cloudErr) },
        runtime: { status: "critical", label: "Runtime", message: "Runtime no disponible — puerto 8765" },
      };
      state.lastError = "Cloud y Runtime no disponibles (puertos 8000 y 8765)";
      state.lastCheck = Date.now();
      return { overall: "critical", components: state.components, ports: state.ports };
    }
  }

  function coreServicesHealthy(health) {
    const comps = (health && health.components) || state.components || {};
    const runtimeOk = comps.runtime && comps.runtime.status === "ok";
    const cloudOk = comps.cloud && comps.cloud.status === "ok";
    const hermesOk = comps.hermes && comps.hermes.status === "ok";
    return !!(runtimeOk && cloudOk && hermesOk);
  }

  function overallLabel(overall, health) {
    if (state.runtimeStale) return STALE_RUNTIME_MSG;
    if (overall === "healthy" || (overall === "degraded" && coreServicesHealthy(health))) {
      return "Sistema operativo";
    }
    if (overall === "degraded") return "Sistema degradado";
    if (overall === "checking") return "Comprobando estado…";
    return "Sistema offline";
  }

  function overallClass(overall, health) {
    if (state.runtimeStale) return "warn";
    if (overall === "healthy" || (overall === "degraded" && coreServicesHealthy(health))) return "ok";
    if (overall === "degraded") return "warn";
    if (overall === "checking") return "checking";
    return "err";
  }

  function componentLabel(comp) {
    if (comp.label === "Connector" || comp.authRequired !== undefined || comp.running !== undefined) {
      if (comp.message && /Connector (conectado|requiere|desconectado|no disponible|Reconectando)/.test(comp.message)) {
        return comp.message;
      }
      if (comp.recovering) return "↻ Reconectando...";
      if (comp.running && comp.authenticated) return "● Connector conectado";
      if (comp.running && comp.authenticated === false) return "⚠ Connector requiere autenticación";
      if (comp.running === false) return "○ Connector desconectado";
      if (!comp.running && comp.status === "critical") return "✕ Connector no disponible";
    }
    if (comp.message) return comp.message;
    if (comp.status === "ok") return "Online";
    if (comp.status === "warning") return "Parcial";
    if (comp.status === "critical") return "Offline";
    return "Desconocido";
  }

  function portDotClass(st) {
    if (st === "ok") return "ok";
    if (st === "blocked") return "err";
    if (st === "offline") return "warn";
    return "warn";
  }

  function renderPill(el, health) {
    if (!el) return;
    const cls = overallClass(health.overall, health);
    el.className = "hdr-status sys-" + cls;
    el.innerHTML =
      '<span class="dot ' + cls + '"></span>' +
      '<span class="live">' + overallLabel(health.overall, health) + "</span>";
  }

  function renderPopover(health) {
    const order = ["runtime", "cloud", "connector", "hermes", "aiProvider", "maios", "network"];
    order.forEach(function (key) {
      const comp = health.components && health.components[key];
      const dot = document.getElementById("sp-dot-" + key);
      const val = document.getElementById("sp-val-" + key);
      if (!dot || !val) return;
      if (!comp) {
        dot.className = "sp-dot warn";
        val.textContent = "—";
        return;
      }
      const st = comp.status === "ok" ? "ok" : comp.status === "warning" ? "warn" : "err";
      dot.className = "sp-dot " + st;
      val.textContent = componentLabel(comp);
    });

    const ports = health.ports || state.ports;
    if (ports) {
      ["runtime", "cloud"].forEach(function (key) {
        const row = ports[key];
        const dot = document.getElementById("sp-dot-port-" + key);
        const val = document.getElementById("sp-val-port-" + key);
        if (!dot || !val || !row) return;
        dot.className = "sp-dot " + portDotClass(row.status);
        val.textContent = row.message || "—";
        val.title = row.hint || "";
      });
    }

    const foot = document.getElementById("sp-foot");
    if (foot) {
      const ts = state.lastCheck ? new Date(state.lastCheck).toLocaleTimeString() : "—";
      foot.textContent =
        "Última comprobación: " +
        ts +
        (state.runtimeAvailable ? "" : " · runtime offline");
    }
  }

  function connectionBannerMessage(health) {
    const ports = health.ports || state.ports;
    const runtime = health.components && health.components.runtime;
    const cloud = health.components && health.components.cloud;

    if (state.runtimeStale) {
      return {
        level: "warn",
        title: STALE_RUNTIME_MSG,
        detail:
          state.lastError ||
          "El runtime en puerto 8765 no incluye importación de archivos. Reinicia para actualizar.",
        showRestart: true,
      };
    }

    if (ports && ports.runtime && ports.runtime.status === "blocked") {
      return {
        level: "err",
        title: "Puerto 8765 ocupado",
        detail: ports.runtime.hint || "Cierra el proceso que bloquea el runtime o reinicia VANOVA.",
      };
    }
    if (ports && ports.cloud && ports.cloud.status === "blocked") {
      return {
        level: "err",
        title: "Puerto 8000 ocupado",
        detail: ports.cloud.hint || "Cierra el proceso que bloquea Cloud o reinicia los servicios.",
      };
    }
    if (!state.runtimeAvailable || (runtime && runtime.status === "critical")) {
      return {
        level: "err",
        title: "Runtime no disponible — puerto 8765",
        detail: runtime && runtime.message ? runtime.message : "Comprueba que VANOVA esté en ejecución.",
        showRestart: true,
      };
    }
    if (cloud && cloud.status === "critical") {
      return {
        level: "warn",
        title: cloud.message || "Cloud no disponible — puerto 8000",
        detail: cloud.hint || "Reinicia los servicios desde el panel de estado.",
      };
    }
    if (health.overall === "degraded") {
      const conn = health.components && health.components.connector;
      const runtimeOk = runtime && runtime.status === "ok";
      const cloudOk = cloud && cloud.status === "ok";
      const hermes = health.components && health.components.hermes;
      const hermesOk = hermes && hermes.status === "ok";
      if (runtimeOk && cloudOk && hermesOk && conn && conn.status === "warning") {
        return null;
      }
      if (conn && conn.authRequired) {
        return {
          level: "warn",
          title: "Connector requiere registro",
          detail:
            conn.hint ||
            "Este PC aún no está registrado como dispositivo. Pulsa «Registrar dispositivo» para conectarlo con Cloud.",
          showRegisterConnector: true,
        };
      }
      const connMsg =
        conn && conn.status !== "ok" && conn.message
          ? conn.message
          : state.lastError || "Abre el panel de estado para más detalles.";
      return {
        level: "warn",
        title: "Algunos componentes requieren atención",
        detail: connMsg,
        showRestartConnector: !!(conn && conn.status !== "ok" && conn.running === false && !conn.authRequired),
      };
    }
    if (
      state.runtimeAvailable &&
      runtime &&
      runtime.status === "ok" &&
      cloud &&
      cloud.status === "ok" &&
      state.realtimeState &&
      state.realtimeState !== "connected"
    ) {
      return {
        level: "warn",
        title: REALTIME_LABELS[state.realtimeState] || "Tiempo real no disponible",
        detail:
          state.realtimeError ||
          "Tiempo real no disponible — los datos pueden estar desactualizados.",
      };
    }
    return null;
  }

  function renderConnectionBanner(health) {
    const banner = document.getElementById("maios-conn-banner");
    if (!banner) return;
    const msg = connectionBannerMessage(health);
    if (!msg) {
      if (lastBannerSignature === "hidden") return;
      lastBannerSignature = "hidden";
      banner.className = "conn-banner hidden";
      banner.innerHTML = "";
      return;
    }
    const runtimeDown =
      state.runtimeStale ||
      !state.runtimeAvailable ||
      msg.title.indexOf("Runtime no disponible") !== -1 ||
      msg.title.indexOf("Runtime desactualizado") !== -1;
    const actionBtn = runtimeDown
      ? '<button type="button" class="btn btn-ghost conn-banner-btn" id="conn-restart-runtime">Reiniciar runtime</button>'
      : msg.showRegisterConnector
        ? '<button type="button" class="btn btn-primary conn-banner-btn" id="conn-register-connector">Registrar dispositivo</button>'
      : msg.title.indexOf("Cloud no disponible") !== -1
        ? '<button type="button" class="btn btn-ghost conn-banner-btn" id="conn-restart-services">Reiniciar servicios</button>'
        : msg.showRestartConnector
          ? '<button type="button" class="btn btn-ghost conn-banner-btn" id="conn-restart-connector">Recuperar connector</button>'
          : "";
    const signature = [msg.level || "warn", msg.title || "", msg.detail || "", actionBtn].join("|");
    if (signature === lastBannerSignature) return;
    lastBannerSignature = signature;
    banner.className = "conn-banner conn-banner--" + (msg.level || "warn");
    banner.innerHTML =
      '<span class="conn-banner-dot"></span>' +
      '<div class="conn-banner-body"><strong>' +
      msg.title +
      "</strong><span>" +
      msg.detail +
      "</span></div>" +
      actionBtn;

    const restartRuntimeBtn = document.getElementById("conn-restart-runtime");
    if (restartRuntimeBtn) {
      restartRuntimeBtn.addEventListener("click", function () {
        restartRuntime("banner").catch(function () {});
      });
    }
    const restartServicesBtn = document.getElementById("conn-restart-services");
    if (restartServicesBtn) {
      restartServicesBtn.addEventListener("click", function () {
        runRecovery("cloud").catch(function () {});
      });
    }
    const restartConnectorBtn = document.getElementById("conn-restart-connector");
    if (restartConnectorBtn) {
      restartConnectorBtn.addEventListener("click", function () {
        runRecovery("connector").catch(function () {});
      });
    }
    const registerConnectorBtn = document.getElementById("conn-register-connector");
    if (registerConnectorBtn) {
      registerConnectorBtn.addEventListener("click", function () {
        runRecovery("connector").catch(function () {});
      });
    }
  }

  async function getElectronDiagnosticsFallback() {
    async function readFallback() {
      if (global.maios && typeof global.maios.getDiagnosticsFallback === "function") {
        return await global.maios.getDiagnosticsFallback();
      }
      if (global.maios && typeof global.maios.getVersion === "function") {
        const version = await global.maios.getVersion();
        return { version: version, source: "electron" };
      }
      return null;
    }

    try {
      return await promiseWithTimeout(readFallback(), IPC_TIMEOUT_MS, "Electron no respondió");
    } catch (_) {
      return null;
    }
  }

  async function fetchRuntimeDiagnostics() {
    try {
      const res = await fetchWithTimeout(
        RUNTIME + "/api/diagnostics",
        {},
        FETCH_TIMEOUT_MS,
      );
      if (res.ok) return { data: await res.json(), error: null };
      return { data: null, error: "HTTP " + res.status };
    } catch (e) {
      return { data: null, error: abortErrorMessage(e) };
    }
  }

  function renderDiagnosticsPanel(health, diagnostics, opts) {
    opts = opts || {};
    const host = document.getElementById("diag-panel");
    if (!host) return;

    if (opts.loading) {
      host.innerHTML = '<div class="diag-empty">Cargando diagnóstico…</div>';
      return;
    }

    const ports = (health && health.ports) || state.ports;
    const comps = (health && health.components) || state.components || {};
    const runtimeDown = !state.runtimeAvailable && !state.runtimeStale;
    const staleBanner = state.runtimeStale
      ? '<div class="diag-banner diag-banner--warn">' +
        STALE_RUNTIME_MSG +
        ' — falta importación de archivos. Usa el botón «Reiniciar runtime».</div>' +
        '<div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">' +
        '<button class="btn btn-primary" style="height:30px;font-size:12px" data-act="diag-restart-runtime">Reiniciar runtime</button>' +
        '<button class="btn btn-ghost" style="height:30px;font-size:12px" data-act="diag-refresh">Reintentar</button>' +
        "</div>"
      : "";
    const portRows = ports
      ? ["runtime", "cloud"]
          .map(function (key) {
            const row = ports[key];
            if (!row) return "";
            return (
              '<div class="diag-row"><span class="status-dot ' +
              portDotClass(row.status) +
              '"></span><span>Puerto ' +
              row.port +
              " (" +
              row.label +
              ')</span><span class="diag-val">' +
              (row.message || "—") +
              "</span></div>"
            );
          })
          .join("")
      : '<div class="diag-empty">Puertos no disponibles — runtime offline</div>';

    const connRows = ["runtime", "cloud", "connector", "hermes", "aiProvider"]
      .map(function (key) {
        const comp = comps[key];
        if (!comp) return "";
        const st = comp.status === "ok" ? "ok" : comp.status === "warning" ? "warn" : "err";
        return (
          '<div class="diag-row"><span class="status-dot ' +
          st +
          '"></span><span>' +
          (comp.label || key) +
          '</span><span class="diag-val">' +
          componentLabel(comp) +
          "</span></div>"
        );
      })
      .join("");

    const rtSt =
      state.realtimeState === "connected"
        ? "ok"
        : state.realtimeState === "connecting" || state.realtimeState === "reconnecting"
          ? "warn"
          : state.realtimeState === "auth_failed" || state.realtimeState === "disconnected"
            ? "warn"
            : "warn";
    const rtRow =
      '<div class="diag-row"><span class="status-dot ' +
      rtSt +
      '"></span><span>Tiempo real (WebSocket)</span><span class="diag-val">' +
      (REALTIME_LABELS[state.realtimeState] || state.realtimeState) +
      (state.realtimeError ? " — " + state.realtimeError : "") +
      "</span></div>";

    let sysHtml = "";
    if (diagnostics) {
      const upd = diagnostics.updates || {};
      const srcNote =
        diagnostics.source === "electron"
          ? ' <span class="diag-sub">(datos locales — runtime offline)</span>'
          : "";
      sysHtml =
        '<div class="diag-sub">Versión ' +
        (diagnostics.version || "—") +
        srcNote +
        " · Actualizaciones: " +
        (upd.state || "—") +
        (upd.lastCheck ? " · última comprobación " + upd.lastCheck : "") +
        "</div>";
      if (diagnostics.offlineMessage) {
        sysHtml +=
          '<div class="diag-row" style="margin-top:8px"><span class="status-dot err"></span><span>Runtime</span><span class="diag-val">' +
          diagnostics.offlineMessage +
          "</span></div>";
      }
      if (diagnostics.logsPath) {
        sysHtml +=
          '<div class="diag-sub">Logs: <code class="diag-code">' +
          diagnostics.logsPath +
          "</code></div>";
      }
      if (diagnostics.correlationId) {
        sysHtml +=
          '<div class="diag-sub">Correlation ID: <code class="diag-code">' +
          diagnostics.correlationId +
          "</code></div>";
      }
      if (diagnostics.overall) {
        const overallCls = diagnostics.overall === "healthy" ? "ok" : diagnostics.overall === "degraded" ? "warn" : "err";
        sysHtml +=
          '<div class="diag-row" style="margin-top:8px"><span class="status-dot ' +
          overallCls +
          '"></span><span>Estado general</span><span class="diag-val">' +
          diagnostics.overall +
          "</span></div>";
      }
      if (Array.isArray(diagnostics.checks) && diagnostics.checks.length) {
        sysHtml +=
          '<div style="margin-top:12px">' +
          diagnostics.checks
            .map(function (c) {
              const st = c.status === "ok" ? "ok" : c.status === "warning" ? "warn" : "err";
              return (
                '<div class="diag-row"><span class="status-dot ' +
                st +
                '"></span><span>' +
                (c.label || c.id || "check") +
                '</span><span class="diag-val">' +
                (c.message || c.status || "—") +
                "</span></div>"
              );
            })
            .join("") +
          "</div>";
      }
      if (diagnostics.backups && diagnostics.backups.latest) {
        sysHtml +=
          '<div class="diag-sub" style="margin-top:10px">Última copia: ' +
          String(diagnostics.backups.latest.createdAt || "—").slice(0, 19) +
          " · " +
          (diagnostics.backups.count || 0) +
          " copia(s)</div>" +
          '<button class="btn btn-ghost btn-sm" style="margin-top:8px" data-act="diag-backup">Crear copia ahora</button>';
      } else if (diagnostics.backups) {
        sysHtml +=
          '<button class="btn btn-ghost btn-sm" style="margin-top:10px" data-act="diag-backup">Crear primera copia</button>';
      }
      const preUpdateBackups =
        diagnostics.backups && Array.isArray(diagnostics.backups.preUpdateBackups)
          ? diagnostics.backups.preUpdateBackups
          : [];
      if (preUpdateBackups.length) {
        sysHtml +=
          '<div class="diag-sub" style="margin-top:14px">Copias previas a actualizaciones</div>' +
          preUpdateBackups
            .slice(0, 5)
            .map(function (backup) {
              const id = String(backup.id || "").replace(/[^A-Za-z0-9._-]/g, "");
              const summary = backup.dataSummary || {};
              return (
                '<div class="diag-row" style="align-items:center;gap:8px"><span>V' +
                (backup.version || "—") +
                " · " +
                String(backup.createdAt || "—").slice(0, 19) +
                " · " +
                (summary.organizedProducts || 0) +
                ' productos</span><button class="btn btn-ghost btn-sm" data-act="diag-restore-backup" data-backup-id="' +
                id +
                '">Restaurar</button></div>'
              );
            })
            .join("");
      }
    } else if (runtimeDown || opts.diagnosticsError) {
      sysHtml =
        '<div class="diag-error">' +
        '<div class="diag-row"><span class="status-dot err"></span><span>Runtime no disponible</span>' +
        '<span class="diag-val">' +
        (opts.diagnosticsError || state.lastError || "Puerto 8765 sin respuesta") +
        "</span></div>" +
        '<div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">' +
        '<button class="btn btn-primary" style="height:30px;font-size:12px" data-act="diag-restart-runtime">Reiniciar runtime</button>' +
        '<button class="btn btn-ghost" style="height:30px;font-size:12px" data-act="diag-refresh">Reintentar</button>' +
        "</div></div>";
    } else {
      sysHtml =
        '<div class="diag-empty">Diagnóstico del runtime no disponible</div>' +
        '<button class="btn btn-ghost" style="height:30px;font-size:12px;margin-top:8px" data-act="diag-refresh">' +
        "Reintentar</button>";
    }

    const banner =
      runtimeDown && !opts.loading
        ? '<div class="diag-banner diag-banner--err">Runtime no disponible — mostrando datos parciales</div>'
        : "";

    const conn = comps.connector;
    const connAuthBanner =
      conn && conn.authRequired
        ? '<div class="diag-banner diag-banner--warn" style="margin-bottom:14px">' +
          (conn.hint ||
            "El connector está activo pero este PC no está registrado como dispositivo.") +
          '<div style="margin-top:10px">' +
          '<button class="btn btn-primary" style="height:30px;font-size:12px" data-act="diag-register-connector">Registrar dispositivo</button>' +
          "</div></div>"
        : "";

    host.innerHTML =
      staleBanner +
      banner +
      connAuthBanner +
      '<div class="diag-section"><div class="diag-title">Puertos</div>' +
      portRows +
      "</div>" +
      '<div class="diag-section"><div class="diag-title">Estado de conexiones</div>' +
      (connRows || '<div class="diag-empty">Sin datos de conexión</div>') +
      rtRow +
      "</div>" +
      '<div class="diag-section"><div class="diag-title">Diagnóstico del sistema</div>' +
      sysHtml +
      "</div>";
  }

  async function fetchHealthForDiagnostics() {
    try {
      return await promiseWithTimeout(fetchHealth(), DIAG_FETCH_MS, "Runtime no responde en puerto 8765");
    } catch (_) {
      state.runtimeAvailable = false;
      state.lastError = "Runtime no responde en puerto 8765";
      return offlineHealthForDiagnostics(state.lastError);
    }
  }

  async function loadDiagnosticsWork(gen) {
    const healthPromise = fetchHealthForDiagnostics();
    const diagPromise = fetchRuntimeDiagnostics();
    const health = await healthPromise;
    if (gen !== diagLoadGen) return null;

    let diagnostics = null;
    let diagnosticsError = null;

    if (state.runtimeAvailable) {
      const diagResult = await promiseWithTimeout(diagPromise, DIAG_FETCH_MS, "Diagnóstico runtime agotado").catch(
        function (e) {
          return { data: null, error: abortErrorMessage(e) };
        },
      );
      diagnostics = diagResult.data;
      diagnosticsError = diagResult.error;
    } else {
      diagnosticsError = state.lastError || "Runtime no responde en puerto 8765";
      diagPromise.catch(function () {});
    }

    if (gen !== diagLoadGen) return null;

    if (!diagnostics) {
      const fallback = await getElectronDiagnosticsFallback();
      diagnostics = fallback || staticDiagnosticsFallback(diagnosticsError);
      if (!fallback && diagnosticsError) {
        diagnostics.offlineMessage = diagnosticsError;
      }
    }

    state.diagError = diagnosticsError;
    renderDiagnosticsPanel(health, diagnostics, { diagnosticsError: diagnosticsError });
    return { health: health, diagnostics: diagnostics, error: diagnosticsError };
  }

  async function loadDiagnostics(opts) {
    opts = opts || {};
    const soft = !!opts.soft;
    const gen = ++diagLoadGen;
    state.diagLoading = true;
    state.diagError = null;
    if (!soft || !diagPanelReady) {
      renderDiagnosticsPanel(null, null, { loading: true });
    }

    try {
      const result = await promiseWithTimeout(
        loadDiagnosticsWork(gen),
        DIAG_TOTAL_TIMEOUT_MS,
        "Diagnóstico tardó demasiado",
      );
      if (gen === diagLoadGen && result) diagPanelReady = true;
      if (gen !== diagLoadGen) return result;
      return result;
    } catch (e) {
      if (gen !== diagLoadGen) return { error: "stale" };
      state.diagError = abortErrorMessage(e);
      let fallback = await getElectronDiagnosticsFallback();
      if (!fallback) fallback = staticDiagnosticsFallback(state.diagError);
      else if (state.diagError) fallback.offlineMessage = state.diagError;
      const health = offlineHealthForDiagnostics("Runtime no responde en puerto 8765");
      renderDiagnosticsPanel(health, fallback, {
        diagnosticsError: state.diagError || "Runtime no responde en puerto 8765",
      });
      return { health: health, diagnostics: fallback, error: state.diagError };
    } finally {
      if (gen === diagLoadGen) {
        state.diagLoading = false;
        forceDiagnosticsPanelIfStillLoading(state.diagError);
      }
    }
  }

  function refreshDiagnostics() {
    return loadDiagnostics({ soft: false });
  }

  let diagViewActive = false;

  function setDiagnosticsViewActive(active) {
    diagViewActive = !!active;
    if (!active) stopDiagnosticsPolling();
  }

  function startDiagnosticsPolling() {
    if (!diagViewActive || diagPollTimer) return;
    diagPollTimer = setInterval(function () {
      if (document.hidden || !diagViewActive) return;
      const host = document.getElementById("diag-panel");
      if (!host) return;
      loadDiagnostics({ soft: true }).catch(function () {});
    }, DIAG_POLL_MS);
  }

  function stopDiagnosticsPolling() {
    if (diagPollTimer) {
      clearInterval(diagPollTimer);
      diagPollTimer = null;
    }
  }

  function emit(health) {
    document.dispatchEvent(new CustomEvent("maios:health", { detail: health }));
    renderConnectionBanner(health);
    maybeAutoRecover(health);
    if (typeof global.__MAIOS_onHealthUpdate === "function") {
      global.__MAIOS_onHealthUpdate(health);
    }
  }

  function componentNeedsRecovery(comp) {
    if (!comp || comp.status === "ok") return false;
    if (comp.authRequired || (comp.running && comp.authenticated === false)) return false;
    return true;
  }

  async function maybeAutoRecover(health) {
    if (!state.runtimeAvailable || autoRecovery.inFlight) return;
    const now = Date.now();
    const targets = [
      { key: "cloud", since: "cloudDownSince", component: health.components && health.components.cloud },
      { key: "connector", since: "connectorDownSince", component: health.components && health.components.connector },
    ];
    for (let i = 0; i < targets.length; i++) {
      const t = targets[i];
      const comp = t.component;
      const ok = comp && comp.status === "ok";
      if (ok) {
        autoRecovery[t.since] = null;
        autoRecovery.attemptCounts[t.key] = 0;
        autoRecovery.gaveUp[t.key] = false;
        continue;
      }
      if (!componentNeedsRecovery(comp)) {
        autoRecovery[t.since] = null;
        continue;
      }
      if (autoRecovery.gaveUp[t.key]) continue;
      if ((autoRecovery.attemptCounts[t.key] || 0) >= AUTO_RECOVERY_MAX_ATTEMPTS) {
        autoRecovery.gaveUp[t.key] = true;
        continue;
      }
      if (!autoRecovery[t.since]) autoRecovery[t.since] = now;
      if (now - autoRecovery[t.since] < AUTO_RECOVERY_AFTER_MS) continue;
      const last = autoRecovery.lastAttempt[t.key] || 0;
      if (now - last < AUTO_RECOVERY_COOLDOWN_MS) continue;
      autoRecovery.inFlight = true;
      autoRecovery.lastAttempt[t.key] = now;
      autoRecovery.attemptCounts[t.key] = (autoRecovery.attemptCounts[t.key] || 0) + 1;
      try {
        await runRecovery(t.key, { silent: true });
        autoRecovery[t.since] = null;
      } catch (_) {
      } finally {
        autoRecovery.inFlight = false;
      }
      break;
    }
  }

  let timer = null;

  function startPolling() {
    if (state.polling) return;
    state.polling = true;

    async function tick() {
      let health;
      try {
        health = await fetchHealth();
      } catch (e) {
        state.overall = "critical";
        state.lastError = abortErrorMessage(e);
        state.lastCheck = Date.now();
        health = offlineHealthSnapshot(state.lastError);
      }
      const pill = document.getElementById("ai-status");
      renderPill(pill, health);
      const pop = document.getElementById("status-pop");
      if (pop && pop.classList.contains("open")) renderPopover(health);
      emit(health);
    }

    tick();
    timer = setInterval(tick, POLL_MS);
  }

  function stopPolling() {
    state.polling = false;
    if (timer) clearInterval(timer);
    timer = null;
  }

  async function waitForHealthyRuntime(maxMs) {
    const deadline = Date.now() + (maxMs || 25000);
    while (Date.now() < deadline) {
      const probe = await probeRuntimeHealthy();
      if (probe.ok) return true;
      await sleep(600);
    }
    return false;
  }

  async function restartRuntime(source) {
    showOperation("Reiniciando runtime…");
    try {
      if (global.maios && typeof global.maios.restartRuntime === "function") {
        const result = await promiseWithTimeout(
          global.maios.restartRuntime(),
          30000,
          "Electron no respondió al reinicio",
        );
        if (await waitForHealthyRuntime(25000)) {
          const health = await fetchHealth();
          await loadDiagnostics();
          emit(health);
          return { recovered: true, message: "Runtime reiniciado", ok: true };
        }
        if (result && result.ok) {
          throw new Error("Runtime reiniciado pero /api/health/all sigue fallando — ejecuta scripts/restart-maios-runtime.ps1");
        }
        throw new Error("Electron no pudo reiniciar el runtime");
      }

      if (state.runtimeReachable || state.runtimeStale) {
        try {
          await runRecovery("runtime");
          if (await waitForHealthyRuntime(15000)) {
            const health = await fetchHealth();
            await loadDiagnostics();
            emit(health);
            return { recovered: true, message: "Runtime recuperado vía /api/recovery", ok: true };
          }
        } catch (_) {}
      }

      throw new Error(
        "Runtime offline — abre VANOVA o ejecuta scripts/restart-vanova-runtime.ps1",
      );
    } catch (e) {
      throw e instanceof Error ? e : new Error(String(e || "No se pudo reiniciar el runtime"));
    } finally {
      hideOperation();
    }
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  async function runtimeAuthHeaders() {
    try {
      if (global.maios && typeof global.maios.getRuntimeAuthHeaders === "function") {
        const headers = await global.maios.getRuntimeAuthHeaders();
        if (headers && typeof headers === "object") return headers;
      }
    } catch (e) {}
    return {};
  }

  async function runRecovery(component, opts) {
    opts = opts || {};
    const silent = !!opts.silent;
    if (!state.runtimeAvailable && (component === "cloud" || component === "hermes" || component === "runtime")) {
      return restartRuntime("recovery-" + component);
    }
    if (!silent) showOperation("Recuperando " + component + "…");
    try {
      const auth = await runtimeAuthHeaders();
      const res = await fetchWithTimeout(
        RUNTIME + "/api/recovery",
        {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, auth),
          body: JSON.stringify({ component: component }),
        },
        30000,
      );
      const data = await res.json();
      await fetchHealth();
      return data;
    } finally {
      if (!silent) hideOperation();
    }
  }

  /* Global operation bar — visible feedback for async work */
  let opCount = 0;

  function showOperation(message) {
    opCount++;
    const bar = document.getElementById("maios-op-bar");
    const txt = document.getElementById("maios-op-text");
    if (bar) bar.classList.add("active");
    if (txt) {
      txt.textContent = message || "Trabajando…";
      txt.classList.add("active");
    }
  }

  function hideOperation() {
    opCount = Math.max(0, opCount - 1);
    if (opCount === 0) {
      const bar = document.getElementById("maios-op-bar");
      const txt = document.getElementById("maios-op-text");
      if (bar) bar.classList.remove("active");
      if (txt) txt.classList.remove("active");
    }
  }

  global.MAIOSSystemStatus = {
    probeRuntimeHealthy: probeRuntimeHealthy,
    fetchHealth: fetchHealth,
    fetchPortStatus: fetchPortStatus,
    loadDiagnostics: loadDiagnostics,
    refreshDiagnostics: refreshDiagnostics,
    startDiagnosticsPolling: startDiagnosticsPolling,
    stopDiagnosticsPolling: stopDiagnosticsPolling,
    setDiagnosticsViewActive: setDiagnosticsViewActive,
    startPolling: startPolling,
    stopPolling: stopPolling,
    renderPopover: renderPopover,
    renderPill: renderPill,
    renderConnectionBanner: renderConnectionBanner,
    renderDiagnosticsPanel: renderDiagnosticsPanel,
    runRecovery: runRecovery,
    restartRuntime: restartRuntime,
    showOperation: showOperation,
    hideOperation: hideOperation,
    connectionBannerMessage: connectionBannerMessage,
    setRealtimeState: setRealtimeState,
    getState: function () {
      return Object.assign({}, state);
    },
  };
})(window);
