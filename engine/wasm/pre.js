// Emscripten injects --pre-js into both the browser main thread and each
// pthread worker. Browser UI, storage and input bridges belong only to the
// main thread; workers intentionally skip this block because they do not
// expose window or document.
if (typeof window !== "undefined") {
const webParams = new URLSearchParams(window.location.search);
const requestedLanguage = webParams.get("lang");
const webLanguage = requestedLanguage === "en" ? "en" : "zh-TW";
const profileDirectory = "/home/web_user/.uqm/profile";
const parentOrigin = (() => {
    try {
        return document.referrer ? new URL(document.referrer).origin : window.location.origin;
    } catch {
        return window.location.origin;
    }
})();

function postToParent(message) {
    window.parent.postMessage(message, parentOrigin);
}

const gamePathMarker = "/game/";
const gamePathIndex = window.location.pathname.indexOf(gamePathMarker);
const deploymentBase = gamePathIndex >= 0
    ? window.location.pathname.slice(0, gamePathIndex)
    : "";
const websocketProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";

// Emscripten appends the address and port requested by the original TCP
// client to this prefix. The Azure relay pairs two outgoing connections with
// the same suffix, so browsers retain UQM's network Super Melee protocol.
Module.websocket = {
    url: `${websocketProtocol}//${window.location.host}${deploymentBase}/netplay/`,
    subprotocol: "binary",
};

Module.arguments = [
    "--contentdir=/content",
    "--addondir=/content/addons",
    `--configdir=${profileDirectory}`,
    "--res=1440x1080",
    "--resfactor=3",
    "--windowed",
    "--nogl",
    "--keepaspectratio",
    "--scale=bilinear",
];

if (webLanguage === "zh-TW") {
    Module.arguments.push("--addon", "native1080-zh_TW");
}

const pressedWebKeys = new Map();

function dispatchWebKey(type, definition) {
    const target = Module.canvas || document;
    const event = new KeyboardEvent(type, {
        key: definition.key,
        code: definition.code,
        location: definition.location || 0,
        bubbles: true,
        cancelable: true,
        repeat: false,
    });

    // Chromium does not populate these legacy fields from the constructor,
    // while Emscripten's SDL input bridge still reads them.
    Object.defineProperties(event, {
        keyCode: { get: () => definition.keyCode },
        which: { get: () => definition.keyCode },
        charCode: { get: () => 0 },
    });
    target.dispatchEvent(event);
}

window.uqmWeb = {
    language: webLanguage,
    keyDown(id, definition) {
        if (pressedWebKeys.has(id)) {
            return;
        }
        pressedWebKeys.set(id, definition);
        dispatchWebKey("keydown", definition);
    },
    keyUp(id) {
        const definition = pressedWebKeys.get(id);
        if (!definition) {
            return;
        }
        pressedWebKeys.delete(id);
        dispatchWebKey("keyup", definition);
    },
    tapKey(definition) {
        dispatchWebKey("keydown", definition);
        window.setTimeout(() => dispatchWebKey("keyup", definition), 60);
    },
    releaseAll() {
        for (const [id, definition] of pressedWebKeys) {
            pressedWebKeys.delete(id);
            dispatchWebKey("keyup", definition);
        }
    },
    focus() {
        Module.canvas?.focus();
    },
    resumeAudio() {
        const contexts = [
            globalThis.AL?.currentContext?.audioCtx,
            globalThis.SDL?.audioContext,
        ].filter(Boolean);
        for (const context of contexts) {
            if (context.state === "suspended") {
                context.resume().catch(() => {});
            }
        }
    },
    isBattle() {
        return window.uqmWeb.battleState() !== 0;
    },
    battleState() {
        return typeof Module._uqm_web_battle_state === "function"
            ? Module._uqm_web_battle_state()
            : 0;
    },
};

window.addEventListener("blur", () => window.uqmWeb.releaseAll());

const previousRuntimeInitialized = Module.onRuntimeInitialized;
Module.onRuntimeInitialized = () => {
    previousRuntimeInitialized?.();

    // With PROXY_TO_PTHREAD, onRuntimeInitialized runs before the native main
    // thread has replaced Emscripten's default 300x150 canvas. Do not uncover
    // that placeholder or advertise readiness until the HD renderer is live.
    const readyPoll = window.setInterval(() => {
        const canvas = Module.canvas;
        if (!canvas || canvas.width < 1440 || canvas.height < 1080) {
            return;
        }

        window.clearInterval(readyPoll);
        canvas.focus();
        postToParent({ type: "uqm-ready", language: webLanguage });

        let previousBattleState = null;
        window.setInterval(() => {
            const battleState = window.uqmWeb.battleState();
            if (battleState !== previousBattleState) {
                previousBattleState = battleState;
                postToParent({
                    type: "uqm-state",
                    inBattle: Boolean(battleState & 1),
                    player1: Boolean(battleState & 2),
                    player2: Boolean(battleState & 4),
                });
            }
        }, 200);
    }, 50);
};

window.addEventListener("message", event => {
    if (event.source !== window.parent || event.origin !== parentOrigin ||
            event.data?.type !== "uqm-command") {
        return;
    }

    const command = event.data.command;
    if (command === "keyDown") {
        window.uqmWeb.keyDown(String(event.data.id), event.data.definition);
    } else if (command === "keyUp") {
        window.uqmWeb.keyUp(String(event.data.id));
    } else if (command === "tapKey") {
        window.uqmWeb.tapKey(event.data.definition);
    } else if (command === "releaseAll") {
        window.uqmWeb.releaseAll();
    } else if (command === "focus") {
        window.uqmWeb.focus();
    } else if (command === "resumeAudio") {
        window.uqmWeb.resumeAudio();
    }
});

Module.preRun ||= [];

Module.preRun.push(function () {
    let persistRequested = false;

    function requestPersistentStorage() {
        if (navigator.storage && navigator.storage.persist) {
            return navigator.storage.persist().then(isPersisted => {
                if (isPersisted) {
                    console.log("Persistent storage request was accepted.");
                } else {
                    throw "Persistent storage request was rejected.";
                }
            });
        } else {
            return Promise.reject("Persistent storage not supported by browser.");
        }
    }

    // Called from C code: uio_fclose()
    window.wasm_syncfs = () => {
        FS.syncfs( /*populate=*/ false, err => {
            if (err) {
                alert("Saving to IndexedDB failed, saved game & preferences will not be persistent.\n" + err);
            } else {
                console.log("Saved files to browser IndexedDB.");
            }
        });

        if (!persistRequested) {
            requestPersistentStorage().catch(err => {
                alert("Warning: Browser may delete saved games & preferences after inactivity.\n" + err);
            });
            persistRequested = true;
        }
    };

    addRunDependency("syncfs");

    FS.mkdir("/home/web_user/.uqm");
    FS.mount(IDBFS, {}, "/home/web_user/.uqm");
    FS.syncfs( /*populate=*/ true, err => {
        if (err) {
            alert("Populating from IndexedDB failed, saved game & preferences will not be persistent.\n" + err);
        } else {
            removeRunDependency("syncfs");
            console.log("Loaded files from browser IndexedDB.");
        }
    });
});

Module.preRun.push(function () {
    const commonAddons = [
        "hires4x.zip",
        "3domusic.zip",
        "3dovoice.zip",
        "3dovideo.zip",
    ];
    const addonNames = webLanguage === "zh-TW"
        ? [...commonAddons, "native1080-zh_TW.uqm"]
        : commonAddons;
    const dependency = "web-addon-packages";

    function ensureDirectory(path) {
        const parts = path.split("/").filter(Boolean);
        let current = "";
        for (const part of parts) {
            current += `/${part}`;
            try {
                FS.mkdir(current);
            } catch (error) {
                if (!FS.analyzePath(current).exists) {
                    throw error;
                }
            }
        }
    }

    async function loadAddon(name, index) {
        const url = new URL(`content/addons/${name}`, window.location.href);
        postToParent({
            type: "uqm-loading",
            file: index + 1,
            files: addonNames.length,
            name,
            progress: 0,
        });

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Unable to download ${name}: HTTP ${response.status}`);
        }

        const total = Number(response.headers.get("content-length")) || 0;
        let bytes;
        if (response.body && total) {
            const reader = response.body.getReader();
            const data = new Uint8Array(total);
            let offset = 0;
            for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                data.set(value, offset);
                offset += value.length;
                postToParent({
                    type: "uqm-loading",
                    file: index + 1,
                    files: addonNames.length,
                    name,
                    progress: offset / total,
                });
            }
            bytes = offset === data.length ? data : data.slice(0, offset);
        } else {
            bytes = new Uint8Array(await response.arrayBuffer());
        }

        FS.writeFile(`/content/addons/${name}`, bytes, { canOwn: true });
    }

    addRunDependency(dependency);
    ensureDirectory("/content/addons");
    (async () => {
        for (let index = 0; index < addonNames.length; index += 1) {
            await loadAddon(addonNames[index], index);
        }
        removeRunDependency(dependency);
    })().catch(error => {
        console.error(error);
        Module.setStatus?.(`Game content error: ${error.message}`);
        postToParent({
            type: "uqm-error",
            message: error.message,
        });
    });
});
}
