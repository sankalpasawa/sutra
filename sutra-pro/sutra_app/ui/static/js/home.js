/* home.js - the controller of the Home page (work package UI-7; docs/design/ui.md sections 6.6, 7, 8, 9 and 10; S1-contracts-03, S1-contracts-08,
   S3-web-06, S3-web-13, S4-fnodes-12; D18).

   Home is the J2 Simple skeleton (home.html). The left column is the org chat, the owner's talk with the chat agent: the Root node's one rolling session
   cs_org, so there is no task picker. The right column is J2's preview slot: the "Needs you" strip and one pane at a time, the Workflow graph, the Org
   chart or Settings, chosen from the rail. Everything it draws comes from the pure modules (ChatView, SettingsView) or from the views of UI-5 and UI-6
   (GraphView, OrgChartView, NodePanel); this file fetches, keeps them current from the event stream and handles clicks.

   Functions (docs/design/ui.md 6.6): boot, loadAll, renderChat, send, answerNeeds, selectPane, renderRail, renderNeeds, onEvent, themeApply, barSet,
   renderSettings, saveEngine, testConnector, signIn. They are on window.HomePage with the state (HomePage.state()), so a test can look at both.

   Reads: GET /api/chats/cs_org and its messages, /api/chart, /api/chart/changes, /api/graph?level=chart, /api/departments, /api/needs-you, /api/health,
   /api/engine/settings. Writes (each with X-Sutra-Token, through SutraCtx.api): POST /api/chats/cs_org/messages and .../retry, POST /api/chats/{department
   session}/messages (an answer to a team's question, never to cs_org), the connector Test and Sign in calls, PUT /api/engine/settings.

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
    session: null, messages: [], lastId: 0, pending: [], localSeq: 0, answers: {},
    departments: [], departmentsLoaded: false, needs: [], needsLoaded: false,
    graph: null, chart: null, changes: [],
    health: null, settings: null, scope: "", errors: {}, saved: false, saving: false, conn: {test: {}, signin: null}, signer: null,
    pane: "graph", turn: {seen: false, phase: "", n: 0, active: false}, awaitGraph: false,
    banner: null, blocked: "", sending: false, live: "offline", theme: null, loaded: false,
    graphView: null, chartView: null, panel: null, stream: null, watch: null, values: null,
  };

  /* ---------------------------------------------------------------- errors in words */
  // errorWords(e) -> {text, settings}: the sentence for an ApiError and whether the banner should link to Settings.
  function errorWords(e) {
    const status = e && Number.isInteger(e.status) ? e.status : 0;
    const code = e && typeof e.code === "string" ? e.code : "";
    const said = clean(e && e.message);
    if (status === 401 || code === "bad_token") return {text: NO_TOKEN, settings: false, blocked: true};
    if (code === "provider_unavailable" || code === "cli_missing") return {text: said || "No model is available right now.", settings: true};
    if (status === 429) return {text: TOO_MANY, settings: false};
    if (status === 0 || code === "network") return {text: DOWN, settings: false, retry: true};
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

  async function fetchSession() { S.session = await api.get("/api/chats/" + ORG); }

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
    renderChat();
    renderComposer();
  }

  function mergeMessages(list, replace) {
    const byId = new Map(replace ? [] : S.messages.map(m => [m.id, m]));
    list.forEach(m => { if (isObj(m) && m.id !== undefined) byId.set(m.id, m); });
    S.messages = Array.from(byId.values()).sort((a, b) => a.id - b.id);
    S.lastId = S.messages.reduce((n, m) => (typeof m.id === "number" && m.id > n ? m.id : n), 0);
    S.pending = S.pending.filter(p => p.serverId === null || !S.messages.some(m => m.id === p.serverId));
  }

  async function fetchChart() {
    const [chart, changes] = await Promise.all([api.get("/api/chart"), api.get("/api/chart/changes", {limit: 50})]);
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
    if (S.settings) paintEngine();
  }

  async function fetchNeeds() {
    const list = await api.get("/api/needs-you");
    S.needs = Array.isArray(list) ? list : [];
    S.needsLoaded = true;
    renderNeeds();
    renderChat();
  }

  async function fetchHealth() { S.health = await api.get("/api/health"); paintConnectors(); }

  const reloadMessages = single(() => fetchMessages(true));
  const refetchMessages = SutraEvents.coalesce(single(() => fetchMessages(false)), COALESCE_MS);
  const refetchGraph = SutraEvents.coalesce(single(fetchGraph), COALESCE_MS);
  const refetchChart = SutraEvents.coalesce(single(fetchChart), COALESCE_MS);
  const refetchNeeds = SutraEvents.coalesce(single(fetchNeeds), COALESCE_MS);
  const refetchDepartments = SutraEvents.coalesce(single(fetchDepartments), COALESCE_MS);

  const settled = list => Promise.allSettled(list.map(f => f()));

  // Everything Home shows, once: on load, on server.resync, and for "Retry". Each part fails on its own and keeps what it had.
  async function loadAll() {
    const results = await settled([fetchSession, () => fetchMessages(true), fetchChart, fetchGraph, fetchDepartments, fetchNeeds, fetchHealth]);
    const failed = results.filter(r => r.status === "rejected");
    if (failed.length === results.length) handleFetchError(failed[0].reason);
    else if (failed.length === 0) clearBanner();
    failed.forEach(r => { const w = errorWords(r.reason); if (w.blocked) showBanner(w); });
    S.loaded = true;
    renderAll();
    return results;
  }

  // What polling asks every 2 s when the stream is down (docs/design/ui.md 9, X4).
  function pollAll() {
    return settled([() => fetchMessages(false), fetchGraph, fetchChart, fetchNeeds, fetchDepartments]);
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

  // The answer of every card the owner has dealt with: what the owner clicked here, a message the server marks answered, and a team question
  // that /api/needs-you no longer lists (then the card just reads "Answered").
  function answersMap() {
    const out = Object.assign({}, S.answers);
    S.messages.forEach(m => {
      if (m.kind !== "card" || !isObj(m.card) || hasOwn(out, m.id)) return;
      const c = m.card;
      if (m.answered_by !== null && m.answered_by !== undefined) out[m.id] = "";
      else if (c.type === "needs_you" && S.needsLoaded &&
        !S.needs.some(n => String(n.message_id) === String(c.question_message_id) && (!n.dept_id || !c.dept_id || n.dept_id === c.dept_id))) out[m.id] = "";
    });
    return out;
  }

  function startHtml() {
    if (hasWritten() || S.messages.length === 0) return "";
    return '<div class="sb team starter" data-start="true"><small>Sutra</small>Try one of these, or write your own below.' +
      '<div class="cards">' + EXAMPLES.map(t => '<button type="button" data-brief="' + esc(t) + '">' + esc(t) + "</button>").join("") + "</div></div>";
  }

  function renderChat() {
    const shown = S.messages.concat(S.pending.map(p => p.msg));
    const session = S.session || {kind: "org", writable: true, status: "active", title: "Sutra"};
    const html = root.ChatView.transcript(session, shown, {deptName: "", live: true, answers: answersMap(), deptSessions: deptSessions()}) + startHtml();
    if (!ctx.paint($("smsgs"), html)) return;
    const end = () => { const el = $("smsgs"); el.scrollTop = el.scrollHeight; };
    end();
    if (root.requestAnimationFrame) root.requestAnimationFrame(end);
  }

  function renderComposer() {
    const session = S.session || {kind: "org", writable: true, status: "active", title: "Sutra"};
    const st = root.ChatView.composerState(session, {busy: S.turn.active === true, asking: false, blocked: S.blocked});
    $("scompose").hidden = st.hidden;
    $("sbox").disabled = st.disabled;
    $("ssend").disabled = st.disabled || S.sending;
    $("sbox").placeholder = S.messages.some(m => m.role === "user") ? "Write a message…" : "Tell Sutra what you need…";
    const note = $("snote");
    note.hidden = st.note === "";
    note.textContent = st.note;
  }

  function renderProgress() {
    const el = $("sprog");
    const at = hasOwn(PHASE_AT, S.turn.phase) ? PHASE_AT[S.turn.phase] : -1;
    el.hidden = !S.turn.seen || S.turn.phase === "error";
    ctx.paint(el, STAGES.map((x, i) => '<div class="' + (i < at ? "done" : i === at ? "on" : "") + '"><i></i>' + esc(x) + "</div>").join(""));
    $("sstatus").textContent = hasOwn(PHASE_SENTENCE, S.turn.phase) ? PHASE_SENTENCE[S.turn.phase] : "";
  }

  // The owner writes. The bubble shows at once (pending, dimmed); the box keeps its text until the server accepts the line, so a refusal (no usable
  // connector, too many waiting) loses nothing.
  async function send(value, choice) {
    const body = text(value).trim();
    if (body === "" || S.blocked !== "" || (S.sending && !choice)) return false;
    const entry = {serverId: null, msg: {id: "local-" + (++S.localSeq), session_id: ORG, role: "user", who: "user", kind: "text", text: body, card: null,
      pause: null, answered_by: null, task_id: null, state: "pending", at: ""}};
    S.pending.push(entry);
    S.awaitGraph = true;
    S.sending = true;
    renderChat();
    renderComposer();
    try {
      const accepted = await api.post("/api/chats/" + ORG + "/messages", choice ? {text: body, choice} : {text: body});
      entry.serverId = isObj(accepted) && Number.isInteger(accepted.message_id) ? accepted.message_id : null;
      if ($("sbox").value.trim() === body) $("sbox").value = "";
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
    }
  }

  /* ---------------------------------------------------------------- the strip "Needs you", the rail, the panes */
  function needLine(item) {
    const ask = root.ChatView.parseAsk(item.text);
    const question = ask.qs.length ? ask.qs[0].q : "";
    const said = root.ChatView.stripTag(question || ask.say || item.text).split("\n")[0].trim();
    return clean(item.dept_name) + (said ? ": " + said : "");
  }

  function renderNeeds() {
    const items = S.needs;
    $("needs").classList.toggle("on", items.length > 0);
    ctx.paint($("needs"), '<h2>Needs you <span class="needbadge" id="needcount">' + items.length + "</span></h2>" +
      (items.length ? items.map(i => '<div class="needitem"><span>' + esc(needLine(i)) + '</span><button type="button" data-needmsg="' + esc(i.message_id) + '">Answer in Chat</button></div>').join("")
        : '<span class="none">Nothing needs you right now.</span>'));
    barBadge();
  }

  function statusWord(status) { return hasOwn(STATUS_WORDS, status) ? STATUS_WORDS[status] : "idle"; }

  function renderRail() {
    const rows = S.departments.filter(isObj).map(d => '<a class="railteam st-' + esc(d.node_status || "idle") + '" href="/d/' + enc(d.id) + '/" data-dept="' + esc(d.id) + '">' +
      '<span class="rtname">' + esc(d.name || d.id) + '</span><span class="rtstat">' + esc(statusWord(d.node_status)) + "</span></a>");
    ctx.paint($("railteams"), rows.length ? rows.join("") : '<p class="railnone">No teams yet. Tell Sutra what you need and a team appears here.</p>');
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
  }

  // selectPane("chat"|"graph"|"chart"|"settings", {reveal, group}). reveal (default true) also shows the right column on a phone.
  function selectPane(name, options) {
    const o = isObj(options) ? options : {};
    const reveal = o.reveal !== false;
    if (name === "chat") {
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
    try { const p = root.localStorage.getItem("j2theme"); return ["light", "dark", "system"].includes(p) ? p : "dark"; } catch (e) { return "dark"; }
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
    const n = S.needs.length;
    $("barbadge").textContent = String(n);
    $("barbadge").hidden = !n;
    $("railtoggle").setAttribute("aria-label", n ? "Menu, " + n + " waiting on you" : "Menu");
  }

  /* ---------------------------------------------------------------- Settings */
  const SV = () => root.SettingsView;

  function paintAppearance() { ctx.paint($("set-appearance"), SV().appearanceHtml(themePref())); themeApply(); }
  function paintConnectors() { ctx.paint($("set-connectors"), SV().connectorsHtml(S.health, S.conn)); }
  function paintEngine() {
    ctx.paint($("set-engine"), SV().engineHtml(S.settings, {scope: S.scope, departments: S.departments, errors: S.errors, values: S.values, saved: S.saved, busy: S.saving}));
  }

  function renderSettings() {
    paintAppearance();
    paintConnectors();
    paintEngine();
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
    if (S.health === null) fetchHealth().catch(handleFetchError);
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

  function onSettingsClick(e) {
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const act = b.dataset.act;
    if (act === "test") testConnector(b.dataset.provider);
    else if (act === "signin") signIn();
    else if (act === "cancel") cancelSignIn();
    else if (act === "save-engine") saveEngine(S.scope, readEngineForm());
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
      case "chat.turn":
        if (d.session_id === ORG) {
          S.turn.seen = true;
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
          if (isObj(d.message)) { mergeMessages([d.message], false); renderChat(); }
          refetchMessages();
        } else if (S.graphView && isObj(d.message)) {
          S.graphView.noteMessage(d.session_id, d.message.id);
        }
        break;
      case "chart.changed": refetchChart(); refetchGraph(); break;
      case "chart.approval": refetchMessages(); break;
      case "graph.updated": refetchGraph(); break;
      case "task.updated": refetchDepartments(); break;
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
    S.watch = SV().watchHealth(api, h => { S.health = h; paintConnectors(); }, () => {});
    const link = deepLink();
    wire();
    selectPane(link.pane, {reveal: link.pane !== "graph" || !!link.node, focus: false});
    renderProgress();
    renderComposer();
    S.stream = SutraEvents.connect({url: "/api/events", onEvent, onState: setLive, pollFn: pollAll, pollMs: POLL_MS});
    await loadAll();
    applyDeepLink(link);
  }

  function wire() {
    $("smsgs").addEventListener("click", onChatClick);
    $("ssend").addEventListener("click", () => send($("sbox").value));
    $("sbox").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send($("sbox").value); } });
    $("sbanner").addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.act === "open-settings") selectPane("settings", {group: "connectors"});
      else if (b.dataset.act === "retry-load") loadAll();
      else clearBanner();
    });
    $("needs").addEventListener("click", e => { const b = e.target.closest("[data-needmsg]"); if (b) focusCard(b.dataset.needmsg); });
    $("pane-settings").addEventListener("click", onSettingsClick);
    $("pane-settings").addEventListener("change", e => {
      if (e.target && e.target.matches && e.target.matches("select[data-scope]")) { S.scope = e.target.value; S.settings = null; S.errors = {}; loadEngineSettings(); }
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

  function renderAll() {
    renderChat();
    renderComposer();
    renderNeeds();
    renderRail();
    renderBanner();
    if (S.pane === "settings") renderSettings();
  }

  const HomePage = {
    boot, loadAll, renderChat, send, answerNeeds, selectPane, renderRail, renderNeeds, onEvent, themeApply, barSet, renderSettings, saveEngine, testConnector,
    signIn, cancelSignIn, errorWords, poll: pollAll, state: () => S,
  };
  root.HomePage = HomePage;
  const start = () => protect("boot", () => boot().catch(e => { if (root.console) root.console.error("HomePage: boot failed", e); }));
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start);
  else start();
})(globalThis);
