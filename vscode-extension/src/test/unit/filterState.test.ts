import * as assert from 'assert';

import {
  applyCustomRange,
  applyFilterPatch,
  applyPeriod,
  createDefaultFilterState,
  resetFilters,
} from '../../state/filterState';

describe('dashboard filter state', () => {
  it('switches between preset and custom periods', () => {
    const initial = createDefaultFilterState('7d');
    const custom = applyCustomRange(initial, '2026-08-01', '2026-08-18');
    assert.strictEqual(custom.period, null);
    assert.strictEqual(custom.from, '2026-08-01');
    const month = applyPeriod(custom, 'month');
    assert.strictEqual(month.period, 'month');
    assert.strictEqual(month.from, null);
    assert.strictEqual(month.to, null);
  });

  it('preserves independent dimension filters', () => {
    const state = applyFilterPatch(createDefaultFilterState('7d'), {
      project: 'example-project',
      source: 'codex',
      model: 'gpt-example',
      user: 'Dev A',
      machine: 'Notebook A',
    });
    assert.strictEqual(state.project, 'example-project');
    assert.strictEqual(state.source, 'codex');
    assert.strictEqual(state.model, 'gpt-example');
    assert.strictEqual(state.user, 'Dev A');
    assert.strictEqual(state.machine, 'Notebook A');
  });

  it('reset restores only the configured period', () => {
    assert.deepStrictEqual(
      resetFilters({ period: '7d', project: 'example-project' }, '30d'),
      { period: '30d' },
    );
  });
});
