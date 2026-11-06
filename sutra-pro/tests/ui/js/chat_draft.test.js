"use strict";
// ChatDraft (sutra_app/ui/static/js/chat_draft.js): one draft per chat that survives Esc, a closed panel, a tab switch and a reload, cleared only by an
// accepted send; and the box that grows with its text (GAP-chat-comfort). Run with: node --test tests/ui/js/chat_draft.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatDraft = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_draft.js"));
const {create, grow, PREFIX, MAX_CHARS, MAX_CHATS} = ChatDraft;

const DAY = 24 * 60 * 60 * 1000;
const A = "cs_000000000aaa";
const B = "cs_000000000bbb";

function memory() {
  const map = new Map();
  return {
    map,
    get length() { return map.size; },
    key: i => Array.from(map.keys())[i] === undefined ? null : Array.from(map.keys())[i],
    getItem: k => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, String(v)); },
    removeItem: k => { map.delete(k); },
  };
}
const rig = start => {
  const storage = memory();
  const clock = {t: start === undefined ? 1_000_000 : start};
  return {storage, clock, d: create({storage, now: () => clock.t})};
};

test("a draft is kept per chat and comes back exactly as it was left; another chat's box is its own", () => {
  const {d, storage, clock} = rig();
  assert.equal(d.load(A), "");
  assert.equal(d.save(A, "Dear team,\n  the menu needs  prices "), true);
  d.save(B, "something else");
  assert.equal(d.load(A), "Dear team,\n  the menu needs  prices ");
  assert.equal(d.load(B), "something else");
  assert.deepEqual(Array.from(storage.map.keys()).sort(), [PREFIX + A, PREFIX + B]);
  const again = create({storage, now: () => clock.t + DAY});  // a reload the next day: a new store over the same storage
  assert.equal(again.load(A), "Dear team,\n  the menu needs  prices ");
});

test("an empty or blank draft is never written, and writing one removes the old draft", () => {
  const {d, storage} = rig();
  d.save(A, "   \n ");
  assert.equal(storage.map.size, 0);
  d.save(A, "hello");
  d.save(A, "");
  assert.equal(storage.map.size, 0);
  assert.equal(d.load(A), "");
});

test("clearIf forgets the draft only when it is what was sent; a box the owner kept typing in keeps its newer words", () => {
  const {d} = rig();
  d.save(A, "  ship it  ");
  assert.equal(d.clearIf(A, "ship it"), true);
  assert.equal(d.load(A), "");
  d.save(A, "ship it, and the menu too");
  assert.equal(d.clearIf(A, "ship it"), false);
  assert.equal(d.load(A), "ship it, and the menu too");
  assert.equal(d.clear(A), true);
  assert.equal(d.load(A), "");
});

test("a draft over the cap keeps its first 8000 characters", () => {
  const {d, storage} = rig();
  d.save(A, "x".repeat(MAX_CHARS + 500));
  assert.equal(d.load(A).length, MAX_CHARS);
  assert.ok(storage.getItem(PREFIX + A).length < MAX_CHARS + 100);
});

test("a draft older than 14 days is dropped when read and by prune; at most 30 chats are kept, the newest", () => {
  const {d, storage, clock} = rig();
  d.save(A, "old words");
  clock.t += 15 * DAY;
  assert.equal(d.load(A), "");
  assert.equal(storage.getItem(PREFIX + A), null);
  for (let i = 0; i < MAX_CHATS + 5; i += 1) { clock.t += 1000; d.save("cs_" + String(i).padStart(12, "0"), "draft " + i); }
  assert.equal(Array.from(storage.map.keys()).filter(k => k.startsWith(PREFIX)).length, MAX_CHATS);
  assert.equal(d.load("cs_000000000000"), "");                // the oldest went
  assert.equal(d.load("cs_" + String(MAX_CHATS + 4).padStart(12, "0")), "draft " + (MAX_CHATS + 4));
  storage.setItem("j2theme", "dark");                         // another key of the page is never touched
  d.prune();
  assert.equal(storage.getItem("j2theme"), "dark");
});

test("a storage that throws, or none at all, loses the draft quietly and never throws to the page", () => {
  const boom = () => { throw new Error("SecurityError"); };
  const broken = {length: 1, key: boom, getItem: boom, setItem: boom, removeItem: boom};
  for (const storage of [broken, () => { throw new Error("blocked"); }, null]) {
    const d = create({storage});
    assert.equal(d.save(A, "hello"), false);
    assert.equal(d.load(A), "");
    assert.equal(d.clear(A), false);
    assert.equal(d.clearIf(A, "hello"), false);
    assert.equal(d.prune(), 0);
  }
  const full = memory();
  full.setItem = () => { throw new Error("QuotaExceededError"); };
  assert.equal(create({storage: full}).save(A, "hello"), false);
});

test("a stored value that is not a draft is dropped, and a hostile chat id reaches no key", () => {
  const {d, storage} = rig();
  storage.setItem(PREFIX + A, "{not json");
  assert.equal(d.load(A), "");
  assert.equal(storage.getItem(PREFIX + A), null);
  storage.setItem(PREFIX + A, JSON.stringify({t: 5, at: "x"}));
  assert.equal(d.load(A), "");
  for (const sid of ["", "../j2theme", "a b", "cs_" + "x".repeat(80), null, 42, {}, "j2theme\u0000"]) {
    assert.equal(d.save(sid, "x"), false);
    assert.equal(d.load(sid), "");
    assert.equal(d.clear(sid), false);
  }
  assert.equal(storage.map.size, 0);
});

test("a draft is only text: whatever is saved is a string, and a non-string is nothing", () => {
  const {d, storage} = rig();
  assert.equal(d.save(A, {files: ["a.png"]}), false);         // an object is no text: nothing is written
  assert.equal(storage.map.size, 0);
  d.save(A, "words");
  const kept = JSON.parse(storage.getItem(PREFIX + A));
  assert.deepEqual(Object.keys(kept).sort(), ["at", "t"]);
});

test("grow sizes the box to its text, up to the ceiling, and scrolls inside it only above that", () => {
  const box = (content, border) => ({style: {}, get scrollHeight() { return content; }, offsetHeight: 60 + (border || 0), clientHeight: 60});
  const small = box(40, 2);
  assert.equal(grow(small), 42);
  assert.equal(small.style.height, "42px");
  assert.equal(small.style.overflowY, "hidden");
  const big = box(900, 2);
  assert.equal(grow(big, 200), 200);
  assert.equal(big.style.height, "200px");
  assert.equal(big.style.overflowY, "auto");
  assert.equal(grow(box(500, 0), 120), 120);
  assert.equal(grow(null), 0);
  assert.equal(grow({}), 0);
});
