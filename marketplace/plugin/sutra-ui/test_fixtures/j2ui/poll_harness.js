#!/usr/bin/env node
/* poll_harness.js -- the J2 page, polled against a bundle of answers, in a stub DOM (UI port, package j2ui-verify, T2).

     node poll_harness.js <page.html> <bundle.json>

Runs the last bare <script> of the page in a node vm over a stub DOM modelled on the prototype's own j2_ui_render.js, with a
fetch that answers by URL path from the bundle, then polls and prints one JSON object on stdout:

     {ok, errors, panes, polls, posts, sstatus}

The bundle is the answers of one department or run: {state, map, board, artifacts, docs, audits, refs, runs, preview?, files?,
search?, expect_keys?}. `state` is the whole api/state answer (the chat is cut by `since`, as the server does); `search` is the page's
location.search (a saved run is opened with ?run=ID). A missing key answers 404, which the page treats as "not there".
The path is read after stripping a leading slash and everything before api/, site/, file/, shot/, so the prototype's
"/api/state" and the copy's "api/state" both work.

The page's poll() swallows its own exceptions (the only sign is "Something went wrong. Try again." while no state is held), so
this harness also notes whatever the page's catch received (the one catch of poll is wrapped in memory; nothing is written)
and, as a second witness, whether poll() got to its last line (state === CTX).

`expect_keys` is the list of keys the state must carry (the 56 of api/state): a key the state lacks is an error, because a
state with a key missing is one the page was not written for, even where the page happens to shrug it off. The state is also
handed to the page behind a proxy that notes every read of a key the state does not have.

`ok` is false when: the script threw at load; the state stayed null after the first poll; #sstatus says
"Something went wrong. Try again."; a poll threw; a render function threw; or the visible text of any pane (tags and
attribute values removed) has undefined, NaN or null as a word. `panes` holds the HTML of the panes listed in PANES, and the
strings returned by renderMap(MAP), renderDocs(), renderArtifacts() and renderBoard().

No network, no timers: setTimeout and requestAnimationFrame are no-ops, so nothing polls by itself. */
"use strict";
const fs = require("fs");
const vm = require("vm");

const [pagePath, bundlePath] = process.argv.slice(2);
if (!pagePath || !bundlePath) {
  console.error("usage: node poll_harness.js <page.html> <bundle.json>");
  process.exit(2);
}
const HTML = fs.readFileSync(pagePath, "utf8");
const B = JSON.parse(fs.readFileSync(bundlePath, "utf8"));

// the panes whose HTML is reported: the spec's fifteen, then the rest of the detailed view's panes
const PANES = ["smsgs", "sprog", "needs", "pane-goal", "pane-workflows", "pane-conflicts", "pane-audit", "reportbody", "pane-charter",
  "pane-timeline", "pane-lessons", "pane-style", "pane-playbooks", "lanes", "steps", "pane-map", "pane-docs", "pane-artifacts",
  "pane-board", "msgs", "waiting", "mode", "fixes", "mem", "typing", "quick"];
const RENDERS = [["renderMap", "renderMap(MAP)"], ["renderDocs", "renderDocs()"], ["renderArtifacts", "renderArtifacts()"],
  ["renderBoard", "renderBoard()"]];

// ---- a stub DOM ------------------------------------------------------------------------------------------------------
const ids = new Set([...HTML.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
const noop = function () {};
const NUM = { scrollTop: 0, scrollHeight: 0, clientWidth: 1000, clientHeight: 800, offsetWidth: 1000, offsetHeight: 800, tabIndex: 0 };

function makeEl(tag, id) {
  const classes = new Set(), attrs = {}, listeners = {};
  const t = {
    tagName: String(tag || "div").toUpperCase(), id: id || "", innerHTML: "", textContent: "", value: "", className: "", hidden: false,
    disabled: false, open: false, src: "", href: "", title: "", placeholder: "", checked: false, name: "", type: "",
    style: { setProperty: noop, removeProperty: noop, cssText: "" }, dataset: {}, children: [], childNodes: [],
    onclick: null, onchange: null, oninput: null, onkeydown: null,
    classList: {
      add: (...c) => c.forEach(x => classes.add(x)), remove: (...c) => c.forEach(x => classes.delete(x)),
      toggle: (c, f) => { const on = f === undefined ? !classes.has(c) : !!f; if (on) classes.add(c); else classes.delete(c); return on; },
      contains: c => classes.has(c),
    },
    setAttribute: (k, v) => { attrs[k] = String(v); }, getAttribute: k => (k in attrs ? attrs[k] : null),
    hasAttribute: k => k in attrs, removeAttribute: k => { delete attrs[k]; },
    appendChild: c => { t.children.push(c); return c; }, append: (...c) => { t.children.push(...c); },
    prepend: (...c) => { t.children.unshift(...c); }, remove: noop, replaceChildren: () => { t.children.length = 0; },
    addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); }, removeEventListener: noop,
    querySelector: () => null, querySelectorAll: () => [], closest: () => null, matches: () => false, contains: () => false,
    focus: noop, blur: noop, click: noop, scrollIntoView: noop, getClientRects: () => [],
    getBoundingClientRect: () => ({ width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 }),
    showModal: noop, close: noop, insertAdjacentHTML: noop, select: noop, __listeners: listeners, __classes: classes,
  };
  Object.assign(t, NUM);
  return new Proxy(t, {
    get(target, k) {
      if (k in target) return target[k];
      if (typeof k === "symbol" || k === "then" || k === "toJSON" || String(k).startsWith("__") || /^on[a-z]+$/.test(String(k))) return undefined;
      return noop;
    },
    set(target, k, v) { target[k] = v; return true; },
  });
}

const els = {};
const bySelector = {};
const docListeners = {};
const document = {
  getElementById: id => (ids.has(id) ? (els[id] = els[id] || makeEl("div", id)) : null),
  querySelector: sel => (bySelector[sel] = bySelector[sel] || makeEl("div", "")),
  querySelectorAll: () => [],
  createElement: tag => makeEl(tag, ""),
  addEventListener: (type, fn) => { (docListeners[type] = docListeners[type] || []).push(fn); },
  body: makeEl("body", ""), documentElement: makeEl("html", ""), title: "",
};

const store = {};
const calls = { posts: [], errors: [], consoleErrors: [], missing: new Set() };
const ctxObj = {
  document,
  location: { search: String(B.search || ""), href: "http://127.0.0.1/j2ui/x/" + String(B.search || ""), hash: "", pathname: "/j2ui/x/", reload: noop },
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  CSS: { escape: x => String(x) },
  navigator: { userAgent: "node-harness", language: "en" },
  matchMedia: () => ({ matches: false, addEventListener: noop, removeEventListener: noop }),
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  setTimeout: noop, clearTimeout: noop, setInterval: noop, clearInterval: noop, requestAnimationFrame: noop,
  confirm: () => true, alert: noop, URLSearchParams, URL, TextEncoder,
  console: { log: noop, info: noop, warn: noop, debug: noop, error: (...a) => calls.consoleErrors.push(a.map(String).join(" ")) },
  __pollError: e => calls.errors.push("poll: " + (e && e.stack ? String(e.stack).split("\n").slice(0, 3).join(" | ") : String(e))),
};

function tail(url) {
  const m = String(url).match(/(?:^|\/)((?:api|site|file|shot)\/[^?#]*)(?:\?([^#]*))?/);
  return m ? { path: m[1], query: new URLSearchParams(m[2] || "") } : { path: String(url).replace(/^\//, ""), query: new URLSearchParams() };
}

function answer(url, init) {
  const { path, query } = tail(url);
  const method = String((init && init.method) || "GET").toUpperCase();
  let body = null, status = 200, text = null, isState = false;
  if (method !== "GET") {
    calls.posts.push({ path, body: init && init.body ? String(init.body) : "" });
    body = { ok: true };
  } else if (path === "api/state") {
    const s = B.state;
    if (!s) status = 404;
    else {
      const since = Math.max(0, parseInt(query.get("since") || "0", 10) || 0);
      body = Object.assign({}, s, { chat: (s.chat || []).slice(since) });
      isState = true;
    }
  } else if (/^api\/(map|board|artifacts|docs|audits|refs|runs|preview)$/.test(path)) {
    const k = path.slice(4);
    if (B[k] === undefined) status = 404; else body = B[k];
  } else if (path === "api/artifact") {
    const f = query.get("name");
    if (B.files && f in B.files) text = String(B.files[f]); else { status = 404; text = "not found"; }
  } else {
    status = 404;
    text = "not found";
  }
  const raw = text !== null ? text : status === 200 ? JSON.stringify(body) : JSON.stringify({ error: "not found" });
  return Promise.resolve({
    ok: status >= 200 && status < 300, status,
    json: () => Promise.resolve().then(() => { const o = inCtx.JSON.parse(raw); return isState ? watch(o) : o; }),
    text: () => Promise.resolve(raw),
  });
}
// the state the page is given: reads of a key it does not have are noted (the page's own writes, allChat, are not reads)
const watch = o => new Proxy(o, {
  get(t, k) {
    if (typeof k === "string" && !(k in t) && k !== "then" && k !== "toJSON") calls.missing.add(k);
    return t[k];
  },
});
ctxObj.fetch = answer;
ctxObj.window = ctxObj;
ctxObj.self = ctxObj;
const ctx = vm.createContext(ctxObj);
const inCtx = { JSON: vm.runInContext("JSON", ctx) };
// the same clock on every run, so a time printed by the page is the same in two harness runs
vm.runInContext(`(() => { const D = Date, T = 1760000000000;
  globalThis.Date = class extends D { constructor(...a) { if (a.length) super(...a); else super(T); } static now() { return T; } }; })()`, ctx);

const flush = async (n = 8) => { for (let i = 0; i < n; i++) await new Promise(r => setImmediate(r)); };

// ---- the page's script -----------------------------------------------------------------------------------------------
const scripts = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (!scripts.length) {
  console.log(JSON.stringify({ ok: false, errors: ["the page has no bare <script>"], panes: {}, polls: 0, posts: [], sstatus: "" }));
  process.exit(0);
}
let code = scripts[scripts.length - 1][1];
// poll() ends in `catch(e){ if (!state) $("sstatus")...`: let the harness see e (in memory; the page file is not touched)
const CATCH = 'catch(e){ if (!state) $("sstatus").textContent = "Something went wrong. Try again."; }';
if (code.split(CATCH).length === 2) code = code.replace(CATCH, 'catch(e){ __pollError(e); if (!state) $("sstatus").textContent = "Something went wrong. Try again."; }');

const visible = html => String(html)
  .replace(/<(script|style)\b[\s\S]*?<\/\1>/gi, " ")
  .replace(/<[^>]*>/g, " ")
  .replace(/&(?:amp|lt|gt|quot|#39);/g, " ");
const BAD = /\b(undefined|NaN|null)\b/;

function paneText(id) {
  const e = els[id];
  if (!e) return "";
  if (id === "msgs") {
    return e.children.map(c => `<div class="${c.className}"${c.dataset && c.dataset.id ? ` data-id="${c.dataset.id}"` : ""}>${c.innerHTML || ""}${c.textContent || ""}</div>`).join("");
  }
  return String(e.innerHTML || "");
}

(async () => {
  let polls = 0;
  try {
    vm.runInContext(code, ctx, { filename: "j2_ui.html" });
  } catch (e) {
    calls.errors.push("load: " + (e && e.stack ? String(e.stack).split("\n").slice(0, 3).join(" | ") : String(e)));
  }
  await flush();
  polls = 1;                                                // the page's own last line is poll()
  const afterFirst = vm.runInContext("state !== null", ctx);
  const poll = async () => {
    try { await vm.runInContext("poll()", ctx); } catch (e) { calls.errors.push("poll(): " + e); }
    polls++;
    await flush();
    if (!vm.runInContext("state === CTX", ctx)) calls.errors.push("poll " + polls + " stopped before its last line (state !== CTX)");
  };
  await poll();
  await poll();
  const panes = {};
  for (const id of PANES) panes[id] = paneText(id);
  for (const [name, expr] of RENDERS) {
    try { panes[name] = String(vm.runInContext(expr, ctx)); } catch (e) { calls.errors.push(name + ": " + (e && e.message)); panes[name] = ""; }
  }
  const sstatus = els.sstatus ? String(els.sstatus.textContent || "") : "";
  const errors = calls.errors.slice();
  for (const m of calls.consoleErrors) errors.push("console.error: " + m);
  if (!afterFirst) errors.push("the state was still null after the first poll");
  if (B.state && Array.isArray(B.expect_keys)) {
    const lack = B.expect_keys.filter(k => !(k in B.state));
    if (lack.length) errors.push("the state lacks " + lack.join(", "));
  }
  if (calls.missing.size) errors.push("the page read " + [...calls.missing].join(", ") + ", which the state does not have");
  if (sstatus === "Something went wrong. Try again.") errors.push('#sstatus says "Something went wrong. Try again."');
  for (const [name, html] of Object.entries(panes)) {
    const m = BAD.exec(visible(html));
    if (m) {
      const at = visible(html).indexOf(m[0]);
      errors.push(`pane ${name} shows "${m[0]}": ...${visible(html).slice(Math.max(0, at - 40), at + 40).replace(/\s+/g, " ")}...`);
    }
  }
  console.log(JSON.stringify({ ok: errors.length === 0, errors, panes, polls, posts: calls.posts, sstatus }));
})();
