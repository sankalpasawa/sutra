/* Run whatever render() was deferred during a drag. Called from dragend and
   from every early-return path in ondrop, so a deferred render can never be
   stranded. */
function flushRender(){ if (S.renderDirty) render(); }

/* Drag the browse/session divider. The drag writes the width straight onto the
   element instead of re-rendering per mousemove -- a full innerHTML rebuild at
   60Hz would tear down the very button being dragged. State is persisted once,
   on mouseup. Arrow keys do the same thing for keyboard users; Home clears the
   override and returns the pane to its default flex ratio. */
function wireDivider(){
  const d = document.getElementById("pdiv");
  if (!d) return;
  const panes = document.getElementById("panes");
  const browse = panes.querySelector(".pane.browse");
  if (!browse) return;
  const apply = w => { S.ui.browseW = Math.round(w);
    browse.style.flex = "0 0 " + Math.round(w) + "px"; browse.style.maxWidth = "none"; };
  /* The SAME ceiling render() applies to a restored width -- a drag must not
     be able to reach a width the next reload would clamp away. */
  const limit = browseMax;
  d.onmousedown = e => {
    e.preventDefault();
    d.classList.add("dragging");
    const startX = e.clientX, startW = browse.getBoundingClientRect().width;
    const move = ev => apply(Math.max(BROWSE_MIN, Math.min(limit(), startW + (ev.clientX - startX))));
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      d.classList.remove("dragging");
      saveLayout();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  };
  d.onkeydown = e => {
    const cur = S.ui.browseW || browse.getBoundingClientRect().width;
    if (e.key === "ArrowLeft"){ e.preventDefault(); apply(Math.max(BROWSE_MIN, cur - 24)); saveLayout(); }
    else if (e.key === "ArrowRight"){ e.preventDefault(); apply(Math.min(limit(), cur + 24)); saveLayout(); }
    else if (e.key === "Home"){ e.preventDefault(); S.ui.browseW = null; saveLayout(); render(); }
  };
}

function wire(){
  /* With the browse pane closed there is no #scBody. A detached node keeps
     every scBody.querySelectorAll below a no-op instead of a TypeError that
     would kill wire() before the session panes got their handlers. */
  const scBody = document.getElementById("scBody") || document.createElement("div");
  const panes  = document.getElementById("panes");

  /* ── layout affordances (collapse, fold, resize) ── */
  panes.querySelectorAll("[data-pane-fold]").forEach(b=>b.onclick=()=>{
    const id = b.dataset.paneFold;
    if (S.ui.paneCollapsed[id]) delete S.ui.paneCollapsed[id];
    else S.ui.paneCollapsed[id] = true;
    saveLayout(); render(); });
  scBody.querySelectorAll("[data-fold]").forEach(b=>b.onclick=()=>{
    /* read the state off the button rather than recomputing the default -- some
       folds ship closed (an empty provider group) and a hardcoded default here
       would invert their first click */
    S.ui.folds[b.dataset.fold] = b.getAttribute("aria-expanded") === "true" ? 0 : 1;
    saveLayout(); render(); });
  wireDivider();

  /* ── settings: every control posts, and reports the server's refusal ── */
  /* ── updates ── */
  scBody.querySelectorAll("[data-upd]").forEach(b=>b.onclick=()=>{
    const what = b.dataset.upd;
    if (what === "check") checkUpdates(); else installUpdate(what);
  });

  scBody.querySelectorAll("[data-prov]").forEach(b=>b.onclick=()=>{
    if (b.disabled) return;                       /* not runnable -- the reason is on screen */
    S.setBusy = "prov:" + b.dataset.prov; S.setError = null; S.setOk = null; render();
    apiPost("/api/providers/active", { id: b.dataset.prov })
      .then(r=>{ PROVIDERS = r.providers || PROVIDERS;
                 SETTINGS = r.settings || SETTINGS;
                 S.setOk = "active provider is now " + r.active + "."; })
      .catch(e=>{ S.setError = e.message; })
      .then(()=>{ S.setBusy = null; render(); }); });
  scBody.querySelectorAll("[data-pmode-set]").forEach(b=>b.onclick=()=>{
    const m = b.dataset.pmodeSet;
    const spec = PERM_MODES.find(x=>x.id===m) || {};
    /* A gated mode is refused server-side with a 400. Firing the request anyway
       turned "this is locked" into "settings are broken"; say which it is
       without a round-trip. */
    if (spec.settable === false){
      const envName = (SETTINGS||{}).unsafe_modes_env || "SUTRA_UI_ALLOW_UNSAFE_PERM_MODES";
      S.setOk = null;
      S.setError = m + " auto-approves agent actions and is gated. Restart the server with "
                 + envName + "=1 to make it selectable — the gate is out of band on purpose.";
      render(); return;
    }
    /* Unlocked but still dangerous: the second gate is the operator saying yes. */
    if (spec.writes_files && !window.confirm(
        "Switch to " + m + "?\n\n" + (spec.note || "") +
        "\n\nSessions started from this panel will act under that authority until you change it back.")){
      return;
    }
    S.setBusy = "mode:" + m; S.setError = null; S.setOk = null; render();
    apiPost("/api/settings", { permission_mode: m })
      .then(r=>{ SETTINGS = r.settings || SETTINGS;
                 /* Report what will RUN, not what was written — they differ when clamped. */
                 S.setOk = "permission mode is now "
                         + ((SETTINGS||{}).permission_mode_effective || (SETTINGS||{}).permission_mode) + "."; })
      .catch(e=>{ S.setError = e.message; })
      .then(()=>{ S.setBusy = null; render(); }); });

  /* ── editor ── */
  scBody.querySelectorAll("[data-edopen]").forEach(b=>b.onclick=()=>openEdFile(b.dataset.edopen));
  const edFilter = scBody.querySelector("[data-edfilter]");
  if (edFilter) edFilter.oninput = ()=>{ S.fsQuery = edFilter.value; renderFilterOnly(); };
  const edTa = scBody.querySelector("[data-edta]");
  if (edTa){
    /* No render() on input: a full rebuild on every keystroke would fight the caret
       and make typing in a large file unusable. The dirty pill is updated directly. */
    edTa.oninput = ()=>{
      S.edText = edTa.value;
      const pill = scBody.querySelector("[data-edsave]");
      const dirty = S.edText !== S.edBase;
      if (pill) pill.disabled = !dirty || !(S.fs&&S.fs.editable) || S.edBusy;
      const chip = scBody.querySelector(".edbar .pill");
      if (chip){ chip.textContent = dirty ? "unsaved changes" : "saved";
                 chip.className = "pill " + (dirty ? "p-warn" : "p-mut"); }
    };
    edTa.onkeydown = e=>{
      if ((e.metaKey || e.ctrlKey) && e.key === "s"){ e.preventDefault(); saveEdFile(); }
    };
  }
  const edSave = scBody.querySelector("[data-edsave]");
  if (edSave) edSave.onclick = ()=>saveEdFile();
  const edReload = scBody.querySelector("[data-edreload]");
  if (edReload) edReload.onclick = ()=>{ const p=S.edFile; S.edBase=S.edText; openEdFile(p); };

  /* ── git ── */
  scBody.querySelectorAll("[data-gitfile]").forEach(b=>b.onclick=()=>{
    const p = b.dataset.gitfile;
    /* Clicking the selected file again closes the diff rather than re-fetching it. */
    if (S.gitFile === p){ S.gitFile = null; S.gitDiff = null; render(); return; }
    loadGitDiff(p);
  });

  /* ── workdir ── */
  const wdIn = scBody.querySelector("[data-workdir-input]");
  if (wdIn){
    wdIn.oninput = ()=>{ S.workdirDraft = wdIn.value; };   /* no render: it would fight the caret */
    wdIn.onkeydown = e=>{ if (e.key === "Enter"){ e.preventDefault();
      const b = scBody.querySelector("[data-workdir-save]"); if (b) b.click(); } };
  }
  const wdSave = scBody.querySelector("[data-workdir-save]");
  if (wdSave) wdSave.onclick = ()=>{
    const el = scBody.querySelector("[data-workdir-input]");
    const want = (el ? el.value : "").trim();
    if (!want){ S.setError = "a working directory is required"; S.setOk = null; render(); return; }
    S.setBusy = "workdir"; S.setError = null; S.setOk = null; render();
    apiPost("/api/settings", { workdir: want })
      .then(r=>{ SETTINGS = r.settings || SETTINGS;
                 /* Report what the SERVER stored (it expands ~ and resolves symlinks), not what
                    was typed -- they differ, and echoing the input would misreport the result. */
                 S.workdirDraft = null;
                 S.setOk = "sessions will now start in " + ((SETTINGS||{}).workdir || want) + "."; })
      .catch(e=>{ S.setError = e.message; })
      .then(()=>{ S.setBusy = null; render(); }); };

  const ea=scBody.querySelector("[data-expall]");
  if(ea) ea.onclick=()=>{ S.collapsed.clear(); render(); };
  const ca=scBody.querySelector("[data-collall]");
  if(ca) ca.onclick=()=>{ live().forEach(d=>{ if(d.parent_ref) S.collapsed.add(d.ref); }); render(); };

  /* working directory, per session */
  panes.querySelectorAll("[data-cwdopen]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.cwdopen;
    S.cwdEdit = S.cwdEdit === sid ? null : sid;
    S.cwdError = null;
    render();
    /* Focus and put the caret at the END: the field is pre-filled with the current
       path, and selecting it all would make the first keystroke wipe a value the
       operator most likely wants to edit rather than replace. */
    const inp = panes.querySelector('[data-cwdinput="' + sid + '"]');
    if (inp){ inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
  });
  panes.querySelectorAll("[data-cwdsave]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.cwdsave;
    const inp = panes.querySelector('[data-cwdinput="' + sid + '"]');
    setSessCwd(sid, inp ? inp.value : "");
  });
  panes.querySelectorAll("[data-cwdcancel]").forEach(b=>b.onclick=()=>{
    S.cwdEdit = null; S.cwdError = null; render(); });
  /* usage chip + popover */
  panes.querySelectorAll("[data-usagepop]").forEach(b=>{
    const sid = b.closest("[data-sess]") && b.closest("[data-sess]").dataset.sess;
    b.onclick = ()=>{
      const opening = S.usagePop !== sid;
      S.usagePop = opening ? sid : null;
      render();
      /* Refresh ON OPEN rather than on a timer. The number only matters when
         someone is looking at it, and a background poll against an external API
         for a panel nobody has open is cost with no reader. The server's 60s
         cache makes reopening free. */
      if (opening) loadUsage(true);
    };
  });
  panes.querySelectorAll("[data-usageclose]").forEach(b=>b.onclick=()=>{
    S.usagePop = null; render(); });
  /* repository bar */
  panes.querySelectorAll("[data-prstoggle]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.prstoggle;
    const opening = S.prsOpen !== sid;
    S.prsOpen = opening ? sid : null;
    render();
    if (opening) loadPrs(sid, true);
  });
  panes.querySelectorAll("[data-propose-pr]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.proposePr;
    const r = S.repo[sid] || {};
    /* Pre-filled from what the repository already says, not blank: the head is
       the branch you are on and the base is what it tracks, which is right
       almost always -- and both stay editable because "almost" is not "always". */
    S.prForm = { sid,
      head: r.branch || "",
      base: (r.upstream || "").replace(/^origin\//, "") || "main",
      title: "", body: "" };
    S.prError = null; S.prDone = null;
    render();
    const t = panes.querySelector("[data-prf='title']"); if (t) t.focus();
  });
  panes.querySelectorAll("[data-prf]").forEach(inp=>{
    inp.oninput = ()=>{ if (S.prForm) S.prForm[inp.dataset.prf] = inp.value; };
  });
  panes.querySelectorAll("[data-prcancel]").forEach(b=>b.onclick=()=>{
    S.prForm = null; S.prError = null; render(); });
  panes.querySelectorAll("[data-prsubmit]").forEach(b=>b.onclick=async ()=>{
    if (!S.prForm || S.prBusy) return;
    S.prBusy = true; S.prError = null; render();
    try {
      const r = await apiPost("/api/repo/pr-proposal", {
        cwd: sessCwd(S.prForm.sid), head: S.prForm.head, base: S.prForm.base,
        title: S.prForm.title, body: S.prForm.body });
      /* The proposal is INERT. Say so plainly rather than letting a green tick
         imply the pull request exists -- it does not, and will not until it is
         approved under Routines. */
      S.prDone = (r.proposal && r.proposal.id) || "written";
      S.prForm = null;
      loadProposals(true);
    } catch (e){ S.prError = e.message; }
    S.prBusy = false; render();
  });
  panes.querySelectorAll("[data-prdone-dismiss]").forEach(b=>b.onclick=()=>{
    S.prDone = null; render(); });
  panes.querySelectorAll("[data-cwdinput]").forEach(inp=>{
    inp.onkeydown = e=>{
      if (e.key === "Enter"){ e.preventDefault(); setSessCwd(inp.dataset.cwdinput, inp.value); }
      else if (e.key === "Escape"){ e.preventDefault(); S.cwdEdit = null; S.cwdError = null; render(); }
    };
  });
  /* session panes */
  panes.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{
    S.sessTab[b.dataset.sid]=b.dataset.tab; render(); });
  panes.querySelectorAll("[data-agentsfold]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.agentsfold;
    if (S.agentsFold[sid]) delete S.agentsFold[sid];
    else { S.agentsFold[sid] = true; loadAgents(sid, false); }
    render(); });
  panes.querySelectorAll("[data-agentopen]").forEach(b=>b.onclick=()=>{
    /* sid is a claude session id (uuid) and aid is agent-<hex>; neither contains a
       colon, so a single split is unambiguous. */
    const i = b.dataset.agentopen.indexOf(":");
    const sid = b.dataset.agentopen.slice(0, i), aid = b.dataset.agentopen.slice(i + 1);
    if (S.agentOpen[sid] === aid){ delete S.agentOpen[sid]; render(); return; }
    S.agentOpen[sid] = aid; loadAgentTranscript(sid, aid); render(); });
  /* Retry an interrupted turn: same text, same session, new socket. The turn is
     reset rather than duplicated, so the transcript does not grow a copy of a
     message that was never answered. */
  panes.querySelectorAll("[data-retry]").forEach(b=>b.onclick=()=>{
    const uid = b.dataset.retry;
    let sess=null, turn=null;
    S.sessions.forEach(s=>(s.turns||[]).forEach(t=>{ if (t.uid===uid){ sess=s; turn=t; } }));
    Object.keys(S.sideTurns||{}).forEach(sid=>(S.sideTurns[sid]||[]).forEach(t=>{
      if (t.uid===uid){ sess=S.sessions.find(x=>x.id===sid); turn=t; } }));
    if (!sess || !turn) return;
    turn.error = null; turn.interrupted = false; turn.response = "";
    turn.tools = []; turn.toolRuns = [];
    askClaude(sess, turn, !!turn.side);
    render();
  });

  panes.querySelectorAll("[data-close]").forEach(b=>b.onclick=()=>{
    const sid = b.dataset.close;
    /* "browse" is the screens pane, not a session: nothing to hang up, and the
       closed state persists like a pane collapse does. Session ids are UUIDs,
       so the sentinel can never collide with one. */
    if (sid === "browse"){ S.ui.browseClosed = true; saveLayout(); render(); return; }
    /* Returns the channels it KEPT because work was still in flight. Closing the
       pane hides the view; it does not cancel the reply. Say so, because the
       button now does something different from what it used to. */
    const kept = closeClaudeChannel(sid);
    S.openPanes = S.openPanes.filter(id=>id!==sid);
    if (kept.length){
      const s = S.sessions.find(x=>x.id===sid);
      S.toast = "Still running in the background — reopen “" +
                ((s && s.title) || "the session") + "” to watch it finish.";
      setTimeout(()=>{ if (S.toast) { S.toast = null; render(); } }, 6000);
    }
    render(); });
  /* the composer is NOT disabled while a turn runs: the reply streams in, and disabling
     the input mid-stream blurred it and dropped whatever was being typed next */
  panes.querySelectorAll("[data-ssend]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.ssend;
    const inp=panes.querySelector('[data-sask="'+sid+'"]');
    const text=(inp && inp.value.trim())||"";
    const composed=composeWithAttachments(sid, text);
    if(!composed) return;                       /* nothing typed AND nothing attached */
    if(inp) inp.value=""; S.composerText[sid]=""; S.palette=null;
    submitTurn(composed, sid); });

  /* ── side chat ── */
  panes.querySelectorAll("[data-optstoggle]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.optstoggle; S.optsOpen[sid]=!S.optsOpen[sid]; render(); });
  panes.querySelectorAll("[data-opt]").forEach(el=>{
    const sid=el.dataset.sid, key=el.dataset.opt;
    const commit=()=>{
      const o = (S.turnOpts[sid] = S.turnOpts[sid] || {});
      const raw = el.value;
      if (key === "allowed_tools" || key === "disallowed_tools"){
        const list = raw.split(/\s+/).filter(Boolean);
        if (list.length) o[key] = list; else delete o[key];
      } else if (key === "max_budget_usd"){
        const n = parseFloat(raw);
        if (isFinite(n) && n > 0) o[key] = n; else delete o[key];
      } else if (raw && raw.trim()){
        o[key] = raw.trim();
      } else { delete o[key]; }
      /* No render(): re-rendering on every keystroke would tear down the field
         being typed into. The value is already in S. */
    };
    el.oninput = commit; el.onchange = commit;
  });
  panes.querySelectorAll("[data-toolout]").forEach(b=>b.onclick=()=>{
    const id = b.dataset.toolout;
    S.toolOpen[id] = !S.toolOpen[id];
    render();
  });
  /* governance chip fold — same structural-toggle pattern as [data-toolout]:
     flip the S key, full render. Deliberately not the patch path. */
  panes.querySelectorAll("[data-govopen]").forEach(b=>b.onclick=()=>{
    const uid = b.dataset.govopen;
    if (!uid) return;
    S.govOpen = S.govOpen || {};
    S.govOpen[uid] = !S.govOpen[uid];
    render();
  });
  /* "view it in the terminal" for a shell command the agent ran.
     It TYPES the command and stops. It does not press Enter, and that is the whole
     design: the agent ran this once already, a second run is a NEW side effect, and
     `rm`, a migration or a deploy would be re-executed by a control the operator
     clicked to LOOK at something. Typed-not-run is also what term.html's own
     data-insert buttons already do, so this is the established gesture here. */
  panes.querySelectorAll("[data-toolterm]").forEach(b=>b.onclick=()=>{
    const id = b.dataset.toolterm;
    let run = null;
    S.sessions.forEach(s=>(s.turns||[]).forEach(t=>
      (t.toolRuns||[]).forEach(r=>{ if (r.id === id) run = r; })));
    Object.keys(S.sideTurns||{}).forEach(sid=>(S.sideTurns[sid]||[]).forEach(t=>
      (t.toolRuns||[]).forEach(r=>{ if (r.id === id) run = r; })));
    if (!run || !run.command) return;
    sendToTerminal(run.command);
  });
  panes.querySelectorAll("[data-sidetoggle]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sidetoggle;
    S.sideOpen[sid] = !S.sideOpen[sid];
    render();
  });
  panes.querySelectorAll("[data-sideclose]").forEach(b=>b.onclick=()=>{
    /* Closing HIDES it; the turns stay in S.sideTurns so reopening does not lose the
       branch. Discarding an operator's conversation on a close click would be a
       destructive default. */
    S.sideOpen[b.dataset.sideclose] = false; render();
  });
  panes.querySelectorAll("[data-sideask]").forEach(inp=>{
    const sid = inp.dataset.sideask;
    inp.oninput = ()=>{ S.sideText[sid] = inp.value; };
    inp.onkeydown = e=>{
      if (e.key === "Enter" && inp.value.trim()){
        e.preventDefault(); const t = inp.value.trim(); inp.value = ""; askSide(sid, t); }
    };
  });
  panes.querySelectorAll("[data-sidesend]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sidesend;
    const inp=panes.querySelector('[data-sideask="'+sid+'"]');
    if (inp && inp.value.trim()){ const t=inp.value.trim(); inp.value=""; askSide(sid, t); }
  });

  /* ── stop ── */
  panes.querySelectorAll("[data-sstop]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sstop;
    const ch=CLAUDE_SOCKETS.get(sid);
    if(!ch || !ch.open){
      /* No live socket = nothing to interrupt. Say so rather than leaving a button
         that silently does nothing. */
      const s=S.sessions.find(x=>x.id===sid);
      const t=s && (s.turns||[]).slice().reverse().find(x=>x.streaming);
      if(t){ t.streaming=false; t.stopped=true; render(); }
      return;
    }
    ch.ws.send(JSON.stringify({type:"stop"}));
  });

  /* The side chat had NO stop anywhere: the main composer's Stop resolves
     CLAUDE_SOCKETS.get(sid) -- the MAIN key -- while a side turn lives under
     chanKey(sid,true). Kept as a SEPARATE control so stopping one never kills the
     other. */
  panes.querySelectorAll("[data-sidestop]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sidestop;
    const ch=CLAUDE_SOCKETS.get(chanKey(sid, true));
    if(!ch || !ch.open){
      const t=(S.sideTurns[sid]||[]).slice().reverse().find(x=>x.streaming);
      if(t){ t.streaming=false; t.stopped=true; render(); }
      return;
    }
    ch.ws.send(JSON.stringify({type:"stop"}));
  });

  /* ── routines ── */
  scBody.querySelectorAll("[data-prok]").forEach(b=>b.onclick=()=>
    decideProposal(b.dataset.prok, true));
  scBody.querySelectorAll("[data-prno]").forEach(b=>b.onclick=()=>
    decideProposal(b.dataset.prno, false));

  scBody.querySelectorAll("[data-rtnew]").forEach(b=>b.onclick=()=>{
    S.rtForm = {preset:"daily", hour:9, minute:0, weekday:1, model:"",
                permission_mode:(S.rt&&S.rt.permission_modes||["dontAsk"])[0],
                max_budget_usd:1, cwd:((SETTINGS||{}).workdir)||""};
    S.rtError = null; render();
  });
  scBody.querySelectorAll("[data-rtcancel]").forEach(b=>b.onclick=()=>{
    S.rtForm = null; S.rtError = null; render(); });
  scBody.querySelectorAll("[data-rtreload]").forEach(b=>b.onclick=()=>loadRoutines(true));
  scBody.querySelectorAll("[data-rtfix]").forEach(b=>b.onclick=()=>
    rtAction("/reconcile", {fix:true}, "Removed the leftover jobs."));

  /* Field edits are held in S.rtForm, not read off the DOM at submit: render()
     rebuilds the screen whenever the preset changes, and anything only in the
     DOM would be lost at that moment. */
  scBody.querySelectorAll("[data-rtf]").forEach(el=>{
    const k = el.dataset.rtf;
    const commit = ()=>{ if (!S.rtForm) return; S.rtForm[k] = el.value; };
    el.oninput = commit;
    /* A select changes the SHAPE of the form (a weekly needs a day picker), so it
       must re-render; a text input must not, or the caret jumps on every key. */
    if (el.tagName === "SELECT") el.onchange = ()=>{ commit(); render(); };
  });

  scBody.querySelectorAll("[data-rtsave]").forEach(b=>b.onclick=async ()=>{
    const f = S.rtForm || {};
    const body = {
      id:(f.id||"").trim().toLowerCase(), description:f.description, prompt:f.prompt,
      cwd:f.cwd, model:f.model||"", permission_mode:f.permission_mode,
      opts:{ max_budget_usd:Number(f.max_budget_usd)||0 },
      schedule:{ preset:f.preset, hour:Number(f.hour)||0, minute:Number(f.minute)||0,
                 weekday:Number(f.weekday)||0, cron:f.cron },
      enabled:true };
    S.rtBusy = "create"; S.rtError = null; S.rtMsg = null; render();
    try {
      const r = await apiPost("/api/routines", body);
      S.rtForm = null;
      S.rtMsg = (r.launchd && r.launchd.ok)
        ? "Created and scheduled. It has never run — use Run now to check it works."
        : "Created, but launchd refused to load it: " + ((r.launchd||{}).stderr||"no reason given");
      await loadRoutines(true);
    } catch (e) { S.rtError = e.message; }
    S.rtBusy = null; render();
  });

  scBody.querySelectorAll("[data-rtrun]").forEach(b=>b.onclick=()=>
    rtAction("/" + b.dataset.rtrun + "/run", {confirm:true}));
  scBody.querySelectorAll("[data-rttoggle]").forEach(b=>b.onclick=()=>
    rtAction("/" + b.dataset.rttoggle, {enabled: b.dataset.en === "1"},
             b.dataset.en === "1" ? "Resumed." : "Paused — it will not fire on its own."));
  scBody.querySelectorAll("[data-rtruns]").forEach(b=>b.onclick=()=>
    rtLoadRuns(b.dataset.rtruns));
  /* Open a run as a thread. Keyboard too: the row is the control, and a table
     row that only answers to a mouse is a control half the users cannot reach. */
  const openRun = el => {
    const rid = el.dataset.runopen, name = el.dataset.runname;
    if (!rid || !name) return;
    if (S.runOpen && S.runOpen.rid===rid && S.runOpen.name===name){
      S.runOpen = null; S.runDetail = null; render(); return;   /* toggle shut */
    }
    const idx = (S.rtRuns[rid] || {}).runs || [];
    const rec = idx.find(x=>x.output_file===name) || {};
    S.runOpen = {rid, name, started: rec.started_at || ""};
    S.runDetail = null;
    /* Marked read on OPEN, not on close: you have seen it the moment it is on
       screen, and a mark that waits for a close never lands when the reader
       simply navigates away. */
    markRunSeen(rid, name);
    render();
    loadRunDetail(rid, name);
  };
  scBody.querySelectorAll("[data-runopen]").forEach(el=>{
    el.onclick = ()=>openRun(el);
    el.onkeydown = e=>{ if (e.key==="Enter" || e.key===" "){ e.preventDefault(); openRun(el); } };
  });
  scBody.querySelectorAll("[data-runclose]").forEach(b=>b.onclick=()=>{
    S.runOpen = null; S.runDetail = null; render(); });
  scBody.querySelectorAll("[data-runcontinue]").forEach(b=>b.onclick=()=>{
    const d = S.runDetail;
    if (!d || !d.session_id) return;
    continueRunThread(b.dataset.runcontinue, d);
  });
  scBody.querySelectorAll("[data-rtdel]").forEach(b=>b.onclick=()=>{
    /* Deleting unloads a real launchd job. Confirm, and say what survives. */
    if (!confirm("Delete routine \"" + b.dataset.rtdel + "\"?\n\nThe scheduled job is " +
                 "removed. Its run history is kept on disk.")) return;
    rtAction("/" + b.dataset.rtdel + "/delete", {confirm:true}, "Deleted.");
  });

  /* ── connectors ──
     Three controls, one shape: mutate, re-read, render. Nothing is optimistic --
     what the screen shows is always the server's answer, because a toolkit that
     LOOKS enabled but is not is the failure mode that costs a turn to discover.
     Auth field edits go to S.connAuth (not the DOM) so a re-render mid-typing
     cannot drop them. */
  scBody.querySelectorAll("[data-cx]").forEach(el=>{
    const k = el.dataset.cx;
    el.oninput = ()=>{ (S.connAuth = S.connAuth || {})[k] = el.value; };
  });

  scBody.querySelectorAll("[data-cx-save]").forEach(b=>b.onclick=async ()=>{
    const a = S.connAuth || {};
    const body = {};
    /* A BLANK key field means "keep the key you have", not "clear it" -- the
       field renders empty on every load because the server never sends the key
       back, so treating empty as a clear would wipe it on any unrelated save. */
    if ((a.api_key||"").trim()) body.api_key = a.api_key.trim();
    if (a.user_id != null) body.user_id = a.user_id.trim();
    if (!Object.keys(body).length){ S.connAuthError = "Nothing to save."; render(); return; }
    S.connBusy = "auth"; S.connAuthError = null; S.connMsg = null; render();
    try {
      const r = await apiPost("/api/connectors/auth", body);
      /* The contract returns {error} as a normal body, so a 2xx with an error
         field is a refusal, not a success -- show it and keep what was typed. */
      if (r && r.error){ S.connAuthError = r.error; }
      else { S.conn = r; S.connAuth = {api_key:"", user_id:r.user_id||""};
             S.connMsg = "Saved."; }
    } catch (e) { S.connAuthError = e.message; }
    S.connBusy = null; render();
  });

  scBody.querySelectorAll("[data-cx-test]").forEach(b=>b.onclick=async ()=>{
    S.connBusy = "test"; S.connMsg = null; S.connAuthError = null; render();
    try {
      const r = await apiPost("/api/connectors/session", {force:true});
      if (r && r.state) S.conn = r.state;
      /* Composio refusing is an ANSWER, not an exception: it comes back 200
         with ok:false and the reason, and the reason is the useful part. */
      if (r && r.ok) S.connMsg = "Connected. Session " + (r.session_id||"") + ".";
      else S.connAuthError = (r && r.error) || "Could not create a session.";
    } catch (e) { S.connAuthError = e.message; }
    S.connBusy = null; render();
  });

  scBody.querySelectorAll("[data-conn-reload]").forEach(b=>b.onclick=()=>{
    loadConnectors(true); loadConnCatalog(true); loadLocal(true); loadLocalRegistry(true);
    loadClaudeConfigured(true); });
  /* Option A: configuring/authenticating is DELEGATED to Claude — we type the
     command into the PTY (sendToTerminal does NOT execute it; the operator reads
     it and presses Enter), so people use Claude's own familiar flow and Sutra
     never handles an OAuth token. Kept alongside the Composio/local halves: this
     mirrors what Claude already has and never enters the governed spawn path. */
  scBody.querySelectorAll("[data-conn-configured-reload]").forEach(b=>b.onclick=()=>{
    loadClaudeConfigured(true); });
  scBody.querySelectorAll("[data-conn-add-in-claude]").forEach(b=>b.onclick=()=>{
    sendToTerminal("claude mcp add "); });
  scBody.querySelectorAll("[data-conn-configure]").forEach(b=>b.onclick=()=>{
    sendToTerminal("claude mcp login " + shq(b.dataset.connConfigure)); });

  /* Enable/disable. Both the catalog card and the Disable button land here; the
     card sends no direction (flip), the button forces off, so a stale render
     cannot turn something back on. */
  const toggleToolkit = async (slug, on)=>{
    S.connBusy = "toolkit:"+slug; S.connMsg = null; S.connAuthError = null; render();
    try {
      const r = await apiPost("/api/connectors/toolkits/"+encodeURIComponent(slug)+"/toggle",
                              on==null ? {} : {on:!!on});
      if (r && r.error) S.connError = r.error;
      else { S.conn = r;
             S.connMsg = (r.enabled||[]).indexOf(slug)>=0
               ? "Enabled " + slug + ". It reaches sessions started from now on."
               : "Disabled " + slug + "."; }
    } catch (e) { S.connError = e.message; }
    S.connBusy = null;
    /* Re-read the catalog page so its cards carry the new enabled flags. */
    await loadConnCatalog(true);
  };
  scBody.querySelectorAll("[data-tk-pick]").forEach(b=>b.onclick=()=>toggleToolkit(b.dataset.tkPick, null));
  scBody.querySelectorAll("[data-tk-off]").forEach(b=>b.onclick=()=>toggleToolkit(b.dataset.tkOff, false));

  scBody.querySelectorAll("[data-cx-search]").forEach(el=>{ el.oninput = ()=>connCatalogSearch(el.value); });

  /* ── local connector (1MCP) ──
     Same shape as the hosted half: mutate, re-read, render, nothing optimistic.
     Form edits live in S.localForm because the transport <select> re-renders. */
  scBody.querySelectorAll("[data-lc-add]").forEach(b=>b.onclick=()=>{
    S.localForm = {name:"", transport:"stdio", tag:"", command:"", args:"", url:"", env:[]};
    S.localFormError = null; render();
    const el = scBody.querySelector('[data-lf="name"]'); if (el) el.focus();
  });
  scBody.querySelectorAll("[data-lc-cancel]").forEach(b=>b.onclick=()=>{
    S.localForm = null; S.localFormError = null; render(); });

  scBody.querySelectorAll("[data-lf]").forEach(el=>{
    const k = el.dataset.lf;
    el.oninput = ()=>{ if (S.localForm) S.localForm[k] = el.value; };
  });
  const lfT = scBody.querySelector("[data-lf-transport]");
  if (lfT) lfT.onchange = ()=>{ if (S.localForm){ S.localForm.transport = lfT.value; render(); } };

  scBody.querySelectorAll("[data-lenvk]").forEach(el=>{ const i=+el.dataset.lenvk;
    el.oninput = ()=>{ const e = S.localForm && S.localForm.env[i]; if (e) e.k = el.value; }; });
  scBody.querySelectorAll("[data-lenvv]").forEach(el=>{ const i=+el.dataset.lenvv;
    el.oninput = ()=>{ const e = S.localForm && S.localForm.env[i]; if (e) e.v = el.value; }; });
  scBody.querySelectorAll("[data-lenv-add]").forEach(b=>b.onclick=()=>{
    if (!S.localForm) return;
    (S.localForm.env = S.localForm.env || []).push({k:"", v:""}); render(); });
  scBody.querySelectorAll("[data-lenv-del]").forEach(b=>b.onclick=()=>{
    if (S.localForm && S.localForm.env) S.localForm.env.splice(+b.dataset.lenvDel, 1);
    render(); });

  scBody.querySelectorAll("[data-lc-save]").forEach(b=>b.onclick=async ()=>{
    const f = S.localForm || {};
    const name = (f.name||"").trim();
    if (!name){ S.localFormError = "A name is required."; render(); return; }
    const t = f.transport || "stdio";
    const body = {name, transport:t, enabled:true, title:(f.title||"").trim()};
    if ((f.tag||"").trim()) body.tag = f.tag.trim();
    if (t === "stdio"){
      body.command = (f.command||"").trim();
      body.args = (f.args||"").split(/\s+/).filter(Boolean);   /* space OR newline */
      const env = {};
      (f.env||[]).forEach(r=>{ const k=(r.k||"").trim(); if (k) env[k] = r.v||""; });
      body.env = env;
    } else {
      body.url = (f.url||"").trim();
    }
    S.localBusy = "save"; S.localFormError = null; S.connMsg = null; render();
    try {
      const r = await apiPost("/api/connectors/local", body);
      if (r && r.error){ S.localFormError = r.error; }
      else { S.localForm = null;
             S.connMsg = "Added " + ((r.server&&r.server.name)||name) + "."; }
    } catch (e) { S.localFormError = e.message; }
    S.localBusy = null; await loadLocal(true);
  });

  const lcAct = async (path, body, msg)=>{
    S.localBusy = path; S.connMsg = null; render();
    try {
      const r = await apiPost("/api/connectors/local" + path, body || {});
      if (r && r.error) S.localError = r.error; else if (msg) S.connMsg = msg;
    } catch (e) { S.localError = e.message; }
    S.localBusy = null; await loadLocal(true);
  };
  scBody.querySelectorAll("[data-lc-toggle]").forEach(b=>b.onclick=()=>
    lcAct("/" + b.dataset.lcToggle + "/toggle", {}, null));
  scBody.querySelectorAll("[data-lc-tag]").forEach(sel=>sel.onchange=()=>
    lcAct("/" + sel.dataset.lcTag + "/tag", {tag: sel.value}, "Re-filed under " + sel.value + "."));
  scBody.querySelectorAll("[data-lc-route]").forEach(b=>b.onclick=()=>
    lcAct("/options", {route_composio: b.getAttribute("aria-pressed") !== "true"}, null));

  /* The filter is a text field, so it commits on blur/Enter rather than per
     keystroke -- every commit rewrites 1MCP's config file. */
  scBody.querySelectorAll("[data-lc-filter]").forEach(el=>{
    const commit = ()=>{ if ((el.value||"") !== ((S.local&&S.local.filter)||""))
      lcAct("/options", {filter: el.value}, null); };
    el.onblur = commit;
    el.onkeydown = ev=>{ if (ev.key === "Enter"){ ev.preventDefault(); el.blur(); } };
  });

  scBody.querySelectorAll("[data-lc-remove]").forEach(b=>b.onclick=async ()=>{
    if (!window.confirm("Remove this local server?\n\nSessions started after this will no " +
                        "longer see its tools.")) return;
    S.localBusy = "remove"; S.connMsg = null; render();
    try { await apiDelete("/api/connectors/local/" + encodeURIComponent(b.dataset.lcRemove)); }
    catch (e) { S.localError = e.message; }
    S.localBusy = null; await loadLocal(true);
  });

  /* Aggregator version check -- the local half of auto-update, counterpart to
     the hosted connector's catalog check. */
  scBody.querySelectorAll("[data-lc-refresh]").forEach(b=>b.onclick=async ()=>{
    S.localBusy = "refresh"; S.connMsg = null; render();
    try {
      const r = await apiPost("/api/connectors/local/refresh", {force:true});
      if (r && r.error) S.localError = r.error;
      else if (r && r.updated) S.connMsg = "Aggregator updated " + r.from + " → " + r.version + ".";
      else S.connMsg = "Aggregator already up to date (" + (r&&r.version) + ").";
    } catch (e) { S.localError = e.message; }
    S.localBusy = null; await loadLocal(true);
  });

  scBody.querySelectorAll("[data-lc-search]").forEach(el=>{ el.oninput = ()=>lcRegistrySearch(el.value); });

  /* registry entry -> prefill. args arrive as an array and the form holds a
     string, so join; env_keys become empty rows so only the secret is left. */
  scBody.querySelectorAll("[data-lc-pick]").forEach(b=>b.onclick=()=>{
    const r = ((S.localReg||{}).results||[])[+b.dataset.lcPick]; if (!r) return;
    S.localForm = {
      name: r.name||"", title: r.title||"", tag: r.tag||"",
      transport: r.transport||"stdio", command: r.command||"",
      args: Array.isArray(r.args) ? r.args.join(" ") : (r.args||""),
      url: r.url||"", env: (r.env_keys||[]).map(k=>({k, v:""}))};
    S.localFormError = null; render();
    const el = scBody.querySelector('[data-lf="name"]'); if (el) el.focus();
  });

  /* The manual half of auto-update. force:true skips the TTL so pressing it
     always talks to GitHub, and the result distinguishes "checked, nothing
     changed" from "adopted a new catalog" -- collapsing them would make the
     button feel broken on the (common) unchanged path. */
  scBody.querySelectorAll("[data-cx-refresh]").forEach(b=>b.onclick=async ()=>{
    S.connBusy = "refresh"; S.connMsg = null; render();
    try {
      const r = await apiPost("/api/connectors/refresh", {force:true});
      if (r && r.error) S.connError = r.error;
      else if (r && r.updated) S.connMsg = "Catalog updated — " + (r.count||0) +
        " toolkits" + ((r.added||[]).length ? ", new: " + r.added.slice(0,6).join(", ") : "") + ".";
      else S.connMsg = "Already up to date.";
    } catch (e) { S.connError = e.message; }
    S.connBusy = null;
    await loadConnCatalog(true);
  });

  /* ── permission mode (chat level) ── */
  panes.querySelectorAll("[data-perm]").forEach(sel=>sel.onchange=()=>{
    const want = sel.value;
    /* Re-render first so the select snaps back to the EFFECTIVE mode if the
       confirmation is cancelled -- leaving it showing a mode that is not
       running would be the same lie the clamp exists to prevent. */
    setPermMode(want);
  });
  panes.querySelectorAll("[data-permok]").forEach(b=>b.onclick=()=>{
    if (S.permConfirm) applyPermMode(S.permConfirm.mode, true);
  });
  panes.querySelectorAll("[data-permno]").forEach(b=>b.onclick=()=>{
    S.permConfirm = null; S.permError = null; render();
  });

  /* ── model ── */
  panes.querySelectorAll("[data-model]").forEach(sel=>sel.onchange=()=>{
    /* Per-session only. Persisting it here would silently change the default for
       every other session too; Settings is where the default lives. */
    S.model[sel.dataset.model] = sel.value;
  });

  /* ── attachments ── */
  panes.querySelectorAll("[data-attach]").forEach(b=>b.onclick=()=>pickAttachment(b.dataset.attach));
  panes.querySelectorAll("[data-attrm]").forEach(b=>b.onclick=()=>{
    const [sid, i] = b.dataset.attrm.split(":");
    (S.attach[sid]||[]).splice(+i, 1);
    render();
  });
  panes.querySelectorAll("[data-sask]").forEach(inp=>{
    const sid = inp.dataset.sask;
    /* "/" opens the palette; it only ever lists commands that actually
       resolve, because the source is GET /api/skills reading ~/.claude. */
    autoGrowComposer(inp);
    inp.oninput = ()=>{
      S.composerText[sid] = inp.value;
      autoGrowComposer(inp);
      const p = paletteFor(inp.value);
      const was = S.palette && S.palette.sid===sid;
      if (p && p.items.length){ S.palette = { sid, items:p.items, idx:0, token:p.token,
                                              kind:p.kind }; render(); }
      else if (was){ S.palette = null; render(); }
    };
    inp.onkeydown = e=>{
      const pal = S.palette && S.palette.sid===sid ? S.palette : null;
      if (pal){
        if (e.key==="ArrowDown"){ e.preventDefault(); pal.idx=(pal.idx+1)%pal.items.length; render(); return; }
        if (e.key==="ArrowUp"){ e.preventDefault(); pal.idx=(pal.idx-1+pal.items.length)%pal.items.length; render(); return; }
        if (e.key==="Enter" || e.key==="Tab"){ e.preventDefault(); applyPalette(sid, pal.idx); return; }
        if (e.key==="Escape"){ e.preventDefault(); S.palette=null; render(); return; }
      }
      /* Shift+Enter is a NEWLINE, Enter sends. Ctrl/Cmd+J too, because that is
         what readline users reach for. Returning early leaves the default
         behaviour -- in a textarea that inserts the newline for us. */
      /* Cmd/Ctrl+Enter SENDS -- the convention in Claude Code, Slack, ChatGPT and
         GitHub. It used to insert a newline too, so an operator who reached for it
         watched the message sit in the box. Shift+Enter is a newline: return early
         and the textarea default inserts it. */
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        const composed = composeWithAttachments(sid, inp.value.trim());
        if(!composed) return;
        e.preventDefault();
        inp.value=""; S.composerText[sid]=""; S.palette=null;
        submitTurn(composed, sid);
        return;
      }
      if (e.key === "Enter" && e.shiftKey) return;
      if(e.key==="Enter"){
        /* Not gated on inp.value: an attachment with no typed text is a legitimate
           message ("here is the file"), and the old guard silently swallowed it. */
        const composed = composeWithAttachments(sid, inp.value.trim());
        if(!composed) return;
        e.preventDefault();
        inp.value=""; S.composerText[sid]=""; S.palette=null;
        submitTurn(composed, sid); }
    };
    /* Drop and paste land on the composer, which is where the operator aims. */
    inp.ondragover = e=>{ e.preventDefault(); inp.classList.add("dropping"); };
    inp.ondragleave = ()=>inp.classList.remove("dropping");
    inp.ondrop = e=>{
      const files = [...((e.dataTransfer && e.dataTransfer.files) || [])];
      if (!files.length) return;                 /* let a plain text drop behave normally */
      e.preventDefault(); inp.classList.remove("dropping");
      files.forEach(f=>uploadAttachment(sid, f));
    };
    inp.onpaste = e=>{
      const items = [...((e.clipboardData && e.clipboardData.files) || [])];
      if (!items.length) return;                 /* pasted TEXT must still paste as text */
      e.preventDefault();
      items.forEach(f=>uploadAttachment(sid, f));
    };
  });
  panes.querySelectorAll("[data-pal]").forEach(r=>r.onclick=()=>{
    if (S.palette) applyPalette(S.palette.sid, +r.dataset.pal); });
  panes.querySelectorAll('.pane:not(.browse) [data-ref]').forEach(n=>n.onclick=()=>{
    S.screen="departments"; S.sel=n.dataset.ref; render(); });

  scBody.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{S.view=b.dataset.view;render();});
  /* Directory search. render() restores focus + caret for the focused input,
     so re-rendering per keystroke does not steal the cursor. */
  const dq = scBody.querySelector("#dirQ");
  if (dq) dq.oninput = ()=>{ S.dirQ = dq.value; render(); };
  scBody.querySelectorAll("[data-chst]").forEach(b=>
    b.onclick = ()=>{ S.dirSt = b.dataset.chst; render(); });
  scBody.querySelectorAll("[data-toggle]").forEach(b=>b.onclick=()=>{
    S[b.dataset.toggle]=!S[b.dataset.toggle];
    render(); });
  scBody.querySelectorAll("[data-ref]").forEach(n=>{
    /* the tile IS the control: selecting a department also opens or closes its subtree */
    n.onclick=()=>{ const r=n.dataset.ref;
      if (DOMAINS.some(k=>k.parent_ref===r))
        S.collapsed.has(r) ? S.collapsed.delete(r) : S.collapsed.add(r);
      S.sel=r; render(); };
    if (n.getAttribute("draggable")==="true"){
      n.ondragstart=e=>{ S.drag=n.dataset.ref; n.classList.add("drg");
        e.dataTransfer.effectAllowed="move"; e.dataTransfer.setData("text/plain",n.dataset.ref);
        paintRings(n.dataset.ref); };
      n.ondragend=()=>{ S.drag=null; clearRings(); flushRender(); };
    }
    n.ondragover=e=>{ if(!S.drag) return;
      const src=byRef(S.drag), tgt=byRef(n.dataset.ref);
      if (!src||!tgt) return;
      if (blockCodesForMove(src,tgt).length) return;      /* no preventDefault ⇒ drop never fires */
      e.preventDefault(); e.dataTransfer.dropEffect="move"; };
    n.ondrop=e=>{ e.preventDefault(); if(!S.drag){ flushRender(); return; }
      const src=byRef(S.drag), tgt=byRef(n.dataset.ref);
      if (!src||!tgt) return;
      if (src.parent_ref===tgt.ref){ clearRings(); S.drag=null; flushRender(); return; }  /* inert no-op */
      if (blockCodesForMove(src,tgt).length){ clearRings(); S.drag=null; flushRender(); return; }
      S.draft.ops.push({op:"move",ref:src.ref,target:tgt.ref}); saveDraft();
      S.drag=null; render(); };
  });
  const sqEl=scBody.querySelector("#sq");
  if(sqEl) sqEl.oninput=()=>runSearch(sqEl.value);
  scBody.querySelectorAll("[data-goto-domain]").forEach(r=>r.onclick=()=>{
    S.screen="departments"; S.sel=r.dataset.gotoDomain; render(); });
  const q=scBody.querySelector("#q");
  if(q) q.oninput=()=>{S.q=q.value; const p=q.selectionStart; render();
    const n=scBody.querySelector("#q"); if(n){n.focus(); n.setSelectionRange(p,p);} };
  scBody.querySelectorAll("[data-facet]").forEach(b=>b.onclick=()=>{
    const g=S.cf[b.dataset.facet]; const v=b.dataset.val;
    g.has(v)?g.delete(v):g.add(v); render(); });
  scBody.querySelectorAll("[data-sort]").forEach(h=>h.onclick=()=>{
    const c=h.dataset.sort; S.sort = {col:c, dir: S.sort.col===c ? -S.sort.dir : 1}; render(); });
  scBody.querySelectorAll("[data-charter]").forEach(r=>r.onclick=()=>{S.selCharter=r.dataset.charter;render();});
  scBody.querySelectorAll("[data-pmode]").forEach(b=>b.onclick=()=>{S.pmode=b.dataset.pmode;render();});
  scBody.querySelectorAll("[data-revert]").forEach(b=>b.onclick=()=>{
    S.draft.ops.splice(+b.dataset.revert,1); saveDraft(); render(); });
  const rat=scBody.querySelector("#rat");
  /* debounced + chained: one POST per pause, and writes cannot overtake each
     other (an earlier keystroke's request landing last used to roll the stored
     rationale backwards) */
  if(rat) rat.oninput=()=>{S.draft.rationale=rat.value; saveDraftSoon();};
  /* The drift-simulation dev control was removed: it was a developer
   affordance on a product surface, and it was inverted -- it bumped a client-side
   counter the server never compared against, so it did nothing, while Rebase (which
   should CLEAR drift) was what actually triggered ORG-010. Real drift still surfaces:
   the server compares the draft's captured base against the registry on every
   simulate, so a concurrent mint raises ORG-010 without anyone faking it. */
  const rb=scBody.querySelector("#rebase");
  /* Rebase CLEARS drift: re-capture the registry's REAL fingerprint so the
     POSTed base matches the file again and ORG-010 stops firing. It used to
     write the locally-bumped count — i.e. rebasing CREATED the drift, and
     saveDraft() persisted it server-side across reloads. */
  if(rb) rb.onclick=()=>{ S.draft.base={...S.draft.base, domain_index_lines:META.domain_index_lines,
    captured_ms:Date.now()}; S.drift=false; invalidateSim(); saveDraft(); render(); };
  const dc=scBody.querySelector("#discard");
  if(dc) dc.onclick=()=>{ S.draft={ops:[],base:{...PLANS[0].base},rationale:"",
    plan_origin:"studio-drag",validated_at_ms:null}; S.drift=false;
    invalidateSim(); saveDraft(); render(); };
  const cc=scBody.querySelector("#copyCmd");
  if(cc) cc.onclick=()=>{ const s="placement_engine.py org plan --import ~/.sutra-ui/drafts/"+PLANS[0].plan_id+".json";
    try{ navigator.clipboard.writeText(s); cc.textContent="copied"; setTimeout(()=>cc.textContent="copy",1200);}catch(e){} };
}
function paintRings(srcRef){
  const src = byRef(srcRef); if(!src) return;
  const scBody = document.getElementById("scBody");
  let n=0;
  scBody.querySelectorAll("[data-ref]").forEach(node=>{
    const t = byRef(node.dataset.ref); if(!t) return;
    const codes = blockCodesForMove(src,t);
    if (codes.length){ node.classList.add("ring"); n++;
      node.title = codes.map(c=>c.code+" · "+c.subject).join("\n"); }
    else if (t.ref!==src.ref) node.classList.add("ok-t");
  });
  const s=document.getElementById("dragStatus");
  if(s) s.innerHTML = ` <b style="color:var(--block)">${n} blocked</b> for “${esc(src.name)}”.`;
}
function clearRings(){
  const scBody = document.getElementById("scBody");
  scBody.querySelectorAll("[data-ref]").forEach(n=>{
    n.classList.remove("ring","drg","ok-t"); n.removeAttribute("title"); });
  const s=document.getElementById("dragStatus"); if(s) s.textContent="";
}
document.querySelector(".rail").addEventListener("click", e=>{
  /* Feature A: the ⋮ trigger and its menu items. These run BEFORE the data-open
     branch below, each stopPropagation()+returns, so opening the menu never also
     opens the pane, and the document-level closer added later does not
     immediately re-close a just-opened menu. */
  const mt = e.target.closest("[data-sessmenu]");
  if (mt){ e.stopPropagation();
    S.sessMenu = S.sessMenu === mt.dataset.sessmenu ? null : mt.dataset.sessmenu;
    S.sessRename = null; renderRail(); return; }
  const act = e.target.closest("[data-act]");
  if (act){ e.stopPropagation();
    sessAction(act.dataset.act, act.dataset.sid, act.dataset.group); return; }
  const b = e.target.closest("[data-screen]");
  if (b && !b.disabled){
    /* "terminal" is a PANE TOGGLE living in the nav, not a screen. Routing it
       through S.screen would set S.screen to an id SCREENS has no entry for,
       and render() would blank the browse pane. */
    if (b.dataset.screen === "terminal"){ termToggle(); renderRail(); return; }
    S.screen=b.dataset.screen;
    /* Picking a screen is the OPEN gesture, the way clicking a session row is:
       a closed browse pane reopens rather than swapping content nobody can see. */
    if (S.ui.browseClosed){ S.ui.browseClosed = false; saveLayout(); }
    if (S.screen === "git") loadGit(false);      /* lazy: only when actually opened */
    if (S.screen === "editor") loadFs(false);    /* walking a real project is not free */
    if (S.screen === "automation") loadAuto(false);
    if (S.screen === "balance") loadBalance(false); /* lazy, like Git */
    /* force=true: unlike a repo, utilization moves while you are not looking, and
       a stale percentage is the one number this screen must not show. The 60s
       server cache is what keeps re-opening cheap. */
    if (S.screen === "usage") loadUsage(true);
    if (S.screen === "evals") loadEvals(false);     /* lazy, like Git */
    if (S.screen === "routines"){ loadRoutines(false); loadProposals(false); }
    /* lazy, like Git: reading the MCP config and the preset catalog on every boot
       is work a panel that never opens this screen has no reason to do. */
    if (S.screen === "connectors"){ loadConnectors(false); loadConnCatalog(false);
                                    loadLocal(false); loadLocalRegistry(false);
                                    loadClaudeConfigured(false); }
    render(); return;
  }
  const sg = e.target.closest("[data-sgroup]");
  if (sg){ S.sgroup = sg.dataset.sgroup; render(); return; }
  /* + on a project heading. Starts the session IN that folder rather than in the
     global workdir -- which is the only thing that makes a per-project + different
     from the one at the top of the rail. */
  const np = e.target.closest("[data-newproj]");
  if (np){ newSession(np.dataset.newproj); return; }
  const ss = e.target.closest("#sessSort");
  if (ss){ S.sessSort = S.sessSort === "az" ? "recent" : "az"; render(); return; }
  const op = e.target.closest("[data-open]");
  if (op){ const id=op.dataset.open;
    markRead(id); S.sessMenu = null; S.sessRename = null;
    if (!S.openPanes.includes(id)) S.openPanes.push(id);
    if (S.openPanes.length>2) S.openPanes = S.openPanes.slice(-2);
    /* opening a REAL session is what triggers the transcript read -- the list
       endpoint only read each file's head, so until now the turns are unknown,
       not empty */
    ensureTranscript(S.sessions.find(s=>s.id===id));
    render(); return; }
  const g = e.target.closest("[data-goto]");
  if (g){ S.screen="departments"; S.sel=g.dataset.goto; render(); }
});
document.querySelector(".rail").addEventListener("keydown", e=>{
  const ri = e.target.closest("[data-renameinput]");
  if (ri && e.key === "Enter"){ e.preventDefault(); renameSession(ri.dataset.sid, ri.value); }
  if (ri && e.key === "Escape"){ S.sessRename = null; renderRail(); }
});
/* One global closer: any click not on a ⋮ trigger or inside an open menu dismisses
   it. The ⋮/menu-item branches stopPropagation(), so this never fires for the
   click that opened the menu. Guarded so it costs nothing when closed. */
document.addEventListener("click", e=>{
  if (!S.sessMenu) return;
  if (e.target.closest("[data-sessmenu]") || e.target.closest(".smenu")) return;
  S.sessMenu = null; S.sessRename = null; renderRail();
});
/* New session: opens an empty pane on the right, exactly like the reference */
/* One path for every "start a session", so the rail button and the per-project +
   cannot drift. `cwd` is optional: with one, the new session gets that directory
   as its working-directory override (the same per-session mechanism the composer's
   folder chip writes), which is the entire point of a + that lives on a project
   heading -- starting a session "in" a project means starting it in that folder. */
function newSession(cwd){
  const s = { id:"s-"+(++SID), title:"New session", created_ms:NOW, updated_ms:NOW,
              turns:[], local:true, loadState:"live" };
  /* BOTH fields, deliberately. S.cwd is the override map sessCwd()/claudeWsUrl()
     read (so the session really runs in that folder); s.cwd is what the rail's
     project grouping and projOf() read. Writing only the first meant the + on a
     project heading opened a session that ran in the right directory but was
     listed under "No folder" -- the one group with no + of its own, so the
     button looked like it had done nothing. */
  if (cwd){ S.cwd[s.id] = cwd; s.cwd = cwd; }
  S.sessions.unshift(s);
  S.openPanes.push(s.id);
  if (S.openPanes.length>2) S.openPanes = S.openPanes.slice(-2);
  render();
  const inp = document.querySelector('[data-sask="'+s.id+'"]'); if (inp) inp.focus();
  return s;
}
/* With no argument the new session falls through to SETTINGS.workdir, which
   defaults to ~/sutra-ui-workspace -- a directory the operator never works in.
   Running `claude` in the repo they were discussing and hitting /resume then
   lists nothing, because claude only shows the project dir for the cwd you are
   standing in. Default to the folder in view instead. */
document.getElementById("newSession").onclick = () =>
  newSession(sessCwd(S.openPanes[S.openPanes.length - 1]) || "");
/* theme */
(function(){
  const r=document.documentElement, KEY="sutra.panel.theme";
  const rd=()=>{try{return localStorage.getItem(KEY)}catch(e){return null}};
  const wr=v=>{try{localStorage.setItem(KEY,v)}catch(e){}};
  const saved=rd(); if(saved==="light"||saved==="dark") r.setAttribute("data-theme",saved);
  const eff=()=>r.getAttribute("data-theme")||
    (matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");
  const lab=()=>themeBtn.setAttribute("aria-label","Switch to "+(eff()==="light"?"dark":"light")+" theme");
  lab();
  themeBtn.onclick=()=>{ const n=eff()==="light"?"dark":"light";
    r.setAttribute("data-theme",n); wr(n); lab(); };
})();
/* ══════════════════════ bootstrap ══════════════════════
   One registry, one org, so there is no scope to settle before reading it.
   boot() reads the registry, the runtime and the sessions together and lets
   each degrade on its own. */

const shq = p => "'" + String(p).replace(/'/g, "'\\''") + "'";
function sessAction(action, sid, group){
  const s = S.sessions.find(x=>x.id===sid); if(!s) return;
  switch(action){
    case "pin": togglePin(sid); S.sessMenu=null; break;
    case "unread": markUnread(sid); S.sessMenu=null; break;
    case "group": setGroup(sid, group||""); S.sessMenu=null; break;
    case "group-new": { const n=(prompt("Group name")||"").trim(); if(n) setGroup(sid,n); S.sessMenu=null; break; }
    case "rename": S.sessRename=sid; renderRail();
      { const i=document.querySelector('[data-renameinput][data-sid="'+sid+'"]'); if(i){ i.focus(); i.select(); } } return;
    case "rename-save": { const i=document.querySelector('[data-renameinput][data-sid="'+sid+'"]');
      renameSession(sid, i?i.value:""); return; }
    case "fork": forkSession(sid); return;
    case "archive": archiveSession(sid); return;
    case "delete": deleteSession(sid); return;
    case "open-terminal": { const cwd=sessCwd(sid); if(cwd) sendToTerminal("cd "+shq(cwd)+"\n"); S.sessMenu=null; break; }
    case "open-editor": S.sessMenu=null; S.screen="editor"; loadFs(true); render(); return;
    case "open-repo":
      if(!S.openPanes.includes(sid)){ S.openPanes.push(sid); if(S.openPanes.length>2) S.openPanes=S.openPanes.slice(-2); }
      loadRepo(sid,true); S.sessMenu=null; break;
    case "open-finder": revealSession(sid); return;
  }
  render();
}
async function renameSession(sid, title){
  title=(title||"").trim(); if(!title){ S.sessRename=null; renderRail(); return; }
  const s=S.sessions.find(x=>x.id===sid);
  if (s && !s.real){ s.title=title; S.sessRename=null; S.sessMenu=null; render(); return; }
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/rename", {title});
    if(s) s.title=title; S.sessRename=null; S.sessMenu=null;
    S.toast="renamed — the same record Claude writes, so it shows there too";
  }catch(e){ S.toast="rename failed: "+e.message; }
  render();
}
function forkSession(sid){
  const src=S.sessions.find(x=>x.id===sid); if(!src) return;
  const s=newSession(sessCwd(sid));
  s.title="Fork of "+(src.title||"session");
  s.fork=true; s.forkOf=sid;
  s.claude_session=src.claude_session||src.id;
  S.turnOpts[s.id]=Object.assign({}, S.turnOpts[s.id], {fork_session:true});
  S.sessMenu=null; render();
}
async function archiveSession(sid){
  if(!confirm("Archive this session? The transcript moves out of Claude's project folder to ~/.sutra-ui/archive — it stops listing here and in Claude, and is recoverable.")) return;
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/archive", {});
    S.sessions=S.sessions.filter(x=>x.id!==sid); S.openPanes=S.openPanes.filter(x=>x!==sid);
    S.sessMenu=null; S.toast="archived — recoverable in ~/.sutra-ui/archive";
  }catch(e){ S.toast="archive failed: "+e.message; }
  render();
}
async function deleteSession(sid){
  if(!confirm("Delete this session? History is NOT destroyed — the transcript moves to ~/.sutra-ui/trash and can be restored.")) return;
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/delete", {});
    S.sessions=S.sessions.filter(x=>x.id!==sid); S.openPanes=S.openPanes.filter(x=>x!==sid);
    S.sessMenu=null; S.toast="deleted — recoverable in ~/.sutra-ui/trash";
  }catch(e){ S.toast="delete failed: "+e.message; }
  render();
}
async function revealSession(sid){
  S.sessMenu=null;
  try{ await apiPost("/api/sessions/"+encodeURIComponent(sid)+"/reveal", {}); }
  catch(e){ S.toast="could not reveal: "+e.message; render(); }
}

function backendError(e){
  document.getElementById("panes").innerHTML =
    `<section class="pane browse"><div class="pb">
      <div class="zero"><h4>Could not reach the backend</h4>
      <p>${esc(e.message)}</p>
      <p style="color:var(--faint)">Is the server running? <code>uvicorn app:app</code> from
      <code>sutra-ui/</code>.</p></div></div></section>`;
  console.error(e);
}

/* Registry reads. Separated from the runtime reads below because they answer
   different questions: what the org IS, versus what this machine can run. */
async function loadOrg(){
  const [tree, charters, placements, history] = await Promise.all([
    apiGet("/api/org/tree?include_retired=true"),
    apiGet("/api/org/charters"),
    apiGet("/api/org/placements"),
    apiGet("/api/org/history"),
  ]);
  DOMAINS = tree;
  CHARTERS = charters;
  PLACEMENTS = placements;
  INDEX = history.events || [];
  // history_complete_from_ms is DERIVED server-side (earliest event carrying a
  // before/after snapshot), not a stored engine field -- see /api/org/history.
  META.history_complete_from_ms = history.meta.history_complete_from_ms;
  META.history_derived = history.meta.derived;
  META.domain_index_lines = history.meta.domain_index_lines;
  META.legacy_events = history.meta.legacy_events;
  invalidateSim();
}

/* Machine state, not registry state: what can run, and how it is configured. */
async function loadRuntime(){
  /* allSettled, NOT all. These are three independent endpoints, and under
     Promise.all a 500 from /api/skills -- a catalog walk that touches every
     plugin directory on the machine -- discarded a perfectly good
     /api/settings response and left SETTINGS null for the life of the window.
     The Settings screen then rendered "GET /api/settings has not answered",
     which is not what happened and cannot be falsified from the screen.
     Each subsystem now fails on its own and says which one failed. */
  const [skillsR, provsR, settingsR] = await Promise.allSettled([
    apiGet("/api/skills"),
    apiGet("/api/providers"),
    apiGet("/api/settings"),
  ]);
  const reason = r => String((r.reason && r.reason.message) || r.reason);
  const failed = [];

  if (skillsR.status === "fulfilled"){
    const skills = skillsR.value;
    SKILLS = skills.items || [];
    SKILLS_META = { by_kind: skills.by_kind, by_source: skills.by_source,
                    by_provider: skills.by_provider, total: skills.total,
                    runnable: skills.runnable, providers: skills.providers || [] };
    S.cat.etag = skills.signature || null;
  } else {
    failed.push("GET /api/skills — " + reason(skillsR));
  }

  if (provsR.status === "fulfilled") PROVIDERS = provsR.value.providers || [];
  else failed.push("GET /api/providers — " + reason(provsR));

  if (settingsR.status === "fulfilled"){
    const settings = settingsR.value;
    SETTINGS = settings.settings || null;
    PERM_MODES = settings.permission_modes || [];
    MODELS = settings.models || [];
  } else {
    failed.push("GET /api/settings — " + reason(settingsR));
  }

  /* Reported, not thrown: boot() already treats the runtime as degradable, and
     the screens read S.runtimeError to say what actually failed. */
  S.runtimeError = failed.length ? failed.join(" · ") : null;
  /* The freshness baseline is seeded from the SAME response that populated
     SKILLS (S.cat.etag, set above), so the first poll compares against what is
     actually on screen rather than re-fetching a catalog the panel already has. */
  S.cat.readAt = Date.now();
  S.cat.lastCheckAt = Date.now();
}

/* ── connectors ──────────────────────────────────────────────────────────────
   The Composio connector the Connectors screen manages. Two loaders, both
   CACHING (S.conn / S.connCat stay set until a forced reload) and both reporting
   failures into state without throwing -- the same degradable contract loadAuto
   uses, because a panel whose Connectors screen throws is a panel that looks
   broken over a subsystem the operator may not even use.

   Neither loader ever holds the API key: /api/connectors answers with a redacted
   state (api_key_set + last four), so there is nothing here to leak into a
   client-side log or a screenshot. */
async function loadConnectors(force){
  if (S.conn && !force) return;
  try {
    S.conn = await apiGet("/api/connectors"); S.connError = null;
    /* Seed the editable user id from the server ONCE, so the field shows what is
       stored without clobbering something half-typed on a forced re-read. */
    if (!S.connAuth) S.connAuth = {api_key:"", user_id:S.conn.user_id||""};
  }
  catch (e) { S.connError = e.message; S.conn = null; }
  render();
}

/* The catalog page. The server serves it from the local mirror and refreshes
   that mirror on a TTL, so this is a local read that occasionally costs one
   conditional GET to GitHub -- typing in the search box never waits on the
   network for a catalog that has not changed. */
async function loadConnCatalog(force){
  if (S.connCat && !force) return;
  S.catBusy = true;
  const q = (S.connQuery || "").trim();
  try {
    S.connCat = await apiGet("/api/connectors/catalog?limit=60&q=" + encodeURIComponent(q));
    S.catError = null;
  } catch (e) { S.catError = e.message; if (!S.connCat) S.connCat = {results:[], total:0}; }
  S.catBusy = false;
  render();
}

/* Debounced so we don't fire a request per keystroke. */
let _catSearchTimer = null;
function connCatalogSearch(q){
  S.connQuery = q;
  if (_catSearchTimer) clearTimeout(_catSearchTimer);
  _catSearchTimer = setTimeout(()=>{ _catSearchTimer = null; loadConnCatalog(true); }, 250);
}

/* ── local connector ─────────────────────────────────────────────────────────
   The 1MCP half. Three loaders on the same degradable contract as the hosted
   half: cache unless forced, report failures into state, never throw.

   apiDelete lives here because removing a local server is the only DELETE the
   Connectors screen issues, and neither apiGet nor apiPost covers one -- same
   _fail error shape as the others, so a 500 here reads like a 500 anywhere. */
async function apiDelete(path){
  const r = await fetch(API + path, { method:"DELETE" });
  if (!r.ok) throw await _fail(r, path);
  return r.json();
}
/* Option A (2026-08-15): the connectors PRESENT IN CLAUDE, read live from
   `claude mcp list` via /api/connectors/configured. Display-only — the panel
   mirrors Claude and delegates add/auth to Claude itself; it never holds a
   token. Holds the whole {connectors,error,stale} payload so the screen can
   badge status and surface a read error without throwing.

   Kept through the Composio merge: it is the one half of the old connectors
   model with no equivalent on the hosted/local side, and its endpoint survived
   because it reads Claude rather than Sutra's own store. The preset gallery and
   registry search that used to live beside it are NOT re-wired -- the local
   (1MCP) half now owns those paths. */
async function loadClaudeConfigured(force){
  if (S.claudeConfigured && !force) return;
  try { S.claudeConfigured = await apiGet("/api/connectors/configured"); }
  catch (e) { S.claudeConfigured = { connectors: [], error: e.message, stale: false }; }
  render();
}

async function loadLocal(force){
  if (S.local && !force) return;
  try {
    S.local = await apiGet("/api/connectors/local"); S.localError = null;
    /* The category <select> on each row offers every tag currently IN USE, so
       re-filing a server means picking a group that exists rather than typing
       a new one and hoping it matches. */
    S.localTags = (S.local.groups||[]).map(g=>g.tag);
  }
  catch (e) { S.localError = e.message; S.local = null; }
  render();
}

async function loadLocalRegistry(force){
  if (S.localReg && !force) return;
  S.localRegBusy = true;
  const q = (S.localQuery || "").trim();
  try { S.localReg = await apiGet("/api/connectors/local/registry?limit=24&q=" +
                                  encodeURIComponent(q)); }
  catch (e) { if (!S.localReg) S.localReg = {results:[], error:e.message}; }
  S.localRegBusy = false;
  render();
}

let _lcSearchTimer = null;
function lcRegistrySearch(q){
  S.localQuery = q;
  if (_lcSearchTimer) clearTimeout(_lcSearchTimer);
  _lcSearchTimer = setTimeout(()=>{ _lcSearchTimer = null; loadLocalRegistry(true); }, 300);
}

/* ── skills auto-refresh ─────────────────────────────────────────────────────
   The catalog was read ONCE, in boot(). Installing a plugin or writing a new
   command meant the palette kept offering yesterday's list until the app was
   restarted -- and, worse, could keep offering a command that no longer resolves.

   ETag, not a separate probe endpoint: /api/skills returns the signature of the
   payload it is actually returning, from the same scan. A /signature endpoint would
   scan twice and let the client store a fingerprint describing state it never
   received -- a missed update that never self-corrects, because every later probe
   matches the stored value.

   Only /api/skills is polled. Re-fetching /api/settings on a timer would clobber a
   permission-mode or workdir change the operator is in the middle of making. */
const CAT_TICK_MS      = 20000;   /* how often we CONSIDER refreshing */
const CAT_FOCUSED_MS   = 60000;   /* refresh at most this often while focused */
const CAT_VISIBLE_MS   = 300000;  /* ... and far less often when merely visible */
const CAT_BACKOFF      = [60000, 120000, 300000];

