# Sutra Pro, the desktop app

A window around the local server (D116). The server is the Python app of the parent folder; the window finds the one that is running for the data
folder or starts its own, shows its page, and stops its own when the window closes. Plain JavaScript, no bundler, no runtime dependencies: Electron and
the packager are development dependencies at exact versions (`package-lock.json`).

## Run it from a checkout

```bash
cd desktop
npm ci                       # Node 22.12 or newer; the first `npm start` downloads Electron's binary
npm start                    # the window, on this checkout's .venv Python (SUTRA_PRO_PYTHON names another)
npm test                     # the node tests: no Electron needed
```

It uses `~/.sutra-pro` unless `SUTRA_DATA_DIR` names another folder; with `SUTRA_DATA_DIR` set the window's own state (Chromium's cache, the single-instance
lock) lives in `<data>/electron`, so a test run never meets the app you use every day. The app makes that folder first: when it cannot (a missing drive, a file
in the way, a read-only folder) the window opens, says it cannot use the data folder and why, and keeps its log in the system's own user-data folder.
From a checkout the developer tools are in the View menu.

## What is where

| File | What |
|---|---|
| `src/main.js` | the Electron entry: single instance, the window, the menu, the quit that waits for the server to stop |
| `src/server.js` | the supervisor: attach to the server `app.pid` names, or start one; wait for `/api/health`; stop it (D118) |
| `src/runtime.js` | the data folder (and the check that a folder can be made and written), the interpreter, the server's command line and environment, the start timeout |
| `src/urls.js` | which addresses the window may show (its own origin) and which go to the browser (web addresses only) |
| `src/pages.js`, `src/menu.js`, `src/log.js` | the "starting" and "could not start" pages, the application menu, `<data>/logs/desktop.log` |
| `src/selftest.js` | the self-test (D120) |
| `scripts/package.mjs` | `@electron/packager` with the app's identity and icons; only `package.json` and `src/` go into the app archive |
| `entitlements.electron.plist`, `entitlements.python.plist` | what the hardened runtime is told to allow, each line with its reason |
| `test/` | `node --test`: the supervisor against a fake server process, the guard, the pages, the menu, the packager's options |

## How the server's life works (D118)

- **One server per data folder.** The server writes `"<pid> <port>"` to `<data>/app.pid`. When that names a live server that answers `/api/health` and does not say (`/api/config`) that it serves another data folder, the window **attaches** to it
  and leaves it running on quit. (A pid file is only a claim: a crash leaves one behind, and its pid may be reused while its port belongs to a server of another folder.) Otherwise it starts `python -I -B -m sutra_app --no-browser --exit-when-stdin-closes --data-dir <data>`, on the first free port from 8780.
- **It ends with the window.** The window holds the write end of the server's standard input. Closing it is the normal stop (the same on every system), and it is
  also what happens when the window is killed, so a crash leaves nothing running. If the server does not follow: SIGTERM (Windows: the `app.stop` file), then SIGKILL
  (Windows: `taskkill /T /F`).
- **A failed start** shows what the server printed and offers Try Again, Show the Log and Quit. The same happens when the server dies later: one the window started is noticed through its process,
  one it only attached to through its health (four checks, 3 s apart, without an answer).

## Environment

`SUTRA_DATA_DIR`, `SUTRA_EXTRA_PATH`, `SUTRA_PRO_PYTHON`, `SUTRA_PRO_START_TIMEOUT`, `SUTRA_PRO_DEVTOOLS`, `SUTRA_PRO_SELFTEST`, `SUTRA_PRO_SELFTEST_DIR`,
`SUTRA_PRO_EXPECT_VERSION`: see `docs/ENVIRONMENT.md`.

## The self-test

```bash
SUTRA_PRO_SELFTEST=1 SUTRA_OFFLINE=1 SUTRA_DATA_DIR=/tmp/sutra-test SUTRA_PRO_SELFTEST_DIR=/tmp/sutra-out npm start
```

The window opens, starts its server, and the app asks the page whether it finished loading, is the server's own (it carries the boot block the server
injects), drew something, and gets `/api/health` from inside the page. It saves `selftest.png` (a picture of the window) and `selftest.json`, prints one `SELFTEST` line,
and quits through the normal path, which stops the server. The exit status is 0 only when every answer was right. The release workflows run it on the packaged app
(`scripts/prove_desktop_app.py`).

## Package it

From `sutra-pro/`: `scripts/py scripts/build_desktop_app.py --wheel dist/<the wheel> --target mac-arm64 --out build` (see `docs/RELEASE-macos.md` and
`docs/RELEASE-windows.md`). The packager alone, without Python in the app: `node scripts/package.mjs --platform darwin --arch arm64 --out out --version X.Y.Z`.
