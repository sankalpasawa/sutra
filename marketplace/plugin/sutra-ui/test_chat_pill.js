#!/usr/bin/env node
"use strict";
/* test_chat_pill.js -- the combined governance + runtime pill (founder
   2026-09-23: "combine both the governance and the runtime", "the round shape
   with the accordion with the downward arrow", "a little bit left and right",
   "micro animations so that it's very smooth", and "make sure that the chat
   doesn't become buggy because of so many animations").

   What ships:
     - gvPillParts / gvPillHtml / gvRuntimeHtml / gvStepDots (05-chat.js): one
       round pill per turn inside [data-aturn]; live it is the loader (spinner +
       the ticker's runPhrase), settled it is the summary, opened it is the
       governance rows over ONE Runtime block;
     - gvPillMotion / gvFx: one-shot motion decided once per real event and
       remembered per turn, never per render; loops phase-locked to the clock;
     - turnControlClick (07-loaders.js): an open pill folds before it closes;
     - panel.css: the founder turn on the right, the pill's depth and motion,
       reduced motion off.
   The DOM-level pins for the same turns live in test_panel.js sections 28, 30,
   42 and 56 (full sandbox); this lane is the unit and rebuild-safety proof. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const J = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const helpers = J("02-helpers.js");
const state = J("01-state.js");
const chat = J("05-chat.js");
const render = J("06-render.js");
const loaders = J("07-loaders.js");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");

const queue = [];
const test = (n, f) => queue.push([n, f]);
const assert = (c, m) => { if (!c) throw new Error(m || "assertion failed"); };
const eq = (a, b, m) => assert(a === b, (m || "") + " expected " + JSON.stringify(b)
                                        + " got " + JSON.stringify(a));
const count = (h, re) => (h.match(re) || []).length;
let pass = 0, fail = 0;

function grab(src, name) {
  const start = src.indexOf("function " + name + "(");
  assert(start >= 0, "could not find function " + name);
  let i = src.indexOf("{", start), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error("unbalanced braces reading " + name);
}
function grabConst(src, name) {
  const m = new RegExp("^(?:const|let|var) " + name + "\\s*=[\\s\\S]*?;$", "m").exec(src);
  assert(m, "could not find const " + name);
  return m[0];
}

/* a lean sandbox: the SHIPPED pill, card and click functions, with the few
   collaborators they call stubbed to plain values */
function box(opts) {
  const o = opts || {};
  const b = { S: { thinkOpen: {}, toolOpen: {}, govOpen: {}, sessions: [], sideTurns: {} },
              rendered: 0, console, timers: [], NOW: 1000000 };
  b.render = () => { b.rendered++; };
  b.setTimeout = (fn, ms) => { b.timers.push({ fn, ms }); return b.timers.length; };
  b.matchMedia = () => ({ matches: !!o.reduce });
  b.Date = { now: () => b.NOW };
  b.dPath = (ref) => "D0 > " + ref;
  b.mdHtml = (s) => "<p>" + String(s) + "</p>";
  b.caretHtml = (h) => h + '<span class="caret"></span>';
  b.nth = (n) => (n === 2 ? "nd" : n === 3 ? "rd" : "th");
  b.queueState = (t) => (t && t._queued) || null;
  b.globalThis = b;
  vm.createContext(b);
  vm.runInContext([
    grabConst(helpers, "esc"),
    grab(state, "fmtDur"), grab(state, "runPhrase"),
    grabConst(helpers, "TOOL_KIND_BY_NAME"), grabConst(helpers, "TOOL_KINDS"),
    grabConst(helpers, "TOOL_KIND_LABEL"),
    grab(helpers, "toolKindOf"), grab(helpers, "toolKindFor"),
    grab(render, "_tcBase"), grab(render, "_tcDiff"), grab(render, "toolCardParts"),
    grab(render, "toolCardHtml"), grabConst(render, "TOOLCARD_WINDOW"),
    grab(render, "toolCallsHtml"),
    grab(chat, "parseGov"), grab(chat, "gvBody"), grab(chat, "gvClean"), grab(chat, "gvAgents"),
    grab(chat, "gvPanelRowsHtml"),
    grabConst(chat, "PILL_FX_MAX"), grabConst(chat, "PILL_FOLD_MS"), grab(chat, "gvFx"), grab(chat, "gvPillParts"),
    grab(chat, "gvPillMotion"), grabConst(chat, "STEP_DOT"), grab(chat, "gvStepDots"),
    grab(chat, "gvAgentsHtml"), grab(chat, "gvMarkNewCards"), grab(chat, "gvRuntimeHtml"),
    grab(chat, "gvPhase"), grab(chat, "gvPillHtml"), grab(chat, "turnResponse"),
    grab(loaders, "pillReducedMotion"),
    grab(loaders, "turnControlClick"),
  ].join("\n"), b, { filename: "pill#extract" });
  return b;
}

const GOV = "[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]\n"
          + "DEPTH: 5/5 | TASK: \"x\" | EFFORT: 1 | COST: 0 | IMPACT: y\n"
          + "STEP TRACE turn ab12 (adherence=on)\n"
          + "   1 classify   runtime  done     INBOUND\n"
          + "   2 resolve    runtime  done     FOLLOW\n"
          + "   9 atom       runtime  pending  no open atom\n"
          + "\nThe export test now passes.";
const DOMAIN = { name: "Sutra Desktop", ref: "dref-1" };
const run = (o) => Object.assign({ id: "r" + Math.random().toString(36).slice(2, 7), name: "Read",
                                   summary: "a.md", running: false, ok: true, startedAt: 1, endedAt: 2 }, o);
const RUNS = [run({ id: "a" }), run({ id: "b", name: "Bash", command: "npm test", summary: "npm test", ok: false }),
              run({ id: "c", name: "Edit", summary: "x.js" })];
const settled = (o) => Object.assign({ uid: "u1", streaming: false, response: GOV, domain: DOMAIN,
                                       confidence: 0.7, tools: RUNS.map(r => r.name), toolRuns: RUNS,
                                       duration_ms: 42100, cost_usd: 0.0812, num_turns: 9 }, o);
const liveT = (o) => Object.assign({ uid: "L1", streaming: true, response: "", domain: DOMAIN,
                                     tools: [], toolRuns: [] }, o);

/* ── 1. what the closed pill says ─────────────────────────────────────────── */
test("1a. settled: one pill, governance words and what ran, failure in red", () => {
  const b = box();
  const h = b.turnResponse(settled());
  eq(count(h, /class="gv gv-pill/g), 1, "one pill");
  assert(/<span>D5<\/span>/.test(h), "depth");
  assert(/<span class="gv-leaf">Sutra Desktop<\/span>/.test(h), "department");
  assert(/risk:low/.test(h), "risk");
  assert(/<span>3 tool calls<\/span>/.test(h), "tool count");
  assert(/<span class="gv-pfail">1 failed<\/span>/.test(h), "the failure is said");
  assert(/class="gv-pulse gv-bad"/.test(h), "a failure turns the dot red");
  assert(/<span class="gv-chev" aria-hidden="true">▼<\/span><\/button>/.test(h), "the down arrow closes the pill");
});
test("1b. nothing failed: the accent dot, no failure word", () => {
  const b = box();
  const h = b.turnResponse(settled({ toolRuns: [run({ id: "a" })], tools: ["Read"] }));
  assert(/class="gv-pulse"/.test(h) && !/gv-pfail/.test(h), h.slice(0, 300));
  assert(/<span>1 tool call<\/span>/.test(h), "singular");
});
test("1c. held and unresolved keep their governance colour on the closed pill", () => {
  const b = box();
  const held = b.turnResponse(settled({ uid: "h1", mode: "floor", toolRuns: [], tools: [] }));
  assert(/gv-pulse gv-amber/.test(held) && /gv-pwarn">held</.test(held), "held is amber and said");
  const un = b.turnResponse(settled({ uid: "h2", domain: null, toolRuns: [], tools: [] }));
  assert(/gv-pulse gv-amber/.test(un) && /gv-unres">unresolved</.test(un), "unresolved is amber and said");
});
test("1d. stopped and failed turns say so on the pill", () => {
  const b = box();
  assert(/gv-pwarn">stopped by you</.test(b.turnResponse(settled({ uid: "s1", stopped: true }))));
  const e = b.turnResponse(settled({ uid: "s2", error: "boom", toolRuns: [], tools: [] }));
  assert(/gv-pfail">turn failed</.test(e) && /gv-pulse gv-bad/.test(e), "an errored turn is red");
  assert(/boom/.test(e), "the real error text still shows");
});
test("1e. the old square pills and fold row are gone from the block", () => {
  const b = box();
  const h = b.turnResponse(settled());
  assert(!/p-ok">answered|tfhead|gv-thinkbtn/.test(h), "answered pill, fold row or loader button came back");
  assert(!/42\.1s · \$0\.0812/.test(h.split("<div class=\"md\"")[0].replace(/gv-panel[\s\S]*/, "")),
    "duration and cost belong in the open pill, not on the turn");
});
test("1f. a terminal transcript: a pill only when something ran or was captured", () => {
  const b = box();
  eq(count(b.turnResponse({ uid: "x1", transcript: true, response: "plain answer" }), /gv-pill/g), 0,
     "a plain terminal answer gets no pill");
  const h = b.turnResponse({ uid: "x2", transcript: true, response: "a",
                             calls: [{ id: "c1", name: "Read", input: "a.md" }, { id: "c2", name: "Bash", input: "ls", is_error: true }] });
  assert(/<span>2 tool calls<\/span>/.test(h) && /1 failed/.test(h), "calls counted, is_error counted");
  assert(!/unresolved/.test(h), "a terminal turn never claims a failed classification");
});
test("1g. names-only transcript: counted, never judged", () => {
  const b = box();
  const h = b.turnResponse({ uid: "x3", transcript: true, response: "a", tools: ["Read", "Read", "Bash"] });
  assert(/<span>3 tool calls<\/span>/.test(h) && !/failed/.test(h), h);
});

/* ── 2. live: the pill is the loader ──────────────────────────────────────── */
test("2a. live: spinner, the measured strip as a text-only ticker anchor", () => {
  const b = box();
  const h = b.turnResponse(liveT({ toolRuns: [run({ id: "a", running: true, ok: null })], tools: ["Read"] }));
  assert(/gv-pbtn is-live/.test(h) && /gv-pulse gv-run/.test(h), "live pill with spinner");
  const m = h.match(/class="gv-tlabel" data-runstrip="L1">([^<]*)</);
  assert(m && !/[<>]/.test(m[1]), "the ticker anchor holds text only");
});
test("2b. a queued turn is not live and does not spin", () => {
  const b = box();
  const h = b.turnResponse(liveT({ uid: "Q1", _queued: { behind: true, pos: 2 } }));
  assert(!/is-live|gv-run/.test(h) && /gv-pulse gv-wait/.test(h) && /Queued/.test(h), h.slice(0, 400));
});
test("2c. loops are phase-locked: negative delays inside one period", () => {
  const b = box();
  b.NOW = 1234567;
  const h = b.turnResponse(liveT({ uid: "P1" }));
  const m = h.match(/--gv-sheen-d:-(\d+)ms;--gv-spin-d:-(\d+)ms;--gv-shim-d:-(\d+)ms/);
  assert(m, "phase style missing");
  eq(+m[1], 1234567 % 2400, "sheen"); eq(+m[2], 1234567 % 700, "spin"); eq(+m[3], 1234567 % 1800, "shimmer");
});
test("2d. a rebuild at a later instant continues the loop instead of restarting it", () => {
  const b = box();
  b.NOW = 1000; const a = b.turnResponse(liveT({ uid: "P2" }));
  b.NOW = 1300; const c = b.turnResponse(liveT({ uid: "P2" }));
  assert(/--gv-sheen-d:-1000ms/.test(a) && /--gv-sheen-d:-1300ms/.test(c),
    "the delay must advance with the clock, or every patch restarts the sheen");
});

/* ── 3. the open pill ─────────────────────────────────────────────────────── */
test("3a. open: Turn row, governance rows, then ONE Runtime block", () => {
  const b = box(); b.S.govOpen = { u1: true };
  const t = settled(); t._n = 4;
  const h = b.turnResponse(t);
  assert(/gv-label">Turn<\/span><span class="gv-val">turn 4 · DIRECT · 42\.1s · \$0\.0812 · 9 model turns · matched 0\.70/.test(h), "Turn row");
  assert(/gv-label">Placement/.test(h), "placement row");
  eq(count(h, /class="gv-rt"/g), 1, "one Runtime block");
  assert(h.indexOf("Placement") < h.indexOf('class="gv-rt"'), "governance above runtime");
  eq(count(h, /class="toolcall tcard /g), 3, "the cards the turn always had");
  assert(/aria-expanded="true"/.test(h));
});
test("3b. the step trace is drawn once, as dots, inside the Runtime block", () => {
  const b = box(); b.S.govOpen = { u1: true };
  const h = b.turnResponse(settled());
  assert(!/gv-label">Step trace</.test(h), "the step trace must not also print as a governance row");
  eq(count(h, /class="gv-step"/g), 3, "one dot per parsed step");
  assert(/gv-sd ok[^>]*><\/i>classify/.test(h) && /gv-sd n[^>]*><\/i>atom/.test(h), "done is filled, pending is hollow");
  assert(/2 of 3 steps · 3 tool calls · <span class="gv-pfail">1 failed/.test(h), "the block header counts");
});
test("3c. a step trace that does not parse is shown verbatim, never guessed", () => {
  const b = box(); b.S.govOpen = { v1: true };
  const odd = "STEP TRACE turn zz\n   something unexpected here\n\nbody";
  const h = b.turnResponse(settled({ uid: "v1", response: odd }));
  assert(/<pre class="gv-pre">[^<]*something unexpected here/.test(h), h);
});
test("3d. an open live pill with nothing run says so", () => {
  const b = box(); b.S.govOpen = { L1: true };
  assert(/nothing has run yet in this turn/.test(b.turnResponse(liveT())));
});
test("3f. a panel turn stopped before any output keeps its pill (review)", () => {
  const b = box();
  const h = b.turnResponse({ uid: "e1", streaming: false, stopped: true, response: "", tools: [], toolRuns: [], domain: DOMAIN });
  assert(/gv-pill/.test(h) && /Sutra Desktop/.test(h) && /stopped by you/.test(h), "where it was filed is lost: " + h);
  eq(b.turnResponse({ uid: "e2", transcript: true, response: "" }), "", "an empty terminal turn draws nothing");
});
test("3g. a long chat numbers its turns absolutely (review)", () => {
  const src = grab(chat, "sessionBody");
  assert(/all\.slice\(-TURN_WINDOW\)\.map\(\(t, j\) => turnBlock\(t, hidden \+ j\)\)/.test(src),
    "the windowed turns must get their absolute index");
});
test("3e. closed means closed: no panel, no cards", () => {
  const b = box();
  const h = b.turnResponse(settled());
  assert(!/gv-panel|toolcall tcard|gv-rt/.test(h), "a closed pill renders its panel");
});

/* ── 4. motion fires once per real event, never on a rebuild ──────────────── */
test("4a. the AI side enters from the left once, on its first live render only", () => {
  const b = box();
  const t = liveT({ uid: "M1" });
  eq(count(b.turnResponse(t), /class="a gv-in-l"/g), 1, "first render");
  eq(count(b.turnResponse(t), /gv-in-l/g), 0, "patchTurn rebuild");
  eq(count(b.turnResponse(t), /gv-in-l/g), 0, "render() rebuild");
});
test("4b. a failure glows once, in the render where the count first rises", () => {
  const b = box();
  const t = liveT({ uid: "M2", toolRuns: [run({ id: "a" })], tools: ["Read"] });
  b.turnResponse(t);
  t.toolRuns = [run({ id: "a" }), run({ id: "b", ok: false })];
  eq(count(b.turnResponse(t), /gv-flash/g), 1, "the failing frame");
  eq(count(b.turnResponse(t), /gv-flash/g), 0, "the next rebuild");
  t.toolRuns = t.toolRuns.concat([run({ id: "c", ok: false })]);
  eq(count(b.turnResponse(t), /gv-flash/g), 1, "a second failure glows again");
});
test("4c. a replayed turn that already failed loads still", () => {
  const b = box();
  const h = b.turnResponse(settled({ uid: "M3" }));
  assert(!/gv-flash|gv-settle|gv-in-l/.test(h), "no motion on a page load");
});
test("4d. the spinner settles once when the turn ends", () => {
  const b = box();
  const t = liveT({ uid: "M4", response: GOV });
  b.turnResponse(t); b.turnResponse(t);
  t.streaming = false;
  eq(count(b.turnResponse(t), /gv-settle/g), 1, "the settling frame");
  eq(count(b.turnResponse(t), /gv-settle/g), 0, "every later rebuild");
});
test("4e. opening unfolds in exactly one render, then the flag is spent", () => {
  const b = box(); b.S.govOpen = { u1: true }; b.S._pillOpening = "u1";
  eq(count(b.turnResponse(settled()), /gv-opening/g), 1, "the click's render");
  eq(b.S._pillOpening, null, "flag spent");
  eq(count(b.turnResponse(settled()), /gv-opening/g), 0, "a later rebuild does not unfold again");
});
test("4f. a row that arrives while open rises in once; nothing else re-animates", () => {
  const b = box(); b.S.govOpen = { M5: true }; b.S._pillOpening = "M5";
  const t = liveT({ uid: "M5", toolRuns: [run({ id: "a" }), run({ id: "b" })], tools: ["Read", "Read"] });
  eq(count(b.turnResponse(t), /gv-enter/g), 0, "the opening render staggers instead");
  t.toolRuns = t.toolRuns.concat([run({ id: "c", running: true, ok: null })]);
  const h = b.turnResponse(t);
  eq(count(h, /gv-enter/g), 1, "exactly the new row");
  assert(/tcard gv-enter k-[a-z_]+ run"/.test(h), "and it is the last one");
  eq(count(b.turnResponse(t), /gv-enter/g), 0, "the same rows on a rebuild");
});
test("4g. closing forgets the row memory, so the next open staggers again", () => {
  const b = box(); b.S.govOpen = { M6: true };
  const t = settled({ uid: "M6" });
  b.turnResponse(t);
  b.S.govOpen = {}; b.turnResponse(t);
  eq(b.S._pillFx.M6.rows, -1);
});
test("4h. the motion memory is bounded", () => {
  const b = box();
  for (let i = 0; i < 450; i++) b.gvFx("k" + i);
  assert(Object.keys(b.S._pillFx).length <= 400, "memory grew past its bound");
  assert(b.S._pillFx.k449 && !b.S._pillFx.k0, "the oldest are dropped, the newest kept");
});
test("4j. a turn drawn while queued does not slide in again when it starts (review)", () => {
  const b = box();
  const t = liveT({ uid: "M8", _queued: { behind: true, pos: 2 } });
  eq(count(b.turnResponse(t), /gv-in-l/g), 0, "queued");
  delete t._queued;
  eq(count(b.turnResponse(t), /gv-in-l/g), 0, "it was already on screen");
});
test("4k. a settled turn has no looping motion, even for a step left 'running' (review)", () => {
  const b = box(); b.S.govOpen = { M9: true };
  const trace = "STEP TRACE turn q\n   1 classify   runtime  done     x\n   2 lens       model    running  y\n\nok";
  const settledH = b.turnResponse(settled({ uid: "M9", response: trace }));
  assert(!/gv-sd run/.test(settledH) && /gv-sd n[^>]*><\/i>lens/.test(settledH), "a settled step spins");
  b.S.govOpen = { M10: true };
  const liveH = b.turnResponse(liveT({ uid: "M10", response: trace }));
  assert(/gv-sd run[^>]*><\/i>lens/.test(liveH), "a live running step spins");
  assert(/<div class="gv gv-pill gv-open" data-pill="M10" style="--gv-sheen-d:/.test(liveH),
    "the phase sits on the wrapper, so the open panel inherits it");
});
test("4i. the renderer never mutates the turn", () => {
  const b = box();
  const t = liveT({ uid: "M7", toolRuns: RUNS, tools: ["Read"] });
  const before = JSON.stringify(t);
  b.turnResponse(t); b.turnResponse(t);
  eq(JSON.stringify(t), before);
});

/* ── 5. the click: open, fold, close ──────────────────────────────────────── */
const pillNode = (open) => {
  const cls = new Set(["gv", "gv-pill"].concat(open ? ["gv-open"] : []));
  return { classList: { contains: c => cls.has(c), add: c => cls.add(c), _s: cls } };
};
const clickOn = (b, uid, pill) => b.turnControlClick({ target: { closest: sel =>
  sel === ".turn" ? {} : sel === "[data-govopen]" ? { dataset: { govopen: uid }, closest: s => (s === ".gv-pill" ? pill : null) } : null } });

test("5a. opening sets the one-render flag and renders", () => {
  const b = box(); const p = pillNode(false);
  clickOn(b, "u9", p);
  eq(b.S.govOpen.u9, true); eq(b.S._pillOpening, "u9"); eq(b.rendered, 1);
});
test("5b. closing folds the node on screen first, then closes and renders", () => {
  const b = box(); b.S.govOpen = { u9: true }; const p = pillNode(true);
  clickOn(b, "u9", p);
  assert(p.classList._s.has("gv-closing"), "the fold class is on the live node");
  eq(b.S.govOpen.u9, true, "state waits for the fold"); eq(b.rendered, 0);
  eq(b.timers.length, 1); eq(b.timers[0].ms, vm.runInContext("PILL_FOLD_MS", b));
  b.timers[0].fn();
  eq(b.S.govOpen.u9, false); eq(b.rendered, 1);
});
test("5c. a click during the fold is ignored", () => {
  const b = box(); b.S.govOpen = { u9: true }; const p = pillNode(true);
  clickOn(b, "u9", p); clickOn(b, "u9", p);
  eq(b.timers.length, 1, "a second fold was scheduled");
});
test("5d. reduced motion closes at once", () => {
  const b = box({ reduce: true }); b.S.govOpen = { u9: true }; const p = pillNode(true);
  clickOn(b, "u9", p);
  eq(b.S.govOpen.u9, false); eq(b.timers.length, 0); eq(b.rendered, 1);
});
test("5f. a rebuild mid-fold keeps folding, at the elapsed point, and a click on the NEW node is still ignored (review)", () => {
  const b = box(); b.S.govOpen = { u9: true }; b.NOW = 5000;
  clickOn(b, "u9", pillNode(true));
  b.NOW = 5080;                               /* a tool frame lands 80 ms into the fold */
  const h = b.turnResponse(settled({ uid: "u9" }));
  assert(/class="gv gv-pill gv-open gv-closing"/.test(h), "the rebuilt pill popped back open: " + h.slice(0, 200));
  assert(/--gv-fold-d:-80ms/.test(h), "the fold must continue from 80 ms, not restart");
  clickOn(b, "u9", pillNode(true));           /* the new node carries no class of its own */
  eq(b.timers.length, 1, "a second close was scheduled from the rebuilt node");
  b.timers[0].fn();
  eq(b.S.govOpen.u9, false); eq(b.S._pillClosing.u9, undefined, "the fold state is cleared");
  assert(!/gv-closing/.test(b.turnResponse(settled({ uid: "u9" }))), "closed after the fold");
});
test("5e. the fold time matches the css fold", () => {
  const b = box();
  const m = css.match(/\.gv-pill\.gv-closing \.gv-acc\{animation:gvFold \.(\d+)s/);
  assert(m, "gvFold rule missing");
  eq(vm.runInContext("PILL_FOLD_MS", b), +m[1] * 10, "the timer and the animation disagree");
});

/* ── 6. the stylesheet ────────────────────────────────────────────────────── */
test("6a. every keyframe the renderer names exists", () => {
  ["gvSheen", "gvFlash", "gvSettle", "gvInL", "gvInR", "gvUnfold", "gvFold", "gvDrop", "gvLift", "gvRowIn"]
    .forEach(k => assert(new RegExp("@keyframes " + k + "\\{").test(css), "missing @keyframes " + k));
});
/* the pill's css block, split into its animated rules and its reduced-motion list */
function pillCss() {
  const i = css.indexOf("/* ══ the combined pill");
  assert(i >= 0, "pill block missing");
  const j = css.indexOf("@media (prefers-reduced-motion: reduce){", i);
  const body = css.slice(i, j).replace(/\/\*[\s\S]*?\*\//g, "").replace(/@keyframes[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}/g, "");
  const rules = [];
  body.replace(/([^{}]+)\{([^{}]*)\}/g, (_, sel, decl) => { rules.push({ sels: sel.split(",").map(s => s.trim()).filter(Boolean), decl }); });
  const k = css.indexOf("{animation:none}", j);
  assert(k > j, "the reduced-motion animation rule is missing");
  const before = css.slice(j, k);
  const rmSels = before.slice(before.lastIndexOf("}") + 1).replace(/\s+/g, " ").split(",").map(s => s.trim());
  return { rules, rmSels };
}
test("6b. reduced motion names EVERY animated pill selector exactly (specificity, review)", () => {
  const { rules, rmSels } = pillCss();
  const animated = [];
  rules.forEach(r => { if (/(^|;)\s*animation:/.test(r.decl)) animated.push(...r.sels); });
  assert(animated.length >= 12, "the parse found too few animated rules: " + animated.length);
  animated.forEach(s => assert(rmSels.includes(s), "reduced motion does not name '" + s + "' exactly"));
});
test("6c. no animation hangs off .turn.arriving inside the patched block", () => {
  /* .turn.arriving stays on the turn until the next full render, while
     patchTurn replaces .a on every tool frame: any animation keyed there
     would replay on every frame. Only .u (never patched) may use it. */
  const bad = css.match(/\.turn\.arriving \.(?!u\b)[^{]*\{[^}]*animation/g);
  assert(!bad, "animation under .turn.arriving on a patched node: " + (bad || []).join(" | "));
});
test("6d. every looping pill animation reads its phase (review: all of them, not three)", () => {
  const { rules } = pillCss();
  const loops = rules.filter(r => /infinite/.test(r.decl));
  assert(loops.length >= 4, "the parse found too few loops: " + loops.length);
  loops.forEach(r => assert(/animation-delay:[^;]*var\(--gv-(sheen|spin|shim)-d/.test(r.decl),
    "a loop restarts on every rebuild: " + r.sels.join(", ")));
  assert(/\.gv-pill \.gv-tlabel\{animation-delay:var\(--gv-shim-d/.test(css), "shimmer");
  assert(/\.gv-pill \.tcard\.run \.tcdot\{animation-delay:var\(--gv-spin-d/.test(css), "the card spinner inside the pill");
  assert(/\.gv-pill \.gv-pbtn\.is-live\{transition:none\}/.test(css), "hover must not replay on a rebuilt live pill");
});
test("6e. your turn sits on the right, plain", () => {
  const r = css.match(/\.turn \.u\{([^}]*)\}/);
  assert(r && /margin-left:auto/.test(r[1]) && /border-right:2px solid var\(--line\)/.test(r[1]), "right side");
  assert(!/background/.test(r[1]), "no bubble");
});
test("6f. depth comes from tokens in both themes", () => {
  ["--pill-bg", "--pill-lift", "--pill-lift-h"].forEach(v =>
    assert(count(css, new RegExp(v.replace(/-/g, "\\-") + ":", "g")) >= 3, v + " must be set for dark, system-light and light"));
});

/* ── 7. load: a long chat stays quiet ─────────────────────────────────────── */
test("7a. 60 settled turns: zero looping and zero one-shot motion", () => {
  const b = box();
  let all = "";
  for (let i = 0; i < 60; i++) all += b.turnResponse(settled({ uid: "z" + i }));
  eq(count(all, /class="gv gv-pill/g), 60, "one pill per turn");
  eq(count(all, /is-live|gv-run|gv-flash|gv-settle|gv-in-l|gv-opening|gv-enter/g), 0);
  eq(Object.keys(b.S._pillFx || {}).length, 0, "a replayed chat must add nothing to the motion memory");
});
test("7b. one live turn among 60: exactly one loop on screen", () => {
  const b = box();
  let all = "";
  for (let i = 0; i < 59; i++) all += b.turnResponse(settled({ uid: "y" + i }));
  all += b.turnResponse(liveT({ uid: "y59" }));
  eq(count(all, /gv-pbtn is-live/g), 1); eq(count(all, /gv-pulse gv-run/g), 1);
});

(async () => {
  for (const [n, f] of queue) {
    try { await f(); console.log("ok   - " + n); pass++; }
    catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; }
  }
  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
