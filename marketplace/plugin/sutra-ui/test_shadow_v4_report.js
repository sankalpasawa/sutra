#!/usr/bin/env node
/* test_shadow_v4_report.js -- the Worker's own REPORT line, and the rule that
 * a turn says nothing until it has finished saying it.
 *
 * TWO CHANGES, ONE SURFACE (founder, 2026-09-16). The line under WORKER AGENT
 * used to be an EXCERPT -- the first sentence shadowSayGist could salvage out
 * of the turn's prose. An excerpt only accidentally answers the question the
 * heading asks, and on a turn that was still running it was answering it about
 * work that had not happened yet.
 *
 *   1. THE WORKER WRITES THE LINE. app._WORKER_AGREEMENT asks for
 *      "REPORT: <one sentence>" on a line of its own -- the same shape as the
 *      DONE-CHECK line beside it -- and shadowSayReport SELECTS it. No model
 *      is asked, no sentence is composed, and a turn with no REPORT falls back
 *      to exactly the behaviour it had before.
 *
 *   2. A TURN IN FLIGHT SHOWS ITS NUMBER AND NOTHING ELSE. `turn_open` is the
 *      engine's own signal for the turn being worked (mission_engine.run_
 *      mission stamps it before the wait, clears it on the boundary) and
 *      /api/shadow/missions has always carried it. No timer, no heuristic, no
 *      new state.
 *
 * WHAT THIS FILE DOES NOT TEST: everything test_shadow_rhs.js already pins --
 * ordering, asides, the ask, the story, the control-plane filter. Those lanes
 * are unchanged and must stay that way.
 *
 * Run: node test_shadow_v4_report.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(
  path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const src = fs.readFileSync(
  path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");

function fresh(){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){},
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    fetched: [], posted: [],
    listeners: {},
    document: {
      addEventListener(t, fn){
        (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  ctx.loadGoalTranscript = (sid) => { ctx.fetched.push(sid); };
  ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
  ctx.goalTranscriptHtml = (msgs) => "";
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "Write the fixture file", template: "fix",
  target_mode: "new", target_session: "sess-1", target_chat: "c-1",
  state: "running", turns_used: 1, max_turns: 12,
  done_when: [{ check: "the file exists", tier: "founder_confirm" }],
}, over);

const SH = (ts) => ({ role: "user", text: "[Shadow · mission m-1] carry on",
                      ts: ts || "" });
const W = (text, ts) => ({ role: "assistant", text: text, ts: ts || "" });

/* render the whole right pane the way the app does, and read the timeline
   back as (heading, line) pairs -- a turn with no line reads as "" */
function timeline(msgs, over){
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": msgs };
  const m = M(over);
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  const h = ctx.shadowHomeHtml();
  /* split rather than match a nested shape: a row with no line has one
     fewer closing div, and a regex that assumed two silently read "" */
  const rows = h.split('<div class="shagent">').slice(1).map(body => ({
    head: (body.match(/shagenthead">([^<]*)</) || [])[1] || "",
    say: (body.match(/class="shagentsay"[^>]*>([^<]*)</) || [])[1] || "",
  }));
  return { h: h, rows: rows, ctx: ctx };
}

let ok = 0;
const pass = (s) => { console.log("ok " + (++ok) + " " + s); };

/* ── 1. AN ACTIVE TURN SHOWS ITS NUMBER AND NOTHING UNDER IT ──────────── */
{
  const t = timeline([
    SH("2026-09-16T10:00:00Z"),
    W("Reading the target directory now. REPORT: partial, still working",
      "2026-09-16T10:00:20Z"),
  ], { turns_used: 0, turn_open: 1 });
  assert.strictEqual(t.rows.length, 1, "the turn in flight still takes a row");
  assert(/Worker agent · turn 1/.test(t.rows[0].head),
    "and the heading names it, got: " + t.rows[0].head);
  assert.strictEqual(t.rows[0].say, "",
    "an active turn must show NO line, got: " + t.rows[0].say);
  assert(!/class="shagentsay"/.test(t.h),
    "and no line element at all is drawn");
  /* not one word of the in-flight turn reached the founder */
  assert(t.h.indexOf("Reading the target directory") === -1,
    "partial worker output leaked onto the timeline");
  assert(t.h.indexOf("partial, still working") === -1,
    "a partial REPORT leaked onto the timeline");
  pass("an active turn draws its number and no summary");
}

/* ── 2. IT STAYS EMPTY AS MORE OF THE TURN ARRIVES ────────────────────── */
{
  const grow = [SH("2026-09-16T10:00:00Z")];
  const steps = [
    "Orienting.",
    "Orienting. Found the directory.",
    "Orienting. Found the directory. REPORT: created the file",
    "Orienting. Found the directory. REPORT: created the file and verified it.",
  ];
  for (const text of steps){
    grow[1] = W(text, "2026-09-16T10:00:20Z");
    const t = timeline(grow.slice(), { turns_used: 0, turn_open: 1 });
    assert.strictEqual(t.rows.length, 1, "still exactly one row");
    assert.strictEqual(t.rows[0].say, "",
      "the line must stay empty while the turn is open, got: " + t.rows[0].say);
    assert(t.h.indexOf("Orienting") === -1 && t.h.indexOf("Found the") === -1,
      "streamed worker text reached the pane: " + text);
  }
  pass("no partial summary ever appears while the turn is streaming");
}

/* ── 3. A COMPLETED TURN SHOWS THE WORKER'S OWN REPORT ────────────────── */
{
  const t = timeline([
    SH("2026-09-16T10:00:00Z"),
    W("## What I did\n\nWrote the file and checked it.\n\n"
      + "REPORT: Created shadow-v4-test.md and verified its three lines.",
      "2026-09-16T10:01:00Z"),
  ], { turns_used: 1, turn_open: null });
  assert.strictEqual(t.rows.length, 1);
  assert.strictEqual(t.rows[0].say,
    "Created shadow-v4-test.md and verified its three lines.",
    "the REPORT is shown verbatim, got: " + t.rows[0].say);
  pass("a completed turn shows the worker-authored REPORT, unedited");
}

/* ── 4. TURN 1 KEEPS ITS REPORT WHILE TURN 2 IS OPEN ──────────────────── */
{
  const t = timeline([
    SH("2026-09-16T10:00:00Z"),
    W("REPORT: Created the file and verified its contents.",
      "2026-09-16T10:01:00Z"),
    SH("2026-09-16T10:02:00Z"),
    W("Starting on the checks. REPORT: not finished yet",
      "2026-09-16T10:02:20Z"),
  ], { turns_used: 1, turn_open: 2 });
  assert.strictEqual(t.rows.length, 2, "both turns take a row");
  assert(/turn 1/.test(t.rows[0].head) && /turn 2/.test(t.rows[1].head),
    "in order: " + t.rows.map(r => r.head).join(" | "));
  assert.strictEqual(t.rows[0].say,
    "Created the file and verified its contents.",
    "the finished turn keeps its report");
  assert.strictEqual(t.rows[1].say, "",
    "the open turn shows nothing, got: " + t.rows[1].say);
  assert(t.h.indexOf("not finished yet") === -1,
    "the open turn's partial REPORT leaked");
  pass("turn 1 keeps its report while turn 2 is open and silent");
}

/* ── 5. TURN 2 REPORTS ONCE IT CLOSES ─────────────────────────────────── */
{
  const msgs = [
    SH("2026-09-16T10:00:00Z"),
    W("REPORT: Created the file and verified its contents.",
      "2026-09-16T10:01:00Z"),
    SH("2026-09-16T10:02:00Z"),
    W("REPORT: Updated the file and ran the requested checks.",
      "2026-09-16T10:03:00Z"),
  ];
  const t = timeline(msgs, { turns_used: 2, turn_open: null });
  assert.deepStrictEqual(t.rows.map(r => r.say),
    ["Created the file and verified its contents.",
     "Updated the file and ran the requested checks."],
    "both reports, in order");
  pass("turn 2's report appears the moment the turn closes");
}

/* ── 6. THE REPORT NEED NOT BE FIRST, OR LAST ─────────────────────────── */
{
  const before = timeline([SH(), W(
    "REPORT: Rewrote the parser.\n\nThen a long tail of tool narration that "
    + "nobody wants on the timeline.", "2026-09-16T10:01:00Z")],
    { turns_used: 1, turn_open: null });
  assert.strictEqual(before.rows[0].say, "Rewrote the parser.",
    "a REPORT above the prose is found");

  const after = timeline([SH(), W(
    "I looked at three files and ran the suite twice before touching "
    + "anything.\n\nREPORT: Rewrote the parser and 12 tests pass.",
    "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(after.rows[0].say,
    "Rewrote the parser and 12 tests pass.",
    "a REPORT below the prose wins over the prose above it, got: "
    + after.rows[0].say);

  /* and across MESSAGES: the report may not be in the turn's last one */
  const split = timeline([SH(),
    W("REPORT: Rewrote the parser and 12 tests pass.", "2026-09-16T10:01:00Z"),
    W("One more thing worth flagging about the flag name.",
      "2026-09-16T10:01:30Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(split.rows[0].say,
    "Rewrote the parser and 12 tests pass.",
    "the report wins over a later message with no report, got: "
    + split.rows[0].say);
  pass("the REPORT is selected wherever in the turn it sits");
}

/* ── 7. NO REPORT -> THE EXACT BEHAVIOUR THAT SHIPPED BEFORE ──────────── */
{
  const t = timeline([SH(), W(
    "## What I did\n\nUpdated README.md with setup instructions.",
    "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(t.rows[0].say,
    "Updated README.md with setup instructions.",
    "the announcement is still skipped and the news still kept");

  const two = timeline([SH(), W(
    "14 tests green, PR #212 open. The push is a floor, so I stopped here.",
    "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(two.rows[0].say, "14 tests green, PR #212 open.",
    "still exactly one sentence, still the first one");
  pass("a completed turn with no REPORT falls back, unchanged");
}

/* ── 8. A HISTORICAL MISSION HAS NO turn_open AND NO REPORT ───────────── */
{
  /* the screenshot mission, m-625e29919430, as its records actually read */
  const t = timeline([
    SH("2026-09-16T09:54:36Z"),
    W('PLACEMENT: D0 Joy Tadanki | "Joy Tadanki Charter"\n\n```\nTYPE: task\n'
      + "```\n\nPlan mode is active, so I have not created the file. Plan "
      + "written to `/Users/x/plan.md`.\n\n**What I checked (read-only):**\n"
      + "\n| Check | Result |\n|---|---|\n| exists | no |",
      "2026-09-16T09:55:00Z"),
    SH("2026-09-16T09:55:47Z"),
    W("**Done.** One file written, three verifications pass.\n\n```\n"
      + "$ wc -c shadow-v4-test.md\n      17\n```\n\nTwo things to flag:",
      "2026-09-16T09:56:03Z"),
  ], { turns_used: 2 });   /* no turn_open field at all -- an old record */
  assert.deepStrictEqual(t.rows.map(r => r.say),
    ["Plan mode is active, so I have not created the file.",
     "One file written, three verifications pass."],
    "a historical timeline must render exactly as it always did");
  assert(!/PLACEMENT|TYPE:|\|/.test(t.h), "and the control plane stays out");
  pass("historical missions render byte-for-byte as before");
}

/* ── 9. A REPORT CANNOT WIDEN WHAT REACHES THE FOUNDER ────────────────── */
{
  const leaks = [
    ['REPORT: PLACEMENT: D0 Joy Tadanki | "Joy Tadanki Charter"', "PLACEMENT"],
    ["REPORT: TRIAGE: depth_selected=2, class=correct", "TRIAGE"],
    ["REPORT: | Field | Value received | Problem |", "Value received"],
    ["REPORT: DEPTH: 4/5", "DEPTH"],
  ];
  for (const [bad, word] of leaks){
    const t = timeline([SH(), W(
      bad + "\n\nThe honest sentence the worker also wrote.",
      "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
    assert(t.h.indexOf(word) === -1,
      "control-plane material reached the founder through a REPORT: " + word);
    assert.strictEqual(t.rows[0].say,
      "The honest sentence the worker also wrote.",
      "a REPORT that cleans to nothing must fall back, got: "
      + t.rows[0].say);
  }
  /* a REPORT quoted inside a fence is the format, not a report */
  const fenced = timeline([SH(), W(
    "```\nREPORT: this is the shape of the line\n```\n\n"
    + "Actually did the work and it passed.", "2026-09-16T10:01:00Z")],
    { turns_used: 1, turn_open: null });
  assert.strictEqual(fenced.rows[0].say, "Actually did the work and it passed.",
    "a fenced REPORT must not be selected, got: " + fenced.rows[0].say);
  pass("a malformed or fenced REPORT leaks nothing and falls back");
}

/* ── 10. DONE-CHECK IS UNTOUCHED ──────────────────────────────────────── */
{
  /* the verifier is server-side and the timeline never parsed DONE-CHECK;
     what this lane pins is that the new selector does not CLAIM one, and
     that the line keeps travelling in the worker's text as it always did */
  const ctx = fresh();
  assert.strictEqual(
    ctx.shadowSayReport("DONE-CHECK: the file exists and contains ALPHA"), "",
    "a DONE-CHECK line is not a REPORT");
  const t = timeline([SH(), W(
    "DONE-CHECK: the file exists and contains ALPHA\n\n"
    + "REPORT: Created the file with the three requested lines.",
    "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(t.rows[0].say,
    "Created the file with the three requested lines.",
    "the REPORT is the line, not the claim above it");
  pass("DONE-CHECK is neither consumed nor altered by the REPORT selector");
}

/* ── 11. SEVERAL REPORTS -> THE FIRST VALID ONE, DETERMINISTICALLY ────── */
{
  const t = timeline([SH(), W(
    "REPORT: Rewrote the parser.\nREPORT: And then rewrote it again.",
    "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(t.rows[0].say, "Rewrote the parser.",
    "the FIRST valid report wins, got: " + t.rows[0].say);

  /* and "first VALID": one that cleans to nothing is skipped, not fatal */
  const skip = timeline([SH(), W(
    "REPORT: | a | b |\nREPORT: Rewrote the parser.",
    "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(skip.rows[0].say, "Rewrote the parser.",
    "an unusable first report is skipped for the next, got: "
    + skip.rows[0].say);

  /* across messages, the earlier message's report wins */
  const across = timeline([SH(),
    W("REPORT: First message's report.", "2026-09-16T10:01:00Z"),
    W("REPORT: Second message's report.", "2026-09-16T10:01:30Z")],
    { turns_used: 1, turn_open: null });
  assert.strictEqual(across.rows[0].say, "First message's report.",
    "forward scan across messages, got: " + across.rows[0].say);
  pass("several REPORT lines resolve to the first valid one");
}

/* ── 12. A LONG REPORT OBEYS THE EXISTING ONE-LINE LIMITS ─────────────── */
{
  const LONG = "Rewired the delegate spawn path so a stalled worker is "
    + "adopted instead of respawned, which is what was doubling the turn "
    + "count on every resume, and then re-ran the whole suite twice over";
  const t = timeline([SH(), W("REPORT: " + LONG + ".", "2026-09-16T10:01:00Z")],
    { turns_used: 1, turn_open: null });
  const say = t.rows[0].say;
  assert(say.length <= 170, "the line must stay short, got " + say.length);
  assert(!/\n/.test(say), "and stay a single line");
  assert(LONG.indexOf(say.replace(/\s…$/, "")) === 0,
    "and remain a PREFIX of the worker's own words, got: " + say);
  /* two sentences in one REPORT still yield one line */
  const two = timeline([SH(), W(
    "REPORT: Wrote the file. Then ran the checks and they passed.",
    "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert.strictEqual(two.rows[0].say, "Wrote the file.",
    "one sentence, the existing cap, got: " + two.rows[0].say);
  pass("a long REPORT obeys the existing one-line display limits");
}

/* ── 13. COMPLETION IS turn_open, NOT A CLOCK ─────────────────────────── */
{
  const msgs = [SH("2026-09-16T10:00:00Z"),
                W("REPORT: Created the file.", "2026-09-16T10:01:00Z")];
  /* the SAME transcript, the SAME stamps -- only turn_open moves */
  const open = timeline(msgs, { turns_used: 0, turn_open: 1 });
  const shut = timeline(msgs, { turns_used: 1, turn_open: null });
  assert.strictEqual(open.rows[0].say, "",
    "turn_open === n -> no summary, got: " + open.rows[0].say);
  assert.strictEqual(shut.rows[0].say, "Created the file.",
    "turn_open cleared -> the summary is eligible");
  assert.strictEqual(open.rows[0].head, shut.rows[0].head,
    "and the heading is identical either way");

  /* turn_open naming ANOTHER turn leaves this one alone */
  const other = timeline([
    SH("2026-09-16T10:00:00Z"), W("REPORT: Turn one did this.", "2026-09-16T10:01:00Z"),
    SH("2026-09-16T10:02:00Z"), W("REPORT: Turn two is mid-flight.", "2026-09-16T10:02:30Z"),
  ], { turns_used: 1, turn_open: 2 });
  assert.deepStrictEqual(other.rows.map(r => r.say),
    ["Turn one did this.", ""], "only the open turn is silenced");

  /* A TERMINAL MISSION IS NEVER IN FLIGHT: the engine can exit INSIDE a turn
     (a stall, a takeover) without reaching the line that clears turn_open,
     so a stale stamp must not silence a finished mission forever. */
  for (const state of ["done", "failed", "stopped"]){
    const t = timeline(msgs, { state: state, turns_used: 1, turn_open: 1 });
    assert.strictEqual(t.rows[0].say, "Created the file.",
      state + ": a stale turn_open must not silence a terminal mission");
  }
  pass("active/completed is decided by turn_open alone, never by elapsed time");
}

/* ══ A REPORT ENDS ON A FULL STOP, OR WHERE IT ALWAYS DID ═══════════════
   (founder, 2026-09-16.) shadowSayGist cuts an over-long FIRST sentence and
   marks the cut. For a REPORT that is the wrong answer when a LATER sentence
   of the same report is a whole thought that fits. shadowReportGist prefers
   that sentence; everything else about the path is unchanged.

   THE CAP IS 160 (SH_SAY_MAX) and these lanes state every boundary in
   characters rather than trusting a hand-counted string. */
const MAX = 160;

/* a sentence of EXACTLY n characters, ending in a full stop, made of words
   so the word-boundary cut in shadowSayGist has something to land on */
function sentenceOf(n, lead){
  let s = String(lead || "Adjusted the parser");
  while (s.length < n - 1) s += (s.length % 6 === 0) ? " " : "x";
  s = s.slice(0, n - 1);
  if (/\s$/.test(s)) s = s.slice(0, -1) + "z";
  return s + ".";
}
assert.strictEqual(sentenceOf(MAX).length, MAX, "the fixture builder is off");
assert.strictEqual(sentenceOf(MAX + 1).length, MAX + 1, "ditto");

const reportSay = (report, over) => timeline(
  [SH("2026-09-16T10:00:00Z"), W("REPORT: " + report, "2026-09-16T10:01:00Z")],
  Object.assign({ turns_used: 1, turn_open: null }, over || {})).rows[0];

/* ── 14. A REPORT THAT FITS IS UNCHANGED ──────────────────────────────── */
{
  const R = "Created shadow-test.txt with the requested content and verified it.";
  assert(R.length <= MAX, "fixture must fit: " + R.length);
  assert.strictEqual(reportSay(R).say, R,
    "a report inside the cap must arrive byte for byte");
  assert(reportSay(R).say.indexOf("…") === -1, "and with no ellipsis");
  console.log("ok " + (++ok) + " a REPORT within the cap is shown unchanged");
}

/* ── 15. THE LIVE CASE: the plan-mode blocker, as the worker wrote it ──
   VERBATIM from mission m-8aa4a0c3, worker session 1c287941: 147 characters,
   ONE sentence, already inside the cap. It must arrive WHOLE -- and this
   lane exists to pin that the new preference cannot shorten it. */
{
  const R = "shadow-test.txt is NOT created — plan mode blocks writes and "
    + "ExitPlanMode is unavailable in this session; approve plan mode off and "
    + "it's one write.";
  assert.strictEqual(R.length, 147, "the live fixture is " + R.length);
  const say = reportSay(R).say;
  assert.strictEqual(say, R, "the live report must arrive whole, got: " + say);
  assert(say.indexOf("…") === -1, "and must not be cut by the JS at all");
  console.log("ok " + (++ok) + " the live plan-mode report arrives whole");
}

/* ── 16. FIRST SENTENCE FITS -> IT STAYS THE LINE ──────────────────────
   THE DETERMINISTIC RULE, stated once: the FIRST sentence that carries news
   wins whenever it fits. "Longest that fits" is the tie-breaker used ONLY
   when the first one overruns -- otherwise a report would end on whichever
   trailing remark happened to be wordiest. */
{
  const a = reportSay("Created the file. Verified its contents. "
                      + "No further changes were needed.").say;
  assert.strictEqual(a, "Created the file.",
    "the first sentence wins when it fits, got: " + a);

  const b = reportSay("shadow-test.txt is NOT created — plan mode blocks "
    + "writes. ExitPlanMode is unavailable in this session.").say;
  assert.strictEqual(b,
    "shadow-test.txt is NOT created — plan mode blocks writes.",
    "the blocker leads and the second sentence is left in the chat, got: " + b);
  console.log("ok " + (++ok) + " with several sentences the first that fits wins");
}

/* ── 17. FIRST SENTENCE OVERRUNS -> THE LONGEST WHOLE ONE THAT FITS ──── */
{
  const long1 = sentenceOf(MAX + 40, "Rewired the delegate spawn path");
  const say = reportSay(long1 + " The suite is green. "
                        + "Nothing else was touched.").say;
  assert.strictEqual(say, "Nothing else was touched.",
    "the longest whole sentence that fits wins, got: " + say);
  assert(say.indexOf("…") === -1, "and it is whole, so no ellipsis");
  console.log("ok " + (++ok) + " an over-long opener yields to a whole sentence");
}

/* ── 18. THE EXACT CHARACTER BOUNDARY ────────────────────────────────── */
{
  const long1 = sentenceOf(MAX + 40, "Rewired the delegate spawn path");
  /* exactly 160 -> it fits, and is chosen whole */
  const at = sentenceOf(MAX, "Folded the verify gate in");
  const hit = reportSay(long1 + " " + at).say;
  assert.strictEqual(hit, at,
    "a sentence of exactly " + MAX + " must be chosen whole");
  assert.strictEqual(hit.length, MAX, "…and arrive at full length");

  /* exactly 161 -> it does NOT fit, so the existing cut stands */
  const over = sentenceOf(MAX + 1, "Folded the verify gate in");
  const miss = reportSay(long1 + " " + over).say;
  assert(/\s…$/.test(miss),
    "a sentence of " + (MAX + 1) + " must not be chosen, got: " + miss);
  assert(long1.indexOf(miss.replace(/\s…$/, "")) === 0,
    "and the fallback is still the cut FIRST sentence");
  console.log("ok " + (++ok) + " the boundary is exactly " + MAX + " characters");
}

/* ── 19. ONE OVER-LONG SENTENCE -> THE EXISTING FALLBACK, UNCHANGED ──── */
{
  const only = sentenceOf(MAX + 60, "Rewired the delegate spawn path");
  const say = reportSay(only).say;
  assert(/\s…$/.test(say), "the existing cut marker is kept, got: " + say);
  assert(say.length <= MAX + 2, "and the existing cap still applies");
  assert(only.indexOf(say.replace(/\s…$/, "")) === 0,
    "and every character is still a PREFIX of the worker's own sentence");
  console.log("ok " + (++ok) + " a single over-long sentence keeps the old cut");
}

/* ── 20. WHAT CANNOT BE CHOSEN, EVEN WHEN IT FITS ─────────────────────── */
{
  const long1 = sentenceOf(MAX + 40, "Rewired the delegate spawn path");

  /* an announcement fits and completes and says nothing */
  const ann = reportSay(long1 + " Done.").say;
  assert(/\s…$/.test(ann),
    '"Done." must not be promoted over a cut sentence, got: ' + ann);

  /* a grid is not a sentence, wherever it reached */
  const grid = reportSay(long1 + " Field | Value | Problem.").say;
  assert(grid.indexOf("|") === -1, "a row reached the founder: " + grid);
  assert(/\s…$/.test(grid), "and the cut stands instead");

  /* an unterminated trailing fragment is not a sentence either */
  const frag = reportSay(long1 + " and then the suite went green").say;
  assert(/\s…$/.test(frag),
    "an unclosed fragment must not be promoted, got: " + frag);
  console.log("ok " + (++ok) + " announcements, grids and fragments cannot win");
}

/* ── 21. TIES GO TO THE EARLIER SENTENCE ──────────────────────────────── */
{
  const long1 = sentenceOf(MAX + 40, "Rewired the delegate spawn path");
  const a = "The backend suite is green.";
  const b = "The frontend lane is green.";
  assert.strictEqual(a.length, b.length, "the fixtures must tie");
  assert.strictEqual(reportSay(long1 + " " + a + " " + b).say, a,
    "equal lengths resolve to the earlier sentence");
  console.log("ok " + (++ok) + " an exact tie resolves to the earlier sentence");
}

/* ── 22. NOTHING IS INVENTED, REWRITTEN OR RE-PUNCTUATED ──────────────── */
{
  const long1 = sentenceOf(MAX + 40, "Rewired the delegate spawn path");
  const R = long1 + " The push is a floor, so I stopped there.";
  const say = reportSay(R).say;
  assert(R.indexOf(say) !== -1,
    "the line must be an exact substring of the worker's report, got: " + say);
  assert.strictEqual(say, "The push is a floor, so I stopped there.",
    "the worker's own words, unedited");
  /* and a worker sentence left unterminated never gains a full stop */
  const open = reportSay(long1 + " the suite went green").say;
  assert(!/green\.$/.test(open), "punctuation must never be added");
  console.log("ok " + (++ok) + " nothing is invented, rewritten or re-punctuated");
}

/* ── 23. THE THREE THINGS THIS MUST NOT HAVE TOUCHED ──────────────────── */
{
  const long1 = sentenceOf(MAX + 40, "Rewired the delegate spawn path");

  /* (a) an ACTIVE turn is still silent, however long its report */
  const act = timeline([SH("2026-09-16T10:00:00Z"),
    W("REPORT: " + long1 + " The suite is green.", "2026-09-16T10:00:20Z")],
    { turns_used: 0, turn_open: 1 });
  assert.strictEqual(act.rows[0].say, "",
    "an active turn must still draw nothing, got: " + act.rows[0].say);
  assert(act.h.indexOf("suite is green") === -1, "and leak nothing");

  /* (b) the NO-REPORT fallback is not routed through the new preference:
     ordinary prose still shows its cut first sentence, as it always did */
  const prose = timeline([SH("2026-09-16T10:00:00Z"),
    W(long1 + " Nothing else was touched.", "2026-09-16T10:01:00Z")],
    { turns_used: 1, turn_open: null });
  assert(/\s…$/.test(prose.rows[0].say),
    "a turn with no REPORT must keep the old cut, got: " + prose.rows[0].say);
  assert(prose.rows[0].say.indexOf("Nothing else") === -1,
    "and must not gain the new sentence preference");

  /* (c) the control-plane filter still refuses a report it cannot clean,
         and the turn drops through to its ordinary prose */
  const ctl = timeline([SH("2026-09-16T10:00:00Z"),
    W("REPORT: PLACEMENT: D0 Joy Tadanki. " + long1
      + "\n\nThe honest sentence the worker also wrote.",
      "2026-09-16T10:01:00Z")], { turns_used: 1, turn_open: null });
  assert(ctl.h.indexOf("PLACEMENT") === -1,
    "control-plane material reached the founder: " + ctl.rows[0].say);
  assert.strictEqual(ctl.rows[0].say,
    "The honest sentence the worker also wrote.",
    "an unusable report still falls back to the turn's prose, got: "
    + ctl.rows[0].say);
  console.log("ok " + (++ok)
    + " active turns, the prose fallback and the control filter are untouched");
}

console.log("\nall shadow worker-REPORT tests passed");
