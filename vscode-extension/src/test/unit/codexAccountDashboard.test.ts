import * as assert from 'assert';

import {
  ExtensionSnapshot,
  parseExtensionSnapshot,
} from '../../contracts/snapshot';
import { toDashboardViewModel } from '../../views/dashboardViewModel';

const snapshot: ExtensionSnapshot = {
  schema: 'agentscope-extension-snapshot',
  version: 2,
  generated_at: '2026-08-20T16:01:00Z',
  database: 'agentscope.db',
  codex_account: {
    available: true,
    captured_at: '2026-08-20T16:00:00+00:00',
    plan_type: 'pro',
    primary_used_percent: 63,
    primary_resets_at: 1787241600,
    secondary_used_percent: 42,
    secondary_resets_at: 1787846400,
    credits: {
      has_credits: true,
      balance: '18.42',
      unlimited: false,
    },
    spend_control_reached: false,
  },
  filters: { period: '7d' },
  summary: {
    sessions: 1,
    total_tokens: 100,
    tokens_saved: 0,
    cache_ratio: 0.5,
    observed_cost_usd: null,
    estimated_cost_usd: null,
    known_estimated_cost_usd: null,
    estimated_cost_events_total: 0,
    estimated_cost_events_priced: 0,
    estimated_cost_coverage: 0,
    estimated_cost_complete: false,
    estimated_savings_usd: null,
  },
  billing: {
    mode: 'chatgpt_codex_plan',
    confidence: 'explicit',
    estimated_cost_basis: 'openai_api_equivalent',
    is_observed_spend: false,
  },
  availability: {
    observed_cost: { available: false, reason: 'source_does_not_report_cost' },
    estimated_cost: { available: false, reason: 'insufficient_pricing_data' },
    estimated_savings: { available: false, reason: 'no_optimization_data' },
  },
  series: { daily: [] },
  breakdowns: { projects: [], models: [], sources: [], clients: [] },
  dimensions: { projects: [], models: [], sources: [], users: [], machines: [] },
  quality: {
    import_errors: 0,
    tokens_without_model: 0,
    identity_confidence: {},
    correlation_confidence: {},
  },
};

describe('Codex account dashboard', () => {
  it('accepts optional Codex account data in snapshot v2', () => {
    const parsed = parseExtensionSnapshot(snapshot);
    assert.strictEqual(parsed.codex_account?.plan_type, 'pro');
  });

  it('formats stored Codex account data for the dashboard', () => {
    const vm = toDashboardViewModel(snapshot, { period: '7d' });
    assert.strictEqual(vm.codexAccount?.title, 'Codex — ChatGPT Pro');
    assert.strictEqual(vm.codexAccount?.primaryUsageLabel, '63,00%');
    assert.strictEqual(vm.codexAccount?.secondaryUsageLabel, '42,00%');
    assert.strictEqual(vm.codexAccount?.creditBalanceLabel, '18,42 créditos');
    assert.ok(vm.codexAccount?.syncedAtLabel.startsWith('Conta sincronizada:'));
  });

  it('keeps backend plan identifiers that do not have a known product mapping', () => {
    const vm = toDashboardViewModel(
      {
        ...snapshot,
        codex_account: {
          ...snapshot.codex_account!,
          plan_type: 'prolite',
          credits: {
            has_credits: false,
            balance: '0',
            unlimited: false,
          },
        },
      },
      { period: '7d' },
    );

    assert.strictEqual(vm.codexAccount?.title, 'Codex — prolite');
    assert.strictEqual(vm.codexAccount?.creditBalanceLabel, '0,00 créditos');
  });

  it('keeps version 2 snapshots without Codex account data valid', () => {
    const { codex_account: _ignored, ...withoutAccount } = snapshot;
    const parsed = parseExtensionSnapshot(withoutAccount);
    assert.strictEqual(parsed.codex_account, undefined);
  });
});
