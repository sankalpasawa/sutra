#!/usr/bin/env node
/* test_shadow_rhs.js -- the right pane is SHADOW REPORTING, not the worker chat.
 *
 * THE DESIGN THIS PINS ("Shadow Design - Final", founder 2026-09-15). The RHS
 * reads top to bottom as one editorial column:
 *
 *     seal + title + status + Open the chat     who, and the way OUT to the
 *                                               delegate's real conversation
 *     the brief          WHERE IT RUNS / DONE WHEN / TURN
 *     worker agent       ONE line of the latest turn -- never the transcript
 *     the ask            Shadow's decision boundary, as its own card
 *     the story          what you answered, and what Shadow said next
 *     remember           what Shadow wants to keep, with the existing confirm
 *     say anything       the SHADOW<->FOUNDER channel (/api/shadow/chat)
 *
 * THE DISTINCTION THAT MATTERS MOST, asserted several ways below: this pane
 * is Shadow talking to the founder. The worker's own chat lives behind
 * "Open the chat" (data-shtakeover -> target_session) and behind the
 * "Show worker chat" toggle, and neither is replaced or merged here.
 *
 * PRESENTATION ONLY. Every hook, handler, endpoint and payload under test is
 * the one that already existed; this file exists to prove the redesign moved
 * pixels and not behaviour.
 *
 * Run: node test_shadow_rhs.js
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
  /* shadowSubmitCompose is scoped inside the wiring block, not a global, so
     the composer is driven the way the app drives it: Enter on the box. */
  ctx.typeAndSend = (el) => (ctx.listeners.keydown || []).forEach(fn => fn({
    key: "Enter", shiftKey: false, target: el,
    preventDefault(){}, stopPropagation(){} }));
  /* the Assignment module's real contract, same shape as 18-goal-workspace */
  ctx.loadGoalTranscript = (sid) => { ctx.fetched.push(sid); };
  ctx.goalMessages = (sid) => (ctx.S.goalTranscript || {})[sid];
  ctx.goalTranscriptHtml = (msgs) => (msgs || [])
    .map(m => `<div class="gwturn">${m.text}</div>`).join("");
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "EMI auto-fix", template: "fix",
  target_mode: "new", target_session: "sess-1", target_chat: "c-1",
  state: "running", turns_used: 10, max_turns: 12,
  done_when: [{ check: "the fix runs before every EMI check", tier: "auto" },
              { check: "a tested PR is open", tier: "auto" }],
}, over);

/* render the whole right pane for one mission, the way the app does */
function pane(ctx, m, extra){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  Object.assign(ctx.S, extra || {});
  return ctx.shadowHomeHtml();
}

/* ── 1. the header: who, what state, and the door to the WORKER chat ──── */
{
  const ctx = fresh();
  const h = pane(ctx, M());
  assert(/class="shwseal"/.test(h), "the Shadow seal is the pane's identity");
  assert(/class="shwtitle">EMI auto-fix</.test(h), "the task titles the pane");
  assert(/shtpill-running[^>]*>RUNNING</.test(h),
    "the current user-facing status sits in the header");
  assert(/class="shwheadacts"/.test(h), "the header's action group is missing");
  assert(/data-shtakeover="sess-1"[^>]*>Open the chat</.test(h),
    "Open the chat must be in the header, pointed at the worker session");
  console.log("ok 1 header: seal, title, status pill, Open the chat");
}

/* ── 2. OPEN THE CHAT IS THE ONLY DOOR TO THE WORKER CONVERSATION ────────
   The hook and the id are the delegate's session, unchanged. The RHS never
   becomes that chat: the transcript block is still behind its own toggle. */
{
  const ctx = fresh();
  const m = M();
  const h = pane(ctx, m);
  const hooks = (h.match(/data-shtakeover="[^"]*"/g) || []);
  assert.deepStrictEqual(hooks, ['data-shtakeover="sess-1"'],
    "exactly one worker-chat door, carrying the mission's target_session");
  /* the full transcript is NOT dumped into the pane */
  assert(!/class="gwturns"/.test(h) && !/gwchat/.test(h),
    "the RHS must not render the worker transcript inline");
  /* ONE DOOR, NOT TWO (founder, 2026-09-15). The inline toggle came off the
     card; Open the chat in the header is the single entry point. The
     transcript, its renderer and the data-shtaskchat handler are untouched. */
  assert(!/data-shtaskchat/.test(h),
    "the card must not offer a second door to the worker chat");
  assert(!/worker chat/i.test(h), "the toggle label must be gone");
  console.log("ok 2 the worker chat stays behind exactly one control");
}

/* ── 3. the brief, in the reference's words ──────────────────────────── */
{
  const ctx = fresh();
  ctx.S.sessions = [{ id: "sess-1", title: "paisa" }];
  const h = pane(ctx, M());
  assert(/shcard2k">where it runs</.test(h), "WHERE IT RUNS row missing");
  assert(/shcard2k">done when</.test(h), "DONE WHEN row missing");
  assert(/shcard2k">turn<\/span>\s*<span class="shcard2v">10 of 12/.test(h),
    "TURN row must read 10 of 12, from the record");
  assert(/its own chat/.test(h), "where it runs still resolves the target");
  assert(/a tested PR is open/.test(h), "done_when still comes from the record");
  /* and nothing else: no STOPPED ON, no LAST UPDATED, no floors */
  const blocked = pane(fresh(), M({ state: "blocked",
    block_reason: "needs_founder" }));
  assert(!/stopped on/.test(blocked),
    "STOPPED ON restates the NEEDS YOU pill in the engine's words");
  assert(!/needs founder/.test(blocked), "the raw blocker must not be drawn");
  assert(!/last updated/.test(blocked), "LAST UPDATED must stay off the brief");
  console.log("ok 3 the brief is WHERE IT RUNS / DONE WHEN / TURN, and no more");
}

/* ── 4. WORKER AGENT: one report of the latest turn, never the transcript ─ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    { role: "user", text: "[Shadow · mission m-1] carry on" },
    { role: "assistant", text: "ran the suite, 9 green" },
    { role: "user", text: "[Shadow · mission m-1] and the PR?" },
    { role: "assistant", text: "14 tests green, PR #212 open. The push is a "
      + "floor, so I stopped here." },
  ] };
  const h = pane(ctx, M());
  assert(/class="shagent"/.test(h), "the agent block is missing");
  /* BOTH TURNS, IN ORDER (founder, 2026-09-15). This used to assert that
     only the latest survived; that was the defect -- turn 2 erased turn 1
     and the delegation lost its history. */
  assert(/ran the suite, 9 green/.test(h), "turn 1 must still be here");
  assert(/14 tests green, PR #212 open/.test(h), "and turn 2 beside it");
  assert(h.indexOf("ran the suite, 9 green") < h.indexOf("14 tests green"),
    "and in the order they happened");
  /* THE NUMBER IS THE BACKEND'S: session_reader counts turns as USER
     messages, so this transcript is two turns however high turns_used
     climbs in an artificial fixture. On real records the two agree -- the
     six-turn release mission numbers 1..6 against turns_used 6. */
  /* two turns held, turns_used 10 -> they are turns 9 and 10, counted back
     from the record. Numbering them 1 and 2 would relabel history. */
  assert(/Worker agent · turn 9</.test(h) && /Worker agent · turn 10</.test(h),
    "turns are anchored to turns_used, not to what the transcript holds");
  assert(!/>The agent/.test(h), "the old THE AGENT label is still on screen");
  /* A TIMELINE, NOT A DUMP: one line per turn, and Shadow's own injected
     instructions are never drawn as the worker speaking. */
  assert.strictEqual((h.match(/class="shagentsay"/g) || []).length, 2,
    "one line per turn -- not the transcript");
  assert(h.indexOf("carry on") === -1 && h.indexOf("and the PR?") === -1,
    "Shadow's own injected turns are not the agent reporting");
  assert(!/class="gwturns"/.test(h), "and the transcript is still not inlined");
  console.log("ok 4 the timeline keeps every turn, one line each, in order");
}

/* ── 4b. THE PREVIEW IS A CLAMPED QUOTE, NOT A SUMMARY ─────────
   The line under WORKER AGENT is the worker's own latest words, cut to one
   line for the glance and clamped again in CSS so no pane width can grow it
   into a paragraph. The untruncated sentence rides on the title, and the
   whole turn stays behind Open the chat. */
{
  const ctx = fresh();
  const LONG = "Rewired the delegate spawn path so a stalled worker is "
    + "adopted instead of respawned, which is what was doubling the turn "
    + "count on every resume, and then re-ran the whole suite twice.";
  ctx.S.goalTranscript = { "sess-1": [{ role: "assistant", text: LONG }] };
  const h = pane(ctx, M({ turns_used: 4 }));

  assert(/Worker agent \u00b7 turn 4/.test(h), "the WORKER AGENT heading is missing");
  const say = (h.match(/class="shagentsay"[^>]*>([^<]*)</) || [])[1] || "";
  assert(say, "the preview line is missing");
  assert(!/\n/.test(say), "the preview must be a single line");
  assert(LONG.indexOf(say.replace(/\s\u2026$/, "")) === 0,
    "the preview must be a PREFIX of the worker's real words, got: " + say);
  /* the full sentence is reachable without opening the chat */
  assert(/class="shagentsay" title="/.test(h),
    "the untruncated line must ride on the title attribute");

  /* and the VISUAL floor, so a narrow pane cannot wrap it to two rows */
  const css = fs.readFileSync(
    path.join(__dirname, "static", "panel.css"), "utf8");
  const rule = css.slice(css.indexOf(".shagentsay{"));
  const decl = rule.slice(0, rule.indexOf("}"));
  assert(/-webkit-line-clamp:\s*1/.test(decl) && /overflow:hidden/.test(decl),
    "the preview must be clamped to ONE line in CSS");
  assert(!/pre-wrap/.test(decl),
    "pre-wrap would honour a newline and break the one-line preview");
  console.log("ok 4b the preview is the worker's own words, clamped to one line");
}

/* ── 5. no report to make -> no furniture ────────────────────────────── */
{
  const ctx = fresh();
  const h = pane(ctx, M({ target_session: null }));
  assert(!/class="shagent"/.test(h),
    "with nothing to report the block draws nothing at all");
  assert.strictEqual(ctx.fetched.length, 0,
    "a mission with no session must not trigger a transcript read");
  console.log("ok 5 nothing to report -> nothing drawn, nothing fetched");
}

/* ── 5b. the latest turn is read through the EXISTING throttled reader ──
   One read for the ONE mission in focus, then nothing until the window is
   up -- the same shTranscriptAt/SH_TRANSCRIPT_MS gate the worker-chat block
   has always used. No second transcript store, no new endpoint. */
{
  const ctx = fresh();
  const m = M();
  pane(ctx, m); pane(ctx, m); pane(ctx, m);
  assert.deepStrictEqual(ctx.fetched, ["sess-1"],
    "three renders inside one throttle window are one read, not three");
  console.log("ok 5b the agent block reuses the throttled transcript reader");
}

/* ── 6. THE ASK IS ITS OWN CARD, and every hook still belongs to it ───── */
const IV = {
  id: "iv-1", schema_version: 1,
  question: "Approve the push to paisa?",
  context: "The push is a floor.",
  evidence: [{ ref: "PR #212", text: "14/14" }],
  submit_label: "Send to Shadow",
  fields: [{ key: "approve", type: "boolean", label: "Approve", required: true }],
};
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "blocked", intervention: IV }));
  assert(/data-shivform="iv-1"/.test(h), "the intervention id must be intact");
  assert(/Approve the push to paisa\?/.test(h), "the question renders");
  assert(/PR #212/.test(h) && /14\/14/.test(h), "the evidence renders");
  assert(/data-shivmid="m-1" data-shivkey="approve"/.test(h),
    "the field hooks carry the mission id and the field key, unchanged");
  assert(/data-shivsend="m-1"/.test(h), "the submit hook is unchanged");
  assert(/Send to Shadow/.test(h), "the server's submit label is used as sent");
  /* it is a SIBLING of the brief now, not nested inside it */
  assert(h.indexOf('class="shiv"') > h.indexOf('data-shtaskcard'),
    "the ask is drawn after the brief, as its own card");
  assert(ctx.shadowTaskCardHtml(M({ state: "blocked", intervention: IV }))
    .indexOf('class="shiv"') === -1,
    "the brief card must no longer nest the ask");
  /* and the state behind it is untouched */
  assert(/shtpill-blocked[^>]*>NEEDS YOU</.test(h),
    "blocked still reads NEEDS YOU in the header");
  console.log("ok 6 the ask is a standalone card with every hook intact");
}

/* ── 7. EVERY TYPED INTERVENTION STILL DRAWS. The redesign restyled the
   boolean pair; it must not have narrowed the renderer to it. ─────────── */
{
  const ctx = fresh();
  const types = ["boolean", "choice", "multi_choice", "text", "long_text",
    "number", "currency", "percent", "date", "datetime", "url", "email",
    "ranking"];
  for (const t of types){
    const f = { key: "k_" + t, type: t, label: "Ask " + t,
      options: [{ value: "a", label: "A" }, { value: "b", label: "B" }] };
    const h = pane(ctx, M({ id: "m-" + t, state: "blocked",
      intervention: Object.assign({}, IV, { id: "iv-" + t, fields: [f] }) }));
    assert(/class="shivfield"/.test(h), t + ": the field wrapper is missing");
    assert(new RegExp('data-shivkey="k_' + t + '"').test(h),
      t + ": the field lost its hook");
    assert(!/cannot ask for/.test(h), t + ": drew the unknown-type fallback");
  }
  /* and a type this build does not know is still honest rather than silent */
  const un = pane(ctx, M({ id: "m-x", state: "blocked",
    intervention: Object.assign({}, IV, { id: "iv-x",
      fields: [{ key: "k", type: "hologram", label: "?" }] }) }));
  assert(/cannot ask for/.test(un), "an unknown type must say so, not vanish");
  console.log("ok 7 all 13 typed interventions still render");
}

/* ── 8. THE STORY: what you answered, and what Shadow said next ───────── */
{
  const ctx = fresh();
  const h = pane(ctx, M({
    founder_response: { intervention_id: "iv-1",
      question: "Sign off on release-checklist.md as written?",
      answered_at: new Date(Date.now() - 3600000).toISOString(),
      summary: [{ key: "checklist_approved", label: "the checklist is approved",
                  value: "True" }] },
    last_instruction: "Accepted — folding the dual-arch verify gate in.",
  }));
  assert(/class="shstory"/.test(h), "the story block is missing");
  assert(/You answered · 1h ago/.test(h),
    "what you answered, stamped from founder_response.answered_at");
  assert(/Sign off on release-checklist\.md/.test(h),
    "the question you answered is quoted from the record");
  assert(/the checklist is approved/.test(h), "the answer summary renders");
  /* THE WORKER'S OWN INSTRUCTION IS NOT A FOUNDER REPORT (founder,
     2026-09-15). last_instruction is the turn Shadow injects INTO the
     delegate -- "You are a delegate session working for the founder via
     Shadow. Objective: ... Work step by step" -- addressed to the agent.
     It belongs to the worker chat, and it is still on the record, still
     sent and still received; this pane simply stopped drawing it. */
  assert(!/Shadow → the agent/.test(h),
    "the internal worker instruction must not be drawn on the RHS");
  assert(!/folding the dual-arch verify gate/.test(h),
    "last_instruction must not reach the founder-facing pane");
  assert(!/delegate session working for the founder/
    .test(pane(fresh(), M({ last_instruction:
      "You are a delegate session working for the founder via Shadow. "
      + "Objective: x. Work step by step." }))),
    "the worker's own briefing must never appear on the RHS");
  /* ...and a mission with ONLY that instruction has no story to tell */
  assert(!/class="shstory"/.test(pane(fresh(), M({ last_instruction: "x" }))),
    "an instruction alone is not a story");
  assert(!/class="shstory"/.test(pane(fresh(), M())),
    "no answer -> no story block");
  console.log("ok 8 the story is your answer only; the worker briefing is gone");
}

/* ── 8b. THE WORKER AGENT BLOCK IS A SUMMARY, NOT A CONSOLE ─────────────
   The delegate is itself a governed session, so its turns open with this
   repo's own control plane. None of it is addressed to the founder, and
   none of it may reach this pane. */
const LEAKED = [
  'PLACEMENT: D0 Joy Tadanki | "Joy Tadanki Charter"',
  '  (domain_ref=dref-feea2aad confidence=0.219 - engine output)',
  '',
  'TYPE: task (malformed)',
  'HOME: sutra/marketplace/plugin/sutra-ui',
  'ROUTE: none',
  'OBJECTIVE: unparsable',
  'FIT: fails',
  'ACTION: halt, request restatement',
  '',
  'TASK: "interpret Shadow mission"',
  'DEPTH: 1/5',
  'EFFORT: <1 min',
  'COST: ~$0',
  'IMPACT: none',
  '',
  'TRIAGE: depth_selected=1, depth_correct=1, class=correct',
].join("\n");
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [{ role: "assistant", text: LEAKED }] };
  const h = pane(ctx, M({ state: "running", turns_used: 1 }));
  /* IN THE TIMELINE A TURN THAT SAID NOTHING TAKES NO ROW (founder,
     2026-09-15). A numbered heading with an empty body under it is
     furniture, and on a timeline it reads as a turn that happened and was
     lost. The turn is still in the worker chat, unabridged. */
  assert(!/class="shagent"/.test(h),
    "an all-control turn must take no row on the timeline");
  for (const word of ["PLACEMENT", "domain_ref", "ROUTE:", "OBJECTIVE:",
                      "FIT:", "DEPTH:", "EFFORT:", "COST:", "IMPACT:",
                      "TRIAGE:", "Joy Tadanki Charter"]){
    assert(h.indexOf(word) === -1,
      "control-plane material reached the founder: " + word);
  }
  /* A TURN THAT WAS ALL CONTROL PLANE QUOTES NOTHING (founder, 2026-09-15).
     The preview is the WORKER'S OWN WORDS; a state-derived stand-in in that
     slot reads as something the worker said, so no line is drawn at all. */
  assert(!/class="shagentsay"/.test(h),
    "an all-control turn must draw no preview line, not a substituted phrase");
  assert(!/Working on it/.test(h),
    "no hardcoded status phrase may stand in for the worker's own words");
  console.log("ok 8b the control plane never reaches the founder");
}

/* ── 8c. real prose survives, and stays short ────────────────────── */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [{ role: "assistant", text: [
    'PLACEMENT: D0 Joy Tadanki | "Joy Tadanki Charter"',
    'DEPTH: 2/5',
    '==================',
    '',
    '14 tests green, PR #212 open. The push is a floor, so I stopped here.',
    'The changelog entry and the version bump are what is left, plus a note '
      + 'in RELEASES.md about the dual-arch verify gate and notarization.',
    '',
    '```',
    'TRIAGE: depth_selected=2',
    '```',
  ].join("\n") }] };
  const h = pane(ctx, M({ turns_used: 10 }));
  assert(/14 tests green, PR #212 open/.test(h), "the real report was lost");
  /* everything past the first sentence is the worker chat's job now */
  assert(!/The push is a floor, so I stopped here/.test(h),
    "only the first sentence belongs in the one-line block");
  assert(!/PLACEMENT|DEPTH:|TRIAGE:/.test(h), "control plane leaked");
  /* ONE LINE (founder, 2026-09-15): one sentence, and short enough to read
     at a glance. The rest of the turn is in the worker chat. */
  const say = (h.match(/class="shagentsay"[^>]*>([^<]*)</) || [])[1] || "";
  assert(say.length <= 170, "the line must stay short, got " + say.length);
  assert(!/\n/.test(say), "the block must be a single line");
  assert.strictEqual(
    say.replace(/\s\u2026$/, "").replace(/[.!?]+$/, "").split(/[.!?]+\s/).length,
    1, "exactly one sentence, got: " + say);
  assert(/^14 tests green, PR #212 open\./.test(say),
    "the one line must be the agent's own first sentence");
  assert(!/changelog/.test(say), "the second sentence belongs in the chat");
  /* prose that merely MENTIONS a control word is not control material */
  assert.strictEqual(ctx.shadowSayClean(
    "The cost of the migration is high. Impact on users is small."),
    "The cost of the migration is high. Impact on users is small.",
    "ordinary prose must not be filtered");
  console.log("ok 8c the report survives the filter, trimmed to a paragraph");
}

/* ── 8d. THE SCREENSHOT CASE: a heading over a markdown table ───────
   VERBATIM from mission m-09ec0d640f7c (founder, 2026-09-15). The delegate
   reports a refusal as a `## heading` over a `| Field | Value | Problem |`
   grid. The grid has no terminal punctuation, so it fused onto the heading
   and the 160-char cut landed mid-row: the founder read
   "## Stopped — objective is not actionable | Field | Value received |
   Problem | |---|---| | Objective | `bjbhjb` | Not a word, …" in a box
   labelled with the worker's name. */
const TABLE_TURN = [
  'PLACEMENT: D0 Joy Tadanki | "Joy Tadanki Charter"',
  '',
  '```',
  'TYPE: task (malformed)',
  'ROUTE: none — objective unparseable',
  '```',
  '',
  '## Stopped — objective is not actionable',
  '',
  '| Field | Value received | Problem |',
  '|---|---|---|',
  '| Objective | `bjbhjb` | Not a word, acronym, path, or command |',
  '| Done-when | `bhbh` | No verifiable completion criterion |',
  '',
  'Both fields look like keyboard mash — likely a test dispatch.',
].join("\n");
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [{ role: "assistant", text: TABLE_TURN }] };
  const h = pane(ctx, M({ state: "blocked", turns_used: 1 }));
  const say = (h.match(/class="shagentsay"[^>]*>([^<]*)</) || [])[1] || "";

  /* the heading IS the sentence the founder wanted, and it is the worker's
     own words -- only the hashes and a full stop were touched */
  assert.strictEqual(say, "Stopped — objective is not actionable.",
    "the preview must be the worker's own heading, got: " + say);
  assert(say.length < 60, "and it must be one short line, got " + say.length);

  /* NOT ONE CELL OF THE GRID */
  assert(say.indexOf("|") === -1, "a table row reached the founder");
  for (const cell of ["Value received", "bjbhjb", "Not a word", "---",
                      "Done-when", "No verifiable"]){
    assert(h.indexOf(cell) === -1, "table content leaked: " + cell);
  }
  assert(!/PLACEMENT|TYPE:|ROUTE:/.test(h), "control plane leaked");
  console.log("ok 8d a heading over a table reads as the heading, alone");
}

/* ── 8e. the two guards, asserted on the functions themselves ─────── */
{
  const ctx = fresh();
  /* clean: rows go, the heading keeps its words and gains only a full stop */
  assert.strictEqual(
    ctx.shadowSayClean("## All green\n| a | b |\n|---|---|\n| 1 | 2 |"),
    "All green.", "clean must drop the grid and close the heading");
  assert.strictEqual(ctx.shadowSayClean("### Done already."), "Done already.",
    "a heading that already ends in a stop gains nothing");
  assert.strictEqual(ctx.shadowSayClean("| only | a | table |"), "",
    "a turn that is nothing but a grid cleans to nothing");
  /* gist: even if a pipe reached it, cut AT the structure, never through */
  /* the ellipsis is right here: something WAS cut, and saying so is honest */
  assert.strictEqual(ctx.shadowSayGist("A real sentence | Field | x |"),
    "A real sentence \u2026", "the guard must cut at the pipe, not mid-row");
  assert.strictEqual(ctx.shadowSayGist("| x | y |"), "",
    "a pipe-only fragment says nothing rather than half a row");
  /* and an all-control turn still draws NO line (no invented speech) */
  const ctl = fresh();
  ctl.S.goalTranscript = { "sess-1": [{ role: "assistant",
    text: "PLACEMENT: x\nDEPTH: 1/5\nTRIAGE: ok" }] };
  const h = pane(ctl, M({ state: "running", turns_used: 1 }));
  assert(!/class="shagentsay"/.test(h), "no line may be drawn");
  assert(!/Working on it|Queued|Paused\./.test(h),
    "no state-derived phrase may stand in for the worker");
  console.log("ok 8e clean and gist can never emit structure or invention");
}

/* ── 8f. THE ASK IS CALM: context clamped, long instructions in the box ──
   Neither string is edited. The decider's words are delivered whole -- the
   clamp is CSS and the instruction moves into the control it instructs. */
const CTX_375 = "The chat did the right thing — it refused to guess, touched "
  + "no files, and reported the round-trip cleanly. I can't resolve this "
  + "myself because neither field carries any recoverable meaning, so there's "
  + "nothing for me to instruct it to go find out.";
const LABEL_112 = "If not a smoke test: the actual objective — what should "
  + "change, in which surface, and what state counts as done.";
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "blocked", intervention: {
    id: "iv-1", question: "Was this a smoke test?", context: CTX_375,
    evidence: [], submit_label: "Send to Shadow",
    fields: [
      { key: "smoke_ok", type: "boolean", required: true,
        label: "This was a smoke test and the round-trip is satisfactory." },
      { key: "real_objective", type: "long_text", required: false,
        label: LABEL_112 },
    ] } }));

  /* the context is DELIVERED WHOLE, and clamped only in CSS */
  assert(/class="shnewsub shivctx"/.test(h), "the context lost its clamp hook");
  assert(h.indexOf(CTX_375.slice(0, 60)) !== -1,
    "the decider's context must not be shortened, only clamped");
  assert(/shivctx[^>]*title="/.test(h), "the full context must be on hover");

  /* the 112-char instruction is in the BOX, not bold above it */
  assert(!new RegExp('shnewlabel">' + "If not a smoke test").test(h),
    "a 112-char instruction must not be a prominent label");
  assert(h.indexOf('placeholder="If not a smoke test') !== -1,
    "it must become the placeholder of the field it instructs");
  assert(h.indexOf('aria-label="If not a smoke test') !== -1,
    "and stay the field's accessible name");
  assert(/data-shivkey="real_objective"/.test(h), "the key is untouched");

  /* a boolean keeps its label -- a chip has no box to move into */
  assert(/shnewlabel">This was a smoke test/.test(h),
    "a chip field's label must never move");
  assert(/shivreq/.test(h), "and required stays attached to it");
  console.log("ok 8f context clamped, long instruction moved into its box");
}

/* ── 8g. THE DECISION, NOT THE NARRATION ───────────────────────
   VERBATIM from the README sign-off on the live dogfood (founder,
   2026-09-15). The decider wrote one proposition three times -- as the
   question, as the field label and as the done_when check -- and added a
   paragraph of its own reasoning on top. The founder has to decide, not
   audit, so the card shows the question, the control and the criterion. */
const Q_README = "Does the new Shadow task-pane README section meet the bar "
  + "— clear overview, setup/test instructions, and a short troubleshooting "
  + "section?";
const L_README = "README has a clear overview, setup/test instructions, and "
  + "a short troubleshooting section.";
const C_README = "README includes a clear overview, setup/test instructions, "
  + "and a short troubleshooting section.";
const CTX_README = "The delegate added a ## Shadow: the task pane section to "
  + "the README covering what the pane is, how to run it, and what to do "
  + "when it will not start. I cannot judge whether that clears your bar "
  + "for a founder-facing doc, so this is yours to sign off.";
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "blocked",
    done_when: [{ tier: "founder_confirm", check: C_README }],
    intervention: { id: "iv-r", question: Q_README, context: CTX_README,
      evidence: [], submit_label: "Send to Shadow",
      confirms_check: { index: 0, field: "readme_ok" },
      fields: [{ key: "readme_ok", type: "boolean", required: true,
                 label: L_README }] } }));

  /* PRIMARY: the question and the criterion, both in full */
  assert(h.indexOf(Q_README) !== -1, "the question is primary and unedited");
  assert(h.indexOf("“" + C_README + "”") !== -1,
    "the sign-off criterion is primary and quoted verbatim");
  assert(/Yes signs off/.test(h), "and it still says what the Yes does");

  /* GONE: the label that was the same sentence a third time */
  assert(h.indexOf(L_README) === -1 || !new RegExp(
    'shnewlabel[^>]*>' + "README has a clear").test(h),
    "the echoed label must not be printed as a third copy");
  assert(!/shnewlabel">README has/.test(h),
    "the label is the question again -- it must not be drawn");
  /* ...but the control keeps its name for a screen reader */
  assert(/role="group" aria-label="README has/.test(h),
    "the suppressed label must survive as the control's accessible name");

  /* GONE: Shadow's reasoning as a paragraph, on a sign-off */
  assert(!/shivctx/.test(h),
    "a sign-off card must not draw the decider's narration");
  assert(h.indexOf("The delegate added a") === -1
    || /class="shivq" title="The delegate added a/.test(h),
    "the context may only survive on the question's title");
  assert(/class="shivq" title="/.test(h),
    "and it must survive there -- the text is never lost");

  /* the decision itself is untouched */
  assert(/data-shivkey="readme_ok"/.test(h), "the field hook is unchanged");
  assert(/data-shivopt="yes"/.test(h) && /data-shivopt="no"/.test(h),
    "Yes and No still carry their values");
  assert(/data-shivsend="m-1"/.test(h), "the submit hook is unchanged");
  console.log("ok 8g a sign-off shows question + control + criterion, once each");
}

/* ── 8h. the test is conservative: only a NEAR DUPLICATE is hidden ──── */
{
  const ctx = fresh();
  const same = (line, said) => ctx.shadowAlreadySaid(line, said);
  assert.strictEqual(same(L_README, [Q_README, C_README]), true,
    "the live case is a duplicate");
  /* a SHORT question must never swallow a longer label that adds something */
  assert.strictEqual(same(
    "This was a smoke test and the round-trip is satisfactory — close it out.",
    ["Was this a smoke test?"]), false,
    "a short question must not swallow a label that adds a condition");
  assert.strictEqual(same("Default region", ["Which region?"]), false,
    "two words in common is not a duplicate");
  assert.strictEqual(same("Relevant tests pass.", ["Do the tests pass?"]), false,
    "'relevant' is a real qualifier and must survive");
  assert.strictEqual(same("", [Q_README]), false, "nothing is never redundant");
  assert.strictEqual(same(L_README, []), false,
    "with nothing said yet, nothing can be a repeat");
  console.log("ok 8h only a near duplicate is suppressed, never a qualifier");
}

/* ── 8i. DONE WHEN STANDS ASIDE WHEN THE ASK *IS* THE CHECKLIST ───────
   The live shape (founder, 2026-09-15): state `blocked`, block_reason
   "needs_founder", one unmet founder_confirm check, and an intervention
   whose boolean signs exactly that check. The brief printed the criterion
   and the ask printed it again, two blocks apart.

   shadowMissionNeedsFounder() does not fire here and MUST NOT be widened to
   -- it describes the PAUSED sign-off flow, where the checklist replaces the
   row. This is the narrower second reason, and it proves coverage per
   check. */
const askMission = (over, checks, fields) => M(Object.assign({
  state: "blocked", block_reason: "needs_founder",
  done_when: checks || [{ tier: "founder_confirm", check: C_README }],
  intervention: { id: "iv-r", question: Q_README, context: CTX_README,
    evidence: [], submit_label: "Send to Shadow",
    confirms_check: { index: 0, field: "readme_ok" },
    fields: fields || [{ key: "readme_ok", type: "boolean", required: true,
                         label: L_README }] },
}, over || {}));
{
  /* the screenshot, exactly */
  const h = pane(fresh(), askMission());
  assert(!/shcard2k">done when</.test(h),
    "DONE WHEN must stand aside when the ask signs off every unmet check");
  /* the criterion is still on screen -- ONCE, where it is being signed */
  assert.strictEqual(h.split(C_README).length - 1, 1,
    "the criterion must appear exactly once, in the sign-off row");
  assert(/Yes signs off/.test(h), "and it is the sign-off that carries it");
  assert(/shcard2k">where it runs</.test(h) && /shcard2k">turn</.test(h),
    "the rest of the brief is untouched");

  /* TWO unmet, the ask signs ONE -> the row stays, because it still says
     something the ask does not */
  const two = pane(fresh(), askMission(null, [
    { tier: "founder_confirm", check: C_README },
    { tier: "founder_confirm", check: "A CHANGELOG entry exists." }]));
  assert(/shcard2k">done when</.test(two),
    "an unmet check the ask does not cover must keep the row");
  assert(/A CHANGELOG entry exists/.test(two), "and must be readable in it");

  /* an unmet MACHINE-tier check is never the founder's to sign */
  const machine = pane(fresh(), askMission(null, [
    { tier: "founder_confirm", check: C_README },
    { tier: "contains_artifact", check: "The PR is open." }]));
  assert(/shcard2k">done when</.test(machine),
    "a machine-tier check the verifier owns must keep the row");

  /* an ordinary ask that confirms nothing changes nothing */
  const plain = pane(fresh(), askMission({ intervention: {
    id: "iv-p", question: "Which region?", evidence: [], fields: [
      { key: "region", type: "choice", label: "Region", options: [
        { value: "eu", label: "EU" }, { value: "us", label: "US" }] }] } }));
  assert(/shcard2k">done when</.test(plain),
    "an ask unrelated to completion must not hide the checklist");

  /* no intervention at all -> untouched */
  assert(/shcard2k">done when</.test(pane(fresh(),
    askMission({ intervention: null }))),
    "a card with no ask keeps its done-when row");

  /* a check already MET is not outstanding, so it cannot be 'covered' */
  assert(/shcard2k">done when</.test(pane(fresh(), askMission(null,
    [{ tier: "founder_confirm", check: C_README, met: true }]))),
    "with nothing unmet the row behaves exactly as it always did");
  console.log("ok 8i DONE WHEN hides only when the ask covers every unmet check");
}

/* ── 8j. THE PREVIEW SKIPS THE ANNOUNCEMENT AND KEEPS THE NEWS ───────
   The live pane read "WORKER AGENT · TURN 1 / What I did." -- real worker
   text, carrying nothing. The next real sentence of the SAME turn is used;
   nothing is generated, and an all-announcement turn draws nothing. */
{
  const ctx = fresh();
  const say = (text) => {
    const c = fresh();
    c.S.goalTranscript = { "sess-1": [{ role: "assistant", text }] };
    const h = pane(c, M({ turns_used: 1 }));
    return (h.match(/class="shagentsay"[^>]*>([^<]*)</) || [])[1] || "";
  };

  /* THE REGRESSION, in the founder's own example */
  assert.strictEqual(
    say("## What I did\n\nUpdated marketplace/plugin/sutra-ui/README.md "
        + "with setup and testing instructions."),
    "Updated marketplace/plugin/sutra-ui/README.md with setup and testing "
    + "instructions.",
    "the preview must be the news, not the heading above it");
  /* ...and the sentence must arrive WHOLE: the dot in README.md is not a
     sentence boundary, and the old splitter dropped everything before it */
  assert(say("## What I did\n\nUpdated README.md with setup instructions.")
    .indexOf("Updated README.md") === 0, "a filename must not split a sentence");

  assert.strictEqual(say("Done.\n\nAdded 14 tests and opened PR #212."),
    "Added 14 tests and opened PR #212.", "'Done.' is an announcement");

  /* a stop notice is NOT an announcement -- it is the whole report */
  assert.strictEqual(
    say("## Stopped — objective is not actionable\n\n| a | b |\n|---|---|"),
    "Stopped — objective is not actionable.",
    "a substantive heading must still win");

  /* an opener that carries its own news is kept whole, never re-cut */
  assert.strictEqual(
    say("What I did: updated the README with setup and testing instructions."),
    "What I did: updated the README with setup and testing instructions.",
    "an opener with three content words after it is not an announcement");
  assert.strictEqual(
    say("Summary: the migration removed 14 call sites and added 3 tests."),
    "Summary: the migration removed 14 call sites and added 3 tests.",
    "'Summary:' with real content is not an announcement");

  /* nothing but announcements -> no block at all, never a fabricated line */
  const none = fresh();
  none.S.goalTranscript = { "sess-1": [{ role: "assistant",
    text: "## What I did\n\nDone." }] };
  const h = pane(none, M({ turns_used: 1 }));
  assert(!/class="shagentsay"/.test(h),
    "an all-announcement turn must draw no line");
  assert(!/What I did|Done\./.test(h), "and must not print the announcement");

  /* the filler test itself, on its own */
  assert.strictEqual(ctx.shadowSayFiller("What I did."), true);
  assert.strictEqual(ctx.shadowSayFiller("Done."), true);
  assert.strictEqual(ctx.shadowSayFiller("Fourteen tests are green."), false);
  assert.strictEqual(ctx.shadowSayFiller("Stopped — objective is not "
    + "actionable."), false, "a stop notice is never filler");
  console.log("ok 8j the preview skips announcements and never invents one");
}

/* ── 8k. THE RIGHT PANE IS A TIMELINE, NOT A LATEST-STATUS ──────────
   (founder, 2026-09-15.) Turn 2 used to ERASE turn 1. A delegation is a
   sequence -- the worker works, Shadow reaches a boundary, the founder
   answers, the worker carries on -- and that sequence is the product.

   A TURN IS THE BACKEND'S TURN: session_reader counts turns as USER
   messages, so turn N opens at the Nth instruction Shadow injects and owns
   every assistant message until the next one. */
const W = (text, ts) => ({ role: "assistant", text: text, ts: ts || "" });
const SH = (ts) => ({ role: "user", text: "[Shadow · mission m-1] go on",
                      ts: ts || "" });
function timeline(ctx, msgs, over){
  ctx.S.goalTranscript = { "sess-1": msgs };
  const h = pane(ctx, M(Object.assign({ turns_used: 2 }, over || {})));
  return { h: h,
    rows: (h.match(/shagenthead">([^<]*)</g) || [])
      .map(x => (x.match(/>([^<]*)</) || [])[1]),
    says: (h.match(/class="shagentsay"[^>]*>([^<]*)</g) || [])
      .map(x => (x.match(/>([^<]*)</) || [])[1]) };
}

/* 1. TWO worker turns -> BOTH render, in order */
{
  const t = timeline(fresh(), [
    SH("2026-09-15T10:00:00Z"), W("Oriented in the repo.", "2026-09-15T10:01:00Z"),
    SH("2026-09-15T10:02:00Z"), W("Wrote the file.", "2026-09-15T10:03:00Z"),
  ]);
  assert.deepStrictEqual(t.rows,
    ["Worker agent · turn 1", "Worker agent · turn 2"],
    "turn 2 must not erase turn 1");
  assert.deepStrictEqual(t.says, ["Oriented in the repo.", "Wrote the file."],
    "both turns keep their own words, in order");
}

/* 2. THREE worker turns -> all three, no cap */
{
  const t = timeline(fresh(), [
    SH("2026-09-15T10:00:00Z"), W("One thing happened.", "2026-09-15T10:01:00Z"),
    SH("2026-09-15T10:02:00Z"), W("Two things happened.", "2026-09-15T10:03:00Z"),
    SH("2026-09-15T10:04:00Z"), W("Three things happened.", "2026-09-15T10:05:00Z"),
  ], { turns_used: 3 });
  assert.strictEqual(t.rows.length, 3, "no fixed cap on how many turns show");
  assert.deepStrictEqual(t.says,
    ["One thing happened.", "Two things happened.", "Three things happened."],
    "every meaningful turn keeps its place");
}

/* 2b. MORE THAN THREE -- there is no 2/3-turn cap anywhere. The count is
   whatever the transcript actually holds. */
{
  const msgs = [];
  for (let k = 1; k <= 7; k++){
    msgs.push(SH("2026-09-15T10:" + String(k * 2).padStart(2, "0") + ":00Z"));
    msgs.push(W("Step " + k + " is finished.",
                "2026-09-15T10:" + String(k * 2).padStart(2, "0") + ":30Z"));
  }
  const t = timeline(fresh(), msgs, { turns_used: 7 });
  assert.strictEqual(t.rows.length, 7,
    "seven turns must draw seven rows, got " + t.rows.length);
  assert.deepStrictEqual(t.rows.slice(0, 3),
    ["Worker agent \u00b7 turn 1", "Worker agent \u00b7 turn 2",
     "Worker agent \u00b7 turn 3"], "numbered from the first turn");
  assert.strictEqual(t.rows[6], "Worker agent \u00b7 turn 7",
    "and the last is turn 7, not a truncation");
  assert.strictEqual(t.says[0], "Step 1 is finished.", "turn 1 survives");
  assert.strictEqual(t.says[6], "Step 7 is finished.", "and so does turn 7");
  /* one line each: a timeline, not a transcript */
  assert.strictEqual((t.h.match(/class="shagentsay"/g) || []).length, 7,
    "one line per turn, seven lines");
  /* and no inner scroller was introduced to hold them */
  assert(!/shtimeline[^"]*"[^>]*style="[^"]*overflow/.test(t.h),
    "the pane stays the single scroll container");
}

/* 3. worker -> ANSWER -> worker, in the order it actually happened */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH("2026-09-15T10:00:00Z"), W("Oriented in the repo.", "2026-09-15T10:01:00Z"),
    SH("2026-09-15T10:04:00Z"), W("Carried on as told.", "2026-09-15T10:05:00Z"),
  ] };
  const h = pane(ctx, M({ turns_used: 2, founder_response: {
    intervention_id: "iv-1", question: "Ship it?",
    answered_at: "2026-09-15T10:03:00Z",
    summary: [{ key: "ok", label: "approved", value: "True" }] } }));
  const order = [];
  const re = /shagenthead">([^<]*)<|class="shstoryhead">([^<]*)</g;
  let x; while ((x = re.exec(h))) order.push(x[1] || x[2]);
  assert.strictEqual(order.length, 3, "three events, got " + order.join(" | "));
  assert(/turn 1/.test(order[0]), "turn 1 first");
  assert(/You answered/i.test(order[1]),
    "the answer sits BETWEEN the turns, where answered_at puts it");
  assert(/turn 2/.test(order[2]), "and the next turn follows it");
  /* and it is drawn ONCE -- the spine must not repeat it below */
  assert.strictEqual((h.match(/class="shstory"/g) || []).length, 1,
    "the answer card must not be duplicated");
  assert(/Ship it\?/.test(h), "the question you answered is the record's");
}

/* 4. generic and control-plane turns stay filtered, and do not take a row */
{
  const t = timeline(fresh(), [
    SH(), W("PLACEMENT: x\nDEPTH: 1/5\nTRIAGE: ok", "2026-09-15T10:01:00Z"),
    SH(), W("## What I did\n\nAdded the troubleshooting section.",
            "2026-09-15T10:03:00Z"),
  ]);
  assert.deepStrictEqual(t.rows, ["Worker agent · turn 2"],
    "a turn that said nothing readable takes no row");
  assert.deepStrictEqual(t.says, ["Added the troubleshooting section."],
    "and the announcement above the news is still skipped");
  assert(!/PLACEMENT|DEPTH:|TRIAGE:|What I did/.test(t.h),
    "no control plane and no announcement anywhere in the pane");
}

/* 4b. a turn ending in scaffolding falls back WITHIN its own turn */
{
  const t = timeline(fresh(), [
    SH(), W("Added the section.", "2026-09-15T10:01:00Z"),
    W("TRIAGE: depth_selected=2", "2026-09-15T10:01:30Z"),
  ], { turns_used: 1 });
  assert.deepStrictEqual(t.says, ["Added the section."],
    "a turn is not dropped for signing off with scaffolding");
}

/* 5. nothing is ever fabricated */
{
  const t = timeline(fresh(), [SH(), W("PLACEMENT: x\nTRIAGE: ok")]);
  assert.deepStrictEqual(t.rows, [], "an all-control mission draws no rows");
  assert(!/Working on it|Queued|Paused\.|shagentsay/.test(t.h),
    "and never a substituted phrase");
}

/* 7. a COMPLETED mission keeps its timeline */
{
  const t = timeline(fresh(), [
    SH("2026-09-15T10:00:00Z"), W("Oriented in the repo.", "2026-09-15T10:01:00Z"),
    SH("2026-09-15T10:02:00Z"), W("Shipped it.", "2026-09-15T10:03:00Z"),
  ], { state: "done", completion: { headline: "the fix ships",
       objective: "o", checks: [], turns_used: 2, max_turns: 20 } });
  assert.strictEqual(t.rows.length, 2, "a done mission keeps every turn");
  assert(/data-shdone="m-1"/.test(t.h), "and still draws its completion card");
  assert(/shtpill-done[^>]*>DONE</.test(t.h), "and still reads DONE");
}

/* 6/extra. DELETE is untouched by the timeline */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [SH(), W("Did the thing.")] };
  ctx.S.shadowMissions = [M({ turns_used: 1 })];
  ctx.S.shadowTaskSel = "m-1";
  const list = ctx.shadowTaskListHtml();
  assert(/data-shtaskdel="m-1"/.test(list), "the DELETE hook left the row");
  assert.strictEqual((ctx.shadowHomeHtml().match(/data-shtaskdel=/g) || []).length,
    1, "exactly one delete control, unmoved");
  console.log("ok 8k the timeline persists every meaningful turn, in order");
}

/* ── 8l. THE COMPLETION CARD IS A CONCLUSION, NOT AN AUDIT LOG ──────
   (founder, 2026-09-15.) `completion.outcome` is sliced off the head and
   tail of the evidence blob, so the live card carried file permissions, a
   grep invocation and a markdown table as its primary content -- and the
   real record's copy ends mid-sentence. The card refuses evidence; the
   working stays behind Open the chat and in Copy result. */
const EVIDENCE_OUTCOME = "**(1) Path and existing references** ``` -rw-r--r--@ "
  + "1 joytadanki staff 7474 Sep 15 10:17 marketplace/plugin/sutra-ui/"
  + "release-checklist.md ``` `grep -rn 'release-checklist' --exclude-dir=.git "
  + ".` returned four hits, **none of them a real reference to this file**: "
  + "| Hit | What it actually is | |---|---| | `marketplace/plugin/skills/"
  + "workflow-type-resolve/SKILL.md:203,205,206` | A worked example |";
const CRITERION = "release-checklist.md contains 5–7 concrete release "
  + "checks, explicitly states my chosen priority, and puts that priority first.";
const doneMission = (outcome) => M({ state: "done", target_session: "sess-1",
  turns_used: 6, max_turns: 20,
  done_when: [{ tier: "founder_confirm", check: CRITERION, met: true }],
  completion: { headline: "1 of 1 checks passed", objective: "Create a file "
    + "named release-checklist.md for the next Sutra release, and do not "
    + "finalize it until you ask me which risk I want prioritized.",
    outcome: outcome, turns_used: 6, max_turns: 20,
    checks: [{ check: CRITERION, met: true, how: "you confirmed it",
               by: "founder" }] } });
{
  const ctx = fresh();
  const m = doneMission(EVIDENCE_OUTCOME);
  const kept = m.completion.outcome;
  const h = pane(ctx, m);

  /* 1. THE DUMP IS GONE */
  const work = (h.match(/class="shdonework"[^>]*>([^<]*)</) || [])[1] || "";
  assert.strictEqual(work, "",
    "a pure-evidence outcome must draw no preview, got: " + work);
  for (const leak of ["-rw-r--r--", "grep -rn", "```", "SKILL.md:203",
                      "| Hit |", "7474"]){
    assert(h.indexOf(leak) === -1, "evidence on the card: " + leak);
  }
  /* the objective is not restated here either */
  assert(!/do not finalize it until you ask me/.test(h),
    "the objective must not be restated on the completion card");

  /* 2. DONE + the check count remain */
  assert(/shtpill-done[^>]*>DONE</.test(h), "the DONE pill must remain");
  assert(/Done — 1 of 1 checks passed/.test(h),
    "the headline and check count must remain");
  assert(/6 of 20 turns used/.test(h), "the turn cost stays");

  /* 3. the actual done-when criterion remains, with who satisfied it */
  assert(h.indexOf(CRITERION) !== -1, "the criterion must remain, verbatim");
  assert(/shcheckmet/.test(h), "and its met verdict");
  assert(/you confirmed it · founder/.test(h), "and who satisfied it");

  /* 4. Copy result remains, and still carries the FULL outcome */
  assert(/data-shcopydone="m-1"/.test(h), "Copy result must remain");
  assert(ctx.shadowCompletionText(m).indexOf(kept.slice(0, 60)) !== -1,
    "Copy result must still carry the untrimmed outcome");

  /* 5. Open the chat remains */
  assert(/data-shtakeover="sess-1"[^>]*>Open the chat</.test(h),
    "Open the chat must remain the way to the working");

  /* 6. DELETE is untouched */
  ctx.S.shadowMissions = [m]; ctx.S.shadowTaskSel = m.id;
  assert(/data-shtaskdel="m-1"/.test(ctx.shadowTaskListHtml()),
    "the DELETE hook must be untouched");
  assert.strictEqual((h.match(/data-shtaskdel=/g) || []).length, 1,
    "exactly one delete control");

  /* 7. THE RECORD IS NOT MUTATED -- this is a render filter, nothing else */
  assert.strictEqual(m.completion.outcome, kept,
    "completion.outcome must be byte-identical after rendering");
  assert.strictEqual(m.completion.outcome.length, EVIDENCE_OUTCOME.length,
    "not one character of the stored outcome may be trimmed");
  console.log("ok 8l the completion card keeps the conclusion, drops the working");
}

/* ── 8m. a REAL sentence in the outcome is still shown ────────────── */
{
  const ctx = fresh();
  const h = pane(ctx, doneMission("The checklist now names release safety "
    + "first and all seven checks are concrete. Evidence: `grep -rn x` "
    + "returned four hits."));
  const work = (h.match(/class="shdonework"[^>]*>([^<]*)</) || [])[1] || "";
  assert.strictEqual(work,
    "The checklist now names release safety first and all seven checks are "
    + "concrete.", "a real conclusion is shown, got: " + work);
  /* the evidence sentence is not VISIBLE text IN THE PREVIEW; it may still
     ride on the title, which is how the untrimmed outcome stays reachable.

     SCOPED TO THE PREVIEW ON 2026-09-17, and the scope is the point. This
     assertion was card-wide when the card had exactly one place the outcome
     could appear -- the one-line .shdonework preview -- and the 2026-09-15
     ruling it encodes is about that line: a card whose PRIMARY content was
     a grep invocation and a permissions listing. The card now also carries a
     Summary block under the verdicts, whose whole purpose is the accepted
     result in full, and for a research task that result IS what the founder
     opened the pane to read. A conclusion followed by its own "Evidence:"
     sentence is the worker's answer, in the worker's order.

     So the preview still refuses it -- unchanged, asserted above and
     immediately below -- and the Summary no longer pretends the sentence was
     never written. What is NOT relaxed: shadowSummaryHtml still draws
     nothing at all when the outcome is pure working with no conclusion in
     it (8l), which is the case that ruling was actually about. */
  const beforeSummary = h.slice(0, h.indexOf('class="shdonesummary"') === -1
    ? h.length : h.indexOf('class="shdonesummary"'));
  assert(!/>[^<]*grep -rn x/.test(beforeSummary),
    "the evidence sentence must not be rendered in the preview");
  /* the untrimmed text is still reachable */
  assert(/shdonework[^>]*title="The checklist now names/.test(h),
    "the full outcome rides on the title");
  /* the evidence test itself */
  assert.strictEqual(ctx.shadowResultEvidence("Ran `grep -rn foo` twice."), true);
  assert.strictEqual(ctx.shadowResultEvidence("-rw-r--r--@ 1 joy staff"), true);
  assert.strictEqual(ctx.shadowResultEvidence("See SKILL.md:203 for it."), true);
  assert.strictEqual(ctx.shadowResultEvidence("(1) Path and references"), true);
  assert.strictEqual(ctx.shadowResultEvidence("All seven checks are concrete."),
    false, "ordinary prose is never evidence");
  console.log("ok 8m a real conclusion survives; the working beside it does not");
}

/* ── 8n. THE COMPOSER REACHES SHADOW, NOT THE WORKER ─────────────
   (founder, 2026-09-15; the destination changed 2026-09-17.) It first posted
   to /api/shadow/chat -- the chief-of-staff conversation, which holds no
   mission and cannot act on one. With a task in focus it then posted an aside
   to THAT task's record, which the decider read but which nothing answered.

   IT NOW POSTS TO THE TASK'S OWN SHADOW CHAT, because that route does both
   halves: it answers the founder AND records their words to `founder_says`,
   which is the same operational path the aside took. So the founder no longer
   has to decide whether a sentence is chat or instruction -- the one thing
   only Shadow can judge. Everything this lane pinned still holds: one POST,
   to the task in focus, carrying the founder's words and nothing else, never
   the worker session and never the chief-of-staff chat. */
function sayCtx(over){
  const ctx = fresh();
  ctx.posted = [];
  ctx.shadowPost = (path, body) => {
    ctx.posted.push({ path: path, body: body });
    return Promise.resolve(Object.assign(
      { ok: true, status: 200, json: () => Promise.resolve({ id: "m-1" }) },
      over || {}));
  };
  ctx.sendToShadow = (t) => { ctx.chatted = t; return Promise.resolve(null); };
  ctx.loadShadowHome = () => {};
  ctx.showNudge = (t) => { ctx.nudged = t; };
  return ctx;
}
const box = () => ({ value: "", dataset: { shhomecompose: "1" } });

/* 1/4/10. it goes to the MISSION action endpoint, never to the worker */
{
  const ctx = sayCtx();
  ctx.S.shadowMissions = [M({ state: "running" })];
  ctx.S.shadowTaskSel = "m-1";
  const el = box();
  el.value = "Prioritize release safety over code cleanliness.";
  ctx.typeAndSend(el);
  assert.strictEqual(ctx.posted.length, 1, "exactly one POST");
  assert.strictEqual(ctx.posted[0].path, "/api/shadow/tasks/m-1/chat",
    "it must go to the task in focus -- the route that answers AND records");
  assert.strictEqual(ctx.posted[0].body.message,
    "Prioritize release safety over code cleanliness.");
  assert.deepStrictEqual(Object.keys(ctx.posted[0].body), ["message"],
    "the founder's words and nothing else -- the frontend classifies nothing");
  /* NOT the worker, and NOT the chief-of-staff chat */
  assert.strictEqual(ctx.chatted, undefined,
    "with a task in focus it must not go to /api/shadow/chat");
  assert(ctx.posted[0].path.indexOf("sessions") === -1,
    "it must never address the worker session");
  /* 12. the box clears */
  assert.strictEqual(el.value, "", "the composer clears on send");
  console.log("ok 8n-1 the aside goes to Shadow, for this mission only");
}

/* 6. no intervention on screen is fine -- an aside is unsolicited */
{
  const ctx = sayCtx();
  ctx.S.shadowMissions = [M({ state: "running" })];   /* no intervention */
  ctx.S.shadowTaskSel = "m-1";
  const el = box(); el.value = "Keep going, but verify it.";
  ctx.typeAndSend(el);
  assert.strictEqual(ctx.posted.length, 1,
    "Say anything works with no question outstanding");
}

/* with NOTHING in focus the briefing composer is untouched */
{
  const ctx = sayCtx();
  ctx.S.shadowMissions = []; ctx.S.goals = [];
  const el = box(); el.value = "what should I take on?";
  ctx.typeAndSend(el);
  assert.strictEqual(ctx.posted.length, 0, "no mission POST");
  assert.strictEqual(ctx.chatted, "what should I take on?",
    "the chief-of-staff channel is unchanged when no task is selected");
}

/* 12. duplicate submission while a send is in flight */
{
  const ctx = sayCtx();
  ctx.S.shadowMissions = [M({ state: "running" })];
  ctx.S.shadowTaskSel = "m-1";
  ctx.shadowPost = (path, body) => {
    ctx.posted.push({ path: path, body: body });
    return new Promise(() => {});           /* never settles: still in flight */
  };
  const a = box(); a.value = "first";
  ctx.typeAndSend(a);
  const b = box(); b.value = "second";
  ctx.typeAndSend(b);
  assert.strictEqual(ctx.posted.length, 1,
    "a second send while one is in flight must not post again");
}

/* 12. an API failure must not swallow what was typed. The restore lands
   after the POST settles, so this one is asserted asynchronously -- and a
   failure inside a promise must still fail the run, hence the exitCode. */
const asyncChecks = [];
{
  const ctx = sayCtx({ ok: false, status: 500 });
  ctx.S.shadowMissions = [M({ state: "running" })];
  ctx.S.shadowTaskSel = "m-1";
  const el = box(); el.value = "don't touch that file";
  /* the send's own promise, so the assertion cannot race the restore */
  const typed = el.value;
  el.value = "";                       /* the composer clears optimistically */
  ctx.shadowTalk().text = typed;
  asyncChecks.push(ctx.shadowTalkSend("m-1", el).then(() => {
    assert.strictEqual(el.value, "don't touch that file",
      "the text must come back when the send fails");
    /* the panel that used to carry this message is gone; the refusal now
       lands on the composer's own error line, which shadowStageHtml draws */
    assert(/still in the box/.test(ctx.S.shadowScopeErr || ""),
      "and the founder is told, rather than left guessing");
    console.log("ok 8n-4 a failed send hands the text back");
  }));
}

/* 2/3/7. the asides are timeline events, chronological, and they persist:
   they are read off the RECORD, so a refresh redraws them */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [
    SH("2026-09-15T10:00:00Z"), W("Inspected the repo.", "2026-09-15T10:01:00Z"),
    SH("2026-09-15T10:04:00Z"), W("Wrote the module.", "2026-09-15T10:05:00Z"),
    SH("2026-09-15T10:08:00Z"), W("Added the tests.", "2026-09-15T10:09:00Z"),
  ] };
  const h = pane(ctx, M({ state: "running", turns_used: 3, founder_says: [
    { text: "Prioritize release safety.", at: "2026-09-15T10:03:00Z" },
    { text: "Use the existing implementation.", at: "2026-09-15T10:07:00Z" },
  ] }));
  const order = [];
  const re = /shagenthead">([^<]*)<|class="shsaidhead">([^<]*)<|class="shsaidtext">([^<]*)</g;
  let x; while ((x = re.exec(h))) order.push(x[1] || x[2] || x[3]);
  assert.deepStrictEqual(order, [
    "Worker agent \u00b7 turn 1",
    "You \u2192 Shadow", "Prioritize release safety.",
    "Worker agent \u00b7 turn 2",
    "You \u2192 Shadow", "Use the existing implementation.",
    "Worker agent \u00b7 turn 3",
  ], "worker -> aside -> worker -> aside -> worker, in order");
  /* 3. an aside must not replace worker history */
  assert(/Inspected the repo/.test(h) && /Wrote the module/.test(h)
      && /Added the tests/.test(h), "every worker turn survives");
  /* 11. nothing is put in Shadow's mouth */
  assert(!/Shadow understood|Shadow is considering|Working on it/.test(h),
    "no fabricated Shadow reply");
  console.log("ok 8n-2 asides are chronological events beside the worker turns");
}

/* 9. DELETE is untouched by any of this */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [M({ state: "running",
    founder_says: [{ text: "hi", at: "2026-09-15T10:00:00Z" }] })];
  ctx.S.shadowTaskSel = "m-1";
  assert(/data-shtaskdel="m-1"/.test(ctx.shadowTaskListHtml()),
    "the DELETE hook is untouched");
  assert.strictEqual(
    (ctx.shadowHomeHtml().match(/data-shtaskdel=/g) || []).length, 1,
    "exactly one delete control");
  console.log("ok 8n-3 Delete untouched by Say anything");
}

/* ── 8o. THE ASIDES MERGE INTO THE STREAM, THEY DO NOT FOLLOW IT ────
   THE BUG (founder, 2026-09-15). The founder spoke after turn 1 and the pane
   drew TURN 1 / TURN 2 / TURN 3 / YOU -> SHADOW. The sort existed; its
   FALLBACK defeated it -- a comparison where either side had no parseable
   stamp fell through to original index, and the asides are pushed after the
   worker loop, so one unstamped worker message dropped every aside to the
   end. The worker spine now always carries a stamp, so there is something
   real to sort against. */
const WU = (ts) => ({ role: "user", text: "[Shadow · mission m-1] go",
                      ts: ts || "" });
const WA = (t, ts) => ({ role: "assistant", text: t, ts: ts || "" });
function stream(msgs, says, turns){
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": msgs };
  const h = pane(ctx, M({ state: "running", turns_used: turns,
                          founder_says: says }));
  const out = [];
  const re = /shagenthead">([^<]*)<|class="shsaidtext">([^<]*)</g;
  let x; while ((x = re.exec(h))) out.push(x[1] || ("YOU: " + x[2]));
  return { rows: out, h: h };
}

/* A. turn 1 -> aside -> turn 2, exactly the founder's sequence */
{
  const t = stream([
    WU("2026-09-15T10:00:00Z"), WA("Inspected the repo.", "2026-09-15T10:01:00Z"),
    WU("2026-09-15T10:02:30Z"), WA("Wrote the module.", "2026-09-15T10:03:00Z"),
  ], [{ text: "Prioritize release safety.", at: "2026-09-15T10:02:00Z" }], 2);
  assert.deepStrictEqual(t.rows, ["Worker agent \u00b7 turn 1",
    "YOU: Prioritize release safety.", "Worker agent \u00b7 turn 2"],
    "the aside belongs between the turns it happened between");
}

/* A-hard. THE REGRESSION ITSELF: assistant messages with NO stamp. This is
   the shape that defeated the old fallback. */
{
  const t = stream([
    WU("2026-09-15T10:00:00Z"), WA("Inspected the repo."),
    WU("2026-09-15T10:02:30Z"), WA("Wrote the module."),
    WU("2026-09-15T10:04:30Z"), WA("Added the tests."),
  ], [{ text: "Prioritize release safety.", at: "2026-09-15T10:02:00Z" }], 3);
  assert.deepStrictEqual(t.rows, ["Worker agent \u00b7 turn 1",
    "YOU: Prioritize release safety.", "Worker agent \u00b7 turn 2",
    "Worker agent \u00b7 turn 3"],
    "an unstamped worker message must not push the aside to the end");
}

/* B. an aside sent AFTER the last turn stays last */
{
  const t = stream([
    WU("2026-09-15T10:00:00Z"), WA("One.", "2026-09-15T10:01:00Z"),
    WU("2026-09-15T10:02:00Z"), WA("Two.", "2026-09-15T10:03:00Z"),
  ], [{ text: "That's good, leave it.", at: "2026-09-15T10:09:00Z" }], 2);
  assert.deepStrictEqual(t.rows, ["Worker agent \u00b7 turn 1",
    "Worker agent \u00b7 turn 2", "YOU: That's good, leave it."],
    "an aside after the last turn must not be pulled forward");
}

/* C. several asides interleave, each in its own place */
{
  const t = stream([
    WU("2026-09-15T10:00:00Z"), WA("One.", "2026-09-15T10:01:00Z"),
    WU("2026-09-15T10:04:00Z"), WA("Two.", "2026-09-15T10:05:00Z"),
    WU("2026-09-15T10:08:00Z"), WA("Three.", "2026-09-15T10:09:00Z"),
  ], [{ text: "a1", at: "2026-09-15T10:02:00Z" },
      { text: "a2", at: "2026-09-15T10:06:00Z" },
      { text: "a3", at: "2026-09-15T10:07:00Z" }], 3);
  assert.deepStrictEqual(t.rows, ["Worker agent \u00b7 turn 1", "YOU: a1",
    "Worker agent \u00b7 turn 2", "YOU: a2", "YOU: a3",
    "Worker agent \u00b7 turn 3"], "every aside lands where it happened");
}

/* D. an aside is never pulled to the front merely for living in its own
   array -- one sent after turn 2 must not precede turn 1 */
{
  const t = stream([
    WU("2026-09-15T10:00:00Z"), WA("One.", "2026-09-15T10:01:00Z"),
    WU("2026-09-15T10:02:00Z"), WA("Two.", "2026-09-15T10:03:00Z"),
  ], [{ text: "later", at: "2026-09-15T10:04:00Z" }], 2);
  assert.strictEqual(t.rows[0], "Worker agent \u00b7 turn 1",
    "a worker turn opens the stream, never a separately-stored aside");
}

/* E. numbering is the record's, and inserting asides does not renumber */
{
  const t = stream([
    WU("2026-09-15T10:00:00Z"), WA("One.", "2026-09-15T10:01:00Z"),
    WU("2026-09-15T10:04:00Z"), WA("Two.", "2026-09-15T10:05:00Z"),
  ], [{ text: "mid", at: "2026-09-15T10:02:00Z" }], 2);
  assert(/turn 1$/.test(t.rows[0]) && /turn 2$/.test(t.rows[2]),
    "turns stay 1 and 2 with an aside between them");
  assert(!/turn 3/.test(t.h), "no turn is invented by the insertion");
}

/* F. nothing is put in Shadow's mouth */
{
  const t = stream([WU("2026-09-15T10:00:00Z"),
                    WA("One.", "2026-09-15T10:01:00Z")],
    [{ text: "do X instead", at: "2026-09-15T10:02:00Z" }], 1);
  assert(/YOU \u2192 Shadow/.test(t.h) || /shsaidhead/.test(t.h),
    "the aside is labelled as the founder's");
  assert(!/Shadow understood|Shadow is considering|Working on it/.test(t.h),
    "no fabricated Shadow reply");
}

/* G + H. Delete and the intervention surface are untouched by all of this */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "sess-1": [WU("2026-09-15T10:00:00Z"),
                                      WA("One.", "2026-09-15T10:01:00Z")] };
  const h = pane(ctx, M({ state: "blocked", turns_used: 1,
    founder_says: [{ text: "context for you", at: "2026-09-15T10:02:00Z" }],
    intervention: { id: "iv-1", question: "Ship it?", evidence: [],
      submit_label: "Send to Shadow",
      fields: [{ key: "ok", type: "boolean", label: "Ship it" }] } }));
  assert(/data-shivform="iv-1"/.test(h), "the ask still renders");
  assert(/data-shivsend="m-1"/.test(h), "with its submit hook");
  assert(/shtpill-blocked[^>]*>NEEDS YOU</.test(h), "and still reads NEEDS YOU");
  assert(/class="shsaidtext">context for you</.test(h),
    "the aside renders beside it, not instead of it");
  ctx.S.shadowMissions = [M({ state: "blocked" })];
  ctx.S.shadowTaskSel = "m-1";
  assert(/data-shtaskdel="m-1"/.test(ctx.shadowTaskListHtml()),
    "the DELETE hook is untouched");
  assert.strictEqual((h.match(/data-shtaskdel=/g) || []).length, 1,
    "exactly one delete control");
  console.log("ok 8o asides merge into the stream by stamp, never appended");
}

/* ── 8p. THE NEW-TASK COMPOSER IS NOT ON THE WORKSPACE ──────────── */
{
  const ctx = fresh();
  const h = pane(ctx, M({ state: "running" }));
  assert(!/What should I take on/.test(h),
    "the new-task ask must not draw under an active task");
  assert(!/Tell Shadow the outcome you want/.test(h),
    "nor its subtitle");
  /* ONE BOX, AND IT IS NAMED FOR THE WHOLE INTERACTION (founder,
     2026-09-17). It was "Say anything", then "Give instruction to Shadow"
     beside a Talk to Shadow panel -- two doors, and the founder had to pick.
     The panel is gone and this box talks to Shadow; the count below still
     pins that there is exactly one of it. */
  assert(/placeholder="Talk to Shadow…"/.test(h),
    "the active task keeps exactly one composer");
  assert.strictEqual((h.match(/data-shhomecompose/g) || []).length, 1,
    "exactly one composer on the page");
  /* ...AND THE FORM ASKS ON ITS OWN (founder, 2026-09-15, second pass).
     The ask block and the stage composer used to draw UNDER the open New
     Task panel -- a second outcome box beneath a form whose first field is
     already "The outcome you want". The panel is self-contained, so the
     stage is not rendered behind it at all. */
  const ctx2 = fresh();
  ctx2.S.shadowMissions = [M({ state: "running" })];
  ctx2.S.shadowTaskSel = "m-1";
  ctx2.S.shadowNewOpen = true;
  /* v4: the form is the opt-in path (flags.shadow_form) */
  ctx2.SETTINGS = { flags: { shadow_form: true } };
  const nt = ctx2.shadowHomeHtml();
  assert(!/What should I take on/.test(nt),
    "the ask heading still draws behind the New Task form");
  assert(!/Tell Shadow the outcome you want/.test(nt),
    "the ask subtitle still draws behind the New Task form");
  assert(!/Tell Shadow what outcome you want/.test(nt),
    "the stage placeholder still draws behind the New Task form");
  assert.strictEqual((nt.match(/data-shhomecompose/g) || []).length, 0,
    "no stage composer behind the New Task form");
  /* the form itself is the one that asks, and is untouched */
  assert(/data-shnewpanel="1"/.test(nt), "the New Task panel was lost");
  assert(/What should Shadow get done\?/.test(nt),
    "the panel's own heading was lost");
  assert(/data-shnewobj="1"/.test(nt), "the outcome field was lost");
  /* CLOSED, the workspace is byte-identical -- re-asserted here because this
     file owns the task-pane view of the same rule */
  const ctx3 = fresh();
  ctx3.S.shadowMissions = [M({ state: "running" })];
  ctx3.S.shadowTaskSel = "m-1";
  const closed = ctx3.shadowHomeHtml();
  assert.strictEqual((closed.match(/data-shhomecompose/g) || []).length, 1,
    "closing the form must restore exactly one composer");
  assert(/placeholder="Talk to Shadow…"/.test(closed),
    "and it is the calm one, unchanged");
  console.log("ok 8p one composer on the workspace; none behind New Task");
}

/* ── 9. MEMORY: the existing confirm, in the founder's flow ───────────── */
{
  const ctx = fresh();
  ctx.S.sessions = [{ id: "sess-1", title: "paisa" }];
  const h = pane(ctx, M(), { shadowMemory: [
    { id: "i-1", text: "run the EMI check before commits", confirmed: false,
      scope: "chat", scope_id: "sess-1", precedence: "project" },
    { id: "i-2", text: "already agreed", confirmed: true, scope: "chat",
      scope_id: "sess-1", precedence: "project" },
    { id: "i-3", text: "struck out", confirmed: false, revoked_at: "x",
      scope: "chat", scope_id: "sess-1", precedence: "project" },
  ] });
  assert(/class="shremember"/.test(h), "the remember capsule is missing");
  assert(/data-shconfirm="i-1"/.test(h),
    "it must reuse the EXISTING confirm hook, not a new one");
  assert(/I’ll remember: run the EMI check before commits/.test(h),
    "the instruction text comes from the memory record");
  assert(/shrememberk">paisa</.test(h), "the scope names the chat it is for");
  assert(!/data-shconfirm="i-2"/.test(h),
    "a confirmed instruction is not asking for anything");
  assert(!/data-shconfirm="i-3"/.test(h), "a revoked instruction is not either");
  console.log("ok 9 memory: unconfirmed only, through the existing confirm");
}

/* ── 10. SAY ANYTHING is the SHADOW<->FOUNDER channel, UI only ────────── */
{
  const ctx = fresh();
  const h = pane(ctx, M());
  assert(/class="shstage shstage-calm"/.test(h), "the calm composer is missing");
  assert(/placeholder="Talk to Shadow…"/.test(h),
    "the reference's placeholder is missing");
  /* the SAME surface and the SAME hooks it always had -- nothing new is wired */
  assert(/data-shhomecompose="1"/.test(h), "the composer hook changed");
  assert(/data-shscope=/.test(h), "the composer lost its scope attribute");
  assert(/data-shsend="1"/.test(h), "the send hook changed");
  /* and it is not the worker chat, nor a second delegation surface */
  assert(!/data-shtakeover/.test(h.slice(h.indexOf("shstage-calm"))),
    "the composer must not reach the worker chat");
  console.log("ok 10 say anything: existing composer, existing hooks");
}

/* ── 11. THE ACTIONS THE PANE MUST NEVER LOSE ────────────────────────── */
{
  const ctx = fresh();
  /* STOP IS A BUTTON ON THIS CARD AGAIN; RESUME IS NOT (founder,
     2026-09-16).

     The note this replaces removed both on 2026-09-15 -- "this pane reports
     and asks; it is not a worker control panel" -- and reassured that
     "shadowPlaneHtml still draws both". It does, on the WATCHING screen:
     SCREENS.shadowwatching renders shadowPlaneHtml, SCREENS.shadow renders
     this pane. Rendering one mission per state through SCREENS.shadow gave
     actions=[] for running, paused and blocked -- a founder watching a live
     worker had no way to stop it without changing screens, and the report
     ("only RUNNING and Open the chat") is exactly that.

     Only Stop moves. Resume stays off this pane: a NEEDS YOU task is
     answered by its intervention form, and the plane still offers Resume --
     both assertions below are unchanged. */
  const stop = pane(ctx, M({ state: "running" }));
  assert(/data-shact="stop"/.test(stop),
    "a running task must offer Stop on the pane the workspace renders");
  const blocked = pane(fresh(), M({ state: "blocked" }));
  assert(/data-shact="stop"/.test(blocked), "…and so must a blocked one");
  assert(!/data-shact="resume"/.test(blocked), "the Resume button must be gone");
  const finished = pane(fresh(), M({ state: "done" }));
  assert(!/data-shact="stop"/.test(finished),
    "a completed task must never be offered Stop");
  /* ...and the actions themselves still exist, on their own surface */
  const plane = fresh().shadowPlaneHtml([], [M({ state: "running" })], "working");
  assert(/data-shact="stop" data-shmid="m-1"/.test(plane),
    "Stop must still render on the plane that owns mission actions");
  const paused = fresh().shadowPlaneHtml([], [M({ state: "paused" })], "working");
  assert(/data-shact="resume"/.test(paused), "Resume must still render there");
  const failed = pane(fresh(), M({ state: "failed" }));
  assert(/data-shact="retry" data-shmid="m-1"/.test(failed), "Retry was lost");
  const stopped = pane(fresh(), M({ state: "stopped" }));
  assert(/data-shact="retry"/.test(stopped), "Retry was lost for stopped");
  const ready = pane(fresh(), M({ state: "brief_confirm",
    target_session: null, start_requested_at: null }));
  assert(/data-shstart="m-1"/.test(ready), "Start was lost");
  const queued = pane(fresh(), M({ state: "queued" }));
  assert(/data-shact="drop"/.test(queued), "Drop was lost");
  console.log("ok 11 Stop/Resume off the card, actions intact; Retry/Start/Drop stay");
}

/* ── 12. DELETE IS UNTOUCHED BY THE RHS REDESIGN ──────────────────────
   It lives on the LIST row, it is the only control that erases anything, and
   nothing in this pass may have moved, renamed or duplicated it. */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [M()];
  ctx.S.shadowTaskSel = "m-1";
  const list = ctx.shadowTaskListHtml();
  assert(/data-shtaskdel="m-1"/.test(list), "the DELETE hook left the row");
  assert(/aria-label="Delete task"/.test(list), "the DELETE label changed");
  assert.strictEqual(typeof ctx.shadowDeleteTask, "function",
    "shadowDeleteTask must still exist");
  /* and the right pane must not have grown a second one */
  const h = ctx.shadowHomeHtml();
  const dels = (h.match(/data-shtaskdel=/g) || []).length;
  assert.strictEqual(dels, 1,
    "exactly one delete control, on the list row, where it has always been");
  console.log("ok 12 DELETE: one control, unmoved, unrenamed");
}

/* ── 13. the terminal faces still draw their own surfaces ────────────── */
{
  const done = pane(fresh(), M({ state: "done", completion: {
    headline: "the fix ships", objective: "EMI auto-fix",
    checks: [{ check: "a tested PR is open", met: true }],
    turns_used: 5, max_turns: 20 } }));
  assert(/data-shdone="m-1"/.test(done), "the completion summary was lost");
  assert(/shtpill-done[^>]*>DONE</.test(done), "DONE lost its pill");
  const stopped = pane(fresh(), M({ state: "stopped" }));
  assert(/shtpill-stopped[^>]*>STOPPED</.test(stopped), "STOPPED lost its pill");
  const failed = pane(fresh(), M({ state: "failed" }));
  assert(/shtpill-failed[^>]*>FAILED</.test(failed), "FAILED lost its pill");
  console.log("ok 13 DONE / STOPPED / FAILED still render their own surfaces");
}

/* ── 14. the founder sign-off checklist and the floors line survive ───── */
{
  const h = pane(fresh(), M({ state: "paused", pause_reason: "founder_confirm",
    done_when: [{ check: "the PR is open", tier: "founder_confirm" }] }),
    { shadowSettings: { floors: ["destructive git operations"] } });
  assert(/class="shconfirm"/.test(h), "the sign-off checklist was lost");
  assert(/the PR is open/.test(h), "the check text was lost");
  /* the floors line came off the brief; the floors themselves did not move */
  assert(!/destructive git operations/.test(h),
    "floors are configuration, not a row under every task");
  assert(/shtpill-blocked[^>]*>NEEDS YOU</.test(h),
    "a founder pause still reads NEEDS YOU");
  /* ...including a FLOOR pause, which is the floor doing its job */
  assert(/shtpill-blocked[^>]*>NEEDS YOU</.test(pane(fresh(),
    M({ state: "paused", pause_reason: "floor_confirm" }))),
    "a floor still stops the mission and still reads NEEDS YOU");
  console.log("ok 14 sign-off checklist and NEEDS YOU survive; floors off the brief");
}

Promise.all(asyncChecks).then(() => {
  console.log("\nall shadow RHS tests passed");
}, (err) => {
  console.error(err && err.message ? err.message : err);
  process.exitCode = 1;
});
