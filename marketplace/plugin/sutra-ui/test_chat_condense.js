#!/usr/bin/env node
"use strict";
/* test_chat_condense.js -- the activity fold: one row per turn in place of a
   card per tool call (founder 2026-09-21: "the model output call is written
   one by one, like an output terminal ... can we condense that? There's also
   'thinking' written. Are both required?").

   What ships:
     - toolFoldParts / toolFoldHtml (06-render.js): a settled turn's runs fold
       behind ONE row -- count, kinds by count, failures -- that opens into the
       cards toolCallsHtml has always drawn, keyed on S.thinkOpen[uid], the
       same map the streaming loader's button toggles.
     - turnControlClick (07-loaders.js): [data-toolfold] and [data-thinkopen]
       are two doors into that one state.
     - turnResponse (05-chat.js): while streaming nothing is drawn at the top
       (the loader carries the runs); the loader's fixed word "thinking" is
       gone, the measured strip carries the shimmer; a failure mid-turn is
       stated on the loader.
   The turn-level pins live in test_panel.js section 56, which has the full
   sandbox; this file pins the fold and the click path on a lean one. */
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
const textOf = (h) => h.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

function box() {
  const b = { S: { thinkOpen: {}, toolOpen: {}, govOpen: {}, sessions: [], sideTurns: {} },
              rendered: 0, console };
  b.render = () => { b.rendered++; };
  b.globalThis = b;
  vm.createContext(b);
  vm.runInContext([
    grabConst(helpers, "esc"),
    grab(state, "fmtDur"),
    grabConst(helpers, "TOOL_KIND_BY_NAME"), grabConst(helpers, "TOOL_KINDS"),
    grabConst(helpers, "TOOL_KIND_LABEL"),
    grab(helpers, "toolKindOf"), grab(helpers, "toolKindFor"),
    grab(render, "_tcBase"), grab(render, "_tcDiff"), grab(render, "toolCardParts"),
    grab(render, "toolCardHtml"), grabConst(render, "TOOLCARD_WINDOW"),
    grab(render, "toolCallsHtml"),
    grab(render, "toolFoldParts"), grab(render, "toolFoldHtml"),
    grab(loaders, "turnControlClick"),
  ].join("\n"), b, { filename: "condense#extract" });
  return b;
}

const run = (o) => Object.assign({ id: "t1", name: "Read", running: false, ok: true,
                                   startedAt: 1000, endedAt: 2000 }, o);
/* a settled turn's runs: 5 reads, 3 shell commands, 2 edits */
function tenRuns() {
  const out = [];
  for (let i = 0; i < 5; i++) out.push(run({ id: "r" + i, name: "Read", meta: { path: "a/b" + i + ".md" } }));
  for (let i = 0; i < 3; i++) out.push(run({ id: "b" + i, name: "Bash", command: "ls " + i }));
  for (let i = 0; i < 2; i++) out.push(run({ id: "e" + i, name: "Edit", meta: { path: "x" + i + ".js" } }));
  return out;
}

/* ══ 1. the row states the facts ══════════════════════════════════════════ */

test("1a. the count and the kinds by count, most frequent first", () => {
  const b = box();
  const f = b.toolFoldParts(tenRuns(), true);
  eq(f.n, 10);
  eq(f.kinds.join(" · "), "Read 5 · Command 3 · Edited 2");
  eq(f.bad, 0); eq(f.state, "ok");
  const h = b.toolFoldHtml(tenRuns(), "t9", { live: true });
  assert(/<b class="tfn">10 tool calls<\/b/.test(h), h);
  assert(h.includes("Read 5 · Command 3 · Edited 2"), textOf(h));
});

test("1b. a failed run is counted, coloured and said", () => {
  const b = box();
  const runs = tenRuns(); runs[3].ok = false;
  const f = b.toolFoldParts(runs, true);
  eq(f.bad, 1); eq(f.state, "bad");
  const h = b.toolFoldHtml(runs, "t9", { live: true });
  assert(/class="tfhead bad"/.test(h), "the dot must go red: " + h);
  assert(/<span class="tfbad">1 failed<\/span>/.test(h), h);
});

test("1c. a run still going puts the row in the running state", () => {
  const b = box();
  const runs = tenRuns(); runs[9].running = true; runs[9].ok = null;
  eq(b.toolFoldParts(runs, true).state, "run");
  assert(/class="tfhead run"/.test(b.toolFoldHtml(runs, "t9", { live: true })));
});

test("1d. a run that never reported is unknown, not done", () => {
  const b = box();
  const runs = tenRuns(); runs[0].ok = null;
  eq(b.toolFoldParts(runs, true).state, "unk");
});

test("1e. a REPLAYED transcript counts is_error, and never invents a lifecycle", () => {
  const b = box();
  const calls = [{ name: "Read", input: "a.md" }, { name: "Bash", input: "ls", is_error: true }];
  const f = b.toolFoldParts(calls, false);
  eq(f.n, 2); eq(f.bad, 1); eq(f.state, "bad");
  eq(f.kinds.join(" · "), "Command 1 · Read 1", "ties break by name");
});

test("1f. more than four kinds are summed, not dropped silently", () => {
  const b = box();
  const calls = ["Read", "Bash", "Edit", "Grep", "WebSearch", "WebFetch"].map((n, i) =>
    run({ id: "k" + i, name: n }));
  const f = b.toolFoldParts(calls, true);
  eq(f.kinds.length, 5);
  eq(f.kinds[4], "+2 more");
});

test("1g. one call reads singular", () => {
  const b = box();
  assert(/1 tool call</.test(b.toolFoldHtml([run({})], "t9", { live: true })));
});

/* ══ 2. closed by default, opens into the cards ═══════════════════════════ */

test("2a. closed: one row, no cards, and the row says it is collapsed", () => {
  const b = box();
  const h = b.toolFoldHtml(tenRuns(), "t9", { live: true });
  assert(!/toolcall tcard/.test(h), "the cards leaked out of the fold: " + h);
  assert(/data-toolfold="t9"/.test(h) && /aria-expanded="false"/.test(h), h);
  assert(!/tfold open/.test(h));
  eq((h.match(/<button/g) || []).length, 1, "exactly one control");
});

test("2b. open: the same cards toolCallsHtml draws, with the same keys", () => {
  const b = box();
  b.S.thinkOpen.t9 = true;
  const h = b.toolFoldHtml(tenRuns(), "t9", { live: true });
  assert(/class="tfold open"/.test(h) && /aria-expanded="true"/.test(h), h);
  eq((h.match(/class="toolcall tcard/g) || []).length, 10, "one card per run");
  const plain = b.toolCallsHtml(tenRuns(), { live: true });
  assert(h.endsWith(plain + "</div>"), "the fold must wrap toolCallsHtml verbatim");
});

test("2c. open on a long fan-out keeps the cap and the 'earlier' line", () => {
  const b = box();
  b.S.thinkOpen.t9 = true;
  const many = []; for (let i = 0; i < 20; i++) many.push(run({ id: "t" + i }));
  const h = b.toolFoldHtml(many, "t9", { live: true });
  assert(/20 tool calls/.test(h));
  assert(h.includes("8 earlier tool calls"), textOf(h));
});

test("2d. a turn with no uid states the facts but is not a control", () => {
  const b = box();
  const h = b.toolFoldHtml(tenRuns(), "", { live: true });
  assert(/ disabled/.test(h), "no key to open on, so no pretend button: " + h);
  assert(/10 tool calls/.test(h));
});

test("2e. nothing ran, nothing drawn", () => {
  const b = box();
  eq(b.toolFoldHtml([], "t9", { live: true }), "");
  eq(b.toolFoldHtml(null, "t9"), "");
});

test("2f. a hostile tool name cannot open a tag in the row", () => {
  const b = box();
  const h = b.toolFoldHtml([run({ name: '<img src=x onerror=1>' })], "t9", { live: true });
  assert(!/<img/.test(h), "unescaped markup in the fold: " + h);
});

/* ══ 3. two doors, one state ══════════════════════════════════════════════ */

const evFor = hits => ({ target: { closest: sel => hits[sel] || null } });
const IN_TURN = { ".turn": {} };

test("3a. the fold's head toggles S.thinkOpen -- the loader's own map", () => {
  const b = box();
  const btn = { dataset: { toolfold: "t9" } };
  b.turnControlClick(evFor({ ...IN_TURN, "[data-toolfold]": btn }));
  eq(b.S.thinkOpen.t9, true, "first click opens");
  b.turnControlClick(evFor({ ...IN_TURN, "[data-toolfold]": btn }));
  eq(b.S.thinkOpen.t9, undefined, "second click closes");
  eq(b.rendered, 2, "each click repaints once");
});

test("3b. the loader's button still opens the same state", () => {
  const b = box();
  b.turnControlClick(evFor({ ...IN_TURN, "[data-thinkopen]": { dataset: { thinkopen: "t9" } } }));
  eq(b.S.thinkOpen.t9, true);
});

test("3c. a fold with no uid never flips anything", () => {
  const b = box();
  b.turnControlClick(evFor({ ...IN_TURN, "[data-toolfold]": { dataset: { toolfold: "" } } }));
  eq(Object.keys(b.S.thinkOpen).length, 0);
  eq(b.rendered, 0);
});

test("3d. outside a turn the click is not intercepted", () => {
  const b = box();
  b.turnControlClick(evFor({ "[data-toolfold]": { dataset: { toolfold: "t9" } } }));
  eq(Object.keys(b.S.thinkOpen).length, 0);
});

/* ══ 4. the turn renderer and the stylesheet carry it ═════════════════════ */

/* 2026-09-23: the fold row and the loader became ONE combined pill
   (gvPillHtml, pinned in test_chat_pill.js). The condense promises hold on it:
   one row per turn, no cards until opened, the measured strip, failures said. */
test("4a. turnResponse draws one pill at the top, never a card list or a fold row", () => {
  const src = grab(chat, "turnResponse");
  assert(/gvPillParts\(t\)/.test(src) && /gvPillHtml\(t, p, m\)/.test(src), "the pill is the top of the block");
  assert(!/toolFoldHtml\(|toolCallsHtml\(/.test(src), "no tool list at the top of a turn");
  const pill = grab(chat, "gvPillHtml");
  assert(/\(open \?/.test(pill) && /gvRuntimeHtml\(t, p, opening\)/.test(pill), "cards only when the pill is open");
});

test("4b. the loader has no fixed word beside the measured strip", () => {
  const src = grab(chat, "gvPillHtml");
  assert(!/gv-tlabel">thinking</.test(src), "the static 'thinking' label is back");
  assert(/class="gv-tlabel" data-runstrip=/.test(src), "the strip carries the shimmer");
  assert(/gv-pfail">\$\{p\.failed\} failed/.test(src), "a failure mid-turn is stated on the pill");
});

test("4c. the stylesheet styles the fold in the card palette", () => {
  ["tfhead", "tfhead.ok  .tfdot", "tfhead.bad .tfdot", "tfhead.run .tfdot", "tfold.open .tfchev",
   "gv-tbad"].forEach(sel => assert(css.includes(sel), "panel.css lacks ." + sel));
});

test("4d. a transcript turn gets its uid before the fold is drawn", () => {
  const src = grab(chat, "turnBlock");
  const at = src.indexOf("turnUid(t);");
  assert(at > 0 && at < src.indexOf("turnResponse(t)"), "turnUid(t) must precede turnResponse(t)");
});

(async () => {
  for (const [n, f] of queue) {
    try { await f(); console.log("ok   - " + n); pass++; }
    catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; }
  }
  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
