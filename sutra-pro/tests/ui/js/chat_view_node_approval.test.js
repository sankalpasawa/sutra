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
