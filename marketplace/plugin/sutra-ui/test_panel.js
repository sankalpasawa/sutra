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
  /* The DeepSeek browser session token lives here rather than in localStorage:
     it dies with the server process, so a localStorage copy would outlive the
     thing it authorises. removeItem is real because the panel DROPS the token
     on a 403 -- a no-op stub would let that regression through. */
  sessionStorage: {
    _m: {},
    getItem(k) { return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; },
    setItem(k, v) { this._m[k] = String(v); },
    removeItem(k) { delete this._m[k]; },
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
  chanKey, paletteFor, CLAUDE_SOCKETS, queueState,
  _browseScrollKey, _browseScrollState, _restoreBrowseScroll, dirChip, resumableId,
  fmt, dirPickerAvailable,
  /* TENANTS was exported here. It is a lazy getter, so it kept "passing" after
     the global was deleted -- it would only have thrown the moment a test
     touched it. Removed with the tenant surface it belonged to. */
  get PROVIDERS(){ return PROVIDERS; }, set PROVIDERS(v){ PROVIDERS = v; },
  /* SETTINGS needs the same getter/setter pair as PROVIDERS above: a top-level
     \`let\` in a classic script lives in the SCRIPT scope, not on the global
     object, so a plain \`T.SETTINGS = x\` would set a property on the export
     object and leave the binding the code actually reads untouched. */
  get SETTINGS(){ return SETTINGS; }, set SETTINGS(v){ SETTINGS = v; },
  /* Same getter/setter reason as SETTINGS. Arrived with per-provider models:
     the pane picker reads THIS, keyed by the pane's own provider, so a test
     that wants a Model row has to say which provider's models exist. */
  get MODELS_BY_PROVIDER(){ return MODELS_BY_PROVIDER; },
  set MODELS_BY_PROVIDER(v){ MODELS_BY_PROVIDER = v; },
  /* Same getter/setter reason as MODELS_BY_PROVIDER. The other two controls
     that were Claude's rendered on every pane, now keyed by provider. */
  get TURN_OPTIONS_BY_PROVIDER(){ return TURN_OPTIONS_BY_PROVIDER; },
  set TURN_OPTIONS_BY_PROVIDER(v){ TURN_OPTIONS_BY_PROVIDER = v; },
  get PERM_MODES_BY_PROVIDER(){ return PERM_MODES_BY_PROVIDER; },
  set PERM_MODES_BY_PROVIDER(v){ PERM_MODES_BY_PROVIDER = v; },
  get PERM_MODES(){ return PERM_MODES; }, set PERM_MODES(v){ PERM_MODES = v; },
  turnOptsHtml, permSelect, turnOptsFor,
  /* Codex Reasoning effort: the option set is the SELECTED model's, so both
     the lookup and the pane's model resolution are pinned */
  codexEffortsFor, paneModelFor,
  get MODELS_BY_PROVIDER_RAW(){ return MODELS_BY_PROVIDER; },
  /* the Codex UX pass: per-turn token counts (the one usage fact codex
     reports), and the compacting that must never turn a small exact number
     into a rounded one */
  providerUsage, usageKindOf, tokShort,
  /* the global Codex plan indicator: the label is DERIVED from
     windowDurationMins, so both the derivation and the row mapping are
     pinned rather than a hardcoded 5h/weekly pair */
  codexWindowLabel, codexPlanRows, codexPlanBodyHtml,
  /* Pane provider resolution. TWO functions on purpose (see 06-render), and
     both are exported so the split itself is pinned: collapsing them would
     feed the page's seed to the Usage row, whose not-loaded branch turns a
     known provider id into a specific false claim. */
  paneProvider, paneDeclProvider, paneMenuHtml, readDeclarations,
  get SEED(){ return SEED; }, set SEED(v){ SEED = v; },
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
  /* the empty-chat rule: New chat reuses a chat nobody typed in rather than
     minting a second one. chatUntouched is the whole safety argument, so it is
     pinned on its own -- a predicate that says "empty" about a chat with a
     message, a draft, a rename or a run in flight is how real work is lost. */
  newSession, startNewChat, chatUntouched, reusableEmptyChat, NEW_CHAT_TITLE,
  sessionBusy, sessCwd,
  /* Teamsutra seeded chat: the budgeter is pure string assembly, exported so
     tests can prove the 8000-char server cap is never silently exceeded */
  tsBuildSeed, TS_SEED_MAX, openTeamsutraChat,
  /* the Usage account card: sign-in is a mutating control on a read screen,
     so its render states (offered / cancel-while-busy / browser hint) are
     pinned as strings */
  accountHtml, accountLoginHtml,
  /* the Codex sign-in block: the row exists to say which BILLING MODE is
     active, so every render state is pinned as a string -- a wrong badge here
     tells someone paying per token that their usage is included */
  codexAuthHtml, codexConfirmText, codexDoneText, loadCodexAuth, codexNeedsProbe,
  codexReprobe,
  /* the auth/readiness join. S.codexAuth and PROVIDERS were separate state and
     only the first was refreshed after a sign-in, so the row kept boot()'s
     answer until a reload -- these are what make one answer move both, and
     what keeps an older backend's omission from blanking the provider list */
  codexApplyState, codexNeedsInstall, codexEnsureRuntime, codexInstall,
  codexInstallHtml,
  /* the browser-transport sign-in watch: every stop condition is pinned,
     because a poll with no way to end is the render loop all over again */
  codexOnScreen, codexWatchLogin, codexStopPoll, codexBridge,
  /* the DeepSeek sign-in block: unlike codex this row decides whether the
     provider RUNS AT ALL, so each state is pinned as a string -- and so is the
     one thing that must never appear in any of them, the key itself */
  deepseekAuthHtml, deepseekBridge,
  /* the browser sign-in lane: a page with no Electron bridge trades the
     server's one-time code for a write token, so the code field must come
     BEFORE the key field -- there must be no paint where a key can be typed
     into a page that cannot deliver it */
  deepseekCanWrite, deepseekSessionToken, deepseekSetSessionToken,
  deepseekClearSessionToken, DEEPSEEK_SESSION_KEY,
  /* task.apply card states: the board is where a machine diff meets a human
     click, so the three renders (Apply offered / PR handed off / failure in
     place) are pinned as strings */
  tsCard, tsStatusWords, tsCurrentError, tsParseDiff, tsChangeView, tsStory,
  /* the permission-mode divergence marker. Pinned as a string because it is
     the ONLY place an operator learns their chosen mode is not the one
     running -- a marker that renders nothing recreates the silent fallback
     it was written to end. */
  modeMarkerHtml
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
/* Pins the EXACT default layout, so a new field cannot be added without a
   deliberate edit here -- which is the point: loadLayout's output is persisted
   to every operator's browser, and a field added by accident is a migration
   nobody designed. sessCollapsed joined it on 2026-09-09 for department-group
   collapse in Chats -> Dept (01-state.js). */
const LAYOUT_DEFAULTS = { paneCollapsed: {}, folds: {}, browseW: null, browseClosed: false,
                          navCollapsed: false, planeSections: {}, sessCollapsed: {},
                          dest: "now", destSel: {}, railOpen: null,
                          balanceTab: "today" };

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
  /* The rail track became var(--railw,224px) in 2.259.0, when the sidebar got a drag edge.
     224px is still the default INSIDE the var, so a browser with nothing stored lays out
     exactly as before; the assertion keeps that default pinned rather than dropping it. */
  assert.ok(/grid-template-columns:\s*var\(--railw,\s*224px\)\s+1fr\s+var\(--termw/.test(app[0]),
    ".app must lay out rail | panes | terminal, with 224px still the rail default");
  assert.ok(/position:relative/.test(app[0]),
    ".app is the positioning context for the drag edge; without it the edge resolves against the page");
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
  assert.ok(/function permSelect\([^)]*\)\{/.test(h), "a composer-level selector must exist");
  /* It renders in the composer row -- the same block as the model select, which
     is the anchor that is unambiguously part of the composer. */
  /* Re-sliced: the call now passes the pane's provider (permSelect(mpid)), so
     the three modes DeepSeek cannot enforce are not offered on a DeepSeek pane.
     What this test asserts -- that the selector is called from the template and
     sits beside the model select -- is unchanged. */
  const call = h.indexOf("${permSelect(");
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
  const fn = panelHtml.match(/function permSelect\([^)]*\)\{[\s\S]*?\n\}/)[0];
  assert.ok(/permission_mode_effective/.test(fn),
    "must read permission_mode_effective first");
});

/* ── 23e-g. the permission-mode divergence marker ─────────────────────────
   AcpRuntime asked DeepSeek for the operator's permission mode using a method
   name the CLI does not have (`session/set_session_mode`; the real one is
   `session/set_mode`), never read the answer, and recorded the mode it had
   asked for. Every DeepSeek pane displayed the chosen mode while running
   `default`. The server now states the divergence; this is the half that makes
   it visible, so an empty render here is the bug coming back. */

test("23e. a pane with no divergence renders NO marker", () => {
  T.S.modeNote = {};
  assert.strictEqual(T.modeMarkerHtml("s1"), "",
    "a Claude pane -- or any pane whose mode was applied -- gets nothing");
});

test("23f. the marker names BOTH modes and the reason", () => {
  T.S.modeNote = { s1: { asked: "dontAsk", running: "default",
                         reason: "dontAsk has no equivalent on this provider",
                         provider: "deepseek" } };
  const h = T.modeMarkerHtml("s1");
  /* "your mode was changed" without saying to WHAT is a warning nobody can
     act on, so both names are required, not just the failure. */
  assert.ok(h.includes("dontAsk"), "must name the mode that was asked for: " + h);
  assert.ok(h.includes("default"), "must name the mode actually running: " + h);
  assert.ok(h.includes("no equivalent"), "must carry the server's reason: " + h);
  assert.ok(/class="swmark bad"/.test(h),
    "always the .bad variant -- there is no benign version of this");
  T.S.modeNote = {};
});

test("23g. the server's reason is escaped, never interpolated as markup", () => {
  /* The reason carries CLI error text (set_mode's -32603 detail). That is a
     string from a subprocess, i.e. exactly the kind of value that must not
     reach innerHTML raw. */
  T.S.modeNote = { s1: { asked: "<b>x</b>", running: "default",
                         reason: "the CLI refused: <img src=x onerror=1>",
                         provider: "deepseek" } };
  const h = T.modeMarkerHtml("s1");
  assert.ok(!/<img/.test(h), "raw markup from the CLI reached the DOM: " + h);
  assert.ok(!/<b>x<\/b>/.test(h), "raw markup in a mode name rendered: " + h);
  assert.ok(h.includes("&lt;img"), "the reason must still be SHOWN, escaped: " + h);
  T.S.modeNote = {};
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
  /* Every stylesheet panel.html links is part of the shipped theme — the
     Workspace screen ships its controls in workspace.css, and a control
     styled there is themed, not a UA fallback. Concatenate them all. */
  const sheets = [...panelHtml.matchAll(/<link rel="stylesheet" href="\/static\/([\w.-]+\.css)/g)]
    .map(m => m[1]);
  const css = sheets.map(f =>
      fs.readFileSync(path.join(__dirname, "static", f), "utf8")).join("\n")
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

/* ── a message typed while a turn is already running ────────────────────────
   Typing mid-turn is normal and the message is never lost: the client sends it
   at once and the server's reader task queues it. But askClaude set
   `streaming = true` the instant a turn was SENT, so a message that had not
   begun rendered the same breathing "thinking" pulse as the one actually
   running -- two turns both claiming to work, and no way to tell whether the
   new input had been taken or ignored (founder, 2026-09-04). */
test("42a. a turn waiting behind a running one does not claim to be thinking", () => {
  const running = { uid: "t-run", streaming: true, response: "", tools: [], toolRuns: [] };
  const queued  = { uid: "t-que", streaming: true, response: "", tools: [], toolRuns: [] };
  T.CLAUDE_SOCKETS.set("sess-q", { pending: [queued], turn: running, sid: "sess-q" });
  try {
    const run = T.turnResponse(running);
    const que = T.turnResponse(queued);
    assert.ok(/gv-think/.test(run), "the RUNNING turn lost its thinking indicator");
    assert.ok(!/gv-waiting/.test(run), "the running turn was drawn as waiting");
    assert.ok(!/gv-think/.test(que),
      "the queued turn still shows the thinking pulse -- the two are indistinguishable");
    assert.ok(/gv-waiting/.test(que), "the queued turn shows no waiting state");
    assert.ok(/Queued/.test(que), "the queued turn does not say it is queued");
  } finally { T.CLAUDE_SOCKETS.delete("sess-q"); }
});

test("42b. the first message says it was sent, not that it is queued behind something", () => {
  /* Nothing is running -- ch.turn is null -- so this turn is waiting for the
     agent to spin up, which a cold CLI takes seconds to do. Saying "queued"
     there would imply something is ahead of it, a different and wrong fact. */
  const first = { uid: "t-first", streaming: true, response: "", tools: [], toolRuns: [] };
  T.CLAUDE_SOCKETS.set("sess-f", { pending: [first], turn: null, sid: "sess-f" });
  try {
    const html = T.turnResponse(first);
    assert.ok(/gv-waiting/.test(html));
    assert.ok(!/Queued/.test(html), "a first message must not claim to be queued");
    assert.ok(/waiting for the agent/.test(html), "it should say it was sent");
  } finally { T.CLAUDE_SOCKETS.delete("sess-f"); }
});

test("42c. queue position is stated once more than one is waiting", () => {
  const a = { uid: "q1", streaming: true, response: "", tools: [], toolRuns: [] };
  const b = { uid: "q2", streaming: true, response: "", tools: [], toolRuns: [] };
  T.CLAUDE_SOCKETS.set("sess-p", { pending: [a, b], turn: { uid: "live" }, sid: "sess-p" });
  try {
    assert.ok(/2nd in line/.test(T.turnResponse(b)),
      "the second queued message does not say where it is in the queue");
    assert.ok(!/in line/.test(T.turnResponse(a)),
      "the next-up message should not be numbered");
  } finally { T.CLAUDE_SOCKETS.delete("sess-p"); }
});

test("42d. the state is DERIVED, so a started turn cannot look queued forever", () => {
  /* queueState reads ch.pending, which the `start` frame shifts and failChannel
     splices. A stored flag would need clearing in seven separate places, and
     whichever was missed would strand a turn as permanently queued. */
  const t = { uid: "t-x", streaming: true, response: "", tools: [], toolRuns: [] };
  const ch = { pending: [t], turn: null, sid: "sess-d" };
  T.CLAUDE_SOCKETS.set("sess-d", ch);
  try {
    assert.ok(T.queueState(t), "should be queued while in pending");
    ch.pending.shift();                       /* exactly what the `start` frame does */
    assert.strictEqual(T.queueState(t), null, "still reported queued after start");
    assert.ok(!/gv-waiting/.test(T.turnResponse(t)));
  } finally { T.CLAUDE_SOCKETS.delete("sess-d"); }
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
/* The pane picker reads MODELS_BY_PROVIDER[thisPane'sProvider], so the fixture
   has to declare some or there is legitimately no Model row to assert on. This
   mirrors what GET /api/settings ships for claude. Tests that care about a
   DIFFERENT provider's list set T.MODELS_BY_PROVIDER themselves. */
const PANE_MODELS = { claude: [{ id: "", name: "CLI default" },
                               { id: "opus", name: "Opus" },
                               { id: "sonnet", name: "Sonnet" },
                               { id: "haiku", name: "Haiku" }] };

function paneHtml(over) {
  const prevMenu = T.S.paneMenu, prevFold = T.S.ui.paneCollapsed["sid-35"];
  const prevModels = T.MODELS_BY_PROVIDER;
  if (!(over && over.keepModels)) T.MODELS_BY_PROVIDER = PANE_MODELS;
  T.S.paneMenu = over && over.menu ? "sid-35" : null;
  if (over && over.collapsed) T.S.ui.paneCollapsed["sid-35"] = true; else delete T.S.ui.paneCollapsed["sid-35"];
  try { return sandbox.sessionPane(PANE_S); }
  finally {
    T.S.paneMenu = prevMenu;
    T.MODELS_BY_PROVIDER = prevModels;
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

/* ── 35p-t. the Model picker is the PANE'S provider's, not a shared list ──
   The panel had ONE model list and it was Claude's, so a DeepSeek session's ⋯
   menu offered Opus/Sonnet/Haiku -- none of which DeepSeek can run, and the
   fork does not reject a bad -m, it just answers as something else. */

/* Renders the pane menu with an explicit provider map and pane channel. */
function paneMenuWith(models, channelId, settings) {
  const prevCh = PANE_S.channel, prevSet = T.SETTINGS;
  PANE_S.channel = channelId ? { id: channelId } : null;
  if (settings !== undefined) T.SETTINGS = settings;
  try {
    T.MODELS_BY_PROVIDER = models;
    return paneHtml({ menu: true, keepModels: true });
  } finally { PANE_S.channel = prevCh; T.SETTINGS = prevSet; T.MODELS_BY_PROVIDER = {}; }
}
/* Scoped to the MODEL select. An unscoped scan also collects the permission
   select's options ("plan", "auto", ...) sitting one row above, which silently
   turns every assertion below into a claim about the wrong control. */
const optionsIn = h => {
  const i = h.indexOf('<select class="modelsel"');
  if (i === -1) return [];
  const block = h.slice(i, h.indexOf("</select>", i));
  return [...block.matchAll(/<option value="([^"]*)"([^>]*)>/g)]
    .map(m => ({ id: m[1], attrs: m[2] }));
};

const DS_MODELS = {
  claude: PANE_MODELS.claude,
  deepseek: [{ id: "", name: "CLI default" },
             { id: "deepseek-v4-pro", name: "V4 Pro", note: "flagship, 1M context" },
             { id: "deepseek-v4-flash", name: "V4 Flash" },
             { id: "deepseek-v4-flash-vision-exp", name: "V4 Flash Vision",
               selectable: false,
               unavailable_reason: "this panel has no image channel" }],
};

test("35p. a DeepSeek pane offers DeepSeek's models and none of Claude's", () => {
  const h = paneMenuWith(DS_MODELS, "deepseek", { provider: "claude" });
  const ids = optionsIn(h).map(o => o.id);
  assert.ok(ids.includes("deepseek-v4-pro"), "DeepSeek's flagship must be offered, got " + ids);
  ["opus", "sonnet", "haiku"].forEach(id =>
    assert.ok(!ids.includes(id),
      "Claude's " + id + " must not appear on a DeepSeek pane, got " + ids));
});

test("35q. the pane follows ITS OWN channel, not the global provider", () => {
  /* The bug this rules out: SETTINGS.provider is global, so a pane opened under
     DeepSeek and left open while the default was switched to Claude would have
     started listing Claude's models for a session DeepSeek is still answering. */
  const h = paneMenuWith(DS_MODELS, "deepseek", { provider: "claude" });
  assert.ok(optionsIn(h).some(o => o.id === "deepseek-v4-pro"),
    "the pane's own channel must win over SETTINGS.provider");
  const h2 = paneMenuWith(DS_MODELS, "claude", { provider: "deepseek" });
  assert.ok(optionsIn(h2).some(o => o.id === "opus"), "and in the other direction");
});

test("35r. the vision model is listed, disabled, and says why", () => {
  /* Dropping it hides that it exists; offering it enabled offers a choice that
     cannot run. Listed + disabled + reason is the third option. */
  const h = paneMenuWith(DS_MODELS, "deepseek", { provider: "deepseek" });
  const vis = optionsIn(h).find(o => o.id === "deepseek-v4-flash-vision-exp");
  assert.ok(vis, "it must still be listed");
  assert.ok(/\bdisabled\b/.test(vis.attrs), "it must not be selectable: " + vis.attrs);
  assert.ok(/no image channel/.test(vis.attrs), "the reason must be on the option: " + vis.attrs);
  assert.ok(!/\bselected\b/.test(vis.attrs), "a disabled option must never be the selection");
});

test("35s. a provider that declares no models gets no picker at all", () => {
  /* Codex has no model flag. An empty select would be a control that cannot do
     anything -- the same offer-a-dead-choice failure the provider list avoids. */
  const h = paneMenuWith(DS_MODELS, "codex", { provider: "codex" });
  assert.ok(!/<select class="modelsel"/.test(h), "no select for a provider with no models");
  const keys = [...h.matchAll(/<span class="mk">([^<]+)<\/span>/g)].map(m => m[1]);
  assert.ok(!keys.includes("Model"), "and no empty Model row either, got " + keys);
});

test("35t. before /api/settings resolves the row still renders", () => {
  /* It used to fall back to a lone "CLI default" whenever the list was empty.
     Losing that would make the Model row appear a beat after every other row
     on first paint -- a flicker that reads as a bug. */
  const h = paneMenuWith({}, null, null);
  assert.ok(/<select class="modelsel"/.test(h), "the row must survive an unloaded map");
  assert.deepStrictEqual(optionsIn(h).map(o => o.id), [""],
    "and offer exactly the CLI default until the real list arrives");
});

test("35u. the pre-selected model comes from THIS provider's stored slot", () => {
  /* The old fallback read the single flat SETTINGS.model, which only ever held
     a Claude id -- so a DeepSeek pane pre-selected something it could not send. */
  const h = paneMenuWith(DS_MODELS, "deepseek",
    { provider: "deepseek", model: "opus",
      model_by_provider: { claude: "opus", deepseek: "deepseek-v4-pro" } });
  const sel = optionsIn(h).filter(o => /\bselected\b/.test(o.attrs)).map(o => o.id);
  assert.deepStrictEqual(sel, ["deepseek-v4-pro"],
    "the DeepSeek slot must win over the legacy flat model, got " + sel);
});

/* ── 35v-x. the Usage row reports THIS provider's kind of fact ──────────── */

const usageRowOf = h => {
  const m = h.match(/data-mrow="usage"[\s\S]*?<span class="mv">([^<]*)<\/span>/);
  return m ? m[1] : null;
};

test("35v. a provider with no usage concept borrows nobody else's figure", () => {
  /* THE LATENT BUG, at the row. The branch was `if (deepseek) balance; else
     Anthropic percentage`, so Codex -- which has neither a window nor a
     balance -- would have rendered Claude's percentage on a Codex session the
     day it became selectable. */
  const prevP = T.PROVIDERS, prevU = T.S.usage;
  T.PROVIDERS = [{ id: "claude", name: "Claude Code", usage_kind: "window-percent" },
                 { id: "codex", name: "OpenAI Codex", usage_kind: "none" }];
  T.S.usage = { available: true, limits: [{ active: true, percent: 26 }] };
  try {
    const h = paneMenuWith({ claude: PANE_MODELS.claude }, "codex", { provider: "claude" });
    const row = usageRowOf(h);
    assert.ok(!/26/.test(row), "Claude's percentage leaked onto a Codex pane: " + row);
    assert.ok(/not reported/.test(row) && /Codex/.test(row),
      "it must say whose figure is missing and why, got: " + row);
  } finally { T.PROVIDERS = prevP; T.S.usage = prevU; }
});

test("35w. a Claude pane still shows the window percentage, unchanged", () => {
  const prevP = T.PROVIDERS, prevU = T.S.usage;
  T.PROVIDERS = [{ id: "claude", name: "Claude Code", usage_kind: "window-percent" }];
  T.S.usage = { available: true, limits: [{ active: true, percent: 26 }] };
  try {
    const h = paneMenuWith({ claude: PANE_MODELS.claude }, "claude", { provider: "claude" });
    assert.strictEqual(usageRowOf(h), "26% used");
  } finally { T.PROVIDERS = prevP; T.S.usage = prevU; }
});

test("35x. the Usage row follows the pane's provider, like the Model row", () => {
  /* Same divergence as the model list: SETTINGS.provider is global, so a
     DeepSeek pane left open across a switch to Claude would have started
     quoting Claude's percentage for a session DeepSeek is still answering. */
  const prevP = T.PROVIDERS, prevU = T.S.usage, prevD = T.S.deepseekUsage;
  T.PROVIDERS = [{ id: "claude", name: "Claude Code", usage_kind: "window-percent" },
                 { id: "deepseek", name: "DeepSeek", usage_kind: "balance" }];
  T.S.usage = { available: true, limits: [{ active: true, percent: 26 }] };
  T.S.deepseekUsage = { available: true, balances: [{ total_balance: "1.81", currency: "USD" }] };
  try {
    const h = paneMenuWith(DS_MODELS, "deepseek", { provider: "claude" });
    assert.strictEqual(usageRowOf(h), "$1.81 balance",
      "the pane's own provider must win over the global setting");
  } finally { T.PROVIDERS = prevP; T.S.usage = prevU; T.S.deepseekUsage = prevD; }
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

/* ── the composer reads as a field ─────────────────────────────────────────────
   The owner could not find the chat bar: it was placeholder text on the pane with
   `background:none;border:0` around it. Asserted in CSS because that is where the
   fault was, and asserted as TOKENS because the ring has to follow the theme
   picker rather than being one hardcoded colour. (2026-09-10) */
test("the chat composer looks like something you type in, in every theme", () => {
  const css = require("fs").readFileSync(
    require("path").join(__dirname, "static/panel.css"), "utf8");
  const rest = /\.pc input,\.pc textarea\{([^}]*)\}/.exec(css);
  assert.ok(rest, "the composer input has a rule");
  assert.ok(/border:1px solid var\(--line\)/.test(rest[1]), "a visible edge at rest");
  assert.ok(/background:var\(--inset\)/.test(rest[1]), "and a field background");
  assert.ok(!/border:0/.test(rest[1]), "not borderless any more");

  const focus = /\.pc input:focus,\.pc textarea:focus\{([^}]*)\}/.exec(css);
  assert.ok(focus, "and a focus rule");
  assert.ok(/var\(--acc\)/.test(focus[1]) && /var\(--acc-bg\)/.test(focus[1]),
    "focus uses the ACCENT tokens, so it follows the theme rather than one fixed colour");
  assert.ok(/\.pc input:hover,\.pc textarea:hover\{[^}]*var\(--acc\)/.test(css),
    "and it answers a hover, so it reads as interactive before you click");
  assert.ok(!/\.pc input:focus-visible[^{]*\{[^}]*outline:2px/.test(css),
    "the old outline is gone: border + halo already draws the ring, two is worse than none");
});

/* ── empty chats · New chat REUSES a chat nobody typed in ────────────────
   The Chats list filled with "New session · 0 turns" rows: one per click of
   New chat, six of them in front of the single real conversation, with nothing
   to tell them apart. The rule is "do not create a second empty chat", never
   "delete the empty ones" -- so most of what is pinned here is the other
   direction: every kind of chat that must NOT be mistaken for empty, because a
   wrong answer there hands the operator's blank pane to work they had started.
*/
function emptyChatFixture(fn){
  const saved = {
    sessions: T.S.sessions, openPanes: T.S.openPanes, cwd: T.S.cwd,
    composerText: T.S.composerText, attach: T.S.attach, model: T.S.model,
    turnOpts: T.S.turnOpts, sideTurns: T.S.sideTurns, sideText: T.S.sideText,
    sutraId: T.S.sutraId, chatProvider: T.S.chatProvider,
    pinned: T.S._pinned, unread: T.S._unread, groups: T.S._groups,
  };
  T.S.sessions = []; T.S.openPanes = []; T.S.cwd = {};
  T.S.composerText = {}; T.S.attach = {}; T.S.model = {};
  T.S.turnOpts = {}; T.S.sideTurns = {}; T.S.sideText = {};
  T.S.sutraId = {}; T.S.chatProvider = {};
  T.S._pinned = new Set(); T.S._unread = new Set(); T.S._groups = {};
  const sockets = [...T.CLAUDE_SOCKETS.keys()];
  try { fn(); } finally {
    [...T.CLAUDE_SOCKETS.keys()].forEach(k => { if (!sockets.includes(k)) T.CLAUDE_SOCKETS.delete(k); });
    Object.assign(T.S, {
      sessions: saved.sessions, openPanes: saved.openPanes, cwd: saved.cwd,
      composerText: saved.composerText, attach: saved.attach, model: saved.model,
      turnOpts: saved.turnOpts, sideTurns: saved.sideTurns, sideText: saved.sideText,
      sutraId: saved.sutraId, chatProvider: saved.chatProvider,
      _pinned: saved.pinned, _unread: saved.unread, _groups: saved.groups,
    });
  }
}

test("empty chat: New chat twice with nothing typed leaves ONE chat", () => {
  emptyChatFixture(() => {
    const a = T.startNewChat("/w");
    const b = T.startNewChat("/w");
    assert.strictEqual(T.S.sessions.length, 1,
      "the second click must reuse the blank chat, not mint a second row");
    assert.strictEqual(a.id, b.id, "the same chat comes back");
    assert.strictEqual(T.S.openPanes.filter(x => x === a.id).length, 1,
      "and it is still open exactly once");
  });
});

test("empty chat: New chat AFTER a real message mints a second chat", () => {
  emptyChatFixture(() => {
    const a = T.startNewChat("/w");
    a.turns.push({ text: "ship the release notes", response: "", tools: [] });
    const b = T.startNewChat("/w");
    assert.strictEqual(T.S.sessions.length, 2, "a chat with a message is not empty");
    assert.notStrictEqual(a.id, b.id);
    assert.strictEqual(a.turns.length, 1, "the earlier chat keeps its message");
  });
});

test("empty chat: a chat the operator NAMED is never treated as empty", () => {
  emptyChatFixture(() => {
    const a = T.startNewChat("/w");
    a.title = "Pricing rewrite";        /* exactly what renameSession() writes */
    assert.strictEqual(T.chatUntouched(a), false, "a named chat is somebody's");
    const b = T.startNewChat("/w");
    assert.strictEqual(T.S.sessions.length, 2, "the named chat must survive untouched");
    assert.strictEqual(a.title, "Pricing rewrite");
    assert.notStrictEqual(a.id, b.id);
  });
});

test("empty chat: a turn-less chat with a run IN FLIGHT survives", () => {
  emptyChatFixture(() => {
    const a = T.startNewChat("/w");
    /* A socket holding a queued turn: the window between "send pressed" and the
       first frame, where the chat has no turn on it yet. */
    T.CLAUDE_SOCKETS.set(T.chanKey(a.id, false),
      { open: true, ws: {}, queue: [], pending: [{ text: "hi" }], turn: null });
    assert.strictEqual(T.sessionBusy(a.id), true, "the fixture must really be busy");
    assert.strictEqual(T.chatUntouched(a), false, "work in flight is not emptiness");
    const b = T.startNewChat("/w");
    assert.strictEqual(T.S.sessions.length, 2, "the in-flight chat must not be reused");
    assert.notStrictEqual(a.id, b.id);
  });
});

test("empty chat: every per-chat store the operator can write blocks reuse", () => {
  /* One case per store, each proving the SAME thing: a blank-looking chat that
     someone has already put something into is not a chat to hand back. */
  const cases = {
    "a typed but unsent message": (s) => { T.S.composerText[s.id] = "draft I have not sent"; },
    "a pending attachment":       (s) => { T.S.attach[s.id] = [{ ref: "f1", pending: true }]; },
    "a chosen model":             (s) => { T.S.model[s.id] = "opus"; },
    "a per-turn option":          (s) => { T.S.turnOpts[s.id] = { effort: "high" }; },
    "a side chat":                (s) => { T.S.sideTurns[s.id] = [{ text: "branch" }]; },
    "a side-chat draft":          (s) => { T.S.sideText[s.id] = "half a question"; },
    "a durable chat record":      (s) => { T.S.sutraId[s.id] = "0".repeat(32); },
    "a resumable session id":     (s) => { s.claude_session = "abc-123"; },
    "a provider frame":           (s) => { s.channel = { provider: "claude" }; },
    "an in-chat provider switch": (s) => { T.S.chatProvider[s.id] = "codex"; },
    "a pin":                      (s) => { T.S._pinned.add(s.id); },
    "an unread mark":             (s) => { T.S._unread.add(s.id); },
    "a group":                    (s) => { T.S._groups[s.id] = "Launch"; },
    "a fork marker":              (s) => { s.fork = true; s.forkOf = "s-9"; },
  };
  for (const [what, mark] of Object.entries(cases)) {
    emptyChatFixture(() => {
      const a = T.startNewChat("/w");
      mark(a);
      assert.strictEqual(T.chatUntouched(a), false, what + " must make a chat non-empty");
      T.startNewChat("/w");
      assert.strictEqual(T.S.sessions.length, 2, what + " must not be reused away");
    });
  }
});

test("empty chat: a transcript on disk is never in scope", () => {
  emptyChatFixture(() => {
    assert.strictEqual(T.chatUntouched(
      { id: "s-real", title: T.NEW_CHAT_TITLE, real: true, local: false, turns: [] }), false,
      "a real transcript is a file, and this rule only ever governs panel-minted chats");
    assert.strictEqual(T.chatUntouched(
      { id: "s-gone", title: T.NEW_CHAT_TITLE, local: true, vanished: true, turns: [] }), false);
    assert.strictEqual(T.chatUntouched(null), false);
    assert.strictEqual(T.chatUntouched(undefined), false);
  });
});

test("empty chat: a blank chat in ANOTHER folder is not the chat this click asked for", () => {
  emptyChatFixture(() => {
    const a = T.startNewChat("/repo/one");
    const b = T.startNewChat("/repo/two");
    assert.strictEqual(T.S.sessions.length, 2, "a different folder means a different chat");
    assert.strictEqual(T.S.cwd[a.id], "/repo/one", "the first chat keeps its folder");
    assert.strictEqual(T.S.cwd[b.id], "/repo/two");
    const c = T.startNewChat("/repo/two");
    assert.strictEqual(c.id, b.id, "the same folder reuses the blank chat in it");
  });
});

test("empty chat: the department + adopts a blank chat, but never re-files a filed one", () => {
  emptyChatFixture(() => {
    const a = T.startNewChat("");                       /* no folder, no department */
    const b = T.startNewChat("", { ref: "dref-s", name: "Sutra" });
    assert.strictEqual(b.id, a.id, "an unfiled blank chat is what the + should use");
    assert.strictEqual(b.department.ref, "dref-s", "and it takes the department on");
    const c = T.startNewChat("", { ref: "dref-other", name: "Ops" });
    assert.strictEqual(T.S.sessions.length, 2, "a chat already filed elsewhere is left alone");
    assert.strictEqual(a.department.ref, "dref-s", "its department is not rewritten");
    assert.strictEqual(c.department.ref, "dref-other");
  });
});

test("empty chat: reuse is wired to the New chat gestures ONLY", () => {
  const loaders = require("fs").readFileSync(__dirname + "/static/js/07-loaders.js", "utf8");
  const boot = require("fs").readFileSync(__dirname + "/static/js/08-boot.js", "utf8");
  assert.ok(/getElementById\("newSession"\)\.onclick = \(\) =>\s*startNewChat\(/.test(loaders),
    "the rail's New chat button goes through startNewChat");
  assert.ok(/dept-new"\){[\s\S]{0,400}?startNewChat\(/.test(loaders),
    "the + on a department heading goes through startNewChat");
  assert.ok(/startNewChat\(sessCwd\(focused\)/.test(boot),
    "Cmd+N goes through startNewChat, or the keyboard mints what the button reuses");
  /* The named chats mint their own row on purpose: reusing the operator's blank
     pane for one would put a title and a seeded system prompt they never asked
     for on the chat in front of them. */
  assert.ok(/function forkSession\(sid\)\{[\s\S]{0,200}?newSession\(sessCwd\(sid\)\)/.test(loaders),
    "fork still mints its own chat");
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

/* ── 34. Usage account card: sign-in states + simplification ───────────── */

test("34a. desktop offers Sign in when signed out, Switch when signed in", () => {
  sandbox.sutra = { authLogin: () => Promise.resolve({ ok: true }) };
  try {
    T.S.authBusy = false; T.S.authMsg = null; T.S.accountError = null;
    T.S.account = { available: false, reason: "no Claude account is signed in" };
    assert.ok(/data-auth-login/.test(T.accountHtml()), "signed-out card offers the button");
    assert.ok(/>\s*Sign in</.test(T.accountHtml()), "and it says Sign in");
    T.S.account = { available: true, profile: { email: "a@b.c", display_name: "A" },
                    subscription: {} };
    assert.ok(/Switch account/.test(T.accountHtml()), "signed-in card says Switch account");
  } finally { delete sandbox.sutra; }
});

test("34b. while a sign-in runs the button becomes Cancel", () => {
  sandbox.sutra = { authLogin: () => Promise.resolve({ ok: true }) };
  try {
    T.S.authBusy = true;
    T.S.account = { available: true, profile: { email: "a@b.c" }, subscription: {} };
    const html = T.accountHtml();
    assert.ok(/Cancel sign-in/.test(html), "busy button cancels");
    assert.ok(/Waiting for the browser sign-in/.test(html), "and says why it waits");
  } finally { T.S.authBusy = false; delete sandbox.sutra; }
});

test("34c. a plain browser gets the CLI hint, never a dead button", () => {
  T.S.account = { available: true, profile: { email: "a@b.c" }, subscription: {} };
  const html = T.accountHtml();               // no sandbox.sutra: browser context
  assert.ok(!/data-auth-login/.test(html), "no button without the bridge");
  assert.ok(/claude auth login/.test(html), "the CLI path is named instead");
});

test("34d. simplified card: four rows on top, the rest behind Details", () => {
  sandbox.sutra = { authLogin: () => Promise.resolve({ ok: true }) };
  try {
    T.S.authBusy = false; T.S.authMsg = null;
    T.S.account = { available: true,
      profile: { email: "a@b.c", display_name: "A", organization: "Org",
                 plan: "Max", account_id: "acc_1", rate_limit_tier: "t2" },
      subscription: { subscription_type: "max" } };
    const html = T.accountHtml();
    const top = html.split("<details")[0];
    assert.ok(/Signed in as/.test(top) && /Email/.test(top)
           && /Plan/.test(top) && /Organization/.test(top), "the four acting rows are on top");
    assert.ok(!/Rate-limit tier/.test(top) && !/acc_1/.test(top),
      "diagnostics are not furniture any more");
    const details = html.split("<details")[1] || "";
    assert.ok(/Rate-limit tier/.test(details) && /acc_1/.test(details),
      "but they are still reachable behind Details");
  } finally { delete sandbox.sutra; }
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

/* ── Optimus (Focus > the daemon, visible) ─────────────────────────────── */

test("opt1. optimus is registered: SCREENS + TITLES + focus plane row", () => {
  assert.ok(typeof T.SCREENS.optimus === "function", "SCREENS.optimus");
  assert.ok(Array.isArray(T.TITLES.optimus) && T.TITLES.optimus[0] === "Optimus", "TITLES.optimus");
});

test("opt2. optimus renders honest emptiness — no fabricated daemon state", () => {
  T.S.optimus = { snap: { present: false, root: "/tmp/x", daemon: { running: false, pid: null } },
                  at: new Date(), err: null, act: null };
  const html = T.SCREENS.optimus();
  assert.ok(html.includes("hasn\u2019t done anything yet"), "empty state text");
  assert.ok(html.includes("data-optstart"), "start control offered");
  assert.ok(!html.includes("undefined"), "no undefined leaks");
});

test("opt3. a proposed route renders the TWO-STEP approve (typed confirm), never one-click", () => {
  T.S.optimus = { snap: { present: true, root: "/tmp/x",
    daemon: { running: true, pid: { pid: 4242, started_at: "2026-08-24T00:00:00Z" } },
    routes: [{ route_id: "r-abc12345", status: "proposed", pattern: "^(write|author) ",
               workflow: "W-md-authoring@0.1.0", host: "claude-bare",
               department: "Finance Ops", charter: "EMI Reconciliation" }],
    pending_inputs: [], state_summary: { passed: 2 }, asks: [], runs: [],
    quarantine: [], inbox_malformed: 0 }, at: new Date(), err: null, act: null };
  const html = T.SCREENS.optimus();
  assert.ok(html.includes('data-optconfirm="r-abc12345"'), "typed-confirm input present");
  assert.ok(html.includes('data-optapprove="r-abc12345"'), "approve button present");
  assert.ok(html.includes("Finance Ops") && html.includes("EMI Reconciliation"), "dept/charter chips");
  assert.ok(html.includes('data-optstop="4242"'), "stop echoes the pid it saw");
});

test("opt4. throwback asks render as first-class decisions, with their ids", () => {
  T.S.optimus.snap.asks = [{ outbox_id: "ob-1", ask_text: "[daemon:throwback] input in-x: host exited 3" }];
  const html = T.SCREENS.optimus();
  assert.ok(html.includes("ob-1"), "ask keeps its exact id");
  assert.ok(html.includes("couldn\u2019t finish this"), "throwback in customer voice");
  assert.ok(html.includes("host exited 3"), "raw evidence stays one glance away");
});

test("opt5. chat-first: teach and chat buttons present; the 7-field form is gone", () => {
  const html = T.SCREENS.optimus();
  assert.ok(html.includes("data-optteach"), "teach-in-chat button");
  assert.ok(html.includes("data-optchat"), "chat-about-this button");
  assert.ok(!html.includes("optP_pattern"), "field form removed");
});



/* ── 45. Codex sign-in block ────────────────────────────────────────────────
   The reason this row was built: a ChatGPT sign-in and an API key cost the
   operator completely different amounts for identical output, and nothing in
   the panel showed which was in play. Every assertion below is about not
   claiming the wrong one. */

const CODEX_ROW = { id:"codex", name:"OpenAI Codex", installed:true, configured:true,
                    runnable:false, adapter:false,
                    reason:"no chat adapter yet -- this panel speaks two protocols" };

function codexRender(auth, opts){
  const o = opts || {};
  T.PROVIDERS = [CODEX_ROW];
  T.S.codexAuth = auth;
  T.S.codexBusy = o.busy || null;
  T.S.codexMsg = o.msg || null;
  T.S.codexKeyOpen = !!o.keyOpen;
  return T.codexAuthHtml();
}

test("45a. each state renders its own badge, and the billing line with it", () => {
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const out = codexRender({ state:"logged_out", key_display:"", billing:null });
    assert.ok(/Not signed in/.test(out), "signed-out says so");
    assert.ok(/Sign in with ChatGPT/.test(out) && /Add API key/.test(out),
      "and offers both ways in");
    /* REWORDED 2026-09-08: neither way in may state a price or an allowance,
       because codex publishes neither. Each says which ACCOUNT pays. */
    assert.ok(/ChatGPT plan's own Codex limits/.test(out)
           && /billed to your OpenAI API account/.test(out),
      "each way in says which account pays");

    const chat = codexRender({ state:"chatgpt", key_display:"",
                               billing:"covered by your ChatGPT plan" });
    assert.ok(/Signed in with ChatGPT/.test(chat), "chatgpt badge");
    assert.ok(/covered by your ChatGPT plan/.test(chat), "with the billing line");
    assert.ok(/Sign out/.test(chat) && /Use an API key instead/.test(chat),
      "sign out + the switch");

    const key = codexRender({ state:"api_key", key_display:"sk-proj-***SMnIA",
                              billing:"billed to your OpenAI API account" });
    assert.ok(/sk-proj-\*\*\*SMnIA/.test(key), "the masked stub the CLI printed");
    assert.ok(/billed to your OpenAI API account/.test(key), "with the billing line");
    assert.ok(/Sign out/.test(key) && /Switch to ChatGPT plan/.test(key),
      "sign out + the other switch");

    const none = codexRender({ state:"no_binary", detail:"the `codex` CLI is not on PATH" });
    assert.ok(/not on PATH/.test(none), "a missing CLI says that, not 'not signed in'");
    assert.ok(!/Sign in with ChatGPT/.test(none), "and offers nothing to click");
  } finally { delete sandbox.sutra; }
});

test("45b. an unrecognised answer says so and NEVER invents a mode", () => {
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const out = codexRender({ state:"unknown", key_display:"", billing:null,
                              detail:"`codex login status` answered in a shape this build does not recognise (exit 2)" });
    assert.ok(/Could not tell which credential/.test(out), "the honest message");
    assert.ok(/does not recognise/.test(out), "with the reason attached");
    assert.ok(!/usage included/.test(out) && !/billed per token/.test(out),
      "no billing claim is made when the mode is unknown");
    assert.ok(!/Signed in with ChatGPT/.test(out) && !/Not signed in/.test(out),
      "and no state is fabricated either way");
    assert.ok(!/Sign out/.test(out),
      "Sign out is withheld: it would imply we know there is something to sign out of");
  } finally { delete sandbox.sutra; }
});

test("45c. not asked yet is not signed out", () => {
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const out = codexRender(null);
    assert.ok(/Reading the Codex sign-in/.test(out), "it says it is still reading");
    assert.ok(!/Not signed in/.test(out), "never a billing claim before anything was read");
  } finally { delete sandbox.sutra; }
});

test("45d. a browser can sign in and out; only the API key needs the desktop", () => {
  /* This inverts what the row used to say. Sign in, sign out and cancel now
     ride POST /api/providers/codex/{login,logout,login/cancel}, so a browser
     gets real buttons. The API KEY does not and never will: it would have to
     cross an HTTP request body to reach the CLI. */
  const out = codexRender({ state:"logged_out" });      // no sandbox.sutra: browser
  assert.ok(/data-codex="login"/.test(out), "ChatGPT sign-in works from a browser");
  assert.ok(!/data-codex="apikey"/.test(out), "the API key button needs the bridge");
  assert.ok(/codex login --with-api-key/.test(out), "and the CLI path is named for it");
  assert.ok(/desktop app/.test(out),
    "with the alternative, so it does not read as a missing feature");

  const signed = codexRender({ state:"chatgpt", billing:"usage included in your plan" });
  assert.ok(/data-codex="logout"/.test(signed), "sign out works from a browser too");
  assert.ok(!/data-codex="apikey"/.test(signed), "switching TO a key still needs the bridge");

  const keyed = codexRender({ state:"api_key", key_display:"sk-proj-***SMnIA",
                              billing:"billed per token" });
  assert.ok(/data-codex="login"/.test(keyed) && /data-codex="logout"/.test(keyed),
    "switching back to ChatGPT, and signing out, both work from a browser");
});

test("45d2. the waiting copy always names the terminal way through", () => {
  /* Neither transport forwards the child's output, so codex's fallback sign-in
     URL is invisible here by design. Someone whose browser did not open needs
     the escape hatch WHILE waiting, not in an error three minutes later. */
  const out = codexRender({ state:"logged_out" }, { busy:"login" });
  assert.ok(/Waiting for the browser sign-in/.test(out), "it says what it waits for");
  assert.ok(/run <code>codex login<\/code> in a terminal/.test(out),
    "and names the way through if no window opened");
  assert.ok(/>Cancel</.test(out), "and the button cancels");
});

test("45d3. a sign-in the SERVER is running is adopted after a reload", () => {
  /* A reload loses S.codexBusy. With login_in_flight true a child is running
     and about to change the credential, so a row reading "Not signed in" with
     an idle button would be the row lying about state. */
  const out = codexRender({ state:"logged_out", login_in_flight:true });
  assert.ok(/Waiting for the browser sign-in/.test(out),
    "the row shows the sign-in it did not start");
  assert.ok(/>Cancel</.test(out), "and offers to cancel it");
  const idle = codexRender({ state:"logged_out", login_in_flight:false });
  assert.ok(!/Waiting for the browser sign-in/.test(idle),
    "and does not invent a sign-in when none is running");
});

test("45e. it says Codex cannot be selected, and does NOT restate the row's reason", () => {
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const out = codexRender({ state:"chatgpt", billing:"covered by your ChatGPT plan" });
    /* REWORDED 2026-09-08. The old sentence was "signing in here does NOT make
       Codex selectable" -- true when nothing could install the CLI, and
       misleading once Sutra provisions it: a sign-in on a machine that has the
       runtime DOES make the row selectable, on the same paint. The claim that
       still needs making is that a credential is only HALF of it. */
    assert.ok(/credential\s*<i>and<\/i>\s*its command-line tool/.test(
                out.replace(/\s+/g, " ")),
      "the block must still say a credential alone is not enough");
    assert.ok(!/does <b>not<\/b> make Codex selectable/.test(out),
      "the superseded absolute claim is back");
    /* The row directly above prints `reason` verbatim -- both protocols, the
       version pin, the install path. Repeating it here put the same paragraph
       on screen twice. The block must say the one thing the row does not, and
       stop. */
    assert.ok(!out.includes(CODEX_ROW.reason),
      "the block repeats the row's reason back at the reader");
    assert.ok(!/stream-json|ACP|0\.153\.2|opt\/homebrew/.test(out),
      "no fragment of the adapter explanation is duplicated here");
  } finally { delete sandbox.sutra; }
});

test("45f. while a spawn runs its own button cancels and the others are dead", () => {
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const out = codexRender({ state:"logged_out" }, { busy:"login" });
    assert.ok(/>Cancel</.test(out), "the busy button became Cancel");
    assert.ok(/Waiting for the browser sign-in/.test(out), "and says why it waits");
    const others = out.match(/data-codex="apikey"[^>]*disabled/);
    assert.ok(others, "the other action is disabled while one runs");
  } finally { delete sandbox.sutra; }
});

test("45g. every credential-replacing action warns first, and only those", () => {
  /* The warning is the only thing standing between a click and a credential
     Sutra cannot restore, because it never had a copy. */
  const replaces = [["logout","chatgpt"], ["logout","api_key"],
                    ["login","api_key"], ["apikey","chatgpt"]];
  for (const [verb, state] of replaces){
    const t = T.codexConfirmText(verb, state);
    assert.ok(t, verb + " from " + state + " must warn before it replaces anything");
    assert.ok(/REPLACES|removes/.test(t), "the warning names the replacement: " + t);
    assert.ok(/go back|sign back in|restore/.test(t),
      "and says what getting back would take: " + t);
    /* The "Sutra never had a copy" clause is required exactly where a KEY is
       what gets destroyed. Leaving an API key means the operator needs the key
       itself again and nothing on this side can hand it back; leaving a
       ChatGPT sign-in just means signing in again, where the clause would be
       noise. */
    if (state === "api_key")
      assert.ok(/never had a copy/.test(t),
        "a key is being destroyed and nothing here can put it back: " + t);
  }
  /* Signing in from signed-out destroys nothing, so it must not nag. */
  assert.strictEqual(T.codexConfirmText("login", "logged_out"), null);
  assert.strictEqual(T.codexConfirmText("apikey", "logged_out"), null);
  assert.strictEqual(T.codexConfirmText("login", "unknown"), null);
});

test("45h. the API-key field is uncontrolled, so no key is ever held in state", () => {
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const out = codexRender({ state:"logged_out" }, { keyOpen:true });
    assert.ok(/data-codex-key/.test(out), "the field is there");
    assert.ok(/type="password"/.test(out), "and not in plain sight");
    assert.ok(!/value=/.test(out.slice(out.indexOf("data-codex-key") - 200,
                                       out.indexOf("data-codex-key") + 200)),
      "no value bound to state: the typed key lives only in the DOM node");
    assert.ok(/keeps no copy/.test(out), "and the field says Sutra keeps nothing");
  } finally { delete sandbox.sutra; }
});

/* ── 45i-45l. The Codex probe's async contract ──────────────────────────────
   These drive the SAME globals -- sandbox.fetch, sandbox.render, S.codexAuth --
   so registered straight into ASYNC_CHECKS they interleave and stomp each
   other. The first version of them did exactly that and reported a failure in
   the wrong test. They run SERIALLY through one queue, and each installs its
   own stubs at the moment it RUNS, not when it is declared.

   A failure does not cancel the ones behind it: the queue continues on a
   caught copy while the original carries the result to ASYNC_CHECKS. */
/* The queue starts after a real timer tick, not immediately. Other suites in
   this file (25j's stageInBackground, for one) call render() from their own
   async continuations, and those land on the microtask queue while a codex
   body is mid-await -- which showed up as a phantom render inside 45k and had
   me hunting a loop in code that no longer had one. Draining first makes the
   render counts below attributable. Same 20ms-tick trick 31e uses. */
let _codexQ = new Promise(r => setTimeout(r, 60));
function codexSerial(name, body){
  const mine = _codexQ.then(body);
  _codexQ = mine.catch(() => {});
  ASYNC_CHECKS.push(mine.catch(e => {
    throw new Error(name + " -- " + (e && e.message ? e.message : e));
  }));
}

/* Fresh stubs and a clean slate, with its own teardown. */
function codexStub(fetchImpl){
  const prevFetch = sandbox.fetch, prevRender = sandbox.render;
  let renders = 0;
  sandbox.render = () => { renders++; };
  sandbox.fetch = fetchImpl;
  T.PROVIDERS = [CODEX_ROW];
  T.S.codexAuth = null; T.S.codexProbing = false;
  return {
    renders: () => renders,
    reset: () => { renders = 0; },
    setFetch: f => { sandbox.fetch = f; },
    restore: () => { sandbox.fetch = prevFetch; sandbox.render = prevRender;
                     T.S.codexAuth = null; T.S.codexProbing = false; },
  };
}

const jsonOnce = payload => () => Promise.resolve(
  { ok:true, json: () => Promise.resolve(payload) });
const stillLoadingNow = () => /Reading the Codex sign-in/.test(T.codexAuthHtml());

/* 45i. A PERMANENT LOADING STATE IS THE WORST ANSWER THIS BLOCK CAN GIVE.
   The first build hooked the probe only into openScreen(), and boot() sets
   S.screen directly (09-tail.js) -- so the shell could come up on this screen
   with nothing having asked, and the block promised an answer that was never
   coming. Once loadCodexAuth has SETTLED, on any path, loading must be gone. */
codexSerial("45i", async () => {
  const h = codexStub(jsonOnce({ state:"chatgpt", key_display:"",
                                 billing:"usage included in your plan" }));
  try {
    await T.loadCodexAuth(true);
    assert.ok(!stillLoadingNow(), "a successful probe must leave the loading state");
    assert.ok(/Signed in with ChatGPT/.test(T.codexAuthHtml()), "and render the answer");

    /* the fetch rejects outright -- socket gone, backend restarted */
    T.S.codexAuth = null;
    h.setFetch(() => Promise.reject(new Error("socket closed")));
    await T.loadCodexAuth(true);
    assert.ok(!stillLoadingNow(), "a REJECTED probe must not sit on loading");
    assert.ok(/Could not tell which credential/.test(T.codexAuthHtml()),
      "it falls through to the honest unknown state");

    /* a non-2xx answer -- the shape apiGet turns into a throw */
    T.S.codexAuth = null;
    h.setFetch(() => Promise.resolve({ ok:false, status:500,
                                       json: () => Promise.resolve({ detail:"boom" }) }));
    await T.loadCodexAuth(true);
    assert.ok(!stillLoadingNow(), "a 500 must not sit on loading");
    assert.strictEqual(T.S.codexAuth.state, "unknown");

    /* a 200 carrying no state. Left falsy this would keep the loading state AND
       re-arm the wire() predicate on every render, forever. */
    T.S.codexAuth = null;
    h.setFetch(jsonOnce(null));
    await T.loadCodexAuth(true);
    assert.ok(T.S.codexAuth && T.S.codexAuth.state === "unknown",
      "a stateless 200 is coerced to unknown, never left null");
    assert.ok(!stillLoadingNow(), "a stateless 200 must not sit on loading");
  } finally { h.restore(); }
});

/* 45j. Does the probe ever fire? Pure predicate, so the answer needs no DOM. */
test("45j. the probe fires when the screen is up and nothing has been asked", () => {
  const prev = T.S.screen;
  try {
    T.S.screen = "settings"; T.S.codexAuth = null;
    assert.strictEqual(T.codexNeedsProbe(), true,
      "screen up, no answer yet -> the probe must fire");
    T.S.codexAuth = { state:"chatgpt" };
    assert.strictEqual(T.codexNeedsProbe(), false, "an answered probe must not re-fire");
    T.S.codexAuth = { state:"unknown", detail:"could not read it" };
    assert.strictEqual(T.codexNeedsProbe(), false,
      "a FAILED probe must not re-fire on every render either");
    T.S.screen = "chats"; T.S.codexAuth = null;
    assert.strictEqual(T.codexNeedsProbe(), false, "no probe for a screen that is not up");
  } finally { T.S.screen = prev; T.S.codexAuth = null; }
});

/* 45k. THE FREEZE, and the contract that makes it impossible.
   What shipped was `if (codexNeedsProbe()) loadCodexAuth().then(()=>render())`.
   While a probe is in flight the predicate is still true (no answer yet) and
   the loader early-returns on its in-flight guard -- and an early return from
   an async function is an ALREADY-RESOLVED promise. So the chained render
   fired, re-entered wire(), early-returned again, and looped at microtask
   speed, rebuilding the whole panel and re-binding every handler per turn.
   Nothing painted and nothing took input; and because apiGet carries no
   timeout, a probe that never landed never ended the loop.

   Pinned as a property of the LOADER, not as a model of the caller: it renders
   exactly when it has something new to show, and a call that does nothing
   renders nothing. That is what makes every caller safe as a bare call. */
codexSerial("45k", async () => {
  const h = codexStub(() => new Promise(() => {}));
  try {
    /* A. the in-flight guard blocks -- the case that used to hand the caller a
          resolved promise to loop on */
    T.S.codexProbing = true;
    await T.loadCodexAuth();
    assert.strictEqual(h.renders(), 0,
      "a call blocked by the in-flight guard rendered " + h.renders() + " time(s)");

    /* B. the answer-in-hand guard blocks */
    T.S.codexProbing = false; T.S.codexAuth = { state:"chatgpt" };
    await T.loadCodexAuth();
    assert.strictEqual(h.renders(), 0, "a call blocked by an answer in hand rendered too");

    /* C. a real probe renders its own result exactly once, so nothing needs to
          chain a render onto it */
    h.reset();
    T.S.codexAuth = null;
    h.setFetch(jsonOnce({ state:"chatgpt", key_display:"", billing:"x" }));
    await T.loadCodexAuth();
    assert.strictEqual(h.renders(), 1,
      "a completed probe must render its own result exactly once");
  } finally { h.restore(); }
});

/* 45k2. The other half of the same contract, read off the real source. The loop
   is invisible in any single function -- it exists only in the coupling between
   wire() and render() -- so the rule is enforced where it can be seen.
   Comments are stripped first: the explanation above quotes the very expression
   it forbids, and matching that would be a test failing on its own prose. */
test("45k2. no caller chains a render onto loadCodexAuth", () => {
  const raw = fs.readFileSync(path.join(__dirname, "static", "js", "07-loaders.js"), "utf8");
  const code = raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const chained = code.match(/loadCodexAuth\([^)]*\)\s*\.then/g) || [];
  assert.deepStrictEqual(chained, [],
    "a caller chains onto loadCodexAuth (" + chained.join(", ") + ") -- a "
    + "guard-blocked call resolves immediately and that render re-enters wire()");
});

/* 45l. The guard must not swallow the RE-PROBE. An action has just changed the
   credential, so the answer in hand is precisely the stale one. Without force
   the row keeps showing the state from before the sign-in -- the single thing
   this row exists not to do. This failed when first written: 0 requests. */
codexSerial("45l", async () => {
  let calls = 0;
  const h = codexStub(() => { calls++; return Promise.resolve({ ok:true,
    json: () => Promise.resolve({ state:"logged_out", key_display:"", billing:null }) }); });
  try {
    T.S.codexAuth = { state:"chatgpt", billing:"usage included in your plan" };
    await T.codexReprobe(false);
    assert.strictEqual(calls, 1,
      "codexReprobe made " + calls + " request(s) -- with an answer in hand the "
      + "guard swallowed the re-read, so the row would still show the old credential");
    assert.strictEqual(T.S.codexAuth.state, "logged_out", "and the NEW answer is what lands");
  } finally { h.restore(); }
});

/* ── 45m-45p. The sign-in POLL. ────────────────────────────────────────────
   The browser transport's route returns the instant the child exists, so the
   panel watches the CREDENTIAL rather than the process. A watch with no way to
   end is the same class of waste as the render loop this file already pinned,
   so every stop condition gets a test.

   Timers are FAKED here -- captured in a queue and drained by hand -- because
   the real cadence is 2s a tick and a test that sleeps is a test nobody runs. */
function codexFakeTimers(){
  const prev = sandbox.setTimeout;
  let queue = [];
  sandbox.setTimeout = (fn, ms) => { queue.push(fn); return queue.length; };
  return {
    pending: () => queue.length,
    /* one tick, awaited: the poll body is async and awaits the probe */
    tick: async () => { const q = queue; queue = []; for (const fn of q) await fn(); },
    restore: () => { sandbox.setTimeout = prev; },
  };
}

/* 45m. Nobody is looking -> stop watching. The founder's condition. Note it
   does NOT cancel the server child: that finishes or hits its own cap, and
   returning to the screen re-adopts it through login_in_flight. */
codexSerial("45m", async () => {
  let calls = 0;
  const h = codexStub(() => { calls++; return Promise.resolve({ ok:true,
    json: () => Promise.resolve({ state:"logged_out", login_in_flight:true }) }); });
  const t = codexFakeTimers();
  const prevScreen = T.S.screen;
  try {
    T.S.screen = "settings";
    T.S.codexAuth = { state:"logged_out" };
    T.S.codexBusy = "login";
    T.codexWatchLogin("logged_out");
    assert.strictEqual(T.S.codexPolling, true, "the watch starts");

    await t.tick();                       /* one poll while on screen */
    const after1 = calls;
    assert.ok(after1 >= 1, "it polls while the row is up");

    T.S.screen = "chats";                 /* the user leaves */
    await t.tick();
    assert.strictEqual(T.S.codexPolling, false, "leaving the screen stops the watch");
    assert.strictEqual(T.S.codexBusy, null, "and clears the local busy state");
    assert.strictEqual(t.pending(), 0, "with no further tick scheduled");
    await t.tick();
    assert.strictEqual(calls, after1,
      "and no probe fires against a screen nobody is looking at");
  } finally { t.restore(); h.restore(); T.S.screen = prevScreen; T.S.codexBusy = null;
             T.codexStopPoll(); }
});

/* 45n. The credential changed -> the sign-in landed, stop. */
codexSerial("45n", async () => {
  const h = codexStub(() => Promise.resolve({ ok:true,
    json: () => Promise.resolve({ state:"chatgpt", billing:"usage included in your plan",
                                  login_in_flight:false }) }));
  const t = codexFakeTimers();
  const prevScreen = T.S.screen;
  try {
    T.S.screen = "settings";
    T.S.codexAuth = { state:"logged_out" };
    T.S.codexBusy = "login";
    T.codexWatchLogin("logged_out");
    await t.tick();
    assert.strictEqual(T.S.codexAuth.state, "chatgpt", "the new credential landed");
    assert.strictEqual(T.S.codexPolling, false, "the watch stops on the change");
    assert.strictEqual(T.S.codexBusy, null, "the button stops saying Cancel");
    assert.strictEqual(T.S.codexMsg, null,
      "and no banner repeats what the row already says");
    assert.strictEqual(t.pending(), 0, "nothing further is scheduled");
  } finally { t.restore(); h.restore(); T.S.screen = prevScreen; T.codexStopPoll(); }
});

/* 45o. A second sign-in supersedes the first watcher instead of running two. */
codexSerial("45o", async () => {
  let calls = 0;
  const h = codexStub(() => { calls++; return Promise.resolve({ ok:true,
    json: () => Promise.resolve({ state:"logged_out", login_in_flight:true }) }); });
  const t = codexFakeTimers();
  const prevScreen = T.S.screen;
  try {
    T.S.screen = "settings";
    T.S.codexAuth = { state:"logged_out" };
    T.S.codexBusy = "login";
    T.codexWatchLogin("logged_out");
    T.codexWatchLogin("logged_out");      /* the second one wins */
    await t.tick();
    assert.strictEqual(calls, 1,
      "two watchers polled " + calls + " times for one sign-in");
  } finally { t.restore(); h.restore(); T.S.screen = prevScreen; T.S.codexBusy = null;
             T.codexStopPoll(); }
});

/* 45p. codexStopPoll invalidates a tick that is already scheduled -- the
   cancel path calls it, and a stale tick landing afterwards would re-adopt a
   sign-in the operator just stopped. */
codexSerial("45p", async () => {
  let calls = 0;
  const h = codexStub(() => { calls++; return Promise.resolve({ ok:true,
    json: () => Promise.resolve({ state:"logged_out", login_in_flight:true }) }); });
  const t = codexFakeTimers();
  const prevScreen = T.S.screen;
  try {
    T.S.screen = "settings";
    T.S.codexAuth = { state:"logged_out" };
    T.S.codexBusy = "login";
    T.codexWatchLogin("logged_out");
    T.codexStopPoll();
    await t.tick();
    assert.strictEqual(calls, 0, "a stopped watch must not probe");
    assert.strictEqual(T.S.codexPolling, false, "and reports itself stopped");
  } finally { t.restore(); h.restore(); T.S.screen = prevScreen; T.S.codexBusy = null; }
});

/* ── 45m-45t. Codex API-key MEMORY ──────────────────────────────────────────
   Codex holds one credential and each sign-in wipes the other (measured
   2026-09-08 on codex-cli 0.153.2: `tokens` and `last_refresh` are deleted
   outright). Sutra now keeps a copy of the API key so the switch is
   reversible. Everything below is about the two lies that copy makes possible:
   claiming the saved key is the LIVE one, and offering to remember on a
   machine that cannot. */

/* The bridge as it exists once the memory verbs ship. codexKeyRestore is
   checked separately because the verbs shipped AFTER codexLogin -- a shell
   built before this change has the first and not the second. */
const CODEX_MEM_BRIDGE = {
  codexLogin:      () => Promise.resolve({ ok:true }),
  codexKeyRestore: () => Promise.resolve({ ok:true }),
  codexKeyForget:  () => Promise.resolve({ ok:true }),
};
const SAVED = { stored:true, display:"sk-proj-***Kyt8A", saved_at:1757260000,
                store_available:true, store_reason:null };
const NOT_SAVED = { stored:false, display:"", saved_at:null,
                    store_available:true, store_reason:null };
const NO_STORE = { stored:false, display:"", saved_at:null, store_available:false,
                   store_reason:"this is Linux, where Sutra has no credential store yet." };

test("45m. a saved key is offered as a SWITCH and never as the live mode", () => {
  sandbox.sutra = CODEX_MEM_BRIDGE;
  try {
    const out = codexRender({ state:"chatgpt", billing:"usage included in your plan",
                              stored:SAVED });
    assert.ok(/Signed in with ChatGPT/.test(out), "the live mode still comes from the probe");
    assert.ok(/usage included in your plan/.test(out), "and so does the billing line");
    assert.ok(/data-codex="restore"/.test(out), "the saved key is offered");
    assert.ok(/Use saved API key sk-proj-\*\*\*Kyt8A/.test(out),
      "named with the stub CODEX printed, so the offer and the live row read alike");
    /* THE LIE THIS TEST EXISTS FOR. A saved key must never make the row say
       the user is billed per token while codex is on a ChatGPT plan. */
    assert.ok(!/billed per token/.test(out),
      "holding a key is not using one: no per-token claim over a ChatGPT session");
    assert.ok(/not using it right now/.test(out),
      "and the copy says plainly that codex is not on it");
  } finally { delete sandbox.sutra; }
});

test("45n. the key field says whether a copy is actually kept", () => {
  /* 45h pins the no-copy wording. That sentence is now CONDITIONAL, so the
     other branch needs pinning too -- otherwise remembering could quietly stop
     working and the copy would still read as correct. */
  sandbox.sutra = CODEX_MEM_BRIDGE;
  try {
    const kept = codexRender({ state:"logged_out", stored:NOT_SAVED }, { keyOpen:true });
    assert.ok(/login keychain/.test(kept), "it names where the copy goes");
    assert.ok(/switch back to it later/.test(kept), "and what the copy buys");
    assert.ok(!/keeps no copy/.test(kept), "and does not deny keeping one");
    assert.ok(/checks the key with OpenAI first/.test(kept),
      "codex accepts any text, so the field must say Sutra checks it -- this is the "
      + "one sentence that explains why a bad paste is refused instead of accepted");
    assert.ok(/401/.test(kept),
      "and name the failure it prevents, which is what the user would otherwise meet");
  } finally { delete sandbox.sutra; }

  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const not = codexRender({ state:"logged_out", stored:NO_STORE }, { keyOpen:true });
    assert.ok(/keeps no copy/.test(not), "an older shell still gets the honest sentence");
  } finally { delete sandbox.sutra; }
});

test("45o. a live key Sutra has no copy of warns BEFORE the switch, not after", () => {
  /* Entered in a terminal, or saved on a machine that could not keep it.
     Switching away destroys it and nothing here can put it back. */
  sandbox.sutra = CODEX_MEM_BRIDGE;
  try {
    const out = codexRender({ state:"api_key", key_display:"sk-proj-***SMnIA",
                              billing:"billed per token", stored:NOT_SAVED });
    assert.ok(/not saved in Sutra/.test(out), "it says the key is unheld");
    assert.ok(/would lose it/.test(out), "and what switching would cost");
    assert.ok(!/data-codex="restore"/.test(out),
      "and offers no restore, because there is nothing to restore");
    assert.ok(!/data-codex="forget"/.test(out), "nor a forget for a copy that does not exist");

    const held = codexRender({ state:"api_key", key_display:"sk-proj-***Kyt8A",
                               billing:"billed per token", stored:SAVED });
    assert.ok(!/not saved in Sutra/.test(held), "a held key draws no warning");
    assert.ok(/data-codex="forget"/.test(held), "and can be forgotten");
  } finally { delete sandbox.sutra; }
});

test("45p. no memory controls where there is no credential store", () => {
  /* The row must never draw a control that cannot work on this machine --
     Linux, Windows, or a Mac whose keychain will not load. */
  sandbox.sutra = CODEX_MEM_BRIDGE;
  try {
    for (const state of ["chatgpt", "logged_out", "api_key", "unknown"]) {
      const out = codexRender({ state, stored:NO_STORE });
      assert.ok(!/data-codex="restore"/.test(out), state + ": no restore without a store");
      assert.ok(!/data-codex="forget"/.test(out), state + ": no forget without a store");
    }
  } finally { delete sandbox.sutra; }
});

test("45q. a shell built before the memory verbs draws none of them", () => {
  /* codexLogin shipped first. Presence of the NEWER verb is the capability
     signal -- a page cannot conjure a preload, and an older one must degrade
     to the row it already had rather than to a dead button. */
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    const out = codexRender({ state:"chatgpt", stored:SAVED });
    assert.ok(!/data-codex="restore"/.test(out), "no restore on an older shell");
    assert.ok(!/data-codex="forget"/.test(out), "no forget either");
    assert.ok(/data-codex="apikey"/.test(out), "but the key field it already had stays");
  } finally { delete sandbox.sutra; }
});

test("45r. restore warns; forget warns and says it is NOT a sign-out", () => {
  const r = T.codexConfirmText("restore", "chatgpt");
  assert.ok(r, "switching onto the saved key replaces a credential, so it warns");
  assert.ok(/REPLACES/.test(r), "the warning names the replacement");
  assert.ok(/per token/.test(r), "and the billing consequence, which is the point of the row");

  const f = T.codexConfirmText("forget", "api_key");
  assert.ok(f, "deleting the only copy of a key warns");
  assert.ok(/does not sign you out/.test(f),
    "and distinguishes itself from Sign out -- a tidy-up must not read as destroying a session");

  /* Restoring from signed-out replaces nothing, so it must not nag. */
  assert.strictEqual(T.codexConfirmText("restore", "logged_out"), null);
});

test("45s. success messages claim exactly what was checked, and no more", () => {
  /* MEASURED (2026-09-08, 0.153.2): `codex login --with-api-key` accepted a
     deliberately fake key, exited 0 and printed "Successfully logged in", and
     the user met it later as a raw 401 retried five times. Sutra now probes the
     key against OpenAI BEFORE signing in, so "OpenAI accepted it" is a report of
     a request that really happened -- and saying it is the point, because it is
     what tells the user a bad paste would have been refused.

     The bound is that nothing may claim MORE than the probe established. One
     authenticated GET says the key authenticates today. It says nothing about
     quota, about tomorrow, or about whether any particular model is reachable. */
  const msgs = [T.codexDoneText("apikey:save", { ok:true, remembered:true }),
                T.codexDoneText("apikey:save", { ok:true, remembered:false, note:"no keychain." }),
                T.codexDoneText("restore", { ok:true, display:"sk-proj-***Kyt8A" })];
  for (const m of msgs) {
    assert.ok(/OpenAI accepted/.test(m), "the check is stated: " + m);
    for (const over of ["unlimited", "will work", "guaranteed", "verified forever"])
      assert.ok(!new RegExp(over, "i").test(m), over + " overstates the probe: " + m);
  }
});

test("45t. a failed copy does not read as a failed sign-in", () => {
  /* The login and the copy fail independently. codex is using the key either
     way, so a keychain that refused must not be reported as a sign-in that did. */
  /* THREE facts, three clauses: OpenAI accepted it, Codex is using it, Sutra
     kept a copy. They fail independently, so a keychain that refused must not
     read as a rejected key or a failed sign-in. */
  const bad = T.codexDoneText("apikey:save", { ok:true, remembered:false,
                                               note:"the login keychain would not keep a copy." });
  assert.ok(/OpenAI accepted/.test(bad), "the key was still accepted");
  assert.ok(/using it now/.test(bad), "and the sign-in still worked");
  assert.ok(/could not keep a copy/.test(bad), "and the shortfall is its own clause");
  assert.ok(/keychain/.test(bad), "carrying the reason through");

  const good = T.codexDoneText("apikey:save", { ok:true, remembered:true });
  assert.ok(/OpenAI accepted/.test(good) && /using it now/.test(good)
            && /switch to ChatGPT and back/.test(good),
    "and the happy path states all three");

  assert.ok(/still signed in/.test(T.codexDoneText("forget", { ok:true, removed:true })),
    "forgetting reassures that codex is untouched");
});

/* ── 46. a rejected API key must never be echoed back ───────────────────────
   The classified-error path in electron/main.js exists so the child's stderr
   never crosses the bridge -- on the --with-api-key path that stderr can
   contain the key that was just typed. This reads the real function out of
   main.js (which cannot be require()d here: it pulls in electron) and proves
   the property on the actual bytes, because "we return a fixed string" is
   exactly the kind of thing that regresses quietly. */
test("46a. codexError classifies and never quotes the child's stderr", () => {
  const src = fs.readFileSync(path.join(__dirname, "electron", "main.js"), "utf8");
  const start = src.indexOf("function codexError(");
  assert.ok(start > 0, "codexError is gone from main.js -- did the verb change shape?");
  const end = src.indexOf("\n}", start);
  const fn = vm.runInNewContext(src.slice(start, end + 2) + ";codexError");

  const KEY = "sk-proj-abcdef0123456789SECRET";
  const cases = [
    "Error: 401 Unauthorized - Incorrect API key provided: " + KEY,
    "invalid_api_key: " + KEY + " is not valid",
    "insufficient quota for key " + KEY,
    "connection timed out while checking " + KEY,
    "something nobody has seen before involving " + KEY,
  ];
  for (const stderr of cases){
    const out = fn(1, stderr);
    assert.ok(!out.includes(KEY), "the key was echoed back: " + out);
    assert.ok(!out.includes("sk-"), "a key-shaped fragment survived: " + out);
    assert.ok(out.length < 200, "the raw line leaked wholesale: " + out);
  }
  assert.ok(/rejected that API key/.test(fn(1, cases[0])), "a 401 is named as a bad key");
  assert.ok(/billing or quota/.test(fn(1, cases[2])), "a quota problem is named as one");
  assert.ok(/could not reach OpenAI/.test(fn(1, cases[3])), "a network failure is named");
  assert.ok(/exited 7/.test(fn(7, cases[4])), "an unknown failure carries the exit code");
});


/* ── 46. DeepSeek sign-in block ─────────────────────────────────────────────
   Why this row exists: before it, the only way to get a DeepSeek key onto a
   machine was `export DEEPSEEK_API_KEY=...` and a server restart, which the
   panel told you to do in a websocket error frame after you had already picked
   the provider and sent a message.

   It is NOT the codex row with different words. codex reports which of two
   billing modes its one credential is in and signing in there does not make
   codex selectable; here the key is half of whether the provider runs, so the
   only job is moving the row between not-signed-in and selectable.

   THE INVARIANT ACROSS EVERY ASSERTION BELOW: no render may contain a key.
   The row is fed a mask by the backend and has no other source. */

const DS_ROW = { id:"deepseek", name:"DeepSeek", installed:true, configured:false,
                 runnable:false, adapter:true, reason:"installed at /opt/homebrew/bin/deepseek, but no API key." };
const DS_FAKE = "sk-" + ["notreal","notreal","notreal"].join("-") + "4f2a";
const DS_MASK = "sk-****4f2a";

function dsRender(auth, opts){
  const o = opts || {};
  T.PROVIDERS = o.providers || [DS_ROW];
  T.SETTINGS = Object.assign({ provider:"claude" }, o.settings || {},
                             { deepseek_auth: auth });
  T.S.deepseekBusy = o.busy || null;
  T.S.deepseekMsg = o.msg || null;
  T.S.deepseekMsgOk = !!o.msgOk;
  return T.deepseekAuthHtml();
}

const DS_BRIDGE = { deepseekKeySave: () => Promise.resolve({ ok:true }),
                    deepseekKeyRemove: () => Promise.resolve({ ok:true }) };

function withDs(fn){
  const saved = sandbox.sutra;
  sandbox.sutra = DS_BRIDGE;
  try { return fn(); } finally { sandbox.sutra = saved; }
}

/* browser_session is what a CLI-run server reports: a one-time code was
   printed on its stdout and not yet spent. A desktop-started server sends
   available:false with the reason, and DS_NO_CODE below is that case. */
const DS_NONE = { state:"none", signed_in:false, env_var:null,
                  env_vars:["SUTRA_UI_DEEPSEEK_API_KEY","DEEPSEEK_API_KEY"],
                  mask:null, saved_at:null, stored_mask:null,
                  store_available:true, store_reason:null,
                  browser_session:{ available:true, claimed:false, reason:null },
                  reason:"no API key. […]" };

const DS_NO_CODE = { ...DS_NONE, browser_session:{ available:false, claimed:false,
  reason:"this server was started by the Sutra desktop app, which already owns "
       + "the key-writing channel, so no browser sign-in code was issued." } };

/* A browser that has already traded the code for a token. Runs `fn` with the
   token in sessionStorage and no Electron bridge -- the state the key field is
   allowed to exist in outside the desktop app. */
function withDsPaired(fn){
  const saved = sandbox.sutra;
  sandbox.sutra = undefined;
  sandbox.sessionStorage.setItem(T.DEEPSEEK_SESSION_KEY, "paired-token");
  try { return fn(); }
  finally {
    sandbox.sessionStorage.removeItem(T.DEEPSEEK_SESSION_KEY);
    sandbox.sutra = saved;
  }
}

/* A browser that has not. Explicit rather than implied by the default, because
   the token survives a reload and therefore survives one test into the next if
   anything forgets to clear it. */
function withDsBrowser(fn){
  const saved = sandbox.sutra;
  sandbox.sutra = undefined;
  sandbox.sessionStorage.removeItem(T.DEEPSEEK_SESSION_KEY);
  try { return fn(); } finally { sandbox.sutra = saved; }
}

test("46a. not signed in offers the field inline, and says what it costs", () => {
  const out = withDs(() => dsRender(DS_NONE));
  assert.ok(/DeepSeek needs an API key/.test(out), "names what is missing");
  assert.ok(/type="password"/.test(out), "the field never shows the key being typed");
  assert.ok(/data-deepseek-key/.test(out) && /data-deepseek="save"/.test(out), "field + Save");
  assert.ok(!/value=/.test(out),
    "the input is UNCONTROLLED -- a value bound to state would keep a key in S");
  assert.ok(/no plan to\s+inherit/.test(out), "says why a key is needed at all");
  assert.ok(/checked\s+with DeepSeek before anything is saved/.test(out),
    "and that it is validated before it is stored");
});

test("46b. signed in shows the mask and nothing else, plus Remove", () => {
  const out = withDs(() => dsRender({ ...DS_NONE, state:"stored", signed_in:true,
                                      mask:DS_MASK, stored_mask:DS_MASK,
                                      saved_at: Math.floor(Date.now()/1000) - 120,
                                      reason:null }));
  assert.ok(out.includes(DS_MASK), "the mask the backend built");
  assert.ok(!out.includes(DS_FAKE), "and never a key");
  assert.ok(/data-deepseek="remove"/.test(out), "Remove is offered");
  assert.ok(!/data-deepseek-key/.test(out), "and the field is gone -- write-only, no re-edit");
  assert.ok(/login keychain/.test(out), "says where it actually is");
  assert.ok(/2m ago/.test(out), "and when it was saved");
  assert.ok(/nothing needs restarting/.test(out), "no restart claim");
  assert.ok(!/settings\.json/.test(out),
    "the row is back to naming Sutra's own storage layout (founder 2026-09-07: "
    + "only show the minimum a user might want to see)");
});

test("46c. an env var DISABLES the field and names which var is winning", () => {
  /* The failure this prevents: saving a key that silently has no effect. The
     operator would see "Saved" and the old key would keep answering. */
  const out = withDs(() => dsRender({ ...DS_NONE, state:"env", signed_in:true,
                                      env_var:"DEEPSEEK_API_KEY", mask:DS_MASK,
                                      reason:null }));
  assert.ok(/DEEPSEEK_API_KEY/.test(out), "names the variable");
  assert.ok(/disabled/.test(out), "the field is disabled");
  assert.ok(!/data-deepseek="save"/.test(out), "and Save cannot be clicked");
  assert.ok(/would never be used/.test(out), "with the reason, so it is not a mystery");
  assert.ok(!/data-deepseek="remove"/.test(out),
    "Remove would imply this row owns the credential; the environment does");
});

test("46c2. an env var that SHADOWS a saved key says both exist", () => {
  /* Otherwise unsetting the variable looks like it signs you out, when there
     is a saved key waiting underneath. */
  const out = withDs(() => dsRender({ ...DS_NONE, state:"env", signed_in:true,
                                      env_var:"SUTRA_UI_DEEPSEEK_API_KEY",
                                      mask:"sk-****9911", stored_mask:DS_MASK,
                                      reason:null }));
  assert.ok(out.includes("sk-****9911") && out.includes(DS_MASK),
    "both masks, so the precedence is visible");
  assert.ok(/takes over/.test(out), "and what happens if the variable goes away");
});

test("46d. validating disables everything and says what is happening", () => {
  const out = withDs(() => dsRender(DS_NONE, { busy:"save" }));
  assert.ok(/aria-busy="true"/.test(out), "the button reports busy to a screen reader");
  assert.ok(/Checking…/.test(out), "and says so in words");
  assert.ok(/data-deepseek-key[^>]*disabled/.test(out), "the field is locked while it runs");
  assert.ok(/Nothing is saved until it says yes/.test(out),
    "the spinner copy states the guarantee");
});

test("46e. a refusal renders as a refusal, a success as a success", () => {
  const bad = withDs(() => dsRender(DS_NONE, { msg:"DeepSeek rejected that key.", msgOk:false }));
  assert.ok(/class="note b"/.test(bad), "a refusal is not painted as an all-clear");
  assert.ok(/rejected that key/.test(bad), "and carries the classified reason");

  const good = withDs(() => dsRender({ ...DS_NONE, state:"stored", signed_in:true,
                                       mask:DS_MASK, reason:null },
                                     { msg:"DeepSeek accepted the key", msgOk:true }));
  assert.ok(!/class="note b"/.test(good), "a success is not painted as a failure");
});

test("46f. no bridge and no code means no field and the variables named instead", () => {
  /* A desktop-started backend seen through a browser: the shell owns the write
     channel, no code was printed, and a key field here could only ever 403. */
  const out = withDsBrowser(() => dsRender(DS_NO_CODE));
  assert.ok(!/data-deepseek-key/.test(out), "no field a browser cannot use");
  assert.ok(!/data-deepseek="save"/.test(out), "and nothing to click");
  assert.ok(!/data-deepseek-code/.test(out), "and no code field, because there is no code");
  assert.ok(/SUTRA_UI_DEEPSEEK_API_KEY/.test(out) && /DEEPSEEK_API_KEY/.test(out),
    "both variables are named as the way in");
  assert.ok(/already owns the key-writing channel/.test(out),
    "with the server's own reason, so it does not read as a missing feature");
});

/* ── 46p-46u. the browser sign-in lane ──────────────────────────────────────
   WHAT WAS BROKEN. The key write route is token-gated and only Electron main
   held a token, so the row rendered "saving one is a desktop-app action" and
   no field -- which made the browser at 127.0.0.1 unable to sign in to
   DeepSeek at all, and that is where development happens.

   THE ORDER IS THE SAFETY PROPERTY. A page with no write lane must never draw
   a key field. So the code field comes first, and only a page that HOLDS a
   token draws the key field. Every assertion below is about that ordering. */

test("46p. an unpaired browser is offered the CODE field and no key field", () => {
  const out = withDsBrowser(() => dsRender(DS_NONE));
  assert.ok(/data-deepseek-code/.test(out), "the code field is drawn");
  assert.ok(/data-deepseek="pair"/.test(out), "with something to click");
  assert.ok(!/data-deepseek-key/.test(out),
    "and NO key field -- a key must not be typeable into a page that cannot deliver it");
  assert.ok(!/data-deepseek="save"/.test(out), "nor a Save that would 403");
  assert.ok(/sign-in code/.test(out), "names what to paste");
  assert.ok(/terminal you launched it from/.test(out), "and where to find it");
  assert.ok(/works once/.test(out), "and that it is single-use");
  assert.ok(!/value=/.test(out),
    "the code input is UNCONTROLLED, like the key input -- nothing bound to state");
});

test("46q. once paired, the key field appears and the code field goes", () => {
  const out = withDsPaired(() => dsRender(DS_NONE));
  assert.ok(/data-deepseek-key/.test(out) && /data-deepseek="save"/.test(out),
    "the key field is live");
  assert.ok(!/data-deepseek-code/.test(out), "and the code step is done with");
  /* The loopback sentence came OUT (founder 2026-09-07: only the minimum). What
     must still hold is that neither lane CLAIMS the other's transport -- the copy
     is now silent on transport, which is honest for both. */
  assert.ok(!/in-process/.test(out),
    "a browser render must not claim the desktop app's in-process hand-off");
  assert.ok(!out.includes(DS_FAKE), "no key, ever");
});

test("46r. the desktop bridge still wins and never mentions a code", () => {
  /* Lane 1 is unchanged. A shell-started server prints no code at all, so a
     bridge render that talked about pasting one would be nonsense. */
  const out = withDs(() => dsRender(DS_NO_CODE));
  assert.ok(/data-deepseek-key/.test(out), "the field is drawn as before");
  assert.ok(!/data-deepseek-code/.test(out), "and no pairing step is offered");
  assert.ok(!/127\.0\.0\.1/.test(out),
    "and no loopback claim: the bridge hands the key across in-process");
});

test("46s. a signed-in browser with no write lane is not given a dead Remove", () => {
  /* THE BUG THIS PINS: Remove was drawn whenever a key was stored, and its
     handler returned early with no bridge -- a button that did nothing at all,
     silently, on every browser. */
  const stored = { ...DS_NONE, state:"stored", signed_in:true,
                   mask:DS_MASK, stored_mask:DS_MASK, reason:null };
  const unpaired = withDsBrowser(() => dsRender(stored));
  assert.ok(!/data-deepseek="remove"/.test(unpaired), "no button that cannot work");
  assert.ok(/data-deepseek="pair"/.test(unpaired), "the way to make it work instead");
  assert.ok(unpaired.includes(DS_MASK), "and the row still says what is saved");

  const paired = withDsPaired(() => dsRender(stored));
  assert.ok(/data-deepseek="remove"/.test(paired), "paired, Remove is live");
  assert.ok(!/data-deepseek="pair"/.test(paired), "and the code step is gone");

  const noCode = withDsBrowser(() => dsRender({ ...stored,
    browser_session: DS_NO_CODE.browser_session }));
  assert.ok(!/data-deepseek="remove"/.test(noCode) && !/data-deepseek="pair"/.test(noCode),
    "no code and no bridge: neither control is offered");
  assert.ok(/restart the server/.test(noCode),
    "but the way out is named rather than left a mystery");
  assert.ok(!/com\.sutra\.provider/.test(noCode),
    "and it does not send a user into Keychain Access after an internal item name");
});

test("46t. the write lane is the token or the bridge, and nothing else", () => {
  assert.strictEqual(withDsBrowser(() => T.deepseekCanWrite()), false, "browser, unpaired");
  assert.strictEqual(withDsPaired(() => T.deepseekCanWrite()), true, "browser, paired");
  assert.strictEqual(withDs(() => T.deepseekCanWrite()), true, "desktop bridge");

  /* The token round-trips through sessionStorage and can be DROPPED -- which is
     what the panel does on a 403, so a restarted server falls back to the code
     field instead of re-offering a key field that cannot work. */
  withDsBrowser(() => {
    assert.strictEqual(T.deepseekSessionToken(), null, "nothing held to start");
    assert.strictEqual(T.deepseekSetSessionToken("t0k"), true, "stored");
    assert.strictEqual(T.deepseekSessionToken(), "t0k", "and read back");
    T.deepseekClearSessionToken();
    assert.strictEqual(T.deepseekSessionToken(), null, "and dropped on demand");
  });
});

test("46u. storage that throws costs the field, not the page", () => {
  /* sessionStorage throws outright in some private windows and webviews. The
     row has to render there -- without a field it cannot use, but render. */
  const saved = sandbox.sessionStorage, savedSutra = sandbox.sutra;
  sandbox.sutra = undefined;
  sandbox.sessionStorage = { getItem(){ throw new Error("denied"); },
                             setItem(){ throw new Error("denied"); },
                             removeItem(){ throw new Error("denied"); } };
  try {
    assert.strictEqual(T.deepseekSessionToken(), null, "no token, no throw");
    assert.strictEqual(T.deepseekSetSessionToken("t0k"), false,
      "and setting REPORTS the refusal -- the handler says so instead of drawing a field");
    const out = dsRender(DS_NONE);
    assert.ok(/data-deepseek-code/.test(out), "the code step still renders");
    assert.ok(!/data-deepseek-key/.test(out), "and no key field");
  } finally { sandbox.sessionStorage = saved; sandbox.sutra = savedSutra; }
});

test("46f2. a shell without the DeepSeek verb is not treated as a bridge", () => {
  /* window.sutra exists in any Sutra desktop build; deepseekKeySave does not
     exist in one built before this change. Keying off the wrong verb would
     draw a field whose only transport is absent. */
  const saved = sandbox.sutra;
  sandbox.sutra = { codexLogin: () => Promise.resolve({ ok:true }) };
  try {
    assert.strictEqual(T.deepseekBridge(), null, "codexLogin alone is not this bridge");
    assert.ok(!/data-deepseek-key/.test(dsRender(DS_NONE)), "so no field is drawn");
  } finally { sandbox.sutra = saved; }
});

test("46g. no keychain says so and does NOT offer a control that cannot work", () => {
  const out = withDs(() => dsRender({ ...DS_NONE, store_available:false,
    store_reason:"saving a key needs the macOS login keychain and this is Linux." }));
  assert.ok(/cannot save one/.test(out), "the headline states the limit");
  assert.ok(/this is Linux/.test(out), "with the reason from the backend");
  assert.ok(!/data-deepseek-key/.test(out) && !/data-deepseek="save"/.test(out),
    "and no field, because saving would have to lie or lose the key");
});

test("46h. an older backend that sends no state renders nothing at all", () => {
  /* A row is a claim. With nothing read, the honest render is no render --
     never "not signed in", which is a claim about the machine. */
  assert.strictEqual(withDs(() => dsRender(undefined)), "", "no state, no block");
  const gone = withDs(() => dsRender(DS_NONE, { providers:[
    { id:"claude", name:"Claude Code", runnable:true }] }));
  assert.strictEqual(gone, "", "and nothing when deepseek is not in the catalogue");
});

test("46i. NO render state can contain a key, on any transport", () => {
  const states = [
    DS_NONE,
    DS_NO_CODE,
    { ...DS_NONE, state:"stored", signed_in:true, mask:DS_MASK, reason:null },
    { ...DS_NO_CODE, state:"stored", signed_in:true, mask:DS_MASK, reason:null },
    { ...DS_NONE, state:"env", signed_in:true, env_var:"DEEPSEEK_API_KEY",
      mask:DS_MASK, stored_mask:DS_MASK, reason:null },
    { ...DS_NONE, store_available:false, store_reason:"no keychain" },
  ];
  /* All THREE transports, because each takes a different branch now: the
     bridge, a paired browser, and an unpaired one drawing the code field. A
     sweep over one of them would have left the other two unswept. */
  const transports = [["bridge", withDs], ["paired", withDsPaired],
                      ["browser", withDsBrowser]];
  states.forEach((a, i) => {
    [null, "save", "remove", "pair"].forEach(busy => {
      transports.forEach(([label, wrap]) => {
        const out = wrap(() => dsRender(a, { busy, msg:DS_FAKE, msgOk:false }));
        /* msg is deliberately set to a key-shaped string: the message channel is
           the one place a backend could hand the row something it should not
           render, and if that ever changes this test says so. */
        assert.ok(!out.includes(DS_FAKE.slice(0, 20)) || /note/.test(out),
          label + " state " + i + " must not leak a key outside a message it was handed");
        assert.ok(!/-notreal-notreal4f2a[^<]*value=/.test(out),
          label + " state " + i + " must never put a key in an input value");
      });
    });
  });
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

/* ── 47a-h. turn options and permission modes are the PANE'S provider's ────
   The panel rendered Claude's five turn options and all six of Claude's
   permission modes on every pane. On a DeepSeek pane the five were collected,
   sent, and dropped by the server -- ACP's per-turn request has no field to
   carry them -- and three of the six ran as `default` while this control kept
   displaying the operator's choice. Both read as settings that took effect.

   Same shape as the Model picker (35p-t above) and the same fix: the provider
   declares what it can honour, the client renders from that. */

const TOPTS = {
  claude: ["effort", "max_budget_usd", "allowed_tools", "disallowed_tools",
           "append_system_prompt"],
};
const PMODES = {
  claude: ["plan", "acceptEdits", "bypassPermissions", "auto", "manual", "dontAsk"],
  deepseek: ["plan", "acceptEdits", "bypassPermissions"],
};
const SIX = PMODES.claude.map(id => ({
  id, writes_files: id === "acceptEdits" || id === "bypassPermissions" }));

/* Runs permSelect with an explicit provider map, mode list and stored mode. */
function permWith(mpid, cur, byProvider) {
  const pv = T.PERM_MODES, pb = T.PERM_MODES_BY_PROVIDER, ps = T.SETTINGS;
  try {
    T.PERM_MODES = SIX;
    T.PERM_MODES_BY_PROVIDER = byProvider === undefined ? PMODES : byProvider;
    T.SETTINGS = { permission_mode: cur, permission_mode_effective: cur };
    return T.permSelect(mpid);
  } finally { T.PERM_MODES = pv; T.PERM_MODES_BY_PROVIDER = pb; T.SETTINGS = ps; }
}
const permOptions = h =>
  [...h.matchAll(/<option value="([^"]*)"([^>]*)>/g)]
    .map(m => ({ id: m[1], attrs: m[2] }));

function toptsWith(mpid, byProvider) {
  const prev = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.TURN_OPTIONS_BY_PROVIDER = byProvider === undefined ? TOPTS : byProvider;
    return T.turnOptsHtml("s47", mpid);
  } finally { T.TURN_OPTIONS_BY_PROVIDER = prev; }
}
const fieldsIn = h =>
  [...h.matchAll(/data-opt="([^"]+)"/g)].map(m => m[1]);

test("47a. a Claude pane still gets all five turn options", () => {
  assert.deepStrictEqual(fieldsIn(toptsWith("claude")), TOPTS.claude,
    "Claude's controls must not move -- that is the constraint on this change");
});

test("47b. a DeepSeek pane gets NO turn option fields", () => {
  /* Not one of the five survives the trip: build_acp_args has no per-turn argv
     and session/prompt takes only {sessionId, prompt[]}. */
  assert.deepStrictEqual(fieldsIn(toptsWith("deepseek")), []);
});

test("47c. 'Allow only' is never rendered on a DeepSeek pane", () => {
  /* The one that must not be 'fixed' later. DeepSeek's CLI HAS an
     --allowed-tools flag, but it AUTO-APPROVES tools rather than restricting
     them -- so wiring this box to it would widen permissions for an operator
     trying to narrow them. Absent is the correct render. */
  const h = toptsWith("deepseek");
  assert.ok(!/data-opt="allowed_tools"/.test(h), h);
  assert.ok(!/Allow only/.test(h), h);
});

test("47d. before /api/settings resolves, every option still renders", () => {
  /* Empty map means NOT FETCHED, not "nobody honours anything". Stripping
     controls off a pane on a slow settings fetch would be a new bug. */
  assert.deepStrictEqual(fieldsIn(toptsWith("deepseek", {})), TOPTS.claude);
  assert.deepStrictEqual(fieldsIn(toptsWith("claude", {})), TOPTS.claude);
});

test("47e. the Turn options ROW is omitted, not opened onto an empty box", () => {
  const shown = paneMenuWith(DS_MODELS, "claude", { provider: "claude" });
  const prev = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.TURN_OPTIONS_BY_PROVIDER = TOPTS;
    const claude = paneMenuWith(DS_MODELS, "claude", { provider: "claude" });
    const deepseek = paneMenuWith(DS_MODELS, "deepseek", { provider: "claude" });
    assert.ok(/data-mrow="opts"/.test(claude), "Claude keeps the row");
    assert.ok(!/data-mrow="opts"/.test(deepseek),
      "a provider honouring none must not offer the row: " + deepseek);
  } finally { T.TURN_OPTIONS_BY_PROVIDER = prev; }
  assert.ok(shown.length > 0);
});

test("47f. a Claude pane still offers all six permission modes", () => {
  const ids = permOptions(permWith("claude", "plan")).map(o => o.id);
  assert.deepStrictEqual(ids, PMODES.claude);
});

test("47g. a DeepSeek pane offers only the three modes it can enforce", () => {
  const ids = permOptions(permWith("deepseek", "plan")).map(o => o.id);
  assert.deepStrictEqual(ids, PMODES.deepseek);
  const sel = permOptions(permWith("deepseek", "plan")).filter(o => /selected/.test(o.attrs));
  assert.strictEqual(sel.length, 1, "exactly one option is selected");
  assert.strictEqual(sel[0].id, "plan");
});

test("47h. a stored mode this provider cannot offer is SHOWN, not silently swapped", () => {
  /* THE EDGE CASE. permission_mode is stored globally, so a pane can inherit a
     `dontAsk` chosen while Claude was selected. Filtering it out of the list
     leaves no option carrying `selected`, and the browser then displays the
     FIRST one -- so a pane running `default` would have claimed to be in
     `plan`. That is the same mis-report this whole change exists to remove,
     recreated inside the control meant to fix it. */
  const h = permWith("deepseek", "dontAsk");
  const opts = permOptions(h);
  assert.strictEqual(opts[0].id, "dontAsk",
    "the stored mode must still be the one shown: " + h);
  assert.ok(/selected/.test(opts[0].attrs),
    "it must be SELECTED, or the browser shows the first supported mode "
    + "and the pane misreports what is running: " + h);
  assert.ok(/disabled/.test(opts[0].attrs),
    "and disabled, because it cannot be applied here: " + h);
  assert.ok(/not supported by DeepSeek/.test(h), "must say why: " + h);
  /* And no supported option may ALSO claim to be selected. */
  const sel = opts.filter(o => /selected/.test(o.attrs));
  assert.strictEqual(sel.length, 1, "two selected options: " + h);
  assert.strictEqual(sel[0].id, "dontAsk");
});

test("47i. an unsupported stored mode does not paint the composer red", () => {
  /* permSelect reads writes_files from the FULL list so Claude's warn class is
     computed exactly as before. Safe only while the omitted modes are the
     non-writing ones -- pinned server-side too
     (test_every_mode_deepseek_omits_is_a_non_writing_one). */
  assert.ok(!/permsel warn/.test(permWith("deepseek", "dontAsk")));
  assert.ok(/permsel warn/.test(permWith("claude", "bypassPermissions")),
    "a real write-capable mode must still warn");
});

test("47j. a provider with no declared modes keeps ALL of them", () => {
  /* The opposite fallback from turn options, deliberately: a missing entry
     must never leave a pane with no way to say `plan`. Hiding a safety control
     is the wrong direction to be wrong in. */
  const ids = permOptions(permWith("codex", "plan")).map(o => o.id);
  assert.deepStrictEqual(ids, PMODES.claude);
});

/* ── 48. THE PANE NOBODY HAS ASKED ANYTHING YET (founder 2026-09-07) ────────
   Section 47 above proved the gating works when it is HANDED a provider id.
   Nothing proved the panel could work out which id to hand it, and on an
   unstarted pane it could not: the provider frame arrives with the socket, so
   `channel` is null until the first message, and before /api/settings resolves
   SETTINGS is null too. paneProvider returned undefined, every consumer took
   its not-loaded branch, and for turn options that branch is Claude's five.

   So a fresh DeepSeek pane showed all five turn options -- in exactly the
   window when this menu gets opened, which is BEFORE asking anything, to set
   something first. 47d pinned that fallback as correct without ever asking
   which provider was on the other side of it.

   The fix is app.py putting the declarations in the page (a meta 01-state
   reads at parse time), so "which provider?" has an answer on the first paint.
   These tests are written against the UNSTARTED pane specifically -- channel
   null -- because that is the state every one above skipped. */

const DECL_TOPTS = {
  claude: ["effort", "max_budget_usd", "allowed_tools", "disallowed_tools",
           "append_system_prompt"],
};
const DECL_PMODES = {
  claude: ["plan", "acceptEdits", "bypassPermissions", "auto", "manual", "dontAsk"],
  deepseek: ["plan", "acceptEdits", "bypassPermissions"],
};

/* Renders the pane menu for a pane with NOTHING ASKED YET.
     served   -- which provider's machine served the page (the meta), or null
                 for a page with no declarations at all
     fetched  -- has GET /api/settings landed? false is the boot window
   The maps behave as the browser's do: seeded from the page, replaced by the
   fetch. Never force-cleared, because after this change the browser has no way
   to reach an empty map on a page that carried a seed. */
function unstartedPane({ served, fetched, stored }) {
  const prev = {
    ch: PANE_S.channel, set: T.SETTINGS, seed: T.SEED, menu: T.S.paneMenu,
    to: T.TURN_OPTIONS_BY_PROVIDER, pm: T.PERM_MODES_BY_PROVIDER, pv: T.PERM_MODES,
  };
  try {
    PANE_S.channel = null;              /* THE POINT: no provider frame yet */
    /* paneMenuHtml returns "" unless THIS pane's menu is the open one. Without
       it every "no Turn options row" assertion below passes against an empty
       string -- which is how the first version of 48a and 48b passed while
       proving nothing. assertOpen() keeps that from coming back. */
    T.S.paneMenu = PANE_S.id;
    T.SEED = served ? {
      provider: served,
      turn_options_by_provider: DECL_TOPTS,
      permission_modes_by_provider: DECL_PMODES,
    } : {};
    T.TURN_OPTIONS_BY_PROVIDER = T.SEED.turn_options_by_provider || {};
    T.PERM_MODES_BY_PROVIDER = T.SEED.permission_modes_by_provider || {};
    T.PERM_MODES = fetched ? SIX : [];
    T.SETTINGS = fetched
      ? { provider: served, permission_mode: stored || "plan",
          permission_mode_effective: stored || "plan" }
      : null;
    if (fetched) {                      /* the same response carries both */
      T.TURN_OPTIONS_BY_PROVIDER = DECL_TOPTS;
      T.PERM_MODES_BY_PROVIDER = DECL_PMODES;
    }
    return {
      menu: T.paneMenuHtml(PANE_S),
      decl: T.paneDeclProvider(PANE_S),
      running: T.paneProvider(PANE_S),
      perm: T.permSelect(T.paneDeclProvider(PANE_S)),
    };
  } finally {
    PANE_S.channel = prev.ch; T.SETTINGS = prev.set; T.SEED = prev.seed;
    T.S.paneMenu = prev.menu;
    T.TURN_OPTIONS_BY_PROVIDER = prev.to; T.PERM_MODES_BY_PROVIDER = prev.pm;
    T.PERM_MODES = prev.pv;
  }
}
const hasOptsRow = h => /data-mrow="opts"/.test(h);
/* An absent row and an absent MENU are not the same finding, and only one of
   them is this section's subject. */
const assertOpen = h => assert.ok(/class="upop panemenu"/.test(h),
  "the pane menu did not render at all -- the assertion below would be vacuous");

test("48a. a DeepSeek pane with nothing asked yet has NO Turn options row", () => {
  /* The founder's report. Settings HAVE loaded here -- this is the state a
     pane sits in for as long as it goes unused. */
  const r = unstartedPane({ served: "deepseek", fetched: true });
  assertOpen(r.menu);
  assert.strictEqual(r.decl, "deepseek",
    "the pane could not work out its own provider before the first turn");
  assert.ok(!hasOptsRow(r.menu), "Turn options rendered on a DeepSeek pane: " + r.menu);
});

test("48b. ...and not during the boot window either, before /api/settings", () => {
  /* THE ACTUAL DEFECT. SETTINGS is null, so the id can only come from the
     page. Without the seed this is where Claude's five appeared. */
  const r = unstartedPane({ served: "deepseek", fetched: false });
  assertOpen(r.menu);
  assert.strictEqual(r.running, undefined,
    "paneProvider must stay undefined until something has actually reported");
  assert.strictEqual(r.decl, "deepseek", "the declaring provider must come from the page");
  assert.ok(!hasOptsRow(r.menu), "Turn options rendered during boot: " + r.menu);
});

test("48c. a Claude pane keeps its Turn options row in BOTH those states", () => {
  /* The constraint on the whole change. A control that blinks out during boot
     and back in afterwards is its own defect. */
  for (const fetched of [true, false]) {
    const r = unstartedPane({ served: "claude", fetched });
    assertOpen(r.menu);
    assert.ok(hasOptsRow(r.menu),
      `Claude lost the Turn options row (fetched=${fetched}): ` + r.menu);
  }
});

test("48d. an unstarted DeepSeek pane never offers a mode it cannot run", () => {
  /* Asked for alongside turn options: `plan` showing there is correct, but it
     is also what a fallback would show, so the LIST is what settles it.

     The two states differ, and the first version of this test was wrong to
     expect them not to. The mode list is the server's vocabulary (PERM_MODES);
     before that lands there is nothing to list but the mode in force, so the
     boot window legitimately shows exactly one option. The claim that holds in
     BOTH is the one worth pinning: nothing DeepSeek cannot enforce. */
  const fetchedIds = permOptions(unstartedPane({ served: "deepseek", fetched: true }).perm)
    .map(o => o.id);
  assert.deepStrictEqual(fetchedIds, DECL_PMODES.deepseek);

  const bootIds = permOptions(unstartedPane({ served: "deepseek", fetched: false }).perm)
    .map(o => o.id);
  assert.deepStrictEqual(bootIds, ["plan"],
    "with no vocabulary fetched the select can only carry the mode in force");
  for (const ids of [fetchedIds, bootIds])
    for (const id of ids)
      assert.ok(DECL_PMODES.deepseek.includes(id),
        `offered "${id}", which DeepSeek cannot enforce`);
});

test("48e. an unstarted Claude pane still offers all six", () => {
  const ids = permOptions(unstartedPane({ served: "claude", fetched: true }).perm)
    .map(o => o.id);
  assert.deepStrictEqual(ids, DECL_PMODES.claude);
});

test("48f. a mode stored under Claude is labelled, not offered, on a fresh DeepSeek pane", () => {
  /* 47h's edge case, reached through resolution rather than a handed-in id:
     permission_mode is global, so an unused DeepSeek pane inherits it. */
  const r = unstartedPane({ served: "deepseek", fetched: true, stored: "dontAsk" });
  assert.ok(/not supported by/.test(r.perm), r.perm);
  const sel = permOptions(r.perm).filter(o => /selected/.test(o.attrs));
  assert.strictEqual(sel.length, 1, "exactly one option stays selected");
  assert.strictEqual(sel[0].id, "dontAsk");
});

test("48g. the two resolvers are NOT interchangeable", () => {
  /* Pins the split. paneDeclProvider may read the page's seed; paneProvider
     may not, because the Usage row keys off it and usageKindOf answers "none"
     for any id while PROVIDERS is unfetched -- so a known id would turn "not
     reported for default" into "not reported for DeepSeek", a vague false
     claim sharpened into a specific one. Collapsing these two functions is
     what this test exists to fail. */
  const r = unstartedPane({ served: "deepseek", fetched: false });
  assert.strictEqual(r.running, undefined, "paneProvider consumed the seed");
  assert.notStrictEqual(r.decl, r.running, "the two resolvers agree where they must not");
  assert.ok(!/not reported for DeepSeek/.test(r.menu),
    "the seed reached the Usage row: " + r.menu);
});

test("48h. a page served without declarations behaves exactly as before", () => {
  /* Backwards compatibility, and it is not hypothetical: a cached page from
     before this shipped has no meta, and app.py returns "" if the lookup
     throws. Both give SEED = {}, and then the not-loaded fallback 47d pins is
     what runs -- Claude's five, on every pane, which is the old behaviour
     rather than a new failure. */
  const r = unstartedPane({ served: null, fetched: false });
  assertOpen(r.menu);
  assert.strictEqual(r.decl, undefined);
  assert.ok(hasOptsRow(r.menu), "the pre-seed fallback must be untouched");
});

test("48i. readDeclarations survives every malformed attribute", () => {
  /* It runs at parse time, before anything can catch for it: a throw here is
     a blank panel.
     Asserted on KEYS, not with deepStrictEqual against {}. The function builds
     its object inside the vm realm, whose Object.prototype is not this file's,
     and deepStrictEqual compares prototypes -- so the object-literal version
     of this test failed on a correct return value. */
  const prev = sandbox.document.querySelector;
  const keys = () => Object.keys(T.readDeclarations());
  try {
    for (const content of ["", "{", "null", "[]", "3", '"x"', undefined, 7]) {
      sandbox.document.querySelector = () => ({ content });
      assert.deepStrictEqual(keys(), [],
        "malformed content did not degrade to empty: " + JSON.stringify(content));
    }
    sandbox.document.querySelector = () => null;
    assert.deepStrictEqual(keys(), [], "a missing meta must be empty");
    sandbox.document.querySelector = () => ({ content: '{"provider":"deepseek"}' });
    assert.deepStrictEqual(keys(), ["provider"], "the real parse path must actually work");
    assert.strictEqual(T.readDeclarations().provider, "deepseek");
  } finally { sandbox.document.querySelector = prev; }
});

/* ── 49. Codex: the join between "signed in" and "can be picked" ────────────
   THE BUG THESE CLOSE (2026-09-08). `S.codexAuth` and `PROVIDERS` are separate
   state, and only the first was ever refreshed after a sign-in. PROVIDERS is
   filled exactly once, by loadRuntime() inside boot(); nothing else in the app
   re-reads it. So a successful ChatGPT sign-in updated the sign-in block and
   left the ROW above it -- "Ready to use", and the radio's disabled attribute,
   both read off PROVIDERS -- showing what was true when the window opened.
   Only a page reload fixed it.

   45n above already pinned that a completed sign-in updates
   S.codexAuth.state, and it passed for the whole life of the bug, because
   nothing looked at the row. Every test here looks at the row. */

const CODEX_ROW_BLOCKED = { id:"codex", name:"OpenAI Codex", installed:true,
                            configured:false, runnable:false, adapter:true,
                            reason:"installed, but nobody is signed in" };
const CODEX_ROW_READY   = { id:"codex", name:"OpenAI Codex", installed:true,
                            configured:true, runnable:true, adapter:true,
                            reason:null };
const CODEX_ROW_ABSENT  = { id:"codex", name:"OpenAI Codex", installed:false,
                            configured:false, runnable:false, adapter:true,
                            reason:"binary 'codex' not on PATH" };

/* 49a. THE FIX ITSELF: one answer moves both halves. */
codexSerial("49a", async () => {
  const h = codexStub(jsonOnce({
    state:"chatgpt", key_display:"", billing:"usage included in your plan",
    providers:[CODEX_ROW_READY], settings:{ provider:"codex" },
    runtime:{ installed:true, can_install:true, reason:null } }));
  try {
    T.PROVIDERS = [CODEX_ROW_BLOCKED];
    T.SETTINGS = { provider:"claude" };
    await T.loadCodexAuth(true);
    assert.strictEqual(T.PROVIDERS[0].runnable, true,
      "the row did not move -- this is the reload-required bug");
    assert.strictEqual(T.SETTINGS.provider, "codex", "settings did not move");
    assert.strictEqual(T.S.codexRuntime.installed, true, "the runtime half is missing");
  } finally { h.restore(); }
});

/* 49b. A sign-in landing through the WATCH makes the row selectable on the
   same paint. The end-to-end version of 45n, asserting what 45n could not. */
codexSerial("49b", async () => {
  const h = codexStub(jsonOnce({
    state:"chatgpt", billing:"usage included in your plan", login_in_flight:false,
    providers:[CODEX_ROW_READY], settings:{ provider:"codex" } }));
  const t = codexFakeTimers();
  const prevScreen = T.S.screen;
  try {
    T.S.screen = "settings";
    T.PROVIDERS = [CODEX_ROW_BLOCKED];
    T.S.codexAuth = { state:"logged_out" };
    T.S.codexBusy = "login";
    T.codexWatchLogin("logged_out");
    await t.tick();
    assert.strictEqual(T.S.codexAuth.state, "chatgpt", "the credential landed");
    assert.strictEqual(T.PROVIDERS[0].runnable, true,
      "the sign-in landed and the row STILL cannot be picked");
  } finally { t.restore(); h.restore(); T.S.screen = prevScreen;
              T.S.codexBusy = null; T.codexStopPoll(); }
});

/* 49c. ...and the row is what the RADIO reads, so pin the rendered markup too.
   A `runnable` that never reaches the DOM is the same bug one layer down. */
codexSerial("49c", async () => {
  const h = codexStub(jsonOnce({
    state:"chatgpt", providers:[CODEX_ROW_READY], settings:{ provider:"claude" } }));
  const prevSettings = T.SETTINGS, prevModes = T.PERM_MODES;
  try {
    T.PROVIDERS = [CODEX_ROW_BLOCKED];
    T.SETTINGS = { provider:"claude", permission_mode:"plan", workdir:"/tmp" };
    T.PERM_MODES = [];
    const before = T.SCREENS.settings();
    assert.ok(/Installed, but not signed in yet/.test(before), before.slice(0, 400));

    await T.loadCodexAuth(true);
    const after = T.SCREENS.settings();
    assert.ok(/Ready to use/.test(after), "the row never says Ready to use");
    const row = after.slice(after.indexOf('data-prov="codex"'));
    assert.ok(!/^[^>]*disabled/.test(row), "the radio is still disabled: " + row.slice(0, 200));
  } finally { h.restore(); T.SETTINGS = prevSettings; T.PERM_MODES = prevModes; }
});

/* 49d. THE OPPOSITE DIRECTION, and the more dangerous one. A row saying
   "Ready to use" over a signed-out Codex is an offer that dies at the first
   message. */
codexSerial("49d", async () => {
  const h = codexStub(jsonOnce({
    state:"logged_out", providers:[CODEX_ROW_BLOCKED],
    settings:{ provider:"claude", provider_ignored:[{ id:"codex" }] } }));
  try {
    T.PROVIDERS = [CODEX_ROW_READY];
    T.SETTINGS = { provider:"codex" };
    await T.loadCodexAuth(true);
    assert.strictEqual(T.PROVIDERS[0].runnable, false,
      "signing out left the row offering a Codex with no credential");
    assert.strictEqual(T.SETTINGS.provider, "claude",
      "the active provider did not fall back");
  } finally { h.restore(); }
});

/* 49e. AN OLDER BACKEND MUST NOT BLANK THE SCREEN. The panel is served fresh
   by the backend, but a cached page, a proxy, or a half-updated install can
   pair a new panel with an old server. Omission is not an answer of []. */
codexSerial("49e", async () => {
  const h = codexStub(jsonOnce({ state:"chatgpt", key_display:"", billing:"x" }));
  const prevSettings = T.SETTINGS;
  try {
    T.PROVIDERS = [CODEX_ROW_READY];
    T.SETTINGS = { provider:"codex" };
    await T.loadCodexAuth(true);
    assert.strictEqual(T.PROVIDERS.length, 1, "PROVIDERS was wiped");
    assert.strictEqual(T.PROVIDERS[0].runnable, true, "PROVIDERS was replaced");
    assert.strictEqual(T.SETTINGS.provider, "codex", "SETTINGS was wiped");
    assert.strictEqual(T.S.codexAuth.state, "chatgpt", "the credential still lands");
  } finally { h.restore(); T.SETTINGS = prevSettings; }
});

/* 49f. codexApplyState is the whole guard, so pin it directly against every
   shape a wire can produce. `if (r.providers)` would let most of these
   through -- and `{}` was the one that mattered: it is an object, so a
   typeof check alone replaced a good SETTINGS with one holding no provider,
   no permission mode and no workdir. Every screen then renders its own
   not-loaded fallback, which is a blank panel dressed as a successful read. */
test("49f. only a real provider array and a real settings object are applied", () => {
  const prevP = T.PROVIDERS, prevS = T.SETTINGS, prevR = T.S.codexRuntime;
  try {
    for (const bad of [null, undefined, "many", 3, {}, true, []]) {
      T.PROVIDERS = [CODEX_ROW_READY]; T.SETTINGS = { provider:"codex" };
      T.codexApplyState({ state:"chatgpt", settings:bad });
      assert.strictEqual(T.SETTINGS.provider, "codex", "settings=" + JSON.stringify(bad));
    }
    for (const bad of [null, undefined, "many", 3, {}, true]) {
      T.PROVIDERS = [CODEX_ROW_READY];
      T.codexApplyState({ state:"chatgpt", providers:bad });
      assert.strictEqual(T.PROVIDERS[0].runnable, true, "providers=" + JSON.stringify(bad));
    }
    assert.strictEqual(T.codexApplyState(null), false, "a null answer applies nothing");
    assert.strictEqual(T.codexApplyState("nope"), false, "a string applies nothing");
    assert.strictEqual(T.codexApplyState({ providers:[] }), true,
      "an empty list IS an answer and must be taken");
    assert.strictEqual(T.codexApplyState({ settings:{ provider:null } }), true,
      "a settings object carrying the contract key is taken even when the "
      + "value is null -- that is what 'nothing runnable' looks like");
  } finally { T.PROVIDERS = prevP; T.SETTINGS = prevS; T.S.codexRuntime = prevR; }
});

/* 49g. A PROBE THAT COULD NOT BE UNDERSTOOD STILL CARRIED A GOOD ROW.
   The state check and the row are independent, and coupling them would keep
   the row stale for a reason that has nothing to do with the row. */
codexSerial("49g", async () => {
  const h = codexStub(jsonOnce({ providers:[CODEX_ROW_READY] }));   /* no `state` */
  try {
    T.PROVIDERS = [CODEX_ROW_BLOCKED];
    await T.loadCodexAuth(true);
    assert.strictEqual(T.S.codexAuth.state, "unknown", "a stateless 200 is still unknown");
    assert.strictEqual(T.PROVIDERS[0].runnable, true, "but the row it carried was thrown away");
  } finally { h.restore(); }
});

/* 49h. A FAILED FETCH CHANGES NOTHING. The synthetic unknown must not reach
   codexApplyState -- it has no providers, and a wipe here would blank the
   screen every time the backend hiccuped. */
codexSerial("49h", async () => {
  const h = codexStub(() => Promise.reject(new Error("socket closed")));
  const prevS = T.SETTINGS;
  try {
    T.PROVIDERS = [CODEX_ROW_READY];
    T.SETTINGS = { provider:"codex" };
    await T.loadCodexAuth(true);
    assert.strictEqual(T.S.codexAuth.state, "unknown");
    assert.strictEqual(T.PROVIDERS.length, 1, "a dead endpoint wiped the provider list");
    assert.strictEqual(T.SETTINGS.provider, "codex");
  } finally { h.restore(); T.SETTINGS = prevS; }
});

/* ── 49i-49m. The runtime half: no_binary stops being a dead end ────────────
   Before this, `state: "no_binary"` rendered the reason and `actions = ""`.
   Nothing to click, on the one screen that exists to get Codex working: the
   user could not sign in (nothing to sign in to) and could not install
   (nothing offered it). */

/* 49i. The dead end, replaced. */
test("49i. a Mac with no Codex is offered an install, not just a reason", () => {
  const prevP = T.PROVIDERS, prevA = T.S.codexAuth, prevR = T.S.codexRuntime;
  try {
    T.PROVIDERS = [CODEX_ROW_ABSENT];
    T.S.codexRuntime = { installed:false, can_install:true, reason:null };
    T.S.codexAuth = { state:"no_binary", detail:"the `codex` CLI is not on PATH" };
    const h = T.codexAuthHtml();
    assert.ok(/data-codex="install"/.test(h), "no Install control at all: " + h);
    assert.ok(/Install it/.test(h), "the button has no label");
    assert.ok(/not on this Mac yet/.test(h), "nothing explains what is missing");
  } finally { T.PROVIDERS = prevP; T.S.codexAuth = prevA; T.S.codexRuntime = prevR; }
});

/* 49j. WHAT THE BLOCK MUST NOT SAY. Same rule the DeepSeek install block is
   held to: the user is deciding whether to let Sutra put a tool in its own
   folder, and no internal name helps them decide it. */
test("49j. the install block names nothing internal and promises no password", () => {
  const prevP = T.PROVIDERS, prevA = T.S.codexAuth, prevR = T.S.codexRuntime;
  try {
    T.PROVIDERS = [CODEX_ROW_ABSENT];
    T.S.codexRuntime = { installed:false, can_install:true, reason:null };
    T.S.codexAuth = { state:"no_binary", detail:"not on PATH" };
    const h = T.codexInstallHtml(null);
    for (const banned of ["npm", "node_modules", "@openai/codex", "sudo", "PATH",
                          "--prefix", "provider_bins"]) {
      assert.ok(!h.includes(banned), "the block leaks " + banned + ": " + h);
    }
    /* Whitespace-normalised: the copy is a template literal wrapped for the
       source, so every sentence in it spans newlines and indentation. */
    const flat = h.replace(/\s+/g, " ");
    assert.ok(/won.t be asked for a password/.test(flat), "it must say no password");
    assert.ok(/own folder/.test(flat), "it must say where it goes");
    assert.ok(/your own tools are left alone/.test(flat),
      "it must promise not to touch a codex they already have");
  } finally { T.PROVIDERS = prevP; T.S.codexAuth = prevA; T.S.codexRuntime = prevR; }
});

/* 49k. Busy is a state, never a percentage. npm reports nothing parseable, so
   a bar here would be a claim about time this code cannot make. */
test("49k. installing shows a busy state and invents no progress", () => {
  const h = T.codexInstallHtml("install");
  assert.ok(/Installing…/.test(h), "no busy label");
  assert.ok(/aria-busy="true"/.test(h) && /disabled/.test(h), "the button stays clickable");
  assert.ok(!/%/.test(h), "a percentage was invented: " + h);
  assert.ok(/checking that it runs/.test(h),
    "the busy line must say verification is part of it");
});

/* 49l. A machine that cannot install is told why BEFORE clicking -- but the
   button stays, so a stale can_install cannot strand anyone. */
test("49l. the backend's own reason is previewed, and never removes the button", () => {
  const prev = T.S.codexRuntime;
  try {
    T.S.codexRuntime = { installed:false, can_install:false,
                         reason:"npm is not on this Mac … get it from nodejs.org" };
    const h = T.codexInstallHtml(null);
    assert.ok(/nodejs\.org/.test(h), "the reason is not shown");
    assert.ok(/data-codex="install"/.test(h), "the button was removed on a stale flag");
  } finally { T.S.codexRuntime = prev; }
});

/* 49m. A successful install makes the row selectable on the same paint --
   the install's own answer carries the row, exactly like the sign-in's does. */
codexSerial("49m", async () => {
  let posted = null;
  const h = codexStub((url, opts) => {
    if (String(url).indexOf("/cli") >= 0){
      posted = { url:String(url), opts };
      return Promise.resolve({ ok:true, json: () => Promise.resolve({
        ok:true, code:"INSTALLED", message:"the Codex CLI is installed",
        providers:[CODEX_ROW_READY], settings:{ provider:"codex" },
        runtime:{ installed:true, can_install:true, reason:null } }) });
    }
    return Promise.resolve({ ok:true, json: () => Promise.resolve({
      state:"logged_out", providers:[CODEX_ROW_READY],
      settings:{ provider:"codex" } }) });
  });
  try {
    T.PROVIDERS = [CODEX_ROW_ABSENT];
    const r = await T.codexInstall();
    assert.ok(r && r.ok, "the install did not report success");
    assert.ok(/\/api\/providers\/codex\/cli$/.test(posted.url), posted.url);
    assert.strictEqual(posted.opts.method, "POST");
    assert.strictEqual(T.PROVIDERS[0].runnable, true,
      "the CLI landed and the row still cannot be picked");
    assert.strictEqual(T.S.codexBusy, null, "the button is stuck on Installing…");
  } finally { h.restore(); T.S.codexBusy = null; T.S.codexMsg = null; }
});

/* 49n. A refused install still corrects the rows and says why. */
codexSerial("49n", async () => {
  const h = codexStub(url => String(url).indexOf("/cli") >= 0
    ? Promise.resolve({ ok:true, json: () => Promise.resolve({
        ok:false, code:"NO_NPM", message:"npm is not on this Mac",
        providers:[CODEX_ROW_ABSENT],
        runtime:{ installed:false, can_install:false, reason:"no npm" } }) })
    : Promise.resolve({ ok:true, json: () => Promise.resolve({
        state:"no_binary", providers:[CODEX_ROW_ABSENT] }) }));
  try {
    T.PROVIDERS = [CODEX_ROW_ABSENT];
    const r = await T.codexInstall();
    assert.strictEqual(r.ok, false);
    assert.ok(/npm is not on this Mac/.test(T.S.codexMsg), T.S.codexMsg);
    assert.strictEqual(T.S.codexRuntime.can_install, false,
      "the refusal did not correct the runtime state");
    assert.strictEqual(T.S.codexBusy, null);
  } finally { h.restore(); T.S.codexBusy = null; T.S.codexMsg = null; }
});

/* 49o. PROVISION ONLY WHAT IS MISSING. The guard on the post-sign-in chain: a
   Mac that already has Codex must never see an install request. */
codexSerial("49o", async () => {
  let calls = 0;
  const h = codexStub(() => { calls++; return Promise.resolve({ ok:true,
    json: () => Promise.resolve({ state:"chatgpt", providers:[CODEX_ROW_READY] }) }); });
  try {
    T.PROVIDERS = [CODEX_ROW_READY];
    assert.strictEqual(T.codexNeedsInstall(), false);
    assert.strictEqual(await T.codexEnsureRuntime(), null, "an install was attempted");
    assert.strictEqual(calls, 0, "an installed Codex still cost a request");

    T.PROVIDERS = [CODEX_ROW_ABSENT];
    assert.strictEqual(T.codexNeedsInstall(), true);
  } finally { h.restore(); T.S.codexBusy = null; T.S.codexMsg = null; }
});

/* 49p. A page with no Codex row at all asks for nothing. */
test("49p. no codex in the catalogue means no install offer", () => {
  const prev = T.PROVIDERS;
  try {
    T.PROVIDERS = [{ id:"claude", name:"Claude Code", installed:true,
                     configured:true, runnable:true }];
    assert.strictEqual(T.codexNeedsInstall(), false);
    assert.strictEqual(T.codexAuthHtml(), "", "the block rendered without a row");
  } finally { T.PROVIDERS = prev; }
});

/* ── 50. Codex UX pass: tokens, controls, folder ────────────────────────────
   Codex reports per-turn TOKEN COUNTS on turn.completed and nothing else --
   no price, no rate-limit window, no plan allowance. Those counts were already
   arriving on the `done` frame's `quota` and NOTHING in this directory read
   them. Everything below is about showing exactly that and not one claim more. */

const CODEX_TOK_ROW = { id:"codex", name:"OpenAI Codex", installed:true,
                        configured:true, runnable:true, adapter:true,
                        usage_kind:"tokens", reason:null };

test("50a. token counts compact without rounding small exact numbers", () => {
  assert.strictEqual(T.tokShort(0), "0");
  assert.strictEqual(T.tokShort(347), "347", "a small count is a fact, not 0.3k");
  assert.strictEqual(T.tokShort(999), "999");
  assert.strictEqual(T.tokShort(1240), "1.2k");
  assert.strictEqual(T.tokShort(29582), "30k");
  assert.strictEqual(T.tokShort(1500000), "1.5M");
  for (const bad of [null, undefined, "12", NaN, Infinity, -5])
    assert.strictEqual(T.tokShort(bad), null, "junk: " + String(bad));
});

test("50b. the tokens kind renders what codex measured, and no money", () => {
  const prevP = T.PROVIDERS, prevS = T.SETTINGS, prevT = T.S.turnTokens;
  try {
    T.PROVIDERS = [CODEX_TOK_ROW];
    T.SETTINGS = { provider:"codex" };
    /* The exact shape measured off codex-cli 0.153.2's turn.completed. */
    T.S.turnTokens = { s1: { input_tokens:29582, cached_input_tokens:25088,
                             cache_write_input_tokens:0, output_tokens:412,
                             reasoning_output_tokens:128 } };
    const u = T.providerUsage("codex", "s1");
    assert.ok(u, "no usage rendered at all");
    assert.ok(/30k in/.test(u.row) && /412 out/.test(u.row), u.row);
    assert.ok(/last turn/.test(u.row), "it must say WHICH turn: " + u.row);
    assert.ok(/25k cached/.test(u.row), "cached input changes the cost: " + u.row);
    assert.ok(/128 reasoning/.test(u.row), "reasoning tokens are output too");
    /* THE INVARIANT. codex publishes no price and no allowance, so no glyph
       here may suggest either one. */
    assert.ok(!/\$/.test(u.row + u.long + u.short), "a price appeared: " + u.row);
    assert.ok(!/%/.test(u.row + u.long + u.short), "a percentage appeared: " + u.row);
    assert.ok(!/remaining|left|quota|limit/i.test(u.row + u.long),
      "an allowance was implied: " + u.row);
  } finally { T.PROVIDERS = prevP; T.SETTINGS = prevS; T.S.turnTokens = prevT; }
});

test("50c. a zero cached/reasoning count is omitted rather than shown as 0", () => {
  const prevP = T.PROVIDERS, prevT = T.S.turnTokens;
  try {
    T.PROVIDERS = [CODEX_TOK_ROW];
    T.S.turnTokens = { s1: { input_tokens:100, output_tokens:20,
                             cached_input_tokens:0, reasoning_output_tokens:0 } };
    const u = T.providerUsage("codex", "s1");
    assert.strictEqual(u.row, "100 in · 20 out last turn");
  } finally { T.PROVIDERS = prevP; T.S.turnTokens = prevT; }
});

test("50d. before the first reply there is nothing to claim", () => {
  const prevP = T.PROVIDERS, prevT = T.S.turnTokens;
  try {
    T.PROVIDERS = [CODEX_TOK_ROW];
    T.S.turnTokens = {};
    assert.strictEqual(T.providerUsage("codex", "s1"), null,
      "an unfinished pane must report nothing, not zero");
    assert.strictEqual(T.providerUsage("codex"), null,
      "and with no session id there is nothing to look up");
  } finally { T.PROVIDERS = prevP; T.S.turnTokens = prevT; }
});

test("50e. Claude and DeepSeek usage rendering is untouched", () => {
  const prevP = T.PROVIDERS, prevU = T.S.usage, prevD = T.S.deepseekUsage,
        prevT = T.S.turnTokens;
  try {
    /* Tokens present for BOTH sessions -- the other two kinds must ignore them
       entirely rather than start rendering a second provider's fact. */
    T.S.turnTokens = { s1: { input_tokens:100, output_tokens:20 } };
    T.PROVIDERS = [{ id:"claude", name:"Claude Code", usage_kind:"window-percent" }];
    T.S.usage = { available:true, limits:[{ active:true, percent:42 }] };
    assert.strictEqual(T.providerUsage("claude", "s1").row, "42% used");

    T.PROVIDERS = [{ id:"deepseek", name:"DeepSeek", usage_kind:"balance" }];
    T.S.deepseekUsage = { available:true, balances:[{ total_balance:"7.50",
                                                      currency:"USD" }] };
    assert.strictEqual(T.providerUsage("deepseek", "s1").row, "$7.50 balance");
  } finally { T.PROVIDERS = prevP; T.S.usage = prevU;
             T.S.deepseekUsage = prevD; T.S.turnTokens = prevT; }
});

test("50f. a provider with no usage concept still reports none", () => {
  const prev = T.PROVIDERS;
  try {
    T.PROVIDERS = [{ id:"gemini", name:"Gemini CLI", usage_kind:"none" }];
    assert.strictEqual(T.providerUsage("gemini", "s1"), null);
    assert.strictEqual(T.usageKindOf("gemini"), "none");
  } finally { T.PROVIDERS = prev; }
});

/* ── 50g-50j. The two per-turn controls ─────────────────────────────────────
   Both values are codex's OWN enumeration, read out of the CLI's rejection of
   a bad one. The gating is the pre-existing `f(key, html)` in turnOptsHtml, so
   a provider that does not DECLARE a key renders no field for it. */

test("50g. a Codex pane offers Reasoning summary and Verbosity", () => {
  const prev = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.TURN_OPTIONS_BY_PROVIDER = { codex:["reasoning_summary","verbosity"] };
    const h = T.turnOptsHtml("s1", "codex");
    assert.ok(/data-opt="reasoning_summary"/.test(h), "no Reasoning control");
    assert.ok(/data-opt="verbosity"/.test(h), "no Verbosity control");
    /* THE LABEL, not just the attribute. This control sets
       model_reasoning_summary -- how much of its reasoning Codex SHOWS -- and
       it was labelled "Reasoning", which reads as how much it DOES. Codex
       exposes both axes and they share no values (summary:
       auto/concise/detailed/none; effort: low/medium/high/xhigh/max/ultra), so
       "Reasoning ... none" invited "reasoning off" when it only hides the
       summary. The old assertions were on `data-opt`, which is why none of
       them caught the wording. */
    assert.ok(/<span>Reasoning summary<\/span>/.test(h),
      "the label must say which reasoning axis this is: " + h.slice(0, 400));
    assert.ok(!/<span>Reasoning<\/span>/.test(h),
      "the ambiguous label is back");
    assert.ok(/model_reasoning_summary/.test(h),
      "the tooltip must still name the config key it sets");
    /* codex's own variants, and only those. */
    for (const v of ["auto","concise","detailed","none"])
      assert.ok(h.includes(`value="${v}"`), "missing summary variant " + v);
    for (const v of ["low","medium","high"])
      assert.ok(h.includes(`value="${v}"`), "missing verbosity variant " + v);
    /* No Claude control leaks onto a Codex pane. */
    assert.ok(!/data-opt="effort"/.test(h), "Claude's Effort appeared");
    assert.ok(!/data-opt="max_budget_usd"/.test(h), "a $ budget appeared");
  } finally { T.TURN_OPTIONS_BY_PROVIDER = prev; }
});

test("50h. a Claude pane is byte-identical to before the pass", () => {
  const prev = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.TURN_OPTIONS_BY_PROVIDER = { claude:["effort","max_budget_usd",
      "allowed_tools","disallowed_tools","append_system_prompt"] };
    const h = T.turnOptsHtml("s1", "claude");
    assert.ok(/data-opt="effort"/.test(h), "Claude lost its Effort control");
    assert.ok(!/reasoning_summary|verbosity/.test(h),
      "a Codex control reached a Claude pane");
  } finally { T.TURN_OPTIONS_BY_PROVIDER = prev; }
});

test("50i. the boot-window fallback draws no Codex control", () => {
  /* turnOptsFor() answers with TOPT_ALL before /api/providers lands. Adding
     the Codex keys there would draw them on a Claude pane for the first second
     of every launch -- a false-specific claim, which is why they are not in it. */
  const prev = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.TURN_OPTIONS_BY_PROVIDER = {};
    const on = T.turnOptsFor("claude");
    assert.ok(on.has("effort"), "the pre-existing fallback must be intact");
    assert.ok(!on.has("reasoning_summary") && !on.has("verbosity"),
      "a Codex control is in the boot-window fallback");
    assert.ok(!/reasoning_summary|verbosity/.test(T.turnOptsHtml("s1", "claude")));
  } finally { T.TURN_OPTIONS_BY_PROVIDER = prev; }
});

test("50j. a DeepSeek pane still offers no per-turn controls at all", () => {
  const prev = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.TURN_OPTIONS_BY_PROVIDER = { deepseek:[] };
    assert.strictEqual(T.turnOptsFor("deepseek").size, 0);
  } finally { T.TURN_OPTIONS_BY_PROVIDER = prev; }
});

/* ── 50k. The folder row ────────────────────────────────────────────────────
   "sutra-ui · deepseek-provider" on a CODEX pane read as provider context. It
   was a folder name and a GIT BRANCH, both correct. `on` is what stops the
   middle field being read as anything but a branch. */

test("50k. the branch is labelled as a branch", () => {
  const prevSettings = T.SETTINGS, prevProv = T.PROVIDERS,
        prevMenu = T.S.paneMenu, prevRepo = T.S.repo;
  try {
    T.PROVIDERS = [CODEX_TOK_ROW];
    T.SETTINGS = { provider:"codex", permission_mode:"plan", workdir:"/w" };
    const s = { id:"s1", title:"t", real:true };
    T.S.paneMenu = "s1";
    /* sessCwd() resolves S.cwd -> S.sessions -> SETTINGS.workdir, never the
       object passed in, so the per-session override is what a real pane with
       its own folder uses. */
    T.S.cwd = Object.assign({}, T.S.cwd, { s1: "/Users/x/sutra" });
    T.S.repo = { s1: { available:true, branch:"deepseek-provider",
                       diff:{ files:0 } } };
    const h = T.paneMenuHtml(s);
    assert.ok(/on deepseek-provider/.test(h),
      "the branch is still unlabelled, so it reads as provider context: " + h.slice(0, 300));
    assert.ok(/sutra/.test(h), "the folder itself must still be shown");
    /* The absolute path the provider actually receives is one hover away. */
    assert.ok(/title="[^"]*\/Users\/x\/sutra/.test(h),
      "the full working directory is not reachable from the row");
  } finally { T.SETTINGS = prevSettings; T.PROVIDERS = prevProv;
             T.S.paneMenu = prevMenu; T.S.repo = prevRepo;
             delete T.S.cwd.s1; }
});

test("50l. the Tokens row is titled for what it holds, not 'Usage'", () => {
  const prevSettings = T.SETTINGS, prevProv = T.PROVIDERS,
        prevMenu = T.S.paneMenu, prevT = T.S.turnTokens;
  try {
    T.PROVIDERS = [CODEX_TOK_ROW];
    T.SETTINGS = { provider:"codex", permission_mode:"plan", workdir:"/w" };
    T.S.paneMenu = "s1";
    T.S.turnTokens = { s1: { input_tokens:1200, output_tokens:80 } };
    const h = T.paneMenuHtml({ id:"s1", title:"t", real:true, cwd:"/w" });
    assert.ok(/>Tokens</.test(h), "'Usage' next to a number reads as spend: " + h.slice(0,400));
    assert.ok(/1\.2k in/.test(h), "the measured counts are not rendered");
  } finally { T.SETTINGS = prevSettings; T.PROVIDERS = prevProv;
              T.S.paneMenu = prevMenu; T.S.turnTokens = prevT; }
});

/* ── 51. Codex Reasoning effort ──────────────────────────────────────────────
   The OTHER axis from Reasoning summary: effort is how much reasoning codex
   DOES, summary is how much it SHOWS. They share no values.

   It waited for model/list because `-c model_reasoning_effort` ACCEPTS an
   unknown value without complaint (measured: "__bogus__" sailed through), so
   before there was an enumeration any list would have been guesses. The
   enumeration is PER MODEL and the sets genuinely differ, which is why every
   test below drives it off MODELS_BY_PROVIDER rather than a constant. */

const CODEX_MODELS_FIXTURE = [
  { id:"", name:"CLI default", note:"whatever `codex` is configured to use" },
  { id:"m-alpha", name:"Alpha", note:"a", default:true,
    efforts:["low","medium","high","xhigh","max","ultra"] },
  { id:"m-beta", name:"Beta", note:"b", default:false,
    efforts:["low","medium","high","xhigh"] },
];

function withCodexModels(models, fn){
  const prevM = T.MODELS_BY_PROVIDER, prevT = T.TURN_OPTIONS_BY_PROVIDER,
        prevSel = T.S.model, prevOpts = T.S.turnOpts;
  try {
    T.MODELS_BY_PROVIDER = { codex: models };
    T.TURN_OPTIONS_BY_PROVIDER = {
      codex:["reasoning_summary","verbosity","reasoning_effort"] };
    T.S.model = {}; T.S.turnOpts = {};
    return fn();
  } finally { T.MODELS_BY_PROVIDER = prevM; T.TURN_OPTIONS_BY_PROVIDER = prevT;
              T.S.model = prevSel; T.S.turnOpts = prevOpts; }
}

const effortOpts = h => {
  const at = h.indexOf('data-opt="reasoning_effort"');
  if (at < 0) return null;
  const seg = h.slice(at, h.indexOf("</select>", at));
  return [...seg.matchAll(/<option value="([^"]*)"/g)].map(m => m[1]);
};

test("51a. the options are the SELECTED model's supportedReasoningEfforts", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    assert.deepStrictEqual(effortOpts(T.turnOptsHtml("s1", "codex", "m-alpha")),
      ["", "low", "medium", "high", "xhigh", "max", "ultra"]);
  });
});

test("51b. a different model exposes a different set", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    /* beta has no `max` and no `ultra`. A fixed union would offer them and the
       turn would silently run at something else. */
    const beta = effortOpts(T.turnOptsHtml("s1", "codex", "m-beta"));
    assert.deepStrictEqual(beta, ["", "low", "medium", "high", "xhigh"]);
    assert.ok(!beta.includes("ultra"), "beta was offered alpha's ultra");
    assert.ok(!beta.includes("max"), "beta was offered alpha's max");
  });
});

test("51c. changing the selected model changes the options", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    const before = effortOpts(T.turnOptsHtml("s1", "codex", "m-alpha"));
    T.S.model = { s1: "m-beta" };                 /* what the picker's onchange does */
    const after = effortOpts(T.turnOptsHtml("s1", "codex",
                                            T.paneModelFor({ id:"s1" }, "codex")));
    assert.ok(before.includes("ultra"), "alpha should have offered ultra");
    assert.ok(!after.includes("ultra"), "the list did not follow the model change");
  });
});

test("51d. CLI default offers the default model's efforts", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    /* "" resolves to whatever codex marked isDefault -- alpha here -- which is
       the same resolution providers.codex_efforts_for(None) makes, so the
       control cannot offer something the validator would drop. */
    assert.deepStrictEqual(effortOpts(T.turnOptsHtml("s1", "codex", "")),
      ["", "low", "medium", "high", "xhigh", "max", "ultra"]);
  });
});

test("51e. default is always present and always first", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    const h = T.turnOptsHtml("s1", "codex", "m-beta");
    assert.strictEqual(effortOpts(h)[0], "", "default must be the first option");
    assert.ok(/<option value="" [^>]*>default<\/option>|<option value="">default</.test(
      h.replace(/\s+/g, " ")) || /value=""/.test(h), "default is not labelled");
  });
});

test("51f. no discovery -> the control offers default alone", () => {
  withCodexModels([{ id:"", name:"CLI default", note:"n" }], () => {
    assert.deepStrictEqual(effortOpts(T.turnOptsHtml("s1", "codex", "")), [""]);
  });
  withCodexModels([], () => {
    assert.deepStrictEqual(effortOpts(T.turnOptsHtml("s1", "codex", "")), [""]);
  });
});

test("51g. an unknown model degrades to default alone", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    assert.deepStrictEqual(effortOpts(T.turnOptsHtml("s1", "codex", "not-a-model")),
      [""]);
  });
});

test("51h. Reasoning summary is completely unchanged", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    const h = T.turnOptsHtml("s1", "codex", "m-alpha");
    assert.ok(/<span>Reasoning summary<\/span>/.test(h), "summary label moved");
    assert.ok(/data-opt="reasoning_summary"/.test(h), "summary control gone");
    for (const v of ["auto","concise","detailed","none"])
      assert.ok(h.includes(`value="${v}"`), "summary lost " + v);
    /* the two are separate controls, not one renamed */
    assert.ok(/data-opt="reasoning_effort"/.test(h), "effort control missing");
    assert.notStrictEqual(h.indexOf('data-opt="reasoning_summary"'),
                          h.indexOf('data-opt="reasoning_effort"'));
  });
});

test("51i. Verbosity is completely unchanged", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    const h = T.turnOptsHtml("s1", "codex", "m-alpha");
    assert.ok(/data-opt="verbosity"/.test(h), "verbosity control gone");
    assert.ok(/<span>Verbosity<\/span>/.test(h), "verbosity label moved");
    for (const v of ["low","medium","high"])
      assert.ok(h.includes(`value="${v}"`), "verbosity lost " + v);
  });
});

test("51j. no Codex control reaches a Claude or DeepSeek pane", () => {
  withCodexModels(CODEX_MODELS_FIXTURE, () => {
    T.TURN_OPTIONS_BY_PROVIDER = {
      claude:["effort","max_budget_usd","allowed_tools","disallowed_tools",
              "append_system_prompt"], deepseek:[] };
    const claude = T.turnOptsHtml("s1", "claude", "");
    assert.ok(!/reasoning_effort|reasoning_summary|data-opt="verbosity"/.test(claude),
      "a Codex control reached a Claude pane");
    assert.ok(/data-opt="effort"/.test(claude), "Claude lost its own Effort control");
    assert.strictEqual(T.turnOptsFor("deepseek").size, 0);
  });
});

test("51k. the boot-window fallback still draws no Codex control", () => {
  const prev = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.TURN_OPTIONS_BY_PROVIDER = {};
    const on = T.turnOptsFor("claude");
    assert.ok(!on.has("reasoning_effort"), "effort is in the boot fallback");
    assert.ok(on.has("effort"), "the pre-existing fallback must be intact");
  } finally { T.TURN_OPTIONS_BY_PROVIDER = prev; }
});

/* ── 52. Codex global plan usage ─────────────────────────────────────────────
   `account/rateLimits/read` renders in the SAME two global places Claude's plan
   usage does -- the rail badge and the footer telemetry -- plus the Usage screen
   and the composer popover.

   THE ASSUMPTION THIS FEATURE ALMOST SHIPPED ON: "5-hour and weekly windows".
   The measured account is planType "go" and returns ONE 30-day window with no
   `secondary`. So no test here hardcodes a duration pair; they pin the
   DERIVATION. */

const CODEX_TOK_PROV = [{ id:"codex", name:"OpenAI Codex", usage_kind:"tokens" }];

function withCodexPlan(plan, fn){
  const pv = T.PROVIDERS, st = T.SETTINGS, pl = T.S.codexPlan,
        pe = T.S.codexPlanError, tt = T.S.turnTokens;
  try {
    T.PROVIDERS = CODEX_TOK_PROV;
    T.SETTINGS = { provider:"codex" };
    T.S.codexPlan = plan; T.S.codexPlanError = null; T.S.turnTokens = {};
    return fn();
  } finally { T.PROVIDERS = pv; T.SETTINGS = st; T.S.codexPlan = pl;
             T.S.codexPlanError = pe; T.S.turnTokens = tt; }
}

test("52a. window labels are DERIVED from windowDurationMins", () => {
  /* 5-hour and weekly fall out of the arithmetic rather than being listed --
     which is why the account that returns 43200 is labelled correctly too. */
  assert.strictEqual(T.codexWindowLabel(300), "5-hour");
  assert.strictEqual(T.codexWindowLabel(10080), "weekly");
  assert.strictEqual(T.codexWindowLabel(1440), "daily");
  assert.strictEqual(T.codexWindowLabel(43200), "30-day");
  assert.strictEqual(T.codexWindowLabel(60), "1-hour");
  assert.strictEqual(T.codexWindowLabel(45), "45-minute");
  for (const bad of [null, undefined, 0, -5, NaN, "300"])
    assert.strictEqual(T.codexWindowLabel(bad), "usage window", String(bad));
});

test("52b. the measured one-window account renders one row", () => {
  const plan = { plan_type:"go", limit_id:"codex", credits:null, reset_credits:0,
    windows:[{ key:"primary", used_percent:5, duration_mins:43200,
               resets_at: Math.floor(Date.now()/1000) + 86400 }] };
  withCodexPlan(plan, () => {
    const rows = T.codexPlanRows(plan);
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].label, "30-day");
    assert.strictEqual(rows[0].percent, 5);
    assert.strictEqual(rows[0].active, true, "the only window is the active one");
  });
});

test("52c. multiple windows all render, and the fullest is active", () => {
  const plan = { windows:[
    { key:"primary", used_percent:12, duration_mins:300, resets_at:111 },
    { key:"secondary", used_percent:44, duration_mins:10080, resets_at:222 }] };
  const rows = T.codexPlanRows(plan);
  assert.deepStrictEqual(rows.map(r => r.label), ["5-hour", "weekly"]);
  assert.deepStrictEqual(rows.map(r => r.active), [false, true]);
});

test("52d. a missing secondary window is a normal answer", () => {
  const rows = T.codexPlanRows({ windows:[
    { key:"primary", used_percent:3, duration_mins:300, resets_at:0 }] });
  assert.strictEqual(rows.length, 1);
  assert.strictEqual(rows[0].resets_epoch, 0, "no reset is not a fake reset");
});

test("52e. no plan -> no rows and no global figure", () => {
  /* LENGTH, not deepStrictEqual: the array is built inside the vm realm whose
     Object.prototype is not this file's, and deepStrictEqual compares
     prototypes -- the same trap 48i records for readDeclarations. */
  for (const p of [null, undefined, {}, { windows:[] }, { windows:"x" }])
    assert.strictEqual(T.codexPlanRows(p).length, 0, JSON.stringify(p));
  withCodexPlan(null, () => {
    assert.strictEqual(T.providerUsage("codex"), null,
      "the global indicator must be absent, not zero");
  });
});

test("52f. the GLOBAL surfaces show the plan; a PANE still shows its tokens", () => {
  const plan = { windows:[{ key:"primary", used_percent:44,
                            duration_mins:10080, resets_at:0 }] };
  withCodexPlan(plan, () => {
    /* no sid = the app asking -> plan */
    const g = T.providerUsage("codex");
    assert.strictEqual(g.short, 44);
    assert.ok(/44% of the weekly limit/.test(g.long), g.long);
    /* sid = a pane asking -> that pane's last turn, unchanged */
    T.S.turnTokens = { s1: { input_tokens:1200, output_tokens:80 } };
    const pane = T.providerUsage("codex", "s1");
    assert.ok(/1\.2k in/.test(pane.row) && /80 out/.test(pane.row), pane.row);
    assert.ok(!/%/.test(pane.row), "the pane row must not become a percentage");
  });
});

test("52g. the plan body draws every window through Claude's renderer", () => {
  const plan = { plan_type:"plus", credits:null, reset_credits:0, windows:[
    { key:"primary", used_percent:12, duration_mins:300, resets_at:0 },
    { key:"secondary", used_percent:44, duration_mins:10080, resets_at:0 }] };
  withCodexPlan(plan, () => {
    const h = T.codexPlanBodyHtml();
    assert.ok(/5-hour/.test(h) && /weekly/.test(h), "both windows must render");
    assert.ok(/class="ubar"/.test(h), "it must reuse the shared bar markup");
    assert.ok(!/\$/.test(h), "codex publishes no prices: " + h);
  });
});

test("52h. credits render only when OpenAI reports them", () => {
  const base = { windows:[{ key:"primary", used_percent:5, duration_mins:300,
                            resets_at:0 }] };
  /* null credits -> nothing. NOT "0", which would read as exhausted. */
  withCodexPlan(Object.assign({}, base, { credits:null }), () => {
    const h = T.codexPlanBodyHtml();
    assert.ok(!/Credits/.test(h), "an absent balance was rendered: " + h);
    assert.ok(!/\b0\b(?![-\d])/.test(h.replace(/\d+%/g, "")), "a zero appeared");
  });
  withCodexPlan(Object.assign({}, base,
      { credits:{ unlimited:false, balance:"12.50", has_credits:true } }), () => {
    assert.ok(/Credits/.test(T.codexPlanBodyHtml()));
    assert.ok(/12\.50/.test(T.codexPlanBodyHtml()));
  });
  withCodexPlan(Object.assign({}, base,
      { credits:{ unlimited:true, balance:null, has_credits:true } }), () => {
    assert.ok(/unlimited/.test(T.codexPlanBodyHtml()));
  });
});

test("52i. a failed read says so and never reads as a zeroed allowance", () => {
  const pv = T.PROVIDERS, st = T.SETTINGS, pl = T.S.codexPlan, pe = T.S.codexPlanError;
  try {
    T.PROVIDERS = CODEX_TOK_PROV; T.SETTINGS = { provider:"codex" };
    T.S.codexPlan = null; T.S.codexPlanError = "the endpoint did not answer";
    const h = T.codexPlanBodyHtml();
    assert.ok(/did not answer/.test(h), h);
    assert.ok(!/0%/.test(h), "a failure rendered as 0%");
    /* Whitespace-normalised: the copy is a wrapped template literal, so the
       sentence spans newlines and indentation in the source. */
    assert.ok(/no model turn is spent/i.test(h.replace(/\s+/g, " ")),
      "it must say the read costs nothing");
  } finally { T.PROVIDERS = pv; T.SETTINGS = st; T.S.codexPlan = pl;
              T.S.codexPlanError = pe; }
});

test("52j. API-key mode shows no ChatGPT plan usage", () => {
  withCodexPlan(null, () => {
    const h = T.codexPlanBodyHtml();
    assert.ok(/ChatGPT sign-in/.test(h), "it must say which credential has a plan");
    assert.ok(/API key/.test(h), "and that a key is billed elsewhere");
    assert.ok(!/%/.test(h), "no percentage may appear without a plan: " + h);
    assert.strictEqual(T.providerUsage("codex"), null);
  });
});

test("52k. a credential change CLEARS the plan rather than leaving it stale", () => {
  const pl = T.S.codexPlan, pv = T.PROVIDERS;
  try {
    T.S.codexPlan = { windows:[{ key:"primary", used_percent:5,
                                 duration_mins:300, resets_at:0 }] };
    T.codexApplyState({ state:"api_key" });
    assert.strictEqual(T.S.codexPlan, null, "an API key kept a ChatGPT plan on screen");
    T.S.codexPlan = { windows:[] };
    T.codexApplyState({ state:"logged_out" });
    assert.strictEqual(T.S.codexPlan, null, "a sign-out kept the plan");
    /* still chatgpt -> untouched; populating is loadUsage's job, not this one */
    T.S.codexPlan = { windows:[{ key:"primary", used_percent:9,
                                 duration_mins:300, resets_at:0 }] };
    T.codexApplyState({ state:"chatgpt" });
    assert.ok(T.S.codexPlan, "a chatgpt answer must not clear the plan");
  } finally { T.S.codexPlan = pl; T.PROVIDERS = pv; }
});

test("52l. Claude and DeepSeek global usage are untouched", () => {
  const pv = T.PROVIDERS, st = T.SETTINGS, u = T.S.usage, d = T.S.deepseekUsage,
        pl = T.S.codexPlan;
  try {
    /* a Codex plan present must not leak into either */
    T.S.codexPlan = { windows:[{ key:"primary", used_percent:5,
                                 duration_mins:300, resets_at:0 }] };
    T.PROVIDERS = [{ id:"claude", name:"Claude Code", usage_kind:"window-percent" }];
    T.S.usage = { available:true, limits:[{ active:true, percent:42 }] };
    assert.strictEqual(T.providerUsage("claude").row, "42% used");
    T.PROVIDERS = [{ id:"deepseek", name:"DeepSeek", usage_kind:"balance" }];
    T.S.deepseekUsage = { available:true,
                          balances:[{ total_balance:"7.50", currency:"USD" }] };
    assert.strictEqual(T.providerUsage("deepseek").row, "$7.50 balance");
  } finally { T.PROVIDERS = pv; T.SETTINGS = st; T.S.usage = u;
              T.S.deepseekUsage = d; T.S.codexPlan = pl; }
});

/* ── 53. the model map arrives on the Codex answer ───────────────────────────
   THE CLIENT HALF of the picker bug (2026-09-09). MODELS_BY_PROVIDER is
   written exactly ONCE, by loadRuntime() inside boot(), and Codex's list is
   DISCOVERED -- warmed only by GET /providers/codex/auth, which cannot run
   before boot because the probe waits for the Settings screen. So boot always
   stored the pre-discovery list and nothing ever re-read it: "CLI default"
   alone, for the life of the window, on a machine where model/list had just
   answered. A reload appeared to fix it because a reload is loadRuntime again.

   49f pins the SETTINGS/PROVIDERS half of codexApplyState and passed for the
   whole life of this bug -- nothing looked at the model map. These do.

   The wire half is pinned in test_codex_readiness.py. */

/* Ids that exist in no catalogue, so a hardcoded list cannot satisfy these. */
const DISCOVERED_MAP = {
  codex: [
    { id:"", name:"CLI default", note:"whatever `codex` is configured to use" },
    { id:"m-disc-one", name:"Disc One", note:"a", default:true,
      efforts:["low","medium","high"] },
    { id:"m-disc-two", name:"Disc Two", note:"b", default:false,
      efforts:["low","medium"] },
  ],
  claude: [{ id:"", name:"CLI default" }, { id:"opus", name:"Opus" }],
};

function withModelMap(initial, fn){
  const prevM = T.MODELS_BY_PROVIDER, prevP = T.PROVIDERS, prevS = T.SETTINGS,
        prevSel = T.S.model, prevOpts = T.S.turnOpts, prevT = T.TURN_OPTIONS_BY_PROVIDER;
  try {
    T.MODELS_BY_PROVIDER = initial;
    T.S.model = {}; T.S.turnOpts = {};
    return fn();
  } finally { T.MODELS_BY_PROVIDER = prevM; T.PROVIDERS = prevP; T.SETTINGS = prevS;
             T.S.model = prevSel; T.S.turnOpts = prevOpts;
             T.TURN_OPTIONS_BY_PROVIDER = prevT; }
}

test("53a. a Codex answer carrying models updates MODELS_BY_PROVIDER", () => {
  withModelMap({}, () => {
    assert.strictEqual(
      T.codexApplyState({ state:"chatgpt", models_by_provider:DISCOVERED_MAP }),
      true, "the answer applied nothing");
    assert.deepStrictEqual(T.MODELS_BY_PROVIDER, DISCOVERED_MAP,
      "the discovered map did not land");
  });
});

test("53b. the dropdown then renders the discovered models, not the fallback", () => {
  withModelMap({}, () => {
    /* the boot-window state the bug froze the panel in */
    let opts = optionsIn(paneMenuWith(T.MODELS_BY_PROVIDER, "codex",
                                      { provider:"codex", workdir:"/w" }));
    assert.deepStrictEqual(opts.map(o => o.id), [""],
      "the fixture is not reproducing the pre-fix state: " + JSON.stringify(opts));
    /* the AI Provider screen's answer lands */
    T.codexApplyState({ state:"chatgpt", models_by_provider:DISCOVERED_MAP });
    opts = optionsIn(paneMenuWith(T.MODELS_BY_PROVIDER, "codex",
                                  { provider:"codex", workdir:"/w" }));
    assert.deepStrictEqual(opts.map(o => o.id), ["", "m-disc-one", "m-disc-two"],
      "the picker still has nothing to select: " + JSON.stringify(opts));
  });
});

test("53c. CLI default survives as the first option", () => {
  withModelMap({}, () => {
    T.codexApplyState({ state:"chatgpt", models_by_provider:DISCOVERED_MAP });
    const opts = optionsIn(paneMenuWith(T.MODELS_BY_PROVIDER, "codex",
                                        { provider:"codex", workdir:"/w" }));
    assert.strictEqual(opts[0].id, "", "CLI default is no longer first");
  });
});

test("53d. an API-key answer lands its models exactly like a ChatGPT one", () => {
  /* The picker was stuck on "CLI default" under BOTH credentials, and the two
     are scoped by different things -- so neither may be assumed to carry the
     other's list, and neither may be the only one that works. */
  for (const state of ["chatgpt", "api_key"]) {
    withModelMap({}, () => {
      T.codexApplyState({ state, models_by_provider:DISCOVERED_MAP });
      assert.deepStrictEqual(T.MODELS_BY_PROVIDER.codex.map(m => m.id),
        ["", "m-disc-one", "m-disc-two"], "state=" + state);
    });
  }
});

test("53e. AN OLDER BACKEND'S OMISSION MUST NOT WIPE A LOADED MAP", () => {
  /* `{}` is the panel's sentinel for "not fetched yet" (06-render's mloaded
     reads Object.keys().length), so a downgrade here does not merely lose the
     new list -- it puts a LOADED picker back into its boot-window fallback.
     Omission is not an answer of empty, the same rule PROVIDERS follows. */
  for (const bad of [undefined, null, {}, [], "many", 3, true]) {
    withModelMap(DISCOVERED_MAP, () => {
      T.codexApplyState({ state:"chatgpt", models_by_provider:bad });
      assert.deepStrictEqual(T.MODELS_BY_PROVIDER, DISCOVERED_MAP,
        "models_by_provider=" + JSON.stringify(bad) + " wiped the map");
    });
  }
  /* and the omission alone must not be reported as an applied change */
  withModelMap(DISCOVERED_MAP, () => {
    assert.strictEqual(T.codexApplyState({ state:"chatgpt" }), false,
      "an answer carrying nothing claimed to have applied something");
  });
});

test("53f. the other providers' lists are not touched by a Codex answer", () => {
  withModelMap({ claude:[{ id:"", name:"CLI default" }, { id:"opus", name:"Opus" }] },
    () => {
      T.codexApplyState({ state:"chatgpt", models_by_provider:DISCOVERED_MAP });
      assert.deepStrictEqual(T.MODELS_BY_PROVIDER.claude.map(m => m.id),
        ["", "opus"], "Claude's list changed shape");
      assert.ok(!("gemini" in T.MODELS_BY_PROVIDER),
        "a provider with no models gained a picker");
    });
});

test("53g. the Reasoning-effort options follow the newly landed model", () => {
  /* The efforts are PER MODEL and ride on the same rows, so the control has to
     move with the map -- otherwise it keeps offering the CLI-default set for a
     model that was only selectable because this answer arrived. */
  withModelMap({}, () => {
    T.codexApplyState({ state:"chatgpt", models_by_provider:DISCOVERED_MAP });
    T.TURN_OPTIONS_BY_PROVIDER = {
      codex:["reasoning_summary","verbosity","reasoning_effort"] };
    assert.deepStrictEqual(T.codexEffortsFor("codex", "m-disc-one"),
      ["low","medium","high"]);
    assert.deepStrictEqual(T.codexEffortsFor("codex", "m-disc-two"),
      ["low","medium"]);
    /* falsy model = the CLI default row, which resolves to the isDefault one */
    assert.deepStrictEqual(T.codexEffortsFor("codex", ""),
      ["low","medium","high"], "CLI default did not resolve to the default model");
    /* and through the rendered control, which is what an operator sees */
    T.S.model = { s1:"m-disc-two" };
    assert.deepStrictEqual(effortOpts(T.turnOptsHtml("s1", "codex", "m-disc-two")),
      ["", "low", "medium"], "the control is not describing the selected model");
  });
});

test("53h. selecting one of the landed models is what gets sent", () => {
  /* The handler is per-session and unpersisted; what matters here is that an id
     that only exists because this answer arrived is the id the frame carries.
     The `-m` half is server-side and pinned in test_codex_readiness.py. */
  withModelMap({}, () => {
    T.codexApplyState({ state:"chatgpt", models_by_provider:DISCOVERED_MAP });
    const chosen = T.MODELS_BY_PROVIDER.codex[1].id;
    /* PANE_S.id, not a literal: paneMenuWith renders THAT pane, and a hardcoded
       id silently asserts about a session the markup was never built for. */
    T.S.model = { [PANE_S.id]: chosen };
    assert.strictEqual(T.paneModelFor(PANE_S, "codex"), chosen);
    /* and it renders as the selected option rather than silently reverting */
    T.SETTINGS = { provider:"codex", workdir:"/w" };
    const h = paneMenuWith(T.MODELS_BY_PROVIDER, "codex",
                           { provider:"codex", workdir:"/w" });
    const sel = optionsIn(h).find(o => o.id === chosen);
    assert.ok(sel && / selected/.test(sel.attrs),
      "the chosen model is not the selected option: " + JSON.stringify(optionsIn(h)));
  });
});

/* ══════════════════════════════════════════════════════════════════════════
   54. Clicking a chat opens it in a pane — on the Chats destination, after
       any visit to Agents

   THE BUG (owner, 2026-09-10): "clicking a chat in the Chats list does not
   open it. The whole area to the right of the list stays empty." Reading the
   open path proves nothing, because the open path is correct: the row's
   [data-open] handler runs, markRead/pushPane/ensureTranscript all fire, and
   S.openPanes ends up holding the chat. It is render() that then paints
   nothing, and only after Agents has been visited once.

   WHY A SECOND MOUNT. The suite's main sandbox hands out a FRESH element for
   every getElementById, so the delegated #app click listener is registered on
   a node nobody can reach and #panes.innerHTML is written to a throwaway. This
   mounts the same concatenated source against a DOM that keeps its elements,
   so the test can dispatch a real click at the real listener and then read the
   real #panes markup — driving the bug rather than describing it.
   ══════════════════════════════════════════════════════════════════════════ */
function mountPanel(){
  const byId = {};
  const camel = s => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
  function matchSel(n, sel){
    let m = /^\[data-([a-z0-9-]+)\]$/i.exec(sel);
    if (m) return n.dataset[camel(m[1])] !== undefined;
    m = /^\.([a-z0-9_-]+)$/i.exec(sel);
    if (m) return n.classList.contains(m[1]);
    m = /^#([a-z0-9_-]+)$/i.exec(sel);
    if (m) return n.id === m[1];
    return false;    /* nothing else is dispatched on in this test */
  }
  function mk(tag, id){
    const n = {
      tagName: (tag || "div").toUpperCase(), id: id || "", innerHTML: "", textContent: "",
      value: "", disabled: false, hidden: false, dataset: {}, style: {},
      _attrs: {}, _parent: null, _listeners: {},
      classList: { _s: new Set(),
        add(...c){ c.forEach(x => this._s.add(x)); },
        remove(...c){ c.forEach(x => this._s.delete(x)); },
        contains(c){ return this._s.has(c); },
        toggle(c, f){ if (f === undefined){ this._s.has(c) ? this._s.delete(c) : this._s.add(c); return this._s.has(c); }
                      f ? this._s.add(c) : this._s.delete(c); return !!f; } },
      setAttribute(k, v){ this._attrs[k] = String(v); },
      getAttribute(k){ return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; },
      hasAttribute(k){ return Object.prototype.hasOwnProperty.call(this._attrs, k); },
      removeAttribute(k){ delete this._attrs[k]; },
      addEventListener(t, fn){ (this._listeners[t] = this._listeners[t] || []).push(fn); },
      removeEventListener(){}, appendChild(c){ c._parent = this; return c; }, remove(){},
      focus(){ doc.activeElement = this; }, blur(){}, setSelectionRange(){}, scrollTo(){},
      contains(){ return false; },
      getBoundingClientRect(){ return { width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 }; },
      closest(sel){ let p = this; while (p){ if (matchSel(p, sel)) return p; p = p._parent; } return null; },
      querySelector(){ return null; }, querySelectorAll(){ return []; },
    };
    n.content = n;
    return n;
  }
  const doc = {
    activeElement: null, documentElement: mk("html"),
    createElement: t => mk(t),
    /* THE WHOLE POINT: one element per id, for the life of the mount. */
    getElementById(id){ return byId[id] || (byId[id] = mk("div", id)); },
    querySelector(){ return mk("div"); }, querySelectorAll(){ return []; },
    _listeners: {},
    addEventListener(t, fn){ (this._listeners[t] = this._listeners[t] || []).push(fn); },
  };
  doc.body = doc.getElementById("__body");
  const box = {
    console: { log(){}, warn(){}, error(){} },
    document: doc,
    themeBtn: mk("button"), navOrg: mk("div"), navChange: mk("div"), navRuntime: mk("div"),
    localStorage: { _m: {}, getItem(k){ return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; },
                    setItem(k, v){ this._m[k] = String(v); }, removeItem(k){ delete this._m[k]; } },
    sessionStorage: { _m: {}, getItem(k){ return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; },
                      setItem(k, v){ this._m[k] = String(v); }, removeItem(k){ delete this._m[k]; } },
    matchMedia: () => ({ matches: false, addEventListener(){} }),
    location: { protocol: "http:", host: "127.0.0.1:7000" },
    innerWidth: 1440,
    navigator: { clipboard: { writeText: () => Promise.resolve() } },
    WebSocket: function WebSocketStub(){ this.readyState = 0; this.send = () => {}; this.close = () => {}; },
    setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
    requestAnimationFrame: () => 0, cancelAnimationFrame: () => {},
    Date, Math, JSON, Set, Map, Promise, Object, Array, String, Number, Boolean, RegExp, Error,
    fetch: () => new Promise(() => {}),      /* never settles, as in the main sandbox */
  };
  box.window = box; box.globalThis = box;
  box.WebSocket.CONNECTING = 0; box.WebSocket.OPEN = 1;
  vm.createContext(box);
  new vm.Script(source + `;globalThis.__P = { S, render, goDest, openScreen, startNewChat };`,
                { filename: "panel.html#openpane" }).runInContext(box);
  const P = box.__P;
  const app = doc.getElementById("app"), panes = doc.getElementById("panes");
  return {
    P, doc, panes,
    /* A real row button under a real .srow, dispatched at the real delegated
       listener -- the same object the browser hands it. */
    clickRow(sid){
      const li = mk("li"); li.classList.add("srow"); li.dataset.sid = sid;
      const btn = mk("button"); btn.classList.add("rowopen"); btn.dataset.open = sid; btn._parent = li;
      (app._listeners.click || []).forEach(fn => fn({ target: btn, stopPropagation(){}, preventDefault(){} }));
      return btn;
    },
    seed(){
      P.S.sessions = [
        { id: "s-dust", title: "Dust spaces and connections", created_ms: 1, updated_ms: 2,
          turns: [], local: true, loadState: "live" },
      ];
      P.S.openPanes = [];
    },
  };
}

test("54a. the delegated listener is reachable and a row click opens the pane on Chats", () => {
  const m = mountPanel();
  m.seed();
  m.P.goDest("chats");
  m.clickRow("s-dust");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(m.P.S.openPanes)), ["s-dust"],
    "the [data-open] branch must reach pushPane");
  assert.ok(/data-sess="s-dust"/.test(m.panes.innerHTML),
    "the clicked chat must paint a pane; #panes was: " + JSON.stringify(m.panes.innerHTML.slice(0, 120)));
});

test("54b. THE BUG: after one visit to Agents, a chat click still opens on Chats", () => {
  /* The owner's exact route: Chats -> Agents -> Chats -> click a chat.
     goDest("chats") sets S.ui.browseClosed and NOTHING resets S.screen, so
     S.screen was still "agents" and the solo-screen rule blanked every pane on
     a destination Agents is not even showing on. Before the fix this asserted
     an empty #panes -- not a mispainted one, an EMPTY string. */
  const m = mountPanel();
  m.seed();
  m.P.goDest("chats");
  m.P.goDest("agents");
  m.P.goDest("chats");
  m.clickRow("s-dust");
  assert.strictEqual(m.P.S.screen, "agents",
    "precondition: S.screen is deliberately left on agents -- that is what makes this a trap");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(m.P.S.openPanes)), ["s-dust"],
    "the click path itself was never the fault");
  assert.ok(/data-sess="s-dust"/.test(m.panes.innerHTML),
    "clicking a chat on the Chats destination must open it even after Agents has been visited; "
    + "#panes was: " + JSON.stringify(m.panes.innerHTML.slice(0, 120)));
});

test("54c. Agents still opens ALONE — the rule the fix must not undo", () => {
  const m = mountPanel();
  m.seed();
  m.P.goDest("chats");
  m.clickRow("s-dust");
  assert.ok(/data-sess="s-dust"/.test(m.panes.innerHTML), "open it first");
  m.P.goDest("agents");
  assert.ok(!/data-sess="s-dust"/.test(m.panes.innerHTML),
    "no session pane may paint beside the Agents screen");
  assert.deepStrictEqual(JSON.parse(JSON.stringify(m.P.S.openPanes)), ["s-dust"],
    "and the pane is still OPEN -- Agents decides what paints, never what is open");
  m.P.goDest("chats");
  assert.ok(/data-sess="s-dust"/.test(m.panes.innerHTML),
    "leaving Agents brings the pane back exactly as it was");
});
