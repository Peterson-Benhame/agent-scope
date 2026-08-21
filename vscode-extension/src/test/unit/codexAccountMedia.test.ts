import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';

describe('Codex account dashboard media', () => {
  it('renders a synchronization action without acquiring a second VS Code API', () => {
    const mediaPath = path.resolve(__dirname, '../../../media/codex-account.js');
    const source = fs.readFileSync(mediaPath, 'utf8');

    assert.ok(source.includes('Sincronizar Codex'));
    assert.ok(!source.includes('acquireVsCodeApi()'));
    assert.ok(source.includes("agentscope:syncCodex"));
    assert.ok(source.includes('codexSyncing'));
  });

  it('keeps the existing Codex card visible while the dashboard refreshes', () => {
    const mediaPath = path.resolve(__dirname, '../../../media/codex-account.js');
    const source = fs.readFileSync(mediaPath, 'utf8');

    assert.ok(!source.includes("message.type === 'loading' || message.type === 'error'"));
    assert.ok(source.includes("message.type === 'error'"));
  });

  it('routes the internal sync event through the dashboard VS Code API instance', () => {
    const mediaPath = path.resolve(__dirname, '../../../media/dashboard.js');
    const source = fs.readFileSync(mediaPath, 'utf8');

    assert.ok(source.includes("agentscope:syncCodex"));
    assert.ok(source.includes("vscode.postMessage({ type: 'syncCodex' })"));
  });
});
