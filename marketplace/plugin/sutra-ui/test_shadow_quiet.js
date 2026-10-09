#!/usr/bin/env node
/* test_shadow_quiet.js -- a worker gone quiet mid-turn is said on its task
   before Shadow's 4-minute stall end (founder, 2026-10-08: "keep the
   4-minute end, add a warning"). The server sends `quiet` from 2 minutes;
   the pane says how long and when the step ends. Nothing else changes.

   Run: node test_shadow_quiet.js */
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

const RUN = { id: "m-q1", state: "running" };

let n = 0;
function test(name, fn){ fn(); n++; console.log("ok   " + name); }

test("nothing when the worker is not quiet, or the task is not running", () => {
  const ctx = fresh();
  assert.strictEqual(ctx.shadowQuietHtml(RUN), "");
  assert.strictEqual(ctx.shadowQuietHtml(Object.assign({}, RUN,
    { state: "paused", quiet: { secs: 150, ends_in: 90 } })), "");
  assert.strictEqual(ctx.shadowQuietHtml(null), "");
});

test("two and a half minutes quiet: how long, and when the step ends", () => {
  const ctx = fresh();
  const h = ctx.shadowQuietHtml(Object.assign({}, RUN, { quiet: { secs: 150, ends_in: 90 } }));
  assert(/No new output for 2 min/.test(h));
  assert(/running something long, or it may be stuck/.test(h));
  assert(/ends this step in about 2 min/.test(h));
  assert(!/<button/.test(h), "it only says so; it has no control");
});

test("at the end it says the step is ending now", () => {
  const ctx = fresh();
  const h = ctx.shadowQuietHtml(Object.assign({}, RUN, { quiet: { secs: 240, ends_in: 0 } }));
  assert(/No new output for 4 min/.test(h) && /ends this step now/.test(h));
});

test("the pane draws it beside the other task notices", () => {
  const i = home.indexOf("shadowCantStartHtml(sel)}");
  const j = home.indexOf("shadowQuietHtml(sel)}");
  const k = home.indexOf("shadowInterventionHtml(sel)}");
  assert(i > 0 && j > i && k > j);
});

test("its style uses tokens only", () => {
  const block = css.slice(css.indexOf(".shquiet{"));
  const rules = block.slice(0, block.indexOf(".shquietv{") + 80);
  assert(!/#[0-9a-fA-F]{3,6}\b|rgba?\(/.test(rules), "no colour literal");
});

console.log("test_shadow_quiet.js: " + n + " passed");
