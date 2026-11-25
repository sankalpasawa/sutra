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
     ResultView.team(html, s, rows)      the page's "How it was made" HTML with finished cards decorated (T3; see team() below)
     ResultView.WORDS                    the wording of a non-page run (no site, page or website)
     ResultView.adopt(root)              on a team page: replaces the page's sViews (tabs Result, Files, How it was made; each file in the viewer
                                         for its type; #rvpane in #sout for text, code, tables and lists, the page's sandboxed frame for pages,
                                         markdown, HTML and images) and its sGo for runs that are not a website. False, and nothing changed,
                                         when a page global it needs is missing. Every replacement falls back to the page's own on a throw.

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
    if (!done(s)) return isPageRun(s) && !(s.docset || []).length && s.versions > 0 ? siteLabel(s) : "result";      // a document set shows no site
    const k = (main && main.kind) || "none";
    if (k === "file") return viewerFor(main.row) === "site" ? siteLabel(s) : base(main.row.file);
    if (k === "real-run") return base(main.result);
    return k === "list" ? "files" : "no files";
  }

  // The plan cards of "How it was made" (the page's sTeamwork HTML), as a string: a part card that is not in progress loses its grey bars;
  // a done one gets its builder's line and its files. Placeholder cards (no data-part) stay. On a run that is not a page run, the
  // "What you got" line for a site goes (and its section when nothing is left in it).
  const SL = '<span class="sl" aria-hidden="true"><i></i><i></i><i></i></span>';
  const unesc = x => x.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  const escape = x => String(x ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  function team(html, s, rows) {
    const parts = ((s && s.studio && s.studio.parts) || []);
    let out = String(html).replace(/(<button type="button" class="spart ([a-z]+)[^"]*" data-part="([^"]*)"[^>]*>)([\s\S]*?)<\/button>/g, (all, open, st, sec, inner) => {
      if (st === "doing" || st === "fix") return all;
      inner = inner.split(SL).join("");
      if (st === "done") {
        const part = parts.find(x => x && x.sec === unesc(sec)) || {sec: unesc(sec), workflows: [unesc(sec)]};
        const files = filesOfPart(part, rows);
        inner += `<small class="rvsum">${escape(summaryOf(s, part))}</small>`
          + (files.length ? `<span class="rvfiles">${files.map(r => `<span class="rvfile" data-view="file:${escape(r.file)}">${escape(base(r.file))}</span>`).join("")}</span>` : "");
      }
      return open + inner + "</button>";
    });
    if (!isPageRun(s)) out = out.replace(/<button type="button" data-view="site">[\s\S]*?<\/button>/g, "")
      .replace(/<section class="stw-sec"><h3>[^<]*<\/h3><div class="sdocs"><\/div><\/section>/g, "");
    return out;
  }

  // ---- the page glue (T2). Runs only on a team page: J2's page globals are read by bare name, typeof guarded.
  const T = {adopted: false, last: null, files: new Map(), runs: [], gkey: ""};
  const NEEDS = ["renderSimple", "sViews", "sLoad", "paint", "sTeamwork", "sSkTime", "sDecorate"];
  const TABS = [["result", "Result"], ["files", "Files"], ["team", "How it was made"]];
  const enc = encodeURIComponent;

  function pageGlobals() {      // the page's own `const`s (not on window): visible by bare name from this classic script
    try {
      return typeof SV === "object" && typeof esc === "function" && typeof runQ === "function" && typeof isReady === "function"
        && typeof sNoun === "function" ? {SV, esc, runQ, isReady, failed: typeof failed === "function" ? failed : () => false} : null;
    } catch (e) { return null; }
  }

  // The file's text from /api/artifact, fetched once per file + sha256; the page is painted again when it arrives.
  function fileText(root, G, row) {
    const k = row.file + "|" + (row.sha256 || ""), hit = T.files.get(k);
    if (hit) return hit;
    const entry = {loading: true};
    T.files.set(k, entry);
    root.fetch(`/api/artifact?name=${enc(row.file)}${G.runQ()}`, {cache: "no-store"})
      .then(r => r.ok ? r.text() : Promise.reject(r.status))
      .then(text => { entry.text = text; }, () => { entry.failed = true; })
      .then(() => { entry.loading = false; if (T.last) root.renderSimple(T.last); });
    return entry;
  }

  // /api/artifacts/groups `real_runs` (main-result step 1), fetched only for a done run whose plan has a real run (P45 hook)
  function realRuns(root, G, s) {
    const k = G.SV.akey || "";
    if (k === T.gkey || !done(s) || !(s.workflows || []).some(w => w && w.real_run)) return T.runs;
    T.gkey = k;
    root.fetch(`/api/artifacts/groups?x=1${G.runQ()}`, {cache: "no-store"}).then(r => r.ok ? r.json() : null).then(g => {
      const runs = ((g && g.groups) || []).flatMap(x => (x.rows || []).flatMap(r => r.real_runs || []));
      if (runs.length) { T.runs = runs; if (T.last) root.renderSimple(T.last); }
    }, () => {});
    return T.runs;
  }

  function dl(G, row) {
    return `<a class="rvdl" href="/api/artifact?name=${enc(row.file)}${G.runQ()}" download="${G.esc(base(row.file))}">${WORDS.download}</a>`;
  }

  function fileList(G, rows) {
    return `<ul class="rvfiles">${rows.map(r => `<li><button type="button" class="slink" data-view="file:${G.esc(r.file)}">${G.esc(r.file)}</button>${dl(G, r)}</li>`).join("")}</ul>`;
  }

  const note = (G, t) => `<p class="rvnote">${G.esc(t)}</p>`;
  const numbered = (G, text) => `<div class="rvcode">${String(text).replace(/\r?\n$/, "").split(/\r?\n/).map(l => `<code>${G.esc(l)}</code>`).join("")}</div>`;
  function tableHTML(G, t) {
    const tr = (cells, tag) => `<tr>${cells.map(c => `<${tag}>${G.esc(c)}</${tag}>`).join("")}</tr>`;
    return `<div class="rvtable"><table><thead>${tr(t.head, "th")}</thead><tbody>${t.rows.map(r => tr(r, "td")).join("")}</tbody></table></div>`
      + (t.total > t.rows.length ? note(G, WORDS.showing(t.rows.length, t.total)) : "");
  }

  // The body of one file in #rvbody (text, code, table, json, download); frame viewers go to the page's sandboxed frame instead.
  function bodyOf(root, G, row, kind) {
    if (kind === "download") return "";
    const f = fileText(root, G, row);
    if (f.loading) return note(G, "Opening…");
    if (f.failed) return note(G, WORDS.cantShow);
    if (kind === "text") return `<pre class="rvtext">${G.esc(f.text)}</pre>`;
    if (kind === "table") { const t = table(f.text, /\.tsv$/i.test(row.file) ? "\t" : ","); return t ? tableHTML(G, t) : numbered(G, f.text); }
    if (kind === "json") {
      const t = jsonTable(f.text); if (t) return tableHTML(G, t);
      try { return numbered(G, JSON.stringify(JSON.parse(f.text), null, 2)); } catch (e) { return numbered(G, f.text); }
    }
    return numbered(G, f.text);
  }

  // What the stage shows for a view: {site}, {frame: url, head}, or {pane: html}. Never a /site/ URL on a non-page run (FR-21).
  function stage(root, G, s, v, rows, main) {
    const head = (row, back) => `<div class="rvhead">${back ? `<button type="button" class="rvback" data-view="files">${WORDS.allFiles}</button>` : ""}<b>${G.esc(row.file)}</b>${dl(G, row)}</div>`;
    const one = (row, back) => {
      const kind = viewerFor(row);
      if (kind === "site") return isPageRun(s) && s.versions > 0 ? {site: true} : {pane: head(row, back) + note(G, WORDS.cantShow)};
      if (kind === "frame") return {frame: `/view?name=${enc(row.file)}${G.runQ()}`, head: head(row, back)};
      return {pane: head(row, back) + (kind === "download" ? note(G, "No preview for this kind of file.") : bodyOf(root, G, row, kind))};
    };
    if (v.startsWith("file:")) return one(rows.find(r => "file:" + r.file === v), true);
    if (v === "files") return {pane: rows.length ? fileList(G, rows) : note(G, WORDS.noFiles)};
    if (isPageRun(s) && !(s.docset || []).length && s.versions > 0) return {site: true};      // a website: its site, live while it builds (Q-2)
    if (!done(s)) return {pane: note(G, WORDS.soon)};
    if (main.kind === "file") return one(main.row, false);
    if (main.kind === "real-run") return {pane: `<div class="rvhead"><b>${G.esc(main.result)}</b></div>` + note(G, WORDS.cantShow)};      // ponytail: P45's route is not built; show its text once it is
    return {pane: main.kind === "list" ? fileList(G, rows) : note(G, WORDS.noFiles)};
  }

  function views(root, G, s, M) {
    const d = root.document, $ = id => d.getElementById(id), SV = G.SV;
    T.last = s;
    const rows = (SV.arts && SV.arts.deliverables) || [], main = mainResult(s, rows, realRuns(root, G, s));
    const pick = SV.pick || "", known = ["result", "files", "team"].includes(pick) || (pick.startsWith("file:") && rows.some(r => "file:" + r.file === pick));
    const v = !pick ? (done(s) ? "result" : "team") : known ? pick : "result";
    const tabOf = v.startsWith("file:") ? "files" : v, running = s.status === "running", web = isPageRun(s) && !(s.docset || []).length && s.versions > 0;
    const pip = k => running && (k === "result" ? web : k === "team" && !web) ? '<span class="pip" aria-hidden="true"></span>' : "";
    root.paint($("sviews"), TABS.map(([k, l]) => `<button type="button" role="tab" data-view="${k}" aria-selected="${k === tabOf}">${l}${pip(k)}</button>`).join(""));
    if (isPageRun(s) && typeof root.sTabs === "function") {      // a page run's own toasts, as the page draws them; none on other runs
      const outs = root.sTabs(s).filter(t => t.k !== "team"), last = outs[outs.length - 1];
      if (last && SV.lastOut !== last.k && SV.view && !SV.pick && running && typeof root.sToast === "function")
        root.sToast(last.k === "site" ? `The ${typeof TYL === "function" ? TYL("site", "page").toLowerCase() : "page"} is taking shape` : `The ${last.label} is being written`);
      SV.lastOut = last ? last.k : "";
    } else SV.lastOut = "";
    const team = v === "team", show = team ? {} : stage(root, G, s, v, rows, main), box = $("sframebox").classList, pane = $("rvpane");
    SV.view = team ? "team" : show.site ? "site" : v;      // "site" keeps the page's sGo and sDecorate working on a website
    box.toggle("team", team); box.toggle("site", !!show.site); box.toggle("live", running);
    box.toggle("rvpane", !!show.pane); box.toggle("rvbar", !!show.frame);
    $("steamwork").hidden = !team;
    pane.hidden = !(show.pane || show.frame); pane.classList.toggle("rvbar", !!show.frame);
    root.paint($("rvbody"), show.pane || show.head || "");
    const url = label(s, v, main);
    if ($("surl").__t !== url) { $("surl").__t = url; $("surl").innerHTML = `<span>${G.esc(url)}</span>`; }
    if (team) { root.paint($("steamwork"), root.sTeamwork(s, M)); root.sSkTime($("steamwork")); }
    else if (show.site) root.sLoad(`/site/v${s.versions}?x=1${G.runQ()}`);
    else if (show.frame) root.sLoad(show.frame);
    root.sDecorate();
  }

  // The finish bar of a run that is not a page run (T4): the page's message, then the main file's Download, or "All files (N)" when
  // Result is the Files list; Copy share link only with a main file (Q-4: a list, no files or a real-run result has no /view link).
  // Same markup and icons as the page's own sFinish (j2_ui.html).
  const ic = d => `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  function finish(root, G, s) {
    const rows = (G.SV.arts && G.SV.arts.deliverables) || [], main = mainResult(s, rows, T.runs);
    const dlink = main.kind === "file" ? `<a class="pri" href="/api/artifact?name=${enc(main.row.file)}${G.runQ()}" download="${G.esc(base(main.row.file))}">${ic('<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>')}${WORDS.download}</a>`
      : main.kind === "list" ? `<button type="button" data-view="files">${WORDS.allFiles} (${rows.length})</button>` : "";
    return `<span class="sfmsg"><span><i aria-hidden="true">✓</i>${G.esc(root.sPhase(s, []))}</span></span>${dlink}`
      + (main.kind === "file" ? `<button type="button" data-share>${ic('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>')}${WORDS.share}</button>` : "")
      + `<button type="button" data-full>${ic('<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>')}Open full view</button>`;
  }

  // Copy share link, every run (FR-19): a page run copies the page's own URL, any other run its main file's /view link; then the note.
  function share(root, G, e) {
    const b = e.target && e.target.closest && e.target.closest("[data-share]");
    if (!b) return;
    e.stopImmediatePropagation();      // the page's own listener (anonymous, on the same element) never runs for this button
    const s = T.last || {}, rows = (G.SV.arts && G.SV.arts.deliverables) || [], main = mainResult(s, rows, T.runs), o = root.location.origin;
    const url = !isPageRun(s) && main.kind === "file" ? `${o}/view?name=${enc(main.row.file)}${G.runQ()}` : `${o}/site/latest${G.runQ().replace("&", "?")}`;
    Promise.resolve().then(() => root.navigator.clipboard.writeText(url))
      .then(() => { b.textContent = WORDS.copied; }, () => { b.textContent = url; })
      .then(() => root.setTimeout(() => { b.textContent = WORDS.share; }, 2500));
  }

  function adopt(root) {
    const d = root && root.document, G = pageGlobals();
    if (T.adopted || !d || !G || NEEDS.some(n => typeof root[n] !== "function")) return false;
    const out = d.getElementById("sout");
    if (!out) return false;
    const pane = d.createElement("div"), body = d.createElement("div"), later = d.createElement("div");
    pane.id = "rvpane"; pane.className = "rvpane"; pane.hidden = true; body.id = "rvbody"; later.id = "rvlater";      // #rvlater: the Later items' slot
    pane.appendChild(body); pane.appendChild(later); out.appendChild(pane);
    if (d.head && !d.querySelector('link[href$="/ui/css/result_view.css"]')) {
      const link = d.createElement("link"); link.rel = "stylesheet"; link.href = "/ui/css/result_view.css"; d.head.appendChild(link);
    }
    const orig = root.sViews;
    root.sViews = function (s, M, ready) {
      try { return views(root, G, s, M); } catch (e) { return orig.apply(this, arguments); }      // NFR-7: the page's own on a throw
    };
    if (typeof root.sGo === "function" && typeof root.sOpenPart === "function") {
      const go = root.sGo;      // the page's sGo looks for a J2 tab per document; with three tabs only a website's site is one
      root.sGo = function (sec) {
        const s = T.last;
        if (!s || (isPageRun(s) && !(s.docset || []).length)) return go.apply(this, arguments);
        return root.sOpenPart(sec);
      };
    }
    const wrap = (name, after) => {      // the page's own function first; ours only adjusts its result, and never breaks it (NFR-7)
      const fn = root[name];
      if (typeof fn !== "function") return;
      root[name] = function () {
        const out = fn.apply(this, arguments);
        try { return after(out, arguments); } catch (e) { return out; }
      };
    };
    wrap("sTeamwork", (html, [s]) => team(html, s, (G.SV.arts && G.SV.arts.deliverables) || []));
    wrap("sPhase", (text, [s]) => !isPageRun(s) && text === "Checking it on a phone and a laptop" ? WORDS.checking : text);
    wrap("sOpenPart", (p) => Promise.resolve(p).then(r => {
      const b = d.getElementById("sdbody");
      if (T.last && !isPageRun(T.last) && b && b.innerHTML.includes("The part, on the page.")) b.innerHTML = b.innerHTML.split("The part, on the page.").join(WORDS.partDrawer);
      return r;
    }));
    const fin = d.getElementById("sfinish");
    if (typeof root.sFinish === "function" && fin) {
      const pageFinish = root.sFinish;
      root.sFinish = function (s) {
        if (isPageRun(s)) return pageFinish.apply(this, arguments);      // a website or a document set: the page's own, byte for byte
        try { return finish(root, G, s); } catch (e) { return pageFinish.apply(this, arguments); }
      };
      fin.addEventListener("click", e => { try { share(root, G, e); } catch (err) {} }, true);
    }
    wrap("renderSimple", (out, [s]) => {
      const open = d.getElementById("sopen");
      if (open && s && !isPageRun(s)) { open.hidden = true; open.setAttribute("href", "#"); }      // "Open the site" (/site/latest): the finish bar and Result cover it
      // the page draws the finish bar once, when the run turns ready; /api/artifacts comes later, so draw it again when it changes
      if (fin && s && !isPageRun(s) && G.isReady(s) && !G.failed(s)) {
        const html = root.sFinish(s);
        if (html !== T.finish) { T.finish = html; fin.innerHTML = html; }
      }
      return out;
    });
    T.adopted = true;
    return true;
  }

  const ResultView = {MAX_ROWS, WORDS, isPageRun, done, realRun, named, mainResult, viewerFor, summaryOf, filesOfPart, table, jsonTable, label,
    team, adopt};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ResultView;
  else { root.ResultView = ResultView; adopt(root); }
})(globalThis);
