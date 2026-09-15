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
 *   1. shadowTaskChatHtml draws the delegate conversation -- by CALLING the
 *      Assignment workspace's existing transcript machinery rather than
 *      copying it -- and degrades to the old brief when that module is not
 *      loaded. Since 2026-09-14 it is COLLAPSED by default and revealed in
 *      place: the detail pane is Shadow's control room, and the transcript
 *      was the longest block on it. Nothing was removed and nothing moved;
 *      a shut chat is simply not drawn, and so is not polled either.
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
  assert(/where it runs/.test(h) && /a new chat/.test(h),
    "no session: the existing brief row is untouched");
  assert.strictEqual(ctx.fetched.length, 0, "no session: nothing is fetched");
  console.log("ok 1 no session -> the brief, unchanged");
}

/* ── 2-7: THE CARD IS NOT A CHAT, AND HAS NO DOOR OF ITS OWN ─────────────
   (founder, 2026-09-15.) The inline "Show worker chat" toggle and the
   transcript it revealed are gone from the card: "Open the chat" in the RHS
   header is the single entry point to the delegate's conversation.

   NOTHING UNDERNEATH WAS REMOVED. shadowTaskChatHtml still renders that
   conversation through the same Assignment machinery, the data-shtaskchat
   handler still exists, and the throttled transcript READER is still live --
   it feeds the one-line agent block instead of an inline chat. So the fetch
   discipline these tests were written for still matters, and it is asserted
   on the pane, which is what reads now. */

/* the whole right pane, the way the app renders it */
function pane(ctx, m){
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  ctx.S.shadowMissions = [Object.assign({}, BASE, m)];
  ctx.S.shadowTaskSel = BASE.id;
  return ctx.shadowHomeHtml();
}

/* 2. no toggle, no transcript, and the brief is untouched */
{
  const ctx = fresh(true);
  ctx.S.goalTranscript = { "sid-1": [{ role: "assistant", text: "working on it" }] };
  const h = card(ctx, { state: "brief_confirm", target_session: "sid-1" });
  assert(!/gwchat/.test(h), "the card must not render the transcript");
  assert(!/working on it/.test(h), "no conversation text on the card");
  assert(!/data-shtaskchat/.test(h), "the inline door must be gone");
  assert(!/worker chat/i.test(h), "the toggle label must be gone");
  assert.strictEqual(ctx.fetched.length, 0, "the card must fetch nothing");
  /* the control room itself is untouched */
  assert(/where it runs/.test(h) && />turn</.test(h),
    "the brief rows must survive");
  console.log("ok 2 the card carries no worker-chat door and no transcript");
}

/* 2b. ONE DOOR, in the header, and it is the real session */
{
  const ctx = fresh(true);
  const h = pane(ctx, { state: "running", target_session: "sid-1" });
  assert.deepStrictEqual((h.match(/data-shtakeover="[^"]*"/g) || []),
    ['data-shtakeover="sid-1"'],
    "exactly one way into the worker chat, carrying the real session id");
  assert(/Open the chat/.test(h), "and it is labelled");
  assert(!/data-shtaskchat/.test(h), "no second door anywhere in the pane");
  console.log("ok 2b Open the chat is the only entry to the worker chat");
}

/* 2c. THE CONVERSATION RENDERER IS INTACT -- nothing was ripped out, it is
   simply not drawn on this card any more. */
{
  const ctx = fresh(true);
  ctx.S.goalTranscript = { "sid-1": [{ role: "assistant", text: "working on it" }] };
  const block = ctx.shadowTaskChatHtml(
    Object.assign({}, BASE, { state: "running", target_session: "sid-1" }));
  assert(/gwchat/.test(block) && /working on it/.test(block),
    "shadowTaskChatHtml must still render the delegate conversation");
  assert.strictEqual(typeof ctx.shadowTaskTranscript, "function",
    "the transcript reader must still exist");
  console.log("ok 2c the transcript machinery is untouched, just not drawn");
}

/* 4. nothing held yet -> exactly one fetch, and no report to draw */
{
  const ctx = fresh(true);
  const h = pane(ctx, { state: "running", target_session: "sid-3" });
  assert.deepStrictEqual(ctx.fetched, ["sid-3"], "one fetch for one session");
  assert(!/class="shagent"/.test(h),
    "nothing fetched yet -> no agent line, rather than a placeholder");
  console.log("ok 4 one fetch, and nothing claimed before it lands");
}

/* 5. RENDER STORM GUARD: render() runs many times a second */
{
  const ctx = fresh(true);
  ctx.S.goalTranscript = { "sid-4": [] };
  for (let i = 0; i < 25; i++) pane(ctx, { state: "running", target_session: "sid-4" });
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
  pane(ctx, { state: "running", target_session: "sid-5" });
  assert.strictEqual(ctx.fetched.length, 0,
    "an open pane must not be fetched a second time");
  console.log("ok 6 open pane is left to its own reader");
}

/* 7. DEGRADATION: the Assignment module was not loaded */
{
  const ctx = fresh(false);
  let h = null;
  assert.doesNotThrow(() => {
    h = pane(ctx, { state: "running", target_session: "sid-6" });
  }, "a context without the goal module must not throw");
  assert(!/gwchat/.test(h), "without the module there is nothing to draw");
  assert(!/data-shtaskchat/.test(h), "and no door to it either");
  assert(/where it runs/.test(h), "the brief still renders");
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
