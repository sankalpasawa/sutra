#!/usr/bin/env node
/* test_shadow_v4_shell.js -- the two-box settings page, and task motion.
 *
 * TWO CHANGES, ONE LANE (founder, 2026-09-17), because they are the same
 * ask: make the surface say what matters and stop asking the founder to
 * configure things whose answer is a default.
 *
 *   1. SETTINGS IS TWO TEXT BOXES. Personality (the founder's words about
 *      how Shadow should behave) and Memory (what Shadow should carry into
 *      every task). Six sections left the page: Autonomy, Tasks, Delegate
 *      offers, Presence, Add a control, Attention. NOTHING LEFT THE ENGINE
 *      -- every route still answers, every stored value still binds, and
 *      autonomy() still defaults to L3.
 *
 *   2. THREE STATES NOW HAVE A FACE. Waiting on Shadow, a turn in flight,
 *      and the instant a task lands. Each is drawn from state the pane
 *      already had; none of them stores anything new.
 *
 * Run: node test_shadow_v4_shell.js
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
const css = fs.readFileSync(
  path.join(__dirname, "static", "panel.css"), "utf8");

function fresh(){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){},
    /* shadowMemorySave/shadowBehavesSave both bail when there is no fetch --
       the guard that lets this module load in a context with no network */
    fetch: async () => ({ ok: false }),
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {},
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  ctx.loadGoalTranscript = () => {};
  ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
  ctx.goalTranscriptHtml = () => "";
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const SETTINGS = {
  behaves: "Check in every 3 turns.",
  behaves_max: 4000,
  memory: "I run Sutra. Ship small.",
  memory_max: 4000,
  global: [{ id: "i-1", text: "everywhere rule" }],
  per_chat: { "sess-a": [{ id: "i-2", text: "scoped rule" }] },
  autonomy: { level: "L3", levels: ["L0","L1","L2","L3"],
              confirm_top_tier: false, worker_may_write: true,
              worker_mode: "plan" },
  tasks: { running_at_once: 2, offers: [] },
  presence: { nudges_per_hour: 3 },
  attention: { watching: [], off: [], alerts: 0 },
  floors: ["destructive git"],
};

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);

/* ══ 1. THE PAGE IS TWO BOXES ═══════════════════════════════════════════ */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SETTINGS));
  const h = ctx.shadowSettingsHtml();
  assert.strictEqual((h.match(/class="ssh"/g) || []).length, 2,
    "exactly two sections");
  assert(h.indexOf(">Personality<") !== -1, "Personality");
  assert(h.indexOf(">Memory<") !== -1, "Memory");
  assert(h.indexOf(">Personality<") < h.indexOf(">Memory<"),
    "Personality leads");
  /* both are TEXT BOXES, same shape, same save-on-change, no Save button */
  assert.strictEqual((h.match(/<textarea/g) || []).length, 2,
    "two textareas and nothing else to fill in");
  assert(/data-shbehaves="1"/.test(h) && /data-shmemory="1"/.test(h));
  assert(!/<button[^>]*>Save</.test(h), "neither has a Save button");
  /* the header is untouched */
  assert(/<h2 class="sstitle">What Shadow knows<\/h2>/.test(h));
  pass("1: settings is two text boxes, Personality then Memory");
}

/* ══ 2. THE SIX ARE OFF THE PAGE — AND STILL IN THE ENGINE ═════════════ */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SETTINGS));
  const h = ctx.shadowSettingsHtml();
  for (const gone of ["Autonomy", "Tasks", "Delegate offers", "Presence",
                      "Add a control", "Attention"]){
    assert(h.indexOf(">" + gone + "<") === -1, gone + " is off the page");
  }
  /* no control from any of them survives */
  for (const hook of ["data-shautonomy", "data-shrunlimit", "data-shnudges",
                      "data-shrevoke", "data-shoffer"]){
    assert(h.indexOf(hook) === -1, hook + " must not be drawn");
  }
  /* THE RENDERERS ARE UNTOUCHED -- this is a page change, not a teardown */
  for (const fn of ["shadowSetAutonomyHtml", "shadowSetTasksHtml",
                    "shadowSetPresenceHtml", "shadowSetAttentionHtml",
                    "shadowSetMemoryHtml", "shadowSetOffersSecHtml"]){
    assert.strictEqual(typeof ctx[fn], "function", fn + " still exists");
  }
  assert(/everywhere rule/.test(ctx.shadowSetMemoryHtml(ctx.S.shadowSettings)),
    "the learned-rule record still renders for its callers");
  pass("2: six sections off the page; every renderer still exists");
}

/* ══ 3. THE MEMORY BOX IS THE TWIN OF PERSONALITY ══════════════════════ */
{
  const ctx = fresh();
  ctx.S.shadowSettings = JSON.parse(JSON.stringify(SETTINGS));
  let h = ctx.shadowSettingsHtml();
  assert(/I run Sutra\. Ship small\./.test(h), "prefilled from the record");
  assert.strictEqual((h.match(/maxlength="4000"/g) || []).length, 2,
    "both ceilings come from the server");
  /* typing keeps a draft and marks it unsaved, exactly as behaves does */
  ctx.listeners.input.forEach(fn => fn({
    target: { dataset: { shmemory: "1" }, value: "new memory" } }));
  assert.strictEqual(ctx.S.shadowMemoryDraft, "new memory");
  assert.strictEqual(ctx.S.shadowMemorySaved, false);
  h = ctx.shadowSettingsHtml();
  assert(/new memory/.test(h), "the draft survives a re-render");
  /* and it posts to its OWN route, never the behaves one */
  const posted = [];
  ctx.shadowPost = async (url, body) => { posted.push({ url, body });
    return { ok: true, json: async () => ({ memory: body.memory }) }; };
  ctx.listeners.change.forEach(fn => fn({
    target: { dataset: { shmemory: "1" }, value: "saved memory" } }));
  assert.strictEqual(posted.length, 1);
  assert.strictEqual(posted[0].url, "/api/shadow/settings/memory");
  assert.strictEqual(posted[0].body.memory, "saved memory");
  pass("3: Memory drafts, re-renders and posts to its own route");
}

/* ══ 4. WAITING ON SHADOW HAS A FACE ═══════════════════════════════════ */
{
  const ctx = fresh();
  const m = { id: "m-1", state: "running", target_session: "sess-1",
              turns_used: 1, max_turns: 12 };
  ctx.S.goalTranscript = { "sess-1": [] };
  /* not waiting -> nothing drawn */
  assert(!/shthinking/.test(ctx.shadowTimelineHtml(m) || ""),
    "no thinking row when nothing is in flight");
  /* waiting -> the row appears, in the stream */
  ctx.shadowTalk().busy = "m-1";
  ctx.shadowTalk().live["m-1"] = [{ who: "founder", text: "status?", ts: 1 }];
  const h = ctx.shadowTimelineHtml(m);
  assert(/class="shsaid shthinking"/.test(h), "the thinking row is drawn");
  assert(/role="status"/.test(h) && /aria-live="polite"/.test(h),
    "and it is announced, not just animated");
  assert(/shthinkword">thinking</.test(h));
  /* it is LAST -- the answer will replace it */
  assert(h.indexOf("status?") < h.indexOf("shthinking"),
    "it sits after the question it is answering");
  /* ONE TASK'S SPINNER IS NOT ANOTHER'S */
  const other = { id: "m-2", state: "running", target_session: "sess-1",
                  turns_used: 1, max_turns: 12 };
  assert(!/shthinking/.test(ctx.shadowTimelineHtml(other) || ""),
    "another task must not show this task's thinking row");
  pass("4: the thinking row is drawn, announced, and per-task");
}

/* ══ 5. A TURN IN FLIGHT CARRIES A CLOCK ═══════════════════════════════ */
{
  const ctx = fresh();
  assert.strictEqual(ctx.shadowTurnElapsed(Date.now() - 84000), "1:24");
  assert.strictEqual(ctx.shadowTurnElapsed(Date.now() - 5000), "0:05");
  /* an unstamped or stale turn claims no elapsed rather than inventing one */
  assert.strictEqual(ctx.shadowTurnElapsed(NaN), "");
  assert.strictEqual(ctx.shadowTurnElapsed(0), "");
  assert.strictEqual(ctx.shadowTurnElapsed(Date.now() - 90000000), "");
  const open = ctx.shadowOpenTurnHtml(2, Date.now() - 84000);
  assert(/shagent shagentopen/.test(open), "it is still an agent row");
  assert(/Worker agent · turn 2/.test(open), "and still names the turn");
  assert(/class="shturntimer"\s*>1:24</.test(open), "the clock is drawn");
  assert(/shturnsweep/.test(open) && /shturnlive/.test(open));
  /* AND STILL NO REPORT -- the rule the open row has always followed */
  assert(!/shagentsay/.test(open),
    "a turn in flight still shows no line under it");
  const bare = ctx.shadowOpenTurnHtml(1, NaN);
  assert(!/shturntimer/.test(bare), "no stamp, no clock, still a row");
  assert(/shagentopen/.test(bare));
  pass("5: an open turn carries a clock, and still reports nothing");
}

/* ══ 6. THE MOMENT IT LANDS ════════════════════════════════════════════ */
{
  const ctx = fresh();
  const m = { id: "m-1", state: "done", turns_used: 2, max_turns: 12,
    completion: { headline: "2 of 2 checks passed", turns_used: 2,
      max_turns: 12, outcome: "The file is written and verified.",
      checks: [{ check: "the file exists", tier: "verify", met: true,
                 how: "Shadow checked this" }] } };
  const h = ctx.shadowCompletionHtml(m);
  assert(/class="shdoneburst"/.test(h), "the flourish is drawn");
  assert(/shdonecheck/.test(h) && /shdonering/.test(h));
  assert(/aria-hidden="true"/.test(h.slice(h.indexOf("shdoneburst") - 60)),
    "it is decoration, and says so");
  /* it LEADS the card, and the content still follows in its own order */
  assert(h.indexOf("shdoneburst") < h.indexOf("shdonehead"));
  assert(h.indexOf("shdonehead") < h.indexOf("shchecks"));
  assert(h.indexOf("shchecks") < h.indexOf("shdonesummary"));
  /* the content is unchanged */
  assert(/Done — 2 of 2 checks passed/.test(h));
  assert(/The file is written and verified\./.test(h));
  pass("6: the done flourish leads, and changes nothing under it");
}

/* ══ 7. MOTION IS NEVER THE MESSAGE ════════════════════════════════════ */
{
  /* every animation is removed wholesale under reduced motion -- not slowed,
     not shortened -- and the finished state is drawn instead. */
  const rm = css.slice(css.indexOf("@media (prefers-reduced-motion:reduce){",
                                   css.indexOf("TASK MOTION")));
  const block = rm.slice(0, rm.indexOf("\n}") + 2);
  for (const cls of ["shthinkdot", "shturnlive", "shturnsweep",
                     "shdonering", "shdonecheck", "shdonesummary"]){
    assert(block.indexOf(cls) !== -1, cls + " must be answered for");
  }
  assert(/\.shdonecheck\{stroke-dashoffset:0;animation:none\}/.test(block),
    "the check is drawn FINISHED, not left invisible");
  assert(/content:"\.\.\."/.test(block),
    "the ellipsis becomes static dots, not nothing");
  /* the clock is a NUMBER, not an animation -- it keeps ticking */
  assert(block.indexOf("shturntimer") === -1,
    "the elapsed clock is not disabled: it is information");
  /* the rules exist at all */
  for (const cls of [".shthinking", ".shturntimer", ".shdoneburst",
                     ".shturnsweep", ".shdonetick"]){
    assert(css.indexOf(cls) !== -1, cls + " has a stylesheet rule");
  }
  pass("7: reduced motion removes the movement and keeps the meaning");
}

console.log("\nall shell + motion tests passed");
