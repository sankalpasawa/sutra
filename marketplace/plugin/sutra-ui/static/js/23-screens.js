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
/* A function's class on the Map, from the five functions' read (functions_view.py, PRD M1.5): working is lit, waits on
   you is amber, a fault is block, waiting on another function is dashed, quiet is plain; a stopped department is off,
   by its switch or by the read.
   Until the read lands, or when it failed, the boxes fall back to today's rule: an ask is Identity's (it is the one that
   asks), a run of its own lights it, and a paused function is off. */
const WB2_FN_CLS = { working: "run", waiting_on_you: "ask", fault: "block", waiting: "wait", quiet: "" };
function wb2FnNode(fv, name){ return ((fv && !fv.failed && fv.functions) || []).filter(x => x.name === name)[0] || null; }
function wb2FnCls(m, name, fv){
  const node = wb2FnNode(fv, name);
  if (node) return m.stopped || fv.stopped ? "off" : (WB2_FN_CLS[node.state] || "");
  if (wb2Asks(m).some(a => a.engine === name || name === "Identity")) return "ask";
  if (wb2Running(m).indexOf(name) >= 0) return "run";
  const s = (m.systems || []).filter(x => x.name === name)[0];
  return s && s.state === "running" ? "" : "off";
}
/* the state word under a function's name: the read's own word, the one the list, All five and the pane print too (a
   stopped department's is 'stopped' on every function; functions_view.py), or today's rule said in the same words */
function wb2FnWord(m, name, fv){
  const node = wb2FnNode(fv, name);
  if (node) return m.stopped || fv.stopped ? "stopped" : node.word;
  if (m.stopped) return "stopped";
  return ({ run: "working", ask: "waits on you", off: "off" })[wb2FnCls(m, name, fv)] || "quiet";
}
function wb2EngCls(m, e){
  if (!m.stopped && (e.state === "Running" || wb2Running(m).indexOf(e.name) >= 0)) return "run";
  if (e.state === "Waits" || wb2Asks(m).some(a => a.engine === e.name)) return "ask";
  if (e.last && e.last.status === "failed") return "block";
  return e.last ? "ok" : "off";
}
function wb2DotCls(cls){ return cls === "run" ? "" : (cls === "ask" ? "warn" : cls); }

/* ── the head the two screens wear ────────────────────────────────────────── */
function wb2Head(n, m){
  const st = wbS();
  const root = m.root && m.root !== n.ref && st.refs && st.refs[m.root];
  /* the crumb names the organisation, whose row is Root's chat: Root itself is not drawn (22-website.js wbHidden) */
  const od = root && typeof o2Data === "function" ? o2Data() : null;
  const rr = od && od.byRef.get(m.root);
  const org = rr && od.hidden && od.hidden.has(rr.ref) && rr.parent_ref ? od.byRef.get(rr.parent_ref) : null;
  const crumb = root ? `<div class="wb2crumb"><button type="button" class="o2more wb" data-wb2go="${wbEsc(org ? org.ref : m.root)}">${wbEsc(org ? org.name : root.name)}</button> &rsaquo; ${wbEsc(m.name)}</div>` : "";
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
/* The NOW line (PRD S1, S4; System status folds into it): the cycle in the owner's words first, then what runs, what
   waits for you, how today's runs went and a fault by its name. A count shows only when it is not zero; a department
   that is Off says Off. While the five functions' read is on its way a skeleton holds its place; when it failed the
   line says so once, with a way to read it again. */
function wb2NowHtml(m, fv){
  const pills = [];
  const cyc = fv && !fv.failed ? fv.cycle : null;
  if (fv === null && wbRt(m)) pills.push(`<span class="wb2pill wb2skel" aria-hidden="true"></span>`);
  if (fv && fv.failed) pills.push(`<span class="wb2pill off">Could not read</span><button type="button" class="o2more wb" data-wbfvretry="1">Try again</button>`);
  if (cyc && cyc.says && !m.stopped){
    const cls = cyc.state === "done" ? "ok" : (cyc.needs_you ? "ask" : (cyc.state === "running" || cyc.state === "pursuing" ? "run" : "say"));
    pills.push(`<span class="wb2pill ${cls}" aria-live="polite">${wbEsc((cyc.round ? "Round " + cyc.round + " · " : "") + cyc.says)}</span>`);
  }
  if (!m.stopped) wb2Running(m).forEach(e => pills.push(`<span class="wb2pill run">${wbEsc(e)} running</span>`));
  const asks = wb2Asks(m).length + ((m.status && m.status.escalated) || []).length;
  if (asks) pills.push(`<span class="wb2pill ask">${asks} ask${asks > 1 ? "s" : ""} for you</span>`);
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

/* a function's mark at list size, in its own colour (20-dept.js's function rows, S3; 24-functions.js's cards) */
function wb2Mark(fn){
  const ic = WB2_ICONS[String(fn || "").toLowerCase()];
  return ic ? `<svg class="dpfnmk fn-${wbEsc(String(fn).toLowerCase())}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ic}</svg>` : "";
}
/* ── Map: the whole topology, fixed, the active parts lit ─────────────────── */
/* PRD M1.5 (the ruled Map, rows 2.1 to 2.4): the topology is kept; the NOW line sits above it; each function's box takes
   its state from the five functions' read, with its colour bar, its mark, its name and its state word; the legend is
   cut, and every node names itself on hover instead; Budget joins what the department knows. Below a viewer width of
   600px the picture becomes a list of cards in the same order (a size container, panel.css). */
const WB2_FN_W = 154, WB2_FN_H = 64;
function wb2Title(t){ return `<title>${wbEsc(t)}</title>`; }
/* Where a box of the line of work goes, and what its hover adds: a filed thing opens itself; one not made yet opens the
   card of the engine that makes it, and the first thing (the Brief, which your words make) the Chat. No box opens a
   Motor screen: on the engine runtime the motor folds into each engine's card (PRD M4.7, S17). */
function wb2WorkAt(line, i, a){
  if (a && a.versions) return [`data-wbart="${wbEsc(a.slug)}"`, ""];
  const prev = i > 0 ? line[i - 1] : null;
  return prev && prev.kind === "eng" ? [`data-wbengine="${wbEsc(prev.e.name)}"`, " · " + prev.e.name + " makes it"] : [`data-wbtab="chat"`, " · your words make it"];
}
function wb2MapHtml(n, m){
  if (m.kind === "root") return wb2RootHtml(n, m);
  const fv = wbFv(n.ref);
  const W = 960, arts = {}; (m.artifacts || []).forEach(a => { arts[a.name] = a; });
  /* the line of work is the plan's (PRD M4.2): an engine the registered plan left out stays on the record and never
     runs, so it is not on the line; it sits under it, muted, with the words "left out" (map_view's in_line). Before
     Root's check there is no plan (map_view's planned, the test Coordination's pane takes too): the engines the
     department was born with are no line of work, and the Brief stands alone with 'No plan yet' (S1, Empty) */
  const plan = m.planned === false ? [] : (m.engines || []);
  const engs = plan.filter(e => e.in_line !== false), out = plan.filter(e => e.in_line === false);
  /* the line of work: what the first engine reads, then each engine and what it writes */
  const line = [];
  if (engs.length) line.push({ kind: "work", name: engs[0].reads });
  else if ((m.artifacts || []).length) line.push({ kind: "work", name: m.artifacts[0].name });   /* no plan yet: the Brief alone */
  engs.forEach(e => { line.push({ kind: "eng", e }); line.push({ kind: "work", name: e.writes }); });
  const last = (m.artifacts || []).length ? m.artifacts[m.artifacts.length - 1].name : "";
  /* the deliverable, the last thing the line makes, takes the ok tint once it is delivered, for every kind: a website's
     Live site (the map's live), the cycle's goal reached, or a version of it that passed its check (S1, Done) */
  const lastA = arts[last] || {}, lastChk = (lastA.latest && lastA.latest.check) || {};
  const delivered = !!(m.live || (fv && !fv.failed && fv.cycle && fv.cycle.state === "done") || (lastA.versions && lastChk.ok));
  const gap = line.length > 1 ? (W - 170) / (line.length - 1) : 0;
  const lx = i => 105 + i * gap;
  const fns = (m.systems || []).map(s => s.name);
  const fgap = fns.length > 1 ? (W - 260) / (fns.length - 1) : 0;
  const fx = i => 165 + i * fgap;                          /* clear of the row's label, the last box inside the frame */
  const FY = 104, FB = FY + WB2_FN_H;
  /* what the department knows: the template it runs (the functions read, 20-dept.js), its rules, its record, its host,
     and its budget: the spend of the whole goal against its ceiling, a bar whose numbers are its hover */
  if (typeof dpLoadFunctions === "function") dpLoadFunctions(n.ref);
  const fr = (typeof dpS === "function" && dpS().functions && dpS().functions.ref === n.ref) ? dpS().functions : null;
  const picked = fr && fr.picked && (fr.picked.identity || fr.picked.adaptation);
  const filed = (m.artifacts || []).filter(a => a.versions);
  const versions = filed.reduce((s, a) => s + (a.versions || 0), 0);
  /* the Record opens the last thing the department filed (Filed work), or the Chat while nothing is filed (PRD M4.7) */
  const rec = filed.length ? `data-wbart="${wbEsc(filed[filed.length - 1].slug)}"` : `data-wbtab="chat"`;
  const bud = (fv && !fv.failed && fv.budget) || null;
  /* [label, value, where a click goes, its hover name]: the hover says where the click goes, the box says the value */
  const knows = [
    ["Template", picked ? picked.name : (fr ? "Default" : ""), `data-wbfn="adaptation"`, "Template · kept by Adaptation"],
    ["Rules", (m.rules || []).length ? String(m.rules.length) : "none yet", `data-wbfn="identity"`, "Rules · kept by Identity"],
    ["Record", filed.length ? `${filed.length} thing${filed.length > 1 ? "s" : ""}, ${versions} version${versions > 1 ? "s" : ""}` : "nothing filed", rec, "Record · what the department filed"],
    ["Host", m.host || "this app's server", `data-wbfn="identity"`, "Host · where the work is served from"],
    ["Budget", null, `data-wbfn="priority"`, ""]];
  const kw = k => k[1] === null ? 150 : Math.max(150, Math.ceil(k[0].length * 8 + 16 + String(k[1]).length * 6.2 + 12));
  const kws = knows.map(kw), ktot = kws.reduce((s, w) => s + w, 0) + 12 * (knows.length - 1);
  const kx0 = i => (W - ktot) / 2 + kws.slice(0, i).reduce((s, w) => s + w + 12, 0);
  const kx = i => kx0(i) + kws[i] / 2;
  const esc = wbEsc;
  let svg = `<svg viewBox="0 0 ${W} 400" role="img" aria-label="The department as a map">` +
    `<defs><marker id="sxarrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker></defs>` +
    `<text class="lbl" x="12" y="30">People</text><text class="lbl" x="12" y="140">Functions</text><text class="lbl" x="12" y="228">Work</text><text class="lbl" x="12" y="360">Knows</text>`;
  /* edges: the owner to Identity; each function to the line; the hand-offs; what the department knows to who keeps it */
  const idx = fns.indexOf("Identity");
  if (idx >= 0) svg += `<path class="e soft" d="M110 44 L${(fx(idx) - 20).toFixed(0)} ${FY}"/>`;
  fns.forEach((f, i) => {
    const to = f === "Identity" ? 0 : (f === "Audit" ? line.length - 1 : Math.min(line.length - 1, 1 + 2 * Math.floor(i * engs.length / Math.max(1, fns.length))));
    if (line.length) svg += `<path class="e soft" d="M${fx(i).toFixed(0)} ${FB} L${lx(to).toFixed(0)} 232"/>`;
  });
  line.forEach((node, i) => {
    if (i === 0) return;
    const prev = line[i - 1];
    const hot = (node.kind === "eng" && wb2EngCls(m, node.e) === "run") || (prev.kind === "eng" && wb2EngCls(m, prev.e) === "run");
    const x1 = lx(i - 1) + (prev.kind === "eng" ? 20 : 36), x2 = lx(i) - (node.kind === "eng" ? 22 : 38);
    svg += `<path class="e${hot ? " flow" : ""}" marker-end="url(#sxarrow)" d="M${x1.toFixed(0)} 250 L${x2.toFixed(0)} 250"/>`;
  });
  knows.forEach((k, i) => { const j = k[0] === "Template" ? fns.indexOf("Adaptation") : (k[0] === "Rules" ? idx : (k[0] === "Budget" ? fns.indexOf("Priority") : -1));
    svg += j >= 0 ? `<path class="e soft" d="M${kx(i).toFixed(0)} 340 L${fx(j).toFixed(0)} ${FB}"/>`
                  : (line.length ? `<path class="e soft" d="M${kx(i).toFixed(0)} 340 L${lx(line.length - 1).toFixed(0)} 268"/>` : ""); });
  /* people */
  const you = wb2Asks(m).length ? "ask" : "";
  svg += `<g class="n who ${you}" data-wbtab="chat" transform="translate(70,10)"><rect class="bx" width="80" height="34" rx="17"/><path class="ic" d="M20 25a8 8 0 0 1 16 0M28 10a4 4 0 1 1 0 8a4 4 0 1 1 0-8"/><text x="46" y="22">You</text>` +
    wb2Title(you ? "You · an ask waits for you" : "You · the owner") + `</g>`;
  /* functions: a box each, in its colour, with its state word; a click opens the function's own card */
  fns.forEach((f, i) => {
    const cls = wb2FnCls(m, f, fv), word = wb2FnWord(m, f, fv), node = wb2FnNode(fv, f);
    const k = f.toLowerCase(), ic = WB2_ICONS[k] || "";
    const tip = [f, word, node && (node.why || node.line)].filter(Boolean).join(" · ");
    svg += `<g class="n fn${cls ? " " + cls : ""}" data-wbfn="${esc(k)}" transform="translate(${(fx(i) - WB2_FN_W / 2).toFixed(0)},${FY})"><rect class="bx" width="${WB2_FN_W}" height="${WB2_FN_H}" rx="8"/>` +
      (ic ? `<g class="ic" transform="translate(14,12) scale(0.85)">${ic}</g>` : "") +
      `<rect class="fnbar fn-${esc(k)}" width="4" height="${WB2_FN_H}" rx="2"/>` +
      (cls === "run" ? `<rect class="halo" width="${WB2_FN_W}" height="${WB2_FN_H}" rx="8"/>` : "") +
      `<text x="${ic ? 42 : 14}" y="24">${esc(f)}</text><text class="st" x="${ic ? 42 : 14}" y="40">${esc(word)}</text>` +
      (wb2BoxLine(node) ? `<text class="ln" x="${ic ? 42 : 14}" y="55">${esc(wb2BoxLine(node))}</text>` : "") +
      (cls === "ask" || cls === "block" ? `<g class="bdg ${cls}"><circle cx="${WB2_FN_W - 14}" cy="14" r="7"/><text x="${WB2_FN_W - 14}" y="18" text-anchor="middle">${cls === "ask" ? "?" : "!"}</text></g>` : "") +
      `${wb2Title(tip)}</g>`;
  });
  /* MK-8, the prototype's extras: who speaks to whom among the five, three lines at most (the busiest pairs, drawn as
     arcs over the row; the rest are in the closed dropdown under the picture), and a line from a function to the work
     it made, where the record says it made any */
  if (fv && !fv.failed){
    const at = f => fns.indexOf(f);
    (fv.speaks || []).filter(p => at(p.from) >= 0 && at(p.to) >= 0 && p.from !== p.to).slice(0, 3).forEach(p => {
      const x1 = fx(at(p.from)), x2 = fx(at(p.to)), lift = 18 + Math.abs(at(p.to) - at(p.from)) * 6;
      svg += `<path class="e talk" marker-end="url(#sxarrow)" d="M${x1.toFixed(0)} ${FY} Q${((x1 + x2) / 2).toFixed(0)} ${FY - lift} ${x2.toFixed(0)} ${FY}">${wb2Title(p.from + " speaks to " + p.to)}</path>`;
    });
    (fv.made || []).forEach(a => (a.makers || []).filter(x => at(x) >= 0).forEach(x => {
      const j = line.findIndex(nd => nd.kind === "work" && nd.name === a.art);
      if (j >= 0) svg += `<path class="e made" d="M${fx(at(x)).toFixed(0)} ${FB} L${lx(j).toFixed(0)} 232">${wb2Title(x + " made " + a.art)}</path>`;
    }));
  }
  /* the line of work: an engine opens its card, a filed thing opens itself; the deliverable is lit once it is delivered */
  line.forEach((node, i) => {
    if (node.kind === "eng"){
      const cls = wb2EngCls(m, node.e);
      svg += `<g class="n eng ${cls}" data-wbengine="${esc(node.e.name)}" transform="translate(${lx(i).toFixed(0)},250)">` +
        (cls === "run" ? `<circle class="halo" r="17"/>` : "") + `<circle class="bx" r="17"/><text x="0" y="4" text-anchor="middle">${esc(node.e.name)}</text>` +
        wb2Title([node.e.name, cls === "run" ? "running" : (cls === "ask" ? "waits on you" : (cls === "block" ? "failed" : "engine")),
                  node.e.timetable && node.e.timetable.on].filter(Boolean).join(" · ")) + `</g>`;   /* its slot, as Coordination's timetable has it */
    } else {
      const a = arts[node.name] || { versions: 0, slug: "" };
      const v = a.versions ? "v" + a.versions : "";
      const live = node.name === last && delivered ? " live" : "";
      const [to, by] = wb2WorkAt(line, i, a);
      svg += `<g class="n work${a.versions ? " done" : ""}${live}" ${to} transform="translate(${(lx(i) - 34).toFixed(0)},232)">` +
        `<rect class="bx" width="68" height="36" rx="4"/><text x="8" y="17">${esc(node.name)}</text><text class="v" x="8" y="30">${esc(v)}</text>` +
        wb2Title(node.name + (a.versions ? " · filed, " + v : " · not made yet" + by) + (live ? (m.live ? " · live" : " · delivered") : "")) + `</g>`;
    }
  });
  /* what the plan left out: under the line, muted, each with its word; a click opens its card, which says so too */
  out.forEach((e, i) => {
    svg += `<g class="n eng out" data-wbengine="${esc(e.name)}" transform="translate(${105 + i * 160},304)"><circle class="bx" r="8"/>` +
      `<text x="16" y="4">${esc(e.name)} · left out</text>` + wb2Title(e.name + " · left out of the plan") + `</g>`;
  });
  /* what the department knows */
  knows.forEach((k, i) => {
    const x = kx0(i).toFixed(0), w = kws[i];
    if (k[1] === null){
      const sh = bud ? Math.max(0, Math.min(1, Number(bud.share) || 0)) : 0;
      const tip = bud ? `Budget · ${bud.calls} of ${bud.calls_limit} calls, ${bud.usd} of ${bud.usd_limit} USD, ${bud.of}` : "Budget · not read yet";
      svg += `<g class="n" ${k[2]} transform="translate(${x},340)"><rect class="bx" width="${w}" height="32" rx="8"/><text x="10" y="20">${esc(k[0])}</text>` +
        `<rect class="bar0" x="66" y="13" width="${w - 78}" height="6" rx="3"/><rect class="bar1" x="66" y="13" width="${((w - 78) * sh).toFixed(1)}" height="6" rx="3"/>` +
        wb2Title(tip) + `</g>`;
      return;
    }
    svg += `<g class="n" ${k[2]} transform="translate(${x},340)"><rect class="bx" width="${w}" height="32" rx="8"/><text x="10" y="20">${esc(k[0])}</text><text class="v" x="${k[0].length * 8 + 16}" y="20">${esc(k[1])}</text>` +
      wb2Title(k[3]) + `</g>`;
  });
  svg += `</svg>`;
  const empty = !engs.length ? dpQuiet("No plan yet") : "";
  return wb2NowHtml(m, fv) + `<div class="wb2frame wb"><div class="wb2map wb">${svg}</div>` + wb2CardsHtml(m, fv, line, arts, knows, bud, out) + `</div>` + empty +
    wb2UnderHtml(fv);
}
/* A line of the record at rest (no counts at rest; a name such as v1, Round 2, D2 or F1 is a name, not a count): the
   line as it is when it holds no count; else the part before its first colon, the act without its detail, when that
   part holds none; else nothing. What is not at rest stays on the hover (a title), never lost. One rule for the Map's
   boxes and 24-functions.js's cards and Between them, so a fault's why, a run's line or the owner's own words that
   carry a number never print it at rest. */
const WB2_NAMED = /\b(?:v|D|F|Round )\d+\b/g;
function wb2Rest(line){
  const s = String(line || ""), counts = x => /\d/.test(x.replace(WB2_NAMED, ""));
  if (!counts(s)) return s;
  const head = s.split(/:\s/)[0];
  return head !== s && !counts(head) ? head : "";
}
/* a function's line under its state word, at rest and cut to the box; the whole line is the box's hover */
function wb2BoxLine(node){
  const line = wb2Rest((node && (node.why || node.line)) || "");
  if (!line) return "";
  return line.length > 20 ? line.slice(0, 19).replace(/\s+\S*$/, "") + "…" : line;
}
/* Under the picture, three closed dropdowns (the prototype's "Not recorded" pattern, 8b24f54): every message between the
   functions, who made each thing and who reads it, and what the record does not hold. A count is a bar, never a number. */
function wb2UnderHtml(fv){
  if (!fv || fv.failed) return "";
  const five = ["Identity", "Adaptation", "Priority", "Coordination", "Audit"];
  const talk = (fv.speaks || []).filter(p => five.indexOf(p.from) >= 0 && five.indexOf(p.to) >= 0);
  const most = talk.reduce((x, p) => Math.max(x, p.n || 0), 0) || 1;
  const dd = (label, rows) => rows ? `<details class="wb2dd wb"><summary>${wbEsc(label)}</summary>${rows}</details>` : "";
  const msgs = talk.length ? talk.map(p => `<div class="wb2ddrow">${wbChip(p.from)}<span class="wbarrow">&rarr;</span>${wbChip(p.to)}${dpBar(Math.min(1, (p.n || 0) / most))}</div>`).join("") : "";
  const made = (fv.made || []).filter(a => a.v).map(a => `<div class="wb2ddrow"><b>${wbEsc(a.art)}</b><span class="dpchk">made by ${wbEsc(a.by === "Owner" ? "you" : (a.by || "not recorded"))}` +
    `${(a.readers || []).length ? " · read by " + wbEsc(a.readers.join(", ")) : ""}</span></div>`).join("");
  const nr = (fv.not_recorded || []).length ? fv.not_recorded.map(x => `<div class="wb2ddrow"><span class="dpchk">${wbEsc(x)}</span></div>`).join("") : "";
  return dd("Messages between functions", msgs) + dd("Who made each thing", made) + dd("Not recorded", nr);
}
/* The same map as a list of cards, for a narrow viewer: people, the five, the work in line order, what it knows. */
function wb2CardsHtml(m, fv, line, arts, knows, bud, out){
  const row = (attrs, dot, name, word) => `<button type="button" class="wb2card wb" ${attrs}>${dot}<b>${wbEsc(name)}</b><span class="dpchk">${wbEsc(word)}</span></button>`;
  const fnDot = { run: "", ask: "warn", block: "block", wait: "wait", off: "off" };
  const people = row(`data-wbtab="chat"`, wbDot(wb2Asks(m).length ? "warn" : "off"), "You", wb2Asks(m).length ? "an ask waits for you" : "the owner");
  const five = (m.systems || []).map(s => {
    const cls = wb2FnCls(m, s.name, fv);
    return row(`data-wbfn="${wbEsc(s.name.toLowerCase())}"`, `<i class="wb2mk fn-${wbEsc(s.name.toLowerCase())}"></i>` + wbDot(fnDot[cls] === undefined ? "ok" : fnDot[cls]),
      s.name, wb2FnWord(m, s.name, fv));
  }).join("");
  const work = line.map((node, i) => {
    if (node.kind === "eng"){
      const cls = wb2EngCls(m, node.e);
      return row(`data-wbengine="${wbEsc(node.e.name)}"`, wbDot(cls === "run" ? "" : (cls === "ask" ? "warn" : cls)), node.e.name,
        cls === "run" ? "running" : (cls === "ask" ? "waits on you" : (cls === "block" ? "failed" : "engine")));
    }
    const a = arts[node.name] || { versions: 0, slug: "" };
    return row(wb2WorkAt(line, i, a)[0], wbDot(a.versions ? "ok" : "off"), node.name, a.versions ? "v" + a.versions : "not made yet");
  }).join("") + (out || []).map(e => row(`data-wbengine="${wbEsc(e.name)}"`, wbDot("off"), e.name, "left out")).join("");   /* after the line, as on the picture */
  const know = knows.map(k => k[1] === null
    ? `<button type="button" class="wb2card wb" ${k[2]}><b>${wbEsc(k[0])}</b>${dpBar(bud ? Math.max(0, Math.min(1, Number(bud.share) || 0)) : 0)}</button>`
    : row(k[2], "", k[0], /\d/.test(String(k[1])) ? k[3].split(" · ")[1] : k[1])).join("");   /* a count stays on the picture's own value */
  const group = (label, body) => `<div class="wb2cardg"><div class="dpk">${wbEsc(label)}</div>${body}</div>`;
  return `<div class="wb2cards wb">` + group("People", people) + group("Functions", five) + group("Work", work || dpQuiet("No plan yet")) + group("Knows", know) + `</div>`;
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
    const strip = dm ? (dm.artifacts || []).map(a => `<i class="${a.versions ? "on" : ""}${wb2Running(dm).indexOf(wbMakerByLine(dm, a.name)) >= 0 ? " run" : ""}" title="${wbEsc(a.name)}"></i>`).join("") : "";
    return `<button type="button" class="wb2dept wb" data-wb2go="${wbEsc(d.ref)}"><b><span class="dpdot ${wb2DotCls(cls)}"></span>${wbEsc(d.name)}</b><span class="wb2spark">${strip}</span></button>`;
  };
  const more = `<button type="button" class="wb2dept wb2new wb" data-wbtab="chat"><b>A new department</b><span class="dpchk">say what it is for, in Chat</span></button>`;
  return wb2NowHtml(m, undefined) + `<div class="wb2org wb">${depts.map(box).join("")}${more}</div>`;
}

/* ── Board: one thread, the department talking to itself ──────────────────── */
function wb2Turn(p){
  const said = p.line ? wbEsc(p.line) : wbEsc(wbCap(p.word || ""));
  const act = `<span class="dpchk">${wbEsc(wbActWord(p))} · ${wbEsc(wbWhen(p.at))}</span>`;
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
    if (wbIs(ds.wb2go)) wbLoadMap(ds.wb2go, true);   /* the organisation has no map of its own: its row is Root's chat */
    dpRender();
  }, true);
}
