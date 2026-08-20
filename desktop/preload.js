const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('maios', {
  openDashboard: () => ipcRenderer.invoke('open-dashboard'),
  retryDashboard: () => ipcRenderer.invoke('retry-dashboard'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  getVersion: () => ipcRenderer.invoke('get-version'),
  getRuntimeAuthHeaders: () => ipcRenderer.invoke('get-runtime-auth-headers'),
  getDiagnosticsFallback: () => ipcRenderer.invoke('get-diagnostics-fallback'),
  getRuntimeHealth: () => ipcRenderer.invoke('get-runtime-health'),
  restartRuntime: () => ipcRenderer.invoke('restart-runtime'),
  repairInstallation: () => ipcRenderer.invoke('repair-installation'),
});
