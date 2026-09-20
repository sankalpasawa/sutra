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
  assert(h.indexOf("shdonehead") < h.indexOf("shdonesummary"));
  /* THE ORDER INVERTED 2026-09-21 and that is the change: the verdicts moved
     into a closed "Verification" fold, so the Summary -- the result -- now
     comes first and the machinery last. Both are still drawn. */
  assert(h.indexOf("shdonesummary") < h.indexOf("shchecks"));
  assert(h.indexOf("shdoneverif") < h.indexOf("shchecks"),
    "the rows are inside the fold");
  /* the content is unchanged */
  assert(/class="shconfirmq">Done</.test(h));
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

/* ══ 8. THE TOP TWO SECTIONS ARE PINNED; ONLY THE CONVERSATION SCROLLS ══
 *
 * THE PROBLEM (founder, 2026-09-18). `.pb` (#scBody) is the app's screen
 * scroller and it scrolled ALL of Shadow, so reading back through a long
 * delegation carried the objective and the brief card off the top -- the two
 * things that say WHAT is being worked and HOW it is judged were the first to
 * leave. On a twenty-turn task the founder scrolled a wall of turns with
 * nothing anchoring them.
 *
 * THE SHAPE. Three regions, in this order and this nesting:
 *
 *     .shwright                     (flex column, own height, overflow hidden)
 *       .shwhead      PINNED        the outcome
 *       .shcard2      PINNED        the brief card
 *       .shwscroll    SCROLLS       timeline + thread + memory
 *       .shiv         PINNED        the question, when there is one (block 10)
 *       .shstage      PINNED        the composer
 *
 * The composer being pinned is a DECISION: by the letter it is the founder's
 * half of the conversation and belongs in the scroller, but one that scrolls
 * away has to be hunted for before you can type -- the opposite of what
 * pinning the header was for.
 */
{
  const ctx = fresh();
  ctx.loadGoalTranscript = () => {};
  ctx.goalTranscriptHtml = () => "";
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  ctx.S.goalTranscript = { "sess-1": [
    { role: "user", text: "[Shadow · mission m-1] go",
      ts: "2026-09-18T04:00:00Z" },
    { role: "assistant", text: "Wrote it. REPORT: notes.txt written.",
      ts: "2026-09-18T04:00:20Z" }] };
  ctx.goalMessages = (sid) => ctx.S.goalTranscript[sid];
  const m = { id: "m-1", objective: "Create notes.txt", state: "running",
    target_session: "sess-1", turns_used: 1, max_turns: 12,
    done_when: [{ tier: "verify", check: "notes.txt has 10 lines",
                  met: false }] };
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = "m-1";
  const h = ctx.shadowHomeHtml();

  /* the scroller exists, once */
  assert.strictEqual((h.match(/class="shwscroll"/g) || []).length, 1,
    "exactly one scroll region");
  const iScroll = h.indexOf('class="shwscroll"');

  /* ORDER: the HEAD before it, so it cannot be inside it. The BRIEF CARD is
     inside it now (founder, 2026-09-20: "many scroll bars ... make it like a
     long interactive chat") -- it was the second pinned block, with a 32%
     cap and a scrollbar of its own, and it is the conversation's first
     message instead. What the 2026-09-18 pinning was protecting is the
     anchor, and the header still provides it: objective, state, and now the
     live turn count. */
  assert(h.indexOf('class="shwhead"') < iScroll, "the outcome is pinned above");
  assert(h.indexOf('class="shcard2') > iScroll,
    "the brief is the first message INSIDE the conversation");
  assert(h.indexOf('class="shcard2') < h.indexOf('class="shtimeline"'),
    "...and it is FIRST: the brief opens the thread it belongs to");
  assert(/class="shwturn"/.test(h),
    "the live turn count moved to the pinned header");

  /* the conversation is INSIDE it */
  assert(h.indexOf('class="shtimeline"') > iScroll,
    "the timeline scrolls inside");

  /* the composer is OUTSIDE it, and after */
  assert(h.indexOf('class="shstage') > h.indexOf('class="shtimeline"'),
    "the composer sits below the scroller, pinned");

  /* ── THE STYLESHEET HALF. Markup order alone pins nothing; every rule
        below is load-bearing and each has a specific failure mode. */
  const need = [
    [/\.shwork\{[^}]*height:100%/,
     ".shwork must take the pane's HEIGHT, not min-height -- min-height:100% "
     + "is what let .pb scroll the whole screen"],
    [/\.shwork\{[^}]*min-height:0/,
     ".shwork needs min-height:0 or an overflowing child pushes the column "
     + "open and the pinning silently does nothing"],
    [/\.shwright\{[^}]*min-height:0/, ".shwright needs min-height:0"],
    [/\.shwright\{[^}]*overflow:hidden/, ".shwright must clip"],
    [/\.shwscroll\{[^}]*overflow-y:auto/, ".shwscroll must scroll"],
    [/\.shwscroll\{[^}]*min-height:0/,
     ".shwscroll needs min-height:0 to be SHORTER than its content -- the "
     + "default auto refuses and the column grows instead"],
    [/\.shwright>\.shwhead[^{]*\{[^}]*flex:0 0 auto/,
     "the pinned children need flex-shrink:0 -- a flex item shrinks by "
     + "default, so a long objective would give up height and creep upward"],
    [/\.shwscroll>\.shcard2\{[^}]*overflow:visible/,
     "the brief must not keep a scrollbar of its own inside the scroller -- "
     + "a box that scrolls inside a box is the thing being removed"],
    [/\.shwscroll>\.shcard2\{[^}]*max-height:none/,
     "...nor a cap, which is what made it clip and need that scrollbar"],
  ];
  for (const [re, why] of need) assert(re.test(css), why);

  /* the left list gets its own scroll: the page no longer grows for it */
  assert(/\.shwleft>\.shtasks\{[^}]*overflow-y:auto/.test(css),
    "the task list scrolls on its own now");

  /* and .pb -- shared by every other screen -- is NOT touched */
  assert(!/\.shwork[^{]*\.pb|\.pb[^{]*\{[^}]*shwork/.test(css),
    "the fix must not reach into .pb, which every screen shares");
  pass("8: outcome pinned, brief opens the conversation, composer stays");
}

/* ══ 9. NEEDS YOU MUST NOT EAT THE CONVERSATION ═══════════════════════════
 *
 * THE BUG (founder, 2026-09-18, same day as block 8 above). Pinning the brief
 * card gave it flex:0 0 auto -- it could not give up a single pixel -- and
 * NEEDS YOU is the one state that GROWS it: shadowCheckRowsHtml puts the
 * sign-off list inside the card, taking it from 192px to 330px. .shwright
 * clips, so the height came out of the only child that could shrink: the
 * conversation. Measured in Chrome, one NEEDS YOU mission with four checks
 * and six turns on the record:
 *
 *     window   card    conversation   turns visible
 *     900px    330px      195px          3 of 6
 *     760px    330px       55px          1 of 6
 *     660px    330px        0px          0 of 6    <- Turn 1, Turn 2 and the
 *                                                     whole founder <-> Shadow
 *                                                     stream, gone
 *
 * THE FIX IS TWO RULES AND A HOOK:
 *   - the card SHRINKS and scrolls itself instead of never yielding
 *   - the conversation yields FIRST (weighted shrink) but never below a floor
 *   - the scroller carries the mission it was drawn for, so the renderer can
 *     keep the founder's place across the rebuild instead of resetting to
 *     Turn 1 every time the delegate speaks
 */
{
  /* THE CARD IS NO LONGER A COMPETITOR AT ALL (founder, 2026-09-20). The
     three rules that stood here -- shrinkable, self-scrolling, capped --
     were how a PINNED brief was stopped from starving the conversation.
     The brief is inside the conversation now, so it cannot take height from
     it by construction, and the cure went with the disease. What survives
     is the pair below: the question pinned under the scroller is still a
     competitor, and the scroller must still hold a floor against it. */
  const need = [
    [/\.shwscroll>\.shcard2\{[^}]*flex:none/,
     "the brief, inside the scroller, must size to its own content"],
    [/\.shwright>\.shwscroll\{[^}]*min-height:min\(/,
     "the conversation needs a FLOOR, expressed as a min() so the floor "
     + "itself cannot push the composer off a short pane"],
    [/\.shwright>\.shwscroll\{[^}]*flex:1 1000 auto/,
     "the conversation must absorb the squeeze BEFORE the card does -- "
     + "proportional shrink had the card scrolling on a roomy window"],
  ];
  for (const [re, why] of need) assert(re.test(css), why);
  /* the card must no longer be in the never-shrink list -- nor in any of
     .shwright's direct-child rules, since it is not a direct child now */
  const pinned = css.match(/\.shwright>\.shwhead[^{]*\{flex:0 0 auto\}/);
  assert(pinned, "the pinned rule still exists");
  assert(pinned[0].indexOf("shcard2") === -1,
    "the brief card must NOT be in the flex:0 0 auto list any more");
  assert(!/\.shwright>\.shcard2\{/.test(css),
    "the brief is not a direct child of the pane any more");

  /* THE HOOK. The scroller names the mission it is showing, so a rebuild can
     tell "same conversation, keep the founder's place" from "different task,
     open at the newest turn". */
  const ctx = fresh();
  ctx.loadGoalTranscript = () => {};
  ctx.goalTranscriptHtml = () => "";
  ctx.S.goalTranscript = { "sess-9": [
    { role: "user", text: "[Shadow · mission m-9] go", ts: "2026-09-18T04:00:00Z" },
    { role: "assistant", text: "REPORT: done.", ts: "2026-09-18T04:00:20Z" }] };
  ctx.goalMessages = (sid) => ctx.S.goalTranscript[sid];
  ctx.S.shadowMissions = [{ id: "m-9", objective: "Ship it", state: "paused",
    pause_reason: "founder_confirm", target_session: "sess-9",
    turns_used: 1, max_turns: 12,
    done_when: [{ tier: "founder_confirm", check: "it is live", met: false }] }];
  ctx.S.shadowTaskSel = "m-9";
  const h = ctx.shadowHomeHtml();
  assert(/class="shwscroll" data-shscroll="m-9"/.test(h),
    "the scroller carries the mission it is drawn for");
  /* the check rows ARE still on the card, wherever the card lives -- this
     block is about the conversation keeping its height, not about moving
     the sign-off list somewhere else */
  assert(h.indexOf('class="shconfirm"') !== -1, "NEEDS YOU still signs off");
  ctx.S.shadowNewOpen = true;
  assert(!/data-shscroll/.test(ctx.shadowHomeHtml()),
    "no mission is on screen behind the New Task panel, so no place to keep");

  /* THE RENDERER'S HALF IS BLOCK 10, and it RUNS the functions rather than
     matching their source text. What used to stand here was a regex pinning
     the exact expression `nsc.scrollTop = (same && !oscKeep.atEnd) ? ...`,
     which was the DEFECT: one write, around scBody.innerHTML, deciding from a
     measurement of an element the panes rebuild may already have detached. An
     assertion that pins a buggy line makes the bug load-bearing. */
  pass("9: NEEDS YOU cannot squeeze the conversation out of the pane");
}

/* ══ 11. THE CONVERSATION KEEPS THE FOUNDER'S PLACE ACROSS A REBUILD ══════
 *
 * FOUNDER, 2026-09-18: "when I am at the bottom of that scroll, sometimes it
 * goes to the top for no reason" -- and the other half of the same contract,
 * a mid-list position that must survive a rebuild untouched.
 *
 * `.shwscroll` is replaced on every render, so three functions in 06-render.js
 * carry the place across: _shScrollState() at the top of render(), before any
 * innerHTML has run; _restoreShScroll() at the bottom, after the rebuild and
 * after the focus restore; _shBindScroll(), whose listener is the only thing
 * that records whether the founder CHOSE to leave the tail.
 *
 * These are lifted whole and executed. The stub scroller CLAMPS scrollTop the
 * way a browser does -- capped at scrollHeight - clientHeight -- because the
 * clamp is where the bug lived: a list that does not overflow yet takes
 * `scrollTop = scrollHeight` and lands on ZERO, which is Turn 1.
 */
{
  const src = fs.readFileSync(
    path.join(__dirname, "static", "js", "06-render.js"), "utf8");
  const a = src.indexOf("const SH_PIN_SLOP = 24;");
  const b = src.indexOf("function _shBindScroll(){", a);
  assert(a !== -1 && b !== -1,
    "the Shadow scroll block must still exist in 06-render.js");
  const BLOCK = src.slice(a, src.indexOf("\n}\n", b) + 3);

  /* ...and the capture must still happen at the TOP of render(), above every
     innerHTML in it. This is the one structural claim left as text, because it
     is about WHERE the call sits, which running the functions cannot show. */
  const iCapture = src.indexOf("const priorSh = _shScrollState();");
  /* the STATEMENT, not the prose about it -- a comment upstream names this
     same line and indexOf would find that first */
  /* the statement moved INSIDE an `if` when the Shadow compose box became a
     mounted node (it is skipped while one is mounted), so its indent is no
     longer fixed. The semicolon is what distinguishes the statement from the
     comments that name it, not the leading whitespace. */
  const iPanes = src.indexOf("panesEl.innerHTML = panesHtml;");
  const iScreen = src.indexOf("scBody.innerHTML = html");
  const iRestore = src.indexOf("_restoreShScroll(priorSh);");
  const iFocus = src.indexOf("      el.focus();");
  assert(iCapture !== -1 && iCapture < iPanes && iCapture < iScreen,
    "the place is captured before BOTH rebuilds -- a reading taken after the "
    + "panes row is replaced is a reading of a detached element");
  assert(iRestore > iScreen && iRestore > iFocus,
    "and restored after the rebuild AND after el.focus(), which scrolls "
    + "ancestors to reveal the field");

  const scroller = (id, h, c) => {
    const el = { _t: 0, scrollHeight: h, clientHeight: c, __pinning: false,
      _on: null,
      getAttribute: (k) => (k === "data-shscroll" ? id : null),
      addEventListener: (ev, fn) => { if (ev === "scroll") el._on = fn; } };
    Object.defineProperty(el, "scrollTop", {
      get(){ return el._t; },
      set(v){ el._t = Math.max(0, Math.min(v, el.bottom()));
              if (el._on) el._on(); } });
    el.bottom = () => Math.max(0, el.scrollHeight - el.clientHeight);
    el.founderScrollsTo = (t) => { el._t = Math.max(0, Math.min(t, el.bottom()));
                                   if (el._on) el._on(); };
    return el;
  };
  const world = () => {
    const raf = [];
    const w = { live: null };
    const ctx = { console,
      document: { querySelector: (q) => (q === "[data-shscroll]" ? w.live : null) },
      requestAnimationFrame: (fn) => raf.push(fn) };
    vm.createContext(ctx);
    vm.runInContext(BLOCK, ctx);
    w.ctx = ctx;
    w.flush = () => raf.splice(0).forEach(fn => fn());
    w.put = (el) => (w.live = el);
    /* ONE RENDER: capture at the top, replace the element, restore at the
       tail -- the exact order render() calls them in. */
    w.rebuild = (next) => {
      const prior = ctx._shScrollState();
      w.put(next);
      ctx._restoreShScroll(prior);
      ctx._shBindScroll();
      w.flush();
      return next;
    };
    return w;
  };

  /* -- pinned at the bottom, new turns arriving ------------------------- */
  {
    const w = world();
    let el = w.put(scroller("m-1", 1200, 400));
    w.ctx._shBindScroll();
    el.scrollTop = el.bottom();                      /* watching the tail */
    for (const h of [1600, 2400, 5000]){
      el = w.rebuild(scroller("m-1", h, 400));
      assert.strictEqual(el.scrollTop, el.bottom(),
        "a founder at the tail is carried to the new bottom as turns land");
    }
    assert.strictEqual(el.scrollTop, 4600, "and that bottom is the real one");
  }

  /* -- an arbitrary mid-list position, left exactly where they put it --- */
  {
    const w = world();
    let el = w.put(scroller("m-1", 5000, 400));
    w.ctx._shBindScroll();
    el.founderScrollsTo(1234);                       /* reading turn 3 */
    for (const h of [5000, 5600, 6400]){
      el = w.rebuild(scroller("m-1", h, 400));
      assert.strictEqual(el.scrollTop, 1234,
        "new turns must not move a reader -- yanking someone to the tail "
        + "while they are reading is the worse failure of the two");
    }
  }

  /* -- a list whose height is still growing ------------------------------
     The pin writes `scrollTop = scrollHeight`, which CLAMPS. A rebuild that
     lands while the list has nothing in it yet therefore sits at 0, and this
     is the shape that produced "it goes to the top": it must not survive the
     next rebuild, and it must not be mistaken for the founder scrolling up. */
  {
    const w = world();
    let el = w.put(scroller("m-1", 900, 400));
    w.ctx._shBindScroll();
    el.scrollTop = el.bottom();
    /* the turns are momentarily gone: nothing to scroll at all */
    el = w.rebuild(scroller("m-1", 400, 400));
    assert.strictEqual(el.scrollTop, 0,
      "a list with nothing to scroll can only sit at 0 -- the clamp");
    /* they come back, taller than before */
    el = w.rebuild(scroller("m-1", 3000, 400));
    assert.strictEqual(el.scrollTop, el.bottom(),
      "THE BUG: the empty frame must not leave a pinned founder on Turn 1");

    /* and the same sequence for a founder who was READING mid-list */
    const w2 = world();
    let e2 = w2.put(scroller("m-2", 5000, 400));
    w2.ctx._shBindScroll();
    e2.founderScrollsTo(1234);
    e2 = w2.rebuild(scroller("m-2", 400, 400));      /* turns vanish */
    e2 = w2.rebuild(scroller("m-2", 5000, 400));     /* and return */
    assert.strictEqual(e2.scrollTop, 1234,
      "their place is REMEMBERED, not re-read off an empty list that reads 0");
  }

  /* -- the snapshot must survive the scroller being destroyed ------------
     `panesEl.innerHTML = panesHtml` runs before the screen's own rebuild, so
     the element the old code measured could already be detached. */
  {
    const w = world();
    const el = w.put(scroller("m-1", 3000, 400));
    w.ctx._shBindScroll();
    el.scrollTop = el.bottom();
    const prior = w.ctx._shScrollState();            /* taken while attached */
    w.put(null);                                     /* panes row replaced */
    assert.strictEqual(w.ctx._shScrollState(), null,
      "no scroller on screen means no state to keep");
    const after = w.put(scroller("m-1", 3000, 400));
    w.ctx._restoreShScroll(prior);
    assert.strictEqual(after.scrollTop, after.bottom(),
      "the founder is put back from a value read before the rebuild");
  }

  /* -- our own write is not a gesture ----------------------------------- */
  {
    const w = world();
    const el = w.put(scroller("m-1", 3000, 400));
    w.ctx._shBindScroll();
    w.ctx._restoreShScroll({ id: "m-1", top: 0, pinned: true });
    assert.strictEqual(el.scrollTop, el.bottom(), "pinned to the tail");
    assert.strictEqual(w.ctx._shScrollState().pinned, true,
      "and STILL pinned -- following the tail must not un-pin itself");
    w.flush();
    assert.strictEqual(el.__pinning, false, "the flag is released on the frame");
  }

  /* -- returning to the bottom resumes following ------------------------ */
  {
    const w = world();
    const el = w.put(scroller("m-1", 5000, 400));
    w.ctx._shBindScroll();
    el.founderScrollsTo(900);
    assert.strictEqual(w.ctx._shScrollState().pinned, false, "parked");
    el.founderScrollsTo(el.bottom());
    assert.strictEqual(w.ctx._shScrollState().pinned, true,
      "landing back at the bottom means 'show me the newest' again");
  }

  /* -- a different task opens at its newest turn ------------------------ */
  {
    const w = world();
    const a1 = w.put(scroller("m-1", 5000, 400));
    w.ctx._shBindScroll();
    a1.founderScrollsTo(1234);
    const prior = w.ctx._shScrollState();
    const b1 = w.put(scroller("m-2", 9000, 400));
    w.ctx._restoreShScroll(prior);
    w.flush();
    assert.strictEqual(b1.scrollTop, b1.bottom(),
      "another mission is not a position to keep");
    assert.strictEqual(w.ctx._shScrollState().pinned, true,
      "and it inherits no scrolled-up intent from the task before it");
  }
  pass("11: the conversation keeps the founder's place across a rebuild");
}

/* ══ 10. THE QUESTION IS PINNED; THE CONVERSATION KEEPS THE SCROLLER ═════
 *
 * THE BUG THAT SURVIVED BLOCK 9 (founder, 2026-09-18, second report). Block 9
 * gave the conversation a floor, but the intervention form was INSIDE the
 * scroller with it -- and the pane opens at the NEWEST row, which on a blocked
 * mission is the form. So the founder landed on the question with the turns
 * scrolled off above it. Measured in Chrome, six turns and a four-line
 * conversation on the record, scroller opened at its newest row:
 *
 *     window   turn rows visible   conversation lines visible
 *     660px           0                       0
 *     900px           0                       1
 *
 * THE FIX. The form leaves the scroller and is pinned between it and the
 * composer: always on screen, never taking the conversation's height with it.
 * It is capped and scrolls itself so a long question cannot starve the turns
 * the way the brief card did, and the card's own cap comes down so the
 * conversation is at least its equal (panel.css carries the measured table).
 */
{
  const ctx = fresh();
  ctx.loadGoalTranscript = () => {};
  ctx.goalTranscriptHtml = () => "";
  ctx.S.goalTranscript = { "sess-10": [
    { role: "user", text: "[Shadow \u00b7 mission m-10] go", ts: "2026-09-18T04:00:00Z" },
    { role: "assistant",
      text: "REPORT: the deploy is live and the smoke test passed.",
      ts: "2026-09-18T04:00:20Z" }] };
  ctx.goalMessages = (sid) => ctx.S.goalTranscript[sid];
  const m = { id: "m-10", objective: "Ship it", state: "paused",
    pause_reason: "founder_confirm", target_session: "sess-10",
    turns_used: 1, max_turns: 12,
    done_when: [{ tier: "founder_confirm", check: "it is live", met: false }],
    intervention: { id: "iv-10", question: "Is it live?",
      fields: [{ key: "ok", type: "boolean", label: "Signed off",
                 required: true }] } };
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = "m-10";
  const h = ctx.shadowHomeHtml();

  /* the form is still drawn, with the hook the submit handler reads */
  assert(/data-shivform="iv-10"/.test(h), "the question still renders");
  assert(/data-shivsend="m-10"/.test(h), "and it can still be sent");

  /* ...and it is OUTSIDE the scroller: after the timeline that is inside it,
     and after the element that closes it, but before the composer */
  const iScroll = h.indexOf('class="shwscroll"');
  const iTimeline = h.indexOf('class="shtimeline"');
  const iForm = h.indexOf('data-shivform');
  const iStage = h.indexOf('class="shstage');
  assert(iScroll !== -1 && iTimeline > iScroll, "the timeline is in the scroller");
  assert(iForm > iTimeline, "the question is drawn after the conversation");
  assert(iStage > iForm, "the composer is still last");
  /* the scroller's own closing tag sits between the two -- the form cannot be
     inside a region that has already closed */
  const closed = h.slice(iTimeline, iForm).indexOf("</div>") !== -1;
  assert(closed, "the scroller closes before the question is drawn");

  /* the stylesheet half: pinned, capped, scrolls itself */
  const need = [
    [/\.shwright>\.shiv\{[^}]*flex:0 1 auto/,
     "the pinned question must be able to yield height"],
    [/\.shwright>\.shiv\{[^}]*max-height:/,
     "a six-field question needs a cap or it starves the turns"],
    [/\.shwright>\.shiv\{[^}]*overflow-y:auto/,
     "a capped form must scroll, or Send becomes unreachable"],
    /* THE CARD'S CAP IS GONE, NOT LOWERED (founder, 2026-09-20): the brief
       moved inside the conversation, so there is no longer a third block
       bidding for the pane's height -- only the question below it, which is
       what the two rules above cap. The floor stays: it is what the
       question yields to. */
    [/\.shwright>\.shwscroll\{[^}]*min-height:min\(220px/,
     "the conversation's floor must hold against the pinned question"],
  ];
  for (const [re, why] of need) assert(re.test(css), why);
  /* .shwright>.shiv must come AFTER .shwright .shiv -- same specificity, so
     the earlier rule's margin-top would otherwise win */
  assert(css.indexOf(".shwright .shiv{") < css.indexOf(".shwright>.shiv{"),
    "the pinned rule must follow the one it overrides");

  /* NO OTHER STATE MOVES: a running mission carries no question, so the
     markup below the scroller is what it always was */
  const ctx2 = fresh();
  ctx2.loadGoalTranscript = () => {};
  ctx2.goalTranscriptHtml = () => "";
  ctx2.S.goalTranscript = ctx.S.goalTranscript;
  ctx2.goalMessages = (sid) => ctx2.S.goalTranscript[sid];
  ctx2.S.shadowMissions = [{ id: "m-10", objective: "Ship it", state: "running",
    target_session: "sess-10", turns_used: 1, max_turns: 12, done_when: [] }];
  ctx2.S.shadowTaskSel = "m-10";
  const h2 = ctx2.shadowHomeHtml();
  assert(h2.indexOf("data-shivform") === -1, "a running mission asks nothing");
  assert(h2.indexOf('class="shtimeline"') > h2.indexOf('class="shwscroll"'),
    "and its conversation is where it always was");
  pass("10: the question is pinned, the conversation keeps the scroller");
}

console.log("\nall shell + motion tests passed");
