#!/usr/bin/env node
/* test_shadow_rhs.js -- the right pane is SHADOW REPORTING, not the worker chat.
 *
 * THE DESIGN THIS PINS ("Shadow Design - Final", founder 2026-09-15). The RHS
 * reads top to bottom as one editorial column:
 *
 *     seal + title + status + Open the chat     who, and the way OUT to the
 *                                               delegate's real conversation
 *     the brief          WHERE IT RUNS / DONE WHEN / TURN
 *     the agent          ONE report of the latest turn -- never the transcript
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
      addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(src, ctx);
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

/* ── 4. THE AGENT: one report of the latest turn, never the transcript ── */
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
  assert(/14 tests green, PR #212 open/.test(h),
    "the agent block must carry the delegate's LATEST say");
  assert(/The agent · turn 10/.test(h),
    "the block names the turn it is reporting, from turns_used");
  /* it is a REPORT, not a dump: the earlier turns are not in the block */
  const block = h.slice(h.indexOf('class="shagent"'));
  const end = block.indexOf("</div>", block.indexOf("shagentsay"));
  assert(block.slice(0, end).indexOf("ran the suite, 9 green") === -1,
    "only the latest agent turn belongs here -- the rest is the chat");
  assert(block.slice(0, end).indexOf("carry on") === -1,
    "Shadow's own injected turns are not the agent reporting");
  console.log("ok 4 the agent block is the latest turn, not the transcript");
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

/* ── 8b. THE AGENT BLOCK IS A SUMMARY, NOT A CONSOLE ──────────────────
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
  /* the heading stays -- it is the block's whole point */
  assert(/class="shagent"/.test(h) && /The agent · turn 1/.test(h),
    "THE AGENT must remain visible");
  for (const word of ["PLACEMENT", "domain_ref", "ROUTE:", "OBJECTIVE:",
                      "FIT:", "DEPTH:", "EFFORT:", "COST:", "IMPACT:",
                      "TRIAGE:", "Joy Tadanki Charter"]){
    assert(h.indexOf(word) === -1,
      "control-plane material reached the founder: " + word);
  }
  /* a turn that was ALL control plane still says something true, briefly */
  const fallback = (h.match(/class="shagentsay">([^<]*)</) || [])[1] || "";
  assert.strictEqual(fallback, "Working on it.",
    "an all-control turn falls back to the mission's own state, in one line");
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
  const say = (h.match(/class="shagentsay">([^<]*)</) || [])[1] || "";
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
  assert(/placeholder="Say anything…"/.test(h),
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
  /* STOP AND RESUME ARE NOT BUTTONS ON THIS CARD (founder, 2026-09-15) --
     this pane reports and asks; it is not a worker control panel. The
     ACTIONS are untouched: same data-shact hooks, same shadowMissionAct,
     same endpoint, and shadowPlaneHtml still draws both. */
  const stop = pane(ctx, M({ state: "running" }));
  assert(!/data-shact="stop"/.test(stop), "the Stop button must be gone");
  const blocked = pane(fresh(), M({ state: "blocked" }));
  assert(!/data-shact="resume"/.test(blocked), "the Resume button must be gone");
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

console.log("\nall shadow RHS tests passed");
