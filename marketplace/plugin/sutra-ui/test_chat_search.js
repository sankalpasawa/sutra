#!/usr/bin/env node
"use strict";
/* test_chat_search.js -- the Chats rail search (founder 2026-09-24: "titles,
   folders, headers. That's it." and "show me the UI where the search icon is").

   What ships:
     - panel.html: a search icon at the end of the Recent/Dept/Routines row and
       a .rsearch box that takes the row's place while open;
     - chatMatches / chatSearchList / hlq / chatSearchRemote (02-helpers.js):
       match on title, folder, department name, routine name -- never text;
       loaded rows plus the server's older rows, deduped, newest first;
     - realSessionFromRow (01-state.js): one converter for list rows and search
       rows; adoptRealSessions keeps a chat opened from search while its pane
       is open;
     - 07-loaders.js: click open/close, typing, Esc, opening an older result.
   Server side: test_chat_search.py. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const J = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const helpers = J("02-helpers.js");
const state = J("01-state.js");
const loaders = J("07-loaders.js");
const html = fs.readFileSync(path.join(__dirname, "static", "panel.html"), "utf8");
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

function box(api) {
  const b = { S: { sessions: [], openPanes: [] }, console, timers: [], rails: 0 };
  b.setTimeout = (fn, ms) => { b.timers.push({ fn, ms }); return b.timers.length; };
  b.clearTimeout = () => {};
  b.renderRail = () => { b.rails++; };
  b.sessionBusy = () => false;
  b.apiGet = api || (() => Promise.resolve([]));
  b.document = { querySelector: () => null };
  b.globalThis = b;
  vm.createContext(b);
  vm.runInContext([
    grabConst(helpers, "esc"),
    grab(helpers, "chatSearchNorm"), grab(helpers, "chatMatches"),
    grab(helpers, "chatSearchList"), grab(helpers, "hlq"),
    "let _chatSearchTimer = null;",
    grab(helpers, "chatSearchRemote"),
    grab(state, "realSessionFromRow"), grab(state, "adoptRealSessions"),
  ].join("\n"), b, { filename: "search#extract" });
  return b;
}
const row = (o) => Object.assign({ id: "x", title: "t", real: true, local: false, cwd: "",
                                   project: "", department: null, routine: null,
                                   updated_ms: 1, turns: [] }, o);

/* ---- matching: titles, folders, headers, and nothing else ---- */
test("matches the title, case-insensitively", () => {
  const b = box();
  assert(b.chatMatches(row({ title: "Paisa KYC flow" }), "paisa"));
  assert(b.chatMatches(row({ title: "PAISA" }), "paisa"));
});
test("matches the folder", () => {
  const b = box();
  assert(b.chatMatches(row({ cwd: "/Users/a/Claude/paisa" }), "paisa"));
});
test("matches the department header and the routine header", () => {
  const b = box();
  assert(b.chatMatches(row({ department: { ref: "d1", name: "Paisa" } }), "paisa"));
  assert(b.chatMatches(row({ routine: { routine: "daily-paisa-sync" } }), "paisa"));
});
test("does not match anything else (no transcript text)", () => {
  const b = box();
  const r = row({ title: "Refund", cwd: "/w/billu", turns: [{ text: "paisa" }], branch: "paisa" });
  assert(!b.chatMatches(r, "paisa"), "turn text or branch must not match");
});
test("an empty query matches everything; the query is trimmed", () => {
  const b = box();
  assert(b.chatMatches(row({}), ""));
  eq(b.chatSearchNorm("  PaiSa "), "paisa");
});

/* ---- highlight is escaped ---- */
test("hlq marks every hit and escapes the rest", () => {
  const b = box();
  eq(b.hlq("Paisa & paisa", "paisa"),
     '<mark class="qhit">Paisa</mark> &amp; <mark class="qhit">paisa</mark>');
});
test("hlq never lets a title inject markup", () => {
  const b = box();
  const out = b.hlq('<img src=x onerror=1>paisa', "img");
  assert(!/<img/.test(out), "raw tag leaked: " + out);
  assert(/&lt;<mark class="qhit">img<\/mark>/.test(out), out);
});
test("hlq with no query is plain esc", () => {
  const b = box();
  eq(b.hlq("a<b", ""), "a&lt;b");
});

/* ---- the list: loaded rows plus older server rows ---- */
test("chatSearchList merges loaded + server rows, dedups, newest first", () => {
  const b = box();
  b.S.sessions = [row({ id: "a", title: "paisa one", updated_ms: 30 }),
                  row({ id: "b", title: "billu", updated_ms: 20 })];
  b.S.chatSearch = { q: "paisa", rows: [row({ id: "a", title: "paisa one", updated_ms: 30 }),
                                         row({ id: "c", title: "old paisa", updated_ms: 5 })] };
  const ids = b.chatSearchList("paisa").map(s => s.id).join(",");
  eq(ids, "a,c");
});
test("server rows for a different query are ignored", () => {
  const b = box();
  b.S.chatSearch = { q: "pai", rows: [row({ id: "c", title: "paisa" })] };
  eq(b.chatSearchList("paisa").length, 0);
});

/* ---- the server call keeps only the current query's answer ---- */
test("chatSearchRemote asks /api/sessions?q= after a debounce", async () => {
  let asked = "";
  const b = box((u) => { asked = u; return Promise.resolve([{ id: "z", title: "old paisa", mtime: 9 }]); });
  b.S.chatQ = "Paisa";
  b.chatSearchRemote();
  eq(b.S.chatSearch.pending, true);
  eq(b.timers.length, 1); assert(b.timers[0].ms >= 150, "debounced");
  b.timers[0].fn();
  await new Promise(r => setImmediate(r));
  assert(/\/api\/sessions\?limit=\d+&q=paisa$/.test(asked), asked);
  eq(b.S.chatSearch.rows[0].id, "z");
  eq(b.S.chatSearch.rows[0].updated_ms, 9000, "converted to a rail row");
  eq(b.S.chatSearch.pending, false);
});
test("a slow answer to an old query never overwrites the new one", async () => {
  const b = box(() => Promise.resolve([{ id: "stale", title: "pai" }]));
  b.S.chatQ = "pai";
  b.chatSearchRemote();
  const fire = b.timers[0].fn;
  b.S.chatQ = "paisa";               /* user kept typing */
  b.S.chatSearch = { q: "paisa", rows: [], pending: true };
  fire();
  await new Promise(r => setImmediate(r));
  eq(b.S.chatSearch.q, "paisa");
  eq(b.S.chatSearch.rows.length, 0);
});
test("clearing the box drops the server answer", () => {
  const b = box();
  b.S.chatSearch = { q: "x", rows: [] };
  b.S.chatQ = "  ";
  b.chatSearchRemote();
  eq(b.S.chatSearch, null);
});

/* ---- a chat opened from search survives a list refresh ---- */
test("adoptRealSessions keeps an open search result the new page lacks", () => {
  const b = box();
  const old = b.realSessionFromRow({ id: "old", title: "old paisa", mtime: 1 });
  old.fromSearch = true;
  b.S.sessions = [old];
  b.S.openPanes = ["old"];
  b.adoptRealSessions([{ id: "new", title: "new", mtime: 50 }]);
  eq(b.S.sessions.map(s => s.id).join(","), "new,old");
});
test("...but not once its pane is closed, and never a non-search row", () => {
  const b = box();
  const old = b.realSessionFromRow({ id: "old", title: "old", mtime: 1 });
  old.fromSearch = true;
  const other = b.realSessionFromRow({ id: "gone", title: "gone", mtime: 2 });
  b.S.sessions = [old, other];
  b.S.openPanes = ["gone"];
  b.adoptRealSessions([{ id: "new", title: "new", mtime: 50 }]);
  eq(b.S.sessions.map(s => s.id).join(","), "new");
});

/* ---- the markup, styles and wiring the design promised ---- */
test("panel.html: search icon in the toggle row, box hidden by default", () => {
  const tog = html.slice(html.indexOf('<div class="rtoggle">'), html.indexOf('<div class="rsearch"'));
  assert(/data-chatsearch="open"[\s\S]*aria-label="Search chats"/.test(tog), "icon button in the row");
  assert(/<div class="rsearch" hidden>/.test(html), "box starts hidden");
  assert(/<input type="search" data-chatq aria-label="Search chats"/.test(html), "labelled input");
  assert(/data-chatsearch="close" aria-label="Close search"/.test(html), "labelled close");
});
test("panel.css: hidden really hides, the hit mark is styled", () => {
  assert(/\.rtoggle\[hidden\],\.rsearch\[hidden\]\{display:none\}/.test(css));
  assert(/mark\.qhit\{/.test(css));
});
test("07-loaders: click, typing and Esc are wired", () => {
  assert(/closest\("\[data-chatsearch\]"\)/.test(loaders), "click");
  assert(/addEventListener\("input"[\s\S]{0,80}data-chatq/.test(loaders), "input");
  assert(/Escape"[^\n]*data-chatq[^\n]*chatSearchClose/.test(loaders), "Esc");
  assert(/hit\.fromSearch = true; S\.sessions\.push\(hit\)/.test(loaders), "open older result");
});
test("renderRail draws every grouping from the search list", () => {
  const body = grab(helpers, "renderRail");
  assert(/const LIST = q \? chatSearchList\(q\) : S\.sessions;/.test(body));
  assert(!/S\.sessions\.forEach/.test(body), "a grouping still reads S.sessions directly");
  assert(/hlq\(dept\.name, q\)/.test(body) && /hlq\(gr\.id, q\)/.test(body), "headers highlighted");
  assert(/hlq\(s\.title, q\)/.test(body) && /hlq\(trailTxt, q\)/.test(body), "title + folder highlighted");
});

(async () => {
  for (const [n, f] of queue) {
    try { await f(); pass++; console.log("  ok   " + n); }
    catch (e) { fail++; console.log("  FAIL " + n + "\n       " + e.message); }
  }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
