#!/usr/bin/env node
/* The J2 page in a real browser: headless Chrome of its own over the DevTools protocol (raw CDP on node's global WebSocket; there
   is no playwright or puppeteer here). It looks, clicks and counts, and writes screenshots; it changes nothing on the server but
   what the page's own polling reads.
     usage: node qa/walks/shot-j2.js <out-dir> <base-url> <dept-ref> [kind]
       out-dir   where the PNGs go (design/j2ui)
       base-url  the app, e.g. http://127.0.0.1:8362
       dept-ref  a department of kind website on the engine runtime (qa/walks/j2ui-e2e.sh seeds them)
       kind      start | question | building | ready | hostile (default ready): which screens to take and which claims to make
     and, to compare the page's structure with the prototype's own (design/j2ui/STRUCTURE.md):
            node qa/walks/shot-j2.js <out-dir> <base-url> <page-path> outline <label>
       writes <out-dir>/outline-<label>.json: the DOM outline (tag, id, classes; no text) of the Simple and the Detailed view of the page
       at <page-path> (/j2ui/<ref>/ here, /?run=<id> on the prototype's server) at 1280x900
     and, to compare what the eye sees (not only the markup) on the start screen with the prototype's own:
            node qa/walks/shot-j2.js <out-dir> <base-url> <page-path> layout <label>
       writes <out-dir>/layout-<label>.json and layout-<label>.png: the computed style, text and right edge of the placeholder the
       preview frame shows while nothing is built (the server answers it, so the page cannot differ but the adapter can), and the
       layout box (x, y, width, height) of every element of the Simple view, at 1280x900
     env: SHOT_PORT=<n> the DevTools port (default 9361); CHROME=<path> the browser (default: Google Chrome on this Mac).
   Phase 1, the page directly, at 1280x900 and at 390x844 (mobile): the Simple view and, for ready and hostile, the Detailed view:
     zero exceptions and zero console errors (a Content Security Policy violation is a console error, so this proves the page
     needs nothing the policy forbids), the rail walked (Map, Chat, Internals, each of the 16 tabs: the pane is visible and its
     text says no undefined or NaN), the Map's cards on the phone.
   Phase 2, in the app (ready): the department opens in exactly one iframe at /j2ui/<ref>/ with no sandbox attribute, titled
     J2 Department, under the bar with the On/Off switch and Settings and records; Settings and records shows the classic list
     with a Department view row and none of Chat, Map, Board, Agent activity; a function's Settings has the Instructions (S16);
     the way back is the page.
   Phase 3 (hostile): nothing the department holds runs: window.__xss is undefined in the page and in the host.
   Exit 0 when every claim held, 1 otherwise; each claim is printed as PASS or FAIL. */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

const OUT = process.argv[2];
const BASE = (process.argv[3] || "").replace(/\/$/, "");
const REF = process.argv[4];
const KIND = process.argv[5] || "ready";
const LABEL = process.argv[6] || "page";
if (!OUT || !BASE || !REF) { console.log("usage: node shot-j2.js <out-dir> <base-url> <dept-ref> [start|question|building|ready|hostile]"); process.exit(2); }
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = Number(process.env.SHOT_PORT || 9361);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const get = url => new Promise((res, rej) => http.get(url, r => { let b = ""; r.on("data", d => b += d); r.on("end", () => res(b)); }).on("error", rej));
const TABS = ["preview", "goal", "workflows", "conflicts", "timeline", "audit", "charter", "docs", "artifacts", "board", "style", "lessons",
  "playbooks", "report", "rundetails", "runsettings"];
const VIEWPORTS = [{ w: 1280, h: 900, mobile: false, tag: "1280" }, { w: 390, h: 844, mobile: true, tag: "390" }];
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok }); console.log((ok ? "PASS " : "FAIL ") + name + (ok || !detail ? "" : "  -- " + detail)); };

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "shot-j2-"));
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
  let id = 0; const waiting = {}; const attached = [];
  const events = { exceptions: [], consoleErrors: [], logErrors: [], cspViolations: [] };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && waiting[m.id]) { waiting[m.id](m); delete waiting[m.id]; return; }
    if (m.method === "Target.attachedToTarget") { attached.push(m.params); return; }
    if (m.method === "Target.detachedFromTarget") { const i = attached.findIndex(a => a.sessionId === m.params.sessionId); if (i >= 0) attached.splice(i, 1); return; }
    if (m.sessionId) return;                                        // an event of a frame in a process of its own: not the page's
    if (m.method === "Runtime.exceptionThrown") {
      const d = m.params.exceptionDetails || {};
      events.exceptions.push(((d.exception && d.exception.description) || d.text || "exception") + " @" + (d.url || ""));
    } else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
      events.consoleErrors.push((m.params.args || []).map(a => a.value || a.description || "").join(" "));
    } else if (m.method === "Log.entryAdded" && m.params.entry.level === "error") {
      const e = m.params.entry, text = (e.text || "") + " " + (e.url || "");
      if (/Content Security Policy/i.test(text)) events.cspViolations.push(text);
      // a stylesheet from a host outside the app (the prototype's own web fonts) and the browser's own look for a favicon are not the page's
      else if (/favicon\.ico/.test(e.url || "") || (e.url && !e.url.startsWith(BASE))) { /* not the page's */ }
      else events.logErrors.push(text);
    }
  };
  const send = (method, params, sessionId) => new Promise(res => { const i = ++id; waiting[i] = res; ws.send(JSON.stringify(Object.assign({ id: i, method, params: params || {} }, sessionId ? { sessionId } : {}))); });
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
    await sleep(500);
    const r = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.result.data, "base64"));
    console.log("saved " + name + " " + fs.statSync(path.join(OUT, name)).size + " bytes");
  };
  const viewport = vp => send("Emulation.setDeviceMetricsOverride", { width: vp.w, height: vp.h, deviceScaleFactor: 1, mobile: !!vp.mobile });
  const clear = () => { events.exceptions.length = events.consoleErrors.length = events.logErrors.length = events.cspViolations.length = 0; };
  const quiet = (name) => {
    check(name + ": no exception", events.exceptions.length === 0, events.exceptions.slice(0, 2).join(" | "));
    check(name + ": no console error", events.consoleErrors.length + events.logErrors.length === 0, events.consoleErrors.concat(events.logErrors).slice(0, 2).join(" | "));
    check(name + ": no Content Security Policy violation", events.cspViolations.length === 0, events.cspViolations.slice(0, 1).join(" | "));
  };
  const load = async (url, vp) => {
    clear();
    await viewport(vp);
    await send("Page.navigate", { url });
    await waitFor(`document.readyState === 'complete' && !!document.querySelector('#sprog') && document.querySelector('#sprog').children.length > 0`, 25000);
    await sleep(1200);                                              // the first poll has drawn
  };
  const BAD = "\\b(undefined|NaN)\\b";

  await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");

  // ---- the outline of the page's structure, for design/j2ui/STRUCTURE.md ------------------------------------------------
  if (KIND === "outline") {
    const OUTLINE = `(() => {
      // a class the page toggles with its data (the Needs you strip is "on" while a question waits) is state, not structure
      const STATE = new Set(["on", "has-links", "flash", "hot", "dim"]);
      const sig = e => { const c = [...e.classList].filter(x => !STATE.has(x)).sort(); return e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (c.length ? "." + c.join(".") : ""); };
      const data = e => /^(smsgs|msgs|needs|sprog|lanes|steps|quick|waiting|typing|reportbody|dbody|dtitle|doclinks|ver|outsel|runsel)$/.test(e.id) || /^pane-/.test(e.id);
      const vocab = e => { const s = new Set(); e.querySelectorAll("*").forEach(x => { if (!/^(script|style)$/i.test(x.tagName)) s.add(sig(x).replace(/#[^.\s]+/, "")); }); return [...s].sort(); };
      const walk = (e, d, lines) => {
        lines.push("  ".repeat(d) + sig(e));
        if (data(e)) { const v = vocab(e); if (v.length) lines.push("  ".repeat(d + 1) + "~ " + v.join(", ")); return; }
        [...e.children].filter(c => !/^(script|style)$/i.test(c.tagName)).forEach(c => walk(c, d + 1, lines));
      };
      const of = id => { const lines = [], r = document.getElementById(id); if (r) walk(r, 0, lines); return lines; };
      return { simple: of("sview"), detail: of("dview") };
    })()`;
    await viewport({ w: 1280, h: 900, mobile: false });
    await send("Page.navigate", { url: BASE + REF + (REF.includes("?") ? "&" : "?") + "view=detail" });
    await waitFor(`document.readyState === 'complete' && !!document.querySelector('#sprog') && document.querySelector('#sprog').children.length > 0`, 25000);
    await sleep(2000);
    const out = await run(OUTLINE);
    fs.writeFileSync(path.join(OUT, "outline-" + LABEL + ".json"), JSON.stringify(out, null, 1));
    console.log("saved outline-" + LABEL + ".json: " + out.simple.length + " simple lines, " + out.detail.length + " detailed lines");
    ws.close();
    done(0);
    return;
  }

  // ---- the start screen as drawn: the placeholder the server answers and the layout box of every element ----------------------
  // The outline above compares markup; this compares what is drawn. The right-hand pane of a start screen is an iframe on
  // site/latest, which the SERVER answers (the page cannot differ, the adapter can). The app answers it with the sandbox header
  // (website_api.SAFE), so the frame is a foreign origin to the page (and Chrome puts it in a process of its own): its computed
  // style is read over the protocol, in the frame's own session, not through contentDocument. The prototype's frame is
  // same-origin and is read through the page. The function below runs in whichever window holds the placeholder.
  if (KIND === "layout") {
    const PLACEHOLDER = `(win => {
      const document = win.document, p = document.querySelector('p');
      if (!p) return null;
      const cs = win.getComputedStyle(p), bs = win.getComputedStyle(document.body);
      let right = null;
      if (p.firstChild) { const r = document.createRange(); r.selectNodeContents(p); right = Math.round(r.getBoundingClientRect().right * 10) / 10; }
      if (!right) return null;                                      // not laid out (a frame the page has already replaced)
      return { text: p.textContent, fontSize: cs.fontSize, fontFamily: cs.fontFamily, fontWeight: cs.fontWeight, color: cs.color, padding: cs.padding,
        margin: cs.margin, lineHeight: cs.lineHeight, bodyMargin: bs.margin, mode: document.compatMode, textRight: right };
    })`;
    const BOXES = `(async () => {
      await document.fonts.ready;
      const q = n => Math.round(n * 10) / 10, boxes = {}, seen = {};
      const sig = e => { const c = [...e.classList].sort(); return e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (c.length ? "." + c.join(".") : ""); };
      const visit = (e, at) => {
        const k = at + "/" + sig(e), n = seen[k] = (seen[k] || 0) + 1, key = k + "[" + n + "]", r = e.getBoundingClientRect();
        boxes[key] = [q(r.x), q(r.y), q(r.width), q(r.height)];
        [...e.children].filter(c => !/^(script|style)$/i.test(c.tagName)).forEach(c => visit(c, key));
      };
      visit(document.getElementById('sview'), '');
      return { boxes, viewport: [innerWidth, innerHeight], bodyClass: document.body.className, cards: document.querySelectorAll('#smsgs .cards button').length };
    })()`;
    const placeholderNow = async () => {
      try { const same = await run(`(() => { try { return JSON.stringify((${PLACEHOLDER})(document.getElementById('sframe').contentWindow)); } catch (e) { return null; } })()`);
        if (same && same !== "null") return JSON.parse(same); } catch (e) {}
      for (const t of attached.filter(a => a.targetInfo && a.targetInfo.type === "iframe").reverse()) {
        const r = await send("Runtime.evaluate", { expression: `JSON.stringify((${PLACEHOLDER})(window))`, returnByValue: true }, t.sessionId);
        const v = r.result && r.result.result && r.result.result.value;
        if (v && v !== "null") return JSON.parse(v);
      }
      return null;
    };
    await send("Target.setAutoAttach", { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });
    await viewport({ w: 1280, h: 900, mobile: false });
    await send("Page.navigate", { url: BASE + REF + (REF.includes("?") ? "&" : "?") + "view=simple" });
    await waitFor(`document.readyState === 'complete' && !!document.querySelector('#sprog') && document.querySelector('#sprog').children.length > 0`, 25000);
    let placeholder = null;
    for (let i = 0; i < 60 && !placeholder; i++) { await sleep(250); placeholder = await placeholderNow(); }
    await sleep(1500);                                              // the page reloads the frame once when its first state arrives
    placeholder = (await placeholderNow()) || placeholder;
    const out = Object.assign(await run(BOXES), { placeholder });
    fs.writeFileSync(path.join(OUT, "layout-" + LABEL + ".json"), JSON.stringify(out, null, 1));
    const r = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(OUT, "layout-" + LABEL + ".png"), Buffer.from(r.result.data, "base64"));
    console.log("saved layout-" + LABEL + ".json: " + Object.keys(out.boxes).length + " boxes, placeholder " + (placeholder ? placeholder.fontSize + " " + placeholder.color + ", text ends at " + placeholder.textRight : "MISSING"));
    ws.close();
    done(placeholder ? 0 : 1);
    return;
  }

  // ---- phase 1: the page directly ---------------------------------------------------------------------------------------
  const page = BASE + "/j2ui/" + encodeURIComponent(REF) + "/";
  for (const vp of VIEWPORTS) {
    const label = KIND + " " + vp.tag;
    await load(page + "?view=simple", vp);
    const simple = JSON.parse(await run(`JSON.stringify({ simple: document.body.classList.contains('simple'), msgs: document.getElementById('smsgs').innerText.length,
      examples: document.querySelectorAll('#smsgs .cards button').length, opts: document.querySelectorAll('#smsgs .opts button').length,
      ready: !!document.querySelector('#smsgs .ready'), bad: new RegExp(${JSON.stringify(BAD)}).test(document.getElementById('smsgs').innerText),
      title: document.title, stages: document.getElementById('sprog').children.length })`));
    check(label + ": the Simple view is shown, titled J2 Department, with its five stages", simple.simple && simple.title === "J2 Department" && simple.stages === 5, JSON.stringify(simple));
    check(label + ": the Simple view says no undefined or NaN", !simple.bad);
    if (KIND === "start") check(label + ": the start screen offers its example briefs", simple.examples >= 3 && simple.msgs > 0, JSON.stringify(simple));
    if (KIND === "question") check(label + ": the question has its option buttons", simple.opts >= 2, JSON.stringify(simple));
    if (KIND === "ready") check(label + ": the ready card is there", simple.ready, JSON.stringify(simple));
    if (KIND === "building") {
      const lock = JSON.parse(await run(`JSON.stringify({ box: document.getElementById('sbox').disabled, send: document.getElementById('ssend').disabled, status: document.getElementById('sstatus').innerText })`));
      check(label + ": while work runs and nothing waits on the owner the composer is locked and the page says what is being built", lock.box && lock.send && /^Building|^Planning|^Checking/.test(lock.status), JSON.stringify(lock));
    }
    if (["start", "question", "building", "ready"].includes(KIND)) await shot(`simple-${KIND}-${vp.tag}.png`);
    quiet(label + " simple");

    if (KIND !== "ready" && KIND !== "hostile") continue;
    await load(page + "?view=detail", vp);
    const detail = JSON.parse(await run(`JSON.stringify({ detail: !document.body.classList.contains('simple'),
      map: !document.getElementById('pane-map').hidden, mapcards: document.querySelectorAll('#pane-map .mapcards').length,
      mapsvg: document.querySelectorAll('#pane-map .mapsvg').length, chat: document.querySelectorAll('#msgs .msg').length })`));
    check(label + ": the Detailed view opens on the Map", detail.detail && detail.map && detail.mapsvg > 0, JSON.stringify(detail));
    if (vp.mobile) check(label + ": the phone's Map is the card list", detail.mapcards > 0, JSON.stringify(detail));
    if (KIND === "ready") await shot(`detail-map-${vp.tag}.png`);
    // the rail: Map, Chat, Internals, each of the 16 tabs
    const walk = JSON.parse(await run(`(() => {
      const out = [], bad = new RegExp(${JSON.stringify(BAD)});
      const click = sel => { const b = document.querySelector(sel); if (!b) return false; b.click(); return true; };
      out.push(["map", click('.rail [data-tab="map"]') && !document.getElementById('pane-map').hidden, bad.test(document.getElementById('pane-map').innerText)]);
      out.push(["chat", click('#gochat') && document.body.classList.contains('simple'), false]);
      click('#internals');
      out.push(["internals", !document.getElementById('railsub').hidden, false]);
      ${JSON.stringify(TABS)}.forEach(t => {
        const b = document.querySelector('.rail [data-tab="' + t + '"]');
        if (!b || b.hidden) { out.push([t, "skipped", false]); return; }
        b.click();
        const p = document.getElementById('pane-' + t);
        out.push([t, !!p && !p.hidden && document.body.classList.contains('simple') === false, bad.test(p ? p.innerText : '')]);
      });
      return JSON.stringify(out); })()`));
    for (const [t, shown, bad] of walk) {
      if (shown === "skipped") { console.log("skip  " + label + " tab " + t + " (not on this department: its button is hidden)"); continue; }
      check(label + ": tab " + t + " is shown and says no undefined or NaN", shown && !bad, "shown=" + shown + " bad=" + bad);
    }
    check(label + ": all 16 tabs were walked or are hidden by the page", walk.filter(w => w[1] !== "skipped").length >= 14);
    if (KIND === "ready" && !vp.mobile) {                  // the tabs the owner's sign-off list points at (design/PRD-FIVE-FUNCTIONS-J2UI.md)
      for (const t of ["runsettings", "rundetails", "report", "style", "lessons", "playbooks", "charter", "preview", "audit", "docs", "artifacts", "conflicts"]) {
        await run(`document.querySelector('.rail [data-tab="${t}"]').click()`);
        await shot(`detail-${t}-${vp.tag}.png`);
      }
      // a work atom's card, opened: its prompt, reply and tokens are what the page prints for an atom that has them
      await run(`(() => { document.querySelector('.rail [data-tab="workflows"]').click(); const d = document.querySelector('#pane-workflows details'); if (!d) return 0;
        d.open = true; d.scrollIntoView(); [...d.querySelectorAll('details')].slice(0, 1).forEach(x => { x.open = true; }); return 1; })()`);
      await shot(`detail-atoms-${vp.tag}.png`);
    }
    if (KIND === "ready" && !vp.mobile) {
      await run(`document.querySelector('.rail [data-tab="workflows"]').click()`);
      await shot(`detail-workflows-${vp.tag}.png`);
    } else if (KIND === "ready") {
      await run(`document.querySelector('.rail [data-tab="workflows"]') ? (document.getElementById('internals').click(), document.querySelector('.rail [data-tab="workflows"]').click()) : 0`);
      await shot(`detail-workflows-${vp.tag}.png`);
    }
    // a message of an agent opens its dialog
    await run(`(() => { document.querySelector('.rail [data-tab="map"]').click(); return 1; })()`);
    const dlg = JSON.parse(await run(`(async () => { const m = [...document.querySelectorAll('#msgs .msg')].find(x => !x.classList.contains('user'));
      if (!m) return JSON.stringify({ none: true }); m.click(); await new Promise(r => setTimeout(r, 400));
      const d = document.getElementById('detail'); return JSON.stringify({ open: d.open, text: d.innerText.length, bad: new RegExp(${JSON.stringify(BAD)}).test(d.innerText) }); })()`));
    check(label + ": an agent's message opens its dialog, which says no undefined or NaN", !dlg.none && dlg.open && dlg.text > 20 && !dlg.bad, JSON.stringify(dlg));
    if (KIND === "ready") await shot(`detail-chat-${vp.tag}.png`);
    await run(`document.getElementById('dclose').click()`);
    if (KIND === "hostile") {
      // every agent's message, one after the other
      const all = JSON.parse(await run(`(async () => { let n = 0; for (const m of [...document.querySelectorAll('#msgs .msg')].filter(x => !x.classList.contains('user'))) {
        m.click(); await new Promise(r => setTimeout(r, 40)); n++; document.getElementById('dclose').click(); } return JSON.stringify({ n, xss: String(window.__xss) }); })()`));
      check(label + ": every agent message of the hostile department was opened and nothing ran", all.n > 3 && all.xss === "undefined", JSON.stringify(all));
    }
    quiet(label + " detail");
  }

  // ---- phase 2: in the app ----------------------------------------------------------------------------------------------
  if (KIND === "ready" || KIND === "hostile") {
    const vp = { w: 1440, h: 900, mobile: false, tag: "1440" };
    clear();
    await viewport(vp);
    await send("Page.navigate", { url: BASE + "/" });
    await waitFor(`typeof o2Select === 'function' && typeof goDest === 'function' && typeof S !== 'undefined'`, 30000);
    await sleep(1500);
    const opened = await run(`(async () => {
      const REF = ${JSON.stringify(REF)};
      goDest('org'); if (S.screen !== 'org2') openScreen('org2');
      if (typeof loadOrg2 === 'function') await loadOrg2(true);
      const d = await (await fetch('/api/native/depts')).json();
      const o = o2S(); let r = REF; const seen = new Set();
      while (r && !seen.has(r)) { seen.add(r); if (o.expanded) o.expanded.add(r);
        const dom = (typeof DOMAINS !== 'undefined' ? DOMAINS : []).filter(x => x.ref === r)[0]; const dep = d.depts.filter(x => x.ref === r)[0];
        r = (dom && dom.parent_ref) || (dep && dep.parent) || null; }
      await wbLoadRefs(); o2Select(REF); await wbLoadMap(REF, true);
      delete S.wb.tab[REF]; dpRender();
      for (let i = 0; i < 40 && !(j2vOn(REF) && document.querySelector('.j2vbar')); i++) { await new Promise(r => setTimeout(r, 250)); dpRender(); }
      return JSON.stringify({ tab: wbTab(REF), on: j2vOn(REF), bar: !!document.querySelector('.j2vbar') });
    })()`);
    console.log("opened " + opened);
    const framed = await waitFor(`document.querySelectorAll('iframe.j2v-if').length === 1 && !!document.querySelector('iframe.j2v-if').contentDocument
      && document.querySelector('iframe.j2v-if').contentDocument.getElementById('sprog') && document.querySelector('iframe.j2v-if').contentDocument.getElementById('sprog').children.length > 0`, 30000);
    check("app: the department opens in a frame", framed, opened);
    await sleep(1200);
    const fr = JSON.parse(await run(`(() => { const f = document.querySelectorAll('iframe.j2v-if'), a = f[0];
      const bar = document.querySelector('.j2vbar');
      return JSON.stringify({ n: f.length, src: a && a.getAttribute('src'), sandbox: a && a.getAttribute('sandbox'), title: a && a.contentDocument && a.contentDocument.title,
        host: !!a && !a.parentNode.hidden, onoff: !!bar && !!bar.querySelector('[data-wbstop],[data-wbresume]'),
        records: !!bar && /Settings and records/.test(bar.textContent), xss: String(window.__xss), inner: a && String(a.contentWindow.__xss) }); })()`));
    check("app: exactly one iframe, at /j2ui/<ref>/", fr.n === 1 && fr.src === "/j2ui/" + REF + "/", JSON.stringify(fr));
    check("app: the frame has no sandbox attribute and holds the page titled J2 Department", fr.sandbox === null && fr.title === "J2 Department" && fr.host, JSON.stringify(fr));
    check("app: the bar has the On/Off switch and Settings and records", fr.onoff && fr.records, JSON.stringify(fr));
    check("app: nothing ran in the host or in the frame", fr.xss === "undefined" && fr.inner === "undefined", JSON.stringify(fr));
    if (KIND === "ready") await shot("app-j2view-1440.png");
    if (KIND === "ready") {
      await run(`document.querySelector('.j2vbar [data-wbtab="records"]').click()`);
      await sleep(800);
      const rec = JSON.parse(await run(`(() => { const rows = [...document.querySelectorAll('.o2li.dpli span')].map(s => s.textContent.trim());
        const f = document.querySelector('iframe.j2v-if'); return JSON.stringify({ rows, dv: rows.includes('Department view'),
          none: ['Chat', 'Map', 'Board', 'Agent activity'].filter(x => rows.includes(x)), fn: !!document.querySelector('[data-dptab="identity"]'),
          frameHidden: !f || f.parentNode.hidden || f.getBoundingClientRect().width === 0 }); })()`));
      check("app: Settings and records shows the classic list with a Department view row and none of Chat, Map, Board, Agent activity",
        rec.dv && rec.none.length === 0 && rec.fn, JSON.stringify(rec));
      check("app: the page's frame is out of the way in records mode", rec.frameHidden, JSON.stringify(rec));
      await shot("app-records-1440.png");
      await run(`document.querySelector('[data-dptab="identity"]').click()`);
      await sleep(600);
      await run(`(() => { const b = document.querySelector('[data-dppane="settings"]'); if (b) b.click(); return !!b; })()`);
      await sleep(600);
      const s16 = JSON.parse(await run(`JSON.stringify({ ins: document.querySelectorAll('.wbins').length, change: document.querySelectorAll('.wbins [data-wbinschange],.wbins button').length })`));
      check("app: a function's Settings has its typed Instructions (S16 is reachable)", s16.ins >= 1, JSON.stringify(s16));
      await run(`document.querySelector('[data-wbtab="j2"]').click()`);
      await sleep(800);
      const back = JSON.parse(await run(`(() => { const f = document.querySelector('iframe.j2v-if'); return JSON.stringify({ n: document.querySelectorAll('iframe.j2v-if').length,
        shown: !!f && !f.parentNode.hidden && f.getBoundingClientRect().width > 300 }); })()`));
      check("app: the way back is the page, still one frame", back.n === 1 && back.shown, JSON.stringify(back));
    }
    quiet("app " + KIND);
  }
  if (KIND === "hostile") {
    const x = await run(`String(window.__xss)`);
    check("hostile: window.__xss is undefined in the host at the end", x === "undefined", x);
  }

  const failed = results.filter(r => !r.ok);
  console.log("\n" + (results.length - failed.length) + " of " + results.length + " claims held for " + KIND + (failed.length ? "; FAILED: " + failed.map(f => f.name).join(" | ") : ""));
  ws.close();
  done(failed.length ? 1 : 0);
})().catch(e => { console.log("failed: " + (e && e.message || e)); process.exit(1); });
