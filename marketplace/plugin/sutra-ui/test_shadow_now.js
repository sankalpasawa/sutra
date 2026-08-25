#!/usr/bin/env node
/*
 * test_shadow_now.js -- PLAN-100 S59/S60/S62: the Now surface consumes the
 * needs-you feed, render-only. Loads the REAL module under vm with minimal
 * stubs and asserts on real function output.
 *
 * Run: node test_shadow_now.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

/* panel.html must actually load the module (a written-but-unwired module is
   dead code, and this is the check that catches it) */
const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
assert(/14-needs-you\.js/.test(html), "panel.html loads 14-needs-you.js");

const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "14-needs-you.js"), "utf8");

function fresh(withDom){
  const ctx = {
    console, setTimeout: (fn)=>({fn}), clearTimeout(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    SCREENS: {}, S: {}, goneTo: [],
    goDest(d){ ctx.goneTo.push(d); },
  };
  if (withDom){
    const removed = [];
    ctx.document = {
      created: [],
      createElement(tag){
        const el = { tagName: tag, className: "", textContent: "",
                     remove(){ removed.push(el); } };
        ctx.document.created.push(el);
        return el;
      },
      body: { appended: [], appendChild(el){ ctx.document.body.appended.push(el); } },
      addEventListener(){},
    };
    ctx._removed = removed;
  }
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

const ITEMS = [{
  item_id: "f-1", producer: "shadow", kind: "needs_decision",
  title: "Mission m-1 needs a yes", why_now: "floor tripped",
  primary_action: "Review", deep_link: "sutra://shadow/mission/m-1",
  dedupe_key: "m-1:paused:v1", state: "new",
}, {
  item_id: "f-2", producer: "org", kind: "info",
  title: "Charter A1 awaiting ratification",
  deep_link: "sutra://org/charter/a1", dedupe_key: "org:a1", state: "new",
}];

/* 1. pure renderer: cards carry title, producer tag, deep link, action */
{
  const ctx = fresh(false);
  const out = ctx.needsYouHtml(ITEMS);
  assert(/Mission m-1 needs a yes/.test(out), "title rendered");
  assert(/data-deeplink="sutra:\/\/shadow\/mission\/m-1"/.test(out), "deep link on card");
  assert(/nyprod/.test(out) && /shadow/.test(out) && /org/.test(out),
         "producer tags rendered (Now is a multi-producer surface)");
  assert(/data-nyact="f-1"/.test(out), "primary action is a button");
  assert.strictEqual(ctx.needsYouHtml([]), "", "empty feed renders nothing");
  console.log("ok 1 pure renderer");
}

/* 2. SCREENS.now: placeholder when dark/empty, cards when items exist */
{
  const ctx = fresh(false);
  ctx.S.needsYou = null;             /* feature dark (403) */
  assert(/Nothing needs you right now/.test(ctx.SCREENS.now()),
         "dark feed renders the honest empty state");
  ctx.S.needsYou = ITEMS;
  assert(/nyfeed/.test(ctx.SCREENS.now()), "items render as cards");
  console.log("ok 2 screen states");
}

/* 3. S60 deep link: records intent + navigates to focus, mutates nothing */
{
  const ctx = fresh(false);
  ctx.openNeedsYouItem("sutra://shadow/mission/m-1");
  assert.strictEqual(ctx.S.pendingDeepLink, "sutra://shadow/mission/m-1");
  assert.deepStrictEqual(ctx.goneTo, ["focus"], "navigates to Focus");
  console.log("ok 3 deep link");
}

/* 4. S62 nudge: ephemeral, appended, never navigates */
{
  const ctx = fresh(true);
  const el = ctx.showNudge("Shadow finished mission m-1");
  assert.strictEqual(el.className, "nudge");
  assert.strictEqual(ctx.document.body.appended.length, 1);
  assert.deepStrictEqual(ctx.goneTo, [], "a nudge never navigates");
  console.log("ok 4 nudge");
}

console.log("test_shadow_now.js: all green");
