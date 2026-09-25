/* Tests for browser mode (browser_mode.js + bridge_client.js).
 *
 * Plain node, no Electron: the gateway is pure Node by design. Two layers:
 *   unit   every guard on its own (pairing, sessions, host, cookies, injection,
 *          debug-port parsing)
 *   live   a real gateway in front of a fake backend, driven over real sockets:
 *          pairing, the proxy, HTML injection, the bridge, websockets, events.
 *
 * Run: node test_browser_mode.js   (exit 0 = all pass)
 */
"use strict";

const assert = require("assert");
const http = require("http");
const net = require("net");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const bm = require("./browser_mode.js");

let passed = 0;
const failures = [];
async function t(name, fn) {
  if (process.env.TRACE) console.error("> " + name);
  try { await fn(); passed++; }
  catch (e) { failures.push(name + ": " + (e && e.message)); }
}

/* ------------------------------------------------------------------ unit -- */
async function unit() {
  await t("debug port: off by default", () => {
    assert.strictEqual(bm.debugPortFrom({}, []), null);
    assert.strictEqual(bm.debugPortFrom({ SUTRA_DEBUG_PORT: "" }, []), null);
  });
  await t("debug port: env and flag, flag wins", () => {
    assert.strictEqual(bm.debugPortFrom({ SUTRA_DEBUG_PORT: "9229" }, []), 9229);
    assert.strictEqual(bm.debugPortFrom({ SUTRA_DEBUG_PORT: "9229" }, ["--debug-port=9333"]), 9333);
  });
  await t("debug port: junk and privileged ports refused", () => {
    for (const bad of ["80", "0", "65536", "9229; rm -rf", "abc", "-1", "9229.5", "123456"]) {
      assert.strictEqual(bm.debugPortFrom({ SUTRA_DEBUG_PORT: bad }, []), null, bad);
    }
  });

  await t("host: only loopback on our port", () => {
    assert.ok(bm.hostAllowed("127.0.0.1:8340", 8340));
    assert.ok(bm.hostAllowed("localhost:8340", 8340));
    assert.ok(bm.hostAllowed("LOCALHOST:8340", 8340));
    for (const bad of ["evil.com:8340", "127.0.0.1:8330", "127.0.0.1", "", undefined,
                       "127.0.0.1.evil.com:8340", "127.0.0.1:8340@evil.com"]) {
      assert.ok(!bm.hostAllowed(bad, 8340), String(bad));
    }
  });

  await t("cookies: parse and strip only ours", () => {
    assert.deepStrictEqual(bm.parseCookies("a=1; sutra_gw_8340=xyz; b=2"),
                           { a: "1", sutra_gw_8340: "xyz", b: "2" });
    assert.strictEqual(bm.stripCookie("a=1; sutra_gw_8340=xyz; b=2", "sutra_gw_8340"), "a=1; b=2");
    assert.strictEqual(bm.stripCookie("sutra_gw_8340=xyz", "sutra_gw_8340"), "");
    assert.strictEqual(bm.stripCookie(undefined, "x"), "");
  });

  await t("inject: after <head>, before every other script", () => {
    const out = bm.injectBridge('<!doctype html><html><head><script src="a.js"></script></head>');
    assert.ok(out.indexOf(bm.BRIDGE_SCRIPT_TAG) < out.indexOf("a.js"));
    assert.ok(out.includes("<head>" + bm.BRIDGE_SCRIPT_TAG));
  });
  await t("inject: page with no <head> (panel.html shape)", () => {
    const out = bm.injectBridge("<!doctype html>\n<title>Sutra</title><script src=x.js></script>");
    assert.ok(out.startsWith("<!doctype html>" + bm.BRIDGE_SCRIPT_TAG));
    assert.ok(bm.injectBridge("<p>hi</p>").startsWith(bm.BRIDGE_SCRIPT_TAG));
  });
  await t("inject: idempotent", () => {
    const once = bm.injectBridge("<head></head>");
    assert.strictEqual(bm.injectBridge(once), once);
  });

  await t("pairing: single use", () => {
    const p = bm.createPairingStore();
    const c = p.mint();
    assert.ok(c.length >= 40);
    assert.ok(p.redeem(c));
    assert.ok(!p.redeem(c));
  });
  await t("pairing: expires after the TTL", () => {
    let now = 1000;
    const p = bm.createPairingStore(() => now);
    const c = p.mint();
    now += bm.PAIR_TTL_MS + 1;
    assert.ok(!p.redeem(c));
  });
  await t("pairing: garbage refused, pending codes capped", () => {
    const p = bm.createPairingStore();
    for (const bad of [undefined, null, "", "short", 12345, "x".repeat(500)]) assert.ok(!p.redeem(bad));
    for (let i = 0; i < 20; i++) p.mint();
    assert.ok(p.size() <= 8);
  });
  await t("sessions: unknown ids refused, store capped", () => {
    const s = bm.createSessionStore();
    const id = s.create();
    assert.ok(s.has(id));
    assert.ok(!s.has("nope") && !s.has(undefined) && !s.has(id + "x"));
    for (let i = 0; i < 50; i++) s.create();
    assert.ok(s.size() <= 32);
  });

  await t("verbs: mirror every preload verb except the event", () => {
    const pre = fs.readFileSync(path.join(__dirname, "preload.js"), "utf8");
    const preVerbs = [...pre.matchAll(/^\s{2}([a-zA-Z]+):\s/gm)].map((m) => m[1])
      .filter((v) => v !== "desktop" && v !== "onUpdateStaged");
    assert.deepStrictEqual(Object.keys(bm.BRIDGE_VERBS).sort(), preVerbs.sort());
    for (const v of preVerbs) {
      const ch = bm.BRIDGE_VERBS[v].channel;
      assert.ok(pre.includes(`"${ch}"`), `${v} channel ${ch} not in preload`);
    }
  });
}

/* ------------------------------------------------------------------ live -- */
function freePort() {
  return new Promise((resolve) => {
    const s = net.createServer().listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

function request(port, opts, body) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: "127.0.0.1", port, method: "GET", ...opts,
                               headers: { host: `127.0.0.1:${port}`, ...(opts.headers || {}) } }, (res) => {
      let text = "";
      res.setEncoding("utf8");
      res.on("data", (c) => { text += c; });
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, text }));
    });
    req.on("error", reject);
    if (body !== undefined) req.write(body);
    req.end();
  });
}

/* Open a raw websocket-shaped upgrade and return the socket once a status line
   arrives. The fake backend answers 101 and then echoes bytes back. */
function upgrade(port, headers) {
  return new Promise((resolve, reject) => {
    const s = net.connect(port, "127.0.0.1", () => {
      let raw = `GET /ws/chat HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n`;
      for (const [k, v] of Object.entries(headers || {})) raw += `${k}: ${v}\r\n`;
      s.write(raw + "\r\n");
    });
    let buf = "";
    s.on("data", (d) => {
      buf += d.toString();
      if (buf.includes("\r\n\r\n")) { s.removeAllListeners("data"); resolve({ sock: s, head: buf }); }
    });
    s.on("error", reject);
  });
}

async function live() {
  const upPort = await freePort();
  const gwPort = await freePort();
  const seen = [];   // requests the fake backend received
  let streamClosed = false;

  const backend = http.createServer((req, res) => {
    let body = "";
    req.on("data", (d) => { body += d; });
    req.on("end", () => {
      seen.push({ url: req.url, headers: req.headers, body });
      if (req.url === "/redirect") {
        res.writeHead(307, { Location: `http://127.0.0.1:${upPort}/api/x?y=1` });
        return res.end();
      }
      if (req.url === "/cached") {
        res.writeHead(304, { "Content-Type": "text/html" });
        return res.end();
      }
      if (req.url === "/stream") {         // never ends on its own: an event stream
        res.writeHead(200, { "Content-Type": "text/event-stream" });
        res.write("data: 1\n\n");
        req.socket.on("close", () => { streamClosed = true; });
        return;
      }
      if (req.url === "/die") {             // the backend crashing mid-body
        res.writeHead(200, { "Content-Type": "application/octet-stream" });
        res.write("partial");
        return setTimeout(() => req.socket.destroy(), 50);
      }
      if (req.url === "/") {
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", ETag: "abc" });
        return res.end("<!doctype html><title>Sutra</title><script src=/static/app.js></script>");
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, method: req.method }));
    });
  });
  backend.on("upgrade", (req, sock) => {
    seen.push({ url: req.url, headers: req.headers, ws: true });
    sock.write("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n");
    sock.on("data", (d) => sock.write(d));   // echo
  });
  await new Promise((r) => backend.listen(upPort, "127.0.0.1", r));

  const calls = [];
  const handlers = new Map([
    ["sutra:update-state", async (e) => { calls.push({ ch: "state", e }); return { ok: true, attach: false }; }],
    ["sutra:balance-actionable", async (e, arg) => { calls.push({ ch: "balance", e, arg }); return { ok: true }; }],
    ["sutra:codex-api-key", async (e, key) => { throw new Error("leak " + key); }],
  ]);
  const callerUrl = `http://127.0.0.1:${upPort}/`;
  const gw = bm.createGateway({ port: gwPort, upstreamPort: upPort, handlers, callerUrl });
  await gw.listen();
  const origin = `http://127.0.0.1:${gwPort}`;
  const code = () => new URL(gw.pairingUrl()).searchParams.get("code");

  let cookie = "";
  try {
    await t("live: unpaired page is refused and says how to open Sutra", async () => {
      const r = await request(gwPort, { path: "/" });
      assert.strictEqual(r.status, 401);
      assert.ok(/Open in Browser/.test(r.text));
      assert.strictEqual(seen.length, 0, "nothing reached the backend");
    });
    await t("live: DNS-rebinding host refused", async () => {
      const r = await request(gwPort, { path: "/", headers: { host: `evil.example:${gwPort}` } });
      assert.strictEqual(r.status, 421);
    });
    await t("live: bad pairing code refused", async () => {
      const r = await request(gwPort, { path: "/__sutra/pair?code=" + "A".repeat(43) });
      assert.strictEqual(r.status, 403);
      assert.ok(!r.headers["set-cookie"]);
    });
    await t("live: pairing sets a strict HttpOnly cookie and strips the code", async () => {
      const c = code();
      const r = await request(gwPort, { path: "/__sutra/pair?code=" + c });
      assert.strictEqual(r.status, 303);
      assert.strictEqual(r.headers.location, "/");
      assert.strictEqual(r.headers["referrer-policy"], "no-referrer");
      const sc = r.headers["set-cookie"][0];
      assert.ok(/HttpOnly/.test(sc) && /SameSite=Strict/.test(sc) && /Path=\//.test(sc));
      assert.ok(sc.startsWith(gw.cookieName + "="));
      cookie = sc.split(";")[0];
      const again = await request(gwPort, { path: "/__sutra/pair?code=" + c });
      assert.strictEqual(again.status, 403, "code is single use");
    });
    await t("live: paired page is proxied with the bridge injected first", async () => {
      const r = await request(gwPort, { path: "/", headers: { cookie } });
      assert.strictEqual(r.status, 200);
      assert.ok(r.text.startsWith("<!doctype html>" + bm.BRIDGE_SCRIPT_TAG));
      assert.ok(r.text.indexOf(bm.BRIDGE_SCRIPT_TAG) < r.text.indexOf("app.js"));
      assert.strictEqual(Number(r.headers["content-length"]), Buffer.byteLength(r.text));
      assert.ok(!r.headers.etag, "stale etag dropped");
    });
    await t("live: backend never sees our cookie; other cookies and host rewritten", async () => {
      seen.length = 0;
      const r = await request(gwPort, { path: "/api/x", method: "POST",
        headers: { cookie: cookie + "; theme=dark", origin, "content-type": "application/json" } }, "{}");
      assert.strictEqual(r.status, 200);
      const got = seen[0];
      assert.strictEqual(got.headers.cookie, "theme=dark");
      assert.strictEqual(got.headers.host, `127.0.0.1:${upPort}`);
      assert.strictEqual(got.headers.origin, origin, "origin passes through for the backend's own guard");
      assert.strictEqual(got.body, "{}");
    });
    await t("live: bridge.js carries the offered verbs only", async () => {
      const r = await request(gwPort, { path: "/__sutra/bridge.js", headers: { cookie } });
      assert.strictEqual(r.status, 200);
      assert.ok(!r.text.includes("__SUTRA_BRIDGE_VERBS__"));
      assert.ok(r.text.includes('["markActionable","updateState","codexApiKey"]') ||
                r.text.includes('"updateState"'));
      assert.ok(!r.text.includes('"authLogin"'), "a verb with no handler is not offered");
    });
    await t("live: bridge.js and bridge calls need a session", async () => {
      assert.strictEqual((await request(gwPort, { path: "/__sutra/bridge.js" })).status, 401);
      const r = await request(gwPort, { path: "/__sutra/bridge/updateState", method: "POST",
        headers: { origin, "content-type": "application/json", "x-sutra-bridge": "1" } }, "{}");
      assert.strictEqual(r.status, 401);
    });

    const bridgeHeaders = { cookie, origin, "content-type": "application/json", "x-sutra-bridge": "1" };
    await t("live: bridge call runs the IPC handler with a vouched caller", async () => {
      calls.length = 0;
      const r = await request(gwPort, { path: "/__sutra/bridge/markActionable", method: "POST",
        headers: bridgeHeaders }, JSON.stringify({ args: ["a-1", "done", "n", "r"] }));
      assert.strictEqual(r.status, 200, r.text);
      assert.deepStrictEqual(JSON.parse(r.text).result, { ok: true });
      assert.deepStrictEqual(calls[0].arg, { id: "a-1", op: "done", note: "n", reason: "r" });
      assert.strictEqual(calls[0].e.senderFrame.url, callerUrl);
      assert.strictEqual(calls[0].e.viaBrowserBridge, true);
    });
    await t("live: bridge refuses cross-origin, missing header, wrong type, GET", async () => {
      const post = (h) => request(gwPort, { path: "/__sutra/bridge/updateState", method: "POST", headers: h }, "{}");
      assert.strictEqual((await post({ ...bridgeHeaders, origin: "http://evil.example" })).status, 403);
      assert.strictEqual((await post({ ...bridgeHeaders, origin: "http://127.0.0.1:1" })).status, 403);
      const noOrigin = { ...bridgeHeaders }; delete noOrigin.origin;
      assert.strictEqual((await post(noOrigin)).status, 403);
      const noHdr = { ...bridgeHeaders }; delete noHdr["x-sutra-bridge"];
      assert.strictEqual((await post(noHdr)).status, 403);
      assert.strictEqual((await post({ ...bridgeHeaders, "content-type": "text/plain" })).status, 403);
      const g = await request(gwPort, { path: "/__sutra/bridge/updateState", headers: bridgeHeaders });
      assert.strictEqual(g.status, 405);
      assert.strictEqual(calls.filter((c) => c.ch === "state").length, 0, "handler never ran");
    });
    await t("live: unknown verb, bad args, oversize body", async () => {
      const post = (verb, body) => request(gwPort, { path: "/__sutra/bridge/" + verb, method: "POST",
        headers: bridgeHeaders }, body);
      assert.strictEqual((await post("authLogin", "{}")).status, 404, "no handler registered");
      assert.strictEqual((await post("constructor", "{}")).status, 404);
      assert.strictEqual((await post("updateState", '{"args":"x"}')).status, 400);
      assert.strictEqual((await post("updateState", '{"args":[1,2,3,4,5]}')).status, 400);
      assert.strictEqual((await post("updateState", "not json")).status, 400);
      assert.strictEqual((await post("updateState", JSON.stringify({ args: ["x".repeat(70000)] }))).status, 413);
    });
    await t("live: a handler error never echoes its input (API key)", async () => {
      const key = "sk-proj-SECRETSECRETSECRET";
      const r = await request(gwPort, { path: "/__sutra/bridge/codexApiKey", method: "POST",
        headers: bridgeHeaders }, JSON.stringify({ args: [key] }));
      assert.strictEqual(r.status, 500);
      assert.ok(!r.text.includes("SECRET"), "key leaked in: " + r.text);
    });
    await t("live: websocket without a session refused, backend untouched", async () => {
      seen.length = 0;
      const { sock, head } = await upgrade(gwPort, { Origin: origin });
      sock.destroy();
      assert.ok(head.startsWith("HTTP/1.1 401"));
      assert.strictEqual(seen.length, 0);
    });
    await t("live: websocket from another origin refused", async () => {
      const { sock, head } = await upgrade(gwPort, { Cookie: cookie, Origin: "http://127.0.0.1:3000" });
      sock.destroy();
      assert.ok(head.startsWith("HTTP/1.1 403"));
    });
    await t("live: paired websocket is tunnelled both ways, cookie stripped", async () => {
      seen.length = 0;
      const { sock, head } = await upgrade(gwPort, { Cookie: cookie, Origin: origin });
      assert.ok(head.startsWith("HTTP/1.1 101"), head);
      const echoed = await new Promise((resolve) => { sock.once("data", (d) => resolve(d.toString())); sock.write("ping-123"); });
      sock.destroy();
      assert.strictEqual(echoed, "ping-123");
      assert.ok(seen[0].ws && !seen[0].headers.cookie);
      assert.strictEqual(seen[0].headers.host, `127.0.0.1:${upPort}`);
    });
    await t("live: HEAD and 304 pass through with no injected body", async () => {
      const h = await request(gwPort, { path: "/", method: "HEAD", headers: { cookie } });
      assert.strictEqual(h.status, 200);
      assert.strictEqual(h.text, "");
      assert.notStrictEqual(Number(h.headers["content-length"] || 0), bm.BRIDGE_SCRIPT_TAG.length + 68,
                            "no length claiming an injected body");
      const c = await request(gwPort, { path: "/cached", headers: { cookie } });
      assert.strictEqual(c.status, 304);
      assert.strictEqual(c.text, "");
      assert.ok(!c.headers["content-length"] || c.headers["content-length"] === "0");
    });
    await t("live: a backend redirect to its own port is pointed back at the gateway", async () => {
      const r = await request(gwPort, { path: "/redirect", headers: { cookie } });
      assert.strictEqual(r.status, 307);
      assert.strictEqual(r.headers.location, `${origin}/api/x?y=1`);
    });
    await t("live: closing a tab mid-stream releases the backend", async () => {
      streamClosed = false;
      await new Promise((resolve, reject) => {
        const req = http.get({ host: "127.0.0.1", port: gwPort, path: "/stream",
                               headers: { host: `127.0.0.1:${gwPort}`, cookie } }, (res) => {
          res.once("data", () => { req.destroy(); resolve(); });
        });
        req.on("error", () => {});
        setTimeout(() => reject(new Error("no first event")), 3000);
      });
      for (let i = 0; i < 30 && !streamClosed; i++) await new Promise((r) => setTimeout(r, 50));
      assert.ok(streamClosed, "backend stream still open after the tab went away");
    });
    await t("live: a backend dying mid-body ends the tab's request, never hangs", async () => {
      const outcome = await new Promise((resolve) => {
        const req = http.get({ host: "127.0.0.1", port: gwPort, path: "/die",
                               headers: { host: `127.0.0.1:${gwPort}`, cookie } }, (res) => {
          res.on("data", () => {});
          res.on("end", () => resolve("end"));
          res.on("error", () => resolve("error"));
          res.on("aborted", () => resolve("aborted"));
        });
        req.on("error", () => resolve("error"));
        setTimeout(() => resolve("hung"), 3000);
      });
      assert.notStrictEqual(outcome, "hung");
    });
    await t("live: a refused handshake reset by the client never throws in the app", async () => {
      let uncaught = null;
      const onErr = (e) => { uncaught = e; };
      process.on("uncaughtException", onErr);
      try {
        for (let i = 0; i < 20; i++) {
          const s = net.connect(gwPort, "127.0.0.1", () => {
            s.write(`GET /ws/chat HTTP/1.1\r\nHost: 127.0.0.1:${gwPort}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nOrigin: http://evil.example\r\n\r\n`);
            s.resetAndDestroy ? s.resetAndDestroy() : s.destroy();
          });
          s.on("error", () => {});
        }
        await new Promise((r) => setTimeout(r, 400));
      } finally { process.removeListener("uncaughtException", onErr); }
      assert.strictEqual(uncaught, null, uncaught && uncaught.message);
    });
    await t("live: events reach a paired tab", async () => {
      const got = await new Promise((resolve, reject) => {
        const req = http.get({ host: "127.0.0.1", port: gwPort, path: "/__sutra/events",
                               headers: { host: `127.0.0.1:${gwPort}`, cookie } }, (res) => {
          let buf = "";
          res.setEncoding("utf8");
          res.on("data", (c) => {
            buf += c;
            if (buf.includes(": sutra")) gw.emit("sutra:update-staged", { staged: true, version: "9.9.9" });
            if (buf.includes("9.9.9")) { req.destroy(); resolve(buf); }
          });
        });
        req.on("error", reject);
      });
      assert.ok(got.includes("event: sutra:update-staged"));
      assert.ok(got.includes('"version":"9.9.9"'));
    });
    await t("live: backend down answers 502, not a hang", async () => {
      // A second gateway in front of a port nothing listens on.
      const deadGw = bm.createGateway({ port: await freePort(), upstreamPort: await freePort(),
                                        handlers: new Map(), callerUrl });
      await deadGw.listen();
      const dport = Number(new URL(deadGw.origin).port);
      try {
        const pr = await request(dport, { path: "/__sutra/pair?code=" + new URL(deadGw.pairingUrl()).searchParams.get("code") });
        const c2 = pr.headers["set-cookie"][0].split(";")[0];
        const r = await request(dport, { path: "/api/y", headers: { cookie: c2 } });
        assert.strictEqual(r.status, 502);
      } finally { await deadGw.close(); }
    });
  } finally {
    await gw.close();
    try { backend.closeAllConnections(); backend.close(); } catch (e) {}
  }
}

/* ---------------------------------------------------------- page shim -- */
async function shim() {
  const src = fs.readFileSync(path.join(__dirname, "bridge_client.js"), "utf8")
    .replace("__SUTRA_BRIDGE_VERBS__", JSON.stringify(["updateState", "markActionable"]));

  await t("shim: defines a frozen window.sutra with the offered verbs", async () => {
    const sent = [];
    const win = {};
    const ctx = { window: win, JSON, Array, Object,
      fetch: (url, init) => { sent.push({ url, init }); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ result: { ok: true } }) }); },
      EventSource: function () { this.addEventListener = () => {}; } };
    vm.runInNewContext(src, ctx);
    const s = win.sutra;
    assert.strictEqual(s.desktop, true);
    assert.strictEqual(s.browser, true);
    assert.strictEqual(typeof s.updateState, "function");
    assert.strictEqual(typeof s.onUpdateStaged, "function");
    assert.strictEqual(s.authLogin, undefined, "only offered verbs");
    assert.ok(Object.isFrozen(s));
    const out = await s.markActionable("a-1", "done", "n", "r", "extra");
    assert.deepStrictEqual(out, { ok: true });
    assert.strictEqual(sent[0].url, "/__sutra/bridge/markActionable");
    assert.strictEqual(sent[0].init.headers["x-sutra-bridge"], "1");
    assert.strictEqual(sent[0].init.credentials, "same-origin");
    assert.deepStrictEqual(JSON.parse(sent[0].init.body).args, ["a-1", "done", "n", "r"], "capped at 4 args");
  });
  await t("shim: a refused call resolves {ok:false}, never throws", async () => {
    const win = {};
    vm.runInNewContext(src, { window: win, JSON, Array, Object,
      fetch: () => Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ error: "refused: origin" }) }) });
    const out = await win.sutra.updateState();
    // Built inside the vm realm, so compare by value, not by prototype.
    assert.deepStrictEqual(JSON.parse(JSON.stringify(out)), { ok: false, error: "refused: origin" });
    const win2 = {};
    vm.runInNewContext(src, { window: win2, JSON, Array, Object, fetch: () => Promise.reject(new Error("down")) });
    assert.strictEqual((await win2.sutra.updateState()).ok, false);
  });
  await t("shim: never replaces an Electron preload", () => {
    const pre = { desktop: true, fromPreload: true };
    const win = { sutra: pre };
    vm.runInNewContext(src, { window: win, JSON, Array, Object, fetch: () => {} });
    assert.strictEqual(win.sutra, pre);
  });
}

/* ----------------------------------------------------- main.js wiring -- */
async function wiring() {
  const main = fs.readFileSync(path.join(__dirname, "main.js"), "utf8");
  await t("wiring: debug port is opt-in and read before ready", () => {
    const at = main.indexOf('appendSwitch("remote-debugging-port"');
    assert.ok(at > 0);
    assert.ok(main.slice(at - 200, at).includes("if (DEBUG_PORT)"));
    assert.ok(at < main.indexOf("app.whenReady()"));
  });
  await t("wiring: every IPC handler is recorded for the gateway", () => {
    const reg = main.indexOf("ipcMain.handle = (channel, fn)");
    assert.ok(reg > 0 && reg < main.indexOf('ipcMain.handle("sutra:'), "registry installed before first handler");
  });
  await t("wiring: both boot paths branch on browser mode, window kept off macOS", () => {
    const n = (main.match(/if \(!windowless\(\)\) createWindow\(\);\s*\n\s*if \(BROWSER_MODE\) await openInBrowser\(NO_OPEN\);/g) || []).length;
    assert.strictEqual(n, 2);
    assert.ok(main.includes('let quitHandle = process.platform === "darwin";'));
    assert.ok(main.includes("const windowless = () => BROWSER_MODE && quitHandle;"));
    assert.ok(main.includes("if (quitHandle) BROWSER_MODE = true;"), "no quit handle, no windowless");
  });
  await t("wiring: Windows/Linux get a tray with Open in Browser and Quit, made before the UI", () => {
    const fn = main.slice(main.indexOf("async function installShellMenu()"));
    const body = fn.slice(0, fn.indexOf("\n}\n"));
    assert.ok(/new Tray\(icon\)/.test(body));
    assert.ok(/label: "Open in Browser"/.test(body) && /Quit Sutra/.test(body) && /app\.quit\(\)/.test(body));
    assert.ok(/quitHandle = true;/.test(body), "a tray is what makes windowless safe");
    assert.ok(/catch \(e\)/.test(body), "a tray failure falls back to a window, not a crash");
    const boots = (main.match(/await installShellMenu\(\);\s*\n(\s*\/\/[^\n]*\n)?\s*if \(!windowless\(\)\) createWindow\(\);/g) || []).length;
    assert.strictEqual(boots, 2, "the tray exists before deciding whether to show a window");
  });
  await t("wiring: only windowless mode survives its windows closing", () => {
    assert.ok(main.includes('app.on("window-all-closed", () => { if (!windowless()) app.quit(); });'));
  });
  await t("wiring: update relaunch marker is time-limited", () => {
    assert.ok(/String\(Date\.now\(\)\)/.test(main));
    assert.ok(/Date\.now\(\) - at < RELAUNCH_MARKER_TTL_MS/.test(main));
  });
  await t("wiring: the pairing link never goes to stdout, only its file path", () => {
    assert.ok(main.includes("SUTRA_BROWSER_URL_FILE=${pairUrlFile()}"));
    assert.ok(!/SUTRA_BROWSER_URL=\$\{url\}/.test(main));
  });
  await t("wiring: pairing link file is 0600 and ships in the Windows build", () => {
    assert.ok(/mode: 0o600/.test(main));
    const yml = fs.readFileSync(path.join(__dirname, "electron-builder-win.yml"), "utf8");
    assert.ok(yml.includes("- browser_mode.js") && yml.includes("- bridge_client.js"));
  });
}

(async () => {
  await unit();
  await live();
  await shim();
  await wiring();
  if (failures.length) {
    console.error(`FAIL ${failures.length} / ${passed + failures.length}`);
    for (const f of failures) console.error("  - " + f);
    process.exit(1);
  }
  console.log(`test_browser_mode: ${passed} passed`);
})().catch((e) => { console.error(e); process.exit(1); });
