import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = __dirname;
const BASE = 'http://127.0.0.1:8000/';
const USER = 'ceo';
const PASS = 'mooving2026';

const findings = [];
const sections = [
  { key: 'home', label: 'Inicio', nav: 'Inicio' },
  { key: 'insights', label: 'Insights', nav: 'Insights' },
  { key: 'tasks', label: 'Tareas', nav: 'Tareas' },
  { key: 'hermes', label: 'Hermes', nav: 'Hermes' },
  { key: 'integrations', label: 'Integraciones', nav: 'Integraciones' },
  { key: 'products', label: 'Productos', nav: 'Productos' },
  { key: 'diagnostics', label: 'Diagnóstico', nav: 'Diagnóstico' },
  { key: 'settings', label: 'Ajustes', nav: 'Ajustes' },
];

async function shot(page, name) {
  const path = join(OUT, `${name}.png`);
  await page.screenshot({ path, fullPage: true });
  return path;
}

async function text(page, sel) {
  try {
    const el = page.locator(sel).first();
    if (await el.count() === 0) return '';
    return (await el.innerText({ timeout: 2000 })).trim();
  } catch { return ''; }
}

async function bodyText(page) {
  return page.locator('body').innerText();
}

async function login(page) {
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1500);
  const loginVisible = await page.locator('#login:not(.hidden)').isVisible().catch(() => false);
  if (loginVisible) {
    await page.fill('#l-user', USER);
    await page.fill('#l-pass', PASS);
    await page.click('#l-btn');
    await page.waitForSelector('#login.hidden', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);
  }
}

async function navTo(page, label) {
  const link = page.locator(`.nav-item`, { hasText: label }).first();
  if (await link.count()) {
    await link.click();
    await page.waitForTimeout(1800);
    return true;
  }
  findings.push({ severity: 'critico', msg: `Enlace de navegación no encontrado: ${label}` });
  return false;
}

async function analyzeSection(page, key, label) {
  const data = { key, label, screenshot: '', notes: [], issues: [], scoreHints: {} };
  data.screenshot = await shot(page, key);

  const title = await text(page, '.page-title');
  if (title) data.notes.push(`Título: ${title}`);

  const body = await bodyText(page);

  if (key === 'hermes') {
    const hasCargandoContexto = /Cargando contexto/i.test(body);
    const hasBlockingOverlay = await page.locator('.hermes-status-line:not([style*="display:none"])').isVisible().catch(() => false);
    const opPanel = await page.locator('#hermes-op-panel').count();
    const chatLog = await page.locator('#hermes-chat-log').count();
    const attachBtn = await page.locator('[data-act="hermes-attach"]').count();
    const input = await page.locator('#hermes-q').count();
    data.notes.push(`Panel operativo: ${opPanel ? 'presente' : 'ausente'}`);
    data.notes.push(`Chat log: ${chatLog ? 'presente' : 'ausente'}`);
    data.notes.push(`Input pregunta: ${input ? 'sí' : 'no'}`);
    data.notes.push(`Botón adjuntar: ${attachBtn ? 'sí' : 'no'}`);
    if (hasCargandoContexto) data.issues.push('Texto "Cargando contexto" visible — posible bloqueo UX');
    else data.notes.push('"Cargando contexto" NO bloquea la vista');
    const readyStrip = await text(page, '#hermes-ready-strip');
    if (readyStrip) data.notes.push(`Banner estado: ${readyStrip.replace(/\s+/g, ' ').slice(0, 120)}`);
    const sessions = await text(page, '#hermes-sessions');
    if (/Cargando/i.test(sessions)) data.notes.push('Sesiones: aún cargando');
    else if (sessions) data.notes.push(`Sesiones: ${sessions.slice(0, 80)}`);
  }

  if (key === 'products') {
    const hasErrorRow = /error/i.test(body) && /tabla|table|row/i.test(body);
    const hasEmpty = /sin productos|no hay productos|catálogo vacío|importa|empty/i.test(body);
    const hasBanner = await page.locator('.conn-banner, .shopify-warn, [class*="warn"]').count();
    data.notes.push(`Banner Shopify/warning: ${hasBanner ? 'visible' : 'no detectado'}`);
    if (hasEmpty) data.notes.push('Estado vacío detectado (no tabla de error)');
  }

  if (key === 'integrations') {
    const cards = await page.locator('.int-card, .integration-card, [data-int]').count();
    data.notes.push(`Tarjetas integración: ~${cards || 'varias'}`);
    // Try open Shopify drawer
    const shopBtn = page.locator('button, .int-card').filter({ hasText: /Shopify/i }).first();
    if (await shopBtn.count()) {
      await shopBtn.click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(800);
      const drawer = await page.locator('.drawer, #drawer, .drawer-panel').count();
      if (drawer) {
        data.notes.push('Drawer Shopify: se abre');
        data.screenshotDrawer = await shot(page, `${key}-drawer`);
        await page.keyboard.press('Escape');
      }
    }
  }

  if (key === 'diagnostics') {
    const diagItems = await page.locator('.diag-row, .diag-item, .diag-comp, [class*="diag"]').count();
    data.notes.push(`Componentes diagnóstico: ~${diagItems}`);
    const hasConnector = /connector|conector/i.test(body);
    data.notes.push(`Etiqueta Connector/Conector: ${hasConnector ? 'sí' : 'no'}`);
    const hasSpanish = /Diagnóstico|Estado|Conexiones|Actualizar/i.test(body);
    if (!hasSpanish) data.issues.push('Etiquetas posiblemente no en español');
  }

  if (key === 'settings') {
    const versionMatch = body.match(/1\.0\.[0-9]+/g);
    if (versionMatch) data.notes.push(`Versión detectada: ${[...new Set(versionMatch)].join(', ')}`);
    else data.notes.push('Versión 1.0.2 no encontrada en texto visible');
    const updateCenter = await page.locator('#maios-update-center').count();
    data.notes.push(`Update center: ${updateCenter ? 'presente' : 'ausente'}`);
  }

  if (key === 'home') {
    const metrics = await page.locator('.metric-card, .dash-card, .kpi').count();
    data.notes.push(`Bloques/cards visibles: ~${metrics}`);
    const tasksWidget = body.includes('Tareas') || body.includes('tareas');
    data.notes.push(`Widget tareas en inicio: ${tasksWidget ? 'sí' : 'no'}`);
  }

  return data;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'es-ES' });
  const page = await context.newPage();
  const report = { generatedAt: new Date().toISOString(), sections: [], nav: {}, theme: {}, mobile: {}, login: {} };

  try {
    await login(page);
    report.login.screenshot = await shot(page, '00-login-or-home');
    report.login.blocked = !(await page.locator('#app').isVisible().catch(() => false));

    // Sidebar nav audit
    const navItems = await page.locator('.nav-item .nav-label, .nav-item').allInnerTexts().catch(() => []);
    report.nav.items = navItems.map(t => t.trim()).filter(Boolean);
    report.nav.screenshot = await shot(page, '00-sidebar');

    const expectedNav = ['Inicio','Insights','Tareas','Hermes','Integraciones','Productos','Diagnóstico','Ajustes'];
    for (const exp of expectedNav) {
      if (!report.nav.items.some(n => n.includes(exp))) {
        findings.push({ severity: 'medio', msg: `Sidebar: falta o no visible "${exp}"` });
      }
    }

    // Theme toggle
    await navTo(page, 'Ajustes');
    const themeBtn = page.locator('[data-act="theme-toggle"]').first();
    if (await themeBtn.count()) {
      const before = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
      await themeBtn.click();
      await page.waitForTimeout(600);
      const after = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
      report.theme.before = before;
      report.theme.after = after;
      report.theme.screenshotDark = await shot(page, 'settings-dark-theme');
      await themeBtn.click();
      await page.waitForTimeout(400);
    }

    // Sections
    for (const s of sections) {
      await navTo(page, s.nav);
      const data = await analyzeSection(page, s.key, s.label);
      report.sections.push(data);
    }

    // Mobile viewport
    await page.setViewportSize({ width: 390, height: 844 });
    await navTo(page, 'Inicio');
    report.mobile.home = await shot(page, 'mobile-home');
    await navTo(page, 'Hermes');
    report.mobile.hermes = await shot(page, 'mobile-hermes');

  } catch (e) {
    report.error = String(e);
    findings.push({ severity: 'critico', msg: `Error automatización: ${e.message}` });
  } finally {
    await browser.close();
  }

  writeFileSync(join(OUT, 'ux-test-data.json'), JSON.stringify({ report, findings }, null, 2));
  console.log(JSON.stringify({ report, findings }, null, 2));
}

main();
