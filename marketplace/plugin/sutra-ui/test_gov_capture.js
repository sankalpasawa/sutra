#!/usr/bin/env node
"use strict";
/* test_gov_capture.js -- the runtime's own blocks reach the governance chip.
   Founder 2026-09-21: "I see that the work, audit, close, as well as the step
   trace and bound query, are all there. Can we also add those into the
   governance block, the top block which we have, and in detail?"
   parseGov (05-chat.js) now lifts three more families out of a reply, verbatim:
     stepTrace  the runtime's "STEP TRACE turn <id> (adherence=on)" ledger
     dispatch   the "+-- DISPATCH ---+" box (placement, class, envelope, bound atom)
     atom       the "+== ATOM OPEN / CLOSED / ABANDONED ==+" cards
   The over-capture guards of the 2026-08-23 refuter still hold: a lone field
   in prose, or a list the reply introduces, stays in the body. */
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "static", "js", "05-chat.js"), "utf8");
const grab = (n) => { const a = src.indexOf("function " + n + "("); if (a < 0) throw new Error("no " + n);
  let i = src.indexOf("{", a), d = 0; for (let j = i; j < src.length; j++) { if (src[j] === "{") d++; else if (src[j] === "}") { d--; if (!d) return src.slice(a, j + 1); } } };
const parseGov = new Function(grab("parseGov") + "; return parseGov;")();

const queue = []; const test = (n, f) => queue.push([n, f]);
const assert = (c, m) => { if (!c) throw new Error(m || "assertion failed"); };
const eq = (a, b, m) => assert(JSON.stringify(a) === JSON.stringify(b), (m || "") + " expected " + JSON.stringify(b) + " got " + JSON.stringify(a));
let pass = 0, fail = 0;
const keys = (r) => r.sections.map(s => s.key);
const sec = (r, k) => r.sections.find(s => s.key === k);

const DISPATCH = [
  "+-- DISPATCH ------------------------------------------------------+",
  "| Unit:      chat-condense: fold tool cards into one row per turn   |",
  "| PLACEMENT: INLINE   GRAIN: multi-atom                             |",
  "| CLASS:     3 -> MODEL: claude-opus-5  EFFORT: high                |",
  "| FLOOR:     governance:sutra/marketplace/plugin/                   |",
  "| TOUCHES:   05-chat.js 06-render.js 07-loaders.js panel.css        |",
  "| ATOM:      a-498d0ca8-02 (bound; envelope frozen at bind)         |",
  "+------------------------------------------------------------------+",
].join("\n");
const ATOM_OPEN = [
  "+== ATOM OPEN ========================================================+",
  "| Goal:       chat-condense: fold tool cards into one activity row   |",
  "|             per turn; the thinking button opens the same fold      |",
  "| Done when:  the text \"data-toolfold\" appears in                    |",
  "|             sutra/marketplace/plugin/sutra-ui/test_chat_condense.js |",
  "| Done by:    Claude, in this session                                |",
  "| Limits:     - envelope only: the subagent viewer is untouched      |",
  "| Ref:        a-498d0ca8-01                                          |",
  "+====================================================================+",
].join("\n");
const ATOM_CLOSED = [
  "+== ATOM CLOSED ======================================================+",
  "| Verify:     grep-count \"2.289.1\" in marketplace.json               |",
  "|             >=1 required · 48ms · exit 0                           |",
  "| Proof:      checked the text appears -- passed                     |",
  "| Recorded:   added to the work log (.sutra/atom-ledger.jsonl)       |",
  "| Ref:        a-498d0ca8-02                                          |",
  "+====================================================================+",
].join("\n");
const ATOM_ABANDONED = [
  "+== ATOM ABANDONED ===================================================+",
  "| Ref:        a-498d0ca8-01                                          |",
  "| Reason:     envelope lacked sutra/.claude-plugin/marketplace.json  |",
  "| Recorded:   added to the work log (.sutra/atom-ledger.jsonl)       |",
  "+====================================================================+",
].join("\n");
const TRACE = [
  "STEP TRACE turn 994d9ddd (adherence=on)",
  "   1 classify   runtime  done     INBOUND DIRECT now in-band low",
  "   2 resolve    runtime  done     FOLLOW:lens scope=platform",
  "   5 lens       model    pending",
  "   8 codex      model    pending  the review lane (sealed verdict)",
  "  11 close      runtime  pending  at Stop",
  "  mutations: allow=8 exempt=4",
].join("\n");
const fence = (s) => "```\n" + s + "\n```";

/* ══ 1. DISPATCH ══════════════════════════════════════════════════════════ */
test("1a. an unfenced DISPATCH box is one section, none of it in the body", () => {
  const r = parseGov("Answer first.\n\n" + DISPATCH + "\n\nThen the rest of the answer.");
  eq(keys(r), ["dispatch"]);
  eq(sec(r, "dispatch").lines.join("\n"), DISPATCH, "lossless");
  eq(sec(r, "dispatch").title, "Dispatch");
  eq(r.body, "Answer first.\n\nThen the rest of the answer.");
});
test("1b. a fenced DISPATCH box is captured whole, fence markers included", () => {
  const r = parseGov("Prose.\n" + fence(DISPATCH) + "\nMore prose.");
  eq(keys(r), ["dispatch"]);
  eq(sec(r, "dispatch").lines.join("\n"), fence(DISPATCH));
  eq(r.body, "Prose.\nMore prose.");
});

/* ══ 2. ATOM cards ════════════════════════════════════════════════════════ */
test("2a. an unfenced ATOM OPEN card is a Work atom section", () => {
  const r = parseGov(ATOM_OPEN + "\n\nShipped.");
  eq(keys(r), ["atom"]);
  eq(sec(r, "atom").title, "Work atom");
  eq(sec(r, "atom").lines.join("\n"), ATOM_OPEN);
  eq(r.body, "Shipped.");
});
test("2b. several cards in one fence come out as one Work atom section, verbatim", () => {
  const all = [ATOM_OPEN, "", ATOM_ABANDONED, "", ATOM_CLOSED].join("\n");
  const r = parseGov("The four atom cards for this turn:\n\n" + fence(all) + "\n\nOne note after.");
  eq(keys(r), ["atom"]);
  eq(sec(r, "atom").lines.join("\n"), fence(all));
  eq(r.body, "The four atom cards for this turn:\n\nOne note after.");
});
test("2c. CLOSED and ABANDONED heads are read as atom cards too", () => {
  eq(keys(parseGov(ATOM_CLOSED)), ["atom"]);
  eq(keys(parseGov(ATOM_ABANDONED)), ["atom"]);
});
test("2d. an unfenced card followed by a column-0 numbered answer keeps the answer", () => {
  const r = parseGov(ATOM_CLOSED + "\n1. First thing you asked\n2. Second thing");
  eq(keys(r), ["atom"]);
  eq(r.body, "1. First thing you asked\n2. Second thing");
});

/* ══ 3. STEP TRACE ════════════════════════════════════════════════════════ */
test("3a. an unfenced STEP TRACE with its indented rows is one section", () => {
  const r = parseGov("Header line.\n" + TRACE + "\nNow the answer.");
  eq(keys(r), ["stepTrace"]);
  eq(sec(r, "stepTrace").title, "Step trace");
  eq(sec(r, "stepTrace").lines.join("\n"), TRACE, "every indented row, including mutations:");
  eq(r.body, "Header line.\nNow the answer.");
});
test("3b. a fenced STEP TRACE is captured whole", () => {
  const r = parseGov(fence(TRACE) + "\nAnswer.");
  eq(keys(r), ["stepTrace"]);
  eq(sec(r, "stepTrace").lines.join("\n"), fence(TRACE));
  eq(r.body, "Answer.");
});

/* ══ 4. the guards still hold ═════════════════════════════════════════════ */
test("4a. a lone field in prose is prose: Goal, Unit, CLASS", () => {
  for (const t of ["Goal: ship on Friday.", "Unit: kg per crate.", "CLASS: the parameter class matters here."]) {
    const r = parseGov("Intro.\n" + t + "\nOutro.");
    eq(keys(r), [], t); eq(r.body, "Intro.\n" + t + "\nOutro.");
  }
});
test("4b. a field list the reply introduces stays in the body", () => {
  const t = "Each field means:\nGRAIN: how many atoms\nCLASS: the model ladder rung\nFLOOR: the governance floor";
  const r = parseGov(t);
  eq(keys(r), []); eq(r.body, t);
});
test("4c. a STEP TRACE mention mid-sentence is not a block", () => {
  const t = "The runtime prints a STEP TRACE after the depth block.";
  eq(keys(parseGov(t)), []);
});
test("4d. two atom fields at column 0 outside a card are still a run (the model may emit them bare)", () => {
  const r = parseGov("Goal: fold the cards\nDone when: the test passes\n\nAnswer.");
  eq(keys(r), ["atom"]); eq(r.body, "Answer.");
});

/* ══ 6. the runtime-rendered one-liners (2.286+) -- found leaking while pinning 5a ══ */
test("6a. the one-line DEPTH block is a depth section, not prose", () => {
  const t = "DEPTH: 5/5 | TASK: \"fold\" | EFFORT: 60 min | COST: ~$6 | IMPACT: every chat";
  const r = parseGov("INPUT: x\nTYPE: task | HOME: y\n" + t + "\nAnswer.");
  eq(keys(r), ["routing", "depth"]); eq(r.body, "Answer.");
});
test("6b. a prose mention of a depth stays prose", () => {
  const t = "DEPTH: 3/5 is what I would pick for this, given the risk.";
  const r = parseGov("Intro.\n" + t + "\nOutro.");
  eq(keys(r), []); eq(r.body, "Intro.\n" + t + "\nOutro.");
});
test("6c. the rendered FLOW one-liner is a flow section; a pump spec is not", () => {
  const t = "FLOW: direction / INBOUND.DIRECT | FOLLOW:lens scope=platform | steps 4 | lens what x element | cynefin complicated | close tests";
  eq(keys(parseGov(t + "\nAnswer.")), ["flow"]);
  eq(keys(parseGov("FLOW: question / INBOUND.QUERY | CONSTRUCT | steps 2\nAnswer.")), ["flow"]);
  const pump = "FLOW: 3.2 L/min at 40 psi | inlet 1/2 in";
  eq(keys(parseGov(pump)), []); eq(parseGov(pump).body, pump);
});

/* ══ 5. a whole reply, as the runtime-rendered stack emits it ═════════════ */
test("5a. the full stack lifts out in order and the body is the reply alone", () => {
  const reply = [
    "[INBOUND·DIRECT · TENSE:present · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]",
    "INPUT: fold the tool calls",
    "TYPE: direction | HOME: sutra-ui | ROUTE: build | FIT: none | ACTION: build it",
    "DEPTH: 5/5 | TASK: \"fold\" | EFFORT: 60 min | COST: ~$6 | IMPACT: every chat",
    "FLOW: direction / INBOUND.DIRECT | FOLLOW:lens scope=platform | steps 4 | lens what x element | cynefin complicated | close tests",
    "PLACEMENT: D0 Sutra > D9 Claude > D9.D9 Modules | \"Modules Charter\"",
    "",
    fence(TRACE),
    "",
    "+-- BLUEPRINT --------------------------------------------------+",
    "| Doing: fold the cards                                          |",
    "| Steps:                                                         |",
    "|   1) build   Verify: node test_chat_condense.js               |",
    "| Output looks like: one row                                     |",
    "| Verified by (overall): the runner                              |",
    "| Scale: 11 files  | Stops if: peer edits collide                |",
    "| Switch: ON                                                     |",
    "+---------------------------------------------------------------+",
    DISPATCH,
    "",
    "**Answer: neither was required as drawn.** Shipped as 2.289.1.",
    "",
    "- **\"thinking\" was a fixed label.** Gone.",
    "",
    fence([ATOM_OPEN, "", ATOM_CLOSED].join("\n")),
    "",
    "TRIAGE: depth_selected=5, depth_correct=4, class=overtriage",
    "ESTIMATE: tokens_est=120000, files_est=4, time_min_est=75, category=x",
    "",
    "OS: Input Routing (direction) > Depth 5 > 4 steps > DeepSeek > pushed",
  ].join("\n");
  const r = parseGov(reply);
  eq(keys(r), ["header", "routing", "depth", "flow", "placement", "stepTrace", "blueprint", "dispatch", "atom", "triage", "trace"]);
  eq(r.body, "**Answer: neither was required as drawn.** Shipped as 2.289.1.\n\n- **\"thinking\" was a fixed label.** Gone.");
  eq(r.g.verb, "DIRECT"); eq(r.g.depth, "5"); eq(r.g.leaf, "D9.D9 Modules");
  /* lossless: every captured line is a line of the reply, in order */
  const lines = reply.split("\n");
  for (const s of r.sections) for (const l of s.lines) assert(lines.includes(l), "captured a line that was never emitted: " + l);
});

(async () => {
  for (const [n, f] of queue) {
    try { await f(); console.log("ok   - " + n); pass++; }
    catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; }
  }
  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
