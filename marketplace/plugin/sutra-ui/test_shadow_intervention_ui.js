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
  /* `where it runs` rather than `turn`: the count moved to the pinned
     header on 2026-09-20 when the brief became the first message of the
     conversation. The brief itself renders exactly as it did. */
  assert(/where it runs/.test(h) && /done when/.test(h),
    "the brief still renders");
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
  const M = targeted();
  const h = card(ctx, M);
  /* ── REVERSED 2026-09-23 ─────────────────────────────────────────────
     This block pinned that the form SHOWS which internal check a Yes
     closes. The founder's ruling: "Remove the YES SIGNS OFF line and the
     internal acceptance criterion entirely. The user does not need to see
     Shadow's internal judgment/sign-off language."

     ONLY THE DISPLAY WENT. shadowIvSignsIndex still decides which check a
     field closes, the answer still closes it, and the lanes that assert on
     that behaviour are untouched -- see the confirms_check checks below and
     test_shadow_intervention_confirms.py. What is gone is printing the
     bookkeeping at the founder. */
  assert(!/shivsigns/.test(h), "the internal sign-off row is not shown");
  /* the check string went with the row that quoted it (2026-09-23): it is
     Shadow's own acceptance criterion, and the founder is answering a
     question, not auditing a checklist. Asserted where it still matters --
     that the ANSWER closes it -- in test_shadow_intervention_confirms.py. */
  assert(h.indexOf(CHECK) === -1,
    "the internal acceptance criterion is not quoted at the founder");
  assert(!/Yes signs off/.test(h), "nor its label");
  /* THE BINDING IS UNCHANGED, and that is the point of keeping this block:
     the field still KNOWS which check it closes, which is what the answer
     acts on. Only the printing of it went. */
  assert.strictEqual(
    ctx.shadowIvSignsIndex(M, M.intervention.fields[0]), 1,
    "the gating field still names the check it closes");
  assert.strictEqual(
    ctx.shadowIvSignsIndex(M, M.intervention.fields[1]), -1,
    "and the other field still closes nothing");
  console.log("ok 12 confirms_check still binds; it is no longer printed");
}

/* 13. an intervention WITHOUT confirms_check renders exactly as before */
{
  const ctx = fresh();
  const plain = card(ctx, targeted(null));
  assert(!/shivsigns/.test(plain), "no target -> no row");
  assert(form(plain).indexOf(CHECK) === -1, "and no check text in the form");
  assert(/Which region\?/.test(plain) && /data-shivsend=/.test(plain),
    "the form itself is untouched");
  /* THE FORM IS BYTE-FOR-BYTE THE SAME. Every field, hook, value and the
     submit button are identical with or without the marker -- that is the
     invariant this test has always existed to hold, and it still holds.

     WHAT LEGITIMATELY CHANGED (founder, 2026-09-15): a card that signs off
     a check now draws NO context paragraph, because on a sign-off the
     question asks it and the criterion defines the bar, and the decider's
     "why I can't settle this myself" is narration beside them. So the two
     cards also differ by that paragraph, deliberately. The text is not
     lost -- it rides on the question's title. */
  const bare = (h) => form(h)
    .replace(/<div class="shivsigns">[\s\S]*?<\/div>/, "")
    .replace(/<p class="shnewsub shivctx"[\s\S]*?<\/p>/, "")
    .replace(/ title="[^"]*"/g, "");
  assert.strictEqual(bare(card(ctx, targeted())), bare(plain),
    "the FORM must be identical with or without the marker");
  /* THE BRIEF legitimately differs too (founder, 2026-09-15): when the ask
     signs off every unmet check, the flat done-when row stands aside rather
     than printing the criterion a second time. */
  assert(!/shcard2k">done when</.test(card(ctx, targeted())),
    "the ask covers the only unmet check, so the flat row stands aside");
  assert(/shcard2k">done when</.test(plain),
    "an ask that confirms nothing leaves the checklist alone");
  /* ...and the sign-off card is the calm one */
  const signed = card(ctx, targeted());
  assert(!/shivctx/.test(signed),
    "a sign-off card must not draw Shadow's reasoning as a paragraph");
  assert(/shivctx/.test(plain),
    "an ordinary ask still shows its context, clamped to one line");
  assert(/class="shivq" title="/.test(signed),
    "the context must stay reachable on the question's title");
  console.log("ok 13 a non-confirms_check intervention renders byte-identical"
    + " to pre-change output");
}

/* 14. FALLBACK: the check is real but has no text to quote */
{
  const ctx = fresh();
  const blank = [{ tier: "founder_confirm", check: "   ", met: false }];
  const h = card(ctx, targeted({ index: 0 }, blank));
  /* the sign-off still HAPPENS -- it is simply not narrated at the founder
     (2026-09-23). shadowIvSignsIndex is what decides it, and it is asserted
     directly rather than through markup that no longer exists. */
  assert(!/shivsigns/.test(h), "it still happens; it is no longer shown");
  assert(!/check 1/.test(h),
    "and neither is the positional fallback it used when the check was blank");
  assert(h.indexOf("no text for it") === -1,
    "nor the apology it used to make for a check with no words in it");
  assert(!/“\s*”/.test(h), "and no empty quotation anywhere");
  /* the BINDING is still whatever it was -- a blank check is still the one
     this field closes, and the answer still closes it */
  assert.strictEqual(
    ctx.shadowIvSignsIndex(targeted({ index: 0 }, blank),
      targeted({ index: 0 }, blank).intervention.fields[0]), 0,
    "a check with no text is still bound to its field");
  console.log("ok 14 a blank check is bound and, like every check, unprinted");
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

/* 16. A CHECK IS FOUNDER TEXT, AND IT IS NOT DRAWN AT ALL NOW. The row that
   quoted it went on 2026-09-23, so the escaping it needed is moot HERE --
   but the string must not reach this surface by any other route either,
   which is the stronger thing to assert. The card's own done-when summary
   still prints checks, and still escapes them; that is its own lane. */
{
  const ctx = fresh();
  const evil = [{ tier: "founder_confirm", met: false,
    check: "<img src=x onerror=alert(1)>" }];
  const h = ctx.shadowInterventionHtml(targeted({ index: 0 }, evil));
  assert(!/shivsigns/.test(h), "the sign-off row is gone");
  assert(h.indexOf("<img") === -1, "and no raw markup reaches the ask");
  assert(h.indexOf("onerror") === -1, "escaped or absent, never live");
  console.log("ok 16 a check never reaches the ask, escaped or otherwise");
}

/* 17. WHAT IS BEING JUDGED IS ON SCREEN, AND IT IS ABOVE THE QUESTION
   (founder, 2026-09-23). Shadow asked "are these the ten you wanted?" and
   the ten were nowhere on this surface. The key was always validated and
   always rendered -- it was documented nowhere, so Shadow never sent it,
   and it drew UNDER the question when it did. Both halves pinned here. */
{
  const ctx = fresh();
  const lines = "1. First story\n2. Second story\n3. Third story";
  const m = mission(null, { intervention: {
    id: "iv-ten", schema_version: 1,
    question: "Are these the ten stories you wanted?",
    context: "",
    evidence: [{ kind: "output", ref: "news.md", text: lines }],
    fields: [{ key: "list_ok", type: "boolean",
               label: "These are the ten I wanted." }],
    submit_label: "Send to Shadow", expires_at: null } });
  const h = ctx.shadowInterventionHtml(m);

  assert(/shivev/.test(h), "the material is drawn at all");
  assert(h.indexOf("First story") !== -1, "verbatim, not summarised");
  assert(h.indexOf("news.md") !== -1, "and it says where it came from");
  assert(h.indexOf("shivev") < h.indexOf("shivq"),
    "IT IS ABOVE THE QUESTION -- a question about ten lines printed above "
    + "the ten lines is one the founder must scroll past to answer");
  console.log("ok 17 the judged material is on screen, above the question");
}

/* 18. AN ASK THAT NEEDS NO EVIDENCE IS UNCHANGED. How much to show is
   Shadow's judgement about the question; none is a legal answer to it, and
   this renderer must not grow a placeholder for it. */
{
  const ctx = fresh();
  const m = mission(null, { intervention: {
    id: "iv-bare", schema_version: 1, question: "Which region?",
    context: "", evidence: [],
    fields: [{ key: "region", type: "text", label: "Region" }],
    submit_label: "Send to Shadow", expires_at: null } });
  const h = ctx.shadowInterventionHtml(m);
  assert(!/shivev/.test(h), "no evidence block, and no empty one either");
  assert(/shivq/.test(h) && /Which region\?/.test(h), "the ask still works");
  console.log("ok 18 an ask needing no evidence draws none");
}

/* 19-26. THE ASK IS A USER-FACING SURFACE (founder, 2026-09-23). Nine
   points, each one a thing the machine used to say out loud or a decision
   the founder could not see. */
{
  const ctx = fresh();
  const RESULT = "1. Fed holds rates steady\n2. EU agrees AI liability rules";
  const ask = (over) => mission(null, { intervention: Object.assign({
    id: "iv-9", schema_version: 1,
    question: "Are these the ten stories you wanted?", context: "",
    evidence: [{ kind: "output", ref: "international-news.md", text: RESULT }],
    fields: [{ key: "list_ok", type: "boolean",
               label: "These are the ten I wanted.", required: true,
               options: [], constraints: {} }],
    submit_label: "Send to Shadow", expires_at: null }, over || {}),
    done_when: [{ tier: "founder_confirm",
                  check: "The ten are the ones I wanted.", met: false }] });

  const h = ctx.shadowInterventionHtml(ask());

  /* (1) no internal vocabulary anywhere on this surface */
  for (const word of ["Evidence", "worker reply", "worker chat", "its own chat",
                      "predicate", "sign off", "signs off"])
    assert(h.toLowerCase().indexOf(word.toLowerCase()) === -1,
      "internal word on a user-facing surface: " + JSON.stringify(word));
  console.log("ok 19 no internal vocabulary is rendered");

  /* (2) the sign-off strip specifically */
  assert(!/shivsigns/.test(h), "the Yes-signs-off strip is not drawn");
  assert(h.indexOf("The ten are the ones I wanted") === -1,
    "nor the internal check it would have quoted");
  console.log("ok 20 'YES SIGNS OFF' and its criterion are gone");

  /* (3) and (4) the result IS here, in the success tone */
  assert(h.indexOf("Fed holds rates steady") !== -1,
    "the result is in Shadow -- no other chat needed to read it");
  assert(/shivev/.test(h), "drawn as the result block");
  console.log("ok 21 the result is rendered directly in Shadow");

  /* (5) and (6) the two answers carry the two tones */
  assert(/shkindyes/.test(h) && /shkindno/.test(h),
    "Yes and No are distinguishable at all");
  const css = fs.readFileSync(
    path.join(__dirname, "static", "panel.css"), "utf8");
  assert(/\.shkindyes\.on\{[^}]*--ok/.test(css),
    "a chosen Yes uses the success tone");
  assert(/\.shkindno\.on\{[^}]*--block/.test(css),
    "a chosen No uses the refusal tone");
  assert(/\.shwright \.shivev\{[^}]*--ok/.test(css),
    "and the result block is the success tone, not the warm accent");
  console.log("ok 22 Yes is green, No is red, the result is green");

  /* (7) choosing No opens somewhere to say what is wrong */
  const m = ask();
  assert(!/data-shivwhy/.test(ctx.shadowInterventionHtml(m)),
    "nothing extra before an answer is chosen");
  ctx.shadowIvDraft(m.id).values.list_ok = true;
  assert(!/data-shivwhy/.test(ctx.shadowInterventionHtml(m)),
    "and none on a Yes");
  ctx.shadowIvDraft(m.id).values.list_ok = false;
  const no = ctx.shadowInterventionHtml(m);
  assert(/data-shivwhy/.test(no), "a No opens a field to say what is wrong");
  assert(/What should I change\?/.test(no),
    "asked in the founder's language, not a form label");
  console.log("ok 23 selecting No exposes a field for what to change");

  /* (8) what they type there rides the task's own conversation */
  ctx.shadowIvSetWhy(m.id, "list_ok", "Too much finance \u2014 more science.");
  assert.strictEqual(ctx.shadowIvWhy(m.id, "list_ok"),
    "Too much finance \u2014 more science.", "it is kept on the same draft");
  assert(/Too much finance/.test(ctx.shadowInterventionHtml(m)),
    "and survives a re-render while they are typing");
  console.log("ok 24 the No feedback is held on the ask's own draft");

  /* (9) and the ask still works: question, answer, send */
  assert(/Are these the ten stories you wanted\?/.test(no), "the question stands");
  assert(/data-shivopt="yes"/.test(no) && /data-shivopt="no"/.test(no),
    "both answers are still offered");
  assert(/data-shivsend/.test(no), "and it can still be sent");
  console.log("ok 25 the existing question behaviour is intact");
}

setTimeout(() => console.log("\nall shadow intervention UI tests passed"), 30);
