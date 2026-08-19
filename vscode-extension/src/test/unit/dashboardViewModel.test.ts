import * as assert from 'assert';

import { ExtensionSnapshot } from '../../contracts/snapshot';
import { toDashboardViewModel } from '../../views/dashboardViewModel';

const snapshot: ExtensionSnapshot = {
  schema: 'agentscope-extension-snapshot',
  version: 1,
  generated_at: '2026-08-19T14:00:00Z',
  database: 'agentscope.db',
  filters: { period: '7d' },
  summary: {
    sessions: 77,
    total_tokens: 1465312344,
    tokens_saved: 1234,
    cache_ratio: 0.9463,
    observed_cost_usd: 13.777,
    estimated_savings_usd: 76.891,
  },
  dimensions: { projects: [], models: [], sources: [], users: [], machines: [] },
  quality: { import_errors: 0, tokens_without_model: 0, identity_confidence: {}, correlation_confidence: {} },
};

describe('dashboard view model', () => {
  it('formats executive cards using pt-BR presentation', () => {
    const vm = toDashboardViewModel(snapshot, { period: '7d' });
    assert.strictEqual(vm.isEmpty, false);
    assert.strictEqual(vm.cards.sessions, '77');
    assert.strictEqual(vm.cards.totalTokens, '1.465.312.344');
    assert.strictEqual(vm.cards.tokensSaved, '1.234');
    assert.strictEqual(vm.cards.cacheRatio, '94,63%');
    assert.strictEqual(vm.cards.observedCost, 'US$ 13,78');
    assert.strictEqual(vm.cards.estimatedSavings, 'US$ 76,89');
  });

  it('shows unavailable for unknown monetary values', () => {
    const vm = toDashboardViewModel({
      ...snapshot,
      summary: { ...snapshot.summary, observed_cost_usd: null },
    }, { period: '7d' });
    assert.strictEqual(vm.cards.observedCost, 'Não disponível');
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
        estimated_savings_usd: null,
      },
    }, { period: '7d' });
    assert.strictEqual(vm.isEmpty, true);
  });
});
