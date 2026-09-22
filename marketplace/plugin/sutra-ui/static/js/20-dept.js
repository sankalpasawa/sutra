/* 20-dept.js -- the department screen: what the Org structure tree shows when a
   department is selected (holding/plans/department-screen/{PRD,LLD,BUILD-PLAN}.md).

   It registers no destination and no SCREENS entry of its own. 19-org2.js owns
   the tree, the selection and the strip; when the selected node is a department
   or an organisation its list column and viewer delegate here (LLD section 4,
   "Mount point"), and everything else on that screen is untouched.

   Reuse (LLD section 5): o2S/o2Data/o2Kind/o2Select/o2ViewerShell as-is;
   o2Group/o2Row copied and re-scoped to `.dp`; o2LoadDept's busy-guard copied
   into every dpLoad*; decideProposal/loadProposals (08-boot.js) as-is for Stamp
   and Refuse. Every handler here is delegated and scoped to `.dp`, so nothing
   fires on another screen (the 18-modules.js discipline 19-org2.js names).

   Copy discipline (founder, 2026-09-14 + D78): names, never paths; no counts at
   rest; no help text; one quiet line and at most one action per empty state;
   every colour a panel.css token. The word "charter" belongs to the raw rows of
   an Exact tab and nowhere else on a card. */

const DP_MORE = 4;                       /* names per list group before "more…" */
const DP_FUNCS = [["identity", "Identity"], ["adaptation", "Adaptation"],
                  ["priority", "Priority"], ["coordination", "Coordination"],
                  ["audit", "Audit"]];

/* ── state ────────────────────────────────────────────────────────────────── */
/* One slice, lazily initialised, exactly the guard o2S() uses (19-org2.js:35-42).
   The per-card reads carry the ref they were read for, so a second department
   opened while the first is still in flight can never paint the first one's
   rows. `busy` is keyed by card AND ref for the same reason. */
function dpS(){
  if (!S.dp) S.dp = { sel:null, tab:{}, pane:{}, engineSel:null, filedSel:null, personSel:null, chatMode:{},
                      loading:{}, error:{}, busy:{}, more:{}, confirm:null,
                      identity:null, now:null, running:null, waits:null,
                      adaptation:null, priority:null, coordination:null, audit:null,
                      engines:null, engineRuns:{}, engineData:{}, filed:null,
                      people:null, meters:null,
                      /* slice I: the template each function runs, the picker, the
                         ask just filed, and the chats started on this department */
                      functions:null, fnPick:null, fnAsked:{}, chatStart:{}, selName:"" };
  return S.dp;
}
function dpEsc(x){ return (typeof esc === "function") ? esc(x) : String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
function dpRender(){ if (typeof render === "function") render(); }
function dpNow(){ return Date.now(); }

/* ── loaders ──────────────────────────────────────────────────────────────── */
/* One read per card, shaped after o2LoadDept (19-org2.js:162-181): a per-card,
   per-department busy flag so a second call while one is in flight is a no-op,
   the error text kept beside the card rather than thrown, and a `force` that
   re-reads. The answer is dropped unless the department it was read for is
   still the open one. */
async function dpLoad(key, ref, path, force){
  const st = dpS();
  if (!ref) return;
  if (st[key] && st[key].ref === ref && !force) return;
  const lock = key + ":" + ref;
  if (st.busy[lock]) return;                            /* one read in flight per card */
  st.busy[lock] = true;
  st.loading[key] = true;
  try {
    const r = await apiGet(path);
    if (dpS().sel === ref){ st[key] = Object.assign({ ref: ref }, r || {}); delete st.error[key]; }
  } catch (e) {
    if (dpS().sel === ref) st.error[key] = (e && e.message) || String(e);
  }
  delete st.busy[lock];
  delete st.loading[key];
  dpRender();
}
function dpUrl(ref, tail){ return "/api/dept/" + encodeURIComponent(ref) + "/" + tail; }
function dpLoadNow(ref, force){ return dpLoad("now", ref, dpUrl(ref, "now"), force); }
function dpLoadRunning(ref, force){ return dpLoad("running", ref, dpUrl(ref, "running"), force); }
function dpLoadWaits(ref, force){ return dpLoad("waits", ref, dpUrl(ref, "waits"), force); }
/* Identity is read when its card OPENS, not when the department does (drift
   from LLD section 4, which fires every loader from dpSelect): opening a
   department must cost the three reads Now needs and no more, and the
   call-on-render pattern is the one o2LoadApps already uses (19-org2.js:639). */
function dpLoadIdentity(ref, force){ return dpLoad("identity", ref, dpUrl(ref, "identity"), force); }
/* The other four functions read the same way Identity does: when their own
   card opens, never when the department does. */
function dpLoadAdaptation(ref, force){ return dpLoad("adaptation", ref, dpUrl(ref, "adaptation"), force); }
function dpLoadPriority(ref, force){ return dpLoad("priority", ref, dpUrl(ref, "priority"), force); }
function dpLoadCoordination(ref, force){ return dpLoad("coordination", ref, dpUrl(ref, "coordination"), force); }
function dpLoadAudit(ref, force){ return dpLoad("audit", ref, dpUrl(ref, "audit"), force); }
/* Engines is read when the LIST COLUMN paints, not when a card opens: the
   group carries a state word per row (A18), so the column itself needs it. */
function dpLoadEngines(ref, force){ return dpLoad("engines", ref, dpUrl(ref, "engines"), force); }
/* The two engine-scoped reads are kept per engine, so opening a second engine
   never drops the first one's rows. The guard is dpLoad's, widened by one key:
   a read is in flight per department AND per engine. */
const DP_ENG_READS = { engineRuns: "runs", engineData: "data" };
async function dpLoadEngine(key, ref, id, force){
  const st = dpS();
  if (!ref || !id) return;
  const bag = st[key];
  if (bag[id] && bag[id].ref === ref && !force) return;
  const lock = key + ":" + ref + ":" + id;
  if (st.busy[lock]) return;
  st.busy[lock] = true;
  try {
    const r = await apiGet(dpUrl(ref, "engines/" + encodeURIComponent(id) + "/" + DP_ENG_READS[key]));
    if (dpS().sel === ref){ bag[id] = Object.assign({ ref: ref }, r || {}); delete st.error[lock]; }
  } catch (e) {
    if (dpS().sel === ref) st.error[lock] = (e && e.message) || String(e);
  }
  delete st.busy[lock];
  dpRender();
}
function dpLoadEngineRuns(ref, id, force){ return dpLoadEngine("engineRuns", ref, id, force); }
function dpLoadEngineData(ref, id, force){ return dpLoadEngine("engineData", ref, id, force); }
/* Filed work and People are read when the LIST COLUMN paints, the way Engines
   is: the Filed work row carries a version count (A24) and the People group
   carries names (A25), so the column itself needs both answers -- a card that
   opened first would have nothing to open. */
function dpLoadFiled(ref, force){ return dpLoad("filed", ref, dpUrl(ref, "filed"), force); }
function dpLoadPeople(ref, force){ return dpLoad("people", ref, dpUrl(ref, "people"), force); }
/* The meters are read when a card that DRAWS one opens -- Now, and an engine's
   Engine tab -- never when the department does. Opening a department still
   costs the three reads Now needs (S14); a month of run rows behind four bars
   is not one of them. */
function dpLoadMeters(ref, force){ return dpLoad("meters", ref, dpUrl(ref, "meters"), force); }
/* Slice I: which template each function runs here, read when a function card
   that shows its template line opens -- never when the department does. */
function dpLoadFunctions(ref, force){ return dpLoad("functions", ref, dpUrl(ref, "functions"), force); }

/* ── selection ────────────────────────────────────────────────────────────── */
/* Opening a department, mirroring o2Select (19-org2.js:250-261): everything the
   last department answered is dropped, Now is the card, and the three reads it
   needs go out together. The tree's own selection is o2Select's job and is not
   touched here -- this runs INSIDE it. */
function dpSelect(ref){
  const st = dpS();
  if (!ref) return;
  if (st.sel !== ref){
    st.sel = ref;
    st.now = null; st.running = null; st.waits = null; st.identity = null;
    st.adaptation = null; st.priority = null; st.coordination = null; st.audit = null;
    st.engines = null; st.filed = null; st.people = null; st.meters = null;
    st.engineRuns = {}; st.engineData = {};
    st.engineSel = null; st.filedSel = null; st.personSel = null; st.confirm = null;
    st.more = {}; st.error = {}; st.loading = {}; st.pane = {}; st.chatMode = {};
    st.functions = null; st.fnPick = null; st.fnAsked = {}; st.chatStart = {};
    dpFrameDrop();                                       /* a chat belongs to its department */
  }
  if (!st.tab[ref]) st.tab[ref] = "now";                /* A2: Now without a click */
  dpLoadNow(ref);
  dpLoadRunning(ref);
  dpLoadWaits(ref);
}

/* ── list column ──────────────────────────────────────────────────────────── */
/* dpRow and dpGroup are o2Row/o2Group (19-org2.js:600-609) with the department
   screen's class prefix. Both classes are carried on every element: the `.o2`
   one so the column keeps the Org screen's layout rules with no new CSS, the
   `.dp` one so this screen can refine what is its own. A group with no rows
   still paints -- all seven are always on screen (A33) -- with one quiet line
   and nothing else. */
function dpRow(label, attrs, on, cls){
  return `<button type="button" class="o2li dpli${on ? " on" : ""}${cls ? " " + cls : ""}" ${attrs}><span>${dpEsc(label)}</span></button>`;
}
function dpGroup(label, rows, key, quiet){
  const st = dpS();
  const head = `<div class="o2gl dpgl">${dpEsc(label)}</div>`;
  if (!rows.length) return `<div class="o2g dpg">${head}<div class="o2quiet dpq">${dpEsc(quiet)}</div></div>`;
  /* A group with no key is a FIXED set -- Now's one row, Functions' five -- and
     is never cut short: "more…" belongs to lists the department grew. */
  if (!key) return `<div class="o2g dpg">${head}${rows.join("")}</div>`;
  const all = !!st.more[key];
  const shown = all ? rows : rows.slice(0, DP_MORE);
  const more = rows.length > DP_MORE && !all
    ? `<button type="button" class="o2more dpmore" data-dpmore="${dpEsc(key)}">more…</button>` : "";
  return `<div class="o2g dpg">${head}${shown.join("")}${more}</div>`;
}
/* One filed row: the name, and one dot per version of it. A count at rest is
   the one thing this screen never prints (A28), so the versions are dots; a
   work item filed once carries no mark at all, because the dots are there to
   say "this one has been re-filed", not to number what has not. The row wears
   `.dpeng` for its layout -- name left, mark right -- which is the rule the
   engine row already carries, not a second one written for this. */
const DP_VER_DOTS = 6;                   /* the longest chain in the store is 6 */
function dpVerDots(n){
  const k = Math.min(Number(n) || 0, DP_VER_DOTS);
  if (k < 2) return "";
  return `<span class="dpdots">${new Array(k).fill("<i></i>").join("")}</span>`;
}
function dpFiledRow(f){
  const st = dpS();
  const on = st.filedSel === f.id && st.tab[st.sel] === "filed";
  return `<button type="button" class="o2li dpli dpeng${on ? " on" : ""}" data-dpfiled="${dpEsc(f.id || "")}">` +
    `<span>${dpEsc(f.label)}</span>${dpVerDots(f.versions)}</button>`;
}
/* The people of a department, in the PRD's order: the owner first, then the
   role charters (A25). With no role charter written -- which is every
   department today -- that is the owner alone, and with no owner either it is
   the group's one quiet line. */
function dpPeople(read){
  if (!read) return [];
  const out = [];
  const o = read.owner || {};
  if (o.name) out.push({ key: "owner", name: o.name, stamps: o.stamps || "", seen: o.seen || [] });
  (read.roles || []).forEach(r => out.push({ key: r.charter_id || r.title, name: r.name || r.title,
                                             stamps: r.stamps || "", seen: r.seen || [] }));
  return out;
}
function dpPersonRow(p){
  const st = dpS();
  const on = st.personSel === p.key && st.tab[st.sel] === "people";
  return dpRow(p.name, `data-dpperson="${dpEsc(p.key)}"`, on);
}
/* Apps are the Org screen's own answer, read by the Org screen's own loader
   (A26): o2LoadApps holds `/api/modules?subtree=0&department=<ref>` and the
   cache behind it, so this column reads what that loader put there rather than
   asking the same question a second way. `undefined` is unread and `null` is
   in flight -- both are the quiet line, and neither is "no apps". */
function dpApps(ref){
  const apps = (typeof o2S === "function") ? o2S().apps[ref] : undefined;
  if (apps === undefined && typeof o2LoadApps === "function") o2LoadApps(ref);
  return apps || [];
}
function dpAppsQuiet(ref){
  const apps = (typeof o2S === "function") ? o2S().apps[ref] : undefined;
  return apps ? "No apps yet" : "Not read yet";
}
function dpAppOn(m){
  const st = (typeof o2S === "function") ? o2S() : null;
  return !!(st && st.view === "app" && st.app && st.app.id === m.id);
}
const DP_GROUPS = ["Now", "Functions", "Engines", "Filed work", "People", "Documents", "Apps"];
function dpListHtml(n, d, dept, err){
  const st = dpS();
  if (st.sel !== n.ref) dpSelect(n.ref);   /* the first paint opens it, as o2ListHtml does for Apps */
  const tab = st.tab[n.ref] || "now";
  const filed = (dept && dept.filed) || [];
  const docs = (dept && dept.docs) || [];
  let groups = "";
  groups += dpGroup("Now", [dpRow("Now", `data-dptab="now"`, tab === "now")], null, "");
  groups += dpGroup("Functions", DP_FUNCS.map(([v, label]) =>
    dpRow(label, `data-dptab="${dpEsc(v)}"`, tab === v)), null, "");
  /* People and Apps read routes that land in a later slice; until then the
     group is on screen and says so in one line rather than showing nothing. */
  dpLoadEngines(n.ref);                    /* call-on-render, as o2LoadApps does */
  const eng = (st.engines && st.engines.ref === n.ref) ? st.engines : null;
  groups += dpGroup("Engines", ((eng && eng.engines) || []).map(dpEngRow), "engines",
    eng ? "No engines here" : (st.error.engines ? "Could not read" : "Not read yet"));
  /* Filed work reads its own route for the version count (A24); until that
     answer lands the rows the Org screen already loaded are shown, so the
     group is never blank for a department that has filed something. */
  dpLoadFiled(n.ref);
  const fread = (st.filed && st.filed.ref === n.ref) ? st.filed : null;
  const rows = (fread && fread.filed) || filed;
  groups += dpGroup("Filed work", rows.map(dpFiledRow), "filed",
    st.error.filed ? "Could not read" : "Nothing filed yet");
  dpLoadPeople(n.ref);
  const ppl = (st.people && st.people.ref === n.ref) ? st.people : null;
  groups += dpGroup("People", dpPeople(ppl).map(dpPersonRow), "people",
    ppl ? "No people yet" : (st.error.people ? "Could not read" : "Not read yet"));
  groups += dpGroup("Documents", docs.map(x =>
    dpRow(x.title, `data-dpdoc="${dpEsc(x.path)}" data-dptitle="${dpEsc(x.title)}"`, false)), "docs", "No documents yet");
  groups += dpGroup("Apps", dpApps(n.ref).map(m =>
    dpRow(m.name, `data-dpapp="${dpEsc(m.id)}"`, dpAppOn(m))), "apps", dpAppsQuiet(n.ref));
  if (err) groups = `<div class="o2quiet dpq">Sutra did not answer for ${dpEsc(n.name)}</div>` + groups;
  /* `.dp` on the column itself: the delegated handlers below gate on
     closest(".dp"), the way 19-org2.js gates on closest(".o2"), and the two
     children of `.o2body` must stay its direct children for the layout. */
  return `<div class="o2list dplist dp">${groups}</div>`;
}

/* ── viewer ───────────────────────────────────────────────────────────────── */
/* The frame is the Org screen's own viewer (`.o2viewer`/`.o2vh`/`.o2vb`,
   19-org2.js:670-672) carried as a second class, so the department card
   inherits its layout with no new rule. The close button is dropped on
   purpose: the department card is where this screen RESTS, so there is
   nothing behind it to close back to (drift from reuse row 3, stated). */
function dpViewerShell(title, body, cls){
  return `<div class="o2viewer dpviewer dp${cls ? " " + cls : ""}"><div class="o2vh"><b>${dpEsc(title)}</b></div><div class="o2vb">${body}</div></div>`;
}
function dpQuiet(line){ return `<div class="o2quiet dpq">${dpEsc(line)}</div>`; }
function dpSkel(){ return [220, 180, 260].map(w => `<div class="o2skel" style="width:${w}px"></div>`).join(""); }
function dpCard(title, body){ return `<div class="dpcard"><h3>${dpEsc(title)}</h3>${body}</div>`; }

/* One line of a list: the name, what the record says under it, and a dot that
   carries the record's own word for how it stands. The dot is a colour and
   nothing else -- there is no number beside it anywhere on this screen (A28). */
function dpRunRow(label, note, dot, extra){
  return `<div class="dprow"><span class="dpdot${dot ? " " + dot : ""}"></span>` +
    `<span>${dpEsc(label)}${note ? `<div class="dpchk">${dpEsc(note)}</div>` : ""}${extra || ""}</span></div>`;
}
/* How much of the window is left, as a share of it. A bar, never a number:
   the owner needs to see "soon" or "not yet", and a count at rest is the one
   thing this screen does not show (A28). */
function dpLeft(a){
  const win = Number(a.window_ms) || 0, made = Number(a.created_ms) || 0;
  if (!win || !made) return 1;
  const left = (made + win - dpNow()) / win;
  return left < 0 ? 0 : (left > 1 ? 1 : left);
}
function dpBar(share, cls){
  const pct = Math.round(share * 1000) / 10;
  return `<div class="dpbar${cls ? " " + cls : ""}"><i style="width:${pct}%"></i></div>`;
}
/* One ask. The sentence the asker wrote, what happens if the window closes on
   it, the window itself as a bar, and the two answers. Stamp and Refuse go
   through decideProposal (08-boot.js:145-153) -- the same call the Approvals
   panel makes, so this screen adds no write path of its own (A5). */
function dpAskHtml(a){
  const st = dpS();
  const share = dpLeft(a);
  const hard = !!a.irreversible;
  const gone = share <= 0;
  const id = dpEsc(a.id);
  /* A32: an ask whose default leaves this machine is stamped TWICE. The first
     click arms it and says what it will do; the second is the answer. Nothing
     is posted in between (dpDecide is not reached until the ask is armed). */
  const armed = hard && st.confirm === a.id;
  const acts = gone ? "" :
    `<button type="button" class="btn dpstamp" data-dpdecide="${id}" data-dpok="1">${armed ? "Stamp, it leaves this machine" : "Stamp"}</button>` +
    `<button type="button" class="btn" data-dpdecide="${id}" data-dpok="0">Refuse</button>`;
  const line = gone ? `The window closed: ${dpEsc(a.default || "Nothing happens")}`
                    : `If nothing is done: ${dpEsc(a.default || "Nothing happens")}`;
  return `<div class="dpask${hard ? " hard" : ""}${gone ? " gone" : ""}" data-dpask="${id}">` +
    `<div class="dpasks">${dpEsc(a.summary || "")}</div>` +
    `<div class="dpaskd">${line}</div>` +
    (gone ? "" : dpBar(share, hard ? "hard" : "")) + acts + `</div>`;
}
/* ── the month's meters ────────────────────────────────────────────────────
   A27: what the department did this calendar month -- runs, asks, refuses and
   spend -- each as a bar and never as a number (A28). The bar is this month
   against the department's OWN busiest month, because no record anywhere
   carries a target; what the owner reads off it is "busy or quiet, for us".
   A meter with nothing on record is not a zero: it says so in its own line. */
function dpMeterHtml(m){
  const of = Number(m.of) || 0, v = Number(m.value) || 0;
  return dpCell(m.label, m.reading ? dpBar(of ? Math.min(1, v / of) : 0)
                                   : dpQuiet("No reading yet"));
}
function dpMeters(){
  const st = dpS();
  const read = (st.meters && st.meters.ref === st.sel) ? st.meters : null;
  return (read && read.meters) || [];
}
/* Nothing read anywhere draws no card at all, so a department with nothing
   open still says exactly one line on Now (A9). */
function dpMetersHtml(){
  const rows = dpMeters();
  if (!rows.some(m => m.reading)) return "";
  return dpCard("Meters", `<div class="dpmets">${rows.map(dpMeterHtml).join("")}</div>`);
}

/* Now: what is waiting on the owner, what is stuck, what is moving. When all
   three are empty the card says so ONCE (A9) rather than three times. */
function dpNowHtml(){
  const st = dpS(), ref = st.sel;
  const mine = k => (st[k] && st[k].ref === ref) ? st[k] : null;
  const nowR = mine("now"), runR = mine("running"), waitR = mine("waits");
  const failed = st.error.now || st.error.running || st.error.waits;
  if (!nowR && !runR && !waitR) return failed ? dpQuiet("Could not read") : dpSkel();
  const asks = (nowR && nowR.asks) || [];
  const waits = (waitR && waitR.waits) || [];
  const running = (runR && runR.running) || [];
  const meters = dpMetersHtml();
  if (!asks.length && !waits.length && !running.length){
    return failed ? dpQuiet("Could not read") : dpQuiet("Nothing waiting on you") + meters;
  }
  let body = "";
  if (asks.length) body += dpCard("Asks", asks.map(dpAskHtml).join(""));
  if (waits.length) body += dpCard("Waits", waits.map(w => dpRunRow(w.objective, w.state)).join(""));
  if (running.length) body += dpCard("Running", running.map(r => dpRunRow(r.goal, "")).join(""));
  return body + meters;
}

/* ── the chat every card keeps ─────────────────────────────────────────────
   Written once here and reused by every function card and every engine card
   (LLD section 4). Two readings of ONE row array, never two stores: Summary
   is the turn as a person reads it -- who, to whom, the line -- and Exact is
   the record itself. Exact is the one place on this screen where a raw path,
   or the word the card is forbidden to say, is allowed to appear (A29). */
const DP_MODES = [["summary", "Summary"], ["exact", "Exact"]];
const DP_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/* A record's own stamp, read as a person reads one: the clock when the record
   carries a time, the day when it carries only a date (a governance finding is
   dated, not timed), and nothing at all when it carries neither. */
function dpWhen(at){
  const s = String(at || "");
  const t = /T(\d\d:\d\d)/.exec(s);
  if (t) return t[1];
  const d = /^(\d{4})-(\d\d)-(\d\d)$/.exec(s);
  return d ? (Number(d[3]) + " " + (DP_MON[Number(d[2]) - 1] || "")).trim() : "";
}
function dpStamp(ms){
  const n = Number(ms) || 0;
  if (!n) return "";
  const d = new Date(n);
  return d.getDate() + " " + (DP_MON[d.getMonth()] || "");
}
/* Today reads as a clock, any other day as the day. The owner asking "when"
   means "how long ago" while it is today, and "which day" once it is not. */
function dpWhenMs(ms){
  const n = Number(ms) || 0;
  if (!n) return "";
  const d = new Date(n), today = new Date(dpNow());
  if (d.getDate() !== today.getDate() || d.getMonth() !== today.getMonth()) return dpStamp(n);
  return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
}
function dpChatLine(row){
  const to = row.to ? " to " + dpEsc(row.to) : "";
  return `<div class="dpmsg${row.mode === "think" ? " think" : ""}">` +
    `<span><div class="dpwho">${dpEsc(row.who || "")}${to}</div>${dpEsc(row.line || "")}</span>` +
    `<span class="dpat">${dpEsc(dpWhen(row.at))}</span></div>`;
}
function dpChatHtml(rows, mode){
  rows = rows || [];
  if (!rows.length) return dpQuiet("Nothing yet.");
  if (mode === "exact"){
    return `<pre class="dpexact">${dpEsc(rows.map(r => JSON.stringify(r, null, 2)).join("\n\n"))}</pre>`;
  }
  return `<div class="dpchat">${rows.map(dpChatLine).join("")}</div>`;
}
/* The Summary / Exact control is the panel's own `.tabs` (panel.css:595-597)
   with one placement rule of its own, so the two readings switch the way
   every other pair of tabs in this app does. */
function dpTabsHtml(cur, panes, attr){
  return `<div class="tabs dptabs">` + panes.map(([v, label]) =>
    `<button type="button" aria-pressed="${v === cur}" ${attr}="${dpEsc(v)}">${dpEsc(label)}</button>`
  ).join("") + `</div>`;
}
function dpChatCard(title, rows, key){
  const mode = dpS().chatMode[key] || "summary";
  const modes = `<div class="tabs dptabs dpmodes">` + DP_MODES.map(([v, label]) =>
    `<button type="button" aria-pressed="${v === mode}" data-dpchatmode="${v}" data-dpchatkey="${dpEsc(key)}">${label}</button>`
  ).join("") + `</div>`;
  return dpCard(title, modes + dpChatHtml(rows, mode));
}

/* ── Identity ──────────────────────────────────────────────────────────────
   What the department is for, when it is done, what it may and may not do,
   what it may spend, and whose it is -- every line a projection of the record
   behind it, and a quiet line wherever the record carries nothing. */
const DP_TAGS = ["go", "ask", "refuse", "always"];
function dpCell(label, body){ return `<div class="dpcell"><div class="dpk">${dpEsc(label)}</div>${body}</div>`; }
function dpBig(text){ return `<div class="dpbig">${dpEsc(text)}</div>`; }
function dpRuleHtml(r){
  const tag = DP_TAGS.indexOf(String(r && r.tag)) === -1 ? "always" : String(r.tag);
  return `<div class="dprule"><span class="dptag ${tag}">${dpEsc(tag)}</span>` +
         `<span>${dpEsc((r && r.text) || "")}</span></div>`;
}
/* The bar says how much of the ceiling the founder's setting takes, and no
   number is printed (A28). Nothing set is not zero -- it is no reading. */
function dpBudgetHtml(b){
  if (!b || b.running_at_once == null) return dpQuiet("No reading yet");
  const ceiling = Number(b.ceiling) || 0;
  const share = ceiling ? Math.min(1, Number(b.running_at_once) / ceiling) : 0;
  const kinds = Object.keys(b.turn_budget || {});
  return dpBar(share) + (kinds.length ? `<div class="dpchk">Turns set for ${dpEsc(kinds.join(", "))}</div>` : "");
}
function dpOwnerHtml(o){
  const name = (o && o.name) || "";
  if (!name) return dpQuiet("No owner yet");
  return `<div class="dpown"><span class="dpav">${dpEsc(name.slice(0, 1).toUpperCase())}</span><span>${dpEsc(name)}</span></div>`;
}
/* A12: a department nobody has written a goal for says so in its own words,
   and the one action beside it is the Org screen's existing write-it ask
   (o2OpenSheet -> POST /api/org2/request kind org.charter). The word that
   names that record is not on this card. */
function dpNoGoalHtml(){
  return dpQuiet("No goal yet") + `<button type="button" class="btn" data-dpgoal="1">Write the goal</button>`;
}
function dpIdentityCardHtml(id){
  const grid = `<div class="dpid">` +
    dpCell("Goal", id.goal ? dpBig(id.goal) : dpNoGoalHtml()) +
    dpCell("Done when", id.done ? dpBig(id.done) : dpQuiet("No done line yet")) +
    dpCell("Budget", dpBudgetHtml(id.budget)) +
    dpCell("Owner", dpOwnerHtml(id.owner)) +
    `</div>`;
  const rules = (id.rules || []).length ? id.rules.map(dpRuleHtml).join("")
                                        : dpQuiet("No rules yet");
  return dpCard("The department", grid) + dpCard("Rules", rules);
}
/* Three tabs above the card (A10): the department itself, and the two chats
   Identity keeps -- one with the person who owns it, one with Adaptation. */
function dpIdentityHtml(){
  const st = dpS(), ref = st.sel;
  const id = (st.identity && st.identity.ref === ref) ? st.identity : null;
  if (!id) return st.error.identity ? dpQuiet("Could not read") : dpSkel();
  const pane = st.pane[ref + ":identity"] || "identity";
  const owner = (id.owner && id.owner.name) || "";
  const chats = id.chats || {};
  /* DS-13 (the founder's structure, 2026-09-22): two tabs. The card, and the
     chat -- the exact Sutra chat, which is also where a department is started.
     The owner's turns and Adaptation's turns are the card's Recent section. */
  const tabs = dpTabsHtml(pane, [["identity", "Identity"], ["chat", "Chat"]], "data-dppane");
  /* Slice I (DS-10): the owner's tab is the live Sutra chat with Identity; the
     With Adaptation tab keeps the record's turns, unchanged. */
  if (pane === "chat") return tabs + dpLiveChatHtml("identity", "Identity");
  const recent = (chats.owner || []).concat(chats.adaptation || [])
    .sort((a, b) => String(a.at || "").localeCompare(String(b.at || "")));
  return tabs + dpTemplateLine("identity") + dpIdentityCardHtml(id) +
         dpFrameworkHtml("identity") + dpRecentHtml(recent, "Recent");
}

/* ── the other four functions ──────────────────────────────────────────────
   Adaptation, Priority, Coordination and Audit are one shape with four sets of
   rows: the function's own card, and beside it the Chat tab carrying the turns
   its route wrote (A17). The tabs, the chat, the bar and the row are slice B's
   -- only the rows below are new. Every card follows Now's rule for empty: a
   section with no rows is not drawn at all, and a function with nothing
   anywhere is ONE quiet line, never one per section. */
function dpPane(ref, tab){ return dpS().pane[ref + ":" + tab] || tab; }
/* The frame every card with tabs wears. A function card passes nothing but its
   renderer and gets two tabs; the engine card passes five panes and its own
   chat rows, and gets the same pane key (`<ref>:<tab>`), the same chat key
   (`<ref>:<tab>:chat`) and the same read guard. One frame, not two. */
function dpFnHtml(tab, label, card, panes, chat){
  const st = dpS(), ref = st.sel;
  const data = (st[tab] && st[tab].ref === ref) ? st[tab] : null;
  if (!data) return st.error[tab] ? dpQuiet("Could not read") : dpSkel();
  const pane = dpPane(ref, tab);
  /* Slice I (DS-10): a function card's Chat tab is the live Sutra chat with that
     function, and the record's turns move to a Log tab beside it. An engine
     card passes its own panes and keeps its record chat exactly as before. */
  const isFn = !panes && DP_FUNCS.some(f => f[0] === tab);
  const tabs = dpTabsHtml(pane, panes || [[tab, label], ["chat", "Chat"]], "data-dppane");
  if (isFn && pane === "chat") return tabs + dpLiveChatHtml(tab, label);
  if (pane === "chat"){                                  /* an engine card keeps its record chat */
    const rows = (typeof chat === "function") ? chat(data) : (chat || data.chat);
    return tabs + dpChatCard("Chat", rows, ref + ":" + tab + ":chat");
  }
  if (!isFn) return tabs + card(data, pane);
  /* DS-13 and DS-14: the template line, the card's own rows, its framework, the
     sections this function adds, and the record's turns as Recent. */
  const extra = tab === "adaptation" ? dpGraphHtml() + dpEngineStepsHtml()
              : tab === "priority" ? dpNextRunsHtml()
              : tab === "coordination" ? dpMakesReadsHtml() : "";
  return tabs + dpTemplateLine(tab) + card(data, pane) + extra +
         dpFrameworkHtml(tab) + dpRecentHtml((typeof chat === "function") ? chat(data) : (chat || data.chat), "Recent");
}

/* Adaptation: what it wants changed, and the asking behind it. */
function dpPropHtml(p){
  const note = [p.evidence, p.state].filter(Boolean).join(" · ");
  return dpRunRow(p.change, note, p.open ? "warn" : "ok", p.open ? dpBar(dpLeft(p)) : "");
}
/* A23: an engine an ask brought into being, on the two cards that were part of
   it. Adaptation put the change forward, so its Runs row is the engine's
   birth; Priority admitted the first row that engine ever got, so its row says
   that. Both read the same match slice D made -- the ask decided in the minute
   the record was written -- and neither invents a row for an engine somebody
   wrote by hand. */
function dpBirthRows(births, line){
  return (births || []).map(b => dpRunRow(line + b.name, dpStamp(b.at_ms), "ok")).join("");
}
function dpAdaptationCard(a){
  const props = a.proposals || [], pats = a.patterns || [], born = a.births || [];
  /* the one action: the Org screen's existing write-it ask, which is how a
     rule is changed here too -- this screen still files nothing of its own */
  const offer = `<div class="dpoffer"><button type="button" class="btn" data-dprule="1">Change a rule</button></div>`;
  if (!props.length && !pats.length && !born.length) return dpQuiet("Nothing to change yet") + offer;
  let body = "";
  if (props.length) body += dpCard("Proposals", props.map(dpPropHtml).join(""));
  if (pats.length) body += dpCard("Seen in the logbook", pats.map(p =>
    dpRunRow(p.summary, "Since " + dpStamp(p.since_ms))).join(""));
  if (born.length) body += dpCard("Runs", dpBirthRows(born, "Engine born: "));
  return body + offer;
}

/* Priority: what it took on, in the order it took it, under one ceiling. */
function dpPriorityCard(p){
  const q = p.queue || [], born = p.births || [];
  const budget = dpBudgetHtml(p.budget);
  if (!q.length && !born.length && !(p.budget && p.budget.running_at_once != null)) return dpQuiet("Nothing in the queue");
  let body = "";
  if (q.length) body += dpCard("Queue", q.map(r => dpRunRow(r.next,
    [r.runs_as ? "Runs as " + r.runs_as : "", dpWhenMs(r.when_ms)].filter(Boolean).join(" · "),
    "ok")).join(""));
  if (born.length) body += dpCard("Runs", dpBirthRows(born, "First row admitted: "));
  return body + dpCard("Budget", budget);
}

/* Coordination: what is moving, what is held, and what changed hands last. */
function dpCoordinationCard(c){
  const st = dpS();
  const runR = (st.running && st.running.ref === st.sel) ? st.running : null;
  const live = (runR && runR.running) || [], held = c.held || [], hand = c.handoffs || [];
  if (!live.length && !held.length && !hand.length) return dpQuiet("Nothing held");
  let body = "";
  if (live.length) body += dpCard("Live board", live.map(r => dpRunRow(r.goal, "", "ok")).join(""));
  if (held.length) body += dpCard("Locks", held.map(h => dpRunRow(h.resource,
    [h.holder, h.since_ms ? "since " + dpWhenMs(h.since_ms) : ""].filter(Boolean).join(" · "),
    "warn")).join(""));
  /* the LAST hand-off, not every one: the question the card answers is who
     has it now, and the chain behind that is the Chat tab's business */
  if (hand.length) body += dpCard("Hand-offs", dpRunRow(hand[0].what,
    [hand[0].from + " to " + hand[0].to, dpStamp(hand[0].ts_ms)].filter(Boolean).join(" · ")));
  return body;
}

/* Audit: one claim per line and what the record answered. A check is a check
   (A16) -- no score, no share, no total, and no bar on this card at all. */
function dpAuditCard(v){
  const found = v.findings || [], unseen = v.unseen || [];
  if (!found.length && !unseen.length) return dpQuiet("No check has run here");
  let body = "";
  if (found.length) body += dpCard("Checks", found.map(f =>
    dpRunRow(f.claim, f.record, f.dot)).join(""));
  if (unseen.length) body += dpCard("Never looked at", unseen.map(u =>
    dpQuiet(u.claim + (u.since ? " — open since " + dpWhen(u.since) : ""))).join(""));
  return body;
}

/* ── Engines ───────────────────────────────────────────────────────────────
   An engine is a routine that runs in this department's folder. The list column
   names each one with the state word its records add up to (A18); the card is
   the same frame every function card wears, with five panes instead of two:
   what the engine IS, the steps it follows, what it has done, what it filed,
   and the chat those runs make (A19). The one action is Pause, and Pause files
   an ask -- the word on the row does not move until that ask is stamped (A22). */
const DP_ENG_PANES = [["engines", "Engine"], ["workflow", "Workflow"],
                      ["runs", "Runs"], ["data", "Data"], ["chat", "Chat"]];
const DP_STATES = { running: "Running", paused: "Paused", idle: "Idle" };
const DP_RUN_WORDS = { ok: "Done", failed: "Failed", timeout: "Ran out of time",
                       skipped: "Skipped" };
const DP_RUN_DOTS = { ok: "ok", failed: "block", timeout: "block", skipped: "warn" };

function dpEngRow(e){
  const st = dpS();
  const on = st.engineSel === e.id && st.tab[st.sel] === "engines";
  const word = DP_STATES[String(e.state)] || DP_STATES.idle;
  return `<button type="button" class="o2li dpli dpeng${on ? " on" : ""}" data-dpengine="${dpEsc(e.id)}">` +
    `<span>${dpEsc(e.name)}</span><span class="dpst ${dpEsc(String(e.state || "idle"))}">${dpEsc(word)}</span></button>`;
}
/* The engine the card is on: the selected one, or the first, so opening the
   group from the Engines row lands somewhere rather than nowhere. */
function dpEngine(){
  const st = dpS();
  const list = (st.engines && st.engines.ref === st.sel && st.engines.engines) || [];
  return list.filter(e => e.id === st.engineSel)[0] || list[0] || null;
}
function dpNames(xs){ return (xs && xs.length) ? xs.join(", ") : ""; }
function dpKV(label, value, quiet){
  return dpCell(label, value ? dpBig(value) : dpQuiet(quiet));
}
/* A23: where the engine came from, as one line. "From an ask" when an approved
   ask was decided in the same minute the record was written; "Written" when it
   was not -- no record links the two, so those two are the only honest words. */
function dpMade(e){
  const b = e.made_by || {};
  const when = dpStamp(b.at_ms);
  return (b.from_ask ? "From an ask" : "Written") + (when ? ", " + when : "");
}
/* An ask already waiting on this engine: the Pause button says so rather than
   filing a second one, and the state word still does not move (A22). */
function dpAsked(id){
  const st = dpS();
  const asks = (st.now && st.now.ref === st.sel && st.now.asks) || [];
  return asks.some(a => a.kind === "routine.update" && a.args && a.args.id === id);
}
/* The meters the record can answer for ONE engine, as dots (A27). Fit is named
   by the locked screen and has no record anywhere -- nothing measures how much
   of an instruction its rules take -- so it never carries a dot, and an engine
   whose records answer none of them shows the one quiet line instead. */
function dpEngMeters(id){
  const st = dpS();
  const read = (st.meters && st.meters.ref === st.sel) ? st.meters : null;
  const row = ((read && read.engines) || []).filter(e => e.id === id)[0];
  return (row && row.meters) || [];
}
function dpEngMetersCard(id){
  const rows = dpEngMeters(id);
  if (!rows.length) return dpCard("Meters", dpQuiet("No reading yet"));
  return dpCard("Meters", `<div class="dpmets">` + rows.map(m =>
    `<span class="dpmet"><i class="dpdot ${dpEsc(m.dot || "")}"></i>${dpEsc(m.label)}</span>`
  ).join("") + `</div>`);
}
function dpEngineTable(e){
  const st = dpS();
  const grid = `<div class="dpengines">` +
    /* A34: the state word belongs on the card as well as on the row, so an
       engine opened from anywhere says what it is doing without going back */
    dpKV("State", DP_STATES[String(e.state)] || DP_STATES.idle, "") +
    dpKV("Made by", dpMade(e), "") +
    dpKV("Runs as", e.runs_as, "Not named") +
    dpKV("Cadence", e.cadence, "Not set") +
    dpKV("Needs", dpNames(e.needs), "Not named") +
    dpKV("Makes", dpNames(e.makes), "Not named") +
    dpKV("Read by", dpNames(e.read_by), "Not named") +
    `</div>`;
  const asked = dpAsked(e.id) || !!st.busy["pause:" + e.id];
  const act = e.state === "paused" ? "" :
    `<div class="dpoffer"><button type="button" class="btn" data-dppause="${dpEsc(e.id)}">` +
    (asked ? "Asked to pause" : "Pause") + `</button></div>`;
  return dpCard("The engine", grid) + dpEngMetersCard(e.id) + act;
}
/* F-11: a run row carries no step, so there is nothing to mark. When one ever
   names where it is, the live run lights that step and no other. */
function dpStepDot(s, runs){
  const live = ((runs && runs.runs) || []).filter(r => r.started_at && !r.ended_at)[0];
  const at = live && (live.step || live.step_id);
  return at && String(at) === String(s.id) ? "ok" : "";
}
function dpWorkflowCard(e){
  const st = dpS();
  const read = st.engineRuns[e.id];
  const runs = (read && read.ref === st.sel) ? read : null;
  const w = e.workflow, steps = (w && w.steps) || [];
  if (!steps.length){
    /* no registered workflow: what the engine is told to do, in its own words */
    return e.prompt ? dpCard("What it is told to do", `<pre class="dpexact">${dpEsc(e.prompt)}</pre>`)
                    : dpQuiet("No steps written yet");
  }
  return dpCard(w.title || "Steps", steps.map(s => dpRunRow(s.name || s.id,
    [dpNames(s.produces), s.verify].filter(Boolean).join(" · "),
    dpStepDot(s, runs))).join(""));
}
/* How long a run took, against the longest run on the card. A bar, never a
   number of seconds (A28) -- the owner reads "that one was the long one". */
function dpDur(r, full){
  const s = Number(r.duration_s) || 0;
  return (s && full) ? dpBar(Math.min(1, s / full)) : "";
}
function dpElapsed(at){
  const t = Date.parse(String(at || ""));
  if (!t) return "";
  const m = Math.floor((dpNow() - t) / 60000);
  if (m < 1) return "just started";
  return m < 60 ? m + "m so far" : Math.floor(m / 60) + "h so far";
}
/* When a run started: the clock while it is today, the day once it is not.
   A list of nightly runs is a list of DAYS, and a bare clock hides that. */
function dpAt(iso){ return dpWhenMs(Date.parse(String(iso || "")) || 0); }
function dpRunsCard(e){
  const st = dpS();
  const read = st.engineRuns[e.id];
  const mine = (read && read.ref === st.sel) ? read : null;
  if (!mine) return st.error["engineRuns:" + st.sel + ":" + e.id] ? dpQuiet("Could not read") : dpSkel();
  const rows = mine.runs || [];
  if (!rows.length) return dpQuiet("Never run");
  const full = rows.reduce((m, r) => Math.max(m, Number(r.duration_s) || 0), 0);
  /* A34: a paused engine has no live run. A row it left behind with no end
     stamp is a run that was stopped, not one that is going, and reading it as
     live would put a clock on a card whose engine is switched off. */
  const paused = e.state === "paused";
  return dpCard("Runs", rows.map(r => {
    const live = !paused && r.started_at && !r.ended_at;
    if (live) return dpRunRow("Running", [dpAt(r.started_at), dpElapsed(r.started_at)].filter(Boolean).join(" · "));
    const word = DP_RUN_WORDS[String(r.outcome)] || DP_RUN_WORDS.ok;
    return dpRunRow(word, dpAt(r.started_at), DP_RUN_DOTS[String(r.outcome)] || "ok", dpDur(r, full));
  }).join(""));
}
function dpDataCard(e){
  const st = dpS();
  const read = st.engineData[e.id];
  const mine = (read && read.ref === st.sel) ? read : null;
  if (!mine) return st.error["engineData:" + st.sel + ":" + e.id] ? dpQuiet("Could not read") : dpSkel();
  const rows = mine.filed || [];
  if (!rows.length) return dpQuiet("Nothing filed");
  return dpCard("Filed work", rows.map(f => dpRunRow(f.label, dpStamp(f.ts_ms), "ok")).join(""));
}
const DP_ENG_CARDS = { engines: dpEngineTable, workflow: dpWorkflowCard,
                       runs: dpRunsCard, data: dpDataCard };
/* The two engine-scoped reads fire when the pane that needs them opens, never
   before -- the same call-on-render rule every card on this screen follows. */
function dpEngineCard(_data, pane){
  const st = dpS(), e = dpEngine();
  if (!e) return dpQuiet("No engines here");
  if (pane === "engines") dpLoadMeters(st.sel);          /* the meters the card draws */
  if (pane === "runs" || pane === "workflow") dpLoadEngineRuns(st.sel, e.id);
  if (pane === "data") dpLoadEngineData(st.sel, e.id);
  return (DP_ENG_CARDS[pane] || dpEngineTable)(e);
}
function dpEngineChat(){
  const st = dpS(), e = dpEngine();
  if (!e) return [];
  dpLoadEngineRuns(st.sel, e.id);
  const read = st.engineRuns[e.id];
  return (read && read.ref === st.sel && read.chat) || [];
}
function dpEnginesHtml(){
  return dpFnHtml("engines", "Engine", dpEngineCard, DP_ENG_PANES, dpEngineChat);
}

/* ── Filed work ────────────────────────────────────────────────────────────
   A filed item and every version of it. The same work item is placed again and
   again -- a re-file, a charter amendment, a move to another department -- and
   each placement names the one before it; that chain IS the version history,
   newest first (A24). The three words a version carries are derived from two
   of the record's own fields and nothing else: a version another one replaced
   reads retired, and the one still standing reads in use when the work it was
   filed for has closed, waits when it has not. The maker is the filer's own
   word for itself; no record anywhere names a reader, so that line is quiet. */
const DP_VER_CLS = { "in use": "use", waits: "waits", retired: "gone" };
function dpVersionHtml(v){
  const state = String(v.state || "waits");
  const note = [v.made_by ? "Filed by " + v.made_by : "", v.where, dpStamp(v.ts_ms)]
    .filter(Boolean).join(" · ");
  return `<div class="dpver"><span class="dpvw ${DP_VER_CLS[state] || "waits"}">${dpEsc(state)}</span>` +
    `<span>${dpEsc(note)}</span></div>`;
}
function dpFiledRead(){
  const st = dpS();
  return (st.filed && st.filed.ref === st.sel) ? st.filed : null;
}
/* The filed item the card is on: the selected one, or the first, so opening
   the group from a row lands somewhere rather than nowhere (dpEngine's rule). */
function dpFiledOne(){
  const st = dpS(), read = dpFiledRead();
  const rows = (read && read.filed) || [];
  return rows.filter(f => f.id === st.filedSel)[0] || rows[0] || null;
}
function dpFiledCard(){
  const st = dpS();
  if (!dpFiledRead()) return st.error.filed ? dpQuiet("Could not read") : dpSkel();
  const f = dpFiledOne();
  if (!f) return dpQuiet("Nothing filed yet");
  const hist = f.history || [];
  const now = hist[0] || {};
  const grid = `<div class="dpengines">` +
    dpKV("Filed by", now.made_by, "Not named") +
    dpKV("Read by", dpNames(now.read_by), "Not named") +
    dpKV("Where", now.where, "Not named") +
    `</div>`;
  const versions = hist.length ? hist.map(dpVersionHtml).join("") : dpQuiet("No versions yet");
  return dpCard("The work item", grid) + dpCard("Versions", versions);
}

/* ── People ────────────────────────────────────────────────────────────────
   Who answers for this department: the owner by the same rule Identity uses,
   then the role charters when any are written (A25). A person opens on a card
   with their name, what their record says is theirs to stamp, and the asks
   they saw -- the answered ones, because an ask nobody answered was not seen. */
function dpPerson(){
  const st = dpS();
  const read = (st.people && st.people.ref === st.sel) ? st.people : null;
  const list = dpPeople(read);
  return list.filter(p => p.key === st.personSel)[0] || list[0] || null;
}
function dpPeopleCard(){
  const st = dpS();
  const read = (st.people && st.people.ref === st.sel) ? st.people : null;
  if (!read) return st.error.people ? dpQuiet("Could not read") : dpSkel();
  const p = dpPerson();
  if (!p) return dpQuiet("No people yet");
  const grid = `<div class="dpengines">` +
    dpCell("Name", dpOwnerHtml({ name: p.name })) +
    dpCell("Stamps", p.stamps ? dpBig(p.stamps) : dpQuiet("Not named")) +
    `</div>`;
  const seen = (p.seen || []).length
    ? p.seen.map(s => dpRunRow(s.summary, [s.answer, dpWhen(s.at)].filter(Boolean).join(" · "), "ok")).join("")
    : dpQuiet("No asks yet");
  return dpCard("The person", grid) + dpCard("Asks they saw", seen);
}

/* ── answering an ask about an engine ─────────────────────────────────────── */
/* Pause posts to the one route this screen has that writes, and what that route
   writes is an ASK (A22). Nothing is applied here: Now grows a row, the state
   word stays exactly where it was, and Approvals is where it moves. */
async function dpPause(id){
  const st = dpS(), ref = st.sel;
  if (!id || !ref || st.busy["pause:" + id]) return;
  st.busy["pause:" + id] = true;
  dpRender();
  try {
    await apiPost(dpUrl(ref, "engines/" + encodeURIComponent(id) + "/pause"), {});
  } catch (e) {
    st.error.engines = (e && e.message) || String(e);
  }
  delete st.busy["pause:" + id];
  if (typeof loadProposals === "function") loadProposals();
  await dpLoadNow(ref, true);
  await dpLoadEngines(ref, true);
  dpRender();
}

const DP_CARDS = {
  adaptation: [dpLoadAdaptation, dpAdaptationCard],
  priority: [dpLoadPriority, dpPriorityCard],
  coordination: [dpLoadCoordination, dpCoordinationCard],
  audit: [dpLoadAudit, dpAuditCard],
};

function dpViewerHtml(n, d, dept, err){
  const st = dpS();
  const tab = st.tab[n.ref] || "now";
  st.selName = n.name || "";                             /* the chat's title and its seed read it */
  if (tab === "now"){
    dpLoadMeters(n.ref);                                 /* read on open, as o2LoadApps does */
    return dpViewerShell("Now", dpNowHtml());
  }
  if (tab === "identity"){
    dpLoadIdentity(n.ref);                               /* read on open, as o2LoadApps does */
    return dpViewerShell("Identity", dpIdentityHtml());
  }
  if (tab === "engines"){
    dpLoadEngines(n.ref);
    const e = dpEngine();
    return dpViewerShell(e ? e.name : "Engines", dpEnginesHtml());
  }
  if (tab === "filed"){
    dpLoadFiled(n.ref);                                  /* read on open, the same way */
    const f = dpFiledOne();
    return dpViewerShell(f ? f.label : "Filed work", dpFiledCard());
  }
  if (tab === "people"){
    dpLoadPeople(n.ref);
    const p = dpPerson();
    return dpViewerShell(p ? p.name : "People", dpPeopleCard());
  }
  const label = (DP_FUNCS.find(f => f[0] === tab) || [tab, tab])[1];
  const card = DP_CARDS[tab];
  if (card){
    card[0](n.ref);                                      /* read on open, the same way */
    return dpViewerShell(label, dpFnHtml(tab, label, card[1]));
  }
  return dpViewerShell(label, dpQuiet("Not read yet"));
}

/* ── slice J: the template as the function's framework ────────────────────── */
/* The founder's structure (2026-09-22, DS-14): a function card opens on the
   template it runs -- its name, when it is picked, and the six parts of its
   framework. The parts are the template's own lines; nothing here is written
   by the screen. */
const DP_FRAME_PARTS = [["floor", "Always does"], ["choices", "Decides"], ["reads", "Reads"],
                        ["may_propose", "May propose"], ["checks", "How we know it worked"]];
function dpFrameworkHtml(fn){
  const st = dpS(), ref = st.sel;
  if (!ref) return "";
  dpLoadFunctions(ref);
  const f = (st.functions && st.functions.ref === ref) ? st.functions : null;
  const t = f && (f.picked || {})[fn];
  if (!t) return "";
  const rows = DP_FRAME_PARTS.map(([k, label]) => {
    const lines = t[k] || [];
    if (!lines.length) return "";
    return `<div class="dpfpart"><div class="dpk">${dpEsc(label)}</div>` +
           lines.map(l => `<div class="dpfline">${dpEsc(l)}</div>`).join("") + `</div>`;
  }).join("");
  const when = t.schedule ? `<div class="dpfpart"><div class="dpk">Runs</div><div class="dpfline">${dpEsc(t.schedule)}</div></div>` : "";
  return dpCard("The " + (t.name || "Default") + " template",
    `<div class="dpfuse">${dpEsc(t.use_case || "")}</div><div class="dpframework">` + rows + when + `</div>`);
}
/* The record's own turns, as the card's Recent section (DS-13): the summary
   reading only -- the Exact tab and the Log tab are gone from a function card. */
const DP_RECENT_MAX = 6;
function dpRecentHtml(rows, title){
  rows = (rows || []).slice(-DP_RECENT_MAX);
  /* A33: a function with nothing anywhere is ONE quiet line, and the card's own
     line is that one -- an empty Recent is not drawn at all. */
  if (!rows.length) return "";
  return dpCard(title || "Recent", `<div class="dpchat">` + rows.map(dpChatLine).join("") + `</div>`);
}

/* ── slice J: the department's graph (Adaptation) ─────────────────────────── */
/* What the department is made of, drawn from the records it already reads: the
   owner above Identity, the five functions, and every engine with the state
   word its records add up to. Arrows say who proposes and who admits. */
function dpGraphHtml(){
  const st = dpS(), ref = st.sel;
  dpLoadEngines(ref);                                   /* read on open, as the list column does */
  const eng = (st.engines && st.engines.ref === ref) ? (st.engines.engines || []) : [];
  const W = 860, top = 26, rowH = 62;
  const fns = DP_FUNCS.map(f => f[1]);
  const fnW = 150, gap = 14, fnY = top + rowH;
  const fnX = i => 20 + i * (fnW + gap);
  const engY = fnY + rowH + 8;
  const cols = Math.max(1, Math.min(eng.length, 5));
  const engW = Math.min(160, Math.floor((W - 40 - (cols - 1) * gap) / cols));
  const engX = i => 20 + (i % 5) * (engW + gap);
  const rows = Math.ceil(Math.max(eng.length, 1) / 5);
  const H = engY + rows * 54 + 34;
  const box = (x, y, w, h, label, note, cls) =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="7" class="dpg-${cls}"/>` +
    `<text x="${x + 9}" y="${y + 19}" class="dpg-t">${dpEsc(String(label).slice(0, 22))}</text>` +
    (note ? `<text x="${x + 9}" y="${y + 35}" class="dpg-n">${dpEsc(String(note).slice(0, 24))}</text>` : "");
  let s = `<svg viewBox="0 0 ${W} ${H}" class="dpgraph" role="img" aria-label="What this department is made of">`;
  s += box(20, top, 200, 40, "The owner", "stamps every ask", "own");
  s += box(240, top, 200, 40, "Identity", "goal, done, rules", "id");
  s += `<line x1="220" y1="${top + 20}" x2="240" y2="${top + 20}" class="dpg-a"/>`;
  fns.slice(1).forEach((label, i) => {
    s += box(fnX(i), fnY, fnW, 40, label, "", "fn");
    s += `<line x1="340" y1="${top + 40}" x2="${fnX(i) + fnW / 2}" y2="${fnY}" class="dpg-a"/>`;
  });
  if (!eng.length){
    s += `<text x="20" y="${engY + 22}" class="dpg-n">No engines yet</text>`;
  } else {
    eng.slice(0, 10).forEach((e, i) => {
      const y = engY + Math.floor(i / 5) * 54;
      s += box(engX(i), y, engW, 40, e.name || e.id, DP_STATES[e.state] || e.state || "", "eng");
      s += `<line x1="${fnX(0) + fnW / 2}" y1="${fnY + 40}" x2="${engX(i) + engW / 2}" y2="${y}" class="dpg-a"/>`;
    });
  }
  return s + `</svg>`;
}
/* Every engine's steps, under the graph: the department's written ways, in one
   place, without opening each engine (the founder's "various workflow things"). */
function dpEngineStepsHtml(){
  const st = dpS(), ref = st.sel;
  dpLoadEngines(ref);                                   /* read on open, as the list column does */
  const eng = (st.engines && st.engines.ref === ref) ? (st.engines.engines || []) : [];
  if (!eng.length) return "";
  const body = eng.map(e => {
    const steps = ((e.workflow || {}).steps) || [];
    const lines = steps.length
      ? steps.map(x => `<div class="dpfline">${dpEsc(x.name || x.id || "")}</div>`).join("")
      : `<div class="dpfline">${dpEsc(e.prompt ? "Told in its own words, no steps written yet" : "No steps written yet")}</div>`;
    return `<div class="dpfpart"><div class="dpk">${dpEsc(e.name || e.id)}</div>${lines}</div>`;
  }).join("");
  return dpCard("What each engine does, step by step", `<div class="dpframework">${body}</div>`);
}
/* When each engine runs next, off its own record (Priority, DS-14). */
function dpNextRunsHtml(){
  const st = dpS(), ref = st.sel;
  dpLoadEngines(ref);                                   /* read on open, as the list column does */
  const eng = (st.engines && st.engines.ref === ref) ? (st.engines.engines || []) : [];
  if (!eng.length) return "";
  const rows = eng.map(e => dpRunRow(e.name || e.id,
    [e.cadence || "", e.next_run ? "next " + dpWhen(e.next_run) : "not scheduled"].filter(Boolean).join(" · "),
    e.next_run ? "ok" : "")).join("");
  return dpCard("Next runs", rows);
}
/* Who makes each engine's work and who reads it (Coordination, DS-14). */
function dpMakesReadsHtml(){
  const st = dpS(), ref = st.sel;
  dpLoadEngines(ref);                                   /* read on open, as the list column does */
  const eng = (st.engines && st.engines.ref === ref) ? (st.engines.engines || []) : [];
  if (!eng.length) return "";
  const rows = eng.map(e => {
    const by = (e.made_by && e.made_by.from_ask) ? "from an ask" : "written by the owner";
    const reads = e.read_by || "nobody named yet";
    return dpRunRow(e.name || e.id, by + " · read by " + reads, "");
  }).join("");
  return dpCard("Who makes it, who reads it", rows);
}

/* ── slice I: the template each function runs ─────────────────────────────── */
/* holding/plans/department-screen/LLD-FUNCTIONS.md section 3 and 5. One line
   under a function's tabs names the template it runs; Change opens the picker
   of that function's templates; picking files an org.template ask through the
   Org screen's own request route. Nothing changes until the owner stamps it. */
function dpTemplateLine(fn){
  const st = dpS(), ref = st.sel;
  if (!ref) return "";
  dpLoadFunctions(ref);                                  /* read on open, as the cards do */
  const f = (st.functions && st.functions.ref === ref) ? st.functions : null;
  if (!f) return "";
  const cur = (f.picked || {})[fn];
  const asked = st.fnAsked[ref + ":" + fn];
  let out = `<div class="dptpl"><span>Runs the ${dpEsc(cur ? cur.name : "Default")} template</span>` +
    (asked ? `<span class="dpchk">${dpEsc(asked)}</span>`
           : `<button type="button" class="btn" data-dptplopen="${dpEsc(fn)}">Change</button>`) + `</div>`;
  if (st.fnPick === fn && !asked){
    out += `<div class="dptplpick">` + (((f.templates || {})[fn]) || []).map(t => {
      const on = !!(cur && cur.id === t.id);
      return `<div class="dptplrow"><div><div class="dptplname">${dpEsc(t.name)}</div>` +
        `<div class="dpchk">${dpEsc(t.use_case)}</div></div>` +
        (on ? `<span class="dpchk">In use</span>`
            : `<button type="button" class="btn" data-dptpluse="${dpEsc(t.id)}" data-dptplfn="${dpEsc(fn)}">Use this</button>`) +
        `</div>`;
    }).join("") + `</div>`;
  }
  return out;
}
async function dpTemplateAsk(fn, tid){
  const st = dpS(), ref = st.sel;
  if (!ref || !fn || !tid || st.busy["tpl:" + ref]) return;
  st.busy["tpl:" + ref] = true;
  dpRender();
  try {
    await apiPost("/api/org2/request", { kind: "org.template", args: { ref: ref, function: fn, template: tid } });
    st.fnAsked[ref + ":" + fn] = "Asked; stamp it in Now";
    st.fnPick = null;
    if (typeof loadProposals === "function") loadProposals();
    delete st.busy["tpl:" + ref];
    await dpLoadNow(ref, true);
  } catch (e) {
    st.fnAsked[ref + ":" + fn] = "Could not ask: " + ((e && e.message) || e);
    delete st.busy["tpl:" + ref];
  }
  dpRender();
}

/* ── slice I: the live chat on a function card ─────────────────────────────── */
/* DS-10: the exact Sutra chat, fitted into the card. The panel loads itself in
   a chat-only mode (`/?embed=chat&dept=&fn=`) inside ONE iframe that lives OUT
   of the region render() rebuilds -- re-inserting an iframe reloads it, so it
   is kept on a host element on <body> and laid over the placeholder the card
   paints (the terminal pane's mount-once rule, 09-tail.js). The host is hidden,
   never emptied, when the tab changes; the frame is dropped only when the
   department changes or another function's chat opens (one live frame). */
const DP_FNCHAT_KEY = "sutra.fnchat";                   /* {"<ref>:<fn>": {claude_session, sutra_id, at}} */
const DP_FRAME = { key: null, el: null, host: null, observed: false };
function dpFnChatMap(){
  try {
    const v = (typeof localStorage !== "undefined") ? localStorage.getItem(DP_FNCHAT_KEY) : null;
    const m = v ? JSON.parse(v) : {};
    return (m && typeof m === "object" && !Array.isArray(m)) ? m : {};
  } catch (e) { return {}; }
}
function dpFnChatUrl(ref, fn, name, start){
  return "/?embed=chat&dept=" + encodeURIComponent(ref) + "&fn=" + encodeURIComponent(fn) +
         "&name=" + encodeURIComponent(name || "") + (start ? "&start=1" : "");
}
function dpLiveChatHtml(fn, label){
  const st = dpS(), key = (st.sel || "") + ":" + fn;
  if (dpFnChatMap()[key] || st.chatStart[key]) return `<div class="dpframe" data-dpframe="${dpEsc(key)}"></div>`;
  return dpCard("Chat", dpQuiet("No chat with " + label + " yet") +
    `<button type="button" class="btn" data-dpchatstart="${dpEsc(fn)}">Start the chat with ${dpEsc(label)}</button>`);
}
function dpFrameDrop(){
  if (DP_FRAME.el && DP_FRAME.el.parentNode) DP_FRAME.el.parentNode.removeChild(DP_FRAME.el);
  DP_FRAME.el = null; DP_FRAME.key = null;
  if (DP_FRAME.host) DP_FRAME.host.hidden = true;
}
function dpFrameHost(){
  if (DP_FRAME.host && DP_FRAME.host.isConnected) return DP_FRAME.host;
  if (typeof document === "undefined" || !document.createElement || !document.body) return null;
  const h = document.createElement("div");
  h.className = "dpframehost";
  h.hidden = true;
  document.body.appendChild(h);
  DP_FRAME.host = h;
  return h;
}
/* Lay the host over the placeholder, or hide it when no placeholder is on
   screen (another tab, another screen, the browse pane closed). */
function dpFramePlace(){
  const h = DP_FRAME.host;
  if (!h) return;
  const ph = (DP_FRAME.key && typeof document !== "undefined" && document.querySelector)
    ? document.querySelector('[data-dpframe="' + String(DP_FRAME.key).replace(/"/g, "") + '"]') : null;
  if (!ph || S.screen !== "org2" || !ph.getBoundingClientRect){ h.hidden = true; return; }
  const r = ph.getBoundingClientRect();
  h.style.left = r.left + "px"; h.style.top = r.top + "px";
  h.style.width = r.width + "px"; h.style.height = r.height + "px";
  h.hidden = !(r.width > 0 && r.height > 0);
}
/* Called after every paint of the Org screen (wireOrg2) and on every rebuild of
   #panes (a MutationObserver, so leaving the screen hides the frame too). */
function dpAfterPaint(scBody){
  const root = (scBody && scBody.querySelector) ? scBody
             : (typeof document !== "undefined" && document.querySelector ? document : null);
  const ph = (root && S.screen === "org2") ? root.querySelector("[data-dpframe]") : null;
  if (!ph){ if (DP_FRAME.host) DP_FRAME.host.hidden = true; return; }
  const key = ph.getAttribute("data-dpframe") || "";
  const cut = key.lastIndexOf(":");
  const ref = key.slice(0, cut), fn = key.slice(cut + 1);
  const st = dpS();
  if (DP_FRAME.key !== key){
    dpFrameDrop();
    const host = dpFrameHost();
    if (!host) return;
    const fr = document.createElement("iframe");
    const label = (DP_FUNCS.find(f => f[0] === fn) || [fn, fn])[1];
    fr.className = "dpframe-if";
    fr.title = "Chat with " + label;
    fr.src = dpFnChatUrl(ref, fn, st.selName, !dpFnChatMap()[key] && !!st.chatStart[key]);
    host.appendChild(fr);
    DP_FRAME.el = fr; DP_FRAME.key = key;
  }
  dpFrameWatch();
  dpFramePlace();
}
function dpFrameWatch(){
  if (DP_FRAME.observed || typeof window === "undefined" || !window.addEventListener) return;
  DP_FRAME.observed = true;
  window.addEventListener("resize", dpFramePlace);
  window.addEventListener("scroll", dpFramePlace, true);
  const panes = document.getElementById && document.getElementById("panes");
  if (panes && typeof MutationObserver !== "undefined"){
    new MutationObserver(() => {
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => dpAfterPaint(null));
      else dpAfterPaint(null);
    }).observe(panes, { childList: true });
  }
}

/* ── slice I: the chat-only mode (the panel inside the card) ──────────────── */
/* EMBED_CHAT (01-state.js) is true only in the frame above. boot() (09-tail.js)
   calls dpEmbedOpen once the sessions are read: with &start=1 it mints the
   chat in the department's folder, filed under the department, and sends the
   picked template's brief filled from Identity as the first turn; without it,
   it reopens the chat this card started before. */
function dpFillBrief(brief, v){
  v = v || {};
  let rules = (v.rules || []).map(r => (r && r.tag ? r.tag : "always") + ": " + ((r && (r.text || r.line)) || "")).join("; ");
  if (rules.length > 1200) rules = rules.slice(0, 1197) + "...";
  const say = {
    department: v.department || "this department",
    goal: v.goal || "not written yet",
    done: v.done || "not written yet",
    rules: rules || "none written yet",
    owner: v.owner || "not named yet",
    folder: v.folder || "no folder yet",
  };
  let out = String(brief || "").replace(/\{(department|goal|done|rules|owner|folder)\}/g, (m, k) => String(say[k]));
  if (out.length > 4000) out = out.slice(0, 3997) + "...";
  return out;
}
function dpEmbedNote(text){
  if (typeof document === "undefined" || !document.createElement || !document.body) return;
  const d = document.createElement("div");
  d.className = "dpembednote";
  d.textContent = text;
  document.body.appendChild(d);
}
async function dpEmbedOpen(){
  const p = new URLSearchParams(location.search);
  const ref = p.get("dept") || "", fn = String(p.get("fn") || "").toLowerCase();
  const name = p.get("name") || "", start = p.get("start") === "1";
  const label = (DP_FUNCS.find(f => f[0] === fn) || [])[1];
  S.ui.dest = "chats"; S.ui.browseClosed = true; S.openPanes = [];
  if (!ref || !label){ dpEmbedNote("This chat is not one of the five functions."); return null; }
  const key = ref + ":" + fn;
  if (!start){
    const saved = dpFnChatMap()[key];
    const s = saved && (S.sessions || []).find(x => x.claude_session === saved.claude_session || x.id === saved.claude_session);
    if (s){
      s.fnKey = key;
      pushPane(s.id);
      if (typeof ensureTranscript === "function") ensureTranscript(s);
      return s;
    }
    dpEmbedNote("This chat is no longer on this Mac.");
    return null;
  }
  let brief, id;
  try {
    [brief, id] = await Promise.all([apiGet(dpUrl(ref, "functions/" + fn + "/brief")), apiGet(dpUrl(ref, "identity"))]);
  } catch (e) {
    dpEmbedNote("Sutra did not answer: " + ((e && e.message) || e));
    return null;
  }
  const seed = dpFillBrief(brief && brief.brief, {
    department: name, goal: id && id.goal, done: id && id.done, rules: id && id.rules,
    owner: id && id.owner && id.owner.name, folder: brief && brief.cwd,
  });
  const s = newSession((brief && brief.cwd) || "", { ref: ref, name: name });
  s.title = label + " · " + (name || "department");
  s.fnKey = key;
  /* DS-15: a function chat may build inside its own department's folder, so it
     opens on Accept edits (edits here, asks for anything else) rather than the
     operator's global mode, which is read-only by default. The native id comes
     from the provider's own map, never a literal. */
  try {
    const opt = (typeof accessOptionsFor === "function")
      ? accessOptionsFor(typeof providerId === "function" ? providerId() : "claude").find(o => o.id === "edits") : null;
    if (opt && opt.mode){ S.perm = S.perm || {}; S.perm[s.id] = opt.mode; }
  } catch (e) {}
  S.openPanes = [s.id];
  submitTurn(seed, s.id, { pin: { department_ref: ref } });
  return s;
}
/* The one write the chat-only mode makes: once the chat has a session, the
   card that started it can find it again. Called from the session frame
   (01-state.js). Outside the chat-only mode it does nothing. */
function dpFnChatRemember(s){
  if (typeof EMBED_CHAT === "undefined" || !EMBED_CHAT || !s || !s.fnKey || !s.claude_session) return;
  const m = dpFnChatMap();
  if (m[s.fnKey] && m[s.fnKey].claude_session === s.claude_session) return;
  m[s.fnKey] = { claude_session: s.claude_session, sutra_id: (S.sutraId || {})[s.id] || null, at: Date.now() };
  lsSet(DP_FNCHAT_KEY, m);
}

/* ── answering an ask ─────────────────────────────────────────────────────── */
/* Stamp and Refuse call decideProposal (08-boot.js:145-153) -- the SAME call
   the Approvals panel makes -- and nothing else. This screen files no write of
   its own; the answer lands, then Now is re-read so the card tells the truth. */
/* B2 (2026-09-21): a decision changes a RECORD, and Now is not the only card
   that reads it. A stamped routine ask flips the routine's own state word,
   which the Engines list AND the open engine card's Engine tab both read out of
   the one /engines answer; a stamped org ask rewrites the goal, the rules and
   who holds a role, which Identity and People read. Those cards are re-read
   HERE, on the decide, and nowhere else -- opening a department still costs the
   three reads Now needs (S14). A card that holds no answer for this department
   is left alone: it reads itself when it opens. */
const DP_DECIDE_READS = [
  [/^routine\./, [["engines", dpLoadEngines]]],
  [/^org\./, [["identity", dpLoadIdentity], ["people", dpLoadPeople], ["functions", dpLoadFunctions]]],
];
function dpAfterDecide(ref, kind){
  const st = dpS(), out = [];
  /* a stamped or refused template ask ends the "asked" line on every card */
  if (String(kind || "") === "org.template"){
    for (const k of Object.keys(st.fnAsked)) if (k.indexOf(ref + ":") === 0) delete st.fnAsked[k];
  }
  for (const pair of DP_DECIDE_READS){
    if (!pair[0].test(String(kind || ""))) continue;
    for (const one of pair[1]){
      if (st[one[0]] && st[one[0]].ref === ref) out.push(one[1](ref, true));
    }
  }
  return Promise.all(out);
}

async function dpDecide(pid, ok){
  const st = dpS();
  if (!pid || st.busy["decide:" + pid]) return;
  const ask = (((st.now && st.now.asks) || []).filter(a => a.id === pid))[0];
  if (ok && ask && ask.irreversible && st.confirm !== pid){
    st.confirm = pid;                                    /* A32: arm, do not answer */
    dpRender();
    return;
  }
  st.confirm = null;
  st.busy["decide:" + pid] = true;
  dpRender();
  try {
    if (typeof decideProposal === "function") await decideProposal(pid, ok);
  } catch (e) {
    st.error.now = (e && e.message) || String(e);
  }
  delete st.busy["decide:" + pid];
  if (st.sel){
    await dpLoadNow(st.sel, true);
    await dpAfterDecide(st.sel, ask && ask.kind);
  }
  dpRender();
}

/* ── handlers ─────────────────────────────────────────────────────────────── */
/* Delegated, and gated twice: the screen must be org2 AND the click must have
   landed inside a `.dp` element. That is 19-org2.js:875-880's own guard with
   this screen's class, so nothing here can fire on another screen. */
if (typeof document !== "undefined" && document.addEventListener){
  const DP_SEL = "[data-dptab],[data-dpdecide],[data-dpmore],[data-dpfiled],[data-dpperson],[data-dpdoc],[data-dpapp],[data-dpengine],[data-dppause],[data-dpchatmode],[data-dppane],[data-dpgoal],[data-dprule],[data-dpchatstart],[data-dptplopen],[data-dptpluse]";
  document.addEventListener("click", (ev) => {
    if (!S.dp || S.screen !== "org2") return;
    const t = ev.target && ev.target.closest ? ev.target.closest(DP_SEL) : null;
    if (!t || !t.closest(".dp")) return;                 /* never outside this screen */
    const st = dpS(), ds = t.dataset || {};
    if (ds.dptab !== undefined){
      ev.preventDefault();
      if (st.sel){ st.tab[st.sel] = ds.dptab; st.confirm = null; }
      dpRender(); return;
    }
    if (ds.dppane !== undefined){
      ev.preventDefault();
      if (st.sel) st.pane[st.sel + ":" + (st.tab[st.sel] || "now")] = ds.dppane;
      dpRender(); return;
    }
    if (ds.dpchatmode !== undefined){
      ev.preventDefault();
      st.chatMode[ds.dpchatkey || ""] = ds.dpchatmode;
      dpRender(); return;
    }
    if (ds.dpgoal !== undefined || ds.dprule !== undefined){
      ev.preventDefault();
      /* the Org screen's own write-it sheet, which posts org.charter through
         /api/org2/request -- this screen adds no second way to ask (A12), and
         changing a rule is the same ask on the same record (A13) */
      if (typeof o2OpenSheet === "function") o2OpenSheet("charter");
      return;
    }
    if (ds.dpengine !== undefined){
      ev.preventDefault();
      if (st.sel){
        /* a different engine opens on its own Engine tab, not on whichever
           pane the last one was left on */
        if (st.engineSel !== ds.dpengine) st.pane[st.sel + ":engines"] = "engines";
        st.engineSel = ds.dpengine;
        st.tab[st.sel] = "engines";
      }
      dpRender(); return;
    }
    if (ds.dppause !== undefined){ ev.preventDefault(); dpPause(ds.dppause); return; }
    /* slice I: nothing is sent without this click (DS-10) */
    if (ds.dpchatstart !== undefined){
      ev.preventDefault();
      if (st.sel) st.chatStart[st.sel + ":" + ds.dpchatstart] = true;
      dpRender(); return;
    }
    if (ds.dptplopen !== undefined){
      ev.preventDefault();
      st.fnPick = st.fnPick === ds.dptplopen ? null : ds.dptplopen;
      dpRender(); return;
    }
    if (ds.dptpluse !== undefined){ ev.preventDefault(); dpTemplateAsk(ds.dptplfn, ds.dptpluse); return; }
    if (ds.dpmore !== undefined){ st.more[ds.dpmore] = true; dpRender(); return; }
    if (ds.dpdecide !== undefined){ ev.preventDefault(); dpDecide(ds.dpdecide, ds.dpok === "1"); return; }
    if (ds.dpfiled !== undefined){
      ev.preventDefault();
      if (st.sel){ st.filedSel = ds.dpfiled; st.tab[st.sel] = "filed"; }
      dpRender(); return;
    }
    if (ds.dpperson !== undefined){
      ev.preventDefault();
      if (st.sel){ st.personSel = ds.dpperson; st.tab[st.sel] = "people"; }
      dpRender(); return;
    }
    if (ds.dpdoc !== undefined){
      ev.preventDefault();
      if (typeof o2OpenDoc === "function") o2OpenDoc(ds.dpdoc, ds.dptitle);   /* the Org screen's own reader */
      return;
    }
    /* An app opens the way the Org screen opens it (A26): its own o2OpenApp,
       over the module o2LoadApps already put in that screen's cache. The
       department card yields to the app frame, exactly as it yields to a
       document -- there is no second app viewer written here. */
    if (ds.dpapp !== undefined){
      ev.preventDefault();
      if (typeof o2S !== "function" || typeof o2OpenApp !== "function") return;
      const m = (o2S().apps[st.sel] || []).filter(x => x.id === ds.dpapp)[0];
      if (m) o2OpenApp(m);
      return;
    }
  });
}
