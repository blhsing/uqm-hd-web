'use client';

import { PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

type Language = 'en' | 'zh-TW';
type WebKey = { key: string; code: string; keyCode: number; location?: number };
type WebCommand = 'keyDown' | 'keyUp' | 'tapKey' | 'requestBack' | 'pauseCombat' | 'resumeCombat' | 'releaseAll' | 'focus' | 'resumeAudio';
type CommandSender = (command: WebCommand, payload?: Record<string, unknown>) => void;
type JoystickDirection = 'left' | 'right' | 'thrust';

const AZURE_GAME_BASE = 'https://test-officialwebsite.azurewebsites.net/starcontrol2';

const copy = {
  en: {
    title: 'Star Control II',
    loading: 'Loading the complete game…',
    downloading: 'Downloading game content',
    cached: 'Loading cached game content',
    back: 'Back',
    fullscreen: 'Fullscreen',
    controls: 'Battle controls',
    player1: 'Player 1',
    player2: 'Player 2',
    joystick: 'Steering and thrust joystick',
    left: 'Turn left',
    right: 'Turn right',
    thrust: 'Thrust',
    fire: 'Fire',
    special: 'Special',
  },
  'zh-TW': {
    title: '星際控制 II',
    loading: '正在載入完整遊戲…',
    downloading: '正在下載遊戲內容',
    cached: '正在載入已快取的遊戲內容',
    back: '返回',
    fullscreen: '全螢幕',
    controls: '戰鬥操作',
    player1: '玩家一',
    player2: '玩家二',
    joystick: '轉向及推進搖桿',
    left: '左轉',
    right: '右轉',
    thrust: '推進',
    fire: '武器',
    special: '特殊能力',
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

type VirtualJoystickProps = {
  idPrefix: string;
  label: string;
  leftLabel: string;
  rightLabel: string;
  thrustLabel: string;
  leftKey: WebKey;
  rightKey: WebKey;
  thrustKey: WebKey;
  sendCommand: CommandSender;
};

function VirtualJoystick({
  idPrefix,
  label,
  leftLabel,
  rightLabel,
  thrustLabel,
  leftKey,
  rightKey,
  thrustKey,
  sendCommand,
}: VirtualJoystickProps) {
  const pointerRef = useRef<number | null>(null);
  const heldRef = useRef<Set<JoystickDirection>>(new Set());
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [activeDirections, setActiveDirections] = useState('');
  const bindings: Record<JoystickDirection, WebKey> = {
    left: leftKey,
    right: rightKey,
    thrust: thrustKey,
  };

  const releaseHeld = useCallback(() => {
    for (const direction of heldRef.current) {
      sendCommand('keyUp', { id: `${idPrefix}-${direction}` });
    }
    heldRef.current.clear();
  }, [idPrefix, sendCommand]);

  useEffect(() => {
    const resetAfterBlur = () => {
      pointerRef.current = null;
      releaseHeld();
      setPosition({ x: 0, y: 0 });
      setActiveDirections('');
    };
    window.addEventListener('blur', resetAfterBlur);
    return () => {
      window.removeEventListener('blur', resetAfterBlur);
      releaseHeld();
    };
  }, [releaseHeld]);

  const applyDirections = (horizontal: number, vertical: number) => {
    const next = new Set<JoystickDirection>();
    if (horizontal <= -0.28) next.add('left');
    if (horizontal >= 0.28) next.add('right');
    if (vertical <= -0.2) next.add('thrust');

    for (const direction of ['left', 'right', 'thrust'] as const) {
      const wasHeld = heldRef.current.has(direction);
      const shouldHold = next.has(direction);
      if (shouldHold && !wasHeld) {
        sendCommand('keyDown', {
          id: `${idPrefix}-${direction}`,
          definition: bindings[direction],
        });
      } else if (!shouldHold && wasHeld) {
        sendCommand('keyUp', { id: `${idPrefix}-${direction}` });
      }
    }

    heldRef.current = next;
    setActiveDirections([...next].join(' '));
  };

  const updateFromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const rawX = event.clientX - (rect.left + rect.width / 2);
    const rawY = event.clientY - (rect.top + rect.height / 2);
    const maxTravel = rect.width * 0.29;
    const distance = Math.hypot(rawX, rawY);
    const scale = distance > maxTravel ? maxTravel / distance : 1;
    const x = rawX * scale;
    const y = rawY * scale;

    setPosition({ x, y });
    applyDirections(rawX / maxTravel, rawY / maxTravel);
  };

  const finishPointer = () => {
    pointerRef.current = null;
    releaseHeld();
    setPosition({ x: 0, y: 0 });
    setActiveDirections('');
  };

  const beginPointer = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (pointerRef.current !== null) return;
    pointerRef.current = event.pointerId;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Synthetic test events and older WebViews may not expose pointer capture.
    }
    sendCommand('resumeAudio');
    updateFromPointer(event);
  };

  const movePointer = (event: PointerEvent<HTMLDivElement>) => {
    if (pointerRef.current !== event.pointerId) return;
    event.preventDefault();
    updateFromPointer(event);
  };

  const endPointer = (event: PointerEvent<HTMLDivElement>) => {
    if (pointerRef.current !== event.pointerId) return;
    event.preventDefault();
    finishPointer();
  };

  return (
    <div className="joystick-shell">
      <div
        className="virtual-joystick"
        role="group"
        aria-label={label}
        aria-roledescription="joystick"
        data-active={activeDirections}
        onContextMenu={(event) => event.preventDefault()}
        onPointerDown={beginPointer}
        onPointerMove={movePointer}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        onLostPointerCapture={endPointer}
      >
        <span className="joystick-direction joystick-left" aria-hidden="true">◀</span>
        <span className="joystick-direction joystick-thrust" aria-hidden="true">▲</span>
        <span className="joystick-direction joystick-right" aria-hidden="true">▶</span>
        <span
          className="joystick-knob"
          aria-hidden="true"
          style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
        >
          <span>✥</span>
        </span>
      </div>
      <span className="joystick-labels" aria-hidden="true">
        <small>{leftLabel}</small>
        <small>{thrustLabel}</small>
        <small>{rightLabel}</small>
      </span>
    </div>
  );
}

export default function Home() {
  const [language, setLanguage] = useState<Language>('en');
  const [hydrated, setHydrated] = useState(false);
  const [mobileControls, setMobileControls] = useState(false);
  const [running, setRunning] = useState(false);
  const [ready, setReady] = useState(false);
  const [inBattle, setInBattle] = useState(false);
  const [atMainMenu, setAtMainMenu] = useState(true);
  const [battlePlayers, setBattlePlayers] = useState({ player1: true, player2: false });
  const [loadingDetail, setLoadingDetail] = useState<{ label: string; progress: number } | null>(null);
  const [gameBase, setGameBase] = useState('');
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const text = copy[language];

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const deploymentPath = window.location.pathname.startsWith('/starcontrol2')
        ? '/starcontrol2'
        : '';
      const localHost = /^(?:localhost|127(?:\.\d+){3}|\[?::1\]?)$/i.test(window.location.hostname);

      setLanguage(preferredLanguage());
      setMobileControls(isMobileBrowser());
      setGameBase((deploymentPath || localHost) ? deploymentPath : AZURE_GAME_BASE);
      setHydrated(true);
      setRunning(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const sendCommand = useCallback<CommandSender>((command, payload = {}) => {
    try {
      const frame = iframeRef.current;
      if (!frame?.contentWindow) return;
      const targetOrigin = new URL(frame.src, window.location.href).origin;
      frame.contentWindow.postMessage({ type: 'uqm-command', command, ...payload }, targetOrigin);
    } catch {
      // The iframe may be navigating while the selected language is reloaded.
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
        if ('mainMenu' in event.data) setAtMainMenu(Boolean(event.data.mainMenu));
        setBattlePlayers({
          player1: Boolean(event.data.player1),
          player2: Boolean(event.data.player2),
        });
      } else if (event.data?.type === 'uqm-loading') {
        const fileProgress = Number(event.data.progress) || 0;
        const fileIndex = Math.max(1, Number(event.data.file) || 1);
        const fileCount = Math.max(fileIndex, Number(event.data.files) || fileIndex);
        setLoadingDetail({
          label: `${event.data.cached ? text.cached : text.downloading} · ${fileIndex}/${fileCount}`,
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
  }, [running, sendCommand, text.cached, text.downloading, text.loading]);

  useEffect(() => {
    if (!running || !ready || !inBattle) return;

    const pauseForLostFocus = () => {
      sendCommand('releaseAll');
      sendCommand('pauseCombat');
    };
    const resumeForFocus = () => sendCommand('resumeCombat');
    const onVisibilityChange = () => {
      if (document.hidden) pauseForLostFocus();
      else if (document.hasFocus()) resumeForFocus();
    };

    window.addEventListener('blur', pauseForLostFocus);
    window.addEventListener('focus', resumeForFocus);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('blur', pauseForLostFocus);
      window.removeEventListener('focus', resumeForFocus);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [inBattle, ready, running, sendCommand]);

  const selectLanguage = (next: Language) => {
    if (next === language) return;
    sendCommand('releaseAll');
    setRunning(false);
    setLanguage(next);
    setReady(false);
    setInBattle(false);
    setAtMainMenu(true);
    setBattlePlayers({ player1: true, player2: false });
    setLoadingDetail(null);
    window.setTimeout(() => setRunning(true), 0);
  };

  const gameUrl = useMemo(
    () => `${gameBase}/game/uqm-hd.html?lang=${encodeURIComponent(language)}`,
    [gameBase, language],
  );

  const goBack = () => {
    if (!running || !ready || atMainMenu) return;
    sendCommand('requestBack', { definition: keys.escape });
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
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture is unavailable for synthetic events in browser tests.
    }
    sendCommand('resumeAudio');
    sendCommand('keyDown', { id, definition });
  };
  const release = (id: string) => (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    sendCommand('keyUp', { id });
  };

  const control = (id: string, label: string, glyph: string, definition: WebKey, kind: string) => (
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
    return <main className="game-shell" aria-label="Star Control II" />;
  }

  const dualPlayerControls = battlePlayers.player1 && battlePlayers.player2;

  return (
    <main className="game-shell">
      {running && (
        <iframe
          ref={iframeRef}
          className="game-frame"
          src={gameUrl}
          title={text.title}
          allow="autoplay; fullscreen; gamepad; cross-origin-isolated"
        />
      )}

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

      {ready && (
        <header className={`launcher-bar${atMainMenu ? ' no-back' : ''}`}>
          {!atMainMenu && (
            <button className="back-button" type="button" aria-label={text.back} onClick={goBack}>
              <span aria-hidden="true">←</span>
              {text.back}
            </button>
          )}
          {atMainMenu && (
            <div className="header-actions">
            <button
              className="fullscreen-button"
              type="button"
              aria-label={text.fullscreen}
              title={text.fullscreen}
              onClick={toggleFullscreen}
            >
              <span aria-hidden="true">⛶</span>
            </button>
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
          )}
        </header>
      )}

      {running && ready && inBattle && mobileControls && (
        <section
          className={`battle-controls ${dualPlayerControls ? 'dual-player' : 'single-player'}`}
          aria-label={text.controls}
        >
          {battlePlayers.player1 && (
            <fieldset className="player-controls player-one">
              <legend>{text.player1}</legend>
              <VirtualJoystick
                idPrefix="p1"
                label={`${text.player1}: ${text.joystick}`}
                leftLabel={text.left}
                rightLabel={text.right}
                thrustLabel={text.thrust}
                leftKey={keys.p1Left}
                rightKey={keys.p1Right}
                thrustKey={keys.p1Thrust}
                sendCommand={sendCommand}
              />
              <div className="actions">
                {control('p1-special', text.special, '✦', keys.p1Special, 'special')}
                {control('p1-fire', text.fire, '●', keys.p1Fire, 'fire')}
              </div>
            </fieldset>
          )}

          {battlePlayers.player2 && (
            <fieldset className="player-controls player-two">
              <legend>{text.player2}</legend>
              <VirtualJoystick
                idPrefix="p2"
                label={`${text.player2}: ${text.joystick}`}
                leftLabel={text.left}
                rightLabel={text.right}
                thrustLabel={text.thrust}
                leftKey={keys.p2Left}
                rightKey={keys.p2Right}
                thrustKey={keys.p2Thrust}
                sendCommand={sendCommand}
              />
              <div className="actions">
                {control('p2-special', text.special, '✦', keys.p2Special, 'special')}
                {control('p2-fire', text.fire, '●', keys.p2Fire, 'fire')}
              </div>
            </fieldset>
          )}
        </section>
      )}
    </main>
  );
}
