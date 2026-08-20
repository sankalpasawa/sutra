/* ── Evals (Verifier layer, 2026-08-08) ──
   Read model is /api/evals: registry counts, latest-vs-previous nightly
   scorecard, regression strip, findings tail. Lazy fetch like Git/Balance.
   Deep transcripts stay in Inspect's own viewer — the screen SHOWS the exact
   command instead of spawning a server from the panel (hardened-surface rule). */
async function loadEvals(force){
  if (S.evals && !force) return;
  S.evals = { loading: true };
  try { S.evals = await apiGet("/api/evals"); }
  catch (e){ S.evals = { present: false, error: true }; }
  render();
}
const EVCHIP = {active:"p-ok", superseded:"p-warn", quarantined:"p-block", retired:"p-warn"};
SCREENS.evals = () => {
  if (!S.evals || S.evals.loading)
    return `<p style="color:var(--muted)">Reading the verifier registry…</p>`;
  if (!S.evals.present) return `<div class="zero"><h4>No verifier registry here</h4>
    <p>This install has no <code>holding/state/verifier/registry.jsonl</code> —
    the Verifier layer has not been set up for this repo. Checks appear after
    the first <code>check_registry.py</code> build (nightly does it automatically
    where the eval program is installed).</p></div>`;
  const ev = S.evals, reg = ev.registry || {}, sc = ev.scorecard;
  const st = reg.by_status || {}, scope = reg.active_by_scope || {};
  const chips = Object.entries(st).map(([k,v]) =>
    `<span class="pill ${EVCHIP[k]||""}" title="${esc(k)}">${esc(k)} ${v}</span>`).join(" ");
  const failing = new Set(sc ? (sc.failing_ids||[]) : []);
  const regre = ev.regressions || [];
  const rows = (ev.checks||[])
    .filter(c => c.status !== "superseded" || failing.has(c.check_id))
    .sort((a,b) => (failing.has(b.check_id)?1:0)-(failing.has(a.check_id)?1:0)
                 || (a.status==="active"?-1:1)-(b.status==="active"?-1:1))
    .slice(0, 80);
  return `
  <h3 class="sec">Nightly decay ${sc?``:`<span class="pill p-warn">NO RUNS YET</span>`}</h3>
  ${sc ? `<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:8px">
    <div style="background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:10px 14px">
      <div style="font:600 8.5px/1 var(--mono);letter-spacing:.12em;color:var(--muted);margin-bottom:5px">SCORED</div>
      <div style="font-size:19px;font-weight:600">${sc.scored}</div></div>
    <div style="background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:10px 14px">
      <div style="font:600 8.5px/1 var(--mono);letter-spacing:.12em;color:var(--ok);margin-bottom:5px">PASS</div>
      <div style="font-size:19px;font-weight:600">${sc.pass}</div></div>
    <div style="background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:10px 14px">
      <div style="font:600 8.5px/1 var(--mono);letter-spacing:.12em;color:${sc.fail?"var(--warn)":"var(--muted)"};margin-bottom:5px">FAIL</div>
      <div style="font-size:19px;font-weight:600">${sc.fail}</div></div>
    ${regre.length ? `<span class="pill p-block">NEW REGRESSIONS: ${regre.length}</span>
      <span style="font:11px var(--mono);color:var(--warn)">${regre.map(esc).join(", ")}</span>`
      : `<span class="pill p-ok">no new regressions vs previous run</span>`}
    ${(ev.fixed||[]).length ? `<span class="pill p-ok">fixed since last: ${ev.fixed.length}</span>`:""}
  </div>`:""}
  <h3 class="sec">Registry</h3>
  <div style="margin-bottom:6px">${chips}
    <span style="color:var(--faint);font-size:11px;margin-left:8px">active by scope:
    ${Object.entries(scope).map(([k,v])=>`${esc(k)} ${v}`).join(" · ")}</span></div>
  <div class="tw"><table><thead><tr>
    <th>Check</th><th>Scope</th><th>Status</th><th>Lane</th><th>Goal / reason</th>
  </tr></thead><tbody>
  ${rows.map(c=>`<tr>
    <td class="k" style="${failing.has(c.check_id)?"color:var(--warn)":""}">${esc(c.check_id)}${failing.has(c.check_id)?" ✗":""}</td>
    <td>${esc(c.scope||"")}</td>
    <td><span class="pill ${EVCHIP[c.status]||""}">${esc(c.status||"")}</span>${c.superseded_by?`<span style="color:var(--faint);font-size:10px"> → ${esc(c.superseded_by)}</span>`:""}</td>
    <td style="font-size:11px;color:var(--muted)">${esc(c.tag||"")}</td>
    <td style="font-size:11.5px">${esc(c.goal||"")}${c.reason?`<span style="color:var(--faint)"> — ${esc(c.reason)}</span>`:""}</td>
  </tr>`).join("")}
  </tbody></table></div>
  <p style="color:var(--faint);font-size:10.5px;margin:4px 0 0">superseded rows hidden unless failing;
    top 80 shown of ${(ev.checks||[]).length} registry rows.</p>
  <h3 class="sec">Deep transcripts</h3>
  <div class="note">Per-case transcripts live in Inspect's own viewer. Run in a terminal:
    <code>${esc(ev.view_cmd||"")}</code></div>
  <div class="legend">Read model: check registry (declaration + binding + status), nightly
    decay lane (observe-only — it never gates), findings routed to the daily governance
    audit. Program of record: holding/plans/eval-program/VERIFIER-LEDGER.md.</div>`;
};

/* ── S8 Skills ──
   Grouped BY PROVIDER, because the entries are not interchangeable: a claude
   slash command is typed and runs; a codex SKILL.md is selected by that model
   and cannot be typed here; ~/.codex/AGENTS.md is standing instructions that
   are always loaded and never invoked at all. Flattening the three into one
   "commands" table would imply every row is runnable, and on this machine only
   the claude rows are. The per-provider header carries installed/configured and
   the server's own `note`, so a group with zero entries always says why. */
SCREENS.skills = () => {
  const q = (S.q||"").toLowerCase();
  const provs = SKILLS_META.providers || [];
  if (!provs.length && !SKILLS.length) return `<div class="zero"><h4>No capability files found</h4>
    <p>Nothing readable under any configured assistant's config directory.
    Install a plugin and reload.</p></div>`;
  const match = k => !q ||
    ((k.slash||"") + " " + (k.name||"") + " " + (k.description||"")).toLowerCase().includes(q);

  const KINDNOTE = {
    instructions: "always loaded as standing instructions — there is nothing to invoke",
    skill: "selected by the model, not typed",
    command: "typed in the composer",
    prompt: "typed in that assistant's own TUI"
  };

  const group = p => {
    const items = SKILLS.filter(k => k.provider === p.id);
    const shown = items.filter(match);
    const state = p.runnable
      ? `<span class="pill p-ok">runnable</span>`
      : `<span class="pill p-block">not runnable</span>`;
    const body = !items.length
      ? `<div class="zero" style="padding:18px 10px">
           <h4>Nothing read for ${esc(p.name)}</h4>
           <p>${esc(p.note || "no capability files")}</p></div>`
      : !shown.length
        ? `<p style="color:var(--faint);margin:0">No entry here matches “${esc(S.q)}”.</p>`
        : `<div class="tw"><table><thead><tr>
             <th>Entry</th><th>Kind</th><th>Source</th><th>Runnable</th><th>What it does</th>
           </tr></thead><tbody>
           ${shown.map(k=>`<tr>
             <td class="k">${k.slash
                 ? `<code>${esc(k.slash)}</code>`
                 : `<span style="color:var(--ink)">${esc(k.name)}</span>
                    <span class="pill p-mut">no slash</span>`}</td>
             <td>${esc(k.kind)}${k.always_loaded?' <span class="pill p-warn">always loaded</span>':""}</td>
             <td>${esc(k.source)}</td>
             <td class="whynot">${k.runnable ? `<span class="pill p-ok">yes</span>`
                   : `<span class="pill p-block">no</span>
                      <div style="font:500 9.5px/1.4 var(--mono);color:var(--faint);margin-top:3px">
                        ${esc(k.runnable_reason || KINDNOTE[k.kind] || "")}</div>`}</td>
             <td class="desc" title="${esc(k.description||"")}">${esc(k.description||"")}</td></tr>`).join("")}
           </tbody></table></div>
           <p style="margin:9px 0 0;font-size:11px;color:var(--faint)">
             ${shown.length} of ${items.length} · ${p.runnable_entries} runnable</p>`;
    return fold("skills." + p.id, p.name,
      `${items.length} entr${items.length===1?"y":"ies"}`,
      `<div class="facets" style="margin-bottom:9px">
         ${state}
         <span class="pill ${p.installed?"p-ok":"p-mut"}">binary ${p.installed?"on PATH":"missing"}</span>
         <span class="pill ${p.configured?"p-ok":"p-mut"}">config ${esc(p.config_dir)}${p.configured?"":" absent"}</span>
       </div>
       ${p.reason?`<div class="note w" style="margin-top:0"><b>Why nothing here runs.</b>
          ${esc(p.reason)}</div>`:""}
       ${p.note?`<p style="font-size:11px;color:var(--muted)">${esc(p.note)}</p>`:""}
       ${body}`,
      /* a provider with nothing to show starts folded — it is context, not content */
      items.length > 0);
  };

  return `
    <p>Every capability file each configured assistant actually exposes, read from its own
      config directory at request time — not a curated list. Only entries with a slash
      <i>and</i> a binary on PATH are offered in the composer's <code>/</code> palette.</p>
    <div class="facets">
      ${Object.entries(SKILLS_META.by_provider||{}).map(([k,n])=>
        `<span class="pill p-acc">${esc(k)} ${n}</span>`).join(" ")}
      ${Object.entries(SKILLS_META.by_kind||{}).map(([k,n])=>
        `<span class="pill p-mut">${esc(k)} ${n}</span>`).join(" ")}
      <span class="pill p-ok">${SKILLS_META.runnable==null?"—":SKILLS_META.runnable} runnable</span>
      <input type="search" id="q" placeholder="Filter entries…" value="${esc(S.q)}"
             style="margin-left:auto;width:200px">
    </div>
    ${provs.map(group).join("")}`;
};

/* ── S10 Settings ──
   Every control here acts. The provider list is the live one from
   GET /api/providers: `claude` is selectable, and the two that cannot run are
   RENDERED AND DISABLED with the server's exact `reason` beside them — not
   omitted. Hiding them would answer "can I use codex?" with silence; a
   selectable-but-broken entry would answer it with a dead websocket ten seconds
   later. Disabled-with-the-reason is the only version that answers it now. */
/* ── editor ──────────────────────────────────────────────────────────────────
   A plain <textarea>, not a syntax-highlighting editor. CodeMirror/Monaco would be
   ~300 KB of vendored JS in a project whose whole point is no build step and three
   dependencies, and it would have to be loaded from a CDN -- which the Electron
   shell may block and an offline machine certainly does. What the operator needs
   here is "read what the agent changed and fix a line", and a textarea does that.

   Saving is gated server-side (SUTRA_UI_ALLOW_EDIT). When it is off, the pane still
   OPENS files -- reading exposes nothing the chat agent, whose cwd is this same
   directory, cannot already read -- and says plainly why saving is unavailable. */
SCREENS.editor = () => {
  if (S.fsError) return `<div class="zero"><h4>Files unavailable</h4>
    <p>${esc(S.fsError)}</p></div>`;
  if (!S.fs) return `<div class="zero"><h4>Reading the workdir…</h4></div>`;

  const q = (S.fsQuery||"").toLowerCase();
  const files = S.fs.files.filter(f=>!q || f.path.toLowerCase().includes(q));
  const open = S.edFile;
  const dirty = open && S.edText !== null && S.edText !== S.edBase;

  const gate = S.fs.editable ? "" : `<div class="note w">
    <b>Saving is off.</b> This pane writes to your files and the panel is
    unauthenticated by construction, so it is gated out of band. Restart with
    <code>${esc(S.fs.edit_env||"SUTRA_UI_ALLOW_EDIT")}=1</code> to enable saving.
    Opening files still works.</div>`;

  const list = `<div class="fslist">${files.slice(0,600).map(f=>`
    <button class="opt fsf ${open===f.path?"sel":""}" type="button" data-edopen="${esc(f.path)}">
      <span class="oi"><span class="on">${esc(f.path)}</span>
      <span class="od">${fmtBytes(f.bytes)}</span></span>
    </button>`).join("")}</div>
    ${files.length>600?`<p style="font-size:11px;color:var(--faint);margin:7px 0 0">
      Showing 600 of ${files.length} matches — narrow the filter.</p>`:""}
    ${S.fs.truncated?`<p class="note w" style="margin-top:7px">The tree was truncated at
      ${S.fs.files.length} files. Files beyond that are not listed — this is a limit,
      not an empty result.</p>`:""}`;

  const pane = !open ? "" : `
    ${fold("ed.file", "Editing", esc(open), `
      <div class="edbar">
        <span class="pill ${dirty?"p-warn":"p-mut"}">${dirty?"unsaved changes":"saved"}</span>
        ${S.edBytes!=null?`<span class="pill p-mut">${fmtBytes(S.edBytes)} on load</span>`:""}
        <button class="btn" type="button" data-edsave
          ${(!dirty || !S.fs.editable || S.edBusy)?"disabled":""}>${
            S.edBusy?"Saving…":"Save"}</button>
        <button class="btn" type="button" data-edreload>Reload</button>
      </div>
      ${S.edError?`<div class="note b"><b>Not saved.</b> ${esc(S.edError)}</div>`:""}
      ${S.edOk?`<div class="note"><b>Saved.</b> ${esc(S.edOk)}</div>`:""}
      ${S.edText===null
        ? `<p style="color:var(--faint)">Reading…</p>`
        : `<textarea class="edta" data-edta spellcheck="false"
             aria-label="Contents of ${esc(open)}">${esc(S.edText)}</textarea>`}`)}`;

  return `${gate}
    ${fold("ed.files", "Files", `${files.length}`, `
      <input type="search" class="wdin" data-edfilter placeholder="Filter files…"
             value="${esc(S.fsQuery||"")}" aria-label="Filter files" style="margin-bottom:8px">
      ${files.length?list:`<p style="color:var(--faint);margin:0">No file matches
        “${esc(S.fsQuery)}”.</p>`}`)}
    ${pane}`;
};

/* ── git ─────────────────────────────────────────────────────────────────────
   READ-ONLY, and says so. The endpoints behind this expose status/log/diff and
   nothing that mutates a repository, so this screen deliberately offers no
   stage/commit/push control -- an affordance that cannot work is worse than a
   missing one. The repo is the configured workdir, never a path from here. */
/* ── S? Usage ────────────────────────────────────────────────────────────────
   The plan's rate-limit windows, from the same endpoint Claude Code's own /usage
   reads. Rendered from the server's `limits` LIST rather than from named keys:
   the list already carries a per-model row (`weekly_scoped`, e.g. "Weekly ·
   Fable") that no pair of hardcoded keys can express, and a window Anthropic adds
   later shows up here without this file learning its name.

   There is deliberately NO daily or monthly figure for the plan. The endpoint
   does not return one -- five-hour and weekly are the only rate-limit windows
   that exist. `daily` and `monthly_limit` live under extra_usage, which is
   pay-as-you-go credits and a different thing entirely; they are shown in their
   own section, and only when extra usage is actually enabled. */
/* ── usage, rendered once and shown in two places ────────────────────────────
   The full screen and the composer popover render from THESE functions, not from
   two copies of the same markup. Two renderers for one set of numbers is how a
   chip ends up saying 4% beside a panel saying 40% -- and the whole point of this
   surface is that the operator can trust the figure without checking it twice. */

/* "resets in 11 min" beats an ISO timestamp for the thing you actually want to
   know. Past-due is stated as such rather than rendered as a negative. */
function usageUntil(epoch){
  if (!epoch) return "";
  const s = epoch - Date.now()/1000;
  if (s <= 0) return "resetting now";
  if (s < 3600) return "resets in " + Math.max(1, Math.round(s/60)) + " min";
  if (s < 86400) return "resets in " + Math.round(s/3600) + "h";
  return "resets in " + Math.round(s/86400) + "d";
}
/* The guard's own thresholds (warn 70, block 80), so the colour on this chip and
   the moment tool use actually stops are the same number. A chip that turns red
   at a different point than the hook fires would be worse than no chip. */
function usageSev(pct){ return pct >= 80 ? "p-block" : pct >= 70 ? "p-warn" : "p-ok"; }

/* The window the operator is actually being metered by. `is_active` is the
   server's own flag; the first row is the fallback so a payload that marks
   nothing active still yields a number rather than a blank chip. */
function usageActive(u){
  const rows = (u && u.limits) || [];
  return rows.find(r => r.active) || rows[0] || null;
}

function usageRowsHtml(u){
  const rows = (u && u.limits) || [];
  if (!rows.length) return `<p style="color:var(--faint);margin:0">The endpoint
    returned no windows for this account.</p>`;
  return rows.map(r => `<div class="urow">
      <div class="uhead">
        <span class="ulabel">${esc(r.label)}</span>
        ${r.active?`<span class="pill p-acc" title="This is the window currently metering you">active</span>`:""}
        <span class="ureset">${esc(usageUntil(r.resets_epoch))}</span>
        <span class="upct ${usageSev(r.percent)}">${Math.round(r.percent)}%</span>
      </div>
      <div class="ubar" role="img"
           aria-label="${esc(r.label)} at ${Math.round(r.percent)} percent">
        <i class="${usageSev(r.percent)}" style="width:${Math.min(100, Math.max(0, r.percent))}%"></i>
      </div>
    </div>`).join("");
}

/* ── the repository bar ──────────────────────────────────────────────────────
   Under the composer, describing the repository THIS session is in -- which is
   the session's working directory, not the Settings workdir, or the bar would
   name one repo while the session ran in another.

   Per session, cached in S.repo[sid], because two panes can be in two different
   folders and one shared object would show whichever loaded last. */
function repoBarHtml(sid){
  const r = S.repo && S.repo[sid];
  if (r === undefined) return "";                       /* not asked yet: draw nothing */
  if (!r || !r.available){
    /* Deliberately quiet. "This folder is not a git repository" is the normal
       state for most sessions and must not look like a failure. */
    return `<div class="repobar off"><span class="rbnone">${
      esc((r && r.reason) || "no repository")}</span></div>`;
  }
  const d = r.diff || {};
  const dirty = (d.files || 0) > 0;
  const sync = [];
  if (r.ahead)  sync.push(`<span class="rbahead" title="${r.ahead} commit${r.ahead===1?"":"s"} not on ${esc(r.upstream||"the upstream")}">↑${r.ahead}</span>`);
  if (r.behind) sync.push(`<span class="rbbehind" title="${r.behind} commit${r.behind===1?"":"s"} on ${esc(r.upstream||"the upstream")} not here">↓${r.behind}</span>`);
  /* No upstream is NOT "in sync" -- there is nothing to be in sync with, and
     showing 0/0 would claim otherwise. */
  if (!r.upstream) sync.push(`<span class="rbnoup" title="This branch tracks nothing — it has never been pushed">no upstream</span>`);

  const prs = S.prs && S.prs[sid];
  const prCount = prs && prs.available ? (prs.pulls||[]).length : null;

  return `<div class="repobar">
      <span class="rbrepo" title="${esc(r.root||"")}">${esc(r.name||"repo")}</span>
      <span class="rbbranch" title="${r.upstream?("tracking "+esc(r.upstream)):"no upstream"}">${
        r.detached ? "detached HEAD" : esc(r.branch||"—")}</span>
      ${sync.join("")}
      ${dirty ? `<span class="rbdiff" title="${d.files} file${d.files===1?"":"s"} changed in the working tree, untracked files included">
          <b class="add">+${d.added}</b> <b class="rem">−${d.removed}</b></span>`
              : `<span class="rbclean">clean</span>`}
      ${r.remote ? `<button type="button" class="rbprs" data-prstoggle="${esc(sid)}"
           aria-expanded="${S.prsOpen===sid?"true":"false"}"
           title="Open pull requests on ${esc(r.remote)}">${
             /* Gated on the REMOTE, not on the loaded count. Gating on the count
                made this button unreachable: it only rendered once pull requests
                were loaded, and they only load when it is clicked. The label
                carries the number once known and reads "PRs" until then. */
             prCount != null ? prCount + " PR" + (prCount===1?"":"s") : "PRs"
           }</button>` : ""}
      ${r.remote && !r.detached ? `<button type="button" class="rbpr" data-propose-pr="${esc(sid)}"
           title="Propose a pull request — nothing is pushed or published until you approve it">Create PR</button>` : ""}
    </div>`;
}

/* The PR form. Everything it produces is a PROPOSAL -- the wording says so twice,
   in the note and on the button, because the one misreading that matters here is
   thinking the pull request now exists. */
function prFormHtml(sid){
  if (S.prDone && (!S.prForm || S.prForm.sid !== sid))
    return `<div class="prform done">
        <b>Proposal ${esc(S.prDone)} written.</b>
        <span>Nothing has been pushed and no pull request exists yet. Approve it
        under <b>Routines → Proposals</b> to push the branch and open it.</span>
        <button class="ib" type="button" data-prdone-dismiss="1" aria-label="Dismiss">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>`;
  if (!S.prForm || S.prForm.sid !== sid) return "";
  const f = S.prForm;
  return `<div class="prform">
      <div class="prfrow">
        <label>HEAD<input type="text" data-prf="head" value="${esc(f.head)}" spellcheck="false"></label>
        <label>BASE<input type="text" data-prf="base" value="${esc(f.base)}" spellcheck="false"></label>
      </div>
      <label class="prfw">TITLE<input type="text" data-prf="title" value="${esc(f.title)}"
             placeholder="what this pull request does"></label>
      <label class="prfw">BODY<textarea data-prf="body" rows="3"
             placeholder="optional">${esc(f.body)}</textarea></label>
      ${S.prError?`<div class="prfnote bad">${esc(S.prError)}</div>`:""}
      <div class="prfnote">This writes a <b>proposal</b>. It does not push and does
        not open anything — approving it under Routines pushes
        <code>${esc(f.head||"the branch")}</code> to origin and opens the pull request.</div>
      <div class="prfbtns">
        <button type="button" data-prsubmit="1" ${S.prBusy?"disabled":""}>${
          S.prBusy?"writing…":"Propose"}</button>
        <button type="button" data-prcancel="1">Cancel</button>
      </div>
    </div>`;
}

/* The PR list, opened from the bar. Same in-flow placement as the folder editor:
   a list of rows wants width, and it is read deliberately rather than glanced at. */
function prListHtml(sid){
  if (S.prsOpen !== sid) return "";
  const p = S.prs && S.prs[sid];
  if (!p) return `<div class="prlist"><p class="prnone">Reading pull requests…</p></div>`;
  if (!p.available)
    return `<div class="prlist"><p class="prnone">${esc(p.reason||"unavailable")}</p></div>`;
  if (!(p.pulls||[]).length)
    return `<div class="prlist"><p class="prnone">No open pull requests.</p></div>`;
  return `<div class="prlist">${p.pulls.map(pr=>`
      <div class="prrow">
        <span class="prnum">#${pr.number}</span>
        <span class="prt" title="${esc(pr.title)}">${esc(pr.title)}</span>
        <span class="prbr" title="${esc(pr.head)} → ${esc(pr.base)}">${esc(pr.head)}</span>
        <span class="pill ${pr.draft?"p-mut":"p-ok"}">${pr.draft?"draft":esc(pr.state||"open")}</span>
      </div>`).join("")}</div>`;
}

/* ── the composer chip ───────────────────────────────────────────────────────
   Usage belongs next to the message you are about to send, not behind a nav
   click: the number matters at the moment you decide whether to send, and a
   screen you have to navigate to is a screen you check after it mattered.

   It renders even when usage is UNAVAILABLE, as a muted "—". A chip that
   disappears on failure teaches the operator that no chip means no problem,
   which is exactly wrong when the reason is a dead network. */
function usageChipHtml(){
  const u = S.usage;
  if (u && !u.available)
    return `<button class="uchip off" type="button" data-usagepop="1"
              aria-expanded="${S.usagePop?"true":"false"}"
              title="Usage unavailable — ${esc(u.reason||"no data")}"
              aria-label="Plan usage unavailable">—</button>`;
  const a = u ? usageActive(u) : null;
  if (!a) return `<button class="uchip off" type="button" data-usagepop="1"
              aria-expanded="${S.usagePop?"true":"false"}"
              title="Plan usage — not read yet" aria-label="Plan usage">…</button>`;
  const pct = Math.round(a.percent);
  return `<button class="uchip ${usageSev(a.percent)}" type="button" data-usagepop="1"
            aria-expanded="${S.usagePop?"true":"false"}"
            title="${esc(a.label)} — ${pct}% used${
              a.resets_epoch?", "+esc(usageUntil(a.resets_epoch)):""}\n\nClick for every window."
            }" aria-label="Plan usage: ${esc(a.label)} at ${pct} percent">
      <span class="uring" style="--p:${Math.min(100,Math.max(0,pct))}"></span>
      <span class="uchipn">${pct}%</span>
    </button>`;
}

/* The popover. Anchored above the composer, same rows as the screen. */
function usagePopHtml(){
  if (!S.usagePop) return "";
  const u = S.usage;
  const body = !u
    ? `<p style="color:var(--faint);margin:0">Reading usage…</p>`
    : !u.available
      ? `<p style="margin:0">${esc(u.reason||"No usage data.")}</p>
         <p style="margin:6px 0 0;font-size:10.5px;color:var(--faint)">This reads the
         same endpoint as <code>/usage</code> in the CLI, using the Claude Code
         credentials on this machine.</p>`
      : usageRowsHtml(u);
  const stale = u && u.source === "stale-cache"
    ? `<div class="upopnote w">Endpoint unreachable — cached figures, up to 10 min old.</div>` : "";
  return `<div class="upop" role="dialog" aria-label="Plan usage">
      <div class="upophead">
        <b>Plan usage</b>
        <button class="ib" type="button" data-usageclose="1" aria-label="Close">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.2" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
      ${stale}
      <div class="upopbody">${body}</div>
      <div class="upopnote">Five-hour and weekly are the only rate-limit windows the
        endpoint reports — there is no daily or monthly figure for the plan.</div>
    </div>`;
}

SCREENS.usage = () => {
  if (S.usageError) return `<div class="zero"><h4>Usage unavailable</h4>
    <p>${esc(S.usageError)}</p></div>`;
  if (!S.usage) return `<div class="zero"><h4>Reading usage…</h4></div>`;
  const u = S.usage;
  if (!u.available) return `<div class="zero"><h4>Usage unavailable</h4>
    <p>${esc(u.reason || "no usage data")}</p>
    <p style="font-size:11px;color:var(--faint)">This reads the same endpoint as
    <code>/usage</code> in the CLI, using the Claude Code credentials on this
    machine. No credentials are sent to this panel.</p></div>`;

  const rows = usageRowsHtml(u);

  const x = u.extra_usage;
  const extra = !x
    ? `<p style="color:var(--faint);margin:0">Not reported for this account.</p>`
    : !x.enabled
      /* NOT rendered as zeros. A null limit means "none configured", and showing
         that as 0 would read as "you have no allowance left" -- the opposite. */
      ? `<p style="margin:0">Extra usage is <b>off</b>. Daily, weekly and monthly
         figures only exist once pay-as-you-go credits are enabled — they are
         <code>null</code> right now, not zero.</p>`
      : `<div class="kv"><b>Used</b><span>${esc(String(x.used_credits ?? "—"))} ${esc(x.currency||"")}</span></div>
         <div class="kv"><b>Daily</b><span>${esc(String(x.daily ?? "no limit set"))}</span></div>
         <div class="kv"><b>Weekly</b><span>${esc(String(x.weekly ?? "no limit set"))}</span></div>
         <div class="kv"><b>Monthly limit</b><span>${esc(String(x.monthly_limit ?? "no limit set"))}</span></div>
         ${x.limit_reached?`<div class="note w" style="margin-top:7px">The spend limit has been reached.</div>`:""}`;

  const age = u.source === "stale-cache"
    ? `<div class="note w" style="margin-bottom:9px">The usage endpoint could not be
       reached just now. These figures come from a cached response and may be up to
       10 minutes old.</div>` : "";

  return `${age}
    <div class="note" style="margin-bottom:9px"><b>Read-only.</b> The same data as
      <code>/usage</code> in the CLI, for the account whose Claude Code credentials
      are on this machine. Shared cache with <code>sutra-usage</code>, so the guard
      and this screen can never disagree.</div>

    ${fold("usage.limits", "Plan limits", `${(u.limits||[]).length} windows`, rows)}

    ${fold("usage.extra", "Extra usage (pay-as-you-go)", x && x.enabled ? "on" : "off", extra)}

    <p class="note" style="margin-top:9px;font-size:11px;color:var(--faint)">
      There is no daily or monthly figure for the plan itself — five-hour and weekly
      are the only rate-limit windows the endpoint returns.</p>`;
};

SCREENS.git = () => {
  if (S.gitError) return `<div class="zero"><h4>Git unavailable</h4>
    <p>${esc(S.gitError)}</p>
    <p style="font-size:11px;color:var(--faint)">The repository is the workdir set in
    Settings. Point it at a git checkout to use this screen.</p></div>`;
  if (!S.git) return `<div class="zero"><h4>Reading the repository…</h4></div>`;

  const st = S.git.status || {};
  const files = st.files || [];
  const sel = S.gitFile;
  const CODE = {M:"modified", A:"added", D:"deleted", R:"renamed", C:"copied", "?":"untracked", U:"conflicted"};
  const label = f => CODE[(f.y !== " " ? f.y : f.x)] || "changed";

  const row = f => `<button class="opt gitf ${sel===f.path?"sel":""}" type="button"
      data-gitfile="${esc(f.path)}">
      <span class="gcode ${f.y==="?"||f.x==="?"?"new":""}">${esc((f.x+f.y).trim()||"?")}</span>
      <span class="oi"><span class="on">${esc(f.path)}</span>
      <span class="od">${esc(label(f))}${f.x!==" "&&f.x!=="?"?" · staged":""}</span></span>
    </button>`;

  const diff = S.gitDiff == null
    ? (sel ? `<p style="color:var(--faint)">Reading diff…</p>` : "")
    : (S.gitDiff.trim()
        ? `<pre class="diff">${diffHtml(S.gitDiff)}</pre>${
            S.gitDiffTruncated?`<p class="note w" style="margin-top:6px">This diff was
            truncated at 400 KB. What is shown is the beginning of the real diff, not a
            summary of it.</p>`:""}`
        : `<p style="color:var(--faint)">No unstaged changes in this file. It may be
           staged already — this view shows the working tree against the index.</p>`);

  return `
    <div class="note" style="margin-bottom:9px"><b>Read-only.</b> This screen runs
      <code>git status</code>, <code>log</code> and <code>diff</code> against
      <code>${esc(S.git.repo || "—")}</code>. There is no stage, commit or push here:
      those write, and writes are gated separately.</div>

    ${fold("git.files", "Working tree", `${files.length} changed`, files.length
      ? `<div class="kv"><b>Branch</b><span><code>${esc(st.branch||"—")}</code></span></div>
         <div role="list" style="margin-top:7px">${files.map(row).join("")}</div>`
      : `<p style="color:var(--faint);margin:0">Nothing changed. The working tree is
         clean relative to the index.</p>`)}

    ${sel ? fold("git.diff", "Diff", esc(sel), diff) : ""}

    ${fold("git.log", "Recent commits", `${(S.git.commits||[]).length}`, (S.git.commits||[]).length
      ? `<div class="tw"><table><thead><tr><th>Commit</th><th>When</th><th>Author</th><th>Subject</th></tr></thead>
         <tbody>${S.git.commits.map(c=>`<tr>
           <td class="k"><code>${esc(c.short)}</code></td>
           <td>${esc(c.when)}</td><td>${esc(c.author)}</td>
           <td class="desc" title="${esc(c.subject)}">${esc(c.subject)}</td></tr>`).join("")}
         </tbody></table></div>`
      : `<p style="color:var(--faint);margin:0">No commits read.</p>`)}`;
};

/* ── S8b Automation ──
   The dispatcher and the scheduler, and they are NOT the same kind of thing:

     Dispatcher  has real state. bin/sutra-dispatch and bin/sutra-atom append
                 ledgers under <workdir>/.sutra/, the gate hooks append verdicts
                 under <workdir>/.enforcement/. This reads them; it never writes.

     Scheduler   has none. Cadence is a daemon-side tick in the Native engine
                 (ADR-017 -- deliberately not OS cron/launchd), the daemon is not
                 running in this install, and the v1.0 scheduler does not evaluate
                 cron expressions at all. So this reports LIVENESS and says why
                 there is nothing else to report.

   The distinction is the point. A "Cron" table showing "0 runs today" would be a
   claim that a scheduler ran and found nothing to do. Nothing ran. */
SCREENS.automation = () => {
  if (S.autoError) return `<div class="zero"><h4>Automation unavailable</h4>
    <p>${esc(S.autoError)}</p></div>`;
  if (!S.auto) return `<div class="zero"><h4>Reading…</h4>
    <p>${esc(TITLES.automation[1])}</p></div>`;

  const a = S.auto, d = a.dispatcher || {}, sch = a.scheduler || {};
  const led = d.ledger || {}, atoms = d.atoms || {}, gate = d.gate || {};

  const tally = obj => {
    const ks = Object.keys(obj || {});
    return ks.length ? ks.sort().map(k=>
      `<span class="pill p-mut">${esc(k)} ${obj[k]}</span>`).join(" ") : "";
  };

  /* A file that is not there and a file that is there and empty are different
     facts, and only the second one means "nothing has been dispatched". */
  const source = (label, o) => `<div class="kv"><b>${esc(label)}</b>
    <span><code>${esc(o.path||"")}</code> · ${o.rows
      ? `<b>${o.rows}</b> row${o.rows===1?"":"s"}`
      : `<span style="color:var(--faint)">no rows</span>`}</span></div>`;

  const rows = (list, cols) => !list || !list.length ? "" : `
    <div class="tw"><table><thead><tr>${cols.map(c=>`<th>${esc(c[0])}</th>`).join("")}</tr></thead>
      <tbody>${list.slice().reverse().map(r=>`<tr>${cols.map(c=>{
        const v = c[1](r);
        return `<td>${v===undefined||v===null||v===""
          ? '<span style="color:var(--faint)">—</span>' : esc(String(v))}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table></div>`;

  const dispatched = (led.rows||0) + (atoms.rows||0) + (gate.rows||0);

  return `
    <div class="facets">
      <span class="fl">Workdir</span><code>${esc(a.root||"—")}</code>
      ${a.root_exists ? "" : `<span class="pill p-block" style="margin-left:auto">does not exist</span>`}
    </div>

    <section class="chsec"><h2 class="chh">Dispatcher</h2>
      ${source("Dispatch ledger", led)}
      ${source("Atom ledger", atoms)}
      ${source("Gate verdicts", gate)}
      ${led.too_large?`<div class="note w"><b>Ledger too large to read.</b>
        It is past the size this screen will walk, so no rows are shown rather than
        a partial tail presented as the whole.</div>`:""}
      ${dispatched ? `
        ${tally(led.kinds) ? `<p style="margin:9px 0 4px">${tally(led.kinds)}</p>` : ""}
        ${tally(gate.verdicts) ? `<p style="margin:4px 0 9px">${tally(gate.verdicts)}</p>` : ""}
        ${rows(led.recent, [["Kind",r=>r.kind],["Unit",r=>r.unit||r.atom_id],
                            ["Class",r=>r.class],["Model",r=>r.model],
                            ["When",r=>r.ts?fmt(r.ts*1000):""]])}
        ${rows(gate.recent, [["Verdict",r=>r.verdict],["Reason",r=>r.reason],
                             ["Tool",r=>r.tool],["Target",r=>r.target],
                             ["When",r=>r.ts?fmt(r.ts*1000):""]])}`
      : `<div class="zero"><h4>Nothing dispatched here</h4>
          <p>No dispatch, atom or gate rows under <code>${esc(a.root||"")}</code>.
             These files are written by the gate hooks in whatever project the agent
             runs in — this is the configured workdir, which may simply not be that
             project. Nothing is inferred from their absence.</p></div>`}
    </section>

    <section class="chsec"><h2 class="chh">Cron / scheduler</h2>
      <div class="kv"><b>Daemon</b><span>${sch.daemon_running
        ? '<span class="pill p-ok">running</span>'
        : '<span class="pill p-mut">not running</span>'} · <code>${esc(sch.pid_file||"")}</code></div>
      <div class="kv"><b>Ready</b><span>${sch.ready
        ? '<span class="pill p-ok">yes</span>' : '<span class="pill p-mut">no</span>'}</span></div>
      <div class="kv"><b>Triggers</b><span>${sch.triggers_dir_exists
        ? `<b>${(sch.triggers||[]).length}</b> in <code>${esc(sch.triggers_dir||"")}</code>`
        : `<span style="color:var(--faint)">no trigger store at</span> <code>${esc(sch.triggers_dir||"")}</code>`}</span></div>
      <div class="note"><b>There is no cron here, and that is the finding.</b>
        ${esc(sch.note||"")}</div>
    </section>`;
};

/* ── S8c Routines ──
   Local scheduled tasks. Claude Code calls the umbrella noun "Routines" and
   offers Local vs Cloud; only Local is something this panel can honestly own,
   so that is the badge. The five schedule presets are Claude's own
   (Manual / Hourly / Daily / Weekdays / Weekly) plus a custom cron escape.

   The honesty rules this screen follows, all of them because the alternative is
   a plausible lie:
     - never "0 runs" -- "never run" and "ran and produced nothing" differ
     - a green Run now proves the RUNNER, not the schedule; say so
     - saved-but-not-loaded is not "scheduled"; show launchd's own stderr
     - next-run is NOT computed here: launchd decides, and a number we invented
       would be wrong the first time the Mac slept */
function rtPresetForm(f){
  const P = [["manual","Manual"],["hourly","Hourly"],["daily","Daily"],
             ["weekdays","Weekdays"],["weekly","Weekly"],["custom","Custom cron"]];
  const DAYS = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
  const needsTime = ["daily","weekdays","weekly"].includes(f.preset);
  /* The controls that make up ONE schedule stay on one line: a preset, a time and
     a day are a single thought, and stacking them full-width read as three
     unrelated fields. */
  const hint = {
    manual:"Never fires on its own — you run it from here.",
    hourly:"Every hour, at the minute you choose.",
    daily:"Every day, including weekends.",
    weekdays:"Monday to Friday only.",
    weekly:"Once a week, on the day you choose.",
    custom:"Five-field cron, local time. At most one run per hour."
  }[f.preset] || "";
  return `<div class="rfrow"><label for="rf-preset">Schedule</label><div class="rfield">
    <div class="rinline">
      <select id="rf-preset" data-rtf="preset">${P.map(([v,n])=>
        `<option value="${v}" ${f.preset===v?"selected":""}>${n}</option>`).join("")}</select>
      ${f.preset==="hourly"?`<span class="sep">at :</span>
        <input data-rtf="minute" style="width:66px" inputmode="numeric"
               value="${esc(String(f.minute??0))}" aria-label="Minute past the hour">`:""}
      ${needsTime?`<input data-rtf="hour" style="width:66px" inputmode="numeric"
          value="${esc(String(f.hour??9))}" aria-label="Hour (24h)">
        <span class="sep">:</span>
        <input data-rtf="minute" style="width:66px" inputmode="numeric"
          value="${esc(String(f.minute??0))}" aria-label="Minute">`:""}
      ${f.preset==="weekly"?`<select data-rtf="weekday" aria-label="Day of week"
        >${DAYS.map((d,i)=>`<option value="${i}"
          ${String(f.weekday??1)===String(i)?"selected":""}>${d}</option>`).join("")}</select>`:""}
      ${f.preset==="custom"?`<input data-rtf="cron" style="flex:1;min-width:180px"
          placeholder="0 9 * * 1-5" value="${esc(f.cron||"")}" aria-label="Cron expression">`:""}
    </div>
    <span class="hint">${esc(hint)}${needsTime?" 24-hour clock, this Mac's local time.":""}</span>
  </div></div>`;
}

function rtCreateForm(){
  const f = S.rtForm; if (!f) return "";
  const st = S.rt || {};
  const row = (id,label,control,hint) => `<div class="rfrow">
    <label for="rf-${id}">${esc(label)}</label>
    <div class="rfield">${control}${hint?`<span class="hint">${hint}</span>`:""}</div></div>`;
  return `<section class="chsec" style="margin-bottom:14px">
    <h2 class="chh">New routine <span class="pill p-mut">Local</span></h2>
    <p style="margin:0 0 10px;color:var(--muted);font-size:11.5px;max-width:70ch">
      Runs on this Mac, on a schedule, with nobody watching. It is not a cloud
      routine and does not run while the Mac is off.</p>
    ${S.rtError?`<div class="note b" style="white-space:pre-wrap">${esc(S.rtError)}</div>`:""}
    <div class="rform">
      ${row("id","Name",
        `<input id="rf-id" data-rtf="id" placeholder="morning-brief"
                spellcheck="false" autocapitalize="off" value="${esc(f.id||"")}">`,
        "Lower-case with dashes. Also the folder name and the launchd label.")}
      ${row("description","Description",
        `<input id="rf-description" data-rtf="description"
                placeholder="What changed in sutra since yesterday"
                value="${esc(f.description||"")}">`,
        "One line. This is what makes a list of routines scannable.")}
      ${row("prompt","Instructions",
        `<textarea id="rf-prompt" data-rtf="prompt"
           placeholder="What Sutra should do on each run">${esc(f.prompt||"")}</textarea>`,
        "What Sutra runs on each fire. Drag the corner to make it taller.")}
      ${row("cwd","Working folder",
        `<div class="rfpick"><input id="rf-cwd" data-rtf="cwd" placeholder="~/some/project"
                spellcheck="false" value="${esc(f.cwd||"")}">${
          dirPickerAvailable()?`<button class="btn" type="button" data-rtcwd-browse
            title="Choose a folder in Finder">Browse…</button>`:""}</div>`,
        "Must exist, and be inside your home directory.")}
      ${row("model","Model",
        `<select id="rf-model" data-rtf="model">${(st.models||[""]).map(m=>
          `<option value="${esc(m)}" ${f.model===m?"selected":""}
            >${m||"CLI default"}</option>`).join("")}</select>`, "")}
      ${row("permission_mode","Permission",
        `<select id="rf-permission_mode" data-rtf="permission_mode">${
          (st.permission_modes||["dontAsk"]).map(m=>`<option value="${esc(m)}"
            ${f.permission_mode===m?"selected":""}>${esc(m)}</option>`).join("")}</select>`,
        "A routine runs unattended, so the modes that write files without asking " +
        "are not offered here at all.")}
      ${row("max_budget_usd","Budget",
        `<div class="rinline"><span class="sep">$</span>
          <input id="rf-max_budget_usd" data-rtf="max_budget_usd" style="width:96px"
                 inputmode="decimal" value="${esc(String(f.max_budget_usd??1))}"></div>`,
        "Per run. A schedule with no ceiling is how it becomes a bill.")}
      ${rtPresetForm(f)}
    </div>
    <div class="rfoot">
      <button class="btn" type="button" data-rtsave ${S.rtBusy?"disabled":""}>
        ${S.rtBusy==="create"?"Creating…":"Create routine"}</button>
      <button class="btn" type="button" data-rtcancel>Cancel</button>
    </div>
  </section>`;
}

/* ── Teamsutra: the task board ────────────────────────────────────────────
   Tasks filed from the Ask Sutra chat. The worker is READ-ONLY — a finished
   task carries a unified diff a human reads and applies; nothing on this
   screen edits code. Mutations (queue/drop/release) are desktop-token-gated
   server-side, so in a browser-served panel the buttons render disabled with
   the reason instead of failing with a bare 403. */
function tsStatusPill(st){
  const cls = { draft:"p-mut", queued:"p-acc", claimed:"p-warn",
                needs_review:"p-acc", blocked:"p-warn", failed:"p-err",
                done:"p-ok", dropped:"p-mut", corrupt:"p-err" }[st] || "p-mut";
  return `<span class="pill ${cls}">${esc(st)}</span>`;
}
function tsCanAct(){ return !!(window.sutra && window.sutra.teamsutraAction); }
function tsCard(t){
  const src = t.source || {};
  const dept = src.domain_name ? `${esc(src.domain_path||"")} ${esc(src.domain_name)}` : "no department";
  const acts = [];
  if (t.status === "draft")   acts.push(`<button data-tsact="queue" data-tid="${esc(t.id)}">Queue</button>`);
  if (t.status === "claimed") acts.push(`<button data-tsact="release" data-tid="${esc(t.id)}">Release</button>`);
  if (t.status === "needs_review" && t.diff)
    acts.push(`<button data-tsact="apply" data-tid="${esc(t.id)}">Apply</button>`);
  if (!["done","dropped","corrupt"].includes(t.status))
    acts.push(`<button data-tsact="drop" data-tid="${esc(t.id)}">Drop</button>`);
  const gate = tsCanAct() ? "" :
    `<div style="color:var(--faint);font-size:11px;margin-top:4px">queue actions need the desktop app — this panel was started from the CLI</div>`;
  return `<div class="card" style="margin-bottom:8px">
    <div style="display:flex;gap:8px;align-items:baseline">
      ${tsStatusPill(t.status)}
      <strong>${esc(t.title||"")}</strong>
      <span style="color:var(--faint);font-size:11px">${esc(t.id)} · ${esc(dept)} · attempt ${t.attempts||0}/${t.max_attempts||3}</span>
    </div>
    ${t.blocked_reason ? `<div style="color:var(--warn);font-size:12px;margin-top:4px">blocked: ${esc(t.blocked_reason)}</div>` : ""}
    ${t.last_error ? `<div style="color:var(--block);font-size:12px;margin-top:4px">${esc(t.last_error)}</div>` : ""}
    ${t.pr_url ? `<div style="font-size:12px;margin-top:4px"><a href="${esc(t.pr_url)}" target="_blank" rel="noopener">PR open — merge on GitHub →</a></div>` : ""}
    ${t.apply_error ? `<div style="color:var(--block);font-size:12px;margin-top:4px">apply failed: ${esc(t.apply_error)} — fix and press Apply again</div>` : ""}
    ${t.diff ? `<details style="margin-top:6px"><summary>the proposed change (${(t.diff.match(/^[+-]/gm)||[]).length} changed lines) — review before applying</summary>
        <pre class="md-pre" style="max-height:340px;overflow:auto">${esc(t.diff)}</pre></details>` : ""}
    <div style="margin-top:6px;display:flex;gap:6px">${tsCanAct() ? acts.join("") : ""}</div>
    ${gate}
  </div>`;
}
SCREENS.teamsutra = () => {
  if (S.tsError) return `<p style="color:var(--block)">${esc(S.tsError)}</p>`;
  if (!S.ts) return `<p style="color:var(--muted)">Reading the task store…</p>`;
  const rows = S.ts.tasks || [];
  if (!rows.length) return `<div class="info">No tasks yet. Select text anywhere
    in the panel and click <strong>Ask Sutra</strong> — the chat can file what
    you find as a task. A filed task sits as a draft until you queue it here;
    the hourly worker then picks it up and returns a change for your review.</div>`;
  return rows.map(tsCard).join("");
};
