(() => {
  const vscode = acquireVsCodeApi();
  const cards = document.getElementById('cards');
  const filters = document.getElementById('filters');
  const status = document.getElementById('status');
  const trends = document.getElementById('trends');
  const breakdowns = document.getElementById('breakdowns');
  const notes = document.getElementById('notes');
  const refresh = document.getElementById('refresh');
  const selectDatabase = document.getElementById('select-database');
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const cardDefinitions = [
    ['sessions', 'Sessões'],
    ['totalTokens', 'Total de tokens'],
    ['tokensSaved', 'Tokens economizados'],
    ['cacheRatio', 'Taxa de cache'],
    ['observedCost', 'Custo observado'],
    ['estimatedCost', 'Custo estimado'],
    ['estimatedSavings', 'Economia estimada'],
  ];

  const integerFormatter = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
  const usdFormatter = new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

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
      const metric = vm.cards[key];
      const article = document.createElement('article');
      article.className = 'card';
      const caption = document.createElement('span');
      caption.className = 'card-label';
      caption.textContent = metric.label || label;
      const value = document.createElement('strong');
      value.className = 'card-value';
      value.textContent = metric.value;
      article.append(caption, value);
      if (metric.subtitle) {
        const subtitle = document.createElement('span');
        subtitle.className = 'card-subtitle';
        subtitle.textContent = metric.subtitle;
        article.appendChild(subtitle);
      }
      cards.appendChild(article);
    });
  }

  function chartCard(title) {
    const article = document.createElement('article');
    article.className = 'chart-card';
    const heading = document.createElement('h3');
    heading.textContent = title;
    article.appendChild(heading);
    return article;
  }

  function emptyChart(article, message = 'Sem dados para os filtros selecionados.') {
    const empty = document.createElement('p');
    empty.className = 'chart-empty';
    empty.textContent = message;
    article.appendChild(empty);
    return article;
  }

  function renderLineChart(title, points, seriesDefs) {
    const article = chartCard(title);
    if (!points.length) return emptyChart(article);

    const values = [];
    seriesDefs.forEach((series) => {
      points.forEach((point) => {
        const value = point[series.key];
        if (typeof value === 'number' && Number.isFinite(value)) values.push(value);
      });
    });
    if (!values.length) return emptyChart(article, 'Métrica não disponível neste período.');

    const width = 640;
    const height = 220;
    const paddingX = 34;
    const paddingY = 24;
    const maxValue = Math.max(...values, 0);
    const minValue = Math.min(...values, 0);
    const range = maxValue - minValue || 1;
    const x = (index) => points.length === 1
      ? width / 2
      : paddingX + (index / (points.length - 1)) * (width - paddingX * 2);
    const y = (value) => height - paddingY - ((value - minValue) / range) * (height - paddingY * 2);

    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', title);
    svg.classList.add('chart-svg');

    const baseline = document.createElementNS(SVG_NS, 'line');
    baseline.setAttribute('x1', String(paddingX));
    baseline.setAttribute('x2', String(width - paddingX));
    baseline.setAttribute('y1', String(y(0)));
    baseline.setAttribute('y2', String(y(0)));
    baseline.classList.add('chart-axis');
    svg.appendChild(baseline);

    seriesDefs.forEach((series, seriesIndex) => {
      const segments = [];
      let current = [];
      points.forEach((point, index) => {
        const value = point[series.key];
        if (typeof value === 'number' && Number.isFinite(value)) {
          current.push(`${x(index)},${y(value)}`);
        } else if (current.length) {
          segments.push(current);
          current = [];
        }
      });
      if (current.length) segments.push(current);

      segments.forEach((segment) => {
        if (segment.length === 1) {
          const [cx, cy] = segment[0].split(',');
          const circle = document.createElementNS(SVG_NS, 'circle');
          circle.setAttribute('cx', cx);
          circle.setAttribute('cy', cy);
          circle.setAttribute('r', '4');
          circle.classList.add('chart-point', `series-${seriesIndex + 1}`);
          svg.appendChild(circle);
        } else {
          const polyline = document.createElementNS(SVG_NS, 'polyline');
          polyline.setAttribute('points', segment.join(' '));
          polyline.classList.add('chart-line', `series-${seriesIndex + 1}`);
          svg.appendChild(polyline);
        }
      });
    });

    article.appendChild(svg);
    const legend = document.createElement('div');
    legend.className = 'chart-legend';
    seriesDefs.forEach((series, index) => {
      const item = document.createElement('span');
      item.className = `legend-item series-${index + 1}`;
      item.textContent = series.label;
      legend.appendChild(item);
    });
    article.appendChild(legend);
    return article;
  }

  function renderBreakdownChart(title, rows) {
    const article = chartCard(title);
    const top = rows.slice(0, 8);
    if (!top.length) return emptyChart(article);
    const max = Math.max(...top.map((row) => row.totalTokens), 0);
    if (max === 0) return emptyChart(article, 'Nenhum token registrado nesta seleção.');

    const list = document.createElement('div');
    list.className = 'breakdown-list';
    top.forEach((row) => {
      const item = document.createElement('div');
      item.className = 'breakdown-row';
      const header = document.createElement('div');
      header.className = 'breakdown-header';
      const label = document.createElement('span');
      label.textContent = row.label;
      const value = document.createElement('strong');
      value.textContent = `${integerFormatter.format(row.totalTokens)} tokens`;
      header.append(label, value);
      const track = document.createElement('div');
      track.className = 'bar-track';
      const bar = document.createElement('span');
      bar.className = 'bar-fill';
      bar.style.width = `${Math.max(2, (row.totalTokens / max) * 100)}%`;
      track.appendChild(bar);
      item.append(header, track);
      list.appendChild(item);
    });
    article.appendChild(list);
    return article;
  }

  function renderCharts(vm) {
    trends.replaceChildren();
    breakdowns.replaceChildren();
    const daily = vm.series.daily;
    trends.append(
      renderLineChart('Sessões por dia', daily, [{ key: 'sessions', label: 'Sessões' }]),
      renderLineChart('Tokens por dia', daily, [{ key: 'totalTokens', label: 'Tokens' }]),
      renderLineChart('Custo observado × economia estimada', daily, [
        { key: 'observedCostUsd', label: 'Custo observado' },
        { key: 'estimatedSavingsUsd', label: 'Economia estimada' },
      ]),
      renderLineChart('Taxa de cache', daily, [{ key: 'cacheRatio', label: 'Taxa de cache' }]),
    );
    breakdowns.append(
      renderBreakdownChart('Uso por projeto', vm.breakdowns.projects),
      renderBreakdownChart('Uso por modelo', vm.breakdowns.models),
      renderBreakdownChart('Uso por fonte', vm.breakdowns.sources),
    );
  }

  function renderNotes(vm) {
    notes.replaceChildren();
    const unavailable = cardDefinitions
      .map(([key, label]) => ({ label: vm.cards[key].label || label, metric: vm.cards[key] }))
      .filter(({ metric }) => metric.subtitle);
    if (!unavailable.length && vm.quality.import_errors === 0) return;

    const heading = document.createElement('strong');
    heading.textContent = 'Qualidade e disponibilidade';
    notes.appendChild(heading);
    unavailable.forEach(({ label, metric }) => {
      const line = document.createElement('p');
      line.textContent = `${label}: ${metric.subtitle}`;
      notes.appendChild(line);
    });
    if (vm.quality.import_errors > 0) {
      const line = document.createElement('p');
      line.textContent = `${vm.quality.import_errors} erro(s) de importação registrado(s).`;
      notes.appendChild(line);
    }
  }

  function clearDataRegions() {
    cards.replaceChildren();
    trends.replaceChildren();
    breakdowns.replaceChildren();
    notes.replaceChildren();
  }

  window.addEventListener('message', (event) => {
    const message = event.data;
    if (!message || typeof message.type !== 'string') return;
    if (message.type === 'loading') {
      status.textContent = 'Carregando dados do AgentScope...';
      clearDataRegions();
      return;
    }
    if (message.type === 'error') {
      clearDataRegions();
      status.textContent = message.message || 'Falha ao carregar AgentScope.';
      return;
    }
    if (message.type === 'snapshot') {
      const vm = message.payload;
      status.textContent = vm.isEmpty
        ? 'Nenhum dado encontrado para os filtros selecionados.'
        : vm.database ? `Banco: ${vm.database}` : 'Banco padrão do AgentScope';
      renderFilters(vm);
      renderCards(vm);
      renderCharts(vm);
      renderNotes(vm);
    }
  });
})();
