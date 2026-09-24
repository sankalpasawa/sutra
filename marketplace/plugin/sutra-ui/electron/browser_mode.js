/* Browser mode -- the panel in an ordinary browser tab, with the app's authority.
 *
 * `Sutra --browser` starts the backend exactly as the window does, but instead of
 * a BrowserWindow it runs this gateway on 127.0.0.1:8340 (beta 8341) and opens
 * the operator's default browser at it. Two jobs:
 *
 *   1. PROXY every request (HTTP and WebSocket) to the backend on 8330, adding
 *      one <script src="/__sutra/bridge.js"> to each HTML page.
 *   2. SERVE the bridge: bridge.js defines window.sutra over fetch(), and
 *      POST /__sutra/bridge/<verb> runs the SAME main-process handler the
 *      preload's ipcRenderer.invoke() runs. The panel cannot tell the two apart.
 *
 * WHY A GATEWAY AND NOT BACKEND ROUTES. Every verb behind the preload lives in
 * the main process on purpose: it owns the desktop token, and credentials (a
 * Codex API key, a DeepSeek key) cross one in-process hop and a child's stdin,
 * never a request body on the unauthenticated backend port. Moving the verbs
 * into app.py would undo that. The gateway keeps the main process the authority
 * and only changes the transport from IPC to authenticated loopback HTTP.
 *
 * TRUST MODEL -- what the preload got for free, rebuilt explicitly:
 *   preload: "a page cannot conjure a preload"      -> here: a SESSION COOKIE
 *   ipc:     only the window we loaded can invoke   -> here: a PAIRING CODE
 *
 *   PAIRING   The main process mints a one-time code (32 random bytes, 120 s,
 *             single use) and opens /__sutra/pair?code=... in the browser. The
 *             code is swapped for a session cookie (HttpOnly, SameSite=Strict)
 *             and the browser is redirected so the code leaves the address bar.
 *   SESSION   EVERY request -- pages, API, websockets, the bridge -- needs the
 *             cookie. An unpaired tab gets a page saying how to open Sutra, and
 *             nothing else. So the gateway is stricter than raw 8330.
 *   HOST      Only 127.0.0.1:<port> and localhost:<port> are served. A site that
 *             points its own DNS name at 127.0.0.1 (DNS rebinding) is refused.
 *   BRIDGE    POST only, Origin must equal this gateway's origin exactly,
 *             Content-Type application/json and x-sutra-bridge: 1 (neither can
 *             be sent cross-origin without a preflight this server never
 *             answers), body capped at 64 KB, verb from a fixed allowlist.
 *   PRIVACY   Bridge bodies can hold an API key. They are never logged, never
 *             forwarded to the backend, and dropped when the handler returns.
 *             Our cookie is stripped before a request reaches the backend.
 *
 * OUT OF SCOPE, same as the backend's declared model (providers.editing_allowed):
 * other processes running as this user. They can already reach 8330 and read
 * this user's files; cookies for 127.0.0.1 are also visible to any other
 * server on loopback. The cookie name carries the port so stable and beta do
 * not overwrite each other (cookies ignore ports).
 *
 * Pure Node: no `electron` import, so test_browser_mode.js runs it with plain
 * node against a fake backend.
 */
"use strict";

const http = require("http");
const net = require("net");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PAIR_TTL_MS = 120 * 1000;
const MAX_PENDING_CODES = 8;
const MAX_SESSIONS = 32;
const MAX_BRIDGE_BODY = 64 * 1024;
const MAX_HTML_BYTES = 8 * 1024 * 1024;
const BRIDGE_SCRIPT_TAG = '<script src="/__sutra/bridge.js"></script>';

/* The preload's surface, verb -> IPC channel + how its arguments pack into the
   one value the handler receives. Mirrors preload.js; a verb missing here is
   simply absent from window.sutra in a browser, which the panel already treats
   as "not available". onUpdateStaged is an event, served by /__sutra/events. */
const one = (a) => a;
const none = () => undefined;
const BRIDGE_VERBS = {
  applyUpdate:        { channel: "sutra:update-apply",         pack: none },
  deferUpdate:        { channel: "sutra:update-defer",         pack: none },
  updateState:        { channel: "sutra:update-state",         pack: none },
  stageUpdate:        { channel: "sutra:update-stage",         pack: none },
  setTheme:           { channel: "sutra:theme",                pack: one },
  pickDirectory:      { channel: "sutra:pick-directory",       pack: one },
  markActionable:     { channel: "sutra:balance-actionable",
                        pack: (id, op, note, reason) => ({ id, op, note, reason }) },
  teamsutraAction:    { channel: "sutra:teamsutra-action",     pack: (id, op) => ({ id, op }) },
  authLogin:          { channel: "sutra:auth-login",           pack: none },
  codexLogin:         { channel: "sutra:codex-login",          pack: none },
  codexApiKey:        { channel: "sutra:codex-api-key",        pack: one },
  codexLogout:        { channel: "sutra:codex-logout",         pack: none },
  codexKeyRestore:    { channel: "sutra:codex-key-restore",    pack: none },
  codexKeyForget:     { channel: "sutra:codex-key-forget",     pack: none },
  codexKeyState:      { channel: "sutra:codex-key-state",      pack: none },
  deepseekKeySave:    { channel: "sutra:deepseek-key-save",    pack: one },
  deepseekKeyRemove:  { channel: "sutra:deepseek-key-remove",  pack: none },
  deepseekCliInstall: { channel: "sutra:deepseek-cli-install", pack: none },
};

const sha256 = (s) => crypto.createHash("sha256").update(String(s)).digest("hex");
const token = (n) => crypto.randomBytes(n).toString("base64url");

/* One-time pairing codes. Stored as hashes, so a lookup compares digests of the
   caller's input, never the secret itself byte by byte. */
function createPairingStore(now = Date.now) {
  const codes = new Map();   // sha256(code) -> expiry
  const sweep = () => { const t = now(); for (const [h, exp] of codes) if (exp <= t) codes.delete(h); };
  return {
    mint() {
      sweep();
      while (codes.size >= MAX_PENDING_CODES) codes.delete(codes.keys().next().value);
      const code = token(32);
      codes.set(sha256(code), now() + PAIR_TTL_MS);
      return code;
    },
    redeem(code) {
      if (typeof code !== "string" || code.length < 20 || code.length > 128) return false;
      sweep();
      const h = sha256(code);
      if (!codes.has(h)) return false;
      codes.delete(h);            // single use, whether or not the rest succeeds
      return true;
    },
    size() { sweep(); return codes.size; },
  };
}

function createSessionStore() {
  const sessions = new Set();   // sha256(session id)
  return {
    create() {
      while (sessions.size >= MAX_SESSIONS) sessions.delete(sessions.values().next().value);
      const id = token(32);
      sessions.add(sha256(id));
      return id;
    },
    has(id) { return typeof id === "string" && id.length <= 128 && sessions.has(sha256(id)); },
    clear() { sessions.clear(); },
    size() { return sessions.size; },
  };
}

function parseCookies(header) {
  const out = {};
  for (const part of String(header || "").split(";")) {
    const eq = part.indexOf("=");
    if (eq <= 0) continue;
    const k = part.slice(0, eq).trim();
    if (!(k in out)) out[k] = part.slice(eq + 1).trim();
  }
  return out;
}

/* Everything in the cookie header except ours, so the backend never sees it. */
function stripCookie(header, name) {
  const kept = String(header || "").split(";").map((p) => p.trim())
    .filter((p) => p && !p.startsWith(name + "="));
  return kept.join("; ");
}

function hostAllowed(hostHeader, port) {
  const h = String(hostHeader || "").toLowerCase();
  return h === `127.0.0.1:${port}` || h === `localhost:${port}`;
}

/* The bridge script goes FIRST in the document, before any of the panel's own
   scripts, because the panel reads window.sutra at parse time. panel.html has
   no <head> tag, so the fallbacks matter. */
function injectBridge(html) {
  if (html.includes(BRIDGE_SCRIPT_TAG)) return html;
  for (const re of [/<head\b[^>]*>/i, /<html\b[^>]*>/i, /<!doctype[^>]*>/i]) {
    const m = re.exec(html);
    if (m) {
      const at = m.index + m[0].length;
      return html.slice(0, at) + BRIDGE_SCRIPT_TAG + html.slice(at);
    }
  }
  return BRIDGE_SCRIPT_TAG + html;
}

const UNPAIRED_PAGE = `<!doctype html><meta charset="utf-8"><title>Sutra</title>
<style>body{font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:32em;margin:18vh auto;padding:0 16px;color:#222}
@media (prefers-color-scheme:dark){body{background:#0f0e0c;color:#e8e4dc}}</style>
<h1 style="font-size:20px">This tab is not connected to Sutra</h1>
<p>Open Sutra in the browser from the app: click the Sutra icon in the Dock, or
right-click it and choose <b>Open in Browser</b>. Each link works once.</p>`;

/* createGateway({port, upstreamPort, handlers, clientScript, callerUrl})
     port          the gateway's own port (8340 / 8341)
     upstreamPort  the backend (8330 / 8331)
     handlers      Map channel -> async (event, arg) => result  (the IPC handlers)
     clientScript  path to bridge_client.js
     callerUrl     the senderFrame.url the handlers' origin gates expect; the
                   gateway only calls a handler AFTER authenticating the caller,
                   so it vouches for it exactly as the window's IPC does.       */
function createGateway(opts) {
  const HOST = "127.0.0.1";
  const port = opts.port;
  const upstreamPort = opts.upstreamPort;
  const origin = `http://${HOST}:${port}`;
  const cookieName = `sutra_gw_${port}`;
  const pairing = createPairingStore(opts.now);
  const sessions = createSessionStore();
  const handlers = opts.handlers || new Map();
  const verbs = Object.keys(BRIDGE_VERBS).filter((v) => handlers.has(BRIDGE_VERBS[v].channel));
  const events = new Set();    // open SSE responses
  const tunnels = new Set();   // upgraded sockets; closeAllConnections() cannot see them
  const log = opts.log || (() => {});

  let clientJs = "";
  try { clientJs = fs.readFileSync(opts.clientScript || path.join(__dirname, "bridge_client.js"), "utf8"); }
  catch (e) { log("bridge client missing: " + e.message); }
  const bridgeJs = clientJs.replace("__SUTRA_BRIDGE_VERBS__", JSON.stringify(verbs));

  const plain = (res, code, body, type = "text/plain; charset=utf-8", extra = {}) => {
    res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store",
                          "X-Content-Type-Options": "nosniff", ...extra });
    res.end(body);
  };
  const json = (res, code, obj) => plain(res, code, JSON.stringify(obj), "application/json");
  const authed = (req) => sessions.has(parseCookies(req.headers.cookie)[cookieName]);

  function upstreamHeaders(req) {
    const h = { ...req.headers };
    h.host = `${HOST}:${upstreamPort}`;
    // The body is rewritten for HTML, and loopback compression buys nothing.
    h["accept-encoding"] = "identity";
    const c = stripCookie(req.headers.cookie, cookieName);
    if (c) h.cookie = c; else delete h.cookie;
    return h;
  }

  function proxy(req, res) {
    const up = http.request({ host: HOST, port: upstreamPort, method: req.method,
                              path: req.url, headers: upstreamHeaders(req) }, (ur) => {
      const type = String(ur.headers["content-type"] || "");
      if (!/^text\/html/i.test(type)) {
        res.writeHead(ur.statusCode, ur.headers);
        return ur.pipe(res);
      }
      const chunks = []; let size = 0;
      ur.on("data", (c) => { size += c.length; if (size <= MAX_HTML_BYTES) chunks.push(c); });
      ur.on("end", () => {
        if (size > MAX_HTML_BYTES) return plain(res, 502, "page too large to serve");
        const body = Buffer.from(injectBridge(Buffer.concat(chunks).toString("utf8")), "utf8");
        const headers = { ...ur.headers, "content-length": body.length };
        delete headers["transfer-encoding"];
        delete headers.etag;       // the body is no longer the one the tag names
        res.writeHead(ur.statusCode, headers);
        res.end(body);
      });
      ur.on("error", () => { try { res.destroy(); } catch (e) {} });
    });
    up.on("error", () => { if (!res.headersSent) plain(res, 502, "Sutra backend is not answering"); else res.destroy(); });
    req.pipe(up);
  }

  function pair(req, res, url) {
    if (!pairing.redeem(url.searchParams.get("code"))) {
      return plain(res, 403, UNPAIRED_PAGE, "text/html; charset=utf-8", { "Referrer-Policy": "no-referrer" });
    }
    const id = sessions.create();
    res.writeHead(303, {
      Location: "/",
      "Set-Cookie": `${cookieName}=${id}; Path=/; HttpOnly; SameSite=Strict`,
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
    });
    res.end();
  }

  function bridge(req, res, verb) {
    const spec = Object.prototype.hasOwnProperty.call(BRIDGE_VERBS, verb) ? BRIDGE_VERBS[verb] : null;
    if (!spec || !handlers.has(spec.channel)) return json(res, 404, { ok: false, error: "unknown verb" });
    if (req.method !== "POST") return json(res, 405, { ok: false, error: "POST only" });
    if (req.headers.origin !== origin) return json(res, 403, { ok: false, error: "refused: origin" });
    if (req.headers["x-sutra-bridge"] !== "1" ||
        !/^application\/json\b/i.test(String(req.headers["content-type"] || ""))) {
      return json(res, 403, { ok: false, error: "refused: not a bridge call" });
    }
    let body = ""; let over = false;
    req.setEncoding("utf8");
    req.on("data", (d) => { if (over) return; body += d; if (body.length > MAX_BRIDGE_BODY) { over = true; body = ""; } });
    req.on("end", async () => {
      if (over) return json(res, 413, { ok: false, error: "request too large" });
      let args;
      try { args = JSON.parse(body || "{}").args; } catch (e) { return json(res, 400, { ok: false, error: "bad json" }); }
      if (args === undefined) args = [];
      if (!Array.isArray(args) || args.length > 4) return json(res, 400, { ok: false, error: "bad args" });
      body = "";                   // the key, if there was one, goes no further than the handler
      const event = { senderFrame: { url: opts.callerUrl }, sender: null, viaBrowserBridge: true };
      try {
        const out = await handlers.get(spec.channel)(event, spec.pack(...args));
        json(res, 200, { result: out === undefined ? null : out });
      } catch (e) {
        // Never the message: a handler error can quote its input.
        json(res, 500, { ok: false, error: "the app could not complete that" });
      }
    });
  }

  function eventStream(req, res) {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store",
                         Connection: "keep-alive" });
    res.write(": sutra\n\n");
    events.add(res);
    req.on("close", () => events.delete(res));
  }

  const server = http.createServer((req, res) => {
    if (!hostAllowed(req.headers.host, port)) return plain(res, 421, "wrong host");
    let url;
    try { url = new URL(req.url, origin); } catch (e) { return plain(res, 400, "bad url"); }
    if (url.pathname === "/__sutra/pair") return pair(req, res, url);
    if (!authed(req)) return plain(res, 401, UNPAIRED_PAGE, "text/html; charset=utf-8");
    if (url.pathname === "/__sutra/bridge.js") return plain(res, 200, bridgeJs, "text/javascript; charset=utf-8");
    if (url.pathname === "/__sutra/events") return eventStream(req, res);
    const m = /^\/__sutra\/bridge\/([A-Za-z]+)$/.exec(url.pathname);
    if (m) return bridge(req, res, m[1]);
    if (url.pathname.startsWith("/__sutra/")) return plain(res, 404, "not found");
    proxy(req, res);
  });

  /* WebSockets (chat, terminal). Same gates, plus Origin: a browser always sends
     it on a handshake and cannot forge it, and the backend's own _origin_ok
     would otherwise accept any loopback origin. */
  server.on("upgrade", (req, sock, head) => {
    tunnels.add(sock);
    sock.on("close", () => tunnels.delete(sock));
    const refuse = (code, why) => { try { sock.end(`HTTP/1.1 ${code} ${why}\r\nConnection: close\r\n\r\n`); } catch (e) {} };
    if (!hostAllowed(req.headers.host, port)) return refuse(421, "Misdirected Request");
    if (!authed(req)) return refuse(401, "Unauthorized");
    if (req.headers.origin && req.headers.origin !== origin) return refuse(403, "Forbidden");
    const up = net.connect(upstreamPort, HOST);
    tunnels.add(up);
    up.on("close", () => tunnels.delete(up));
    up.once("connect", () => {
      const h = upstreamHeaders(req);
      delete h["accept-encoding"];
      let raw = `${req.method} ${req.url} HTTP/1.1\r\n`;
      for (const [k, v] of Object.entries(h)) {
        for (const vv of Array.isArray(v) ? v : [v]) raw += `${k}: ${vv}\r\n`;
      }
      up.write(raw + "\r\n");
      if (head && head.length) up.write(head);
      sock.pipe(up); up.pipe(sock);
    });
    const kill = () => { try { sock.destroy(); } catch (e) {} try { up.destroy(); } catch (e) {} };
    up.on("error", kill); sock.on("error", kill);
    up.on("close", kill); sock.on("close", kill);
  });

  const heartbeat = setInterval(() => { for (const r of events) { try { r.write(": ping\n\n"); } catch (e) {} } }, 25000);
  if (heartbeat.unref) heartbeat.unref();

  return {
    server,
    origin,
    cookieName,
    verbs,
    listen() {
      return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(port, HOST, () => { server.removeListener("error", reject); resolve(); });
      });
    },
    /* A fresh single-use link. Minted per open, never reused. */
    pairingUrl() { return `${origin}/__sutra/pair?code=${pairing.mint()}`; },
    /* Push to every paired tab (the preload's webContents.send). */
    emit(name, data) {
      const msg = `event: ${name}\ndata: ${JSON.stringify(data === undefined ? null : data)}\n\n`;
      for (const r of events) { try { r.write(msg); } catch (e) {} }
    },
    close() {
      clearInterval(heartbeat);
      for (const r of events) { try { r.end(); } catch (e) {} }
      for (const s of tunnels) { try { s.destroy(); } catch (e) {} }
      sessions.clear();
      const closing = new Promise((resolve) => server.close(() => resolve()));
      // Keep-alive, event-stream and websocket sockets would hold close() open.
      if (server.closeAllConnections) server.closeAllConnections();
      return closing;
    },
  };
}

/* The debug port, from SUTRA_DEBUG_PORT or --debug-port=N. Returns a valid
   unprivileged port number or null; anything else is ignored, never guessed. */
function debugPortFrom(env, argv) {
  let raw = env && env.SUTRA_DEBUG_PORT;
  for (const a of argv || []) {
    const m = /^--debug-port=(.*)$/.exec(String(a));
    if (m) raw = m[1];
  }
  if (raw === undefined || raw === null || raw === "") return null;
  if (!/^\d{4,5}$/.test(String(raw))) return null;
  const n = Number(raw);
  return n >= 1024 && n <= 65535 ? n : null;
}

module.exports = {
  BRIDGE_VERBS, BRIDGE_SCRIPT_TAG, PAIR_TTL_MS,
  createGateway, createPairingStore, createSessionStore,
  parseCookies, stripCookie, hostAllowed, injectBridge, debugPortFrom,
};
