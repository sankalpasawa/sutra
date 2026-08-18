/* The subagents fold. The rail's "N agents" badge proved these transcripts exist
   but led nowhere; this is where they become readable. Shown only for a REAL
   session that has agents (live now, or already loaded). READ-ONLY: an agent ran
   outside this panel, so there is no composer and no placement, only its turns,
   rendered through the SAME transcriptTurns()/turnResponse() as the main thread. */
/* Relative time from an epoch-seconds mtime — "3m ago", "2h ago", "5d ago". */
function agRelTime(sec){
  if (!sec) return "";
  const s = Math.max(0, Math.floor(Date.now()/1000) - sec);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s/60) + "m ago";
  if (s < 86400) return Math.floor(s/3600) + "h ago";
  return Math.floor(s/86400) + "d ago";
}

function agentsFold(s){
  const list = S.agents[s.id];
  const have = (list && list.length) || s.agents_live;
  if (!s.real || !have) return "";
  const open = !!S.agentsFold[s.id];
  const n = list ? list.length : (s.agents_live || 0);
  const head = `<button class="agfold" type="button" data-agentsfold="${esc(s.id)}"
      aria-expanded="${open}">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.2" aria-hidden="true"><path d="${open?"M6 9l6 6 6-6":"M9 6l6 6-6 6"}"/></svg>
      <b>${n} subagent${n===1?"":"s"}</b>
      <span>agents this session spawned</span></button>`;
  if (!open) return `<div class="agents">${head}</div>`;
  if (list === undefined) return `<div class="agents open">${head}
      <p class="agnone">Reading…</p></div>`;
  if (!list.length) return `<div class="agents open">${head}
      <p class="agnone">No subagent transcripts on disk for this session.</p></div>`;
  const openId = S.agentOpen[s.id];
  const rows = list.map(a=>{
    const sel = openId === a.id;
    const steps = a.steps || a.turns || 0;
    const bits = [`${steps} step${steps===1?"":"s"}`];
    if (a.tools && a.tools.length) bits.push(a.tools.slice(0,3).join(", "));
    bits.push(a.running ? "running" : agRelTime(a.mtime));
    return `<button class="agrow ${sel?"on":""}" type="button"
        data-agentopen="${esc(s.id)}:${esc(a.id)}" aria-pressed="${sel}"
        title="${esc(a.label||"")}">
        <span class="agdot ${a.running?"run":""}" aria-hidden="true"></span>
        <span class="agrow-main">
          <span class="agrow-top">
            <span class="agl">${esc(a.title || a.label || a.id)}</span>
            ${a.agent_type?`<span class="agtype">${esc(a.agent_type)}</span>`:""}
          </span>
          <span class="agm">${esc(bits.filter(Boolean).join(" · "))}</span>
        </span>
        <svg class="agchev" width="12" height="12" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>
      </button>`;
  }).join("");
  const meta = openId ? list.find(a=>a.id===openId) : null;
  const messages = openId ? S.agentTurns[s.id + ":" + openId] : undefined;
  const detail = !openId ? "" : `<div class="agdetail">${agentDetailHtml(meta, messages)}</div>`;
  return `<div class="agents open">${head}<div class="aglist">${rows}</div>${detail}</div>`;
}

/* One subagent rendered as Claude's agent view: a header (title / type / status),
   the task it was handed (collapsed), then its work as a SEQUENCE of steps —
   assistant text as markdown, tool calls as pills — with the final text-bearing
   message set apart as the result. READ-ONLY: an agent ran outside this panel,
   so there is no composer and no placement, only what it did. */
function agentDetailHtml(meta, messages){
  if (messages === undefined || messages === null) return `<p class="agnone">Reading transcript…</p>`;
  if (!messages.length) return `<p class="agnone">No readable turns in this subagent transcript.</p>`;
  const task = messages.find(m=>m.role==="user");
  const steps = messages.filter(m=>m.role==="assistant");
  const title = (meta && meta.title) || "Subagent";
  const when = meta && meta.running ? "running"
             : (meta && meta.mtime ? agRelTime(meta.mtime) : "");
  const head = `<div class="agdhead">
      <span class="agdot ${meta&&meta.running?"run":""}" aria-hidden="true"></span>
      <b class="agdtitle">${esc(title)}</b>
      ${meta&&meta.agent_type?`<span class="agtype">${esc(meta.agent_type)}</span>`:""}
      <span class="agdmeta">${steps.length} step${steps.length===1?"":"s"}${when?" · "+esc(when):""}</span>
    </div>`;
  const taskHtml = task ? `<details class="agtask"><summary>Task it was handed</summary>
      <div class="md">${mdHtml(task.text)}</div></details>` : "";
  let lastTextIdx = -1;
  steps.forEach((m,i)=>{ if (m.text) lastTextIdx = i; });
  let stepsHtml = "";
  for (let i=0;i<steps.length;i++){
    const m = steps[i];
    const txt = m.text ? `<div class="agstep-text md">${mdHtml(m.text)}</div>` : "";
    /* the captured agentic output for this step — command/input + collapsible result */
    const tools = (m.calls && m.calls.length) ? toolCallsHtml(m.calls)
      : ((m.tools&&m.tools.length)
          ? `<div class="agstep-tools">${[...new Set(m.tools)].map(x=>`<span class="pill p-acc">${esc(x)}</span>`).join("")}</div>` : "");
    if (!txt && !tools) continue;
    stepsHtml += `<div class="agstep${i===lastTextIdx?" result":""}">${tools}${txt}</div>`;
  }
  return `${head}${taskHtml}<div class="agsteps">${stepsHtml}</div>`;
}

function sessionPane(s){
  const tab = S.sessTab[s.id] || "chat";
  const collapsed = !!S.ui.paneCollapsed[s.id];
  const last = s.turns[s.turns.length-1];
  const chip = last && last.domain
    ? `<span class="fchip ${last.mode==="floor"?"held":""}">${esc(dPath(last.domain.ref))} ${esc(last.domain.name)}${last.mode==="floor"?" · held":" · "+last.confidence.toFixed(2)}</span>`
    : "";
  /* what the server said it would actually run, from the ws "provider" frame */
  const ch = s.channel;
  const chanChip = ch ? `<span class="pill ${ch.writes_files?"p-block":"p-mut"}">${esc(ch.id)} ·
      ${esc(ch.permission_mode||"")}${ch.writes_files?" · writes files":""}</span>` : "";
  const body = tab==="route" ? routingChart(s) : sessionBody(s);
  return `<section class="pane ${collapsed?"collapsed":""}" data-sess="${s.id}">
    <div class="ph">
      <button class="pfold" type="button" data-pane-fold="${esc(s.id)}"
              aria-expanded="${!collapsed}"
              aria-label="${collapsed?"Expand":"Collapse"} this session pane">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.2" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>
      </button>
      <span class="dot run" aria-hidden="true" style="width:6px;height:6px;border-radius:50%;background:var(--ok);flex:none"></span>
      <h3 title="${esc(s.title)}${s.real&&s.cwd?" — "+esc(s.cwd):""}">${esc(s.title)}</h3>
      ${s.real?`<span class="src">transcript</span>`:""}
      ${s.fork?`<span class="src" title="Branched from another session with --fork-session">fork</span>`:""}
      <span class="tabs">
        <button type="button" data-tab="chat"  data-sid="${s.id}" aria-pressed="${tab==="chat"}">Chat</button>
        <button type="button" data-tab="route" data-sid="${s.id}" aria-pressed="${tab==="route"}">Routing</button>
      </span>
      <button class="ib act-trigger" data-act-toggle type="button"
              aria-label="Activity — running turns and agents"
              title="Activity — running turns & agents (background tasks)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.9" aria-hidden="true"><path d="M3 12h4l2 5 4-13 2 8h6"/></svg>
        <span class="act-badge" data-act-badge hidden>0</span>
      </button>
      <button class="ib" data-sidetoggle="${s.id}" type="button"
              aria-pressed="${!!S.sideOpen[s.id]}"
              aria-label="${S.sideOpen[s.id]?"Hide the side chat":"Open a side chat"}"
              title="Side chat — ask something without touching this thread">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.8" aria-hidden="true">
          <path d="M4 5h11a2 2 0 012 2v5a2 2 0 01-2 2H8l-4 3V5z"/><path d="M19 9h1a1 1 0 011 1v9l-3-2h-5"/>
        </svg>
      </button>
      <button class="ib" data-close="${s.id}" aria-label="Close session">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>
    <div class="pb">${chip||chanChip?`<div style="margin-bottom:10px;display:flex;gap:6px;flex-wrap:wrap">${chip}${chanChip}</div>`:""}${body}</div>
    ${agentsFold(s)}
    ${S.sideOpen[s.id] ? `<div class="sidewrap">
      <div class="sidehead">
        <b>Side chat</b>
        <span>separate thread — nothing here is sent to the conversation above, and it
          is not filed as a placement</span>
        ${sideStreamingFor(s.id) ? `<button class="ib" data-sidestop="${s.id}" type="button"
                aria-label="Stop the side chat turn"
                title="Stop — interrupts this side thread only, never the conversation above">
          <svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg>
        </button>` : ""}
        <button class="ib" data-sideclose="${s.id}" type="button" aria-label="Close the side chat">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="sidebody">${
        (S.sideTurns[s.id]||[]).length
          ? (S.sideTurns[s.id]||[]).map(t=>`<div class="turn">
              <div class="q">${esc(t.text)}</div>${turnResponse(t)}</div>`).join("")
          : `<p class="sidezero">Ask something you do not want in the main thread —
             “would OAuth be better here?” — and the answer stays in this box.</p>`}</div>
      <div class="pc">
        <input type="text" data-sideask="${s.id}" value="${esc(S.sideText[s.id]||"")}"
               placeholder="Ask on the side…" aria-label="Side chat message"/>
        <button class="send" data-sidesend="${s.id}" type="button" aria-label="Send on the side">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
        </button>
      </div></div>` : ""}
    ${S.palette && S.palette.sid===s.id ? paletteHtml() : ""}
    ${(S.attach[s.id]||[]).length ? `<div class="attrow">
      ${(S.attach[s.id]||[]).map((a,i)=>`<span class="att ${a.error?"bad":""}">
        <span class="attn">${esc(a.name)}</span>
        <span class="atts">${a.error ? esc(a.error) : (a.pending ? "uploading…" : fmtBytes(a.bytes))}</span>
        <button class="attx" type="button" data-attrm="${s.id}:${i}"
                aria-label="Remove ${esc(a.name)}">&times;</button></span>`).join("")}
    </div>` : ""}
    ${permConfirmHtml()}
    ${S.optsOpen[s.id] ? turnOptsHtml(s.id) : ""}
    ${cwdEditorHtml(s.id)}
    ${prFormHtml(s.id)}
    ${prListHtml(s.id)}
    ${repoBarHtml(s.id)}
    <div class="pc">
      ${S.usagePop === s.id ? usagePopHtml() : ""}
      <button class="ib" data-optstoggle="${s.id}" type="button"
              aria-expanded="${S.optsOpen[s.id]?"true":"false"}"
              aria-label="Turn options" title="Effort, budget and tool limits for the next message">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.9" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg>
      </button>
      <button class="ib" data-attach="${s.id}" type="button"
              aria-label="Attach a file" title="Attach a file (or drop / paste one)">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.9" aria-hidden="true"><path d="M21 11l-8.5 8.5a4.6 4.6 0 01-6.5-6.5L14 4.5a3 3 0 014.3 4.3l-8.5 8.5a1.5 1.5 0 01-2.1-2.1l7.9-7.9"/></svg>
      </button>
      <!-- A TEXTAREA, not <input type="text">. An input cannot hold a newline at
           any price, so Shift+Enter, Ctrl+J and pasted multi-line text were not
           "unimplemented" -- they were impossible. rows=1 keeps it looking like a
           single line until there is a reason not to; autoGrowComposer() sizes it. -->
      <textarea data-sask="${s.id}" rows="1"
             placeholder="Ask anything — / for commands, Shift+Enter for a new line"
             aria-label="Continue this session">${esc(S.composerText[s.id]||"")}</textarea>
      ${cwdButtonHtml(s.id)}
      ${usageChipHtml()}
      ${permSelect()}
      <select class="modelsel" data-model="${s.id}" aria-label="Model for this session"
              title="Model — applies to the next message">
        ${(MODELS.length?MODELS:[{id:"",name:"CLI default"}]).map(m=>`
          <option value="${esc(m.id)}" ${(S.model[s.id] ?? ((SETTINGS||{}).model||"")) === m.id ? "selected":""}
          >${esc(m.name)}</option>`).join("")}
      </select>
      ${streamingFor(s.id)
        ? `<button class="send stop" data-sstop="${s.id}" type="button" aria-label="Stop this turn"
                   title="Stop — kills the running process">
             <svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg>
           </button>`
        : `<button class="send" data-ssend="${s.id}" type="button" aria-label="Send">
             <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
           </button>`}
    </div></section>`;
}

/* render() does a full innerHTML rebuild, and now some rebuilds are triggered by an
   ASYNC event (a simulate()/loadOrg() fetch resolving) rather than direct user action --
   unlike the earlier fully-synchronous build, a background render can now land while the
   operator is mid-keystroke in the composer, the rationale field, search, or the create-
   department form. Without this, that re-render silently wipes whatever they just typed
   (the click-send handler reads an emptied input and no-ops with no error, no request,
   no visible failure). Capture the focused input's identity + value + caret before
   rebuilding, restore it after -- covers every text input uniformly, not just the ones
   with bespoke keep() handlers. */
/* Size the composer to its content, up to a ceiling.
   Reset to "auto" first: scrollHeight only SHRINKS correctly when the element is
   not already holding a taller explicit height, so without the reset the box
   grows and never comes back down after deleting a paragraph. */
const COMPOSER_MAX_PX = 200;
/* Per-turn CLI options. These map 1:1 onto flags `claude --help` documents, and
   the SERVER validates every one (build_agent_args) -- nothing typed here is
   trusted. Kept per SESSION rather than global: "spend at most $2 on this one"
   is a property of the question being asked, not of the panel. */
const EFFORTS = ["", "low", "medium", "high", "xhigh", "max"];
function turnOptsHtml(sid){
  const o = S.turnOpts[sid] || {};
  return `<div class="topts">
    <label><span>Effort</span>
      <select data-opt="effort" data-sid="${sid}">
        ${EFFORTS.map(e=>`<option value="${e}" ${o.effort===e?"selected":""}>${
          e||"default"}</option>`).join("")}
      </select></label>
    <label><span>Budget</span>
      <input type="number" step="0.5" min="0" placeholder="no cap"
             data-opt="max_budget_usd" data-sid="${sid}"
             value="${o.max_budget_usd!=null?esc(String(o.max_budget_usd)):""}"
             title="--max-budget-usd: stop the turn once it has cost this much"/></label>
    <label class="wide"><span>Allow only</span>
      <input type="text" placeholder="Read Bash Grep — blank means every tool"
             data-opt="allowed_tools" data-sid="${sid}"
             value="${esc((o.allowed_tools||[]).join(" "))}"
             title="--allowedTools: whitespace separated"/></label>
    <label class="wide"><span>Never</span>
      <input type="text" placeholder="WebFetch Write"
             data-opt="disallowed_tools" data-sid="${sid}"
             value="${esc((o.disallowed_tools||[]).join(" "))}"
             title="--disallowedTools: whitespace separated"/></label>
    <label class="wide"><span>Extra instructions</span>
      <input type="text" placeholder="appended to the system prompt for this turn"
             data-opt="append_system_prompt" data-sid="${sid}"
             value="${esc(o.append_system_prompt||"")}"/></label>
    <p class="topts-note">Applies to the next message; the server validates each
      value and drops anything it does not recognise.
      <strong>Denying one tool is not a capability limit</strong> — blocking only
      <code>Read</code>, the agent read the same file with <code>Bash</code>. To
      stop a capability, deny every route to it
      (<code>Read Bash Grep Glob</code>). Measured, not assumed.</p>
  </div>`;
}

function autoGrowComposer(el){
  if (!el || el.tagName !== "TEXTAREA") return;
  el.style.height = "auto";
  const want = Math.min(el.scrollHeight, COMPOSER_MAX_PX);
  el.style.height = want + "px";
  el.style.overflowY = el.scrollHeight > COMPOSER_MAX_PX ? "auto" : "hidden";
}

function _focusedInputSelector(){
  const el = document.activeElement;
  /* TEXTAREA belongs here: the composer is one now, and omitting it means the
     caret jumps to the end on every background re-render while you type. */
  if (!el || !(el.tagName === "INPUT" || el.tagName === "SELECT"
               || el.tagName === "TEXTAREA")) return null;
  if (el.id) return "#" + el.id;
  /* Every one of these is an input with no id that render() rebuilds wholesale.
     The comment above describes the caret fix for the composer; it was never
     generalised, so typing a PR body or a folder path while ANY transcript on
     disk was being written dropped focus to <body> mid-word. Valueless
     attributes need no special case: getAttribute returns "" and [data-x=""]
     matches a bare data-x. */
  for (const attr of ["data-sask", "data-ssend", "data-sideask", "data-cwdinput",
                      "data-prf", "data-edta", "data-workdir-input", "data-edfilter"]) {
    if (el.hasAttribute(attr)) return "[" + attr + '="' + el.getAttribute(attr) + '"]';
  }
  return null;
}
/* ── "/" palette: real slash commands in the composer ──────────────────────
   Typing "/" used to insert a character and offer nothing. The list is the same
   catalog the Skills screen shows (GET /api/skills), so the palette can only ever
   offer something that actually resolves -- and only the RUNNABLE half of it.
   Rendered into the pane body, reusing .tw/.legend. */
/* Only RUNNABLE slash commands are offered. Two filters, both necessary:
     k.slash      -- codex's AGENTS.md and its SKILL.md entries have none. They
                     are real capability files, but nothing is typed to invoke
                     them, so a palette row for them would resolve to nothing.
     k.runnable   -- the provider that resolves the command must have its binary
                     on PATH. ~/.codex existing is not evidence that `codex` does.
   The Skills screen still lists everything, disabled and with the reason. The
   palette is the place where offering something means it will run. */
const runnableCommands = () => SKILLS.filter(k => k.slash && k.runnable);
function paletteFor(text){
  /* Two palettes, one mechanism. "/" offers runnable commands; "@" offers real files
     under the workdir. Sharing the machinery means the keyboard model (arrows, enter,
     tab, escape) is identical for both -- two separate implementations would drift. */
  const at = /(^|\s)@([^\s@]*)$/.exec(text || "");
  if (at){
    const token = at[2].toLowerCase();
    /* Files come from the SAME /api/fs/tree the editor uses, so @ can only ever offer
       a path that exists. Fetched on first use; until it answers the palette stays
       shut rather than showing a stale or invented list. */
    if (!S.fs){ loadFs(false); return null; }
    const items = S.fs.files
      .filter(f => !token || f.path.toLowerCase().includes(token))
      /* Shallower paths first: with no token typed, the top of the project is a far
         more useful default than whatever sorts first alphabetically. */
      .sort((a,b)=> (a.path.split("/").length - b.path.split("/").length)
                 || a.path.length - b.path.length)
      .slice(0, 8)
      .map(f => ({ ref: "@" + f.path, label: f.path, meta: fmtBytes(f.bytes) }));
    return { token, items, kind: "file" };
  }
  const m = /(^|\s)\/([A-Za-z0-9:_-]*)$/.exec(text || "");
  if (!m) return null;
  const token = m[2].toLowerCase();
  const items = runnableCommands().filter(k =>
    k.slash.slice(1).toLowerCase().includes(token) ||
    (k.name||"").toLowerCase().includes(token)).slice(0, 8)
    .map(k => ({ ref: k.slash, label: k.slash, meta: (k.description||"").slice(0,72) }));
  return { token, items, kind: "command" };
}
function paletteHtml(){
  const p = S.palette;
  if (!p || !p.items.length) return "";
  const total = p.kind === "file"
    ? ((S.fs && S.fs.files.length) || 0) + " files"
    : runnableCommands().length + " runnable";
  return `<div class="tw" style="margin-bottom:9px">
    <table><tbody>${p.items.map((k,i)=>`
      <tr data-pal="${i}" class="${i===p.idx?"sel":""}" style="cursor:pointer">
        <td class="k" style="white-space:nowrap"><code>${esc(k.label)}</code></td>
        <td>${esc(k.meta||"")}</td></tr>`).join("")}
    </tbody></table>
    <div class="legend" style="padding:6px 9px">up/down to move · enter or tab to insert ·
      esc to dismiss · ${p.items.length} of ${total}</div></div>`;
}
function applyPalette(sid, idx){
  const p = S.palette; if (!p || !p.items[idx]) return;
  const inp = document.querySelector('[data-sask="'+sid+'"]'); if (!inp) return;
  /* Compute the new value FIRST, render, THEN write it back. Setting it before
     render() lost it entirely: render() rebuilds the pane from the template and
     only restores the value of the element that happened to be focused, so a
     CLICKED palette row (input not focused) silently cleared the composer. */
  const cur = S.composerText[sid] !== undefined ? S.composerText[sid] : inp.value;
  /* Replace the token that OPENED this palette, not a hardcoded "/" pattern -- with
     @ live, the wrong pattern would leave the "@frag" in place and append the path
     after it. */
  const pat = p.kind === "file" ? /(^|\s)@[^\s@]*$/ : /(^|\s)\/[A-Za-z0-9:_-]*$/;
  const next = cur.replace(pat, (mm, pre)=> pre + p.items[idx].ref + " ");
  S.composerText[sid] = next;
  S.palette = null;
  render();
  const back = document.querySelector('[data-sask="'+sid+'"]');
  if (back) { back.value = next; back.focus();
              back.setSelectionRange(next.length, next.length); }
}

/* Knowledge search -- debounced, server-side. */
let _sqT = null;
function runSearch(q){
  S.sq = q;
  clearTimeout(_sqT);
  if (!q.trim()){ S.searchRes = null; S.searchHits = null; S.searchBusy = false; render(); return; }
  S.searchBusy = true;
  _sqT = setTimeout(()=>{
    apiGet("/api/org/search?q=" + encodeURIComponent(q) + "&limit=40")
      .then(r => { S.searchRes = r; S.searchHits = r.results.length; S.searchBusy = false; render(); })
      .catch(e => { S.searchRes = { query:q, results:[], counts:{}, error:e.message };
                    S.searchHits = 0; S.searchBusy = false; render(); });
  }, 250);
}

/* ── first run ───────────────────────────────────────────────────────────────
   Four facts the operator needs BEFORE the panel starts driving a CLI on their
   machine, each read from the same endpoint the corresponding screen uses:
   which assistant runs, where it works, what it is allowed to do, what it can
   see. Every value is live -- there is no illustrative copy here, so a machine
   with no `claude` on PATH is told that on step 1 instead of after its first
   message dies. Dismissing writes settings.onboarded=true server-side; a
   browser flag would re-show this on another browser and skip it after a
   settings reset, and this is exactly the disclosure that must not be skipped. */
function onboardingHtml(){
  const st = SETTINGS || {};
  const running = st.permission_mode_effective || st.permission_mode || "plan";
  const runnable = PROVIDERS.filter(p=>p.runnable);
  const active = PROVIDERS.find(p=>p.id===st.provider) || runnable[0] || null;
  const blocked = PROVIDERS.filter(p=>!p.runnable);
  const writes = running !== "plan";

  const step = (n, title, body) => `<div class="onb-step">
    <span class="onb-num">${n}</span><div class="onb-b">${title}${body}</div></div>`;

  return `<div class="onb" role="dialog" aria-modal="true" aria-label="Welcome to Sutra">
    <div class="onb-card">
      <h1>Welcome to Sutra</h1>
      <p class="onb-lede">A reader for your placement registry — the departments, charters and
        placements your work is filed into — with an assistant alongside it. Four things worth
        knowing before you start. All of them are live readings from this machine, not examples.</p>

      ${step(1, `<h3>${active
          ? `It drives <code>${esc(active.name)}</code>`
          : "No assistant can run here yet"}</h3>`,
        active
          ? `<p>Chat in this panel spawns your local <code>${esc(active.bin)}</code> CLI and bills as
               your existing subscription — never an API key.</p>
             <div class="onb-fact">${esc(active.bin_path||"")}</div>`
          : `<p>None of the ${PROVIDERS.length} catalogued assistants is usable on this machine, so
               chat is unavailable. Everything else — departments, charters, placements — still works.</p>
             ${blocked.map(p=>`<div class="onb-fact">${esc(p.name)} — ${esc(p.reason||"")}</div>`).join("")}`)}

      ${step(2, `<h3>It works in one directory</h3>`,
        `<p>Every session this panel starts runs with this as its working directory. It is created
           if it does not exist.</p>
         <div class="onb-fact">${esc(st.workdir||"—")}</div>`)}

      ${step(3, `<h3>${writes
          ? "The assistant can change files"
          : "The assistant proposes, you approve"}</h3>`,
        `<p>${writes
            ? `Sessions run as <code>${esc(running)}</code> — edits under the workdir are applied
               without prompting you first.`
            : `Sessions run as <code>${esc(running)}</code>: it reads and plans, and every edit needs
               your approval. You can widen this in Settings.`}</p>
         ${st.permission_mode_clamped?`<div class="onb-fact">note: <code>${esc(st.permission_mode)}</code>
           is on file but is not honoured — sessions run as <code>${esc(running)}</code></div>`:""}`)}

      ${step(4, `<h3>It reads what is already on your disk</h3>`,
        `<p>The registry below, and every slash command your assistant can already resolve. Nothing
           was seeded or invented for this screen.</p>
         <div class="onb-fact">${live().length} departments ·
           ${CHARTERS.length} charters · ${PLACEMENTS.length} placements ·
           ${(SKILLS_META&&SKILLS_META.total)||0} commands</div>`)}

      <div class="onb-foot">
        <span class="sp">You can change any of this later in Settings.</span>
        <button class="onb-skip" type="button" data-onb="later">Not now</button>
        <button class="onb-go" type="button" data-onb="done">Start using Sutra</button>
      </div>
    </div></div>`;
}

/* Mounted OUTSIDE #app so render()'s wholesale replacement of #panes cannot
   tear it down mid-interaction. */
/* ── staged desktop update ─────────────────────────────────────────────────
   The update is MANDATORY (founder direction 2026-08-06), which decides the
   shape of this UI more than anything else: there is no "skip this version"
   and no "remind me next week", because neither is true. Cancel stops the
   countdown and nothing else -- the build is already downloaded and verified,
   and the shell applies it when the app next exits. So the honest words are
   "not now", and then a plain statement of what will happen anyway.

   TWO REASONS THIS IS NOT ALWAYS A COUNTDOWN:

     no shell    The CLI serves this same panel to an ordinary browser, where
                 there is nothing to restart. window.sutra only exists behind
                 the Electron preload, so its absence is a reliable "I cannot
                 honour a countdown" -- and a countdown that cannot restart
                 anything would be a lie told once every fifteen seconds.

     no focus    The clock only runs while the window has focus. A countdown
                 that ran in the background would restart the app while the
                 user was in another window, having never seen the banner --
                 which is not a prompt, it is an ambush. */
const UPDATE_COUNTDOWN_S = 15;
const UPDATE_POLL_MS = 60000;
let _updTicker = null;

function updDesktop(){ return !!(window.sutra && window.sutra.desktop); }

async function pollStagedUpdate(){
  try {
    /* Local staging state only -- this route never touches the network, which
       is why a poll is acceptable here and would not be on /api/updates. */
    S.updStaged = await apiGet("/api/updates/staged");
  } catch (e) { S.updStaged = null; }
  renderUpdateBanner();
}

function updTick(){
  /* Held, not decremented, while the window is in the background. */
  if (!document.hasFocus()) { renderUpdateBanner(); return; }
  if (S.updLeft === null) return;
  S.updLeft -= 1;
  if (S.updLeft > 0) { renderUpdateBanner(); return; }
  stopUpdCountdown();
  applyUpdateNow();
}

function stopUpdCountdown(){
  if (_updTicker) { clearInterval(_updTicker); _updTicker = null; }
  S.updLeft = null;
}

async function applyUpdateNow(){
  stopUpdCountdown();
  /* Set BEFORE the render below, which would otherwise see "staged, no clock
     running, no error yet" and start a second countdown -- firing applyUpdate
     again every fifteen seconds for as long as the shell took to quit. */
  S.updFiring = true;
  S.updApplyError = null;
  renderUpdateBanner();
  try {
    const r = await window.sutra.applyUpdate();
    /* On success the app is already on its way out; leave the banner saying so
       rather than flashing something else in the last frames. */
    if (!r || !r.ok) S.updApplyError = (r && r.error) || "the restart was refused";
  } catch (e) { S.updApplyError = e.message || String(e); }
  if (S.updApplyError) S.updFiring = false;   /* the app is staying; allow a retry */
  renderUpdateBanner();
}

function renderUpdateBanner(){
  let host = document.getElementById("updHost");
  const u = S.updStaged;
  /* `error` on a PENDING record is the reason the last attempt failed -- it is
     the most important thing the banner has to say, not a signal to say
     nothing. (An unusable staging directory reports {pending:false} instead,
     and is correctly silent.) */
  const show = !!(u && u.pending);
  if (!show){ stopUpdCountdown(); if (host) host.remove(); return; }
  if (!host){
    host = document.createElement("div");
    host.id = "updHost";
    document.body.appendChild(host);
  }

  const ver = esc(u.version || "a new version");
  const armed = u.state === "installing";
  const counting = updDesktop() && !armed && !S.updDeferred && u.state === "staged";

  /* Start the clock the first time we see a staged build this load. */
  if (counting && S.updLeft === null && !_updTicker && !S.updApplyError && !S.updFiring){
    S.updLeft = UPDATE_COUNTDOWN_S;
    _updTicker = setInterval(updTick, 1000);
  }

  /* Founder decision 2026-08-06: a live terminal WARNS, it does not stop the
     clock. Said plainly, because the restart will take the session with it. */
  const termWarn = S.termOpen
    ? `<div class="updwarn">A terminal session is open. Restarting Sutra ends it.</div>` : "";

  let body;
  if (S.updApplyError){
    body = `<div class="updmsg"><b>Sutra ${ver} could not be applied.</b>
      <span class="updwhy">${esc(S.updApplyError)}</span>
      <span class="updwhy">It will be retried when you quit.</span></div>
      <div class="updacts"><button class="btn" type="button" data-upd2="retry">Try again</button></div>`;
  } else if (armed){
    body = `<div class="updmsg"><b>Sutra ${ver} is ready to install.</b>
      <span class="updwhy">It is applied as soon as the app closes.</span></div>`;
  } else if (!updDesktop()){
    /* Browser / CLI: state the fact, promise nothing this page can't keep. */
    body = `<div class="updmsg"><b>Sutra ${ver} has been downloaded.</b>
      <span class="updwhy">It installs the next time the desktop app quits.</span></div>`;
  } else if (u.state === "failed"){
    /* Given up on automatically. Reached via resolve_pending's "manual"
       verdict, and it must NOT fall through to the countdown -- there is no
       clock running, so it would render "Restarting in nulls". */
    body = `<div class="updmsg"><b>Sutra ${ver} could not be installed.</b>
      <span class="updwhy">${esc(u.error || "the installer did not report why")}</span>
      <span class="updwhy">Settings → Updates has the manual install.</span></div>`;
  } else if (S.updDeferred){
    body = `<div class="updmsg"><b>Sutra ${ver} will finish installing when you quit.</b>
      <span class="updwhy">Nothing to download again — it is already verified.</span></div>`;
  } else if (S.updFiring){
    /* The countdown fired applyUpdate: the clock is stopped (S.updLeft === null) and
       the app is on its way out. Say so — do NOT fall through to the countdown
       branch below, which with a null clock renders "Restarting in nulls". */
    body = `<div class="updmsg"><b>Sutra ${ver} is restarting…</b>
      <span class="updwhy">Installing on the way out — this window will close.</span></div>`;
  } else {
    const paused = !document.hasFocus();
    /* Null-safe backstop: S.updLeft can be null for a frame before the clock is
       (re)started; never print the literal "nulls". */
    const when = paused
      ? "Restarting when you come back to this window."
      : (S.updLeft != null
          ? `Restarting in <span class="updn">${S.updLeft}s</span>.`
          : "Restarting shortly…");
    body = `<div class="updmsg"><b>Sutra ${ver} is ready.</b>
      <span class="updwhy">${when}</span></div>
      <div class="updacts">
        <button class="btn pri" type="button" data-upd2="now">Restart now</button>
        <button class="btn" type="button" data-upd2="later">Not now</button>
      </div>`;
  }

  host.innerHTML = `<style>
    #updHost{position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:9000;
      max-width:min(720px,calc(100vw - 32px));}
    #updHost .updbar{display:flex;gap:14px;align-items:center;flex-wrap:wrap;
      background:var(--panel,#1b1917);border:1px solid var(--line,#332f2a);
      border-radius:10px;padding:11px 14px;box-shadow:0 8px 28px rgba(0,0,0,.45);}
    #updHost .updmsg{font-size:12.5px;line-height:1.5;flex:1 1 320px;}
    #updHost .updwhy{display:block;color:var(--muted,#9b938a);font-size:11.5px;}
    #updHost .updn{font-variant-numeric:tabular-nums;}
    #updHost .updacts{display:flex;gap:8px;flex:0 0 auto;}
    #updHost .updwarn{flex:1 1 100%;font-size:11.5px;color:var(--warn,#d9a441);}
  </style><div class="updbar">${body}${termWarn}</div>`;

  host.querySelectorAll("[data-upd2]").forEach(b=>b.onclick=()=>{
    const a = b.dataset.upd2;
    if (a === "now" || a === "retry") return applyUpdateNow();
    /* "Not now" is a DEFER, and the copy above says so. The staged build is
       kept; the shell applies it on the way out. */
    S.updDeferred = true;
    stopUpdCountdown();
    if (window.sutra && window.sutra.deferUpdate) window.sutra.deferUpdate();
    renderUpdateBanner();
  });
}

function renderOnboarding(){
  let host = document.getElementById("onbHost");
  const show = !!(SETTINGS && SETTINGS.onboarded === false && !S.onbDismissed);
  if (!show){ if (host) host.remove(); return; }
  if (!host){
    host = document.createElement("div");
    host.id = "onbHost";
    document.body.appendChild(host);
  }
  host.innerHTML = onboardingHtml();
  host.querySelectorAll("[data-onb]").forEach(b=>b.onclick=()=>{
    /* "Not now" hides it for this load only and does NOT persist -- the
       disclosure returns next launch, because it was never acknowledged. */
    if (b.dataset.onb === "later"){ S.onbDismissed = true; renderOnboarding(); return; }
    S.onbDismissed = true;
    renderOnboarding();
    apiPost("/api/settings", { onboarded: true })
      .then(r=>{ SETTINGS = r.settings || SETTINGS; })
      .catch(()=>{ /* the panel is usable either way; it simply shows again next launch */ });
  });
}

function render(){
  /* A drag is a live binding between the dragged node and the drop targets'
     ondragover/ondrop handlers. render() replaces #panes wholesale, so a
     background render (a simulate() fetch resolving mid-gesture) swaps every
     node under the cursor for a fresh one with no handlers attached yet: the
     drop then silently never fires and the operator's move is lost with no
     error. Defer; dragend/drop flushes it. */
  if (S.drag){ S.renderDirty = true; return; }
  S.renderDirty = false;
  const sel = _focusedInputSelector();
  const prior = sel ? { sel, value: document.activeElement.value,
    start: document.activeElement.selectionStart, end: document.activeElement.selectionEnd } : null;
  /* SCROLL POSITION, for the same reason focus and caret are saved here.
     render() replaces #panes wholesale, so the browse pane's scroller is a
     brand-new element scrolled to 0 -- clicking a Directory status filter 800px
     down the Charters table threw the operator back to the top of the page, on
     every click. Keyed by screen+view so this only ever restores a position the
     operator can still recognise: SWITCHING view or screen is a new document
     and correctly starts at the top. */
  const priorScroll = _browseScrollState();
  const priorSess = _sessScrollState();

  renderRail();
  renderOnboarding();
  renderUpdateBanner();

  document.getElementById("app").classList.toggle("railcol", !!S.ui.railCollapsed);

  const [t,src] = TITLES[S.screen];
  const open = S.openPanes.map(id=>S.sessions.find(s=>s.id===id)).filter(Boolean);
  const bCol = !!S.ui.paneCollapsed.browse;
  /* a dragged width wins over the default flex ratio; without a drag the pane
     keeps the original `flex:1 1 480px` and nothing about the layout changed.

     CLAMPED to the CURRENT window, not the one it was dragged in. The width is
     persisted, so a pane widened on a 1600px display came back at that width
     on a 1000px one: the pane overflowed .panes, the session pane next to it
     was pushed out of sight, and the only way back was a sideways scroll to
     find a divider that was itself off-screen. Same ceiling the drag itself
     uses (leave >=170px for the session pane), so the restored width can never
     be one the drag would have refused. The stored value is left alone -- go
     back to the wide display and the original width returns. */
  /* A pinned width is only meaningful when there is ANOTHER expanded pane to
     share the row with. Pinning unconditionally was the dead-space bug: with a
     single pane (session closed, or every session pane collapsed) the browse
     pane sat at its dragged width -- measured 453px inside a 1061px row, 608px
     of the container simply unclaimed, because `flex:0 0 <px>` sets flex-grow
     to 0 and nothing else was left to grow. The stored width is NOT discarded;
     it is just not applied while it would strand space. Reopen a session and
     the drag width returns. */
  const expandedSessions = open.filter(s => !S.ui.paneCollapsed[s.id]).length;
  const pinBrowse = !bCol && S.ui.browseW && expandedSessions > 0;
  /* COLLAPSED emits NO inline flex. `.pane.collapsed` already pins the rail to
     38px, but an inline style beats a stylesheet rule, so the old unconditional
     `flex:1 1 auto` overrode it and the collapsed rail GREW to fill the row --
     a 38px strip stretched across ~600px with its vertical label floating in
     the middle. Letting the class own the collapsed width is the whole fix. */
  const bStyle = bCol
    ? ""
    : pinBrowse
      ? ` style="flex:0 0 ${clampBrowseW(S.ui.browseW)}px;max-width:none"`
      : ` style="flex:1 1 auto;max-width:none"`;
  document.getElementById("panes").innerHTML =
    `<section class="pane browse ${bCol?"collapsed":""}"${bStyle}>
       <div class="ph">
         <button class="pfold" type="button" data-pane-fold="browse"
                 aria-expanded="${!bCol}"
                 aria-label="${bCol?"Expand":"Collapse"} the browse pane">
           <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2.2" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>
         </button>
         <h3 style="max-width:none">${esc(t)}</h3>
         </div>
       <div class="pb" id="scBody"></div>
     </section>`
    + (open.length && !bCol
        ? `<button class="pdiv" id="pdiv" type="button" role="separator"
             aria-orientation="vertical" aria-label="Resize the browse pane
             (left and right arrows adjust, home resets)"></button>` : "")
    + open.map(sessionPane).join("");
  document.getElementById("scBody").innerHTML = SCREENS[S.screen]();
  wire();

  /* Fill the repository bar for whatever panes are open. Idempotent -- loadRepo
     returns immediately once S.repo[sid] is set -- so calling it from render()
     costs one subprocess per session rather than one per repaint, and a pane
     opened later gets its bar without a second code path. */
  S.openPanes.forEach(sid => loadRepo(sid, false));
  /* THE FLOOR under "an open pane has read its transcript". This used to be the
     responsibility of each site that opens a pane -- the rail's click handler,
     the keyboard nav, the boot block -- and the ⋮ > "open in repo" action was
     one that forgot, so it pushed a session into openPanes at loadState
     "unread" and left it there. Nothing recovered it: ensureTranscript() only
     acts on "unread" but is only CALLED from those open sites, and the
     background re-read in applySessionChange() fires only when the SSE reports
     a WRITE to that file. An idle transcript is never written, so the pane sat
     on "Transcript not read yet" forever -- not a flicker, a permanent state.
     Enforcing it here makes the invariant structural: every path into
     openPanes, including ones not yet written, gets the read. Idempotent for
     the same reason loadRepo is -- ensureTranscript() returns immediately
     unless the session is real AND still unread, so a repaint costs nothing. */
  S.openPanes.forEach(sid => ensureTranscript(S.sessions.find(x=>x.id===sid)));
  /* Prime the subagents fold for open panes receiving agent writes, or already
     expanded. Idempotent like loadRepo. */
  S.openPanes.forEach(sid => {
    const s = S.sessions.find(x=>x.id===sid);
    if (s && s.real && (s.agents_live || S.agentsFold[sid])) loadAgents(sid, false);
  });

  /* A turn may have just started, so the strip needs a clock. Idempotent, and
     the ticker clears itself on the first tick after the last turn ends. */
  ensureRunTicker();

  if (prior) {
    const el = document.querySelector(prior.sel);
    if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) {
      el.value = prior.value;
      el.focus();
      if (typeof prior.start === "number" && el.setSelectionRange) {
        try { el.setSelectionRange(prior.start, prior.end); } catch (e) {}
      }
    }
  }
  _restoreBrowseScroll(priorScroll);
  _restoreSessScroll(priorSess);
  /* Rendered LAST and outside #panes, so it survives a pane rebuild and cannot
     be what a scroll restore is measuring. */
  {
    let el = document.getElementById("toast");
    if (S.toast){
      if (!el){ el = document.createElement("div"); el.id = "toast";
                el.className = "toast"; el.setAttribute("role","status");
                document.body.appendChild(el); }
      el.textContent = S.toast;
    } else if (el) el.remove();
  }
  /* AFTER #panes is populated -- scrollHeight is meaningless before layout. */
  scrollNewSessionsToNewest();
}

/* ── session transcript scroll, across a rebuild ──────────────────────────
   render() replaces #panes wholesale, so every session pane's scroller is a
   BRAND NEW element starting at scrollTop 0. The browse pane has been protected
   from that for a while; the session panes never were. During one reply that is
   a turn-start render, a render per tool call and a done render -- so a turn
   with six tool calls threw the reader back to the top of the transcript six
   times. That is the "it scrolls me to the top for every message" report.

   Two states worth keeping apart, which is what Claude Code's own transcript
   does:
     PINNED   the reader is at the bottom watching it arrive -> stay at the
              bottom as content grows (follow the tail).
     PARKED   the reader scrolled up to read something -> keep their EXACT
              offset. Yanking someone to the tail while they are reading is the
              worse failure of the two, so `pinned` requires being genuinely at
              the bottom, not merely near it.
   S.userScrolled already records which, maintained by the scroll listener. */
const SESS_PIN_SLOP = 24;      // px; a hair of tolerance for subpixel layout

function _sessScrollState(){
  const out = [];
  document.querySelectorAll("#panes .pane[data-sess] .pb").forEach(pb=>{
    const sid = pb.closest(".pane").dataset.sess;
    if (!sid) return;
    const atBottom = pb.scrollHeight - pb.clientHeight - pb.scrollTop <= SESS_PIN_SLOP;
    out.push({ sid, top: pb.scrollTop, pinned: atBottom });
  });
  return out;
}

function _restoreSessScroll(prior){
  if (!prior || !prior.length) return;
  const apply = () => prior.forEach(p=>{
    const pane = document.querySelector('#panes .pane[data-sess="' + CSS.escape(p.sid) + '"]');
    const pb = pane && pane.querySelector(".pb");
    if (!pb) return;                       /* pane closed during the rebuild */
    /* __pinning marks this as OUR scroll so the listener does not read it as
       the reader choosing to move -- otherwise following the tail would
       immediately look like a manual scroll and unpin itself. */
    pb.__pinning = true;
    pb.scrollTop = p.pinned ? pb.scrollHeight
                            : Math.min(p.top, Math.max(0, pb.scrollHeight - pb.clientHeight));
    requestAnimationFrame(()=>{ pb.__pinning = false; });
  });
  apply();
  /* Once more after layout: images, code blocks and tool rows settle late, and
     a height that grew after the synchronous pass would leave a pinned reader
     short of the tail. */
  requestAnimationFrame(apply);
}

/* The browse pane's scroller, and the identity of what it is scrolling.
   S.view distinguishes Live / Draft / Directory, which are three different
   documents in one screen; without it, switching to Directory would inherit
   the org chart's offset. */
function _browseScrollKey(){
  return S.screen + ":" + (S.view || "");
}
function _browseScroller(){
  return document.querySelector("#panes .pane.browse .pb");
}
function _browseScrollState(){
  const el = _browseScroller();
  if (!el || !el.scrollTop) return null;
  return { key: _browseScrollKey(), top: el.scrollTop };
}
function _restoreBrowseScroll(prior){
  if (!prior || prior.key !== _browseScrollKey()) return;
  const el = _browseScroller();
  if (!el) return;
  el.scrollTop = prior.top;
  /* Re-apply once after layout. The synchronous set above is enough whenever
     the new content is at least as tall as the old, which is the common case;
     it silently clamps to a shorter document (a filter that removed rows), and
     a rAF pass lands the honest maximum instead of leaving it at 0. */
  requestAnimationFrame(()=>{
    const e2 = _browseScroller();
    if (e2 && prior.key === _browseScrollKey() && e2.scrollTop !== prior.top) {
      e2.scrollTop = Math.min(prior.top, Math.max(0, e2.scrollHeight - e2.clientHeight));
    }
  });
}
/* A transcript is a LOG: the interesting end is the newest turn. Opening a
   60-turn session at turn 1 makes the operator scroll to find what just
   happened. Scroll once per pane-open, then leave the scroll position alone so
   a re-render (a streaming token, a sim result) never yanks the view back. */
function scrollNewSessionsToNewest(){
  const open = new Set(S.openPanes);
  [...S.userScrolled.keys()].forEach(id => { if (!open.has(id)) S.userScrolled.delete(id); });
  requestAnimationFrame(()=>{
    document.querySelectorAll("#panes .pane[data-sess]").forEach(pane=>{
      const sid = pane.dataset.sess;
      const pb = pane.querySelector(".pb");
      if (!pb || pb.__sutraBound) return;
      pb.__sutraBound = true;
      /* Distinguish OUR scroll from the operator's: only a scroll we did not
         cause counts as intent. Landing back at the bottom clears it again. */
      pb.addEventListener("scroll", ()=>{
        if (pb.__pinning) return;
        const atBottom = pb.scrollHeight - pb.clientHeight - pb.scrollTop < 24;
        if (atBottom) S.userScrolled.delete(sid); else S.userScrolled.set(sid, true);
      }, { passive:true });
    });
    /* Fixed timeouts do not work here. Transcripts range from 2 turns to ~1MB,
       and layout finishes whenever it finishes -- a 120/400/900ms ladder pinned
       three sessions and missed the largest. FOLLOW THE LAYOUT instead: poll
       scrollHeight and re-pin every time it grows, stopping when it stops
       changing, when the operator scrolls, or after a hard 4s ceiling so this
       can never become a permanent timer. */
    document.querySelectorAll("#panes .pane[data-sess]").forEach(pane=>{
      const sid = pane.dataset.sess;
      const pb = pane.querySelector(".pb");
      if (!pb || pb.__pinTimer) return;
      let lastH = -1, stable = 0, ticks = 0;
      pb.__pinTimer = setInterval(()=>{
        ticks++;
        const done = () => { clearInterval(pb.__pinTimer); pb.__pinTimer = null; };
        if (S.userScrolled.get(sid) || ticks > 40) return done();   // 4s ceiling
        const h = pb.scrollHeight;
        if (h <= pb.clientHeight + 1) return;                       // nothing yet
        if (h === lastH){ if (++stable >= 3) done(); return; }       // settled
        lastH = h; stable = 0;
        pb.__pinning = true;
        pb.scrollTop = h;                                            // newest turn is last
        setTimeout(()=>{ pb.__pinning = false; }, 0);
      }, 100);
    });
  });
}

