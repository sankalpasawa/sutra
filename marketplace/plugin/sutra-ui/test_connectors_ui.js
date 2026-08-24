#!/usr/bin/env node
/*
 * test_connectors_ui.js -- wiring tests for the Connectors screen.
 *
 * WHY THIS EXISTS
 * ---------------
 * 2.112.3 shipped a Connectors screen that rendered perfectly and where no
 * button did anything. The handlers had been added inside the `.rail` click
 * listener, which only ever sees clicks inside `.rail`; every control on the
 * screen lives in `#scBody`. Rendering and event handling are separate paths
 * and only one of them was wrong, so the screen LOOKED right in a screenshot.
 *
 * test_panel.js could not catch it: it extracts the inline <script> from
 * panel.html, and this screen lives in static/js/12-connectors.js. 152 tests
 * passed while every button was dead.
 *
 * The load-bearing test here is the last one: every data-conn* attribute the
 * markup emits must have a handler that reads it. That generalises past this
 * one bug to "a control was rendered and nothing listens for it".
 *
 * Run: node test_connectors_ui.js
 */
const fs = require("fs");
const path = require("path");

const JS = p => fs.readFileSync(path.join(__dirname, "static/js", p), "utf8");
const loaders = JS("07-loaders.js");
const screen = JS("12-connectors.js");
const panelHtml = fs.readFileSync(path.join(__dirname, "static/panel.html"), "utf8");

let pass = 0, fail = 0;
function test(name, fn){
  try { fn(); console.log("ok   - " + name); pass++; }
  catch (e){ console.log("FAIL - " + name + "\n       " + e.message); fail++; }
}
function assert(cond, msg){ if (!cond) throw new Error(msg); }

/* Slice out the body of the shell's shared click listener so we can assert on
   it. v3.3 moved it from `.rail` to `#app` (the session list now lives in the
   second plane); the assertion's subject — connector handlers must not ride
   the shell delegation — is unchanged. */
function railListenerBody(src){
  const start = src.indexOf('document.getElementById("app").addEventListener("click"');
  assert(start !== -1, "shell (#app) click listener not found");
  const next = src.indexOf('document.addEventListener("click"', start);
  return src.slice(start, next === -1 ? src.length : next);
}

test("the screen is loaded by panel.html", () => {
  assert(/12-connectors\.js/.test(panelHtml), "12-connectors.js is not in panel.html");
});

test("12-connectors.js loads before 09-tail.js", () => {
  /* Match the SCRIPT TAGS, not the prose: panel.html explains this very
     ordering in a comment above them, and a plain indexOf finds the comment. */
  const tag = f => panelHtml.indexOf('<script src="/static/js/' + f);
  assert(tag("12-connectors.js") !== -1, "no script tag for 12-connectors.js");
  assert(tag("12-connectors.js") < tag("09-tail.js"),
    "load order would leave the screen undefined at boot (09-tail ends with boot())");
});

test("no connector handler sits in the rail listener", () => {
  /* The exact 2.112.3 bug. The rail listener cannot see #scBody clicks. */
  const body = railListenerBody(loaders);
  assert(!/data-conn/.test(body),
    "a connector handler is inside the .rail listener, where it can never fire");
});

test("the screen registers its own document-level click delegate", () => {
  assert(/document\.addEventListener\(\s*["']click["']/.test(screen),
    "12-connectors.js registers no click listener");
});

test("the delegate scopes itself to #scBody", () => {
  assert(/closest\(["']#scBody["']\)/.test(screen),
    "delegate is unscoped; a stray data-conn attribute anywhere would trigger it");
});

test("the delegate is not attached to a re-rendered element", () => {
  /* #scBody is rebuilt by render() every pass, so a listener bound to it would
     be discarded with the element. */
  assert(!/getElementById\(["']scBody["']\)\.addEventListener/.test(screen),
    "listener bound to #scBody would not survive a re-render");
});

test("every data-conn* control the markup emits has a handler", () => {
  /* The general form of the bug: a button rendered with nothing listening. */
  const emitted = new Set();
  for (const m of screen.matchAll(/\sdata-(conn[a-z]*)(?=[\s=>])/g)) emitted.add(m[1]);
  assert(emitted.size >= 5, "expected several data-conn* controls, found " + emitted.size);

  const handled = new Set();
  for (const m of screen.matchAll(/closest\(["']\[data-(conn[a-z]*)\]["']\)/g)) handled.add(m[1]);

  const orphans = [...emitted].filter(a => !handled.has(a));
  assert(orphans.length === 0,
    "controls rendered with no handler: " + orphans.map(o => "data-" + o).join(", "));
});

test("every handler corresponds to a control that exists", () => {
  const emitted = new Set();
  for (const m of screen.matchAll(/\sdata-(conn[a-z]*)(?=[\s=>])/g)) emitted.add(m[1]);
  const handled = new Set();
  for (const m of screen.matchAll(/closest\(["']\[data-(conn[a-z]*)\]["']\)/g)) handled.add(m[1]);
  const dead = [...handled].filter(a => !emitted.has(a));
  assert(dead.length === 0, "handlers for controls nothing renders: " + dead.join(", "));
});

test("the lazy loader fires when the screen opens", () => {
  /* 2.118.1 moved the open path into openScreen(id) — the guard reads `id`,
     not S.screen; the promise (open => load) is the same. */
  assert(/id\s*===\s*["']connectors["']\)\s*loadConnectors/.test(loaders),
    "opening the screen does not trigger loadConnectors");
});

test("the rail has a connectors entry", () => {
  const helpers = JS("02-helpers.js");
  assert(/id:\s*["']connectors["']/.test(helpers), "no rail entry for connectors");
});

/* ── CSS blast radius ────────────────────────────────────────────────────
 * The connectors CSS is appended to a stylesheet the WHOLE panel shares. A
 * rule written for this screen that is not scoped to it changes every other
 * screen -- which is exactly what happened: a global `a.btn{margin-top:7px}`
 * pushed the Updates screen's "Release notes" link 7px below the "Re-check"
 * button beside it.
 */
const css = fs.readFileSync(path.join(__dirname, "static/panel.css"), "utf8");

test("no global margin on a.btn", () => {
  const rule = css.match(/\n\s*a\.btn\{([^}]*)\}/);
  assert(rule, "a.btn rule not found");
  assert(!/margin-top/.test(rule[1]),
    "a.btn carries a global margin-top; it will misalign every <a class=btn> "
    + "next to a <button class=btn> panel-wide. Scope it (.note a.btn, etc).");
});

test("connector CSS additions are scoped", () => {
  /* Everything added for this screen must be reachable only from a connector
     container. A bare element or utility selector added here applies panel-wide. */
  /* Bounded at the NEXT section banner, not at EOF. Slicing to the end
     attributed every later addition to this section -- the streaming-caret
     rules appended afterwards were reported as unscoped connector CSS, which
     is a false positive that would train someone to ignore this test. */
  const start = css.indexOf("Connector tiles");
  const after = css.indexOf("─────", css.indexOf("\n", start) + 1);
  const section = css.slice(start, after === -1 ? css.length : after);
  const bare = [];
  for (const m of section.matchAll(/(?:^|\n)\s{2}([^@\s][^{\n]*)\{/g)) {
    const sel = m[1].trim();
    const scoped = /\.(ptile|ptiles|conn|tile|tbl|txactions|usercode|k-|r-|sc-head|sp\b|err\b|dot\b)/.test(sel);
    if (!scoped) bare.push(sel);
  }
  assert(bare.length === 0, "unscoped selectors added by the connectors CSS: " + bare.join(" | "));
});


/* ── mediated (Claude-owned) connector tile ──────────────────────────────
 * These EXECUTE the renderer. A regex over the source would pass for a tile
 * that interpolates a hostile string without esc(), because the source
 * contains the word "esc" plenty of times elsewhere.
 */
const vm = require("vm");

function mediatedSandbox(){
  const sandbox = {
    S: { conn: { mediated: null, mediatedBusy: false } },
    esc: v => String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;"),
    document: { addEventListener(){}, querySelector(){ return null; } },
    apiGet: async () => ({ tiles: [] }),
    render(){}, console,
    /* The file assigns its screen renderer into these at load. Stubbing them
       is what lets the real module run unmodified in a sandbox, so these
       tests exercise the shipped code rather than a copy of it. */
    SCREENS: {}, TITLES: {}, fmt: v => String(v),
    setTimeout, clearTimeout, encodeURIComponent, decodeURIComponent,
    Date, JSON, Math, Object, Array, String, Number, Boolean, RegExp,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  /* The file registers a document click listener at load; the stub above
     absorbs it. Everything else here is plain function declarations. */
  vm.runInContext(screen, sandbox, { filename: "12-connectors.js" });
  return sandbox;
}

const medTile = (over) => Object.assign({
  provider: "google", name: "Google", via: "claude",
  manage_url: "https://claude.ai/customize/connectors",
  account_known: false, availability: "ok", availability_detail: "",
  checked_at: 1787411853, stale: false,
  services: [
    { key: "gmail", name: "Gmail", membership: "added", observation: "connected",
      connectors: [{ label: "claude.ai Gmail", observation: "connected",
                     raw_status: "Connected" }] },
    { key: "gdrive", name: "Google Drive", membership: "not_added",
      observation: null, connectors: [] },
  ],
}, over || {});

test("mediatedTile escapes hostile text from the CLI", () => {
  const sb = mediatedSandbox();
  const evil = '<img src=x onerror=alert(1)>';
  const html = sb.mediatedTiles(medTile({ services: [
    { key: "gmail", name: "Gmail", membership: "added", observation: "unknown",
      connectors: [{ label: evil, observation: "unknown", raw_status: evil }] }]}));
  assert(!/<img src=x/.test(html), "raw CLI text reached the DOM unescaped");
  assert(/&lt;img/.test(html), "expected the payload to appear escaped");
});

test("mediatedTile escapes the availability detail", () => {
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile({
    availability: "cli_error", availability_detail: '<script>x</script>' }));
  assert(!/<script>x<\/script>/.test(html), "stderr reached the DOM unescaped");
});

test("the mediated tile never renders an account", () => {
  /* The Claude account email is usually a @gmail.com address and is the most
     tempting wrong answer available. It must not appear on a Google tile. */
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile());
  assert(/Account: not visible to Sutra/.test(html),
    "a connected tile must say the account is unknown, not stay silent about it");
  assert(!/@/.test(html.replace(/https?:\/\/[^"'\s]+/g, "")),
    "an email-shaped string appeared on the tile: " + html.slice(0, 300));
});

test("an unavailable check asserts NEITHER presence NOR absence, on any tile", () => {
  /* This replaced a test that matched the literal string "Status unknown".
     With one tile per connector that copy moved into a per-tile subtitle and a
     per-availability reason, so the old assertion tested the wording rather
     than the property. The property is what matters: when the check did not
     succeed, no tile may claim the connector exists OR that it does not. */
  const sb = mediatedSandbox();
  for (const avail of ["not_checked", "cli_missing", "timed_out", "cli_error", "unreadable"]){
    const html = sb.mediatedTiles(medTile({
      availability: avail,
      services: [{ key: "gmail", name: "Gmail", membership: "unknown",
                   observation: null, connectors: [] }] }));
    assert(!/Not listed by the Claude CLI/.test(html),
      avail + " asserted absence it cannot support");
    assert(!/Connected inside Claude/.test(html),
      avail + " asserted a connection it cannot support");
    assert(!/last check reported/.test(html),
      avail + " quoted an observation it does not have");
    assert(/could not check|Status unknown|Not checked yet|Claude Code is not installed/.test(html),
      avail + " gave the operator no signal that the state is unknown");
  }
});

test("the account note is suppressed when nothing is connected", () => {
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile({ services: [
    { key: "gmail", name: "Gmail", membership: "not_added",
      observation: null, connectors: [] }]}));
  assert(!/Account: not visible to Sutra/.test(html),
    "hedging about an account for a connector that is not added reads as a bug");
});

test("the mediated tile emits no connect or disconnect control", () => {
  /* Sutra cannot connect or revoke this -- Claude owns it. Rendering a button
     that cannot work would be a lie in the shape of a control. */
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile());
  for (const attr of ["data-connstart", "data-conndis", "data-connopen"]){
    assert(!html.includes(attr), "mediated tile emitted " + attr);
  }
  assert(html.includes("data-connrecheck"), "no re-check control");
  assert(/href="https:\/\/claude\.ai\/customize\/connectors"/.test(html),
    "no link out to where the connection can actually be managed");
});

test("both connectors on one host are rendered, never collapsed", () => {
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile({ services: [
    { key: "gmail", name: "Gmail", membership: "added", observation: "needs_auth",
      connectors: [
        { label: "claude.ai Gmail", observation: "connected", raw_status: "Connected" },
        { label: "claude.ai Gmail (2)", observation: "needs_auth",
          raw_status: "Needs authentication" }]}]}));
  assert(html.includes("claude.ai Gmail (2)"),
    "the second Google account vanished -- a broken connector hidden behind a healthy one");
});

test("probe results are attributed to the check, never asserted as state", () => {
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile());
  assert(/last check\s+reported/.test(html.replace(/\s+/g, " ")),
    "the status string must be attributed to the check that produced it");
});

test("every connector type gets its OWN tile", () => {
  /* Founder direction 2026-08-24, non-negotiable. One card listing four
     services made them look like sub-items of a product that does not exist. */
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile({ services: [
    { key:"gmail",  name:"Gmail",        membership:"added", observation:"connected",
      connectors:[{label:"claude.ai Gmail", observation:"connected", raw_status:"Connected"}] },
    { key:"gdrive", name:"Google Drive", membership:"added", observation:"connected",
      connectors:[{label:"claude.ai Google Drive", observation:"connected", raw_status:"Connected"}] },
    { key:"slack",  name:"Slack",        membership:"not_added", observation:null, connectors:[] },
    { key:"other:mcp.atlassian.com", name:"Atlassian Rovo", membership:"added",
      observation:"needs_auth", catalogued:false,
      connectors:[{label:"claude.ai Atlassian Rovo", observation:"needs_auth",
                   raw_status:"Needs authentication"}] },
  ]}));
  const tiles = html.match(/<div class="ptile mediated/g) || [];
  assert(tiles.length === 4, "expected 4 separate tiles, got " + tiles.length);
  for (const name of ["Gmail", "Google Drive", "Slack", "Atlassian Rovo"]){
    assert(html.includes(">" + name + "<"), "no tile headed " + name);
  }
});

test("each tile carries its own controls, not one shared set", () => {
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile());
  const tiles  = (html.match(/<div class="ptile mediated/g) || []).length;
  const checks = (html.match(/data-connrecheck=/g) || []).length;
  const manage = (html.match(/Manage in Claude/g) || []).length;
  assert(checks === tiles, `${tiles} tiles but ${checks} re-check buttons`);
  assert(manage === tiles, `${tiles} tiles but ${manage} manage links`);
});

test("a tile whose connector needs attention is marked, and healthy ones are not", () => {
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile({ services: [
    { key:"gmail", name:"Gmail", membership:"added", observation:"connected",
      connectors:[{label:"claude.ai Gmail", observation:"connected", raw_status:"Connected"}] },
    { key:"gdrive", name:"Google Drive", membership:"added", observation:"needs_auth",
      connectors:[{label:"claude.ai Google Drive", observation:"needs_auth",
                   raw_status:"Needs authentication"}] },
  ]}));
  const attn = (html.match(/ptile mediated attn/g) || []).length;
  assert(attn === 1, "exactly one tile should carry .attn, got " + attn);
});

test("an unavailable check marks EVERY tile unknown, not just the first", () => {
  /* With one card the availability note was rendered once. With N tiles a
     partial render would leave some tiles silently asserting stale state. */
  const sb = mediatedSandbox();
  const html = sb.mediatedTiles(medTile({
    availability: "unreadable",
    services: [
      { key:"gmail", name:"Gmail", membership:"unknown", observation:null, connectors:[] },
      { key:"slack", name:"Slack", membership:"unknown", observation:null, connectors:[] },
    ]}));
  const unknown = (html.match(/Status unknown/g) || []).length;
  assert(unknown >= 2, "every tile must say unknown, found " + unknown);
  assert(!/Not listed by the Claude CLI/.test(html),
    "an unreadable check must not assert absence on any tile");
});

test("opening the screen reads cache only and never probes", () => {
  /* The probe runs the Claude CLI, which contacts every connector and
     rewrites Claude's own cache. That must be a deliberate act. */
  assert(/loadMediated\(false\)/.test(loaders),
    "the screen must call loadMediated(false) -- cache only");
  assert(!/loadMediated\(true\)/.test(loaders),
    "no loader may force a probe on screen open");
});

console.log("\n" + "-".repeat(60));
console.log(`connectors UI wiring: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
