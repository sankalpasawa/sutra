#!/usr/bin/env node
/* test_shadow_v4_talk.js -- ONE door to Shadow, and it answers.
 *
 * WHAT THIS LANE PINNED BEFORE, and why it changed. Step 1 (2026-09-16) added
 * a floating "Talk to Shadow" panel beside the workspace composer, so the
 * founder had two ways to reach Shadow: a box that deposited a line on the
 * record and never answered, and a popup that answered. Choosing between them
 * meant classifying your own sentence -- deciding whether "don't touch the API"
 * was chat or instruction -- which is the one judgement only Shadow can make.
 *
 * SO THERE IS ONE BOX (founder, 2026-09-17). The composer is named for what it
 * does, "Talk to Shadow", and posts to the route that already did both halves:
 * POST /api/shadow/tasks/{id}/chat returns Shadow's reply AND records the
 * founder's words to `founder_says`, which is what reaches the decider. The
 * popup, its button and its stylesheet are gone. The conversation is drawn in
 * the task stream, beside the worker turns it is about.
 *
 * NOTHING BACKEND MOVED FOR THIS. Every assertion here about what must NOT
 * happen -- no worker turn, no turn spent, no /act, a terminal task refusing --
 * is carried over from the panel's lane unchanged, because the path underneath
 * is the same one.
 *
 * Run: node test_shadow_v4_talk.js
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

function fresh(reply){
  const ctx = {
    console, Date,
    setTimeout: () => ({}), clearTimeout(){}, setInterval: () => ({}),
    scheduleRender(){},
    esc: (x) => String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"),
    SCREENS: {}, TITLES: {}, S: {},
    posted: [], fetched: [], nudged: "", chatted: null,
    listeners: {},
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
  ctx.showNudge = (t) => { ctx.nudged = t; };
  ctx.sendToShadow = async (t) => { ctx.chatted = t; };
  ctx.shadowPost = async (url, body) => {
    ctx.posted.push({ url: url, body: body });
    const r = (typeof reply === "function") ? reply(url, body) : reply;
    if (r && r.status && !r.ok) return { ok: false, status: r.status };
    return { ok: true, status: 200,
             json: async () => ({ mission: { id: "m-1" },
                                  reply: (r && r.reply) || "I am waiting on the worker." }) };
  };
  ctx.S.shadowHomeDark = false;
  ctx.S.goals = [];
  return ctx;
}

const M = (over) => Object.assign({
  id: "m-1", objective: "Ship the fix", template: "fix",
  target_mode: "new", target_session: "sess-1", target_chat: "c-1",
  task_chat_session: "shadow-1", task_chat: "c-2",
  state: "running", turns_used: 3, max_turns: 12,
  done_when: [{ check: "the tests pass", tier: "founder_confirm" }],
}, over);

function pane(ctx, m){
  ctx.S.shadowMissions = [m];
  ctx.S.shadowTaskSel = m.id;
  return ctx.shadowHomeHtml();
}
const enter = (ctx, dataset, value) =>
  (ctx.listeners.keydown || []).forEach(fn =>
    fn({ key: "Enter", shiftKey: false,
         target: { dataset: dataset, value: value },
         preventDefault(){}, stopPropagation(){} }));
const settle = () => new Promise(r => setImmediate(r));

let ok = 0;
const pass = (s) => console.log("ok " + (++ok) + " " + s);
const asyncChecks = [];

/* ══ 1/2/3. ONE FOUNDER INPUT, AND IT IS NAMED FOR WHAT IT DOES ══════════ */
{
  const ctx = fresh();
  const h = pane(ctx, M());
  assert(!/Give instruction to Shadow/.test(h),
    "the old composer wording must be gone");
  assert(/placeholder="Talk to Shadow…"/.test(h),
    "the one composer is labelled Talk to Shadow");
  assert.strictEqual((h.match(/data-shhomecompose/g) || []).length, 1,
    "exactly one founder input on the workspace");
  /* the popup, its button and its stylesheet */
  assert(!/data-shtalk=/.test(h), "the floating Talk to Shadow button is gone");
  assert(!/class="shtalk"/.test(h), "and so is the panel");
  assert(!/data-shtalkbox|data-shtalksend|data-shtalkclose/.test(h),
    "and every hook it owned");
  assert.strictEqual(css.indexOf(".shtalk{"), -1,
    "its stylesheet rules are gone too");
  /* the WORKER's door is untouched */
  assert(/data-shtakeover="sess-1"[^>]*>Open the chat/.test(h),
    "Open the chat -- the worker's own conversation -- is unchanged");
  assert.strictEqual((h.match(/data-shtakeover=/g) || []).length, 1,
    "exactly one door to the worker chat");
  pass("one founder input, named Talk to Shadow; the popup is gone");
}

/* ══ 4/5. A CONVERSATIONAL MESSAGE IS ANSWERED ══════════════════════════ */
{
  const ctx = fresh({ reply: "I am waiting on the worker's verification." });
  pane(ctx, M());
  enter(ctx, { shhomecompose: "1" }, "What are you waiting on?");
  asyncChecks.push(settle().then(() => {
    assert.strictEqual(ctx.posted.length, 1, "exactly one request");
    assert.strictEqual(ctx.posted[0].url, "/api/shadow/tasks/m-1/chat",
      "it goes to the task chat -- the route that answers, got " + ctx.posted[0].url);
    assert.strictEqual(ctx.posted[0].body.message, "What are you waiting on?");
    const h = pane(ctx, M());
    assert(/What are you waiting on\?/.test(h), "the founder's line is drawn");
    assert(/I am waiting on the worker&#x27;s verification\.|I am waiting on the worker's verification\./.test(h),
      "and Shadow's answer with it");
    assert(/shsaidhead">Shadow</.test(h), "attributed to Shadow");
    assert(/shsaidhead">You → Shadow</.test(h), "and to the founder");
    pass("a conversational message is answered, in the stream");
  }));
}

/* ══ 6/7. AN EXPLICIT INSTRUCTION TAKES THE SAME DOOR ═══════════════════ */
{
  const ctx = fresh({ reply: "Got it. I will keep the production config unchanged." });
  pane(ctx, M());
  enter(ctx, { shhomecompose: "1" }, "Don't modify the production config.");
  asyncChecks.push(settle().then(() => {
    assert.strictEqual(ctx.posted.length, 1,
      "an instruction is not a second kind of message");
    assert.strictEqual(ctx.posted[0].url, "/api/shadow/tasks/m-1/chat");
    assert.strictEqual(ctx.posted[0].body.message,
      "Don't modify the production config.");
    const h = pane(ctx, M());
    assert(/keep the production config unchanged/.test(h),
      "and it is answered like anything else");
    /* the frontend classified nothing: the payload is the founder's words */
    assert.strictEqual(Object.keys(ctx.posted[0].body).join(","), "message",
      "no kind, no type, no flag -- the frontend must not classify");
    pass("an explicit instruction takes the same door and is answered");
  }));
}

/* ══ 10. TALKING IS NOT ORCHESTRATION ══════════════════════════════════ */
{
  const ctx = fresh();
  pane(ctx, M());
  enter(ctx, { shhomecompose: "1" }, "Go ahead and fix the failing test.");
  asyncChecks.push(settle().then(() => {
    for (const p of ctx.posted){
      assert(!/\/act$/.test(p.url),
        "no message may take the mission-action path from here: " + p.url);
      assert(!/\/sessions\//.test(p.url),
        "and none may reach the worker session: " + p.url);
    }
    const m = ctx.S.shadowMissions[0];
    assert.strictEqual(m.turns_used, 3, "no worker turn is spent");
    assert.strictEqual(m.max_turns, 12, "nor the budget touched");
    assert.strictEqual(m.state, "running", "nor the state");
    pass("talking spends no worker turn and drives no worker directly");
  }));
}

/* ══ 12. THE CONVERSATION IS THE RECORD, NOT THE BROWSER ═══════════════
   A brand-new context has no live thread. Everything drawn comes from the
   task chat's own transcript, through the reader that already existed -- so
   a reload, and a restart that --resumes the same session, both redraw it. */
const TRANSCRIPT = [
  { role: "user", text: "[Shadow boot] Read your operating context, then answer READY.\n\nYou are Shadow." },
  { role: "assistant", text: "READY" },
  { role: "user", text: "Write the opening brief for this task's worker chat.\n\nFACTS\n- repo: x" },
  { role: "assistant", text: "```brief\nThe brief.\n```" },
  { role: "user", text: "You are Shadow, driving one target chat toward an outcome.\nOUTCOME\nShip the fix" },
  { role: "assistant", text: '```json\n{"action":"continue","instruction":"go"}\n```' },
  { role: "user", text: "What are you waiting on?", ts: "2026-09-17T10:01:00Z" },
  { role: "assistant", text: "Waiting on the worker's verification.", ts: "2026-09-17T10:01:20Z" },
];
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const h = pane(ctx, M());
  assert(/What are you waiting on\?/.test(h), "the founder's line returns");
  assert(/Waiting on the worker/.test(h), "and Shadow's answer");
  /* the orchestration that shares the same session never surfaces */
  const stream = h.slice(h.indexOf("shtimeline"));
  for (const hidden of ["[Shadow boot]", "READY", "Write the opening brief",
                        "driving one target chat", '"action"', "```brief"]){
    assert(stream.indexOf(hidden) === -1,
      "orchestration leaked into the founder's conversation: " + hidden);
  }
  assert(ctx.fetched.indexOf("shadow-1") !== -1,
    "read through the existing throttled transcript reader");
  pass("the conversation survives reload and restart, from the record");
}

/* ══ no line is drawn twice ════════════════════════════════════════════
   The route records the founder's words to `founder_says` AND they land in
   the transcript, so both sources carry them. */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": TRANSCRIPT };
  const h = pane(ctx, M({ founder_says: [
    { text: "What are you waiting on?", at: "2026-09-17T10:01:00Z", via: "talk" },
    { text: "An older aside, from the say path.", at: "2026-09-16T09:00:00Z" },
  ] }));
  assert.strictEqual((h.match(/What are you waiting on\?/g) || []).length, 1,
    "a line in both the transcript and founder_says is drawn once");
  assert(/An older aside, from the say path\./.test(h),
    "and a say with no transcript counterpart still has its place");
  pass("the two records of one line never double-draw");
}

/* ══ 13. THE WORKER'S TURNS ARE UNTOUCHED ══════════════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = {
    "sess-1": [
      { role: "user", text: "[Shadow · mission m-1] go", ts: "2026-09-17T10:00:00Z" },
      { role: "assistant", text: "REPORT: Created the file and verified it.",
        ts: "2026-09-17T10:00:30Z" },
    ],
    "shadow-1": TRANSCRIPT,
  };
  const h = pane(ctx, M({ turns_used: 1, turn_open: null }));
  assert(/Worker agent · turn 1/.test(h), "the worker turn heading is unchanged");
  assert(/Created the file and verified it\./.test(h),
    "and the REPORT line still selects exactly as before");
  assert(/class="shagentsay"/.test(h), "in the worker's own row shape");
  /* and the conversation sits in the same stream */
  assert(/class="shtimeline"/.test(h), "one stream");
  assert(/What are you waiting on\?/.test(h), "carrying the conversation too");
  pass("worker turns and REPORT selection render exactly as before");
}

/* ══ a finished task: the route refuses, and it is said in words ════════ */
{
  const ctx = fresh({ ok: false, status: 409 });
  pane(ctx, M({ state: "done" }));
  enter(ctx, { shhomecompose: "1" }, "still there?");
  asyncChecks.push(settle().then(() => {
    const h = pane(ctx, M({ state: "done" }));
    assert(/has finished/.test(h),
      "a 409 reaches the founder in words, got: " + h.slice(0, 160));
    pass("a terminal task refuses, and the founder is told");
  }));
}

/* ══ with NO task in focus the briefing composer is untouched ═══════════ */
{
  const ctx = fresh();
  ctx.S.shadowMissions = []; ctx.S.goals = [];
  ctx.shadowHomeHtml();
  enter(ctx, { shhomecompose: "1" }, "what should I take on?");
  asyncChecks.push(settle().then(() => {
    assert.strictEqual(ctx.posted.length, 0, "no task POST");
    assert.strictEqual(ctx.chatted, "what should I take on?",
      "the chief-of-staff channel is unchanged when nothing is selected");
    pass("with no task in focus the briefing composer is unchanged");
  }));
}

/* ══ REGRESSION: ONE TASK'S CONVERSATION NEVER REACHES ANOTHER ═════════
   (founder, 2026-09-17.) `S.shadowTalk.live` was one flat array shared by
   every mission. The floating panel hid that by accident -- it drew only
   when its `mid` matched the task on screen, and opening it elsewhere reset
   the array. Folding the panel into the workspace composer removed both
   guards, so a brand-new task opened already showing the previous task's
   conversation. These lanes pin the scoping, in both directions. */
{
  const ctx = fresh((url, body) => ({ reply: "Answer to: " + body.message }));
  const A_ = () => M({ id: "m-A", task_chat_session: "shadow-A",
                       target_session: "sess-A" });
  const B_ = () => M({ id: "m-B", task_chat_session: "shadow-B",
                       target_session: "sess-B" });
  asyncChecks.push((async () => {
    /* talk to A */
    pane(ctx, A_());
    enter(ctx, { shhomecompose: "1" }, "What are you waiting on?");
    await settle();
    const a1 = pane(ctx, A_());
    assert(/What are you waiting on\?/.test(a1), "A must show its own line");
    assert(/Answer to: What are you waiting on\?/.test(a1),
      "and Shadow's answer to it");

    /* open B -- a different mission, never spoken to */
    const b1 = pane(ctx, B_());
    assert(b1.indexOf("What are you waiting on?") === -1,
      "A's question leaked into B");
    assert(b1.indexOf("Answer to: What are you waiting on?") === -1,
      "A's answer leaked into B");
    assert.strictEqual((b1.match(/class="shsaid"/g) || []).length, 0,
      "a task nobody has talked to starts with an EMPTY conversation");

    /* talk to B */
    enter(ctx, { shhomecompose: "1" }, "Create shadow-f.txt");
    await settle();
    const b2 = pane(ctx, B_());
    assert(/Create shadow-f\.txt/.test(b2), "B must show its own line");
    assert(b2.indexOf("What are you waiting on?") === -1,
      "and still none of A's");

    /* ...and A did not gain B's */
    const a2 = pane(ctx, A_());
    assert(/What are you waiting on\?/.test(a2), "A keeps its own line");
    assert(a2.indexOf("Create shadow-f.txt") === -1,
      "B's line leaked backwards into A");

    /* RELOAD: a fresh context holds nothing, so both read from their own
       transcripts -- which is where the durable record always lived */
    const r = fresh();
    r.S.goalTranscript = {
      "shadow-A": [{ role: "user", text: "What are you waiting on?", ts: "2026-09-17T10:00:00Z" },
                   { role: "assistant", text: "Waiting on you.", ts: "2026-09-17T10:00:10Z" }],
      "shadow-B": [{ role: "user", text: "Create shadow-f.txt", ts: "2026-09-17T11:00:00Z" },
                   { role: "assistant", text: "On it.", ts: "2026-09-17T11:00:10Z" }],
    };
    const ra = pane(r, A_());
    assert(/Waiting on you\./.test(ra), "A redraws its own conversation");
    assert(ra.indexOf("Create shadow-f.txt") === -1, "and only its own");
    const rb = pane(r, B_());
    assert(/On it\./.test(rb), "B redraws its own conversation");
    assert(rb.indexOf("Waiting on you.") === -1, "and only its own");

    /* a task whose Shadow chat has not booted yet has nothing to show */
    const nb = pane(r, M({ id: "m-C", task_chat_session: null,
                           target_session: "sess-C" }));
    assert.strictEqual((nb.match(/class="shsaid"/g) || []).length, 0,
      "a task with no Shadow chat yet starts empty");
    pass("one task's conversation never reaches another, live or reloaded");
  })());
}
/* ══ INTERNAL MARKUP NEVER REACHES THE FOUNDER ═════════════════════════
   (founder, 2026-09-17.) Shadow answers in the same protocol the Now chat
   speaks -- ```chips and its five siblings. The floating panel this stream
   replaced ran every Shadow line through shadowProseHtml; the stream did
   not, and a bare "```chips" reached the founder. Both halves are pinned:
   the renderer sanitises, and the sanitiser handles a fence that never
   closes (which is how it leaked -- the closed-fence rule needs a ```). */
{
  const CHIPS_REPLY =
    "Two ways to go.\n\n1. Treat it as a question.\n2. Turn it into work." +
    "\n\n```chips";
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": [
    { role: "user", text: "What should we do?", ts: "2026-09-17T10:00:00Z" },
    { role: "assistant", text: CHIPS_REPLY, ts: "2026-09-17T10:00:10Z" },
  ] };
  const h = pane(ctx, M());
  const stream = h.slice(h.indexOf("shtimeline"));
  /* A. the markup is gone, in every form it could survive as */
  assert(stream.indexOf("```chips") === -1, "a bare ```chips reached the founder");
  assert(stream.indexOf("chips") === -1, "the fence name reached the founder");
  assert(stream.indexOf("&#96;&#96;&#96;") === -1, "escaped backticks leaked");
  /* B. the prose around it survives */
  assert(/Two ways to go\./.test(stream), "the useful prose was stripped");
  assert(/Treat it as a question/.test(stream), "and its first option");
  assert(/Turn it into work/.test(stream), "and its second");
  /* and the founder's own line is untouched */
  assert(/What should we do\?/.test(stream), "the founder's line was lost");
  pass("internal chips markup never reaches the founder-visible stream");
}

/* ══ A CLOSED PROTOCOL FENCE, AND ORDINARY CODE ════════════════════════ */
{
  const ctx = fresh();
  ctx.S.goalTranscript = { "shadow-1": [
    { role: "user", text: "How do I run it?", ts: "2026-09-17T10:00:00Z" },
    { role: "assistant", ts: "2026-09-17T10:00:10Z",
      text: "Run this:\n\n```bash\nls -la\n```\n\nThen:\n\n" +
            "```chips\n[\"a\",\"b\"]\n```\n\nThat is all." },
  ] };
  const stream = pane(ctx, M()).slice(pane(ctx, M()).indexOf("shtimeline"));
  /* C. ordinary code formatting is NOT stripped -- only the protocol's
     own vocabulary is, which is why the kind list is a closed set */
  assert(/ls -la/.test(stream), "an ordinary code fence was stripped");
  assert(/Run this:/.test(stream) && /That is all\./.test(stream),
    "prose either side of the fences was lost");
  /* ...and the protocol fence is gone, contents and all */
  assert(stream.indexOf("chips") === -1, "a closed chips fence leaked");
  assert(stream.indexOf("[&quot;a&quot;") === -1 && stream.indexOf('["a"') === -1,
    "the chips payload leaked");
  pass("closed protocol fences go; ordinary code fences stay");
}

/* ══ THE SANITISER ITSELF, on the two fence shapes ═════════════════════ */
{
  const ctx = fresh();
  const p = (t) => ctx.shadowProseText(t);
  assert.strictEqual(p("Prose.\n\n```chips"), "Prose.",
    "an unterminated protocol fence must go");
  assert.strictEqual(p("Prose.\n\n```chips\n[1]\n```\n\nMore."),
    "Prose.\n\nMore.", "a closed one too");
  assert.strictEqual(p("Run:\n\n```\nplain\n```"), "Run:\n\n```\nplain\n```",
    "a bare fence is the reply's own and stays");
  assert.strictEqual(p("Run:\n\n```js\nx()\n```"), "Run:\n\n```js\nx()\n```",
    "and so is a language fence");
  /* the founder writing the word chips in prose is not markup */
  assert(/chips/.test(p("I want fish and chips.")),
    "ordinary prose containing the word must survive");
  pass("the sanitiser knows protocol fences from ordinary code");
}
/* ══ THE TASK CONVERSATION IS ONE CHRONOLOGICAL STREAM ══════════════════
 *
 * TWO DEFECTS, ONE SEAM (founder, 2026-09-17; mission m-194c266205d3).
 * Reconciling the LIVE conversation against the PERSISTED transcript failed
 * twice in the same thirty lines:
 *
 *   1. a live row carried no clock (`ts: NaN`), and the comparator falls back
 *      to PUSH INDEX when either side is unstamped -- worker events are
 *      pushed first, so an unstamped line sank below every worker turn. The
 *      founder asked at 09:18:18.125Z, turn 1 opened at 09:18:19.920Z, and
 *      the pane drew the turn ABOVE the question.
 *
 *   2. the dedupe compared RAW text. The transcript keeps Shadow's raw reply
 *      ("PLACEMENT: …\n\nSent worker…"), the route returns the parsed one
 *      ("Sent worker…"), so the same answer was drawn twice -- and
 *      shadowProseHtml normalised both to identical prose on screen.
 *
 * These drive the REAL merge, shadowTimelineEvents, over the real transcript
 * reader -- not the helpers in isolation.
 */
function stream(ctx, over, live){
  ctx.S.goalTranscript = Object.assign({
    "sess-1": [], "shadow-1": [] }, (over && over.transcripts) || {});
  const T = ctx.shadowTalk();
  T.live["m-1"] = live || [];
  const m = M(Object.assign({ turns_used: 1 }, (over && over.mission) || {}));
  return ctx.shadowTimelineEvents(m);
}
/* A STRING, NOT AN ARRAY. Every events array here is built inside a vm
   context and carries THAT context's Array prototype, which
   assert.deepStrictEqual refuses however well the contents match. */
const shape = (events) => Array.prototype.map.call(events, e =>
  e.kind === "worker" ? ("WORKER " + e.n)
  : e.kind === "talk" ? (e.who === "shadow" ? "SHADOW" : "FOUNDER")
  : e.kind).join(" ");
const countIn = (s_, w) => s_.split(" ").filter(x => x === w).length;

const AT = (ms) => new Date(ms).toISOString();

/* ── A. real stamps, real order ──────────────────────────────────────── */
{
  const ctx = fresh();
  const ev = stream(ctx, { transcripts: {
    "sess-1": [{ role: "user", text: "[Shadow · mission m-1] go",
                 ts: AT(200) },
               { role: "assistant", text: "I fetched it.", ts: AT(250) }] } },
    [{ who: "founder", text: "What are you doing right now?", ts: 100 },
     { who: "shadow", text: "Sent worker first instruction.", ts: 300 }]);
  /* THE STAMPS ARE STILL 100 < 200 < 300 -- that is the fix this block was
     written for and it holds. What changed on 2026-09-17 is the DISPLAY:
     shadowTimelinePair keeps the question with its answer, so the turn the
     question stepped over is drawn after the pair rather than inside it.
     See lane G below for the pairing rule and its own guard. */
  assert.strictEqual(shape(ev), "FOUNDER SHADOW WORKER 1",
    "founder 100 < worker 200 < shadow 300, drawn as question + answer");
  assert.strictEqual(
    Array.prototype.map.call(ev, e => e.ts).join(","), "100,300,200",
    "and every row still carries the stamp the record gave it");
  pass("A: the stream is ordered by real event stamps");
}

/* ── B. a talk row with a LATER stamp sorts after the turn ───────────── */
{
  const ctx = fresh();
  const ev = stream(ctx, { transcripts: {
    "sess-1": [{ role: "user", text: "[Shadow · mission m-1] go", ts: AT(100) },
               { role: "assistant",
                 text: "I pulled the news page and listed the stories.",
                 ts: AT(120) }] } },
    [{ who: "founder", text: "and now?", ts: 200 }]);
  assert.strictEqual(shape(ev), "WORKER 1 FOUNDER",
    "a line sent after the turn opened belongs after it");
  pass("B: the comparator keys on the stamp, never on push order");
}

/* ── C. same answer, two sources, different raw text ─────────────────── */
{
  const ctx = fresh();
  const REPLY = "Sent worker first instruction: fetch the news live.";
  const RAW = "PLACEMENT: unresolved (no-match) \u2014 address assigned when "
            + "this work touches files\n\n" + REPLY;
  const ev = stream(ctx, { transcripts: {
    "shadow-1": [{ role: "user", text: "what are you doing?", ts: AT(100) },
                 { role: "assistant", text: RAW, ts: AT(200) }] } },
    [{ who: "founder", text: "what are you doing?", ts: 100 },
     { who: "shadow", text: REPLY, ts: 200 }]);
  assert.strictEqual(countIn(shape(ev), "SHADOW"), 1,
    "the persisted and live copies of one answer are one row");
  assert.strictEqual(countIn(shape(ev), "FOUNDER"), 1,
    "and so is the question");
  pass("C: live and persisted differ in raw text and still dedupe");
}

/* ── D. same answer, identical text ──────────────────────────────────── */
{
  const ctx = fresh();
  const REPLY = "Waiting on the worker. Nothing back yet.";
  const ev = stream(ctx, { transcripts: {
    "shadow-1": [{ role: "user", text: "status?", ts: AT(100) },
                 { role: "assistant", text: REPLY, ts: AT(200) }] } },
    [{ who: "founder", text: "status?", ts: 100 },
     { who: "shadow", text: REPLY, ts: 200 }]);
  assert.strictEqual(shape(ev), "FOUNDER SHADOW",
    "the pre-existing dedupe still holds");
  pass("D: identical text is still exactly one row");
}

/* ── E. the live row before the transcript has loaded ────────────────── */
{
  const ctx = fresh();
  /* goalMessages returns undefined for a chat nothing has fetched yet --
     the window the founder actually hit */
  ctx.S.goalTranscript = { "sess-1": [
    { role: "user", text: "[Shadow · mission m-1] go", ts: AT(200) },
    { role: "assistant",
      text: "I pulled the news page and listed the stories.",
      ts: AT(250) }] };
  const T = ctx.shadowTalk();
  T.live["m-1"] = [{ who: "founder", text: "hello?", ts: 100 },
                   { who: "shadow", text: "Working on it.", ts: 300 }];
  const ev = ctx.shadowTimelineEvents(M({ turns_used: 1 }));
  assert.strictEqual(ctx.goalMessages("shadow-1"), undefined,
    "the Shadow chat transcript really is unloaded");
  assert.strictEqual(shape(ev), "FOUNDER SHADOW WORKER 1",
    "the live rows still render, once each, question beside answer");
  pass("E: a live row renders correctly before the transcript arrives");
}

/* ── F. the mutation guards ──────────────────────────────────────────── */
/* A SANDBOXED COPY OF THE SOURCE with one defect re-introduced. Every guard
   below runs against one of these: a guard that cannot fail proves nothing. */
const back = (mutate) => {
  const ctx0 = { console, Date, setTimeout: () => ({}), clearTimeout(){},
    setInterval: () => ({}), scheduleRender(){},
    esc: (x) => String(x == null ? "" : x), SCREENS: {}, TITLES: {}, S: {},
    document: { addEventListener(){},
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; } } };
  vm.createContext(ctx0);
  vm.runInContext(overlay, ctx0);
  vm.runInContext(mutate(src), ctx0);
  ctx0.loadGoalTranscript = () => {};
  ctx0.goalMessages = (sid) => (ctx0.S.goalTranscript || {})[sid];
  return ctx0;
};

{

  /* F1: unstamped live rows -> the chronology inverts */
  const STAMP = "ts: Number(t && t.ts) });";
  assert(src.indexOf(STAMP) !== -1,
    "the live-row stamp is where the mutation expects it");
  const noStamp = back(t => t.replace(STAMP, "ts: NaN });"));
  noStamp.S.goalTranscript = { "sess-1": [
    { role: "user", text: "[Shadow · mission m-1] go", ts: AT(200) },
    { role: "assistant", text: "I fetched it.", ts: AT(250) }], "shadow-1": [] };
  noStamp.shadowTalk().live["m-1"] = [
    { who: "founder", text: "What are you doing right now?", ts: 100 },
    { who: "shadow", text: "Sent worker first instruction.", ts: 300 }];
  /* joined, not deepStrictEqual: this array was built in ANOTHER vm context
     and carries that context's Array prototype, which deepStrictEqual
     refuses even when every element matches. */
  const bad = shape(noStamp.shadowTimelineEvents(M({ turns_used: 1 })));
  assert.strictEqual(bad, "WORKER 1 FOUNDER SHADOW",
    "reverting the stamp must reproduce the reported inversion");

  /* F2: raw-text dedupe -> the answer doubles */
  assert(/function shadowTalkKey\(text\)\{/.test(src),
    "the dedupe key helper is where the mutation expects it");
  const rawKey = back(t => t.replace(
    /function shadowTalkKey\(text\)\{[\s\S]*?\n\}/,
    "function shadowTalkKey(text){ return String(text == null ? '' : text); }"));
  const REPLY = "Sent worker first instruction: fetch the news live.";
  const RAW = "PLACEMENT: unresolved (no-match)\n\n" + REPLY;
  rawKey.S.goalTranscript = { "sess-1": [], "shadow-1": [
    { role: "user", text: "what are you doing?", ts: AT(100) },
    { role: "assistant", text: RAW, ts: AT(200) }] };
  rawKey.shadowTalk().live["m-1"] = [
    { who: "founder", text: "what are you doing?", ts: 100 },
    { who: "shadow", text: REPLY, ts: 200 }];
  const dupes = countIn(
    shape(rawKey.shadowTimelineEvents(M({ turns_used: 0 }))), "SHADOW");
  assert.strictEqual(dupes, 2,
    "reverting the key must reproduce the reported duplicate");
  pass("F: both defects are reproducible, so both guards really bite");
}

/* ══ G. A QUESTION AND ITS ANSWER ARE ONE BLOCK ════════════════════
 *
 * THE DEFECT (founder, 2026-09-17), downstream of the fix lanes A-F pinned.
 * Once every row carried a real stamp the stream was chronological -- and a
 * worker turn that opened between the founder pressing send and Shadow
 * answering then sorted BETWEEN them:
 *
 *     founder 100 · worker 150 · shadow 200
 *
 *         YOU → SHADOW   "What are you doing right now?"
 *         WORKER TURN 1
 *         SHADOW         "Sent worker first instruction…"
 *
 * Nothing there is untrue and it still reads wrong. shadowTimelinePair is the
 * answer: a DISPLAY pass over the sorted array that keeps a founder line and
 * its replies adjacent and draws what they stepped over after them.
 *
 * WHAT THESE LANES ALSO PROVE IS WHAT DID NOT CHANGE -- the stamps, the
 * dedupe, and a worker turn's right to sit between two separate exchanges.
 */
const tsOf = (events) => Array.prototype.map.call(events, e => e.ts).join(",");
/* what a stamps-only renderer would have drawn, from the very same rows */
const byStamp = (events) => shape(
  Array.prototype.slice.call(events).sort((a, b) => a.ts - b.ts));
const TURN = (at, say) => ([
  { role: "user", text: "[Shadow · mission m-1] go", ts: AT(at) },
  { role: "assistant", text: say, ts: AT(at + 10) }]);

/* ── G1. the reported case: a turn opens mid-exchange ─────────────── */
{
  const ctx = fresh();
  const ev = stream(ctx, { transcripts: {
    "sess-1": TURN(150, "I fetched the news page.") } },
    [{ who: "founder", text: "What are you doing right now?", ts: 100 },
     { who: "shadow", text: "Sent worker first instruction.", ts: 200 }]);
  assert.strictEqual(shape(ev), "FOUNDER SHADOW WORKER 1",
    "the turn must not come between the question and its answer");
  assert.strictEqual(tsOf(ev), "100,200,150",
    "and no stamp is rewritten to make that happen");
  assert.strictEqual(byStamp(ev), "FOUNDER WORKER 1 SHADOW",
    "the rows really do carry the stamps that would split them");
  pass("G1: a worker turn stamped mid-exchange is drawn after the pair");
}

/* ── G2. between two exchanges it keeps its place ───────────────── */
{
  const ctx = fresh();
  const ev = stream(ctx, { mission: { turns_used: 1 }, transcripts: {
    "sess-1": TURN(300, "I listed the stories.") } },
    [{ who: "founder", text: "what are you doing?", ts: 100 },
     { who: "shadow", text: "Briefing the worker.", ts: 200 },
     { who: "founder", text: "and now?", ts: 400 },
     { who: "shadow", text: "Reading what it sent back.", ts: 500 }]);
  assert.strictEqual(shape(ev),
    "FOUNDER SHADOW WORKER 1 FOUNDER SHADOW",
    "a turn BETWEEN two exchanges is not swept to the end");
  assert.strictEqual(tsOf(ev), "100,200,300,400,500",
    "which here is also plain chronological order");
  pass("G2: worker events still appear between separate exchanges");
}

/* ── G3. several exchanges, each with a turn inside it ──────────── */
{
  const ctx = fresh();
  const ev = stream(ctx, { mission: { turns_used: 2 }, transcripts: {
    "sess-1": TURN(150, "I fetched the news page.")
      .concat(TURN(350, "I wrote the summary.")) } },
    [{ who: "founder", text: "what are you doing?", ts: 100 },
     { who: "shadow", text: "Briefing the worker.", ts: 200 },
     { who: "founder", text: "and now?", ts: 300 },
     { who: "shadow", text: "Reading what it sent back.", ts: 400 }]);
  assert.strictEqual(shape(ev),
    "FOUNDER SHADOW WORKER 1 FOUNDER SHADOW WORKER 2",
    "each question keeps its own answer, and each turn follows its pair");
  assert.strictEqual(byStamp(ev),
    "FOUNDER WORKER 1 SHADOW FOUNDER WORKER 2 SHADOW",
    "stamps alone would have split BOTH exchanges");
  assert.strictEqual(tsOf(ev), "100,200,150,300,400,350",
    "the turns keep their own stamps and their own order");
  pass("G3: several exchanges pair independently");
}

/* ── G4. after a reload, off the transcript alone ──────────────── */
{
  const ctx = fresh();
  /* nothing live: this is the pane a founder opens tomorrow, where every row
     comes back through shadowTalkTurns -> shadowTaskTranscript */
  const ev = stream(ctx, { transcripts: {
    "sess-1": TURN(150, "I fetched the news page."),
    "shadow-1": [
      { role: "user", text: "what are you doing?", ts: AT(100) },
      { role: "assistant", text: "Sent worker first instruction.",
        ts: AT(200) }] } }, []);
  assert.strictEqual(shape(ev), "FOUNDER SHADOW WORKER 1",
    "a reloaded conversation pairs exactly as the live one did");
  assert.strictEqual(byStamp(ev), "FOUNDER WORKER 1 SHADOW",
    "and the persisted stamps are the splitting ones too");
  pass("G4: the pairing survives a reload");
}

/* ── G5. the dedupe still holds with a turn in the middle ───────── */
{
  const ctx = fresh();
  const REPLY = "Sent worker first instruction: fetch the news live.";
  const RAW = "PLACEMENT: unresolved (no-match) — address assigned when "
            + "this work touches files\n\n" + REPLY;
  const ev = stream(ctx, { transcripts: {
    "sess-1": TURN(150, "I fetched the news page."),
    "shadow-1": [{ role: "user", text: "what are you doing?", ts: AT(100) },
                 { role: "assistant", text: RAW, ts: AT(200) }] } },
    [{ who: "founder", text: "what are you doing?", ts: 100 },
     { who: "shadow", text: REPLY, ts: 200 }]);
  assert.strictEqual(countIn(shape(ev), "SHADOW"), 1,
    "ONE visible Shadow answer, live and persisted reconciled");
  assert.strictEqual(countIn(shape(ev), "FOUNDER"), 1, "and one question");
  assert.strictEqual(shape(ev), "FOUNDER SHADOW WORKER 1",
    "deduped AND paired, in one pass");
  pass("G5: dedupe and pairing compose — exactly one Shadow row");
}

/* ── G6. a question with no answer yet holds nothing back ──────── */
{
  const ctx = fresh();
  const ev = stream(ctx, { transcripts: {
    "sess-1": TURN(150, "I fetched the news page.") } },
    [{ who: "founder", text: "what are you doing?", ts: 100 }]);
  assert.strictEqual(shape(ev), "FOUNDER WORKER 1",
    "an unanswered question does not defer the work happening under it");
  pass("G6: a reply still in flight never stalls the stream");
}

/* ── G7. the mutation guard ─────────────────────────────── */
{
  /* Timestamp-only ordering is re-introduced -- shadowTimelinePair becomes
     the identity -- and the reported split must come back. */
  const PAIR = "function shadowTimelinePair(seq){";
  assert(src.indexOf(PAIR) !== -1,
    "the pairing pass is where the mutation expects it");
  const flat = back(t => t.replace(
    /function shadowTimelinePair\(seq\)\{[\s\S]*?\n\}/,
    "function shadowTimelinePair(seq){ return seq; }"));
  flat.S.goalTranscript = {
    "sess-1": [{ role: "user", text: "[Shadow · mission m-1] go",
                 ts: AT(150) },
               { role: "assistant", text: "I fetched the news page.",
                 ts: AT(160) }], "shadow-1": [] };
  flat.shadowTalk().live["m-1"] = [
    { who: "founder", text: "What are you doing right now?", ts: 100 },
    { who: "shadow", text: "Sent worker first instruction.", ts: 200 }];
  assert.strictEqual(
    shape(flat.shadowTimelineEvents(M({ turns_used: 1 }))),
    "FOUNDER WORKER 1 SHADOW",
    "reverting to timestamp-only order must reproduce the split");
  pass("G7: stamps alone really do split the exchange — the guard bites");
}

Promise.all(asyncChecks).then(() => {
  console.log("\nall unified Talk-to-Shadow tests passed");
}, (e) => { console.error(e); process.exitCode = 1; });
