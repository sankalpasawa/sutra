/* 23-screens.js -- the department screens, second design, behind a switch.

   The design of record is holding/plans/website-department/design-simplify.html
   (third pass, 2026-09-28): fewer words, no box without a decision, state as
   colour and motion, the Map as a fixed topology with the active parts lit,
   Chat as the one place to speak, the Board as one thread, Work as one table,
   every function as Activity and Settings with an About behind a disclosure,
   an engine card of its own.

   The switch is wbV2() in 22-website.js: `?screens=v2` in the address, or the
   row at the foot of the list, kept in localStorage. Off, 22-website.js draws
   what it drew before and nothing here runs. On, wbList and wbViewer hand
   their answer to wb2List and wb2Viewer below; everything that reads a
   record (map, steps, board, chat, engine, artifact) is 22-website.js's own
   loader, so the two designs read the same record the same way.

   Copy discipline is 22-website.js's: names, never paths; no counts at rest;
   no help text on a face; one quiet line for an empty state; every class is
   prefixed `wb2` and has a rule in panel.css (test_website.js V12). */

const WB2_TOP = [["chat", "Chat"], ["map", "Map"], ["board", "Board"], ["work", "Work"]];
const WB2_FN_PANES = [["activity", "Activity"], ["settings", "Settings"]];

/* ── state words, as colours ──────────────────────────────────────────────── */
function wb2Asks(m){ return (m.status && m.status.asks) || []; }
function wb2Running(m){ return ((m.status && m.status.running) || []).map(r => r.engine); }
function wb2Faults(m){ return ((m.health && m.health.checks) || []).filter(c => c.state === "block"); }
/* a function: waiting on you (an ask of its own), running now, quiet, or off */
function wb2FnCls(m, name){
  /* an ask waiting for the owner is Identity's: it is the one that asks */
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
function wb2Word(cls){ return ({ run: "running", ask: "waiting on you", block: "a fault", off: "off", ok: "quiet", "": "quiet" })[cls] || cls; }

/* ── the list: every section, nothing repeated in the pane ────────────────── */
function wb2Li(label, attrs, on, dot){
  return `<button type="button" class="o2li dpli wb2li${on ? " on" : ""}" ${attrs}><span class="dpdot ${wb2DotCls(dot)}${dot ? "" : " none"}"></span><span>${wbEsc(label)}</span></button>`;
}
function wb2List(n){
  const st = wbS(), m = st.map[n.ref], tab = wbTab(n.ref), dtab = dpS().tab[n.ref];
  if (!m) wbLoadMap(n.ref);
  const asks = m ? wb2Asks(m).length : 0;
  const top = `<div class="o2g dpg wb">` + WB2_TOP.map(([v, label]) =>
    wb2Li(label, `data-wbtab="${v}"`, tab === v || (v === "work" && tab === "art"), v === "chat" && asks ? "ask" : "")).join("") +
    wb2Li("Old screens", `data-wbv2="0"`, false, "") + `</div>`;
  const functions = dpGroup("Functions", DP_FUNCS.map(([v, label]) =>
    wb2Li(label, `data-dptab="${wbEsc(v)}"`, !tab && dtab === v, m ? wb2FnCls(m, label) : "")), null, "");
  const engines = dpGroup("Engines", ((m && m.engines) || []).map(e =>
    wb2Li(e.name, `data-wbengine="${wbEsc(e.name)}"`, tab === "engine" && st.sel[n.ref] === e.name, wb2EngCls(m, e))), null, m ? "No engines here" : "Not read yet");
  return { top, functions, engines, filed: "", apps: [] };
}

/* ── the head every section wears ─────────────────────────────────────────── */
function wb2Head(n, m){
  const st = wbS();
  const root = m.root && m.root !== n.ref && st.refs && st.refs[m.root];
  const crumb = root ? `<div class="wb2crumb"><button type="button" class="o2more wb" data-wb2go="${wbEsc(m.root)}">${wbEsc(root.name)}</button> &rsaquo; ${wbEsc(m.name)}</div>` : "";
  const sw = `<button type="button" role="switch" aria-checked="${m.stopped ? "false" : "true"}" class="wb2switch${m.stopped ? "" : " on"}" ` +
    (m.stopped ? `data-wbresume="1" title="Off. Start every engine."` : `data-wbstop="1" title="On. Stop every engine."`) + `></button>`;
  const live = m.live ? `<a class="o2more wb2live" href="${wbEsc(wbUrl(n.ref, "site/index.html"))}" target="_blank" rel="noopener">Live site</a>` : "";
  return crumb + `<div class="wb2head"><b>${wbEsc(m.name)}</b><span class="dpchk">${wbEsc(m.kind || "")}</span>${sw}${live}</div>`;
}
/* what is active now: names, never counts; nothing when nothing is */
function wb2NowHtml(m){
  const pills = [];
  wb2Running(m).forEach(e => pills.push(`<span class="wb2pill run">${wbEsc(e)} running</span>`));
  const asks = wb2Asks(m);
  if (asks.length) pills.push(`<span class="wb2pill ask">Waiting for you: ${wbEsc(asks.map(a => a.engine).filter((x, i, xs) => xs.indexOf(x) === i).join(", "))}</span>`);
  wb2Faults(m).forEach(c => pills.push(`<span class="wb2pill block" title="${wbEsc(c.line || "")}">${wbEsc(c.name)}</span>`));
  if (m.stopped) pills.push(`<span class="wb2pill off">Off</span>`);
  return `<div class="wb2now">${pills.join("")}</div>`;
}

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
  const knows = [
    ["Template", m.template || "", `data-dptab="adaptation"`],
    ["Rules", "", `data-dptab="identity"`],
    ["Record", "", `data-wbtab="work"`],
    ["Host", m.host || "this app's server", `data-dptab="identity"`]];
  const kx = i => 150 + i * ((W - 300) / 3);
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
  /* functions */
  fns.forEach((f, i) => {
    const cls = wb2FnCls(m, f);
    svg += `<g class="n fn ${cls}" data-dptab="${esc(f.toLowerCase())}" transform="translate(${(fx(i) - 70).toFixed(0)},120)"><rect class="bx" width="140" height="32" rx="8"/>` +
      (cls === "run" ? `<rect class="halo" width="140" height="32" rx="8"/>` : "") + `<text x="70" y="21" text-anchor="middle">${esc(f)}</text></g>`;
  });
  /* the line of work */
  line.forEach((node, i) => {
    if (node.kind === "eng"){
      const cls = wb2EngCls(m, node.e);
      svg += `<g class="n eng ${cls}" data-wbengine="${esc(node.e.name)}" transform="translate(${lx(i).toFixed(0)},250)">` +
        (cls === "run" ? `<circle class="halo" r="17"/>` : "") + `<circle class="bx" r="17"/><text x="0" y="4" text-anchor="middle">${esc(node.e.name)}</text></g>`;
    } else {
      const a = arts[node.name] || { versions: 0, slug: "" };
      const v = a.versions ? "v" + a.versions : "";
      svg += `<g class="n work${a.versions ? " done" : ""}" ${a.versions ? `data-wbart="${esc(a.slug)}"` : `data-wbtab="work"`} transform="translate(${(lx(i) - 34).toFixed(0)},232)">` +
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
    `<span><i class="wb2lg done"></i>filed</span><span><i class="wb2lg run"></i>running</span><span><i class="wb2lg ask"></i>waiting on you</span><span><i class="wb2lg block"></i>fault</span></div>`;
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

/* ── Work: one table, then the thing itself ───────────────────────────────── */
function wb2WorkHtml(n, m){
  const st = wbS();
  const rows = (m.artifacts || []).map(a => {
    const k = n.ref + ":" + a.slug, art = a.versions ? st.art[k] : null;
    if (a.versions && !art) wbLoadArt(n.ref, a.slug);
    const cur = art && (art.versions || [])[0];
    const chk = !a.versions ? "off" : (!cur ? "" : (cur.check && cur.check.ok ? "ok" : "block"));
    const by = a.name === "Brief" || a.name === "Request" ? "Identity, from your words" : (wbMakerOf(a.name) || "");
    const running = wb2Running(m).indexOf(wbMakerOf(a.name)) >= 0;
    return `<tr class="wb2tr${a.versions ? "" : " none"}"><td>${a.versions ? `<button type="button" class="o2more wb" data-wbart="${wbEsc(a.slug)}">${wbEsc(a.name)}</button>` : wbEsc(a.name)}</td>` +
      `<td class="wb2v">${a.versions ? "v" + a.versions + (running ? " &rarr;" : "") : ""}</td><td>${wbEsc(a.versions ? by : "not yet")}</td>` +
      `<td><span class="dpdot ${running ? "" : chk}"></span></td><td class="wb2when">${cur ? wbEsc(wbWhen(cur.at)) : ""}</td></tr>`;
  });
  return `<table class="wb2table wb"><tr><th>Thing</th><th>Latest</th><th>By</th><th>Check</th><th>When</th></tr>${rows.join("")}</table>`;
}

/* ── a function: Activity, Settings, and About behind a disclosure ────────── */
function wb2Row(who, what, when, dot){
  return `<div class="wb2row"><span class="dpdot ${dot || ""}"></span><b>${wbEsc(who)}</b><span>${wbEsc(what)}</span><span class="wb2when">${wbEsc(when || "")}</span></div>`;
}
function wb2About(label, v){
  if (!v || v.failed) return "";
  const s = v.start || {};
  const starts = (s.on || []).length ? `<div class="wbstep"><span class="dpk">On</span>${s.on.map(x => wbChip(wbCap(x))).join("")}</div>` : "";
  const held = (s.unless || []).length ? `<div class="wbstep"><span class="dpk">Unless</span>${s.unless.map(b => wbChip(b.by + ": " + b.name)).join("")}</div>` : "";
  const skills = (v.skills || []).length ? `<div class="wbstep">${v.skills.map(x => wbChip(x)).join("")}</div>` : "";
  return `<details class="wb2about wb"><summary>About ${wbEsc(label)}</summary><div class="wb2aboutb">` +
    (v.description ? `<div class="dpbig">${wbEsc(wbCap(v.description))}</div>` : "") + skills + starts + held + `</div></details>`;
}
/* Adaptation's ladder: one row an engine, a dot on the rung each of its steps runs on */
function wb2LadderHtml(n, m){
  const st = wbS(), engs = m.engines || [];
  const rows = engs.map(e => {
    const v = st.steps[n.ref + ":" + e.name];
    if (!v) wbLoadSteps(n.ref, e.name);
    const steps = (v && v.steps) || [];
    return `<tr><td>${wbEsc(e.name)}</td>` + WB_RUNGS.map(([r]) => `<td>` + steps.filter(s => s.rung === r).map(s =>
      `<span class="dpdot ${s.held ? "warn" : (s.rung === s.ceiling ? "ok" : "")}" title="${wbEsc(s.name)}"></span>`).join("") + `</td>`).join("") + `</tr>`;
  });
  return `<table class="wb2ladder wb"><tr><th></th>${WB_RUNGS.map(([r, name]) => `<th title="${wbEsc(name)}">${wbEsc(r)}</th>`).join("")}</tr>${rows.join("")}</table>`;
}
/* Priority's limits: one table, one Save that posts what changed */
function wb2LimitsHtml(n, m){
  const st = wbS(), v = st.steps[n.ref + ":Priority"];
  if (!v){ wbLoadSteps(n.ref, "Priority"); return dpSkel(); }
  const rows = (v.limits || []).map(l => {
    const kc = n.ref + ":env:" + l.engine + ":calls", ku = n.ref + ":env:" + l.engine + ":usd";
    const val = (k, d) => wbEsc(st.draft[k] !== undefined ? st.draft[k] : d);
    return `<tr><td>${wbEsc(l.engine)}</td><td><input type="number" min="0" step="1" data-wbdraft="${wbEsc(kc)}" value="${val(kc, l.calls)}" aria-label="calls a day"></td>` +
      `<td><input type="number" min="0" step="0.5" data-wbdraft="${wbEsc(ku)}" value="${val(ku, l.usd)}" aria-label="USD a day"></td>` +
      `<td>${dpBar(Math.min(1, (l.used_calls || 0) / (l.calls || 1)))}</td></tr>`;
  });
  const dirty = Object.keys(st.draft).some(k => k.indexOf(n.ref + ":env:") === 0);
  return `<table class="wb2table wb2edit wb"><tr><th>Engine</th><th>Calls</th><th>USD a day</th><th>Used</th></tr>${rows.join("")}</table>` +
    `<div class="wb2save${dirty ? " show" : ""}">${wbBtn("Save", `data-wbenvall="1"`, "dpstamp")}</div>`;
}
function wb2LineHtml(m){
  const running = wb2Running(m);
  const engs = m.engines || [], out = [];
  const work = name => `<span class="wb2node work">${wbEsc(name)}</span>`;
  if (engs.length) out.push(work(engs[0].reads));
  engs.forEach(e => { out.push(`<span class="wb2node${running.indexOf(e.name) >= 0 ? " now" : ""}">${wbEsc(e.name)}</span>`); out.push(work(e.writes)); });
  return `<div class="wb2line">${out.join(`<span class="wbarrow">&rarr;</span>`)}</div>`;
}
function wb2Activity(n, m, fn, label, v){
  const st = wbS();
  if (fn === "identity"){
    const b = st.board[n.ref]; if (!b) wbLoadBoard(n.ref);
    const said = [];
    ((b && b.threads) || []).forEach(t => (t.posts || []).forEach(p => { if (p.src === "Owner" || (p.dst || []).indexOf("Owner") >= 0) said.push(p); }));
    said.sort((a, c) => c.n - a.n);
    const asks = wb2Asks(m).length ? wbAsksHtml(m) : "";
    return asks + (said.length ? said.slice(0, 12).map(p => wb2Row(p.src === "Owner" ? "your words" : (WB_ACTS[p.msg_type] || p.msg_type),
      p.line || wbCap(p.word || ""), wbWhen(p.at), p.msg_type === "request" && p.src !== "Owner" ? "warn" : "ok")).join("") : dpQuiet("Nothing said yet"));
  }
  if (fn === "adaptation"){
    const b = st.board[n.ref]; if (!b) wbLoadBoard(n.ref);
    return wb2LadderHtml(n, m) + wbIdeasHtml(b);
  }
  if (fn === "priority") return wb2LimitsHtml(n, m);
  if (fn === "coordination"){
    const t = (v && v.table) || {};
    const running = wb2Running(m);
    return wb2LineHtml(m) +
      (t.first || []).map(x => wb2Row("first", x, "", "")).join("") +
      (t.may_post || []).map(r => wb2Row("may speak", r.from + " " + (WB_ACTS[r.act] || r.act) + " " + (r.to || []).join(", "), "", "")).join("") +
      wb2Row("held", running.length ? running.join(", ") + " holds the line" : "nothing", "", running.length ? "warn" : "");
  }
  if (fn === "audit"){
    const steps = (v && v.steps) || [];
    const strip = `<div class="wb2runs">` + steps.map(s => `<i class="${!s.ran ? "none" : (s.last && s.last.ok === false ? "bad" : "")}" title="${wbEsc(s.name)}"></i>`).join("") + `</div>`;
    const rows = (m.recent || []).filter(r => r.engine === "Audit").map(r => wb2Row("checked", r.what || "", wbWhen(r.at), WB_DOTS[r.status] || ""));
    return strip + (rows.length ? rows.join("") : dpQuiet("No check has run here"));
  }
  return "";
}
function wb2FnHtml(n, m, fn){
  const st = wbS(), label = wbCap(fn), k = n.ref + ":fn:" + fn, v = st.steps[n.ref + ":" + label];
  if (!v) wbLoadSteps(n.ref, label);
  const pane = st.pane[k] || "activity";
  const cls = wb2FnCls(m, label);
  const state = `<div class="wb2state"><span class="dpdot ${wb2DotCls(cls)}"></span>${wbEsc(wb2Word(cls))}` +
    (fn === "identity" ? ` · ${wbEsc(m.control === "granted" ? "granted" : "held")} · ${wbEsc(m.owner || "no owner")}` : "") + `</div>`;
  const tabs = dpTabsHtml(pane, WB2_FN_PANES, `data-wbpanekey="${wbEsc(k)}" data-wbpane`);
  const body = pane === "settings" ? wbSettingsHtml(n.ref, fn) : wb2Activity(n, m, fn, label, v);
  return state + tabs + body + wb2About(label, v);
}

/* ── an engine: what it reads and writes, its runs, its budget, its rung, its steps ── */
function wb2EngineHtml(n, m){
  const st = wbS(), name = st.sel[n.ref], k = n.ref + ":" + name;
  const e = (m.engines || []).filter(x => x.name === name)[0];
  if (!e) return dpQuiet("No such engine");
  const ev = st.engine[k]; if (!ev) wbLoadEngine(n.ref, name);
  const v = st.steps[k]; if (!v) wbLoadSteps(n.ref, name);
  const arts = {}; (m.artifacts || []).forEach(a => { arts[a.name] = a; });
  const cls = wb2EngCls(m, e);
  const work = nm => { const a = arts[nm] || {}; return `<span class="wb2node work">${wbEsc(nm)}${a.versions ? `<small>v${a.versions}</small>` : ""}</span>`; };
  const flow = `<div class="wb2flow">${work(e.reads)}<span class="wbarrow">&rarr;</span><span class="wb2node${cls === "run" ? " now" : ""}">${wbEsc(name)}</span><span class="wbarrow">&rarr;</span>${work(e.writes)}</div>`;
  const runs = ((ev && ev.runs) || []).slice(0, 10);
  const strip = `<div class="wb2runs">` + (runs.length ? runs.map(r => `<i class="${r.status === "failed" ? "bad" : (r.status === "running" ? "now" : "")}" title="${wbEsc((r.what || "") + " · " + wbWhen(r.at || r.started))}"></i>`).join("") : `<i class="none"></i>`) + `</div>`;
  const env = e.envelope || {};
  const steps = (v && v.steps) || [];
  const rungs = steps.map(s => WB_RUNGS.map(r => r[0]).indexOf(s.rung)).filter(i => i >= 0);
  const low = rungs.length ? WB_RUNGS[Math.min.apply(null, rungs)] : null;
  const stepRows = steps.map(s => dpRunRow(s.name, s.rung_name + (s.last ? " · " + (WB_WORDS[s.last.status] || "") : ""),
    !s.ran ? "off" : (s.last && (s.last.ok === false || s.last.status === "failed") ? "block" : "ok")));
  const last = runs[0];
  return `<div class="wb2state"><span class="dpdot ${wb2DotCls(cls)}"></span>${wbEsc(wb2Word(cls))}</div>` + flow +
    `<div class="wb2kv"><span class="dpk">Runs</span>${strip}</div>` +
    `<div class="wb2kv"><span class="dpk">Budget</span>${dpBar(Math.min(1, (env.used_calls || 0) / (env.calls || 1)))}</div>` +
    (low ? `<div class="wb2kv"><span class="dpk">Rung</span>${wbRungHtml({ rung: low[0], rung_name: low[1] })}<span class="dpchk">${wbEsc(low[1])}</span></div>` : "") +
    (stepRows.length ? `<div class="dpk">Steps</div>` + stepRows.join("") : "") +
    (last ? `<details class="wb2about wb"><summary>Last run</summary><div class="wb2aboutb">${wbRunRow(last, last.wrote ? ` <button type="button" class="o2more wb" data-wbart="${wbEsc(last.wrote.art.toLowerCase().replace(/[^a-z0-9]+/g, "-"))}" data-wbpane="trace" data-wbv="${last.wrote.v}">Trace</button>` : "")}</div></details>` : "");
}

/* ── the viewer ───────────────────────────────────────────────────────────── */
function wb2Viewer(n){
  const st = wbS(), m = st.map[n.ref], tab = wbTab(n.ref);
  if (!m) return null;
  const shell = (title, body) => dpViewerShell(title, wb2Head(n, m) + body, "wb wb2");
  if (tab === "chat") return shell("Chat", wbChatHtml(n, m));
  if (tab === "map") return shell("Map", wb2MapHtml(n, m));
  if (tab === "board") return shell("Board", wb2BoardHtml(n, m));
  if (tab === "work") return shell("Work", wb2WorkHtml(n, m));
  if (tab === "engine") return shell(st.sel[n.ref] || "Engine", wb2EngineHtml(n, m));
  if (tab === "art"){
    const a = (m.artifacts || []).filter(x => x.slug === st.sel[n.ref])[0];
    return shell(a ? a.name : "Work", wbArtHtml(n));
  }
  const dtab = dpS().tab[n.ref] || "now";
  if (dtab === "now"){ st.tab[n.ref] = "chat"; return shell("Chat", wbChatHtml(n, m)); }
  if (DP_FUNCS.some(f => f[0] === dtab)) return shell(wbCap(dtab), wb2FnHtml(n, m, dtab));
  if (dtab === "people"){
    dpLoadPeople(n.ref);
    const asks = wb2Asks(m);
    return shell("People", dpPeopleCard() + (asks.length ? wb2Row("waits", "an ask for you, in Chat", "", "warn") : ""));
  }
  return null;
}

/* ── handlers of this file's own ──────────────────────────────────────────── */
if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    if (S.screen !== "org2") return;
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-wbenvall],[data-wb2go],[data-wbv2]") : null;
    if (!t) return;
    const st = wbS(), ds = t.dataset || {}, ref = S.dp && S.dp.sel;
    ev.preventDefault(); ev.stopPropagation();
    if (ds.wbv2 !== undefined){
      st.v2 = ds.wbv2 === "1";
      try { if (typeof localStorage !== "undefined") localStorage.setItem("sutra.screens", st.v2 ? "v2" : "v1"); } catch (e) {}
      dpRender(); return;
    }
    if (ds.wb2go !== undefined){
      st.tab[ds.wb2go] = "map";
      if (typeof o2Select === "function") o2Select(ds.wb2go);
      wbLoadMap(ds.wb2go, true); dpRender(); return;
    }
    if (ds.wbenvall !== undefined && ref){
      const keys = Object.keys(st.draft).filter(k => k.indexOf(ref + ":env:") === 0), engines = {};
      keys.forEach(k => { const [, , name, what] = k.split(":"); (engines[name] = engines[name] || {})[what] = Number(st.draft[k]); });
      const posts = Object.keys(engines).map(name => wbPost(ref, "envelope", Object.assign({ engine: name }, engines[name]), ref + ":env:" + name + ":calls"));
      Promise.all(posts).then(() => { keys.forEach(k => delete st.draft[k]); wbLoadSteps(ref, "Priority", true); });
    }
  }, true);
}
