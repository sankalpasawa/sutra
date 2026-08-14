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

/* ── S8b2 Connectors ──
   ONE connector: Composio's tool router. The panel used to model a connector as
   "an MCP server the operator hand-configures", with a 50-entry preset gallery
   and a search over the open MCP registry -- which made the operator responsible
   for finding a server, installing it, and pasting its secrets, per service,
   forever. Composio inverts that: one session, one endpoint, and every toolkit
   enabled on it is reachable through it.

   So this screen has exactly three things on it, in the order they must happen:
     1. the account   -- an API key and a user id, or nothing else works
     2. what is ON    -- the enabled toolkits, and the live session's health
     3. the catalog   -- 1181 apps to search, each a one-click enable

   Per-toolkit OAuth is deliberately ABSENT: the session exposes Composio's
   connection manager, so the agent hands you an auth link in-browser the first
   time it touches a toolkit you have not connected. A second login flow here
   would be a second thing to keep correct for no gain. */
SCREENS.connectors = () => {
  const c = S.conn, err = S.connError;

  /* Two connectors, and the screen says which is which up front, because they
     differ in the one way that decides which you want: where the tool RUNS. */
  const explain = `<p>External tools available to the sessions this panel starts. Two connectors,
    both aggregated — one entry each in every session's MCP config, however many services
    are behind them:</p>
    <table class="conn-kinds"><tbody>
      <tr><td><b>Hosted</b> · Composio</td><td>1000+ SaaS toolkits, run on Composio's
        infrastructure, authenticated once</td></tr>
      <tr><td><b>Local</b> · 1MCP</td><td>MCP servers that run on <i>this machine</i> —
        files, git, browsers, databases</td></tr>
    </tbody></table>
    <p>They run under the session's permission mode — use <b>Accept Edits</b> or <b>Bypass</b>
    to let them act.</p>`;

  /* Not read yet vs read-and-empty are different facts (Git rule). Only the first
     is "Reading…"; the second is the not-configured state inside connAccount. */
  if (c == null && !err) return `${explain}<div class="zero"><h4>Reading…</h4>
    <p>${esc(TITLES.connectors[1])}</p></div>`;

  const notice = S.connMsg ? `<div class="note"><b>${esc(S.connMsg)}</b></div>` : "";
  /* A load failure is reported WITHOUT throwing: the form still renders so the
     operator can retry, and the notice says what failed. */
  const loadErr = err ? `<div class="note b"><b>Could not read connectors.</b> ${esc(err)}</div>` : "";

  return `${explain}${notice}${loadErr}
    <h2 class="chh conn-kind-h">Hosted — Composio</h2>
    ${connAccount(c || {})}
    ${connEnabled(c || {})}
    ${connCatalog(c || {})}
    <h2 class="chh conn-kind-h">Local — 1MCP aggregator</h2>
    ${lcSection()}`;
};

/* ── the LOCAL half ──
   One 1MCP process fronts every enabled local server, so the session sees one
   `local` namespace instead of one per server. Everything here is assorted by
   TAG -- which is 1MCP's own per-server field, not a label this screen keeps to
   itself: the groups below are the same strings `--filter` narrows on.

   Preflight is rendered BEFORE anything else can be enabled. A connector that
   says "enabled" on a machine with no Node fails as "the tools just are not
   there", three turns later, with nothing on screen explaining why. */
function lcSection(){
  const L = S.local;
  if (L == null && !S.localError) return `<div class="zero"><h4>Reading…</h4>
    <p>local MCP servers, behind one aggregator</p></div>`;
  if (S.localError) return `<div class="note b"><b>Could not read local servers.</b>
    ${esc(S.localError)}</div>`;

  const pf = L.preflight || {};
  const blocked = !pf.runnable
    ? `<div class="note b"><b>This machine cannot run the aggregator.</b> ${esc(pf.reason||"")}
       — install Node.js, then press Re-read. Servers you add are kept; they simply
       will not reach a session until Node is present.</div>` : "";

  return `${blocked}${lcOptions(L)}${lcGroups(L)}${lcAddForm()}${lcRegistry(L)}`;
}

/* The aggregator's own row: what version is pinned, what it fronts, and the two
   knobs that change what it exposes rather than what is in it. */
function lcOptions(L){
  const a = L.agent || {};
  const ago = t => !t ? "never" : (Date.now()/1000 - t < 5400
    ? Math.max(1, Math.round((Date.now()/1000 - t)/60)) + "m ago"
    : Math.round((Date.now()/1000 - t)/3600) + "h ago");
  return `<section class="chsec" style="margin-bottom:14px">
    <div class="rform">
      <div class="rfrow"><label>Aggregator</label><div class="rfield">
        <code>${esc(a.package||"")}@${esc(a.version||"")}</code>
        <span class="hint">Pinned on purpose — an unpinned <code>npx -y</code> could swap the
          aggregator between two turns of one session. Checked ${esc(ago(a.checked_at))},
          automatically every ${Math.round((a.ttl||86400)/3600)}h.
          <button class="btn" type="button" data-lc-refresh ${S.localBusy==="refresh"?"disabled":""}
                  style="margin-left:6px">${S.localBusy==="refresh"?"Checking…":"Check now"}</button></span>
      </div></div>
      <div class="rfrow"><label for="lc-filter">Tag filter</label><div class="rfield">
        <input id="lc-filter" data-lc-filter spellcheck="false" autocapitalize="off"
               placeholder="e.g. developer-tools,databases" value="${esc(L.filter||"")}">
        <span class="hint">Blank exposes every enabled server. Otherwise only these tags reach
          the session — the same tags the groups below are keyed on.</span>
      </div></div>
      <div class="rfrow"><label>Route hosted</label><div class="rfield">
        <button class="btn" type="button" aria-pressed="${!!L.route_composio}"
                data-lc-route ${S.localBusy?"disabled":""}>
          ${L.route_composio?"Composio routed through here":"Composio connects directly"}</button>
        <span class="hint">On, the Composio endpoint is added to this aggregator and the session
          gets ONE connector for everything. Off (default) it connects directly — one less
          process in front of something that already works.</span>
      </div></div>
    </div>
  </section>`;
}

/* The servers, grouped by tag. This is the assorting, and it is the same
   grouping 1MCP itself sees -- the <select> writes a real config field. */
function lcGroups(L){
  const groups = L.groups || [];
  if (!groups.length) return `<div class="zero"><h4>No local servers</h4>
    <p>Add one below, or pick from the open MCP Registry. Each one is grouped by category,
       and one aggregator process fronts them all.</p></div>`;

  return `<div class="conn-groups">${groups.map(g=>`
    <div class="conn-catgroup">
      <h3 class="conn-catgroup-h">${esc(g.tag)}<span class="conn-catgroup-n">${g.servers.length}</span></h3>
      <div class="conn-list">${g.servers.map(lcRow).join("")}</div>
    </div>`).join("")}
    <div class="conn-actions">
      <button class="btn" type="button" data-lc-add>＋ Add server</button>
      <button class="btn" type="button" data-conn-reload>Re-read</button>
    </div>`;
}

/* One local server. The summary is the command line (stdio) or the url -- the
   one line that says what this actually runs. */
function lcRow(s){
  const on = !!s.enabled, busy = !!S.localBusy;
  const line = s.transport === "stdio"
    ? [s.command, ...(Array.isArray(s.args)?s.args:[])].filter(Boolean).join(" ")
    : (s.url||"");
  const tags = (S.localTags||[]).indexOf(s.tag) < 0
    ? [s.tag].concat(S.localTags||[]) : (S.localTags||[]);
  return `<div class="conn-row">
    <div class="conn-main">
      <div class="conn-name">${esc(s.title||s.name)}
        <span class="pill ${s.transport==="stdio"?"p-acc":"p-mut"}">${esc(s.transport)}</span></div>
      <div class="conn-sum">${line?`<code>${esc(line)}</code>`
        :`<span style="color:var(--faint)">no target set</span>`}</div>
    </div>
    <div class="conn-ctl">
      <select data-lc-tag="${esc(s.id)}" ${busy?"disabled":""} aria-label="Category for ${esc(s.name)}">
        ${tags.map(t=>`<option value="${esc(t)}" ${t===s.tag?"selected":""}>${esc(t)}</option>`).join("")}
      </select>
      <button class="btn conn-tog" type="button" aria-pressed="${on}"
              data-lc-toggle="${esc(s.id)}" ${busy?"disabled":""}
              title="${on?"Enabled — click to disable":"Disabled — click to enable"}">
        ${on?"Enabled":"Disabled"}</button>
      <button class="btn" type="button" data-lc-remove="${esc(s.id)}" ${busy?"disabled":""}>Remove</button>
    </div>
  </div>`;
}

/* The add/edit form. Mirrors the routines grid; field edits live in S.localForm,
   not the DOM, because a transport change re-renders the whole form and anything
   only in the DOM would be lost at that moment. */
function lcAddForm(){
  const f = S.localForm; if (!f) return "";
  const t = f.transport || "stdio";
  const row = (id,label,control,hint) => `<div class="rfrow">
    <label for="lf-${id}">${esc(label)}</label>
    <div class="rfield">${control}${hint?`<span class="hint">${hint}</span>`:""}</div></div>`;

  const stdioRows = `
    ${row("command","Command",
      `<input id="lf-command" data-lf="command" placeholder="npx" spellcheck="false"
              autocapitalize="off" value="${esc(f.command||"")}">`,
      "The executable that speaks MCP over stdio. It runs on this machine.")}
    ${row("args","Arguments",
      `<textarea id="lf-args" data-lf="args" class="conn-args"
         placeholder="-y @modelcontextprotocol/server-filesystem ~/work">${esc(f.args||"")}</textarea>`,
      "Space- or newline-separated. Each token is one argument.")}
    ${row("env","Environment", lcEnvRows(f),
      "One row per variable — this is where a server's secrets go.")}`;

  const urlRows = `
    ${row("url","URL",
      `<input id="lf-url" data-lf="url" placeholder="https://example.com/mcp"
              spellcheck="false" value="${esc(f.url||"")}">`,
      "A remote endpoint the aggregator connects to on your behalf.")}`;

  return `<section class="chsec" style="margin-bottom:14px">
    <h2 class="chh">Add local server</h2>
    ${S.localFormError?`<div class="note b" style="white-space:pre-wrap">${esc(S.localFormError)}</div>`:""}
    <div class="rform">
      ${row("name","Name",
        `<input id="lf-name" data-lf="name" placeholder="filesystem" spellcheck="false"
                autocapitalize="off" value="${esc(f.name||"")}">`,
        "How it appears inside the aggregator's tool namespace.")}
      ${row("transport","Transport",
        `<select id="lf-transport" data-lf-transport>${["stdio","http","sse"].map(x=>
          `<option value="${x}" ${t===x?"selected":""}>${x}</option>`).join("")}</select>`,
        "stdio runs a local command; http and sse connect to a URL.")}
      ${row("tag","Category",
        `<input id="lf-tag" data-lf="tag" placeholder="developer-tools" spellcheck="false"
                autocapitalize="off" value="${esc(f.tag||"")}">`,
        "The 1MCP tag this server is filed under. Blank lets it be guessed.")}
      ${t==="stdio" ? stdioRows : urlRows}
    </div>
    <div class="rfoot">
      <button class="btn" type="button" data-lc-save ${S.localBusy==="save"?"disabled":""}>
        ${S.localBusy==="save"?"Saving…":"Save"}</button>
      <button class="btn" type="button" data-lc-cancel>Cancel</button>
    </div>
  </section>`;
}

function lcEnvRows(f){
  const env = f.env || [];
  return `<div class="conn-env">${env.map((r,i)=>`<div class="conn-envrow">
    <input data-lenvk="${i}" placeholder="KEY" spellcheck="false" autocapitalize="off"
           value="${esc(r.k||"")}">
    <input data-lenvv="${i}" placeholder="value" spellcheck="false" value="${esc(r.v||"")}">
    <button class="btn" type="button" data-lenv-del="${i}"
            aria-label="Remove variable ${esc(r.k||String(i+1))}">✕</button>
  </div>`).join("")}
    <button class="btn conn-env-add" type="button" data-lenv-add>＋ Add variable</button></div>`;
}

/* The open MCP Registry, assorted. Clicking a card PREFILLS the form and stops
   -- a registry entry ships without secrets, so an auto-save would write a
   server that cannot run. `tag_source` is shown because a GUESSED category and
   a LOOKED-UP one are different claims, and the registry publishes no
   categories at all. */
function lcRegistry(L){
  const reg = S.localReg || {};
  const rows = reg.results || [];
  const q = S.localQuery || "";
  const status = S.localRegBusy ? "searching…"
    : (rows.length ? rows.length + (reg.source==="stale" ? " (last good copy)" : " servers")
                   : (q ? "no matches" : ""));
  const err = reg.error ? `<div class="note b">Registry unavailable — ${esc(reg.error)}.
    Showing the last copy we had.</div>` : "";

  const groups = {};
  rows.forEach((r,i)=>{ (groups[r.tag||"other"] = groups[r.tag||"other"] || []).push([r,i]); });

  return `<section class="chsec conn-cat"><h2 class="chh">Open MCP Registry</h2>
    <p style="margin:0 0 8px;color:var(--muted);font-size:11.5px;max-width:70ch">Every server
      published to <code>registry.modelcontextprotocol.io</code>, grouped into the same categories
      the hosted connector uses. Clicking one fills the form above — you add any secrets, and
      nothing is saved until you press Save.</p>
    <div class="conn-search">
      <input data-lc-search placeholder="Search the registry — postgres, playwright, figma…"
             spellcheck="false" autocapitalize="off" value="${esc(q)}">
      <span class="conn-search-note">${esc(status)}</span>
    </div>${err}
    ${Object.keys(groups).sort().map(tag=>`<div class="conn-catgroup">
      <h3 class="conn-catgroup-h">${esc(tag)}<span class="conn-catgroup-n">${groups[tag].length}</span></h3>
      <div class="conn-chips">${groups[tag].map(ri=>lcRegChip(ri[0], ri[1])).join("")}</div>
    </div>`).join("")}</section>`;
}

function lcRegChip(r, i){
  return `<button class="conn-chip" type="button" data-lc-pick="${i}"
       title="${esc(r.description||"")}">
       <span class="conn-chip-h"><span class="conn-chip-n">${esc(r.title||r.name)}</span>
         <span class="pill ${r.transport==="stdio"?"p-acc":"p-mut"}">${esc(r.transport||"?")}</span></span>
       <span class="conn-chip-d">${esc(r.description||"")}</span>
       ${r.tag_source==="guess"?`<span class="conn-chip-d" style="opacity:.6">category guessed</span>`:""}
     </button>`;
}

/* The account block. The key is a password field and the server never sends it
   back -- only whether one is set and its last four characters, which is enough
   to recognise which key you pasted and useless to anyone reading the screen.

   "Test connection" is here rather than implied because the alternative is
   finding out from a missing tool three turns later: it provisions a real
   session against Composio and reports what Composio said. */
function connAccount(c){
  const a = S.connAuth || {};
  const set = !!c.api_key_set;
  const sess = c.session || {};
  const busy = S.connBusy;

  const keyState = set
    ? `<span class="pill p-acc">set ${esc(c.api_key_hint||"")}</span>`
    : `<span class="pill p-mut">not set</span>`;

  /* Three distinct session facts, and the screen says which one it is rather
     than collapsing them into a green dot: never provisioned, provisioned but
     superseded by a toolkit change, or live. */
  const sessLine = !c.ready
    ? `<span style="color:var(--faint)">nothing to connect yet — set a key, a user id, and one toolkit</span>`
    : sess.active
      ? (sess.stale
          ? `<span class="pill p-mut">will re-provision</span> the enabled toolkits changed since this session was made`
          : `<span class="pill p-acc">live</span> <code>${esc(sess.session_id||"")}</code>`)
      : `<span style="color:var(--faint)">no session yet — it is created on the next message, or press Test connection</span>`;

  const row = (id,label,control,hint) => `<div class="rfrow">
    <label for="cx-${id}">${esc(label)}</label>
    <div class="rfield">${control}${hint?`<span class="hint">${hint}</span>`:""}</div></div>`;

  return `<section class="chsec" style="margin-bottom:14px">
    <h2 class="chh">Composio account</h2>
    ${S.connAuthError?`<div class="note b" style="white-space:pre-wrap">${esc(S.connAuthError)}</div>`:""}
    <div class="rform">
      ${row("key","API key",
        `<input id="cx-key" type="password" data-cx="api_key" spellcheck="false"
                autocapitalize="off" autocomplete="off"
                placeholder="${set?"leave blank to keep the current key":"ak_…"}"
                value="${esc(a.api_key||"")}"> ${keyState}`,
        `From <code>dashboard.composio.dev/settings</code>. Stored in ~/.sutra-ui/composio.json
         and sent to Composio as a header — never in a URL, never logged.`)}
      ${row("user","User id",
        `<input id="cx-user" data-cx="user_id" spellcheck="false" autocapitalize="off"
                placeholder="you@example.com" value="${esc(a.user_id!=null?a.user_id:(c.user_id||""))}">`,
        "Whoever the connected accounts belong to. Composio scopes every session to it.")}
      ${row("sess","Session", `<div style="font-size:11.5px">${sessLine}</div>`,
        "One session carries every enabled toolkit. It is re-made automatically when you change them.")}
    </div>
    <div class="rfoot">
      <button class="btn" type="button" data-cx-save ${busy==="auth"?"disabled":""}>
        ${busy==="auth"?"Saving…":"Save"}</button>
      <button class="btn" type="button" data-cx-test ${busy==="test"||!c.ready?"disabled":""}>
        ${busy==="test"?"Connecting…":"Test connection"}</button>
      <button class="btn" type="button" data-conn-reload>Re-read</button>
    </div>
  </section>`;
}

/* What is actually ON. Named toolkits with their tool counts, because "gmail"
   and "gmail, 63 tools" are different amounts of information about what a
   session can now do. Empty is a real state and says what to do about it. */
function connEnabled(c){
  const enabled = c.enabled || [];
  if (!enabled.length) return `<div class="zero"><h4>No toolkits enabled</h4>
    <p>Sessions this panel starts cannot reach any external service yet. Enable one
       from the catalog below — the agent will ask you to connect the account the
       first time it uses it.</p></div>`;

  const meta = {};
  ((S.connCat && S.connCat.results) || []).forEach(r => { meta[r.slug] = r; });
  return `<section class="chsec"><h2 class="chh">Enabled toolkits (${enabled.length})</h2>
    <div class="conn-list">${enabled.map(slug=>{
      const m = meta[slug] || {};
      const counts = m.tools
        ? `${m.tools} tool${m.tools===1?"":"s"}${m.triggers?` · ${m.triggers} trigger${m.triggers===1?"":"s"}`:""}`
        : "";
      return `<div class="conn-row">
        <div class="conn-main">
          <div class="conn-name">${esc(m.name||slug)} <span class="pill p-acc">${esc(slug)}</span></div>
          <div class="conn-sum">${counts?`<code>${esc(counts)}</code>`
            :`<span style="color:var(--faint)">${esc(m.category||"enabled")}</span>`}</div>
        </div>
        <div class="conn-ctl">
          <button class="btn" type="button" data-tk-off="${esc(slug)}" ${S.connBusy?"disabled":""}>Disable</button>
        </div>
      </div>`;
    }).join("")}</div></section>`;
}

/* The catalog: Composio's own toolkit list, mirrored from ComposioHQ/composio and
   refreshed on a TTL (see composio_store.refresh_catalog). Served from the local
   copy, so typing never waits on GitHub.

   The freshness line states CHECKED and UPDATED separately, because "we looked
   and nothing changed" and "nothing has changed since we last looked" are
   different claims and only one of them is about upstream. */
function connCatalog(c){
  const page = S.connCat || {};
  const rows = page.results || [];
  const q = S.connQuery || "";
  const meta = (c.catalog) || page.catalog || {};
  const enabled = new Set(c.enabled || []);

  const status = S.catBusy ? "searching…"
    : (rows.length ? (q ? `${page.total} match${page.total===1?"":"es"}`
                        : `${meta.count||page.total||0} toolkits`)
                   : (q ? "no matches" : ""));

  const body = rows.length
    ? `<div class="conn-chips">${rows.map(r=>connChip(r, enabled.has(r.slug))).join("")}</div>`
    : "";
  const more = (!q && page.total > rows.length)
    ? `<p class="conn-search-note" style="margin-top:8px">Showing the ${rows.length} largest of
       ${page.total}. Search to reach the rest.</p>` : "";

  return `<section class="chsec conn-cat"><h2 class="chh">Toolkit catalog</h2>
    <p style="margin:0 0 8px;color:var(--muted);font-size:11.5px;max-width:70ch">Every app Composio
      connects. Enabling one adds its tools to the single MCP endpoint your sessions already have —
      nothing is installed, and you connect the account in-browser the first time the agent uses it.</p>
    <div class="conn-search">
      <input data-cx-search placeholder="Search 1000+ toolkits — jira, hubspot, shopify…"
             spellcheck="false" autocapitalize="off" value="${esc(q)}">
      <span class="conn-search-note">${esc(status)}</span>
    </div>
    ${connFresh(meta)}
    ${body}${more}</section>`;
}

/* One toolkit card. The whole card is the toggle -- there is exactly one thing
   you can do to a toolkit, so a card that shows state and a separate button that
   changes it would be two controls for one decision. */
function connChip(r, on){
  return `<button class="conn-chip" type="button" data-tk-pick="${esc(r.slug)}"
       aria-pressed="${!!on}" ${S.connBusy?"disabled":""}
       title="${esc(r.slug)} — ${on?"enabled, click to disable":"click to enable"}">
       <span class="conn-chip-h"><span class="conn-chip-n">${esc(r.name||r.slug)}</span>
         <span class="pill ${on?"p-acc":"p-mut"}">${on?"on":esc(String(r.tools||0))}</span></span>
       <span class="conn-chip-d">${esc(r.category||"")}${
         r.tools?` · ${r.tools} tool${r.tools===1?"":"s"}`:""}</span>
     </button>`;
}

/* Catalog freshness + the manual update check. This is the visible half of the
   auto-update: the same refresh runs on a TTL when the screen opens and on the
   desktop shell's update tick, so the button is a way to HURRY it, not the only
   way it happens -- and the line says so rather than implying the operator is
   responsible for staying current. */
function connFresh(meta){
  const ago = t => {
    if (!t) return "never";
    const s = Math.max(0, Date.now()/1000 - t);
    if (s < 90) return "just now";
    if (s < 5400) return Math.round(s/60) + "m ago";
    if (s < 172800) return Math.round(s/3600) + "h ago";
    return Math.round(s/86400) + "d ago";
  };
  const src = meta.source === "vendored"
    ? "the copy shipped with this app" : "ComposioHQ/composio";
  return `<p class="conn-search-note" style="margin:0 0 10px">
    From ${esc(src)} · checked ${esc(ago(meta.checked_at))} · last changed ${esc(ago(meta.updated_at))}
    · re-checked automatically every ${Math.round((meta.ttl||21600)/3600)}h
    <button class="btn" type="button" data-cx-refresh ${S.connBusy==="refresh"?"disabled":""}
            style="margin-left:8px">${S.connBusy==="refresh"?"Checking…":"Check now"}</button></p>`;
}

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

