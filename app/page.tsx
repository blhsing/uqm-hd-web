'use client';

import { PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';

type Language = 'en' | 'zh-TW';
type WebKey = { key: string; code: string; keyCode: number; location?: number };
type WebCommand = 'keyDown' | 'keyUp' | 'tapKey' | 'releaseAll' | 'focus' | 'resumeAudio';

const AZURE_GAME_BASE = 'https://test-officialwebsite.azurewebsites.net/starcontrol2';

const copy = {
  en: {
    eyebrow: 'The Ur-Quan Masters HD',
    title: 'Star Control II — Web Edition',
    description: 'The complete campaign and Super Melee, with browser saves and touch controls.',
    loading: 'Loading the complete game…',
    downloading: 'Downloading high-resolution game content',
    play: 'Launch game',
    back: 'Back',
    fullscreen: 'Fullscreen',
    backAgain: 'Back sent to the game. Tap again to return to the launcher.',
    controls: 'Battle controls',
    player1: 'Player 1',
    player2: 'Player 2',
    left: 'Turn left',
    right: 'Turn right',
    thrust: 'Thrust',
    fire: 'Fire',
    special: 'Special',
    touchHint: 'Tap menus directly. Battle buttons appear automatically when combat begins.',
    networkHint: 'Online Super Melee: both players choose Connect, enter 127.0.0.1, and share the same five-digit port as the room code.',
  },
  'zh-TW': {
    eyebrow: '《星際控制 II》HD',
    title: '星際控制 II — 網頁版',
    description: '完整戰役與超級對戰，支援瀏覽器存檔及觸控操作。',
    loading: '正在載入完整遊戲…',
    downloading: '正在下載高解析度遊戲內容',
    play: '啟動遊戲',
    back: '返回',
    fullscreen: '全螢幕',
    backAgain: '已向遊戲送出返回指令；再按一次可回到啟動畫面。',
    controls: '戰鬥操作',
    player1: '玩家一',
    player2: '玩家二',
    left: '左轉',
    right: '右轉',
    thrust: '推進',
    fire: '武器',
    special: '特殊能力',
    touchHint: '選單可直接點選；進入戰鬥後會自動顯示觸控按鈕。',
    networkHint: '網路超級對戰：兩邊都選「連線至遠端主機」，輸入 127.0.0.1，並共用同一個五位數連接埠作為房間碼。',
  },
} as const;

const keys = {
  escape: { key: 'Escape', code: 'Escape', keyCode: 27 },
  p1Left: { key: 'ArrowLeft', code: 'ArrowLeft', keyCode: 37 },
  p1Right: { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39 },
  p1Thrust: { key: 'ArrowUp', code: 'ArrowUp', keyCode: 38 },
  p1Fire: { key: 'Control', code: 'ControlRight', keyCode: 17, location: 2 },
  p1Special: { key: 'Shift', code: 'ShiftRight', keyCode: 16, location: 2 },
  p2Left: { key: 's', code: 'KeyS', keyCode: 83 },
  p2Right: { key: 'f', code: 'KeyF', keyCode: 70 },
  p2Thrust: { key: 'e', code: 'KeyE', keyCode: 69 },
  p2Fire: { key: 'q', code: 'KeyQ', keyCode: 81 },
  p2Special: { key: 'a', code: 'KeyA', keyCode: 65 },
} satisfies Record<string, WebKey>;

function preferredLanguage(): Language {
  const saved = window.localStorage.getItem('uqm-language');
  if (saved === 'en' || saved === 'zh-TW') {
    return saved;
  }

  const primary = navigator.languages?.[0] || navigator.language;
  const traditionalChinese = /^zh-(?:Hant(?:-|$)|TW(?:-|$)|HK(?:-|$)|MO(?:-|$))/i.test(primary);
  return traditionalChinese ? 'zh-TW' : 'en';
}

function isMobileBrowser(): boolean {
  const navigatorWithHints = navigator as Navigator & {
    userAgentData?: { mobile?: boolean };
  };
  if (typeof navigatorWithHints.userAgentData?.mobile === 'boolean') {
    return navigatorWithHints.userAgentData.mobile;
  }

  const mobileUserAgent = /Android|iPhone|iPad|iPod|Mobile|IEMobile|Opera Mini/i.test(
    navigator.userAgent,
  );
  const modernIPad = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
  return mobileUserAgent || modernIPad;
}

export default function Home() {
  const [language, setLanguage] = useState<Language>('en');
  const [hydrated, setHydrated] = useState(false);
  const [mobileControls, setMobileControls] = useState(false);
  const [running, setRunning] = useState(false);
  const [ready, setReady] = useState(false);
  const [inBattle, setInBattle] = useState(false);
  const [battlePlayers, setBattlePlayers] = useState({ player1: true, player2: false });
  const [loadingDetail, setLoadingDetail] = useState<{ label: string; progress: number } | null>(null);
  const [backNotice, setBackNotice] = useState(false);
  const [basePath, setBasePath] = useState('');
  const [gameBase, setGameBase] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const lastBackRef = useRef(0);
  const text = copy[language];

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setLanguage(preferredLanguage());
      setMobileControls(isMobileBrowser());
      const deploymentPath = window.location.pathname.startsWith('/starcontrol2')
        ? '/starcontrol2'
        : '';
      const localHost = /^(?:localhost|127(?:\.\d+){3}|\[?::1\]?)$/i.test(window.location.hostname);
      setBasePath(deploymentPath);
      setGameBase((deploymentPath || localHost) ? deploymentPath : AZURE_GAME_BASE);
      setHydrated(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const sendCommand = useCallback((command: WebCommand, payload: Record<string, unknown> = {}) => {
    try {
      const frame = iframeRef.current;
      if (!frame?.contentWindow) return;
      const targetOrigin = new URL(frame.src, window.location.href).origin;
      frame.contentWindow.postMessage({ type: 'uqm-command', command, ...payload }, targetOrigin);
    } catch {
      // The iframe may be navigating while the launcher is being reset.
    }
  }, []);

  useEffect(() => {
    if (!running) return;

    const onMessage = (event: MessageEvent) => {
      const frame = iframeRef.current;
      if (!frame?.contentWindow || event.source !== frame.contentWindow) return;
      const expectedOrigin = new URL(frame.src, window.location.href).origin;
      if (event.origin !== expectedOrigin) return;

      if (event.data?.type === 'uqm-ready') {
        setReady(true);
        setLoadingDetail(null);
        window.setTimeout(() => sendCommand('focus'), 0);
      } else if (event.data?.type === 'uqm-state') {
        setInBattle(Boolean(event.data.inBattle));
        setBattlePlayers({
          player1: Boolean(event.data.player1),
          player2: Boolean(event.data.player2),
        });
      } else if (event.data?.type === 'uqm-loading') {
        const fileProgress = Number(event.data.progress) || 0;
        const fileIndex = Math.max(1, Number(event.data.file) || 1);
        const fileCount = Math.max(fileIndex, Number(event.data.files) || fileIndex);
        setLoadingDetail({
          label: `${text.downloading} · ${fileIndex}/${fileCount}`,
          progress: Math.min(1, Math.max(0, (fileIndex - 1 + fileProgress) / fileCount)),
        });
      } else if (event.data?.type === 'uqm-error') {
        setLoadingDetail({ label: String(event.data.message || text.loading), progress: 0 });
      }
    };
    window.addEventListener('message', onMessage);

    return () => {
      window.removeEventListener('message', onMessage);
      sendCommand('releaseAll');
    };
  }, [running, sendCommand, text.downloading, text.loading]);

  const selectLanguage = (next: Language) => {
    window.localStorage.setItem('uqm-language', next);
    setLanguage(next);
    if (running) {
      sendCommand('releaseAll');
      setReady(false);
      setInBattle(false);
      setBattlePlayers({ player1: true, player2: false });
      setLoadingDetail(null);
      setRunning(false);
      window.setTimeout(() => setRunning(true), 0);
    }
  };

  const gameUrl = useMemo(
    () => `${gameBase}/game/uqm-hd.html?lang=${encodeURIComponent(language)}`,
    [gameBase, language],
  );

  const goBack = () => {
    if (!running) {
      if (window.history.length > 1) window.history.back();
      return;
    }

    const now = Date.now();
    if (now - lastBackRef.current < 1600) {
      sendCommand('releaseAll');
      setRunning(false);
      setReady(false);
      setInBattle(false);
      setBattlePlayers({ player1: true, player2: false });
      setLoadingDetail(null);
      setBackNotice(false);
      lastBackRef.current = 0;
      return;
    }

    sendCommand('tapKey', { definition: keys.escape });
    lastBackRef.current = now;
    setBackNotice(true);
    window.setTimeout(() => setBackNotice(false), 1600);
  };

  const toggleFullscreen = async () => {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await document.documentElement.requestFullscreen();
    }
    sendCommand('focus');
  };

  const hold = (id: string, definition: WebKey) => (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    sendCommand('resumeAudio');
    sendCommand('keyDown', { id, definition });
  };
  const release = (id: string) => (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    sendCommand('keyUp', { id });
  };

  const control = (id: string, label: string, glyph: string, definition: WebKey, kind = '') => (
    <button
      className={kind}
      type="button"
      aria-label={label}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={hold(id, definition)}
      onPointerUp={release(id)}
      onPointerCancel={release(id)}
      onLostPointerCapture={release(id)}
    >
      <span aria-hidden="true">{glyph}</span>
      <small>{label}</small>
    </button>
  );

  if (!hydrated) {
    return <main className="launcher-shell" aria-label="Star Control II" />;
  }

  return (
    <main className={running ? 'game-shell' : 'launcher-shell'}>
      {!running && (
        <>
          <Image
            className="game-preview"
            src={`${basePath}/assets/main-menu-zh-tw.png`}
            alt="Traditional Chinese main menu of The Ur-Quan Masters HD"
            fill
            priority
            sizes="100vw"
            unoptimized
          />
          <div className="space-vignette" />
          <section className="launch-card">
            <p className="eyebrow">{text.eyebrow}</p>
            <h1>{text.title}</h1>
            <p className="description">{text.description}</p>
            <button className="launch-button" type="button" onClick={() => setRunning(true)}>
              {text.play}
            </button>
            <p className="touch-hint">{text.touchHint}</p>
            <p className="network-hint">{text.networkHint}</p>
          </section>
        </>
      )}

      {running && (
        <>
          <iframe
            ref={iframeRef}
            className="game-frame"
            src={gameUrl}
            title={text.title}
            allow="autoplay; fullscreen; gamepad; cross-origin-isolated"
          />
          {!ready && (
            <div className="loading-screen" role="status">
              <span />
              <p>{loadingDetail?.label || text.loading}</p>
              {loadingDetail && (
                <progress value={loadingDetail.progress} max={1}>
                  {Math.round(loadingDetail.progress * 100)}%
                </progress>
              )}
            </div>
          )}
        </>
      )}

      <header className="launcher-bar">
        <button className="back-button" type="button" aria-label={text.back} onClick={goBack}>
          <span aria-hidden="true">←</span>
          {text.back}
        </button>
        <div className="header-actions">
          {running && (
            <button
              className="fullscreen-button"
              type="button"
              aria-label={text.fullscreen}
              title={text.fullscreen}
              onClick={toggleFullscreen}
            >
              <span aria-hidden="true">⛶</span>
            </button>
          )}
          <div className="language-switch" role="group" aria-label="Language / 語言">
            <button
              className={language === 'zh-TW' ? 'active' : ''}
              onClick={() => selectLanguage('zh-TW')}
              type="button"
            >
              繁體中文
            </button>
            <button
              className={language === 'en' ? 'active' : ''}
              onClick={() => selectLanguage('en')}
              type="button"
            >
              English
            </button>
          </div>
        </div>
      </header>

      {backNotice && <div className="back-notice" role="status">{text.backAgain}</div>}

      {running && ready && inBattle && mobileControls && (
        <section className="battle-controls" aria-label={text.controls}>
          {battlePlayers.player1 && <fieldset className="player-controls player-one">
            <legend>{text.player1}</legend>
            <div className="steering">
              {control('p1-left', text.left, '◀', keys.p1Left)}
              {control('p1-thrust', text.thrust, '▲', keys.p1Thrust, 'thrust')}
              {control('p1-right', text.right, '▶', keys.p1Right)}
            </div>
            <div className="actions">
              {control('p1-fire', text.fire, '●', keys.p1Fire, 'fire')}
              {control('p1-special', text.special, '✦', keys.p1Special, 'special')}
            </div>
          </fieldset>}

          {battlePlayers.player2 && <fieldset className="player-controls player-two">
            <legend>{text.player2}</legend>
            <div className="steering">
              {control('p2-left', text.left, '◀', keys.p2Left)}
              {control('p2-thrust', text.thrust, '▲', keys.p2Thrust, 'thrust')}
              {control('p2-right', text.right, '▶', keys.p2Right)}
            </div>
            <div className="actions">
              {control('p2-fire', text.fire, '●', keys.p2Fire, 'fire')}
              {control('p2-special', text.special, '✦', keys.p2Special, 'special')}
            </div>
          </fieldset>}
        </section>
      )}
    </main>
  );
}
