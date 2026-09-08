// ============================================================
// DIANA.CODER — Renderer logic
// ============================================================

let projectRoot = null;
let editor = null;
let monacoReady = false;

// tabs: filePath -> { model, dirty, name }
const openTabs = new Map();
let activeTabPath = null;
let fileRevealToken = 0;
const editorWrap = document.getElementById('editor-wrap');
const fileRevealStatus = document.getElementById('file-reveal-status');
const fileRevealLabel = document.getElementById('file-reveal-label');
const fileRevealName = document.getElementById('file-reveal-name');

// ===================== Monaco Setup =====================
require.config({ paths: { vs: '../vendor/monaco-vs' } });
require(['vs/editor/editor.main'], () => {
    monaco.editor.defineTheme('diana-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [],
        colors: {
            'editor.background': '#07130C',
            'editor.foreground': '#E9FFF0',
            'editorLineNumber.foreground': '#166534',
            'editorLineNumber.activeForeground': '#22c55e',
            'editorCursor.foreground': '#22c55e',
            'editor.selectionBackground': '#22c55e33',
            'editor.inactiveSelectionBackground': '#22c55e1c',
            'editor.selectionHighlightBackground': '#22c55e18',
            'editor.lineHighlightBackground': '#12351F55',
            'editorIndentGuide.background': '#12351F66',
            'editorIndentGuide.activeBackground': '#22c55e66',
            'editorBracketMatch.background': '#22c55e22',
            'editorBracketMatch.border': '#22c55e88',
            'editorWidget.background': '#0A1710',
            'editorWidget.border': '#03480F',
            'editorHoverWidget.background': '#0A1710',
            'editorHoverWidget.border': '#03480F',
            'editorSuggestWidget.background': '#0A1710',
            'editorSuggestWidget.border': '#03480F',
            'editorSuggestWidget.selectedBackground': '#03480F',
            'scrollbarSlider.background': '#03480F88',
            'scrollbarSlider.hoverBackground': '#22c55e88',
            'minimap.background': '#07130C',
            'minimap.selectionHighlight': '#22c55e55',
            'overviewRulerBorder': '#03480F'
        }
    });

    editor = monaco.editor.create(document.getElementById('monaco-container'), {
        value: '',
        language: 'plaintext',
        theme: 'diana-dark',
        automaticLayout: true,
        fontFamily: "'Courier New', monospace",
        fontSize: 13,
        minimap: { enabled: true }
    });

    editor.onDidChangeModelContent(() => {
        if (activeTabPath && openTabs.has(activeTabPath)) {
            const tab = openTabs.get(activeTabPath);
            tab.dirty = true;
            renderTabs();
        }
    });

    monacoReady = true;
});

function languageForFile(fileName) {
    const ext = fileName.split('.').pop().toLowerCase();
    const map = {
        py: 'python', js: 'javascript', ts: 'typescript', jsx: 'javascript',
        tsx: 'typescript', html: 'html', css: 'css', json: 'json',
        md: 'markdown', java: 'java', c: 'c', cpp: 'cpp', cs: 'csharp',
        sh: 'shell', yml: 'yaml', yaml: 'yaml', txt: 'plaintext'
    };
    return map[ext] || 'plaintext';
}

// ===================== File Explorer =====================
async function mountProject(folder) {
    if (!folder) return false;
    projectRoot = folder;
    document.getElementById('project-path').textContent = folder;
    return refreshTree();
}

document.getElementById('btn-open-folder').addEventListener('click', async () => {
    const folder = await window.diana.openFolder();
    if (!folder) return;
    await mountProject(folder);
});

async function refreshTree() {
    if (!projectRoot) return;
    const tree = await window.diana.readTree(projectRoot);
    if (!tree || tree.ok === false) {
        const reason = tree?.error || 'The selected folder is not available';
        document.getElementById('tree-root').innerHTML = `<div class="tree-error">ACCESS BLOCKED<br><small>${escapeHtml(reason)}</small></div>`;
        appendChatMessage('diana', `مش قادر أقرأ المجلد: ${reason}`);
        return false;
    }
    const container = document.getElementById('tree-root');
    container.innerHTML = '';
    container.appendChild(renderTreeNode(tree, true));
    return true;
}

function renderTreeNode(node, isRoot = false) {
    const wrap = document.createElement('div');
    wrap.className = 'tree-node';

    if (!isRoot) {
        const label = document.createElement('div');
        label.className = `tree-node-label${node.type === 'dir' ? ' is-folder' : ''}`;
        label.dataset.path = node.path;
        const icon = node.type === 'dir' ? '📁' : fileIcon(node.name);
        const chevron = node.type === 'dir' ? '<span class="tree-chevron" aria-hidden="true">›</span>' : '';
        label.innerHTML = `${chevron}<span class="tree-icon">${icon}</span><span>${escapeHtml(node.name)}</span>`;
        wrap.appendChild(label);

        if (node.type === 'file') {
            label.addEventListener('click', () => openFile(node.path, node.name));
        } else {
            let expanded = false;
            label.setAttribute('role', 'button');
            label.setAttribute('tabindex', '0');
            label.setAttribute('aria-expanded', 'false');
            const childrenWrap = document.createElement('div');
            childrenWrap.className = 'tree-children is-collapsed';
            const toggleFolder = () => {
                expanded = !expanded;
                childrenWrap.classList.toggle('is-open', expanded);
                childrenWrap.classList.toggle('is-collapsed', !expanded);
                label.classList.toggle('is-expanded', expanded);
                label.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            };
            label.addEventListener('click', toggleFolder);
            label.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    toggleFolder();
                }
            });
            (node.children || []).forEach((child) => {
                childrenWrap.appendChild(renderTreeNode(child));
            });
            wrap.appendChild(childrenWrap);
        }
    } else {
        (node.children || []).forEach((child) => {
            wrap.appendChild(renderTreeNode(child));
        });
    }

    return wrap;
}

function fileIcon(name) {
    const ext = name.split('.').pop().toLowerCase();
    const icons = {
        py: '🐍', js: '📜', ts: '📜', html: '🌐', css: '🎨',
        json: '🧾', md: '📝', png: '🖼️', jpg: '🖼️', jpeg: '🖼️'
    };
    return icons[ext] || '📄';
}

function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// ===================== Tabs / Editor =====================
function beginFileReveal(fileName) {
    const token = ++fileRevealToken;
    if (fileRevealStatus) {
        fileRevealStatus.classList.remove('is-ready', 'is-error');
        fileRevealStatus.classList.add('is-reading');
        fileRevealStatus.setAttribute('aria-hidden', 'false');
    }
    if (fileRevealLabel) fileRevealLabel.textContent = 'READING FILE';
    if (fileRevealName) fileRevealName.textContent = fileName || 'LOADING CONTENT';
    if (editorWrap) editorWrap.classList.add('is-revealing');
    return token;
}

function finishFileReveal(token, state = 'ready', message = '') {
    if (token !== fileRevealToken) return;
    if (fileRevealStatus) {
        fileRevealStatus.classList.remove('is-reading', 'is-error');
        fileRevealStatus.classList.add(state === 'error' ? 'is-error' : 'is-ready');
        fileRevealStatus.setAttribute('aria-hidden', state === 'error' ? 'false' : 'true');
    }
    if (fileRevealLabel) fileRevealLabel.textContent = state === 'error' ? 'FILE LINK FAILED' : 'FILE LINKED';
    if (message && fileRevealName) fileRevealName.textContent = message;
    window.setTimeout(() => {
        if (token !== fileRevealToken) return;
        if (fileRevealStatus) {
            fileRevealStatus.classList.remove('is-ready', 'is-error');
            fileRevealStatus.setAttribute('aria-hidden', 'true');
        }
        if (editorWrap) editorWrap.classList.remove('is-revealing');
    }, state === 'error' ? 1300 : 430);
}

function displayActiveFile(filePath, token) {
    if (token !== fileRevealToken || !editor) return;
    const tab = openTabs.get(filePath);
    if (!tab) return;
    document.getElementById('editor-empty').style.display = 'none';
    activeTabPath = filePath;
    editor.setModel(tab.model);
    renderTabs();
    highlightActiveTreeNode(filePath);
    finishFileReveal(token, 'ready', tab.name);
}

async function openFile(filePath, fileName) {
    const token = beginFileReveal(fileName);
    const ready = await waitForMonaco();
    if (!ready) {
        finishFileReveal(token, 'error', 'EDITOR NOT READY');
        appendChatMessage('diana', 'المحرر لسه بيجهز، جرّب تفتح الملف تاني بعد لحظة.');
        return;
    }

    if (!openTabs.has(filePath)) {
        const res = await window.diana.readFile(filePath);
        if (token !== fileRevealToken) return;
        if (!res.ok) {
            finishFileReveal(token, 'error', fileName || 'UNREADABLE FILE');
            appendChatMessage('diana', `مش قادر افتح الملف: ${res.error}`);
            return;
        }
        const model = monaco.editor.createModel(res.content, languageForFile(fileName));
        openTabs.set(filePath, { model, dirty: false, name: fileName });
    }

    displayActiveFile(filePath, token);
}

let pendingClosePath = null;
let pendingCloseFromAll = false;
let closeAllQueue = [];

function activateOpenTab(filePath) {
    const tab = openTabs.get(filePath);
    if (!tab) return;
    closeOpenFilesMenu();
    const token = beginFileReveal(tab.name);
    displayActiveFile(filePath, token);
}

function renderTabs() {
    const row = document.getElementById('tabs-row');
    row.innerHTML = '';
    openTabs.forEach((tab, filePath) => {
        const el = document.createElement('div');
        el.className = 'tab-item' + (filePath === activeTabPath ? ' active' : '');
        el.innerHTML = `<span>${escapeHtml(tab.name)}</span>${tab.dirty ? '<span class="tab-dirty">●</span>' : ''}<span class="tab-close" role="button" aria-label="Close ${escapeHtml(tab.name)}">✕</span>`;
        el.addEventListener('click', (e) => {
            if (e.target.classList.contains('tab-close')) {
                e.stopPropagation();
                requestCloseTab(filePath);
            } else {
                activateOpenTab(filePath);
            }
        });
        row.appendChild(el);
    });
    renderOpenFilesMenu();
}

function renderOpenFilesMenu() {
    const count = openTabs.size;
    const countEl = document.getElementById('open-files-count');
    const list = document.getElementById('open-files-list');
    const summary = document.getElementById('open-files-summary');
    const closeAll = document.getElementById('btn-close-all-files');
    if (!list) return;

    if (countEl) countEl.textContent = String(count);
    if (summary) summary.textContent = `${count} ${count === 1 ? 'FILE OPEN' : 'FILES OPEN'}`;
    if (closeAll) closeAll.disabled = count === 0;
    list.innerHTML = '';

    if (!count) {
        list.innerHTML = '<div class="open-files-empty"><span class="open-files-empty-orbit">⌁</span><strong>NO OPEN FILES</strong><span>Choose a file from Explorer or drop one into Diana.</span></div>';
        return;
    }

    openTabs.forEach((tab, filePath) => {
        const row = document.createElement('div');
        row.className = 'open-file-row' + (filePath === activeTabPath ? ' is-active' : '');
        const select = document.createElement('button');
        select.className = 'open-file-select';
        select.type = 'button';
        select.title = filePath;
        select.innerHTML = `<span class="open-file-icon">${fileIcon(tab.name)}</span><span class="open-file-copy"><strong>${escapeHtml(tab.name)}</strong><small>${escapeHtml(filePath)}</small></span>${tab.dirty ? '<span class="open-file-dirty">● UNSAVED</span>' : '<span class="open-file-clean">LINKED</span>'}`;
        select.addEventListener('click', () => activateOpenTab(filePath));

        const close = document.createElement('button');
        close.className = 'open-file-close';
        close.type = 'button';
        close.title = `Close ${tab.name}`;
        close.setAttribute('aria-label', `Close ${tab.name}`);
        close.textContent = '✕';
        close.addEventListener('click', (event) => {
            event.stopPropagation();
            requestCloseTab(filePath);
        });

        row.append(select, close);
        list.appendChild(row);
    });
}

function closeOpenFilesMenu() {
    const menu = document.getElementById('open-files-menu');
    const trigger = document.getElementById('btn-manage-files');
    if (!menu) return;
    menu.classList.remove('is-open');
    menu.setAttribute('aria-hidden', 'true');
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
}

function toggleOpenFilesMenu() {
    const menu = document.getElementById('open-files-menu');
    const trigger = document.getElementById('btn-manage-files');
    if (!menu) return;
    const open = menu.classList.toggle('is-open');
    menu.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (trigger) trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) renderOpenFilesMenu();
}

function showCloseFileConfirm(filePath, fromAll = false) {
    const tab = openTabs.get(filePath);
    const confirm = document.getElementById('close-file-confirm');
    if (!tab || !confirm) return false;
    pendingClosePath = filePath;
    pendingCloseFromAll = fromAll;
    document.getElementById('close-file-title').textContent = tab.name;
    document.getElementById('close-file-copy').textContent = fromAll ? 'This file has unsaved changes. Close All is waiting for your choice.' : 'This file has unsaved changes. Save it before closing?';
    confirm.classList.add('is-open');
    confirm.setAttribute('aria-hidden', 'false');
    return true;
}

function hideCloseFileConfirm() {
    const confirm = document.getElementById('close-file-confirm');
    if (!confirm) return;
    confirm.classList.remove('is-open');
    confirm.setAttribute('aria-hidden', 'true');
    pendingClosePath = null;
    pendingCloseFromAll = false;
}

async function saveFileAtPath(filePath) {
    const tab = openTabs.get(filePath);
    if (!tab) return true;
    const res = await window.diana.writeFile(filePath, tab.model.getValue());
    if (!res.ok) {
        appendChatMessage('diana', `مش قادر أحفظ الملف ${tab.name}: ${res.error || 'Unknown error'}`);
        return false;
    }
    tab.dirty = false;
    renderTabs();
    return true;
}

function requestCloseTab(filePath) {
    const tab = openTabs.get(filePath);
    if (!tab) return;
    if (tab.dirty) {
        showCloseFileConfirm(filePath, false);
        return;
    }
    closeTab(filePath);
}

function processCloseAllQueue() {
    if (!closeAllQueue.length) {
        closeAllQueue = [];
        renderOpenFilesMenu();
        return;
    }
    const filePath = closeAllQueue[0];
    if (!openTabs.has(filePath)) {
        closeAllQueue.shift();
        processCloseAllQueue();
        return;
    }
    const tab = openTabs.get(filePath);
    if (tab.dirty) {
        showCloseFileConfirm(filePath, true);
        return;
    }
    closeAllQueue.shift();
    closeTab(filePath);
    window.setTimeout(processCloseAllQueue, 70);
}

function requestCloseAllFiles() {
    if (!openTabs.size) {
        closeOpenFilesMenu();
        return;
    }
    closeAllQueue = Array.from(openTabs.keys());
    closeOpenFilesMenu();
    processCloseAllQueue();
}

async function resolvePendingClose(action) {
    const filePath = pendingClosePath;
    const fromAll = pendingCloseFromAll;
    const tab = filePath ? openTabs.get(filePath) : null;
    if (!filePath || !tab) {
        hideCloseFileConfirm();
        return;
    }
    if (action === 'save') {
        const saved = await saveFileAtPath(filePath);
        if (!saved) return;
    }
    hideCloseFileConfirm();
    closeTab(filePath);
    if (fromAll) {
        closeAllQueue.shift();
        window.setTimeout(processCloseAllQueue, 70);
    }
}

function cancelPendingClose() {
    const fromAll = pendingCloseFromAll;
    closeAllQueue = [];
    hideCloseFileConfirm();
    if (fromAll) renderOpenFilesMenu();
}

function closeTab(filePath) {
    const tab = openTabs.get(filePath);
    if (!tab) return;
    const wasActive = activeTabPath === filePath;
    if (tab.model && !tab.model.isDisposed()) tab.model.dispose();
    openTabs.delete(filePath);

    if (wasActive) {
        const nextPath = openTabs.keys().next().value;
        if (nextPath) {
            const nextTab = openTabs.get(nextPath);
            activeTabPath = nextPath;
            if (editor) editor.setModel(nextTab.model);
            document.getElementById('editor-empty').style.display = 'none';
            highlightActiveTreeNode(nextPath);
        } else {
            activeTabPath = null;
            document.getElementById('editor-empty').style.display = 'flex';
            highlightActiveTreeNode(null);
        }
    }
    renderTabs();
}

const manageFilesButton = document.getElementById('btn-manage-files');
manageFilesButton?.addEventListener('click', toggleOpenFilesMenu);
document.getElementById('btn-close-files-menu')?.addEventListener('click', closeOpenFilesMenu);
document.getElementById('btn-close-all-files')?.addEventListener('click', requestCloseAllFiles);
document.getElementById('btn-cancel-close-file')?.addEventListener('click', cancelPendingClose);
document.getElementById('btn-discard-close-file')?.addEventListener('click', () => resolvePendingClose('discard'));
document.getElementById('btn-save-close-file')?.addEventListener('click', () => resolvePendingClose('save'));
document.addEventListener('click', (event) => {
    const menu = document.getElementById('open-files-menu');
    if (menu?.classList.contains('is-open') && !menu.contains(event.target) && event.target !== manageFilesButton && !manageFilesButton?.contains(event.target)) closeOpenFilesMenu();
});
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const confirm = document.getElementById('close-file-confirm');
    if (confirm?.classList.contains('is-open')) cancelPendingClose();
    else closeOpenFilesMenu();
});

function highlightActiveTreeNode(filePath) {
    document.querySelectorAll('.tree-node-label').forEach((el) => {
        el.classList.toggle('active-file', el.dataset.path === filePath);
    });
}

async function saveActiveFile() {
    if (!activeTabPath) return;
    await saveFileAtPath(activeTabPath);
}

document.getElementById('btn-save').addEventListener('click', saveActiveFile);
window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveActiveFile();
    }
});

// ===================== Command Palette =====================
const commandPalette = document.getElementById('command-palette');
const commandSearch = document.getElementById('command-search');
const commandList = document.getElementById('command-list');
let commandIndex = 0;
const commandItems = [
    { id: 'open-folder', label: 'OPEN FOLDER', detail: 'Mount a local workspace', key: '⌘ O' },
    { id: 'refresh-tree', label: 'REFRESH PROJECT FILES', detail: 'Re-read the mounted workspace', key: '↻' },
    { id: 'save-file', label: 'SAVE ACTIVE FILE', detail: 'Write the current tab to disk', key: '⌘ S' },
    { id: 'run-code', label: 'RUN ACTIVE FILE', detail: 'Run the current file in Terminal', key: 'F6' },
    { id: 'toggle-terminal', label: 'TOGGLE TERMINAL', detail: 'Show or hide the local shell', key: '⌘ J' },
    { id: 'manage-files', label: 'MANAGE OPEN FILES', detail: 'Switch or close editor tabs', key: '⌘ P' },
    { id: 'close-all-files', label: 'CLOSE ALL FILES', detail: 'Close every open editor tab', key: '' }
];

function getVisibleCommands() {
    const query = (commandSearch?.value || '').trim().toLowerCase();
    return commandItems.filter((item) => `${item.label} ${item.detail}`.toLowerCase().includes(query));
}

function renderCommandList() {
    if (!commandList) return [];
    const visible = getVisibleCommands();
    commandIndex = Math.max(0, Math.min(commandIndex, Math.max(visible.length - 1, 0)));
    commandList.innerHTML = '';
    if (!visible.length) {
        commandList.innerHTML = '<div class="command-empty"><span>⌁</span><strong>NO ACTIONS FOUND</strong><small>Try another command.</small></div>';
        return visible;
    }
    visible.forEach((item, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `command-item${index === commandIndex ? ' is-active' : ''}`;
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', index === commandIndex ? 'true' : 'false');
        button.innerHTML = `<span class="command-item-icon">›</span><span class="command-item-copy"><strong>${item.label}</strong><small>${item.detail}</small></span><kbd>${item.key || ' '}</kbd>`;
        button.addEventListener('click', () => executeCommand(item.id));
        commandList.appendChild(button);
    });
    return visible;
}

function openCommandPalette() {
    if (!commandPalette) return;
    commandPalette.classList.add('is-open');
    commandPalette.setAttribute('aria-hidden', 'false');
    commandIndex = 0;
    if (commandSearch) {
        commandSearch.value = '';
        renderCommandList();
        window.requestAnimationFrame(() => commandSearch.focus());
    }
}

function closeCommandPalette() {
    if (!commandPalette) return;
    commandPalette.classList.remove('is-open');
    commandPalette.setAttribute('aria-hidden', 'true');
}

function executeCommand(commandId) {
    closeCommandPalette();
    const actions = {
        'open-folder': () => document.getElementById('btn-open-folder')?.click(),
        'refresh-tree': () => projectRoot ? refreshTree() : appendChatMessage('diana', 'افتح Project Folder الأول عشان أعمل refresh للملفات.'),
        'save-file': () => saveActiveFile(),
        'run-code': () => runActiveFile(),
        'toggle-terminal': () => document.getElementById('btn-toggle-terminal')?.click(),
        'manage-files': () => toggleOpenFilesMenu(),
        'close-all-files': () => requestCloseAllFiles()
    };
    actions[commandId]?.();
}

document.getElementById('btn-command-palette')?.addEventListener('click', openCommandPalette);
document.getElementById('btn-close-command-palette')?.addEventListener('click', closeCommandPalette);
document.getElementById('btn-refresh-tree')?.addEventListener('click', () => executeCommand('refresh-tree'));
commandPalette?.addEventListener('click', (event) => {
    if (event.target === commandPalette) closeCommandPalette();
});
commandSearch?.addEventListener('input', () => {
    commandIndex = 0;
    renderCommandList();
});
commandSearch?.addEventListener('keydown', (event) => {
    const visible = getVisibleCommands();
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (visible.length) {
            commandIndex = (commandIndex + (event.key === 'ArrowDown' ? 1 : -1) + visible.length) % visible.length;
            renderCommandList();
        }
    } else if (event.key === 'Enter') {
        event.preventDefault();
        if (visible[commandIndex]) executeCommand(visible[commandIndex].id);
    } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeCommandPalette();
    }
});
window.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        openCommandPalette();
    } else if (event.key === 'Escape' && commandPalette?.classList.contains('is-open')) {
        event.preventDefault();
        closeCommandPalette();
    }
});

// ===================== Terminal =====================
let term = null;
let fitAddon = null;
const TERM_ID = 'main';
let terminalStarted = false;

async function ensureTerminalOpen() {
    const panel = document.getElementById('terminal-panel');
    panel.classList.add('open');
    if (!terminalStarted) await startTerminal();
    if (fitAddon) window.setTimeout(() => fitAddon.fit(), 80);
    return Boolean(term && terminalStarted);
}

document.getElementById('btn-toggle-terminal').addEventListener('click', async () => {
    const panel = document.getElementById('terminal-panel');
    if (panel.classList.contains('open')) {
        panel.classList.remove('open');
        return;
    }
    await ensureTerminalOpen();
});

document.getElementById('btn-close-terminal').addEventListener('click', () => {
    document.getElementById('terminal-panel').classList.remove('open');
});

async function startTerminal() {
    terminalStarted = true;
    term = new Terminal({
        theme: {
            background: '#000000',
            foreground: '#22c55e',
            cursor: '#22c55e'
        },
        fontFamily: "'Courier New', monospace",
        fontSize: 13
    });
    fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById('xterm-container'));
    fitAddon.fit();

    await window.diana.terminalStart(TERM_ID, projectRoot || undefined);

    term.onData((data) => {
        window.diana.terminalWrite(TERM_ID, data);
    });

    window.diana.onTerminalData((termId, data) => {
        if (termId === TERM_ID) term.write(data);
    });
    window.diana.onTerminalExit((termId) => {
        if (termId === TERM_ID) term.write('\r\n\r\n[process exited]\r\n');
    });
}

function quoteShellPath(targetPath, platform = window.diana.platform) {
    if (!targetPath) return "''";
    if (platform === 'win32') return `'${targetPath.replace(/'/g, "''")}'`;
    return `'${targetPath.replace(/'/g, "'\\''")}'`;
}

function commandForFile(filePath, fileName, platform = window.diana.platform) {
    const quotedPath = quoteShellPath(filePath, platform);
    const ext = (fileName.split('.').pop() || '').toLowerCase();
    const python = platform === 'win32' ? 'python' : 'python3';
    const shell = platform === 'win32' ? 'powershell -NoProfile -ExecutionPolicy Bypass -File' : 'bash';
    if (ext === 'py') return `${python} ${quotedPath}`;
    if (ext === 'js' || ext === 'mjs' || ext === 'cjs') return `node ${quotedPath}`;
    if (ext === 'ts') return `npx --no-install tsx ${quotedPath}`;
    if (ext === 'sh' || ext === 'bash') return `${shell} ${quotedPath}`;
    if (ext === 'json') return platform === 'win32' ? `Get-Content -Raw ${quotedPath}` : `cat ${quotedPath}`;
    if (ext === 'html') return `${python} -m http.server 5500`;
    return platform === 'win32' ? `Write-Host "No runner configured for ${fileName}"` : `printf '%s\\n' 'No runner configured for ${fileName}'`;
}

async function runActiveFile() {
    if (!activeTabPath) {
        appendChatMessage('diana', 'افتح ملف قابل للتشغيل الأول، وبعدها دوس RUN CODE.');
        return;
    }
    const tab = openTabs.get(activeTabPath);
    if (!tab) return;
    if (tab.dirty) {
        const saved = await saveFileAtPath(activeTabPath);
        if (!saved) {
            appendChatMessage('diana', `مش قادر أحفظ ${tab.name} قبل التشغيل.`);
            return;
        }
    }
    const ready = await ensureTerminalOpen();
    if (!ready) {
        appendChatMessage('diana', 'الترمنال لسه مش جاهز للتشغيل.');
        return;
    }
    const platform = window.diana.platform || 'linux';
    const root = projectRoot || parentDirectory(activeTabPath);
    const cdCommand = root
        ? (platform === 'win32' ? `Set-Location -LiteralPath ${quoteShellPath(root, platform)}` : `cd -- ${quoteShellPath(root, platform)}`)
        : '';
    const command = commandForFile(activeTabPath, tab.name, platform);
    const fullCommand = cdCommand ? `${cdCommand}\n${command}` : command;
    term.write(`\r\n\x1b[1;32m[DIANA RUN] ${tab.name}\x1b[0m\r\n`);
    await window.diana.terminalWrite(TERM_ID, `${fullCommand}\n`);
}

document.getElementById('btn-run-code')?.addEventListener('click', runActiveFile);
window.addEventListener('keydown', (event) => {
    if (event.key === 'F6') {
        event.preventDefault();
        runActiveFile();
    }
});

// ===================== Diana Chat + Apply Edits =====================
function appendChatMessage(role, text) {
    const box = document.getElementById('chat-messages');
    const el = document.createElement('div');
    el.className = 'chat-msg ' + role;
    box.appendChild(el);
    renderMessageContent(el, text);
    box.scrollTop = box.scrollHeight;
}

// بيقسم رد ديانا لنص عادي + كتل كود (```lang ... ```) وبيحط زرار Apply لكل كتلة
function renderMessageContent(container, text) {
    const parts = text.split(/```([a-zA-Z0-9]*)\n([\s\S]*?)```/g);
    // parts pattern: [text, lang, code, text, lang, code, ...]
    for (let i = 0; i < parts.length; i += 3) {
        const plain = parts[i];
        if (plain && plain.trim()) {
            const p = document.createElement('div');
            p.textContent = plain.trim();
            container.appendChild(p);
        }
        const lang = parts[i + 1];
        const code = parts[i + 2];
        if (code !== undefined) {
            const block = document.createElement('div');
            block.className = 'code-block';
            const head = document.createElement('div');
            head.className = 'code-block-head';
            head.innerHTML = `<span>${lang || 'code'}</span>`;
            const applyBtn = document.createElement('button');
            applyBtn.className = 'apply-btn';
            applyBtn.textContent = activeTabPath ? 'APPLY TO FILE' : 'NO FILE OPEN';
            applyBtn.disabled = !activeTabPath;
            applyBtn.addEventListener('click', () => applyCodeToActiveFile(code, applyBtn));
            head.appendChild(applyBtn);

            const pre = document.createElement('pre');
            pre.textContent = code;

            block.appendChild(head);
            block.appendChild(pre);
            container.appendChild(block);
        }
    }
}

function applyCodeToActiveFile(code, btnEl) {
    if (!activeTabPath) return;
    const tab = openTabs.get(activeTabPath);
    tab.model.setValue(code);
    tab.dirty = true;
    renderTabs();
    btnEl.textContent = 'APPLIED ✓';
    btnEl.classList.add('applied');
    btnEl.disabled = true;
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    appendChatMessage('user', message);
    input.value = '';

    const persona = document.getElementById('persona-select').value;
    const backendUrl = `http://127.0.0.1:${window.location.port || 5000}/chat`;

    let fileContext = '';
    if (activeTabPath) {
        const tab = openTabs.get(activeTabPath);
        fileContext = `\n\n[Current open file: ${tab.name}]\n\`\`\`${languageForFile(tab.name)}\n${tab.model.getValue()}\n\`\`\``;
    }

    const thinkingEl = document.createElement('div');
    thinkingEl.className = 'chat-msg diana';
    thinkingEl.textContent = '...';
    document.getElementById('chat-messages').appendChild(thinkingEl);

    try {
        const res = await fetch(backendUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message + fileContext,
                persona,
                voice: false
            })
        });
        const data = await res.json();
        thinkingEl.remove();
        if (data.error) {
            appendChatMessage('diana', 'Error: ' + data.error);
        } else {
            appendChatMessage('diana', data.reply || '(no reply)');
        }
    } catch (err) {
        thinkingEl.remove();
        appendChatMessage('diana', `Connection error: ${err.message}\n(اتأكد إن Diana backend شغال على العنوان اللي في Backend URL فوق)`);
    }
}

document.getElementById('btn-send-chat').addEventListener('click', sendChatMessage);
document.getElementById('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
    }
});


// ===================== macOS-style micro interactions =====================
function releaseButtonPress(button) {
    if (button) button.classList.remove('is-pressed');
}

document.addEventListener('pointerdown', (event) => {
    const button = event.target.closest('button');
    if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true') return;
    button.classList.add('is-pressed');
});

document.addEventListener('pointerup', (event) => releaseButtonPress(event.target.closest('button')));
document.addEventListener('pointercancel', (event) => releaseButtonPress(event.target.closest('button')));
document.addEventListener('pointerover', (event) => {
    const button = event.target.closest('button');
    if (button && button !== event.relatedTarget?.closest?.('button')) button.classList.remove('is-pressed');
});

document.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true') return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;

    const rect = button.getBoundingClientRect();
    const ripple = document.createElement('span');
    ripple.className = 'button-ripple';
    ripple.style.left = `${event.clientX - rect.left}px`;
    ripple.style.top = `${event.clientY - rect.top}px`;
    button.appendChild(ripple);
    window.setTimeout(() => ripple.remove(), 620);
});


// ===================== Premium Drag & Drop =====================
const dropDeck = document.getElementById('drop-deck');
const dropTitle = document.getElementById('drop-title');
const dropSubtitle = document.getElementById('drop-subtitle');
const dropEyebrow = document.getElementById('drop-eyebrow');
const dropFileCount = document.getElementById('drop-file-count');
let dragDepth = 0;
let dropResetTimer = null;

function hasDraggedFiles(event) {
    return Array.from(event.dataTransfer?.types || []).includes('Files');
}

function setDropDeck(state, count = 0) {
    if (!dropDeck) return;
    window.clearTimeout(dropResetTimer);
    dropDeck.classList.toggle('is-active', state === 'active' || state === 'complete' || state === 'error');
    dropDeck.classList.toggle('is-complete', state === 'complete');
    dropDeck.classList.toggle('is-error', state === 'error');
    document.body.classList.toggle('is-dragging', state === 'active');
    dropDeck.setAttribute('aria-hidden', state === 'idle' ? 'true' : 'false');

    if (state === 'active') {
        dropEyebrow.textContent = 'DIANA // DROP DECK';
        dropTitle.textContent = count > 1 ? `DROP ${count} FILES TO OPEN` : 'DROP FILE TO OPEN';
        dropSubtitle.textContent = 'Release to mount the workspace and open your files.';
        dropFileCount.textContent = count > 1 ? `${count} ITEMS` : 'READY';
    } else if (state === 'complete') {
        dropEyebrow.textContent = 'DIANA // WORKSPACE READY';
        dropTitle.textContent = 'FILES MOUNTED';
        dropSubtitle.textContent = 'Your files are open in the editor.';
        dropFileCount.textContent = `${count} ${count === 1 ? 'ITEM' : 'ITEMS'}`;
        dropResetTimer = window.setTimeout(() => setDropDeck('idle'), 850);
    } else if (state === 'error') {
        dropEyebrow.textContent = 'DIANA // DROP DECK';
        dropTitle.textContent = 'DROP COULD NOT OPEN';
        dropSubtitle.textContent = 'Try a readable file or a project folder.';
        dropFileCount.textContent = 'RETRY';
        dropResetTimer = window.setTimeout(() => setDropDeck('idle'), 1300);
    } else {
        dropDeck.setAttribute('aria-hidden', 'true');
    }
}

function parentDirectory(targetPath) {
    const slash = Math.max(targetPath.lastIndexOf('/'), targetPath.lastIndexOf('\\'));
    return slash > 0 ? targetPath.slice(0, slash) : null;
}

async function waitForMonaco(timeoutMs = 7000) {
    const startedAt = Date.now();
    while (!monacoReady && Date.now() - startedAt < timeoutMs) {
        await new Promise((resolve) => window.setTimeout(resolve, 30));
    }
    return monacoReady;
}

async function handleDroppedFiles(fileList) {
    const paths = [];
    for (const file of Array.from(fileList || [])) {
        const targetPath = window.diana.getPathForFile(file);
        if (targetPath) paths.push(targetPath);
    }
    if (!paths.length) throw new Error('No local paths found');

    const authorized = [];
    for (const targetPath of paths) {
        const permission = await window.diana.authorizePath(targetPath);
        if (!permission?.ok) throw new Error(permission?.error || 'Path access was denied');
        authorized.push(permission.path || targetPath);
    }

    const stats = await Promise.all(authorized.map((targetPath) => window.diana.statPath(targetPath)));
    const folders = authorized.filter((targetPath, index) => stats[index]?.ok && stats[index].type === 'dir');
    const files = authorized.filter((targetPath, index) => stats[index]?.ok && stats[index].type === 'file');

    if (folders.length) await mountProject(folders[0]);
    else if (!projectRoot && files.length) await mountProject(parentDirectory(files[0]));

    if (files.length) {
        const ready = await waitForMonaco();
        if (!ready) throw new Error('Editor is still loading');
        for (const targetPath of files) {
            const fileName = targetPath.split(/[\\/]/).pop();
            await openFile(targetPath, fileName);
        }
    }
    return folders.length + files.length;
}

document.addEventListener('dragenter', (event) => {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    const count = event.dataTransfer?.items?.length || 1;
    setDropDeck('active', count);
});

document.addEventListener('dragover', (event) => {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
});

document.addEventListener('dragleave', (event) => {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) setDropDeck('idle');
});

document.addEventListener('drop', async (event) => {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    const files = event.dataTransfer?.files;
    const count = files?.length || 0;
    try {
        const openedCount = await handleDroppedFiles(files);
        setDropDeck('complete', openedCount || count);
    } catch (error) {
        console.error('Diana drop error:', error);
        setDropDeck('error');
        appendChatMessage('diana', `مش قادر أفتح العناصر المسحوبة: ${error.message}`);
    }
});

window.addEventListener('blur', () => {
    dragDepth = 0;
    if (dropDeck?.classList.contains('is-active')) setDropDeck('idle');
});

// Open the integrated Diana Terminal automatically when the IDE window starts.
// The user can still close it with the terminal close button.
window.addEventListener('load', () => {
    window.setTimeout(() => {
        ensureTerminalOpen().catch((error) => {
            appendChatMessage('diana', `الترمنال غير متاح: ${error.message}`);
        });
    }, 180);
});
