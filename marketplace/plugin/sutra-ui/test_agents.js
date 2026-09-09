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
test("a read-only article never offers the per-block editor, and a Library one offers Edit", () => {
  const S = A.S; S.ag = null;
  const a = A.agS();
  a.panel = { run_id: "r1", name: "draft.md", view: "article", data: { text: "# T\n\nbody" }, loading: false, readOnly: true, title: "Saved one" };
  let html = A.agPanelHtml(a);
  assert.ok(!/data-ag="artedit"/.test(html), "no per-block editor on a read-only draft");
  assert.ok(/data-ag="copymd"/.test(html));
  assert.ok(/Saved one/.test(html));
  assert.ok(!/data-ag="libedit"/.test(html), "an artifact with no library id offers no Edit");
  a.panel.libId = "lib7";
  html = A.agPanelHtml(a);
  assert.ok(/data-ag="libedit" data-arg="lib7"/.test(html), "a saved article does");
  assert.ok(/data-ag="copymd"/.test(html), "and can still be copied");
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

test("the research brief lists who researched it and every step's own file", () => {
  const r = {
    topic: "Cost per hire", keywords: { primary: { keyword: "cost per hire", volume: 210, kd: 7 } },
    evidence: { cards: 483, questions: 16, searches: 48, dossier_words: 14856,
                team: [{ role: "The Builder", focus: "how it is done" },
                       { role: "The Sceptic", focus: "what it costs" }],
                turns: [{ persona: "The Builder", question: "Which hires count toward the denominator?" }] },
  };
  A.S.ag.trail = [{ file: "curate.json", label: "The research conversation", note: "every question asked", bytes: 91234 },
                  { file: "winners.json", label: "What the winners cover", note: "their common headings", bytes: 4096 }];
  A.S.ag.workOpen = null;
  const html = A.agResearchHtml(r);
  assert(html.indexOf("Who researched this") !== -1, "the team has its own block");
  assert(html.indexOf("The Builder") !== -1 && html.indexOf("The Sceptic") !== -1, "every researcher is named");
  assert(/2 researchers asked 16 questions across 48 searches/.test(html), "and what they did: " + html.slice(html.indexOf("researchers") - 40, html.indexOf("researchers") + 80));
  assert(html.indexOf("14,856-word dossier") !== -1, "the dossier is named with its size");
  assert(html.indexOf("Which hires count toward the denominator?") !== -1, "a real question is shown");

  assert(html.indexOf("The evidence trail") !== -1, "the trail has its own block");
  assert(html.indexOf("The research conversation") !== -1 && html.indexOf("What the winners cover") !== -1,
         "each file is named in plain English, never by filename alone");
  assert(html.indexOf('data-ag="work" data-arg="curate.json"') !== -1, "and each row is clickable");
  assert(html.indexOf("89 KB") !== -1, "sizes are human: " + (html.match(/\d+ [KM]?B/g) || []).join(","));

  A.S.ag.workOpen = { label: "What the winners cover", data: { gaps_to_own: ["the formula"] } };
  const open = A.agResearchHtml(r);
  assert(open.indexOf("gaps_to_own") !== -1, "an opened file shows its real content");
  assert(open.indexOf('data-ag="workclose"') !== -1, "and can be closed");
  A.S.ag.trail = []; A.S.ag.workOpen = null;
  assert(A.agResearchHtml(r).indexOf("The evidence trail") === -1, "no trail, no block");
});

test("a brief from before the research team shows no team block and never breaks", () => {
  A.S.ag.trail = []; A.S.ag.workOpen = null;
  const html = A.agResearchHtml({ topic: "Old run", primary_keyword: { keyword: "x" }, evidence_count: 12 });
  assert(html.indexOf("Who researched this") === -1, "no team, no block");
  assert(html.indexOf("Old run") !== -1 || html.indexOf("x") !== -1, "the old brief still renders");
});

test("Knowledge offers a check for changes and a traffic import, and never a chat log", () => {
  const k = { site_index: { domain: "x.com", page_count: 100, pages: [] }, report: {}, brand: { files: [] } };
  A.S.ag.refresh = null; A.S.ag.trafficForm = null;
  const html = A.agKnowledgeHtml(k, A.S.ag);
  assert(html.indexOf('data-ag="refreshcheck"') !== -1, "a check button");
  assert(html.indexOf('data-ag="trafficimport"') !== -1, "and an import button");
  assert(/only what is new or has changed/.test(html), "and says it does not re-read the site");
});

test("a refresh shows ONE line while it works, then what it found, then what changed", () => {
  const a = A.S.ag;
  a.refresh = { busy: true, step: "Asking the site for its current list…" };
  let h = A.agRefreshHtml(a);
  assert(/class="spin"/.test(h) && h.indexOf("Asking the site") !== -1, "one line and a spinner");
  assert((h.match(/class="msg"/g) || []).length === 1, "exactly one line, never a log");

  a.refresh = { preview: { new: 37, gone: 4, changed: 112, unchecked: 900 } };
  h = A.agRefreshHtml(a);
  assert(/37 new/.test(h) && /4 gone/.test(h) && /112 rewritten/.test(h), "the counts: " + h.slice(0, 160));
  assert(/900 pages give no date/.test(h), "and says what it could not check");
  assert(h.indexOf('data-ag="refreshgo"') !== -1, "nothing happens until you say go");

  a.refresh = { preview: { new: 0, gone: 0, changed: 0, unchecked: 0 } };
  h = A.agRefreshHtml(a);
  assert(/Nothing has changed/.test(h) && h.indexOf('data-ag="refreshgo"') === -1,
         "with nothing to do there is nothing to press");

  a.refresh = { done: "584 pages added, 0 removed." };
  h = A.agRefreshHtml(a);
  assert(/Done\./.test(h) && h.indexOf('data-ag="refreshchanges"') !== -1, "done, and a way to read it");

  a.refresh = { error: "The site refused every page." };
  h = A.agRefreshHtml(a);
  assert(/refused every page/.test(h) && /class="msg err"/.test(h), "a failure says so plainly");
  a.refresh = null;
});

test("the traffic import asks for a path and never invents a figure", () => {
  const a = A.S.ag;
  a.refresh = null; a.trafficForm = { path: "" };
  const h = A.agRefreshHtml(a);
  assert(h.indexOf("data-agtraffic") !== -1, "a path box");
  assert(/page address column and a traffic column/.test(h), "and says what the file must have");
  assert(h.indexOf('data-ag="trafficgo"') !== -1 && h.indexOf('data-ag="trafficcancel"') !== -1, "import or cancel");
  a.trafficForm = null;
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
test("the brand pack lists every file with its purpose, and never nags about confirming one", () => {
  const html = A.agBrandPackHtml({ files: [{ name: "writer-brief.md", exists: true, words: 1660, flags: 0 }, { name: "stats.md", exists: true, words: 400, flags: 12 }], needs_review: ["stats.md: 12 rows to confirm"] });
  assert.ok(/Writer brief/.test(html) && /1,660 words/.test(html));
  assert.ok(/data-ag="brandfile" data-arg="stats.md"/.test(html));
  assert.ok(/not built yet/.test(html), "unbuilt files are listed so the user knows what is coming");
  assert.ok(!/\d+ to confirm/.test(html), "no N-to-confirm pill anywhere");
  assert.ok(!/Confirm these before they are used/.test(html), "and no yellow banner");
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


/* ── the Knowledge tab, rebuilt: a quiet document ──────────────────────────── */
const KIDX = { domain: "testlify.com", page_count: 12318, ranking_pages: 2188, ok_pages: 12287,
               indexed_at: new Date(Date.now() - 3600000).toISOString(), has_traffic: true,
               types: { "test-library": 8000, "hr-glossary": 900 },
               type_names: { "test-library": "Test library", "hr-glossary": "HR glossary" },
               languages: { de: 412, ja: 88 }, language_names: { de: "German", ja: "Japanese" } };
const KBRAND = { brand: "Testlify",
  brief: { exists: true, words: 1660, text: "## How we sound\n\nPlain, specific, never breathless." },
  built_from: [{ name: "brand-voice.md", label: "Brand voice", note: "How the brand sounds.", exists: true, words: 900 },
               { name: "writer-brief-rulings.md", label: "Rulings", note: "Decisions that outrank the rest.", exists: false, words: 0 }],
  extras: [{ name: "voices.md", label: "Who writes", note: "Who signs the writing.", exists: true, words: 120, in_use: false }],
  cta: { count: 2 } };
function kdoc(over){
  return Object.assign({ site_index: KIDX, report: { gates: [] }, page_index: { built: true, pages: 12318 },
                         company: { brand: "Testlify", language_code: "en" }, brand: KBRAND, competitors: [] }, over || {});
}
function agReset(){
  const a = A.agS();
  a.pages = null; a.pageQ = ""; a.pageType = ""; a.pageLang = null; a.map = null; a.mapOn = false;
  a.libEdit = null; a.knowledge = null;
  a.refresh = null; a.trafficForm = null; a.compForm = null; a.coForm = null;
  a.cta = null; a.ctaForm = null; a.detailOpen = {}; a.panel = null;
  return a;
}

test("the four gate chips are gone from the screen, whatever the report still carries", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(kdoc({ report: { gates: [
    { name: "enumeration accounting", pass: true, detail: "every url accounted for" },
    { name: "response integrity", pass: false, detail: "" },
    { name: "extraction coverage", pass: true, detail: "" },
    { name: "traffic check", pass: true, detail: "" }] }, confidence: "full: enumeration accounting passed" }), a);
  assert.ok(!/ag-check/.test(html), "no chips are drawn");
  assert.ok(!/enumeration|accounting|response integrity|extraction|coverage/i.test(html),
            "and none of those words reach the screen");
});

test("the catalogue line is one sentence, and says so plainly when traffic is not connected", () => {
  const a = agReset();
  const on = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(on.indexOf("12,318 pages · 2,188 rank for something · 12,287 with full text · read an hour ago") !== -1,
            "the line the owner kept: " + (on.match(/12,318 pages[^<]*/) || [""])[0]);
  const off = A.agKnowledgeHtml(kdoc({ site_index: Object.assign({}, KIDX, { has_traffic: false, ranking_pages: 0 }) }), a);
  assert.ok(off.indexOf("12,318 pages · 12,287 with full text · read an hour ago · search traffic not connected yet") !== -1,
            "no traffic, no zero: " + (off.match(/12,318 pages[^<]*/) || [""])[0]);
  assert.ok(!/0 pages rank|0 rank for something/.test(off), "never a zero dressed up as a count");
});

test("the meaning-index section is gone; its one good sentence is the map's caption", () => {
  const a = agReset();
  let html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(!/Pages indexed by meaning|Page index/.test(html), "the section is gone");
  assert.ok(!/passages|vectors|embedding/i.test(html), "and its vocabulary with it");
  assert.ok(!/ag-mapcap/.test(html), "no caption while the map is shut");
  assert.ok(/data-ag="map"/.test(html) && /ag-secctl/.test(html), "the map button moved to the heading row");
  a.mapOn = true;
  html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(/id="agMap"/.test(html), "the canvas is the same canvas");
  assert.ok(html.indexOf("pages that mean similar things sit close together, hover to read, click to open") !== -1,
            "the sentence became the caption");
  a.mapOn = false;
});

test("the catalogue's controls sit on its heading row, not in its body", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(kdoc(), a);
  const head = html.slice(html.indexOf("The site catalogue"), html.indexOf("The site catalogue") + 700);
  assert.ok(/data-ag="refreshcheck"/.test(head), "check for changes is on the heading row");
  assert.ok(/data-ag="trafficimport"/.test(head), "so is the traffic import");
  assert.ok(/data-ag="map"/.test(head), "and the map");
  assert.ok(/only what is new or has changed/.test(html), "it still says it does not re-read the site");
});

test("the type filter carries real type names, and the languages are their OWN filter", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(kdoc(), a);
  const type = html.slice(html.indexOf("data-agpagetype"), html.indexOf("data-agpagelang"));
  assert.ok(/>Test library</.test(type) && /value="test-library"/.test(type), "a real name, not the slug");
  assert.ok(!/>de</.test(type) && !/>ja</.test(type), "no language codes in the type list");
  const lang = html.slice(html.indexOf("data-agpagelang"));
  assert.ok(/value="de"[^>]*>German</.test(lang), "German, not de: " + lang.slice(0, 200));
  assert.ok(/value="ja"[^>]*>Japanese</.test(lang));
  assert.ok(html.indexOf("data-agpagetype") < html.indexOf("data-agpagelang"), "language comes after type");
  const none = A.agKnowledgeHtml(kdoc({ site_index: Object.assign({}, KIDX, { languages: {} }) }), a);
  assert.ok(!/data-agpagelang/.test(none), "one language, no filter");
});

test("the page table asks the server for FIVE rows, and passes the language filter", () => {
  const a = agReset(); const seen = [];
  const prev = A.apiGet;
  A.apiGet = async (p) => { seen.push(p); return { total: 0, offset: 0, rows: [] }; };
  a.pageType = "hr-glossary"; a.pageLang = "de";
  A.agLoadPages(0);
  A.apiGet = prev;
  assert.strictEqual(seen.length, 1, "one call");
  assert.ok(/[?&]limit=5(&|$)/.test(seen[0]), "five rows, not twenty-five: " + seen[0]);
  assert.ok(/[?&]lang=de(&|$)/.test(seen[0]), "the language rides along: " + seen[0]);
  assert.ok(/[?&]type=hr-glossary(&|$)/.test(seen[0]), "and the type still does");
  a.pageType = ""; a.pageLang = "";
});

test("the pager steps by five, so page two starts at row six", () => {
  const a = agReset(); const seen = [];
  a.pages = { total: 40, offset: 0, rows: [] };
  const prev = A.apiGet;
  A.apiGet = async (p) => { seen.push(p); return { total: 40, offset: 5, rows: [] }; };
  A.agAction("pagesnext", { getAttribute: () => "" });
  A.apiGet = prev;
  assert.ok(/offset=5(&|$)/.test(seen[0]), "next asks for row six: " + seen[0]);
  a.pages = null;
});

test("the writer brief is on the page in full, with the files it was built from behind one door", () => {
  const a = agReset();
  let html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(/<h3 class="sec">The writer brief<\/h3>/.test(html), "its own section");
  assert.ok(html.indexOf("This is what the writer reads before writing an article about Testlify.") !== -1,
            "the one line above it");
  assert.ok(/class="ag-brief"/.test(html) && /never breathless/.test(html), "the brief itself, rendered");
  assert.ok(/data-ag="detail" data-arg="builtfrom"/.test(html) && /See how this was built/.test(html), "and the door");
  assert.ok(/aria-expanded="false"/.test(html.slice(html.indexOf("builtfrom") - 120, html.indexOf("builtfrom") + 60)));
  const shut = A.agBriefHtml(KBRAND, false);
  /* Was "no brandfile button at all" until 2026-09-09, when Open joined the heading row and became
     a brandfile button too. What must stay true is that the door is shut: none of the files the
     brief was built from are on screen. */
  assert.ok(!/brand-voice\.md|writer-brief-rulings\.md/.test(shut), "shut, the brief shows none of the files it was built from");
  assert.ok(!/ag-file/.test(shut), "and no file list either");

  a.detailOpen = { builtfrom: true };
  html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(/data-ag="brandfile" data-arg="brand-voice.md" data-label="Brand voice"/.test(html), "open, each file is clickable");
  assert.ok(/Rulings/.test(html) && /ag-file off/.test(html) && /not written yet/.test(html), "a missing one is greyed, not hidden");
  assert.ok(!/company\.json|page-shortlist|type-roles|stats\.md|stories\.md/.test(html),
            "and ONLY the files the brief was built from");
  a.detailOpen = {};
});

test("the brief box is short, and Open puts the whole file in the side panel", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(kdoc(), a);
  const ctl = html.slice(html.indexOf('<h3 class="sec">The writer brief</h3>'));
  const row = ctl.slice(ctl.indexOf('<div class="ag-secctl">'), ctl.indexOf('class="ag-brief"'));
  assert.ok(/data-ag="brandfile" data-arg="writer-brief\.md"/.test(row), "Open opens writer-brief.md by the route the other files use");
  assert.ok(/>Open</.test(row), "and it is called Open");
  assert.ok(/data-ag="detail" data-arg="builtfrom"/.test(row), "it sits beside See how this was built, on one control row");
  assert.ok(row.indexOf('data-arg="writer-brief.md"') < row.indexOf('data-arg="builtfrom"'), "Open comes first");
  /* The control belongs to the heading row, not inside the box you scroll. Before 2026-09-09
     the only door was below the sub line; a control inside the brief scrolls away with it. */
  const box = html.slice(html.indexOf('class="ag-brief"'));
  assert.ok(!/data-arg="writer-brief\.md"/.test(box), "Open is not inside the brief box");
  assert.ok(/<div class="ag-sechead"><h3 class="sec">The writer brief<\/h3>/.test(html),
            "the brief uses the same heading idiom as the site catalogue");
  assert.ok(!/ag-briefhead/.test(html), "and the old one-off heading row is gone");
});

test("the brief that is not written yet still gets its heading, and no Open", () => {
  const none = A.agBriefHtml({ brand: "Testlify", brief: { exists: false } }, false);
  assert.ok(/<h3 class="sec">The writer brief<\/h3>/.test(none), "the section is still named");
  assert.ok(!/data-ag="brandfile"/.test(none), "nothing to open");
  assert.ok(/Not written yet/.test(none));
});

test("who writes is one file, and says it is not in use yet", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(/<h3 class="sec">Who writes<\/h3>/.test(html), "its label is the heading, and is not repeated in the row");
  assert.ok((html.match(/>Who writes</g) || []).length === 1, "said once on screen, never repeated in the row");
  assert.ok(/Who signs the writing\./.test(html), "the row says what the file is");
  assert.ok(/not in use yet/.test(html) && /data-arg="voices.md"/.test(html));
  const none = A.agKnowledgeHtml(kdoc({ brand: Object.assign({}, KBRAND, { extras: [] }) }), a);
  assert.ok(!/Who writes/.test(none), "nothing to show, no heading");
});

test("the nineteen tiles and the yellow banner are gone from Knowledge", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(!/The brand pack/.test(html), "no brand-pack section");
  assert.ok(!/note w/.test(html) && !/Confirm these before they are used/.test(html), "no yellow banner");
  assert.ok(!/\d+ to confirm/.test(html), "no N-to-confirm pill");
});

test("the pages a close may point at: what the crawl found, and what the owner added", () => {
  const a = agReset();
  a.cta = { domain: "testlify.com", rows: [
    { url: "https://testlify.com/pricing/", note: "when price is the question", title: "Pricing", mine: false },
    { url: "https://testlify.com/demo/", note: "", title: "", mine: true }] };
  const html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(/<h3 class="sec">Links the close may point at<\/h3>/.test(html));
  assert.ok(/value="https:\/\/testlify.com\/pricing\/"/.test(html), "the address is editable");
  assert.ok(/value="when price is the question"/.test(html), "so is the note");
  assert.ok(/class="ag-ctarow"/.test(html) && /class="ag-ctarow mine"/.test(html), "his rows look different from the crawl's");
  assert.ok(/>suggested</.test(html) && /"ag-ctasrc">yours</.test(html), "and say which is which");
  assert.ok(/data-ag="ctaadd"/.test(html) && /data-ag="ctadel" data-arg="1"/.test(html) && /data-ag="ctasave"/.test(html),
            "add, remove, save");
  const empty = (function(){ const b = agReset(); b.cta = { domain: "testlify.com", rows: [] };
    return A.agKnowledgeHtml(kdoc(), b); })();
  assert.ok(/No pages yet/.test(empty) && /data-ag="ctaadd"/.test(empty), "an empty list still offers a row");
});

test("adding and removing a link edits the draft, never the saved list", () => {
  const a = agReset();
  a.cta = { domain: "testlify.com", rows: [{ url: "https://testlify.com/pricing/", note: "n", mine: false }] };
  A.agAction("ctaadd", { getAttribute: () => "" });
  assert.strictEqual(a.ctaForm.rows.length, 2, "a blank row appears");
  assert.strictEqual(a.ctaForm.rows[1].mine, true, "and it is his");
  assert.strictEqual(a.cta.rows.length, 1, "the saved list has not moved");
  A.agAction("ctadel", { getAttribute: k => k === "data-arg" ? "0" : "" });
  assert.strictEqual(a.ctaForm.rows.length, 1);
  assert.strictEqual(a.ctaForm.rows[0].url, "", "the right row went");
  assert.strictEqual(a.cta.rows.length, 1, "still not the saved list");
});

test("the tab still draws against the payload the server sends TODAY, mid-rebuild", () => {
  const a = agReset();
  /* no has_traffic, no languages, no type_names, and the old brand pack shape */
  const old = { site_index: { domain: "testlify.com", page_count: 12318, ranking_pages: 2188, ok_pages: 12287, types: { "test-library": 8000 } },
                report: null, page_index: { built: false, pages: 0, chunks: 0 }, company: { brand: "Testlify" },
                brand: { files: [{ name: "company.json", exists: false, words: 1, flags: 1 }] }, competitors: [] };
  const html = A.agKnowledgeHtml(old, a);
  assert.ok(html.indexOf("12,318 pages · 2,188 rank for something · 12,287 with full text") !== -1,
            "the line still reads, with no indexed_at to date it");
  assert.ok(!/data-agpagelang/.test(html), "no languages, no language filter");
  assert.ok(!/data-ag="map"/.test(html), "no page index, no map button");
  assert.ok(/Not written yet/.test(html), "no brief in the payload, so it says so");
  assert.ok(/No pages yet/.test(html) && /data-ag="ctaadd"/.test(html), "and the link list still offers a row");
});


/* ── the language filter starts where the owner actually reads ─────────────── */
test("the page list opens in the site's own language, and All is still one click away", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(kdoc(), a);
  const sel = html.slice(html.indexOf("data-agpagelang"));
  assert.ok(/<option value="en" selected>/.test(sel), "the site's own language is selected: " + sel.slice(0, 220));
  assert.ok(/<option value="de" >German</.test(sel.replace(/\s+>/g, " >")), "the translations are still offered");
  assert.ok(/<option value="" >All languages</.test(sel.replace(/\s+>/g, " >")), "and so is All");
  assert.strictEqual(A.agEffLang(a, KIDX, { language_code: "en" }), "en", "not chosen means the site's own");
  a.pageLang = "";
  assert.strictEqual(A.agEffLang(a, KIDX, { language_code: "en" }), "", "an explicit All is honoured, not overridden");
  const html2 = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(/<option value="" selected>All languages</.test(html2.slice(html2.indexOf("data-agpagelang"))), "and shows as chosen");
});

test("one language on the site means no default and no filter at all", () => {
  const a = agReset();
  const mono = { site_index: Object.assign({}, KIDX, { languages: {}, language_names: {} }) };
  assert.strictEqual(A.agEffLang(a, mono.site_index, { language_code: "en" }), "",
                     "nothing to filter, so nothing is filtered");
  assert.ok(!/data-agpagelang/.test(A.agKnowledgeHtml(kdoc(mono), a)), "and no control is drawn");
});

test("the fetch sends the site's own language without the owner choosing it", () => {
  const a = agReset(); const seen = [];
  a.knowledge = kdoc();
  const prev = A.apiGet;
  A.apiGet = async (p) => { seen.push(p); return { total: 0, offset: 0, rows: [] }; };
  A.agLoadPages(0);
  A.apiGet = prev;
  assert.ok(/[?&]lang=en(&|$)/.test(seen[0]), "the default rides on the request: " + seen[0]);
});

test("a filtered list says WHY it is shorter than the catalogue", () => {
  const a = agReset();
  a.pages = { total: 9858, offset: 0, rows: [{ url: "https://testlify.com/a/", title: "A", type: "hr-glossary", body_status: "ok", word_count: 10 }] };
  let html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(html.indexOf("1–1 of 9,858 · in the site&#39;s own language · 12,318 pages in all") !== -1,
            "with no real name in the payload it still reads: " + (html.match(/1–1 of[^<]*/) || [""])[0]);
  const named = kdoc({ site_index: Object.assign({}, KIDX, { language_names: { en: "English", de: "German", ja: "Japanese" } }) });
  html = A.agKnowledgeHtml(named, a);
  assert.ok(html.indexOf("1–1 of 9,858 · in English · 12,318 pages in all") !== -1,
            "and names the language when the payload knows it: " + (html.match(/1–1 of[^<]*/) || [""])[0]);
  a.pageType = "hr-glossary"; a.pageQ = "cost";
  html = A.agKnowledgeHtml(named, a);
  assert.ok(html.indexOf('matching "cost", HR glossary, in English · 12,318 pages in all') !== -1,
            "every filter is named: " + (html.match(/1–1 of[^<]*/) || [""])[0]);
  a.pageQ = ""; a.pageType = ""; a.pageLang = "";
  html = A.agKnowledgeHtml(kdoc(), a);
  assert.ok(/1–1 of 9,858<\/span>/.test(html), "nothing filtered, nothing to explain");
});

/* ── a link to a page the crawl has not read ───────────────────────────────── */
test("a link to a page we have not read says so, as information and not as a failure", () => {
  const a = agReset();
  a.cta = { domain: "testlify.com", rows: [
    { url: "https://testlify.com/pricing/", note: "", title: "Pricing", mine: false },
    { url: "https://testlify.com/brand-new/", note: "", title: "", mine: true }] };
  const html = A.agCtaHtml(a.cta, null);
  assert.strictEqual((html.match(/ag-ctanote/g) || []).length, 1, "only the unread row says anything");
  assert.ok(html.indexOf("This page is not in the catalogue yet, so there is nothing read about it. The link still works.") !== -1,
            "allowed, and said");
  assert.ok(!/ag-err|error|failed|invalid/i.test(html), "it never reads as a failure");
  A.agAction("ctaadd", { getAttribute: () => "" });
  const drafted = A.agCtaHtml(a.cta, a.ctaForm);
  assert.strictEqual((drafted.match(/ag-ctanote/g) || []).length, 1,
                     "the blank row he just added is not accused of anything");
  assert.strictEqual(a.ctaForm.rows[0].title, "Pricing", "a title survives an edit to the draft");
});

/* ── a standing screen carries no nags; a live moment does ─────────────────── */
const PACK = { files: [{ name: "persona.md", exists: true, words: 400 }],
               confirm: ["Three reader types are drafted. Which of them do we actually write for?",
                         "Nobody has said who signs these articles."] };
test("at a checkpoint the agent says what it is waiting for, as a question and not a warning", () => {
  const S = A.S; S.ag = null;
  const a = A.agS();
  a.chatId = "c1";
  a.chat = { runs: [{ run_id: "r1", status: "waiting", waiting_on: { kind: "artifact", artifact: "brand", view: "brand_pack" } }] };
  a.panel = { run_id: "r1", name: "brand", view: "brand_pack", data: PACK, loading: false };
  const html = A.agPanelHtml(a);
  assert.ok(/Before I carry on, there are 2 things I need you to decide\./.test(html), "the agent asks");
  assert.ok(/Which of them do we actually write for\?/.test(html) && /who signs these articles/.test(html),
            "and names each one");
  assert.ok(!/p-warn|note w/.test(html), "no warning colour, no yellow banner");
  assert.ok(!/\d+ to confirm/.test(html), "and no badge with a number on it");
  assert.ok(/class="ag-card"/.test(html), "it is the card the agent already waits in");
  const one = A.agBrandPackHtml({ files: [], confirm: ["Only this one."] }, { atCheckpoint: true });
  assert.ok(/there is one thing I need you to decide/.test(one), "one question is not '1 things'");
});

test("the same payload nags nobody on the standing screen", () => {
  const a = agReset();
  assert.ok(!/I need you to decide/.test(A.agBrandPackHtml(PACK, {})), "no caller, no ask");
  assert.ok(!/I need you to decide/.test(A.agBrandPackHtml(PACK, { atCheckpoint: false })), "not at a checkpoint, no ask");
  const k = kdoc({ brand: Object.assign({}, KBRAND, { confirm: PACK.confirm, needs_review: PACK.confirm }) });
  const html = A.agKnowledgeHtml(k, a);
  assert.ok(!/I need you to decide/.test(html) && !/write for\?/.test(html), "and the Knowledge tab never asks");
  assert.ok(!/ag-card/.test(html), "there is no waiting card on a reference screen");
});

/* ── the Library editor, back ──────────────────────────────────────────────── */
test("the Library editor puts the title and the whole article in front of him", () => {
  const S = A.S; S.ag = null;
  const a = A.agS();
  a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true,
              libId: "lib7", title: "Cost per hire", data: { text: "# Cost per hire\n\nSix hundred words." } };
  A.agAction("libedit", { getAttribute: k => k === "data-arg" ? "lib7" : "" });
  assert.strictEqual(a.libEdit.title, "Cost per hire", "the title is loaded from the panel");
  assert.strictEqual(a.libEdit.draft, "# Cost per hire\n\nSix hundred words.", "and the body");
  const html = A.agPanelHtml(a);
  assert.ok(/data-aglibtitle value="Cost per hire"/.test(html), "the title is editable");
  assert.ok(/data-aglibbody[^>]*>. Cost per hire/.test(html.replace(/#/g, ".")), "so is the article");
  assert.ok(/data-ag="libsave" data-arg="lib7"/.test(html) && /data-ag="libcancel"/.test(html), "save and cancel");
  assert.ok(/>7 words</.test(html), "the count is of HIS text: " + (html.match(/>\d+ words</) || [""])[0]);
  assert.ok(!/data-ag="libedit"/.test(html), "and the Edit button steps aside while he edits");
});

test("cancel throws the draft away and never touches the saved article", () => {
  const S = A.S; S.ag = null;
  const a = A.agS();
  a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true,
              libId: "lib7", title: "Cost per hire", data: { text: "the saved words" } };
  A.agAction("libedit", { getAttribute: () => "lib7" });
  a.libEdit.draft = "words he typed and thought better of";
  a.libEdit.title = "a title he thought better of";
  A.agAction("libcancel", { getAttribute: () => "" });
  assert.strictEqual(a.libEdit, null, "the draft is gone");
  assert.strictEqual(a.panel.data.text, "the saved words", "the saved article never moved");
  assert.strictEqual(a.panel.title, "Cost per hire");
  assert.ok(/data-ag="libedit"/.test(A.agPanelHtml(a)), "and Edit is offered again");
});

test("an empty article is not a save", () => {
  const S = A.S; S.ag = null;
  const a = A.agS();
  a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true,
              libId: "lib7", title: "T", data: { text: "body" } };
  a.libEdit = { title: "T", draft: "   \n  ", busy: false, error: "" };
  let posted = false;
  const prev = A.apiPost; A.apiPost = async () => { posted = true; return {}; };
  A.agAction("libsave", { getAttribute: () => "lib7" });
  A.apiPost = prev;
  assert.strictEqual(posted, false, "nothing is sent");
  assert.ok(/An empty article is not a save/.test(a.libEdit.error), "and he is told why");
  assert.strictEqual(a.libEdit.draft, "   \n  ", "with what he typed still there");
});

/* ── the CSS the layout leans on ───────────────────────────────────────────── */
const CSS = fs.readFileSync(path.join(__dirname, "static", "agents.css"), "utf8");
test("opening the panel no longer changes the document's HEIGHT under the reader", () => {
  assert.ok(CSS.indexOf(".ag.haspanel .ag-file .fd{display:none}") === -1,
            "the rule that hid every blurb the moment the panel opened is gone");
  assert.ok(/\.ag\.haspanel \.ag-view\.wide\{max-width:none\}/.test(CSS), "the width rule stays");
  assert.ok(typeof A.agScrollAnchor === "function" && typeof A.agScrollRestore === "function",
            "and agDraw has something to hold the reader's place with");
});
test("every new class the Knowledge tab uses is actually styled", () => {
  ["ag-sechead", "ag-secctl", "ag-mapcap", "ag-brief", "ag-ctalist", "ag-ctarow", "ag-ctasrc",
   "ag-ctanote", "ag-editrow", "ag-libedit", "ag-lbl"].forEach(c => {
    assert.ok(CSS.indexOf("." + c) !== -1, "." + c + " has no rule in agents.css");
  });
  assert.ok(!/#[0-9a-fA-F]{3,6}/.test(CSS.slice(CSS.indexOf(".ag-sechead"))), "no hardcoded colour after the new block");
  assert.ok(CSS.indexOf(".ag-briefsub") !== -1, ".ag-briefsub has no rule in agents.css");
});
test("the brief box is capped short enough to leave room for what is under it", () => {
  /* 62vh until 2026-09-09: the owner read the real 3,090-word pack and the box still owned the
     screen. Short window on the page, whole file behind Open. */
  const flat = CSS.replace(/\s+/g, "");
  const m = flat.match(/\.ag-brief\{[^}]*max-height:(\d+)vh/);
  assert.ok(m, ".ag-brief has no max-height");
  assert.ok(Number(m[1]) <= 34, "the brief box is still tall: " + m[1] + "vh");
  assert.ok(/overflow-y:auto/.test(m.input.slice(flat.indexOf(".ag-brief{"), flat.indexOf(".ag-brief{") + 400)),
            "and it keeps its own scroll");
});

/* the save round-trips, so it runs after the synchronous suite and reports with it */
async function atest(name, fn){
  try { await fn(); pass++; console.log("ok   - " + name); }
  catch (e){ fail++; console.log("FAIL - " + name); console.log("       " + (e && e.message)); }
}

(async () => {
  await atest("saving the link list posts the WHOLE list, in display order, and clears the draft", async () => {
    const a = agReset();
    a.cta = { domain: "testlify.com", rows: [{ url: "https://testlify.com/pricing/", note: "price", mine: false }] };
    a.ctaForm = { rows: [{ url: "https://testlify.com/pricing/", note: "price", mine: false },
                         { url: " https://testlify.com/demo/ ", note: "a look first", mine: true },
                         { url: "", note: "half typed", mine: true }] };
    let body = null;
    const prev = A.apiPost;
    A.apiPost = async (p, b) => { body = { path: p, b }; return { domain: "testlify.com", rows: b.rows.map(r => Object.assign({ mine: true, title: "" }, r)) }; };
    await A.agAction("ctasave", { getAttribute: () => "" });
    A.apiPost = prev;
    assert.ok(body && /\/knowledge\/cta$/.test(body.path), "posted to /knowledge/cta: " + (body && body.path));
    assert.strictEqual(body.b.rows.length, 2, "the empty row is not sent");
    assert.strictEqual(body.b.rows[0].url, "https://testlify.com/pricing/", "in display order");
    assert.strictEqual(body.b.rows[1].url, "https://testlify.com/demo/", "and trimmed");
    assert.strictEqual(a.ctaForm, null, "the draft is dropped once it is saved");
    assert.strictEqual(a.cta.rows.length, 2, "and the saved list is what came back");
  });

  await atest("a save that fails keeps the draft on screen and says why", async () => {
    const a = agReset();
    a.ctaForm = { rows: [{ url: "https://testlify.com/demo/", note: "", mine: true }] };
    const prev = A.apiPost;
    A.apiPost = async () => { throw new Error("that address is not on testlify.com"); };
    await A.agAction("ctasave", { getAttribute: () => "" });
    A.apiPost = prev;
    assert.strictEqual(a.ctaForm.rows.length, 1, "nothing he typed is thrown away");
    assert.ok(/not on testlify\.com/.test(a.ctaForm.msg), "and the reason is his: " + a.ctaForm.msg);
    assert.ok(/not on testlify\.com/.test(A.agCtaHtml(a.cta, a.ctaForm)), "on the screen, beside the button");
  });

  await atest("saving a Library article posts the title and the body, and the panel shows the saved one", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true,
                libId: "lib7", title: "Old title", data: { text: "old body" } };
    a.libEdit = { title: "  Cost per hire  ", draft: "new body, longer", busy: false, error: "" };
    let body = null;
    const prevP = A.apiPost, prevG = A.apiGet;
    A.apiPost = async (p, b) => { body = { path: p, b }; return { id: "lib7", title: "Cost per hire", words: 3, status: "draft" }; };
    A.apiGet = async () => ([{ id: "lib7", title: "Cost per hire" }]);
    await A.agAction("libsave", { getAttribute: k => k === "data-arg" ? "lib7" : "" });
    A.apiPost = prevP; A.apiGet = prevG;
    assert.ok(body && /\/library\/lib7\/save$/.test(body.path), "posted to the save endpoint: " + (body && body.path));
    assert.strictEqual(body.b.title, "Cost per hire", "the title is trimmed before it goes");
    assert.strictEqual(body.b.draft, "new body, longer", "the body goes whole");
    assert.strictEqual(a.libEdit, null, "the editor closes");
    assert.strictEqual(a.panel.data.text, "new body, longer", "the panel shows what he saved");
    assert.ok(/edited by you/.test(a.panel.subtitle), "and says he did it: " + a.panel.subtitle);
  });

  await atest("a Library save that fails keeps every word he typed on screen", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true,
                libId: "lib7", title: "T", data: { text: "old body" } };
    a.libEdit = { title: "T", draft: "the words he wants kept", busy: false, error: "" };
    const prev = A.apiPost;
    A.apiPost = async () => { throw new Error("the disk is full"); };
    await A.agAction("libsave", { getAttribute: () => "lib7" });
    A.apiPost = prev;
    assert.strictEqual(a.libEdit.draft, "the words he wants kept", "nothing is thrown away");
    assert.ok(/disk is full/.test(a.libEdit.error), "and the reason is his: " + a.libEdit.error);
    assert.strictEqual(a.panel.data.text, "old body", "the saved article is untouched");
    assert.ok(/disk is full/.test(A.agLibEditHtml(a.panel, a.libEdit)), "on screen, beside the button");
  });

  console.log("\n" + "-".repeat(60));
  console.log("agents screen: " + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
