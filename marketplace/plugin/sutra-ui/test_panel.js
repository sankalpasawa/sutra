#!/usr/bin/env node
/*
 * test_panel.js -- pure-logic tests for the <script> inside static/panel.html.
 *
 * WHY THIS EXISTS
 * ---------------
 * Almost all of panel.html's behaviour lives in its single <script>, and that is
 * where the reviewed design-vs-live divergences lived. (The byte-identical
 * <style>/<body> constraint this file used to name has been retired: collapsible
 * and resizable panels need markup and CSS of their own.) Four of those
 * divergences were invisible to the Python suite because they never crossed the
 * wire:
 *
 *   - isSuperseded was a Set built at PARSE time, when CHARTERS was still the
 *     empty array declared at the top of the file. loadAll() replaces that
 *     array seconds later, so the set stayed permanently empty and the
 *     "superseded" pill could never render anywhere.
 *   - simKey() hashed ops only. ORG-010 fires purely from the `base` the
 *     server compares against the file, so two different bases collided on one
 *     cache entry and the second one silently reused the first one's findings.
 *   - blockCodesForMove is the per-hover ring painter -- the only validation
 *     an operator sees while dragging. A regression there mislabels a legal
 *     move as blocked (or worse, a blocked one as legal).
 *   - emptySim().pending was written and never read: 1 write, 0 reads. A
 *     pending simulation therefore rendered as a green "0 open issues" -- an
 *     all-clear the server never sent.
 *
 * HOW
 * ---
 * Extract the <script> body, run it under node's `vm` with a minimal DOM/fetch
 * stub, and assert on the real functions. No test doubles of the logic itself:
 * the code under test is the same bytes the browser loads.
 *
 * fetch() is stubbed to return a promise that NEVER settles. That is
 * deliberate: simulate() then parks in its "pending" branch, which is exactly
 * the state the fourth bug above concerns, and no timer or continuation is
 * left to fire after the assertions finish.
 *
 * Run: node test_panel.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const PANEL = path.join(__dirname, "static", "panel.html");

/* ── 1. load the script exactly as the browser does ─────────────────────────
   panel.html was one 7900-line file with an inline <script>; it is now a shell
   that pulls panel.css and an ORDERED list of /static/js/*.js modules. The
   browser runs those classic scripts in one shared global scope, in source
   order -- so concatenating them in the SAME order the shell lists them
   reproduces exactly what runs, and the whole suite below (which exercises the
   top-level functions) keeps testing the real thing. If the split ever drifts,
   the module list in the shell drifts with it, and this reads that list rather
   than a hardcoded set. */
function loadScript() {
  const html = fs.readFileSync(PANEL, "utf8");
  const refs = [...html.matchAll(/<script src="\/static\/js\/([^"?]+)(?:\?[^"]*)?"><\/script>/g)]
    .map(m => m[1]);   /* strip the ?v=__ASSETVER__ cache-bust query the server fills in */
  assert.ok(refs.length > 0,
    "panel.html references no /static/js modules -- has the shell changed?");
  // No inline <script> should remain: the invariant is now "all logic lives in
  // the modules", so an inline block would be code the browser runs but this
  // harness never sees.
  assert.ok(!/<script>/.test(html),
    "panel.html still has an inline <script> -- logic outside the modules is untested");
  return refs.map(name =>
    fs.readFileSync(path.join(__dirname, "static", "js", name), "utf8")).join("\n");
}

const source = loadScript();

/* ── 2. the smallest DOM that lets the script finish parsing ───────────── */

/* Replaced by tests that mount real elements on document.body. Default is a
   no-op so nothing outside those tests changes behaviour. */
let onNodeRemove = () => {};

function makeNode(tag) {
  const node = {
    tagName: (tag || "div").toUpperCase(),
    innerHTML: "",
    textContent: "",
    value: "",
    disabled: false,
    dataset: {},
    style: {},
    content: null,
    _attrs: {},
    classList: {
      _s: new Set(),
      add(...c) { c.forEach(x => this._s.add(x)); },
      remove(...c) { c.forEach(x => this._s.delete(x)); },
      contains(c) { return this._s.has(c); },
      toggle(c) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); },
    },
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; },
    removeAttribute(k) { delete this._attrs[k]; },
    addEventListener() {},
    removeEventListener() {},
    appendChild(c) { return c; },
    // Body-mounted overlays (#onbHost, #updHost) detach themselves. Routed
    // through a hook so a test can keep a real element registry and observe
    // that the banner is actually GONE, not merely re-rendered empty.
    remove() { onNodeRemove(this); },
    focus() {},
    blur() {},
    setSelectionRange() {},
    scrollTo() {},
    closest() { return null; },
    // elements resolve nothing: every call site in the script already guards
    // with `if (!n) return` or `.forEach` over an empty list.
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  node.content = node;
  return node;
}

const documentStub = {
  documentElement: makeNode("html"),
  createElement: (t) => makeNode(t),
  // document-level lookups DO resolve -- the script wires .rail and
  // #newSession at top level and would throw on null.
  getElementById: () => makeNode("div"),
  querySelector: () => makeNode("div"),
  querySelectorAll: () => [],
  addEventListener() {},
};

let fetchCalls = [];
const sandbox = {
  console,
  document: documentStub,
  themeBtn: makeNode("button"),     // implicit global from the element id
  /* The rail's three section containers. renderRail() addresses them as bare
     identifiers -- the browser creates a global for every element id, and the
     panel relies on it. The sandbox has to provide the same globals or any test
     that reaches render() dies on "navOrg is not defined" for a reason that has
     nothing to do with what it is testing. */
  navOrg: makeNode("div"),
  navChange: makeNode("div"),
  navRuntime: makeNode("div"),
  localStorage: {
    _m: {},
    getItem(k) { return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; },
    setItem(k, v) { this._m[k] = String(v); },
  },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  location: { protocol: "http:", host: "127.0.0.1:7000" },
  innerWidth: 1440,     // clampBrowseW() reads it for the 860px breakpoint
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  WebSocket: function WebSocketStub() { this.readyState = 0; this.send = () => {}; this.close = () => {}; },
  setTimeout, clearTimeout, setInterval, clearInterval,
  /* A NO-OP that never runs the callback, for the same reason fetch never
     settles below: the frame callbacks are pure scroll positioning, and running
     them would leave a continuation firing after the assertions finish. Returns
     a handle so a caller that cancels does not throw. */
  requestAnimationFrame: () => 0,
  cancelAnimationFrame: () => {},
  Date, Math, JSON, Set, Map, Promise, Object, Array, String, Number, Boolean, RegExp, Error,
  // never settles on purpose -- parks simulate() in its pending branch and
  // leaves no continuation running after the assertions.
  fetch: (url, opts) => { fetchCalls.push({ url, opts }); return new Promise(() => {}); },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.WebSocket.CONNECTING = 0;
sandbox.WebSocket.OPEN = 1;

/* Re-export the script's top-level `const`/`let` bindings. In a vm script
   those live in the script's own lexical scope, not on the global object, so
   an epilogue in the SAME scope is the only way to reach them -- and it reads
   the live bindings, not copies. */
const EPILOGUE = `
;globalThis.__T = {
  get DOMAINS(){ return DOMAINS; },  set DOMAINS(v){ DOMAINS = v; },
  get CHARTERS(){ return CHARTERS; }, set CHARTERS(v){ CHARTERS = v; },
  get PLACEMENTS(){ return PLACEMENTS; }, set PLACEMENTS(v){ PLACEMENTS = v; },
  get NOW(){ return NOW; }, set NOW(v){ NOW = v; },
  S, META, isSuperseded, simKey, simulate, emptySim, simNum, invalidateSim,
  blockCodesForMove, isDescendant, railSpec, tok, jac, band, lastRouted, dPath,
  NOT_CHECKED, CONFIDENCE_FLOOR,
  clampBrowseW, browseMax, loadLayout, adoptRealSessions, transcriptTurns,
  ensureTranscript, sessionBody, __renderSrc: String(render),
  checkUpdates, stageInBackground, TITLES, SCREENS,
  chanKey, paletteFor,
  _browseScrollKey, _browseScrollState, _restoreBrowseScroll, dirChip, resumableId,
  fmt, dirPickerAvailable,
  /* TENANTS was exported here. It is a lazy getter, so it kept "passing" after
     the global was deleted -- it would only have thrown the moment a test
     touched it. Removed with the tenant surface it belonged to. */
  get PROVIDERS(){ return PROVIDERS; }, set PROVIDERS(v){ PROVIDERS = v; },
  renderUpdateBanner, stopUpdCountdown, updDesktop, updTick, UPDATE_COUNTDOWN_S,
  /* B1 cadence smoothing: the drain POLICY is pure arithmetic and lives here so
     it can be tested without rAF, which never fires headlessly. */
  /* the per-turn chat surface: the projection is unit-tested in
     test_governance.js, and these two prove the projection actually REACHES
     the DOM -- a correct roster rendered into the wrong place still fails */
  gvAgents, turnResponse, agentMatch, focusKeyOf, patchTurn,
  /* the delegated per-turn click handler + the fold, exported so the live-run
     regressions (dead controls mid-stream; invisible fold on non-real
     sessions) stay pinned */
  turnControlClick, agentsFold, streamBodyHtml, drainStep, _MAX_STEP, _reduceMotion,
  gvChipHtml, routingChart, turnBlock, gvHasCapture, pushPane, MAX_PANES,
  rowMeta, rowWorkspace, workspaceLabel,
  /* Teamsutra seeded chat: the budgeter is pure string assembly, exported so
     tests can prove the 8000-char server cap is never silently exceeded */
  tsBuildSeed, TS_SEED_MAX, openTeamsutraChat,
  /* task.apply card states: the board is where a machine diff meets a human
     click, so the three renders (Apply offered / PR handed off / failure in
     place) are pinned as strings */
  tsCard, tsStatusWords, tsCurrentError, tsParseDiff, tsChangeView, tsStory
};
`;

vm.createContext(sandbox);
new vm.Script(source + EPILOGUE, { filename: "panel.html#script" }).runInContext(sandbox);
const T = sandbox.__T;

/* ── 3. tiny test harness ──────────────────────────────────────────────── */

/* Values built INSIDE the vm realm have that realm's Array/Object prototypes,
   so assert.deepStrictEqual rejects a structurally identical array as "not
   reference-equal" on the prototype. Compare by structure instead -- the
   values under test are plain JSON (arrays of code strings, small objects). */
function deepEq(actual, expected, msg) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  assert.strictEqual(a, b, (msg ? msg + " -- " : "") + "expected " + b + ", got " + a);
}
function isEmptyObject(o) {
  return o != null && typeof o === "object" && Object.keys(o).length === 0;
}

let passed = 0;
const failures = [];
function test(name, fn) {
  try {
    fn();
    passed++;
    console.log("ok   - " + name);
  } catch (e) {
    failures.push({ name, e });
    console.log("FAIL - " + name + "\n       " + (e && e.message ? e.message : e));
  }
}

/* The awaiting variant. test() calls fn() and never awaits it, which is right
   for the ~90 synchronous checks below but silently wrong for an async one: the
   body after the first `await` resumes AFTER later tests have already mutated the
   shared S, so it asserts against another test's state. That is not hypothetical
   -- the update-staging checks below passed only by microtask luck until an
   upstream render() grew one more tick and they began reading a null another test
   had just written. Anything async goes through here, and the runner drives them
   in the async phase, after every sync test has finished touching S. */
async function atest(name, fn) {
  try {
    await fn();
    passed++;
    console.log("ok   - " + name);
  } catch (e) {
    failures.push({ name, e });
    console.log("FAIL - " + name + "\n       " + (e && e.message ? e.message : e));
  }
}


/* ── fixture: a small org that exercises every ring code ───────────────── */

const D = [
  { ref: "r0", name: "Sutra Labs",     parent_ref: null, tenant_id: "T-local", status: "active",  ts_minted_ms: 100 },
  { ref: "r1", name: "Research",       parent_ref: "r0", tenant_id: "T-local", status: "active",  ts_minted_ms: 200 },
  { ref: "r2", name: "Market Intel",   parent_ref: "r1", tenant_id: "T-local", status: "active",  ts_minted_ms: 300 },
  { ref: "r3", name: "Agent Ops",      parent_ref: "r0", tenant_id: "T-local", status: "retired", ts_minted_ms: 400 },
  { ref: "r4", name: "Client Success", parent_ref: null, tenant_id: "T-acme",  status: "active",  ts_minted_ms: 500 },
  { ref: "r5", name: "Research",       parent_ref: "r4", tenant_id: "T-acme",  status: "active",  ts_minted_ms: 600 },
  { ref: "r6", name: "Infrastructure", parent_ref: "r0", tenant_id: "T-local", status: "active",  ts_minted_ms: 700 },
  { ref: "r7", name: "Evaluation",     parent_ref: "r6", tenant_id: "T-local", status: "frozen",  ts_minted_ms: 800 },
  { ref: "r8", name: "Agent Ops",      parent_ref: "r1", tenant_id: "T-local", status: "active",  ts_minted_ms: 900 },
  { ref: "r9", name: "Market Intel",   parent_ref: "r6", tenant_id: "T-local", status: "active",  ts_minted_ms: 1000 },
];
const d = r => D.find(x => x.ref === r);
const codesOf = (src, tgt) => T.blockCodesForMove(d(src), d(tgt)).map(c => c.code).sort();

/* ══════════════════════════════════════════════════════════════════════════
   8. isSuperseded works AFTER CHARTERS is populated
   ══════════════════════════════════════════════════════════════════════════ */

test("8a. isSuperseded is empty-safe before CHARTERS is loaded", () => {
  T.CHARTERS = [];
  assert.strictEqual(T.isSuperseded({ id: "C-1" }), false);
  assert.strictEqual(T.isSuperseded(null), false, "must tolerate a null charter");
  assert.strictEqual(T.isSuperseded(undefined), false);
});

test("8b. isSuperseded detects a supersedes edge once CHARTERS is populated", () => {
  // THE BUG: `new Set(CHARTERS.map(c=>c.supersedes))` evaluated at script-parse
  // time, when CHARTERS was still []. loadAll() reassigns CHARTERS, so a
  // parse-time snapshot stays empty forever and the pill never renders.
  T.CHARTERS = [
    { id: "C-old", title: "Research charter v1", domain_ref: "r1", status: "retired" },
    { id: "C-new", title: "Research charter v2", domain_ref: "r1", status: "active", supersedes: "C-old" },
    { id: "C-solo", title: "Infra charter", domain_ref: "r6", status: "active" },
  ];
  assert.strictEqual(T.isSuperseded({ id: "C-old" }), true,
    "C-old IS superseded by C-new -- reading CHARTERS at CALL time is the fix");
  assert.strictEqual(T.isSuperseded({ id: "C-new" }), false, "the successor is not superseded");
  assert.strictEqual(T.isSuperseded({ id: "C-solo" }), false, "an unreferenced charter is not superseded");
});

test("8c. isSuperseded tracks a LATER reassignment of CHARTERS", () => {
  // the precise failure mode: any precomputed snapshot survives this.
  T.CHARTERS = [{ id: "C-a", status: "active" }];
  assert.strictEqual(T.isSuperseded({ id: "C-a" }), false);
  T.CHARTERS = T.CHARTERS.concat([{ id: "C-b", status: "active", supersedes: "C-a" }]);
  assert.strictEqual(T.isSuperseded({ id: "C-a" }), true,
    "isSuperseded must re-read CHARTERS on every call, never cache it");
  // and a wholesale replacement (what loadAll actually does) too
  T.CHARTERS = [{ id: "C-a", status: "active" }];
  assert.strictEqual(T.isSuperseded({ id: "C-a" }), false,
    "removing the edge must remove the pill");
});

/* ══════════════════════════════════════════════════════════════════════════
   9. simKey includes base
   ══════════════════════════════════════════════════════════════════════════ */

test("9a. two different bases produce different sim cache keys", () => {
  const ops = [{ op: "move", ref: "r2", target: "r0" }];
  T.S.draft.base = { domain_index_lines: 10 };
  const k10 = T.simKey(ops);
  T.S.draft.base = { domain_index_lines: 11 };
  const k11 = T.simKey(ops);
  assert.notStrictEqual(k10, k11,
    "ORG-010 is decided ENTIRELY by `base`; an ops-only key makes two different " +
    "bases share one cache entry and the second silently reuses the first's findings");
  assert.ok(k10.includes("10") && k11.includes("11"), "the base must actually be in the key");
});

test("9b. same ops + same base is a cache HIT (the key is not just a nonce)", () => {
  const ops = [{ op: "move", ref: "r2", target: "r0" }];
  T.S.draft.base = { domain_index_lines: 42 };
  assert.strictEqual(T.simKey(ops), T.simKey(ops.slice()),
    "an identical request must reuse the cache, or every render re-POSTs");
});

test("9c. different ops still produce different keys (base did not mask ops)", () => {
  T.S.draft.base = { domain_index_lines: 42 };
  const a = T.simKey([{ op: "move", ref: "r2", target: "r0" }]);
  const b = T.simKey([{ op: "move", ref: "r2", target: "r6" }]);
  const empty = T.simKey([]);
  assert.notStrictEqual(a, b);
  assert.notStrictEqual(a, empty);
  assert.notStrictEqual(b, empty);
});

test("9d. a null/absent base is a stable key, not a crash", () => {
  T.S.draft.base = null;
  const k1 = T.simKey([]);
  T.S.draft.base = undefined;
  const k2 = T.simKey([]);
  assert.strictEqual(k1, k2, "null and undefined base must normalise to one key");
  T.S.draft.base = {};
  assert.notStrictEqual(T.simKey([]), k1, "an empty-object base is a different fact from no base");
});

/* ══════════════════════════════════════════════════════════════════════════
   10. blockCodesForMove regression -- ORG-006/016/017/018
   ══════════════════════════════════════════════════════════════════════════ */

test("10a. ORG-006: dropping a node onto its own descendant (or itself)", () => {
  T.DOMAINS = D;
  deepEq(codesOf("r1", "r2"), ["ORG-006"],
    "Research onto its own child Market Intel is a cycle");
  deepEq(codesOf("r0", "r2"), ["ORG-006"],
    "the root onto a grandchild is a cycle (isDescendant walks the whole chain)");
  deepEq(codesOf("r1", "r1"), ["ORG-006"],
    "a node onto itself is ORG-006");
});

test("10b. ORG-016: the target is not active", () => {
  T.DOMAINS = D;
  deepEq(codesOf("r1", "r3"), ["ORG-016"], "target retired");
  deepEq(codesOf("r1", "r7"), ["ORG-016"], "target frozen");
  // and the code carries the actual status, not a generic string
  const subj = T.blockCodesForMove(d("r1"), d("r7"))[0].subject;
  assert.ok(/frozen/.test(subj), "ORG-016 must name the status: " + subj);
});

test("10c. ORG-017 is NOT raised client-side: tenancy is removed", () => {
  T.DOMAINS = D;
  // This used to assert ORG-017 ("the move crosses a tenant boundary"). One
  // registry holds one org now, so a client-side cross-tenant preview can only
  // ever be false -- and if it somehow fired it would put the word "tenant" in
  // front of an operator as a finding. The check is gone; what remains is the
  // name-clash code that fires on the same move for a real reason.
  deepEq(codesOf("r1", "r4"), ["ORG-018"],
    "r4 already parents a live 'Research' -> ORG-018 alone");
  deepEq(codesOf("r2", "r4"), [],
    "a differently-stamped target with no name clash is not a finding at all");
});

test("10d. ORG-018: a LIVE sibling already carries that name", () => {
  T.DOMAINS = D;
  deepEq(codesOf("r2", "r6"), ["ORG-018"],
    "r6 already parents a live 'Market Intel'");
  // retired siblings do NOT clash -- a tombstone keeps its ordinal, not its name lock
  deepEq(codesOf("r8", "r0"), [],
    "r0's only other 'Agent Ops' is RETIRED; blocking on it would make a legal " +
    "move look illegal on every hover");
  // ...and the node being dragged never clashes with itself
  deepEq(codesOf("r6", "r0"), [],
    "r6 is already r0's child; it must not count as its own duplicate sibling");
  // the clash is with the TARGET's children, wherever the source came from:
  // r9 ("Market Intel", under r6) onto r1, which already parents r2 ("Market Intel")
  deepEq(codesOf("r9", "r1"), ["ORG-018"],
    "r1 already parents a live 'Market Intel' -- the source's current parent is irrelevant");
  // name comparison is normalised (case + whitespace)
  const spaced = { ref: "rX", name: "  market   INTEL ", parent_ref: "r0", tenant_id: "T-local", status: "active" };
  T.DOMAINS = D.concat([spaced]);
  deepEq(T.blockCodesForMove(spaced, d("r6")).map(c => c.code), ["ORG-018"],
    "ORG-018 normalises case and runs of whitespace before comparing");
  T.DOMAINS = D;
});

test("10e. a legal move produces NO codes (the painter is not stuck on red)", () => {
  T.DOMAINS = D;
  deepEq(codesOf("r2", "r0"), [], "Market Intel -> Sutra Labs is legal");
  deepEq(codesOf("r7", "r1"), [], "Evaluation -> Research is legal (no name clash, active, same tenant)");
  deepEq(codesOf("r5", "r4"), [], "an in-tenant no-op parent is legal");
  deepEq(codesOf("r9", "r0"), [], "Market Intel(r9) -> Sutra Labs is legal");
});

test("10f. every code carries a human subject, never an empty string", () => {
  T.DOMAINS = D;
  [["r1", "r2"], ["r1", "r7"], ["r1", "r4"], ["r2", "r6"]].forEach(([s, t]) => {
    T.blockCodesForMove(d(s), d(t)).forEach(c => {
      assert.ok(/^ORG-\d{3}$/.test(c.code), "bad code shape: " + c.code);
      assert.ok(typeof c.subject === "string" && c.subject.length > 0,
        "ring code " + c.code + " has no subject -- the operator sees a blank tooltip");
      assert.ok(!/undefined|null/.test(c.subject), "subject leaked a placeholder: " + c.subject);
    });
  });
});

/* ══════════════════════════════════════════════════════════════════════════
   11. emptySim().pending is true AND consumers actually branch on it
   ══════════════════════════════════════════════════════════════════════════ */

test("11a. emptySim() reports pending, with no fabricated findings", () => {
  const e = T.emptySim();
  assert.strictEqual(e.pending, true, "an unanswered simulation must say so");
  deepEq(e.findings, [], "pending must never invent findings");
  assert.strictEqual(e.maxDepth, 0);
  assert.strictEqual(e.error, null);
});

test("11b. the source READS .pending, not just writes it (bug was 1 write / 0 reads)", () => {
  const writes = source.match(/\bpending\s*:/g) || [];
  // reads of the flag on a simulation result. ch.pending is the WebSocket
  // channel's own queue -- a different thing entirely -- so it is excluded.
  const reads = (source.match(/\b(\w+)\.pending\b/g) || []).filter(m => !/^ch\./.test(m));
  assert.ok(writes.length > 0, "expected the pending flag to be written somewhere");
  assert.ok(reads.length > 0,
    "emptySim() sets pending:true and NOTHING read it -- a pending simulation " +
    "rendered as a green '0 open issues', an all-clear the server never sent");
  assert.ok(reads.length >= 3,
    "expected several consumers to branch on pending (rail badge, reorg strip, " +
    "health screen); found " + reads.length + ": " + reads.join(", "));
});

test("11c. simNum() -- the single read point -- returns an em-dash while pending", () => {
  assert.strictEqual(T.simNum({ pending: true, error: null }, 7), "—",
    "a number derived from an unanswered simulation must render as unknown");
  assert.strictEqual(T.simNum({ pending: false, error: "boom" }, 7), "—",
    "a FAILED simulation is equally unknown -- never 0");
  assert.strictEqual(T.simNum({ pending: false, error: null }, 7), 7,
    "a real answer must pass straight through");
  assert.strictEqual(T.simNum({ pending: false, error: null }, 0), 0,
    "a genuine 0 must survive -- the fix must not swallow real all-clears");
});

test("11d. a real consumer (railSpec) shows '…' while pending and a count once answered", () => {
  T.DOMAINS = D;
  T.CHARTERS = [];
  T.PLACEMENTS = [];
  T.META.tenant_id = "T-local";
  T.S.draft = { ops: [], base: { domain_index_lines: 7 }, rationale: "",
                plan_origin: "studio-drag", validated_at_ms: null };
  T.invalidateSim();

  const health = () => T.railSpec().change.find(x => x.id === "health");

  // BEFORE the registry is read at all (the tenant gate is up), there is no
  // badge -- not a 0. Absent and "0 open issues" are different claims, and the
  // second one would be about a tenant nobody has loaded yet.
  T.S.loaded = false;
  assert.strictEqual(health().c, undefined,
    "before load the Health badge must be absent, never a green 0");
  const noPost = fetchCalls.length;
  T.railSpec();
  assert.strictEqual(fetchCalls.length, noPost,
    "railSpec must not POST /api/org/simulate before a tenant has been chosen");

  T.S.loaded = true;
  const before = fetchCalls.length;
  assert.strictEqual(health().c, "…",
    "with no answer yet the Health badge must read '…', never a green 0");
  assert.ok(fetchCalls.length > before, "the pending render must have kicked off the real POST");
  assert.ok(fetchCalls[fetchCalls.length - 1].url.indexOf("/api/org/simulate") !== -1);

  // now hand it a real answer through the same cache the fetch would fill
  T.S.simCache[T.simKey([])] = {
    domains2: D.slice(), findings: [{ code: "ORG-008", sev: "warn", subject: "x" }],
    maxDepth: 2, notChecked: [], pending: false, error: null,
  };
  assert.strictEqual(health().c, 1, "an answered simulation must show the real count");

  // and a FAILED one must not look like an all-clear either
  T.S.simCache[T.simKey([])] = {
    domains2: D.slice(), findings: [], maxDepth: 0, notChecked: null,
    pending: false, error: "the simulate request failed",
  };
  assert.strictEqual(health().c, "!",
    "a failed validation must be visibly broken, not silently 0");
});

test("11e. invalidateSim() clears the cache and bumps the generation", () => {
  // a registry mutation (a composer turn writing a placement) changes the
  // findings while ops+base are byte-identical -- the cache key cannot see it.
  T.S.simCache[T.simKey([])] = { findings: [], pending: false, error: null };
  const gen = T.S.simGen;
  T.invalidateSim();
  assert.ok(isEmptyObject(T.S.simCache), "the stale answer must be dropped");
  assert.strictEqual(T.S.simPending.size, 0);
  assert.ok(T.S.simGen > gen, "the generation must advance so in-flight replies are discarded");
});

/* ── extra: the NOT_CHECKED contract the panel promises ────────────────── */

test("12. NOT_CHECKED codes are never presented as passing", () => {
  const codes = T.NOT_CHECKED.map(x => x[0]);
  ["ORG-005", "ORG-011", "ORG-012", "ORG-013", "ORG-014", "ORG-019"].forEach(c =>
    assert.ok(codes.includes(c), c + " must be listed as not-checked, never as a green tick"));
  T.NOT_CHECKED.forEach(([code, reason]) => {
    assert.ok(/^ORG-\d{3}$/.test(code));
    assert.ok(reason && reason.length > 10, code + " needs a real reason, got: " + reason);
  });
});

/* ── 13. a restored pane width must fit the CURRENT window ─────────────── */

/* browseW is persisted. A width dragged out on a wide display came back
   verbatim on a narrow one: the browse pane overflowed .panes, the session
   pane beside it was pushed out of view, and the divider that would undo it
   was itself off-screen. render() has to apply the same ceiling the drag does.
   Observed live at a 980px viewport with a stored 705px width. */
/* browseMax() measures the panes container and its non-browse children, so the
   stub has to answer both. `kinds` is what sits beside the browse pane:
   "pane" = an open session pane (flex-basis 380, shrink 0),
   "collapsed" = a folded one (38), "pdiv" = the divider. */
function stubPanes(width, kinds) {
  const kid = (k) => {
    const n = makeNode("section");
    if (k === "pdiv") { n.classList.add("pdiv"); n.getBoundingClientRect = () => ({ width: 8 }); }
    else if (k === "collapsed") { n.classList.add("pane"); n.classList.add("collapsed"); }
    else n.classList.add("pane");
    return n;
  };
  const kids = (kinds || []).map(kid);
  const browse = makeNode("section");
  browse.classList.add("pane"); browse.classList.add("browse");
  return {
    getBoundingClientRect: () => ({ width }),
    querySelectorAll: () => kids,
    querySelector: (sel) => (sel.indexOf("browse") !== -1 ? browse : null),
    classList: makeNode("div").classList,
  };
}
function withPanes(width, kinds, vw, fn) {
  const prevGet = sandbox.document.getElementById, prevVW = sandbox.innerWidth;
  const panes = stubPanes(width, kinds);
  sandbox.document.getElementById = (id) => (id === "panes" ? panes : makeNode("div"));
  if (vw !== undefined) sandbox.innerWidth = vw;
  try { return fn(); }
  finally { sandbox.document.getElementById = prevGet; sandbox.innerWidth = prevVW; }
}

test("13a. a stored width wider than the window is clamped to fit", () => {
  /* the live regression, to the pixel: a 705px stored width in a 661px panes
     container holding one open session pane and the divider.
     661 - (380 + 8) - 11*2 = 251 */
  withPanes(661, ["pdiv", "pane"], 980, () => {
    assert.strictEqual(T.clampBrowseW(705), 251);
    assert.ok(T.clampBrowseW(705) + 380 + 8 + 22 <= 661,
      "browse + session pane + divider + gaps must fit inside .panes");
  });
});

test("13b. a width that already fits is returned untouched", () => {
  withPanes(1400, ["pdiv", "pane"], 1600, () => {
    assert.strictEqual(T.clampBrowseW(705), 705,
      "clamping a width that fits would move the layout the operator set");
  });
});

test("13c. below the stacking breakpoint the CSS owns the width, not this", () => {
  withPanes(700, ["pdiv", "pane"], 700, () => {
    assert.strictEqual(T.clampBrowseW(705), 705,
      "<=860px the panes stack and .pane's width is overridden -- clamping " +
      "here would corrupt the stored value for no benefit");
  });
});

test("13e. the breakpoint is the VIEWPORT, not the panes container", () => {
  /* Keying the guard off the CONTAINER would read 661 <= 860 and skip the
     clamp at a 980px viewport -- the exact case that overflows. */
  withPanes(661, ["pdiv", "pane"], 980, () => {
    assert.ok(T.clampBrowseW(705) < 705, "the clamp must still apply at vw=980");
  });
});

test("13f. the reserve is the session pane's REAL minimum, not a flat 170", () => {
  /* .pane is `flex:1 0 380px` -- shrink 0. Reserving 170 handed the browse
     pane 491px in a 661px container; the session pane then refused to drop
     below 380 and .panes overflowed by ~245px. */
  withPanes(661, ["pdiv", "pane"], 980, () => {
    assert.ok(T.clampBrowseW(705) <= 661 - 380 - 8 - 22,
      "reserving less than 380 per open session pane reintroduces the overflow");
  });
  // a COLLAPSED neighbour only needs its 38px strip, so more room is available
  const collapsedMax = withPanes(661, ["pdiv", "collapsed"], 980,
    () => T.clampBrowseW(705));
  const openMax = withPanes(661, ["pdiv", "pane"], 980, () => T.clampBrowseW(705));
  assert.ok(collapsedMax > openMax,
    "collapsing the session pane must free width, not be ignored");
});

test("13g. with no session pane open the browse pane may take the whole row", () => {
  withPanes(661, [], 980, () => {
    assert.strictEqual(T.clampBrowseW(705), 661,
      "nothing to reserve for -- the ceiling is the container itself");
  });
});

test("13d. clamping is a render-time view, it never rewrites the stored width", () => {
  T.S.ui.browseW = 705;
  withPanes(661, ["pdiv", "pane"], 980, () => { T.clampBrowseW(T.S.ui.browseW); });
  assert.strictEqual(T.S.ui.browseW, 705,
    "go back to the wide display and the original width must return");
  T.S.ui.browseW = null;
});

/* ── 14. sessions are adopted from the server, never generated ─────────── */

/* seedSessions() used to build sessions by grouping PLACEMENT rows by the
   first path segment of work_ref and titling each group "<segment> — N turns".
   No such session ever existed. adoptRealSessions() is its replacement and
   must copy what the endpoint said and nothing more. */
test("14a. every adopted field is the server's, and turns are NOT invented", () => {
  T.S.sessions = [];
  T.adoptRealSessions([
    { id: "abc-123", title: "fix the parser", project: "-Users-x-repo",
      cwd: "/Users/x/repo", branch: "main", mtime: 1700000000, size: 4096 },
  ]);
  assert.strictEqual(T.S.sessions.length, 1);
  const s0 = T.S.sessions[0];
  assert.strictEqual(s0.id, "abc-123");
  assert.strictEqual(s0.title, "fix the parser");
  assert.strictEqual(s0.size, 4096);
  assert.strictEqual(s0.claude_session, "abc-123",
    "the jsonl filename IS the resumable claude session id");
  assert.strictEqual(s0.real, true);
  assert.strictEqual(s0.local, false);
  deepEq(s0.turns, [], "the list endpoint never reads message bodies");
  assert.strictEqual(s0.loadState, "unread",
    "'unread' and '0 turns' are different facts -- claiming the second is the bug");
  assert.strictEqual(s0.created_ms, 1700000000 * 1000, "mtime is seconds, buckets are ms");
});

test("14b. a session with no readable prompt says so rather than being titled", () => {
  T.S.sessions = [];
  T.adoptRealSessions([{ id: "no-prompt", title: "", mtime: 1, size: 0 }]);
  assert.strictEqual(T.S.sessions[0].title, "(no prompt)");
});

test("14c. panel-started sessions survive a refresh of the real list", () => {
  T.S.sessions = [{ id: "s-1", title: "typed here", local: true, turns: [], updated_ms: 9e12 }];
  T.adoptRealSessions([{ id: "on-disk", title: "from a file", mtime: 2, size: 1 }]);
  const ids = T.S.sessions.map(s => s.id);
  assert.ok(ids.includes("s-1"), "a live in-memory session is not a file yet -- do not drop it");
  assert.ok(ids.includes("on-disk"));
});

test("14d. transcript turns carry NO routing metadata, because none was computed", () => {
  const turns = T.transcriptTurns([
    { role: "user", text: "hello", ts: "2026-01-01T00:00:00Z" },
    { role: "assistant", text: "hi", tools: ["Bash"], ts: "2026-01-01T00:00:01Z" },
  ]);
  assert.strictEqual(turns.length, 1, "a turn is one prompt plus the reply to it");
  assert.strictEqual(turns[0].domain, null,
    "these ran in the terminal -- inventing a placement to fill the slot is the bug");
  assert.strictEqual(turns[0].mode, "transcript");
  assert.strictEqual(turns[0].confidence, 0);
  assert.strictEqual(turns[0].transcript, true);
  deepEq(turns[0].tools, ["Bash"]);
});

test("14e. an assistant block with no recorded prompt is marked orphan, not given one", () => {
  const turns = T.transcriptTurns([{ role: "assistant", text: "stray", ts: "" }]);
  assert.strictEqual(turns.length, 1);
  assert.strictEqual(turns[0].orphan, true);
  assert.strictEqual(turns[0].text, "", "no prompt may be manufactured for it");
});

/* ── 15. loadLayout rejects junk rather than trusting localStorage ──────── */

/* DEFAULTS is spelled once. When loadLayout() grows a key, this test used to have
   to be edited in two places or it went red for the wrong reason -- which is
   exactly what happened when balanceTab shipped: the code was correct and
   validated, the expectation was simply stale. Naming the shape once means the
   next key added to loadLayout() fails this test only if it is genuinely
   unguarded, not merely new. */
/* Mirrors loadLayout()'s defaults. Every new persisted layout key must be added
   here too -- this is a whole-object deepEq, so a new default reads as a
   corruption failure until the fixture catches up. */
const LAYOUT_DEFAULTS = { paneCollapsed: {}, folds: {}, browseW: null, browseClosed: false,
                          navCollapsed: false, railSections: {},
                          dest: "now", destSel: {},
                          balanceTab: "today", sessCollapsed: {} };

test("15. a corrupt/hostile stored layout degrades to defaults", () => {
  const prev = sandbox.localStorage._m["sutra.panel.layout"];
  try {
    sandbox.localStorage._m["sutra.panel.layout"] = "{not json";
    deepEq(T.loadLayout(), LAYOUT_DEFAULTS,
      "unparseable layout must not take the panel down");
    sandbox.localStorage._m["sutra.panel.layout"] =
      JSON.stringify({ browseW: "700px", paneCollapsed: "nope", folds: 3, browseClosed: "yes" });
    deepEq(T.loadLayout(), LAYOUT_DEFAULTS,
      "wrong types must be dropped, not applied");
    sandbox.localStorage._m["sutra.panel.layout"] = JSON.stringify({ browseW: 12 });
    assert.strictEqual(T.loadLayout().browseW, null,
      "an absurdly small width would render an unusable sliver");
  } finally {
    if (prev === undefined) delete sandbox.localStorage._m["sutra.panel.layout"];
    else sandbox.localStorage._m["sutra.panel.layout"] = prev;
  }
});

/* balanceTab shipped with an allowlist in loadLayout() but no test. localStorage is
   attacker-writable from anything that runs in this origin, and the value is used to
   pick a render branch, so a value outside the allowlist must never survive. */
test("15b. balanceTab is allowlisted, not trusted", () => {
  const prev = sandbox.localStorage._m["sutra.panel.layout"];
  try {
    for (const good of ["today", "week", "month"]) {
      sandbox.localStorage._m["sutra.panel.layout"] = JSON.stringify({ balanceTab: good });
      assert.strictEqual(T.loadLayout().balanceTab, good, good + " is a real tab and must survive");
    }
    for (const bad of ["year", "", null, 3, {}, ["today"], "__proto__", "<script>"]) {
      sandbox.localStorage._m["sutra.panel.layout"] = JSON.stringify({ balanceTab: bad });
      assert.strictEqual(T.loadLayout().balanceTab, "today",
        JSON.stringify(bad) + " is not a tab and must degrade to the default");
    }
  } finally {
    if (prev === undefined) delete sandbox.localStorage._m["sutra.panel.layout"];
    else sandbox.localStorage._m["sutra.panel.layout"] = prev;
  }
});

/* Side chats are a BRANCH, not a continuation. The promise is that nothing said on
   the side reaches the main thread, and there are exactly two ways to break it:
   share the socket, or resume the main session id. Both are pinned here. */
test("16a. a side channel resolves to its OWN key, never the main one", () => {
  assert.strictEqual(T.chanKey("S1", false), "S1");
  assert.strictEqual(T.chanKey("S1", true), "S1::side");
  assert.notStrictEqual(T.chanKey("S1", true), T.chanKey("S1", false),
    "side and main resolved to the same channel key — they would share one socket");
});

test("16b. side turns are stored apart from the session's own turns", () => {
  assert.ok(Object.prototype.hasOwnProperty.call(T.S, "sideTurns"),
    "S.sideTurns missing — side turns would have to live in s.turns and appear " +
    "in the main transcript");
  assert.ok(Object.prototype.hasOwnProperty.call(T.S, "sideOpen"), "S.sideOpen missing");
});

test("17. the '@' palette offers files and '/' offers commands, each replacing its own token", () => {
  const prevFs = T.S.fs;
  try {
    T.S.fs = { files: [{ path: "src/app.py", bytes: 10 }, { path: "README.md", bytes: 5 }] };
    const at = T.paletteFor("look at @app");
    assert.strictEqual(at && at.kind, "file", "@ did not open the file palette");
    assert.strictEqual(at.items[0].ref, "@src/app.py");
    /* No token: shallower paths first, so the top of the project is the default
       rather than whatever sorts first alphabetically. */
    const bare = T.paletteFor("see @");
    assert.strictEqual(bare.items[0].label, "README.md");
    /* An @ mid-word is not a mention (an email address must not open the palette). */
    assert.strictEqual(T.paletteFor("mail me at a@b"), null,
      "an embedded @ opened the file palette");
  } finally { T.S.fs = prevFs; }
});

/* ── 18. scroll survives a re-render ────────────────────────────────────────
   render() replaces #panes wholesale, so the browse pane's scroller comes back
   as a fresh element at scrollTop 0. Clicking a Directory status filter part
   way down the Charters table therefore threw the operator back to the top of
   the page on every single click. Focus and caret were already saved across
   the rebuild; scroll was not. */
function withScroller(top, scrollHeight, clientHeight, fn) {
  /* A real scroller CLAMPS: assigning a scrollTop past the end silently lands
     at scrollHeight - clientHeight. The clamp is the whole reason the restore
     needs a rAF pass, so a plain-object stub that stored 4000 verbatim would
     test a browser that does not exist. */
  const el = {
    scrollHeight: scrollHeight, clientHeight: clientHeight, _t: 0,
    get scrollTop() { return this._t; },
    set scrollTop(v) {
      this._t = Math.max(0, Math.min(v, Math.max(0, this.scrollHeight - this.clientHeight)));
    },
  };
  el.scrollTop = top;
  const prev = sandbox.document.querySelector;
  sandbox.document.querySelector = (sel) =>
    (sel.indexOf("browse") !== -1 ? el : prev.call(sandbox.document, sel));
  const prevRAF = sandbox.requestAnimationFrame;
  const queued = [];
  sandbox.requestAnimationFrame = (cb) => queued.push(cb);
  try { return fn(el, () => queued.splice(0).forEach((cb) => cb())); }
  finally { sandbox.document.querySelector = prev; sandbox.requestAnimationFrame = prevRAF; }
}

test("18a. the scroll key separates the three views of one screen", () => {
  const prev = [T.S.screen, T.S.view];
  try {
    T.S.screen = "departments"; T.S.view = "dir";
    const dir = T._browseScrollKey();
    T.S.view = "live";
    assert.notStrictEqual(T._browseScrollKey(), dir,
      "Live and Directory are different documents and must not share a position");
    T.S.view = "dir";
    assert.strictEqual(T._browseScrollKey(), dir, "the same view must key the same");
  } finally { T.S.screen = prev[0]; T.S.view = prev[1]; }
});

test("18b. a position is restored across a rebuild of the same view", () => {
  T.S.screen = "departments"; T.S.view = "dir";
  withScroller(4000, 20000, 900, (el) => {
    const saved = T._browseScrollState();
    assert.strictEqual(saved.top, 4000);
    el.scrollTop = 0;                       // what the innerHTML rebuild does
    T._restoreBrowseScroll(saved);
    assert.strictEqual(el.scrollTop, 4000, "the operator's position was lost");
  });
});

test("18c. switching view does NOT restore -- a new document starts at the top", () => {
  T.S.screen = "departments"; T.S.view = "dir";
  withScroller(4000, 20000, 900, (el) => {
    const saved = T._browseScrollState();
    T.S.view = "live";                      // the operator switched views
    el.scrollTop = 0;
    T._restoreBrowseScroll(saved);
    assert.strictEqual(el.scrollTop, 0, "an unrelated view inherited a stale offset");
  });
});

test("18d. a filter that SHORTENS the page clamps to the real maximum, not 0", () => {
  T.S.screen = "departments"; T.S.view = "dir";
  withScroller(4000, 20000, 900, (el, flushRAF) => {
    const saved = T._browseScrollState();
    // the rebuild leaves a much shorter document; the browser clamps to 0
    el.scrollHeight = 2000; el.scrollTop = 0;
    T._restoreBrowseScroll(saved);
    flushRAF();
    assert.strictEqual(el.scrollTop, 1100, "should land at scrollHeight - clientHeight");
  });
});

test("18e. an unscrolled pane saves nothing, so nothing is restored", () => {
  T.S.screen = "departments"; T.S.view = "dir";
  withScroller(0, 20000, 900, () => {
    assert.strictEqual(T._browseScrollState(), null);
  });
});

/* ── 18f-18j. "Transcript not read yet" was a RESTING state ────────────────
   Reported live: the message shows on opening the app and does not clear.
   Reproduced in the running panel -- an open pane on an IDLE session sat at
   loadState "unread" for 8s and never moved. Two independent causes:

     1. Nothing enforced "an open pane reads its transcript". ensureTranscript()
        only acts on "unread", and was only CALLED from the sites that open a
        pane; the ⋮ > "open in repo" action pushes into openPanes without
        calling it. The background re-read in applySessionChange() is no safety
        net -- it fires on a WRITE to the file, and an idle transcript is never
        written. So the pane never recovered.
     2. sessionBody() treated every state that was not loading/error/empty as
        "not read yet", including "ok" with zero turns -- which the busy guard
        in applySessionChange() produces without parsing anything.

   These pin the FACTS, not the wiring: a pane left unread must become read,
   and a session that HAS been read must never claim otherwise. */

test("18f. ensureTranscript starts the read for a pane left unread", () => {
  const s = { id: "idle-1", real: true, turns: [], loadState: "unread" };
  T.ensureTranscript(s);
  assert.strictEqual(s.loadState, "loading",
    "an unread real session is exactly what the read is for");
});

test("18g. ensureTranscript is idempotent -- a repaint must not refetch", () => {
  /* render() calls this for every open pane on EVERY repaint. If it were not a
     no-op past "unread" it would issue a GET per frame per pane. */
  ["loading", "ok", "empty", "error"].forEach(st => {
    const s = { id: "x", real: true, turns: [], loadState: st };
    T.ensureTranscript(s);
    assert.strictEqual(s.loadState, st, `${st} must be left alone`);
  });
  assert.doesNotThrow(() => T.ensureTranscript(null), "a closed/missing pane is not an error");
  const local = { id: "s-1", real: false, turns: [], loadState: "live" };
  T.ensureTranscript(local);
  assert.strictEqual(local.loadState, "live", "a panel-started session has no file to read");
});

test("18h. render() is the floor: every open pane gets its read scheduled", () => {
  /* The regression this closes is a pane reaching openPanes by a path that
     forgot the call. Assert the floor exists rather than the call sites. */
  assert.ok(/openPanes[\s\S]{0,200}ensureTranscript/.test(T.__renderSrc),
    "render() must schedule ensureTranscript for open panes");
});

test("18i. a session that WAS read never says 'not read yet'", () => {
  /* the busy guard promotes "loading" -> "ok" without parsing, so ok+0 turns
     is a real state and it is a READ one */
  ["ok", "empty", "live"].forEach(st => {
    const body = T.sessionBody({ id: "a", real: true, turns: [], loadState: st });
    assert.ok(!/not read yet/.test(body), `${st} is read -- claiming otherwise is the bug`);
    assert.ok(/No readable turns/.test(body), `${st} must say what was actually found`);
  });
});

test("18j. the four honest states are still distinguishable", () => {
  const mk = st => T.sessionBody({ id: "a", real: true, turns: [], loadState: st, loadError: "boom" });
  assert.ok(/Reading the transcript/.test(mk("loading")));
  assert.ok(/could not be read/.test(mk("error")) && /boom/.test(mk("error")));
  assert.ok(/No readable turns/.test(mk("empty")));
  assert.ok(/not read yet/.test(mk("unread")), "unread is still a truthful transient");
  assert.ok(/not read yet/.test(mk(undefined)), "a session built with no loadState is unread");
});

/* ── 19. a resume id that cannot possibly resolve is not sent ───────────────
   `claude --resume <id>` resolves the id IN THE PROJECT OF ITS WORKING
   DIRECTORY. adoptRealSessions() attaches claude_session to every transcript on
   disk, and those belong to the directory they were recorded in -- usually a
   repo, not the panel's workdir. Sending one guaranteed:
       No conversation found with session ID: 565ad6a3-...
   a wasted claude run, seconds of dead air, and a failed-looking turn. */
const mkSess = (id, cwd, workdir) => ({
  claude_session: id, cwd: cwd, channel: workdir ? { workdir: workdir } : null,
});

test("19a. an id recorded in THIS workdir is resumed", () => {
  assert.strictEqual(T.resumableId(mkSess("abc", "/repo", "/repo")), "abc");
});

test("19b. an id from a DIFFERENT directory is never sent", () => {
  assert.strictEqual(T.resumableId(mkSess("abc", "/repo", "/workspace")), null,
    "this is the doomed round trip the operator saw fail");
});

test("19c. an UNKNOWN cwd is still attempted -- unknown is not mismatched", () => {
  /* the server replays without the id if the guess is wrong, so trying costs
     one recoverable turn; refusing would break every legitimate continuation
     whose cwd the transcript did not record */
  assert.strictEqual(T.resumableId(mkSess("abc", "", "/workspace")), "abc");
  assert.strictEqual(T.resumableId(mkSess("abc", "/repo", null)), "abc");
});

test("19d. no id means no resume, never the string 'null'", () => {
  assert.strictEqual(T.resumableId(mkSess(null, "/repo", "/repo")), null);
  assert.strictEqual(T.resumableId(mkSess(undefined, "/repo", "/repo")), null);
});

/* ── 20. the composer can hold more than one line ──────────────────────────
   It was <input type="text">, which cannot contain a newline at any price:
   Shift+Enter, Ctrl+J and pasting a multi-line block were not "unimplemented",
   they were impossible. These assertions are on the shipped markup, because the
   element TYPE is the whole feature. */
/* The panel used to be ONE file, so these tests grepped it for everything:
   JS-rendered markup (composer <textarea>, the Enter handler) AND CSS rules
   (.pc textarea colours, the grid, .termbody[hidden]). Those now live in three
   places -- the HTML shell, panel.css, the js modules -- so reconstruct the
   whole picture the browser assembles, and every existing grep resolves against
   the right file without caring which one it landed in. */
const panelHtml = fs.readFileSync(PANEL, "utf8")
  + "\n" + fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8")
  + "\n" + source;

test("20a. the composer is a textarea, not an input", () => {
  assert.ok(/<textarea data-sask=/.test(panelHtml),
    "the composer must be a textarea or multiline is impossible");
  assert.ok(!/<input type="text" data-sask=/.test(panelHtml),
    "the old single-line input must be gone");
});

test("20b. its value is the element's CONTENT, not a value= attribute", () => {
  /* a textarea ignores value="..."; leaving that in place would silently blank
     the composer on every re-render */
  const m = panelHtml.match(/<textarea data-sask=[\s\S]{0,320}?<\/textarea>/);
  assert.ok(m, "composer markup not found");
  assert.ok(/>\$\{esc\(S\.composerText/.test(m[0]),
    "the draft text must be the textarea's content");
  assert.ok(!/value="\$\{esc\(S\.composerText/.test(m[0]),
    "a textarea ignores value=, so the draft would vanish");
});

test("20c. focus restore knows about TEXTAREA", () => {
  /* _focusedInputSelector tested INPUT||SELECT only. Without TEXTAREA the caret
     jumps to the end on every background re-render while you type. */
  const fn = panelHtml.match(/function _focusedInputSelector\(\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/TEXTAREA/.test(fn), "_focusedInputSelector must accept TEXTAREA");
});

test("20d. Shift+Enter is a newline, Cmd/Ctrl+Enter sends, plain Enter sends", () => {
  const h = panelHtml;
  /* Cmd/Ctrl+Enter now SENDS (it used to insert a newline) -- the branch must
     exist and must be a SEND, so it references submitTurn. */
  assert.ok(/e\.key === "Enter" && \(e\.ctrlKey \|\| e\.metaKey\)/.test(h),
    "Cmd/Ctrl+Enter must have its own branch");
  const cmdSend = h.slice(h.indexOf('e.key === "Enter" && (e.ctrlKey || e.metaKey)'));
  assert.ok(/submitTurn/.test(cmdSend.slice(0, 400)),
    "the Cmd/Ctrl+Enter branch must SEND, not insert a newline");
  /* Shift+Enter must be handled (and return, i.e. fall through to the textarea's
     own newline) BEFORE the plain-Enter send branch, or it would send. */
  const shiftIdx = h.indexOf('e.key === "Enter" && e.shiftKey) return');
  const sendIdx = h.indexOf('if(e.key==="Enter"){');
  assert.ok(shiftIdx !== -1, "Shift+Enter must be a newline (return early)");
  assert.ok(sendIdx !== -1, "plain Enter must still send");
  assert.ok(shiftIdx < sendIdx, "Shift+Enter must be handled before the send branch");
});

test("20e. auto-grow resets height before measuring", () => {
  /* scrollHeight only shrinks correctly when the element is not already holding a
     taller explicit height -- without the reset the box grows and never returns */
  const fn = panelHtml.match(/function autoGrowComposer\(el\)\{[\s\S]*?\n\}/)[0];
  const reset = fn.indexOf('height = "auto"');
  const measure = fn.indexOf("scrollHeight");
  assert.ok(reset !== -1 && measure !== -1 && reset < measure,
    "must set height:auto BEFORE reading scrollHeight");
});

/* ── 21. the boot contract ──────────────────────────────────────────────────
   These exist because of a shipped, user-visible outage: 5781a2f deleted
   <div id="tenantMenu"> from the markup and left the code that wired it. The
   getElementById returned null, the next addEventListener threw, and boot() --
   the LAST statement in the script -- never ran. No settings, no departments,
   no sessions, no skills, all at once, each screen blaming its own endpoint.
   Every endpoint was healthy the whole time. */

test("21a. no top-level getElementById result is dereferenced without a guard", () => {
  /* The exact failure shape: `const x = document.getElementById("y")` at top
     level, followed by `x.something` with nothing proving x is non-null. Only
     top-level code matters -- inside a function the element may legitimately be
     created before the call. */
  const h = panelHtml;
  const tail = h.slice(h.lastIndexOf("\n}") + 2);   // after the last function body
  const decls = [...tail.matchAll(/^const (\w+)\s*=\s*document\.getElementById\("([^"]+)"\)/gm)];
  const unguarded = [];
  for (const [, name, id] of decls) {
    const idInMarkup = new RegExp('id="' + id + '"').test(h);
    const guarded = new RegExp("(if\\s*\\(\\s*" + name + "\\b|" + name + "\\s*&&|" + name + "\\s*\\?)").test(tail);
    if (!idInMarkup && !guarded) unguarded.push(name + " -> #" + id);
  }
  assert.deepStrictEqual(unguarded, [],
    "top-level element refs with no matching id= in the markup and no guard: " +
    unguarded.join(", "));
});

test("21b. boot() is still the last statement, and nothing throws before it", () => {
  const h = panelHtml;
  const i = h.lastIndexOf("boot();");
  assert.ok(i !== -1, "boot() must be called");
  const after = h.slice(i + "boot();".length).replace(/<\/script>/, "").trim();
  assert.strictEqual(after, "",
    "boot() must be the final statement -- anything before it that throws is silent");
});

test("21c. the tenant surface is gone, not half-gone", () => {
  /* Half-removal is what caused the outage. Assert BOTH directions: no markup,
     and no code that expects markup. */
  const h = panelHtml;
  for (const sym of ["tenantMenuEl", "tenantSwitchEl", "pickTenant", "renderTenantMenu",
                     "tenantGateHtml", "wireGate", "inTenant", "scopeQ", "S.showAcme",
                     "META.tenant_id", "LS_TENANT"]) {
    assert.ok(!h.includes(sym), "tenant symbol still referenced: " + sym);
  }
});

test("21d. loadRuntime degrades per endpoint, it does not fail as a block", () => {
  /* Promise.all here meant a 500 from /api/skills nulled SETTINGS for the life
     of the window, and Settings then claimed "GET /api/settings has not
     answered" -- which had not happened. */
  const fn = panelHtml.match(/async function loadRuntime\(\)\{[\s\S]*?\n\}/)[0];
  assert.ok(fn.includes("Promise.allSettled"), "must use allSettled");
  assert.ok(!/Promise\.all\(/.test(fn), "must not use Promise.all");
  assert.ok(fn.includes("S.runtimeError"), "must report WHICH endpoint failed");
});

test("21e. the composer's colours come from the theme, not the UA stylesheet", () => {
  /* 03c09cc turned the composer into a <textarea> and left the rule selecting
     `.pc input`, so it lost background/border/colour/outline and rendered as a
     bordered white box with a browser focus ring. */
  const h = panelHtml;
  assert.ok(/\.pc input,\s*\.pc textarea\{/.test(h),
    ".pc rule must select the textarea as well as the input");
  const ta = h.match(/textarea\[data-sask\]\{[\s\S]*?\}/)[0];
  assert.ok(!/font:\s*inherit/.test(ta),
    "font:inherit resets font-size to 16px and beats the .pc rule at equal specificity");
});

test("21f. a hidden terminal body is display:none, so it cannot fit to zero", () => {
  /* .termbody{display:flex} overrode [hidden]{display:none}: switching to the
     Preview tab left the terminal laid out at zero size, it fit itself to 2x1
     and pushed that winsize into the PTY. */
  assert.ok(/\.termbody\[hidden\]\{display:none\}/.test(panelHtml),
    ".termbody[hidden] must be display:none");
});

test("21g. the terminal mode toggle calls a function that exists", () => {
  /* termSetMode called mountTerm(), which has never been defined -- so it threw
     AFTER persisting the new mode, and the pane and the PTY diverged for good. */
  const h = panelHtml;
  assert.ok(!/\bmountTerm\s*\(/.test(h), "mountTerm() does not exist; termMount() does");
  const fn = h.match(/function termSetMode\(mode\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/termMount\(\s*true\s*\)/.test(fn), "must force a remount on a mode change");
});

test("21h. an undated row does not take the History screen down", () => {
  /* Two real domain_updated events in the live registry carry no ts_ms. fmt()
     called toISOString() on them and threw a RangeError, so History rendered
     nothing at all rather than 65 dated rows and 2 undated ones. */
  assert.strictEqual(T.fmt(undefined), "—", "undefined must not throw");
  assert.strictEqual(T.fmt(NaN), "—", "NaN must not throw");
  assert.strictEqual(T.fmt("not a date"), "—", "junk must not throw");
  assert.strictEqual(T.fmt(1785508157097).length, 10, "a real stamp still formats");
});

test("21i. the app is a three-column grid with the rail on the left", () => {
  /* SHIPPED REGRESSION. The tenant popover was removed with a RANGE delete --
     "from .tmenuwrap{ to .rtop{" -- and the rules that happened to sit between
     them went with it: .app's grid-template-columns, .rail's flex column, and
     the narrow-window media query. .app fell back to display:block, so the rail
     stopped being a left column and Home/Code stacked across the top of the
     window. A range delete is only as safe as its end anchor. */
  const h = panelHtml;
  const app = h.match(/\n\s*\.app\{[\s\S]*?\}/);
  assert.ok(app, ".app rule must exist");
  assert.ok(/display:grid/.test(app[0]), ".app must be display:grid");
  assert.ok(/grid-template-columns:\s*224px\s+1fr\s+var\(--termw/.test(app[0]),
    ".app must lay out rail | panes | terminal");
  const rail = h.match(/\n\s*\.rail\{[\s\S]*?\}/);
  assert.ok(rail, ".rail rule must exist");
  assert.ok(/display:flex/.test(rail[0]) && /flex-direction:column/.test(rail[0]),
    ".rail must be a flex column");
  assert.ok(/@media\(max-width:860px\)\{\.app\{grid-template-columns:1fr/.test(h),
    "the narrow-window fallback must survive");
});

test("22a. a streaming token patches one node, it does not re-render the pane", () => {
  /* REPORTED: the transcript flickered, the view snapped bottom->top, and chunk
     delivery was not smooth. One cause: a token frame called scheduleRender(),
     and render() replaces #panes WHOLESALE via innerHTML -- ten times a second,
     destroying and re-parsing the whole transcript per frame. */
  const h = panelHtml;
  const tok = h.match(/\} else if \(f\.type === "token"\)\{[\s\S]*?\n    \} else/);
  assert.ok(tok, "the token frame branch must exist");
  assert.ok(/scheduleStreamPatch/.test(tok[0]),
    "a token must patch, not re-render");
  assert.ok(/\breturn;/.test(tok[0]),
    "it must return before the handler's trailing scheduleRender(), or the " +
    "rebuild happens anyway and the patch is pointless");
  assert.ok(/data-resp="\$\{esc\(t\.uid/.test(h),
    "the reply body needs a stable patch anchor");
});

test("22b. the patch follows the tail only when the reader has not scrolled away", () => {
  const fn = panelHtml.match(/function patchStreaming\(\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/S\.userScrolled\.get\(sid\)/.test(fn),
    "must consult userScrolled before moving the scroller");
  assert.ok(/__pinning/.test(fn),
    "our own scroll must be marked so the listener does not read it as intent");
});

test("22c. streaming is animation-framed, not a 100ms timer", () => {
  const fn = panelHtml.match(/function scheduleStreamPatch\(uid\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/requestAnimationFrame/.test(fn), "must batch on a frame");
  assert.ok(!/setTimeout/.test(fn), "10fps batching is what made it choppy");
});

test("23a. the permission mode is chosen at chat level, not only in Settings", () => {
  /* It lived only in Settings, behind an env var set when STARTING the server --
     which for a Finder-launched .app means editing a plist. The panel showed the
     control, refused it, and told the operator to do something they could not. */
  const h = panelHtml;
  assert.ok(/function permSelect\(\)\{/.test(h), "a composer-level selector must exist");
  /* It renders in the composer row -- the same block as the model select, which
     is the anchor that is unambiguously part of the composer. */
  const call = h.indexOf("${permSelect()}");
  const model = h.indexOf('<select class="modelsel"');
  assert.ok(call !== -1, "permSelect() must be called from the template");
  assert.ok(call < model && model - call < 600,
    "it must render next to the model select, i.e. in the composer row");
});

test("23b. a write-capable mode is confirmed, never one click away", () => {
  const fn = panelHtml.match(/async function setPermMode\(mode\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/writes_files/.test(fn), "must branch on whether the mode writes files");
  assert.ok(/S\.permConfirm = \{ mode \}/.test(fn),
    "a write-capable mode must open the confirmation instead of applying");
  assert.ok(/unsafe_modes_allowed/.test(fn),
    "already-granted consent must not be re-prompted -- that is friction with no safety");
});

test("23c. only the confirmation sends the acknowledgement phrase", () => {
  /* The server refuses a bare boolean on purpose: the port is unauthenticated.
     If the phrase were sent from anywhere else, that protection would be moot. */
  const h = panelHtml;
  const apply = h.match(/async function applyPermMode\(mode, withAck\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/if \(withAck\) body\.unsafe_ack = UNSAFE_ACK_PHRASE/.test(apply),
    "the phrase is sent only when explicitly confirmed");
  const sends = (h.match(/unsafe_ack/g) || []).length;
  assert.ok(sends <= 3, "the phrase should have one send site, not be sprinkled around");
});

test("23d. the selector shows the EFFECTIVE mode, not the stored one", () => {
  /* The server clamps at the point of use. Showing the stored value would tell
     the operator the agent is doing something it is not. */
  const fn = panelHtml.match(/function permSelect\(\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/permission_mode_effective/.test(fn),
    "must read permission_mode_effective first");
});

test("24a. every composer control is themed, none falls back to the UA stylesheet", () => {
  /* .permsel shipped with NO css at all and rendered as a white box in a dark
     theme, directly beside a correctly themed .modelsel. Same shape as the
     composer-textarea regression: a control added next to an existing one
     without inheriting the rule that made the existing one belong. */
  const h = panelHtml;
  /* The class attribute is often a template literal -- `class="permsel${writes}"`.
     An earlier version of this test required a closing quote right after the
     letters, so it never collected `permsel` at all and passed while the very
     regression it names was reintroduced. Take the LEADING literal token of any
     class attribute instead, interpolation or not. */
  const classes = new Set();
  const re = /<(?:select|input|textarea)[^>]*\sclass="([a-z][a-z-]*)/g;
  let m;
  while ((m = re.exec(h))) classes.add(m[1]);
  assert.ok(classes.has("permsel") && classes.has("modelsel"),
    "sanity: the extractor must actually see the composer selects, got " +
    [...classes].join(","));
  /* Comments are stripped first. A prose mention like "the .permsel rule" in a
     comment satisfied a naive search and made this test pass while the CSS it
     checks for was absent -- the test was reassuring rather than load-bearing.
     Only a real selector counts: the class followed by { , : or another class. */
  /* The stylesheet is panel.css now, not a <style> block. Read it directly: a
     `<style[\s\S]*?</style>` match would instead grab the tiny inline update-
     banner style embedded in a module's template literal, which styles none of
     the composer controls -- and every one would report as "unstyled". */
  const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const unstyled = [...classes].filter(c => !new RegExp("\\." + c + "\\s*[,{:.]").test(css));
  assert.deepStrictEqual(unstyled, [],
    "form controls with no CSS rule: " + unstyled.join(", "));
});

test("24b. the directory grid can shrink, and its TOC stops overlaying when it collapses", () => {
  /* Two compounding bugs made the Directory view unreadable in a narrow pane:
     `1fr` is minmax(auto,1fr) and `auto` floors at MIN-CONTENT, so the column
     sized itself to 973px inside a 385px pane; and when the container query
     collapsed the grid to one column the nav was still position:sticky, so the
     TOC printed itself over the departments underneath. */
  const h = panelHtml;
  const grid = h.match(/\.dpage\{[^}]*\}/)[0];
  assert.ok(/grid-template-columns:200px minmax\(0,1fr\)/.test(grid),
    "the content column must be allowed to shrink below min-content");
  assert.ok(/\.dpage > \*\{min-width:0\}/.test(h),
    "grid items default to min-width:auto -- the same trap one level down");
  const cq = h.match(/@container \(max-width:720px\)\{[\s\S]*?\n  \}/);
  assert.ok(cq, "the collapse query must exist");
  assert.ok(/\.dpage nav\{position:static\}/.test(cq[0]),
    "a sticky nav in a single column is an overlay, not a rail");
  /* Source order is the whole reason this works: a container query carries no
     extra specificity, so declared BEFORE the sticky rule it is overridden by
     the very rule it exists to undo. */
  assert.ok(h.indexOf("@container (max-width:720px)") >
            h.indexOf(".dpage nav{position:sticky"),
    "the container query must come AFTER the sticky rule it overrides");
});

/* ── 25. the staged-update banner ───────────────────────────────────────────
   The update is mandatory, so the banner is the only thing standing between a
   verified download and the app closing itself. Every test here is about it
   telling the truth: what it will do, when, and whether it can do it at all. */

const _updHosts = Object.create(null);

/* Mount a real element registry on the stub document so the banner can be
   inspected after it renders -- and, just as importantly, so its absence is
   observable. */
function updHarness({ staged, desktop, focus = true, term = false }) {
  Object.keys(_updHosts).forEach((k) => delete _updHosts[k]);
  onNodeRemove = (n) => { delete _updHosts[n.id]; };
  documentStub.body = { appendChild(c) { _updHosts[c.id] = c; return c; } };
  documentStub.getElementById = (id) =>
    (id === "updHost" ? (_updHosts[id] || null) : makeNode("div"));
  documentStub.hasFocus = () => focus;

  const applied = [];
  sandbox.sutra = desktop
    ? { desktop: true,
        applyUpdate: () => { applied.push(1); return Promise.resolve({ ok: true }); },
        deferUpdate: () => Promise.resolve({ ok: true }) }
    : undefined;

  T.stopUpdCountdown();
  T.S.updStaged = staged;
  T.S.updDeferred = false;
  T.S.updApplyError = null;
  T.S.updFiring = false;
  T.S.termOpen = term;
  T.renderUpdateBanner();
  return { applied, html: () => (_updHosts.updHost || { innerHTML: "" }).innerHTML,
           gone: () => !_updHosts.updHost };
}

const STAGED = { pending: true, version: "2.70.0", state: "staged" };

test("25a. no staged update means no banner at all", () => {
  const h = updHarness({ staged: { pending: false }, desktop: true });
  assert.ok(h.gone(), "a banner with nothing to say must be removed, not blanked");
  T.stopUpdCountdown();
});

test("25b. a browser gets a statement of fact, never a countdown", () => {
  /* The CLI serves this same panel where there is no app to restart. A
     countdown there would promise something the page cannot do. */
  const h = updHarness({ staged: STAGED, desktop: false });
  const html = h.html();
  assert.ok(/has been downloaded/.test(html), "it should say what happened");
  assert.ok(/next time the desktop app quits/.test(html), "and what happens next");
  assert.ok(!/Restart now/.test(html), "no control it cannot honour");
  assert.strictEqual(T.S.updLeft, null, "no clock without a shell to restart");
  T.stopUpdCountdown();
});

test("25c. the desktop counts down from 15 and offers both exits", () => {
  const h = updHarness({ staged: STAGED, desktop: true });
  assert.strictEqual(T.S.updLeft, T.UPDATE_COUNTDOWN_S);
  assert.ok(/Restarting in/.test(h.html()));
  assert.ok(/Restart now/.test(h.html()));
  assert.ok(/Not now/.test(h.html()));
  T.stopUpdCountdown();
});

test("25d. the clock is HELD while the window is in the background", () => {
  /* A countdown that ran unfocused would restart the app while the user was in
     another window, having never seen the banner. That is not a prompt. */
  const h = updHarness({ staged: STAGED, desktop: true, focus: false });
  const before = T.S.updLeft;
  T.updTick();
  assert.strictEqual(T.S.updLeft, before, "the clock must not advance unfocused");
  assert.ok(/when you come back/.test(h.html()), "and it must say why it is paused");
  T.stopUpdCountdown();
});

test("25e. a focused tick advances, and reaching zero restarts", () => {
  const h = updHarness({ staged: STAGED, desktop: true });
  T.S.updLeft = 2;
  T.updTick();
  assert.strictEqual(T.S.updLeft, 1);
  T.updTick();
  assert.strictEqual(T.S.updLeft, null, "the clock stops when it fires");
  assert.deepStrictEqual(h.applied, [1], "and the shell is asked to restart");
  /* Regression: the render inside applyUpdateNow() saw "staged, no clock, no
     error yet" and started a SECOND countdown -- re-firing every 15s for as
     long as the shell took to quit. */
  T.renderUpdateBanner();
  assert.strictEqual(T.S.updLeft, null, "firing must not re-arm the countdown");
  assert.deepStrictEqual(h.applied, [1], "and must not restart twice");
  T.stopUpdCountdown();
});

test("25f. 'Not now' defers -- it does not decline, and it does not restart", () => {
  /* The whole point of the mandatory design: cancelling costs nothing because
     the verified build is applied on the way out anyway. The copy has to say
     that, or the user will expect to be asked again. */
  const h = updHarness({ staged: STAGED, desktop: true });
  T.S.updDeferred = true;
  T.stopUpdCountdown();
  T.renderUpdateBanner();
  assert.deepStrictEqual(h.applied, [], "deferring must never restart the app");
  assert.strictEqual(T.S.updLeft, null, "and it must stop the clock");
  assert.ok(/will finish installing when you quit/.test(h.html()),
    "the promise the shell actually keeps");
  assert.ok(!/Restarting in/.test(h.html()));
  T.stopUpdCountdown();
});

test("25g. an open terminal WARNS and the clock keeps running", () => {
  /* Founder decision 2026-08-06: warn, do not suppress. So the warning has to
     be present AND the countdown has to be unaffected by it. */
  const h = updHarness({ staged: STAGED, desktop: true, term: true });
  assert.ok(/terminal session is open/i.test(h.html()), "say what will be lost");
  assert.strictEqual(T.S.updLeft, T.UPDATE_COUNTDOWN_S, "and still count down");
  T.stopUpdCountdown();
});

test("25h. a failed install never renders a countdown that is not running", () => {
  /* Regression: `failed` fell through to the countdown branch and rendered
     "Restarting in nulls" -- there is no clock in that state. */
  const h = updHarness({
    staged: { pending: true, version: "2.70.0", state: "failed",
              error: "new bundle failed codesign" },
    desktop: true });
  const html = h.html();
  assert.ok(!/null/.test(html), "no null leaked into the copy: " + html);
  assert.ok(!/Restarting in/.test(html));
  assert.ok(/could not be installed/.test(html));
  assert.ok(/codesign/.test(html), "the reason is the useful part");
  T.stopUpdCountdown();
});

test("25i. an update already armed says so instead of counting again", () => {
  const h = updHarness({
    staged: { pending: true, version: "2.70.0", state: "installing" },
    desktop: true });
  assert.strictEqual(T.S.updLeft, null, "arming already happened; no second clock");
  assert.ok(/ready to install/.test(h.html()));
  assert.ok(/as soon as the app closes/.test(h.html()));
  T.stopUpdCountdown();
});

/* ══════════════════════════════════════════════════════════════════════════
   26. dirPickerAvailable() -- the native folder-picker gate (05-chat.js)
   ──────────────────────────────────────────────────────────────────────────
   The Browse… buttons in Settings and the composer are rendered ONLY when a
   real folder picker exists, i.e. the Electron preload bridge exposed
   window.sutra.pickDirectory. In a bare browser that bridge is absent and the
   button must stay off (a dead button that opens nothing is worse than none).
   window === sandbox in this harness, so window.sutra IS sandbox.sutra.
   ══════════════════════════════════════════════════════════════════════════ */

/* ── 25j-25n. a check that FINDS an update must start the download ─────────
   Reported: "check for updates is not downloading the dmg in the background".
   It was accurate. Staging ran only on the shell's timer (90s after launch,
   then every six hours), so a deliberate check reported "x.y available" and
   downloaded nothing; the only way on was the blocking "Download & install"
   that quits the app. The panel cannot stage by itself -- /desktop/stage is
   token-authenticated and the token never reaches the renderer -- so it asks
   the shell, the same shape as apply/defer. */

/* sandbox IS window inside the vm realm (sandbox.window = sandbox), so this is
   the same stub the dirPickerAvailable test uses one section down. */
const withSutra = async (bridge, fn) => {
  const saved = sandbox.sutra;
  sandbox.sutra = bridge;
  try { return await fn(); } finally { sandbox.sutra = saved; }
};

/* Driven in the async phase by the runner at the foot of this file, in
   sequence: every one of these mutates S.upd*, so they must not interleave
   with each other or with a sync test. */
async function updateStagingChecks(){
await atest("25j. finding an update asks the shell to stage it", async () => {
  let asked = 0;
  T.S.upd = { desktop: { managed: true, update_available: true, latest: "9.9.9" } };
  T.S.updStaging = false;
  await withSutra({ desktop: true, stageUpdate: () => { asked++; return Promise.resolve({ ok: true, staged: true, version: "9.9.9" }); } },
    () => T.stageInBackground());
  assert.strictEqual(asked, 1, "the download the operator asked for by checking");
  assert.ok(/9\.9\.9/.test(T.S.updMsg) && /verified|install/i.test(T.S.updMsg),
    "report what landed, not that a download started");
});

await atest("25k. up-to-date, unmanaged, or errored checks download nothing", async () => {
  for (const d of [{ managed: true, update_available: false },
                   { managed: false, reason: "source checkout" },
                   { managed: true, update_available: true, error: "rate limited" }]) {
    let asked = 0;
    T.S.upd = { desktop: d }; T.S.updStaging = false; T.S.updMsg = null;
    await withSutra({ desktop: true, stageUpdate: () => { asked++; return Promise.resolve({ ok: true }); } },
      () => T.stageInBackground());
    assert.strictEqual(asked, 0, `must not stage for ${JSON.stringify(d)}`);
  }
});

await atest("25l. a plain browser stages nothing -- there is no app to replace", async () => {
  T.S.upd = { desktop: { managed: true, update_available: true, latest: "9.9.9" } };
  T.S.updStaging = false; T.S.updMsg = null;
  await withSutra(undefined, () => T.stageInBackground());
  assert.strictEqual(T.S.updMsg, null, "no promise of a download that cannot happen");
});

await atest("25m. one download at a time", async () => {
  let asked = 0;
  T.S.upd = { desktop: { managed: true, update_available: true, latest: "9.9.9" } };
  T.S.updStaging = true;                     /* one already in flight */
  await withSutra({ desktop: true, stageUpdate: () => { asked++; return Promise.resolve({ ok: true }); } },
    () => T.stageInBackground());
  assert.strictEqual(asked, 0, "two concurrent 160MB downloads into one path is not a race worth having");
});

await atest("25n. a failed stage says so instead of claiming a download", async () => {
  T.S.upd = { desktop: { managed: true, update_available: true, latest: "9.9.9" } };
  T.S.updStaging = false;
  await withSutra({ desktop: true, stageUpdate: () => Promise.resolve({ ok: false, error: "offline" }) },
    () => T.stageInBackground());
  assert.ok(/failed/i.test(T.S.updMsg) && /offline/.test(T.S.updMsg));
});
}

/* ── 26b. the Test pane scaffold is gone from all three wiring sites ───────
   It rendered nothing by design and shipped in the operator's Organization nav. */
test("26b. no Test pane in the nav, the titles, or the screens", () => {
  assert.ok(!T.railSpec().org.some(x => x.id === "testpane"), "nav");
  assert.ok(!("testpane" in T.TITLES), "TITLES");
  assert.ok(!("testpane" in T.SCREENS), "SCREENS");
});

test("26a. dirPickerAvailable is true ONLY when window.sutra.pickDirectory is callable", () => {
  const saved = sandbox.sutra;
  try {
    sandbox.sutra = { pickDirectory: function () {} };
    assert.strictEqual(T.dirPickerAvailable(), true,
      "an Electron host exposing sutra.pickDirectory must enable the Browse… button");

    sandbox.sutra = undefined;
    assert.strictEqual(T.dirPickerAvailable(), false,
      "in a bare browser (no preload bridge) the picker must be gated OFF");

    sandbox.sutra = {};
    assert.strictEqual(T.dirPickerAvailable(), false,
      "a sutra bridge WITHOUT pickDirectory is not a picker");

    sandbox.sutra = { pickDirectory: "nope" };
    assert.strictEqual(T.dirPickerAvailable(), false,
      "pickDirectory must be a function, not merely present");
  } finally {
    sandbox.sutra = saved;
  }
});

/* ══════════════════════════════════════════════════════════════════════════
   27. 10-activity.js -- the global Activity drawer (observable contract)
   ──────────────────────────────────────────────────────────────────────────
   The module is a self-contained IIFE whose `act`-prefixed internals it never
   exports, so there is nothing to import. It is driven the way the browser
   drives it: load its source into a purpose-built minimal DOM, let it mount,
   and assert on what an operator can actually SEE -- the injected <style>, the
   built drawer, the [data-act-toggle] toggle, the rendered rows, and fail-soft
   on a bad fetch. A synchronous-resolving fetch thenable makes the 2s poll
   complete during mount, so these fit the synchronous harness above and leave
   no timers running (setInterval is stubbed to a no-op).
   ══════════════════════════════════════════════════════════════════════════ */

const ACT_SRC = fs.readFileSync(path.join(__dirname, "static", "js", "10-activity.js"), "utf8");

/* single-shot, synchronous promise-like: .then runs its callback NOW and hands
   back another sync-thenable, so fetch().then().then().catch() resolves inside
   the call that started it. Two states -- fulfilled ("f") / rejected ("r"). */
function sThen(state, value) {
  const self = {
    then(onF, onR) {
      try {
        if (state === "f") return (typeof onF === "function") ? sWrap(onF(value)) : self;
        return (typeof onR === "function") ? sWrap(onR(value)) : self; // propagate reject
      } catch (e) { return sThen("r", e); }
    },
    catch(onR) { return self.then(undefined, onR); },
  };
  return self;
}
function sWrap(r) { return (r && typeof r.then === "function") ? r : sThen("f", r); }
const sResolve = v => sThen("f", v);
const sReject = e => sThen("r", e);

/* the smallest DOM that lets 10-activity.js mount, toggle, and render. Only the
   operations the module actually performs are implemented; anything else would
   be dead code pretending to be a DOM. */
function actDom() {
  function matchSel(n, sel) {
    if (!n || !n._attrs) return false;
    if (sel[0] === "[") return n.hasAttribute(sel.slice(1, -1));
    if (sel[0] === ".") return n.classList.contains(sel.slice(1));
    if (sel[0] === "#") return n.id === sel.slice(1);
    return n.tagName === sel.toUpperCase();
  }
  function collect(node, sel) {
    const out = [];
    (function walk(n) {
      (n._kids || []).forEach(k => { if (matchSel(k, sel)) out.push(k); walk(k); });
    })(node);
    return out;
  }
  function byId(node, id) {
    let hit = null;
    (function walk(n) { (n._kids || []).forEach(k => { if (!hit && k.id === id) hit = k; walk(k); }); })(node);
    return hit;
  }
  function mkEl(tag) {
    return {
      tagName: (tag || "div").toUpperCase(),
      id: "", type: "", hidden: false, _text: "", _html: "",
      _attrs: {}, _kids: [], _parent: null, _listeners: {},
      classList: {
        _s: new Set(),
        add(...c) { c.forEach(x => this._s.add(x)); },
        remove(...c) { c.forEach(x => this._s.delete(x)); },
        contains(c) { return this._s.has(c); },
        toggle(c, force) {
          if (force === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); return this._s.has(c); }
          force ? this._s.add(c) : this._s.delete(c); return !!force;
        },
      },
      get textContent() { return this._text; },
      set textContent(v) { this._text = String(v); },
      get innerHTML() { return this._html; },
      set innerHTML(v) { this._html = String(v); this._kids = []; },
      setAttribute(k, v) { this._attrs[k] = String(v); },
      getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; },
      hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k); },
      addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); },
      removeEventListener() {},
      appendChild(c) { c._parent = this; this._kids.push(c); return c; },
      querySelector(sel) { return collect(this, sel)[0] || null; },
      querySelectorAll(sel) { return collect(this, sel); },
      closest(sel) { let n = this; while (n) { if (matchSel(n, sel)) return n; n = n._parent; } return null; },
    };
  }
  const head = mkEl("head"); const body = mkEl("body");
  const doc = {
    readyState: "complete", head, body, _listeners: {},
    createElement: t => mkEl(t),
    getElementById: id => byId(head, id) || byId(body, id),
    querySelector(sel) { return collect(head, sel)[0] || collect(body, sel)[0] || null; },
    querySelectorAll(sel) { return collect(head, sel).concat(collect(body, sel)); },
    addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); },
    removeEventListener() {},
  };
  return { doc, dispatch(type, ev) { (doc._listeners[type] || []).slice().forEach(fn => fn(ev)); } };
}

function mountActivity(fetchImpl) {
  const { doc, dispatch } = actDom();
  const box = {
    console, document: doc,
    Date, Math, JSON, Set, Map, Promise, Object, Array, String, Number, Boolean, RegExp, Error,
    setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0, clearTimeout: () => {},
    fetch: fetchImpl || (() => sResolve({ ok: true, json: () => sResolve({ turns: [], agents: [], count: 0 }) })),
  };
  box.window = box; box.globalThis = box;
  vm.createContext(box);
  new vm.Script(ACT_SRC, { filename: "10-activity.js#act-test" }).runInContext(box);
  return { doc, dispatch, box };
}

function clickTrigger(m) {
  const trig = m.doc.createElement("button");
  trig.setAttribute("data-act-toggle", "");
  m.doc.body.appendChild(trig);
  m.dispatch("click", { target: trig, preventDefault() {} });
  return trig;
}

test("27a. mounts once: injects #act-style, builds #act-drawer, and re-load is a no-op", () => {
  const m = mountActivity();
  assert.ok(m.doc.getElementById("act-style"), "must inject its own <style id=act-style>");
  assert.ok(m.doc.getElementById("act-drawer"), "must build the #act-drawer aside on load");
  assert.strictEqual(m.doc.querySelectorAll("#act-style").length, 1, "style injected exactly once");
  assert.strictEqual(m.doc.querySelectorAll("#act-drawer").length, 1, "drawer built exactly once");
  // running the module again in the SAME realm must hit the __actMounted guard
  new vm.Script(ACT_SRC, { filename: "10-activity.js#reload" }).runInContext(m.box);
  assert.strictEqual(m.doc.querySelectorAll("#act-drawer").length, 1,
    "a double-load must not build a second drawer");
});

test("27b. a [data-act-toggle] click toggles the drawer's act-open class (Escape closes)", () => {
  const m = mountActivity();
  const drawer = m.doc.getElementById("act-drawer");
  assert.strictEqual(drawer.classList.contains("act-open"), false, "starts closed");
  const trig = clickTrigger(m);
  assert.strictEqual(drawer.classList.contains("act-open"), true, "first click opens");
  m.dispatch("click", { target: trig, preventDefault() {} });
  assert.strictEqual(drawer.classList.contains("act-open"), false, "second click closes");
  m.dispatch("click", { target: trig, preventDefault() {} });
  assert.strictEqual(drawer.classList.contains("act-open"), true, "re-open");
  m.dispatch("keydown", { key: "Escape" });
  assert.strictEqual(drawer.classList.contains("act-open"), false, "Escape closes an open drawer");
});

test("27c. a populated /api/activity renders the header count and a row per item", () => {
  const data = {
    turns: [{ sid: "sess-abcdef012", title: "Build the feature", cwd: "/a/b/proj", elapsed_s: 5 }],
    agents: [{ parent_sid: "sess-abcdef012", id: "agent-x", label: "run the search", elapsed_s: 3 }],
    count: 2,
  };
  const m = mountActivity(() => sResolve({ ok: true, json: () => sResolve(data) }));
  // the poll resolved synchronously during mount; the header count is synced
  assert.strictEqual(m.doc.getElementById("act-dcount").textContent, "2",
    "the drawer header count must be turns+agents");
  clickTrigger(m);   // open -> body renders
  const html = m.doc.getElementById("act-dbody").innerHTML;
  assert.ok(/act-item/.test(html), "at least one .act-item row must render");
  assert.ok(/Build the feature/.test(html), "the turn title must appear");
  assert.ok(/proj/.test(html), "the turn cwd basename must appear");
  assert.ok(/run the search/.test(html), "the agent label must appear");
  assert.ok(/Running turns/.test(html) && /Agents/.test(html), "both section headers render");
});

test("27d. a failed or malformed fetch does not throw and leaves the drawer intact", () => {
  // (i) network error -> straight to .catch
  const failed = mountActivity(() => sReject(new Error("network down")));
  assert.ok(failed.doc.getElementById("act-drawer"), "drawer still built after a failed fetch");
  assert.strictEqual(failed.doc.getElementById("act-dcount").textContent, "0",
    "a failed feed reports 0, never a fabricated number");
  // (ii) 200 with a body that won't parse -> json() throws, still caught
  const malformed = mountActivity(() => sResolve({ ok: true, json: () => { throw new Error("bad json"); } }));
  assert.ok(malformed.doc.getElementById("act-drawer"), "drawer still built after malformed json");
  // opening an errored feed shows the quiet error copy, not empty-state or a crash
  clickTrigger(failed);
  const html = failed.doc.getElementById("act-dbody").innerHTML;
  assert.ok(/act-err/.test(html), "an errored feed renders the .act-err notice: " + html);
  assert.ok(/reach the activity feed/i.test(html), "the notice must say the feed was unreachable");
});

/* ── 28. the per-turn agent roster, AS RENDERED ─────────────────────────────
   test_governance.js proves the projection is right. These prove it reaches the
   DOM in the right shape, in the right place, escaped. A bug has to survive
   both suites, and they fail for different reasons. */

const AG_FIX = JSON.parse(
  require("fs").readFileSync(__dirname + "/tests/fixtures/toolruns-fanout.json", "utf8"));
/* a turn as 01-state.js builds it: BOTH stores populated, because the wire
   pushes to `tools` and `toolRuns` on the same frame */
const agTurn = runs => ({
  uid: "t9", streaming: true, response: "working",
  tools: runs.map(r => r.name), toolRuns: runs,
});

test("28a. a real fan-out renders one button row per agent, inside .gv-agents", () => {
  const html = T.turnResponse(agTurn(AG_FIX.toolRuns));
  assert.ok(/<div class="gv-agents">/.test(html), "the container is missing: " + html.slice(0, 200));
  const rows = html.match(/<button class="trow /g) || [];
  assert.strictEqual(rows.length, 4, "4 Agent runs in the fixture, got " + rows.length);
});

test("28b. an ordinary turn renders NO roster at all — not an empty container", () => {
  const html = T.turnResponse(agTurn([
    { id: "a", name: "Read", summary: "x.md", running: false, ok: true, startedAt: 1 },
  ]));
  assert.ok(!/gv-agents/.test(html), "a turn that spawned nothing must be unchanged: " + html);
});

test("28c. rows reuse .trow — no second row component was invented", () => {
  const html = T.turnResponse(agTurn(AG_FIX.toolRuns));
  assert.ok(!/gv-arow|agent-row|class="arow/.test(html),
    "the roster must reuse .trow, not introduce a parallel class");
});

test("28d. the live agent renders run, the finished ones render ok", () => {
  const html = T.turnResponse(agTurn(AG_FIX.toolRuns));
  assert.strictEqual((html.match(/<button class="trow run"/g) || []).length, 1);
  assert.strictEqual((html.match(/<button class="trow ok"/g) || []).length, 3);
});

/* The check that matters is not "does the string `onerror=` appear" -- it does,
   harmlessly, inside escaped text. It is whether a payload can CLOSE a tag or
   CLOSE an attribute. Those are the two shapes tested here. */
test("28e. a hostile agent summary cannot open a tag", () => {
  const html = T.turnResponse(agTurn([
    { id: "x", name: "Agent", running: true, ok: null, startedAt: 1,
      summary: 'Explore: <img src=x onerror="alert(1)"><script>bad()</' + "script>" },
  ]));
  assert.ok(!/<img|<script/i.test(html), "a tag was opened by wire text: " + html);
  assert.ok(/&lt;img/.test(html), "and it is still readable, just inert");
});

test("28f. a hostile agent id or kind cannot close an attribute", () => {
  const html = T.turnResponse(agTurn([
    { id: 'x" onclick="steal()', name: "Agent", running: true, ok: null, startedAt: 1,
      summary: 'a" onmouseover="x(): y' },
  ]));
  /* the attack shape: a raw quote that ENDS the attribute, followed by a live
     handler. Escaped payloads read `&quot; onclick=&quot;` and cannot do this. */
  assert.ok(!/"\s*on[a-z]+\s*=/i.test(html), "an attribute was closed by wire text: " + html);
  assert.ok(/&quot; onclick=/.test(html), "the payload should survive, escaped, in the id");
});

test("28g. 20 agents render 12 rows and say how many were dropped", () => {
  const many = Array.from({ length: 20 }, (_, i) => ({
    id: "id" + i, name: "Agent", summary: "Explore: job " + i,
    running: false, ok: true, startedAt: 1, endedAt: 2,
  }));
  const html = T.turnResponse(agTurn(many));
  assert.strictEqual((html.match(/<button class="trow /g) || []).length, 12,
    "the roster must be bounded like the tool rows");
  assert.ok(/8 earlier agents/.test(html), "a silent truncation reads as the whole fan-out");
  assert.ok(/job 19/.test(html) && !/job 0</.test(html),
    "it keeps the RECENT ones — those are the ones still moving");
});

test("28h. a row with nothing to correlate on is shown but disabled, with a reason", () => {
  /* two ways a row can be unopenable: no tool_use id (no row identity) and no
     description (nothing for agentMatch() to join on). Both must still RENDER --
     the work happened -- and both must decline to look like a link. */
  [
    { id: null, name: "Agent", summary: "Explore: orphan", running: true, ok: null, startedAt: 1 },
    { id: "toolu_1", name: "Agent", summary: "Explore", running: true, ok: null, startedAt: 1 },
  ].forEach(run => {
    const html = T.turnResponse(agTurn([run]));
    assert.ok(/<button class="trow run" type="button" disabled/.test(html),
      "must not pretend to be openable: " + html);
    assert.ok(/title="Nothing to open/.test(html), "and it must say why");
    assert.ok(!/data-agentrow/.test(html), "an unopenable row carries no open handle");
    assert.ok(/class="trow run"/.test(html), "the row itself still renders");
  });
});

test("28l. an openable row carries the correlation keys, not just an id", () => {
  const html = T.turnResponse(agTurn(AG_FIX.toolRuns));
  assert.ok(/data-agentrow="toolu_/.test(html), "row identity, for focus and for tests");
  assert.ok(/data-agkind="Explore"/.test(html), "the type half of the join");
  assert.ok(/data-agdesc="Audit model PRD pages"/.test(html), "the description half of the join");
});

test("28i. the roster sits inside [data-aturn], so patchTurn() covers it", () => {
  const html = T.turnResponse(agTurn(AG_FIX.toolRuns));
  const anchor = html.indexOf("data-aturn");
  const roster = html.indexOf("gv-agents");
  assert.ok(anchor >= 0 && roster > anchor,
    "outside the patch anchor the roster would go stale mid-stream");
  assert.ok(html.trim().endsWith("</div>"), "the anchor element must still close the block");
});

test("28q. a roster row never falls back to the UA button colour", () => {
  /* design-qa 20260819-004318-adf0df, all 8 states: button.trow computed
     rgb(0,0,0). A <button> does NOT inherit colour -- the UA paints buttontext
     (black) -- so the "without looking like one" reset was incomplete:
     div.trow inherits the token ink, button.trow carried UA black. Latent
     today (every glyph sits in .tname/.tsum/.tverdict), live the moment any
     bare text or currentColor lands inside a row. Comments stripped and only
     the real rule matched -- the 24a lesson. */
  const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const rule = css.match(/button\.trow\{([^}]*)\}/);
  assert.ok(rule, "the button.trow reset rule must exist");
  const colour = rule[1].match(/(?:^|;)\s*color\s*:\s*([^;}]+)/);
  assert.ok(colour, "the reset must declare a colour -- a button does not inherit one");
  assert.ok(/^(inherit|var\(--[a-z-]+\))$/.test(colour[1].trim()),
    "and it must resolve through the token system, not a literal: " + colour[1].trim());
});

test("28r. the governance chip paints the token focus ring, not the UA fallback", () => {
  /* design-qa 20260819-004318-adf0df rows 9-12: button.gv-chip had no
     :focus-visible rule while every sibling control (button.trow:825,
     .gv-thinkbtn:1474) carries the token ring — the chip fell back to the UA
     ring, off-token in BOTH themes. Comments stripped and only the real rule
     matched — the 24a lesson. */
  const css = fs.readFileSync(path.join(__dirname, "static", "panel.css"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const rule = css.match(/\.gv-chip:focus-visible\{([^}]*)\}/);
  assert.ok(rule, "the .gv-chip:focus-visible rule must exist");
  assert.ok(/outline\s*:\s*2px solid var\(--acc\)/.test(rule[1]),
    "and it must paint the same token ring as button.trow / .gv-thinkbtn: " + rule[1]);
  assert.ok(!/\.gv-chip[^{]*\{[^}]*outline\s*:\s*(none|0)/.test(css),
    "no later chip rule may cancel the ring");
});

test("28j. every row carries visible text — a row is never a bare dot", () => {
  const html = T.turnResponse(agTurn(AG_FIX.toolRuns));
  const rows = html.split('<button class="trow ').slice(1);
  rows.forEach((r, i) => {
    const text = r.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    assert.ok(text.length > 3, "row " + i + " has no accessible name: " + JSON.stringify(text));
  });
});

test("28k. per-turn open state is NEVER persisted — uids are per-page-load", () => {
  /* turnUid() is a monotonic in-memory counter, so a uid means nothing after a
     reload. Persisting a uid-keyed map would make a stale key collide with a
     fresh turn and attach someone else's open panel to it. */
  const persisted = Object.keys(T.loadLayout());
  ["govOpen", "thinkOpen", "agentOpen", "toolOpen", "agentsFold"].forEach(k =>
    assert.ok(!persisted.includes(k),
      k + " is uid- or id-keyed and must not be written to localStorage"));
});

test("28m. both streaming patch anchors survive the new blocks", () => {
  /* patchStreaming() writes tokens into [data-resp] and the ticker into
     [data-runstrip]; patchTurn() replaces [data-aturn]. Adding a roster and a
     log between them must not displace any of the three, or streaming silently
     falls back to a full render per token — the exact cost the patch path exists
     to avoid. */
  const html = T.turnResponse({ uid: "t9", streaming: true, response: "partial text",
                                tools: ["Agent"], toolRuns: AG_FIX.toolRuns });
  ["data-aturn=\"t9\"", "data-resp=\"t9\"", "data-runstrip=\"t9\""].forEach(a =>
    assert.ok(html.indexOf(a) !== -1, "missing patch anchor " + a));
});

test("28o. a transcript-replayed turn shows NO roster, because none was recorded", () => {
  /* transcriptTurns() (01-state.js:509) builds replayed turns with `tools` — flat
     names — and never `toolRuns`, because a transcript on disk records no
     lifecycle. The roster is therefore a LIVE surface. Deriving one from the
     flat names would mean inventing a state, a summary and an elapsed time for
     agents whose outcome was never written down. The session-level subagent fold
     is what covers replayed sessions, and it reads the transcripts themselves. */
  const replayed = { uid: "t9", transcript: true, streaming: false,
                     response: "an answer", tools: ["Agent", "Agent", "Read"] };
  const html = T.turnResponse(replayed);
  assert.ok(!/gv-agents/.test(html), "a replayed turn cannot know what its agents did");
  assert.ok(/2 tool calls|3 tool calls/.test(html), "it still says what ran: " + html);
});

test("28p. an unfenced governance run never reaches the rendered turn body", () => {
  /* L2 of the parseGov unfenced fix (test_governance.js §9 is L1): the strip
     must survive the REAL render path — mdHtml(gvBody(...)) inside
     turnResponse — not just the projection. Verified live 2026-08-19 that the
     unfenced block leaked into bodies as governance soup. */
  const html = T.turnResponse({ uid: "t9", streaming: false,
    response: "Answer.\nINPUT: x\nTYPE: task", tools: [], toolRuns: [] });
  assert.ok(!/INPUT:|TYPE:/.test(html), "governance soup reached the DOM: " + html);
  assert.ok(/Answer\./.test(html), "the real answer must survive the strip");
  /* and the sentence-not-block rule holds in the DOM too */
  const prose = T.turnResponse({ uid: "t9", streaming: false,
    response: "First.\nTYPE: the parameter kind matters here\nAfter.",
    tools: [], toolRuns: [] });
  assert.ok(/TYPE: the parameter kind matters here/.test(prose),
    "a lone key-looking line inside prose was eaten by the strip: " + prose);
});

test("28n. turnResponse is pure — rendering a turn twice gives the same string", () => {
  const t = { uid: "t9", streaming: true, response: "x",
              tools: ["Agent"], toolRuns: AG_FIX.toolRuns };
  const before = JSON.stringify(t);
  const a = T.turnResponse(t), b = T.turnResponse(t);
  assert.strictEqual(a, b, "a renderer with side effects would drift under the patch loop");
  assert.strictEqual(JSON.stringify(t), before, "the renderer must not mutate the turn");
});

/* ── 30. the loader opens into the turn's step log ──────────────────────────── */

const logTurn = (runs, open) => {
  T.S.thinkOpen = open ? { t9: true } : {};
  return T.turnResponse({ uid: "t9", streaming: true, response: "…",
                          tools: runs.map(r => r.name), toolRuns: runs });
};
const RUNS3 = [
  { id: "a", name: "Read", summary: "os/engines/LEDGER.md", running: false, ok: true },
  { id: "b", name: "Bash", summary: "bats placement.bats", running: false, ok: false },
  { id: "c", name: "Agent", summary: "Explore: audit pages", running: true, ok: null },
];

test("30a. the loader is a button, so it is reachable by keyboard", () => {
  const html = logTurn(RUNS3, false);
  assert.ok(/<button class="gv-thinkbtn" type="button" data-thinkopen="t9"/.test(html), html.slice(-400));
  assert.ok(/aria-expanded="false"/.test(html), "a collapsed control must say it is collapsed");
});

test("30b. the log is CLOSED by default — the turn looks as it does today", () => {
  assert.ok(!/gv-log/.test(logTurn(RUNS3, false)), "an unopened log must not render");
});

test("30c. opened, it renders one line per run, coloured by outcome", () => {
  const html = logTurn(RUNS3, true);
  assert.ok(/<div class="gv-log">/.test(html));
  assert.strictEqual((html.match(/class="gv-ln /g) || []).length, 3);
  assert.ok(/class="gv-ln ok">Read · os\/engines\/LEDGER.md</.test(html));
  assert.ok(/class="gv-ln bad">Bash · bats placement.bats</.test(html));
  assert.ok(/class="gv-ln run">Agent · Explore: audit pages</.test(html));
  assert.ok(/aria-expanded="true"/.test(html));
});

test("30d. data-runstrip still holds ONLY a text node — the ticker contract", () => {
  /* patchStreaming() writes textContent into this node once a second. If the
     wrapper had put an element inside it, the ticker would erase it. */
  const html = logTurn(RUNS3, true);
  const m = html.match(/data-runstrip="t9"[^>]*>([^<]*)</);
  assert.ok(m, "the runstrip anchor is gone: " + html.slice(-400));
  assert.ok(!/[<>]/.test(m[1]), "the anchor must contain text and nothing else: " + m[1]);
});

test("30e. a settled turn has no loader and no log", () => {
  T.S.thinkOpen = { t9: true };
  const html = T.turnResponse({ uid: "t9", streaming: false, response: "done",
                                tools: ["Read"], toolRuns: RUNS3 });
  assert.ok(!/gv-thinkbtn|gv-log/.test(html),
    "the log belongs to a turn in flight; a finished turn shows its answer");
});

test("30f. a hostile tool summary cannot open a tag in the log", () => {
  const html = logTurn([{ id: "a", name: "Bash", running: true, ok: null,
                          summary: '<img src=x onerror=1>' }], true);
  assert.ok(!/<img/.test(html), "unescaped markup in the log: " + html);
  assert.ok(/&lt;img/.test(html));
});

test("30g. the log is bounded in the DOM, not just in the projection", () => {
  const many = Array.from({ length: 2000 }, (_, i) => ({
    id: "i" + i, name: "Bash", summary: "step " + i, running: false, ok: true }));
  const html = logTurn(many, true);
  assert.strictEqual((html.match(/class="gv-ln /g) || []).length, 61,
    "60 lines plus the one saying what was dropped");
  assert.ok(/1940 earlier steps not shown/.test(html));
});

/* ── 29. focus survives a patch ──────────────────────────────────────────────
   patchTurn() replaces the whole assistant block via outerHTML on every tool
   frame. Anything focused inside it is destroyed, so a keyboard user gets thrown
   to <body> several times a second during a fan-out. This already affected the
   shipped `output`/`terminal` buttons; a roster of clickable rows made it worth
   fixing rather than documenting. */

test("29a. a focused control is identified by the key its handler already uses", () => {
  const node = { getAttribute: k => (k === "data-agentrow" ? "toolu_42" : null) };
  assert.strictEqual(T.focusKeyOf(node), '[data-agentrow="toolu_42"]');
});

test("29b. a hostile id cannot break out of the restore selector", () => {
  const node = { getAttribute: k => (k === "data-toolout" ? 'x"] , script[src' : null) };
  const key = T.focusKeyOf(node);
  assert.strictEqual(key, '[data-toolout="x\\"] , script[src"]',
    "the quote must be escaped, or the selector would match other elements");
});

test("29c. a node with none of those keys is not restored", () => {
  assert.strictEqual(T.focusKeyOf({ getAttribute: () => null }), null);
  assert.strictEqual(T.focusKeyOf(null), null);
  assert.strictEqual(T.focusKeyOf({}), null, "a node with no getAttribute must not throw");
});

test("29d. patchTurn puts focus back on the same control it destroyed", () => {
  const prevQ = sandbox.document.querySelector;
  const prevA = Object.getOwnPropertyDescriptor(sandbox.document, "activeElement");
  try {
    let focused = 0;
    const row = { getAttribute: k => (k === "data-agentrow" ? "toolu_7" : null) };
    const replacement = { focus: () => { focused++; }, getAttribute: () => null };
    const block = {
      contains: n => n === row,
      closest: () => null,
      /* the restore is SCOPED to the replaced block, so the lookup happens here
         and not on the document */
      querySelector: sel => (sel === '[data-agentrow="toolu_7"]' ? replacement : null),
      set outerHTML(v) { this._html = v; },
      get outerHTML() { return this._html; },
    };
    sandbox.document.activeElement = row;
    sandbox.document.querySelector = sel =>
      sel.indexOf("data-aturn") !== -1 ? block : null;

    const ok = T.patchTurn({ uid: "t9", streaming: true, response: "x", tools: [], toolRuns: [] });
    assert.strictEqual(ok, true, "the block was found, so the patch must report success");
    assert.strictEqual(focused, 1, "focus was not restored after the block was replaced");
  } finally {
    sandbox.document.querySelector = prevQ;
    if (prevA) Object.defineProperty(sandbox.document, "activeElement", prevA);
    else delete sandbox.document.activeElement;
  }
});

test("29f. the restore is scoped to the patched turn, not the whole document", () => {
  /* Two turns can hold the same data-* value — a side chat replaying the same
     session, or simply a document-wide lookup finding the first match. A global
     querySelector would move focus into a DIFFERENT turn, which is worse than
     losing it. The lookup must happen inside the block that was replaced. */
  const prevQ = sandbox.document.querySelector;
  const prevA = Object.getOwnPropertyDescriptor(sandbox.document, "activeElement");
  try {
    let inThisTurn = 0, inAnotherTurn = 0;
    const row = { getAttribute: k => (k === "data-agentrow" ? "toolu_7" : null) };
    const block = {
      contains: n => n === row,
      closest: () => null,
      /* this turn's copy is gone from the DOM and has no replacement yet */
      querySelector: () => null,
      set outerHTML(v) { this._html = v; },
      get outerHTML() { return this._html; },
    };
    sandbox.document.activeElement = row;
    sandbox.document.querySelector = sel => {
      if (sel.indexOf("data-aturn") !== -1) return block;
      inAnotherTurn++;                       /* a document-wide lookup happened */
      return { focus: () => { inAnotherTurn++; }, getAttribute: () => null };
    };
    T.patchTurn({ uid: "t9", streaming: true, response: "x", tools: [], toolRuns: [] });
    assert.strictEqual(inThisTurn, 0);
    assert.strictEqual(inAnotherTurn, 0,
      "focus was searched for outside the patched block — it could land in another turn");
  } finally {
    sandbox.document.querySelector = prevQ;
    if (prevA) Object.defineProperty(sandbox.document, "activeElement", prevA);
    else delete sandbox.document.activeElement;
  }
});

test("29e. patchTurn never STEALS focus from outside the turn it patched", () => {
  const prevQ = sandbox.document.querySelector;
  const prevA = Object.getOwnPropertyDescriptor(sandbox.document, "activeElement");
  try {
    let focused = 0;
    /* the operator is typing in the composer, which is not inside this block */
    const elsewhere = { getAttribute: k => (k === "data-agentrow" ? "toolu_7" : null) };
    const block = {
      contains: () => false,
      closest: () => null,
      set outerHTML(v) { this._html = v; },
      get outerHTML() { return this._html; },
    };
    sandbox.document.activeElement = elsewhere;
    sandbox.document.querySelector = sel =>
      sel.indexOf("data-aturn") !== -1 ? block
      : { focus: () => { focused++; }, getAttribute: () => null };

    T.patchTurn({ uid: "t9", streaming: true, response: "x", tools: [], toolRuns: [] });
    assert.strictEqual(focused, 0, "focus must stay where the operator put it");
  } finally {
    sandbox.document.querySelector = prevQ;
    if (prevA) Object.defineProperty(sandbox.document, "activeElement", prevA);
    else delete sandbox.document.activeElement;
  }
});

/* ── 28. the Teamsutra selection bubble (11-teamsutra.js) ──────────────── */

const TS_SRC = fs.readFileSync(path.join(__dirname, "static", "js", "11-teamsutra.js"), "utf8");

/* Same shape as actDom(), with the two selector forms 11-teamsutra actually
   uses and the activity stub lacks: comma lists ("input, textarea, .smenu")
   and the [id^="dir-"] prefix match. Extended HERE, not in actDom — the
   activity tests keep their own smaller contract. */
function tsDom() {
  function matchOne(n, sel) {
    if (!n || !n._attrs) return false;
    sel = sel.trim();
    let m = sel.match(/^\[id\^="([^"]+)"\]$/);
    if (m) return typeof n.id === "string" && n.id.indexOf(m[1]) === 0;
    if (sel[0] === "[") return n.hasAttribute(sel.slice(1, -1));
    if (sel[0] === ".") return n.classList.contains(sel.slice(1));
    if (sel[0] === "#") return n.id === sel.slice(1);
    m = sel.match(/^([a-z]+)\.([\w-]+)$/i);            // e.g. nav.rail
    if (m) return n.tagName === m[1].toUpperCase() && n.classList.contains(m[2]);
    m = sel.match(/^\.([\w-]+)\[([\w-]+)\]$/);          // e.g. .pane[data-sess]
    if (m) return n.classList.contains(m[1]) && n.hasAttribute(m[2]);
    return n.tagName === sel.toUpperCase();
  }
  function matchSel(n, sel) {
    return String(sel).split(",").some(s => matchOne(n, s));
  }
  function mkEl(tag) {
    return {
      tagName: String(tag).toUpperCase(), nodeType: 1, id: "", _text: "", _html: "",
      get parentElement() { return this._parent; },
      _attrs: {}, _kids: [], _parent: null, _listeners: {}, style: {},
      classList: {
        _s: new Set(),
        add(...c) { c.forEach(x => this._s.add(x)); },
        contains(c) { return this._s.has(c); },
      },
      get textContent() { return this._text; },
      set textContent(v) { this._text = String(v); },
      get innerHTML() { return this._html; },
      set innerHTML(v) { this._html = String(v); this._kids = []; },
      setAttribute(k, v) { this._attrs[k] = String(v); },
      getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; },
      hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k); },
      addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); },
      appendChild(c) { c._parent = this; this._kids.push(c); return c; },
      querySelector() { return null; },
      closest(sel) { let n = this; while (n) { if (matchSel(n, sel)) return n; n = n._parent; } return null; },
    };
  }
  const head = mkEl("head"); const body = mkEl("body");
  function byId(node, id) {
    let hit = null;
    (function walk(n) { (n._kids || []).forEach(k => { if (!hit && k.id === id) hit = k; walk(k); }); })(node);
    return hit;
  }
  const doc = {
    readyState: "complete", head, body, _listeners: {},
    createElement: t => mkEl(t),
    getElementById: id => byId(head, id) || byId(body, id),
    addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); },
  };
  return { doc, mkEl };
}

function mountTeamsutra() {
  const { doc, mkEl } = tsDom();
  const box = {
    console, document: doc, setTimeout: fn => fn(), clearTimeout: () => {},
    Date, Math, JSON, Set, Object, Array, String, Number, Boolean, RegExp, Error,
  };
  box.window = box; box.globalThis = box;
  vm.createContext(box);
  new vm.Script(TS_SRC, { filename: "11-teamsutra.js#ts-test" }).runInContext(box);
  return { doc, mkEl, box };
}

test("28a. mounts once: injects #ts-style, registers listeners, re-load is a no-op", () => {
  const m = mountTeamsutra();
  assert.ok(m.doc.getElementById("ts-style"), "must inject its own <style id=ts-style>");
  const before = (m.doc._listeners.mouseup || []).length;
  assert.ok(before >= 1, "must listen for mouseup on the document");
  new vm.Script(TS_SRC, { filename: "11-teamsutra.js#reload" }).runInContext(m.box);
  assert.strictEqual((m.doc._listeners.mouseup || []).length, before,
    "a double-load must hit the __tsMounted guard, not add listeners again");
});

test("28b. resolver: per-turn data-turn-domain wins, and an EMPTY one resolves null", () => {
  const m = mountTeamsutra();
  const turn = m.mkEl("div"); turn.setAttribute("data-turn-domain", "dref-abc123");
  const p = m.mkEl("p"); turn.appendChild(p);
  assert.strictEqual(JSON.stringify(m.box.__tsResolve(p)), JSON.stringify({ ref: "dref-abc123", kind: "turn" }));
  // A transcript-style turn carries the attribute EMPTY -- that is "nothing
  // classified this", and the resolver must fall through, never return "".
  const bare = m.mkEl("div"); bare.setAttribute("data-turn-domain", "");
  const q = m.mkEl("p"); bare.appendChild(q);
  assert.strictEqual(m.box.__tsResolve(q), null);
});

test("28c. resolver: [data-ref] is trusted only on the departments screen", () => {
  const m = mountTeamsutra();
  const tile = m.mkEl("button"); tile.setAttribute("data-ref", "dref-tile01");
  const span = m.mkEl("span"); tile.appendChild(span);
  m.box.S = { screen: "departments" };
  assert.strictEqual(JSON.stringify(m.box.__tsResolve(span)), JSON.stringify({ ref: "dref-tile01", kind: "tile" }));
  // The SAME attribute appears on routing-chart nodes inside chat, where it
  // is not a department address. Off the departments screen: null.
  m.box.S = { screen: "charters" };
  assert.strictEqual(m.box.__tsResolve(span), null);
});

test("28d. resolver: directory sections and charter rows; plain prose is null", () => {
  const m = mountTeamsutra();
  m.box.S = { screen: "departments" };
  const dir = m.mkEl("section"); dir.id = "dir-dref-dir999";
  const t = m.mkEl("p"); dir.appendChild(t);
  assert.strictEqual(JSON.stringify(m.box.__tsResolve(t)), JSON.stringify({ ref: "dref-dir999", kind: "directory" }));
  const row = m.mkEl("tr"); row.setAttribute("data-charter", "C-abcdef1234567890");
  const td = m.mkEl("td"); row.appendChild(td);
  assert.strictEqual(JSON.stringify(m.box.__tsResolve(td)),
    JSON.stringify({ charter: "C-abcdef1234567890", kind: "charter" }));
  const lone = m.mkEl("p");
  assert.strictEqual(m.box.__tsResolve(lone), null,
    "unattributed prose must resolve to null — never to a guess");
});

test("28e. chrome exclusion: selections in inputs, menus, the rail and the bubble itself never show it", () => {
  const m = mountTeamsutra();
  for (const make of [
    () => m.mkEl("input"), () => m.mkEl("textarea"), () => m.mkEl("button"),
    () => { const e = m.mkEl("div"); e.classList.add("smenu"); return e; },
    () => { const e = m.mkEl("div"); e.classList.add("composer"); return e; },
    () => { const e = m.mkEl("div"); e.classList.add("sidewrap"); return e; },
    () => { const e = m.mkEl("nav"); e.classList.add("rail"); return e; },
    () => { const e = m.mkEl("button"); e.id = "ts-bubble"; return e; },
  ]) {
    const host = make();
    const inner = m.mkEl("span"); host.appendChild(inner);
    assert.strictEqual(m.box.__tsInChrome(inner), true,
      "selection inside <" + host.tagName + (host.id ? "#" + host.id : "") + "> must be excluded");
  }
  const prose = m.mkEl("p");
  assert.strictEqual(m.box.__tsInChrome(prose), false, "plain prose is not chrome");
});

/* ── 29. the Teamsutra seed budgeter (03-org.js) ───────────────────────── */

test("29a. a null department seeds 'none' and never guesses", () => {
  T.DOMAINS = []; T.CHARTERS = [];
  const seed = T.tsBuildSeed({ text: "what is this", screen: "evals",
                               domainRef: null, charterId: null });
  assert.ok(seed.indexOf("DEPARTMENT: none") !== -1,
    "a selection nothing classified must say so");
  assert.ok(seed.indexOf("do not guess") !== -1, "the persona must forbid guessing");
  assert.ok(seed.length <= T.TS_SEED_MAX);
});

test("29b. byte-exact budget: the largest org + longest selection never exceeds the cap, and says it truncated", () => {
  /* Build an org bigger than the budget could ever hold: 12-deep chain, 80
     children, 120 charters with long titles. */
  const doms = [];
  let parent = null;
  for (let i = 0; i < 12; i++) {
    const ref = "dref-chain" + i;
    doms.push({ ref, name: "Department Layer " + i + " With A Deliberately Long Name",
                parent_ref: parent, ts_minted_ms: i });
    parent = ref;
  }
  for (let i = 0; i < 80; i++) {
    doms.push({ ref: "dref-kid" + i, name: "Subdepartment Number " + i + " Of Many",
                parent_ref: "dref-chain11", ts_minted_ms: 100 + i });
  }
  T.DOMAINS = doms;
  T.CHARTERS = Array.from({ length: 120 }, (_, i) => ({
    id: "C-" + i, domain_ref: "dref-chain11",
    title: "Charter " + i + ": a title long enough to blow any budget wide open when repeated",
    status: "shipped" }));
  const seed = T.tsBuildSeed({ text: "x".repeat(4000), screen: "departments",
                               domainRef: "dref-chain11" });
  assert.ok(seed.length <= T.TS_SEED_MAX,
    "seed is " + seed.length + " chars — the server truncates at " + T.TS_SEED_MAX + " SILENTLY");
  assert.ok(seed.indexOf("[context truncated") !== -1,
    "a cut seed must SAY it was cut — a silently halved briefing answers confidently from half a department");
  assert.ok(seed.indexOf("DEPARTMENT: ") !== -1, "the parent chain survives every cut");
  assert.ok(seed.indexOf("SELECTED TEXT") !== -1, "the selection survives every cut");
});

test("29c. a small org fits whole: chain, children and charters all present, no marker", () => {
  T.DOMAINS = [
    { ref: "dref-root", name: "Asawa", parent_ref: null, ts_minted_ms: 1 },
    { ref: "dref-os", name: "Sutra OS", parent_ref: "dref-root", ts_minted_ms: 2 },
    { ref: "dref-ts", name: "Teamsutra", parent_ref: "dref-os", ts_minted_ms: 3 },
  ];
  T.CHARTERS = [{ id: "C-x", domain_ref: "dref-os", title: "Protocol System", status: "shipped" }];
  const seed = T.tsBuildSeed({ text: "short", screen: "departments", domainRef: "dref-os" });
  assert.ok(seed.indexOf("Sutra OS") !== -1);
  assert.ok(seed.indexOf("SUB-DEPARTMENTS: Teamsutra") !== -1);
  assert.ok(seed.indexOf("CHARTERS: Protocol System") !== -1);
  assert.ok(seed.indexOf("[context truncated") === -1, "nothing was cut, so nothing may claim it was");
});

test("28f. panel.html loads 11-teamsutra before 09-tail, so boot() stays last", () => {
  const h = panelHtml;
  // Match the script TAGS, not bare filenames — the names also appear in
  // prose comments earlier in the file. The src carries a ?v=<token> cache-bust
  // the server substitutes per build, so the query is optional here: the
  // invariant under test is the ORDER of the two tags, not their query string.
  const tagAt = name =>
    h.search(new RegExp('<script src="/static/js/' + name.replace('.', '\\.') + '(\\?[^"]*)?">'));
  const ts = tagAt("11-teamsutra.js");
  const tail = tagAt("09-tail.js");
  assert.ok(ts !== -1, "panel.html must register 11-teamsutra.js");
  assert.ok(tail !== -1, "panel.html must still register 09-tail.js");
  assert.ok(ts < tail, "11-teamsutra.js must load before 09-tail.js (test 21b's invariant)");
});

/* ── 31. per-turn controls survive patchTurn — found by driving the LIVE app ──
   patchTurn() replaces a turn's DOM mid-stream; per-render onclick bindings die
   with the replaced nodes, so the thinking toggle (and the shipped output/
   terminal buttons) were dead exactly while a turn streamed. The five per-turn
   controls are now handled by ONE delegated listener that no patch can kill. */

/* a synthetic event whose target chains .closest() the way a real one does:
   hits[sel] is what that selector resolves to */
const evFor = hits => ({ target: { closest: sel => hits[sel] || null } });
const IN_TURN = { ".turn": {} };   /* every control below lives inside a turn */
/* the handler ends in render(), which needs the full DOM this stub does not
   have. State changes land BEFORE render, so a no-op render isolates exactly
   what these tests assert. Top-level function declarations in a non-strict vm
   script live on the global, so the swap is visible inside the handler. */
function withNoopRender(fn){
  const prev = sandbox.render;
  sandbox.render = () => {};
  try { return fn(); } finally { sandbox.render = prev; }
}

test("31a. the thinking toggle works with no per-render binding at all", () => {
  T.S.thinkOpen = {};
  const btn = { dataset: { thinkopen: "t42" } };
  withNoopRender(() => {
    T.turnControlClick(evFor({ ...IN_TURN, "[data-thinkopen]": btn }));
    assert.strictEqual(T.S.thinkOpen["t42"], true, "first click opens");
    T.turnControlClick(evFor({ ...IN_TURN, "[data-thinkopen]": btn }));
    assert.strictEqual(T.S.thinkOpen["t42"], undefined, "second click closes");
  });
});

test("31b. the governance chip and tool output toggle through the same path", () => {
  T.S.govOpen = {}; T.S.toolOpen = {};
  withNoopRender(() => {
    T.turnControlClick(evFor({ ...IN_TURN,
      "[data-govopen]": { dataset: { govopen: "t42" } } }));
    assert.strictEqual(T.S.govOpen["t42"], true);
    T.turnControlClick(evFor({ ...IN_TURN,
      "[data-toolout]": { dataset: { toolout: "toolu_9" } } }));
    assert.strictEqual(T.S.toolOpen["toolu_9"], true);
  });
});

test("31c. a click OUTSIDE a turn is never intercepted", () => {
  T.S.thinkOpen = {};
  /* same button, but nothing resolves .turn — e.g. a control in the rail */
  withNoopRender(() =>
    T.turnControlClick(evFor({ "[data-thinkopen]": { dataset: { thinkopen: "t42" } } })));
  assert.strictEqual(Object.keys(T.S.thinkOpen).length, 0,
    "the delegated listener must not reach outside chat turns");
});

test("31d. the five delegated controls have NO per-render binding left", () => {
  /* the whole point: if wire() also bound them, one click would toggle twice
     and every control would appear dead. The source must contain no
     querySelectorAll binding for any of the five. */
  const src = require("fs").readFileSync(__dirname + "/static/js/07-loaders.js", "utf8");
  ["data-thinkopen", "data-govopen", "data-toolout", "data-toolterm", "data-agentrow"]
    .forEach(k => {
      const bound = new RegExp('panes\\.querySelectorAll\\("\\[' + k + '\\]"\\)\\.forEach').test(src);
      assert.ok(!bound, k + " is still bound per-render — a click would fire twice");
    });
});

/* The harness runs tests synchronously and the file ends in process.exit, so a
   returned promise would never be awaited — its assertions would silently not
   run. Async checks register here and the exit waits for them. */
const ASYNC_CHECKS = [];

test("31e. the roster drill-down works through delegation and captures before await", () => {
  /* the async body must read every DOM value BEFORE its first await — the row
     may be patched away while loadAgents is in flight. Proven by handing it a
     row whose dataset is DESTROYED synchronously after the call returns. */
  const rowDataset = { agkind: "Explore", agdesc: "count things" };
  const row = {
    dataset: rowDataset,
    closest: sel => sel === ".pane[data-sess]" ? { dataset: { sess: "sid-1" } }
           : sel === ".gv-agents" ? { querySelectorAll: () => [{ dataset: { ...rowDataset } }] }
           : sel === ".turn" ? {} : null,
  };
  T.S.agentsFold = {}; T.S.agents = { "sid-1": [] }; T.S.agentNote = {};
  const prevRender = sandbox.render;
  sandbox.render = () => {};
  T.turnControlClick(evFor({ ...IN_TURN, "[data-agentrow]": row }));
  /* synchronous part: the fold opened immediately */
  assert.strictEqual(T.S.agentsFold["sid-1"], true, "the fold opens on click, before any fetch");
  /* now the row disappears, as a patch would make it */
  delete rowDataset.agkind; delete rowDataset.agdesc;
  /* the async continuation still runs to an HONEST note, not a crash.
     render stays a no-op until it settles, then is restored. Registered, not
     returned: the exit below waits on ASYNC_CHECKS. */
  ASYNC_CHECKS.push(new Promise(r => setTimeout(r, 20)).then(() => {
    sandbox.render = prevRender;
    /* only the continuation's OWN writes are asserted — tests that ran after
       31e legitimately reset S.agentsFold, and asserting state they own would
       couple this check to test ordering */
    assert.ok(T.S.agentNote["sid-1"],
      "no transcript to join on -> the fold must SAY so: " + JSON.stringify(T.S.agentNote));
  }));
});

/* ── 32. the fold renders for a live panel session — found by driving the app ── */

test("32a. an explicit open request renders the fold even before the session is real", () => {
  T.S.agentsFold = { "sid-9": true };
  T.S.agents = { "sid-9": [] };
  T.S.agentNote = { "sid-9": "No subagent transcript on disk for this agent yet." };
  const html = T.agentsFold({ id: "sid-9", real: false });
  assert.ok(html && /agents open/.test(html),
    "the operator clicked; showing nothing at all was the live-run bug");
  assert.ok(/No subagent transcripts on disk|No subagent transcript on disk/.test(html),
    "and what renders is the honest empty state, not a blank container");
});

test("32b. an UNOPENED non-real session still shows nothing — no new noise", () => {
  T.S.agentsFold = {};
  T.S.agents = {};
  T.S.agentNote = {};
  assert.strictEqual(T.agentsFold({ id: "sid-9", real: false }), "",
    "the fix must not put an empty fold under every fresh session");
});

test("32c. a real session with agents behaves exactly as before", () => {
  T.S.agentsFold = {};
  T.S.agents = { "sid-9": [{ id: "agent-a", title: "t", steps: 1, tools: [], mtime: 1 }] };
  const closedHtml = T.agentsFold({ id: "sid-9", real: true });
  assert.ok(/1 subagent/.test(closedHtml), "collapsed head still renders");
  assert.ok(!/agents open/.test(closedHtml), "and stays collapsed until asked");
});

/* ── 33. task.apply card states (APPLY-DESIGN v1.1) ─────────────────────── */

/* v3 board (2026-08-21): the card speaks the operator's language. These pin
   the click contract (data-tsact/data-tid) AND the voice — no status codes,
   ids or raw errors on the face of the card. */
const TS_DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n ctx\n-old line\n+new line\n";

test("33a. a reviewed task with a diff offers Apply; without one it cannot; no bridge, no buttons", () => {
  const base = { id: "t-aaaa1111", title: "z-index bug", status: "needs_review",
                 attempts: 1, max_attempts: 3, source: {}, created_at: "2026-08-19T00:45:00+05:30" };
  sandbox.sutra = { teamsutraAction: () => Promise.resolve({}) };  // desktop bridge present
  try {
    const withDiff = T.tsCard({ ...base, diff: TS_DIFF });
    assert.ok(/data-tsact="apply" data-tid="t-aaaa1111"/.test(withDiff), "needs_review + diff renders Apply");
    assert.ok(/data-tsact="drop"[^>]*>Close this</.test(withDiff), "drop is worded Close this");
    assert.ok(/Ready for your review/.test(withDiff), "status is words");
    assert.ok(!/needs_review/.test(withDiff), "the status CODE never reaches the operator");
    const noDiff = T.tsCard({ ...base, diff: null });
    assert.ok(!/data-tsact="apply"/.test(noDiff),
      "no diff means nothing to apply — the button must not render");
  } finally { delete sandbox.sutra; }
  const cli = T.tsCard({ ...base, diff: TS_DIFF });
  assert.ok(!/data-tsact=/.test(cli), "CLI-served panel: no dead buttons");
  assert.ok(/need the desktop app/.test(cli), "and it says why");
});

test("33b. a handed-off task links its PR as a plain link and hides the old apply error", () => {
  const html = T.tsCard({ id: "t-aaaa1111", title: "t", status: "done",
    attempts: 1, max_attempts: 3, source: {}, diff: TS_DIFF,
    apply_error: "commit: BLOCKED — pre-commit gate",
    pr_url: "https://github.com/sankalpasawa/sutra/pull/999", pr_state: "open",
    applied_at: "2026-08-19T00:48:10+05:30" });
  assert.ok(/Done — your merge/.test(html), "done-with-open-PR says it is the operator's merge");
  assert.ok(/<a class="tsc-btn pri" href="https:\/\/github\.com\/sankalpasawa\/sutra\/pull\/999"/.test(html),
    "the PR is a plain anchor, never a data-tsact action");
  assert.ok(/pull request #999/.test(html), "and is named by number");
  assert.ok(!/data-tsact="apply"/.test(html), "done offers no second Apply");
  assert.ok(!/BLOCKED|Tried to apply/.test(html), "an apply error is history once a PR exists");
  assert.strictEqual(T.tsCurrentError({ status: "done", apply_error: "x", pr_url: "u" }), null);
});

test("33c. a failed apply says so in one plain sentence and offers Apply again", () => {
  sandbox.sutra = { teamsutraAction: () => Promise.resolve({}) };
  try {
    const html = T.tsCard({ id: "t-aaaa1111", title: "t", status: "needs_review",
      attempts: 1, max_attempts: 3, source: {}, diff: TS_DIFF,
      apply_error: "apply --check: error: corrupt patch at line 11" });
    assert.ok(/Tried to apply it and couldn.t: corrupt patch at line 11\./.test(html), "error in words, prefix stripped");
    assert.ok(/data-tsact="apply"[^>]*>Apply again</.test(html), "Apply still offered, relabelled");
  } finally { delete sandbox.sutra; }
});

test("33d. status words cover every state; smoke tasks wear a TEST badge", () => {
  const w = s => T.tsStatusWords({ status: s })[1];
  assert.strictEqual(w("draft"), "Waiting for you to queue it");
  assert.strictEqual(w("queued"), "In line — Sutra checks hourly");
  assert.strictEqual(w("claimed"), "Sutra is working on it");
  assert.strictEqual(w("blocked"), "Stuck — needs you");
  assert.strictEqual(w("done"), "Done");
  assert.strictEqual(T.tsStatusWords({ status: "done", pr_url: "u", pr_state: "open" })[1], "Done — your merge");
  const html = T.tsCard({ id: "t-1", title: "smoke: x", status: "queued", source: {} });
  assert.ok(/<span class="test">TEST<\/span>/.test(html), "smoke: prefix -> TEST badge");
  assert.ok(!/class="test"/.test(T.tsCard({ id: "t-2", title: "real bug", status: "queued", source: {} })));
});

test("33e. the YOU line prefers the highlight, then the operator's words, then an honest nothing", () => {
  const sel = T.tsCard({ id: "t-1", title: "t", status: "queued",
    source: { selection: "what a run may actually do", ask: "why?", screen: "teamsutra" } });
  assert.ok(/Highlighted <q>what a run may actually do<\/q>/.test(sel));
  assert.ok(/Teamsutra screen/.test(sel), "screen named in words");
  const ask = T.tsCard({ id: "t-1", title: "t", status: "queued", source: { ask: "the page shows 11", screen: "departments" } });
  assert.ok(/<q>the page shows 11<\/q>/.test(ask));
  assert.ok(/What you said<\/div>\s*<div class="b"><p class="quote">the page shows 11/.test(ask), "Details carries the full words");
  const none = T.tsCard({ id: "t-1", title: "t", status: "queued", source: {} });
  assert.ok(/Filed from the chat, nothing highlighted/.test(none));
  assert.ok(/Not kept for this task/.test(none));
  const xss = T.tsCard({ id: "t-1", title: "<b>t</b>", status: "queued", source: { selection: "<img src=x onerror=1>" } });
  assert.ok(!/<img/.test(xss) && /&lt;img/.test(xss), "selection is escaped");
});

test("33f. the change view is hunk-aware, hides headers, escapes every line, and falls back when unparseable", () => {
  const tricky = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,2 @@\n ctx <x>\n---- not a header\n+++ also content\n";
  const rows = T.tsParseDiff(tricky);
  assert.ok(Array.isArray(rows), "parses");
  const kinds = rows.map(r => r.k).join(",");
  assert.strictEqual(kinds, "file,ctx,del,add", "inside the hunk, leading --/++ are content");
  assert.strictEqual(rows[2].text, "--- not a header");
  assert.strictEqual(rows[0].text, "f.py");
  const view = T.tsChangeView(tricky);
  assert.ok(!/@@|diff --git/.test(view), "hunk and git headers never shown");
  assert.ok(/f\.py <span>· 1 removed, 1 added<\/span>/.test(view), "human count in the header");
  assert.ok(/&lt;x&gt;/.test(view) && !/<x>/.test(view), "context escaped");
  assert.strictEqual(T.tsParseDiff("just some text\nno hunks"), null);
  assert.ok(/<pre class="md-pre">just some text/.test(T.tsChangeView("just some text\nno hunks")), "fallback is escaped plain text");
  assert.ok(/Reference for support: t-9/.test(T.tsStory({ id: "t-9", status: "queued", source: {} })), "id only in Details, as support reference");
});

/* ── 30x. an OPEN empty log is never invisible ──────────────────────────────
   The founder clicked "thinking" before any tool ran, the state flipped, and
   nothing rendered — indistinguishable from a dead button. An open log now
   always draws: real lines when there are steps, one honest line when not.
   (Numbered 30h/30i in the fix plan; placed here after a cross-session merge
   renumbered the neighborhood.) */

test("30h. an OPEN log with zero runs renders exactly one honest line", () => {
  T.S.thinkOpen = { t9: true };
  const html = T.turnResponse({ uid: "t9", streaming: true, response: "",
                                tools: [], toolRuns: [] });
  assert.ok(/<div class="gv-log">/.test(html), "the open log must render: " + html.slice(-300));
  assert.strictEqual((html.match(/class="gv-ln /g) || []).length, 1);
  assert.ok(/nothing has run yet in this turn/.test(html));
  /* the ticker contract survives the new branch */
  const m = html.match(/data-runstrip="t9"[^>]*>([^<]*)</);
  assert.ok(m && !/[<>]/.test(m[1]), "data-runstrip must stay text-only");
  T.S.thinkOpen = {};
});

test("30i. the honest line yields to the first real step", () => {
  T.S.thinkOpen = { t9: true };
  const html = T.turnResponse({ uid: "t9", streaming: true, response: "",
    tools: ["Read"], toolRuns: [{ id: "a", name: "Read", summary: "x.md", running: true, ok: null }] });
  assert.ok(!/nothing has run yet/.test(html), "the placeholder must disappear");
  assert.strictEqual((html.match(/class="gv-ln /g) || []).length, 1, "one real line");
  assert.ok(/class="gv-ln run">Read/.test(html));
  T.S.thinkOpen = {};
});

test("30j. a CLOSED log still renders nothing — the default is unchanged", () => {
  T.S.thinkOpen = {};
  const html = T.turnResponse({ uid: "t9", streaming: true, response: "",
                                tools: [], toolRuns: [] });
  assert.ok(!/gv-log/.test(html), "closed means closed");
});

/* ── 34. the streaming caret is gated on the STRIPPED body — both writers ────
   The founder saw a lone brown caret block on its own line while a turn
   streamed pure governance preamble. Two writers draw this caret: turnResponse
   at render time and patchStreaming on every token frame. The fix earlier
   landed only in turnResponse (the second writer repainted the lone caret each
   frame), and the L2 tests written for it were dropped in a cross-session
   merge — both facts are why this section pins the SHARED builder and the
   call-site contract, not just one writer. */

test("34a. a preamble-only streamed body renders NO caret", () => {
  const html = T.streamBodyHtml({ response:
    "[INBOUND\u00b7QUERY \u00b7 TIMING:now \u00b7 CHANNEL:x \u00b7 REV:none \u00b7 RISK:low]" });
  assert.ok(!/class="caret"/.test(html), "the lone caret is back: " + html);
});

test("34b. the caret returns with real text, INSIDE the last block", () => {
  /* Position changed deliberately. The caret used to be concatenated after the
     markdown, so the DOM read `<p>text</p><span class=caret>` -- <p> is a block,
     so the caret sat on its own line, and the <p> losing :last-child brought
     back 8px of margin above it. It now goes inside the last text-bearing
     element, so it trails the final character wherever that is.
     Matched on `class="caret` without the closing quote: the class list also
     carries `blink` when the stream has stalled. */
  const html = T.streamBodyHtml({ response:
    "[INBOUND\u00b7QUERY \u00b7 TIMING:now \u00b7 CHANNEL:x \u00b7 REV:none \u00b7 RISK:low]\nHello." });
  const ci = html.indexOf('class="caret');
  assert.ok(ci > -1, "caret must return once text exists");
  assert.ok(html.indexOf("Hello.") > -1 && html.indexOf("Hello.") < ci,
    "caret marks where text is APPEARING — after the text");
  const close = html.lastIndexOf("</p>");
  assert.ok(close > -1 && ci < close,
    "caret must sit INSIDE the paragraph, not orphaned after it: " + html);
});

test("34e. the caret lands inside a list item, not after the list", () => {
  /* The end of a reply is often a bullet. Matching only the final tag would
     put the caret after </ul>, i.e. back on its own line. */
  const html = T.streamBodyHtml({ response: "- one\n- two" });
  const ci = html.indexOf('class="caret');
  const lastLi = html.lastIndexOf("</li>");
  assert.ok(ci > -1, "caret missing on a list body");
  assert.ok(lastLi > -1 && ci < lastLi, "caret escaped the list item: " + html);
});

test("34f. a settled turn carries no caret", () => {
  /* turnResponse() gates on t.streaming. An earlier version of the inline-caret
     change dropped that gate and left a caret on every finished reply. */
  const html = T.turnResponse
    ? T.turnResponse({ uid: "u1", response: "Done.", streaming: false })
    : "";
  if (html) assert.ok(!/class="caret/.test(html), "settled turn kept a caret: " + html);
});

test("34g. a partial table row is withheld until its line completes", () => {
  /* A markdown table needs `|---|` on the NEXT line, so a header alone renders
     as a paragraph and then re-parses into a bordered table one frame later --
     a hard layout jump that shoves everything below it. */
  if (!T.withholdPartialRow) return;
  const w = T.withholdPartialRow;
  assert.equal(w("intro\n| Col A | Col B"), "intro", "table header must be withheld");
  assert.equal(w("| a |\n|---|\n| 1 "), "| a |\n|---|", "mid-table row must be withheld");
  assert.equal(w("intro\n| Col A |\n"), "intro\n| Col A |\n", "a terminated line is kept");
});

test("34h. ordinary prose containing one pipe is NOT withheld", () => {
  /* The first cut withheld any last line with a pipe, so "use a | b here"
     vanished until its newline -- and if it was line one, the reply showed
     nothing at all. Withholding must key on table SHAPE, not on the character. */
  if (!T.withholdPartialRow) return;
  const w = T.withholdPartialRow;
  assert.equal(w("a pipe | inside prose"), "a pipe | inside prose");
  assert.equal(w("just prose"), "just prose");
});

test("34i. only ONE scroll pin timer per session survives a re-render", () => {
  /* render() replaces #panes wholesale, so a guard stashed on the .pb element
     is orphaned every time and a fresh 100ms interval was created on EVERY
     render -- overlapping 4s timers all writing scrollTop while patchStreaming
     pinned on rAF. Two writers at different cadences is visible jitter. */
  const raw = require("fs").readFileSync(
    require("path").join(__dirname, "static/js/06-render.js"), "utf8");
  /* Strip comments before asserting. Twice now a source-level test has failed
     on the comment that DOCUMENTS the fix rather than on code -- a test that
     cannot tell prose from program is worse than no test, because the failure
     teaches you to loosen the assertion. */
  const src = raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
  assert.ok(!/pb\.__pinTimer\s*\)/.test(src),
    "the pin guard is back on the element, where a re-render orphans it");
  assert.ok(/_pinTimers\s*=\s*new Map\(\)/.test(src),
    "pin timers must be keyed by session id, not stored on the node");
  assert.ok(/_sessionIsStreaming\(sid\)/.test(src),
    "the pin timer must yield while patchStreaming owns the pin");
});

test("34j. cadence drain always converges to the full text", () => {
  /* The load-bearing correctness property: the smoothed view must reach 100%
     of the accumulator, or the reply would render truncated until `done`
     flushed it. Adversarial sizes, all must land exactly on full. */
  if (!T.drainStep) return;
  for (const full of [1, 3, 7, 40, 400, 5000, 100000]){
    let shown = 0, frames = 0;
    while (shown < full){ shown = T.drainStep(shown, full); frames++;
      assert.ok(shown <= full, "drain overshot the text: " + shown + " > " + full);
      assert.ok(frames < full + 50, "drain stalled — no convergence for full=" + full); }
    assert.equal(shown, full, "drain did not reach the end for full=" + full);
  }
});

test("34k. the drain makes progress every frame (step floor >= 1)", () => {
  if (!T.drainStep) return;
  assert.ok(T.drainStep(0, 1) === 1, "a 1-char reply must show in one step");
  assert.ok(T.drainStep(99, 100) === 100, "the last char must not require many frames");
  assert.ok(T.drainStep(0, 600) > T.drainStep(0, 60),
    "a bigger backlog must drain faster — the rate is backlog-aware");
});

test("34c. empty and null responses produce no caret and do not throw", () => {
  assert.ok(!/caret/.test(T.streamBodyHtml({ response: "" })));
  assert.ok(!/caret/.test(T.streamBodyHtml({})));
  assert.ok(!/caret/.test(T.streamBodyHtml(null)));
});

test("34d. patchStreaming uses the shared builder — no second caret writer", () => {
  /* the source contract: the ONLY caret literal on the streaming path lives in
     streamBodyHtml. A caret literal reappearing inside patchStreaming is the
     regression that already happened once. */
  const src = require("fs").readFileSync(__dirname + "/static/js/01-state.js", "utf8");
  const ps = src.slice(src.indexOf("function patchStreaming"));
  const psBody = ps.slice(0, ps.indexOf("\nfunction ", 10) > 0 ? ps.indexOf("\nfunction ", 10) : ps.length);
  assert.ok(/streamBodyHtml\(/.test(psBody), "patchStreaming must call streamBodyHtml");
  assert.ok(!/class="caret"/.test(psBody), "a caret literal inside patchStreaming is the second writer returning");
});

/* NAMESPACE NOTE (2026-08-22): this spec was first written against S.sessMenu /
   data-sessmenu / sessMenuAction. Those names already belong to the RAIL's
   per-session actions menu (rename / pin / archive -- 02-helpers.js:809,
   07-loaders.js:814), and sharing them made the composer chip toggle the wrong
   menu. The pane menu is paneMenu / data-panemenu / paneMenuAction. The spec
   is corrected to the non-colliding names; every assertion's INTENT is intact. */
/* ── 35. chat-surface chrome — the founder's 2026-08-18 decisions, ported ──
   design/app-preview.html + design/drive-preview.mjs are the contract. These
   pin the DOM that sessionPane() emits: the header exists only for the
   collapsed strip, a left-edge grip folds the pane, the composer opens with a
   session chip whose ⋯ menu carries every relocated control, and the
   placeholder is one word. Measured against 2.112.5 before the port: 6 of the
   24 lane-1 checks in design/PARITY-PLAN-chat-chrome.md passed. */
const PANE_S = { id: "sid-35", title: "ledger migration", turns: [], real: false, cwd: "", channel: null };
function paneHtml(over) {
  const prevMenu = T.S.paneMenu, prevFold = T.S.ui.paneCollapsed["sid-35"];
  T.S.paneMenu = over && over.menu ? "sid-35" : null;
  if (over && over.collapsed) T.S.ui.paneCollapsed["sid-35"] = true; else delete T.S.ui.paneCollapsed["sid-35"];
  try { return sandbox.sessionPane(PANE_S); }
  finally {
    T.S.paneMenu = prevMenu;
    if (prevFold) T.S.ui.paneCollapsed["sid-35"] = prevFold; else delete T.S.ui.paneCollapsed["sid-35"];
  }
}
const chipTagOf = h => (h.match(/<button[^>]*data-panemenu="sid-35"[^>]*>/) || [""])[0];

/* DECISION CHANGE (founder, 2026-08-23) superseding 2026-08-18: the header is
   BACK, minimal -- "what this chat is about" in <= 45 words, a live dot, and
   the × close. Tabs, Activity and the side-chat control stay out. */
test("35a. the expanded header is summary + live dot + close — nothing else", () => {
  const h = paneHtml();
  const ph = h.slice(h.indexOf('<div class="ph">'), h.indexOf('<div class="pb">'));
  assert.ok(/<h3 class="phsum"/.test(ph), "the summary h3 is the header");
  assert.ok(/data-close="sid-35"/.test(ph), "the × close is back in the header (founder 2026-08-23)");
  ["data-tab=", "data-act-toggle", "data-sidetoggle="].forEach(k =>
    assert.ok(!ph.includes(k), k + " must not be in the header"));
  assert.ok(/class="dot/.test(ph), "a live dot next to the summary");
});

test("35b. the section names itself — the only h3 is display:none while expanded", () => {
  assert.ok(/<section class="pane[^"]*"[^>]*aria-label="ledger migration — session pane"/.test(paneHtml()),
    "aria-label missing: a named section stays a navigable region without a visible h3");
});

test("35c. the grip renders BEFORE the header while expanded, and not at all while collapsed", () => {
  const h = paneHtml();
  const grip = h.indexOf('class="pgrip"'), ph = h.indexOf('<div class="ph">');
  assert.ok(grip > -1, "no .pgrip rendered");
  assert.ok(grip < ph, "the grip must precede .ph so a [data-pane-fold] query resolves to the VISIBLE control");
  const tag = (h.match(/<button[^>]*class="pgrip"[^>]*>/) || [""])[0];
  assert.ok(/data-pane-fold="sid-35"/.test(tag), "the grip reuses the fold handler");
  assert.ok(/aria-label="Collapse this session pane"/.test(tag));
  assert.ok(!paneHtml({ collapsed: true }).includes("pgrip"),
    "collapsed: the strip's own fold button must be the only [data-pane-fold]");
});

test("35d. the composer opens with the ⋯ chip, left of attach; no placeholder", () => {
  const h = paneHtml();
  const pc = h.slice(h.lastIndexOf('<div class="pc">'));
  const chip = pc.indexOf("data-panemenu="), attach = pc.indexOf("data-attach=");
  assert.ok(chip > -1, "no chip");
  assert.ok(chip < attach, "chip must sit LEFT of attach (founder, 2026-08-18)");
  const firstCtl = pc.indexOf("<button");
  assert.ok(pc.slice(firstCtl, firstCtl + 600).includes("data-panemenu="), "the chip must be the first control");
  assert.ok(!/<textarea data-sask="sid-35"[^>]*placeholder=/.test(pc), "NO placeholder (founder 2026-08-23: remove the silent text)");
  assert.ok(/<textarea data-sask="sid-35"[^>]*aria-label="Continue this session"/.test(pc), "aria-label unchanged");
});

test("35e. the chip is ⋯ ONLY — identity moved to the header; the a11y name still says what it opens", () => {
  const h = paneHtml();
  const tag = chipTagOf(h);
  assert.ok(tag, "chip tag missing");
  assert.ok(/class="uchip[^"]*"/.test(tag), "the chip reuses .uchip");
  assert.ok(/aria-label="Chat options — ledger migration"/.test(tag), "accessible name names the chat (codex P2)");
  assert.ok(/aria-haspopup="true"/.test(tag), "a generic popup — the rows are not menuitems (refuter 2026-08-23)");
  assert.ok(!/aria-controls=/.test(tag), "closed: no aria-controls to a non-existent id");
  assert.ok(/aria-expanded="false"/.test(tag), "closed by default");
  const inner = h.slice(h.indexOf(tag) + tag.length, h.indexOf("</button>", h.indexOf(tag)));
  assert.strictEqual(inner.replace(/<[^>]+>/g, "").trim(), "⋯", "three dots only (founder 2026-08-23)");
  assert.ok(!/uname|uring|udirty/.test(inner), "no name, no live ring, no dirty dot on the chip");
  assert.ok(/aria-expanded="true"/.test(chipTagOf(paneHtml({ menu: true }))), "open state reflected");
});

test("35f. the menu is closed by default and, open, carries every relocated control in order", () => {
  assert.ok(!paneHtml().includes('class="mrow'), "no menu rows while closed");
  const hm = paneHtml({ menu: true });
  const keys = [...hm.matchAll(/<span class="mk">([^<]+)<\/span>/g)].map(m => m[1]);
  deepEq(keys, ["Folder", "Permissions", "Model", "Usage", "Turn options", "Routing", "Fold", "Close"],
    "the 8-row contract: the ≡ turn-options control became a row (founder 2026-08-23)");
  assert.ok(/id="panemenu-sid-35"/.test(hm), "the popover carries the id aria-controls points at");
  assert.ok(/<div class="upop[^"]*"/.test(hm), "the popover reuses .upop");
});

test("35g. Permissions and Model rows are LABELS around the existing selects — never a select inside a button", () => {
  const hm = paneHtml({ menu: true });
  assert.ok(/<label class="mrow"[^>]*>[\s\S]*?<span class="mk">Permissions<\/span>[\s\S]*?<select class="permsel/.test(hm),
    "Permissions must wrap select[data-perm] in a label (codex [P1]: interactive-in-button is invalid)");
  assert.ok(/<label class="mrow"[^>]*>[\s\S]*?<span class="mk">Model<\/span>[\s\S]*?<select class="modelsel/.test(hm),
    "Model must wrap select[data-model] in a label");
  hm.split("</button>").filter(x => x.includes('class="mrow"')).forEach(chunk =>
    assert.ok(!/<select/.test(chunk.slice(chunk.lastIndexOf("<button"))), "a button row must not contain a select"));
  assert.ok(hm.includes('data-perm') && hm.includes('data-model='), "the existing handlers' hooks survive");
});

test("35h. menu state is in-memory only — never part of the persisted layout", () => {
  assert.ok(!("paneMenu" in T.S.ui), "S.ui is what saveLayout() persists; paneMenu must not live there");
  assert.ok(!/paneMenu/.test(String(sandbox.saveLayout)), "saveLayout must not know about the menu");
  assert.strictEqual(T.S.paneMenu, null, "default closed");
});

test("35i. every row dispatches to the state the old control mutated, and closes the menu", () => {
  const sid = "sid-35i";
  T.S.sessions.push({ id: sid, title: "t", turns: [] });
  withNoopRender(() => {
    T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "route");
    assert.strictEqual(T.S.sessTab[sid], "route", "Routing swaps the pane body");
    assert.strictEqual(T.S.paneMenu, null, "and closes the menu");
    sandbox.paneMenuAction(sid, "route");
    assert.strictEqual(T.S.sessTab[sid], "chat", "Routing toggles back");
    T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "fold");
    assert.strictEqual(T.S.ui.paneCollapsed[sid], true, "Fold collapses the pane");
    delete T.S.ui.paneCollapsed[sid];
    T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "usage");
    assert.strictEqual(T.S.usagePop, sid, "Usage opens the existing popover");
    T.S.usagePop = null;
    T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "folder");
    assert.strictEqual(T.S.cwdEdit, sid, "Folder opens the existing cwd editor");
    T.S.cwdEdit = null;
    T.S.openPanes = [sid]; T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "close");
    assert.ok(!T.S.openPanes.includes(sid), "Close closes the pane through the same path as data-close");
  });
  T.S.sessions = T.S.sessions.filter(s => s.id !== sid);
});

test("35j. the stylesheet ships the chrome: visible minimal header, grip, rows, chip", () => {
  const css = require("fs").readFileSync(__dirname + "/static/panel.css", "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/\.pane\[data-sess\]:not\(\.collapsed\)\s*>\s*\.ph\s*\{\s*display:\s*none/.test(css),
    "the header is VISIBLE while expanded again (founder 2026-08-23)");
  assert.ok(/\.pane\[data-sess\]:not\(\.collapsed\)\s*>\s*\.ph\s*>\s*\.pfold\s*\{\s*display:\s*none/.test(css),
    "but the strip's fold button stays hidden while expanded — the grip folds");
  assert.ok(/\.pht\{[^}]*text-overflow:\s*ellipsis/.test(css), "the title row ellipsizes on one line");
  assert.ok(/\.phs\{[^}]*text-overflow:\s*ellipsis/.test(css), "the subtitle row ellipsizes on one line");
  assert.ok(!/\.phsum\{[^}]*line-clamp/.test(css),
    "the wrapped 2-line clamp is gone — its tail was unreachable (founder 2026-08-24)");
  assert.ok(/\.pgrip\s*\{/.test(css), ".pgrip rule missing");
  assert.ok(/\.mrow\s*\{/.test(css), ".mrow rule missing");
  assert.ok(/\.pane\[data-sess\]\s*>\s*\.pb\s*,\s*\.pane\[data-sess\]\s*>\s*\.pc\s*\{\s*padding-left:\s*19px/.test(css),
    "body + composer clear the grip");
});

test("35k. dismissal is wired once at boot: click-away and Escape-first, with focus back on the chip", () => {
  const boot = require("fs").readFileSync(__dirname + "/static/js/08-boot.js", "utf8");
  const esc = boot.slice(boot.indexOf('if (e.key === "Escape")'));
  const menuAt = esc.indexOf("S.paneMenu"), palAt = esc.indexOf("S.palette");
  assert.ok(menuAt > -1 && menuAt < palAt, "Escape must close the menu FIRST in the cascade");
  assert.ok(/data-panemenu=/.test(esc.slice(menuAt, menuAt + 400)), "Escape must put focus back on the chip (codex [P2])");
  assert.ok(/closest\("\[data-panemenu\]"\)/.test(boot) && /closest\("\.upop"\)/.test(boot),
    "click-away must treat the trigger and the popover as not-away");
  const wire = require("fs").readFileSync(__dirname + "/static/js/07-loaders.js", "utf8");
  assert.ok(/panes\.querySelectorAll\("\[data-panemenu\]"\)/.test(wire), "chip toggle bound in wire()");
  assert.ok(/panes\.querySelectorAll\("\[data-mrow\]"\)/.test(wire), "rows bound in wire()");
});

/* ── 36. the chip panel shows every captured block — nothing escapes ──────── */
test("36a. an open chip renders one row per captured section, verbatim, escaped", () => {
  T.S.govOpen = { t36: true };
  const t = { uid: "t36", streaming: false, tools: [], toolRuns: [],
    response: "[INBOUND·DIRECT · TIMING:now · CHANNEL:x · REV:none · RISK:low]\nINPUT: <b>x</b>\nTYPE: task\n\nTASK: \"t\"\nDEPTH: 2/5\n\nReal answer." };
  const html = sandbox.gvChipHtml(t, 0);
  ["Header", "Input routing", "Depth"].forEach(l =>
    assert.ok(html.includes('<span class="gv-label">' + l + "</span>"), "missing row " + l));
  assert.ok(html.includes("INPUT: &lt;b&gt;x&lt;/b&gt;"), "captured text must be escaped");
  assert.ok(!html.includes("<b>x</b>"), "raw markup in a captured line must not render");
  assert.ok(/<pre class="gv-pre">/.test(html));
  T.S.govOpen = {};
});

test("36b. the rendered BODY carries no governance while the panel carries all of it", () => {
  const resp = "[INBOUND·QUERY · TIMING:now · CHANNEL:x · REV:none · RISK:low]\nINPUT: q\nTYPE: question\n\nThe answer is 4.";
  const html = T.turnResponse({ uid: "t36b", streaming: false, response: resp, tools: [], toolRuns: [] });
  assert.ok(html.includes("The answer is 4."));
  assert.ok(!/INPUT:|TYPE:|\[INBOUND/.test(html), "governance leaked into the body: " + html);
});

/* ── 35l-n. the repo bar's facts live in the ⋯ menu now ──────────────────── */
test("35l. with a repository known, Folder carries branch + state and PR rows appear after it", () => {
  const prevRepo = T.S.repo; T.S.repo = { "sid-35": { available: true, branch: "main", remote: "github.com/x/y",
    upstream: "origin/main", diff: { files: 2, added: 10, removed: 3 } } };
  try {
    const hm = paneHtml({ menu: true });
    const keys = [...hm.matchAll(/<span class="mk">([^<]+)<\/span>/g)].map(m => m[1]);
    deepEq(keys, ["Folder", "Pull requests", "Create PR", "Permissions", "Model", "Usage", "Turn options", "Routing", "Fold", "Close"]);
    assert.ok(/main · \+10 −3/.test(hm), "Folder row must show branch + dirty state");
    assert.ok(!/class="repobar/.test(paneHtml()), "the bar itself must be gone");
    assert.ok(!/class="udirty"/.test(paneHtml()), "no dirty dot on the chip any more — the Folder row carries it (founder 2026-08-23: three dots only)");
  } finally { T.S.repo = prevRepo; }
});

test("35m. a clean tree: Folder says clean, no dirty dot; no remote: no PR rows", () => {
  const prevRepo = T.S.repo; T.S.repo = { "sid-35": { available: true, branch: "main", remote: "", diff: { files: 0 } } };
  try {
    const hm = paneHtml({ menu: true });
    assert.ok(/main · clean/.test(hm));
    assert.ok(!/Pull requests|Create PR/.test(hm), "no remote -> nothing to open a PR against");
  } finally { T.S.repo = prevRepo; }
});

test("35n. PR rows dispatch to the same state the bar's buttons mutated", () => {
  const sid = "sid-35n";
  T.S.sessions.push({ id: sid, title: "t", turns: [] });
  const prevRepo = T.S.repo; T.S.repo = { [sid]: { available: true, branch: "feat", remote: "r", upstream: "origin/main" } };
  const prevLoad = sandbox.loadPrs; sandbox.loadPrs = () => {};
  try {
    withNoopRender(() => {
      T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "prs");
      assert.strictEqual(T.S.prsOpen, sid, "Pull requests opens the PR list");
      assert.strictEqual(T.S.paneMenu, null);
      T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "pr");
      assert.ok(T.S.prForm && T.S.prForm.sid === sid && T.S.prForm.head === "feat" && T.S.prForm.base === "main",
        "Create PR pre-fills head/base from the repo: " + JSON.stringify(T.S.prForm));
    });
  } finally { T.S.repo = prevRepo; sandbox.loadPrs = prevLoad; T.S.prsOpen = null; T.S.prForm = null;
    T.S.sessions = T.S.sessions.filter(s => s.id !== sid); }
});

/* ── 37. Routing view: a tree-list, not an org chart ─────────────────────── */
test("37a. the routing view is an indented tree with turn badges and a way back", () => {
  const prevD = T.DOMAINS;
  T.DOMAINS = [
    { ref: "r", name: "Asawa", path: "D0", parent_ref: null, ts_minted_ms: 1 },
    { ref: "a", name: "Sutra OS", path: "D1", parent_ref: "r", ts_minted_ms: 2 },
    { ref: "b", name: "Engine Library", path: "D1.D3", parent_ref: "a", ts_minted_ms: 3 },
  ];
  try {
    const s = { id: "s37", title: "t", turns: [
      { text: "q1", domain: { ref: "b", name: "Engine Library" }, confidence: 0.62, mode: "match" },
      { text: "q2", domain: { ref: "a", name: "Sutra OS" }, confidence: 0, mode: "floor" },
      { text: "q3" },
    ] };
    const html = sandbox.routingChart(s);
    assert.ok(/class="rt-back"[^>]*data-tab="chat"[^>]*data-sid="s37"/.test(html), "no way back to the chat");
    assert.ok(/3 turns · 3 departments on the path · 2 filed · <span class="gv-unres">1 unresolved/.test(html), (html.match(/rt-sum.{0,160}/) || [""])[0]);
    const rows = [...html.matchAll(/<div class="rt-row ?(hit)?" style="--d:(\d)"/g)].map(m => ({ hit: !!m[1], d: +m[2] }));
    deepEq(rows, [{ hit: false, d: 0 }, { hit: true, d: 1 }, { hit: true, d: 2 }], "depth follows ancestry; hit rows own turns");
    assert.ok(/turn 1 · 0\.62/.test(html) && /turn 2 · held/.test(html), "badges carry turn + confidence/held");
    assert.ok(/passed through/.test(html), "the root is an ancestor, not a participant");
    assert.ok(!/class="ocard"/.test(html), "the org chart is gone from the chat pane");
  } finally { T.DOMAINS = prevD; }
});

test("37b. no placements: the honest empty state, still with a way back", () => {
  const html = sandbox.routingChart({ id: "s", title: "t", turns: [{ text: "x", transcript: true }] });
  assert.ok(/rt-back/.test(html) && /No turn here carries a placement/.test(html));
});

/* ── 38. the header says what the chat is about — deterministically ───────── */
test("38a. the summary is the SUBTITLE row — capped at 45 words with an ellipsis (founder 2026-08-24)", () => {
  const words = Array.from({ length: 60 }, (_, i) => "w" + i).join(" ");
  const h = sandbox.sessionPane({ id: "sid-38", title: "short title", real: false, cwd: "", channel: null,
    turns: [{ text: words }] });
  const t = h.match(/<span class="pht">([^<]*)<\/span>/);
  const m = h.match(/<span class="phs">([^<]*)<\/span>/);
  assert.ok(t && m, "title row + subtitle row missing");
  assert.strictEqual(t[1], "short title", "the title row is the session title");
  const shown = m[1];
  assert.ok(shown.endsWith("…"), "a cut must say so");
  assert.strictEqual(shown.replace("…", "").trim().split(" ").length, 45, "exactly 45 words survive");
});

test("38b. a pasted code block says nothing about the chat — fences are dropped, text stays", () => {
  const h = sandbox.sessionPane({ id: "sid-38", title: "t", real: false, cwd: "", channel: null,
    turns: [{ text: "Fix this:\n```js\nconst secret = 1;\n```\nplease" }] });
  const shown = h.match(/<span class="phs">([^<]*)<\/span>/)[1];
  assert.strictEqual(shown, "Fix this: please");
});

test("38c. with no transcript loaded the server title is the summary; collapsed shows the raw title", () => {
  const open = sandbox.sessionPane({ id: "sid-38", title: "server title here", real: false, cwd: "", channel: null, turns: [] });
  assert.ok(/<span class="pht">server title here<\/span>/.test(open));
  assert.ok(!/<span class="phs">/.test(open),
    "summary == title must not render two identical rows (codex 2026-08-24)");
  T.S.ui.paneCollapsed["sid-38"] = true;
  try {
    const col = sandbox.sessionPane({ id: "sid-38", title: "server title here", real: false, cwd: "", channel: null,
      turns: [{ text: Array.from({ length: 60 }, () => "x").join(" ") }] });
    assert.ok(/<h3 class="phsum"[^>]*>server title here<\/h3>/.test(col), "the strip keeps the plain title");
  } finally { delete T.S.ui.paneCollapsed["sid-38"]; }
});

test("38d. the summary is inert text — markup in a prompt cannot render", () => {
  const h = sandbox.sessionPane({ id: "sid-38", title: "t", real: false, cwd: "", channel: null,
    turns: [{ text: "<img src=x onerror=alert(1)> hello" }] });
  assert.ok(!/<img/.test(h) && /&lt;img/.test(h));
});

test("38e. the ≡ control is gone from the composer and lives in the menu as Turn options", () => {
  const h = paneHtml();
  const pc = h.slice(h.lastIndexOf('<div class="pc">'));
  assert.ok(!/data-optstoggle/.test(pc), "no turn-options button next to send");
  const sid = "sid-38e";
  T.S.sessions.push({ id: sid, title: "t", turns: [] });
  try {
    withNoopRender(() => {
      T.S.paneMenu = sid; sandbox.paneMenuAction(sid, "opts");
      assert.strictEqual(T.S.optsOpen[sid], true, "the row toggles the same state the button did");
      assert.strictEqual(T.S.paneMenu, null);
    });
  } finally { delete T.S.optsOpen[sid]; T.S.sessions = T.S.sessions.filter(s => s.id !== sid); }
});

/* ── 39. the capture boundary, in the DOM (L2 of test_governance.js §13) ──
   The refuter's 2026-08-23 repros through the REAL render path: mdHtml(gvBody())
   inside turnResponse, and gvChipHtml for the panel. A reply that merely LOOKS
   like governance must reach the DOM; governance in a new dress must not. */
const t39 = (uid, response) => ({ uid, streaming: false, response, tools: [], toolRuns: [] });

test("39a. a glossary explaining the routing keys renders in the turn body, figures and all", () => {
  const html = T.turnResponse(t39("t39a",
    "[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]\nINPUT: x\nTYPE: question\n\n"
    + "Each line of the routing block has a fixed meaning:\nINPUT: a paraphrase of what you said\n"
    + "TYPE: one of direction/task/feedback/question\nROUTE: which skill handles it\n\nSo ROUTE: is just the dispatch decision."));
  assert.ok(/TYPE: one of direction\/task\/feedback\/question/.test(html), "the glossary was stripped: " + html);
  assert.ok(/ROUTE: which skill handles it/.test(html));
  assert.ok(!/INPUT: x|TYPE: question/.test(html), "the real block still must not reach the DOM");
});

test("39b. a plan comparison keeps its COST:/IMPACT: figures; a bug report keeps its OS: line", () => {
  const plan = T.turnResponse(t39("t39b",
    "Option A — keep Postgres\nCOST: $40/mo\nIMPACT: no migration work\n\nOption B — move to SQLite\nCOST: $0\nIMPACT: lose concurrent writers\n\nI would pick A."));
  assert.ok(/COST: \$40\/mo/.test(plan) && /IMPACT: lose concurrent writers/.test(plan), "figures lost: " + plan);
  const env = T.turnResponse(t39("t39b2", "Environment:\n\nOS: macOS 14.6 (Darwin 23.6.0)\nBrowser: Chrome 128\n\nThe crash is in the renderer."));
  assert.ok(/OS: macOS 14\.6/.test(env), "the environment line was taken for the trace: " + env);
});

test("39c. a fenced ticket template with one Steps: line, and a fenced commit template, render as the reply's code", () => {
  const html = T.turnResponse(t39("t39c",
    "Paste this into the ticket:\n\n```\nTitle: Login button unresponsive\nSteps:\n1. open /login\nExpected: redirect to /home\n```\n\n"
    + "Use the team template:\n\n```\nTYPE: fix | feat | chore\nSCOPE: module name\n```"));
  assert.ok(/Steps:/.test(html) && /Expected: redirect to \/home/.test(html), "the ticket template was stripped: " + html);
  assert.ok(/TYPE: fix \| feat \| chore/.test(html), "the commit template was stripped: " + html);
});

test("39d. an UNFENCED FLOW box never reaches the turn body and sits whole in the open chip panel", () => {
  const resp = "+-- FLOW -----+\n| [1] TYPE: question |\n| [2] RESOLVE: CONSTRUCT |\n+-------------+\n\nHere is the real answer.";
  const body = T.turnResponse(t39("t39d", resp));
  assert.ok(!/\+-- FLOW|RESOLVE: CONSTRUCT/.test(body), "the box leaked into the body: " + body);
  assert.ok(/Here is the real answer\./.test(body));
  T.S.govOpen = { t39d: true };
  try {
    const chip = sandbox.gvChipHtml(t39("t39d", resp), 0);
    assert.ok(chip.includes('<span class="gv-label">Flow</span>'), "no Flow row in the panel");
    assert.ok(/\[2\] RESOLVE: CONSTRUCT/.test(chip) && /\+-------------\+/.test(chip), "the box is not shown whole: " + chip);
  } finally { T.S.govOpen = {}; }
});

test("39e. bold **INPUT:** keys, a multi-line FLOW and a Steps bullet list are governance in the DOM too", () => {
  const bold = T.turnResponse(t39("t39e", "**INPUT:** ship it\n**TYPE:** task\n**ACTION:** do it\n\nHere is the real answer."));
  assert.ok(!/INPUT:|ACTION:/.test(bold), "bold keys leaked: " + bold);
  const flow = T.turnResponse(t39("t39e2", "FLOW: [1] task/cell\n[2] FOLLOW core:flow\n[6] close\n\nHere is the real answer."));
  assert.ok(!/FOLLOW core:flow|\[6\] close/.test(flow), "FLOW continuation leaked: " + flow);
  const bp = T.turnResponse(t39("t39e3", "BLUEPRINT\nDoing: the thing\nSteps:\n- first\n- second\nStops if: z\n\nHere is the real answer."));
  assert.ok(!/Stops if: z|- second/.test(bp), "Steps bullets leaked: " + bp);
  [bold, flow, bp].forEach(h => assert.ok(/Here is the real answer\./.test(h), "the answer must survive"));
});

test("39f. the [STAGE-1-FAIL · CLARIFY] header is lifted out of the body and names the verb on the chip", () => {
  const t = t39("t39f", "[STAGE-1-FAIL · CLARIFY · attempt:1/1]\n\nWhich file did you mean?");
  const body = T.turnResponse(t);
  assert.ok(!/STAGE-1-FAIL/.test(body), "the clarify header leaked: " + body);
  assert.ok(/Which file did you mean\?/.test(body));
  assert.ok(/<span>CLARIFY<\/span>/.test(sandbox.gvChipHtml(t, 0)), "the chip must carry the verb");
});

/* ── 40. the ⋯ popover's a11y contract (refuter 2026-08-23) ──────────────── */
test("40a. the popover is a labelled group, not a menu it cannot honour; aria-controls only while open", () => {
  const closed = chipTagOf(paneHtml());
  assert.ok(/aria-haspopup="true"/.test(closed), "generic popup, not menu semantics");
  assert.ok(!/aria-controls=/.test(closed), "aria-controls must not point at an id that does not exist");
  const hm = paneHtml({ menu: true });
  assert.ok(/aria-controls="panemenu-sid-35"/.test(chipTagOf(hm)), "open: it points at the popover");
  assert.ok(/<div class="upop panemenu" id="panemenu-sid-35" role="group"/.test(hm));
  assert.ok(!/role="menu"/.test(hm) && !/role="menuitem"/.test(hm));
});

test("40b. the live dot has a text alternative when it means something, and is hidden when it does not", () => {
  const quiet = paneHtml();
  assert.ok(/class="dot " aria-hidden="true"/.test(quiet), "idle dot is decorative");
});

/* ── 41 · governance chip on TRANSCRIPT turns ─────────────────────────────
   Every real session is read from ~/.claude/projects, so every real turn is a
   transcript turn — and until 2.117.3 the transcript branch of turnBlock never
   rendered gvChipHtml while gvBody stripped the same content from the body:
   captured nowhere, shown nowhere (found live 2026-08-24, founder report
   "input routing … getting missed"). These pin the honest fix: chip when
   something was captured, "terminal" (a fact) instead of "unresolved" (a
   failure that never happened), no chip when there is nothing to capture. */

const GOV_RESP = "```\nINPUT: ship the fix\nTYPE: task\nEXISTING HOME: none\nROUTE: bash\nFIT CHECK: none\nACTION: run the gate\n```\nDone — the fix shipped.";

test("41a. a transcript turn whose text carries governance renders the chip", () => {
  const h = T.turnBlock({ transcript:true, text:"q", response:GOV_RESP, tools:[] }, 0);
  assert.ok(/gv-chip/.test(h), "chip missing on a transcript turn with governance");
});

test("41b. the transcript chip reports 'terminal', never a fabricated resolution failure", () => {
  const t = { transcript:true, text:"q", uid:"tr41b", response:GOV_RESP, tools:[] };
  const closed = T.turnBlock(t, 0);
  assert.ok(/>terminal</.test(closed), "terminal segment missing");
  assert.ok(!/gv-unres/.test(closed) && !/Unresolved/.test(closed),
    "a terminal turn was misreported as a resolution failure");
  T.S.govOpen = { tr41b: true };                    /* open it — the prose lives in the panel */
  const open = T.turnBlock(t, 0);
  T.S.govOpen = {};
  assert.ok(/no placement was ever computed/.test(open),
    "the opened chip must carry the honest terminal prose (codex consult)");
  assert.ok(!/Unresolved/.test(open), "opened transcript chip misreports a failure");
  assert.ok(/gv-row/.test(open) && /INPUT: ship the fix/.test(open),
    "the opened chip must show the captured governance sections");
});

test("41c. a prose-only transcript turn renders NO chip — nothing captured is not a chip", () => {
  const h = T.turnBlock({ transcript:true, text:"q", response:"Just an answer. No blocks anywhere.", tools:[] }, 1);
  assert.ok(!/gv-chip/.test(h), "chip rendered with nothing captured");
});

test("41d. the transcript chip is toggleable: a real uid is assigned, not an empty anchor", () => {
  const t = { transcript:true, text:"q", response:GOV_RESP, tools:[] };
  const h = T.turnBlock(t, 0);
  assert.ok(t.uid && new RegExp('data-govopen="' + t.uid + '"').test(h),
    "empty data-govopen means the click handler returns and the chip is dead");
});

test("41e. panel turns are untouched: no domain still reads unresolved", () => {
  const h = T.turnBlock({ text:"q", uid:"u41e", response:"plain", tools:[] }, 0);
  assert.ok(/gv-chip/.test(h) && /gv-unres/.test(h), "panel branch changed");
});

test("41f. the gate ignores a prose mention of DEPTH — broad regex must not chip a non-capture", () => {
  const prose = "Here is the glossary the doc introduces:\n- DEPTH: 3/5 means thorough\n- COST: an estimate\nThat is all.";
  assert.equal(T.gvHasCapture({ response: prose }), false,
    "an explanatory list that stays in the body must not claim a capture (codex P2)");
});

/* ── 42 · header round 2 + transcript-noise removal (founder 2026-08-24) ── */

test("42a. hover and the accessible name carry the FULL title and subtitle", () => {
  const words = Array.from({ length: 60 }, (_, i) => "w" + i).join(" ");
  const h = sandbox.sessionPane({ id: "sid-42", title: "my title", real: false, cwd: "", channel: null,
    turns: [{ text: words }] });
  const ph = h.match(/<h3 class="phsum" title="([^"]*)" aria-label="([^"]*)"/);
  assert.ok(ph, "hover + aria attributes missing");
  assert.ok(ph[1].startsWith("my title — w0 "), "hover = title — subtitle");
  assert.ok(ph[2].startsWith("my title. w0 "), "aria-label = title. subtitle (codex: punctuation)");
});

test("42b. the per-turn transcript boilerplate is gone; the orphan warning is not", () => {
  const plain = T.turnBlock({ transcript: true, text: "q", response: "An answer.", tools: [] }, 3);
  assert.ok(!/from transcript/.test(plain) && !/~\/.claude\/projects/.test(plain),
    "the 'turn N · from transcript' pill and provenance note must be gone");
  const orphan = T.turnBlock({ transcript: true, orphan: true, text: "", response: "x", tools: [] }, 0);
  assert.ok(/no recorded prompt/.test(orphan), "the orphan warning reports a real anomaly and stays");
});

test("42c. the pane's 'transcript' tag is gone; fork survives", () => {
  const real = sandbox.sessionPane({ id: "sid-42c", title: "t", real: true, cwd: "/x", channel: null, turns: [] });
  assert.ok(!/>transcript<\/span>/.test(real), "the transcript label is provenance noise");
  const fork = sandbox.sessionPane({ id: "sid-42c", title: "t", real: true, fork: true, cwd: "/x", channel: null, turns: [] });
  assert.ok(/>fork<\/span>/.test(fork), "fork is a user-relevant fact and stays");
});

/* ── 43 · six vertical panes (founder 2026-08-24: "1, 2, 3, 4, 5, 6") ───── */

test("43a. six panes stand open at once; the seventh evicts the OLDEST, never a random one", () => {
  const saved = T.S.openPanes;
  T.S.openPanes = [];
  try {
    ["a","b","c","d","e","f"].forEach(id => T.pushPane(id));
    assert.strictEqual(T.S.openPanes.length, 6, "six panes must coexist");
    assert.strictEqual(T.MAX_PANES, 6);
    T.pushPane("g");
    assert.deepStrictEqual(T.S.openPanes, ["b","c","d","e","f","g"], "FIFO eviction — the oldest yields");
  } finally { T.S.openPanes = saved; }
});

test("43b. re-opening an open session never duplicates its pane", () => {
  const saved = T.S.openPanes;
  T.S.openPanes = ["a","b"];
  try {
    T.pushPane("a");
    assert.deepStrictEqual(T.S.openPanes, ["a","b"], "no duplicate pane for an open session");
  } finally { T.S.openPanes = saved; }
});

test("43c. the stylesheet lets six panes overflow into horizontal scroll, never crush", () => {
  const css = require("fs").readFileSync(__dirname + "/static/panel.css", "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(/\.panes\{[^}]*overflow-x:\s*auto/.test(css), "the pane row scrolls horizontally");
  assert.ok(/\.pane\{[^}]*flex:\s*1 0 380px/.test(css), "each pane floors at 380px");
});

/* ── 44 · chat-row metadata in USER language (founder 2026-08-24) ────────── */

test("44a. an unopened session says 'not opened yet' — no file size, no 'transcript'", () => {
  const m = T.rowMeta({ id: "r44a", real: true, live: "idle", turns: [], loadState: "unread", size: 1258291 });
  assert.ok(/not opened yet/.test(m), "the human phrasing is the row");
  assert.ok(!/MB|KB|\d+ B\b/.test(m), "file size is file-system provenance, not user language");
  assert.ok(!/transcript/i.test(m), "the word 'transcript' left the rows");
});

test("44b. transient states read human: 'opening…' and 'can't be opened'", () => {
  assert.ok(/opening…/.test(T.rowMeta({ id: "x", real: true, turns: [], loadState: "loading" })));
  assert.ok(/can't be opened/.test(T.rowMeta({ id: "x", real: true, turns: [], loadState: "error" })));
});

test("44c. the workspace label earns its pixels: shown only when the list spans >1 workspace", () => {
  const a = { id: "a", real: true, cwd: "/u/asawa-holding", turns: [] };
  const b = { id: "b", real: true, cwd: "/u/asawa-holding", turns: [] };
  const c = { id: "c", real: true, cwd: "/u/other-repo", turns: [] };
  assert.strictEqual(T.workspaceLabel(a, [a, b]), "", "one workspace — the label repeats and says nothing");
  assert.strictEqual(T.workspaceLabel(a, [a, b, c]), "asawa-holding", "two workspaces — now it differentiates");
  assert.strictEqual(T.workspaceLabel({ id: "p", real: false, turns: [] }, [a, c]), "", "panel-only sessions carry dept trails, not workspaces");
});

test("44d. what stayed: turn counts, live badges, and the deleted-on-disk anomaly", () => {
  assert.ok(/3 turns/.test(T.rowMeta({ id: "x", real: true, turns: [1, 2, 3], loadState: "ok" })));
  assert.ok(/livedot/.test(T.rowMeta({ id: "x", real: true, live: "active", turns: [], loadState: "unread" })), "live stays — the founder's signal");
  assert.ok(/deleted on disk/.test(T.rowMeta({ id: "x", real: true, vanished: true, turns: [] })));
});

test("42e. the subtitle strips a governance-opening prompt down to the actual ask", () => {
  const h = sandbox.sessionPane({ id: "sid-42e", title: "t42e", real: false, cwd: "", channel: null,
    turns: [{ text: 'PLACEMENT: D1.1 Core | "C"\n\nINPUT: a\nTYPE: task\nEXISTING HOME: none\nROUTE: r\nFIT CHECK: none\nACTION: y\n\nMake the header calm.' }] });
  const m = h.match(/<span class="phs">([^<]*)<\/span>/);
  assert.ok(m, "subtitle missing");
  assert.ok(!/PLACEMENT:|INPUT:/.test(m[1]), "governance leaked into the subtitle");
  assert.ok(/Make the header calm\./.test(m[1]), "the ask survives");
});

test("42d. the department chip is the LATEST FILED turn's leaf, labelled as such — absent when nothing was filed", () => {
  const filed = sandbox.sessionPane({ id: "sid-42d", title: "t", real: false, cwd: "", channel: null,
    turns: [{ text: "a", domain: { ref: "d1", name: "Sutra OS" } }, { text: "b" }] });
  const chip = filed.match(/<span class="phdept" title="([^"]*)">([^<]*)<\/span>/);
  assert.ok(chip, "dept chip missing when a turn was filed");
  assert.strictEqual(chip[2], "Sutra OS");
  assert.ok(/^latest filed:/.test(chip[1]), "the label must say it is the latest filed, not the session's identity (codex)");
  const none = sandbox.sessionPane({ id: "sid-42d", title: "t", real: false, cwd: "", channel: null,
    turns: [{ text: "a" }] });
  assert.ok(!/phdept/.test(none), "no fabricated dash when nothing was ever filed");
});

/* ── report ────────────────────────────────────────────────────────────── */

/* Sequential async checks FIRST (they own S.upd* and must not interleave),
   then the parallel ones, then the summary. */
/* ── the drain policy: properties, not thresholds ────────────────────────── */
/* These deliberately do NOT skip when a symbol is missing: a silent
   `if (!T.x) return` turns a deleted feature into a green test. */
test("34j drainStep never exceeds what has been received", () => {
  assert.equal(T.drainStep(0, 10), Math.min(10, T.drainStep(0, 10)), "sanity");
  assert.equal(T.drainStep(9, 10), 10, "cannot pass full");
  assert.equal(T.drainStep(50, 20), 20, "shown ahead of full clamps to full");
});

test("34k drainStep always makes progress, so the drain cannot stall", () => {
  let shown = 0, guard = 0;
  while (shown < 5000 && guard++ < 100000) {
    const next = T.drainStep(shown, 5000);
    assert.ok(next > shown, "step made no progress at shown=" + shown);
    shown = next;
  }
  assert.equal(shown, 5000, "must converge");
});

test("34l no single frame may dump a lump, at any backlog size", () => {
  /* The property that actually matters perceptually: not how EVEN the steps
     are (the drain eases out by design, so a max/avg ratio means nothing), but
     that no ONE frame paints a visible chunk. A purely proportional step passes
     at 400 chars and fails badly at 40000 -- which is why all three are here. */
  [400, 4000, 40000].forEach(total => {
    let shown = 0, guard = 0, max = 0;
    while (shown < total && guard++ < 200000) {
      const next = T.drainStep(shown, total);
      max = Math.max(max, next - shown);
      shown = next;
    }
    assert.equal(shown, total, "must fully drain a " + total + "-char backlog");
    assert.ok(max <= T._MAX_STEP,
      "backlog " + total + ": one frame painted " + max + " chars, over the " +
      T._MAX_STEP + "-char ceiling");
  });
});

test("34m the live view lags while streaming but never after", () => {
  /* streamBodyHtml is the single place the smoothed view is computed. If it
     ever renders past _shown mid-stream the caret jumps ahead of the text; if
     it still clips after streaming ends the final answer is truncated. */
  const partial = T.streamBodyHtml({ streaming: true,  response: "abcdefghij", _shown: 3 });
  const settled = T.streamBodyHtml({ streaming: false, response: "abcdefghij", _shown: 3 });
  if (!T._reduceMotion()) {
    assert.ok(/abc/.test(partial) && !/abcdefg/.test(partial),
      "mid-stream must clip to _shown, got: " + partial);
  }
  assert.ok(/abcdefghij/.test(settled),
    "a finished turn must show the whole response, got: " + settled);
});

updateStagingChecks()
  .then(() => Promise.allSettled(typeof ASYNC_CHECKS !== "undefined" ? ASYNC_CHECKS : []))
  .then(results => {
  results.forEach((r, i) => {
    if (r.status === "rejected") failures.push({ name: "async check #" + i, e: r.reason });
    else passed++;
  });
  console.log("\n" + "-".repeat(60));
  console.log("panel.html script: " + passed + " passed, " + failures.length + " failed");
  if (failures.length) {
    failures.forEach(f => {
      console.log("\nFAILED: " + f.name);
      console.log(f.e && f.e.stack ? f.e.stack : String(f.e));
    });
    process.exit(1);
  }
  process.exit(0);
});
