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
    console, _timers: [],
    setTimeout: (fn, ms)=>{ const t = { fn, ms }; ctx._timers.push(t); return t; },
    clearTimeout(){},
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
  assert(/class="nyprod">Org</.test(out),
         "another producer keeps its tag (Now is a multi-producer surface)");
  assert(/class="nygo">Review</.test(out), "the row names its action (shown on hover)");
  assert(!/<button/.test(out), "no button inside a row: the whole row is the click (2026-09-27)");
  assert.strictEqual(ctx.needsYouHtml([]), "", "empty feed renders nothing");
  console.log("ok 1 pure renderer");
}

/* 2. SCREENS.now: placeholder when dark/empty, cards when items exist */
{
  const ctx = fresh(false);
  ctx.S.needsYou = null;             /* feature dark (403) */
  const off = ctx.SCREENS.now();
  assert(/Shadow is off/.test(off),
         "a dark feed says Shadow is off, never 'nothing needs you' (2026-09-27)");
  assert(!/data-nyask="1"/.test(off), "no box that sends to a Shadow that is off");
  ctx.S.needsYou = [];
  const empty = ctx.SCREENS.now();
  assert(/Nothing needs you right now/.test(empty),
         "an empty feed renders the honest empty state");
  assert(/data-nystart/.test(empty),
         "the empty state must offer a way to start talking to Shadow");
  ctx.S.needsYou = ITEMS;
  assert(/nyfeed/.test(ctx.SCREENS.now()), "items render as rows");
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
  assert.strictEqual(ctx._timers[0].ms, 6000,
    "the default lifetime every existing caller was written against");
  console.log("ok 4 nudge");
}

/* 4b. the OPTIONAL duration. A caller needing a different life says so, and
   the default above is what proves the other callers were not moved. */
{
  const ctx = fresh(true);
  const el = ctx.showNudge("This chat will use OpenAI Codex.", 5000);
  assert.strictEqual(el.textContent, "This chat will use OpenAI Codex.");
  assert.strictEqual(ctx._timers[0].ms, 5000, "an explicit duration is honoured");
  console.log("ok 4b nudge duration");
}

/* founder 2026-09-16: opening a card marks it SEEN and keeps it on Now
   until the task moves on (the relevance rule retires it). The dot stops
   counting it; the cached list is kept so the card does not blink away. */
{
  const ctx = fresh();
  const posts = [];
  ctx.S.needsYou = [{ item_id: "item-9", state: "new", kind: "needs_decision" }];
  ctx.shadowPost = (path, body) => { posts.push({ path, body });
    return Promise.resolve({ ok: true }); };
  ctx.shadowRouteDeepLink = () => true;
  ctx.openNeedsYouItem("sutra://shadow/home", "item-9");
  assert.strictEqual(posts[0].path, "/api/shadow/feed/handle");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(posts[0].body)),
    { item_id: "item-9" }, "open marks the card seen");
  assert.ok(Array.isArray(ctx.S.needsYou) && ctx.S.needsYou.length === 1,
    "the card stays in the cached list");
  assert.strictEqual(ctx.S.needsYou[0].state, "seen",
    "and is drawn as seen until the next poll");
  const html = ctx.needsYouHtml(ctx.S.needsYou);
  assert.ok(/class="nycard[^"]* seen"/.test(html), "the seen look is a class");
  console.log("ok 5 seen on open, the card stays");
}

/* Layout A (founder 2026-09-27): two lanes -- what needs a decision, then FYI --
   plain reasons, one card per task, the box last and pinned. */

/* 6. two lanes, and the greeting counts decisions only */
{
  const ctx = fresh(false);
  ctx.S.needsYou = ITEMS;                          /* 1 decision + 1 update */
  const h = ctx.SCREENS.now();
  assert(/nylane nydecide/.test(h) && /nylane nyfyilane/.test(h), "two lanes");
  assert(h.indexOf("nydecide") < h.indexOf("nyfyilane"), "decisions first, then FYI");
  assert(/what can we do for you\?/.test(h), "the Codex-style greeting (2026-09-27)");
  assert(h.indexOf('data-nyask="1"') < h.indexOf("nydecide"), "the bar on top, rows under it");
  assert(!/class="nynow center"/.test(h), "rows on screen: not centred");
  console.log("ok 6 two lanes under the bar");
}

/* 7. stalls in different tasks stay separate and never show the generic
   title; the producer tag shows only for a producer other than Shadow */
{
  const ctx = fresh(false);
  const old = "mission may be stalled -- nothing from its session for 4 min";
  const rows = ["m-a", "m-b", "m-c"].map(id => ({ item_id: "stall-" + id,
    producer: "shadow", kind: "needs_decision", title: old,
    deep_link: "sutra://shadow/mission/" + id, dedupe_key: "stall:" + id, state: "new" }));
  const h = ctx.needsYouHtml(rows);
  assert.strictEqual((h.match(/class="nycard/g) || []).length, 3, "one card per stalled task");
  assert(!/mission may be stalled/.test(h), "the generic title is rewritten");
  assert(/Silent for 4 min/.test(h), "the reason is plain");
  const named = ctx.needsYouHtml([{ item_id: "stall-m-d", mission_id: "m-d",
    producer: "shadow", kind: "needs_decision", title: "Weekly digest",
    why_now: "silent for 6 min", deep_link: "sutra://shadow/mission/m-d",
    dedupe_key: "stall:m-d", state: "new" }]);
  assert(/Weekly digest/.test(named) && /Silent for 6 min/.test(named),
         "a named stall reads as its task");
  assert(!/class="nyprod"/.test(named), "no Shadow tag on Shadow's own cards");
  console.log("ok 7 stalls stay separate and named");
}

/* 8. reasons read as plain words, never as a code */
{
  const ctx = fresh(false);
  const codes = ["needs_founder", "autonomy_top_tier", "no_live_runtime",
                 "error_during_execution", "founder_confirm"];
  const rows = codes.map((c, i) => ({ item_id: "r-" + i, mission_id: "m-" + i,
    producer: "shadow", kind: "needs_decision", title: "Task " + i, why_now: c,
    deep_link: "sutra://x/" + i, dedupe_key: "k" + i, state: "new" }));
  const h = ctx.needsYouHtml(rows);
  for (const c of codes)
    assert(h.indexOf(c) === -1 && h.indexOf(c.replace(/_/g, " ")) === -1, "raw code shown: " + c);
  assert(/Waiting for your answer/.test(h) && /Needs your go-ahead before it runs/.test(h));
  console.log("ok 8 plain reasons");
}

/* 9. the decision waiting longest comes first; FYI newest first, three shown,
   the rest behind "Show N more" */
{
  const ctx = fresh(false);
  const row = (kind, p, t) => ({ item_id: p + t, mission_id: "m" + p + t,
    producer: "shadow", kind, title: (kind === "info" ? "Update " : "Decide ") + t,
    ts: t, deep_link: "sutra://" + p + "/" + t, dedupe_key: p + t, state: "new" });
  const all = [300, 100, 200].map(t => row("needs_decision", "d", t))
    .concat([10, 50, 20, 40, 30].map(t => row("info", "f", t)));
  const h = ctx.needsYouHtml(all);
  assert(h.indexOf("Decide 100") < h.indexOf("Decide 200")
      && h.indexOf("Decide 200") < h.indexOf("Decide 300"), "oldest decision first");
  assert(h.indexOf("Update 50") < h.indexOf("Update 40")
      && h.indexOf("Update 40") < h.indexOf("Update 30"), "newest update first");
  assert(!/Update 20/.test(h) && !/Update 10/.test(h), "three updates shown");
  assert(/data-nymore="1">2 more</.test(h), "the rest behind '2 more'");
  ctx.S.nyFyiAll = true;
  assert(/Update 10/.test(ctx.needsYouHtml(all)), "Show more reveals every update");
  console.log("ok 9 order and the FYI cap");
}

/* 10. nothing to decide: the same page -- greeting, the door to Shadow,
   updates still listed, the box still there */
{
  const ctx = fresh(false);
  ctx.S.needsYou = [ITEMS[1]];
  const h = ctx.SCREENS.now();
  assert(/Nothing needs you right now/.test(h) && /data-nystart/.test(h));
  assert(!/nydecide/.test(h) && /nyfyilane/.test(h), "no empty decision lane; updates listed");
  assert(/class="nyhero"/.test(h), "one layout: the greeting stays");
  assert(/data-nyask="1"/.test(h), "the box stays");
  console.log("ok 10 nothing to decide keeps the page");
}

/* Restyle (founder 2026-09-27: "it's boxes ... show me empty states, error
   states"): rows with a status dot, and every state says what is true. */

/* 11. first load: quiet placeholder rows, never an empty claim before the
   feed has answered */
{
  const ctx = fresh(false);
  const h = ctx.SCREENS.now();                    /* S.needsYou undefined */
  assert(/Checking what needs you/.test(h));
  assert(!/Nothing needs you/.test(h), "no empty claim before the first answer");
  console.log("ok 11 first load");
}

/* 16. the home (founder 2026-09-27): with nothing under the bar, the
   greeting and the bar sit in the middle of the screen */
{
  const ctx = fresh(false);
  ctx.S.needsYou = [];
  const h = ctx.SCREENS.now();
  assert(/class="nynow center"/.test(h), "empty: centred");
  assert(/Good (morning|afternoon|evening), what can we do for you\?/.test(h));
  assert(/data-nyask="1"/.test(h), "the bar is there when nothing is");
  ctx.S.needsYou = null;
  assert(/class="nynow center"/.test(ctx.SCREENS.now()), "Shadow off: centred too");
  console.log("ok 16 centred home");
}

/* 12. feed trouble: with rows, one line on top (since when, Try again) and
   the last known rows stay; with none, the line replaces the empty claim */
{
  const ctx = fresh(false);
  ctx.S.needsYou = ITEMS;
  ctx.S.nyErr = Date.now() - 6 * 60 * 1000;
  const h = ctx.SCREENS.now();
  assert(/class="nyerr"/.test(h) && /Couldn't refresh since/.test(h)
      && /data-nyretry="1"/.test(h), "one trouble line with Try again");
  assert(/Mission m-1 needs a yes/.test(h), "the last known rows stay");
  ctx.S.needsYou = [];
  const none = ctx.SCREENS.now();
  assert(/Couldn't load what needs you/.test(none) && /data-nyretry="1"/.test(none));
  assert(!/Nothing needs you/.test(none), "a failed load never claims all clear");
  console.log("ok 12 feed trouble");
}

/* 14. the dot says what kind of wait it is, at a glance */
{
  const ctx = fresh(false);
  const mk = over => Object.assign({ producer: "shadow", kind: "needs_decision",
    title: "T", deep_link: "sutra://x", dedupe_key: "k", state: "new" }, over);
  const tone = it => (/tone-(\w+)/.exec(ctx.needsYouHtml([it])) || [])[1];
  assert.strictEqual(tone(mk({ item_id: "rescue-s1" })), "err", "a broken session");
  assert.strictEqual(tone(mk({ item_id: "stall-m1" })), "warn", "a task gone quiet");
  assert.strictEqual(tone(mk({ item_id: "f1", why_now: "needs_founder" })), "ask", "yours to answer");
  assert.strictEqual(tone(mk({ item_id: "i1", kind: "info", why_now: "mission failed" })), "err");
  assert.strictEqual(tone(mk({ item_id: "i2", kind: "info", why_now: "1 of 1 checks passed" })), "ok");
  console.log("ok 14 status dots");
}

/* 15. every row can be reached from the keyboard */
{
  const ctx = fresh(false);
  const h = ctx.needsYouHtml(ITEMS);
  assert.strictEqual((h.match(/tabindex="0" role="button"/g) || []).length, 2,
                     "both rows are focusable buttons");
  console.log("ok 15 keyboard reachable");
}

/* 13. loadNeedsYou marks trouble on a failed answer and clears it on the
   next good one (async, so it runs last) */
(async () => {
  const ctx = fresh(false);
  let status = 500;
  ctx.fetch = () => Promise.resolve({ ok: status === 200, status,
    json: () => Promise.resolve({ items: ITEMS }) });
  const tick = () => new Promise(r => setImmediate(r));
  ctx.loadNeedsYou(); await tick(); await tick();
  assert.ok(ctx.S.nyErr > 0, "a 500 marks trouble");
  const first = ctx.S.nyErr;
  ctx.loadNeedsYou(); await tick(); await tick();
  assert.strictEqual(ctx.S.nyErr, first, "trouble keeps the time it started");
  status = 200;
  ctx.loadNeedsYou(); await tick(); await tick();
  assert.strictEqual(ctx.S.nyErr, 0, "a good answer clears it");
  assert.strictEqual(ctx.S.needsYou.length, 2);
  console.log("ok 13 trouble marked and cleared");
  console.log("test_shadow_now.js: all green");
})();
