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

/* ── run ─────────────────────────────────────────────────────────────────── */
let pass = 0, fail = 0;
for (const [n, f] of queue) {
  try { f(); pass++; console.log("ok   " + n); }
  catch (e) { fail++; console.log("FAIL " + n + "\n     " + (e && e.message)); }
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
