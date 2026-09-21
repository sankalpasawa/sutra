#!/usr/bin/env node
/* test_shadow_conversation.js -- the conversational Shadow surface
   (founder, 2026-09-21).

   WHAT THIS LANE PINS, and all three are defects the founder named:

     1. A DECISION IS RENDERED EXACTLY ONCE. A founder_confirm check used to
        carry a live Confirm button in shadowAskRowsHtml (inside the
        timeline) AND another in shadowCheckRowsHtml (below it), in the same
        paused/founder_confirm state. Two working buttons for one criterion,
        and answering either left the other looking unanswered.

     2. SUPERSEDED WORK IS SHOWN, NOT VANISHED. MissionStore.amend strips
        every verdict the old objective earned, and the screen used to say
        nothing -- the founder's Africa question was simply absent on the
        next render. "Outdated" and "never happened" are different claims.

     3. SUPERSEDED WORK IS INERT. A struck-through check that still carried
        a button would be the worst of both: visibly dead and mechanically
        live. This asserts there is no button, no hook and no index in it.

   Run: node test_shadow_conversation.js
*/
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const css = fs.readFileSync(
  path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }),
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: {
      addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  return ctx;
}
const C = fresh();

let passed = 0;
function ok(name, fn){
  try { fn(); passed++; }
  catch (e){
    console.error("FAIL: " + name + "\n  " + (e && e.message));
    process.exitCode = 1;
  }
}

/* A mission parked on the founder's signature -- the state in which the two
   surfaces used to both draw a button. */
function awaiting(extra){
  return Object.assign({
    id: "m-1",
    objective: "Plan a personal trip to Africa for 10 days.",
    state: "paused",
    pause_reason: "founder_confirm",
    turns_used: 4, max_turns: 25,
    done_when: [
      { tier: "founder_confirm", check: "The itinerary is feasible for 10 days." },
      { tier: "judge", check: "Every day has lodging.", met: true },
    ],
  }, extra || {});
}

/* ─────────────────────────────────── 1. one decision, one place ───────── */

ok("the timeline no longer draws a second Confirm for a done-when check", () => {
  const html = C.shadowAskRowsHtml(awaiting());
  assert(!/data-shkind="confirm"/.test(html),
    "shadowAskRowsHtml still emits a confirm action");
  assert(!/shask-check/.test(html),
    "the duplicate check row is still rendered");
});

ok("the canonical decision surface still draws exactly one Confirm", () => {
  const html = C.shadowCheckRowsHtml(awaiting());
  const n = (html.match(/data-shcheckix=/g) || []).length;
  assert.strictEqual(n, 1, "expected exactly one confirm control, got " + n);
});

ok("the two surfaces never both carry a control for the same check", () => {
  const m = awaiting();
  const both = C.shadowAskRowsHtml(m) + C.shadowCheckRowsHtml(m);
  const controls = (both.match(/data-shcheckix=|data-shkind="confirm"/g) || []);
  assert.strictEqual(controls.length, 1,
    "one criterion must yield one control, got " + controls.length);
});

ok("a settled check is not offered for signature at all", () => {
  const m = awaiting();
  m.done_when[0].met = true;
  const html = C.shadowCheckRowsHtml(m);
  assert(!/data-shcheckix=/.test(html), "a signed check still offers Confirm");
});

ok("the holding and intervention rows are untouched", () => {
  const m = awaiting({ approval: { id: "a1" }, pending_say: "carry on" });
  const html = C.shadowAskRowsHtml(m);
  assert(/data-shact="approve"/.test(html), "the approval row was lost");
  const iv = C.shadowAskRowsHtml(awaiting({
    intervention: { id: "i1", question: "Which airline?" } }));
  assert(/Which airline\?/.test(iv), "the intervention question was lost");
});

/* ────────────────────────────────────── 2. superseded work is shown ───── */

const REVISED = awaiting({
  objective: "Plan a personal trip to India for 10 days.",
  version: 2,
  done_when: [{ tier: "founder_confirm", check: "The India itinerary is feasible." }],
  revisions: [{
    version: 1,
    objective: "Plan a personal trip to Africa for 10 days.",
    checks: [
      { check: "The Africa itinerary is feasible for 10 days.",
        tier: "founder_confirm", met: true },
      { check: "Every Africa day has lodging.", tier: "judge", met: false },
    ],
    at: "2026-09-21T02:00:00Z",
  }],
});

ok("a mission with no revisions renders nothing", () => {
  assert.strictEqual(C.shadowRevisionsHtml(awaiting()), "");
  assert.strictEqual(C.shadowRevisionsHtml({}), "");
  assert.strictEqual(C.shadowRevisionsHtml(null), "");
});

ok("the superseded objective is named", () => {
  const html = C.shadowRevisionsHtml(REVISED);
  assert(/Plan a personal trip to Africa for 10 days\./.test(html),
    "the abandoned objective is not shown");
});

ok("the superseded criteria are counted, not printed", () => {
  /* "Don't show user stuff he doesn't care about (Done checks and all)."
     Listing every retired predicate struck through put the longest strings
     in the product on screen to say something the founder already knows. */
  const html = C.shadowRevisionsHtml(REVISED);
  assert(/2 checks retired with it/.test(html), "the count is missing");
  assert(!/The Africa itinerary is feasible for 10 days\./.test(html),
    "a retired criterion is still printed");
  assert(!/Every Africa day has lodging\./.test(html),
    "a retired criterion is still printed");
});

ok("the live objective is NOT drawn as superseded", () => {
  const html = C.shadowRevisionsHtml(REVISED);
  assert(!/India/.test(html),
    "the current objective leaked into the outdated block");
});

/* ────────────────────────────────────────── 3. superseded work is inert ── */

ok("a superseded check carries no control of any kind", () => {
  const html = C.shadowRevisionsHtml(REVISED);
  assert(!/<button/.test(html), "the outdated block contains a button");
  assert(!/data-shact/.test(html), "the outdated block carries an action hook");
  assert(!/data-shcheckix/.test(html), "the outdated block carries a check index");
  assert(!/data-shkind/.test(html), "the outdated block carries an answer hook");
});

ok("a founder signature on the old revision is not shown as still standing", () => {
  const html = C.shadowRevisionsHtml(REVISED);
  assert(!/you confirmed it/.test(html),
    "an old signature is presented as though it still applies");
  assert(/Superseded by your latest instruction/.test(html),
    "the block does not say what happened");
});

ok("the outdated rows are struck through by stylesheet, not by markup", () => {
  assert(/\.shstalecheck \.shchecktxt\{text-decoration:line-through/.test(css),
    "panel.css does not strike the superseded rows");
});

ok("only the most recent revision is drawn", () => {
  const many = awaiting({ revisions: [
    { version: 1, objective: "Africa", checks: [{ check: "africa check" }] },
    { version: 2, objective: "Peru",   checks: [{ check: "peru check" }] },
  ]});
  const html = C.shadowRevisionsHtml(many);
  assert(/Peru/.test(html), "the latest superseded objective is missing");
  assert(!/Africa/.test(html), "an older revision is stacked on the screen");
});

/* ───────────────────────────────── the header reflects the real state ─── */

/* The end-to-end render of these states is pinned by test_shadow_home.js
   block 23b/c, which drives SCREENS.shadow with a real selection. What is
   asserted here is the GUARD ITSELF -- that Stop stands down on the
   needs-founder predicate and not on a state name, which is the distinction
   the first cut of this change got wrong. */
ok("Stop stands down on the needs-founder predicate, not on a state name", () => {
  assert(/!shadowMissionNeedsFounder\(sel\)[\s\S]{0,160}data-shact="stop"/.test(src),
    "the Stop guard no longer keys on shadowMissionNeedsFounder");
});

ok("Stop is still reachable for every non-NEEDS-YOU working state", () => {
  assert(/\["running", "paused", "blocked"\]\.includes\(sel\.state\)[\s\S]{0,160}data-shact="stop"/.test(src),
    "a stalled or blocked task lost the control that ends work");
});

ok("the workspace draws Stop from exactly one site", () => {
  /* shadowPlaneHtml -- the WATCHING screen's mission rows -- has always had
     its own stop and is a different surface; it is excluded by name rather
     than by counting, so a third site anywhere still fails this. */
  const workspace = src.slice(src.indexOf("function shadowTaskCardHtml"));
  /* the MARKUP pattern, not the bare attribute: the note at the button's
     new site names the hook in prose, and a comment is not a control. */
  const drawn = workspace.match(/type="button" data-shact="stop"/g) || [];
  assert.strictEqual(drawn.length, 1,
    "the workspace draws Stop from " + drawn.length + " sites");
  const card = src.slice(src.indexOf("function shadowTaskCardHtml"),
                         src.indexOf("function shadowHomeHtml"));
  assert(!/`<button[\s\S]{0,120}data-shact="stop"/.test(card),
    "the task card still draws its own Stop");
});

ok("Resume is still offered at NEEDS YOU", () => {
  assert(/\["paused", "blocked"\]\.includes\(m\.state\)[\s\S]{0,180}data-shact="resume"/.test(src),
    "Resume was lost from the paused state");
});

/* ───────────────────────────────────── the left nav is not a casualty ─── */

ok("the left navigation is untouched", () => {
  assert(typeof C.shadowTaskListHtml === "function", "the task list is gone");
  assert(typeof C.shadowNavHtml === "function", "the settings door is gone");
  assert(/data-shscreen="shadowsettings"/.test(C.shadowNavHtml()),
    "Shadow settings no longer reachable from the nav");
});

/* ═════════════════════════════════ PASS 2 ═══════════════════════════════ */

/* ── the final-state summary replaces the tally ───────────────────────── */

const DONE_INDIA = {
  id: "m-1", state: "done",
  objective: "Plan a personal trip to India for 10 days.",
  completion: {
    objective: "Plan a personal trip to India for 10 days.",
    headline: "3 of 3 checks passed",
    checks_met: 3, checks_total: 3, checks: [],
    completed: ["The India itinerary is feasible for 10 days.",
                "Every day has lodging."],
    remains: ["Prices are estimates, not bookings."],
    artifacts: ["india-trip-plan.md"],
    revised: 1,
    was: "Plan a personal trip to Africa for 10 days.",
    turns_used: 6, max_turns: 25,
  },
};

ok("the founder is not shown the check tally", () => {
  const html = C.shadowCompletionHtml(DONE_INDIA);
  assert(!/3 of 3 checks passed/.test(html),
    "the internal tally is still the headline");
  assert(/Done/.test(html), "the plain ending is missing");
});

ok("no criterion reaches the completion surface", () => {
  /* "Even in summary -- don't show user stuff he doesn't care about (Done
     checks and all)." A done_when predicate is written to be MATCHED, not
     read; a list of them is a QA report however it is worded. */
  const html = C.shadowCompletionHtml(DONE_INDIA);
  const visible = html.slice(0, html.indexOf("<details"));
  assert(!/What I completed/.test(visible), "the check list still leads");
  assert(!/What remains/.test(visible), "the unmet checks still lead");
  assert(!/The India itinerary is feasible for 10 days\./.test(visible),
    "a criterion is on the primary surface");
  assert(!/Prices are estimates, not bookings\./.test(visible),
    "an unmet criterion is on the primary surface");
});

ok("what the founder CAN act on still leads", () => {
  const html = C.shadowCompletionHtml(DONE_INDIA);
  assert(/Done/.test(html), "the plain ending is missing");
  assert(/What you can open/.test(html), "the artifact section is missing");
  assert(/india-trip-plan\.md/.test(html), "the artifact is not named");
});

ok("every criterion is still one click away, whole", () => {
  const html = C.shadowCompletionHtml(Object.assign({}, DONE_INDIA, {
    completion: Object.assign({}, DONE_INDIA.completion, {
      checks: [{ check: "each line is a specific, current MotoGP news item "
                      + "drawn from a real source rather than filler",
                 met: true, how: "Shadow checked this" }] }) }));
  const fold = html.slice(html.indexOf("<details"));
  assert(/Verification/.test(fold), "the fold is gone");
  assert(/each line is a specific, current MotoGP news item drawn from a real source rather than filler/
    .test(fold), "the criterion was truncated or dropped from the record view");
});

ok("a failed check is signalled without printing the criterion", () => {
  const html = C.shadowCompletionHtml(Object.assign({}, DONE_INDIA, {
    completion: Object.assign({}, DONE_INDIA.completion, {
      checks: [{ check: "the dates are right", met: false, how: "not settled" }]
    }) }));
  const visible = html.slice(0, html.indexOf("<details"));
  assert(/did not pass/.test(visible), "the founder is not told something failed");
  assert(!/the dates are right/.test(visible),
    "the criterion itself is on the primary surface");
});

ok("the summary describes the FINAL revision, never the abandoned one", () => {
  const html = C.shadowCompletionHtml(DONE_INDIA);
  const completed = html.slice(html.indexOf("What I completed"));
  assert(!/Africa/.test(completed),
    "abandoned work is reported as part of the result");
});

ok("the abandoned objective appears only as history", () => {
  const html = C.shadowCompletionHtml(DONE_INDIA);
  assert(/Replaced an earlier plan/.test(html),
    "the founder is not told a plan was replaced");
  assert(/Plan a personal trip to Africa for 10 days\./.test(html),
    "the superseded objective is not named");
});

ok("the artifact is named, and it is this mission's", () => {
  const html = C.shadowCompletionHtml(DONE_INDIA);
  assert(/india-trip-plan\.md/.test(html));
  assert(!/africa-trip-plan/.test(html),
    "another revision's artifact leaked into the result");
});

ok("a completion stamped before these fields still renders", () => {
  const old = { id: "m-2", state: "done", completion: {
    headline: "1 of 2 checks passed", checks: [
      { check: "it holds together", met: true, how: "Shadow checked this" },
      { check: "the dates are right", met: false, how: "not settled" }],
    turns_used: 3, max_turns: 10 } };
  const html = C.shadowCompletionHtml(old);
  assert(/Done/.test(html), "a record without the new fields renders nothing");
  assert(/did not pass/.test(html), "the founder is not told something failed");
  const fold = html.slice(html.indexOf("<details"));
  assert(/the dates are right/.test(fold), "the criterion left the record view");
});

/* ── the composer is never a form field for the open question ─────────── */

ok("the composer invites a reply OR a change at NEEDS YOU", () => {
  C.S.shadowMissions = [awaiting()];
  C.S.shadowTaskSel = "m-1";
  assert(/Reply, or change the plan/.test(C.shadowComposePlaceholder(true)),
    "the founder is left looking trapped in the structured question");
});

ok("the composer is a plain conversation while running", () => {
  C.S.shadowMissions = [awaiting({ state: "running", pause_reason: null })];
  C.S.shadowTaskSel = "m-1";
  assert(/Talk to Shadow/.test(C.shadowComposePlaceholder(true)));
});

/* ── why the founder is the one being asked ───────────────────────────── */

ok("the decision carries a closed why-am-I-needed line", () => {
  const html = C.shadowCheckRowsHtml(awaiting());
  assert(/Why am I needed\?/.test(html), "the affordance is missing");
  assert(!/<details class="shwhyme" open/.test(html),
    "it must be closed by default");
});

/* ── the outdated block stays history, not an error ───────────────────── */

ok("the outdated block reads as history", () => {
  const html = C.shadowRevisionsHtml(REVISED);
  assert(/Superseded by your latest instruction\./.test(html));
  assert(!/error|failed|warning|problem/i.test(html),
    "superseded work is dressed as a failure");
});

ok("the thread opens with what the founder ORIGINALLY asked for", () => {
  /* After a redirect `objective` is the NEW one, so opening on it made the
     thread read "Plan a trip to India" three messages above the founder
     saying "actually, I want India". */
  const html = C.shadowOpeningHtml(REVISED);
  assert(/Plan a personal trip to Africa for 10 days\./.test(html),
    "the opening line is not the founder's original ask");
  assert(!/India/.test(html), "the current objective opened the thread");
});

ok("an unrevised task opens on its own objective", () => {
  const html = C.shadowOpeningHtml(awaiting());
  assert(/Plan a personal trip to Africa for 10 days\./.test(html));
});

ok("the opening message is the founder speaking, and carries no controls", () => {
  const html = C.shadowOpeningHtml(awaiting());
  assert(/You \u2192 Shadow/.test(html), "it is not attributed to the founder");
  assert(!/<button/.test(html) && !/data-shact/.test(html),
    "the opening line carries a control");
});

ok("the metadata card no longer draws the conversation surface", () => {
  C.S.shadowMissions = [awaiting()];
  C.S.shadowTaskSel = "m-1";
  C.S.shadowWatching = []; C.S.goals = [];
  const stream = C.shadowTimelineHtml(awaiting());
  assert(!/shcard2k">where it runs</.test(stream),
    "WHERE IT RUNS is still on the conversation surface");
  assert(!/shcard2k">done when</.test(stream),
    "DONE WHEN is still on the conversation surface");
  /* The header carries the objective; the stream does not restate it. */
  assert(!/class="shsaid shopening"/.test(stream),
    "the objective is restated under the header it is already in");
});

ok("the decision, the outdated block and the completion are IN the stream", () => {
  const stream = C.shadowTimelineHtml(REVISED);
  assert(/class="shsaid shstale"/.test(stream), "outdated is not in the stream");
  assert(/shconfirmq/.test(stream), "the decision is not in the stream");
  const done = C.shadowTimelineHtml(DONE_INDIA);
  assert(/shdonesum/.test(done), "the completion is not in the stream");
});

ok("the forward fence never reaches the founder", () => {
  /* THE BUG THIS LANE EXISTS FOR: the forwarding lane added a ```forward
     fence to Shadow's reply and did not add it to the prose stripper, so a
     verdict meant for the app arrived as literal {"worker": false} in the
     middle of a sentence the founder was reading. */
  const raw = 'Got it, I will pass that on.\n\n```forward\n{"worker": true}\n```';
  assert(!/worker/.test(C.shadowProseText(raw)),
    "the forward fence leaks into the conversation");
  assert(/Got it, I will pass that on\./.test(C.shadowProseText(raw)),
    "and the reply itself must survive");
});

ok("every protocol fence the parser accepts is also stripped from prose", () => {
  const ov = require("fs").readFileSync(
    require("path").join(__dirname, "static/js/15-shadow-overlay.js"), "utf8");
  const stripped = (ov.match(/```\(\?:([a-z|]+)\)/) || [])[1] || "";
  for (const kind of ["mission", "goal", "chips", "remember", "module",
                      "brief", "forward"]){
    assert(stripped.split("|").indexOf(kind) !== -1,
      "the prose stripper does not know the " + kind + " fence");
  }
});

console.log("test_shadow_conversation.js  " +
  (process.exitCode ? "FAIL" : "PASS") + "  " + passed + " checks");
