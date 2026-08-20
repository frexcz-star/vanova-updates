/**
 * MAIOS Update Center — Dashboard widget + Settings detail view.
 * Single backend: desktop runtime API at :8765
 */
(function () {
  'use strict';

  const API = 'http://127.0.0.1:8765';
  const STARTUP_DELAY_MS = 4000;
  const DEFAULT_CHECK_INTERVAL_HOURS = 4;
  const ACTIVE = new Set([
    'checking', 'downloading', 'downloaded', 'verifying', 'backing_up',
    'installing', 'restarting', 'verifying_install', 'rollback',
  ]);

  let pollTimer = null;
  let periodicCheckTimer = null;
  let startupTimer = null;
  let lastNotifiedVersion = null;
  let modalDismissedVersion = null;
  let cachedStatus = null;
  let cachedVersion = null;
  let appReady = false;

  async function runtimeAuthHeaders() {
    try {
      if (window.maios && typeof window.maios.getRuntimeAuthHeaders === 'function') {
        const headers = await window.maios.getRuntimeAuthHeaders();
        if (headers && typeof headers === 'object') return headers;
      }
    } catch (_) {}
    return {};
  }

  async function api(path, opts) {
    const auth = await runtimeAuthHeaders();
    const method = ((opts && opts.method) || 'GET').toUpperCase();
    const headers = Object.assign({}, auth, (opts && opts.headers) || {});
    if (method !== 'GET' && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    // Timeout duro: si el runtime tarda (red lenta, DNS colgado), la promesa
    // debe resolverse con error y nunca dejar la UI en "Buscando
    // actualizaciones…" para siempre.
    const timeoutMs = (opts && opts.timeoutMs) || 60000;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(API + path, Object.assign({}, opts || {}, { headers, signal: controller.signal }));
      if (!res.ok) throw new Error('API ' + path + ' failed');
      return res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleString(); } catch (_) { return iso; }
  }

  function fmtBytes(n) {
    if (!n && n !== 0) return '';
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function settingsLabel(state) {
    const map = {
      idle: 'Listo',
      checking: 'Buscando actualizaciones…',
      available: 'Actualización disponible',
      up_to_date: 'VANOVA está actualizado.',
      downloading: 'Descargando actualización…',
      downloaded: 'Descarga completa',
      verifying: 'Verificando actualización…',
      ready_to_install: 'Actualización lista',
      installing: 'Instalando actualización…',
      restarting: 'Reiniciando VANOVA…',
      verifying_install: 'Verificando instalación…',
      completed: 'Actualización completada',
      failed: 'Error en la actualización',
      cancelled: 'Cancelado',
      rollback: 'Revirtiendo…',
      offline: 'Sin conexión',
    };
    return map[state] || state || '—';
  }

  function installedVersion(status, versionInfo) {
    return (status && status.installedVersion) ||
      (versionInfo && versionInfo.version) ||
      '—';
  }

  function dashboardCompactLine(status, versionInfo) {
    const st = status.state || 'idle';
    const cur = installedVersion(status, versionInfo);
    const target = status.targetVersion;
    if (st === 'checking') return 'VANOVA ' + cur + ' · comprobando…';
    if (st === 'up_to_date' || st === 'completed') return 'VANOVA ' + cur + ' · al día';
    if (st === 'available') return 'VANOVA ' + (target || '?') + ' disponible';
    if (st === 'ready_to_install') return 'VANOVA ' + (target || '?') + ' · lista para instalar';
    if (st === 'downloaded') return 'VANOVA ' + (target || '?') + ' · descargada';
    if (st === 'downloading') return 'VANOVA ' + cur + ' · descargando…';
    if (st === 'installing' || st === 'restarting') return 'VANOVA · reiniciando…';
    if (st === 'failed') return 'VANOVA ' + cur + ' · error de actualización';
    if (st === 'offline') return 'VANOVA ' + cur + ' · sin conexión';
    return 'VANOVA ' + cur;
  }

  function dashboardStatusText(status, versionInfo) {
    const st = status.state || 'idle';
    const target = status.targetVersion;
    const dl = status.download || {};
    const pct = dl.percent;
    if (st === 'checking') return 'Buscando actualizaciones…';
    if (st === 'up_to_date') return 'VANOVA está actualizado.';
    if (st === 'available') return 'VANOVA ' + (target || '?') + ' disponible — pulsa Descargar';
    if (st === 'ready_to_install') return 'Actualización lista. Reinicia para aplicar los cambios.';
    if (st === 'downloaded') return 'Verificando actualización…';
    if (st === 'downloading') {
      return typeof pct === 'number' && pct > 0
        ? 'Descargando actualización… ' + pct + '%'
        : 'Descargando actualización…';
    }
    if (st === 'verifying') return 'Verificando actualización…';
    if (st === 'backing_up') return 'Preparando instalación…';
    if (st === 'installing' || st === 'restarting') return 'Reiniciando VANOVA…';
    if (st === 'verifying_install') return 'Verificando instalación…';
    if (st === 'completed') return 'Actualización completada';
    if (st === 'failed') return status.message || status.error || 'Error — pulsa Reintentar';
    if (st === 'offline') return 'Sin conexión — se reintentará más tarde';
    if (st === 'idle') return 'Pulsa Buscar actualizaciones para comprobar';
    return settingsLabel(st);
  }

  function isUpdateAvailable(st) {
    return st === 'available' || st === 'ready_to_install' || st === 'downloaded';
  }

  function isBusy(st) {
    return ACTIVE.has(st);
  }

  function checkIntervalMs(status) {
    const cfg = (status && status.config) || {};
    const hours = parseFloat(cfg.checkIntervalHours) || DEFAULT_CHECK_INTERVAL_HOURS;
    return Math.max(1, hours) * 60 * 60 * 1000;
  }

  function progressBar(pct, indeterminate) {
    if (indeterminate || pct == null) {
      return '<div class="maios-update-progress indeterminate"><div class="bar pulse"></div></div>';
    }
    const p = Math.max(0, Math.min(100, pct));
    return '<div class="maios-update-progress"><div class="bar" style="width:' + p + '%"></div></div>';
  }

  function renderNotes(notes, compact) {
    if (!notes || !notes.length) return '';
    const items = notes.slice(0, compact ? 4 : 8).map(function (n) {
      return '<li>' + escapeHtml(n) + '</li>';
    }).join('');
    return '<div class="maios-update-notes"><div class="label">Novedades</div><ul>' + items + '</ul></div>';
  }

  function updateNavBadge(status) {
    const nav = document.querySelector('[data-nav="settings"]');
    if (!nav) return;
    let badge = nav.querySelector('.update-badge');
    if (isUpdateAvailable(status.state) || status.state === 'ready_to_install') {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'update-badge';
        badge.textContent = '•';
        nav.appendChild(badge);
      }
    } else if (badge) {
      badge.remove();
    }
  }

  function updateHeaderIndicator(status) {
    const el = document.getElementById('hdr-update');
    if (!el) return;
    const st = status.state || 'idle';
    el.classList.remove('has-update', 'busy');
    if (isUpdateAvailable(st) || st === 'ready_to_install') {
      el.classList.add('has-update');
      el.title = 'Actualización disponible: VANOVA ' + (status.targetVersion || '');
    } else if (isBusy(st)) {
      el.classList.add('busy');
      el.title = dashboardStatusText(status, cachedVersion);
    } else {
      el.title = 'Actualizaciones VANOVA';
    }
  }

  /* ---- Startup / notification modal ---- */
  function hideUpdateModal() {
    const modal = document.getElementById('maios-update-modal');
    if (modal) modal.remove();
  }

  function showUpdateModal(status) {
    injectStyles();
    const st = status.state || 'idle';
    const target = status.targetVersion || '';
    const manifest = status.manifest || {};
    const dl = status.download || {};
    const pct = dl.percent;

    if (status.postponed) return;
    // Descartar tambien en 'failed': si no, el modal de error reaparece en cada poll
    if (modalDismissedVersion === target && (st === 'available' || st === 'failed')) return;

    let title = '';
    let body = '';
    let actions = '';

    if (st === 'available') {
      title = 'VANOVA ' + escapeHtml(target) + ' disponible';
      body = renderNotes(manifest.releaseNotes, true);
      actions =
        '<button type="button" class="btn btn-primary" id="maios-modal-update">Actualizar</button>' +
        '<button type="button" class="btn btn-ghost" id="maios-modal-later">Más tarde</button>';
    } else if (st === 'downloading' || st === 'verifying' || st === 'downloaded') {
      title = 'Descargando actualización…';
      const pctText = typeof pct === 'number' && pct > 0 ? ' ' + pct + '%' : '';
      body =
        progressBar(st === 'downloading' && pct > 0 ? pct : null, st !== 'downloading' || !pct) +
        '<div class="maios-modal-status">' + escapeHtml(
          st === 'verifying' || st === 'downloaded'
            ? 'Verificando actualización…'
            : 'Descargando actualización…' + pctText
        ) + '</div>';
      actions = '<button type="button" class="btn btn-ghost" id="maios-modal-hide">Ocultar</button>';
    } else if (st === 'ready_to_install') {
      title = 'Actualización lista';
      body = '<div class="maios-modal-status">VANOVA ' + escapeHtml(target) + ' está listo para instalar.</div>';
      actions =
        '<button type="button" class="btn btn-primary" id="maios-modal-restart">Reiniciar ahora</button>' +
        '<button type="button" class="btn btn-ghost" id="maios-modal-later">Más tarde</button>';
    } else if (st === 'failed') {
      title = 'Error en la actualización';
      body = '<div class="maios-modal-status">' + escapeHtml(status.message || status.error || 'No se pudo completar la descarga.') + '</div>';
      actions =
        '<button type="button" class="btn btn-primary" id="maios-modal-retry">Reintentar</button>' +
        '<button type="button" class="btn btn-ghost" id="maios-modal-later">Más tarde</button>';
    } else {
      return;
    }

    let modal = document.getElementById('maios-update-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'maios-update-modal';
      document.body.appendChild(modal);
    }

    modal.innerHTML =
      '<div class="maios-update-modal-backdrop">' +
      '<div class="maios-update-modal-card">' +
      '<div class="maios-update-modal-title">' + title + '</div>' +
      body +
      '<div class="maios-update-modal-actions">' + actions + '</div>' +
      '</div></div>';

    requestAnimationFrame(function () { modal.classList.add('show'); });

    const updateBtn = document.getElementById('maios-modal-update');
    const laterBtn = document.getElementById('maios-modal-later');
    const restartBtn = document.getElementById('maios-modal-restart');
    const retryBtn = document.getElementById('maios-modal-retry');
    const hideBtn = document.getElementById('maios-modal-hide');

    if (updateBtn) {
      updateBtn.onclick = async function () {
        updateBtn.disabled = true;
        try {
          await downloadUpdate();
          await refreshAll();
        } catch (e) {
          showToast(e.message || 'Error al descargar');
          updateBtn.disabled = false;
        }
      };
    }
    if (laterBtn) {
      laterBtn.onclick = async function () {
        try {
          await postponeUpdate(target);
        } catch (_) {}
        modalDismissedVersion = target;
        hideUpdateModal();
        await refreshAll();
      };
    }
    if (restartBtn) {
      restartBtn.onclick = async function () {
        restartBtn.disabled = true;
        try {
          await installUpdate();
        } catch (e) {
          showToast(e.message || 'Error al instalar');
          restartBtn.disabled = false;
        }
      };
    }
    if (retryBtn) {
      retryBtn.onclick = async function () {
        retryBtn.disabled = true;
        try {
          await downloadUpdate();
          await refreshAll();
        } catch (e) {
          showToast(e.message || 'Error al reintentar');
          retryBtn.disabled = false;
        }
      };
    }
    if (hideBtn) {
      hideBtn.onclick = function () { hideUpdateModal(); };
    }
  }

  function maybeNotifyUpdate(status) {
    const st = status.state || 'idle';
    const target = status.targetVersion;

    if (st === 'available' && target && !status.postponed) {
      if (target !== lastNotifiedVersion) {
        lastNotifiedVersion = target;
        if (appReady) showUpdateModal(status);
      }
    } else if (st === 'ready_to_install' && target) {
      showUpdateModal(status);
    } else if (st === 'downloading' || st === 'verifying' || st === 'downloaded') {
      showUpdateModal(status);
    } else if (st === 'failed') {
      showUpdateModal(status);
    } else if (st === 'up_to_date' || st === 'completed' || st === 'idle') {
      hideUpdateModal();
    }
  }

  async function postponeUpdate(version) {
    await api('/api/updates/postpone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version: version || '' }),
    });
  }

  /* ---- Settings (full detail) ---- */
  function renderUpdateSection(status, versionInfo) {
    const el = document.getElementById('maios-update-center');
    if (!el) return;

    const cur = installedVersion(status, versionInfo);
    const st = status.state || 'idle';
    const target = status.targetVersion;
    const manifest = status.manifest || {};
    const dl = status.download || {};
    const pct = dl.percent;
    const hasPct = typeof pct === 'number' && pct > 0;
    const busy = isBusy(st);

    let actions = '';
    if (!busy) {
      actions = '<button type="button" class="btn btn-ghost" id="maios-check-updates">Buscar actualizaciones</button>';
    }
    if (status.postponed && !busy) {
      actions += '<button type="button" class="btn btn-primary" id="maios-resume-update">Reanudar actualización</button>';
    }
    if (st === 'available') {
      actions += '<button type="button" class="btn btn-primary" id="maios-download-update">Descargar</button>';
      actions += '<button type="button" class="btn btn-ghost" id="maios-postpone-update">Más tarde</button>';
    }
    if (st === 'ready_to_install') {
      actions += '<button type="button" class="btn btn-primary" id="maios-install-update">Reiniciar ahora</button>';
      actions += '<button type="button" class="btn btn-ghost" id="maios-postpone-update">Más tarde</button>';
    }
    if (st === 'downloading' || st === 'verifying') {
      actions += '<button type="button" class="btn btn-ghost" id="maios-cancel-update">Cancelar</button>';
    }
    if (st === 'failed') {
      actions += '<button type="button" class="btn btn-primary" id="maios-retry-update">Reintentar</button>';
      actions += '<button type="button" class="btn btn-ghost" id="maios-postpone-update">Más tarde</button>';
    }

    let progressHtml = '';
    if (st === 'downloading' || st === 'verifying') {
      progressHtml =
        '<div class="maios-update-dl">' +
        progressBar(st === 'downloading' && hasPct ? pct : null, st !== 'downloading' || !hasPct) +
        (st === 'downloading' && hasPct
          ? '<div class="meta">Descargando actualización… ' + pct + '% · ' +
            fmtBytes(dl.bytesReceived) + ' / ' + fmtBytes(dl.totalBytes) + '</div>'
          : '<div class="meta">' + escapeHtml(settingsLabel(st)) + '</div>') +
        '</div>';
    }

    const statusIcon =
      st === 'up_to_date' || st === 'completed' ? '<span class="ok">✓</span> ' :
      st === 'failed' ? '<span class="err">✕</span> ' : '';

    const postponedTarget = (status.postponed && status.manifest && status.manifest.version) || target;
    const statusLine = status.postponed && postponedTarget
      ? 'Actualización ' + escapeHtml(postponedTarget) + ' pospuesta' +
        (status.config && status.config.postponedUntil
          ? ' hasta ' + fmtDate(status.config.postponedUntil)
          : '')
      : (st === 'up_to_date'
        ? 'VANOVA está actualizado.'
        : (st === 'available' && target)
          ? 'VANOVA ' + escapeHtml(target) + ' disponible.'
          : settingsLabel(st));

    const manifestUrl = status.manifestUrl || (status.config && status.config.manifestUrl) || '';
    const manifestLabel = manifestUrl
      ? (manifestUrl.indexOf('releases.moovingpaper.com') >= 0 ? 'CDN de producción' : 'Local / personalizado')
      : 'CDN de producción (predeterminado)';

    el.innerHTML =
      '<div class="maios-settings-block">' +
      '<div class="maios-kv"><span>Versión actual</span><strong>' + escapeHtml(cur) + '</strong></div>' +
      (target && (isUpdateAvailable(st) || st === 'ready_to_install')
        ? '<div class="maios-kv"><span>Versión disponible</span><strong>' + escapeHtml(target) + '</strong></div>'
        : '') +
      '<div class="maios-kv"><span>Canal</span><strong>' + escapeHtml(status.channel || 'stable') + '</strong></div>' +
      '<div class="maios-kv"><span>Origen del manifiesto</span><strong title="' + escapeHtml(manifestUrl) + '">' + escapeHtml(manifestLabel) + '</strong></div>' +
      '<div class="maios-kv"><span>Última comprobación</span><strong>' + fmtDate(status.lastCheck) + '</strong></div>' +
      '<div class="maios-kv"><span>Estado</span><strong>' + statusIcon + escapeHtml(statusLine) + '</strong></div>' +
      (target && (st === 'available' || st === 'ready_to_install' || st === 'downloading' || st === 'downloaded' || st === 'verifying')
        ? '<div class="maios-update-available"><div class="title">Actualización disponible</div><div class="ver">VANOVA ' + escapeHtml(target) + ' disponible</div>' +
          renderNotes(manifest.releaseNotes, false) + '</div>'
        : '') +
      progressHtml +
      (st === 'failed'
        ? '<div class="maios-update-error">' +
          '<div class="maios-update-error-title">Error al actualizar</div>' +
          '<div class="maios-update-error-detail">' + escapeHtml(status.message || status.error || 'La descarga o instalación no se completó. Pulsa Reintentar o Más tarde.') + '</div>' +
          '</div>'
        : (st === 'offline'
          ? '<div class="maios-update-msg subtle">Sin conexión — no se pudo comprobar actualizaciones.</div>'
          : (status.message && st !== 'up_to_date' ? '<div class="maios-update-msg">' + escapeHtml(status.message) + '</div>' : ''))) +
      '<div class="maios-update-actions">' + actions + '</div>' +
      renderHistory(status.history, st, target) +
      '</div>';

    bindSettingsActions();
  }

  var HISTORY_LABELS = {
    installed: 'Instalada',
    installing: 'Instalando…',
    available: 'Disponible',
    downloaded: 'Descargada',
    ready_to_install: 'Lista para instalar',
    restarting: 'Reiniciando…',
    verifying_install: 'Verificando…',
    failed: 'Error',
    cancelled: 'Cancelada',
    rollback: 'Reversión',
    postponed: 'Pospuesta',
  };

  function renderHistory(history, currentState, currentTarget) {
    if (!history || !history.length) return '';
    const active = new Set(['downloading', 'downloaded', 'verifying', 'backing_up', 'installing', 'restarting', 'verifying_install', 'rollback']);
    const transient = new Set(['installing', 'restarting', 'verifying_install', 'rollback']);
    const rows = history.slice(0, 8).map(function (h) {
      const raw = h.outcome || h.status || '';
      const stale = transient.has(raw) && !(active.has(currentState) && String(h.version || '') === String(currentTarget || ''));
      const label = stale ? 'Interrumpida' : (HISTORY_LABELS[raw] || raw || '—');
      return '<div class="maios-history-row"><span>' + escapeHtml(h.version) + '</span><span>' +
        escapeHtml(label) + '</span><span>' + fmtDate(h.timestamp) + '</span></div>';
    }).join('');
    return '<div class="maios-update-history"><div class="label">Historial</div>' + rows + '</div>';
  }

  /* ---- Dashboard (compact) ---- */
  function renderDashboardBanner(status, versionInfo) {
    const el = document.getElementById('maios-dashboard-update');
    if (!el) return;

    const cur = installedVersion(status, versionInfo);
    const st = status.state || 'idle';
    const target = status.targetVersion;
    const manifest = status.manifest || {};
    const dl = status.download || {};
    const pct = dl.percent;
    const hasPct = typeof pct === 'number' && pct > 0;
    const busy = isBusy(st);
    const postponedTarget = (status.postponed && status.manifest && status.manifest.version) || target;
    const statusText = dashboardStatusText(status, versionInfo);
    const dotClass = st === 'up_to_date' || st === 'completed' ? 'ok' :
      isUpdateAvailable(st) || st === 'ready_to_install' ? 'update' :
      st === 'failed' || st === 'offline' ? 'warn' :
      busy ? 'busy' : '';

    let actions = '<button type="button" class="btn btn-ghost btn-sm" id="maios-dash-refresh"' +
      (busy ? ' disabled' : '') + '>Buscar</button>';

    if (st === 'available' && !busy) {
      actions += '<button type="button" class="btn btn-primary btn-sm" id="maios-dash-download">Descargar</button>';
    }
    if (st === 'ready_to_install' && !busy) {
      actions += '<button type="button" class="btn btn-primary btn-sm" id="maios-dash-install">Reiniciar ahora</button>';
    }

    let progressHtml = '';
    if (st === 'downloading' || st === 'verifying' || st === 'backing_up' || st === 'installing' || st === 'restarting') {
      progressHtml =
        '<div class="maios-dash-update-progress">' +
        progressBar(st === 'downloading' && hasPct ? pct : null, st !== 'downloading' || !hasPct) +
        (st === 'downloading' && hasPct
          ? '<div class="meta">Descargando… ' + pct + '% · ' + fmtBytes(dl.bytesReceived) + ' / ' + fmtBytes(dl.totalBytes) + '</div>'
          : '') +
        '</div>';
    }

    const notesHtml = isUpdateAvailable(st) && !busy ? renderNotes(manifest.releaseNotes, true) : '';

    el.innerHTML =
      '<div class="maios-dash-update">' +
      '<div class="maios-dash-update-head">' +
      '<span class="maios-dash-update-dot ' + dotClass + '"></span>' +
      '<div class="maios-dash-update-meta">' +
      '<div class="maios-dash-update-ver">' + escapeHtml(dashboardCompactLine(status, versionInfo)) + '</div>' +
      ((st !== 'up_to_date' && st !== 'completed' && st !== 'idle') || status.postponed
        ? '<div class="maios-dash-update-status">' +
          (status.postponed && postponedTarget
            ? 'Actualización ' + escapeHtml(postponedTarget) + ' pospuesta — reanúdala en Ajustes'
            : escapeHtml(statusText)) +
          '</div>'
        : '') +
      '</div></div>' +
      notesHtml +
      progressHtml +
      '<div class="maios-dash-update-actions">' + actions + '</div>' +
      '</div>';

    bindDashboardActions();
  }

  async function checkForUpdates(force) {
    try {
      await api('/api/updates/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: force !== false }),
        timeoutMs: 45000,
      });
    } catch (e) {
      console.warn('Update check failed/timed out', e);
      showToast('No se pudo comprobar actualizaciones — comprueba tu conexión');
    }
    await refreshAll();
  }

  async function downloadUpdate() {
    // Arranca el poll ANTES del POST: el runtime descarga de forma bloqueante
    // y sin esto la UI no mostraria progreso hasta que acabase la descarga.
    startPolling();
    const st = await api('/api/updates/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    await refreshAll();
    if (st.state !== 'ready_to_install' && st.state !== 'downloading' && st.state !== 'verifying') {
      throw new Error(st.message || st.error || 'Error al descargar');
    }
    if (st.state === 'downloading' || st.state === 'verifying') startPolling();
    return st;
  }

  async function installUpdate() {
    const targetVersion = (cachedStatus && cachedStatus.targetVersion) || '';
    showInstallOverlay(targetVersion);

    try {
      const st = await api('/api/updates/status');
      if (st.state !== 'ready_to_install') {
        throw new Error(st.message || st.error || 'La actualización no está lista para instalar');
      }

      setInstallOverlayStep('Preparando actualización…', 0);

      const install = await api('/api/updates/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });

      if (install.state !== 'restarting') {
        throw new Error(install.message || install.error || 'Error al instalar');
      }

      setInstallOverlayStep('Cerrando VANOVA…', 1);

      if (window.maios && window.maios.quitForUpdate) {
        try {
          await window.maios.quitForUpdate();
        } catch (_) {}
      }
      setInstallOverlayStep('Instalando actualización…', 2);
    } catch (e) {
      hideInstallOverlay();
      try {
        await api('/api/updates/status');
        await refreshAll();
      } catch (_) {}
      throw e;
    }
  }

  function bindSettingsActions() {
    const checkBtn = document.getElementById('maios-check-updates');
    const downloadBtn = document.getElementById('maios-download-update');
    const installBtn = document.getElementById('maios-install-update');
    const cancelBtn = document.getElementById('maios-cancel-update');
    const retryBtn = document.getElementById('maios-retry-update');
    const postponeBtn = document.getElementById('maios-postpone-update');
    const resumeBtn = document.getElementById('maios-resume-update');

    if (checkBtn) {
      checkBtn.onclick = async function () {
        checkBtn.disabled = true;
        try { await checkForUpdates(true); } catch (e) { console.error(e); }
        finally { checkBtn.disabled = false; }
      };
    }
    if (resumeBtn) {
      resumeBtn.onclick = async function () {
        resumeBtn.disabled = true;
        try { await checkForUpdates(true); } catch (e) { console.error(e); }
        finally { if (resumeBtn) resumeBtn.disabled = false; }
      };
    }
    if (downloadBtn) {
      downloadBtn.onclick = async function () {
        downloadBtn.disabled = true;
        try {
          await downloadUpdate();
        } catch (e) {
          console.error(e);
          showToast(e.message || 'Error al descargar');
          downloadBtn.disabled = false;
          await refreshAll();
        }
      };
    }
    if (installBtn) {
      installBtn.onclick = async function () {
        installBtn.disabled = true;
        try {
          await installUpdate();
        } catch (e) {
          console.error(e);
          showToast(e.message || 'Error al instalar — revisa Ajustes > Actualizaciones');
          installBtn.disabled = false;
          await refreshAll();
        }
      };
    }
    if (cancelBtn) {
      cancelBtn.onclick = async function () {
        await api('/api/updates/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        await refreshAll();
      };
    }
    if (retryBtn) {
      retryBtn.onclick = async function () {
        retryBtn.disabled = true;
        try {
          await downloadUpdate();
        } catch (e) {
          showToast(e.message || 'Error al reintentar');
          retryBtn.disabled = false;
        }
      };
    }
    if (postponeBtn) {
      postponeBtn.onclick = async function () {
        try {
          await postponeUpdate((cachedStatus && cachedStatus.targetVersion) || '');
          modalDismissedVersion = (cachedStatus && cachedStatus.targetVersion) || null;
          hideUpdateModal();
          await refreshAll();
        } catch (e) {
          showToast('No se pudo posponer la actualización');
        }
      };
    }
  }

  function bindDashboardActions() {
    const refreshBtn = document.getElementById('maios-dash-refresh');
    const downloadBtn = document.getElementById('maios-dash-download');
    const installBtn = document.getElementById('maios-dash-install');

    if (refreshBtn) {
      refreshBtn.onclick = async function () {
        refreshBtn.disabled = true;
        try { await checkForUpdates(true); } catch (e) { console.error(e); }
        finally { if (refreshBtn) refreshBtn.disabled = isBusy((cachedStatus && cachedStatus.state) || ''); }
      };
    }
    if (downloadBtn) {
      downloadBtn.onclick = async function () {
        downloadBtn.disabled = true;
        try {
          await downloadUpdate();
        } catch (e) {
          console.error(e);
          showToast(e.message || 'Error al descargar');
          downloadBtn.disabled = false;
          await refreshAll();
        }
      };
    }
    if (installBtn) {
      installBtn.onclick = async function () {
        installBtn.disabled = true;
        try {
          await installUpdate();
        } catch (e) {
          console.error(e);
          showToast(e.message || 'Error al instalar — revisa Ajustes > Actualizaciones');
          installBtn.disabled = false;
          await refreshAll();
        }
      };
    }
  }

  async function refreshAll() {
    try {
      const [status, versionInfo] = await Promise.all([
        api('/api/updates/status'),
        api('/api/version'),
      ]);
      cachedStatus = status;
      cachedVersion = versionInfo;

      const st = status.state || 'idle';
      if (st === 'failed' || st === 'cancelled' || st === 'completed' ||
          st === 'ready_to_install' || st === 'available' || st === 'idle') {
        if (st !== 'ready_to_install' && st !== 'available' && st !== 'failed') {
          hideInstallOverlay();
        }
      }

      renderUpdateSection(status, versionInfo);
      renderDashboardBanner(status, versionInfo);
      updateNavBadge(status);
      updateHeaderIndicator(status);
      maybeNotifyUpdate(status);
      schedulePeriodicCheck(status);

      if (isBusy(status.state)) startPolling();
      else stopPolling();
    } catch (e) {
      console.warn('Update center offline', e);
      if (window.maios && window.maios.restartRuntime && !window._maiosUpdateRestartTried) {
        window._maiosUpdateRestartTried = true;
        try {
          const rr = await window.maios.restartRuntime();
          if (rr && rr.ok) {
            await refreshAll();
            return;
          }
        } catch (_) {}
      }
      const offline = { state: 'offline', message: 'Servicio de actualizaciones no disponible' };
      cachedStatus = offline;
      renderUpdateSection(offline, cachedVersion);
      renderDashboardBanner(offline, cachedVersion);
      updateHeaderIndicator(offline);
    }
  }

  function schedulePeriodicCheck(status) {
    if (periodicCheckTimer) {
      clearTimeout(periodicCheckTimer);
      periodicCheckTimer = null;
    }
    const interval = checkIntervalMs(status);
    periodicCheckTimer = setTimeout(async function () {
      try {
        await api('/api/updates/check', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ force: false }),
        });
        await refreshAll();
      } catch (_) {
        schedulePeriodicCheck(cachedStatus || {});
      }
    }, interval);
  }

  function showToast(msg) {
    let t = document.getElementById('maios-update-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'maios-update-toast';
      t.className = 'maios-update-toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(function () { t.classList.remove('show'); }, 5000);
  }

  var INSTALL_STEPS = ['Preparando', 'Cerrando VANOVA', 'Instalando actualización', 'Reiniciando VANOVA'];

  function showInstallOverlay(version) {
    injectStyles();
    hideInstallOverlay();
    const overlay = document.createElement('div');
    overlay.id = 'maios-install-overlay';
    overlay.innerHTML =
      '<div class="maios-install-overlay-card">' +
      '<div class="maios-install-overlay-title">Actualizando VANOVA</div>' +
      (version ? '<div class="maios-install-overlay-ver">Versión ' + escapeHtml(version) + '</div>' : '') +
      '<div class="maios-install-overlay-steps" id="maios-install-steps">' +
      INSTALL_STEPS.map(function (s, i) {
        return '<div class="maios-install-step" data-step="' + i + '">' + escapeHtml(s) + '</div>';
      }).join('') +
      '</div>' +
      '<div class="maios-install-overlay-detail" id="maios-install-detail">Preparando actualización…</div>' +
      '<div class="maios-update-progress indeterminate"><div class="bar pulse"></div></div>' +
      '</div>';
    document.body.appendChild(overlay);
    requestAnimationFrame(function () { overlay.classList.add('show'); });
  }

  function setInstallOverlayStep(detail, stepIndex) {
    const detailEl = document.getElementById('maios-install-detail');
    if (detailEl) detailEl.textContent = detail;
    const steps = document.querySelectorAll('.maios-install-step');
    steps.forEach(function (el, i) {
      el.classList.remove('active', 'done');
      if (i < stepIndex) el.classList.add('done');
      else if (i === stepIndex) el.classList.add('active');
    });
  }

  function hideInstallOverlay() {
    const overlay = document.getElementById('maios-install-overlay');
    if (overlay) overlay.remove();
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(refreshAll, 2000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function injectStyles() {
    if (document.getElementById('maios-update-styles')) return;
    const s = document.createElement('style');
    s.id = 'maios-update-styles';
    s.textContent =
      '#maios-update-center .maios-kv{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.06)}' +
      '.maios-update-progress{height:5px;background:rgba(255,255,255,.08);border-radius:3px;overflow:hidden;margin:8px 0}' +
      '.maios-update-progress .bar{height:100%;background:var(--accent,#c45c4a);transition:width .2s}' +
      '.maios-update-progress.indeterminate .bar{width:30%;animation:maios-up-pulse 1.2s infinite}' +
      '@keyframes maios-up-pulse{0%,100%{margin-left:0}50%{margin-left:70%}}' +
      '.maios-update-actions,.maios-dash-update-actions{margin-top:12px;display:flex;gap:8px;flex-wrap:wrap}' +
      '.maios-update-notes ul{margin:6px 0 0 16px;font-size:12px;color:var(--text-2)}' +
      '.maios-update-notes .label{font-size:11px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:.04em;margin-top:8px}' +
      '.maios-update-msg{font-size:12px;color:var(--text-2);margin-top:8px}' +
      '.maios-update-msg.subtle{font-size:12px;color:var(--text-3);margin-top:8px}' +
      '.maios-update-error{margin-top:12px;padding:12px 14px;border-radius:8px;background:rgba(220,38,38,.12);border:1px solid rgba(220,38,38,.35)}' +
      '.maios-update-error-title{font-size:13px;font-weight:700;color:#f87171;margin-bottom:4px}' +
      '.maios-update-error-detail{font-size:12px;color:var(--text-2);line-height:1.45}' +
      '.update-badge{color:#DC2626;margin-left:4px}' +
      '.maios-update-toast{position:fixed;bottom:24px;right:24px;background:var(--surface);border:1px solid var(--border);padding:12px 16px;border-radius:8px;opacity:0;transition:opacity .2s;z-index:9999;font-size:13px}' +
      '.maios-update-toast.show{opacity:1}' +
      '.maios-history-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px;padding:4px 0;color:var(--text-3)}' +
      '.maios-dash-update{background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px}' +
      '.maios-dash-update-head{display:flex;align-items:flex-start;gap:10px}' +
      '.maios-dash-update-dot{width:8px;height:8px;border-radius:50%;margin-top:5px;flex-shrink:0;background:var(--text-3)}' +
      '.maios-dash-update-dot.ok{background:var(--success)}' +
      '.maios-dash-update-dot.update{background:#DC2626;box-shadow:0 0 8px rgba(220,38,38,.45)}' +
      '.maios-dash-update-dot.warn{background:var(--warning)}' +
      '.maios-dash-update-dot.busy{background:var(--text-3);animation:maios-up-pulse 1.2s infinite}' +
      '.maios-dash-update-ver{font-size:12px;font-weight:600;color:var(--text)}' +
      '.maios-dash-update-status{font-size:12px;color:var(--text-2);margin-top:2px;line-height:1.4}' +
      '.maios-dash-update .btn-sm{height:32px;padding:0 12px;font-size:12px}' +
      '.maios-dash-update-progress{margin-top:10px}' +
      '.maios-dash-update-progress .meta{font-size:11px;color:var(--text-3);margin-top:4px}' +
      '#hdr-update{display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:var(--radius-pill);border:1px solid var(--border);font-size:11px;color:var(--text-3);background:var(--surface-2);cursor:default;transition:var(--trans)}' +
      '#hdr-update.has-update{border-color:var(--accent);color:var(--accent);background:var(--accent-soft,rgba(196,92,74,.08))}' +
      '#hdr-update.busy{color:var(--text-2)}' +
      '#hdr-update .hdr-up-dot{width:6px;height:6px;border-radius:50%;background:currentColor}' +
      '#maios-install-overlay{position:fixed;inset:0;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;z-index:100000;opacity:0;transition:opacity .15s}' +
      '#maios-install-overlay.show{opacity:1}' +
      '.maios-install-overlay-card{background:var(--surface,#1e1e24);border:1px solid var(--border,rgba(255,255,255,.1));border-radius:12px;padding:28px 32px;min-width:340px;max-width:420px;box-shadow:0 16px 48px rgba(0,0,0,.5)}' +
      '.maios-install-overlay-title{font-size:18px;font-weight:700;color:var(--text,#fff);margin-bottom:6px}' +
      '.maios-install-overlay-ver{font-size:13px;color:var(--text-2,#aaa);margin-bottom:18px}' +
      '.maios-install-overlay-steps{margin-bottom:14px}' +
      '.maios-install-step{font-size:13px;color:var(--text-3,#777);padding:3px 0;transition:color .2s}' +
      '.maios-install-step.active{color:var(--accent,#c45c4a);font-weight:600}' +
      '.maios-install-step.active::before{content:">> ";color:var(--accent,#c45c4a)}' +
      '.maios-install-step.done{color:var(--success,#4ade80)}' +
      '.maios-install-step.done::before{content:"[OK] ";color:var(--success,#4ade80)}' +
      '.maios-install-overlay-detail{font-size:12px;color:var(--text-2,#aaa);margin-bottom:12px}' +
      '#maios-update-modal{position:fixed;inset:0;z-index:99998;opacity:0;transition:opacity .2s;pointer-events:none}' +
      '#maios-update-modal.show{opacity:1;pointer-events:auto}' +
      '.maios-update-modal-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;padding:24px}' +
      '.maios-update-modal-card{background:var(--surface,#1e1e24);border:1px solid var(--border,rgba(255,255,255,.12));border-radius:14px;padding:24px 28px;max-width:440px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.45)}' +
      '.maios-update-modal-title{font-size:17px;font-weight:700;color:var(--text,#fff);margin-bottom:12px}' +
      '.maios-update-modal-status{font-size:13px;color:var(--text-2,#aaa);margin:8px 0;line-height:1.45}' +
      '.maios-update-modal-actions{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}';
    document.head.appendChild(s);
  }

  function ensureHeaderIndicator() {
    if (document.getElementById('hdr-update')) return;
    const hdrIcons = document.querySelector('.hdr-icons');
    if (!hdrIcons) return;
    const el = document.createElement('div');
    el.id = 'hdr-update';
    el.innerHTML = '<span class="hdr-up-dot"></span><span>Actualizaciones</span>';
    hdrIcons.parentNode.insertBefore(el, hdrIcons.nextSibling);
  }

  window.maiosUpdateCenter = {
    mount: function (containerId) {
      injectStyles();
      ensureHeaderIndicator();
      const host = document.getElementById(containerId || 'settings-updates-host');
      if (!host) return;
      if (!document.getElementById('maios-update-center')) {
        const div = document.createElement('div');
        div.id = 'maios-update-center';
        host.appendChild(div);
      }
      refreshAll();
    },

    mountDashboard: function () {
      injectStyles();
      ensureHeaderIndicator();
      const host = document.getElementById('maios-dashboard-update-host');
      if (!host) return;
      if (!document.getElementById('maios-dashboard-update')) {
        const div = document.createElement('div');
        div.id = 'maios-dashboard-update';
        host.appendChild(div);
      }
      renderDashboardBanner(
        cachedStatus || { state: 'idle' },
        cachedVersion || { version: '…' }
      );
      refreshAll();
    },

    refresh: refreshAll,

    checkOnStartup: async function () {
      injectStyles();
      ensureHeaderIndicator();
      hideInstallOverlay();
      try {
        await api('/api/updates/recovery', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
      } catch (_) {}
      this.mountDashboard();
      await refreshAll();

      if (startupTimer) clearTimeout(startupTimer);
      startupTimer = setTimeout(async function () {
        appReady = true;
        try {
          await api('/api/updates/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force: false }),
          });
          await refreshAll();
        } catch (_) {
          await refreshAll();
        }
      }, STARTUP_DELAY_MS);
    },
  };
})();
