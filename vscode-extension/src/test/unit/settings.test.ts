import * as assert from 'assert';

import { normalizeSettings } from '../../config/settings';

describe('AgentScope settings', () => {
  it('uses stable defaults', () => {
    assert.deepStrictEqual(normalizeSettings({}), {
      executablePath: 'agentscope',
      databasePath: '',
      defaultPeriod: '7d',
      autoRefresh: false,
      autoRefreshIntervalSeconds: 60,
    });
  });

  it('clamps refresh interval', () => {
    assert.strictEqual(
      normalizeSettings({ autoRefreshIntervalSeconds: 1 }).autoRefreshIntervalSeconds,
      10,
    );
  });
});
