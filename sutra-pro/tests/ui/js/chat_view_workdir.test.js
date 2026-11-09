"use strict";
// ChatView.workdirChip: the one line under a team chat's box (D125; node_panel.js paints it). With a folder: "Working in <last two path segments>" and the full path
// as the tooltip; without one: "No working folder: Choose" with a Choose button that opens Settings > Working folder; before the answer (or when it failed): nothing.
// Run with: node --test tests/ui/js/chat_view_workdir.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../../../sutra_app/ui/static");
const {workdirChip} = require(path.join(ROOT, "js/chat_view.js"));

test("a folder is named by its last two segments, with the full path as the tooltip", () => {
  assert.equal(workdirChip({path: "/Users/me/Documents/my-project"}), '<span title="/Users/me/Documents/my-project">Working in Documents/my-project</span>');
  assert.match(workdirChip({path: "/Users/me/proj/"}), /Working in me\/proj</);
  assert.match(workdirChip({path: "C:\\Users\\me\\proj"}), /Working in me\/proj</);
  assert.match(workdirChip({path: "/proj"}), /Working in proj</);
  assert.match(workdirChip({path: "/"}), /Working in \/</);
});

test("no folder says so and offers Choose, a button that opens the settings group", () => {
  const expected = 'No working folder: <button type="button" class="linkbtn" data-act="open-workdir">Choose</button>';
  assert.equal(workdirChip({path: null, usable: false}), expected);
  assert.equal(workdirChip({path: ""}), expected);
  assert.equal(workdirChip({}), expected);
});

test("nothing is drawn before the answer, or when reading it failed", () => {
  for (const unknown of [null, undefined, "nonsense", 7, []]) assert.equal(workdirChip(unknown), "");
});

test("a path from the wire is escaped, in the words and in the tooltip", () => {
  const html = workdirChip({path: '/a/<img src=x onerror="alert(1)">/b"c'});
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /title="\/a\/&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;\/b&quot;c"/);
});

test("the panel has the line under its box, reads the folder once per open, and Choose goes to the settings group", () => {
  const src = fs.readFileSync(path.join(ROOT, "js/node_panel.js"), "utf8");
  assert.match(src, /<p class="nwd" hidden><\/p><\/div><p class="nnote"/);                      // inside the composer, so it hides with it
  assert.equal((src.match(/api\(\)\.get\("\/api\/connectors\/workdir"\)/g) || []).length, 1);
  assert.match(src, /name === "open-workdir"\) \{ if \(opts\.openSettings\) opts\.openSettings\("workdir"\)/);
  const home = fs.readFileSync(path.join(ROOT, "js/home.js"), "utf8");
  assert.match(home, /openSettings: group => selectPane\("settings", \{group\}\)/);
  assert.match(home, /act === "workdir-choose" \|\| act === "workdir-access"\) workdirAct\(act, b\)/);
});
