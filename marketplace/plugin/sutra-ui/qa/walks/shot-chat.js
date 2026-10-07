#!/usr/bin/env node
/* Capture the one point of entry on the source server, with a headless Chrome of its own over the DevTools protocol:
   Root's chat (whole), a department's chat (scoped, the chip on the box), the Board as chats, and Priority's Settings.
   It only looks.
     usage: node qa/walks/shot-chat.js <out-dir> [base-url]
       out-dir   where the four PNGs go (a Chrome profile is kept under out-dir/chrome-profile)
       base-url  default http://127.0.0.1:8341
     env: WALK_ROOT=<name> picks that Root (default: the last Root the server lists); SHOT_PORT=<n> the DevTools port
          (default 9351); CHROME=<path> the browser (default: Google Chrome on this Mac). */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

const OUT = process.argv[2];
const BASE = (process.argv[3] || "http://127.0.0.1:8341").replace(/\/$/, "");
if (!OUT){ console.log("usage: node shot-chat.js <out-dir> [base-url]"); process.exit(2); }
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = Number(process.env.SHOT_PORT || 9351);
const ROOT_NAME = process.env.WALK_ROOT || "";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const get = url => new Promise((res, rej) => http.get(url, r => { let b = ""; r.on("data", d => b += d); r.on("end", () => res(b)); }).on("error", rej));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars", "--remote-debugging-port=" + PORT,
    "--user-data-dir=" + path.join(OUT, "chrome-profile"), "--window-size=1500,1300", "about:blank"], { stdio: "ignore" });
  const done = code => { try { chrome.kill("SIGKILL"); } catch (e) {} process.exit(code); };
  setTimeout(() => { console.log("gave up after 120 s"); done(2); }, 120000);
  let target = null;
  for (let i = 0; i < 60 && !target; i++){
    await sleep(250);
    try { target = JSON.parse(await get("http://127.0.0.1:" + PORT + "/json/list")).filter(t => t.type === "page")[0]; } catch (e) {}
  }
  if (!target){ console.log("Chrome did not come up"); done(1); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const waiting = {};
  ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && waiting[m.id]){ waiting[m.id](m); delete waiting[m.id]; } };
  const send = (method, params) => new Promise(res => { const i = ++id; waiting[i] = res; ws.send(JSON.stringify({ id: i, method, params: params || {} })); });
  const run = async expr => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result && r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
    return r.result && r.result.result && r.result.result.value;
  };
  const shot = async name => {
    await sleep(600);
    const r = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.result.data, "base64"));
    console.log("saved", name, fs.statSync(path.join(OUT, name)).size, "bytes");
  };
  const words = async n => run(`(document.querySelector('.o2vb') || document.body).innerText.replace(/\\s+/g, ' ').slice(0, ${n})`);
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1500, height: 1300, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(3500);
  const opened = await run(`(async () => {
    goDest('org'); if (S.screen !== 'org2') openScreen('org2');
    const d = await (await fetch('/api/native/depts')).json();
    const roots = d.depts.filter(x => x.kind === 'root');
    const root = roots.filter(x => x.name === ${JSON.stringify(ROOT_NAME)})[0] || roots.slice(-1)[0];
    if (!root) return JSON.stringify({ error: 'no Root on this server' });
    const child = d.depts.filter(x => x.parent === root.ref)[0];
    if (typeof loadOrg2 === 'function') await loadOrg2(true);
    const me = DOMAINS.filter(x => x.ref === root.ref)[0]; const org = me && me.parent_ref;
    const o = o2S(); [org, root.ref].forEach(r => r && o.expanded && o.expanded.add(r));
    await wbLoadRefs(); o2Select(root.ref); await wbLoadMap(root.ref, true); await wbLoadChat(root.ref, true);
    delete S.wb.tab[root.ref]; dpRender();
    window.__refs = { root: root.ref, child: child && child.ref };
    return JSON.stringify({ root: root.name, child: child && child.name, tab: wbTab(root.ref), turns: (S.wb.chat[root.ref].turns || []).length });
  })()`);
  console.log("opened", opened);
  if (/no Root/.test(opened)){ done(1); }
  await shot("1-root-chat.png");
  console.log("Root's chat, in words:", await words(900));
  const scoped = await run(`(async () => {
    const r = window.__refs.child; if (!r) return 'no child';
    o2Select(r); await wbLoadMap(r, true); await wbLoadChat(r, true); delete S.wb.tab[r]; dpRender();
    return JSON.stringify({ tab: wbTab(r), about: S.wb.chat[r].about, turns: (S.wb.chat[r].turns || []).length });
  })()`);
  console.log("scoped", scoped);
  await shot("2-dept-chat.png");
  console.log("the department's chat, in words:", await words(700));
  await run(`(async () => { const r = window.__refs.child; if (!r) return 0; await wbLoadBoard(r, true); S.wb.tab[r] = 'board'; dpRender(); return 1; })()`);
  await sleep(500);
  await shot("3-board-as-chats.png");
  console.log("the Board, in words:", await words(500));
  await run(`(async () => { const r = window.__refs.child; if (!r) return 0; await wbLoadSteps(r, 'Priority', true); S.wb.tab[r] = ''; dpS().tab[r] = 'priority'; dpS().pane[r + ':priority'] = 'settings'; dpRender(); return 1; })()`);
  await sleep(1200);
  await run(`(() => { dpRender(); return 1; })()`);
  await shot("4-priority-settings.png");
  console.log("Priority's Settings, in words:", await words(600));
  ws.close();
  done(0);
})().catch(e => { console.log("failed:", e && e.message || e); process.exit(1); });
