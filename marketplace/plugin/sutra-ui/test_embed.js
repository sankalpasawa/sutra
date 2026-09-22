#!/usr/bin/env node
/* test_embed.js -- the panel's chat-only mode (slice I, holding/plans/
   department-screen/LLD-FUNCTIONS.md section 4).

   The panel also loads INSIDE a department's function card as `/?embed=chat`.
   That frame shares the main panel's origin and therefore its localStorage, so
   it must never write a key the main panel reads. Two pins:

   1. The real EMBED_CHAT flag and lsSet from 01-state.js, evaluated in a vm:
      the flag is true only for embed=chat, and in that mode lsSet writes the
      function-chat map and nothing else.
   2. A scan of every script: each direct localStorage write is inside lsSet or
      carries the EMBED_CHAT guard on its own line, so a new writer added later
      without the guard fails here, not on the founder's layout.
   Run: node test_embed.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const JS = path.join(__dirname, "static", "js");
const stateSrc = fs.readFileSync(path.join(JS, "01-state.js"), "utf8");
let ran = 0, failed = 0;
function test(name, fn){
  ran++;
  try { fn(); console.log("ok   " + name); }
  catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.stack || e)); }
}

/* the block under test, cut from the real file: from the flag to the end of lsSet */
const from = stateSrc.indexOf("const EMBED_CHAT");
const lsAt = stateSrc.indexOf("function lsSet(", from);
const to = stateSrc.indexOf("\n}\n", lsAt) + 3;
const BLOCK = stateSrc.slice(from, to);

function load(search){
  const store = {}, classes = [];
  const ctx = {
    URLSearchParams,
    location: { search },
    localStorage: { setItem: (k, v) => { store[k] = v; }, getItem: (k) => (k in store ? store[k] : null) },
    document: { documentElement: { classList: { add: (c) => classes.push(c) } } },
    JSON,
  };
  vm.createContext(ctx);
  vm.runInContext(BLOCK + "\n;this.__flag = EMBED_CHAT; this.__lsSet = lsSet;", ctx);
  return { ctx, store, classes };
}

test("the block under test is the real one", () => {
  assert.ok(from !== -1 && lsAt > from && to > lsAt, "01-state.js carries EMBED_CHAT before lsSet");
  assert.ok(/EMBED_KEYS/.test(BLOCK) && /function lsSet\(/.test(BLOCK));
});

test("EMBED_CHAT is true for embed=chat and for nothing else", () => {
  assert.strictEqual(load("?embed=chat&dept=r4&fn=audit").ctx.__flag, true);
  for (const s of ["", "?embed=1", "?embed=term", "?embed=chats", "?dept=r4&fn=audit"])
    assert.strictEqual(load(s).ctx.__flag, false, s);
});

test("the chat-only frame marks the page so the chrome can hide", () => {
  assert.deepStrictEqual(load("?embed=chat").classes, ["embed-chat"]);
  assert.deepStrictEqual(load("").classes, []);
});

test("in the chat-only frame lsSet writes the function-chat map and nothing else", () => {
  const { ctx, store } = load("?embed=chat&dept=r4&fn=audit");
  for (const k of ["sutra.panel.layout", "sutra.panel.term", "sutra.panel.termw", "sutra.panel.sidetab",
                   "sutra.panel.prevurl", "sutra.panel.groups", "sutra.panel.pinned", "sutra.panel.unread"])
    ctx.__lsSet(k, { any: 1 });
  assert.deepStrictEqual(Object.keys(store), [], "no main-panel key written");
  ctx.__lsSet("sutra.fnchat", { "r4:audit": { claude_session: "u-1" } });
  assert.deepStrictEqual(Object.keys(store), ["sutra.fnchat"]);
});

test("outside the frame lsSet writes as it always did", () => {
  const { ctx, store } = load("");
  ctx.__lsSet("sutra.panel.layout", { dest: "org2" });
  assert.strictEqual(store["sutra.panel.layout"], JSON.stringify({ dest: "org2" }));
});

test("every direct localStorage write in the panel is guarded or goes through lsSet", () => {
  const bad = [];
  for (const f of fs.readdirSync(JS).filter(n => n.endsWith(".js"))){
    const lines = fs.readFileSync(path.join(JS, f), "utf8").split("\n");
    lines.forEach((line, i) => {
      if (!/localStorage\.(setItem|removeItem)\(/.test(line)) return;
      if (/^\s*(\/\/|\*|\/\*)/.test(line)) return;                      /* prose */
      if (/EMBED_CHAT/.test(line)) return;                               /* guarded on the line */
      /* the one writer lsSet wraps, in 01-state.js, sits two lines under its own guard */
      if (f === "01-state.js" && /function lsSet\(/.test(lines[i - 2] || "") && /EMBED_CHAT/.test(lines[i - 1] || "")) return;
      bad.push(f + ":" + (i + 1) + ": " + line.trim());
    });
  }
  assert.deepStrictEqual(bad, [], "unguarded writers:\n" + bad.join("\n"));
});

console.log("\n" + (failed ? failed + " failed" : "all passed") + " (" + ran + " tests)");
process.exit(failed ? 1 : 0);
