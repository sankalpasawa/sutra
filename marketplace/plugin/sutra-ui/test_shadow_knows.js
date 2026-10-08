#!/usr/bin/env node
/* test_shadow_knows.js -- What Shadow learned (founder, 2026-10-07).

   The settings sheet draws, above each of the founder's two boxes, the list
   the system fills in (shadow_knows): suggestions first with Keep / Drop,
   then the lines that bind with where they came from, edit and forget, then
   an add line. Suggestions also surface in the task pane. Every write goes
   through POST /api/shadow/knows and the page redraws from its answer.

   Run: node test_shadow_knows.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const overlay = fs.readFileSync(path.join(__dirname, "static", "js", "15-shadow-overlay.js"), "utf8");
const home = fs.readFileSync(path.join(__dirname, "static", "js", "16-shadow-home.js"), "utf8");
const FIXTURE = JSON.parse(fs.readFileSync(
  path.join(__dirname, "test_fixtures", "shadow_v4", "settings.json"), "utf8"));

const SWITCHES = [
  { name: "acting", label: "Acting on its own", default: "balanced",
    value: "balanced", set: false,
    options: [{ value: "ask_first", label: "Ask first" },
              { value: "balanced", label: "Balanced" },
              { value: "just_do_it", label: "Just do it" }] },
  { name: "replies", label: "Replies", default: "short", value: "normal",
    set: true,
    options: [{ value: "short", label: "Short" },
              { value: "normal", label: "Normal" },
              { value: "detailed", label: "Detailed" }] },
];
const KNOWS = {
  personality: [
    { id: "know-p1", section: "personality", category: "rules",
      text: "Pick regions yourself", source: "asked", status: "pending",
      evidence: "Asked: Which region?", expired: false },
    { id: "know-p2", section: "personality", category: "rules",
      text: "Run tests before done", source: "said", status: "active",
      expired: false },
  ],
  memory: [
    { id: "know-m1", section: "memory", category: "work",
      text: "Launch on Oct 20", source: "typed", status: "active",
      expired: true },
    { id: "know-m2", section: "memory", category: "you",
      text: "CEO of Sutra", source: "said", status: "active", expired: false },
  ],
  pending: 1, max_active: 10, switches: SWITCHES,
};

function fresh(){
  const ctx = {
    console, Date, setTimeout: (fn) => ({ fn }), setImmediate,
    esc: (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;"),
    escAttr: (x) => String(x == null ? "" : x).replace(/"/g, "&quot;"),
    SCREENS: {}, TITLES: {}, S: {}, listeners: {}, posts: [], renders: 0,
    document: { addEventListener(t, fn){ ctx.listeners[t] = fn; },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      body: { appendChild(){} }, querySelector(){ return null; },
      querySelectorAll(){ return []; } },
  };
  ctx.scheduleRender = () => { ctx.renders++; };
  ctx.fetch = async (url, opts) => {
    const body = JSON.parse((opts && opts.body) || "{}");
    /* only the writes this feature makes; a click also refreshes the home */
    if (url === "/api/shadow/knows") ctx.posts.push({ url, body });
    if (body.text && /sk-/.test(body.text))
      return { ok: false, status: 409,
               json: async () => ({ detail: "that looks like a credential" }) };
    return { ok: true, status: 200,
             json: async () => ({ row: {}, knows: { personality: [], memory: [], pending: 0 } }) };
  };
  vm.createContext(ctx);
  vm.runInContext(overlay, ctx);
  vm.runInContext(home, ctx);
  return ctx;
}
const settle = () => new Promise(r => setImmediate(() => setImmediate(r)));
const target = (dataset, extra) => Object.assign(
  { dataset, closest(){ return null; } }, extra || {});

(async () => {
  /* 1. the sheet: one suggestions line, four switches, three folded groups,
     the founder's own words folded at the end (2026-10-07) */
  {
    const ctx = fresh();
    const d = JSON.parse(JSON.stringify(FIXTURE));
    d.knows = JSON.parse(JSON.stringify(KNOWS));
    ctx.S.shadowSettings = d;
    const h = ctx.shadowSettingsHtml();
    const at = (x) => h.indexOf(x);
    assert(at("1 suggestion waiting") !== -1 && at("1 suggestion waiting") < at(">How Shadow works for you<"),
      "suggestions are one line, above everything");
    assert(at("Pick regions yourself") === -1, "and folded until opened");
    assert(/data-shswitch="replies" data-shval="normal"/.test(h), "switches carry their hooks");
    assert(/class="ssseg on"[^>]*data-shswitch="replies" data-shval="normal"/.test(h),
      "the set value is the one drawn on");
    const rules = at("Other things Shadow should always do");
    assert(rules > at(">How Shadow works for you<")
           && rules < at(">What Shadow remembers about you<"),
      "the rules list sits under How Shadow works for you");
    assert(/Other things Shadow should always do<span class="sscount"\s+aria-label="1 saved">1</.test(h),
      "counting only lines that bind");
    for (const [label, n] of [["About you", 1], ["Your work", 1], ["Your preferences", 0]])
      assert(new RegExp(label + '<span class="sscount"\\s+aria-label="' + n + ' saved">' + n + "<").test(h)
             && at(label) > at(">What Shadow remembers about you<"), label + " has its count");
    assert(/CEO of Sutra/.test(h), "a folded group shows a preview");
    assert(/Shadow will fill this in/.test(h), "an empty group says so in one line");
    assert(!/data-shknowadd=/.test(h), "no add lines until a group is opened");
    assert(at("Tell Shadow in your own words") > at(">What Shadow remembers about you<"), "the founder's own words come last");
    assert(/class="ssownbody" hidden/.test(h), "folded when they have written nothing");
    assert(/data-shbehaves="1"/.test(h) && /data-shmemory="1"/.test(h),
      "but the two boxes stay in the page");
  }

  /* 2. opening: a group shows its lines, where they came from and an add line;
     the suggestions line shows Keep / Drop; own words open once written */
  {
    const ctx = fresh();
    const d = JSON.parse(JSON.stringify(FIXTURE));
    d.knows = JSON.parse(JSON.stringify(KNOWS));
    d.behaves = "Check in rarely.";
    ctx.S.shadowSettings = d;
    ctx.listeners.click({ target: target({}, { closest: (sel) =>
      sel === "[data-shkgroup]" ? { dataset: { shkgroup: "memory:work" } } : null }) });
    ctx.listeners.click({ target: target({}, { closest: (sel) =>
      sel === "[data-shkgroup]" ? { dataset: { shkgroup: "pending" } } : null }) });
    ctx.listeners.click({ target: target({}, { closest: (sel) =>
      sel === "[data-shkgroup]" ? { dataset: { shkgroup: "memory:you" } } : null }) });
    const h = ctx.shadowSettingsHtml();
    assert(/out of date/.test(h) && /ssknow expired/.test(h), "a dated line is flagged, not dropped");
    assert(/you said/.test(h), "a line in date says where it came from");
    assert(/data-shknowadd="memory:work"/.test(h), "the open group has its own add line");
    assert(/data-shknow="keep" data-shkid="know-p1"/.test(h), "a suggestion carries Keep");
    assert(/data-shknow="forget" data-shkid="know-p1"/.test(h), "and Drop");
    assert(/Asked: Which region\?/.test(h), "and where it came from");
    assert(!/class="ssownbody" hidden/.test(h), "own words open once they wrote some");
    assert.strictEqual(ctx.posts.length, 0, "opening writes nothing");
  }

  /* 3. Keep writes through the route and redraws from its answer */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = { knows: JSON.parse(JSON.stringify(KNOWS)) };
    ctx.listeners.click({ target: target({ shknow: "keep", shkid: "know-p1" }) });
    await settle();
    assert.strictEqual(ctx.posts.length, 1);
    assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.posts[0].body)),
      { action: "keep", id: "know-p1" });
    assert.strictEqual(ctx.S.shadowSettings.knows.pending, 0, "the page took the server's listing");
  }

  /* 3b. a switch is one click */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = { knows: JSON.parse(JSON.stringify(KNOWS)) };
    ctx.listeners.click({ target: target({ shswitch: "acting", shval: "just_do_it" }) });
    await settle();
    assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.posts[0].body)),
      { action: "switch", name: "acting", value: "just_do_it" });
  }

  /* 4. click a line to edit it; Enter saves, Escape abandons */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = { knows: JSON.parse(JSON.stringify(KNOWS)) };
    ctx.S.shadowKnowOpen = { "personality:rules": true };
    ctx.listeners.click({ target: target({ shknow: "open", shkid: "know-p2" }) });
    assert.strictEqual(ctx.posts.length, 0, "opening an edit writes nothing");
    const row = ctx.shadowKnowsGroupHtml(ctx.S.shadowSettings, "personality", "rules");
    assert(/data-shknowedit="know-p2"/.test(row), "the line is now an input");
    ctx.listeners.keydown({ key: "Enter", preventDefault(){},
      target: target({ shknowedit: "know-p2" }, { value: "Run the suite first" }) });
    await settle();
    assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.posts[0].body)),
      { action: "edit", id: "know-p2", text: "Run the suite first" });
    /* the blur that follows the redraw must not save a second time */
    ctx.listeners.change({ target: target({ shknowedit: "know-p2" }, { value: "x" }) });
    await settle();
    assert.strictEqual(ctx.posts.length, 1, "one edit, one write");

    ctx.listeners.click({ target: target({ shknow: "open", shkid: "know-p2" }) });
    ctx.listeners.keydown({ key: "Escape",
      target: target({ shknowedit: "know-p2" }, { value: "nope" }) });
    assert.strictEqual(ctx.S.shadowKnowEdit, null, "Escape closes the edit");
    assert.strictEqual(ctx.posts.length, 1, "and writes nothing");
  }

  /* 5. the add line files under its group; a refusal is shown in that group */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = { knows: JSON.parse(JSON.stringify(KNOWS)) };
    ctx.S.shadowKnowOpen = { "memory:work": true };
    const el = target({ shknowadd: "memory:work" }, { value: "  Uses Vercel " });
    ctx.listeners.keydown({ key: "Enter", preventDefault(){}, target: el });
    await settle();
    assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.posts[0].body)),
      { action: "add", section: "memory", text: "Uses Vercel", category: "work" });
    assert.strictEqual(el.value, "", "the line empties itself on submit");
    ctx.listeners.keydown({ key: "Enter", preventDefault(){},
      target: target({ shknowadd: "memory:work" }, { value: "key sk-abcdefghijklmnop" }) });
    await settle();
    assert(/credential/.test(ctx.shadowKnowsGroupHtml(ctx.S.shadowSettings, "memory", "work")),
      "the store's refusal is shown under the group");
  }

  /* 6. suggestions surface where the founder already is */
  {
    const ctx = fresh();
    ctx.S.shadowSettings = { knows: JSON.parse(JSON.stringify(KNOWS)) };
    /* ONLY ON THE TASK IT CAME FROM (founder, 2026-10-07: the card
       overflowed onto every other task) */
    ctx.S.shadowSettings.knows.personality[0].mission_id = "m-pricing";
    const mine = ctx.shadowPendingKnowsHtml({ id: "m-pricing" });
    assert(/Remember for next time: Pick regions yourself/.test(mine), "shown on its own task");
    assert(!/Run tests before done/.test(mine), "lines that already bind are not");
    assert.strictEqual(ctx.shadowPendingKnowsHtml({ id: "m-readme" }), "",
      "never on another task");
    assert.strictEqual(ctx.shadowPendingKnowsHtml(null), "",
      "nor where no task is in focus");
    ctx.S.shadowSettings.knows.personality[0].mission_id = null;
    assert(/Pick regions yourself/.test(ctx.shadowPendingKnowsHtml(null)),
      "a suggestion from a chat shows where no task is in focus");
    assert(/Pick regions yourself/.test(
      ctx.shadowPendingKnowsHtml({ id: "shc-1", conversation: true })),
      "a chat row counts as no task");
    assert.strictEqual(ctx.shadowPendingKnowsHtml({ id: "m-pricing" }), "",
      "and not on a task");
    ctx.S.shadowSettings = {};
    assert.strictEqual(ctx.shadowPendingKnowsHtml(null), "", "no settings yet: nothing drawn");
  }

  /* 7. a conversation row (Shadow answered, no worker) is a CHAT, in its own
     section, and its x deletes the conversation -- not a mission that does
     not exist (founder, 2026-10-07: "not able to delete") */
  {
    const ctx = fresh();
    ctx.S.shadowMissions = [];
    ctx.S.shadowConversations = [
      { id: "shc-aaa111", title: "Who has final say on Shadow?", mission_id: null },
      { id: "shc-bbb222", title: "Bound one", mission_id: "m-1" }];
    ctx.S.shadowThreads = { "shc-aaa111": [{ who: "founder", text: "x" }] };
    ctx.S.shadowTaskSel = "shc-aaa111"; ctx.S.shadowChat = "shc-aaa111";
    const rows = ctx.shadowTasks();
    assert.strictEqual(rows.length, 1, "only the unbound conversation is a row");
    assert.strictEqual(ctx.shadowTaskFaceFor(rows[0]).label, "CHAT");
    assert.strictEqual(ctx.shadowTaskSection(rows[0]), "chat");
    const list = ctx.shadowTaskListHtml();
    assert(/QUESTIONS/.test(list) && !/QUEUED/.test(list), "drawn under QUESTIONS, never QUEUED");
    /* founder order, 2026-10-08: Waiting on you, Running, Questions, Done, Archived */
    ctx.S.shadowMissions = [{ id: "m-done", objective: "Done one.", state: "done",
                              max_turns: 25, turns_used: 9 }];
    const both = ctx.shadowTaskListHtml();
    assert(both.indexOf("QUESTIONS") > -1 && both.indexOf(">DONE<") > -1
      && both.indexOf("QUESTIONS") < both.indexOf(">DONE<"),
      "QUESTIONS sits above DONE");
    assert(/Delete this chat/.test(list), "its x says what it does");

    const urls = [];
    ctx.fetch = async (url, opts) => { urls.push(url);
      return { ok: true, status: 200, json: async () => ({ deleted: true }) }; };
    await ctx.shadowDeleteTask("shc-aaa111");
    assert.deepStrictEqual(urls, ["/api/shadow/conversations/shc-aaa111/delete"],
      "the conversation route, and no mission action");
    assert.strictEqual(ctx.S.shadowConversations.length, 1, "the row is gone");
    assert(!ctx.S.shadowThreads["shc-aaa111"], "and its thread");
    assert.strictEqual(ctx.S.shadowTaskSel, null, "the focus does not point at it");
    assert.strictEqual(ctx.S.shadowChat, "global");
  }

  /* 8. FOCUS SURVIVES A REPAINT IN ANY FIELD (founder, 2026-10-07: "some
     textfields go out of focus even after I put the cursor there"). The
     restore names a field by its own data-* hooks, so Shadow's typed
     questions and the memory lines are found again without an allow-list. */
  {
    const render = fs.readFileSync(path.join(__dirname, "static", "js", "06-render.js"), "utf8");
    const src = /function _inputKeySelector\(el\)\{[\s\S]*?\n\}/.exec(render);
    assert(src, "_inputKeySelector exists in 06-render.js");
    const ctx = { Array };
    vm.createContext(ctx);
    vm.runInContext(src[0], ctx);
    const field = (tag, attrs, id) => ({ tagName: tag, id: id || "",
      attributes: Object.keys(attrs).map(n => ({ name: n, value: attrs[n] })) });
    assert.strictEqual(ctx._inputKeySelector(field("TEXTAREA",
        { "data-shivtext": "1", "data-shivmid": "m-1", "data-shivkey": "plan", "class": "x" })),
      'textarea[data-shivtext="1"][data-shivmid="m-1"][data-shivkey="plan"]',
      "a question's answer box is named by all three keys, not the first");
    assert.strictEqual(ctx._inputKeySelector(field("INPUT", { "data-shknowadd": "memory" })),
      'input[data-shknowadd="memory"]');
    assert.strictEqual(ctx._inputKeySelector(field("INPUT", { "data-x": 'a"b' })),
      'input[data-x="a\\"b"]', "a quote in a value cannot break the selector");
    assert.strictEqual(ctx._inputKeySelector(field("INPUT", {}, "q")), "#q");
    assert.strictEqual(ctx._inputKeySelector(field("INPUT", { "class": "x" })), null,
      "no hook, no restore -- as before");
    assert.strictEqual(ctx._inputKeySelector(field("BUTTON", { "data-x": "1" })), null);
    assert(/: _inputKeySelector\(act\)\)/.test(render),
      "the Shadow screen's own rebuild uses it too");
  }

  /* 9. a task the founder closed because there was nothing to do reads
     NOTHING TO DO under DONE -- never the red STOPPED (2026-10-07) */
  {
    const ctx = fresh();
    const m = { id: "m-ntd", state: "stopped", ended_by: "founder",
                end_reason: "nothing_to_do", objective: "Fix a typo" };
    assert.strictEqual(ctx.shadowTaskFaceFor(m).label, "NOTHING TO DO");
    assert.strictEqual(ctx.shadowTaskSection(m), "done");
    const plain = Object.assign({}, m, { end_reason: undefined });
    assert.strictEqual(ctx.shadowTaskFaceFor(plain).label, "STOPPED",
      "an ordinary stop is unchanged");
  }

  /* 10. rule 2: a switch suggestion is a Yes/No card -- in the suggestions
     line, and where no task is in focus; never on a task */
  {
    const ctx = fresh();
    const sug = { name: "acting", label: "Acting on its own", from: "balanced",
                  from_label: "Balanced", to: "just_do_it", to_label: "Just do it",
                  why: "You approved 3 held instructions without changing them.",
                  count: 3 };
    const d = JSON.parse(JSON.stringify(FIXTURE));
    d.knows = Object.assign(JSON.parse(JSON.stringify(KNOWS)),
                            { switch_suggestions: [sug] });
    ctx.S.shadowSettings = d;
    assert(/2 suggestions waiting/.test(ctx.shadowSettingsHtml()),
      "it joins the one suggestions line");
    ctx.S.shadowKnowOpen = { pending: true };
    const h = ctx.shadowSettingsHtml();
    assert(/Change to \u201cJust do it\u201d\?/.test(h) && /approved 3 held/.test(h));
    assert(/data-shswsug="acting"\s+data-shans="yes"/.test(h));
    assert(/Change to \u201cJust do it\u201d/.test(ctx.shadowPendingKnowsHtml(null)),
      "shown where no task is in focus");
    assert(!/Change to/.test(ctx.shadowPendingKnowsHtml({ id: "m-1" })),
      "never on a task");
    ctx.listeners.click({ target: target({ shswsug: "acting", shans: "no" }) });
    await settle();
    assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.posts[0].body)),
      { action: "switch_suggestion", name: "acting", answer: "no" });
  }

  console.log("test_shadow_knows.js: all passed");
})().catch((e) => { console.error(e); process.exit(1); });
