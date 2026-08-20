/** MAIOS UX helpers — empty/loading/error states, Hermes formatting (Phases 19-22). */
(function (global) {
  "use strict";

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function emptyState(opts) {
    const o = opts || {};
    const title = o.title || "Sin datos";
    const why = o.why || "Todavía no hay información para mostrar aquí.";
    const actionLabel = o.actionLabel || "";
    const actionGo = o.actionGo || "";
    const icon = o.icon || "database";
    const icFn = global.ic || function () { return ""; };
    return (
      '<div class="dash-card dash-card--cream"><div class="state-box">' +
      icFn(icon) +
      '<div class="sb-title">' + escapeHtml(title) + "</div>" +
      '<div style="font-size:14px;color:var(--text-2);max-width:420px;line-height:1.55;margin:0 auto">' +
      escapeHtml(why) +
      "</div>" +
      (actionLabel && actionGo
        ? '<span class="sb-link" data-go="' + escapeHtml(actionGo) + '">' + escapeHtml(actionLabel) + " →</span>"
        : "") +
      "</div></div>"
    );
  }

  function loadingState(message) {
    return (
      '<div class="card card-pad" style="text-align:center;padding:40px 20px">' +
      '<div class="sl-spin" style="margin:0 auto 12px"></div>' +
      '<div style="font-size:13px;color:var(--text-2)">' + escapeHtml(message || "Cargando…") + "</div>" +
      "</div>"
    );
  }

  function friendlyError(raw) {
    const msg = String(raw || "");
    if (/ECONNREFUSED|Failed to fetch|NetworkError|fetch failed/i.test(msg)) {
      return {
        title: "VANOVA Runtime no responde",
        message: "El servicio local no está disponible. Prueba reiniciar VANOVA.",
        actions: [{ label: "Ver diagnóstico", go: "diagnostics" }],
      };
    }
    if (/401|Unauthorized/i.test(msg)) {
      return {
        title: "Sesión expirada",
        message: "Vuelve a iniciar sesión para continuar.",
        actions: [],
      };
    }
    if (/429|rate limit|Límite/i.test(msg)) {
      return {
        title: "Demasiadas solicitudes",
        message: "Espera un momento e inténtalo de nuevo.",
        actions: [],
      };
    }
    return {
      title: "Algo salió mal",
      message: msg.length > 180 ? msg.slice(0, 180) + "…" : msg,
      actions: [{ label: "Ver diagnóstico", go: "diagnostics" }],
    };
  }

  function errorBannerHTML(raw) {
    const f = friendlyError(raw);
    const icFn = global.ic || function () { return ""; };
    const actions = (f.actions || [])
      .map(function (a) {
        return '<button class="btn btn-ghost btn-sm" data-go="' + escapeHtml(a.go) + '">' + escapeHtml(a.label) + "</button>";
      })
      .join("");
    return (
      '<div class="conn-banner conn-banner--warn" style="margin-bottom:16px">' +
      '<span class="status-dot warn"></span>' +
      '<div class="conn-banner-body"><strong>' + escapeHtml(f.title) + "</strong>" +
      "<span>" + escapeHtml(f.message) + "</span></div>" +
      (actions ? '<div style="margin-left:auto">' + actions + "</div>" : "") +
      "</div>"
    );
  }

  /** Structure Hermes free-text into readable sections (Phase 19). */
  function formatHermesStructured(text) {
    const raw = String(text || "").trim();
    if (!raw) return "";

    const sectionNames = ["ANALYSIS", "ANÁLISIS", "LIKELY CAUSE", "CAUSA", "RECOMMENDATION", "RECOMENDACIÓN", "ACTIONS", "ACCIONES"];
    const lines = raw.split(/\r?\n/);
    let html = "";
    let current = "";
    let body = [];

    function flush() {
      if (!current && !body.length) return;
      const label = current || "RESPUESTA";
      html +=
        '<div class="hermes-section" style="margin-bottom:12px">' +
        '<div style="font-size:11px;font-weight:600;letter-spacing:.06em;color:var(--text-3);margin-bottom:4px">' +
        escapeHtml(label) +
        "</div>" +
        '<div style="font-size:13px;line-height:1.55;white-space:pre-wrap">' +
        escapeHtml(body.join("\n").trim()) +
        "</div></div>";
      body = [];
    }

    lines.forEach(function (line) {
      const upper = line.trim().toUpperCase();
      const isHeader = sectionNames.some(function (s) {
        return upper === s || upper.startsWith(s + ":");
      });
      if (isHeader) {
        flush();
        current = line.trim().replace(/:$/, "");
        return;
      }
      body.push(line);
    });
    flush();
    if (html) {
      return (
        html +
        '<div class="row" style="gap:8px;margin-top:8px;flex-wrap:wrap">' +
        '<button class="btn btn-ghost btn-sm" data-go="tasks">Crear tarea</button>' +
        '<button class="btn btn-ghost btn-sm" data-go="hermes">Seguir en Hermes</button>' +
        "</div>"
      );
    }
    return '<div style="white-space:pre-wrap">' + escapeHtml(raw) + "</div>";
  }

  /** Expandable operational summary after Hermes responses (matches standalone context). */
  function formatOperationalDetail(summary) {
    if (!summary || typeof summary !== "object") return "";
    const p = summary.productos || {};
    const o = summary.pedidos || {};
    const f = summary.archivos || {};
    const dm = summary.dataMode || {};
    const integ = summary.integraciones || {};
    const shop = integ.shopify || {};
    const hermes = integ.hermes || {};
    const cloud = integ.cloud || {};
    const conn = integ.connector || {};
    const agents = summary.agentes || [];
    const agentLines = agents.slice(0, 8).map(function (a) {
      return (
        '<div class="hop-row"><span>' +
        escapeHtml(a.name || a.id || "Agente") +
        '</span><b>' +
        escapeHtml(a.status || "idle") +
        "</b></div>"
      );
    }).join("");
    return (
      '<details class="hermes-op-detail" open>' +
      '<summary>Detalle operativo</summary>' +
      '<div class="hop-body">' +
      '<div class="hop-row"><span>Modo datos</span><b>' +
      escapeHtml((dm.label || dm.dataMode || "—") + "") +
      "</b></div>" +
      '<div class="hop-row"><span>Productos organizados</span><b>' +
      (p.total || 0) +
      " (" +
      (p.local || 0) +
      " Excel + " +
      (p.shopify || 0) +
      " Shopify)</b></div>" +
      '<div class="hop-row"><span>Catálogo Excel</span><b>' +
      (p.catalogExcelRows || 0) +
      " filas / " +
      (p.productFiles || 0) +
      " archivos</b></div>" +
      '<div class="hop-row"><span>Sync Shopify productos</span><b>' +
      (shop.syncedProducts != null ? shop.syncedProducts : p.shopifySynced || 0) +
      "</b></div>" +
      '<div class="hop-row"><span>Pedidos organizados</span><b>' +
      (o.total || 0) +
      " (sync " +
      (o.shopifySynced || 0) +
      ")</b></div>" +
      '<div class="hop-row"><span>Archivos</span><b>' +
      (f.total || 0) +
      " total</b></div>" +
      '<div class="hop-row"><span>Shopify</span><b>' +
      escapeHtml(shop.message || (shop.connected ? "Conectado" : "No conectado")) +
      "</b></div>" +
      '<div class="hop-row"><span>Hermes</span><b>' +
      escapeHtml((hermes.healthy ? "Online" : "Offline") + (hermes.model ? " · " + hermes.model : "")) +
      "</b></div>" +
      '<div class="hop-row"><span>Cloud / Connector</span><b>' +
      escapeHtml((cloud.running ? "Cloud ✓" : "Cloud ○") + " · " + (conn.running ? "Connector ✓" : "Connector ○")) +
      "</b></div>" +
      (agentLines ? '<div style="margin-top:8px;font-weight:600;color:var(--text);font-size:11px">Agentes</div>' + agentLines : "") +
      "</div></details>"
    );
  }

  global.MAIOSUx = {
    emptyState: emptyState,
    loadingState: loadingState,
    friendlyError: friendlyError,
    errorBannerHTML: errorBannerHTML,
    formatHermesStructured: formatHermesStructured,
    formatOperationalDetail: formatOperationalDetail,
  };
})(typeof window !== "undefined" ? window : globalThis);
