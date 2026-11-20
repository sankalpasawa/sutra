"use strict";
// What the project page draws (MAN-13, D326): the state in words, the cards with their buttons, the graph and the conflict edge, the steps, the spend, "Sutra decided for you", the audit, the
// reason a project stopped, the app-location note; every word from the wire is escaped and none of the page's words is "node", "lease" or "tier".
// Run with: node --test tests/ui/js/project_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const View = require(path.join(JS, "project_view.js"));
const PROJECT = "prj_0123456789ab";
const node = (id, ref, state, over = {}) => Object.assign({id, role: "worker", plan_ref: ref, state, depends_on: [], scope: [], attempt: 1, failure_reason: ""}, over);
const snap = (over = {}) => Object.assign({
  project: {id: PROJECT, title: "A page and a quote", status: "running", failure_policy: "stop_branch", decide_for_me: false, paused: false, budget_credits: 60, stop_reason: ""},
  nodes: [node("nd_a", "a1", "done"), node("nd_b", "a2", "running", {depends_on: ["nd_a"]}), node("nd_c", "a3", "planned")],
  edges: [{from: "nd_a", to: "nd_b", kind: "depends_on"}, {from: "nd_b", to: "nd_c", kind: "conflict"}],
  spend: {calls: 14, usd: null}, cards: [], system_cards: [], last_message_seq: 0}, over);

test("the header says the state in words and offers Pause and Stop while the project is not over", () => {
  const html = View.header(snap());
  assert.match(html, /<h1 class="ptitle">A page and a quote<\/h1>/);
  assert.match(html, /data-status="running">Working</);
  assert.match(html, /data-act="project-pause" data-resume="0">Pause</);
  assert.match(html, /data-act="project-stop"[^>]*>Stop everything</);
  assert.match(html, /stops only the steps after it/);
  const paused = View.header(snap({project: Object.assign(snap().project, {paused: true})}));
  assert.match(paused, /data-resume="1">Continue</);
  const over = View.header(snap({project: Object.assign(snap().project, {status: "done"})}));
  assert.equal(over.includes("<button"), false);
  assert.match(View.header(snap({project: Object.assign(snap().project, {failure_policy: "stop_all", decide_for_me: true})})), /stops the whole project[^<]*Sutra answers the questions it may/);
});

test("a question is a card with a button for each answer, carrying the project, the question and the answer", () => {
  const card = {kind: "tier", approval_id: "ap_0123456789ab", question: "A step wants to read GitHub. Allow it?", options: ["allow_once", "allow_project", "deny", "rm -rf"], item: ""};
  const html = View.cardsHtml(snap({cards: [card]}));
  assert.match(html, /Waiting for you/);
  assert.match(html, /A step wants to read GitHub\. Allow it\?/);
  for (const [d, label] of [["allow_once", "Allow once"], ["allow_project", "Allow for this project"], ["deny", "No"]]) {
    assert.ok(html.includes('data-act="node-answer" data-project="' + PROJECT + '" data-approval="ap_0123456789ab" data-item="" data-decision="' + d + '">' + label + "</button>"), d);
  }
  assert.equal((html.match(/<button/g) || []).length, 3, "a word the page does not know makes no button");
  assert.equal(View.cardsHtml(snap()), "");
});

test("a permission of the computer lists its steps, what it holds up, and Check again and Skip", () => {
  const system = {item: "files_folders", approval_id: "ap_0123456789ab", label: "Your computer must let Sutra into Documents.", steps: ["Open System Settings.", "Allow Sutra Pro."], affects: ["Step a2"], options: ["check_again", "skip"]};
  const html = View.cardsHtml(snap({system_cards: [system]}));
  assert.match(html, /<ol class="psteps"><li>Open System Settings\.<\/li><li>Allow Sutra Pro\.<\/li><\/ol>/);
  assert.match(html, /This holds up: Step a2\. The other steps go on\./);
  assert.ok(html.includes('data-item="files_folders" data-decision="check_again">Check again</button>') && html.includes('data-decision="skip">Skip</button>'));
});

test("the graph has a box for each step but not the planner, a line for each edge and a dashed one for a shared file", () => {
  const html = View.graphHtml(snap({nodes: snap().nodes.concat([{id: "nd_p", role: "planner", state: "done"}])}));
  assert.equal((html.match(/class="pnode"/g) || []).length, 3);
  assert.equal((html.match(/class="pedge"/g) || []).length, 1);
  assert.equal((html.match(/class="pedge pconflict"/g) || []).length, 1);
  assert.match(html, /Step a1/);
  assert.match(html, /A dashed line means two steps use the same files, so one waits for the other\./);
  assert.match(html, /role="img" aria-label="3 steps and the order they run in"/);
  assert.equal(View.graphHtml(snap({nodes: []})), "");
  assert.equal(View.graphHtml(snap({edges: [{from: "nd_a", to: "nd_b", kind: "depends_on"}]})).includes("dashed"), false, "no note when nothing is shared");
});

test("a step shows its state, what it follows, what it shares, its files, why it failed and a stop button only while it works", () => {
  const html = View.stepsHtml(snap({nodes: [node("nd_a", "a1", "failed", {failure_reason: "Your computer did not allow it", scope: ["site/index.html"]}), node("nd_b", "a2", "running", {depends_on: ["nd_a"], attempt: 2})],
    edges: [{from: "nd_a", to: "nd_b", kind: "depends_on"}, {from: "nd_a", to: "nd_b", kind: "conflict"}]}));
  assert.match(html, /Starts after: Step a1/);
  assert.match(html, /Shares files with, so waits for: Step a1/);
  assert.match(html, /May change: site\/index\.html/);
  assert.match(html, /Your computer did not allow it/);
  assert.match(html, /\(try 2\)/);
  assert.equal((html.match(/data-act="node-stop" data-node="nd_b"/g) || []).length, 1);
  assert.equal(html.includes('data-node="nd_a">Stop'), false);
});

test("what it has used is in credits against its own limit", () => {
  assert.match(View.spendHtml(snap()), /<b>14 credits<\/b> of 60 credits/);
  assert.match(View.spendHtml(snap({spend: {calls: 60, usd: 1.5}})), /about \$1\.50[\s\S]*used all of its credits/);
  assert.match(View.spendHtml(snap({spend: {calls: 1, usd: null}, project: Object.assign(snap().project, {budget_credits: 0})})), /<b>1 credit<\/b>(?! of)/);
  assert.equal(View.spendHtml({project: {}, spend: null}), "");
});

test("Sutra decided for you lists each answer with its reason and says what it never does", () => {
  const html = View.decidedHtml([{seq: 1, at: "2026-11-20T10:00:00Z", decision: "yes", why: "reads the team folder"}, {seq: 2, decision: "no", why: "set the work aside"}]);
  assert.match(html, /Sutra decided for you/);
  assert.match(html, /Said yes<\/b> reads the team folder/);
  assert.match(html, /Said no<\/b> set the work aside/);
  assert.match(html, /never raises credits[\s\S]*never answers a question about your computer/);
  assert.equal(View.decidedHtml([]), "");
});

test("the reason a project stopped is shown only when it did not finish", () => {
  const reason = "The computer was closed while a question was open, so it was refused";
  assert.match(View.whyHtml(snap({project: Object.assign(snap().project, {status: "stopped", stop_reason: reason})})), /Why:<\/b> The computer was closed/);
  assert.equal(View.whyHtml(snap({project: Object.assign(snap().project, {status: "running", stop_reason: reason})})), "");
  assert.equal(View.whyHtml(snap()), "");
});

test("the audit reads as plain words, newest first, and an action it does not know says only that something happened", () => {
  const html = View.auditHtml([{seq: 1, at: "2026-11-20T10:00:00Z", action: "project.created", reason: "3 steps"}, {seq: 2, action: "grant.issued", reason: "tiers 0,1"}, {seq: 3, action: "odd.thing", reason: ""}]);
  assert.ok(html.indexOf("Something happened") < html.indexOf("A step was given what it may do") && html.indexOf("A step was given what it may do") < html.indexOf("Project started"));
  assert.match(html, /3 steps/);
  assert.equal(html.includes("odd.thing") || html.includes("tiers 0,1"), false);
  assert.match(View.auditHtml([]), /Nothing yet\./);
});

test("the steps' messages show who said what, clipped", () => {
  const html = View.messagesHtml([{seq: 1, from: {node_id: "nd_a"}, body: {summary: "done with the page"}}, {seq: 2, from: {node_id: "nd_zzz"}, body: "x".repeat(400)}, {seq: 3, from: {}, body: {}}], snap());
  assert.match(html, /<b>Step a1<\/b> done with the page/);
  assert.match(html, /<b>A step<\/b> x{240}\.\.\./);
  assert.match(html, /\(handed in its work\)/);
  assert.equal(View.messagesHtml([], snap()), "");
});

test("the note about the app's place shows only for a place that is not the usual one", () => {
  assert.match(View.noteHtml({usual: false, note: "Sutra Pro is not in your Applications folder."}), /role="note">Sutra Pro is not in your Applications folder\./);
  assert.equal(View.noteHtml({usual: true, note: ""}), "");
  assert.equal(View.noteHtml(null), "");
  assert.equal(View.noteHtml({usual: false, note: ""}), "");
});

test("a hostile word from the wire is escaped everywhere and the page's own words avoid the machine's", () => {
  const evil = "<img src=x onerror=1>";
  const s = snap({project: Object.assign(snap().project, {title: evil, status: "stopped", stop_reason: evil}), nodes: [node("nd_a", evil, "failed", {failure_reason: evil, scope: [evil]})], edges: [],
    cards: [{kind: "tier", approval_id: evil, question: evil, options: ["deny"], item: evil}]});
  const html = View.header(s) + View.whyHtml(s) + View.cardsHtml(s) + View.graphHtml(s) + View.stepsHtml(s) + View.auditHtml([{seq: 1, action: evil, reason: evil}]) + View.messagesHtml([{seq: 1, from: {node_id: "nd_a"}, body: evil}], s);
  assert.equal(html.includes("<img"), false);
  const words = View.page({snapshot: snap(), audit: [], messages: []}, {usual: false, note: "x"}).replace(/<[^>]*>/g, " ") + View.header(snap()).replace(/<[^>]*>/g, " ");
  assert.equal(/\b(node|nodes|lease|tier|gate|grant|conductor|gatekeeper)\b/i.test(words), false, words);
});

test("the page shows Loading, or the error, until there is a snapshot", () => {
  assert.match(View.page({snapshot: null, error: ""}, null), /Loading/);
  assert.match(View.page({snapshot: null, error: "That project is not here any more."}, null), /class="cerr">That project is not here any more\./);
  assert.match(View.page({snapshot: snap(), error: "Sutra could not be reached."}, null), /role="alert">Sutra could not be reached\./);
});

test("every audit action the server writes has words, so the page never prints a machine name", () => {
  const fs = require("node:fs");
  const dir = path.resolve(__dirname, "../../../sutra_app/orchestrator");
  const found = new Set(["node.done", "node.failed", "node.cancelled", "node.retry", "node.restarted", "trigger.project_wall", "trigger.project_usd", "project.stopped", "gate.refused", "approval.denied"]);
  for (const name of fs.readdirSync(dir).filter(f => f.endsWith(".py"))) {
    const text = fs.readFileSync(path.join(dir, name), "utf8");
    for (const m of text.matchAll(/action="([a-z_]+\.[a-z_]+)"/g)) found.add(m[1]);
  }
  const missing = [...found].filter(a => !Object.prototype.hasOwnProperty.call(View.ACTION_WORDS, a));
  assert.deepEqual(missing, []);
  const html = View.auditHtml([...found].map((action, i) => ({seq: i + 1, at: "2026-11-20T10:00:00Z", action, reason: "x"})).concat([{seq: 999, action: "never.heard.of", reason: ""}]));
  const text = html.replace(/<[^>]*>/g, " ");
  assert.equal(/\b[a-z_]+\.[a-z_]+\b/.test(text), false, text);                                         // no dotted machine name on the page
  assert.match(text, /Something happened/);
});

test("reasons that are not plain words are put into words or left out", () => {
  const r = (action, reason) => View.reasonWords({action, reason});
  assert.equal(r("node.leased", "lease 90 s"), "");
  assert.equal(r("node.heartbeat_lost", "silent for 120 s (lease 90 s)"), "");
  assert.equal(r("grant.issued", "tiers 0,1,2,3; folder edit; scope 1 path(s); tools none; commands git_reads; run_tools engine; calls 60; wall 1800s"), "");
  assert.equal(r("gate.decided", "decided_by rule:decide_for_me: tier_4_github: reads GitHub for this project only"), "Sutra answered for you: reads GitHub for this project only");
  assert.equal(r("gate.decided", "decided_by owner: allow_once"), "you answered");
  assert.equal(r("handoff.accepted", "3 file(s), message 4"), "3 files");
  assert.equal(r("handoff.accepted", "1 file(s), message 2"), "1 file");
  assert.equal(r("project.ended", "done_with_open_items"), "Done, but some steps did not finish");
  assert.equal(r("verdict.received", "changes"), "asks for changes");
  assert.equal(r("tool.used", "read a.txt, 2 times"), "read a.txt, 2 times");
  assert.equal(r("scope.unchecked", "git could not say which files this step changed"), "git could not say which files this step changed");
});

test("the reviewer's verdict is shown as its opinion, never as an approval", () => {
  const html = View.messagesHtml([{seq: 1, from: {node_id: "nd_zzz"}, body: {v: 1, verdict: "approve", summary: "Looks right.", needs_work: [], points: []}}, {seq: 2, from: {node_id: "nd_zzz"}, body: {verdict: "changes", summary: "Thin."}}], snap());
  assert.match(html, /gave its opinion: approves of the work\. Looks right\./);
  assert.match(html, /gave its opinion: asks for changes\. Thin\./);
  assert.equal(/approved/i.test(html), false);
});
