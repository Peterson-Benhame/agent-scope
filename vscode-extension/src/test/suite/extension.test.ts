import * as assert from 'assert';
import * as vscode from 'vscode';

suite('AgentScope extension', () => {
  test('activates and registers the MVP commands', async () => {
    const extension = vscode.extensions.getExtension('peterson-benhame.agentscope');
    assert.ok(extension, 'AgentScope extension must be installed in the test host');
    await extension.activate();

    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('agentscope.openDashboard'));
    assert.ok(commands.includes('agentscope.refreshDashboard'));
    assert.ok(commands.includes('agentscope.selectDatabase'));
    assert.ok(commands.includes('agentscope.filterBySource'));
    assert.ok(commands.includes('agentscope.filterByProject'));
  });

  test('can reveal the AgentScope view container without crashing activation', async () => {
    await vscode.commands.executeCommand('workbench.view.extension.agentscope');
    assert.ok(true);
  });
});
