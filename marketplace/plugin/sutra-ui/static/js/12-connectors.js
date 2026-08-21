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

S.conn = { providers: null, err: null, tx: null, txProvider: null, txErr: null,
           open: null, openProvider: null,
           repos: null, orgs: null, perms: null, events: null, busy: false };

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
  const wants = provider === "github"
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
      ${S.conn.repos !== null ? connRepos(provider, c) : ""}
      ${S.conn.orgs !== null ? connOrgs() : ""}
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
  if (!d || d._err) return "";
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
  if (!d) return "";
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
  if (!d || d._err) return "";
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
    tx = s.tx.mode === "device"
      ? `<div class="note conntx"><b>Enter this code</b>
         <div class="usercode">${esc(s.tx.user_code||"")}</div>
         <a class="btn" href="${esc(s.tx.verification_uri||"")}" target="_blank"
            rel="noreferrer">Open ${esc(s.tx.verification_uri||"")}</a>
         <button class="btn" type="button" data-conncancel>Cancel</button>
         <p class="muted">Live — not yet durable. Waiting for you to approve.</p></div>`
      : `<div class="note conntx"><b>Approve in your browser</b>
         <p>A browser window has opened. Approve there and this will complete.</p>
         <button class="btn" type="button" data-conncancel>Cancel</button>
         <p class="muted">Live — not yet durable. Waiting for the callback.</p></div>`;
  }
  const txErr = s.txErr ? `<div class="note w"><b>Could not start the connection.</b>
    <br><code>${esc(s.txErr)}</code></div>` : "";

  return head + degraded + txErr + tx
    + `<div class="ptiles">${(s.providers||[]).map(providerTile).join("")}</div>`
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

  const ref = e.target.closest("[data-connrefresh]");
  if (ref){ connRefreshRepos(providerOf(ref), ref.dataset.connrefresh); return; }
});
