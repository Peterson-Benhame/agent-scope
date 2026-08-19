(() => {
  const vscode = acquireVsCodeApi();
  const cards = document.getElementById('cards');
  const filters = document.getElementById('filters');
  const status = document.getElementById('status');
  const refresh = document.getElementById('refresh');
  const selectDatabase = document.getElementById('select-database');

  const cardDefinitions = [
    ['sessions', 'Sessões'],
    ['totalTokens', 'Total de tokens'],
    ['tokensSaved', 'Tokens economizados'],
    ['cacheRatio', 'Taxa de cache'],
    ['observedCost', 'Custo observado'],
    ['estimatedSavings', 'Economia estimada'],
  ];

  refresh.addEventListener('click', () => vscode.postMessage({ type: 'refresh' }));
  selectDatabase.addEventListener('click', () => vscode.postMessage({ type: 'selectDatabase' }));

  function button(label, action, active) {
    const element = document.createElement('button');
    element.type = 'button';
    element.textContent = label;
    if (active) element.classList.add('active');
    element.addEventListener('click', action);
    return element;
  }

  function option(value, current) {
    const element = document.createElement('option');
    element.value = value;
    element.textContent = value || 'Todos';
    element.selected = value === (current || '');
    return element;
  }

  function dimensionSelect(label, key, values, current) {
    const wrapper = document.createElement('label');
    wrapper.className = 'filter-field';
    const caption = document.createElement('span');
    caption.textContent = label;
    const select = document.createElement('select');
    select.appendChild(option('', current));
    values.forEach((value) => select.appendChild(option(value, current)));
    select.addEventListener('change', () => {
      vscode.postMessage({ type: 'setFilter', patch: { [key]: select.value || null } });
    });
    wrapper.append(caption, select);
    return wrapper;
  }

  function renderFilters(vm) {
    filters.replaceChildren();
    const periods = [
      ['today', 'Hoje'],
      ['7d', '7 dias'],
      ['30d', '30 dias'],
      ['month', 'Mês'],
    ];
    const periodRow = document.createElement('div');
    periodRow.className = 'period-row';
    periods.forEach(([period, label]) => {
      periodRow.appendChild(button(
        label,
        () => vscode.postMessage({ type: 'setPeriod', period }),
        vm.filters.period === period,
      ));
    });
    periodRow.appendChild(button('Limpar', () => vscode.postMessage({ type: 'resetFilters' }), false));
    filters.appendChild(periodRow);

    const dateRow = document.createElement('div');
    dateRow.className = 'date-row';
    const from = document.createElement('input');
    from.type = 'date';
    from.value = vm.filters.from || '';
    from.setAttribute('aria-label', 'Data inicial');
    const to = document.createElement('input');
    to.type = 'date';
    to.value = vm.filters.to || '';
    to.setAttribute('aria-label', 'Data final');
    const apply = button('Aplicar período', () => {
      vscode.postMessage({
        type: 'setCustomRange',
        from: from.value || null,
        to: to.value || null,
      });
    }, false);
    dateRow.append(from, to, apply);
    filters.appendChild(dateRow);

    const dimensions = document.createElement('div');
    dimensions.className = 'dimension-grid';
    dimensions.append(
      dimensionSelect('Projeto', 'project', vm.dimensions.projects, vm.filters.project),
      dimensionSelect('Modelo', 'model', vm.dimensions.models, vm.filters.model),
      dimensionSelect('Fonte', 'source', vm.dimensions.sources, vm.filters.source),
      dimensionSelect('Usuário', 'user', vm.dimensions.users, vm.filters.user),
      dimensionSelect('Máquina', 'machine', vm.dimensions.machines, vm.filters.machine),
    );
    filters.appendChild(dimensions);
  }

  function renderCards(vm) {
    cards.replaceChildren();
    cardDefinitions.forEach(([key, label]) => {
      const article = document.createElement('article');
      article.className = 'card';
      const caption = document.createElement('span');
      caption.className = 'card-label';
      caption.textContent = label;
      const value = document.createElement('strong');
      value.className = 'card-value';
      value.textContent = vm.cards[key];
      article.append(caption, value);
      cards.appendChild(article);
    });
  }

  window.addEventListener('message', (event) => {
    const message = event.data;
    if (!message || typeof message.type !== 'string') return;
    if (message.type === 'loading') {
      status.textContent = 'Carregando dados do AgentScope...';
      return;
    }
    if (message.type === 'error') {
      cards.replaceChildren();
      status.textContent = message.message || 'Falha ao carregar AgentScope.';
      return;
    }
    if (message.type === 'snapshot') {
      const vm = message.payload;
      status.textContent = vm.database
        ? `Banco: ${vm.database}`
        : 'Banco padrão do AgentScope';
      renderFilters(vm);
      renderCards(vm);
    }
  });
})();
