#!/usr/bin/env node
/* test_shadow_v4_oversee.js -- Shadow v4 step 15 (C10, ADR-043): the working
   chat's "Shadow is driving" strip carries the way back to the task -- one
   click to the task's own chat in Focus > Shadow -- beside Take over and
   Stop. The strip itself (turn n / max, done when, Take over, Stop) is the
   one 2.278.x ships; test_panel.js 33b renders it for real.

   Run: node test_shadow_v4_oversee.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const render = fs.readFileSync(path.join(__dirname, "static", "js", "06-render.js"), "utf8");
const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

/* 1. the strip's action group carries the Shadow button, first, beside the two
      it always had -- read off the source the browser runs */
{
  const i = render.indexOf('class="shdriveacts"');
  assert(i !== -1, "the strip's action group exists");
  const acts = render.slice(i, render.indexOf("</span>", i));
  const order = ["data-shopentask", "data-shtakeoverchat", "data-shstopchat"]
    .map(k => acts.indexOf(k));
  assert(order.every(x => x !== -1), "Shadow, Take over and Stop are all there: " + order);
  assert(order[0] < order[1] && order[1] < order[2], "Shadow first, then Take over, then Stop");
  assert(/Shadow \\u203a|Shadow ›/.test(acts), "the button reads Shadow ›");
  console.log("ok 1 the strip carries Shadow, Take over, Stop in that order");
}

/* 2. clicking Shadow puts the task in focus and routes to its chat */
function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }),
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {}, routed: [],
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  ctx.shadowRouteDeepLink = (l) => ctx.routed.push(l);
  return ctx;
}
{
  const ctx = fresh();
  ctx.S.screen = "chats";
  ctx.listeners.click({ target: { dataset: { shopentask: "m-fruits" }, closest: () => null } });
  assert.strictEqual(ctx.S.shadowTaskSel, "m-fruits", "the task is selected");
  assert.deepStrictEqual(ctx.routed, ["sutra://shadow/m-fruits"], "routed to the task's chat");
  console.log("ok 2 Shadow routes to the task's own chat in Focus > Shadow");
}

/* 3. Take over and Stop keep their own hooks (nothing removed) */
{
  const ctx = fresh();
  const acts = [];
  ctx.shadowMissionAct = async (id, act) => { acts.push([id, act]); return { id }; };
  ctx.listeners.click({ target: { dataset: { shtakeoverchat: "m-1" }, closest: () => null } });
  ctx.listeners.click({ target: { dataset: { shstopchat: "m-1" }, closest: () => null } });
  assert.deepStrictEqual(acts.map(a => a[1]), ["take_over", "stop"]);
  console.log("ok 3 Take over and Stop are untouched");
}

console.log("test_shadow_v4_oversee: all ok");
