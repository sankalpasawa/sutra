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
  // real_run.result names report.txt: it is a path in the user's folder, never matched against the outputs
  const rr = noEntry({workflows: [{id: "W-2", real_run: {result: "report.txt"}}]});
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

test("the real-run step reads the last workflow naming a result and that workflow's last receipt row, strict link form only", () => {
  const wfs = [{id: "W-1", real_run: {result: "a.txt"}}, {id: "W-2", real_run: {result: "b.txt"}}, {id: "W-3", real_run: {command: ["x"]}}];
  const s = st({workflows: wfs});
  assert.deepEqual(RV.realRun(s, [{workflow: "W-1", run_output: "run_output/R-1.json"}]), null, "W-1 is not the last naming a result");
  assert.deepEqual(RV.realRun(s, [{workflow: "W-2", run_output: "run_output/R-2.json"}, {workflow: "W-2", output: "tail"}]), null, "last row wins");
  assert.deepEqual(RV.realRun(s, [{workflow: "W-2", output: "tail"}, {workflow: "W-2", output: "tail", run_output: "run_output/R-3.json"}]),
    {workflow: "W-2", result: "b.txt", link: "run_output/R-3.json"});
  for (const bad of ["run_output/../x.json", "run_output/a/b.json", "x/run_output/R.json", "run_output/R.json\nmore", "run_output/.json",
    "run_output/R.txt", " run_output/R.json", "...run_output/R-1.json", 7, null]) {
    assert.equal(RV.realRun(s, [{workflow: "W-2", run_output: bad}]), null, String(bad));
  }
  assert.equal(RV.realRun(s, [{workflow: "W-2", output: "run_output/R-4.json"}]), null, "`output` is never read as a link");
  assert.equal(RV.realRun(st({workflows: [{id: "W-2", real_run: {result: ""}}]}), RUNS.p45), null);
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
