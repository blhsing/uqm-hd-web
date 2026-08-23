import { cpSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = process.cwd();
const vinextCli = join(root, 'node_modules', 'vinext', 'dist', 'cli.js');
const result = spawnSync(process.execPath, [vinextCli, 'build'], {
  cwd: root,
  env: { ...process.env, SITES_BUILD: '1' },
  stdio: 'inherit',
});

if (result.status !== 0) process.exit(result.status ?? 1);

const publicRoot = join(root, 'public');
const clientRoot = join(root, 'dist', 'client');
mkdirSync(clientRoot, { recursive: true });

for (const name of ['assets', 'favicon.svg', 'og.png']) {
  const source = join(publicRoot, name);
  if (!existsSync(source)) throw new Error(`Missing launcher asset: ${source}`);
  cpSync(source, join(clientRoot, name), { recursive: true });
}

if (existsSync(join(clientRoot, 'game'))) {
  throw new Error('The Sites bundle unexpectedly contains the full game payload.');
}
