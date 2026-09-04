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


/* ------------------------------------------------------------ browser fetch --
 * The agent's crawler reads the user's own website. More and more sites sit behind
 * a JavaScript bot challenge (Vercel "Attack Challenge Mode", Cloudflare "Under
 * Attack"): every plain request, robots.txt and the sitemap included, answers 429
 * with a page only a browser running JavaScript can get past, and the pass is bound
 * to the browser's network fingerprint, so cookies do not carry over. Measured on a
 * real customer site on 2026-09-03: 429 on the very first request, from any client.
 *
 * This app IS a browser. So the shell runs a tiny loopback service: POST /fetch
 * {url} -> a hidden window for that origin clears the challenge once, then an
 * in-page fetch() returns the raw body (HTML, XML, text) in a fraction of a second.
 * The backend gets the address and a token in its environment and uses it only
 * when a site has refused plain requests. Loopback only, token on every call,
 * http(s) only, one request in flight at a time, windows retired after ten idle
 * minutes. Nothing here can be reached from a web page: the token never leaves
 * the two processes.
 */
const BROWSER_TOKEN = crypto.randomBytes(24).toString("hex");
const BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";
const BROWSER_IDLE_MS = 10 * 60 * 1000;
const BROWSER_MAX_WINDOWS = 3;
const IN_PAGE_FETCH = `(async (u) => {
  const r = await fetch(u, {credentials: 'include', redirect: 'follow'});
  const t = await r.text();
  const h = {}; r.headers.forEach((v, k) => { h[k] = v; });
  return {status: r.status, url: r.url, text: t, content_type: r.headers.get('content-type') || '', headers: h};
})`;
let browserFetchUrl = "";
const browserWindows = new Map();      // origin -> {win, ready, lastUsed}
let browserQueue = Promise.resolve();

function browserChallenged(r) {
  if (!r || ![403, 429, 503].includes(r.status)) return false;
  const h = r.headers || {};
  if (/challenge/i.test(h["x-vercel-mitigated"] || "") || /challenge/i.test(h["cf-mitigated"] || "")) return true;
  const body = (r.text || "").slice(0, 6000);
  return /cf-chl|_cf_chl_opt|challenge-platform|vercel-challenge|Just a moment|Verifying you are human|Checking your browser/i.test(body);
}

function browserWindowFor(origin) {
  const have = browserWindows.get(origin);
  if (have && !have.win.isDestroyed()) { have.lastUsed = Date.now(); return have; }
  if (browserWindows.size >= BROWSER_MAX_WINDOWS) {
    const oldest = [...browserWindows.entries()].sort((a, b) => a[1].lastUsed - b[1].lastUsed)[0];
    if (oldest) { try { oldest[1].win.destroy(); } catch {} browserWindows.delete(oldest[0]); }
  }
  const win = new BrowserWindow({
    show: false, width: 1280, height: 800,
    webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false,
                      images: false, backgroundThrottling: false, partition: "persist:agent-fetch" },
  });
  win.webContents.setUserAgent(BROWSER_UA);
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  const ready = new Promise((resolve) => {
    const done = () => resolve();
    win.webContents.once("did-finish-load", done);
    win.webContents.once("did-fail-load", done);
    setTimeout(done, 45000);
  });
  win.loadURL(origin + "/").catch(() => {});
  const entry = { win, ready, lastUsed: Date.now() };
  browserWindows.set(origin, entry);
  return entry;
}

async function browserFetch(url, timeoutMs) {
  const u = new URL(url);
  if (!/^https?:$/.test(u.protocol)) throw new Error("only http(s) urls");
  const origin = u.origin;
  const entry = browserWindowFor(origin);
  await entry.ready;
  const deadline = Date.now() + timeoutMs;
  let last = null;
  for (let i = 0; i < 10 && Date.now() < deadline; i++) {
    try {
      last = await entry.win.webContents.executeJavaScript(`${IN_PAGE_FETCH}(${JSON.stringify(url)})`, true);
    } catch (e) {
      last = { status: 0, url, text: "", content_type: "", headers: {}, error: String(e && e.message || e).slice(0, 160) };
    }
    if (last && !browserChallenged(last) && last.status) return last;
    await new Promise((r) => setTimeout(r, 1500));
  }
  return last || { status: 0, url, text: "", content_type: "", headers: {} };
}

function startBrowserFetchService() {
  const server = http.createServer((req, res) => {
    const reply = (code, obj) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };
    if (req.method !== "POST" || req.url !== "/fetch") return reply(404, { error: "not found" });
    if (req.headers["x-sutra-browser"] !== BROWSER_TOKEN) return reply(403, { error: "bad token" });
    let body = "";
    req.on("data", (d) => { body += d; if (body.length > 65536) req.destroy(); });
    req.on("end", () => {
      let want;
      try { want = JSON.parse(body || "{}"); } catch { return reply(400, { error: "bad json" }); }
      const url = String(want.url || "");
      const timeoutMs = Math.min(120, Math.max(5, Number(want.timeout) || 60)) * 1000;
      browserQueue = browserQueue.then(() => browserFetch(url, timeoutMs))
        .then((r) => reply(200, r), (e) => reply(502, { error: String(e && e.message || e).slice(0, 200) }));
    });
  });
  server.on("error", (e) => console.error("[sutra] browser fetch service:", e && e.message));
  server.listen(0, HOST, () => {
    browserFetchUrl = `http://${HOST}:${server.address().port}`;
    console.log("[sutra] browser fetch service on", browserFetchUrl);
  });
  setInterval(() => {
    const cut = Date.now() - BROWSER_IDLE_MS;
    for (const [origin, e] of browserWindows) {
      if (e.lastUsed < cut) { try { e.win.destroy(); } catch {} browserWindows.delete(origin); }
    }
  }, 60000).unref();
  return server;
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
        // Where the bundled payload lives. (r5: the Files sidecar that read
        // payload/sb/ is retired; the env stays for any bundled resource a
        // backend module resolves — e.g. the update sidecar's assets.)
        SUTRA_UI_RESOURCES: path.join(process.resourcesPath || "", "payload"),
        // The agent's crawler can read a site behind a bot challenge through this
        // app's own hidden window. Address + token, both minted per launch.
        ...(browserFetchUrl ? { SEO_AGENT_BROWSER_FETCH: browserFetchUrl, SEO_AGENT_BROWSER_TOKEN: BROWSER_TOKEN } : {}),
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

/* ------------------------------------------------------------- installed? --
 * The one install mistake that costs a user everything and tells them nothing.
 *
 * You open the DMG and double-click Sutra right there in the installer window.
 * It opens. It works. Nothing anywhere says you never installed it -- and a
 * disk image is read-only, so the app can never replace itself. Every update
 * from then on fails, or worse, never even announces itself. A real user ran
 * 2.238.0 off the image for weeks and only found out when an update refused
 * with "/Volumes/Sutra 2.238.0 is not writable by this user".
 *
 * macOS cannot fix this from the other end: opening a disk image is not allowed
 * to run code, so a DMG can never install itself. The app has to move ITSELF,
 * which is what every well-behaved Mac app does and what this function is.
 *
 * Deliberately a question, not a silent move. A window that vanishes and comes
 * back somewhere else reads as a crash. One question, answered once.
 *
 * Returns true to carry on booting here, false when this process is done
 * (the app has been moved and relaunched from Applications).
 */
function skipMoveMarker() {
  return path.join(app.getPath("userData"), "skip-move-to-applications");
}

function appBundleDir() {
  /* <...>/Sutra.app/Contents/MacOS/Sutra -> <...>/Sutra.app */
  return path.resolve(app.getPath("exe"), "..", "..", "..");
}

/* The fallback when Electron's own mover declines: copy, open the copy, quit.
   ditto rather than cp because it preserves the signature and the symlinks
   inside a .app; a plain recursive copy produces a bundle that will not
   launch on a machine with Gatekeeper awake. */
function copyIntoApplications() {
  const src = appBundleDir();
  const dst = path.join("/Applications", path.basename(src));
  execFileSync("/usr/bin/ditto", [src, dst]);
  spawn("/usr/bin/open", ["-n", "-a", dst], { detached: true, stdio: "ignore" }).unref();
  return dst;
}

async function ensureInstalled() {
  if (process.platform !== "darwin" || !app.isPackaged) return true;
  try { if (fs.existsSync(skipMoveMarker())) return true; } catch {}
  try { if (app.isInApplicationsFolder()) return true; } catch { return true; }

  const onImage = appBundleDir().startsWith("/Volumes/");
  /* The async form, not showMessageBoxSync: only this one reports the
     checkbox, and "do not ask again" has to actually mean it. */
  const r = await dialog.showMessageBox({
    type: "question",
    buttons: ["Move to Applications", "Not now"],
    defaultId: 0,
    cancelId: 1,
    title: "Move Sutra to Applications?",
    message: onImage
      ? "Sutra is running from the installer disk image."
      : "Sutra is not in your Applications folder.",
    detail: (onImage
      ? "A disk image is read-only, so Sutra cannot update itself from here. "
      : "Sutra updates itself by replacing its own copy, which only works from Applications. ") +
      "Move it now and Sutra will reopen from Applications. You will not be asked again.",
    checkboxLabel: "Do not ask again",
    checkboxChecked: false,
    noLink: true,
  });

  if (r.response !== 0) {
    /* Asked again next launch, because the problem is still there next launch.
       Silencing it is the user's call to make, not ours to default to. */
    if (r.checkboxChecked) {
      try { fs.writeFileSync(skipMoveMarker(), new Date().toISOString() + "\n"); }
      catch (e) { console.error("[sutra] could not write skip marker:", e && e.message); }
    }
    return true;
  }

  try {
    const moved = app.moveToApplicationsFolder({
      conflictHandler: (conflict) => {
        if (conflict === "existsAndRunning") {
          dialog.showErrorBox(
            "Sutra is already open",
            "There is already a copy of Sutra in Applications and it is running.\n\n" +
            "Quit that one, then try again.");
          return false;
        }
        return true;    /* replace an older, idle copy */
      },
    });
    if (moved) return false;               /* it relaunched from Applications */
  } catch (e) {
    console.error("[sutra] moveToApplicationsFolder:", e && e.message);
  }

  /* Electron declined (it refuses some read-only sources). Copy by hand. */
  try {
    const dst = copyIntoApplications();
    console.log("[sutra] installed to", dst);
    app.exit(0);
    return false;
  } catch (e) {
    dialog.showErrorBox(
      "Could not move Sutra",
      "Sutra could not copy itself into Applications:\n\n" + (e && e.message) +
      "\n\nDrag Sutra.app to Applications in Finder, then open it from there.");
    return true;                            /* carry on; it still works today */
  }
}

async function boot() {
  /* Before anything else: a copy running off the installer image can never
     update itself, and everything below assumes it can. */
  if (!(await ensureInstalled())) return;
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
  // A staged runtime is made once and never updated, so a venv from before a dependency was
  // added stays broken forever and the failure surfaces deep inside a run ("No module named
  // 'bs4'" on every page). Check at launch, repair silently if we can, and say it plainly if
  // we cannot. A bundled payload ships complete, so this only ever does work on a staged one.
  let missing = provision.missingDeps(RUNTIME.python);
  if (missing.length) {
    console.error("[sutra] missing python deps:", missing.map(m => m[0]).join(", "));
    const fixed = provision.repairDeps(RUNTIME);
    if (fixed.ok) {
      console.error("[sutra] repaired the runtime from requirements.txt");
      missing = [];
    } else {
      console.error("[sutra] could not repair:", fixed.why);
    }
  }
  if (missing.length) {
    return fail("Sutra is missing something it needs", provision.depsMessage(missing));
  }

  const wasProvisioned = provision.alreadyProvisioned();
  pluginReport = provision.installPlugin({ payload: RUNTIME.payload });
  if (pluginReport.status === "failed") {
    console.error("[sutra] plugin install failed:", pluginReport.error);
  }

  if (await isSutra()) {
    // A Sutra is already serving 8330 (the CLI, or a previous run). Attach to
    // it rather than starting a second server on a pinned port. Updating no
    // longer stops here: a deferred update from the last run is finished via
    // the bundled sidecar BEFORE the window, exactly like the own path below.
    if (await resolvePendingUpdate()) return;
    createWindow();
    firstRunNotice(wasProvisioned);
    startUpdateSchedule();   // sidecar-backed in attach mode; see updateCapable()
    return;
  }
  if (await portBusy()) {
    return fail("Port 8330 is in use",
      "Something is already listening on 127.0.0.1:8330 and it is not Sutra " +
      "(it did not answer /api/org/health).\n\nQuit that process and open Sutra again.\n\n" +
      "Find it with:  lsof -ti tcp:8330");
  }

  startBrowserFetchService();
  await new Promise((r) => setTimeout(r, 150));   // listen(0) binds on the next tick; the port must be known before spawn
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

/* ── the attach-mode update-sidecar ──────────────────────────────────────────
 * One seam for every update operation. When this shell OWNS the backend the
 * verbs ride HTTP with the control token, exactly as before. When it is
 * ATTACHED to a backend it did not start, the same machinery runs as a spawned
 * child of the BUNDLE's own python (updates_cli.py beside updates.py) -- no
 * HTTP and no token: the token exists because any browser page can POST to
 * localhost, and a child process is not reachable from a page. Dev shells
 * (RUNTIME.kind !== "bundled") have no updater and answer capable:false --
 * which the panel renders as its honesty message, never as a fake row.
 */
function updateCapable() { return ownBackend || !!(RUNTIME && RUNTIME.kind === "bundled"); }

let lastUpdateCheck = null;   // the desktop section of the last check, for update-state

function updateCli(args, timeoutMs) {
  return new Promise((resolve, reject) => {
    execFile(RUNTIME.python, ["-m", "updates_cli", ...args], {
      // cwd puts updates_cli.py + updates.py on sys.path (asserted CLI-side);
      // env is INHERITED and overlaid, never replaced -- HOME/TMPDIR/locale
      // matter, and shellEnv() brings the proxy vars a Finder launch lacks.
      cwd: RUNTIME.appDir,
      env: { ...process.env, ...shellEnv(), PYTHONDONTWRITEBYTECODE: "1" },
      timeout: timeoutMs || 30000,
      maxBuffer: 4 * 1024 * 1024,
    }, (err, stdout) => {
      let parsed = null;
      try { parsed = JSON.parse(String(stdout || "").trim()); } catch (e) { /* judged below */ }
      if (parsed && parsed.error) return reject(new Error(parsed.error));
      if (err) return reject(new Error(err.killed ? "the updater timed out" : (err.message || "updater failed")));
      if (!parsed) return reject(new Error("the updater returned no answer"));
      resolve(parsed);
    });
  });
}

async function updateOp(verb, body, timeoutMs) {
  if (ownBackend) {
    switch (verb) {
      case "check":   return api("GET", "/api/updates", undefined, timeoutMs || 30000);
      case "staged":  return api("GET", "/api/updates/staged", undefined, timeoutMs || 3000);
      case "stage":   return api("POST", "/api/updates/desktop/stage", {}, timeoutMs || 600000);
      case "arm":     return api("POST", "/api/updates/desktop/arm",
                                 { wait_pid: body.wait_pid, relaunch: !!body.relaunch }, timeoutMs || 60000);
      case "resolve": return api("POST", "/api/updates/desktop/resolve",
                                 { installed: body && body.installed }, timeoutMs || 20000);
    }
  }
  if (!updateCapable()) throw new Error("no update capability in this shell (not a bundled app)");
  switch (verb) {
    case "check":   return updateCli(["check"], timeoutMs || 30000);
    case "staged":  return updateCli(["staged"], timeoutMs || 5000);
    case "stage":   return updateCli(["stage"], timeoutMs || 600000);
    case "arm": {
      const a = ["arm", "--wait-pid", String(body.wait_pid)];
      if (body.relaunch) a.push("--relaunch");
      return updateCli(a, timeoutMs || 60000);
    }
    case "resolve": {
      const a = ["resolve"];
      if (body && body.installed) a.push("--installed", String(body.installed));
      return updateCli(a, timeoutMs || 20000);
    }
  }
  throw new Error("unknown update verb " + verb);
}

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
/* One staging run at a time. The six-hourly timer and the panel's manual check
   both land here, and two concurrent 160MB downloads writing the same staging
   path is not a race worth having. Shared with the IPC verb below so a click
   during a scheduled run joins that run instead of starting a second. */
let staging = null;

function stageNow() {
  if (staging) return staging;                     /* already downloading */
  staging = (async () => {
    const state = await updateOp("check", null, 30000);
    const d = (state && state.desktop) || {};
    lastUpdateCheck = d;
    if (!d.managed || d.error || !d.update_available)
      return { staged: false, reason: d.error || (d.managed ? "up to date" : "not managed here") };
    console.log(`[sutra] update ${d.installed} -> ${d.latest}; staging`);
    const staged = await updateOp("stage", null, 600000);
    if (staged && staged.staged) {
      console.log(`[sutra] staged ${staged.version}`);
      // Attach mode has no backend the panel could poll for this; the shell
      // says it happened. Own mode sends it too -- one code path, no lies.
      try {
        if (win && !win.isDestroyed())
          win.webContents.send("sutra:update-staged", { staged: true, version: staged.version });
      } catch (e) { /* a closed window is not a failed stage */ }
    }
    return staged || { staged: false };
  })();
  staging.finally(() => { staging = null; });
  return staging;
}

async function checkForUpdate() {
  if (!updateCapable() || armed) return;
  try {
    await stageNow();
  } catch (err) {
    console.error("[sutra] update check failed:", err.message);
  }
}

/* Track what each connector depends on upstream. Both ride the SAME tick as the
   desktop update rather than adding timers of their own, because all three are
   the same question asked of different upstreams -- "is there a newer version of
   a thing we shipped a copy of?" -- and three schedules would be three things to
   reason about when one of them misfires.

     hosted   ComposioHQ/composio's toolkit catalog
     local    the pinned 1MCP aggregator version, from npm

   NOT force:true, either of them. Each backend's TTL decides whether the call
   costs a request at all, so a shell that restarts often does not hammer GitHub
   or npm, and the backend stays the single place a polling interval is defined.
   Failures are logged and dropped: the catalog and the pin we already have keep
   working, offline included. */
async function checkConnectorUpstreams() {
  if (!desktopControl()) return;
  try {
    const r = await api("POST", "/api/connectors/refresh", {}, 60000);
    if (r && r.updated) {
      console.log(`[sutra] connector catalog updated: ${r.count || 0} toolkits`);
    }
  } catch (err) {
    console.error("[sutra] connector catalog check failed:", err.message);
  }
  try {
    const r = await api("POST", "/api/connectors/local/refresh", {}, 60000);
    if (r && r.updated) {
      console.log(`[sutra] 1mcp aggregator ${r.from} -> ${r.version}`);
    }
  } catch (err) {
    console.error("[sutra] aggregator version check failed:", err.message);
  }
}

/* One tick, every upstream. Sequential, not parallel: the desktop update may
   stage a multi-hundred-megabyte DMG, and a catalog check racing it for the
   backend's attention buys nothing on a schedule measured in hours. */
async function checkUpstreams() {
  await checkForUpdate();
  await checkConnectorUpstreams();
}

function startUpdateSchedule() {
  if (!updateCapable()) {
    console.log("[sutra] no update capability in this shell (dev checkout); auto-update off");
    return;
  }
  if (!desktopControl()) {
    // Founder direction 2026-08-25: attaching must not cost the user their
    // updates. The schedule runs; the verbs ride the bundled sidecar CLI.
    console.log("[sutra] attached to a backend we did not start; updating via the bundled sidecar");
  }
  updateTimers.push(setTimeout(checkUpstreams, UPDATE_FIRST_CHECK_MS));
  updateTimers.push(setInterval(checkUpstreams, UPDATE_INTERVAL_MS));
}

/* Hand the helper this process -- its pid, so it waits for THE SHELL rather
   than for whatever the backend's parent happens to be. */
async function armUpdate(relaunch, timeoutMs) {
  const r = await updateOp("arm", { wait_pid: process.pid, relaunch: !!relaunch },
                           timeoutMs || 60000);
  armed = true;
  return r;
}

/* Launch-time reconciliation, before the window is shown.
 *
 * `installed` is read from THIS bundle, not from the backend: on the attach
 * path the backend can be an older install still serving 8330, and treating its
 * answer as our version would throw away an update that actually landed. */
async function resolvePendingUpdate() {
  if (!updateCapable()) return false;
  let r;
  try {
    r = await updateOp("resolve", { installed: app.getVersion() }, 20000);
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
  if (!updateCapable()) return { ok: false, error: "no update capability in this shell" };
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

/* The renderer's one honest window into shell-side updating. In attach mode
   the backend serving the page knows nothing about the shell's staging, so
   the panel asks the SHELL. capable:false (dev checkout, unpackaged run) is a
   first-class answer the panel renders as its honesty message -- this verb
   never fabricates a row. `staged` is read live from the manifest (network-
   free); the latest/available figures are the cache of the last check. */
ipcMain.handle("sutra:update-state", async () => {
  const base = { ok: true, attach: !ownBackend, capable: updateCapable(),
                 installed: app.getVersion(), staging: !!staging, armed };
  if (!updateCapable()) return { ...base, reason: "not running from an installed bundle" };
  const d = lastUpdateCheck || {};
  let staged = null;
  try { staged = await updateOp("staged", null, 5000); } catch (e) { /* unknown stays unknown */ }
  return { ...base,
    latest: d.latest || null,
    update_available: !!d.update_available,
    error: d.error || null,
    staged: !!(staged && staged.pending && staged.state === "staged"),
    staged_version: (staged && staged.version) || null,
    staged_state: (staged && staged.state) || null };
});

/* Panel theme -> nativeTheme. The SB iframe is cross-origin and derives its
   own dark mode from prefers-color-scheme; Chromium derives that scheme from
   nativeTheme. Following the panel's effective theme here is the only bridge
   that keeps the iframe and the panel in the same palette. Allow-listed
   values only — this is renderer input. */
ipcMain.handle("sutra:theme", async (_e, t) => {
  const allowed = ["dark", "light", "system"];
  if (!allowed.includes(t)) return { ok: false, error: "bad theme " + String(t).slice(0, 24) };
  try {
    require("electron").nativeTheme.themeSource = t;
    return { ok: true, theme: t };
  } catch (err) {
    return { ok: false, error: String(err && err.message || err) };
  }
});

/* Stage on demand, for the panel's "Check for updates".
 *
 * The panel found an update and cannot download it itself: /desktop/stage is
 * token-authenticated and the token deliberately never reaches the renderer.
 * Before this verb existed the manual check was a dead end -- it reported a new
 * version and downloaded nothing, leaving the only path the blocking
 * "Download & install" button, while the background download waited for a timer
 * up to six hours away. The renderer still only ASKS; this process owns the
 * token and does the work, exactly as with apply/defer. */
ipcMain.handle("sutra:update-stage", async () => {
  if (!updateCapable()) return { ok: false, error: "no update capability in this shell" };
  if (armed) return { ok: true, staged: false, reason: "an update is already armed" };
  try {
    const r = await stageNow();
    return { ok: true, staged: !!(r && r.staged), version: r && r.version, reason: r && r.reason };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

/* Balance actionable write: the ONLY path from the panel to the token-gated
   endpoint. The renderer asks; the main process — which owns the token —
   attaches it via api() below. Input is passed through untouched: the server
   owns validation (op whitelist, id shape, note cap) and answers 4xx there. */
ipcMain.handle("sutra:balance-actionable", async (_e, body) => {
  try {
    const b = body || {};
    return await api("POST", "/api/balance/actionable",
                     { id: b.id, op: b.op, note: b.note, reason: b.reason });
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
});

/* Teamsutra task actions (queue / drop / release). Unlike the balance handler
   above, this one CHECKS desktopControl() first: on the attach path the
   backend was started with a different token and every write would 403 —
   refusing here with a reason beats a bare server error in the UI. */
ipcMain.handle("sutra:teamsutra-action", async (_e, body) => {
  try {
    if (!desktopControl()) {
      return { ok: false, error: "this window is attached to a backend it did not start — queue actions are disabled" };
    }
    const b = body || {};
    if (!/^t-[0-9a-f]{8}$/.test(String(b.id || "")))  return { ok: false, error: "bad task id" };
    if (!["queue", "drop", "release", "apply"].includes(b.op)) return { ok: false, error: "bad op" };
    return await api("POST", "/api/teamsutra/tasks/" + b.id + "/" + b.op, {});
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
});

/* Sign in / switch the Claude account, from the Usage screen's Account card.
   Runs the CLI's OWN OAuth flow (`claude auth login`) -- this app never sees a
   credential; the CLI writes ~/.claude.json and the backend re-reads it on the
   next /api/account request, so the card refreshes without a restart.

   Gates, per the dual-lane design review (codex + deepseek, 2026-08-25):
     - desktopControl(): only when this shell spawned its own backend;
     - SENDER ORIGIN: only the panel this shell serves may invoke it — any other
       frame that somehow gets the preload bridge is refused;
     - the child runs under the imported login-shell env (Finder's empty env
       HANGS `claude` — see shellEnv) MINUS every ANTHROPIC_- and CLAUDE_CODE_-
       prefixed var, so an exported token cannot change what "login" means;
     - stdout/stderr are drained and NEVER cross the bridge — OAuth CLIs print
       URLs and device codes; the renderer gets {ok, error} and nothing else.

   A second invocation while one runs CANCELS the running one (the panel's
   button doubles as Cancel) — an abandoned browser tab must not wedge the
   card. Teardown is SIGTERM, then SIGKILL after 5s; the busy slot clears on
   actual child exit, never on a timer alone. The binary is whatever `claude`
   the user's login shell resolves — deliberate for a desktop developer tool,
   and the same resolution every terminal on this machine uses. */
let authChild = null;
ipcMain.handle("sutra:auth-login", async (e) => {
  if (!desktopControl()) {
    return { ok: false, error: "sign-in is only available when this window started its own backend" };
  }
  try {
    if (new URL(e.senderFrame.url).origin !== ORIGIN) throw new Error("origin");
  } catch { return { ok: false, error: "refused: unexpected caller" }; }
  if (authChild) {
    const c = authChild;
    try { c.kill("SIGTERM"); } catch (err) {}
    setTimeout(() => { try { c.kill("SIGKILL"); } catch (err) {} }, 5000);
    return { ok: false, error: "cancelled" };
  }
  const env = { ...process.env, ...shellEnv() };
  for (const k of Object.keys(env)) if (/^(ANTHROPIC_|CLAUDE_CODE_)/.test(k)) delete env[k];
  return await new Promise((resolve) => {
    let settled = false;
    const done = (r) => { if (!settled) { settled = true; authChild = null; resolve(r); } };
    let child;
    try {
      child = spawn("claude", ["auth", "login"], { env, stdio: ["ignore", "pipe", "pipe"] });
    } catch (err) { return done({ ok: false, error: "could not start claude: " + err.message }); }
    authChild = child;
    child.stdout.resume();                       // drained, never forwarded
    child.stderr.resume();
    const t = setTimeout(() => {
      try { child.kill("SIGTERM"); } catch (err) {}
      setTimeout(() => { try { child.kill("SIGKILL"); } catch (err) {} }, 5000);
    }, 180000);
    child.on("error", (err) => { clearTimeout(t); done({ ok: false, error: String(err.message || err) }); });
    child.on("close", (code) => {
      clearTimeout(t);
      done(code === 0 ? { ok: true }
                      : { ok: false, error: "sign-in did not complete (exit " + code + ")" });
    });
  });
});

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
 * It has to run BEFORE the backend is killed -- arming is an HTTP call to it
 * in own mode, a sidecar-CLI call in attach mode -- which is why the quit is
 * deferred once and re-issued. Bounded hard on BOTH verbs: a quit that hangs
 * on a network call OR a locked manifest is a frozen app, and no update is
 * worth that; a timeout here means quit WITHOUT arming, and the next launch's
 * resolve finishes the job from the surviving manifest.
 *
 * A backend we merely attached to is still left alone -- but since 2026-08-25
 * attaching no longer forfeits the update: the sidecar owns it. */
let quitArmAttempted = false;

async function applyOnQuit() {
  try {
    const s = await updateOp("staged", null, 3000);
    if (!s || !s.pending || s.state !== "staged") return;
    console.log(`[sutra] applying deferred update ${s.version} on quit`);
    await armUpdate(false, 8000);    // do NOT reopen: the user chose to quit
  } catch (err) {
    // Nothing is lost. The manifest survives, and the next launch finishes it.
    console.error("[sutra] deferred apply skipped:", err.message);
  }
}

app.on("before-quit", (e) => {
  if (!quitArmAttempted && updateCapable() && !armed) {
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
