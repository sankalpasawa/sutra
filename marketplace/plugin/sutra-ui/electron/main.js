/* Sutra desktop shell.
 *
 * This process owns the WINDOW. It does not reimplement the panel: the panel is
 * the same FastAPI app the CLI serves, spawned here as a child and loaded over
 * loopback. Keeping one server implementation means the CLI and the desktop app
 * cannot drift apart.
 *
 * Every invariant the shell-script launcher earned is preserved here, because
 * they were each written for a failure that actually happened:
 *
 *   - 127.0.0.1 ONLY. A browser terminal is machine access.
 *   - REFUSE to start when ANTHROPIC_API_KEY is set: that routes through the
 *     per-token API instead of the Max plan.
 *   - PINNED to port 8330. The app is a fixed-port product; it is not moved by
 *     an environment variable.
 *   - NEVER adopt a server we did not start. A port answering 200 is not proof
 *     of identity -- every FastAPI project in the world is `uvicorn app:app`.
 *     We require /api/org/health to return a lint_scope key, which is Sutra's
 *     own route. The script launcher shipped without this and was observed
 *     printing a full success banner while its own uvicorn had already died on
 *     "address already in use".
 *   - Runtime is read from ~/Library/Application Support/Sutra, never from the
 *     checkout. macOS TCC protects ~/Desktop, so a Finder-launched app cannot
 *     read a checkout that lives there.
 */
"use strict";

const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");
const net = require("net");

const HOST = "127.0.0.1";
const PORT = 8330; // canonical, pinned -- see header
const ORIGIN = `http://${HOST}:${PORT}`;

// app.getPath("appData") is ~/Library/Application Support on macOS. install.sh
// stages the runtime there precisely so this path is never TCC-protected.
const STAGE = path.join(app.getPath("appData"), "Sutra");
const APP_DIR = path.join(STAGE, "plugin", "sutra-ui");
const PY = path.join(STAGE, "venv", "bin", "python");

let win = null;
let backend = null;      // the uvicorn child WE spawned, or null if we reused one
let quitting = false;

function fail(title, message) {
  dialog.showErrorBox(title, message);
  app.exit(2);
}

/* Identity, not liveness. Resolves true only for a server that serves Sutra's
   own /api/org/health with the lint_scope key. */
function isSutra() {
  return new Promise((resolve) => {
    const req = http.get(
      { host: HOST, port: PORT, path: "/api/org/health", timeout: 2000 },
      (res) => {
        if (res.statusCode !== 200) { res.resume(); return resolve(false); }
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (c) => { if (body.length < 65536) body += c; });
        res.on("end", () => {
          try {
            const j = JSON.parse(body);
            resolve(!!j && typeof j === "object" && "lint_scope" in j);
          } catch { resolve(false); }
        });
      }
    );
    req.on("timeout", () => { req.destroy(); resolve(false); });
    req.on("error", () => resolve(false));
  });
}

/* True when something is listening, whatever it is. */
function portBusy() {
  return new Promise((resolve) => {
    const s = net.connect({ host: HOST, port: PORT });
    const done = (v) => { s.destroy(); resolve(v); };
    s.setTimeout(1500);
    s.on("connect", () => done(true));
    s.on("timeout", () => done(false));
    s.on("error", () => done(false));
  });
}

function startBackend() {
  const child = spawn(
    PY,
    ["-m", "uvicorn", "app:app", "--host", HOST, "--port", String(PORT), "--log-level", "warning"],
    { cwd: APP_DIR, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env } }
  );
  let stderr = "";
  child.stderr.on("data", (d) => {
    stderr += d.toString();
    if (stderr.length > 65536) stderr = stderr.slice(-65536);
  });
  child.on("exit", (code) => {
    if (quitting) return;
    // The server dying while the window is open is not recoverable by waiting.
    fail("Sutra server stopped",
      `The Sutra backend exited (code ${code}).\n\n${stderr.slice(-1200) || "(no output)"}`);
  });
  child.__stderr = () => stderr;
  return child;
}

/* Poll for OUR child. Every tick re-checks that the child is still alive, so a
   child that dies on a bind race fails immediately instead of us adopting
   whatever else answers on the port. */
async function waitForOwnBackend(child, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) return false;
    if (await isSutra()) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 900,
    minHeight: 600,
    title: "Sutra",
    backgroundColor: "#0f0e0c",
    show: false,
    webPreferences: {
      // The renderer loads a local web app; it never needs Node. Keeping these
      // off means a compromised page cannot reach the filesystem.
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  win.once("ready-to-show", () => win.show());
  win.on("closed", () => { win = null; });

  // Anything that is not our own origin opens in the real browser, never inside
  // the app shell.
  // Hand the OS only http(s). The panel renders repo contents and agent
  // output, so a link in it is not trusted input -- file://, smb:// or a
  // registered custom-protocol URL passed to openExternal would let that
  // content mount shares or launch handlers.
  const openExternalSafe = (url) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
  };
  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternalSafe(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(ORIGIN)) { e.preventDefault(); openExternalSafe(url); }
  });

  win.loadURL(ORIGIN);
}

async function boot() {
  if (process.env.ANTHROPIC_API_KEY) {
    return fail("Sutra refuses to start",
      "ANTHROPIC_API_KEY is set. That routes through the API (per-token billing) " +
      "instead of your Max plan.\n\nUnset it, then make sure `claude` is logged in.");
  }
  if (!fs.existsSync(PY) || !fs.existsSync(path.join(APP_DIR, "app.py"))) {
    return fail("Sutra runtime missing",
      `Expected the staged runtime at:\n  ${APP_DIR}\n  ${PY}\n\n` +
      "Run install.sh from your Sutra checkout to stage it.");
  }

  if (await isSutra()) {
    // A Sutra is already serving 8330 (the CLI, or a previous run). Attach to
    // it rather than starting a second server on a pinned port.
    createWindow();
    return;
  }
  if (await portBusy()) {
    return fail("Port 8330 is in use",
      "Something is already listening on 127.0.0.1:8330 and it is not Sutra " +
      "(it did not answer /api/org/health).\n\nQuit that process and open Sutra again.\n\n" +
      "Find it with:  lsof -ti tcp:8330");
  }

  backend = startBackend();
  const up = await waitForOwnBackend(backend);
  if (!up) {
    const err = backend.__stderr ? backend.__stderr() : "";
    try { backend.kill("SIGTERM"); } catch {}
    return fail("Sutra server did not start",
      `The backend did not answer on ${ORIGIN} within 45s.\n\n${err.slice(-1200) || "(no output)"}`);
  }
  createWindow();
}

// One Sutra window per machine. Electron enforces this properly; the shell
// launcher could not, and four launchers were observed running at once.
if (!app.requestSingleInstanceLock()) {
  app.exit(0);
} else {
  app.on("second-instance", () => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });
  app.whenReady().then(boot);
}

app.on("window-all-closed", () => app.quit());

// Kill the child we started. A backend we merely attached to is left alone --
// it belongs to whoever started it.
app.on("before-quit", () => {
  quitting = true;
  if (backend && backend.exitCode === null) {
    try { backend.kill("SIGTERM"); } catch {}
    setTimeout(() => { try { backend.kill("SIGKILL"); } catch {} }, 2000);
  }
});
