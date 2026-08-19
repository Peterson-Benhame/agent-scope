import * as assert from 'assert';

import {
  parseExtensionSnapshot,
  SnapshotContractError,
} from '../../contracts/snapshot';

const valid = {
  schema: 'agentscope-extension-snapshot',
  version: 2,
  generated_at: '2026-08-19T14:00:00Z',
  database: 'agentscope.db',
  filters: { period: '7d' },
  summary: {
    sessions: 1,
    total_tokens: 150,
    tokens_saved: 10,
    cache_ratio: 0.4,
    observed_cost_usd: null,
    estimated_cost_usd: 0.20,
    estimated_savings_usd: 0.03,
  },
  billing: {
    mode: 'unknown',
    confidence: 'unknown',
    estimated_cost_basis: 'openai_api_equivalent',
    is_observed_spend: false,
  },
  availability: {
    observed_cost: { available: false, reason: 'source_does_not_report_cost' },
    estimated_cost: { available: true, reason: null },
    estimated_savings: { available: true, reason: null },
  },
  series: {
    daily: [{
      date: '2026-08-19',
      sessions: 1,
      total_tokens: 150,
      cache_ratio: 0.4,
      observed_cost_usd: null,
      estimated_cost_usd: 0.20,
      estimated_savings_usd: 0.03,
    }],
  },
  breakdowns: {
    projects: [{ project: 'example-project', sessions: 1, total_tokens: 150 }],
    models: [{ model: 'gpt-example', sessions: 1, total_tokens: 150 }],
    sources: [{ source: 'codex', sessions: 1, total_tokens: 150 }],
  },
  dimensions: {
    projects: ['example-project'],
    models: ['gpt-example'],
    sources: ['codex'],
    users: ['Dev A'],
    machines: ['Notebook A'],
  },
  quality: {
    import_errors: 0,
    tokens_without_model: 0,
    identity_confidence: { inferred: 1 },
    correlation_confidence: {},
  },
};

describe('parseExtensionSnapshot', () => {
  it('accepts version 2 contract and preserves nullable money', () => {
    const parsed = parseExtensionSnapshot(valid);
    assert.deepStrictEqual(parsed, valid);
    assert.strictEqual(parsed.series.daily[0].observed_cost_usd, null);
  });

  it('rejects unsupported versions', () => {
    assert.throws(
      () => parseExtensionSnapshot({ ...valid, version: 1 }),
      (error: unknown) => error instanceof SnapshotContractError && error.code === 'SNAPSHOT_UNSUPPORTED_VERSION',
    );
  });

  it('rejects malformed summary', () => {
    assert.throws(
      () => parseExtensionSnapshot({ ...valid, summary: { sessions: 'one' } }),
      (error: unknown) => error instanceof SnapshotContractError && error.code === 'SNAPSHOT_INVALID_JSON',
    );
  });

  it('rejects malformed daily nullable metrics', () => {
    assert.throws(
      () => parseExtensionSnapshot({
        ...valid,
        series: { daily: [{ ...valid.series.daily[0], observed_cost_usd: 'unknown' }] },
      }),
      (error: unknown) => error instanceof SnapshotContractError && error.code === 'SNAPSHOT_INVALID_JSON',
    );
  });

  it('rejects malformed billing semantics', () => {
    assert.throws(
      () => parseExtensionSnapshot({
        ...valid,
        billing: { ...valid.billing, estimated_cost_basis: 'actual_spend' },
      }),
      (error: unknown) => error instanceof SnapshotContractError && error.code === 'SNAPSHOT_INVALID_JSON',
    );
  });
});
