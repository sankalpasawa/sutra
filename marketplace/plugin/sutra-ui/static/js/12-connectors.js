/* Connectors — the External World block's operator projection (ADR-023).
 *
 * Tile view: one tile per PROVIDER, connected or not. A provider with no
 * connector still needs somewhere to live, and there is no connector row to
 * render it from — which is why the tiles come from /api/providers rather than
 * from the connector list.
 *
 * Render-only over the connector service. This screen never sees a credential:
 * everything below is a projection the backend already stripped (ADR-034).
 *
 * Truth-class discipline (ADR-023 Decision 1b): connector rows and audit events
 * are AUTHORITATIVE; an in-flight authorization is EPHEMERAL and is labelled as
 * such rather than drawn as settled state.
 */

S.conn = { providers: null, sections: null, err: null, tx: null, txProvider: null, txErr: null,
           open: null, openProvider: null,
           repos: null, orgs: null, perms: null, events: null, busy: false,
           /* mediated = connections Sutra can SEE but does not own. Held apart
              from `providers` on purpose: merging them would let Claude's
              connections inflate Sutra's own connected count. */
           mediated: null, mediatedBusy: false };

/* The backend returns a structured error body; apiGet/apiPost stringify the
 * whole object into the Error message. Rendering that raw put a JSON blob on
 * screen -- `{"code":"VALIDATION_FAILED","message":"slack: bad_client_secret",
 * "retryable":false,...}` -- when the useful part is one sentence and an action.
 */
const CONN_ACTION_HINT = {
  RECONNECT: "Reconnect this account.",
  GRANT_CAPABILITY: "Grant the capability in your settings file.",
  AUTHORISE_SSO: "Authorise Sutra for that organisation.",
  INSTALL_APP: "Install the app on the account you want reachable.",
  ADD_REPOSITORY: "Add repositories to the installation.",
  WAIT: "Rate limited — try again shortly.",
  CONTACT_ORG_OWNER: "An organisation owner has to approve this.",
};
const PROVIDER_ERROR_HELP = {
  bad_client_secret:
    "The client secret on this machine is not the one this Slack app expects. "
    + "Copy it from Basic Information \u2192 App Credentials \u2192 Client Secret into "
    + "~/.sutra/provider-secrets.env",
  invalid_client_id: "The client id does not match this Slack app.",
  bad_redirect_uri:
    "The redirect URL is not registered on the app. Add "
    + "http://localhost:8765/slack/callback under OAuth & Permissions.",
  invalid_auth: "The stored credential was rejected. Reconnect.",
};

function connError(raw){
  const text = String(raw && raw.message || raw || "");
  let parsed = null;
  const brace = text.indexOf("{");
  if (brace >= 0){
    try { parsed = JSON.parse(text.slice(brace, text.lastIndexOf("}") + 1)); } catch (e) {}
  }
  if (!parsed) return { headline: text, hint: null, code: null };
  const pe = parsed.provider_error;
  return {
    headline: parsed.message || parsed.code || text,
    hint: PROVIDER_ERROR_HELP[pe] || CONN_ACTION_HINT[parsed.user_action] || null,
    code: parsed.code || null,
  };
}

async function apiDelete(path){
  const r = await fetch(API + path, { method:"DELETE" });
  if (!r.ok) throw await _fail(r, path);
  return r.json();
}
const connUrl = (p, id, tail) =>
  "/api/connectors/" + encodeURIComponent(p) + "/" + encodeURIComponent(id) + (tail || "");

async function loadConnectors(force){
  if (S.conn.providers && !force) return;
  try {
    const d = await apiGet("/api/connectors/providers");
    S.conn.providers = d.providers || [];
    S.conn.degraded = d.degraded || null;
    S.conn.err = null;
  } catch (e) {
    S.conn.err = String(e.message || e);
    S.conn.providers = [];
  }
  render();
}

async function loadConnectorDetail(provider, id){
  S.conn.open = id; S.conn.openProvider = provider;
  S.conn.repos = S.conn.orgs = S.conn.perms = S.conn.events = null;
  render();
  /* allSettled, not all: independent endpoints, and a permissions read that
     throws must not discard a perfectly good repository list. Repos and orgs
     are GitHub-shaped; other providers simply return nothing for them. */
  /* Which sections a provider HAS is a property of the provider, not of
     whether its data has arrived yet. Deriving it from the value conflated
     "Slack has no repositories" with "GitHub's repositories are still
     loading", so the detail pane rendered empty for the seconds a live GitHub
     call takes -- no spinner, no text, nothing. */
  S.conn.sections = provider === "github"
    ? { repos: true, orgs: true } : { repos: false, orgs: false };
  const wants = S.conn.sections.repos
    ? ["/repositories", "/organizations", "/permissions", "/events?limit=20"]
    : [null, null, "/permissions", "/events?limit=20"];
  const settled = await Promise.allSettled(
    wants.map(t => t === null ? Promise.resolve(null) : apiGet(connUrl(provider, id, t))));
  const val = r => r.status === "fulfilled" ? r.value
    : { _err: String((r.reason && r.reason.message) || r.reason) };
  S.conn.repos = wants[0] === null ? null : val(settled[0]);
  S.conn.orgs  = wants[1] === null ? null : val(settled[1]);
  S.conn.perms = val(settled[2]);
  S.conn.events = val(settled[3]);
  render();
}

/* ── connect ─────────────────────────────────────────────────────────── */
async function connStart(provider){
  if (S.conn.busy) return;
  S.conn.busy = true; S.conn.txErr = null; S.conn.txProvider = provider; render();
  try {
    S.conn.tx = await apiPost("/api/connectors/" + encodeURIComponent(provider) + "/authorize", {});
    connPoll(provider);
  } catch (e) { S.conn.txErr = String(e.message || e); S.conn.tx = null; }
  S.conn.busy = false; render();
}

async function connPoll(provider){
  const tx = S.conn.tx; if (!tx) return;
  const id = tx.transaction_id;
  const tick = async () => {
    if (!S.conn.tx || S.conn.tx.transaction_id !== id) return;   /* cancelled */
    let d;
    try { d = await apiGet("/api/connectors/" + encodeURIComponent(provider)
                           + "/authorize/" + encodeURIComponent(id)); }
    catch (e) { S.conn.txErr = String(e.message || e); S.conn.tx = null; render(); return; }
    if (d.status === "COMPLETED"){
      S.conn.tx = null; S.conn.providers = null;
      await loadConnectors(true);
      if (d.connector_id) loadConnectorDetail(provider, d.connector_id);
      return;
    }
    /* Honour the server's interval. Polling faster earns a rate limit. */
    setTimeout(tick, (d.poll_interval_seconds || 5) * 1000);
  };
  setTimeout(tick, (tx.poll_interval_seconds || 3) * 1000);
}

async function connCancel(){
  const tx = S.conn.tx, p = S.conn.txProvider;
  S.conn.tx = null; render();
  if (tx && p) { try { await apiDelete("/api/connectors/" + encodeURIComponent(p)
      + "/authorize/" + encodeURIComponent(tx.transaction_id)); } catch (e) {} }
}

async function connDisconnect(provider, id){
  if (!confirm("Disconnect this account?\n\nSutra deletes its copy of the credentials. "
             + "It cannot revoke the authorization at the provider — you do that in "
             + "their settings.")) return;
  try {
    await apiDelete(connUrl(provider, id));
    S.conn.open = null; S.conn.providers = null;
    await loadConnectors(true);
  } catch (e) { S.conn.err = String(e.message || e); render(); }
}

async function connRefreshRepos(provider, id){
  S.conn.repos = null; render();
  try { S.conn.repos = await apiGet(connUrl(provider, id, "/repositories?refresh=true")); }
  catch (e) { S.conn.repos = { _err: String(e.message || e) }; }
  render();
}

/* ── render ──────────────────────────────────────────────────────────── */
const CONN_STATUS = {
  ACTIVE:          ["ok",   "Connected"],
  PENDING:         ["warn", "Connecting…"],
  ERROR:           ["warn", "Unreachable — retrying"],
  REAUTH_REQUIRED: ["warn", "Reconnect needed"],
  DISCONNECTED:    ["off",  "Not connected"],
};

const PROVIDER_GLYPH = {
  github: '<path d="M12 2.2a9.8 9.8 0 0 0-3.1 19.1c.5.1.7-.2.7-.5v-1.7c-2.8.6-3.4-1.3-3.4-1.3-.4-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.3 1.1 2.9.8.1-.7.4-1.1.6-1.4-2.2-.3-4.6-1.1-4.6-4.9 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.7 1a9.4 9.4 0 0 1 5 0c1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.8-2.4 4.6-4.6 4.9.4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A9.8 9.8 0 0 0 12 2.2z"/>',
  slack:  '<path d="M5.1 14.5a2 2 0 1 1-2-2h2v2zm1 0a2 2 0 1 1 4 0v5a2 2 0 1 1-4 0v-5zM9.1 5.1a2 2 0 1 1 2-2v2h-2zm0 1a2 2 0 1 1 0 4h-5a2 2 0 1 1 0-4h5zM18.5 9.1a2 2 0 1 1 2 2h-2v-2zm-1 0a2 2 0 1 1-4 0v-5a2 2 0 1 1 4 0v5zM14.5 18.5a2 2 0 1 1-2 2v-2h2zm0-1a2 2 0 1 1 0-4h5a2 2 0 1 1 0 4h-5z"/>',
};

/* ── mediated tiles: a connection Sutra observes but does not own ────────
 *
 * Two kinds of fact are rendered differently on purpose, because the backend
 * can vouch for one and not the other:
 *
 *   MEMBERSHIP is durable. "This Claude account has a Gmail connector" comes
 *   from the account's connector list. It is rendered as state.
 *
 *   The STATUS STRING is a five-second probe. The same unchanged connector
 *   was observed reporting four different things within one hour. It is
 *   rendered as a quoted observation attributed to the check, never as a
 *   claim about the connector -- "Claude's last check reported X".
 *
 * And the account is not rendered at all, because it is not knowable: Claude
 * does not report which Google account a connector is bound to. The nearest
 * thing to hand is the CLAUDE account email, which is usually a @gmail.com
 * address and is therefore the single most tempting wrong answer available.
 */
const MED_MEMBERSHIP = {
  added:     ["ok",  "Added in Claude"],
  /* Scoped to the evidence that exists. Sutra sees what the Claude CLI lists;
     that is not the same as what the account holds -- a connector can be
     present in claude.ai and absent from the CLI's view. Claiming the stronger
     fact from the weaker observation is the error ADR-035 exists to prevent. */
  not_added: ["off", "Not listed by the Claude CLI"],
  unknown:   ["off", "Status unknown"],
};

const MED_OBSERVED = {
  connected:        "connected",
  degraded:         "connected, but its tools did not answer",
  needs_auth:       "not authenticated",
  pending_approval: "waiting for approval",
  not_configured:   "not configured",
  probe_failed:     "unreachable",
  unknown:          "something it did not recognise",
};

/* Availability is about the CHECK, not the connector. Every one of these
   means "we do not know", and none of them may render as "not connected". */
const MED_UNAVAILABLE = {
  not_checked: ["Not checked yet.",
    "Checking runs `claude mcp list`, which contacts each of your connectors."],
  cli_missing: ["Claude Code is not installed.",
    "Sutra reads these connections by running the `claude` CLI, and no `claude` binary was found. Set SUTRA_UI_CLAUDE_BIN to its full path if it lives elsewhere."],
  timed_out: ["Status unknown.",
    "`claude mcp list` did not answer in time. It contacts every connector to check it, so this can happen on a slow connection or with many connectors."],
  cli_error: ["Status unknown.", "The Claude CLI exited with an error."],
  unreadable: ["Status unknown.",
    "The Claude CLI listed no claude.ai connectors. It prints exactly the same thing when you are offline, when you are signed out, and when you genuinely have none — so Sutra will not guess which."],
};

function medWhen(ts){
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit", second:"2-digit"});
}

/* Founder direction 2026-08-24, non-negotiable: EVERY connector type gets its
   own tile. One tile listing four services was the shape that got called weird
   twice; grouping them under a single "Connected in Claude" card made Gmail,
   Drive, Slack and Atlassian look like sub-items of a product that does not
   exist. They are four separate connections and they render as four tiles,
   sitting beside GitHub's.

   The probe is still ONE call for all of them -- the CLI lists every connector
   in a single run -- so Re-check on any tile refreshes them all. The button
   says so rather than implying it only refreshes its own. */
const MED_GLYPH = {
  gmail:  '<path d="M3 6.5v11h4.2V11l4.8 3.6L16.8 11v6.5H21v-11a1.6 1.6 0 0 0-2.5-1.3L12 9.9 5.5 5.2A1.6 1.6 0 0 0 3 6.5z"/>',
  gdrive: '<path d="M8.4 3.5h7.2l5.4 9.3-3.6 6.2H5.4l-3.6-6.2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
  slack:  '<path d="M5.2 14.4a1.8 1.8 0 1 1-1.8-1.8h1.8zm.9 0a1.8 1.8 0 0 1 3.6 0v4.5a1.8 1.8 0 0 1-3.6 0zM9.7 5.2a1.8 1.8 0 1 1 1.8-1.8v1.8zm0 .9a1.8 1.8 0 0 1 0 3.6H5.2a1.8 1.8 0 0 1 0-3.6zM18.8 9.7a1.8 1.8 0 1 1 1.8 1.8h-1.8zm-.9 0a1.8 1.8 0 0 1-3.6 0V5.2a1.8 1.8 0 0 1 3.6 0zM14.3 18.8a1.8 1.8 0 1 1-1.8 1.8v-1.8zm0-.9a1.8 1.8 0 0 1 0-3.6h4.5a1.8 1.8 0 0 1 0 3.6z"/>',
};
const MED_GLYPH_FALLBACK =
  '<path d="M8.5 8.5a3.5 3.5 0 1 0 0 7M15.5 8.5a3.5 3.5 0 1 1 0 7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>';

/* What the tile says under the name. Membership, not health -- health is the
   quoted observation below it. */
const MED_SUBTITLE = {
  added:     "Connected inside Claude",
  not_added: "Not connected in Claude",
  unknown:   "Sutra could not check",
};

function mediatedTile(t, svc){
  const ok = t.availability === "ok";
  const [cls, label] = MED_MEMBERSHIP[svc.membership] || ["off", "Status unknown"];
  const glyph = MED_GLYPH[svc.key] || MED_GLYPH_FALLBACK;
  const attn = svc.membership === "added" &&
               ["needs_auth", "probe_failed", "not_configured"].indexOf(svc.observation) !== -1;

  /* One line per real connector, never collapsed: two accounts can share a
     host, and folding them together would hide a broken connection behind a
     healthy one. */
  const rows = (svc.connectors || []).map(c => {
    const said = MED_OBSERVED[c.observation] || "something it did not recognise";
    return `<li><span class="dot ${cls}"></span>
      <span class="muted">Claude's last check reported it ${esc(said)}</span>
      ${c.raw_status ? `<code>${esc(c.raw_status)}</code>` : ""}
      ${(svc.connectors.length > 1) ? `<span class="tag">${esc(c.label)}</span>` : ""}
    </li>`;
  }).join("");

  let body;
  if (!ok){
    const [head, why] = MED_UNAVAILABLE[t.availability] || MED_UNAVAILABLE.cli_error;
    body = `<div class="note w tileblocked"><b>${esc(head)}</b> ${esc(why)}
      ${t.availability_detail ? `<br><code>${esc(t.availability_detail)}</code>` : ""}</div>`;
  } else if (svc.membership === "not_added"){
    body = `<ul class="connlist"><li class="muted tileempty">
      ${esc(label)} — add it in Claude and it will appear here.</li></ul>`;
  } else {
    body = `<ul class="connlist">${rows}</ul>`;
  }

  /* Only where a connection actually exists. Next to "not connected" it would
     read as a hedge about something that is not there. */
  /* Three states, deliberately distinct. A blanket "not visible to Sutra" was
     accurate but hid the difference between "the connector told us", "we asked
     and it could not tell" and "we have no way to ask this one yet". */
  let acct = "";
  if (ok && svc.membership === "added"){
    if (svc.account){
      acct = `<p class="mediatedacct"><span class="muted">Account</span>
                <b>${esc(svc.account)}</b></p>`;
    } else if (svc.account_resolvable){
      acct = `<p class="mediatedacct muted">Account: Claude did not report one.</p>`;
    } else {
      acct = `<p class="mediatedacct muted">Account: Sutra cannot ask this
                connector who it is.</p>`;
    }
  }

  return `<div class="ptile mediated ${attn ? "attn" : ""}">
    <div class="ptilehead">
      <svg class="pglyph" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${glyph}</svg>
      <div>
        <b>${esc(svc.name)}</b>
        <div class="muted">${esc(MED_SUBTITLE[svc.membership] || "Sutra could not check")}</div>
      </div>
      <span class="sp"></span>
      <span class="ct via">via Claude</span>
    </div>
    ${body}
    ${acct}
    <p class="tilecaveat">Claude owns this connection. No token and no account
      reaches Sutra, and a Sutra turn cannot use it.</p>
    ${t.checked_at ? `<p class="medfoot muted">Checked ${esc(medWhen(t.checked_at))}${
        t.stale ? " · may be out of date" : ""}</p>` : ""}
    <div class="medactions">
      <button class="btn" type="button" data-connrecheck="${esc(svc.key)}"
        ${S.conn.mediatedBusy ? "disabled" : ""}
        title="Runs one live probe through the Claude CLI — it refreshes every Claude connection, not just this one">
        ${S.conn.mediatedBusy ? "Checking…" : (t.checked_at ? "Re-check" : "Check now")}</button>
      <a class="btn" href="${esc(t.manage_url || "https://claude.ai/customize/connectors")}"
         target="_blank" rel="noreferrer">Manage in Claude</a>
    </div>
  </div>`;
}

/* One tile per connector. The snapshot is shared (a single CLI run), the tiles
   are not. */
function mediatedTiles(t){
  if (!t) return "";
  return (t.services || []).map(svc => mediatedTile(t, svc)).join("");
}

async function loadMediated(refresh){
  if (S.conn.mediatedBusy) return;
  if (refresh) { S.conn.mediatedBusy = true; render(); }
  try {
    const d = await apiGet("/api/connectors/mediated" + (refresh ? "?refresh=true" : ""));
    S.conn.mediated = (d.tiles || [])[0] || null;
  } catch (e) {
    /* A failed fetch is not evidence about the connection. Fall back to the
       same "we do not know" shape the backend uses. */
    S.conn.mediated = { provider: "google", name: "Google", via: "claude",
                        account_known: false, availability: "cli_error",
                        availability_detail: String(e.message || e),
                        services: [], checked_at: null };
  }
  S.conn.mediatedBusy = false;
  render();
}

function providerTile(p){
  const glyph = PROVIDER_GLYPH[p.provider] || '<circle cx="12" cy="12" r="8"/>';
  const connected = p.connectors || [];
  const attention = p.needs_attention > 0;

  const rows = connected.length
    ? connected.map(c => {
        const [cls, label] = CONN_STATUS[c.status] || ["off", c.status];
        return `<li>
          <span class="dot ${cls}"></span>
          <b>${esc(c.account.username || c.account.id)}</b>
          ${c.label?`<span class="tag">${esc(c.label)}</span>`:""}
          <span class="muted">${esc(label)}</span>
          <span class="sp"></span>
          <button class="btn" type="button" data-connopen="${esc(c.id)}"
            data-provider="${esc(p.provider)}">${S.conn.open===c.id?"Hide":"Manage"}</button>
        </li>`;
      }).join("")
    : `<li class="muted tileempty">Not connected</li>`;

  /* Blocked is a DIFFERENT state from not-connected, with a different fix.
     Saying so on the tile means the operator learns a secret is missing
     before a browser opens, not from an error afterwards. */
  const action = p.connectable
    ? `<button class="btn ${connected.length?"":"primary"}" type="button"
         data-connstart="${esc(p.provider)}" ${S.conn.busy?"disabled":""}>
         ${connected.length ? "Add account" : "Connect"}</button>`
    : `<div class="note w tileblocked"><b>Not configured.</b>
         ${esc(p.blocked_reason || "")}</div>`;

  return `<div class="ptile ${attention?"attn":""}">
    <div class="ptilehead">
      <svg class="pglyph" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${glyph}</svg>
      <div>
        <b>${esc(p.display_name)}</b>
        <div class="muted">${esc(p.tagline)}</div>
      </div>
      <span class="sp"></span>
      ${connected.length?`<span class="ct ${attention?"w":""}">${connected.length}</span>`:""}
    </div>
    <ul class="connlist">${rows}</ul>
    ${p.caveat?`<p class="tilecaveat">${esc(p.caveat)}</p>`:""}
    ${action}
  </div>`;
}

function connDetailPane(){
  if (!S.conn.open) return "";
  const provider = S.conn.openProvider;
  let card = null;
  (S.conn.providers||[]).forEach(p => (p.connectors||[]).forEach(c => {
    if (c.id === S.conn.open) card = { p, c }; }));
  if (!card) return "";
  const { p, c } = card;
  return `<div class="conncard open">
    <div class="connhead">
      <span class="dot ok"></span><b>${esc(p.display_name)} · ${esc(c.account.username||"")}</b>
      ${c.label?`<span class="tag">${esc(c.label)}</span>`:""}
      <span class="sp"></span>
      <button class="btn" type="button" data-connopen="${esc(c.id)}"
        data-provider="${esc(provider)}">Hide</button>
      <button class="btn danger" type="button" data-conndis="${esc(c.id)}"
        data-provider="${esc(provider)}">Disconnect</button>
    </div>
    <div class="connmeta">account ${esc(c.account.id)} · connected ${esc((c.created_at||"").slice(0,10))}</div>
    <div class="conndetail">
      ${(S.conn.sections||{}).repos ? connRepos(provider, c) : ""}
      ${(S.conn.sections||{}).orgs ? connOrgs() : ""}
      ${connPerms()}
      ${connEvents()}
    </div>
  </div>`;
}

function connRepos(provider, c){
  const d = S.conn.repos;
  if (!d) return `<section><h4>Repositories</h4><p class="muted">Loading…</p></section>`;
  if (d._err) return `<section><h4>Repositories</h4><p class="err">${esc(d._err)}</p></section>`;
  const rows = d.repositories || [];
  if (!rows.length){
    const notInstalled = d.empty_reason === "NOT_INSTALLED";
    return `<section><h4>Repositories</h4>
      <div class="note w"><b>${notInstalled?"Authorized but not installed."
        :"The installation selects no repositories."}</b>
      ${notInstalled?"Authorization proves who you are; installation is what grants access."
        :"Add repositories to the installation to make them reachable."}
      <br><a class="btn" href="${esc(d.install_url||"https://github.com/settings/installations")}"
        target="_blank" rel="noreferrer">Open installations</a></div></section>`;
  }
  return `<section><h4>Repositories <span class="ct">${rows.length}</span>
    <button class="btn" type="button" data-connrefresh="${esc(c.id)}"
      data-provider="${esc(provider)}">Refresh</button></h4>
    <div class="tblwrap"><table class="tbl"><thead><tr><th>Repository</th><th>Visibility</th>
      <th>Your role</th><th>Capabilities</th></tr></thead><tbody>
    ${rows.map(r=>`<tr><td><code>${esc(r.full_name)}</code></td>
      <td>${esc(r.visibility)}</td><td>${esc(r.user_permission)}</td>
      <td title="${esc((r.capabilities||[]).join("\n"))}">${(r.capabilities||[]).length}</td></tr>`).join("")}
    </tbody></table></div></section>`;
}

function connOrgs(){
  const d = S.conn.orgs;
  if (!d) return `<section><h4>Organizations</h4><p class="muted">Loading…</p></section>`;
  if (d._err) return `<section><h4>Organizations</h4><p class="err">${esc(d._err)}</p></section>`;
  const rows = d.organizations || [], personal = d.personal_installation;
  if (!rows.length && !personal) return "";
  const note = { ok:"installed", not_installed:"Sutra not installed",
                 sso_required:"SAML sign-in required", suspended:"suspended" };
  return `<section><h4>Organizations</h4><ul class="connlist">
    ${personal?`<li><span class="dot ok"></span><b>${esc(personal.account)}</b>
      <span class="muted">personal · ${esc(personal.repository_selection)}</span></li>`:""}
    ${rows.map(o=>`<li><span class="dot ${o.access==="ok"?"ok":"warn"}"></span>
      <b>${esc(o.login)}</b> <span class="muted">${esc(note[o.access]||o.access)}</span></li>`).join("")}
  </ul></section>`;
}

function connPerms(){
  const d = S.conn.perms;
  if (!d) return `<section><h4>Permissions</h4><p class="muted">Loading…</p></section>`;
  if (d._err) return `<section><h4>Permissions</h4><p class="err">${esc(d._err)}</p></section>`;
  const kinds = ["deny","ask","allow"];   /* evaluation order, so it reads as the engine reads it */
  const total = kinds.reduce((n,k)=>n+((d.rules||{})[k]||[]).length,0);
  return `<section><h4>Permissions</h4>
    <div class="note"><b>Mode: ${esc(d.mode)}</b> — evaluated <b>deny → ask → allow</b>,
      first match wins. A broad deny beats a narrow allow.
      ${d.managed_rules_only?" Managed policy is the only rule source here.":""}</div>
    ${total?`<div class="tblwrap"><table class="tbl"><thead><tr><th>Rule</th><th>Effect</th>
      <th>From</th></tr></thead><tbody>
      ${kinds.flatMap(k=>((d.rules||{})[k]||[]).map(r=>
        `<tr><td><code>${esc(r.rule)}</code></td><td class="k-${k}">${k}</td>
         <td>${esc(r.source)}</td></tr>`)).join("")}
      </tbody></table></div>`
    :`<p class="muted">No rules configured. Reads inside the connected scope are allowed;
      every write asks. Add rules in <code>~/.sutra/settings.json</code>.</p>`}
    ${(d.removed_tools||[]).length?`<p class="muted"><b>Removed from the agent entirely:</b>
      ${d.removed_tools.map(t=>`<code>${esc(t)}</code>`).join(" ")} — a bare deny rule removes a
      tool from the model's context, so it cannot be proposed at all.</p>`:""}
    ${(d.warnings||[]).length?`<div class="note w"><b>${d.warnings.length} rule${
      d.warnings.length===1?"":"s"} ignored:</b><ul>${
      d.warnings.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></div>`:""}
  </section>`;
}

function connEvents(){
  const d = S.conn.events;
  if (!d) return `<section><h4>Recent activity</h4><p class="muted">Loading…</p></section>`;
  if (d._err) return "";
  const rows = d.events || [];
  if (!rows.length) return "";
  return `<section><h4>Recent activity <span class="muted">audited, hash-chained</span></h4>
    <div class="tblwrap"><table class="tbl"><thead><tr><th>When</th><th>Event</th>
      <th>Result</th><th>Resource</th></tr></thead><tbody>
    ${rows.map(e=>`<tr><td>${esc((e.occurred_at||"").slice(0,19).replace("T"," "))}</td>
      <td>${esc(e.event_type)}</td>
      <td class="r-${esc(String(e.result).toLowerCase())}">${esc(e.result)}</td>
      <td>${esc(e.resource||"")}</td></tr>`).join("")}
    </tbody></table></div></section>`;
}

SCREENS.connectors = () => {
  const s = S.conn;
  const head = `<div class="sc-head"><h3>${esc(TITLES.connectors[0])}</h3>
    <p>${esc(TITLES.connectors[1])}</p></div>`;

  if (s.err){
    const structured = /PANEL_INTERNAL_ERROR/.test(s.err);
    return head + `<div class="note w">
      <b>${structured ? "The connector service hit an unexpected error."
                      : "The connector service did not answer."}</b>
      <br><code>${esc(s.err)}</code>
      ${structured?`<br>Full traceback: <code>~/.sutra/panel-errors.log</code>`:""}
      <br><button class="btn" type="button" data-connretry>Retry</button></div>`;
  }
  if (s.providers === null) return head + `<p class="muted">Loading…</p>`;

  const degraded = s.degraded ? `<div class="note w"><b>${esc(s.degraded)}</b></div>` : "";

  /* An authorization in flight is EPHEMERAL state, flagged per ADR-023 rather
     than rendered as if it had settled. Device flow shows a code to transcribe;
     a redirect flow has already opened a browser and has no code to show. */
  let tx = "";
  if (s.tx){
    /* The URL is shown as selectable TEXT, not as a button label. Putting it in
       the label produced a 221px button that, with Cancel beside it, needed
       more width than this pane has. It is also the thing a user may want to
       read or copy, which a button label does not support. */
    const uri = s.tx.verification_uri || "";
    const shown = uri.replace(/^https?:\/\//, "");
    tx = s.tx.mode === "device"
      ? `<div class="note conntx"><b>Enter this code</b>
         <div class="usercode">${esc(s.tx.user_code||"")}</div>
         <p class="txwhere">at <code>${esc(shown)}</code></p>
         <div class="txactions">
           <a class="btn" href="${esc(uri)}" target="_blank" rel="noreferrer">Open in browser</a>
           <button class="btn" type="button" data-conncancel>Cancel</button>
         </div>
         <p class="muted">Live — not yet durable. Waiting for you to approve.</p></div>`
      : `<div class="note conntx"><b>Approve in your browser</b>
         <p class="txwhere">A browser window has opened. Approve there and this completes.</p>
         <div class="txactions">
           <button class="btn" type="button" data-conncancel>Cancel</button>
         </div>
         <p class="muted">Live — not yet durable. Waiting for the callback.</p></div>`;
  }
  let txErr = "";
  if (s.txErr){
    const e = connError(s.txErr);
    txErr = `<div class="note w"><b>Could not start the connection.</b>
      <br>${esc(e.headline)}
      ${e.hint?`<br><span class="muted">${esc(e.hint)}</span>`:""}
      ${e.code?`<br><span class="muted">code: <code>${esc(e.code)}</code></span>`:""}</div>`;
  }

  return head + degraded + txErr + tx
    + `<div class="ptiles">${(s.providers||[]).map(providerTile).join("")
         }${mediatedTiles(s.mediated)}</div>`
    + connDetailPane();
};

/* ── events ──────────────────────────────────────────────────────────────
 * Delegated on `document`, not on `.rail` and not on the screen container.
 *
 * The first version wired these into the rail's click listener, where they
 * could never fire: that listener only sees clicks inside `.rail`, and every
 * control here lives in `#scBody`. The screen rendered perfectly and no button
 * did anything, because rendering and event handling are separate paths and
 * only one of them was wrong.
 *
 * `#scBody` is rebuilt by render() on every pass, so a listener attached to it
 * would be discarded with the element. Scoping in the guard keeps a stray
 * data-conn* attribute elsewhere from reaching these handlers.
 */
document.addEventListener("click", e => {
  if (!e.target.closest("#scBody")) return;
  const providerOf = el => el.dataset.provider || "github";

  const retry = e.target.closest("[data-connretry]");
  if (retry){ S.conn.err = null; S.conn.providers = null; loadConnectors(true); return; }

  const start = e.target.closest("[data-connstart]");
  if (start){ connStart(start.dataset.connstart); return; }

  const cancel = e.target.closest("[data-conncancel]");
  if (cancel){ connCancel(); return; }

  const open = e.target.closest("[data-connopen]");
  if (open){
    const id = open.dataset.connopen;
    if (S.conn.open === id){ S.conn.open = null; S.conn.openProvider = null; render(); }
    else loadConnectorDetail(providerOf(open), id);
    return;
  }

  const dis = e.target.closest("[data-conndis]");
  if (dis){ connDisconnect(providerOf(dis), dis.dataset.conndis); return; }

  const recheck = e.target.closest("[data-connrecheck]");
  if (recheck){ loadMediated(true); return; }

  const ref = e.target.closest("[data-connrefresh]");
  if (ref){ connRefreshRepos(providerOf(ref), ref.dataset.connrefresh); return; }
});
