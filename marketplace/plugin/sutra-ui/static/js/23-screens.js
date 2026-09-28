/* 23-screens.js -- the Map and the Board, second design.

   The design of record is holding/plans/website-department/design-simplify.html
   (third pass, 2026-09-28). The founder's word on what of it is built: "Make
   changes to map, chart, and board. Do these changes." and "Rest of the
   changes, don't implement them... Don't change the navigation. Just change
   the three-screen animation." So: the Map is a fixed topology with the active
   parts lit, Root's Map is its departments as boxes, the Board is one thread
   in the chat's own markup; Chat was already the chat (22-website.js). The
   list, Work, the function cards and the engine card are 22-website.js's and
   20-dept.js's own, unchanged.

   The switch is wbV2() in 22-website.js, on unless `?screens=v1` (kept in
   localStorage). wbViewer hands the Map and the Board here when it is on;
   everything that reads a record (map, board, chat) is 22-website.js's own
   loader, so the two designs read the same record the same way.

   Copy discipline is 22-website.js's: names, never paths; no counts at rest;
   no help text on a face; one quiet line for an empty state; every class is
   prefixed `wb2` and has a rule in panel.css (test_website.js V12). */

/* ── state words, as colours ──────────────────────────────────────────────── */
function wb2Asks(m){ return (m.status && m.status.asks) || []; }
function wb2Running(m){ return ((m.status && m.status.running) || []).map(r => r.engine); }
function wb2Faults(m){ return ((m.health && m.health.checks) || []).filter(c => c.state === "block"); }
/* a function: waiting on you (an ask is Identity's, it is the one that asks), running now, quiet, or off */
function wb2FnCls(m, name){
  if (wb2Asks(m).some(a => a.engine === name || name === "Identity")) return "ask";
  if (wb2Running(m).indexOf(name) >= 0) return "run";
  const s = (m.systems || []).filter(x => x.name === name)[0];
  return s && s.state === "running" ? "" : "off";
}
function wb2EngCls(m, e){
  if (e.state === "Running" || wb2Running(m).indexOf(e.name) >= 0) return "run";
  if (e.state === "Waits" || wb2Asks(m).some(a => a.engine === e.name)) return "ask";
  if (e.last && e.last.status === "failed") return "block";
  return e.last ? "ok" : "off";
}
function wb2DotCls(cls){ return cls === "run" ? "" : (cls === "ask" ? "warn" : cls); }

/* ── the head the two screens wear ────────────────────────────────────────── */
function wb2Head(n, m){
  const st = wbS();
  const root = m.root && m.root !== n.ref && st.refs && st.refs[m.root];
  const crumb = root ? `<div class="wb2crumb"><button type="button" class="o2more wb" data-wb2go="${wbEsc(m.root)}">${wbEsc(root.name)}</button> &rsaquo; ${wbEsc(m.name)}</div>` : "";
  const sw = `<button type="button" role="switch" aria-checked="${m.stopped ? "false" : "true"}" class="wb2switch${m.stopped ? "" : " on"}" ` +
    (m.stopped ? `data-wbresume="1" title="Off. Start every engine."` : `data-wbstop="1" title="On. Stop every engine."`) + `></button>`;
  const live = m.live ? `<a class="o2more wb2live" href="${wbEsc(wbUrl(n.ref, "site/index.html"))}" target="_blank" rel="noopener">Live site</a>` : "";
  return crumb + `<div class="wb2head"><b>${wbEsc(m.name)}</b><span class="dpchk">${wbEsc(m.kind || "")}</span>${sw}${live}</div>`;
}
/* what is active now, as the design page draws it: what runs, what waits for you, how today's runs went, a fault by
   its name; nothing when nothing is. The counts here are the NOW line's own, the one place the design carries them. */
function wb2Today(m){
  const rows = ((m.health && m.health.timeline) || []).filter(r => r.started && String(r.started).slice(0, 10) === new Date().toISOString().slice(0, 10));
  return [rows.filter(r => r.status === "ok").length, rows.length];
}
function wb2NowHtml(m){
  const pills = [];
  wb2Running(m).forEach(e => pills.push(`<span class="wb2pill run">${wbEsc(e)} running</span>`));
  const asks = wb2Asks(m);
  if (asks.length) pills.push(`<span class="wb2pill ask">${asks.length} ask${asks.length > 1 ? "s" : ""} for you</span>`);
  const [ok, all] = wb2Today(m);
  if (all) pills.push(`<span class="wb2pill ok">${ok} of ${all} runs passed today</span>`);
  wb2Faults(m).forEach(c => pills.push(`<span class="wb2pill block" title="${wbEsc(c.line || "")}">${wbEsc(c.name)}</span>`));
  if (m.stopped) pills.push(`<span class="wb2pill off">Off</span>`);
  return `<div class="wb2now">${pills.join("")}</div>`;
}
/* the five functions' marks, as the design page draws them, each in a 24-unit box */
const WB2_ICONS = {
  identity: `<path d="M4 5h16v10H11l-4 4v-4H4z"/><path d="M14 19l2 2 4-4"/>`,
  adaptation: `<path d="M7 20V4M17 20V4M7 7h10M7 11h10M7 15h10"/>`,
  priority: `<path d="M4 17a8 8 0 0 1 16 0"/><path d="M12 17l4-6"/>`,
  coordination: `<circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v5M12 12l-5.5 5.5M12 12l5.5 5.5"/>`,
  audit: `<rect x="5" y="3" width="11" height="14" rx="1"/><path d="M8 7h6M8 10h6M8 13h4M15 15l4 4"/>`
};

/* ── Map: the whole topology, fixed, the active parts lit ─────────────────── */
function wb2MapHtml(n, m){
  if (m.kind === "root") return wb2RootHtml(n, m);
  const W = 960, arts = {}; (m.artifacts || []).forEach(a => { arts[a.name] = a; });
  const engs = m.engines || [];
  /* the line of work: what the first engine reads, then each engine and what it writes */
  const line = [];
  if (engs.length) line.push({ kind: "work", name: engs[0].reads });
  engs.forEach(e => { line.push({ kind: "eng", e }); line.push({ kind: "work", name: e.writes }); });
  const gap = line.length > 1 ? (W - 170) / (line.length - 1) : 0;
  const lx = i => 105 + i * gap;
  const fns = (m.systems || []).map(s => s.name);
  const fgap = fns.length > 1 ? (W - 260) / (fns.length - 1) : 0;
  const fx = i => 130 + i * fgap;
  /* what the department knows: the template it runs (the functions read, 20-dept.js), its rules, its record, its host */
  if (typeof dpLoadFunctions === "function") dpLoadFunctions(n.ref);
  const fr = (typeof dpS === "function" && dpS().functions && dpS().functions.ref === n.ref) ? dpS().functions : null;
  const picked = fr && fr.picked && (fr.picked.identity || fr.picked.adaptation);
  const filed = (m.artifacts || []).filter(a => a.versions);
  const versions = filed.reduce((s, a) => s + (a.versions || 0), 0);
  const knows = [
    ["Template", picked ? picked.name : (fr ? "Default" : ""), `data-wbfn="adaptation"`],
    ["Rules", (m.rules || []).length ? String(m.rules.length) : "none yet", `data-wbfn="identity"`],
    ["Record", filed.length ? `${filed.length} thing${filed.length > 1 ? "s" : ""}, ${versions} version${versions > 1 ? "s" : ""}` : "nothing filed", `data-wbtab="motor"`],
    ["Host", m.host || "this app's server", `data-wbfn="identity"`]];
  const kx = i => 170 + i * ((W - 340) / 3);
  const esc = wbEsc;
  let svg = `<svg viewBox="0 0 ${W} 400" role="img" aria-label="The department as a map">` +
    `<defs><marker id="sxarrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker></defs>` +
    `<text class="lbl" x="12" y="30">People</text><text class="lbl" x="12" y="118">Functions</text><text class="lbl" x="12" y="228">Work</text><text class="lbl" x="12" y="352">Knows</text>`;
  /* edges: the owner to Identity; each function to the line; the hand-offs; what the department knows to who keeps it */
  const idx = fns.indexOf("Identity");
  if (idx >= 0) svg += `<path class="e soft" d="M110 44 L${(fx(idx) - 20).toFixed(0)} 100"/>`;
  fns.forEach((f, i) => {
    const to = f === "Identity" ? 0 : (f === "Audit" ? line.length - 1 : Math.min(line.length - 1, 1 + 2 * Math.floor(i * engs.length / Math.max(1, fns.length))));
    svg += `<path class="e soft" d="M${fx(i).toFixed(0)} 152 L${lx(to).toFixed(0)} 232"/>`;
  });
  line.forEach((node, i) => {
    if (i === 0) return;
    const prev = line[i - 1];
    const hot = (node.kind === "eng" && wb2EngCls(m, node.e) === "run") || (prev.kind === "eng" && wb2EngCls(m, prev.e) === "run");
    const x1 = lx(i - 1) + (prev.kind === "eng" ? 20 : 36), x2 = lx(i) - (node.kind === "eng" ? 22 : 38);
    svg += `<path class="e${hot ? " flow" : ""}" marker-end="url(#sxarrow)" d="M${x1.toFixed(0)} 250 L${x2.toFixed(0)} 250"/>`;
  });
  knows.forEach((k, i) => { const j = k[0] === "Template" ? fns.indexOf("Adaptation") : (k[0] === "Rules" ? idx : -1);
    svg += j >= 0 ? `<path class="e soft" d="M${kx(i).toFixed(0)} 340 L${fx(j).toFixed(0)} 152"/>` : `<path class="e soft" d="M${kx(i).toFixed(0)} 340 L${lx(line.length - 1).toFixed(0)} 268"/>`; });
  /* people */
  const you = wb2Asks(m).length ? "ask" : "";
  svg += `<g class="n who ${you}" data-wbtab="chat" transform="translate(70,10)"><rect class="bx" width="80" height="34" rx="17"/><path class="ic" d="M20 25a8 8 0 0 1 16 0M28 10a4 4 0 1 1 0 8a4 4 0 1 1 0-8"/><text x="46" y="22">You</text></g>`;
  /* functions: a click opens the function's own card, as the tiles did */
  fns.forEach((f, i) => {
    const cls = wb2FnCls(m, f);
    const ic = WB2_ICONS[f.toLowerCase()] || "";
    svg += `<g class="n fn ${cls}" data-wbfn="${esc(f.toLowerCase())}" transform="translate(${(fx(i) - 70).toFixed(0)},120)"><rect class="bx" width="140" height="32" rx="8"/>` +
      (cls === "run" ? `<rect class="halo" width="140" height="32" rx="8"/>` : "") +
      (ic ? `<g class="ic" transform="translate(12,6) scale(0.85)">${ic}</g>` : "") + `<text x="${ic ? 40 : 70}" y="21"${ic ? "" : ` text-anchor="middle"`}>${esc(f)}</text></g>`;
  });
  /* the line of work: an engine opens its card, a filed thing opens itself */
  line.forEach((node, i) => {
    if (node.kind === "eng"){
      const cls = wb2EngCls(m, node.e);
      svg += `<g class="n eng ${cls}" data-wbengine="${esc(node.e.name)}" transform="translate(${lx(i).toFixed(0)},250)">` +
        (cls === "run" ? `<circle class="halo" r="17"/>` : "") + `<circle class="bx" r="17"/><text x="0" y="4" text-anchor="middle">${esc(node.e.name)}</text></g>`;
    } else {
      const a = arts[node.name] || { versions: 0, slug: "" };
      const v = a.versions ? "v" + a.versions : "";
      svg += `<g class="n work${a.versions ? " done" : ""}" ${a.versions ? `data-wbart="${esc(a.slug)}"` : `data-wbtab="motor"`} transform="translate(${(lx(i) - 34).toFixed(0)},232)">` +
        `<rect class="bx" width="68" height="36" rx="4"/><text x="8" y="17">${esc(node.name)}</text><text class="v" x="8" y="30">${esc(v)}</text></g>`;
    }
  });
  /* what the department knows */
  knows.forEach((k, i) => {
    svg += `<g class="n" ${k[2]} transform="translate(${(kx(i) - 95).toFixed(0)},340)"><rect class="bx" width="190" height="32" rx="8"/><text x="10" y="20">${esc(k[0])}</text><text class="v" x="${k[0].length * 8 + 16}" y="20">${esc(k[1])}</text></g>`;
  });
  svg += `</svg>`;
  return wb2NowHtml(m) + `<div class="wb2map wb">${svg}</div>` +
    `<div class="wb2legend"><span><i class="wb2lg fn"></i>function</span><span><i class="wb2lg eng"></i>engine</span><span><i class="wb2lg"></i>work, with its version</span>` +
    `<span><i class="wb2lg done"></i>filed and checked</span><span><i class="wb2lg run"></i>running now</span><span><i class="wb2lg ask"></i>waiting on you</span><span><i class="wb2lg block"></i>fault</span>` +
    `<span><i class="wb2lg edge"></i>hand-off</span><span><i class="wb2lg edge soft"></i>speaks to</span></div>`;
}
/* Root: the same map one level up, each department a box with its state and its line of work as a strip */
function wb2RootHtml(n, m){
  const st = wbS(), c = st.chat[n.ref];
  if (!c) wbLoadChat(n.ref);
  const depts = (c && c.departments) || [];
  const box = d => {
    const dm = st.map[d.ref];
    if (!dm) wbLoadMap(d.ref);
    const cls = !dm ? "" : (wb2Asks(dm).length ? "ask" : (wb2Running(dm).length ? "run" : (dm.stopped ? "off" : "ok")));
    const strip = dm ? (dm.artifacts || []).map(a => `<i class="${a.versions ? "on" : ""}${wb2Running(dm).indexOf(wbMakerOf(a.name)) >= 0 ? " run" : ""}" title="${wbEsc(a.name)}"></i>`).join("") : "";
    return `<button type="button" class="wb2dept wb" data-wb2go="${wbEsc(d.ref)}"><b><span class="dpdot ${wb2DotCls(cls)}"></span>${wbEsc(d.name)}</b><span class="wb2spark">${strip}</span></button>`;
  };
  const more = `<button type="button" class="wb2dept wb2new wb" data-wbtab="chat"><b>A new department</b><span class="dpchk">say what it is for, in Chat</span></button>`;
  return wb2NowHtml(m) + `<div class="wb2org wb">${depts.map(box).join("")}${more}</div>`;
}

/* ── Board: one thread, the department talking to itself ──────────────────── */
function wb2Turn(p){
  const said = p.line ? wbEsc(p.line) : wbEsc(wbCap(p.word || ""));
  const act = `<span class="dpchk">${wbEsc(WB_ACTS[p.msg_type] || p.msg_type)} · ${wbEsc(wbWhen(p.at))}</span>`;
  if (p.src === "Owner") return `<div class="turn wbturn"><div class="who who-you">You</div><div class="u md">${said}${act}</div></div>`;
  return `<div class="turn wbturn"><div class="who who-ai">${wbEsc(p.src)}</div><div class="a">${said}${act}</div></div>`;
}
function wb2BoardHtml(n, m){
  const st = wbS(), b = st.board[n.ref];
  if (!b){ wbLoadBoard(n.ref); return dpSkel(); }
  if (b.failed) return dpQuiet("Could not read");
  const posts = [];
  (b.threads || []).forEach(t => (t.posts || []).forEach(p => posts.push(p)));
  posts.sort((a, c) => a.n - c.n);
  return `<div class="wbchat wb">${posts.length ? posts.map(wb2Turn).join("") : dpQuiet("Nothing has been said yet")}</div>` +
    wbIdeasHtml(b) + wbAskBox(n.ref, "ask", "Say something on the board", "data-wbask", "Send");
}

/* ── the viewer: the Map and the Board only; null hands everything else back ── */
function wb2Viewer(n){
  const st = wbS(), m = st.map[n.ref], tab = wbTab(n.ref);
  if (!m) return null;
  const shell = (title, body) => dpViewerShell(title, wb2Head(n, m) + body, "wb wb2");
  if (tab === "map") return shell("Map", wb2MapHtml(n, m));
  if (tab === "board") return shell("Board", wb2BoardHtml(n, m));
  return null;
}

/* ── handlers of this file's own ──────────────────────────────────────────── */
if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    if (S.screen !== "org2") return;
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-wb2go]") : null;
    if (!t) return;
    const st = wbS(), ds = t.dataset || {};
    ev.preventDefault(); ev.stopPropagation();
    st.tab[ds.wb2go] = "map";
    if (typeof o2Select === "function") o2Select(ds.wb2go);
    wbLoadMap(ds.wb2go, true); dpRender();
  }, true);
}
