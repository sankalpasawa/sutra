#!/usr/bin/env node
/* Walk the organisation level on the source server with a headless Chrome of its own over the DevTools protocol, as the
   person would: found an organisation from the New organisation sheet with words for its first department, read Root's
   ask in the organisation's chat, stamp it, watch the department appear on the left, open the chart, Root's settings and
   the department's Map. It founds one organisation on the server's record and stamps one ask; nothing else is written.
     usage: node qa/walks/shot-org.js <out-dir> [base-url]
       out-dir   where the PNGs go (a Chrome profile is kept under out-dir/chrome-profile)
       base-url  default http://127.0.0.1:8341
     env: WALK_ORG=<name> the organisation to found (default "Sharma Tailors"); WALK_FIRST=<words> for its first department;
          SHOT_PORT=<n> the DevTools port (default 9352); CHROME=<path> the browser (default: Google Chrome on this Mac). */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

const OUT = process.argv[2];
const BASE = (process.argv[3] || "http://127.0.0.1:8341").replace(/\/$/, "");
if (!OUT){ console.log("usage: node shot-org.js <out-dir> [base-url]"); process.exit(2); }
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = Number(process.env.SHOT_PORT || 9352);
const ORG = process.env.WALK_ORG || "Sharma Tailors";
const FIRST = process.env.WALK_FIRST || "A website for Sharma Tailors: bespoke suits and sherwanis in Jaipur since 1978, what we stitch, our prices, and how to book a fitting";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const get = url => new Promise((res, rej) => http.get(url, r => { let b = ""; r.on("data", d => b += d); r.on("end", () => res(b)); }).on("error", rej));
const api = async tail => JSON.parse(await get(BASE + "/api/native/" + tail));

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars", "--remote-debugging-port=" + PORT,
    "--user-data-dir=" + path.join(OUT, "chrome-profile"), "--window-size=1500,1100", "about:blank"], { stdio: "ignore" });
  const done = code => { try { chrome.kill("SIGKILL"); } catch (e) {} process.exit(code); };
  setTimeout(() => { console.log("gave up after 420 s"); done(2); }, 420000);
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
  const words = async (sel, n) => run(`(document.querySelector(${JSON.stringify(sel)}) || document.body).innerText.replace(/\\s+/g, ' ').slice(0, ${n})`);
  const tree = () => run(`JSON.stringify([...document.querySelectorAll('.o2tree .o2row')].map(r => r.textContent.trim()))`);
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1500, height: 1100, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(3500);
  /* 1. found, from the sheet's own path: the organisation and its first words */
  const founded = await run(`(async () => {
    goDest('org'); if (S.screen !== 'org2') openScreen('org2');
    if (typeof loadOrg2 === 'function') await loadOrg2(true);
    await wbLoadRefs();
    wbS().found = { org: ${JSON.stringify(ORG)}, goal: ${JSON.stringify(FIRST)}, busy: false, error: null };
    await wbFoundGo();
    return JSON.stringify({ error: S.wb.found && S.wb.found.error, sel: o2S().sel });
  })()`);
  console.log("founded", founded);
  if (/"error":"/.test(founded)) done(1);
  const depts = (await api("depts")).depts;
  const root = depts.filter(x => x.kind === "root" && x.name === ORG + " Root").slice(-1)[0];
  if (!root){ console.log("no Root named", ORG + " Root"); done(1); }
  const org = JSON.parse(founded).sel;
  console.log("root", root.ref, "organisation", org);
  /* 2. Root's ask for the first department lands in the organisation's chat */
  let ask = null;
  for (let i = 0; i < 60 && !ask; i++){ await sleep(2000); const c = await api(encodeURIComponent(root.ref) + "/chat"); ask = (c.asks || [])[0] || null; }
  if (!ask){ console.log("Root asked nothing in 120 s"); done(1); }
  await run(`(async () => { await wbLoadChat(${JSON.stringify(root.ref)}, true); dpRender(); return 1; })()`);
  await sleep(800);
  console.log("tree before the stamp:", await tree());
  await shot("1-org-chat.png");
  console.log("the organisation's row, in words:", await words(".o2main", 700));
  /* 3. the stamp, by the button in the chat; the department is born; the tree learns of it without a reload */
  const stamped = await run(`(() => { const b = document.querySelector('[data-wbdecide][data-wbok="1"]'); if (!b) return 'no Stamp button'; b.click(); return 'clicked'; })()`);
  console.log("stamp", stamped);
  if (stamped !== "clicked") done(1);
  let child = null;
  for (let i = 0; i < 90 && !child; i++){ await sleep(2000); child = (await api("depts")).depts.filter(x => x.parent === root.ref)[0] || null; }
  if (!child){ console.log("no department born in 180 s"); done(1); }
  console.log("born", child.name, child.ref);
  for (let i = 0; i < 10; i++){ await sleep(1500); const t = await tree(); if (t.indexOf(child.name) >= 0) break; }
  const after = await tree();
  console.log("tree after the birth:", after);
  await shot("2-org-born.png");
  console.log("the organisation's row, in words:", await words(".o2main", 900));
  /* 4. the chart: the organisation over its departments, no Root tile */
  await run(`(() => { o2S().view = 'chart'; o2Render(); return 1; })()`);
  await sleep(500);
  console.log("the chart, in words:", await words(".o2chart", 300));
  await shot("3-org-chart.png");
  /* 5. Root's settings: a pane */
  await run(`(() => { o2S().view = 'charter'; S.wb.tab[${JSON.stringify(root.ref)}] = 'root'; dpRender(); return 1; })()`);
  await sleep(500);
  console.log("Root settings, in words:", await words(".o2main", 600));
  await shot("4-root-settings.png");
  /* 6. the department's own Map */
  await run(`(async () => { S.wb.tab[${JSON.stringify(root.ref)}] = 'chat'; o2Select(${JSON.stringify(child.ref)}); await wbLoadMap(${JSON.stringify(child.ref)}, true); S.wb.tab[${JSON.stringify(child.ref)}] = 'map'; dpRender(); return 1; })()`);
  await sleep(1200);
  await run(`(() => { dpRender(); return 1; })()`);
  await shot("5-dept-map.png");
  console.log("the department's Map, in words:", await words(".o2main", 400));
  console.log(JSON.stringify({ org: ORG, root: root.ref, child: child.name, root_row_drawn: after.indexOf("Root") >= 0, child_on_left: after.indexOf(child.name) >= 0 }));
  ws.close();
  done(0);
})().catch(e => { console.log("failed:", e && e.message || e); process.exit(1); });
