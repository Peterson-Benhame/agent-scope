import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';

describe('Codex account dashboard media', () => {
  it('renders a synchronization action and posts syncCodex', () => {
    const mediaPath = path.resolve(__dirname, '../../../media/codex-account.js');
    const source = fs.readFileSync(mediaPath, 'utf8');

    assert.ok(source.includes('Sincronizar Codex'));
    assert.ok(source.includes("type: 'syncCodex'"));
    assert.ok(source.includes('codexSyncing'));
  });
});
