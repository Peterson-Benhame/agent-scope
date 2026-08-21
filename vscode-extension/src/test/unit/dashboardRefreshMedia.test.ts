import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';

describe('Dashboard manual refresh routing', () => {
  it('keeps the toolbar button on the refresh message', () => {
    const mediaPath = path.resolve(__dirname, '../../../media/dashboard.js');
    const source = fs.readFileSync(mediaPath, 'utf8');

    assert.ok(source.includes("vscode.postMessage({ type: 'refresh' })"));
  });

  it('uses a lightweight load message when the webview first opens', () => {
    const providerPath = path.resolve(__dirname, '../../views/dashboardViewProvider.js');
    const source = fs.readFileSync(providerPath, 'utf8');

    assert.ok(source.includes("this.handler?.({ type: 'load' })"));
  });

  it('routes load to snapshot-only and refresh to derived-data recalculation', () => {
    const extensionPath = path.resolve(__dirname, '../../extension.js');
    const source = fs.readFileSync(extensionPath, 'utf8');

    assert.ok(source.includes("case 'load':"));
    assert.ok(source.includes('await coordinator.refresh();'));
    assert.ok(source.includes("case 'refresh':"));
    assert.ok(source.includes('await coordinator.refreshDerived();'));
  });
});
