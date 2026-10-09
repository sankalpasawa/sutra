#!/usr/bin/env node
/* test_shadow_cant_start.js -- a task Shadow could not start says why, with
   one action (founder, 2026-10-08, from Paperclip). The face is CAN'T START
   under WAITING ON YOU, the pane shows the reason with Try again (the
   existing data-shstart hook), and a task that is merely READY or already
   starting is drawn exactly as before.

   Run: node test_shadow_cant_start.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate, Promise,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {}, click(){} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  ctx.scheduleRender = () => {};
  ctx.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}

const BLOCKED = { id: "m-cant1", state: "brief_confirm", start_requested_at: null,
  start_blocked: { reason: "Shadow tried 4 times and the connection to Claude <dropped>." } };
const READY = { id: "m-ready1", state: "brief_confirm", start_requested_at: null };
const STARTING = { id: "m-go1", state: "brief_confirm",
  start_requested_at: "2026-10-08T10:00:00Z",
  start_blocked: { reason: "stale reason from before Try again" } };

let n = 0;
function test(name, fn){ fn(); n++; console.log("ok   " + name); }

test("a task that could not start reads CAN'T START, under WAITING ON YOU", () => {
  const ctx = fresh();
  assert.strictEqual(ctx.shadowTaskFaceFor(BLOCKED).label, "CAN'T START");
  assert.strictEqual(ctx.shadowTaskFaceFor(BLOCKED).cls, "blocked");
  assert.strictEqual(ctx.shadowTaskSection(BLOCKED), "wait");
});

test("READY and a start on its way keep the faces they had", () => {
  const ctx = fresh();
  assert.strictEqual(ctx.shadowTaskFaceFor(READY).label, "READY");
  assert.strictEqual(ctx.shadowTaskFaceFor(STARTING).label, "QUEUED",
    "once Try again is pressed the old reason no longer shows");
  assert.strictEqual(ctx.shadowCantStartHtml(READY), "");
  assert.strictEqual(ctx.shadowCantStartHtml(STARTING), "");
});

test("the pane says why, escaped, with one action on the existing Start hook", () => {
  const ctx = fresh();
  const h = ctx.shadowCantStartHtml(BLOCKED);
  assert(/Couldn't start/.test(h));
  assert(/connection to Claude &lt;dropped>/.test(h), "the reason is escaped");
  assert(/data-shstart="m-cant1">Try again<\/button>/.test(h));
  assert.strictEqual((h.match(/<button/g) || []).length, 1, "one action");
});

test("the pane draws the notice where the founder looks, before the ask", () => {
  const i = home.indexOf("shadowCantStartHtml(sel)");
  const j = home.indexOf("shadowInterventionHtml(sel)}");
  assert(i > 0 && j > i);
});

test("the header never offers Start the task beside Try again", () => {
  assert(/!shadowMissionCantStart\(sel\)\s*\n\s*&& \(typeof shadowMissionStartable/.test(home));
});

test("its style uses tokens only", () => {
  const block = css.slice(css.indexOf(".shcant{"));
  const rules = block.slice(0, block.indexOf(".shcantv{") + 80);
  assert(!/#[0-9a-fA-F]{3,6}\b|rgba?\(/.test(rules), "no colour literal");
});

console.log("test_shadow_cant_start.js: " + n + " passed");
