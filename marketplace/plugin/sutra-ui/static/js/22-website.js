/* 22-website.js -- the website department on the department screen.

   The first build of the Native design (system/first-build.html): one
   department whose four engines are run by the motor inside the app
   (website_dept.py, routes in website_api.py). This file draws it INSIDE the
   department screen 20-dept.js already owns, through three hooks there:

     wbList(n)      replaces the list's first group (Map, System status, Motor)
                    and its Engines and Filed work groups, for a website
                    department only; every other group is 20-dept.js's own
     wbViewer(n)    draws the viewer when one of this file's entries is open,
                    and adds the internal systems' own state under the five
                    function cards; for a department on the engine runtime
                    it also draws the Board, and every engine and function as
                    its steps, each on its rung
     wbMenuItem()   one line in the Org screen's Edit menu: the command that
                    founds an organisation with its one Root; Root then sets
                    up every department the person asks it for

   Every other department is untouched: both list and viewer hooks answer null
   unless the selected department has a website record.

   Copy discipline is 20-dept.js's: names, never paths; no counts at rest; no
   help text; one quiet line for an empty state; every colour a panel.css token. */

const WB_POLL_MS = 2500;
const WB_FUNCS = ["identity", "adaptation", "priority", "coordination", "audit"];
const WB_PANES = [["item", "The work item"], ["preview", "Preview"], ["versions", "Versions"], ["trace", "Trace"]];
const WB_ENG_PANES = [["engine", "Engine"], ["runs", "Runs"]];
const WB_DOTS = { ok: "ok", failed: "block", running: "", skipped: "warn", interrupted: "warn" };
const WB_WORDS = { ok: "Done", failed: "Failed", running: "Running", skipped: "Skipped", interrupted: "Interrupted" };
/* A department on the engine runtime (engine_runtime.py) shows three things
   more: every engine and function as its steps, each on its rung; the board
   the engines speak on; and what the department said back to its owner. */
const WB_RT_PANES = [["steps", "Steps"], ["engine", "Engine"], ["runs", "Runs"]];
const WB_RUNGS = [["P", "Person"], ["C0", "Improvised call"], ["C1", "Checklist"], ["C2", "Code"]];
const WB_THREADS = { "submitted": ["", "Sent"], "working": ["", "Working"], "input-required": ["warn", "Waits for you"],
                     "completed": ["ok", "Done"], "failed": ["block", "Failed"], "canceled": ["off", "Let go"], "rejected": ["block", "Refused"] };
const WB_ACTS = { "request": "asks", "agree": "agrees", "refuse": "refuses", "propose": "proposes", "accept-proposal": "accepts",
                  "reject-proposal": "rejects", "inform": "tells", "failure": "could not", "not-understood": "did not follow", "cancel": "lets go" };

function wbS(){
  if (!S.wb) S.wb = { refs: null, refsBusy: false, refsMissed: {}, map: {}, sig: {}, tab: {}, pane: {}, sel: {}, draft: {},
                      busy: {}, err: {}, engine: {}, art: {}, trace: {}, steps: {}, board: {}, chat: {}, chatSig: {},
                      fnchat: {}, fnchatSig: {}, chip: {}, thread: {}, turns: {}, scroll: {}, found: null, timer: null };
  return S.wb;
}
function wbRt(m){ return !!(m && m.runtime === 2); }
/* The Map and the Board of the second design (23-screens.js) are the default
   for a department on the engine runtime (founder, 2026-09-28: "Make changes
   to map, chart, and board. Do these changes... Don't change the
   navigation."). The way back is `?screens=v1` in the address, kept in
   localStorage; the first design's tests set the switch off themselves. */
function wbV2(){
  const st = wbS();
  if (st.v2 !== undefined) return st.v2;
  st.v2 = true;
  try {
    const q = (typeof location !== "undefined" && location.search) || "";
    const m = /[?&]screens=(v2|v1)\b/.exec(q);
    /* the one writer goes through lsSet (01-state.js), which the chat-only frame refuses (test_embed.js) */
    if (m){ st.v2 = m[1] === "v2"; if (typeof lsSet === "function") lsSet("sutra.screens", m[1]); }
    else if (typeof localStorage !== "undefined" && JSON.parse(localStorage.getItem("sutra.screens") || "null") === "v1") st.v2 = false;
  } catch (e) { st.v2 = true; }
  return st.v2;
}
function wbEsc(x){ return dpEsc(x); }
function wbUrl(ref, tail){ return "/api/native/" + encodeURIComponent(ref) + "/" + tail; }
function wbIs(ref){
  const st = wbS();
  if (st.refs === null){ wbLoadRefs(); return false; }
  if (!st.refs[ref] && ref && !st.refsMissed[ref]){
    /* a department born since the list was read (Root made it): the list is read again, once for that name, and the
       department wears its own view when the read lands (found live 2026-09-28: the first build's card until a reload) */
    st.refsMissed[ref] = true;
    wbLoadRefs();
  }
  return !!st.refs[ref];
}
async function wbLoadRefs(again){
  const st = wbS();
  if (st.refsBusy) return;
  st.refsBusy = true;
  let sig = null;
  try {
    const r = await apiGet("/api/native/depts");
    st.refs = {};
    ((r && r.depts) || []).forEach(d => { st.refs[d.ref] = d; });
    sig = JSON.stringify(st.refs);
  } catch (e) { if (!again) st.refs = {}; }
  st.refsBusy = false;
  /* on the clock (again) the list is read for what is working now (SIM-3 a): a paint only when something changed */
  const moved = sig !== null && sig !== st.refsSig;
  if (sig !== null) st.refsSig = sig;
  if (again && !moved) return;
  if (!again) wbTick();
  dpRender();
}
/* A department on the engine runtime opens on its chat: the one point of entry
   (founder, 2026-09-28). One of the first build opens on its Map, as before. */
function wbTab(ref){
  const st = wbS();
  return st.tab[ref] === undefined ? (wbRt(st.map[ref]) ? "chat" : "map") : st.tab[ref];
}
/* What the screen compares to decide whether to paint again. The motor's
   heartbeat moves every tick and is patched in place, so it is left out: a
   preview frame must not reload because a clock moved. */
function wbSig(m){
  return JSON.stringify([m.stopped, m.has_goal, m.status, m.recent, m.live,
    (m.artifacts || []).map(a => [a.name, a.versions]), (m.engines || []).map(e => [e.name, e.state, e.envelope])]);
}
async function wbLoadMap(ref, force){
  const st = wbS();
  if (!ref || st.busy["map:" + ref]) return;
  st.busy["map:" + ref] = true;
  try {
    const m = await apiGet(wbUrl(ref, "map"));
    const sig = wbSig(m);
    const changed = sig !== st.sig[ref];
    st.map[ref] = m; st.sig[ref] = sig; delete st.err[ref];
    wbPatchMotor(m);
    if (changed || force){
      /* what is open re-reads with it, so a run that just ended shows its row */
      st.engine = {}; st.art = {}; st.trace = {};
      wbAgain(ref);
      if (!wbTyping()) dpRender();
    }
  } catch (e) {
    st.err[ref] = (e && e.message) || String(e);
  }
  delete st.busy["map:" + ref];
}
function wbTyping(){
  const a = document.activeElement;
  return !!(a && a.closest && a.closest(".wb") && /^(INPUT|TEXTAREA)$/.test(a.tagName));
}
function wbTick(){
  const st = wbS();
  if (st.timer) return;
  st.timer = setInterval(() => {
    if (S.screen !== "org2" || !S.dp || !S.dp.sel) return;
    /* every fourth tick the list of departments is read again, for the working marks on the tree (SIM-3 a) */
    st.ticks = (st.ticks || 0) + 1;
    if (st.ticks % 4 === 0 && st.refs) wbLoadRefs(true);
    if (!wbIs(S.dp.sel)) return;
    wbLoadMap(S.dp.sel);
    /* a department's answer lands on Root's board without a run of Root's own, so the open chat is read on its own clock */
    if (wbTab(S.dp.sel) === "chat" && st.chat[S.dp.sel]) wbLoadChat(S.dp.sel, true);
    /* a function's open chat is read on the same clock */
    const ftab = (typeof dpS === "function" && dpS().tab[S.dp.sel]) || "", fk = S.dp.sel + ":" + ftab;
    if (ftab && st.fnchat[fk] && dpS().pane[fk] === "chat") wbLoadFnChat(S.dp.sel, ftab, true);
  }, WB_POLL_MS);
}
function wbMotorState(m){
  const age = m && m.health && m.health.motor ? m.health.motor.age_s : null;
  if (age === null || age === undefined) return ["block", "Not running"];
  if (age < 15) return ["ok", "Running"];
  return [age < 90 ? "warn" : "block", age < 90 ? "Slow" : "Not running"];
}
function wbPatchMotor(m){
  const [cls, word] = wbMotorState(m);
  document.querySelectorAll("[data-wbmotor]").forEach(el => {
    el.className = "dpdot " + cls;
    const w = el.parentNode && el.parentNode.querySelector("[data-wbmotorword]");
    if (w) w.textContent = word;
  });
}

/* ── the list ─────────────────────────────────────────────────────────────── */
function wbEngDot(e){
  if (e.state === "Running") return "";
  if (e.state === "Waits") return "warn";
  if (e.last && e.last.status === "failed") return "block";
  return e.last ? "ok" : "off";
}
function wbList(n){
  if (!wbIs(n.ref)) return null;
  const st = wbS(), m = st.map[n.ref], tab = wbTab(n.ref);
  if (!m) wbLoadMap(n.ref);
  const top = `<div class="o2g dpg wb">` +
    (wbRt(m) ? dpRow("Chat", `data-wbtab="chat"`, tab === "chat") : "") +
    dpRow("Map", `data-wbtab="map"`, tab === "map") +
    dpRow("System status", `data-wbtab="status"`, tab === "status") +
    dpRow("Motor", `data-wbtab="motor"`, tab === "motor") +
    (wbRt(m) ? dpRow("Board", `data-wbtab="board"`, tab === "board") : "") + `</div>`;
  const engines = dpGroup("Engines", ((m && m.engines) || []).map(e => {
    const on = tab === "engine" && st.sel[n.ref] === e.name;
    const word = e.state === "Running" ? "running" : (e.state === "Waits" ? "paused" : "idle");
    return `<button type="button" class="o2li dpli dpeng wb${on ? " on" : ""}" data-wbengine="${wbEsc(e.name)}">` +
      `<span>${wbEsc(e.name)}</span><span class="dpst ${word}">${wbEsc(e.state)}</span></button>`;
  }), null, m ? "No engines here" : "Not read yet");
  const filed = dpGroup("Filed work", ((m && m.artifacts) || []).filter(a => a.versions).map(a => {
    const on = tab === "art" && st.sel[n.ref] === a.slug;
    return `<button type="button" class="o2li dpli dpeng wb${on ? " on" : ""}" data-wbart="${wbEsc(a.slug)}">` +
      `<span>${wbEsc(a.name)}</span>${dpVerDots(a.versions)}</button>`;
  }), null, m ? "Nothing filed yet" : "Not read yet");
  /* Human Sutra is an app, not part of the core: a department on the engine
     runtime carries it in its Apps group (PRD section J) */
  const apps = wbRt(m) ? [dpRow("Human Sutra", `data-wbtab="conversation"`, tab === "conversation")] : [];
  return { top, engines, filed, apps };
}

/* ── shared pieces ────────────────────────────────────────────────────────── */
function wbWhen(at){
  const d = new Date(at);
  if (isNaN(d)) return "";
  const p = x => String(x).padStart(2, "0");
  return p(d.getHours()) + ":" + p(d.getMinutes());
}
function wbDot(cls){ return `<span class="dpdot${cls ? " " + cls : ""}"></span>`; }
function wbBtn(label, attrs, cls){ return `<button type="button" class="btn wb${cls ? " " + cls : ""}" ${attrs}>${wbEsc(label)}</button>`; }
function wbRunRow(r, extra){
  return dpRunRow((r.engine || "") + (r.at || r.started ? " · " + wbWhen(r.at || r.started) : ""), r.what || "",
                  WB_DOTS[r.status] === undefined ? "" : WB_DOTS[r.status], extra || "");
}
/* The textarea carries an id: render() (06-render.js) carries focus, caret and
   value across a rebuild for a focused input that has one, so a background
   paint never takes the words out from under the person typing them. */
function wbAskBox(ref, key, placeholder, action, label){
  const st = wbS(), k = ref + ":" + key;
  const err = st.err[k] ? `<div class="o2quiet dpq">${wbEsc(st.err[k])}</div>` : "";
  return `<div class="wbask wb"><textarea id="wbd-${wbEsc(key)}" data-wbdraft="${wbEsc(k)}" rows="2" placeholder="${wbEsc(placeholder)}">${wbEsc(st.draft[k] || "")}</textarea>` +
    wbBtn(label, `${action}="${wbEsc(key)}"`, "dpstamp") + err + `</div>`;
}
function wbAsksHtml(m){
  const asks = (m.status && m.status.asks) || [];
  if (!asks.length) return dpQuiet("Nothing is waiting for you");
  return asks.map(a => `<div class="dpask wb"><div class="dpasks">${wbEsc(a.text)}</div>` +
    `<div class="dpaskd">${wbEsc(a.engine)} · ${wbEsc(wbWhen(a.created))}</div>` +
    wbBtn("Stamp", `data-wbdecide="${wbEsc(a.id)}" data-wbok="1"`, "dpstamp") +
    wbBtn("Refuse", `data-wbdecide="${wbEsc(a.id)}" data-wbok="0"`) + `</div>`).join("");
}
function wbControls(m){
  if (wbRt(m)) return `<div class="wbctl wb">` + wbOnOff(m) + `</div>`;
  return `<div class="wbctl wb">` + wbBtn(m.stopped ? "Resume" : "Stop", m.stopped ? `data-wbresume="1"` : `data-wbstop="1"`) + `</div>`;
}
/* Start is just a button (founder, 2026-09-28): one button on the department,
   Start when it is off and Stop when it is on. It is a signal to every engine
   and function of the department; each then looks to its own triggers.

   WORDS. On this screen the five are functions: that is the users' word.
   "Internal system" is the word inside, for documents and code, and it is
   never printed here (founder, 2026-09-28; test_website.js W19). */
function wbOnOff(m){
  return m.stopped ? wbBtn("Start", `data-wbresume="1"`, "wbonoff dpstamp") : wbBtn("Stop", `data-wbstop="1"`, "wbonoff");
}

/* ── Map ──────────────────────────────────────────────────────────────────── */
function wbSystemTile(s, m){
  const off = s.state !== "running";
  let mark = "";
  if (s.name === "Identity") mark = dpBar(m.live ? 1 : ((m.artifacts || []).filter(a => a.versions).length / 5));
  else if (s.name === "Priority"){
    const e = (m.engines || []).reduce((a, x) => Math.max(a, x.envelope ? x.envelope.used_calls / (x.envelope.calls || 1) : 0), 0);
    mark = dpBar(Math.min(1, e));
  } else if (s.name === "Coordination") mark = `<span class="dpdots">${(m.engines || []).map(() => "<i></i>").join("")}</span>`;
  else mark = `<span class="dpchk">${off ? "Paused" : "Awake"}</span>`;
  return `<button type="button" class="wbtile wb${off ? " off" : ""}" data-wbfn="${wbEsc(s.name.toLowerCase())}">` +
    `<b>${wbDot(off ? "off" : "ok")}${wbEsc(s.name)}</b>${mark}</button>`;
}
function wbFlowHtml(m){
  const arts = {}; (m.artifacts || []).forEach(a => { arts[a.name] = a; });
  const doc = name => {
    const a = arts[name] || { versions: 0, slug: "" };
    return `<button type="button" class="wbdoc wb${a.versions ? "" : " none"}" ${a.versions ? `data-wbart="${wbEsc(a.slug)}"` : "disabled"}>` +
      `${wbEsc(name)}${dpVerDots(a.versions) || `<span class="dpdots"><i></i></span>`}</button>`;
  };
  const eng = e => `<button type="button" class="wbeng wb" data-wbengine="${wbEsc(e.name)}">${wbDot(wbEngDot(e))}${wbEsc(e.name)}</button>`;
  const arrow = `<span class="wbarrow">&rarr;</span>`;
  /* two engines to a row, each row opening on the artifact it reads, as drawn */
  const engs = m.engines || [], rows = [];
  for (let i = 0; i < engs.length; i += 2) rows.push(engs.slice(i, i + 2));
  return rows.map(r => `<div class="wbflow">` + doc(r[0].reads) +
    r.map(e => arrow + eng(e) + arrow + doc(e.writes)).join("") + `</div>`).join("");
}
function wbGoalHtml(n, m){
  return dpCard("Goal", `<div class="dpbig">${wbEsc(m.name)}</div>` +
    wbAskBox(n.ref, "goal", "What is this website for?", "data-wbgoal", "Start"));
}
/* One way in. A runtime department reads the words and recognises which of
   the five journeys they are (a task, a question, a rule, feedback, an idea),
   so the screen never asks the owner to choose. */
function wbAskCard(n, m){
  return wbRt(m) ? dpCard("Say", wbAskBox(n.ref, "ask", m.say || "A task, a question, a rule, feedback or an idea", "data-wbask", "Send"))
                 : dpCard("Ask", wbAskBox(n.ref, "ask", "Ask for a page or a change", "data-wbask", "Ask"));
}
/* What the department said back to its owner, newest first: every exchange is
   on the screen, none is hidden in a record. */
function wbRepliesHtml(n, m){
  if (!wbRt(m)) return "";
  const b = wbS().board[n.ref];
  if (!b){ wbLoadBoard(n.ref); return ""; }
  const said = [];
  (b.threads || []).forEach(t => (t.posts || []).forEach(p => {
    if ((p.dst || []).indexOf("Owner") >= 0 && p.line) said.push(p);
  }));
  if (!said.length) return "";
  said.sort((a, b2) => b2.n - a.n);
  return dpCard("Replies", said.slice(0, 5).map(p => dpRunRow(p.line,
    p.src + " " + (WB_ACTS[p.msg_type] || p.msg_type) + " · " + wbWhen(p.at), p.msg_type === "request" ? "warn" : (p.msg_type === "inform" ? "ok" : "block"))).join(""));
}
function wbMapHtml(n, m){
  if (!m.has_goal) return wbGoalHtml(n, m) + dpCard("The department", `<div class="wbgrid">${m.systems.map(s => wbSystemTile(s, m)).join("")}</div>` + wbFlowHtml(m));
  const [mc, mw] = wbMotorState(m);
  const st = m.status || {};
  const lane = (label, rows, cls) => `<div class="wblane"><div class="dpk">${label}</div>` +
    (rows.length ? rows.map(() => wbDot(cls)).join("") : wbDot("off")) + `</div>`;
  const rt = wbRt(m);
  const status = `<div class="wblanes">` + lane("Asks", st.asks || [], "") + lane("Waits", st.waits || [], "warn") +
    lane("Running", st.running || [], "ok") + lane("Escalated", st.escalated || [], "block") + `</div>` +
    wbAsksHtml(m) + (rt ? "" : wbControls(m));
  const health = `<div class="wbhealth">` + ((m.health && m.health.checks) || []).map(c =>
    `<span title="${wbEsc(c.line)}">${wbDot(c.state)}${wbEsc(c.name)}</span>`).join("") + `</div>`;
  const live = m.live ? wbBtn("Open the live site", `data-wbart="live-site" data-wbpane="preview"`) : "";
  const head = rt
    ? `<div class="wbmotor">${wbDot(m.stopped ? "off" : mc)}<span>${m.stopped ? "Off" : (mw === "Running" ? "On" : wbEsc(mw))}</span>` +
      `${wbOnOff(m)}${live}</div>`
    : `<div class="wbmotor"><span class="dpdot ${mc}" data-wbmotor="1"></span><span data-wbmotorword="1">${wbEsc(mw)}</span>` +
      `<span class="dpchk">Motor</span>${m.stopped ? `<span class="dpst paused">Stopped</span>` : ""}${live}</div>`;
  /* a Root that has not been asked for anything yet: the one empty state that names the action, so the person who
     just founded an organisation knows the next thing is to say what the first department is for */
  const asked = ((m.artifacts || []).filter(a => a.name === "Request")[0] || {}).versions;
  const rootEmpty = m.kind === "root" && !asked ? dpCard("Departments", dpQuiet("No department yet. Say what the first one is for.")) : "";
  return dpCard("The department", head +
      `<div class="wbgrid">${m.systems.map(s => wbSystemTile(s, m)).join("")}</div>` + wbFlowHtml(m)) +
    rootEmpty +
    dpCard("System status", status) +
    wbAskCard(n, m) + wbRepliesHtml(n, m) +
    dpCard("Health", health) +
    dpCard("Recent", (m.recent || []).length ? m.recent.map(r => wbRunRow(r)).join("") : dpQuiet("Nothing has run yet"));
}

/* ── System status ────────────────────────────────────────────────────────── */
function wbStatusHtml(n, m){
  const st = m.status || {};
  const rows = (xs, fn, quiet) => xs && xs.length ? xs.map(fn).join("") : dpQuiet(quiet);
  return wbControls(m) +
    dpCard("Asks", wbAsksHtml(m)) +
    dpCard("Waits", rows(st.waits, w => dpRunRow(w.what, w.why, "warn"), "Nothing is waiting")) +
    dpCard("Running", rows(st.running, r => dpRunRow(r.engine, r.what, "ok"), m.stopped ? "Stopped" : "Nothing is running")) +
    dpCard("Escalated", rows(st.escalated, a => dpRunRow(a.engine, a.text, "block",
      wbBtn("Stamp", `data-wbdecide="${wbEsc(a.id)}" data-wbok="1"`, "dpstamp")), "Nothing escalated")) +
    wbAskCard(n, m) + wbRepliesHtml(n, m);
}

/* ── Motor ────────────────────────────────────────────────────────────────── */
function wbTimelineHtml(rows){
  if (!rows.length) return dpQuiet("Nothing has run yet");
  const t0 = Math.min.apply(null, rows.map(r => +new Date(r.started)));
  const t1 = Math.max.apply(null, rows.map(r => +new Date(r.ended || r.started))) + 1000;
  const span = Math.max(1000, t1 - t0);
  const names = [];
  rows.forEach(r => { if (names.indexOf(r.engine) < 0) names.push(r.engine); });
  return `<div class="wbtl">` + names.map(nm => {
    const bars = rows.filter(r => r.engine === nm).map(r => {
      const a = (+new Date(r.started) - t0) / span * 100;
      const w = Math.max(0.8, ((+new Date(r.ended || r.started)) - (+new Date(r.started))) / span * 100);
      return `<i class="${WB_DOTS[r.status] || "run"}" style="left:${a.toFixed(2)}%;width:${w.toFixed(2)}%" title="${wbEsc((r.what || "") + " · " + wbWhen(r.started))}"></i>`;
    }).join("");
    return `<div class="wbtlr"><span>${wbEsc(nm)}</span><div class="wbtlb">${bars}</div></div>`;
  }).join("") + `<div class="wbtlx"><span>${wbEsc(wbWhen(t0))}</span><span>${wbEsc(wbWhen(t1))}</span></div></div>`;
}
function wbMotorHtml(n, m){
  const h = m.health || {}, [mc, mw] = wbMotorState(m);
  const next = (m.status && m.status.next) || "";
  const running = ((m.status && m.status.running) || [])[0];
  const due = /@/.test(next) ? next.split("@")[0] : "";
  const why = running ? "After this run" : (due ? "" : next.charAt(0).toUpperCase() + next.slice(1));
  const loop = ["A tick, or a new version", "Due slots, from the timetable", "The envelope has room", "No lock is held", "The run starts", "A run row, and a new version"];
  return dpCard("Motor", `<div class="dpengines">` +
      dpCell("State", `<div class="dpbig"><span class="dpdot ${mc}" data-wbmotor="1"></span> <span data-wbmotorword="1">${wbEsc(mw)}</span></div>`) +
      dpKV("Now", running ? running.engine : "", m.stopped ? "Stopped" : "Nothing is running") +
      dpKV("Next", due, why || "Nothing due") + `</div>`) +
    dpCard("It only reads", dpRunRow("When", "Coordination's timetable", "ok") + dpRunRow("How much", "Priority's envelope", "ok") +
      dpRunRow("Whether", "Identity's rules", "ok") + dpRunRow("What", "The engine's own steps", "ok")) +
    dpCard("What it does each tick", loop.map((l, i) => dpRunRow(l, "", i < 4 ? "" : "ok")).join("")) +
    dpCard("Checks", (h.checks || []).map(c => dpRunRow(c.name, c.line, c.state)).join("")) +
    dpCard("Timeline", wbTimelineHtml(h.timeline || [])) +
    dpCard("Never happens", (h.never || []).map(x => dpRunRow(x.name, "", x.ok ? "ok" : "block")).join(""));
}

/* ── an engine ────────────────────────────────────────────────────────────── */
async function wbLoadEngine(ref, name){
  const st = wbS(), k = ref + ":" + name;
  if (st.engine[k] || st.busy["e:" + k]) return;
  st.busy["e:" + k] = true;
  try { st.engine[k] = await apiGet(wbUrl(ref, "engine/" + encodeURIComponent(name))); } catch (e) { st.err["e:" + k] = String(e); }
  delete st.busy["e:" + k];
  dpRender();
}
function wbEngineHtml(n){
  const st = wbS(), name = st.sel[n.ref], k = n.ref + ":" + name;
  const rt = wbRt(st.map[n.ref]);
  const pane = st.pane[k] || (rt ? "steps" : "engine");
  const tabs = dpTabsHtml(pane, rt ? WB_RT_PANES : WB_ENG_PANES, `data-wbpanekey="${wbEsc(k)}" data-wbpane`);
  if (rt && pane === "steps") return tabs + wbStepsHtml(n.ref, name);
  const e = st.engine[k];
  if (!e){ wbLoadEngine(n.ref, name); return (rt ? tabs : "") + dpSkel(); }
  if (pane === "runs"){
    return tabs + dpCard("Runs", (e.runs || []).length ? e.runs.map(r => wbRunRow(r,
      r.wrote ? ` <button type="button" class="o2more wb" data-wbart="${wbEsc(r.wrote.art.toLowerCase().replace(/[^a-z0-9]+/g, "-"))}" data-wbpane="trace" data-wbv="${r.wrote.v}">Trace</button>` : "")).join("")
      : dpQuiet("No runs yet"));
  }
  const env = e.envelope || {};
  return tabs + dpCard("The engine", `<div class="dpengines">` +
      dpKV("Runs as", e.runs_as, "Not named") + dpKV("Needs", e.reads, "Not named") + dpKV("Makes", e.writes, "Not named") + `</div>`) +
    dpCard("In its slot", `<div class="dpengines">` +
      dpKV("Slot", e.slot, "Not named") +
      dpCell("Envelope", dpBar(Math.min(1, (env.used_calls || 0) / (env.calls || 1)))) +
      dpCell("Autonomy window", dpBar(Math.min(1, (e.window_min || 0) / 30))) + `</div>`);
}

/* ── the engine runtime: steps on their rungs, and the board ──────────────── */
async function wbLoadSteps(ref, name, again){
  const st = wbS(), k = ref + ":" + name;
  if ((st.steps[k] && !again) || st.busy["s:" + k]) return;
  st.busy["s:" + k] = true;
  try { st.steps[k] = await apiGet(wbUrl(ref, "steps/" + encodeURIComponent(name))); }
  catch (e) { if (!st.steps[k]) st.steps[k] = { failed: true }; }
  delete st.busy["s:" + k];
  if (!again || !wbTyping()) dpRender();
}
async function wbLoadBoard(ref, again){
  const st = wbS();
  if ((st.board[ref] && !again) || st.busy["b:" + ref]) return;
  st.busy["b:" + ref] = true;
  try { st.board[ref] = await apiGet(wbUrl(ref, "board")); }
  catch (e) { if (!st.board[ref]) st.board[ref] = { failed: true }; }
  delete st.busy["b:" + ref];
  if (!again || !wbTyping()) dpRender();
}
async function wbLoadChat(ref, again){
  const st = wbS();
  if ((st.chat[ref] && !again) || st.busy["c:" + ref]) return;
  st.busy["c:" + ref] = true;
  try {
    const v = await apiGet(wbUrl(ref, "chat"));
    const sig = JSON.stringify(v);
    const moved = sig !== st.chatSig[ref] || !st.chat[ref];
    /* a department Root made since the tree was read: the tree learns of it here, without a reload (found live
       2026-09-28: the person could not open the department he had just stamped) */
    const known = ((st.chat[ref] || {}).departments || []).length, now = (v.departments || []).length;
    st.chat[ref] = v; st.chatSig[ref] = sig;
    delete st.busy["c:" + ref];
    if (st.chatSig[ref + ":depts"] !== undefined && now > known && typeof loadOrg2 === "function"){
      if (typeof o2S === "function" && o2S().expanded) o2S().expanded.add(ref);
      loadOrg2(true);
      wbLoadRefs();                              /* and the list of departments on the runtime, so the new one opens on its own view */
    }
    st.chatSig[ref + ":depts"] = now;
    if (moved && (!again || !wbTyping())) dpRender();
  } catch (e) {
    if (!st.chat[ref]) st.chat[ref] = { failed: true };
    delete st.busy["c:" + ref];
    if (!again) dpRender();
  }
}
/* The record moved: what is already on the screen is read again and swapped in
   when it arrives, so a card never blinks empty between two reads. */
function wbAgain(ref){
  const st = wbS();
  Object.keys(st.steps).forEach(k => { if (k.indexOf(ref + ":") === 0) wbLoadSteps(ref, k.slice(ref.length + 1), true); });
  if (st.board[ref]) wbLoadBoard(ref, true);
  if (st.chat[ref]) wbLoadChat(ref, true);
  Object.keys(st.fnchat).forEach(k => { if (k.indexOf(ref + ":") === 0) wbLoadFnChat(ref, k.slice(ref.length + 1), true); });
}
function wbRungHtml(s){
  const at = WB_RUNGS.map(r => r[0]).indexOf(s.rung);
  return `<span class="wbrung" title="${wbEsc(s.rung_name)}">` +
    WB_RUNGS.map((r, i) => `<i${i <= at ? ` class="on"` : ""}></i>`).join("") + `</span>`;
}
function wbRungName(id){ return (WB_RUNGS.filter(r => r[0] === id)[0] || ["", ""])[1]; }
function wbChip(word, cls){ return `<span class="wbchip${cls ? " " + cls : ""}">${wbEsc(word)}</span>`; }
function wbStepHtml(s, need){
  const last = s.last || {};
  const dot = !s.ran ? "off" : (last.ok === false || last.status === "failed" ? "block" : (last.miss ? "warn" : "ok"));
  const note = (last.notes && last.notes[0]) || String(s.check || "").replace(/_/g, " ");
  const ev = s.evidence;
  const climbs = s.soft && s.rung !== s.ceiling && !s.held;
  const marks = wbRungHtml(s) + wbChip(s.rung_name, s.rung === "C2" ? "on" : "") +
    (s.mode === "gate" ? wbChip("Gate") : "") + (s.each && s.side_by_side > 1 ? wbChip("Side by side") : "") +
    (s.trial ? wbChip("On trial", "ask") : "") + (s.pending ? wbChip("Waits for your stamp", "ask") : "") +
    (s.held ? wbChip("Held", "on") : "") +
    `<button type="button" class="o2more wb" data-wbhold="${wbEsc(s.id)}" data-wbheld="${s.held ? "0" : "1"}">${s.held ? "Let go" : "Hold"}</button>`;
  const bars = ev ? `<div class="wbev"><span class="dpk">Passing</span>${dpBar(ev.pass === null || ev.pass === undefined ? 0 : ev.pass)}` +
    (climbs ? `<span class="dpk">To the next rung</span>${dpBar(Math.min(1, ev.runs / (need || 1)))}` : "") + `</div>` : "";
  return dpRunRow(s.name, note, dot, `<div class="wbstep">${marks}</div>` + bars);
}
function wbStepsHtml(ref, name){
  const st = wbS(), k = ref + ":" + name, v = st.steps[k];
  if (!v){ wbLoadSteps(ref, name); return dpSkel(); }
  if (v.failed) return dpQuiet("Could not read");
  const need = (v.numbers && v.numbers.runs) || 0;
  const steps = v.steps || [];
  const card = (title, rows) => rows.length ? dpCard(title, rows.map(s => wbStepHtml(s, need)).join("")) : "";
  const moves = [];
  steps.forEach(s => (s.history || []).forEach(h => { if (h.from) moves.push([s, h]); }));
  moves.sort((a, b) => String(b[1].at).localeCompare(String(a[1].at)));
  return (v.description ? dpCard(v.kind === "function" ? "The function" : "The engine",
        `<div class="dpbig">${wbEsc(v.description.charAt(0).toUpperCase() + v.description.slice(1))}</div>` +
        ((v.skills || []).length ? `<div class="wbstep">${v.skills.map(x => wbChip(x)).join("")}</div>` : "")) : "") +
    wbStartHtml(v) + wbTableHtml(v) +
    card("Gates", steps.filter(s => s.mode === "gate")) +
    card("Steps", steps.filter(s => s.mode !== "gate" && !s.under)) +
    (v.hears || []).map(h => card(h, steps.filter(s => s.under === h))).join("") +
    (moves.length ? dpCard("Moves", moves.slice(0, 12).map(([s, h]) => dpRunRow(s.name,
        wbRungName(h.from) + " to " + wbRungName(h.to) + " · " + String(h.by || "") + " · " + wbWhen(h.at),
        WB_RUNGS.map(r => r[0]).indexOf(h.to) > WB_RUNGS.map(r => r[0]).indexOf(h.from) ? "ok" : "warn")).join("")) : "");
}
function wbCap(x){ x = String(x || ""); return x.charAt(0).toUpperCase() + x.slice(1); }
/* How this engine starts: what makes it want to run, and what holds it. The
   same two lines on all nine cards, because all nine start by the same rule. */
function wbStartHtml(v){
  const s = v.start;
  if (!s || !(s.on || []).length) return "";
  const held = (s.unless || []).length ? s.unless.map(b => wbChip(b.by + ": " + b.name, "ask")).join("") : wbChip("Nothing holds it");
  return dpCard("Starts", `<div class="wbstep"><span class="dpk">On</span>${s.on.map(x => wbChip(wbCap(x), "on")).join("")}</div>` +
    `<div class="wbstep"><span class="dpk">Unless</span>${held}</div>`);
}
/* What engines share is Coordination's, and it is a record: who goes first
   when several are ready, and who may post what to whom. */
function wbTableHtml(v){
  const t = v.table;
  if (!t) return "";
  const arrow = `<span class="wbarrow">&rarr;</span>`;
  return dpCard("Who goes first", (t.first || []).map(x => dpRunRow(x, "", "")).join("") +
      `<div class="wbstep"><span class="dpk">The line</span>${(t.line || []).map(x => wbChip(x)).join(arrow)}</div>`) +
    dpCard("Who may post to whom", (t.may_post || []).map(r => `<div class="wbpost">${wbChip(r.from)}` +
      `<span class="dpchk">${wbEsc(WB_ACTS[r.act] || r.act)}</span>${(r.to || []).map(x => wbChip(x)).join("")}</div>`).join(""));
}
function wbIdeasHtml(b){
  const rows = (b && b.ideas) || [];
  if (!rows.length) return "";
  return dpCard("Ideas, parked", rows.map(i => dpRunRow(i.reflected || i.words || "", i.question || "", "off",
    `<div class="wbstep">${(i.shapes || []).map(x => wbChip(x)).join("")}</div>`)).join(""));
}
/* The Board as chats (founder, 2026-09-28: "even the board should also be like
   a chat interface"): every thread a row down the side, newest first, and the
   open one as turns in the Sutra chat's own markup, the owner on the right and
   whoever spoke on the left, with the act in a word. */
function wbBoardTurn(p){
  const to = p.dst || [];                       /* the Board is the whole record: the owner is named as a reader too */
  const said = p.line ? wbEsc(p.line) : wbEsc(wbCap(p.word || ""));
  const act = `<span class="dpchk">${wbEsc(WB_ACTS[p.msg_type] || p.msg_type)} · ${wbEsc(wbWhen(p.at))}</span>`;
  if (p.src === "Owner") return `<div class="turn wbturn"><div class="who who-you">You</div><div class="u md">${said}${act}</div></div>`;
  const who = wbEsc(p.src) + (to.length ? ` <span class="wbarrow">&rarr;</span> ` + wbEsc(to.join(", ")) : "");
  return `<div class="turn wbturn"><div class="who who-ai">${who}</div><div class="a">${said}${act}</div></div>`;
}
function wbBoardHtml(n){
  const st = wbS(), b = st.board[n.ref];
  if (!b){ wbLoadBoard(n.ref); return dpSkel(); }
  if (b.failed) return dpQuiet("Could not read");
  if (!b.any) return dpQuiet("Nothing has been said yet");
  const threads = b.threads || [];
  const cur = threads.some(t => t.id === st.thread[n.ref]) ? st.thread[n.ref] : (threads[0] || {}).id;
  const rows = threads.map(t => {
    const [dot, word] = WB_THREADS[t.state] || ["", t.state];
    const posts = t.posts || [], who = [];
    posts.forEach(p => { if (who.indexOf(p.src) < 0) who.push(p.src); });
    return `<button type="button" class="wbthr wb${t.id === cur ? " on" : ""}" data-wbthread="${wbEsc(t.id)}">${wbDot(dot)}` +
      `<span class="wbwho">${who.map(w => wbChip(w)).join("")}</span><span class="dpst">${wbEsc(word)}</span>` +
      `<b>${wbEsc((posts[0] && posts[0].line) || t.topic || "")}</b></button>`;
  }).join("");
  const open = threads.filter(t => t.id === cur)[0];
  const turns = open ? (open.posts || []).slice().sort((a, c) => a.n - c.n).map(wbBoardTurn).join("") : "";
  return wbIdeasHtml(b) + `<div class="wbboard wb"><div class="wbthreads">${rows}</div><div class="wbthread"><div class="wbchat wb">${turns}</div></div></div>`;
}

/* ── the conversation: Human Sutra, an app ────────────────────────────────── */
/* Founder, 2026-09-28: "a much more conversational style... Assume Slack,
   where everybody is talking about certain things, and whatever has been
   decided, then they come as whatever things we need to do." One stream in
   time order, newest at the bottom: the owner's words, what the department
   said back, the functions' own exchanges folded under the line that started
   them, the asks inline with their buttons, and the box to say more. It reads
   the board, the asks and the replies and writes nothing of its own: a word
   goes in by the one way in. It is an app in the department's list, not part
   of the core (PRD section J); the Board stays as the record, one block a
   thread. */
function wbLineHtml(p){
  const to = (p.dst || []).filter(d => d !== "Owner");
  const mine = p.src === "Owner";
  return `<div class="wbline wb${mine ? " me" : ""}">${wbChip(p.src, mine ? "on" : "")}` +
    (to.length ? `<span class="wbarrow">&rarr;</span>${wbChip(to.join(", "))}` : "") +
    `<span class="dpchk">${wbEsc(WB_ACTS[p.msg_type] || p.msg_type)}${p.line ? "" : " · " + wbEsc(wbCap(p.word || ""))} · ${wbEsc(wbWhen(p.at))}</span>` +
    (p.line ? `<div class="wbsaid">${wbEsc(p.line)}</div>` : "") + `</div>`;
}
function wbConversationHtml(n, m){
  const b = wbS().board[n.ref];
  if (!b){ wbLoadBoard(n.ref); return dpSkel(); }
  if (b.failed) return dpQuiet("Could not read");
  const items = [];
  (b.threads || []).forEach(t => {
    const posts = (t.posts || []).slice().sort((a, c) => a.n - c.n);
    const own = posts.filter(p => p.src === "Owner" || (p.dst || []).indexOf("Owner") >= 0);
    const theirs = posts.filter(p => own.indexOf(p) < 0);
    own.forEach(p => items.push({ n: p.n, html: wbLineHtml(p) }));
    if (theirs.length){
      const who = [];
      theirs.forEach(p => { if (who.indexOf(p.src) < 0) who.push(p.src); });
      const [dot, word] = WB_THREADS[t.state] || ["", t.state];
      items.push({ n: theirs[0].n, html: `<details class="wbfold wb"><summary>${wbDot(dot)}${who.map(w => wbChip(w)).join("")}` +
        `<span class="dpchk">${wbEsc(theirs[0].line || t.topic || "")}</span><span class="dpst">${wbEsc(word)}</span></summary>` +
        theirs.map(wbLineHtml).join("") + `</details>` });
    }
  });
  items.sort((a, c) => a.n - c.n);
  const asks = (m.status && m.status.asks) || [];
  return `<div class="wbconv wb">` + (items.length ? items.map(i => i.html).join("") : dpQuiet("Nothing has been said yet")) + `</div>` +
    (asks.length ? dpCard("Waiting for you", wbAsksHtml(m)) : "") +
    dpCard("Say", wbAskBox(n.ref, "ask", "A task, a question, a rule, feedback or an idea", "data-wbask", "Send"));
}
/* ── the chat: the one point of entry ─────────────────────────────────────── */
/* Founder, 2026-09-28: "I want one point of entry, and that can be chat...
   The user always speaks with the root, but the user can just open up at a
   particular department and wants to speak there... It goes to the root, and
   then it translates into that department appropriately." One record: Root's
   board, every turn about a department. Two views: on Root the whole chat;
   inside a department the same chat scoped to it, and the box carries where
   you stand as a chip the person can take off. The left name is always Root;
   the department is a chip on the turn. The markup is the Sutra chat's own
   (05-chat.js: turn, who, u, a), so it reads as a chat. */
/* The department a turn is about is a chip that opens it (found live 2026-09-28: the person clicked the chip first). */
function wbDeptChip(ref, name){
  return `<button type="button" class="wbchip wbto wb" data-wbopen="${wbEsc(ref)}">${wbEsc(name)}</button>`;
}
function wbChatTurn(t, scoped){
  const dept = !scoped && t.name ? (t.dept ? wbDeptChip(t.dept, t.name) : wbChip(t.name)) : "";
  /* a stamp or a refusal carries no words of its own: the act is the line */
  const line = t.line || (t.msg_type === "accept-proposal" ? "Stamped" : t.msg_type === "reject-proposal" ? "Refused" : wbCap(t.word || ""));
  if (t.src === "Owner") return `<div class="turn wbturn"><div class="who who-you">${dept}You</div><div class="u md">${wbEsc(line)}</div></div>`;
  /* a turn that carries a way to the thing (the site that went live) shows it as the one button a person clicks
     (found live 2026-09-28: after the publish stamp the chat said nothing, and the person did not know it was live) */
  const link = t.link ? ` <button type="button" class="wbchip on wbto wb" data-wblive="${wbEsc(t.dept || "")}">Open the live site</button>` : "";
  return `<div class="turn wbturn"><div class="who who-ai">Root${dept}</div><div class="a">${wbEsc(line)}${link}` +
    `<span class="dpchk">${wbEsc(WB_ACTS[t.msg_type] || t.msg_type)} · ${wbEsc(wbWhen(t.at))}</span></div></div>`;
}
/* An ask is a line with its buttons, and it says where it lives: the stamp goes
   to that department, never to the one the chat is read from. */
function wbChatAsksHtml(c){
  const asks = c.asks || [];
  if (!asks.length) return "";
  return dpCard("Waiting for you", asks.map(a => `<div class="dpask wb"><div class="dpasks">${wbEsc(a.text)}</div>` +
    `<div class="dpaskd">${wbEsc([a.dept, a.engine].filter(Boolean).join(" · "))} · ${wbEsc(wbWhen(a.created))}</div>` +
    wbBtn("Stamp", `data-wbdecide="${wbEsc(a.id)}" data-wbok="1" data-wbref="${wbEsc(a.ref || "")}"`, "dpstamp") +
    wbBtn("Refuse", `data-wbdecide="${wbEsc(a.id)}" data-wbok="0" data-wbref="${wbEsc(a.ref || "")}"`) + `</div>`).join(""));
}
function wbChatBoxHtml(n, m){
  const st = wbS(), k = n.ref + ":ask";
  const inside = m.kind !== "root" && !!m.root, on = inside && st.chip[n.ref] !== false;
  const chip = !inside ? "" : on
    ? `<button type="button" class="wbchip on wbto wb" data-wbchip="off">to ${wbEsc(m.name)} &times;</button>`
    : `<button type="button" class="wbchip wbto wb" data-wbchip="on">to Root</button>`;
  const err = st.err[k] ? `<div class="o2quiet dpq">${wbEsc(st.err[k])}</div>` : "";
  /* Root's box: once departments exist, words for one of them are the usual thing to say (found live 2026-09-28:
     "Ask Root for a department" invited a new one when the person meant the one they had) */
  const depts = ((st.chat[n.ref] || {}).departments || []);
  const rootSay = m.kind === "root" && depts.length ? "Say it to Root, or name a department: " + depts.map(d => d.name).join(", ") : (m.say || "Say it to Root");
  return `<div class="wbbox wb">${chip}<textarea id="wbd-ask" data-wbdraft="${wbEsc(k)}" rows="2" placeholder="${wbEsc(on ? "Say it to " + m.name : rootSay)}">${wbEsc(st.draft[k] || "")}</textarea>` +
    wbBtn("Send", `data-wbask="ask"`, "dpstamp") + err + `</div>`;
}
/* The panel is painted whole, so a paint drops the chat to its top (found live 2026-09-28: after Send the person's
   words and the answer sat out of view). After each paint the chat goes back where it was; when a turn has landed it
   moves to that turn. The box that scrolls is found from the chat itself, so no other screen is touched. */
function wbKeepPlace(ref, landed){
  if (typeof document === "undefined" || !document.querySelector || typeof setTimeout !== "function") return;
  const st = wbS();
  setTimeout(() => {
    try {
      const chat = document.querySelector(".wbchat");
      if (!chat) return;
      let box = chat.parentElement;
      while (box && !(box.scrollHeight > box.clientHeight + 4)) box = box.parentElement;
      if (landed){
        const last = chat.querySelector(".wbturn:last-of-type");
        if (last && last.scrollIntoView) last.scrollIntoView({ block: "nearest" });
        else if (box) box.scrollTop = box.scrollHeight;
        if (box) st.scroll[ref] = box.scrollTop;
      } else if (box && st.scroll[ref] !== undefined) box.scrollTop = st.scroll[ref];
      if (box && !box.__wbKeep){
        box.__wbKeep = true;
        box.addEventListener("scroll", () => { const r = S.dp && S.dp.sel; if (r) st.scroll[r] = box.scrollTop; }, { passive: true });
      }
    } catch (e) {}
  }, 0);
}
function wbChatHtml(n, m){
  const st = wbS(), c = st.chat[n.ref];
  if (!c){ wbLoadChat(n.ref); return dpSkel(); }
  if (c.failed) return dpQuiet("Could not read");
  const scoped = !!c.about, depts = c.departments || [];
  const all = c.turns || [];
  /* fewer words (SIM-3 f): Root's hand-over line folds to one quiet line once that department has answered */
  const folded = t => !scoped && t.src !== "Owner" && /^handed to /.test(t.line || "") && t.dept &&
    all.some(u => u.n > t.n && u.dept === t.dept && u.src !== "Owner" && !/^handed to /.test(u.line || ""));
  const count = all.length, seen = st.turns[n.ref];
  const landed = seen !== undefined && count > seen;
  /* motion marks what just happened and nothing else: the turn that landed slides in once */
  const turns = all.map((t, i) => folded(t) ? `<div class="o2quiet dpq wbfold">${wbEsc(t.line)}</div>`
    : wbChatTurn(t, scoped).replace('class="turn wbturn"', (landed && i === all.length - 1) ? 'class="turn wbturn wbnew"' : 'class="turn wbturn"')).join("");
  const empty = m.kind === "root" && !depts.length ? "No department yet. Say what the first one is for." : "Nothing has been said yet";
  const names = !scoped && depts.length ? `<div class="wbstep"><span class="dpk">Departments</span>${depts.map(d => wbDeptChip(d.ref, d.name)).join("")}</div>` : "";
  /* while an engine runs, the chat says so under the last turn, and the mark breathes (founder, 2026-09-28: "I give a
     message to the chat, and it seems something is happening, but I don't know"); a department that is Off works on nothing */
  const running = m.stopped ? [] : ((m.status && m.status.running) || []);
  const working = running.map(r => `<div class="o2quiet dpq wbworking"><i class="wbbreath"></i>${wbEsc(`${r.engine} is working${r.what ? ": " + r.what : ""}`)}</div>`).join("");
  st.turns[n.ref] = count;
  wbKeepPlace(n.ref, landed);
  return `<div class="wbchat wb">${turns || (running.length ? "" : dpQuiet(empty))}${working}</div>` + wbChatAsksHtml(c) + wbChatBoxHtml(n, m) + names;
}

/* ── a function's chat ────────────────────────────────────────────────────
   Founder, 2026-09-29: a click on a function's Chat "should not start a new
   chat. It should just show the existing chat there." On the engine runtime a
   function is an engine on the board, so its chat is read from the record and
   exists from birth: what it said and was told, the person's words to it, its
   thinking as quiet lines (SIM-3 c). 20-dept.js's dpLiveChatHtml asks here
   first; null keeps the first build's chat for a department not on the runtime. */
async function wbLoadFnChat(ref, fn, again){
  const st = wbS(), k = ref + ":" + fn;
  if ((st.fnchat[k] && !again) || st.busy["f:" + k]) return;
  st.busy["f:" + k] = true;
  try {
    const v = await apiGet(wbUrl(ref, "chat?fn=" + encodeURIComponent(fn)));
    const sig = JSON.stringify(v), moved = sig !== st.fnchatSig[k] || !st.fnchat[k];
    st.fnchat[k] = v; st.fnchatSig[k] = sig;
    delete st.busy["f:" + k];
    if (moved && (!again || !wbTyping())) dpRender();
  } catch (e) {
    if (!st.fnchat[k]) st.fnchat[k] = { failed: true };
    delete st.busy["f:" + k];
    if (!again) dpRender();
  }
}
function wbFnTurn(t){
  if (t.think) return `<div class="o2quiet dpq wbthink">${wbEsc(t.line)} · ${wbEsc(wbWhen(t.at))}</div>`;
  const line = t.line || (t.msg_type === "accept-proposal" ? "Stamped" : t.msg_type === "reject-proposal" ? "Refused" : wbCap(t.word || ""));
  if (t.src === "Owner") return `<div class="turn wbturn"><div class="who who-you">You</div><div class="u md">${wbEsc(line)}</div></div>`;
  return `<div class="turn wbturn"><div class="who who-ai">${wbEsc(t.src)}</div><div class="a">${wbEsc(line)}` +
    `<span class="dpchk">${wbEsc(WB_ACTS[t.msg_type] || t.msg_type)} · ${wbEsc(wbWhen(t.at))}</span></div></div>`;
}
function wbFnChatHtml(ref, fn, label){
  if (!wbIs(ref)) return null;
  const st = wbS(), m = st.map[ref];
  if (!m){ wbLoadMap(ref); return dpSkel(); }
  if (!wbRt(m)) return null;
  const k = ref + ":" + fn, c = st.fnchat[k];
  if (!c){ wbLoadFnChat(ref, fn); return dpSkel(); }
  if (c.failed) return dpQuiet("Could not read");
  const name = c.fn || label || wbCap(fn), dk = ref + ":fn:" + fn;
  const turns = (c.turns || []).map(t => wbFnTurn(t)).join("");
  const err = st.err[dk] ? `<div class="o2quiet dpq">${wbEsc(st.err[dk])}</div>` : "";
  return `<div class="wbchat wbfn wb">${turns || dpQuiet("Nothing yet between you and " + name)}</div>` +
    `<div class="wbbox wb"><textarea data-wbdraft="${wbEsc(dk)}" rows="2" placeholder="${wbEsc("Say it to " + name)}">${wbEsc(st.draft[dk] || "")}</textarea>` +
    wbBtn("Send", `data-wbask="fn:${wbEsc(fn)}"`, "dpstamp") + err + `</div>`;
}

/* Priority's card: the limits, born from Priority's template, set here by the
   owner (founder, 2026-09-28: "configured in the relevant priority"). */
function wbLimitRow(ref, l){
  const st = wbS(), kc = ref + ":env:" + l.engine + ":calls", ku = ref + ":env:" + l.engine + ":usd";
  const val = (k, d) => wbEsc(st.draft[k] !== undefined ? st.draft[k] : d);
  return `<div class="wbstep wblim"><b>${wbEsc(l.engine)}</b>` +
    `<input type="number" min="0" step="1" data-wbdraft="${wbEsc(kc)}" value="${val(kc, l.calls)}" aria-label="calls a day"><span class="dpchk">calls</span>` +
    `<input type="number" min="0" step="0.5" data-wbdraft="${wbEsc(ku)}" value="${val(ku, l.usd)}" aria-label="USD a day"><span class="dpchk">USD a day</span>` +
    wbBtn("Set", `data-wbenv="${wbEsc(l.engine)}"`) + `</div>`;
}
function wbLimitsHtml(ref){
  const v = wbS().steps[ref + ":Priority"];
  const rows = (v && v.limits) || [];
  if (!rows.length) return "";
  return dpCard("Limits", rows.map(l => wbLimitRow(ref, l)).join(""));
}

/* ── filed work: the item, Preview, Versions, Trace ───────────────────────── */
async function wbLoadArt(ref, slug){
  const st = wbS(), k = ref + ":" + slug;
  if (st.art[k] || st.busy["a:" + k]) return;
  st.busy["a:" + k] = true;
  try { st.art[k] = await apiGet(wbUrl(ref, "artifact/" + encodeURIComponent(slug))); } catch (e) { st.err["a:" + k] = String(e); }
  delete st.busy["a:" + k];
  dpRender();
}
async function wbLoadTrace(ref, slug, v){
  const st = wbS(), k = ref + ":" + slug + ":" + v;
  if (st.trace[k] || st.busy["t:" + k]) return;
  st.busy["t:" + k] = true;
  try { st.trace[k] = await apiGet(wbUrl(ref, "trace/" + encodeURIComponent(slug) + "/" + v)); } catch (e) { st.err["t:" + k] = String(e); }
  delete st.busy["t:" + k];
  dpRender();
}
function wbFromHtml(v){
  return (v.made_from || []).map(f => f.art ? `<span class="wbchip">${wbEsc(f.art)} ${dpVerDots(f.v) || ""}</span>`
    : (f.ask ? `<span class="wbchip ask">${wbEsc(f.ask)}</span>` : "")).join("");
}
function wbArtHtml(n){
  const st = wbS(), slug = st.sel[n.ref], k = n.ref + ":" + slug;
  const a = st.art[k];
  if (!a){ wbLoadArt(n.ref, slug); return dpSkel(); }
  const vs = a.versions || [];
  if (!vs.length) return dpQuiet("Nothing filed yet");
  const pane = st.pane[k] || "preview";
  const tabs = dpTabsHtml(pane, WB_PANES, `data-wbpanekey="${wbEsc(k)}" data-wbpane`);
  const cur = vs.filter(v => String(v.v) === String(st.sel[k + ":v"]))[0] || vs[0];
  const chk = v => (v.check && v.check.ok) ? "ok" : "block";
  if (pane === "item"){
    /* the artifact's template from the Library: what it holds, its checks, who writes it, what runs on a new version */
    const t = a.template;
    const tpl = t ? dpCard("Template", `<div class="dpengines">` + dpKV("Holds", (t.files || []).join(", "), "A screen") +
      dpKV("Checks", (t.checks || []).join(", "), "None") + dpKV("Written by", (t.written_by || []).join(", "), "Nobody") +
      dpKV("Counts", t.counts_after === "stamp" ? "After your stamp" : "When filed", "") +
      dpKV("Runs on a new one", (t.operations || []).join(", "), "Nothing") + `</div>`) : "";
    return tabs + dpCard("The work item", `<div class="dpengines">` +
      dpKV("Made by", cur.run === "owner" ? "The owner" : (wbMakerOf(a.name)), "Not named") +
      dpKV("Read by", wbReaderOf(a.name), "Nobody yet") +
      dpCell("Check", `<div class="dpbig">${wbDot(chk(cur))} ${cur.check && cur.check.ok ? "Passed" : "Failed"}</div>`) + `</div>` +
      ((cur.check && cur.check.notes) || []).map(x => dpRunRow(x, "", chk(cur))).join("")) + tpl;
  }
  if (pane === "versions"){
    return tabs + dpCard("Versions", vs.map((v, i) => `<div class="wbver${i === 0 ? " on" : ""}">` +
      `<div class="wbverh">${wbDot(chk(v))}<span class="dpbig">${wbEsc(wbWhen(v.at))}</span>${dpVerDots(v.v) || ""}` +
      `<span class="dpchk">${wbEsc(v.note || ((v.check && v.check.notes) || [])[0] || "")}</span></div>` +
      `<div class="wbverf"><span class="dpk">From</span>${wbFromHtml(v)}` +
      `<button type="button" class="o2more wb" data-wbart="${wbEsc(slug)}" data-wbpane="preview" data-wbv="${v.v}">Preview</button>` +
      `<button type="button" class="o2more wb" data-wbart="${wbEsc(slug)}" data-wbpane="trace" data-wbv="${v.v}">Trace</button>` +
      (i > 0 && a.name !== "Brief" ? wbBtn("Put back", `data-wbputback="${wbEsc(slug)}" data-wbv="${v.v}"`) : "") + `</div></div>`).join(""));
  }
  if (pane === "trace"){
    const tk = n.ref + ":" + slug + ":" + cur.v, t = st.trace[tk];
    if (!t){ wbLoadTrace(n.ref, slug, cur.v); return tabs + dpSkel(); }
    return tabs + dpCard("Trace", `<div class="wbtrace">` + (t.chain || []).map(c => {
      if (c.kind === "version") return `<div class="wbtv">${wbDot(c.check && c.check.ok ? "ok" : "block")}<b>${wbEsc(c.art)}</b>${dpVerDots(c.v) || ""}<span class="dpchk">${wbEsc(wbWhen(c.at))}</span></div>`;
      if (c.kind === "run") return `<div class="wbtr"><span class="wbchip">${wbEsc(c.engine)}</span><span class="dpchk">${wbEsc(wbWhen(c.at))}</span></div>`;
      return `<div class="wbtr"><span class="wbchip ask">${wbEsc(c.text)}</span></div>`;
    }).join(`<div class="wbtl1"></div>`) + `</div>`);
  }
  const live = a.name === "Live site" && cur === vs[0];
  const src = live ? wbUrl(n.ref, "site/index.html") : wbUrl(n.ref, "preview/" + encodeURIComponent(slug) + "/" + cur.v + "/index.html");
  return tabs + `<div class="wbprev wb"><div class="wbprevh">${wbDot(chk(cur))}<span>${live ? "Live" : wbEsc(wbWhen(cur.at))}</span>` +
    `<a class="o2more" href="${wbEsc(src)}" target="_blank" rel="noopener">Open</a></div>` +
    `<iframe class="wbframe" sandbox="" src="${wbEsc(src)}" title="${wbEsc(a.name)}"></iframe></div>`;
}
function wbMakerOf(name){ return ({ "Site plan": "Plan", "Pages": "Write", "Build": "Check", "Live site": "Publish" })[name] || ""; }
function wbReaderOf(name){ return ({ "Brief": "Plan", "Site plan": "Write", "Pages": "Check", "Build": "Publish" })[name] || ""; }

/* ── the five systems' own state, under the function cards ────────────────── */
function wbFnExtra(tab, m){
  if (!m) return "";
  const engs = m.engines || [];
  /* on the engine runtime a function is an engine too: its own steps, each on
     its rung, under the state the card already shows */
  const steps = wbRt(m) ? wbStepsHtml(m.ref, tab.charAt(0).toUpperCase() + tab.slice(1)) : "";
  if (tab === "identity"){
    return dpCard("Control", `<div class="dpengines">` + dpKV("Control", m.control === "granted" ? "Granted" : "Held", "") +
        dpKV("Owner", m.owner, "Not named") + dpKV("Stop", m.stopped ? "Stopped" : "Running", "") + `</div>`) +
      dpCard("Autonomy windows", engs.map(e => dpRunRow(e.name, "", "", dpBar(Math.min(1, (e.window_min || 0) / 30)))).join("")) +
      dpCard("Stamped by rule", (m.recent || []).filter(r => r.engine === "Identity").map(r => wbRunRow(r)).join("") || dpQuiet("Nothing yet")) +
      steps;
  }
  if (tab === "priority"){
    return dpCard("Envelopes", engs.map(e => dpRunRow(e.name, "", "", dpBar(Math.min(1, ((e.envelope || {}).used_calls || 0) / ((e.envelope || {}).calls || 1))))).join("")) +
      (wbRt(m) ? wbLimitsHtml(m.ref) : "") +
      dpCard("Queue", engs.map(e => dpRunRow(e.name, e.state === "Running" ? "Running" : (e.state === "Waits" ? "Waits for the stamp" : e.slot), wbEngDot(e))).join("")) +
      steps;
  }
  if (tab === "coordination"){
    return dpCard("Timetable", engs.map(e => dpRunRow(e.name, e.slot, "")).join("")) +
      dpCard("Hand-offs", engs.map(e => dpRunRow(e.reads + " → " + e.name, "", "ok")).join("")) +
      dpCard("Locks", (m.status && m.status.running && m.status.running.length)
        ? m.status.running.map(r => dpRunRow(r.engine, "Holds the line", "warn")).join("") : dpQuiet("Nothing is held")) +
      steps;
  }
  if (wbRt(m)){
    const b = wbS().board[m.ref];
    if (!b) wbLoadBoard(m.ref);
    return (tab === "adaptation" ? wbIdeasHtml(b) : "") + steps;
  }
  return dpCard("State", dpRunRow("Paused", "Growth is paused in this build", "off"));
}
/* 20-dept.js's dpOwnState() asks this for every function card it draws. */
function wbFnOwn(ref, tab){
  if (!wbIs(ref)) return "";
  const m = wbS().map[ref];
  if (!m){ wbLoadMap(ref); return ""; }
  return wbFnExtra(tab, m);
}

/* ── Settings: a function's own ────────────────────────────────────────────
   Founder, 2026-09-28: "Each of the five functions has a default settings tab
   which has its own updates", and "One identity is being used for everything":
   never one template for all five. 20-dept.js draws the tab on each function
   card and asks wbFnSettings for its body: the function's own template (the
   line and its picker are 20-dept.js's), its own limit, the numbers of its
   ladder, how it starts and what it hears; Identity's carries where the site
   is served from, Coordination's its table. */
const WB_LADDER = [["runs", "Runs before a step climbs"], ["differing", "Differing runs it may keep"],
                   ["trial", "Runs a trial lasts"], ["misses", "Misses that step it down"]];
function wbLadderHtml(ref, name, n){
  const st = wbS();
  return dpCard("Ladder", WB_LADDER.map(([k, label]) => {
      const key = ref + ":ladder:" + name + ":" + k;
      return `<div class="wbstep wbset"><span class="dpk">${wbEsc(label)}</span>` +
        `<input type="number" min="0" step="1" data-wbdraft="${wbEsc(key)}" value="${wbEsc(st.draft[key] !== undefined ? st.draft[key] : (n[k] === undefined ? "" : n[k]))}" aria-label="${wbEsc(label)}"></div>`;
    }).join("") + `<div class="wbctl">${wbBtn("Set", `data-wbladder="${wbEsc(name)}"`)}</div>`);
}
function wbHostHtml(ref, m){
  const st = wbS(), key = ref + ":host";
  return dpCard("Served from", `<div class="wbstep wbset"><input type="text" data-wbdraft="${wbEsc(key)}" value="${wbEsc(st.draft[key] !== undefined ? st.draft[key] : (m.host || ""))}"` +
    ` aria-label="where the site is served from" placeholder="Where the site is served from">` + wbBtn("Set", `data-wbhost="1"`) + `</div>`);
}
function wbSettingsHtml(ref, fn){
  const st = wbS(), m = st.map[ref], name = wbCap(fn), v = st.steps[ref + ":" + name];
  if (!v){ wbLoadSteps(ref, name); return dpSkel(); }
  if (v.failed) return dpQuiet("Could not read");
  const pr = st.steps[ref + ":Priority"];
  if (!pr) wbLoadSteps(ref, "Priority");
  const lim = ((pr && pr.limits) || []).filter(l => l.engine === name)[0];
  const tpl = (typeof dpTemplateLine === "function") ? dpTemplateLine(fn) : "";
  return dpCard("Template", tpl || dpQuiet("Not read yet")) +
    (lim ? dpCard("Limit", wbLimitRow(ref, lim)) : "") +
    wbLadderHtml(ref, name, v.numbers || {}) +
    (fn === "identity" ? wbHostHtml(ref, m) : "") +
    wbStartHtml(v) +
    ((v.hears || []).length ? dpCard("Hears", `<div class="wbstep">${v.hears.map(h => wbChip(h)).join("")}</div>`) : "") +
    wbTableHtml(v);
}
/* 20-dept.js asks this for every function card: null for a department that is
   not on the engine runtime, so its card keeps the tabs it had. */
function wbFnSettings(ref, fn){
  if (!wbIs(ref)) return null;
  const m = wbS().map[ref];
  if (!m){ wbLoadMap(ref); return null; }
  return wbRt(m) ? wbSettingsHtml(ref, fn) : null;
}
function wbCanDoHtml(m){
  const owner = true;
  const pill = (name, on) => `<span class="wbchip${on ? " on" : ""}">${name}</span>`;
  return dpCard("Can do", `<div class="wbcando">` + pill("See", true) + pill("Stamp", owner) + pill("Ask", owner) + pill("Stop", owner) + `</div>`);
}

/* ── the viewer ───────────────────────────────────────────────────────────── */
function wbViewer(n){
  if (!wbIs(n.ref)) return null;
  const st = wbS(), m = st.map[n.ref], tab = wbTab(n.ref);
  wbTick();
  if (!m){ wbLoadMap(n.ref); return dpViewerShell(n.name, st.err[n.ref] ? dpQuiet("Could not read") : dpSkel(), "wb"); }
  /* the Map and the Board of the second design, when the switch is on; null hands the rest back to this file */
  if (wbV2() && wbRt(m) && typeof wb2Viewer === "function"){ const own = wb2Viewer(n); if (own) return own; }
  if (tab === "chat" && wbRt(m)) return dpViewerShell("Chat", wbChatHtml(n, m), "wb");
  if (tab === "map") return dpViewerShell("Map", wbMapHtml(n, m), "wb");
  if (tab === "status") return dpViewerShell("System status", wbStatusHtml(n, m), "wb");
  if (tab === "motor") return dpViewerShell("Motor", wbMotorHtml(n, m), "wb");
  if (tab === "board" && wbRt(m)) return dpViewerShell("Board", wbBoardHtml(n), "wb");
  if (tab === "conversation" && wbRt(m)) return dpViewerShell("Human Sutra", wbConversationHtml(n, m), "wb");
  if (tab === "engine") return dpViewerShell(st.sel[n.ref] || "Engine", wbEngineHtml(n), "wb");
  if (tab === "art"){
    const a = (m.artifacts || []).filter(x => x.slug === st.sel[n.ref])[0];
    return dpViewerShell(a ? a.name : "Filed work", wbArtHtml(n), "wb");
  }
  /* one of 20-dept.js's own cards is open: it draws it, and asks wbFnOwn for this
     department's state; only People gains a section here */
  const dtab = dpS().tab[n.ref] || "now";
  if (dtab === "now"){
    st.tab[n.ref] = wbRt(m) ? "chat" : "map";
    return wbRt(m) ? dpViewerShell("Chat", wbChatHtml(n, m), "wb") : dpViewerShell("Map", wbMapHtml(n, m), "wb");
  }
  if (dtab === "people"){
    dpLoadPeople(n.ref);
    const p = dpPerson();
    return dpViewerShell(p ? p.name : "People", dpPeopleCard() + wbCanDoHtml(m), "wb");
  }
  return null;
}

/* ── the organisation's chart: a website department's tile is live ────────── */
function wbTileMark(ref){
  if (!wbIs(ref)) return "";
  const m = wbS().map[ref];
  if (!m){ wbLoadMap(ref); return ""; }
  const asks = ((m.status && m.status.asks) || []).length;
  /* a department at work carries a breathing mark on its row (SIM-3 a; the list says which are working) */
  const working = ((wbS().refs || {})[ref] || {}).working;
  const breath = (working && working.length) ? `<i class="wbbreath" title="${wbEsc(working.join(", ") + " working")}"></i>` : "";
  return `<span class="wbtm">` + breath + m.systems.map(s => wbDot(s.state === "running" ? "ok" : "off")).join("") +
    (asks ? wbDot("") : "") + `</span>`;
}

/* ── the command: found an organisation, with its one Root ───────────────────
   Founder, 2026-09-28: "root can always spawn off new departments. There will be
   one root for one organizational structure." So founding makes the
   organisation and its Root, On, and nothing else; words for the first
   department go to Root as its first request, and Root asks the owner. */
function wbMenuItem(){
  return `<button type="button" role="menuitem" data-wbfound="open">New organisation…</button>`;
}
function wbFoundHtml(){
  const f = wbS().found;
  if (!f) return "";
  return `<div class="wbscrim wb" data-wbfound="close"></div><div class="o2sheet wbsheet wb" role="dialog" aria-label="New organisation">` +
    `<h4>New organisation</h4>` +
    `<label for="wbforg">Organisation</label><input id="wbforg" data-wbfield="org" value="${wbEsc(f.org)}" placeholder="City Care Hospital" autocomplete="off">` +
    `<label for="wbfgoal">The first department</label><textarea id="wbfgoal" data-wbfield="goal" rows="3" placeholder="What should Root set up first? A website: what it is for">${wbEsc(f.goal)}</textarea>` +
    `<div class="o2acts2">${wbBtn(f.busy ? "Founding" : "Found", `data-wbfound="go"${f.busy ? " disabled" : ""}`, "dpstamp")}` +
    wbBtn("Cancel", `data-wbfound="close"`) + (f.error ? `<span class="o2err">${wbEsc(f.error)}</span>` : "") + `</div></div>`;
}
function wbFoundPaint(){
  let host = document.getElementById("wbfound");
  if (!host){ host = document.createElement("div"); host.id = "wbfound"; document.body.appendChild(host); }
  host.innerHTML = wbFoundHtml();
  const el = document.getElementById("wbforg");
  if (el && !wbS().found.org) el.focus();
}
async function wbFoundGo(){
  const st = wbS(), f = st.found;
  if (!f || f.busy) return;
  if (!f.org.trim()){ f.error = "Name the organisation"; wbFoundPaint(); return; }
  f.busy = true; f.error = null; wbFoundPaint();
  try {
    const body = { org: f.org.trim() };
    if (f.goal.trim()) body.first = f.goal.trim();
    const out = await apiPost("/api/native/found", body);
    st.found = null; st.refs = null; wbFoundPaint();
    await wbLoadRefs();
    if (typeof loadOrg2 === "function") await loadOrg2(true);
    if (typeof o2S === "function"){
      const o = o2S();
      if (o.expanded){ [out.org].forEach(r => o.expanded.add(r)); }
    }
    /* Root is where the person goes on: its chat, where its ask for the first department is */
    st.tab[out.root] = "chat";
    if (typeof o2Select === "function") o2Select(out.root);
    wbLoadMap(out.root, true);
  } catch (e) {
    f.busy = false; f.error = (e && e.message) || String(e); wbFoundPaint();
  }
}

/* ── handlers ─────────────────────────────────────────────────────────────── */
/* `at` is the department the route is posted to when it is not the one on the
   screen: Root for the words said inside a department, the department an ask
   lives in for its stamp. What is on the screen is read again either way. */
async function wbPost(ref, tail, body, key, at){
  const st = wbS();
  if (st.busy["p:" + tail]) return;
  st.busy["p:" + tail] = true;
  try { await apiPost(wbUrl(at || ref, tail), body || {}); if (key) { delete st.err[key]; delete st.draft[key]; } }
  catch (e) { if (key) st.err[key] = (e && e.message) || String(e); }
  delete st.busy["p:" + tail];
  await wbLoadMap(ref, true);
  dpRender();
}
if (typeof document !== "undefined" && document.addEventListener){
  const WB_SEL = "[data-wbtab],[data-wbengine],[data-wbart],[data-wbpane],[data-wbdecide],[data-wbstop],[data-wbresume]," +
    "[data-wbgoal],[data-wbask],[data-wbputback],[data-wbfn],[data-wbfound],[data-wbhold],[data-wbenv]," +
    "[data-wbchip],[data-wbthread],[data-wbladder],[data-wbhost],[data-wbopen],[data-wblive]";
  /* capture phase: a click on one of 20-dept.js's own rows hands the viewer
     back to it BEFORE that file's handler paints */
  document.addEventListener("click", (ev) => {
    if (S.screen !== "org2") return;
    const st = wbS();
    const own = ev.target && ev.target.closest ? ev.target.closest("[data-dptab],[data-dpengine],[data-dpfiled],[data-dpperson],[data-dpdoc],[data-dpapp]") : null;
    if (own && S.dp && S.dp.sel && wbIs(S.dp.sel)) st.tab[S.dp.sel] = "";
    const t = ev.target && ev.target.closest ? ev.target.closest(WB_SEL) : null;
    if (!t) return;
    const ds = t.dataset || {}, ref = S.dp && S.dp.sel;
    if (ds.wbfound !== undefined){
      ev.preventDefault(); ev.stopPropagation();
      if (ds.wbfound === "open"){
        st.found = { org: "", goal: "", busy: false, error: null };
        if (typeof o2S === "function"){ o2S().menu = false; if (typeof o2Render === "function") o2Render(); }
        wbFoundPaint();
      } else if (ds.wbfound === "close"){ st.found = null; wbFoundPaint(); }
      else if (ds.wbfound === "go") wbFoundGo();
      return;
    }
    if (!ref || !wbIs(ref)) return;
    ev.preventDefault(); ev.stopPropagation();
    /* Hold sits on a function card too, which 20-dept.js draws: the card stays open */
    if (ds.wbhold !== undefined){ wbPost(ref, "hold", { step: ds.wbhold, held: ds.wbheld === "1" }); return; }
    /* Set on Priority's card, which 20-dept.js draws: the owner's own limits for one engine */
    if (ds.wbenv !== undefined){
      const kc = ref + ":env:" + ds.wbenv + ":calls", ku = ref + ":env:" + ds.wbenv + ":usd", body = { engine: ds.wbenv };
      if (st.draft[kc] !== undefined && st.draft[kc] !== "") body.calls = Number(st.draft[kc]);
      if (st.draft[ku] !== undefined && st.draft[ku] !== "") body.usd = Number(st.draft[ku]);
      wbPost(ref, "envelope", body, kc).then(() => { delete st.draft[ku]; wbLoadSteps(ref, "Priority", true); });
      return;
    }
    /* Set on a function's Settings tab, which 20-dept.js draws: its own ladder numbers, or where the site is served from */
    if (ds.wbladder !== undefined){
      const body = { engine: ds.wbladder }, keys = WB_LADDER.map(([k]) => [k, ref + ":ladder:" + ds.wbladder + ":" + k]);
      keys.forEach(([k, key]) => { if (st.draft[key] !== undefined && st.draft[key] !== "") body[k] = Number(st.draft[key]); });
      wbPost(ref, "ladder", body).then(() => { keys.forEach(([, key]) => delete st.draft[key]); wbLoadSteps(ref, ds.wbladder, true); });
      return;
    }
    if (ds.wbhost !== undefined){ const k = ref + ":host"; wbPost(ref, "host", { host: st.draft[k] || "" }, k); return; }
    /* one of this file's entries is opening: none of 20-dept.js's rows stays lit */
    if (ds.wbfn === undefined && dpS().tab[ref] !== "now") dpS().tab[ref] = "now";
    if (ds.wbtab !== undefined){ st.tab[ref] = ds.wbtab; dpRender(); return; }
    if (ds.wbfn !== undefined){ st.tab[ref] = ""; dpS().tab[ref] = ds.wbfn; dpRender(); return; }
    if (ds.wbpane !== undefined && ds.wbpanekey !== undefined){ st.pane[ds.wbpanekey] = ds.wbpane; dpRender(); return; }
    if (ds.wbengine !== undefined){ st.tab[ref] = "engine"; st.sel[ref] = ds.wbengine; dpRender(); return; }
    if (ds.wbart !== undefined){
      st.tab[ref] = "art"; st.sel[ref] = ds.wbart;
      const k = ref + ":" + ds.wbart;
      if (ds.wbpane) st.pane[k] = ds.wbpane;
      st.sel[k + ":v"] = ds.wbv || "";
      dpRender(); return;
    }
    if (ds.wbchip !== undefined){ st.chip[ref] = ds.wbchip === "on"; dpRender(); return; }
    if (ds.wbopen !== undefined){ if (typeof o2Select === "function") o2Select(ds.wbopen); return; }
    /* the live site of the department a turn is about: its Live site, previewed; from Root's chat, that department opens on it */
    if (ds.wblive !== undefined){
      const dref = ds.wblive || ref;
      st.tab[dref] = "art"; st.sel[dref] = "live-site"; st.pane[dref + ":live-site"] = "preview"; st.sel[dref + ":live-site:v"] = "";
      if (dref !== ref && typeof o2Select === "function") o2Select(dref); else dpRender();
      return;
    }
    if (ds.wbthread !== undefined){ st.thread[ref] = ds.wbthread; dpRender(); return; }
    if (ds.wbdecide !== undefined){ wbPost(ref, "asks/" + encodeURIComponent(ds.wbdecide), { approve: ds.wbok === "1" }, null, ds.wbref || ref); return; }
    if (ds.wbstop !== undefined){ wbPost(ref, "stop"); return; }
    if (ds.wbresume !== undefined){ wbPost(ref, "resume"); return; }
    if (ds.wbgoal !== undefined){ const k = ref + ":goal"; wbPost(ref, "goal", { text: st.draft[k] || "" }, k); return; }
    if (ds.wbask !== undefined){
      if (String(ds.wbask).indexOf("fn:") === 0){
        /* said in one function's own chat: to this department, carrying the function (founder, 2026-09-29) */
        const fk = ref + ":" + ds.wbask;
        wbPost(ref, "ask", { text: st.draft[fk] || "", about: ds.wbask }, fk).then(() => wbAgain(ref)); return;
      }
      /* the words go to Root, the front door; said inside a department they carry it, unless the person took the chip off */
      const k = ref + ":ask", m = st.map[ref], body = { text: st.draft[k] || "" };
      let at = ref;
      if (wbRt(m) && m.root && m.root !== ref){ at = m.root; if (st.chip[ref] !== false) body.about = ref; }
      wbPost(ref, "ask", body, k, at); return;
    }
    if (ds.wbputback !== undefined){ wbPost(ref, "putback", { slug: ds.wbputback, v: Number(ds.wbv) }); return; }
  }, true);
  document.addEventListener("input", (ev) => {
    const t = ev.target, ds = (t && t.dataset) || {};
    if (ds.wbdraft !== undefined) wbS().draft[ds.wbdraft] = t.value;
    if (ds.wbfield !== undefined && wbS().found) wbS().found[ds.wbfield] = t.value;
  });
}
