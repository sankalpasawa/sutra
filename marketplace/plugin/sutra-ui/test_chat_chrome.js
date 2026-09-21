#!/usr/bin/env node
/* Chat chrome, founder 2026-09-21 -- three complaints about the Mac app's chat
   screen, pinned against the SHIPPED functions:

     1. "when I go up, suddenly they go down"  -- the reader's scroll-up during a
        streaming reply was dropped because the scroll listener trusted the pin
        flag, and the flag was still up when the browser dispatched the event.
     2. "those green dots keep coming and going" -- the live mark followed a 45 s
        file-write window and blinked through every long tool call.
     3. "Claude Code, this chat only ... the full access thing ... put that into
        the three dots" -- the provider name, the chat-local note and the access
        chip leave the composer and the chat list; the ⋯ menu carries them.

   Run: node test_chat_chrome.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const J = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const helpers = J("02-helpers.js");
const chat = J("05-chat.js");
const render = J("06-render.js");
const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8");

const queue = [];
const test = (n, f) => queue.push([n, f]);
const assert = (c, m) => { if (!c) throw new Error(m || "assertion failed"); };
const eq = (a, b, m) => assert(a === b, (m || "") + " expected " + JSON.stringify(b)
                                        + " got " + JSON.stringify(a));

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

/* ── 1. the reader's scroll-up wins over the stream ─────────────────────── */

/* A scroller the way the listener sees it: scrollTop, sizes, and the handlers
   it registered. dispatch() runs them the way the browser would. */
function fakeScroller(top, height, client) {
  const on = {};
  return {
    scrollTop: top, scrollHeight: height, clientHeight: client,
    addEventListener(type, fn) { (on[type] = on[type] || []).push(fn); },
    querySelector() { return null; },
    dispatch(type, ev) { (on[type] || []).forEach(fn => fn(ev || {})); },
    handlers: on,
  };
}

function scrollBox(pb) {
  const pane = { dataset: { sess: "s1" }, querySelector: (sel) => sel === ".pb" ? pb : null };
  const box = {
    S: { openPanes: ["s1"], userScrolled: new Map(), sessions: [], sideTurns: {} },
    document: { querySelectorAll: () => [pane], querySelector: () => null },
    requestAnimationFrame: (fn) => fn(),
    setInterval: () => 1, clearInterval: () => {},
    console,
  };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grabConst(render, "_pinTimers"),
    grab(render, "_sessionIsStreaming"),
    grabConst(render, "SESS_UP_KEYS"),
    grab(render, "_sessUserIntent"),
    grab(render, "scrollNewSessionsToNewest"),
    ";scrollNewSessionsToNewest();",
  ].join("\n"), { filename: "scroll#extract" }).runInContext(box);
  return box;
}

test("1a. a wheel-up parks the pane at the gesture, before any scroll event", () => {
  const pb = fakeScroller(1000, 1400, 400);      /* at the bottom, following */
  const box = scrollBox(pb);
  assert(!box.S.userScrolled.get("s1"), "parked before anyone touched it");
  pb.dispatch("wheel", { deltaY: -40 });
  eq(box.S.userScrolled.get("s1"), true, "the wheel-up did not park the pane:");
});

test("1b. a wheel-down is not a park (it is where the tail already goes)", () => {
  const pb = fakeScroller(1000, 1400, 400);
  const box = scrollBox(pb);
  pb.dispatch("wheel", { deltaY: 40 });
  assert(!box.S.userScrolled.get("s1"), "scrolling toward the tail parked the pane");
});

test("1c. PageUp / ArrowUp / Home park; other keys do not", () => {
  const pb = fakeScroller(1000, 1400, 400);
  const box = scrollBox(pb);
  pb.dispatch("keydown", { key: "ArrowDown" });
  assert(!box.S.userScrolled.get("s1"), "ArrowDown parked the pane");
  pb.dispatch("keydown", { key: "PageUp" });
  eq(box.S.userScrolled.get("s1"), true, "PageUp did not park the pane:");
});

test("1d. THE BUG: a scroll that moved UP counts even while the pin flag is up", () => {
  const pb = fakeScroller(1000, 1400, 400);
  const box = scrollBox(pb);
  pb.__pinning = true;                            /* patchStreaming just pinned */
  pb.scrollTop = 700;                             /* ...and the reader dragged up */
  pb.dispatch("scroll");
  eq(box.S.userScrolled.get("s1"), true,
     "the reader's scroll-up was dropped because our pin flag was still up:");
});

test("1e. our own pin (scrollTop grows) under the flag is still not intent", () => {
  const pb = fakeScroller(1000, 1400, 400);
  const box = scrollBox(pb);
  pb.__pinning = true;
  pb.scrollHeight = 1600; pb.scrollTop = 1200;   /* the tail grew, we followed */
  pb.dispatch("scroll");
  assert(!box.S.userScrolled.get("s1"), "following the tail read as a manual scroll");
});

test("1f. landing back at the bottom un-parks, so following resumes by itself", () => {
  const pb = fakeScroller(1000, 1400, 400);
  const box = scrollBox(pb);
  pb.dispatch("wheel", { deltaY: -40 });
  eq(box.S.userScrolled.get("s1"), true);
  pb.scrollTop = 1000; pb.dispatch("scroll");    /* back at the tail */
  assert(!box.S.userScrolled.get("s1"), "at the bottom and still parked");
});

/* ── 2. the live mark holds through a quiet stretch ─────────────────────── */

function liveBox() {
  const box = { console };
  box.globalThis = box;
  vm.createContext(box);
  new vm.Script([
    grabConst(helpers, "LIVE_HOLD_MS"),
    grabConst(helpers, "_liveSeen"),
    grab(helpers, "liveHeld"),
    ";globalThis.__L={liveHeld,LIVE_HOLD_MS};",
  ].join("\n"), { filename: "live#extract" }).runInContext(box);
  return box.__L;
}

test("2a. active is live; idle within the hold is STILL live; after the hold it is not", () => {
  const L = liveBox();
  const t0 = 1_000_000_000;
  eq(L.liveHeld({ id: "a", live: "active" }, t0), true, "active must be live:");
  eq(L.liveHeld({ id: "a", live: "idle" }, t0 + 60_000), true,
     "a 60 s quiet stretch (a long tool call) dropped the mark:");
  eq(L.liveHeld({ id: "a", live: "idle" }, t0 + L.LIVE_HOLD_MS - 1), true, "held to the edge:");
  eq(L.liveHeld({ id: "a", live: "idle" }, t0 + L.LIVE_HOLD_MS + 1), false,
     "a chat that really stopped stays lit forever:");
});

test("2b. a row never seen active is not live, and a vanished one drops at once", () => {
  const L = liveBox();
  eq(L.liveHeld({ id: "b", live: "idle" }, 5), false, "never active, yet live:");
  eq(L.liveHeld({ id: "c", live: "active" }, 5), true);
  eq(L.liveHeld({ id: "c", live: "idle", vanished: true }, 6), false, "deleted on disk, still live:");
});

test("2c. the rail dot is steady: its rule carries no animation (Shadow's dots keep theirs)", () => {
  const rule = /\.livedot::before\{([^}]*)\}/.exec(css);
  assert(rule, "no rule for the live dot");
  assert(!/animation/.test(rule[1]), "the live dot still blinks: " + rule[1]);
  assert(/box-shadow/.test(rule[1]), "the steady dot lost its halo");
  assert(/@keyframes livepulse/.test(css), "Shadow's breathing dots lost their keyframes");
});

test("2d. rowMeta reads the held mark, not the raw 45 s window", () => {
  const src = grab(helpers, "rowMeta");
  assert(src.includes("liveHeld(s)"), "rowMeta still reads s.live directly");
  assert(!src.includes('s.live === "active"'), "rowMeta still reads s.live directly");
});

/* ── 3. the chrome that moved into the ⋯ menu ──────────────────────────── */

test("3a. the composer carries no access row and no provider name", () => {
  assert(!/class="accrow"/.test(render), "the access row is still under the box");
  assert(!/composerAccessHtml\(/.test(render), "the chip renderer is still called");
  assert(!/class="provnow/.test(grab(chat, "providerSwitcherHtml")),
         "the composer row still prints the provider name");
  assert(!/this chat only/.test(grab(chat, "providerSwitcherHtml")),
         "the composer row still prints the chat-local note");
});

test("3b. the ⋯ menu has the Access row and the provider facts", () => {
  const menu = grab(render, "paneMenuHtml");
  assert(/paneAccessRowHtml\(s\)/.test(menu), "no Access row in the pane menu");
  assert(/providerFactsFor/.test(menu), "the Model row does not carry the provider facts");
  const row = grab(render, "paneAccessRowHtml");
  assert(/data-accmenu=/.test(row), "the Access row does not open the access list");
  assert(/this chat only/.test(row), "a chat-local access no longer says so");
});

test("3c. the chat list row carries no provider tag; the row menu names the writer", () => {
  assert(!/class="provtag/.test(grab(helpers, "rowMeta")), "rowMeta still tags rows");
  assert(/data-smsource/.test(grab(helpers, "sessMenuHtml")), "the row menu never says who wrote it");
});

/* ── 4. the six micro-interactions (founder 2026-09-21 "Do these changes.";
   design of record: website/preview/chat-micro-interactions.html) ────────── */

const state = J("01-state.js");
const loaders = J("07-loaders.js");

test("4a. the css carries all six, and reduced motion switches every one of them off", () => {
  ["\\.jumpwrap\\{position:sticky", "\\.jumppill\\.show\\{opacity:1", "@keyframes riseIn", "\\.turn\\.arriving\\{animation:riseIn 120ms",
   "\\.livedot\\.breathe::before\\{animation:breathe 4s", "@keyframes menuIn", "\\.upop\\.panemenu\\.fresh\\{", "\\.mrow\\{transition:background 60ms",
   "\\.accn\\.flash\\{animation:flashtint 600ms", "\\.pc textarea\\[data-sask\\]\\{transition:height 100ms", "\\.send:active\\{transform:scale\\(\\.94\\)",
   "\\.send\\.stop\\.fresh\\{animation:fadeIn 120ms", "\\.pane\\.fresh\\{animation:fadeIn 150ms"]
    .forEach(re => assert(new RegExp(re).test(css), "missing rule: " + re));
  const block = css.slice(css.indexOf(".jumpwrap{position:sticky"));
  const reduced = block.indexOf("@media (prefers-reduced-motion:reduce){\n    .jumppill{transition:none}");
  assert(reduced >= 0, "no reduced-motion block for the six");
  const rm = block.slice(reduced, reduced + 400);
  assert(rm.includes(".turn.arriving,.livedot.breathe::before,.upop.panemenu.fresh,.accn.flash,.send.stop.fresh,.pane.fresh{animation:none}"),
         "reduced motion does not switch the animations off");
  assert(rm.includes(".mrow,.pc textarea[data-sask],.send{transition:none}"), "reduced motion does not switch the transitions off");
  assert(/\.caret\{display:inline-block;width:2px;height:12px;font-size:0/.test(css), "the caret is not a soft bar");
  assert(/\.caret\.blink\{animation:caretsoft 1s ease-in-out infinite\}/.test(css), "the stalled caret still hard-blinks");
});

test("4b. the pane draws the pill at the end of its transcript and flags its mounts once", () => {
  const pane = grab(render, "sessionPane");
  assert(/<div class="jumpwrap"><button class="jumppill/.test(pane), "no pill at the end of .pb");
  assert(/data-jump="\$\{esc\(s\.id\)\}"/.test(pane), "the pill does not name its pane");
  assert(/const paneFresh = !\(S\._prevOpenPanes \|\| \[\]\)\.includes\(s\.id\)/.test(pane), "a pane is not flagged fresh against the previous render");
  assert(/const stopFresh = streamingFor\(s\.id\) && !stopShown\[s\.id\]/.test(pane), "Stop is not flagged fresh once per stream");
  assert(/class="send stop\$\{stopFresh\?" fresh":""\}"/.test(pane), "the Stop button does not carry the flag");
  const tail = grab(render, "render");
  assert(/S\.paneMenuFresh = null;\s*S\.accFlash = null;\s*S\._prevOpenPanes = \(S\.openPanes \|\| \[\]\)\.slice\(\);/.test(tail),
         "render() does not spend the one-render flags at its end");
  assert(/class="upop panemenu\$\{S\.paneMenuFresh===s\.id\?" fresh":""\}"/.test(grab(render, "paneMenuHtml")), "the menu does not grow in on open");
  assert(/class="accn\$\{S\.accFlash===s\.id\?" flash":""\}"/.test(grab(render, "paneAccessRowHtml")), "the changed Access value does not flash");
  assert(/S\.accFlash = sid;/.test(grab(render, "setSessAccess")), "setSessAccess does not arm the flash");
  assert(/S\.paneMenuFresh = opening \? sid : null;/.test(loaders), "the chip toggle does not arm the menu animation");
});

test("4c. the rail dot breathes with a wall-clock phase, so a rebuild never restarts it", () => {
  const src = grab(helpers, "rowMeta");
  assert(/breathe" style="animation-delay:-\$\{Date\.now\(\) % 4000\}ms/.test(src), "no wall-clock phase on the breath");
  assert(/livedot\$\{breath\}/.test(src), "the live badges do not carry the breath");
});

test("4d. a new streaming turn eases in once per uid", () => {
  assert(/const arriving = !!\(t\.streaming && t\.uid && !arrived\[t\.uid\]\);\s*if \(arriving\) arrived\[t\.uid\] = 1;/.test(chat),
         "the arrival class is not gated on the first draw");
  assert(/class="turn\$\{arriving \? " arriving" : ""\}"/.test(chat), "the turn does not carry the class");
});

test("4e. the composer tweens from its previous height, and lands at once the first time", () => {
  const box = { COMPOSER_MAX_PX: 200, console };
  box.globalThis = box; vm.createContext(box);
  new vm.Script(grab(render, "autoGrowComposer") + ";globalThis.__g=autoGrowComposer;", { filename: "grow#extract" }).runInContext(box);
  function ta(prev, scrollHeight){
    const writes = []; const style = {};
    Object.defineProperty(style, "height", { get(){ return writes[writes.length-1] === undefined ? prev : writes[writes.length-1]; }, set(v){ writes.push(v); } });
    return { tagName: "TEXTAREA", style, scrollHeight, offsetHeight: 0, writes };
  }
  const grown = ta("22px", 60);
  box.__g(grown);
  assert(grown.writes.join(">") === "auto>22px>60px", "no tween start value: " + grown.writes.join(">"));
  const first = ta("", 60);
  box.__g(first);
  assert(first.writes.join(">") === "auto>60px", "the first sizing should land at once: " + first.writes.join(">"));
});

test("4f. patching under a parked reader shows the pill; the tail pin does not", () => {
  assert(/\} else showJumpPill\(pb\);\s*\/\* parked/.test(state), "patchStreaming does not show the pill when parked");
  assert(/\} else showJumpPill\(pb\);\s*return true;/.test(state), "patchTurn does not show the pill when parked");
  assert(/function showJumpPill\(pb\)/.test(state), "no showJumpPill");
  assert(/\(S\.jumpNew = S\.jumpNew \|\| \{\}\)\[sid\] = true/.test(state), "the pill is not remembered in state across a rebuild");
  assert(/S\.userScrolled\.get\(s\.id\) && \(S\.jumpNew \|\| \{\}\)\[s\.id\] \? " show" : ""/.test(grab(render, "sessionPane")),
         "a full render does not redraw the pill from state");
  assert(/if \(S\.jumpNew\) delete S\.jumpNew\[sid\];/.test(loaders), "the pill click does not clear the state");
  assert(/\.caret\{[^}]*animation:none\}/.test(css), "the older unconditional caret blink still applies to the bar");
  assert(/\.jumpwrap\{[^}]*align-items:flex-end/.test(css), "a 0-height flex row would stretch the pill to nothing");
});

test("4g. back at the tail, the scroll listener hides the pill", () => {
  const pb = fakeScroller(700, 1400, 400);
  const pill = { cls: new Set(["jumppill", "show"]) };
  pill.classList = { add: c => pill.cls.add(c), remove: c => pill.cls.delete(c) };
  pb.querySelector = (sel) => sel === ".jumppill" ? pill : null;
  const box = scrollBox(pb);
  box.S.userScrolled.set("s1", true);
  pb.scrollTop = 1000; pb.dispatch("scroll");
  assert(!box.S.userScrolled.get("s1"), "not un-parked at the tail");
  assert(!pill.cls.has("show"), "the pill is still shown at the tail");
});

test("4h. a reopened pane comes back where the reader was; a pinned one follows the tail", () => {
  const pb = fakeScroller(0, 1400, 400);
  const box = scrollBox(pb);
  box.S.paneScrollMem = { s1: { top: 300, pinned: false } };
  box.scrollNewSessionsToNewest();
  assert(pb.scrollTop === 300, "the parked place was not restored: " + pb.scrollTop);
  assert(box.S.userScrolled.get("s1") === true, "a restored parked pane must stay parked");
  assert(!box.S.paneScrollMem.s1, "the memory was not spent");
  const pb2 = fakeScroller(0, 1400, 400);
  const box2 = scrollBox(pb2);
  box2.S.paneScrollMem = { s1: { top: 990, pinned: true } };
  box2.scrollNewSessionsToNewest();
  assert(!box2.S.userScrolled.get("s1"), "a pinned place must not park the pane");
  assert(/data-jump/.test(loaders) && /S\.userScrolled\.delete\(sid\);\s*if \(S\.jumpNew\) delete S\.jumpNew\[sid\];\s*b\.classList\.remove\("show"\);/.test(loaders),
         "the pill click does not un-park, clear the state and hide");
  assert(/S\.paneScrollMem = S\.paneScrollMem \|\| \{\}\)\[sid\] = \{/.test(loaders), "closePane does not remember the place");
});

/* ── run ─────────────────────────────────────────────────────────────────── */
let pass = 0, fail = 0;
for (const [n, f] of queue) {
  try { f(); pass++; console.log("ok   " + n); }
  catch (e) { fail++; console.log("FAIL " + n + "\n     " + (e && e.message)); }
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
