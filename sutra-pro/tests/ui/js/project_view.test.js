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
  assert.equal((html.match(/class="pnode"/g) || []).length, 6, "three boxes in each of the two drawings (left to right, top to bottom)");
  assert.equal((html.match(/class="pedge"/g) || []).length, 2);
  assert.equal((html.match(/class="pedge pconflict"/g) || []).length, 2);
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
    for (const m of text.matchAll(/\b_audit\("([a-z_.]+)"/g)) found.add(m[1]);                         // the kill switch's own rows: node.stopped, pause, kill, resume (D383)
    for (const m of text.matchAll(/action="(trigger\.[a-z_]+)"|"(trigger\.project_[a-z]+)"/g)) found.add(m[1] || m[2]);
  }
  const missing = [...found].filter(a => !Object.prototype.hasOwnProperty.call(View.ACTION_WORDS, a));
  assert.deepEqual(missing, []);
  const html = View.auditHtml([...found].map((action, i) => ({seq: i + 1, at: "2026-11-20T10:00:00Z", action, reason: "x"})).concat([{seq: 999, action: "never.heard.of", reason: ""}]));
  const text = html.replace(/<[^>]*>/g, " ");
  assert.equal(/\b[a-z_]+\.[a-z_]+\b/.test(text), false, text);                                         // no dotted machine name on the page
  for (const action of ["node.stopped", "kill", "pause", "resume", "trigger.project_month"]) assert.ok(found.has(action), action + " is one the server writes");
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
  assert.equal(r("tool.used", "read a.txt, 2 times"), "", "a tool row says it all in its heading");
  assert.equal(r("scope.unchecked", "git could not say which files this step changed"), "git could not say which files this step changed");
});

test("the reviewer's verdict is shown as its opinion, never as an approval", () => {
  const html = View.messagesHtml([{seq: 1, from: {node_id: "nd_zzz"}, body: {v: 1, verdict: "approve", summary: "Looks right.", needs_work: [], points: []}}, {seq: 2, from: {node_id: "nd_zzz"}, body: {verdict: "changes", summary: "Thin."}}], snap());
  assert.match(html, /gave its opinion: approves of the work\. Looks right\./);
  assert.match(html, /gave its opinion: asks for changes\. Thin\./);
  assert.equal(/approved/i.test(html), false);
});

test("while a question about files holds the project there is no Continue, and the page says why", () => {          // N-3
  const held = snap({project: Object.assign(snap().project, {paused: true}), cards: [{kind: "scope_violation", approval_id: "ap_0123456789ab", question: "Keep its work?", options: ["allow_once", "deny"], item: ""}]});
  const html = View.header(held);
  assert.equal(html.includes("project-pause"), false);
  assert.match(html, /It is held until you answer the question below about files\. It goes on when you do\./);
  assert.match(html, /data-act="project-stop"/, "Stop everything is still there");
  const ordinary = View.header(snap({project: Object.assign(snap().project, {paused: true})}));
  assert.match(ordinary, /data-resume="1">Continue</);
  assert.equal(ordinary.includes("held until"), false);
});

// ---- the words and the shape of the page after the first real run (D383) -------------------------------------------------------------------

const titled = (id, ref, title, state, over = {}) => node(id, ref, state, Object.assign({title}, over));

test("a step is named by its title, and by Step a1 only when it has none", () => {
  const s = snap({nodes: [titled("nd_a", "a1", "List what each file is for", "done"), titled("nd_b", "a2", "", "running", {depends_on: ["nd_a"]}), titled("nd_c", "a3", "a3", "planned")], edges: [{from: "nd_a", to: "nd_b", kind: "depends_on"}]});
  const steps = View.stepsHtml(s);
  assert.match(steps, /<b>List what each file is for<\/b>/);
  assert.match(steps, /<b>Step a2<\/b>/);
  assert.match(steps, /<b>Step a3<\/b>/, "a title that is only the plan's own label is not a title");
  assert.match(steps, /Starts after: List what each file is for/);
  assert.match(View.graphHtml(s), /<title>List what each file is for<\/title>/);
  assert.equal(/Step a1/.test(steps + View.graphHtml(s)), false);
});

test("the picture is drawn twice and fits a phone: one left to right and one top to bottom, each scaled by its viewBox", () => {
  const html = View.graphHtml(snap());
  assert.equal((html.match(/<svg /g) || []).length, 2);
  assert.match(html, /<svg class="pflow-h" role="img"/);
  assert.match(html, /<svg class="pflow-v" aria-hidden="true"/, "the copy is hidden from a screen reader");
  const vertical = /class="pflow-v"[^>]*viewBox="0 0 (\d+) (\d+)"/.exec(html);
  assert.ok(Number(vertical[1]) <= 150, "a chain of steps is one box wide when it is stacked");
  const css = require("node:fs").readFileSync(path.join(JS, "../css/sutra-project.css"), "utf8");
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.pgraph \.pflow-h \{ display: none/);
  assert.match(css, /\.pgraph svg \{[^}]*max-width: 100%/);
});

test("a stop is said as the owner knows it: you, or the kill switch, never the engine's own words", () => {
  const stopped = why => snap({project: Object.assign(snap().project, {status: "stopped", stop_reason: why}), nodes: [node("nd_a", "a1", "done"), node("nd_b", "a2", "cancelled", {failure_reason: "Stopped: stopped on request"})]});
  const kill = stopped("stopped by the kill switch");
  assert.match(View.whyHtml(kill), /Why:<\/b> The kill switch was used\./);
  assert.match(View.stepsHtml(kill), /<span class="pwhy">The kill switch was used\.<\/span>/);
  assert.equal(/stopped on request/i.test(View.whyHtml(kill) + View.stepsHtml(kill) + View.auditHtml([{seq: 1, action: "node.cancelled", reason: "Stopped: stopped on request"}], kill.project)), false);
  const you = stopped("stopped by you");
  assert.match(View.whyHtml(you), /You stopped it\./);
  assert.match(View.stepsHtml(you), /You stopped it\./);
  assert.match(View.whyHtml(stopped("Your monthly limit was reached, so the project stopped.")), /Your monthly limit was reached, so the project stopped\./);
  assert.match(View.whyHtml(stopped("stopped: the project ran longer than 120 minutes")), /Why:<\/b> The project ran longer than 120 minutes\./);
  assert.match(View.stepsHtml(snap({project: Object.assign(snap().project, {status: "running"}), nodes: [node("nd_a", "a1", "cancelled", {failure_reason: "Stopped: stopped on request"})]})), /It was stopped before it finished\./);
});

test("the audit says what happened in plain words: no 'Something happened', no 'a step used a tool: run'", () => {
  const rows = [{seq: 1, at: "2026-11-20T10:00:00Z", action: "project.stopped", reason: "stopped by the kill switch"}, {seq: 2, action: "node.stopped", reason: "stopped by the kill switch"},
    {seq: 3, action: "kill", reason: "watchdog abort (1 node(s))"}, {seq: 4, action: "kill", reason: "the KILL file was found (0 node(s))"}, {seq: 5, action: "tool.used", reason: "run, 7 times"},
    {seq: 6, action: "tool.used", reason: "read README.md, 2 times"}, {seq: 7, action: "tool.used", reason: "search, 2 times"}, {seq: 8, action: "tool.used", reason: "edit project.md, 1 time"},
    {seq: 9, action: "tool.used", reason: "web, 3 times"}];
  const text = View.auditHtml(rows, {status: "stopped", stop_reason: "stopped by the kill switch"}).replace(/<[^>]*>/g, " ");
  assert.equal(/Something happened|watchdog|KILL file|node\(s\)|stopped by the kill switch/.test(text), false, text);
  assert.match(text, /A step ran commands 7 times/);
  assert.match(text, /A step read README\.md, 2 times/);
  assert.match(text, /A step searched, 2 times/);
  assert.match(text, /A step changed project\.md, once/);
  assert.match(text, /A step used the web 3 times/);
  assert.match(text, /The kill switch was used/);
  assert.match(text, /A step was stopped[\s\S]*The kill switch was used/);
  assert.match(text, /written down when the step ends/, "the tool lines say they carry the time the step ended");
  assert.equal(/written down when the step ends/.test(View.auditHtml([{seq: 1, action: "project.created", reason: ""}], null)), false);
});

test("what the steps said is a plain line about what they produced, never the engine's own words", () => {
  const body = {v: 1, node_id: "nd_a", status: "done", summary: "Done: the project work report is workable. Every done-when item, rubric item and necessary condition passes.",
    files: [{path: "artifacts.json", sha256: "x", bytes: 1}, {path: "report.md", sha256: "x", bytes: 1}, {path: "project.md", sha256: "x", bytes: 1}, {path: "workflows.json", sha256: "x", bytes: 1}], claims: [], needs: []};
  const html = View.messagesHtml([{seq: 1, from: {node_id: "nd_a"}, body}], snap());
  const text = html.replace(/<[^>]*>/g, " ");
  assert.match(text, /Step a1\s+handed in its work\. It made report\.md, project\.md\./);
  assert.equal(/rubric|done-when|necessary condition|artifacts\.json|workflows\.json/.test(text), false, text);
  const open = View.messagesHtml([{seq: 1, from: {node_id: "nd_a"}, body: Object.assign({}, body, {status: "done_with_open_items", files: [], changes: ["a.py", "b.py"]})}], snap());
  assert.match(open.replace(/<[^>]*>/g, " "), /handed in its work, with some things left open\. It changed 2 files in your folder: a\.py, b\.py\./);
  const many = View.messagesHtml([{seq: 1, from: {node_id: "nd_a"}, body: Object.assign({}, body, {files: ["a", "b", "c", "d", "e", "f"].map(n => ({path: n + ".md"}))})}], snap());
  assert.match(many, /It made a\.md, b\.md, c\.md, d\.md and 2 more\./);
  assert.match(View.messagesHtml([{seq: 1, from: {node_id: "nd_a"}, body: {summary: "every rubric item passes"}}], snap()), /\(handed in its work\)/, "an engine sentence on its own is left out");
  assert.match(View.messagesHtml([{seq: 1, from: {node_id: "nd_a"}, body: {summary: "Looks fine to me."}}], snap()), /Looks fine to me\./, "a person's sentence is shown");
});

test("the cost says it is about, includes the planning, and counts the calls that have no price", () => {
  const html = View.spendHtml(snap({spend: {calls: 23, usd: 0.97, unpriced: 2}}));
  assert.match(html, /about \$0\.97/);
  assert.match(html, /include the planning of the project; 2 calls have no price, so it may be a little more\./);
  assert.match(View.spendHtml(snap({spend: {calls: 23, usd: 0.97, unpriced: 1}})), /1 call has no price/);
  assert.equal(/no price/.test(View.spendHtml(snap({spend: {calls: 23, usd: 0.97, unpriced: 0}}))), false);
  assert.equal(/estimate/.test(View.spendHtml(snap({spend: {calls: 1, usd: null}}))), false);
});

test("the reviewer's question is answered with 'Send them back' and 'Leave as it is', every other question keeps its words (D393)", () => {
  const review = {kind: "review", approval_id: "ap_0123456789ab", question: "The reviewer asks for changes to a1. Send them back?", options: ["allow_once", "deny"], item: ""};
  const html = View.cardsHtml(snap({cards: [review]}));
  assert.ok(html.includes('data-decision="allow_once">Send them back</button>') && html.includes('data-decision="deny">Leave as it is</button>'));
  assert.equal(/Allow once|>No</.test(html), false);
  assert.ok(View.cardsHtml(snap({cards: [Object.assign({}, review, {kind: "tier"})]})).includes('data-decision="allow_once">Allow once</button>'));
});
