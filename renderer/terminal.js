(() => {
  const API = 'http://127.0.0.1:5000';
  const termId = `standalone-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const shellOutput = document.getElementById('terminal-output');
  const shellPath = document.getElementById('shell-path');
  const commandInput = document.getElementById('command-input');
  const commandForm = document.getElementById('command-form');
  const dianaOutput = document.getElementById('diana-output');
  const dianaInput = document.getElementById('diana-input');
  const dianaForm = document.getElementById('diana-form');
  const chatState = document.getElementById('chat-state');
  const connectionDot = document.getElementById('connection-dot');
  const connectionLabel = document.getElementById('connection-label');
  const bootReadout = document.getElementById('boot-readout');

  const appendShell = (value, className = '') => {
    const text = String(value ?? '');
    const span = document.createElement('span');
    if (className) span.className = className;
    span.textContent = text;
    shellOutput.appendChild(span);
    shellOutput.scrollTop = shellOutput.scrollHeight;
  };

  const addChat = (role, text) => {
    const article = document.createElement('article');
    article.className = `chat-line ${role}`;
    const label = document.createElement('span');
    label.className = 'chat-role';
    label.textContent = role === 'user' ? 'YOU' : 'DIANA';
    const body = document.createElement('p');
    body.textContent = String(text ?? '');
    article.append(label, body);
    dianaOutput.appendChild(article);
    dianaOutput.scrollTop = dianaOutput.scrollHeight;
  };

  const setState = (label, busy = false) => {
    chatState.textContent = label;
    chatState.classList.toggle('is-busy', busy);
    connectionLabel.textContent = busy ? 'LOCAL NODE // THINKING' : 'LOCAL NODE // READY';
    connectionDot.classList.toggle('is-busy', busy);
  };

  const startShell = async () => {
    if (!window.diana?.terminalStart) {
      appendShell('Electron terminal bridge unavailable.\n', 'error');
      connectionLabel.textContent = 'LOCAL NODE // BRIDGE ERROR';
      return;
    }
    const cwd = window.diana.platform === 'win32' ? undefined : undefined;
    const result = await window.diana.terminalStart(termId, cwd);
    if (!result?.ok) appendShell(`Terminal failed: ${result?.error || 'unknown error'}\n`, 'error');
    else {
      shellPath.textContent = window.diana.platform === 'win32' ? 'POWERSHELL // ACTIVE' : 'BASH // ACTIVE';
      bootReadout.textContent = 'SHELL // CONNECTED // READY';
      commandInput.focus();
    }
  };

  window.diana?.onTerminalData?.((id, data) => {
    if (id === termId) appendShell(data);
  });
  window.diana?.onTerminalExit?.((id, code) => {
    if (id === termId) {
      appendShell(`\n[terminal exited with code ${code}]\n`, 'error');
      shellPath.textContent = 'SHELL // CLOSED';
      bootReadout.textContent = 'SHELL // STOPPED';
    }
  });

  commandForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const command = commandInput.value;
    if (!command.trim()) return;
    appendShell(`\n> ${command}\n`);
    commandInput.value = '';
    await window.diana?.terminalWrite?.(termId, `${command}\n`);
  });

  dianaForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = dianaInput.value.trim();
    if (!message) return;
    dianaInput.value = '';
    addChat('user', message);
    setState('THINKING // LOCAL', true);
    try {
      const response = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, persona: 'texty', private: false, source: 'terminal' })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Diana request failed');
      addChat('assistant', payload.reply || 'No response received.');
      setState('TEXTY // READY');
    } catch (error) {
      addChat('assistant', `LOCAL ERROR // ${error.message}`);
      setState('OFFLINE // CHECK BACKEND');
    }
    dianaInput.focus();
  });

  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.activeElement === commandInput) commandInput.value = '';
  });

  startShell().catch((error) => appendShell(`Terminal startup error: ${error.message}\n`, 'error'));
})();
