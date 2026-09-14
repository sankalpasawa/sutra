#!/usr/bin/env node
/* test_shadow_task_chat.js -- Create Task must show the chat it just started.
 *
 * THE UX THIS PINS (founder, 2026-09-14). One click on "Create Task" already
 * created the mission, started it through the existing start_now path and
 * published a delegate chat ~1.4s later. What the founder saw for the next
 * fourteen seconds was a static brief -- QUEUED, "turn 0 of 20", "a new chat
 * Shadow starts when you begin" -- because the task pane never drew the
 * conversation. The chat existed and was simply not rendered.
 *
 * Two halves are asserted here and nothing else:
 *   1. shadowTaskChatHtml draws the delegate conversation as soon as the
 *      session exists, by CALLING the Assignment workspace's existing
 *      transcript machinery rather than copying it -- and degrades to the
 *      old brief when that module is not loaded.
 *   2. shadowWatchStart keeps re-reading until there is a chat to draw, not
 *      merely until the state left brief_confirm.
 *
 * Run: node test_shadow_task_chat.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

/* `goals` false = the Assignment module was never loaded, which is the
   degradation path the typeof guards exist for. */
function fresh(goals){
  const ctx = {
    console, Date,
    timers: [],
    setTimeout: (fn, ms) => { ctx.timers.push({ fn, ms }); return { fn, ms }; },
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {},
    fetched: [],
    listeners: {},
    document: {
      addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  if (goals){
    /* the REAL contract of the three functions this reuses, stubbed at the
       same shape 18-goal-workspace.js exports */
    ctx.loadGoalTranscript = (sid) => { ctx.fetched.push(sid); };
    ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
    ctx.goalTranscriptHtml = (msgs) => {
      if (msgs === undefined) return `<div class="gwempty">Reading the chat…</div>`;
      if (!msgs.length) return `<div class="gwempty">Nothing in this chat yet.</div>`;
      return msgs.map(m => `<div class="gwturn">${m.text}</div>`).join("");
    };
  }
  return ctx;
}

const BASE = { id: "m-x", objective: "write the note", template: "fix",
  target_mode: "new", turns_used: 0, max_turns: 20, done_when: [] };
const card = (ctx, m) => ctx.shadowTaskCardHtml(Object.assign({}, BASE, m));

/* 1. no session yet -- nothing to draw, and the brief is unchanged */
{
  const ctx = fresh(true);
  const h = card(ctx, { state: "brief_confirm", target_session: null });
  assert(!/gwchat/.test(h), "no session: there is no conversation to show");
  assert(/acts in/.test(h) && /a new chat/.test(h),
    "no session: the existing brief row is untouched");
  assert.strictEqual(ctx.fetched.length, 0, "no session: nothing is fetched");
  console.log("ok 1 no session -> the brief, unchanged");
}

/* 2. THE FIX: the session exists, so the conversation is drawn */
{
  const ctx = fresh(true);
  ctx.S.goalTranscript = { "sid-1": [{ role: "assistant", text: "working on it" }] };
  const h = card(ctx, { state: "brief_confirm", target_session: "sid-1" });
  assert(/gwchat/.test(h), "the delegate chat block must render");
  assert(/working on it/.test(h), "the conversation itself must be visible");
  assert(/its own chat/.test(h), "the chat must be named");
  console.log("ok 2 session -> the conversation is on screen");
}

/* 3. it renders BEFORE the state moves -- that is the whole point */
{
  const ctx = fresh(true);
  ctx.S.goalTranscript = { "sid-2": [{ role: "assistant", text: "hello" }] };
  const h = card(ctx, { state: "brief_confirm", target_session: "sid-2" });
  assert(/gwchat/.test(h) && /hello/.test(h),
    "brief_confirm with a session must still show the chat: the chat is " +
    "published ~13s before the row leaves brief_confirm");
  console.log("ok 3 the chat shows while the row is still brief_confirm");
}

/* 4. nothing held yet -> exactly one fetch, and the pane says so */
{
  const ctx = fresh(true);
  const h = card(ctx, { state: "running", target_session: "sid-3" });
  assert.deepStrictEqual(ctx.fetched, ["sid-3"], "one fetch for one session");
  assert(/Reading the chat/.test(h), "an unfetched chat says it is reading");
  console.log("ok 4 one fetch, honest placeholder");
}

/* 5. RENDER STORM GUARD: render() runs many times a second */
{
  const ctx = fresh(true);
  ctx.S.goalTranscript = { "sid-4": [] };
  for (let i = 0; i < 25; i++) card(ctx, { state: "running", target_session: "sid-4" });
  /* ONE refresh for a live mission (the held copy is a second old at best),
     then silence for the rest of the throttle window -- 25 renders must not
     be 25 GETs, which is the storm this guard exists for. */
  assert.strictEqual(ctx.fetched.length, 1,
    "25 renders must collapse to one refresh: got " + ctx.fetched.length);
  console.log("ok 5 throttled -- 25 renders, one refresh");
}

/* 6. an OPEN pane owns its own re-reads (09-tail.js) -- never two GETs */
{
  const ctx = fresh(true);
  ctx.S.openPanes = ["sid-5"];
  card(ctx, { state: "running", target_session: "sid-5" });
  assert.strictEqual(ctx.fetched.length, 0,
    "an open pane must not be fetched a second time");
  console.log("ok 6 open pane is left to its own reader");
}

/* 7. DEGRADATION: the Assignment module was not loaded */
{
  const ctx = fresh(false);
  let h = null;
  assert.doesNotThrow(() => {
    h = card(ctx, { state: "running", target_session: "sid-6" });
  }, "a context without the goal module must not throw");
  assert(!/gwchat/.test(h), "without the module there is nothing to draw");
  assert(/acts in/.test(h), "the brief still renders");
  console.log("ok 7 degrades to the brief, never throws");
}

/* ---- shadowWatchStart: wait for something to SHOW ---------------------- */

function runTimers(ctx){ ctx.timers.splice(0).forEach(t => t.fn()); }

/* 8. the schedule reaches the chat's real arrival (~1.4s) */
{
  const ctx = fresh(true);
  ctx.shadowWatchStart("m-w");
  const ms = ctx.timers.map(t => t.ms);
  assert(ms.some(x => x >= 1200 && x <= 1600),
    "there must be a re-read around when the chat lands: " + ms.join(","));
  console.log("ok 8 backoff covers the chat's arrival");
}

/* 9. state moved but NO chat yet -> keep looking */
{
  const ctx = fresh(true);
  let reads = 0;
  ctx.loadShadowHome = () => { reads++; };
  ctx.S.shadowMissions = [{ id: "m-w", state: "running", target_chat: null }];
  ctx.shadowWatchStart("m-w");
  runTimers(ctx);
  assert(reads > 0,
    "running with no chat is not done: the pane still has nothing to show");
  console.log("ok 9 keeps looking until there is a chat");
}

/* 10. state moved AND the chat exists -> stop */
{
  const ctx = fresh(true);
  let reads = 0;
  ctx.loadShadowHome = () => { reads++; };
  ctx.S.shadowMissions = [{ id: "m-w", state: "running", target_chat: "c-1" }];
  ctx.shadowWatchStart("m-w");
  runTimers(ctx);
  assert.strictEqual(reads, 0, "both landed: stop re-reading");
  console.log("ok 10 stops once there is something to show");
}

/* 11. a start that FAILED has no chat coming -> stop, do not poll it out */
{
  const ctx = fresh(true);
  let reads = 0;
  ctx.loadShadowHome = () => { reads++; };
  ctx.S.shadowMissions = [{ id: "m-w", state: "failed", target_chat: null }];
  ctx.shadowWatchStart("m-w");
  runTimers(ctx);
  assert.strictEqual(reads, 0, "a failed start must not be polled to the end");
  console.log("ok 11 a failed start stops the watcher");
}

console.log("\nall shadow task-chat tests passed");
