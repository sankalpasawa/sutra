/* Governance / per-turn chat surface — the PURE projections.

   Two levels of test cover this feature on purpose:
     · here          — the projection functions, no DOM, fed by a REAL captured
                       fan-out (tests/fixtures/toolruns-fanout.json)
     · test_panel.js — the rendered DOM, so a correct projection that renders
                       wrong still fails
   A bug that survives both has to be wrong in the same way twice.

   Extracts the REAL functions out of the shipped modules, the same way
   test_charter_filter.js does, so this tests what ships rather than a copy.

   Run: node test_governance.js
*/
const fs = require('fs');
const assert = require('assert');

const PANEL = __dirname + '/static/panel.html';
const html = fs.readFileSync(PANEL, 'utf8');
/* ?v=<token> cache-bust is captured separately and dropped -- reading
   "01-state.js?v=__ASSETVER__" off disk is an ENOENT. */
const refs = [...html.matchAll(/<script src="\/static\/js\/([^"?]+)(?:\?[^"]*)?"><\/script>/g)].map(m => m[1]);
if (!refs.length) throw new Error('panel.html references no /static/js modules -- has the shell changed?');
const script = refs.map(name => fs.readFileSync(__dirname + '/static/js/' + name, 'utf8')).join('\n');

function slice(from, toAnchor) {
  const a = script.indexOf(from);
  if (a < 0) throw new Error('not found in the shipped modules: ' + from);
  const b = script.indexOf('\n}', script.indexOf(toAnchor, a)) + 2;
  return script.slice(a, b);
}

const FIX = JSON.parse(fs.readFileSync(__dirname + '/tests/fixtures/toolruns-fanout.json', 'utf8'));

/* ── harness ─────────────────────────────────────────────────────────────── */
let pass = 0, fail = 0;
function test(name, fn) {
  try { fn(); pass++; console.log('ok   - ' + name); }
  catch (e) { fail++; console.log('FAIL - ' + name); console.log('       ' + (e && e.message)); }
}

/* Frozen clock. gvAgents() measures a RUNNING agent against "now", and a test
   whose expectation moves with the wall clock is not a test. */
const NOW = 1700000600000;
const realNow = Date.now;
Date.now = () => NOW;

const G = new Function(
  slice('function gvClean', 'return v;')
  + slice('function gvLog', 'return out;')
  + slice('function gvAgents', 'return out;')
  + slice('function agentMatch', 'return hits.length === 1 ? hits[0] : null;')
  + '; return { gvClean, gvLog, gvAgents, agentMatch };'
)();

const turn = runs => ({ uid: 't1', toolRuns: runs });
const agentsOf = runs => G.gvAgents(turn(runs));

/* ── 1. the projection, against real captured wire data ──────────────────── */

test('1a. every Agent run in a real fan-out becomes exactly one row', () => {
  const rows = agentsOf(FIX.toolRuns);
  assert.strictEqual(rows.length, 4, 'the fixture holds 4 Agent runs');
});

test('1b. non-agent tool runs are excluded, not renamed', () => {
  const rows = agentsOf(FIX.toolRuns);
  assert.ok(!rows.some(r => /Bash|find|cd /.test(r.kind + r.desc)),
    'a Bash row must not appear in an AGENT roster');
});

test('1c. rows keep wire order — the roster is not sorted behind the operator', () => {
  const rows = agentsOf(FIX.toolRuns);
  const wire = FIX.toolRuns.filter(r => r.name === 'Agent' || r.name === 'Task').map(r => r.id);
  assert.deepStrictEqual(rows.map(r => r.id), wire);
});

test('1d. identity is split out of the composed summary', () => {
  const rows = agentsOf(FIX.toolRuns);
  assert.strictEqual(rows[0].kind, 'Explore');
  assert.strictEqual(rows[0].desc, 'Audit model PRD pages');
});

test('1e. four agents of the SAME type stay distinguishable', () => {
  const rows = agentsOf(FIX.toolRuns);
  assert.strictEqual(new Set(rows.map(r => r.kind)).size, 1, 'same type — that is the real case');
  assert.strictEqual(new Set(rows.map(r => r.desc)).size, 4,
    'the description is the only thing telling them apart, so it must survive');
});

/* ── 2. lifecycle — the same ternary the tool row uses, no second rule ────── */

test('2a. the live agent is the one still running', () => {
  const rows = agentsOf(FIX.toolRuns);
  const live = rows.filter(r => r.state === 'run');
  assert.strictEqual(live.length, 1);
  assert.strictEqual(live[0].verdict, 'running');
});

test('2b. finished agents report done', () => {
  const rows = agentsOf(FIX.toolRuns).filter(r => r.state === 'ok');
  assert.strictEqual(rows.length, 3);
  rows.forEach(r => assert.strictEqual(r.verdict, 'done'));
});

test('2c. ok===false is an error, ok===null is unknown — never conflated', () => {
  const rows = agentsOf([
    { id: 'a', name: 'Agent', summary: 'x: failed one',  running: false, ok: false, startedAt: NOW - 1000 },
    { id: 'b', name: 'Agent', summary: 'x: never said',  running: false, ok: null,  startedAt: NOW - 1000 },
  ]);
  assert.strictEqual(rows[0].state, 'bad');   assert.strictEqual(rows[0].verdict, 'error');
  assert.strictEqual(rows[1].state, 'unk');   assert.strictEqual(rows[1].verdict, 'unknown');
});

test('2d. the verdict is an allowlist, never text off the wire', () => {
  const rows = agentsOf([
    { id: 'a', name: 'Agent', summary: 'x: y', running: false, ok: true, startedAt: NOW - 1000,
      verdict: 'TOTALLY FINE', state: 'ok', output: 'PASSED' },
  ]);
  assert.ok(['running', 'done', 'error', 'unknown'].includes(rows[0].verdict),
    'a wire-supplied verdict must not be able to spoof a status label');
  assert.notStrictEqual(rows[0].verdict, 'TOTALLY FINE');
});

test('2e. elapsed comes from the run, and a running agent measures against now', () => {
  const rows = agentsOf([
    { id: 'a', name: 'Agent', summary: 'x: done one', running: false, ok: true,
      startedAt: NOW - 90000, endedAt: NOW - 30000 },
    { id: 'b', name: 'Agent', summary: 'x: live one', running: true, ok: null, startedAt: NOW - 5000 },
  ]);
  assert.strictEqual(rows[0].ms, 60000, 'a finished agent is endedAt - startedAt');
  assert.strictEqual(rows[1].ms, 5000,  'a running agent is now - startedAt');
});

test('2f. a run with no startedAt reports no elapsed rather than a fake 0', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent', summary: 'x: y', running: true, ok: null }]);
  assert.strictEqual(rows[0].ms, null);
});

/* ── 3. Task is the same thing under its other name ──────────────────────── */

test('3. Task counts as an agent — the tool has had both names', () => {
  const rows = agentsOf([{ id: 'a', name: 'Task', summary: 'Explore: something',
                           running: true, ok: null, startedAt: NOW }]);
  assert.strictEqual(rows.length, 1);
  assert.strictEqual(rows[0].kind, 'Explore');
});

/* ── 4. degrading, not inventing ─────────────────────────────────────────── */

test('4a. a turn with no tool runs produces nothing at all', () => {
  assert.deepStrictEqual(G.gvAgents({ uid: 't', toolRuns: [] }), []);
  assert.deepStrictEqual(G.gvAgents({ uid: 't' }), []);
  assert.deepStrictEqual(G.gvAgents(null), []);
});

test('4b. a turn of ordinary tools produces nothing — no empty roster shell', () => {
  assert.deepStrictEqual(agentsOf([
    { id: 'a', name: 'Read', summary: 'x.md', running: false, ok: true, startedAt: NOW },
    { id: 'b', name: 'Bash', summary: 'ls',   running: false, ok: true, startedAt: NOW },
  ]), []);
});

test('4c. a summary with no colon is all kind, and desc stays empty', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent', summary: 'general-purpose',
                           running: true, ok: null, startedAt: NOW }]);
  assert.strictEqual(rows[0].kind, 'general-purpose');
  assert.strictEqual(rows[0].desc, '');
});

test('4d. a colon INSIDE the description does not re-split the row', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent', summary: 'Explore: fix bug: the sequel',
                           running: true, ok: null, startedAt: NOW }]);
  assert.strictEqual(rows[0].kind, 'Explore');
  assert.strictEqual(rows[0].desc, 'fix bug: the sequel');
});

test('4e. a missing summary yields a stated placeholder, never "undefined"', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent', running: true, ok: null, startedAt: NOW }]);
  assert.strictEqual(rows[0].kind, 'agent');
  assert.strictEqual(rows[0].desc, '');
  assert.ok(!/undefined|null/.test(rows[0].kind + rows[0].desc));
});

/* ── 5. the summary is UNTRUSTED text ────────────────────────────────────────
   It originates in a subagent prompt, so it is attacker-influenced in any
   session that runs untrusted content. esc() stops markup; these stop the rest. */

test('5a. control characters are stripped', () => {
  /* escapes, not literal bytes: a raw control character in this source is
     invisible in review and some editors normalise it away on save */
  const rows = agentsOf([{ id: 'a', name: 'Agent',
    summary: 'Explore: dro\x07p\x00 tab\x1bles', running: true, ok: null, startedAt: NOW }]);
  assert.ok(!/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/.test(rows[0].desc),
    'control chars must not reach the DOM: ' + JSON.stringify(rows[0].desc));
  assert.strictEqual(rows[0].desc, 'drop tables',
    'the printable remainder survives — stripping must not eat the message');
});

test('5g. bidi and zero-width characters are stripped', () => {
  /* RLO can reverse how a row READS without changing what it says — the classic
     trick for making a failure render as something reassuring. Written with
     escapes so the payload is visible to a reviewer. */
  const rows = agentsOf([{ id: 'a', name: 'Agent',
    summary: 'Explore: safe\u202E\u200B evil', running: true, ok: null, startedAt: NOW }]);
  assert.ok(!/[\u200B-\u200F\u2028\u2029\u202A-\u202E\u2066-\u2069\uFEFF]/.test(rows[0].desc),
    'bidi/zero-width must not reach the DOM: ' + JSON.stringify(rows[0].desc));
  assert.strictEqual(rows[0].desc, 'safe evil', 'the readable text still survives');
});

test('5b. newlines cannot turn one row into several lines', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent',
    summary: 'Explore: line one\nline two\r\nline three', running: true, ok: null, startedAt: NOW }]);
  assert.ok(!/[\n\r]/.test(rows[0].desc), 'a row is one line');
  assert.strictEqual(rows[0].desc, 'line one line two line three');
});

test('5c. runs of whitespace collapse — no 400-space indent as a layout attack', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent',
    summary: 'Explore:      ' + ' '.repeat(400) + 'hi', running: true, ok: null, startedAt: NOW }]);
  assert.strictEqual(rows[0].desc, 'hi');
});

test('5d. an enormous summary is capped, and says it was cut', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent',
    summary: 'Explore: ' + 'x'.repeat(50000), running: true, ok: null, startedAt: NOW }]);
  assert.ok(rows[0].desc.length <= 121, 'got ' + rows[0].desc.length);
  assert.ok(rows[0].desc.endsWith('…'), 'a silent truncation reads as the whole story');
});

test('5e. an enormous KIND is capped too — it is the bold column', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent',
    summary: 'y'.repeat(9000) + ': hi', running: true, ok: null, startedAt: NOW }]);
  assert.ok(rows[0].kind.length <= 33, 'got ' + rows[0].kind.length);
});

test('5f. a summary that mimics a verdict cannot become one', () => {
  const rows = agentsOf([{ id: 'a', name: 'Agent',
    summary: 'Explore: done', running: true, ok: null, startedAt: NOW }]);
  assert.strictEqual(rows[0].verdict, 'running',
    'the state comes from the lifecycle, never from what the text says');
});

/* ── 6. the id survives, because the drill-down is keyed on it ───────────── */

test('6a. every row carries the tool_use id that correlates it to a transcript', () => {
  agentsOf(FIX.toolRuns).forEach(r =>
    assert.ok(r.id && /^toolu_/.test(r.id), 'row without a usable id: ' + JSON.stringify(r)));
});

test('6b. a run with no id still renders, but is marked unopenable', () => {
  const rows = agentsOf([{ id: null, name: 'Agent', summary: 'Explore: orphan',
                           running: true, ok: null, startedAt: NOW }]);
  assert.strictEqual(rows.length, 1, 'the work happened; hiding it would be a lie');
  assert.strictEqual(rows[0].id, '');
  assert.strictEqual(rows[0].openable, false, 'nothing to open, so the row must say so');
});

/* ── 8. gvLog — the step log the loader opens into ───────────────────────────
   The rule for this surface is that every line traces to a real toolRuns entry.
   A log that narrates, infers or pads is worse than no log: it reads like a
   record and is not one. */

test('8a. one line per tool run, and nothing else', () => {
  const lines = G.gvLog(turn(FIX.toolRuns));
  assert.strictEqual(lines.length, FIX.toolRuns.length,
    'a line with no source run would be invented');
});

test('8b. a line is the tool name and what it was asked to do', () => {
  const lines = G.gvLog(turn([
    { id: 'a', name: 'Read', summary: 'os/engines/LEDGER.md', running: false, ok: true },
  ]));
  assert.strictEqual(lines[0].text, 'Read · os/engines/LEDGER.md');
});

test('8c. a run with no summary is just its name — no dangling separator', () => {
  const lines = G.gvLog(turn([{ id: 'a', name: 'Read', running: true, ok: null }]));
  assert.strictEqual(lines[0].text, 'Read');
  assert.ok(!/·\s*$/.test(lines[0].text));
});

test('8d. state mirrors the lifecycle, using the same ternary as everywhere else', () => {
  const lines = G.gvLog(turn([
    { id: 'a', name: 'Read', running: true,  ok: null  },
    { id: 'b', name: 'Read', running: false, ok: true  },
    { id: 'c', name: 'Read', running: false, ok: false },
    { id: 'd', name: 'Read', running: false, ok: null  },
  ]));
  assert.deepStrictEqual(lines.map(l => l.state), ['run', 'ok', 'bad', 'unk']);
});

test('8e. a turn that ran nothing has no log at all', () => {
  assert.deepStrictEqual(G.gvLog(turn([])), []);
  assert.deepStrictEqual(G.gvLog({ uid: 't' }), []);
  assert.deepStrictEqual(G.gvLog(null), []);
});

test('8f. a 2000-step turn stays bounded and says what it dropped', () => {
  const many = Array.from({ length: 2000 }, (_, i) => ({
    id: 'i' + i, name: 'Bash', summary: 'step ' + i, running: false, ok: true,
  }));
  const lines = G.gvLog(turn(many));
  assert.strictEqual(lines.length, 61, 'cap of 60 plus one line saying so, got ' + lines.length);
  assert.strictEqual(lines[0].text, '1940 earlier steps not shown');
  assert.ok(lines[lines.length - 1].text.endsWith('step 1999'),
    'it keeps the RECENT steps — those are the ones you opened it to read');
});

test('8g. log text is normalised the same way roster text is', () => {
  const lines = G.gvLog(turn([
    { id: 'a', name: 'Bash', running: true, ok: null,
      summary: 'rm\n-rf  ' + 'x'.repeat(500) },
  ]));
  assert.ok(!/[\n\r]/.test(lines[0].text), 'a log line is one line');
  assert.ok(lines[0].text.length <= 24 + 3 + 97, 'unbounded text: ' + lines[0].text.length);
  assert.ok(lines[0].text.endsWith('…'), 'and it says it was cut');
});

test('8h. a hostile tool NAME is capped too', () => {
  const lines = G.gvLog(turn([
    { id: 'a', name: 'B'.repeat(9000), summary: 'hi', running: true, ok: null },
  ]));
  assert.ok(lines[0].text.length < 60, 'got ' + lines[0].text.length);
});

/* ── 7. agentMatch — joining a roster row to a transcript ────────────────────
   The riskiest part of the feature. The two sides have DIFFERENT keys (tool_use
   id vs transcript filename), so the join is on description + type. Getting it
   wrong opens someone else's transcript, which is worse than opening nothing. */

const AGENTS = [
  { id: 'agent-aa', title: 'Audit model PRD pages',  agent_type: 'Explore' },
  { id: 'agent-bb', title: 'Audit platform pages',   agent_type: 'Explore' },
  { id: 'agent-cc', title: 'Fix the ledger writer',  agent_type: 'general-purpose' },
];

test('7a. an unambiguous row resolves to exactly its transcript', () => {
  assert.strictEqual(G.agentMatch(AGENTS, 'Explore', 'Audit platform pages').id, 'agent-bb');
});

test('7b. type disambiguates two agents with the same title', () => {
  const list = [
    { id: 'agent-x', title: 'same title', agent_type: 'Explore' },
    { id: 'agent-y', title: 'same title', agent_type: 'general-purpose' },
  ];
  assert.strictEqual(G.agentMatch(list, 'general-purpose', 'same title').id, 'agent-y');
});

test('7j. ambiguity on the ROSTER side also resolves to nothing', () => {
  /* The hole an adversarial review found: checking uniqueness only among
     transcripts is not enough. If two rows in the same turn normalise to the
     same key and only ONE transcript is on disk, both rows would confidently
     open it. `peers` is how many rows share this row's key. */
  const one = [{ id: 'agent-x', title: 'same title', agent_type: 'Explore' }];
  assert.strictEqual(G.agentMatch(one, 'Explore', 'same title', 1).id, 'agent-x',
    'a lone row still resolves');
  assert.strictEqual(G.agentMatch(one, 'Explore', 'same title', 2), null,
    'two indistinguishable rows must not both claim the one transcript');
});

test('7c. a genuinely ambiguous pair resolves to NOTHING, not a coin flip', () => {
  const twins = [
    { id: 'agent-x', title: 'same title', agent_type: 'Explore' },
    { id: 'agent-y', title: 'same title', agent_type: 'Explore' },
  ];
  assert.strictEqual(G.agentMatch(twins, 'Explore', 'same title'), null,
    'opening one of two identical candidates would be a guess presented as an answer');
});

test('7d. no transcript yet — a running agent — resolves to nothing', () => {
  assert.strictEqual(G.agentMatch(AGENTS, 'Explore', 'Audit something not on disk'), null);
  assert.strictEqual(G.agentMatch([], 'Explore', 'anything'), null);
  assert.strictEqual(G.agentMatch(null, 'Explore', 'anything'), null);
});

test('7e. a row with no description can never match', () => {
  assert.strictEqual(G.agentMatch(AGENTS, 'Explore', ''), null,
    'an empty description would match whichever agent had an empty title');
  assert.strictEqual(G.agentMatch(AGENTS, 'Explore', '   '), null);
});

test('7f. the roster\'s ellipsis does not defeat the join', () => {
  /* the roster caps at 120 and appends "…"; the server caps title at 80 */
  const long = 'x'.repeat(80);
  const list = [{ id: 'agent-z', title: long, agent_type: 'Explore' }];
  assert.strictEqual(G.agentMatch(list, 'Explore', long + '…').id, 'agent-z');
});

test('7g. case and stray whitespace do not defeat the join', () => {
  assert.strictEqual(G.agentMatch(AGENTS, 'explore', '  Audit Model PRD Pages ').id, 'agent-aa');
});

test('7h. an agent the server could not type still matches on title alone', () => {
  const untyped = [{ id: 'agent-q', title: 'Fix the ledger writer', agent_type: '' }];
  assert.strictEqual(G.agentMatch(untyped, 'general-purpose', 'Fix the ledger writer').id, 'agent-q');
});

test('7i. a wrong type never resolves to a same-titled agent', () => {
  assert.strictEqual(G.agentMatch(AGENTS, 'Explore', 'Fix the ledger writer'), null,
    'the ledger agent is general-purpose; matching it here would open the wrong transcript');
});

/* ─────────────────────────────────────────────────────────────────────────── */
Date.now = realNow;
console.log('\n' + '-'.repeat(60));
console.log('governance projections: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
