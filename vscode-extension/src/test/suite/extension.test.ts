import * as assert from 'assert';
import * as vscode from 'vscode';

suite('AgentScope extension', () => {
  test('registers the MVP commands', async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('agentscope.openDashboard'));
    assert.ok(commands.includes('agentscope.refreshDashboard'));
    assert.ok(commands.includes('agentscope.selectDatabase'));
  });
});
