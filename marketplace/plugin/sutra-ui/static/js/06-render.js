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
  const open = S.agentsFold[s.id] === true;
  /* An EXPLICIT open request always renders the fold. A session the panel
     started is not `real` (transcript-adopted) yet, so the old guard returned
     "" even after a roster drill-down set S.agentsFold — the operator clicked
     an agent and watched nothing whatsoever happen. Observed live. When the
     request finds nothing on disk, the honest empty/note states below render
     instead of a blank. Unopened non-real sessions still show nothing. */
  if ((!s.real || !have) && !open) return "";
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
  /* Set when a drill-down from a turn's roster could not resolve to exactly one
     transcript. Says so instead of silently opening nothing -- or worse, opening
     a plausible-looking wrong one. Reuses .agnone, the same line "Reading…" and
     "No subagent transcripts" already use. */
  const note = (S.agentNote && S.agentNote[s.id])
    ? `<p class="agnone">${esc(S.agentNote[s.id])}</p>` : "";
  return `<div class="agents open">${head}${note}<div class="aglist">${rows}</div>${detail}</div>`;
}

/* Correlate a turn's roster row with a subagent transcript.
   THE TWO IDS ARE NOT THE SAME, and treating them as such would open the wrong
   agent: a roster row is keyed by the `tool_use` id off the wire, while the
   fold's rows are keyed by transcript FILENAME (session_reader.py: id = f.stem).
   The server already pairs them -- _parent_tasks() matches an agent to its Task
   by prompt prefix -- and then surfaces the SAME two fields on both sides:
   subagent_type/agent_type and description/title. So this re-joins on the
   pairing the server made rather than inventing a second, weaker one.

   An AMBIGUOUS match resolves to nothing on purpose. Two agents of the same type
   with the same description are indistinguishable here, and picking one would be
   a coin flip presented as an answer. */
function agentMatch(list, kind, desc, peers){
  if (!list || !list.length || !desc) return null;
  /* Ambiguity has TWO sides, and checking only one was a real hole: if two rows
     in the SAME turn normalise to the same key and only one transcript happens
     to be on disk, both rows would resolve to it -- confidently opening the
     wrong agent. `peers` is how many rows in this turn share this row's key. */
  if (peers > 1) return null;
  /* the roster caps desc at 120 and may end in an ellipsis; the server caps
     title at 80. Compare on the common ground. */
  const nd = s => String(s||"").replace(/…+$/, "").trim().toLowerCase().slice(0, 80);
  const nk = s => String(s||"").trim().toLowerCase();
  const d = nd(desc), k = nk(kind);
  if (!d) return null;
  const hits = list.filter(a =>
    nd(a.title) === d && (!a.agent_type || !k || nk(a.agent_type) === k));
  return hits.length === 1 ? hits[0] : null;
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

/* The composer's PANE menu (chat-surface chrome, founder 2026-08-18): every
   control the pane header used to carry, in one place. Namespaced paneMenu /
   data-panemenu on purpose -- S.sessMenu + sessMenuHtml() already belong to the
   RAIL's per-session actions menu (rename / pin / archive), and a second owner
   of that name silently broke it. The popover reuses .upop; rows either dispatch
   through paneMenuAction() or -- for Permissions and Model -- are LABELS around
   the existing selects, so the [data-perm]/[data-model] handlers in wire()
   survive unchanged (a select inside a button is invalid HTML -- codex P1). */
/* THIS PANE'S provider id. Three controls now key off it (Model, Permissions,
   Turn options) and they must agree, so the expression lives in one place.

   s.channel is what the SERVER said it would actually run (the ws "provider"
   frame), so a pane opened under DeepSeek keeps its own answer after the global
   default is switched to Claude. SETTINGS.provider covers only the pane that
   has not received its frame yet.

   Undefined before /api/settings resolves, and that is on purpose -- see
   paneDeclProvider below for the one kind of question that can be answered
   earlier, and why this one cannot. */
function paneProvider(s){
  /* A SWITCH ALREADY ASKED FOR OUTRANKS THE FRAME IT HAS NOT REPLACED YET.
     A chat-level switch is armed as a one-shot request (S.chatProvider, read
     by claudeWsUrl) and only becomes `s.channel` when the next socket opens
     and the server answers — which for a menu-driven switch is not until the
     next message is sent. Without this the pane would keep reporting the
     provider it is LEAVING for as long as the operator looks at the menu
     without typing: the Chat AI Provider row would snap back to Claude a
     moment after Codex was chosen, and the Model and Permissions rows beside
     it would go on offering Claude's for a chat whose next turn is Codex's.
     Ranked first because it is the most recent fact about where this chat is
     going, and spent the moment the socket carries it. */
  /* `s.source` sits between the two for ONE window: a chat reopened from the
     rail before its socket exists. The chat's real answer lives server-side in
     provider_history, which only the ws `provider` frame can report -- but the
     rail already knows which provider WROTE this chat's transcript
     (GET /api/sessions -> session_reader), and for a chat that has switched
     that is the provider it switched TO. So a Codex chat reopened from the
     rail no longer paints Claude's model list for the window before its first
     message. Still a hint, not the answer: the frame overwrites it the moment
     it lands, which is why it ranks below s.channel and not above. */
  return (s && sessProviderRequest(s.id))
      || (s && s.channel && s.channel.id)
      || (s && s.source)
      || (SETTINGS || {}).provider;
}
/* IS THIS CHAT GOVERNED BY THE GLOBAL SETTING, or by its own choice?

   Answered off the SERVER's provider frame rather than any local state,
   because `source` is how ws_chat actually resolved the provider and nothing
   in the browser can know better:

     "chat"          an explicit ?provider= -- the in-chat request that switched it
     "chat-history"  the chat's own provider_history segment (app.py _chat_local_provider)
     env/settings/fallback   the global default

   Used by the Settings handler to leave chat-local chats alone, and by the
   composer to stop promising that a global change will move them. A pane with
   no socket yet answers false: nothing has told us otherwise, and claiming a
   chat is pinned when it may not be would strand it on a provider the operator
   never chose. */
function providerIsChatLocal(sid){
  const s = (S.sessions || []).find(x => x.id === sid);
  const src = s && s.channel && s.channel.source;
  return src === "chat" || src === "chat-history";
}
/* THE SAME PANE, for a DIFFERENT KIND OF QUESTION -- and the split is the fix
   for a real defect, not a convenience.

   An UNSTARTED pane has no channel: the provider frame arrives with the socket,
   i.e. on the first message. So until then paneProvider is SETTINGS.provider,
   and SETTINGS is null until /api/settings resolves. Every consumer therefore
   took its not-loaded branch during the boot window -- and for turn options
   that branch renders CLAUDE'S FIVE. On a DeepSeek pane. In precisely the
   window when this menu gets opened, which is before asking anything, to set
   something first.

   What separates the two is WHAT THE CONTROL NEEDS TO KNOW:

     a DECLARATION  -- "which controls can this provider honour?" Static per
                       provider, so app.py can put it in the page and 01-state
                       reads it at parse time (SEED). Answerable on the first
                       paint. Permissions and Turn options ask this.
     FETCHED STATE  -- "what has this provider actually reported?" (usage_kind
                       off GET /api/providers) or "which models exist?"
                       (MODELS_BY_PROVIDER). No amount of knowing the provider
                       id answers these before the fetch. Usage and Model ask
                       this, and they keep paneProvider above.

   Feeding the seed to the fetched-state controls looked free and was not: the
   Usage row reads `usageKindOf(mpid) === "none"` and usageKindOf answers "none"
   for ANY id while PROVIDERS is unfetched, so a known id turns its boot-window
   text from "not reported for default" into "not reported for Claude Code" --
   a vague false claim sharpened into a specific one. That is a defect in the
   Usage row's not-loaded branch, logged rather than fixed here, and this split
   is what keeps it from spreading while it waits. */
function paneDeclProvider(s){
  return paneProvider(s) || SEED.provider;
}
function paneMenuHtml(s){
  if (S.paneMenu !== s.id) return "";
  /* The Claude-only `u = usageActive(S.usage)` binding lived here. Its one
     consumer was the Usage row, which now asks providerUsage() so the row
     matches the provider actually selected. */
  /* `title` is OPTIONAL and only the Folder row passes it. The row shows a
     BASENAME (cwdLabel), which is the right thing to show and the wrong thing
     to have to guess at -- so the absolute path the provider actually receives
     is one hover away. Added as a fourth parameter so every existing
     three-argument call renders byte-identical markup. */
  const row = (key, label, val, title) => `<button class="mrow" type="button" data-mrow="${key}"${
      title ? ` title="${esc(title)}"` : ""}>
      <span class="mk">${label}</span><span class="mv">${val}</span><span class="ma">›</span></button>`;
  /* ── the Model row, built here so the template below stays one line ──
     THIS PANE'S provider, not the globally selected one -- see paneProvider()
     above for why, which is now shared with the Permissions and Turn options
     rows rather than restated here. */
  const mpid = paneProvider(s);
  /* Declaration-gated controls only -- see paneDeclProvider. */
  const dpid = paneDeclProvider(s);
  /* Before /api/settings resolves there is no map at all, and the row must not
     vanish on first paint -- that is what the old `MODELS.length ? ... : [CLI
     default]` fallback was for. An EMPTY map means not-loaded; a loaded map
     that simply has no entry for this provider means the provider genuinely
     declares no models (codex has no model flag), and then there is no picker
     to draw rather than an empty one. */
  const mloaded = !!mpid && Object.keys(MODELS_BY_PROVIDER).length > 0;
  const mlist = mloaded ? (MODELS_BY_PROVIDER[mpid] || [])
                        : [{ id: "", name: "CLI default" }];
  /* The stored default for THIS provider. The old fallback read the single flat
     SETTINGS.model, which was Claude's -- so a DeepSeek pane pre-selected a
     Claude id that could never be sent. */
  const msel = S.model[s.id] ?? (((SETTINGS || {}).model_by_provider || {})[mpid] || "");
  /* selectable:false is CATALOGUED BUT NOT RUNNABLE HERE -- the vision model,
     which this panel has no image channel to feed. Listed so its existence is
     not hidden, disabled so it cannot be picked, reason on the option itself.
     The server refuses it too (providers.clean_model gates on the selectable
     set), so this is the visible face of a real refusal, not the only thing
     standing in the way. */
  const mopts = mlist.map(m=>{ const off = m.selectable === false; return `
          <option value="${esc(m.id)}"${off?" disabled":""}${!off && msel === m.id ? " selected":""}
            title="${esc(off ? (m.unavailable_reason || "not available") : (m.note || ""))}"
          >${esc(m.name)}${off?" — unavailable":""}</option>`; }).join("");
  /* role="group", not "menu": the rows are buttons and <label>s, not menuitems,
     and a menu role promises arrow-key navigation this popover does not have
     (refuter 2026-08-23). A labelled group is honest and valid. */
  return `<div class="upop panemenu" id="panemenu-${esc(s.id)}" role="group" aria-label="Chat options — ${esc(s.title)}">
    ${row("folder", "Folder", esc(cwdLabel(sessCwd(s.id))) + (()=>{
        /* the repo bar's facts, one click away instead of always on screen */
        const r = S.repo && S.repo[s.id]; if (!r || !r.available) return "";
        const d = r.diff || {};
        /* THE BRANCH IS LABELLED AS A BRANCH (2026-09-08). This row rendered
           `<folder> · <branch> · clean`, and on a checkout whose branch is
           named after a provider it read as provider context: the founder saw
           "sutra-ui · deepseek-provider" on a CODEX pane and reasonably asked
           whether Codex was being routed through DeepSeek. It was not -- the
           folder and the branch were both correct, and `deepseek-provider` is
           simply the git branch this checkout sits on.

           Presentation only. The path, the branch and the diff are the same
           three facts from the same source; `on` is what stops the middle one
           being read as something other than a branch. `git:` was the
           alternative and was rejected as jargon for the audience this row is
           written for. */
        return ` · on ${esc(r.detached ? "a detached HEAD" : (r.branch || "—"))} · ${(d.files||0) > 0 ? `+${d.added||0} −${d.removed||0}` : "clean"}`;
      })(),
      /* The absolute path this pane's assistant is actually given -- the same
         string that reaches `-C` on a Codex spawn and `cwd=` on every spawn.
         The row can only show a basename; this is where the whole answer
         lives, so "which folder is this really?" never needs a guess. */
      (sessCwd(s.id) || "no folder") + "\nthe working directory "
        + (providerLabel(paneProvider(s)) || "this assistant") + " is given")}
    ${(()=>{ const r = S.repo && S.repo[s.id]; if (!r || !r.available || !r.remote) return "";
        const prs = S.prs && S.prs[s.id]; const n = prs && prs.available ? (prs.pulls||[]).length : null;
        return row("prs", "Pull requests", n != null ? `${n} open` : "on " + esc(r.remote))
             + (r.detached ? "" : row("pr", "Create PR", "propose — nothing is pushed until you approve"));
      })()}
    ${(()=>{ /* ── Chat AI Provider ─────────────────────────────────────────
         THIS CHAT ONLY. Settings' Primary Provider still governs new chats and
         every chat that never asked for anything else; nothing in this row
         touches it (see switchChatProvider, which is what the handler calls).

         NO STATE OF ITS OWN. The selection is `mpid` — paneProvider, the same
         expression the Model, Permissions, Turn options and Usage rows read —
         so the row cannot disagree with what the chat is about to run, and a
         "using Codex, ..." typed in the composer shows up here without this
         control being told about it. It sits FIRST because the four rows below
         it are all answers about the provider it names.

         ONLY READY-TO-USE PROVIDERS ARE OFFERED. `runnable` is the server's own
         verdict on the /api/providers row (installed AND configured AND this
         build has an adapter); offering a name that cannot start is the exact
         failure providers.py was written to prevent.

         Two omissions, both for the same reason the Model row has its own: an
         EMPTY provider table means NOT FETCHED, never "nothing is ready", so a
         row built from it would offer nothing at all; and with no `mpid` there
         is no honest answer to which provider this chat is on, and a select
         renders its first option when nothing matches — inventing one. */
       const usable = (PROVIDERS || []).filter(p => p.runnable);
       if (!usable.length || !mpid) return "";
       /* RUNNING, BUT NO LONGER READY. A provider can be signed out or
          uninstalled after the socket resolved it. A select whose value is
          absent from its options silently displays the FIRST one, which would
          name a provider this chat is not on — so the current one is listed
          disabled instead, the same way the Model row carries a catalogued
          model it cannot select. */
       const opts = (usable.some(p => p.id === mpid) ? usable
                     : [{ id: mpid, name: providerLabel(mpid), off: true }].concat(usable))
         .map(p => `<option value="${esc(p.id)}"${p.off ? " disabled" : ""}${
              p.id === mpid ? " selected" : ""}>${esc(p.name)}${
              p.off ? " — no longer ready" : ""}</option>`).join("");
       return `<label class="mrow"><span class="mk">Chat AI Provider</span><span class="mv"><select class="provsel" data-chatprov="${esc(s.id)}" aria-label="AI provider for this chat"
            title="This chat only — Settings keeps the default for new chats">${opts}
      </select></span><span class="ma"></span></label>`;
     })()}
    <label class="mrow"><span class="mk">Permissions</span><span class="mv">${permSelect(dpid)}</span><span class="ma"></span></label>
    ${!mlist.length ? "" : `<label class="mrow"><span class="mk">Model</span><span class="mv"><select class="modelsel" data-model="${esc(s.id)}" aria-label="Model for this session"
            title="Model — applies to the next message">${mopts}
      </select></span><span class="ma"></span></label>`}
    ${(()=>{ /* THIS PANE'S provider, same rule as the Model row above. */
       /* `s.id` is new here and only the "tokens" kind reads it -- token counts
          belong to THIS pane's last turn, not to the app. */
       const pu = providerUsage(mpid, s.id);
       /* TOKENS ARE NOT BILLING, and the row label is where that has to be
          said, because "Usage" next to a number reads as spend. codex reports
          no price and no plan allowance (see providers' usage_kind "tokens"),
          so the row is titled for what it holds. Only the tokens kind renames;
          Claude's "Usage" and DeepSeek's "Usage" are untouched. */
       const ulabel = usageKindOf(mpid) === "tokens" ? "Tokens" : "Usage";
       if (pu) return row("usage", ulabel, pu.row);
       /* No figure. THREE different reasons now, and saying the wrong one is
          worse than saying nothing: a provider with no usage concept will
          never have one, a provider not read yet will, and a tokens provider
          simply has not finished a turn in this pane. */
       return row("usage", ulabel, usageKindOf(mpid) === "none"
         ? "not reported for " + (providerLabel(mpid) || mpid || "this assistant")
         : usageKindOf(mpid) === "tokens" ? "after the first reply"
         : "not read yet");
     })()}
    ${/* Omitted entirely for a provider that honours none of them, rather than
          opening onto an empty box -- same rule as the Model row above. On a
          DeepSeek pane every one of the five was collected and discarded: ACP's
          per-turn request has no options field for them to travel in. */
       !turnOptsFor(dpid).size ? "" :
       row("opts", "Turn options", S.optsOpen[s.id] ? "hide effort, budget and tool limits" : "effort, budget and tool limits for the next message")}
    ${row("route", "Routing", (S.sessTab[s.id]||"chat")==="route" ? "back to the chat" : "departments this session touched")}
    ${row("fold", "Fold", "collapse this pane")}
    ${row("close", "Close", "close this session")}
  </div>`;
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
  /* Chrome decisions (founder, 2026-08-18): the header exists only for the
     COLLAPSED strip -- while expanded it is display:none (panel.css), because
     the rail already names the session and the three controls it carried
     (Chat/Routing tabs, Activity, close) moved into the composer's ⋯ menu. The
     <section> names itself, since its only <h3> is hidden while expanded. The
     grip is the expanded pane's fold control; it is NOT rendered while
     collapsed, so a [data-pane-fold] query always resolves to the visible one
     (the strip's own .pfold) -- codex follow-up, 2026-08-21. */
  const live = streamingFor(s.id) || !!s.agents_live;
  const menuOpen = S.paneMenu === s.id;
  return `<section class="pane ${collapsed?"collapsed":""}" data-sess="${s.id}"
      aria-label="${esc(s.title)} — session pane">
    ${collapsed ? "" : `<button class="pgrip" type="button" data-pane-fold="${esc(s.id)}"
            aria-label="Collapse this session pane" title="Collapse this pane">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.2" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>
    </button>`}
    <!-- Header (founder 2026-08-24): ONE title line + ONE subtitle line, both
         single-line ellipsized, full text on hover (title=) and in the
         accessible name. The 45-word summary is the SUBTITLE now, never a
         wrapped paragraph ("too many lines, and I cannot find more lines").
         The department sits beside the live dot — the LATEST FILED turn's
         leaf, honestly labelled as such, absent when nothing was ever filed
         (codex 2026-08-24: last-domain-wins without the label misleads).
         The per-pane "transcript" tag is gone (fork stays). Collapsed, the
         same element is the vertical strip (panel.css), unchanged. -->
    <div class="ph">
      <button class="pfold" type="button" data-pane-fold="${esc(s.id)}"
              aria-expanded="${!collapsed}"
              aria-label="${collapsed?"Expand":"Collapse"} this session pane">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.2" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>
      </button>
      ${(() => {
        const sub = collapsed ? "" : sessSummary(s);
        const dupSub = !sub || sub.replace(/\s+/g, " ").trim() === String(s.title || "").replace(/\s+/g, " ").trim();
        const hover = esc(s.title) + (dupSub ? "" : " — " + esc(sub)) + (s.real && s.cwd ? " · " + esc(s.cwd) : "");
        const dTurn = collapsed ? null : [...(s.turns || [])].reverse().find(t => t && t.domain);
        return `<h3 class="phsum" title="${hover}" aria-label="${esc(s.title)}${dupSub ? "" : ". " + esc(sub)}">${
          collapsed ? esc(s.title)
                    : `<span class="pht">${esc(s.title)}</span>${dupSub ? "" : `<span class="phs">${esc(sub)}</span>`}`
        }</h3>
      ${s.fork?`<span class="src" title="Branched from another session with --fork-session">fork</span>`:""}
      ${dTurn ? `<span class="phdept" title="latest filed: ${esc(dTurn.domain.name)}">${esc(dTurn.domain.name)}</span>` : ""}`;
      })()}
      <span class="dot ${live?"run":""}" ${live ? `role="img" aria-label="a turn is running"` : `aria-hidden="true"`} style="width:6px;height:6px;border-radius:50%;background:var(${live?"--ok":"--line"});flex:none"></span>
      <button class="ib" data-close="${esc(s.id)}" type="button" aria-label="Close session" title="Close this session">
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
    ${switchMarkerHtml(s.id)}
    ${modeMarkerHtml(s.id)}
    ${permConfirmHtml()}
    ${S.optsOpen[s.id] ? turnOptsHtml(s.id, paneDeclProvider(s),
                                  paneModelFor(s, paneDeclProvider(s))) : ""}
    ${cwdEditorHtml(s.id)}
    ${providerSwitcherHtml(s.id)}
    ${prFormHtml(s.id)}
    ${prListHtml(s.id)}
    <div class="pc">
      <!-- Chat-surface chrome (founder, 2026-08-18): the ⋯ chip is the pane's
           identity — the header no longer shows while expanded — and its menu is
           the one home for Folder / Permissions / Model / Usage / Routing /
           Fold / Close. It sits LEFT of attach by direction. -->
      <!-- ⋯ ONLY (founder 2026-08-23): the header carries the identity now, and
           the dirty-tree fact lives in the menu's Folder row. The name a screen
           reader hears is the accessible label, not the glyph (codex P2). -->
      <button class="uchip" type="button" data-panemenu="${esc(s.id)}"
              aria-expanded="${S.paneMenu===s.id?"true":"false"}" aria-haspopup="true"${
              S.paneMenu===s.id ? ` aria-controls="panemenu-${esc(s.id)}"` : ""}
              aria-label="Chat options — ${esc(s.title)}"
              title="Everything about this chat — folder, permissions, model, usage, routing, turn options">
        <span aria-hidden="true">⋯</span>
      </button>
      <button class="ib" data-attach="${s.id}" type="button"
              aria-label="Attach a file" title="Attach a file (or drop / paste one)">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.9" aria-hidden="true"><path d="M21 11l-8.5 8.5a4.6 4.6 0 01-6.5-6.5L14 4.5a3 3 0 014.3 4.3l-8.5 8.5a1.5 1.5 0 01-2.1-2.1l7.9-7.9"/></svg>
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
      <!-- A TEXTAREA, not <input type="text">. An input cannot hold a newline at
           any price, so Shift+Enter, Ctrl+J and pasted multi-line text were not
           "unimplemented" -- they were impossible. rows=1 keeps it looking like a
           single line until there is a reason not to; autoGrowComposer() sizes it.
           Placeholder is ONE WORD (founder, 2026-08-18): the / palette and
           Shift+Enter are learned by use. -->
      <!-- no placeholder at all (founder 2026-08-23): the bar is self-evident -->
      <textarea data-sask="${s.id}" rows="1"
             aria-label="Continue this session">${esc(S.composerText[s.id]||"")}</textarea>
      ${paneMenuHtml(s)}
      ${S.usagePop === s.id ? usagePopHtml() : ""}
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
/* Which of the five this PANE'S provider can honour, as a Set.
   Not-loaded (empty map) => all of them, so the first paint is what it always
   was; a loaded map with no entry for this provider => none, and the caller
   omits the whole block rather than opening an empty one. */
function turnOptsFor(mpid){
  const loaded = Object.keys(TURN_OPTIONS_BY_PROVIDER).length > 0;
  if (!loaded) return new Set(TOPT_ALL);
  return new Set(TURN_OPTIONS_BY_PROVIDER[mpid] || []);
}
/* THE BOOT-WINDOW FALLBACK, and Codex's two keys are deliberately NOT in it.
   turnOptsFor() answers with this whole set before /api/providers has landed,
   so adding them here would draw Reasoning and Verbosity on a CLAUDE pane for
   the first second of every launch -- the same class of false-specific claim
   the Usage row's not-loaded branch is logged for. Left as Claude's five, so
   nothing renders until a provider actually declares it. */
const TOPT_ALL = ["effort", "max_budget_usd", "allowed_tools",
                  "disallowed_tools", "append_system_prompt"];

/* Codex's own enumerations, mirrored from providers.CODEX_REASONING_SUMMARY and
   providers.CODEX_VERBOSITY. Duplicated rather than fetched because they are
   the CLI's fixed vocabulary, not machine state -- and the server validates
   every value again in codex_turn_config, so a drift here cannot put an
   unrecognised value on the wire. "" is first: it is the default. */
const CODEX_SUMMARY_OPTS = ["", "auto", "concise", "detailed", "none"];
const CODEX_VERBOSITY_OPTS = ["", "low", "medium", "high"];

/* The reasoning EFFORTS the selected model supports. There is deliberately no
   constant beside the two above, because this set is PER MODEL and discovered:
   measured on one account, terra offers `ultra`, luna does not, and 5.5 stops
   at `xhigh`. A fixed list would offer every model the union, and codex takes
   an unsupported value SILENTLY -- so the turn would quietly run at something
   other than what the control said.

   A falsy `model` is the "CLI default" row, which resolves to whatever codex
   marked isDefault -- so its efforts are that model's. providers.
   codex_efforts_for() resolves None the same way server-side, which is what
   stops this offering a value the validator would then drop.

   [] whenever discovery has not run or the model is unknown, and the caller
   renders "default" alone -- the behaviour that existed before this control. */
function codexEffortsFor(mpid, model){
  const list = (MODELS_BY_PROVIDER || {})[mpid] || [];
  const pick = model ? list.find(m => m && m.id === model)
                     : list.find(m => m && m.default);
  return (pick && Array.isArray(pick.efforts)) ? pick.efforts : [];
}

/* This pane's selected model id. Mirrors the resolution paneMenuHtml uses for
   its own picker, but takes `mpid` explicitly rather than recomputing it: the
   two call sites resolve the provider differently (paneProvider there,
   paneDeclProvider here), so sharing that half would change which provider one
   of them asks about. */
function paneModelFor(s, mpid){
  return S.model[s.id] ?? (((SETTINGS || {}).model_by_provider || {})[mpid] || "");
}
function turnOptsHtml(sid, mpid, model){
  const o = S.turnOpts[sid] || {};
  const on = turnOptsFor(mpid);
  /* Each field is emitted only if this provider can act on it. A field that is
     collected and then discarded server-side is the model-dropdown bug in a
     different control: it reads as a setting that took effect. */
  const f = (key, html) => on.has(key) ? html : "";
  return `<div class="topts">
    ${f("effort", `<label><span>Effort</span>
      <select data-opt="effort" data-sid="${sid}">
        ${EFFORTS.map(e=>`<option value="${e}" ${o.effort===e?"selected":""}>${
          e||"default"}</option>`).join("")}
      </select></label>`)}
    ${f("max_budget_usd", `<label><span>Budget</span>
      <input type="number" step="0.5" min="0" placeholder="no cap"
             data-opt="max_budget_usd" data-sid="${sid}"
             value="${o.max_budget_usd!=null?esc(String(o.max_budget_usd)):""}"
             title="--max-budget-usd: stop the turn once it has cost this much"/></label>`)}
    ${f("allowed_tools", `<label class="wide"><span>Allow only</span>
      <input type="text" placeholder="Read Bash Grep — blank means every tool"
             data-opt="allowed_tools" data-sid="${sid}"
             value="${esc((o.allowed_tools||[]).join(" "))}"
             title="--allowedTools: whitespace separated"/></label>`)}
    ${f("disallowed_tools", `<label class="wide"><span>Never</span>
      <input type="text" placeholder="WebFetch Write"
             data-opt="disallowed_tools" data-sid="${sid}"
             value="${esc((o.disallowed_tools||[]).join(" "))}"
             title="--disallowedTools: whitespace separated"/></label>`)}
    ${f("append_system_prompt", `<label class="wide"><span>Extra instructions</span>
      <input type="text" placeholder="appended to the system prompt for this turn"
             data-opt="append_system_prompt" data-sid="${sid}"
             value="${esc(o.append_system_prompt||"")}"/></label>`)}
    ${/* CODEX'S TWO, and they are here rather than in a Codex-only box because
          this function is already the provider-gated place: `f()` emits a field
          only if the provider DECLARES it, so Claude and DeepSeek -- which
          declare neither -- render exactly the markup they rendered before.

          Both values come from codex's OWN enumeration, read out of the CLI's
          rejection of a bad one (providers.CODEX_REASONING_SUMMARY /
          CODEX_VERBOSITY). Nothing here is a Sutra invention, and the empty
          option is a real choice meaning "leave it to codex" -- it emits no
          -c at all. `model_reasoning_effort` is deliberately absent: it is a
          real key whose values codex does not enumerate, so a picker for it
          would be guesses. */""}
    ${/* "Reasoning summary", not "Reasoning" (2026-09-09). The key is
          model_reasoning_summary, which controls how much of its reasoning
          Codex SHOWS -- not how much it DOES. Codex exposes both axes and they
          share no values: summary is auto/concise/detailed/none, effort is
          low/medium/high/xhigh/max/ultra (per model, off model/list). A control
          labelled "Reasoning" offering `none` reads as "turn reasoning off",
          and selecting it leaves the effort at the model's own default and
          merely hides the summary. The tooltip already said so; the label is
          what gets read. */""}
    ${f("reasoning_summary", `<label><span>Reasoning summary</span>
      <select data-opt="reasoning_summary" data-sid="${sid}"
              title="model_reasoning_summary — how much of its reasoning Codex shows">
        ${CODEX_SUMMARY_OPTS.map(v=>`<option value="${v}" ${
          o.reasoning_summary===v?"selected":""}>${v||"default"}</option>`).join("")}
      </select></label>`)}
    ${/* REASONING EFFORT -- how much reasoning codex DOES, the other axis from
          the summary control above (which is how much it SHOWS). They share no
          values and both are codex's own.

          THE OPTIONS ARE THE SELECTED MODEL'S, not a constant: the sets differ
          per model and codex accepts an unsupported value silently, so a fixed
          list would let a turn quietly run at something else. "default" is
          always present and always first -- it emits no override at all, which
          is also the whole control when discovery has produced nothing. */""}
    ${f("reasoning_effort", `<label><span>Reasoning effort</span>
      <select data-opt="reasoning_effort" data-sid="${sid}"
              title="model_reasoning_effort — how much reasoning Codex does">
        ${[""].concat(codexEffortsFor(mpid, model)).map(v=>`<option value="${esc(v)}" ${
          o.reasoning_effort===v?"selected":""}>${v||"default"}</option>`).join("")}
      </select></label>`)}
    ${f("verbosity", `<label><span>Verbosity</span>
      <select data-opt="verbosity" data-sid="${sid}"
              title="model_verbosity — how long Codex's answers run">
        ${CODEX_VERBOSITY_OPTS.map(v=>`<option value="${v}" ${
          o.verbosity===v?"selected":""}>${v||"default"}</option>`).join("")}
      </select></label>`)}
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
                      "data-prf", "data-edta", "data-workdir-input", "data-edfilter",
                      "data-wssearch", "data-gitfilter"]) {
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

/* (r5) the Knowledge-screen search (runSearch/S.sq) is gone — workspace
   search is the one search surface. */

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
    /* Attach mode on a sidecar-capable shell: the SHELL's manifest is the
       truth -- the backend serving this page cannot know about shell-side
       staging. Feature-detected; a failed shell call renders as nothing
       staged, never as optimistic HTTP state from the wrong server. */
    if (window.sutra && typeof window.sutra.updateState === "function") {
      const s = await window.sutra.updateState();
      if (s && s.attach) {
        S.updStaged = (s.capable && s.staged)
          ? { pending: true, state: s.armed ? "installing" : "staged", version: s.staged_version }
          : { pending: false };
        renderUpdateBanner();
        return;
      }
    }
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
  /* "Not now" must actually dismiss. Deferring used to swap the countdown for
     a message with NO buttons, so the banner became permanent -- an update the
     operator explicitly postponed then sat on screen until the app quit.
     Dismissal is keyed to the VERSION, so a genuinely newer build still gets
     to announce itself. An error or an in-flight install always shows: those
     are not states the operator asked to stop hearing about. */
  const dismissed = !!(u && u.version && S.updDismissed === u.version
                       && !S.updApplyError && u.state !== "installing");
  const show = !!(u && u.pending) && !dismissed;
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
    /* "Not now" is a DEFER: the staged build is kept and the shell applies it
       on the way out. It is also a DISMISSAL -- the banner goes away. Saying
       "not now" and being answered with a permanent notice is not a defer, it
       is a nag, and Settings -> Updates already carries the same fact for
       anyone who wants it. */
    S.updDeferred = true;
    S.updDismissed = (S.updStaged && S.updStaged.version) || null;
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

function invalidatePanesHtml(){
  const p = document.getElementById("panes");
  if (p) p.__lastPanesHtml = null;
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

  document.getElementById("app").classList.toggle("railcol", !!S.ui.navCollapsed);

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
  /* The browse pane closes like a session pane closes: it is a VIEW, and the
     rail keeps every way back to it. Closed emits no section at all -- a hidden
     pane would still own #scBody and every handler wired into it. Picking any
     Home item reopens it (07-loaders' data-screen handler). */
  const bClosed = !!S.ui.browseClosed;
  /* r8: the same unchanged-HTML skip #143 gave #scBody, for the WHOLE panes
     row — idle websocket frames stop killing hover states and swapping
     buttons mid-click. Streaming panes change the string every frame, so
     live repaints continue. Direct-DOM patches inside #panes must call
     invalidatePanesHtml() (wsRenderSideOnly / save-chip swap / divider). */
  const panesEl = document.getElementById("panes");
  const panesHtml =
    (bClosed ? "" :
    `<section class="pane browse ${bCol?"collapsed":""}"${bStyle}>
       <div class="ph">
         <button class="pfold" type="button" data-pane-fold="browse"
                 aria-expanded="${!bCol}"
                 aria-label="${bCol?"Expand":"Collapse"} the browse pane">
           <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                stroke-width="2.2" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>
         </button>
         <h3 style="max-width:none">${esc(t)}</h3>
         ${S.screen === "workspace" && typeof wsPaneHeadHtml === "function" ? wsPaneHeadHtml() : ""}
         <button class="ib" data-close="browse" style="margin-left:auto"
                 aria-label="Close this pane">
           <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
         </button>
         </div>
       <div class="pb" id="scBody"></div>
     </section>`
    + (open.length && !bCol
        ? `<button class="pdiv" id="pdiv" type="button" role="separator"
             aria-orientation="vertical" aria-label="Resize the browse pane
             (left and right arrows adjust, home resets)"></button>` : ""))
    + open.map(sessionPane).join("")
    + (bClosed && !open.length
        ? `<p style="padding:24px 28px;font-size:12px;color:var(--faint)">
             Nothing is open. Pick a screen from Home, or a session from Code.</p>` : "");
  if (panesEl && panesEl.__lastPanesHtml !== panesHtml){
    panesEl.__lastPanesHtml = panesHtml;
    panesEl.innerHTML = panesHtml;
  }
  const scBody = document.getElementById("scBody");
  if (scBody){
    /* founder's "it stops working there" root cause (2026-08-26): every
       websocket frame renders, and an unconditional innerHTML rebuild
       replaces the screen's buttons between mousedown and mouseup. Only
       rebuild when the markup actually changed. */
    const html = SCREENS[S.screen]();
    if (scBody.__lastScreenHtml !== html){
      /* the founder may be typing INTO this screen right now (a live
         session update re-renders it under them) -- carry the cursor,
         the draft and the caret across the rebuild */
      const act = document.activeElement;
      const keep = (act && scBody.contains(act)
        && (act.tagName === "TEXTAREA" || act.tagName === "INPUT"))
        ? { sel: act.dataset && act.dataset.shhomecompose
              ? "[data-shhomecompose]"
              : (act.dataset && act.dataset.shcompose
                 ? "[data-shcompose]" : null),
            value: act.value,
            start: act.selectionStart, end: act.selectionEnd }
        : null;
      scBody.__lastScreenHtml = html;
      scBody.innerHTML = html;
      if (keep && keep.sel){
        const el = scBody.querySelector(keep.sel);
        if (el){
          if (keep.value) el.value = keep.value;
          try { el.focus({ preventScroll: true });
            el.setSelectionRange(keep.start, keep.end); } catch (e) {}
        }
      }
    }
  }
  /* the shadow home is two columns; widen ONLY its pane (explicit class,
     not :has -- deepseek fold 2026-08-26). Self-cleaning on screen change. */
  if (scBody && scBody.closest){
    const bp = scBody.closest(".pane");
    if (bp && bp.classList){
      /* review fold: a COLLAPSED browse pane keeps its 38px rail -- never
         re-inflate it (inline flex beat .collapsed once before; documented
         above the bStyle computation) */
      const wide = S.screen === "shadow" && !bCol;
      bp.classList.toggle("shwide", wide);
      /* the pane carries a saved inline flex-basis that beats any class;
         the render rebuilds it fresh each pass, so setting inline here is
         authoritative for THIS paint only (learned live 2026-08-26) */
      if (wide && bp.style) bp.style.flex = "0 0 720px";
      /* Agents (2.239.0) carries three columns of its own -- agent, conversation,
         review panel -- so it takes the row the way a session pane would. Measured
         at 385px beside an open chat before this: the composer was four words wide.
         The class also drops the pane's padding (agents.css). */
      const agw = S.screen === "agents" && !bCol;
      bp.classList.toggle("agwide", agw);
      if (agw && bp.style) bp.style.flex = "1 1 100%";
    }
  }
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
/* The workspace screen never scrolls .pb (.ws exactly fills it) — its real
   scrollers are the tree column and the doc column, reborn at scrollTop 0 on
   every innerHTML rebuild. Saving them here is what stops the left tree from
   snapping to the top on every SSE-driven repaint (founder glitch report
   2026-08-25; dual consult — the full rebuild itself is a logged follow-up). */
function _wsScrollers(){
  if (S.screen !== "workspace") return [];
  return [
    ["wsSide", document.querySelector("#scBody .ws-side")],
    ["wsDoc",  document.querySelector("#scBody .ws-doccol")],
  ].filter(p => p[1]);
}
function _browseScrollState(){
  const el = _browseScroller();
  const st = { key: _browseScrollKey(), top: (el && el.scrollTop) || 0 };
  _wsScrollers().forEach(([id, sc]) => { if (sc.scrollTop) st[id] = sc.scrollTop; });
  if (!st.top && st.wsSide == null && st.wsDoc == null) return null;
  return st;
}
function _restoreBrowseScroll(prior){
  if (!prior || prior.key !== _browseScrollKey()) return;
  const el = _browseScroller();
  if (el && prior.top) el.scrollTop = prior.top;
  _wsScrollers().forEach(([id, sc]) => { if (prior[id] != null) sc.scrollTop = prior[id]; });
  /* Re-apply once after layout. The synchronous set above is enough whenever
     the new content is at least as tall as the old, which is the common case;
     it silently clamps to a shorter document (a filter that removed rows), and
     a rAF pass lands the honest maximum instead of leaving it at 0. */
  requestAnimationFrame(()=>{
    if (prior.key !== _browseScrollKey()) return;
    const e2 = _browseScroller();
    if (e2 && prior.top && e2.scrollTop !== prior.top) {
      e2.scrollTop = Math.min(prior.top, Math.max(0, e2.scrollHeight - e2.clientHeight));
    }
    _wsScrollers().forEach(([id, sc]) => {
      if (prior[id] != null && sc.scrollTop !== prior[id]) {
        sc.scrollTop = Math.min(prior[id], Math.max(0, sc.scrollHeight - sc.clientHeight));
      }
    });
  });
}
/* A transcript is a LOG: the interesting end is the newest turn. Opening a
   60-turn session at turn 1 makes the operator scroll to find what just
   happened. Scroll once per pane-open, then leave the scroll position alone so
   a re-render (a streaming token, a sim result) never yanks the view back. */
/* One pin timer per session, surviving the #panes rebuild that orphans any
   flag stored on the element itself. */
const _pinTimers = new Map();

function _sessionIsStreaming(sid){
  const s = (S.sessions || []).find(x => x.id === sid);
  if (s && (s.turns || []).some(t => t.streaming)) return true;
  return ((S.sideTurns || {})[sid] || []).some(t => t.streaming);
}

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
      if (!pb) return;
      /* Keyed by SESSION, not stashed on the element. The old guard was
         `if (pb.__pinTimer) return`, but render() replaces #panes wholesale --
         so every .pb is a brand-new node with no flag, and a fresh 100ms
         interval was created on EVERY render(). A turn with several structural
         frames left overlapping 4s timers all writing scrollTop, while
         patchStreaming was also pinning on rAF. Two writers at different
         cadences on one element is visible micro-jitter, and a real scroll
         gesture landing between them could be swallowed. */
      const prev = _pinTimers.get(sid);
      if (prev) clearInterval(prev);
      let lastH = -1, stable = 0, ticks = 0;
      const timer = setInterval(()=>{
        ticks++;
        const done = () => { clearInterval(timer); if (_pinTimers.get(sid) === timer) _pinTimers.delete(sid); };
        if (S.userScrolled.get(sid) || ticks > 40) return done();   // 4s ceiling
        /* While a reply is streaming, patchStreaming() owns the pin. This timer
           exists to settle the view after a RENDER, and running both makes them
           fight. Yield rather than stop: the stream will end and the tail may
           still need settling. */
        if (_sessionIsStreaming(sid)) return;
        const h = pb.scrollHeight;
        if (h <= pb.clientHeight + 1) return;                       // nothing yet
        if (h === lastH){ if (++stable >= 3) done(); return; }       // settled
        lastH = h; stable = 0;
        pb.__pinning = true;
        pb.scrollTop = h;                                            // newest turn is last
        /* rAF, not setTimeout(0), so the release lands on the same boundary
           patchStreaming uses -- the scroll listener reads one convention. */
        requestAnimationFrame(()=>{ pb.__pinning = false; });
      }, 100);
      _pinTimers.set(sid, timer);
    });
  });
}

