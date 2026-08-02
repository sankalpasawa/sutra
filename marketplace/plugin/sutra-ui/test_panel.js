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
  get PROVIDERS(){ return PROVIDERS; }, set PROVIDERS(v){ PROVIDERS = v; },
  get TENANTS(){ return TENANTS; },   set TENANTS(v){ TENANTS = v; }
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

test("10c. ORG-017: the move crosses a tenant boundary", () => {
  T.DOMAINS = D;
  // r4 is T-acme AND already parents a live "Research" -> both codes fire
  deepEq(codesOf("r1", "r4"), ["ORG-017", "ORG-018"]);
  // a cross-tenant target with no name clash fires ORG-017 alone
  deepEq(codesOf("r2", "r4"), ["ORG-017"]);
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
