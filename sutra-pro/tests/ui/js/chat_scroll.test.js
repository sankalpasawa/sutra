"use strict";
// ChatScroll (sutra_app/ui/static/js/chat_scroll.js): a reader who scrolls up is never pulled down, a pill counts what arrived below, the owner's own
// send goes to the bottom and a reopened chat comes back where it was read (GAP-chat-comfort). Blocks 1a-1f re-express the old app's
// test_chat_chrome.js (founder: "when I go up, suddenly they go down"). Run with: node --test tests/ui/js/chat_scroll.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatScroll = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_scroll.js"));
const {idle, intent, plan, settle, lastId, newCount, pillHtml, distance, watch, behavior, remember, restore, SLOP} = ChatScroll;

// A transcript element: content of `height` px in a view of `view` px, scrolled to `top`, with listeners that a test can fire.
function scroller(top, height, view) {
  const listeners = {};
  return {
    scrollTop: top, scrollHeight: height, clientHeight: view, listeners,
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    removeEventListener(type, fn) { listeners[type] = (listeners[type] || []).filter(f => f !== fn); },
    dispatch(type, e) { (listeners[type] || []).forEach(fn => fn(e || {})); },
  };
}
function follow(el) {
  let s = idle();
  const stop = watch(el, ev => { s = intent(s, Object.assign(ev, {lastId: 9})); });
  return {get: () => s, stop};
}
const msgs = ids => ids.map(id => ({id, kind: "text", text: "line " + id}));

test("1a. a wheel-up parks the reader at the gesture, before any scroll event", () => {
  const pb = scroller(1000, 1400, 400);               // at the bottom, following
  const r = follow(pb);
  assert.equal(r.get().parked, false);
  pb.dispatch("wheel", {deltaY: -40});
  assert.equal(r.get().parked, true);
});

test("1b. a wheel-down is not a park (it is where the newest line already is)", () => {
  const pb = scroller(1000, 1400, 400);
  const r = follow(pb);
  pb.dispatch("wheel", {deltaY: 40});
  assert.equal(r.get().parked, false);
});

test("1c. PageUp, ArrowUp, Home and a finger on the transcript park; other keys do not", () => {
  for (const key of ["PageUp", "ArrowUp", "Home"]) {
    const pb = scroller(1000, 1400, 400);
    const r = follow(pb);
    pb.dispatch("keydown", {key: "ArrowDown"});
    pb.dispatch("keydown", {key: "End"});
    assert.equal(r.get().parked, false, "ArrowDown or End parked");
    pb.dispatch("keydown", {key});
    assert.equal(r.get().parked, true, key + " did not park");
  }
  const touch = scroller(1000, 1400, 400);
  const r = follow(touch);
  touch.dispatch("touchmove");
  assert.equal(r.get().parked, true);
});

test("1d. a scroll that moved up is the reader's, whatever caused it", () => {
  const pb = scroller(1000, 1400, 400);
  const r = follow(pb);
  pb.scrollTop = 700;
  pb.dispatch("scroll");
  assert.equal(r.get().parked, true);
});

test("1e. following the newest line (scrollTop grows) is not the reader's intent", () => {
  const pb = scroller(1000, 1400, 400);
  const r = follow(pb);
  pb.scrollHeight = 1600; pb.scrollTop = 1200;
  pb.dispatch("scroll");
  assert.equal(r.get().parked, false);
});

test("1f. coming back within 24 px of the bottom follows again, the pill goes and everything counts as seen", () => {
  const pb = scroller(1000, 1400, 400);
  const r = follow(pb);
  pb.dispatch("wheel", {deltaY: -40});
  assert.equal(r.get().parked, true);
  pb.scrollTop = 1000 - SLOP; pb.dispatch("scroll");
  assert.deepEqual(r.get(), {parked: false, seenId: 9, pill: 0});
  r.stop();
  pb.dispatch("wheel", {deltaY: -40});
  assert.equal(r.get().parked, false, "a stopped watch still listened");
});

test("a repaint: the owner's own send goes to the bottom, a parked reader keeps the place and sees the count, a follower follows", () => {
  assert.deepEqual(plan({parked: true, atBottom: false, grew: true, newCount: 3, own: true}), {scroll: "bottom", pill: 0});
  assert.deepEqual(plan({parked: true, atBottom: false, grew: true, newCount: 2}), {scroll: "keep", pill: 2});
  assert.deepEqual(plan({parked: false, atBottom: false, grew: true, newCount: 1}), {scroll: "keep", pill: 1});       // reading, though no gesture was seen
  assert.deepEqual(plan({parked: false, atBottom: true, grew: true, newCount: 1}), {scroll: "bottom", pill: 0});
  assert.deepEqual(plan({parked: true, grew: false, newCount: 5, pill: 2}), {scroll: "keep", pill: 2});            // nothing changed: nothing moves
  assert.deepEqual(plan({}), {scroll: "keep", pill: 0});
});

test("the count is the messages above the last one seen; a local unsent line has no number and is not counted", () => {
  const list = msgs([3, 4, 5, 6]).concat([{id: "local-1", role: "user"}, null, {id: NaN}]);
  assert.equal(lastId(list), 6);
  assert.equal(newCount(list, 4), 2);
  assert.equal(newCount(list, 6), 0);
  assert.equal(newCount(null, 0), 0);
  let s = settle({parked: true, seenId: 4, pill: 0}, {scroll: "keep", pill: 2}, 300, 6);
  assert.deepEqual(s, {parked: true, seenId: 4, pill: 2});
  s = settle(s, {scroll: "keep", pill: 2}, 10, 6);                  // the new lines fit in view: they are seen
  assert.deepEqual(s, {parked: false, seenId: 6, pill: 0});
  assert.deepEqual(settle({parked: false, seenId: 1}, {scroll: "bottom"}, 0, 8), {parked: false, seenId: 8, pill: 0});
});

test("the pill says how many in words and carries only digits and fixed words", () => {
  assert.equal(pillHtml(0), "");
  assert.equal(pillHtml(-3), "");
  assert.equal(pillHtml("<b>"), "");
  assert.match(pillHtml(1), /^<button type="button" class="cjump-btn" data-act="jump-latest" aria-label="1 new message below, go to the newest">1 new message below<\/button>$/);
  assert.match(pillHtml(2), />2 new messages below</);
  assert.match(pillHtml(12.7), />12 new messages below</);
});

test("the jump is smooth, and instant under reduced motion or when it cannot be asked", () => {
  assert.equal(behavior(q => ({matches: q === "(prefers-reduced-motion: reduce)"})), "auto");
  assert.equal(behavior(() => ({matches: false})), "smooth");
  assert.equal(behavior(undefined), "smooth");
  assert.equal(behavior(() => { throw new Error("no"); }), "auto");
});

test("a chat closed above its bottom reopens there, clamped to the new height; one closed at the bottom opens at the bottom", () => {
  const mem = new Map();
  remember(mem, "cs_a", {top: 900, scrollHeight: 2000, clientHeight: 400, seenId: 7});
  assert.deepEqual(restore(mem, "cs_a", {scrollHeight: 1000, clientHeight: 400}), {top: 600, parked: true, seenId: 7});
  assert.equal(restore(mem, "cs_a", {scrollHeight: 1000, clientHeight: 400}), null);          // a place is used once
  remember(mem, "cs_b", {top: 1590, scrollHeight: 2000, clientHeight: 400});
  assert.equal(restore(mem, "cs_b", {scrollHeight: 2000, clientHeight: 400}), null);
  assert.equal(restore(mem, "cs_none", {}), null);
  for (let i = 0; i < 80; i += 1) remember(mem, "cs_" + i, {top: 1, scrollHeight: 900, clientHeight: 100});
  assert.equal(mem.size, ChatScroll.MAX_REMEMBERED);
  assert.equal(mem.has("cs_0"), false);
  assert.equal(remember(null, "cs_a", {}), null);
  assert.equal(remember(mem, "", {}), null);
});

test("pin keeps a follower at the bottom when the transcript's box changes size, and leaves a reader alone", () => {
  const observers = [];
  globalThis.ResizeObserver = class { constructor(fn) { this.fn = fn; this.on = false; observers.push(this); } observe() { this.on = true; } disconnect() { this.on = false; } };
  try {
    const el = scroller(100, 1400, 400);
    let following = true;
    const stop = ChatScroll.pin(el, () => following);
    observers[0].fn();
    assert.equal(el.scrollTop, 1400);
    el.scrollTop = 100; following = false;
    observers[0].fn();
    assert.equal(el.scrollTop, 100);
    stop();
    assert.equal(observers[0].on, false);
  } finally {
    delete globalThis.ResizeObserver;
  }
  assert.equal(typeof ChatScroll.pin(scroller(0, 10, 10), () => true), "function");       // no ResizeObserver: a no-op
});

test("distance is what is left below the view; watch on nothing is a no-op", () => {
  assert.equal(distance(scroller(600, 1400, 400)), 400);
  assert.equal(distance(scroller(1000, 1400, 400)), 0);
  assert.equal(distance(null), 0);
  assert.equal(typeof watch(null, () => {}), "function");
  assert.deepEqual(intent(undefined, {type: "other"}), idle());
});
