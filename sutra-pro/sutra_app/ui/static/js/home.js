/* home.js - the controller of the Home page (work package UI-7; docs/design/ui.md sections 6.6, 7, 8, 9 and 10; S1-contracts-03, S1-contracts-08,
   S3-web-06, S3-web-13, S4-fnodes-12; D18).

   Home is the J2 Simple skeleton (home.html). The left column is the org chat, the owner's talk with the chat agent: the Root node's one rolling session
   cs_org, so there is no task picker. The right column is J2's preview slot: the "Needs you" strip and one pane at a time, the Workflow graph, the Org
   chart or Settings, chosen from the rail. Everything it draws comes from the pure modules (ChatView, SettingsView) or from the views of UI-5 and UI-6
   (GraphView, OrgChartView, NodePanel); this file fetches, keeps them current from the event stream and handles clicks.

   Functions (docs/design/ui.md 6.6): boot, loadAll, renderChat, send, answerNeeds, selectPane, renderRail, renderNeeds, onEvent, themeApply, barSet,
   renderSettings, saveEngine, testConnector, signIn. They are on window.HomePage with the state (HomePage.state()), so a test can look at both.

   Reads: GET /api/chats/cs_org and its messages, /api/chart, /api/chart/changes, /api/graph?level=chart, /api/departments, /api/needs-you, /api/health,
   /api/engine/settings, /api/heads-up, /api/find (the rail's search, team_find.js; the Org chart pane also reads /api/chart/notes). Writes (each with X-Sutra-Token, through SutraCtx.api): POST /api/chats/cs_org/messages and .../retry, POST /api/chats/{department
   session}/messages (an answer to a team's question, never to cs_org), the connector Test and Sign in calls, PUT /api/engine/settings, POST
   /api/tasks/{id}/retry (Try again, from the Heads up lane or a done card).

   Gap package attention: the strip shows how long each ask has waited and a Heads up lane (HeadsUpView); the badge, the strip's count and the tab
   title count the asks plus the problems not marked "Got it"; ChatAttention sends one desktop notice per new one while the window is not in front.

   Gap package routines-limits: GET /api/limits, GET and PUT /api/ops/attention (quiet hours and the cap the notices obey), GET/POST/PUT/DELETE /api/recurring
   and POST /api/recurring/{id}/run. The strip gains one line when the monthly limit or a plan window is near (with Continue while the guard holds work), and
   Settings gains the Limits, Notifications and Recurring work groups (LimitsView, RecurringView); a block near the end of the Settings section is the controller.

   Gap package dept-chats: every team the org chat makes has its own chat, and the chat column shows ONE chat at a time. A strip of tabs (ChatSwitch) names
   the org chat and each team's; the "Started <team>: open its chat" line of the org chat and the strip's "Answer in <team>'s chat" open a team's chat in
   the column, with the node panel's own Chat tab shown inline (#teamchat). Nothing of a team's chat is copied into the org chat.

   A classic script with one global, HomePage. It does nothing on a page that is not Home (no #sview). */
(function (root) {
  "use strict";

  const doc = root.document;
  if (!doc || !doc.getElementById("sview")) return;

  /* ---------------------------------------------------------------- small helpers */
  const $ = id => doc.getElementById(id);
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const enc = encodeURIComponent;
  const ctx = root.SutraCtx;
  const esc = ctx.esc;
  const api = ctx.api;
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const protect = (where, fn) => { try { return fn(); } catch (e) { if (root.console) root.console.error("HomePage: " + where + " failed", e); return undefined; } };

  const ORG = "cs_org";
  const PANES = ["graph", "chart", "settings"];
  const COALESCE_MS = 150;
  const POLL_MS = 2000;
  const MINUTE_MS = 60000;
  const NO_TOKEN = "This page was opened without its access token. Reload it from the app.";
  const TOO_MANY = "Too many messages are waiting. I answer them one at a time.";
  const DOWN = "The app is not responding. Try again in a moment.";
  const FAILED = "Something went wrong. Try again.";
  // J2's example briefs (j2_ui.html:141), the start page's buttons.
  const EXAMPLES = ["A website for my cafe", "A website for Sweet Crumbs Bakery in Pune: menu, cake orders, contact",
    "A website for Petal & Stem, a florist in Jaipur: bouquets, same-day delivery, wedding flowers",
    "A website for Asha Rao Photography, a wedding and portrait photographer in Mumbai: portfolio, packages, booking"];
  // The five segments of the progress bar follow chat.turn of cs_org (owner steps 1 to 5 and 7).
  const STAGES = ["Reading the org chart", "Checking the model library", "Planning", "Setting up the team", "Done"];
  const PHASE_AT = {reading_chart: 0, consulting_library: 1, planning: 2, applying: 3, handing_off: 3, done: 4};
  const PHASE_SENTENCE = {reading_chart: "Reading the org chart…", consulting_library: "Checking the model library…", planning: "Planning…",
    applying: "Setting up the team…", handing_off: "Handing the request over…", done: ""};
  const STATUS_WORDS = {idle: "idle", running: "working", waiting: "waiting", waiting_on_you: "waiting on you", fault: "problem", filed: "done", done_unchecked: "done, not checked",
    left_open: "done, with open items", not_made: "not started"};

  /* ---------------------------------------------------------------- state */
  const S = {
    cc: undefined, session: null, messages: [], lastId: 0, pending: [], localSeq: 0, answers: {}, chat: {sid: ORG, node: ""}, team: null,
    departments: [], departmentsLoaded: false, needs: [], needsLoaded: false,
    graph: null, chart: null, changes: [],
    health: null, settings: null, scope: "", errors: {}, saved: false, saving: false, conn: {test: {}, signin: null}, signer: null,
    pane: "graph", turn: {seen: false, phase: "", n: 0, active: false, resumed: false}, awaitGraph: false,
    banner: null, blocked: "", sending: false, live: "offline", theme: null, loaded: false,
    graphView: null, chartView: null, panel: null, stream: null, watch: null, values: null,
    // gap attention: the Heads up lane, the age of each ask, the "Got it" marks of this browser, the tab title and the desktop notice
    heads: [], headsLoaded: false, needsAt: 0, seen: {}, fyiMore: false, attention: null,
    scroll: {parked: false, seenId: 0, pill: 0}, own: false, drafts: undefined,          // the reader's place and the box's draft (GAP-chat-comfort)
    // gap routines-limits: the limits (strip line, Settings), the owner's quiet hours and cap, the standing tasks (LimitsView, RecurringView)
    limits: null, limitsForm: {}, notices: null, noticesForm: {}, recurring: null, recForm: {draft: null, open: {}, confirm: "", error: {}, busy: false, saved: false},
    // welcome-settings: the default-model controls (policy and the models each provider lists), the About group (version, folder, the update answer)
    policy: null, models: null, pol: {busy: false, saved: false, errors: {}}, info: null, update: {step: "idle"},
    // autoupdate: the "Check for updates automatically" setting (GET /api/ops/update-setting) and the switch's own busy flag and sentence
    auto: null, autoBusy: false, autoMsg: "",
    pillStale: false, pillSeq: 0,          // the org chat's pill is read again when its session may have moved (renderPill)
    // the front door (front_door.js): the cards being answered, a refusal per card, Done recently opened up, a send from its box, the Raw AI chat note
    front: {answering: {}, errors: {}, moreDone: false, sent: false, error: "", hookNote: ""},
  };

  /* ---------------------------------------------------------------- errors in words */
  // errorWords(e) -> {text, settings}: the sentence for an ApiError and whether the banner should link to Settings.
  function errorWords(e) {
    const status = e && Number.isInteger(e.status) ? e.status : 0;
    const code = e && typeof e.code === "string" ? e.code : "";
    const said = clean(e && e.message);
    const found = e && isObj(e.details) && Array.isArray(e.details.violations) ? e.details.violations.find(v => isObj(v) && clean(v.message) !== "") : null;
    if (status === 401 || code === "bad_token") return {text: NO_TOKEN, settings: false, blocked: true};
    if (code === "provider_unavailable" || code === "cli_missing") return {text: said || "No model is available right now.", settings: true};
    if (status === 429) return {text: TOO_MANY, settings: false};
    if (status === 0 || code === "network") return {text: DOWN, settings: false, retry: true};
    if (status === 422 && found && said) return {text: said.replace(/[.:\s]+$/, "") + ": " + clean(found.message), settings: false};     // "... refused: String should have at most 8000 characters"
    return {text: status >= 500 || !said ? FAILED : said, settings: false};
  }

  function showBanner(words) {
    S.banner = words;
    if (words && words.blocked) S.blocked = NO_TOKEN;
    renderBanner();
    renderComposer();
  }
  function clearBanner() { if (S.banner) { S.banner = null; renderBanner(); } }

  function renderBanner() {
    const el = $("sbanner");
    const b = S.banner;
    el.hidden = !b;
    ctx.paint(el, b ? "<span>" + esc(b.text) + "</span>" + (b.settings ? ' <button type="button" class="linkbtn" data-act="open-settings">Open Settings</button>' : "") +
      (b.retry ? ' <button type="button" class="linkbtn" data-act="retry-load">Retry</button>' : "") + ' <button type="button" class="linkbtn" data-act="dismiss">Dismiss</button>' : "");
  }

  /* ---------------------------------------------------------------- the data */
  // One request of a kind at a time: a call that comes while one is in flight runs once more when it ends.
  function single(fn) {
    let running = null;
    let again = false;
    const run = () => {
      if (running) { again = true; return running; }
      running = Promise.resolve().then(fn).catch(e => { handleFetchError(e); }).then(() => {
        running = null;
        if (again) { again = false; return run(); }
        return undefined;
      });
      return running;
    };
    return run;
  }

  function handleFetchError(e) {
    const w = errorWords(e);
    if (w.blocked || w.retry) showBanner(w);
    return w;
  }

  async function fetchSession() { S.session = await api.get("/api/chats/" + ORG); syncTurn(S.session); }

  // A page opened while a turn runs has no chat.turn events behind it, so the phase word of GET /api/chats/cs_org (reading, planning, building) stands in
  // for them until the first event arrives. Until then the session is read again every 2.5 s: a turn that ended before this page's event stream opened
  // does not leave the strip and the "one at a time" note on the screen.
  const TURN_WORD = {reading: "reading_chart", planning: "planning", building: "applying"};
  function syncTurn(session) {
    if (S.turn.seen && !S.turn.resumed) return;                                          // the page's own events know better
    const word = isObj(session) && hasOwn(TURN_WORD, session.phase) ? TURN_WORD[session.phase] : "";
    if (word === "" && !S.turn.resumed) return;
    S.turn.seen = true;
    S.turn.resumed = word !== "";
    S.turn.phase = word || "done";
    S.turn.active = word !== "";
    renderProgress();
    renderComposer();
    if (word !== "") watchTurn();
    else reloadMessages();
  }
  let turnTimer = null;                                                                  // one re-read at a time, however often the page loads everything again
  function watchTurn() {
    if (turnTimer !== null) return;
    turnTimer = root.setTimeout(() => { turnTimer = null; if (S.turn.resumed) fetchSession().catch(watchTurn); }, 2500);
  }

  // The org chat, oldest first. all=true reads it from the start (a message can change after it was read, such as one that turned into an error);
  // otherwise only what is newer than the last one seen.
  async function fetchMessages(all) {
    let after = all ? 0 : S.lastId;
    const fresh = [];
    for (let i = 0; i < 20; i++) {
      const page = await api.get("/api/chats/" + ORG + "/messages", {after, limit: 200});
      const got = isObj(page) && Array.isArray(page.messages) ? page.messages : [];
      fresh.push(...got);
      if (got.length < 200) break;
      after = Number.isFinite(page.next_after) ? page.next_after : got[got.length - 1].id;
    }
    mergeMessages(fresh, all);
    if (fresh.length > 0) pillMoved();
    if (S.cc && S.cc.reconcile(S.messages)) renderBar();
    renderChat();
    renderComposer();
    renderPill();
  }

  function mergeMessages(list, replace) {
    const byId = new Map(replace ? [] : S.messages.map(m => [m.id, m]));
    list.forEach(m => { if (isObj(m) && m.id !== undefined) byId.set(m.id, m); });
    S.messages = Array.from(byId.values()).sort((a, b) => a.id - b.id);
    S.lastId = S.messages.reduce((n, m) => (typeof m.id === "number" && m.id > n ? m.id : n), 0);
    S.pending = S.pending.filter(p => p.serverId === null || !S.messages.some(m => m.id === p.serverId));
  }

  async function fetchChart() {
    const [chart, changes] = await Promise.all([api.get("/api/chart"), api.get("/api/chart/changes", {limit: 50, newest: true})]);
    S.chart = chart;
    S.changes = Array.isArray(changes) ? changes : [];
    if (S.chartView) S.chartView.update(S.chart, S.changes);
  }

  async function fetchGraph() {
    const graph = await api.get("/api/graph", {level: "chart"});
    S.graph = graph;
    const nodes = isObj(graph) && Array.isArray(graph.nodes) ? graph.nodes : [];
    doc.body.classList.toggle("has-site", nodes.length > 1 || S.pane !== "graph");
    if (S.graphView) S.graphView.update(graph);
    renderSwitch();
    // The first graph with something in it after a turn takes the right pane (a phone only gets its Graph toggle).
    if (S.awaitGraph && nodes.length > 1) {
      S.awaitGraph = false;
      selectPane("graph", {reveal: false});
    }
  }

  async function fetchDepartments() {
    const list = await api.get("/api/departments");
    S.departments = Array.isArray(list) ? list : [];
    S.departmentsLoaded = true;
    renderRail();
    renderChat();
    renderFront();
    if (S.settings) paintEngine();
  }

  async function fetchNeeds() {
    const list = await api.get("/api/needs-you");
    S.needs = Array.isArray(list) ? list : [];
    S.needsLoaded = true;
    S.needsAt = Date.now();
    renderNeeds();
    renderChat();
  }

  // GET /api/heads-up: crashed or app-stopped work (Try again), teams gone quiet, work finished in 24 h. A failed read keeps the lane it had.
  async function fetchHeads() {
    try {
      const list = await api.get("/api/heads-up");
      S.heads = Array.isArray(list) ? list : [];
    } finally {
      S.headsLoaded = true;
      renderNeeds();
      renderChat();
    }
  }

  async function fetchHealth() { S.health = await api.get("/api/health"); paintConnectors(); paintModels(); }

  // GET /api/limits and /api/ops/attention (gap routines-limits): the strip line, the Settings groups, and the quiet hours and cap the notices obey. Never
  // rejects: a read that fails keeps what the page had (a page with no answer yet shows no line and sends no finished notice).
  let limitsWrites = 0;                                     // counts the owner's saves: a read that began before one ended is out of date and is dropped
  async function fetchLimits(withNotices) {
    if (!LV()) return;
    const before = limitsWrites;
    const got = await LV().load(api, {notices: withNotices !== false});
    if (before !== limitsWrites) return;
    if (got.limits) S.limits = got.limits;
    if (got.notices) S.notices = got.notices;
    renderNeeds();
    if (S.pane === "settings") { paintLimits(); paintNotices(); }
  }

  const reloadMessages = single(() => fetchMessages(true));
  const refetchMessages = SutraEvents.coalesce(single(() => fetchMessages(false)), COALESCE_MS);
  const refetchGraph = SutraEvents.coalesce(single(fetchGraph), COALESCE_MS);
  const refetchChart = SutraEvents.coalesce(single(fetchChart), COALESCE_MS);
  const refetchNeeds = SutraEvents.coalesce(single(fetchNeeds), COALESCE_MS);
  const refetchHeads = SutraEvents.coalesce(single(fetchHeads), COALESCE_MS);
  const refetchDepartments = SutraEvents.coalesce(single(fetchDepartments), COALESCE_MS);
  const refetchLimits = SutraEvents.coalesce(single(() => fetchLimits(false)), COALESCE_MS);          // after an event or a minute: the limits only

  const settled = list => Promise.allSettled(list.map(f => f()));

  // Everything Home shows, once: on load, on server.resync, and for "Retry". Each part fails on its own and keeps what it had.
  async function loadAll() {
    const results = await settled([fetchSession, () => fetchMessages(true), fetchChart, fetchGraph, fetchDepartments, fetchNeeds, fetchHealth, fetchHeads, fetchLimits]);
    const failed = results.filter(r => r.status === "rejected");
    if (failed.length === results.length) handleFetchError(failed[0].reason);
    else if (failed.length === 0) clearBanner();
    failed.forEach(r => { const w = errorWords(r.reason); if (w.blocked) showBanner(w); });
    S.loaded = true;
    renderAll();
    if (composer()) composer().resync();            // a direct turn this page did not start (a reload, another tab) gets its Stop; one the server lost (a restart) is over
    return results;
  }

  // What polling asks every 2 s when the stream is down (docs/design/ui.md 9, X4).
  function pollAll() {
    return settled([() => fetchMessages(false), fetchGraph, fetchChart, fetchNeeds, fetchDepartments, fetchHeads, () => fetchLimits(false)]);
  }

  /* ---------------------------------------------------------------- the org chat */
  const hasWritten = () => S.messages.some(m => m.role === "user") || S.pending.length > 0;

  function deptSessions() {
    const map = {};
    S.departments.forEach(d => { if (isObj(d) && d.id && d.session_id) map[d.id] = d.session_id; });
    const nodes = isObj(S.graph) && Array.isArray(S.graph.nodes) ? S.graph.nodes : [];
    nodes.forEach(n => { if (n.kind === "department" && n.chat_session_id && !map[n.id]) map[n.id] = n.chat_session_id; });
    return map;
  }

  // The answer of every card the owner has dealt with (ChatView.answersOf): what the owner clicked here, a card the server says was answered (also after
  // a reload: an approval or choice whose button was pressed), and a team question that /api/needs-you no longer lists (then the card just reads "Answered").
  const answersMap = () => root.ChatView.answersOf(S.messages, {local: S.answers, needs: S.needs, needsLoaded: S.needsLoaded});

  function startHtml() {
    if (hasWritten() || S.messages.length === 0) return "";
    return '<div class="sb team starter" data-start="true"><small>Sutra</small>Try one of these, or write your own below.' +
      '<div class="cards">' + EXAMPLES.map(t => '<button type="button" data-brief="' + esc(t) + '">' + esc(t) + "</button>").join("") + "</div></div>";
  }

  function renderChat() {
    const shown = S.messages.concat(S.pending.map(p => p.msg));
    const session = S.session || {kind: "org", writable: true, status: "active", title: "Sutra"};
    const view = {deptName: "", live: true, answers: answersMap(), deptSessions: deptSessions(), retryTasks: retryTasks()};
    const el = $("smsgs");
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    // Fluid.patchList edits the list in place: the lines that did not change are not touched, a new line enters (a long chat is not rebuilt per message)
    let changed;
    if (root.Fluid) {
      const items = root.ChatView.transcriptItems(session, shown, view);
      const start = startHtml();
      if (start !== "") items.push({key: "starter", html: start});
      changed = root.Fluid.patchList(el, items, {enter: "nmsg-in"}).changed;
    } else {
      changed = ctx.paint(el, root.ChatView.transcript(session, shown, view) + startHtml());
    }
    renderFrontLatest();
    if (!changed) return;
    follow(el, shown, near);
  }

  /* ---------------------------------------------------------------- the reader's place and the box (GAP-chat-comfort) */
  // ChatScroll: the owner's own line goes to the bottom; a reader who moved up keeps the place and the pill counts what came below; else follow.
  function follow(el, shown, near) {
    const CS = root.ChatScroll;
    const end = () => { el.scrollTop = el.scrollHeight; };
    if (!CS) { end(); if (root.requestAnimationFrame) root.requestAnimationFrame(end); return; }
    const p = CS.plan({parked: S.scroll.parked, atBottom: near, grew: true, own: S.own, newCount: CS.newCount(shown, S.scroll.seenId), pill: S.scroll.pill});
    S.own = false;
    if (p.scroll === "bottom") {
      end();
      if (root.requestAnimationFrame) root.requestAnimationFrame(() => { if (!S.scroll.parked) end(); });
    }
    S.scroll = CS.settle(S.scroll, p, CS.distance(el), CS.lastId(shown));
    renderJump();
  }

  // A follower stays at the newest line when a row under the transcript changes size (ChatScroll.pin does it too, where the page renders).
  function keepFollowing() {
    if (!root.ChatScroll || S.scroll.parked) return;
    const el = $("smsgs");
    el.scrollTop = el.scrollHeight;
  }

  function renderJump() {
    const el = $("sjump");
    if (!el || !root.ChatScroll) return;
    const html = root.ChatScroll.pillHtml(S.scroll.pill);
    ctx.paint(el, html);
    el.hidden = html === "";
  }

  function jumpLatest() {
    const CS = root.ChatScroll;
    const el = $("smsgs");
    if (!CS) return;
    S.scroll = {parked: false, seenId: CS.lastId(S.messages), pill: 0};
    renderJump();
    const how = CS.behavior(typeof root.matchMedia === "function" ? q => root.matchMedia(q) : undefined);
    if (typeof el.scrollTo === "function") el.scrollTo({top: el.scrollHeight, behavior: how});
    else el.scrollTop = el.scrollHeight;
  }

  // ChatDraft: the org chat's box keeps its words across a reload, a trip to a team page and a pane switch; only an accepted send clears them.
  const drafts = () => { if (S.drafts === undefined) S.drafts = root.ChatDraft ? root.ChatDraft.create() : null; return S.drafts; };
  const growBox = () => { if (root.ChatDraft) root.ChatDraft.grow($("sbox"), 200); };
  function clearSent(body) {
    if (drafts()) drafts().clearIf(ORG, body);
    if ($("sbox").value.trim() === body) $("sbox").value = "";
    growBox();
  }

  // The provider pill of the org chat (ABS-9): the choice also governs the chat agent (ABS-8).
  // The pill is read once, and again whenever the chat's session may have moved: a reply ends a turn, and the turn is what pins the model, the effort and
  // the provider the session runs on (the pickers wait for it: "can be chosen after your next message"), and connector.switch is the session starting on the
  // other provider. pillMoved() says so; the pill on screen stays until the new answer is in, and an older answer never replaces a newer one.
  const pillMoved = () => { S.pillStale = true; };

  async function renderPill() {
    const el = $("spill");
    const CP = root.ChatPill;
    if (!el || !CP) return;
    if (S.pillData === undefined || S.pillStale) {
      const first = S.pillData === undefined;
      const mine = ++S.pillSeq;
      S.pillStale = false;
      if (first) S.pillData = null;
      let got = null;
      try { got = await api.get("/api/chats/" + ORG + "/providers"); } catch (e) { got = null; }
      if (mine === S.pillSeq && (got !== null || first)) S.pillData = got;          // a failed read of a pill already shown keeps it
    }
    const html = S.pillData ? CP.pill(S.pillData.providers, S.pillData.chosen) : "";
    ctx.paint(el, html);
    el.hidden = html === "";
  }

  // A turn that ended may have moved the chat to the other model (the router switches on a failure): read the pill again, keeping what it shows until the answer comes.
  async function rereadPill() {
    let fresh = null;
    try { fresh = await api.get("/api/chats/" + ORG + "/providers"); } catch (e) { fresh = null; }
    if (fresh) S.pillData = fresh;
    return renderPill();
  }

  function onPillClick(e) {
    const b = e.target.closest("button[data-act=choose-provider]");
    if (!b || !root.ChatPill) return;
    const req = root.ChatPill.choiceRequest(ORG, b.dataset.provider || null);
    api.put(req.path, req.body).then(() => { S.pillData = undefined; return renderPill(); }, err => showBanner({text: clean(err && err.message) || "That model cannot answer right now.", settings: false}));
  }

  // The model list and the effort under the pill (model_pick.js): one select changed is one PUT /choice, then the pill is read again.
  function onPillChange(e) {
    const t = e.target && e.target.closest ? e.target.closest("select[data-act]") : null;
    if (!t || !root.ModelPick) return;
    const req = root.ModelPick.selectRequest(ORG, providersOf(), t.dataset.act, t.dataset.provider, t.value);
    if (!req) { S.pillData = undefined; renderPill(); return; }
    api.put(req.path, req.body).then(() => { S.pillData = undefined; return renderPill(); }, err => {
      S.pillData = undefined;
      renderPill();
      showBanner({text: clean(err && err.message) || "That model cannot be used right now.", settings: false});
    });
  }

  // The composer of the direct chat (ABS-15). "Plan with Sutra" is the staged path as it was; "Ask directly" is POST /direct on the org chat (D115): the
  // chosen model answers, streamed, with attachments and a Stop. The mode is the owner's, per page load.
  function composer() {
    // one repaint per animation frame, however many chunks of a reply arrived in it (Fluid.frame; without fluid.js it is at once, as before)
    const repaint = () => { renderBar(); renderComposer(); };
    if (S.cc === undefined) S.cc = root.ChatComposer ? root.ChatComposer.create({api, sid: ORG, mode: "team", onChange: () => (root.Fluid ? root.Fluid.frame(repaint, repaint) : repaint()), onTurnEnd: rereadPill}) : null;
    return S.cc;
  }
  const directOn = () => { const c = composer(); return c !== null && c.state().mode === "direct"; };
  const providersOf = () => (S.pillData ? S.pillData.providers : []);
  const askBlocked = () => (directOn() && S.pillData ? root.ChatComposer.askBlock(providersOf()) : "");

  function renderBar() {
    const c = composer();
    const bar = $("sbar");
    if (!c || !bar) return;
    const CC = root.ChatComposer;
    const html = CC.bar(c.state(), {labels: {team: "Plan with Sutra", direct: "Ask directly"}});
    ctx.paint(bar, html);
    bar.hidden = html === "";
    $("sstream").hidden = !CC.paintStreamRow($("sstream"), c.state(), CC.providerOf(providersOf(), S.pillData ? S.pillData.chosen : null));       // a chunk adds to the end of the row
    keepFollowing();
  }

  async function sendDirect(value) {
    const c = composer();
    const body = text(value).trim();
    if (!c || body === "") return false;
    const stuck = askBlocked();
    if (stuck !== "") { showBanner({text: stuck, settings: true}); return false; }
    clearBanner();
    const out = await c.send(body);
    if (!out.ok) return false;
    clearSent(body);
    S.own = true;
    try { await fetchMessages(false); } catch (e) { handleFetchError(e); }
    return true;
  }

  // Retry on a direct line that failed: the same words, once, to the model (the error line names the owner's line in data-turn).
  async function retryDirect(turnId) {
    const c = composer();
    const line = S.messages.find(m => String(m.id) === String(turnId) && m.role === "user");
    if (!c || !line) return false;
    const stuck = S.pillData ? root.ChatComposer.askBlock(providersOf()) : "";
    if (stuck !== "") { showBanner({text: stuck, settings: true}); return false; }
    clearBanner();
    const said = root.ChatView.attachedOf(line.text);
    const out = await c.retry(line.id, said.text, {files: said.names.length});
    if (!out.ok) return false;
    S.own = true;
    try { await fetchMessages(false); } catch (e) { handleFetchError(e); }
    return true;
  }

  async function stopDirect() {
    const c = composer();
    if (!c) return;
    await c.stop();
    try { await fetchMessages(false); } catch (e) { handleFetchError(e); }
  }

  function renderComposer() {
    const session = S.session || {kind: "org", writable: true, status: "active", title: "Sutra"};
    const direct = directOn();
    const st = root.ChatView.composerState(session, {busy: !direct && S.turn.active === true, asking: false, blocked: S.blocked || askBlocked()});
    $("scompose").hidden = st.hidden;
    $("sbox").disabled = st.disabled;
    $("ssend").disabled = st.disabled || S.sending;
    const c = composer();
    const b = c && direct ? root.ChatComposer.button(c.state(), $("sbox").value, {disabled: st.disabled || S.sending, blocked: askBlocked() !== ""}) : {label: "Send", act: "send", disabled: st.disabled || S.sending};
    $("ssend").textContent = b.label;
    $("ssend").dataset.act = b.act;
    $("ssend").disabled = b.disabled || st.disabled || S.sending;
    $("sbox").placeholder = S.messages.some(m => m.role === "user") ? "Write a message…" : "Tell Sutra what you need…";
    const note = $("snote");
    note.hidden = st.note === "";
    note.textContent = st.note;
    keepFollowing();
  }

  function renderProgress() {
    const el = $("sprog");
    const at = hasOwn(PHASE_AT, S.turn.phase) ? PHASE_AT[S.turn.phase] : -1;
    el.hidden = !S.turn.seen || S.turn.phase === "error";
    ctx.paint(el, STAGES.map((x, i) => '<div class="' + (i < at ? "done" : i === at ? "on" : "") + '"><i></i>' + esc(x) + "</div>").join(""));
    $("sstatus").textContent = hasOwn(PHASE_SENTENCE, S.turn.phase) ? PHASE_SENTENCE[S.turn.phase] : "";
    renderFrontLatest();
  }

  // The owner writes. The bubble shows at once (pending, dimmed); the box keeps its text until the server accepts the line, so a refusal (no usable
  // connector, too many waiting) loses nothing.
  // opts.plan: the front door's box always plans with Sutra, whatever mode the workspace's box was left in.
  async function send(value, choice, opts) {
    if (!choice && !(isObj(opts) && opts.plan === true) && directOn()) return sendDirect(value);
    const body = text(value).trim();
    if (body === "" || S.blocked !== "" || (S.sending && !choice)) return false;
    const entry = {serverId: null, msg: {id: "local-" + (++S.localSeq), session_id: ORG, role: "user", who: "user", kind: "text", text: body, card: null,
      pause: null, answered_by: null, task_id: null, state: "pending", at: ""}};
    S.pending.push(entry);
    S.awaitGraph = true;
    S.sending = true;
    S.own = true;                                                    // the owner's own line: the transcript goes to the bottom
    renderChat();
    renderComposer();
    try {
      const accepted = await api.post("/api/chats/" + ORG + "/messages", choice ? {text: body, choice} : {text: body});
      entry.serverId = isObj(accepted) && Number.isInteger(accepted.message_id) ? accepted.message_id : null;
      clearSent(body);
      clearBanner();
      S.sending = false;
      try { await fetchMessages(false); } catch (e) { handleFetchError(e); }
      if (entry.serverId === null) S.pending = S.pending.filter(p => p !== entry);
      renderChat();
      renderComposer();
      return true;
    } catch (e) {
      S.pending = S.pending.filter(p => p !== entry);
      S.sending = false;
      if (choice) delete S.answers[choice.message_id];
      showBanner(errorWords(e));
      renderChat();
      renderComposer();
      return false;
    }
  }

  async function retryTurn() {
    try {
      await api.post("/api/chats/" + ORG + "/retry");
      clearBanner();
      S.awaitGraph = true;
      await fetchMessages(true);
    } catch (e) {
      showBanner(errorWords(e));
    }
  }

  // The owner answers a team's question from its card in the org chat. The answer goes to that DEPARTMENT's session, never to cs_org
  // (docs/design/orchestrator.md 1.1). `card` is the card's element; `shown` is what the card should say the owner answered.
  async function answerNeeds(card, value, shown) {
    const body = text(value).trim();
    if (!card || body === "") return false;
    const messageId = card.closest ? (card.closest(".nmsg") || {}).dataset : null;
    const key = messageId ? messageId.id : "";
    let sid = card.dataset.session || "";
    try {
      if (sid === "") {
        const dept = await api.get("/api/departments/" + enc(card.dataset.dept || ""));
        sid = isObj(dept) ? clean(dept.session_id) : "";
      }
      if (sid === "") throw new Error("This team has no chat to answer in.");
      await api.post("/api/chats/" + enc(sid) + "/messages", {text: body});
      if (key !== "") S.answers[/^\d+$/.test(key) ? Number(key) : key] = shown || body;
      clearBanner();
      renderChat();
      refetchNeeds();
      return true;
    } catch (e) {
      showBanner(errorWords(e));
      return false;
    }
  }

  function openTeamFrom(el) {
    const name = el.dataset.deptName || "";
    const task = el.dataset.task || "";
    const dept = S.departments.find(d => isObj(d) && ((name && d.name === name) || (task && d.live_task_id === task)));
    if (dept) root.location.assign("/d/" + enc(dept.id) + "/?view=simple");
    else selectPane("graph", {reveal: true});
  }

  function focusCard(messageId) {
    const need = S.needs.find(n => isObj(n) && String(n.message_id) === String(messageId));
    if (need && need.kind !== "approval" && clean(need.dept_id) !== "" && clean(need.session_id) !== "" && need.session_id !== ORG && S.team) {
      openTeamChat(need.dept_id, need.session_id, {question: need.message_id});          // the question is in the team's own chat
      return true;
    }
    const el = $("smsgs").querySelector('.c-needs[data-question="' + String(messageId).replace(/[^\w-]/g, "") + '"]');
    selectPane("chat");
    if (!el) { $("sbox").focus(); return false; }
    const row = el.closest(".nmsg") || el;
    row.tabIndex = -1;
    row.classList.add("flash");
    if (row.scrollIntoView) row.scrollIntoView({block: "center"});
    row.focus();
    root.setTimeout(() => row.classList.remove("flash"), 2500);
    return true;
  }

  function onChatClick(e) {
    const b = e.target.closest("button, a[data-act]");
    if (!b || !$("smsgs").contains(b)) return;
    if (b.dataset.brief) { send(b.dataset.brief); return; }
    const act = b.dataset.act;
    if (!act) return;
    const row = b.closest(".nmsg");
    const messageId = row ? row.dataset.id : "";
    const numeric = /^\d+$/.test(messageId) ? Number(messageId) : messageId;
    if (act === "open-team") {
      if (b.tagName !== "A") openTeamFrom(b);                                         // a real link navigates by itself
    } else if (act === "open-team-chat") {
      const pointer = b.closest(".c-teamchat");
      openTeamChat(b.dataset.node, b.dataset.session, {question: pointer ? Number(pointer.dataset.question) : 0});
    } else if (act === "show-node") {
      selectPane("graph", {reveal: true});
      if (S.graphView) S.graphView.select(b.dataset.node);
    } else if (act === "show-change") {
      selectPane("chart", {reveal: true});
      const seq = Number(b.dataset.seq);
      if (S.chartView && Number.isFinite(seq)) S.chartView.selectChange(seq);
    } else if (act === "choose") {
      const label = b.dataset.option || "";
      if (typeof numeric === "number") {
        S.answers[numeric] = label;
        renderChat();
        send(label, {message_id: numeric, option: b.dataset.id || label});
      }
    } else if (act === "option") {
      send("Option " + b.dataset.opt);
    } else if (act === "answer-option") {
      answerNeeds(b.closest(".c-needs"), "Option " + b.dataset.opt, b.dataset.text);
    } else if (act === "answer") {
      const card = b.closest(".c-needs");
      const box = card && card.querySelector(".canswerbox");
      if (box) answerNeeds(card, box.value);
    } else if (act === "retry") {
      retryTurn();
    } else if (act === "retry-task") {
      retryTask(b.dataset.task, b);
    } else if (act === "retry-direct") {
      retryDirect(b.dataset.turn);
    }
  }

  /* ---------------------------------------------------------------- the strip "Needs you", the rail, the panes */
  function needLine(item) {
    const ask = root.ChatView.parseAsk(item.text);
    const question = ask.qs.length ? ask.qs[0].q : "";
    const said = root.ChatView.stripTag(question || ask.say || item.text).split("\n")[0].trim();
    const who = clean(item.dept_name) || (item.kind === "approval" ? "Approval needed" : "");           // an approval belongs to no team
    return who + (said ? (who ? ": " : "") + said : "");
  }

  // A question is answered in its team's own chat, and the button says which one; an approval waits in the org chat.
  const needButton = item => (item.kind !== "approval" && clean(item.dept_name) !== "" && clean(item.session_id) !== ORG ? "Answer in " + clean(item.dept_name) + "'s chat" : "Answer in Chat");

  // The strip: what waits on the owner (questions and approvals, each with how long it has waited) and the Heads up lane (heads_up_view.js).
  // The count is the questions and approvals plus the problems the owner has not marked "Got it"; quiet teams and finished work never count.
  const HV = () => root.HeadsUpView || null;
  const attentionCount = () => (HV() ? HV().count(S.needs, S.heads, S.seen) : S.needs.length);

  function renderNeeds() {
    const items = S.needs;
    const n = attentionCount();
    const hv = HV();
    attend();
    const lane = hv ? hv.laneHtml(S.heads, {seen: S.seen, more: S.fyiMore}) : "";
    const sum = hv && lane ? hv.summary(items, S.heads, S.seen) : "";
    const elapsed = S.needsAt ? Date.now() - S.needsAt : 0;
    $("needs").classList.toggle("on", n > 0);
    ctx.paint($("needs"), '<h2>Needs you <span class="needbadge" id="needcount">' + n + "</span></h2>" + (sum ? '<p class="needsum">' + esc(sum) + "</p>" : "") +
      (items.length ? (lane ? '<h3 class="nylane">Waiting on you</h3>' : "") + items.map(i => '<div class="needitem"><span>' + esc(needLine(i)) + "</span>" +
        (hv ? hv.waitedHtml(i, elapsed) : "") + '<button type="button" data-needmsg="' + esc(i.message_id) + '">' + esc(needButton(i)) + "</button></div>").join("")
        : (n === 0 ? '<span class="none">Nothing needs you right now.</span>' : "")) + lane + limitLines() + offerHtml());
    barBadge();
    renderSwitch();
    renderFront();
  }

  /* ---------------------------------------------------------------- the front door (front_door.js; the one-front brief) */
  // Home has two places: the front door (what needs you, what runs, what finished, a new project) and the workspace (the org chat, the panes, the rail).
  // <html data-place> says which shows; Manager and Debug owners come back to the place they left, a Simple owner always to the front door.
  const FD = () => root.FrontDoor || null;
  const level = () => (ctx.level ? ctx.level() : "simple");
  const place = () => (doc.documentElement.dataset.place === "ws" ? "ws" : "front");
  const PLACE_KEY = "sutra:home:place";

  function setPlace(where) {
    const p = where === "ws" ? "ws" : "front";
    doc.documentElement.dataset.place = p;
    try { if (level() !== "simple") root.localStorage.setItem(PLACE_KEY, p); } catch (e) { /* storage may be blocked */ }
    if (p === "ws" && S.graphView && S.graph) protect("graph redraw", () => S.graphView.update(S.graph));       // drawn while hidden: draw it at its size
    if (p === "front") renderFront();
    return p;
  }

  // The front door's state for FrontDoor: what is fetched already, plus the front's own marks.
  function frontState() {
    return {level: level(), needs: S.needs, heads: S.heads, seen: S.seen, departments: S.departments, elapsedMs: S.needsAt ? Date.now() - S.needsAt : 0,
      loaded: S.needsLoaded && S.headsLoaded && S.departmentsLoaded, answering: S.front.answering, errors: S.front.errors, moreDone: S.front.moreDone};
  }

  // A repaint keeps what the owner typed in an answer box (and the focus in it): the boxes are found again by their message id.
  function paintKeeping(el, html) {
    if (!el) return false;
    const typed = {};
    let focus = "";
    el.querySelectorAll("textarea[data-msg]").forEach(t => { typed[t.dataset.msg] = t.value; if (t === doc.activeElement) focus = t.dataset.msg; });
    if (!ctx.paint(el, html)) return false;
    el.querySelectorAll("textarea[data-msg]").forEach(t => { if (hasOwn(typed, t.dataset.msg)) t.value = typed[t.dataset.msg]; if (t.dataset.msg === focus) t.focus(); });
    return true;
  }

  function renderFront() {
    const fd = FD();
    if (!fd || !$("front")) return;
    protect("front door", () => {
      const st = frontState();
      paintKeeping($("fdneeds"), fd.needsHtml(st));
      ctx.paint($("fdlists"), fd.listsHtml(st));
      ctx.paint($("fddebug"), (S.front.hookNote && st.level === "debug" ? '<p class="fdcalm" role="status">' + esc(S.front.hookNote) + "</p>" : "") + fd.debugHtml(st));
      const nav = fd.navHtml(st.level);
      ctx.paint($("fdnav"), nav);
      $("fdnav").hidden = nav === "";
      doc.querySelectorAll("#fdlevel [data-level]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.level === st.level)));
      renderFrontLatest();
    });
  }

  // Under the box: after the owner started something here, the org chat's progress sentence and its last word (or the choice it waits on).
  function renderFrontLatest() {
    const fd = FD();
    if (!fd || !$("fdlatest")) return;
    const status = S.front.error || (S.front.sent && S.turn.active && hasOwn(PHASE_SENTENCE, S.turn.phase) ? PHASE_SENTENCE[S.turn.phase] : "");
    ctx.paint($("fdlatest"), fd.latestHtml({show: S.front.sent || S.front.error !== "", status, messages: S.messages, answers: answersMap()}));
  }

  async function sendFront() {
    const box = $("fdbox");
    const body = text(box.value).trim();
    if (body === "" || S.sending) return false;
    S.front.sent = true;
    S.front.error = "";
    $("fdsend").disabled = true;
    const ok = await send(body, null, {plan: true});
    $("fdsend").disabled = false;
    if (ok) { if (box.value.trim() === body) box.value = ""; }
    else S.front.error = (S.banner && S.banner.text) || S.blocked || FAILED;
    renderFrontLatest();
    return ok;
  }

  // An answer to a team's question, from its card: to that team's own session (never cs_org), as answerNeeds does from the org chat.
  async function answerFront(messageId, value) {
    const body = text(value).trim();
    const item = S.needs.find(n => isObj(n) && String(n.message_id) === String(messageId));
    if (!item || body === "" || S.front.answering[item.message_id]) return false;
    S.front.answering[item.message_id] = true;
    delete S.front.errors[item.message_id];
    renderFront();
    try {
      let sid = clean(item.session_id);
      if (sid === "" || sid === ORG) {
        const dept = await api.get("/api/departments/" + enc(clean(item.dept_id)));
        sid = isObj(dept) ? clean(dept.session_id) : "";
      }
      if (sid === "") throw new Error("This team has no chat to answer in.");
      await api.post("/api/chats/" + enc(sid) + "/messages", {text: body});
      S.answers[item.message_id] = body;
      await fetchNeeds().catch(handleFetchError);
      return true;
    } catch (e) {
      S.front.errors[item.message_id] = e && e.code ? errorWords(e).text : clean(e && e.message) || FAILED;
      return false;
    } finally {
      delete S.front.answering[item.message_id];
      renderFront();
    }
  }

  // Approve or Not now: the approval card's own button, pressed through the org chat (the same path as the card in the chat).
  async function decideFront(messageId, label) {
    const id = Number(messageId);
    if (!Number.isInteger(id) || S.front.answering[id]) return false;
    S.front.answering[id] = true;
    delete S.front.errors[id];
    S.answers[id] = label;
    renderFront();
    const ok = await send(label, {message_id: id, option: label});
    delete S.front.answering[id];
    if (!ok) S.front.errors[id] = (S.banner && S.banner.text) || FAILED;
    await fetchNeeds().catch(handleFetchError);
    renderFront();
    return ok;
  }

  function onFrontClick(e) {
    const lv = e.target.closest("#fdlevel [data-level]");
    if (lv) { ctx.setLevel(lv.dataset.level); return; }
    if (e.target.closest("#fdsend")) { sendFront(); return; }
    const b = e.target.closest("button[data-act]");
    if (!b || !$("front").contains(b)) return;
    const act = b.dataset.act;
    const card = b.closest(".fdcard");
    if (act === "fd-option") answerFront(b.dataset.msg, "Option " + b.dataset.opt);
    else if (act === "fd-answer") { const box = card && card.querySelector("textarea[data-msg]"); if (box) answerFront(b.dataset.msg, box.value); }
    else if (act === "fd-approve" || act === "fd-decline") decideFront(b.dataset.msg, b.dataset.text || (act === "fd-approve" ? "Yes" : "No"));
    else if (act === "fd-choose") { const id = Number(b.dataset.msg); if (Number.isInteger(id)) { S.answers[id] = b.dataset.text || ""; send(b.dataset.text || b.dataset.option, {message_id: id, option: b.dataset.option || b.dataset.text}).then(renderFrontLatest); } }
    else if (act === "fd-retry" || act === "retry-task") retryTask(b.dataset.task, b);
    else if (act === "fd-seen" || act === "headsup-seen") {
      S.seen[text(b.dataset.task)] = true;
      if (HV()) protect("seen", () => HV().saveSeen(storage(), S.seen, S.heads));
      renderNeeds();
    } else if (act === "fd-more") { S.front.moreDone = true; renderFront(); }
    else if (act === "fd-chat" || act === "open-team-chat") { setPlace("ws"); openTeamChat(b.dataset.node, b.dataset.session || "", {}); }
    else if (act === "fd-go") {
      setPlace("ws");
      if (b.dataset.pane === "chat") selectPane("chat");
      else selectPane(b.dataset.pane, {group: b.dataset.pane === "settings" ? "appearance" : ""});
    } else if (act === "fd-conversation") { setPlace("ws"); selectPane("chat"); }
    else if (act === "fd-hook") {
      // the Raw AI chat viewer is built elsewhere: a page that has it handles the event (and cancels it); until then, say where it will be
      const ev = new root.CustomEvent("sutra:raw-ai-chat", {cancelable: true, detail: {from: "home"}});
      if (doc.dispatchEvent(ev)) { S.front.hookNote = "The raw AI chat viewer is not in this version yet. It will open from here and from each agent's panel."; renderFront(); }
    }
  }

  function wireFront() {
    if (!$("front")) return;
    $("front").addEventListener("click", onFrontClick);
    $("fdbox").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendFront(); } });
    $("front").addEventListener("keydown", e => {
      const t = e.target;
      if (t && t.matches && t.matches("textarea[data-msg]") && e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); answerFront(t.dataset.msg, t.value); }
    });
    if ($("gofront")) $("gofront").addEventListener("click", () => setPlace("front"));
    doc.addEventListener("sutra:level", () => {
      if (level() === "simple" && place() === "ws" && S.chat.sid !== ORG) showOrgChat();
      renderFront();
    });
  }

  // The tab title count and one desktop notice per new question or problem (chat_attention.js), once both lists have been read: what is
  // there at the first read is not news.
  function attend() {
    if (!S.attention || !S.needsLoaded || !S.headsLoaded) return;
    protect("attention", () => S.attention.update(root.ChatAttention.itemsOf(S.needs, S.heads, S.seen, {finished: true})));
  }

  // The monthly limit from 80 % and the plan window from 70 %, one line each, with Continue while the guard holds work (limits_view.js). Not counted.
  const limitLines = () => (LV() ? protect("limit lines", () => LV().stripHtml(S.limits)) || "" : "");

  function offerHtml() {
    if (!S.attention || !protect("offer", () => S.attention.offered())) return "";
    return '<p class="nyoffer">Get a desktop notice when a team needs you and Sutra is in the background? ' +
      '<button type="button" class="linkbtn" data-act="notify-on">Turn on</button> <button type="button" class="linkbtn" data-act="notify-off">No thanks</button></p>';
  }

  // A notice was clicked: the window is in front already; show what it was about.
  function openAttention(item) {
    const ref = isObj(item) && isObj(item.ref) ? item.ref : {};
    if (place() === "front") {                                                         // the front door has a card for it: bring that card into view
      const card = (ref.kind === "question" || ref.kind === "approval") && $("fdneeds").querySelector('.fdcard[data-msg="' + String(ref.message_id).replace(/\D/g, "") + '"]');
      const at = card || $("fdneeds");
      if (at.scrollIntoView) at.scrollIntoView({block: "center"});
      at.tabIndex = -1;
      at.focus();
      return;
    }
    if (ref.kind === "question") { focusCard(ref.message_id); return; }
    if (ref.kind === "approval") {
      selectPane("chat", {focus: false});
      const row = $("smsgs").querySelector('.nmsg[data-id="' + String(ref.message_id).replace(/\D/g, "") + '"]');
      if (row && row.scrollIntoView) row.scrollIntoView({block: "center"});
      return;
    }
    const strip = $("needs");
    doc.body.classList.add("has-site", "sp-preview");
    if (strip.scrollIntoView) strip.scrollIntoView({block: "start"});
    strip.focus();
  }

  // The tasks whose done card offers Try again: exactly the Heads up rows that offer it, so the button goes when the problem does.
  function retryTasks() {
    const out = {};
    S.heads.forEach(h => { if (isObj(h) && h.retry === true && typeof h.task_id === "string") out[h.task_id] = true; });
    return out;
  }

  // Try again: the existing POST /api/tasks/{id}/retry (a new task with the same words, parent_task_id = this one), then the lane again.
  async function retryTask(taskId, button) {
    if (!/^tsk_[0-9a-f]{12}$/.test(text(taskId))) return false;
    if (button) button.disabled = true;
    try {
      await api.post("/api/tasks/" + enc(taskId) + "/retry");
      clearBanner();
    } catch (e) {
      showBanner(errorWords(e));
      if (button) button.disabled = false;
      return false;
    }
    try { await fetchHeads(); } catch (e) { handleFetchError(e); }
    refetchDepartments();
    return true;
  }

  function onNeedsClick(e) {
    const b = e.target.closest("[data-needmsg], button[data-act]");
    if (!b || !$("needs").contains(b)) return;
    if (b.dataset.needmsg) { focusCard(b.dataset.needmsg); return; }
    const act = b.dataset.act;
    const hv = HV();
    if (act === "retry-task") retryTask(b.dataset.task, b);
    else if (act === "open-team-chat") openTeamChat(b.dataset.node, b.dataset.session || "", {});
    else if (act === "headsup-seen" && hv) {
      S.seen[text(b.dataset.task)] = true;
      protect("seen", () => hv.saveSeen(storage(), S.seen, S.heads));
      renderNeeds();
    } else if (act === "headsup-more") { S.fyiMore = true; renderNeeds(); }
    else if (act === "notify-on" && S.attention) S.attention.enable().then(renderNeeds, renderNeeds);
    else if (act === "notify-off" && S.attention) { S.attention.decline(); renderNeeds(); }
    else if (act === "guard-continue") continueGuard();
  }

  function storage() { try { return root.localStorage; } catch (e) { return null; } }

  function statusWord(status) { return hasOwn(STATUS_WORDS, status) ? STATUS_WORDS[status] : "idle"; }

  function renderRail() {
    const rows = S.departments.filter(isObj).map(d => '<a class="railteam st-' + esc(d.node_status || "idle") + '" href="/d/' + enc(d.id) + '/" data-dept="' + esc(d.id) + '">' +
      '<span class="rtname">' + esc(d.name || d.id) + '</span><span class="rtstat">' + esc(statusWord(d.node_status)) + "</span></a>");
    ctx.paint($("railteams"), rows.length ? rows.join("") : '<p class="railnone">No teams yet. Tell Sutra what you need and a team appears here.</p>');
    renderSwitch();
  }

  /* ---------------------------------------------------------------- the chat switcher and a team's own chat (gap dept-chats) */
  // The chat column shows ONE chat: the org chat, or the own chat of a team or division (the node panel's Chat tab, inline in #teamchat). S.chat names the
  // one on show: {sid, node}; the org chat is {sid: "cs_org", node: ""}. The org chat's own parts stay in the page, hidden, while a team's chat shows.
  const CS = () => root.ChatSwitch || null;
  const switchEntries = () => (CS() ? CS().entries(S.departments, S.graph, S.needs) : []);

  function renderSwitch() {
    const el = $("cswitch");
    if (!el || !CS()) return;
    const items = switchEntries();
    const had = el.contains(doc.activeElement) ? doc.activeElement.id : "";
    const html = CS().bar(items, S.chat.sid);
    if (ctx.paint(el, html) && had) { const back = doc.getElementById(had); if (back && back !== doc.activeElement) back.focus(); }   // a repaint must not drop the owner's place
    el.hidden = html === "";
    if ($("schat")) $("schat").setAttribute("aria-label", CS().heading(items, S.chat.sid));
  }

  // Show a team's (or a division's) own chat in the chat column. `sid` is the chat session when the caller knows it (a pointer card carries it).
  // opts.question: the message of that chat to bring into view (a question that waits).
  function openTeamChat(node, sid, opts) {
    const nodeId = clean(node);
    if (nodeId === "" || !S.team) return Promise.resolve(false);
    const known = CS() ? CS().entryOf(switchEntries(), nodeId) : null;
    S.chat = {sid: clean(sid) || (known ? known.id : ""), node: nodeId};
    $("schat").classList.add("team-open");
    doc.body.classList.remove("sp-preview");                                       // a phone: the chat column, not the graph
    markRail();
    renderSwitch();
    const question = isObj(opts) && Number.isInteger(opts.question) && opts.question > 0 ? opts.question : 0;
    return Promise.resolve(S.team.open(nodeId, "chat")).then(() => {
      if (S.chat.node === nodeId && S.chat.sid === "") { const found = CS() ? CS().entryOf(switchEntries(), nodeId) : null; if (found) { S.chat.sid = found.id; renderSwitch(); } }
      if (question) focusTeamLine(question);
      return true;
    }, () => false);
  }

  function focusTeamLine(messageId) {
    const row = $("teamchat").querySelector('.nmsg[data-id="' + String(messageId).replace(/\D/g, "") + '"]');
    if (!row) return false;
    row.tabIndex = -1;
    row.classList.add("flash");
    if (row.scrollIntoView) row.scrollIntoView({block: "center"});
    row.focus();
    root.setTimeout(() => row.classList.remove("flash"), 2500);
    return true;
  }

  // Back to the org chat. The panel's own Back button and Esc land here too (its onClose), so a second call finds everything done.
  function showOrgChat() {
    const was = S.chat.sid !== ORG;
    S.chat = {sid: ORG, node: ""};
    $("schat").classList.remove("team-open");
    renderSwitch();
    if (S.team && S.team.isOpen()) S.team.close();
    if (!was) return;
    const tab = doc.getElementById("cstab-" + ORG);                                  // the owner's place: the Sutra tab, or the box when there is no strip
    if (tab && !tab.closest("[hidden]")) tab.focus();
    else if ($("sbox") && !$("sbox").disabled) $("sbox").focus();
  }

  function onSwitchClick(e) {
    const b = e.target.closest("button[data-act=switch-chat]");
    if (!b || !$("cswitch").contains(b)) return;
    if (b.dataset.session === ORG) showOrgChat();
    else if (S.team && (b.dataset.session !== S.chat.sid || !S.team.isOpen())) openTeamChat(b.dataset.node, b.dataset.session, {});
  }

  // Arrow keys, Home and End move between the tabs (the chat itself is chosen with Enter or Space, a button's own click).
  function onSwitchKey(e) {
    const tabs = Array.from($("cswitch").querySelectorAll("button[data-act=switch-chat]"));
    const at = tabs.indexOf(doc.activeElement);
    const to = CS() ? CS().nextIndex(e.key, tabs.length, at) : -1;
    if (to < 0 || at < 0) return;
    e.preventDefault();
    tabs[to].focus();
  }

  function markRail() {
    doc.querySelectorAll("#rail [data-pane]").forEach(b => {
      if (b.dataset.pane === S.pane && (!b.dataset.group || b.dataset.group === S.group)) b.setAttribute("aria-current", "true");
      else b.removeAttribute("aria-current");
    });
    doc.querySelectorAll(".stoggle [data-show]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.show === (doc.body.classList.contains("sp-preview") ? "right" : "chat"))));
  }

  function ensureGraph() {
    if (S.graphView || !root.GraphView) return;
    S.graphView = root.GraphView.create($("pane-graph"), {mode: "graph", scope: "all", level: "chart", title: "Workflow graph", onOpen: openNode, onSelect() {}});
    S.graphView.setLive(S.live);
    if (S.graph) S.graphView.update(S.graph);
  }

  function ensureChart() {
    if (S.chartView || !root.OrgChartView) return;
    S.chartView = root.OrgChartView.create($("pane-chart"), {onOpen: openNode, onShow(node) { selectPane("graph", {reveal: true}); if (S.graphView) S.graphView.select(node.id); }});
    S.chartView.setLive(S.live);
    if (S.chart) S.chartView.update(S.chart, S.changes);
    if (S.find) S.chartView.setFind(S.find);
  }

  // Gap package chart-insight: the rail's search (team_find.js). A hit is a team or a division; the Org chart keeps the hits lit and fades the rest, and a
  // chat hit opens the node that owns it (an archived chat opens the node it was filed under).
  function wireFind() {
    if (!root.TeamFind || !$("railfind") || !$("railfindres")) return;
    S.finder = root.TeamFind.mount({input: $("railfind"), out: $("railfindres"), api, onChange: rows => {
      S.find = rows;
      if (S.chartView) S.chartView.setFind(rows);
    }, onOpenChat: sid => api.get("/api/chats/" + enc(sid)).then(s => {
      if (isObj(s) && s.kind === "org") selectPane("chat");
      else if (isObj(s)) openNode({id: s.filed_under || s.node_id, kind: s.kind});
    }, () => {})});
  }

  // selectPane("chat"|"graph"|"chart"|"settings", {reveal, group}). reveal (default true) also shows the right column on a phone.
  function selectPane(name, options) {
    const o = isObj(options) ? options : {};
    const reveal = o.reveal !== false;
    if (name === "chat") {
      if (S.chat.sid !== ORG) showOrgChat();                                          // the rail's Chat and a notice about an approval mean the org chat
      doc.body.classList.remove("sp-preview");
      markRail();
      if ($("sbox") && !$("sbox").disabled && o.focus !== false) $("sbox").focus();
      return "chat";
    }
    const pane = PANES.includes(name) ? name : "graph";
    S.pane = pane;
    S.group = pane === "settings" ? clean(o.group) : "";
    PANES.forEach(p => { $("pane-" + p).hidden = p !== pane; });
    if (reveal) doc.body.classList.add("has-site", "sp-preview");
    if (pane === "graph") ensureGraph();
    if (pane === "chart") ensureChart();
    if (pane === "settings") openSettings(S.group);
    markRail();
    return pane;
  }

  // The graph or the org chart asks to open a node: the root is the org chat itself, every other node opens its panel (Chat tab).
  function openNode(node) {
    if (!isObj(node)) return;
    if (node.kind === "root" || node.id === "root") { selectPane("chat"); return; }
    if (S.panel) Promise.resolve(S.panel.open(node.id, "chat")).catch(() => {});
  }

  /* ---------------------------------------------------------------- appearance and the left bar (J2's logic, keys j2theme and j2bar) */
  function themePref() {
    if (S.theme) return S.theme;
    try { const p = root.localStorage.getItem("j2theme"); return ["light", "dark", "system"].includes(p) ? p : "light"; } catch (e) { return "light"; }
  }

  function themeApply() {
    const pref = themePref();
    const de = doc.documentElement;
    let light = false;
    try { light = root.matchMedia("(prefers-color-scheme: light)").matches; } catch (e) { light = false; }
    de.dataset.theme = pref === "system" ? (light ? "light" : "dark") : pref;
    doc.querySelectorAll("[data-themepick]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.themepick === pref)));
  }

  const BARWIDE = root.matchMedia ? root.matchMedia("(min-width:1200px)") : {matches: true, addEventListener() {}};
  const barOpen = () => !$("dview").classList.contains("railoff");
  function barSet(open, keep) {
    $("dview").classList.toggle("railoff", !open);
    $("railtoggle").setAttribute("aria-expanded", String(open));
    if (keep && BARWIDE.matches) { try { root.localStorage.setItem("j2bar", open ? "1" : "0"); } catch (x) { /* storage may be blocked */ } }
  }
  function barInit() {
    let v = null;
    try { v = root.localStorage.getItem("j2bar"); } catch (x) { v = null; }
    barSet(BARWIDE.matches && v !== "0", false);
  }
  function barBadge() {
    const n = attentionCount();
    $("barbadge").textContent = String(n);
    $("barbadge").hidden = !n;
    $("railtoggle").setAttribute("aria-label", n ? "Menu, " + n + " waiting on you" : "Menu");
  }

  /* ---------------------------------------------------------------- Settings */
  const SV = () => root.SettingsView;

  function paintAppearance() { ctx.paint($("set-appearance"), SV().appearanceHtml(themePref())); themeApply(); }
  // Windows words the CLI file box its own way (a drive letter, `where`): the page runs in the browser of the machine the app runs on.
  const ON_WINDOWS = typeof navigator !== "undefined" && /Windows/i.test(String(navigator.userAgent || ""));
  function paintConnectors() { ctx.paint($("set-connectors"), SV().connectorsHtml(S.health, Object.assign({windows: ON_WINDOWS}, S.conn))); }

  /* ---- the working folder (GAP3-workdir; settings_view.js draws it, this part keeps what was typed and calls the server) */
  const WD = {data: null, loaded: false, value: "", dirty: false, step: "idle", message: ""};
  function paintWorkdir() { if ($("set-workdir") && !typingIn($("set-workdir"))) ctx.paint($("set-workdir"), SV().workdirHtml(WD)); }
  async function loadWorkdir() {
    const r = await SV().loadWorkdir(api);
    if (r.ok) {
      WD.data = r.data;
      WD.loaded = true;
      if (!WD.dirty && WD.step !== "saving") WD.value = r.data && r.data.path ? r.data.path : "";      // what the owner is typing is never replaced
      if (WD.step === "error") { WD.step = "idle"; WD.message = ""; }
    } else if (WD.data === null) { WD.step = "error"; WD.message = r.message; }
    paintWorkdir();
    return r;
  }
  async function workdirAct(act, b) {
    if (WD.step === "saving") return null;
    if (act === "workdir-choose") {                                                    // the desktop's folder dialog; a closed dialog changes nothing
      const picked = await SV().chooseWorkdir();
      if (picked === null) return null;
      WD.value = picked;
      WD.dirty = true;
    }
    WD.step = "saving";
    WD.message = "";
    paintWorkdir();
    const r = act === "workdir-clear" ? await SV().clearWorkdir(api)
      : (act === "workdir-access" ? await SV().saveWorkdirAccess(api, b && b.dataset.access) : await SV().saveWorkdir(api, WD.value));
    WD.step = r.ok ? "ok" : "error";
    WD.message = r.message;
    if (r.ok && r.data) {
      WD.data = r.data;
      WD.loaded = true;
      WD.value = r.data.path || "";
      WD.dirty = false;
    }
    paintWorkdir();
    return r;
  }
  function paintEngine() {
    ctx.paint($("set-engine"), SV().engineHtml(S.settings, {scope: S.scope, departments: S.departments, errors: S.errors, values: S.values, saved: S.saved, busy: S.saving,
      dataDir: S.info && S.info.data_dir}));
  }

  /* ---- the owner's notes (GAP2 rules-notes; notes_view.js draws them, this part reads the fields and calls the server) */
  const NS = {data: null, error: "", editing: 0, draft: null, busy: false, saved: ""};
  const NV = () => root.NotesView || null;
  function paintNotes() { if (NV() && $("set-notes")) ctx.paint($("set-notes"), NV().notesHtml(NS)); }
  async function loadNotes() {
    if (!NV()) return;
    try { NS.data = await NV().loadNotes(api); NS.error = ""; } catch (e) { NS.error = NV().errorWords(e); }
    paintNotes();
  }
  function noteFields(box) {
    const at = sel => { const el = box ? box.querySelector(sel) : null; return el ? el.value : ""; };
    return {group: at("[data-note-group]"), text: at("[data-note-text]"), expires: at("[data-note-date]")};
  }
  async function noteAct(act, b) {
    const N = NV();
    const host = $("set-notes");
    if (!N || !host || NS.busy) return;
    const id = Number(b.dataset.id) || 0;
    if (act === "note-edit" || act === "note-cancel") { NS.editing = act === "note-edit" ? id : 0; NS.draft = null; NS.error = ""; NS.saved = ""; paintNotes(); return; }
    const form = act === "note-add" ? noteFields(host.querySelector(".noteadd")) : act === "note-save" ? noteFields(host.querySelector('li[data-note="' + id + '"]')) : null;
    NS.busy = true;
    paintNotes();
    const out = act === "note-add" ? await N.addNote(api, form) : act === "note-save" ? await N.editNote(api, id, form) : await N.forgetNote(api, id);
    NS.busy = false;
    if (out.ok) { if (out.data) NS.data = out.data; NS.error = out.error; NS.draft = null; NS.editing = 0; NS.saved = act === "note-forget" ? "Forgotten." : "Saved. It applies from the next request."; }
    else { NS.error = out.error; NS.saved = ""; NS.draft = act === "note-save" ? Object.assign({id: id}, form) : form; }
    paintNotes();
  }
  function paintModels() {
    ctx.paint($("set-models"), SV().policyHtml(S.policy, S.health, {models: S.models, errors: S.pol.errors, saved: S.pol.saved, busy: S.pol.busy}));
  }
  function paintAbout() { ctx.paint($("set-about"), SV().aboutHtml(S.info, S.update, S.auto ? {...S.auto, busy: S.autoBusy, message: S.autoMsg} : null)); }

  function renderSettings() {
    paintAppearance();
    paintConnectors();
    paintModels();
    paintWorkdir();
    paintEngine();
    paintLimits();
    paintNotices();
    paintRecurring();
    paintNotes();
    paintAbout();
  }

  // The Default model group (welcome-settings, item 3): one change is one read-modify-write of the routing policy (SettingsView.savePolicy).
  async function loadPolicyState() {
    try {
      const got = await SV().loadPolicy(api);
      S.policy = got.policy;
      S.models = got.models;
      S.pol = {busy: false, saved: false, errors: {}};
    } catch (e) {
      S.pol = {busy: false, saved: false, errors: {"": errorWords(e).text}};
    }
    paintModels();
  }
  async function changePolicy(edits) {
    if (S.policy === null || S.pol.busy) return null;
    S.pol = {busy: true, saved: false, errors: {}};
    paintModels();
    const out = await SV().savePolicy(api, S.policy, edits);
    S.policy = out.policy;                               // what is stored now: the answer of the PUT, or the policy savePolicy read again when it refused or failed
    S.pol = {busy: false, saved: out.ok, errors: out.errors};
    paintModels();
    return out;
  }

  async function loadAbout() {
    try { S.info = await api.get("/api/ops/info"); } catch (e) { S.info = {}; }
    paintAbout();
    paintEngine();                                                                    // its locked rows name the data folder
    await loadAutoUpdate();
  }
  async function loadAutoUpdate() {                    // a read: it asks GitHub nothing
    try { S.auto = await api.get("/api/ops/update-setting"); } catch (e) { /* the group stays as it was, without the switch */ }
    paintAbout();
  }
  async function toggleAutoUpdate(on) {
    if (S.autoBusy || S.auto === null) return null;
    S.autoBusy = true;
    S.autoMsg = "";
    paintAbout();
    const out = await SV().setAutoUpdate(api, on);
    if (out.ok) S.auto = out.auto;
    S.autoMsg = out.message;
    S.autoBusy = false;
    paintAbout();
    return out;
  }
  async function checkForUpdates() {
    if (S.update.step === "running") return null;
    S.update = {step: "running"};
    paintAbout();
    S.update = await SV().checkUpdate(api);
    paintAbout();
    loadAutoUpdate();                                  // the server wrote the "last check" line: show it
    return S.update;
  }

  async function loadEngineSettings() {
    try {
      S.settings = await SV().loadEngine(api, S.scope);
      S.errors = {};
      S.values = null;
    } catch (e) {
      S.errors = {"": errorWords(e).text};
    }
    S.saved = false;
    paintEngine();
  }

  function openSettings(group) {
    renderSettings();
    if (S.settings === null) loadEngineSettings();
    if (NS.data === null) loadNotes();
    if (S.policy === null) loadPolicyState();
    if (S.info === null) loadAbout(); else loadAutoUpdate();                              // the last check line moves on by itself: read it again when About opens
    if (S.health === null) fetchHealth().catch(handleFetchError);
    loadWorkdir();                                                                     // read again on every visit: the folder may have vanished
    if (S.notices === null) fetchLimits(); else refetchLimits();                          // the notices are read at load; read them again here only if that failed
    if (S.recurring === null) fetchRecurring();
    if (group) {
      const el = $("pane-settings").querySelector('.setgrp[data-group="' + group.replace(/[^\w-]/g, "") + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({block: "start"});
    }
  }

  function readEngineForm() {
    const form = {};
    doc.querySelectorAll("#set-engine [data-input]").forEach(el => { form[el.dataset.input] = el.type === "checkbox" ? el.checked : el.value; });
    return form;
  }

  // Save the Engine group: PUT {set, unset} for the scope (dept in the query by hand, none for all teams).
  async function saveEngine(scope, changes) {
    S.saving = true;
    S.saved = false;
    paintEngine();
    const out = await SV().saveEngine(api, S.settings, scope, changes);
    S.saving = false;
    S.errors = out.errors;
    S.saved = out.ok && !out.unchanged;
    S.values = out.ok ? null : changes;                    // a refusal keeps what the owner typed, beside the sentence that names the field
    if (out.ok && out.settings) S.settings = out.settings;
    paintEngine();
    return out;
  }

  async function testConnector(provider) {
    S.conn.test[provider] = {step: "running"};
    paintConnectors();
    const r = await SV().testConnector(api, provider);
    S.conn.test[provider] = r.ok ? {step: "ok", seconds: r.seconds} : {step: "error", message: r.message};
    paintConnectors();
    return r;
  }

  // Codex Sign in: the link and the one-time code of the start answer are shown, the page asks until signed_in, failed or expired.
  function signIn() {
    if (S.signer && S.signer.state().step === "pending") return S.signer.done;
    S.signer = SV().signIn(api, {onState(state) {
      S.conn.signin = state;
      paintConnectors();
      if (state.step === "signed_in" && S.watch) S.watch.refetch();
    }});
    return S.signer.done;
  }

  function cancelSignIn() { return S.signer ? S.signer.cancel() : Promise.resolve(null); }

  // The CLI file the owner chose (GAP-providers): what was typed is kept across a repaint; the rows refetch on the connector.health the route sends.
  function cliPathState(provider) {
    if (!isObj(S.conn.path)) S.conn.path = {};
    if (!isObj(S.conn.path[provider])) S.conn.path[provider] = {step: "idle", value: ""};
    return S.conn.path[provider];
  }
  async function setCliPath(provider, path) {
    Object.assign(cliPathState(provider), {step: "saving", message: ""});
    paintConnectors();
    const r = await SV().setCliPath(api, provider, path);
    Object.assign(cliPathState(provider), r.ok ? {step: "ok", message: r.message, value: ""} : {step: "error", message: r.message});
    paintConnectors();
    if (r.ok && S.watch) S.watch.refetch();
    return r;
  }

  function onSettingsClick(e) {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const act = b.dataset.act;
    if (act === "test") testConnector(b.dataset.provider);
    else if (act === "signin") signIn();
    else if (act === "cancel") cancelSignIn();
    else if (act === "save-engine") saveEngine(S.scope, readEngineForm());
    else if (act === "set-path") setCliPath(b.dataset.provider, cliPathState(b.dataset.provider).value);
    else if (act === "clear-path") setCliPath(b.dataset.provider, null);
    else if (act === "workdir-save" || act === "workdir-clear" || act === "workdir-choose" || act === "workdir-access") workdirAct(act, b);
    else if (act.indexOf("note-") === 0) noteAct(act, b);
    else if (act === "make-first") changePolicy({first: b.dataset.provider});
    else if (act === "check-update") checkForUpdates();
    else routinesLimits(act, b);
  }

  /* ---------------------------------------------------------------- gap routines-limits: Limits, Notifications and Recurring work (docs/notes/GAP2-routines-limits.md)
     The words and the checks are in limits_view.js and recurring_view.js; this is only what is fetched, kept while the owner types, and clicked. */
  const LV = () => root.LimitsView || null;
  const RV = () => root.RecurringView || null;

  // A group is not redrawn while the owner is typing in it (a repaint would take the focus and the caret away); what was typed is kept in the state, so the
  // next repaint, after Save or the next event, shows it. `force` is for the select that changes the form's own fields.
  const typingIn = el => {
    const a = doc.activeElement;
    return !!(a && el && el.contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && a.type !== "checkbox" && a.type !== "button");
  };
  // A repaint replaces the group's elements, so the control the owner was on from the keyboard would lose focus to the page. The group remembers which control it
  // was (what it does and for which row, not the element) and gives focus to the same one again. A confirm that takes the place of its button is met on "No", the safe
  // answer; a control that is gone (the row was removed) leaves focus on the group's heading, which takes focus for this only (tabindex -1). A button that is
  // disabled while its action runs cannot hold focus, so the group keeps the key for the next repaint (when the action ends) if focus is still nowhere.
  const KEEP_MS = 10000;
  const FOCUS_AFTER = {"rec-delete": "rec-delete-no", "rec-delete-no": "rec-delete", "rec-delete-yes": "rec-delete"};
  const sameControl = (x, k) => x.tagName === k.tag && (x.dataset.act || "") === k.act && (x.dataset.id || "") === k.id &&
    (x.dataset.input || "") === k.input && ("guard" in x.dataset) === k.guard;
  function paintGroup(el, html) {
    if (!el) return false;
    const a = doc.activeElement;
    const kept = el.__kept && Date.now() - el.__kept.at < KEEP_MS && (!a || a === doc.body) ? el.__kept.key : null;
    const key = a && a !== el && el.contains(a) && a.dataset ? {tag: a.tagName, act: a.dataset.act || "", id: a.dataset.id || "", input: a.dataset.input || "", guard: "guard" in a.dataset} : kept;
    const drawn = ctx.paint(el, html);
    if (drawn) el.__kept = null;
    if (drawn && key) {
      const all = Array.from(el.querySelectorAll("button, input, select, textarea"));
      const after = FOCUS_AFTER[key.act];
      const next = all.find(x => sameControl(x, key)) || (after && all.find(x => sameControl(x, Object.assign({}, key, {act: after})))) || el.querySelector("h3");
      if (next) {
        next.focus();
        if (doc.activeElement !== next) el.__kept = {key, at: Date.now()};
        if (next.tagName === "INPUT" && next.type === "text") { const n = next.value.length; try { next.setSelectionRange(n, n); } catch (e) { /* no caret in this input */ } }
      }
    }
    return drawn;
  }
  // `force` repaints although the owner is in a text field: for Enter, which finishes the typing and saves.
  function paintLimits(force) { if (LV() && (force === true || !typingIn($("set-limits")))) paintGroup($("set-limits"), LV().limitsHtml(S.limits, S.limitsForm)); }
  // "Quiet right now." follows this page's clock, with the same twin of the rule the notices obey (ChatAttention.windowActive), not the server's reading at the
  // last fetch, which is minutes old by the time the window begins or ends. No twin or no answer yet: the form carries nothing and the server's reading is used.
  const quietNowOf = () => {
    const twin = root.ChatAttention && root.ChatAttention.windowActive;
    return typeof twin === "function" && S.notices ? {quietNow: !!twin(attentionPrefs().quiet, new Date())} : {};
  };
  function paintNotices(force) { if (LV() && (force === true || !typingIn($("set-notices")))) paintGroup($("set-notices"), LV().noticesHtml(S.notices, Object.assign({}, S.noticesForm, quietNowOf()))); }
  function recDraft() {
    if (!S.recForm.draft && RV()) S.recForm.draft = Object.assign({}, RV().DEFAULT_DRAFT);
    return S.recForm.draft || {};
  }
  function paintRecurring(force) {
    if (!RV() || (force !== true && typingIn($("set-recurring")))) return;
    const teams = S.departments.filter(d => isObj(d) && d.id).map(d => ({id: d.id, name: d.name || d.id}));
    paintGroup($("set-recurring"), RV().recurringHtml(S.recurring, Object.assign({}, S.recForm, {draft: recDraft(), now: Date.now(), teams})));
  }

  // The notices obey what the owner chose: the window and the cap come from the last read of /api/ops/attention. Unknown until it was read.
  const attentionPrefs = () => ({
    quiet: S.notices && isObj(S.notices.quiet_hours) ? S.notices.quiet_hours : null,
    nudges: S.notices && Number.isInteger(S.notices.nudges_per_hour) ? S.notices.nudges_per_hour : null,
  });

  async function fetchRecurring() {
    if (!RV()) return;
    const got = await RV().load(api);
    if (got.ok) { S.recurring = got.list; if (S.recForm.error[""]) S.recForm.error = {}; }
    else if (S.recurring === null) S.recForm.error = {"": got.error};
    for (const id of Object.keys(S.recForm.open)) {                                   // a history that is open stays current
      const h = await RV().history(api, id);
      if (h.ok) S.recForm.open[id] = h.runs;
    }
    paintRecurring();
  }
  const refetchRecurring = SutraEvents.coalesce(single(fetchRecurring), COALESCE_MS);

  async function saveLimit(raw, force) {
    S.limitsForm = Object.assign({}, S.limitsForm, {busy: true, saved: false, error: ""});
    paintLimits(force);
    const r = await LV().saveLimit(api, raw);
    limitsWrites += 1;
    if (r.ok && isObj(r.state)) S.limits = r.state;
    S.limitsForm = r.ok ? {saved: true} : {raw, error: r.error};
    paintLimits(force);
    renderNeeds();
  }

  async function saveGuard(enabled) {
    S.limitsForm = Object.assign({}, S.limitsForm, {busy: true, saved: false, error: ""});
    paintLimits();
    const r = await LV().saveGuard(api, enabled);
    limitsWrites += 1;
    if (r.ok && isObj(r.state)) S.limits = r.state;
    S.limitsForm = r.ok ? {saved: true} : Object.assign({}, S.limitsForm, {busy: false, error: r.error});
    paintLimits();
    renderNeeds();
    refetchDepartments();                                                              // switching the guard off may start work that waited for it
  }

  async function continueGuard() {
    const r = await LV().continueGuard(api);
    limitsWrites += 1;
    if (r.ok && isObj(r.state)) S.limits = r.state;
    else showBanner({text: r.error});
    renderNeeds();
    if (S.pane === "settings") paintLimits();
    refetchDepartments();
  }

  const noticeInput = name => { const el = $("set-notices").querySelector('[data-input="' + name + '"]'); return el ? el.value : ""; };
  const readNotices = () => ({start: noticeInput("quiet_start"), end: noticeInput("quiet_end"), nudges: noticeInput("nudges_per_hour")});

  async function saveNotices(form, force) {
    S.noticesForm = Object.assign({}, form, {busy: true});
    paintNotices(force);
    const r = await LV().saveNotices(api, form);
    limitsWrites += 1;
    if (r.ok && isObj(r.state)) { S.notices = r.state; S.noticesForm = {saved: true}; }
    else S.noticesForm = Object.assign({}, form, {error: r.error});
    paintNotices(force);
    renderNeeds();                                                                     // a window that now covers this minute may change what the notices do
  }

  async function recAct(act, id) {
    const rf = S.recForm;
    if (act === "rec-add") {
      Object.assign(rf, {busy: true, saved: false, error: {}});
      paintRecurring();
      const r = await RV().create(api, recDraft());
      rf.busy = false;
      if (r.ok) { rf.saved = true; recDraft().text = ""; await fetchRecurring(); } else { rf.error = {"": r.error}; paintRecurring(); }
      return;
    }
    if (act === "rec-delete" || act === "rec-delete-no") { rf.confirm = act === "rec-delete" ? id : ""; paintRecurring(); return; }
    if (act === "rec-history") {
      if (Array.isArray(rf.open[id])) delete rf.open[id];
      else rf.open[id] = (await RV().history(api, id)).runs;
      paintRecurring();
      return;
    }
    Object.assign(rf, {busy: true, error: {}, saved: false});
    paintRecurring();
    let r;
    if (act === "rec-run") r = await RV().runNow(api, id);
    else if (act === "rec-toggle") r = await RV().toggle(api, (S.recurring || []).find(x => isObj(x) && x.id === id));
    else r = await RV().remove(api, id);
    rf.busy = false;
    rf.confirm = "";
    if (!r.ok) rf.error = {[id]: r.error};
    else if (act === "rec-delete-yes") delete rf.open[id];
    await fetchRecurring();
    if (act === "rec-run") { refetchDepartments(); refetchHeads(); }
  }

  function routinesLimits(act, b) {
    if (!LV() || !RV()) return;
    if (act === "save-limit") saveLimit(($("set-limits").querySelector('[data-input="monthly_usd"]') || {}).value || "");
    else if (act === "clear-limit") saveLimit("");
    else if (act === "guard-continue") continueGuard();
    else if (act === "save-notices") saveNotices(readNotices());
    else if (act === "clear-quiet") saveNotices(Object.assign(readNotices(), {start: "", end: ""}));
    else if (/^rec-/.test(act)) recAct(act, b.dataset.id || "");
  }

  // "Saved." says what the server holds, so it goes as soon as a field of its group is edited. The group is not repainted while the owner types (typingIn), so
  // the line is cleared in place as well as in the state that the next repaint reads (QA firstrun-settings: it stayed beside a value the server did not have).
  function staleSaved(t) {
    const group = t && t.closest ? t.closest(".setgrp") : null;
    if (!group) return;
    const line = group.querySelector(".setstatus");
    if (line) line.textContent = "";
    const key = group.dataset.group;
    if (key === "engine") S.saved = false;
    else if (key === "limits") S.limitsForm = Object.assign({}, S.limitsForm, {saved: false});
    else if (key === "notices") S.noticesForm = Object.assign({}, S.noticesForm, {saved: false});
    else if (key === "notes") NS.saved = "";
    else if (key === "recurring") S.recForm.saved = false;
  }

  // What the owner types is kept in the state, so a repaint (the limits move with every task) never takes it away; a switch and a select act at once.
  function wireRoutinesLimits() {
    const pane = $("pane-settings");
    pane.addEventListener("input", e => {
      const t = e.target;
      staleSaved(t);
      const name = t && t.dataset ? t.dataset.input : "";
      if (name === "monthly_usd") S.limitsForm = Object.assign({}, S.limitsForm, {raw: t.value, saved: false});
      else if (name === "quiet_start") S.noticesForm = Object.assign({}, S.noticesForm, {start: t.value});
      else if (name === "quiet_end") S.noticesForm = Object.assign({}, S.noticesForm, {end: t.value});
      else if (name === "nudges_per_hour") S.noticesForm = Object.assign({}, S.noticesForm, {nudges: t.value});
      else if (name === "rec_text") recDraft().text = t.value;
      else if (name === "rec_time") recDraft().time = t.value;
      else if (name === "rec_minute") recDraft().minute = t.value;
    });
    pane.addEventListener("keydown", e => {                                                          // Enter in a field of Limits or Notifications saves, like its Save button
      const t = e.target;
      if (e.key !== "Enter" || e.isComposing || !t || !t.dataset || !LV()) return;
      if (t.dataset.input === "monthly_usd") { e.preventDefault(); if (S.limitsForm.busy !== true) saveLimit(t.value, true); }
      else if (/^(quiet_start|quiet_end|nudges_per_hour)$/.test(t.dataset.input || "")) { e.preventDefault(); if (S.noticesForm.busy !== true) saveNotices(readNotices(), true); }
    });
    pane.addEventListener("change", e => {
      const t = e.target;
      if (!t || !t.matches) return;
      if (t.matches("input[data-guard]")) { if (LV()) saveGuard(t.checked); return; }
      const name = t.dataset ? t.dataset.input : "";
      if (name === "rec_dept") recDraft().dept_id = t.value;
      else if (name === "rec_weekday") recDraft().weekday = t.value;
      else if (name === "rec_every") { recDraft().every = t.value; paintRecurring(true); }                 // the cadence decides which fields the form shows
    });
  }

  // Enter in a text, number, time or date field presses the Save of its own place, as in a form (the Settings groups have no <form>): a note row, the CLI file
  // box or the add form of Recurring work first, else the group's. A disabled button (a save in flight) is left alone. The button takes the focus first, as
  // a mouse press would: a group is not repainted while a field of it has the focus (typingIn), so the answer of a save would not show. A key that another
  // handler of the pane already took (preventDefault) is left to it.
  const ENTER_SAVES = '[data-act="save-limit"], [data-act="save-notices"], [data-act="save-engine"], [data-act="note-add"], [data-act="note-save"], ' +
    '[data-act="rec-add"], [data-act="set-path"]';
  function wireEnterSaves() {
    $("pane-settings").addEventListener("keydown", e => {
      const t = e.target;
      if (e.defaultPrevented || e.key !== "Enter" || e.isComposing || e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
      if (!t || t.tagName !== "INPUT" || !/^(text|number|time|date)$/.test(t.type)) return;
      const scope = t.closest(".noteadd, li.note, .setpath, .setgrp");
      const b = scope ? scope.querySelector(ENTER_SAVES) : null;
      if (!b || b.disabled) return;
      e.preventDefault();
      b.focus();
      b.click();
    });
  }

  /* ---------------------------------------------------------------- events */
  function setLive(state) {
    S.live = state;
    if (S.graphView) S.graphView.setLive(state);
    if (S.chartView) S.chartView.setLive(state);
  }

  // One event is an invalidation: refetch what it names (coalesced), keep nothing from its body but a few small facts.
  function onEvent(type, data) {
    const d = isObj(data) ? data : {};
    if (S.watch) S.watch.onEvent(type);
    switch (type) {
      case "chat.partial":
        if (d.session_id === ORG && composer()) composer().partial(d);
        break;
      case "chat.turn":
        if (d.session_id === ORG) {
          S.turn.seen = true;
          S.turn.resumed = false;
          S.awaitGraph = true;
          S.turn.phase = clean(d.phase);
          S.turn.n = Number.isFinite(d.turn) ? d.turn : S.turn.n;
          S.turn.active = S.turn.phase !== "done" && S.turn.phase !== "error" && S.turn.phase !== "";
          renderProgress();
          renderComposer();
          if (!S.turn.active) reloadMessages();
        }
        break;
      case "chat.message":
        if (d.session_id === ORG) {
          pillMoved();
          if (isObj(d.message)) { mergeMessages([d.message], false); renderChat(); }
          refetchMessages();
        } else if (S.graphView && isObj(d.message)) {
          S.graphView.noteMessage(d.session_id, d.message.id);
        }
        break;
      case "chart.changed": refetchChart(); refetchGraph(); refetchDepartments(); refetchNeeds(); break;                // a rename also changes the rail and the Needs-you lines
      case "chart.approval": refetchMessages(); break;
      case "graph.updated": refetchGraph(); break;
      case "task.updated": refetchDepartments(); refetchHeads(); refetchLimits(); if (S.recurring !== null) refetchRecurring(); break;
      case "connector.health": refetchLimits(); break;                                                // a plan window moved: the guard's line may change
      case "connector.switch": if (d.session_id === ORG) { pillMoved(); renderPill(); } break;           // the org chat's session now runs on the other provider
      case "needs_you.changed": refetchNeeds(); break;
      case "server.resync": loadAll(); break;
      default: break;
    }
  }

  /* ---------------------------------------------------------------- start */
  function deepLink() {
    const q = new root.URLSearchParams(root.location.search);
    const pane = q.get("pane");
    return {pane: pane === "chart" ? "chart" : (pane === "graph" || q.get("node") ? "graph" : (q.get("change") ? "chart" : "graph")),
      node: q.get("node") || "", change: q.get("change") || ""};
  }

  function applyDeepLink(link) {
    if (link.node && S.graphView) S.graphView.select(link.node);
    const seq = Number(link.change);
    if (link.change && Number.isFinite(seq) && S.chartView) S.chartView.selectChange(seq);
  }

  async function boot() {
    themeApply();
    barInit();
    try { root.matchMedia("(prefers-color-scheme: light)").addEventListener("change", themeApply); } catch (e) { /* no matchMedia */ }
    BARWIDE.addEventListener("change", barInit);
    S.panel = root.NodePanel.mount($("nodepanel"), {getGraph: () => S.graph, navigate: url => root.location.assign(url)});
    if ($("teamchat")) S.team = root.NodePanel.mount($("teamchat"), {inline: true, idPrefix: "npi", getGraph: () => S.graph, navigate: url => root.location.assign(url),
      openSettings: group => selectPane("settings", {group}), onClose: () => { if (S.chat.sid !== ORG) showOrgChat(); }});
    S.watch = SV().watchHealth(api, h => { S.health = h; paintConnectors(); paintModels(); }, () => {});
    if (root.HeadsUpView) S.seen = root.HeadsUpView.loadSeen(storage());
    if (root.ChatAttention) S.attention = protect("ChatAttention.create", () => root.ChatAttention.create({onOpen: openAttention, prefs: attentionPrefs})) || null;
    // a quiet team and the age of each ask move with time, not with events: read the lane again and redraw the strip every minute
    root.setInterval(() => { refetchHeads(); refetchLimits(); renderNeeds(); if (S.pane === "settings" && S.recurring !== null) refetchRecurring(); }, MINUTE_MS);
    const link = deepLink();
    wire();
    wireFind();
    selectPane(link.pane, {reveal: link.pane !== "graph" || !!link.node, focus: false});
    renderProgress();
    renderComposer();
    renderBar();
    S.stream = SutraEvents.connect({url: "/api/events", onEvent, onState: setLive, pollFn: pollAll, pollMs: POLL_MS});
    // the first-run welcome card (welcome.js): mounted outside #sview, shown until the owner says Got it (stored on the server)
    if (root.Welcome) Promise.resolve().then(() => root.Welcome.start(doc, api)).catch(e => { if (root.console) root.console.error("HomePage: welcome failed", e); });
    await loadAll();
    applyDeepLink(link);
  }

  function wire() {
    $("smsgs").addEventListener("click", onChatClick);
    if ($("cswitch")) { $("cswitch").addEventListener("click", onSwitchClick); $("cswitch").addEventListener("keydown", onSwitchKey); }
    if ($("spill")) { $("spill").addEventListener("click", onPillClick); $("spill").addEventListener("change", onPillChange); }
    $("ssend").addEventListener("click", e => {
      if ($("ssend").dataset.act !== "composer-stop") send($("sbox").value);
      else if (!root.ChatComposer || root.ChatComposer.stopPress(e)) stopDirect();          // the 2nd click of a double-click on Send is not a Stop
    });
    $("sbar").addEventListener("click", e => {
      const b = e.target.closest("[data-act]");
      const c = composer();
      if (!b || !c) return;
      if (b.dataset.act === "composer-mode") c.setMode(b.dataset.mode);
      else if (b.dataset.act === "composer-attach") { const input = $("sbar").querySelector(".ccinput"); if (input) input.click(); }
      else if (b.dataset.act === "composer-remove") c.removeFile(b.dataset.key);
    });
    $("sbar").addEventListener("change", e => {
      const t = e.target;
      const c = composer();
      if (!c || !t || !t.classList || !t.classList.contains("ccinput")) return;
      c.addFiles(t.files);
      t.value = "";
    });
    $("sbox").addEventListener("keydown", e => {
      if (root.ChatComposer ? root.ChatComposer.sendKey(e) : (e.key === "Enter" && !e.shiftKey && !e.isComposing)) { e.preventDefault(); send($("sbox").value); }
    });
    wireComfort();
    wireFront();
    $("sbanner").addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.act === "open-settings") selectPane("settings", {group: "connectors"});
      else if (b.dataset.act === "retry-load") loadAll();
      else clearBanner();
    });
    $("needs").addEventListener("click", onNeedsClick);
    $("pane-settings").addEventListener("click", onSettingsClick);
    wireRoutinesLimits();
    wireEnterSaves();
    $("pane-settings").addEventListener("input", e => {
      if (e.target && e.target.matches && e.target.matches("input[data-path]")) cliPathState(e.target.dataset.path).value = e.target.value;
      else if (e.target && e.target.matches && e.target.matches("input[data-workdir-input]")) { WD.value = e.target.value; WD.dirty = true; }
    });
    $("pane-settings").addEventListener("change", e => {
      const t = e.target;
      if (t && t.matches && t.matches("select[data-scope]")) { S.scope = t.value; S.settings = null; S.errors = {}; loadEngineSettings(); }
      else if (t && t.matches && t.matches("input[data-policy-on]")) changePolicy({enabled: {[t.dataset.policyOn]: t.checked}});
      else if (t && t.matches && t.matches('input[data-act="toggle-auto-update"]')) toggleAutoUpdate(t.checked);
      else if (t && t.matches && t.matches("select[data-policy-model]")) changePolicy({model: {[t.dataset.policyModel]: t.value}});
    });
    doc.querySelector(".stoggle").addEventListener("click", e => {
      const b = e.target.closest("[data-show]");
      if (!b) return;
      doc.body.classList.toggle("sp-preview", b.dataset.show === "right");
      markRail();
    });
    $("gochat").addEventListener("click", () => selectPane("chat"));
    doc.querySelectorAll("#rail [data-pane]").forEach(b => b.addEventListener("click", () => selectPane(b.dataset.pane, {group: b.dataset.group || ""})));
    doc.addEventListener("click", e => {
      const b = e.target.closest && e.target.closest("[data-themepick]");
      if (b) { S.theme = b.dataset.themepick; try { root.localStorage.setItem("j2theme", S.theme); } catch (err) { /* storage may be blocked */ } themeApply(); }
      if (!BARWIDE.matches && barOpen() && (!e.target.closest(".rail, #railtoggle") || e.target.closest(".rail [data-pane], #gochat, .railteam"))) barSet(false);
    });
    $("railtoggle").addEventListener("click", () => barSet(!barOpen(), true));
    doc.addEventListener("keydown", e => {
      if (e.key === "Escape" && !BARWIDE.matches && barOpen() && !(S.panel && S.panel.isOpen())) { e.stopImmediatePropagation(); barSet(false); $("railtoggle").focus(); }
    }, true);
  }

  // GAP-chat-comfort: the draft and the size of the box, Esc stops a direct answer, a pasted or dropped file attaches, the reader's gestures, the pill.
  function wireComfort() {
    const box = $("sbox");
    const d = drafts();
    if (d && box.value === "") box.value = d.load(ORG);
    growBox();
    box.addEventListener("input", () => { if (drafts()) drafts().save(ORG, box.value); growBox(); });
    box.addEventListener("keydown", e => {
      if (e.key !== "Escape" || e.isComposing || (S.panel && S.panel.isOpen())) return;
      const c = composer();
      const turn = c ? c.state().turn : null;
      if (directOn() && turn && turn.active && !turn.stopping) { e.preventDefault(); stopDirect(); }
    });
    box.addEventListener("paste", e => { const c = composer(); if (c && !box.disabled && c.take(e.clipboardData, {pasted: true})) e.preventDefault(); });
    $("scompose").addEventListener("dragover", e => { if (composer() && root.ChatComposer.hasFiles(e.dataTransfer)) e.preventDefault(); });
    $("scompose").addEventListener("drop", e => { const c = composer(); if (c && !box.disabled && c.take(e.dataTransfer)) e.preventDefault(); });
    if ($("sjump")) $("sjump").addEventListener("click", e => { if (e.target.closest("[data-act=jump-latest]")) jumpLatest(); });
    if (root.ChatScroll) {
      root.ChatScroll.pin($("smsgs"), () => !S.scroll.parked);
      root.ChatScroll.watch($("smsgs"), ev => {
        const before = S.scroll.pill;
        S.scroll = root.ChatScroll.intent(S.scroll, Object.assign(ev, {lastId: root.ChatScroll.lastId(S.messages)}));
        if (S.scroll.pill !== before) renderJump();
      });
    }
  }

  function renderAll() {
    renderChat();
    renderComposer();
    renderProgress();
    renderNeeds();
    renderRail();
    renderBanner();
    renderFront();
    if (S.pane === "settings") renderSettings();
  }

  const HomePage = {
    boot, loadAll, renderChat, send, answerNeeds, selectPane, renderRail, renderNeeds, onEvent, themeApply, barSet, renderSettings, saveEngine, testConnector,
    signIn, cancelSignIn, errorWords, poll: pollAll, state: () => S, retryTask, renderFront, setPlace, answerFront, decideFront, sendFront,
  };
  root.HomePage = HomePage;
  const start = () => protect("boot", () => boot().catch(e => { if (root.console) root.console.error("HomePage: boot failed", e); }));
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start);
  else start();
})(globalThis);
