/* result_view.js - the centre panel of a team page for any output, not only websites (SUT-27, D450).

   Pure core (this file, T1): no DOM, strings and plain objects in and out.

     ResultView.isPageRun(s)             a docset run, or one whose output type has form "page": the page's own wording and finish bar stay
     ResultView.done(s)                  the page's isReady (Done, not paused, not running), or a saved run
     ResultView.realRun(s, runs)         main-result step 1, from the real_run receipt rows (/api/artifacts/groups `real_runs`): each
                                         workflow's last row, in plan order; the last of them with a `run_output` link (`run_output/<id>.json`)
                                         and a non-empty `result` (a path in the user's folder, resolved by the engine, never one of the run's
                                         outputs) gives {workflow, result, link}; else null. P45, not built yet. Only those two keys of the row
                                         are read: never `output` (the stdout+stderr tail), `dry_run.*` or `expect`.
     ResultView.named(s)                 main-result step 2: the output type's entry file (`entry_file`, else `file`) when it is one concrete
                                         file, not a glob such as `<name>/*`; else ""
     ResultView.mainResult(s, rows, runs)  {kind: "real-run", workflow, result, link} | {kind: "file", row} | {kind: "list"} | {kind: "none"}.
                                         Real-run result, then the entry file among the rows, then the only row, then the Files list.
                                         Never a guess from a file name or extension.
     ResultView.viewerFor(row)           "site" | "frame" | "text" | "code" | "table" | "json" | "download", from the row's form and extension
     ResultView.summaryOf(s, part)       the last chat message of the part's workflows: its human_output, a leading @name removed, first
                                         sentence; "Finished." when there is none
     ResultView.filesOfPart(part, rows)  the output rows that share a workflow with the part
     ResultView.table(text, sep)         CSV / TSV: {head, rows, total}, rows capped at 1,000; null when it does not parse
     ResultView.jsonTable(text)          the same for a JSON array of objects; null otherwise
     ResultView.label(s, tab, main)      the address bar text for a tab ("result", "files", "team", "file:<path>")
     ResultView.WORDS                    the wording of a non-page run (no site, page or website)
     ResultView.adopt(root)              installs the page wrappers (T2); a stub returning false for now

   A classic script with ONE global, ResultView; in node it is module.exports. */
(function (root) {
  "use strict";

  const MAX_ROWS = 1000;
  const LINK = /^run_output\/\w[\w.-]*\.json$/;      // P45's link, the receipt row's `run_output` key (never `output`, a stdout tail)
  const FRAME = new Set(["html", "htm", "md", "png", "jpg", "jpeg", "gif", "webp", "svg"]);
  const TEXT = new Set(["txt", "log"]);
  const CODE = new Set(["py", "js", "mjs", "ts", "tsx", "jsx", "sh", "rb", "go", "rs", "java", "c", "h", "cpp", "css", "sql", "yaml", "yml",
    "toml", "ini"]);
  const WORDS = {
    soon: "Your result will appear here when the team finishes.",
    noFiles: "This run produced no files.",
    cantShow: "This file can't be shown here (it may be over 2 MB).",
    checking: "Checking the work",
    partDrawer: "The part, in the result.",
    finished: "Finished.",
    download: "Download",
    allFiles: "All files",
    share: "Copy share link",
    copied: "Link copied — opens on this computer only",
    showing: (n, total) => `Showing ${n.toLocaleString("en-US")} of ${total.toLocaleString("en-US")} rows`,
  };

  const str = x => typeof x === "string" && x ? x : "";
  const base = f => str(f).split("/").pop();

  const isPageRun = s => ((s && s.docset) || []).length > 0 || (((s && s.types) || {})[s && s.output] || {}).form === "page";
  const done = s => !!s && ((/^Done/.test(s.outcome || "") && !s.paused && s.status !== "running") || !!s.saved);

  function realRun(s, runs) {
    const last = ((s && s.workflows) || []).map(w => w && (runs || []).filter(r => r && r.workflow === w.id).pop())
      .filter(r => r && LINK.test(str(r.run_output)) && str(r.result)).pop();
    return last ? {workflow: last.workflow, result: last.result, link: last.run_output} : null;
  }

  function named(s) {
    const t = ((s && s.types) || {})[s && s.output] || {}, entry = str(t.entry_file) || str(t.file);
    return entry.includes("*") ? "" : entry;
  }

  function mainResult(s, rows, runs) {
    rows = rows || [];
    const rr = realRun(s, runs);
    if (rr) return {kind: "real-run", ...rr};
    const entry = named(s), hit = entry && rows.find(r => r.file === entry);
    if (hit) return {kind: "file", row: hit};
    if (rows.length === 1) return {kind: "file", row: rows[0]};
    return rows.length ? {kind: "list"} : {kind: "none"};
  }

  function viewerFor(row) {
    if (row && row.form === "page") return "site";
    const m = /\.([a-z0-9]+)$/.exec(base(row && row.file).toLowerCase()), ext = m ? m[1] : "";
    return FRAME.has(ext) ? "frame" : TEXT.has(ext) ? "text" : CODE.has(ext) ? "code" : ext === "csv" || ext === "tsv" ? "table"
      : ext === "json" ? "json" : "download";
  }

  function summaryOf(s, part) {
    const wfs = (part && part.workflows) || [];
    const msgs = (s && (s.allChat || s.chat)) || [];
    const m = msgs.filter(x => x && wfs.includes(x.who) && str(x.human_output)).pop();
    const text = m ? m.human_output.replace(/^\s*@\S+\s*/, "").trim() : "";
    const first = /^[\s\S]*?[.!?](?=\s|$)/.exec(text);
    return (first ? first[0] : text).trim() || WORDS.finished;
  }

  const filesOfPart = (part, rows) => {
    const wfs = (part && part.workflows) || [];
    return (rows || []).filter(r => (r.workflows || []).some(w => wfs.includes(w)));
  };

  // RFC 4180-ish: quoted fields may hold the separator, newlines and doubled quotes. An unterminated quote means it is not a table.
  function table(text, sep) {
    sep = sep || ",";
    const out = [];
    let rowv = [], field = "", q = false, i = 0;
    text = String(text || "");
    for (; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (c === '"') q = false;
        else field += c;
      } else if (c === '"' && field === "") q = true;
      else if (c === sep) { rowv.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        rowv.push(field); out.push(rowv); rowv = []; field = "";
      } else field += c;
    }
    if (q) return null;
    if (field !== "" || rowv.length) { rowv.push(field); out.push(rowv); }
    const rows = out.filter(r => !(r.length === 1 && r[0] === ""));      // blank lines
    if (!rows.length) return null;
    return {head: rows[0], rows: rows.slice(1, 1 + MAX_ROWS), total: rows.length - 1};
  }

  function jsonTable(text) {
    let v;
    try { v = JSON.parse(text); } catch (e) { return null; }
    if (!Array.isArray(v) || !v.length || !v.every(o => o && typeof o === "object" && !Array.isArray(o))) return null;
    const head = [...new Set(v.flatMap(o => Object.keys(o)))];
    const cell = x => x === null || x === undefined ? "" : typeof x === "object" ? JSON.stringify(x) : String(x);
    return {head, rows: v.slice(0, MAX_ROWS).map(o => head.map(k => cell(o[k]))), total: v.length};
  }

  // The page's own site label (j2_ui.html sViews), kept word for word on a page run.
  function siteLabel(s) {
    const host = s.goal && s.goal.site_name ? String(s.goal.site_name).toLowerCase().replace(/[^a-z0-9]+/g, "") : "";
    return `${host ? host + " · " : ""}${s.status === "running" ? "live preview" : "preview"}`;
  }

  function label(s, tab, main) {
    s = s || {};
    if (tab === "team") return done(s) ? "how your project was made" : "your team, live";
    if (tab === "files") return "files";
    if (str(tab).startsWith("file:")) return base(tab.slice(5));
    if (!done(s)) return isPageRun(s) && s.versions > 0 ? siteLabel(s) : "result";
    const k = (main && main.kind) || "none";
    if (k === "file") return viewerFor(main.row) === "site" ? siteLabel(s) : base(main.row.file);
    if (k === "real-run") return base(main.result);
    return k === "list" ? "files" : "no files";
  }

  const adopt = () => false;      // T2 installs the page wrappers

  const ResultView = {MAX_ROWS, WORDS, isPageRun, done, realRun, named, mainResult, viewerFor, summaryOf, filesOfPart, table, jsonTable, label,
    adopt};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ResultView;
  else root.ResultView = ResultView;
})(globalThis);
