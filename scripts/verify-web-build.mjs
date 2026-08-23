import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const output = join(root, 'out');
const game = join(output, 'game');

function requireFile(path, minimumBytes = 1) {
  if (!existsSync(path)) throw new Error(`Missing build artifact: ${path}`);
  const bytes = statSync(path).size;
  if (bytes < minimumBytes) throw new Error(`Build artifact is unexpectedly small: ${path} (${bytes} bytes)`);
  return bytes;
}

function sha256(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

const required = [
  ['index.html', 500],
  ['web.config', 500],
  ['server.js', 3_000],
  ['node_modules/ws/index.js', 100],
  ['game/uqm-hd.html', 500],
  ['game/uqm-hd.js', 10_000],
  ['game/uqm-hd.wasm', 100_000],
  ['game/uqm-hd.data', 10_000_000],
  ['game/content/addons/3domusic.zip', 20_000_000],
  ['game/content/addons/3dovoice.zip', 140_000_000],
  ['game/content/addons/3dovideo.zip', 500],
  ['game/content/addons/hires4x.zip', 360_000_000],
  ['game/content/addons/native1080-zh_TW.uqm', 180_000_000],
];

const sizes = Object.fromEntries(required.map(([relative, minimum]) => [relative, requireFile(join(output, relative), minimum)]));
const index = readFileSync(join(output, 'index.html'), 'utf8');
if (!index.includes('/starcontrol2/')) throw new Error('Static launcher was not built with the /starcontrol2 base path.');

const shell = readFileSync(join(game, 'uqm-hd.html'), 'utf8');
if (!shell.includes('uqm-hd.js')) throw new Error('WebAssembly shell does not load uqm-hd.js.');

const config = readFileSync(join(output, 'web.config'), 'utf8');
for (const header of ['Cross-Origin-Opener-Policy', 'Cross-Origin-Embedder-Policy', 'Cross-Origin-Resource-Policy']) {
  if (!config.includes(header)) throw new Error(`web.config is missing ${header}.`);
}

console.log(JSON.stringify({
  verified: true,
  files: sizes,
  wasmSha256: sha256(join(game, 'uqm-hd.wasm')),
  dataSha256: sha256(join(game, 'uqm-hd.data')),
}, null, 2));
