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
  if (!S.dp) S.dp = { sel:null, tab:{}, pane:{}, engineSel:null, filedSel:null, chatMode:{},
                      loading:{}, error:{}, busy:{}, more:{}, confirm:null,
                      identity:null, now:null, running:null, waits:null,
                      adaptation:null, priority:null, coordination:null, audit:null,
                      engines:null, engineRuns:{}, engineData:{}, filed:null,
                      people:null, meters:null };
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
    st.engineSel = null; st.filedSel = null; st.confirm = null;
    st.more = {}; st.error = {}; st.loading = {}; st.pane = {}; st.chatMode = {};
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
  groups += dpGroup("Filed work", filed.map(x =>
    dpRow(x.label, `data-dpfiled="${dpEsc(x.id || "")}"`, st.filedSel === x.id)), "filed", "Nothing filed yet");
  groups += dpGroup("People", [], "people", "Not read yet");
  groups += dpGroup("Documents", docs.map(x =>
    dpRow(x.title, `data-dpdoc="${dpEsc(x.path)}" data-dptitle="${dpEsc(x.title)}"`, false)), "docs", "No documents yet");
  groups += dpGroup("Apps", [], "apps", "Not read yet");
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
  if (!asks.length && !waits.length && !running.length){
    return failed ? dpQuiet("Could not read") : dpQuiet("Nothing waiting on you");
  }
  let body = "";
  if (asks.length) body += dpCard("Asks", asks.map(dpAskHtml).join(""));
  if (waits.length) body += dpCard("Waits", waits.map(w => dpRunRow(w.objective, w.state)).join(""));
  if (running.length) body += dpCard("Running", running.map(r => dpRunRow(r.goal, "")).join(""));
  return body;
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
  const tabs = dpTabsHtml(pane, [
    ["identity", "Identity"],
    ["owner", "With " + (owner || "the owner")],
    ["adaptation", "With Adaptation"],
  ], "data-dppane");
  if (pane === "owner") return tabs + dpChatCard(owner || "The owner", chats.owner, ref + ":owner");
  if (pane === "adaptation") return tabs + dpChatCard("Adaptation", chats.adaptation, ref + ":adaptation");
  return tabs + dpIdentityCardHtml(id);
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
  const tabs = dpTabsHtml(pane, panes || [[tab, label], ["chat", "Chat"]], "data-dppane");
  if (pane === "chat"){
    const rows = (typeof chat === "function") ? chat(data) : (chat || data.chat);
    return tabs + dpChatCard("Chat", rows, ref + ":" + tab + ":chat");
  }
  return tabs + card(data, pane);
}

/* Adaptation: what it wants changed, and the asking behind it. */
function dpPropHtml(p){
  const note = [p.evidence, p.state].filter(Boolean).join(" · ");
  return dpRunRow(p.change, note, p.open ? "warn" : "ok", p.open ? dpBar(dpLeft(p)) : "");
}
function dpAdaptationCard(a){
  const props = a.proposals || [], pats = a.patterns || [];
  /* the one action: the Org screen's existing write-it ask, which is how a
     rule is changed here too -- this screen still files nothing of its own */
  const offer = `<div class="dpoffer"><button type="button" class="btn" data-dprule="1">Change a rule</button></div>`;
  if (!props.length && !pats.length) return dpQuiet("Nothing to change yet") + offer;
  let body = "";
  if (props.length) body += dpCard("Proposals", props.map(dpPropHtml).join(""));
  if (pats.length) body += dpCard("Seen in the logbook", pats.map(p =>
    dpRunRow(p.summary, "Since " + dpStamp(p.since_ms))).join(""));
  return body + offer;
}

/* Priority: what it took on, in the order it took it, under one ceiling. */
function dpPriorityCard(p){
  const q = p.queue || [];
  const budget = dpBudgetHtml(p.budget);
  if (!q.length && !(p.budget && p.budget.running_at_once != null)) return dpQuiet("Nothing in the queue");
  let body = "";
  if (q.length) body += dpCard("Queue", q.map(r => dpRunRow(r.next,
    [r.runs_as ? "Runs as " + r.runs_as : "", dpWhenMs(r.when_ms)].filter(Boolean).join(" · "),
    "ok")).join(""));
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
function dpEngineTable(e){
  const st = dpS();
  const grid = `<div class="dpengines">` +
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
  return dpCard("The engine", grid) + act;
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
  return dpCard("Runs", rows.map(r => {
    const live = r.started_at && !r.ended_at;
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
  if (tab === "now") return dpViewerShell("Now", dpNowHtml());
  if (tab === "identity"){
    dpLoadIdentity(n.ref);                               /* read on open, as o2LoadApps does */
    return dpViewerShell("Identity", dpIdentityHtml());
  }
  if (tab === "engines"){
    dpLoadEngines(n.ref);
    const e = dpEngine();
    return dpViewerShell(e ? e.name : "Engines", dpEnginesHtml());
  }
  const label = (DP_FUNCS.find(f => f[0] === tab) || [tab, tab])[1];
  const card = DP_CARDS[tab];
  if (card){
    card[0](n.ref);                                      /* read on open, the same way */
    return dpViewerShell(label, dpFnHtml(tab, label, card[1]));
  }
  return dpViewerShell(label, dpQuiet("Not read yet"));
}

/* ── answering an ask ─────────────────────────────────────────────────────── */
/* Stamp and Refuse call decideProposal (08-boot.js:145-153) -- the SAME call
   the Approvals panel makes -- and nothing else. This screen files no write of
   its own; the answer lands, then Now is re-read so the card tells the truth. */
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
  if (st.sel) await dpLoadNow(st.sel, true);
  dpRender();
}

/* ── handlers ─────────────────────────────────────────────────────────────── */
/* Delegated, and gated twice: the screen must be org2 AND the click must have
   landed inside a `.dp` element. That is 19-org2.js:875-880's own guard with
   this screen's class, so nothing here can fire on another screen. */
if (typeof document !== "undefined" && document.addEventListener){
  const DP_SEL = "[data-dptab],[data-dpdecide],[data-dpmore],[data-dpfiled],[data-dpdoc],[data-dpengine],[data-dppause],[data-dpchatmode],[data-dppane],[data-dpgoal],[data-dprule]";
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
    if (ds.dpmore !== undefined){ st.more[ds.dpmore] = true; dpRender(); return; }
    if (ds.dpdecide !== undefined){ ev.preventDefault(); dpDecide(ds.dpdecide, ds.dpok === "1"); return; }
    if (ds.dpfiled !== undefined){ ev.preventDefault(); st.filedSel = ds.dpfiled; dpRender(); return; }
    if (ds.dpdoc !== undefined){
      ev.preventDefault();
      if (typeof o2OpenDoc === "function") o2OpenDoc(ds.dpdoc, ds.dptitle);   /* the Org screen's own reader */
      return;
    }
  });
}
