import * as assert from 'assert';

import {
  AgentScopeClient,
  ProcessRunner,
} from '../../client/agentScopeClient';

class RecordingRunner implements ProcessRunner {
  public calls: Array<{ executable: string; args: readonly string[]; timeoutMs: number }> = [];

  async run(executable: string, args: readonly string[], timeoutMs: number) {
    this.calls.push({ executable, args, timeoutMs });
    return {
      stdout: args.includes('codex-account')
        ? '{"status":"complete"}'
        : args.includes('usage-context')
          ? '{"sessions_updated":4,"errors":0}'
          : '{"events_scanned":10,"events_priced":9,"events_unpriced":1,"complete":false}',
      stderr: '',
      exitCode: 0,
    };
  }
}

describe('Codex dashboard synchronization', () => {
  it('syncs account, backfills Codex context, then recalculates costs', async () => {
    const runner = new RecordingRunner();
    const client = new AgentScopeClient({
      executablePath: 'agentscope',
      databasePath: 'C:/data/agentscope.db',
      runner,
    });

    const result = await client.syncCodexAndRecalculate();

    assert.deepStrictEqual(
      runner.calls.map((call) => call.args),
      [
        [
          'codex-account', 'sync',
          '--database', 'C:/data/agentscope.db',
          '--timeout-seconds', '30',
          '--json',
        ],
        [
          'usage-context', 'backfill',
          '--database', 'C:/data/agentscope.db',
          '--source', 'codex',
          '--json',
        ],
        [
          'costs', 'calculate',
          '--database', 'C:/data/agentscope.db',
          '--json',
        ],
      ],
    );
    assert.strictEqual(result.account.status, 'complete');
    assert.strictEqual(result.context.errors, 0);
    assert.strictEqual(result.costs.events_priced, 9);
    assert.ok(runner.calls.every((call) => call.timeoutMs === 30_000));
  });

  it('stops before recalculation when account sync fails', async () => {
    class FailureRunner extends RecordingRunner {
      async run(executable: string, args: readonly string[], timeoutMs: number) {
        this.calls.push({ executable, args, timeoutMs });
        return { stdout: '', stderr: 'sync failed', exitCode: 1 };
      }
    }

    const runner = new FailureRunner();
    const client = new AgentScopeClient({ runner });

    await assert.rejects(client.syncCodexAndRecalculate());
    assert.strictEqual(runner.calls.length, 1);
  });
});
