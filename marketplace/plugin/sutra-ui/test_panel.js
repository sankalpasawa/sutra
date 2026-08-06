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

/* ── 1. extract the script exactly as the browser would ────────────────── */

function extractScript(html) {
  const open = html.indexOf("<script>");
  assert.ok(open !== -1, "panel.html has no <script> block");
  const close = html.lastIndexOf("</script>");
  assert.ok(close > open, "panel.html has no closing </script>");
  // guard the invariant this whole file rests on: exactly ONE script block,
  // so "the script" is unambiguous and nothing under test is being skipped.
  const count = (html.match(/<script\b/g) || []).length;
  assert.strictEqual(count, 1,
    "expected exactly one <script> block in panel.html, found " + count);
  return html.slice(open + "<script>".length, close);
}

const html = fs.readFileSync(PANEL, "utf8");
const source = extractScript(html);

/* ── 2. the smallest DOM that lets the script finish parsing ───────────── */

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
  chanKey, paletteFor,
  _browseScrollKey, _browseScrollState, _restoreBrowseScroll, dirChip, resumableId,
  fmt,
  /* TENANTS was exported here. It is a lazy getter, so it kept "passing" after
     the global was deleted -- it would only have thrown the moment a test
     touched it. Removed with the tenant surface it belonged to. */
  get PROVIDERS(){ return PROVIDERS; }, set PROVIDERS(v){ PROVIDERS = v; }
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

test("15. a corrupt/hostile stored layout degrades to defaults", () => {
  const prev = sandbox.localStorage._m["sutra.panel.layout"];
  try {
    sandbox.localStorage._m["sutra.panel.layout"] = "{not json";
    deepEq(T.loadLayout(), { paneCollapsed: {}, folds: {}, browseW: null,
                             railCollapsed: false, railSections: {}, railTab: "home" },
      "unparseable layout must not take the panel down");
    sandbox.localStorage._m["sutra.panel.layout"] =
      JSON.stringify({ browseW: "700px", paneCollapsed: "nope", folds: 3 });
    deepEq(T.loadLayout(), { paneCollapsed: {}, folds: {}, browseW: null,
                             railCollapsed: false, railSections: {}, railTab: "home" },
      "wrong types must be dropped, not applied");
    sandbox.localStorage._m["sutra.panel.layout"] = JSON.stringify({ browseW: 12 });
    assert.strictEqual(T.loadLayout().browseW, null,
      "an absurdly small width would render an unusable sliver");
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
const panelHtml = fs.readFileSync(PANEL, "utf8");

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

test("20d. Shift+Enter is a newline and Enter still sends", () => {
  const h = panelHtml;
  assert.ok(/e\.key === "Enter" && \(e\.shiftKey/.test(h),
    "Shift+Enter must be handled before the send branch");
  assert.ok(/if\(e\.key==="Enter"\)\{/.test(h), "Enter must still send");
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

/* ── report ────────────────────────────────────────────────────────────── */

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
