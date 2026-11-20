"use strict";
// The card of a multi-agent project's question (D317, `node_approval`): the question in plain words, its answers as buttons that carry the project, the question and the answer, a
// permission card's buttons name the item, and an answered card reads "Answered" with no buttons. Words from the wire are escaped.
// Run with: node --test tests/ui/js/chat_view_node_approval.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatView = require(path.join(path.resolve(__dirname, "../../../sutra_app/ui/static/js"), "chat_view.js"));
const PROJECT = "prj_0123456789ab";
const APPROVAL = "ap_0123456789ab";
const card = (over = {}) => Object.assign({type: "node_approval", project_id: PROJECT, approval_id: APPROVAL, kind: "tier", tier: 4, node_id: "", item: "",
  question: "A step wants to read GitHub. Allow it? If you say no, only that step is cancelled.", options: ["allow_once", "allow_project", "deny"], expires_at: "2026-11-21T10:00:00Z"}, over);

test("an open question shows its words and one button for each answer", () => {
  const html = ChatView.card(card());
  assert.match(html, /^<div class="ncard c-nodeapproval" data-card="node_approval" data-kind="tier"/);
  assert.match(html, /If you say no, only that step is cancelled\./);
  for (const [decision, label] of [["allow_once", "Allow once"], ["allow_project", "Allow for this project"], ["deny", "No"]]) {
    assert.ok(html.includes('data-act="node-answer" data-project="' + PROJECT + '" data-approval="' + APPROVAL + '" data-item="" data-decision="' + decision + '">' + label + "</button>"), decision);
  }
});

test("a permission card has the check again and skip buttons and names the item", () => {
  const html = ChatView.card(card({kind: "system", tier: 2, item: "files_folders", options: ["check_again", "skip"], question: "Your computer must allow something first."}));
  assert.ok(html.includes('data-item="files_folders" data-decision="check_again">Check again</button>') && html.includes('data-decision="skip">Skip</button>'));
});

test("an answered card has no buttons", () => {
  const html = ChatView.card(card(), {answered: true});
  assert.match(html, /data-answered="true"/);
  assert.match(html, /<p class="canswer">Answered<\/p>/);
  assert.equal(html.includes("<button"), false);
});

test("a word the page does not know makes no button and a hostile word is escaped", () => {
  const html = ChatView.card(card({question: "<img src=x onerror=1>", options: ["allow_once", "rm -rf", "<b>"]}));
  assert.equal(html.includes("<img"), false);
  assert.equal((html.match(/<button/g) || []).length, 1);
});

test("an org-chat card message is answered when the server says so (it points at itself)", () => {
  const messages = [{id: 7, kind: "card", role: "agent", who: "sutra", card: card(), answered_by: 7}];
  assert.deepEqual(ChatView.answersOf(messages, {}), {7: ""});
  const html = ChatView.transcript({kind: "org", writable: true}, messages, {answers: ChatView.answersOf(messages, {})});
  assert.match(html, /data-answered="true"/);
});

test("the card links to the project's own page, and only for an id of the project's shape", () => {
  assert.ok(ChatView.card(card()).includes('<a class="plink" href="/p/' + PROJECT + '">Open the project</a>'));
  const hostile = ChatView.card(card({project_id: '"><script>x</script>'}));
  assert.equal(hostile.includes("<script"), false);
  assert.equal(hostile.includes("/p/"), false);
});

const SESSION = {id: "cs_x", node_id: "web", kind: "department", title: "Web", writable: true, status: "active", connector: "claude", note: ""};
const note = text => ({id: 1, session_id: "cs_x", role: "agent", who: "sutra", kind: "note", text, card: null, pause: null, answered_by: null, task_id: null, state: "ok", at: "2026-11-04T10:00:00Z"});

test("a note that ends with a project's address links to the project, and every other note comes out as it always did", () => {          // R6, PB-19
  const linked = ChatView.transcript(SESSION, [note("I stopped the project \u201cA\u201d: why. /p/" + PROJECT)]);
  assert.ok(linked.includes('<a class="plink" href="/p/' + PROJECT + '">Open the project</a>'));
  for (const same of ["a plain note", "see /p/prj_zz and <b>x</b>", "/p/" + PROJECT + "abc", "http://x.example/p/" + PROJECT.toUpperCase()]) {
    const html = ChatView.transcript(SESSION, [note(same)]);
    assert.equal(html.includes("<a class=\"plink\""), false, same);
  }
  assert.equal(ChatView.transcript(SESSION, [note("a plain note")]), ChatView.transcript(SESSION, [note("a plain note")]));
  assert.equal(ChatView.transcript(SESSION, [note("Merged into Web")]).includes("Merged into Web</div>"), true);                       // the flag-off note is the text and nothing else
});

const reply = text => ({id: 2, session_id: "cs_x", role: "agent", who: "sutra", kind: "text", text, card: null, pause: null, answered_by: null, task_id: null, state: "ok", at: "2026-11-04T10:00:00Z"});
const taskCard = over => Object.assign({type: "task", task_id: "tsk_0123456789ab", dept_id: "web", dept_name: "Web", title: "Page", status: "running"}, over || {});

test("a reply that ends with a project's address links to the project, any other reply is as it was (D382)", () => {
  const ORG = Object.assign({}, SESSION, {id: "cs_org", kind: "org", node_id: "", title: "Org"});
  const html = ChatView.transcript(ORG, [reply("I gave this to the Web team. You can follow it here: /p/" + PROJECT)]);
  assert.ok(html.includes('You can follow it here: <a class="plink" href="/p/' + PROJECT + '">Open the project</a>'));
  assert.equal(ChatView.transcript(SESSION, [reply("a model wrote /p/" + PROJECT)]).includes('class="plink"'), false, "a team's own chat never links it (D389)");
  for (const same of ["I gave this to the Web team.", "see /p/prj_zz", "/p/" + PROJECT + "abc"]) {
    assert.equal(ChatView.transcript(ORG, [reply(same)]).includes('class="plink"'), false, same);
  }
});

test("the card of a step of a project links to the project, the card of an ordinary task is unchanged (D382)", () => {
  assert.ok(ChatView.card(taskCard({project_id: PROJECT})).includes('<a class="plink" href="/p/' + PROJECT + '">Open the project</a>'));
  const plain = ChatView.card(taskCard());
  assert.equal(plain.includes("plink"), false);
  assert.equal(ChatView.card(taskCard({project_id: '"><script>'})).includes("<script"), false);
});

test("the reviewer's card says 'Send them back' and 'Leave as it is' (D393)", () => {
  const html = ChatView.card(card({kind: "review", question: "The reviewer asks for changes to a1. Send them back?", options: ["allow_once", "deny"]}));
  assert.ok(html.includes('data-decision="allow_once">Send them back</button>') && html.includes('data-decision="deny">Leave as it is</button>'));
  assert.equal(/Allow once|>No</.test(html), false);
});

test("the done card of a step of a project links to the project and offers no Try again of its own (D394)", () => {
  const done = over => Object.assign({type: "done", task_id: "tsk_0123456789ab", dept_id: "web", dept_name: "Web", title: "Page", status: "crashed", outcome: "The kill switch was used"}, over || {});
  const ctx = {retry: true};
  const linked = ChatView.card(done({project_id: PROJECT}), ctx);
  assert.ok(linked.includes('<a class="plink" href="/p/' + PROJECT + '">Open the project</a>'));
  assert.equal(/data-act="retry/.test(linked), false);
  assert.ok(/data-act="retry/.test(ChatView.card(done(), ctx)), "an ordinary task keeps its Try again");
});
