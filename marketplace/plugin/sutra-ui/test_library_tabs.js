#!/usr/bin/env node
/*
 * test_library_tabs.js -- the five read-only Library tabs (Search picture / Research /
 * Architect / Draft / Edits) that replace the old milestone-dot panels, plus the Undo/Redo
 * pair wired into the full-width article view's back bar.
 *
 * Same harness as test_agents.js: static/js/17-agents.js loaded under vm into a stubbed
 * context, apiGet/apiPost stubbed per test, and every check reads the module's own pure
 * renderers and agAction arms rather than a real server or a real DOM.
 *
 * Run: node test_library_tabs.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const SRC = fs.readFileSync(path.join(__dirname, "static", "js", "17-agents.js"), "utf8");

const ctx = {
  SCREENS: {}, TITLES: {}, S: {}, console,
  apiGet: async () => ({}), apiPost: async () => ({}),
  setTimeout, clearTimeout, setInterval, clearInterval, Date, JSON, Math, Number, String, Array, Object, RegExp, encodeURIComponent, isNaN,
  document: undefined, confirm: undefined, navigator: undefined,
};
vm.createContext(ctx);
vm.runInContext(SRC, ctx, { filename: "17-agents.js" });
const A = ctx;

let pass = 0, fail = 0;
function test(name, fn){
  try { fn(); pass++; console.log("ok   - " + name); }
  catch (e){ fail++; console.log("FAIL - " + name); console.log("       " + (e && e.stack || e)); }
}
async function atest(name, fn){
  try { await fn(); pass++; console.log("ok   - " + name); }
  catch (e){ fail++; console.log("FAIL - " + name); console.log("       " + (e && e.stack || e)); }
}

/* ── sample payloads, shaped exactly like the four /tabs fields plus the Draft fields off
   GET /library/{id} -- every field named in the build spec, once each ─────────────────── */
const SP = {
  primary: { keyword: "cost per hire", volume: 1200, kd: 34 },
  variations: [{ keyword: "average cost per hire", volume: 300, kd: 28 }],
  secondary: [{ keyword: "hiring costs", volume: 150, kd: 40 }],
  in_body: ["recruiting costs", "hiring budget"],
  avg_words: 2700,
  band: { min: 2400, max: 3000 },
  who_ranks: [
    { rank: 1, title: "The real cost of hiring", url: "https://example.com/a", domain: "example.com" },
    { rank: 2, title: "Cost per hire, explained", url: "https://acme.com/b", domain: "acme.com" },
    { rank: 3, title: "Hiring cost calculator", url: "https://widgets.io/c", domain: "widgets.io" },
  ],
  ai_overview: "Cost per hire averages $4,700 in the US.",
  paa: ["What is cost per hire?", "How do you calculate cost per hire?"],
  common: ["A formula", "Benchmark data"],
  gaps: ["No mention of hidden costs"],
};
const RESEARCH = {
  angle: "The one true formula", spine: "Cost per hire is one number with three real inputs",
  about: "What goes into the number", not_about: "Salary negotiation",
  persona: "A hiring manager sizing next year's budget",
  researchers: [
    { role: "Data analyst", focus: "benchmarks", questions: ["What is the average?", "How does it vary by industry?"] },
    { role: "Practitioner", focus: "process", questions: ["What tools do teams use?"] },
    { role: "Skeptic", focus: "pitfalls", questions: ["What gets miscounted?"] },
    { role: "Editor", focus: "clarity", questions: ["What confuses readers?"] },
  ],
  have_it: { verdict: "yes", why: "we wrote about this before", links: [{ url: "https://testlify.com/old", title: "Old article" }] },
  dossier: true, voices: true,
};
const ARCH = {
  format: "How-to guide", spine: "The spine sentence", target_words: 1800, n_sections: 2, n_sub_headings: 3,
  sections: [
    { headline: "What it costs", job: "Explain the real cost per hire with a worked example.",
      word_target: 400, n_facts: 3, h3s: ["The formula", "An example"], why: "grounds the reader before the how-to" },
    { headline: "How to lower it", job: "Give three concrete levers.",
      word_target: 500, n_facts: 4, h3s: ["Referrals", "Faster screening"], why: "answers the actual search intent" },
  ],
  left_out: { sections: ["A history of hiring"], faq: ["Is cost per hire the same as cost per applicant?"],
              note: "kept the piece focused on the calculation" },
};
const EDITS = {
  passes: ["Joined the sections into one piece", "Tightened the opening", "Ran a source check"],
  source_check: { checked: 12, fine: 9, corrected: 2, softened: 1, removed: 0 },
  has_source_check_doc: true, words: 1840, target_words: 1800,
};
const DRAFT = { title: "Cost per hire", words: 1840,
  draft: "# Cost per hire\n\nSome opening body text.\n\n## Why it matters\n\nMore body here.\n" };

function fullTabsState(){
  return { on: true, itemId: "lib7", active: "picture",
           data: { search_picture: SP, research: RESEARCH, architect: ARCH, edits: EDITS },
           draft: DRAFT, loading: false, error: null, rOpen: {}, secOpen: {}, openerSel: "" };
}

/* ── 1. each tab renders its rows from a sample payload ───────────────────────────────── */
test("Search picture renders every row from its payload", () => {
  const html = A.agTabPictureHtml(SP);
  assert.ok(/cost per hire/.test(html) && /1,200 vol/.test(html) && /KD 34/.test(html), "primary keyword, with volume and KD");
  assert.ok(/average cost per hire/.test(html), "a variation");
  assert.ok(/hiring costs/.test(html), "a secondary");
  assert.ok(/recruiting costs, hiring budget/.test(html), "in-body terms as plain phrases");
  assert.ok(/2,700 words \(2,400 to 3,000\)/.test(html), "average word count with its band");
  assert.ok(/Cost per hire averages \$4,700/.test(html), "Google's own answer");
  assert.ok(/What is cost per hire\?/.test(html), "a People Also Ask question");
  assert.ok(/A formula/.test(html), "what they all cover");
  assert.ok(/No mention of hidden costs/.test(html), "what none of them cover");
});
test("Research renders every row from its payload", () => {
  const html = A.agTabResearchHtml(RESEARCH, { rOpen: {} });
  assert.ok(/The one true formula/.test(html), "the angle");
  assert.ok(/Cost per hire is one number with three real inputs/.test(html), "the spine");
  assert.ok(/What goes into the number/.test(html), "what it is about");
  assert.ok(/Salary negotiation/.test(html), "what it is not about");
  assert.ok(/A hiring manager sizing next year/.test(html), "written for");
  assert.ok(/Data analyst/.test(html) && /Practitioner/.test(html) && /Skeptic/.test(html) && /Editor/.test(html), "all four researchers");
  assert.ok(/yes/.test(html) && /we wrote about this before/.test(html), "do you already have this");
  assert.ok(/data-ag="libtabs2open" data-arg="dossier"/.test(html), "the dossier door");
  assert.ok(/data-ag="libtabs2open" data-arg="voices"/.test(html), "the voices door");
});
test("Architect renders the header line, the spine, every section and the left-out door", () => {
  const html = A.agTabArchitectHtml(ARCH, { secOpen: {} });
  assert.ok(/How-to guide/.test(html), "the format");
  assert.ok(/1,800 target words/.test(html), "target words");
  assert.ok(/2 sections/.test(html), "section count");
  assert.ok(/3 sub-headings/.test(html), "sub-heading count");
  assert.ok(/The spine sentence/.test(html), "the spine row");
  assert.ok(/What it costs/.test(html) && /How to lower it/.test(html), "both section headlines");
  assert.ok(/400 words · 3 facts/.test(html), "a section's own word target and fact count");
  assert.ok(/data-ag="libtabs2open" data-arg="purpose:0"/.test(html), "the first section's Purpose door");
  assert.ok(/data-ag="libtabs2open" data-arg="leftout"/.test(html), "the what-was-left-out door");
});
test("Draft renders the sections read-only, with no editing affordance anywhere", () => {
  const html = A.agTabDraftHtml(DRAFT);
  assert.ok(/1,840 words/.test(A.agTabDraftHtml({ draft: DRAFT.draft })) === false, "word count comes from the text itself, not a passed-in number");
  assert.ok(/Some opening body text/.test(html) && /Why it matters/.test(html) && /More body here/.test(html), "both sections");
  assert.ok(!/data-ag="libsec"/.test(html), "no pencil, no per-section edit door");
  assert.ok(!/ag-editbtn/.test(html), "no edit button class at all");
});
test("Edits renders the passes, the source-check line and the words line", () => {
  const html = A.agTabEditsHtml(EDITS);
  EDITS.passes.forEach(p => assert.ok(html.indexOf(p) !== -1, "pass listed: " + p));
  assert.ok(/Checked 12 · Fine 9 · Corrected 2 · Softened 1 · Removed 0/.test(html), "the source-check summary line");
  assert.ok(/data-ag="libtabs2open" data-arg="source-check"/.test(html), "a door to the full source-check document");
  assert.ok(/1,840 words against a target of 1,800/.test(html), "the words line");
});

/* ── 2. a null tab payload greys out, never an empty table ────────────────────────────── */
test("a tab whose payload is null is inert in the switcher, not a dead click into an empty table", () => {
  const a = { libTabs: { on: true, itemId: "lib7", active: "picture",
    data: { search_picture: SP, research: null, architect: null, edits: null },
    draft: DRAFT, loading: false, error: null, rOpen: {}, secOpen: {}, openerSel: "" } };
  const html = A.agLibTabsHtml(a);
  assert.ok(/<button[^>]*data-ag="libtabsswitch" data-arg="picture"/.test(html), "Search picture is clickable: it has data");
  assert.ok(/<button[^>]*data-ag="libtabsswitch" data-arg="draft"/.test(html), "Draft is always clickable, never gated on /tabs");
  assert.ok(/<span class="ag-tabsbtn off"[^>]*>Research<\/span>/.test(html), "Research is an inert span, not a button");
  assert.ok(/<span class="ag-tabsbtn off"[^>]*>Architect<\/span>/.test(html), "Architect is an inert span");
  assert.ok(/<span class="ag-tabsbtn off"[^>]*>Edits<\/span>/.test(html), "Edits is an inert span");
  assert.ok(!/data-ag="libtabsswitch" data-arg="research"/.test(html), "no click target for the greyed-out ones");
});
test("a coarser milestone than its tab's real data: the tab still opens, and shows Not written yet", () => {
  /* the spec's gating note: clicking Architect the moment blueprint.json exists but the
     architect payload is still null must not crash or guess -- it shows the placeholder. */
  const a = { libTabs: { on: true, itemId: "lib7", active: "architect",
    data: { search_picture: null, research: null, architect: null, edits: null },
    draft: null, loading: false, error: null, rOpen: {}, secOpen: {} } };
  const html = A.agLibTabsHtml(a);
  assert.ok(/Not written yet\./.test(html), "the plain placeholder, not a broken table");
});

/* ── 3. Search picture's "who ranks now": one row per result, a real link, the domain too ── */
test("who ranks now draws exactly one row per result, each a link with its domain", () => {
  const html = A.agTabPictureHtml(SP);
  const rows = html.match(/<tr>/g) || [];
  assert.strictEqual(rows.length, SP.who_ranks.length, "one <tr> per result, no more, no fewer");
  SP.who_ranks.forEach(r => {
    assert.ok(html.indexOf(`<a href="${r.url}" target="_blank" rel="noopener">${r.title}</a>`) !== -1,
      "a real link for " + r.title);
    assert.ok(html.indexOf(r.domain) !== -1, "the domain shown for " + r.title);
  });
});

/* ── 8. old rows / old payloads missing fields still render, nothing throws ───────────── */
test("Search picture with everything nullable actually null does not throw and shows no broken rows", () => {
  const thin = { primary: null, variations: [], secondary: [], in_body: [], avg_words: null,
                 band: null, who_ranks: [], ai_overview: null, paa: [], common: [], gaps: [] };
  const html = A.agTabPictureHtml(thin);
  assert.ok(!/undefined/.test(html) && !/NaN/.test(html), "nothing stringified badly: " + html.slice(0, 300));
  assert.ok(!/<table/.test(html), "no empty who-ranks table when there is nothing to rank");
});
test("Architect with left_out null draws no what-was-left-out door", () => {
  const half = Object.assign({}, ARCH, { left_out: null });
  const html = A.agTabArchitectHtml(half, { secOpen: {} });
  assert.ok(!/data-ag="libtabs2open" data-arg="leftout"/.test(html), "nothing to open when there was nothing left out");
});
/* ── the coverage report on the Edits tab (spec item 5) ──────────────────────────────────
   Recruiting Metrics shipped missing two of the six things every ranking page covers and nobody
   knew until a person read it. The check had been running the whole time and writing a report
   nobody surfaced; this is the surface. Deliberately a note, not a gate. */
const COV = { expected_total: 6,
              covered: [{ topic: "Time to Fill", section: "Time to Fill Formula" },
                        { topic: "Cost per Hire", section: "What it costs" },
                        { topic: "Quality of Hire", section: "Quality of Hire" },
                        { topic: "Offer Acceptance", section: "Offers" }],
              dropped: [{ topic: "Source of Hire", why: "no evidence was found" },
                        { topic: "Candidate NPS", why: "it did not serve the angle" }] };
test("Edits says how many of the expected topics landed, which ones, and why the rest did not", () => {
  const html = A.agTabEditsHtml(Object.assign({}, EDITS, { coverage: COV }));
  assert.ok(/<span class="k">Expected topics<\/span><span class="v">4 of 6<\/span>/.test(html),
            "the count, against the report's own expected_total: " + html);
  assert.ok(/Time to Fill — in “Time to Fill Formula”/.test(html), "a covered topic names the section it landed in");
  assert.ok(/Source of Hire, because no evidence was found/.test(html), "and a dropped one carries its reason, in words");
  assert.ok(/Candidate NPS, because it did not serve the angle/.test(html), "every dropped one, not just the first");
});
test("an article written before coverage existed draws no coverage rows and no empty box", () => {
  const html = A.agTabEditsHtml(EDITS);
  assert.ok(!/Expected topics/.test(html), "no heading with nothing under it: " + html);
  assert.ok(!/>Covered</.test(html) && !/>Dropped</.test(html), "and neither list");
  assert.ok(/What was done/.test(html), "the rest of the tab is untouched");
});
test("a coverage report missing pieces draws only the pieces it has, and invents no total", () => {
  const noTotal = A.agTabEditsHtml(Object.assign({}, EDITS, {
    coverage: { covered: [{ topic: "Time to Fill" }], dropped: [] } }));
  assert.ok(!/Expected topics/.test(noTotal),
            "a total the report did not give is left out, never derived from what happened: " + noTotal);
  assert.ok(/Time to Fill/.test(noTotal) && !/ — in /.test(noTotal), "a covered topic with no section is just the topic");
  assert.ok(!/>Dropped</.test(noTotal), "and an empty dropped list draws nothing");
  const noWhy = A.agTabEditsHtml(Object.assign({}, EDITS, {
    coverage: { expected_total: 2, covered: [], dropped: [{ topic: "Source of Hire" }] } }));
  assert.ok(/Source of Hire/.test(noWhy) && !/because/.test(noWhy), "a dropped topic with no reason is just the topic");
  assert.ok(/0 of 2/.test(noWhy), "and nothing covered is still an honest count");
  assert.ok(!/undefined|NaN|\[object/.test(noTotal + noWhy), "nothing stringified badly");
});

test("Edits with source_check null draws no source-check row at all", () => {
  const half = Object.assign({}, EDITS, { source_check: null, has_source_check_doc: false });
  const html = A.agTabEditsHtml(half);
  assert.ok(!/Checked/.test(html), "no half-built summary line when there is nothing to summarise");
  assert.ok(/1,840 words against a target of 1,800/.test(html), "the words line is unaffected");
});
test("Research with have_it null reads plainly as No, and no dossier/voices doors when both are false", () => {
  const half = Object.assign({}, RESEARCH, { have_it: null, dossier: false, voices: false });
  const html = A.agTabResearchHtml(half, { rOpen: {} });
  assert.ok(/<span class="k">Do you already have this<\/span><span class="v">No<\/span>/.test(html));
  assert.ok(!/libtabs2open" data-arg="dossier"/.test(html) && !/libtabs2open" data-arg="voices"/.test(html));
});
test("three of four /tabs fields null, and no draft yet either: they grey out, nothing crashes", () => {
  const a = { libTabs: { on: true, itemId: "lib7", active: "picture",
    data: { search_picture: SP, research: null, architect: null, edits: null },
    draft: { title: "", words: 0, draft: "" }, loading: false, error: null, rOpen: {}, secOpen: {} } };
  const html = A.agLibTabsHtml(a);
  assert.ok(/cost per hire/.test(html), "the active (Search picture) tab, which has data, renders normally");
  assert.ok((html.match(/ag-tabsbtn off/g) || []).length === 3, "research, architect and edits are all greyed: " + html);
});
test("a null payload on the CURRENTLY OPEN tab greys its own switcher button too, same rule for every tab", () => {
  /* the spec draws no exception for the active tab: null is null, whichever tab it is on */
  const a = { libTabs: { on: true, itemId: "lib7", active: "picture",
    data: { search_picture: null, research: null, architect: null, edits: null },
    draft: { title: "", words: 0, draft: "" }, loading: false, error: null, rOpen: {}, secOpen: {} } };
  const html = A.agLibTabsHtml(a);
  assert.ok(/Not written yet\./.test(html), "the body still shows the placeholder rather than throwing");
  assert.ok((html.match(/ag-tabsbtn off/g) || []).length === 4, "all four /tabs-backed tabs grey out, Draft stays clickable: " + html);
});
/* ── the tabs that were never kept (owner, 2026-09-21) ─────────────────────────────────────
   Three different empties used to look identical on screen. The server now says which one it
   is (`source`, `dropped` on GET /library/{id}/tabs) and the tab says it in words. */
test("an article whose steps were never kept says so, in plain words, on every tab", () => {
  const data = { search_picture: null, research: null, architect: null, edits: null,
                 source: "none", dropped: [] };
  const st = { data };
  [["picture", "search_picture"], ["research", "research"], ["architect", "architect"],
   ["edits", "edits"]].forEach(([id, field]) => {
    const html = A.agTabEmptyHtml(st, field);
    assert.ok(/were not kept/.test(html), id + " says the steps were not kept: " + html);
    assert.ok(!/Not written yet/.test(html), id + " does not promise something still coming");
  });
});
test("and those tabs stay clickable, or the sentence could never be read", () => {
  const a = { libTabs: { on: true, itemId: "lib9", active: "draft",
    data: { search_picture: null, research: null, architect: null, edits: null,
            source: "none", dropped: [] },
    draft: { title: "An old article", words: 900, draft: "# An old article\n\nbody\n" },
    loading: false, error: null, rOpen: {}, secOpen: {} } };
  const html = A.agLibTabsHtml(a);
  assert.ok(!/ag-tabsbtn off/.test(html), "nothing is greyed out: every tab has something to say");
  ["picture", "research", "architect", "edits"].forEach(id => {
    assert.ok(new RegExp('data-ag="libtabsswitch" data-arg="' + id + '"').test(html), id + " can be opened");
  });
});
test("a tab the size guard dropped says THAT, not that the steps were never kept", () => {
  const data = { search_picture: { primary: { keyword: "cost per hire" } }, research: { angle: "a" },
                 architect: null, edits: { passes: ["x"] }, source: "saved", dropped: ["architect"] };
  const st = { data };
  const html = A.agTabArchitectHtml(null, st);
  assert.ok(/too big to share/.test(html), "the real reason: " + html);
  assert.ok(!/were not kept/.test(html), "the steps WERE kept; this one tab did not travel");
  const a = { libTabs: Object.assign({ on: true, itemId: "lib9", active: "architect", draft: null,
    loading: false, error: null, rOpen: {}, secOpen: {} }, { data }) };
  assert.ok(/data-ag="libtabsswitch" data-arg="architect"/.test(A.agLibTabsHtml(a)),
    "and it is still clickable so the reason can be read");
});
test("an ordinary not-there-yet tab is unchanged: Not written yet", () => {
  const st = { data: { search_picture: null, research: null, architect: null, edits: null,
                       source: "run", dropped: [] } };
  assert.ok(/Not written yet\./.test(A.agTabResearchHtml(null, st)), "a live run has not got there yet");
  assert.ok(/Not written yet\./.test(A.agTabPictureHtml(null)), "and a caller with no state at all still works");
});
test("a teammate's kept tabs render exactly like the author's assembled ones", () => {
  /* source "saved" is the ONLY difference in the payload: the tables themselves are the same
     dict the author's Mac assembled, so nothing about the drawing may depend on it. */
  const fresh = A.agTabPictureHtml(SP, { data: { source: "run", dropped: [] } });
  const kept = A.agTabPictureHtml(SP, { data: { source: "saved", dropped: [] } });
  assert.strictEqual(fresh, kept, "byte-for-byte the same tab");
});

test("a milestone row from before /tabs existed (no milestones array) still draws no strip, no throw", () => {
  const html = A.agLibraryHtml([{ id: "old1", title: "Old row", status: "ready", words: 900, created_at: "2026-01-01T00:00:00Z" }]);
  assert.ok(!/ag-miles/.test(html), "no strip drawn for a row with nothing on it");
  assert.ok(/Old row/.test(html));
});

/* ── 4. Purpose and What-was-left-out open the second overlay, from memory, no fetch ──── */
(async () => {
  await atest("clicking Purpose on an Architect section opens the second overlay with just that section's job", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    let fetched = false;
    const prev = A.apiGet;
    A.apiGet = async () => { fetched = true; return {}; };
    await A.agAction("libtabs2open", { getAttribute: k => (k === "data-arg" ? "purpose:1" : "") });
    A.apiGet = prev;
    assert.strictEqual(fetched, false, "the job text is already in memory -- no network call");
    assert.ok(a.libTabs2 && a.libTabs2.on, "the second overlay is open");
    assert.strictEqual(a.libTabs2.kind, "purpose");
    assert.strictEqual(a.libTabs2.body, ARCH.sections[1].job, "the SECOND section's job (index 1), not the first");
    const html = A.agLibTabs2Html(a);
    assert.ok(html.indexOf(ARCH.sections[1].job) !== -1, "on screen");
  });

  await atest("clicking What was left out opens the second overlay listing both its lists, no fetch", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    let fetched = false;
    const prev = A.apiGet;
    A.apiGet = async () => { fetched = true; return {}; };
    await A.agAction("libtabs2open", { getAttribute: k => (k === "data-arg" ? "leftout" : "") });
    A.apiGet = prev;
    assert.strictEqual(fetched, false, "already in memory");
    assert.strictEqual(a.libTabs2.kind, "leftout");
    assert.deepStrictEqual(JSON.parse(JSON.stringify(a.libTabs2.sections)), ARCH.left_out.sections);
    assert.deepStrictEqual(JSON.parse(JSON.stringify(a.libTabs2.faq)), ARCH.left_out.faq);
    const html = A.agLibTabs2Html(a);
    assert.ok(html.indexOf("A history of hiring") !== -1 && html.indexOf("cost per applicant") !== -1);
  });

  /* ── 5. stacked overlays: Escape (via the close helpers the Escape cascade calls) shuts
     only the TOPMOST one ───────────────────────────────────────────────────────────────── */
  await atest("closing with both overlays open clears only layer 2, leaving layer 1 exactly as it was", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    a.libTabs2 = { on: true, kind: "purpose", title: "Purpose", body: "x", loading: false, error: null, openerSel: "" };
    /* this is the same function the Escape keydown cascade calls first, most-specific-first */
    const sel = A.agLibTabs2Close(a);
    assert.strictEqual(a.libTabs2, null, "layer 2 is gone");
    assert.ok(a.libTabs && a.libTabs.on, "layer 1 is UNTOUCHED");
    assert.strictEqual(a.libTabs.itemId, "lib7", "not reset, not refetched");
    void sel;
  });
  await atest("closing layer 1 after layer 2 is already gone clears it and returns nothing further", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    a.libTabs2 = null;
    const sel = A.agLibTabsClose(a);
    assert.strictEqual(a.libTabs, null);
    void sel;
  });

  /* ── 6. the three artifact keys build the right fetch, from the Research/Edits doors ──── */
  await atest("Open the dossier fetches GET /library/{id}/artifact/dossier", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    const seen = [];
    const prev = A.apiGet;
    A.apiGet = async (p) => { seen.push(p); return { key: "dossier", label: "The research dossier", text: "# Dossier\n\nBody." }; };
    await A.agAction("libtabs2open", { getAttribute: k => (k === "data-arg" ? "dossier" : "") });
    A.apiGet = prev;
    assert.ok(seen.some(p => /\/library\/lib7\/artifact\/dossier$/.test(p)), "the exact route: " + seen.join(", "));
    assert.strictEqual(a.libTabs2.kind, "artifact");
    assert.ok(/Dossier/.test(A.agLibTabs2Html(a)), "the markdown is rendered in the overlay");
  });
  await atest("Voices from the field fetches GET /library/{id}/artifact/voices", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    const seen = [];
    const prev = A.apiGet;
    A.apiGet = async (p) => { seen.push(p); return { text: "notes" }; };
    await A.agAction("libtabs2open", { getAttribute: k => (k === "data-arg" ? "voices" : "") });
    A.apiGet = prev;
    assert.ok(seen.some(p => /\/library\/lib7\/artifact\/voices$/.test(p)), seen.join(", "));
  });
  await atest("the source-check door fetches GET /library/{id}/artifact/source-check", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    const seen = [];
    const prev = A.apiGet;
    A.apiGet = async (p) => { seen.push(p); return { text: "notes" }; };
    await A.agAction("libtabs2open", { getAttribute: k => (k === "data-arg" ? "source-check" : "") });
    A.apiGet = prev;
    assert.ok(seen.some(p => /\/library\/lib7\/artifact\/source-check$/.test(p)), seen.join(", "));
  });
  await atest("a door that fails to read says so in the overlay, instead of sitting on Reading…", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.libTabs = fullTabsState();
    const prev = A.apiGet;
    A.apiGet = async () => { throw new Error("that file is not on disk"); };
    await A.agAction("libtabs2open", { getAttribute: k => (k === "data-arg" ? "dossier" : "") });
    A.apiGet = prev;
    assert.strictEqual(a.libTabs2.loading, false);
    assert.ok(/not on disk/.test(a.libTabs2.error));
    assert.ok(/not on disk/.test(A.agLibTabs2Html(a)));
  });

  /* ── 7. Undo / Redo: enabled state off a.libMeta.history, and the right POST route ─────── */
  await atest("Undo and Redo read their enabled state off a.libMeta.history, nowhere else", () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true,
                libId: "lib7", title: "Cost per hire", data: { text: "body" } };
    a.libMeta = { version: 3, edited_by: "", edited_at: "", team: null, has_previous: true,
                  history: { can_undo: true, can_redo: false } };
    const html = A.agPanelHtml(a);
    assert.ok(/data-ag="libundo" data-arg="lib7"(?! disabled)[^>]* title="Undo/.test(html) || /data-ag="libundo" data-arg="lib7" title="Undo/.test(html),
      "Undo is enabled: " + (html.match(/data-ag="libundo"[^>]*>/) || [""])[0]);
    assert.ok(!/data-ag="libundo" data-arg="lib7" disabled/.test(html), "Undo carries no disabled attribute");
    assert.ok(/data-ag="libredo" data-arg="lib7" disabled/.test(html), "Redo IS disabled: nothing to redo to yet");
    a.libMeta.history = { can_undo: false, can_redo: true };
    const html2 = A.agPanelHtml(a);
    assert.ok(/data-ag="libundo" data-arg="lib7" disabled/.test(html2), "now Undo is the disabled one");
    assert.ok(!/data-ag="libredo" data-arg="lib7" disabled/.test(html2), "and Redo is enabled");
  });
  await atest("libundo posts to /library/{id}/undo and re-reads the article on success", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true, libId: "lib7", title: "T", data: { text: "old" } };
    a.libMeta = { version: 1, history: { can_undo: true, can_redo: false } };
    const posts = [], gets = [];
    const prevPost = A.apiPost, prevGet = A.apiGet;
    A.apiPost = async (p, b) => { posts.push([p, b]); return {}; };
    A.apiGet = async (p) => { gets.push(p); return { id: "lib7", title: "T", words: 5, draft: "new body",
      version: 2, history: { can_undo: false, can_redo: true } }; };
    await A.agAction("libundo", { getAttribute: () => "lib7" });
    A.apiPost = prevPost; A.apiGet = prevGet;
    assert.ok(posts.some(([p]) => /\/library\/lib7\/undo$/.test(p)), "posted to undo: " + posts.map(x => x[0]).join(", "));
    assert.ok(gets.some(p => /\/library\/lib7$/.test(p)), "and re-read the whole item afterward");
    assert.strictEqual(a.libMeta.history.can_undo, false, "the fresh history flags landed");
    assert.strictEqual(a.libMeta.history.can_redo, true);
  });
  await atest("libredo posts to /library/{id}/redo", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true, libId: "lib7", title: "T", data: { text: "old" } };
    a.libMeta = { version: 1, history: { can_undo: true, can_redo: true } };
    const posts = [];
    const prevPost = A.apiPost, prevGet = A.apiGet;
    A.apiPost = async (p, b) => { posts.push([p, b]); return {}; };
    A.apiGet = async () => ({ id: "lib7", title: "T", words: 5, draft: "x", version: 3, history: { can_undo: true, can_redo: false } });
    await A.agAction("libredo", { getAttribute: () => "lib7" });
    A.apiPost = prevPost; A.apiGet = prevGet;
    assert.ok(posts.some(([p]) => /\/library\/lib7\/redo$/.test(p)), posts.map(x => x[0]).join(", "));
  });
  await atest("a 404 on undo (nothing earlier) does not throw and does not re-read the item", async () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true, libId: "lib7", title: "T", data: { text: "old" } };
    a.libMeta = { version: 1, history: { can_undo: false, can_redo: false } };
    let gets = 0;
    const prevPost = A.apiPost, prevGet = A.apiGet;
    A.apiPost = async () => { const e = new Error("not found"); e.status = 404; throw e; };
    A.apiGet = async () => { gets++; return {}; };
    await A.agAction("libundo", { getAttribute: () => "lib7" });
    A.apiPost = prevPost; A.apiGet = prevGet;
    assert.strictEqual(gets, 0, "a 404 means nothing to undo to -- the item is not re-read");
    assert.strictEqual(a.libMeta.history.can_undo, false, "nothing on screen changed");
  });
  await atest("the old footer Undo ('Undo last save') is gone from the read-only article view", () => {
    const S = A.S; S.ag = null;
    const a = A.agS();
    a.panel = { run_id: "r1", name: "draft.md", view: "article", loading: false, readOnly: true, libId: "lib7", title: "T", data: { text: "body" } };
    a.libMeta = { version: 1, has_previous: true, history: { can_undo: true, can_redo: true } };
    const html = A.agPanelHtml(a);
    assert.ok(!/data-ag="librevert"/.test(html), "superseded by the top-bar Undo/Redo pair");
  });

  /* ── the five milestone dots open the overlay, in the fixed order, not the server's own ── */
  await atest("the milestone strip re-sorts to Search picture, Research, Architect, Draft, Edits, whatever order the server sent", () => {
    const miles = [
      { key: "edited", label: "Edits", exists: true, at: "2026-09-16T09:00:00Z" },
      { key: "draft", label: "Draft", exists: true, at: "2026-09-16T08:50:00Z" },
      { key: "research", label: "Research", exists: true, at: "2026-09-16T08:00:00Z" },
      { key: "picture", label: "Search picture", exists: true, at: "2026-09-16T08:10:00Z" },
      { key: "plan", label: "Architect", exists: true, at: "2026-09-16T08:30:00Z" },
    ];
    const html = A.agMileStripHtml("lib7", miles, false);
    const order = ["picture", "research", "plan", "draft", "edited"].map(k => html.indexOf('data-name="' + k + '"'));
    for (let i = 1; i < order.length; i++) assert.ok(order[i - 1] < order[i], "each key appears after the one before it in the fixed order: " + order.join(","));
    assert.ok(/data-ag="libtabsopen"/.test(html), "every dot opens the tab overlay");
    assert.ok(!/data-ag="libmile"/.test(html), "the old click target is gone");
  });

  console.log("");
  console.log("------------------------------------------------------------");
  console.log(`library tabs: ${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
