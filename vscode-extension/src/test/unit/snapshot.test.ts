import * as assert from 'assert';

import {
  parseExtensionSnapshot,
  SnapshotContractError,
} from '../../contracts/snapshot';

const valid = {
  schema: 'agentscope-extension-snapshot',
  version: 1,
  generated_at: '2026-08-19T14:00:00Z',
  database: 'agentscope.db',
  filters: { period: '7d' },
  summary: {
    sessions: 1,
    total_tokens: 150,
    tokens_saved: 10,
    cache_ratio: 0.4,
    observed_cost_usd: null,
    estimated_savings_usd: 0.03,
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
  it('accepts version 1 contract', () => {
    assert.deepStrictEqual(parseExtensionSnapshot(valid), valid);
  });

  it('rejects unsupported versions', () => {
    assert.throws(
      () => parseExtensionSnapshot({ ...valid, version: 2 }),
      (error: unknown) => error instanceof SnapshotContractError && error.code === 'SNAPSHOT_UNSUPPORTED_VERSION',
    );
  });

  it('rejects malformed summary', () => {
    assert.throws(
      () => parseExtensionSnapshot({ ...valid, summary: { sessions: 'one' } }),
      (error: unknown) => error instanceof SnapshotContractError && error.code === 'SNAPSHOT_INVALID_JSON',
    );
  });
});
