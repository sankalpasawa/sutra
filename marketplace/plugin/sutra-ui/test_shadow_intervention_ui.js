#!/usr/bin/env node
/* test_shadow_intervention_ui.js -- the generic form, drawn and submitted.
 *
 * The rule this suite exists to hold: a mission WITHOUT an intervention must
 * render byte-for-byte what it rendered before, and a mission WITH one must
 * draw whatever schema the server sent -- not a hard-coded yes/no.
 *
 * Run: node test_shadow_intervention_ui.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }),
    S: {}, SCREENS: {}, TITLES: {},
    posts: [], nudges: [], loads: 0,
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    escAttr: undefined,
    showNudge: (t) => ctx.nudges.push(t),
    loadShadowHome: async () => { ctx.loads++; },
    scheduleRender: () => {},
    listeners: {},
    document: {
      addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8"), ctx);
  vm.runInContext(fs.readFileSync(
    path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8"), ctx);
  return ctx;
}

const F = (key, type, extra) => Object.assign(
  { key, type, label: key, help: "", required: false, default: null,
    options: (["choice", "multi_choice", "ranking"].indexOf(type) !== -1)
      ? [{ value: "a", label: "A", help: "" }, { value: "b", label: "B", help: "" }]
      : [],
    constraints: {} }, extra || {});

function mission(fields, over){
  return Object.assign({
    id: "m-1", objective: "ship it", template: "fix", state: "blocked",
    block_reason: "needs_founder", target_mode: "new",
    target_session: "s-1", target_chat: "c-1",
    turns_used: 2, max_turns: 20, done_when: [],
    intervention: fields === null ? undefined : {
      id: "iv-abc", schema_version: 1, question: "Which region?",
      context: "two configs disagree",
      evidence: [{ kind: "quote", ref: "cfg.yaml:14", text: "region: eu" }],
      fields: fields, submit_label: "Send to Shadow", expires_at: null,
    },
  }, over || {});
}

/* THE ASK IS A SIBLING OF THE CARD NOW ("Shadow Design - Final", founder
   2026-09-15): shadowHomeHtml emits shadowInterventionHtml directly into the
   RHS spine instead of shadowTaskCardHtml nesting it. The renderer, its
   hooks, its draft store and its POST are unchanged, so this helper simply
   composes the pane the way the pane does. */
const card = (ctx, m) =>
  ctx.shadowTaskCardHtml(m) + ctx.shadowInterventionHtml(m);

/* 1. NOTHING MOVED for a mission with no intervention */
{
  const ctx = fresh();
  const h = card(ctx, mission(null));
  assert(!/shiv/.test(h), "a mission with no intervention must gain nothing");
  assert(/>turn</.test(h) && /done when/.test(h), "the brief still renders");
  console.log("ok 1 no intervention -> the card is unchanged");
}

/* 2. blocked + intervention still reads NEEDS YOU */
{
  const ctx = fresh();
  const m = mission([F("region", "choice")]);
  assert.strictEqual(ctx.shadowTaskFaceFor(m).label, "NEEDS YOU",
    "blocked already means NEEDS YOU; the form must not change the face");
  const h = card(ctx, m);
  assert(/Which region\?/.test(h), "the question renders");
  assert(/two configs disagree/.test(h), "the context renders");
  assert(/cfg\.yaml:14/.test(h), "the evidence renders");
  assert(/Send to Shadow/.test(h), "the submit label renders");
  console.log("ok 2 NEEDS YOU + question + context + evidence");
}

/* 3. EVERY answerable type draws a control */
{
  const ctx = fresh();
  const types = ["boolean", "choice", "multi_choice", "text", "long_text",
    "number", "currency", "percent", "date", "datetime", "url", "email",
    "ranking"];
  types.forEach((t) => {
    const h = card(ctx, mission([F("f", t)]));
    assert(/shivfield/.test(h), t + ": no field rendered");
    const drawn = /data-shivopt=/.test(h) || /data-shivtext="1"/.test(h);
    assert(drawn, t + ": no usable control rendered");
  });
  console.log("ok 3 all 13 answerable types render a control");
}

/* 4. the right control for the right type */
{
  const ctx = fresh();
  assert(/type="date"/.test(card(ctx, mission([F("f", "date")]))), "date");
  assert(/type="datetime-local"/.test(card(ctx, mission([F("f", "datetime")]))),
    "datetime");
  assert(/type="email"/.test(card(ctx, mission([F("f", "email")]))), "email");
  assert(/type="url"/.test(card(ctx, mission([F("f", "url")]))), "url");
  assert(/type="number"/.test(card(ctx, mission([F("f", "percent")]))), "percent");
  assert(/<textarea/.test(card(ctx, mission([F("f", "long_text")]))), "long_text");
  const b = card(ctx, mission([F("f", "boolean")]));
  assert(/data-shivopt="yes"/.test(b) && /data-shivopt="no"/.test(b), "boolean");
  console.log("ok 4 each type maps to the right control");
}

/* 5. an UNKNOWN type is honest, not silently dropped */
{
  const ctx = fresh();
  const h = card(ctx, mission([F("f", "hologram")]));
  assert(/cannot ask for/.test(h),
    "a newer Shadow in front of an older panel must say so");
  console.log("ok 5 unknown type degrades honestly");
}

/* 6. MANY FIELDS, ONE FORM */
{
  const ctx = fresh();
  const h = card(ctx, mission([
    F("region", "choice"), F("cap", "currency"),
    F("when", "date"), F("agree", "boolean", { required: true })]));
  assert((h.match(/shivfield/g) || []).length === 4, "four fields render");
  assert((h.match(/data-shivsend=/g) || []).length === 1,
    "one submit for the whole form");
  assert(/shivreq/.test(h), "required is marked");
  console.log("ok 6 a multi-field form is one coherent response");
}

/* 7. clicking options writes the draft */
{
  const ctx = fresh();
  const m = mission([F("pick", "choice"), F("many", "multi_choice"),
    F("ok", "boolean"), F("order", "ranking")]);
  ctx.S.shadowMissions = [m];
  const click = (ds) => ctx.listeners.click({
    target: { dataset: ds, closest: () => null }, stopPropagation(){} });
  click({ shivopt: "a", shivmid: "m-1", shivkey: "pick" });
  click({ shivopt: "a", shivmid: "m-1", shivkey: "many" });
  click({ shivopt: "b", shivmid: "m-1", shivkey: "many" });
  click({ shivopt: "yes", shivmid: "m-1", shivkey: "ok" });
  click({ shivopt: "b", shivmid: "m-1", shivkey: "order" });
  click({ shivopt: "a", shivmid: "m-1", shivkey: "order" });
  const v = ctx.shadowIvDraft("m-1").values;
  assert.strictEqual(v.pick, "a", "choice");
  /* join(): the draft's arrays are built inside the vm realm, so their
     prototype is not the host's Array -- deepStrictEqual would reject
     identical contents on that alone. Compare by value. */
  assert.strictEqual(v.many.join(","), "a,b", "multi_choice accumulates");
  assert.strictEqual(v.ok, true, "boolean yes");
  assert.strictEqual(v.order.join(","), "b,a", "ranking keeps click order");
  click({ shivopt: "a", shivmid: "m-1", shivkey: "many" });
  assert.strictEqual(v.many.join(","), "b", "clicking again deselects");
  console.log("ok 7 option clicks build the draft");
}

/* 8. typing writes the draft, on the EXISTING input listener */
{
  const ctx = fresh();
  ctx.S.shadowMissions = [mission([F("note", "text")])];
  ctx.listeners.input({ target: { dataset: {
    shivtext: "1", shivmid: "m-1", shivkey: "note" }, value: "hello" } });
  assert.strictEqual(ctx.shadowIvDraft("m-1").values.note, "hello");
  // and the delegate panel's own fields still work on that same listener
  ctx.listeners.input({ target: { dataset: { shnewobj: "1" }, value: "obj" } });
  assert.strictEqual(ctx.shadowNewDraft().objective, "obj",
    "the existing + Delegate input path must be untouched");
  console.log("ok 8 typing writes the draft; + Delegate still works");
}

/* 9. the draft value is rendered back (render() runs constantly) */
{
  const ctx = fresh();
  const m = mission([F("note", "text")]);
  ctx.S.shadowMissions = [m];
  ctx.shadowIvDraft("m-1").values.note = "kept";
  assert(/value="kept"/.test(card(ctx, m)), "typed text survives a repaint");
  console.log("ok 9 the draft survives re-render");
}

/* 10. SEND posts one payload to the existing endpoint */
{
  const ctx = fresh();
  const m = mission([F("region", "choice"), F("cap", "number")]);
  ctx.S.shadowMissions = [m];
  ctx.shadowIvDraft("m-1").values = { region: "a", cap: 5 };
  ctx.shadowPost = async (url, body) => {
    ctx.posts.push({ url, body });
    return { ok: true, status: 200, json: async () => ({}) };
  };
  ctx.shadowSendIntervention("m-1").then(() => {
    assert.strictEqual(ctx.posts.length, 1, "exactly one POST");
    const p = ctx.posts[0];
    assert.strictEqual(p.url, "/api/shadow/missions/m-1/act",
      "the EXISTING mission action endpoint");
    assert.strictEqual(p.body.action, "intervene");
    assert.strictEqual(p.body.intervention_id, "iv-abc",
      "the id is sent so a stale answer can be refused");
    assert.strictEqual(JSON.stringify(p.body.values),
      JSON.stringify({ region: "a", cap: 5 }));
    console.log("ok 10 one POST, one payload, the right endpoint");
  });
}

/* 11. a 422 shows per-field errors and keeps the form up */
{
  const ctx = fresh();
  const m = mission([F("region", "choice")]);
  ctx.S.shadowMissions = [m];
  ctx.shadowIvDraft("m-1").values = { region: "zzz" };
  ctx.shadowPost = async () => ({
    ok: false, status: 422,
    json: async () => ({ detail: { detail: "some answers need a fix",
      intervention_id: "iv-abc",
      errors: { region: "pick one of the offered options" } } }),
  });
  ctx.shadowSendIntervention("m-1").then(() => {
    const d = ctx.shadowIvDraft("m-1");
    assert.strictEqual(d.errors.region, "pick one of the offered options");
    assert(/pick one of the offered options/.test(card(ctx, m)),
      "the message renders beside its field");
    assert(!d.busy, "the button is usable again");
    console.log("ok 11 field errors render and the form stays");
  });
}

/* ── confirms_check: the form says what the Yes signs off ────────────────
 * The server (39682c81) lets an intervention name one done_when check and
 * the boolean field that gates it. These hold the UI half: the check text
 * is QUOTED VERBATIM (founder decision, 2026-09-15), and every condition
 * the server refuses to act on draws nothing at all.
 */
const CHECK = "Relevant tests pass.";

/* The card's flat "done when" row already prints every check, so "is the
 * text on the card" cannot tell the row apart from that summary. These
 * assertions look at the FORM only -- opening tag to submit button. */
const form = (h) => h.slice(h.indexOf('<div class="shiv" '),
  h.indexOf("data-shivsend"));

/* a mission whose intervention targets done_when[ix]; `over` patches the
 * target so one helper covers the valid case and every broken one */
function targeted(over, checks){
  const m = mission([F("tests_pass", "boolean"), F("note", "text")]);
  m.done_when = checks || [
    { tier: "contains_artifact", check: "The change is implemented.", met: true },
    { tier: "founder_confirm", check: CHECK, met: false },
  ];
  if (over !== null)
    m.intervention.confirms_check = Object.assign(
      { index: 1, field: "tests_pass" }, over || {});
  return m;
}

/* 12. THE CHECK TEXT IS QUOTED, VERBATIM */
{
  const ctx = fresh();
  const h = card(ctx, targeted());
  assert(/shivsigns/.test(h), "the sign-off row must render");
  assert(h.indexOf(CHECK) !== -1,
    "the LITERAL check string must appear -- not a paraphrase of it");
  assert(/Yes signs off/.test(h), "the row says what the Yes does");
  assert(h.indexOf("“" + CHECK + "”") !== -1,
    "quoted, so the founder can see where the criterion starts and ends");
  /* it belongs to the gating field, not to the form at large */
  const fields = h.split('class="shivfield"');
  assert(fields[1].indexOf(CHECK) !== -1, "it sits under tests_pass");
  assert(fields[2].indexOf(CHECK) === -1, "and not under the other field");
  console.log("ok 12 confirms_check renders the literal check string");
}

/* 13. an intervention WITHOUT confirms_check renders exactly as before */
{
  const ctx = fresh();
  const plain = card(ctx, targeted(null));
  assert(!/shivsigns/.test(plain), "no target -> no row");
  assert(form(plain).indexOf(CHECK) === -1, "and no check text in the form");
  assert(/Which region\?/.test(plain) && /data-shivsend=/.test(plain),
    "the form itself is untouched");
  /* byte-for-byte: the ONLY difference the feature may make is inserting
     that one div. Strip it from the targeted card and the two must match. */
  const stripped = card(ctx, targeted())
    .replace(/<div class="shivsigns">[\s\S]*?<\/div>/, "");
  assert.strictEqual(stripped, plain,
    "a targeted card must differ from an untargeted one by the row alone");
  console.log("ok 13 a non-confirms_check intervention renders byte-identical"
    + " to pre-change output");
}

/* 14. FALLBACK: the check is real but has no text to quote */
{
  const ctx = fresh();
  const blank = [{ tier: "founder_confirm", check: "   ", met: false }];
  const h = card(ctx, targeted({ index: 0 }, blank));
  assert(/shivsigns/.test(h), "the sign-off still happens, so it still shows");
  assert(/Yes signs off/.test(h), "and still says so");
  assert(/check 1/.test(h), "named by position when it cannot be quoted");
  assert(/no text for it/.test(h), "and honest that there is nothing to read");
  assert(!/“\s*”/.test(h), "never quote an empty string as criterion");
  console.log("ok 14 whitespace-only check text falls back to the generic"
    + " label");
}

/* 15. every target the SERVER would refuse draws nothing */
{
  const ctx = fresh();
  const silent = (over, checks, why) => {
    const h = card(ctx, targeted(over, checks));
    assert(!/shivsigns/.test(h), why);
    assert(form(h).indexOf(CHECK) === -1, why + " (and quotes nothing)");
  };
  silent({ index: 9 }, null, "an out-of-range index");
  silent({ index: -1 }, null, "a negative index");
  silent({ index: 1.5 }, null, "a non-integer index");
  silent({ index: true }, null, "a boolean index (would read as 1)");
  silent({ index: "1" }, null, "a string index");
  silent({ index: 0 }, null, "a check that is not founder_confirm");
  silent({ field: "note" }, null, "a field that is not boolean");
  silent({ field: "absent" }, null, "a field that is not on the form");
  silent({}, [], "a mission with no done_when at all");
  console.log("ok 15 nine refused targets draw nothing at all");
}

/* 16. the quote is ESCAPED -- a check is founder text, not markup */
{
  const ctx = fresh();
  const evil = [{ tier: "founder_confirm", met: false,
    check: "<img src=x onerror=alert(1)>" }];
  const h = card(ctx, targeted({ index: 0 }, evil));
  assert(/shivsigns/.test(h), "it still renders");
  assert(h.indexOf("<img") === -1, "the check text must go through esc()");
  assert(/&lt;img/.test(h), "escaped, not dropped");
  console.log("ok 16 check text is escaped before it is quoted");
}

setTimeout(() => console.log("\nall shadow intervention UI tests passed"), 30);
