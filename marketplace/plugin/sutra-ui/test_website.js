#!/usr/bin/env node
/* test_website.js -- the website department on the department screen
   (static/js/22-website.js; the first build, holding/website/native/system/
   first-build.html).

   Named claims:
     W1  no global of 22-website.js is a global of any other script (it once
         took S.ws and ws*() from 13-workspace.js; this is the test that would
         have caught it)
     W2  a department with no website record paints exactly as before
     W3  a website department's list: Map, System status, Motor, the five
         functions, its engines with a state word, its filed work with dots
     W4  before a goal the Map asks for one; Start posts it
     W5  with a goal the Map shows the systems, the line, System status with
         Stamp, Refuse and Stop, Ask, Health, Recent
     W6  Stamp, Stop, Ask and Put back each post the one route they name
     W7  a click on one of 20-dept.js's rows hands the viewer back, and the
         function card carries this department's own state under it
     W8  Preview shows the thing itself in a frame that can run nothing
     W9  the screen prints no count and no path at rest
     W10 the Edit menu carries the command, and panel.html loads the script
         before the tail
     W11 the stylesheet block is tokens only and every class the script emits
         has a rule or is one of 20-dept.js's own
     W12 a department on the engine runtime gains the Board in its list; one
         that is not on it gains nothing and reads neither steps nor board
     W13 an engine opens on its steps: each with its rung, its check, what its
         rows say and Hold; the words carry no step id, rung code or count
     W14 Hold posts the one route it names, and the card that is open stays open
     W15 the Board is a list of threads and the open one as a chat: who spoke
         to whom and with which act; the ideas parked; an empty board is one
         quiet line (amended 2026-09-28: the Board as chats)
     W16 the Map of a runtime department has one way in, shows what the
         department said back, and a function's card carries its steps
     W17 a runtime department has one button, Start when it is off and Stop
         when it is on, at the top of its Map; each posts the one route
     W18 every engine's card says how it starts, on what and unless what, and
         Coordination's card carries its table: who goes first, who may post
     W19 on the screen the five are functions; the word "internal system" is
         the inside word and is printed nowhere
     W25 the chat is the one point of entry: a runtime department opens on it;
         inside a department the same chat scoped, the box carries the
         department as a chip; the words go to Root; a stamp goes where the ask
         lives; on Root the whole chat, the department a chip on the turn
     W26 each function's card has its own Settings tab: its template, its own
         limit, its ladder numbers, how it starts; Identity's carries where the
         site is served from; a department of the first build has none
     W27 the department's own asks and answers are turns of the same chat
         (ER-10): inside the department without a chip, on Root with its chip;
         a stamp of its own says Stamped
     W28 the department chip in Root's chat opens the department; the tree
         learns of a Root-born department without a reload (Human Simulation
         run 1, findings 1 and 2)
     W29 while a function runs the chat says so; when the site goes live the
         turn carries "Open the live site", which previews it, and from Root's
         chat opens that department on it (Human Simulation run 1, findings 5
         and 6)
     W30 a department born since the list was read is read again once and
         wears its own view when the read lands (run 2, finding 17)
     W31 the chat keeps its place across a paint and moves to a turn only when
         one lands (run 2, the scroll-to-top after Send)
     W32 Root's box, once departments exist, invites words for one of them
     W33 the working line says how far along (page n of m) and is gone when
         the department is Off (run 2, finding 15)
     W34 a function's chat is its existing turns and thinking from the record,
         with a box to say more; never a Start button, never a new chat
         (founder 2026-09-29)
     W42 the organisation row is Root's chat and nothing else; Root is not a
         row of the tree nor a tile of the chart; its departments sit under
         the organisation (founder 2026-09-29: "at the organization level,
         only a chat is shown, and root is not shown")
     W43 Root settings is a pane, never a chat: what Root does, On or Off with
         its one switch, its rules, the departments it made, a way back
     W44 founding lands on the organisation, whose row is Root's chat
     S16 a function's Settings lists its instruction files by the names its
         page gives them, each with its first line, as shipped or your words,
         and Change; Change opens a sheet whose Send files the one ask; the
         row then says the change waits for the stamp; no path, no count
         (PRD M2.3)
     X1  (UI-port package j2ui-shell) Settings > Instructions from the interface's typed view: a card for each group
         (its lead as the title), in it each part with its fields (the words in use, as shipped or your words,
         Change) and the notes `filled by the app` and `answers with` in words; a part no run reads says so; a field
         that waits says so beside the amber mark; an earlier whole-file change reads kept as your note; no path, no
         `Return ONLY`, no JSON, no count at rest (from test_fixtures/views/instructions.identity.json); before the
         typed fields arrive the first design's files are listed as they were (S16 above)
     X2  Change opens a sheet: a textarea with a count of its length against the field's most, or a list editor for
         skills (add, remove, move, at most the field's most); past the most the count says so and Send is disabled
     X3  Send posts {fn, group, part, field, value} to the one route; the sheet closes and the card is read again; a
         refusal shows the server's plain reason under the field, never the route
     X4  Root settings carries a read-only card Standards every plan meets: the standards in their order from GET /layers,
         the line that says they are the app's, no button; read once for the pane and kept (test_fixtures/views/layers.json)
     X5  each function's Settings head says Runs version N, N the number after /v in its layer's pin
     X6  Root's check on Adaptation's pane (S11), from test_fixtures/views/adaptation.root_checks.json: one row, a ticked or
         crossed ring for each standard that applied titled with its words, the verdict and the time; a plan sent
         back names the broken standard in its words with why, and shows the reshapes as two dots; blocked after two;
         not yet says Root has not checked a plan; no count at rest
     S7  Coordination's pane on the engine runtime opens on its timetable: one row per engine with what starts it, its
         window, and its last run or the exact reason it waits; who makes and who reads each thing; the chain, alarms
         and ties side by side; the function's page folded under it; every state the screen names; no count at rest
         (PRD M4.7)
     S17 the engine card on the engine runtime: its head on every tab, the motor folded in (slot, once per slot,
         window, today), and one row for each of the five; the Motor row leaves the list column (PRD M4.7)
     W47 Identity's open question is a card in Chat with its own answer box:
         Send posts {text} to the department's /j2/answer, reads Sending...
         while it goes, a refused answer is a snack and the words stay, and
         the answered card keeps 'You: ...' (PRD-FIVE-FUNCTIONS M0.6, S6)
     W48 a question on Identity's standard offers Just do it, which sends
         'just do it' to the same answer box, whether Identity's reading or its
         code asked it; a question on thin words offers none (PRD M3.3, S6)
     W50 one voice: a function's chat box says the words go to Identity about
         that function, and they go to the department about it (PRD M3.6)
     W51 one voice: in a department's chat every turn of the department's is
         Identity's, signed with Identity's mark and the department's name,
         with or without a Root; Root's own chat keeps Root, the department a
         chip on its turns (PRD M3.6, S15)
     S5  Identity's pane: the open question card, Enough to work? row by row
         with a word beside each dot, the goal with Change the goal (the Chat,
         its box begun), done-when items with level, how and to confirm, the
         rules with where each came from, the conflicts closed; how Identity
         works folds under them; never 'charter' (PRD M3.7)
     W49 a blocked plan is a card with its ways out: who, why and if nothing
         is done, each option with its cost; one click posts {option}, the box
         posts {option: words, text}; an unknown option is a snack; chosen,
         the card goes quiet with 'You chose: ...'; never a stamp (PRD M3.5, S10)
     W52 the cards that wait on the owner stand wherever the department needs
         them: Identity's question (S6) and a blocked plan's card (S10) at the
         top of All five; the blocked card at the top of the pane of the
         function that caused it, and pinned at the top of Chat while it is
         open; the same card and state everywhere, answered in one place,
         and kept so by the poll clock on All five and on a function's pane
         (PRD M3.7)

   Harness: test_dept.js's fresh(), with 22-website.js loaded after 20-dept.js
   (panel.html's order). Run: node test_website.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const read = f => fs.readFileSync(path.join(JS, f), "utf8");
const orgSrc = read("03-org.js"), o2Src = read("19-org2.js"), dpSrc = read("20-dept.js"), wbSrc = read("22-website.js"), sxSrc = read("23-screens.js");
const fvSrc = read("24-functions.js");
const panelHtml = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
const RB = "/* rail-helpers:begin */", RE = "/* rail-helpers:end */";
const railSrc = orgSrc.slice(orgSrc.indexOf(RB), orgSrc.indexOf(RE));

let failed = 0, ran = 0;
const pending = [];
function test(name, fn){
  ran++;
  try {
    const r = fn();
    if (r && typeof r.then === "function") pending.push(r.then(() => console.log("ok   " + name), e => { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e)); }));
    else console.log("ok   " + name);
  } catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e)); }
}
const sleep = () => new Promise(r => setTimeout(r, 0));

const ROOT = { ref: "r0", path: "D0", name: "Sutra", parent_ref: null, status: "active", ts_minted_ms: 1, node_kind: "root" };
const ORG  = { ref: "r1", path: "D1", name: "City Care Hospital", parent_ref: "r0", status: "active", ts_minted_ms: 2, node_kind: "organisation" };
const RT   = { ref: "r2", path: "D1.D1", name: "Root", parent_ref: "r1", status: "active", ts_minted_ms: 3, node_kind: "department" };
const WEB  = { ref: "r3", path: "D1.D1.D1", name: "Website", parent_ref: "r2", status: "active", ts_minted_ms: 4, node_kind: "department" };
const OTHER = { ref: "r4", path: "D1.D1.D2", name: "Billing", parent_ref: "r2", status: "active", ts_minted_ms: 5, node_kind: "department" };
const TREE = [ROOT, ORG, RT, WEB, OTHER];

const ENGS = [["Plan", "Brief", "Site plan", "model"], ["Write", "Site plan", "Pages", "model"],
              ["Check", "Pages", "Build", "code"], ["Publish", "Build", "Live site", "code"]];
function mapOf(o){
  o = o || {};
  const vers = o.versions || { "Brief": 1, "Site plan": 2, "Pages": 5, "Build": 5, "Live site": 0 };
  return {
    ref: "r3", name: "City Care Hospital Website", goal: "A live website for City Care Hospital", done: "Every page checked and live",
    rules: [], owner: "Sankalp", control: "granted", stopped: !!o.stopped, has_goal: o.has_goal !== false, live: !!o.live,
    runtime: o.runtime || 1,
    systems: ["Identity", "Adaptation", "Priority", "Coordination", "Audit"].map(n => ({ name: n, state: /Adaptation|Audit/.test(n) && o.runtime !== 2 ? "paused" : "running", last: null })),
    engines: ENGS.map(e => ({ name: e[0], reads: e[1], writes: e[2], runs_as: e[3], slot: "after a new " + e[1],
      state: e[0] === "Publish" && o.ask ? "Waits" : "Idle", envelope: { calls: 30, usd: 6, used_calls: 3, used_usd: 0.4 }, window_min: 15,
      last: { status: "ok", at: "2026-09-27T11:02:00+05:30", what: "" } })),
    artifacts: Object.keys(vers).map(n => ({ name: n, slug: n.toLowerCase().replace(/ /g, "-"), versions: vers[n], latest: null })),
    status: { asks: o.ask ? [{ id: "a-1", kind: "publish", engine: "Publish", text: "Publish: go live for the first time", status: "pending", created: "2026-09-27T11:08:00+05:30" }] : [],
              escalated: [], waits: o.ask ? [{ what: "Publish", why: "for the stamp", since: "2026-09-27T11:08:00+05:30" }] : [], running: [], stopped: !!o.stopped, next: "nothing due" },
    health: { motor: { last_tick: "2026-09-27T11:09:00+05:30", age_s: 2 },
              checks: ["Motor", "Slots", "Versions", "Stuck", "Awake", "Budget", "Done"].map(n => ({ name: n, state: "ok", line: "" })),
              never: [{ name: "A slot run twice", ok: true }],
              timeline: [{ engine: "Plan", system: false, status: "ok", started: "2026-09-27T10:55:00+05:30", ended: "2026-09-27T10:56:00+05:30", slot: "Plan@brief.v1", what: "" }] },
    recent: [{ engine: "Write", system: false, status: "ok", at: "2026-09-27T11:02:00+05:30", what: "Pages from Site plan, check passed" }],
    requests: [], templates: {},
  };
}
/* What the engine runtime's two reads answer (engine_runtime.py: steps_view, board_view). */
const AT = "2026-09-28T10:02:00+05:30";
function stepOf(o){
  return Object.assign({ nature: "transform", mode: "slot", under: null, rung: "C2", rung_name: "Code", form: null, born: "C2", ceiling: "C2",
    soft: false, held: false, pending: null, trial: null, each: false, side_by_side: 1, ran: true,
    last: { at: AT, status: "ok", rung: "C2", miss: false, by: "code", item: null, ok: true, notes: ["every page of the plan is listed"] },
    evidence: { runs: 5, differing: 0, shape_drift: 0, pass: 1, marked: 0, misses: 0, usd: 0 },
    history: [{ at: AT, from: null, to: "C2", by: "born", evidence: null }] }, o);
}
function stepsOf(name, o){
  o = o || {};
  const numbers = { runs: 40, differing: 1, trial: 20, misses: 3 };
  if (name === "Write") return { name, kind: "work", description: "Writes every page the plan names", skills: ["Writing"], reads: "Site plan", writes: "Pages",
    start: { on: ["a new Site plan"], unless: [{ by: "Identity", name: "Say whether it may start" }, { by: "Priority", name: "Keep it inside its envelope" },
                                                { by: "Coordination", name: "Stop a chain at its limit" }] },
    hears: [], numbers, steps: [
      stepOf({ id: "write.list", name: "List the pages", check: "list_has_pages" }),
      stepOf({ id: "write.page", name: "Write a page", nature: "make", rung: o.rung || "C0", rung_name: o.rung_name || "Improvised call", born: "C0", ceiling: "C1",
               soft: true, each: true, side_by_side: 4, check: "page_has_body", held: !!o.held, trial: o.trial || null, pending: o.pending || null,
               last: { at: AT, status: "ok", rung: "C0", miss: false, by: "model", item: "careers", ok: true, notes: ["the page has a body"] },
               evidence: { runs: 10, differing: 0, shape_drift: 0, pass: 0.9, marked: 0, misses: 0, usd: 0.01 },
               history: [{ at: AT, from: null, to: "C0", by: "born", evidence: null }].concat(o.moved ? [{ at: AT, from: "C0", to: "C1", by: "the owner's stamp", evidence: {} }] : []) }),
      stepOf({ id: "write.file", name: "Put the pages together", check: "filed_has_files", ran: false, last: null, evidence: null })] };
  const table = name !== "Coordination" ? undefined : { first: ["A post waiting for its reader", "The line, in its order", "A function woken by new work"],
    line: ["Plan", "Write", "Check", "Publish"], may_post: [{ from: "Audit", act: "inform", to: ["Identity"] }, { from: "Owner", act: "request", to: ["Identity"] }] };
  const limits = name !== "Priority" ? undefined : ENGS.map(e => ({ engine: e[0], calls: 240, usd: 6, used_calls: 3, used_usd: 0.4 }))
    .concat(["Identity", "Adaptation", "Priority", "Coordination", "Audit"].map(s => ({ engine: s, calls: 30, usd: 6, used_calls: 0, used_usd: 0 })));
  const fn = name.toLowerCase(), instructions = o.instructions !== undefined ? JSON.parse(JSON.stringify(o.instructions)) : (INS[fn] || []).map(([file, lead]) => ({ file, lead, text: lead + "\n\n## " + file + "\n\nThe words.\n",
    as_shipped: o.mine !== fn + ":" + file, read: fn + ":" + file !== "adaptation:decide", waits: o.waits === fn + ":" + file ? { ask: "a-9", at: "2026-10-23T11:02:00+05:30" } : null }));
  return { name, kind: "function", description: name === "Priority" ? "grants each engine its budget" : "", skills: [], reads: null, writes: null, numbers, table, limits, instructions,
    start: { on: ["a post addressed to it"], unless: [] },
    hears: (table ? ["What engines share"] : []).concat(["Take a request"]), steps: [
    stepOf({ id: name.toLowerCase() + ".gate", name: "Say whether it may start", nature: "decide", mode: "gate", check: "gate_answer_is_known" }),
    stepOf({ id: name.toLowerCase() + ".pick", name: "Say who goes first, when several are ready", nature: "decide", mode: "rule", under: table ? "What engines share" : "Nowhere", check: "names_who_goes_first" }),
    stepOf({ id: name.toLowerCase() + ".read", name: "Read the request", under: "Take a request", check: "brief_is_text" })] };
}
/* Each function's instruction files, as its page names them, with the line that says what each is for
   (engine_runtime.py: INSTRUCTIONS, instructions_view; function-prompts/). */
const INS = {
  identity: [["goal", "What Identity is for, and the rules it keeps."], ["completeness", "When the department has enough to work; what to ask if not."],
             ["take", "How to judge a request: go, ask or refuse."]],
  adaptation: [["goal", "What Adaptation is for, and the rules it keeps."], ["sense", "How Adaptation reads an idea the owner floats: what it asks, and the shapes it could take."],
               ["decide", "How Adaptation chooses its next move from what the department's own rows say."],
               ["make", "How Adaptation shapes the workflows a goal needs when none is in place."]],
  priority: [["goal", "What Priority is for, and the rules it keeps."], ["bargain", "How Priority answers a proposal: said yes, asked for less, or said no."]],
  coordination: [["goal", "What Coordination is for, and the rules it keeps."], ["tie", "How Coordination says who goes first when several functions are ready at once."]],
  audit: [["goal", "What Audit is for, and the rules it keeps."], ["judge", "How Audit reads what went live against what was asked."]] };
const FNCHAT = { fn: "Identity", dept: "r3", name: "City Care Hospital Website", any: true, turns: [
  { n: 1, src: "Owner", dst: ["Identity"], msg_type: "request", at: "2026-09-27T11:00:00+05:30", thread: "t1", word: "request", line: "A website for the hospital", think: false },
  { n: null, src: "Identity", dst: [], msg_type: "step", at: "2026-09-27T11:00:05+05:30", thread: "r-1", word: "identity.read", line: "Read the words, code", think: true },
  { n: 2, src: "Identity", dst: ["Owner"], msg_type: "agree", at: "2026-09-27T11:00:20+05:30", thread: "t1", word: "request", line: "Filed in the Brief.", think: false }] };
const BOARD = { any: true,
  ideas: [{ id: "i-1", words: "what about a patient portal", reflected: "A place where patients sign in", question: "Who signs in first?",
            shapes: ["A page that links out", "A sign-in of its own"], state: "parked", at: AT }],
  threads: [
    { id: "x-2", topic: "rule", protocol: "request", state: "input-required", decider: "Owner", opened: AT, closed: null, outcome: null,
      bounds: { hops: 4, seconds: 900, usd: 0.5 }, hops: 0, default: "failure", posts: [
        { n: 3, src: "Identity", dst: ["Owner"], msg_type: "request", at: AT, word: "rule", line: "A rule, as understood: every page names a phone line" }] },
    { id: "x-1", topic: "request", protocol: "request", state: "completed", decider: "Identity", opened: AT, closed: AT, outcome: { by: "inform" },
      bounds: { hops: 4, seconds: 900, usd: 0.5 }, hops: 0, default: "failure", posts: [
        { n: 1, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, word: "request", line: "Which page lists the doctors?" },
        { n: 2, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, word: "answer", line: "The Doctors page lists them" }] }] };
/* What the chat read answers (engine_runtime.py: chat_view): on Root the whole
   chat, inside a department the same chat scoped to it. */
const DEPT = "City Care Hospital Website";
const ROOT_CHAT = { root: "r3", about: null, departments: [{ ref: "r5", name: DEPT, stopped: false }], turns: [
    { n: 1, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, thread: "x-1", word: "front", line: "Start a website department for City Care Hospital", dept: null, name: null },
    { n: 2, src: "Identity", dst: ["Owner"], msg_type: "request", at: AT, thread: "x-1", word: "setup", line: "Set up a department: City Care Hospital Website", dept: null, name: null },
    { n: 3, src: "Owner", dst: ["Identity"], msg_type: "accept-proposal", at: AT, thread: "x-1", word: "setup", line: "", dept: null, name: null },
    { n: 5, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, thread: "x-4", word: "front", line: "Which page lists the doctors?", dept: "r5", name: DEPT },
    { n: 6, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: "x-4", word: "request", line: "handed to City Care Hospital Website", dept: "r5", name: DEPT },
    { n: 7, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: null, word: "answer", line: "The Doctors page lists them", dept: "r5", name: DEPT },
    /* the department's own turns (ER-10): its publish ask and the owner's stamp, from its own board */
    { n: 3, src: "Identity", dst: ["Owner"], msg_type: "request", at: AT, thread: "x-9", word: "publish", line: "say whether the site may go live for the first time", dept: "r5", name: DEPT, own: true },
    { n: 4, src: "Owner", dst: ["Identity"], msg_type: "accept-proposal", at: AT, thread: "x-9", word: "publish", line: "", dept: "r5", name: DEPT, own: true }],
  asks: [{ id: "a-1", kind: "publish", engine: "Publish", text: "Publish: go live for the first time", status: "pending", created: AT, ref: "r5", dept: DEPT }] };
const CHAT = { root: "r2", about: "r3", departments: [{ ref: "r3", name: DEPT, stopped: false }],
  turns: ROOT_CHAT.turns.filter(t => t.dept).map(t => Object.assign({}, t, { dept: "r3" })),
  asks: [Object.assign({}, ROOT_CHAT.asks[0], { ref: "r3" })] };

/* What the five functions' read answers (functions_view.py: functions): the five nodes in canonical order, the cycle in
   the owner's words with its eight steps, who spoke to whom, what was made and who reads it, and what is not recorded. */
const FV_NAMES = ["Identity", "Adaptation", "Priority", "Coordination", "Audit"];
const FV_WORDS = { working: "working", waiting: "waiting", waiting_on_you: "waits on you", fault: "fault", quiet: "quiet" };
const FV_STEPS = ["Enough to work", "Propose", "Price", "Settle", "Root's review", "Run", "Read", "Next or done"];
function fvOf(o){
  o = o || {};
  const states = o.states || {}, lines = o.lines || {};
  const step = (o.cycle && o.cycle.step) || 6;
  return {
    ref: "r3", name: DEPT, kind: "website", stopped: !!o.stopped,
    functions: FV_NAMES.map(n => {
      const s = states[n] || "quiet";
      /* a stopped department's word is 'stopped' on every function (functions_view.py functions) */
      return { id: "fn:" + n.toLowerCase(), fn: n.toLowerCase(), name: n, state: s, word: o.stopped ? "stopped" : FV_WORDS[s],
        waits_on: s === "waiting_on_you" ? "you" : (s === "waiting" ? ((o.waits || {})[n] || "Priority") : null),
        line: lines[n] !== undefined ? lines[n] : (s === "working" ? "working" : (s === "waiting" ? "waits on " + ((o.waits || {})[n] || "Priority") : "")),
        why: s === "fault" ? (lines[n] || "a step failed its check") : null,
        last: (o.last || {})[n] === undefined ? { what: "did its part", at: AT } : o.last[n],
        spend: { calls: 3, usd: 0.4, calls_limit: 30, usd_limit: 6, share: (o.share || {})[n] === undefined ? 0.1 : o.share[n] },
        speaks_to: (o.speaksTo || {})[n] || [], made: [] };
    }),
    cycle: Object.assign({ state: "running", step: step, journey: "J2.f", says: "The work is running",
      steps: FV_STEPS.map((name, i) => ({ step: i + 1, name, state: i + 1 < step ? (i === 3 ? "skipped" : "done") : (i + 1 === step ? "now" : "next"),
                                          last: i + 1 <= step ? { summary: name + " happened", at: AT } : null })),
      needs_you: false, asks: 0, running: [], ceiling: null, round: null }, o.cycle || {}),
    speaks: o.speaks || [], made: o.made || [], between: o.between || [],
    budget: { calls: 30, usd: 1.2, calls_limit: 120, usd_limit: 60, share: o.budget === undefined ? 0.25 : o.budget, of: "today's limits" },
    not_recorded: o.not_recorded || [] };
}

function fresh(opts){
  opts = opts || {};
  const calls = { apiGet: [], apiPost: [], render: 0 };
  const map = opts.map === undefined ? mapOf() : opts.map;
  const ctx = {
    console, Date, Number, String, Array, Set, Map, JSON, Math, encodeURIComponent, Promise, setTimeout, clearTimeout, isNaN,
    setInterval: () => 1, clearInterval: () => {},
    apiGet: (p) => {
      calls.apiGet.push(p);
      if (p === "/api/native/depts") return Promise.resolve({ depts: opts.none ? [] : (opts.depts || [{ ref: "r3", name: "Website", stopped: false }]) });
      if (/\/api\/native\/r3\/map$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(map)));
      /* Root (r2), for the organisation's row (W42-W44) */
      if (/\/api\/native\/r2\/map$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(opts.rootMap || rtMap())));
      if (/\/api\/native\/r2\/chat$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(opts.rootChat || ROOT_CHAT)));
      if (/\/api\/native\/r3\/steps\//.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(stepsOf(decodeURIComponent(p.split("/steps/")[1]), opts.steps))));
      if (/\/api\/native\/r3\/board$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(opts.board || BOARD)));
      if (/\/api\/native\/r3\/chat\?fn=/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(opts.fnchat || FNCHAT)));
      if (/\/api\/native\/r3\/chat$/.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(opts.chat || CHAT)));
      /* the five functions' read (functions_view.py), when the test gives one; a function's own page likewise */
      if (/\/api\/native\/r3\/functions$/.test(p) && opts.fv) return typeof opts.fv === "function" ? opts.fv() : Promise.resolve(JSON.parse(JSON.stringify(opts.fv)));
      if (/\/api\/native\/r3\/functions\//.test(p) && opts.fnpage) return Promise.resolve(JSON.parse(JSON.stringify(opts.fnpage(decodeURIComponent(p.split("/functions/")[1])))));
      if (/\/api\/native\/r3\/engine\//.test(p)) return Promise.resolve(JSON.parse(JSON.stringify(Object.assign({ runs: [] }, map.engines[1], opts.engine || {}))));
      if (/\/artifact\//.test(p)) return Promise.resolve({ name: "Live site", slug: "live-site",
        template: { id: "artifact/live-site", name: "Live site", kind: "site", files: ["index.html", "*.html"], checks: ["has_index_html"],
                    written_by: ["Publish"], counts_after: "stamp", put_back: true, operations: ["Adaptation", "Audit"] }, versions: [
        { v: 2, at: "2026-09-27T11:20:00+05:30", made_from: [{ art: "Build", v: 6 }], run: "r-2", check: { ok: true, notes: ["live"] }, note: "" },
        { v: 1, at: "2026-09-27T11:10:00+05:30", made_from: [{ art: "Build", v: 5 }], run: "r-1", check: { ok: true, notes: ["live"] }, note: "" }] });
      /* the interface the department runs under (GET /layers): what a test gives, or nothing that answers; layersFail refuses it */
      if (/\/api\/native\/r\d\/layers$/.test(p) && opts.layersFail) return Promise.reject(new Error("layers"));
      if (/\/api\/native\/r\d\/layers$/.test(p) && opts.layers) return Promise.resolve(JSON.parse(JSON.stringify(opts.layers)));
      if (/^\/api\/dept\//.test(p)) return Promise.resolve({});   /* 20-dept.js's own reads: an empty record */
      return new Promise(() => {});
    },
    apiPost: (p, body) => { calls.apiPost.push({ p, body }); return Promise.resolve({ ref: "r3", org: "r1", root: "r2" }); },
    window: {},
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"),
    SCREENS: { departments: () => "" }, TITLES: { departments: ["Departments", ""] },
    DOMAINS: TREE, CHARTERS: [], PLACEMENTS: [], INDEX: [], META: {},
    SETTINGS: { flags: { org2: true } },
    ICON: { know: "<path d='k'/>", dept: "<path d='d'/>", edit: "<path d='e'/>", plc: "<path d='p'/>" },
    st: (d) => d.status || "active",
    S: { screen: "org2", ui: { dest: "org2" }, showRetired: false, draft: { ops: [] } },
    render: () => { calls.render++; },
    loadOrg: () => Promise.resolve(), simulate: () => ({ pending: true }),
    sbPageFromPath: () => null, mdHtml: (t) => "<p>" + t + "</p>",
    decideProposal: () => Promise.resolve({}), loadProposals: () => {},
    document: {
      listeners: {}, activeElement: null, body: { appendChild(){} },
      addEventListener(type, fn){ (this.listeners[type] = this.listeners[type] || []).push(fn); },
      querySelector(){ return null; }, querySelectorAll(){ return []; }, getElementById(){ return null; },
      createElement(){ return { id: "", innerHTML: "" }; },
    },
  };
  ctx.calls = calls;
  vm.createContext(ctx);
  vm.runInContext(railSrc, ctx);
  vm.runInContext(o2Src, ctx);
  vm.runInContext(dpSrc, ctx);
  vm.runInContext(wbSrc, ctx);
  vm.runInContext(sxSrc, ctx);
  vm.runInContext(fvSrc, ctx);
  /* the second design is the default; the first design's claims are pinned to the switch off, v2() sets it on */
  vm.runInContext("wbS().v2 = false;", ctx);
  return ctx;
}
function click(c, ds, inside){
  let prevented = false;
  const el = { dataset: ds, closest(sel){
    const keys = Object.keys(ds).map(k => "[data-" + k.toLowerCase() + "]");
    if (sel === ".dp" || sel === ".wb") return inside === false ? null : el;
    return sel.split(",").some(s => keys.indexOf(s.trim()) >= 0) ? el : null;
  } };
  const ev = { target: el, preventDefault(){ prevented = true; }, stopPropagation(){} };
  (c.document.listeners.click || []).forEach(fn => fn(ev));
  return prevented;
}
async function opened(opts){
  const c = fresh(opts);
  vm.runInContext("dpS().sel = 'r3'; dpS().tab['r3'] = 'now';", c);
  c.wbList(WEB);
  await sleep(); await sleep();
  c.wbList(WEB); c.wbViewer(WEB);
  await sleep(); await sleep();
  return c;
}
const list = c => { const l = c.wbList(WEB); return l.top + l.engines + l.filed; };
const view = c => c.wbViewer(WEB);

/* ── W1 ─────────────────────────────────────────────────────────────────── */
test("W1: no global of 22-website.js is a global of any other script", () => {
  const mine = new Set();
  let m;
  const re = /^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^const\s+([A-Za-z_$][\w$]*)/gm;
  while ((m = re.exec(wbSrc))) mine.add(m[1] || m[2]);
  assert.ok(mine.size > 30, "parsed " + mine.size + " globals");
  [...mine].forEach(n => assert.ok(/^(wb[A-Z]|WB_)/.test(n), n + " is not prefixed wb / WB_"));
  fs.readdirSync(JS).filter(f => /\.js$/.test(f) && f !== "22-website.js").forEach(f => {
    const src = read(f);
    assert.ok(!/\bS\.wb\b/.test(src), f + " reads S.wb");
    const theirs = /^(?:async\s+)?function\s+(wb[A-Z]\w*)|^const\s+(WB_\w+)/gm;
    assert.ok(!theirs.test(src), f + " declares a wb global");
  });
  assert.ok(!/\bS\.ws\b|\bws[A-Z]\w*\(/.test(wbSrc), "22-website.js still touches the Workspace's names");
});

/* ── W2 ─────────────────────────────────────────────────────────────────── */
test("W2: a department with no website record paints exactly as before", async () => {
  const c = fresh({ none: true });
  c.wbList(OTHER);
  await sleep(); await sleep();
  assert.strictEqual(c.wbList(OTHER), null);
  assert.strictEqual(c.wbViewer(OTHER), null);
  assert.strictEqual(c.wbTileMark("r4"), "");
  const html = c.dpListHtml(OTHER, {}, null, null);
  assert.ok(/data-dptab="now"/.test(html) && !/data-wbtab/.test(html));
  assert.ok(/^<div class="o2viewer dpviewer dp"/.test(c.dpViewerHtml(OTHER, {}, null, null)));
});

/* ── W3 ─────────────────────────────────────────────────────────────────── */
test("W3: the list carries Map, System status, Motor, the engines and the filed work", async () => {
  const c = await opened();
  const html = c.dpListHtml(WEB, {}, null, null);
  ["Map", "System status", "Motor"].forEach(n => assert.ok(html.indexOf("<span>" + n + "</span>") >= 0, n));
  assert.ok(!/data-dptab="now"/.test(html), "Now is replaced by System status");
  ["identity", "adaptation", "priority", "coordination", "audit"].forEach(f => assert.ok(html.indexOf('data-dptab="' + f + '"') >= 0, f));
  ENGS.forEach(e => assert.ok(html.indexOf('data-wbengine="' + e[0] + '"') >= 0, e[0]));
  assert.ok(/data-wbart="pages"[^>]*><span>Pages<\/span><span class="dpdots">/.test(html), "Pages carries version dots");
  assert.ok(!/data-wbart="live-site"/.test(html), "nothing filed is not listed");
  assert.ok(/<span>Map<\/span>/.test(html) && /o2li dpli on" data-wbtab="map"/.test(html), "Map opens without a click");
});

/* ── W4 ─────────────────────────────────────────────────────────────────── */
test("W4: before a goal the Map asks for one, and Start posts it", async () => {
  const c = await opened({ map: mapOf({ has_goal: false, versions: { "Brief": 0, "Site plan": 0, "Pages": 0, "Build": 0, "Live site": 0 } }) });
  const html = view(c);
  assert.ok(/<h3>Goal<\/h3>/.test(html) && /data-wbgoal="goal"/.test(html) && />Start</.test(html));
  assert.ok(!/<h3>System status<\/h3>/.test(html));
  assert.ok(/<textarea id="wbd-goal"/.test(html), "the box has an id, so render() keeps its focus and words");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:goal" }, value: "A website for City Care Hospital" } }));
  assert.ok(click(c, { wbgoal: "goal" }));
  await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[0])), { p: "/api/native/r3/goal", body: { text: "A website for City Care Hospital" } });
});

/* ── W5 ─────────────────────────────────────────────────────────────────── */
test("W5: with a goal the Map shows the department, System status, Ask, Health and Recent", async () => {
  const c = await opened({ map: mapOf({ ask: true }) });
  const html = view(c);
  ["The department", "System status", "Ask", "Health", "Recent"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  ["Identity", "Adaptation", "Priority", "Coordination", "Audit"].forEach(s => assert.ok(html.indexOf('data-wbfn="' + s.toLowerCase() + '"') >= 0, s));
  assert.strictEqual((html.match(/class="wbflow"/g) || []).length, 2, "two engines to a row");
  assert.ok(/data-wbdecide="a-1" data-wbok="1">Stamp</.test(html) && /data-wbdecide="a-1" data-wbok="0">Say no</.test(html), "the ask's two answers, in the owner's words: Stamp and Say no");
  assert.ok(!/>Refuse</.test(html), "never Refuse (the owner's ruling on the screen's words)");
  assert.ok(/data-wbstop="1">Stop</.test(html));
  assert.ok(/data-wbmotor="1"/.test(html), "the motor's dot is on the map");
  const stopped = await opened({ map: mapOf({ stopped: true }) });
  assert.ok(/data-wbresume="1">Resume</.test(view(stopped)));
});

/* ── W6 ─────────────────────────────────────────────────────────────────── */
test("W6: Stamp, Stop, Ask and Put back each post the one route they name", async () => {
  const c = await opened({ map: mapOf({ ask: true }) });
  click(c, { wbdecide: "a-1", wbok: "1" }); await sleep(); await sleep();
  click(c, { wbstop: "1" }); await sleep(); await sleep();
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Add a Careers page" } }));
  click(c, { wbask: "ask" }); await sleep(); await sleep();
  click(c, { wbputback: "live-site", wbv: "1" }); await sleep(); await sleep();
  const posts = JSON.parse(JSON.stringify(c.calls.apiPost));
  assert.deepStrictEqual(posts, [
    { p: "/api/native/r3/asks/a-1", body: { approve: true } },
    { p: "/api/native/r3/stop", body: {} },
    { p: "/api/native/r3/ask", body: { text: "Add a Careers page" } },
    { p: "/api/native/r3/putback", body: { slug: "live-site", v: 1 } }]);
});

/* ── W7 ─────────────────────────────────────────────────────────────────── */
test("W7: a click on one of 20-dept.js's rows hands the viewer back, and its card carries this department's state first", async () => {
  const c = await opened();
  const card = async tab => { click(c, { dptab: tab }); c.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 6; i++) await sleep(); return c.dpViewerHtml(WEB, {}, null, null); };
  let html = await card("priority");
  assert.strictEqual(vm.runInContext("S.wb.tab['r3']", c), "");
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "priority");
  assert.strictEqual(c.wbViewer(WEB), null, "20-dept.js draws its own card");
  /* PRD M4.6 (S-05): Priority prices and holds; the queue is Coordination's card */
  assert.ok(/<h3>Envelopes<\/h3>/.test(html) && !/<h3>Queue<\/h3>/.test(html), html.slice(0, 400));
  html = await card("coordination");
  ["Timetable", "Queue", "Hand-offs", "Locks"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  html = await card("identity");
  ["Control", "Autonomy windows", "Stamped by rule"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  html = await card("audit");
  assert.ok(/Paused/.test(html));
  assert.strictEqual(c.wbFnOwn("r4", "priority"), "", "another department's card gains nothing");
  click(c, { wbtab: "motor" });
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "now", "no function row stays lit");
  const motor = view(c);
  ["Motor", "It only reads", "What it does each tick", "Checks", "Timeline", "Never happens"].forEach(h => assert.ok(motor.indexOf("<h3>" + h + "</h3>") >= 0, h));
  const words = motor.replace(/<[^>]+>/g, " ").replace(/\b\d\d:\d\d\b/g, " ");
  assert.ok(!/\d/.test(words), "a number at rest on the Motor: " + (words.match(/.{0,30}\d.{0,30}/) || [""])[0]);
});

/* ── W8 ─────────────────────────────────────────────────────────────────── */
test("W8: Preview shows the thing itself in a frame that can run nothing", async () => {
  const c = await opened({ map: mapOf({ live: true, versions: { "Brief": 1, "Site plan": 1, "Pages": 1, "Build": 1, "Live site": 2 } }) });
  click(c, { wbart: "live-site", wbpane: "preview" });
  view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<iframe class="wbframe" sandbox="" src="\/api\/native\/r3\/site\/index\.html"/.test(html), html.slice(0, 300));
  ["The work item", "Preview", "Versions", "Trace"].forEach(t => assert.ok(html.indexOf(">" + t + "</button>") >= 0, t));
  click(c, { wbpane: "versions", wbpanekey: "r3:live-site" });
  const vs = view(c);
  assert.ok(/<span class="dpk">From<\/span><span class="wbchip">Build/.test(vs), "each version says what it was made from");
  assert.strictEqual((vs.match(/data-wbputback="live-site"/g) || []).length, 1, "only an earlier version can be put back");
});

/* ── W9 ─────────────────────────────────────────────────────────────────── */
test("W9: the screen prints no count and no path at rest", async () => {
  const c = await opened({ map: mapOf({ ask: true, live: true }) });
  const text = h => h.replace(/<[^>]+>/g, " ").replace(/\b\d\d:\d\d\b/g, " ");
  [c.dpListHtml(WEB, {}, null, null), view(c)].forEach(h => {
    const t = text(h);
    assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
    assert.ok(!/\/api\/|\.json|\.html|\bv\d/.test(t), "a path or a version number in the words");
    assert.ok(!/charter/i.test(t), "the word charter on a card");
  });
});

/* ── W10 ────────────────────────────────────────────────────────────────── */
test("W10: the Edit menu carries the command, and panel.html loads the script before the tail", () => {
  const c = fresh();
  assert.ok(/data-wbfound="open">New organisation…<\/button>/.test(c.o2MenuHtml(WEB, c.o2Data())));
  const a = panelHtml.indexOf("/static/js/22-website.js"), b = panelHtml.indexOf("/static/js/09-tail.js"), d = panelHtml.indexOf("/static/js/20-dept.js");
  assert.ok(d >= 0 && a > d && b > a);
});
test("W10b: the command founds the organisation with its Root, hands Root the first department's words, and opens Root", async () => {
  const c = fresh();
  click(c, { wbfound: "open" }, false);
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbfield: "org" }, value: "City Care Hospital" } }));
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbfield: "goal" }, value: "A website for the hospital" } }));
  click(c, { wbfound: "go" }, false);
  for (let i = 0; i < 8; i++) await sleep();
  const posts = JSON.parse(JSON.stringify(c.calls.apiPost));
  assert.deepStrictEqual(posts.slice(0, 1), [
    { p: "/api/native/found", body: { org: "City Care Hospital", first: "A website for the hospital" } }], "one route, nothing founded the old way");
  assert.strictEqual(vm.runInContext("o2S().sel", c), "r2", "Root is where the person goes on");
});

/* ── W11 ────────────────────────────────────────────────────────────────── */
test("W11: the stylesheet block is tokens only and covers what the script emits", () => {
  const i = css.indexOf("/* ── the website department (22-website.js) ");
  assert.ok(i > 0, "the block exists");
  const block = css.slice(i);
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block), "a literal colour");
  const classes = new Set();
  let m;
  const re = /\bwb[a-z0-9]+\b/g;
  const emitted = wbSrc.replace(/data-wb[a-z]+/g, "").replace(/\bds\.wb[a-z]+/g, "").replace(/"wb(found|forg|fgoal)"/g, "");
  while ((m = re.exec(emitted))) classes.add(m[0]);
  classes.delete("wb");
  [...classes].forEach(k => assert.ok(block.indexOf("." + k) >= 0, "no rule for ." + k));
});

/* ── the engine runtime ─────────────────────────────────────────────────── */
const words = h => h.replace(/<[^>]+>/g, " ").replace(/\b\d\d:\d\d\b/g, " ");
/* a department's turn in its chat is Identity's, signed with Identity's mark and the department's name (PRD M3.6, S15) */
const SIGNED = '<div class="who who-ai"><svg class="dpfnmk fn-identity" viewBox="0 0 24 24"[^>]*>(?:(?!</div>)[\\s\\S])*?</svg>City Care Hospital Website</div>';
const rtMap = o => mapOf(Object.assign({ runtime: 2, live: true }, o || {}));
const readsOf = (c, re) => c.calls.apiGet.filter(p => re.test(p));
async function fnCard(c, tab){
  click(c, { dptab: tab });
  for (let k = 0; k < 3; k++){ c.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 6; i++) await sleep(); }
  return c.dpViewerHtml(WEB, {}, null, null);
}

test("W12: a department on the engine runtime gains the Board; one that is not reads neither steps nor board", async () => {
  const c = await opened({ map: rtMap() });
  assert.ok(/data-wbtab="board"><span>Board<\/span>/.test(list(c)), "the Board is in the list");
  const old = await opened();
  assert.ok(!/data-wbtab="board"/.test(list(old)), "a department of the first build has no Board");
  click(old, { wbengine: "Write" }); view(old); await sleep(); await sleep();
  const html = view(old);
  assert.ok(!/>Steps<\/button>/.test(html) && />Engine<\/button>/.test(html), "its engine card is the one it had");
  click(old, { wbtab: "board" });
  const back = view(old);
  assert.ok(/<div class="o2vh"><b>Map<\/b>/.test(back) && !/class="wbth/.test(back), "and a Board that is asked for falls back to the Map");
  ["identity", "adaptation", "audit"].forEach(f => old.wbFnOwn("r3", f));
  await sleep();
  assert.deepStrictEqual(readsOf(old, /\/steps\/|\/board$/), [], "no read of the runtime's routes");
  assert.ok(/Paused/.test(old.wbFnOwn("r3", "audit")), "Audit says Paused, as before");
});

test("W13: an engine opens on its steps, each with its rung, its check, what its rows say and Hold", async () => {
  const c = await opened({ map: rtMap(), steps: { moved: true } });
  click(c, { wbengine: "Write" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.deepStrictEqual(readsOf(c, /\/steps\//), ["/api/native/r3/steps/Write"]);
  ["Steps", "Engine", "Runs"].forEach(t => assert.ok(html.indexOf(">" + t + "</button>") >= 0, t));
  assert.ok(/aria-pressed="true" data-wbpanekey="r3:Write" data-wbpane="steps"/.test(html), "Steps is the pane it opens on");
  ["List the pages", "Write a page", "Put the pages together"].forEach(s => assert.ok(html.indexOf(s) >= 0, s));
  const row = name => html.slice(html.indexOf(name), html.indexOf("</div></div>", html.indexOf(name)) < 0 ? undefined : html.indexOf(name) + 1400);
  const page = row("Write a page");
  assert.ok(/<span class="wbrung" title="Improvised call"><i class="on"><\/i><i class="on"><\/i><i><\/i><i><\/i><\/span>/.test(page), "two of four pips lit");
  assert.ok(/<span class="wbchip">Improvised call<\/span>/.test(page) && /<span class="wbchip">Side by side<\/span>/.test(page));
  assert.ok(/the page has a body/.test(page), "what its check last said");
  assert.ok(/<span class="dpk">Passing<\/span><div class="dpbar"><i style="width:90%">/.test(page), "its pass rate is a bar");
  assert.ok(/<span class="dpk">To the next rung<\/span><div class="dpbar"><i style="width:25%">/.test(page), "and how far it is from the next rung");
  assert.ok(/data-wbhold="write\.page" data-wbheld="1">Hold</.test(page));
  const code = row("List the pages");
  assert.ok(/<span class="wbchip on">Code<\/span>/.test(code.slice(0, 600)) && !/To the next rung/.test(code.slice(0, html.indexOf("Write a page") - html.indexOf("List the pages"))),
    "a step that is code has nowhere to climb");
  assert.ok(/<span class="dpdot off"><\/span><span>Put the pages together<div class="dpchk">filed has files<\/div>/.test(html), "a step that never ran says which check it names");
  assert.ok(/<h3>Moves<\/h3>/.test(html) && /Improvised call to Checklist · the owner's stamp/.test(html), "a rung that moved says from, to and by whom");
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(!/write\.(list|page|file)|page_has_body|\bC[0-3]\b|\/api\//.test(t), "a step id, a check id, a rung code or a path in the words");
  const marks = await opened({ map: rtMap(), steps: { held: true, trial: { rung: "C1" }, pending: { to: "C1" } } });
  click(marks, { wbengine: "Write" }); view(marks); await sleep(); await sleep();
  const mh = view(marks);
  ["On trial", "Waits for your stamp", "Held"].forEach(w => assert.ok(mh.indexOf(">" + w + "</span>") >= 0, w));
  assert.ok(/data-wbhold="write\.page" data-wbheld="0">Let go</.test(mh), "a held step can be let go");
});

test("W14: Hold posts the one route it names, and the card that is open stays open", async () => {
  const c = await opened({ map: rtMap() });
  assert.ok(/data-wbhold="identity\.read" data-wbheld="1">Hold</.test(await fnCard(c, "identity")), "Hold is on the function's card");
  assert.ok(click(c, { wbhold: "identity.read", wbheld: "1" }));
  await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/native/r3/hold", body: { step: "identity.read", held: true } }]);
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "identity", "the function's card is still the one open");
  click(c, { wbhold: "identity.read", wbheld: "0" });
  await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[1])), { p: "/api/native/r3/hold", body: { step: "identity.read", held: false } });
  assert.ok(readsOf(c, /\/steps\/Identity$/).length >= 2, "and its steps are read again after the post");
});

test("W15: the Board is a list of threads and the open one as a chat: who spoke to whom and with which act; the ideas parked", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbtab: "board" }); view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<div class="o2vh"><b>Board<\/b>/.test(html));
  assert.strictEqual((html.match(/class="wbthr wb/g) || []).length, 2, "one row to a thread");
  assert.ok(html.indexOf("A rule, as understood") < html.indexOf("Which page lists the doctors?"), "newest thread first");
  assert.ok(/class="wbthr wb on" data-wbthread="x-2"><span class="dpdot warn"><\/span><span class="wbwho"><span class="wbchip">Identity<\/span><\/span><span class="dpst">Waits for you<\/span><b>A rule, as understood: every page names a phone line<\/b>/.test(html),
    "the newest is open: its dot, who spoke, its state, its first line");
  assert.ok(/class="wbthr wb" data-wbthread="x-1"><span class="dpdot ok"><\/span>[\s\S]*?<span class="dpst">Done<\/span><b>Which page lists the doctors\?<\/b>/.test(html));
  assert.ok(/<div class="who who-ai">Identity <span class="wbarrow">&rarr;<\/span> Owner<\/div><div class="a">A rule, as understood: every page names a phone line<span class="dpchk">asks · /.test(html),
    "the open thread is turns: who, to whom, the act in a word");
  click(c, { wbthread: "x-1" });
  html = view(c);
  assert.ok(/class="wbthr wb on" data-wbthread="x-1"/.test(html) && !/class="wbthr wb on" data-wbthread="x-2"/.test(html), "another thread opens");
  assert.ok(/<div class="who who-you">You<\/div><div class="u md">Which page lists the doctors\?<span class="dpchk">asks · /.test(html), "the owner on the right");
  assert.ok(/<div class="who who-ai">Identity <span class="wbarrow">&rarr;<\/span> Owner<\/div><div class="a">The Doctors page lists them<span class="dpchk">tells · /.test(html), "the department on the left");
  assert.ok(!/A rule, as understood: every page names a phone line<span class="dpchk">/.test(html), "one thread open at a time");
  assert.ok(/<h3>Ideas, parked<\/h3>/.test(html) && /A place where patients sign in/.test(html) && /<span class="wbchip">A sign-in of its own<\/span>/.test(html));
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(!/accept-proposal|input-required|msg_type|\bx-\d|\/api\//.test(t), "a protocol word or an id in the words");
  const empty = await opened({ map: rtMap(), board: { any: false, threads: [], ideas: [] } });
  click(empty, { wbtab: "board" }); view(empty); await sleep(); await sleep();
  assert.ok(/Nothing has been said yet/.test(view(empty)));
});

test("W16: the Map of a runtime department has one way in, shows what was said back, and a function's card carries its steps", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbtab: "map" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<h3>Say<\/h3>/.test(html) && /data-wbask="ask"[^>]*>Send</.test(html) && !/<h3>Ask<\/h3>/.test(html), "one box, one button");
  assert.strictEqual((html.match(/<textarea/g) || []).length, 1, "and no second way in");
  assert.ok(/<h3>Replies<\/h3>/.test(html), "what the department said back is on the Map");
  const replies = html.slice(html.indexOf("<h3>Replies</h3>"), html.indexOf("<h3>Health</h3>"));
  assert.ok(replies.indexOf("A rule, as understood") < replies.indexOf("The Doctors page lists them") && replies.indexOf("A rule, as understood") > 0, "newest first");
  assert.ok(!/Which page lists the doctors/.test(replies), "the owner's own words are not a reply");
  assert.ok(!/Paused/.test(html), "no function is paused: " + (html.match(/.{0,60}Paused.{0,20}/) || [""])[0]);
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Which page lists the doctors?" } }));
  click(c, { wbask: "ask" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/native/r3/ask", body: { text: "Which page lists the doctors?" } }],
    "every kind of words goes through the one route");
  let fn = await fnCard(c, "audit");
  assert.ok(!/Paused/.test(fn) && /<h3>Gates<\/h3>/.test(fn) && /<h3>Take a request<\/h3>/.test(fn), "Audit is an engine: its gate, and its steps under what it hears");
  fn = await fnCard(c, "adaptation");
  assert.ok(/<h3>Ideas, parked<\/h3>/.test(fn), "Adaptation carries the ideas it parked");
  fn = await fnCard(c, "identity");
  ["Control", "Autonomy windows", "Gates", "Take a request"].forEach(h => assert.ok(fn.indexOf("<h3>" + h + "</h3>") >= 0, h));
});

test("W17: a runtime department has one button, Start when it is off and Stop when it is on", async () => {
  const on = await opened({ map: rtMap() });
  click(on, { wbtab: "map" });
  let html = view(on);
  assert.strictEqual((html.match(/data-wbstop="1"/g) || []).length, 1, "one Stop, and only one");
  assert.ok(!/data-wbresume/.test(html) && !/>Resume</.test(html));
  const first = html.slice(0, html.indexOf("<h3>System status</h3>"));
  assert.ok(/<span>On<\/span><button type="button" class="btn wb wbonoff" data-wbstop="1">Stop<\/button>/.test(first), "at the top, beside its state: " + first.slice(0, 400));
  assert.ok(!/>Motor</.test(first) && !/Stopped/.test(first), "its state is one word, On or Off");
  click(on, { wbstop: "1" }); await sleep(); await sleep();
  const off = await opened({ map: rtMap({ stopped: true }) });
  click(off, { wbtab: "map" });
  html = view(off);
  assert.ok(/<span class="dpdot off"><\/span><span>Off<\/span><button type="button" class="btn wb wbonoff dpstamp" data-wbresume="1">Start<\/button>/.test(html), html.slice(0, 500));
  assert.strictEqual((html.match(/data-wbresume="1"/g) || []).length, 1);
  click(off, { wbresume: "1" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify([on.calls.apiPost[0], off.calls.apiPost[0]])),
    [{ p: "/api/native/r3/stop", body: {} }, { p: "/api/native/r3/resume", body: {} }]);
  click(off, { wbtab: "status" });
  assert.ok(/data-wbresume="1">Start</.test(view(off)), "System status carries the same button");
  const old = await opened({ map: mapOf({ stopped: true }) });
  assert.ok(/data-wbresume="1">Resume</.test(view(old)) && !/wbonoff/.test(view(old)), "a department of the first build keeps its own");
});

test("W18: every engine's card says how it starts, and Coordination's card carries its table", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbengine: "Write" }); view(c); await sleep(); await sleep();
  const html = view(c);
  const starts = html.slice(html.indexOf("<h3>Starts</h3>"), html.indexOf("<h3>Steps</h3>"));
  assert.ok(/<span class="dpk">On<\/span><span class="wbchip on">A new Site plan<\/span>/.test(starts), starts.slice(0, 300));
  assert.ok(/<span class="dpk">Unless<\/span><span class="wbchip ask">Identity: Say whether it may start<\/span><span class="wbchip ask">Priority: Keep it inside its envelope<\/span>/.test(starts));
  assert.ok(!/Who goes first/.test(html), "only Coordination carries the table");
  const fn = await fnCard(c, "identity");
  assert.ok(/<h3>Starts<\/h3>/.test(fn) && /A post addressed to it/.test(fn) && /<span class="wbchip">Nothing holds it<\/span>/.test(fn));
  const co = await fnCard(c, "coordination");
  ["Starts", "Who goes first", "Who may post to whom", "What engines share"].forEach(h => assert.ok(co.indexOf("<h3>" + h + "</h3>") >= 0, h));
  assert.ok(/<span class="dpk">The line<\/span><span class="wbchip">Plan<\/span><span class="wbarrow">&rarr;<\/span><span class="wbchip">Write<\/span>/.test(co));
  assert.ok(/<span class="wbchip">Audit<\/span><span class="dpchk">tells<\/span><span class="wbchip">Identity<\/span>/.test(co), "who, the act in a word, to whom");
  assert.ok(co.indexOf("<h3>What engines share</h3>") < co.indexOf("<h3>Take a request</h3>"), "what engines share comes before what it hears");
  [html, co].forEach(h => {
    const t = words(h);
    assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
    assert.ok(!/coord\.|identity\.|write\.|names_who|\/api\//.test(t), "an id or a path in the words");
  });
});

test("W19: on the screen the five are functions; 'internal system' is printed nowhere", async () => {
  const c = await opened({ map: rtMap() });
  const seen = [c.dpListHtml(WEB, {}, null, null), view(c)];
  click(c, { wbtab: "board" }); view(c); await sleep(); await sleep(); seen.push(view(c));
  click(c, { wbengine: "Write" }); view(c); await sleep(); await sleep(); seen.push(view(c));
  for (const f of ["identity", "adaptation", "priority", "coordination", "audit"]) seen.push(await fnCard(c, f));
  assert.strictEqual(seen.length, 9);
  seen.forEach((h, i) => assert.ok(!/internal\s+system/i.test(h), "the inside word is on the screen, in view " + i + ": " + (h.match(/.{0,60}internal\s+system.{0,40}/i) || [""])[0]));
  const pr = await fnCard(c, "priority");
  assert.ok(/<h3>The function<\/h3><div class="dpbig">Grants each engine its budget<\/div>/.test(pr), "a function's own card is titled The function");
  assert.ok(/<span>A function woken by new work<\/span>|A function woken by new work/.test(await fnCard(c, "coordination")));
  assert.ok(!/internal\s+system/i.test(wbSrc.replace(/\/\*[\s\S]*?\*\//g, "")), "nor in any string of the script");
});

test("W20: Human Sutra is an app in the list; it shows the department as one conversation in time order, the asks inline, the functions' exchanges folded, one way in", async () => {
  const c = await opened({ map: rtMap({ ask: true }) });
  const lst = c.dpListHtml(WEB, {}, null, null);
  assert.ok(/data-wbtab="conversation"><span>Human Sutra<\/span>/.test(lst), "the app is listed");
  assert.ok(/>Apps<\/div>[\s\S]{0,300}Human Sutra/.test(lst), "under Apps");
  click(c, { wbtab: "conversation" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<div class="o2vh"><b>Human Sutra<\/b>/.test(html), "the app opens");
  const i1 = html.indexOf("Which page lists the doctors?"), i2 = html.indexOf("The Doctors page lists them"), i3 = html.indexOf("A rule, as understood");
  assert.ok(i1 > 0 && i1 < i2 && i2 < i3, "oldest first, newest at the bottom: " + [i1, i2, i3]);
  assert.ok(/class="wbline wb me">/.test(html), "the owner's own line is marked");
  assert.ok(/<h3>Waiting for you<\/h3>/.test(html) && /Publish: go live for the first time/.test(html) &&
    /data-wbdecide="a-1" data-wbok="1"/.test(html) && /data-wbdecide="a-1" data-wbok="0"/.test(html), "an ask is a line with its buttons");
  assert.strictEqual((html.match(/<textarea/g) || []).length, 1, "one way in");
  assert.ok(/<h3>Say<\/h3>/.test(html) && /data-wbask="ask"[^>]*>Send</.test(html), "and it is Say");
  assert.ok(!/internal\s+system/i.test(html));
  const old = await opened();
  assert.ok(!/Human Sutra/.test(old.dpListHtml(WEB, {}, null, null)), "a department of the first build has no app");
  const b2 = JSON.parse(JSON.stringify(BOARD));
  b2.threads.unshift({ id: "x-3", topic: "trial", protocol: "propose", state: "completed", decider: "Priority", opened: AT, closed: AT,
    outcome: { by: "accept-proposal" }, bounds: { hops: 4, seconds: 900, usd: 0.5 }, hops: 2, default: "failure", posts: [
      { n: 4, src: "Adaptation", dst: ["Priority"], msg_type: "propose", at: AT, word: "trial", line: "one more call a run, for 2 runs" },
      { n: 5, src: "Priority", dst: ["Adaptation"], msg_type: "accept-proposal", at: AT, word: "trial", line: "Room in today's envelope covers it" }] });
  const f = await opened({ map: rtMap(), board: b2 });
  click(f, { wbtab: "conversation" }); view(f); await sleep(); await sleep();
  const h2 = view(f);
  assert.ok(/<details class="wbfold wb"><summary>[\s\S]*?Adaptation[\s\S]*?Priority[\s\S]*?one more call a run[\s\S]*?<\/summary>/.test(h2), "the functions' own exchange folds under the line that started it");
  assert.ok(h2.indexOf("The Doctors page lists them") < h2.indexOf("<details") && h2.indexOf("<details") < h2.indexOf("Room in today"), "and sits in time order");
  assert.ok(/<h3>Say<\/h3>/.test(h2) && !/<h3>Waiting for you<\/h3>/.test(h2), "nothing waits, so no empty card");
});

test("W21: Priority's card carries the limits, born from its template, and Set posts the owner's own for one engine", async () => {
  const c = await opened({ map: rtMap() });
  const pr = await fnCard(c, "priority");
  assert.ok(/<h3>Limits<\/h3>/.test(pr), "the card is there");
  assert.ok(/data-wbdraft="r3:env:Write:calls"[^>]*value="240"/.test(pr) && /data-wbdraft="r3:env:Write:usd"[^>]*value="6"/.test(pr), "each engine's two numbers");
  assert.ok(/data-wbdraft="r3:env:Audit:calls"[^>]*value="30"/.test(pr), "the functions too");
  assert.ok(/data-wbenv="Write"/.test(pr), "and a Set an engine");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:env:Write:usd" }, value: "3" } }));
  click(c, { wbenv: "Write" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/native/r3/envelope", body: { engine: "Write", usd: 3 } }],
    "only what was typed is sent, for that engine");
  const old = await opened();
  assert.ok(!/<h3>Limits<\/h3>/.test(await fnCard(old, "priority")), "a department of the first build keeps its card");
});

test("W22: a Root is a department on the screen: its one engine, Setup; Say asks Root for a department; no goal box; the app", async () => {
  const m = rtMap();
  m.kind = "root"; m.say = "Ask Root for a department: what it is for"; m.has_goal = true; m.live = false;
  m.engines = [{ name: "Setup", reads: "Request", writes: "Department", runs_as: "model", slot: "after a new Request", state: "Idle",
                 envelope: { calls: 240, usd: 6, used_calls: 0, used_usd: 0 }, window_min: 15, last: null }];
  m.artifacts = [{ name: "Request", slug: "request", versions: 1, latest: null }, { name: "Department", slug: "department", versions: 0, latest: null }];
  const c = await opened({ map: m });
  click(c, { wbtab: "map" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/data-wbengine="Setup"/.test(html) && !/data-wbengine="Plan"/.test(html), "Root's line is Setup alone");
  assert.ok(/placeholder="Ask Root for a department: what it is for"/.test(html), "Say speaks to Root");
  assert.ok(!/What is this website for\?/.test(html), "a Root is born with its goal: no goal box");
  assert.ok(!/Open the live site/.test(html), "nothing to open live");
  const lst = c.dpListHtml(WEB, {}, null, null);
  assert.ok(/data-wbengine="Setup"/.test(lst) && /Human Sutra/.test(lst) && /data-wbart="request"/.test(lst), "the list: Setup, the Request filed, the app");
});

test("W23: a Root that has not been asked for anything says so, and what to say; once asked, the line is gone", async () => {
  const m = rtMap();
  m.kind = "root"; m.say = "Ask Root for a department: what it is for"; m.has_goal = true; m.live = false;
  m.engines = [{ name: "Setup", reads: "Request", writes: "Department", runs_as: "model", slot: "after a new Request", state: "Idle",
                 envelope: { calls: 240, usd: 6, used_calls: 0, used_usd: 0 }, window_min: 15, last: null }];
  m.artifacts = [{ name: "Request", slug: "request", versions: 0, latest: null }, { name: "Department", slug: "department", versions: 0, latest: null }];
  const c = await opened({ map: m });
  click(c, { wbtab: "map" }); view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<h3>Departments<\/h3>[\s\S]{0,80}No department yet\. Say what the first one is for\./.test(html), "the empty state names the action");
  const m2 = JSON.parse(JSON.stringify(m)); m2.artifacts[0].versions = 1;
  const c2 = await opened({ map: m2 });
  click(c2, { wbtab: "map" }); view(c2); await sleep(); await sleep();
  html = view(c2);
  assert.ok(!/No department yet/.test(html), "asked once, the line is gone");
  const w = await opened({ map: rtMap() });
  click(w, { wbtab: "map" }); view(w); await sleep(); await sleep();
  assert.ok(!/No department yet/.test(view(w)), "a website department never says it");
  /* the chat says it too, on a Root with nothing yet, and nowhere else */
  const e = await opened({ map: m, chat: { root: "r3", about: null, turns: [], asks: [], departments: [] } });
  view(e); await sleep(); await sleep();
  assert.ok(/No department yet\. Say what the first one is for\./.test(view(e)), "the chat of an empty Root");
  const f = await opened({ map: rtMap(), chat: { root: "r2", about: "r3", turns: [], asks: [], departments: [] } });
  view(f); await sleep(); await sleep();
  assert.ok(/Nothing has been said yet/.test(view(f)) && !/No department yet/.test(view(f)));
});

test("W24: a filed artifact shows its template: what it holds, its checks, who writes it, when it counts, what runs on a new one", async () => {
  const c = await opened({ map: rtMap() });
  click(c, { wbart: "live-site", wbpane: "item" }); view(c); await sleep(); await sleep();
  const html = view(c);
  assert.ok(/<h3>Template<\/h3>/.test(html), "the template card");
  assert.ok(/index\.html, \*\.html/.test(html) && /has_index_html/.test(html) && /Publish/.test(html), "holds, checks, written by");
  assert.ok(/After your stamp/.test(html), "when it counts");
  assert.ok(/Adaptation, Audit/.test(html), "its operations: the engines that run on a new one");
});

test("M1.2: who made a version and who reads it come from the record, never a table of names", async () => {
  assert.ok(!/wbMakerOf|wbReaderOf/.test(wbSrc + sxSrc), "the hard-coded maps are gone");
  const fv = fvOf({ made: [{ art: "Live site", slug: "live-site", v: 2, by: "Launch", makers: ["Launch"], by_v: { "1": "Launch", "2": "Launch" },
                              readers: ["Audit", "Adaptation"] }] });
  const c = await opened({ map: rtMap(), fv });
  click(c, { wbart: "live-site", wbpane: "item" });
  for (let k = 0; k < 3; k++){ view(c); await sleep(); await sleep(); }
  const html = view(c);
  assert.ok(/<div class="dpk">Made by<\/div><div class="dpbig">Launch<\/div>/.test(html), "the maker the run row names");
  assert.ok(/<div class="dpk">Read by<\/div><div class="dpbig">Audit, Adaptation<\/div>/.test(html), "the readers the definitions name");
  assert.deepStrictEqual(readsOf(c, /\/functions$/), ["/api/native/r3/functions"], "read once, from the functions read");
  /* a department of the first build has no functions read: its own engines' reads and writes, off its map */
  const old = await opened();
  click(old, { wbart: "live-site", wbpane: "item" });
  for (let k = 0; k < 3; k++){ view(old); await sleep(); await sleep(); }
  const oh = view(old);
  assert.ok(/<div class="dpk">Made by<\/div><div class="dpbig">Publish<\/div>/.test(oh) && /<div class="dpk">Read by<\/div><div class="o2quiet dpq">Nobody yet<\/div>/.test(oh), "the line on its map");
  assert.deepStrictEqual(readsOf(old, /\/functions$/), [], "never asked");
  /* a maker the record does not hold is said so, never guessed */
  const c2 = await opened({ map: rtMap(), fv: fvOf({ made: [{ art: "Live site", slug: "live-site", v: 2, by: null, makers: [], by_v: {}, readers: [] }] }) });
  click(c2, { wbart: "live-site", wbpane: "item" });
  for (let k = 0; k < 3; k++){ view(c2); await sleep(); await sleep(); }
  assert.ok(/<div class="dpk">Made by<\/div><div class="o2quiet dpq">Not recorded<\/div>/.test(view(c2)));
});

/* W25 (founder, 2026-09-28: "I don't see artifacts in the library"): every artifact a
   website department files, and the app it runs, is a template on the Library's
   Artifacts shelf, and the shelf is a Library screen the Org rail lists. */
test("W25b: every artifact the website kind files has a template on the Library's Artifacts shelf", () => {
  const dir = path.join(__dirname, "artifact-templates");
  const names = fs.readdirSync(dir).filter(f => /\.json$/.test(f))
    .map(f => JSON.parse(fs.readFileSync(path.join(dir, f), "utf8")).name);
  const kinds = JSON.parse(fs.readFileSync(path.join(__dirname, "engine_defs", "website.json"), "utf8")).kinds;
  for (const k of Object.keys(kinds)) for (const a of kinds[k].artifacts)
    assert.ok(names.indexOf(a) >= 0, "no template on the shelf for " + a + " (kind " + k + ")");
  assert.ok(names.indexOf("Human Sutra") >= 0, "the app is a template too");
  const lib = fs.readFileSync(path.join(__dirname, "static", "js", "21-library.js"), "utf8");
  const rail = fs.readFileSync(path.join(__dirname, "static", "js", "19-org2.js"), "utf8");
  assert.ok(/"artifacts"/.test(lib.split("LIB_SHELVES")[1] || ""), "the Library screen has the shelf");
  assert.ok(/\["lib-artifacts", "Artifacts"\]/.test(rail), "the Org rail lists it under Parts");
});

test("W25: the chat is the one point of entry: it opens first; inside a department it is scoped with the department as a chip; the words go to Root; a stamp goes where the ask lives; on Root the whole chat", async () => {
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m });
  assert.ok(/o2li dpli on" data-wbtab="chat"/.test(list(c)) && !/o2li dpli on" data-wbtab="map"/.test(list(c)), "Chat opens without a click");
  view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<div class="o2vh"><b>Chat<\/b>/.test(html));
  assert.deepStrictEqual(readsOf(c, /\/chat/), ["/api/native/r3/chat"], "one read, of the chat");
  assert.ok(/<div class="turn wbturn"><div class="who who-you">You<\/div><div class="u md">Which page lists the doctors\?<\/div><\/div>/.test(html), "the owner's turn, the chat's own markup");
  assert.ok(new RegExp(SIGNED + '<div class="a">The Doctors page lists them<span class="dpchk">tells · ').test(html),
            "the department speaks with one voice: Identity's mark and the department's name (PRD M3.6; Root keeps Root on its own chat)");
  assert.ok(!/<span class="wbchip">City Care Hospital Website<\/span>/.test(html), "inside the department, no chip on the turns");
  assert.ok(!/Set up a department/.test(html), "Root's own turns are not here");
  assert.ok(/<button type="button" class="wbchip on wbto wb" data-wbchip="off">to City Care Hospital Website &times;<\/button><textarea id="wbd-ask"/.test(html), "the box carries where you stand as a chip");
  assert.ok(/<h3>Waiting for you<\/h3>/.test(html) && /City Care Hospital Website · Publish/.test(html) && /data-wbdecide="a-1" data-wbok="1" data-wbref="r3"/.test(html), "an ask says where it lives");
  assert.strictEqual((html.match(/<textarea/g) || []).length, 1, "one way in");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Add a Careers page" } }));
  assert.ok(click(c, { wbask: "ask" })); await sleep(); await sleep();
  click(c, { wbchip: "off" });
  assert.ok(/<button type="button" class="wbchip wbto wb" data-wbchip="on">to Root<\/button>/.test(view(c)), "the chip taken off: the words go to Root alone");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Start a department for billing" } }));
  click(c, { wbask: "ask" }); await sleep(); await sleep();
  click(c, { wbdecide: "a-1", wbok: "1", wbref: "r3" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [
    { p: "/api/native/r2/ask", body: { text: "Add a Careers page", about: "r3" } },
    { p: "/api/native/r2/ask", body: { text: "Start a department for billing" } },
    { p: "/api/native/r3/asks/a-1", body: { approve: true } }], "to Root, about the department; to Root alone; the stamp where the ask lives");
  assert.ok(readsOf(c, /\/chat/).length >= 2, "and the chat is read again after a post");
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.say = "Ask Root for a department: what it is for"; rm.live = false;
  const r = await opened({ map: rm, chat: ROOT_CHAT });
  view(r); await sleep(); await sleep();
  html = view(r);
  assert.ok(/<div class="who who-ai">Root<button type="button" class="wbchip wbto wb" data-wbopen="r5">City Care Hospital Website<\/button><\/div><div class="a">The Doctors page lists them/.test(html), "on Root the department is a chip on the turn");
  assert.ok(/<div class="who who-you"><button type="button" class="wbchip wbto wb" data-wbopen="r5">City Care Hospital Website<\/button>You<\/div><div class="u md">Which page lists the doctors\?/.test(html), "on the owner's turn too");
  assert.ok(/<div class="who who-ai">Root<\/div><div class="a">Set up a department: City Care Hospital Website<span class="dpchk">asks · /.test(html), "Root's own turns, with no chip");
  assert.ok(/<div class="who who-you">You<\/div><div class="u md">Stamped<\/div>/.test(html), "a stamp is a turn with the act as its line, never an empty bubble");
  assert.ok(!/data-wbchip/.test(html) && /placeholder="Say it to Root, or name a department: City Care Hospital Website"/.test(html), "no chip on the box: Root is where you stand, and a department exists to name");
  assert.ok(/<span class="dpk">Departments<\/span><button type="button" class="wbchip wbto wb" data-wbopen="r5">City Care Hospital Website<\/button>/.test(html), "the departments under Root");
  assert.ok(/data-wbdecide="a-1" data-wbok="1" data-wbref="r5"/.test(html), "the department's ask, with where it lives");
  (r.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ask" }, value: "Stop City Care Hospital Website" } }));
  click(r, { wbask: "ask" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(r.calls.apiPost)), [{ p: "/api/native/r3/ask", body: { text: "Stop City Care Hospital Website" } }], "on Root the words go straight in");
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(!/\bx-\d|\/api\/|\br[0-9]\b/.test(t), "an id or a path in the words");
  const old = await opened();
  assert.ok(!/data-wbtab="chat"/.test(list(old)) && /o2li dpli on" data-wbtab="map"/.test(list(old)), "a department of the first build opens on its Map, as before");
});

test("W27: the department's own asks and answers are turns of the same chat: inside without a chip, on Root with its chip", async () => {
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m });
  view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(new RegExp(SIGNED + '<div class="a">say whether the site may go live for the first time<span class="dpchk">asks · ').test(html),
            "the department's own ask is a turn, no chip, signed by its Identity");
  assert.ok(/<div class="who who-you">You<\/div><div class="u md">Stamped<\/div>/.test(html), "and the owner's own stamp");
  const i1 = html.indexOf("say whether the site may go live"), i2 = html.indexOf("The Doctors page lists them");
  assert.ok(i1 > 0 && i2 > 0, "both boards' turns in one chat");
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.say = "Ask Root for a department: what it is for"; rm.live = false;
  const r = await opened({ map: rm, chat: ROOT_CHAT });
  view(r); await sleep(); await sleep();
  html = view(r);
  assert.ok(/<div class="who who-ai">Root<button type="button" class="wbchip wbto wb" data-wbopen="r5">City Care Hospital Website<\/button><\/div><div class="a">say whether the site may go live for the first time/.test(html), "on Root, the department's own ask carries its chip");
  assert.ok(/<div class="who who-you"><button type="button" class="wbchip wbto wb" data-wbopen="r5">City Care Hospital Website<\/button>You<\/div><div class="u md">Stamped<\/div>/.test(html), "so does its stamp");
});

test("W28: the department chip in Root's chat opens the department, and the tree learns of a Root-born department without a reload", async () => {
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.say = "Ask Root for a department: what it is for"; rm.live = false;
  const chat = JSON.parse(JSON.stringify(ROOT_CHAT));
  const r = await opened({ map: rm, chat });
  vm.runInContext("globalThis.__opened = null; o2Select = function(ref){ globalThis.__opened = ref; }; globalThis.__org = 0; loadOrg2 = function(){ globalThis.__org++; return Promise.resolve(); };", r);
  view(r); await sleep(); await sleep();
  const html = view(r);
  assert.ok(/<button type="button" class="wbchip wbto wb" data-wbopen="r5">City Care Hospital Website<\/button>/.test(html), "the chip on a turn is a button that names the department");
  assert.ok(/<span class="dpk">Departments<\/span><button type="button" class="wbchip wbto wb" data-wbopen="r5">/.test(html), "so is the chip under Departments");
  assert.ok(click(r, { wbopen: "r5" }));
  assert.strictEqual(vm.runInContext("globalThis.__opened", r), "r5", "clicking it opens the department");
  assert.strictEqual(vm.runInContext("globalThis.__org", r), 0, "the tree is not re-read while nothing is new");
  chat.departments.push({ ref: "r6", name: "City Care Hospital Newsletter", stopped: false });
  await r.wbLoadChat("r3", true); await sleep(); await sleep();
  assert.strictEqual(vm.runInContext("globalThis.__org", r), 1, "a department Root made since the tree was read re-reads the tree");
  await r.wbLoadChat("r3", true); await sleep();
  assert.strictEqual(vm.runInContext("globalThis.__org", r), 1, "once, not on every read");
});

test("W29: while a function runs the chat says so; the live turn carries Open the live site, which previews it, and from Root opens that department on it", async () => {
  const m = rtMap(); m.root = "r2";
  m.status.running = [{ engine: "Write", since: AT, what: "Pages from Site plan" }];
  const chat = JSON.parse(JSON.stringify(CHAT));
  chat.turns.push({ n: 9, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: null, word: "live", line: "Live site v1 is live.", dept: "r3", name: DEPT, own: true, link: "Live site" });
  const c = await opened({ map: m, chat });
  view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<div class="o2quiet dpq wbworking"><i class="wbbreath"><\/i>Write is working: Pages from Site plan<\/div><\/div>/.test(html), "the running function is a quiet line under the last turn, its mark breathing");
  assert.ok(/<div class="a">Live site v1 is live\. <button type="button" class="wbchip on wbto wb" data-wblive="r3">Open the live site<\/button>/.test(html), "the live turn carries the one button");
  assert.ok(click(c, { wblive: "r3" }));
  assert.strictEqual(vm.runInContext("[wbS().tab.r3, wbS().sel.r3, wbS().pane['r3:live-site']].join('|')", c), "art|live-site|preview", "inside, the button previews the Live site");
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.say = "Ask Root for a department: what it is for"; rm.live = false;
  const rchat = JSON.parse(JSON.stringify(ROOT_CHAT));
  rchat.turns.push({ n: 9, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: null, word: "live", line: "Live site v1 is live.", dept: "r5", name: DEPT, link: "Live site" });
  const r = await opened({ map: rm, chat: rchat });
  vm.runInContext("globalThis.__opened = null; o2Select = function(ref){ globalThis.__opened = ref; };", r);
  view(r); await sleep(); await sleep();
  html = view(r);
  assert.ok(!/is working/.test(html), "Root's chat says nothing of a run it does not have");
  assert.ok(/data-wbopen="r5">City Care Hospital Website<\/button><\/div><div class="a">Live site v1 is live\. <button type="button" class="wbchip on wbto wb" data-wblive="r5">Open the live site<\/button>/.test(html), "on Root the live turn carries the department and the button");
  assert.ok(click(r, { wblive: "r5" }));
  assert.strictEqual(vm.runInContext("globalThis.__opened", r), "r5", "from Root the button opens that department");
  assert.strictEqual(vm.runInContext("[wbS().tab.r5, wbS().sel.r5, wbS().pane['r5:live-site']].join('|')", r), "art|live-site|preview", "on its Live site");
});

test("W30: a department born since the list was read is read again once, and wears its own view when the read lands", async () => {
  const c = await opened({});
  let listed = [{ ref: "r3", name: "Website", stopped: false }];
  const asked = () => c.calls.apiGet.filter(p => p === "/api/native/depts").length;
  c.apiGet = (p) => { c.calls.apiGet.push(p); if (p === "/api/native/depts") return Promise.resolve({ depts: listed }); return new Promise(() => {}); };
  const before = asked();
  assert.strictEqual(c.wbIs("r9"), false, "unknown to the list read at load");
  assert.strictEqual(c.wbIs("r9"), false);
  await sleep();
  assert.strictEqual(asked(), before + 1, "the list is read again, once for that name, not on every ask");
  listed = listed.concat([{ ref: "r9", name: "Newsletter", stopped: false }]);
  vm.runInContext("wbS().refsMissed = {};", c);
  assert.strictEqual(c.wbIs("r9"), false, "still unknown until the second read lands");
  await sleep();
  assert.strictEqual(c.wbIs("r9"), true, "known once the read lands: the runtime view, no reload");
  assert.strictEqual(asked(), before + 2);
});

test("W31: the chat keeps its place across a paint, and moves to a turn only when one lands", async () => {
  const chat = JSON.parse(JSON.stringify(CHAT));
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m, chat });
  vm.runInContext(`globalThis.__moves = []; globalThis.__box = { scrollHeight: 2000, clientHeight: 400, scrollTop: 0, parentElement: null, addEventListener(){}, __wbKeep: false };
    globalThis.__last = { scrollIntoView(o){ globalThis.__moves.push(o); } };
    document.querySelector = (sel) => sel === ".wbchat" ? { parentElement: globalThis.__box, querySelector: () => globalThis.__last } : null;`, c);
  view(c); await sleep(); await sleep();
  assert.strictEqual(vm.runInContext("globalThis.__moves.length", c), 0, "a paint with no new turn moves nothing");
  vm.runInContext("wbS().scroll.r3 = 777;", c);
  view(c); await sleep(); await sleep();
  assert.strictEqual(vm.runInContext("globalThis.__box.scrollTop", c), 777, "the chat goes back where the person had it");
  chat.turns.push({ n: 30, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: null, word: "answer", line: "A new turn", dept: "r3", name: DEPT, own: true });
  await c.wbLoadChat("r3", true); await sleep();
  view(c); await sleep(); await sleep();
  assert.strictEqual(vm.runInContext("globalThis.__moves.length", c), 1, "a turn landed: the chat moves to it");
  assert.strictEqual(vm.runInContext("JSON.stringify(globalThis.__moves[0])", c), '{"block":"nearest"}');
});

test("W32: Root's box, once departments exist, invites words for one of them", async () => {
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.say = "Ask Root for a department: what it is for"; rm.live = false;
  const r = await opened({ map: rm, chat: ROOT_CHAT });
  view(r); await sleep(); await sleep();
  assert.ok(/placeholder="Say it to Root, or name a department: City Care Hospital Website"/.test(view(r)), "Root with a department");
  const none = JSON.parse(JSON.stringify(ROOT_CHAT)); none.departments = [];
  const r0 = await opened({ map: rm, chat: none });
  view(r0); await sleep(); await sleep();
  assert.ok(/placeholder="Ask Root for a department: what it is for"/.test(view(r0)), "Root with none yet: the kind's own words");
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m });
  view(c); await sleep(); await sleep();
  assert.ok(/placeholder="Say it to City Care Hospital Website"/.test(view(c)), "inside, with the chip on");
});

test("W33: the working line says how far along, and is gone when the department is Off", async () => {
  const m = rtMap(); m.root = "r2";
  m.status.running = [{ engine: "Write", since: AT, what: "page 3 of 8" }];
  const c = await opened({ map: m });
  view(c); await sleep(); await sleep();
  assert.ok(/Write is working: page 3 of 8<\/div>/.test(view(c)), "page n of m from the run row");
  const off = rtMap(); off.root = "r2"; off.stopped = true;
  off.status.running = [{ engine: "Write", since: AT, what: "page 3 of 8" }];
  const c2 = await opened({ map: off });
  view(c2); await sleep(); await sleep();
  assert.ok(!/is working/.test(view(c2)), "Off: nothing works, so nothing says it does");
});

test("W26: each function's card has its own Settings tab: its template, its own limit, its ladder numbers, how it starts; Identity's carries where the site is served from", async () => {
  const c = await opened({ map: rtMap() });
  vm.runInContext("dpS().pane['r3:priority'] = 'settings';", c);
  let html = await fnCard(c, "priority");
  assert.ok(/aria-pressed="true" data-dppane="settings">Settings<\/button>/.test(html), "the tab, open");
  ["Template", "Limit", "Ladder", "Starts", "Hears"].forEach(h => assert.ok(html.indexOf("<h3>" + h + "</h3>") >= 0, h));
  assert.ok(!/<h3>Envelopes<\/h3>/.test(html) && !/<h3>Queue<\/h3>/.test(html), "the card's own rows are on its own tab");
  assert.ok(/data-wbdraft="r3:env:Priority:calls"[^>]*value="30"/.test(html) && /data-wbenv="Priority"/.test(html), "its own limit, and only its own");
  assert.ok(!/data-wbdraft="r3:env:Write:calls"/.test(html), "not another's");
  assert.ok(/<span class="dpk">Runs before a step climbs<\/span><input type="number" min="0" step="1" data-wbdraft="r3:ladder:Priority:runs" value="40"/.test(html), "its ladder numbers");
  assert.ok(/data-wbladder="Priority"/.test(html) && !/<h3>Served from<\/h3>/.test(html));
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:ladder:Priority:runs" }, value: "50" } }));
  assert.ok(click(c, { wbladder: "Priority" })); await sleep(); await sleep();
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "priority", "the card stays open");
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", c);
  html = await fnCard(c, "identity");
  assert.ok(/<h3>Served from<\/h3>/.test(html) && /data-wbhost="1"/.test(html), "Identity's carries the host");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:host" }, value: "https://cityclinic.example" } }));
  click(c, { wbhost: "1" }); await sleep(); await sleep();
  vm.runInContext("dpS().pane['r3:coordination'] = 'settings';", c);
  html = await fnCard(c, "coordination");
  assert.ok(/<h3>Who goes first<\/h3>/.test(html) && /<h3>Who may post to whom<\/h3>/.test(html), "Coordination's carries its table");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [
    { p: "/api/native/r3/ladder", body: { engine: "Priority", runs: 50 } },
    { p: "/api/native/r3/host", body: { host: "https://cityclinic.example" } }], "only what was typed, for that function");
  const t = words(html);
  assert.ok(!/internal\s+system/i.test(t));
  const old = await opened();
  vm.runInContext("dpS().pane['r3:priority'] = 'settings';", old);
  const oh = await fnCard(old, "priority");
  assert.ok(!/>Settings<\/button>/.test(oh) && /<h3>Envelopes<\/h3>/.test(oh), "a department of the first build keeps the tabs it had");
});

/* ── V2: the Map and the Board of the second design (23-screens.js) ─────────
   The design of record is holding/plans/website-department/design-simplify.html
   (third pass). What the founder had built: "Make changes to map, chart, and
   board. Do these changes... Don't change the navigation." One test each for
   the Map, Root's Map and the Board; one that the navigation and every other
   card stay the first design's with the switch on; V12 is the stylesheet.
   The runtime map with an ask waiting is the fixture, as W25 uses it. */
async function v2(opts){
  const c = fresh(opts);
  vm.runInContext("wbS().v2 = true; dpS().sel = 'r3'; dpS().tab['r3'] = 'now';", c);
  c.wbList(WEB); await sleep(); await sleep();
  c.wbList(WEB); c.wbViewer(WEB); await sleep(); await sleep();
  c.wbViewer(WEB); await sleep(); await sleep();          /* the map landed: the open section reads its own record */
  return c;
}
async function paint(c, n){
  for (let k = 0; k < (n || 3); k++){ c.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 6; i++) await sleep(); }
  return c.dpViewerHtml(WEB, {}, null, null);
}

test("W34: a function's chat is its existing turns and thinking from the record, with a box to say more; never a Start button, never a new chat", async () => {
  const c = await opened({ map: rtMap() });
  await fnCard(c, "identity");
  vm.runInContext("dpS().pane['r3:identity'] = 'chat';", c);
  for (let k = 0; k < 3; k++){ c.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 6; i++) await sleep(); }
  let html = c.dpViewerHtml(WEB, {}, null, null);
  assert.deepStrictEqual(readsOf(c, /\/chat\?fn=/), ["/api/native/r3/chat?fn=identity"], "read from the record, once");
  assert.ok(/<div class="wbchat wbfn wb">/.test(html), "the function's own chat");
  assert.ok(/<div class="who who-you">You<\/div><div class="u md">A website for the hospital<\/div>/.test(html), "the person's words to it");
  assert.ok(/<div class="o2quiet dpq wbthink">Read the words, code · /.test(html), "its thinking as a quiet line between the turns");
  assert.ok(/<div class="who who-ai">Identity<\/div><div class="a">Filed in the Brief\.<span class="dpchk">agrees · /.test(html), "what it said, with the act");
  assert.ok(/placeholder="Say it to Identity"/.test(html) && /data-wbask="fn:identity"/.test(html), "a box to say more");
  assert.ok(!/Start the chat|data-dpchatstart|data-dpframe|No chat with/.test(html), "never a Start button, never a frame, never a new chat");
  vm.runInContext("wbS().draft['r3:fn:identity'] = 'Could the careers page come first?';", c);
  assert.ok(click(c, { wbask: "fn:identity" }));
  for (let i = 0; i < 4; i++) await sleep();
  const post = JSON.parse(JSON.stringify(c.calls.apiPost.filter(x => /\/ask$/.test(x.p))[0]));
  assert.deepStrictEqual(post, { p: "/api/native/r3/ask", body: { text: "Could the careers page come first?", about: "fn:identity" } }, "the words go to this department, said to Identity");
  assert.ok(readsOf(c, /\/chat\?fn=/).length >= 2, "and the chat is read again once they are sent");
  const old = await opened();
  await fnCard(old, "identity");
  vm.runInContext("dpS().pane['r3:identity'] = 'chat';", old);
  for (let k = 0; k < 2; k++){ old.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 4; i++) await sleep(); }
  html = old.dpViewerHtml(WEB, {}, null, null);
  assert.ok(/Start the chat with Identity/.test(html), "a department of the first build keeps the chat it had");
  assert.deepStrictEqual(readsOf(old, /\/chat\?fn=/), [], "and reads no function chat");
});

test("W34b (PRD M1.7, round 3): an act with no words of its own is said in the owner's words, on a function's chat and the owner's", async () => {
  const c = await opened({ map: rtMap() });
  const at = "2026-10-23T10:00:00+05:30";
  const fn = t => c.wbFnTurn(Object.assign({ src: "Priority", dst: ["Adaptation"], at, think: false, line: "" }, t));
  const all = [];
  const seen = (html, re, why) => { all.push(html); assert.ok(re.test(html), why + ": " + html); };
  seen(fn({ msg_type: "reject-proposal" }), /<div class="a">Said no<span class="dpchk">says no · /, "a function's no");
  seen(fn({ msg_type: "accept-proposal" }), /<div class="a">Said yes<span class="dpchk">says yes · /, "a function's yes");
  seen(fn({ src: "Owner", dst: ["Identity"], msg_type: "accept-proposal" }), /<div class="u md">Stamped<\/div>/, "the owner stamps");
  seen(fn({ msg_type: "propose", counter: true, line: "the envelope has room for one" }),
       /the envelope has room for one<span class="dpchk">asks for less · /, "Priority's counter is an ask for less");
  seen(c.wbChatTurn({ src: "Owner", dst: ["Identity"], msg_type: "reject-proposal", at, line: "" }, true), /<div class="u md">Said no<\/div>/, "the owner's no");
  assert.ok(!/refus|grant|counter/i.test(all.join(" ").replace(/class="[^"]*"/g, "")), "never refused, granted or countered");
});

test("W35: a turn that lands slides in once; the working mark breathes; nothing else moves", async () => {
  const chat = JSON.parse(JSON.stringify(CHAT));
  chat.turns.push({ n: 9, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: null, word: "plan", line: "Planned 5 pages.", dept: "r3", name: DEPT, own: true });
  const c = await opened({ map: rtMap(), chat });
  view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/Planned 5 pages\./.test(html) && !/wbnew/.test(html), "a paint of what was already there moves nothing");
  /* the paint after a turn lands (W31 covers the read that lands it): the count the last paint saw is one short */
  vm.runInContext("wbS().turns.r3 = wbS().chat.r3.turns.length - 1;", c);
  html = view(c);
  assert.strictEqual((html.match(/class="turn wbturn wbnew"/g) || []).length, 1, "the one turn that landed slides in");
  assert.ok(new RegExp('wbnew">' + SIGNED + '<div class="a">Planned 5 pages\\.').test(html), "and it is the last one");
  html = view(c);
  assert.ok(!/wbnew/.test(html), "the next paint moves nothing: it slides in once");
  const m = rtMap(); m.status.running = [{ engine: "Write", since: AT, what: "page 2 of 5" }];
  const w = await opened({ map: m, chat });
  view(w); await sleep(); await sleep();
  assert.ok(/<div class="o2quiet dpq wbworking"><i class="wbbreath"><\/i>Write is working: page 2 of 5<\/div>/.test(view(w)), "the working line carries the breathing mark");
  assert.ok(/@keyframes wbBreathe/.test(css) && /@keyframes wbSlide/.test(css), "the motions are in the stylesheet");
  assert.ok(/prefers-reduced-motion:reduce\)\{\.wbbreath,\.wbchat \.wbturn\.wbnew\{animation:none\}/.test(css), "reduced motion: the same marks, no motion");
});

test("W36: a department at work carries a breathing mark on its row; the list is read again on the clock and painted only when it changed", async () => {
  const c = await opened({ map: rtMap() });
  assert.ok(!/wbbreath/.test(c.wbTileMark("r3")), "at rest, no breathing mark");
  let listed = [{ ref: "r3", name: "Website", stopped: false, working: ["Write"] }];
  c.apiGet = (p) => { c.calls.apiGet.push(p); if (p === "/api/native/depts") return Promise.resolve({ depts: JSON.parse(JSON.stringify(listed)) }); return new Promise(() => {}); };
  const painted = () => c.calls.render;
  const before = painted();
  vm.runInContext("wbLoadRefs(true);", c);
  await sleep(); await sleep();
  assert.ok(/<span class="wbtm"><i class="wbbreath" title="Write working"><\/i>/.test(c.wbTileMark("r3")), "the row breathes while Write works, and says who");
  assert.strictEqual(painted(), before + 1, "one paint: the list changed");
  vm.runInContext("wbLoadRefs(true);", c);
  await sleep(); await sleep();
  assert.strictEqual(painted(), before + 1, "no paint: the list did not change");
  listed = [{ ref: "r3", name: "Website", stopped: false, working: [] }];
  vm.runInContext("wbLoadRefs(true);", c);
  await sleep(); await sleep();
  assert.ok(!/wbbreath/.test(c.wbTileMark("r3")), "the mark is gone when the work is done");
  assert.strictEqual(painted(), before + 2);
  assert.ok(/st\.ticks % 4 === 0/.test(wbSrc), "read on every fourth tick of the clock");
});

test("W37: on Root, the hand-over line folds to one quiet line once that department has answered", async () => {
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.live = false;
  const chat = JSON.parse(JSON.stringify(ROOT_CHAT));
  chat.turns = [
    { n: 1, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, thread: "t1", word: "front", line: "A careers page", dept: "r5", name: DEPT },
    { n: 2, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: "t1", word: "request", line: "handed to " + DEPT, dept: "r5", name: DEPT }];
  let c = await opened({ map: rm, chat });
  view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<div class="a">handed to City Care Hospital Website/.test(html) && !/wbfold/.test(html), "before the answer, the hand-over is a turn of Root's");
  chat.turns.push({ n: 3, src: "Identity", dst: ["Owner"], msg_type: "inform", at: AT, thread: "t1", word: "request", line: "Filed in the Brief.", dept: "r5", name: DEPT });
  c = await opened({ map: rm, chat });
  view(c); await sleep(); await sleep();
  html = view(c);
  assert.ok(/<div class="o2quiet dpq wbfold">handed to City Care Hospital Website<\/div>/.test(html), "once the department answered, the hand-over is one quiet line");
  assert.ok(/Filed in the Brief\./.test(html), "and the answer stands");
});

test("W38: a filed turn's button is named for what was filed and opens it; a live turn's opens the live site", async () => {
  const c = await opened({});
  const filed = c.wbChatTurn({ src: "Identity", msg_type: "inform", at: AT, word: "filed", line: "Source Reader v1 is filed.", link: "Source Reader", v: 1, dept: "r5", name: DEPT }, false);
  assert.ok(/data-wbopenart="source-reader"/.test(filed) && /data-wbdept="r5"/.test(filed), filed);
  assert.ok(/>Open Source Reader</.test(filed) && !/Open the live site/.test(filed), filed);
  const live = c.wbChatTurn({ src: "Identity", msg_type: "inform", at: AT, word: "live", line: "Live site v1 is live.", link: "Live site", v: 1, dept: "r5", name: DEPT }, false);
  assert.ok(/data-wblive="r5"/.test(live) && />Open the live site</.test(live), live);
});

test("W39: opening from a chat button selects the row and the department's own tab, so the next repaint keeps the preview", async () => {
  const c = await opened({});
  vm.runInContext("dpS().tab['r5'] = 'conversation';", c);
  click(c, { wblive: "r5" });
  let st = c.wbS();
  assert.strictEqual(st.tab.r5, "art"); assert.strictEqual(st.sel.r5, "live-site"); assert.strictEqual(st.pane["r5:live-site"], "preview");
  assert.strictEqual(c.dpS().tab.r5, "now", "the department opens on its own rows, not on the app it showed last");
  vm.runInContext("dpS().tab['r5'] = 'conversation';", c);
  click(c, { wbopenart: "source-reader", wbdept: "r5" });
  st = c.wbS();
  assert.strictEqual(st.tab.r5, "art"); assert.strictEqual(st.sel.r5, "source-reader"); assert.strictEqual(st.pane["r5:source-reader"], "preview");
  assert.strictEqual(c.dpS().tab.r5, "now");
});

test("W40: Send in a function's chat keeps the person in that chat and reads it again", async () => {
  const c = await opened({});
  vm.runInContext("dpS().tab['r3'] = 'priority'; wbS().draft['r3:fn:priority'] = 'Put the top three first.'; wbS().fnchat['r3:priority'] = { fn: 'Priority', turns: [] };", c);
  const reads = c.calls.apiGet.length;
  click(c, { wbask: "fn:priority" });
  await sleep(); await sleep(); await sleep();
  assert.strictEqual(c.dpS().tab.r3, "priority", "the person stays in Priority's chat");
  const post = c.calls.apiPost[c.calls.apiPost.length - 1];
  assert.strictEqual(JSON.stringify(post.body), JSON.stringify({ text: "Put the top three first.", about: "fn:priority" }));
  assert.ok(c.calls.apiGet.slice(reads).some(p => /chat\?fn=priority/.test(p)), "the function's chat is read again after the words");
});

test("W41: the New organisation sheet asks what the first department is for, naming no website", async () => {
  const c = await opened({});
  vm.runInContext("wbS().found = { org: '', goal: '', busy: false, error: null };", c);
  const html = c.wbFoundHtml();
  assert.ok(/placeholder="What should Root set up first\? Say what it is for, in your words"/.test(html), html.slice(0, 600));
  assert.ok(!/placeholder="[^"]*[Ww]ebsite/.test(html), "a tool, a desk or a list is set up here as well as a site");
});

/* ── W42-W44: the organisation row ─────────────────────────────────────── */
const ORG_DEPTS = [{ ref: "r2", name: "City Care Hospital Root", stopped: false, kind: "root", parent: "r1", working: [] },
                   { ref: "r3", name: "Website", stopped: false, kind: "website", parent: "r2", working: [] }];
async function orgOpened(opts){
  const rm = rtMap(); rm.ref = "r2"; rm.name = "City Care Hospital Root"; rm.kind = "root"; rm.root = "r2"; rm.live = false;
  rm.goal = "Makes, changes and ends City Care Hospital's departments from the Library's templates";
  const c = fresh(Object.assign({ depts: ORG_DEPTS, rootMap: rm, rootChat: Object.assign({}, ROOT_CHAT, { root: "r2" }) }, opts || {}));
  vm.runInContext("wbS().v2 = true; o2S().loaded = true;", c);
  c.o2Select("r1");
  for (let k = 0; k < 4; k++){ c.o2ScreenHtml(); await sleep(); await sleep(); }   /* the list of departments, Root's map, then its chat land */
  return c;
}

test("W42: the organisation row is Root's chat and nothing else; Root is not a row of the tree nor a tile of the chart; its departments sit under the organisation", async () => {
  const c = await orgOpened();
  const html = c.o2ScreenHtml(), d = c.o2Data();
  assert.deepStrictEqual(JSON.parse(JSON.stringify((d.kids.get("r1") || []).map(x => x.ref))), ["r3", "r4"], "the departments sit under the organisation");
  assert.ok(!d.kids.has("r2") && d.hidden.has("r2") && d.lifted.get("r1").ref === "r2", "Root is lifted, not drawn");
  assert.ok(!/data-o2ref="r2"/.test(html), "no Root row anywhere on the screen");
  assert.ok(/data-o2ref="r3"[^>]*style="--d:2"/.test(html), "a department one level under the organisation");
  assert.ok(/<div class="o2vh"><b>Chat<\/b>/.test(html) && /<div class="wbchat wb">/.test(html) && /<textarea id="wbd-ask"/.test(html), "Root's chat");
  assert.ok(/<div class="wb2head"><b>City Care Hospital<\/b>/.test(html) && />Root settings<\/button>/.test(html), "headed by the organisation, with one button");
  assert.ok(/<div class="o2body wide">/.test(html) && !/data-dptab=/.test(html) && !/class="o2list/.test(html), "no list column");
  assert.strictEqual(vm.runInContext("dpS().sel", c), "r2", "the clicks and the box speak for Root");
  const chart = c.o2ChartHtml(ORG, d);
  assert.ok(/data-o2ref="r1"/.test(chart) && /data-o2ref="r3"/.test(chart) && /data-o2ref="r4"/.test(chart) && !/data-o2ref="r2"/.test(chart), "the chart: the organisation over its departments, no Root tile");
  assert.ok(/<span class="o2parent">City Care Hospital<\/span>/.test(c.o2StripHtml(WEB, d, null)), "a department's parent reads the organisation");
  const m3 = rtMap(); m3.root = "r2";
  assert.ok(/data-wb2go="r1">City Care Hospital<\/button> &rsaquo; City Care Hospital Website/.test(c.wb2Head(WEB, m3)), "a department's crumb names the organisation, and goes there");
  /* an organisation without a Root paints as before */
  const plain = await orgOpened({ depts: [{ ref: "r3", name: "Website", stopped: false, kind: "website", parent: "r2", working: [] }] });
  const ph = plain.o2ScreenHtml(), pd = plain.o2Data();
  assert.ok(/data-o2ref="r2"/.test(ph) && pd.kids.has("r2") && /data-dptab=/.test(ph), "Root drawn, the list column back");
});

test("W43: Root settings is a pane, never a chat: what Root does, On or Off with its one switch, its rules, the departments it made, a way back", async () => {
  const c = await orgOpened();
  assert.ok(click(c, { wbtab: "root" }), "the button is this file's");
  let html = c.o2ScreenHtml();
  assert.ok(/<div class="o2vh"><b>Root<\/b>/.test(html) && /<h3>Root<\/h3>/.test(html), "the pane");
  assert.ok(/Makes, changes and ends City Care Hospital's departments/.test(html), "what it does, from its record");
  assert.ok(/data-wbstop="1"/.test(html) && /<div class="dpchk">none yet<\/div>/.test(html), "the switch; no rules yet");
  assert.ok(/data-wbopen="r5">City Care Hospital Website<\/button>/.test(html), "the departments it made open");
  assert.ok(!/<textarea/.test(html) && !/wbchat/.test(html) && !/Root settings/.test(html), "never a chat; the button gone while open");
  assert.ok(click(c, { wbtab: "chat" }));
  html = c.o2ScreenHtml();
  assert.ok(/<div class="wbchat wb">/.test(html) && !/<h3>Root<\/h3>/.test(html), "back to the chat");
});

test("W44: founding lands on the organisation, whose row is Root's chat", async () => {
  const c = await orgOpened();
  vm.runInContext("o2S().sel = 'r0'; wbS().found = { org: 'City Care Hospital', goal: 'A website', busy: false, error: null };", c);
  await c.wbFoundGo();
  for (let i = 0; i < 6; i++) await sleep();
  const post = c.calls.apiPost.filter(x => x.p === "/api/native/found")[0];
  assert.deepStrictEqual(JSON.parse(JSON.stringify(post.body)), { org: "City Care Hospital", first: "A website" });
  assert.strictEqual(vm.runInContext("o2S().sel", c), "r1", "the organisation is selected");
  assert.strictEqual(vm.runInContext("S.wb.tab['r2']", c), "chat", "its row is Root's chat");
  assert.ok(/<div class="wbchat wb">/.test(c.o2ScreenHtml()));
});

test("V2 navigation: with the switch on the list, Chat, a function card and an engine card are the first design's, unchanged", async () => {
  const c = await v2({ map: rtMap({ ask: true }) });
  const html = c.dpListHtml(WEB, {}, null, null);
  ["Chat", "Map", "Board", "Filed work", "Human Sutra"].forEach(x => assert.ok(html.indexOf(x) >= 0, x));
  /* PRD M4.7 (ruled: the motor folds into the engine card, S17): the Motor row leaves the list column */
  assert.ok(!/data-wbtab="motor"/.test(html) && html.indexOf("<span>Motor</span>") < 0, "no Motor row");
  /* PRD M1.5 (the ruled Map, 2026-09-29): System status folds into the Map's NOW line, so its row is gone */
  assert.ok(!/System status/.test(html) && !/data-wbtab="status"/.test(html), "System status folded into the NOW line");
  assert.ok(!/wb2/.test(html), "no second-design piece in the list");
  let v = view(c);
  assert.ok(/<div class="o2vh"><b>Chat<\/b>/.test(v) && !/wb2/.test(v), "Chat is the chat 22-website.js draws");
  v = await fnCard(c, "priority");
  assert.ok(/<h3>Envelopes<\/h3>/.test(v) && !/wb2/.test(v), "a function card, unchanged");
  click(c, { wbengine: "Write" }); await sleep();
  v = await paint(c);
  assert.ok(/<div class="o2vh"><b>Write<\/b>/.test(v) && /data-wbpane="steps"/.test(v) && !/wb2/.test(v), "an engine card, unchanged");
});

test("V2 map: the head has one switch and the live site; four fixed rows; the running engine lit and its hand-offs marching; the NOW line names what is active; every node says where a click goes", async () => {
  const m = rtMap({ ask: true }); m.status.running = [{ engine: "Write", what: "" }]; m.engines[1].state = "Running";
  const c = await v2({ map: m });
  click(c, { wbtab: "map" }); await sleep();
  const html = await paint(c);
  assert.ok(/<div class="o2vh"><b>Map<\/b>/.test(html));
  assert.ok(/role="switch" aria-checked="true" class="wb2switch on" data-wbstop="1"/.test(html) && /class="o2more wb2live"/.test(html), "the head");
  ["People", "Functions", "Work", "Knows"].forEach(l => assert.ok(html.indexOf(">" + l + "</text>") >= 0, l));
  assert.ok(/<g class="n eng run" data-wbengine="Write"[^>]*><circle class="halo"/.test(html), "Write lit");
  assert.strictEqual((html.match(/class="e flow"/g) || []).length, 2, "the hand-off into it and out of it march");
  assert.ok(/<span class="wb2pill run">Write running<\/span><span class="wb2pill ask">1 ask for you<\/span>/.test(html), "the NOW line");
  assert.ok(/<g class="n fn ask" data-wbfn="identity"[^>]*><rect[^>]*><g class="ic"/.test(html), "a function carries its mark");
  assert.ok(/<text x="10" y="20">Rules<\/text><text class="v" x="56" y="20">none yet<\/text>/.test(html) && /<text class="v" x="64" y="20">4 things, 13 versions<\/text>/.test(html), "what the department knows, from the record");
  /* PRD M1.5: the legend is cut; every node names itself on hover instead */
  assert.ok(!/wb2legend|wb2lg/.test(html), "no legend");
  assert.ok((html.match(/<g class="n[^"]*"[^>]*>/g) || []).length === (html.match(/<title>[^<]+<\/title><\/g>/g) || []).length, "every node has its hover name");
  assert.ok(/<g class="n fn ask" data-wbfn="identity"/.test(html) && /<g class="n who ask" data-wbtab="chat"/.test(html), "the ask is amber on Identity and on you");
  assert.ok(/<g class="n work done" data-wbart="site-plan"[^>]*><rect[^>]*><text x="8" y="17">Site plan<\/text><text class="v" x="8" y="30">v2<\/text>/.test(html), "work with its version");
  const nodes = html.match(/<g class="n[^"]*"[^>]*>/g) || [];
  assert.ok(nodes.length >= 18 && nodes.every(g => /data-(wbtab|wbengine|wbart|wbfn)=/.test(g)), "every node says where a click goes: " + nodes.length);
  assert.ok(!/Nothing is waiting for you/.test(html) && !/<h3>System status<\/h3>/.test(html) && !/<h3>Health<\/h3>/.test(html) && !/<textarea/.test(html), "no empty box, no composer");
  click(c, { wbengine: "Write" });
  assert.strictEqual(vm.runInContext("S.wb.tab['r3'] + ':' + S.wb.sel['r3']", c), "engine:Write", "a click goes there");
  click(c, { wbfn: "priority" });
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "priority", "a function opens its own card");
  const t = words(html.replace(/<div class="wb2now">.*?<\/div>/, "").replace(/<text class="v"[^>]*>[^<]*<\/text>/g, ""));
  assert.ok(!/\b\d{2,}\b/.test(t), "a count at rest outside the NOW line and the record: " + (t.match(/.{0,30}\b\d{2,}\b.{0,30}/) || [""])[0]);
  const old = await opened({ map: m });
  vm.runInContext("S.wb.tab['r3'] = 'map';", old);
  assert.ok(/<h3>The department<\/h3>/.test(old.wbViewer(WEB)) && !/wb2/.test(old.wbViewer(WEB)), "off: the first design's Map");
});

/* PRD M1.5: the ruled Map. The five boxes take their state from the five functions' read; the NOW line carries the
   cycle's words and counts only when they are not zero; no legend; no digits at rest outside the NOW line; Budget is a
   bar in Knows; a failed read falls back to today's classes and says so once; Off and Goal reached read as such. */
async function mapWith(o){
  const c = await v2(Object.assign({ map: rtMap() }, o));
  click(c, { wbtab: "map" }); await sleep();
  return [c, await paint(c)];
}
const fnBox = (html, fn) => (new RegExp('<g class="n fn([^"]*)" data-wbfn="' + fn + '"[^>]*>([\\s\\S]*?)</g>(?=<g|<path|<text|</svg>)').exec(html) || []);
test("M1.5: each function's box takes its class and its state word from the functions read", async () => {
  const fv = fvOf({ states: { Identity: "waiting_on_you", Adaptation: "waiting", Priority: "fault", Coordination: "working", Audit: "quiet" },
                    lines: { Identity: "May the reviews show first names?", Adaptation: "waits on Priority", Priority: "Answer a proposal: page 3 of 8 failed its check",
                             Coordination: "Write's turn" },
                    cycle: { says: "Write is working", needs_you: true, asks: 1 } });
  const [c, html] = await mapWith({ fv });
  const want = { identity: [" ask", "waits on you"], adaptation: [" wait", "waiting"], priority: [" block", "fault"], coordination: [" run", "working"], audit: ["", "quiet"] };
  Object.keys(want).forEach(fn => {
    const g = fnBox(html, fn);
    assert.ok(g.length, fn + " box");
    assert.strictEqual(g[1], want[fn][0], fn + " class");
    assert.ok(new RegExp('<text class="st" x="42" y="40">' + want[fn][1] + '</text>').test(g[2]), fn + " word: " + g[2]);
    assert.ok(new RegExp('<rect class="fnbar fn-' + fn + '" width="4" height="64"').test(g[2]), fn + " carries its colour bar");
    assert.ok(/<rect class="bx" width="154" height="64"/.test(g[2]), fn + " is a 154x64 box");
  });
  assert.ok(/<rect class="halo" width="154"/.test(fnBox(html, "coordination")[2]) && !/class="halo"/.test(fnBox(html, "identity")[2]), "only the working one has a halo");
  assert.ok(/<title>Identity · waits on you · May the reviews show first names\?<\/title>/.test(html), "the hover names it and says what it waits on");
  assert.ok(!/wb2legend|wb2lg/.test(html), "no legend");
  /* the NOW line: the cycle's words first */
  assert.ok(/<div class="wb2now"><span class="wb2pill ask" aria-live="polite">Write is working<\/span>/.test(html), "the cycle's words lead, amber when it needs you");
  /* no digits at rest outside the NOW line: the line with its count sits in the hover only */
  const rest = html.replace(/<div class="wb2now">[\s\S]*?<\/div>/, "").replace(/<title>[^<]*<\/title>/g, "").replace(/<text class="v"[^>]*>[^<]*<\/text>/g, "");
  const t = words(rest.slice(rest.indexOf("<svg"), rest.indexOf("</svg>")));
  assert.ok(!/\d/.test(t.replace(/\bv\d+\b/g, "")), "a digit at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(readsOf(c, /\/functions$/).length >= 1, "the Map reads the functions read");
});
test("M1.5: the NOW line counts only what is not zero, folds in System status, and says Off and Goal reached", async () => {
  const quiet = rtMap(); quiet.health.timeline = [];
  let [, html] = await mapWith({ map: quiet, fv: fvOf({ cycle: { says: "Proposing the work", state: "adapting", step: 2 } }) });
  let now = /<div class="wb2now">([\s\S]*?)<\/div>/.exec(html)[1];
  assert.strictEqual(now, '<span class="wb2pill say" aria-live="polite">Proposing the work</span>', "nothing to count: the words alone");
  const busy = rtMap({ ask: true }); busy.status.running = [{ engine: "Write", what: "" }]; busy.engines[1].state = "Running";
  busy.status.escalated = [{ id: "a-2", kind: "envelope", engine: "Write", text: "Write is out of today's envelope", status: "pending", created: AT, escalated: true }];
  busy.health.checks[0] = { name: "Motor", state: "block", line: "Not ticking" };
  [, html] = await mapWith({ map: busy, fv: fvOf({ states: { Identity: "waiting_on_you", Coordination: "working" }, cycle: { says: "Write is working", needs_you: true, asks: 2 } }) });
  now = /<div class="wb2now">([\s\S]*?)<\/div>/.exec(html)[1];
  assert.ok(/>Write is working<\/span><span class="wb2pill run">Write running<\/span><span class="wb2pill ask">2 asks for you<\/span><span class="wb2pill block" title="Not ticking">Motor<\/span>$/.test(now), now);
  /* stopped: the switch is off, NOW reads Off, no halos, the boxes off */
  const off = rtMap({ stopped: true }); off.status.running = [{ engine: "Write", what: "" }]; off.engines[1].state = "Running";
  [, html] = await mapWith({ map: off, fv: fvOf({ stopped: true, cycle: { state: "stopped", says: "Stopped by you" } }) });
  now = /<div class="wb2now">([\s\S]*?)<\/div>/.exec(html)[1];
  assert.ok(/<span class="wb2pill off">Off<\/span>$/.test(now) && !/Stopped by you|running/.test(now), now);
  assert.ok(!/class="halo"/.test(html) && /role="switch" aria-checked="false"/.test(html), "no halo, the switch off");
  ["identity", "adaptation", "priority", "coordination", "audit"].forEach(fn => assert.strictEqual(fnBox(html, fn)[1], " off", fn));
  /* done: Goal reached, and the deliverable lit */
  [, html] = await mapWith({ map: rtMap({ versions: { "Brief": 1, "Site plan": 2, "Pages": 5, "Build": 5, "Live site": 1 } }),
                            fv: fvOf({ cycle: { state: "done", says: "Goal reached" } }) });
  assert.ok(/<span class="wb2pill ok" aria-live="polite">Goal reached<\/span>/.test(html), "Goal reached");
  assert.ok(/<g class="n work done live" data-wbart="live-site"/.test(html), "the deliverable takes the ok tint once it is live");
});
/* M1.5 (round 1, gap 8): S1's Done holds for every runtime department, not the website alone. An organic department has
   no Live site, so its deliverable (the last thing its line makes) is lit when the cycle's goal is reached or a version
   of it passed its check; before either it is filed, not lit. */
test("M1.5: an organic department's deliverable takes the ok tint once the goal is reached or it passed its check", async () => {
  const organic = o => {
    const m = rtMap({ versions: { "Brief": 1, "Facts": 1, "Inventory": 1 } });
    m.kind = "organic"; m.live = false;
    m.engines = [["Facts", "Brief", "Facts"], ["Track", "Facts", "Inventory"]].map(([name, reads, writes]) => Object.assign({}, m.engines[0], { name, reads, writes }));
    m.artifacts.forEach(a => { a.latest = { v: 1, at: AT, check: { ok: a.name !== "Inventory" || !!o.passed, notes: [] } }; });
    return m;
  };
  let [, html] = await mapWith({ map: organic({}), fv: fvOf({ cycle: { state: "running", says: "Track is working" } }) });
  assert.ok(/<g class="n work done" data-wbart="inventory"/.test(html), "filed, not yet delivered: not lit");
  [, html] = await mapWith({ map: organic({}), fv: fvOf({ cycle: { state: "done", says: "Goal reached" } }) });
  assert.ok(/<g class="n work done live" data-wbart="inventory"[\s\S]*?<title>Inventory · filed, v1 · delivered<\/title>/.test(html), "the goal reached: lit");
  [, html] = await mapWith({ map: organic({ passed: true }), fv: fvOf({ cycle: { state: "pursuing", step: 8, says: "Working on what Audit found" } }) });
  assert.ok(/<g class="n work done live" data-wbart="inventory"/.test(html), "a version that passed its check: lit");
  assert.ok(!/<g class="n work done live" data-wbart="facts"/.test(html), "only the deliverable");
});
test("M1.5: Budget joins Knows as a bar with its numbers on hover; a failed read falls back and can be read again; the narrow list", async () => {
  let [c, html] = await mapWith({ fv: fvOf({ budget: 0.25 }) });
  assert.ok(/<g class="n" data-wbfn="priority" transform="[^"]*"><rect class="bx" width="150" height="32" rx="8"\/><text x="10" y="20">Budget<\/text><rect class="bar0" x="66" y="13" width="72" height="6" rx="3"\/><rect class="bar1" x="66" y="13" width="18.0" height="6" rx="3"\/><title>Budget · 30 of 120 calls/.test(html), "a bar, the numbers on hover");
  click(c, { wbfn: "priority" });
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "priority", "Budget opens Priority");
  /* the narrow list: the same order, the five with their mark and their word */
  const cards = /<div class="wb2cards wb">([\s\S]*)$/.exec(html)[1];
  const order = (cards.match(/data-wbfn="(\w+)"><i class="wb2mk/g) || []).map(x => /"(\w+)"/.exec(x)[1]);
  assert.deepStrictEqual(order, ["identity", "adaptation", "priority", "coordination", "audit"], "the five in order");
  assert.ok(/<div class="wb2frame wb"><div class="wb2map wb"><svg/.test(html), "one frame, a size container, holds both");
  /* a failed read: the line says so once, with Try again; the boxes keep today's classes */
  let fails = 0;
  [c, html] = await mapWith({ map: rtMap({ ask: true }), fv: () => (fails++ ? Promise.resolve(fvOf({ states: { Identity: "working" } })) : Promise.reject(new Error("down"))) });
  assert.ok(/<span class="wb2pill off">Could not read<\/span><button type="button" class="o2more wb" data-wbfvretry="1">Try again<\/button>/.test(html), "said once");
  assert.strictEqual(fnBox(html, "identity")[1], " ask", "today's class: an ask is Identity's");
  click(c, { wbfvretry: "1" }); await sleep(); await sleep();
  html = await paint(c);
  assert.strictEqual(fnBox(html, "identity")[1], " run", "read again, and the read's state shows");
  assert.ok(!/Could not read/.test(html));
  /* while the read is on its way a skeleton holds the words' place */
  [, html] = await mapWith({ fv: () => new Promise(() => {}) });
  assert.ok(/<div class="wb2now"><span class="wb2pill wb2skel" aria-hidden="true"><\/span>/.test(html), "a skeleton");
});
/* MK-8 taken (decision log): the prototype's Map extras. The box carries '?' or '!' and its line when it fits and has no
   count; who speaks to whom among the five is three arcs at most, the rest in a closed dropdown; who made each thing and
   what is not recorded are closed dropdowns too, counts as bars. */
test("M1.5 extras (MK-8): badges and the line on a box, three speaks-to arcs at most, the closed dropdowns", async () => {
  const speaks = [{ from: "Adaptation", to: "Priority", n: 9 }, { from: "Priority", to: "Adaptation", n: 7 }, { from: "Identity", to: "Adaptation", n: 4 },
                  { from: "Coordination", to: "Identity", n: 2 }, { from: "Owner", to: "Identity", n: 12 }, { from: "Identity", to: "Owner", n: 11 }];
  const fv = fvOf({ states: { Identity: "waiting_on_you", Coordination: "working", Audit: "fault" },
                    lines: { Identity: "May the reviews show first names?", Coordination: "Write's turn", Audit: "a step failed" },
                    speaks, not_recorded: ["what Audit did"],
                    made: [{ art: "Site plan", slug: "site-plan", v: 2, by: "Plan", makers: ["Plan"], by_v: {}, readers: ["Write"] },
                           { art: "Brief", slug: "brief", v: 1, by: "Owner", makers: ["Owner"], by_v: {}, readers: ["Plan"] }] });
  const [, html] = await mapWith({ fv });
  assert.ok(/<g class="bdg ask"><circle cx="140" cy="14" r="7"\/><text x="140" y="18" text-anchor="middle">\?<\/text><\/g>/.test(fnBox(html, "identity")[2]), "'?' on Identity");
  assert.ok(/<g class="bdg block">[\s\S]*?>!<\/text><\/g>/.test(fnBox(html, "audit")[2]), "'!' on Audit");
  assert.ok(!/class="bdg/.test(fnBox(html, "coordination")[2]), "no badge on a working one");
  assert.ok(/<text class="st" x="42" y="40">working<\/text><text class="ln" x="42" y="55">Write(&#39;|')s turn<\/text>/.test(fnBox(html, "coordination")[2]), "the word, and the line under it");
  assert.ok(/<text class="st" x="42" y="40">waits on you<\/text><text class="ln" x="42" y="55">May the reviews…<\/text>/.test(fnBox(html, "identity")[2]), "a long line is cut to the box");
  const [, h2] = await mapWith({ fv: fvOf({ states: { Coordination: "working" }, lines: { Coordination: "page 3 of 8" } }) });
  assert.ok(!/class="ln"/.test(fnBox(h2, "coordination")[2]) && /<title>Coordination · working · page 3 of 8<\/title>/.test(h2), "a count stays on the hover");
  const arcs = html.match(/<path class="e talk"[^>]*><title>([^<]+)<\/title><\/path>/g) || [];
  assert.deepStrictEqual(arcs.map(a => /<title>([^<]+)</.exec(a)[1]), ["Adaptation speaks to Priority", "Priority speaks to Adaptation", "Identity speaks to Adaptation"], "three at most, the busiest, among the five only");
  const under = html.slice(html.indexOf('<details class="wb2dd wb">'));
  assert.ok(/^<details class="wb2dd wb"><summary>Messages between functions<\/summary>/.test(under) && !/<details[^>]* open/.test(under), "closed by default");
  assert.strictEqual((under.split("<summary>Who made each thing</summary>")[0].match(/<div class="wb2ddrow">/g) || []).length, 4, "every pair among the five in the dropdown, the owner's lines not among them");
  assert.ok(/<b>Site plan<\/b><span class="dpchk">made by Plan · read by Write<\/span>/.test(under) && /<b>Brief<\/b><span class="dpchk">made by you · read by Plan<\/span>/.test(under), "who made each thing");
  assert.ok(/<summary>Not recorded<\/summary><div class="wb2ddrow"><span class="dpchk">what Audit did<\/span><\/div>/.test(under), "what the record does not hold");
  assert.ok(!/\d/.test(words(under).replace(/\bv\d+\b/g, "")), "a count in the dropdowns is a bar, never a number");
});
test("M1.5: a department with no plan yet shows its Brief and one quiet line", async () => {
  const m = rtMap({ versions: { "Brief": 1 } }); m.engines = []; m.live = false; m.artifacts = [{ name: "Brief", slug: "brief", versions: 1, latest: null }];
  const [, html] = await mapWith({ map: m, fv: fvOf({ cycle: { state: "adapting", step: 2, says: "Proposing the work" } }) });
  assert.ok(/<g class="n work done" data-wbart="brief"/.test(html) && /<div class="o2quiet dpq">No plan yet<\/div>/.test(html));
});
/* PRD M4.2 (round 1, gap 7): an engine the registered plan left out stays on the record and never runs. The Map drew it
   on the line of work all the same (Build -> Publish -> Live site), with no word saying so; map_view's in_line and its
   slot in the timetable were read by no screen. Now the line is the plan's, the left-out engine sits under it, muted,
   with the words "left out", on the picture and on the narrow list, and an engine's hover names its slot. */
test("M4.2: the Map leaves an engine the plan left out off the line, says it is left out, and hovers each engine's slot", async () => {
  const m = rtMap({ versions: { "Brief": 1, "Site plan": 1, "Pages": 1, "Build": 1, "Live site": 0 } }); m.live = false;
  m.engines.forEach(e => { e.in_line = e.name !== "Publish"; e.timetable = e.in_line ? { engine: e.name, on: "after " + e.reads + " v1", window_min: 15 } : null; });
  m.engines[3].state = "Left out";
  const [c, html] = await mapWith({ map: m, fv: fvOf({}) });
  const svg = html.slice(html.indexOf("<svg"), html.indexOf("</svg>"));
  const onLine = (svg.match(/<g class="n eng (?!out)[^"]*" data-wbengine="(\w+)"/g) || []).map(x => /"(\w+)"$/.exec(x)[1]);
  assert.deepStrictEqual(onLine, ["Plan", "Write", "Check"], "the line is the plan's");
  assert.strictEqual((svg.match(/<path class="e( flow)?" marker-end/g) || []).length, 6, "Brief, three engines and what each writes: six hand-offs");
  assert.ok(!/<text x="8" y="17">Live site<\/text>/.test(svg), "what only the left-out engine makes is not on the line");
  assert.ok(/<g class="n eng out" data-wbengine="Publish" transform="translate\(105,304\)"><circle class="bx" r="8"\/><text x="16" y="4">Publish · left out<\/text><title>Publish · left out of the plan<\/title><\/g>/.test(svg),
    "under the line, muted, with its word");
  assert.ok(/<title>Plan · engine · after Brief v1<\/title>/.test(svg) && /<title>Check · engine · after Pages v1<\/title>/.test(svg), "the hover names its slot");
  const cards = /<div class="wb2cards wb">([\s\S]*)$/.exec(html)[1];
  const work = cards.slice(cards.indexOf('<div class="dpk">Work</div>'), cards.indexOf('<div class="dpk">Knows</div>'));
  assert.ok(/data-wbengine="Check"[\s\S]*data-wbart="build"[\s\S]*<button type="button" class="wb2card wb" data-wbengine="Publish"><span class="dpdot off"><\/span><b>Publish<\/b><span class="dpchk">left out<\/span><\/button>/.test(work),
    "the narrow list: after the line, a word with the dot");
  assert.ok(/\.wb2map \.n\.out \.bx\{[^}]*var\(--line-soft\)/.test(css) && /\.wb2map \.n\.out text\{fill:var\(--faint\)\}/.test(css), "muted, by tokens");
  click(c, { wbengine: "Publish" });
  assert.strictEqual(vm.runInContext("S.wb.tab['r3']", c) + ":" + vm.runInContext("S.wb.sel['r3']", c), "engine:Publish", "a click opens its card");
  /* a plan that keeps every engine (or the first build, where map_view says nothing of in_line) has every engine on the line */
  const [, all] = await mapWith({ fv: fvOf({}) });
  assert.deepStrictEqual((all.match(/<g class="n eng [^"]*" data-wbengine="(\w+)"/g) || []).map(x => /"(\w+)"$/.exec(x)[1]), ["Plan", "Write", "Check", "Publish"]);
  assert.ok(!/class="n eng out"|left out|No plan yet/.test(all));
  /* before Root's check there is no plan (map_view's planned false, every in_line true): the Brief alone and 'No plan
     yet', on the picture and the narrow list, and nothing reads 'left out' (S1, Empty; round 2, gap 3) */
  const none = rtMap({ versions: { "Brief": 1 } }); none.live = false; none.planned = false;
  none.engines.forEach(e => { e.in_line = true; e.timetable = null; });
  const [, bare] = await mapWith({ map: none, fv: fvOf({ cycle: { state: "adapting", step: 2, says: "Proposing the work" } }) });
  const bsvg = bare.slice(bare.indexOf("<svg"), bare.indexOf("</svg>"));
  assert.ok(!/class="n eng/.test(bsvg) && (bsvg.match(/<g class="n work[^"]*"/g) || []).length === 1, "no engine on the line, the Brief alone");
  assert.ok(/<g class="n work done" data-wbart="brief"/.test(bsvg) && /<div class="o2quiet dpq">No plan yet<\/div>/.test(bare), "the Brief, filed, and the quiet line");
  const bcards = /<div class="wb2cards wb">([\s\S]*)$/.exec(bare)[1];
  const bwork = bcards.slice(bcards.indexOf('<div class="dpk">Work</div>'), bcards.indexOf('<div class="dpk">Knows</div>'));
  assert.ok(/data-wbart="brief"/.test(bwork) && !/data-wbengine=/.test(bwork), "the narrow list: the Brief alone");
  assert.ok(!/left out/.test(bare), "an engine of no plan is not 'left out'");
  const bold = await opened({ map: none });
  click(bold, { wbtab: "map" });
  const bflow = view(bold);
  assert.ok(!/class="wbeng wb"/.test(bflow) && /No plan yet/.test(bflow) && !/Left out of the plan/.test(bflow), "the first design's flow too");
  /* the first design's flow takes the same line */
  const old = await opened({ map: m });
  click(old, { wbtab: "map" });
  const flow = view(old);
  assert.ok(/data-wbengine="Check"/.test(flow) && !/class="wbeng wb" data-wbengine="Publish"/.test(flow) && /<div class="dpchk">Left out of the plan: Publish<\/div>/.test(flow), "the first design too");
});

test("M1.6: on the runtime the list's function rows read the same functions read as the Map; the first build's stay bare", async () => {
  const fv = fvOf({ states: { Identity: "waiting_on_you", Coordination: "working" } });
  const c = await v2({ map: rtMap(), fv });
  for (let k = 0; k < 2; k++){ c.dpListHtml(WEB, {}, null, null); await sleep(); await sleep(); }
  const html = c.dpListHtml(WEB, {}, null, null);
  assert.ok(/data-dptab="identity" aria-label="Identity · waits on you"[^>]*><svg class="dpfnmk fn-identity"[\s\S]*?<b class="dpfnb warn" aria-hidden="true">\?<\/b><i class="dpdot warn"/.test(html), "Identity: its mark, '?' and amber");
  assert.ok(/data-dptab="coordination" aria-label="Coordination · working"[\s\S]*?<i class="dpdot breath"/.test(html), "Coordination breathes");
  assert.deepStrictEqual(readsOf(c, /\/functions$/), ["/api/native/r3/functions"], "one read serves the list and the Map");
  const old = await opened();
  const oh = old.dpListHtml(WEB, {}, null, null);
  assert.ok(/<button type="button" class="o2li dpli" data-dptab="identity"><span>Identity<\/span><\/button>/.test(oh), "the first build's rows stay bare");
  assert.deepStrictEqual(readsOf(old, /\/functions$/), [], "and it never asks for the read");
});
/* PRD M1.7: each function's pane opens on what its site page holds: its line, its template's fields (a placeholder is
   one quiet line, "not set yet"), its recipe (each step by code, AI or a person, on its rung), its journeys with their
   live status and last move, and its version 1 scope. Fixtures for all five, as functions_view.function answers. */
const FN_JOURNEYS = { identity: [["FI1", "Enough to work?"], ["FI2", "Words after go-live"], ["FI3", "The gates"], ["FI4", "Closes a conflict"]],
  adaptation: [["FA1", "The first workflows"], ["FA2", "Pursue until done"], ["FA3", "Crystallize a step"], ["FA4", "Grow out"], ["FA5", "Learn"]],
  priority: [["FP1", "The limit on every start"], ["FP2", "The bargain with Adaptation"]],
  coordination: [["FC1", "Who goes first"], ["FC2", "A lost request"]], audit: [["FAU1", "Read the result"]] };
function fnPageOf(fn){
  const name = fn.charAt(0).toUpperCase() + fn.slice(1);
  return { ref: "r3", fn, name, vsm: "VSM", line: name + "'s one line, as its page says it.", holds: "What " + name + " holds.",
    hands_to: "Who " + name + " hands to.", keeps: "The rules " + name + " keeps.", v1: name + "'s version 1, as built.",
    template: { id: fn + "/product-build", name: "Product build", use_case: "a product" },
    fields: [{ key: "goal", label: "Goal", value: "Holds the goal", placeholder: false },
             { key: "done", label: "Done when", value: null, placeholder: true },
             { key: "hears", label: "Hears", value: ["Take a request"], placeholder: false },
             { key: "writes", label: "Writes", value: ["Tells Identity"], placeholder: false },
             { key: "checks", label: "Checks", value: ["Every effect has a verdict."], placeholder: false },
             { key: "envelope", label: "Limit", value: { share: 0.25 }, placeholder: false },
             { key: "settings", label: "Settings", value: ["Ladder", "Limit"], placeholder: false }],
    recipe: [{ id: fn + ".gate", name: "Say whether it may start", by: "code", rung: "C2", rung_name: "Code", mode: "gate", under: null },
             { id: fn + ".take", name: "Read the words", by: "AI", rung: "C0", rung_name: "Improvised call", mode: "slot", under: "Take a request" },
             { id: fn + ".ask", name: "Ask the owner", by: "person", rung: "P", rung_name: "Person", mode: "slot", under: "Take a request" }],
    journeys: FN_JOURNEYS[fn].map(([id, jn], i) => ({ id, name: jn, built: i === 4 ? "later" : "built",
      status: i === 0 ? "done" : (i === 1 ? "waiting" : (i === 4 ? "later" : "not run yet")),
      last: i < 2 ? { summary: jn + " moved", at: AT, action: "x" } : null })),
    node: { name, state: "quiet", word: "quiet", line: "" }, j2: {} };
}
test("M1.7: each function's pane opens on its page: line, fields, recipe, journeys with status and last move, version 1", async () => {
  const c = await opened({ map: rtMap(), fnpage: fnPageOf });
  for (const fn of ["identity", "adaptation", "priority", "coordination", "audit"]){
    const name = fn.charAt(0).toUpperCase() + fn.slice(1);
    const html = await fnCard(c, fn);
    assert.ok(new RegExp("<div class=\"o2vh\"><b>" + name + "</b>").test(html), fn + ": the first tab keeps its name");
    assert.ok(html.indexOf("<h3>The function</h3><div class=\"dpbig\">" + name + "&#39;s one line") >= 0 || html.indexOf("<h3>The function</h3><div class=\"dpbig\">" + name + "'s one line") >= 0, fn + " line");
    assert.ok(html.indexOf("<h3>The Product build template</h3>") >= 0, fn + " template");
    assert.ok(/<div class="dpk">Done when<\/div><div class="o2quiet dpq">not set yet<\/div>/.test(html), fn + ": a placeholder is one quiet line");
    assert.ok(/<div class="dpk">Hears<\/div><div class="wbstep"><span class="wbchip">Take a request<\/span>/.test(html), fn + " hears");
    assert.ok(/<div class="dpk">Limit<\/div><div class="dpbar"><i style="width:25%"><\/i><\/div>/.test(html), fn + ": the limit is a bar");
    assert.ok(/<div class="wbrec"><span class="wbchip on">Code<\/span><span>Say whether it may start<\/span><span class="wbrung"/.test(html), fn + ": a step by code, on its rung");
    assert.ok(/<details class="wbrecg wb"><summary>Take a request<\/summary><div class="wbrec"><span class="wbchip">AI<\/span><span>Read the words<\/span>/.test(html), fn + ": the AI inside, grouped by what it hears");
    assert.ok(/<span class="wbchip">Person<\/span><span>Ask the owner<\/span>/.test(html), fn + ": a person");
    FN_JOURNEYS[fn].forEach(([id, jn], i) => {
      const row = new RegExp('<div class="dprow wbjrn"><span class="dpdot[^"]*"></span><span><span class="wbjid">' + id + '</span>' + jn.replace(/[?]/g, "\\?") + ' <span class="wbchip">([^<]+)</span>(<div class="dpchk">([^<]*)</div>)?').exec(html);
      assert.ok(row, fn + " journey " + id);
      assert.strictEqual(row[1], i === 0 ? "done" : (i === 1 ? "waiting" : (i === 4 ? "later" : "not run yet")), id + " status");
      if (i < 2) assert.ok(/ moved · \d\d:\d\d$/.test(row[3]), id + " last move and its time: " + row[3]);
    });
    assert.ok(html.indexOf("<h3>Version 1</h3><div class=\"dpfline\">" + name + "&#39;s version 1") >= 0 || html.indexOf("<h3>Version 1</h3><div class=\"dpfline\">" + name + "'s version 1") >= 0, fn + " version 1");
    const t = words(html);
    assert.ok(!/charter/i.test(t) && !/internal system/i.test(t), fn + ": no charter, no internal system");
    assert.ok(!/\/api\/|\.json|\.md\b|\/Users\//.test(t), fn + ": no path");
  }
  assert.deepStrictEqual(readsOf(c, /\/functions\//).sort(), ["identity", "adaptation", "priority", "coordination", "audit"].map(f => "/api/native/r3/functions/" + f).sort(),
    "each page read once, from its own route");
  /* a department of the first build keeps its card as it was */
  const old = await opened();
  const oh = await fnCard(old, "priority");
  assert.ok(!/<h3>The function<\/h3>|wbjrn/.test(oh) && readsOf(old, /\/functions\//).length === 0);
});
/* PRD M1.7 (round 4, gap 5): on the engine runtime the registry's department card is gone, and what Identity holds is
   drawn from the record instead, once: by Identity's page from its own record (S5, M3.7) when the read carries it, and
   otherwise from the map read: the goal, the done-when and each rule with its tag as a chip in the pane's word. */
test("M1.7: Identity's pane shows the goal, done-when and each rule with its tag from the record, once, and repaints when they move", async () => {
  const map = rtMap();
  map.rules = [{ tag: "go", line: "Plan, write and check inside the record" }, { tag: "refuse", line: "Never publish a build whose check failed" }];
  /* a page read with no record of Identity's own: the map read draws them under the page */
  const c = await opened({ map, fnpage: fnPageOf });
  const html = await fnCard(c, "identity");
  assert.ok(/<h3>The department<\/h3><div class="dpid"><div class="dpcell"><div class="dpk">Goal<\/div><div class="dpbig">A live website for City Care Hospital<\/div>/.test(html), "the goal");
  assert.ok(/<div class="dpk">Done when<\/div><div class="dpbig">Every page checked and live<\/div>/.test(html), "the done-when");
  assert.ok(html.indexOf('<div class="wbidrule"><span class="wbchip on">go</span><span>Plan, write and check inside the record</span></div>') >= 0 &&
            html.indexOf('<div class="wbidrule"><span class="wbchip ask">never</span><span>Never publish a build whose check failed</span></div>') >= 0,
            "each rule with its tag, a chip in the pane's word: a refuse rule reads never, as on S5");
  assert.ok(!/class="dptag/.test(html), "never the registry's badge, which says refuse");
  assert.strictEqual((html.match(/Never publish a build whose check failed/g) || []).length, 1, "a rule once");
  assert.ok(!/No owner yet/.test(html) && (html.match(/Sankalp/g) || []).length === 1, "the owner once, on Control");
  /* the pane repaints when what Identity holds moves, and not when the read says the same */
  const a = c.wbSig(map);
  assert.strictEqual(a, c.wbSig(JSON.parse(JSON.stringify(map))), "the same read paints nothing");
  assert.notStrictEqual(a, c.wbSig(Object.assign({}, map, { rules: map.rules.concat([{ tag: "ask", line: "Ask before a new page goes live" }]) })), "a new rule paints");
  assert.notStrictEqual(a, c.wbSig(Object.assign({}, map, { done: "Every page checked, live and read" })), "a new done-when paints");
  assert.notStrictEqual(a, c.wbSig(Object.assign({}, map, { goal: "A live website for City Care Clinic" })), "a new goal paints");
  /* Identity's page carries its own record (S5): the goal, the done-when items and the rules are on top, once, and the
     map read's department card is not drawn under them */
  const j2 = { standard: { met: true, missing: [], rows: [{ id: "goal", says: "The goal names what and for whom", state: "met", note: "as you said it" }] },
    goal: "A live website for City Care Hospital", done_items: [{ id: "D1", text: "Every page checked and live", how: "code", level: "outcome", confirm: null }],
    rules: map.rules.map(r => Object.assign({ by: "the template", since: null }, r)), open_question: null, conflicts: [] };
  const own = await fnCard(await opened({ map, fnpage: fn => Object.assign(fnPageOf(fn), fn === "identity" ? { j2: JSON.parse(JSON.stringify(j2)) } : {}) }), "identity");
  assert.ok(own.indexOf("<h3>Enough to work?</h3>") >= 0 && own.indexOf("<h3>The department</h3>") < 0, "S5 on top, no second card");
  for (const t of ["Every page checked and live", "Plan, write and check inside the record", "Never publish a build whose check failed"])
    assert.strictEqual((own.match(new RegExp(t, "g")) || []).length, 1, t + ", once");
  assert.ok(own.indexOf('<span class="wbchip ask">never</span><span>Never publish a build whose check failed</span><span class="dpchk">the template</span>') >= 0, "S5's rule row");
  /* (m1fix, gap 5 residual) a record from before Root drafted done-when items keeps its done line: S5 draws that line,
     once, as the record has it, never 'No done-when items yet' and never 'Drafted by Root at birth' */
  const before = Object.assign(JSON.parse(JSON.stringify(j2)), { done: "Every page checked and live", done_items: [] });
  const old5 = await fnCard(await opened({ map, fnpage: fn => Object.assign(fnPageOf(fn), fn === "identity" ? { j2: JSON.parse(JSON.stringify(before)) } : {}) }), "identity");
  assert.ok(/<h3>Done when<\/h3><div class="dpbig">Every page checked and live<\/div>/.test(old5), "the done line, on S5's Done when card");
  assert.strictEqual((old5.match(/Every page checked and live/g) || []).length, 1, "the done line, once");
  assert.ok(old5.indexOf("No done-when items yet") < 0 && old5.indexOf("Drafted by Root at birth") < 0 && old5.indexOf("<h3>The department</h3>") < 0,
            "never 'no items', never 'drafted by Root', and no second card");
  assert.ok(/No done-when items yet/.test(c.wbIdentityHtml("r3", Object.assign({}, before, { done: "" }))), "a record with neither says so");
  assert.notStrictEqual(JSON.stringify(c.wbIdSig(before)), JSON.stringify(c.wbIdSig(Object.assign({}, before, { done: "Every page checked, live and read" }))),
                        "a new done line paints");
  /* while the page is read, nothing is drawn twice; a department off the runtime keeps the registry's card (20-dept.js),
     so this one draws none */
  const wait = await opened({ map });
  vm.runInContext("wbS().map['r3'] = " + JSON.stringify(map) + "; wbS().fnpage = {};", wait);
  assert.ok(wait.wbFnExtra("identity", map).indexOf("<h3>The department</h3>") < 0, "the page not read yet: nothing to draw twice");
  const old = await opened();
  vm.runInContext("wbS().fnpage['r3:identity'] = " + JSON.stringify(fnPageOf("identity")) + ";", old);
  assert.ok(old.wbFnExtra("identity", Object.assign({}, map, { runtime: 1 })).indexOf("<h3>The department</h3>") < 0, "off the runtime the registry card draws it");
});
/* PRD M1.8 (S2, proposal built on MK-8): All five. Five cards in canonical order, each with its mark, a state word and
   a Today bar, then Between them; no digits at rest outside titles; the states the screen names; the arrow keys. */
const FV_BOARD = { any: true, ideas: [], threads: [
  { id: "x-9", topic: "line", protocol: "propose", state: "completed", decider: "Priority", opened: AT, closed: AT, outcome: null, bounds: {}, hops: 2, default: "cancel", posts: [
    { n: 7, src: "Adaptation", dst: ["Priority"], msg_type: "propose", at: AT, word: "line", line: "the next round" },
    { n: 8, src: "Priority", dst: ["Adaptation"], msg_type: "accept-proposal", at: AT, word: "line", line: "said yes to the round" }] },
  { id: "x-8", topic: "request", protocol: "request", state: "completed", decider: "Identity", opened: AT, closed: AT, outcome: null, bounds: {}, hops: 0, default: "failure", posts: [
    { n: 5, src: "Owner", dst: ["Identity"], msg_type: "request", at: AT, word: "request", line: "a careers page" },
    { n: 6, src: "Identity", dst: ["Adaptation"], msg_type: "request", at: AT, word: "line", line: "the next thing to correct" },
    { n: 4, src: "Coordination", dst: ["Identity"], msg_type: "inform", at: AT, word: "alarm", line: "Write ran past its window" }] }] };
/* the same messages as the read says them (functions_view.py _between): newest first, each the act its function did, in
   the owner's words, and what it carried as its detail, for the hover */
const FV_BETWEEN = [
  { n: 8, thread: "x-9", from: "Priority", to: ["Adaptation"], act: "said yes to the plan", detail: "said yes to the round", at: AT },
  { n: 7, thread: "x-9", from: "Adaptation", to: ["Priority"], act: "proposed the plan to Priority", detail: "the next round", at: AT },
  { n: 6, thread: "x-8", from: "Identity", to: ["Adaptation"], act: "asked Adaptation for the plan", detail: "the next thing to correct", at: AT }];
async function allFive(o){
  const c = await v2(Object.assign({ map: rtMap(), board: FV_BOARD }, o));
  click(c, { wbtab: "five" }); await sleep();
  return [c, await paint(c)];
}
test("M1.8: All five is five cards in order, each with its mark, a state word and a bar, then Between them", async () => {
  const fv = fvOf({ states: { Identity: "waiting_on_you", Adaptation: "waiting", Priority: "quiet", Coordination: "working", Audit: "fault" },
                    lines: { Identity: "May the reviews show first names?", Coordination: "Write's turn", Audit: "Audit has not read Live site v1" },
                    waits: { Adaptation: "Priority" }, last: { Priority: { what: "said yes to round two", at: AT },
                                                               Coordination: { what: "gave Write the turn", detail: "after Site plan v2", at: AT } },
                    cycle: { says: "Write is working", needs_you: true, asks: 1 }, between: FV_BETWEEN });
  const [c, html] = await allFive({ fv });
  assert.ok(/<div class="o2vh"><b>All five<\/b>/.test(html) && /class="o2viewer dpviewer dp wb fv"/.test(html), "the viewer, a size container");
  const cards = html.match(/<button type="button" class="fvcard fn-(\w+) wb[^"]*" data-wbfn="\1"[^>]*>[\s\S]*?<\/button>(?=<button type="button" class="fvcard|<div class="fvcard fvbetween)/g) || [];
  assert.deepStrictEqual(cards.map(x => /class="fvcard fn-(\w+)/.exec(x)[1]), ["identity", "adaptation", "priority", "coordination", "audit"], "five, in order");
  const want = { identity: "waits on you", adaptation: "waiting", priority: "quiet", coordination: "working", audit: "fault" };
  cards.forEach(x => {
    const fn = /class="fvcard fn-(\w+)/.exec(x)[1];
    assert.ok(new RegExp('<svg class="dpfnmk fn-' + fn + '"').test(x), fn + " mark");
    assert.ok(x.indexOf('aria-label="' + fn.charAt(0).toUpperCase() + fn.slice(1) + " · " + want[fn] + '"') >= 0, fn + " says its state");
    assert.ok(/<span class="fvtoday"><span class="dpk">Today<\/span><div class="dpbar"><i style="width:10%"><\/i><\/div><\/span>/.test(x), fn + " Today bar");
  });
  assert.ok(/<span class="wbchip ask" data-wbtab="chat">waits on you<\/span> May the reviews show first names\?/.test(cards[0]), "the ask, and the way to it");
  assert.ok(/<span class="wbchip" data-wbfn="priority">waits on Priority<\/span>/.test(cards[1]), "a wait opens the function it waits on");
  assert.ok(/<b class="dpfnb block" aria-hidden="true">!<\/b>/.test(cards[4]) && /fault<\/b>: Audit has not read Live site v1/.test(cards[4]), "a fault with '!' and the reason");
  assert.ok(/last: said yes to round two · \d\d:\d\d/.test(cards[2]), "the last act and its time");
  assert.ok(/<div class="dpchk" title="gave Write the turn: after Site plan v2">last: gave Write the turn · \d\d:\d\d<\/div>/.test(cards[3]),
    "the act at rest, what it acted on in the hover: " + cards[3]);
  assert.ok(/<div class="fvprog wb"><div class="fvsays"><i class="dpdot breath"[^>]*><\/i><b aria-live="polite">Write is working<\/b><span class="wbchip ask">needs you<\/span>/.test(html), "the progress words, full form");
  assert.strictEqual((html.match(/<span class="fvpill /g) || []).length, 8, "eight step pills");
  assert.ok(/<span class="fvpill now" title="Run · Run happened · \d\d:\d\d"><i class="dpdot breath"/.test(html) && /<span class="fvpill skip" title="[^"]*">- Settle<\/span>/.test(html), "now breathes; Settle skipped");
  /* Between them: the last three messages between the functions, newest first, and the way to all of them */
  const between = /<div class="fvcard fvbetween wb">([\s\S]*)$/.exec(html)[1];
  const msgs = (between.match(/data-wbthread="[^"]+"><i class="fvbar fn-(\w+)"><\/i><span class="wbchip">(\w+)<\/span>/g) || []).map(x => /class="wbchip">(\w+)</.exec(x)[1]);
  assert.deepStrictEqual(msgs, ["Priority", "Adaptation", "Identity"], "three, newest first, the owner's words not among them");
  /* each row is what the function did, never the words its message carried (round 2, gap 5): those are its hover */
  assert.ok(/<span class="dpchk" title="the next round">proposed the plan to Priority<\/span>/.test(between), between);
  assert.ok(/<span class="dpchk" title="the next thing to correct">asked Adaptation for the plan<\/span>/.test(between), between);
  assert.ok(/data-wbtab="board">All messages &rsaquo;<\/button>/.test(between));
  /* no digits at rest outside titles (times are clocks, not counts; v1 is a name) */
  const t = words(html.replace(/ title="[^"]*"/g, "").replace(/ aria-label="[^"]*"/g, "")).replace(/\bv\d+\b/g, "");
  assert.ok(!/\d/.test(t), "a digit at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  /* a card opens its pane; Between them opens the board at that message */
  click(c, { wbfn: "coordination" });
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "coordination");
  click(c, { wbtab: "board", wbthread: "x-9" });
  assert.strictEqual(vm.runInContext("S.wb.tab['r3'] + ':' + S.wb.thread['r3']", c), "board:x-9");
});
/* M1.8 (round 1, gap 7): the record's own lines carry counts (a fault's why, a run's line, the owner's words), and All
   five prints them at rest through the Map's own rule (23-screens.js wb2Rest): a line with a count gives its act before
   the colon, or nothing, and the whole line is the hover. Names (v1) stay. */
test("M1.8: a fault, a last act and a line between them that carry a count keep it on the hover, never at rest", async () => {
  const fv = fvOf({ states: { Identity: "waiting_on_you", Priority: "fault", Coordination: "working", Audit: "fault" },
                    lines: { Identity: "May the reviews show the 12 doctors' first names?", Priority: "Answer a proposal: page 3 of 8 failed its check",
                             Coordination: "Write is on page 3 of 8", Audit: "Audit has not read Live site v1" },
                    last: { Adaptation: { what: "took Priority's ask for less: keep 2 of 4 engines", at: AT },
                            Identity: { what: "took the owner's words", detail: "A site for Class 8", at: AT }, Priority: { what: "said no 3 times", at: AT } } });
  fv.between = JSON.parse(JSON.stringify(FV_BETWEEN));
  fv.between[0].detail = "the envelope has room for 3 of them";
  const [, html] = await allFive({ fv });
  const card = fn => (html.match(new RegExp('<button type="button" class="fvcard fn-' + fn + ' wb[^"]*"[^>]*>[\\s\\S]*?</button>')) || [""])[0];
  assert.ok(/<span class="fvnow" title="May the reviews show the 12 doctors(&#39;|')s? first names\?"><span class="wbchip ask" data-wbtab="chat">waits on you<\/span> <\/span>/.test(card("identity")),
    "the owner's ask with a count: the chip at rest, the words on the hover: " + card("identity"));
  assert.ok(/<span class="fvnow" title="Answer a proposal: page 3 of 8 failed its check"><b>fault<\/b>: Answer a proposal<\/span>/.test(card("priority")), "the act before the colon");
  assert.ok(/<span class="fvnow" title="Write is on page 3 of 8"><b>working<\/b><\/span>/.test(card("coordination")), "a line that is all count: the word alone");
  assert.ok(/<b>fault<\/b>: Audit has not read Live site v1<\/span>/.test(card("audit")), "a name stays");
  assert.ok(/title="took Priority(&#39;|')s ask for less: keep 2 of 4 engines">last: took Priority(&#39;|')s ask for less · \d\d:\d\d<\/div>/.test(card("adaptation")), card("adaptation"));
  assert.ok(/title="took the owner(&#39;|')s words: A site for Class 8">last: took the owner(&#39;|')s words · /.test(card("identity")), "the owner's words are the hover");
  assert.ok(/title="said no 3 times">last: \d\d:\d\d<\/div>/.test(card("priority")), "an act that is all count: its time alone");
  assert.ok(/<span class="dpchk" title="the envelope has room for 3 of them">said yes to the plan<\/span><\/button>/.test(html), "between them: the act at rest, the line on the hover");
  const t = words(html.replace(/ title="[^"]*"/g, "").replace(/ aria-label="[^"]*"/g, "")).replace(/\bv\d+\b/g, "");
  assert.ok(!/\d/.test(t), "a digit at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  /* the Map's boxes keep the same rule: the act before the colon, the whole line on the hover */
  const [, map] = await mapWith({ fv });
  assert.ok(/<text class="ln" x="42" y="55">Answer a proposal<\/text>/.test(fnBox(map, "priority")[2]), "the Map's box: " + fnBox(map, "priority")[2]);
  assert.ok(!/class="ln"/.test(fnBox(map, "coordination")[2]) && /<title>Coordination · working · Write is on page 3 of 8<\/title>/.test(map), "all count: the hover");
});
test("M1.8: the list carries All five first; loading, error, not started and stopped read as the screen names them", async () => {
  let [c, html] = await allFive({ fv: () => new Promise(() => {}) });
  assert.strictEqual((html.match(/<div class="fvcard fvskel">/g) || []).length, 5, "five skeleton cards");
  [c, html] = await allFive({ fv: () => Promise.reject(new Error("down")) });
  assert.ok(/<div class="fvgrid fverr"><div class="o2quiet dpq">Could not read<\/div><button type="button" class="o2more wb" data-wbfvretry="1">Try again<\/button>/.test(html) && !/fvcard/.test(html), "the grid gives way to one line");
  [c, html] = await allFive({ fv: fvOf({ cycle: { state: "not_started", says: "Not started", steps: [] } }) });
  assert.ok(/<b>Not started<\/b>/.test(html) && /data-dpj2start="1">Start<\/button>/.test(html), "Start, for a department born before J2");
  [c, html] = await allFive({ map: rtMap({ stopped: true }), fv: fvOf({ stopped: true, states: { Coordination: "working" }, cycle: { state: "stopped", says: "Stopped by you" } }) });
  assert.ok(/<b>Stopped by you<\/b>/.test(html) && /data-wbresume="1"[^>]*>Start</.test(html), "Stopped by you, with Start");
  assert.strictEqual((html.match(/class="fvcard fn-\w+ wb still"/g) || []).length, 5, "the cards at seventy percent");
  assert.ok(!/dpdot breath/.test(html.slice(html.indexOf("fvgrid"))), "nothing breathes when stopped");
  [c, html] = await allFive({ fv: fvOf({}) });
  const list = c.dpListHtml(WEB, {}, null, null);
  assert.ok(/<div class="o2gl dpgl">Functions<\/div><button type="button" class="o2li dpli on" data-wbtab="five"><span>All five<\/span><\/button><button type="button" class="o2li dpli dpfn" data-dptab="identity"/.test(list), "All five, first, lit while open");
  /* the compact form, in the strip after the parent's name; it opens All five */
  const strip = c.fvStripHtml("r3");
  assert.ok(/^<button type="button" class="fvline wb" data-wbtab="five"><i class="dpdot breath"[^>]*><\/i><span>The work is running<\/span><\/button>$/.test(strip), strip);
  assert.strictEqual(c.fvStripHtml("r4"), "", "no read, no line");
  const old = await opened();
  assert.ok(!/data-wbtab="five"/.test(old.dpListHtml(WEB, {}, null, null)), "the first build has no All five");
});
test("M1.8: the arrow keys move between the cards, and the stylesheet block is tokens only and covers every class", async () => {
  const [c] = await allFive({ fv: fvOf({}) });
  const focused = [];
  const cards = FV_ORDER_T.map(fn => ({ dataset: { fvcard: fn }, focus(){ focused.push(fn); } }));
  const grid = { querySelectorAll(){ return cards; } };
  cards.forEach(k => { k.closest = sel => sel === ".fvgrid" ? grid : null; });
  const key = (t, k) => { let stopped = false; (c.document.listeners.keydown || []).forEach(fn => fn({ key: k, target: t, preventDefault(){ stopped = true; } })); return stopped; };
  assert.ok(key(cards[0], "ArrowRight")); assert.ok(key(cards[4], "ArrowRight")); assert.ok(key(cards[0], "ArrowLeft")); assert.ok(key(cards[2], "ArrowDown"));
  assert.deepStrictEqual(focused, ["adaptation", "identity", "audit", "coordination"]);
  assert.ok(!key(cards[1], "Enter"), "Enter is the card's own: it is a button");
  const i = css.indexOf("/* ── All five (24-functions.js");
  assert.ok(i > 0, "the block exists");
  const block = css.slice(i, css.indexOf("/* ── Images for Shadow"));
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block), "a literal colour");
  const classes = new Set();
  let m;
  const re = /\bfv[a-z0-9]+\b/g, emitted = fvSrc.replace(/data-fv[a-z]+/g, "").replace(/\bfv[A-Z]\w*/g, "").replace(/\bds\.fv[a-z]+/g, "");
  while ((m = re.exec(emitted))) classes.add(m[0]);
  ["fvcard", "fvgrid", "fvpill", "fvprog"].forEach(k => assert.ok(classes.has(k), "parsed " + k));
  [...classes].forEach(k => assert.ok(block.indexOf("." + k) >= 0, "no rule for ." + k));
  const a = panelHtml.indexOf("/static/js/23-screens.js"), b = panelHtml.indexOf("/static/js/24-functions.js"), t = panelHtml.indexOf('<script src="/static/js/09-tail.js');
  assert.ok(a > 0 && b > a && t > b, "loaded after 23, before the tail");
});
const FV_ORDER_T = ["identity", "adaptation", "priority", "coordination", "audit"];
/* M1 acceptance, line 1 (round 1, gap 2): the Map, the list, All five and each pane agree with each other in every J2
   state. One functions read per state, as functions_view.py gives it (test_functions_view.py F1 pins the states), feeds
   all four surfaces; each prints the read's own word for each function, stopped and done included. A wait on another
   function is its 'waits on' chip on the card, the word's own long form. */
const FV_BY_STATE = {
  assessing: { states: { Identity: "working" } }, waiting: { states: { Identity: "waiting_on_you" } },
  adapting: { states: { Adaptation: "working" } }, bargaining: { states: { Priority: "working", Adaptation: "waiting" } },
  closing: { states: { Identity: "working", Adaptation: "waiting" }, waits: { Adaptation: "Identity" } },
  checking: { states: { Adaptation: "waiting" }, waits: { Adaptation: "Root" } }, running: { states: { Coordination: "working" } },
  pursuing: { states: { Identity: "waiting_on_you" } }, blocked: { states: { Identity: "waiting_on_you" } },
  stopped: { stopped: true }, done: {},
  /* the goal reached, then switched off on the Map: the cycle stays done, the department is stopped (round 2, gap 7) */
  done_switched_off: { stopped: true, cycle: "done" } };
test("M1: the Map, the list, All five and each pane print the same word for each function in every J2 state", async () => {
  for (const state of Object.keys(FV_BY_STATE)){
    const o = FV_BY_STATE[state];
    const fv = fvOf(Object.assign({}, o, { cycle: { state: o.cycle || state, says: state } }));
    const page = fn => Object.assign(fnPageOf(fn), { node: fv.functions.filter(x => x.fn === fn)[0] });
    const map = rtMap({ stopped: !!o.stopped });
    const c = await v2({ map, fv, fnpage: page, board: FV_BOARD });
    click(c, { wbtab: "map" }); await sleep();
    const mapHtml = await paint(c);
    for (let k = 0; k < 2; k++){ c.dpListHtml(WEB, {}, null, null); await sleep(); await sleep(); }
    const listHtml = c.dpListHtml(WEB, {}, null, null);
    click(c, { wbtab: "five" }); await sleep();
    const fiveHtml = await paint(c);
    for (const node of fv.functions){
      const fn = node.fn, name = node.name, want = node.word;
      const box = /<text class="st" x="\d+" y="40">([^<]+)<\/text>/.exec(fnBox(mapHtml, fn)[2] || "");
      assert.strictEqual(box && box[1], want, state + ": the Map's " + fn);
      const row = new RegExp('data-dptab="' + fn + '" aria-label="' + name + ' · ([^"]+)"').exec(listHtml);
      assert.strictEqual(row && row[1], want, state + ": the list's " + fn);
      const card = (fiveHtml.match(new RegExp('<button type="button" class="fvcard fn-' + fn + ' wb[^"]*"[^>]*>[\\s\\S]*?</button>')) || [""])[0];
      assert.ok(card.indexOf('aria-label="' + name + " · " + want + '"') >= 0, state + ": All five's " + fn + " names it");
      const shown = /<span class="fvnow"[^>]*>(?:<b>([^<]+)<\/b>|<span class="wbchip[^"]*"[^>]*>([^<]+)<\/span>)/.exec(card);
      assert.ok(shown, state + ": All five's " + fn + " shows a word");
      if (shown[1] !== undefined) assert.strictEqual(shown[1], want, state + ": All five's " + fn);
      else assert.strictEqual(shown[2], want === "waiting" ? "waits on " + node.waits_on : want, state + ": All five's " + fn + " chip");
      const pane = await fnCard(c, fn);
      const now = /<h3>The function<\/h3><div class="dpbig">[^<]*<\/div><div class="dprow"><span class="dpdot[^"]*"><\/span><span>([^<]+)/.exec(pane);
      assert.strictEqual(now && now[1].toLowerCase(), want, state + ": " + fn + "'s pane");
    }
    if (o.stopped) assert.ok(fv.functions.every(x => x.word === "stopped"), "stopped is one word");
  }
});
test("V2 root: Root's Map is its departments as boxes, each with a state dot and its line of work as a strip, and a way to a new one", async () => {
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.live = false;
  const c = await v2({ map: rm, chat: ROOT_CHAT });
  click(c, { wbtab: "map" }); await sleep();
  const html = await paint(c);
  assert.ok(/<button type="button" class="wb2dept wb" data-wb2go="r5"><b><span class="dpdot [^"]*"><\/span>City Care Hospital Website<\/b><span class="wb2spark">/.test(html), "a department box");
  assert.ok(/class="wb2dept wb2new wb" data-wbtab="chat"/.test(html), "a new one, in Chat");
  assert.ok(!/<svg/.test(html), "no line of work of its own");
});

test("V2 board: one thread in time order, who spoke as the name, the act as a word, no arrows, one way to speak", async () => {
  const c = await v2({ map: rtMap() });
  click(c, { wbtab: "board" }); await sleep();
  const html = await paint(c);
  assert.strictEqual((html.match(/<div class="turn wbturn">/g) || []).length, 3, "every post, one thread");
  assert.ok(html.indexOf('<div class="who who-you">You</div><div class="u md">Which page lists the doctors?<span class="dpchk">asks · ') <
            html.indexOf('<div class="who who-ai">Identity</div><div class="a">The Doctors page lists them<span class="dpchk">tells · '), "in order");
  assert.ok(!/wbarrow/.test(html) && !/wbthreads/.test(html) && !/<h3>Replies<\/h3>/.test(html));
  assert.strictEqual((html.match(/<textarea/g) || []).length, 1);
});

test("V12: the second design's stylesheet block is tokens only and covers every class 23-screens.js emits", () => {
  const i = css.indexOf("/* ── the second design (23-screens.js)");
  assert.ok(i > 0, "the block exists");
  const block = css.slice(i);
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block), "a literal colour");
  const classes = new Set();
  let m;
  const re = /\bwb2[a-z0-9]*\b/g;
  const emitted = sxSrc.replace(/data-wb2?[a-z]+/g, "").replace(/\bds\.wb2?[a-z]+/g, "").replace(/\bwb2[A-Z]\w*/g, "");
  while ((m = re.exec(emitted))) classes.add(m[0]);
  classes.delete("wb2");
  [...classes].forEach(k => assert.ok(block.indexOf("." + k) >= 0, "no rule for ." + k));
  const a = panelHtml.indexOf("/static/js/22-website.js"), b = panelHtml.indexOf("/static/js/23-screens.js"), t = panelHtml.indexOf("/static/js/09-tail.js");
  assert.ok(a > 0 && b > a && t > b, "loaded after 22, before the tail");
});

/* M1.3: the five function colours, in both themes, read off panel.css and measured by the accent picker's own rule
   (07-loaders.js _lum/_contrast, WCAG relative luminance). A colour with alpha is laid over the ground it sits on:
   the -bg tints and the dark --acc-bg over both --card and --surface, and the worse of the two is the one that counts. */
const loadersSrc = read("07-loaders.js");
const ACC_RULE = (() => {
  const box = {};
  vm.createContext(box);
  vm.runInContext(/function _lum\([\s\S]*?\n\}\n/.exec(loadersSrc)[0] + /function _contrast\([\s\S]*?\n\}\n/.exec(loadersSrc)[0], box);
  return box;
})();
function cssBlock(sel){
  /* every declaration under one theme selector, in file order (a later block adds to an earlier one) */
  const out = {};
  let i = 0;
  while ((i = css.indexOf(sel, i)) >= 0){
    const open = css.indexOf("{", i + sel.length - 1), close = css.indexOf("}", open);
    css.slice(open + 1, close).split(";").forEach(d => { const m = /^\s*(--[\w-]+)\s*:\s*([^;]+?)\s*$/.exec(d); if (m) out[m[1]] = m[2]; });
    i = close;
  }
  return out;
}
const hex2rgb = h => [1, 3, 5].map(k => parseInt(h.slice(k, k + 2), 16));
const rgb2hex = c => "#" + c.map(v => Math.round(v).toString(16).padStart(2, "0")).join("");
function solid(v, ground){
  const m = /^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([.\d]+)\)$/.exec(v);
  if (!m) return [v];
  const a = Number(m[4]), fg = [m[1], m[2], m[3]].map(Number);
  return ground.map(g => rgb2hex(fg.map((x, k) => x * a + hex2rgb(g)[k] * (1 - a))));
}
test("M1.3: the five function colours pass 4.5:1 on --card, --surface, --acc-bg and their own -bg, in both themes", () => {
  const themes = { dark: cssBlock(':root,[data-theme="dark"]{'), light: cssBlock('[data-theme="light"]{'),
                   system: cssBlock("@media (prefers-color-scheme:light){:root:not([data-theme]){") };
  const media = css.slice(css.indexOf("@media (prefers-color-scheme:light){:root:not([data-theme]){"));
  ["identity", "adaptation", "priority", "coordination", "audit"].forEach(fn => {
    ["", "-bg", "-line"].forEach(k => {
      assert.ok(themes.dark["--fn-" + fn + k], "dark --fn-" + fn + k);
      assert.ok(themes.light["--fn-" + fn + k], "light --fn-" + fn + k);
    });
    assert.ok(media.indexOf("--fn-" + fn + ":") >= 0, "the system light block names --fn-" + fn);
  });
  let n = 0;
  Object.keys(themes).filter(t => t !== "system").forEach(theme => {
    const T = themes[theme], ground = [T["--card"], T["--surface"]];
    ["identity", "adaptation", "priority", "coordination", "audit"].forEach(fn => {
      const ink = T["--fn-" + fn];
      assert.ok(/^#[0-9a-fA-F]{6}$/.test(ink), theme + " " + fn + " is one hex: " + ink);
      const on = [].concat(solid(T["--card"], ground), solid(T["--surface"], ground), solid(T["--acc-bg"], ground), solid(T["--fn-" + fn + "-bg"], ground));
      on.forEach(bg => {
        const r = ACC_RULE._contrast(ink, bg);
        assert.ok(r >= 4.5, theme + " --fn-" + fn + " on " + bg + " is " + r.toFixed(2) + ":1");
      });
      n++;
    });
  });
  assert.strictEqual(n, 10, "all ten colours measured");
  /* a function colour never fills a state dot; waiting on another function is a hollow muted ring, never amber */
  assert.ok(/\.dpdot\.wait\{background:transparent;box-shadow:inset 0 0 0 1\.5px var\(--muted\)\}/.test(css), "the waiting ring");
  assert.ok(!/\.dpdot[^{]*\{[^}]*--fn-/.test(css), "no state dot wears a function colour");
});

test("W45: J1 shows Root's one question and final department tell without renaming Root", () => {
  const c = fresh();
  const q = c.wbChatTurn({ src: "Identity", msg_type: "inform", at: AT, word: "question",
    line: "What should this department achieve?" }, true);
  const done = c.wbChatTurn({ src: "Identity", msg_type: "inform", at: AT, word: "department",
    line: "Acme <Learning> Website is set up with Plan, Write, Check, Publish. First: Plan.",
    dept: "r5", name: "Acme <Learning> Website" }, false);
  assert.ok(/<div class="who who-ai">Root<\/div>/.test(q), "the helper is Root");
  assert.strictEqual((q.match(/\?/g) || []).length, 1, "one question in the turn");
  assert.ok(/Acme/.test(done) && /Website is set up/.test(done) && !/Acme <Learning>/.test(done), "the final tell is escaped");
  assert.ok(/data-wbopen="r5">[^<]*Acme[^<]*Website<\/button>/.test(done), "the child opens once from its chip");
  assert.ok(!/Sutra<\/div>/.test(q + done), "J1 does not alias Root as Sutra");
});

test("W46: J1.5 the second department is offered as one chip that carries its own words; a turn with no offer has none", () => {
  const c = fresh();
  const plain = c.wbChatTurn({ src: "Identity", msg_type: "inform", at: AT, word: "department",
    line: "Acme Website is set up with Plan, Write, Check, Publish. First: Plan.", dept: "r5", name: "Acme Website" }, false);
  const offered = c.wbChatTurn({ src: "Identity", msg_type: "inform", at: AT, word: "department",
    line: "Acme Website is set up. You also asked for a second department.", dept: "r5", name: "Acme Website",
    offer: { label: "sales <CRM> for the team", words: "Set up another department: sales \"CRM\" for the team" } }, false);
  assert.ok(!/data-wbsay/.test(plain), "no offer, no chip");
  assert.strictEqual((offered.match(/data-wbsay=/g) || []).length, 1, "one chip");
  assert.ok(/data-wbsay="Set up another department: sales &quot;CRM&quot; for the team"/.test(offered), "the chip carries the words, escaped");
  assert.ok(/>Set up: sales &lt;CRM/.test(offered) && !/<CRM/.test(offered), "the chip reads what it sets up, escaped");
});

/* ── S16: a function's Settings > Instructions (PRD M2.3) ─────────────────── */
test("S16: a function's Settings lists its files by name with their first line and Change; Send files the one ask; the row then waits for the stamp; no path", async () => {
  const c = await opened({ map: rtMap() });
  for (const fn of Object.keys(INS)){
    vm.runInContext("dpS().pane['r3:" + fn + "'] = 'settings';", c);
    const html = await fnCard(c, fn);
    const at = html.indexOf("<h3>Instructions</h3>");
    assert.ok(at >= 0 && at < html.indexOf("<h3>Template</h3>"), fn + ": the instructions first, then the template");
    assert.ok(/<div class="wbpair"><div class="dpcard"><h3>Template<\/h3>/.test(html), fn + ": the template and the limit side by side");
    INS[fn].forEach(([file, lead]) => {
      assert.ok(html.indexOf('<div class="wbins"><b>' + file + '</b><span class="wbinslead">' + c.wbEsc(lead) + "</span>") >= 0, fn + " lists " + file + " with its first line");
      assert.ok(html.indexOf('data-wbins="' + file + '" data-wbinsfn="' + fn + '"') >= 0, fn + ": " + file + " has its Change");
    });
    assert.strictEqual((html.match(/<div class="wbins">/g) || []).length, INS[fn].length, fn + ": its files and no other");
    assert.strictEqual((html.match(/>as shipped</g) || []).length, INS[fn].length, fn + ": each as shipped");
    /* a file no run reads says so in words, and still takes the owner's change, as a note */
    assert.strictEqual((html.match(/>a note: no run reads it yet</g) || []).length, fn === "adaptation" ? 1 : 0, fn + ": only a file no run reads says so");
    if (fn === "adaptation")
      assert.ok(/<b>decide<\/b><span class="wbinslead">[^<]*<\/span><span class="wbchip" title="In this version the code makes this choice, so no run reads these words yet">a note: no run reads it yet<\/span><span class="wbchip">as shipped<\/span><button[^>]*data-wbins="decide"/.test(html),
                "decide: the code makes its choice, so no run reads it, said beside its Change");
    assert.ok(!/function-prompts|\.md\b|\/prompts\/|records home/.test(html), fn + ": a path on the screen");
    const t = words(html);
    assert.ok(!/charter|internal\s+system/i.test(t), fn + ": the screen's words");
    assert.ok(!/\d/.test(words(html.slice(at, html.indexOf('<div class="wbpair">')))), fn + ": a count in the instructions");
  }
  /* Change opens the sheet with the file's words; Send files the one ask; the sheet closes; the card stays open and is read again */
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", c);
  await fnCard(c, "identity");
  const before = readsOf(c, /\/steps\/Identity$/).length;
  assert.ok(click(c, { wbins: "take", wbinsfn: "identity" }));
  let sheet = c.wbInsSheetHtml();
  assert.ok(/role="dialog" aria-label="Change Identity · take"/.test(sheet) && /<h4>Identity · take<\/h4>/.test(sheet), "the sheet names the function and the file");
  assert.ok(/<textarea id="wbins-text" data-wbinstext="1"[^>]*>How to judge a request: go, ask or refuse\.\n\n## take\n\nThe words\.\n<\/textarea>/.test(sheet), "the file's words, to change");
  assert.ok(/data-wbins="send"[^>]*>Send</.test(sheet) && /data-wbins="close"[^>]*>Cancel</.test(sheet));
  assert.ok(!/function-prompts|\.md\b|\/prompts\//.test(sheet), "no path in the sheet");
  assert.strictEqual(c.calls.apiPost.length, 0, "opening the sheet changes nothing");
  const mine = "How to judge a request: go, ask or refuse.\n\n## take\n\nJudge it kindly.\n";
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbinstext: "1" }, value: mine } }));
  assert.ok(click(c, { wbins: "send" }));
  for (let i = 0; i < 6; i++) await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [
    { p: "/api/native/r3/instructions", body: { fn: "identity", file: "take", text: mine } }], "Send files the one ask, and nothing else");
  assert.strictEqual(c.wbInsSheetHtml(), "", "the sheet closes");
  assert.ok(readsOf(c, /\/steps\/Identity$/).length > before, "the card is read again");
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "identity", "the card stays open");
  /* Cancel files nothing */
  click(c, { wbins: "goal", wbinsfn: "identity" });
  click(c, { wbins: "close" });
  assert.strictEqual(c.wbInsSheetHtml(), "");
  assert.strictEqual(c.calls.apiPost.length, 1);
  /* the row of a change that waits: amber, its ? and its words, its time, and no second Change; one the owner changed reads your words */
  const w = await opened({ map: rtMap(), steps: { waits: "identity:completeness", mine: "identity:goal" } });
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", w);
  const html = await fnCard(w, "identity");
  assert.ok(/<b>completeness<\/b><span class="wbinslead">[^<]*<\/span><span class="wbinsnote"><i class="wbinsq">\?<\/i>your change waits for your stamp · \d\d:\d\d<\/span><\/div>/.test(html),
            "the row says the change waits, in words beside the mark");
  assert.ok(html.indexOf('data-wbins="completeness"') < 0 && html.indexOf('data-wbins="take"') >= 0, "no second change while one waits");
  assert.ok(/<b>goal<\/b><span class="wbinslead">[^<]*<\/span><span class="wbchip">your words<\/span>/.test(html), "a file the owner changed");
});

/* ── S16 as typed fields (PRD A1.16; UI-port package j2ui-shell X1 to X3), from the interface's own view ────────────
   test_fixtures/views/instructions.identity.json is instructions_view('identity') as layers/ and engine_runtime.py give
   it: groups with a lead, parts with what the app fills and what each answers with, fields with their bounds and words. */
const VIEWS_DIR = path.join(__dirname, "test_fixtures", "views");
const viewFile = f => JSON.parse(fs.readFileSync(path.join(VIEWS_DIR, f), "utf8"));
const settle = async () => { for (let i = 0; i < 6; i++) await sleep(); };
const TYPED = () => viewFile("instructions.identity.json");
async function typedCard(o, instr){
  const c = await opened(Object.assign({ map: rtMap(), steps: { instructions: instr || TYPED() } }, o || {}));
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", c);
  return [c, await fnCard(c, "identity")];
}
/* the fake elements a sheet's count and Send are found by, so the typing can be seen to move them */
function sheetEls(c){
  const els = {};
  c.document.getElementById = id => els[id] || (els[id] = { id, textContent: "", className: "", disabled: false, innerHTML: "" });
  return els;
}
const OPEN = (group, part, field) => ({ wbins: "change", wbinsfn: "identity", wbinsgroup: group, wbinspart: part, wbinsfield: field });
const typeInto = (c, ds, value) => (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: ds, value } }));
const TYPED_FIELDS = () => TYPED().reduce((n, g) => n + g.parts.reduce((m, p) => m + p.fields.length, 0), 0);

test("X1: Settings draws a card for each group of the typed view, in its order; each part with its fields, Change and the notes in words", async () => {
  const [c, html] = await typedCard();
  const groups = TYPED();
  const from = html.indexOf("<h3>" + c.wbEsc(groups[0].lead) + "</h3>"), to = html.indexOf('<div class="wbpair">');
  assert.ok(from >= 0 && to > from, "the groups come before the template and the limit");
  const section = html.slice(from, to);
  let at = -1;
  groups.forEach(g => {
    const i = section.indexOf("<h3>" + c.wbEsc(g.lead) + "</h3>");
    assert.ok(i > at, g.group + ": its card, after the one before it"); at = i;
    g.parts.forEach(p => {
      assert.ok(section.indexOf("<b>" + p.part + "</b>") >= 0, g.group + "/" + p.part + " is listed");
      p.fields.forEach(f => {
        const open = 'data-wbins="change" data-wbinsfn="identity" data-wbinsgroup="' + g.group + '" data-wbinspart="' + p.part + '" data-wbinsfield="' + f.field + '"';
        assert.ok(section.indexOf(open) >= 0, g.group + "/" + p.part + "/" + f.field + " has its Change");
        assert.ok(section.indexOf('<span class="wbinsf">' + c.wbInsLabel(p.part, f.field) + "</span>") >= 0, "and its name in words");
      });
      if (p.inputs.length) assert.ok(section.indexOf("filled by the app: " + p.inputs.map(c.wbEsc).join(", ")) >= 0, p.part + ": what the app fills");
      if (p.answers.length) assert.ok(section.indexOf("answers with: " + p.answers.map(c.wbEsc).join(", ")) >= 0, p.part + ": what it answers with");
    });
  });
  assert.strictEqual((section.match(/<h3>/g) || []).length, groups.length, "a card for each group and no other");
  assert.strictEqual((section.match(/data-wbins="change"/g) || []).length, TYPED_FIELDS(), "a Change for each field and no other");
  assert.strictEqual((section.match(/>as shipped</g) || []).length, TYPED_FIELDS(), "each as shipped");
  assert.strictEqual((section.match(/>filled by the app: /g) || []).length, groups.reduce((n, g) => n + g.parts.filter(p => p.inputs.length).length, 0));
  assert.ok(!/<h3>Instructions<\/h3>/.test(html), "the first design's one card is gone");
  assert.ok(!/function-prompts|\.md\b|\/prompts\/|records home|Return ONLY/.test(section), "no path and no answer's shape");
  const t = words(section);
  assert.ok(!/[{}]|"\w+"\s*:/.test(t), "no JSON on the screen");
  assert.ok(!/charter|internal\s+system/i.test(t), "the screen's words");
  assert.ok(!/\d/.test(t), "a count at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
});

test("X1: a part no run reads says so; a field that waits says so beside the amber mark with no second Change; one the owner changed reads your words; an earlier whole-file change reads kept as your note", async () => {
  const v = TYPED(), take = v.filter(g => g.group === "take")[0];
  take.parts.filter(p => p.part === "recognise")[0].read = false;
  const tk = take.parts.filter(p => p.part === "take")[0];
  tk.fields.filter(f => f.field === "task")[0].waits = { ask: "a-9", at: "2026-10-26T11:02:00+05:30" };
  tk.fields.filter(f => f.field === "guidance")[0].as_shipped = false;
  take.kept = { at: "2026-10-26T09:00:00+05:30" };
  const [c, html] = await typedCard({}, v);
  assert.ok(/<b>recognise<\/b><span class="wbchip" title="In this version the code makes this choice, so no run reads these words yet">a note: no run reads it yet<\/span>/.test(html), "a part no run reads");
  assert.strictEqual((html.match(/>a note: no run reads it yet</g) || []).length, 1, "only that one");
  assert.ok(/<span class="wbinsf">the task<\/span><span class="wbinslead">[^<]*<\/span><span class="wbinsnote"><i class="wbinsq">\?<\/i>your change waits for your stamp · \d\d:\d\d<\/span>/.test(html), "the waiting field");
  assert.ok(html.indexOf('data-wbinspart="take" data-wbinsfield="task"') < 0, "no second change while one waits");
  assert.ok(html.indexOf('data-wbinspart="take" data-wbinsfield="guidance"') >= 0);
  assert.ok(/<span class="wbinsf">the guidance<\/span><span class="wbinslead">[^<]*<\/span><span class="wbchip">your words<\/span><button/.test(html), "a field the owner changed");
  assert.ok(/<div class="wbinsk"><span class="wbchip">kept as your note<\/span><span class="dpchk">\d\d:\d\d<\/span><\/div>/.test(html), "the earlier whole-file change");
  assert.strictEqual((html.match(/kept as your note/g) || []).length, 1, "said once");
  /* a click on a field that waits opens nothing */
  assert.ok(click(c, OPEN("take", "take", "task")));
  assert.strictEqual(c.wbInsSheetHtml(), "");
});

test("X1: the words are escaped, a list reads as its items, and a part with no fields still shows its notes", async () => {
  const v = TYPED();
  v[0].parts[0].fields[0].value = "<img src=x onerror=alert(1)> & \"quoted\"";
  const [c, html] = await typedCard({}, v);
  assert.ok(html.indexOf("<img src=x") < 0 && html.indexOf("&lt;img src=x onerror=alert(1)") >= 0 && html.indexOf("&amp; &quot;quoted&quot;") >= 0, "escaped");
  assert.ok(/<span class="wbinsf">the skills<\/span><span class="wbinslead">recognise a task, a query, a directive, feedback or a new idea; judge a request against the goal; /.test(html), "the skills as one line");
  assert.ok(/<b>close<\/b><\/div>(?:<div class="dpchk">filled by the app: [^<]*<\/div>)(?:<div class="dpchk">answers with: [^<]*<\/div>)<\/div>/.test(html), "the part with no field: its notes only");
});

test("X1: before the typed fields arrive the files are listed as the first design had them", async () => {
  const c = await opened({ map: rtMap() });
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", c);
  const html = await fnCard(c, "identity");
  assert.ok(/<h3>Instructions<\/h3>/.test(html) && /<div class="wbins"><b>take<\/b>/.test(html) && html.indexOf("wbinsgroup") < 0);
});

test("X2: Change opens the sheet with a textarea and the count of its length; past the most the count says so and Send is disabled", async () => {
  const [c] = await typedCard();
  const els = sheetEls(c), guidance = TYPED().filter(g => g.group === "take")[0].parts.filter(p => p.part === "take")[0].fields[1];
  assert.ok(click(c, OPEN("take", "take", "guidance")));
  let sheet = c.wbInsSheetHtml();
  assert.ok(/role="dialog" aria-label="Change Identity · take · the guidance"/.test(sheet) && /<h4>Identity · take · the guidance<\/h4>/.test(sheet), "the sheet names the function, the part and the field");
  assert.ok(sheet.indexOf('<textarea id="wbins-text" data-wbinstext="1" rows="12" spellcheck="false">' + c.wbEsc(guidance.value) + "</textarea>") >= 0, "the words in use, to change");
  assert.ok(sheet.indexOf('<div id="wbins-count" class="wbinscount">' + guidance.value.length + " of 2000</div>") >= 0, "the count against the field's most");
  assert.ok(/id="wbins-send" data-wbins="send"[^>]*>Send</.test(sheet) && !/id="wbins-send"[^>]*disabled/.test(sheet) && /data-wbins="close"[^>]*>Cancel</.test(sheet));
  assert.ok(!/function-prompts|\.md\b|\/prompts\/|Return ONLY/.test(sheet), "no path and no answer's shape in the sheet");
  assert.strictEqual(c.calls.apiPost.length, 0, "opening the sheet changes nothing");
  typeInto(c, { wbinstext: "1" }, "x".repeat(2001));
  assert.strictEqual(els["wbins-count"].textContent, "2001 of 2000: too long", "the count follows the typing, without a paint");
  assert.ok(/over/.test(els["wbins-count"].className) && els["wbins-send"].disabled === true, "over: the count says so and Send is disabled");
  sheet = c.wbInsSheetHtml();
  assert.ok(/<div id="wbins-count" class="wbinscount over">2001 of 2000: too long<\/div>/.test(sheet) && /id="wbins-send" data-wbins="send"[^>]*disabled/.test(sheet), "and so a paint says it");
  assert.ok(click(c, { wbins: "send" }));
  for (let i = 0; i < 4; i++) await sleep();
  assert.strictEqual(c.calls.apiPost.length, 0, "nothing is sent while over");
  assert.ok(/These words are longer than 2000 characters/.test(c.wbInsSheetHtml()), "and the sheet says why");
  typeInto(c, { wbinstext: "1" }, "x".repeat(2000));
  assert.ok(!/over/.test(els["wbins-count"].className) && els["wbins-send"].disabled === false, "back within it");
  typeInto(c, { wbinstext: "1" }, "   ");
  assert.ok(els["wbins-send"].disabled === true, "no words, no Send");
  click(c, { wbins: "close" });
  assert.strictEqual(c.wbInsSheetHtml(), "", "Cancel closes it and files nothing");
  assert.strictEqual(c.calls.apiPost.length, 0);
});

test("X2: a one-line field is a short textarea; the sheet's count and Send are the field's own", async () => {
  const [c] = await typedCard();
  click(c, OPEN("goal", "does", "text"));
  const sheet = c.wbInsSheetHtml();
  assert.ok(/<textarea id="wbins-text" data-wbinstext="1" rows="3"/.test(sheet) && /holds the goal and the rules, judges every effect/.test(sheet));
  assert.ok(/<div id="wbins-count" class="wbinscount">\d+ of 400<\/div>/.test(sheet), "the field's most is 400");
});

test("X2: skills are a list editor: an input for each item with Up, Down and Remove, and Add up to the field's most; an item past its most is counted over", async () => {
  const [c] = await typedCard();
  const els = sheetEls(c), skills = TYPED()[0].parts[1].fields[0];
  assert.ok(click(c, OPEN("goal", "skills", "items")));
  let sheet = c.wbInsSheetHtml();
  assert.strictEqual((sheet.match(/<input type="text" data-wbinsitem="/g) || []).length, skills.value.length, "an input for each item");
  skills.value.forEach((x, i) => assert.ok(sheet.indexOf('<input type="text" data-wbinsitem="' + i + '" value="' + c.wbEsc(x) + '"') >= 0, "item " + i));
  assert.ok(/data-wbins="up" data-wbinsi="0"[^>]*disabled/.test(sheet) && !/data-wbins="up" data-wbinsi="1"[^>]*disabled/.test(sheet), "the first cannot go up");
  const last = skills.value.length - 1;
  assert.ok(new RegExp('data-wbins="down" data-wbinsi="' + last + '"[^>]*disabled').test(sheet) && !/data-wbins="down" data-wbinsi="0"[^>]*disabled/.test(sheet), "the last cannot go down");
  assert.ok(/data-wbins="rm" data-wbinsi="0"/.test(sheet) && /data-wbins="add"(?![^>]*disabled)[^>]*>Add</.test(sheet));
  assert.ok(sheet.indexOf('<div id="wbins-count" class="wbinscount">4 of 12</div>') >= 0, "the items against the field's most");
  /* move: Down on the first swaps it with the second; Up puts it back */
  click(c, { wbins: "down", wbinsi: "0" });
  assert.deepStrictEqual(Array.from(c.wbS().ins.items).slice(0, 2), [skills.value[1], skills.value[0]]);
  click(c, { wbins: "up", wbinsi: "1" });
  assert.deepStrictEqual(Array.from(c.wbS().ins.items), skills.value, "and back");
  click(c, { wbins: "up", wbinsi: "0" });
  assert.deepStrictEqual(Array.from(c.wbS().ins.items), skills.value, "nothing above the first");
  /* remove, then add up to the most */
  click(c, { wbins: "rm", wbinsi: "1" });
  assert.strictEqual(c.wbS().ins.items.length, 3);
  assert.ok(!c.wbInsSheetHtml().includes(c.wbEsc(skills.value[1]) + '"'), "gone");
  for (let i = 0; i < 20; i++) click(c, { wbins: "add" });
  assert.strictEqual(c.wbS().ins.items.length, 12, "at most the field's most");
  sheet = c.wbInsSheetHtml();
  assert.ok(/data-wbins="add"[^>]*disabled/.test(sheet), "Add is disabled at the most");
  assert.ok(sheet.indexOf('<div id="wbins-count" class="wbinscount">12 of 12</div>') >= 0);
  /* an item past its most: counted over, and Send is disabled */
  typeInto(c, { wbinsitem: "0" }, "y".repeat(161));
  assert.strictEqual(els["wbins-n0"].textContent, "161 of 160");
  assert.ok(/over/.test(els["wbins-n0"].className) && els["wbins-send"].disabled === true && /over/.test(els["wbins-count"].className));
  typeInto(c, { wbinsitem: "0" }, "recognise a task");
  assert.ok(els["wbins-send"].disabled === false, "back within it; the empty items do not hold Send");
  click(c, { wbins: "close" });
});

test("X3: Send posts {fn, group, part, field, value} to the one route and nothing else; the sheet closes and the card is read again", async () => {
  const [c] = await typedCard();
  sheetEls(c);
  const before = readsOf(c, /\/steps\/Identity$/).length;
  click(c, OPEN("take", "take", "guidance"));
  typeInto(c, { wbinstext: "1" }, "go: do it. ask: it reaches outside. refuse: never.");
  assert.ok(click(c, { wbins: "send" }));
  for (let i = 0; i < 6; i++) await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [
    { p: "/api/native/r3/instructions", body: { fn: "identity", group: "take", part: "take", field: "guidance", value: "go: do it. ask: it reaches outside. refuse: never." } }],
    "Send files the one ask, and the old body's file and text are gone");
  assert.strictEqual(c.wbInsSheetHtml(), "", "the sheet closes");
  assert.ok(readsOf(c, /\/steps\/Identity$/).length > before, "the card is read again");
  assert.strictEqual(vm.runInContext("dpS().tab['r3']", c), "identity", "the card stays open");
  /* skills go as the list, trimmed and without the blank items */
  click(c, OPEN("goal", "skills", "items"));
  click(c, { wbins: "add" });
  typeInto(c, { wbinsitem: "4" }, "  put a question to the owner, kindly  ");
  click(c, { wbins: "add" });
  assert.ok(click(c, { wbins: "send" }));
  for (let i = 0; i < 6; i++) await sleep();
  const body = JSON.parse(JSON.stringify(c.calls.apiPost[1].body));
  assert.deepStrictEqual(Object.keys(body), ["fn", "group", "part", "field", "value"]);
  assert.strictEqual(body.value.length, 5);
  assert.strictEqual(body.value[4], "put a question to the owner, kindly");
  assert.ok(body.value.every(x => x === x.trim() && x), "trimmed, none blank");
  /* the field then waits for the stamp, beside the amber mark */
  const v = TYPED();
  v[2].parts[1].fields[1].waits = { ask: "a-9", at: "2026-10-26T11:02:00+05:30" };
  const [, html] = await typedCard({}, v);
  assert.ok(/<span class="wbinsf">the guidance<\/span><span class="wbinslead">[^<]*<\/span><span class="wbinsnote"><i class="wbinsq">\?<\/i>your change waits for your stamp/.test(html));
});

test("X3: a refusal shows the server's plain reason under the field, never the route; the sheet stays and Send can be tried again", async () => {
  const [c] = await typedCard();
  sheetEls(c);
  let n = 0;
  c.apiPost = (p, body) => {
    c.calls.apiPost.push({ p, body });
    n++;
    return n === 1 ? Promise.reject(Object.assign(new Error("these words cannot serve Identity: a field may not hold the answer's shape (/api/native/r3/instructions -> 400)"), { status: 400 }))
         : n === 2 ? Promise.reject(Object.assign(new Error("/api/native/r3/instructions -> 500"), { status: 500 }))
         : Promise.resolve({ ok: true });
  };
  click(c, OPEN("take", "take", "task"));
  typeInto(c, { wbinstext: "1" }, "Judge it kindly.");
  click(c, { wbins: "send" });
  for (let i = 0; i < 6; i++) await sleep();
  let sheet = c.wbInsSheetHtml();
  assert.ok(sheet.indexOf('<div class="o2err wbinserr" role="alert">these words cannot serve Identity: a field may not hold the answer&#39;s shape</div>') >= 0
         || sheet.indexOf('<div class="o2err wbinserr" role="alert">these words cannot serve Identity: a field may not hold the answer\'s shape</div>') >= 0, "the plain reason, under the field: " + sheet.slice(sheet.indexOf("wbinserr") - 40, sheet.indexOf("wbinserr") + 200));
  assert.ok(!/\/api\/|-> 400|\(\//.test(words(sheet)), "never the route");
  assert.ok(sheet.indexOf('<textarea id="wbins-text"') >= 0 && !/id="wbins-send"[^>]*disabled/.test(sheet), "the sheet stays, with the words, and Send is live");
  assert.ok(sheet.indexOf('id="wbins-text" data-wbinstext="1" rows="12" spellcheck="false">Judge it kindly.</textarea>') >= 0, "the owner's words kept");
  click(c, { wbins: "send" });
  for (let i = 0; i < 6; i++) await sleep();
  assert.ok(/Sutra could not take that; try again/.test(c.wbInsSheetHtml()), "a failure with no sentence of its own: one of ours, not the route");
  click(c, { wbins: "send" });
  for (let i = 0; i < 6; i++) await sleep();
  assert.strictEqual(c.wbInsSheetHtml(), "", "the third try goes through and the sheet closes");
  assert.strictEqual(c.calls.apiPost.length, 3);
});

/* ── S18 and the version line (PRD A1.23; UI-port package j2ui-shell X4, X5), from GET /layers ──────────────────────
   test_fixtures/views/layers.json is the answer of /api/native/{ref}/layers: the schema version, the implementation each
   layer runs, every implementation on disk and Root's standards in their words. The screen reads pins and standards. */
const LAYERS = () => viewFile("layers.json");
const layersReads = c => readsOf(c, /\/api\/native\/r\d\/layers$/);

test("X4: Root settings has a read-only card Standards every plan meets: the standards in their order, the line that says they are the app's, no button", async () => {
  const c = await orgOpened({ layers: LAYERS() });
  click(c, { wbtab: "root" });
  for (let k = 0; k < 3; k++){ c.o2ScreenHtml(); await settle(); }
  const html = c.o2ScreenHtml();
  const from = html.indexOf("<h3>Standards every plan meets</h3>"), to = html.lastIndexOf("<div><button", html.indexOf("Back to the chat"));
  assert.ok(from > 0 && to > from, "the card is in Root's pane, before the way back");
  const card = html.slice(from, to);
  const says = LAYERS().standards.map(s => s.says);
  let at = -1;
  says.forEach(t => { const i = card.indexOf('<div class="dpfline">' + c.wbEsc(t) + "</div>"); assert.ok(i > at, t); at = i; });
  assert.strictEqual((card.match(/<div class="dpfline">/g) || []).length, says.length, "the standards and no other line");
  assert.ok(card.indexOf("These are part of how the app is built; they change only with a new version of the app.") > at, "the line, after them");
  assert.ok(!/<button|<textarea|<input/.test(card), "no Change and nothing to type in");
  assert.ok(!/<h3>Standards every plan meets<\/h3>/.test(html.slice(0, from)), "once");
  assert.ok(/<h3>Root<\/h3>/.test(html) && /Back to the chat/.test(html), "the rest of Root's pane is as it was");
  assert.ok(!/charter|internal\s+system|GRANT|COUNTER|REFUSE/.test(words(card)), "the screen's words");
});

test("X4: the layers are read once for the pane, kept, and a failed read says Not read yet and is not asked again", async () => {
  const c = await orgOpened({ layers: LAYERS() });
  click(c, { wbtab: "root" });
  for (let k = 0; k < 6; k++){ c.o2ScreenHtml(); await settle(); }
  assert.deepStrictEqual(layersReads(c), ["/api/native/r2/layers"], "one read, for Root");
  const down = await orgOpened({});                          /* nothing answers the route */
  click(down, { wbtab: "root" });
  for (let k = 0; k < 4; k++){ down.o2ScreenHtml(); await settle(); }
  assert.ok(/<h3>Standards every plan meets<\/h3><div class="o2quiet dpq">Not read yet<\/div>/.test(down.o2ScreenHtml()), "while it is on its way, or if it never comes");
  assert.strictEqual(layersReads(down).length, 1);
  const failing = await orgOpened({ layersFail: true });
  click(failing, { wbtab: "root" });
  for (let k = 0; k < 6; k++){ failing.o2ScreenHtml(); await settle(); }
  assert.ok(/Standards every plan meets<\/h3><div class="o2quiet dpq">Not read yet</.test(failing.o2ScreenHtml()));
  assert.strictEqual(layersReads(failing).length, 1, "not asked again");
});


test("X5: each function's Settings head says Runs version N, N being the number after /v in its layer's pin; nothing until it is read", async () => {
  const c = await opened({ map: rtMap(), layers: LAYERS() });
  for (const fn of ["identity", "adaptation", "priority", "coordination", "audit"]){
    vm.runInContext("dpS().pane['r3:" + fn + "'] = 'settings';", c);
    let html = await fnCard(c, fn);
    for (let i = 0; i < 4 && html.indexOf("Runs version") < 0; i++){ await settle(); html = c.dpViewerHtml(WEB, {}, null, null); }
    assert.ok(html.indexOf('<div class="o2quiet dpq">Runs version 1</div>') >= 0, fn + ": Runs version 1");
    assert.strictEqual((html.match(/Runs version/g) || []).length, 1, fn + ": said once");
    assert.ok(html.indexOf("Runs version 1") < html.indexOf("<h3>Template</h3>"), fn + ": at the head, before the cards");
  }
  assert.deepStrictEqual(layersReads(c), ["/api/native/r3/layers"], "read once for the department");
  const three = LAYERS(); three.pins.identity = "identity/v3";
  const d = await opened({ map: rtMap(), layers: three });
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", d);
  await fnCard(d, "identity"); await settle();
  assert.ok(d.dpViewerHtml(WEB, {}, null, null).indexOf("Runs version 3") >= 0, "the pin says v3");
  const none = await opened({ map: rtMap() });
  vm.runInContext("dpS().pane['r3:identity'] = 'settings';", none);
  assert.ok((await fnCard(none, "identity")).indexOf("Runs version") < 0, "no line while the read has not come");
});

/* ── S11: Root's check on Adaptation's pane (PRD M7.3; UI-port package j2ui-shell X6), from the Adaptation view ────────
   test_fixtures/views/adaptation.root_checks.json: view.adaptation as layers/adaptation/v1.py builds it, in the states
   the row has: none yet, approved, sent back once and twice, blocked, and approved after a send back. */
const RC = () => viewFile("adaptation.root_checks.json");
async function adaptationPane(state){
  const j2 = RC()[state];
  const c = await opened({ map: rtMap(), fnpage: fn => Object.assign(fnPageOf(fn), fn === "adaptation" ? { j2 } : {}) });
  for (let k = 0; k < 3; k++){ c.wbFnOwn("r3", "adaptation"); await settle(); }
  return [c, c.wbFnOwn("r3", "adaptation"), j2];
}
const rcRow = html => html.slice(html.indexOf("<h3>Root's check</h3>"), html.indexOf("<h3>The function</h3>"));
const rcDots = row => [...row.matchAll(/<span class="wbrcdot( no)?" role="img" title="([^"]*)" aria-label="([^"]*)"><\/span>/g)].map(m => ({ no: !!m[1], title: m[2], label: m[3] }));

test("X6: an approved plan is one row: a ticked dot for each standard that applied, each titled with its words, and approved with the time", async () => {
  const [c, html, j2] = await adaptationPane("approved");
  const row = rcRow(html), checks = j2.root_checks[0].checks;
  assert.ok(row.length > 20, "the row is above the function's page: " + html.slice(0, 200));
  const dots = rcDots(row);
  assert.strictEqual(dots.length, checks.length, "a dot for each row of the review, the schema's own row first");
  assert.ok(dots.every(d => !d.no), "every standard held");
  checks.forEach((ch, i) => {
    const said = ch.says !== ch.check ? ch.says : ch.why;
    assert.strictEqual(dots[i].title, c.wbEsc(said), "the dot is titled with its words, in order");
    assert.strictEqual(dots[i].label, c.wbEsc(said + ", held"), "and said in words to a screen reader");
  });
  assert.ok(!dots.some(d => /workflow_meets_standards|_/.test(d.title)), "no check id on the screen");
  assert.ok(/<span class="wbrcv approved">approved · \d\d:\d\d<\/span>/.test(row), "the verdict and the time");
  assert.ok(!/wbrcwhy|wbrcrs/.test(row), "nothing to explain and no reshapes");
  assert.ok(html.indexOf("<h3>Root's check</h3>") < html.indexOf("<h3>The function</h3>"), "above the function's page");
});

test("X6: a plan sent back names the standard that broke in its words, with why, and shows the reshapes so far as dots", async () => {
  const [c, html, j2] = await adaptationPane("sent_back");
  const row = rcRow(html), dots = rcDots(row);
  assert.deepStrictEqual(dots.map(d => d.no), j2.root_checks[0].checks.map(ch => !ch.passed), "the crossed dot is the one that broke");
  const broke = dots.filter(d => d.no);
  assert.strictEqual(broke.length, 1);
  assert.strictEqual(broke[0].title, "every done-when item is covered by an engine");
  assert.ok(/<span class="wbrcv back">sent back · \d\d:\d\d<\/span>/.test(row));
  assert.ok(/<div class="wbrcwhy"><b>every done-when item is covered by an engine<\/b>: D3 \(new arrivals, lookbook, reviews\) is covered by no engine<\/div>/.test(row), "the standard in its words, then why");
  assert.ok(/<div class="wbrcrs back"><span>reshapes<\/span><i class="on"><\/i><i class=""><\/i><\/div>/.test(row), "one reshape of the two");
  assert.ok(!/\d/.test(words(row).replace(/D3 \(new arrivals, lookbook, reviews\)/, "")), "no count at rest: " + words(row));
  const twice = (await adaptationPane("sent_back_twice"))[1];
  assert.ok(/<div class="wbrcrs back"><span>reshapes<\/span><i class="on"><\/i><i class="on"><\/i><\/div>/.test(rcRow(twice)) && /wbrcv back">sent back/.test(rcRow(twice)), "sent back twice: both dots, still sent back");
});

test("X6: after two reshapes the plan is blocked: both dots, the broken standard named, and the word blocked", async () => {
  const [, html] = await adaptationPane("blocked");
  const row = rcRow(html);
  assert.ok(/<span class="wbrcv blocked">blocked · \d\d:\d\d<\/span>/.test(row), row);
  assert.ok(/<div class="wbrcrs blocked"><span>reshapes<\/span><i class="on"><\/i><i class="on"><\/i><\/div>/.test(row));
  assert.ok(/<b>every done-when item is covered by an engine<\/b>/.test(row));
});

test("X6: approved after a send back is approved; no review yet says Root has not checked a plan", async () => {
  const [, html] = await adaptationPane("approved_after_a_send_back");
  assert.ok(/wbrcv approved">approved/.test(rcRow(html)) && !/wbrcrs/.test(rcRow(html)));
  const none = (await adaptationPane("none"))[1];
  assert.ok(/<h3>Root's check<\/h3><div class="o2quiet dpq">Root has not checked a plan yet<\/div>/.test(none));
  /* a read from before the standards were listed (no checks): the review's own sentence, and no dots */
  const c = await opened({ map: rtMap(), fnpage: fn => Object.assign(fnPageOf(fn), fn === "adaptation" ? { j2: { proposal: null, root_checks: [{ summary: "Root's check sent the plan back: the line reaches outside without a rule", at: AT, passed: false }], rounds: [] } } : {}) });
  for (let k = 0; k < 3; k++){ c.wbFnOwn("r3", "adaptation"); await settle(); }
  const row = rcRow(c.wbFnOwn("r3", "adaptation"));
  assert.ok(/wbrcv back">sent back/.test(row) && /<div class="wbrcwhy">Root's check sent the plan back: the line reaches outside without a rule<\/div>/.test(row) && rcDots(row).length === 0);
  const plain = await opened({ map: rtMap(), fnpage: fn => fnPageOf(fn) });          /* a page whose view holds no root_checks: nothing added */
  for (let k = 0; k < 3; k++){ plain.wbFnOwn("r3", "adaptation"); await settle(); }
  assert.ok(plain.wbFnOwn("r3", "adaptation").indexOf("Root's check") < 0, "an older read is drawn as it was");
});

test("X6: the row repaints when a review moves, and the words are escaped", async () => {
  const j = RC().sent_back;
  const c = fresh({ map: rtMap() });
  const before = c.wbFnPageSig({ fn: "adaptation", j2: j });
  const moved = JSON.parse(JSON.stringify(j)); moved.root_checks[0].checks[7].passed = true; moved.root_checks[0].passed = true;
  assert.notStrictEqual(c.wbFnPageSig({ fn: "adaptation", j2: moved }), before, "a check that held now changes the signature");
  const hostile = JSON.parse(JSON.stringify(j)); hostile.root_checks[0].checks[7].why = "<script>x</script>";
  const html = c.wbRootChecksHtml(hostile.root_checks);
  assert.ok(html.indexOf("<script") < 0 && html.indexOf("&lt;script") >= 0, "escaped");
});

/* ── W47: Identity's question as a card in Chat (PRD-FIVE-FUNCTIONS M0.6, screen S6) ── */
const QAT = "2026-10-23T10:20:00+05:30";
const QUESTION = { id: "a-j2-1", kind: "j2_identity", text: "What is the site for, and about whom or what?", why: "Your words name nothing to build from yet.",
                   missing: "words", answer: "words", status: "pending", created: QAT, ref: "r3", dept: DEPT };
function qChat(o){
  o = o || {};
  return { root: "r2", about: "r3", departments: [{ ref: "r3", name: DEPT, stopped: false }], turns: [
      { n: 1, src: "Owner", dst: ["Identity"], msg_type: "request", at: "2026-10-23T10:19:00+05:30", thread: "x-1", word: "request", line: "a website", dept: "r3", name: DEPT },
      /* the chat read leaves Identity's line about the question to the card (engine_runtime._on_card); the next turn is later */
      { n: 3, src: "Identity", dst: ["Owner"], msg_type: "inform", at: "2026-10-23T10:21:00+05:30", thread: "x-2", word: "request", dept: "r3", name: DEPT,
        line: "Filed in the Brief." }],
    asks: o.answered ? [] : [Object.assign({}, QUESTION, o.standard ? { standard: true, points: ["goal"] } : {})].concat(o.publish ? [Object.assign({}, CHAT.asks[0])] : []),
    answered: o.answered ? [Object.assign({}, QUESTION, { status: "stamped", answered: o.answered, decided: "2026-10-23T10:26:00+05:30" })] : [] };
}
async function chatOpen(o){
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m, chat: qChat(o) });
  vm.runInContext("globalThis.__snacks = []; snack = function(m, o){ __snacks.push(m); };", c);
  view(c); await sleep(); await sleep();
  return c;
}
const typeAnswer = (c, value) => (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:q:a-j2-1" }, value } }));

test("W47: a waiting department shows Identity's question as a card in Chat, with its answer box, never a stamp", async () => {
  const c = await chatOpen({ publish: true });
  const html = view(c);
  assert.ok(/<div class="dpask wbq wb"><div class="dpk">Identity asks<\/div><div class="dpasks">What is the site for, and about whom or what\?<\/div><div class="dpaskd">Your words name nothing to build from yet\.<\/div>/.test(html), "the label, the question and its why");
  assert.ok(/<textarea id="wbd-q-a-j2-1" data-wbdraft="r3:q:a-j2-1"[^>]*placeholder="Type your answer\.\.\."/.test(html), "an answer box of its own");
  assert.ok(/data-wbanswer="a-j2-1" data-wbref="r3">Send</.test(html), "Send answers where the question lives");
  assert.ok(!/data-wbdecide="a-j2-1"/.test(html), "a question that takes words is never stamped");
  assert.ok(/data-wbdecide="a-1"/.test(html), "the other asks keep their stamp");
  assert.ok(html.indexOf(">a website<") < html.indexOf('class="dpask wbq wb"'), "the card stands after the words it asks about");
  assert.ok(html.indexOf('class="dpask wbq wb"') < html.indexOf("Filed in the Brief."), "and before what was said after it was asked");
  assert.strictEqual(html.split("What is the site for, and about whom or what?").length, 2, "the question is said once, on its card");
  assert.ok(html.indexOf('class="dpask wbq wb"') < html.indexOf('id="wbd-ask"'), "and above the chat's own box");
  const t = words(html);
  assert.ok(!/\d/.test(t), "a number at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");
  assert.ok(/\.wbq\{max-width:640px/.test(css), "at most 640px wide");
});

test("W47: where the asks are listed outside the chat, Identity's question points to its card and is never stamped", () => {
  const c = fresh();
  const m = rtMap({ ask: true });
  m.status.asks.push(Object.assign({}, QUESTION));
  const html = c.wbAsksHtml(m);
  assert.ok(/<div class="dpasks">What is the site for, and about whom or what\?<\/div><div class="dpaskd">Identity · \d\d:\d\d<\/div><button type="button" class="btn wb" data-wbtab="chat">Identity asks you in Chat ›<\/button>/.test(html), "a pointer to the Chat");
  assert.ok(!/data-wbdecide="a-j2-1"/.test(html) && /data-wbdecide="a-1" data-wbok="1"/.test(html), "no stamp on the question; the publish ask keeps its own");
});

test("W47: Send posts {text}, says Sending... while it goes, and the answered card keeps 'You: ...'", async () => {
  const c = await chatOpen();
  let release;
  c.apiPost = (p, body) => { c.calls.apiPost.push({ p, body }); return new Promise(r => { release = () => r({ state: "assessing", open_question: null }); }); };
  typeAnswer(c, "a site for my bakery in Pune");
  assert.ok(click(c, { wbanswer: "a-j2-1", wbref: "r3" }));
  await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/dept/r3/j2/answer", body: { text: "a site for my bakery in Pune" } }]);
  let html = view(c);
  assert.ok(/data-wbanswer="a-j2-1" data-wbref="r3" disabled>Sending\.\.\.</.test(html), "Send is disabled and reads Sending...");
  click(c, { wbanswer: "a-j2-1", wbref: "r3" }); await sleep();
  assert.strictEqual(c.calls.apiPost.length, 1, "a second press while it goes sends nothing");
  release(); await sleep(); await sleep(); await sleep();
  html = view(c);
  assert.ok(/<div class="dpask gone wbq wb"><div class="dpk">Identity asked<\/div><div class="dpasks">What is the site for, and about whom or what\?<\/div><div class="dpaskd">You: a site for my bakery in Pune · \d\d:\d\d<\/div><\/div>/.test(html), "the card goes quiet with the answer under it");
  assert.ok(!/id="wbd-q-a-j2-1"/.test(html), "and no box is left on it");
  const onRoot = c.wbQuestionHtml(Object.assign({}, QUESTION, { id: "a-j2-9" }), "r2", true);
  assert.ok(/<div class="dpk">Identity asks · City Care Hospital Website<\/div>/.test(onRoot), "on Root's whole chat the card names the department that asks");
  assert.ok(/data-wbanswer="a-j2-9" data-wbref="r3"/.test(onRoot), "and answers there, not on Root");
  const back = await chatOpen({ answered: "Initials only" });
  assert.ok(/<div class="dpk">Identity asked<\/div>[^]*?You: Initials only · \d\d:\d\d/.test(view(back)), "an answer on the record keeps its card, read again from the chat");
  assert.strictEqual(view(back).split("Initials only").length, 2, "the answer is said once, under its card");
});

test("W47: EMPTY_ANSWER shows its snack and the words stay; Cmd+Enter sends", async () => {
  const c = await chatOpen();
  c.apiPost = (p, body) => { c.calls.apiPost.push({ p, body }); return Promise.reject(new Error('{"code":"EMPTY_ANSWER"} (/api/dept/r3/j2/answer -> 400)')); };
  typeAnswer(c, "   ");
  click(c, { wbanswer: "a-j2-1", wbref: "r3" }); await sleep(); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(vm.runInContext("__snacks", c))), ["Write your answer first, then Send."], "the snack says what to do");
  let html = view(c);
  assert.ok(/id="wbd-q-a-j2-1"[^>]*>   <\/textarea>/.test(html) && />Send</.test(html), "the box keeps what was typed, and Send is back");
  c.apiPost = (p, body) => { c.calls.apiPost.push({ p, body }); return Promise.reject(new Error('{"code":"NO_OPEN_QUESTION"} (/api/dept/r3/j2/answer -> 409)')); };
  click(c, { wbanswer: "a-j2-1", wbref: "r3" }); await sleep(); await sleep(); await sleep();
  assert.strictEqual(vm.runInContext("__snacks", c)[1], "That question is no longer open.");
  c.apiPost = (p, body) => { c.calls.apiPost.push({ p, body }); return Promise.resolve({}); };
  const key = { key: "Enter", metaKey: true, target: { value: "Initials only", dataset: { wbqid: "a-j2-1", wbqref: "r3", wbdraft: "r3:q:a-j2-1" } }, preventDefault(){} };
  (c.document.listeners.keydown || []).forEach(fn => fn(key)); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[2])), { p: "/api/dept/r3/j2/answer", body: { text: "Initials only" } }, "Cmd+Enter sends what is in the box");
  const plain = Object.assign({}, key, { metaKey: false });
  (c.document.listeners.keydown || []).forEach(fn => fn(plain)); await sleep();
  assert.strictEqual(c.calls.apiPost.length, 3, "Enter alone is a new line, not a send");
});

/* ── W48: 'Just do it' on a question of Identity's standard (PRD M3.3, screen S6) ── */
test("W48: a question on Identity's standard offers Just do it, which sends 'just do it'; thin words offer none", async () => {
  const c = await chatOpen();
  assert.ok(!/data-wbjust=/.test(view(c)), "a question on thin words has no Just do it: nothing was said to build from");
  const std = Object.assign({}, QUESTION, { text: "Who are the site's visitors?", why: "The goal names no one the site is for.", missing: "goal",
                                           points: ["goal"], standard: true });
  const html = c.wbQuestionHtml(std, "r3", false);
  assert.ok(/data-wbanswer="a-j2-1" data-wbref="r3">Send<\/button><button type="button" class="btn wb" data-wbjust="a-j2-1" data-wbref="r3">Just do it<\/button>/.test(html),
            "Just do it stands after Send");
  const s = await chatOpen({ standard: true });
  assert.ok(/data-wbjust="a-j2-1"/.test(view(s)), "the card in Chat offers it");
  typeAnswer(s, "half a thought");
  assert.ok(click(s, { wbjust: "a-j2-1", wbref: "r3" })); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(s.calls.apiPost)), [{ p: "/api/dept/r3/j2/answer", body: { text: "just do it" } }],
                         "one answer, 'just do it', where the question lives");
  /* a question Identity's code read off the record (standard false) is a step-1 question on the same standard: it takes
     'just do it' too (found by a verifier 2026-10-26: the owner question had no way to end the questions) */
  const coded = Object.assign({}, QUESTION, { text: "Who owns this department, and what may it spend?", why: "the record has no owner, no budget",
                                             missing: "owner", points: ["owner", "budget"], standard: false });
  assert.ok(/data-wbanswer="a-j2-1" data-wbref="r3">Send<\/button><button type="button" class="btn wb" data-wbjust="a-j2-1" data-wbref="r3">Just do it<\/button>/.test(c.wbQuestionHtml(coded, "r3", false)),
            "a question Identity's code asked offers Just do it");
});

/* ── S5: Identity's pane (PRD M3.7), from the screen's own sample ── */
const ID_J2 = { goal: "A phone-first website for Thread & Loom, a handloom boutique in Pune, where shoppers browse kurtas, sarees, shirts and dupattas and order on WhatsApp.",
  standard: { met: false, missing: [], rows: [
    { id: "goal", says: "The goal names what and for whom", state: "met", note: "as you said it" },
    { id: "items", says: "Done-when items, each with how it is checked", state: "met", note: "each says how it is checked" },
    { id: "rules", says: "Every rule is tagged", state: "met", note: "each says go, ask, never or always" },
    { id: "owner_budget", says: "Owner and budget are set", state: "met", note: "you, and Priority's limits" },
    { id: "invented", says: "Nothing invented", state: "to_confirm", note: "to confirm with you: D6, the reviews' names" }] },
  done_items: [{ id: "D1", text: "Browse all ten products by category", how: "code", level: "target", confirm: null },
               { id: "D2", text: "Filter by size (XS to XXL) and by price", how: "code", level: "target", confirm: null },
               { id: "D6", text: "New arrivals, a lookbook of three outfits, three reviews", how: "model", level: "outcome", confirm: "the reviews' names" }],
  rules: [{ tag: "go", line: "Plan, write and check inside the record", by: "the template", since: null },
          { tag: "ask", line: "Ask the owner before the first publish", by: "the template", since: null },
          { tag: "refuse", line: "Never show a price that is not in my list", by: "yours", since: "2026-10-23T10:14:00+05:30" }],
  open_question: { id: "a-j2-1", text: "May the three reviews show your customers' first names?", why: "Nothing on record says the customers agreed (D6).",
                   missing: "invented", asked: QAT, standard: true, points: ["invented"] },
  conflicts: [{ at: "2026-10-23T10:08:00+05:30", who: "Adaptation and Priority did not agree", split: "Priority said no to the plan: no room", plan: "Photo Picker",
                ruling: "drop", ruled: "dropped", why: "D6 stays covered by Write", asked_you: false }] };
test("S5: Identity's pane holds its one record: the question, the standard, the goal, done-when, the rules, the conflicts closed", async () => {
  const page = fn => Object.assign(fnPageOf(fn), fn === "identity" ? { j2: JSON.parse(JSON.stringify(ID_J2)) } : {});
  const c = await opened({ map: rtMap(), fnpage: page });
  const html = await fnCard(c, "identity");
  const i = k => html.indexOf(k);
  assert.ok(i('<div class="dpk">Identity asks</div><div class="dpasks">May the three reviews show your customers&#39;') >= 0 ||
            i('<div class="dpk">Identity asks</div><div class="dpasks">May the three reviews show your customers\'') >= 0, "the open question, the S6 card");
  assert.ok(/data-wbanswer="a-j2-1" data-wbref="r3"/.test(html) && /data-wbjust="a-j2-1"/.test(html), "answered where it lives");
  assert.ok(i("<h3>Enough to work?</h3>") > i("Identity asks") && i("<h3>Goal</h3>") > i("<h3>Enough to work?</h3>") && i("<h3>Done when</h3>") > i("<h3>Goal</h3>") &&
            i("<h3>Rules</h3>") > i("<h3>Done when</h3>") && i("<h3>Conflicts closed</h3>") > i("<h3>Rules</h3>"), "the cards in the screen's order");
  assert.ok(/<div class="dprow wbstd"><span class="dpdot ok"><\/span><span><b>The goal names what and for whom<\/b> <span class="wbchip on">met<\/span><div class="dpchk">as you said it<\/div>/.test(html), "a dot, a word and a note");
  assert.ok(/<span class="dpdot warn"><\/span><span><b>Nothing invented<\/b> <span class="wbchip">to confirm<\/span><div class="dpchk">to confirm with you: D6, the reviews/.test(html), "to confirm, in words");
  assert.ok(/<div class="dpbig wbidgoal">A phone-first website for Thread &amp; Loom/.test(html) && /data-wbtab="chat" data-wbfill="Change the goal to: ">Change the goal</.test(html), "the goal, and a way to change it");
  assert.ok(/data-wbfn="audit" title="Audit&#39;s reading">D1<\/button><span>Browse all ten products by category<\/span><span class="dpchk">target · code<\/span>/.test(html) ||
            /data-wbfn="audit" title="Audit's reading">D1<\/button><span>Browse all ten products by category<\/span><span class="dpchk">target · code<\/span>/.test(html), "an item, its level and how");
  assert.ok(/>D6<\/button><span>New arrivals, a lookbook of three outfits, three reviews<\/span><span class="wbchip">to confirm<\/span><span class="dpchk">outcome · model<\/span>/.test(html), "a to confirm chip");
  assert.ok(/<span class="wbchip on">go<\/span><span>Plan, write and check inside the record<\/span><span class="dpchk">the template<\/span>/.test(html), "a rule of the template");
  assert.ok(/<span class="wbchip ask">never<\/span><span>Never show a price that is not in my list<\/span><span class="dpchk">yours · \d\d:\d\d<\/span>/.test(html), "a rule of yours, and when");
  assert.ok(/data-wbtab="board"><span class="dpchk">\d\d:\d\d<\/span><span>Adaptation and Priority did not agree on Photo Picker\. Ruled: dropped; D6 stays covered by Write\. No ask to you\.<\/span>/.test(html), "a conflict closed: who split, the ruling and why");
  assert.ok(/<details class="wbhow wb"><summary>How Identity works<\/summary><div class="dpcard"><h3>The function<\/h3>/.test(html), "how Identity works, folded under");
  const t = words(html);
  assert.ok(!/charter|internal system/i.test(t), "never charter");
  assert.ok(!/\b(?:GRANT|COUNTER|REFUSE|orders)\b/i.test(t), "the owner's words only: never grant, counter, refuse or orders: " +
            (t.match(/.{0,30}\b(?:grant|counter|refuse|orders)\b.{0,30}/i) || [""])[0]);
  assert.ok(!/\/api\/|\.json|\.md\b/.test(t), "no path");
  /* Change the goal opens the Chat with the box begun */
  click(c, { wbtab: "chat", wbfill: "Change the goal to: " });
  assert.strictEqual(vm.runInContext("wbS().draft['r3:ask']", c), "Change the goal to: ");
  assert.strictEqual(vm.runInContext("wbS().tab['r3']", c), "chat");
  /* a pane with no record of Identity's own keeps its page as it was */
  const other = await fnCard(await opened({ map: rtMap(), fnpage: fnPageOf }), "identity");
  assert.ok(other.indexOf("<h3>Enough to work?</h3>") < 0 && other.indexOf("wbhow") < 0, "a page with no record of its own keeps its page");
});

/* ── W50: one voice (PRD M3.6, Q1): a function's chat box sends the owner's words to Identity about that function ── */
test("W50: a function's chat box says the words go to Identity about that function", async () => {
  const c = await opened({ map: rtMap(), fnchat: Object.assign({}, FNCHAT, { fn: "Priority" }) });
  await fnCard(c, "priority");
  vm.runInContext("dpS().pane['r3:priority'] = 'chat';", c);
  for (let k = 0; k < 3; k++){ c.dpViewerHtml(WEB, {}, null, null); for (let i = 0; i < 6; i++) await sleep(); }
  const html = c.dpViewerHtml(WEB, {}, null, null);
  assert.ok(/placeholder="Say it to Identity about Priority"/.test(html) && /data-wbask="fn:priority"/.test(html), "said to Identity, about Priority");
  vm.runInContext("wbS().draft['r3:fn:priority'] = 'Spend less on the careers page';", c);
  assert.ok(click(c, { wbask: "fn:priority" }));
  for (let i = 0; i < 4; i++) await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost.filter(x => /\/ask$/.test(x.p))[0])),
                         { p: "/api/native/r3/ask", body: { text: "Spend less on the careers page", about: "fn:priority" } }, "to the department, about Priority");
});

/* ── W51: one voice (PRD M3.6, S15): a department's chat is signed by its Identity; Root's own chat by Root ── */
test("W51: in a department's chat each of its turns is Identity's, signed with Identity's mark and the department's name; Root keeps Root", async () => {
  const signedBy = html => (html.match(/<div class="who who-ai">(?:(?!<\/div>)[\s\S])*?<\/div>/g) || []);
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m });
  view(c); await sleep(); await sleep();
  let ai = signedBy(view(c));
  assert.ok(ai.length >= 3, "the department's turns: " + ai.length);
  ai.forEach(w => assert.ok(new RegExp("^" + SIGNED + "$").test(w), "signed by Identity for the department: " + w));
  assert.ok(/<svg class="dpfnmk fn-identity"[^>]*aria-hidden="true"><path d="M4 5h16v10H11l-4 4v-4H4z"\/><path d="M14 19l2 2 4-4"\/><\/svg>/.test(ai[0]),
            "Identity's mark, the speech bubble with a tick");
  assert.ok(/<div class="who who-you">You<\/div>/.test(view(c)), "the owner's turns stay the owner's");
  /* a department with no Root: its own chat, its own voice */
  const lone = await opened({ map: rtMap(), chat: Object.assign({}, CHAT, { root: null, about: null }) });
  view(lone); await sleep(); await sleep();
  ai = signedBy(view(lone));
  assert.ok(ai.length >= 2 && ai.every(w => new RegExp("^" + SIGNED + "$").test(w)), "no Root, still Identity for the department: " + ai.join(" | "));
  assert.ok(!/<span class="wbchip">City Care Hospital Website<\/span>/.test(view(lone)), "and no chip of its own name beside it");
  /* Root's own chat: Root, with the department a chip on the turns about it */
  const rm = rtMap(); rm.kind = "root"; rm.root = "r3"; rm.say = "Ask Root for a department: what it is for"; rm.live = false;
  const r = await opened({ map: rm, chat: ROOT_CHAT });
  view(r); await sleep(); await sleep();
  ai = signedBy(view(r));
  assert.ok(ai.length >= 3 && ai.every(w => /^<div class="who who-ai">Root(?:<button type="button" class="wbchip wbto wb" data-wbopen="r5">City Care Hospital Website<\/button>)?<\/div>$/.test(w)),
            "Root's chat is signed Root: " + ai.join(" | "));
  assert.ok(!/fn-identity/.test(ai.join("")), "and never with Identity's mark");
});

/* ── W49: a blocked plan's card and its ways out (PRD M3.5, screen S10) ── */
const BLOCKED = { id: "a-b-1", kind: "blocked", engine: "Identity", ref: "r3", dept: DEPT, status: "pending", created: QAT, thread: "x-9",
                  text: "Root's check sent the plan back 3 times: the line reaches outside without a rule. Say what to change and I will have it shaped afresh.",
                  title: "The plan could not be approved.", who: "Root, at its review", why: "the line reaches outside without a rule",
                  if_nothing: "Nothing runs; the department waits for your words.", chosen: null,
                  options: [{ id: "words", label: "Change the plan in my words", cost: "Adaptation shapes it afresh from what you say; nothing runs before Root's review" },
                            { id: "leave:D3", label: "Leave D3 out", cost: "D3 is dropped from done-when (Three reviews from customers); nothing more is spent" },
                            { id: "stop", label: "Stop here", cost: "the department stops where it is; you can start it again later" }] };
async function blockedOpen(chosen){
  const m = rtMap(); m.root = "r2";
  const card = Object.assign({}, BLOCKED, chosen ? { status: "chosen", chosen } : {});
  const chat = Object.assign(qChat({ answered: "a site" }), { asks: chosen ? [] : [card], chosen: chosen ? [card] : [] });
  const c = await opened({ map: m, chat });
  vm.runInContext("globalThis.__snacks = []; snack = function(m, o){ __snacks.push(m); };", c);
  view(c); await sleep(); await sleep();
  return c;
}

test("W49: a blocked plan is a card with its ways out, each with its cost, and never a stamp", async () => {
  const c = await blockedOpen();
  const html = view(c);
  assert.ok(/<div class="dpask hard wbq wbopt wb"><div class="dpk">Identity asks<\/div><div class="dpasks">The plan could not be approved\.<\/div>/.test(html), "Identity asks, with its title");
  assert.ok(/<span class="dpk">Who<\/span><span>Root, at its review<\/span>[^]*<span class="dpk">Why<\/span><span>the line reaches outside without a rule<\/span>[^]*<span class="dpk">If nothing is done<\/span><span>Nothing runs; the department waits for your words\.<\/span>/.test(html),
            "who, why and if nothing is done");
  const ids = (html.match(/data-wboption="([^"]+)"/g) || []).map(x => x.slice(15, -1));
  assert.deepStrictEqual(ids, ["words", "leave:D3", "stop"], "the owner's words first, then the others");
  assert.ok(/title="Leave D3 out: D3 is dropped from done-when \(Three reviews from customers\); nothing more is spent"[^>]*>Leave D3 out<\/button><span class="dpchk">D3 is dropped/.test(html), "the cost beside it and in its title");
  assert.ok(!/data-wbdecide="a-b-1"/.test(html) && html.indexOf("Waiting for you") < 0, "never a stamp, never in Waiting for you");
  assert.ok(click(c, { wboption: "leave:D3", wbopt: "a-b-1", wbref: "r3" })); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost)), [{ p: "/api/native/r3/asks/a-b-1", body: { option: "leave:D3" } }], "one click, the option");
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:o:a-b-1" }, value: "Only the cakes page" } }));
  click(c, { wboption: "words", wbopt: "a-b-1", wbref: "r3" }); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost[1])), { p: "/api/native/r3/asks/a-b-1", body: { option: "words", text: "Only the cakes page" } }, "the box sends the words");
  c.apiPost = (p, body) => { c.calls.apiPost.push({ p, body }); return Promise.reject(new Error('{"detail":{"code":"UNKNOWN_OPTION"}} (/api/native/r3/asks/a-b-1 -> 409)')); };
  click(c, { wboption: "stop", wbopt: "a-b-1", wbref: "r3" }); await sleep(); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(vm.runInContext("__snacks", c))), ["That choice is no longer on the card."], "a snack says why");
  const quiet = view(await blockedOpen({ id: "leave:D3", label: "Leave D3 out", at: "2026-10-23T10:26:00+05:30", by: "the owner", words: null }));
  assert.ok(/<div class="dpask gone wbq wbopt wb"><div class="dpk">Identity asked<\/div><div class="dpasks">The plan could not be approved\.<\/div><div class="dpaskd">You chose: Leave D3 out · \d\d:\d\d<\/div><\/div>/.test(quiet), "chosen, it goes quiet");
  assert.ok(!/data-wboption=/.test(quiet));
  const t = words(html).replace(/D\d\b/g, " ");
  assert.ok(!/\bGRANT|\bCOUNTER|\bREFUSE\b|charter|internal system/i.test(t), "owner's words only");
});

/* ── W52: the cards that wait on the owner, wherever the department needs them (PRD M3.7, screens S6 and S10) ── */
const QSTD = Object.assign({}, QUESTION, { text: "Who are the site's visitors?", why: "The goal names no one the site is for.", missing: "goal",
                                         points: ["goal"], standard: true });
const cardsChat = (who) => Object.assign(qChat({}), { asks: [Object.assign({}, QSTD), Object.assign({}, BLOCKED, who ? { who } : {})] });
test("W52: All five carries Identity's question and the blocked card at its top, the same cards as in Chat, answered in one place", async () => {
  const [c, html] = await allFive({ fv: fvOf({ states: { Identity: "waiting_on_you" }, cycle: { needs_you: true, asks: 2 } }), chat: cardsChat() });
  const blocked = html.indexOf('<div class="dpask hard wbq wbopt wb"><div class="dpk">Identity asks</div><div class="dpasks">The plan could not be approved.</div>');
  const question = html.indexOf('<div class="dpask wbq wb"><div class="dpk">Identity asks</div><div class="dpasks">Who are the site&#39;s visitors?') >= 0
    ? html.indexOf('<div class="dpask wbq wb"><div class="dpk">Identity asks</div><div class="dpasks">Who are the site&#39;s visitors?')
    : html.indexOf('<div class="dpask wbq wb"><div class="dpk">Identity asks</div><div class="dpasks">Who are the site\'s visitors?');
  const prog = html.indexOf('class="fvprog'), grid = html.indexOf('class="fvgrid');
  assert.ok(blocked > 0 && question > 0, "both cards on All five");
  assert.ok(blocked < prog && question < prog && prog < grid, "at the top, before the progress and the five");
  assert.ok(/data-wboption="leave:D3" data-wbopt="a-b-1" data-wbref="r3"/.test(html) && /data-wbanswer="a-j2-1" data-wbref="r3"/.test(html) &&
            /data-wbjust="a-j2-1"/.test(html), "each answered where it lives, as in Chat");
  /* the same card and state: a choice on All five posts the Chat card's one route, and a draft typed here is the Chat's */
  assert.ok(click(c, { wboption: "leave:D3", wbopt: "a-b-1", wbref: "r3" })); await sleep(); await sleep();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.calls.apiPost.filter(x => /\/asks\//.test(x.p)))), [{ p: "/api/native/r3/asks/a-b-1", body: { option: "leave:D3" } }]);
  (c.document.listeners.input || []).forEach(fn => fn({ target: { dataset: { wbdraft: "r3:q:a-j2-1" }, value: "Families in Pune" } }));
  assert.ok(/data-wbdraft="r3:q:a-j2-1"[^>]*>Families in Pune<\/textarea>/.test(await paint(c)), "the box keeps the words on All five");
  click(c, { wbtab: "chat" });
  assert.ok(/data-wbdraft="r3:q:a-j2-1"[^>]*>Families in Pune<\/textarea>/.test(await paint(c)), "and the Chat's card shows the same words");
  /* with nothing waiting, nothing stands there; and a failed read of the five still shows what waits */
  const [, quiet] = await allFive({ fv: fvOf({}) });
  assert.ok(quiet.indexOf("dpask") < 0, "nothing waits, no card");
  const [, down] = await allFive({ fv: () => Promise.reject(new Error("down")), chat: cardsChat() });
  assert.ok(down.indexOf("The plan could not be approved.") > 0 && down.indexOf("The plan could not be approved.") < down.indexOf("fverr"), "the card, then Could not read");
  const t = words(html.replace(/ title="[^"]*"/g, ""));
  assert.ok(!/\b(?:GRANT|COUNTER|REFUSE|orders)\b|charter|internal system/i.test(t), "the owner's words only");
});

test("W52: a blocked card stands at the top of the pane of the function that caused it, and nowhere else among the five", async () => {
  const pane = async (who, fn) => fnCard(await opened({ map: rtMap(), chat: cardsChat(who), fnpage: fnPageOf }), fn);
  const card = h => h.indexOf('<div class="dpask hard wbq wbopt wb">');
  let html = await pane(null, "adaptation");                       /* Root, at its review: Root's check of Adaptation's plan */
  assert.ok(card(html) >= 0 && card(html) < html.indexOf("<h3>The function</h3>"), "on Adaptation's pane, above its page");
  assert.ok(/data-wboption="stop" data-wbopt="a-b-1" data-wbref="r3"/.test(html), "with its ways out");
  assert.ok(html.indexOf('<div class="dpask wbq wb">') < 0, "Identity's question is Identity's, not Adaptation's");
  for (const fn of ["identity", "priority", "audit", "coordination"]) assert.ok(card(await pane(null, fn)) < 0, "not on " + fn + "'s pane");
  html = await pane("Identity, settling Priority's no", "identity");
  assert.ok(card(html) >= 0, "a card Identity's ruling caused, on Identity's pane");
  assert.ok(card(await pane("Identity, settling Priority's no", "adaptation")) < 0, "and not on Adaptation's");
  assert.ok(card(await pane("You, on the plan Identity put to you", "identity")) >= 0, "the owner's own no is Identity's to carry");
  assert.ok(card(await pane("Adaptation, shaping the plan", "adaptation")) >= 0, "Adaptation's own");
  assert.strictEqual(vm.runInContext("wbCauseFn({ who: 'Priority, on its limit' })", fresh()), "priority");
});

/* the poll clock (wbTick), captured: the callback setInterval was given, run as one tick of the clock */
function clockOf(c){
  const ticks = [];
  c.setInterval = fn => { ticks.push(fn); return 2; };
  vm.runInContext("wbS().timer = null;", c);
  c.wbViewer(WEB);
  assert.strictEqual(ticks.length, 1, "one clock");
  return async () => { ticks[0](); for (let i = 0; i < 6; i++) await sleep(); };
}
test("W52: on All five and on the causing function's pane the clock reads the chat again, so a card raised or answered elsewhere shows there as in Chat", async () => {
  const card = h => h.indexOf('<div class="dpask hard wbq wbopt wb"><div class="dpk">Identity asks</div><div class="dpasks">The plan could not be approved.</div>');
  const chats = () => readsOf(c, /\/api\/native\/r3\/chat$/).length;
  const o = { map: rtMap(), board: FV_BOARD, fv: fvOf({}), chat: qChat({}), fnpage: fnPageOf };
  const c = await v2(o);
  click(c, { wbtab: "five" }); await sleep();
  assert.ok(card(await paint(c)) < 0, "nothing waits yet");
  const tick = clockOf(c);
  /* a blocked card is raised while the owner sits on All five: the five's read says needs you, and the card stands */
  o.chat = cardsChat(); o.fv = fvOf({ states: { Identity: "waiting_on_you" }, cycle: { needs_you: true, asks: 1 } });
  let before = chats();
  await tick();
  let html = await paint(c);
  assert.ok(chats() > before, "the chat read again on the clock, on All five");
  assert.ok(card(html) >= 0 && card(html) < html.indexOf('class="fvgrid'), "the card on All five, at its top");
  /* answered elsewhere (Root's chat): the card goes here too */
  o.chat = qChat({});
  await tick();
  assert.ok(card(await paint(c)) < 0, "answered elsewhere, gone from All five");
  /* the same on the pane of the function that caused it */
  html = await fnCard(c, "adaptation");
  assert.ok(card(html) < 0, "nothing on Adaptation's pane yet");
  o.chat = cardsChat();
  before = chats();
  await tick();
  html = await fnCard(c, "adaptation");
  assert.ok(chats() > before, "the chat read again on the clock, on a function's pane");
  assert.ok(card(html) >= 0 && card(html) < html.indexOf("<h3>The function</h3>"), "the card on Adaptation's pane, above its page");
});

test("W52: in Chat an open blocked card is pinned at the top while it waits; chosen, it stands quiet at its time", async () => {
  const m = rtMap(); m.root = "r2";
  const c = await opened({ map: m, chat: cardsChat() });
  view(c); await sleep(); await sleep();
  let html = view(c);
  const pin = html.indexOf('<div class="wbchat wb"><div class="wbpin wb"><div class="dpask hard wbq wbopt wb">');
  assert.ok(pin >= 0 && pin < html.indexOf(">a website<"), "the blocked card is first in the chat, pinned");
  assert.ok(html.indexOf(">a website<") < html.indexOf('<div class="dpask wbq wb">') && html.indexOf('<div class="dpask wbq wb">') < html.indexOf("Filed in the Brief."),
            "the question stands at its time in the flow");
  assert.strictEqual(html.split("The plan could not be approved.").length, 2, "the card is said once");
  assert.ok(/\.wbpin\{position:sticky;top:0;[^}]*background:var\(--surface\)/.test(css), "pinned as the chat scrolls, on an opaque base");
  const done = await blockedOpen({ id: "stop", label: "Stop here", at: "2026-10-23T10:26:00+05:30", by: "the owner", words: null });
  html = view(done);
  assert.ok(html.indexOf("wbpin") < 0 && /<div class="dpask gone wbq wbopt wb">/.test(html), "chosen, it goes quiet in the flow");
});

/* ── PRD M4.7: Coordination's pane (S7) and the engine card (S17) ────────────────────────────────────────────── */
const T = h => "2026-10-26T" + h + ":00+05:30";
/* S7's sample data, as functions_view.coordination answers it */
function coordOf(o){
  o = o || {};
  const row = (engine, starts, win, state, why, at, wrote) => ({ engine, on: "after a new thing", starts, window_min: win, since: T("10:00"),
    state, word: { running: "running", turn: "its turn", waits: "waits", ran: "ran", stopped: "stopped where it was" }[state], why, at,
    last: wrote ? { at, status: "ok", wrote } : null });
  const tt = o.empty ? [] : o.stopped ? ["Plan", "Write", "Check", "Publish"].map(n => row(n, "after a new Brief", 15, "stopped", null, null, null))
    : o.done ? ["Plan", "Write", "Check", "Publish"].map(n => row(n, "after a new Brief", 15, "ran", null, T("10:40"), n + " made v1"))
    : [row("Plan", "after a new Brief", 15, "ran", null, T("10:22"), "Site plan v2"),
       row("Write", "after a new Site plan", 30, "turn", null, T("10:23"), null),
       row("Check", "after a new Pages", 5, "waits", "Pages v2 is not filed yet", null, null),
       row("Publish", "after a Build that passed", 10, "waits", "Build v2 is not filed yet", null, null)];
  return { line: tt.map(r => r.engine), registered: 2, timetable: tt,
    left_out: o.empty ? [] : [{ engine: "Photo Picker", since: T("10:08") }],
    holds: tt.filter(r => r.state === "waits").map(r => ({ engine: r.engine, why: r.why })),
    handoffs: [{ art: "Brief", v: 3, by: "Owner", says: "Identity, from your words", readers: ["Plan"] },
               { art: "Site plan", v: 2, by: "Plan", says: "Plan", readers: ["Write"] },
               { art: "Pages", v: 1, by: "Write", says: "Write", readers: ["Check"] },
               { art: "Live site", v: null, by: null, says: null, readers: ["Audit", "Adaptation"] }],
    chain: { of: "Brief v3", used: 3, limit: 12, share: 0.25 },
    alarms: o.alarm ? [{ engine: "Write", text: "Write has run past its window", at: T("10:50") }] : [],
    ties: o.tie ? [{ pick: "Write", said: "Coordination chose Write first", why: "the pages wait on it", at: T("10:23"), today: true }] : [] };
}
function coordPage(o){
  return fn => {
    const p = fnPageOf(fn);
    if (fn === "coordination"){
      p.j2 = coordOf(o);
      p.node = o && o.stopped ? { name: "Coordination", state: "quiet", word: "stopped", line: "" }
        : { name: "Coordination", state: o && o.alarm ? "fault" : "working", word: o && o.alarm ? "fault" : "working", line: "Write's turn" };
    }
    return p;
  };
}
/* no count at rest: times, names such as Site plan v2, D2, FC1, Round 2 or Version 1, and a window in minutes are not counts */
const atRest = h => words(h).replace(/\b(?:v|[A-Z]{1,3}|Round |[Vv]ersion )\d+\b/g, " ").replace(/\b\d+ min\b/g, " ");

test("S7: Coordination's pane opens on its timetable, who makes and who reads, the chain, alarms and ties, its page folded", async () => {
  const c = await opened({ map: rtMap(), fnpage: coordPage() });
  const html = await fnCard(c, "coordination");
  assert.ok(/<div class="wbcohead wb"><svg class="dpfnmk fn-coordination"[^]*?<b>Coordination<\/b><span class="dpdot breath"><\/span><span>working · Write(&#39;|')s turn<\/span><\/div>/.test(html), "the frame: mark, name, a dot and its word");
  const tt = html.slice(html.indexOf("<h3>Timetable</h3>"), html.indexOf("<h3>Who makes it, who reads it</h3>"));
  assert.ok(/data-wbengine="Plan"[^>]*><span class="dpdot ok"><\/span><b>Plan<\/b><span>after a new Brief<\/span><span class="wbttw">window 15 min<\/span><span class="wbttn">ran 10:22 · Site plan v2<\/span>/.test(tt), tt.slice(0, 400));
  assert.ok(/<span class="dpdot breath"><\/span><b>Write<\/b><span>after a new Site plan<\/span><span class="wbttw">window 30 min<\/span><span class="wbttn">its turn since 10:23<\/span>/.test(tt), "Write has the turn");
  assert.ok(/<span class="dpdot wait"><\/span><b>Check<\/b>[^]*?<span class="wbttn">waits: Pages v2 is not filed yet<\/span>/.test(tt), "a wait on the work before it is the hollow ring, with its reason");
  assert.ok(/<b>Publish<\/b><span>after a Build that passed<\/span>[^]*?waits: Build v2 is not filed yet/.test(tt));
  assert.ok(/Left out of the plan: Photo Picker \(10:08\)/.test(tt), "what the plan left out, under it");
  const who = html.slice(html.indexOf("<h3>Who makes it, who reads it</h3>"), html.indexOf("<h3>The chain</h3>"));
  assert.ok(/<button type="button" class="wbhand wb" data-wbart="brief"><b>Brief v3<\/b><span>Identity, from your words<\/span><span class="wbttn">read by Plan<\/span><\/button>/.test(who), who.slice(0, 300));
  assert.ok(/<div class="wbhand wb"><b>Live site<\/b><span>not made yet<\/span><span class="wbttn">read by Audit, Adaptation<\/span><\/div>/.test(who), "a thing not made yet opens nothing");
  assert.ok(/<div class="wbtrio">[^]*<h3>The chain<\/h3><div title="The chain from Brief v3: 3 of 12"><div class="dpbar"><i style="width:25%"><\/i><\/div><\/div>/.test(html), "the chain is a bar; its numbers the hover");
  assert.ok(/<h3>Alarms<\/h3><div class="o2quiet dpq">None<\/div>/.test(html) && /<h3>Ties<\/h3><div class="o2quiet dpq">None today<\/div>/.test(html));
  assert.ok(/<details class="wbfold wb"><summary>The function page<\/summary>[^]*?<h3>The function<\/h3>/.test(html), "the page folds at the bottom");
  assert.ok(html.indexOf("<h3>Who goes first</h3>") > html.indexOf("<summary>The function page</summary>"), "its table and steps stay under it");
  assert.ok(!/<h3>Queue<\/h3>|<h3>Locks<\/h3>/.test(html), "the first build's cards give way to the timetable");
  const t = atRest(html);
  assert.ok(!/\d/.test(t), "a count at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  assert.ok(!/charter|internal system|\/api\/|\.json/i.test(t), "no charter, no inside word, no path");
  /* a row opens its engine card; an artifact its filed work */
  click(c, { wbengine: "Check" }); await sleep();
  assert.strictEqual(vm.runInContext("S.wb.tab['r3']", c), "engine");
  assert.strictEqual(vm.runInContext("S.wb.sel['r3']", c), "Check");
});

test("S7: the states the pane names: no plan yet, a fault in Alarms with '!', a tie, stopped, and nothing waiting", async () => {
  const pane = async o => fnCard(await opened({ map: rtMap(), fnpage: coordPage(o) }), "coordination");
  assert.ok(/<h3>Timetable<\/h3><div class="o2quiet dpq">No plan yet<\/div>/.test(await pane({ empty: true })), "empty before Root's check");
  const fault = await pane({ alarm: true });
  assert.ok(/<b>Coordination<\/b><b class="dpfnb block" aria-hidden="true">!<\/b><span class="dpdot block"><\/span><span>fault · Write(&#39;|')s turn<\/span>/.test(fault), "the head carries '!' and the word");
  assert.ok(/<h3>Alarms<\/h3><div class="dprow"><span class="dpdot block"><\/span><span>Write<div class="dpchk">Write has run past its window<\/div>/.test(fault), "a block row in Alarms");
  const tie = await pane({ tie: true });
  assert.ok(/<h3>Ties<\/h3><div class="dprow"><span class="dpdot ok"><\/span><span>Coordination chose Write first<div class="dpchk">the pages wait on it · 10:23<\/div>/.test(tie), "a tie it broke");
  const stopped = await pane({ stopped: true });
  assert.strictEqual((stopped.match(/stopped where it was/g) || []).length, 4, "every engine stopped where it was");
  assert.ok(/<span class="dpdot off"><\/span><span>stopped<\/span>/.test(stopped));
  assert.ok(/<div class="o2quiet dpq">Nothing waiting<\/div>/.test(await pane({ done: true })), "done: nothing waiting");
  const first = await fnCard(await opened({ map: rtMap() }), "coordination");
  assert.ok(/class="o2skel"/.test(first) && /<h3>Who goes first<\/h3>/.test(first), "loading: a skeleton, its table under it");
});

test("S7: the pane paints again when the timetable moves, and not when it says the same thing", () => {
  const c = fresh();
  const a = coordPage()("coordination"), b = coordPage()("coordination");
  assert.strictEqual(c.wbFnPageSig(a), c.wbFnPageSig(b), "the same read paints nothing");
  b.j2.timetable[2] = Object.assign({}, b.j2.timetable[2], { state: "turn", word: "its turn", why: null, at: T("10:31") });
  assert.notStrictEqual(c.wbFnPageSig(a), c.wbFnPageSig(b), "Check's turn paints");
  const t = coordPage({ tie: true })("coordination");
  assert.notStrictEqual(c.wbFnPageSig(a), c.wbFnPageSig(t), "a tie paints");
});

/* S17's sample data, as functions_view.engine_card answers it */
function cardOf(o){
  o = o || {};
  const waits = !!o.waits;
  return { engine: "Write", head: waits ? { state: "waits", word: "waits", why: "Pages v2 is not filed yet", at: null, round: null }
                                          : { state: "running", word: "running", why: null, at: T("10:23"), round: 2 },
    motor: { slot: "after Site plan v2", starts: "after a new Site plan", once: true, says: "ran once per slot", window_min: 30, today: 0.1 },
    five: [{ fn: "Identity", state: "ok", says: "lets it start: no rule holds it", at: null, share: null },
           { fn: "Adaptation", state: "ok", says: "proposed it in the plan Root registered", at: null, share: null },
           { fn: "Priority", state: o.held ? "block" : "ok", says: o.held ? "holds it: today's limit is spent" : "let the run start inside today's limit", at: null, share: o.held ? 1 : 0.1 },
           { fn: "Coordination", state: waits ? "wait" : "breath", says: waits ? "keeps its slot: Pages v2 is not filed yet" : "gave it the turn", at: waits ? null : T("10:23"), share: 0.3 },
           { fn: "Audit", state: "off", says: "will read the Live site it leads to", at: null, share: null }] };
}

test("S17: the engine card carries its head on every tab, the motor folded in, and the five beside it; no Motor row", async () => {
  const c = await opened({ map: rtMap(), engine: { card: cardOf() } });
  assert.ok(!/data-wbtab="motor"/.test(list(c)), "the Motor row leaves the list column");
  click(c, { wbengine: "Write" }); view(c); await sleep(); await sleep();
  let html = view(c);
  assert.ok(/<div class="wbenghead wb"><b>Write<\/b><span class="dpchk">engine<\/span><span class="dpdot breath"><\/span><span>running · Round 2 · since 10:23<\/span><\/div>/.test(html), "the head, on the Steps tab");
  assert.ok(/data-wbpane="steps"/.test(html) && /<h3>Starts<\/h3>/.test(html), "the steps are still the first tab");
  vm.runInContext("S.wb.pane['r3:Write'] = 'engine';", c);
  html = view(c);
  const motor = html.slice(html.indexOf("<h3>Motor</h3>"), html.indexOf("<h3>With the five functions</h3>"));
  assert.ok(/<span class="dpk">Slot<\/span><span class="dpdot ok"><\/span><span>after Site plan v2 · ran once per slot · window 30 min<\/span><span title="Today"><div class="dpbar"><i style="width:10%"><\/i><\/div><\/span>/.test(motor), motor);
  const five = html.slice(html.indexOf("<h3>With the five functions</h3>"), html.indexOf("<h3>The engine</h3>"));
  ["identity", "adaptation", "priority", "coordination", "audit"].forEach(fn =>
    assert.ok(new RegExp('<button type="button" class="wbfivefn fn-' + fn + ' wb" data-dptab="' + fn + '"><svg class="dpfnmk fn-' + fn).test(five), fn + ": its chip opens its pane"));
  assert.ok(/Identity<\/button><span class="dpdot ok"><\/span><span>lets it start: no rule holds it<\/span>/.test(five));
  assert.ok(/Coordination<\/button><span class="dpdot breath"><\/span><span>gave it the turn at 10:23<\/span><span><div class="dpbar"><i style="width:30%">/.test(five), "Coordination gave it the turn, with the chain's bar");
  assert.ok(/Audit<\/button><span class="dpdot off"><\/span><span>will read the Live site it leads to<\/span><span><\/span>/.test(five));
  assert.ok(!/<h3>In its slot<\/h3>/.test(html), "the motor replaces the old slot card");
  const t = atRest(html);
  assert.ok(!/\d/.test(t), "a count at rest: " + (t.match(/.{0,30}\d.{0,30}/) || [""])[0]);
  /* waiting: the head says why, and the holding function's row says it too */
  const w = await opened({ map: rtMap(), engine: { card: cardOf({ waits: true, held: true }) } });
  click(w, { wbengine: "Write" }); view(w); await sleep(); await sleep();
  vm.runInContext("S.wb.pane['r3:Write'] = 'engine';", w);
  html = view(w);
  assert.ok(/<span class="dpdot wait"><\/span><span>Waits: Pages v2 is not filed yet<\/span>/.test(html), "the head reads Waits: and the reason");
  assert.ok(/Priority<\/button><span class="dpdot block"><\/span><span>holds it: today(&#39;|')s limit is spent<\/span>/.test(html), "held by budget: Priority's row is block");
  /* a department of the first build keeps its engine card as it was */
  const old = await opened({ engine: { card: cardOf() } });
  click(old, { wbengine: "Write" }); view(old); await sleep(); await sleep();
  assert.ok(/<h3>In its slot<\/h3>/.test(view(old)) && !/wbenghead|With the five functions/.test(view(old)));
});

/* PRD M4.7 (round 1, gap 8): only the list's Motor row had gone; the Map's Record box and every box of a thing not made
   yet still opened the Motor screen, and the viewer still served it on the runtime. Now no Map target is the Motor: the
   Record opens the last thing filed (the Chat while nothing is), a thing not made yet the card of the engine that makes
   it (the Brief, which the owner's words make, the Chat), and the runtime's viewer never draws a Motor screen. */
test("S17: on the runtime the Map emits no Motor target, and the viewer serves no Motor screen", async () => {
  let [c, html] = await mapWith({ map: rtMap({ live: false, versions: { "Brief": 1, "Site plan": 1, "Pages": 0, "Build": 0, "Live site": 0 } }), fv: fvOf({}) });
  assert.ok(!/data-wbtab="motor"/.test(html), "no Motor target on the picture or the narrow list");
  assert.ok(/<g class="n" data-wbart="site-plan" transform="[^"]*"><rect class="bx"[^>]*\/><text x="10" y="20">Record<\/text>/.test(html), "the Record opens the last thing filed");
  assert.ok(/<g class="n work" data-wbengine="Write" transform="[^"]*"><rect class="bx"[^>]*\/><text x="8" y="17">Pages<\/text>[\s\S]*?<title>Pages · not made yet · Write makes it<\/title>/.test(html), "not made yet: the engine that makes it");
  assert.ok(/<g class="n work" data-wbengine="Publish" transform="[^"]*"><rect class="bx"[^>]*\/><text x="8" y="17">Live site<\/text>/.test(html));
  const cards = /<div class="wb2cards wb">([\s\S]*)$/.exec(html)[1];
  assert.ok(/<button type="button" class="wb2card wb" data-wbengine="Write"><span class="dpdot off"><\/span><b>Pages<\/b><span class="dpchk">not made yet<\/span><\/button>/.test(cards), "the narrow list goes the same way");
  click(c, { wbengine: "Write" });
  assert.strictEqual(vm.runInContext("S.wb.tab['r3']", c) + ":" + vm.runInContext("S.wb.sel['r3']", c), "engine:Write", "a click opens the engine's card");
  /* nothing filed: the Record and the Brief open the Chat, where the owner's words make it */
  [, html] = await mapWith({ map: rtMap({ live: false, versions: { "Brief": 0, "Site plan": 0, "Pages": 0, "Build": 0, "Live site": 0 } }), fv: fvOf({}) });
  assert.ok(!/data-wbtab="motor"/.test(html));
  assert.ok(/<g class="n" data-wbtab="chat" transform="[^"]*"><rect class="bx"[^>]*\/><text x="10" y="20">Record<\/text>/.test(html), "the Record, with nothing filed");
  assert.ok(/<g class="n work" data-wbtab="chat" transform="[^"]*"><rect class="bx"[^>]*\/><text x="8" y="17">Brief<\/text>[\s\S]*?<title>Brief · not made yet · your words make it<\/title>/.test(html), "the Brief");
  /* a Motor tab left from the first build, or set by hand, is not served on the runtime */
  vm.runInContext("S.wb.tab['r3'] = 'motor'; dpS().tab['r3'] = 'now';", c);
  const v = view(c);
  assert.ok(!/<h3>It only reads<\/h3>|<h3>What it does each tick<\/h3>/.test(v) && vm.runInContext("S.wb.tab['r3']", c) !== "motor", "no Motor screen on the runtime");
  /* the first build keeps its Motor screen (W7) */
  const old = await opened();
  click(old, { wbtab: "motor" });
  assert.ok(/<h3>What it does each tick<\/h3>/.test(view(old)), "the first build's Motor stays");
});

Promise.all(pending).then(() => {
  console.log("-".repeat(60));
  console.log(failed ? " " + failed + " failed (" + ran + " tests)" : " all passed (" + ran + " tests)");
  process.exit(failed ? 1 : 0);
});
