const { app, BrowserWindow, ipcMain, dialog, safeStorage } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

let windowRef;
let splashWindow;
let ideWindow;
let backend;
let ollama;
let isQuitting = false;
const hasSingleInstanceLock = app.requestSingleInstanceLock();
const terminals = new Map();
const PORT = Number(process.env.DIANA_PORT || 5000);
const IGNORE_DIRS = new Set(['node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build']);
const approvedRoots = new Set();
const MAX_IPC_TEXT = 5 * 1024 * 1024;
let externalTerminalLastLaunchAt = 0;

function resourceRoot() {
  return app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');
}

function firstExisting(paths) {
  return paths.find((candidate) => fs.existsSync(candidate));
}

function focusWindow(target) {
  if (!target || target.isDestroyed()) return;
  if (target.isMinimized()) target.restore();
  target.show();
  target.focus();
}

function absolutePath(value) {
  if (typeof value !== 'string' || !value.trim()) throw new Error('A local path is required');
  return path.resolve(value);
}

function isInside(candidate, parent) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

function nearestExistingPath(targetPath) {
  let current = absolutePath(targetPath);
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) return current;
    current = parent;
  }
  try { return fs.realpathSync.native(current); } catch (_) { return current; }
}

function canonicalPath(targetPath) {
  const resolved = absolutePath(targetPath);
  if (fs.existsSync(resolved)) {
    try { return fs.realpathSync.native(resolved); } catch (_) { return resolved; }
  }
  const ancestor = nearestExistingPath(resolved);
  const suffix = path.relative(ancestor, resolved);
  return suffix ? path.join(ancestor, suffix) : ancestor;
}

function rememberApprovedRoot(targetPath) {
  const resolved = canonicalPath(targetPath);
  approvedRoots.add(resolved);
  return resolved;
}

function approvedRootFor(targetPath) {
  const resolved = canonicalPath(targetPath);
  for (const root of approvedRoots) {
    if (isInside(resolved, root)) return root;
  }
  return null;
}

function pathPermissionError(targetPath, operation) {
  return new Error(`Permission denied: ${operation} is limited to a user-approved folder (${targetPath})`);
}

function assertApprovedPath(targetPath, operation, { mustExist = false, directory = false } = {}) {
  const resolved = canonicalPath(targetPath);
  if (!approvedRootFor(resolved)) throw pathPermissionError(resolved, operation);
  if (mustExist && !fs.existsSync(resolved)) throw new Error(`Path does not exist: ${resolved}`);
  if (directory && fs.existsSync(resolved) && !fs.statSync(resolved).isDirectory()) {
    throw new Error(`A folder is required: ${resolved}`);
  }
  return resolved;
}

function senderWindow(event) {
  return BrowserWindow.fromWebContents(event.sender) || windowRef;
}

async function askPermission(event, title, message, detail) {
  const result = await dialog.showMessageBox(senderWindow(event), {
    type: 'question',
    title,
    message,
    detail,
    buttons: ['Allow', 'Deny'],
    defaultId: 1,
    cancelId: 1,
    noLink: true,
  });
  return result.response === 0;
}

async function authorizePath(event, targetPath) {
  const requested = absolutePath(targetPath);
  const canonical = canonicalPath(requested);
  if (approvedRootFor(canonical)) return canonical;
  const exists = fs.existsSync(requested);
  const targetLabel = exists && fs.statSync(requested).isDirectory() ? 'folder' : 'file';
  const allowed = await askPermission(
    event,
    'Diana // Path Permission',
    `Allow Diana to access this ${targetLabel}?`,
    `${requested}\n\nDiana will only access this ${targetLabel} and its children during this session.`
  );
  if (!allowed) throw new Error(`Access denied by user: ${requested}`);
  rememberApprovedRoot(exists && targetLabel === 'file' ? path.dirname(canonical) : canonical);
  return canonical;
}

async function confirmCreation(event, targetPath, kind) {
  return askPermission(
    event,
    `Diana // Confirm ${kind}`,
    `Allow Diana to create this ${kind}?`,
    `${targetPath}\n\nThis operation will create a new item on your computer.`
  );
}

function updateSplash(payload = {}) {
  if (!splashWindow || splashWindow.isDestroyed() || !splashWindow.webContents) return;
  const safePayload = JSON.stringify(payload).replace(/<\/script/gi, '<\\/script');
  splashWindow.webContents.executeJavaScript(`window.dianaSplash?.update(${safePayload})`).catch(() => {});
}

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 560,
    height: 360,
    resizable: false,
    maximizable: false,
    minimizable: false,
    movable: true,
    show: false,
    frame: false,
    transparent: false,
    backgroundColor: '#07130f',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  splashWindow.on('closed', () => { splashWindow = null; });
  return splashWindow.loadFile(path.join(__dirname, 'splash.html')).then(() => {
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.show();
  });
}

function probeHttp(url, timeoutMs = 500) {
  return new Promise((resolve) => {
    const request = http.get(url, (response) => {
      response.resume();
      response.on('end', () => resolve(response.statusCode >= 200 && response.statusCode < 300));
    });
    request.setTimeout(timeoutMs, () => { request.destroy(); resolve(false); });
    request.on('error', () => resolve(false));
  });
}

function waitForBackend(baseUrl, attempts = 180, onAttempt = () => {}) {
  const healthUrl = `${baseUrl}/health`;
  return new Promise((resolve, reject) => {
    let settled = false;
    const fail = (error) => {
      if (settled) return;
      if (--attempts <= 0) {
        settled = true;
        reject(new Error(`Backend health check failed at ${healthUrl}: ${error.message}`));
      } else setTimeout(check, 500);
    };
    const check = () => {
      if (settled) return;
      onAttempt({ remaining: attempts });
      let requestHandled = false;
      const failRequest = (error) => {
        if (requestHandled || settled) return;
        requestHandled = true;
        fail(error);
      };
      const request = http.get(healthUrl, (response) => {
        let body = '';
        response.setEncoding('utf8');
        response.on('data', (chunk) => { body += chunk; });
        response.on('end', () => {
          if (requestHandled || settled) return;
          if (response.statusCode >= 200 && response.statusCode < 300) {
            try {
              const payload = body ? JSON.parse(body) : { status: 'ok' };
              if (payload.status === 'ok') { requestHandled = true; settled = true; resolve(payload); return; }
              failRequest(new Error(`health status: ${payload.status || 'unknown'}`));
            } catch (error) { failRequest(new Error(`invalid health response: ${error.message}`)); }
            return;
          }
          failRequest(new Error(`Health check returned HTTP ${response.statusCode}`));
        });
      });
      request.setTimeout(1000, () => failRequest(new Error('health timeout')));
      request.on('error', failRequest);
    };
    check();
  });
}

async function startOllama(root) {
  if (process.env.DIANA_START_OLLAMA !== '1') return null;
  if (await probeHttp('http://127.0.0.1:11434/api/tags')) {
    console.log('[Diana Ollama] existing service detected; not starting another process');
    return null;
  }
  const executable = process.platform === 'win32' ? 'ollama.exe' : 'ollama';
  const modelHome = process.env.OLLAMA_MODELS || (app.isPackaged
    ? path.join(app.getPath('userData'), 'models', 'ollama')
    : path.join(root, 'models', 'ollama'));
  fs.mkdirSync(modelHome, { recursive: true });
  const child = spawn(executable, ['serve'], {
    env: { ...process.env, OLLAMA_HOST: '127.0.0.1:11434', OLLAMA_MODELS: modelHome },
    windowsHide: true,
    stdio: 'ignore',
  });
  child.once('error', (error) => console.error('[Diana Ollama] failed:', error.message));
  return child;
}

function seedUserData(root, dataDir) {
  for (const filename of ['diana_texty_memory.json', 'diana_coding_memory.json']) {
    const target = path.join(dataDir, filename);
    const candidates = [path.join(root, 'memory', filename), path.join(root, 'python', filename)];
    const template = candidates.find((candidate) => fs.existsSync(candidate));
    if (!fs.existsSync(target) && template) fs.copyFileSync(template, target);
  }
}

async function startBackend(root) {
  if (await probeHttp(`http://127.0.0.1:${PORT}/health`)) {
    console.log(`[Diana backend] existing healthy service detected on port ${PORT}; not starting another process`);
    return null;
  }
  const packagedExecutable = firstExisting([
    path.join(root, 'backend', 'diana-backend', process.platform === 'win32' ? 'diana-backend.exe' : 'diana-backend'),
    path.join(root, 'backend', process.platform === 'win32' ? 'diana-backend.exe' : 'diana-backend'),
    path.join(root, 'diana-backend.exe'),
    path.join(root, 'diana-backend'),
  ]);
  const pythonScript = path.join(root, 'python', 'server.py');
  const localPython = firstExisting(process.platform === 'win32'
    ? [path.join(root, '.venv', 'Scripts', 'python.exe'), path.join(root, '.venv', 'python.exe')]
    : [path.join(root, '.venv', 'bin', 'python3'), path.join(root, '.venv', 'bin', 'python')]);
  const python = process.env.PYTHON || localPython || (process.platform === 'win32' ? 'python' : 'python3');
  const command = packagedExecutable || python;
  const args = packagedExecutable ? [] : [pythonScript];
  const dataDir = path.join(app.getPath('userData'), 'data');
  const env = {
    ...process.env,
    DIANA_HOST: '127.0.0.1',
    DIANA_PORT: String(PORT),
    DIANA_DATA_DIR: dataDir,
    DIANA_REFERENCE_VOICE: path.join(root, 'python', 'reference_voice.wav'),
    TTS_HOME: path.join(app.getPath('userData'), 'models', 'tts'),
    OLLAMA_URL: 'http://127.0.0.1:11434/api/chat',
  };
  fs.mkdirSync(dataDir, { recursive: true });
  seedUserData(root, dataDir);
  const child = spawn(command, args, { cwd: root, env, windowsHide: true, stdio: 'pipe' });
  let backendReady = false;
  child.stdout?.on('data', (chunk) => console.log(`[Diana backend] ${chunk.toString().trimEnd()}`));
  child.stderr?.on('data', (chunk) => console.error(`[Diana backend] ${chunk.toString().trimEnd()}`));
  child.once('spawn', () => console.log('[Diana backend] process spawned:', command));
  child.once('error', (error) => console.error('[Diana backend] spawn failed:', error.message));
  child.once('exit', (code, signal) => {
    if (!backendReady) console.error('[Diana backend] exited before health was ready:', { code, signal, command, pythonScript });
  });
  child.__markReady = () => { backendReady = true; };
  return child;
}

function buildTree(dirPath, depth = 0, maxDepth = 8) {
  if (depth > maxDepth) return [];
  let entries;
  try { entries = fs.readdirSync(dirPath, { withFileTypes: true }); } catch (_) { return []; }
  return entries
    .filter((entry) => !entry.name.startsWith('.') || entry.name === '.env')
    .filter((entry) => !(entry.isDirectory() && IGNORE_DIRS.has(entry.name)))
    .sort((a, b) => a.isDirectory() !== b.isDirectory() ? (a.isDirectory() ? -1 : 1) : a.name.localeCompare(b.name))
    .map((entry) => {
      const fullPath = path.join(dirPath, entry.name);
      const node = { name: entry.name, path: fullPath, type: entry.isDirectory() ? 'dir' : 'file' };
      if (entry.isDirectory()) node.children = buildTree(fullPath, depth + 1, maxDepth);
      return node;
    });
}

function registerIpc() {
  ipcMain.on('storage:encrypt', (event, value) => {
    try {
      if (!safeStorage.isEncryptionAvailable()) { event.returnValue = null; return; }
      event.returnValue = safeStorage.encryptString(String(value ?? '')).toString('base64');
    } catch (error) {
      console.error('[Diana storage] encryption failed:', error);
      event.returnValue = null;
    }
  });

  ipcMain.on('storage:decrypt', (event, value) => {
    try {
      if (!safeStorage.isEncryptionAvailable() || typeof value !== 'string' || !value.trim()) { event.returnValue = null; return; }
      event.returnValue = safeStorage.decryptString(Buffer.from(value, 'base64'));
    } catch (error) {
      console.error('[Diana storage] decryption failed:', error);
      event.returnValue = null;
    }
  });

  ipcMain.handle('dialog:openFolder', async (event) => {
    const result = await dialog.showOpenDialog(senderWindow(event), { properties: ['openDirectory'] });
    if (result.canceled || !result.filePaths.length) return null;
    return rememberApprovedRoot(result.filePaths[0]);
  });

  ipcMain.handle('dialog:openBookFiles', async (event) => {
    const result = await dialog.showOpenDialog(senderWindow(event), {
      properties: ['openFile', 'multiSelections'],
      filters: [
        { name: 'Diana Books', extensions: ['txt', 'md', 'markdown', 'html', 'htm', 'pdf', 'epub'] },
        { name: 'Readable Text', extensions: ['txt', 'md', 'markdown', 'html', 'htm'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    if (result.canceled || !result.filePaths.length) return [];
    return Promise.all(result.filePaths.map(async (targetPath) => {
      try { return { ok: true, path: await authorizePath(event, targetPath) }; }
      catch (error) { return { ok: false, path: targetPath, error: error.message }; }
    }));
  });

  ipcMain.handle('fs:authorizePath', async (event, targetPath) => {
    try { return { ok: true, path: await authorizePath(event, targetPath) }; }
    catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('fs:readTree', async (_event, rootPath) => {
    try {
      const safeRoot = assertApprovedPath(rootPath, 'read tree', { mustExist: true, directory: true });
      return { name: path.basename(safeRoot), path: safeRoot, type: 'dir', children: buildTree(safeRoot) };
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('fs:statPath', async (_event, targetPath) => {
    try {
      const safePath = assertApprovedPath(targetPath, 'inspect path', { mustExist: true });
      const stats = fs.statSync(safePath);
      return { ok: true, type: stats.isDirectory() ? 'dir' : 'file', path: safePath };
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('fs:readFile', async (_event, filePath) => {
    try {
      const safePath = assertApprovedPath(filePath, 'read file', { mustExist: true });
      return { ok: true, content: fs.readFileSync(safePath, 'utf8') };
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('fs:writeFile', async (event, filePath, content) => {
    try {
      const requested = absolutePath(filePath);
      const text = String(content ?? '');
      if (Buffer.byteLength(text, 'utf8') > MAX_IPC_TEXT) throw new Error('File content is too large for one IPC request');
      const exists = fs.existsSync(requested);
      let safePath;
      if (exists) {
        safePath = assertApprovedPath(requested, 'write file', { mustExist: true });
      } else {
        assertApprovedPath(path.dirname(requested), 'create file parent', { mustExist: true, directory: true });
        safePath = canonicalPath(requested);
        if (!(await confirmCreation(event, safePath, 'file'))) return { ok: false, error: 'Creation denied by user' };
      }
      fs.writeFileSync(safePath, text, { encoding: 'utf8', flag: 'w' });
      return { ok: true, path: safePath };
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('fs:createFile', async (event, filePath) => {
    try {
      const requested = absolutePath(filePath);
      if (fs.existsSync(requested)) throw new Error('The target already exists');
      assertApprovedPath(path.dirname(requested), 'create file parent', { mustExist: true, directory: true });
      const safePath = canonicalPath(requested);
      if (!(await confirmCreation(event, safePath, 'file'))) return { ok: false, error: 'Creation denied by user' };
      fs.writeFileSync(safePath, '', { flag: 'wx' });
      return { ok: true, path: safePath };
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('fs:createDirectory', async (event, directoryPath) => {
    try {
      const requested = absolutePath(directoryPath);
      if (fs.existsSync(requested)) throw new Error('The target already exists');
      assertApprovedPath(path.dirname(requested), 'create folder parent', { mustExist: true, directory: true });
      const safePath = canonicalPath(requested);
      if (!(await confirmCreation(event, safePath, 'folder'))) return { ok: false, error: 'Creation denied by user' };
      fs.mkdirSync(safePath, { recursive: false });
      return { ok: true, path: safePath };
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('book:extractText', async (event, filePath) => {
    try {
      const safePath = assertApprovedPath(filePath, 'extract book text', { mustExist: true });
      const extension = path.extname(safePath).toLowerCase();
      if (!['.pdf', '.epub'].includes(extension)) throw new Error('Book parser accepts PDF or EPUB files only');
      const root = resourceRoot();
      const helper = path.join(root, 'python', 'extract_book.py');
      if (!fs.existsSync(helper)) throw new Error('Book parser helper is not bundled');
      const python = process.env.PYTHON || firstExisting(process.platform === 'win32'
        ? [path.join(root, '.venv', 'Scripts', 'python.exe'), path.join(root, '.venv', 'python.exe')]
        : [path.join(root, '.venv', 'bin', 'python3'), path.join(root, '.venv', 'bin', 'python')]) || (process.platform === 'win32' ? 'python' : 'python3');
      return await new Promise((resolve) => {
        const child = spawn(python, [helper, safePath], {
          cwd: root,
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
          shell: false,
          windowsHide: true,
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => {
          if (stdout.length < MAX_IPC_TEXT * 2) stdout += chunk.toString('utf8');
        });
        child.stderr.on('data', (chunk) => {
          if (stderr.length < 8000) stderr += chunk.toString('utf8');
        });
        child.on('error', (error) => resolve({ ok: false, error: `Book parser failed to start: ${error.message}` }));
        child.on('close', (code) => {
          try {
            const payload = JSON.parse(stdout.trim());
            if (!payload.ok) return resolve({ ok: false, error: payload.error || stderr.trim() || `Book parser exited with ${code}` });
            const text = String(payload.text || '');
            if (!text) return resolve({ ok: false, error: 'Book parser returned no readable text' });
            return resolve({ ok: true, text: text.slice(0, MAX_IPC_TEXT), path: safePath, type: extension.slice(1) });
          } catch (_) {
            return resolve({ ok: false, error: stderr.trim() || `Book parser exited with ${code}` });
          }
        });
      });
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('terminal:start', async (event, termId, cwd) => {
    if (typeof termId !== 'string' || termId.length < 1 || termId.length > 128) return { ok: false, error: 'Invalid terminal id' };
    if (terminals.has(termId)) return { ok: true, alreadyRunning: true };
    try {
      const approvedDefault = approvedRoots.values().next().value || resourceRoot();
      const workingDirectory = cwd
        ? assertApprovedPath(cwd, 'start terminal', { mustExist: true, directory: true })
        : approvedDefault;
      const shell = process.platform === 'win32' ? 'powershell.exe' : (process.env.SHELL || 'bash');
      const args = process.platform === 'win32' ? ['-NoLogo', '-NoProfile'] : [];
      const child = spawn(shell, args, { cwd: workingDirectory, env: process.env, shell: false, stdio: ['pipe', 'pipe', 'pipe'] });
      const terminal = { child, webContents: event.sender };
      terminals.set(termId, terminal);
      child.stdout.on('data', (data) => terminal.webContents.send('terminal:data', termId, data.toString('utf8')));
      child.stderr.on('data', (data) => terminal.webContents.send('terminal:data', termId, data.toString('utf8')));
      child.on('error', (error) => {
        terminal.webContents.send('terminal:data', termId, `\\r\\n[Diana terminal error] ${error.message}\\r\\n`);
        terminals.delete(termId);
      });
      child.on('exit', (code) => { terminal.webContents.send('terminal:exit', termId, code); terminals.delete(termId); });
      return { ok: true };
    } catch (error) { return { ok: false, error: error.message }; }
  });

  ipcMain.handle('terminal:write', async (event, termId, data) => {
    const terminal = terminals.get(termId);
    if (!terminal || terminal.webContents !== event.sender || !terminal.child.stdin?.writable) return { ok: false, error: 'terminal not running or not owned by this window' };
    const text = String(data ?? '');
    if (Buffer.byteLength(text, 'utf8') > MAX_IPC_TEXT) return { ok: false, error: 'Terminal input is too large' };
    terminal.child.stdin.write(text);
    return { ok: true };
  });

  ipcMain.handle('terminal:kill', async (event, termId) => {
    const terminal = terminals.get(termId);
    if (terminal && terminal.webContents === event.sender) { terminal.child.kill(); terminals.delete(termId); }
    return { ok: true };
  });

  ipcMain.handle('window:openIDE', async () => { await openIDEWindow(); return { ok: true }; });
  ipcMain.handle('window:openTerminal', async () => { await openExternalPowerShell(); return { ok: true }; });
}

async function openIDEWindow() {
  if (ideWindow && !ideWindow.isDestroyed()) { focusWindow(ideWindow); return; }
  ideWindow = new BrowserWindow({
    width: 1500, height: 920, minWidth: 1000, minHeight: 650,
    backgroundColor: '#07130C', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  ideWindow.on('closed', () => { ideWindow = null; });
  ideWindow.on('unresponsive', () => console.error('[Diana IDE] renderer became unresponsive'));
  ideWindow.webContents.on('render-process-gone', (_event, details) => console.error('[Diana IDE] renderer exited:', details));
  await ideWindow.loadURL(`http://127.0.0.1:${PORT}/ide.html`);
}

function openExternalPowerShell() {
  const isWindows = process.platform === 'win32';
  const windowsPowerShell = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  const command = isWindows
    ? (fs.existsSync(windowsPowerShell) ? windowsPowerShell : (process.env.POWERSHELL_EXE || 'powershell.exe'))
    : (process.env.SHELL || 'bash');
  const now = Date.now();
  if (isWindows && now - externalTerminalLastLaunchAt < 900) {
    console.log('[Diana external terminal] duplicate click ignored');
    return Promise.resolve({ ok: true, duplicate: true, command });
  }
  externalTerminalLastLaunchAt = now;
  const args = isWindows
    ? ['-NoLogo', '-NoProfile', '-NoExit', '-Command', 'diana']
    : ['-lc', 'diana; exec bash'];
  console.log('[Diana external terminal] launching visible shell:', { command, args });
  return new Promise((resolve, reject) => {
    if (isWindows) {
      const launcher = path.join(resourceRoot(), 'terminal', 'open-diana-powershell.cmd');
      const comspec = process.env.ComSpec || path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'cmd.exe');
      if (!fs.existsSync(launcher)) {
        const error = new Error(`PowerShell launcher is missing: ${launcher}`);
        console.error('[Diana external terminal] launcher missing:', error);
        reject(error);
        return;
      }
      const commandLine = `call "${launcher}"`;
      console.log('[Diana external terminal] launching bundled Windows launcher:', { comspec, launcher });
      const starter = spawn(comspec, ['/d', '/s', '/c', commandLine], {
        detached: true,
        windowsHide: false,
        shell: false,
        stdio: 'ignore'
      });
      starter.once('spawn', () => {
        starter.unref();
        resolve({ ok: true, command, launcher, via: 'bundled-cmd-launcher' });
      });
      starter.once('error', (error) => {
        console.error('[Diana external terminal] bundled launcher failed:', { comspec, launcher, error });
        reject(new Error(`Could not open PowerShell: ${error.message}`));
      });
      return;
    }
    const child = spawn(command, args, { detached: true, windowsHide: false, shell: false, stdio: 'ignore' });
    child.once('spawn', () => { child.unref(); resolve({ ok: true, command }); });
    child.once('error', (error) => {
      console.error('[Diana external terminal] failed:', { command, error });
      reject(new Error(`Could not open terminal: ${error.message}`));
    });
  });
}

function closeChild(child) { if (child && !child.killed) { try { child.kill(); } catch (_) {} } }

async function createWindow() {
  const root = resourceRoot();
  const splashStartedAt = Date.now();
  await createSplashWindow();
  updateSplash({ status: 'Starting local engine...', detail: 'Preparing Diana services', progress: 12 });
  ollama = await startOllama(root);
  updateSplash({ status: 'Starting local engine...', detail: ollama ? 'Starting Ollama service' : 'Using existing local services', progress: 28 });
  backend = await startBackend(root);
  backend?.stdout?.on('data', (data) => console.log(`[Diana backend] ${data}`));
  backend?.stderr?.on('data', (data) => console.error(`[Diana backend] ${data}`));
  backend?.on('error', (error) => console.error('[Diana backend] failed:', error));
  updateSplash({ status: 'Loading Diana...', detail: 'Waiting for the local Python backend', progress: 52 });
  const backendHealth = await waitForBackend(`http://127.0.0.1:${PORT}`, 180, ({ remaining }) => {
    const elapsed = 180 - remaining;
    updateSplash({
      status: 'Loading Diana...',
      detail: 'Waiting for the local Python backend',
      progress: Math.min(88, 52 + Math.round(elapsed / 3)),
    });
  });
  backend?.__markReady?.();
  updateSplash({
    status: 'Local engine ready',
    detail: backendHealth.ollama_available ? 'Python backend and Ollama are available' : 'Python backend ready; Ollama is not detected',
    progress: 92,
  });
  const minimumSplashMs = 3200;
  const splashRemaining = minimumSplashMs - (Date.now() - splashStartedAt);
  if (splashRemaining > 0) await new Promise((resolve) => setTimeout(resolve, splashRemaining));
  updateSplash({ status: 'Almost ready...', detail: 'Opening Diana interface', progress: 96 });
  windowRef = new BrowserWindow({
    width: 1400, height: 900, minWidth: 960, minHeight: 620,
    show: false,
    backgroundColor: '#07130F', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  windowRef.on('closed', () => { windowRef = null; });
  windowRef.on('unresponsive', () => console.error('[Diana main] renderer became unresponsive'));
  windowRef.webContents.on('render-process-gone', (_event, details) => console.error('[Diana main] renderer exited:', details));
  windowRef.webContents.on('before-input-event', (_event, input) => {
    if (input.type === 'keyDown' && input.control && input.alt && input.key.toLowerCase() === 'i') openIDEWindow();
  });
  await windowRef.loadURL(`http://127.0.0.1:${PORT}/`);
  windowRef.show();
  windowRef.focus();
  // Reveal the desktop while the splash performs its matching exit animation.
  await windowRef.webContents.executeJavaScript('window.dianaDesktopReveal?.(); true').catch(() => {});
  updateSplash({ status: 'Diana ready', detail: 'Opening local desktop', progress: 100 });
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.executeJavaScript('window.dianaSplash?.finish?.(); true').catch(() => {});
    setTimeout(() => {
      if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
    }, 820);
  }
}

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (isQuitting) return;
    console.log('[Diana startup] second instance redirected to existing window');
    focusWindow(windowRef || splashWindow);
  });
  registerIpc();
  app.whenReady().then(createWindow).catch((error) => {
    console.error('[Diana startup] failed:', error);
    updateSplash({ status: 'Diana could not start', detail: 'Check the local backend and try again', error: error.message, progress: 100 });
    setTimeout(() => app.quit(), 7000);
  });
  app.on('before-quit', () => {
    isQuitting = true;
    for (const terminal of terminals.values()) closeChild(terminal.child);
    terminals.clear();
    closeChild(backend);
    closeChild(ollama);
  });
  app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow().catch((error) => console.error('[Diana activate] failed:', error)); else focusWindow(windowRef); });
}
