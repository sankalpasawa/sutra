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
                     "completed": ["ok", "Done"], "failed": ["block", "Failed"], "canceled": ["off", "Let go"], "rejected": ["block", "Said no"] };
/* an act on the board in a word, in the owner's words: said yes and said no, never accept, refuse or reject (the
   owner's ruling); the board, the chat turns and Coordination's who-may-post table print these, and the server's
   engine_runtime.ACT_SAYS says the same words (Coordination's check writes its note in them) */
const WB_ACTS = { "request": "asks", "agree": "agrees", "refuse": "says no", "propose": "proposes", "accept-proposal": "says yes",
                  "reject-proposal": "says no", "inform": "tells", "failure": "could not", "not-understood": "did not follow", "cancel": "lets go" };
/* Priority's counter is a proposal on the board, and a function's chat says it as what it is (PRD M1.7) */
const WB_COUNTER = "asks for less";
/* the act of a post on the Board, in a word: a question between engines asks (the act is a request), and Coordination's answer to
   the asker answers (the act is an inform, which tells; PRD M4.9, with SUTRA_BOARD_QUESTIONS on). Identity's answer to the owner,
   which has the same word, is told */
function wbActWord(p){
  return p && p.msg_type === "inform" && p.word === "answer" && p.src === "Coordination" ? "answers" : (WB_ACTS[p && p.msg_type] || (p && p.msg_type));
}

function wbS(){
  if (!S.wb) S.wb = { refs: null, refsBusy: false, refsMissed: {}, map: {}, sig: {}, tab: {}, pane: {}, sel: {}, draft: {},
                      busy: {}, err: {}, engine: {}, art: {}, trace: {}, steps: {}, board: {}, chat: {}, chatSig: {},
                      fnchat: {}, fnchatSig: {}, chip: {}, thread: {}, turns: {}, scroll: {}, found: null, timer: null, born: {},
                      fv: {}, fvSig: {}, fnpage: {}, fnpageSig: {}, said: {} };
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
/* ── the organisation and its Root ────────────────────────────────────────
   Founder, 2026-09-29: "at the organization level, only a chat is shown, and
   root is not shown." Root stays a department of the registry under its
   organisation; the screen does not draw it. 19-org2.js asks wbHidden when it
   builds the tree and lifts Root's departments under the organisation; the
   organisation row is then Root's chat (wbOrgHtml). */
function wbHidden(ref){
  const st = wbS();
  if (st.refs === null){ wbLoadRefs(); return false; }
  const r = st.refs[ref];
  return !!(r && r.kind === "root");
}
function wbRootOf(orgRef){
  const d = (typeof o2Data === "function") ? o2Data() : null;
  const r = d && d.lifted && d.lifted.get(orgRef);
  return r ? r.ref : null;
}
/* a department Root just made slides into the tree once: marked when the chat learns of it, timed from its first paint */
function wbBorn(ref){
  const st = wbS(), t = st.born && st.born[ref];
  if (!t) return false;
  if (t === true){ st.born[ref] = Date.now(); return true; }
  return (Date.now() - t) < 1200;
}
/* A department on the engine runtime opens on its chat: the one point of entry
   (founder, 2026-09-28). One of the first build opens on its Map, as before. */
function wbTab(ref){
  /* 25-j2view.js: a website department on the engine runtime is the J2 page, which folds Chat, Map, All five, Board,
     Agent activity and System status into itself, and Settings and records is the `records` tab; null for the rest */
  if (typeof j2vTab === "function"){ const t = j2vTab(ref); if (t) return t; }
  const st = wbS();
  return st.tab[ref] === undefined ? (wbRt(st.map[ref]) ? "chat" : "map") : st.tab[ref];
}
/* What the screen compares to decide whether to paint again. The motor's
   heartbeat moves every tick and is patched in place, so it is left out: a
   preview frame must not reload because a clock moved. */
function wbSig(m){
  /* what Identity's pane draws from the record too (its goal, done-when, rules, owner and control), so a change repaints */
  return JSON.stringify([m.stopped, m.has_goal, m.status, m.recent, m.live, m.goal, m.done, m.rules, m.owner, m.control,
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
/* ── the five functions, as one read of the record (functions_view.py) ──────
   The Map, the list column's function rows, each function's pane and the All
   five overview read the five here and nowhere else, so they agree with each
   other and with the record (PRD M1.1). A department not on the engine
   runtime has no such read: it is never asked. A read that failed keeps
   what was on the screen, or says so once. */
function wbFv(ref){
  const st = wbS(), m = st.map[ref];
  if (!ref || !wbRt(m)) return null;
  if (!st.fv[ref]) wbLoadFv(ref);
  return st.fv[ref] || null;
}
/* What the screen compares before it paints the five again (PRD M1.9), after dpActivitySig (20-dept.js): everything a
   surface shows of the read, as it shows it. Per function its state, what it waits on, its line, its spend as the bar
   draws it, and its last act with its detail and its clock to the minute (All five prints 'last: ... · 10:21'); the
   cycle's own words and step; who made what; who speaks to whom, as the Map's arcs and its dropdown's bars draw them;
   what the record does not hold; and the messages Between them. A read that says the same thing paints nothing, so a
   quiet department never flickers on the 2.5 s tick, and a clock's seconds paint nothing; a change paints on the tick
   that reads it. The answer is kept either way, so the next paint is the newest one. */
function wbFvSig(v){
  if (!v || v.failed) return "failed";
  const c = v.cycle || {}, share = x => Math.round((Number(x) || 0) * 50), minute = at => String(at || "").slice(0, 16);
  const five = WB_FUNCS.map(wbCap), talk = (v.speaks || []).filter(p => five.indexOf(p.from) >= 0 && five.indexOf(p.to) >= 0);
  const most = talk.reduce((x, p) => Math.max(x, p.n || 0), 0) || 1;
  return JSON.stringify([v.stopped, c.state, c.step, c.says, c.needs_you, c.asks, c.round, (c.ceiling || {}).rounds, (c.steps || []).map(p => p.state),
    (v.functions || []).map(f => [f.name, f.state, f.waits_on, f.line, share((f.spend || {}).share),
      f.last ? [f.last.what, f.last.detail, minute(f.last.at)] : null]),
    share((v.budget || {}).share), (v.made || []).map(a => [a.art, a.v, a.by, (a.readers || []).join(",")]),
    (v.speaks || []).map(p => [p.from, p.to, share((p.n || 0) / most)]), v.not_recorded || [],
    (v.between || []).map(b => [b.thread, b.from, (b.to || []).join(","), b.act, b.detail])]);
}
async function wbLoadFv(ref, again){
  const st = wbS();
  if (!ref || st.busy["fv:" + ref] || (st.fv[ref] && !again)) return;
  st.busy["fv:" + ref] = true;
  try {
    const v = await apiGet(wbUrl(ref, "functions"));
    const sig = wbFvSig(v), moved = sig !== st.fvSig[ref];
    st.fv[ref] = v; st.fvSig[ref] = sig;
    delete st.busy["fv:" + ref];
    if (moved && (!again || !wbTyping())) dpRender();
  } catch (e) {
    if (!st.fv[ref]) st.fv[ref] = { failed: true };
    delete st.busy["fv:" + ref];
    if (!again) dpRender();
  }
}
/* 20-dept.js asks this for the list column's function rows (S3): undefined for a department with no functions read
   (not on the engine runtime, or its map not read yet), null while it is read, the read once it lands */
function wbFnView(ref){
  if (!wbIs(ref)) return undefined;
  const m = wbS().map[ref];
  return m && wbRt(m) ? wbFv(ref) : undefined;
}
/* one artifact as the record says it: who made each version, who reads it (M1.2) */
function wbMadeOf(fv, name){ return ((fv && fv.made) || []).filter(x => x.art === name)[0] || null; }
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
    /* the five functions' read is read on the same clock: the Map's boxes, the list's dots, All five and the open
       function's page repaint only when what they show moved (PRD M1.9) */
    if (st.fv[S.dp.sel]) wbLoadFv(S.dp.sel, true);
    /* a department's answer lands on Root's board without a run of Root's own, so the open chat is read on its own clock;
       so is the chat read All five and a function's pane draw the cards that wait on the owner from (S6, S10, PRD M3.7),
       so a card raised, or answered elsewhere, shows there as it does in Chat (found by a verifier 2026-10-26: All five
       showed 'needs you' and no card) */
    const ftab = (typeof dpS === "function" && dpS().tab[S.dp.sel]) || "", fk = S.dp.sel + ":" + ftab;
    const cards = wbTab(S.dp.sel) === "chat" || wbTab(S.dp.sel) === "five" || WB_FUNCS.indexOf(ftab) >= 0;
    if (cards && st.chat[S.dp.sel]) wbLoadChat(S.dp.sel, true);
    /* a function's open chat is read on the same clock */
    if (ftab && st.fnchat[fk] && dpS().pane[fk] === "chat") wbLoadFnChat(S.dp.sel, ftab, true);
    if (WB_FUNCS.indexOf(ftab) >= 0 && st.fnpage[fk] && (!dpS().pane[fk] || dpS().pane[fk] === ftab)) wbLoadFnPage(S.dp.sel, ftab, true);
    /* and so is the open Agent activity: the lifecycle's events land while the person watches */
    if (ftab === "activity" && typeof dpActivityAgain === "function") dpActivityAgain(S.dp.sel);
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
  let top = `<div class="o2g dpg wb">` +
    (wbRt(m) ? dpRow("Chat", `data-wbtab="chat"`, tab === "chat") : "") +
    dpRow("Map", `data-wbtab="map"`, tab === "map") +
    /* the ruled Map (PRD M1.5): System status folds into the Map's NOW line for a department on the runtime */
    (wbRt(m) && wbV2() ? "" : dpRow("System status", `data-wbtab="status"`, tab === "status")) +
    /* the ruled engine card (PRD M4.7, S17): on the engine runtime the motor folds into each engine's card */
    (wbRt(m) ? "" : dpRow("Motor", `data-wbtab="motor"`, tab === "motor")) +
    (wbRt(m) ? dpRow("Board", `data-wbtab="board"`, tab === "board") +
      dpRow("Agent activity", `data-wbtab="activity"`, tab === "activity") : "") + `</div>`;
  /* 25-j2view.js: in Settings and records the first group is one row back to the J2 page */
  if (typeof j2vTop === "function"){ const t = j2vTop(n.ref, m); if (t) top = t; }
  const engines = dpGroup("Engines", ((m && m.engines) || []).map(e => {
    const on = tab === "engine" && st.sel[n.ref] === e.name;
    const word = e.state === "Running" ? "running" : (e.state === "Waits" ? "paused" : (e.state === "Missing" ? "fault" : "idle"));
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
  /* Identity's question takes words, never a stamp: it is answered on its card in the Chat (M0.6); so is an ask with
     options, which takes one of them (M3.5) */
  return asks.map(a => a.kind === "j2_identity" || wbOptionAsk(a) ? `<div class="dpask wb"><div class="dpasks">${wbEsc(a.title || a.text)}</div>` +
    `<div class="dpaskd">Identity · ${wbEsc(wbWhen(a.created))}</div>` + wbBtn("Identity asks you in Chat ›", `data-wbtab="chat"`) + `</div>`
    : `<div class="dpask wb"><div class="dpasks">${wbEsc(a.text)}</div>` +
    `<div class="dpaskd">${wbEsc(a.engine)} · ${wbEsc(wbWhen(a.created))}</div>` +
    wbBtn("Stamp", `data-wbdecide="${wbEsc(a.id)}" data-wbok="1"`, "dpstamp") +
    wbBtn("Say no", `data-wbdecide="${wbEsc(a.id)}" data-wbok="0"`) + `</div>`).join("");
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
  /* two engines to a row, each row opening on the artifact it reads, as drawn; an engine the registered plan left out
     is not on the line, and is named under it (PRD M4.2); before Root's check, the Brief alone and 'No plan yet', as
     on the second design's Map (map_view's planned) */
  if (m.planned === false) return `<div class="wbflow">${(m.artifacts || []).length ? doc(m.artifacts[0].name) : ""}</div>` + dpQuiet("No plan yet");
  const engs = (m.engines || []).filter(e => e.in_line !== false), rows = [];
  const out = (m.engines || []).filter(e => e.in_line === false).map(e => e.name);
  for (let i = 0; i < engs.length; i += 2) rows.push(engs.slice(i, i + 2));
  return rows.map(r => `<div class="wbflow">` + doc(r[0].reads) +
    r.map(e => arrow + eng(e) + arrow + doc(e.writes)).join("") + `</div>`).join("") +
    (out.length ? `<div class="dpchk">Left out of the plan: ${wbEsc(out.join(", "))}</div>` : "");
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
async function wbLoadEngine(ref, name, again){
  const st = wbS(), k = ref + ":" + name;
  if ((st.engine[k] && !again) || st.busy["e:" + k]) return;
  st.busy["e:" + k] = true;
  const was = JSON.stringify(st.engine[k] || null);
  try { st.engine[k] = await apiGet(wbUrl(ref, "engine/" + encodeURIComponent(name))); } catch (e) { if (!again) st.err["e:" + k] = String(e); }
  delete st.busy["e:" + k];
  /* read again when the record moved: an engine card paints only when what it shows moved */
  if (!again || (JSON.stringify(st.engine[k] || null) !== was && !wbTyping())) dpRender();
}
function wbEngineHtml(n){
  const st = wbS(), name = st.sel[n.ref], k = n.ref + ":" + name;
  const rt = wbRt(st.map[n.ref]);
  const pane = st.pane[k] || (rt ? "steps" : "engine");
  let tabs = dpTabsHtml(pane, rt ? WB_RT_PANES : WB_ENG_PANES, `data-wbpanekey="${wbEsc(k)}" data-wbpane`);
  const e = st.engine[k];
  if (rt){
    /* the engine card (PRD M4.7, S17): its head on every tab, from the engine read */
    if (!e) wbLoadEngine(n.ref, name);
    tabs = wbEngHeadHtml(name, e && e.card) + tabs;
  }
  if (rt && pane === "steps") return tabs + wbStepsHtml(n.ref, name);
  if (!e){ wbLoadEngine(n.ref, name); return (rt ? tabs : "") + dpSkel(); }
  if (pane === "runs"){
    return tabs + dpCard("Runs", (e.runs || []).length ? e.runs.map(r => wbRunRow(r,
      r.wrote ? ` <button type="button" class="o2more wb" data-wbart="${wbEsc(r.wrote.art.toLowerCase().replace(/[^a-z0-9]+/g, "-"))}" data-wbpane="trace" data-wbv="${r.wrote.v}">Trace</button>` : "")).join("")
      : dpQuiet("No runs yet"));
  }
  const env = e.envelope || {};
  const made = dpCard("The engine", `<div class="dpengines">` +
      dpKV("Runs as", e.runs_as, "Not named") + dpKV("Needs", e.reads, "Not named") + dpKV("Makes", e.writes, "Not named") + `</div>`);
  /* on the engine runtime the motor is folded into the card, and the five functions sit beside it (S17) */
  if (rt && e.card) return tabs + `<div class="wbs17 wb">` + wbEngMotorHtml(e.card) + wbEngFiveHtml(e.card) + `</div>` + made;
  return tabs + made +
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
    const had = ((st.chat[ref] || {}).departments || []).map(x => x.ref);
    const known = had.length, now = (v.departments || []).length;
    st.chat[ref] = v; st.chatSig[ref] = sig;
    delete st.busy["c:" + ref];
    if (st.chatSig[ref + ":depts"] !== undefined && now > known && typeof loadOrg2 === "function"){
      (v.departments || []).forEach(x => { if (had.indexOf(x.ref) < 0) st.born[x.ref] = true; });
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
  if (st.fv[ref]) wbLoadFv(ref, true);
  Object.keys(st.fnpage).forEach(k => { if (k.indexOf(ref + ":") === 0) wbLoadFnPage(ref, k.slice(ref.length + 1), true); });
  Object.keys(st.engine).forEach(k => { if (k.indexOf(ref + ":") === 0) wbLoadEngine(ref, k.slice(ref.length + 1), true); });
}
function wbRungHtml(s){
  const at = WB_RUNGS.map(r => r[0]).indexOf(s.rung);
  return `<span class="wbrung" title="${wbEsc(s.rung_name)}">` +
    WB_RUNGS.map((r, i) => `<i${i <= at ? ` class="on"` : ""}></i>`).join("") + `</span>`;
}
function wbRungName(id){ return (WB_RUNGS.filter(r => r[0] === id)[0] || ["", ""])[1]; }
function wbChip(word, cls){ return `<span class="wbchip${cls ? " " + cls : ""}">${wbEsc(word)}</span>`; }
/* an artifact's slug, as the map gives it: its name in lower case, joined by dashes */
function wbSlug(name){ return String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
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
  const act = `<span class="dpchk">${wbEsc(wbActWord(p))} · ${wbEsc(wbWhen(p.at))}</span>`;
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
    `<span class="dpchk">${wbEsc(wbActWord(p))}${p.line ? "" : " · " + wbEsc(wbCap(p.word || ""))} · ${wbEsc(wbWhen(p.at))}</span>` +
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
   you stand as a chip the person can take off. On Root's own chat the left
   name is Root and the department is a chip on the turn; in a department's
   chat only Identity speaks, so each of its turns is signed with Identity's
   mark and the department's name (PRD M3.6, screen S15; found by a verifier
   2026-10-23: a department's turns were signed Root, as if Root spoke for it).
   The markup is the Sutra chat's own (05-chat.js: turn, who, u, a), so it
   reads as a chat. */
/* The department a turn is about is a chip that opens it (found live 2026-09-28: the person clicked the chip first). */
function wbDeptChip(ref, name){
  return `<button type="button" class="wbchip wbto wb" data-wbopen="${wbEsc(ref)}">${wbEsc(name)}</button>`;
}
/* The name the organisation's helper wears on the screen, in one place. The department page (S-20) says the screen
   will say Sutra; the J1 contract of 2026-10-05 keeps Root, and test W45 pins it. Changing this word is the whole change. */
const WB_HELPER = "Root";
function wbChatTurn(t, scoped, signer){
  /* `signer` is the department whose chat this is: its turns are Identity's, signed with its mark and that name */
  const dept = !scoped && !signer && t.name ? (t.dept ? wbDeptChip(t.dept, t.name) : wbChip(t.name)) : "";
  const who = signer ? (typeof wb2Mark === "function" ? wb2Mark("identity") : "") + wbEsc(signer) : WB_HELPER + dept;
  /* a stamp or a no carries no words of its own: the act is the line, in the owner's words (said no, never refused) */
  const line = t.line || (t.msg_type === "accept-proposal" ? "Stamped" : t.msg_type === "reject-proposal" ? "Said no" : wbCap(t.word || ""));
  if (t.src === "Owner") return `<div class="turn wbturn"><div class="who who-you">${dept}You</div><div class="u md">${wbEsc(line)}</div></div>`;
  /* a turn that carries a way to the thing (the site that went live) shows it as the one button a person clicks
     (found live 2026-09-28: after the publish stamp the chat said nothing, and the person did not know it was live);
     a turn about something else filed (an engine the person added) opens that filed work under its own name
     (found live 2026-09-29: "Source Reader v1 is filed." wore "Open the live site") */
  const link = !t.link ? "" : t.word === "live" || t.link === "Live site"
    ? ` <button type="button" class="wbchip on wbto wb" data-wblive="${wbEsc(t.dept || "")}">Open the live site</button>`
    : ` <button type="button" class="wbchip on wbto wb" data-wbopenart="${wbEsc(wbSlug(t.link))}" data-wbdept="${wbEsc(t.dept || "")}">Open ${wbEsc(t.link)}</button>`;
  /* J1.5: the second department the owner's words named is offered, never made unasked: one chip sends the words for it */
  const offer = t.offer && t.offer.words
    ? ` <button type="button" class="wbchip wbto wb" data-wbsay="${wbEsc(t.offer.words)}">Set up: ${wbEsc(t.offer.label || t.offer.words)}</button>` : "";
  return `<div class="turn wbturn"><div class="who who-ai">${who}</div><div class="a">${wbEsc(line)}${link}${offer}` +
    `<span class="dpchk">${wbEsc(WB_ACTS[t.msg_type] || t.msg_type)} · ${wbEsc(wbWhen(t.at))}</span></div></div>`;
}
/* Identity's question (S6, M0.6): a card in the chat that takes words, never a stamp. Its Send answers where the
   question lives (/api/dept/{ref}/j2/answer); answered, the card goes quiet and keeps the answer under it. Every
   question on Identity's standard (M3.3), whether its reading asked it or its code read the gap on the record, also
   offers 'Just do it', which ends the questions on the kind's defaults (found by a verifier 2026-10-26: the owner
   question Identity's code asked had none); a question on thin words has no such way, since nothing was said to
   build from. */
function wbTakesJust(q){ return !!(q && (q.standard || (q.missing && q.missing !== "words"))); }
const WB_ANSWER_SAYS = { EMPTY_ANSWER: "Write your answer first, then Send.", NO_OPEN_QUESTION: "That question is no longer open.",
                         ALREADY_HANDLED: "That question is already answered." };
function wbQuestionHtml(q, ref, named){
  const st = wbS(), at = q.ref || ref, k = at + ":q:" + q.id, said = q.answered ? { text: q.answered, at: q.decided } : st.said[k];
  /* on Root's whole chat the card says which department asks */
  const whose = named && q.dept ? " · " + wbEsc(q.dept) : "";
  if (said) return `<div class="dpask gone wbq wb"><div class="dpk">Identity asked${whose}</div><div class="dpasks">${wbEsc(q.text)}</div>` +
    `<div class="dpaskd">You: ${wbEsc(said.text)}${said.at ? " · " + wbEsc(wbWhen(said.at)) : ""}</div></div>`;
  const busy = !!st.busy["q:" + k];
  return `<div class="dpask wbq wb"><div class="dpk">Identity asks${whose}</div><div class="dpasks">${wbEsc(q.text)}</div>` +
    (q.why ? `<div class="dpaskd">${wbEsc(q.why)}</div>` : "") +
    `<div class="wbbox wb"><textarea id="wbd-q-${wbEsc(q.id)}" data-wbdraft="${wbEsc(k)}" data-wbqid="${wbEsc(q.id)}" data-wbqref="${wbEsc(at)}" rows="2" ` +
    `placeholder="Type your answer...">${wbEsc(st.draft[k] || "")}</textarea>` +
    wbBtn(busy ? "Sending..." : "Send", `data-wbanswer="${wbEsc(q.id)}" data-wbref="${wbEsc(at)}"${busy ? " disabled" : ""}`, "dpstamp") +
    (wbTakesJust(q) ? wbBtn("Just do it", `data-wbjust="${wbEsc(q.id)}" data-wbref="${wbEsc(at)}"${busy ? " disabled" : ""}`) : "") + `</div></div>`;
}
/* The open questions and the answered ones, each at its time among the turns: a card goes before the first turn said
   after it was asked. The card is the one place the question and its answer are said: the chat read leaves out
   Identity's line that names the card and the owner's words it keeps (engine_runtime._on_card). An ask with options
   (a blocked plan's way out, M3.5) is a card of the same kind, open or chosen. */
function wbOptionAsk(a){ return !!(a && a.options && a.options.length); }
function wbQuestions(c){
  const open = (c.asks || []).filter(a => a.kind === "j2_identity" || wbOptionAsk(a));
  return open.concat(c.answered || [], c.chosen || []).sort((a, b) => String(a.created || "") < String(b.created || "") ? -1 : 1);
}
/* A blocked plan's card (S10, PRD M3.5): no dead end. It says what stopped, who, why, and what happens if nothing is
   done, then up to three ways out, the first the one Identity recommends, each with its cost beside it and in its
   title. One click applies an option by code; nothing here leaves the machine, so there is no second confirm. The
   first way out is the owner's own words, from the box. Chosen, the card goes quiet with 'You chose: ... · time'. */
const WB_OPTION_SAYS = { UNKNOWN_OPTION: "That choice is no longer on the card.", ALREADY_HANDLED: "That card is already answered.",
                         EMPTY_ANSWER: "Write what to change first, then Send.", OVER_CAP: "That is more than the limit allows." };
function wbOptionsHtml(a, ref, named){
  const st = wbS(), at = a.ref || ref, k = at + ":o:" + a.id;
  const whose = named && a.dept ? " · " + wbEsc(a.dept) : "";
  const head = wbEsc(a.title || a.text);
  if (a.chosen) return `<div class="dpask gone wbq wbopt wb"><div class="dpk">Identity asked${whose}</div><div class="dpasks">${head}</div>` +
    `<div class="dpaskd">You chose: ${wbEsc(a.chosen.label)}${a.chosen.words ? ": " + wbEsc(a.chosen.words) : ""}` +
    `${a.chosen.at ? " · " + wbEsc(wbWhen(a.chosen.at)) : ""}</div></div>`;
  const busy = !!st.busy["o:" + k];
  const kv = (label, v) => v ? `<div class="wboptkv"><span class="dpk">${label}</span><span>${wbEsc(v)}</span></div>` : "";
  const attrs = o => `data-wboption="${wbEsc(o.id)}" data-wbopt="${wbEsc(a.id)}" data-wbref="${wbEsc(at)}" title="${wbEsc(o.label + ": " + o.cost)}"${busy ? " disabled" : ""}`;
  const words = (a.options || []).filter(o => o.id === "words")[0];
  const box = words ? `<div class="wboptrow wbbox wb"><textarea id="wbd-o-${wbEsc(a.id)}" data-wbdraft="${wbEsc(k)}" data-wboptid="${wbEsc(a.id)}" ` +
    `data-wboptref="${wbEsc(at)}" rows="2" placeholder="${wbEsc(words.label + "...")}">${wbEsc(st.draft[k] || "")}</textarea>` +
    wbBtn(busy ? "Applying..." : "Send", attrs(words), "dpstamp") + `<span class="dpchk">${wbEsc(words.cost)}</span></div>` : "";
  const rows = (a.options || []).filter(o => o.id !== "words").map(o => `<div class="wboptrow">` +
    wbBtn(busy ? "Applying..." : o.label, attrs(o)) + `<span class="dpchk">${wbEsc(o.cost)}</span></div>`).join("");
  /* what Identity said is the card's own line, under its title: the chat leaves that line to the card (M0.6) */
  const said = a.title && a.text && a.text !== a.title ? `<div class="dpaskd">${wbEsc(a.text)}</div>` : "";
  return `<div class="dpask hard wbq wbopt wb"><div class="dpk">Identity asks${whose}</div><div class="dpasks">${head}</div>` + said +
    kv("Who", a.who) + kv("Why", a.why) + kv("If nothing is done", a.if_nothing) + box + rows + `</div>`;
}
/* The cards that wait on the owner (S6, S10) stand wherever the department needs them: Chat first, then All five and
   the pane of the function that caused a block, Identity's question also on Identity's pane (wbIdentityHtml). Each is
   the same card with the same state, read from the chat read and drawn by the same code, so answering in one place
   clears them all (PRD M3.7; found by a verifier 2026-10-23: All five and the causing function's pane showed a 'needs
   you' chip and no card). A blocked card's `who` names the function that caused it: 'Root, at its review' is Root's
   check of Adaptation's plan, so that card stands on Adaptation's pane; the owner's own no is Identity's to carry. */
function wbCauseFn(a){
  const w = String((a && a.who) || "").split(/[^A-Za-z]+/)[0].toLowerCase();
  return WB_FUNCS.indexOf(w) >= 0 ? w : (w === "root" ? "adaptation" : "identity");
}
/* the open cards of a department: on a function's pane (`fn`) the blocked cards that function caused; on All five every
   open question and blocked card; nothing while the chat read is on its way */
function wbOpenCards(ref, fn){
  const c = wbS().chat[ref];
  if (!c){ wbLoadChat(ref); return ""; }
  if (c.failed) return "";
  return (c.asks || []).filter(a => fn ? (wbOptionAsk(a) && wbCauseFn(a) === fn) : (a.kind === "j2_identity" || wbOptionAsk(a)))
    .map(a => (wbOptionAsk(a) ? wbOptionsHtml : wbQuestionHtml)(a, ref, false)).join("");
}
async function wbChoose(ref, id, at, oid){
  const st = wbS(), k = at + ":o:" + id, body = { option: oid };
  if (st.busy["o:" + k]) return;
  if (oid === "words") body.text = st.draft[k] || "";
  st.busy["o:" + k] = true;
  dpRender();
  try {
    await apiPost(wbUrl(at, "asks/" + encodeURIComponent(id)), body);
    if (oid === "words") delete st.draft[k];
  } catch (e) {
    /* the typed words stay in the box; the snack says why, and the card is read again */
    const code = (/"code":\s*"([A-Z_]+)"/.exec(String((e && e.message) || "")) || [])[1];
    if (typeof snack === "function") snack(WB_OPTION_SAYS[code] || "Could not apply your choice. Try again.", { kind: "error" });
  }
  delete st.busy["o:" + k];
  wbAgain(ref);
  await wbLoadMap(ref, true);
  dpRender();
}
async function wbAnswer(ref, id, at, said){
  const st = wbS(), k = at + ":q:" + id, text = said !== undefined ? said : (st.draft[k] || "");
  if (st.busy["q:" + k]) return;
  st.busy["q:" + k] = true;
  dpRender();
  try {
    await apiPost(dpUrl(at, "j2/answer"), { text: text });
    st.said[k] = { text: text.split(/\s+/).filter(Boolean).join(" "), at: new Date().toISOString() };
    if (said === undefined) delete st.draft[k];
  } catch (e) {
    /* the typed words stay in the box; the snack says why in a person's words */
    const code = (/"code":\s*"([A-Z_]+)"/.exec(String((e && e.message) || "")) || [])[1];
    if (typeof snack === "function") snack(WB_ANSWER_SAYS[code] || "Could not send your answer. Try again.", { kind: "error" });
  }
  delete st.busy["q:" + k];
  wbAgain(ref);
  await wbLoadMap(ref, true);
  dpRender();
}
/* An ask is a line with its buttons, and it says where it lives: the stamp goes
   to that department, never to the one the chat is read from. Identity's
   question takes words, so it is a card of its own in the chat (above). */
function wbChatAsksHtml(c){
  const asks = (c.asks || []).filter(a => a.kind !== "j2_identity" && !wbOptionAsk(a));
  if (!asks.length) return "";
  return dpCard("Waiting for you", asks.map(a => `<div class="dpask wb"><div class="dpasks">${wbEsc(a.text)}</div>` +
    `<div class="dpaskd">${wbEsc([a.dept, a.engine].filter(Boolean).join(" · "))} · ${wbEsc(wbWhen(a.created))}</div>` +
    wbBtn("Stamp", `data-wbdecide="${wbEsc(a.id)}" data-wbok="1" data-wbref="${wbEsc(a.ref || "")}"`, "dpstamp") +
    wbBtn("Say no", `data-wbdecide="${wbEsc(a.id)}" data-wbok="0" data-wbref="${wbEsc(a.ref || "")}"`) + `</div>`).join(""));
}
function wbChatBoxHtml(n, m){
  const st = wbS(), k = n.ref + ":ask";
  const inside = m.kind !== "root" && !!m.root, on = inside && st.chip[n.ref] !== false;
  const chip = !inside ? "" : on
    ? `<button type="button" class="wbchip on wbto wb" data-wbchip="off">to ${wbEsc(m.name)} &times;</button>`
    : `<button type="button" class="wbchip wbto wb" data-wbchip="on">to ${WB_HELPER}</button>`;
  const err = st.err[k] ? `<div class="o2quiet dpq">${wbEsc(st.err[k])}</div>` : "";
  /* Root's box: once departments exist, words for one of them are the usual thing to say (found live 2026-09-28:
     "Ask Root for a department" invited a new one when the person meant the one they had) */
  const depts = ((st.chat[n.ref] || {}).departments || []);
  const rootSay = m.kind === "root" && depts.length ? "Say it to " + WB_HELPER + ", or name a department: " + depts.map(d => d.name).join(", ") : (m.say || "Say it to " + WB_HELPER);
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
  /* a department's chat is signed by its Identity; Root's own chat keeps Root */
  const signer = m.kind === "root" ? "" : (m.name || "");
  const all = c.turns || [];
  /* fewer words (SIM-3 f): Root's hand-over line folds to one quiet line once that department has answered */
  const folded = t => !scoped && t.src !== "Owner" && /^handed to /.test(t.line || "") && t.dept &&
    all.some(u => u.n > t.n && u.dept === t.dept && u.src !== "Owner" && !/^handed to /.test(u.line || ""));
  const count = all.length, seen = st.turns[n.ref];
  const landed = seen !== undefined && count > seen;
  /* motion marks what just happened and nothing else: the turn that landed slides in once */
  /* an open blocked card (S10) stands at the top of the Chat while it waits, pinned as the chat scrolls (S10: 'Where:
     top of Chat'); a question (S6) and every answered card stand at their time in the flow */
  const pinned = wbQuestions(c).filter(q => wbOptionAsk(q) && !q.chosen);
  const qs = wbQuestions(c).filter(q => pinned.indexOf(q) < 0);
  const pin = pinned.length ? `<div class="wbpin wb">${pinned.map(q => wbOptionsHtml(q, n.ref, !scoped)).join("")}</div>` : "";
  const card = t => { let out = ""; while (qs.length && (!t || String(qs[0].created || "") < String(t.at || ""))){ const q = qs.shift(); out += (wbOptionAsk(q) ? wbOptionsHtml : wbQuestionHtml)(q, n.ref, !scoped); } return out; };
  const turns = all.map((t, i) => card(t) + (folded(t) ? `<div class="o2quiet dpq wbfold">${wbEsc(t.line)}</div>`
    : wbChatTurn(t, scoped, signer).replace('class="turn wbturn"', (landed && i === all.length - 1) ? 'class="turn wbturn wbnew"' : 'class="turn wbturn"'))).join("") + card(null);
  const empty = m.kind === "root" && !depts.length ? "No department yet. Say what the first one is for." : "Nothing has been said yet";
  const names = !scoped && depts.length ? `<div class="wbstep"><span class="dpk">Departments</span>${depts.map(d => wbDeptChip(d.ref, d.name)).join("")}</div>` : "";
  /* while an engine runs, the chat says so under the last turn, and the mark breathes (founder, 2026-09-28: "I give a
     message to the chat, and it seems something is happening, but I don't know"); a department that is Off works on nothing */
  const running = m.stopped ? [] : ((m.status && m.status.running) || []);
  const working = running.map(r => `<div class="o2quiet dpq wbworking"><i class="wbbreath"></i>${wbEsc(`${r.engine} is working${r.what ? ": " + r.what : ""}`)}</div>`).join("");
  st.turns[n.ref] = count;
  wbKeepPlace(n.ref, landed);
  return `<div class="wbchat wb">${pin}${turns || (running.length ? "" : dpQuiet(empty))}${working}</div>` + wbChatAsksHtml(c) + wbChatBoxHtml(n, m) + names;
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
  /* an act with no words of its own is said in the owner's words: the owner stamps; a function says yes or says no */
  const line = t.line || (t.msg_type === "accept-proposal" ? (t.src === "Owner" ? "Stamped" : "Said yes")
                          : t.msg_type === "reject-proposal" ? "Said no" : wbCap(t.word || ""));
  if (t.src === "Owner") return `<div class="turn wbturn"><div class="who who-you">You</div><div class="u md">${wbEsc(line)}</div></div>`;
  return `<div class="turn wbturn"><div class="who who-ai">${wbEsc(t.src)}</div><div class="a">${wbEsc(line)}` +
    `<span class="dpchk">${wbEsc(t.counter ? WB_COUNTER : (WB_ACTS[t.msg_type] || t.msg_type))} · ${wbEsc(wbWhen(t.at))}</span></div></div>`;
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
  /* one voice (PRD M3.6, Q1): only Identity speaks with the owner, so a function's box says the words go to Identity,
     about that function; they always did (data-wbask="fn:...", the about chip) */
  const say = String(fn).toLowerCase() === "identity" ? "Say it to Identity" : "Say it to Identity about " + name;
  return `<div class="wbchat wbfn wb">${turns || dpQuiet("Nothing yet between you and " + name)}</div>` +
    `<div class="wbbox wb"><textarea data-wbdraft="${wbEsc(dk)}" rows="2" placeholder="${wbEsc(say)}">${wbEsc(st.draft[dk] || "")}</textarea>` +
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
    const [by, readers] = wbWhoMade(n.ref, a.name, cur);
    return tabs + dpCard("The work item", `<div class="dpengines">` +
      dpKV("Made by", by, "Not recorded") +
      dpKV("Read by", readers, "Nobody yet") +
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
/* Who made a version and who reads the work, from the record (PRD M1.2): on the engine runtime the functions read says
   it (runs.json for the maker, each engine's reads in the definitions and born templates for the readers); a department
   of the first build reads its own engines' reads and writes off its map. Nothing here is a table of names. */
function wbWhoMade(ref, name, cur){
  const m = wbS().map[ref] || {}, fv = wbFv(ref), mk = wbMadeOf(fv, name);
  if (cur && cur.run === "owner") return ["The owner", wbReadersOf(m, mk, name)];
  const by = mk ? ((mk.by_v || {})[String(cur && cur.v)] || "") : (wbMakerByLine(m, name) || "");
  return [by === "Owner" ? "The owner" : by, wbReadersOf(m, mk, name)];
}
function wbMakerByLine(m, name){ return ((m.engines || []).filter(e => e.writes === name)[0] || {}).name || ""; }
function wbReadersOf(m, mk, name){
  const names = mk ? (mk.readers || []) : (m.engines || []).filter(e => e.reads === name).map(e => e.name);
  return names.join(", ");
}

/* ── a function's page: what its site page holds (PRD M1.7) ─────────────────
   The pane each function already has opens on its page: its one line, its
   template's fields, its recipe (each step run by code, by the AI inside, or
   by a person, on the rung it has earned), its journeys with their live
   status and last move, and its version 1 scope. A field the record leaves
   empty is one quiet line, "not set yet". Read from functions_view.function;
   the first tab keeps its name. */
/* a function's page paints again when anything it shows moved (M1.9; round 3, gap 5): its node (its word too: a
   department switched off says stopped), the template it runs and each field's value as the page draws it (the Limit
   as its bar, its share to a fiftieth as wbFvSig keeps a spend, so a bar that moves paints and a hair's move does
   not), a step's name, group, who runs it and its rung, or a journey's status, last move and its minute; Coordination's
   pane also when its timetable, what it left out, who makes and reads, the chain's bar, an alarm or a tie moved (M4.7) */
function wbFnPageSig(v){
  if (!v || v.failed) return "failed";
  const n = v.node || {}, share = x => Math.round((Number(x) || 0) * 50);
  const value = f => f.key === "envelope" ? share((f.value || {}).share) : f.value;
  const co = v.fn === "coordination" ? (v.j2 || {}) : {}, minute = at => String(at || "").slice(0, 16);
  return JSON.stringify([n.state, n.word, n.waits_on, n.line, n.why, (v.template || {}).name, v.line, v.holds, v.hands_to, v.keeps, v.v1,
    (v.journeys || []).map(j => [j.id, j.name, j.status, j.last && j.last.summary, j.last && String(j.last.at || "").slice(0, 16)]),
    (v.recipe || []).map(r => [r.id, r.name, r.under, r.by, r.rung, r.rung_name]),
    (v.fields || []).map(f => [f.key, f.label, f.placeholder, value(f)]),
    (co.timetable || []).map(r => [r.engine, r.on, r.state, r.why, minute(r.at), r.window_min, r.last && r.last.wrote]),
    (co.left_out || []).map(r => r.engine), (co.handoffs || []).map(h => [h.art, h.v, h.says, (h.readers || []).join(",")]),
    share((co.chain || {}).share), (co.alarms || []).map(a => a.text), (co.ties || []).map(t => [t.said, minute(t.at)]), wbIdSig(v.j2), wbRcSig(v.j2)]);
}
/* Identity's pane paints again when its record moves: a point of the standard, the done line or an item, a rule, its
   question, a ruling */
function wbIdSig(j){
  if (!j || !j.standard || !j.standard.rows) return null;
  return [j.standard.rows.map(r => [r.id, r.state, r.note]), j.goal, j.done, (j.done_items || []).map(i => [i.id, i.text, i.confirm]),
    (j.rules || []).map(r => [r.tag, r.line, r.by]), j.open_question && j.open_question.id, (j.conflicts || []).map(c => [c.at, c.ruling])];
}
/* Identity's pane (S5, PRD M3.7), on top of its page: the open question (the same S6 card as in Chat, so answering in
   one place clears them all), Enough to work? (one row per point of the marked standard: a dot, a word and a note),
   the goal in the owner's words with a way to change it, done-when as items with level and how (a record from before
   Root drafted items keeps its done line, and that line is drawn as the record has it), the rules with where each came
   from, and the conflicts Identity closed; how Identity works folds under them. It renders the read and writes
   nothing: Change the goal opens the Chat with the box begun. */
const WB_STD = { met: ["ok", "met"], not_met: ["warn", "not yet"], to_confirm: ["warn", "to confirm"], reading: ["breath", "reading"] };
/* a rule's tag as the pane says it: the record keeps refuse; the screen never says refuse, so a refuse rule reads never */
const WB_TAG_SAYS = { refuse: "never" };
/* a rule as Identity's pane draws it: its tag as a chip in the pane's word, its line, and where it came from when the
   read says (S5 does; the department card under a page with no record of its own does not) */
function wbIdRuleHtml(r, from){
  return `<div class="wbidrule">${wbChip(WB_TAG_SAYS[r.tag] || r.tag, r.tag === "go" ? "on" : (r.tag === "always" ? "" : "ask"))}<span>${wbEsc(r.line)}</span>` +
    (from === undefined ? "" : `<span class="dpchk">${wbEsc(from)}</span>`) + `</div>`;
}
/* Identity's own record on its page read (S5), or null when the read carries none (an older read, or one that failed) */
function wbIdRecord(p){
  const j = (p && p.j2) || {};
  return j.standard && j.standard.rows ? j : null;
}
function wbIdentityHtml(ref, j){
  const q = j.open_question ? wbQuestionHtml(Object.assign({ ref: ref }, j.open_question), ref, false) : "";
  const rows = (j.standard.rows || []).map(r => {
    const [dot, word] = WB_STD[r.state] || ["off", r.state];
    return `<div class="dprow wbstd"><span class="dpdot ${dot}"></span><span><b>${wbEsc(r.says)}</b> ${wbChip(word, r.state === "met" ? "on" : "")}` +
      (r.note ? `<div class="dpchk">${wbEsc(r.note)}</div>` : "") + `</span></div>`;
  }).join("");
  const goal = j.goal ? `<div class="dpbig wbidgoal">${wbEsc(j.goal)}</div>` : dpQuiet("Identity has not read the words yet");
  const items = (j.done_items || []).map(i => `<div class="wbiditem"><button type="button" class="wbjid wb" data-wbfn="audit" title="Audit's reading">${wbEsc(i.id)}</button>` +
    `<span>${wbEsc(i.text)}</span>${i.confirm ? wbChip("to confirm") : ""}<span class="dpchk">${wbEsc([i.level, i.how].filter(Boolean).join(" · "))}</span></div>`).join("");
  const rules = (j.rules || []).map(r => wbIdRuleHtml(r, r.by === "yours" ? "yours" + (r.since ? " · " + wbWhen(r.since) : "") : "the template")).join("");
  const closed = (j.conflicts || []).map(c => `<button type="button" class="wbidconf wb" data-wbtab="board"><span class="dpchk">${wbEsc(wbWhen(c.at))}</span>` +
    `<span>${wbEsc(wbCap(c.who))}${c.plan ? " on " + wbEsc(c.plan) : ""}. Ruled: ${wbEsc(c.ruled)}${c.why ? "; " + wbEsc(c.why) : ""}.` +
    `${c.asked_you ? "" : " No ask to you."}</span></button>`).join("");
  return q + dpCard("Enough to work?", rows) +
    dpCard("Goal", goal + (j.goal ? `<div class="dpoffer">${wbBtn("Change the goal", `data-wbtab="chat" data-wbfill="Change the goal to: "`)}</div>` : "")) +
    dpCard("Done when", items ? `<div class="dpchk">Drafted by Root at birth</div>` + items : (j.done ? dpBig(j.done) : dpQuiet("No done-when items yet"))) +
    dpCard("Rules", rules || dpQuiet("No rules yet")) +
    dpCard("Conflicts closed", closed || dpQuiet("No conflict yet"));
}
async function wbLoadFnPage(ref, fn, again){
  const st = wbS(), k = ref + ":" + fn;
  if ((st.fnpage[k] && !again) || st.busy["fp:" + k]) return;
  st.busy["fp:" + k] = true;
  try {
    const v = await apiGet(wbUrl(ref, "functions/" + encodeURIComponent(fn)));
    const sig = wbFnPageSig(v), moved = sig !== st.fnpageSig[k];
    st.fnpage[k] = v; st.fnpageSig[k] = sig;
    delete st.busy["fp:" + k];
    if (moved && (!again || !wbTyping())) dpRender();
  } catch (e) {
    if (!st.fnpage[k]) st.fnpage[k] = { failed: true };
    delete st.busy["fp:" + k];
    if (!again) dpRender();
  }
}
/* ── Root's check, on Adaptation's pane (PRD M7.3, S11) ────────────────────────────────────────────────────────
   One row for the last review of the plan: a dot for each standard of the workflow schema that applied, in the order the
   app keeps them (its words as the title; ticked when it held and crossed when it did not, so a mark says it as well as a
   colour), the verdict and the time. A plan Root sent back names the standard that broke, in its words, and why, and shows
   the reshapes so far as dots. Root sends a plan back twice at most; the third refusal is the block (engine_runtime
   _j2_settle), and the owner is asked what to change in Chat. No count is printed. Reads root_checks[].checks of the
   Adaptation view ([{check, says, passed, why}]); a review from before the standards were listed has no checks and shows
   its own sentence. */
const WB_RESHAPES = 2;
const WB_RC_SAYS = { approved: "approved", back: "sent back", blocked: "blocked" };
/* a check's words: the standard's, or for the schema's own row (which is no standard) what it found */
function wbRcSays(c){ return c.says && c.says !== c.check ? c.says : (c.why || ""); }
function wbRcDot(c){
  const said = wbRcSays(c);
  return `<span class="wbrcdot${c.passed ? "" : " no"}" role="img" title="${wbEsc(said)}" aria-label="${wbEsc(said + (c.passed ? ", held" : ", did not hold"))}"></span>`;
}
/* the reviews at the end of the list that sent the plan back, one after another */
function wbRcFails(rows){
  let n = 0;
  for (let i = rows.length - 1; i >= 0 && !rows[i].passed; i--) n++;
  return n;
}
function wbRcSig(j){
  return j && Array.isArray(j.root_checks) ? j.root_checks.map(r => [r.at, r.passed, (r.checks || []).map(c => c.passed)]) : null;
}
function wbRootChecksHtml(rows){
  if (!rows.length) return dpCard("Root's check", dpQuiet("Root has not checked a plan yet"));
  const last = rows[rows.length - 1], fails = wbRcFails(rows), checks = last.checks || [];
  const state = last.passed ? "approved" : (fails > WB_RESHAPES ? "blocked" : "back");
  const row = `<div class="wbrcrow"><span class="wbrcdots">${checks.map(wbRcDot).join("")}</span>` +
    `<span class="wbrcv ${state}">${WB_RC_SAYS[state]}${last.at ? " · " + wbEsc(wbWhen(last.at)) : ""}</span></div>`;
  if (last.passed) return dpCard("Root's check", row);
  const broke = checks.filter(c => !c.passed).map(c => c.says && c.says !== c.check
    ? `<div class="wbrcwhy"><b>${wbEsc(c.says)}</b>${c.why ? wbEsc(": " + c.why) : ""}</div>` : `<div class="wbrcwhy"><b>${wbEsc(wbRcSays(c))}</b></div>`);
  const why = broke.length ? broke.join("") : (last.summary ? `<div class="wbrcwhy">${wbEsc(last.summary)}</div>` : "");
  const sent = Math.min(fails, WB_RESHAPES);
  return dpCard("Root's check", row + why + `<div class="wbrcrs ${state}"><span>reshapes</span>` +
    [0, 1].map(i => `<i class="${i < sent ? "on" : ""}"></i>`).join("") + `</div>`);
}

const WB_JOURNEY_DOT = { "done": "ok", "said yes": "ok", "heard": "ok", "let through": "ok", "told Identity": "ok", "moved": "ok",
                         "waiting": "wait", "held": "wait", "running": "", "failed": "block" };
const WB_BY = { code: "Code", AI: "AI", person: "Person" };
function wbFieldHtml(f){
  const v = f.value;
  if (f.placeholder) return dpCell(f.label, dpQuiet("not set yet"));
  if (f.key === "envelope") return dpCell(f.label, dpBar(Math.max(0, Math.min(1, Number((v || {}).share) || 0))));
  if (Array.isArray(v)) return dpCell(f.label, f.key === "checks"
    ? v.map(x => `<div class="dpfline">${wbEsc(x)}</div>`).join("") : `<div class="wbstep">${v.map(x => wbChip(x)).join("")}</div>`);
  return dpCell(f.label, `<div class="dpbig">${wbEsc(v)}</div>`);
}
function wbRecipeHtml(steps){
  if (!(steps || []).length) return dpCard("Recipe", dpQuiet("No steps yet"));
  const row = s => `<div class="wbrec">${wbChip(WB_BY[s.by] || s.by, s.by === "code" ? "on" : "")}<span>${wbEsc(s.name)}</span>` +
    wbRungHtml({ rung: s.rung, rung_name: s.rung_name }) + `</div>`;
  /* the steps that run on every start first; each thing the function hears is its own group, closed until opened */
  const own = steps.filter(s => !s.under), groups = [];
  steps.filter(s => s.under).forEach(s => { if (groups.indexOf(s.under) < 0) groups.push(s.under); });
  return dpCard("Recipe", own.map(row).join("") + groups.map(g => `<details class="wbrecg wb"><summary>${wbEsc(g)}</summary>` +
    steps.filter(s => s.under === g).map(row).join("") + `</details>`).join(""));
}
function wbJourneysHtml(js){
  if (!(js || []).length) return "";
  return dpCard("Journeys", js.map(j => {
    const dot = WB_JOURNEY_DOT[j.status] === undefined ? "off" : WB_JOURNEY_DOT[j.status];
    const last = j.last ? [j.last.summary, wbWhen(j.last.at)].filter(Boolean).join(" · ") : "";
    return `<div class="dprow wbjrn"><span class="dpdot${dot ? " " + dot : ""}"></span><span><span class="wbjid">${wbEsc(j.id)}</span>` +
      `${wbEsc(j.name)} ${wbChip(j.status)}${last ? `<div class="dpchk">${wbEsc(last)}</div>` : ""}</span></div>`;
  }).join(""));
}
function wbFnPageHtml(ref, fn){
  const st = wbS(), k = ref + ":" + fn, p = st.fnpage[k];
  if (!p){ wbLoadFnPage(ref, fn); return dpSkel(); }
  if (p.failed) return dpQuiet("Could not read");
  const node = p.node || {};
  const now = node.state ? dpRunRow(wbCap(node.word || node.state), node.why || node.line || "",
                                    ({ working: "", waiting: "wait", waiting_on_you: "warn", fault: "block", quiet: "off" })[node.state]) : "";
  const page = dpCard("The function", `<div class="dpbig">${wbEsc(p.line)}</div>` + now +
      `<div class="dpengines">` + dpKV("Holds", p.holds, "Not named") + dpKV("Hands to", p.hands_to, "Nobody") + dpKV("Keeps", p.keeps, "Not named") + `</div>`) +
    dpCard("The " + ((p.template && p.template.name) || "Default") + " template", `<div class="dpengines">` + (p.fields || []).map(wbFieldHtml).join("") + `</div>`) +
    wbRecipeHtml(p.recipe) + wbJourneysHtml(p.journeys) +
    dpCard("Version 1", `<div class="dpfline">${wbEsc(p.v1)}</div>`);
  /* Identity's own record on top (S5); its page folds under it */
  const j = wbIdRecord(p);
  if (fn === "identity" && j)
    return wbIdentityHtml(ref, j) + `<details class="wbhow wb"><summary>How Identity works</summary>${page}</details>`;
  /* Adaptation's pane opens on Root's check of its plan (S11), when the read carries the reviews */
  if (fn === "adaptation" && p.j2 && Array.isArray(p.j2.root_checks)) return wbRootChecksHtml(p.j2.root_checks) + page;
  return page;
}

/* ── Coordination's pane: the timetable (PRD M4.7, screen S7) ───────────────
   Who goes first and why anything waits, from Coordination's own state (functions_view.coordination, the j2 part of
   its page read): the timetable, one row per engine with what starts it, its window, and its last run or the exact
   reason it waits, and the engines the plan left out under it; who makes and who reads each thing; then the chain,
   alarms and ties side by side, and the function's page folded at the bottom. Coordination judges nothing about
   content, so nothing here is a verdict. An engine row opens its engine card and an artifact its filed work; the
   pane writes nothing. No count at rest: the chain is a bar and its numbers are the hover. */
const WB_TT_DOT = { running: "breath", turn: "breath", waits: "wait", ran: "ok", stopped: "off" };
const WB_NODE_DOT = { working: "breath", waiting: "wait", waiting_on_you: "warn", fault: "block", quiet: "off" };
/* amber means it waits on you and nothing else; waiting on another function is the hollow ring */
function wbTtDot(r){ return r.state === "waits" && /\b(stamp|you|owner)\b/.test(r.why || "") ? "warn" : (WB_TT_DOT[r.state] || "off"); }
function wbTtSaid(r){
  if (r.state === "running") return "running since " + wbWhen(r.at);
  if (r.state === "turn") return "its turn" + (r.at ? " since " + wbWhen(r.at) : "");
  if (r.state === "waits") return /^waits\b/.test(r.why || "") ? r.why : "waits: " + (r.why || "");
  if (r.state === "ran") return "ran " + wbWhen(r.at) + (r.last && r.last.wrote ? " · " + r.last.wrote : "");
  return r.word || "";
}
function wbTtRow(r){
  return `<button type="button" class="wbtt wb" data-wbengine="${wbEsc(r.engine)}" title="${wbEsc(r.on || "")}">${wbDot(wbTtDot(r))}` +
    `<b>${wbEsc(r.engine)}</b><span>${wbEsc(r.starts || "")}</span><span class="wbttw">window ${wbEsc(r.window_min)} min</span>` +
    `<span class="wbttn">${wbEsc(wbTtSaid(r))}</span></button>`;
}
function wbHandRow(h){
  const art = h.v ? h.art + " v" + h.v : h.art, by = h.says || "not made yet";
  const rd = (h.readers || []).length ? "read by " + h.readers.join(", ") : "read by nobody yet";
  const body = `<b>${wbEsc(art)}</b><span>${wbEsc(by)}</span><span class="wbttn">${wbEsc(rd)}</span>`;
  return h.v ? `<button type="button" class="wbhand wb" data-wbart="${wbEsc(wbSlug(h.art))}">${body}</button>` : `<div class="wbhand wb">${body}</div>`;
}
function wbCoordHtml(ref){
  const st = wbS(), p = st.fnpage[ref + ":coordination"], steps = wbStepsHtml(ref, "Coordination");
  if (!p){ wbLoadFnPage(ref, "coordination"); return dpSkel() + steps; }
  if (p.failed) return dpQuiet("Could not read") + steps;
  const co = p.j2 || {}, tt = co.timetable || [], node = p.node || {}, alarms = co.alarms || [];
  const today = (co.ties || []).filter(t => t.today), chain = co.chain || {};
  const line = [node.word, node.why || node.line].filter(Boolean).join(" · ");
  const head = `<div class="wbcohead wb">${typeof wb2Mark === "function" ? wb2Mark("coordination") : ""}<b>Coordination</b>` +
    (alarms.length ? `<b class="dpfnb block" aria-hidden="true">!</b>` : "") + wbDot(WB_NODE_DOT[node.state] || "off") +
    `<span>${wbEsc(line)}</span></div>`;
  const left = (co.left_out || []).length ? `<div class="dpchk wbttl">Left out of the plan: ${wbEsc(co.left_out.map(r => r.engine +
    (r.since ? " (" + wbWhen(r.since) + ")" : "")).join(", "))}</div>` : "";
  const settled = tt.length && tt.every(r => r.state === "ran") ? dpQuiet("Nothing waiting") : "";
  const table = tt.length ? tt.map(wbTtRow).join("") + left + settled : dpQuiet("No plan yet");
  const tip = chain.of ? "The chain from " + chain.of + ": " + (chain.used || 0) + " of " + (chain.limit || 0) : "No chain yet";
  const trio = `<div class="wbtrio">` +
    dpCard("The chain", `<div title="${wbEsc(tip)}">${dpBar(Math.max(0, Math.min(1, Number(chain.share) || 0)))}</div>`) +
    dpCard("Alarms", alarms.length ? alarms.map(a => dpRunRow(a.engine || "Alarm", a.text, "block")).join("") : dpQuiet("None")) +
    dpCard("Ties", today.length ? today.map(t => dpRunRow(t.said, [t.why, wbWhen(t.at)].filter(Boolean).join(" · "), "ok")).join("") : dpQuiet("None today")) +
    `</div>`;
  return `<div class="wbs7 wb">` + head + dpCard("Timetable", table) +
    dpCard("Who makes it, who reads it", (co.handoffs || []).length ? co.handoffs.map(wbHandRow).join("") : dpQuiet("Nothing filed yet")) + trio +
    `<details class="wbfold wb"><summary>The function page</summary>${wbFnPageHtml(ref, "coordination")}</details></div>` + steps;
}

/* ── the engine card: the motor folded in, and the five beside it (PRD M4.7, screen S17) ──
   The motor's facts are the engine's own: its slot in Coordination's timetable, whether each slot ran once, its window
   and today's spend as a bar. Then what each of the five is doing to it now, one sentence each, read off the record
   (functions_view.engine_card); a function's chip opens its pane. Status is a word and a dot, never a colour alone. */
const WB_ENG_HEAD = { running: "running", turn: "its turn", ran: "ran", stopped: "stopped where it was", left_out: "left out of the plan" };
function wbEngHeadHtml(name, card){
  if (!card) return "";
  const h = card.head || {};
  let said = WB_ENG_HEAD[h.state] || h.word || "";
  if (h.state === "waits") said = /^waits\b/.test(h.why || "") ? wbCap(h.why) : "Waits: " + (h.why || "");
  const bits = [said, h.state === "running" && h.round ? "Round " + h.round : "",
                (h.state === "running" || h.state === "turn") && h.at ? "since " + wbWhen(h.at) : (h.state === "ran" && h.at ? wbWhen(h.at) : "")];
  const dot = h.state === "waits" ? wbTtDot(h) : (WB_TT_DOT[h.state] || "off");
  return `<div class="wbenghead wb"><b>${wbEsc(name)}</b><span class="dpchk">engine</span>${wbDot(dot)}<span>${wbEsc(bits.filter(Boolean).join(" · "))}</span></div>`;
}
function wbEngMotorHtml(card){
  const mo = card.motor || {};
  return dpCard("Motor", `<div class="wbfive wb"><span class="dpk">Slot</span>${wbDot(mo.once ? "ok" : "block")}` +
    `<span>${wbEsc([mo.slot, mo.says, "window " + mo.window_min + " min"].filter(Boolean).join(" · "))}</span>` +
    `<span title="Today">${dpBar(Math.max(0, Math.min(1, Number(mo.today) || 0)))}</span></div>`);
}
function wbEngFiveHtml(card){
  const rows = (card.five || []).map(r => {
    const fn = String(r.fn || "").toLowerCase();
    const said = r.says + (r.at ? " at " + wbWhen(r.at) : "");
    return `<div class="wbfive wb"><button type="button" class="wbfivefn fn-${wbEsc(fn)} wb" data-dptab="${wbEsc(fn)}">` +
      `${typeof wb2Mark === "function" ? wb2Mark(fn) : ""}${wbEsc(r.fn)}</button>${wbDot(r.state)}<span>${wbEsc(said)}</span>` +
      `<span>${r.share === null || r.share === undefined ? "" : dpBar(Math.max(0, Math.min(1, Number(r.share) || 0)))}</span></div>`;
  }).join("");
  return dpCard("With the five functions", rows || dpQuiet("Not read yet"));
}

/* ── the five systems' own state, under the function cards ────────────────── */
/* What Identity holds, from the record (the map read; PRD M1.7, acceptance line 1), on a department on the engine
   runtime whose registry department card is left out (20-dept.js dpRuntimeFnHtml): the goal and the done-when, and the
   rules, each with its tag as a chip in the pane's word, as S5 says them (a refuse rule reads never), the lines as the
   record has them and never rewritten. Identity's page draws these from its own record on top (S5, M3.7), so they are
   drawn here only once that page is read and carries no record of its own, never twice and never on a department the
   registry card still draws. The owner is on Control, once. */
function wbIdHoldsHtml(m){
  const p = wbS().fnpage[m.ref + ":identity"];
  if (!wbRt(m) || !p || wbIdRecord(p)) return "";
  const rules = (m.rules || []).filter(r => r && (r.line || r.text));
  return dpCard("The department", `<div class="dpid">` + dpCell("Goal", m.goal ? dpBig(m.goal) : dpQuiet("No goal yet")) +
      dpCell("Done when", m.done ? dpBig(m.done) : dpQuiet("No done line yet")) + `</div>`) +
    dpCard("Rules", rules.length ? rules.map(r => wbIdRuleHtml({ tag: r.tag, line: r.line || r.text })).join("") : dpQuiet("No rules yet"));
}
function wbFnExtra(tab, m){
  if (!m) return "";
  const engs = m.engines || [];
  /* on the engine runtime a function is an engine too: its own steps, each on
     its rung, under the state the card already shows */
  const steps = wbRt(m) ? wbStepsHtml(m.ref, tab.charAt(0).toUpperCase() + tab.slice(1)) : "";
  if (tab === "identity"){
    /* what Identity holds, then the department's control, in the owner's words: it runs itself within the owner's
       rules, or the owner holds it */
    return wbIdHoldsHtml(m) + dpCard("Control", `<div class="dpengines">` + dpKV("Control", m.control === "granted" ? "Runs within your rules" : "Held by you", "") +
        dpKV("Owner", m.owner, "Not named") + dpKV("Stop", m.stopped ? "Stopped" : "Running", "") + `</div>`) +
      dpCard("Autonomy windows", engs.map(e => dpRunRow(e.name, "", "", dpBar(Math.min(1, (e.window_min || 0) / 30)))).join("")) +
      dpCard("Stamped by rule", (m.recent || []).filter(r => r.engine === "Identity").map(r => wbRunRow(r)).join("") || dpQuiet("Nothing yet")) +
      steps;
  }
  /* Priority prices and holds the budget; who goes first is Coordination's, so the queue is on Coordination's card
     (PRD M4.6, S-05) */
  if (tab === "priority"){
    return dpCard("Envelopes", engs.map(e => dpRunRow(e.name, "", "", dpBar(Math.min(1, ((e.envelope || {}).used_calls || 0) / ((e.envelope || {}).calls || 1))))).join("")) +
      (wbRt(m) ? wbLimitsHtml(m.ref) : "") +
      steps;
  }
  if (tab === "coordination"){
    return dpCard("Timetable", engs.map(e => dpRunRow(e.name, e.slot, "")).join("")) +
      dpCard("Queue", engs.map(e => dpRunRow(e.name, e.state === "Running" ? "Running" : (e.state === "Waits" ? "Waits for the stamp" : e.slot), wbEngDot(e))).join("")) +
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
  /* a blocked card stands at the top of the pane of the function that caused it (S10, PRD M3.7) */
  const cards = wbRt(m) && WB_FUNCS.indexOf(tab) >= 0 ? wbOpenCards(ref, tab) : "";
  /* Coordination's pane opens on its timetable (PRD M4.7, S7); its page folds under it */
  if (wbRt(m) && tab === "coordination") return cards + wbCoordHtml(ref);
  /* on the engine runtime the card opens on the function's page (PRD M1.7), its own state under it */
  return cards + (wbRt(m) && WB_FUNCS.indexOf(tab) >= 0 ? wbFnPageHtml(ref, tab) : "") + wbFnExtra(tab, m);
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
/* Settings > Instructions (PRD A1.16, S16): each function's version 1 is one agent whose instructions are typed fields of
   the interface, kept in groups as its page names them. A card for each group, its lead line as the title; in it each part
   with the fields the owner may change: the words in use, a mark for as shipped or the owner's own, and Change. Under a
   part two quiet notes say, in words, what the app fills in and what the part answers with; the shape of an answer is the
   app's and is never shown or editable here. Change opens a sheet (a textarea with a count of its length, or a list
   editor for skills); Send files the one ask Identity puts to the owner, and nothing changes until the stamp: until then
   the field says it waits, beside the amber mark. A part no run reads says so, so a change to it is read as the owner's
   note; an earlier whole-file change shows once as kept as a note. Names only, never where anything lives.

   Before the interface's typed fields arrive (a read whose instructions are the first design's files) the files are listed
   as they were: wbInsFilesHtml, with the sheet and the Send of that design (an ask {fn, file, text}). */
const WB_INS_NOT_READ = "In this version the code makes this choice, so no run reads these words yet";
const WB_INS_FIELDS = { task: "the task", guidance: "the guidance", text: "the words", items: "the list" };
const WB_INS_OWN = { "does.text": "what it does", "skills.items": "the skills", "note.text": "the note" };
const WB_INS_WAIT = "your change waits for your stamp";
function wbInsLabel(part, field){ return WB_INS_OWN[part + "." + field] || WB_INS_FIELDS[field] || String(field); }
/* the typed fields, or the first design's files */
function wbInsHtml(fn, v){
  const rows = v.instructions || [];
  if (!rows.length) return "";
  return rows[0] && rows[0].parts ? rows.map(g => wbInsGroupHtml(fn, g)).join("") : wbInsFilesHtml(fn, rows);
}
function wbInsFilesHtml(fn, rows){
  return dpCard("Instructions", rows.map(r => `<div class="wbins"><b>${wbEsc(r.file)}</b><span class="wbinslead">${wbEsc(r.lead)}</span>` +
    (r.read === false ? `<span class="wbchip" title="${wbEsc(WB_INS_NOT_READ)}">a note: no run reads it yet</span>` : "") +
    (r.waits ? `<span class="wbinsnote"><i class="wbinsq">?</i>${WB_INS_WAIT}${r.waits.at ? " · " + wbEsc(wbWhen(r.waits.at)) : ""}</span>`
             : wbChip(r.as_shipped ? "as shipped" : "your words") + wbBtn("Change", `data-wbins="${wbEsc(r.file)}" data-wbinsfn="${wbEsc(fn)}"`)) +
    `</div>`).join(""));
}
/* the words in use as one line of a row, as the read says them in the owner's words (`shown`); else a list read as its items,
   a text with its lines run together */
function wbInsShown(f){
  if (typeof f.shown === "string") return f.shown;
  return (Array.isArray(f.value) ? f.value.join("; ") : String(f.value == null ? "" : f.value)).replace(/\s+/g, " ").trim();
}
function wbInsFieldHtml(fn, g, p, f){
  const open = `data-wbins="change" data-wbinsfn="${wbEsc(fn)}" data-wbinsgroup="${wbEsc(g.group)}" data-wbinspart="${wbEsc(p.part)}" data-wbinsfield="${wbEsc(f.field)}"`;
  return `<div class="wbins"><span class="wbinsf">${wbEsc(wbInsLabel(p.part, f.field))}</span><span class="wbinslead">${wbEsc(wbInsShown(f))}</span>` +
    (f.waits ? `<span class="wbinsnote"><i class="wbinsq">?</i>${WB_INS_WAIT}${f.waits.at ? " · " + wbEsc(wbWhen(f.waits.at)) : ""}</span>`
             : wbChip(f.as_shipped ? "as shipped" : "your words") + wbBtn("Change", open)) + `</div>`;
}
function wbInsPartHtml(fn, g, p){
  const said = (words, list) => (list && list.length) ? `<div class="dpchk">${words}: ${list.map(wbEsc).join(", ")}</div>` : "";
  return `<div class="wbinsp"><div class="wbinsh"><b>${wbEsc(p.label || p.part)}</b>` +
    (p.read === false ? `<span class="wbchip" title="${wbEsc(p.note || WB_INS_NOT_READ)}">a note: no run reads it yet</span>` : "") + `</div>` +
    (p.fields || []).map(f => wbInsFieldHtml(fn, g, p, f)).join("") + said("filled by the app", p.inputs) + said("answers with", p.answers) + `</div>`;
}
function wbInsGroupHtml(fn, g){
  const kept = g.kept ? `<div class="wbinsk">${wbChip("kept as your note")}<span class="dpchk">${g.kept.at ? wbEsc(wbWhen(g.kept.at)) : ""}</span></div>` : "";
  return dpCard(g.lead || g.group, kept + (g.parts || []).map(p => wbInsPartHtml(fn, g, p)).join(""));
}
/* a field of the read, with its group and part, or null */
function wbInsFind(ref, fn, group, part, field){
  const v = wbS().steps[ref + ":" + wbCap(fn)], gs = (v && v.instructions) || [];
  for (const g of gs){
    if (g.group !== group) continue;
    for (const p of g.parts || []){
      if (p.part !== part) continue;
      for (const f of p.fields || []) if (f.field === field) return { g, p, f };
    }
  }
  return null;
}
/* The words against the field's bounds, as one answer: whether they may be sent, the count to show, and why not. A text
   is at most `max` long and has some words; a list is at most `max_items` long, each at most `max`, with at least one. */
function wbInsCheck(s){
  if (s.type === "list"){
    const items = (s.items || []).map(x => String(x == null ? "" : x)), kept = items.filter(x => x.trim());
    const long = items.some(x => x.length > s.max), full = items.length > (s.max_items || Infinity);
    return { ok: !long && !full && kept.length > 0, over: long || full, line: items.length + " of " + (s.max_items || "no limit"),
             why: long ? "an item is longer than " + s.max + " characters" : (full ? "too many items" : (kept.length ? "" : "add at least one item")) };
  }
  const n = String(s.text == null ? "" : s.text).length, empty = !String(s.text == null ? "" : s.text).trim();
  return { ok: !empty && n <= s.max, over: n > s.max, line: n + " of " + s.max + (n > s.max ? ": too long" : ""),
           why: empty ? "Say what the words should be" : (n > s.max ? "These words are longer than " + s.max + " characters" : "") };
}
/* an error as the owner reads it: the server's plain sentence, without the route apiPost appends to it */
function wbInsPlain(e){
  const m = String((e && e.message) || e || "").replace(/\s*\((?:\/[^)\s]*)\s*->\s*\d+\)\s*$/, "").trim();
  return m && !/^\/\S+ -> \d+$/.test(m) ? m : "Sutra could not take that; try again";
}
function wbInsItemRow(s, i, x){
  const over = String(x).length > s.max;
  const b = (word, what, off) => wbBtn(word, `data-wbins="${what}" data-wbinsi="${i}" aria-label="${wbEsc(word + " item")}"${off ? " disabled" : ""}`);
  return `<li class="wbinsit"><input type="text" data-wbinsitem="${i}" value="${wbEsc(x)}" aria-label="${wbEsc("item " + (i + 1))}" spellcheck="false">` +
    `<span id="wbins-n${i}" class="wbinscount${over ? " over" : ""}">${String(x).length} of ${s.max}</span>` +
    b("Up", "up", i === 0) + b("Down", "down", i === s.items.length - 1) + b("Remove", "rm", false) + `</li>`;
}
function wbInsTypedSheetHtml(s){
  const c = wbInsCheck(s), title = wbCap(s.fn) + " · " + s.part + " · " + s.label;
  const body = s.type === "list"
    ? `<label>${wbEsc(wbCap(s.label))}</label><ol class="wbinslist">${s.items.map((x, i) => wbInsItemRow(s, i, x)).join("")}</ol>` +
      `<div class="wbinsadd">${wbBtn("Add", `data-wbins="add"${s.items.length >= (s.max_items || Infinity) ? " disabled" : ""}`)}</div>`
    : `<label for="wbins-text">${wbEsc(wbCap(s.label))}</label>` +
      `<textarea id="wbins-text" data-wbinstext="1" rows="${s.multiline ? 12 : 3}" spellcheck="false">${wbEsc(s.text)}</textarea>`;
  return `<div class="wbscrim wb" data-wbins="close"></div><div class="o2sheet wbsheet wbinssheet wb" role="dialog" aria-label="${wbEsc("Change " + title)}">` +
    `<h4>${wbEsc(title)}</h4>${s.lead ? `<div class="o2quiet dpq">${wbEsc(s.lead)}</div>` : ""}${body}` +
    `<div id="wbins-count" class="wbinscount${c.over ? " over" : ""}">${wbEsc(c.line)}</div>` +
    (s.error ? `<div class="o2err wbinserr" role="alert">${wbEsc(s.error)}</div>` : "") +
    `<div class="o2acts2">${wbBtn(s.busy ? "Sending" : "Send", `id="wbins-send" data-wbins="send"${s.busy || !c.ok ? " disabled" : ""}`, "dpstamp")}` +
    wbBtn("Cancel", `data-wbins="close"`) + `</div></div>`;
}
function wbInsSheetHtml(){
  const s = wbS().ins;
  if (!s) return "";
  if (s.group !== undefined) return wbInsTypedSheetHtml(s);
  const title = wbCap(s.fn) + " · " + s.file;
  return `<div class="wbscrim wb" data-wbins="close"></div><div class="o2sheet wbsheet wbinssheet wb" role="dialog" aria-label="${wbEsc("Change " + title)}">` +
    `<h4>${wbEsc(title)}</h4>` +
    `<label for="wbins-text">Instructions</label><textarea id="wbins-text" data-wbinstext="1" rows="16" spellcheck="false">${wbEsc(s.text)}</textarea>` +
    `<div class="o2acts2">${wbBtn(s.busy ? "Sending" : "Send", `data-wbins="send"${s.busy ? " disabled" : ""}`, "dpstamp")}` +
    wbBtn("Cancel", `data-wbins="close"`) + (s.error ? `<span class="o2err">${wbEsc(s.error)}</span>` : "") + `</div></div>`;
}
function wbInsPaint(){
  let host = document.getElementById("wbins-sheet");
  if (!host){ host = document.createElement("div"); host.id = "wbins-sheet"; document.body.appendChild(host); }
  host.innerHTML = wbInsSheetHtml();
}
/* While the owner types, the count and Send follow the words without the sheet being painted again (a paint would take
   the caret out from under them) */
function wbInsSync(){
  const s = wbS().ins;
  if (!s || s.group === undefined || typeof document === "undefined" || !document.getElementById) return;
  const c = wbInsCheck(s), line = document.getElementById("wbins-count"), send = document.getElementById("wbins-send");
  if (line){ line.textContent = c.line; line.className = "wbinscount" + (c.over ? " over" : ""); }
  if (send) send.disabled = !!s.busy || !c.ok;
  if (s.type === "list") (s.items || []).forEach((x, i) => {
    const n = document.getElementById("wbins-n" + i);
    if (n){ n.textContent = String(x).length + " of " + s.max; n.className = "wbinscount" + (String(x).length > s.max ? " over" : ""); }
  });
}
function wbInsOpen(ref, fn, file){
  const v = wbS().steps[ref + ":" + wbCap(fn)];
  const r = ((v && v.instructions) || []).filter(x => x.file === file)[0];
  if (!r) return;
  wbS().ins = { ref, fn, file, text: r.text || "", busy: false, error: null };
  wbInsPaint();
}
function wbInsOpenField(ref, fn, group, part, field){
  const hit = wbInsFind(ref, fn, group, part, field);
  if (!hit || hit.f.waits) return;
  const f = hit.f, list = f.type === "list";
  wbS().ins = { ref, fn, group, part, field, type: f.type, max: f.max, max_items: f.max_items, multiline: !!f.multiline, lead: hit.g.lead,
                label: wbInsLabel(part, field), text: list ? "" : String(f.value == null ? "" : f.value),
                items: list ? (f.value || []).map(String) : null, busy: false, error: null };
  wbInsPaint();
}
/* the list editor's own buttons: add an item, remove one, move one up or down */
function wbInsEdit(what, i){
  const s = wbS().ins;
  if (!s || s.type !== "list") return;
  const items = s.items;
  if (what === "add" && items.length < (s.max_items || Infinity)) items.push("");
  else if (what === "rm" && i >= 0 && i < items.length) items.splice(i, 1);
  else if ((what === "up" && i > 0) || (what === "down" && i < items.length - 1)){
    const j = what === "up" ? i - 1 : i + 1, t = items[i]; items[i] = items[j]; items[j] = t;
  }
  s.error = null;
  wbInsPaint();
}
async function wbInsSend(){
  const st = wbS(), s = st.ins;
  if (!s || s.busy) return;
  if (s.group !== undefined){
    const c = wbInsCheck(s);
    if (!c.ok){ s.error = c.why; wbInsPaint(); return; }
    s.busy = true; s.error = null; wbInsPaint();
    try {
      await apiPost(wbUrl(s.ref, "instructions"), { fn: s.fn, group: s.group, part: s.part, field: s.field,
                                                    value: s.type === "list" ? s.items.map(x => String(x).trim()).filter(Boolean) : s.text });
      st.ins = null; wbInsPaint();
      wbLoadSteps(s.ref, wbCap(s.fn), true);            /* the field reads that the change waits for the stamp */
    } catch (e) {
      s.busy = false; s.error = wbInsPlain(e); wbInsPaint();
    }
    return;
  }
  if (!String(s.text || "").trim()){ s.error = "Say what the instructions should be"; wbInsPaint(); return; }
  s.busy = true; s.error = null; wbInsPaint();
  try {
    await apiPost(wbUrl(s.ref, "instructions"), { fn: s.fn, file: s.file, text: s.text });
    st.ins = null; wbInsPaint();
    wbLoadSteps(s.ref, wbCap(s.fn), true);            /* the row reads that the change waits for the stamp */
  } catch (e) {
    s.busy = false; s.error = (e && e.message) || String(e); wbInsPaint();
  }
}
/* ── what the interface says it runs: GET /layers (PRD A1.18, A1.23) ─────────────────────────────────────────
   The schema version, the implementation each layer runs and Root's standards in their words, read once for the pane that
   asks (a function's Settings, Root's settings) and kept; a read that failed is kept as failed and is not asked again, so
   the pane says Not read yet instead of reading on every paint. */
async function wbLoadLayers(ref){
  const L = wbS().layers || (wbS().layers = {});
  if (L[ref] !== undefined) return;                    /* undefined: not asked; null: on its way; { failed }: it could not be read */
  L[ref] = null;
  try { L[ref] = await apiGet(wbUrl(ref, "layers")); } catch (e) { L[ref] = { failed: true }; }
  dpRender();
}
function wbLayers(ref){
  const L = wbS().layers || (wbS().layers = {});
  if (L[ref] === undefined) wbLoadLayers(ref);
  return L[ref] && !L[ref].failed ? L[ref] : null;
}
/* Root's settings (S18): the standards every plan meets, read only, in the order the app keeps them, with the line that
   says they are part of how the app is built. There is no Change: they move only with a new version of the app. */
/* a function's Settings head (A1.23): one quiet line, Runs version N, N being the number after /v in the pin of the
   function's layer; nothing until the read has come, so the head never says a version it does not know */
function wbRunsLine(ref, fn){
  const L = wbLayers(ref), m = /\/v(\d+)$/.exec(String(((L && L.pins) || {})[fn] || ""));
  return m ? dpQuiet("Runs version " + m[1]) : "";
}
const WB_STANDARDS_LINE = "These are part of how the app is built; they change only with a new version of the app.";
function wbStandardsHtml(ref){
  const L = wbLayers(ref), std = (L && Array.isArray(L.standards)) ? L.standards : [];
  return dpCard("Standards every plan meets", std.length
    ? std.map(x => `<div class="dpfline">${wbEsc(x.says)}</div>`).join("") + dpQuiet(WB_STANDARDS_LINE) : dpQuiet("Not read yet"));
}

function wbSettingsHtml(ref, fn){
  const st = wbS(), m = st.map[ref], name = wbCap(fn), v = st.steps[ref + ":" + name];
  if (!v){ wbLoadSteps(ref, name); return dpSkel(); }
  if (v.failed) return dpQuiet("Could not read");
  const pr = st.steps[ref + ":Priority"];
  if (!pr) wbLoadSteps(ref, "Priority");
  const lim = ((pr && pr.limits) || []).filter(l => l.engine === name)[0];
  const tpl = (typeof dpTemplateLine === "function") ? dpTemplateLine(fn) : "";
  /* the version the function runs, then S16: the Instructions, then the Template and today's limit side by side */
  return wbRunsLine(ref, fn) + wbInsHtml(fn, v) + `<div class="wbpair">` + dpCard("Template", tpl || dpQuiet("Not read yet")) +
    (lim ? dpCard("Limit", wbLimitRow(ref, lim)) : "") + `</div>` +
    wbLadderHtml(ref, name, v.numbers || {}) +
    (fn === "identity" ? wbHostHtml(ref, m) : "") +
    wbStartHtml(v) +
    ((v.hears || []).length ? dpCard("Hears", `<div class="wbstep">${v.hears.map(h => wbChip(h)).join("")}</div>`) : "") +
    wbTableHtml(v);
}
/* 20-dept.js asks this before it draws a function's pane: on the engine runtime the pane is the function's page and
   its own state, read from the runtime record, and the registry's cards are not drawn under it (PRD M1.7) */
function wbFnRuntime(ref){
  if (!wbIs(ref)) return false;
  const m = wbS().map[ref];
  if (!m){ wbLoadMap(ref); return false; }
  return wbRt(m);
}
/* 20-dept.js asks this before it reads one of the registry's five function routes (GET /api/dept/{ref}/identity,
   adaptation, priority, coordination and audit; PRD M10.2: one API family for runtime departments). True for a
   department the website does not run on the engine runtime and for one it knows nothing of, whose cards are the
   registry's. False for one that runs on it, whose pane is drawn from /api/native and /j2 and never from those cards;
   and false while the answer is not in -- the list of departments or the map is still being read -- when the paint
   that follows asks again. wbIs starts the read of the list, and wbLoadMap the map's, so nothing here waits on its own. */
function wbFnReadsRegistry(ref){
  const st = wbS();
  if (!wbIs(ref)) return st.refs !== null && !st.refsBusy;
  const m = st.map[ref];
  if (!m){ wbLoadMap(ref); return false; }
  return !wbRt(m);
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
  /* 25-j2view.js: Settings and records, the classic list with a way back to the J2 page */
  if (tab === "records" && typeof j2vRecordsHtml === "function") return dpViewerShell("Settings and records", j2vRecordsHtml(n), "wb");
  /* the Map and the Board of the second design, when the switch is on; null hands the rest back to this file */
  if (wbV2() && wbRt(m) && typeof wb2Viewer === "function"){ const own = wb2Viewer(n); if (own) return own; }
  /* All five (PRD M1.8, S2): 24-functions.js draws the five as one system */
  if (tab === "five" && wbRt(m) && typeof fvAllHtml === "function") return dpViewerShell("All five", fvAllHtml(n, m), "wb fv");
  if (tab === "chat" && wbRt(m)) return dpViewerShell("Chat", wbChatHtml(n, m), "wb");
  if (tab === "map") return dpViewerShell("Map", wbMapHtml(n, m), "wb");
  if (tab === "status") return dpViewerShell("System status", wbStatusHtml(n, m), "wb");
  /* the first build's Motor screen; on the engine runtime the motor folds into each engine's card (PRD M4.7, S17) */
  if (tab === "motor" && !wbRt(m)) return dpViewerShell("Motor", wbMotorHtml(n, m), "wb");
  if (tab === "board" && wbRt(m)) return dpViewerShell("Board", wbBoardHtml(n), "wb");
  if (tab === "activity" && wbRt(m)){
    dpLoadJ2(n.ref);
    dpLoadActivity(n.ref);
    return dpViewerShell("Agent activity", dpActivityHtml(), "wb");
  }
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

/* ── the organisation: Root's chat, and nothing else ──────────────────────
   Founder, 2026-09-29: "The UI wherein a particular person chats with root,
   and it creates a department, but at the organization level, only a chat is
   shown, and root is not shown." The organisation row is the chat with Root,
   headed by the organisation's name; Root's own settings sit behind one
   button and are a pane, never a chat (the design of record:
   holding/website/native/preview/org.html). Null for an organisation without
   a Root on the runtime: 19-org2.js paints it as before. The clicks and the
   box speak for Root, so Root is the department the screen holds selected. */
function wbOrgHtml(n, d){
  const root = d && d.lifted && d.lifted.get(n.ref);
  if (!root || !wbIs(root.ref)) return null;
  const st = wbS(), m = st.map[root.ref];
  wbTick();
  if (typeof dpSelect === "function" && dpS().sel !== root.ref) dpSelect(root.ref);
  if (!m){ wbLoadMap(root.ref); return dpViewerShell(n.name, st.err[root.ref] ? dpQuiet("Could not read") : dpSkel(), "wb"); }
  const rn = { ref: root.ref, name: n.name };
  const pane = st.tab[root.ref] === "root";
  const head = `<div class="wb2head"><b>${wbEsc(n.name)}</b>${m.stopped ? `<span class="dpst paused">Off</span>` : ""}` +
    (pane ? "" : wbBtn(WB_HELPER + " settings", `data-wbtab="root"`)) + `</div>`;
  return dpViewerShell(pane ? WB_HELPER : "Chat", head + (pane ? wbRootPaneHtml(rn, m) : wbChatHtml(rn, m)), "wb");
}
/* Root's pane: what its record holds, in rows; the one switch; a way back */
function wbRootPaneHtml(n, m){
  const st = wbS(), c = st.chat[n.ref] || {};
  if (!st.chat[n.ref]) wbLoadChat(n.ref);
  const row = (label, body, cls) => `<div class="dprow"><span class="dpdot${cls ? " " + cls : ""}"></span><span>${wbEsc(label)}<div class="dpchk">${body}</div></span></div>`;
  const rules = (m.rules || []).map(r => wbEsc(typeof r === "string" ? r : (r.line || r.text || ""))).filter(Boolean);
  const made = (c.departments || []).map(x => wbDeptChip(x.ref, x.name)).join("");
  const sw = m.stopped ? wbBtn("Start", `data-wbresume="1"`, "dpstamp") : wbBtn("Stop", `data-wbstop="1"`);
  return dpCard("Root",
    row("What it does", wbEsc(m.goal || ""), "ok") +
    row(m.stopped ? "Off" : "On", (m.stopped ? "makes no department until started " : "makes departments when asked ") + sw, m.stopped ? "off" : "ok") +
    row("Rules", rules.length ? rules.join("; ") : "none yet", rules.length ? "ok" : "") +
    row("Departments it has made", made || "none yet", made ? "ok" : "")) +
    wbStandardsHtml(n.ref) +
    `<div>${wbBtn("Back to the chat", `data-wbtab="chat"`)}</div>`;
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
    `<label for="wbfgoal">The first department</label><textarea id="wbfgoal" data-wbfield="goal" rows="3" placeholder="What should Root set up first? Say what it is for, in your words">${wbEsc(f.goal)}</textarea>` +
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
    /* the organisation is where the person goes on: its row is Root's chat, where the ask for the first department is
       (founder, 2026-09-29: at the organisation level only a chat is shown); Root itself when the tree has not learnt yet */
    st.tab[out.root] = "chat";
    if (typeof o2Select === "function") o2Select(wbRootOf(out.org) ? out.org : out.root);
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
    "[data-wbchip],[data-wbthread],[data-wbladder],[data-wbhost],[data-wbopen],[data-wblive],[data-wbopenart],[data-wbsay],[data-wbins],[data-wbfvretry]," +
    "[data-wbanswer],[data-wbjust],[data-wboption]";
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
    /* Settings > Instructions: Change opens the sheet, Send files the ask, Cancel closes it; the card stays open */
    if (ds.wbins !== undefined){
      ev.preventDefault(); ev.stopPropagation();
      if (ds.wbins === "close"){ st.ins = null; wbInsPaint(); }
      else if (ds.wbins === "send") wbInsSend();
      else if (ds.wbins === "change"){ if (ref && wbIs(ref)) wbInsOpenField(ref, ds.wbinsfn, ds.wbinsgroup, ds.wbinspart, ds.wbinsfield); }
      else if (/^(add|rm|up|down)$/.test(ds.wbins)) wbInsEdit(ds.wbins, ds.wbinsi === undefined ? -1 : Number(ds.wbinsi));
      else if (ref && wbIs(ref)) wbInsOpen(ref, ds.wbinsfn, ds.wbins);
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
    /* one of this file's entries is opening: none of 20-dept.js's rows stays lit; words said inside a function's chat
       keep the person there (found live 2026-09-29: Send in Priority's chat landed on the department's Chat) */
    const inFn = ds.wbask !== undefined && String(ds.wbask).indexOf("fn:") === 0;
    if (ds.wbfn === undefined && !inFn && dpS().tab[ref] !== "now") dpS().tab[ref] = "now";
    if (ds.wbtab !== undefined){
      /* a way into the Chat with the box begun (Identity's pane: Change the goal, M3.7); the owner finishes and sends it */
      if (ds.wbfill !== undefined && !st.draft[ref + ":ask"]) st.draft[ref + ":ask"] = ds.wbfill;
      st.tab[ref] = ds.wbtab; if (ds.wbthread !== undefined) st.thread[ref] = ds.wbthread; dpRender(); return;
    }
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
    /* the live site of the department a turn is about: its Live site, previewed; from Root's chat, that department opens on it;
       the department's own tab is set too, so the next repaint keeps the preview (found live 2026-09-29: the preview gave
       way to the Human Sutra page on the next tick, the row lit was Brief) */
    if (ds.wblive !== undefined || ds.wbopenart !== undefined){
      const dref = (ds.wblive !== undefined ? ds.wblive : ds.wbdept) || ref, slug = ds.wblive !== undefined ? "live-site" : ds.wbopenart;
      st.tab[dref] = "art"; st.sel[dref] = slug; st.pane[dref + ":" + slug] = "preview"; st.sel[dref + ":" + slug + ":v"] = "";
      if (typeof dpS === "function") dpS().tab[dref] = "now";
      if (dref !== ref && typeof o2Select === "function") o2Select(dref); else dpRender();
      return;
    }
    if (ds.wbthread !== undefined){ st.thread[ref] = ds.wbthread; dpRender(); return; }
    /* the five functions' read failed: Try again reads it once more (a read, never a write) */
    if (ds.wbfvretry !== undefined){ delete st.fv[ref]; wbLoadFv(ref); dpRender(); return; }
    if (ds.wbdecide !== undefined){ wbPost(ref, "asks/" + encodeURIComponent(ds.wbdecide), { approve: ds.wbok === "1" }, null, ds.wbref || ref); return; }
    if (ds.wbanswer !== undefined){ wbAnswer(ref, ds.wbanswer, ds.wbref || ref); return; }
    if (ds.wbjust !== undefined){ wbAnswer(ref, ds.wbjust, ds.wbref || ref, "just do it"); return; }
    if (ds.wboption !== undefined){ wbChoose(ref, ds.wbopt, ds.wbref || ref, ds.wboption); return; }
    if (ds.wbstop !== undefined){ wbPost(ref, "stop"); return; }
    if (ds.wbresume !== undefined){ wbPost(ref, "resume"); return; }
    if (ds.wbgoal !== undefined){ const k = ref + ":goal"; wbPost(ref, "goal", { text: st.draft[k] || "" }, k); return; }
    if (ds.wbsay !== undefined){
      /* an offer's chip: its words go to the front door as the person's own, about no department */
      const m = st.map[ref];
      wbPost(ref, "ask", { text: ds.wbsay }, null, (wbRt(m) && m.root && m.root !== ref) ? m.root : ref).then(() => wbAgain(ref)); return;
    }
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
    if (ds.wbinstext !== undefined && wbS().ins){ wbS().ins.text = t.value; wbInsSync(); }
    if (ds.wbinsitem !== undefined && wbS().ins && wbS().ins.items){ wbS().ins.items[Number(ds.wbinsitem)] = t.value; wbInsSync(); }
  });
  /* Cmd+Enter (Ctrl+Enter) in the box of Identity's question sends the answer */
  document.addEventListener("keydown", (ev) => {
    const t = ev.target, ds = (t && t.dataset) || {};
    if (S.screen !== "org2" || (ds.wbqid === undefined && ds.wboptid === undefined) || ev.key !== "Enter" || !(ev.metaKey || ev.ctrlKey)) return;
    const ref = S.dp && S.dp.sel;
    if (!ref || !wbIs(ref)) return;
    ev.preventDefault();
    if (t.value !== undefined && ds.wbdraft !== undefined) wbS().draft[ds.wbdraft] = t.value;
    if (ds.wboptid !== undefined){ wbChoose(ref, ds.wboptid, ds.wboptref || ref, "words"); return; }
    wbAnswer(ref, ds.wbqid, ds.wbqref || ref);
  });
}
