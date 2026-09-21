#!/usr/bin/env node
/* test_shadow_v4_approve.js -- Shadow v4 step 19 fold (codex P2): a held say
   carries a one-use approval, and the founder can give it from the product:
   the task row shows Approve, primary, which posts action approve with the
   approval id; Resume stays beside it; a used approval shows no Approve.

   Run: node test_shadow_v4_approve.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }),
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}
const HELD = { id: "m-1", objective: "Ship the fix", state: "paused",
  pause_reason: "floor_confirm", turns_used: 2, max_turns: 12,
  pending_say: "Now run git push --force to origin main.",
  approval: { id: "ap-abc123", reason: "floor_confirm", used: false } };

/* 1. the row shows Approve, primary, with the approval id, beside Resume */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [HELD];
  const h = ctx.shadowPlaneHtml([], [HELD], "working");
  assert(/data-shact="approve"[\s\S]*data-shapproval="ap-abc123"/.test(h), "Approve carries the approval id");
  assert(/class="btn pri" type="button" data-shact="approve"/.test(h), "Approve is the primary");
  assert(/data-shact="resume"/.test(h), "Resume stays");
  assert(h.indexOf('data-shact="approve"') < h.indexOf('data-shact="resume"'), "Approve first");
  console.log("ok 1 a held say shows Approve, primary, beside Resume");
}

/* 2. clicking Approve posts action approve with the approval id */
{
  const ctx = fresh();
  const acts = [];
  ctx.shadowMissionAct = async (id, act, extra) => { acts.push([id, act, extra]); return { id }; };
  ctx.listeners.click({ target: { dataset: { shact: "approve", shmid: "m-1", shapproval: "ap-abc123" },
    closest: () => null } });
  /* objects cross the vm boundary with another Object prototype, so compare by
     value, not by deepStrictEqual (which also checks the prototype) */
  assert.strictEqual(JSON.stringify(acts), JSON.stringify([["m-1", "approve", { approval_id: "ap-abc123" }]]));
  ctx.listeners.click({ target: { dataset: { shact: "resume", shmid: "m-1" }, closest: () => null } });
  assert.strictEqual(JSON.stringify(acts[1]), JSON.stringify(["m-1", "resume", null]), "other actions carry no extra");
  console.log("ok 2 Approve posts the one-use approval id; Resume is unchanged");
}

/* 3. a used approval, or a pause with none, shows no Approve */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [
    Object.assign({}, HELD, { id: "m-2", approval: Object.assign({}, HELD.approval, { used: true }) }),
    { id: "m-3", objective: "x", state: "paused", pause_reason: "app_restart", turns_used: 1, max_turns: 12 },
  ];
  const h = ctx.shadowPlaneHtml([], ctx.S.shadowMissions, "working");
  assert(!/data-shact="approve"/.test(h), "no Approve without a live approval");
  assert((h.match(/data-shact="resume"/g) || []).length === 2, "Resume on both");
  console.log("ok 3 no Approve on a spent approval or a plain pause");
}

/* 4. the task card in Focus > Shadow shows the exact held string and Approve */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [HELD];
  const card = ctx.shadowTaskCardHtml(HELD);
  assert(/data-shapprove="m-1"/.test(card), "the approval block is on the card");
  assert(/Now run git push --force to origin main\./.test(card), "the exact string is shown");
  assert(/data-shact="approve"[\s\S]*data-shapproval="ap-abc123"/.test(card), "Approve carries the id");
  /* RESUME STAYS OFF THE CARD; STOP CAME BACK (founder, 2026-09-16, one day
     after the ruling this line encodes). The 2026-09-15 decision removed both
     on the stated understanding that "the same two buttons on the same two
     hooks still render in shadowPlaneHtml" -- and they do, on the WATCHING
     screen. SCREENS.shadow renders this card, so on the surface the founder
     works from, a running task offered its state pill, "Open the chat" and
     nothing else: the founder reported it as "no visible Stop action", and
     the fix is cd72e43d. Rendering pristine v4 confirms it was still true
     here -- SCREENS.shadow for a running task draws no data-shact hook at
     all, only the x that DELETES the task.

     Only the Stop half moves. Resume is still not drawn on this card, so the
     other half of the ruling is asserted exactly as v4 wrote it. */
  assert(!/data-shact="resume"/.test(card), "Resume stays off the card");
  /* AND STOP STANDS DOWN HERE TOO (founder, 2026-09-21: "do not show Stop
     as though a worker is currently burning turns"). `floor_confirm` is one
     of the four founder pauses: the loop is parked holding an instruction
     until the founder answers, so no turn is in flight and Stop advertised
     a cost that was not being incurred.

     REFUSAL IS NOT LOST, which is the only thing that would have made this
     wrong. The hold row carries Withdraw (data-shkind="withdraw") -- the
     control that actually answers "no" to a held instruction -- and the
     task-list row keeps its own stop for ending the task outright. Stop
     returns on this card the moment the hold is answered. The predicate is
     shadowMissionNeedsFounder, so a task paused for a STALL still offers it
     (test_shadow_home 23b/c). */
  assert(!/data-shact="stop"/.test(card),
    "a task waiting on the founder must not offer Stop");
  const spent = ctx.shadowTaskCardHtml(Object.assign({}, HELD, { approval: Object.assign({}, HELD.approval, { used: true }) }));
  assert(!/data-shapprove/.test(spent), "a spent approval draws nothing");
  console.log("ok 4 the task card shows the held string with Approve");
}

console.log("test_shadow_v4_approve: all ok");
