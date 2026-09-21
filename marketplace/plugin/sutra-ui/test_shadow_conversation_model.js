#!/usr/bin/env node
/* test_shadow_conversation_model.js -- USER <-> SHADOW, and the worker is an
 * implementation detail (founder, 2026-09-21, pass 4).
 *
 * THE MODEL THIS PINS. The main content area is a conversation with exactly
 * two visible participants. The founder must feel "I am talking to Shadow,
 * and Shadow is working on my task" -- never "I am watching Shadow operate a
 * worker-agent pipeline". So:
 *
 *   1. no worker vocabulary reaches the surface -- no "WORKER AGENT", no
 *      turn number, no raw worker envelope, no orchestration instructions
 *   2. the founder is right-aligned, Shadow is left-aligned, and both are
 *      real conversational messages rather than dashboard cards
 *   3. Shadow narrates MEANINGFUL transitions, not every worker event --
 *      and narrates only what the record actually says (nothing invented)
 *   4. NEEDS YOU stays fully interactive, and Confirm still works
 *
 * WHAT IT DELIBERATELY DOES NOT CHANGE, asserted here so a later pass cannot
 * quietly regress it: the worker still runs, the REPORT selection machinery
 * is untouched, shadowAgentRowHtml / shadowOpenTurnHtml / shadowHeadTurnHtml
 * are still exported, and every ask still carries its button.
 *
 * Run: node test_shadow_conversation_model.js
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
    setTimeout: () => ({}), clearTimeout(){},
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    fetched: [], posted: [], listeners: {},
    document: {
      addEventListener(t, fn){ (ctx.listeners[t] = ctx.listeners[t] || []).push(fn); },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
  ctx.loadGoalTranscript = (sid) => { ctx.fetched.push(sid); };
  ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
  ctx.goalTranscriptHtml = () => "";
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "Plan a personal trip for me to Europe for 10 days",
  template: "plan", target_mode: "new", target_session: "sess-1",
  task_chat_session: "shadow-1", target_chat: "c-1",
  state: "running", turns_used: 3, max_turns: 25,
  done_when: [{ check: "the itinerary covers 10 days", tier: "auto" }],
}, over);

function pane(ctx, m, extra){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  Object.assign(ctx.S, extra || {});
  return ctx.shadowHomeHtml();
}

/* one narration line per row, in document order */
function said(h){
  const out = [];
  /* the head is optional (a row continuing a run drops it) and the tag may
     carry further attributes after its class (role, data-shdone) */
  const re = /class="shsaid shfrom-(you|shadow)[^"]*"[^>]*>\s*(?:<div class="shsaidhead">[^<]*<\/div>\s*)?<div class="shsaidtext[^"]*"[^>]*>([\s\S]*?)<\/div>/g;
  let x; while ((x = re.exec(h))) out.push(x[1] + ": " + x[2]);
  return out;
}

const SH = (ts) => ({ role: "user", text: "[Shadow · mission m-1] carry on",
                      ts: ts });
const W = (t, ts) => ({ role: "assistant", text: t, ts: ts });
const T = (n) => "2026-09-21T10:" + String(n).padStart(2, "0") + ":00Z";

let n = 0;
const pass = (s) => console.log("ok " + (++n) + " " + s);

/* ══ 1. NO WORKER VOCABULARY ON THE PRIMARY SURFACE ════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("Drafted a Cape Town to Livingstone route.", T(1)),
    SH(T(2)), W("Rebuilt the route around five days in London.", T(3)),
  ] };
  const h = pane(ctx, M({ turns_used: 2 }));
  for (const banned of ["WORKER AGENT", "Worker agent", "worker agent"])
    assert(h.indexOf(banned) === -1, "worker vocabulary leaked: " + banned);
  assert(!/\bturn \d/i.test(h), "a worker turn number reached the founder");
  assert(!/shagenthead|shagentsay|shwturn/.test(h),
    "a worker-turn row or the turn budget is still drawn");
  /* the words themselves survive -- this is attribution, not suppression */
  assert(/The worker drafted a Cape Town to Livingstone route\./.test(h),
    "the worker's own reported sentence was lost");
  assert(/The worker rebuilt the route around five days in London\./.test(h),
    "the second report was lost");
  pass("the worker is internal: its words survive, its machinery does not");
}

/* ══ 2. TWO PARTICIPANTS, TWO SIDES ════════════════════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = {
    /* the turn OPENS at 10:03, after the founder's line -- a turn sorts by
       when it opened, which is what puts Shadow's answer before its work */
    "sess-1": [SH(T(3)), W("Rebuilt the route.", T(4))],
    "shadow-1": [
      { role: "user", text: "I want to spend 5 days in London.", ts: T(1) },
      { role: "assistant", text: "Got it — I’ll reshape the plan around "
        + "five days in London.", ts: T(2) },
    ],
  };
  const h = pane(ctx, M({ turns_used: 1 }));
  assert.deepStrictEqual(said(h), [
    "you: Plan a personal trip for me to Europe for 10 days",
    "shadow: Got it. I\u2019m working through this now.",
    "you: I want to spend 5 days in London.",
    "shadow: Got it — I’ll reshape the plan around five days in London.",
    "shadow: The worker rebuilt the route.",
  ], "the stream must open on the founder, then read you -> shadow");
  assert(/class="shsaidhead">You</.test(h), "the founder is named You");
  assert(/class="shsaidhead">Shadow</.test(h), "and the other side is Shadow");
  /* A SPEAKER IS NAMED ONCE PER RUN (pass 5): three consecutive Shadow
     messages carry one SHADOW label, not three. */
  {
    const run = fresh();
    run.S.goalTranscript = { "sess-1": [
      SH(T(0)), W("Found a workable route.", T(1)),
      SH(T(2)), W("Rebuilt it around London.", T(3)),
      SH(T(4)), W("Checked the travel legs.", T(5)),
    ] };
    const r = pane(run, M({ turns_used: 3 }));
    assert.strictEqual((r.match(/class="shsaidhead">Shadow</g) || []).length, 1,
      "one SHADOW label for the whole run");
    assert.strictEqual((r.match(/shfrom-shadow[^"]*shrun/g) || []).length, 3,
      "and every continuation row is marked as one");
    assert.strictEqual(said(r).length, 5,
      "while every message is still its own row");
  }

  /* the alignment is real, and it lives in the stylesheet */
  assert(/\.shsaid\.shfrom-you\{[^}]*align-self:flex-end/.test(css),
    "the founder's message must be right-aligned");
  assert(/\.shsaid\.shfrom-shadow\{[^}]*align-self:flex-start/.test(css),
    "Shadow's message must be left-aligned");
  /* "Do not make every Shadow message a bordered dashboard card." */
  const shadowRule = (css.match(/\.shsaid\.shfrom-shadow\{([^}]*)\}/) || [])[1] || "";
  assert(/background:transparent/.test(shadowRule)
         && /border-left:0/.test(shadowRule),
    "a plain Shadow message must not be a card, got: " + shadowRule);
  pass("you on the right, Shadow on the left, neither inside a dashboard card");
}

/* ══ 3. SHADOW NARRATES TRANSITIONS, NOT EVERY WORKER EVENT ════════════ */
{
  /* the stream the direction explicitly refuses: "I'm searching... I found
     something... I'm checking... I'm checking again..." */
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("Found a workable route through three cities.", T(1)),
    SH(T(2)), W("Searching for the rail connections.", T(3)),
    SH(T(4)), W("Checking the rail routes.", T(5)),
    SH(T(6)), W("Checking the rail routes.", T(7)),
    SH(T(8)), W("Rebuilt the itinerary around five days in London.", T(9)),
  ] };
  const h = pane(ctx, M({ turns_used: 5 }));
  assert.deepStrictEqual(said(h), [
    "you: Plan a personal trip for me to Europe for 10 days",
    "shadow: Got it. I\u2019m working through this now.",
    "shadow: The worker found a workable route through three cities.",
    "shadow: The worker rebuilt the itinerary around five days in London.",
  ], "only the meaningful transitions may be said");
  assert(h.indexOf("Searching for the rail") === -1, "an in-flight line leaked");
  assert(h.indexOf("Checking the rail") === -1, "an in-flight line leaked");
  pass("the in-progress narration is filtered; the transitions survive");
}

/* 3b. THE LAST WORD IS NEVER DROPPED -- the founder is not left blind about
   where the task actually is, even when the newest report is in-flight
   narration. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("Found a workable route.", T(1)),
    SH(T(2)), W("Checking the budget.", T(3)),
    SH(T(4)), W("Checking the travel legs.", T(5)),
  ] };
  const h = pane(ctx, M({ turns_used: 3 }));
  assert.deepStrictEqual(said(h), [
    "you: Plan a personal trip for me to Europe for 10 days",
    "shadow: Got it. I\u2019m working through this now.",
    /* PASS 5: "Found a workable route." is not the newest, and it is not a
       gerund, so it stays; "Checking the budget." is dropped and "Checking
       the travel legs." survives only because it is the current state. */
    "shadow: The worker found a workable route.",
    "shadow: The worker is checking the travel legs.",
  ], "the newest state must always be said, whatever its aspect");
  pass("the first and the newest report always survive the filter");
}

/* 3c. NOTHING IS INVENTED. A past-tense report is a completed step and is
   kept; two reports are never filtered at all. */
{
  const ctx = fresh();
  assert.strictEqual(ctx.shadowWorkNoise("Checking the rail routes."), true);
  assert.strictEqual(ctx.shadowWorkNoise("Checked the rail routes."), false);
  assert.strictEqual(ctx.shadowWorkNoise("Rebuilt the route."), false);
  assert.strictEqual(ctx.shadowWorkNoise("Still working on it."), true);
  assert.strictEqual(ctx.shadowWorkNoise("I'm checking the legs."), true);
  assert.strictEqual(ctx.shadowWorkNoise("Found an issue with the plan."), false);
  /* PASS 5: the NEWEST report is exempt and nothing else is -- the start
     signal is Shadow's own answer to the opening request, which is
     permanent, so the first report has no exemption to inherit. */
  const two = [{ kind: "worker", say: "Checking one." },
               { kind: "worker", say: "Checking two." }];
  assert.deepStrictEqual(ctx.shadowNarration(two).map(e => e.say),
    ["Checking two."], "only the newest in-flight line survives");
  /* a LONE report is never thinned: it is the newest, so it is exempt */
  assert.deepStrictEqual(
    ctx.shadowNarration([{ kind: "worker", say: "Checking one." }])
      .map(e => e.say),
    ["Checking one."], "a lone report is the current state and must be said");
  /* ...but a lone RECORD is refused whatever its position */
  assert.deepStrictEqual(
    ctx.shadowNarration([{ kind: "worker", say: "10 tool calls \u2014 Web search 6" }]),
    [], "a record is refused even when it is the only thing there is");
  pass("the filter is on aspect, not on content, and never invents a line");
}

/* ══ 4. THE ACTIVITY INDICATOR IS NOT A WORKER LOG ═════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("Rebuilt the route.", T(1)),
    SH(Date.now ? new Date(Date.now() - 84000).toISOString() : T(2)),
    W("Reading the rail timetables now.", new Date(Date.now() - 60000).toISOString()),
  ] };
  const h = pane(ctx, M({ turns_used: 1, turn_open: 2, state: "running" }));
  /* PASS 5: a row continuing a run of messages from the same speaker gains
     " shrun" and drops its label, so the class is matched by prefix. */
  assert(/class="shsaid shfrom-shadow shworking/.test(h),
    "a turn in flight must draw the activity row");
  assert(/shworkword">Working</.test(h), "and it says only that work is on");
  assert(h.indexOf("Reading the rail timetables") === -1,
    "a turn in flight must not preview itself");
  assert(!/Worker agent|\bturn \d/i.test(h), "and it names no turn");
  assert(/role="status"/.test(h) && /aria-live="polite"/.test(h),
    "it is announced, not merely animated");
  pass("the in-flight row says Shadow is working, and nothing else");
}

/* ══ 5. THE ORCHESTRATION ENVELOPE NEVER REACHES THE FOUNDER ═══════════
   api_shadow_task_chat prefixes the founder's line with
   mission_engine.pending_asks_text, so that is what the transcript records.
   The founder wrote one sentence and must read one sentence back. */
{
  const ENVELOPE = [
    "[Pending asks on this task -- the founder may answer any of them in "
      + "this chat; if their line answers one, emit ONE ```answer fence]",
    "- confirm #1: the itinerary covers 10 days",
    "[The founder says:] I want to spend 5 days in London.",
  ].join("\n");
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [], "shadow-1": [
    { role: "user", text: ENVELOPE, ts: T(1) },
    { role: "assistant", text: "Got it — five days in London it is.", ts: T(2) },
  ] };
  const h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm" }));
  for (const leak of ["Pending asks on this task", "answer fence",
                      "The founder says", "confirm #1", "emit ONE"])
    assert(h.indexOf(leak) === -1, "internal orchestration leaked: " + leak);
  assert(/class="shsaid shfrom-you[^"]*">\s*<div class="shsaidhead">You<\/div>\s*<div class="shsaidtext">I want to spend 5 days in London\.<\/div>/
    .test(h), "the founder's own sentence must be the message");
  /* the helper on its own, both shapes */
  assert.strictEqual(ctx.shadowStripEnvelope(ENVELOPE),
    "I want to spend 5 days in London.");
  assert.strictEqual(ctx.shadowStripEnvelope("[The founder says:] keep it relaxed"),
    "keep it relaxed");
  assert.strictEqual(ctx.shadowStripEnvelope("keep it relaxed"), "keep it relaxed",
    "an ordinary line must pass through untouched");
  pass("the pending-ask envelope is stripped; the founder's words are not");
}

/* 5b. the briefing with NO founder line after it is Shadow's, and folds */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [], "shadow-1": [
    { role: "user", text: "[Pending asks on this task -- ...]\n- confirm #1: x",
      ts: T(1) },
    { role: "assistant", text: "Nothing needs you yet.", ts: T(2) },
  ] };
  const h = pane(ctx, M());
  /* PASS 5: it is not folded either -- the app's own prompts are not
     conversation at all. Nothing of it may appear, and it must certainly
     never be attributed to the founder. */
  assert(!/shfold/.test(h), "a bare briefing must not be drawn at all");
  assert(h.indexOf("Pending asks on this task") === -1, "not one byte of it");
  assert(h.indexOf("Nothing needs you yet.") === -1,
    "and neither is the reply it drew");
  /* the founder's side holds exactly one thing: their original request */
  assert.strictEqual((h.match(/class="shsaid shfrom-you/g) || []).length, 1,
    "the briefing must never be attributed to the founder");
  pass("a bare pending-ask briefing is not drawn, folded or attributed");
}

/* ══ 6. NEEDS YOU STAYS FULLY INTERACTIVE, AND CONFIRM STILL WORKS ═════ */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm",
    done_when: [{ check: "the itinerary covers 10 days",
                  tier: "founder_confirm", met: false }] }));
  /* the canonical decision surface, with its one live control */
  assert((h.match(/data-shcheckix=/g) || []).length === 1,
    "NEEDS YOU must carry exactly one Confirm, and it must be live");
  /* and the composer is still there, so a REPLY is possible beside it */
  assert(/data-shhomecompose/.test(h),
    "the founder must still be able to reply, not only confirm");
  /* a held instruction keeps Approve and Withdraw */
  const hold = pane(fresh(), M({ state: "paused",
    approval: { id: "ap-1", used: false },
    pending_say: "Book the Sabi Sand leg." }));
  assert(/data-shact="approve"/.test(hold) && /data-shkind="withdraw"/.test(hold),
    "the hold keeps both of its answers");
  pass("NEEDS YOU is not terminal: Confirm, Approve, Withdraw and Reply all live");
}

/* ══ 7. THE HEADER IS COMPACT, AND CARRIES NO MARK AND NO TURN COUNT ═══ */
{
  const h = pane(fresh(), M());
  assert(!/shwseal/.test(h), "the S seal is still in the header");
  assert(!/class="shwturn"/.test(h), "the turn budget is still in the header");
  assert(!/shwseal/.test(css), "and its rules are still in the stylesheet");
  assert(/class="shwtitle">/.test(h), "the objective still titles the pane");
  assert(/data-shtakeover=/.test(h), "Open the chat is unchanged");
  pass("header: title, status and controls -- no mark, no turn count");
}

/* ══ 8. NOTHING WAS DELETED FROM THE BACKEND-FACING SURFACE ════════════
   Every renderer this pass took OFF the conversation is still exported, so
   a caller that genuinely wants the worker's view still has it. */
{
  const ctx = fresh();
  for (const fn of ["shadowAgentRowHtml", "shadowOpenTurnHtml",
                    "shadowHeadTurnHtml", "shadowAgentTurnHtml",
                    "shadowOpeningHtml", "shadowTaskCardHtml"])
    assert.strictEqual(typeof ctx[fn], "function", fn + " was deleted");
  assert(/Worker agent · turn 4/.test(ctx.shadowAgentRowHtml(4, "did a thing")),
    "the worker-turn renderer itself is unchanged");
  assert(/>10\/25</.test(ctx.shadowHeadTurnHtml({ turns_used: 10, max_turns: 25 })),
    "the turn counter itself is unchanged");
  pass("every worker-facing renderer survives; only the conversation changed");
}

/* ══ 12. TURN #1 IS THE FOUNDER'S (pass 5, contract 1) ═════════════════
   "The first user input itself MUST appear as a normal USER -> SHADOW
   conversation message ... There is no reason for the user to see 'Shadow
   booted with its operating context' before seeing what THEY asked Shadow
   to do." */
{
  const ctx = fresh();
  const ASK = "Pull the latest news from the India cricket team and put it "
            + "in a file.";
  const h = pane(ctx, M({ objective: ASK, state: "running", turns_used: 0 }));
  const rows = said(h);
  assert.strictEqual(rows[0], "you: " + ASK,
    "the conversation must open with the founder's own request, got: " + rows[0]);
  assert(/class="shsaid shfrom-you shopening"/.test(h),
    "and it must be a real USER message, right-aligned");
  /* ...and Shadow answers it, without a word of machinery */
  assert(/shsaid shfrom-shadow shidle/.test(h),
    "Shadow must answer the opening request");
  assert.strictEqual(rows[1], "shadow: Got it. I\u2019m working through this now.",
    "in words, got: " + rows[1]);
  assert.strictEqual(rows.length, 2,
    "a just-started mission is exactly two messages, got: " + rows.join(" | "));
  pass("a just-started mission opens on the founder's request, then Shadow");
}

/* 12b. IT IS THE ORIGINAL ASK, not the revision -- a redirected task still
   opens on the sentence the founder actually opened it with. */
{
  const ctx = fresh();
  const h = pane(ctx, M({ objective: "Plan a trip to India for 10 days",
    revisions: [{ objective: "Plan a trip to Africa for 10 days" }] }));
  assert.strictEqual(said(h)[0], "you: Plan a trip to Africa for 10 days",
    "the thread opens on what was asked, not on what the task became");
  pass("the opening message is the original ask, not the current revision");
}

/* ══ 13. NO LIFECYCLE EVENT IS A CHAT MESSAGE (contracts 5, 11, 12) ════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = {
    "sess-1": [
      SH(T(0)),
      W("REPORT: 10 tool calls — Web search 6, fetched 3, wrote 1.", T(1)),
      SH(T(2)),
      W("REPORT: DONE-CHECK: india-cricket-news.txt exists and has 10 items.", T(3)),
      SH(T(4)),
      W("REPORT: Created india-cricket-news.txt with 10 current items.", T(5)),
    ],
    "shadow-1": [
      { role: "user", text: "[Shadow boot] Read your operating context, then "
        + "answer READY.", ts: T(0) },
      { role: "assistant", text: "READY", ts: T(0) },
      { role: "user", text: "You are Shadow, driving one target chat toward "
        + "an outcome.\nOUTCOME\nthe file", ts: T(2) },
      { role: "assistant", text: '```json\n{"action":"continue"}\n```', ts: T(2) },
      { role: "user", text: "Write the opening brief for this task's worker "
        + "chat.", ts: T(1) },
      { role: "assistant", text: "Sent worker first instruction: You are a "
        + "delegate session working for the founder via Shadow.", ts: T(1) },
    ],
  };
  const h = pane(ctx, M({ turns_used: 3, objective: "Put the news in a file" }));
  for (const record of [
      "Shadow boot", "READY", "operating context", "driving one target chat",
      "booted", "chose the next instruction", "Write the opening brief",
      "Sent worker first instruction", "delegate session",
      "tool calls", "Web search 6", "DONE-CHECK", "REPORT:",
      '{"action"', "```json"])
    assert(h.indexOf(record) === -1,
      "an internal record reached the conversation: " + record);
  /* what DID survive is the one thing a founder would want said */
  assert.deepStrictEqual(said(h), [
    "you: Put the news in a file",
    "shadow: Got it. I\u2019m working through this now.",
    "shadow: The worker created india-cricket-news.txt with 10 current items.",
  ], "only the real update survives, got: " + said(h).join(" | "));
  pass("lifecycle events, tool-call counts and DONE-CHECK are not chat");
}

/* 13b. the rejection list on its own -- a record is refused wherever it
   sits, and prose that merely mentions a tool or a file is untouched */
{
  const ctx = fresh();
  for (const record of [
      "10 tool calls — Web search 6, fetched 3",
      "3 tool-calls: web_search, read_file",
      "DONE-CHECK: the file exists",
      "REPORT: something",
      "Sent worker first instruction: go",
      "Worker instruction: keep going",
      "You are a delegate session working for the founder.",
      "m-194c266205d3 is blocked",
      '{"worker": false}',
      "```answer"])
    assert.strictEqual(ctx.shadowNotSpeech(record), true,
      "must be refused: " + record);
  for (const speech of [
      "I searched the cricket boards and found ten current items.",
      "The first search gave conflicting results, so I'm checking the "
        + "original sources before I use them.",
      "Done — I created india-cricket-news.txt with 10 current items.",
      "I've found a workable route. I'm checking the remaining connections."])
    assert.strictEqual(ctx.shadowNotSpeech(speech), false,
      "must be kept: " + speech);
  pass("the rejection list is keyed on shape, and keeps ordinary prose");
}

/* ══ 14. WORKER TURNS ARE NOT CONVERSATIONAL TURNS (contract 7) ════════
   "A mission may have 1 user message, 5 Shadow messages, 3 worker turns,
   20 tool calls -- and the conversation must still visually contain only
   the relevant USER and SHADOW messages." */
{
  const ctx = fresh();
  const msgs = [];
  for (let k = 1; k <= 9; k++){ msgs.push(SH(T(k * 2))); msgs.push(
    W("REPORT: " + (k % 2 ? "Checking source " + k + "." : "Collected batch "
      + k + "."), T(k * 2 + 1))); }
  const h = pane(ctx, M({ turns_used: 9, max_turns: 25,
                          objective: "Put the news in a file" }));
  const rows = said(h);
  assert.strictEqual(rows[0], "you: Put the news in a file",
    "one user message");
  assert(rows.length < 9,
    "nine worker turns must not become nine messages, got " + rows.length);
  assert(!/\bturn \d|Worker agent|9\/25|shwturn/i.test(h),
    "no worker turn count may reach the conversation");
  pass("nine worker turns, one user message, a handful of Shadow messages");
}

/* ══ 15. NEEDS YOU: the reply is a USER message (contracts 8, 9, 14) ═══ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [], "shadow-1": [
    { role: "user", text: "[Pending asks on this task -- emit ONE ```answer "
      + "fence]\n- confirm #1: the budget is right\n[The founder says:] "
      + "Increase it to $7,000.", ts: T(4) },
    { role: "assistant", text: "Got it — I’ll raise the budget to $7,000 "
      + "and rework the plan around it.", ts: T(5) },
  ] };
  const h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm",
    objective: "Plan a trip",
    done_when: [{ check: "the budget is right", tier: "founder_confirm",
                  met: false }] }));
  assert.deepStrictEqual(said(h), [
    "you: Plan a trip",
    "shadow: Got it. I\u2019m working through this now.",
    "you: Increase it to $7,000.",
    "shadow: Got it — I’ll raise the budget to $7,000 and rework the plan "
      + "around it.",
  ], "the reply must be a USER message, answered by Shadow");
  /* CONTRACT 14: Confirm is untouched, and is still the one live control */
  assert.strictEqual((h.match(/data-shcheckix=/g) || []).length, 1,
    "Confirm must still be there, exactly once");
  /* CONTRACT 9: the resume path is the backend's, and it is not this file's
     to re-implement -- test_shadow_reply_resumes.py (20 cases) pins
     app.resume_after_revision on the existing mission-action door. */
  pass("a NEEDS YOU reply is a USER message; Confirm and the resume path stand");
}

/* ══ 16. COMPLETION STILL REACHES THE FINAL-STATE SUMMARY (contract 13) ═ */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "done", objective: "Put the news in a file",
    completion: { headline: "3 of 3 checks passed", turns_used: 3,
      max_turns: 25,
      outcome: "Created india-cricket-news.txt with 10 current items.",
      checks: [{ check: "the file exists", met: true, how: "Shadow verified" },
               { check: "it has 10 items", met: true, how: "Shadow verified" },
               { check: "no duplicates", met: true, how: "Shadow verified" }],
      artifacts: [{ path: "india-cricket-news.txt" }] } }));
  assert(/shdonesum/.test(h), "the completion summary must still render");
  assert(/india-cricket-news\.txt/.test(h), "naming what was produced");
  /* and the machinery stays behind the disclosure, as pass 4 left it */
  assert(/<details/.test(h), "verification must stay behind a disclosure");
  assert(said(h)[0] === "you: Put the news in a file",
    "and the thread still opens on the founder's request");
  pass("completion is unchanged: summary outside, verification folded in");
}

/* ══ 17. NOTHING BACKEND-FACING WAS TOUCHED (contract 15) ══════════════
   Asserted the only way a UI lane honestly can: every function the
   orchestration reads or writes through is still exported and still
   behaves as it did. The route/engine lanes (test_shadow_reply_resumes.py,
   test_shadow_v42_routes.py) are unchanged and still pass. */
{
  const ctx = fresh();
  for (const fn of ["shadowTalkSend", "shadowSendIntervention",
                    "shadowTimelineEvents", "shadowCheckRowsHtml",
                    "shadowCompletionHtml", "shadowAskRowsHtml",
                    "shadowRevisionsHtml", "shadowStoryHtml",
                    "shTalkFold", "shadowTaskTranscript"])
    assert.strictEqual(typeof ctx[fn], "function", fn + " was removed");
  /* shadowTimelineEvents is still the COMPLETE record -- the filtering is a
     render-time decision, so nothing downstream of it lost anything */
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: 10 tool calls — Web search 6.", T(1)),
    SH(T(2)), W("REPORT: Collected the items.", T(3)),
  ] };
  ctx.S.shadowMissions = [M({ turns_used: 2 })];
  ctx.S.shadowTaskSel = "m-1";
  const events = ctx.shadowTimelineEvents(M({ turns_used: 2 }));
  assert.strictEqual(events.filter(e => e.kind === "worker").length, 2,
    "the event list must still carry every worker turn");
  assert(events.some(e => /tool calls/.test(e.say || "")),
    "including the one the renderer refuses to say");
  pass("the record is complete; only the presentation boundary decides");
}

/* ══ 20. SHADOW NARRATES; IT DOES NOT SPEAK AS THE WORKER ══════════════
   (founder, 2026-09-21, pass 6: "Do not expose worker-facing narration as
   if they are Shadow speaking to the user ... avoid ambiguous first-person
   worker language such as 'I'll pull...', 'I'll write...', 'I'm going to
   search...', 'I found...' when that statement is derived from the
   worker's internal turn.") */
{
  const ctx = fresh();
  const shift = ctx.shadowThirdPerson;
  /* every shape the founder named, and what Shadow says instead */
  const CASES = [
    ["I’ll pull current India cricket news and write it to a file.",
     "The worker will pull current India cricket news and write it to a file."],
    ["I’ll write the findings to india-cricket-news.md.",
     "The worker will write the findings to india-cricket-news.md."],
    ["I’m going to search the boards.",
     "The worker is going to search the boards."],
    ["I found 10 current items.", "The worker found 10 current items."],
    ["I have checked every source.", "The worker has checked every source."],
    ["I am writing the file now.", "The worker is writing the file now."],
    ["Let me check the last two sources.",
     "The worker will check the last two sources."],
    ["We’ve gathered the updates.", "The worker has gathered the updates."],
    /* a pronoun after the head goes with it */
    ["The first search gave conflicting results, so I went back to the sources.",
     "The first search gave conflicting results, so it went back to the sources."],
    /* subject-less shapes that still read as Shadow doing the work */
    ["Checking the sources for duplicates.",
     "The worker is checking the sources for duplicates."],
    ["Created india-cricket-news.txt with 10 items.",
     "The worker created india-cricket-news.txt with 10 items."],
    ["Cut the list to the last 7 days.",
     "The worker cut the list to the last 7 days."],
  ];
  for (const [raw, want] of CASES)
    assert.strictEqual(shift(raw), want, "shift of: " + raw);

  /* NOTHING IS ADDED AND NOTHING IS GUESSED. A sentence with no first
     person and no recognisable subject-less verb is returned byte-identical
     -- rewriting it would be the invention this deliberately refuses. */
  for (const same of [
      "The file now lists 10 items.",
      "Ten items were written to the file.",
      "Indeed the two boards disagree.",
      "Speed was the limiting factor.",
      "Three sources could not be reached."])
    assert.strictEqual(shift(same), same, "must be left alone: " + same);

  /* and every content word survives the shift */
  const raw = "I found 10 current items and I’m checking the sources.";
  for (const word of ["found", "10", "current", "items", "checking", "sources"])
    assert(shift(raw).indexOf(word) !== -1, "a content word was lost: " + word);
  pass("first-person worker language is narrated, never ventriloquised");
}

/* 20b. ...and it reaches the rendered surface */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: I’ll pull current India cricket news and write it "
                + "to a file.", T(1)),
    SH(T(2)), W("REPORT: I found 10 current items and I’m checking the "
                + "sources for duplicates.", T(3)),
  ] };
  const h = pane(ctx, M({ turns_used: 2, objective: "Put the news in a file" }));
  /* scoped to the NARRATION rows: Shadow's own "Got it. I’m working through
     this now." is Shadow speaking and keeps its first person (below). */
  const narrated = (h.match(/shsay[^"]*"[^>]*>[\s\S]*?<div class="shsaidtext">([^<]*)</g) || [])
    .map(x => (x.match(/<div class="shsaidtext">([^<]*)</) || [])[1] || "");
  assert(narrated.length, "there must be narration rows to check");
  for (const line of narrated)
    assert(!/\bI\b|\bI’(?:ll|m|ve|d)\b|\bmy\b|\bwe\b/i.test(line),
      "worker first person reached the conversation: " + line);
  assert(/The worker found 10 current items and it is checking the sources/
    .test(h), "and the narrated form is what is drawn");
  /* SHADOW'S OWN REPLIES KEEP THEIR "I" -- Shadow owns the mission, and
     what it says to the founder in the task chat is its own speech. */
  const own = fresh();
  own.S.goalTranscript = { "sess-1": [], "shadow-1": [
    { role: "user", text: "how is it going?", ts: T(1) },
    { role: "assistant", text: "I’m reworking the list around that now.",
      ts: T(2) },
  ] };
  assert(/I’m reworking the list around that now\./
    .test(pane(own, M({ objective: "Put the news in a file" }))),
    "Shadow's own reply must keep its own first person");
  pass("the surface narrates the worker and leaves Shadow's own voice alone");
}

/* ══ 21. A SERIALIZED WORKER PAYLOAD NEVER REACHES THE CONVERSATION ════
   (founder, 2026-09-21, pass 6, from the rendered screenshot:
    "T20I series against Bangladesh announced"... "url"... {...}) */
{
  const ctx = fresh();
  const PAYLOAD = '{"results": [{"title": "T20I series against Bangladesh '
    + 'announced", "url": "https://bcci.tv/news/1", "published_at": '
    + '"2026-09-20"}, {"title": "Bumrah cleared to return", "url": '
    + '"https://espncricinfo.com/x"}]}';
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: " + PAYLOAD, T(1)),
    SH(T(2)), W("REPORT: Gathered the current updates and checked the "
                + "sources for duplicates.", T(3)),
  ] };
  const h = pane(ctx, M({ turns_used: 2, objective: "Put the news in a file" }));
  for (const leak of ['"url"', '"title"', "https://", "bcci.tv",
                      "espncricinfo", "published_at", "{", "}", "[{",
                      "T20I series against Bangladesh"])
    assert(h.indexOf(leak) === -1, "a serialized payload leaked: " + leak);
  assert.deepStrictEqual(said(h), [
    "you: Put the news in a file",
    "shadow: Got it. I’m working through this now.",
    "shadow: The worker gathered the current updates and checked the sources "
      + "for duplicates.",
  ], "only the sentence survives, got: " + said(h).join(" | "));
  pass("a flattened search payload is refused; the readable report is not");
}

/* 21b. the rejection list on its own -- shape, never topic */
{
  const ctx = fresh();
  for (const payload of [
      '{"title": "x"}',
      '[{"url": "https://a.b"}]',
      'Found: "a"... "url"... {...}',
      "See https://espncricinfo.com/story/123 for the report",
      'url: "https://a.b"',
      'published_at: 2026-09-20',
      '"one" and "two" and "three" and "four"'])
    assert.strictEqual(ctx.shadowNotSpeech(payload), true,
      "must be refused: " + payload);
  for (const speech of [
      "The worker gathered 10 items and checked each against its board report.",
      "I found a workable route through three cities.",
      "Created india-cricket-news.txt with 10 items, one per line.",
      "The board's own report disagrees with the wire copy."])
    assert.strictEqual(ctx.shadowNotSpeech(speech), false,
      "must be kept: " + speech);
  pass("braces, JSON keys, URLs and quote runs are refused; prose is not");
}

/* ══ 22. THE ALIGNMENT CONTRACT, ASSERTED ON THE STYLESHEET ════════════
   (founder, 2026-09-21, pass 6: "Shadow messages have a consistent left
   edge close to the conversation content boundary ... do NOT have a large
   arbitrary left margin / centered-column offset ... anchor that max-width
   from the left.")

   MEASURED IN CHROME BEFORE THE FIX, at a 1160px window:
       .shwscroll   L=323  W=831
       .shtimeline  L=396  W=676      <- 73px of centring inset
   and after:
       .shtimeline  L=323  W=780      <- flush with the content edge */
{
  const rule = (sel) => {
    const i = css.indexOf(sel + "{");
    assert(i !== -1, "missing rule: " + sel);
    return css.slice(i + sel.length + 1, css.indexOf("}", i));
  };
  const scroll = rule(".shwscroll>*");
  assert(/margin-left:0\b/.test(scroll),
    "the stream must be anchored from the LEFT, got: " + scroll);
  assert(!/margin-left:auto/.test(scroll),
    "a centred stream indents Shadow away from the content edge");
  assert(/align-self:stretch/.test(scroll),
    "an auto cross-margin cancels stretch -- it must be explicit");
  assert(/max-width:\d+rem/.test(scroll),
    "the reading measure is kept, only its anchor moved");

  const shadow = rule(".shsaid.shfrom-shadow");
  assert(/align-self:flex-start/.test(shadow), "Shadow sits on the left");
  assert(!/margin-left/.test(shadow), "and takes no left margin of its own");
  const you = rule(".shsaid.shfrom-you");
  assert(/align-self:flex-end/.test(you), "the founder sits on the right");
  assert(/max-width:/.test(you), "with a measure of its own");
  pass("Shadow is left-anchored at the content edge; the founder is right");
}

/* ══ 25. CASE A: A CLEAN FINISH HIDES THE MACHINERY ════════════════════
   (founder, 2026-09-21, pass 7: "When Shadow/worker completes a task
   successfully and the user does NOT need to do anything manually, do NOT
   expose internal verification machinery in the main Shadow conversation
   ... make the completion appear as a natural Shadow response.") */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "done",
    objective: "Make a file of 10 lines about spaceships.",
    done_when: [{ check: "the file has 10 lines", tier: "verify", met: true }],
    completion: {
      headline: "3 of 3 checks passed", turns_used: 4, max_turns: 25,
      outcome: "Created spaceships.txt with 10 lines about spaceships.\n\n"
        + "DONE-CHECK: spaceships.txt exists\n"
        + "DONE-CHECK: it has exactly 10 lines\n"
        + "| line | text |\n|---|---|\n| 1 | ... |",
      artifacts: ["spaceships.txt"],
      checks: [
        { check: "spaceships.txt exists", met: true, how: "Shadow checked this" },
        { check: "it has exactly 10 lines", met: true, how: "Shadow checked this" },
        { check: "every line is about spaceships", met: true,
          how: "Shadow checked this" },
      ],
    } }));

  /* what the founder reads: their request, Shadow's answer, Shadow's close */
  assert.deepStrictEqual(said(h), [
    "you: Make a file of 10 lines about spaceships.",
    "shadow: Got it. I’m working through this now.",
    "shadow: Done — created spaceships.txt with 10 lines about spaceships.",
  ], "the finish must read as one Shadow message, got: " + said(h).join(" | "));
  /* ...and the file itself */
  assert(/class="shdonefile">spaceships\.txt</.test(h),
    "the artifact affordance must be there");

  /* NONE of the machinery, on the surface */
  for (const gone of ["DONE-CHECK", "3 of 3 checks passed", "shdonesummary",
                      ">Summary<", "What you can open", "shconfirmq",
                      "shdonework", "shdoneburst", "| line |"])
    assert(h.indexOf(gone) === -1,
      "internal verification machinery on a clean finish: " + gone);
  /* the check names appear ONLY inside the closed fold */
  const fold = h.slice(h.indexOf("shdoneverif"));
  assert(/spaceships\.txt exists/.test(fold),
    "every criterion must still be rendered, inside the fold");
  assert(h.indexOf("spaceships.txt exists") > h.indexOf("shdoneverif"),
    "and nowhere above it");
  assert(!/<details class="shcheckfold shdoneverif"[^>]* open/.test(h),
    "the fold must be closed");
  /* nothing was deleted from the record */
  assert(/data-shcopydone/.test(h), "the full record is still copyable");
  pass("A: a clean finish is one Shadow message, the file, and a closed fold");
}

/* ══ 26. CASE B: NEEDS YOU STILL SHOWS THE CHECKS AND THE CONTROLS ═════
   "DO NOT hide the checks when the user actually needs to inspect
   something, confirm something, approve something, or make a decision." */
{
  /* B1: a decision is open -- the criterion, its evidence and Confirm are
     all on the surface, exactly as before */
  const ctx = fresh();
  const h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm",
    objective: "Plan the route",
    done_when: [{ check: "the route avoids the toll road",
                  tier: "founder_confirm", met: false,
                  evidence: "two viable routes found" }] }));
  assert(/the route avoids the toll road/.test(h),
    "the criterion the founder must judge must be visible");
  assert((h.match(/data-shcheckix=/g) || []).length === 1,
    "and Confirm must be live, exactly once");
  assert(!/shdonesay/.test(h), "a clean-finish message must not appear");

  /* B2: a held instruction keeps Approve and Withdraw */
  const hold = pane(fresh(), M({ state: "paused",
    approval: { id: "ap-1", used: false },
    pending_say: "Book the non-refundable leg." }));
  assert(/Book the non-refundable leg\./.test(hold),
    "what is being approved must be visible");
  assert(/data-shact="approve"/.test(hold) && /data-shkind="withdraw"/.test(hold),
    "Approve and Withdraw must both be live");

  /* B3: a finish with a check that did NOT pass keeps the card, the caveat
     and the criteria -- the verification qualifies the result, so it is the
     actionable part */
  const flagged = pane(fresh(), M({ state: "done", objective: "Plan the route",
    completion: {
      headline: "1 of 2 checks passed", turns_used: 4, max_turns: 25,
      outcome: "Built the route.",
      checks: [{ check: "the route avoids the toll road", met: false,
                 how: "Shadow checked this" },
               { check: "it fits in one day", met: true,
                 how: "Shadow checked this" }],
    } }));
  assert(/class="shconfirmq">Done</.test(flagged),
    "a flagged finish must render the card, not the message");
  assert(!/shdonesay/.test(flagged), "and not the clean message");
  assert(/check did not pass/.test(flagged),
    "the caveat must name that something is outstanding");
  assert(flagged.indexOf("the route avoids the toll road") !== -1,
    "and the criterion must be reachable");
  pass("B: a decision, a hold and a failed check all keep their evidence");
}

/* ══ 27. THE DECISION SURFACE IS CONTEXT, NOT A DEBUGGER ═══════════════
   (founder, 2026-09-21, pass 8: "Do not put internal evidence above the
   user's current conversation ... file line counts, 'Shadow established',
   proof snippets, 'shown in part', internal verification text.") */
{
  const ctx = fresh();
  const m = M({ state: "paused", pause_reason: "founder_confirm",
    objective: "Plan a 10-day India ride",
    done_when: [{ check: "the itinerary matches the trip you want",
                  tier: "founder_confirm", met: false }],
    decision: {
      question: "Does this itinerary match the trip you want?",
      artifacts: [{ path: "india-10-day-plan.md", truncated: true,
        text: "Day 1 Bengaluru\nDay 2 Western Ghats\nDay 3 Konkan",
        facts: { lines: 233, distinct_non_empty_lines: 181 } }],
      established: [{ check: "the file exists", met: true,
                      how: "exists, found Day 10" }],
    } });
  const h = pane(ctx, m);

  /* the internal evidence the founder named, gone */
  for (const noise of ["233 lines", "181 distinct", "Shadow established",
                       "exists, found Day 10", "shown in part",
                       "open the task's chat for the whole", "shdecmeta",
                       "shdecest"])
    assert(h.indexOf(noise) === -1,
      "internal evidence on the decision surface: " + noise);

  /* what a person deciding actually needs, kept */
  assert(/india-10-day-plan\.md/.test(h), "the file must be named");
  assert(/Day 2 Western Ghats/.test(h), "and its preview shown");
  assert(/class="shdeccut"/.test(h),
    "a cut preview must still say it is cut, without the renderer's words");
  assert((h.match(/data-shcheckix=/g) || []).length === 1,
    "and the decision control must be live");

  /* the record is untouched -- the facts are still on the mission */
  assert.strictEqual(m.decision.artifacts[0].facts.lines, 233,
    "the measured facts must still be on the record");
  assert.strictEqual(m.decision.established.length, 1,
    "and so must what Shadow established");
  pass("the decision shows the file and the preview, not the measurements");
}

/* 27b. `missing` STAYS: it is the one note that explains an absent preview */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm",
    done_when: [{ check: "it matches", tier: "founder_confirm", met: false }],
    decision: { question: "Does it match?", artifacts: [], established: [],
      missing: "Shadow could not gather the artifact this question is about "
             + "— no file it checked is readable." } }));
  assert(/could not gather the artifact/.test(h),
    "an impossible question must still state its own gap");
  pass("a decision with nothing to show says why, in words");
}

/* ══ 28. THE DEBUGGER'S VOCABULARY IS NOT CONVERSATION ═════════════════ */
{
  const ctx = fresh();
  for (const noise of [
      "Shadow established: exists, found Day 10",
      "§3 gives all ten days, shown in part",
      "record: m-194c266205d3",
      "payload: 14 results",
      "evidence: the file exists",
      "10 tool calls — Web search 6",
      "The file has 181 distinct lines"])
    assert.strictEqual(ctx.shadowNotSpeech(noise), true,
      "must be refused: " + noise);
  /* ...and ordinary prose that merely uses those words is untouched */
  for (const speech of [
      "The record was set in 2019 and still stands.",
      "I checked the evidence the board published and it holds up.",
      "Every stage is distinct, so the loop never doubles back."])
    assert.strictEqual(ctx.shadowNotSpeech(speech), false,
      "must be kept: " + speech);
  pass("debug vocabulary is refused by shape; prose that uses it is not");
}

/* ══ 29. THE DECISION CLOSES WHEN THE FOUNDER ANSWERS IT ═══════════════
   (founder, 2026-09-21, pass 8, item 5: "The old decision request should be
   resolved/closed once the user has answered it.")

   THE RENDER SIDE OF THE BACKEND CHANGE. app.resume_after_reply moves a
   task off `paused` when the founder's reply is new direction, and every
   NEEDS YOU surface in this pane is keyed on `state === "paused"` -- so the
   old decision block leaves the conversation by construction rather than by
   a second rule that could drift from it. The backend half is pinned in
   test_shadow_reply_resumes.py. */
{
  const decision = { question: "Does this itinerary match?", artifacts: [],
    established: [], missing: "" };
  const checks = [{ check: "the itinerary matches the trip you want",
                    tier: "founder_confirm", met: false }];
  const waiting = pane(fresh(), M({ state: "paused",
    pause_reason: "founder_confirm", done_when: checks, decision: decision }));
  assert((waiting.match(/data-shcheckix=/g) || []).length === 1,
    "while it is waiting, the decision is live");

  /* ...and once the reply put the task back to work */
  const resumed = pane(fresh(), M({ state: "running", pause_reason: null,
    done_when: checks, decision: decision }));
  assert(!/data-shcheckix=/.test(resumed),
    "the answered decision must not stay live above the reply");
  assert(!/Shadow needs your decision/.test(resumed),
    "nor its heading");
  assert(!/shask-hold|shask-question|shask-parked/.test(resumed),
    "and no ask row may survive the resume");
  pass("the decision block closes when the reply puts the task back to work");
}

/* ══ 30. CONFIRM IS STILL THE OTHER ENDING ═════════════════════════════
   "We are removing INTERNAL verification noise, NOT removing USER
   DECISIONS." */
{
  const confirmed = pane(fresh(), M({ state: "done",
    done_when: [{ check: "the itinerary matches the trip you want",
                  tier: "founder_confirm", met: true,
                  confirmed_at: "2026-09-21T10:00:00Z" }],
    completion: { headline: "1 of 1 checks passed", turns_used: 4,
      max_turns: 25, outcome: "Built the 10-day India plan.",
      artifacts: ["india-10-day-plan.md"],
      checks: [{ check: "the itinerary matches the trip you want", met: true,
                 how: "you confirmed it", by: "founder" }] } }));
  assert(/You confirmed: the itinerary matches the trip you want/
    .test(confirmed), "the confirmation stays in the scrollback");
  assert(/shdonesay/.test(confirmed), "and the task reaches its clean finish");
  assert(!/data-shcheckix=/.test(confirmed),
    "with nothing left to decide");
  pass("confirming a plan completes the task and keeps the record of it");
}

/* ══ 31. WORKER → SHADOW → FOUNDER (founder, 2026-09-21, pass 9) ═══════
   "Worker output should always come back through Shadow's existing
   task-chat/conversation layer before it is shown to the founder."

   `shadow_updates` is what Shadow wrote on the decide turn it already takes
   (mission_engine.validate_update). Where it exists it IS the message --
   Shadow's own voice, first person, its own reading of the worker's result. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: I’ll pull current India cricket news and write it "
                + "to a file.", T(1)),
    SH(T(2)), W("REPORT: The worker wrote india-10-day-plan.md — 10-day "
                + "Bengaluru ride loop.", T(3)),
  ] };
  const h = pane(ctx, M({ turns_used: 2, objective: "Plan a 10-day ride",
    shadow_updates: [
      { text: "I’m pulling the current reports together now.", at_turn: 1 },
      { text: "I’ve got the 10-day plan in india-10-day-plan.md. It "
            + "follows a Bengaluru → Western Ghats → Konkan → Hampi loop.",
        at_turn: 2 },
    ] }));
  assert.deepStrictEqual(said(h), [
    "you: Plan a 10-day ride",
    "shadow: Got it. I’m working through this now.",
    "shadow: I’m pulling the current reports together now.",
    "shadow: I’ve got the 10-day plan in india-10-day-plan.md. It follows a "
      + "Bengaluru → Western Ghats → Konkan → Hampi loop.",
  ], "Shadow's own line must be the message, got: " + said(h).join(" | "));
  /* the worker's own sentence, and the shift of it, are both gone */
  assert(h.indexOf("I’ll pull current India cricket news") === -1,
    "the worker's first person reached the founder");
  assert(h.indexOf("The worker will pull") === -1
      && h.indexOf("The worker wrote india-10-day-plan") === -1,
    "the deterministic shift is still being drawn over Shadow's own line");
  /* and the row says which it is, so a regression is visible */
  assert.strictEqual((h.match(/shsay shsayown/g) || []).length, 2,
    "both narration rows must be Shadow's own");
  pass("worker output is summarised by Shadow before the founder reads it");
}

/* 31b. SHADOW'S FIRST PERSON IS ITS OWN and is never shifted */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: I found 10 items.", T(1)),
  ] };
  const h = pane(ctx, M({ turns_used: 1, shadow_updates: [
    { text: "I’ve got the ten items and I’m checking the sources.",
      at_turn: 1 }] }));
  assert(/I’ve got the ten items and I’m checking the sources\./.test(h),
    "Shadow's own first person must survive untouched");
  assert(h.indexOf("The worker") === -1,
    "and must never be put through the subject shift");
  pass("Shadow's own voice stays first-person");
}

/* ══ 32. NO UPDATE → EXACTLY THE BEHAVIOUR THAT SHIPPED BEFORE ═════════
   Every mission that ran before this key existed, and every turn Shadow had
   nothing worth saying about. */
{
  const ctx = fresh();
  const msgs = [SH(T(0)), W("REPORT: Created the file with 10 items.", T(1))];
  ctx.S.goalTranscript = { "sess-1": msgs };
  const without = pane(ctx, M({ turns_used: 1 }));
  assert(/The worker created the file with 10 items\./.test(without),
    "with no update the deterministic shift is still the fallback");
  assert(!/shsayown/.test(without), "and the row is not marked as Shadow's own");
  /* a record with the key present but EMPTY behaves the same */
  const ctx2 = fresh();
  ctx2.S.goalTranscript = { "sess-1": msgs };
  const empty = pane(ctx2, M({ turns_used: 1, shadow_updates: [] }));
  assert.deepStrictEqual(said(empty), said(without),
    "an empty list must render byte-for-byte what no list renders");
  pass("without an update the pane draws exactly what it drew before");
}

/* ══ 33. A NARRATED TURN IS NEVER A LOST TURN ══════════════════════════
   The worker's output can be a raw payload this pane refuses to draw. Before
   pass 9 that turn simply vanished. If Shadow wrote a line about it, the line
   is the row -- the founder hears what happened. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W('REPORT: {"results": [{"title": "T20I series announced", '
                + '"url": "https://bcci.tv/news/1"}]}', T(1)),
    SH(T(2)), W("REPORT: Created india-cricket-news.txt with 10 items.", T(3)),
  ] };
  const h = pane(ctx, M({ turns_used: 2, objective: "Put the news in a file",
    shadow_updates: [
      { text: "I found ten current reports across the boards.", at_turn: 1 },
      { text: "I’ve written them to india-cricket-news.txt.", at_turn: 2 }] }));
  assert.deepStrictEqual(said(h), [
    "you: Put the news in a file",
    "shadow: Got it. I’m working through this now.",
    "shadow: I found ten current reports across the boards.",
    "shadow: I’ve written them to india-cricket-news.txt.",
  ], "the narrated turn must keep its place, got: " + said(h).join(" | "));
  for (const leak of ["bcci.tv", '"url"', '"results"', "{", "T20I series"])
    assert(h.indexOf(leak) === -1, "the payload leaked: " + leak);
  pass("a turn whose worker output was a payload is narrated, not dropped");
}

/* 33b. ONE VOICE, OR THE OTHER. Once Shadow is narrating a mission it
   narrates all of it: a turn it said nothing about is SILENCE, not a
   fallback to the worker's own sentence beside Shadow's. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: Searched the boards.", T(1)),
    SH(T(2)), W("REPORT: Created india-cricket-news.txt with 10 items.", T(3)),
  ] };
  const h = pane(ctx, M({ turns_used: 2, objective: "Put the news in a file",
    shadow_updates: [
      { text: "I found ten current reports across the boards.", at_turn: 1 }] }));
  assert.deepStrictEqual(said(h), [
    "you: Put the news in a file",
    "shadow: Got it. I’m working through this now.",
    "shadow: I found ten current reports across the boards.",
  ], "an un-narrated turn is silence, got: " + said(h).join(" | "));
  assert(h.indexOf("The worker created") === -1,
    "the worker's voice must not reappear beside Shadow's");
  /* ...and the shift is still the WHOLE rendering when nothing is narrated */
  const ctx2 = fresh();
  ctx2.S.goalTranscript = ctx.S.goalTranscript;
  const plain = pane(ctx2, M({ turns_used: 2,
    objective: "Put the news in a file" }));
  assert(/The worker created india-cricket-news\.txt with 10 items\./
    .test(plain), "with no updates the shift still renders every turn");
  pass("one voice per mission: Shadow's where it speaks, the shift where it "
       + "never did");
}

/* ══ 34. SHADOW IS NOT EXEMPT FROM THE RECORD FLOOR ════════════════════
   An `update` that is itself machinery must not reach the founder merely
   because Shadow wrote it. mission_engine.validate_update refuses these at
   the source; this is the second floor, at the presentation boundary. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: Created the file with 10 items.", T(1)),
  ] };
  const h = pane(ctx, M({ turns_used: 1, shadow_updates: [
    { text: "10 tool calls — Web search 6, fetched 3.", at_turn: 1 }] }));
  assert(h.indexOf("10 tool calls") === -1,
    "a machinery-shaped update must be refused even from Shadow");
  assert(/The worker created the file with 10 items\./.test(h),
    "and the turn falls back to what it drew before");
  pass("an update that is machinery is refused, and the turn is not lost");
}

/* ══ 35. CHRONOLOGY: FOUNDER → SHADOW → RESULT → DECISION ══════════════
   "A NEEDS YOU block must only appear after the work/evidence that caused
   the decision request has actually happened." */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: Drafted the loop.", T(1)),
  ] };
  const h = pane(ctx, M({ state: "paused", pause_reason: "founder_confirm",
    turns_used: 1, objective: "Plan a 10-day ride",
    done_when: [{ check: "the pace matches the trip you want",
                  tier: "founder_confirm", met: false }],
    shadow_updates: [
      { text: "I’ve got the loop. I need your call on the pace before I "
            + "finalise it.", at_turn: 1 }] }));
  const at = (needle) => h.indexOf(needle);
  assert(at("Plan a 10-day ride") > -1, "the founder's request opens it");
  assert(at("Got it. I’m working through this now.") > at("Plan a 10-day ride"),
    "Shadow answers it");
  assert(at("I need your call on the pace") > at("Got it."),
    "the result comes after Shadow's acknowledgement");
  assert(at("data-shcheckix=") > at("I need your call on the pace"),
    "and the decision comes after the work that caused it");
  assert((h.match(/data-shcheckix=/g) || []).length === 1,
    "NEEDS YOU is intact, with its one live control");
  pass("founder -> Shadow -> result -> decision, in that order");
}

/* ══ 36. QUEUED IS ALIVE, AND IS NOT RUNNING ═══════════════════════════
   (founder, 2026-09-21, pass 10: "QUEUED feels dead/unfinished ... make it
   feel intentional and alive without pretending that work has started.") */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "queued", turns_used: 0,
    objective: "Plan a 10-day ride", target_session: null }));

  /* A. it is not an empty page: the request, and Shadow answering it */
  const rows = said(h).map(r => r.replace(/<[^>]*>/g, " ")
                                 .replace(/\s+/g, " ").trim());
  assert.deepStrictEqual(rows, [
    "you: Plan a 10-day ride",
    "shadow: Got it. I’m lining this up now. QUEUED Waiting for a free slot "
      + "— I’ll start as soon as one opens. Nothing needed from you.",
  ], "queued must be acknowledged, got: " + rows.join(" | "));

  /* B. and it claims no work */
  for (const claim of ["working through this now", "Working", "shworking",
                       "shsayown", "shsay\""])
    assert(h.indexOf(claim) === -1,
      "queued must not claim worker progress: " + claim);
  assert(!/data-shcheckix=/.test(h), "and must ask for nothing");

  /* it says the three things a person needs and no more */
  assert(/shqueued/.test(h), "the queued line has its own hook");
  assert(/shtpill-queued[^>]*>QUEUED</.test(h),
    "and carries the pill this pane already draws for the state");
  /* the copy wraps in the source, so the claim is made on the words */
  assert(/Nothing needed from\s+you/.test(h), "and says so");
  /* calm: no new component was introduced for it */
  for (const busy of ["spinner", "progress", "shdoneburst", "shcard2"])
    assert(h.indexOf(busy) === -1, "queued must stay calm: " + busy);
  pass("A/B: queued is acknowledged, and claims no work");
}

/* 36b. C/D: QUEUED transitions cleanly, and leaves nothing stale */
{
  const queued = pane(fresh(), M({ state: "queued", turns_used: 0,
    objective: "Plan a 10-day ride", target_session: null }));
  assert(/shidlequeued/.test(queued), "queued draws the queued line");

  /* C. queued -> running: the acknowledgement becomes the running one */
  const ctxR = fresh();
  ctxR.S.goalTranscript = { "sess-1": [
    SH(T(0)), W("REPORT: Drafted the loop.", T(1)) ] };
  const running = pane(ctxR, M({ state: "running", turns_used: 1,
    objective: "Plan a 10-day ride" }));
  assert(!/shidlequeued/.test(running) && !/shqueued/.test(running),
    "no queued messaging may survive the promotion");
  assert(/Got it. I’m working through this now\./.test(running),
    "and the running acknowledgement takes its place");
  assert(/The worker drafted the loop\./.test(running),
    "with the worker's turn beneath it");

  /* D. queued -> stopped / failed: the queued line is gone there too */
  for (const st of ["stopped", "failed", "done"]){
    const ended = pane(fresh(), M({ state: st, turns_used: 1,
      objective: "Plan a 10-day ride" }));
    assert(!/shqueued/.test(ended),
      "stale queued messaging survived into " + st);
  }
  pass("C/D: queued transitions cleanly and leaves nothing stale behind");
}

/* ══ 37. THE PANE OPENS ON THE FIRST ROW OF THE LIST ═══════════════════
   (founder, 2026-09-21: "when we enter the Shadow tab the focus should be
   on the FIRST item of the left-hand side -- not some fifth or sixth.") */
{
  const ctx = fresh();
  const C = (n) => "2026-09-21T10:" + String(n).padStart(2, "0") + ":00Z";
  ctx.S.shadowMissions = [
    { id: "m-a", objective: "A running, oldest", state: "running",
      turns_used: 1, max_turns: 9, created_at: C(1), done_when: [] },
    { id: "m-b", objective: "B running, newest", state: "running",
      turns_used: 1, max_turns: 9, created_at: C(5), done_when: [] },
    { id: "m-c", objective: "C queued", state: "queued",
      turns_used: 0, max_turns: 9, created_at: C(4), done_when: [] },
    { id: "m-d", objective: "D needs you", state: "paused",
      pause_reason: "founder_confirm", turns_used: 2, max_turns: 9,
      created_at: C(2), done_when: [] },
  ];
  ctx.S.shadowTaskSel = null;
  const drawn = (ctx.shadowTaskListHtml().match(/data-shtask="([^"]+)"/g) || [])
    .map(x => x.slice(13, -1));
  assert.strictEqual(ctx.shadowSelectedTask().id, drawn[0],
    "the pane must open on the row the rail draws first, got "
    + ctx.shadowSelectedTask().id + " for a list of " + drawn.join(","));
  /* WAITING ON YOU is the list's first section, so a task that needs the
     founder still opens -- by the list's rule, not a second one */
  assert.strictEqual(drawn[0], "m-d", "attention still leads the list");

  /* ...and with nothing waiting, the newest running row leads */
  ctx.S.shadowMissions = ctx.S.shadowMissions.filter(m => m.id !== "m-d");
  const d2 = (ctx.shadowTaskListHtml().match(/data-shtask="([^"]+)"/g) || [])
    .map(x => x.slice(13, -1));
  assert.strictEqual(d2[0], "m-b", "recency decides inside a section");
  assert.strictEqual(ctx.shadowSelectedTask().id, d2[0],
    "and the pane follows it");

  /* THE FOUNDER'S OWN PICK STILL WINS -- this is only the default */
  ctx.S.shadowTaskSel = "m-c";
  assert.strictEqual(ctx.shadowSelectedTask().id, "m-c",
    "a clicked row must survive the default");
  pass("the pane opens on the first row of the rail, and a click still wins");
}

/* ══ 38. THE FINISH ANSWERS THE REQUEST, NOT THE LAST SENTENCE ═════════
   (founder, 2026-09-21, pass 10: "the worker's output is evidence, the
   artifact is the deliverable.") */
{
  const ctx = fresh();
  /* the worker's last message is ONE OF THE TEN LINES -- interesting, and
     not what was asked for */
  const completion = {
    headline: "2 of 2 checks passed", turns_used: 3, max_turns: 25,
    outcome: "A NASA-led reanalysis of JWST spectra from K2-18b found no "
           + "reliable dimethyl-sulfide signal.",
    artifacts: ["alien-species.txt"],
    checks: [{ check: "the file has 10 lines", met: true,
               how: "Shadow verified" },
             { check: "no two lines are the same", met: true,
               how: "Shadow verified" }],
  };
  const OBJ = "Make a file of 10 lines with the latest information about "
            + "alien species.";
  const CLOSE = "I wrote 10 sourced, unique lines on recent "
              + "extraterrestrial-life research to alien-species.txt. The "
              + "file has exactly 10 lines.";
  const h = pane(ctx, M({ state: "done", objective: OBJ,
    completion: completion,
    shadow_updates: [{ at_turn: 3, text: CLOSE }] }));

  /* E: the completion is Shadow's, at the level of the request */
  assert(h.indexOf("Done — " + CLOSE) !== -1,
    "the finish must answer the request, got: " + said(h).join(" | "));
  assert(h.indexOf("dimethyl-sulfide") === -1,
    "one of the ten lines must not stand in for the result");
  /* and the artifact is the deliverable, exposed as one */
  assert(/class="shdonefile">alien-species\.txt</.test(h),
    "the artifact must be there to open");
  /* no ten-line duplication in the conversation */
  assert(h.indexOf("K2-18b") === -1, "the file's contents stay in the file");

  /* Q: the fallback is unchanged for a mission with no update */
  const plain = pane(fresh(), M({ state: "done", objective: OBJ,
    completion: completion }));
  assert(/Done — a NASA-led reanalysis/.test(plain),
    "with no update the worker gist is still the fallback");
  pass("E/Q: the finish answers the request; the gist remains the fallback");
}

/* 38b. J: a verification claim is Shadow's to make, and only from the
   record -- the UI never composes one */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "done", objective: "Make a file",
    completion: { headline: "1 of 1", turns_used: 2, max_turns: 25,
      outcome: "Wrote it.", artifacts: ["a.txt"],
      checks: [{ check: "the file has 10 lines", met: true,
                 how: "Shadow verified" }] },
    shadow_updates: [{ at_turn: 2, text: "I wrote a.txt." }] }));
  assert(/Done — I wrote a\.txt\./.test(h), "Shadow's line is the finish");
  /* the pane adds no verification sentence of its own */
  assert(h.slice(0, h.indexOf("shdoneverif")).indexOf("checks passed") === -1,
    "the UI must not compose a verification claim");
  /* ...and the criteria are still one click away, unchanged */
  assert(/shdoneverif/.test(h) && h.indexOf("the file has 10 lines") > -1,
    "every criterion is still on the record and in the fold");
  pass("J: verification stays in the fold; the UI claims nothing");
}

/* ══ 39. THE FINISH CARRIES SHADOW'S OWN LINE (pass 12) ════════════════
   (founder, 2026-09-21.) THE EXACT FAILURE REPORTED:

       SHADOW  You confirmed: the 10-day Africa itinerary is the trip you want
       SHADOW  Done.
               Replaced an earlier plan: ...
               africa-10-day-plan.md

   A founder_confirm pause is settled WITHOUT A TURN, so nothing
   Shadow-authored existed for the completion to carry and the pane fell back
   to the worker's last message -- which for that mission cleaned to nothing.
   `completion.said` is stamped by mission_engine._complete, the one writer
   of a done mission, so BOTH routes to DONE carry it. */
{
  const OBJ = "I wanna visit Africa, make a 10 day plan I’d like";
  const SAID = "I built a 10-day Africa plan — Cape Town, three nights in "
             + "Sabi Sand and Victoria Falls to close — in "
             + "africa-10-day-plan.md.";
  const completion = {
    headline: "2 of 2 checks passed", turns_used: 4, max_turns: 25,
    outcome: "",                       /* the worker's last word cleaned away */
    was: "I wanna visit Africa, make a 15 day plan I’d like",
    artifacts: ["africa-10-day-plan.md"],
    checks: [{ check: "the 10-day Africa itinerary is the trip you want",
               met: true, how: "you confirmed it", by: "founder" }],
  };

  /* THE BUG, pinned so it cannot come back: with nothing Shadow-authored
     the finish is a bare "Done." -- grounded, and useless. */
  const bug = pane(fresh(), M({ state: "done", objective: OBJ,
    completion: completion }));
  assert(/<div class="shsaidtext">Done\.<\/div>/.test(bug),
    "with nothing to say the finish must be a bare Done.");

  /* B: the confirmed proposal, summarised by Shadow */
  const h = pane(fresh(), M({ state: "done", objective: OBJ,
    /* the confirmed check on the record, which is what puts "You confirmed"
       in the scrollback where the founder answered */
    done_when: [{ check: "the 10-day Africa itinerary is the trip you want",
                  tier: "founder_confirm", met: true,
                  confirmed_at: "2026-09-21T10:00:00Z" }],
    completion: Object.assign({}, completion, { said: SAID }) }));
  assert(h.indexOf("Done — " + SAID) !== -1,
    "the finish must carry Shadow's own line, got: " + said(h).join(" | "));
  /* the confirmation stays in the scrollback, above it */
  assert(/You confirmed: the 10-day Africa itinerary is the trip you want/
    .test(h), "the confirmation must still be on the record");
  assert(h.indexOf("You confirmed") < h.indexOf("Done — "),
    "and it must come before the finish");
  /* E: one voice -- no worker sentence, and the artifact chip stays */
  assert(/class="shdonefile">africa-10-day-plan\.md</.test(h),
    "the artifact chip must remain");
  for (const gone of ["DONE-CHECK", "shdonesummary", "What you can open",
                      "shconfirmq", "shdonework"])
    assert(h.indexOf(gone) === -1, "worker machinery on the finish: " + gone);
  pass("B/E: a confirmed proposal finishes with Shadow's own summary");
}

/* 39b. A: the direct artifact finishes the same way, and the ORDER of the
   three fallbacks is what decides which sentence is used */
{
  const completion = {
    headline: "2 of 2 checks passed", turns_used: 3, max_turns: 25,
    outcome: "A NASA-led reanalysis of JWST spectra found no signal.",
    artifacts: ["alien-species.txt"],
    checks: [{ check: "the file has 10 lines", met: true,
               how: "Shadow verified" }],
  };
  const OBJ = "Make a file of 10 lines about alien species";
  const SAID = "alien-species.txt has 10 sourced, unique lines on recent "
             + "extraterrestrial-life research.";

  /* 1. completion.said wins over everything */
  const one = pane(fresh(), M({ state: "done", objective: OBJ,
    completion: Object.assign({}, completion, { said: SAID }),
    shadow_updates: [{ at_turn: 3, text: "I’m checking the sources." }] }));
  assert(one.indexOf("Done — " + SAID) !== -1,
    "the stamped result must win over the newest update");
  assert(one.indexOf("dimethyl") === -1 && one.indexOf("JWST") === -1,
    "and over the worker's last sentence");

  /* 2. no stamped result -> the newest update (pass 10 behaviour, kept) */
  const two = pane(fresh(), M({ state: "done", objective: OBJ,
    completion: completion,
    shadow_updates: [{ at_turn: 3, text: "I wrote the ten lines to the file." }] }));
  assert(/Done — I wrote the ten lines to the file\./.test(two),
    "without a stamped result the newest update is the finish");

  /* 3. neither -> the worker gist (the original fallback, unchanged) */
  const three = pane(fresh(), M({ state: "done", objective: OBJ,
    completion: completion }));
  assert(/Done — a NASA-led reanalysis/.test(three),
    "and with neither, the worker gist still stands");
  pass("A: the finish prefers Shadow's result, then its update, then the gist");
}

/* 39c. D: a stamped line that is machinery is refused like any other, and
   the finish falls back rather than printing it */
{
  const h = pane(fresh(), M({ state: "done", objective: "Make a file",
    completion: { headline: "1 of 1", turns_used: 2, max_turns: 25,
      outcome: "", artifacts: ["a.txt"],
      said: '{"path": "a.txt", "lines": 10}',
      checks: [{ check: "the file exists", met: true, how: "Shadow verified" }] } }));
  assert(h.indexOf('{"path"') === -1,
    "a machinery-shaped result must be refused even from Shadow");
  assert(/<div class="shsaidtext">Done\.<\/div>/.test(h),
    "and the finish falls back to the grounded minimum");
  pass("D: a machinery-shaped result is refused; nothing is invented");
}

/* ══ 40. THE FINISH DELIVERS THE RESULT, NOT ITS FILENAME (pass 14) ════
   (founder, 2026-09-21: "Founder confirmation controls WHETHER a proposal
   may become done. It does NOT control whether Shadow shows the resulting
   deliverable.") */
{
  const PLAN = "Day 1  Arrive Kilimanjaro — overnight Arusha\n"
             + "Day 2  Tarangire — elephants along the river\n"
             + "Day 3  Ngorongoro Crater rim\n"
             + "Day 4  Crater floor, then Serengeti\n"
             + "Day 5  Serengeti — fly back to Kilimanjaro";
  const completion = {
    headline: "1 of 1 checks passed", turns_used: 4, max_turns: 25,
    outcome: "", artifacts: ["africa-5-day-plan.md"],
    said: "I built the 5-day Tanzania northern-circuit plan in "
        + "africa-5-day-plan.md.",
    preview: { path: "africa-5-day-plan.md", text: PLAN, truncated: true,
               lines: 31 },
    checks: [{ check: "the itinerary is the trip you want", met: true,
               how: "you confirmed it", by: "founder" }],
  };
  const h = pane(fresh(), M({ state: "done",
    objective: "I wanna visit Africa, make a 5 day plan I’d like",
    done_when: [{ check: "the itinerary is the trip you want",
                  tier: "founder_confirm", met: true,
                  confirmed_at: "2026-09-21T10:00:00Z" }],
    completion: completion }));

  /* Shadow's line, AND the plan itself */
  assert(h.indexOf("Done — I built the 5-day Tanzania northern-circuit plan")
    !== -1, "Shadow's own line must still lead");
  assert(/class="shdoneprev"/.test(h), "the deliverable must be rendered");
  for (const day of ["Day 1  Arrive Kilimanjaro", "Day 3  Ngorongoro Crater",
                     "Day 5  Serengeti"])
    assert(h.indexOf(day) !== -1, "the plan structure is missing: " + day);
  /* concise: the cut is reported, and the whole file is one click away */
  assert(/class="shdeccut"/.test(h), "a cut preview must say it was cut");
  assert(/class="shdonefile">africa-5-day-plan\.md</.test(h),
    "the artifact chip must remain");
  /* and none of the machinery came back with it */
  for (const gone of ["shdonesummary", "What you can open", "shconfirmq",
                      "DONE-CHECK"])
    assert(h.indexOf(gone) === -1, "machinery on the finish: " + gone);
  /* the confirmation is still in the scrollback, above it */
  assert(h.indexOf("You confirmed: the itinerary is the trip you want")
    < h.indexOf("Done — "), "the confirmation comes first");
  pass("a confirmed proposal delivers the plan, not just its filename");
}

/* 40b. an explicit "give me the lines" finish carries them, whole */
{
  const TEN = Array.from({ length: 10 },
    (_, i) => (i + 1) + ". a sourced line about Pedro Acosta.").join("\n");
  const h = pane(fresh(), M({ state: "done",
    objective: "Make a file of 10 lines about Pedro Acosta and print them",
    completion: { headline: "1 of 1", turns_used: 3, max_turns: 25,
      outcome: "", artifacts: ["pedro-acosta.txt"],
      said: "pedro-acosta.txt has the 10 lines.",
      preview: { path: "pedro-acosta.txt", text: TEN, truncated: false,
                 lines: 10 },
      checks: [{ check: "the file has 10 lines", met: true,
                 how: "Shadow verified" }] } }));
  for (let i = 1; i <= 10; i++)
    assert(h.indexOf(i + ". a sourced line about Pedro Acosta.") !== -1,
      "line " + i + " is missing from the finish");
  assert(!/class="shdeccut"/.test(h), "ten lines fit, so nothing is cut");
  pass("an explicit print request is answered with the lines themselves");
}

/* 40c. GROUNDED: no preview on the record -> nothing is drawn, and the
   finish falls back exactly as it did */
{
  const h = pane(fresh(), M({ state: "done", objective: "Make a file",
    completion: { headline: "1 of 1", turns_used: 2, max_turns: 25,
      outcome: "", artifacts: ["a.txt"], said: "I wrote a.txt.",
      checks: [{ check: "the file exists", met: true,
                 how: "Shadow verified" }] } }));
  assert(!/shdoneprev/.test(h), "no preview must be drawn without one");
  assert(/Done — I wrote a\.txt\./.test(h),
    "and Shadow's line still stands alone");
  /* an empty preview is the same as none */
  const blank = pane(fresh(), M({ state: "done", objective: "Make a file",
    completion: { headline: "1 of 1", turns_used: 2, max_turns: 25,
      outcome: "", artifacts: ["a.txt"], said: "I wrote a.txt.",
      preview: { path: "a.txt", text: "   \n\n", truncated: false },
      checks: [] } }));
  assert(!/shdoneprev/.test(blank), "an empty preview draws nothing");
  pass("with no grounded contents the finish shows none, and invents none");
}

/* ══ 41. A GREETING IS ANSWERED, AND THAT IS ALL (pass 15) ═════════════
   (founder, 2026-09-21.) "Hi" showed NEEDS YOU and carried the criterion
   "the chat has answered the greeting..." -- a reply the founder never saw.
   The criteria layer was asserting a user-visible response that had not been
   rendered. The refusal is in mission_engine.validate_done_when; this is the
   render half: what IS stored is what IS shown. */
{
  const ctx = fresh();
  /* Shadow's answer, as the task chat actually holds it */
  ctx.S.goalTranscript = { "sess-1": [], "shadow-1": [
    { role: "user", text: "Hi", ts: T(0) },
    { role: "assistant", text: "Hi! What can I help you with?", ts: T(1) },
  ] };
  const h = pane(ctx, M({ state: "brief_confirm", objective: "Hi",
    turns_used: 0, target_session: null, done_when: [] }));

  /* #1 + #6: the stored reply is the rendered reply, once */
  assert(/Hi! What can I help you with\?/.test(h),
    "Shadow's greeting must be visible in the conversation");
  assert.strictEqual(
    (h.match(/Hi! What can I help you with\?/g) || []).length, 1,
    "and exactly once");
  assert(/class="shsaid shfrom-shadow/.test(h), "on Shadow's side");

  /* #2 + #3: nothing is waiting on the founder */
  assert(!/data-shcheckix=/.test(h), "a greeting must ask for no decision");
  assert(!/Shadow needs your decision/.test(h), "and show no decision surface");
  assert(!/shask-hold|shask-question|shask-parked/.test(h),
    "and raise no ask of any kind");

  /* #5: no diagnostics stand in for the answer */
  for (const noise of ["repo sits at", "uncommitted", "modified Shadow files",
                       "v2.291"])
    assert(h.indexOf(noise) === -1, "diagnostics reached the founder: " + noise);
  pass("a greeting is answered visibly, once, and asks for nothing");
}

/* 41b. AND A CRITERION ABOUT THE CONVERSATION NEVER REACHES THE SURFACE.
   Even handed one on the record, the decision surface has nothing to draw:
   the engine drops it before it is stored, and a check the founder cannot
   see is a check they can never honestly sign. */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "brief_confirm", objective: "Hi",
    turns_used: 0, target_session: null, done_when: [] }));
  assert(h.indexOf("the chat has answered the greeting") === -1,
    "a self-referential criterion must not be drawn");
  /* the READY line is what a drafted task says, and it is unchanged */
  assert(/Everything is ready — start when you are\./.test(h),
    "a drafted task still offers Start");
  pass("no criterion about the conversation reaches the founder's surface");
}

console.log("\nall shadow conversation-model tests passed");
