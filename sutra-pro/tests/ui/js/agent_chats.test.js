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

// ---- usage by purpose (D159): "judging N calls, $x" and "questions N calls, $x" under an agent's usage ---------------------------------------------------

const BY = {agent_turn: {calls: 2, usd: 0.02}, judge: {calls: 1, usd: 0.02}, plan: {calls: 1, usd: null}, agent_chat: {calls: 1, usd: 0.0625}};
const lines = usage => AC.purposeLines(usage).map(l => l.text);

test("judging adds the late judge's two purposes, plan and judge; questions is the answers in the agent's chat; the agent's own turns are neither", () => {
  assert.deepEqual(lines({calls: 5, usd: 0.1025, by_purpose: BY}), ["judging 2 calls, $0.02", "questions 1 call, $0.06"]);
  assert.deepEqual(AC.purposeLines({by_purpose: BY}).map(l => [l.key, l.calls, l.usd]), [["judging", 2, 0.02], ["questions", 1, 0.0625]]);
  assert.deepEqual(lines({by_purpose: {judge: {calls: 3, usd: 0.5}, plan: {calls: 2, usd: 0.25}}}), ["judging 5 calls, $0.75"]);        // dollars add up across the two purposes
  assert.deepEqual(lines({by_purpose: {plan: {calls: 1, usd: 0.004}}}), ["judging 1 call, $0.0040"]);                              // the words of usageWords: a fraction of a cent has four places
  assert.deepEqual(lines({by_purpose: {agent_turn: {calls: 4, usd: 1}, summary: {calls: 1, usd: 1}, change: {calls: 1, usd: 1}}}), []);
  assert.deepEqual(AC.purposeLines({by_purpose: {agent_chat: {calls: 2, usd: 0.04}, judge: {calls: 1, usd: null}}}).map(l => l.key), ["judging", "questions"]);   // always in this order
});

test("a line is drawn only when its calls are above zero, and a call with no price says the calls and no dollars", () => {
  assert.deepEqual(lines({by_purpose: {judge: {calls: 0, usd: 0}, agent_chat: {calls: 0, usd: null}}}), []);
  assert.deepEqual(lines({by_purpose: {judge: {calls: 0, usd: 0}, plan: {calls: 2, usd: 0.1}}}), ["judging 2 calls, $0.10"]);          // a purpose with no calls adds nothing
  assert.deepEqual(lines({by_purpose: {judge: {calls: 2, usd: null}}}), ["judging 2 calls"]);                                       // Codex reports tokens only
  assert.deepEqual(lines({by_purpose: {judge: {calls: 2, usd: 0}}}), ["judging 2 calls"]);
  assert.deepEqual(lines({by_purpose: {judge: {calls: 1, usd: null}, plan: {calls: 1, usd: 0.3}}}), ["judging 2 calls, $0.30"]);     // one priced part is enough for a figure
});

test("an older server's row, an empty mapping and anything that is not a mapping of counts draw nothing", () => {
  for (const usage of [undefined, null, {}, {calls: 3, usd: 0.04}, {by_purpose: {}}, {by_purpose: null}, {by_purpose: []}, {by_purpose: "judge"}, "x", 5]) {
    assert.deepEqual(AC.purposeLines(usage), [], JSON.stringify(usage));
  }
  const odd = {by_purpose: {judge: null, plan: "2", agent_chat: {calls: "1", usd: 1}}};
  assert.deepEqual(AC.purposeLines(odd), []);
  assert.deepEqual(lines({by_purpose: {judge: {calls: -3, usd: 1}, plan: {calls: NaN, usd: 1}, agent_chat: {calls: Infinity, usd: 1}}}), []);
  assert.deepEqual(lines({by_purpose: {judge: {calls: 2, usd: "0.5"}}}), ["judging 2 calls"]);                                     // a price that is not a number is no price
  assert.deepEqual(lines({by_purpose: JSON.parse('{"__proto__": {"calls": 9}, "constructor": {"calls": 9}}')}), []);                 // only the three words are read
});

test("the list puts the two lines under the agent's usage, in one place, and says what each means", () => {
  const html = AC.list([row({usage: {calls: 5, usd: 0.1025, tokens_in: 605, tokens_out: 121, by_purpose: BY}})]);
  assert.match(html, /<span class="agent-usage">5 calls, \$0\.10<\/span><span class="agent-purposes">/);
  assert.match(html, /<span class="agent-purpose" data-line="judging" title="[^"]+">judging 2 calls, \$0\.02<\/span><span class="agent-purpose" data-line="questions" title="[^"]+">questions 1 call, \$0\.06<\/span><\/span><\/li>/);
  assert.equal((html.match(/class="agent-purposes"/g) || []).length, 1);
  assert.ok(html.indexOf('class="agent-usage"') < html.indexOf('class="agent-purposes"') && html.indexOf('class="agent-purposes"') < html.indexOf("</li>"));
});

test("an agent with no judging and no questions has no line, whether the server knows by_purpose or not", () => {
  for (const usage of [{calls: 3, usd: 0.04, tokens_in: 100, tokens_out: 20}, {calls: 3, usd: 0.04, by_purpose: {agent_turn: {calls: 3, usd: 0.04}}}, {calls: 0, usd: null, by_purpose: {}}]) {
    const html = AC.list([row({usage})]);
    assert.doesNotMatch(html, /agent-purpose|judging|questions/);
  }
  assert.match(AC.list([row({usage: {calls: 3, usd: 0.04}})]), /3 calls, \$0\.04/);                                                // the usage line is as it was
  const onlyQuestions = AC.list([row({usage: {calls: 1, usd: 0.02, by_purpose: {agent_chat: {calls: 1, usd: 0.02}}}})]);
  assert.match(onlyQuestions, /data-line="questions"/);
  assert.doesNotMatch(onlyQuestions, /data-line="judging"/);
});

test("a past run's row and a workflow's row draw their lines as a live function's does, and nothing from the mapping's keys reaches the markup", () => {
  const past = AC.list([row({status: "archived", live: false, state: "filed", usage: {calls: 4, usd: 0.1, by_purpose: {judge: {calls: 1, usd: 0.05}}}})]);
  assert.match(past, /data-state="past"[\s\S]*judging 1 call, \$0\.05/);
  const step = AC.list([row({agent: "W-1", label: "Menu page", kind: "step", usage: {calls: 2, usd: 0.02, by_purpose: {judge: {calls: 1, usd: 0.01}}}})]);
  assert.match(step, /<h4 class="agents-h">Workflows<\/h4>[\s\S]*judging 1 call, \$0\.01/);
  const hostile = AC.list([row({usage: {calls: 3, usd: 1, by_purpose: {'<img src=x onerror="alert(1)">': {calls: 3, usd: 1}, judge: {calls: 1, usd: 0.01}}}})]);
  assert.doesNotMatch(hostile, /<img|onerror/);
  assert.match(hostile, /judging 1 call, \$0\.01/);
});

// ---- Ask: a question to a function, beside the note (J2 sync 4, D147 and D148) -----------------------------------------------------------------

test("a function's box shows the note by default and offers the Ask mode; a step's chat keeps the note box as it was", () => {
  const plain = AC.noteBox({agent: "audit", label: "Audit", live: true});
  assert.doesNotMatch(plain, /box-mode|ccmode/);
  assert.equal(AC.noteBox({label: "Audit", live: true, ask: false}), plain);
  const html = AC.noteBox({agent: "audit", label: "Audit", live: true, ask: true});
  assert.match(html, /^<div class="ccmode nboxmode" role="group" aria-label="What to send to Audit">/);
  assert.match(html, /<button type="button" class="ccmode-opt on" data-act="box-mode" data-mode="note" aria-pressed="true">Note<\/button>/);
  assert.match(html, /<button type="button" class="ccmode-opt" data-act="box-mode" data-mode="ask" aria-pressed="false">Ask<\/button>/);
  assert.match(html, /<label class="nnote-l">Note to Audit<\/label>/);
  assert.match(html, /data-act="steer">Send note<\/button>/);
  assert.doesNotMatch(html, /data-act="ask"/);
});

test("the Ask mode is a question box that names the function, says where the answer comes from and sends with Ask", () => {
  const html = AC.noteBox({label: "Audit", live: true, ask: true, mode: "ask"});
  assert.match(html, /<button type="button" class="ccmode-opt" data-act="box-mode" data-mode="note" aria-pressed="false">Note<\/button>/);
  assert.match(html, /<button type="button" class="ccmode-opt on" data-act="box-mode" data-mode="ask" aria-pressed="true">Ask<\/button>/);
  assert.match(html, /<label class="nnote-l">Ask Audit<\/label>/);
  assert.match(html, /<textarea class="nask-text" rows="2" maxlength="2000" aria-label="Ask Audit" placeholder="Ask Audit about this run"><\/textarea>/);
  assert.match(html, /<button type="button" class="send" data-act="ask">Ask<\/button>/);
  assert.match(html, /Audit answers from this run's records and cannot change the run\. The question and the answer stay in this chat\./);
  assert.doesNotMatch(html, /data-act="steer"|Send note/);
});

test("while the answer is awaited the box says so and is disabled; what the answer's note said stays under it", () => {
  const waiting = AC.noteBox({label: "Audit", live: true, ask: true, mode: "ask", asking: true});
  assert.match(waiting, /<small class="nnote-help nask-wait" role="status">Asking Audit…<\/small>/);
  assert.match(waiting, /aria-label="Ask Audit" placeholder="Ask Audit about this run" disabled><\/textarea>/);
  assert.match(waiting, /data-act="ask" disabled>Ask<\/button>/);
  assert.match(waiting, /data-mode="note" aria-pressed="false" disabled>Note<\/button>/);          // the mode cannot change under a question that is out
  assert.doesNotMatch(waiting, /answers from this run's records/);
  const said = AC.noteBox({label: "Audit", live: true, ask: true, mode: "ask", askNote: "No model is connected."});
  assert.match(said, /<small class="nnote-help nask-note" role="status">No model is connected\.<\/small>/);
  assert.doesNotMatch(AC.noteBox({label: "Audit", live: true, ask: true, mode: "ask"}), /nask-note/);
});

test("a run that is over has no note and no switch, only the Ask box, and says why", () => {
  const html = AC.noteBox({label: "Audit", live: false, ask: true});
  assert.match(html, /<p class="nnote-over" role="note">That run is over\. Audit can no longer read a note\. You can still ask it about the run\.<\/p>/);
  assert.match(html, /data-act="ask">Ask<\/button>/);
  assert.doesNotMatch(html, /box-mode|data-act="steer"|Send note/);
  const asking = AC.noteBox({label: "Audit", live: false, ask: true, mode: "note", asking: true});
  assert.match(asking, /Asking Audit…/);                                                       // whatever mode was left behind, a finished run asks
  assert.equal(AC.noteBox({label: "Audit", live: false, ask: false}).includes("data-act=\"ask\""), false);
});

test("which mode the box shows: the note unless the function can be asked, the question once the run is over", () => {
  assert.equal(AC.boxMode({ask: false, live: true, mode: "ask"}), "note");
  assert.equal(AC.boxMode({ask: true, live: true}), "note");
  assert.equal(AC.boxMode({ask: true, live: true, mode: "note"}), "note");
  assert.equal(AC.boxMode({ask: true, live: true, mode: "ask"}), "ask");
  assert.equal(AC.boxMode({ask: true, live: false, mode: "note"}), "ask");
  assert.equal(AC.boxMode({ask: false, live: false}), "note");
  assert.equal(AC.boxMode(null), "note");
});

test("a question becomes a POST to /api/ask with the team, the function, the words and the run; nothing for what the server would refuse", () => {
  assert.deepEqual(AC.askRequest("web", "audit", "  Why was W-3 scored low? \n", "j2-20261104-1"),
    {method: "POST", path: "/api/ask?dept=web", body: {who: "audit", q: "Why was W-3 scored low?", run: "j2-20261104-1"}});
  assert.deepEqual(AC.askRequest("we b", "identity", "Who?", "").body, {who: "identity", q: "Who?", run: ""});
  assert.equal(AC.askRequest("we b", "identity", "Who?", "").path, "/api/ask?dept=we%20b");
  assert.equal(AC.askRequest("web", "audit", "   ", "r"), null);
  assert.equal(AC.askRequest("web", "audit", "x".repeat(2001), "r"), null);
  assert.notEqual(AC.askRequest("web", "audit", "x".repeat(2000), "r"), null);
  assert.equal(AC.askRequest("web", "W-1", "Why?", "r"), null);                                       // a builder's chat is not asked
  assert.equal(AC.askRequest("web", "validator", "Why?", "r"), null);                                 // the validator is code
  assert.equal(AC.askRequest("", "audit", "Why?", "r"), null);
  assert.equal(AC.askRequest("web", "audit", null, "r"), null);
  assert.deepEqual(AC.FUNCTIONS, ["identity", "adaptation", "priority", "coordination", "audit"]);
  assert.equal(AC.MAX_ASK, 2000);
});

test("a question that was refused is told in plain words, by what the server answered", () => {
  const e = (status, extra = {}) => Object.assign(new Error(extra.message || "x"), {status}, extra);
  assert.equal(AC.askProblem(e(401, {code: "bad_token"}), "Audit"), "This page was opened without its access token. Reload it from the app.");
  assert.equal(AC.askProblem(e(403, {code: "read_only"}), "Audit"), "This team is read-only, so it cannot be asked.");
  assert.equal(AC.askProblem(e(409, {message: "busy"}), "Audit"), "Audit is still answering. Ask again in a moment.");
  assert.equal(AC.askProblem(e(409), ""), "The agent is still answering. Ask again in a moment.");
  assert.equal(AC.askProblem(e(400, {message: "question too long"}), "Audit"), "A question can be up to 2,000 characters.");
  assert.equal(AC.askProblem(e(400, {message: "not a function"}), "Audit"), "Only the team's five functions can be asked.");
  assert.equal(AC.askProblem(e(400, {message: "something else"}), "Audit"), "That question could not be sent.");
  assert.equal(AC.askProblem(e(0, {code: "network"}), "Audit"), "The app is not responding. Try again in a moment.");
  assert.equal(AC.askProblem(e(500), "Audit"), "Something went wrong. Try again.");
  assert.equal(AC.askProblem(null, "Audit"), "The app is not responding. Try again in a moment.");
});

test("the Ask box escapes every word from the wire", () => {
  const html = AC.noteBox({label: '<img src=x onerror="alert(1)">', live: true, ask: true, mode: "ask", askNote: "<b>no</b>"});
  assert.doesNotMatch(html, /<img|<b>/);
  assert.match(html, /Ask &lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.match(html, /&lt;b&gt;no&lt;\/b&gt;/);
});
