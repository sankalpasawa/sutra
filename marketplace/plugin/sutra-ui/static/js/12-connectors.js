/* Connectors — the External World block's operator projection (ADR-023).
 *
 * Render-only over the connector service. This screen never sees a credential:
 * everything below is a projection the backend already stripped (ADR-034), and
 * the only write-backs are connector lifecycle actions the operator initiates.
 *
 * Truth-class discipline (ADR-023 Decision 1b): connector rows and audit events
 * are AUTHORITATIVE (they come from the connector database); a device-flow
 * transaction in progress is EPHEMERAL and is labelled as such rather than
 * presented as settled state.
 */

S.conn = { list: null, err: null, tx: null, txErr: null, open: null,
           repos: null, orgs: null, perms: null, events: null, busy: false };

async function apiDelete(path){
  const r = await fetch(API + path, { method:"DELETE" });
  if (!r.ok) throw await _fail(r, path);
  return r.json();
}

async function loadConnectors(force){
  if (S.conn.list && !force) return;
  try {
    const d = await apiGet("/api/connectors");
    S.conn.list = d.connectors || [];
    S.conn.degraded = d.degraded || null;
    S.conn.err = null;
  } catch (e) {
    /* The backend now returns a structured body for unexpected failures too,
       so an error here names what broke and where the traceback is, instead of
       being an opaque 500 the operator cannot act on. */
    S.conn.err = String(e.message || e);
    S.conn.list = [];
  }
  render();
}

async function loadConnectorDetail(id){
  S.conn.open = id;
  S.conn.repos = S.conn.orgs = S.conn.perms = S.conn.events = null;
  render();
  const [rep, org, perm, ev] = await Promise.allSettled([
    apiGet("/api/connectors/github/" + encodeURIComponent(id) + "/repositories"),
    apiGet("/api/connectors/github/" + encodeURIComponent(id) + "/organizations"),
    apiGet("/api/connectors/github/" + encodeURIComponent(id) + "/permissions"),
    apiGet("/api/connectors/github/" + encodeURIComponent(id) + "/events?limit=20"),
  ]);
  /* allSettled, not all: four independent endpoints, and a permissions read
     that throws must not discard a perfectly good repository list. */
  const val = r => r.status === "fulfilled" ? r.value : { _err: String(r.reason && r.reason.message || r.reason) };
  S.conn.repos = val(rep); S.conn.orgs = val(org);
  S.conn.perms = val(perm); S.conn.events = val(ev);
  render();
}

/* ── device flow ─────────────────────────────────────────────────────── */
async function connStart(){
  if (S.conn.busy) return;
  S.conn.busy = true; S.conn.txErr = null; render();
  try {
    S.conn.tx = await apiPost("/api/connectors/github/authorize", {});
    connPoll();
  } catch (e) { S.conn.txErr = String(e.message || e); }
  S.conn.busy = false; render();
}

async function connPoll(){
  const tx = S.conn.tx; if (!tx) return;
  const id = tx.transaction_id;
  const tick = async () => {
    if (!S.conn.tx || S.conn.tx.transaction_id !== id) return;   /* cancelled */
    let d;
    try { d = await apiGet("/api/connectors/github/authorize/" + encodeURIComponent(id)); }
    catch (e) { S.conn.txErr = String(e.message || e); S.conn.tx = null; render(); return; }
    if (d.status === "COMPLETED"){
      S.conn.tx = null; S.conn.list = null;
      await loadConnectors(true);
      if (d.connector_id) loadConnectorDetail(d.connector_id);
      return;
    }
    /* Honour the server's interval. Polling faster is what earns a secondary
       rate limit from GitHub. */
    setTimeout(tick, (d.poll_interval_seconds || 5) * 1000);
  };
  setTimeout(tick, (tx.poll_interval_seconds || 5) * 1000);
}

async function connCancel(){
  const tx = S.conn.tx; S.conn.tx = null; render();
  if (tx) { try { await apiDelete("/api/connectors/github/authorize/" + encodeURIComponent(tx.transaction_id)); } catch (e) {} }
}

async function connDisconnect(id){
  if (!confirm("Disconnect this GitHub account?\n\nSutra deletes its copy of the credentials. It cannot revoke the authorization on GitHub — you do that in GitHub settings."))
    return;
  try {
    const r = await apiDelete("/api/connectors/github/" + encodeURIComponent(id));
    S.conn.open = null; S.conn.list = null;
    await loadConnectors(true);
    if (r && r.revoke_instructions_url) S.conn.revokeUrl = r.revoke_instructions_url;
  } catch (e) { S.conn.err = String(e.message || e); render(); }
}

async function connRefreshRepos(id){
  S.conn.repos = null; render();
  try { S.conn.repos = await apiGet("/api/connectors/github/" + encodeURIComponent(id) + "/repositories?refresh=true"); }
  catch (e) { S.conn.repos = { _err: String(e.message || e) }; }
  render();
}

/* ── render ──────────────────────────────────────────────────────────── */
const CONN_STATUS = {
  ACTIVE:          ["ok",   "Connected"],
  PENDING:         ["warn", "Connecting…"],
  ERROR:           ["warn", "GitHub unreachable — retrying"],
  REAUTH_REQUIRED: ["warn", "Reconnect needed"],
  DISCONNECTED:    ["off",  "Not connected"],
};

function connCard(c){
  const [cls, label] = CONN_STATUS[c.status] || ["off", c.status];
  const reason = c.status_reason ? ` — ${esc(String(c.status_reason).toLowerCase().replace(/_/g," "))}` : "";
  const open = S.conn.open === c.id;
  return `<div class="conncard ${open?"open":""}">
    <div class="connhead">
      <span class="dot ${cls}"></span>
      <b>@${esc(c.account.username)}</b>
      ${c.label?`<span class="tag">${esc(c.label)}</span>`:""}
      <span class="connstat">${esc(label)}${reason}</span>
      <span class="sp"></span>
      <button class="btn" type="button" data-connopen="${esc(c.id)}">${open?"Hide":"Manage"}</button>
      <button class="btn danger" type="button" data-conndis="${esc(c.id)}">Disconnect</button>
    </div>
    <div class="connmeta">GitHub user id ${esc(c.account.id)} · connected ${esc((c.created_at||"").slice(0,10))}
      ${c.last_used_at?` · last used ${esc(c.last_used_at.slice(0,10))}`:""}</div>
    ${open?connDetail(c):""}
  </div>`;
}

function connDetail(c){
  return `<div class="conndetail">
    ${connRepos(c)}
    ${connOrgs()}
    ${connPerms()}
    ${connEvents()}
  </div>`;
}

function connRepos(c){
  const d = S.conn.repos;
  if (!d) return `<section><h4>Repositories</h4><p class="muted">Loading…</p></section>`;
  if (d._err) return `<section><h4>Repositories</h4><p class="err">${esc(d._err)}</p></section>`;
  const rows = d.repositories || [];
  if (!rows.length){
    /* Not installed is a DIFFERENT state from no repositories selected, and it
       has a different fix. Saying "no repositories" for both is what sends
       people hunting for a problem they do not have. */
    const notInstalled = d.empty_reason === "NOT_INSTALLED";
    return `<section><h4>Repositories</h4>
      <div class="note w"><b>${notInstalled?"Sutra is authorized but not installed.":"The installation selects no repositories."}</b>
      ${notInstalled
        ? `Authorization proves who you are; installation is what grants repository access.`
        : `Add repositories to the installation to make them reachable.`}
      <br><a class="btn" href="${esc(d.install_url||"https://github.com/settings/installations")}" target="_blank" rel="noreferrer">Open GitHub installations</a></div></section>`;
  }
  return `<section><h4>Repositories <span class="ct">${rows.length}</span>
    <button class="btn" type="button" data-connrefresh="${esc(c.id)}">Refresh</button></h4>
    <table class="tbl"><thead><tr><th>Repository</th><th>Visibility</th><th>Your role</th><th>Capabilities</th></tr></thead><tbody>
    ${rows.map(r=>`<tr>
      <td><code>${esc(r.full_name)}</code>${r.archived?' <span class="tag">archived</span>':""}</td>
      <td>${esc(r.visibility)}</td><td>${esc(r.user_permission)}</td>
      <td title="${esc((r.capabilities||[]).join("\n"))}">${(r.capabilities||[]).length}</td></tr>`).join("")}
    </tbody></table>
    ${d.next_cursor?`<p class="muted">More available — paging is cursor-based.</p>`:""}</section>`;
}

function connOrgs(){
  const d = S.conn.orgs;
  if (!d) return "";
  if (d._err) return `<section><h4>Organizations</h4><p class="err">${esc(d._err)}</p></section>`;
  const rows = d.organizations || [];
  const personal = d.personal_installation;
  if (!rows.length && !personal) return "";
  const note = { ok:"installed", not_installed:"Sutra not installed",
                 sso_required:"SAML sign-in required", suspended:"installation suspended" };
  return `<section><h4>Organizations</h4><ul class="connlist">
    ${personal?`<li><span class="dot ok"></span><b>${esc(personal.account)}</b>
       <span class="muted">personal · ${esc(personal.repository_selection)} repositories</span></li>`:""}
    ${rows.map(o=>`<li><span class="dot ${o.access==="ok"?"ok":"warn"}"></span>
      <b>${esc(o.login)}</b> <span class="muted">${esc(note[o.access]||o.access)}</span></li>`).join("")}
  </ul></section>`;
}

function connPerms(){
  const d = S.conn.perms;
  if (!d) return "";
  if (d._err) return `<section><h4>Permissions</h4><p class="err">${esc(d._err)}</p></section>`;
  const kinds = ["deny","ask","allow"];   /* evaluation order, so the list reads as the engine reads it */
  const total = kinds.reduce((n,k)=>n+((d.rules||{})[k]||[]).length,0);
  return `<section><h4>Permissions</h4>
    <div class="note"><b>Mode: ${esc(d.mode)}</b> — rules are evaluated
      <b>deny → ask → allow</b>, first match wins. A broad deny beats a narrow allow.
      ${d.managed_rules_only?" Managed policy is the only rule source on this machine.":""}
      ${d.locks && d.locks.bypass_disabled?" Bypass mode is locked off.":""}</div>
    ${total? `<table class="tbl"><thead><tr><th>Rule</th><th>Effect</th><th>From</th></tr></thead><tbody>
      ${kinds.flatMap(k=>((d.rules||{})[k]||[]).map(r=>
        `<tr><td><code>${esc(r.rule)}</code></td><td class="k-${k}">${k}</td><td>${esc(r.source)}</td></tr>`)).join("")}
      </tbody></table>`
     : `<p class="muted">No rules configured. Reads inside the connected repositories are
        allowed; every write asks. Add rules in <code>~/.sutra/settings.json</code>.</p>`}
    ${(d.removed_tools||[]).length?`<p class="muted"><b>Removed from the agent entirely:</b>
      ${d.removed_tools.map(t=>`<code>${esc(t)}</code>`).join(" ")} — a bare deny rule removes a
      tool from the model's context, so it cannot be proposed at all.</p>`:""}
    ${(d.warnings||[]).length?`<div class="note w"><b>${d.warnings.length} rule${d.warnings.length===1?"":"s"} ignored:</b>
      <ul>${d.warnings.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></div>`:""}
  </section>`;
}

function connEvents(){
  const d = S.conn.events;
  if (!d || d._err) return "";
  const rows = d.events || [];
  if (!rows.length) return "";
  return `<section><h4>Recent activity <span class="muted">audited, hash-chained</span></h4>
    <table class="tbl"><thead><tr><th>When</th><th>Event</th><th>Result</th><th>Resource</th></tr></thead><tbody>
    ${rows.map(e=>`<tr><td>${esc((e.occurred_at||"").slice(0,19).replace("T"," "))}</td>
      <td>${esc(e.event_type)}</td><td class="r-${esc(String(e.result).toLowerCase())}">${esc(e.result)}</td>
      <td>${esc(e.resource||"")}</td></tr>`).join("")}
    </tbody></table></section>`;
}

SCREENS.connectors = () => {
  const s = S.conn;
  const head = `<div class="sc-head"><h3>${esc(TITLES.connectors[0])}</h3>
    <p>${esc(TITLES.connectors[1])}</p></div>`;

  if (s.err){
    /* Distinguish "the backend is not there" from "the backend answered and
       told us what went wrong". Different fixes -- and collapsing them into one
       message is what made the last failure undiagnosable. */
    const structured = /PANEL_INTERNAL_ERROR/.test(s.err);
    return head + `<div class="note w">
      <b>${structured ? "The connector service hit an unexpected error."
                      : "The connector service did not answer."}</b>
      <br><code>${esc(s.err)}</code>
      ${structured ? `<br>Full traceback: <code>~/.sutra/panel-errors.log</code>` : ""}
      <br><button class="btn" type="button" data-connretry>Retry</button></div>`;
  }
  if (s.list === null) return head + `<p class="muted">Loading…</p>`;

  const degraded = s.degraded ? `<div class="note w"><b>${esc(s.degraded)}</b></div>` : "";

  /* An in-flight device flow is EPHEMERAL state, flagged as such per ADR-023
     rather than rendered as if it had settled. */
  const tx = s.tx ? `<div class="note conntx"><b>Enter this code on GitHub</b>
    <div class="usercode">${esc(s.tx.user_code)}</div>
    <a class="btn" href="${esc(s.tx.verification_uri)}" target="_blank" rel="noreferrer">Open github.com/login/device</a>
    <button class="btn" type="button" data-conncancel>Cancel</button>
    <p class="muted">Live — not yet durable. Waiting for you to approve; this code expires.</p></div>` : "";

  const txErr = s.txErr ? `<div class="note w"><b>Could not start the connection.</b>
    <br><code>${esc(s.txErr)}</code></div>` : "";

  if (!s.list.length) return head + degraded + txErr + tx + `<div class="note">
    <b>No GitHub account connected.</b> Connecting authorizes Sutra to act on your
    behalf. Sutra never holds the credential in this window — it lives in your
    macOS Keychain, and the panel only ever sees connector state.
    <br><button class="btn primary" type="button" data-connstart ${s.busy?"disabled":""}>Connect GitHub</button></div>`;

  return head + degraded + txErr + tx +
    `<div class="connlisting">${s.list.map(connCard).join("")}</div>
     <button class="btn" type="button" data-connstart ${s.busy?"disabled":""}>Connect another account</button>`;
};
