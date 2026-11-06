/* node_panel.js - the node panel: one drawer, #nodepanel, with a Chat tab and a Details tab for every node of the graph (work package UI-6;
   docs/design/ui.md sections 6.4, 6.5, 7, 8 and 9; S3-web-05, S4-fnodes-06, S4-fnodes-10, S4-fnodes-12; D63).

   This is the DOM half; fnode_view.js and chat_view.js (strings in, strings out) draw everything it shows. The drawer follows the pattern of J2's
   Agent drawer (aside.agentdrawer, one at a time, Esc closes, focus goes to Close and comes back to the node that opened it).

   The Chat tab shows ONE session: the node's own, except that an Identity function shows its team's session (the owner's chat with the team),
   found through the department node (chatSessionFor). A department or division session has a message box; a function or step session is a read-only
   working log. A division is a lens: its messages are the team's Identity's work for that division, and a link shows the whole team's chat. The
   Details tab is the function drawer (fnode_view.js) or, for any other node, its head, its team's five functions and its links.

   While it is open the panel keeps itself current: its own SutraEvents stream (chat.message of its session, atom.updated of its node, task and graph
   updates) refetches what changed, coalesced, and a dropped stream falls back to polling the same two calls (docs/design/ui.md 9, X4).

   A classic script with ONE global, NodePanel (see sutra_ctx.js for why). It needs SutraCtx, FnodeView and ChatView, which are read when they are used. */
(function (root) {
  "use strict";

  /* ---------------------------------------------------------------- small helpers */
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const enc = encodeURIComponent;

  const FUNCTIONS = ["identity", "adaptation", "priority", "coordination", "audit"];
  const FN_TAB = {identity: "charter", adaptation: "workflows", priority: "conflicts", coordination: "timeline", audit: "audit"};
  const PAGE = 200;                  // messages per request (the server's own cap)
  const MAX_PAGES = 20;              // never more than 4,000 messages for one open
  const ATOM_PAGE = 100;             // "Show all" asks for this many atoms at a time
  const COALESCE_MS = 150;           // a burst of events is one refetch
  const SEEN = "sutra:seen:";
  const TOPICS = ["chat", "atom", "graph", "task", "needs_you"];
  const NO_TOKEN = "This page was opened without its access token. Reload it from the app.";
  const TOO_MANY = "Too many messages are waiting. I answer them one at a time.";
  const DOWN = "The app is not responding. Try again in a moment.";
  const GONE = "This chat is gone.";
  const FAILED = "Something went wrong. Try again.";

  const NEAR_PX = 48;                // a reader this close to the bottom before a repaint is following the newest line
  const BOX_MAX_PX = 200;            // the message box grows with its text up to this (chat_draft.js grow)

  const ctx = () => root.SutraCtx || null;
  const FV = () => root.FnodeView;
  const CV = () => root.ChatView;
  const CSc = () => root.ChatScroll || null;          // GAP-chat-comfort: chat_draft.js and chat_scroll.js, read when used (a J2 page injects them)
  const api = () => {
    const c = ctx();
    if (!c || !c.api) throw new Error("NodePanel needs SutraCtx (sutra_ctx.js) loaded first");
    return c.api;
  };
  const settle = p => Promise.resolve(p).then(value => ({value}), error => ({error}));

  function functionKey(n) {
    const id = text(n.id);
    const tail = id.slice(id.lastIndexOf(".") + 1);
    const found = [n.fn, clean(n.label).toLowerCase(), tail].find(k => typeof k === "string" && FUNCTIONS.includes(k));
    return found === undefined ? "" : found;
  }

  function findNode(graph, id) {
    const nodes = isObj(graph) && Array.isArray(graph.nodes) ? graph.nodes : [];
    return nodes.find(n => isObj(n) && n.id === id) || null;
  }

  // chatSessionFor(node, graph) -> the id of the session the Chat tab shows. An Identity function shows its TEAM's session (the department node's
  // chat_session_id), because Identity is the one voice of the team; its own session is a working log that the Details tab lists as atoms. Every
  // other node shows its own session. null when there is none, or when an Identity's department is not in `graph` (open() then asks the server).
  function chatSessionFor(node, graph) {
    if (!isObj(node)) return null;
    if (node.kind === "function" && functionKey(node) === "identity") {
      const dept = findNode(graph, node.dept_id);
      return dept && clean(dept.chat_session_id) !== "" ? dept.chat_session_id : null;
    }
    return clean(node.chat_session_id) !== "" ? node.chat_session_id : null;
  }

  const wants = id => current !== null && FUNCTIONS.includes(clean(id));

  /* ---------------------------------------------------------------- the browser's storage, never trusted */
  function markSeen(sid, lastId) {
    if (!sid || !lastId) return;
    try {
      root.localStorage.setItem(SEEN + sid, String(lastId));
    } catch (e) {
      return;                    // private window, blocked or full: the dot simply stays
    }
    try {
      root.document.dispatchEvent(new root.CustomEvent("sutra:seen", {detail: {session: sid, id: lastId}}));
    } catch (e) {
      /* no CustomEvent (a stub DOM) */
    }
  }

  /* ---------------------------------------------------------------- the panel */
  let current = null;                // the panel mounted last: the static NodePanel.wants / openFunction act on it

  // The text of a send that failed, and what it does to the box.
  function problemOf(err) {
    const status = err && Number.isFinite(err.status) ? err.status : 0;
    const code = err && typeof err.code === "string" ? err.code : "";
    const said = err && typeof err.message === "string" ? err.message : "";
    if (status === 401 || code === "bad_token") return {text: NO_TOKEN, block: NO_TOKEN};
    if (status === 403 || code === "read_only") return {text: said || "This chat is read-only.", readOnly: true};
    if (status === 404) return {text: GONE, gone: true};
    if (status === 409) return {text: said || CV().BUSY};
    if (status === 429) return {text: TOO_MANY};
    if (status === 0 || code === "network") return {text: DOWN};
    return {text: status >= 500 || !said ? FAILED : said};
  }

  function mount(host, options) {
    if (!host || typeof host.addEventListener !== "function") throw new TypeError("NodePanel.mount: a host element is needed");
    const opts = isObj(options) ? options : {};
    const getGraph = typeof opts.getGraph === "function" ? opts.getGraph : () => null;
    const navigate = typeof opts.navigate === "function" ? opts.navigate : url => root.location.assign(url);
    const doc = host.ownerDocument || root.document;
    const withAgent = () => (typeof opts.withAgent === "boolean" ? opts.withAgent : (ctx() && ctx().boot && ctx().boot.page === "dept") === true);
    const deptPage = () => (ctx() && typeof ctx().dept === "string" ? ctx().dept : "");

    let gen = 0;                     // bumped by every open() and close(): an answer for an older one is dropped
    let st = null;                   // null when closed, else everything about the node on show
    let refs = null;                 // the skeleton's elements
    let chatRefs = null;             // the Chat tab's elements (rebuilt when the tab is)
    let drafts = null;               // the per-chat drafts (ChatDraft), made on first use
    const composers = new Map();     // session id -> its composer controller: the mode, the files and a running turn outlive a closed panel
    const scrollMem = new Map();     // session id -> where it was read when it closed (ChatScroll.remember / restore)
    const draftStore = () => { if (!drafts && root.ChatDraft) drafts = root.ChatDraft.create(); return drafts; };

    /* ------------------------------------------------ the skeleton */
    function ensureShell() {
      if (refs) return;
      host.innerHTML = '<div class="adhead nphead"><div class="npname"><h3 id="nptitle"></h3><span class="npsub"></span></div>' +
        '<span class="nstatus" hidden></span><span class="npprovider" title="The model behind this chat" hidden></span>' +
        '<button type="button" class="linkbtn npclose" data-npclose>Close (Esc)</button></div><p class="npnote" hidden></p>' +
        '<div class="nptabs" role="tablist" aria-label="Panel"><button type="button" role="tab" id="nptab-chat" data-nptab="chat" aria-selected="false">Chat</button>' +
        '<button type="button" role="tab" id="nptab-details" data-nptab="details" aria-selected="false">Details</button></div>' +
        '<div class="npbody" role="tabpanel"></div>';
      refs = {
        title: host.querySelector("#nptitle"), sub: host.querySelector(".npsub"), status: host.querySelector(".nstatus"), provider: host.querySelector(".npprovider"),
        close: host.querySelector(".npclose"), note: host.querySelector(".npnote"), body: host.querySelector(".npbody"),
        tabs: Array.from(host.querySelectorAll("[data-nptab]")),
      };
    }

    function paintTo(el, html) {
      const c = ctx();
      if (c && typeof c.paint === "function") return c.paint(el, html);
      if (el.__html === html) return false;
      el.innerHTML = html;
      el.__html = html;
      return true;
    }

    /* ------------------------------------------------ the head */
    function paintHead() {
      if (!st) return;
      const node = st.node || {};
      const detailNode = st.detail && isObj(st.detail.node) ? st.detail.node : node;
      const kind = clean(detailNode.kind || node.kind);
      const meta = isObj(detailNode.meta) ? detailNode.meta : {};
      const key = kind === "function" ? functionKey(detailNode) : "";
      refs.title.textContent = clean(detailNode.label || node.label) || clean(st.nodeId);
      refs.sub.textContent = key ? FV().PERSONA[key] : ({root: "root", department: "team", division: "division", step: "step"}[kind] || "");
      const status = clean(detailNode.status || node.status);
      if (status) {
        refs.status.hidden = false;
        refs.status.className = "nstatus st-" + (hasOwn({filed: 1, done_unchecked: 1, running: 1, left_open: 1, fault: 1, waiting: 1, waiting_on_you: 1, not_made: 1, idle: 1}, status) ? status : "idle");
        refs.status.textContent = FV().nodeWord(status, kind, meta.wait_on);
      } else {
        refs.status.hidden = true;
      }
      const shown = st.view ? st.view.session : st.session;
      const provider = shown ? CV().providerLabel(shown.connector) : "";
      refs.provider.hidden = provider === "";
      refs.provider.textContent = provider;
      const note = shown ? clean(shown.note) : "";
      refs.note.hidden = note === "";
      refs.note.textContent = note;
    }

    function paintTabs() {
      refs.tabs.forEach(b => b.setAttribute("aria-selected", String(st !== null && b.dataset.nptab === st.tab)));
    }

    /* ------------------------------------------------ the Chat tab */
    function buildChat() {
      refs.body.innerHTML = '<div class="nchat"><div class="nsearch" hidden><input type="search" class="nsbox" aria-label="Search chats" placeholder="Search chats\u2026" maxlength="200"/>' +
        '<div class="nsres" hidden></div></div><div class="nactions" hidden></div><div class="nlens" hidden></div><div class="nlinks" hidden></div><div class="nearlier" hidden></div>' +
        '<div class="nmsgs" role="log" aria-live="polite" aria-label="Messages"></div><div class="cjump" hidden></div><div class="ccstream" hidden></div><p class="nbanner" role="status" hidden></p>' +
        '<div class="npill" hidden></div><div class="ncomposer" hidden><div class="ccbar" hidden></div><div class="row"><textarea class="nbox" aria-label="Your message" rows="2"></textarea>' +
        '<button type="button" class="send" data-act="send">Send</button></div></div><p class="nnote" role="note" hidden></p></div>';
      refs.body.__html = undefined;
      const q = sel => refs.body.querySelector(sel);
      chatRefs = {lens: q(".nlens"), links: q(".nlinks"), earlier: q(".nearlier"), msgs: q(".nmsgs"), banner: q(".nbanner"), composer: q(".ncomposer"),
        box: q(".nbox"), send: q(".send"), note: q(".nnote"), pill: q(".npill"), bar: q(".ccbar"), stream: q(".ccstream"), search: q(".nsearch"), sbox: q(".nsbox"), sres: q(".nsres"), actions: q(".nactions"),
        jump: q(".cjump")};
      if (chatRefs.sbox) chatRefs.sbox.addEventListener("input", () => onSearchInput());
      if (CSc()) {
        CSc().watch(chatRefs.msgs, onScrollIntent);
        CSc().pin(chatRefs.msgs, () => !!st && !st.scroll.parked);       // the box or a row under it changes size: a follower stays at the newest line
      }
    }

    /* ------------------------------------------------ the draft and the box (GAP-chat-comfort) */
    // The box shows the draft of the chat on show; the first time it is synced, words typed before the draft store arrived are kept.
    const draftSid = () => (st && !st.view && !st.readOnly ? st.sid : "");
    function growBox() {
      if (chatRefs && chatRefs.box && root.ChatDraft) root.ChatDraft.grow(chatRefs.box, BOX_MAX_PX);
    }
    function syncDraft() {
      const d = draftStore();
      if (!chatRefs || !chatRefs.box || !d) return;
      const sid = draftSid();
      if (chatRefs.draftFor === sid) return;
      const first = chatRefs.draftFor === undefined;
      chatRefs.draftFor = sid;
      if (first && chatRefs.box.value !== "") d.save(sid, chatRefs.box.value);
      else chatRefs.box.value = sid ? d.load(sid) : "";
      growBox();
    }
    function saveDraft() {
      const d = draftStore();
      if (d && chatRefs && chatRefs.box && chatRefs.draftFor) d.save(chatRefs.draftFor, chatRefs.box.value);
    }

    /* ------------------------------------------------ the reader's place (GAP-chat-comfort) */
    function onScrollIntent(ev) {
      const CS = CSc();
      if (!CS || !st) return;
      const before = st.scroll.pill;
      st.scroll = CS.intent(st.scroll, Object.assign(ev, {lastId: lastIdOf(activeMessages())}));
      if (st.scroll.pill !== before) paintJump();
    }
    function paintJump() {
      const CS = CSc();
      if (!chatRefs || !chatRefs.jump) return;
      const html = CS && st ? CS.pillHtml(st.scroll.pill) : "";
      chatRefs.jump.hidden = html === "";
      paintTo(chatRefs.jump, html);
    }
    function jumpLatest() {
      const CS = CSc();
      const el = chatRefs ? chatRefs.msgs : null;
      if (!CS || !el) return;
      st.scroll = {parked: false, seenId: lastIdOf(activeMessages()), pill: 0};
      paintJump();
      const how = CS.behavior(typeof root.matchMedia === "function" ? q => root.matchMedia(q) : undefined);
      if (typeof el.scrollTo === "function") el.scrollTo({top: el.scrollHeight, behavior: how});
      else el.scrollTop = el.scrollHeight;
    }
    // A follower stays at the newest line when a row above or under the transcript changes size (ChatScroll.pin does it too, where the page renders).
    function keepFollowing() {
      if (CSc() && st && chatRefs && chatRefs.msgs && !st.scroll.parked && !st.loading) chatRefs.msgs.scrollTop = chatRefs.msgs.scrollHeight;
    }
    // Where the chat on show was read, kept when the panel closes or leaves the Chat tab (only once its messages were drawn).
    function rememberScroll() {
      const CS = CSc();
      if (!CS || !st || !chatRefs || !chatRefs.msgs || st.loading || st.chatNote || st.nodeGone) return;
      const el = chatRefs.msgs;
      CS.remember(scrollMem, activeSid(), {top: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight, seenId: st.scroll.seenId});
    }

    const activeSession = () => (st.view ? st.view.session : st.session);
    const activeMessages = () => (st.view ? st.view.messages : st.messages);
    const activeSid = () => (st.view ? st.view.sid : st.sid);

    function departmentOf(node) {
      if (!node) return null;
      const graph = getGraph();
      if (node.kind === "department") return node;
      return findNode(graph, node.dept_id);
    }

    function deptName() {
      const dept = departmentOf(st.node);
      return dept ? clean(dept.label) : "";
    }

    // The team's task is running or starting: the server would answer 409 to a line written now.
    const teamBusy = () => {
      const task = st.detail && isObj(st.detail.task) ? st.detail.task : null;
      return task !== null && (task.status === "running" || task.status === "starting");
    };
    const asking = () => activeMessages().some(m => m.kind === "question" && (m.answered_by === null || m.answered_by === undefined));

    function paintLens() {
      const node = st.node || {};
      const kind = clean(node.kind);
      const dept = departmentOf(node);
      const deptLabel = dept ? clean(dept.label) : "the team";
      const lens = chatRefs.lens;
      if (st.view) {
        lens.hidden = false;
        lens.className = "nlens nlens-archived";
        lens.innerHTML = '<p class="nlenstext">An earlier chat, kept for reading.</p><button type="button" class="linkbtn" data-act="back">Back to this chat</button>';
      } else if (kind === "division" && st.scope === "division") {
        lens.hidden = false;
        lens.className = "nlens";
        lens.innerHTML = '<p class="nlenstext">' + esc(clean(node.label)) + " is part of " + esc(deptLabel) + ". This is " + esc(deptLabel) + "'s Identity, showing the work for " +
          esc(clean(node.label)) + '.</p><button type="button" class="linkbtn" data-act="show-dept">Show everything for ' + esc(deptLabel) + "</button>";
      } else if (kind === "division") {
        lens.hidden = false;
        lens.className = "nlens nlens-all";
        lens.innerHTML = '<p class="nlenstext">Everything for ' + esc(deptLabel) + '.</p><button type="button" class="linkbtn" data-act="show-division">Show only the work for ' +
          esc(clean(node.label)) + "</button>";
      } else if (kind === "function" && functionKey(node) === "identity") {
        lens.hidden = false;
        lens.className = "nlens nlens-identity";
        lens.innerHTML = '<p class="nlenstext">This is ' + esc(deptLabel) + "'s chat. Identity is the voice of the team.</p>";
      } else {
        lens.hidden = true;
        lens.innerHTML = "";
      }
      // the richer J2 view of the same conversation
      const links = chatRefs.links;
      const teamId = dept ? clean(dept.id) : "";
      const session = activeSession();
      const own = session && (session.kind === "department" || session.kind === "division") && !st.view;
      links.hidden = !(own && teamId !== "");
      links.innerHTML = links.hidden ? "" : '<button type="button" class="linkbtn" data-act="open-team" data-href="/d/' + enc(teamId) + '/?view=simple">Open the team page</button>';
      // earlier chats of this node (a merge files the old chats under the survivor)
      const earlier = st.detail && Array.isArray(st.detail.archived_chats) ? st.detail.archived_chats.filter(isObj) : [];
      chatRefs.earlier.hidden = earlier.length === 0 || st.view !== null;
      paintTo(chatRefs.earlier, earlier.length === 0 ? "" : '<details class="nearlierbox" data-key="earlier"><summary>Earlier chats (' + earlier.length + ")</summary><ul>" +
        earlier.map(s => '<li><button type="button" class="linkbtn" data-act="earlier" data-sid="' + esc(clean(s.id)) + '">' + esc(clean(s.title) || clean(s.id)) +
          (clean(s.note) ? " \u00b7 " + esc(clean(s.note)) : "") + "</button></li>").join("") + "</ul></details>");
    }

    // The reader's place (ChatScroll): the owner's own send (st.stick) goes to the bottom; a chat opened again (st.reopen) comes back where it was
    // read, else to the bottom; a reader who moved up stays and the pill counts what arrived below; a follower follows.
    function paintMessages() {
      const session = activeSession();
      const el = chatRefs.msgs;
      const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_PX;
      const list = activeMessages();
      const html = CV().transcript(session, list, {deptName: deptName(), live: !st.view});
      const changed = paintTo(el, html);
      const last = list.reduce((n, m) => Math.max(n, Number(m.id) || 0), 0);
      const CS = CSc();
      if (!CS) {
        if (changed && (st.stick || st.reopen || near)) el.scrollTop = el.scrollHeight;
      } else {
        const back = st.reopen && !st.stick ? CS.restore(scrollMem, activeSid(), {scrollHeight: el.scrollHeight, clientHeight: el.clientHeight}) : null;
        let p;
        if (back) {
          el.scrollTop = back.top;
          st.scroll = {parked: true, seenId: back.seenId, pill: 0};
          p = {scroll: "keep", pill: CS.newCount(list, back.seenId)};
        } else {
          p = CS.plan({parked: st.scroll.parked, atBottom: near, grew: changed, own: st.stick || st.reopen, newCount: CS.newCount(list, st.scroll.seenId), pill: st.scroll.pill});
          if (p.scroll === "bottom") el.scrollTop = el.scrollHeight;
        }
        st.scroll = CS.settle(st.scroll, p, CS.distance(el), last);
        paintJump();
      }
      st.stick = false;
      st.reopen = false;
      markSeen(activeSid(), last);
    }

    function paintComposer() {
      const session = activeSession();
      const direct = directOn();
      const turn = {busy: !st.view && !direct && teamBusy(), asking: asking(), blocked: st.blocked || (direct ? askBlocked() : "")};
      const state = st.readOnly ? {hidden: true, disabled: true, placeholder: "", note: "This chat is read-only."} : CV().composerState(session, turn);
      chatRefs.composer.hidden = state.hidden;
      syncDraft();
      chatRefs.box.disabled = state.disabled || st.sending;
      chatRefs.send.disabled = state.disabled || st.sending;
      const c = st.cc ? st.cc.c : null;
      if (c && direct) {
        const b = root.ChatComposer.button(c.state(), chatRefs.box.value, {disabled: state.disabled || st.sending, blocked: askBlocked() !== ""});
        chatRefs.send.textContent = b.label; chatRefs.send.dataset.act = b.act; chatRefs.send.disabled = b.disabled || state.disabled || st.sending;
      } else {
        chatRefs.send.textContent = "Send"; chatRefs.send.dataset.act = "send";
      }
      chatRefs.box.placeholder = state.placeholder;
      chatRefs.note.hidden = state.note === "";
      chatRefs.note.textContent = state.note;
      const problem = st.banner || "";
      chatRefs.banner.hidden = problem === "";
      chatRefs.banner.innerHTML = problem === "" ? "" : esc(problem) + (st.gone ? ' <button type="button" class="linkbtn" data-npclose>Close</button>' : "") +
        (st.retry ? ' <button type="button" class="linkbtn" data-act="retry-load">Try again</button>' : "");
      keepFollowing();
    }

    // The composer of the direct chat (ABS-15): one controller per open team chat; "Tell the team" is the plain message route as it was, "Ask the model" is
    // POST /direct with attachments and a Stop. The streaming row lives under the messages; the stored reply (with its blocks) replaces it.
    function composerOf() {
      const CC = root.ChatComposer;
      const sid = pillOwner();
      if (!CC || !sid) return null;
      if (!st.cc || st.cc.sid !== sid) {
        let c = composers.get(sid);              // the same chat opened again: its mode, its files and a running turn (with Stop) are still there
        const again = c !== undefined;
        if (!again) {
          c = CC.create({api: api(), sid, mode: st.ccMode || "team", onChange: () => { if (st && chatRefs) { paintComposer(); paintBar(); } }});
          composers.set(sid, c);
        }
        st.cc = {sid, c};                        // set first: rejoin and reconcile repaint, and the repaint asks for this composer again
        if (again) {
          c.rejoin();
          c.reconcile(st.messages);              // a turn whose reply was stored while the chat was closed is over (no event of it reaches this page now)
        }
      }
      return st.cc.c;
    }
    const directOn = () => { const c = st && st.tab === "chat" ? composerOf() : null; return c !== null && c.state().mode === "direct"; };
    const pillData = () => st.pill || {providers: [], chosen: null};
    const askBlocked = () => (directOn() && st.pill ? root.ChatComposer.askBlock(pillData().providers) : "");

    function paintBar() {
      const CC = root.ChatComposer;
      if (!chatRefs || !chatRefs.bar) return;
      const c = composerOf();
      const hidden = !c || chatRefs.composer.hidden;
      if (hidden) {
        chatRefs.bar.hidden = true; chatRefs.bar.innerHTML = ""; chatRefs.bar.__html = undefined;
        chatRefs.stream.hidden = true; chatRefs.stream.innerHTML = ""; chatRefs.stream.__html = undefined;
        keepFollowing();
        return;
      }
      const data = pillData();
      const html = CC.bar(c.state(), {labels: {team: "Tell the team", direct: "Ask the model"}});
      chatRefs.bar.hidden = html === "";
      paintTo(chatRefs.bar, html);
      const row = CC.streamRow(c.state(), CC.providerOf(data.providers, data.chosen));
      chatRefs.stream.hidden = row === "";
      paintTo(chatRefs.stream, row);
      keepFollowing();
    }

    // After a refetch: the turn is over when the stored reply is in the list.
    function reconcileTurn() {
      const c = st && st.cc ? st.cc.c : null;
      if (c && c.reconcile(st.messages) && !st.scroll.parked) st.stick = true;          // a reader who moved up during the answer stays where they read
    }

    // The provider pill (ABS-9): only on a team chat the owner can write in; the data comes from GET /api/chats/{sid}/providers.
    const pillOwner = () => (st && !st.view && !st.readOnly && st.session && (st.session.kind === "department" || st.session.kind === "division")) ? st.sid : "";
    function paintPill() {
      const CP = root.ChatPill;
      if (!chatRefs || !chatRefs.pill) return;
      const sid = pillOwner();
      if (!CP || !sid) { chatRefs.pill.hidden = true; chatRefs.pill.innerHTML = ""; return; }
      if (st.pillSid !== sid) {
        st.pillSid = sid;
        settle(api().get("/api/chats/" + enc(sid) + "/providers")).then(r => {
          if (!st || st.pillSid !== sid || r.error || !r.value) return;
          st.pill = r.value;
          paintPill();
        });
      }
      const data = st.pill || {providers: [], chosen: null};
      const html = CP.pill(data.providers, data.chosen);
      chatRefs.pill.hidden = html === "";
      chatRefs.pill.innerHTML = html;
      keepFollowing();
    }

    // Search, archive and the attachment limits (ABS-10): ChatSearch builds the strings; the server decides what a scope may see.
    let searchTimer = 0;
    function onSearchInput() {
      const CS = root.ChatSearch;
      if (!CS || !st || !chatRefs) return;
      root.clearTimeout(searchTimer);
      searchTimer = root.setTimeout(async () => {
        const session = activeSession();
        const req = CS.request(chatRefs.sbox.value, CS.scopeOf(session, (departmentOf(st.node) || {}).id), true);
        if (!req) { chatRefs.sres.hidden = true; chatRefs.sres.innerHTML = ""; return; }
        const r = await settle(api().get(req.path, req.query));
        if (!st || !chatRefs) return;
        chatRefs.sres.hidden = false;
        chatRefs.sres.innerHTML = r.error ? '<p class="empty csearch-empty">Search is not available right now.</p>' : CS.results(r.value && r.value.results);
      }, 250);
    }

    function paintActions() {
      const CS = root.ChatSearch;
      if (!chatRefs || !chatRefs.actions || !chatRefs.search) return;
      const session = activeSession();
      const on = !!CS && !!session;
      chatRefs.search.hidden = !on;
      const html = on ? CS.archiveButton(session) : "";
      chatRefs.actions.hidden = html === "";
      chatRefs.actions.innerHTML = html;
    }

    function archiveChat(sid, archive) {
      settle(api().post("/api/chats/" + enc(sid) + (archive ? "/archive" : "/unarchive"))).then(r => {
        if (!st) return;
        if (r.error) { st.banner = clean(r.error.message) || "That did not work."; paintChat(); return; }
        const node = st.nodeId, tab = st.tab;
        // the team's chat may now be another session (archiving starts a fresh one, bringing it back re-links the old one): read the graph again
        settle(api().get("/api/graph")).then(g => open(node, tab, g.error ? undefined : g.value));
      });
    }

    function chooseProvider(name) {
      const CP = root.ChatPill;
      const sid = pillOwner();
      if (!CP || !sid) return;
      const req = CP.choiceRequest(sid, name);
      settle(api().put(req.path, req.body)).then(r => {
        if (!st || st.sid !== sid) return;
        if (r.error) { st.banner = clean(r.error.message) || "That model cannot answer right now."; paintChat(); return; }
        st.pillSid = ""; st.pill = null; st.banner = "";
        paintChat();
      });
    }

    function paintChat() {
      if (!st || st.tab !== "chat" || !chatRefs) return;
      const gap = st.loading ? "Loading\u2026" : (st.nodeGone || st.chatNote);
      if (gap) {
        chatRefs.msgs.innerHTML = '<p class="empty nempty">' + esc(gap) + "</p>";
        chatRefs.msgs.__html = undefined;
      } else {
        paintMessages();
      }
      paintLens();
      paintActions();
      paintPill();
      paintComposer();
      paintBar();
    }

    /* ------------------------------------------------ the Details tab */
    function detailRaw() {
      if (!st.detail) return null;
      return st.allAtoms ? Object.assign({}, st.detail, {atoms: st.allAtoms}) : st.detail;
    }

    function paintDetails() {
      if (!st || st.tab !== "details") return;
      let el = refs.body.querySelector(".fndetail");
      if (!el) {
        refs.body.innerHTML = '<div class="fndetail"></div>';
        refs.body.__html = undefined;
        el = refs.body.firstChild;
      }
      const raw = detailRaw();
      let html;
      if (st.loading) html = '<p class="empty nempty">Loading\u2026</p>';
      else if (st.nodeGone) html = '<p class="empty nempty">' + esc(st.nodeGone) + "</p>";
      else if (!raw) html = '<p class="empty nempty">' + esc(st.detailError || "No details yet.") + "</p>";
      else {
        const graph = getGraph();
        if (!st.shownOnce) {         // the first time a node's atoms are drawn, the open one is unfolded; after that the owner's folding stands
          st.shownOnce = true;
          st.openIds = (Array.isArray(raw.atoms) ? raw.atoms : []).filter(a => isObj(a) && a.state === "open").map(a => text(a.id)).slice(0, 1);
        }
        html = FV().nodeHtml(raw, {nodes: isObj(graph) && Array.isArray(graph.nodes) ? graph.nodes : [], withAgent: withAgent(), openIds: st.openIds});
        st.openIds = [];
      }
      paintTo(el, html);
      const slot = el.querySelector("[data-fnagent]");
      if (slot && st.agentHtml && slot.__agent !== st.agentHtml) {
        slot.innerHTML = st.agentHtml;
        slot.__agent = st.agentHtml;
      }
    }

    function paintBody() {
      if (!st) return;
      if (st.tab === "chat") {
        if (!chatRefs || !refs.body.contains(chatRefs.msgs)) buildChat();
        paintChat();
      } else {
        chatRefs = null;
        paintDetails();
      }
    }

    function paintAll() {
      if (!st) return;
      paintHead();
      paintTabs();
      paintBody();
    }

    /* ------------------------------------------------ getting the data */
    const msgPath = sid => "/api/chats/" + enc(sid) + "/messages";

    async function fetchMessages(sid, after) {
      const out = [];
      let cursor = after;
      for (let page = 0; page < MAX_PAGES; page += 1) {
        const r = await api().get(msgPath(sid), {after: cursor, limit: PAGE});
        if (!isObj(r) || !Array.isArray(r.messages)) throw new (ctx().ApiError)("bad_payload");
        const list = r.messages.filter(isObj);
        out.push(...list);
        const last = list.reduce((n, m) => Math.max(n, Number(m.id) || 0), cursor);
        if (list.length < PAGE || last <= cursor) break;
        cursor = last;
      }
      return out;
    }

    // Add the fresh messages (by id), keep the list in id order, and close the open questions an owner line has answered: the server answers a
    // question with the owner's next line, and the questions already on screen are not fetched again.
    function mergeMessages(into, fresh) {
      const byId = new Map(into.map(m => [m.id, m]));
      fresh.forEach(m => byId.set(m.id, m));
      const all = Array.from(byId.values()).sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0));
      let owner = null;
      for (let i = all.length - 1; i >= 0; i -= 1) {
        if (all[i].role === "user" || all[i].who === "user") owner = all[i].id;
        else if (all[i].kind === "question" && (all[i].answered_by === null || all[i].answered_by === undefined) && owner !== null) all[i] = Object.assign({}, all[i], {answered_by: owner});
      }
      return all;
    }

    const lastIdOf = list => list.reduce((n, m) => Math.max(n, Number(m.id) || 0), 0);

    async function loadSession(g, sid) {
      const [session, messages] = await Promise.all([settle(api().get("/api/chats/" + enc(sid))), settle(fetchMessages(sid, 0))]);
      if (g !== gen || !st) return;
      if (session.error || messages.error) {
        const err = session.error || messages.error;
        if (err.status === 404) st.chatNote = GONE;
        else st.banner = problemOf(err).text;
        st.retry = err.status !== 404;
        return;
      }
      st.chatNote = "";
      st.session = isObj(session.value) ? session.value : null;
      st.messages = mergeMessages([], messages.value);
      st.lastId = lastIdOf(st.messages);
      st.reopen = true;                          // back where this chat was read, else at its newest line
      st.scroll = {parked: false, seenId: 0, pill: 0};
    }

    async function resolveSid(node, graph) {
      const direct = chatSessionFor(node, graph);
      if (direct) return direct;
      if (node.kind === "function" && functionKey(node) === "identity" && clean(node.dept_id) !== "") {
        const found = await settle(api().get("/api/departments/" + enc(node.dept_id)));
        if (found.value && clean(found.value.session_id) !== "") return found.value.session_id;
      }
      return clean(node.chat_session_id) !== "" ? node.chat_session_id : null;        // an Identity's own working log, read-only, is better than no chat
    }

    async function loadDetail(g) {
      const found = await settle(api().get("/api/graph/nodes/" + enc(st.nodeId)));
      if (g !== gen || !st) return null;
      if (found.error) {
        if (found.error.status === 404) st.nodeGone = "This node is gone.";
        else st.detailError = problemOf(found.error).text;
        return null;
      }
      if (!isObj(found.value) || !isObj(found.value.node)) {
        st.detailError = "The app sent an answer that could not be read.";
        return null;
      }
      st.detail = found.value;
      st.detailError = "";
      if (!st.node) st.node = found.value.node;
      return found.value;
    }

    async function loadAgent(g) {
      if (!st || !withAgent() || typeof renderAgent !== "function") return;
      const node = st.detail && st.detail.node;
      const fn = node ? functionKey(node) : "";
      if (fn === "") return;
      const found = await settle(api().get("/api/agent", {who: fn, dept: deptPage()}));
      if (g !== gen || !st || !found.value) return;
      try {
        st.agentHtml = renderAgent(found.value);
      } catch (e) {
        st.agentHtml = "";
      }
      paintDetails();
    }

    async function open(nodeId, tab, freshGraph) {
      const id = clean(nodeId);
      if (id === "") return;
      ensureShell();
      const g = ++gen;
      const opener = st ? st.opener : { el: doc.activeElement, id: "" };
      if (st) stopLive();
      const graph = isObj(freshGraph) ? freshGraph : getGraph();      // archive and un-archive re-link the team's chat: the caller passes the graph it just fetched
      st = {nodeId: id, tab: tab === "details" ? "details" : "chat", node: findNode(graph, id), detail: null, detailError: "", sid: "", session: null, messages: [],
        lastId: 0, banner: "", blocked: "", cc: null, ccMode: "team", readOnly: false, gone: false, retry: false, sending: false, view: null, scope: "division", divisionChat: null, allAtoms: null,
        openIds: [], shownOnce: false, agentHtml: "", loading: true, nodeGone: "", chatNote: "", stick: false, reopen: true, scroll: {parked: false, seenId: 0, pill: 0},
        opener: opener, conn: null, refresh: null};
      if (!opener.id) opener.id = id;
      doc.body.classList.add("nodeopen");
      closeAgentDrawer();
      host.hidden = false;
      chatRefs = null;
      refs.body.innerHTML = "";
      refs.body.__html = undefined;
      paintAll();
      if (refs.close && typeof refs.close.focus === "function") refs.close.focus();

      const detailP = loadDetail(g);
      let sidP;
      if (st.node) sidP = resolveSid(st.node, graph);
      else sidP = detailP.then(detail => (detail ? resolveSid(detail.node, graph) : null));
      const sid = await sidP;
      if (g !== gen || !st) return;
      if (sid) {
        st.sid = sid;
        await loadSession(g, sid);
        if (g !== gen || !st) return;
      }
      await detailP;
      if (g !== gen || !st) return;
      st.loading = false;
      if (!sid) st.chatNote = "This node has no chat.";
      paintAll();
      live(g);
      if (st.tab === "details") loadAgent(g);
    }

    async function openFunction(fn, tab) {
      const key = clean(fn);
      if (!FUNCTIONS.includes(key)) return;
      const dept = deptPage();
      const graph = getGraph();
      const nodes = isObj(graph) && Array.isArray(graph.nodes) ? graph.nodes : [];
      const node = nodes.find(n => isObj(n) && n.kind === "function" && functionKey(n) === key && (dept === "" || n.dept_id === dept));
      if (node) return open(node.id, tab || "details");
      if (dept === "") return undefined;
      // the graph on hand holds no function nodes (the Overview level): the team's own record names them
      const found = await settle(api().get("/api/departments/" + enc(dept)));
      const listed = found.value && Array.isArray(found.value.functions) ? found.value.functions.find(f => isObj(f) && f.fn === key) : null;
      return listed && clean(listed.id) !== "" ? open(listed.id, tab || "details") : undefined;
    }

    /* ------------------------------------------------ staying current */
    async function refreshMessages(g) {
      if (!st || g !== gen || !st.sid || st.view) return;
      const sid = st.sid;
      const found = await settle(fetchMessages(sid, st.lastId));
      if (!st || g !== gen || sid !== st.sid) return;
      if (found.error) return;
      if (found.value.length) {
        st.messages = mergeMessages(st.messages, found.value);
        st.lastId = lastIdOf(st.messages);
      }
      reconcileTurn();
      if (st.tab === "chat" && chatRefs) paintChat();
    }

    async function refreshDetail(g) {
      if (!st || g !== gen) return;
      const before = st.detail;
      await loadDetail(g);
      if (!st || g !== gen || st.detail === before) return;
      paintHead();
      if (st.tab === "details") paintDetails();
      else if (chatRefs) paintComposer();
    }

    function live(g) {
      const SE = root.SutraEvents;
      if (!SE || typeof SE.connect !== "function" || !st) return;
      const refetchMessages = SE.coalesce(() => refreshMessages(g), COALESCE_MS);
      const refetchDetail = SE.coalesce(() => refreshDetail(g), COALESCE_MS);
      const mine = data => isObj(data) && data.session_id === (st && st.sid);
      st.refresh = [refetchMessages, refetchDetail];
      st.conn = SE.connect({
        topics: TOPICS,
        onEvent(type, data) {
          if (!st || g !== gen) return;
          if (type === "chat.partial") {
            const c = mine(data) ? composerOf() : null;
            if (c) c.partial(data);
          } else if (type === "chat.message") {
            if (mine(data)) refetchMessages();
          } else if (type === "atom.updated") {
            const atom = isObj(data) && isObj(data.atom) ? data.atom : data;
            if (!isObj(atom) || atom.node_id === st.nodeId) refetchDetail();
          } else if (type === "graph.updated") {
            const team = st.node ? st.node.dept_id : "";
            if (!isObj(data) || !Array.isArray(data.nodes) || data.nodes.some(n => isObj(n) && (n.id === st.nodeId || n.id === team))) refetchDetail();
          } else if (type === "task.updated" || type === "needs_you.changed") {
            refetchDetail();
          } else if (type === "server.resync") {
            refetchMessages();
            refetchDetail();
          }
        },
        pollFn: () => Promise.all([refreshMessages(g), refreshDetail(g)]),
        pollMs: opts.pollMs,
      });
    }

    function stopLive() {
      if (!st) return;
      if (st.conn && typeof st.conn.close === "function") st.conn.close();
      (st.refresh || []).forEach(f => { if (typeof f.cancel === "function") f.cancel(); });
      st.conn = null;
      st.refresh = null;
    }

    /* ------------------------------------------------ one drawer at a time */
    function closeAgentDrawer() {
      if (typeof closeAgent === "function") {
        closeAgent();
        return;
      }
      const drawer = doc.getElementById("agentdrawer");
      if (drawer) drawer.hidden = true;
      doc.body.classList.remove("agentopen");
    }

    function close() {
      if (!st) return false;
      const opener = st.opener;
      rememberScroll();                          // the place it was read and the words in the box come back when it opens again
      saveDraft();
      stopLive();
      st = null;
      gen += 1;
      chatRefs = null;
      host.hidden = true;
      doc.body.classList.remove("nodeopen");
      if (refs) {
        refs.body.innerHTML = "";
        refs.body.__html = undefined;
      }
      // focus goes back to the node that opened the panel (found again by its id when the picture has been redrawn)
      let target = opener && opener.el && opener.el.isConnected ? opener.el : null;
      if (!target && opener && opener.id) {
        target = Array.from(doc.querySelectorAll("[data-id]")).find(e => e.getAttribute("data-id") === opener.id) || null;
      }
      if (target && typeof target.focus === "function") target.focus();
      return true;
    }

    /* ------------------------------------------------ what the owner does */
    function goToTab(tab) {
      close();
      if (typeof showTab === "function") {
        showTab(tab);
        return;
      }
      const button = doc.querySelector('.tabs [data-tab="' + tab + '"]');
      if (button) button.click();
    }

    function openFrom(el) {
      const node = el.dataset.node;
      if (node) return open(node, "details");
      const fn = el.dataset.fn;
      if (!fn) return undefined;
      const dept = el.dataset.dept || (st && st.node ? clean(st.node.dept_id) : "") || deptPage();
      const graph = getGraph();
      const nodes = isObj(graph) && Array.isArray(graph.nodes) ? graph.nodes : [];
      const found = nodes.find(n => isObj(n) && n.kind === "function" && functionKey(n) === fn && n.dept_id === dept);
      if (found) return open(found.id, "details");
      return settle(api().get("/api/departments/" + enc(dept))).then(r => {
        const listed = r.value && Array.isArray(r.value.functions) ? r.value.functions.find(f => isObj(f) && f.fn === fn) : null;
        return listed && clean(listed.id) !== "" ? open(listed.id, "details") : undefined;
      });
    }

    async function sendDirect(value, fromBox) {
      const c = composerOf();
      const body = text(value).trim();
      if (!c || body === "") return false;
      const g = gen;
      const sid = st.sid;
      const stuck = askBlocked();
      if (stuck !== "") { st.banner = stuck; paintChat(); return false; }
      st.banner = "";
      const out = await c.send(body);
      if (out.ok && draftStore()) draftStore().clearIf(sid, body);          // only a send the server accepted clears the draft
      if (g !== gen || !st) return out.ok;
      if (out.ok) {
        if (fromBox && chatRefs && chatRefs.box.value.trim() === body) { chatRefs.box.value = ""; growBox(); }
        st.stick = true;
        await refreshMessages(g);                 // the owner's line (stored before the 202) and, if it was quick, the reply too
      }
      if (st && g === gen && chatRefs) paintChat();
      return out.ok;
    }

    async function stopDirect() {
      const c = st && st.cc ? st.cc.c : null;
      if (!c) return;
      const g = gen;
      await c.stop();
      await refreshMessages(g);
    }

    // Retry on a direct line that failed: the owner's same words, once, to the model (the error line names the line: data-turn).
    async function retryDirect(turnId) {
      const c = composerOf();
      const line = activeMessages().find(m => String(m.id) === String(turnId) && (m.role === "user" || m.who === "user"));
      if (!c || !line) return;
      const stuck = st.pill ? root.ChatComposer.askBlock(pillData().providers) : "";
      if (stuck !== "") { st.banner = stuck; paintChat(); return; }
      const g = gen;
      const said = CV().attachedOf(line.text);
      st.banner = "";
      const out = await c.retry(line.id, said.text, {files: said.names.length});
      if (g !== gen || !st) return;
      if (out.ok) { st.stick = true; await refreshMessages(g); }
      if (st && g === gen && chatRefs) paintChat();
    }

    async function send(value, fromBox, team) {
      if (!st || st.sending || st.view) return false;
      if (directOn() && team !== true) return sendDirect(value, fromBox);
      const body = text(value).trim();
      if (body === "") return false;
      const g = gen;
      const sid = st.sid;
      st.sending = true;
      st.banner = "";
      paintComposer();
      let ok = false;
      try {
        await api().post(msgPath(sid), {text: body});
        ok = true;
        if (draftStore()) draftStore().clearIf(sid, body);                 // only a send the server accepted clears the draft
      } catch (e) {
        if (g === gen && st) {
          const problem = problemOf(e);
          st.banner = problem.text;
          if (problem.block) st.blocked = problem.block;
          if (problem.readOnly) st.readOnly = true;
          if (problem.gone) st.gone = true;
        }
      }
      if (g !== gen || !st) return ok;
      st.sending = false;
      if (ok) {
        if (fromBox && chatRefs && chatRefs.box.value.trim() === body) { chatRefs.box.value = ""; growBox(); }
        st.stick = true;
        await Promise.all([refreshMessages(g), refreshDetail(g)]);
      }
      if (st && g === gen && chatRefs) paintComposer();
      return ok;
    }

    async function showArchived(sid) {
      if (!st) return;
      const g = gen;
      const [session, messages] = await Promise.all([settle(api().get("/api/chats/" + enc(sid))), settle(fetchMessages(sid, 0))]);
      if (g !== gen || !st) return;
      if (session.error || messages.error) {
        st.banner = problemOf(session.error || messages.error).text;
      } else {
        // whatever the server calls it, a chat filed under another node is an archived one: read-only, with the note it was filed with
        const entry = (st.detail && Array.isArray(st.detail.archived_chats) ? st.detail.archived_chats : []).find(c => isObj(c) && c.id === sid) || {};
        const kept = Object.assign({}, entry, session.value, {status: "archived", writable: false});
        kept.note = clean(session.value && session.value.note) || clean(entry.note);
        st.view = {sid, session: kept, messages: mergeMessages([], messages.value)};
        st.stick = true;
        st.banner = "";
      }
      paintAll();
    }

    // the division lens shows its team's whole chat: the team's session is the department node's
    async function showWholeTeam() {
      if (!st) return;
      const g = gen;
      const dept = departmentOf(st.node);
      const sid = dept ? clean(dept.chat_session_id) : "";
      if (sid === "") return;
      st.scope = "all";
      const prev = {sid: st.sid, session: st.session, messages: st.messages, lastId: st.lastId};
      st.divisionChat = prev;
      st.sid = sid;
      st.loading = true;
      paintChat();
      await loadSession(g, sid);
      if (g !== gen || !st) return;
      st.loading = false;
      paintAll();
    }

    async function showDivision() {
      if (!st || !st.divisionChat) return;
      const prev = st.divisionChat;
      st.scope = "division";
      Object.assign(st, {sid: prev.sid, session: prev.session, messages: prev.messages, lastId: prev.lastId, stick: true});
      st.divisionChat = null;
      paintAll();
      await refreshMessages(gen);
    }

    // "Show all": the first press replaces the short list with the first 100 atoms, each further press adds the next 100
    async function showAll() {
      if (!st || !st.detail) return;
      const g = gen;
      const have = st.allAtoms ? st.allAtoms.length : 0;
      const found = await settle(api().get("/api/atoms", {node_id: st.nodeId, limit: ATOM_PAGE, offset: have}));
      if (g !== gen || !st || !Array.isArray(found.value)) return;
      st.allAtoms = (st.allAtoms || []).concat(found.value);
      paintDetails();
    }

    function onClick(e) {
      const target = e.target && e.target.closest ? e.target : null;
      if (!target) return;
      const closeBtn = target.closest("[data-npclose]");
      if (closeBtn) { close(); return; }
      const tabBtn = target.closest("[data-nptab]");
      if (tabBtn) { switchTab(tabBtn.dataset.nptab); return; }
      const act = target.closest("[data-act]");
      if (!act || !st) return;
      const name = act.dataset.act;
      if (name === "chat") switchTab("chat");
      else if (name === "send") send(chatRefs ? chatRefs.box.value : "", true);
      else if (name === "composer-stop") stopDirect();
      else if (name === "composer-mode") { const c = composerOf(); if (c) { st.ccMode = act.dataset.mode === "direct" ? "direct" : "team"; c.setMode(st.ccMode); } }
      else if (name === "composer-attach") { const input = chatRefs && chatRefs.bar ? chatRefs.bar.querySelector(".ccinput") : null; if (input) input.click(); }
      else if (name === "composer-remove") { const c = composerOf(); if (c) c.removeFile(act.dataset.key); }
      else if (name === "fn") openFrom(act);
      else if (name === "go-tab") goToTab(act.dataset.tab);
      else if (name === "show-all") showAll();
      else if (name === "choose-provider") chooseProvider(act.dataset.provider || null);
      else if (name === "archive" || name === "unarchive") archiveChat(act.dataset.sid, name === "archive");
      else if (name === "open-chat") { chatRefs.sres.hidden = true; if (act.dataset.sid !== st.sid) showArchived(act.dataset.sid); }
      else if (name === "open-team") {
        e.preventDefault();
        const dept = departmentOf(st.node);
        const href = act.dataset.href || act.getAttribute("href") || (dept ? "/d/" + enc(clean(dept.id)) + "/?view=detail" : "");
        if (href) navigate(href);
      } else if (name === "option") pickOption(act);
      else if (name === "show-dept") showWholeTeam();
      else if (name === "show-division") showDivision();
      else if (name === "earlier") showArchived(act.dataset.sid);
      else if (name === "back") { st.view = null; st.stick = true; paintAll(); }
      else if (name === "retry-load") { const node = st.nodeId; const tab = st.tab; open(node, tab); }
      else if (name === "jump-latest") jumpLatest();
      else if (name === "retry-direct") retryDirect(act.dataset.turn);
    }

    // J2's convention: an option button answers "Option N"; a question that is one of several adds "<q>. Option N" to the box instead.
    function pickOption(button) {
      const group = button.closest(".opts");
      if (!group || !chatRefs) return;
      const n = button.dataset.opt;
      if (group.dataset.n === "1") { send("Option " + n, false, true); return; }
      const box = chatRefs.box;
      box.value += (box.value ? "; " : "") + group.dataset.q + ". Option " + n;
      saveDraft();
      growBox();
      box.focus();
    }

    function switchTab(tab) {
      if (!st || (tab !== "chat" && tab !== "details") || st.tab === tab) return;
      if (st.tab === "chat") { rememberScroll(); saveDraft(); }
      st.tab = tab;
      st.reopen = true;
      chatRefs = null;
      refs.body.innerHTML = "";
      refs.body.__html = undefined;
      paintAll();
      if (tab === "details" && !st.agentHtml) loadAgent(gen);
    }

    // Esc: first it stops a direct answer that is running, else it closes the panel (the draft is already saved, so nothing is lost).
    function onKeyDown(e) {
      if (!st) return;
      if (e.key === "Escape" && !e.defaultPrevented && !e.isComposing) {
        const turn = st.cc && st.cc.sid === pillOwner() ? st.cc.c.state().turn : null;
        if (st.tab === "chat" && turn && turn.active && !turn.stopping) { stopDirect(); return; }
        close();
        return;
      }
      const t = e.target;
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing && t && t.classList && t.classList.contains("nbox")) {
        e.preventDefault();
        send(t.value, true);
      }
    }

    host.addEventListener("click", onClick);
    host.addEventListener("change", e => {
      const t = e.target;
      const c = st && t && t.classList && t.classList.contains("ccinput") ? composerOf() : null;
      if (!c) return;
      c.addFiles(t.files);
      t.value = "";
    });
    // The box: what is typed is the chat's draft and sizes the box; a pasted or dropped file attaches (a text paste or drop stays text).
    const inBox = e => !!(st && chatRefs && chatRefs.box && e.target === chatRefs.box);
    const inComposer = e => !!(st && chatRefs && chatRefs.composer && e.target && typeof chatRefs.composer.contains === "function" && chatRefs.composer.contains(e.target));
    host.addEventListener("input", e => { if (inBox(e)) { saveDraft(); growBox(); } });
    host.addEventListener("paste", e => {
      const c = inBox(e) && !chatRefs.box.disabled ? composerOf() : null;
      if (c && c.take(e.clipboardData, {pasted: true})) e.preventDefault();
    });
    host.addEventListener("dragover", e => {
      if (inComposer(e) && composerOf() && root.ChatComposer.hasFiles(e.dataTransfer)) e.preventDefault();
    });
    host.addEventListener("drop", e => {
      const c = inComposer(e) && !chatRefs.box.disabled ? composerOf() : null;
      if (c && c.take(e.dataTransfer)) e.preventDefault();
    });
    host.addEventListener("keydown", e => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const t = e.target;
      if (t && t.dataset && t.dataset.nptab) switchTab(t.dataset.nptab === "chat" ? "details" : "chat");
    });
    doc.addEventListener("keydown", onKeyDown);
    // J2's Agent drawer and this panel never show together: when the Agent drawer opens, the panel closes
    let observer = null;
    if (typeof root.MutationObserver === "function" && doc.body) {
      observer = new root.MutationObserver(() => { if (st && doc.body.classList.contains("agentopen")) close(); });
      observer.observe(doc.body, {attributes: true, attributeFilter: ["class"]});
    }

    function destroy() {
      close();
      host.removeEventListener("click", onClick);
      doc.removeEventListener("keydown", onKeyDown);
      if (observer) observer.disconnect();
      if (current === handle) current = null;
    }

    const handle = {
      open: (nodeId, tab) => open(nodeId, tab || "chat"),
      openFunction: (fn, tab) => openFunction(fn, tab),
      wants: id => wants(id),
      chatSessionFor: (node, graph) => chatSessionFor(node, graph || getGraph()),
      close: () => close(),
      isOpen: () => st !== null && host.hidden === false,
      destroy,
    };
    current = handle;
    return handle;
  }

  const NodePanel = {
    mount, chatSessionFor, wants,
    open: (nodeId, tab) => (current ? current.open(nodeId, tab) : undefined),
    openFunction: (fn, tab) => (current ? current.openFunction(fn, tab) : undefined),
    close: () => (current ? current.close() : false),
    isOpen: () => (current ? current.isOpen() : false),
  };
  if (typeof module === "object" && module !== null && module.exports) module.exports = NodePanel;
  else root.NodePanel = NodePanel;
})(globalThis);
