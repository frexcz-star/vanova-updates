const { app, BrowserWindow, ipcMain, shell, session, Tray, Menu, Notification } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const http = require('http');

const isDev = !app.isPackaged;
const DASHBOARD_URL = 'http://127.0.0.1:8000';
const RUNTIME_URL = 'http://127.0.0.1:8765';
const RUNTIME_PORT = 8765;
const RUNTIME_START_ATTEMPTS = 5;
const RUNTIME_WAIT_PER_ATTEMPT_MS = 30000;
const RUNTIME_SLOW_EXTRA_MS = 120000;

function getVersion() {
  try {
    const vf = isDev
      ? path.join(__dirname, '..', 'version.json')
      : path.join(process.resourcesPath, 'vanova', 'version.json');
    if (fs.existsSync(vf)) {
      return JSON.parse(fs.readFileSync(vf, 'utf8')).version;
    }
  } catch (_) {}
  return app.getVersion();
}

function getAppRoot() {
  if (isDev) return path.join(__dirname, '..');
  return path.join(process.resourcesPath, 'vanova');
}

function getPython() {
  const root = getAppRoot();
  const candidates = [
    path.join(root, 'python', 'python.exe'),
    path.join(root, 'python-bundle', 'python.exe'),
    path.join(root, 'python-bundle', 'Scripts', 'python.exe'),
    path.join(root, '.venv', 'Scripts', 'python.exe'),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  const localBase = process.env.LOCALAPPDATA || process.env.APPDATA || '';
  if (localBase) {
    const userVenv = path.join(localBase, 'VANOVA', 'venv', 'Scripts', 'python.exe');
    if (fs.existsSync(userVenv)) return userVenv;
  }
  if (isDev) return 'python';
  return null;
}

// Self-diagnostic state: why the runtime may be failing to start (surfaced in the
// setup wizard so clients/AV issues are visible without digging through logs).
let lastRuntimeStartError = null;
let lastPythonProbe = null;

function getPythonProbe() {
  const root = getAppRoot();
  const paths = [
    path.join(root, 'python', 'python.exe'),
    path.join(root, 'python-bundle', 'python.exe'),
    path.join(root, 'python-bundle', 'Scripts', 'python.exe'),
    path.join(root, '.venv', 'Scripts', 'python.exe'),
  ];
  const localBase = process.env.LOCALAPPDATA || process.env.APPDATA || '';
  if (localBase) paths.push(path.join(localBase, 'VANOVA', 'venv', 'Scripts', 'python.exe'));
  const found = paths.find((p) => fs.existsSync(p)) || null;
  return { found, searched: paths };
}

function getRuntimeHealthSnapshot() {
  const probe = lastPythonProbe || getPythonProbe();
  return {
    pythonFound: !!probe.found,
    pythonPath: probe.found,
    searchedPaths: probe.searched,
    lastError: lastRuntimeStartError,
    runtimeUrl: RUNTIME_URL,
    logFile: getRuntimeLogFile(),
  };
}

const STARTUP_ERROR_MESSAGES = {
  PYTHON_RUNTIME_MISSING: 'Python runtime unavailable. Reinstall VANOVA or run Repair Installation.',
  PYTHON_RUNTIME_INVALID: 'Bundled Python runtime is invalid. Try Repair Installation.',
  DEPENDENCIES_MISSING: 'Required Python packages are missing.',
  DEPENDENCY_INSTALL_FAILED: 'Could not install Python dependencies.',
  CLOUD_START_FAILED: 'VANOVA Cloud could not start.',
  CLOUD_HEALTH_TIMEOUT: 'VANOVA Cloud did not become ready in time.',
  CLOUD_PORT_OCCUPIED: 'Port 8000 is in use by another application.',
  RUNTIME_START_FAILED: 'VANOVA Runtime could not start on port 8765.',
  FOREIGN_RUNTIME: 'Ya hay otra instalación de VANOVA ejecutándose con un perfil de datos diferente. Cierra la otra instancia antes de abrir esta (una instalación activa por máquina).',
  STATIC_ASSETS_MISSING: 'Dashboard files are missing from the installation.',
  INSTALLATION_INCOMPLETE: 'Installation is incomplete.',
};

function getLocalAppDataBase() {
  return process.env.LOCALAPPDATA || process.env.APPDATA || app.getPath('userData');
}

function getLogDir() {
  return path.join(getLocalAppDataBase(), 'VANOVA', 'logs');
}

function getInstallSecretsPath() {
  return path.join(getLocalAppDataBase(), 'VANOVA', 'config', 'install_secrets.json');
}

function readRuntimeToken() {
  try {
    const secretsPath = getInstallSecretsPath();
    if (!fs.existsSync(secretsPath)) return '';
    const data = JSON.parse(fs.readFileSync(secretsPath, 'utf8'));
    return String(data.runtimeToken || '');
  } catch (_) {
    return '';
  }
}

function getUpdatesDir() {
  return path.join(getLocalAppDataBase(), 'VANOVA', 'updates');
}

/** One-time migration: %LOCALAPPDATA%\MAIOS -> %LOCALAPPDATA%\VANOVA. Copies
 *  ALL user data (config/maios.json with products/prices, tasks.db, approvals.db,
 *  logs, backups) so the rebrand never loses a single record. Idempotent: only
 *  runs when VANOVA has no config yet but the legacy MAIOS dir has data. */
function migrateLegacyData() {
  try {
    const base = getLocalAppDataBase();
    const legacy = path.join(base, 'MAIOS');
    const target = path.join(base, 'VANOVA');
    if (!fs.existsSync(path.join(legacy, 'config', 'maios.json'))) return false;
    if (fs.existsSync(path.join(target, 'config', 'maios.json'))) return false;
    fs.mkdirSync(target, { recursive: true });
    fs.cpSync(legacy, target, {
      recursive: true,
      force: false,
      errorOnExist: false,
      filter: (src) => {
        const name = path.basename(src);
        if (name === 'venv' || name === 'updates' || name === 'temp' || name === '.tmp') return false;
        return true;
      },
    });
    logElectronEvent('LEGACY_DATA_MIGRATED', { from: legacy, to: target });
    return true;
  } catch (err) {
    logElectronEvent('LEGACY_DATA_MIGRATE_FAILED', { error: err.message });
    return false;
  }
}

function resolveUpdaterScript() {
  const root = getAppRoot();
  const candidates = [
    path.join(root, 'desktop', 'updater', 'vanova-updater.ps1'),
  ];
  if (process.resourcesPath) {
    candidates.push(
      path.join(process.resourcesPath, 'vanova', 'desktop', 'updater', 'vanova-updater.ps1'),
    );
  }
  if (isDev) {
    candidates.push(path.join(__dirname, 'updater', 'vanova-updater.ps1'));
  }
  const seen = new Set();
  for (const candidate of candidates) {
    const key = path.normalize(candidate).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    if (fs.existsSync(candidate)) return candidate;
  }
  logElectronEvent('Updater script not found in candidate paths', {
    candidates,
    appRoot: root,
    resourcesPath: process.resourcesPath,
  });
  return candidates[0];
}

function isProcessAlive(pid) {
  if (!pid || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === 'EPERM';
  }
}

function getWindowsPowerShellExe() {
  const windir = process.env.WINDIR || 'C:\\Windows';
  return path.join(windir, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
}

function spawnUpdaterProcess(script, jobFile) {
  const psExe = getWindowsPowerShellExe();
  const psArgs = [
    '-NoProfile',
    '-NonInteractive',
    '-STA',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    script,
    '-JobFile',
    jobFile,
  ];
  const spawnOpts = {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    cwd: path.dirname(script),
  };

  if (process.platform === 'win32') {
    // Spawn PowerShell DIRECTLY (windowsHide=true -> CREATE_NO_WINDOW). Never
    // via `cmd /c start /MIN` — that flashes a console window for the client.
    try {
      const spawnLog = path.join(getLogDir(), 'updater-spawn.log');
      fs.mkdirSync(path.dirname(spawnLog), { recursive: true });
      fs.appendFileSync(spawnLog, `${new Date().toISOString()} spawn powershell ${psArgs.join(' ')}${require('os').EOL}`);
    } catch (_) {}
    return spawn(psExe, psArgs, spawnOpts);
  }

  return spawn(psExe, psArgs, spawnOpts);
}

function getUpdaterLogSize() {
  try {
    const logFile = path.join(getLogDir(), 'updater.log');
    return fs.existsSync(logFile) ? fs.statSync(logFile).size : 0;
  } catch (_) {
    return 0;
  }
}

function readUpdaterLogTail(maxBytes = 16384) {
  try {
    const logFile = path.join(getLogDir(), 'updater.log');
    if (!fs.existsSync(logFile)) return '';
    const stat = fs.statSync(logFile);
    const start = Math.max(0, stat.size - maxBytes);
    const fd = fs.openSync(logFile, 'r');
    const buf = Buffer.alloc(stat.size - start);
    fs.readSync(fd, buf, 0, buf.length, start);
    fs.closeSync(fd);
    return buf.toString('utf8');
  } catch (_) {
    return '';
  }
}

function sleepMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForUpdaterLogStart(sizeBefore, timeoutMs = 4000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const logFile = path.join(getLogDir(), 'updater.log');
    if (!fs.existsSync(logFile)) {
      await sleepMs(250);
      continue;
    }
    const sizeAfter = fs.statSync(logFile).size;
    const tail = readUpdaterLogTail();
    if (sizeAfter > sizeBefore && (tail.includes('VANOVA Updater started') || tail.includes('VANOVA Updater launching'))) {
      return true;
    }
    await sleepMs(250);
  }
  return false;
}

async function spawnExternalUpdater() {
  const jobFile = path.join(getUpdatesDir(), 'pending-install.json');
  const script = resolveUpdaterScript();
  if (!fs.existsSync(jobFile)) {
    logElectronEvent('Updater spawn skipped - no pending job', { jobFile });
    return false;
  }
  if (!fs.existsSync(script)) {
    logElectronEvent('Updater spawn skipped - script missing', {
      script,
      appRoot: getAppRoot(),
      resourcesPath: process.resourcesPath,
    });
    return false;
  }
  const logSizeBefore = getUpdaterLogSize();
  let child;
  try {
    child = spawnUpdaterProcess(script, jobFile);
  } catch (err) {
    logElectronEvent('External updater spawn failed', { error: err.message, jobFile, script });
    return false;
  }

  let spawnError = null;
  let earlyExit = null;
  child.on('error', (err) => {
    spawnError = err;
    logElectronEvent('External updater spawn error event', { error: err.message, jobFile, script });
  });
  child.on('exit', (code, signal) => {
    earlyExit = { code, signal };
    logElectronEvent('External updater launcher exited', {
      code,
      signal,
      launcherPid: child.pid,
      jobFile,
      script,
    });
  });

  child.unref();
  logElectronEvent('External updater spawn requested', {
    jobFile,
    script,
    launcherPid: child.pid,
    via: process.platform === 'win32' ? 'cmd-start' : 'direct',
  });

  await sleepMs(400);
  if (spawnError) return false;

  const started = await waitForUpdaterLogStart(logSizeBefore, 15000);
  if (!started) {
    const spawnLog = path.join(getLogDir(), 'updater-spawn.log');
    let spawnLogTail = '';
    try {
      if (fs.existsSync(spawnLog)) {
        spawnLogTail = fs.readFileSync(spawnLog, 'utf8').slice(-4096);
      }
    } catch (_) {}
    logElectronEvent('External updater did not write updater.log (parse error, missing script, or job killed)', {
      jobFile,
      script,
      launcherPid: child.pid,
      launcherAlive: isProcessAlive(child.pid),
      earlyExit,
      spawnLogTail,
      logTail: readUpdaterLogTail(4096),
    });
    return false;
  }
  return true;
}

function logElectronEvent(message, details = {}) {
  try {
    const logFile = path.join(getLogDir(), 'electron-load.log');
    fs.mkdirSync(path.dirname(logFile), { recursive: true });
    fs.appendFileSync(logFile, `${new Date().toISOString()} ${message} ${JSON.stringify(details)}\n`);
  } catch (_) {}
  console.error(message, details);
}

function hardenedWebPreferences() {
  return {
    preload: path.join(__dirname, 'preload.js'),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
  };
}

function shellWebPreferences() {
  return hardenedWebPreferences();
}

function dashboardWebPreferences() {
  return hardenedWebPreferences();
}

function configureSecureSession() {
  const csp = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob:",
    "connect-src 'self' http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:* https://fonts.googleapis.com https://fonts.gstatic.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
  ].join('; ');

  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const headers = { ...details.responseHeaders };
    headers['Content-Security-Policy'] = [csp];
    callback({ responseHeaders: headers });
  });
}

let runtimeProcess = null;
let runtimeSpawnedByUs = false;
let mainWindow = null;
let dashboardWindow = null;
let tray = null;
let isQuitting = false;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function createTray() {
  if (tray) return;
  const iconPath = path.join(__dirname, 'assets', 'icon.png');
  try {
    tray = new Tray(iconPath);
    tray.setToolTip('VANOVA — AI Operating System');
    const contextMenu = Menu.buildFromTemplate([
      { label: 'Abrir VANOVA', click: () => focusPrimaryWindow() },
      { type: 'separator' },
      { label: 'Salir', click: () => { isQuitting = true; app.quit(); } }
    ]);
    tray.setContextMenu(contextMenu);
    tray.on('double-click', () => focusPrimaryWindow());
    logElectronEvent('Tray icon created');
  } catch (err) {
    logElectronEvent('Tray icon creation failed', { error: err.message });
  }
}

function showWindowsNotification(title, body, onClick) {
  if (!Notification.isSupported()) return;
  const notification = new Notification({ title, body, silent: false });
  if (onClick) notification.on('click', onClick);
  notification.show();
}

function getRuntimeLogFile() {
  return path.join(getLogDir(), 'runtime-launcher.log');
}

function killPidsOnPort(port) {
  if (process.platform !== 'win32') return [];
  try {
    const out = execSync('netstat -ano', { encoding: 'utf8', windowsHide: true });
    const pids = new Set();
    const needle = `:${port}`;
    for (const line of out.split(/\r?\n/)) {
      if (!line.includes(needle) || !/LISTENING/i.test(line)) continue;
      const parts = line.trim().split(/\s+/);
      const pid = parseInt(parts[parts.length - 1], 10);
      if (pid > 0) pids.add(pid);
    }
    const killed = [];
    for (const pid of pids) {
      try {
        execSync(`taskkill /PID ${pid} /F /T`, { stdio: 'ignore', windowsHide: true });
        killed.push(pid);
      } catch (_) {}
    }
    return killed;
  } catch (err) {
    logElectronEvent('killPidsOnPort failed', { port, error: err.message });
    return [];
  }
}

function stopRuntimeProcess() {
  if (!runtimeProcess) return;
  try {
    if (process.platform === 'win32') {
      try {
        execSync(`taskkill /PID ${runtimeProcess.pid} /F /T`, { stdio: 'ignore', windowsHide: true });
      } catch (_) {
        runtimeProcess.kill('SIGKILL');
      }
    } else {
      runtimeProcess.kill('SIGKILL');
    }
  } catch (_) {}
  runtimeProcess = null;
  runtimeSpawnedByUs = false;
}

async function stopAllMaiosRuntime() {
  killPidsOnPort(RUNTIME_PORT);
  killPidsOnPort(8000);
  stopRuntimeProcess();
  await sleep(300);
}

function httpGetJson(url, maxMs = 2000) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, json: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, json: null });
        }
      });
    });
    req.on('error', () => resolve(null));
    req.setTimeout(maxMs, () => {
      req.destroy();
      resolve(null);
    });
  });
}

async function probeRuntimeHealth(maxMs = 2000) {
  const health = await httpGetJson(`${RUNTIME_URL}/api/health`, maxMs);
  if (!health || health.status !== 200) return false;
  if (!health.json || health.json.service !== 'vanova-desktop-runtime') return false;

  const setup = await httpGetJson(`${RUNTIME_URL}/api/setup/status`, maxMs);
  if (!setup || setup.status !== 200 || !setup.json || !('configPath' in setup.json)) {
    return false;
  }

  const files = await httpGetJson(`${RUNTIME_URL}/api/files`, maxMs);
  // P2-1: /api/files ahora exige token; un 401 prueba que el runtime está vivo
  // y protegido — sigue contando como sano para la sonda del launcher.
  return !!(files && (files.status === 200 || files.status === 401));
}

function startRuntime() {
  const root = getAppRoot();
  process.env.MAIOS_APP_ROOT = root;
  process.env.MAIOS_RESOURCES = root;
  process.env.MAIOS_EXE = process.execPath;
  process.env.MAIOS_APP_EXE = process.execPath;
  process.env.MAIOS_PACKAGED = isDev ? '0' : '1';

  const py = getPython();
  if (!py) {
    lastRuntimeStartError = 'PYTHON_RUNTIME_MISSING';
    lastPythonProbe = getPythonProbe();
    logElectronEvent('STARTING_RUNTIME', {
      status: 'failed',
      error_code: 'PYTHON_RUNTIME_MISSING',
      searched: lastPythonProbe.searched,
    });
    try {
      fs.appendFileSync(
        getRuntimeLogFile(),
        `\n[${new Date().toISOString()}] FATAL: Python runtime missing — bundled interpreter not found.\n` +
          `  El antivirus puede haber borrado python.exe (no lleva firma). Reinstala VANOVA y añade la carpeta a las exclusiones.\n` +
          `  Buscado en: ${lastPythonProbe.searched.join(' ; ')}\n`
      );
    } catch (_) {}
    return false;
  }
  lastRuntimeStartError = null;
  logElectronEvent('PYTHON_RESOLVED', { python: py });

  const launcher = path.join(root, 'desktop', 'runtime', 'launcher.py');
  const logFile = getRuntimeLogFile();
  fs.mkdirSync(path.dirname(logFile), { recursive: true });
  const logFd = fs.openSync(logFile, 'a');

  logElectronEvent('Starting runtime', { py, launcher, cwd: root });

  runtimeProcess = spawn(py, [launcher], {
    cwd: root,
    env: { ...process.env, PYTHONPATH: root },
    stdio: ['ignore', logFd, logFd],
    windowsHide: true,
  });
  runtimeSpawnedByUs = true;

  runtimeProcess.on('error', (err) => {
    logElectronEvent('Runtime spawn failed', { error: err.message, error_code: 'RUNTIME_START_FAILED' });
  });
  runtimeProcess.on('exit', (code, signal) => {
    logElectronEvent('Runtime process exited', { code, signal });
    runtimeProcess = null;
    runtimeSpawnedByUs = false;
    try { fs.closeSync(logFd); } catch (_) {}
  });
  return true;
}

function waitForRuntime(maxMs = 20000) {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = async () => {
      if (await probeRuntimeHealth(1500)) {
        resolve(true);
        return;
      }
      // The exit handler sets runtimeProcess = null: don't keep waiting for a dead process.
      if (!runtimeProcess) {
        resolve(false);
        return;
      }
      if (Date.now() - start > maxMs) resolve(false);
      else setTimeout(check, 500);
    };
    check();
  });
}

async function runtimeBelongsToThisInstall() {
  // P2-2: comprobar que el runtime ya activo usa el config de ESTA instalación.
  // Un runtime de otra instalación/perfil NO debe reutilizarse en silencio
  // (mezclaría los datos de dos empresas).
  try {
    const setup = await httpGetJson(`${RUNTIME_URL}/api/setup/status`, 2000);
    if (!setup || setup.status !== 200 || !setup.json || !setup.json.configPath) return false;
    const expected = path.join(getLocalAppDataBase(), 'VANOVA', 'config', 'maios.json');
    const norm = (p) => path.resolve(p).replace(/\\/g, '/').toLowerCase();
    return norm(setup.json.configPath) === norm(expected);
  } catch (_) {
    return false;
  }
}

async function ensureRuntimeStarted() {
  if (await probeRuntimeHealth(2000)) {
    if (await runtimeBelongsToThisInstall()) {
      // BUG-0001 (QA baseline): si el runtime responde pero NO fue lanzado por
      // este proceso Electron, es un huérfano de una sesión anterior (crash /
      // force-kill): su stack interno (cloud 8000, connector, Hermes 8642)
      // puede estar en un estado inconsistente. Reemplazarlo para levantar el
      // stack completo limpio en lugar de reutilizar un zombie silencioso.
      if (!runtimeProcess) {
        logElectronEvent('Runtime healthy but orphaned from a previous session — replacing', {});
        const killed = killPidsOnPort(RUNTIME_PORT);
        if (killed.length) {
          logElectronEvent('Cleared orphaned runtime before re-spawn', { pids: killed });
          await sleep(800);
        }
      } else {
        logElectronEvent('Runtime already healthy — skipping spawn (same install)');
        return true;
      }
    } else {
      lastRuntimeStartError = 'FOREIGN_RUNTIME';
      logElectronEvent('Runtime belongs to another installation — refusing to attach', {});
      return false;
    }
  }

  for (let attempt = 1; attempt <= RUNTIME_START_ATTEMPTS; attempt++) {
    logElectronEvent(`Runtime start attempt ${attempt}/${RUNTIME_START_ATTEMPTS}`);
    const killed = killPidsOnPort(RUNTIME_PORT);
    if (killed.length) {
      logElectronEvent('Cleared stale listeners on runtime port', { pids: killed });
      await sleep(800);
    }

    stopRuntimeProcess();
    if (!startRuntime()) {
      logElectronEvent('Runtime start aborted — Python missing', { attempt });
      continue;
    }

    if (await waitForRuntime(RUNTIME_WAIT_PER_ATTEMPT_MS)) {
      logElectronEvent('Runtime API ready', { attempt });
      return true;
    }

    // The process is still alive but hasn't answered yet. On a fresh install the
    // antivirus scans the new files and Python can take a couple of minutes to
    // cold-start. Killing it now would restart that scan from scratch — wait.
    if (runtimeProcess) {
      logElectronEvent('Runtime alive but slow — extending wait (cold start)', { attempt });
      if (await waitForRuntime(RUNTIME_SLOW_EXTRA_MS)) {
        logElectronEvent('Runtime API ready after extended wait', { attempt });
        return true;
      }
      if (runtimeProcess) {
        logElectronEvent('Runtime still not ready after extended wait', { attempt });
        continue;
      }
    }

    logElectronEvent('Runtime process exited — retrying', { attempt });
    await sleep(1500);
  }

  return false;
}

async function restartRuntime() {
  logElectronEvent('Manual runtime restart requested');
  const killed = killPidsOnPort(RUNTIME_PORT);
  stopRuntimeProcess();
  if (killed.length) await sleep(800);
  return ensureRuntimeStarted();
}

function waitForCloud(maxMs = 30000) {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = () => {
      http.get(`${DASHBOARD_URL}/api/health`, (res) => {
        if (res.statusCode === 200) resolve(true);
        else retry();
      }).on('error', retry);
    };
    const retry = () => {
      if (Date.now() - start > maxMs) resolve(false);
      else setTimeout(check, 1000);
    };
    check();
  });
}

async function isSetupComplete() {
  return new Promise((resolve) => {
    http.get('http://127.0.0.1:8765/api/setup/status', (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (typeof parsed.complete === 'boolean') resolve(parsed.complete);
          else resolve(readSetupCompleteFromConfig());
        } catch {
          resolve(readSetupCompleteFromConfig());
        }
      });
    }).on('error', () => resolve(readSetupCompleteFromConfig()));
  });
}

function readSetupCompleteFromConfig() {
  try {
    const base = process.env.LOCALAPPDATA || process.env.APPDATA || app.getPath('userData');
    const cfg = path.join(base, 'VANOVA', 'config', 'maios.json');
    if (!fs.existsSync(cfg)) return false;
    const data = JSON.parse(fs.readFileSync(cfg, 'utf8'));
    return !!data.setupComplete;
  } catch (_) {
    return false;
  }
}

function attachShellLoadHandlers(win, label) {
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (!isMainFrame) return;
    logElectronEvent(`${label} did-fail-load`, { errorCode, errorDescription, validatedURL });
  });
}

function showLoadingPage(win) {
  return win.loadFile(path.join(__dirname, 'ui', 'loading.html'));
}

function showErrorPage(win, message, code = -1, opts = {}) {
  const query = {
    message: message || 'The dashboard failed to load.',
    code: String(code),
    errorCode: opts.errorCode || '',
    cloudDown: opts.cloudDown ? '1' : '0',
    renderOnly: opts.renderOnly ? '1' : '0',
  };
  return win.loadFile(path.join(__dirname, 'ui', 'error.html'), { query });
}

function attachDashboardLoadHandlers(win) {
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (!isMainFrame) return;
    logElectronEvent('Dashboard did-fail-load', { errorCode, errorDescription, validatedURL });
    if (validatedURL.startsWith(DASHBOARD_URL)) {
      showErrorPage(win, errorDescription || 'Could not load the dashboard.', errorCode);
    }
  });

  win.webContents.on('did-finish-load', () => {
    const url = win.webContents.getURL();
    logElectronEvent('Dashboard did-finish-load', { url });
  });

  win.webContents.on('render-process-gone', (_event, details) => {
    logElectronEvent('Dashboard render-process-gone', details);
    showErrorPage(win, 'The dashboard window crashed.', details.reason || -3, { renderOnly: true });
  });
}

async function loadDashboardUrl(win) {
  const bust = `${getVersion()}-${Date.now()}`;
  const url = `${DASHBOARD_URL}/?v=${encodeURIComponent(bust)}`;
  try {
    await session.defaultSession.clearCache();
  } catch (err) {
    logElectronEvent('clearCache failed', { error: err.message });
  }
  await win.loadURL(url, {
    userAgent: `${win.webContents.getUserAgent()} VANOVA-Desktop/2.0`,
    extraHeaders: 'Cache-Control: no-cache, no-store, must-revalidate\r\nPragma: no-cache\r\n',
  });
}

async function loadDashboardContent(win) {
  await showLoadingPage(win);
  if (!win.isVisible()) win.show();

  const cloud = await ensureCloudReady();
  if (!cloud.ok) {
    await showErrorPage(win, cloud.error, -1, { errorCode: cloud.errorCode, cloudDown: true });
    return { ok: false, error: cloud.error, errorCode: cloud.errorCode };
  }

  try {
    await loadDashboardUrl(win);
    return { ok: true };
  } catch (err) {
    logElectronEvent('Dashboard loadURL threw', { error: err.message });
    await showErrorPage(win, err.message, -2);
    return { ok: false, error: err.message };
  }
}

function createSetupWindow() {
  if (mainWindow) {
    mainWindow.focus();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 960,
    height: 640,
    minWidth: 800,
    minHeight: 560,
    title: 'VANOVA Setup',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    backgroundColor: '#0a0a0c',
    show: false,
    webPreferences: shellWebPreferences(),
    autoHideMenuBar: true,
    frame: true,
  });

  attachShellLoadHandlers(mainWindow, 'Setup');
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadFile(path.join(__dirname, 'ui', 'index.html'));
  mainWindow.on('closed', () => { mainWindow = null; });
}

async function createDashboardWindow() {
  if (dashboardWindow) {
    dashboardWindow.focus();
    return loadDashboardContent(dashboardWindow);
  }

  dashboardWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'VANOVA',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    backgroundColor: '#0a0a0c',
    show: false,
    webPreferences: dashboardWebPreferences(),
    autoHideMenuBar: true,
  });

  attachDashboardLoadHandlers(dashboardWindow);
  dashboardWindow.once('ready-to-show', () => {
    if (dashboardWindow && !dashboardWindow.isDestroyed()) dashboardWindow.show();
  });
  dashboardWindow.on('closed', () => { dashboardWindow = null; });

  if (mainWindow) mainWindow.close();
  return loadDashboardContent(dashboardWindow);
}

async function startCloudServices() {
  const token = readRuntimeToken();
  const headers = { 'Content-Type': 'application/json', 'Content-Length': 2 };
  if (token) headers.Authorization = `Bearer ${token}`;

  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: 8765,
        path: '/api/services/start',
        method: 'POST',
        headers,
      },
      (res) => {
        let data = '';
        res.on('data', (c) => (data += c));
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve({ ok: false, warnings: ['Invalid response from runtime API'] });
          }
        });
      },
    );
    req.on('error', () => resolve({ ok: false, warnings: ['Runtime API unavailable'] }));
    req.write('{}');
    req.end();
  });
}

async function ensureCloudReady(maxMs = 60000) {
  const deadline = Date.now() + maxMs;
  let lastError = STARTUP_ERROR_MESSAGES.CLOUD_HEALTH_TIMEOUT;
  let errorCode = 'CLOUD_HEALTH_TIMEOUT';

  while (Date.now() < deadline) {
    const svc = await startCloudServices();
    if (svc.warnings && svc.warnings.length) {
      lastError = svc.warnings.join(' ');
      logElectronEvent('Cloud start warnings', { warnings: svc.warnings });
      if (/port.*8000|occupied|blocked/i.test(lastError)) {
        errorCode = 'CLOUD_PORT_OCCUPIED';
        lastError = STARTUP_ERROR_MESSAGES.CLOUD_PORT_OCCUPIED;
      } else if (/exited|failed|ModuleNotFound|cloud\.log/i.test(lastError)) {
        errorCode = 'CLOUD_START_FAILED';
        lastError = STARTUP_ERROR_MESSAGES.CLOUD_START_FAILED + ' See cloud.log in VANOVA logs.';
      }
    }
    if (svc.cloud === false && svc.ok === false) {
      errorCode = 'CLOUD_START_FAILED';
    }
    const remaining = Math.max(5000, deadline - Date.now());
    const ready = await waitForCloud(Math.min(20000, remaining));
    if (ready) {
      logElectronEvent('CLOUD_READY', { port: 8000 });
      return { ok: true };
    }
    await sleep(2000);
  }

  return { ok: false, error: lastError, errorCode };
}

function focusPrimaryWindow() {
  const win = dashboardWindow || mainWindow;
  if (!win || win.isDestroyed()) return false;
  if (win.isMinimized()) win.restore();
  if (!win.isVisible()) win.show();
  win.focus();
  return true;
}

async function boot() {
  // Rebrand migration: copy any legacy MAIOS user data into VANOVA before
  // anything else reads the config (idempotent, preserves all records).
  migrateLegacyData();
  // Create tray icon for background proactivity
  createTray();
  // Existing installs already completed setup: open the dashboard. The dashboard
  // path needs the runtime + cloud up front and shows loading/error pages with
  // Retry while they come up.
  const configComplete = readSetupCompleteFromConfig();
  if (configComplete) {
    const runtimeReady = await ensureRuntimeStarted();
    if (!runtimeReady) {
      logElectronEvent('Runtime API unavailable after retries — opening dashboard with limited services');
    }
    await createDashboardWindow();
    return;
  }

  // Fresh install: give the runtime a short chance to answer (handles legacy
  // installs where the runtime migrates the old setup flag), then show the
  // wizard immediately. The Environment step polls /api/system/analyze itself
  // while the runtime finishes booting — no invisible multi-minute wait.
  const setup = await httpGetJson(`${RUNTIME_URL}/api/setup/status`, 8000);
  if (setup && setup.status === 200 && setup.json && typeof setup.json.complete === 'boolean' && setup.json.complete) {
    await createDashboardWindow();
    return;
  }

  createSetupWindow();
  ensureRuntimeStarted().then((ok) => {
    logElectronEvent(ok ? 'Runtime ready (behind setup window)' : 'Runtime unavailable — setup shows limited services');
  });
}

app.setAppUserModelId('com.moovingpaper.maios');

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  logElectronEvent('Second instance blocked — exiting');
  app.quit();
} else {
  app.on('second-instance', (event, argv, workingDirectory) => {
    // BUG-0002 (QA baseline): un QA/automatización lanza VANOVA con
    // --remote-debugging-port mientras la app ya corre en background (tray).
    // La 2ª instancia se bloquea por diseño (una instalación activa por
    // máquina), pero el flag se pierde y Playwright ve ECONNREFUSED.
    // Detectar el flag y relanzar ESTA instancia con él, de modo que el
    // puerto de depuración quede disponible sin duplicar el perfil de datos.
    const debugArg = (argv || []).find((a) => a.indexOf('--remote-debugging-port=') === 0);
    if (debugArg) {
      logElectronEvent('Debug flag requested — relaunching with remote debugging', { debugArg });
      const baseArgs = (process.argv.slice(1) || []).filter((a) => a.indexOf('--remote-debugging-port=') !== 0);
      app.relaunch({ args: baseArgs.concat([debugArg]) });
      app.quit();
      return;
    }
    logElectronEvent('Second instance requested — focusing existing window');
    focusPrimaryWindow();
  });
  app.whenReady().then(() => {
    configureSecureSession();
    return boot();
  });
}

app.on('window-all-closed', () => {
  // Minimize to tray instead of quitting (background proactivity)
  if (process.platform !== 'darwin' && !isQuitting) {
    if (!tray) createTray();
    return;
  }
  app.quit();
});

app.on('before-quit', () => {
  isQuitting = true;
  if (runtimeSpawnedByUs && runtimeProcess) {
    try { runtimeProcess.kill(); } catch (_) {}
  }
});

ipcMain.handle('open-dashboard', async () => createDashboardWindow());

ipcMain.handle('retry-dashboard', async () => {
  await ensureRuntimeStarted();
  if (!dashboardWindow || dashboardWindow.isDestroyed()) {
    return createDashboardWindow();
  }
  return loadDashboardContent(dashboardWindow);
});

ipcMain.handle('repair-installation', async () => {
  const token = readRuntimeToken();
  const headers = { 'Content-Type': 'application/json', 'Content-Length': 2 };
  if (token) headers.Authorization = `Bearer ${token}`;
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: RUNTIME_PORT,
        path: '/api/repair/run',
        method: 'POST',
        headers,
      },
      (res) => {
        let data = '';
        res.on('data', (c) => (data += c));
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve({ ok: false, error: 'Invalid repair response' });
          }
        });
      },
    );
    req.on('error', (err) => resolve({ ok: false, error: err.message }));
    req.write('{}');
    req.end();
  });
});

ipcMain.handle('open-external', async (_, url) => {
  await shell.openExternal(url || DASHBOARD_URL);
  return { ok: true };
});

ipcMain.handle('get-version', () => getVersion());

ipcMain.handle('get-runtime-auth-headers', () => {
  const token = readRuntimeToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
});

ipcMain.handle('get-diagnostics-fallback', () => ({
  version: getVersion(),
  logsPath: getLogDir(),
  runtimeLog: getRuntimeLogFile(),
  source: 'electron',
  updates: { state: 'unknown' },
}));

ipcMain.handle('get-runtime-health', () => getRuntimeHealthSnapshot());

ipcMain.handle('restart-runtime', async () => {
  const ok = await restartRuntime();
  return { ok, url: RUNTIME_URL };
});

ipcMain.handle('quit-for-update', async () => {
  const jobFile = path.join(getUpdatesDir(), 'pending-install.json');
  logElectronEvent('Quitting for update install', { jobFile });
  const spawned = await spawnExternalUpdater();
  if (!spawned) {
    logElectronEvent('Updater spawn failed — app will not quit', { jobFile });
    try {
      await ensureRuntimeStarted();
    } catch (err) {
      logElectronEvent('Runtime restart after failed updater spawn failed', { error: err.message });
    }
    return { ok: false, error: 'No se pudo iniciar el instalador externo. El runtime se ha restaurado — vuelve a pulsar Instalar.' };
  }
  await stopAllMaiosRuntime();
  setTimeout(() => app.quit(), 600);
  return { ok: true };
});

// Windows notification support
ipcMain.handle('show-notification', (_, { title, body }) => {
  showWindowsNotification(title, body, () => focusPrimaryWindow());
  return { ok: true };
});
