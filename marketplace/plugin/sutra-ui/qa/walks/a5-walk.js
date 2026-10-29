#!/usr/bin/env node
/* The A5 walk in a real browser (PRD A5.8 P5, steps P5.2 and P5.4): headless Chrome of its own over the DevTools protocol (raw CDP on
   node's global WebSocket, as shot-j2.js does), on the records qa/walks/a5_seed.py wrote.
     usage: node qa/walks/a5-walk.js <out-dir> <base-url> <refs.json>
       out-dir    where the PNGs go (qa/shots/a5)
       base-url   the app, e.g. http://127.0.0.1:8372
       refs.json  what a5_seed.py printed, as {"root": ..., "default": ..., "organic": ..., "website": ..., "task_use": ..., "task_spawn": ..., "task_none": ...,
                  "conversation": ..., "goal": ...}
     env: SHOT_PORT=<n> the DevTools port (default 9362); CHROME=<path> the browser (default: Google Chrome on this Mac).
   Claims, each printed as PASS or FAIL (exit 0 when all held):
     1. Org list: every kind (default, organic, root, website) opens the J2 page in exactly one frame at /j2ui/<ref>/; a word said in
        each reaches its chat; no wording of the page names a kind it is not.
     2. Home, then Graph: every kind of node the seed holds is drawn; `uses` is a solid line, `spawned` a dashed one with a plus, each with
        its reason as words; a node of every kind opens the chat or page it names; no node is only a colour (a word and a glyph go with it).
     3. The Shadow chat's Details jump lands on the task's screen, which holds Decision, Departments, Chats, Costs and Timeline.
     4. Screenshots at 1280 and 390: the graph overview, the focus mode, and the J2 page for default, organic and root. */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

const OUT = process.argv[2];
const BASE = (process.argv[3] || "").replace(/\/$/, "");
const R = process.argv[4] ? JSON.parse(fs.readFileSync(process.argv[4], "utf8")) : null;
if (!OUT || !BASE || !R) { console.log("usage: node a5-walk.js <out-dir> <base-url> <refs.json>"); process.exit(2); }
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = Number(process.env.SHOT_PORT || 9362);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const get = url => new Promise((res, rej) => http.get(url, r => { let b = ""; r.on("data", d => b += d); r.on("end", () => res(b)); }).on("error", rej));
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok }); console.log((ok ? "PASS " : "FAIL ") + name + (ok || !detail ? "" : "  -- " + detail)); };
const BIG = { w: 1280, h: 900, mobile: false, tag: "1280" }, SMALL = { w: 390, h: 844, mobile: true, tag: "390" };
const NARROW = { w: 390, h: 844, mobile: false, tag: "390" };       // the app's own screens (no viewport meta of their own) are laid out at the width, not scaled to 980

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "a5-walk-"));
  const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars", "--remote-debugging-port=" + PORT,
    "--user-data-dir=" + profile, "--window-size=1500,1100", "about:blank"], { stdio: "ignore" });
  const done = code => { try { chrome.kill("SIGKILL"); } catch (e) {} try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {} process.exit(code); };
  setTimeout(() => { console.log("gave up after 240 s"); done(2); }, 240000);
  let target = null;
  for (let i = 0; i < 80 && !target; i++) {
    await sleep(250);
    try { target = JSON.parse(await get("http://127.0.0.1:" + PORT + "/json/list")).filter(t => t.type === "page")[0]; } catch (e) {}
  }
  if (!target) { console.log("Chrome did not come up"); done(1); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const waiting = {}; const exceptions = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && waiting[m.id]) { waiting[m.id](m); delete waiting[m.id]; return; }
    if (m.sessionId) return;
    if (m.method === "Runtime.exceptionThrown") { const d = m.params.exceptionDetails || {}; exceptions.push(((d.exception && d.exception.description) || d.text || "exception").slice(0, 200)); }
  };
  const send = (method, params) => new Promise(res => { const i = ++id; waiting[i] = res; ws.send(JSON.stringify({ id: i, method, params: params || {} })); });
  const run = async expr => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result && r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
    return r.result && r.result.result && r.result.result.value;
  };
  const waitFor = async (expr, ms) => {
    const end = Date.now() + (ms || 15000);
    while (Date.now() < end) { try { if (await run(expr)) return true; } catch (e) {} await sleep(150); }
    return false;
  };
  const shot = async name => {
    await sleep(600);
    const r = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.result.data, "base64"));
    console.log("saved " + name + " " + fs.statSync(path.join(OUT, name)).size + " bytes");
  };
  const viewport = vp => send("Emulation.setDeviceMetricsOverride", { width: vp.w, height: vp.h, deviceScaleFactor: 1, mobile: !!vp.mobile });
  const boot = async vp => {
    await viewport(vp);
    await send("Page.navigate", { url: BASE + "/" });
    await waitFor(`typeof o2Select === 'function' && typeof goDest === 'function' && typeof S !== 'undefined' && typeof sgOpen === 'function'`, 30000);
    await sleep(1500);
  };
  await send("Page.enable"); await send("Runtime.enable");

  // ---- 1. the Org list: every kind opens the J2 page, a word is said in each ----------------------------------------------
  await boot(BIG);
  for (const kind of ["default", "organic", "root", "website"]) {
    const ref = R[kind];
    const opened = await run(`(async () => {
      const REF = ${JSON.stringify(ref)}, root = ${JSON.stringify(kind === "root")};
      goDest('org'); if (S.screen !== 'org2') openScreen('org2');
      if (typeof loadOrg2 === 'function') await loadOrg2(true);
      const d = await (await fetch('/api/native/depts')).json();
      const o = o2S(); let r = REF; const seen = new Set();
      while (r && !seen.has(r)) { seen.add(r); if (o.expanded) o.expanded.add(r);
        const dep = d.depts.filter(x => x.ref === r)[0]; r = (dep && dep.parent) || null; }
      await wbLoadRefs(); o2Select(REF); await wbLoadMap(REF, true);
      if (root) S.wb.tab[REF] = 'j2'; else delete S.wb.tab[REF];
      dpRender();
      for (let i = 0; i < 40 && !(j2vOn(REF) && document.querySelector('.j2vbar')); i++) { await new Promise(r => setTimeout(r, 250)); dpRender(); }
      return JSON.stringify({ on: j2vOn(REF), bar: !!document.querySelector('.j2vbar') });
    })()`);
    const framed = await waitFor(`document.querySelectorAll('iframe.j2v-if').length === 1 && document.querySelector('iframe.j2v-if').getAttribute('src') === '/j2ui/' + ${JSON.stringify(ref)} + '/' && !!document.querySelector('iframe.j2v-if').contentDocument
      && !!document.querySelector('iframe.j2v-if').contentDocument.getElementById('sprog') && document.querySelector('iframe.j2v-if').contentDocument.getElementById('sprog').children.length > 0`, 30000);
    const src = framed ? await run(`document.querySelector('iframe.j2v-if').getAttribute('src')`) : null;
    check("org: " + kind + " opens the J2 page in one frame at /j2ui/<ref>/", framed && src === "/j2ui/" + ref + "/", opened + " " + src);
    if (!framed) continue;
    const word = "hello from the " + kind + " walk";
    const said = await run(`(async () => {
      const w = document.querySelector('iframe.j2v-if').contentWindow, word = ${JSON.stringify(word)};
      const r = await w.fetch('api/say', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: word }) });
      for (let i = 0; i < 24; i++) {
        const st = await (await w.fetch('api/state')).json();
        if ((st.chat || []).some(m => String(m.text).indexOf(word) >= 0)) return JSON.stringify({ code: r.status, seen: true, words: st.words });
        await new Promise(r => setTimeout(r, 500));
      }
      return JSON.stringify({ code: r.status, seen: false });
    })()`);
    const sd = JSON.parse(said);
    check("org: " + kind + ": a word said is in the chat", sd.code === 200 && sd.seen, said);
    const text = await run(`document.querySelector('iframe.j2v-if').contentDocument.body.innerText`);
    check("org: " + kind + ": the page shows no undefined or NaN", !/\b(undefined|NaN)\b/.test(text || ""));
    if (kind !== "website") check("org: " + kind + ": the page does not call itself a website", !/website/i.test(text || ""), (text || "").match(/.{0,30}website.{0,30}/i));
  }

  // ---- 2. Home, then Graph --------------------------------------------------------------------------------------------------
  const home = async () => { await run(`goDest('focus'); openScreen('shadow'); render()`); await sleep(800); };
  const toGraph = async (vp) => {
    await run(`sgSetFocus && sgSetFocus(null); S.shadowGraphFocus = null; try { lsSet('sutra.shadow.graph', null) } catch (e) {} sgReset(); openScreen('shadowgraph'); render()`);
    await waitFor(`S.screen === 'shadowgraph' && document.querySelectorAll('[data-sgnode]').length > 1`, 20000);
    await sleep(500);
  };
  await home();
  const clickGraph = await waitFor(`!!document.querySelector('[data-shgraph]')`, 15000);
  check("home: has a Graph button", clickGraph);
  if (clickGraph) await run(`document.querySelector('[data-shgraph]').click()`);
  const onGraph = await waitFor(`S.screen === 'shadowgraph' && document.querySelectorAll('[data-sgnode]').length > 1`, 20000);
  check("graph: the Graph button opens the graph with nodes", onGraph);
  await sleep(600);
  const view = JSON.parse(await run(`(() => {
    const kinds = {}; document.querySelectorAll('[data-sgnode]').forEach(b => { const k = [...b.classList].filter(c => c.indexOf('sgk-') === 0)[0]; kinds[k] = (kinds[k] || 0) + 1; });
    const edge = k => { const e = document.querySelector('.sgedge.e-' + k); return e ? { dash: getComputedStyle(e).strokeDasharray, plus: !!document.querySelector('.sgplus') } : null; };
    const tags = [...document.querySelectorAll('[data-sgtag]')].map(t => ({ word: t.textContent.trim(), label: t.getAttribute('aria-label') }));
    const bare = [...document.querySelectorAll('[data-sgnode]')].filter(b => !b.querySelector('.sgsub') || !b.querySelector('.sgsub').textContent.trim() || !b.getAttribute('aria-label')).length;
    return JSON.stringify({ kinds, uses: edge('uses'), spawned: edge('spawned'), tags, bare });
  })()`));
  for (const k of ["sgk-shadow", "sgk-task", "sgk-goal", "sgk-conversation", "sgk-task_chat", "sgk-worker", "sgk-department"])
    check("graph: a " + k.slice(4) + " node is drawn", view.kinds[k] > 0, JSON.stringify(view.kinds));
  check("graph: uses is a solid line", view.uses && (view.uses.dash === "none" || view.uses.dash === ""), JSON.stringify(view.uses));
  check("graph: spawned is a dashed line with a plus", view.spawned && view.spawned.dash && view.spawned.dash !== "none" && view.spawned.plus, JSON.stringify(view.spawned));
  check("graph: each of uses and spawned has a tag with its reason", ["uses", "spawned"].every(w => view.tags.some(t => t.word === w && /: .{5,}/.test(t.label || ""))), JSON.stringify(view.tags));
  check("graph: no node is only a colour (a word and a label go with it)", view.bare === 0, "bare " + view.bare);
  await shot("graph-overview-1280.png");

  // every node opens the right chat or page
  const nodes = JSON.parse(await run(`JSON.stringify([...document.querySelectorAll('[data-sgnode]')].map(b => ({ id: b.dataset.sgnode, k: b.dataset.sgk, r: b.dataset.sgr })))`));
  const seen = new Set();
  const landed = JSON.stringify;
  for (const n of nodes) {
    const key = n.id.split(":")[0] + ":" + n.k;
    if (n.k === "none" || seen.has(key)) continue;
    seen.add(key);
    await toGraph();
    await run(`(() => { window.__a5pane = null; const keep = window.shadowOpenSessionPane; window.shadowOpenSessionPane = function (sid) { window.__a5pane = sid; return keep.apply(this, arguments); };
      document.querySelector('[data-sgnode="' + ${JSON.stringify(n.id)} + '"]').click(); window.shadowOpenSessionPane = keep; })()`);
    await sleep(900);
    const at = JSON.parse(await run(`JSON.stringify({ screen: S.screen, sel: S.shadowTaskSel, chat: S.shadowChat, goal: S.goalSel, org: (typeof o2S === 'function' ? o2S().sel : null), pane: window.__a5pane })`));
    let ok = false;
    if (n.k === "task") ok = at.screen === "shadow" && at.sel === n.r;
    else if (n.k === "conversation") ok = at.screen === "shadow" && at.chat === n.r;
    else if (n.k === "goal") ok = at.screen === "goal" && at.goal === n.r;
    else if (n.k === "dept_page") ok = at.screen === "org2" && at.org === n.r;
    else if (n.k === "session") ok = at.pane === n.r;
    check("graph: a " + n.id.split(":")[0] + " node (" + n.k + ") opens its " + (n.k === "dept_page" ? "department page" : n.k === "goal" ? "goal" : n.k === "session" ? "worker chat" : "chat"), ok, landed(at));
  }

  // ---- 3. the Details jump from the Shadow chat strip ------------------------------------------------------------------------
  await home();
  await run(`shadowRouteDeepLink('sutra://shadow/' + ${JSON.stringify(R.task_use)})`);
  const strip = await waitFor(`!!document.querySelector('[data-shdetail="' + ${JSON.stringify(R.task_use)} + '"]')`, 15000);
  check("chat: the Shadow chat strip has a Details button for the task", strip);
  if (strip) await run(`document.querySelector('[data-shdetail="' + ${JSON.stringify(R.task_use)} + '"]').click()`);
  const detail = await waitFor(`S.screen === 'shadowgraph' && S.shadowGraphFocus === ${JSON.stringify(R.task_use)} && document.querySelectorAll('.sgsec').length >= 5`, 20000);
  check("detail: Details lands on the task's screen", detail);
  const secs = JSON.parse(await run(`JSON.stringify([...document.querySelectorAll('.sgsec h3')].map(h => h.textContent.trim()))`));
  for (const s of ["Decision", "Departments", "Chats", "Costs", "Timeline"]) check("detail: the " + s + " section is there", secs.includes(s), JSON.stringify(secs));
  const dtext = await run(`document.querySelector('.sgfocus') ? document.querySelector('.sgfocus').innerText : ''`);
  check("detail: the decision names Billing and its reason", /Used Billing/.test(dtext) && /Billing files the invoices/.test(dtext), (dtext || "").slice(0, 200));
  await shot("graph-focus-1280.png");

  check("walk: no script exception in the app", exceptions.length === 0, exceptions.slice(0, 2).join(" | "));
  // ---- 4. screenshots at 390 and the J2 page of default, organic and root ---------------------------------------------------
  await viewport(NARROW);
  await run(`render()`);
  await waitFor(`window.innerWidth === 390 && !!document.querySelector('.sgfocus')`, 10000);
  await shot("graph-focus-390.png");
  await run(`S.shadowGraphFocus = null; sgSetFocus(null); sgReset(); openScreen('shadowgraph'); render()`);
  await waitFor(`document.querySelectorAll('[data-sgnode]').length > 1 && !document.querySelector('.sgfocus')`, 15000);
  const phone = JSON.parse(await run(`JSON.stringify({ nodes: document.querySelectorAll('[data-sgnode]').length, small: [...document.querySelectorAll('[data-sgnode]')].filter(b => b.getBoundingClientRect().height < 44).length, over: document.documentElement.scrollWidth > window.innerWidth + 1 })`));
  check("phone: the graph is a list of 44 px targets with no sideways scroll", phone.nodes > 1 && phone.small === 0 && !phone.over, JSON.stringify(phone));
  await shot("graph-overview-390.png");
  for (const kind of ["default", "organic", "root"]) {
    for (const vp of [BIG, SMALL]) {
      await viewport(vp);
      await send("Page.navigate", { url: BASE + "/j2ui/" + R[kind] + "/" });
      await waitFor(`document.readyState === 'complete' && !!document.querySelector('#sprog') && document.querySelector('#sprog').children.length > 0`, 25000);
      await sleep(1000);
      await shot("j2-" + kind + "-" + vp.tag + ".png");
    }
  }
  const bad = results.filter(r => !r.ok).length;
  console.log(results.length - bad + " passed, " + bad + " failed");
  ws.close();
  done(bad ? 1 : 0);
})().catch(e => { console.log("walk crashed: " + e.message); process.exit(1); });
