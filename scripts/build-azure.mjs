import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const nextCli = join(root, 'node_modules', 'next', 'dist', 'bin', 'next');
const result = spawnSync(process.execPath, [nextCli, 'build'], {
  cwd: root,
  env: {
    ...process.env,
    AZURE_STATIC_BUILD: '1',
  },
  stdio: 'inherit',
});

if (result.status !== 0) process.exit(result.status ?? 1);

const output = join(root, 'out');
if (!existsSync(output)) throw new Error('Next.js did not create the static output directory.');

cpSync(join(root, 'server', 'netplay-server.cjs'), join(output, 'server.js'));
cpSync(join(root, 'node_modules', 'ws'), join(output, 'node_modules', 'ws'), { recursive: true });

for (const name of ['hires4x.zip', '3dovoice.zip', '3domusic.zip', 'native1080-zh_TW.uqm']) {
  rmSync(join(output, 'game', 'content', 'addons', name), { force: true });
}
