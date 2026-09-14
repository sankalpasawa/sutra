#!/usr/bin/env node
/* test_shadow_floor_needs_you.js -- a floor pause is a REQUEST (2026-09-14).
   Run: node test_shadow_floor_needs_you.js

   WHY THIS FILE EXISTS. run_mission pauses with pause_reason="floor_confirm"
   when the say it wants to make trips a floor and therefore needs founder
   authority before it may leave the engine. The engine already classes that
   with founder_confirm -- MissionEngine.pending_confirmations() returns
   exactly those two as the decisions awaiting an answer -- but the UI
   predicate recognised only founder_confirm. So Shadow stopped BECAUSE it
   needed the founder and the card said PAUSED, which tells the founder that
   nothing is being asked of them. That is the misleading half of the North
   Star: hide the machinery, never hide the accountability.

   No new state and no new vocabulary: the mission is still `paused`, and the
   face it borrows is the existing `blocked` face the engine already uses for
   "Shadow cannot go on without you". */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn)=>({fn}),
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

function mission(pause_reason){
  const m = { id: "m-floor", objective: "email the vendor", state: "paused",
    template: "fix", target_mode: "new", target_session: "sess-floor",
    turns_used: 3, max_turns: 20, done_when: [] };
  if (pause_reason !== undefined) m.pause_reason = pause_reason;
  return m;
}

/* -- the predicate itself -------------------------------------------- */
{
  const ctx = fresh();
  assert.strictEqual(ctx.shadowMissionNeedsFounder(mission("floor_confirm")),
    true, "floor_confirm needs the founder");
  assert.strictEqual(ctx.shadowMissionNeedsFounder(mission("founder_confirm")),
    true, "founder_confirm still needs the founder");

  /* every pause that is NOT a request stays a plain pause */
  ["app_restart", "founder_intervened", "queued_behind", "", "who_knows"]
    .forEach((r) => {
      assert.strictEqual(ctx.shadowMissionNeedsFounder(mission(r)), false,
        r + " is not a request for the founder");
    });
  assert.strictEqual(ctx.shadowMissionNeedsFounder(mission(undefined)), false,
    "a pause with no reason asks nothing");

  /* and a mission that is not paused at all is never a request */
  assert.strictEqual(ctx.shadowMissionNeedsFounder(
    { id: "x", state: "running", pause_reason: "floor_confirm" }), false,
    "the state still gates the predicate -- only a PAUSED mission asks");
  assert.strictEqual(ctx.shadowMissionNeedsFounder(null), false);
  console.log("ok 1 shadowMissionNeedsFounder: both confirm pauses, and only those");
}

/* -- the face it wears, which is what the founder actually sees ------- */
{
  const ctx = fresh();
  const face = ctx.shadowTaskFaceFor(mission("floor_confirm"));
  assert.strictEqual(face.label, "NEEDS YOU", "floor_confirm reads NEEDS YOU");
  assert.strictEqual(face.cls, "blocked", "it wears the existing needs-you pill");
  assert.strictEqual(ctx.shadowTaskFaceFor(mission("founder_confirm")).label,
    "NEEDS YOU", "founder_confirm is unchanged");
  assert.strictEqual(ctx.shadowTaskFaceFor(mission("app_restart")).label,
    "PAUSED", "a restart is still PAUSED");
  assert.strictEqual(ctx.shadowTaskFaceFor(mission("founder_intervened")).label,
    "PAUSED", "an intentional pause is still PAUSED");

  /* NO NEW STATE WAS INVENTED. shadowTaskFace is the state->face map and is
     untouched: `paused` still reads PAUSED there. All that changed is which
     face the MISSION-aware caller picks for a mission carrying a floor. */
  assert.strictEqual(ctx.shadowTaskFace("paused").label, "PAUSED",
    "the state map still calls a paused mission PAUSED");
  assert.strictEqual(ctx.shadowTaskFace("blocked").label, "NEEDS YOU",
    "NEEDS YOU is the EXISTING blocked face, not a new one");
  console.log("ok 2 the face: NEEDS YOU for a floor, PAUSED for everything else");
}

/* -- end to end, through the real rendering --------------------------- */
{
  const render = (reason) => {
    const ctx = fresh();
    ctx.S.shadowHomeDark = false;
    ctx.S.shadowMissions = [mission(reason)];
    ctx.S.shadowTaskSel = "m-floor";
    return ctx.shadowHomeHtml();
  };

  const floor = render("floor_confirm");
  assert(!/>PAUSED</.test(floor),
    "a mission waiting on founder authority must not read as PAUSED");
  assert(/>NEEDS YOU</.test(floor), "the card says NEEDS YOU");
  assert(/shtpill-blocked/.test(floor), "and wears the needs-you pill family");

  const restart = render("app_restart");
  assert(/>PAUSED</.test(restart), "a restart pause still reads PAUSED");
  assert(!/>NEEDS YOU</.test(restart),
    "nothing is being asked, so nothing may claim to be");

  const confirm = render("founder_confirm");
  assert(/>NEEDS YOU</.test(confirm), "founder_confirm is untouched");
  console.log("ok 3 rendered: the founder can see which pauses are requests");
}

console.log("test_shadow_floor_needs_you.js: all green");
