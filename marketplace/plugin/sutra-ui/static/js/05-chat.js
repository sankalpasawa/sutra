/* ── run threads ─────────────────────────────────────────────────────────────
   Every scheduled run is its own conversation, kept on disk. The row is the
   entry to it: click one and the reply it produced is rendered underneath, with
   an unread mark until you have opened it.

   UNREAD IS PER MACHINE, in localStorage, and is keyed by <routine>/<output
   file> -- the output filename is the run's timestamp, so the key is unique and
   stable without the server having to track who has read what. A routine you
   have never opened shows every run unread, which is the honest starting state:
   nobody has read them. */
const LS_RUNSEEN = "sutra.panel.runseen";
function runSeenSet(){
  if (!S._runSeen){
    const raw = lsGet(LS_RUNSEEN, []);
    S._runSeen = new Set(Array.isArray(raw) ? raw : []);
  }
  return S._runSeen;
}
function runKey(rid, name){ return rid + "/" + name; }
function runIsUnread(rid, r){
  /* A run with no captured output has nothing to read, so it is never "unread" --
     marking it so would promise a thread that does not exist. */
  return !!r.output_file && !runSeenSet().has(runKey(rid, r.output_file));
}
function markRunSeen(rid, name){
  const s = runSeenSet();
  if (s.has(runKey(rid, name))) return;
  s.add(runKey(rid, name));
  /* Bounded: one entry per run forever would grow without limit on a routine
     that fires hourly. The newest 500 is far more than any unread mark is worth. */
  const all = [...s].slice(-500);
  S._runSeen = new Set(all);
  lsSet(LS_RUNSEEN, all);
}
const LS_PINNED = "sutra.panel.pinned";
const LS_UNREAD = "sutra.panel.unread";
const LS_GROUPS = "sutra.panel.groups";
function pinnedSet(){ if(!S._pinned){ const r=lsGet(LS_PINNED,[]); S._pinned=new Set(Array.isArray(r)?r:[]); } return S._pinned; }
function isPinned(sid){ return pinnedSet().has(sid); }
function togglePin(sid){ const s=pinnedSet(); if(s.has(sid))s.delete(sid); else s.add(sid); lsSet(LS_PINNED,[...s]); }
function unreadSet(){ if(!S._unread){ const r=lsGet(LS_UNREAD,[]); S._unread=new Set(Array.isArray(r)?r:[]); } return S._unread; }
function isUnread(sid){ return unreadSet().has(sid); }
function markUnread(sid){ const s=unreadSet(); s.add(sid); lsSet(LS_UNREAD,[...s]); }
function markRead(sid){ const s=unreadSet(); if(s.delete(sid)) lsSet(LS_UNREAD,[...s]); }
function groupMap(){ if(!S._groups){ const r=lsGet(LS_GROUPS,{}); S._groups=(r&&typeof r==="object")?r:{}; } return S._groups; }
function setGroup(sid,name){ const g=groupMap(); if(name) g[sid]=name; else delete g[sid]; lsSet(LS_GROUPS,g); }
function pinFirst(arr){ return arr.slice().sort((a,b)=>(isPinned(b.id)?1:0)-(isPinned(a.id)?1:0)); }

function rtUnreadCount(rid, runs){
  if (!runs || !runs.runs) return 0;
  return runs.runs.filter(r=>runIsUnread(rid, r)).length;
}

function rtRunRow(r, rid){
  const pill = r.outcome==="ok" ? `<span class="pill p-ok">ok</span>`
    : r.outcome==="skipped" ? `<span class="pill p-mut">skipped</span>`
    : `<span class="pill p-block">${esc(r.outcome||"?")}</span>`;
  const open = S.runOpen && S.runOpen.rid===rid && S.runOpen.name===r.output_file;
  const unread = runIsUnread(rid, r);
  return `<tr class="runrow ${open?"sel":""}" ${r.output_file
        ? `data-runopen="${esc(rid)}" data-runname="${esc(r.output_file)}" tabindex="0"
           title="Read what this run said"` : ""}>
    <td>${r.output_file?`<i class="rundot ${unread?"on":""}" aria-hidden="true"></i>`:""}${pill}</td>
    <td class="num">${esc(fmt(Date.parse(r.started_at)))}</td>
    <td>${esc(r.trigger||"")}</td><td class="num">${r.duration_s??"—"}s</td>
    <td class="num">${r.cost_usd!=null?"$"+Number(r.cost_usd).toFixed(4):"—"}</td>
    <td>${r.detail?esc(String(r.detail).slice(0,120)):""}</td></tr>`;
}

/* The opened run: what it actually said, and the way back into that thread. */
function rtRunThreadHtml(rid){
  if (!S.runOpen || S.runOpen.rid !== rid) return "";
  const d = S.runDetail;
  if (!d) return `<div class="runthread"><p class="prnone">Reading this run…</p></div>`;
  if (d.error) return `<div class="runthread"><p class="prnone">${esc(d.error)}</p></div>`;
  const denials = (d.permission_denials||[]).map(x=>x && x.tool_name).filter(Boolean);
  /* An empty result is not an empty run. Say WHY it is empty -- a denied tool is
     the usual cause, and "nothing here" without the reason reads as a broken
     routine rather than one that asked for permission nobody was there to give. */
  const body = (d.result && String(d.result).trim())
    ? `<div class="md">${mdHtml(String(d.result))}</div>`
    : (!d.parsed
        ? `<pre class="toutbody">${esc(String(d.text||"").slice(0,4000))}</pre>`
        : `<p class="prnone">This run produced no reply${
            denials.length ? " — it was denied " + esc(denials.join(", "))
                             + ", and nobody was there to approve it." : "."}</p>`);
  return `<div class="runthread">
      <div class="runhead">
        <b>${esc(fmt(Date.parse((S.runOpen.started||""))))}</b>
        ${d.turns!=null?`<span class="pill p-mut">${d.turns} turn${d.turns===1?"":"s"}</span>`:""}
        ${d.cost_usd!=null?`<span class="pill p-mut">$${Number(d.cost_usd).toFixed(4)}</span>`:""}
        ${denials.length?`<span class="pill p-warn">denied ${esc(denials.join(", "))}</span>`:""}
        ${d.session_id
          ? `<button class="btn" type="button" data-runcontinue="${esc(rid)}"
               title="Open this run as a chat and carry on from where it stopped">Continue this thread</button>`
          : `<span class="why">no session id recorded — this run cannot be resumed</span>`}
        <button class="ib" type="button" data-runclose="1" aria-label="Close this run">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
      ${body}
    </div>`;
}

/* What the chat agent asked for. Rendered ABOVE the routines themselves and on
   the empty screen too -- a proposal the operator cannot see is a request that
   silently expires, which is worse than not offering the capability at all.

   The agent's own summary is shown verbatim and is never trusted to decide
   anything: it is a label written by an LLM acting on text that may not have
   come from the operator. The ARGUMENTS are what actually applies, so they are
   shown too, in full. */
function proposalsHtml(){
  const all = S.props || [];
  const open = all.filter(p=>p.status==="pending");
  if (!open.length && !S.propError) return "";
  if (S.propError) return `<div class="note b"><b>Could not read proposals.</b>
    ${esc(S.propError)}</div>`;
  const arg = p => {
    const a = p.args || {};
    if (p.kind === "routine.create")
      return `<code>${esc(a.id||"")}</code> · ${esc((a.schedule||{}).preset||"manual")}
              · runs in <code>${esc(a.cwd||"")}</code>
              · <code>${esc(a.permission_mode||"dontAsk")}</code>
              · $${esc(String((a.opts||{}).max_budget_usd??"?"))}/run`;
    if (p.kind === "routine.update")
      return `<code>${esc(a.id||"")}</code> — changes:
              <code>${esc(Object.keys(a.patch||{}).join(", "))}</code>`;
    return `<code>${esc(a.id||"")}</code>`;
  };
  return `<div class="note" style="border-left-color:var(--acc)">
    <b>${open.length} request${open.length===1?"":"s"} from the chat</b>
    <p style="margin:5px 0;color:var(--faint)">Sutra asked to do the following.
      Nothing has happened yet — these apply only if you approve them.</p>
    ${open.map(p=>`<div class="kv" style="align-items:flex-start">
      <b>${esc(p.kind.replace("routine.",""))}</b>
      <span>
        <div>${esc(p.summary||"")}</div>
        <div class="why" style="margin-top:3px">${arg(p)}</div>
        <div style="margin-top:7px">
          <button class="btn" type="button" data-prok="${esc(p.id)}"
            ${S.propBusy?"disabled":""}>${S.propBusy===p.id?"Applying…":"Approve"}</button>
          <button class="btn" type="button" data-prno="${esc(p.id)}"
            ${S.propBusy?"disabled":""}>Reject</button>
        </div>
      </span></div>`).join("")}
  </div>`;
}

function rtCard(r){
  const runs = S.rtRuns[r.id];
  const sched = (r.schedule||{}).human || "—";
  const state = !r.enabled ? `<span class="pill p-mut">paused</span>`
    : !r.loaded ? `<span class="pill p-warn">not loaded</span>`
    : `<span class="pill p-ok">active</span>`;
  /* "never run" and "0 runs" are different claims. Only one of them is true here. */
  const last = r.never_run
    ? `<span class="pill p-warn">never run</span> <span class="why">Run it once now
        to check it works.</span>`
    : r.last_run
      ? `${r.last_run.outcome==="ok"?`<span class="pill p-ok">last ok</span>`
          :`<span class="pill p-block">last ${esc(r.last_run.outcome)}</span>`}
         <span class="why">${esc(fmt(Date.parse(r.last_run.started_at)))}${
           r.last_run.cost_usd!=null?" · $"+Number(r.last_run.cost_usd).toFixed(4):""}</span>`
      : "";
  return `<section class="chsec" data-rt="${esc(r.id)}">
    <h2 class="chh">${esc(r.id)} <span class="pill p-mut">Local</span></h2>
    <p style="margin:0 0 8px;color:var(--muted)">${esc(r.description||"")}</p>
    <div class="kv"><b>Schedule</b><span>${esc(sched)} ${state}</span></div>
    <div class="kv"><b>Last run</b><span>${last}</span></div>
    <div class="kv"><b>Folder</b><span><code>${esc(r.cwd)}</code>${
      r.cwd_exists?"":` <span class="pill p-block">missing</span>`}</span></div>
    <div class="kv"><b>Runs as</b><span><code>${esc(r.permission_mode)}</code>${
      r.model?` · <code>${esc(r.model)}</code>`:""}</span></div>
    ${!r.enabled?`<div class="note"><b>Paused.</b> It will not fire on its own.
      Run now still works, so pausing does not cost you the ability to test it.</div>`:""}
    ${r.enabled&&!r.loaded?`<div class="note b"><b>Saved as active, but launchd has not
      loaded it — it will not fire.</b> Use Re-check after fixing, or delete and
      recreate it.</div>`:""}
    ${r.never_fired_on_schedule?`<div class="note w"><b>Never fired on schedule.</b>
      Every run so far was started by hand. Run now ignores the schedule, so a green
      run proves the routine works, not that the schedule does.</div>`:""}
    <p style="margin:9px 0 0">
      <button class="btn" type="button" data-rtrun="${esc(r.id)}" ${S.rtBusy?"disabled":""}
        >${S.rtBusy==="/"+r.id+"/run"?"Starting…":"Run now"}</button>
      <button class="btn" type="button" data-rttoggle="${esc(r.id)}" data-en="${r.enabled?0:1}"
        >${r.enabled?"Pause":"Resume"}</button>
      <button class="btn" type="button" data-rtruns="${esc(r.id)}">${
        runs?"Refresh runs":"Show runs"}${
          /* The count is on the BUTTON as well as the rows, because before you
             press it the rows do not exist -- and "3 unread" is the reason to. */
          runs && rtUnreadCount(r.id, runs) ? " · " + rtUnreadCount(r.id, runs) + " unread" : ""}</button>
      <button class="btn" type="button" data-rtdel="${esc(r.id)}">Delete</button></p>
    ${runs?(runs.error?`<div class="note b">${esc(runs.error)}</div>`
      : runs.total===0 ? `<div class="note">No runs recorded yet.</div>`
      : `<div class="tw"><table><thead><tr><th>Outcome</th><th>Started</th><th>Trigger</th>
          <th>Took</th><th>Cost</th><th>Detail</th></tr></thead>
          <tbody>${
            /* An ARROW, not a bare reference. `.map(rtRunRow)` passes the index
               as the second argument, so the routine id would silently become 0,
               1, 2 -- every row keyed to a routine that does not exist. */
            runs.runs.map(x=>rtRunRow(x, r.id)).join("")
          }</tbody></table></div>`):""}
    ${rtRunThreadHtml(r.id)}
  </section>`;
}

SCREENS.routines = () => {
  if (S.rtError && !S.rt) return `<div class="zero"><h4>Routines unavailable</h4>
    <p>${esc(S.rtError)}</p></div>`;
  if (!S.rt) return `<div class="zero"><h4>Reading…</h4>
    <p>${esc(TITLES.routines[1])}</p></div>`;
  const st = S.rt, list = st.routines || [];

  /* The sharp edge of LOCAL scheduling, stated at the top rather than discovered
     after a missed morning. */
  const caveat = `<div class="note"><b>These run on this Mac, not in the cloud.</b>
    ${esc(st.note||"")}</div>`;
  const orphan = (st.orphans||[]).length ? `<div class="note w">
    <b>${st.orphans.length} scheduled job${st.orphans.length===1?"":"s"} with no routine
    behind ${st.orphans.length===1?"it":"them"}.</b> Left over from a deleted routine or an
    older install; ${st.orphans.length===1?"it":"they"} would still fire.
    <button class="btn" type="button" data-rtfix>Remove them</button></div>` : "";
  const banner = S.rtMsg ? `<div class="note"><b>${esc(S.rtMsg)}</b></div>`
    : (S.rtError ? `<div class="note b">${esc(S.rtError)}</div>` : "");

  if (!list.length && !S.rtForm) return `${caveat}${orphan}${banner}${proposalsHtml()}
    <div class="zero"><h4>No routines yet</h4>
      <p>A routine is a prompt this Mac runs on a schedule — a morning brief, a nightly
         check, a weekly summary — without you opening anything.</p>
      <p style="color:var(--faint)">Stored in <code>${esc(st.store)}</code>, scheduled with
         a launchd user agent. Nothing runs until you create one.</p>
      <p><button class="btn" type="button" data-rtnew>New routine</button></p></div>`;

  return `${caveat}${orphan}${banner}${proposalsHtml()}
    <p style="margin-bottom:10px"><button class="btn" type="button" data-rtnew
      >New routine</button> <button class="btn" type="button" data-rtreload>Re-check</button></p>
    ${rtCreateForm()}
    ${list.map(r=>r.unreadable
      ? `<div class="note b"><b>${esc(r.id)} could not be read.</b> ${esc(r.unreadable)}</div>`
      : rtCard(r)).join("")}`;
};

/* Colour a unified diff. Line-based on purpose: a token-level differ would be a
   second, subtly different opinion about what changed from the one git already
   gave us, and this screen's job is to show git's answer. */
function diffHtml(text){
  return text.split("\n").slice(0, 4000).map(l=>{
    const c = l.startsWith("+++") || l.startsWith("---") ? "dh"
            : l.startsWith("@@") ? "dhunk"
            : l.startsWith("+") ? "dadd"
            : l.startsWith("-") ? "ddel"
            : l.startsWith("diff ") || l.startsWith("index ") ? "dh" : "";
    return `<span class="${c}">${esc(l)}</span>`;
  }).join("\n");
}

/* ── updates ──────────────────────────────────────────────────────────────
   TWO components, and they are NOT the same kind of thing. Showing them as one
   "check for updates" button would be a lie about how either behaves:

     Desktop app  checked in the background by the Electron shell and installed
                  automatically (mandatory, founder direction 2026-08-06). The
                  staged build applies on quit; the banner is the countdown.
                  These buttons are the manual path, which still matters: it is
                  what remains after the automatic path has given up on a
                  release.
     Plugin       updates itself once a day at session start, applying to the
                  NEXT session. The button only makes it immediate.

   Nothing on THIS screen runs on load: these are network calls, and a panel
   that phones GitHub every time it opens is a different thing from one with a
   button. S.upd stays null until asked. The banner's poll is a different route
   (/api/updates/staged) precisely because that one touches nothing remote. */
function updatesHtml(){
  const u = S.upd;
  const busy = S.updBusy;

  if (!u && !S.updError) return `
    <section class="chsec"><h2 class="chh">Updates</h2>
      <p style="font-size:11.5px;color:var(--muted);margin-bottom:9px">
        The desktop app and the Claude Code plugin update by different routes.
        Nothing is checked until you ask — this reaches GitHub.</p>
      <button class="btn" type="button" data-upd="check" ${busy?"disabled":""}>
        ${busy==="check"?"Checking…":"Check for updates"}</button>
    </section>`;

  if (S.updError) return `
    <section class="chsec"><h2 class="chh">Updates</h2>
      <div class="note b"><b>Could not check.</b> ${esc(S.updError)}</div>
      <button class="btn" type="button" data-upd="check" ${busy?"disabled":""}>
        ${busy==="check"?"Checking…":"Try again"}</button>
    </section>`;

  /* One row per component. `managed:false` is a real answer, not an error --
     a source checkout has no .app to replace, and that is worth saying. */
  const row = (c, label, installBtn) => {
    if (!c.managed) return `<div class="kv"><b>${esc(label)}</b>
      <span><span class="pill p-mut">not managed here</span> ${esc(c.reason||"")}</span></div>`;
    const cur = c.installed || "unknown";
    const state = c.error
      ? `<span class="pill p-warn">check failed</span> <span class="why">${esc(c.error)}</span>`
      : c.update_available
        ? `<span class="pill p-acc">${esc(c.latest)} available</span>`
        : `<span class="pill p-ok">up to date</span>`;
    return `<div class="kv"><b>${esc(label)}</b><span>
      <code>${esc(cur)}</code> ${state}
      ${c.update_available && !c.error ? installBtn : ""}
    </span></div>
    <div class="kv"><b></b><span class="why">${esc(c.note||"")}</span></div>`;
  };

  const d = u.desktop || {}, p = u.plugin || {};
  const dBtn = `<button class="btn" type="button" data-upd="desktop"
      ${busy?"disabled":""}>${busy==="desktop"?"Downloading…":"Download & install"}</button>`;
  const pBtn = `<button class="btn" type="button" data-upd="plugin"
      ${busy?"disabled":""}>${busy==="plugin"?"Updating…":"Update now"}</button>`;

  return `
    <section class="chsec"><h2 class="chh">Updates</h2>
      ${S.updMsg?`<div class="note"><b>${esc(S.updMsg)}</b></div>`:""}
      ${row(d, "Desktop app", dBtn)}
      ${row(p, "Plugin", pBtn)}
      <p style="margin-top:9px">
        <button class="btn" type="button" data-upd="check" ${busy?"disabled":""}>
          ${busy==="check"?"Checking…":"Re-check"}</button>
        ${d.release_url?`<a class="btn" href="${esc(d.release_url)}" target="_blank"
           rel="noreferrer">Release notes</a>`:""}
      </p>
      ${d.update_available?`<div class="note"><b>Installing the desktop update quits Sutra.</b>
        The download is checksum-verified and Gatekeeper-checked before anything is replaced;
        the swap happens once the app exits, and it reopens itself.</div>`:""}
    </section>`;
}

async function checkUpdates(){
  S.updBusy = "check"; S.updError = null; S.updMsg = null; render();
  try { S.upd = await apiGet("/api/updates"); }
  catch (e) { S.updError = e.message; S.upd = null; }
  S.updBusy = null; render();
  stageInBackground();
}

/* A check that FINDS an update now starts the download, instead of reporting a
   new version and doing nothing with it.
 *
 * The gap this closes: staging was driven only by the shell's timer -- 90s after
 * launch, then every six hours -- so an operator who checked deliberately got a
 * "2.x available" pill and no download, and the only way forward was the
 * blocking "Download & install" button that quits the app. Now the check does
 * what checking implies.
 *
 * Asked of the SHELL, never done here: /api/updates/desktop/stage is
 * token-authenticated and the panel has no token (see preload.js). In a plain
 * browser window.sutra is absent, there is no app to replace, and this is
 * correctly a no-op -- the manual button remains that path's answer.
 *
 * Not awaited by the caller: a 160MB download must not block the screen. The
 * staged banner (poll of /api/updates/staged) is what announces the result, so
 * this reports only the fact that it started, and any failure honestly. */
async function stageInBackground(){
  const d = (S.upd && S.upd.desktop) || {};
  if (!d.managed || d.error || !d.update_available) return;
  if (!(window.sutra && typeof window.sutra.stageUpdate === "function")) return;
  if (S.updStaging) return;                 /* one at a time, like the shell */
  S.updStaging = true;
  S.updMsg = `Downloading ${d.latest} in the background — you can keep working.`;
  render();
  try {
    const r = await window.sutra.stageUpdate();
    S.updMsg = r && r.ok
      ? (r.staged ? `${r.version || d.latest} downloaded and verified — it installs when you restart.`
                  : `Nothing to download${r.reason ? " — " + r.reason : "."}`)
      : `Download failed${r && r.error ? " — " + r.error : "."}`;
  } catch (e) {
    S.updMsg = "Download failed — " + e.message;
  }
  S.updStaging = false;
  render();
}

async function installUpdate(which){
  S.updBusy = which; S.updError = null; S.updMsg = null; render();
  try {
    const r = await apiPost("/api/updates/" + which, {});
    S.updMsg = r.note || "Done.";
    /* Re-read rather than assuming the install moved the version: the plugin
       reports "already current" too, and claiming a move that did not happen
       is the kind of lie an operator finds out about later. */
    try { S.upd = await apiGet("/api/updates"); } catch (e) {}
  } catch (e) {
    S.updError = e.message;
  }
  S.updBusy = null; render();
}

/* v3.3 (PLAN-25 S4): the Now destination's placeholder surface. Honest empty
   state, no invented content — the founder designs this screen later. */
SCREENS.now = () => `
  <div class="zero"><h4>Now</h4>
    <p>Placeholder — the Now surface is not designed yet. Everything else in the shell is live.</p>
  </div>`;

SCREENS.settings = () => {
  if (!SETTINGS) return `<div class="zero"><h4>Settings unavailable</h4>
    <p>${esc(S.runtimeError || S.setError || "GET /api/settings has not answered.")}</p>
    ${S.runtimeError?`<p style="font-size:11px;color:var(--faint)">The registry loaded; only the
      runtime call failed, so the rest of the panel is still live. Reload to retry.</p>`:""}</div>`;
  const st = SETTINGS;
  const active = st.provider;
  const upd = updatesHtml();
  const banner = S.setError
    ? `<div class="note b"><b>The last change was refused.</b> ${esc(S.setError)}</div>`
    : S.setOk ? `<div class="note"><b>Saved.</b> ${esc(S.setOk)}</div>` : "";

  const provRow = p => `
    <button class="opt" type="button" role="radio"
        aria-checked="${active===p.id}" data-prov="${esc(p.id)}"
        ${p.runnable?"":"disabled"}
        ${S.setBusy==="prov:"+p.id?"aria-busy=\"true\"":""}>
      <span class="rd" aria-hidden="true"></span>
      <span class="oi">
        <span class="on">${esc(p.name)} <code>${esc(p.id)}</code>
          ${p.default?'<span class="pill p-mut">catalog default</span>':""}
          ${active===p.id?'<span class="pill p-ok">active</span>':""}
          ${S.setBusy==="prov:"+p.id?'<span class="pill p-acc">saving…</span>':""}</span>
        <span class="od">binary <code>${esc(p.bin)}</code>
          ${p.installed?`at <code>${esc(p.bin_path||"")}</code>`:"— not on PATH"} ·
          config <code>${esc(p.config_dir)}</code>${p.configured?"":" — absent"}</span>
        ${p.reason?`<span class="why">unavailable: ${esc(p.reason)}</span>`:""}
      </span>
    </button>`;

  /* `running` is the mode that actually reaches the spawn; `stored` is what is
     on file. They diverge when an unsafe mode was written without the
     out-of-band opt-in, and the row has to distinguish them -- labelling the
     stored value "active" is precisely the claim that was false. */
  const running = st.permission_mode_effective || st.permission_mode;
  const modeRow = m => `
    <button class="opt" type="button" role="radio"
        aria-checked="${running===m.id}" data-pmode-set="${esc(m.id)}"
        ${m.settable===false?'data-pmode-locked="1"':""}
        ${S.setBusy==="mode:"+m.id?"aria-busy=\"true\"":""}>
      <span class="rd" aria-hidden="true"></span>
      <span class="oi">
        <span class="on"><code>${esc(m.id)}</code>
          ${m.default?'<span class="pill p-mut">default</span>':""}
          ${m.writes_files?'<span class="pill p-block">writes files</span>':'<span class="pill p-ok">read-only</span>'}
          ${running===m.id?'<span class="pill p-ok">running</span>':""}
          ${st.permission_mode===m.id&&running!==m.id?'<span class="pill p-warn">on file · not honoured</span>':""}
          ${m.settable===false?'<span class="pill p-mut">locked</span>':""}
          ${S.setBusy==="mode:"+m.id?'<span class="pill p-acc">saving…</span>':""}</span>
        <span class="od">${esc(m.note||"")}</span>
        ${m.settable===false?`<span class="why">gated: the server must be started with
          <code>${esc(st.unsafe_modes_env||"SUTRA_UI_ALLOW_UNSAFE_PERM_MODES")}=1</code>
          before this can be selected.</span>`:""}
      </span>
    </button>`;

  /* Derived from what RUNS, not from what is stored. */
  const writes = (PERM_MODES.find(m=>m.id===running)||{}).writes_files;

  return `
    ${banner}
    ${upd}
    ${fold("set.prov", "Provider", esc(active||"none runnable"), `
      <p style="margin-bottom:9px">Which AI CLI this panel drives. A provider is offered only when
        its binary is on PATH, it has a config directory, <i>and</i> this build has an adapter for it;
        the others stay listed, disabled, with the exact reason — so "can I use this one?" is answered
        here rather than by a chat that fails later. Installing a CLI is not enough on its own:
        the chat channel speaks Claude's stream-json protocol.</p>
      <div role="radiogroup" aria-label="Provider">${PROVIDERS.map(provRow).join("")}</div>
      <div class="kv"><b>Resolved via</b><span>${esc(st.provider_source||"—")}${
        st.provider_stored?` · stored <code>${esc(st.provider_stored)}</code>`:""}</span></div>
      ${(st.provider_ignored||[]).length?`<div class="note b" style="margin-bottom:0">
        <b>An override was NOT honoured.</b>
        ${st.provider_ignored.map(i=>`<div><code>${esc(i.source)}</code> asked for
          <code>${esc(i.id)}</code> — ${esc(i.reason)}</div>`).join("")}</div>`:""}
      ${PROVIDERS.filter(p=>p.runnable).length<2?`<p style="font-size:11px;color:var(--faint);margin:9px 0 0">
        ${PROVIDERS.filter(p=>p.runnable).length} of ${PROVIDERS.length} catalogued providers can run on
        this machine. The rest are shown above, disabled, with their reason — never silently missing.</p>`:""}`)}

    ${fold("set.mode", "Permission mode", esc(running||"—"), `
      ${st.permission_mode_clamped?`<div class="note w"><b>The stored mode is not the one running.</b>
        <code>${esc(st.permission_mode)}</code> is on file, but sessions start as
        <code>${esc(running)}</code>. ${esc(st.permission_mode_clamp_reason||"")}
        <div style="margin-top:6px">To honour it, restart the server with
        <code>${esc(st.unsafe_modes_env||"SUTRA_UI_ALLOW_UNSAFE_PERM_MODES")}=1</code> — the gate is
        deliberately out of band, because this endpoint is unauthenticated and anything that can
        reach the port could otherwise widen the agent's authority.</div></div>`:""}
      ${writes?`<div class="note b"><b>This mode lets the agent write files without asking.</b>
        With <code>${esc(running)}</code> running, a session started from this panel can
        create, change and delete files under the workdir below — and
        <code>bypassPermissions</code> also auto-approves shell commands. Nothing will prompt you
        per edit.</div>`:`<div class="note"><b>Read-only planning.</b> The agent proposes edits and
        you approve each one. Choosing <code>acceptEdits</code> below removes that prompt.</div>`}
      <div role="radiogroup" aria-label="Permission mode">${PERM_MODES.map(modeRow).join("")}</div>`)}

    ${fold("set.workdir", "Workdir", esc((st.workdir||"").split("/").pop()||"—"), `
      <p style="margin-bottom:9px">The directory every session this panel starts uses as its
        working directory. It is created if it does not exist. A change applies to the
        <b>next</b> session — moving a running agent out from under the transcript it is
        writing is not something this panel will do to you.</p>
      <div class="wdrow">
        <input type="text" class="wdin" data-workdir-input
               value="${esc(S.workdirDraft !== null ? S.workdirDraft : (st.workdir||""))}"
               spellcheck="false" autocapitalize="off" autocorrect="off"
               aria-label="Working directory" placeholder="~/sutra-ui-workspace">
        ${dirPickerAvailable()?`<button class="btn" type="button" data-workdir-browse
          title="Choose a folder in Finder">Browse…</button>`:""}
        <button class="btn" type="button" data-workdir-save
          ${S.setBusy==="workdir"?'aria-busy="true" disabled':""}>${
            S.setBusy==="workdir"?"Saving…":"Use this directory"}</button>
      </div>
      <p style="font-size:11px;color:var(--faint);margin:7px 0 9px">Must sit inside
        <code>${esc(st.workdir_root||"~")}</code>. The chat session runs with this as its cwd, so an
        arbitrary path would turn this panel into a read oracle over the whole disk; widen the
        root with <code>SUTRA_UI_WORKDIR_ROOT</code> when starting the server if you need to.</p>
      <div class="kv"><b>In force</b><span><code>${esc(st.workdir||"—")}</code></span></div>
      <div class="kv"><b>Settings file</b><span><code>${esc(st.settings_path||"—")}</code>
        ${st.settings_file_exists?'<span class="pill p-ok">exists</span>'
                                 :'<span class="pill p-mut">not written yet</span>'}</span></div>
      ${Object.keys(st.invalid_stored_values||{}).length?`<div class="note w">
        <b>Ignored values in the settings file.</b>
        ${Object.entries(st.invalid_stored_values).map(([k,v])=>
          `<div><code>${esc(k)}</code> = <code>${esc(JSON.stringify(v))}</code></div>`).join("")}
        These were not silently corrected — the documented default is in force instead.</div>`:""}`)}`;
};

/* ── Staged department creation (§3.3). Four collapsible sections and a completion meter —
   NOT a Next/Back wizard. Nothing is minted at any step; the last step renders a CLI string. */
/* ══════════════════════ render ══════════════════════ */
const TITLES = {
  /* v3.3 (PLAN-25 S4): Now is a deliberate placeholder — the destination
     exists so the shell is complete; its surface is designed later. */
  now:["Now","placeholder — surface not designed yet"],
  connectors:["Connectors","External accounts · credentials in the OS keychain, never in this window"],
  teamsutra:["Teamsutra","~/.sutra-ui/teamsutra/t-*.json"],departments:["Departments","domains/*.json"],charters:["Charters","charters/C-<sha>.json"],
  placements:["Placements","CURRENT.jsonl"],knowledge:["Knowledge","live scan · domains · charters · placements"],
  reorg:["Reorg plans","plans/*.json"],history:["History","domains/INDEX.jsonl"],
  git:["Git","git status · log · diff — read-only, over the workdir"],
  evals:["Evals","verifier registry · nightly decay runs · findings — read-only"],
  editor:["Editor","files under the workdir — saving is gated by SUTRA_UI_ALLOW_EDIT"],
  health:["Health","lint · mece · verify-charters · stats"],
  skills:["Skills","~/.claude · ~/.codex — read at request time"],
  routines:["Routines","~/.sutra-ui/routines · launchd user agents — runs on this Mac"],
  automation:["Automation",".sutra/*.jsonl · .enforcement/*.jsonl — read-only, over the workdir"],
  settings:["Settings","~/.sutra-ui/settings.json · PATH"],
  balance:["Balance","holding/state/balance/ — not yet observing · design preview"],
  /* Registering a screen means BOTH a SCREENS entry and a TITLES one. render()
     does `const [t,src] = TITLES[S.screen]`, so a missing row here is not a blank
     header -- it is a TypeError that aborts render() before the pane is touched,
     leaving the previous screen on display as though the click did nothing. */
  usage:["Usage","api.anthropic.com/api/oauth/usage — read-only, same data as /usage"]};
/* ── a session's routing path, as a chart ──
   Honest model: the path is SUCCESSIVE PLACEMENT, not delegation. Each turn resolves to
   exactly one accountable department; departments never invoke one another (no such channel
   exists). The vertical chain is the ancestor path, which is real and is how charters are
   inherited; the numbered badges are which turn landed where. */
function routingChart(s){
  const touched = [...new Set(s.turns.filter(t=>t.domain).map(t=>t.domain.ref))];
  const back = `<button class="rt-back" type="button" data-tab="chat" data-sid="${esc(s.id)}">← back to the chat</button>`;
  if (!touched.length) return back + (s.turns.length
    ? `<div class="zero"><h4>No turn here carries a placement</h4>
        <p>Every turn in this session was read from a transcript on disk. They ran in the
        terminal, outside Sutra, so nothing classified them and there is no routing path to
        draw. Ask something below and that turn will have one.</p></div>`
    : `<p style="color:var(--faint)">No turns yet.</p>`);
  const chains = touched.map(ref=>{
    const chain=[]; let n=byRef(ref);
    while(n){ chain.unshift(n); n = n.parent_ref?byRef(n.parent_ref):null; }
    return chain;
  });
  const keep = new Set(); chains.forEach(c=>c.forEach(n=>keep.add(n.ref)));
  const roots = [...keep].map(byRef).filter(d=>!d.parent_ref||!keep.has(d.parent_ref));
  const kids = ref => [...keep].map(byRef).filter(d=>d.parent_ref===ref)
                        .sort((a,b)=>a.ts_minted_ms-b.ts_minted_ms);
  const turnsAt = ref => s.turns.map((t,i)=>({t,i})).filter(x=>x.t.domain&&x.t.domain.ref===ref);
  /* Routing UI treatment (founder to-do from 2026-08-18, done 2026-08-22):
     an indented TREE-LIST, one row per department on any turn's ancestry
     path, in the pane's own row idiom -- not an org chart swapped into the
     chat. Department rows are primary (codex: routing is ancestry; "where did
     this turn pass through"), with turn badges on the rows that own a turn and
     "passed through" on the ancestors. Same data as before; only the shape. */
  const filed = s.turns.filter(t=>t.domain).length;
  const unresolved = s.turns.filter(t=>!t.domain && !t.transcript).length;
  const rows = [];
  const walk = (d, depth) => {
    const ts = turnsAt(d.ref);
    rows.push(`<div class="rt-row ${ts.length?"hit":""}" style="--d:${depth}" data-ref="${esc(d.ref)}">
      <span class="rt-dp">${esc(dPath(d.ref))}</span>
      <span class="rt-nm">${esc(d.name)}</span>
      <span class="rt-meta">${ts.length
        ? ts.map(x=>`<span class="rt-turn" title="turn ${x.i+1} · ${x.t.mode==="floor"?"held at ancestor":"confidence "+x.t.confidence.toFixed(2)}">turn ${x.i+1}${x.t.mode==="floor"?" · held":" · "+x.t.confidence.toFixed(2)}</span>`).join("")
        : `<span class="rt-pass">passed through</span>`}</span>
    </div>`);
    kids(d.ref).forEach(k=>walk(k, depth+1));
  };
  roots.forEach(r=>walk(r, 0));
  return `<div class="rt">
    ${back}
    <div class="rt-sum">${s.turns.length} turn${s.turns.length===1?"":"s"} · ${keep.size} department${keep.size===1?"":"s"} on the path · ${filed} filed${unresolved?` · <span class="gv-unres">${unresolved} unresolved</span>`:""}</div>
    <div class="rt-tree">${rows.join("")}</div>
    <div class="legend">A row with a turn badge owns that turn. Rows marked <b>passed through</b>
      are ancestors on the path — shown because charters inherit down the chain. Departments do
      not hand work to each other: each turn was classified independently and filed to one owner.</div>
  </div>`;
}

/* ── permission mode, at chat level ─────────────────────────────────────────
   This used to live ONLY in Settings, behind an env var set when starting the
   server. For a Finder-launched .app that means editing a plist -- so the panel
   was showing a control, refusing it, and telling the operator to do something
   they realistically could not. It belongs next to the composer, where the
   decision is actually made, the way Claude Code puts it in the session.

   The dangerous modes are still not one click away: choosing one opens an
   explicit confirmation that states what it does, and only that confirmation
   sends the acknowledgement phrase the server requires. */
const UNSAFE_ACK_PHRASE = "I understand the agent will write files without asking";

function permSelect(){
  const st = SETTINGS || {};
  /* The EFFECTIVE mode, not the stored one. When consent is absent the server
     clamps at the point of use, and showing the stored value would tell the
     operator the agent is doing something it is not. */
  const cur = st.permission_mode_effective || st.permission_mode || "plan";
  const modes = PERM_MODES.length ? PERM_MODES : [{id:cur}];
  /* Derived from the EFFECTIVE mode, so the warning colour tracks what will
     actually run -- a stored-but-clamped bypassPermissions must not paint the
     composer red for a session that is really planning. */
  const writes = (modes.find(m=>m.id===cur)||{}).writes_files ? " warn" : "";
  return `<select class="permsel${writes}" data-perm aria-label="Permission mode"
      title="What the agent may do without asking — applies to the next message">
    ${modes.map(m=>`<option value="${esc(m.id)}" ${m.id===cur?"selected":""}
      >${esc(m.id)}${m.writes_files?" ⚠":""}</option>`).join("")}
  </select>`;
}

/* The confirmation. Rendered as a real block in the pane rather than a
   window.confirm: it has to SAY what the mode does, and a native dialog cannot
   carry the server's own wording for it. */
function permConfirmHtml(){
  const c = S.permConfirm;
  if (!c) return "";
  const m = (PERM_MODES.find(x=>x.id===c.mode)) || {};
  return `<div class="note b" role="alertdialog" aria-label="Confirm permission mode">
    <b>Turn on <code>${esc(c.mode)}</code>?</b>
    <p style="margin:6px 0">${esc(m.note || "This mode auto-approves agent actions.")}</p>
    <p style="margin:6px 0;color:var(--faint)">This applies to sessions this panel starts, and
      stays on until you change it back. You can withdraw it here at any time.</p>
    ${S.permError?`<p style="color:var(--block)">${esc(S.permError)}</p>`:""}
    <button class="btn" type="button" data-permok ${S.permBusy?"disabled":""}>
      ${S.permBusy?"Enabling…":"Yes, enable it"}</button>
    <button class="btn" type="button" data-permno>Cancel</button>
  </div>`;
}

async function setPermMode(mode){
  const m = PERM_MODES.find(x=>x.id===mode) || {};
  /* Only the write-capable modes need consent, and only when it is not already
     granted -- re-confirming something already on is friction with no safety. */
  if (m.writes_files && !(SETTINGS||{}).unsafe_modes_allowed){
    S.permConfirm = { mode }; S.permError = null; render(); return;
  }
  await applyPermMode(mode, false);
}

async function applyPermMode(mode, withAck){
  S.permBusy = true; S.permError = null; render();
  try {
    const body = { permission_mode: mode };
    if (withAck) body.unsafe_ack = UNSAFE_ACK_PHRASE;
    await apiPost("/api/settings", body);
    /* Re-read rather than assuming: the server clamps, and the panel must show
       what will actually run, not what was requested. */
    const s = await apiGet("/api/settings");
    SETTINGS = s.settings || SETTINGS;
    PERM_MODES = s.permission_modes || PERM_MODES;
    S.permConfirm = null;
  } catch (e) {
    S.permError = e.message;
  }
  S.permBusy = false; render();
}

/* The assistant half of a turn, rendered with the panel's OWN vocabulary — .turn .a for
   assistant prose, .pill for state, a compact tool row. Used for BOTH a live streaming
   reply and an assistant block replayed out of a transcript: in the second case
   `streaming` is false and `response` is already complete, so the same template renders
   it with no special case. */
/* The breathing Sutra mark, used wherever a turn is actively working. Inline
   SVG rather than a font glyph so it inherits currentColor and scales cleanly. */
const SPARK = '<span class="spark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
  '<path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6L5.6 18.4"/></svg></span>';

/* ── working directory, in the composer ──────────────────────────────────────
   The folder the agent runs in was previously reachable only in Settings, applied
   globally to every session at once. It belongs beside the message box for the same
   reason the permission selector does: it is a property of the turn you are about to
   send, and two sessions can legitimately want two different folders. */
function cwdLabel(p){
  const clean = (p || "").replace(/\/+$/, "");
  if (!clean) return "no folder";
  const base = clean.split("/").filter(Boolean).pop();
  return base || clean;   /* "/" has no basename; show the path itself */
}
function cwdButtonHtml(sid){
  const eff = sessCwd(sid);
  const over = !!(S.cwd && S.cwd[sid]);
  const home = (SETTINGS||{}).workdir || "";
  const title = (eff || "no working directory set")
    + (over ? "\n\nThis session only. Every other session uses " + (home || "the default") + "."
            : "\n\nFrom Settings — shared by every session.")
    + "\nClick to run this session somewhere else.";
  return `<button class="cwdbtn ${over?"over":""}" type="button" data-cwdopen="${esc(sid)}"
            aria-expanded="${S.cwdEdit===sid?"true":"false"}"
            aria-label="Working directory: ${esc(eff||"none")}. Change it."
            title="${esc(title)}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true">
        <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/></svg>
      <span class="cwdn">${esc(cwdLabel(eff))}</span>
    </button>`;
}
function cwdEditorHtml(sid){
  if (S.cwdEdit !== sid) return "";
  const eff = sessCwd(sid);
  const over = !!(S.cwd && S.cwd[sid]);
  /* The note states the CONSTRAINT rather than discovering it after a failed send:
     the server confines any agent cwd to $HOME, and a path outside it is refused
     there. Saying so here means the refusal is not a surprise. */
  const note = S.cwdError
    ? `<div class="cwdnote bad">${esc(S.cwdError)}</div>`
    : `<div class="cwdnote">Applies to the next message — the running agent cannot be
         moved, so changing this starts a new one. Must be inside your home folder.${
         over ? " Clear the box to go back to the shared default." : ""}</div>`;
  return `<div class="cwdrow">
      <input type="text" data-cwdinput="${esc(sid)}" spellcheck="false"
             value="${esc(eff)}" placeholder="~/some/project"
             aria-label="Working directory for this session" />
      ${dirPickerAvailable()?`<button type="button" data-cwdbrowse="${esc(sid)}"
        title="Choose a folder in Finder">Browse…</button>`:""}
      <button type="button" data-cwdsave="${esc(sid)}">SET</button>
      <button type="button" data-cwdcancel="${esc(sid)}">CANCEL</button>
    </div>${note}`;
}

/* ── native folder picker ─────────────────────────────────────────────────────
   The desktop shell can open Finder for the working-directory fields; a plain
   browser cannot. So the Browse buttons are drawn only when the preload bridge
   is present (mirrors updDesktop()), and the text inputs stay the sole way in
   either way -- the picker only fills them. One document-level listener,
   registered once, because the buttons ride on nodes render() rebuilds. It also
   serves the routine form's folder field rendered in 04-screens.js; wiring lives
   here because 07-loaders.js already owns the inputs and cannot be a home for a
   button gated on Electron. Guarded for the bare-vm test harness, as 08-boot.js. */
function dirPickerAvailable(){
  return typeof (window.sutra && window.sutra.pickDirectory) === "function";
}
if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", async (e)=>{
    const el = e.target;
    const t = el && el.closest && el.closest(
      "[data-workdir-browse],[data-cwdbrowse],[data-rtcwd-browse]");
    if (!t || !dirPickerAvailable()) return;
    if (t.hasAttribute("data-workdir-browse")){       /* Settings → draft, user confirms with Save */
      const inp = document.querySelector("[data-workdir-input]");
      const picked = await window.sutra.pickDirectory(
        (inp && inp.value) || (typeof SETTINGS !== "undefined" && SETTINGS && SETTINGS.workdir) || "");
      if (picked == null) return;                     /* cancelled: touch nothing */
      S.workdirDraft = picked; render();
    } else if (t.hasAttribute("data-cwdbrowse")){     /* composer → apply to this session now */
      const sid = t.dataset.cwdbrowse;
      const inp = document.querySelector('[data-cwdinput="' + sid + '"]');
      const picked = await window.sutra.pickDirectory((inp && inp.value) || sessCwd(sid) || "");
      if (picked == null) return;
      /* An explicit Finder choice is a decision — apply it (server confines it to
         $HOME, exactly like SET) rather than leaving it to be wiped by a live
         re-render before the user clicks SET. */
      setSessCwd(sid, picked); S.cwdEdit = null; S.cwdError = null; render();
    } else {                                          /* routine form → S.rtForm.cwd */
      const inp = document.querySelector('[data-rtf="cwd"]');
      const picked = await window.sutra.pickDirectory(
        (inp && inp.value) || (S.rtForm && S.rtForm.cwd) || "");
      if (picked == null) return;
      if (S.rtForm) S.rtForm.cwd = picked; render();
    }
  });
}

/* The captured agentic output: each tool call the agent made, with its command/
   input and a collapsible result (error-styled when the tool failed). Shared by
   the replayed main transcript and the subagent viewer, so both show WHAT ran and
   WHAT came back, not just a tool name. `output` toggles reuse S.toolOpen +
   data-toolout (the same handler the live tool rows use). */
function toolCallsHtml(calls){
  if (!calls || !calls.length) return "";
  return `<div class="toolcalls">${calls.map((c,i)=>{
    const key = "c:" + (c.id || (c.name + ":" + i));
    const open = S.toolOpen && S.toolOpen[key];
    const inp = c.input ? `<code class="tc-in">${esc(String(c.input))}</code>` : "";
    const out = String(c.output == null ? "" : c.output);
    const btn = out.length ? `<button class="tc-btn" type="button" data-toolout="${esc(key)}"
        aria-expanded="${open?"true":"false"}">${open?"hide":(c.is_error?"error":"output")}</button>` : "";
    const body = (out.length && open)
      ? `<pre class="tc-outbody${c.is_error?" err":""}">${esc(out)}</pre>` : "";
    return `<div class="toolcall"><span class="tc-name pill ${c.is_error?"p-block":"p-acc"}">${
        esc(c.name||"tool")}</span>${inp}${btn}${body}</div>`;
  }).join("")}</div>`;
}

/* ── governance surface (chat-surface DS port) ────────────────────────────────
   parseGov reads the model's own governance emissions (H-Sutra header, DEPTH,
   PLACEMENT, OS trace, block fences) out of a response; gvBody strips them from
   the prose so they render as the chip + panel instead of raw markdown. Pure
   string functions, no DOM — the grammar is the risky contract, kept testable.
   Anything not matched renders as body prose: raw text is never lost. */
function parseGov(text){
  const g = { verb:null, depth:null, risk:null, leaf:null, trace:null };
  const sections = [];
  if (!text) return { g, body: "", sections };
  /* the H-Sutra header "[DIRECTION·VERB · ... · RISK:x]" -- fields may follow RISK
     -- or the documented clarify form "[STAGE-1-FAIL · CLARIFY · attempt:1/1]",
     which carries no RISK at all (10 real turns) */
  const h = text.match(/^\s*\[([A-Z0-9-]+)\s*·\s*([A-Z0-9-]+)(?:[^\]]*RISK:\s*(\w+))?[^\]]*\]/);
  if (h){ g.verb = h[2]; g.risk = h[3] || null; }
  const d = text.match(/DEPTH:\s*(\d)\s*\/\s*5/); if (d) g.depth = d[1];
  const p = text.match(/PLACEMENT:[^\n|]*>\s*([^>|\n]+?)\s*\|/); if (p) g.leaf = p[1].trim();
  /* the trace is a " > " chain (985/985 real OS: lines); a bare "OS: macOS 14"
     in a bug report is not one. The lowercase form needs the spec's five fields. */
  const tr = text.match(/\n`?OS:\s*([^\n`]*\s>\s[^\n`]*)/)
          || text.match(/(?:^|\n)>\s*`?route:\s*((?:[^\n]*\s>\s){3}[^\n`]*)/)
          || text.match(/(?:^|\n)route:\s*((?:[^\n]*\s>\s){4}[^\n]*)/);
  if (tr) g.trace = tr[1].trim();

  /* ── CAPTURE, not discard (founder 2026-08-22: "I don't want anything to be
     escaped"). Every governance block the model emits -- the H-Sutra header,
     Input Routing, Depth, FLOW, BLUEPRINT, Build-Layer, Placement, Triage, the
     OS trace -- is lifted out of the body VERBATIM into `sections`, where the
     chip's panel shows it as an audit trail. The body is the reply alone.

     Shape rules (codex 2026-08-22, ADVISORY; refuter 2026-08-23 against 5.6k
     real turns):
       · a section opens on a column-0 known key. Field GROUPS (routing / depth
         / triage) need a RUN of >= 2 key lines, fenced or not, so a lone
         sentence like "TYPE: the parameter kind matters here" stays prose; a
         depth run must carry its DEPTH: line (0 real runs lack it), so a plan
         comparison's "COST: / IMPACT:" pairs are the reply's own.
       · a run directly under a prose line ending in ":" is a list the reply
         introduces ("Each line means:") -- never a block (0 real blocks do).
       · single-line markers (FLOW / PLACEMENT / OS / BUILD-LAYER family) are
         governance even alone, but carry their shape: FLOW's bracketed spine,
         PLACEMENT's D-path / "unresolved", a " > " chain on the trace. A pump
         spec's "FLOW: 3.2 L/min" stays.
       · continuation lines are captured only when INDENTED, or a BLUEPRINT
         sub-key at any indent, a BLUEPRINT "Steps:" list item, or a FLOW "[n]"
         step. A column-0 "1. ..." right after a block is the model's real
         answer and is never swallowed.
       · markdown dress ("**INPUT:**", "## BLUEPRINT", "- Doing:") is read
         through for the key test only; lines are stored as emitted.
       · a fence is captured whole, markers included, when its content passes
         the same rules; an ASCII / unicode box ("+-- FLOW --+", "╭─ FLOW ─╮")
         is captured fenced or not, when its rows carry a key, a "[n]" step or
         a D-path (a box that merely SAYS "DEPTH" over buoy soundings is not one).
       · lossless: lines are stored exactly as emitted. Derived fields above
         are the only normalisation. */
  const GROUP = {
    routing:   /^(INPUT|TYPE|EXISTING HOME|ROUTE|FIT CHECK|ACTION):/,
    depth:     /^(TASK|DEPTH|EFFORT|COST|IMPACT):/,
    triage:    /^(TRIAGE|ESTIMATE|ACTUAL):/,
    blueprint: /^BLUEPRINT\b/,
    buildLayer:/^(BUILD-LAYER|ACTIVATION-SCOPE|TARGET-PATH):/,
    flow:      /^FLOW:(?:[^\n]*\[|\s*$)/,
    placement: /^PLACEMENT:(?=[^\n]*(\bD\d|[Uu]nresolved|[Hh]eld\b|[>|]))/,
    /* "OS: a > b" or "route: a > b > c > d > e" (the spec's five fields);
       "route: the bug is here" and a breadcrumb "Home > Settings > Billing" stay */
    /* the Output Trace spec emits its line as a markdown BLOCKQUOTE --
       "> route: <skill> > <domain> > <nodes> > <terminal>" -- which is why a
       leaked one draws a left border (founder screenshot, 2026-08-23). The
       quoted form is the spec's own shape, so it needs only the spec's three
       hops; a BARE "route:" keeps the four-hop guard that spares a breadcrumb. */
    trace:     /^(`?OS:\s[^\n]*\s>\s|>\s*`?route:\s+(?:[^\n]*\s>\s){3}|route:\s+(?:[^\n]*\s>\s){4})/,
    /* the plugin's self-report line, exact prefix only (codex) */
    state:     /^Governance state:\s+plugin\b/i,
  };
  const TITLE = { header:"Header", routing:"Input routing", depth:"Depth", flow:"Flow",
                  blueprint:"Blueprint", buildLayer:"Build layer", placement:"Placement",
                  triage:"Triage", trace:"Trace", state:"Governance state", fence:"Governance" };
  const RUN_GROUPS = ["routing", "depth", "triage"];             /* need >= 2 lines */
  const bare = (l) => l.replace(/^#{1,6}\s+(?=[A-Z])/, "").replace(/^(\s*(?:[-*]\s+)?)\*\*([^*\n]+?)\*\*/, "$1$2");
  const keyOf = (l) => { l = bare(l); for (const k in GROUP) if (GROUP[k].test(l)) return k; return null; };
  const BP_SUB = /^\s*(?:[-*]\s+)?(Doing|Steps|Output looks like|Verified by|Scale|Stops if|Switch|Verify)\s*:/;
  const isSub = (l) => BP_SUB.test(bare(l));
  const isCont = (l, key, steps) => /^\s+\S/.test(l)
    || (key === "blueprint" && (isSub(l) || (steps && /^\s*(?:[-*]|\d+[.)])\s+/.test(l))))
    || (key === "flow" && /^\[/.test(l));
  const push = (key, lines) => { if (lines.length) sections.push({ key, title: TITLE[key] || key, lines: lines.slice() }); };

  /* boxes: "+-- FLOW ----+ | [1] TYPE: ... |" (the founder's 2026-08-23
     screenshot; 133 real unfenced) and the unicode "╭─ FLOW ─╮ │ ... │" */
  const BOX = /^(?:\+-+|[╭┌]─+)\s*(FLOW|BLUEPRINT|INPUT ROUTING|DEPTH|PLACEMENT|BUILD-LAYER|TRIAGE|GOVERNANCE)\b/i;
  const BOX_KEY = { flow:"flow", blueprint:"blueprint", "input routing":"routing", depth:"depth",
                    placement:"placement", "build-layer":"buildLayer", triage:"triage", governance:"fence" };
  const BOXROW = /^[|+│╭╰┌└]/;
  /* only a box ROW is read through its frame; an indented line elsewhere in a
     fence is indented, exactly as it is unfenced */
  const unbox = (l) => BOXROW.test(l) ? l.replace(/^[\s|+\-│╭╰┌└─]+/, "") : l;
  /* what a block of lines says about itself, box framing ignored */
  const evidence = (lines) => {
    const e = { marker:false, run:0, subs:0, depth:false, steps:false, dpath:false };
    const runs = {};
    for (const raw of lines){
      const l = unbox(raw);
      const k = keyOf(l);
      if (k){ if (RUN_GROUPS.includes(k)) runs[k] = (runs[k] || 0) + 1; else e.marker = true; }
      if (isSub(l)) e.subs++;
      if (/\bDEPTH:\s*\d\s*\/\s*5/.test(l)) e.depth = true;   /* the one-line depth block */
      if (/\[\d+\]/.test(l)) e.steps = true;                  /* a FLOW box row: "[1] TYPE: ..." */
      if (/\bD\d+\b/.test(l)) e.dpath = true;                  /* a PLACEMENT box row: "D0 > D3 Sutra OS" */
    }
    for (const k in runs) e.run = Math.max(e.run, runs[k]);
    return e;
  };
  const isGov = (e, boxHead) => e.marker || e.run >= 2 || e.subs >= 2 || e.depth
                              || (!!boxHead && (e.run >= 1 || e.steps || e.dpath));

  const src = text.split("\n");
  const kept = [];
  let i = 0;
  /* the H-Sutra header is the first non-blank line when present */
  if (h){
    while (i < src.length && !src[i].trim()) { kept.push(src[i]); i++; }
    push("header", [src[i]]); i++;
  }
  while (i < src.length){
    const line = src[i];
    if (/^\s*```/.test(line)){
      let j = i + 1;
      while (j < src.length && !/^\s*```/.test(src[j])) j++;
      const closed = j < src.length;
      const inner = src.slice(i + 1, j);
      const boxHead = inner.length ? inner[0].match(BOX) : null;
      const e = evidence(inner);
      /* an unterminated fence is still streaming: one routing/depth key is
         enough to hold it back until the closing marker says what it is */
      if (isGov(e, boxHead) || (!closed && e.run >= 1)){
        const first = (boxHead && BOX_KEY[boxHead[1].toLowerCase()])
                   || inner.map(l => keyOf(unbox(l))).find(Boolean) || "fence";
        push(first, src.slice(i, closed ? j + 1 : j));   /* unterminated (streaming): capture what is there */
        i = closed ? j + 1 : j; continue;
      }
      kept.push(...src.slice(i, closed ? j + 1 : src.length)); i = closed ? j + 1 : src.length; continue;
    }
    const ub = line.match(BOX);
    if (ub){
      let j = i + 1;
      while (j < src.length && BOXROW.test(src[j]) && !BOX.test(src[j])) j++;
      const rows = src.slice(i, j);
      if (isGov(evidence(rows), ub)){ push(BOX_KEY[ub[1].toLowerCase()], rows); i = j; continue; }
    }
    const key = keyOf(line);
    if (key){
      let j = i + 1;
      const lines = [line];
      let steps = false;                                   /* inside a BLUEPRINT "Steps:" list */
      while (j < src.length){
        const l = src[j];
        const k2 = keyOf(l);
        /* same family continues the run; a sibling family (routing -> depth) starts its own */
        if (k2 === key || (key === "blueprint" && isSub(l))) {
          /* a column-0 sub-key opens or closes the Steps list; an indented "Verify:" under a step does not */
          if (key === "blueprint" && !/^\s/.test(l)) steps = /^(?:[-*]\s+)?Steps\s*:/.test(bare(l));
          lines.push(l); j++; continue;
        }
        if (k2) break;
        if (isCont(l, key, steps)) { lines.push(l); j++; continue; }
        break;
      }
      const keyLines = lines.filter(l => keyOf(l) === key || (key === "blueprint" && isSub(l))).length;
      const prose = RUN_GROUPS.includes(key) && (
           keyLines < 2                                                          /* a lone sentence, not a block */
        || (i > 0 && /\S:\s*$/.test(src[i - 1]) && !keyOf(src[i - 1]))           /* an introduced list */
        || (key === "depth" && !lines.some(l => /^DEPTH:/.test(bare(l)))));      /* no DEPTH: -- the reply's own figures */
      if (prose){ kept.push(...lines); i = j; continue; }
      push(key, lines); i = j; continue;
    }
    kept.push(line); i++;
  }
  return { g, body: kept.join("\n").replace(/\n{3,}/g, "\n\n").trim(), sections };
}
/* patchStreaming (01-state.js) reaches this through window with a fallback so
   module order can never hard-fail streaming */
function gvBody(text){ return parseGov(text).body; }
if (typeof window !== "undefined") window.gvBody = gvBody;

/* The collapsed governance chip + drop-open panel for one panel-run turn.
   Chip: turn n · VERB · Dn · domain · confidence/held. Panel: the SAME honest
   placement prose, grounding charter, and trace that used to print inline —
   relocated behind one click, never reworded. Lives at .turn level, OUTSIDE
   [data-aturn], so patchTurn()/patchStreaming() never touch it mid-stream. */
function gvChipHtml(t, i){
  const open = !!(S.govOpen && t.uid && S.govOpen[t.uid]);
  const parsed = parseGov(t.response || "");
  const pg = parsed.g, secs = parsed.sections || [];
  const held = t.mode === "floor";
  const segs = [`<span>turn ${i+1}</span>`];
  if (pg.verb)  segs.push(`<span>${esc(pg.verb)}</span>`);
  if (pg.depth) segs.push(`<span>D${esc(pg.depth)}</span>`);
  if (t.domain) segs.push(`<span class="gv-leaf">${esc(t.domain.name)}</span>`);
  segs.push(t.domain
    ? `<span>${held ? "held" : esc(Number(t.confidence||0).toFixed(2))}</span>`
    : `<span class="gv-unres">unresolved</span>`);
  if (pg.risk) segs.push(`<span>risk:${esc(pg.risk.toLowerCase())}</span>`);
  const prose = !t.domain
    ? `<b style="color:var(--block)">Unresolved</b> — no department could be
       resolved, so this ran without a charter.${t.blocked?` <span style="color:var(--faint)">${esc(t.blocked)}</span>`:""}`
    : (t.blocked && !t.placement
      ? `Classified to <b style="color:var(--ink)">${esc(t.domain.name)}</b>, but
         <b style="color:var(--block)">nothing was filed</b> —
         <span style="color:var(--faint)">${esc(t.blocked)}</span>`
      : (held
        ? `No department claims this, so it was held at the nearest live ancestor rather than guessed.`
        : `Filed to <b style="color:var(--ink)">${esc(t.domain.name)}</b>${t.matched&&t.matched.length?` on <code>${t.matched.map(esc).join("</code> <code>")}</code>`:""}.`));
  return `<div class="gv ${open?"gv-open":""}">
    <button class="gv-chip" type="button" data-govopen="${esc(t.uid||"")}"
      aria-expanded="${open?"true":"false"}"
      title="Governance for this turn — click to ${open?"collapse":"expand"}">
      <span class="gv-pulse${held||!t.domain?" gv-amber":""}" aria-hidden="true"></span>
      ${segs.join(`<span class="gv-sep">·</span>`)}
      <span class="gv-chev" aria-hidden="true">▼</span>
    </button>
    ${open?`<div class="gv-panel">
      <div class="gv-row"><span class="gv-label">Placement</span><span class="gv-val">${
        t.domain?`<code>${esc(dPath(t.domain.ref))}</code> `:""}${prose}</span></div>
      ${t.charter?`<div class="gv-row"><span class="gv-label">Grounding</span><span class="gv-val">
        <span style="color:var(--acc);font-family:var(--mono);font-size:10px">${esc(t.charter.id)}</span>
        ${esc(t.charter.title)}<br><span style="font-style:italic">${esc(t.charter.purpose)}</span></span></div>`:""}
      ${pg.trace?`<div class="gv-row"><span class="gv-label">Trace</span><span class="gv-val"><code>${esc(pg.trace)}</code></span></div>`:""}
      ${secs.filter(x=>x.key!=="trace").map(x=>`<div class="gv-row"><span class="gv-label">${esc(x.title)}</span><span class="gv-val"><pre class="gv-pre">${esc(x.lines.join("\n"))}</pre></span></div>`).join("")}
    </div>`:""}
  </div>`;
}

/* ── the per-turn agent roster ───────────────────────────────────────────────
   A fan-out used to be invisible: three parallel agents produced three "Agent"
   tool rows whose only distinguishing text was an ellipsised prompt, so the
   operator could not tell which one was still running or which one failed.

   NO NEW DATA. Everything here is already in `turn.toolRuns` (01-state.js:904).
   The identity problem in particular was already solved SERVER-side:
   `_tool_summary()` (app.py:400) composes "<subagent_type>: <description>" for
   Agent/Task inputs, precisely because "every agent's prompt starts with the
   same preamble, so three parallel agents rendered as three identical rows".
   This splits that composed string back apart — it does not invent a name.

   The state ternary is the tool row's, character for character: one rule, two
   surfaces. The verdict is mapped from that state through a fixed table rather
   than read off the wire, so a subagent cannot label itself "done".

   Pure, DOM-free, and deliberately self-contained: test_governance.js extracts
   this function on its own, so it must not lean on helpers that would not
   travel with it. */
/* What this chat is about, for the pane header (founder 2026-08-23: "know
   what the chat is about", 45 words, not more). The ONLY deterministic source
   is the first user prompt -- there is no summariser, and inventing a summary
   would be fabrication -- so this is that prompt as INERT text: fences and
   their contents dropped (a pasted code block says nothing about the chat),
   whitespace collapsed, capped at 45 words AND 280 characters (codex: URL-heavy
   prompts blow past a word cap), with an ellipsis so a cut never reads as the
   whole. The server's `title` is the same prompt already cut at ~90 chars, so
   a loaded transcript's first turn is preferred when it is there. */
function sessSummary(s){
  /* refuter 2026-08-23: must be INERT (control / bidi / zero-width chars
     stripped -- the same gvClean the rows use), must not throw on odd turns,
     must not slice a surrogate pair, and a prompt that is ONLY a code block
     must fall back to the title rather than yield an empty header. A stray
     opening fence drops its marker only, never the rest of the prompt. */
  const turns = s && Array.isArray(s.turns) ? s.turns : [];
  const t0 = turns.length && turns[0] && typeof turns[0].text === "string" ? turns[0].text : "";
  const title = s && typeof s.title === "string" ? s.title : "";
  const strip = (str) => gvClean(
    String(str).replace(/```[\s\S]*?```/g, " ").replace(/^\s*```.*$/gm, " "), 100000);
  let v = strip(t0) || strip(title);
  const words = v.split(" ").filter(Boolean);
  let cut = false;
  if (words.length > 45){ v = words.slice(0, 45).join(" "); cut = true; }
  const cps = Array.from(v);                                  /* code points, not UTF-16 units */
  if (cps.length > 280){ v = cps.slice(0, 280).join("").replace(/\s+\S*$/, ""); cut = true; }
  return v + (cut ? "…" : "");
}

/* Wire text arrives from a subagent prompt or a tool input, so it is
   attacker-influenced in any session that reads untrusted content. esc() stops
   markup at render time; this stops what esc() does not: control bytes, bidi
   overrides that reverse how a line READS without changing what it says,
   newlines that turn one row into several, and unbounded length in a
   single-line row. Every surface showing wire text goes through here, so the
   rule is written once rather than once per renderer. */
function gvClean(s, cap){
  let v = String(s == null ? "" : s)
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "")
    .replace(/[\u200B-\u200F\u2028\u2029\u202A-\u202E\u2066-\u2069\uFEFF]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  /* the ellipsis is the point: a silent cut reads as the whole story */
  if (v.length > cap) v = v.slice(0, cap) + "\u2026";
  return v;
}

/* The turn's step log \u2014 what the loader opens into. Every line traces to a
   real `toolRuns` entry; nothing here is narrated, inferred or padded. A turn
   that ran no tools has no log, and the loader stays what it is today. */
function gvLog(t){
  const out = [];
  const runs = (t && t.toolRuns) || [];
  for (let i = 0; i < runs.length; i++){
    const r = runs[i];
    if (!r) continue;
    /* the same lifecycle ternary as the tool row and the roster */
    const state = r.running ? "run" : (r.ok === false ? "bad" : (r.ok === null ? "unk" : "ok"));
    const name = gvClean(r.name || "tool", 24);
    const sum = gvClean(r.summary, 96);
    out.push({ state, text: sum ? name + " \u00b7 " + sum : name });
  }
  /* Bounded. A long turn can run hundreds of tools, and an unbounded log inside
     a chat turn is a memory leak with a scrollbar. The OLDEST go: the recent
     ones are what you opened this to read. */
  const CAP = 60;
  if (out.length > CAP){
    const n = out.length - CAP;
    return [{ state: "unk", text: n + " earlier step" + (n === 1 ? "" : "s") + " not shown" }]
             .concat(out.slice(-CAP));
  }
  return out;
}

function gvAgents(t){
  const clean = gvClean;
  const VERDICT = { run:"running", bad:"error", unk:"unknown", ok:"done" };
  const out = [];
  const runs = (t && t.toolRuns) || [];
  for (let i = 0; i < runs.length; i++){
    const r = runs[i];
    /* the tool has shipped under both names */
    if (!r || (r.name !== "Agent" && r.name !== "Task")) continue;
    const raw = String(r.summary == null ? "" : r.summary);
    /* FIRST ": " only — a description may legitimately contain a colon */
    const at = raw.indexOf(": ");
    const state = r.running ? "run" : (r.ok === false ? "bad" : (r.ok === null ? "unk" : "ok"));
    const desc = clean(at > 0 ? raw.slice(at + 2) : "", 120);
    out.push({
      id: r.id || "",
      /* the kind is the bold column, so it is capped harder than the summary */
      kind: clean(at > 0 ? raw.slice(0, at) : raw, 32) || "agent",
      desc,
      state,
      verdict: VERDICT[state],
      /* a finished run is its own span; a running one is measured against now.
         No startedAt means no elapsed — 0s would be a fabricated measurement. */
      ms: typeof r.startedAt === "number"
        ? (typeof r.endedAt === "number" ? r.endedAt : Date.now()) - r.startedAt
        : null,
      /* A row is openable only if the drill-down has something to correlate on.
         agentMatch() (06-render.js) joins on description, because the roster's
         tool_use id and the fold's transcript filename are different keys. No
         id means no row identity; no description means nothing to match. Either
         way the row still SHOWS -- the work happened -- it just does not pretend
         to be a link. */
      openable: !!(r.id && desc),
    });
  }
  return out;
}

function turnResponse(t){
  const nTools = (t.tools && t.tools.length) || 0;
  if (!t.streaming && !t.response && !t.error && !nTools) return "";
  const runs = t.toolRuns || [];
  const active = runs.filter(r=>r.running).length;
  /* THE ONLY whole-turn progress surface. Was an 8.5px word in a pill: no
     elapsed time, no counts, no phase, no throughput -- a 3-second turn and a
     wedged one were the same picture. data-runstrip is the ticker's patch anchor
     (text node only); the sweep is indeterminate on purpose. */
  /* DS port: the live loader is chip-less and BOTTOMMOST (rendered last in the
     concat below); the settled verdict pill stays at the top. data-runstrip
     stays the ticker's patch anchor and still holds ONLY a text node. */
  const stateTop = t.streaming ? ""
      : (t.error ? `<span class="pill p-block">failed</span>`
         : t.stopped ? `<span class="pill p-warn">stopped by you</span>`
                 : `<span class="pill p-ok">answered</span>`);
  /* The loader becomes the button that opens the turn's step log. It already
     said the turn was working; it could not say what it was DOING, so a wedged
     turn and a busy one looked the same. The loader markup itself is unchanged
     — data-runstrip still holds ONLY a text node, so the 1s ticker keeps
     patching text and nothing else. Open state lives in S.thinkOpen[uid], the
     same in-memory, per-page-load pattern S.govOpen uses; it survives
     patchTurn() because the render reads it, and it is deliberately NOT
     persisted, because a uid means nothing after a reload. */
  const logLines = t.streaming ? gvLog(t) : [];
  const logOpen = !!(S.thinkOpen && t.uid && S.thinkOpen[t.uid]);
  const stateBottom = t.streaming
      ? `<div><button class="gv-thinkbtn" type="button" data-thinkopen="${esc(t.uid||"")}"
             aria-expanded="${logOpen?"true":"false"}" title="${logLines.length
               ? "What has run so far in this turn"
               : "Nothing has run yet in this turn"}"
           ><span class="gv-think"><span class="gv-pulse gv-beat" aria-hidden="true"></span
           ><span class="gv-tlabel">thinking</span><b class="gv-tmeta" data-runstrip="${esc(t.uid||"")}"
           >${esc(runPhrase(t))}</b></span></button>${
          logOpen
            ? `<div class="gv-log">${logLines.length
                ? logLines.map(l=>
                    `<span class="gv-ln ${l.state}">${esc(l.text)}</span>`).join("")
                /* an OPEN log must never render as nothing — a click that visibly
                   does nothing reads as a dead button (founder, 2026-08-19).
                   One honest line until the first real step arrives. */
                : `<span class="gv-ln unk">nothing has run yet in this turn</span>`}</div>`
            : ""}</div>`
      : "";
  /* A turn whose saved thread had gone and was re-sent as a new one. Stated,
     because the reply legitimately will not remember the earlier conversation
     and an operator who is not told that reads it as the model forgetting. */
  const replayed = t.retried
    ? `<span class="pill p-mut" title="${esc(t.retried)}">new thread</span>` : "";
  /* Server-measured duration and cost, stated only when the server actually sent
     them. A turn replayed from a transcript has neither, and inventing a number
     there would be fabrication. */
  const meta = (!t.streaming && (t.duration_ms != null || t.cost_usd != null
                                 || t.num_turns != null))
    ? `<span class="pill p-mut">${[
         t.duration_ms != null ? (t.duration_ms/1000).toFixed(1) + "s" : null,
         t.cost_usd != null ? "$" + Number(t.cost_usd).toFixed(4) : null,
         /* the closest thing the stream has to "how much work was that" -- the
            server sends it on every `done` and the client already stores it */
         t.num_turns != null ? t.num_turns + " turn" + (t.num_turns===1?"":"s") : null,
       ].filter(Boolean).join(" · ")}</span>` : "";

  /* toolRuns (live, with lifecycle) is preferred; `tools` (flat names, which is all a
     replayed transcript records) is the fallback. A replayed turn therefore shows what
     ran but never claims a pass/fail it does not know. */
  const tools = runs.length
    ? `<div class="toolRow">${runs.length > 12 ? `<div class="trow unk">
           <span class="tstate" aria-hidden="true"></span>
           <span class="tname">${runs.length - 12} earlier tool call${runs.length-12===1?"":"s"}</span>
           <span class="tsum">not shown</span></div>` : ""}${runs.slice(-12).map(r=>`
         <div class="trow ${r.running?"run":(r.ok===false?"bad":(r.ok===null?"unk":"ok"))}">
           <span class="tstate" aria-hidden="true"></span>
           <span class="tname">${esc(r.name)}</span>
           ${r.summary?`<span class="tsum">${esc(r.summary)}</span>`:""}
           ${r.output?`<button class="tout" type="button" data-toolout="${esc(r.id||"")}"
                        aria-expanded="${S.toolOpen&&S.toolOpen[r.id]?"true":"false"}"
                        title="Show what this tool returned">${
                          S.toolOpen&&S.toolOpen[r.id]?"hide":"output"}</button>`:""}
           ${r.command?`<button class="tout tterm" type="button" data-toolterm="${esc(r.id||"")}"
                        title="Open the terminal with this command typed in, ready to run.
It is NOT executed for you — press Enter yourself once you have read it.">terminal</button>`:""}
           ${r.caller && r.caller!=="direct"?`<span class="pill p-acc">${esc(r.caller)}</span>`:""}
           <span class="tverdict">${r.startedAt
               ? esc(fmtDur((r.endedAt || Date.now()) - r.startedAt)) + " · " : ""}${r.running ? "running"
                                   : r.ok === false ? "error"
                                   : r.ok === null ? "unknown"
                                   : "done"}</span>
         </div>${r.output && S.toolOpen && S.toolOpen[r.id]
           ? `<pre class="toutbody">${esc(r.output)}</pre>` : ""}`).join("")}</div>`
    : (t.calls && t.calls.length ? toolCallsHtml(t.calls)
       : (nTools ? `<div class="toolRow" style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">
      <span class="pill p-mut">${nTools} tool call${nTools===1?"":"s"}</span>
      ${[...new Set(t.tools)].slice(0,8).map(n=>`<span class="pill p-acc">${esc(n)}</span>`).join("")}
    </div>` : ""));
  /* The agent roster, nested under the tool rows it elaborates. A turn that
     spawned nothing renders NOTHING here — no empty container, no heading — so
     an ordinary turn's DOM is byte-identical to what it was before this shipped.
     Capped at 12 with the same "N earlier" line and the same slice(-12) the tool
     rows use: on a long fan-out, the ones still moving are the recent ones. */
  const agentRows = gvAgents(t);
  const agents = agentRows.length
    ? `<div class="gv-agents">${agentRows.length > 12 ? `<div class="trow unk">
           <span class="tstate" aria-hidden="true"></span>
           <span class="tname">${agentRows.length - 12} earlier agent${agentRows.length-12===1?"":"s"}</span>
           <span class="tsum">not shown</span></div>` : ""}${agentRows.slice(-12).map(a=>`
         <button class="trow ${a.state}" type="button"${a.openable
             ? ` data-agentrow="${esc(a.id)}" data-agkind="${esc(a.kind)}"`
               + ` data-agdesc="${esc(a.desc)}" title="Open this agent's transcript"`
             : ` disabled title="Nothing to open: this agent has no transcript to correlate with yet"`
           }><span class="tstate" aria-hidden="true"></span
           ><span class="tname">${esc(a.kind)}</span>${a.desc
             ? `<span class="tsum">${esc(a.desc)}</span>` : ""
           }<span class="tverdict">${a.ms != null
               ? esc(fmtDur(a.ms)) + " · " : ""}${a.verdict}</span></button>`).join("")}</div>`
    : "";
  /* A backoff is not a hang, and the difference has to be visible or the
     operator kills a turn that was about to succeed. */
  /* ONLY while the turn is live. `retrying` is assigned in one place and cleared
     by NO terminal branch, so a turn that hit one backoff kept an animated "Rate
     limited — retrying…" row pinned above its completed answer. */
  const retrying = (t.streaming && t.retrying)
    ? `<div class="working"><i class="dot"></i>Rate limited — retrying<b class="ell"></b>
         <span class="tsum">${esc(t.retrying)}</span></div>` : "";
  /* RETIRED. Its condition included `!runs.length`, so it was suppressed for the
     rest of the turn as soon as any tool ran -- i.e. it went away exactly during
     the compose window it was supposed to cover. The run strip now carries the
     whole live window with a stopwatch, so keeping both meant two animated
     elements per turn saying different amounts of nothing. */
  const waiting = "";
  /* data-resp is the PATCH ANCHOR. While a reply streams, patchStreaming()
     rewrites the innerHTML of exactly this node instead of letting render()
     rebuild #panes -- see scheduleStreamPatch(). The id must be stable for the
     life of the turn, which t.uid gives it (assigned once, never reused). */
  /* Emitted while STREAMING as well as when text exists. It used to require
     t.response, so on the `start` frame there was no anchor -- the first token
     of every reply missed patchStreaming(), fell through to a 100ms-debounced
     full #panes rebuild, and paid the heaviest path in the app at the exact
     moment the operator is watching for the answer to begin. An empty anchor
     costs one div and `.md[data-resp]:empty` gives it no height. */
  const body = (t.response || t.streaming)
    ? `<div class="md" data-resp="${esc(t.uid||"")}" style="margin-top:6px;color:var(--ink)">${
        t.response ? (t.streaming ? caretHtml(mdHtml(gvBody(t.response)), t)
                                  : mdHtml(gvBody(t.response))) : ""}</div>` : "";
  /* the REAL failure text, never a fabricated answer and never nothing */
  const err = t.error
    ? `<div style="margin-top:6px;color:var(--block);white-space:pre-wrap">${esc(t.error)}</div>
       ${t.interrupted && t.uid ? `<p style="margin-top:7px">
         <button class="btn" type="button" data-retry="${esc(t.uid)}">Retry this message</button>
         </p>` : ""}` : "";
  /* data-aturn anchors this block for patchTurn(): a tool frame replaces THIS
     node instead of re-rendering the pane. */
  return `<div class="a" data-aturn="${esc(t.uid||"")}"
    >${stateTop}${replayed}${meta}${tools}${agents}${retrying}${waiting}${body}${err}${stateBottom}</div>`;
}
/* One turn. Two provenances, told apart on purpose:
   - a turn the PANEL ran carries a placement (or an honest reason it has none)
   - a turn READ FROM A TRANSCRIPT carries none, because none was ever computed:
     it ran in the terminal, outside Sutra. Filling that slot with "Unresolved —
     no department could be resolved" would report a classification failure that
     never happened. */
function turnBlock(t, i){
  if (t.transcript){
    return `<div class="turn">
      ${t.orphan
        ? `<div class="a"><span class="pill p-warn">assistant message with no recorded prompt</span></div>`
        : `<div class="u md">${mdHtml(t.text)}</div>`}
      <div class="a">
        <span class="pill p-mut">turn ${i+1} · from transcript</span>
        <div style="margin-top:5px;color:var(--faint);font-size:11px">Read from
          <code>~/.claude/projects</code>. This ran in the terminal, not through this panel,
          so no placement was ever filed for it.</div>
      </div>${turnResponse(t)}</div>`;
  }
  /* DS port: the placement prose, grounding charter, and trace that used to
     print inline every turn now live behind the collapsed governance chip —
     same honest words (incl. the mode-"none"/blocked/floor branches, which
     moved verbatim into gvChipHtml), one click away instead of always-on. */
  /* data-turn-domain: the department this turn was classified into, for the
     Teamsutra selection layer. PANEL turns only — the transcript branch above
     deliberately carries none, because those ran in the terminal and nothing
     ever classified them; a selection there resolves to "no department"
     rather than to a guess. A session holds MANY placements and the pane
     header shows only the last turn's, so per-turn provenance must live here,
     on the turn itself. Empty string when classification returned nothing. */
  return `<div class="turn" data-turn-domain="${t.domain && t.domain.ref ? esc(t.domain.ref) : ""}">
    <div class="u md">${mdHtml(t.text)}</div>
    ${gvChipHtml(t, i)}${turnResponse(t)}</div>`;
}

/* Chat body. A real session that has no readable transcript gets an HONEST
   empty state naming which of the four things happened — unread, reading,
   unreadable, or genuinely empty. None of them fabricates a turn. */
function sessionBody(s){
  if (s.turns.length) return s.turns.map(turnBlock).join("");
  if (s.real){
    if (s.loadState === "loading")
      return `<p style="color:var(--muted)">Reading the transcript…</p>`;
    if (s.loadState === "error")
      return `<div class="zero"><h4>The transcript could not be read</h4>
        <p>${esc(s.loadError || "GET /api/sessions/" + s.id + " failed.")}</p>
        <p style="color:var(--faint)">The session is listed because the file exists under
        <code>~/.claude/projects</code>; nothing is shown because nothing could be parsed
        out of it. No turns have been invented to fill the gap.</p></div>`;
    /* "empty" is the read-and-found-nothing state. A session the BUSY guard in
       applySessionChange() promoted to "ok" without parsing anything lands here
       too: it has been read as far as this pane is concerned, and there are no
       turns, which is the same fact under a different label. Saying "not read
       yet" for it was the lie -- it sent the reader looking for a read that had
       already happened and would never happen again. */
    if (s.loadState === "empty" || s.loadState === "ok" || s.loadState === "live")
      return `<div class="zero"><h4>No readable turns in this transcript</h4>
        <p>The file parsed, but it holds no user or assistant messages — a session that was
        opened and abandoned, or one whose content is entirely tool traffic.</p></div>`;
    /* Genuinely unread: loadState "unread", or absent on a session built by a
       path that never set one. render() schedules the read for any open pane,
       so this is a frame or two of honesty, not a resting state. */
    return `<p style="color:var(--muted)">Transcript not read yet.</p>`;
  }
  return `<div class="zero"><h4>Nothing asked yet</h4>
    <p>Type below. The turn is classified and filed to a department before any work starts.</p></div>`;
}

