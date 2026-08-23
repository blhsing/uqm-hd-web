import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..', 'public', 'game', 'content', 'addons');
const assets = [
  ['hires4x.zip', 369_756_672, '76af440bd845a63bd42b88913347374eb62c40c149d0bea37045a10bd0bd6618'],
  ['3dovoice.zip', 146_438_532, 'a14dc7d655297e1b6c6eedc2a4dee30a164646e6525e353bb7fdc5da75232b09'],
  ['3domusic.zip', 21_934_569, '7142332040c13a153856d22487aaf82e6b30fc4d22333bcf7607712843bca689'],
  ['3dovideo.zip', 885, '0fedb35025a8ff0cd9ff09aabe50e4dc4efc702b34471bf0f11de4aa501f7cbe'],
  ['native1080-zh_TW.uqm', 189_687_374, 'f24d1f55e326fe20bb577c53eb12836ecff71af7a8b34ea2520537ec4ef1aef2'],
];

async function sha256(path) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest('hex');
}

for (const [name, expectedBytes, expectedHash] of assets) {
  const path = join(root, name);
  const { size } = await stat(path);
  if (size !== expectedBytes) {
    throw new Error(`${name} has ${size} bytes; expected ${expectedBytes}.`);
  }
  const actualHash = await sha256(path);
  if (actualHash !== expectedHash) {
    throw new Error(`${name} has SHA-256 ${actualHash}; expected ${expectedHash}.`);
  }
  console.log(`${name}: ${size} bytes, SHA-256 verified`);
}

console.log('All staged browser assets match the tested production payloads.');
