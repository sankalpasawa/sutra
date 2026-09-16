#!/usr/bin/env node
/* test_shadow_v4_prose.js -- Shadow v4 step 12 (C6, ADR-043): the Shadow view
   shows Shadow's words and its cards, nothing else.

   A Shadow chat is a normal Claude Code session, so its raw turns carry the
   bracket header, INPUT/TYPE/ROUTE runs, FLOW boxes, the OS trace and the
   protocol fences. shadowProseText strips those at the presentation boundary;
   shadowProseHtml renders what is left as markdown when mdHtml is loaded.
   The founder's own words are never touched.

   Run: node test_shadow_v4_prose.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
assert(/15-shadow-overlay\.js/.test(html), "panel.html loads the overlay module");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const goals = fs.readFileSync(
  path.join(__dirname, "static", "js", "18-goal-workspace.js"), "utf8");

function fresh(extra){
  const ctx = Object.assign({
    console, Date, setTimeout: (fn) => ({ fn }),
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, S: {},
    listeners: {},
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  }, extra || {});
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  return ctx;
}

const RAW = [
  "[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]",
  "",
  "INPUT: founder wants a top-10 fruit list",
  "TYPE: task",
  "ROUTE: delegate",
  "",
  "+-- FLOW ---------------------------+",
  "| Unit: research fruits             |",
  "| [1] TYPE: task / cell x           |",
  "+-----------------------------------+",
  "",
  "Got it. Research task. Done when you have a **table** of fruits by usage.",
  "",
  "```mission",
  "{\"objective\": \"Top 10 fruits\", \"template\": \"research\"}",
  "```",
  "",
  "OS: Input Routing (task) > Depth 3 > 2 tool calls > done",
].join("\n");

/* 1. the belt alone (no gvBody, no mdHtml): only the sentence survives */
{
  const ctx = fresh();
  const text = ctx.shadowProseText(RAW);
  assert.strictEqual(text,
    "Got it. Research task. Done when you have a **table** of fruits by usage.");
  const out = ctx.shadowProseHtml(RAW);
  assert(/Got it\. Research task\./.test(out), "the sentence is shown");
  assert(!/INBOUND/.test(out), "no bracket header");
  assert(!/INPUT:|TYPE:|ROUTE:/.test(out), "no routing block");
  assert(!/FLOW/.test(out), "no FLOW box");
  assert(!/mission/.test(out), "no protocol fence");
  assert(!/Depth 3/.test(out), "no OS trace");
  console.log("ok 1 belt strips header, routing, box, fence, trace");
}

/* 2. mdHtml, when loaded, renders what is left */
{
  const ctx = fresh({ mdHtml: (s) => "<MD>" + s + "</MD>" });
  const out = ctx.shadowProseHtml(RAW);
  assert(/^<MD>Got it\./.test(out), "rendered through mdHtml");
  assert(!/INBOUND|FLOW|```/.test(out));
  console.log("ok 2 markdown renderer is used when present");
}

/* 3. gvBody, when loaded, runs first and its answer is what is shown */
{
  const calls = [];
  const ctx = fresh({ gvBody: (s) => { calls.push(s); return "from gvBody **x**"; } });
  const out = ctx.shadowProseHtml(RAW);
  assert.strictEqual(calls.length, 1, "gvBody consulted once");
  assert(/from gvBody/.test(out));
  console.log("ok 3 the chat pane's scrubber is consulted first");
}

/* 4. a code fence is the reply's own and stays; a plain OS mention stays */
{
  const ctx = fresh();
  const text = ctx.shadowProseText("Run this:\n```bash\nls -la\n```\nOS: macOS 14 is fine.");
  assert(/```bash\nls -la\n```/.test(text), "code fence kept");
  assert(/OS: macOS 14 is fine\./.test(text), "a bare OS line is prose");
  console.log("ok 4 code fences and plain OS lines survive");
}

/* 5. empty in, empty out; governance-only in, empty out (nothing invented) */
{
  const ctx = fresh();
  assert.strictEqual(ctx.shadowProseHtml(""), "");
  assert.strictEqual(ctx.shadowProseHtml("INPUT: x\nTYPE: y\nROUTE: z"), "");
  console.log("ok 5 nothing is generated for a scaffolding-only turn");
}

/* 6. the corner card: Shadow's turn as prose, the founder's verbatim */
{
  const ctx = fresh({ mdHtml: (s) => "<MD>" + s + "</MD>" });
  ctx.S.shadowThread = [
    { who: "shadow", text: "[INBOUND·DIRECT · x]\nHello **there**" },
    { who: "founder", text: "**raw** <b>" },
  ];
  ctx.S._shadowIntroSeeded = true;
  const card = ctx.shadowCardHtml();
  assert(/shshadow[\s\S]*<MD>Hello \*\*there\*\*<\/MD>/.test(card), "Shadow turn is prose");
  assert(!/INBOUND/.test(card), "header stripped from the card");
  assert(/shmine[\s\S]*\*\*raw\*\* &lt;b>/.test(card), "founder turn verbatim, escaped");
  console.log("ok 6 the corner card renders the thread through the filter");
}

/* 7. Focus > Shadow renders the same thread the same way */
{
  const ctx = fresh({ mdHtml: (s) => "<MD>" + s + "</MD>" });
  vm.runInContext(home, ctx);
  ctx.S.shadowHomeDark = false;
  ctx.S.shadowThread = [
    { who: "shadow", text: "+-- FLOW --+\n| x |\n+----+\nDone with the list." },
  ];
  const page = ctx.shadowHomeHtml();
  assert(/<MD>Done with the list\.<\/MD>/.test(page), "home thread is prose");
  assert(!/FLOW/.test(page), "box stripped on the home thread");
  console.log("ok 7 the home thread renders through the filter");
}

/* 8. the task chat transcript: chat and Shadow turns as prose, you verbatim */
{
  const ctx = fresh({ mdHtml: (s) => "<MD>" + s + "</MD>" });
  vm.runInContext(goals, ctx);
  const rows = ctx.goalTranscriptHtml([
    { role: "assistant", text: "TRIAGE: depth_selected=3\nESTIMATE: x\nList done: **10 fruits**." },
    { role: "user", text: "make it **shorter**" },
    { role: "user", text: "[Shadow · mission m-1] Continue toward: the table" },
  ], { target_session: "s-1" });
  assert(/gwturn-chat[\s\S]*<MD>List done: \*\*10 fruits\*\*\.<\/MD>/.test(rows), "chat turn is prose");
  assert(!/TRIAGE/.test(rows), "triage stripped");
  assert(/gwturn-founder[\s\S]*make it \*\*shorter\*\*/.test(rows), "founder verbatim");
  assert(!/gwturn-founder[\s\S]*<MD>make it/.test(rows), "founder not markdown-rendered");
  assert(/gwturn-shadow[\s\S]*<MD>Continue toward: the table<\/MD>/.test(rows), "Shadow turn is prose, tag stripped");
  console.log("ok 8 the transcript renders chat and Shadow turns through the filter");
}

console.log("test_shadow_v4_prose: all ok");
