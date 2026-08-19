import * as assert from 'assert';

import {
  AgentScopeClient,
  buildSnapshotArgs,
  ProcessRunner,
  SnapshotClientError,
} from '../../client/agentScopeClient';

const validSnapshot = JSON.stringify({
  schema: 'agentscope-extension-snapshot',
  version: 1,
  generated_at: '2026-08-19T14:00:00Z',
  database: 'agentscope.db',
  filters: { period: '7d' },
  summary: {
    sessions: 1,
    total_tokens: 150,
    tokens_saved: 0,
    cache_ratio: null,
    observed_cost_usd: null,
    estimated_savings_usd: null,
  },
  dimensions: { projects: [], models: [], sources: [], users: [], machines: [] },
  quality: { import_errors: 0, tokens_without_model: 0, identity_confidence: {}, correlation_confidence: {} },
});

class FakeRunner implements ProcessRunner {
  public executable = '';
  public args: readonly string[] = [];
  public timeout = 0;

  constructor(
    private readonly result: { stdout: string; stderr: string; exitCode: number } = {
      stdout: validSnapshot,
      stderr: '',
      exitCode: 0,
    },
    private readonly thrown?: unknown,
  ) {}

  async run(executable: string, args: readonly string[], timeoutMs: number) {
    this.executable = executable;
    this.args = args;
    this.timeout = timeoutMs;
    if (this.thrown) {
      throw this.thrown;
    }
    return this.result;
  }
}

describe('AgentScopeClient', () => {
  it('builds argument arrays without shell strings', async () => {
    const runner = new FakeRunner();
    const client = new AgentScopeClient({
      executablePath: 'agentscope',
      databasePath: 'C:/data/agentscope.db',
      runner,
    });

    await client.snapshot({ period: '7d', project: 'example-project' });

    assert.deepStrictEqual(runner.args, [
      'extension', 'snapshot', '--json',
      '--database', 'C:/data/agentscope.db',
      '--period', '7d',
      '--project', 'example-project',
    ]);
    assert.strictEqual(runner.timeout, 15_000);
  });

  it('forwards every dimension and omits period for custom dates', () => {
    assert.deepStrictEqual(
      buildSnapshotArgs({
        period: '30d',
        from: '2026-08-01',
        to: '2026-08-18',
        project: 'example-project',
        model: 'gpt-example',
        source: 'codex',
        user: 'Dev A',
        machine: 'Notebook A',
      }),
      [
        'extension', 'snapshot', '--json',
        '--from', '2026-08-01',
        '--to', '2026-08-18',
        '--project', 'example-project',
        '--model', 'gpt-example',
        '--source', 'codex',
        '--user', 'Dev A',
        '--machine', 'Notebook A',
      ],
    );
  });

  it('maps missing database process output', async () => {
    const runner = new FakeRunner({ stdout: '', stderr: 'database not found: missing.db', exitCode: 2 });
    const client = new AgentScopeClient({ runner });
    await assert.rejects(
      client.snapshot({ period: '7d' }),
      (error: unknown) => error instanceof SnapshotClientError && error.code === 'DATABASE_NOT_FOUND',
    );
  });

  it('maps missing executable', async () => {
    const missing = Object.assign(new Error('missing'), { code: 'ENOENT' });
    const client = new AgentScopeClient({ runner: new FakeRunner(undefined, missing) });
    await assert.rejects(
      client.snapshot({ period: '7d' }),
      (error: unknown) => error instanceof SnapshotClientError && error.code === 'AGENTSCOPE_NOT_FOUND',
    );
  });

  it('maps timeouts', async () => {
    const timeout = Object.assign(new Error('timeout'), { killed: true });
    const client = new AgentScopeClient({ runner: new FakeRunner(undefined, timeout) });
    await assert.rejects(
      client.snapshot({ period: '7d' }),
      (error: unknown) => error instanceof SnapshotClientError && error.code === 'SNAPSHOT_TIMEOUT',
    );
  });

  it('maps invalid stdout json', async () => {
    const runner = new FakeRunner({ stdout: 'not json', stderr: '', exitCode: 0 });
    const client = new AgentScopeClient({ runner });
    await assert.rejects(
      client.snapshot({ period: '7d' }),
      (error: unknown) => error instanceof SnapshotClientError && error.code === 'SNAPSHOT_INVALID_JSON',
    );
  });
});
