"use strict";
// ChatView's pointer to a team's own chat (gap package dept-chats): the org chat's "Started <team>: open its chat" line and "<team> has a question for
// you" line (the team_chat card), and the caption on the first line of a team's chat that the org chat passed on (ChatMessageOut.passed_on).
// The chip is a real <button> (keyboard accessible), the team's name and ids are escaped, and no word of the team's own chat is in the card.
// Run with: node --test tests/ui/js/chat_view_teamchat.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const ChatView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/chat_view.js"));

const ORG = {id: "cs_org", node_id: "root", kind: "org", title: "Sutra", writable: true, status: "active"};
const TEAM = {id: "cs_0123456789ab", node_id: "print", kind: "department", title: "Print", writable: true, status: "active"};
const SID = "cs_0123456789ab";
const pointer = (over = {}) => Object.assign({type: "team_chat", node_id: "print", name: "Print", kind: "department", session_id: SID, about: "started"}, over);
const cardMsg = (card, id = 7) => ({id, session_id: "cs_org", role: "agent", who: "sutra", kind: "card", text: "", state: "ok", at: "2026-11-04T10:00:00Z", card});
const line = (over = {}) => Object.assign({id: 3, session_id: SID, role: "user", who: "user", kind: "text", text: "I need a flyer", state: "ok", at: "2026-11-04T10:00:00Z"}, over);

test("a started team is one short line and a chip that carries the team's node and chat", () => {
  const html = ChatView.card(pointer());
  assert.match(html, /^<div class="ncard c-teamchat" data-card="team_chat" data-about="started" data-node="print" data-session="cs_0123456789ab">/);
  assert.match(html, /<span class="cteamlead">Started <b>Print<\/b>:<\/span>/);
  assert.match(html, /<button type="button" class="lbtn chatchip" data-act="open-team-chat" data-node="print" data-session="cs_0123456789ab" aria-label="Open its chat Print">Open its chat<\/button>/);
  assert.doesNotMatch(html, /data-question|data-answered/);
});

test("a question is a pointer too: it names the team and carries the question's message, and none of its words", () => {
  const html = ChatView.card(pointer({about: "question", question_message_id: 41}));
  assert.match(html, /data-about="question"/);
  assert.match(html, /data-question="41"/);
  assert.match(html, /<span class="cteamlead"><b>Print<\/b> has a question for you\.<\/span>/);
  assert.match(html, />Answer in its chat<\/button>/);
  assert.doesNotMatch(html, /canswerbox|data-act="answer|class="opts"/);                      // nothing to answer here: the question is in the team's chat
});

test("an answered question reads so, and the chip stays to read the chat", () => {
  const html = ChatView.card(pointer({about: "question", question_message_id: 41}), {answered: true});
  assert.match(html, /data-answered="true"/);
  assert.match(html, /<b>Print<\/b>'s question was answered\./);
  assert.match(html, />Open its chat<\/button>/);
  assert.doesNotMatch(html, /Answer in its chat/);
  assert.doesNotMatch(ChatView.card(pointer(), {answered: true}), /data-answered/);          // a started line is never "answered"
});

test("the team's name and every id are escaped, and a name with markup is text", () => {
  const evil = pointer({name: '<img src=x onerror=alert(1)>"&', node_id: '"><script>x</script>', session_id: "cs_1\"><b>"});
  const html = ChatView.card(evil);
  assert.doesNotMatch(html, /<img|<script|<b>"/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;&quot;&amp;/);
  assert.match(html, /data-node="&quot;&gt;&lt;script&gt;x&lt;\/script&gt;"/);
});

test("a card without a node has no chip, and one without a session still opens by node", () => {
  assert.doesNotMatch(ChatView.card(pointer({node_id: ""})), /<button/);
  const bare = ChatView.card(pointer({session_id: ""}));
  assert.match(bare, /<button[^>]*data-node="print"/);
  assert.doesNotMatch(bare, /data-session/);
});

test("the transcript draws it as a Sutra card and the chip survives the page's own wrapper", () => {
  const html = ChatView.transcript(ORG, [cardMsg(pointer())], {});
  assert.match(html, /<div class="nmsg sb team" data-id="7" data-who="sutra" data-kind="card" data-state="ok"><small>Sutra<\/small><div class="ncard c-teamchat"/);
  assert.match(html, /data-act="open-team-chat"/);
});

test("a team's first line says it was passed on from the org chat; the org chat's own line and a plain line do not", () => {
  const passed = ChatView.transcript(TEAM, [line({passed_on: 2})], {});
  assert.match(passed, /<div class="nmsg sb me" data-id="3"[^>]*><small class="npassed">Passed on from your chat with Sutra<\/small>I need a flyer<\/div>/);
  assert.doesNotMatch(ChatView.transcript(ORG, [line({session_id: "cs_org", id: 2})], {}), /npassed/);
  assert.doesNotMatch(ChatView.transcript(TEAM, [line({passed_on: null})], {}), /npassed/);
  assert.doesNotMatch(ChatView.transcript(TEAM, [line({passed_on: "2"})], {}), /npassed/);      // only a real message id counts
  assert.doesNotMatch(ChatView.transcript(TEAM, [line({passed_on: 0})], {}), /npassed/);
});

test("the caption never reaches the text: a Retry or an edit sends the words alone", () => {
  assert.equal(ChatView.attachedOf(line({passed_on: 2}).text).text, "I need a flyer");
});

test("a card of an older shape (needs_you) is drawn as it was", () => {
  const html = ChatView.card({type: "needs_you", dept_id: "web", dept_name: "Web", question_message_id: 2, text: "@Requester Name?\n   Option 1: A", options: ["A"]}, {deptSession: SID});
  assert.match(html, /data-card="needs_you"/);
  assert.match(html, /data-act="answer-option"/);
});
