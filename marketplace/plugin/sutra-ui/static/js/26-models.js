/* 26-models.js -- the Models editor on Root's pane (amendment A4, A4.6; screens S19 to S26).
   The shapes the owner's records and templates have: a list, a page for each model, the sheets that make and change one, the
   structure and the history. Sutra-only, in the app's own style (S16 and S18 are its neighbours): dpCard, wbBtn, wbEsc, tokens
   only in panel.css. It reads and writes /api/native/_models and nothing else; the J2 page is not touched.

   The owner is the actor here, so the screen acts directly and says so afterwards, with an undo. A change that lets in more waits
   for the owner's stamp (A4.6.3): the sheet says so before Save, and the amber row on the list and the page carries Stamp and No.
   Every owner word (a label, a field, a choice) is printed as text, never as markup. No count at rest; names, never paths.
   Every global of this file is prefixed mdl / MDL_. */

const MDL_API = "/api/native/_models";
const MDL_PAUSE = 300;                                   /* the live line asks after this pause, never for each key */
const MDL_STATE = { on: ["On", "\u2713"], off: ["Off", "\u25CB"], needs_a_look: ["Needs a look", "!"] };
const MDL_CLASS = { tightens: "Tightens", same: "No change", widens: "Lets in more", mixed: "Lets in more" };
const MDL_TYPES = [["text", "text"], ["long_text", "long text"], ["whole", "whole number"], ["number", "number"], ["yesno", "yes or no"],
  ["choice", "one of"], ["words", "list of words"], ["date", "date"]];
const MDL_PATTERNS = [["", "none"], ["slug", "slug"], ["code", "code"], ["date", "date"]];
const MDL_NESTABLE = [["core:envelope", "Envelope"], ["core:identity.done_item", "Done item"], ["core:option", "Option"]];
const MDL_TWELVE = 12;

let _mdl = null;
function mdlState(){
  if (!_mdl) _mdl = { list: null, listErr: false, rev: -1, pages: {}, pageErr: {}, graph: null, graphErr: false, history: {}, historyErr: false,
    shapes: {}, view: "list", key: null, tab: "structure", sheet: null, stale: false, all: false, busy: {}, timer: null,
    filter: "", said: "", listSig: "" };
  return _mdl;
}
function mdlReset(){ _mdl = null; }
function mdlEsc(x){ return (typeof wbEsc === "function") ? wbEsc(x) : dpEsc(x); }
function mdlBtn(label, attrs, cls){ return `<button type="button" class="btn wb${cls ? " " + cls : ""}" ${attrs}>${mdlEsc(label)}</button>`; }
function mdlClone(x){ return JSON.parse(JSON.stringify(x)); }
function mdlWhen(at){ const m = /T(\d\d:\d\d)/.exec(String(at || "")); return m ? m[1] : ""; }
function mdlQuiet(line){ return `<div class="o2quiet dpq">${mdlEsc(line)}</div>`; }
function mdlSayRead(what){ return `<div class="mdlerr" role="alert">Could not read ${mdlEsc(what)} · ` + mdlBtn("Try again", `data-mdl="retry"`, "mdllink") + `</div>`; }
function mdlKeyOf(label){
  const k = String(label || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return /^[a-z][a-z0-9_]{1,30}$/.test(k) ? k : "";
}
/* the sentences a refused write carries ({"detail": {"code", "faults": [...]}}); never the path the error also names */
function mdlFaults(e){
  const generic = "That did not work · Try again";
  const m = String((e && e.message) || "").replace(/\s*\(\S+ -> \d+\)\s*$/, "");
  try {
    const j = JSON.parse(m);
    if (j && Array.isArray(j.faults) && j.faults.length) return j.faults.map(String);
    if (j && typeof j.detail === "string") return [j.detail];
  } catch (x) {}
  return [m && !/->|^[\/{\[]/.test(m) && m.length < 240 ? m : generic];
}
function mdlOwnEntries(){ const L = mdlState().list; return (L && L.yours) || []; }
function mdlEntry(key){ return mdlOwnEntries().filter(e => e.key === key)[0] || null; }
function mdlNameOfBase(base){ const m = /^x:([a-z0-9_]+)/.exec(String(base || "")); return m ? m[1] : ""; }
function mdlPendingList(){ return mdlOwnEntries().filter(e => e.pending); }
function mdlPaneOpen(){
  if (typeof wbS !== "function") return false;
  const t = wbS().tab || {};
  return Object.keys(t).some(k => t[k] === "models");
}

/* ── loaders: one fetch for each read, an error is a quiet line and a way to try again ─────────────────────────────────── */
async function mdlLoad(force){
  const st = mdlState();
  if (st.busy.list || (st.list && !force)) return;
  st.busy.list = true;
  try {
    st.list = await apiGet(MDL_API + (st.all ? "?all=1" : ""));
    st.listErr = false; st.rev = st.list.rev; st.stale = false;
  } catch (e) { st.listErr = true; }
  st.busy.list = false;
  mdlRender();
}
async function mdlLoadPage(key, force){
  const st = mdlState();
  if (!key || st.busy["p:" + key] || (st.pages[key] && !force)) return;
  st.busy["p:" + key] = true;
  try { st.pages[key] = await apiGet(MDL_API + "/" + encodeURIComponent(key)); delete st.pageErr[key]; }
  catch (e) { st.pageErr[key] = mdlFaults(e)[0]; }
  st.busy["p:" + key] = false;
  mdlRender();
}
async function mdlLoadGraph(force){
  const st = mdlState();
  if (st.busy.graph || (st.graph && !force)) return;
  st.busy.graph = true;
  try { st.graph = await apiGet(MDL_API + "/graph"); st.graphErr = false; } catch (e) { st.graphErr = true; }
  st.busy.graph = false;
  mdlRender();
}
async function mdlLoadHistory(force){
  const st = mdlState();
  if (st.busy.history || (st.historyLoaded && !force)) return;
  st.busy.history = true;
  const keys = st.key ? [st.key] : mdlOwnEntries().map(e => e.key);
  try {
    const got = await Promise.all(keys.map(k => apiGet(MDL_API + "/" + encodeURIComponent(k) + "/history")));
    keys.forEach((k, i) => { st.history[k] = (got[i] && got[i].history) || []; });
    st.historyErr = false; st.historyLoaded = true;
  } catch (e) { st.historyErr = true; }
  st.busy.history = false;
  mdlRender();
}
async function mdlShapeOf(key){
  const st = mdlState();
  if (st.shapes[key]) return st.shapes[key];
  try { st.shapes[key] = await apiGet(MDL_API + "/" + encodeURIComponent(key) + "/shape"); } catch (e) { return { failed: mdlFaults(e)[0] }; }
  return st.shapes[key];
}
function mdlRender(){
  if (typeof dpRender === "function") dpRender();
  mdlPaintSheet();
}

/* ── the card on Root's pane (A4.6.1) ───────────────────────────────────────────────────────────────────────────────────── */
function mdlCardHtml(){
  const st = mdlState(), L = st.list;
  if (!L && !st.listErr && !st.busy.list) mdlLoad();
  let body;
  if (st.listErr) body = mdlSayRead("your models");
  else if (!L) body = dpSkel();
  else {
    const names = (L.yours || []).map(e => e.label);
    body = mdlQuiet("The shapes your records and templates have.") +
      `<div class="dpfline">${names.length ? "Yours: " + names.map(mdlEsc).join(", ") + "." : "You have not made a model yet."}</div>` +
      mdlPendingList().map(e => `<div class="mdlnote"><i class="mdlq" aria-hidden="true">?</i><span>${mdlEsc(e.label)}: a change waits for your stamp</span></div>`).join("");
  }
  return dpCard("Models", body + `<div class="dpoffer">${mdlBtn("Open models", `data-wbtab="models"`)}</div>`);
}

/* ── the pane ───────────────────────────────────────────────────────────────────────────────────────────────────────────── */
function mdlPaneHtml(){
  const st = mdlState();
  const where = st.view === "page" ? "Models · " + ((mdlEntry(st.key) || (st.pages[st.key] || {})).label || "") : st.view === "structure" ? "Models · Structure and history" : "Models";
  const back = st.view === "list" ? mdlBtn("Back to Root", `data-wbtab="root"`) : mdlBtn("Back to models", `data-mdl="back"`);
  const stale = st.stale ? `<button type="button" class="mdlstale" data-mdl="reload">Models changed · Reload</button>` : "";
  const said = st.said ? `<div class="mdlsaid" role="status">${mdlEsc(st.said)}</div>` : "";
  const body = st.view === "page" ? mdlPageHtml(st.key) : st.view === "structure" ? mdlStructureHtml() : mdlListHtml();
  return `<div class="mdlpane"><div class="mdlhead"><b>Root · ${mdlEsc(where)}</b>${back}</div>${stale}${said}${body}</div>`;
}

/* ── S19 the list ───────────────────────────────────────────────────────────────────────────────────────────────────────── */
function mdlStateHtml(state){
  const w = MDL_STATE[state] || MDL_STATE.on;
  return `<span class="mdlstate ${state === "needs_a_look" ? "look" : state === "off" ? "off" : "on"}"><i class="mdlg" aria-hidden="true">${w[1]}</i>${w[0]}</span>`;
}
function mdlLock(){ return `<span class="mdllock"><i class="mdlpad" aria-hidden="true"></i>Built in</span>`; }
function mdlPendingRow(e){
  const p = e.pending;
  return `<div class="mdlnote"><i class="mdlq" aria-hidden="true">?</i><span>${mdlEsc(e.label)}: ${mdlEsc(p.says)} · waits for your stamp${p.at ? " · " + mdlEsc(mdlWhen(p.at)) : ""}</span>` +
    mdlBtn("Stamp", `data-mdl="stamp" data-mdl-id="${mdlEsc(p.id)}"`, "dpstamp") + mdlBtn("No", `data-mdl="no" data-mdl-id="${mdlEsc(p.id)}"`) + `</div>`;
}
function mdlRowHtml(e, depth){
  return `<div class="mdlrow${depth ? " mdlsub" : ""}"><span class="mdlname">${mdlEsc(e.label)}</span>` +
    `<span class="mdlkind">a kind of ${mdlEsc(e.base_label)}</span>${mdlStateHtml(e.state)}${mdlBtn("Open", `data-mdl="open" data-mdl-key="${mdlEsc(e.key)}"`)}</div>` +
    (e.state === "needs_a_look" && e.why ? `<div class="mdlwhy">${mdlEsc(e.why)}</div>` : "");
}
function mdlRowsTree(entries){
  const have = {};
  entries.forEach(e => { have[e.key] = e; });
  const out = [];
  const walk = (e, depth, seen) => {
    out.push(mdlRowHtml(e, depth));
    entries.filter(c => "x." + mdlNameOfBase(c.base) === e.key && !seen[c.key]).forEach(c => { seen[c.key] = 1; walk(c, depth + 1, seen); });
  };
  const seen = {};
  entries.filter(e => !have["x." + mdlNameOfBase(e.base)] || "x." + mdlNameOfBase(e.base) === e.key).forEach(e => { seen[e.key] = 1; walk(e, 0, seen); });
  return out.join("");
}
function mdlListHtml(){
  const st = mdlState(), L = st.list;
  if (st.listErr) return mdlSayRead("your models");
  if (!L){ mdlLoad(); return dpSkel(); }
  const yours = L.yours || [];
  const add = mdlBtn("Add a model", `data-mdl="add"`, "dpstamp");
  const mine = yours.length
    ? mdlRowsTree(yours) + mdlPendingList().map(mdlPendingRow).join("") + `<div class="dpoffer">${add}</div>`
    : mdlQuiet("You have not made a model yet.") + `<div class="dpoffer">${add}</div>`;
  const builtin = (L.buildable || []).filter(b => /^core:/.test(b.key)).map(b =>
    `<div class="mdlrow">${mdlLock()}<span class="mdlname">${mdlEsc(b.label)}</span><span class="mdlkind">${mdlEsc(b.says)}</span>` +
    mdlBtn("Open", `data-mdl="open" data-mdl-key="${mdlEsc(b.key)}"`) + `</div>`).join("");
  const all = st.all && L.built_in
    ? dpCard("Everything built in", L.built_in.map(g => `<div class="mdlgroup"><b>${mdlEsc(g.layer)}</b><span>${g.models.map(m => mdlEsc(m.label)).join(", ")}</span></div>`).join(""))
    : "";
  return mdlQuiet("What your records and templates are shaped like. Built-in models are part of how the app is built; you can build your own on the ones marked \"can be built on\".") +
    dpCard("Yours", mine) + dpCard("Built in, can be built on", builtin) + all +
    `<div class="dpoffer">${st.all ? "" : mdlBtn("Show everything built in", `data-mdl="all"`)}${mdlBtn("Structure and history", `data-mdl="structure"`)}</div>`;
}

/* ── S20 a model's page ─────────────────────────────────────────────────────────────────────────────────────────────────── */
function mdlPageOf(key){
  const st = mdlState();
  if (st.pages[key]) return st.pages[key];
  const L = st.list || {};
  const b = (L.buildable || []).filter(x => x.key === key)[0];
  if (b && /^core:/.test(key) && st.pageErr[key]) return { core: true, key, label: b.label, says: b.says, extensible: true, fields: [], children: [] };
  if (/^core:/.test(key) && st.pageErr[key]) return { core: true, key, label: key.replace(/^core:/, ""), says: "", extensible: false, fields: [], children: [] };
  return null;
}
function mdlBoundWords(f){
  return `${mdlEsc(f.type)}${f.says ? ", " + mdlEsc(f.says) : ""}${f.required ? ", required" : ""}`;
}
function mdlFieldRow(f, page, writable){
  const was = (f.aliases || []).length ? ` (was: ${f.aliases.map(mdlEsc).join(", ")})` : "";
  const btns = !f.locked && writable && !f.retired
    ? mdlBtn("Change", `data-mdl="field" data-mdl-name="${mdlEsc(f.name)}"`) + mdlBtn("Rename", `data-mdl="rename" data-mdl-name="${mdlEsc(f.name)}"`) +
      mdlBtn("Retire", `data-mdl="retire" data-mdl-name="${mdlEsc(f.name)}"`) : "";
  return `<div class="mdlfield${f.retired ? " mdlret" : ""}"><span class="mdlfn">${f.locked ? `<i class="mdlpad" aria-hidden="true"></i>` : ""}${mdlEsc(f.name)}</span>` +
    `<span class="mdlft">${mdlBoundWords(f)}${was}</span>${f.retired ? `<span class="mdlstate off"><i class="mdlg" aria-hidden="true">\u25CB</i>Retired</span>` : ""}` +
    `${f.locked ? `<span class="mdlfrom">from ${mdlEsc(f.from)}</span>` : ""}<span class="mdlfb">${btns}</span></div>`;
}
function mdlLinkWords(l){
  return `${mdlEsc(l.to_label)} (${l.mode === "nest" ? "held inside" : "by its id"}${l.many ? ", many" : ""}${l.required ? ", required" : ""})`;
}
function mdlUsedWords(u){
  return u.kind === "artifact_template" ? `${mdlEsc(u.name)} (artifact template)` : `${mdlEsc(u.name)}${u.v ? " v" + mdlEsc(u.v) : ""}${u.dept ? " · " + mdlEsc(u.dept) : ""}`;
}
function mdlPageHtml(key){
  const st = mdlState(), p = mdlPageOf(key);
  if (!p){
    if (st.pageErr[key]) return mdlSayRead("this model");
    mdlLoadPage(key);
    return dpSkel();
  }
  if (p.core) return mdlBuiltInPage(p);
  const off = p.state === "off", look = p.state === "needs_a_look";
  const chain = (p.chain || []).map(lbl => {
    const e = mdlOwnEntries().filter(x => x.label === lbl)[0];
    return e ? `<button type="button" class="mdllink btn wb" data-mdl="open" data-mdl-key="${mdlEsc(e.key)}">${mdlEsc(lbl)}</button>` : mdlEsc(lbl);
  });
  const head = `<div class="mdlsub2"><span>a kind of ${chain.join(", ") || mdlEsc(p.base_label)}</span><span>version ${mdlEsc(p.version)}</span>${mdlStateHtml(p.state)}</div>`;
  const acts = `<div class="mdlacts">${mdlBtn("Undo last change", `data-mdl="undo"`)}${mdlBtn(off ? "Turn on" : "Turn off", `data-mdl="onoff"`)}</div>`;
  const banner = off ? mdlQuiet("Off. Nothing new is offered. What is stored stays.") : "";
  const needs = look ? `<div class="mdlwhy">${mdlEsc(p.why || (p.faults || [])[0] || "")}</div>` + mdlBtn("Fit it to its base", `data-mdl="fit"`) : "";
  const stamp = p.pending ? mdlPendingRow(Object.assign({}, p, { pending: p.pending })) : "";
  const fields = (p.fields || []);
  const own = fields.filter(f => !f.locked), inh = fields.filter(f => f.locked);
  const fcard = dpCard("Fields", inh.concat(own).map(f => mdlFieldRow(f, p, true)).join("") +
    `<div class="dpoffer">${mdlBtn("Add a field", `data-mdl="field"`)}</div>`);
  const lk = p.links || { out: [], in: [] };
  const lcard = dpCard("Links", `<div class="dpfline">Points out: ${lk.out.length ? lk.out.map(mdlLinkWords).join(" · ") : "nothing yet"}</div>` +
    `<div class="dpfline">Pointed at by: ${lk.in.length ? lk.in.map(i => mdlEsc(i.from_label) + (i.mode === "nest" ? " (holds it)" : " (by its id)")).join(" · ") : "nothing yet"}</div>` +
    `<div class="dpoffer">${mdlBtn("Link or nest", `data-mdl="link"`)}</div>`);
  const kids = (p.children || []).map(k => { const e = mdlEntry(k); return e ? `<div class="dpfline">${mdlBtn(e.label, `data-mdl="open" data-mdl-key="${mdlEsc(e.key)}"`, "mdllink")}</div>` : ""; }).join("");
  const used = (p.used_by || []).map(u => `<div class="dpfline">${mdlUsedWords(u)}</div>`).join("");
  return head + acts + banner + needs + stamp + fcard + lcard +
    `<div class="wbpair">${dpCard("Built on it", kids || mdlQuiet("Nothing yet"))}${dpCard("Where it is used", used || mdlQuiet("Nowhere yet"))}</div>` +
    `<div class="mdlacts">${mdlBtn("Try a sample", `data-mdl="try"`)}${mdlBtn("See its shape", `data-mdl="shape"`)}${mdlBtn("New version", `data-mdl="newversion"`)}` +
    `${mdlBtn("History", `data-mdl="history"`)}</div>`;
}
function mdlBuiltInPage(p){
  return `<div class="mdlsub2">${mdlLock()}<span>${mdlEsc(p.label)}</span></div>` + mdlQuiet("Part of the app: you can look, not change.") +
    (p.says ? `<div class="dpfline">${mdlEsc(p.says)}</div>` : "") +
    `<div class="mdlacts">${mdlBtn("Try a sample", `data-mdl="try"`)}${mdlBtn("See its shape", `data-mdl="shape"`)}` +
    (p.extensible ? mdlBtn("Build on it", `data-mdl="add" data-mdl-key="${mdlEsc(p.key)}"`) : "") + `</div>`;
}

/* ── the spec of a model as the page knows it ────────────────────────────────────────────────────────────────────────── */
/* A change posts the whole spec. The page may carry it whole (`spec`); when it carries the fields only, the constraints come
   back from the owner's words for them, and anything those words do not say is left out. */
function mdlTypeKey(word){ const t = MDL_TYPES.filter(x => x[1] === word)[0]; return t ? t[0] : "text"; }
function mdlParseSays(type, says){
  const s = String(says || ""), o = {};
  let m;
  if (type === "text" || type === "long_text"){
    if ((m = /up to (\d+) characters/.exec(s))) o.max_len = Number(m[1]);
    if ((m = /at least (\d+)/.exec(s))) o.min_len = Number(m[1]);
  } else if (type === "whole" || type === "number"){
    if ((m = /^between (-?[\d.]+) and (-?[\d.]+)$/.exec(s))){ o.minimum = Number(m[1]); o.maximum = Number(m[2]); }
    else if ((m = /^from (-?[\d.]+)$/.exec(s))) o.minimum = Number(m[1]);
    else if ((m = /^up to (-?[\d.]+)$/.exec(s))) o.maximum = Number(m[1]);
  } else if (type === "choice"){
    if ((m = /^one of (.*)$/.exec(s))) o.choices = m[1].split(", ");
  } else if (type === "words"){
    if ((m = /up to (\d+) words/.exec(s))) o.max_items = Number(m[1]);
    if (/each once/.test(s)) o.unique = true;
  }
  return o;
}
function mdlFieldSpec(f){
  const type = mdlTypeKey(f.type), o = { name: f.name, label: f.label || f.name, type };
  if (f.required) o.required = true;
  if (f.nullable) o.nullable = true;
  if (f.retired) o.retired = true;
  if ((f.aliases || []).length) o.aliases = f.aliases.slice();
  return Object.assign(o, f.constraints || mdlParseSays(type, f.says));
}
function mdlSpecOf(p){
  if (p.spec) return mdlClone(p.spec);
  const v = p.version || 1;
  const s = { schema_version: 1, name: p.name, version: v, label: p.label, base: p.base, fields: (p.fields || []).filter(f => !f.locked).map(mdlFieldSpec) };
  if (v > 1) s.parent = "x:" + p.name + "/v" + (v - 1);
  if (p.about) s.about = p.about;
  if (p.abstract) s.abstract = true;
  if (p.discriminator) s.discriminator = p.discriminator;
  if (p.state === "off") s.enabled = false;
  const out = ((p.links && p.links.out) || []).map(l => {
    const o = { name: l.name, label: l.label, mode: l.mode, to: l.to };
    if (l.many) o.many = true;
    if (l.required) o.required = true;
    if (l.enabled === false) o.enabled = false;
    return o;
  });
  if (out.length) s.links = out;
  return s;
}

/* ── sheets: one at a time, painted into a host on the body ─────────────────────────────────────────────────────────────── */
function mdlShell(title, body){
  return `<div class="wbscrim wb" data-mdl="close"></div><div class="o2sheet wbsheet mdlsheet wb" role="dialog" aria-label="${mdlEsc(title)}">` +
    `<h4>${mdlEsc(title)}</h4>${body}</div>`;
}
function mdlSheetHtml(){
  const s = mdlState().sheet;
  if (!s) return "";
  if (s.kind === "add") return mdlAddSheet();
  if (s.kind === "field") return mdlFieldSheet();
  if (s.kind === "onoff") return mdlOnOffSheet();
  if (s.kind === "link") return mdlLinkSheet();
  if (s.kind === "try") return mdlTrySheet();
  if (s.kind === "restore") return mdlRestoreSheet();
  if (s.kind === "fit") return mdlFitSheet();
  return "";
}
function mdlPaintSheet(){
  if (typeof document === "undefined" || !document.createElement) return;
  let host = document.getElementById && document.getElementById("mdl-sheet");
  if (!host){
    if (!mdlState().sheet) return;
    host = document.createElement("div"); host.id = "mdl-sheet"; document.body.appendChild(host);
  }
  host.innerHTML = mdlSheetHtml();
}
function mdlOpenSheet(s){ const st = mdlState(); if (st.timer){ clearTimeout(st.timer); st.timer = null; } st.sheet = s; mdlPaintSheet(); }
function mdlCloseSheet(){ const st = mdlState(); if (st.timer){ clearTimeout(st.timer); st.timer = null; } st.sheet = null; mdlPaintSheet(); }

/* the live line: what the change does to what fits, from the preview; the words, never the codes */
function mdlLiveLine(pv){
  if (!pv) return { cls: "", glyph: "", text: "" };
  if (pv.state === "checking") return { cls: "wait", glyph: "\u2026", text: "Checking..." };
  if (!pv.ok) return { cls: "bad", glyph: "!", text: (pv.faults || []).join(" · ") || "That does not fit." };
  const aff = pv.affects || {}, bad = (aff.would_not_fit || []).map(x => x && x.name ? x.name + (x.v ? " v" + x.v : "") : String(x));
  if (pv.class === "same") return { cls: "ok", glyph: "\u2713", text: "No change in what fits." };
  if (pv.class === "tightens"){
    const none = aff.unchecked ? "" : bad.length ? " " + bad.join(", ") + " would not fit." : " Nothing filed would be turned away.";
    return { cls: "ok", glyph: "\u2713", text: "Tightens: fewer values fit." + none };
  }
  return { cls: "amber", glyph: "?", text: "Lets in more" + (pv.says ? ": this would " + pv.says + "." : ".") + " This waits for your stamp." };
}
function mdlLiveHtml(pv){
  const l = mdlLiveLine(pv);
  return l.text ? `<i class="mdlg" aria-hidden="true">${l.glyph}</i><span>${mdlEsc(l.text)}</span>` : "";
}
function mdlLiveBox(pv){ return `<div id="mdl-live" class="mdllive ${mdlLiveLine(pv).cls}" role="status">${mdlLiveHtml(pv)}</div>`; }
function mdlSaveLabel(pv){ return pv && pv.state !== "checking" && pv.ok && pv.needs_stamp ? "Save for my stamp" : "Save"; }
/* while the owner types, only the live line and the save button follow; a repaint would take the caret from under them */
function mdlSyncSheet(){
  const s = mdlState().sheet;
  if (!s || typeof document === "undefined" || !document.getElementById) return;
  const live = document.getElementById("mdl-live"), save = document.getElementById("mdl-save");
  if (live){ live.innerHTML = mdlLiveHtml(s.pv); live.className = "mdllive " + mdlLiveLine(s.pv).cls; }
  if (save){ save.disabled = !mdlCanSave(s); save.textContent = s.kind === "link" ? "Add the link" : s.kind === "add" ? "Make it" : mdlSaveLabel(s.pv); }
}
function mdlFaultBlock(s){ return (s.faults || []).length ? `<div class="mdlerr" role="alert">${s.faults.map(mdlEsc).join("<br>")}</div>` : ""; }

/* the preview: asked once, after the owner stops typing (A4.6.2 S22) */
function mdlSchedulePreview(){
  const st = mdlState(), s = st.sheet;
  if (!s) return;
  s.pv = { state: "checking" };
  mdlSyncSheet();
  if (st.timer) clearTimeout(st.timer);
  st.timer = setTimeout(mdlRunPreview, MDL_PAUSE);
}
function mdlPreviewBody(s){
  if (s.kind === "field" || s.kind === "link" || s.kind === "add" || s.kind === "fit"){
    const spec = mdlSheetSpec(s);
    return spec ? { op: "edit", key: "x." + spec.name, spec } : null;
  }
  if (s.kind === "onoff") return { op: s.enable ? "enable" : "disable", key: s.key };
  if (s.kind === "restore") return { op: "revert", key: s.key, to_rev: s.rev };
  return null;
}
async function mdlRunPreview(){
  const st = mdlState(), s = st.sheet;
  st.timer = null;
  if (!s) return;
  const body = mdlPreviewBody(s);
  if (!body){ s.pv = null; mdlSyncSheet(); return; }
  const seq = s.seq = (s.seq || 0) + 1;
  try { const r = await apiPost(MDL_API + "/preview", body); if (st.sheet !== s || s.seq !== seq) return; s.pv = Object.assign({ state: "ready" }, r); }
  catch (e) { if (st.sheet !== s || s.seq !== seq) return; s.pv = { state: "ready", ok: false, faults: mdlFaults(e) }; }
  mdlSyncSheet();
  if (s.kind === "onoff" || s.kind === "restore") mdlPaintSheet();
}
function mdlCanSave(s){
  if (s.busy) return false;
  if (s.kind === "add") return !!(s.base && s.label && mdlAddName(s) && !mdlTaken(s));
  const pv = s.pv;
  return !!(pv && pv.state !== "checking" && pv.ok);
}

/* the spec a sheet is about to post */
function mdlSheetSpec(s){
  if (s.kind === "add") return s.base && s.label && mdlAddName(s) ? mdlAddSpec(s) : null;
  if (s.kind === "fit") return s.spec ? mdlClone(s.spec) : null;
  if (s.kind === "link"){
    const spec = mdlClone(s.spec);
    spec.links = (spec.links || []).concat([mdlLinkSpec(s.link)]);
    return spec;
  }
  if (s.kind === "field"){
    const spec = s.back ? mdlAddSpec(s.back) : mdlClone(s.spec);
    return mdlPutField(spec, s);
  }
  return null;
}
function mdlPutField(spec, s){
  const f = mdlClone(s.field), at = spec.fields.map(x => x.name).indexOf(s.orig ? s.orig.name : f.name);
  if (s.act === "retire"){ f.retired = true; }
  if (s.act === "rename" && s.orig){
    const al = (s.orig.aliases || []).concat([s.orig.name]);
    f.aliases = al.slice(-3);
  }
  Object.keys(f).forEach(k => { if (f[k] === "" || f[k] === undefined || (Array.isArray(f[k]) && !f[k].length && k !== "choices")) delete f[k]; });
  if (at >= 0) spec.fields[at] = f; else spec.fields.push(f);
  return spec;
}

/* ── S21 add a model ────────────────────────────────────────────────────────────────────────────────────────────────────── */
function mdlBaseRef(key){
  if (/^core:/.test(key)) return key;
  const e = mdlEntry(key);
  return e ? "x:" + e.name + "/v" + e.version : key;
}
function mdlAddName(s){ return s.fixedName || mdlKeyOf(s.label); }
function mdlTaken(s){
  if (s.fixedName) return false;
  const n = mdlAddName(s);
  return !!n && mdlOwnEntries().some(e => e.name === n);
}
function mdlAddSpec(s){
  const spec = { schema_version: 1, name: mdlAddName(s), version: s.version || 1, label: s.label, base: mdlBaseRef(s.base), fields: mdlClone(s.fields || []) };
  if (s.parent) spec.parent = s.parent;
  if (s.about) spec.about = s.about;
  return spec;
}
function mdlOpenAdd(baseKey, over){
  const st = mdlState();
  const s = Object.assign({ kind: "add", base: baseKey || "", label: "", about: "", fields: [], version: 1, parent: null, faults: [], busy: false, pv: null }, over || {});
  if (baseKey && /^x\./.test(baseKey)) mdlLoadPage(baseKey);
  mdlOpenSheet(s);
}
function mdlOpenNewVersion(p){
  const st = mdlState();
  mdlOpenAdd(p.base && /^x:/.test(p.base) ? "x." + mdlNameOfBase(p.base) : p.base, {
    version: (p.version || 1) + 1, parent: "x:" + p.name + "/v" + p.version, label: p.label, about: p.about || "", fixedName: p.name, locked: true,
    baseRef: p.base });
  const s = st.sheet;
  s.base = p.base;
  s.baseLabel = p.base_label;
  mdlSchedulePreview();
}
function mdlAddSheet(){
  const st = mdlState(), s = st.sheet, L = st.list || {};
  const bases = (L.buildable || []);
  const step1 = s.locked
    ? `<div class="dpfline">Version ${mdlEsc(s.version)} builds on version ${mdlEsc(s.version - 1)}; only what narrows is offered.</div>`
    : `<div class="mdlradios" role="radiogroup" aria-label="Build it on">` + bases.map(b =>
      `<label class="mdlradio"><input type="radio" name="mdl-base" value="${mdlEsc(b.key)}" data-mdlin="base"${s.base === b.key ? " checked" : ""}><span>${mdlEsc(b.label)}</span>` +
      `<em>${mdlEsc(b.says)}</em></label>`).join("") + `</div>`;
  const key = mdlAddName(s);
  const basePage = s.base && /^x\./.test(s.base) ? st.pages[s.base] : null;
  const inherited = basePage ? (basePage.fields || []).map(f =>
    `<div class="mdlfield"><span class="mdlfn"><i class="mdlpad" aria-hidden="true"></i>${mdlEsc(f.name)}</span><span class="mdlft">${mdlBoundWords(f)}</span><span class="mdlfrom">from ${mdlEsc(f.from)}</span></div>`).join("")
    : (s.base ? mdlQuiet("It starts with the fields of " + ((bases.filter(b => b.key === s.base)[0] || {}).label || "its base") + ".") : "");
  const own = (s.fields || []).map((f, i) => `<div class="mdlfield"><span class="mdlfn">${mdlEsc(f.name)}</span><span class="mdlft">${mdlEsc((MDL_TYPES.filter(t => t[0] === f.type)[0] || ["", f.type])[1])}${mdlBoundSaysOf(f) ? ", " + mdlEsc(mdlBoundSaysOf(f)) : ""}${f.required ? ", required" : ""}</span>` +
    `<span class="mdlfb">${mdlBtn("Change", `data-mdl="field" data-mdl-name="${mdlEsc(f.name)}"`)}${mdlBtn("Remove", `data-mdl="rmfield" data-mdl-name="${mdlEsc(f.name)}"`)}</span></div>`).join("");
  const taken = mdlTaken(s) ? `<div class="mdlerr" role="alert">a model called ${mdlEsc(((mdlOwnEntries().filter(e => e.name === key)[0]) || {}).label || s.label)} is already there</div>` : "";
  return mdlShell(s.locked ? "New version of " + s.label : "Add a model",
    `<label>1 Build it on</label>${step1}` +
    `<label for="mdl-label">2 Call it</label><input id="mdl-label" data-mdlin="label" value="${mdlEsc(s.label)}" maxlength="60"${s.locked ? " readonly" : ""} autocomplete="off">` +
    (key ? `<div class="mdlkept">kept as x.${mdlEsc(key)}</div>` : "") + taken +
    `<input id="mdl-about" data-mdlin="about" value="${mdlEsc(s.about)}" maxlength="300" placeholder="One line about it" aria-label="One line about it" autocomplete="off">` +
    `<label>3 Its fields</label>${inherited}${own}<div class="dpoffer">${mdlBtn("Add a field", `data-mdl="field"`)}</div>` +
    mdlLiveBox(s.pv) + mdlFaultBlock(s) +
    `<div class="o2acts2">${mdlBtn("Cancel", `data-mdl="close"`)}${mdlBtn(s.busy ? "Saving" : "Make it", `id="mdl-save" data-mdl="make"${mdlCanSave(s) ? "" : " disabled"}`, "dpstamp")}</div>`);
}
function mdlBoundSaysOf(f){
  if (f.type === "text" || f.type === "long_text") return f.max_len ? "up to " + f.max_len + " characters" : "";
  if (f.type === "whole" || f.type === "number") return f.minimum != null && f.maximum != null ? "between " + f.minimum + " and " + f.maximum : f.maximum != null ? "up to " + f.maximum : f.minimum != null ? "from " + f.minimum : "";
  if (f.type === "choice") return "one of " + (f.choices || []).join(", ");
  if (f.type === "words") return f.max_items ? "up to " + f.max_items + " words" : "";
  return "";
}
async function mdlMake(){
  const st = mdlState(), s = st.sheet;
  if (!s || !mdlCanSave(s)) return;
  s.busy = true; s.faults = []; mdlPaintSheet();
  const spec = mdlAddSpec(s);
  const r = await mdlSend(s.locked ? "/" + encodeURIComponent("x." + spec.name) : "", s.locked ? { spec, rev: (st.list || {}).rev } : { spec });
  if (st.sheet !== s) return;
  s.busy = false;
  if (r.faults){ s.faults = r.faults; mdlPaintSheet(); return; }
  await mdlDone(r.res, "x." + spec.name);
}

/* ── writes ─────────────────────────────────────────────────────────────────────────────────────────────────────────────── */
async function mdlSend(tail, body){
  try { return { res: await apiPost(MDL_API + tail, body) }; }
  catch (e) { return { faults: mdlFaults(e) }; }
}
/* after a write: the list and the page are read again, the sheet is gone, and the screen says what it did */
async function mdlDone(res, key, said){
  const st = mdlState();
  st.sheet = null; st.pages = {}; st.shapes = {}; st.graph = null; st.historyLoaded = false; st.history = {};
  st.said = res && res.pending ? "Saved for your stamp. Nothing changes until you stamp it."
    : res && res.dropped ? "Dropped. Nothing changed." : (said || "Done. You can undo it from the model's page.");
  if (res && res.model && res.model.key){ st.pages[res.model.key] = res.model; }
  if (key && !(res && res.dropped) && st.view !== "structure" && !(res && res.pending && st.view === "list")){ st.view = "page"; st.key = (res && res.model && res.model.key) || key; }
  await mdlLoad(true);
  if (st.view === "page" && st.key && !st.pages[st.key]) mdlLoadPage(st.key);
  mdlPaintSheet();
}
async function mdlStamp(id, approve){
  const st = mdlState();
  if (st.busy["s:" + id]) return;
  st.busy["s:" + id] = true;
  const r = await mdlSend("/pending/" + encodeURIComponent(id), { approve: !!approve });
  delete st.busy["s:" + id];
  if (r.faults){ st.said = r.faults[0]; await mdlLoad(true); return; }
  await mdlDone(r.res, null, approve ? "Stamped. The change is in." : "Dropped. Nothing changed.");
}
async function mdlUndo(){
  const st = mdlState(), p = st.pages[st.key];
  if (!p) return;
  const r = await mdlSend("/" + encodeURIComponent(p.key) + "/undo", { rev: p.rev });
  if (r.faults){ st.said = r.faults[0]; mdlRender(); return; }
  await mdlDone(r.res, p.key, "Undone.");
}

/* ── S22 change a field (and rename, retire, add) ───────────────────────────────────────────────────────────────────────── */
function mdlBlankField(){ return { name: "", label: "", type: "text" }; }
function mdlOpenField(name, act){
  const st = mdlState(), back = st.sheet && st.sheet.kind === "add" ? st.sheet : null;
  let spec, orig = null, mode = "page", key = null, field;
  if (back){
    mode = "draft";
    orig = (back.fields || []).filter(f => f.name === name)[0] || null;
    spec = null;
  } else {
    const p = st.pages[st.key];
    if (!p) return;
    spec = mdlSpecOf(p); key = p.key;
    orig = spec.fields.filter(f => f.name === name)[0] || null;
  }
  field = orig ? mdlClone(orig) : mdlBlankField();
  if (act === "rename") field = Object.assign(field, { name: "" });
  const s = { kind: "field", mode, act: act || "change", key, spec, back, orig, field, faults: [], busy: false, pv: null, fresh: !orig,
    newName: "" };
  const baseKey = back ? back.base : (st.pages[st.key] && st.pages[st.key].base ? "x." + mdlNameOfBase(st.pages[st.key].base) : "");
  if (baseKey && /^x\./.test(baseKey)) mdlLoadPage(baseKey);
  s.baseKey = baseKey;
  mdlOpenSheet(s);
  if (act !== "rename" && (act === "retire" || orig)) mdlSchedulePreview();
}
/* the bound the base sets for a field of this name: the controls stop there and say so */
function mdlBoundFor(s){
  const bp = s.baseKey ? mdlState().pages[s.baseKey] : null;
  if (!bp) return null;
  const f = (bp.fields || []).filter(x => x.name === (s.orig ? s.orig.name : s.field.name))[0];
  return f ? Object.assign({ type: mdlTypeKey(f.type), from: bp.label }, mdlParseSays(mdlTypeKey(f.type), f.says)) : null;
}
function mdlNumBox(s, label, prop, b){
  const v = s.field[prop], lim = b && b[prop] != null ? b[prop] : null;
  const isMax = /^max/.test(prop);
  return `<label for="mdl-f-${prop}">${mdlEsc(label)}</label><input id="mdl-f-${prop}" type="number" data-mdlin="f:${prop}" value="${v == null ? "" : mdlEsc(v)}"` +
    `${lim != null ? ` ${isMax ? "max" : "min"}="${mdlEsc(lim)}"` : ""}>` +
    (lim != null ? `<div class="mdlkept">the base allows ${isMax ? "up to" : "at least"} ${mdlEsc(lim)}</div>` : "");
}
function mdlFieldControls(s){
  const f = s.field, b = mdlBoundFor(s);
  const typeSel = s.fresh
    ? `<label for="mdl-f-type">Type</label><select id="mdl-f-type" data-mdlin="f:type">${MDL_TYPES.map(t => `<option value="${t[0]}"${f.type === t[0] ? " selected" : ""}>${mdlEsc(t[1])}</option>`).join("")}</select>`
    : `<div class="mdlkept">Type: ${mdlEsc((MDL_TYPES.filter(t => t[0] === f.type)[0] || ["", f.type])[1])} (fixed)</div>`;
  let c = "";
  if (f.type === "text") c = mdlNumBox(s, "Up to (characters)", "max_len", b) + mdlNumBox(s, "At least", "min_len", b) +
    `<label for="mdl-f-pattern">Pattern</label><select id="mdl-f-pattern" data-mdlin="f:pattern">${MDL_PATTERNS.map(p => `<option value="${p[0]}"${(f.pattern || "") === p[0] ? " selected" : ""}>${mdlEsc(p[1])}</option>`).join("")}</select>`;
  else if (f.type === "long_text") c = mdlNumBox(s, "Up to (characters)", "max_len", b);
  else if (f.type === "whole" || f.type === "number") c = mdlNumBox(s, "Lowest", "minimum", b) + mdlNumBox(s, "Highest", "maximum", b);
  else if (f.type === "choice") c = `<label for="mdl-f-choices">One of (separate with commas)</label><input id="mdl-f-choices" data-mdlin="f:choices" value="${mdlEsc((f.choices || []).join(", "))}">` +
    (b && b.choices ? `<div class="mdlkept">the base allows ${b.choices.map(mdlEsc).join(", ")}</div>` : "");
  else if (f.type === "words") c = mdlNumBox(s, "Up to (words)", "max_items", b) +
    `<label class="mdlcheck"><input type="checkbox" data-mdlin="f:unique"${f.unique ? " checked" : ""}> each word once</label>`;
  return typeSel + c + `<label class="mdlcheck"><input type="checkbox" data-mdlin="f:required"${f.required ? " checked" : ""}> required</label>`;
}
function mdlFieldSheet(){
  const s = mdlState().sheet, f = s.field;
  let top, extra = "";
  if (s.act === "rename"){
    top = `<div class="dpfline">The old name keeps working.</div><label for="mdl-newname">New name</label><input id="mdl-newname" data-mdlin="f:name" value="${mdlEsc(f.name)}" autocomplete="off">`;
  } else if (s.act === "retire"){
    top = `<div class="dpfline">It stays readable and is never asked for.${s.orig && s.orig.required ? " It is needed now, so retiring it lets in more." : ""}</div>`;
  } else {
    top = (s.fresh ? `<label for="mdl-f-name">Name</label><input id="mdl-f-name" data-mdlin="f:name" value="${mdlEsc(f.name)}" autocomplete="off" maxlength="31">` : `<div class="mdlkept">Kept as: ${mdlEsc(f.name)}</div>`) +
      `<label for="mdl-f-label">Label</label><input id="mdl-f-label" data-mdlin="f:label" value="${mdlEsc(f.label)}" maxlength="60" autocomplete="off">` + mdlFieldControls(s);
    if (!s.fresh && s.mode === "page") extra = mdlBtn("Rename...", `data-mdl="rename" data-mdl-name="${mdlEsc(f.name)}"`) + mdlBtn("Retire", `data-mdl="retire" data-mdl-name="${mdlEsc(f.name)}"`);
  }
  const title = s.fresh ? "Add a field" : (s.act === "rename" ? "Rename " : s.act === "retire" ? "Retire " : "Change ") + (s.orig ? s.orig.name : "");
  return mdlShell(title, top + mdlLiveBox(s.pv) + mdlFaultBlock(s) +
    `<div class="o2acts2">${extra}${mdlBtn("Cancel", `data-mdl="close"`)}${mdlBtn(s.busy ? "Saving" : mdlSaveLabel(s.pv), `id="mdl-save" data-mdl="save"${mdlCanSave(s) ? "" : " disabled"}`, "dpstamp")}</div>`);
}
function mdlSetField(s, prop, raw){
  const f = s.field, b = mdlBoundFor(s) || {};
  if (prop === "required" || prop === "unique"){ if (raw) f[prop] = true; else delete f[prop]; }
  else if (prop === "type"){ const keep = { name: f.name, label: f.label, required: f.required }; s.field = Object.assign({ type: raw }, keep); }
  else if (prop === "name" || prop === "label") f[prop] = raw;
  else if (prop === "pattern"){ if (raw === "") delete f.pattern; else f.pattern = raw; }
  else if (prop === "choices"){
    let list = String(raw).split(",").map(x => x.trim()).filter(Boolean);
    if (b.choices) list = list.filter(x => b.choices.indexOf(x) >= 0);
    f.choices = list;
  } else {
    if (raw === "" || raw == null) delete f[prop];
    else {
      let n = Number(raw);
      if (b[prop] != null && !isNaN(n)) n = /^max/.test(prop) ? Math.min(n, b[prop]) : Math.max(n, b[prop]);
      f[prop] = n;
    }
  }
}
async function mdlSaveField(){
  const st = mdlState(), s = st.sheet;
  if (!s || !mdlCanSave(s)) return;
  if (s.mode === "draft"){
    const back = s.back, f = mdlClone(s.field);
    if (s.act === "retire") return;
    Object.keys(f).forEach(k => { if (f[k] === "" || f[k] === undefined) delete f[k]; });
    const at = back.fields.map(x => x.name).indexOf(s.orig ? s.orig.name : f.name);
    if (at >= 0) back.fields[at] = f; else back.fields.push(f);
    st.sheet = back; mdlPaintSheet(); mdlSchedulePreview();
    return;
  }
  const spec = mdlSheetSpec(s), p = st.pages[st.key];
  s.busy = true; s.faults = []; mdlPaintSheet();
  const r = await mdlSend("/" + encodeURIComponent(p.key), { spec, rev: p.rev });
  if (st.sheet !== s) return;
  s.busy = false;
  if (r.faults){ s.faults = r.faults; mdlPaintSheet(); return; }
  await mdlDone(r.res, p.key);
}

/* ── S23 turn a model on or off ─────────────────────────────────────────────────────────────────────────────────────────── */
function mdlOpenOnOff(){
  const st = mdlState(), p = st.pages[st.key];
  if (!p) return;
  const enable = p.state === "off";
  const baseName = mdlNameOfBase(p.base), be = baseName ? mdlEntry("x." + baseName) : null;
  const s = { kind: "onoff", key: p.key, label: p.label, enable, baseOff: enable && be && be.state === "off" ? be.label : "", faults: [], busy: false, pv: { state: "checking" } };
  mdlOpenSheet(s);
  if (!s.baseOff) mdlRunPreview();
}
function mdlOnOffSheet(){
  const s = mdlState().sheet, pv = s.pv || {}, aff = pv.affects || {};
  let body;
  if (s.baseOff) body = `<div class="dpfline">${mdlEsc(s.baseOff)} is off; turn it on first.</div>`;
  else if (pv.state === "checking") body = dpSkel();
  else if (!pv.ok) body = `<div class="mdlerr" role="alert">${(pv.faults || []).map(mdlEsc).join("<br>")}</div>`;
  else {
    const filed = (aff.used_by || []).filter(u => u.kind !== "artifact_template").map(mdlUsedWords);
    const tpl = (aff.used_by || []).filter(u => u.kind === "artifact_template").map(u => "the artifact template " + mdlEsc(u.name));
    body = s.enable
      ? `<div class="dpfline">${mdlEsc(s.label)} is offered again when you build, link or file.</div><div class="dpfline">You can turn it off again; nothing is deleted.</div>`
      : `<div class="dpfline">${mdlEsc(s.label)} stops being offered when you build, link or file.</div>` +
        ((aff.turns_off || []).length ? `<div class="dpfline">It turns off with it: ${aff.turns_off.map(mdlEsc).join(", ")}</div>` : "") +
        (filed.length ? `<div class="dpfline">Still there, nothing lost: ${filed.join(" · ")}</div>` : `<div class="dpfline">Still there, nothing lost: what it holds.</div>`) +
        (tpl.length ? `<div class="dpfline">Noted as using a model that is off: ${tpl.join(" · ")}</div>` : "") +
        `<div class="dpfline">You can turn it on again; everything comes back as it was.</div>`;
  }
  const go = s.baseOff ? "" : mdlBtn(s.busy ? "Saving" : s.enable ? "Turn on" : "Turn off", `data-mdl="onoffgo"${s.busy || !pv.ok ? " disabled" : ""}`, "dpstamp");
  return mdlShell((s.enable ? "Turn on " : "Turn off ") + s.label, body + mdlFaultBlock(s) +
    `<div class="o2acts2">${mdlBtn(s.enable ? "Keep it off" : "Keep it on", `data-mdl="close"`)}${go}</div>`);
}
async function mdlOnOffGo(){
  const st = mdlState(), s = st.sheet, p = st.pages[st.key];
  if (!s || s.kind !== "onoff" || s.busy || !p) return;
  s.busy = true; mdlPaintSheet();
  const r = await mdlSend("/" + encodeURIComponent(s.key) + "/enabled", { enabled: !!s.enable, rev: p.rev });
  if (st.sheet !== s) return;
  s.busy = false;
  if (r.faults){ s.faults = r.faults; mdlPaintSheet(); return; }
  await mdlDone(r.res, s.key);
}

/* ── S24 link or nest ───────────────────────────────────────────────────────────────────────────────────────────────────── */
function mdlLinkSpec(l){
  const o = { name: l.name, label: l.label || l.name, mode: l.mode, to: l.to };
  if (l.many){ o.many = true; if (l.max) o.max = Number(l.max); }
  if (l.required) o.required = true;
  return o;
}
function mdlOpenLink(){
  const st = mdlState(), p = st.pages[st.key];
  if (!p) return;
  mdlOpenSheet({ kind: "link", key: p.key, spec: mdlSpecOf(p), link: { name: "", label: "", mode: "nest", to: "", many: false, max: "", required: false }, faults: [], busy: false, pv: null });
}
function mdlLinkTargets(own){
  const on = mdlOwnEntries().filter(e => e.state === "on").map(e => ({ to: "x:" + e.name, label: e.label }));
  return on.concat(MDL_NESTABLE.map(n => ({ to: n[0], label: n[1] })));
}
function mdlLinkSheet(){
  const s = mdlState().sheet, l = s.link;
  const opts = `<option value="">Choose...</option>` + mdlLinkTargets().map(t => `<option value="${mdlEsc(t.to)}"${l.to === t.to ? " selected" : ""}>${mdlEsc(t.label)}</option>`).join("");
  return mdlShell("Link or nest",
    `<label for="mdl-l-to">It holds</label><select id="mdl-l-to" data-mdlin="l:to">${opts}</select>` +
    `<label for="mdl-l-name">Field name</label><input id="mdl-l-name" data-mdlin="l:name" value="${mdlEsc(l.name)}" autocomplete="off" maxlength="31">` +
    `<label>How</label><label class="mdlcheck"><input type="radio" name="mdl-l-mode" data-mdlin="l:mode" value="nest"${l.mode === "nest" ? " checked" : ""}> Hold it inside</label>` +
    `<label class="mdlcheck"><input type="radio" name="mdl-l-mode" data-mdlin="l:mode" value="refer"${l.mode === "refer" ? " checked" : ""}> Point to it by its id</label>` +
    `<label>How many</label><label class="mdlcheck"><input type="radio" name="mdl-l-many" data-mdlin="l:many" value="many"${l.many ? " checked" : ""}> many, at most <input type="number" data-mdlin="l:max" value="${mdlEsc(l.max)}" aria-label="At most"></label>` +
    `<label class="mdlcheck"><input type="radio" name="mdl-l-many" data-mdlin="l:many" value="one"${l.many ? "" : " checked"}> one</label>` +
    `<label class="mdlcheck"><input type="checkbox" data-mdlin="l:required"${l.required ? " checked" : ""}> required</label>` +
    mdlLiveBox(s.pv) + mdlFaultBlock(s) +
    `<div class="o2acts2">${mdlBtn("Cancel", `data-mdl="close"`)}${mdlBtn(s.busy ? "Saving" : "Add the link", `id="mdl-save" data-mdl="addlink"${mdlCanSave(s) && s.link.to && s.link.name ? "" : " disabled"}`, "dpstamp")}</div>`);
}
function mdlSetLink(s, prop, raw){
  const l = s.link;
  if (prop === "required") l.required = !!raw;
  else if (prop === "many") l.many = raw === "many";
  else if (prop === "to"){
    l.to = raw;
    const t = mdlLinkTargets().filter(x => x.to === raw)[0];
    l.label = t ? t.label : "";
    if (t && !l.nameTouched) l.name = mdlKeyOf(t.label);
  } else { l[prop] = raw; if (prop === "name") l.nameTouched = true; }
}
async function mdlAddLink(){
  const st = mdlState(), s = st.sheet, p = st.pages[st.key];
  if (!s || !mdlCanSave(s) || !s.link.to || !s.link.name || !p) return;
  s.busy = true; s.faults = []; mdlPaintSheet();
  const r = await mdlSend("/" + encodeURIComponent(p.key), { spec: mdlSheetSpec(s), rev: p.rev });
  if (st.sheet !== s) return;
  s.busy = false;
  if (r.faults){ s.faults = r.faults; mdlPaintSheet(); return; }
  await mdlDone(r.res, p.key);
}

/* ── S25 try a sample, the shape, an example ────────────────────────────────────────────────────────────────────────────── */
function mdlOpenTry(tab){
  const st = mdlState(), s = st.sheet;
  const draft = s && (s.kind === "add" || s.kind === "field" || s.kind === "link") ? mdlSheetSpec(s) : null;
  const key = st.view === "page" ? st.key : (s && s.key) || null;
  const p = key ? mdlPageOf(key) : null;
  const t = { kind: "try", tab: tab || "try", key, label: p ? p.label : draft ? draft.label : "", off: !!(p && p.state === "off"), spec: draft, sample: "", result: null, example: null, schema: null, faults: [] };
  mdlOpenSheet(t);
  if (tab === "shape" || tab === "example") mdlLoadShape();
}
async function mdlLoadShape(){
  const st = mdlState(), s = st.sheet;
  if (!s || s.kind !== "try") return;
  if (s.spec){ s.result = null; s.schema = null; s.example = null; s.note = "Save the model first to see its shape."; mdlPaintSheet(); return; }
  const got = await mdlShapeOf(s.key);
  if (st.sheet !== s) return;
  if (got.failed){ s.result = { error: got.failed }; } else { s.schema = got.schema; s.example = got.example; }
  mdlPaintSheet();
}
function mdlNotJson(e){
  /* where it broke is a position, which is a number the screen does not print */
  const m = String((e && e.message) || "").replace(/\s*\([^)]*\d[^)]*\)/g, "").replace(/\s+at (position|line) \d+.*$/i, "").replace(/\s+/g, " ").trim();
  return "That is not JSON: " + (m || "it could not be read");
}
function mdlTrySheet(){
  const s = mdlState().sheet;
  const tabs = `<div class="mdltabs" role="tablist">` + [["try", "Try a sample"], ["shape", "Shape"], ["example", "Example"]].map(t =>
    `<button type="button" role="tab" class="btn wb mdltab${s.tab === t[0] ? " on" : ""}" aria-selected="${s.tab === t[0] ? "true" : "false"}" data-mdl="${t[0] === "try" ? "trytab" : t[0] + "tab"}">${mdlEsc(t[1])}</button>`).join("") + `</div>`;
  let body;
  if (s.tab === "shape"){
    body = s.note ? mdlQuiet(s.note) : s.result && s.result.error ? `<div class="mdlerr" role="alert">${mdlEsc(s.result.error)}</div>`
      : s.schema ? `<pre class="mdlpre">${mdlEsc(JSON.stringify(s.schema, null, 2))}</pre>` + mdlBtn("Copy", `data-mdl="copy"`) : dpSkel();
  } else if (s.tab === "example"){
    body = s.note ? mdlQuiet(s.note) : s.example !== null && s.example !== undefined ? `<pre class="mdlpre">${mdlEsc(JSON.stringify(s.example, null, 2))}</pre>` : dpSkel();
  } else {
    const r = s.result;
    let res = mdlQuiet("Paste a value and check it. Nothing is stored.");
    if (r && r.notjson) res = `<div class="mdlfit bad" role="status"><i class="mdlg" aria-hidden="true">!</i><span>${mdlEsc(r.notjson)}</span></div>`;
    else if (r && r.error) res = `<div class="mdlerr" role="alert">${mdlEsc(r.error)}</div>`;
    else if (r && r.ok) res = `<div class="mdlfit ok" role="status"><i class="mdlg" aria-hidden="true">\u2713</i><span>It fits.</span></div>`;
    else if (r){
      const more = r.faults.length > MDL_TWELVE;
      res = `<div class="mdlfit bad" role="status"><i class="mdlg" aria-hidden="true">!</i><span>It does not fit:</span></div><ul class="mdlfaults">` +
        r.faults.slice(0, MDL_TWELVE).map(f => `<li>${mdlEsc(f)}</li>`).join("") + (more ? `<li>and more</li>` : "") + `</ul>`;
    }
    body = `<textarea id="mdl-sample" data-mdlin="sample" rows="6" spellcheck="false" aria-label="A sample, as JSON">${mdlEsc(s.sample)}</textarea>` +
      `<div class="o2acts2">${mdlBtn("Make an example", `data-mdl="makeex"`)}${mdlBtn("Check", `data-mdl="check"`, "dpstamp")}</div>` +
      (s.off ? mdlQuiet(s.label + " is off; this checks it anyway.") : "") + res;
  }
  return mdlShell((s.label ? s.label + " · " : "") + "Try a sample", tabs + body + `<div class="o2acts2">${mdlBtn("Close", `data-mdl="close"`)}</div>`);
}
async function mdlCheck(){
  const st = mdlState(), s = st.sheet;
  if (!s || s.kind !== "try") return;
  let sample;
  try { sample = JSON.parse(s.sample); } catch (e) { s.result = { notjson: mdlNotJson(e) }; mdlPaintSheet(); return; }
  const body = s.spec ? { spec: s.spec, sample } : { key: s.key, sample };
  try {
    const r = await apiPost(MDL_API + "/validate", body);
    if (st.sheet !== s) return;
    s.result = { ok: !!r.ok, faults: r.faults || [] };
  } catch (e) { if (st.sheet !== s) return; s.result = { error: mdlFaults(e).join(" · ") }; }
  mdlPaintSheet();
}
async function mdlMakeExample(){
  const st = mdlState(), s = st.sheet;
  if (!s || s.kind !== "try" || s.spec) return;
  const got = await mdlShapeOf(s.key);
  if (st.sheet !== s) return;
  if (got.failed){ s.result = { error: got.failed }; } else { s.sample = JSON.stringify(got.example); s.result = null; }
  mdlPaintSheet();
}

/* ── S26 structure and history ──────────────────────────────────────────────────────────────────────────────────────────── */
const MDL_BOX = { w: 150, h: 34, gx: 70, gy: 20 };
function mdlClip(cx, cy, dx, dy){
  const ux = dx - cx, uy = dy - cy;
  const t = Math.min(ux ? (MDL_BOX.w / 2) / Math.abs(ux) : Infinity, uy ? (MDL_BOX.h / 2) / Math.abs(uy) : Infinity);
  return [cx + ux * t, cy + uy * t];
}
function mdlDrawing(g){
  const nodes = g.nodes || [], edges = g.edges || [], up = {};
  edges.forEach(e => { if (e.kind === "extends") up[e.from] = e.to; });
  const level = k => { let d = 0, c = k; const seen = {}; while (up[c] && !seen[c]){ seen[c] = 1; c = up[c]; d++; } return d; };
  const cols = {};
  nodes.forEach(n => { const l = level(n.key); (cols[l] = cols[l] || []).push(n); });
  const pos = {}, boxes = [];
  const levels = Object.keys(cols).map(Number).sort((a, b) => a - b);
  let maxRows = 0;
  levels.forEach(l => cols[l].forEach((n, i) => {
    const x = 10 + l * (MDL_BOX.w + MDL_BOX.gx), y = 10 + i * (MDL_BOX.h + MDL_BOX.gy);
    pos[n.key] = { x, y, cx: x + MDL_BOX.w / 2, cy: y + MDL_BOX.h / 2 };
    maxRows = Math.max(maxRows, i + 1);
    const word = n.core ? "built in" : (MDL_STATE[n.state] || MDL_STATE.on)[0].toLowerCase();
    boxes.push(`<g class="mdlbox${n.core ? " core" : ""}" tabindex="0" role="link" ${n.core ? "" : `data-mdl="open" data-mdl-key="${mdlEsc(n.key)}" `}aria-label="${mdlEsc(n.label)}, ${mdlEsc(word)}">` +
      `<rect x="${x}" y="${y}" width="${MDL_BOX.w}" height="${MDL_BOX.h}" rx="6"></rect>` +
      `<text x="${x + 10}" y="${y + 14}" class="mdlbt">${mdlEsc(n.label)}</text><text x="${x + 10}" y="${y + 27}" class="mdlbs">${n.core ? "Built in" : mdlEsc((MDL_STATE[n.state] || MDL_STATE.on)[0])}</text></g>`);
  }));
  const lines = edges.filter(e => pos[e.from] && pos[e.to] && e.from !== e.to).map(e => {
    const a = pos[e.from], b = pos[e.to], p1 = mdlClip(a.cx, a.cy, b.cx, b.cy), p2 = mdlClip(b.cx, b.cy, a.cx, a.cy);
    const cls = e.kind === "extends" ? "mdlext" : e.kind === "nests" ? "mdlnest" : "mdlref";
    return `<line class="${cls}" x1="${p1[0].toFixed(1)}" y1="${p1[1].toFixed(1)}" x2="${p2[0].toFixed(1)}" y2="${p2[1].toFixed(1)}"${e.kind === "extends" ? ` marker-end="url(#mdl-closed)"` : e.kind === "refers" ? ` marker-end="url(#mdl-open)"` : ""}></line>`;
  });
  const W = 20 + levels.length * (MDL_BOX.w + MDL_BOX.gx), H = 20 + maxRows * (MDL_BOX.h + MDL_BOX.gy);
  return `<svg class="mdlsvg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="group" aria-label="How the models hang together">` +
    `<defs><marker id="mdl-closed" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="mdlcap"></path></marker>` +
    `<marker id="mdl-open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,1 L9,5 L0,9" class="mdlcapo"></path></marker></defs>` +
    lines.join("") + boxes.join("") + `</svg>`;
}
function mdlStructureHtml(){
  const st = mdlState();
  const tabs = `<div class="mdltabs" role="tablist">` + [["structure", "Structure"], ["history", "History"]].map(t =>
    `<button type="button" role="tab" class="btn wb mdltab${st.tab === t[0] ? " on" : ""}" aria-selected="${st.tab === t[0] ? "true" : "false"}" data-mdl="${t[0]}">${t[1]}</button>`).join("") + `</div>`;
  return tabs + (st.tab === "history" ? mdlHistoryHtml() : mdlGraphHtml());
}
function mdlGraphHtml(){
  const st = mdlState(), g = st.graph;
  if (st.graphErr) return mdlSayRead("the structure");
  if (!g){ mdlLoadGraph(); return dpSkel(); }
  const many = (g.nodes || []).length > 30, f = st.filter.toLowerCase();
  const text = (g.text || []).filter(t => !many || !f || t.toLowerCase().indexOf(f) >= 0);
  return (many ? `<label for="mdl-filter" class="mdlfl">Find a model</label><input id="mdl-filter" data-mdlin="filter" value="${mdlEsc(st.filter)}" autocomplete="off">` : mdlDrawing(g) +
    mdlQuiet("Solid line with a closed head: is a kind of. Thick line: holds. Dashed line: points to by its id. Grey with the word Built in: part of the app.")) +
    `<div class="mdlwords"><b>In words</b><ul id="mdl-words" class="mdlfaults">${text.map(t => `<li>${mdlEsc(t)}.</li>`).join("")}</ul></div>`;
}
function mdlHistoryRows(){
  const st = mdlState(), rows = [];
  Object.keys(st.history).forEach(k => {
    const e = mdlEntry(k);
    (st.history[k] || []).forEach(r => rows.push(Object.assign({ key: k, label: e ? e.label : k }, r)));
  });
  return rows.sort((a, b) => String(b.at).localeCompare(String(a.at)) || b.rev - a.rev);
}
function mdlHistoryHtml(){
  const st = mdlState();
  if (st.historyErr) return mdlSayRead("the history");
  if (!st.historyLoaded){ mdlLoadHistory(); return dpSkel(); }
  const rows = mdlHistoryRows();
  const wait = mdlPendingList().map(mdlPendingRow).join("");
  if (!rows.length) return wait + mdlQuiet("Nothing has changed yet");
  return wait + rows.map(r => `<div class="mdlhist"><span class="mdlwhen">${mdlEsc(mdlWhen(r.at))}</span><span class="mdlsays">You ${mdlEsc(r.says)}${st.key ? "" : " (" + mdlEsc(r.label) + ")"}</span>` +
    (r.class ? `<span class="mdlclass ${r.class === "widens" || r.class === "mixed" ? "wide" : ""}">${MDL_CLASS[r.class] || ""}</span>` : "") +
    mdlBtn("Restore this", `data-mdl="restore" data-mdl-key="${mdlEsc(r.key)}" data-mdl-rev="${mdlEsc(r.rev)}"`) + `</div>`).join("");
}
function mdlOpenRestore(key, rev){
  const s = { kind: "restore", key, rev: Number(rev), faults: [], busy: false, pv: { state: "checking" } };
  mdlOpenSheet(s);
  mdlRunPreview();
}
function mdlRestoreSheet(){
  const s = mdlState().sheet, pv = s.pv || {}, l = mdlLiveLine(pv);
  const e = mdlEntry(s.key);
  return mdlShell("Restore this" + (e ? " · " + e.label : ""), (pv.state === "checking" ? dpSkel() : mdlLiveBox(pv)) + mdlFaultBlock(s) +
    `<div class="o2acts2">${mdlBtn("Cancel", `data-mdl="close"`)}${mdlBtn(s.busy ? "Saving" : mdlSaveLabel(pv), `data-mdl="restorego"${s.busy || !pv.ok || pv.state === "checking" ? " disabled" : ""}`, "dpstamp")}</div>`);
}
async function mdlRestoreGo(){
  const st = mdlState(), s = st.sheet;
  if (!s || s.kind !== "restore" || s.busy) return;
  s.busy = true; mdlPaintSheet();
  const rev = (st.pages[s.key] && st.pages[s.key].rev != null) ? st.pages[s.key].rev : (st.list || {}).rev;
  const r = await mdlSend("/" + encodeURIComponent(s.key) + "/revert", { to_rev: s.rev, rev });
  if (st.sheet !== s) return;
  s.busy = false;
  if (r.faults){ s.faults = r.faults; mdlPaintSheet(); return; }
  await mdlDone(r.res, null);
}

/* Fit it to its base: the spec is saved again against the base as it is now; the server's sentences say what still does not fit */
function mdlOpenFit(){
  const st = mdlState(), p = st.pages[st.key];
  if (!p) return;
  mdlOpenSheet({ kind: "fit", key: p.key, label: p.label, spec: mdlSpecOf(p), faults: [], busy: false, pv: { state: "checking" } });
  mdlRunPreview();
}
function mdlFitSheet(){
  const s = mdlState().sheet;
  return mdlShell("Fit " + s.label + " to its base", mdlQuiet("Its base changed. Save it again against the base as it is now.") + mdlLiveBox(s.pv) + mdlFaultBlock(s) +
    `<div class="o2acts2">${mdlBtn("Cancel", `data-mdl="close"`)}${mdlBtn(s.busy ? "Saving" : mdlSaveLabel(s.pv), `id="mdl-save" data-mdl="fitgo"${mdlCanSave(s) ? "" : " disabled"}`, "dpstamp")}</div>`);
}
async function mdlFitGo(){
  const st = mdlState(), s = st.sheet, p = st.pages[st.key];
  if (!s || s.kind !== "fit" || !mdlCanSave(s) || !p) return;
  s.busy = true; mdlPaintSheet();
  const r = await mdlSend("/" + encodeURIComponent(p.key), { spec: s.spec, rev: p.rev });
  if (st.sheet !== s) return;
  s.busy = false;
  if (r.faults){ s.faults = r.faults; mdlPaintSheet(); return; }
  await mdlDone(r.res, p.key);
}

/* ── the stream: a model changed somewhere ──────────────────────────────────────────────────────────────────────────────── */
/* The `models` event: what is open is not redrawn under the owner's hands (a quiet line offers the reload); the card on Root's pane
   is refreshed. An event for a revision this screen already holds (its own write) says nothing. */
function mdlOnModelsEvent(data){
  const st = mdlState();
  const rev = data && typeof data.rev === "number" ? data.rev : null;
  if (rev !== null && rev <= st.rev) return;
  if (mdlPaneOpen()){ st.stale = true; return; }
  st.pages = {}; st.graph = null; st.historyLoaded = false;
  mdlLoad(true);
}

/* ── one delegated click handler, as data-wbtab ─────────────────────────────────────────────────────────────────────────── */
function mdlAct(ds){
  const st = mdlState(), a = ds.mdl;
  if (a === "open"){ st.view = "page"; st.key = ds.mdlKey; st.sheet = null; st.said = ""; mdlLoadPage(ds.mdlKey); mdlRender(); }
  else if (a === "back"){ st.view = "list"; st.key = null; st.sheet = null; st.said = ""; st.historyLoaded = false; mdlRender(); }
  else if (a === "reload" || a === "retry"){ st.stale = false; st.pages = {}; st.graph = null; st.historyLoaded = false; st.listErr = false; st.graphErr = false; st.historyErr = false; st.said = ""; mdlLoad(true); }
  else if (a === "all"){ st.all = true; mdlLoad(true); }
  else if (a === "add"){ if (st.list) mdlOpenAdd(ds.mdlKey || ""); }
  else if (a === "stamp" || a === "no") mdlStamp(ds.mdlId, a === "stamp");
  else if (a === "undo") mdlUndo();
  else if (a === "onoff") mdlOpenOnOff();
  else if (a === "onoffgo") mdlOnOffGo();
  else if (a === "field") mdlOpenField(ds.mdlName || "", "change");
  else if (a === "rename" || a === "retire"){
    /* from inside the change sheet, the sheet gives way to the smaller one */
    mdlOpenField(ds.mdlName || "", a);
  }
  else if (a === "rmfield"){ const s = st.sheet; if (s && s.kind === "add"){ s.fields = s.fields.filter(f => f.name !== ds.mdlName); mdlPaintSheet(); mdlSchedulePreview(); } }
  else if (a === "link") mdlOpenLink();
  else if (a === "try") mdlOpenTry("try");
  else if (a === "shape") mdlOpenTry("shape");
  else if (a === "trytab" || a === "shapetab" || a === "exampletab"){
    const s = st.sheet; if (s && s.kind === "try"){ s.tab = a.replace("tab", ""); mdlPaintSheet(); if (s.tab !== "try") mdlLoadShape(); }
  }
  else if (a === "check") mdlCheck();
  else if (a === "makeex") mdlMakeExample();
  else if (a === "copy"){ const s = st.sheet; try { if (s && s.schema && navigator.clipboard) navigator.clipboard.writeText(JSON.stringify(s.schema, null, 2)); } catch (e) {} }
  else if (a === "structure"){ st.view = "structure"; st.tab = "structure"; st.key = null; st.said = ""; mdlLoadGraph(); mdlRender(); }
  else if (a === "history"){
    if (st.view === "page") { /* the history of this model alone */ st.tab = "history"; st.view = "structure"; st.historyLoaded = false; }
    else { st.tab = "history"; st.historyLoaded = false; }
    mdlLoadHistory(true); mdlRender();
  }
  else if (a === "restore") mdlOpenRestore(ds.mdlKey, ds.mdlRev);
  else if (a === "restorego") mdlRestoreGo();
  else if (a === "newversion"){ const p = st.pages[st.key]; if (p) mdlOpenNewVersion(p); }
  else if (a === "fit") mdlOpenFit();
  else if (a === "fitgo") mdlFitGo();
  else if (a === "make") mdlMake();
  else if (a === "save") mdlSaveField();
  else if (a === "addlink") mdlAddLink();
  else if (a === "close"){
    const s = st.sheet;
    if (s && s.kind === "field" && s.back){ st.sheet = s.back; mdlPaintSheet(); }   /* a field of the draft: back to the sheet it came from */
    else mdlCloseSheet();
  }
}
/* an input on a sheet: held in the draft, never a repaint of the field the owner is typing in */
function mdlInput(t){
  const st = mdlState(), s = st.sheet, ds = (t && t.dataset) || {}, k = ds.mdlin;
  if (k === "filter"){ st.filter = t.value; const g = st.graph; const ul = typeof document !== "undefined" && document.getElementById && document.getElementById("mdl-words"); if (ul && g){ const f = t.value.toLowerCase(); ul.innerHTML = (g.text || []).filter(x => !f || x.toLowerCase().indexOf(f) >= 0).map(x => `<li>${mdlEsc(x)}.</li>`).join(""); } return; }
  if (!s || k === undefined) return;
  if (s.kind === "try" && k === "sample"){ s.sample = t.value; return; }
  if (s.kind === "add"){
    if (k === "base"){ s.base = t.value; if (/^x\./.test(t.value)) mdlLoadPage(t.value); mdlPaintSheet(); mdlSchedulePreview(); return; }
    if (k === "label"){ s.label = t.value; s.faults = []; mdlSyncAdd(); mdlSchedulePreview(); return; }
    if (k === "about"){ s.about = t.value; return; }
  }
  if (s.kind === "field" && /^f:/.test(k)){
    const prop = k.slice(2), isBox = t.type === "checkbox";
    mdlSetField(s, prop, isBox ? !!t.checked : t.value);
    s.faults = [];
    if (prop === "type") mdlPaintSheet();
    else if (t.value !== undefined && !isBox && typeof t.value === "string" && /^(max|min)/.test(prop) && s.field[prop] != null && String(s.field[prop]) !== String(t.value)) t.value = String(s.field[prop]);
    mdlSchedulePreview();
    return;
  }
  if (s.kind === "link" && /^l:/.test(k)){
    const prop = k.slice(2);
    mdlSetLink(s, prop, t.type === "checkbox" ? !!t.checked : t.value);
    s.faults = [];
    if (prop === "to" || prop === "mode" || prop === "many") mdlPaintSheet();
    mdlSchedulePreview();
  }
}
function mdlSyncAdd(){
  const s = mdlState().sheet;
  if (typeof document === "undefined" || !document.getElementById || !s) return;
  const save = document.getElementById("mdl-save");
  if (save) save.disabled = !mdlCanSave(s);
}

if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-mdl]") : null;
    if (!t) return;
    ev.preventDefault(); ev.stopPropagation();
    mdlAct(t.dataset || {});
  }, true);
  document.addEventListener("keydown", (ev) => {
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-mdl]") : null;
    if (t && t.getAttribute && t.getAttribute("role") === "link" && (ev.key === "Enter" || ev.key === " ")){ ev.preventDefault(); mdlAct(t.dataset || {}); }
  });
  /* a radio and a select speak on change, the rest while the owner types */
  document.addEventListener("input", (ev) => { const t = ev.target; if (t && t.type !== "radio" && t.tagName !== "SELECT") mdlInput(t); });
  document.addEventListener("change", (ev) => { const t = ev.target; if (t && t.dataset && t.dataset.mdlin && (t.type === "radio" || t.tagName === "SELECT")) mdlInput(t); });
}
