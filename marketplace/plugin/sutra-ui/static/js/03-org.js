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
/* ---- The Five Hats: the approved tabbed design, rendered natively ----------
   Data comes from the nightly UI read model (`view`, dashboard-data.json) —
   the SAME semantic decisions the generated dashboard renders, so the two
   surfaces cannot drift (consult 2026-08-18: re-deriving here would recreate
   the drift this closes). Live values (windows observed, actionables) come
   from the 15-min side of the payload; the two clocks are named in one line
   rather than badged everywhere. */
const BAL_TABS = ["today", "week", "month"];
function balTab(){ const t = S.ui && S.ui.balanceTab; return BAL_TABS.includes(t) ? t : "today"; }

function balTiles(cells){
  return `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px">
    ${cells.map(c=>`<div style="background:var(--card);border:1px solid var(--line);border-radius:10px;
       padding:12px 14px;box-shadow:var(--shadow)">
      <b style="display:block;font:600 22px/1.1 var(--serif);color:var(--acc)">${esc(String(c.v))}</b>
      <span style="font-size:11px;color:var(--muted)">${esc(c.k)}</span></div>`).join("")}
  </div>`;
}
function balBars(items, hot){
  const mx = Math.max(1, ...items.map(i=>i.n));
  return `<div style="display:flex;gap:2px;align-items:flex-end;height:52px">
    ${items.map(i=>`<div title="${esc(i.label)}: ${i.n}" aria-label="${esc(i.label)}: ${i.n}"
      style="flex:1;min-height:2px;border-radius:2px 2px 0 0;height:${i.n===0?2:Math.round(4+i.n/mx*46)}px;
      background:${hot && i.hot ? "var(--warn)" : "var(--acc)"};opacity:${i.n===0?.35:1}"></div>`).join("")}
  </div>`;
}
function balHeatmap(view){
  const shades = ["var(--line-soft)","var(--acc-bg)","var(--acc)","var(--acc)","var(--acc)"];
  const alpha  = [1, 1, .45, .72, 1];
  const rows = view.roles.map(r=>`
    <div style="display:grid;grid-template-columns:86px repeat(${view.days.length},minmax(9px,1fr));gap:2px;margin-bottom:2px;align-items:center">
      <div style="font:600 9px/1.2 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)">${esc(r.name)}</div>
      ${r.cells.map(c=>`<div tabindex="0" title="${esc(r.name)}, ${esc(c.d)}: ${c.n} file-touches"
          aria-label="${esc(r.name)}, ${esc(c.d)}: ${c.n} file-touches"
          style="height:13px;border-radius:2px;background:${shades[c.level]};opacity:${alpha[c.level]}"></div>`).join("")}
    </div>`).join("");
  return `<div style="overflow-x:auto"><div style="min-width:520px">${rows}
    <div style="display:grid;grid-template-columns:86px repeat(${view.days.length},minmax(9px,1fr));gap:2px;margin-top:4px">
      <span></span>${view.days.map((d,i)=>`<span style="font:8px var(--mono);color:var(--faint);text-align:center">${i%7===0||i===view.days.length-1?esc(d):""}</span>`).join("")}
    </div></div></div>`;
}
function balRoleCards(view){
  if (!view.roles_review || !view.roles_review.length) return "";
  return view.roles_review.map(r=>`
    <div style="background:var(--card);border:1px solid var(--line);border-left:3px solid var(--acc);
         border-radius:12px;padding:14px 16px;margin-bottom:10px;box-shadow:var(--shadow)">
      <h3 style="font-family:var(--serif);font-size:16px;margin:0 0 4px;font-weight:600">${esc(r.role||"")}</h3>
      <div style="font-size:10.5px;color:var(--faint);margin-bottom:8px">${esc(r.evidence||"")} · confidence: ${esc(r.confidence||"")}</div>
      <div style="font:600 9px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;color:var(--ok);margin-bottom:3px">What's working</div>
      <div style="font-size:12.5px;line-height:1.5;margin-bottom:8px">${esc(r.great||"")}</div>
      <div style="font:600 9px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;color:var(--warn);margin-bottom:3px">Sharpen</div>
      <div style="font-size:12.5px;line-height:1.5;margin-bottom:8px">${esc(r.improve||"")}</div>
      <div style="font-size:12.5px;line-height:1.5;background:var(--acc-bg);border-radius:8px;padding:9px 11px">
        <b>How:</b> ${esc(r.how||"")}</div>
    </div>`).join("");
}
function balanceTabbedHtml(b){
  const view = b.view, st = b.state || {}, rows = b.today || [];
  const acts = Array.isArray(b.actionables) ? b.actionables : [];
  const active = acts.filter(a=>a.status==="open" && a.active).length;
  const done = acts.filter(a=>a.status==="done").length;
  const tab = balTab();
  const sec = (t) => `<h3 class="sec" style="margin-top:18px">${esc(t)}</h3>`;
  let body = "";
  if (tab === "today"){
    body = balTiles([{v:rows.length,k:"observation windows today"},
                     {v:view.commits_today,k:"commits today (nightly)"},
                     {v:active,k:"active actionables"},
                     {v:done,k:"done"}])
      + balanceActionablesHtml(b)
      + sec("Today's insights")
      + `<div style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;
           box-shadow:var(--shadow);font-size:12.5px;line-height:1.6">
          ${view.insights && view.insights.length
            ? view.insights.map(i=>`<div>${esc(i.text)} <span style="color:var(--faint)">(${esc(i.date)})</span></div>`).join("")
            : "First daily pass pending."}</div>`
      + sec("Shipped today")
      + `<div style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;
           box-shadow:var(--shadow);font-size:12.5px;line-height:1.7">
          ${view.today_subjects && view.today_subjects.length
            ? view.today_subjects.map(s=>`<div>${esc(s)}</div>`).join("")
            : "<span style='color:var(--muted)'>Nothing committed yet today.</span>"}</div>`;
  } else if (tab === "week"){
    body = (view.week_insight
        ? `<div style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;
             box-shadow:var(--shadow);margin-bottom:12px">
            <b style="font-family:var(--serif)">The week, read honestly.</b>
            <div style="font-size:12.5px;margin-top:5px;line-height:1.6">${esc(view.week_insight.text||"")}</div></div>`
        : "")
      + sec("Commits per day")
      + `<div style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
           box-shadow:var(--shadow);max-width:420px">
          ${balBars((view.commits_week||[]).map(c=>({n:c.n,label:c.day})), false)}
          <div style="display:flex;justify-content:space-between;margin-top:4px;font:9px var(--mono);color:var(--faint)">
            ${(view.commits_week||[]).map(c=>`<span>${esc(c.day)}</span>`).join("")}</div></div>`
      + sec("Shipped this week")
      + `<div style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;
           box-shadow:var(--shadow);font-size:12.5px;line-height:1.7">
          ${view.week_subjects && view.week_subjects.length
            ? view.week_subjects.map(s=>`<div><span style="font:600 10px var(--mono);color:var(--muted);margin-right:8px">${esc(s.date)}</span>${esc(s.text)}</div>`).join("")
            : "<span style='color:var(--muted)'>No feature/release commits this week.</span>"}</div>`
      + sec("Actionables in play")
      + balanceActionablesHtml(b);
  } else {
    body = sec("Where the month went")
      + `<p style="font-size:12px;color:var(--muted);margin:0 0 10px;max-width:60ch">File-touches per day by role,
          trailing ${view.days.length} days. Darker = more. An empty row is itself a finding.</p>`
      + `<div style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
           box-shadow:var(--shadow)">${balHeatmap(view)}</div>`
      + sec("When you work")
      + `<div style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
           box-shadow:var(--shadow)">
          ${balBars((view.hours||[]).map(h=>({n:h.n,hot:h.hot,label:(h.h===0?"12am":h.h<12?h.h+"am":h.h===12?"12pm":(h.h-12)+"pm")})), true)}
          <div style="display:flex;justify-content:space-between;margin-top:4px;font:9px var(--mono);color:var(--faint)">
            <span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span></div></div>`
      + sec("The five roles, coached")
      + balRoleCards(view)
      + (view.balance_note ? `<div class="legend" style="max-width:70ch">${esc(view.balance_note)}</div>` : "");
  }
  const hh = new Date().getHours();
  const greet = hh < 12 ? "Good morning" : hh < 17 ? "Good afternoon" : "Good evening";
  return `
  <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin:6px 0 2px">
    <div class="balance-greet" style="font-family:var(--serif);font-size:22px;font-weight:500;letter-spacing:-.01em">${greet}.</div>
    <div class="tabs" style="margin-left:auto">
      ${BAL_TABS.map(t=>`<button type="button" data-baltab="${t}" aria-pressed="${tab===t}">${t==="today"?"Today":t==="week"?"This week":"Month"}</button>`).join("")}
    </div>
  </div>
  <div style="color:var(--faint);font:9.5px var(--mono);margin-bottom:14px">
    observed ${esc((st.generated_at||"").slice(11,16) || "—")} UTC by the 15-minute watcher ·
    dashboard rendered ${esc(view.rendered_at_local || "")} by the nightly pass${view.review_window?` · ${esc(view.review_window)}`:""}</div>
  ${body}`;
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
  const dropped = acts.filter(a => a.status === "dropped");
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
    /* Drop ("it doesn't matter"): the x opens four one-click reasons — a
       reason is required (both consult lanes: a why-less drop leaves the
       ledger proving only that discomfort was dismissed) but never typed. */
    const dropUi = (isDone || !canMark) ? "" : `
      <button data-balance-drop="${esc(a.id)}" title="Doesn't matter — drop it"
        aria-label="Drop this actionable" style="font:600 13px/1 var(--mono);color:var(--faint);
        background:none;border:0;cursor:pointer;padding:2px 5px;align-self:flex-start">&times;</button>`;
    const dropPicker = (!isDone && canMark && S.ui.balanceDropFor === a.id) ? `
      <div style="flex-basis:100%;display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;
           border-top:1px dashed var(--line);padding-top:8px">
        <span style="font:9.5px/1.8 var(--mono);color:var(--muted);margin-right:2px">drop because</span>
        ${[["doesnt-matter","doesn't matter"],["not-now","not now"],
           ["handled-elsewhere","handled elsewhere"],["coach-wrong","coach got it wrong"]]
          .map(([v,label])=>`<button data-drop-id="${esc(a.id)}" data-drop-reason="${v}"
            style="font:600 9.5px/1 var(--mono);color:var(--muted);background:var(--card);
            border:1px solid var(--line);border-radius:99px;padding:5px 9px;cursor:pointer">${esc(label)}</button>`).join("")}
      </div>` : "";
    return `
    <div style="display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap;background:var(--card);
         border:1px solid var(--line);border-left:3px solid ${edge};border-radius:10px;padding:11px 13px;
         margin-bottom:8px${isDone?";opacity:.7":""}">
      ${box}
      <div style="flex:1;font-size:12.5px;line-height:1.5">${esc(a.text||"")}
        <div style="font:9.5px var(--mono);color:var(--faint);margin-top:4px">${esc(meta)}</div></div>
      ${dropUi}${dropPicker}
    </div>`;
  };
  const DROP_LABEL = {"doesnt-matter":"doesn't matter","not-now":"not now",
                      "handled-elsewhere":"handled elsewhere","coach-wrong":"coach got it wrong"};
  /* Dropped stays VISIBLE (both consult lanes, P1): the ledger keeps it
     forever regardless, and a coach whose items can be silently deleted stops
     being a coach. Collapsed count + reasons, never in the active list. */
  const droppedHtml = dropped.length ? `
    <details style="margin-top:6px">
      <summary style="font:9.5px/1.6 var(--mono);color:var(--faint);cursor:pointer">
        ${dropped.length} dropped</summary>
      <div style="margin-top:6px">${dropped.slice(-5).map(a=>`
        <div style="font-size:11.5px;color:var(--muted);line-height:1.5;padding:4px 0">
          <span style="text-decoration:line-through">${esc(a.text||"")}</span>
          <span style="font:9px var(--mono);color:var(--faint)"> — ${esc(DROP_LABEL[a.drop_reason]||a.drop_reason||"dropped")}</span>
        </div>`).join("")}</div>
    </details>` : "";
  return `
  <div style="margin-top:14px;max-width:560px">
    <div style="font:600 8.5px/1 var(--mono);letter-spacing:.14em;color:var(--muted);
         text-transform:uppercase;margin-bottom:9px">Actionables · ${open.length} active${parked?` · ${parked} parked`:""}</div>
    ${open.map(card).join("")}${done.map(card).join("")}
    ${droppedHtml}
    ${canMark ? "" : `<div style="font-size:10px;color:var(--faint)">Read-only here — marking done needs the desktop app (or Balance chat).</div>`}
  </div>`;
}
/* Tab switch: state only, no refetch (consult fold — switching must not
   re-hit the API, and loadBalance(true) after a done-click must not reset
   the selected tab, which is why this lives in S.ui and not in S.balance). */
document.addEventListener("click", (ev) => {
  const t = ev.target && ev.target.closest && ev.target.closest("[data-baltab]");
  if (!t) return;
  const want = t.dataset.baltab;
  if (!BAL_TABS.includes(want)) return;
  S.ui.balanceTab = want;
  render();
});
/* Drop: the x reveals the reason chips (state only); a chip does the write. */
document.addEventListener("click", (ev) => {
  const x = ev.target && ev.target.closest && ev.target.closest("[data-balance-drop]");
  if (!x) return;
  const id = x.dataset.balanceDrop;
  S.ui.balanceDropFor = (S.ui.balanceDropFor === id) ? null : id;
  render();
});
document.addEventListener("click", async (ev) => {
  const chip = ev.target && ev.target.closest && ev.target.closest("[data-drop-reason]");
  if (!chip || !(window.sutra && window.sutra.markActionable)) return;
  chip.disabled = true;
  const r = await window.sutra.markActionable(chip.dataset.dropId, "drop", "", chip.dataset.dropReason);
  S.ui.balanceDropFor = null;
  if (r && r.ok) loadBalance(true);
  else { chip.disabled = false; toast && toast("Could not drop: " + esc(String(r && r.error || "unknown"))); }
});
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

/* ── Teamsutra: the Ask Sutra seeded chat ─────────────────────────────────
   Same shape as openBalanceChat, and for the same reasons: a FRESH local
   session, the seed pinned into turnOpts BEFORE the pane renders so the very
   first turn carries it. The difference is that this seed is ASSEMBLED per
   invocation — persona + the department the selection resolved to + the
   selected text — and must therefore be BUDGETED: the server truncates
   append_system_prompt at 8000 chars SILENTLY (app.py _flag_str), and a
   silently cut briefing is a chat that confidently answers from half a
   department. */

const TS_SEED_MAX = 8000;   // mirror of app.py's cap — checked by test 29b

const TS_PERSONA =
  "You are Teamsutra, the in-app assistant of the Sutra desktop panel. The " +
  "user selected a piece of text inside the app and asked about it. FIRST " +
  "explain — what the selected thing is, in the context of the department " +
  "given below; be brief and concrete. If the user describes a problem or " +
  "asks for a change, offer to file it as a task (say what you would write, " +
  "then file only on their yes). HONESTY FLOOR: context below is structure " +
  "only — names, paths, charter titles. If it was truncated, the last line " +
  "says so; when a claim needs data you do not have, say that rather than " +
  "inventing it. A null department means nothing classified this selection " +
  "— do not guess one.";

/* Assemble the department slice of the seed, cheapest facts first, and cut
   HIERARCHICALLY when over budget: descendants drop before the parent chain,
   the parent chain before the selection, and the truncation is STATED in the
   seed itself. Order of sacrifice, most expendable first:
     child charter titles -> child list -> ancestor names -> nothing else.
   The selection and the persona are never cut (the selection is already
   capped at 4000 by the bubble). */
function tsBuildSeed(ctx){
  const parts = { persona: TS_PERSONA, dept: "", sel: "" };
  const d = ctx.domainRef && typeof byRef === "function" ? byRef(ctx.domainRef) : null;
  if (d){
    const chain = [];
    let cur = d;
    for (let i = 0; cur && i < 12; i++){
      chain.unshift((typeof dPath === "function" ? dPath(cur.ref) + " " : "") + cur.name);
      cur = cur.parent_ref ? byRef(cur.parent_ref) : null;
    }
    const kids = (typeof DOMAINS !== "undefined" ? DOMAINS : [])
      .filter(x => x.parent_ref === d.ref)
      .map(x => x.name);
    const charters = (typeof CHARTERS !== "undefined" ? CHARTERS : [])
      .filter(c => c.domain_ref === d.ref && (c.status || "active") !== "retired")
      .map(c => c.title).filter(Boolean);
    const full = [
      "DEPARTMENT: " + chain.join(" > "),
      kids.length ? "SUB-DEPARTMENTS: " + kids.join(", ") : "",
      charters.length ? "CHARTERS: " + charters.join(" | ") : "",
    ].filter(Boolean).join("\n");
    const noCharters = [
      "DEPARTMENT: " + chain.join(" > "),
      kids.length ? "SUB-DEPARTMENTS: " + kids.join(", ") : "",
    ].filter(Boolean).join("\n");
    const bare = "DEPARTMENT: " + chain.join(" > ");
    parts.dept = { full, noCharters, bare };
  } else if (ctx.charterId){
    parts.dept = { full: "CHARTER: " + ctx.charterId, noCharters: "CHARTER: " + ctx.charterId,
                   bare: "CHARTER: " + ctx.charterId };
  } else {
    parts.dept = { full: "DEPARTMENT: none — nothing classified this selection",
                   noCharters: "DEPARTMENT: none — nothing classified this selection",
                   bare: "DEPARTMENT: none — nothing classified this selection" };
  }
  parts.sel = "SELECTED TEXT (screen: " + (ctx.screen || "unknown") + "):\n" + (ctx.text || "");
  const join = dept => parts.persona + "\n\n" + dept + "\n\n" + parts.sel;
  const MARK = "\n[context truncated to fit the briefing budget]";
  let seed = join(parts.dept.full);
  if (seed.length <= TS_SEED_MAX) return seed;
  seed = join(parts.dept.noCharters) + MARK;
  if (seed.length <= TS_SEED_MAX) return seed;
  seed = join(parts.dept.bare) + MARK;
  if (seed.length <= TS_SEED_MAX) return seed;
  /* Persona + bare chain + selection still over: cut the SELECTION's tail as
     the last resort, keeping the marker. Never emit an over-budget seed. */
  const overhead = join(parts.dept.bare).length - (ctx.text || "").length;
  const room = Math.max(0, TS_SEED_MAX - overhead - MARK.length);
  parts.sel = "SELECTED TEXT (screen: " + (ctx.screen || "unknown") + "):\n" +
              (ctx.text || "").slice(0, room);
  return join(parts.dept.bare) + MARK;
}

function openTeamsutraChat(ctx){
  ctx = ctx || {};
  const s = { id:"s-"+(++SID), title:"Ask Sutra", created_ms:NOW, updated_ms:NOW,
              turns:[], local:true, loadState:"live" };
  S.sessions.unshift(s);
  S.turnOpts[s.id] = Object.assign({}, S.turnOpts[s.id],
                                   { append_system_prompt: tsBuildSeed(ctx) });
  S.openPanes.push(s.id);
  if (S.openPanes.length>2) S.openPanes = S.openPanes.slice(-2);
  /* tsPrefill: the first turn is NOT auto-sent (founder feedback 2026-08-18:
     "let me type the message... let me click on Enter"). The default question
     is placed in the composer as an EDITABLE draft via S.composerText — the
     same store the template reads and applyPalette writes — so it survives
     re-renders, and the founder edits or replaces it and presses Enter
     themselves. Nothing spends money until they do. */
  S.composerText[s.id] = "What is this about?";
  render();
  const inp = document.querySelector('[data-sask="'+s.id+'"]');
  if (inp) {
    inp.value = S.composerText[s.id];
    inp.focus();
    if (inp.setSelectionRange) {
      try { inp.setSelectionRange(inp.value.length, inp.value.length); } catch (e) {}
    }
  }
  return s.id;
}
if (typeof window !== "undefined") window.openTeamsutraChat = openTeamsutraChat;
SCREENS.balance = () => {
  if (!S.balance || S.balance.loading)
    return `<p style="color:var(--muted)">Reading the Balance state contract…</p>`;
  /* The approved design when the nightly read model is on disk; the v0 shape
     as an honest fallback for an instance whose pass has never run. */
  if (S.balance.present) return (S.balance.view ? balanceTabbedHtml(S.balance)
                                                : balanceLiveHtml(S.balance)) + `
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

