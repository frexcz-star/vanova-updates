const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('maios', {
  openDashboard: () => ipcRenderer.invoke('open-dashboard'),
  retryDashboard: () => ipcRenderer.invoke('retry-dashboard'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  getVersion: () => ipcRenderer.invoke('get-version'),
  getDiagnosticsFallback: () => ipcRenderer.invoke('get-diagnostics-fallback'),
  restartRuntime: () => ipcRenderer.invoke('restart-runtime'),
  quitForUpdate: () => ipcRenderer.invoke('quit-for-update'),
});
