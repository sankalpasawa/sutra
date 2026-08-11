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
 *   - Runtime is NEVER read from the checkout. macOS TCC protects ~/Desktop, so
 *     a Finder-launched app cannot read a checkout that lives there.
 *
 * TWO WAYS THIS APP GETS INSTALLED, and both must work (provision.js):
 *   DMG      -- the panel, a relocatable CPython and the Claude Code plugin all
 *               ride inside Contents/Resources/payload, and the app runs
 *               straight out of it. Nothing to stage, nothing to download, no
 *               Python or Node needed on the machine.
 *   install.sh -- the developer path: the checkout is the source of truth and
 *               its runtime is staged into Application Support.
 * The bundle wins when both exist, so an operator with both never silently runs
 * whichever happens to be older.
 */
"use strict";

const { app, BrowserWindow, dialog, shell, ipcMain } = require("electron");
const { spawn, execFileSync } = require("child_process");
const crypto = require("crypto");
const path = require("path");
const fs = require("fs");
const os = require("os");
const http = require("http");
const net = require("net");
const provision = require("./provision.js");

const HOST = "127.0.0.1";
const PORT = 8330; // canonical, pinned -- see header
const ORIGIN = `http://${HOST}:${PORT}`;

// Resolved at boot, not at module load: app.getPath() is only valid once the
// app is ready, and the answer decides which of the two installs we are.
let RUNTIME = null;      // {kind, appDir, python, payload, stamp}

let win = null;
let backend = null;      // the uvicorn child WE spawned, or null if we reused one
let quitting = false;
let pluginReport = null; // what installPlugin() did, for the first-run notice

/* Desktop-control token. Minted here, handed to the backend WE spawn, and
   required by the three update routes that can quit the app and replace the
   bundle on disk. Those routes are otherwise reachable by any page in any
   browser on this machine, which would make "replace /Applications/Sutra.app"
   a thing a web page could ask for.

   The token is only ever known for a backend we started. On the attach path
   (isSutra() found a CLI-owned server) we have no token for it, arming is
   refused with a 403, and automatic updating is simply off for that session --
   which is the correct answer anyway: quitting this window would not stop a
   backend somebody else owns. */
const DESKTOP_TOKEN = crypto.randomBytes(32).toString("hex");
let ownBackend = false;  // did WE spawn it? decides whether the token applies

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

/* The editor's write path is gated by SUTRA_UI_ALLOW_EDIT, which the CLI operator
 * sets when starting the server. A Finder-launched .app inherits launchd's
 * environment, so there was NO WAY to enable editing in the desktop app at all --
 * the gate was unreachable rather than merely off.
 *
 * The marker is read HERE, by the launcher, at start time. That keeps the property
 * the gate exists for: the running server still trusts only its environment, so
 * nothing reachable over the (unauthenticated) HTTP port can flip the gate on a
 * live process. Creating the file takes effect on the NEXT launch, deliberately.
 */
const EDIT_MARKER = path.join(os.homedir(), ".sutra-ui", "allow-edit");

function editEnv() {
  try {
    if (fs.existsSync(EDIT_MARKER)) return { SUTRA_UI_ALLOW_EDIT: "1" };
  } catch (e) { /* unreadable marker = not enabled; never fail the launch over it */ }
  return {};
}

/* The environment a TERMINAL would have given us.
 *
 * A Finder-launched .app inherits launchd's environment, which is almost empty.
 * The same bundle run from a shell works; run from Finder, `claude` HANGS --
 * observed indefinitely, sampled blocked on a startup lock with no network
 * connection ever opened, while the identical binary under a minimal env
 * returns "Not logged in · Please run /login" immediately. Every DMG user
 * launches from Finder, so without this the chat pane never answers for anyone
 * who installed the normal way.
 *
 * So: ask the user's own login shell what the environment should be, once, and
 * hand that to the backend. `-l` makes it read the profile that sets PATH and
 * everything `claude` needs to find its runtime and its credentials.
 *
 * ANTHROPIC_API_KEY IS DELIBERATELY DROPPED. Importing a shell environment
 * wholesale would import that too, and this app refuses to start when it is set
 * -- for a real reason (it routes billing through the per-token API instead of
 * the Max plan). A variable exported in someone's .zshrc must not silently
 * change how the desktop app bills, nor block it from starting. The guard in
 * boot() still applies to a key set for the APP ITSELF.
 *
 * Fails open: a shell that errors, hangs or prints junk costs us nothing but
 * the default environment we already had.
 */
const ENV_MARK = "__SUTRA_ENV__";

/* One shell invocation's environment, or null. Never throws. */
function shellEnvOnce(sh, flags) {
  try {
    // The marker isolates the variables from anything a chatty profile prints.
    const out = execFileSync(sh, [flags, `echo ${ENV_MARK}; command env`], {
      encoding: "utf8",
      timeout: 8000,
      maxBuffer: 4 * 1024 * 1024,
      stdio: ["ignore", "pipe", "ignore"],
    });
    const i = out.lastIndexOf(ENV_MARK);
    if (i < 0) return null;
    const env = {};
    for (const line of out.slice(i + ENV_MARK.length).split("\n")) {
      const eq = line.indexOf("=");
      if (eq <= 0) continue;                 // continuation of a multi-line value
      const k = line.slice(0, eq);
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(k)) continue;
      env[k] = line.slice(eq + 1);
    }
    return Object.keys(env).length ? env : null;
  } catch (e) {
    return null;
  }
}

function loginShellEnv() {
  const sh = process.env.SHELL || "/bin/zsh";

  /* INTERACTIVE FIRST, and it is load-bearing. `zsh -lc` is a LOGIN,
   * NON-INTERACTIVE shell, and zsh reads ~/.zshrc only for INTERACTIVE ones.
   * .zshrc is where nvm, npm-global and Claude Code's own native installer put
   * PATH -- so the login-only harvest returned an environment with no `claude`
   * in it, and the app reported it missing on other people's Macs while it ran
   * fine in every terminal on those same Macs.
   *
   * This machine could not reveal it: Homebrew writes its shellenv to
   * .zprofile, which a login shell DOES read.
   *
   * -lc is still run and merged underneath, never replaced by -lic: an
   * interactive shell can be the odd one out too (an rc guarded on
   * `[[ -o interactive ]]` that returns early, a prompt framework that rewrites
   * PATH, or simply a shell that exits non-zero when interactive without a
   * tty). Whichever succeeds wins; the interactive answer takes precedence
   * where both define a variable. Fails open to {} exactly as before.
   */
  const interactive = shellEnvOnce(sh, "-lic");
  const login = shellEnvOnce(sh, "-lc");
  if (!interactive && !login) {
    console.error("[sutra] could not read the login shell environment");
    return {};
  }
  const env = { ...(login || {}), ...(interactive || {}) };

  /* PATH is UNIONED rather than won outright. Every other variable can sensibly
     take the interactive answer, but PATH is the one we are here for, and each
     shell can hold a directory the other does not -- .zprofile exports one,
     .zshrc the other. Order preserved, interactive first, duplicates dropped. */
  const seen = new Set();
  const merged = [];
  for (const src of [interactive, login]) {
    for (const p of ((src && src.PATH) || "").split(":")) {
      if (p && !seen.has(p)) { seen.add(p); merged.push(p); }
    }
  }
  if (merged.length) env.PATH = merged.join(":");

  // Never inherited: see the note above.
  delete env.ANTHROPIC_API_KEY;
  // Ours win -- these describe THIS process, not the shell's.
  delete env.PWD;
  delete env.OLDPWD;
  delete env.SHLVL;
  delete env._;
  return env;
}

// Resolved once, lazily, because spawning a login shell costs ~100ms and the
// answer cannot change while the app is running.
let _shellEnv = null;
function shellEnv() {
  if (_shellEnv === null) _shellEnv = loginShellEnv();
  return _shellEnv;
}

function startBackend() {
  const child = spawn(
    RUNTIME.python,
    ["-m", "uvicorn", "app:app", "--host", HOST, "--port", String(PORT), "--log-level", "warning"],
    { cwd: RUNTIME.appDir, stdio: ["ignore", "pipe", "pipe"],
      env: {
        // THE SHELL WINS, and the order is the whole point. Spreading
        // process.env last would put launchd's minimal PATH back on top of the
        // login shell's -- which is exactly the variable `claude` needs -- and
        // the fix would silently do nothing. shellEnv() has already had the
        // variables we must control (ANTHROPIC_API_KEY, PWD, ...) removed, so
        // letting the rest win reproduces the terminal launch that is verified
        // to work.
        ...process.env,
        ...shellEnv(),
        // The bundle is read-only once signed. Without this, every import in
        // every launch would try to write a .pyc, fail, and silently recompile
        // from source -- a slow start that looks like a hang.
        ...(RUNTIME.kind === "bundled" ? { PYTHONDONTWRITEBYTECODE: "1" } : {}),
        ...editEnv(),
        // Last, and deliberately after the shell environment: the desktop
        // control token is ours to set and nothing inherited may override it.
        SUTRA_DESKTOP_TOKEN: DESKTOP_TOKEN,
      } }
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
      // Two verbs, no token, no filesystem. See preload.js for why the panel
      // cannot do this over HTTP like everything else.
      preload: path.join(__dirname, "preload.js"),
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
  RUNTIME = provision.resolveRuntime(process.resourcesPath, app.getPath("appData"));
  if (RUNTIME.kind === "none") {
    return fail("Sutra runtime missing", RUNTIME.why);
  }

  // The DMG carries the Claude Code plugin as well as the app. Installing it is
  // deliberately NOT allowed to stop the launch: if ~/.claude is unwritable or
  // managed elsewhere, the panel still opens and the notice says what happened.
  const wasProvisioned = provision.alreadyProvisioned();
  pluginReport = provision.installPlugin({ payload: RUNTIME.payload });
  if (pluginReport.status === "failed") {
    console.error("[sutra] plugin install failed:", pluginReport.error);
  }

  if (await isSutra()) {
    // A Sutra is already serving 8330 (the CLI, or a previous run). Attach to
    // it rather than starting a second server on a pinned port.
    createWindow();
    firstRunNotice(wasProvisioned);
    startUpdateSchedule();   // logs that it is off; see desktopControl()
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
  ownBackend = true;

  // Before the window, not after. If a deferred update has to be finished the
  // right thing to show is nothing at all -- a window that appears and closes
  // half a second later reads as a crash.
  if (await resolvePendingUpdate()) return;

  createWindow();
  firstRunNotice(wasProvisioned);
  startUpdateSchedule();
}

/* What this install put on the machine, said out loud, once.
 *
 * An app that writes into ~/.claude unattended owes the user a plain list of
 * what it wrote and where the backups are. Shown only on the run that actually
 * installed something, and never before the window -- a modal in front of a
 * blank screen reads as an error. */
function firstRunNotice(wasProvisioned) {
  const r = pluginReport;
  if (!r || wasProvisioned) return;
  if (r.status === "skipped" || r.status === "already-current") return;

  const home = os.homedir();
  const short = (p) => (p.startsWith(home) ? "~" + p.slice(home.length) : p);
  let title, message, detail;

  if (r.status === "installed") {
    title = "Sutra plugin installed";
    message = `The Claude Code plugin (core ${r.version}) is now installed for your user.`;
    detail = "Written:\n" + r.wrote.map((p) => "  " + short(p)).join("\n") +
      "\n\nExisting config files were copied to *.sutra-backup first." +
      "\nRun /plugin in Claude Code to see it.";
  } else if (r.status === "newer-present") {
    title = "Sutra plugin left alone";
    message = `A newer plugin (${r.version}) is already installed, so nothing was changed.`;
    detail = r.notes.join("\n");
  } else {
    title = "Sutra plugin not installed";
    message = "The desktop app is running, but the Claude Code plugin could not be installed.";
    detail = (r.error || "unknown error") +
      "\n\nThe panel works without it. To install the plugin yourself, run:" +
      "\n  /plugin marketplace add sankalpasawa/sutra";
  }
  dialog.showMessageBox(win, { type: r.status === "installed" ? "info" : "warning",
                               title, message, detail, buttons: ["OK"] });
}

/* ============================================================ auto-update ===
 *
 * The SCHEDULE lives here and not in the Python backend on purpose. That same
 * backend is what the CLI serves to a plain browser; a background poller there
 * would make every CLI user phone GitHub on launch. Only this process has an
 * app to replace, so only this process decides when to look.
 *
 * Mandatory (founder direction 2026-08-06): the user cannot decline. Cancelling
 * the countdown is a DEFER -- the verified build stays staged and is applied on
 * the way out, so the next launch is updated either way. Nothing is discarded
 * and nothing is asked twice.
 *
 * Two exits from "staged", and they differ only in whether we reopen:
 *   countdown fires -> arm(relaunch=true)  -> quit -> helper swaps -> reopens
 *   user quits      -> arm(relaunch=false) -> exit -> helper swaps -> stays shut
 * Relaunching after a deliberate Quit would countermand the user, so it does
 * not happen.
 */
const UPDATE_FIRST_CHECK_MS = 90 * 1000;        // let the app finish starting
const UPDATE_INTERVAL_MS = 6 * 60 * 60 * 1000;  // then every six hours
let updateTimers = [];
let armed = false;       // an installer is already waiting; do not spawn another

function desktopControl() { return ownBackend; }

/* JSON over loopback, with the control token attached. Bounded: this is called
   on the quit path, and a hung request there would look like a frozen app. */
function api(method, urlPath, body, timeoutMs) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? null : Buffer.from(JSON.stringify(body));
    const req = http.request(
      { host: HOST, port: PORT, path: urlPath, method,
        timeout: timeoutMs || 20000,
        headers: Object.assign(
          { "x-sutra-desktop-token": DESKTOP_TOKEN },
          payload ? { "content-type": "application/json",
                      "content-length": payload.length } : {}) },
      (res) => {
        let text = "";
        res.setEncoding("utf8");
        res.on("data", (c) => { if (text.length < 262144) text += c; });
        res.on("end", () => {
          let parsed = null;
          try { parsed = JSON.parse(text); } catch {}
          if (res.statusCode >= 200 && res.statusCode < 300) return resolve(parsed || {});
          reject(new Error((parsed && parsed.detail) || `HTTP ${res.statusCode}`));
        });
      });
    req.on("timeout", () => { req.destroy(new Error("timed out")); });
    req.on("error", reject);
    if (payload) req.write(payload);
    req.end();
  });
}

/* Check, and stage in the background if there is something to stage. Failures
   are logged and dropped: a machine that is offline, or behind a proxy, or
   rate-limited by GitHub, must keep working exactly as before. */
async function checkForUpdate() {
  if (!desktopControl() || armed) return;
  try {
    const state = await api("GET", "/api/updates", undefined, 30000);
    const d = (state && state.desktop) || {};
    if (!d.managed || d.error || !d.update_available) return;
    console.log(`[sutra] update ${d.installed} -> ${d.latest}; staging`);
    const staged = await api("POST", "/api/updates/desktop/stage", {}, 600000);
    if (staged && staged.staged) console.log(`[sutra] staged ${staged.version}`);
  } catch (err) {
    console.error("[sutra] update check failed:", err.message);
  }
}

function startUpdateSchedule() {
  if (!desktopControl()) {
    console.log("[sutra] attached to a backend we did not start; auto-update off");
    return;
  }
  updateTimers.push(setTimeout(checkForUpdate, UPDATE_FIRST_CHECK_MS));
  updateTimers.push(setInterval(checkForUpdate, UPDATE_INTERVAL_MS));
}

/* Hand the helper this process -- its pid, so it waits for THE SHELL rather
   than for whatever the backend's parent happens to be. */
async function armUpdate(relaunch) {
  const r = await api("POST", "/api/updates/desktop/arm",
                      { wait_pid: process.pid, relaunch: !!relaunch }, 60000);
  armed = true;
  return r;
}

/* Launch-time reconciliation, before the window is shown.
 *
 * `installed` is read from THIS bundle, not from the backend: on the attach
 * path the backend can be an older install still serving 8330, and treating its
 * answer as our version would throw away an update that actually landed. */
async function resolvePendingUpdate() {
  if (!desktopControl()) return false;
  let r;
  try {
    r = await api("POST", "/api/updates/desktop/resolve",
                  { installed: app.getVersion() }, 20000);
  } catch (err) {
    console.error("[sutra] could not resolve pending update:", err.message);
    return false;
  }
  if (r.applied) { console.log(`[sutra] update to ${r.applied} applied`); return false; }
  if (r.gave_up) {
    console.error(`[sutra] gave up on ${r.version}: ${r.error}`);
    return false;
  }
  // "wait" means a helper from the previous run may still be counting down on
  // a pid that is already gone. Arming a second one here is how a launch loop
  // starts, so this launch does nothing and the next one re-decides.
  if (r.action !== "arm") return false;

  // The quit-time apply never ran (force reboot, SIGKILL, power loss). Finish
  // it now: this is the one path that costs the user a visible restart, and it
  // is the price of the promise that the next start is updated.
  console.log(`[sutra] finishing deferred update ${r.version}`);
  try {
    await armUpdate(true);
    quitting = true;
    app.quit();
    return true;
  } catch (err) {
    console.error("[sutra] could not arm deferred update:", err.message);
    return false;
  }
}

ipcMain.handle("sutra:update-apply", async () => {
  if (!desktopControl()) return { ok: false, error: "this window does not control the backend" };
  try {
    await armUpdate(true);
    quitting = true;
    // Give the reply time to reach the renderer before the window goes.
    setTimeout(() => app.quit(), 250);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("sutra:update-defer", async () => ({ ok: true, deferred: true }));

/* Native folder chooser for the panel's working-directory fields. The panel is
   the same app the CLI serves to an ordinary browser, where this cannot exist --
   so it is offered over the preload bridge and the renderer only draws the Browse
   button when that bridge is present. Resolves the chosen absolute path, or null
   when the user cancels; the text input stays the fallback either way. */
ipcMain.handle("sutra:pick-directory", async (_e, defaultPath) => {
  let dp = typeof defaultPath === "string" ? defaultPath.trim() : "";
  if (dp === "~" || dp.startsWith("~/")) dp = path.join(app.getPath("home"), dp.slice(1));
  const opts = { title: "Choose working directory", properties: ["openDirectory", "createDirectory"] };
  if (dp) opts.defaultPath = dp;                 // open where they already are, not at random
  try {
    const r = await dialog.showOpenDialog(win, opts);
    return (r.canceled || !r.filePaths || !r.filePaths.length) ? null : r.filePaths[0];
  } catch (e) {
    return null;                                 // a dialog failure must not reject the renderer
  }
});

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

/* Apply a deferred update on the way out, then kill the child we started.
 *
 * This is the PRIMARY apply path and the reason a cancelled countdown costs the
 * user nothing: the bytes are already downloaded and verified, so the swap
 * happens in the seconds after the app closes and the next launch is simply the
 * new version. No restart, no flash, no second prompt.
 *
 * It has to run BEFORE the backend is killed -- arming is an HTTP call to it --
 * which is why the quit is deferred once and re-issued. Bounded hard: a quit
 * that hangs on a network call is a frozen app, and no update is worth that.
 *
 * A backend we merely attached to is left alone; it belongs to whoever started
 * it, and desktopControl() is false there so nothing above applies either. */
let quitArmAttempted = false;

async function applyOnQuit() {
  try {
    const s = await api("GET", "/api/updates/staged", undefined, 3000);
    if (!s || !s.pending || s.state !== "staged") return;
    console.log(`[sutra] applying deferred update ${s.version} on quit`);
    await armUpdate(false);          // do NOT reopen: the user chose to quit
  } catch (err) {
    // Nothing is lost. The manifest survives, and the next launch finishes it.
    console.error("[sutra] deferred apply skipped:", err.message);
  }
}

app.on("before-quit", (e) => {
  if (!quitArmAttempted && desktopControl() && !armed) {
    quitArmAttempted = true;
    e.preventDefault();
    applyOnQuit().then(() => app.quit(), () => app.quit());
    return;
  }
  quitting = true;
  updateTimers.forEach((t) => { clearTimeout(t); clearInterval(t); });
  updateTimers = [];
  if (backend && backend.exitCode === null) {
    try { backend.kill("SIGTERM"); } catch {}
    setTimeout(() => { try { backend.kill("SIGKILL"); } catch {} }, 2000);
  }
});
