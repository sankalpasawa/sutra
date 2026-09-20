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
  /* Engines, People and Apps read routes that land in a later slice; until then
     the group is on screen and says so in one line rather than showing nothing. */
  groups += dpGroup("Engines", [], "engines", "Not read yet");
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

function dpRunRow(label, note){
  return `<div class="dprow"><span class="dpdot"></span><span>${dpEsc(label)}${note ? `<div class="dpchk">${dpEsc(note)}</div>` : ""}</span></div>`;
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
function dpWhen(at){ const m = /T(\d\d:\d\d)/.exec(String(at || "")); return m ? m[1] : ""; }
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

function dpViewerHtml(n, d, dept, err){
  const st = dpS();
  const tab = st.tab[n.ref] || "now";
  if (tab === "now") return dpViewerShell("Now", dpNowHtml());
  if (tab === "identity"){
    dpLoadIdentity(n.ref);                               /* read on open, as o2LoadApps does */
    return dpViewerShell("Identity", dpIdentityHtml());
  }
  const label = (DP_FUNCS.find(f => f[0] === tab) || [tab, tab])[1];
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
  const DP_SEL = "[data-dptab],[data-dpdecide],[data-dpmore],[data-dpfiled],[data-dpdoc],[data-dpengine],[data-dpchatmode],[data-dppane],[data-dpgoal]";
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
    if (ds.dpgoal !== undefined){
      ev.preventDefault();
      /* the Org screen's own write-it sheet, which posts org.charter through
         /api/org2/request -- this screen adds no second way to ask (A12) */
      if (typeof o2OpenSheet === "function") o2OpenSheet("charter");
      return;
    }
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
