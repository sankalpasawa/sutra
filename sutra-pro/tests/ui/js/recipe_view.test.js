"use strict";
// What the Recipes page draws (DV-3): the list with starters apart, one recipe with its parts, the start form with its blanks, the edit form, the versions and a file to read; everything from the wire is
// escaped; the page says "Recipe" and never "playbook", "cron" or a machine name.
// Run with: node --test tests/ui/js/recipe_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const View = require(path.join(path.resolve(__dirname, "../../../sutra_app/ui/static/js"), "recipe_view.js"));
const RID = "rcp_0123456789ab";
const BODY = {overview: "Write the menu.", procedure: ["Ask what is on sale", "Write each dish in $1 words"], specifications: ["One page"], advice: [], forbidden: ["Never invent a price"], needs: [{label: "How long each dish may be"}]};
const own = (over = {}) => Object.assign({id: RID, title: "Menu", kind: "own", status: "active", version: 3, current_version: 3, overview: "Write the menu.", body: BODY,
  versions: [{version: 3, note: "back to version 1", sha256: "a"}, {version: 2, note: "shorter", sha256: "b"}, {version: 1, note: "first version", sha256: "c"}]}, over);
const starter = (over = {}) => Object.assign({id: "starter-explain-this-folder", title: "Explain this folder", kind: "starter", status: "active", version: 1, overview: "A plain guide.", body: BODY, versions: []}, over);

test("the list has the owner's recipes first and the starters apart, each with Open", () => {
  const html = View.listHtml([own(), starter()]);
  assert.match(html, /<h2>Recipes<\/h2>[\s\S]*aria-label="Your recipes"[\s\S]*<b>Menu<\/b>[\s\S]*<h2>Starters<\/h2>[\s\S]*ships with Sutra, cannot be changed/);
  assert.equal((html.match(/data-act="open"/g) || []).length, 2);
  assert.match(html, /data-act="new">New recipe</);
  assert.match(html, /Read a recipe file/);
  assert.match(View.listHtml([starter()]), /You have no recipes yet/);
  assert.equal(View.listHtml([{id: "../x", title: "bad", kind: "own"}, null]).includes("bad"), false, "an id of another shape is never drawn");
});

test("one recipe shows its parts in order, what it asks for, and Start, Change, Put it away and a file", () => {
  const html = View.detailHtml(own(), {});
  assert.match(html, /<h2>Menu<\/h2><p class="cnote">Your recipe<\/p><p>Write the menu\.<\/p>/);
  assert.match(html, /<h3>Steps, in order<\/h3><ol><li>Ask what is on sale<\/li><li>Write each dish in \$1 words<\/li><\/ol>/);
  assert.match(html, /<h3>The result must be like this<\/h3><ul><li>One page<\/li>/);
  assert.match(html, /<h3>Never do these<\/h3><ul><li>Never invent a price<\/li>/);
  assert.equal(html.includes("Good to know"), false, "an empty part is not drawn");
  assert.match(html, /<h3>It asks you for<\/h3><ol><li>How long each dish may be<\/li>/);
  for (const a of ["start-open", "edit", "archive"]) assert.ok(html.includes('data-act="' + a + '"'), a);
  assert.match(html, /data-archived="1">Put it away</);
  assert.match(html, /href="\/api\/recipes\/rcp_0123456789ab\/export" download>Save as a file</);
});

test("a starter cannot be changed: it offers a copy, and a put-away recipe offers to bring it back and no Start", () => {
  const s = View.detailHtml(starter(), {});
  assert.match(s, /It cannot be changed: make a copy to change it\./);
  assert.ok(s.includes('data-act="copy"') && !s.includes('data-act="edit"') && !s.includes('data-act="archive"') && !s.includes("Earlier versions"));
  const away = View.detailHtml(own({status: "archived"}), {});
  assert.match(away, /It is put away\./);
  assert.ok(away.includes("Bring it back") && !away.includes('data-act="start-open"'));
});

test("the versions say which one is in use and offer to go back to any other", () => {
  const html = View.versionsHtml(own());
  assert.match(html, /<b>Version 3<\/b><span class="cnote">back to version 1<\/span><span class="pstate">this is the one in use<\/span>/);
  assert.equal((html.match(/data-act="revert"/g) || []).length, 2);
  assert.match(html, /data-version="1">Go back to this version</);
  assert.equal(View.versionsHtml(own({versions: [{version: 1}]})), "", "one version: nothing to go back to");
});

test("the start form has one box for each thing the recipe asks for, says what starting does and shows an error", () => {
  const html = View.startHtml(own(), {error: "This recipe asks you for 1 thing"});
  assert.match(html, /<form class="rform" data-act="start" data-id="rcp_0123456789ab"><h3>Start “Menu”<\/h3>/);
  assert.match(html, /<label for="r-blank-0">How long each dish may be<\/label><input id="r-blank-0" name="blank0" maxlength="300" required>/);
  assert.match(html, /Starting writes a request in plain words/);
  assert.match(html, /role="alert">This recipe asks you for 1 thing/);
  assert.match(View.startHtml(own({body: Object.assign({}, BODY, {needs: []})}), {}), /asks you for nothing/);
});

test("the edit form holds one line per row, says when it is only a draft and keeps what was typed", () => {
  const html = View.editHtml({id: RID, title: "Menu", body: BODY, draft: true}, {error: "A line of procedure: That line is empty."});
  assert.match(html, /data-act="save" data-id="rcp_0123456789ab"><h2>Change the recipe<\/h2>/);
  assert.match(html, /This is a draft\. Read it, change what you like, then save it\. Nothing is saved yet\./);
  assert.match(html, /<textarea id="r-procedure" name="procedure">Ask what is on sale\nWrite each dish in \$1 words<\/textarea>/);
  assert.match(html, /<textarea id="r-needs" name="needs">How long each dish may be<\/textarea>/);
  assert.match(html, /role="alert">A line of procedure/);
  assert.match(View.editHtml({id: "", title: "", body: {}}, {}), /<h2>New recipe<\/h2>/);
  assert.deepEqual(View.toLines(" a \n\n b\n"), ["a", "b"]);
  assert.equal(View.fromLines(["a", "", "b"]), "a\nb");
});

test("the file to read says that nothing is saved until Save", () => {
  const html = View.importHtml({error: "A recipe file starts with a title line"});
  assert.match(html, /data-act="import"><h2>Read a recipe file<\/h2>/);
  assert.match(html, /nothing is saved until you press Save/);
  assert.match(html, /role="alert">A recipe file starts/);
});

test("everything from the wire is escaped and the page uses no jargon", () => {
  const evil = "<img src=x onerror=1>";
  const r = own({title: evil, overview: evil, body: {overview: evil, procedure: [evil], specifications: [evil], advice: [evil], forbidden: [evil], needs: [{label: evil}]}, versions: [{version: 1, note: evil}, {version: 2, note: evil}], current_version: 2});
  const html = View.listHtml([r]) + View.detailHtml(r, {sent: evil}) + View.startHtml(r, {error: evil}) + View.editHtml(r, {error: evil}) + View.importHtml({error: evil});
  assert.equal(html.includes("<img"), false);
  const words = (View.listHtml([own(), starter()]) + View.detailHtml(own(), {}) + View.startHtml(own(), {}) + View.editHtml(own(), {}) + View.importHtml({})).replace(/<[^>]*>/g, " ");
  assert.equal(/\b(playbook|cron|node|nodes|lease|tier|grant|ledger|acu|api)\b/i.test(words), false, words);
});

test("the start form says that a recipe is words to the planner, not a lock", () => {                                       // architect ruling
  const html = View.startHtml(own(), {});
  assert.match(html, /It is not a lock: the access you gave Sutra to your folder is the lock\./);
  assert.match(html, /"Never do these" included, is told to Sutra as words/);
});
