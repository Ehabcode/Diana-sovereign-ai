const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('diana', {
  platform: process.platform,
  encryptPrivateStorage: (value) => ipcRenderer.sendSync('storage:encrypt', String(value ?? '')),
  decryptPrivateStorage: (value) => ipcRenderer.sendSync('storage:decrypt', String(value ?? '')),
  openIDE: () => ipcRenderer.invoke('window:openIDE'),
  openTerminal: () => ipcRenderer.invoke('window:openTerminal'),
  openFolder: () => ipcRenderer.invoke('dialog:openFolder'),
  openBookFiles: () => ipcRenderer.invoke('dialog:openBookFiles'),
  extractBookText: (filePath) => ipcRenderer.invoke('book:extractText', filePath),
  authorizePath: (targetPath) => ipcRenderer.invoke('fs:authorizePath', targetPath),
  readTree: (rootPath) => ipcRenderer.invoke('fs:readTree', rootPath),
  statPath: (targetPath) => ipcRenderer.invoke('fs:statPath', targetPath),
  getPathForFile: (file) => {
    try { return webUtils.getPathForFile(file); } catch (_) { return file?.path || ''; }
  },
  readFile: (filePath) => ipcRenderer.invoke('fs:readFile', filePath),
  writeFile: (filePath, content) => ipcRenderer.invoke('fs:writeFile', filePath, content),
  createFile: (filePath) => ipcRenderer.invoke('fs:createFile', filePath),
  createDirectory: (directoryPath) => ipcRenderer.invoke('fs:createDirectory', directoryPath),
  terminalStart: (termId, cwd) => ipcRenderer.invoke('terminal:start', termId, cwd),
  terminalWrite: (termId, data) => ipcRenderer.invoke('terminal:write', termId, data),
  terminalKill: (termId) => ipcRenderer.invoke('terminal:kill', termId),
  onTerminalData: (callback) => {
    const listener = (_event, termId, data) => callback(termId, data);
    ipcRenderer.on('terminal:data', listener);
    return () => ipcRenderer.removeListener('terminal:data', listener);
  },
  onTerminalExit: (callback) => {
    const listener = (_event, termId, code) => callback(termId, code);
    ipcRenderer.on('terminal:exit', listener);
    return () => ipcRenderer.removeListener('terminal:exit', listener);
  },
});
