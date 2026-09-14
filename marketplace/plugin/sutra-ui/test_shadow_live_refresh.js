#!/usr/bin/env node
/* test_shadow_live_refresh.js -- the screen has to notice, on its own.
 *
 * THE BUG (founder dogfood, 2026-09-15): Shadow blocked a mission and
 * attached a founder intervention while the founder was watching. The card
 * went on saying RUNNING until the page was refreshed.
 *
 * THE FIRST FIX WAS NOT ENOUGH, and this suite exists because the first
 * version of it could not tell. A throttle inside SCREENS.shadow only runs
 * when SCREENS.shadow runs, which only happens when render() runs -- and
 * render() is NOT a loop. scheduleRender() is a one-shot 100ms debounce
 * fired by events, and an idle founder watching a headless delegate
 * produces none. The old tests called SCREENS.shadow() in a for-loop, so
 * THE TEST WAS THE RENDER LOOP: it proved the throttle arithmetic and
 * could never have caught the missing driver.
 *
 * So these tests capture setInterval and fire it themselves. Nothing here
 * calls SCREENS.shadow() a second time to make the refresh happen -- if the
 * module does not install its own driver, these fail.
 *
 * Run: node test_shadow_live_refresh.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const RealDate = Date;

function ctxFor(files, extra){
  const clock = { t: 1000000 };
  const timers = [];                       // every setInterval the module made
  /* only `now` is faked -- that is the clock this file drives. The rest of
     Date is carried across verbatim, because a partial stub of a global is a
     trap: it turns an ordinary Date.parse anywhere in the module under test
     into "Date.parse is not a function", which reads as a product bug. */
  function FakeDate(...a){ return new RealDate(...a); }
  FakeDate.now = () => clock.t;
  FakeDate.parse = RealDate.parse;
  FakeDate.UTC = RealDate.UTC;
  const ctx = Object.assign({
    console, Date: FakeDate, clock, timers,
    setTimeout: (fn) => ({ fn }),
    setInterval: (fn, ms) => {
      const h = { fn, ms, cleared: false, id: timers.length + 1 };
      timers.push(h);
      return h;
    },
    clearInterval: (h) => { if (h) h.cleared = true; },
    S: {}, SCREENS: {}, TITLES: {},
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    scheduleRender: () => {},
    fetch: () => Promise.resolve({ ok: true, json: async () => ({}) }),
    document: {
      addEventListener(){}, body: { appendChild(){} },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      querySelector(){ return null; },
    },
  }, extra || {});
  vm.createContext(ctx);
  for (const f of files)
    vm.runInContext(fs.readFileSync(
      path.join(__dirname, "static", "js", f), "utf8"), ctx);
  return ctx;
}

const live = (ctx) => ctx.timers.filter(t => !t.cleared);
const tick = (h) => h.fn();

/* ---------------------------------------------------------- Shadow home -- */

function shadowCtx(){
  const ctx = ctxFor(
    ["15-shadow-overlay.js", "16-shadow-home.js", "18-goal-workspace.js"]);
  ctx.S.screen = "shadow";                 // shadowHomeOnScreen() -> true
  ctx.S.goals = [];
  return ctx;
}

const RUNNING = { id: "m-1", objective: "ship it", template: "fix",
  state: "running", target_mode: "new", target_session: "s-1",
  target_chat: "c-1", turns_used: 2, max_turns: 20, done_when: [] };

const BLOCKED = Object.assign({}, RUNNING, {
  state: "blocked", block_reason: "needs_founder",
  intervention: { id: "iv-1", schema_version: 1,
    question: "Which region?", context: "two configs disagree", evidence: [],
    fields: [{ key: "region", type: "choice", label: "Default region",
      help: "", required: true, default: null, constraints: {},
      options: [{ value: "a", label: "A", help: "" },
                { value: "b", label: "B", help: "" }] }],
    submit_label: "Send to Shadow", expires_at: null } });

/* 1. the FIRST render installs a driver */
{
  const ctx = shadowCtx();
  ctx.loadShadowHome = () => {};
  assert.strictEqual(ctx.timers.length, 0, "nothing before the first render");
  ctx.S.shadowHomeDark = undefined;
  ctx.SCREENS.shadow();
  assert.strictEqual(live(ctx).length, 1, "one interval installed");
  assert.strictEqual(live(ctx)[0].ms, 4000, "at the 4s cadence");
  console.log("ok 1 first render installs a 4s interval");
}

/* 2. THE POINT: firing the interval refreshes with NO further render */
{
  const ctx = shadowCtx();
  let reads = 0;
  ctx.loadShadowHome = () => { reads++; };
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [RUNNING];
  ctx.SCREENS.shadow();
  const before = reads;
  tick(live(ctx)[0]);
  tick(live(ctx)[0]);
  assert.strictEqual(reads, before + 2,
    "each tick must read, without SCREENS.shadow() being called again");
  console.log("ok 2 the interval drives the read on its own");
}

/* 3. THE REPORTED BUG, end to end, with no second render to help it */
{
  const ctx = shadowCtx();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [RUNNING];
  ctx.S.shadowTaskSel = "m-1";
  let inFlight = false;
  ctx.loadShadowHome = () => { inFlight = true; };   // resolves later

  const before = ctx.SCREENS.shadow();
  assert(/RUNNING/.test(before), "the founder is watching a running mission");
  assert(!/shivform/.test(before), "no form yet");

  // the founder now does NOTHING. only the interval fires.
  tick(live(ctx)[0]);
  assert(inFlight, "the driver kicked a read with no user action");
  ctx.S.shadowMissions = [BLOCKED];                  // the response lands

  const after = ctx.shadowHomeHtml();                // what the repaint draws
  assert(/NEEDS YOU/.test(after), "NEEDS YOU without a page refresh");
  assert(/shivform/.test(after), "the intervention form is drawn");
  assert(/Which region\?/.test(after), "with the persisted question");
  console.log("ok 3 blocked + intervention appears with no refresh, no render");
}

/* 4. frequent renders must not stack drivers */
{
  const ctx = shadowCtx();
  ctx.loadShadowHome = () => {};
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [RUNNING];
  for (let i = 0; i < 500; i++) ctx.SCREENS.shadow();
  assert.strictEqual(live(ctx).length, 1,
    "500 renders must not create 500 timers, got " + live(ctx).length);
  console.log("ok 4 500 renders -> still one interval");
}

/* 5. it clears itself when Shadow is no longer the screen */
{
  const ctx = shadowCtx();
  let reads = 0;
  ctx.loadShadowHome = () => { reads++; };
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [RUNNING];
  ctx.SCREENS.shadow();
  const h = live(ctx)[0];
  ctx.S.screen = "chat";                   // the founder navigated away
  const was = reads;
  tick(h);
  assert(h.cleared, "the interval must clear itself off-screen");
  assert.strictEqual(reads, was, "and must not read");
  console.log("ok 5 self-clearing when Shadow is not the active screen");
}

/* 6. and a later visit installs a fresh one */
{
  const ctx = shadowCtx();
  ctx.loadShadowHome = () => {};
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [RUNNING];
  ctx.SCREENS.shadow();
  ctx.S.screen = "chat"; tick(ctx.timers[0]);
  assert.strictEqual(live(ctx).length, 0, "cleared");
  ctx.S.screen = "shadow";
  ctx.SCREENS.shadow();
  assert.strictEqual(live(ctx).length, 1, "a return re-arms the driver");
  console.log("ok 6 returning to Shadow re-arms the driver");
}

/* 7. the render-burst throttle survives as a defensive guard */
{
  const ctx = shadowCtx();
  let reads = 0;
  ctx.loadShadowHome = () => { reads++; };
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [RUNNING];
  for (let i = 0; i < 500; i++) ctx.SCREENS.shadow();
  assert.strictEqual(reads, 1,
    "500 renders still collapse to one render-driven read, got " + reads);
  console.log("ok 7 render-burst guard intact (no per-frame storm)");
}

/* 8. first paint is unchanged */
{
  const ctx = shadowCtx();
  let reads = 0;
  ctx.loadShadowHome = () => { reads++; };
  ctx.S.shadowHomeDark = undefined;
  const first = ctx.SCREENS.shadow();
  assert(/Looking/.test(first), "first paint still says Looking…");
  assert.strictEqual(reads, 1, "and reads exactly once");
  console.log("ok 8 first paint preserved");
}

/* 9. existing rendering is untouched */
{
  const ctx = shadowCtx();
  ctx.loadShadowHome = () => {};
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowMissions = [RUNNING];
  ctx.S.shadowTaskSel = "m-1";
  assert.strictEqual(ctx.SCREENS.shadow(), ctx.shadowHomeHtml(),
    "SCREENS.shadow still returns exactly shadowHomeHtml()");
  console.log("ok 9 existing Shadow rendering unchanged");
}

/* -------------------------------------------------------- Needs-You pill -- */

function nyCtx(){
  const ctx = ctxFor(["14-needs-you.js"], {
    escAttr: (x) => String(x == null ? "" : x),
    shadowDotAlerts: () => {},
    openScreen: () => {},
    shadowPost: async () => ({ ok: true }),
  });
  ctx.S.screen = "now";
  return ctx;
}

/* 10. the pill installs its own driver, at the same cadence */
{
  const ctx = nyCtx();
  ctx.loadNeedsYou = () => {};
  ctx.S.needsYou = [];
  ctx.SCREENS.now();
  assert.strictEqual(live(ctx).length, 1, "one interval");
  assert.strictEqual(live(ctx)[0].ms, 4000, "4s cadence");
  console.log("ok 10 Needs-You installs a 4s interval");
}

/* 11. firing it refreshes the pill with no further render */
{
  const ctx = nyCtx();
  let reads = 0;
  ctx.loadNeedsYou = () => { reads++; };
  ctx.S.needsYou = [];
  ctx.SCREENS.now();
  const was = reads;
  tick(live(ctx)[0]);
  assert.strictEqual(reads, was + 1, "the tick reads on its own");
  ctx.S.needsYou = [{ item_id: "i-1", kind: "needs_decision", state: "new",
    title: "Shadow needs you", deep_link: "sutra://x" }];
  assert(/Shadow needs you/.test(ctx.SCREENS.now()),
    "the new item is on screen without a page refresh");
  console.log("ok 11 Needs-You refreshes without a refresh");
}

/* 12. self-clearing, and no stacking */
{
  const ctx = nyCtx();
  ctx.loadNeedsYou = () => {};
  ctx.S.needsYou = [];
  for (let i = 0; i < 200; i++) ctx.SCREENS.now();
  assert.strictEqual(live(ctx).length, 1, "no stacking");
  ctx.S.screen = "shadow";
  tick(ctx.timers[0]);
  assert(ctx.timers[0].cleared, "clears itself when Now is not the screen");
  console.log("ok 12 Needs-You self-clears and never stacks");
}

console.log("\nall shadow live-refresh tests passed");
