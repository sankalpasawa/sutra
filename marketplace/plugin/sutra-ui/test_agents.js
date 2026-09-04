#!/usr/bin/env node
/*
 * test_agents.js -- the Agents screen (static/js/17-agents.js), L1 + L2.
 *
 * L1 (projection): agStepsFromEvents / agRunSummary / agStageOf / agBlocks against
 * CAPTURED fixtures in tests/fixtures/ -- a real run's events.jsonl, and a block split
 * the Python splitter (seo_agent/editing/edit_block.py) produced for the same text.
 * The screen addresses an edit by block id, so the two splitters must agree exactly.
 *
 * L2 (rendered DOM): the HTML the real renderers emit -- escaping, the chosen radio,
 * the live card, the checkpoint footer -- with the module loaded under vm exactly as
 * the browser loads it, plus the smallest stubs that let it finish parsing.
 *
 * Run: node test_agents.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const SRC = fs.readFileSync(path.join(__dirname, "static", "js", "17-agents.js"), "utf8");
const EV = JSON.parse(fs.readFileSync(path.join(__dirname, "tests", "fixtures", "agents-events.json"), "utf8"));
const BLK = JSON.parse(fs.readFileSync(path.join(__dirname, "tests", "fixtures", "agents-blocks.json"), "utf8"));

/* the shell's globals the module reaches for, nothing more */
const ctx = {
  SCREENS: {}, TITLES: {}, S: {}, console,
  apiGet: async () => ({}), apiPost: async () => ({}),
  setTimeout, clearTimeout, setInterval, clearInterval, Date, JSON, Math, Number, String, Array, Object, RegExp, encodeURIComponent, isNaN,
};
vm.createContext(ctx);
vm.runInContext(SRC, ctx, { filename: "17-agents.js" });

let pass = 0, fail = 0;
function test(name, fn){
  try { fn(); pass++; console.log("ok   - " + name); }
  catch (e){ fail++; console.log("FAIL - " + name); console.log("       " + (e && e.message)); }
}
const A = ctx;

/* ── registration ──────────────────────────────────────────────────────────── */
test("registers SCREENS.agents and TITLES.agents", () => {
  assert.strictEqual(typeof A.SCREENS.agents, "function");
  assert.ok(Array.isArray(A.TITLES.agents) && A.TITLES.agents[0] === "Agents");
});
test("the screen shell is CONSTANT, so render() never repaints it under the mount", () => {
  const a = A.SCREENS.agents(), b = A.SCREENS.agents();
  assert.strictEqual(a, b);
  assert.ok(/id="agRoot"/.test(a));
});

/* ── L1: the block splitter agrees with Python byte for byte ───────────────── */
test("agBlocks splits exactly like edit_block.py (ids p0..pN line up)", () => {
  const got = A.agBlocks(BLK.md);
  assert.strictEqual(got.length, BLK.blocks.length, "block count");
  got.forEach((b, i) => assert.strictEqual(b, BLK.blocks[i], "block " + i + " differs"));
  assert.strictEqual(JSON.stringify(got.map((_, i) => "p" + i)), JSON.stringify(BLK.ids));
});
test("agBlocks keeps a fenced code block with a blank line inside as ONE block", () => {
  const md = "para\n\n```\na\n\nb\n```\n\ntail";
  const got = A.agBlocks(md);
  assert.strictEqual(got.length, 3);
  assert.ok(got[1].indexOf("a\n\nb") !== -1);
});

/* ── L1: events → entries, from a captured run ─────────────────────────────── */
test("substeps nest under the step that started them", () => {
  const out = A.agStepsFromEvents(EV.events, EV.state);
  const step = out.find(e => e.kind === "step" && e.tool === "suggest_topics");
  assert.ok(step, "the suggest_topics step exists");
  assert.ok(step.subs.length >= 4, "it carries its substeps, got " + step.subs.length);
  assert.ok(step.subs.some(s => /demo keyword data/i.test(s.label)), "the demo-data substep is on the step");
});
test("an approval that was answered shows its decision, not a live card", () => {
  const out = A.agStepsFromEvents(EV.events, EV.state);
  const ap = out.find(e => e.kind === "approval");
  assert.ok(ap, "approval entry");
  assert.strictEqual(ap.live, false);
  assert.strictEqual(ap.decision, "approved");
  assert.strictEqual(ap.mins, 4, "the time estimate rides along; there are no credits any more");
});
test("a step still running when the run FAILED is marked interrupted, never left spinning", () => {
  const evs = [{ t: "2026-09-03T08:00:00Z", type: "step_started", id: "s1", label: "Reading the website", tool: "index_site" }];
  const out = A.agStepsFromEvents(evs, { status: "failed" });
  assert.strictEqual(out[0].state, "bad");
  assert.ok(/interrupted/i.test(out[0].reason));
  const live = A.agStepsFromEvents(evs, { status: "running" });
  assert.strictEqual(live[0].state, "run");
});
test("the sentence the model wrote before a step becomes that step's body", () => {
  const evs = [
    { t: "2026-09-03T08:00:00Z", type: "message", text: "I'll read the site first." },
    { t: "2026-09-03T08:00:01Z", type: "step_started", id: "s1", label: "Reading the website", tool: "index_site" },
    { t: "2026-09-03T08:00:09Z", type: "step_finished", id: "s1", label: "Reading the website", ms: 8000, summary: "12 pages" },
  ];
  const out = A.agStepsFromEvents(evs, { status: "done" });
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].lead, "I'll read the site first.");
  assert.strictEqual(out[0].state, "ok");
  assert.strictEqual(out[0].ms, 8000);
});
test("a trailing message with no step after it is prose, not lost", () => {
  const evs = [{ t: "2026-09-03T08:00:00Z", type: "message", text: "Done. Six topics are ready." }];
  const out = A.agStepsFromEvents(evs, { status: "done" });
  assert.strictEqual(JSON.stringify(out.map(e => e.kind)), JSON.stringify(["prose"]));
});
test("a question pairs with its answer through call_id order", () => {
  const evs = [
    { t: "2026-09-03T08:00:00Z", type: "waiting", kind: "question", call_id: "c1", question: "Who is this for?", why: "Changes the keyword", options: [{ label: "Founders", recommended: true }, { label: "CFOs" }] },
    { t: "2026-09-03T08:00:05Z", type: "resumed", by: "user", answer: "Founders" },
  ];
  const out = A.agStepsFromEvents(evs, { status: "running" });
  assert.strictEqual(out[0].kind, "ask");
  assert.strictEqual(out[0].live, false);
  assert.strictEqual(out[0].answer, "Founders");
});
test("agRunSummary: live runs measure to now; finished runs measure to the last event", () => {
  const evs = [{ t: "2026-09-03T08:00:00Z", type: "step_started", id: "s1", label: "x" },
               { t: "2026-09-03T08:02:00Z", type: "step_finished", id: "s1", label: "x", ms: 1 }];
  const done = A.agRunSummary(evs, { status: "done", started_at: "2026-09-03T08:00:00Z", updated_at: "2026-09-03T08:02:00Z" });
  assert.strictEqual(done.live, false);
  assert.strictEqual(done.elapsedMs, 120000);
  assert.strictEqual(done.steps, 1);
  const now = Date.parse("2026-09-03T08:05:00Z");
  const live = A.agRunSummary(evs, { status: "running", started_at: "2026-09-03T08:00:00Z" }, now);
  assert.strictEqual(live.live, true);
  assert.strictEqual(live.elapsedMs, 300000);
});
test("agStageOf: earlier stages done, current marked, waiting marked", () => {
  const st = A.agStageOf({ stage: "blueprint", status: "waiting" });
  /* JSON, not deepStrictEqual: arrays born inside the vm context have another Array prototype */
  /* five stages since 2.240.0: Setup joined the front */
  assert.strictEqual(JSON.stringify(st.map(s => s.state)), JSON.stringify(["done", "done", "done", "wait", "todo"]));
  const done = A.agStageOf({ stage: "draft", status: "done" });
  assert.ok(done.every(s => s.state === "done"));
});
test("agDur never invents precision", () => {
  assert.strictEqual(A.agDur(400), "<1s");
  assert.strictEqual(A.agDur(8000), "8s");
  assert.strictEqual(A.agDur(72000), "1m 12s");
  assert.strictEqual(A.agDur(3660000), "1h 1m");
});

/* ── L2: rendered HTML ─────────────────────────────────────────────────────── */
test("agEsc escapes every character that could break out of text or an attribute", () => {
  assert.strictEqual(A.agEsc('<a href="x">&\'</a>'), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;");
});
test("a hostile step label never reaches the DOM unescaped", () => {
  const run = { run_id: "r1", status: "done", request: "<img src=x onerror=alert(1)>", started_at: "2026-09-03T08:00:00Z" };
  const evs = [{ t: "2026-09-03T08:00:00Z", type: "step_started", id: "s1", label: "<script>alert(1)</script>", tool: "x" },
               { t: "2026-09-03T08:00:01Z", type: "step_finished", id: "s1", label: "x", ms: 10 }];
  const html = A.agRunHtml(run, evs, {});
  assert.ok(html.indexOf("<script>") === -1, "script tag escaped");
  assert.ok(html.indexOf("<img") === -1, "img tag escaped");
  assert.ok(html.indexOf("&lt;script&gt;") !== -1);
});
test("the run header says Working while live and Worked when done, with the step count", () => {
  const evs = EV.events;
  const liveHtml = A.agRunHtml(Object.assign({}, EV.state, { status: "running" }), evs, { now: Date.now() });
  assert.ok(/Working/.test(liveHtml) && /runstrip live/.test(liveHtml));
  const doneHtml = A.agRunHtml(Object.assign({}, EV.state, { status: "done" }), evs, {});
  assert.ok(/Worked/.test(doneHtml));
  assert.ok(/<span class="n">1<\/span>/.test(doneHtml), "one step_started in the fixture");
});
test("a live approval card renders Go ahead / Not now; an answered one renders the decision", () => {
  const live = A.agEntryHtml({ kind: "approval", live: true, tool: "run_research", question: "Research will take a while. Go ahead?", mins: 12, options: [] }, {});
  assert.ok(/data-ag="approve" data-arg="yes"/.test(live) && /Not now/.test(live));
  assert.ok(/<b>12<\/b> min/.test(live), "the time is stated");
  assert.ok(!/credit/i.test(live), "credits are gone from the screen");
  const done = A.agEntryHtml({ kind: "approval", live: false, decision: "declined", question: "q", options: [] }, {});
  assert.ok(/You said/.test(done) && /Not now/.test(done));
  assert.ok(!/data-ag="approve"/.test(done), "no buttons after the fact");
});
test("topic cards: the picked one is the checked radio, volumes are labelled demo when the data says so", () => {
  const data = { competitor: "rival.com", demo: true, topics: [
    { id: "t1", topic: "One", angle: "a", est_volume: 2900, est_difficulty: 34 },
    { id: "t2", topic: "Two <b>bold</b>", angle: "b" }] };
  const html = A.agTopicListHtml(data, "t2");
  assert.ok(/data-arg="t1"[^>]*/.test(html));
  assert.ok(/aria-checked="false" data-ag="pick" data-arg="t1"/.test(html));
  assert.ok(/aria-checked="true" data-ag="pick" data-arg="t2"/.test(html));
  assert.ok(html.indexOf("<b>bold</b>") === -1 && html.indexOf("&lt;b&gt;bold") !== -1);
  assert.ok(/p-warn">2,900\/mo/.test(html), "demo volume wears the warn pill");
});
test("the review panel footer offers Use this topic only once a topic is picked", () => {
  const S = A.S; S.ag = null;
  const a = A.agS();
  a.chatId = "c1";
  a.chat = { runs: [{ run_id: "r1", status: "waiting", waiting_on: { kind: "artifact", artifact: "topics.json", view: "topic_list" } }] };
  a.panel = { run_id: "r1", name: "topics.json", view: "topic_list", data: { topics: [{ id: "t1", topic: "One" }] }, loading: false };
  a.picked = null;
  let html = A.agPanelHtml(a);
  assert.ok(/data-ag="usetopic" disabled/.test(html), "disabled without a pick");
  a.picked = "t1";
  html = A.agPanelHtml(a);
  assert.ok(/data-ag="usetopic" >Use this topic/.test(html.replace(/\s+>/g, " >")), "enabled with a pick");
});
test("the article view addresses blocks by the same ids the server uses", () => {
  const html = A.agArticleHtml(BLK.md, null, null, false);
  BLK.ids.forEach(id => assert.ok(html.indexOf('data-blk="' + id + '"') !== -1, "block " + id + " rendered"));
  assert.ok(/data-ag="artedit" data-arg="p0"/.test(html));
});
test("a library item opens read-only: no edit affordance, copy only", () => {
  const S = A.S; S.ag = null;
  const a = A.agS();
  a.panel = { run_id: "r1", name: "draft.md", view: "article", data: { text: "# T\n\nbody" }, loading: false, readOnly: true, title: "Saved one" };
  const html = A.agPanelHtml(a);
  assert.ok(!/data-ag="artedit"/.test(html));
  assert.ok(/data-ag="copymd"/.test(html));
  assert.ok(/Saved one/.test(html));
});
test("the log groups its rows by stage, one line each, and only the running one is open", () => {
  const evs = [
    { t: 1, type: "message", text: "Setting up first." },
    { t: 2, type: "step_started", id: "s1", label: "Reading the website", tool: "index_site", stage: "setup" },
    { t: 3, type: "substep_finished", parent: "s1", label: "Opened the site", note: "https://x.com" },
    { t: 4, type: "step_finished", id: "s1", ms: 120000, summary: "400 pages catalogued" },
    { t: 5, type: "step_started", id: "s2", label: "Researching the topic", tool: "run_research", stage: "research" },
  ];
  const entries = A.agStepsFromEvents(evs, { status: "running" });
  assert(entries.every(e => "stage" in e), "every row carries a stage");
  assert(entries.find(e => e.id === "s1").stage === "setup", "the setup step is in setup");
  assert(entries.find(e => e.id === "s2").stage === "research", "the research step is in research");
  // the sentence before a step is that step's body, so it lands in the step's own stage
  assert(entries.length === 2 && entries[0].lead === "Setting up first.", "the lead was consumed");

  const groups = A.agStageGroups(entries);
  assert(groups.length === 2, "one group per stage: " + groups.length);
  assert(groups[0].stage === "setup" && groups[1].stage === "research", "in the order they happened");
  assert(groups[0].label === "Setup" && groups[1].label === "Research", "each group is named in plain English");
  assert(groups[0].steps === 1 && groups[0].ms === 120000, "a shut stage knows its step count and time");
  assert(groups[0].summary === "400 pages catalogued", "and carries the last summary as its one line");
  assert(groups[0].live === false && groups[1].live === true, "only the unfinished stage is live");

  const html = A.agRunHtml({ run_id: "r1", status: "running", request: "go" }, evs, {});
  const heads = html.match(/class="ag-stagehead/g) || [];
  assert(heads.length === 2, "one clickable head per named stage: " + heads.length);
  assert(html.indexOf("<b>Setup</b>") !== -1 && html.indexOf("<b>Research</b>") !== -1, "named on screen");
  const bodies = html.match(/class="ag-stagebody" hidden/g) || [];
  assert(bodies.length === 1, "the finished stage is shut and the running one is open: " + bodies.length);
  assert(html.indexOf("400 pages catalogued") !== -1, "the shut stage still shows its one-line summary");
});

test("a stage the user opened stays open, and its rows come back", () => {
  const evs = [
    { t: 1, type: "step_started", id: "s1", label: "Reading the website", tool: "index_site", stage: "setup" },
    { t: 2, type: "substep_finished", parent: "s1", label: "Opened the site", note: "https://x.com" },
    { t: 3, type: "step_finished", id: "s1", ms: 1000, summary: "done" },
    { t: 4, type: "step_started", id: "s2", label: "Researching", tool: "run_research", stage: "research" },
  ];
  const shut = A.agRunHtml({ run_id: "r1", status: "running" }, evs, {});
  assert(shut.indexOf("Opened the site") === -1 || /ag-stagebody" hidden/.test(shut), "shut by default");
  const open = A.agRunHtml({ run_id: "r1", status: "running" }, evs, { stageOpen: { "r1:setup": true } });
  assert(open.indexOf("Opened the site") !== -1, "opening the stage shows its substeps");
  assert((open.match(/class="ag-stagebody" hidden/g) || []).length === 0, "nothing hidden once both are open");
});

test("the stage bar names five stages and says what the run is doing, never a credit", () => {
  const html = A.agStagesHtml({ stage: "research", status: "running", credits_spent: 11 });
  assert.strictEqual((html.match(/class="ag-stage /g) || []).length, 5);
  assert.ok(/Setup/.test(html) && /Draft/.test(html));
  assert.ok(/>working</.test(html));
  assert.ok(!/credit/i.test(html), "no credit talk on the stage bar");
  assert.ok(/waiting for you/.test(A.agStagesHtml({ stage: "topic", status: "waiting" })));
});
test("the hero says plainly when there is no model, no DataForSEO and no Voyage key", () => {
  const html = A.agHeroHtml({ model_provider: null, dataforseo: false, voyage: false });
  assert.ok(/No model is available/.test(html));
  assert.ok(/DataForSEO is not connected/.test(html));
  assert.ok(/No Voyage key/.test(html));
  const ok = A.agHeroHtml({ model_provider: "claude-cli", dataforseo: true, voyage: true, site_indexed: true, page_index: { built: true }, brand_ready: true });
  assert.ok(!/No model/.test(ok) && !/not connected/.test(ok) && !/No Voyage/.test(ok));
  assert.ok(/Suggest six topics/.test(ok), "a set-up site offers the article plays");
  const fresh = A.agHeroHtml({ model_provider: "claude-cli", dataforseo: true, voyage: true, site_indexed: false, page_index: { built: false }, brand_ready: false });
  assert.ok(/Set up for my website/.test(fresh), "a fresh install offers setup first");
});
test("agSetupOf: the index is a soft step without a Voyage key, so setup can still be ready", () => {
  const s = A.agSetupOf({ model_provider: "claude-cli", site_indexed: true, voyage: false, page_index: { built: false }, brand_ready: true });
  assert.strictEqual(s.ready, true);
  const t = A.agSetupOf({ model_provider: "claude-cli", site_indexed: false, voyage: true, page_index: { built: false }, brand_ready: false });
  assert.strictEqual(t.ready, false); assert.strictEqual(t.next, "site");
});
test("connections shows Voyage as its own section and never the key", () => {
  const html = A.agConnectionsHtml({ dataforseo_login: true, dataforseo_password: true, voyage_key: true }, { model_provider: "claude-cli" }, null);
  assert.ok(/Voyage/.test(html) && /data-agvoy="key"/.test(html));
  assert.ok(/data-ag="clearvoy"/.test(html), "a set key can be disconnected");
  assert.ok(!/pa-[A-Za-z0-9]{10}/.test(html));
});
test("the tools screen is plain English: what, when, needs, how long", () => {
  const html = A.agToolsHtml([{ name: "index_site", label: "Reading the website", does: "Reads the whole website.", when: "Once, at setup.", needs: "The website address.", takes: "A few minutes." }]);
  assert.ok(/What it does/.test(html) && /When it runs/.test(html) && /What it needs/.test(html) && /How long/.test(html));
  assert.ok(/Reading the website/.test(html));
  assert.ok(!/gate|credit|module/i.test(html));
});
test("the brand pack lists every file with its purpose and flags the rows to confirm", () => {
  const html = A.agBrandPackHtml({ files: [{ name: "writer-brief.md", exists: true, words: 1660, flags: 0 }, { name: "stats.md", exists: true, words: 400, flags: 12 }], needs_review: ["stats.md: 12 rows to confirm"] });
  assert.ok(/Writer brief/.test(html) && /1,660 words/.test(html));
  assert.ok(/12 to confirm/.test(html));
  assert.ok(/data-ag="brandfile" data-arg="stats.md"/.test(html));
  assert.ok(/not built yet/.test(html), "unbuilt files are listed so the user knows what is coming");
});
test("the links block shows each placed link with its match score and flags a weak one", () => {
  const html = A.agLinksHtml({ placed: [{ kind: "inline", anchor: "cost per hire", url: "https://x.com/hr-glossary/cost-per-hire/", section: "S1", rr: 0.95 },
                                          { kind: "inline", anchor: "work sample", url: "https://x.com/blog/ws/", section: "S2", rr: 0.31 }], external_kept: [], integrity_clean: true });
  assert.ok(/cost per hire/.test(html) && /match 0\.95/.test(html));
  assert.ok(/match 0\.31 · weak/.test(html), "under 0.45 is flagged weak, the engine's own threshold");
  assert.ok(!/put back exactly/.test(html));
});
test("the research brief shows the world check, the shared-phrase warning and the cannibalisation flag", () => {
  const html = A.agResearchHtml({ topic: "Cost per hire", keywords: { primary: { keyword: "cost per hire", volume: 2900, kd: 31, intent: "informational", split_world: true, why: "part of the volume is finance" }, variations: [{ keyword: "cph", volume: 100 }], secondary: [] },
    world: { about: "hiring costs", not_about: "cost of goods" }, cannibalisation: { keyword: "cost per hire", rank: 4, url: "https://x.com/hr-glossary/cph/" }, serp: { who_ranks: [{ rank: 1, url: "https://a.com/x", title: "A" }] }, winners: { gaps_to_own: ["the hidden costs"] } });
  assert.ok(/Shared phrase/.test(html) && /You already rank for this/.test(html));
  assert.ok(/About<\/dt><dd>hiring costs/.test(html));
  assert.ok(/The gap we can own/.test(html) && /the hidden costs/.test(html));
  assert.ok(/2,900/.test(html));
});
test("connections never echoes a secret: inputs are empty, placeholders say (set)", () => {
  const html = A.agConnectionsHtml({ dataforseo_login: true, dataforseo_password: true }, { model_provider: "claude-cli" }, null);
  assert.ok(/placeholder="•••••• \(set\)"/.test(html));
  assert.ok(/value=""/.test(html));
  assert.ok(/Disconnect/.test(html));
});

console.log("\n" + "-".repeat(60));
console.log("agents screen: " + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
