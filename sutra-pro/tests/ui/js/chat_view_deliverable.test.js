"use strict";
// ChatView's finished-report card (D135): the report a run delivered, in the TEAM's chat: the report as markdown (ChatMarkdown), folded when long (ChatFold),
// the files git saw change in the owner's folder (nothing at all when git could not say), and "Open the full report", a real link to the team page's Preview tab
// for that run. The done card in the org chat gets "Open the report", the same link. Every word and id from the wire is escaped; the markup is well formed.
// Run with: node --test tests/ui/js/chat_view_deliverable.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const ChatView = require(path.join(JS, "chat_view.js"));
globalThis.ChatMarkdown = require(path.join(JS, "chat_markdown.js"));
globalThis.ChatFold = require(path.join(JS, "chat_fold.js"));

const RUN = "j2-20261104-100004-7f3a";
const TASK = "tsk_b7c8d9e0f1a2";
const REPORT = "# The project\n\n## Findings\n\n- The settings page is `ui/pages/settings.html`.\n\n## Changes\n\n- `README.md`: added the line.\n\n## Confirmation\n\nRead README.md.\n\n" +
  "## Open items\n\n- Nothing.\n\n## Outcome\n\nREADME.md now ends with the line.\n";
const LONG = REPORT + "\n" + "A long paragraph about what was found in the settings code. ".repeat(40);
const card = (over = {}) => Object.assign({type: "deliverable", task_id: TASK, run_id: RUN, dept_id: "web", label: "Project work report", file: "project.md", text: REPORT, cut: false}, over);
const HREF = "/d/web/?view=detail&amp;tab=preview&amp;run=" + RUN;

// A well-formedness check: every tag closes in order and no attribute value holds a raw "<"; returns the number of elements.
function wellFormed(markup) {
  const stack = [];
  let elements = 0;
  for (const m of markup.matchAll(/<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<[^>]*>/g)) {
    assert.ok(m[2] !== undefined, `a malformed tag: ${m[0].slice(0, 80)}`);
    if (m[1] === "/") assert.equal(stack.pop(), m[2], `</${m[2]}> closes the wrong tag`);
    else { elements += 1; if (m[4] !== "/") stack.push(m[2]); }
  }
  assert.deepEqual(stack, [], "every tag is closed");
  assert.equal(/&(?!(?:amp|lt|gt|quot|#39);)/.test(markup), false, "a stray &");
  return elements;
}

test("a short report is drawn as markdown in the card, with its title and the link to the whole report", () => {
  const html = ChatView.card(card({text: "## Findings\n\n- one `file.md`\n\n## Outcome\n\nDone."}));
  wellFormed(html);
  assert.match(html, /^<div class="ncard c-deliverable" data-card="deliverable" data-task="tsk_b7c8d9e0f1a2" data-run="j2-20261104-100004-7f3a">/);
  assert.match(html, /<h2 class="cdtitle">Project work report<\/h2>/);
  assert.match(html, /<div class="cdreport"><div class="cmd"><h4 class="cmd-h">Findings<\/h4><ul class="cmd-l"><li>one <code>file\.md<\/code><\/li><\/ul>/);
  assert.doesNotMatch(html, /<details/);                                                                       // short: nothing to fold
  assert.ok(html.includes(`<div class="acts"><a class="lbtn" data-act="open-team" href="${HREF}">Open the full report</a></div>`), html.slice(-300));
});

test("a long report folds into one row that names its sections, and opens to the whole report", () => {
  const html = ChatView.card(card({text: LONG}));
  wellFormed(html);
  assert.equal((html.match(/<details/g) || []).length, 1);
  assert.match(html, /<details class="cfold cfold-text"><summary>Read the report \(Findings, Changes, Confirmation, Open items, Outcome\)<\/summary><div class="cmd">/);
  assert.ok(html.indexOf("A long paragraph") > html.indexOf("<summary>"), "the text is inside the fold");
  assert.match(html, /<h3 class="cmd-h">The project<\/h3>/);
});

test("a report that was cut says so and points to the whole of it", () => {
  const cut = ChatView.card(card({text: LONG, cut: true}));
  assert.match(cut, /<p class="cdcut">The report is longer than shown here\. Open the full report to read all of it\.<\/p>/);
  assert.doesNotMatch(ChatView.card(card({cut: false})), /cdcut/);
  assert.doesNotMatch(ChatView.card(card({cut: "true"})), /cdcut/);                                          // only a real true
});

test("the files git saw change are listed with a word for each, counted with the ones not shown", () => {
  const html = ChatView.card(card({changes: {files: [{path: "README.md", status: "modified"}, {path: "docs/NEW.md", status: "new"}, {path: "old.md", status: "deleted"},
    {path: "back.md", status: "reverted"}], more: 3}}));
  wellFormed(html);
  assert.match(html, /<p class="cdhead">Changed in your folder during this run \(7\)<\/p>/);
  assert.match(html, /<li><code>README\.md<\/code><span class="cdst st-modified">changed<\/span><\/li>/);
  assert.match(html, /<li><code>docs\/NEW\.md<\/code><span class="cdst st-new">new<\/span><\/li>/);
  assert.match(html, /<li><code>old\.md<\/code><span class="cdst st-deleted">deleted<\/span><\/li>/);
  assert.match(html, /<li><code>back\.md<\/code><span class="cdst st-reverted">back to the committed version<\/span><\/li>/);
  assert.match(html, /<li class="cdmore">and 3 more<\/li>/);
  assert.ok(html.indexOf("cdreport") < html.indexOf("cdchanges") && html.indexOf("cdchanges") < html.indexOf('class="acts"'), "the report, then the files, then the link");
});

test("git looked and nothing changed is said; git could not say is not said at all", () => {
  assert.match(ChatView.card(card({changes: {files: [], more: 0}})), /<p class="cdnone">No file in your folder changed during this run \(checked with git\)\.<\/p>/);
  for (const bare of [card(), card({changes: null}), card({changes: "none"}), card({changes: []})]) {
    const html = ChatView.card(bare);
    assert.doesNotMatch(html, /cdchanges|checked with git|Changed in your folder/);
  }
});

test("a status this module does not know is shown as it came, escaped, and a row with no path is not a row", () => {
  const html = ChatView.card(card({changes: {files: [{path: "x.md", status: "<b>weird</b>"}, {path: "", status: "new"}, {status: "new"}, 5, null], more: 0}}));
  wellFormed(html);
  assert.match(html, /<span class="cdst st-other">&lt;b&gt;weird&lt;\/b&gt;<\/span>/);
  assert.match(html, /\(1\)<\/p>/);
  assert.equal((html.slice(html.indexOf("cdfiles")).match(/<li>/g) || []).length, 1);          // the one row that has a path
});

test("a run that ended before the report was written says so and still lists what it changed", () => {
  const html = ChatView.card(card({text: "", file: "", changes: {files: [{path: "README.md", status: "modified"}], more: 0}}));
  wellFormed(html);
  assert.match(html, /<p class="cdnone">The report was not written: the run ended before it\.<\/p>/);
  assert.match(html, /<code>README\.md<\/code>/);
  assert.doesNotMatch(html, /<details/);
});

test("without the markdown and fold scripts the report is still readable text, escaped", () => {
  const saved = [globalThis.ChatMarkdown, globalThis.ChatFold];
  delete globalThis.ChatMarkdown; delete globalThis.ChatFold;
  try {
    const html = ChatView.card(card({text: "## Findings\n\n**bold** and `code` <script>x</script>"}));
    wellFormed(html);
    assert.match(html, /<b>bold<\/b> and <code>code<\/code> &lt;script&gt;x&lt;\/script&gt;/);
    assert.doesNotMatch(html, /<script|<details/);
  } finally { [globalThis.ChatMarkdown, globalThis.ChatFold] = saved; }
});

test("the link needs a team id and a run id the page knows; an odd id makes no link rather than a wrong one", () => {
  for (const bad of [{dept_id: "../x"}, {dept_id: ""}, {dept_id: "."}, {dept_id: ".."}, {dept_id: '"><script>'}, {dept_id: "a b"}, {run_id: "../x"}, {run_id: ""},
    {run_id: "run-1"}, {run_id: "j2-"}, {run_id: 'j2-1"><script>'}, {run_id: "j2-a b"}, {dept_id: null}, {run_id: 5}]) {
    const html = ChatView.card(card(bad));
    assert.doesNotMatch(html, /<a /, JSON.stringify(bad));
    wellFormed(html);
  }
  assert.match(ChatView.card(card({dept_id: "web.team:1_a-b"})), /href="\/d\/web\.team%3A1_a-b\/\?view=detail&amp;tab=preview&amp;run=j2-20261104-100004-7f3a"/);
});

test("every word and id of the wire is escaped and the markup stays well formed", () => {
  const bad = `<script>alert("x")</script> & 'q'`;
  const html = ChatView.card({type: "deliverable", task_id: bad, run_id: bad, dept_id: bad, label: bad, file: bad, cut: true,
    text: bad + "\n\n## " + bad + "\n\n| a | b |\n|---|---|\n| " + bad + " | x |\n\n```\n" + bad + "\n```\n" + "z".repeat(1500),
    changes: {files: [{path: bad, status: bad}, {path: bad, status: "new"}], more: bad}});
  assert.doesNotMatch(html, /<script/);
  wellFormed(html);
});

test("the report's own markup is never drawn: no html, no link, no image from the text", () => {
  const html = ChatView.card(card({text: "<img src=x onerror=alert(1)> [a link](https://example.com) ![pic](https://example.com/p.png)\n\n<a href=\"https://example.com\">x</a>"}));
  assert.doesNotMatch(html, /<img|<a href="https:|<script/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt; \[a link\]\(https:\/\/example\.com\)/);       // the text stays text: no link, no image, no element
  wellFormed(html);
});

test("a done card with a report has Open the report, the same link, first; one without is as it always was", () => {
  const done = {type: "done", task_id: TASK, dept_name: "Web", title: "Update the README", status: "done", outcome: "Done.",
    report: {dept_id: "web", run_id: RUN, label: "Project work report"}};
  const html = ChatView.card(done);
  wellFormed(html);
  assert.ok(html.includes(`<div class="acts"><a class="lbtn" data-act="open-team" href="${HREF}">Open the report</a><button type="button" class="lbtn" data-act="open-team"`), html);
  const before = '<div class="ncard ready ok c-done" data-card="done" data-tone="ok" data-task="tsk_b7c8d9e0f1a2"><h2>Your Web team is done</h2><p class="ctitle">Update the README</p>' +
    '<p class="coutcome">Done.</p><div class="acts"><button type="button" class="lbtn" data-act="open-team" data-task="tsk_b7c8d9e0f1a2" data-dept-name="Web">Open the team</button></div></div>';
  assert.equal(ChatView.card({...done, report: undefined}), before);
  assert.equal(ChatView.card({...done, report: null}), before);
  assert.equal(ChatView.card({...done, report: {dept_id: "../x", run_id: RUN}}), before);                       // a link that cannot be made is left out
  assert.equal(ChatView.card({...done, report: "yes"}), before);
});

test("in the team's chat the card is one Sutra bubble with the link in it", () => {
  const session = {id: "cs_0123456789ab", node_id: "web", kind: "department", title: "Web", writable: true, status: "active"};
  const message = {id: 31, session_id: session.id, role: "agent", who: "sutra", kind: "card", text: "", state: "ok", at: "2026-11-04T10:00:00Z", card: card()};
  const items = ChatView.transcriptItems(session, [message], {deptName: "Web"});
  assert.equal(items.length, 1);
  assert.equal(items[0].key, "m31");
  wellFormed(items[0].html);
  assert.match(items[0].html, /^<div class="nmsg sb team" data-id="31" data-who="sutra" data-kind="card" data-state="ok"><small>Sutra<\/small><div class="ncard c-deliverable"/);
  assert.ok(items[0].html.includes('data-act="open-team" href="' + HREF + '"'));
});
