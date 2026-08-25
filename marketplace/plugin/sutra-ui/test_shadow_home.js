#!/usr/bin/env node
/* test_shadow_home.js -- PLAN-100 S81-S90: the Focus > Shadow home.
   Run: node test_shadow_home.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
assert(/16-shadow-home\.js/.test(html), "panel.html loads the home module");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn)=>({fn}),
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {},
    document: { addEventListener(){}, createElement(){ return {
      setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);   /* missionCardHtml + shared thread */
  vm.runInContext(src, ctx);
  return ctx;
}

const MISSIONS = [
  { id: "m-1", objective: "fix nav", state: "running", turns_used: 3, max_turns: 20 },
  { id: "m-2", objective: "research Y", state: "queued" },
  { id: "m-3", objective: "ship Z", state: "paused" },
  { id: "m-4", objective: "old", state: "done" },
];

/* 1. S81: screen + title registered; dark state honest */
{
  const ctx = fresh();
  assert(typeof ctx.SCREENS.shadow === "function", "SCREENS.shadow registered");
  assert(ctx.TITLES.shadow[0] === "Shadow", "TITLES row present");
  ctx.S.shadowHomeDark = true;
  assert(/not enabled/.test(ctx.SCREENS.shadow()), "dark = honest zero state");
  console.log("ok 1 registration + dark");
}

/* 2. S82: the home renders the SAME thread array the overlay card uses */
{
  const ctx = fresh();
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowThread = [{ who: "shadow", text: "the-one-thread-msg" }];
  assert(/the-one-thread-msg/.test(ctx.shadowHomeHtml()), "home renders it");
  assert(/the-one-thread-msg/.test(ctx.shadowCardHtml()), "card renders it");
  console.log("ok 2 one thread, two views");
}

/* 3. S83: plane tabs + counts; done missions excluded from Working */
{
  const ctx = fresh();
  const w = ctx.shadowPlaneHtml(["s-1", "s-2"], MISSIONS, "watching");
  assert(/Watching \u00b7 2/.test(w) && /Working \u00b7 3/.test(w),
    "live counts (done excluded)");
  assert(/data-shunwatch="s-1"/.test(w), "watch rows have toggles");
  console.log("ok 3 plane + counts");
}

/* 4. S85: mission rows carry exactly the legal actions for their state */
{
  const ctx = fresh();
  const g = ctx.shadowPlaneHtml([], MISSIONS, "working");
  assert(/data-shact="start_now" data-shmid="m-2"/.test(g), "queued: Start now");
  assert(/data-shact="drop"[\s\S]{0,60}data-shmid="m-2"/.test(g),
    "queued: Drop");
  assert(/data-shact="resume" data-shmid="m-3"/.test(g), "paused: Resume");
  assert(/data-shact="stop" data-shmid="m-1"/.test(g), "running: Stop");
  assert(!/data-shmid="m-4"/.test(g), "done missions leave the plane");
  console.log("ok 4 mission actions");
}

/* 5. S86/S87: memory -- inert until confirmed, revoke is the undo */
{
  const ctx = fresh();
  const rows = [
    { id: "i-1", text: "caveman prose", precedence: "d_ledger",
      confirmed: true },
    { id: "i-2", text: "maybe this", precedence: "history",
      confirmed: false },
    { id: "i-3", text: "old rule", precedence: "taste", confirmed: true,
      revoked_at: "2026-08-25" },
  ];
  const h = ctx.shadowMemoryHtml(rows);
  assert(/data-shrevoke="i-1"/.test(h), "confirmed rows can be revoked");
  assert(/unconfirmed \u00b7 inert/.test(h) && /data-shconfirm="i-2"/.test(h),
    "unconfirmed rows are visibly inert with one-tap confirm");
  assert(/shmem-dead/.test(h) && /revoked/.test(h),
    "revoked rows stay visible, struck through (archive never delete)");
  console.log("ok 5 memory");
}

/* 6. the controls are WIRED (the recurring lesson, pinned per surface) */
assert(/d\.shact && d\.shmid/.test(src), "home mission actions handled");
assert(/shadowWatchSet/.test(src) && /shadowInstructionAct/.test(src),
  "watch + memory controls must act");
assert(/shhomecompose/.test(src) && /sendToShadow/.test(src),
  "the home composer must send");
console.log("ok 6 controls wired");

console.log("test_shadow_home.js: all green");
