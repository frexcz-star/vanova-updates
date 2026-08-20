/* ============================================================
   VANOVA Themes — gestor de temas de la interfaz.
   Expone window.VANOVAThemes; el selector vive en Ajustes, no flota sobre la app.
   ============================================================ */
(function () {
  'use strict';

  var THEME_KEY = 'vanova_theme';
  var LOCK_KEY = 'vanova_theme_locked'; // '1' = user pinned the theme manually

  // id -> { name, nightOf }  (nightOf: if this is the dark variant of a day theme)
  var THEMES = [
    { id: 'ember', name: 'Ember' },
    { id: 'ember-night', name: 'Ember · Noche', nightOf: 'ember' },
    { id: 'ocean', name: 'Océano' },
    { id: 'ocean-night', name: 'Océano · Noche', nightOf: 'ocean' },
    { id: 'forest', name: 'Bosque' },
    { id: 'forest-night', name: 'Bosque · Noche', nightOf: 'forest' },
    { id: 'midnight', name: 'Medianoche' },
    { id: 'slate', name: 'Pizarra' },
    { id: 'rose', name: 'Rosa' },
    { id: 'amber', name: 'Ámbar' },
    { id: 'mint', name: 'Menta' },
    { id: 'aurora', name: 'Aurora' },
    { id: 'graphite', name: 'Grafito' },
    { id: 'sunset', name: 'Atardecer' },
    { id: 'mono', name: 'Mono' },
    { id: 'mono-night', name: 'Mono · Noche', nightOf: 'mono' }
  ];

  function safeGet(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }
  function safeSet(key, val) {
    try { window.localStorage.setItem(key, val); } catch (e) {}
  }

  function isDarkNow() {
    var d = new Date();
    var h = d.getHours();
    return h < 6 || h >= 20; // night 20:00–06:00
  }

  function applyTheme(id) {
    if (!id) return;
    document.documentElement.setAttribute('data-theme', id);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      var bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
      if (bg) meta.setAttribute('content', bg);
    }
  }

  function isNightVariant(id) {
    var t = getThemeById(id);
    return !!(t && t.nightOf);
  }

  function getThemeById(id) {
    for (var i = 0; i < THEMES.length; i++) {
      if (THEMES[i].id === id) return THEMES[i];
    }
    return null;
  }

  function autoDayNight() {
    var current = getCurrent();
    var locked = safeGet(LOCK_KEY) === '1';
    if (locked) return;
    // Only auto-switch themes that have a night variant.
    var dayTheme = null;
    for (var i = 0; i < THEMES.length; i++) {
      var t = THEMES[i];
      if (t.nightOf) {
        dayTheme = t.nightOf;
        break;
      }
    }
    // If the current theme is (or derives from) an auto theme, switch day/night.
    var t = getThemeById(current);
    var base = (t && t.nightOf) ? t.nightOf : current;
    var autoThemes = ['ember', 'ocean', 'forest', 'mono'];
    if (autoThemes.indexOf(base) === -1) return;
    var target = isDarkNow() ? base + '-night' : base;
    if (target !== current) {
      applyTheme(target);
      safeSet(THEME_KEY, target);
      safeSet('maios-theme', target);
    }
  }

  function getCurrent() {
    return safeGet(THEME_KEY) || 'ember';
  }

  function setTheme(id, opts) {
    opts = opts || {};
    var t = getThemeById(id);
    if (!t) return;
    // Pin it manually if requested (or if the user clicked a theme in the picker).
    if (opts.pin !== false) {
      safeSet(LOCK_KEY, '1');
    }
    applyTheme(id);
    safeSet(THEME_KEY, id);
    // Keep the legacy key in sync so older dashboard shells do not override
    // the selected palette after a reload.
    safeSet('maios-theme', id);
    // Notify the dashboard so Ajustes re-renders the active highlight.
    document.dispatchEvent(new CustomEvent('vanova:theme-changed', { detail: { theme: id } }));
  }

  function next() {
    var cur = getCurrent();
    var idx = THEMES.findIndex(function (t) { return t.id === cur; });
    var n = (idx + 1) % THEMES.length;
    setTheme(THEMES[n].id, { pin: true });
  }

  function prev() {
    var cur = getCurrent();
    var idx = THEMES.findIndex(function (t) { return t.id === cur; });
    var n = (idx - 1 + THEMES.length) % THEMES.length;
    setTheme(THEMES[n].id, { pin: true });
  }

  /* ---------- Theme palette helper (used by Settings) ---------- */
  function paletteFor(id) {
    // Theme variables are scoped to html[data-theme], so a child probe alone
    // would incorrectly inherit the currently active palette. Temporarily
    // switch the root, read the computed variables, then restore it.
    var root = document.documentElement;
    var previous = root.getAttribute('data-theme');
    var t = getThemeById(id);
    if (t) root.setAttribute('data-theme', id);
    var cs = getComputedStyle(root);
    var accent = cs.getPropertyValue('--accent').trim() || '#888';
    var bg = cs.getPropertyValue('--bg').trim() || '#fff';
    var surface = cs.getPropertyValue('--surface').trim() || '#fff';
    if (previous) root.setAttribute('data-theme', previous);
    else root.removeAttribute('data-theme');
    return { accent: accent, bg: bg, surface: surface };
  }

  /** Build the theme list HTML for the Settings panel. */
  function renderThemeListHTML() {
    var current = getCurrent();
    return THEMES.map(function (t) {
      var p = paletteFor(t.id);
      var isActive = t.id === current;
      var auto = t.nightOf ? ' <span style="opacity:.65;font-size:11px;font-weight:400">(auto día/noche)</span>' : '';
      return '<div class="vn-theme-item' + (isActive ? ' active' : '') + '" data-theme-id="' + t.id + '" data-act="theme" data-theme="' + t.id + '">' +
        '<span class="vn-theme-swatch">' +
        '<span style="background:' + p.accent + '"></span>' +
        '<span style="background:' + p.bg + '"></span>' +
        '<span style="background:' + p.surface + '"></span>' +
        '</span>' +
        '<span class="vn-theme-name">' + t.name + auto + '</span>' +
        '</div>';
    }).join('');
  }

  /** Expose helpers so the dashboard Settings page can render the picker. */
  window.VANOVAThemes = {
    getThemes: function () { return THEMES.slice(); },
    getCurrent: getCurrent,
    setTheme: setTheme,
    next: next,
    prev: prev,
    autoDayNight: autoDayNight,
    isNightVariant: isNightVariant,
    renderThemeListHTML: renderThemeListHTML,
    paletteFor: paletteFor
  };

  function init() {
    var saved = getCurrent();
    var t = getThemeById(saved);
    if (!t) saved = 'ember';
    applyTheme(saved);
    safeSet(THEME_KEY, saved);
    autoDayNight();
    setInterval(autoDayNight, 60 * 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
