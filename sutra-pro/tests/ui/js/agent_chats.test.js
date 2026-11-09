"use strict";
// AgentChats (sutra_app/ui/static/js/agent_chats.js): the Agents tab, the owner's note box, the model chip and the live row of an agent's chat
// (agent-sessions design 3.7, D130 to D134). Strings in, strings out; every word from the wire is escaped.
// Run with: node --test tests/ui/js/agent_chats.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const AC = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/agent_chats.js"));

const CLAUDE = {name: "claude", ready: true, model_options: [{slug: "sonnet", label: "Sonnet"}, {slug: "haiku", label: "Haiku"}]};
const eff = (over = {}) => Object.assign({provider: "claude", model: "sonnet", effort: "high", source: "team"}, over);
const row = (over = {}) => Object.assign({
  agent: "audit", label: "Audit", kind: "function", title: "Audit · Menu page", session_id: "cs_aaaaaaaaaaaa", node_id: "web.audit", run_id: "r1", task_id: "tsk_1",
  state: "running", live: true, status: "active", own: null, run_pick: null, effective: eff(), usage: {calls: 3, usd: 0.04, tokens_in: 100, tokens_out: 20}, last_at: "2026-11-04T10:00:00Z"}, over);

test("the words of a choice name the provider, the model by its own name and the effort", () => {
  assert.equal(AC.modelWords(eff(), [CLAUDE]), "Claude Sonnet, high");
  assert.equal(AC.modelWords(eff({model: "opus"})), "Claude opus, high");
  assert.equal(AC.modelWords(eff({model: null, effort: null})), "Claude");
  assert.equal(AC.modelWords({provider: "codex", model: "gpt-5.6-luna", effort: "medium"}), "Codex gpt-5.6-luna, medium");
  assert.equal(AC.modelWords({provider: null}), "");
  assert.equal(AC.modelWords(null), "");
});

test("a chip says what the agent runs on and where that comes from, for each of the four sources", () => {
  const sources = {own: "own choice", run: "this run", team: "the team", default: "default"};
  for (const [source, word] of Object.entries(sources)) {
    const html = AC.chip(eff({source}), [CLAUDE]);
    assert.match(html, new RegExp('data-source="' + source + '"'));
    assert.match(html, new RegExp('<small class="achip-src">' + word + "</small>"));
    assert.equal(AC.sourceWord(source), word);
  }
  assert.deepEqual(["own", "run", "team", "default"].map(AC.sourceFrom), ["your choice", "this run", "the team", "the app's default"]);
  assert.match(AC.chip(null), /no model known yet/);
  assert.equal(AC.sourceWord("whatever"), "");
});

test("the chip of a past run's chat comes from its own record and is empty when it had no choice", () => {
  const html = AC.sessionChip({pinned: "claude", pinned_model: "haiku", pinned_effort: "low"});
  assert.match(html, /Claude haiku, low/);
  assert.match(html, /data-source="own"/);
  assert.equal(AC.sessionChip({pinned: ""}), "");
  assert.equal(AC.sessionChip(null), "");
  assert.equal(AC.isAgent({kind: "function"}) && AC.isAgent({kind: "step"}), true);
  assert.equal(AC.isAgent({kind: "department"}) || AC.isAgent(null), false);
});

test("the list has a row per agent chat: the state, a button that opens it, its chip and its usage; functions and workflows apart", () => {
  const html = AC.list([row(), row({agent: "W-1", label: "Menu page", kind: "step", session_id: "cs_bbbbbbbbbbbb", node_id: "s-1", state: "filed", live: false, usage: {calls: 1, usd: 0.0021}})]);
  assert.match(html, /<h4 class="agents-h">The team<\/h4>/);
  assert.match(html, /<h4 class="agents-h">Workflows<\/h4>/);
  assert.match(html, /data-act="open-agent" data-sid="cs_aaaaaaaaaaaa" data-node="web.audit" data-status="active"/);
  assert.match(html, /<span class="agent-dot" data-state="running"/);
  assert.match(html, /<span class="agent-name">Audit<\/span><span class="agent-state">working<\/span>/);
  assert.match(html, /3 calls, \$0\.04/);
  assert.match(html, /1 call, \$0\.0021/);
  assert.match(html, /<span class="agent-state">done<\/span>/);
});

test("a past run's chat is marked as past and still opens", () => {
  const html = AC.list([row({status: "archived", live: false, state: "filed"})]);
  assert.match(html, /data-status="archived"/);
  assert.match(html, /data-state="past"/);
  assert.match(html, /<span class="agent-state">past run<\/span>/);
});

test("the run the owner chose for the agents without a choice shows once, above the list", () => {
  const html = AC.list([row({run_pick: {provider: "claude", model: "haiku", effort: "low"}})]);
  assert.match(html, /<p class="agents-runpick">For this run: .*Claude haiku, low.*this run/);
  assert.doesNotMatch(AC.list([row()]), /agents-runpick/);
});

test("the run switcher is there for two runs or more, newest first, with the chosen one selected", () => {
  const runs = [{run_id: "r2", status: "running"}, {run_id: "r1", status: "done_with_open_items"}];
  assert.equal(AC.runSwitcher([runs[0]], "r2"), "");
  const first = AC.runSwitcher(runs, "");
  assert.match(first, /<select data-act="agents-run" aria-label="Run">/);
  assert.match(first, /<option value="r2" selected>latest \(running\)<\/option>/);
  assert.match(first, /<option value="r1">r1 \(done with open items\)<\/option>/);
  assert.match(AC.runSwitcher(runs, "r1"), /<option value="r1" selected>/);
  assert.match(AC.list([row()], {runs, run: "r1"}), /agents-run/);
});

test("an empty list, a loading list and an error are plain sentences", () => {
  assert.match(AC.list([], {}), /No agent has a chat yet/);
  assert.match(AC.list([], {loading: true}), /Loading/);
  assert.match(AC.list([row()], {error: "This team has no agents yet."}), /This team has no agents yet\./);
});

test("everything from the wire is escaped", () => {
  const html = AC.list([row({label: '<img src=x onerror="alert(1)">', title: '"><script>', session_id: 'cs_x"y', effective: eff({model: "<b>"})})]);
  assert.doesNotMatch(html, /<img|<script|<b>/);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.doesNotMatch(AC.noteBox({agent: "<i>", live: true}), /<i>/);
  assert.doesNotMatch(AC.liveRow({active: true, text: "<u>x</u>", tool: "<s>"}, "<q>"), /<u>|<s>|<q>/);
});

test("the request for the agents of a team names the run only when one was chosen", () => {
  assert.deepEqual(AC.agentsRequest("web", ""), {method: "GET", path: "/api/teams/web/agents", query: {}});
  assert.deepEqual(AC.agentsRequest("we b", "j2-1"), {method: "GET", path: "/api/teams/we%20b/agents", query: {run: "j2-1"}});
});

test("the note box says who the note is for and when it is read; a run that is over has none", () => {
  const html = AC.noteBox({agent: "audit", label: "Audit", live: true});
  assert.match(html, /<label class="nnote-l">Note to Audit<\/label>/);
  assert.match(html, /<textarea class="nnote-text" rows="2" maxlength="2000" aria-label="Note to Audit" placeholder="Tell Audit what to do differently">/);
  assert.match(html, /data-act="steer">Send note<\/button>/);
  assert.match(html, /Audit reads this at its next step\./);
  assert.match(AC.noteBox({label: "Audit", live: true, busy: true}), /disabled><\/textarea>.*data-act="steer" disabled/);
  const over = AC.noteBox({label: "Audit", live: false});
  assert.match(over, /That run is over\. Audit can no longer read a note\./);
  assert.doesNotMatch(over, /textarea/);
});

test("a note becomes a POST to the steer route, trimmed, or nothing when it is empty or over 2,000 characters", () => {
  assert.deepEqual(AC.steerRequest("cs_aaaaaaaaaaaa", "  check the footer \n"), {method: "POST", path: "/api/chats/cs_aaaaaaaaaaaa/steer", body: {text: "check the footer"}});
  assert.equal(AC.steerRequest("cs_aaaaaaaaaaaa", "   "), null);
  assert.equal(AC.steerRequest("cs_aaaaaaaaaaaa", "x".repeat(2001)), null);
  assert.notEqual(AC.steerRequest("cs_aaaaaaaaaaaa", "x".repeat(2000)), null);
});

test("a live partial replaces the text with the agent's text so far and keeps its tool line; done ends it", () => {
  let state = AC.livePartial(null, {session_id: "s", delta: "Looking at", reset: true, tool: "Read src/app.js"});
  assert.deepEqual(state, {active: true, text: "Looking at", tool: "Read src/app.js"});
  state = AC.livePartial(state, {data: {delta: "Looking at the footer", reset: true}});
  assert.deepEqual(state, {active: true, text: "Looking at the footer", tool: ""});
  state = AC.livePartial(state, {delta: " and more"});                                    // a piece without reset adds to it
  assert.equal(state.text, "Looking at the footer and more");
  assert.deepEqual(AC.livePartial(state, {reset: true, delta: "", done: true}), {active: false, text: "", tool: ""});
  assert.equal(AC.livePartial({active: true, text: "x".repeat(5000), tool: ""}, {delta: "y"}).text.length, 4000);
});

test("the live row shows the tool line and the text; a reply that starts with { is shown as writing its reply", () => {
  assert.equal(AC.liveRow(AC.idle(), "Audit"), "");
  assert.equal(AC.liveRow(null, "Audit"), "");
  const working = AC.liveRow({active: true, text: "Checking\nthe footer", tool: "Read index.html"}, "Audit");
  assert.match(working, /<small>Audit is working…<\/small>/);
  assert.match(working, /<span class="alive-tool">Read index\.html<\/span>/);
  assert.match(working, /Checking<br\/>the footer/);
  const json = AC.liveRow({active: true, text: '{"verdict": "pass", "notes": [', tool: ""}, "Audit");
  assert.match(json, /writing its reply/);
  assert.doesNotMatch(json, /verdict/);
});

test("the usage words are short and leave out nothing that was not spent", () => {
  assert.equal(AC.usageWords({calls: 0}), "");
  assert.equal(AC.usageWords({calls: 1, usd: null}), "1 call");
  assert.equal(AC.usageWords({calls: 12, usd: 1.234}), "12 calls, $1.23");
  assert.equal(AC.usageWords(null), "");
});
