#!/usr/bin/env node
/* test_shadow_task_status.js -- the list and the card must agree.
 *
 * THE REPORT (founder, 2026-09-14): "LHS says RUNNING, task detail says
 * QUEUED, turn 0 of 20", for what looked like one mission.
 *
 * IT WAS NEVER ONE MISSION. Both surfaces already read the same record and
 * both already call shadowTaskFaceFor, so for a running mission both say
 * RUNNING -- asserted below so it stays that way. What diverged was WHICH
 * mission the card was given: shadowSelectedTask's fallback ranked
 * `brief_confirm` above `running`, and a brief_confirm row whose start was
 * already accepted (start_requested_at set) draws as QUEUED / turn 0 /
 * "a new chat Shadow starts when you begin" indefinitely. One stale row --
 * a start that died before the transition table could record it -- captured
 * the detail pane for every task created afterwards.
 *
 * The split is made with shadowMissionStartable, the predicate the card
 * already uses to decide whether to draw Start. No new state, no local
 * "hasStarted", and nothing inferred from whether a chat exists.
 *
 * Run: node test_shadow_task_status.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function fresh(){
  const ctx = {
    console, Date, setTimeout: () => ({}),
    S: {}, SCREENS: {}, TITLES: {},
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    document: {
      addEventListener(){}, body: { appendChild(){} },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8"), ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8"), ctx);
  return ctx;
}

const M = (over) => Object.assign({
  id: "m", objective: "o", template: "fix", target_mode: "new",
  target_session: null, target_chat: null, turns_used: 0, max_turns: 20,
  done_when: [],
}, over);

/* the row a start already claimed: QUEUED / turn 0, and it never moves */
const STALE = M({ id: "m-stale", state: "brief_confirm",
  start_requested_at: "2026-09-14T12:09:35Z" });
/* a brief nobody has started: genuinely READY, wants the founder's click */
const READY = M({ id: "m-ready", state: "brief_confirm" });
/* the task the founder just created and watched start */
const LIVE = M({ id: "m-live", state: "running", turns_used: 3,
  target_session: "sid-1", target_chat: "c-1",
  start_requested_at: "2026-09-14T12:37:21Z" });

const pill = (h) => (h.match(/shtpill-[a-z]*"?\s*>([^<]*)</) || [])[1];
const turn = (h) => (h.match(/turn ([^<]*)</) || [])[1];

function ctxWith(rows, selId){
  const ctx = fresh();
  ctx.S.shadowMissions = rows;
  ctx.S.goals = [];
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowTaskSel = selId || null;
  return ctx;
}

/* 1. THE REGRESSION: a stale pre-start row must not capture the card */
{
  const ctx = ctxWith([STALE, LIVE], null);
  const sel = ctx.shadowSelectedTask();
  assert.strictEqual(sel.id, "m-live",
    "with a running task present, a start-already-taken brief_confirm row " +
    "must not be what the detail card shows");
  const card = ctx.shadowTaskCardHtml(sel);
  assert.strictEqual(pill(card), "RUNNING", "detail pill must say RUNNING");
  assert.strictEqual(turn(card), "3 of 20", "turn count comes from the record");
  assert(!/data-shstart=/.test(card), "a running task offers no Start");
  console.log("ok 1 stale QUEUED row no longer captures the detail card");
}

/* 2. THE TWO SURFACES USE ONE SOURCE -- asserted, not assumed */
{
  const ctx = ctxWith([LIVE], "m-live");
  const listFace = ctx.shadowTaskFaceFor(
    ctx.shadowTasks().find(m => m.id === "m-live"));
  const cardFace = ctx.shadowTaskFaceFor(ctx.shadowSelectedTask());
  assert.deepStrictEqual(listFace, cardFace,
    "list and card must derive the face from the same record");
  assert.strictEqual(listFace.label, "RUNNING");
  console.log("ok 2 list and card share one backend-driven face");
}

/* 3. a genuinely READY brief still outranks live work -- it wants the click */
{
  const ctx = ctxWith([LIVE, READY], null);
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-ready",
    "an unstarted brief is still the thing that needs the founder");
  console.log("ok 3 READY still outranks running");
}

/* 4. blocked is still the top of the order (floor_confirm -> NEEDS YOU) */
{
  const blocked = M({ id: "m-blk", state: "blocked" });
  const ctx = ctxWith([READY, LIVE, blocked], null);
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-blk",
    "blocked must keep its place at the top, untouched");
  console.log("ok 4 blocked keeps the top of the order");
}

/* 5. an explicit pick always wins -- the fallback is only a fallback */
{
  const ctx = ctxWith([STALE, LIVE], "m-stale");
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-stale",
    "clicking a row must still select it");
  console.log("ok 5 an explicit selection is never overridden");
}

/* 6. a start already taken still READS as QUEUED -- that mapping is kept */
{
  const ctx = ctxWith([STALE], "m-stale");
  assert.strictEqual(ctx.shadowTaskFaceFor(STALE).label, "QUEUED",
    "the starting face is unchanged; only its RANK in the fallback moved");
  console.log("ok 6 the QUEUED face itself is unchanged");
}

/* 7. THE CANONICAL VOCABULARY, on the card, from mission state alone */
{
  const ctx = fresh();
  const face = (m) => pill(ctx.shadowTaskCardHtml(M(m)));
  assert.strictEqual(face({ state: "running" }), "RUNNING", "running");
  assert.strictEqual(face({ state: "paused" }), "PAUSED", "paused");
  assert.strictEqual(face({ state: "done" }), "DONE", "done");
  assert.strictEqual(face({ state: "failed" }), "FAILED", "failed");
  assert.strictEqual(face({ state: "queued" }), "QUEUED", "queued");
  assert.strictEqual(face({ state: "brief_confirm" }), "READY", "ready");
  /* founder-needed: the existing paused + pause_reason predicate */
  assert.strictEqual(
    face({ state: "paused", pause_reason: "founder_confirm" }), "NEEDS YOU",
    "founder_confirm must read as NEEDS YOU");
  assert.strictEqual(
    face({ state: "paused", pause_reason: "floor_confirm" }), "NEEDS YOU",
    "floor_confirm must read as NEEDS YOU");
  console.log("ok 7 one state vocabulary, straight from mission state");
}

/* 8. the turn counter tracks the record, it is not pinned to 0 */
{
  const ctx = fresh();
  const at = (n) => turn(ctx.shadowTaskCardHtml(
    M({ state: "running", turns_used: n, max_turns: 20 })));
  assert.strictEqual(at(0), "0 of 20");
  assert.strictEqual(at(1), "1 of 20");
  assert.strictEqual(at(7), "7 of 20");
  console.log("ok 8 the turn counter follows the mission record");
}

console.log("\nall shadow task-status tests passed");
