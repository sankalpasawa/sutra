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
  assert(!/data-shact="resume"|data-shact="stop"/.test(card), "Stop and Resume stay off the card (2026-09-15 ruling)");
  const spent = ctx.shadowTaskCardHtml(Object.assign({}, HELD, { approval: Object.assign({}, HELD.approval, { used: true }) }));
  assert(!/data-shapprove/.test(spent), "a spent approval draws nothing");
  console.log("ok 4 the task card shows the held string with Approve");
}

console.log("test_shadow_v4_approve: all ok");
