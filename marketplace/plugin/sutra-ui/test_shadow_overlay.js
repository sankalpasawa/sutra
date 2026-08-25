#!/usr/bin/env node
/*
 * test_shadow_overlay.js -- PLAN-100 S65-S79: the overlay integration suite.
 * Real module under vm, minimal stubs, assertions on real behavior.
 * Run: node test_shadow_overlay.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
assert(/15-shadow-overlay\.js/.test(html), "panel.html loads the overlay module");

const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");

/* S76 energy: the module must not poll -- no setInterval at all */
assert(!/setInterval/.test(src), "overlay must be event-driven, never poll");

function fresh(opts){
  opts = opts || {};
  const appended = [];
  const ctx = {
    console, Date,
    setTimeout: (fn, ms) => ({ fn, ms }), clearTimeout(){},
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    S: {}, listeners: {},
    fetch: opts.fetch,
    document: {
      createElement(tag){
        const el = { tagName: tag, className: "", textContent: "",
                     dataset: {}, _attrs: {},
                     setAttribute(k, v){ el._attrs[k] = v; },
                     remove(){} };
        return el;
      },
      body: { appended, appendChild(el){ appended.push(el); } },
      querySelector(){ return null; },
      addEventListener(type, fn){ ctx.listeners[type] = fn; },
    },
    _appended: appended,
  };
  ctx.__SHADOW_NO_AUTOBOOT = true;   /* tests drive boot explicitly */
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

/* the 2.224.1 lesson: served code that nobody calls. Pin the call sites. */
assert(/^\s*try \{ bootShadowOverlay\(\); \}/m.test(src),
  "the module must CALL bootShadowOverlay on load");
assert(/addEventListener\("click", toggleShadowCard\)/.test(src),
  "the dot must open the card on click");
assert(/function renderShadowCard/.test(src)
       && /appendChild\(wrap\)/.test(src),
  "the card must MOUNT, not just return html");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
const dotRule = css.slice(css.indexOf(".shdot{"), css.indexOf("}", css.indexOf(".shdot{")));
assert(/right:\s*\d/.test(dotRule) && /bottom:\s*\d/.test(dotRule),
  "the dot needs default coordinates or it renders nowhere (2.224.3 bug)");

/* 1. S65: snap picks the nearest corner */
{
  const ctx = fresh();
  const J = (o) => JSON.stringify(o);   /* vm objects have foreign protos */
  assert.strictEqual(J(ctx.snapCorner(10, 10, 1000, 800)),
    J({ left: 16, right: null, top: 16, bottom: null }));
  assert.strictEqual(J(ctx.snapCorner(990, 790, 1000, 800)),
    J({ left: null, right: 16, top: null, bottom: 16 }));
  console.log("ok 1 snap");
}

/* 2. S67: three unsolicited pills an hour, nudges exempt */
{
  const ctx = fresh();
  const now = Date.now();
  let [ok] = ctx.pillAllowed([], now);            assert(ok);
  [ok] = ctx.pillAllowed([now-1, now-2, now-3], now); assert(!ok);
  [ok] = ctx.pillAllowed([now - 3700e3, now - 3800e3, now - 3900e3], now);
  assert(ok, "stale history prunes");
  console.log("ok 2 pill rate");
}

/* 3. S71/S72: chips validate verb+object, cap 3, junk falls to Clarify */
{
  const ctx = fresh();
  assert.strictEqual(
    JSON.stringify(ctx.validChips(["Review the brief", "Stop mission",
                                   "Open thread", "Retry now"])),
    JSON.stringify(["Review the brief", "Stop mission", "Open thread"]),
    "max 3");
  assert.strictEqual(JSON.stringify(ctx.validChips(["ok", "", "1234 do it"])),
    "[]", "junk chips rejected");
  const card = (ctx.S.shadowThread = [], ctx.S.shadowChips = ["??", "!"],
                ctx.shadowCardHtml());
  assert(/Clarify/.test(card), "junk chips fall back to Clarify");
  console.log("ok 3 chips");
}

/* 4. S75: own turns are filtered before they can loop */
{
  const ctx = fresh();
  assert(ctx.isOwnTurn("[Shadow \u00b7 mission m-1] do the thing"));
  assert(!ctx.isOwnTurn("founder text about [Shadow] in passing"));
  console.log("ok 4 own-turn filter");
}

/* 5. S78: dot states incl. down */
{
  const ctx = fresh();
  assert.strictEqual(ctx.dotState(null).cls, "shdot-down");
  assert.strictEqual(ctx.dotState({ watching: true }).cls, "shdot-live");
  assert.strictEqual(ctx.dotState({ watching: false }).cls, "shdot-idle");
  console.log("ok 5 dot states");
}

/* 6. OFF-STATE: status 403 -> NOTHING mounts (the P5 off-invariant) */
{
  let fetched = [];
  const ctx = fresh({ fetch: (url) => { fetched.push(url);
    return Promise.resolve({ ok: false }); } });
  ctx.bootShadowOverlay();
  return_after_microtasks(() => {
    assert.strictEqual(ctx._appended.length, 0,
      "403 status must mount zero shadow DOM");
    console.log("ok 6 dark = no mount");
    part2();
  });
}

function return_after_microtasks(fn){ setTimeout(fn, 10); }

function part2(){
  /* 7. flag on -> dot mounts with a11y attributes (S65/S66) */
  const ctx = fresh({ fetch: () => Promise.resolve({
    ok: true, json: () => Promise.resolve({ watching: true }) }) });
  ctx.bootShadowOverlay();
  return_after_microtasks(() => {
    assert.strictEqual(ctx._appended.length, 1, "dot mounts on 200");
    const dot = ctx._appended[0];
    assert(/shdot-live/.test(dot.className));
    assert.strictEqual(dot._attrs["role"], "button");
    assert(dot._attrs["aria-label"], "a11y label present");
    console.log("ok 7 mount + a11y");
    part3();
  });
}

function part3(){
  /* 8. S77 keyboard toggle + Esc; S73 quiet suppresses pills */
  const ctx = fresh();
  ctx.S.shadowCardOpen = false;
  assert(ctx.shadowKeyHandler({ metaKey: true, shiftKey: true, key: "S" }));
  assert.strictEqual(ctx.S.shadowCardOpen, true, "cmd-shift-S opens");
  assert(ctx.shadowKeyHandler({ key: "Escape" }));
  assert.strictEqual(ctx.S.shadowCardOpen, false, "Esc closes");
  ctx.S.shadowQuiet = true;
  assert.strictEqual(ctx.showPill("psst"), null, "quiet switch silences");
  ctx.S.shadowQuiet = false;
  const el = ctx.showPill("hello");
  assert(el && el.className === "shpill");
  console.log("ok 8 keyboard + quiet + pill");

  /* 8b. dot click toggles + MOUNTS the card; Esc unmounts */
  {
    const c2 = fresh();
    const removed = [];
    let mounted = null;
    c2.document.querySelector = (sel) =>
      sel === "[data-shcardwrap]" ? mounted : null;
    const mkEl = c2.document.createElement;
    c2.document.createElement = (tag) => {
      const el = mkEl(tag);
      el.innerHTML = "";
      el.addEventListener = () => {};
      el.remove = () => { removed.push(el); if (mounted === el) mounted = null; };
      return el;
    };
    const baseAppend = c2.document.body.appendChild.bind(c2.document.body);
    c2.document.body.appendChild = (el) => {
      if (el.dataset && el.dataset.shcardwrap) mounted = el;
      baseAppend(el);
    };
    c2.S.shadowThread = [];
    c2.toggleShadowCard();
    assert(mounted, "click path must mount the card");
    assert(/shcard/.test(mounted.innerHTML), "mounted card carries the shell");
    c2.shadowKeyHandler({ key: "Escape" });
    assert(!mounted, "Esc must unmount");
    console.log("ok 8b card mounts");
  }

  /* 9. ONE thread: the card renders S.shadowThread (shared with the home) */
  ctx.S.shadowThread = [{ who: "founder", text: "hi" },
                        { who: "shadow", text: "watching 4 sessions" }];
  const cardHtml = ctx.shadowCardHtml();
  assert(/watching 4 sessions/.test(cardHtml), "card renders the ONE thread");
  console.log("ok 9 one thread");

  /* 10. S70: mission card in-thread; Start gated by state chip */
  assert(/data-shstart="m-1"/.test(
    ctx.missionCardHtml({ id: "m-1", objective: "x", state: "brief_confirm" })),
    "confirmed brief can Start");
  assert(!/data-shstart/.test(
    ctx.missionCardHtml({ id: "m-1", objective: "x", state: "running" })),
    "a running mission has no Start");
  assert(/shstate-paused/.test(
    ctx.missionCardHtml({ id: "m-2", objective: "y", state: "paused" })),
    "state chip carries the state");
  console.log("ok 10 mission card");
  console.log("test_shadow_overlay.js: all green");
}
