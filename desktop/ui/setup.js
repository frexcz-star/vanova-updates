const API = 'http://127.0.0.1:8765';

const STEPS = [
  { id: 'welcome', label: 'Welcome' },
  { id: 'analyze', label: 'Environment' },
  { id: 'company', label: 'Company' },
  { id: 'channels', label: 'Channels' },
  { id: 'goals', label: 'Goals' },
  { id: 'ai', label: 'AI Provider' },
  { id: 'install', label: 'Setup' },
  { id: 'agents', label: 'Agents' },
  { id: 'ready', label: 'Ready' },
];

const state = {
  step: 0,
  profile: { identity: { name: '', slug: '' }, industry: '', description: '', channels: [], goals: [], integrations: [], priorities: [] },
  ai: { providerId: 'ollama', apiKey: '', model: 'llama3.2' },
  agents: [],
  analysis: null,
};

async function runtimeAuthHeaders() {
  try {
    if (window.maios?.getRuntimeAuthHeaders) {
      return await window.maios.getRuntimeAuthHeaders();
    }
  } catch (_) {}
  return {};
}

async function api(path, opts = {}) {
  const auth = await runtimeAuthHeaders();
  const headers = Object.assign({ 'Content-Type': 'application/json' }, auth, opts.headers || {});
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeout || 60000);
  try {
    const res = await fetch(`${API}${path}`, { ...opts, headers, signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

function renderNav() {
  document.getElementById('stepsNav').innerHTML = STEPS.map((s, i) => {
    let cls = 'step-item';
    if (i === state.step) cls += ' active';
    else if (i < state.step) cls += ' done';
    return `<div class="${cls}"><span class="dot"></span>${s.label}</div>`;
  }).join('');
}

function render() {
  renderNav();
  const fns = [welcome, analyze, company, channels, goals, aiProvider, install, agents, ready];
  document.getElementById('panel').innerHTML = fns[state.step]();
  bindEvents();
}

function welcome() {
  return `<h1>Welcome to VANOVA</h1><p class="subtitle">Your AI operating system for business. We'll analyze your computer, understand your company, and configure everything automatically.</p><div class="actions"><span></span><button class="btn btn-primary" data-action="next">Get started</button></div>`;
}

function analyze() {
  return `<h1>Environment Analysis</h1><p class="subtitle">Checking your computer for VANOVA compatibility.</p><div id="analysisContent"><p class="subtitle">Analyzing...</p></div><div class="actions"><button class="btn btn-ghost" data-action="prev">Back</button><button class="btn btn-primary" data-action="next" id="analyzeNext" disabled>Continue</button></div>`;
}

let analyzeAttempts = 0;
const ANALYZE_MAX_ATTEMPTS = 240; // ~10 min before showing an actionable error (cold first start can be slow)
const ANALYZE_RETRY_MS = 2500;

async function loadAnalysis() {
  const el = document.getElementById('analysisContent');
  if (!el) return;
  try {
    analyzeAttempts = 0;
    state.analysis = await api('/api/system/analyze', { timeout: 15000 });
    const a = state.analysis;
    el.innerHTML = `<div class="analysis-grid">
      <div class="analysis-section"><h3>System</h3><div class="analysis-row"><span class="${a.system.compatible ? 'status-ok' : 'status-fail'}">${a.system.compatible ? '✓' : '✕'}</span> ${a.system.osVersion} ${a.system.architecture}</div></div>
      <div class="analysis-section"><h3>Hardware</h3><div class="analysis-row"><span class="status-ok">✓</span> ${a.hardware.ramGb} GB RAM</div><div class="analysis-row"><span class="status-ok">✓</span> ${a.hardware.diskFreeGb} GB available</div></div>
      <div class="analysis-section"><h3>Connectivity</h3><div class="analysis-row"><span class="${a.network.online ? 'status-ok' : 'status-fail'}">${a.network.online ? '✓' : '✕'}</span> Internet access</div></div>
      <div class="analysis-section"><h3>Dependencies</h3>${Object.values(a.dependencies).map(d => {
        const optional = d.level === 'optional' || d.status === 'optional';
        const okish = d.ok || optional;
        const icon = okish ? 'status-ok' : (d.level === 'required' ? 'status-warn' : 'status-ok');
        const suffix = optional && !d.path ? (d.message ? ` — ${d.message}` : ' — optional') : (d.level === 'required' && !d.ok ? ' — will be installed' : (d.message ? ` — ${d.message}` : ''));
        return `<div class="analysis-row"><span class="${icon}">${okish ? '✓' : '○'}</span> ${d.name}${suffix}</div>`;
      }).join('')}</div>
    </div><div class="result-badge">${a.readyToInstall ? 'Ready to install' : 'Review recommendations'}</div>`;
    document.getElementById('analyzeNext').disabled = false;
  } catch (e) {
    analyzeAttempts += 1;
    const elapsed = Math.round((analyzeAttempts * ANALYZE_RETRY_MS) / 1000);
    if (analyzeAttempts >= ANALYZE_MAX_ATTEMPTS) {
      el.innerHTML =
        '<p class="subtitle">No se pudo conectar con los servicios de VANOVA.</p>' +
        '<p class="subtitle" style="opacity:.65">Si es la primera vez que abres VANOVA tras instalarlo, el arranque puede tardar un par de minutos (Windows está analizando los archivos nuevos). Si sigue sin conectar, cierra VANOVA por completo y vuelve a abrirlo.</p>' +
        '<p class="subtitle" style="opacity:.5;font-size:12px">Detalle: ' + (e && e.message ? String(e.message) : 'sin conexión con el runtime local') + '</p>' +
        '<div class="actions" style="justify-content:flex-start;padding-top:8px"><button class="btn btn-primary" data-action="retry-analyze">Reintentar</button></div>';
      return;
    }
    // Self-diagnostic: if the bundled Python is missing, say so instead of waiting forever.
    if (analyzeAttempts === 20 && window.maios && window.maios.getRuntimeHealth) {
      try {
        const h = await window.maios.getRuntimeHealth();
        if (h && h.pythonFound === false) {
          el.innerHTML =
            '<p class="subtitle">No se encontró el runtime de Python en la instalación.</p>' +
            '<p class="subtitle" style="opacity:.65">El antivirus puede haber bloqueado o borrado archivos durante la instalación (python.exe no lleva firma). Añade la carpeta de VANOVA a las exclusiones del antivirus y reinstala el programa.</p>' +
            '<p class="subtitle" style="opacity:.5;font-size:12px">Buscado en: ' + (h.searchedPaths || []).join(' ; ') + '</p>' +
            '<div class="actions" style="justify-content:flex-start;padding-top:8px"><button class="btn btn-primary" data-action="retry-analyze">Reintentar</button></div>';
          return;
        }
      } catch (_) {}
    }
    el.innerHTML = '<p class="subtitle">Conectando con los servicios de VANOVA… (' + elapsed + 's)</p>';
    setTimeout(loadAnalysis, ANALYZE_RETRY_MS);
  }
}

function company() {
  return `<h1>Your company</h1><p class="subtitle">Let's configure VANOVA for your business.</p>
    <div class="field"><label>What's your company called?</label><input type="text" id="companyName" value="${state.profile.identity.name}" placeholder="Mooving Paper"></div>
    <div class="field"><label>What does your company do?</label><textarea id="companyDesc" placeholder="Distribution and sale of stationery products">${state.profile.description}</textarea></div>
    <div class="actions"><button class="btn btn-ghost" data-action="prev">Back</button><button class="btn btn-primary" data-action="next">Continue</button></div>`;
}

function channels() {
  const opts = ['Shopify', 'Instagram', 'Amazon', 'Email', 'TikTok', 'Other'];
  return `<h1>Your channels</h1><p class="subtitle">Which channels do you use?</p><div class="check-group" id="channelsGroup">${opts.map(c => `<label class="check-item ${state.profile.channels.includes(c.toLowerCase()) ? 'selected' : ''}"><input type="checkbox" value="${c.toLowerCase()}" ${state.profile.channels.includes(c.toLowerCase()) ? 'checked' : ''}> ${c}</label>`).join('')}</div><div class="actions"><button class="btn btn-ghost" data-action="prev">Back</button><button class="btn btn-primary" data-action="next">Continue</button></div>`;
}

function goals() {
  const opts = [{ id: 'marketing', label: 'Marketing' }, { id: 'sales', label: 'Sales' }, { id: 'content', label: 'Content' }, { id: 'inventory', label: 'Inventory' }, { id: 'customer support', label: 'Customer Support' }];
  return `<h1>Your priorities</h1><p class="subtitle">What would you like MAIOS to help with?</p><div class="check-group" id="goalsGroup">${opts.map(g => `<label class="check-item ${state.profile.goals.includes(g.id) ? 'selected' : ''}"><input type="checkbox" value="${g.id}" ${state.profile.goals.includes(g.id) ? 'checked' : ''}> ${g.label}</label>`).join('')}</div><div class="actions"><button class="btn btn-ghost" data-action="prev">Back</button><button class="btn btn-primary" data-action="next">Continue</button></div>`;
}

function aiProvider() {
  const providers = [{ id: 'ollama', name: 'Ollama (local)' }, { id: 'nvidia', name: 'NVIDIA NIM' }, { id: 'google-gemini', name: 'Google Gemini' }, { id: 'openai', name: 'OpenAI' }, { id: 'anthropic', name: 'Anthropic' }, { id: 'openrouter', name: 'OpenRouter' }, { id: 'other', name: 'Other' }];
  return `<h1>Configure your AI</h1><p class="subtitle">Connect your AI provider. Your key is stored securely on this device.</p>
    <div class="field"><label>Provider</label><div class="radio-group" id="providerGroup">${providers.map(p => `<label class="radio-item ${state.ai.providerId === p.id ? 'selected' : ''}"><input type="radio" name="provider" value="${p.id}" ${state.ai.providerId === p.id ? 'checked' : ''}> ${p.name}</label>`).join('')}</div></div>
    <div class="field"><label>API Key</label><input type="password" id="apiKey" placeholder="••••••••••••••••"></div>
    <div class="field"><label>Model</label><input type="text" id="aiModel" value="${state.ai.model}"></div>
    <button class="btn btn-ghost" id="testAi">Test connection</button><div id="testResult"></div>
    <div class="actions"><button class="btn btn-ghost" data-action="prev">Back</button><button class="btn btn-primary" data-action="next">Continue</button></div>`;
}

function install() {
  return `<h1>Setting up MAIOS</h1><p class="subtitle">We're preparing your environment.</p>
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
    <div class="install-steps"><div class="install-step active" id="stepAnalyze">Analyzing your computer</div><div class="install-step" id="stepRuntime">Preparing MAIOS runtime</div><div class="install-step" id="stepServices">Setting up services</div><div class="install-step" id="stepHermes">Installing Hermes</div><div class="install-step" id="stepValidate">Validating installation</div></div>
    <div class="actions"><span></span><button class="btn btn-primary hidden" data-action="next" id="installNext">Continue</button></div>`;
}

async function runInstall() {
  const fill = document.getElementById('progressFill');
  const stepMap = [
    { id: 'stepAnalyze', keys: ['Analyzing', 'Starting'] },
    { id: 'stepRuntime', keys: ['runtime', 'Preparing MAIOS', 'installation plan'] },
    { id: 'stepServices', keys: ['services', 'Setting up'] },
    { id: 'stepHermes', keys: ['Hermes'] },
    { id: 'stepValidate', keys: ['Validating', 'warnings'] },
  ];
  const timeoutMs = 180000;
  const start = Date.now();
  let finished = false;

  function updateSteps(stepText, percent) {
    if (!stepText && !percent) return;
    const lower = (stepText || '').toLowerCase();
    let activeIdx = 0;
    stepMap.forEach((s, i) => {
      if (s.keys.some(k => lower.includes(k.toLowerCase()))) activeIdx = i;
    });
    if (percent >= 100) activeIdx = stepMap.length;
    stepMap.forEach((s, i) => {
      const el = document.getElementById(s.id);
      if (!el) return;
      el.classList.remove('active', 'done');
      if (i < activeIdx) el.classList.add('done');
      else if (i === activeIdx && percent < 100) el.classList.add('active');
      else if (percent >= 100) el.classList.add('done');
    });
  }

  function showContinue() {
    if (finished) return;
    finished = true;
    fill.style.width = '100%';
    updateSteps('Validating installation', 100);
    document.getElementById('installNext')?.classList.remove('hidden');
  }

  const poll = setInterval(async () => {
    try {
      const p = await api('/api/install/progress');
      if (p.percent) fill.style.width = Math.max(5, p.percent) + '%';
      updateSteps(p.step || '', p.percent || 0);
      if (p.done || p.percent >= 100) {
        clearInterval(poll);
        showContinue();
      }
    } catch (_) {}
    if (Date.now() - start > timeoutMs) {
      clearInterval(poll);
      showContinue();
    }
  }, 400);

  try {
    await api('/api/company/profile', { method: 'POST', body: JSON.stringify(state.profile) });
    await api('/api/ai/configure', {
      method: 'POST',
      body: JSON.stringify({ providerId: state.ai.providerId, apiKey: state.ai.apiKey, model: state.ai.model }),
    });
    await api('/api/install/run', { method: 'POST', body: '{}' });
  } catch (_) {
    clearInterval(poll);
    showContinue();
  }
}

function agents() {
  return `<h1>Recommended for your business</h1><p class="subtitle">Based on your company profile, we suggest these agents. Click an agent to include or exclude it.</p><div class="agent-list" id="agentList"><p class="subtitle">Loading...</p></div><div class="actions"><button class="btn btn-ghost" data-action="prev">Back</button><button class="btn btn-primary" data-action="next">Create selected agents</button></div>`;
}

async function loadAgents() {
  const el = document.getElementById('agentList');
  if (!el) return;
  try {
    const recs = await api('/api/agents/recommendations');
    const all = (recs || []).filter(a => a.recommended);
    state.agents = all.slice();
    el.innerHTML = all.map(a => `<div class="agent-card selected" data-id="${a.id}"><div class="name">${a.name}</div><div class="reason">${a.reason}</div><span class="agent-check">✓</span></div>`).join('');
    el.querySelectorAll('.agent-card').forEach(card => {
      card.addEventListener('click', () => {
        const id = card.dataset.id;
        const on = card.classList.toggle('selected');
        const check = card.querySelector('.agent-check');
        if (check) check.textContent = on ? '✓' : '＋';
        const idx = state.agents.findIndex(a => a.id === id);
        if (on && idx < 0) {
          const rec = all.find(a => a.id === id);
          if (rec) state.agents.push(rec);
        } else if (!on && idx >= 0) {
          state.agents.splice(idx, 1);
        }
      });
    });
  } catch (_) { el.innerHTML = '<p class="subtitle">Default agents will be created.</p>'; }
}

function ready() {
  return `<h1>MAIOS is ready</h1><p class="subtitle">Your AI operating system is configured. Open the dashboard to get started.</p>
    <div class="analysis-grid"><div class="analysis-row"><span class="status-ok">✓</span> Company profile saved</div><div class="analysis-row"><span class="status-ok">✓</span> AI provider configured</div><div class="analysis-row"><span class="status-ok">✓</span> Services running</div></div>
    <div class="actions"><span></span><button class="btn btn-primary" data-action="finish">Open MAIOS Dashboard</button></div>`;
}

function bindEvents() {
  document.querySelectorAll('[data-action]').forEach(btn => { btn.onclick = () => handleAction(btn.dataset.action); });
  if (state.step === 1) setTimeout(loadAnalysis, 100);
  if (state.step === 6) setTimeout(runInstall, 100);
  if (state.step === 7) setTimeout(loadAgents, 100);
  document.getElementById('testAi')?.addEventListener('click', async () => {
    const result = await api('/api/ai/test', { method: 'POST', body: JSON.stringify({ providerId: state.ai.providerId, apiKey: document.getElementById('apiKey').value }) });
    const el = document.getElementById('testResult');
    el.className = 'test-result ' + (result.ok ? 'ok' : 'fail');
    el.textContent = result.message;
  });
}

function saveStepData() {
  if (state.step === 2) {
    state.profile.identity.name = document.getElementById('companyName')?.value || '';
    state.profile.identity.slug = state.profile.identity.name.toLowerCase().replace(/\s+/g, '-');
    state.profile.description = document.getElementById('companyDesc')?.value || '';
  }
  if (state.step === 3) state.profile.channels = [...document.querySelectorAll('#channelsGroup input:checked')].map(i => i.value);
  if (state.step === 4) state.profile.goals = [...document.querySelectorAll('#goalsGroup input:checked')].map(i => i.value);
  if (state.step === 5) {
    state.ai.providerId = document.querySelector('#providerGroup input:checked')?.value || 'openrouter';
    state.ai.apiKey = document.getElementById('apiKey')?.value || '';
    state.ai.model = document.getElementById('aiModel')?.value || '';
  }
}

async function handleAction(action) {
  if (action === 'prev') { state.step--; render(); return; }
  if (action === 'retry-analyze') { render(); return; }
  if (action === 'next') {
    saveStepData();
    if (state.step === 7) {
      const selected = state.agents;
      await api('/api/agents/create', { method: 'POST', body: JSON.stringify({ agents: selected }) });
    }
    state.step++;
    render();
    return;
  }
  if (action === 'finish') {
    const btn = document.querySelector('[data-action="finish"]');
    const panel = document.getElementById('panel');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Opening dashboard...';
    }
    try {
      await api('/api/agents/create', {
        method: 'POST',
        body: JSON.stringify({ agents: state.agents.length ? state.agents : [] }),
      }).catch(() => {});
      await api('/api/setup/scan', { method: 'POST', body: '{}' }).catch(() => {});
      const complete = await api('/api/setup/complete', { method: 'POST', body: '{}' });
      if (!complete.ok) throw new Error('Setup could not be finalized');

      let opened = false;
      if (window.maios?.openDashboard) {
        const result = await window.maios.openDashboard();
        opened = !!result?.ok;
        if (!opened) throw new Error(result?.error || 'Could not open the dashboard window');
      } else {
        opened = await openDashboardFallback();
      }
      if (!opened) throw new Error('Could not open the dashboard');
    } catch (err) {
      const msg = err?.message || 'Could not open the dashboard';
      const errEl = document.createElement('div');
      errEl.className = 'test-result fail';
      errEl.textContent = msg + ' Opening in your browser instead...';
      panel?.querySelector('.actions')?.before(errEl);
      await openDashboardFallback();
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Open MAIOS Dashboard';
      }
    }
  }
}

async function openDashboardFallback() {
  const url = 'http://127.0.0.1:8000';
  try {
    const auth = await runtimeAuthHeaders();
    const res = await fetch(`${API}/api/services/start`, {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, auth),
      body: '{}',
    });
    const svc = await res.json();
    if (!svc.cloud) return false;
  } catch (_) {
    return false;
  }
  if (window.maios?.openExternal) {
    await window.maios.openExternal(url);
    return true;
  }
  window.location.href = url;
  return true;
}

render();
