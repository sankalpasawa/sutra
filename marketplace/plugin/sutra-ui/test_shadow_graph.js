#!/usr/bin/env node
/* test_shadow_graph.js -- the Shadow graph screen (amendment A5, A5.2.3 to A5.2.5), in a vm harness.
 *
 * Covers: the states; the sample's nodes and shapes; `uses` and `spawned` differing by dash class and tag text and carrying the reason;
 * each node's open path with the right ids; the keyboard; the Details jump; the ticker's lifecycle; a focused node surviving a patch;
 * the phone list; shadowHomeOnScreen.
 * Run: node test_shadow_graph.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const SAMPLE = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "shadow_graph_sample.json"), "utf8"));
let n = 0, failed = 0;
function test(name, fn){
  try { fn(); console.log("ok   " + (++n) + " " + name); }
  catch (e){ failed++; console.log("FAIL " + name + "\n" + (e && e.stack || e)); }
}
async function atest(name, fn){
  try { await fn(); console.log("ok   " + (++n) + " " + name); }
  catch (e){ failed++; console.log("FAIL " + name + "\n" + (e && e.stack || e)); }
}

function boot(opts){
  opts = opts || {};
  const calls = [];
  const rec = (name) => (...a) => { calls.push([name].concat(a)); };
  const handlers = {};
  const timers = [];
  const clock = { t: 5000000 };
  function FakeDate(...a){ return new Date(...a); }
  FakeDate.now = () => clock.t; FakeDate.parse = Date.parse; FakeDate.UTC = Date.UTC;
  const fetches = [];
  const ctx = {
    console, Date: FakeDate, clock, calls, handlers, timers, fetches, Promise,
    setTimeout: (f) => f, setInterval: (fn, ms) => { const h = { fn, ms, cleared: false }; timers.push(h); return h; },
    clearInterval: (h) => { if (h) h.cleared = true; },
    S: { screen: "shadowgraph", ui: {} }, SCREENS: {}, TITLES: {},
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;"),
    scheduleRender: rec("scheduleRender"), render: rec("render"),
    goDest: rec("goDest"), openScreen: rec("openScreen"), lsSet: rec("lsSet"), lsGet: (k, d) => (opts.ls && opts.ls[k]) || d,
    openGoal: rec("openGoal"), loadShadowHome: rec("loadShadowHome"),
    window: { innerWidth: opts.width || 1200, addEventListener(){} },
    document: {
      addEventListener(t, f){ (handlers[t] = handlers[t] || []).push(f); },
      createElement(){ return { setAttribute(){}, dataset: {} }; },
      querySelector(sel){ calls.push(["querySelector", sel]); return opts.focusEl || null; },
      body: { appendChild(){} }, activeElement: null,
    },
    fetch: (url) => {
      fetches.push(url);
      if (opts.fetch) return opts.fetch(url);
      return Promise.resolve({ ok: true, status: 200, json: async () => SAMPLE.graph });
    },
  };
  ctx.__SHADOW_NO_AUTOBOOT = true;
  vm.createContext(ctx);
  for (const f of ["15-shadow-overlay.js", "16-shadow-home.js", "27-shadow-graph.js"])
    vm.runInContext(fs.readFileSync(path.join(JS, f), "utf8"), ctx, { filename: f });
  // the calls the open paths make are recorded rather than performed
  ["shadowOpenSessionPane", "loadShadowHome"].concat(opts.realLink ? [] : ["shadowRouteDeepLink"]).forEach(k => { ctx[k] = rec(k); });
  return ctx;
}
const flush = () => new Promise(r => setImmediate(r));
function fire(ctx, type, target, extra){
  const ev = Object.assign({ type, target, key: "", preventDefault(){ ev.prevented = true; } }, extra || {});
  (ctx.handlers[type] || []).forEach(h => h(ev));
  return ev;
}
const btn = (attrs, parent) => ({ dataset: attrs, parentNode: parent || null });
const html = (ctx) => ctx.SCREENS.shadowgraph();
async function loaded(ctx, body){
  if (body) ctx.fetch = (u) => { ctx.fetches.push(u); return Promise.resolve({ ok: true, status: 200, json: async () => body }); };
  ctx.SCREENS.shadowgraph();
  await flush(); await flush();
  return html(ctx);
}

(async () => {
  await atest("loading: a skeleton with the words, before any read lands", async () => {
    const ctx = boot({ fetch: () => new Promise(() => {}) });
    const h = html(ctx);
    assert.ok(/Reading Shadow's tasks/.test(h) && /aria-busy="true"/.test(h));
  });

  await atest("empty: says what to do and offers Home", async () => {
    const ctx = boot();
    const h = await loaded(ctx, { nodes: [SAMPLE.graph.nodes[0]], edges: [], as_of: "2026-10-29", focus: null, truncated: false, shadow_on: true });
    assert.ok(/No tasks yet\. Tell Shadow what you need on Home\./.test(h) && /data-sghome/.test(h));
  });

  await atest("dark: a 403 says Shadow is not enabled", async () => {
    const ctx = boot({ fetch: () => Promise.resolve({ ok: false, status: 403, json: async () => ({}) }) });
    await loaded(ctx);
    assert.ok(/Shadow is not enabled/.test(html(ctx)));
  });

  await atest("error with no graph: a plain message and Retry; with a graph: it keeps the graph, an amber note and Retry", async () => {
    const bad = boot({ fetch: () => Promise.resolve({ ok: false, status: 500, json: async () => ({}) }) });
    await loaded(bad);
    let h = html(bad);
    assert.ok(/Could not read Shadow's tasks/.test(h) && /data-sgretry/.test(h) && !/data-sgnode/.test(h));
    const ctx = boot();
    await loaded(ctx);
    ctx.fetch = () => Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
    ctx.sgLoad(true);
    await flush(); await flush();
    h = html(ctx);
    assert.ok(/data-sgnode/.test(h) && /Could not refresh\. Retrying/.test(h) && /data-sgretry/.test(h) && /sgnote warn/.test(h));
  });

  await atest("stale: 'Updated Ns ago' after a quiet while; the summary names what is working and waiting", async () => {
    const ctx = boot();
    let h = await loaded(ctx);
    assert.ok(!/Updated \d+s ago/.test(h));
    assert.ok(/1 working, 1 waiting on you/.test(h));
    ctx.clock.t += 30000;
    assert.ok(/Updated 30s ago/.test(html(ctx)));
  });

  await atest("the sample: every node is a button with an id, a shape of its kind, its status as a word and a glyph", async () => {
    const ctx = boot();
    const h = await loaded(ctx);
    SAMPLE.graph.nodes.forEach(nd => {
      assert.ok(h.indexOf('data-sgnode="' + nd.id + '"') > 0, "no button for " + nd.id);
      assert.ok(new RegExp("sgk-" + nd.kind + " sgs-" + nd.status).test(h), nd.id + " class");
    });
    assert.ok(/<button type="button" class="sgnode sgk-task sgs-working/.test(h));
    assert.ok(/Working/.test(h) && /Waiting/.test(h) && /sgglyph/.test(h), "status is a word and a glyph");
    assert.ok(/role="group" aria-label="Shadow graph"/.test(h));
    assert.ok(/aria-label="task: Fix the login bug, Working"/.test(h) && /aria-label="department: Billing, Idle"/.test(h));
    const shapes = new Set((h.match(/<svg class="sgshape"[^>]*>(.*?)<\/svg>/g) || []).map(s => s.replace(/\s+/g, " ")));
    assert.ok(shapes.size >= 6, "shape by kind");
    assert.ok(/<circle class="sgi"/.test(h), "the shadow has its inner dot");
    assert.ok(/<path class="sgo" d="M11 1\.5/.test(h), "the goal is a diamond");
    assert.ok(/pulse|sgs-working/.test(h));
  });

  await atest("uses and spawned differ by dash class and tag text, and carry the reason", async () => {
    const ctx = boot();
    const h = await loaded(ctx);
    assert.ok(/class="sgedge e-uses"/.test(h) && /class="sgedge e-spawned"/.test(h) && /e-held/.test(h));
    assert.ok(/class="sgplus"/.test(h), "the spawned line starts with a + marker");
    const tag = (kind) => new RegExp('class="sgtag t-' + kind + '"[^>]*>' + kind + '<');
    assert.ok(tag("uses").test(h) && tag("spawned").test(h) && /t-held"[^>]*>held</.test(h));
    const usesId = SAMPLE.graph.edges.find(e => e.kind === "uses" && !e.held).id;
    const spId = SAMPLE.graph.edges.find(e => e.kind === "spawned").id;
    fire(ctx, "mouseover", btn({ sgtag: usesId }));
    let t = html(ctx);
    assert.ok(/Billing already handles invoice and login-token questions/.test(t) && /Confidence: high/.test(t) && /decided by agent/.test(t));
    fire(ctx, "mouseover", btn({ sgtag: spId }));
    t = html(ctx);
    assert.ok(/No department covers recurring reports/.test(t) && /spawned/.test(t));
    const heldId = SAMPLE.graph.edges.find(e => e.held).id;
    fire(ctx, "mouseover", btn({ sgtag: heldId }));
    assert.ok(/by the rule: /.test(html(ctx)) && /Held: Collections is Off/.test(html(ctx)));
  });

  await atest("each node opens the right place with the right id", async () => {
    const ctx = boot();
    await loaded(ctx);
    const click = (nd) => { ctx.calls.length = 0; fire(ctx, "click", btn({ sgnode: nd.id, sgk: nd.open.kind, sgr: nd.open.ref || "" })); return ctx.calls; };
    const byKind = (k) => SAMPLE.graph.nodes.find(x => x.kind === k);
    let c = click(byKind("task"));
    assert.deepStrictEqual(c.find(x => x[0] === "shadowRouteDeepLink"), ["shadowRouteDeepLink", "sutra://shadow/" + byKind("task").open.ref]);
    c = click(byKind("conversation"));
    assert.strictEqual(ctx.S.shadowChat, "shc-a1b2c3");
    assert.strictEqual(ctx.S.shadowTaskSel, "__none__");
    assert.ok(c.some(x => x[0] === "lsSet" && x[1] === "sutra.shadow.conv" && x[2] === "shc-a1b2c3"));
    assert.ok(c.some(x => x[0] === "goDest" && x[1] === "focus") && c.some(x => x[0] === "openScreen" && x[1] === "shadow"));
    c = click(byKind("worker"));
    assert.deepStrictEqual(c.find(x => x[0] === "shadowOpenSessionPane"), ["shadowOpenSessionPane", "sess-0001"]);
    c = click(byKind("goal"));
    assert.deepStrictEqual(c.find(x => x[0] === "openGoal"), ["openGoal", "g-000000000001"]);
    c = click(byKind("task_chat"));
    assert.ok(c.some(x => x[0] === "shadowRouteDeepLink"), "the task chat opens its task");
    c = click(byKind("shadow"));
    assert.strictEqual(c.length, 0, "Shadow opens nothing");
    c = click(byKind("department"));
    assert.ok(c.some(x => x[0] === "goDest" && x[1] === "org"), "no o2OpenDept: the Org screen is the fallback");
    const seen = [];
    ctx.window.o2OpenDept = (ref) => seen.push(ref);
    c = click(byKind("department"));
    assert.deepStrictEqual(seen, [byKind("department").open.ref]);
    assert.ok(c.some(x => x[0] === "goDest" && x[1] === "org"), "the Org screen opens first: o2OpenDept only selects the row");
  });

  await atest("keyboard: roving tabindex, arrows follow edges and columns, space pins, f focuses, Escape leaves", async () => {
    const ctx = boot({ focusEl: { focus(){} } });
    const h = await loaded(ctx);
    const tab0 = (h.match(/tabindex="0"/g) || []).length;
    assert.strictEqual(tab0, 1, "exactly one node is in the tab order");
    const task = SAMPLE.graph.nodes.find(x => x.kind === "task").id;
    const key = (k, id) => fire(ctx, "keydown", btn({ sgnode: id || ctx.sgState().cur }, btn({ sghost: "1" })), { key: k });
    ctx.sgState().cur = task;
    key("ArrowRight");
    const first = SAMPLE.graph.edges.find(e => e.source === task).target;
    assert.strictEqual(ctx.sgState().cur, first, "Right: the first outgoing neighbour");
    key("ArrowLeft");
    assert.strictEqual(ctx.sgState().cur, SAMPLE.graph.edges.find(e => e.target === first).source, "Left: the incoming neighbour");
    ctx.sgState().cur = task;
    key("ArrowDown");
    const col = SAMPLE.graph.nodes.filter(x => x.col === 2).sort((a, b) => a.row - b.row);
    assert.strictEqual(ctx.sgState().cur, col[1].id, "Down: the next sibling in the column");
    key("ArrowUp");
    assert.strictEqual(ctx.sgState().cur, col[0].id);
    key(" ");
    assert.strictEqual(ctx.sgState().pin, col[0].id, "Space pins the tooltip");
    assert.ok(/role="tooltip"/.test(html(ctx)));
    key("i");
    assert.strictEqual(ctx.sgState().pin, null, "i toggles the pin");
    ctx.calls.length = 0;
    key("f");
    assert.strictEqual(ctx.S.shadowGraphFocus, col[0].id.slice(5), "f enters focus mode on the task");
    ctx.S.shadowGraphFocus = task.slice(5);
    key("Escape", task);
    assert.strictEqual(ctx.S.shadowGraphFocus, null, "Escape leaves focus mode");
    const ev = key("ArrowRight");
    assert.ok(ev.prevented);
  });

  await atest("Details jump: data-shdetail focuses the task and opens the screen; Home's missions are read once only when empty", async () => {
    const ctx = boot();
    ctx.S.screen = "shadow";
    fire(ctx, "click", btn({ shdetail: "m-00000000a001" }));
    assert.strictEqual(ctx.S.shadowGraphFocus, "m-00000000a001");
    assert.ok(ctx.calls.some(c => c[0] === "openScreen" && c[1] === "shadowgraph"));
    assert.strictEqual(ctx.calls.filter(c => c[0] === "loadShadowHome").length, 1);
    assert.deepStrictEqual(ctx.calls.find(c => c[0] === "loadShadowHome"), ["loadShadowHome", true]);
    ctx.calls.length = 0;
    ctx.S.shadowMissions = [{ id: "m-00000000a001" }];
    fire(ctx, "click", btn({ shdetail: "m-00000000a002" }));
    assert.strictEqual(ctx.calls.filter(c => c[0] === "loadShadowHome").length, 0);
    assert.ok(ctx.calls.some(c => c[0] === "lsSet" && c[1] === "sutra.shadow.graph" && c[2] === "m-00000000a002"));
    fire(ctx, "click", btn({ shgraph: "1" }));
    assert.strictEqual(ctx.S.shadowGraphFocus, null);
  });

  test("a chat finds its task: task chat session, Sutra id, or the chat it drives", () => {
    const ctx = boot();
    ctx.S.shadowMissions = [{ id: "m-1", task_chat_session: "sess-2", task_chat: "sutra-2", target_session: "sess-1" }];
    assert.strictEqual(ctx.sgMissionForSession({ id: "sess-2" }), "m-1");
    assert.strictEqual(ctx.sgMissionForSession({ id: "x", sutra_id: "sutra-2" }), "m-1");
    assert.strictEqual(ctx.sgMissionForSession({ id: "sess-1" }), "m-1");
    assert.strictEqual(ctx.sgMissionForSession({ id: "other" }), null);
    const src = fs.readFileSync(path.join(JS, "06-render.js"), "utf8");
    assert.ok(/data-shdetail="\$\{escAttr\(shDetailMid\)\}"/.test(src) && /S\.screen === "shadowgraph"\) && !bCol/.test(src), "the strip button and the wide list");
  });

  await atest("focus mode: the detail sections, Open and Open in Chats, and the focused graph", async () => {
    const ctx = boot({ ls: { "sutra.shadow.graph": "m-00000000a001" } });
    const h = await loaded(ctx, SAMPLE.detail);
    assert.strictEqual(ctx.S.shadowGraphFocus, "m-00000000a001", "restored from localStorage");
    assert.ok(ctx.fetches.some(u => u === "/api/shadow/graph/task/m-00000000a001"));
    ["Decision", "Departments", "Chats", "Workers", "Costs", "Timeline"].forEach(s => assert.ok(new RegExp("<h3>" + s + "</h3>").test(h), s));
    assert.ok(/Open in Chats/.test(h) && /Fix the login bug/.test(h) && /about \$0\.12/.test(h));
    assert.ok(/data-sgleave/.test(h) && /decided by agent/.test(h));
    assert.ok(!/charter|internal system|GRANT|COUNTER|REFUSE/i.test(h));
  });

  await atest("a task that is gone leaves its detail", async () => {
    const ctx = boot({ fetch: () => Promise.resolve({ ok: false, status: 404, json: async () => ({}) }) });
    ctx.S.shadowGraphFocus = "m-00000000a009";
    ctx.SCREENS.shadowgraph();
    await flush(); await flush();
    assert.strictEqual(ctx.S.shadowGraphFocus, null);
    assert.ok(ctx.calls.some(c => c[0] === "lsSet" && c[1] === "sutra.shadow.graph" && c[2] === null));
  });

  await atest("ticker: one interval, only on the screen, coalesced, cleared when the screen is left", async () => {
    const ctx = boot();
    ctx.SCREENS.shadowgraph(); ctx.SCREENS.shadowgraph();
    assert.strictEqual(ctx.timers.length, 1);
    assert.strictEqual(ctx.timers[0].ms, 4000);
    await flush(); await flush();
    const before = ctx.fetches.length;
    ctx.timers[0].fn();
    ctx.timers[0].fn();
    await flush();
    assert.strictEqual(ctx.fetches.length, before + 1, "two ticks in the same breath make one read");
    await flush(); await flush();
    ctx.S.screen = "shadow";
    ctx.timers[0].fn();
    assert.ok(ctx.timers[0].cleared, "off the screen the ticker stops");
    const f = ctx.fetches.length;
    ctx.timers[0].fn();
    await flush();
    assert.strictEqual(ctx.fetches.length, f);
    ctx.S.screen = "shadowgraph";
    ctx.SCREENS.shadowgraph();
    assert.strictEqual(ctx.timers.length, 2, "coming back starts a fresh one");
  });

  await atest("Include finished asks again, forced", async () => {
    const ctx = boot();
    await loaded(ctx);
    ctx.fetches.length = 0;
    fire(ctx, "click", btn({ sgdone: "1" }));
    await flush();
    assert.deepStrictEqual(ctx.fetches, ["/api/shadow/graph?include_done=1"]);
  });

  await atest("phone width: a stacked list with a rail, 44 px targets and the tooltip inline", async () => {
    const ctx = boot({ width: 400 });
    const h = await loaded(ctx);
    assert.ok(/<ul class="sglist"/.test(h) && !/sghostwrap/.test(h) && /sgrow/.test(h));
    const task = SAMPLE.graph.nodes.find(x => x.kind === "task").id;
    fire(ctx, "mouseover", btn({ sgnode: task }));
    assert.ok(/class="sgtip inline"/.test(html(ctx)));
    const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
    assert.ok(/\.sglist \.sgnode\{[^}]*min-height:44px/.test(css) && /border-left:3px solid/.test(css));
  });

  test("shadowHomeOnScreen includes the graph; the screen is registered, titled, loaded after 26 and before the tail", () => {
    const ctx = boot();
    ctx.S.screen = "shadowgraph";
    assert.strictEqual(ctx.shadowHomeOnScreen(), true);
    ctx.S.screen = "org";
    assert.strictEqual(ctx.shadowHomeOnScreen(), false);
    assert.strictEqual(typeof ctx.SCREENS.shadowgraph, "function");
    assert.strictEqual(ctx.TITLES.shadowgraph[0], "Shadow graph");
    const ph = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
    const a = ph.indexOf("/static/js/26-models.js"), b = ph.indexOf("/static/js/27-shadow-graph.js"), t = ph.indexOf("/static/js/09-tail.js");
    assert.ok(a > 0 && b > a && t > b);
  });

  test("deep links: sutra://shadow/graph and sutra://shadow/graph/m-... open the screen, with or without a task", () => {
    const ctx = boot({ realLink: true });
    ctx.calls.length = 0;
    ctx.shadowRouteDeepLink("sutra://shadow/graph/m-00000000a001");
    assert.strictEqual(ctx.S.shadowGraphFocus, "m-00000000a001");
    assert.ok(ctx.calls.some(c => c[0] === "openScreen" && c[1] === "shadowgraph"));
    ctx.shadowRouteDeepLink("sutra://shadow/graph");
    assert.strictEqual(ctx.S.shadowGraphFocus, null);
    ctx.shadowRouteDeepLink("sutra://shadow/m-00000000a001");
    assert.strictEqual(ctx.S.shadowTaskSel, "m-00000000a001", "a plain mission link still opens the task");
  });

  test("Home: the Graph button and the per-task Details link are in the header", () => {
    const src = fs.readFileSync(path.join(JS, "16-shadow-home.js"), "utf8");
    assert.ok(/data-shgraph="1"/.test(src) && /data-shdetail="\$\{escAttr\(sel\.id\)\}"/.test(src));
  });

  test("new CSS is tokens only and carries the reduced-motion rule", () => {
    const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
    const block = css.slice(css.indexOf("/* ── the Shadow graph"));
    assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block), "a literal colour");
    assert.ok(/prefers-reduced-motion:reduce\)\{\.sgs-working \.sgshape\{animation:none\}/.test(block));
  });

  /* a focused node survives a patch: the same object, new text (a tiny DOM, as test_shadow_delegate_focus.js has) */
  test("shadowPatchInto keeps the focused node and a typing box", () => {
    const ctx = boot();
    const dk = (k) => k.slice(5).replace(/-([a-z])/g, (m, c) => c.toUpperCase());
    const TREES = {};
    function el(tag, attrs, kids){
      const nd = { nodeType: 1, tagName: tag.toUpperCase(), childNodes: [], parentNode: null, attributes: [], dataset: {}, id: "",
        getAttribute(k){ const a = nd.attributes.find(x => x.name === k); return a ? a.value : null; },
        setAttribute(k, v){ const a = nd.attributes.find(x => x.name === k); if (a) a.value = String(v); else nd.attributes.push({ name: k, value: String(v) });
          if (k === "id") nd.id = String(v); if (k.indexOf("data-") === 0) nd.dataset[dk(k)] = String(v); },
        removeAttribute(k){ const i = nd.attributes.findIndex(x => x.name === k); if (i >= 0) nd.attributes.splice(i, 1); if (k.indexOf("data-") === 0) delete nd.dataset[dk(k)]; },
        appendChild(c){ c.parentNode = nd; nd.childNodes.push(c); return c; },
        removeChild(c){ const i = nd.childNodes.indexOf(c); if (i >= 0) nd.childNodes.splice(i, 1); c.parentNode = null; return c; },
        replaceChild(w, o){ const i = nd.childNodes.indexOf(o); if (i < 0) return o; w.parentNode = nd; nd.childNodes[i] = w; o.parentNode = null; return o; },
        cloneNode(){ return el(tag, nd.attributes.reduce((o, a) => (o[a.name] = a.value, o), {}), nd.childNodes.map(k => k.cloneNode(true))); },
        contains(x){ for (let p = x; p; p = p.parentNode) if (p === nd) return true; return false; },
        querySelector(){ return null; },
        get outerHTML(){ return ser(nd); },
        set innerHTML(h){ nd.childNodes = []; (TREES[h]() || []).forEach(k => nd.appendChild(k)); } };
      Object.keys(attrs || {}).forEach(k => nd.setAttribute(k, attrs[k]));
      (kids || []).forEach(k => nd.appendChild(k));
      return nd;
    }
    const txt = (s) => ({ nodeType: 3, nodeValue: s, parentNode: null, cloneNode(){ return txt(s); } });
    const ser = (x) => x.nodeType === 3 ? x.nodeValue : `<${x.tagName}${x.attributes.map(a => ` ${a.name}="${a.value}"`).join("")}>${x.childNodes.map(ser).join("")}</${x.tagName}>`;
    const tree = (label, status) => () => [el("div", { class: "sgwrap" }, [el("div", { "data-sghost": "1" }, [
      el("button", { "data-sgnode": "task:m-1", class: "sgnode" }, [el("span", {}, [txt(label)]), el("span", {}, [txt(status)])]),
      el("textarea", { "data-shnewtalk": "1" }, [])])])];
    TREES.A = tree("Fix it", "Working"); TREES.B = tree("Fix it", "Done");
    ctx.document.createElement = (t) => el(t, {}, []);
    const host = el("div", { id: "scBody" }, []);
    host.innerHTML = "A";
    const node = host.childNodes[0].childNodes[0].childNodes[0], box = host.childNodes[0].childNodes[0].childNodes[1];
    ctx.document.activeElement = node;
    ctx.shadowPatchInto(host, "B");
    const after = host.childNodes[0].childNodes[0];
    assert.strictEqual(after.childNodes[0], node, "the focused node is the same object");
    assert.strictEqual(after.childNodes[1], box, "and so is the typing box");
    assert.strictEqual(node.childNodes[1].childNodes[0].nodeValue, "Done", "its text updated in place");
  });

  console.log(failed ? failed + " failed" : "all passed");
  process.exit(failed ? 1 : 0);
})();
