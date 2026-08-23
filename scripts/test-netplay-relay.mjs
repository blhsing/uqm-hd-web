import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import WebSocket from 'ws';

const port = 18_000 + Math.floor(Math.random() * 1_000);
const child = spawn(process.execPath, ['server/netplay-server.cjs'], {
  cwd: new URL('..', import.meta.url),
  env: { ...process.env, PORT: String(port), WEBSITE_HOSTNAME: 'localhost' },
  stdio: ['ignore', 'pipe', 'pipe'],
});

const endpoint = `ws://localhost:${port}/server.js?room=127.0.0.1:45678`;
const options = { headers: { Origin: 'http://localhost' } };

async function waitForRelay() {
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      const stderr = await new Promise(resolve => {
        let output = '';
        child.stderr.on('data', chunk => { output += chunk; });
        child.stderr.on('end', () => resolve(output));
      });
      throw new Error(`Relay exited before startup (${child.exitCode}): ${stderr}`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${port}/server.js?status=1`);
      if (response.ok) return;
    } catch {
      // The listen socket may not have been created yet.
    }
    await delay(50);
  }
  throw new Error('Relay did not become ready within five seconds.');
}

function openSocket() {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(endpoint, 'binary', options);
    socket.once('open', () => resolve(socket));
    socket.once('error', reject);
  });
}

function nextMessage(socket) {
  return new Promise((resolve, reject) => {
    socket.once('message', data => resolve(data));
    socket.once('error', reject);
  });
}

try {
  await waitForRelay();
  for (const [name, bytes] of [
    ['hires4x.zip', 369_756_672],
    ['3dovoice.zip', 146_438_532],
    ['3domusic.zip', 21_934_569],
    ['native1080-zh_TW.uqm', 189_687_374],
  ]) {
    const asset = await fetch(`http://127.0.0.1:${port}/server.js?asset=${encodeURIComponent(name)}`, {
      method: 'HEAD',
    });
    if (!asset.ok || Number(asset.headers.get('content-length')) !== bytes) {
      throw new Error(`Asset relay metadata failed for ${name}.`);
    }
  }
  const unknown = await fetch(`http://127.0.0.1:${port}/server.js?asset=unknown.zip`, {
    method: 'HEAD',
  });
  if (unknown.status !== 404) throw new Error('Asset relay allowlist failed.');
  const [first, second] = await Promise.all([openSocket(), openSocket()]);
  first.send(Buffer.from('first-to-second'));
  if (String(await nextMessage(second)) !== 'first-to-second') throw new Error('First relay direction failed.');
  second.send(Buffer.from('second-to-first'));
  if (String(await nextMessage(first)) !== 'second-to-first') throw new Error('Second relay direction failed.');
  first.close();
  second.close();
  console.log('Network Super Melee relay round-trip passed.');
} finally {
  child.kill();
}
