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

/* ── 9. parseGov — UNFENCED governance blocks ────────────────────────────────
   The fenced path was covered; the unfenced one leaked (verified live 2026-08-19:
   gvBody("Answer.\nINPUT: x\nTYPE: task") kept the block — governance soup in
   replies). The rule under test: a RUN of >= 2 contiguous column-0 lines each
   starting with a known governance key is the block shape and is deleted whole;
   a LONE key-looking line surrounded by prose is a sentence and survives.
   parseGov is extracted the same way the other projections are — the shipped
   bytes, never a copy — and is deliberately self-contained. */

const P = new Function(
  slice('function parseGov', 'return { g, body:')
  + '; return { parseGov, gvBody: function(t){ return parseGov(t).body; } };'
)();

test('9a. a preamble-only response strips to nothing at all', () => {
  assert.strictEqual(P.gvBody(
    'INPUT: user asked for a fix\nTYPE: task\nEXISTING HOME: none\n'
    + 'ROUTE: direct\nFIT CHECK: none\nACTION: fix it\n\n'
    + 'TASK: "fix it"\nDEPTH: 3/5\nEFFORT: 10m\nCOST: ~$1\nIMPACT: small'), '',
    'a response that is ONLY governance has no prose to show');
});

test('9b. answer text plus a trailing unfenced block keeps ONLY the answer', () => {
  /* the exact live-verified leak, pinned */
  assert.strictEqual(P.gvBody('Answer.\nINPUT: x\nTYPE: task'), 'Answer.');
});

test('9c. a single key-looking line inside prose survives — it is a sentence', () => {
  const body = P.gvBody(
    'First paragraph.\nTYPE: the parameter kind matters here\nMore prose after.');
  assert.ok(body.includes('TYPE: the parameter kind matters here'),
    'a lone line merely containing a colon must never be eaten: ' + JSON.stringify(body));
  assert.ok(body.includes('First paragraph.') && body.includes('More prose after.'));
});

test('9d. the fenced path still strips — the old contract is untouched', () => {
  const body = P.gvBody('Answer.\n```\nINPUT: x\nTYPE: task\n```\nMore.');
  assert.ok(!/INPUT:|TYPE:/.test(body), 'the fence leaked: ' + JSON.stringify(body));
  assert.ok(body.includes('Answer.') && body.includes('More.'),
    'the prose around the fence survives');
});

test('9e. chip fields (verb/depth/risk) still parse from the unfenced form', () => {
  const r = P.parseGov(
    '[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]\n'
    + 'INPUT: x\nTYPE: task\nTASK: "fix"\nDEPTH: 3/5\nEFFORT: 5m\nAnswer here.');
  assert.strictEqual(r.g.verb, 'DIRECT', 'the header verb feeds the chip');
  assert.strictEqual(r.g.depth, '3', 'DEPTH is read for the chip BEFORE the strip');
  assert.strictEqual(r.g.risk, 'low');
  assert.strictEqual(r.body, 'Answer here.',
    'and the body is the prose alone — extraction and stripping must not fight');
});

/* ── 10. the roster's colour contract, at the projection level ───────────────
   design-qa 20260819-004318-adf0df, all 8 states: button.trow computed
   rgb(0,0,0) — a <button> does not inherit colour, and the reset omitted it.
   The CSS fix (color:inherit on button.trow) is sufficient ONLY while every
   glyph in a row comes from a field the template wraps in a token-coloured
   home (.tname/.tsum/.tverdict) or renders as an attribute. Pin that shape
   here: a NEW field added to the projection without a declared home is the
   first place the defect re-opens, and this is the level where it shows. */

test('10a. a row exposes text only through fields with a token-coloured render home', () => {
  const rows = agentsOf(FIX.toolRuns);
  assert.ok(rows.length > 0, 'sanity: the real fixture must produce rows');
  /* every key gvAgents emits, mapped to where 05-chat.js renders it */
  const HOME = {
    id: 'attribute (data-agentrow)', state: 'attribute (class)',
    openable: 'attribute (disabled)', kind: '.tname span',
    desc: '.tsum span', verdict: '.tverdict span', ms: '.tverdict span',
  };
  rows.forEach((r, i) => {
    Object.keys(r).forEach(k => {
      assert.ok(k in HOME, 'row ' + i + ' emits field "' + k + '" which has no '
        + 'declared render home — wrap it in a token-coloured element in '
        + '05-chat.js (and extend this map) before shipping it');
    });
  });
});

/* ── 11. the chip's keyboard half, at the projection level ───────────────────
   design-qa 20260819-004318-adf0df rows 9-12: button.gv-chip showed no
   author-defined focus indicator — the one interactive element relying on the
   off-token UA ring. The CSS half (.gv-chip:focus-visible, panel.css) can only
   ever fire if this projection keeps emitting a REAL <button>: regressed to a
   click-bearing <div>, the ring dies silently while the CSS rule stays green.
   gvChipHtml is the shipped bytes via slice(); S/esc/dPath are the
   collaborators it closes over, stubbed at the boundary. */

const C = new Function('S', 'esc', 'dPath',
  slice('function parseGov', 'return { g, body:')
  + slice('function gvChipHtml', 'return `<div class="gv ')
  + '; return gvChipHtml;');
const chip = t => C({ govOpen: {} }, s => String(s == null ? '' : s), r => String(r))(t, 0);

test('11a. the governance chip is a real button in the tab order — the focus ring has an element to land on', () => {
  const html = chip({ uid: 'u1', response: 'Answer.',
                      domain: { name: 'Ops', ref: 'r1' }, confidence: 0.9 });
  assert.ok(/<button class="gv-chip" type="button"/.test(html),
    'the chip must stay a <button type="button">, never a click-bearing div: '
    + JSON.stringify(html.slice(0, 160)));
  assert.ok(!/tabindex\s*=\s*"-1"/.test(html),
    'and it must not be pulled out of the tab order');
});

/* ── 10. governance CAPTURE — nothing escapes, nothing is lost ───────────────
   Founder 2026-08-22: every system block lives under the chip; none may leak
   into the reply. Codex rules: lossless lines; continuation only when indented;
   a column-0 numbered list after a block is the ANSWER. */
const PG = new Function(slice('function parseGov', 'return { g, body:') + '; return parseGov;')();
const PRE = "[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:med]\n" +
  "INPUT: ship it\nTYPE: task\nEXISTING HOME: none\nROUTE: direct\nFIT CHECK: none\nACTION: do it\n\n" +
  "TASK: \"ship\"\nDEPTH: 4/5\nEFFORT: 1h\nCOST: ~$2\nIMPACT: real\n\n" +
  "FLOW: [1] task · [2] CONSTRUCT · [3] 3 steps\n\n" +
  "BLUEPRINT\nDoing: the thing\nSteps:\n  1. first\n     Verify: a\n  2. second\nOutput looks like: x\nVerified by: y\nScale: 1 file\nStops if: z\n\n" +
  "BUILD-LAYER: L1\nACTIVATION-SCOPE: here\nTARGET-PATH: /x\n\n" +
  "PLACEMENT: D0 > D1 Sutra OS > D1.D1 Core | \"Charter\"\n\n" +
  "Here is the real answer.\n\n1. First real point\n2. Second real point\n\n" +
  "TRIAGE: depth_selected=4\nESTIMATE: tokens_est=2000\nACTUAL: tokens=2100\n\n" +
  "`OS: Input Routing (task) > D1 > 3 calls > done`";

test('10a. every block family is captured as a section, in order', () => {
  const r = PG(PRE);
  assert.deepStrictEqual(r.sections.map(x => x.key),
    ['header','routing','depth','flow','blueprint','buildLayer','placement','triage','trace']);
});

test('10b. the body is the reply alone — no governance key survives', () => {
  const r = PG(PRE);
  assert.ok(!/^(INPUT|TYPE|TASK|DEPTH|FLOW|BLUEPRINT|BUILD-LAYER|PLACEMENT|TRIAGE|OS):/m.test(r.body), r.body);
  assert.ok(!/\[INBOUND/.test(r.body), 'the header leaked');
  assert.ok(r.body.startsWith('Here is the real answer.'), r.body.slice(0, 60));
});

test('10c. a column-0 numbered list after governance is the ANSWER, never swallowed', () => {
  const r = PG(PRE);
  assert.ok(r.body.includes('1. First real point') && r.body.includes('2. Second real point'), r.body);
});

test('10d. indented BLUEPRINT steps ARE captured as continuation', () => {
  const bp = PG(PRE).sections.find(x => x.key === 'blueprint');
  assert.ok(bp.lines.includes('  1. first') && bp.lines.includes('     Verify: a'), JSON.stringify(bp.lines));
  assert.ok(bp.lines.includes('Stops if: z'), 'sub-keys at column 0 belong to the blueprint');
});

test('10e. capture is LOSSLESS — lines come back verbatim', () => {
  const r = PG(PRE);
  const all = r.sections.flatMap(x => x.lines).join('\n');
  ['INPUT: ship it', 'COST: ~$2', 'FLOW: [1] task · [2] CONSTRUCT · [3] 3 steps', 'TARGET-PATH: /x',
   'PLACEMENT: D0 > D1 Sutra OS > D1.D1 Core | "Charter"', 'ACTUAL: tokens=2100', '`OS: Input Routing (task) > D1 > 3 calls > done`']
    .forEach(l => assert.ok(all.includes(l), 'lost: ' + l));
});

test('10f. a lone key-looking sentence stays prose (9c still holds)', () => {
  const r = PG('The fix is simple.\nTYPE: the parameter kind matters here, not the name.\nDone.');
  assert.ok(r.body.includes('TYPE: the parameter kind'), r.body);
  assert.strictEqual(r.sections.length, 0);
});

test('10g. single-line markers are governance even alone', () => {
  const r = PG('Answer.\nPLACEMENT: D0 > D1 X | "Y"\nMore answer.');
  assert.strictEqual(r.sections.length, 1); assert.strictEqual(r.sections[0].key, 'placement');
  assert.strictEqual(r.body, 'Answer.\nMore answer.');
});

test('10h. a governance fence is captured whole, markers included; a code fence is not', () => {
  const r = PG('```\nINPUT: x\nTYPE: task\n```\nAnswer.\n```js\nconst a = 1;\n```');
  assert.strictEqual(r.sections.length, 1);
  assert.deepStrictEqual(r.sections[0].lines, ['```', 'INPUT: x', 'TYPE: task', '```']);
  assert.ok(r.body.includes('const a = 1;'), 'the reply\'s own code must survive');
});

test('10i. streaming: an unterminated governance fence is captured, not shown', () => {
  const r = PG('```\nINPUT: partial\nTYPE: ta');
  assert.strictEqual(r.body, '');
  assert.strictEqual(r.sections[0].key, 'routing');
});

test('10j. derived chip fields still parse from the captured form', () => {
  const r = PG(PRE);
  assert.strictEqual(r.g.verb, 'DIRECT'); assert.strictEqual(r.g.depth, '4'); assert.strictEqual(r.g.risk, 'med');
  assert.strictEqual(r.g.leaf, 'D1.D1 Core'); assert.ok(/Input Routing/.test(r.g.trace));
});

test('10k. a preamble with NO answer yields an empty body and full sections', () => {
  const r = PG(PRE.split('Here is the real answer.')[0]);
  assert.strictEqual(r.body, '');
  assert.ok(r.sections.length >= 6);
});

/* ── 11. capture: boxes, the state line, the lowercase trace — and the guards ──
   The founder's 2026-08-23 screenshot: a FENCED ASCII box "+-- FLOW ---+ | [1]
   TYPE: ... |", a bare "Governance state: plugin ..." line and a "route: a > b
   > c" trace all leaked. Captured now -- with codex's over-capture guards. */
const SHOT = "[INBOUND·QUERY · TIMING:now · CHANNEL:in-band · REV:none · RISK:low]\n" +
  "```\n+-- FLOW ------------------------------------------------+\n| Unit:    Respond to greeting                              |\n" +
  "| [1] TYPE: question / cell social-inbound                 |\n| [2] RESOLVE: CONSTRUCT (trivial, no workflow type fits)  |\n" +
  "| [3] STEPS: 1 -> reply                                    |\n+----------------------------------------------------------+\n```\n\n" +
  "Hi. No tool calls this turn — nothing written.\n\n" +
  "Governance state: plugin v2.117.0, findings open=19 critical=0.\n\n" +
  "route: input-routing > D1.D1.D3 Engine Library > 0 nodes > readability gate > 0 files";

test('11a. the founder\'s exact screenshot: box, state line and route all captured; only the greeting remains', () => {
  const r = PG(SHOT);
  assert.strictEqual(r.body, 'Hi. No tool calls this turn — nothing written.', r.body);
  assert.deepStrictEqual(r.sections.map(x => x.key), ['header', 'flow', 'state', 'trace']);
});

test('11b. the box is captured WHOLE and verbatim, fence markers included', () => {
  const fl = PG(SHOT).sections.find(x => x.key === 'flow');
  assert.strictEqual(fl.lines[0], '```'); assert.ok(fl.lines[1].startsWith('+-- FLOW'));
  assert.ok(fl.lines.some(l => l.includes('[2] RESOLVE: CONSTRUCT')));
  assert.strictEqual(fl.lines[fl.lines.length - 1], '```');
});

test('11c. the lowercase route: trace feeds the chip trace field', () => {
  assert.ok(/input-routing > D1\.D1\.D3 Engine Library/.test(PG(SHOT).g.trace));
});

test('11d. GUARD: a code fence with ONE key-looking line is the reply\'s own code', () => {
  const r = PG('Here is the log:\n```\n| line 1 |\n| TYPE: widget |\n| line 3 |\n```');
  assert.strictEqual(r.sections.length, 0);
  assert.ok(r.body.includes('TYPE: widget'));
});

test('11e. GUARD: an unknown box header is not governance', () => {
  const r = PG('```\n+-- RESULTS ----+\n| total: 3      |\n+---------------+\n```');
  assert.strictEqual(r.sections.length, 0);
});

test('11f. GUARD: two keys inside a box ARE governance even without a known header', () => {
  const r = PG('```\n| INPUT: x |\n| TYPE: task |\n```');
  assert.strictEqual(r.sections.length, 1);
});

test('11g. GUARD: prose "route: the bug is here" stays; only a > chain is a trace', () => {
  const r = PG('The fix: route: the bug is here, in the router.\nroute: a > b');
  assert.ok(r.body.includes('route: the bug is here') && r.body.includes('route: a > b'), r.body);
  assert.strictEqual(r.sections.length, 0);
});

test('11h. GUARD: "Governance state:" needs the exact plugin prefix', () => {
  const r = PG('Governance state: messy\nGovernance state: plugin v1, ok');
  assert.ok(r.body.includes('Governance state: messy'));
  assert.strictEqual(r.sections.length, 1); assert.strictEqual(r.sections[0].key, 'state');
});

/* ── 12. sessSummary — the header, deterministically ───────────────────────── */
const SUM = new Function(slice('function gvClean', 'return v;') + slice('function sessSummary', 'return v + (cut') + '; return sessSummary;')();
test('12a. 45 words, then an ellipsis', () => {
  const t = Array.from({ length: 50 }, (_, i) => 'w' + i).join(' ');
  const v = SUM({ turns: [{ text: t }] });
  assert.ok(v.endsWith('…') && v.replace('…', '').split(' ').length === 45);
});
test('12b. a 280-char ceiling catches URL soup that a word cap misses', () => {
  const v = SUM({ turns: [{ text: 'https://' + 'x'.repeat(400) + ' tail' }] });
  assert.ok(v.length <= 281 && v.endsWith('…'), String(v.length));
});
test('12c. fences dropped, whitespace collapsed, short text untouched', () => {
  assert.strictEqual(SUM({ turns: [{ text: 'a\n\n```\ncode\n```\n  b  ' }] }), 'a b');
  assert.strictEqual(SUM({ title: 'just a title' }), 'just a title');
  assert.strictEqual(SUM(null), '');
});

/* ── 13. the refuter's 2026-08-23 pass: over-capture (a reply that LOOKS like
   governance is the reply) and under-capture (governance that leaks). Every
   input below is the refuter's own repro, and every shape rule was checked
   against 5.6k real assistant turns before it was written (survey in the
   commit). The contract stays what it was: body = the reply alone, sections =
   the governance verbatim -- these pin the boundary from both sides. */
const GOV = '[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]\n'
  + 'INPUT: x\nTYPE: question\nROUTE: answer\nFIT CHECK: none\nACTION: reply\n\n';
const keysOf = r => r.sections.map(x => x.key);

/* over-capture: the reply survives */
test('13a. a glossary the reply INTRODUCES ("...meaning:") is the reply, even as a run of routing keys', () => {
  const r = PG(GOV + 'Each line of the routing block has a fixed meaning:\nINPUT: a paraphrase of what you said\n'
    + 'TYPE: one of direction/task/feedback/question\nROUTE: which skill handles it\nACTION: what Claude does next\n\n'
    + 'So ROUTE: is just the dispatch decision.');
  assert.ok(r.body.includes('TYPE: one of direction/task/feedback/question'), r.body);
  assert.ok(r.body.includes('ACTION: what Claude does next') && r.body.includes('So ROUTE: is just'), r.body);
  assert.deepStrictEqual(keysOf(r), ['header', 'routing'], 'the real block is still captured once');
});

test('13b. a plan comparison\'s COST:/IMPACT: pairs keep their figures -- a depth run carries DEPTH:', () => {
  const r = PG(GOV + 'Option A — keep Postgres\nCOST: $40/mo\nIMPACT: no migration work\n\n'
    + 'Option B — move to SQLite\nCOST: $0\nIMPACT: lose concurrent writers\n\nI would pick A.');
  ['COST: $40/mo', 'IMPACT: no migration work', 'COST: $0', 'IMPACT: lose concurrent writers']
    .forEach(l => assert.ok(r.body.includes(l), 'lost: ' + l + ' in ' + JSON.stringify(r.body)));
  assert.ok(!keysOf(r).includes('depth'));
  /* and the real thing, with its DEPTH: line, is still a block */
  assert.deepStrictEqual(keysOf(PG('TASK: "ship"\nDEPTH: 3/5\nCOST: ~$1\n\nAnswer.')), ['depth']);
});

test('13c. a fenced bug-report template with ONE "Steps:" line is the reply\'s own', () => {
  const r = PG(GOV + 'Paste this into the ticket:\n\n```\nTitle: Login button unresponsive\nSteps:\n1. open /login\n'
    + '2. click Sign in\nExpected: redirect to /home\nActual: nothing\n```\n\nAttach the HAR file too.');
  assert.ok(r.body.includes('Steps:') && r.body.includes('Expected: redirect to /home') && r.body.includes('Attach the HAR'), r.body);
  assert.deepStrictEqual(keysOf(r), ['header', 'routing']);
});

test('13d. an UNCLOSED fence with one "Verify:" line does not swallow the rest of the reply', () => {
  const r = PG(GOV + 'Checklist:\n```\nVerify: backups exist\nThen run the migration and\n'
    + 'then tell the team. Here is the actual SQL:\nALTER TABLE t ADD COLUMN c int;');
  assert.ok(r.body.includes('ALTER TABLE t ADD COLUMN c int;') && r.body.includes('Verify: backups exist'), r.body);
  /* while a streaming governance fence is still held back on its first key */
  assert.deepStrictEqual(keysOf(PG('```\nINPUT: partial')), ['routing']);
});

test('13e. a fenced commit template with one uppercase TYPE: key is code -- a run is >= 2, fenced or not', () => {
  const r = PG(GOV + 'Use the team template:\n\n```\nTYPE: fix | feat | chore\nSCOPE: module name\nSUMMARY: one line\n```');
  assert.ok(r.body.includes('TYPE: fix | feat | chore') && r.body.includes('SUMMARY: one line'), r.body);
  assert.deepStrictEqual(keysOf(r), ['header', 'routing']);
  /* the real one-line depth block ("TASK: .. DEPTH: 1/5 .. IMPACT: ..") is still a block */
  assert.deepStrictEqual(keysOf(PG('```\nTASK: "reopen deck"  DEPTH: 1/5  EFFORT: <1 min  COST: ~$0  IMPACT: deck visible\n```\nOk.')), ['depth']);
});

test('13f. a bug report\'s "OS: macOS 14.6" is an environment line, not the trace -- the trace is a " > " chain', () => {
  const r = PG(GOV + 'Please file it with this environment block:\n\nOS: macOS 14.6 (Darwin 23.6.0)\nBrowser: Chrome 128\n'
    + 'Node: 20.11\n\nThe crash is in the renderer.');
  assert.ok(r.body.includes('OS: macOS 14.6 (Darwin 23.6.0)'), r.body);
  assert.strictEqual(r.g.trace, null, 'the chip trace must not be polluted');
  assert.deepStrictEqual(keysOf(r), ['header', 'routing']);
});

test('13g. a breadcrumb "route: Home > Settings > Billing > Invoices" stays; the lowercase trace needs the spec\'s five fields', () => {
  const r = PG(GOV + 'To find the setting:\nroute: Home > Settings > Billing > Invoices\nThen click Export.');
  assert.ok(r.body.includes('route: Home > Settings > Billing > Invoices'), r.body);
  assert.strictEqual(r.g.trace, null);
  assert.ok(/input-routing/.test(PG(SHOT).g.trace), '11c still holds: the five-field route: IS the trace');
});

test('13h. a pump spec\'s FLOW:/PLACEMENT: lines stay -- the markers carry their shape', () => {
  const r = PG(GOV + 'Pump spec:\nFLOW: 3.2 L/min at 2 bar\nPLACEMENT: below the tank outlet, never above\nHEAD: 4 m');
  assert.ok(r.body.includes('FLOW: 3.2 L/min at 2 bar') && r.body.includes('PLACEMENT: below the tank outlet'), r.body);
  assert.deepStrictEqual(keysOf(r), ['header', 'routing']);
  /* the real shapes: a bracketed spine, a D-path, the unresolved form */
  assert.deepStrictEqual(keysOf(PG('FLOW: [1] task · [2] CONSTRUCT\nPLACEMENT: D0 Asawa Inc.\nA.\nPLACEMENT: (domain unresolved; charter: x) proceeding')),
    ['flow', 'placement', 'placement']);
});

test('13i. a box that merely SAYS "DEPTH" over buoy soundings is the reply\'s own box', () => {
  const r = PG(GOV + 'Soundings:\n```\n+-- DEPTH -------+\n| buoy 1 | 3.1 m |\n| buoy 2 | 4.7 m |\n+----------------+\n```');
  assert.ok(r.body.includes('| buoy 1 | 3.1 m |'), r.body);
  assert.deepStrictEqual(keysOf(r), ['header', 'routing']);
});

test('13j. an indented "BLUEPRINT step" inside a diagram fence is not a marker -- only box rows read through their frame', () => {
  const r = PG('```\n   atom open          workflow author\n   BLUEPRINT step     system charter\n```\nProse.');
  assert.strictEqual(r.sections.length, 0);
  assert.ok(r.body.includes('BLUEPRINT step'));
});

/* under-capture: the governance is captured */
test('13k. an UNFENCED "+-- FLOW --+" box is captured whole (133 real turns draw it unfenced)', () => {
  const r = PG('+-- FLOW -----+\n| [1] TYPE: question |\n| [2] RESOLVE: CONSTRUCT |\n| [3] STEPS: 1 -> reply |\n+-------------+\n\nHere is the real answer.');
  assert.strictEqual(r.body, 'Here is the real answer.', r.body);
  assert.deepStrictEqual(keysOf(r), ['flow']);
  assert.strictEqual(r.sections[0].lines.length, 5, 'all five rows, bottom edge included');
  /* and the real "(close)" box whose only evidence is a "[6]" row */
  const c = PG('+-- FLOW (close) ----+\n| Unit:    Connect |\n| [6] CLOSE: ok     |\n+--------------------+\n\nAnswer.');
  assert.strictEqual(c.body, 'Answer.'); assert.deepStrictEqual(keysOf(c), ['flow']);
});

test('13l. a unicode box "╭─ FLOW ─╮ │ [1] TYPE: … │" is a box too, fenced', () => {
  const r = PG('```\n╭─ FLOW ───╮\n│ [1] TYPE: question │\n│ [2] RESOLVE: CONSTRUCT │\n╰──────╯\n```\n\nHere is the real answer.');
  assert.strictEqual(r.body, 'Here is the real answer.', r.body);
  assert.deepStrictEqual(keysOf(r), ['flow']);
});

test('13m. the multi-line FLOW per CLAUDE.md: column-0 "[2]".."[6]" steps continue the block', () => {
  const r = PG('FLOW: [1] task/cell\n[2] FOLLOW core:flow\n[3] read > write > run\n[4] Clear\n[5] execute\n[6] close\n\nHere is the real answer.');
  assert.strictEqual(r.body, 'Here is the real answer.', r.body);
  assert.deepStrictEqual(r.sections[0].lines.length, 6);
});

test('13n. BLUEPRINT with column-0 "- " Steps bullets captures the bullets AND the trailing sub-keys', () => {
  const r = PG('BLUEPRINT\nDoing: the thing\nSteps:\n- first\n  Verify: a\n- second\nOutput looks like: x\nVerified by: y\nScale: 1 file\nStops if: z\n\nHere is the real answer.');
  assert.strictEqual(r.body, 'Here is the real answer.', r.body);
  assert.strictEqual(r.sections[0].lines.length, 10);
  /* 10c still holds: a numbered list after "Stops if:" is the ANSWER, not a Steps list */
  assert.ok(PG('BLUEPRINT\nDoing: x\nStops if: z\n1. First real point').body.includes('1. First real point'));
});

test('13o. bold markdown keys "**INPUT:**" are read through; lines are stored as emitted', () => {
  const r = PG('**INPUT:** ship it\n**TYPE:** task\n**EXISTING HOME:** none\n**ROUTE:** direct\n**FIT CHECK:** none\n**ACTION:** do it\n\nHere is the real answer.');
  assert.strictEqual(r.body, 'Here is the real answer.', r.body);
  assert.deepStrictEqual(keysOf(r), ['routing']);
  assert.strictEqual(r.sections[0].lines[0], '**INPUT:** ship it', 'lossless');
  /* the real "**BLUEPRINT**" + "- Doing:" bullet form and the "## BLUEPRINT" heading form */
  assert.strictEqual(PG('**BLUEPRINT**\n- Doing: run\n- Steps: (1) a (2) b\n- Stops if: err\n\nAnswer.').body, 'Answer.');
  assert.strictEqual(PG('## BLUEPRINT\nDoing: the thing\nSteps:\n  1. first\nStops if: z\n\nAnswer.').body, 'Answer.');
});

test('13p. a header with a field after RISK still feeds the chip and is captured', () => {
  const r = PG('[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low · CELL:C4]\nINPUT: x\nTYPE: task\n\nHere is the real answer.');
  assert.strictEqual(r.body, 'Here is the real answer.', r.body);
  assert.strictEqual(r.g.verb, 'DIRECT'); assert.strictEqual(r.g.risk, 'low');
  assert.deepStrictEqual(keysOf(r), ['header', 'routing']);
});

test('13q. the documented "[STAGE-1-FAIL · CLARIFY · attempt:1/1]" header is a header (10 real turns)', () => {
  const r = PG('[STAGE-1-FAIL · CLARIFY · attempt:1/1]\n\nWhich file did you mean?');
  assert.strictEqual(r.body, 'Which file did you mean?', r.body);
  assert.deepStrictEqual(keysOf(r), ['header']);
  assert.strictEqual(r.g.verb, 'CLARIFY'); assert.strictEqual(r.g.risk, null);
});

/* ── 12d-h. sessSummary hardening (refuter 2026-08-23) ───────────────────── */
const SUM2 = new Function(slice('function gvClean', 'return v;') + slice('function sessSummary', 'return v + (cut') + '; return sessSummary;')();
test('12d. inert: control, bidi and zero-width characters never reach the header', () => {
  const v = SUM2({ turns: [{ text: 'safe‮​\x07 text' }] });
  assert.strictEqual(v, 'safe text');
});
test('12e. a fence-only first prompt falls back to the title, never an empty header', () => {
  assert.strictEqual(SUM2({ title: 'the title', turns: [{ text: '```\ncode only\n```' }] }), 'the title');
});
test('12f. a stray opening fence drops its marker only — the rest of the prompt survives', () => {
  assert.strictEqual(SUM2({ turns: [{ text: 'before\n```\nafter the stray fence' }] }), 'before after the stray fence');
});
test('12g. the character cap counts code points — no lone surrogate at the cut', () => {
  const v = SUM2({ turns: [{ text: '😀'.repeat(300) }] });
  assert.ok(!/[\uD800-\uDFFF](?![\uDC00-\uDFFF])/.test(v.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, '')), 'lone surrogate emitted');
  assert.ok(Array.from(v.replace('…','')).length <= 280);
});
test('12h. odd turns never throw: null turn, non-array turns, non-string text', () => {
  assert.strictEqual(SUM2({ title: 't', turns: [null] }), 't');
  assert.strictEqual(SUM2({ title: 't', turns: 'nope' }), 't');
  assert.strictEqual(SUM2({ title: 't', turns: [{ text: { a: 1 } }] }), 't');
});

/* ── 14. the Output Trace as the spec writes it: a blockquote ──────────────── */
test('14a. "> route: a > b > c > d" (the spec\'s literal shape) is captured, and feeds g.trace', () => {
  const r = PG('Answer.\n\n> route: atom-card floor redo > D1 Sutra OS > 0 tool calls > awaiting founder verdict');
  assert.strictEqual(r.body, 'Answer.');
  assert.deepStrictEqual(r.sections.map(x => x.key), ['trace']);
  assert.ok(/atom-card floor redo > D1 Sutra OS/.test(r.g.trace));
});
test('14b. the founder\'s 2026-08-23 screenshot line, with its left-border prefix, is captured whole', () => {
  const r = PG('Text.\n> route: brainstorming revision > D1 Sutra OS (engine mis-address, noted) > 2 web searches + dual consult + atom 14 > v3.1 committed 496baf6, screenshots sent > awaiting founder verdict');
  assert.strictEqual(r.body, 'Text.');
});
test('14c. GUARD: a quoted sentence with two > signs is not a trace; a bare breadcrumb still keeps the 4-hop guard', () => {
  const r = PG('> route: see a > b > c\nroute: Home > Settings > Billing > Invoices');
  assert.strictEqual(r.sections.length, 0, JSON.stringify(r.sections));
});

/* ── 15. gvHasCapture — the transcript-chip gate (2.117.3) ───────────────────
   The chip on a TRANSCRIPT turn renders only when parseGov actually captured
   something. depth is deliberately outside the gate: its regex matches an
   explanatory list that stays in the body (codex consult 2026-08-24). */
const GHC = new Function(
  slice('function parseGov', 'return { g, body:') +
  '; ' + slice('function gvHasCapture', 'p.g.verb || p.g.risk);') +
  ' return gvHasCapture;')();

test('15a. a fenced routing block is a capture — the gate opens', () => {
  assert.strictEqual(GHC({ response: "```\nINPUT: x\nTYPE: task\nEXISTING HOME: none\nROUTE: r\nFIT CHECK: none\nACTION: y\n```\nAnswer." }), true);
});

test('15b. plain prose is not a capture — the gate stays shut', () => {
  assert.strictEqual(GHC({ response: "A normal answer with nothing structured in it." }), false);
});

test('15c. GUARD: an introduced list mentioning DEPTH stays body-only and does not chip (codex P2)', () => {
  assert.strictEqual(GHC({ response: "The doc defines these terms:\n- DEPTH: 3/5 means thorough\n- COST: an estimate\nThat is all." }), false);
});

test('15d. an empty or missing response never throws and never chips', () => {
  assert.strictEqual(GHC({}), false);
  assert.strictEqual(GHC({ response: "" }), false);
});

/* ─────────────────────────────────────────────────────────────────────────── */
Date.now = realNow;
console.log('\n' + '-'.repeat(60));
console.log('governance projections: ' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
