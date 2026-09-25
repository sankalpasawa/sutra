#!/usr/bin/env node
"use strict";
/* test_chat_archive.js -- Live, Pinned, Active, Archived in the Chats rail
   (founder 2026-09-25, design canvas "Chat States Design").

   Pins: which chat reads live or archived; the row's second line (department,
   touched, how long ago -- never the folder); the x only on an active chat; the
   row menu without groups and with Unarchive on an archived chat; the Recent
   tab's four sections and the folded Archived; the clicks; the motion css.
   Server side: test_chat_archive.py. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const J = (f) => fs.readFileSync(path.join(__dirname, "static", "js", f), "utf8");
const helpers = J("02-helpers.js");
const loaders = J("07-loaders.js");
const chat = J("05-chat.js");
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

function box(o) {
  const opt = o || {};
  const b = { S: { sessions: [], sessRename: null }, console, posts: [] };
  b.sessionBusy = (id) => (opt.busy || []).includes(id);
  b.liveHeld = (s) => !!s.liveNow;
  b.isPinned = (id) => (opt.pinned || []).includes(id);
  b.rowMeta = (s) => s.metaHtml || "<span>not opened yet</span>";
  b.apiPost = (u) => { b.posts.push(u); return Promise.resolve({}); };
  b.globalThis = b;
  vm.createContext(b);
  vm.runInContext([
    grabConst(helpers, "esc"),
    grab(helpers, "hlq"),
    grab(helpers, "chatIsLive"), grab(helpers, "chatArchived"),
    grab(helpers, "chatAgo"), grab(helpers, "chatTouched"), grab(helpers, "chatLine"),
    grab(helpers, "chatUnarchive"),
    grab(helpers, "sessMenuHtml"),
  ].join("\n"), b, { filename: "archive#extract" });
  return b;
}
const row = (o) => Object.assign({ id: "c1", title: "Fix login redirect", real: true, turns: [],
  department: { ref: "d", name: "DayFlow" }, cwd: "/Users/a/Claude/dayflow",
  updated_ms: Date.UTC(2026, 8, 25, 2, 14), archived: false, archived_by: null }, o);

/* ---- states ---- */
test("a running or being-written chat is live, and never archived", () => {
  const b = box({ busy: ["c1"] });
  assert(b.chatIsLive(row()), "running in the panel is live");
  assert(!b.chatArchived(row({ archived: true })), "live beats archived");
  const b2 = box();
  assert(b2.chatIsLive(row({ liveNow: true })), "being written is live");
});
test("archived only when the server says so and it is not live", () => {
  const b = box();
  assert(b.chatArchived(row({ archived: true })));
  assert(!b.chatArchived(row()));
  assert(!b.chatArchived(row({ archived: true, real: false })), "a panel-only chat is never archived");
});

/* ---- the row's second line ---- */
test("row reads department, touched date, how long ago -- never the folder", () => {
  const b = box();
  const now = Date.UTC(2026, 8, 25, 6, 14);
  const h = b.chatLine(row(), "", now);
  assert(/class="rdept">DayFlow</.test(h), "department: " + h);
  assert(/· 25 Sep, \d\d:\d\d/.test(h) && /title="Last touched 25 Sep/.test(h), "touched: " + h);   /* local time zone */
  assert(/class="rago">\$\{esc\(chatAgo\(/.test(grab(helpers, "renderRail")), "how long ago sits on the title line");
  assert(!/dayflow<|Claude\/dayflow/.test(h), "the folder leaked into the row");
  assert(!/not opened yet/.test(h), "the old state text stayed");
});
test("no department reads so; an agent's archive names the agent", () => {
  const b = box();
  const h = b.chatLine(row({ department: null, archived: true, archived_by: "Shadow" }), "");
  assert(/No department/.test(h) && /archived by Shadow/.test(h), h);
  assert(!/archived by you/.test(b.chatLine(row({ archived: true, archived_by: "you" }), "")));
});
test("the search highlights the department on the row", () => {
  const b = box();
  assert(/<mark class="qhit">Day<\/mark>Flow/.test(b.chatLine(row(), "day")));
});
test("chatAgo speaks the design's words", () => {
  const b = box(); const n = 1e12;
  eq(b.chatAgo(n - 30e3, n), "now");
  eq(b.chatAgo(n - 20 * 60e3, n), "20 min ago");
  eq(b.chatAgo(n - 4 * 3600e3, n), "4 h ago");
  eq(b.chatAgo(n - 9 * 86400e3, n), "9 days ago");
  eq(b.chatAgo(n - 24 * 86400e3, n), "3 weeks ago");
});
test("a failed read still says so on the row", () => {
  const b = box();
  const h = b.chatLine(row({ metaHtml: '<span style="color:var(--block)">can\'t be opened</span>' }), "");
  assert(/can't be opened/.test(h), h);
});

/* ---- the menu ---- */
test("menu has no groups; an active chat can Archive, a live one cannot", () => {
  const b = box();
  const h = b.sessMenuHtml(row());
  assert(!/group/i.test(h), "groups are gone");
  assert(/data-act="archive"/.test(h) && /data-act="pin"/.test(h) && /data-act="delete"/.test(h));
  const live = box({ busy: ["c1"] }).sessMenuHtml(row());
  assert(!/data-act="archive"/.test(live), "a live chat cannot be archived from the menu");
});
test("an archived chat's menu reads Unarchive, without Pin or Mark as unread", () => {
  const h = box().sessMenuHtml(row({ archived: true }));
  assert(/data-act="unarchive"[^>]*>Unarchive</.test(h), h);
  assert(!/data-act="archive"/.test(h) && !/data-act="pin"/.test(h) && !/data-act="unread"/.test(h));
  assert(/data-act="rename"/.test(h) && /data-act="fork"/.test(h) && /data-act="delete"/.test(h));
});
test("unarchive clears the mark and tells the server", () => {
  const b = box();
  const s = row({ archived: true, archived_by: "you" });
  b.S.sessions = [s];
  b.chatUnarchive("c1");
  eq(s.archived, false);
  eq(b.posts[0], "/api/sessions/c1/unarchive");
});

/* ---- the Recent tab and the wiring ---- */
test("sessRow: x only on an active chat, before the menu", () => {
  const body = grab(helpers, "renderRail");
  assert(/s\.real && !chatArchived\(s\) && !chatIsLive\(s\) \? `<button type="button" class="rowarch"/.test(body));
  assert(/data-chatarchive="\$\{sid\}" aria-label="Archive this chat"/.test(body));
  assert(body.indexOf('class="rowarch"') < body.indexOf('class="rowmenu"'), "x sits before the three dots");
});
test("Recent: Live, Pinned, Active by day, Archived folded at the bottom", () => {
  const body = grab(helpers, "renderRail");
  const iLive = body.indexOf('"Live"'), iPin = body.indexOf('"Pinned"'),
        iDay = body.indexOf('["Today","Yesterday"'), iArch = body.indexOf("Archived<span");
  assert(iLive > 0 && iPin > iLive && iDay > iPin && iArch > iDay, "section order");
  assert(/if \(chatIsLive\(s\)\) live\.push\(s\);\s*else if \(chatArchived\(s\)\) arch\.push\(s\);\s*else if \(isPinned\(s\.id\)\) pinned\.push\(s\);/.test(body),
    "one section per chat, live first");
  assert(/const open = !!\(S\.ui\.archOpen \|\| q\)/.test(body), "folded unless opened or searching");
  assert(/Show \$\{arch\.length - shown\} more/.test(body));
});
test("clicks: x archives, the fold toggles, an archived chat reopens on click", () => {
  assert(/closest\("\[data-chatarchive\]"\)[\s\S]{0,40}chatArchive\(/.test(loaders));
  assert(/data-archtoggle[\s\S]{0,60}S\.ui\.archOpen = !S\.ui\.archOpen/.test(loaders));
  assert(/chatArchived\(was\)\) chatUnarchive\(id\)/.test(loaders), "click reopens");
  assert(/case "archive": chatArchive\(sid\)/.test(loaders) && /case "unarchive": chatUnarchive\(sid\)/.test(loaders));
  assert(!/archiveSession|setGroup|groupMap|group-new/.test(loaders + chat), "old archive + groups gone");
});
test("motion: the row folds in 200 ms; reduced motion skips it", () => {
  assert(/\.srow\.arch-out\{animation:archOut \.2s/.test(css));
  assert(/prefers-reduced-motion: reduce\)\{\.rlist \.srow\.arch-out\{animation:none/.test(css));
  assert(/classList\.add\("arch-out"\)[\s\S]{0,200}setTimeout\([\s\S]{0,300}\}, 200\)/.test(grab(helpers, "chatArchive")));
});

(async () => {
  for (const [n, f] of queue) {
    try { await f(); pass++; console.log("  ok   " + n); }
    catch (e) { fail++; console.log("  FAIL " + n + "\n       " + e.message); }
  }
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
