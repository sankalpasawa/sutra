/* ══════════════════════ screens ══════════════════════ */
const SCREENS = {};

/* ── collapsible section ──────────────────────────────────────────────────
   Panels inside the browse pane are no longer permanently fixed. Each one is
   a fold whose open/closed state is keyed and persisted, so the operator's
   layout survives a reload. The header ALWAYS carries a summary of what is
   inside (`summary`), because a collapsed section that hides its own count is
   indistinguishable from an empty one. Default is open: nothing disappears
   until the operator says so. */
function foldOpen(key, dflt){
  const v = S.ui.folds[key];
  return v === undefined ? (dflt !== false) : !!v;
}
function fold(key, title, summary, inner, dflt){
  const open = foldOpen(key, dflt);
  return `<section class="fold" data-open="${open?1:0}">
    <button class="fh" type="button" data-fold="${esc(key)}" aria-expanded="${open}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
           aria-hidden="true">${ICON.chevron}</svg>
      ${esc(title)}<span class="cv">${summary==null?"":esc(String(summary))}</span>
    </button>
    <div class="fc">${inner}</div>
  </section>`;
}

/* ── S1 Departments ── */
/* ══════════════ Directory view ══════════════
   A port of the PUBLISHED domains page — the one lib/domains_page.py generates
   for GitHub Pages — so the in-app view and the published site are the same
   document rendered twice, not two different opinions about the org.

   Structure mirrored from domains_page.py build(): a sticky TOC rail, one
   <section class="dept"> per top-level domain (chip / name / description /
   charters / child count), an org diagram, and a grid of cascading .info
   cards that recurse to any depth.

   The D-path chip uses the ENGINE's own `path` field rather than recomputing an
   index, so this view can never disagree with the rest of the panel about what
   D-number a domain has. */
function dirData(){
  const live = DOMAINS.filter(d => S.showRetired || st(d) !== "retired");
  const byRef = new Map(live.map(d => [d.ref, d]));
  const kids = new Map();
  live.forEach(d => {
    const pr = d.parent_ref;
    if (pr && byRef.has(pr)){ if (!kids.has(pr)) kids.set(pr, []); kids.get(pr).push(d); }
  });
  kids.forEach(v => v.sort((a,b) => String(a.path||"").localeCompare(String(b.path||""), undefined, {numeric:true})));
  const root = live.find(d => !d.parent_ref || !byRef.has(d.parent_ref)) || null;
  return { live, byRef, kids, root };
}

function dirChartersFor(ref){
  return CHARTERS.filter(c => c.domain_ref === ref)
    .sort((a,b) => String(a.id).localeCompare(String(b.id)));
}

/* The published chip format. The engine's domain_path() renders "D1.D1"; the
   generator's dpath_idx() renders the SAME ordinals as "D1.1"
   (domains_page.py:121). This view is the published page, so it shows the
   published spelling — a pure re-spacing of d.path, never a recomputed index,
   so it still cannot disagree with the rest of the panel about the ordinals.
   Every other view keeps the engine spelling. */
function dirChip(path){
  const parts = String(path||"").split(".");
  return parts.length < 2 ? (path||"")
    : parts[0] + "." + parts.slice(1).map(p => p.replace(/^D/, "")).join(".");
}

function dirMatches(d, q){
  if (!q) return true;
  const hay = ((d.name||"") + " " + (d.description||"") + " " + (d.path||"")).toLowerCase();
  return hay.indexOf(q) !== -1;
}

/* The Charters section, ported from domains_page.py build_site() charter_table():
   Owner / Charter / Kind / Status, owner-grouped, with the status filter bar.

   Two rules copied exactly from the generator, because they are load-bearing:
   - the filter bar renders ONLY when more than one distinct status exists
     (a one-button filter is a control that cannot change anything), and
   - the default selection is "active" when any charter is active, else "all"
     — the generator's comment is explicit that an empty first paint on a
     non-empty page is not acceptable.

   The per-child O/L lane columns are NOT ported: they exist on the published
   SITE's per-domain zoom pages, where "the children of THIS page" is defined.
   This is one page over the whole registry, so those columns have no referent
   here. Owner is shown as a real column instead. */
/* Roll a deep ref UP to the direct child of pageRef it sits under.
   Ported from domains_page.py child_of(), including its cycle guard: a
   parent_ref loop in a damaged registry must not hang the renderer. */
function dirChildOf(byRef, pageRef, ref){
  let cur = ref; const seen = new Set();
  while (byRef.has(cur) && !seen.has(cur)){
    seen.add(cur);
    const par = byRef.get(cur).parent_ref;
    if (par === pageRef) return cur;
    cur = par;
  }
  return null;
}

/* Which top-level department lanes this charter occupies, and in what role.
   Ported from cols_for(): the charter's OWN domain scores "O", every
   linked_domain_ref scores "L", both rolled up to the top-level department
   they sit under — and O outranks L when a charter both owns and links into
   the same lane. */
function dirLanesFor(byRef, pageRef, tops, c){
  const tset = new Set(tops.map(t => t.ref));
  const cols = {};
  const refs = new Set([c.domain_ref].concat(c.linked_domain_refs || []));
  refs.forEach(r => {
    if (!r || r === pageRef || !byRef.has(r)) return;
    const col = dirChildOf(byRef, pageRef, r);
    if (!col || !tset.has(col)) return;
    const role = (r === c.domain_ref) ? "O" : "L";
    if (cols[col] !== "O") cols[col] = role;
  });
  return cols;
}

function dirCharterSection(byRef, kids, root){
  const q = (S.dirQ || "").trim().toLowerCase();
  const all = CHARTERS.slice();
  if (!all.length) return `<section class="chsec"><h2 class="chh">Charters</h2>
    <p class="chempty">none yet</p></section>`;

  const ownerName = c => (byRef.get(c.domain_ref) || {}).name || "—";
  const ownerPath = c => (byRef.get(c.domain_ref) || {}).path || "";
  const statuses = [...new Set(all.map(c => c.status).filter(Boolean))].sort();
  const deffil = all.some(c => c.status === "active") ? "active" : "all";
  const cur = S.dirSt || deffil;

  /* The lanes are the TOP-LEVEL departments, i.e. this page is the root's
     charter table. show only when at least one charter actually lands in one,
     matching the generator's `show_cols` guard. */
  const pageRef = root ? root.ref : null;
  const tops = (kids.get(pageRef) || []);
  const laneOf = new Map(all.map(c => [c.id, dirLanesFor(byRef, pageRef, tops, c)]));
  const showCols = tops.length > 0 && all.some(c => Object.keys(laneOf.get(c.id)||{}).length);

  const rows = all
    .filter(c => cur === "all" || c.status === cur)
    .filter(c => !q || ((c.title||"") + " " + (c.purpose||"") + " " + ownerName(c))
                        .toLowerCase().indexOf(q) !== -1)
    .sort((a,b) =>
      ownerName(a).toLowerCase().localeCompare(ownerName(b).toLowerCase())
      || ((a.kind==="standing"?0:1) - (b.kind==="standing"?0:1))
      || String(a.title||"").toLowerCase().localeCompare(String(b.title||"").toLowerCase()));

  let prevOwner = null;
  const body = rows.map(c => {
    const first = c.domain_ref !== prevOwner;
    prevOwner = c.domain_ref;
    /* the owner cell is ALWAYS present so a screen reader hears it on every
       row; a repeat is hidden visually only (the generator's note) */
    const lanes = laneOf.get(c.id) || {};
    const laneCells = showCols ? tops.map(t => {
      const m = lanes[t.ref];
      if (m === "O") return `<td class="lo" title="owner: ${esc(t.name)}">O</td>`;
      if (m === "L") return `<td class="ll" title="linked: ${esc(t.name)}">L</td>`;
      return `<td class="ln"></td>`;
    }).join("") : "";
    /* The published row is ONE line: owner, title, kind, status, lanes. The
       purpose is a TOOLTIP, never a visible block -- a version of this that
       rendered it inline made every row three lines tall and pushed the text
       out over the lane columns, because a <th> with a max-width inside a
       width:100% table overflows rather than wraps. Owner is the bare name
       (or "here" for a charter the page itself owns), as the generator has it;
       the D-path lives in the rail and the section headers. */
    const ownHere = root && c.domain_ref === root.ref;
    return `<tr class="chtr${first?" obreak":""}" data-status="${esc(c.status||"")}">
      <td class="cown"><span class="ctxt${first?"":" ohide"}">${ownHere
        ? `<span class="cown-here" aria-label="Owned by this department">here</span>`
        : esc(ownerName(c))}</span></td>
      <th scope="row"><span class="cht" title="${esc(c.purpose||"")}">${esc(c.title||"")}</span></th>
      <td class="ckind">${esc(c.kind||"")}</td>
      <td><span class="chdot st-${esc(c.status||"")}"><i></i>${esc(c.status||"")}</span></td>
      ${laneCells}</tr>`;
  }).join("");

  /* The generator hides this bar below two distinct statuses. Here it is
     ALWAYS shown (founder direction): the panel is a live tool, and a control
     that disappears depending on the data reads as a missing feature. */
  const fil = `<div class="chfil">${["all"].concat(statuses).map(st_ =>
      `<button type="button" data-chst="${esc(st_)}" aria-pressed="${cur===st_}">${esc(st_)}</button>`
    ).join("")}</div>`;
  const laneHead = showCols
    ? tops.map(t=>`<th scope="col" class="lane" title="${esc(t.name)}">${esc(dirChip(t.path)||t.name)}</th>`).join("")
    : "";
  const legend = showCols ? `<p class="lanenote">O owner &middot; L linked</p>` : "";
  const ncols = 4 + (showCols ? tops.length : 0);

  return `<section class="chsec"><h2 class="chh">Charters</h2>${legend}${fil}
    <div class="lanewrap"><table class="chtab lanetab" data-deffil="${esc(deffil)}">
      <thead><tr><th scope="col">Owner</th><th scope="col">Charter</th>
        <th scope="col">Kind</th><th scope="col">Status</th>${laneHead}</tr></thead>
      <tbody>${body || `<tr class="chnone"><td colspan="${ncols}">no charters match</td></tr>`}</tbody>
    </table></div></section>`;
}

function domainsDirectory(){
  const { byRef, kids, root } = dirData();
  if (!root) return `<div class="zero"><h4>No domains</h4>
    <p>This registry has no domains yet. One is minted the first time work is placed.</p></div>`;
  const q = (S.dirQ || "").trim().toLowerCase();

  const charterLines = ref => dirChartersFor(ref).map(c =>
    `<p class="charter"><span>Charter</span> ${esc(c.title||"")}${
      c.purpose ? " — " + esc(c.purpose) : ""}</p>`).join("");

  const orgDiagram = (parentName, childNames) => !childNames.length ? "" :
    `<div class="dtree"><div class="tnode troot">${esc(parentName)}</div>
      <div class="tdown"></div>
      <div class="tkids">${childNames.map(n=>`<div class="tnode">${esc(n)}</div>`).join("")}</div></div>`;

  /* a subtree survives the filter if IT matches or any descendant does --
     hiding a matching child because its parent did not match would make the
     search look broken */
  const subtreeMatches = d => dirMatches(d, q)
    || (kids.get(d.ref)||[]).some(subtreeMatches);

  const navEntry = (d, depth) => {
    const ch = (kids.get(d.ref)||[]).filter(subtreeMatches);
    const anchor = "dir-" + d.ref;
    if (ch.length) return `<details class="navgrp"${depth<2?" open":""}>
      <summary><span class="chip">${esc(dirChip(d.path))}</span>
        <a href="#${anchor}">${esc(d.name)}</a>
        <span class="navcount">${(kids.get(d.ref)||[]).length}</span></summary>
      <div class="navkids">${ch.map(c=>navEntry(c, depth+1)).join("")}</div></details>`;
    return `<a class="dsub" href="#${anchor}"><span class="chip">${esc(dirChip(d.path))}</span>${esc(d.name)}</a>`;
  };

  const nodeBlock = (d, depth) => {
    const all = kids.get(d.ref)||[];
    const ch = all.filter(subtreeMatches);
    let body = `<span class="chip">${esc(dirChip(d.path))}</span><b>${esc(d.name)}</b>
      ${d.description?`<p>${esc(d.description)}</p>`:""}${charterLines(d.ref)}`;
    if (ch.length){
      body += `<details class="cascade"${depth<2?" open":""}>
        <summary>${all.length} sub-domain${all.length===1?"":"s"}</summary>
        ${orgDiagram(d.name, all.map(c=>c.name))}
        <div class="grid">${ch.map(c=>nodeBlock(c, depth+1)).join("")}</div></details>`;
    }
    return `<div class="info" id="dir-${esc(d.ref)}">${body}</div>`;
  };

  const tops = (kids.get(root.ref)||[]).filter(subtreeMatches);
  const rail = tops.map(t=>navEntry(t,1)).join("")
    || `<p style="color:var(--faint);font-size:11.5px;padding:4px 6px">no match</p>`;

  const sections = tops.map(t=>{
    const all = kids.get(t.ref)||[];
    const ch = all.filter(subtreeMatches);
    const blocks = ch.length
      ? ch.map(c=>nodeBlock(c,2)).join("")
      : `<div class="info empty">no sub-departments yet</div>`;
    return `<section id="dir-${esc(t.ref)}" class="dept">
      <header><span class="chip big">${esc(dirChip(t.path))}</span>
        <div><h2>${esc(t.name)}</h2>
          ${t.description?`<p class="desc">${esc(t.description)}</p>`:""}
          ${charterLines(t.ref)}</div>
        <span class="count">${all.length}</span></header>
      ${orgDiagram(t.name, all.map(c=>c.name))}
      <div class="grid">${blocks}</div></section>`;
  }).join("") || `<div class="info empty">no departments under ${esc(root.name)} yet</div>`;

  return `<div class="dpage">
    <nav>
      <input class="dq" id="dirQ" type="search" placeholder="Search domains…"
             autocomplete="off" value="${esc(S.dirQ||"")}">
      ${rail}
    </nav>
    <main>
      <div class="dhead"><h1>${esc(root.name)}</h1></div>
      ${root.description?`<p class="rootdesc">${esc(root.description)}</p>`:""}
      ${charterLines(root.ref)}
      ${orgDiagram(root.name, (kids.get(root.ref)||[]).map(c=>c.name))}
      ${sections}
      ${dirCharterSection(byRef, kids, root)}
    </main></div>`;
}

SCREENS.departments = () => {
  const vis = DOMAINS.filter(d=>S.showRetired || isLive(d));
  const roots = vis.filter(d=>!d.parent_ref || !vis.find(p=>p.ref===d.parent_ref));
  const kids = ref => vis.filter(d=>d.parent_ref===ref)
                         .sort((a,b)=>a.ts_minted_ms-b.ts_minted_ms);
  const draft = S.view==="draft";

  /* turn counts per department, so a node shows how much has actually been filed here */
  const turnsOn = ref => S.sessions.reduce((n,s)=>
    n + s.turns.filter(x=>x.domain && x.domain.ref===ref).length, 0);

  const subtreeN = r => kids(r).reduce((a,c)=>a+1+subtreeN(c.ref),0);
  const card = d => {
    const cs = chartersOf(d.ref).filter(c=>c.status!=="retired");
    const ret = st(d)==="retired";
    const n = turnsOn(d.ref);
    /* collapsed subtree count lives on the tile — nothing disappears silently */
    const hidden = (kids(d.ref).length && S.collapsed.has(d.ref)) ? subtreeN(d.ref) : 0;
    return `<button class="ocard ${ret?"retired":""}" data-ref="${d.ref}"
        data-kids="${kids(d.ref).length?1:0}"
        ${draft && !ret ? 'draggable="true"' : ''} aria-selected="${S.sel===d.ref}">
      ${n?`<span class="turnbadge">${n}</span>`:""}
      <span class="odp">${esc(dPath(d.ref))}</span>
      <span class="onm">${esc(d.name)}</span>
      <span class="ometa">
        <span>${cs.length?cs.length+" chr":'<span style="color:var(--warn)">no charter</span>'}</span>
        <span>${placementsOf(d.ref).length} plc</span>
        ${ret?'<span style="color:var(--block)">retired</span>':""}
        ${hidden?`<span class="below">${hidden} below</span>`:""}
      </span>
    </button>`;
  };
  /* expandable: a node with children carries a +/− control; collapsed subtrees are
     summarised on the control so nothing disappears silently */
  const branch = d => {
    const ks = kids(d.ref);
    const open = ks.length && !S.collapsed.has(d.ref);
    return `<li class="${open?"haskids":""}">
      ${card(d)}
      ${open?`<ul>${ks.map(branch).join("")}</ul>`:""}
    </li>`;
  };

  const sel = S.sel && byRef(S.sel);
  let insp = `<div class="insp"><div class="zero" style="padding:20px 8px">
      <p>Select a department to inspect it.</p></div></div>`;
  if (sel){
    const cs = chartersOf(sel.ref), ps = placementsOf(sel.ref);
    const open = ps.filter(p=>p.phase==="open");
    const oldest = open.length ? Math.min(...open.map(p=>p.ts_ms)) : null;
    const succ = (sel.successor_refs||[]).map(r=>byRef(r)).filter(Boolean);
    insp = `<div class="insp">
      <h4>${esc(sel.name)}</h4>
      <div class="sub">${esc(dPath(sel.ref))} · ${esc(sel.ref)}</div>
      ${sel.description?`<p style="font-size:11.5px">${esc(sel.description)}</p>`:
        `<p style="font-size:11.5px;color:var(--faint)">No description — system-minted nodes carry none.</p>`}
      <div class="kv"><b>Status</b><span>${esc(st(sel))}${sel.retired_at_ms?" · "+fmt(sel.retired_at_ms):""}</span></div>
      <div class="kv"><b>Charters</b><span>${cs.length||"none"}</span></div>
      <div class="kv"><b>Placements</b><span class="num">${ps.length}</span></div>
      ${succ.length?`<div class="kv"><b>Succeeded by</b><span>${succ.map(s=>esc(s.name)).join(" · ")}</span></div>`:""}
      ${sel.retire_reason_code?`<div class="kv"><b>Reason</b><span>${esc(sel.retire_reason_code)} <span class="pill p-mut">private</span></span></div>`:""}
      <h3 class="sec" style="margin:13px 0 7px">Currently</h3>
      ${open.length? `<p style="font-size:11.5px;margin:0">${open.length} open work unit${open.length>1?"s":""}${oldest?`, oldest opened ${fmt(oldest)}`:""}.</p>`
                   : `<p style="font-size:11.5px;margin:0;color:var(--faint)">Nothing open.</p>`}
      ${cs.length? `<h3 class="sec" style="margin:13px 0 7px">Charters</h3>` +
        cs.map(c=>`<div class="kv"><b>${esc(c.kind)}</b><span>${esc(c.title)}
          ${isSuperseded(c)?'<span class="pill p-mut">superseded</span>':""}</span></div>`).join("")
        : `<h3 class="sec" style="margin:13px 0 7px">Charters</h3>
           <p style="font-size:11.5px;color:var(--warn);margin:0">No charter yet — this department
           can be routed to, but nothing frames what it owns.</p>`}
    </div>`;
  }

  const sim = simulate(S.draft.ops);
  return `
    <div class="facets">
      <span class="fl">View</span>
      <span class="seg">
        <button type="button" data-view="live"  aria-pressed="${S.view==="live"}">Live</button>
        <button type="button" data-view="draft" aria-pressed="${draft}">Draft${S.draft.ops.length?` · ${S.draft.ops.length}`:""}</button>
        <button type="button" data-view="dir"   aria-pressed="${S.view==="dir"}"
                title="The published domains page layout, over this registry">Directory</button>
      </span>
${DOMAINS.some(d=>st(d)==="retired")
        ? `<button class="btn" data-toggle="showRetired" aria-pressed="${S.showRetired}">Show retired</button>` : ""}
    </div>
    ${S.view==="dir" ? domainsDirectory() : `
    ${draft?`<div class="note w"><b>Draft — nothing on this canvas touches the registry.</b>
       Drag a department onto another to compose a MOVE. Every other operation is a checklist,
       and there is no Apply button in this tier.</div>`:""}
    <div class="cols">
      <div>
        ${fold("dept.chart", "Org chart",
          `${vis.length} shown · ${S.collapsed.size} subtree${S.collapsed.size===1?"":"s"} collapsed`, `
          <div class="canvas ${draft?"draft":""}">
            <div class="chartwrap">
              <ul class="chart">${roots.map(branch).join("")}</ul>
            </div>
          </div>
          <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
            <button class="btn" data-expall="1">Expand all</button>
            <button class="btn" data-collall="1">Collapse to top level</button>
            <span style="font-size:10.5px;color:var(--faint);align-self:center">
              a badge on a node counts turns filed there</span>
          </div>
          ${draft?`<div class="legend">A ring means <b style="color:var(--block)">blocked</b>.
            The absence of a ring is not a promise — ORG-001/002/004/009 are not evaluated per hover,
            and ORG-005/012/019 cannot be evaluated at all. D-paths are greyed during a drag and
            <b>recomputed at apply</b>. Sibling gaps and whitespace are not drop targets.
            <span id="dragStatus"></span></div>`:""}`)}
        <div class="note"><b>Note.</b> This registry has no
          <code>D0.design</code>, so its published site would render in the generator's
          <code>NEUTRAL</code> fallback — accent <code>#1d4ed8</code>, blue — while this shell is bronze.
          Sutra's own published pages are not Sutra-branded until the tokens are written to D0.</div>
      </div>
      <div>
        ${fold("dept.insp", "Inspector", sel ? dPath(sel.ref) + " " + sel.name : "nothing selected", insp)}
        ${fold("dept.metrics", "Metrics", null, `
          <div class="metrics" style="margin:0">
            <div>live<b>${live().length}</b></div>
            <div>retired<b>${DOMAINS.filter(d=>!isLive(d)).length}</b></div>
            <div>max depth<b>${simNum(sim, sim.maxDepth)}</b></div>
            <div>findings<b>${simNum(sim, sim.findings.length)}</b></div>
          </div>`)}
      </div>
    </div>`}`;
};

/* ── S2 Charters ── */
SCREENS.charters = () => {
  const kinds = [...new Set(CHARTERS.map(c=>c.kind))];
  const stats = [...new Set(CHARTERS.map(c=>c.status))];
  let rows = CHARTERS.filter(c=>{
    if (S.cf.kind.size && !S.cf.kind.has(c.kind)) return false;
    if (S.cf.status.size && !S.cf.status.has(c.status)) return false;
    if (S.q && !(c.title+" "+c.purpose).toLowerCase().includes(S.q.toLowerCase())) return false;
    return true;
  });
  const col = S.sort.col, dir = S.sort.dir;
  rows.sort((a,b)=>{
    const v = x => col==="fresh" ? (lastRouted(x.id)||0)
              : col==="owner" ? (byRef(x.domain_ref)?dPath(x.domain_ref):"")
              : String(x[col]||"");
    const A=v(a),B=v(b); return (A>B?1:A<B?-1:0)*dir;
  });
  const sel = S.selCharter && CHARTERS.find(c=>c.id===S.selCharter);
  const fbtn = (g,v)=>`<button class="btn" data-facet="${g}" data-val="${v}"
      aria-pressed="${S.cf[g].has(v)}">${esc(v)}</button>`;
  const th = (k,l)=>`<th data-sort="${k}">${l}${col===k?(dir>0?" ▲":" ▼"):""}</th>`;

  let prev = `<div class="insp"><div class="zero" style="padding:20px 8px"><p>Select a charter.</p></div></div>`;
  if (sel){
    const owner = byRef(sel.domain_ref), lr = lastRouted(sel.id), b = band(lr);
    const ps = PLACEMENTS.filter(p=>p.charter_id===sel.id);
    prev = `<div class="insp">
      <h4>${esc(sel.title)}</h4><div class="sub">${esc(sel.id)}</div>
      <p style="font-size:11.5px">${esc(sel.purpose)}</p>
      <div class="kv"><b>Owner</b><span>${owner?esc(dPath(owner.ref)+" "+owner.name):"—"}
        ${owner&&st(owner)==="retired"?'<span class="pill p-block">tombstone</span>':""}</span></div>
      <div class="kv"><b>Kind</b><span>${esc(sel.kind)} · ${esc(sel.status)}</span></div>
      <div class="kv"><b>Freshness</b><span><span class="pill ${b.cls}">${b.txt}</span></span></div>
      <div class="kv"><b>Superseded</b><span>${isSuperseded(sel)?"yes — derived from edges":"no"}</span></div>
      <div class="kv"><b>Routed</b><span class="num">${ps.length}</span></div>
      ${sel.scope_in&&sel.scope_in.length?`<h3 class="sec" style="margin:13px 0 6px">Scope in</h3>
        <p style="font-size:11.5px;margin:0">${sel.scope_in.map(esc).join(" · ")}</p>`:""}
      ${sel.scope_out&&sel.scope_out.length?`<h3 class="sec" style="margin:11px 0 6px">Out of scope</h3>
        <p style="font-size:11.5px;margin:0">${sel.scope_out.map(esc).join(" · ")}</p>`:""}
      <div class="legend">Freshness is derived at render from <code>max(placement.ts_ms)</code>.
        It is never stored — <code>last_routed_ms</code> has no writer.</div>
    </div>`;
  }
  return `
    <div class="facets">
      <span class="fl">Kind</span>${kinds.map(k=>fbtn("kind",k)).join("")}
      <span class="fl" style="margin-left:8px">Status</span>${stats.map(s=>fbtn("status",s)).join("")}
      <input type="search" id="q" placeholder="Search title and purpose…" value="${esc(S.q)}" style="margin-left:auto;width:210px">
    </div>
    <div class="cols"><div>
      ${fold("chart.table", "Charters", `${rows.length} of ${CHARTERS.length}`, `
      <div class="tw"><table><thead><tr>
        ${th("title","Charter")}${th("kind","Kind")}${th("status","Status")}${th("owner","Owner")}${th("fresh","Freshness")}
      </tr></thead><tbody>
      ${rows.length? rows.map(c=>{
        const o = byRef(c.domain_ref), b = band(lastRouted(c.id));
        return `<tr data-charter="${c.id}" class="${S.selCharter===c.id?"sel":""}">
          <td class="k">${esc(c.title)}${isSuperseded(c)?' <span class="pill p-mut">superseded</span>':""}</td>
          <td>${esc(c.kind)}</td>
          <td><span class="pill ${c.status==="active"?"p-ok":"p-mut"}">${esc(c.status)}</span></td>
          <td>${o?esc(dPath(o.ref)+" "+o.name):"—"}${o&&st(o)==="retired"?' <span class="pill p-block">tombstone</span>':""}</td>
          <td><span class="pill ${b.cls}">${b.txt}</span></td></tr>`;}).join("")
        : `<tr><td colspan="5"><div class="zero"><h4>No charter matches</h4>
             <p>Clear a filter to widen the search. The facet rail never disappears.</p></div></td></tr>`}
      </tbody></table></div>
      <p style="margin:9px 0 0;font-size:11px;color:var(--faint)">${rows.length} of ${CHARTERS.length}</p>`)}
    </div><div>${fold("chart.prev", "Preview", sel ? sel.title : "nothing selected", prev)}</div></div>`;
};

/* ── S3 Placements ── */
SCREENS.placements = () => {
  const modes = ["all","match","floor"];
  let rows = PLACEMENTS.filter(p=>S.pmode==="all"||p.mode===S.pmode);
  rows = rows.slice().sort((a,b)=>b.ts_ms-a.ts_ms);
  const held = PLACEMENTS.filter(p=>p.mode==="floor");
  return `
    <div class="facets">
      <span class="fl">Mode</span>
      <span class="seg">${modes.map(m=>`<button type="button" data-pmode="${m}" aria-pressed="${S.pmode===m}">${m}</button>`).join("")}</span>
    </div>
    ${held.length?`<div class="note w"><b>${held.length} held at ancestor.</b>
      These resolved below the ${CONFIDENCE_FLOOR} confidence floor, so the engine held them at the
      nearest live ancestor rather than guessing. They are not "unrouted" — that value has no writer.
      A run of these is the signal that the org is missing a department.</div>`:""}
    <div class="tw"><table><thead><tr>
      <th>Work</th><th>Filed to</th><th>Charter</th><th>Confidence</th><th>Mode</th><th>When</th>
    </tr></thead><tbody>
    ${rows.map(p=>{
      const d = byRef(p.domain_ref); const floor = p.mode==="floor";
      return `<tr>
        <td class="k">${esc(p.work_ref.id)}</td>
        <td>${d?esc(dPath(d.ref)+" "+d.name):'<span class="pill p-block">unresolvable</span>'}</td>
        <td>${esc(p.charter_id||"—")}</td>
        <td class="num">${p.confidence.toFixed(2)}
          ${floor?'<span class="pill p-warn">held</span>':""}</td>
        <td>${esc(p.mode)}</td>
        <td class="num">${fmt(p.ts_ms)}</td></tr>`;}).join("")}
    </tbody></table></div>
    <div class="note" style="margin-top:12px"><b>Why an unfiled queue can exist at all.</b>
      <code>write_placement</code> rejects a null <code>charter_id</code>, so a floor placement is only
      recordable because the root holds a charter. A registry whose root has no charter cannot record
      one at all.</div>`;
};

/* ── S4 Knowledge (disabled) ── */
SCREENS.knowledge = () => {
  const r = S.searchRes;
  const body = !S.sq
    ? `<div class="zero"><h4>Search the registry</h4>
        <p>Departments, charters and filed work. Matches on names, descriptions,
        routing evidence, charter purpose and scope, and work paths — and tells you
        which field hit, so a result is explainable rather than an opaque rank.</p></div>`
    : S.searchBusy && !r
      ? `<p style="color:var(--muted)">Searching…</p>`
      : (!r || !r.results.length)
        ? `<div class="zero"><h4>No matches for “${esc(S.sq)}”</h4>
            <p>Nothing in the registry contains that term.</p></div>`
        : `<div class="facets">${Object.entries(r.counts).map(([k,n])=>
             `<span class="pill p-acc">${esc(k)} ${n}</span>`).join(" ")}
             ${r.truncated?`<span class="pill p-warn">showing first ${r.results.length}</span>`:""}</div>
           <div class="tw"><table><thead><tr>
             <th>Kind</th><th>Result</th><th>Matched on</th><th>Detail</th>
           </tr></thead><tbody>
           ${r.results.map(x=>`<tr ${x.kind==="domain"?`data-goto-domain="${esc(x.ref)}"`:""}
               style="${x.kind==="domain"?"cursor:pointer":""}">
             <td><span class="pill ${x.kind==="domain"?"p-acc":x.kind==="charter"?"p-ok":"p-mut"}">${esc(x.kind)}</span></td>
             <td class="k">${esc(x.path?x.path+" ":"")}${esc(x.title||"")}
               ${x.owner_retired?'<span class="pill p-block">tombstone</span>':""}
               ${x.status==="retired"?'<span class="pill p-block">retired</span>':""}</td>
             <td>${(x.matched_on||[]).map(f=>`<code>${esc(f)}</code>`).join(" ")}</td>
             <td>${esc((x.subtitle||"").slice(0,90))}</td></tr>`).join("")}
           </tbody></table></div>`;
  return `
    <div class="facets">
      <input type="search" id="sq" placeholder="Search departments, charters, filed work…"
             value="${esc(S.sq)}" style="width:100%;max-width:460px">
    </div>
    ${body}`;
};

/* ── S5 Reorg ── */
SCREENS.reorg = () => {
  const sim = simulate(S.draft.ops);
  const base = simulate([]);
  const blocking = sim.findings.filter(f=>f.sev==="block");
  const warns = sim.findings.filter(f=>f.sev==="warn");
  const ops = S.draft.ops;
  /* Either half of this screen can be un-answered: the draft simulation and
     the base simulation are two separate round trips. If either is pending or
     failed, every derived number on the strip is unknown — say so. */
  const pend = sim.pending || base.pending;
  const err  = sim.error || base.error;
  const n = v => (pend || err) ? "—" : v;
  return `
    <div class="facets">
      <span class="fl">Plan</span><code>${esc(PLANS[0].plan_id)}</code>
      <span class="pill p-mut">plan_origin: studio-drag</span>
      <span class="pill p-mut">validated_at_ms: null</span>
      <button class="btn" id="rebase" ${S.drift?"":"disabled"}>Rebase draft</button>
      <button class="btn" id="discard">Discard draft</button>
    </div>
    ${S.drift?`<div class="note b"><b>Registry changed since this draft captured its base.</b>
      1 event appended. <code>ORG-010</code> will block at apply. Rebasing re-captures the base and
      re-probes every op — the studio never silently refreshes it.</div>`:""}
    <div class="cols"><div>
      <h3 class="sec">Diff rail</h3>
      <div class="tw diff">
        ${ops.length? ops.map((o,i)=>{
          const s=byRef(o.ref), t=byRef(o.target);
          return `<div class="r"><span class="op">MOVE</span>
            <b style="color:var(--ink)">${esc(s?s.name:o.ref)}</b>
            <span>→ ${esc(t?t.name:o.target)}</span>
            <button class="btn" data-revert="${i}" style="margin-left:auto;padding:3px 7px">revert</button></div>`;
        }).join("")
        : `<div class="zero" style="padding:26px 12px"><h4>No operations yet</h4>
             <p>Switch Departments to <b>Draft</b> and drag a department onto a new parent.
             MOVE is the only gesture — every other operation needs per-item disposition a drop
             cannot carry.</p></div>`}
      </div>
      <div class="metrics">
        <div class="${!pend && !err && sim.domains2.filter(isLive).length!==base.domains2.filter(isLive).length?"chg":""}">departments<b>${n(base.domains2.filter(isLive).length)} <span class="ar">→</span> ${n(sim.domains2.filter(isLive).length)}</b></div>
        <div class="${!pend && !err && sim.findings.filter(f=>f.code==="ORG-001").length!==base.findings.filter(f=>f.code==="ORG-001").length?"chg":""}">overlaps<b>${n(base.findings.filter(f=>f.code==="ORG-001").length)} <span class="ar">→</span> ${n(sim.findings.filter(f=>f.code==="ORG-001").length)}</b></div>
        <div class="${!pend && !err && sim.maxDepth!==base.maxDepth?"chg":""}">max depth<b>${n(base.maxDepth)} <span class="ar">→</span> ${n(sim.maxDepth)}</b></div>
        <div>charters<b>${CHARTERS.length} <span class="ar">→</span> ${CHARTERS.length}</b></div>
      </div>
      <div class="findbar">
        ${err ? `<span style="color:var(--block)">✗ validation failed</span>`
          : pend ? `<span style="color:var(--muted)">checking…</span>`
          : `<span style="color:var(--block)">✗ ${blocking.length} blocking</span>
             <span style="color:var(--warn)">⚠ ${warns.length} warning</span>`}
        <span style="color:var(--muted)">${ops.length} changes</span>
      </div>
      <h3 class="sec" style="margin-top:14px">Rationale</h3>
      <input type="text" id="rat" placeholder="Required — becomes the changelog message"
             value="${esc(S.draft.rationale)}" style="width:100%">
      ${!S.draft.rationale && ops.length?`<p style="color:var(--block);font-size:11px;margin-top:6px">
        A rationale is required before this plan is complete.</p>`:""}
      <h3 class="sec" style="margin-top:14px">Effective</h3>
      <p style="font-size:11.5px">now (immediate) — <span class="pill p-mut">label, not a control</span>
        There is no scheduler: a Claude Code plugin has no daemon, and a back- or forward-dated stamp
        would corrupt the monotonic ordering replay depends on.</p>
      <h3 class="sec" style="margin-top:14px">There is no Apply button in this tier</h3>
      <p style="font-size:11.5px">Not disabled, not behind a confirm — absent. <code>org apply</code>
        is the only authority and it re-validates against freshly loaded state inside the RESTRUCTURE
        flock. The hazard is staleness: the tree gains system-minted siblings while you drag.</p>
      <div class="cmd"><span class="p">$</span><span class="t">placement_engine.py org plan --import ~/.sutra-ui/drafts/${esc(PLANS[0].plan_id)}.json</span>
        <button class="btn" id="copyCmd" style="padding:3px 8px">copy</button></div>
    </div><div>
      <h3 class="sec">Findings</h3>
      ${err? `<div class="note b"><b>Validation could not run.</b> ${esc(err)}<br>
        This list is empty because nothing was checked — not because nothing was found.
        Reload once the backend is answering.</div>`
      : pend? `<p style="color:var(--muted)">Checking… the validation pass is running
        server-side against a fresh read of the registry. No count until it answers.</p>`
      : sim.findings.length? sim.findings.map(f=>`
        <details class="code"><summary>
          <span class="cid" style="color:var(--${f.sev==="block"?"block":"warn"})">${f.code}</span>
          <span class="pill ${f.sev==="block"?"p-block":"p-warn"}">${f.sev}</span>
          <span style="color:var(--muted);overflow:hidden;text-overflow:ellipsis">${esc(f.subject)}</span>
        </summary><div class="in">${esc(f.subject)}</div></details>`).join("")
      : `<p style="color:var(--muted)">Nothing flagged on the current tree.</p>`}
      <div class="legend">All predicates live in one <code>simulate()</code>. Rings, the metric strip,
        Health and this list read the same <code>findings[]</code>.<br><br>
        Validation runs <b>server-side</b>: <code>POST /api/org/simulate</code> calls
        <code>reorg_sim.simulate()</code>, which reads the registry through the same
        <code>placement_engine</code> functions the CLI uses. Zero rules live in JS — the
        browser renders <code>findings[]</code>, it does not compute them.</div>
    </div></div>`;
};

/* ── S6 History ── */
SCREENS.history = () => {
  const rows = INDEX.slice().sort((a,b)=>b.ts_ms-a.ts_ms);
  const label = e => e.event==="domain_minted" ? `Minted ${e.name||e.ref.slice(0,12)}`
    : e.op==="retire" ? `Retired ${(e.before&&e.before.name)||e.ref.slice(0,12)}`
    : e.op==="rename" ? `Renamed ${e.ref.slice(0,12)}…`
    : `${e.op||e.event} ${e.ref?e.ref.slice(0,12)+"…":""}`;
  if (!rows.length) return `<div class="zero"><h4>No history yet</h4>
    <p>Nothing has been minted, renamed, moved or retired in this registry.
    <code>domains/INDEX.jsonl</code> is empty.</p></div>`;
  return `
    <ul class="tl">
      ${rows.map(e=>{
        const legacy = e.event==="domain_restructured" && !e.before;
        return `<li class="${legacy?"legacy":""}">
          <div class="when">${fmt(e.ts_ms)}${e.reorg_id?" · "+esc(e.reorg_id):""}</div>
          <div class="what">${esc(label(e))}</div>
          ${legacy?`<div class="det" style="color:var(--faint)">Legacy row — records that a change
            happened, not what it changed from. Enriched events carry before/after.</div>`:""}
          ${e.before&&e.after?`<div class="det">${esc(e.before.name)} → ${esc(e.after.name||e.before.name)}
            ${e.placements_repointed?` · ${e.placements_repointed} placement(s) repointed`:""}</div>`:""}
        </li>`;}).join("")}
    </ul>
    <div class="sepiaband">
      ${META.history_complete_from_ms
        ? `<b style="font-size:11.5px">Reconstructed before ${fmt(META.history_complete_from_ms)}.</b>
           <p style="margin:5px 0 0;font-size:11px">Rows prior to this date record that a change
           happened but not what it changed from. An as-of view before this date exits 2 rather
           than guessing — and as-of is private-report only.
           ${META.legacy_events?`<br>${META.legacy_events} legacy row(s) below the line.`:""}</p>`
        : `<b style="font-size:11.5px">No reconstructable history yet.</b>
           <p style="margin:5px 0 0;font-size:11px">Not one event carries a before/after snapshot,
           so nothing here can be replayed to reconstruct prior state — every row records only
           <i>that</i> something changed. An as-of view would exit 2 at any date.</p>`}
      <p style="margin:6px 0 0;font-size:10.5px;color:var(--faint)">This boundary is
      <b>derived</b> at read time from the earliest enriched event — it is not a stored
      field, because the engine has no such field to store.</p>
    </div>`;
};

/* ── S7 Health ── */
SCREENS.health = () => {
  const sim = simulate(S.draft.ops);
  const groups = {};
  sim.findings.forEach(f=>(groups[f.code]=groups[f.code]||[]).push(f));
  const held = PLACEMENTS.filter(p=>p.mode==="floor").length;
  return `
    <h3 class="sec">Evaluated</h3>
    ${sim.error? `<div class="note b"><b>Validation could not run.</b> ${esc(sim.error)}<br>
      Nothing below this line was evaluated. An empty findings list here is the
      absence of an answer, not a clean bill of health.</div>`
     : sim.pending? `<p style="color:var(--muted)">Checking… the validation pass is running
      server-side. No count, no green tick, until it answers.</p>`
     : Object.keys(groups).length? Object.entries(groups).sort().map(([code,fs])=>`
      <details class="code"><summary>
        <span class="cid" style="color:var(--${fs[0].sev==="block"?"block":"warn"})">${code}</span>
        <span class="pill ${fs[0].sev==="block"?"p-block":"p-warn"}">${fs[0].sev}</span>
        <span style="color:var(--muted)">${fs.length} subject${fs.length>1?"s":""}</span>
      </summary><div class="in">${fs.map(f=>"· "+esc(f.subject)).join("<br>")}</div></details>`).join("")
     : `<p style="color:var(--ok)">Nothing flagged.</p>`}

    <div class="legend">ORG-015 was dropped, not deferred — D-path is display-only and canon
      disclaims it as an identifier, so a code protecting it would teach the operator to defend a
      number the system does not promise.</div>`;
};

/* ── Balance ──
   Shipped by founder direction 2026-08-07 as a deliberate §8.5.3 exception:
   the backing state path does not exist yet, and this screen SAYS so instead
   of pretending. Rules inherited from the Balance design of record
   (holding/plans/insights-balance/DESIGN.md): outputs are work-pattern
   inference, never emotional truth; takeaways are typed AWARENESS /
   UNDERSTANDING / ACTIONABLE and production shows whichever exist (0-3),
   never padded. No counts anywhere on this screen: there is nothing to count.

   v2 (founder direction, same day): the screen is a CASCADE (state line ->
   takeaway cards, both still SAMPLE) over a REAL chat — a session pane opened
   pre-loaded on Balance. The persona rides opts.append_system_prompt, which
   askClaude() already sends per turn and the server already validates
   (build_agent_args, 8000-char cap). The screen splits BY FUNCTION (codex):
   sample preview band on top, a truth bar in the middle stating what exists,
   the real-chat launcher below — so the chat can never launder the sample
   cards into implied measurements. The chat itself is a normal local session
   (fresh, no resume: resumableId() is null until Claude answers), so the main
   thread of any other session is untouched. */
const BALANCE_PROMPT =
  "You are Balance, the founder wellbeing module of Sutra (design of record: " +
  "holding/plans/insights-balance/DESIGN.md). Register: professional coach — brief, calm, " +
  "evidence-first; one observation + one suggestion; never clinical, never diagnosing. " +
  "Everything you say is work-pattern inference from ledgers, never emotional truth — say " +
  "\"possible frustration spike\", not \"you are frustrated\". Takeaways you offer are typed " +
  "AWARENESS (what happened), UNDERSTANDING (why), or ACTIONABLE (a suggestion, never a " +
  "command); give whichever genuinely exist, 0-3, never padded. HONESTY FLOOR: the Balance " +
  "state contract (holding/state/balance/) does not exist yet — observation has NOT started; " +
  "say so if asked about trends you cannot support. When the founder asks about their day or " +
  "patterns, you MAY read these existing ledgers (relative to the repo root): " +
  ".sutra/h-sutra.jsonl (per-turn classifications), .sutra/atom-ledger.jsonl (work atoms), " +
  "holding/hooks/hook-log.jsonl (gate blocks/retries — friction), holding/ESTIMATION-LOG.jsonl, " +
  "holding/LATENCY-LOG.jsonl, holding/TRIAGE-LOG.jsonl. Cite which ledger backs each claim. " +
  "Sparse data lowers confidence — say so rather than inventing a state.";
function openBalanceChat(){
  /* Always a FRESH local session (codex: never adopt an existing one by title).
     The persona is pinned in turnOpts BEFORE the pane renders, so the very
     first turn already carries it. */
  const s = { id:"s-"+(++SID), title:"Balance", created_ms:NOW, updated_ms:NOW,
              turns:[], local:true, loadState:"live" };
  S.sessions.unshift(s);
  S.turnOpts[s.id] = Object.assign({}, S.turnOpts[s.id],
                                   { append_system_prompt: BALANCE_PROMPT });
  S.openPanes.push(s.id);
  if (S.openPanes.length>2) S.openPanes = S.openPanes.slice(-2);
  render();
  const inp = document.querySelector('[data-sask="'+s.id+'"]'); if (inp) inp.focus();
  return s.id;
}
/* Live data path (2026-08-07): lazy fetch like Git/Editor — the read happens
   when the screen is opened, and "we have not fetched yet" renders as loading,
   never as an empty measurement. Real rows REPLACE the sample cascade; the
   samples render only when the backend answers {present:false}. */
async function loadBalance(force){
  if (S.balance && !force) return;
  S.balance = { loading: true };
  try { S.balance = await apiGet("/api/balance"); }
  catch (e){ S.balance = { present: false, error: true }; }
  render();
}
function balanceLiveHtml(b){
  const st = b.state || {};
  /* v2 schema: cards[] in the human register (time/energy/awareness/
     understanding/actionable/custom). v1 takeaways[] still renders if an old
     snapshot is on disk — the reader outlives the writer's schema bump. */
  const tw = (st.cards || st.takeaways || []);
  const typeColor = {time:"var(--acc)", energy:"var(--warn)", awareness:"var(--acc)",
                     understanding:"var(--warn)", actionable:"var(--ok)", custom:"var(--block)"};
  const rows = (b.today || []);
  /* Day strip v3 (founder redline): 96 FIXED 15-min slots, thin, width-capped —
     the v2 flex:1 cells ballooned three observations into three giant blocks. */
  const daySlots = new Array(96).fill(null);
  rows.forEach(r=>{
    const d = new Date((r.epoch||0)*1000);
    const idx = d.getHours()*4 + Math.floor(d.getMinutes()/15);
    if (idx>=0 && idx<96) daySlots[idx] = r.state || "observed";
  });
  const strip = daySlots.map((s,i)=>{
    const c = {steady:"var(--ok)", stretched:"var(--warn)", observed:"var(--acc)",
               "possible-spike":"var(--block)"}[s] || "var(--line-soft)";
    const hh = String(Math.floor(i/4)).padStart(2,"0"), mm = String((i%4)*15).padStart(2,"0");
    return `<span title="${hh}:${mm}${s?" — "+esc(s):""}" style="flex:1;height:10px;border-radius:2px;background:${c}"></span>`;
  }).join("");
  const hh = new Date().getHours();
  const greet = hh < 12 ? "Good morning" : hh < 17 ? "Good afternoon" : "Good evening";
  const timeCard = tw.find(t => (t.kind||t.type) === "time");
  return `
  <div class="balance-greet" style="font-family:var(--serif);font-size:22px;font-weight:500;
       letter-spacing:-.01em;margin:6px 0 2px">${greet}.</div>
  <div style="color:var(--muted);font-size:12.5px;margin-bottom:16px;max-width:560px;line-height:1.5">
    ${esc(timeCard ? timeCard.text : "Your day, read from your own messages.")}
    <span style="color:var(--faint)">· machine activity filtered · observe-only</span></div>
  ${tw.length ? `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px">
    ${tw.filter(t=>(t.kind||t.type)!=="time").map(t=>{
      const k = t.kind||t.type||"";
      return `
    <div style="background:var(--card);border:1px solid var(--line);border-left:3px solid ${typeColor[k]||"var(--line)"};
         border-radius:12px;padding:13px 15px;box-shadow:var(--shadow)">
      <div style="font:600 8.5px/1 var(--mono);letter-spacing:.14em;color:${typeColor[k]||"var(--muted)"};
           text-transform:uppercase;margin-bottom:7px">${esc(k)}</div>
      <div style="font-size:12.5px;line-height:1.55">${esc(t.text||"")}</div>
    </div>`;}).join("")}</div>`
    : `<p style="color:var(--muted);font-size:12px">Nothing to say yet — that's a valid answer.</p>`}
  <div style="background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:13px 15px;margin-top:12px;box-shadow:var(--shadow);max-width:560px;overflow-x:auto">
    <div style="font:600 8.5px/1 var(--mono);letter-spacing:.14em;color:var(--muted);
         text-transform:uppercase;margin-bottom:9px">Today · ${rows.length} of 96 windows observed</div>
    <div style="display:flex;gap:1px;min-width:380px">${strip}</div>
    <div style="display:flex;justify-content:space-between;min-width:380px;margin-top:4px;
         font:9px var(--mono);color:var(--faint)"><span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>12am</span></div>
  </div>
  ${balanceActionablesHtml(b)}
  <div class="legend">Updated ${esc(st.generated_at || "")} by the 15-minute observer — it watches,
    never interrupts. Signals come only from your own messages and their timing.</div>`;
}
/* Live actionables (PLAN-25 step 11). Cards come from the coach's derived
   view served by /api/balance. The checkbox is drawn ONLY when the preload
   verb exists (desktop app) — in a plain browser Balance stays read-only,
   same pattern as the Browse button. No inline onclick with interpolated
   ids: data attributes + one delegated listener. */
function balanceActionablesHtml(b){
  const acts = Array.isArray(b.actionables) ? b.actionables : null;
  if (!acts || !acts.length) return "";
  const canMark = !!(window.sutra && window.sutra.markActionable);
  const open = acts.filter(a => a.status === "open" && a.active);
  const parked = acts.filter(a => a.status === "open" && !a.active).length;
  const done = acts.filter(a => a.status === "done");
  const card = (a) => {
    const isDone = a.status === "done";
    const escd = !isDone && a.escalated;
    const edge = isDone ? "var(--ok)" : escd ? "var(--block)" : "var(--warn)";
    let meta = isDone ? `closed by ${esc(String(a.closed_by||""))}` : `open ${a.days_open||0}d`;
    if (!isDone && a.movements) meta += ` · ${a.movements} progress note${a.movements===1?"":"s"}`;
    if (escd) meta += ` · RECURRING — stalled ${a.stalled_days||0}d`;
    const box = isDone ? `<span style="font:700 13px var(--mono);color:var(--ok)">[x]</span>`
      : canMark
        ? `<button data-balance-done="${esc(a.id)}" title="Mark done"
             style="font:700 13px var(--mono);color:var(--acc);background:none;border:1px solid var(--line);
             border-radius:6px;cursor:pointer;padding:2px 7px">[ ]</button>`
        : `<span style="font:700 13px var(--mono);color:var(--muted)">[ ]</span>`;
    return `
    <div style="display:flex;gap:10px;align-items:flex-start;background:var(--card);border:1px solid var(--line);
         border-left:3px solid ${edge};border-radius:10px;padding:11px 13px;margin-bottom:8px${isDone?";opacity:.7":""}">
      ${box}
      <div style="flex:1;font-size:12.5px;line-height:1.5">${esc(a.text||"")}
        <div style="font:9.5px var(--mono);color:var(--faint);margin-top:4px">${esc(meta)}</div></div>
    </div>`;
  };
  return `
  <div style="margin-top:14px;max-width:560px">
    <div style="font:600 8.5px/1 var(--mono);letter-spacing:.14em;color:var(--muted);
         text-transform:uppercase;margin-bottom:9px">Actionables · ${open.length} active${parked?` · ${parked} parked`:""}</div>
    ${open.map(card).join("")}${done.map(card).join("")}
    ${canMark ? "" : `<div style="font-size:10px;color:var(--faint)">Read-only here — marking done needs the desktop app (or Balance chat).</div>`}
  </div>`;
}
document.addEventListener("click", async (ev) => {
  const btn = ev.target && ev.target.closest && ev.target.closest("[data-balance-done]");
  if (!btn || !(window.sutra && window.sutra.markActionable)) return;
  btn.disabled = true; btn.textContent = "[…]";
  const r = await window.sutra.markActionable(btn.dataset.balanceDone, "done", "");
  if (r && r.ok) { btn.textContent = "[x]"; loadBalance(true); }
  else { btn.disabled = false; btn.textContent = "[ ]"; toast && toast("Could not mark done: " + esc(String(r && r.error || "unknown"))); }
});
/* Inline ask (founder redline): the founder types IN the Balance screen; Enter
   creates the Balance-seeded session and routes the text through submitTurn —
   the same optimistic/streaming/error pipeline as every other message (codex:
   no special first-turn path). On failure the turn machinery keeps the text
   visible as a failed, retryable turn; nothing is swallowed. */
function balanceAsk(e){
  if (e.key !== "Enter") return;
  const text = e.target.value.trim();
  if (!text) return;
  e.preventDefault();
  e.target.value = "";
  const sid = openBalanceChat();
  submitTurn(text, sid);
}
SCREENS.balance = () => {
  if (!S.balance || S.balance.loading)
    return `<p style="color:var(--muted)">Reading the Balance state contract…</p>`;
  if (S.balance.present) return balanceLiveHtml(S.balance) + `
  <div id="balanceChat" style="background:var(--card);border:1px solid var(--line);border-radius:14px;
       padding:14px 16px;display:flex;align-items:center;gap:10px;max-width:560px;margin-top:14px;
       box-shadow:var(--shadow)">
    <input onkeydown="balanceAsk(event)" placeholder="Ask Balance anything — how balanced am I today?"
           style="flex:1;border:0;background:transparent;outline:none;font-family:var(--sans);font-size:13px;color:var(--ink)">
    <span style="font:500 9.5px/1 var(--mono);color:var(--faint);border:1px solid var(--line);
          border-radius:5px;padding:3px 7px">ENTER</span>
  </div>
  <p style="color:var(--faint);font-size:10.5px;margin:6px 0 0">Opens a Balance-loaded session beside
    this pane, already answering.</p>`;
  return balanceSampleHtml();
};
const balanceSampleHtml = () => `
  <h3 class="sec">Today <span class="pill p-warn">SAMPLE</span></h3>
  <div style="font-size:13px;margin-bottom:8px">Steady, mostly — one friction window late morning.
    <span style="color:var(--faint)">(sample state line; the cascade below shows the register, not a measurement)</span></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px">
    <div style="background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:11px 13px">
      <div style="font:600 8.5px/1 var(--mono);letter-spacing:.12em;color:var(--acc);margin-bottom:6px">AWARENESS · SAMPLE</div>
      <div style="font-size:12px">Heavy shipping day — several units closed by mid-afternoon. Steady, not spiking.</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:11px 13px">
      <div style="font:600 8.5px/1 var(--mono);letter-spacing:.12em;color:var(--warn);margin-bottom:6px">UNDERSTANDING · SAMPLE</div>
      <div style="font-size:12px">Friction clusters on one path, not many — the blocks point at a single gap.</div>
    </div>
    <div style="background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:11px 13px">
      <div style="font:600 8.5px/1 var(--mono);letter-spacing:.12em;color:var(--ok);margin-bottom:6px">ACTIONABLE · SAMPLE</div>
      <div style="font-size:12px">Worth considering: 30 focused minutes on the recurring gap, once.</div>
    </div>
  </div>

  <div class="note" style="margin-top:12px"><b>Current truth:</b> observation has not started —
    <code>holding/state/balance/</code> does not exist. The cards above are samples teaching the
    register. The chat below is REAL: it answers from your existing work ledgers when asked,
    not from a Balance state file.</div>

  <h3 class="sec">Ask Balance</h3>
  <p style="color:var(--muted);font-size:12px;margin:0 0 8px">Opens a real session pre-loaded on
    Balance — coach register, ledger evidence, honesty floor. Try: “how balanced am I today?”</p>
  <button type="button" id="balanceChat" onclick="openBalanceChat()">Open Balance chat</button>

  <div class="legend">Takeaways are typed AWARENESS / UNDERSTANDING / ACTIONABLE; production shows
    whichever exist (0–3), never padded. Observation reads existing work ledgers only; no screen,
    keyboard, or microphone capture. Design of record: holding/plans/insights-balance/DESIGN.md.</div>`;

