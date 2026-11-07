"use strict";
// ChatSearch (sutra_app/ui/static/js/chat_search.js): the search request, its results, archive buttons and the attachment limits (work package ABS-10).
// Ports the intent of the old app's test_chat_search.js. Run with: node --test tests/ui/js/chat_search.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const CS = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_search.js"));

test("a blank query asks nothing and a query carries the scope of the panel", () => {
  assert.equal(CS.request("   ", "all"), null);
  assert.deepEqual(CS.request("  the zebra ", "node:web"), {path: "/api/chats/search", query: {q: "the zebra", scope: "node:web"}});
  assert.deepEqual(CS.request("x", "dept:web", true).query, {q: "x", scope: "dept:web", include: "archived"});
  assert.equal(CS.request("x", "node:x' OR 1=1").query.scope, "all");
});

test("the scope follows the chat: a team or division searches the team, a function searches its node, the org chat searches everything", () => {
  assert.equal(CS.scopeOf({kind: "department", node_id: "web"}, "web"), "dept:web");
  assert.equal(CS.scopeOf({kind: "division", node_id: "menu"}, "web"), "dept:web");
  assert.equal(CS.scopeOf({kind: "function", node_id: "web.identity"}, "web"), "node:web.identity");
  assert.equal(CS.scopeOf({kind: "org", node_id: "root"}, ""), "all");
  assert.equal(CS.scopeOf(null, ""), "all");
});

test("results show title and snippet and keep archived chats under Older chats", () => {
  const html = CS.results([
    {session_id: "cs_aaaaaaaaaaaa", message_id: 4, title: "Web", snippet: "the zebra plan", archived: false},
    {session_id: "cs_old_abcdefabcdef", message_id: 0, title: "Old project", snippet: "zebra", archived: true}]);
  const head = html.indexOf("Older chats");
  assert.ok(head > 0);
  assert.ok(html.indexOf("the zebra plan") < head && html.indexOf("Old project") > head);
  assert.match(html, /data-act="open-chat" data-sid="cs_aaaaaaaaaaaa" data-mid="4"/);
});

test("nothing found is said, and wire text is escaped", () => {
  assert.match(CS.results([]), /Nothing found/);
  const html = CS.results([{session_id: "cs_a", message_id: 1, title: "<img src=x>", snippet: '"><script>1</script>', archived: false}]);
  assert.doesNotMatch(html, /<img|<script>/);
});

test("archive and un-archive appear where the app allows them", () => {
  assert.match(CS.archiveButton({id: "cs_a", kind: "department", status: "active"}), /data-act="archive"/);
  assert.match(CS.archiveButton({id: "cs_a", kind: "department", status: "archived"}), /data-act="unarchive"/);
  assert.equal(CS.archiveButton({id: "cs_org", kind: "org", status: "active"}), "");
  assert.equal(CS.archiveButton({id: "cs_old_x", kind: "legacy", status: "archived"}), "");
  assert.equal(CS.archiveButton({id: "cs_a", kind: "division", status: "archived", filed_under: "web"}), "");
});

test("the attachment limits are shown and checked", () => {
  assert.equal(CS.limitsNote(), "Up to 10 files, 20 MB each: images, PDFs and text files. The model reads the first 40,000 characters of a text file.");
  assert.equal(CS.checkFile({name: "a.png", size: 10}), "");
  assert.equal(CS.checkFile({name: "notes.md", size: 10}), "");
  assert.match(CS.checkFile({name: "a.exe", size: 10}), /Only images, PDFs and text files/);
  assert.match(CS.checkFile({name: "big.png", size: 21 * 1024 * 1024}), /over 20 MB/);
  assert.match(CS.checkFile({name: "e.txt", size: 0}), /empty/);
  assert.match(CS.checkFile(null), /could not be read/);
});
