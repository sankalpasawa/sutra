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
  /* left undefined on purpose: the module guards every DOM reach with typeof, and a test that
     needs one swaps in the smallest stand-in it can and puts it back afterwards */
  document: undefined, confirm: undefined, navigator: undefined,
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

test("Knowledge offers a check for changes, and never a chat log", () => {
  const k = { site_index: { domain: "x.com", page_count: 100, pages: [] }, report: {}, brand: { files: [] } };
  A.S.ag.refresh = null;
  const html = A.agKnowledgeHtml(k, A.S.ag);
  assert(html.indexOf('data-ag="refreshcheck"') !== -1, "a check button");
  assert(/only what is new or has changed/.test(html), "and says it does not re-read the site");
});

/* The traffic importer was built for one incident -- a DataForSEO balance at minus seven cents,
   mid-build -- and it is not a thing anybody sets out to do from a settings tab. The tool and
   POST /knowledge/traffic both stay, for the chat to offer when an account runs dry; what goes
   is the standing affordance and everything that only existed to serve it. */
test("the traffic import is not a button, and nothing of its form is left behind", () => {
  const k = { site_index: { domain: "x.com", page_count: 100, pages: [] }, report: {}, brand: { files: [] } };
  A.S.ag.refresh = null;
  const html = A.agKnowledgeHtml(k, A.S.ag);
  assert(html.indexOf("trafficimport") === -1, "no button on the catalogue heading row");
  assert(html.indexOf("data-agtraffic") === -1, "and no path box anywhere on the tab");
  assert(!/Import a traffic file/.test(html), "and it is not offered in words either");
  assert(SRC.indexOf("trafficgo") === -1 && SRC.indexOf("trafficcancel") === -1,
         "the actions that only served that form are gone with it");
  assert(SRC.indexOf("trafficForm") === -1, "and so is the state it parked its draft on");
});

/* ── the refresh card: what it is doing, said in the engine's words ────────────
   THE BUG THESE EXIST FOR (owner, 2026-09-10). The card drew a spinner beside ONE FIXED
   SENTENCE for the whole run, because the route threw every line refresh_site emitted into a
   no-op emit. A run that sat in six minutes of firewall cooldowns therefore looked exactly like
   a hang, and exactly like a finish. So each of these asks the same question in a different
   state: can he tell working from waiting from stopped from done, and is every word of it the
   engine's? */
const kjob = (o) => Object.assign({
  mode: "preview", phase: "running", label: "Catching up on what changed", steps: [],
  waiting: null, result: null, error: null, spawned: true,
  started_at: Date.now() / 1000, updated_at: Date.now() / 1000, finished_at: null }, o || {});

test("while it works the card shows the engine's last line, and the ones before it", () => {
  const a = A.S.ag;
  const now = Date.now() / 1000;
  a.refresh = kjob({ steps: [
    { label: "Asking the site for its current list", note: "no pages are read yet, only their addresses", at: now - 40 },
    { label: "Read the sitemaps", note: "14 sitemap files", at: now - 30 },
    { label: "The site lists 11,656 pages now", note: "every address the sitemaps and the CMS list", at: now - 2 }],
    updated_at: now - 2 });
  const h = A.agRefreshHtml(a);
  assert(/class="spin"/.test(h), "it is working, so it spins");
  assert(h.indexOf("The site lists 11,656 pages now") !== -1, "the line the engine last said is on top");
  assert(h.indexOf("every address the sitemaps and the CMS list") !== -1, "with its own note");
  assert((h.match(/class="msg"/g) || []).length === 1, "one line on top, never a log");
  assert(h.indexOf("Read the sitemaps") !== -1 && h.indexOf("Asking the site") !== -1,
         "and what it said before is behind it: " + h.slice(0, 200));
  assert(h.indexOf("<li>") < h.indexOf("Read the sitemaps"), "the earlier lines are the trail");
  assert(h.indexOf("Catching up on what changed") !== -1, "headed by the tool's own name");
  a.refresh = null;
});

/* Every word of progress must be the engine's. A sentence written here would keep saying the
   same thing whatever the engine was doing -- which is precisely what the old card did. */
test("the card invents no progress line of its own", () => {
  /* the comments still tell the story of the bug, so the CODE is what is read here */
  const code = SRC.replace(/\/\*[\s\S]*?\*\//g, "");
  assert(code.indexOf("Asking the site for its current list") === -1,
         "the fixed sentence that made a six-minute run look like a hang is gone from the client");
  assert(code.indexOf("Reading the pages that are new or have changed") === -1,
         "and so is the one the second button drew");
  const a = A.S.ag;
  a.refresh = kjob({ steps: [], updated_at: Date.now() / 1000 });
  const h = A.agRefreshHtml(a);
  assert(/Nothing back from it yet/.test(h), "with no line yet it says exactly that: " + h.slice(0, 200));
  a.refresh = null;
});

/* WAITING IS NOT WORKING. fetch.py announces a firewall cooldown before it sits through one,
   and the owner's run spent six minutes in those. A wait drawn as work is a claim of progress. */
test("a wait the site imposed is drawn as waiting, not as working", () => {
  const a = A.S.ag;
  const now = Date.now() / 1000;
  a.refresh = kjob({ mode: "apply",
    steps: [{ label: "The site's firewall pushed back",
              note: "waiting 120s before trying https://testlify.com/blog/ again, and slowing to one request every 1.2s",
              at: now - 30 }],
    waiting: { seconds: 120, since: now - 30 }, updated_at: now - 30 });
  const h = A.agRefreshHtml(a);
  assert(!/class="spin"/.test(h), "no working spinner while nothing is being read");
  assert(/class="hold"/.test(h), "a held mark instead");
  assert(/Waiting on the site/.test(h), "and it says so: " + h.slice(0, 240));
  assert(/30s of 2m/.test(h), "with how long it has waited of how long it said: " + h.slice(0, 300));
  assert(h.indexOf("The site&#39;s firewall pushed back") !== -1 || h.indexOf("firewall pushed back") !== -1,
         "the engine's own line is still the line");
  a.refresh = null;
});

/* A run can go quiet for minutes between lines. Quiet must read as alive -- the server has
   already checked the worker is there -- and never as finished. */
test("a run that has said nothing for minutes reads as alive, never as done", () => {
  const a = A.S.ag;
  const now = Date.now() / 1000;
  a.refresh = kjob({ mode: "apply",
    steps: [{ label: "Reading 214 pages", note: "only the ones that are new or have changed", at: now - 200 }],
    updated_at: now - 200 });
  const h = A.agRefreshHtml(a);
  assert(/class="spin"/.test(h), "still working");
  assert(/Still going/.test(h) && /nothing new for 3m 20s/.test(h), "and it says how long it has been quiet: " + h.slice(0, 260));
  assert(!/Done/.test(h), "quiet is not finished");
  assert(h.indexOf('data-ag="refreshchanges"') === -1, "and offers nothing to read yet");
  /* a line that has only just arrived is not worth a gap line */
  a.refresh = kjob({ steps: [{ label: "Read the sitemaps", note: "", at: now - 1 }], updated_at: now - 1 });
  assert(!/Still going/.test(A.agRefreshHtml(a)), "a fresh line needs no explaining");
  a.refresh = null;
});

test("a finished check replaces the spinner with the counts", () => {
  const a = A.S.ag;
  a.refresh = kjob({ phase: "done", finished_at: Date.now() / 1000,
                     result: { new: 37, gone: 4, changed: 112, unchecked: 900, report: "# What changed" } });
  let h = A.agRefreshHtml(a);
  assert(!/class="spin"/.test(h), "nothing is still working");
  assert(/37 new/.test(h) && /4 gone/.test(h) && /112 rewritten/.test(h), "the counts: " + h.slice(0, 200));
  assert(/900 pages give no date/.test(h), "and what could not be checked cheaply");
  assert(h.indexOf('data-ag="refreshgo"') !== -1, "nothing happens until you say go");
  assert(h.indexOf('data-ag="refreshreport"') !== -1, "the list has a door");

  a.refresh = kjob({ phase: "done", finished_at: Date.now() / 1000,
                     result: { new: 0, gone: 0, changed: 0, unchecked: 0 } });
  h = A.agRefreshHtml(a);
  assert(/Nothing has changed/.test(h) && h.indexOf('data-ag="refreshgo"') === -1,
         "with nothing to do there is nothing to press");

  a.refresh = kjob({ mode: "apply", phase: "done", finished_at: Date.now() / 1000,
                     result: { summary: "3 pages added, 0 removed, 0 re-read.", added: 3 } });
  h = A.agRefreshHtml(a);
  assert(/Done\./.test(h) && /3 pages added/.test(h), "what it did, in the engine's own count");
  assert(!/class="spin"/.test(h) && h.indexOf('data-ag="refreshchanges"') !== -1, "done, and a way to read it");
  a.refresh = null;
});

/* A failure that looks like progress is worse than the silence this replaced. */
test("a refresh that stopped replaces the spinner with the reason", () => {
  const a = A.S.ag;
  a.refresh = kjob({ mode: "apply", phase: "failed", finished_at: Date.now() / 1000,
    error: "The site refused every page (cf-mitigated). Nothing was changed, so the catalogue is exactly as it was.",
    result: { summary: "Nothing was added: not one of the 214 pages could be read." },
    steps: [{ label: "Reading 214 pages", note: "", at: Date.now() / 1000 - 60 }] });
  const h = A.agRefreshHtml(a);
  assert(!/class="spin"/.test(h) && !/class="hold"/.test(h), "nothing spins after the work has stopped");
  assert(/refused every page/.test(h) && /class="msg err"/.test(h), "a failure says so plainly");
  assert(/not one of the 214 pages could be read/.test(h), "and the summary beside it is kept");
  assert(!/Done/.test(h), "and never a Done over the top of it");
  assert(h.indexOf('data-ag="refreshcancel"') !== -1, "with a way to put it away");
  a.refresh = null;
});

/* The one failure the server never sees: the press that never reached it. */
test("a job the server has forgotten leaves nothing spinning", () => {
  const a = A.S.ag;
  a.refresh = kjob({ phase: "failed", finished_at: Date.now() / 1000, spawned: true,
    error: "The refresh stopped without saying why. Nothing was changed." });
  const h = A.agRefreshHtml(a);
  assert(!/class="spin"/.test(h) && /stopped without saying why/.test(h));
  a.refresh = null;
});

test("with nothing happening, the refresh box draws nothing at all", () => {
  const a = A.S.ag;
  a.refresh = null;
  assert.strictEqual(A.agRefreshHtml(a), "", "no state, no box");
});

/* THE TEST THAT WOULD HAVE CAUGHT IT. "Check for changes" and "Import a traffic file" both had a
   button, four rendered states and a working route -- and agAction had no arm for either, so the
   click reached `default: break` and nothing happened, with nothing anywhere to say so. A dead
   button is worse than a missing one: the person is told the feature exists.

   So this is structural, not a list of the buttons that exist today: every literal data-ag the
   renderers emit must have a case in agAction. Add a button without wiring it and this goes red. */
test("every button the screen draws has an arm in agAction -- no silent no-ops", () => {
  const body = SRC.slice(SRC.indexOf("async function agAction"), SRC.indexOf("/* \u2500\u2500 wiring:"));
  assert.ok(body.length > 400, "found the agAction body to read");
  const emitted = new Set();
  const re = /data-ag="([a-z][a-z0-9]*)"/g;
  let m;
  while ((m = re.exec(SRC))) emitted.add(m[1]);
  const armed = new Set();
  const rc = /case "([a-z][a-z0-9]*)":/g;
  while ((m = rc.exec(body))) armed.add(m[1]);
  assert.ok(emitted.size > 25, "found the buttons, got " + emitted.size);
  const dead = [...emitted].filter(x => !armed.has(x)).sort();
  assert.strictEqual(dead.join(", "), "", "these buttons do nothing when clicked: " + dead.join(", "));
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

/* Written before the reuse check existed and never wired to anything: no tool takes a page and
   rebuilds it, so the chip filled the composer with a sentence the agent could only improvise
   around. Deleted, not rewired -- there is no step to point it at. */
test("the hero does not offer to improve an existing page", () => {
  const ok = A.agHeroHtml({ model_provider: "claude-cli", dataforseo: true, voyage: true, site_indexed: true, page_index: { built: true }, brand_ready: true });
  assert.ok(!/Improve one of our existing pages/.test(ok), "the button is gone");
  assert.ok(!/Improve our page/.test(ok), "and so is the message it wrote");
  assert.ok(SRC.indexOf("Improve one of our existing pages") === -1, "nothing of it is left in the source");
  assert.strictEqual((ok.match(/class="ag-play"/g) || []).length, 2, "two plays left, both real");
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

/* The lead said "the seven things the agent can do" over eleven rows, and had done since the
   eleventh tool landed; there are twelve now. DERIVED, so it cannot go stale again. */
test("the tools lead counts the tools it is actually drawing", () => {
  const tool = n => ({ name: n, label: "L" + n, does: "d" });
  const twelve = A.agToolsHtml("abcdefghijkl".split("").map(tool));
  assert.ok(/The twelve things the agent can do/.test(twelve), "twelve rows, twelve: " + twelve.slice(0, 200));
  assert.ok(!/seven things|eleven things/.test(twelve), "and never a number somebody typed");
  assert.ok(/The three things the agent can do/.test(A.agToolsHtml("abc".split("").map(tool))));
  assert.ok(/The one thing the agent can do,/.test(A.agToolsHtml([tool("a")])), "and one is singular");
});

/* The sentence also used to claim "the last four run for every article". True only by an accident
   of ordering, and false the day find_prompt was appended -- it is a support tool, not a per-
   article step. A positional claim about a list another team owns cannot be kept true. */
test("the tools lead makes no claim about which rows are the per-article ones", () => {
  const tool = n => ({ name: n, label: "L" + n, does: "d" });
  const html = A.agToolsHtml("abcdefghijkl".split("").map(tool));
  const lead = html.slice(html.indexOf('class="lead"'), html.indexOf("</p>"));
  assert.ok(!/last (four|three|two|\d)/.test(lead), "no positional claim: " + lead);
  assert.ok(/writing steps run again for every article/.test(lead), "it says the useful thing anyway");
  assert.strictEqual((lead.match(/\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b/g) || []).length,
                     1, "and exactly one number in the sentence, the derived one: " + lead);
});

/* registry.LABELS is the ONE place a tool's plain name is decided, and as of 2026-09-09 it covers
   all twelve. The screen carried a stand-in map for the three it was missing; that is deleted, so
   this asserts against the REAL registry rather than against fabricated rows -- if a tool is added
   upstream without a label, this is where it shows up as code on a screen. */
test("no tool is listed under its function name", () => {
  const cp = require("child_process"), os = require("os");
  const venv = path.join(__dirname, ".venv", "bin", "python");
  const PY = fs.existsSync(venv) ? venv : "python3";
  const data = fs.mkdtempSync(path.join(os.tmpdir(), "seo-tools-"));
  const r = cp.spawnSync(PY, ["-c", "import json;from seo_agent import registry;print(json.dumps(registry.for_screen()))"], {
    cwd: __dirname, encoding: "utf8",
    env: Object.assign({}, process.env, { PYTHONPATH: __dirname, SEO_AGENT_DATA: data, SEO_AGENT_NO_CLI: "1" }),
  });
  fs.rmSync(data, { recursive: true, force: true });
  const line = (r.stdout || "").trim().split("\n").pop();
  let tools = null;
  try { tools = JSON.parse(line); } catch (e) { tools = null; }
  if (!tools) return;                 /* no engine in this checkout: nothing to assert against */
  assert.ok(tools.length >= 12, "every work tool, got " + tools.length);
  const html = A.agToolsHtml(tools);
  const raw = tools.filter(t => {
    const d = String(t.name).replace(/_/g, " ");
    return A.agToolName(t) === d.charAt(0).toUpperCase() + d.slice(1) || A.agToolName(t) === d;
  }).map(t => t.name);
  assert.strictEqual(raw.join(", "), "", "these are listed under their function name: " + raw.join(", "));
  assert.ok(/Catching up on what changed/.test(html), "refresh_site reads as a sentence");
  assert.ok(/Loading a traffic file you already have/.test(html), "and so does import_traffic");
  assert.ok(/Working out what is worth writing/.test(html), "and build_assets");
  assert.ok(!/>Refresh site<|>Import traffic<|>Build assets<|>Find prompt</.test(html), "no raw name on screen");
});

/* The label is the ENGINE'S to decide -- one place, not two. The fallback exists only so a tool
   added upstream before its label is written still draws a row rather than an empty cell. */
test("the screen draws the label the engine sends, and only falls back when there is none", () => {
  assert.ok(SRC.indexOf("AG_TOOL_NAMES") === -1, "the stand-in map is deleted, not left dormant");
  assert.strictEqual(A.agToolName({ name: "refresh_site", label: "Catching the site up" }),
                     "Catching the site up", "the engine's word is the word");
  assert.strictEqual(A.agToolName({ name: "some_new_tool" }), "some new tool",
                     "and a tool with no label still draws something readable");
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
  a.refresh = null; a.refreshSeen = null; a.refreshPollErr = null; a.compForm = null; a.coForm = null;
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
  assert.ok(/data-ag="map"/.test(head), "and the map");
  assert.ok(!/data-ag="trafficimport"/.test(head), "the traffic import is not a button any more");
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

/* THE EXTRAS ROW IS GENERIC, and this is the test that says so rather than a comment claiming it.
   It matters twice right now. The byline feature ("Who writes", voices.md) is being deleted from
   the engine: the row goes when the engine stops listing the file, with no change here and no
   special case -- the empty case at the bottom is that promise. And a knowledge file the engine
   ADDS -- pricing.md, "Prices and hidden facts", which a person types into -- appears on its own,
   under the engine's own label, which is what the file used here is. */
test("a knowledge file the engine lists gets its own section, whatever the file is", () => {
  const a = agReset();
  const extras = [{ name: "pricing.md", label: "Prices and hidden facts",
                    note: "What each plan costs and what the site does not say out loud.",
                    exists: true, words: 240, in_use: true }];
  const html = A.agKnowledgeHtml(kdoc({ brand: Object.assign({}, KBRAND, { extras }) }), a);
  assert.ok(/<h3 class="sec">Prices and hidden facts<\/h3>/.test(html),
            "the engine's label is the heading, and is not repeated in the row");
  assert.ok((html.match(/>Prices and hidden facts</g) || []).length === 1, "said once on screen");
  assert.ok(/What each plan costs/.test(html), "the row says what the file is");
  assert.ok(/data-arg="pricing.md"/.test(html), "and opens that file");
  assert.ok(SRC.indexOf("pricing.md") !== -1 && SRC.indexOf("Prices and hidden facts") !== -1,
            "the brand-pack panel's file list -- the one hardcoded list on this screen -- knows it too");

  const off = [{ name: "voices.md", label: "Who writes", note: "Who signs the writing.",
                 exists: true, words: 120, in_use: false }];
  const byline = A.agKnowledgeHtml(kdoc({ brand: Object.assign({}, KBRAND, { extras: off }) }), a);
  assert.ok(/not in use yet/.test(byline), "in_use false is said plainly, never left to look built");

  const none = A.agKnowledgeHtml(kdoc({ brand: Object.assign({}, KBRAND, { extras: [] }) }), a);
  assert.ok(!/Who writes/.test(none) && !/Prices and hidden facts/.test(none),
            "and a file the engine stops listing takes its whole section with it -- no special case");
});

/* PRICING.MD IS THE FIRST FILE IN THE PRODUCT A PERSON IS EXPECTED TO TYPE INTO rather than
   review, and the failure mode is known: the old seed file shipped blank, looked like something
   that had not been built yet, and stayed blank for months. So the inputs section is drawn as an
   ask -- its own row state, a primary button, and a door that lands in the editor. */
const INPUT_ROW = { name: "pricing.md", label: "Prices and hidden facts",
                    note: "Anything your site draws with JavaScript, so a crawler cannot see it.",
                    exists: true, words: 205, filled: false };
const withInputs = rows => kdoc({ brand: Object.assign({}, KBRAND, { inputs: rows }) });

test("a file a person fills in is drawn as an ask, not as another empty artifact", () => {
  const a = agReset();
  const html = A.agKnowledgeHtml(withInputs([INPUT_ROW]), a);
  assert.ok(/<h3 class="sec">Prices and hidden facts<\/h3>/.test(html), "it gets its own section");
  assert.ok(/ag-row ask/.test(html), "drawn as a row that is asking for something");
  assert.ok(/yours to write/.test(html), "and says whose job it is");
  assert.ok(/Nothing has been written here yet/.test(html), "and says so in words");
  assert.ok(/data-ag="inputwrite"/.test(html) && /Write it/.test(html), "the door is Write, not Open");
  assert.ok(/class="btn pri"/.test(html.slice(html.indexOf("ag-row ask"))), "and it is the primary button on the row");
  const none = A.agKnowledgeHtml(withInputs([]), a);
  assert.ok(!/inputwrite/.test(none), "no inputs, no section");
});

/* THE WHOLE REASON `filled` EXISTS. The blank form is 205 real words on disk, so a word count
   alone calls an untouched file filled the day it is created -- which is exactly how the seed
   file this replaces stayed empty for months. */
test("a blank form is never mistaken for a written one, whatever its word count", () => {
  const a = agReset();
  const blank = A.agKnowledgeHtml(withInputs([INPUT_ROW]), a);
  assert.ok(/ag-row ask/.test(blank), "205 words of blank form is still an ask");
  assert.ok(/the blank form/.test(blank) && !/205 words/.test(blank),
            "and its length is not reported as if somebody had written it");

  const written = A.agKnowledgeHtml(withInputs([Object.assign({}, INPUT_ROW, { words: 211, filled: true })]), a);
  assert.ok(!/ag-row ask/.test(written), "once it is written the row settles down");
  assert.ok(/you wrote this/.test(written) && /211 words/.test(written), "and reports what is in it");
  assert.ok(/>Open</.test(written) && !/Write it/.test(written), "an ask that keeps asking is noise");
});

test("an engine too old to say whether it is filled keeps asking, rather than assuming", () => {
  const a = agReset();
  const old = Object.assign({}, INPUT_ROW); delete old.filled;
  assert.ok(/ag-row ask/.test(A.agKnowledgeHtml(withInputs([old]), a)),
            "asking twice costs far less than never asking");
});

/* One file, one description. The Knowledge screen and the brand-pack panel both name pricing.md,
   and describing it two ways would be two answers to the same question. */
test("pricing.md is described the same way wherever it is named", () => {
  assert.ok(/Anything your site draws with JavaScript, so a crawler cannot see it/.test(SRC),
            "the engine's own wording is the wording used here");
  assert.ok(!/the things the site does not say out loud/.test(SRC), "and the divergent one is gone");
  assert.ok(/beats anything we read off the site/.test(SRC),
            "including the half that says a typed fact outranks the crawl");
});

/* The byline is being deleted from the product. The Knowledge tab needed nothing (above); the
   brand-pack panel's file list is hardcoded, so its row had to go by hand or it would have sat
   there saying "not built yet" for ever. */
test("the byline file is gone from the brand pack panel", () => {
  assert.ok(SRC.indexOf("voices.md") === -1, "no row for it in AG_BRAND_FILES");
  assert.ok(!/Bylines/.test(SRC), "and nothing on the screen says Bylines");
  const html = A.agBrandPackHtml({ files: [{ name: "brand-voice.md", exists: true, words: 900 }] }, {});
  assert.ok(!/voices\.md|Bylines/.test(html), "and none is drawn");
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

/* ── the live Library: a row is born when the run starts and fills in ──────────
   Since 2026-09-09 the Library is where he watches an article being made, because the
   checkpoints that used to stop and show him each piece are gone. The risk the whole
   shape is designed against: a person opening the tab mid-run sees half a thing, and
   unless the state reads at a glance the tab looks full of broken articles. So these
   check the three states apart, and check that a row from the OLD payload is untouched. */
const LIB_MILES = (over) => [
  { key: "research", label: "Researched", note: "the brief this article is built on", exists: true, at: "2026-09-09T09:00:00Z" },
  { key: "picture", label: "The search picture", note: "what the search results show", exists: true, at: "2026-09-09T09:05:00Z" },
  { key: "plan", label: "Planned", note: "the headings and the evidence", exists: false, at: null },
  { key: "draft", label: "Written", note: "the article as the writer left it", exists: false, at: null },
  { key: "edited", label: "Edited", note: "what each editing pass changed", exists: false, at: null },
].map(m => Object.assign(m, (over || {})[m.key] || {}));

test("a row being written says so, and shows how far it has got", () => {
  const html = A.agLibraryHtml([{ id: "run-c1-r1", title: "Writing…", status: "writing", words: 0,
                                  request: "Write an article about cost per hire",
                                  created_at: "2026-09-09T09:00:00Z", milestones: LIB_MILES() }]);
  assert.ok(/class="ag-row writing"/.test(html), "the row itself is marked, so it can carry the accent edge");
  assert.ok(/Write an article about cost per hire/.test(html),
            "it is named by what he asked for, because the pill beside it already says writing");
  assert.ok(html.indexOf(">Writing…") === -1, "so the placeholder name never says the same thing twice");
  assert.ok(/<span class="pill p-acc"><i class="spin" aria-hidden="true"><\/i>writing<\/span>/.test(html),
            "accent pill with a turning marker, never a grey one: " + (html.match(/<span class="pill[^]*?<\/span>/) || [""])[0]);
  assert.ok(html.indexOf("<span>2 of 5 done</span>") !== -1, "it counts the pieces instead of 0 words");
  assert.ok(/<span>started /.test(html), "and dates itself from the start, not from a save");
  assert.ok(!/data-ag="libopen"/.test(html), "no Open: there is nothing whole to open yet");
  assert.ok(!/data-ag="libstatus"/.test(html), "and no Mark ready, which the run would overwrite at finish");
  assert.ok(/data-ag="libdel"/.test(html), "Delete stays");
});

test("a milestone that exists is clickable; one that does not is greyed and not a button", () => {
  const html = A.agLibraryHtml([{ id: "run-c1-r1", title: "Writing…", status: "writing", words: 0,
                                  created_at: "2026-09-09T09:00:00Z", milestones: LIB_MILES() }]);
  const strip = html.slice(html.indexOf('class="ag-miles"'), html.indexOf("</div>", html.indexOf('class="ag-miles"')));
  assert.ok(/<button class="ag-mile done" type="button" data-ag="libmile" data-arg="run-c1-r1" data-name="research"/.test(strip),
            "the made one is a button carrying the row and the key: " + strip.slice(0, 200));
  assert.ok(/data-name="picture"/.test(strip) && /The search picture/.test(strip),
            "the search picture is one of them, in plain words");
  assert.ok(/<span class="ag-mile cur"[^>]*title="being made now"><i aria-hidden="true"><\/i>Planned<\/span>/.test(strip),
            "the next one is marked as being made now, not as missing: " + strip);
  assert.ok(/<span class="ag-mile todo"[^>]*>.*?Written/.test(strip), "the ones after it are just ahead");
  assert.ok(strip.indexOf('data-name="plan"') === -1 && strip.indexOf('data-name="draft"') === -1,
            "nothing that does not exist is clickable");
  assert.ok(!/disabled/.test(strip), "and they are spans, not disabled buttons, so there is nothing to tab to");
  assert.ok(/title="the brief this article is built on · /.test(strip), "a made one says what it is and when");
});

test("a row born before the run knew what it was asked keeps the placeholder name", () => {
  const html = A.agLibraryHtml([{ id: "run-c1-r1", title: "Writing…", status: "writing", words: 0,
                                  created_at: "2026-09-09T09:00:00Z", milestones: LIB_MILES() }]);
  assert.ok(/Writing…/.test(html), "no request on the row, so the placeholder stands rather than a blank line");
  assert.ok(/class="ag-row writing"/.test(html), "and it still reads as in progress");
});

test("a finished row keeps every button it had, and its strip is all done with nothing turning", () => {
  const all = LIB_MILES({ plan: { exists: true, at: "2026-09-09T09:10:00Z" },
                          draft: { exists: true, at: "2026-09-09T09:30:00Z" },
                          edited: { exists: true, at: "2026-09-09T09:40:00Z" } });
  const html = A.agLibraryHtml([{ id: "2026-09-09-cost-per-hire", title: "Cost per hire", status: "ready",
                                  words: 1840, primary_keyword: "cost per hire", created_at: "2026-09-09T09:00:00Z",
                                  milestones: all }]);
  assert.ok(!/class="ag-row writing"/.test(html), "no accent edge on finished work");
  assert.ok(/<span class="pill p-ok">ready to read<\/span>/.test(html), "the green pill, and no spinner in it");
  assert.ok(html.indexOf("<span>1,840 words</span>") !== -1, "the word count is back where the count of pieces was");
  assert.ok(/data-ag="libopen"/.test(html) && /data-ag="libstatus"/.test(html) && /data-ag="libdel"/.test(html),
            "Open, Back to draft and Delete all still there");
  assert.ok(html.indexOf('class="ag-mile cur"') === -1, "nothing is being made now");
  assert.ok((html.match(/class="ag-mile done"/g) || []).length === 5, "all five open the panel, which is how you reach a finished plan");
});

test("a row from the payload the server sent BEFORE milestones renders exactly as it did", () => {
  /* no status, no milestones: the shape library_list returned until 2026-09-09 */
  const old = [{ id: "2026-09-01-hiring", title: "Hiring", words: 1200, primary_keyword: "hiring",
                 created_at: "2026-09-01T09:00:00Z" }];
  const html = A.agLibraryHtml(old);
  assert.ok(/<span class="pill p-mut">draft<\/span>/.test(html), "the muted draft pill, word for word as before");
  assert.ok(html.indexOf('class="ag-miles"') === -1, "and no strip at all, rather than an empty or broken one");
  assert.ok(html.indexOf("<span>1,200 words</span>") !== -1, "the word count, not a count of pieces");
  assert.ok(html.indexOf("<span>started ") === -1, "and no start time, because a saved row has no run to start");
  assert.ok(/data-ag="libopen" data-arg="2026-09-01-hiring"/.test(html), "Open");
  assert.ok(/data-ag="libstatus" data-arg="2026-09-01-hiring" data-status="ready">Mark ready</.test(html), "Mark ready");
  assert.ok(/data-ag="libdel" data-arg="2026-09-01-hiring"/.test(html), "Delete");
  assert.ok(!/class="ag-row writing"/.test(html), "and it is not mistaken for something in flight");
});

test("the three states are told apart by more than one thing each", () => {
  const row = (status) => A.agLibraryHtml([{ id: "x", title: "T", status, words: 10,
                                             created_at: "2026-09-09T09:00:00Z", milestones: LIB_MILES() }]);
  const w = row("writing"), r = row("ready"), p = row("published");
  /* the pill colour */
  assert.ok(/pill p-acc/.test(w) && /pill p-ok/.test(r) && /pill p-acc/.test(p), "each draws a pill from the existing set");
  /* the word */
  assert.ok(/>writing</.test(w) && />ready to read</.test(r) && />published</.test(p), "and each says a different word");
  /* the turning marker and the accent edge belong to writing ALONE, which is what makes a
     half-made row read as purposeful rather than as a failure */
  assert.ok(/class="spin"/.test(w), "writing turns");
  assert.ok(!/class="spin"/.test(r) && !/class="spin"/.test(p), "nothing else does");
  assert.ok(/ag-row writing/.test(w) && !/ag-row writing/.test(r) && !/ag-row writing/.test(p),
            "and only writing carries the accent edge");
  /* and only writing names a step as happening now */
  assert.ok(/ag-mile cur/.test(w) && !/ag-mile cur/.test(r) && !/ag-mile cur/.test(p),
            "a stopped or finished row's gaps are gaps, not promises");
});

test("every colour the new Library rules use is a token, so both themes follow", () => {
  const css = fs.readFileSync(path.join(__dirname, "static", "agents.css"), "utf8");
  const block = css.slice(css.indexOf(".ag-row.writing"), css.indexOf(".ag-form{"));
  assert.ok(block.length > 200, "the live-Library block is there");
  const literals = block.match(/#[0-9a-fA-F]{3,8}\b|\brgba?\(/g);
  assert.strictEqual(literals, null, "a raw colour crept in: " + literals);
  assert.ok(/\.ag-row\.writing\{border-color:var\(--acc\)/.test(block), "the writing edge is the accent token");
  assert.ok(/\.ag-mile\.done i\{background:var\(--ok\)\}/.test(block), "a done milestone is the ok token");
  assert.ok(/\.ag-mile\.cur\{color:var\(--acc\)/.test(block), "the one being made now is the accent token");
  assert.ok(/prefers-reduced-motion[^]*\.ag-mile\.cur i\{animation:none\}/.test(css),
            "and the movement is dropped for anyone who asked for that");
});

/* ── the artifact that is announced but never waited on ────────────────────── */
test("artifact_ready draws a quiet line with NONE of the checkpoint chrome", () => {
  const evs = [{ t: "2026-09-09T09:00:00Z", type: "artifact_ready", view: "research_brief",
                 artifact: "research.json", label: "the research" }];
  const out = A.agStepsFromEvents(evs, { status: "running" });
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].kind, "ready", "its own kind, not the waiting 'artifact' kind");
  assert.strictEqual(out[0].live, undefined, "nothing is live about it, so nothing waits on it");
  const html = A.agEntryHtml(out[0], { run_id: "r1" });
  assert.ok(/class="ag-step quiet"/.test(html), "it borrows the log_step note vocabulary: " + html);
  assert.ok(/class="ag-note"/.test(html), "a note, not a card");
  assert.ok(!/ag-card/.test(html) && !/ag-artcard/.test(html), "no checkpoint card");
  assert.ok(!/data-ag="approve/.test(html) && !/Go ahead/.test(html), "no approve button");
  assert.ok(!/Waiting for you/.test(html) && !/Review/.test(html), "and it never says it is waiting");
  assert.ok(!/p-warn/.test(html) && !/var\(--warn/.test(html), "no warning colour");
  assert.strictEqual(A.agGlyph(out[0]), "", "and no icon, only the small grey dot .quiet draws");
});

test("the announced artifact is clickable, to the same panel the checkpoint used to open", () => {
  const e = { kind: "ready", artifact: "research.json", view: "research_brief", label: "the research", t: "t" };
  const html = A.agEntryHtml(e, { run_id: "r7" });
  assert.ok(/Ready to read: /.test(html), "the copy says it exists, not that it needs him: " + html);
  assert.ok(/data-ag="open" data-arg="research.json"[^>]*data-view="research_brief"[^>]*data-run="r7"/.test(html.replace(/\s+/g, " ")),
            "one link, carrying the artifact, the view and the run");
  assert.ok(/>the research</.test(html), "and the label the server wrote, used as it came");
  const open = A.agEntryHtml(e, { run_id: "r7", panel: { name: "research.json", run_id: "r7" } });
  assert.ok(/ag-openlink open/.test(open), "the one already on screen marks itself");
});

test("an artifact_ready in the middle of a run does not become the end of the transcript", () => {
  const evs = [
    { t: "2026-09-09T09:00:00Z", type: "step_started", id: "s1", label: "Researching", tool: "run_research", stage: "research" },
    { t: "2026-09-09T09:04:00Z", type: "step_finished", id: "s1", ms: 240000 },
    { t: "2026-09-09T09:04:01Z", type: "artifact_ready", view: "research_brief", artifact: "research.json", label: "the research" },
    { t: "2026-09-09T09:04:02Z", type: "step_started", id: "s2", label: "Planning", tool: "plan_article", stage: "blueprint" },
  ];
  const out = A.agStepsFromEvents(evs, { status: "running" });
  /* JSON, not deepStrictEqual: the module runs in a vm realm, so its arrays are not the host's */
  assert.strictEqual(JSON.stringify(out.map(e => e.kind)), '["step","ready","step"]', "it sits where it happened");
  assert.strictEqual(out[1].stage, "research", "stamped with the stage that was open, so it groups with it");
  assert.strictEqual(out[2].state, "run", "and the run carried straight on underneath it");
  const groups = A.agStageGroups(out);
  const research = groups.find(g => g.stage === "research");
  assert.ok(research && !research.waiting, "the research stage is NOT marked as waiting for him");
});

/* ── the Asset ideas tab: what "Next up" is offering ──────────────────────── */
/* "okay next up, oh this is the next topic, all of that's not clear" (owner, 2026-09-09). Two
   uppercase words over a title read as a section label, not an offer: it said neither WHICH idea
   this is nor what pressing either button would do. */
const ASSETS = {
  built: true, total: 1892, counts: { open: 214, done: 6, dropped: 3 },
  methods_line: "All three methods contributed.",
  next: { id: "a-17", title: "The hiring-assessment benchmark report",
          angle: "Nobody has published the pass rates by role.",
          format: "Original research", method: ["competitors", "trends"],
          linkability: { score: 3, of: 4 } },
  rows: [{ id: "a-17", title: "The hiring-assessment benchmark report", angle: "Pass rates by role.",
           status: "open", format: "Original research", method: ["competitors"],
           linkability: { score: 3, of: 4 }, reuse: { verdict: "no" } }],
};
test("the next idea says which idea it is, not just Next up", () => {
  const a = agReset(); a.assetFilter = "open"; a.assetOffset = 0;
  const html = A.agAssetsHtml(ASSETS, a);
  assert.ok(/The idea to write next/.test(html), "it is named as an idea, not labelled Next up");
  assert.ok(!/>Next up</.test(html), "and the bare label is gone");
  assert.ok(/top of the 214 still to write/.test(html), "and it says where this one came from");
  assert.ok(/The hiring-assessment benchmark report/.test(html), "the idea itself");
});
test("the next idea's evidence is labelled, not one dot-separated run", () => {
  const a = agReset(); a.assetFilter = "open"; a.assetOffset = 0;
  const html = A.agAssetsHtml(ASSETS, a);
  const card = html.slice(html.indexOf("ag-nextidea"), html.indexOf("ag-editrow", html.indexOf("ag-nextidea")));
  assert.ok(/<dt>Shape<\/dt><dd>Original research<\/dd>/.test(card), "the shape is under its own label");
  assert.ok(/<dt>Found by<\/dt>/.test(card) && /the competitor study and what your audience argues about/.test(card),
            "and so is where it came from, in words: " + card.slice(-260));
  assert.ok(/<dt>Would anyone cite it<\/dt><dd>3 out of 4<\/dd>/.test(card),
            "and the score is attached to the question it answers");
});
test("the next idea says what each of its two buttons does", () => {
  const a = agReset(); a.assetFilter = "open"; a.assetOffset = 0;
  const html = A.agAssetsHtml(ASSETS, a);
  assert.ok(/starts the research on it/.test(html), "what Write this one does");
  assert.ok(/drops it off the sheet and the next-ranked idea moves up/.test(html), "and what Not this one does");
  assert.ok(/data-ag="ideawrite"/.test(html) && /data-ag="ideadrop"/.test(html), "both still act");
});
test("nothing left to write draws no next-idea card at all", () => {
  const a = agReset(); a.assetFilter = "open"; a.assetOffset = 0;
  const html = A.agAssetsHtml(Object.assign({}, ASSETS, { next: null }), a);
  assert.ok(!/ag-nextidea/.test(html) && /Nothing left to write/.test(html));
});

/* ── the CSS the layout leans on ───────────────────────────────────────────── */
const CSS = fs.readFileSync(path.join(__dirname, "static", "agents.css"), "utf8");

/* THE LOOK (owner, 2026-09-09): section headings "darker and bigger", table borders darker "so a
   section is visibly a section". Both are overrides inside .ag against panel.css's global
   h3.sec (10px uppercase at --faint) and against --line-soft, which on the light theme is very
   nearly the page colour. No new colour system: every value below is an existing token. */
test("section headings on this screen are darker and bigger than the global micro-label", () => {
  const rule = CSS.slice(CSS.indexOf(".ag .ag-view h3.sec{"), CSS.indexOf("}", CSS.indexOf(".ag .ag-view h3.sec{")));
  assert.ok(rule.length > 20, "the override exists");
  assert.ok(/var\(--ink\)/.test(rule), "darker: --ink, not the global --faint");
  assert.ok(/text-transform:none/.test(rule), "and not shouted");
  const size = /\b(\d+(?:\.\d+)?)px\/[\d.]+/.exec(rule);
  assert.ok(size && Number(size[1]) >= 13, "bigger than the global 10px, got " + (size && size[1]));
  assert.ok(/border-bottom:1px solid var\(--line\)/.test(rule), "with a rule under it, so a section looks like one");
});
test("the catalogue table's borders are the darker line, and it closes", () => {
  const tbl = CSS.slice(CSS.indexOf(".ag-pages{"), CSS.indexOf(".ag-pages td.n"));
  assert.ok(/border-top:1px solid var\(--line\)/.test(tbl) && /border-bottom:1px solid var\(--line\)/.test(tbl),
            "the table is bounded top and bottom");
  assert.ok(/\.ag-pages th\{[^}]*border-bottom:1px solid var\(--line\)/.test(tbl),
            "and the head sits on the darker rule, not --line-soft");
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|\brgba?\(/.test(tbl), "still no hardcoded colour");
});
test("every class the reworked next-idea card uses is actually styled", () => {
  [".ag-nextidea .nl", ".ag-nextidea .nl .nq", ".ag-nextidea .nf", ".ag-nextidea .nf dt",
   ".ag-nextidea .nf dd", ".ag-nextidea .nh"].forEach(c => {
    assert.ok(CSS.indexOf(c) !== -1, c + " has no rule in agents.css");
  });
  const card = CSS.slice(CSS.indexOf(".ag-nextidea{"), CSS.indexOf(".ag-idea{"));
  assert.ok(!/#[0-9a-fA-F]{3,8}\b|\brgba?\(/.test(card), "no hardcoded colour on the card");
});
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


/* ── the Prompts tab ───────────────────────────────────────────────────────────
   His own writing rules, changed without a developer. What these guard:

     · the tab offers exactly the fourteen prompts he asked for, and none of the
       three he named as skipped (slop, links, clean);
     · the FORMAT RULES come before the architect in the flow, because they are
       not part of it, they are what it obeys;
     · a save reaches the server whole, and a refused save keeps his words on
       screen with the reason beside them;
     · Reset puts a prompt back to what shipped;
     · the Library says what shape each article was written to.

   The list, the flow and the plain names all live in seo_agent/prompts/store.py,
   so they are READ OUT OF THAT FILE here rather than typed a second time: a copy
   in a test is a copy that drifts, and then the test passes while the screen is
   wrong. The Python half (an edit is what the next run loads, Reset restores the
   shipped text, a lost {{TOKEN}} is refused) runs at the foot of this file
   through the same interpreter run_all.sh picks. */
const PSTORE = fs.readFileSync(path.join(__dirname, "seo_agent", "prompts", "store.py"), "utf8");

/* the names in a Python list of ("name", "Title", "note") triples */
function pyNames(listName){
  const m = PSTORE.match(new RegExp("\\n" + listName + " = \\[([\\s\\S]*?)\\n\\]"));
  assert.ok(m, listName + " is not in seo_agent/prompts/store.py");
  return (m[1].match(/\("([^"]+)",/g) || []).map(x => x.slice(2, -2));
}
/* the station titles of FLOW, in order */
function pyFlowTitles(){
  const m = PSTORE.match(/\nFLOW = \[([\s\S]*?)\n\]\n/);
  assert.ok(m, "FLOW is not in seo_agent/prompts/store.py");
  return (m[1].match(/"title": "([^"]+)"/g) || []).map(x => x.slice(10, -1));
}
/* the payload the server sends, rebuilt from the same file the server builds it from */
function promptsPayload(edited){
  edited = edited || [];
  const row = n => ({ name: n, title: n.split("/").pop(), note: "what it decides",
                      edited: edited.indexOf(n) >= 0, lines: 100, words: 900 });
  return {
    flow: pyFlowTitles().map(t => ({ key: t.toLowerCase(), title: t, rules: t === "The format rules",
                                     steps: ["a phrase", "another phrase"] })),
    groups: [{ key: "formats", title: "The format rules", note: "eight shapes", prompts: pyNames("FORMATS").map(row) },
             { key: "writing", title: "The writing prompts", note: "how it writes", prompts: pyNames("WRITING").map(row) }],
    edited: edited,
  };
}

test("the tab offers the eight format rulebooks and the six writing prompts, and nothing else", () => {
  const formats = pyNames("FORMATS"), writing = pyNames("WRITING");
  assert.strictEqual(formats.length, 8, "eight archetypes, got " + formats.length + ": " + formats);
  assert.strictEqual(writing.length, 6, "six writing prompts, got " + writing.length + ": " + writing);
  const html = A.agPromptsHtml(promptsPayload(), A.agS());
  formats.concat(writing).forEach(n => assert.ok(html.indexOf('data-arg="' + n + '"') >= 0, "missing from the tab: " + n));
  /* every one of them is a real file in the bundle, so nothing on this screen opens onto nothing */
  formats.concat(writing).forEach(n =>
    assert.ok(fs.existsSync(path.join(__dirname, "seo_agent", "prompts", n + ".md")), "no such prompt file: " + n));
});

test("the three he said to skip are not on the tab: slop, links, clean", () => {
  const all = pyNames("FORMATS").concat(pyNames("WRITING")).join(" ");
  ["slop", "slop-rules", "inline-links", "external-links", "clean"].forEach(n =>
    assert.ok(all.indexOf(n) < 0, "the tab offers a prompt he told us to skip: " + n));
  const html = A.agPromptsHtml(promptsPayload(), A.agS());
  ["slop", "inline-links", "external-links", "clean"].forEach(n =>
    assert.ok(html.indexOf('data-arg="write/' + n + '"') < 0, "the skipped prompt reached the screen: " + n));
});

test("the format rules come BEFORE the architect in the flow, and after the planner", () => {
  const titles = pyFlowTitles();
  const rules = titles.indexOf("The format rules"), arch = titles.indexOf("Architect"), plan = titles.indexOf("Planner");
  assert.ok(rules >= 0 && arch >= 0 && plan >= 0, "the flow is missing a station: " + titles);
  assert.ok(plan < rules && rules < arch, "the order is wrong: " + titles.join(" -> "));
  const html = A.agFlowHtml(promptsPayload().flow);
  assert.ok(html.indexOf("The format rules") < html.indexOf("Architect"), "and on screen the architect still comes first");
  /* the format-rules station carries the accent, so the eye lands on the one he can change */
  assert.ok(/ag-flowrow rules/.test(html), "the format rules are not marked out in the flow");
});

test("nothing in the flow is marked as missing or not running", () => {
  const html = A.agFlowHtml(promptsPayload().flow).toLowerCase();
  ["not running", "not built", "missing", "skipped", "coming soon"].forEach(w =>
    assert.ok(html.indexOf(w) < 0, "the flow labels a station " + w));
  /* the three stations built in this release are all in it, as stations like any other */
  const titles = pyFlowTitles().join(" | ");
  assert.ok(/Voices from the field/.test(titles), "voices from the field is not a station: " + titles);
});

test("nothing about the word count is on this tab", () => {
  const a = A.agS(); a.panel = null;
  const html = A.agPromptsHtml(promptsPayload(), a).toLowerCase();
  ["word count", "words per", "how long", "2,100", "2100", "word band", "target length"].forEach(w =>
    assert.ok(html.indexOf(w) < 0, "the word count leaked onto the Prompts tab: " + w));
});

test("a prompt he changed says so, and the sidebar counts them", () => {
  const p = promptsPayload(["write/readable"]);
  const html = A.agPromptsHtml(p, A.agS());
  assert.ok(/p-acc">yours/.test(html), "an edited prompt is not marked as his");
  assert.ok(/1 changed by you/.test(html), "the heading does not say how many he changed");
  const a = A.agS(); a.prompts = p; a.view = "prompts";
  const side = A.agSideHtml(a);
  assert.ok(/data-arg="prompts"/.test(side), "Prompts is not in the sidebar");
  assert.ok(/data-arg="prompts"[^>]*aria-current="true"/.test(side), "the open tab is not marked current");
});

test("the panel lists the placeholders the agent fills, and says not to lose them", () => {
  const html = A.agPromptHtml({ name: "write/blend", title: "Blend", note: "n", text: "hi {{ARTICLE}}",
                                shipped: "hi {{ARTICLE}}", edited: false, filled: true, tokens: ["ARTICLE", "BRAND"] }, null);
  assert.ok(/\{\{ARTICLE\}\}/.test(html) && /\{\{BRAND\}\}/.test(html), "the placeholders are not shown");
  assert.ok(/Keep every one of them/.test(html), "and he is not told to keep them");
  /* a format rulebook has no blanks of its own: the two names in its developer header describe
     which slot the file feeds, and warning him to keep a placeholder it does not have would be a
     warning about nothing */
  const rule = A.agPromptHtml({ name: "write/formats/listicle", title: "Listicle", note: "n", text: "x",
                                shipped: "x", edited: false, filled: false, tokens: ["FORMAT_RULE"] }, null);
  assert.ok(!/Keep every one of them/.test(rule), "a rulebook is told to keep placeholders it has not got");
});

test("the Library says what shape each article was written to", () => {
  const html = A.agLibraryHtml([{ id: "x", title: "Cost per hire", status: "ready", words: 2400,
                                  format: "listicle", format_label: "Listicle", created_at: "2026-09-09T10:00:00Z" }]);
  assert.ok(/Listicle/.test(html), "the format is not on the row");
  /* a row whose run never reached the router shows no format rather than a guess */
  const none = A.agLibraryHtml([{ id: "y", title: "Half done", status: "writing", created_at: "2026-09-09T10:00:00Z" }]);
  assert.ok(!/Listicle/.test(none) && !/undefined/.test(none), "an unrouted row invented one: " + none);
});

test("the prompt list scrolls in its own box and does not take the screen", () => {
  const flat = CSS.replace(/\s+/g, "");
  const m = flat.match(/\.ag-promptlist\{[^}]*max-height:(\d+)vh/);
  assert.ok(m, ".ag-promptlist has no max-height, so it fills the screen");
  assert.ok(Number(m[1]) <= 50, "the list is still tall: " + m[1] + "vh");
  assert.ok(/\.ag-promptlist\{[^}]*overflow-y:auto/.test(flat), "and it does not scroll on its own");
  /* every colour on this screen comes from a token, so light, dark and a changed accent follow */
  const mine = CSS.slice(CSS.indexOf("/* ── the Prompts tab"));
  const literals = mine.match(/#[0-9a-fA-F]{3,8}\b|\brgba?\(/g) || [];
  assert.strictEqual(literals.length, 0, "a hard-coded colour on the Prompts tab: " + literals);
});


/* ── the team workspace (design/WORKSPACE-PLAN.md) ─────────────────────────────
   Section 1 is the acceptance test and it is written in the owner's own words, so these
   assert the words: "Go to Supabase", two boxes, a Create button, a spinner, then the link
   with a copy button. Section 10 is the bar, and the three tests at the end of this block are
   that bar: success only from verify, a failure that says what to do, and a token that goes
   nowhere near S.ag or the screen. */

const WSF = { installed: true, configured: false, workspace: null, me: null, members: [],
              link: "", sync: null, job: null };
function wsdoc(over){ return Object.assign({}, WSF, over || {}); }

test("not connected, the workspace offers exactly two ways in and promises nothing else", () => {
  const html = A.agWsHtml(wsdoc(), null);
  assert.ok(/Team workspace/.test(html), "it has a section of its own at the top of Connections");
  assert.ok(/data-ag="wscreate"/.test(html) && /data-ag="wsjoin"/.test(html), "create and join");
  assert.ok(!/data-ag="wscopylink"/.test(html), "there is no link to copy yet");
  assert.ok(/nobody presses sync/.test(html), "and it says the thing the plan promises");
});

test("Create asks for the two things section 1 names, and a way to go and get them", () => {
  const html = A.agWsHtml(wsdoc(), { mode: "create" });
  assert.ok(/Go to Supabase/.test(html), "the button that opens the browser");
  assert.ok(/href="https:\/\/supabase\.com\/dashboard\/projects"/.test(html), "and it really goes there");
  assert.ok(/data-agws="url"/.test(html) && /Project URL/.test(html), "box one");
  assert.ok(/data-agws="key"/.test(html) && /sb_publishable_…/.test(html), "box two, the publishable one");
  assert.ok(/data-ag="wsgo"/.test(html) && />Create</.test(html), "and the Create button");
});

/* THE TOKEN BOX IS OPTIONAL AND SAYS SO. There is no access token on the owner's machine and
   there may never be one, so a step that demanded one before showing the setup script would
   put a locked door in front of the open one. It is a third box, marked optional, with the one
   line that says what it does and that it is not kept. */
test("the access token is optional, says what it is for, and is never echoed back", () => {
  const html = A.agWsHtml(wsdoc(), { mode: "create" });
  assert.ok(/data-agws="token"/.test(html) && /type="password"/.test(html));
  assert.ok(/optional/.test(html), "marked optional");
  assert.ok(/thrown away|never written to disk|never kept/i.test(html), "and says it is not kept");
  assert.ok(/leave this empty/i.test(html), "and that going without one is a real choice");
  const box = html.slice(html.indexOf('data-agws="token"'));
  assert.ok(!/value=/.test(box.slice(0, 200)), "the token input carries no value attribute at all");
  assert.ok(!/\(set\)/.test(html), "and no (set) placeholder: nothing is ever set");
});

test("creating draws a spinner that says what it is doing, and a bar it does not have to watch", () => {
  const html = A.agWsHtml(wsdoc({ job: { kind: "create", phase: "tables", step: "Creating your workspace", pct: 5 } }), null);
  assert.ok(/Creating your workspace/.test(html), "his words, on screen");
  assert.ok(/class="spin"/.test(html), "the spinner");
  assert.ok(/ag-bar/.test(html));
  assert.ok(!/data-ag="wscopylink"/.test(html), "and no link yet: nothing has been verified");
});

test("uploading the pack is its own step, so a long silence is never unexplained", () => {
  const html = A.agWsHtml(wsdoc({ job: { kind: "create", phase: "pack", step: "Uploading the knowledge pack", pct: 60 } }), null);
  assert.ok(/Uploading the knowledge pack/.test(html));
  assert.ok(/width:60%/.test(html));
});

/* THE BAR, first half: "created" is drawn from ONE thing, a server job that reached `done`,
   and the server reaches `done` only after schema.verify() has seen every table. There is no
   branch in the renderer that can print it from anything else. */
test("nothing says the workspace is ready until the server says the job is done", () => {
  const mid = A.agWsHtml(wsdoc({ configured: true, job: { kind: "create", phase: "pack", pct: 60 } }), null);
  assert.ok(!/Your workspace is ready/.test(mid), "not while the pack is still going up");
  const fell = A.agWsHtml(wsdoc({ configured: true, job: { kind: "create", phase: "paste", paste: { sql: "create table x();", editor_url: "https://e" } } }), null);
  assert.ok(!/Your workspace is ready/.test(fell), "and not while the script is still waiting to be pasted");
  const done = A.agWsHtml(wsdoc({ configured: true, link: "sutra-ws-abc",
    workspace: { name: "Testlify", url: "https://abcdefghijklmnop.supabase.co", id: "w1" },
    job: { kind: "create", phase: "done", finished_at: Date.now() / 1000 } }), null);
  assert.ok(/Your workspace is ready/.test(done) && /every table checked/.test(done));
});

/* NO UPDATE BUTTON, and this asserts its ABSENCE on purpose (2026-09-10).

   There was one for about an hour. A workspace created by this build is born current, so a
   migration can only ever apply to one made before the change that needs it — on the day this was
   written, exactly one workspace in the world. Database maintenance on a person's screen for that
   was the wrong trade, and the owner said so.

   The signal itself is kept, because the engine still needs to know: a workspace a version behind
   is still ok, everything else keeps syncing, and sync.push declines rather than queues a row that
   workspace cannot take. What must not come back is a button asking somebody to act on it. */
const WS_CONNECTED = { configured: true, link: "sutra-ws-eyJ1IjoiaHR0cHM6Ly94In0",
  workspace: { name: "Testlify", url: "https://abcdefghijklmnop.supabase.co", id: "w1" },
  members: [{ member_id: "m1", name: "Devansh", last_seen_at: new Date().toISOString() }],
  me: { member_id: "m1", name: "Devansh" }, sync: { pending: 0, pack_state: "idle" } };

test("a workspace a version behind is drawn as connected, and is never asked to do maintenance", () => {
  const ws = wsdoc(Object.assign({}, WS_CONNECTED, {
    verify: { ok: true, needs_update: true, schema_version: 2 },
    sync: { pending: 1, pack_state: "idle",
            needs_update: { kind: "brand_inputs", have: 2, needs: 3, why: "Waiting." } } }));
  const html = A.agWsHtml(ws, null);
  assert.ok(!/data-ag="wsupdate"/.test(html), "no update button, from either signal");
  assert.ok(!/An update is available/.test(html) && !/Update workspace/.test(html));
  assert.ok(!/version 2/.test(html), "and no schema versions on a person's screen");
  assert.ok(/dot ok"><\/i>connected/.test(html), "it is connected, because it is");
  assert.ok(!/not finished/.test(html), "a newer Sutra growing a table is not a broken workspace");
  assert.ok(/data-ag="wscopylink"/.test(html), "and everything it could already do, it still does");
});

test("once it is made, the link is on the tab with a copy button, and stays there", () => {
  const ws = wsdoc({ configured: true, link: "sutra-ws-eyJ1IjoiaHR0cHM6Ly94In0",
    workspace: { name: "Testlify", url: "https://abcdefghijklmnop.supabase.co", id: "w1" },
    members: [{ member_id: "m1", name: "Devansh", last_seen_at: new Date().toISOString() }],
    me: { member_id: "m1", name: "Devansh" }, sync: { pending: 0, pack_state: "idle" } });
  const fresh = A.agWsHtml(ws, null);
  assert.ok(/sutra-ws-eyJ1IjoiaHR0cHM6Ly94In0/.test(fresh) && /data-ag="wscopylink"/.test(fresh));
  /* and a fortnight later, with no job left anywhere, it is still there */
  const later = A.agWsHtml(Object.assign({}, ws, { job: null }), null);
  assert.ok(/data-ag="wscopylink"/.test(later), "the link does not leave with the job that made it");
  assert.ok(!/Your workspace is ready/.test(later), "only the greeting does");
});

test("the resting state is the four things section 3 asks for and nothing more", () => {
  const html = A.agWsHtml(wsdoc({ configured: true, link: "sutra-ws-abc",
    workspace: { name: "Testlify", url: "https://abcdefghijklmnop.supabase.co", id: "w1" },
    me: { member_id: "m1", name: "Devansh" },
    members: [{ member_id: "m1", name: "Devansh", last_seen_at: new Date().toISOString() },
              { member_id: "m2", name: "Ravi", last_seen_at: new Date(Date.now() - 3600000).toISOString() }],
    sync: { pending: 0, pack_state: "idle" } }), null);
  assert.ok(/Testlify/.test(html), "the name");
  assert.ok(/Devansh/.test(html) && /Ravi/.test(html) && /2 people/.test(html), "who is in it");
  assert.ok(/<i>you<\/i>/.test(html), "and which one he is");
  assert.ok(/an hour ago/.test(html), "when the other one was last seen");
  assert.ok(/data-ag="wscopylink"/.test(html), "the link with its copy button");
  assert.ok(/Up to date/.test(html), "and what is happening right now");
});

test("what is happening right now is read from the server, never guessed", () => {
  assert.strictEqual(A.agWsNowLine({ pending: 0, pack_state: "idle" }), "Up to date");
  assert.strictEqual(A.agWsNowLine({ pending: 0, pack_state: "building" }), "Updating the copy for new joiners");
  assert.strictEqual(A.agWsNowLine({ pending: 3, pack_state: "idle" }), "3 changes waiting to go up");
  assert.strictEqual(A.agWsNowLine({ pending: 1, pack_state: "idle" }), "1 change waiting to go up");
  assert.strictEqual(A.agWsNowLine(null), "", "nothing known, nothing claimed");
  assert.strictEqual(A.agWsNowLine({ pending: 0, pack_state: "unknown" }), "",
                     "and 'unknown' is not quietly rounded up to 'Up to date'");
});

/* SECTION 2, THE OWNER'S RULING. He does not wait for the pack. The click finishes; this line
   appears at the foot of whatever screen he is on and leaves on its own. Never a modal, never a
   bar, never a thing to dismiss -- and never drawn from a guess: it is on exactly while the
   server says the pack is being rebuilt. */
test("the quiet line is a line, is driven by the server, and is nothing else", () => {
  const a = agReset();
  a.ws = { sync: { pending: 0, pack_state: "building" } };
  const on = A.agQuietHtml(a);
  assert.ok(/Updating the copy for new joiners/.test(on), "his sentence, exactly");
  assert.ok(!/<button|role="dialog"|ag-bar|%/.test(on), "no button, no modal, no progress bar");
  a.ws = { sync: { pending: 0, pack_state: "idle" } };
  assert.strictEqual(A.agQuietHtml(a), "", "and it leaves when the server says the pack is done");
  a.ws = null;
  assert.strictEqual(A.agQuietHtml(a), "", "with nothing known it says nothing");
});

test("joining asks for the link and a name, and warns how long the download is", () => {
  const html = A.agWsHtml(wsdoc(), { mode: "join" });
  assert.ok(/data-agws="link"/.test(html) && /data-agws="name"/.test(html));
  assert.ok(/data-ag="wsjoingo"/.test(html) && />Done</.test(html), "the button is Done, as he said");
  assert.ok(/five minutes/.test(html));
});

/* "a real progress bar for the ~5 minute download (bytes of total, not a fake spinner)" */
test("the join bar is real bytes, and draws no bar at all when the total is not known", () => {
  const real = A.agWsHtml(wsdoc({ job: { kind: "join", phase: "download", step: "Downloading the team's knowledge",
                                         done_bytes: 26214400, total_bytes: 104857600, pct: 25 } }), null);
  assert.ok(/25 MB of 100 MB/.test(real), "bytes of total, in words a person reads");
  assert.ok(/ag-bar/.test(real) && /width:25%/.test(real));
  const blind = A.agWsHtml(wsdoc({ job: { kind: "join", phase: "download", done_bytes: 1048576, total_bytes: 0 } }), null);
  assert.ok(/1.0 MB so far/.test(blind) && /total is not known/.test(blind));
  assert.ok(!/ag-bar/.test(blind), "a bar that cannot mean anything is not drawn");
});

test("a finished join says the thing that actually changed for him", () => {
  const html = A.agWsHtml(wsdoc({ configured: true, link: "sutra-ws-abc",
    workspace: { name: "Testlify", url: "https://x.supabase.co", id: "w1" },
    members: [], sync: { pending: 0, pack_state: "idle" },
    job: { kind: "join", phase: "done", finished_at: Date.now() / 1000 } }), null);
  assert.ok(/You are on the team/.test(html));
  assert.ok(/Library, ideas and prompts are the team's/.test(html));
});

/* THE SETUP SCRIPT IS A ROUTE, NOT AN ERROR STATE. Whether it came up because no token was
   given, because the script half-applied, or because the tables are there and the knowledge
   bucket is not, it is drawn the same way: a heading, the steps, the script, one button. */
test("the setup script is drawn as a route, with schema's own reason above it", () => {
  const html = A.agWsHtml(wsdoc({ job: { kind: "create", phase: "paste", paste: {
    sql: "create table if not exists public.workspace ();",
    editor_url: "https://supabase.com/dashboard/project/abc/sql/new",
    why: "Sutra has no access token, so it cannot create the tables for you. Nothing has been created yet." } } }), null);
  assert.ok(/Run the setup script/.test(html), "its own heading, not an error heading");
  assert.ok(!/could not|failed|went wrong|Cancel the/i.test(html.slice(0, html.indexOf("<ol"))),
            "and nothing above the steps reads as a failure");
  assert.ok(/Sutra has no access token/.test(html), "schema's reason, verbatim");
  assert.ok(/create table if not exists public\.workspace/.test(html), "the script itself");
  assert.ok(/data-ag="wscopysql"/.test(html), "with a copy button");
  assert.ok(/href="https:\/\/supabase\.com\/dashboard\/project\/abc\/sql\/new"/.test(html), "and a link to the editor");
  assert.ok(/data-ag="wssqldone"/.test(html) && /I've run it/.test(html), "and one way onward");
  assert.ok(!/sbp_/.test(html), "and no token anywhere in it");
});

/* THE STATE THE PLAN'S OWN RISK NOTE NAMES. The storage policies do not always attach, and the
   tables survive when they do not. That workspace has a URL, a key and an id -- everything
   that reads settings calls it connected -- and nobody can ever join it. */
test("tables but no bucket reads as not finished, never as connected and never as a fresh start", () => {
  const html = A.agWsHtml(wsdoc({ configured: true, link: "sutra-ws-abc",
    workspace: { name: "Testlify", url: "https://abcdefghijklmnop.supabase.co", id: "w1" },
    members: [], sync: { pending: 0, pack_state: "idle" },
    verify: { ok: false, bucket: false, missing: [],
              reason: "The tables are there but the knowledge bucket is not, so no teammate could download the knowledge pack." } }), null);
  assert.ok(/not finished/.test(html), "it says so");
  assert.ok(!/>connected</.test(html), "and never says connected");
  assert.ok(/knowledge bucket is not/.test(html), "with verify's own sentence, which names the real thing");
  assert.ok(!/data-ag="wscreate"/.test(html), "not a fresh start either: no Create button");
  assert.ok(/data-ag="wssqldone"/.test(html), "and a way to check again once it is fixed");
});

test("a workspace nobody has been able to check yet is not called broken", () => {
  const html = A.agWsHtml(wsdoc({ configured: true, link: "sutra-ws-abc",
    workspace: { name: "Testlify", url: "https://x.supabase.co", id: "w1" },
    members: [], sync: { pending: 0, pack_state: "idle" }, verify: null }), null);
  assert.ok(!/not finished/.test(html), "a question nobody has asked has no answer");
  assert.ok(/data-ag="wscopylink"/.test(html));
});

/* SECTION 10: every failure says what failed and what to do, and no failure leaves a half-made
   workspace on screen as if it had worked. */
test("a failure names what failed and what to do, and claims nothing was made", () => {
  const html = A.agWsHtml(wsdoc({ job: { kind: "join", phase: "failed", error: {
    what: "That link points at a project that is not set up as a workspace — members missing.",
    do: "Ask whoever set it up to send the link from their Connections tab again." } } }), null);
  assert.ok(/not set up as a workspace/.test(html), "what failed");
  assert.ok(/Ask whoever set it up/.test(html), "what to do");
  assert.ok(/nothing was left half-made/.test(html));
  assert.ok(/data-ag="wsretry"/.test(html) && /data-ag="wscancel"/.test(html));
  assert.ok(!/data-ag="wscopylink"/.test(html), "and no link: there is nothing to share");
});

/* A create whose tables verified but whose pack upload stumbled is NOT a failed create -- nine
   real tables exist and the link works. Saying otherwise would throw them away. */
test("a workspace that was made but whose pack stalled is drawn as made, with the caveat", () => {
  const html = A.agWsHtml(wsdoc({ configured: true, link: "sutra-ws-abc",
    workspace: { name: "Testlify", url: "https://x.supabase.co", id: "w1" }, members: [],
    sync: { pending: 0, pack_state: "idle" },
    job: { kind: "create", phase: "done", finished_at: Date.now() / 1000,
           error: { what: "the knowledge pack did not finish uploading", do: "Press Update on the Knowledge tab." } } }), null);
  assert.ok(/Your workspace is ready/.test(html), "it was made, and verify said so");
  assert.ok(/data-ag="wscopylink"/.test(html), "the link works and is offered");
  assert.ok(/did not finish uploading/.test(html) && /Press Update/.test(html), "and the caveat is not hidden");
});

test("the workspace section is the first thing on the Connections tab", () => {
  const html = A.agConnectionsHtml({ dataforseo_login: true }, { model_provider: "claude-cli" }, null,
                                   wsdoc(), null);
  assert.ok(html.indexOf("Team workspace") < html.indexOf("DataForSEO"), "above the agent's own keys");
  assert.ok(html.indexOf("Team workspace") < html.indexOf(">Model<"));
  /* three older tests call this with three arguments; it must still draw */
  const old = A.agConnectionsHtml({ dataforseo_login: true }, { model_provider: "claude-cli" }, null);
  assert.ok(/Team workspace/.test(old) && /DataForSEO/.test(old));
});

test("a build without the engine says so plainly instead of offering a button that cannot work", () => {
  const html = A.agWsHtml(wsdoc({ installed: false }), null);
  assert.ok(/Not in this build/.test(html));
  assert.ok(!/data-ag="wscreate"/.test(html) && !/data-ag="wsjoin"/.test(html));
  assert.ok(/nothing needs doing/.test(html), "and it does not read as a fault");
});

test("agBytes never invents precision", () => {
  assert.strictEqual(A.agBytes(0), "0 B");
  assert.strictEqual(A.agBytes(999), "999 B");
  assert.strictEqual(A.agBytes(104857600), "100 MB");
  assert.strictEqual(A.agBytes(1048576), "1.0 MB");
  assert.strictEqual(A.agBytes(1073741824 * 2), "2.0 GB");
});

/* Everything drawn here goes through agEsc, the way every other renderer in this file does. A
   workspace name and a member name both come off the network. */
test("a workspace name and a member name are escaped", () => {
  const html = A.agWsHtml(wsdoc({ configured: true, link: "<img src=x>",
    workspace: { name: "<script>alert(1)</script>", url: "https://x.supabase.co", id: "w" },
    members: [{ member_id: "m", name: "<b>evil</b>", last_seen_at: null }],
    me: { member_id: "m", name: "x" }, sync: { pending: 0, pack_state: "idle" } }), null);
  assert.ok(!/<script>/.test(html) && /&lt;script&gt;/.test(html));
  assert.ok(!/<b>evil<\/b>/.test(html));
  assert.ok(!/<img src=x>/.test(html));
});

test("the workspace stylesheet keeps to the palette", () => {
  const mine = CSS.slice(CSS.indexOf("/* ── the team workspace (Connections tab)"));
  assert.ok(mine.length > 400, "found the block");
  const literals = mine.match(/#[0-9a-fA-F]{3,8}\b|\brgba?\(/g) || [];
  assert.strictEqual(literals.length, 0, "a hard-coded colour in the workspace CSS: " + literals);
});

/* the save round-trips, so it runs after the synchronous suite and reports with it */
async function atest(name, fn){
  try { await fn(); pass++; console.log("ok   - " + name); }
  catch (e){ fail++; console.log("FAIL - " + name); console.log("       " + (e && e.message)); }
}

(async () => {
  /* THE TWO-STEP REFRESH, driven through the real action. This is the feature that failed
     silently twice: first with no arm in agAction at all, so the click reached `default: break`;
     then with the arm in, but the press waiting on the whole run behind one fixed sentence.
     A press now STARTS the tool and returns, and the card is filled by polling the job the
     server keeps. Preview reads and changes nothing; only the second press, which he has to
     make, writes. */
  await atest("a press starts the tool, and the card fills with what the engine says", async () => {
    const a = agReset();
    const posts = [];
    let job = null;
    const now = () => Date.now() / 1000;
    const prevPost = A.apiPost, prevGet = A.apiGet;
    A.apiPost = async (path, b) => {
      /* recorded by ROUTE, not by position: an unrelated poll firing between the two presses
         must not be able to shift what this test thinks it asserted */
      if (/\/knowledge\/refresh$/.test(path)){
        posts.push([path, b]);
        job = { mode: b && b.preview ? "preview" : "apply", phase: "running", steps: [],
                label: "Catching up on what changed", waiting: null, result: null, error: null,
                spawned: true, started_at: now(), updated_at: now(), finished_at: null };
        return { started: true, job };
      }
      return {};
    };
    A.apiGet = async (path) => (/\/knowledge\/refresh$/.test(path) ? { job } : {});
    try {
      await A.agAction("refreshcheck", { getAttribute: () => "" });
      assert.strictEqual(posts.length, 1, "exactly one call, to the refresh route");
      assert.strictEqual(posts[0][1].preview, true, "the first press previews and touches nothing");
      assert.strictEqual(a.refresh.phase, "running", "and the card is live at once");
      assert.ok(!a.refresh.result, "with nothing claimed about what it found");

      /* the engine says something; the poll is what puts it on screen */
      job.steps.push({ label: "The site lists 11,656 pages now",
                       note: "every address the sitemaps and the CMS list", at: now() });
      job.updated_at = now();
      await A.agPollRefresh();
      assert.ok(/11,656 pages now/.test(A.agRefreshHtml(a)), "the engine's line reaches the screen");

      job.phase = "done"; job.finished_at = now();
      job.result = { new: 3, gone: 0, changed: 0, unchecked: 11656, preview: true,
                     report: "# What changed on testlify.com" };
      await A.agPollRefresh();
      const h = A.agRefreshHtml(a);
      assert.ok(/3 new/.test(h), "the counts land where the spinner was: " + h.slice(0, 200));
      assert.ok(/11,656 pages give no date/.test(h), "could-not-check-cheaply included");
      assert.ok(!/class="spin"/.test(h), "and nothing is left spinning");
      assert.ok(/data-ag="refreshreport"/.test(h), "the markdown report has a door");

      await A.agAction("refreshgo", { getAttribute: () => "" });
      assert.strictEqual(posts.length, 2, "and the second press is a second call");
      assert.ok(!posts[1][1].preview, "the second press is the real one, not another preview");
      job.phase = "done"; job.finished_at = now();
      job.result = { summary: "3 pages added, 0 removed, 0 re-read.", added: 3 };
      await A.agPollRefresh();
      assert.ok(/3 pages added/.test(A.agRefreshHtml(a)), "and it reports what it did");
      assert.ok(/data-ag="refreshchanges"/.test(A.agRefreshHtml(a)), "with a way to read what changed");

      await A.agAction("refreshcancel", { getAttribute: () => "" });
      assert.strictEqual(a.refresh, null, "close puts the box away");
    } finally { A.apiPost = prevPost; A.apiGet = prevGet; }
  });

  /* A refresh that SURVIVED a total refusal comes back as a stopped job carrying the reason.
     Saying "Done" over that would be a lie about the one thing he is watching. */
  await atest("a refresh the site refused says so, and never says Done", async () => {
    const a = agReset();
    const prevPost = A.apiPost, prevGet = A.apiGet;
    const job = { mode: "apply", phase: "failed", steps: [], label: "Catching up on what changed",
                  waiting: null, spawned: true, finished_at: Date.now() / 1000,
                  updated_at: Date.now() / 1000, started_at: Date.now() / 1000,
                  error: "The site refused every page.",
                  result: { summary: "Nothing was added.", added: 0, removed: 0, rebuilt: 0 } };
    A.apiPost = async () => ({ started: true, job });
    A.apiGet = async (path) => (/\/knowledge\/refresh$/.test(path) ? { job } : {});
    try {
      await A.agAction("refreshgo", { getAttribute: () => "" });
      const h = A.agRefreshHtml(a);
      assert.strictEqual(a.refresh.phase, "failed", "a failure, not a Done");
      assert.ok(/refused every page/.test(h) && /class="msg err"/.test(h), "and it reads as a failure");
      assert.ok(!/class="spin"/.test(h), "with nothing left spinning");
      assert.ok(!/Done\./.test(h), "and no Done over the top of it");
    } finally { A.apiPost = prevPost; A.apiGet = prevGet; }
  });

  /* The one failure the server never hears about: the press that never reached it. Nothing will
     ever poll this away, so the click itself has to say it. */
  await atest("a check that cannot reach the server says so, instead of sitting on the spinner", async () => {
    const a = agReset();
    const prevPost = A.apiPost, prevGet = A.apiGet;
    A.apiPost = async () => { throw new Error("connection refused"); };
    A.apiGet = async () => ({});
    try {
      await A.agAction("refreshcheck", { getAttribute: () => "" });
      assert.ok(a.refresh.error && /connection refused/.test(a.refresh.error), "the reason is on screen");
      assert.strictEqual(a.refresh.phase, "failed", "and it is over");
      assert.ok(!/class="spin"/.test(A.agRefreshHtml(a)), "and the spinner is gone");
      /* a poll that finds no job must not wipe the only record of this one */
      await A.agPollRefresh();
      assert.ok(a.refresh && /connection refused/.test(a.refresh.error), "a poll cannot clear it");
    } finally { A.apiPost = prevPost; A.apiGet = prevGet; }
  });

  /* A second press while one is running is refused by the server. What he should then see is
     the run that IS going, not a red box about his click. */
  await atest("a press refused because one is already running shows the run that is going", async () => {
    const a = agReset();
    const prevPost = A.apiPost, prevGet = A.apiGet;
    const job = { mode: "apply", phase: "running", label: "Catching up on what changed",
                  steps: [{ label: "Reading 214 pages", note: "", at: Date.now() / 1000 }],
                  waiting: null, result: null, error: null, spawned: true,
                  started_at: Date.now() / 1000, updated_at: Date.now() / 1000, finished_at: null };
    A.apiPost = async () => { throw new Error("A refresh is already running. Wait for it to finish."); };
    A.apiGet = async (path) => (/\/knowledge\/refresh$/.test(path) ? { job } : {});
    try {
      await A.agAction("refreshcheck", { getAttribute: () => "" });
      assert.ok(A.agRefreshLive(a.refresh), "the running job is what is drawn");
      assert.ok(/Reading 214 pages/.test(A.agRefreshHtml(a)), "in the engine's words");
      assert.ok(!/already running/.test(A.agRefreshHtml(a)), "and not a box about the click");
    } finally { A.apiPost = prevPost; A.apiGet = prevGet; a.refresh = null; }
  });

  /* A card that is no longer being told anything must not go on spinning as if it were: that
     is the same lie in a different place. */
  await atest("a card that has lost the server says so rather than spinning on an old frame", async () => {
    const a = agReset();
    const prevPost = A.apiPost, prevGet = A.apiGet;
    const job = { mode: "apply", phase: "running", label: "Catching up on what changed",
                  steps: [{ label: "Reading 214 pages", note: "", at: Date.now() / 1000 }],
                  waiting: null, result: null, error: null, spawned: true,
                  started_at: Date.now() / 1000, updated_at: Date.now() / 1000, finished_at: null };
    A.apiPost = async () => ({ started: true, job });
    A.apiGet = async () => { throw new Error("connection refused"); };
    try {
      await A.agAction("refreshgo", { getAttribute: () => "" });
      assert.ok(A.agRefreshLive(a.refresh), "the job it was handed is still the job it holds");
      await A.agPollRefresh(); await A.agPollRefresh();
      assert.strictEqual(a.refreshPollErr.n, 3, "the failures are counted, not swallowed");
      const h = A.agRefreshHtml(a);
      assert.ok(/Not hearing from Sutra/.test(h), "and the card says so: " + h.slice(0, 260));
      assert.ok(/what it last said/.test(h), "naming what it is showing for what it is");
      A.apiGet = async () => ({ job });
      await A.agPollRefresh();
      assert.strictEqual(a.refreshPollErr, null, "one good read clears it");
      assert.ok(!/Not hearing/.test(A.agRefreshHtml(a)));
    } finally { A.apiPost = prevPost; A.apiGet = prevGet; a.refresh = null; a.refreshPollErr = null; }
  });

  /* A refresh he started, then walked away from, is still his to watch when he comes back. */
  await atest("the Knowledge tab picks up a refresh that was already running", async () => {
    const a = agReset();
    a.view = "knowledge";
    const prevGet = A.apiGet;
    const job = { mode: "apply", phase: "running", label: "Catching up on what changed",
                  steps: [{ label: "Reading 214 pages", note: "only the ones that are new", at: Date.now() / 1000 }],
                  waiting: null, result: null, error: null, spawned: true,
                  started_at: Date.now() / 1000 - 90, updated_at: Date.now() / 1000, finished_at: null };
    A.apiGet = async (path) => (/\/knowledge\/refresh$/.test(path) ? { job } : {});
    try {
      assert.strictEqual(a.refresh, null, "the screen knows nothing yet");
      await A.agPollRefresh();
      assert.ok(A.agRefreshLive(a.refresh), "and then it does");
      assert.ok(/Reading 214 pages/.test(A.agRefreshHtml(a)), "drawn where it stands");
    } finally { A.apiGet = prevGet; a.view = "chat"; a.refresh = null; }
  });

  /* The change report is a REPORT: the engine writes it, there is nothing on disk for a save to
     land on, so the panel that shows it offers no Edit. */
  await atest("what changed opens in the panel, read-only", async () => {
    const a = agReset();
    const prevGet = A.apiGet;
    A.apiGet = async () => ({ text: "# What changed on testlify.com\n\n## New pages (3)" });
    try {
      a.refresh = { done: "3 pages added." };
      await A.agAction("refreshchanges", { getAttribute: () => "" });
      assert.ok(a.panel && a.panel.view === "brand_file", "it opens in the panel");
      assert.ok(/New pages \(3\)/.test(a.panel.data.text), "holding the real report");
      const html = A.agPanelHtml(a);
      assert.ok(!/data-ag="fileedit"/.test(html), "and nothing offers to edit a report");
    } finally { A.apiGet = prevGet; a.panel = null; }
  });

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

  await atest("clicking a milestone opens THAT part in the panel, read-only, named for a person", async () => {
    const a = agReset(); const seen = [];
    const prev = A.apiGet;
    A.apiGet = async (p) => { seen.push(p); return { key: "plan", label: "Planned", note: "the headings and the evidence",
                                                    file: "blueprint.json", data: { h1: "Cost per hire", sections: [{ id: "s1", h2: "What it costs", job: "explain" }] } }; };
    await A.agAction("libmile", { getAttribute: k => ({ "data-arg": "run-c1-r1", "data-name": "plan", "data-label": "Planned" })[k] || "" });
    A.apiGet = prev;
    assert.ok(/\/library\/run-c1-r1\/artifact\/plan$/.test(seen[0]), "it asks for that row's own file: " + seen[0]);
    assert.strictEqual(a.panel.view, "blueprint", "the plan opens in the plan view, not a new one");
    assert.strictEqual(a.panel.title, "Planned", "titled the way the strip named it");
    assert.strictEqual(a.panel.subtitle, "the headings and the evidence", "and says what it is");
    assert.strictEqual(a.panel.run_id, null, "no run is answering, so there is no run on the panel");
    assert.strictEqual(a.panel.readOnly, true);
    const html = A.agPanelHtml(a);
    assert.ok(/Cost per hire/.test(html), "the plan is on screen");
    assert.ok(!/data-ag="bpedit"/.test(html) && !/data-ag="bpmove"/.test(html),
              "with no control that would post an edit to a run that is not there");
    assert.ok(!/data-ag="approvert"/.test(html), "and nothing to approve: the run is not waiting on this");
  });

  await atest("a milestone the server cannot serve yet says so, instead of sitting on Reading…", async () => {
    const a = agReset();
    const prev = A.apiGet;
    A.apiGet = async () => { throw new Error("that part of this article has not been written yet"); };
    await A.agAction("libmile", { getAttribute: k => ({ "data-arg": "run-c1-r1", "data-name": "draft" })[k] || "" });
    A.apiGet = prev;
    assert.strictEqual(a.panel.loading, false, "it stops reading");
    assert.ok(/has not been written yet/.test(a.panel.error), "and passes the server's words on: " + a.panel.error);
    assert.ok(/has not been written yet/.test(A.agPanelHtml(a)), "on screen, in the panel");
  });

  await atest("the Library refreshes itself ONLY while it is in front of him and something is moving", async () => {
    const a = agReset(); a.chat = null;
    const calls = [];
    const prev = A.apiGet;
    const lib = (p) => /\/library$/.test(p);
    A.apiGet = async (p) => { calls.push(p); return lib(p) ? [{ id: "x", status: "writing" }] : []; };

    a.view = "library"; a.library = [{ id: "x", status: "writing" }];
    await A.agRefresh();
    assert.ok(calls.some(lib), "a row being written is refetched: " + calls.join(", "));

    calls.length = 0;
    a.library = [{ id: "x", status: "ready" }];
    await A.agRefresh();
    assert.ok(!calls.some(lib), "nothing moving, nothing fetched: " + calls.join(", "));

    calls.length = 0;
    a.view = "knowledge"; a.library = [{ id: "x", status: "writing" }];
    await A.agRefresh();
    assert.ok(!calls.some(lib), "and not while he is on another screen: " + calls.join(", "));
    A.apiGet = prev;
  });

  await atest("opening a prompt reads it from the server and shows what it says now", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    const asked = [];
    const prev = A.apiGet;
    A.apiGet = async (p) => { asked.push(p); return { name: "write/readable", title: "Rewriting it to be read",
      note: "n", text: "THE CURRENT TEXT", shipped: "THE CURRENT TEXT", edited: false, tokens: ["ARTICLE"], lines: 292 }; };
    await A.agAction("promptopen", { getAttribute: k => k === "data-arg" ? "write/readable" : "" });
    A.apiGet = prev;
    assert.ok(asked.some(p => /\/prompts\/one\?name=write%2Freadable$/.test(p)), "asked for the prompt: " + asked.join(", "));
    assert.strictEqual(a.panel.view, "prompt");
    assert.strictEqual(a.panel.data.text, "THE CURRENT TEXT", "it opens showing what it currently says");
    assert.ok(/as it shipped/.test(A.agPanelHtml(a)), "and says whose version it is");
    assert.ok(/THE CURRENT TEXT/.test(A.agPromptHtml(a.panel.data, null)), "on screen, before he edits anything");
  });

  await atest("saving a prompt posts the whole text, and the panel becomes his version", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: null, name: "write/readable", view: "prompt", loading: false,
                title: "Rewriting it to be read", data: { name: "write/readable", text: "old", tokens: ["ARTICLE"], edited: false } };
    a.promptEdit = { text: "MY OWN RULES {{ARTICLE}}", busy: false, msg: "" };
    let sent = null;
    const prevP = A.apiPost, prevG = A.apiGet;
    A.apiPost = async (p, b) => { sent = { path: p, b }; return { name: b.name, title: "Rewriting it to be read",
      text: b.text, shipped: "old", edited: true, tokens: ["ARTICLE"], lines: 1 }; };
    A.apiGet = async () => promptsPayload(["write/readable"]);
    await A.agAction("promptsave", { getAttribute: () => "" });
    A.apiPost = prevP; A.apiGet = prevG;
    assert.ok(sent && /\/prompts\/save$/.test(sent.path), "posted to the save route: " + (sent && sent.path));
    assert.strictEqual(sent.b.name, "write/readable", "with the prompt named");
    assert.strictEqual(sent.b.text, "MY OWN RULES {{ARTICLE}}", "and the text whole");
    assert.strictEqual(a.promptEdit, null, "the editor closes");
    assert.strictEqual(a.panel.data.text, "MY OWN RULES {{ARTICLE}}", "the panel shows what he saved");
    assert.strictEqual(a.panel.data.edited, true, "and knows it is his now");
    const panel = A.agPanelHtml(a);
    assert.ok(/Reset to what shipped/.test(panel), "so Reset is offered");
    assert.ok(/your version, used by the next article/.test(panel),
              "and the line under the title still says it shipped that way");
  });

  await atest("a save that drops a {{TOKEN}} is refused, and his words stay on screen with the reason", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: null, name: "write/readable", view: "prompt", loading: false, title: "Rewriting it to be read",
                data: { name: "write/readable", text: "old {{ARTICLE}}", tokens: ["ARTICLE"], edited: false } };
    a.promptEdit = { text: "I deleted the placeholder", busy: false, msg: "" };
    const prev = A.apiPost;
    A.apiPost = async () => { throw new Error("This version is missing a placeholder the agent fills in: {{ARTICLE}}. Put it back exactly as written, or the next article will be written from a prompt with a hole in it."); };
    await A.agAction("promptsave", { getAttribute: () => "" });
    A.apiPost = prev;
    assert.strictEqual(a.promptEdit.text, "I deleted the placeholder", "nothing he typed is thrown away");
    assert.ok(/\{\{ARTICLE\}\}/.test(a.promptEdit.msg), "the missing placeholder is named: " + a.promptEdit.msg);
    assert.strictEqual(a.panel.data.text, "old {{ARTICLE}}", "and the saved prompt is untouched");
    assert.ok(/hole in it/.test(A.agPromptHtml(a.panel.data, a.promptEdit)), "the reason is beside the button, not in a toast");
  });

  await atest("Reset asks the server to put the prompt back, and the panel says it shipped that way", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: null, name: "write/blend", view: "prompt", loading: false, title: "Blend",
                data: { name: "write/blend", text: "his version {{ARTICLE}}", shipped: "what shipped {{ARTICLE}}",
                        tokens: ["ARTICLE"], edited: true } };
    let sent = null;
    const prevP = A.apiPost, prevG = A.apiGet;
    A.apiPost = async (p, b) => { sent = { path: p, b }; return { name: b.name, title: "Blend",
      text: "what shipped {{ARTICLE}}", shipped: "what shipped {{ARTICLE}}", tokens: ["ARTICLE"], edited: false }; };
    A.apiGet = async () => promptsPayload([]);
    await A.agAction("promptreset", { getAttribute: () => "" });
    A.apiPost = prevP; A.apiGet = prevG;
    assert.ok(sent && /\/prompts\/reset$/.test(sent.path), "posted to the reset route: " + (sent && sent.path));
    assert.strictEqual(sent.b.name, "write/blend");
    assert.strictEqual(a.panel.data.text, "what shipped {{ARTICLE}}", "the shipped text is back");
    assert.strictEqual(a.panel.data.edited, false);
    assert.ok(!/Reset to what shipped/.test(A.agPanelHtml(a)), "and there is nothing left to reset");
  });

  await atest("a row being written puts the poll on its fast cadence, on the one timer there is", async () => {
    const a = agReset();
    a.chat = { runs: [{ run_id: "r1", status: "done" }] };
    assert.strictEqual(A.agLiveRun(), null, "no live run in the loaded chat");
    a.view = "library"; a.library = [{ id: "x", status: "writing" }];
    assert.strictEqual(A.agLibWriting(a), true, "but a row is still being written");
    a.library = [{ id: "x", status: "ready" }];
    assert.strictEqual(A.agLibWriting(a), false);
    assert.strictEqual(A.agLibWriting({}), false, "and an empty screen is not 'writing'");
    /* the fast/idle choice is one expression over both, so there is no second clock */
    const src = fs.readFileSync(path.join(__dirname, "static", "js", "17-agents.js"), "utf8");
    const poll = src.slice(src.indexOf("function agStartPoll"), src.indexOf("function agStopPoll"));
    assert.ok(/agLiveRun\(\) \|\| \(a && a\.view === "library" && agLibWriting\(a\)\)/.test(poll),
              "the Library case rides the existing cadence: " + poll.slice(poll.indexOf("const live")));
    assert.strictEqual((poll.match(/setInterval/g) || []).length, 1, "still exactly one interval");
  });

  /* ── the engine half, in Python ───────────────────────────────────────────────
     Everything above proves the SCREEN behaves. What it cannot prove is the thing
     that actually matters: that a prompt he saved is the one the next article is
     written from. That lives in seo_agent/prompts/store.py, so it is checked here
     by running that module, through the same interpreter run_all.sh picks (the
     project venv when there is one). It imports nothing but the standard library
     and seo_agent.store, so it runs anywhere this repo does. */
  await atest("in the engine: his edit is what the next run loads, Reset puts it back, and a broken template is refused", async () => {
    const cp = require("child_process"), os = require("os");
    const venv = path.join(__dirname, ".venv", "bin", "python");
    const PY = fs.existsSync(venv) ? venv : "python3";
    const data = fs.mkdtempSync(path.join(os.tmpdir(), "seo-prompts-"));
    const script = [
      "from seo_agent.prompts import store as ps",
      "assert ps.install(), 'install() did nothing'",
      "from seo_agent.tools import _shared as sh",
      "name = 'write/blend'",
      "shipped = ps.shipped_text(name)",
      "assert shipped.strip(), 'no shipped prompt to start from'",
      "assert sh.load_prompt(name).startswith(shipped[:40]), 'the door does not serve the shipped prompt'",
      "ps.save(name, 'MY OWN RULES\\n' + shipped)",
      // the override is beside knowledge, under the data dir, and never in the app bundle
      "assert ps.override_path(name).startswith(ps.store.data_dir()), ps.override_path(name)",
      "assert not ps.override_path(name).startswith(ps.SHIPPED), 'it wrote into the app bundle'",
      "assert open(ps.shipped_path(name)).read() == shipped, 'the shipped file was written over'",
      // what the NEXT RUN loads, through the door every step calls
      "assert sh.load_prompt(name).startswith('MY OWN RULES'), 'a run would not load his version'",
      "ps.reset(name)",
      "assert sh.load_prompt(name).startswith(shipped[:40]), 'Reset did not restore the shipped text'",
      "assert not ps.is_edited(name)",
      // a save that loses a placeholder is refused, and nothing is written
      "try:",
      "    ps.save(name, 'every placeholder deleted')",
      "    raise SystemExit('a save that dropped every {{TOKEN}} was ACCEPTED')",
      "except ps.PromptError as e:",
      "    assert '{{' in str(e), 'the refusal does not name the placeholder: %s' % e",
      "assert not ps.is_edited(name), 'a refused save still wrote a file'",
      // a format rulebook is never filled, so its developer header is his to delete; a token he
      // INVENTS is still refused there, because a rulebook's words are injected into a real prompt
      "rule = 'write/formats/listicle'",
      "assert '{{' in ps.shipped_text(rule), 'the fixture no longer has a token in its header'",
      "ps.save(rule, '## Structure\\nNine items, never eight.')",
      "assert ps.is_edited(rule), 'he could not delete a header that only describes the plumbing'",
      "import seo_agent.write._common as C",
      "assert 'Nine items' in C.format_rules('listicle'), 'the rulebook a run reads is not his'",
      "ps.reset(rule)",
      "try:",
      "    ps.save(rule, '## Structure\\nUse {{MADE_UP}} here.')",
      "    raise SystemExit('an invented {{TOKEN}} in a rulebook was ACCEPTED')",
      "except ps.PromptError as e:",
      "    assert 'MADE_UP' in str(e), e",
      "print('PROMPT-STORE-OK')",
    ].join("\n");
    const r = cp.spawnSync(PY, ["-c", script], {
      cwd: __dirname, encoding: "utf8",
      env: Object.assign({}, process.env, { PYTHONPATH: __dirname, SEO_AGENT_DATA: data, SEO_AGENT_NO_CLI: "1" }),
    });
    fs.rmSync(data, { recursive: true, force: true });
    assert.ok(/PROMPT-STORE-OK/.test(r.stdout || ""),
              "the prompt store failed:\n" + ((r.stderr || "") + (r.stdout || "")).trim().split("\n").slice(-6).join("\n"));
  });


  /* ── the team workspace, driven through the real actions ────────────────────
     The renderers above prove what is drawn; these prove what is SENT, because the one thing a
     rendered-DOM test cannot see is a token that quietly stayed behind. */

  /* A tiny document, only as much of one as agTakeToken and agTokenTyped read. It exists so the
     token can be put in a box and then looked for afterwards. */
  function wsDoc(tokenValue){
    const box = { value: tokenValue, getAttribute: () => "token", matches: () => true };
    return { querySelector: sel => (sel === '[data-agws="token"]' ? box : null),
             querySelectorAll: () => [], getElementById: () => null,
             activeElement: null, box: box };
  }

  await atest("Create posts the token exactly once, and it is gone from everywhere afterwards", async () => {
    const a = agReset();
    a.ws = null; a.wsForm = { mode: "create", url: "https://abcdefghijklmnop.supabase.co",
                              key: "sb_publishable_abc", name: "Testlify" };
    const doc = wsDoc("sbp_verysecrettoken");
    const prevDoc = A.document, prevPost = A.apiPost, prevGet = A.apiGet;
    A.document = doc;
    const posts = [];
    A.apiPost = async (path, b) => { posts.push([path, b]); return { started: true }; };
    A.apiGet = async () => ({ installed: true, configured: false,
                              job: { kind: "create", phase: "tables", step: "Setting up your workspace", pct: 5 } });
    try { await A.agAction("wsgo", { getAttribute: () => "" }); }
    finally { A.document = prevDoc; A.apiPost = prevPost; A.apiGet = prevGet; }

    const create = posts.filter(p => /\/workspace\/create$/.test(p[0]));
    assert.strictEqual(create.length, 1, "one create, not two");
    assert.strictEqual(create[0][1].token, "sbp_verysecrettoken", "the token went with it");
    assert.strictEqual(create[0][1].url, "https://abcdefghijklmnop.supabase.co");
    assert.strictEqual(create[0][1].key, "sb_publishable_abc");
    /* and now the three places it must not be */
    assert.strictEqual(doc.box.value, "", "the box is emptied the moment it is read");
    assert.strictEqual(JSON.stringify(a.wsForm).indexOf("sbp_"), -1, "nothing of it on S.ag");
    assert.strictEqual(JSON.stringify(a.ws || {}).indexOf("sbp_"), -1, "and nothing of it came back");
  });

  /* An empty token box is not a mistake. It is the setup-script route, and the server answers
     it with the script rather than with a refusal, so the button must go through. */
  await atest("Create with an empty token box goes through, with no token field at all", async () => {
    const a = agReset();
    a.wsForm = { mode: "create", url: "https://abcdefghijklmnop.supabase.co", key: "sb_publishable_abc" };
    const prevDoc = A.document, prevPost = A.apiPost, prevGet = A.apiGet;
    A.document = wsDoc("");
    const posts = [];
    A.apiPost = async (p, b) => { posts.push([p, b]); return { started: true }; };
    A.apiGet = async () => ({ installed: true, configured: false, job: { kind: "create", phase: "paste",
      paste: { sql: "create table if not exists public.workspace ();", editor_url: "https://e",
               why: "Sutra has no access token, so it cannot create the tables for you." } } });
    try { await A.agAction("wsgo", { getAttribute: () => "" }); }
    finally { A.document = prevDoc; A.apiPost = prevPost; A.apiGet = prevGet; }
    assert.strictEqual(posts.length, 1, "it was sent");
    assert.strictEqual(posts[0][1].token, undefined, "with no token field at all");
    assert.strictEqual(a.ws.job.phase, "paste", "and the script is what comes back");
    assert.ok(/Run the setup script/.test(A.agWsHtml(a.ws, a.wsForm)), "drawn as a route");
  });

  await atest("Create with a box empty asks for it instead of sending half a form", async () => {
    const a = agReset();
    a.wsForm = { mode: "create", url: "", key: "sb_publishable_abc" };
    const prevPost = A.apiPost;
    const posts = [];
    A.apiPost = async p => { posts.push(p); return {}; };
    try { await A.agAction("wsgo", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; }
    assert.strictEqual(posts.length, 0, "nothing was sent");
    assert.ok(/project URL and the publishable key/.test(a.wsForm.msg));
  });

  /* THE BAR: "a wrong key says 'that key is not for this project', not a status code." The
     server writes that sentence; this proves the screen prints it rather than a code. */
  await atest("a refusal from the server is shown in its own words", async () => {
    const a = agReset();
    a.wsForm = { mode: "create", url: "https://abcdefghijklmnop.supabase.co", key: "sb_secret_oops" };
    const prevDoc = A.document, prevPost = A.apiPost, prevGet = A.apiGet;
    A.document = wsDoc("sbp_tok");
    A.apiPost = async () => { throw new Error("That is the secret key. It gets past every row rule, so Sutra never asks for it."); };
    A.apiGet = async () => ({ installed: true, configured: false, job: null });
    try { await A.agAction("wsgo", { getAttribute: () => "" }); }
    finally { A.document = prevDoc; A.apiPost = prevPost; A.apiGet = prevGet; }
    assert.ok(/That is the secret key/.test(a.wsForm.msg), "the sentence, not a code: " + a.wsForm.msg);
    assert.ok(!/\b(400|403|409|500)\b/.test(a.wsForm.msg));
    assert.ok(/data-agws="url"/.test(A.agWsHtml(a.ws, a.wsForm)), "and he is back at the boxes");
  });

  /* "I've run it" and "Check again" are the same question, and it is a DIFFERENT route from
     create: confirm asks "is it set up now", which is the only question verify can answer. */
  await atest("I have run it asks the confirm route, which is verify and nothing else", async () => {
    const a = agReset();
    a.wsForm = { mode: "create", url: "https://abcdefghijklmnop.supabase.co", key: "sb_publishable_abc", name: "Testlify" };
    const prevPost = A.apiPost, prevGet = A.apiGet;
    const posts = [];
    A.apiPost = async (p, b) => { posts.push([p, b]); return { started: true }; };
    A.apiGet = async () => ({ installed: true, configured: true, link: "sutra-ws-abc",
      workspace: { name: "Testlify", url: "https://abcdefghijklmnop.supabase.co", id: "w1" },
      members: [], me: { member_id: "m1" }, sync: { pending: 0, pack_state: "idle" },
      verify: { ok: true, reason: "Workspace ready." },
      job: { kind: "create", phase: "done", finished_at: Date.now() / 1000 } });
    try { await A.agAction("wssqldone", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; A.apiGet = prevGet; }
    assert.strictEqual(posts[0][0], "/api/agents/seo/workspace/confirm");
    assert.strictEqual(posts[0][1].token, undefined, "and never a token");
    assert.ok(/Your workspace is ready/.test(A.agWsHtml(a.ws, a.wsForm)),
              "and only NOW, after the server verified, does it say so");
  });

  /* Check again on an unfinished workspace has no form behind it: the URL has to come off the
     workspace the tab is already showing, or the route gets an empty body and refuses. */
  await atest("Check again on an unfinished workspace sends the project it is looking at", async () => {
    const a = agReset();
    a.wsForm = null;
    a.ws = { installed: true, configured: true, link: "sutra-ws-abc",
             workspace: { name: "Testlify", url: "https://abcdefghijklmnop.supabase.co", id: "w1" },
             members: [], sync: { pending: 0, pack_state: "idle" },
             verify: { ok: false, reason: "The tables are there but the knowledge bucket is not." } };
    const prevPost = A.apiPost, prevGet = A.apiGet;
    const posts = [];
    A.apiPost = async (p, b) => { posts.push([p, b]); return { started: true }; };
    A.apiGet = async () => a.ws;
    try { await A.agAction("wssqldone", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; A.apiGet = prevGet; }
    assert.strictEqual(posts[0][0], "/api/agents/seo/workspace/confirm");
    assert.strictEqual(posts[0][1].url, "https://abcdefghijklmnop.supabase.co");
  });

  /* agDraw holds this view still while there is something in the token box, because that box
     is the one field it cannot re-render. So an arm that changes what the section shows has to
     empty it, or the screen freezes with nothing on it to say why. */
  await atest("Cancel empties the token box, so the view is never left frozen", async () => {
    const a = agReset();
    a.wsForm = { mode: "create", url: "https://abcdefghijklmnop.supabase.co", key: "sb_publishable_abc" };
    const doc = wsDoc("sbp_halftyped");
    const prevDoc = A.document, prevPost = A.apiPost, prevGet = A.apiGet;
    A.document = doc;
    A.apiPost = async () => ({ ok: true });
    A.apiGet = async () => ({ installed: true, configured: false, job: null });
    try { await A.agAction("wscancel", { getAttribute: () => "" }); }
    finally { A.document = prevDoc; A.apiPost = prevPost; A.apiGet = prevGet; }
    assert.strictEqual(doc.box.value, "", "the box is empty, so agDraw is free to redraw");
    assert.strictEqual(a.wsForm, null);
    /* and the discarded token went nowhere */
    assert.strictEqual(JSON.stringify(a.ws).indexOf("sbp_"), -1);
  });

  await atest("Done on the join screen sends the link and the name, and nothing else", async () => {
    const a = agReset();
    a.wsForm = { mode: "join", link: "sutra-ws-abc", name: "Ravi" };
    const prevPost = A.apiPost, prevGet = A.apiGet;
    const posts = [];
    A.apiPost = async (p, b) => { posts.push([p, b]); return { started: true }; };
    A.apiGet = async () => ({ installed: true, configured: false,
      job: { kind: "join", phase: "download", done_bytes: 1024, total_bytes: 104857600 } });
    try { await A.agAction("wsjoingo", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; A.apiGet = prevGet; }
    assert.strictEqual(posts[0][0], "/api/agents/seo/workspace/join");
    assert.strictEqual(JSON.stringify(posts[0][1]), JSON.stringify({ link: "sutra-ws-abc", name: "Ravi" }));
  });

  await atest("join refuses to start with a box empty rather than sending half of it", async () => {
    const a = agReset();
    a.wsForm = { mode: "join", link: "sutra-ws-abc", name: "" };
    const prevPost = A.apiPost;
    const posts = [];
    A.apiPost = async p => { posts.push(p); return {}; };
    try { await A.agAction("wsjoingo", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; }
    assert.strictEqual(posts.length, 0);
    assert.ok(/type the name/i.test(a.wsForm.msg));
  });

  /* Cancel and Start over have to clear the job on the SERVER. Clearing it only on this side
     would put the same fallback screen back on the next poll, four seconds later. */
  await atest("Cancel clears the job on the server, not just on this screen", async () => {
    const a = agReset();
    a.ws = { installed: true, configured: false, job: { kind: "create", phase: "paste", paste: { sql: "x" } } };
    const prevPost = A.apiPost, prevGet = A.apiGet;
    const posts = [];
    A.apiPost = async (p, b) => { posts.push(p); return { ok: true }; };
    A.apiGet = async () => ({ installed: true, configured: false, job: null });
    try { await A.agAction("wscancel", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; A.apiGet = prevGet; }
    assert.ok(posts.indexOf("/api/agents/seo/workspace/dismiss") !== -1, "it asked the server to forget it");
    assert.strictEqual(a.wsForm, null);
    assert.strictEqual(a.ws.job, null);
  });

  await atest("Leaving asks first, then re-reads rather than assuming it worked", async () => {
    const a = agReset();
    a.ws = { installed: true, configured: true, link: "sutra-ws-abc", workspace: { name: "T" }, members: [] };
    const prevPost = A.apiPost, prevGet = A.apiGet, prevConfirm = A.confirm;
    const posts = [];
    A.confirm = () => true;
    A.apiPost = async p => { posts.push(p); return { ok: true }; };
    A.apiGet = async () => ({ installed: true, configured: false, job: null, link: "", members: [] });
    try { await A.agAction("wsleave", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; A.apiGet = prevGet; A.confirm = prevConfirm; }
    assert.ok(posts.indexOf("/api/agents/seo/workspace/leave") !== -1);
    assert.strictEqual(a.ws.configured, false, "and what is drawn is what the server said, not what we hoped");
  });

  await atest("saying no to the Leave question leaves everything alone", async () => {
    const a = agReset();
    a.ws = { installed: true, configured: true, link: "sutra-ws-abc" };
    const prevPost = A.apiPost, prevConfirm = A.confirm;
    const posts = [];
    A.confirm = () => false;
    A.apiPost = async p => { posts.push(p); return {}; };
    try { await A.agAction("wsleave", { getAttribute: () => "" }); }
    finally { A.apiPost = prevPost; A.confirm = prevConfirm; }
    assert.strictEqual(posts.length, 0);
    assert.strictEqual(a.ws.configured, true);
  });

  console.log("\n" + "-".repeat(60));
  console.log("agents screen: " + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
