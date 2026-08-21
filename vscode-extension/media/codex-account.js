(() => {
  const account = document.getElementById('codex-account');
  if (!account) return;

  let syncButton;

  function detail(label, value, hint) {
    const item = document.createElement('div');
    item.className = 'codex-account-detail';

    const caption = document.createElement('span');
    caption.className = 'codex-account-label';
    caption.textContent = label;

    const content = document.createElement('strong');
    content.className = 'codex-account-value';
    content.textContent = value;

    item.append(caption, content);
    if (hint) {
      const note = document.createElement('span');
      note.className = 'codex-account-hint';
      note.textContent = hint;
      item.appendChild(note);
    }
    return item;
  }

  function setSyncState(syncing, errorMessage) {
    if (!syncButton) return;
    syncButton.disabled = syncing;
    syncButton.textContent = syncing ? 'Sincronizando...' : 'Sincronizar Codex';
    syncButton.title = errorMessage || '';
  }

  function render(vm) {
    account.replaceChildren();
    syncButton = undefined;
    const data = vm?.codexAccount;
    if (!data) return;

    const card = document.createElement('article');
    card.className = 'codex-account-card';

    const header = document.createElement('div');
    header.className = 'codex-account-header';
    const heading = document.createElement('h2');
    heading.textContent = data.title;

    const actions = document.createElement('div');
    actions.className = 'codex-account-actions';
    const synced = document.createElement('span');
    synced.textContent = data.syncedAtLabel;
    syncButton = document.createElement('button');
    syncButton.type = 'button';
    syncButton.className = 'codex-account-sync';
    syncButton.textContent = 'Sincronizar Codex';
    syncButton.addEventListener('click', () => {
      setSyncState(true);
      window.dispatchEvent(new CustomEvent('agentscope:syncCodex'));
    });
    actions.append(synced, syncButton);
    header.append(heading, actions);

    const grid = document.createElement('div');
    grid.className = 'codex-account-grid';
    grid.append(
      detail('Uso principal', data.primaryUsageLabel, data.primaryResetLabel ? `Reinicia em ${data.primaryResetLabel}` : undefined),
      detail('Uso secundário', data.secondaryUsageLabel, data.secondaryResetLabel ? `Reinicia em ${data.secondaryResetLabel}` : undefined),
      detail('Créditos adicionais', data.creditBalanceLabel),
    );

    if (data.spendControlLabel) {
      grid.appendChild(detail('Controle de gastos', data.spendControlLabel));
    }

    card.append(header, grid);
    account.appendChild(card);
  }

  window.addEventListener('message', (event) => {
    const message = event.data;
    if (!message || typeof message.type !== 'string') return;
    if (message.type === 'snapshot') {
      render(message.payload);
      return;
    }
    if (message.type === 'codexSyncing') {
      setSyncState(true);
      return;
    }
    if (message.type === 'codexSyncError') {
      setSyncState(false, message.message || 'Falha ao sincronizar Codex.');
      return;
    }
    if (message.type === 'error') {
      account.replaceChildren();
      syncButton = undefined;
    }
  });
})();
