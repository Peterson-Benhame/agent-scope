import * as assert from 'assert';

import { ExtensionSnapshot } from '../../contracts/snapshot';
import { toDashboardViewModel } from '../../views/dashboardViewModel';

const snapshot: ExtensionSnapshot = {
  schema: 'agentscope-extension-snapshot',
  version: 2,
  generated_at: '2026-08-19T14:00:00Z',
  database: 'agentscope.db',
  freshness: {
    last_imported_at: '2026-08-19 16:30:00',
    artifacts_tracked: 129,
  },
  filters: { period: '7d' },
  summary: {
    sessions: 77,
    total_tokens: 1465312344,
    tokens_saved: 1234,
    cache_ratio: 0.9463,
    observed_cost_usd: 13.777,
    estimated_cost_usd: 21.034,
    known_estimated_cost_usd: 21.034,
    estimated_cost_events_total: 4,
    estimated_cost_events_priced: 4,
    estimated_cost_coverage: 1,
    estimated_cost_complete: true,
    estimated_savings_usd: 76.891,
  },
  billing: {
    mode: 'unknown',
    confidence: 'unknown',
    estimated_cost_basis: 'openai_api_equivalent',
    is_observed_spend: false,
  },
  availability: {
    observed_cost: { available: true, reason: null },
    estimated_cost: { available: true, reason: null },
    estimated_savings: { available: true, reason: null },
  },
  series: {
    daily: [{
      date: '2026-08-19',
      sessions: 2,
      total_tokens: 1200,
      cache_ratio: 0.8,
      observed_cost_usd: null,
      estimated_cost_usd: 0.03,
      estimated_savings_usd: null,
    }],
  },
  breakdowns: {
    projects: [{ project: 'S584', sessions: 2, total_tokens: 1200 }],
    models: [{
      model: 'gpt-5.6-sol',
      sessions: 2,
      total_tokens: 1200,
      estimated_cost_usd: 1.25,
      cost_events_total: 4,
      cost_events_priced: 4,
      cost_complete: true,
    }, {
      model: 'codex-auto-review',
      sessions: 1,
      total_tokens: 42,
      estimated_cost_usd: null,
      cost_events_total: 1,
      cost_events_priced: 0,
      cost_complete: false,
    }],
    sources: [{ source: 'codex', sessions: 2, total_tokens: 1200 }],
  },
  dimensions: { projects: [], models: [], sources: [], users: [], machines: [] },
  quality: { import_errors: 0, tokens_without_model: 0, identity_confidence: {}, correlation_confidence: {} },
};

function withBilling(
  mode: 'api' | 'chatgpt_codex_plan' | 'unknown' | 'mixed',
  estimatedCostBasis: 'openai_api_estimate' | 'openai_api_equivalent',
): ExtensionSnapshot {
  return {
    ...snapshot,
    billing: {
      mode,
      confidence: mode === 'mixed' ? 'mixed' : mode === 'unknown' ? 'unknown' : 'explicit',
      estimated_cost_basis: estimatedCostBasis,
      is_observed_spend: false,
    },
  };
}

describe('dashboard view model', () => {
  it('formats executive cards using pt-BR presentation', () => {
    const vm = toDashboardViewModel(snapshot, { period: '7d' });
    assert.strictEqual(vm.isEmpty, false);
    assert.strictEqual(vm.cards.sessions.value, '77');
    assert.strictEqual(vm.cards.totalTokens.value, '1.465.312.344');
    assert.strictEqual(vm.cards.tokensSaved.value, '1.234');
    assert.strictEqual(vm.cards.cacheRatio.value, '94,63%');
    assert.strictEqual(vm.cards.observedCost.value, 'US$ 13,78');
    assert.strictEqual(vm.cards.estimatedCost.value, 'US$ 21,03');
    assert.strictEqual(vm.cards.estimatedSavings.value, 'US$ 76,89');
  });

  it('shows a partial API-equivalent value with coverage instead of hiding the known subtotal', () => {
    const partial: ExtensionSnapshot = {
      ...snapshot,
      summary: {
        ...snapshot.summary,
        estimated_cost_usd: null,
        known_estimated_cost_usd: 31.65021856,
        estimated_cost_events_total: 682,
        estimated_cost_events_priced: 680,
        estimated_cost_coverage: 680 / 682,
        estimated_cost_complete: false,
      },
      availability: {
        ...snapshot.availability,
        estimated_cost: { available: false, reason: 'insufficient_pricing_data' },
      },
    };

    const vm = toDashboardViewModel(partial, { period: '7d' });

    assert.strictEqual(vm.cards.estimatedCost.label, 'Custo equivalente via API');
    assert.strictEqual(vm.cards.estimatedCost.value, 'US$ 31,65');
    assert.ok(vm.cards.estimatedCost.subtitle?.includes('Estimativa parcial'));
    assert.ok(vm.cards.estimatedCost.subtitle?.includes('680 de 682 eventos'));
    assert.ok(vm.cards.estimatedCost.subtitle?.includes('99,71%'));
    assert.ok(vm.cards.estimatedCost.subtitle?.includes('não representa gasto real'));
  });

  it('shows the latest successful collection timestamp', () => {
    const vm = toDashboardViewModel(snapshot, { period: '7d' });
    assert.ok(vm.lastImportedLabel.startsWith('Última coleta:'));
    assert.ok(vm.lastImportedLabel.includes('129 arquivos'));
  });

  it('shows unavailable values with an explanatory reason', () => {
    const vm = toDashboardViewModel({
      ...snapshot,
      summary: { ...snapshot.summary, observed_cost_usd: null },
      availability: {
        ...snapshot.availability,
        observed_cost: { available: false, reason: 'source_does_not_report_cost' },
      },
    }, { period: '7d' });
    assert.strictEqual(vm.cards.observedCost.value, 'Não disponível');
    assert.strictEqual(
      vm.cards.observedCost.subtitle,
      'A fonte selecionada não informa custo monetário observado.',
    );
  });

  it('labels unknown billing as API equivalent rather than spend', () => {
    const vm = toDashboardViewModel(
      withBilling('unknown', 'openai_api_equivalent'),
      { period: '7d' },
    );
    assert.strictEqual(vm.cards.estimatedCost.label, 'Custo equivalente via API');
    assert.ok(vm.cards.estimatedCost.subtitle?.includes('não representa gasto real'));
  });

  it('labels explicit API billing as estimated API cost', () => {
    const vm = toDashboardViewModel(
      withBilling('api', 'openai_api_estimate'),
      { period: '7d' },
    );
    assert.strictEqual(vm.cards.estimatedCost.label, 'Custo estimado API');
    assert.ok(vm.cards.estimatedCost.subtitle?.includes('não é cobrança observada'));
  });

  it('labels plan and mixed billing as API equivalent', () => {
    for (const mode of ['chatgpt_codex_plan', 'mixed'] as const) {
      const vm = toDashboardViewModel(
        withBilling(mode, 'openai_api_equivalent'),
        { period: '7d' },
      );
      assert.strictEqual(vm.cards.estimatedCost.label, 'Custo equivalente via API');
      assert.ok(vm.cards.estimatedCost.subtitle?.includes('não representa gasto real'));
    }
  });

  it('preserves null monetary chart points and maps breakdown labels', () => {
    const vm = toDashboardViewModel(snapshot, { period: '7d' });
    assert.strictEqual(vm.series.daily[0].observedCostUsd, null);
    assert.strictEqual(vm.series.daily[0].estimatedCostUsd, 0.03);
    assert.deepStrictEqual(vm.breakdowns.projects[0], {
      label: 'S584',
      sessions: 2,
      totalTokens: 1200,
    });
    assert.deepStrictEqual(vm.breakdowns.sources[0], {
      label: 'codex',
      sessions: 2,
      totalTokens: 1200,
    });
  });

  it('maps model cost coverage and billing label', () => {
    const vm = toDashboardViewModel(snapshot, { period: '7d' });

    assert.deepStrictEqual(vm.breakdowns.models[0], {
      label: 'gpt-5.6-sol',
      sessions: 2,
      totalTokens: 1200,
      estimatedCostUsd: 1.25,
      costEventsTotal: 4,
      costEventsPriced: 4,
      costComplete: true,
      costLabel: 'Custo equivalente via API',
    });
    assert.deepStrictEqual(vm.breakdowns.models[1], {
      label: 'codex-auto-review',
      sessions: 1,
      totalTokens: 42,
      estimatedCostUsd: null,
      costEventsTotal: 1,
      costEventsPriced: 0,
      costComplete: false,
      costLabel: 'Custo equivalente via API',
    });
  });

  it('marks a zero-session snapshot as empty', () => {
    const vm = toDashboardViewModel({
      ...snapshot,
      summary: {
        sessions: 0,
        total_tokens: 0,
        tokens_saved: 0,
        cache_ratio: null,
        observed_cost_usd: null,
        estimated_cost_usd: null,
        known_estimated_cost_usd: null,
        estimated_cost_events_total: 0,
        estimated_cost_events_priced: 0,
        estimated_cost_coverage: 0,
        estimated_cost_complete: false,
        estimated_savings_usd: null,
      },
      series: { daily: [] },
      breakdowns: { projects: [], models: [], sources: [] },
    }, { period: '7d' });
    assert.strictEqual(vm.isEmpty, true);
  });
});