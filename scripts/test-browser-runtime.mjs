import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import process from 'node:process';
import WebSocket from 'ws';

const chromeCandidates = [
  process.env.CHROME_PATH,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);

async function existingBrowser() {
  const { access } = await import('node:fs/promises');
  for (const candidate of chromeCandidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }
  throw new Error('Chrome or Edge was not found. Set CHROME_PATH to its executable.');
}

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function terminateProcessTree(processId) {
  await new Promise((resolve) => {
    const killer = spawn('taskkill.exe', ['/PID', String(processId), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    });
    killer.once('error', resolve);
    killer.once('exit', resolve);
  });
}

async function removeProfile(profileDirectory) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      await rm(profileDirectory, { recursive: true, force: true });
      return;
    } catch (error) {
      if (attempt === 19) {
        console.warn(`Unable to remove browser profile ${profileDirectory}: ${error.message}`);
        return;
      }
      await delay(250);
    }
  }
}

async function waitForDevtools(profileDirectory, browserProcess) {
  const portFile = path.join(profileDirectory, 'DevToolsActivePort');
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (browserProcess.exitCode !== null) {
      throw new Error(`Headless browser exited early with code ${browserProcess.exitCode}.`);
    }
    try {
      const [port] = (await readFile(portFile, 'utf8')).trim().split(/\r?\n/);
      if (port) return Number(port);
    } catch {}
    await delay(50);
  }
  throw new Error('Timed out waiting for the headless browser debugging port.');
}

class CdpClient {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.socket.once('open', resolve);
      this.socket.once('error', reject);
    });
    this.socket.on('message', (buffer) => {
      const message = JSON.parse(buffer.toString());
      if (message.id) {
        const request = this.pending.get(message.id);
        if (!request) return;
        this.pending.delete(message.id);
        if (message.error) request.reject(new Error(message.error.message));
        else request.resolve(message.result);
      } else {
        this.events.push(message);
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text || 'Browser evaluation failed.');
    }
    return result.result.value;
  }

  close() {
    this.socket.close();
  }
}

async function waitFor(check, timeoutMilliseconds, description) {
  const deadline = Date.now() + timeoutMilliseconds;
  let latest;
  while (Date.now() < deadline) {
    latest = await check();
    if (latest) return latest;
    await delay(500);
  }
  throw new Error(`Timed out waiting for ${description}. Last state: ${JSON.stringify(latest)}`);
}

function isRuntimeFailure({ method, params }) {
  if (method === 'Runtime.exceptionThrown') return true;
  if (method !== 'Runtime.consoleAPICalled' || params.type !== 'error') return false;
  const message = params.args
    ?.map((argument) => argument.value || argument.description || '')
    .join(' ') || '';
  return /(?:uncaught|abort(?:ed)?|fatal error|worker sent an error|game content error|failed to asynchronously prepare wasm)/i.test(message);
}

async function main() {
  const targetUrl = process.env.UQM_TEST_URL || 'http://localhost:3000/';
  const requestedLanguage = process.env.UQM_TEST_LANGUAGE === 'en' ? 'en' : 'zh-TW';
  const emulateMobile = process.env.UQM_TEST_MOBILE === '1';
  const profileDirectory = await mkdtemp(path.join(tmpdir(), 'uqm-web-chrome-'));
  const browserPath = await existingBrowser();
  const browserProcess = spawn(browserPath, [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--lang=zh-TW',
    '--remote-debugging-port=0',
    `--user-data-dir=${profileDirectory}`,
    'about:blank',
  ], { stdio: 'ignore', windowsHide: true });

  let client;
  try {
    const port = await waitForDevtools(profileDirectory, browserProcess);
    const target = await fetch(
      `http://127.0.0.1:${port}/json/new?${encodeURIComponent('about:blank')}`,
      { method: 'PUT' },
    ).then((response) => response.json());
    client = new CdpClient(target.webSocketDebuggerUrl);
    await client.open();
    await Promise.all([
      client.send('Page.enable'),
      client.send('Runtime.enable'),
      client.send('Network.enable'),
      client.send('Emulation.setLocaleOverride', { locale: 'zh-TW' }),
    ]);
    if (emulateMobile) {
      await client.send('Page.addScriptToEvaluateOnNewDocument', {
        source: `
          Object.defineProperty(Navigator.prototype, 'userAgentData', {
            configurable: true,
            get: () => ({ mobile: true, platform: 'Android', brands: [] }),
          });
          Object.defineProperty(Navigator.prototype, 'maxTouchPoints', {
            configurable: true,
            get: () => 5,
          });
        `,
      });
    }
    await client.send('Page.navigate', { url: targetUrl });

    await waitFor(
      () => client.evaluate(`Boolean(document.querySelector('.launch-button'))`),
      20_000,
      'the launcher',
    );

    if (requestedLanguage === 'en') {
      await client.evaluate(`Array.from(document.querySelectorAll('.language-switch button'))
        .find((button) => button.textContent.trim() === 'English')?.click()`);
      await waitFor(
        () => client.evaluate(`document.querySelector('.language-switch .active')?.textContent?.trim() === 'English'`),
        5_000,
        'the English language selection',
      );
    }

    const launcher = await client.evaluate(`(() => ({
      isolated: crossOriginIsolated,
      browserLanguages: navigator.languages,
      browserLanguage: navigator.language,
      title: document.querySelector('h1')?.textContent,
      activeLanguage: document.querySelector('.language-switch .active')?.textContent?.trim(),
      touchControlsVisible: Boolean(document.querySelector('.battle-controls')),
    }))()`);
    if (!launcher.isolated) throw new Error('The launcher is not cross-origin isolated.');
    const expectedLanguageLabel = requestedLanguage === 'en' ? 'English' : '繁體中文';
    if (launcher.activeLanguage !== expectedLanguageLabel) {
      throw new Error(`Expected ${expectedLanguageLabel}, got ${launcher.activeLanguage}.`);
    }
    if (launcher.touchControlsVisible) {
      throw new Error('Desktop browser unexpectedly displayed touch battle controls.');
    }

    await client.evaluate(`document.querySelector('.launch-button').click()`);
    let runtimeSnapshot = null;
    let lastProgressLog = 0;
    let runtime;
    try {
      runtime = await waitFor(
        async () => {
          const state = await client.evaluate(`(() => {
        const frame = document.querySelector('iframe');
        const game = frame?.contentWindow;
        if (!game) return null;
        return {
          ready: !document.querySelector('.loading-screen'),
          isolated: game.crossOriginIsolated,
          apiReady: typeof game.Module?._uqm_web_battle_state === 'function',
          canvasWidth: game.document.querySelector('#canvas')?.width || 0,
          canvasHeight: game.document.querySelector('#canvas')?.height || 0,
          status: game.document.querySelector('#engine-status-text')?.textContent || '',
          language: game.uqmWeb?.language || '',
          parentProgress: document.querySelector('.loading-screen')?.textContent?.replace(/\s+/g, ' ').trim() || '',
        };
      })()`);
          runtimeSnapshot = state;
          if (Date.now() - lastProgressLog >= 15_000) {
            console.log(`Runtime progress: ${JSON.stringify(state)}`);
            lastProgressLog = Date.now();
          }
          const failure = client.events.find(isRuntimeFailure);
          if (failure) {
            throw new Error(`Browser runtime failure: ${JSON.stringify(failure)}`);
          }
          return state?.ready && state.apiReady && state.canvasWidth > 0 ? state : null;
        },
        360_000,
        'the WebAssembly runtime',
      );
    } catch (error) {
      const networkFailures = client.events.filter(({ method }) => method === 'Network.loadingFailed');
      error.message += ` Last runtime snapshot: ${JSON.stringify(runtimeSnapshot)}. Network failures: ${JSON.stringify(networkFailures.slice(0, 5))}`;
      throw error;
    }

    await delay(Number(process.env.UQM_TEST_STABILITY_MS) || 5_000);
    const visual = await client.evaluate(`(() => {
      const canvas = document.querySelector('iframe')?.contentDocument?.querySelector('#canvas');
      const context = canvas?.getContext('2d');
      if (!canvas || !context) return { width: 0, height: 0, sampled: 0, nonBlack: 0 };
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const columns = 64;
      const rows = 48;
      let sampled = 0;
      let nonBlack = 0;
      for (let row = 0; row < rows; row += 1) {
        const y = Math.min(canvas.height - 1, Math.floor((row + 0.5) * canvas.height / rows));
        for (let column = 0; column < columns; column += 1) {
          const x = Math.min(canvas.width - 1, Math.floor((column + 0.5) * canvas.width / columns));
          const offset = (y * canvas.width + x) * 4;
          sampled += 1;
          if (pixels[offset] > 8 || pixels[offset + 1] > 8 || pixels[offset + 2] > 8) nonBlack += 1;
        }
      }
      return { width: canvas.width, height: canvas.height, sampled, nonBlack };
    })()`);
    if (visual.width < 1440 || visual.height < 1080 ||
        !visual.sampled || visual.nonBlack < 20) {
      throw new Error(`The engine started but did not render a visible frame: ${JSON.stringify(visual)}.`);
    }

    let mobile = null;
    if (emulateMobile &&
        !['super-melee-touch', 'super-melee-battle'].includes(process.env.UQM_TEST_FLOW)) {
      mobile = await client.evaluate(`(async () => {
        const frame = document.querySelector('iframe');
        const game = frame?.contentWindow;
        game.Module._uqm_web_battle_state = () => 7;
        await new Promise((resolve) => setTimeout(resolve, 400));
        const labels = Array.from(document.querySelectorAll('.battle-controls button'))
          .map((button) => button.getAttribute('aria-label'));
        const observed = [];
        game.document.addEventListener('keydown', (event) => observed.push({
          type: event.type,
          code: event.code,
          location: event.location,
        }), { once: true, capture: true });
        const fire = Array.from(document.querySelectorAll('.battle-controls button'))
          .find((button) => button.getAttribute('aria-label') === '${requestedLanguage === 'en' ? 'Fire' : '武器'}');
        const originalCapture = fire?.setPointerCapture;
        if (fire) fire.setPointerCapture = () => {};
        fire?.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 1 }));
        await new Promise((resolve) => setTimeout(resolve, 100));
        fire?.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 1 }));
        if (fire && originalCapture) fire.setPointerCapture = originalCapture;
        await new Promise((resolve) => setTimeout(resolve, 100));
        return { labels, observed };
      })()`);
      if (mobile.labels.length !== 10 || mobile.observed[0]?.code !== 'ControlRight') {
        throw new Error(`Mobile battle controls failed: ${JSON.stringify(mobile)}.`);
      }
    }

    let flow = null;
    if (process.env.UQM_TEST_FLOW?.startsWith('super-melee')) {
      await delay(Number(process.env.UQM_TEST_MENU_WAIT_MS) || 40_000);
      let selectSuperMelee;
      if (['super-melee-click', 'super-melee-touch', 'super-melee-battle']
        .includes(process.env.UQM_TEST_FLOW)) {
        const point = await client.evaluate(`(() => {
          const frame = document.querySelector('iframe');
          const canvas = frame?.contentDocument?.querySelector('#canvas');
          if (!frame || !canvas) throw new Error('The game canvas is unavailable.');
          const frameRect = frame.getBoundingClientRect();
          const canvasRect = canvas.getBoundingClientRect();
          return {
            x: frameRect.left + canvasRect.left + canvasRect.width * 0.5,
            y: frameRect.top + canvasRect.top + canvasRect.height * 0.545,
          };
        })()`);
        if (process.env.UQM_TEST_FLOW === 'super-melee-touch') {
          await client.send('Input.dispatchTouchEvent', {
            type: 'touchStart',
            touchPoints: [{ ...point, radiusX: 2, radiusY: 2, force: 1, id: 1 }],
          });
          await client.send('Input.dispatchTouchEvent', {
            type: 'touchEnd',
            touchPoints: [],
          });
        } else {
          await client.send('Input.dispatchMouseEvent', { type: 'mouseMoved', ...point });
          await delay(250);
          await client.send('Input.dispatchMouseEvent', {
            type: 'mousePressed',
            ...point,
            button: 'left',
            buttons: 1,
            clickCount: 1,
          });
          await client.send('Input.dispatchMouseEvent', {
            type: 'mouseReleased',
            ...point,
            button: 'left',
            buttons: 0,
            clickCount: 1,
          });
        }
        await delay(3_000);
        selectSuperMelee = await client.evaluate(`(() => {
          const game = document.querySelector('iframe')?.contentWindow;
          return {
            method: '${process.env.UQM_TEST_FLOW === 'super-melee-touch' ? 'touch' : 'mouse'}',
            battleState: game.uqmWeb.battleState(),
          };
        })()`);
      } else {
        selectSuperMelee = await client.evaluate(`(async () => {
        const game = document.querySelector('iframe')?.contentWindow;
        if (!game?.uqmWeb) throw new Error('The game input bridge is unavailable.');
        const tap = async (definition) => {
          game.uqmWeb.tapKey(definition);
          await new Promise((resolve) => setTimeout(resolve, 180));
        };
        await tap({ key: 'ArrowDown', code: 'ArrowDown', keyCode: 40 });
        await tap({ key: 'ArrowDown', code: 'ArrowDown', keyCode: 40 });
        await tap({ key: 'Enter', code: 'Enter', keyCode: 13 });
        await new Promise((resolve) => setTimeout(resolve, 3_000));
        return { method: 'keyboard', battleState: game.uqmWeb.battleState() };
      })()`);
      }
      flow = selectSuperMelee;
      if (process.env.UQM_TEST_FLOW === 'super-melee-battle') {
        const battle = await client.evaluate(`(async () => {
          const game = document.querySelector('iframe')?.contentWindow;
          const hold = async (id, definition, after = 500) => {
            game.uqmWeb.keyDown(id, definition);
            await new Promise((resolve) => setTimeout(resolve, 250));
            game.uqmWeb.keyUp(id);
            await new Promise((resolve) => setTimeout(resolve, after));
          };
          await hold('flow-enter', { key: 'Enter', code: 'Enter', keyCode: 13 }, 2_500);
          await hold('flow-p1', { key: 'Control', code: 'ControlRight', keyCode: 17, location: 2 });
          await hold('flow-p2', { key: 'q', code: 'KeyQ', keyCode: 81 }, 5_000);
          return { battleState: game.uqmWeb.battleState() };
        })()`);
        flow = { ...flow, actualBattleState: battle.battleState };
        if ((battle.battleState & 1) === 0) {
          if (process.env.UQM_TEST_SCREENSHOT) {
            const failedCapture = await client.send('Page.captureScreenshot', {
              format: 'png',
              captureBeyondViewport: false,
            });
            const failedPath = path.resolve(process.env.UQM_TEST_SCREENSHOT);
            await mkdir(path.dirname(failedPath), { recursive: true });
            await writeFile(failedPath, Buffer.from(failedCapture.data, 'base64'));
          }
          throw new Error(`A Super Melee battle did not start: ${JSON.stringify(flow)}.`);
        }
        if (emulateMobile) {
          mobile = await client.evaluate(`(() => ({
            actualBattle: true,
            labels: Array.from(document.querySelectorAll('.battle-controls button'))
              .map((button) => button.getAttribute('aria-label')),
          }))()`);
          const expectedButtons =
            ((battle.battleState & 2) ? 5 : 0) + ((battle.battleState & 4) ? 5 : 0);
          if (mobile.labels.length !== expectedButtons) {
            throw new Error(`Actual battle touch controls failed: ${JSON.stringify(mobile)}.`);
          }
        }
      }
      if (process.env.UQM_TEST_FLOW === 'super-melee-back') {
        const back = await client.evaluate(`(async () => {
          const button = document.querySelector('.back-button');
          button.click();
          await new Promise((resolve) => setTimeout(resolve, 250));
          const notice = document.querySelector('.back-notice')?.textContent || '';
          button.click();
          await new Promise((resolve) => setTimeout(resolve, 250));
          return { notice, returnedToLauncher: Boolean(document.querySelector('.launch-button')) };
        })()`);
        flow = { ...flow, ...back };
        if (!flow.notice || !flow.returnedToLauncher) {
          throw new Error(`Universal back control failed: ${JSON.stringify(flow)}.`);
        }
      }
    }

    const failures = client.events.filter((event) =>
      event.method === 'Network.loadingFailed' || isRuntimeFailure(event));
    if (failures.length) {
      throw new Error(`Browser reported ${failures.length} runtime failure(s): ${JSON.stringify(failures.slice(0, 5))}`);
    }

    if (process.env.UQM_TEST_SCREENSHOT) {
      await delay(Number(process.env.UQM_TEST_SETTLE_MS) || 3_000);
      const screenshotPath = path.resolve(process.env.UQM_TEST_SCREENSHOT);
      await mkdir(path.dirname(screenshotPath), { recursive: true });
      const capture = await client.send('Page.captureScreenshot', {
        format: 'png',
        captureBeyondViewport: false,
      });
      await writeFile(screenshotPath, Buffer.from(capture.data, 'base64'));
    }

    if (process.env.UQM_TEST_LOGS) {
      const consoleMessages = client.events
        .filter(({ method }) => method === 'Runtime.consoleAPICalled')
        .map(({ params }) => ({
          type: params.type,
          text: params.args?.map((argument) => argument.value || argument.description || '').join(' ') || '',
        }));
      console.log(JSON.stringify({ consoleMessages }, null, 2));
    }

    console.log(JSON.stringify({ launcher, runtime, visual, mobile, flow, runtimeFailures: 0 }, null, 2));
  } finally {
    client?.close();
    if (browserProcess.exitCode === null) {
      await terminateProcessTree(browserProcess.pid);
    }
    await removeProfile(profileDirectory);
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
