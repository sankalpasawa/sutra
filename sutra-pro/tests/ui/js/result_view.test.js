"use strict";
// ResultView (sutra_app/ui/static/js/result_view.js), SUT-27 / D450: the pure core of the centre panel for any output. Which run is a
// page run, the main result (real-run result, concrete entry file, single output, Files list; never by file name), the viewer per file,
// a part's one-line summary and files, the CSV / JSON tables, the address label and the wording of a non-page run.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const STATIC = path.resolve(__dirname, "../../../sutra_app/ui/static");
const RV = require(path.join(STATIC, "js/result_view.js"));
const FIX = path.resolve(__dirname, "../fixtures");
const load = p => JSON.parse(fs.readFileSync(path.join(FIX, p), "utf8"));
const WEB = load("j2/state.json"), WEBARTS = load("j2/artifacts.json").deliverables;
const SCRIPT = load("result_view/state-script.json"), ARTS = load("result_view/artifacts-script.json").deliverables;
const RUNS = load("result_view/real-runs-script.json");
const copy = x => JSON.parse(JSON.stringify(x));
const row = (file, extra) => ({name: file, type: "t", kind: "type", form: "agent", file, workflows: [], sha256: "x", ...extra});
const st = extra => ({...copy(SCRIPT), ...extra});

test("a page run is a docset run or one whose output type has form page", () => {
  assert.equal(RV.isPageRun(WEB), true);
  assert.equal(RV.isPageRun(SCRIPT), false);
  assert.equal(RV.isPageRun({...copy(SCRIPT), docset: ["prd", "hld"]}), true);
  assert.equal(RV.isPageRun({...copy(SCRIPT), output: null}), false);
  assert.equal(RV.isPageRun({}), false);
});

test("done is the page's isReady, or a saved run", () => {
  assert.equal(RV.done(SCRIPT), true);
  assert.equal(RV.done(WEB), false);                                     // paused
  assert.equal(RV.done(st({status: "running"})), false);
  assert.equal(RV.done(st({outcome: "Working"})), false);
  assert.equal(RV.done(st({outcome: "Working", saved: {id: "r1"}})), true);
  assert.equal(RV.done({}), false);
});

test("main result, AC-10: one output, two outputs, real-run result only with a P45 link, glob and concrete entry files, none", () => {
  const two = [row("index.html"), row("report.txt")];
  const noEntry = extra => st({types: {env_report: {form: "agent"}}, workflows: [], ...extra});
  assert.deepEqual(RV.mainResult(noEntry(), [row("out.txt")]), {kind: "file", row: row("out.txt")});
  assert.deepEqual(RV.mainResult(noEntry(), two), {kind: "list"});
  // the P45 row's result names report.txt: a path in the user's folder, never matched against the outputs
  const rr = noEntry({workflows: [{id: "W-2"}]});
  assert.deepEqual(RV.mainResult(rr, two, RUNS.today), {kind: "list"}, "today's row has only the stdout tail in output: step skipped");
  assert.deepEqual(RV.mainResult(rr, two, RUNS.p45), {kind: "real-run", workflow: "W-2", result: "report.txt", link: "run_output/R-1.json"});
  assert.deepEqual(RV.mainResult(rr, two), {kind: "list"}, "no receipt rows: skipped");
  assert.deepEqual(RV.mainResult(rr, two, [{workflow: "W-2"}]), {kind: "list"}, "today's projection: no run_output key");
  assert.deepEqual(RV.mainResult(rr, [row("one.txt")], RUNS.today), {kind: "file", row: row("one.txt")});
  assert.deepEqual(RV.mainResult(rr, [], RUNS.p45).kind, "real-run", "the real-run result needs no output row");
  // glob entry file: no single main; concrete entry file: that row
  assert.deepEqual(RV.mainResult(SCRIPT, ARTS), {kind: "list"});
  const site = st({output: "website", types: {website: {form: "page", file: "site/index.html"}}, workflows: []});
  const siteRows = [row("site/index.html", {form: "page"}), row("notes.txt")];
  assert.deepEqual(RV.mainResult(site, siteRows), {kind: "file", row: siteRows[0]});
  assert.equal(RV.mainResult(WEB, WEBARTS).row.file, "site/index.html");
  assert.deepEqual(RV.mainResult(st({types: {env_report: {form: "agent", entry_file: "a.txt", file: "x/*"}}}), [row("b.txt"), row("a.txt")]),
    {kind: "file", row: row("a.txt")}, "entry_file wins over file");
  assert.deepEqual(RV.mainResult(st({types: {env_report: {form: "agent", file: "missing.txt"}}}), [row("one.txt")]),
    {kind: "file", row: row("one.txt")}, "an entry file not among the outputs is skipped");
  assert.deepEqual(RV.mainResult(noEntry(), []), {kind: "none"});
  assert.deepEqual(RV.mainResult({}, []), {kind: "none"});
  assert.deepEqual(RV.mainResult(st({output: null}), [row("out.txt")]).kind, "file");
});

test("the real-run step reads only the receipt row's own result and run_output: each workflow's last row, the last in plan order", () => {
  const s = st({workflows: [{id: "W-1"}, {id: "W-2"}, {id: "W-3"}]});
  const ok = (wf, id, result) => ({workflow: wf, run_output: `run_output/${id}.json`, result: result || "out.txt"});
  assert.deepEqual(RV.realRun(s, [ok("W-2", "R-2", "b.txt"), ok("W-1", "R-1", "a.txt")]), {workflow: "W-2", result: "b.txt", link: "run_output/R-2.json"},
    "plan order, not row order");
  assert.equal(RV.realRun(s, [ok("W-2", "R-2"), {workflow: "W-2", output: "tail"}]), null, "a workflow's last row decides");
  assert.deepEqual(RV.realRun(s, [ok("W-1", "R-1", "a.txt"), {workflow: "W-2", output: "tail"}]), {workflow: "W-1", result: "a.txt", link: "run_output/R-1.json"},
    "a later workflow without a link does not hide an earlier one");
  assert.equal(RV.realRun(s, [ok("W-9", "R-9")]), null, "a row for a workflow not in the plan is not read");
  assert.equal(RV.realRun(s, [{workflow: "W-2", run_output: "run_output/R-1.json"}]), null, "run_output without result: skipped");
  assert.equal(RV.realRun(s, [{workflow: "W-2", run_output: "run_output/R-1.json", result: ""}]), null);
  assert.equal(RV.realRun(st({workflows: [{id: "W-2", real_run: {result: "b.txt"}}]}), [{workflow: "W-2", run_output: "run_output/R-1.json"}]), null,
    "the plan's real_run.result is not read");
  for (const bad of ["run_output/../x.json", "run_output/a/b.json", "x/run_output/R.json", "run_output/R.json\nmore", "run_output/.json",
    "run_output/R.txt", " run_output/R.json", "...run_output/R-1.json", 7, null]) {
    assert.equal(RV.realRun(s, [{workflow: "W-2", run_output: bad, result: "b.txt"}]), null, String(bad));
  }
  assert.equal(RV.realRun(s, [{workflow: "W-2", output: "run_output/R-4.json", result: "b.txt"}]), null, "`output` is never read as a link");
  assert.equal(RV.realRun(s, [{workflow: "W-2", run_output: "run_output/R-1.json", dry_run: {result: "b.txt"}, expect: {result: "b.txt"}}]), null,
    "dry_run and expect are not read");
  assert.deepEqual(RV.realRun(s, RUNS.p45), {workflow: "W-2", result: "report.txt", link: "run_output/R-1.json"},
    "only workflow, result and run_output come back: no folder changes are read");
  assert.equal(RV.realRun(s, RUNS.today), null);
  assert.equal(RV.realRun({}, RUNS.p45), null);
});

test("named is the concrete entry file only: a glob or an absent field gives nothing", () => {
  assert.equal(RV.named(SCRIPT), "");
  assert.equal(RV.named(WEB), "site/index.html");
  assert.equal(RV.named({}), "");
  assert.equal(RV.named(st({output: null})), "");
});

test("viewer by form and extension, AC-5", () => {
  const got = ["a.md", "b.txt", "c.py", "d.csv", "e.json", "f.png", "g.html", "h.docx"].map(f => RV.viewerFor(row(f)));
  assert.deepEqual(got, ["frame", "text", "code", "table", "json", "frame", "frame", "download"]);
  assert.equal(RV.viewerFor(row("site/index.html", {form: "page"})), "site");
  assert.equal(RV.viewerFor(row("dir/REPORT.TXT")), "text");
  assert.equal(RV.viewerFor(row("x.tsv")), "table");
  assert.equal(RV.viewerFor(row("x.log")), "text");
  assert.equal(RV.viewerFor(row("Makefile")), "download");
  assert.equal(RV.viewerFor(row("dir.v2/README")), "download");
  assert.equal(RV.viewerFor({}), "download");
});

test("a part's summary: the last message of its workflows, leading @name removed, first sentence; else Finished., AC-11", () => {
  const part = {sec: "W-2", workflows: ["W-2"]};
  assert.equal(RV.summaryOf(SCRIPT, part), "I wrote env_report/report.py.");
  const s = st({chat: [{who: "W-2", human_output: "@Coordination Wrote the script. It prints env vars."}]});
  assert.equal(RV.summaryOf(s, part), "Wrote the script.");
  s.allChat = [{who: "W-2", human_output: "@Coordination First."}, {who: "W-1", human_output: "Other part."}, {who: "W-2", human_output: "Later one! More."}];
  assert.equal(RV.summaryOf(s, part), "Later one!", "allChat is preferred, the last message wins");
  assert.equal(RV.summaryOf(SCRIPT, {sec: "W-1", workflows: ["W-1"]}), "Finished.");
  assert.equal(RV.summaryOf(st({chat: [{who: "W-2", human_output: "No full stop here"}]}), part), "No full stop here");
  assert.equal(RV.summaryOf(st({chat: [{who: "W-2", human_output: "@Coordination "}]}), part), "Finished.");
  assert.equal(RV.summaryOf(st({chat: [{who: "W-2", text: "only text"}]}), part), "Finished.");
  assert.equal(RV.summaryOf({}, {}), "Finished.");
});

test("a part's files are the rows sharing a workflow with it", () => {
  assert.deepEqual(RV.filesOfPart({workflows: ["W-2"]}, ARTS).map(r => r.file), ["env_report/report.py", "env_report/report.txt"]);
  assert.deepEqual(RV.filesOfPart({workflows: ["W-1"]}, ARTS), []);
  assert.deepEqual(RV.filesOfPart({workflows: ["W-3", "W-9"]}, WEBARTS).map(r => r.file), ["site/index.html"]);
  assert.deepEqual(RV.filesOfPart({}, ARTS), []);
  assert.deepEqual(RV.filesOfPart({workflows: ["W-2"]}, [{file: "x"}]), []);
});

test("CSV and TSV tables: quotes, doubled quotes, CRLF; an unterminated quote does not parse; 1,000 rows at most", () => {
  assert.deepEqual(RV.table('name,note\r\n"Smith, J","said ""hi"""\r\nx,\n'), {head: ["name", "note"], rows: [["Smith, J", 'said "hi"'], ["x", ""]], total: 2});
  assert.deepEqual(RV.table("a\tb\n1\t2", "\t"), {head: ["a", "b"], rows: [["1", "2"]], total: 1});
  assert.deepEqual(RV.table('a,b\n"line\nbreak",2'), {head: ["a", "b"], rows: [["line\nbreak", "2"]], total: 1});
  assert.equal(RV.table('a,b\n"open,1'), null);
  assert.equal(RV.table(""), null);
  const big = "n\n" + Array.from({length: 1500}, (_, i) => String(i)).join("\n");
  const t = RV.table(big);
  assert.equal(t.rows.length, 1000);
  assert.equal(t.total, 1500);
  assert.deepEqual(t.rows[999], ["999"]);
});

test("JSON table only for an array of objects; anything else is null (the caller shows numbered text)", () => {
  assert.deepEqual(RV.jsonTable('[{"a":1,"b":"x"},{"b":null,"c":{"d":2}}]'),
    {head: ["a", "b", "c"], rows: [["1", "x", ""], ["", "", '{"d":2}']], total: 2});
  assert.equal(RV.jsonTable('{"a":1}'), null);
  assert.equal(RV.jsonTable("[1,2]"), null);
  assert.equal(RV.jsonTable("[]"), null);
  assert.equal(RV.jsonTable("[{]"), null);
  assert.equal(RV.jsonTable("[null]"), null);
  const t = RV.jsonTable(JSON.stringify(Array.from({length: 1500}, (_, i) => ({i}))));
  assert.equal(t.rows.length, 1000);
  assert.equal(t.total, 1500);
});

test("the address label: team as today, site as today on a page run, the file's name or files otherwise", () => {
  const main = RV.mainResult(SCRIPT, ARTS);
  assert.equal(RV.label(SCRIPT, "team", main), "how your project was made");
  assert.equal(RV.label(st({status: "running", outcome: ""}), "team", main), "your team, live");
  assert.equal(RV.label(SCRIPT, "result", main), "files");
  assert.equal(RV.label(SCRIPT, "files", main), "files");
  assert.equal(RV.label(SCRIPT, "file:env_report/report.txt", main), "report.txt");
  assert.equal(RV.label(SCRIPT, "result", {kind: "file", row: ARTS[1]}), "report.txt");
  assert.equal(RV.label(SCRIPT, "result", {kind: "real-run", result: "out/report.txt"}), "report.txt");
  assert.equal(RV.label(SCRIPT, "result", {kind: "none"}), "no files");
  assert.equal(RV.label(st({status: "running", outcome: ""}), "result", main), "result");
  const web = {...copy(WEB), paused: null, status: "done", outcome: "Done", goal: {site_name: "Brew Lab!"}};
  assert.equal(RV.label(web, "result", RV.mainResult(web, WEBARTS)), "brewlab · preview");
  assert.equal(RV.label({...web, status: "running", outcome: ""}, "result", {kind: "none"}), "brewlab · live preview");
});

test("the wording of a non-page run never says site, page or website", () => {
  const strings = Object.values(RV.WORDS).map(v => typeof v === "function" ? v(1000, 1500) : v);
  assert.ok(strings.length >= 8);
  for (const v of strings) assert.doesNotMatch(v, /\b(site|page|website)\b/i, v);
  assert.equal(RV.WORDS.checking, "Checking the work");
  assert.equal(RV.WORDS.partDrawer, "The part, in the result.");
  assert.equal(RV.WORDS.soon, "Your result will appear here when the team finishes.");
  assert.equal(RV.WORDS.noFiles, "This run produced no files.");
  assert.equal(RV.WORDS.cantShow, "This file can't be shown here (it may be over 2 MB).");
  assert.equal(RV.WORDS.copied, "Link copied — opens on this computer only");
  assert.equal(RV.WORDS.showing(1000, 1500), "Showing 1,000 of 1,500 rows");
});

test("adopt is a stub until T2: it changes nothing", () => {
  const root = {sViews() {}};
  const before = root.sViews;
  assert.equal(RV.adopt(root), false);
  assert.equal(root.sViews, before);
});

// ---- the page glue (T2): the module loaded after a stub of J2's page, as the page loads it (a classic script, page globals by bare name)
const vm = require("node:vm");
const SRC = fs.readFileSync(path.join(STATIC, "js/result_view.js"), "utf8");

function fakeEl(id) {
  const cls = new Set();
  return {id, innerHTML: "", hidden: false, children: [], className: "",
    classList: {toggle: (c, on) => (on ? cls.add(c) : cls.delete(c), on), contains: c => cls.has(c), add: c => cls.add(c), remove: c => cls.delete(c)},
    appendChild(c) { this.children.push(c); return c; }, querySelectorAll: () => [],
    attrs: {}, setAttribute(k, v) { this.attrs[k] = String(v); },
    listeners: [], addEventListener(type, fn, capture) { this.listeners.push({type, fn, capture}); }};
}

// files: {file name: text | null (404)}; omit: page globals left out of the stub
function page({files = {}, omit = [], groups = null} = {}) {
  const els = {}, el = id => (els[id] = els[id] || fakeEl(id));
  ["sframebox", "sviews", "surl", "steamwork", "sout", "sdbody", "sopen", "sfinish"].forEach(el);
  const head = fakeEl("head");
  const document = {
    head,
    getElementById: id => els[id] || null,
    createElement: () => { const e = fakeEl(""); return new Proxy(e, {set(t, k, v) { t[k] = v; if (k === "id" && v) els[v] = t; return true; }}); },
    querySelector: sel => head.children.find(c => sel.includes(c.href)) || null,
  };
  const log = {load: [], fetch: [], toast: [], orig: 0, copied: [], timers: []};
  const fetch = async url => {
    log.fetch.push(url);
    if (url.startsWith("/api/artifacts/groups")) return groups ? {ok: true, json: async () => groups} : {ok: false, status: 404};
    const name = decodeURIComponent((/[?&]name=([^&]*)/.exec(url) || [])[1] || "");
    if (!url.startsWith("/api/artifact?") || files[name] === undefined || files[name] === null) return {ok: false, status: 404};
    return {ok: true, text: async () => files[name]};
  };
  const ctx = vm.createContext({document, fetch, log, console, location: {origin: "http://127.0.0.1:8765"},
    navigator: {clipboard: {writeText: async url => { log.copied.push(url); }}}, setTimeout: (fn, ms) => log.timers.push({fn, ms})});
  const decl = {
    SV: 'const SV = {arts: {}, akey: "", view: "", pick: "", lastOut: ""};',
    esc: 'const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;"}[c]));',
    runQ: 'const runQ = () => "&run=r1";',
    isReady: 'const isReady = s => /^Done/.test(s.outcome || "") && !s.paused && s.status !== "running";',
    sNoun: 'const sNoun = s => "result";',
    sLoad: "function sLoad(u){ log.load.push(u); }",
    paint: "function paint(el, html){ if (el.__html === html) return; el.innerHTML = html; el.__html = html; }",
    sTeamwork: 'function sTeamwork(s){ return (s.teamHTML || "<div>the team</div>"); }',
    sSkTime: "function sSkTime(){}",
    sDecorate: "function sDecorate(){}",
    sViews: "function sViews(){ log.orig++; }",
  };
  const stub = Object.entries(decl).filter(([k]) => !omit.includes(k)).map(([, v]) => v).join("\n")
    + "\nconst TYL = (k, d) => d;\nfunction sToast(t){ log.toast.push(t); }\nfunction renderSimple(s){ sViews(s, {}, isReady(s)); }"
    + "\nconst failed = s => !!s.error;"
    + "\nfunction sFinish(s){ return 'PAGE-FINISH:' + s.output; }"
    + "\nfunction sGo(sec){ log.go = sec; }"
    + "\nasync function sOpenPart(sec){ log.part = sec; document.getElementById('sdbody').innerHTML = '<p>The part, on the page.</p>'; }"
    + "\nfunction sPhase(s){ return s.phase || 'Checking it on a phone and a laptop'; }"
    + "\nfunction sTabs(s){ return (s.tabs || (s.versions > 0 && !(s.docset || []).length ? [{k: 'site', label: 'Page'}] : [])).concat([{k: 'team'}]); }";
  vm.runInContext(stub, ctx);
  vm.runInContext(SRC, ctx, {filename: "result_view.js"});
  const SV = omit.includes("SV") ? null : vm.runInContext("SV", ctx);
  return {ctx, els, log, SV, render: s => ctx.renderSimple(s), html: id => els[id].innerHTML};
}
const tick = () => new Promise(r => setTimeout(r, 0));
const tabs = p => [...p.html("sviews").matchAll(/data-view="(\w+)" aria-selected="(true|false)">([^<]+)/g)].map(m => [m[3], m[2] === "true"]);
const webDone = () => ({...copy(WEB), paused: null, status: "done", outcome: "Done: the site is ready."});
const scriptRun = extra => ({...copy(SCRIPT), ...extra});

test("glue: adopt replaces sViews and adds #rvpane with its #rvlater slot and the stylesheet", () => {
  const p = page();
  assert.equal(p.ctx.ResultView.adopt(p.ctx), false, "adopts once");
  const pane = p.els.rvpane;
  assert.ok(pane && pane.hidden);
  assert.deepEqual(pane.children.map(c => c.id), ["rvbody", "rvlater"]);
  assert.equal(p.els.sout.children[0].id, "rvpane");
  assert.equal(p.ctx.document.head.children[0].href, "/ui/css/result_view.css");
  p.render(scriptRun());
  assert.equal(p.log.orig, 0);
});

test("glue: a missing page global leaves the page as J2 drew it", () => {
  for (const omit of [["SV"], ["esc"], ["sLoad"], ["sTeamwork"], ["isReady"]]) {
    const p = page({omit});
    assert.equal(p.els.rvpane, undefined, omit[0]);
    if (omit[0] !== "isReady") { p.render(scriptRun()); assert.equal(p.log.orig, 1, omit[0]); }
  }
});

test("glue: a done website shows three tabs, Result selected, and the site in the sandboxed frame", () => {
  const p = page();
  p.SV.arts = {deliverables: WEBARTS};
  p.render(webDone());
  assert.deepEqual(tabs(p), [["Result", true], ["Files", false], ["How it was made", false]]);
  assert.deepEqual(p.log.load, ["/site/v5?x=1&run=r1"]);
  assert.equal(p.SV.view, "site");
  assert.ok(p.els.rvpane.hidden);
  assert.ok(p.els.sframebox.classList.contains("site"));
  assert.equal(p.html("surl"), "<span>brewlab · preview</span>", "the page's own label");
});

test("glue: a running website opens How it was made; Result picked shows the live site; its toast is today's", () => {
  const p = page();
  const s = {...copy(WEB), paused: null, status: "running", outcome: ""};
  p.render({...s, versions: 0});
  assert.deepEqual(p.log.toast, []);
  p.render(s);
  assert.deepEqual(tabs(p).find(t => t[1])[0], "How it was made");
  assert.match(p.html("steamwork"), /the team/);
  assert.equal(p.els.steamwork.hidden, false);
  assert.deepEqual(p.log.load, []);
  p.render(s);
  assert.deepEqual(p.log.toast, ["The page is taking shape"], "once, when the site first appears");
  p.SV.pick = "result";
  p.render(s);
  assert.deepEqual(p.log.load, ["/site/v5?x=1&run=r1"]);
  assert.match(p.html("sviews"), /data-view="result" aria-selected="true">Result<span class="pip"/);
});

test("glue: a running script shows the placeholder in Result and no toast", () => {
  const p = page();
  const s = scriptRun({status: "running", outcome: ""});
  p.render(s); p.render(s);
  assert.deepEqual(p.log.toast, []);
  p.SV.pick = "result";
  p.render(s);
  assert.match(p.html("rvbody"), /Your result will appear here when the team finishes\./);
  assert.equal(p.els.rvpane.hidden, false);
  assert.ok(p.els.sframebox.classList.contains("rvpane"));
  assert.equal(p.html("surl"), "<span>result</span>");
});

test("glue: a done script with two files shows the Files list in Result, and Files lists both with Download", () => {
  const p = page();
  p.SV.arts = {deliverables: ARTS};
  p.render(scriptRun());
  assert.deepEqual(tabs(p), [["Result", true], ["Files", false], ["How it was made", false]]);
  const list = p.html("rvbody");
  assert.equal((list.match(/<li>/g) || []).length, 2);
  assert.match(list, /data-view="file:env_report\/report.py"/);
  assert.match(list, /href="\/api\/artifact\?name=env_report%2Freport.txt&run=r1" download="report.txt">Download</);
  p.SV.pick = "files";
  p.render(scriptRun()); p.render(scriptRun());
  assert.equal(tabs(p).find(t => t[1])[0], "Files", "the pick is kept across renders");
  assert.equal((p.html("rvbody").match(/>Download</g) || []).length, 2);
  assert.equal(p.html("surl"), "<span>files</span>");
});

test("glue: one text file is the result: fetched once over two renders, escaped, with its name and Download", async () => {
  const p = page({files: {"env_report/report.txt": "<b>x</b>\nline 2"}});
  p.SV.arts = {deliverables: [ARTS[1]]};
  p.render(scriptRun());
  assert.match(p.html("rvbody"), /Opening/);
  await tick();
  p.render(scriptRun());
  assert.deepEqual(p.log.fetch, ["/api/artifact?name=env_report%2Freport.txt&run=r1"]);
  const body = p.html("rvbody");
  assert.match(body, /<pre class="rvtext">&lt;b&gt;x&lt;\/b&gt;\nline 2<\/pre>/);
  assert.doesNotMatch(body, /<b>x<\/b>/);
  assert.match(body, /<b>env_report\/report.txt<\/b><a class="rvdl" href="\/api\/artifact\?name=env_report%2Freport.txt&run=r1" download="report.txt">/);
  assert.equal(p.html("surl"), "<span>report.txt</span>");
});

test("glue: each viewer: code numbered, CSV and JSON tables, bad CSV as numbered text, markdown in the frame, a 404 line", async () => {
  const files = {"a.py": "print(1)\nprint(2)\n", "d.csv": "h1,h2\n1,2", "e.json": '[{"k":"<v>"}]', "bad.csv": 'a,"b', "gone.txt": null};
  const p = page({files});
  p.SV.arts = {deliverables: Object.keys(files).concat(["n.md", "x.docx"]).map(f => row(f))};
  const show = async f => { p.SV.pick = "file:" + f; p.render(scriptRun()); await tick(); p.render(scriptRun()); return p.html("rvbody"); };
  assert.match(await show("a.py"), /<div class="rvcode"><code>print\(1\)<\/code><code>print\(2\)<\/code><\/div>/);
  assert.match(await show("d.csv"), /<thead><tr><th>h1<\/th><th>h2<\/th><\/tr><\/thead><tbody><tr><td>1<\/td><td>2<\/td><\/tr>/);
  assert.match(await show("e.json"), /<th>k<\/th>.*<td>&lt;v&gt;<\/td>/);
  assert.match(await show("bad.csv"), /<div class="rvcode"><code>a,&quot;b<\/code>/);
  assert.match(await show("gone.txt"), /This file can't be shown here \(it may be over 2 MB\)\./);
  const docx = await show("x.docx");
  assert.match(docx, /download="x.docx"/);
  assert.match(docx, /data-view="files">All files</, "a file opened from Files has the way back");
  await show("n.md");
  assert.equal(p.log.load.pop(), "/view?name=n.md&run=r1");
  assert.ok(p.els.rvpane.classList.contains("rvbar") && p.els.sframebox.classList.contains("rvbar"));
  assert.ok(!p.els.sframebox.classList.contains("rvpane"));
  assert.ok(p.log.fetch.every(u => !u.includes("n.md") && !u.includes("x.docx")), "frame and download viewers fetch nothing");
});

test("glue: a saved script run never asks for a /site/ URL; output null and an old pick do not throw", async () => {
  const p = page({files: {"env_report/report.txt": "ok"}});
  p.SV.arts = {deliverables: [ARTS[1]]};
  const saved = scriptRun({status: "saved", outcome: "", saved: {id: "r1"}});
  for (const pick of ["", "site", "a:Environment report", "result", "files", "file:env_report/report.txt", "file:missing"]) {
    p.SV.pick = pick; p.render(saved);
  }
  await tick();
  p.render(scriptRun({output: null, types: {}}));
  p.SV.pick = "";
  p.render(scriptRun({output: null, types: {}, status: "running", outcome: ""}));
  assert.ok(p.log.load.concat(p.log.fetch).every(u => !u.startsWith("/site/")), p.log.load.concat(p.log.fetch).join(" "));
  assert.equal(p.log.orig, 0);
  assert.equal(tabs(p).length, 3);
});

test("glue: zero outputs reads 'This run produced no files.' in Result and Files", () => {
  const p = page();
  p.SV.arts = {deliverables: []};
  p.render(scriptRun());
  assert.match(p.html("rvbody"), /This run produced no files\./);
  p.SV.pick = "files"; p.render(scriptRun());
  assert.match(p.html("rvbody"), /This run produced no files\./);
});

test("glue: a throw inside the module falls back to the page's own sViews", () => {
  const p = page();
  p.render(new Proxy(scriptRun(), {get(t, k) {      // only the module reads `workflows`: it throws there, the page's sViews draws
     if (k === "workflows") throw new Error("boom"); return t[k]; }}));
  assert.equal(p.log.orig, 1);
});

test("glue: sGo opens the part's record on a run that is not a website, the page's own on a website", () => {
  const p = page();
  p.render(scriptRun());
  p.ctx.sGo("W-2");
  assert.equal(p.log.part, "W-2");
  assert.equal(p.log.go, undefined);
  p.render(webDone());
  p.ctx.sGo("W-3");
  assert.equal(p.log.go, "W-3");
});

// ---- T3: plan cards and wording. Card markup as the page's sTeamwork writes it (j2_ui.html sTeamwork `part`)
const SLB = '<span class="sl" aria-hidden="true"><i></i><i></i><i></i></span>';
const card = (sec, st, name) => `<button type="button" class="spart ${st}" data-part="${sec}" style="--c:var(--s-mira)"><span class="spn" aria-hidden="true">01</span><b>${name || sec}</b>`
  + (st === "doing" || st === "fix" ? '<svg class="ssk"></svg>' : SLB) + (st === "next" ? "<small>Mira next</small>" : "") + "</button>";
const PLACEHOLDER = `<div class="spart next"><b>&nbsp;</b>${SLB}</div>`;
const gotSite = n => `<section class="stw-sec"><h3>What you got</h3><div class="sdocs"><button type="button" data-view="site"><svg></svg>The page, version ${n}</button></div></section>`;
const teamOf = s => `<div class="smap"><div class="smap-parts">${s.studio.parts.map(p => card(p.sec, p.st, p.name)).join("")}</div></div>` + (s.versions > 0 ? gotSite(s.versions) : "");

test("plan cards: a done card shows its builder's line and its files, no grey bars, AC-11", () => {
  const out = RV.team(teamOf(SCRIPT), SCRIPT, ARTS);
  const w2 = /<button[^>]*data-part="W-2"[^>]*>([\s\S]*?)<\/button>/.exec(out)[1], w1 = /<button[^>]*data-part="W-1"[^>]*>([\s\S]*?)<\/button>/.exec(out)[1];
  assert.match(w2, /<small class="rvsum">I wrote env_report\/report.py.<\/small>/);
  assert.equal((w2.match(/class="rvfile" data-view="file:env_report\/report\.(py|txt)"/g) || []).length, 2);
  assert.match(w2, />report.txt<\/span>/);
  assert.match(w1, /<small class="rvsum">Finished.<\/small>$/, "no message: Finished., and no file list");
  assert.doesNotMatch(out, /class="sl"/);
  const s = scriptRun({chat: [{who: "W-2", human_output: "@Coordination Wrote the script. It prints env vars."}]});
  assert.match(RV.team(card("W-2", "done"), s, ARTS), /<small class="rvsum">Wrote the script.<\/small>/);
  assert.match(RV.team(card("W-2", "done"), scriptRun({chat: [{who: "W-2", human_output: '<img src=x onerror="y">. Two.'}]}), []),
    /<small class="rvsum">&lt;img src=x onerror=&quot;y&quot;&gt;.<\/small>/, "the line is escaped");
});

test("plan cards: grey bars stay only on cards in progress and on placeholders, AC-12", () => {
  const html = ["doing", "fix", "next", "bad", "ask", "done"].map((st, i) => card("W-" + (i + 1), st)).join("") + PLACEHOLDER;
  const out = RV.team(html, scriptRun({studio: {parts: []}}), []);
  const cards = [...out.matchAll(/<(button|div)[^>]*class="spart ([a-z]+)[^"]*"[^>]*>([\s\S]*?)<\/\1>/g)].map(m => [m[2], m[3].includes('class="sl"')]);
  assert.deepEqual(cards, [["doing", false], ["fix", false], ["next", false], ["bad", false], ["ask", false], ["done", false], ["next", true]]);
  assert.match(out, /<small>Mira next<\/small>/, "the rest of a card's look is kept");
  assert.equal((out.match(/rvsum/g) || []).length, 1, "only the done card gets a line");
  assert.equal(RV.team(html.replace('class="spart doing"', 'class="spart doing fresh"'), scriptRun(), []).includes("ssk"), true);
});

test("plan cards: a website's cards are decorated and its 'What you got' site line stays; a script's goes with its empty section", () => {
  const web = webDone(), webOut = RV.team(teamOf(web), web, WEBARTS);
  assert.match(webOut, /rvsum/);
  assert.match(webOut, /data-view="site">.*The page, version 5/);
  const out = RV.team(teamOf(SCRIPT), SCRIPT, ARTS);
  assert.doesNotMatch(out, /data-view="site"|What you got|stw-sec/);
  const kept = RV.team('<section class="stw-sec"><h3>What you got</h3><div class="sdocs"><a href="/file/x" download>The document (markdown)</a><button type="button" data-view="site">The page, version 1</button></div></section>', SCRIPT, []);
  assert.equal(kept, '<section class="stw-sec"><h3>What you got</h3><div class="sdocs"><a href="/file/x" download>The document (markdown)</a></div></section>');
});

test("glue T3: How it was made is decorated through the page's sTeamwork; #sopen is hidden only on runs that are not a website", () => {
  const p = page();
  p.SV.arts = {deliverables: ARTS};
  p.els.sopen.hidden = false;
  p.SV.pick = "team";
  p.render(scriptRun({teamHTML: teamOf(SCRIPT)}));
  assert.match(p.html("steamwork"), /<small class="rvsum">I wrote env_report\/report.py.<\/small>/);
  assert.equal(p.els.sopen.hidden, true);
  assert.equal(p.els.sopen.attrs.href, "#", "no /site/ link left on a hidden button");
  const w = page();
  w.SV.arts = {deliverables: WEBARTS};
  w.els.sopen.hidden = false;
  w.SV.pick = "team";
  w.render({...webDone(), teamHTML: teamOf(webDone())});
  assert.equal(w.els.sopen.hidden, false);
  assert.match(w.html("steamwork"), /The page, version 5/);
});

test("glue T3: the phase and the part drawer say 'the work' and 'the result' on a run that is not a page run; a website keeps the page's", async () => {
  const p = page();
  p.render(scriptRun());
  assert.equal(p.ctx.sPhase(scriptRun(), []), "Checking the work");
  assert.equal(p.ctx.sPhase(webDone(), []), "Checking it on a phone and a laptop");
  assert.equal(p.ctx.sPhase(scriptRun({phase: "Planning the work"}), []), "Planning the work");
  await p.ctx.sOpenPart("W-2");
  assert.equal(p.html("sdbody"), "<p>The part, in the result.</p>");
  p.render(webDone());
  await p.ctx.sOpenPart("W-2");
  assert.equal(p.html("sdbody"), "<p>The part, on the page.</p>");
});

test("glue T3: a wrapper whose helper throws returns the page's own output", () => {
  const p = page();
  const bad = new Proxy(scriptRun(), {get(t, k) { if (k === "docset") throw new Error("boom"); return t[k]; }});
  assert.equal(p.ctx.sPhase(bad, []), "Checking it on a phone and a laptop");
  assert.equal(p.ctx.sTeamwork(new Proxy(scriptRun({teamHTML: "<p>x</p>"}), {get(t, k) { if (k === "studio") throw new Error("boom"); return t[k]; }})), "<p>x</p>");
});

test("glue T3: toasts as the page's own on page runs: a website's site, a document set's documents; none on other runs", () => {
  const run = extra => ({...copy(WEB), paused: null, status: "running", outcome: "", ...extra});
  const docs = page();
  docs.render(run({docset: ["prd", "hld"], versions: 0, tabs: []}));
  docs.render(run({docset: ["prd", "hld"], versions: 0, tabs: [{k: "prd", label: "PRD"}]}));
  docs.render(run({docset: ["prd", "hld"], versions: 0, tabs: [{k: "prd", label: "PRD"}, {k: "hld", label: "HLD"}]}));
  assert.deepEqual(docs.log.toast, ["The PRD is being written", "The HLD is being written"]);
  const script = page();
  script.render(scriptRun({status: "running", outcome: "", versions: 0}));
  script.render(scriptRun({status: "running", outcome: "", versions: 1, tabs: [{k: "a:Environment report", label: "Environment report"}]}));
  assert.deepEqual(script.log.toast, []);
});

test("the done script run's panel never says site, page or website, AC-13 / FR-18", async () => {
  const p = page({files: {}});
  p.SV.arts = {deliverables: ARTS};
  const s = scriptRun({teamHTML: teamOf(SCRIPT)});
  const text = id => p.html(id).replace(/<[^>]*>/g, " ");
  for (const pick of ["result", "files", "team", "file:env_report/report.txt"]) {
    p.SV.pick = pick; p.render(s); await tick(); p.render(s);
    for (const id of ["sviews", "surl", "steamwork", "rvbody"]) assert.doesNotMatch(text(id), /\b(site|page|website)\b/i, `${pick} ${id}: ${text(id)}`);
  }
});

// ---- T4: the finish bar and Copy share link
const finishOf = (p, s) => p.ctx.sFinish(s);
test("finish bar: one main file is downloaded by its own name through /api/artifact; with it, Copy share link", () => {
  const p = page();
  p.SV.arts = {deliverables: [ARTS[1]]};
  const html = finishOf(p, scriptRun());
  assert.ok(html.startsWith('<span class="sfmsg"><span><i aria-hidden="true">✓</i>Checking the work</span></span>'), "the page's phase, through the wrapped sPhase");
  assert.match(html, /<a class="pri" href="\/api\/artifact\?name=env_report%2Freport.txt&run=r1" download="report.txt"><svg[^>]*><path d="M12 4v11M7 10l5 5 5-5M5 20h14"\/><\/svg>Download<\/a>/);
  assert.match(html, /<button type="button" data-share><svg[\s\S]*?<\/svg>Copy share link<\/button><button type="button" data-full>/);
  assert.doesNotMatch(html, /href="\/site\//);
});

test("finish bar: two files give All files (2), no files give nothing, a real-run result gives no Download; none has Copy share link (Q-4)", () => {
  const p = page();
  p.SV.arts = {deliverables: ARTS};
  const two = finishOf(p, scriptRun());
  assert.match(two, /<button type="button" data-view="files">All files \(2\)<\/button>/);
  p.SV.arts = {deliverables: []};
  const none = finishOf(p, scriptRun());
  assert.doesNotMatch(none, /data-share|class="pri"|data-view/);
  assert.match(none, /data-full/);
  for (const html of [two, none]) assert.doesNotMatch(html, /data-share/);
});

test("finish bar: a real-run result (P45 rows from /api/artifacts/groups) has no Download and no Copy share link", async () => {
  const q = page({groups: {groups: [{id: "documents", rows: [{id: "x", real_runs: RUNS.p45}]}]}});
  q.SV.arts = {deliverables: [ARTS[1]]};
  q.SV.akey = "k1";
  q.render(scriptRun());
  await tick();
  assert.ok(q.log.fetch.some(u => u.startsWith("/api/artifacts/groups?x=1&run=r1")));
  const html = finishOf(q, scriptRun());
  assert.doesNotMatch(html, /data-share|class="pri"|data-view/);
  q.SV.pick = "result"; q.render(scriptRun());
  assert.match(q.html("rvbody"), /<b>report.txt<\/b>/);
});

test("finish bar: a website and a document set keep the page's own sFinish, byte for byte", () => {
  const p = page();
  p.SV.arts = {deliverables: WEBARTS};
  assert.equal(finishOf(p, webDone()), "PAGE-FINISH:website");
  assert.equal(finishOf(p, scriptRun({docset: ["prd", "hld"], output: "prd"})), "PAGE-FINISH:prd");
});

test("finish bar: drawn again when /api/artifacts arrives after the run turned ready; a page run's is left to the page", () => {
  const p = page();
  p.render(scriptRun());
  assert.doesNotMatch(p.html("sfinish"), /class="pri"|data-view/);
  p.SV.arts = {deliverables: [ARTS[1]]};
  p.render(scriptRun());
  assert.match(p.html("sfinish"), /download="report.txt"/);
  p.els.sfinish.innerHTML = "kept";      // an identical render does not write it again (a copied note stays)
  p.render(scriptRun());
  assert.equal(p.html("sfinish"), "kept");
  const w = page();
  w.render(webDone());
  assert.equal(w.html("sfinish"), "");
  const f = page();
  f.render(scriptRun({error: "x"}));
  assert.equal(f.html("sfinish"), "", "a failed run's bar is the page's");
});

test("Copy share link: a script run copies its main file's /view link, a website the page's URL; the note, then back after 2.5 s", async () => {
  const click = async (p, s) => {
    p.render(s);
    const btn = {textContent: "Copy share link"}, ev = {target: {closest: sel => sel === "[data-share]" ? btn : null}, stopped: false, stopImmediatePropagation() { this.stopped = true; }};
    const l = p.els.sfinish.listeners.find(x => x.type === "click");
    assert.equal(l.capture, true);
    l.fn(ev);
    await tick();
    return {btn, ev};
  };
  const p = page();
  p.SV.arts = {deliverables: [ARTS[1]]};
  const {btn, ev} = await click(p, scriptRun());
  assert.equal(ev.stopped, true, "the page's own listener does not run");
  assert.deepEqual(p.log.copied, ["http://127.0.0.1:8765/view?name=env_report%2Freport.txt&run=r1"]);
  assert.equal(btn.textContent, "Link copied — opens on this computer only");
  assert.equal(p.log.timers[0].ms, 2500);
  p.log.timers[0].fn();
  assert.equal(btn.textContent, "Copy share link");
  const w = page();
  w.SV.arts = {deliverables: WEBARTS};
  const web = await click(w, webDone());
  assert.deepEqual(w.log.copied, ["http://127.0.0.1:8765/site/latest?run=r1"]);
  assert.equal(web.btn.textContent, "Link copied — opens on this computer only");
  const other = page(), ev2 = {target: {closest: () => null}, stopImmediatePropagation() { throw new Error("must not stop"); }};
  other.render(scriptRun());
  other.els.sfinish.listeners[0].fn(ev2);      // any other button of the bar: the page handles it
});
