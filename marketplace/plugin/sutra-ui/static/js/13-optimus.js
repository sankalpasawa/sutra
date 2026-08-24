/* 13-optimus.js — the daemon, visible (Focus > Optimus).

   A window over sutra-daemon's stores plus a request surface. The invariant
   (daemon PRD s6 + dual-lane consult 2026-08-24): this screen visualizes and
   REQUESTS; the daemon alone decides, mutates, logs and rejects. Every action
   here is a POST that shells the daemon CLI server-side — nothing in this
   file (or its backend) writes a store file directly.

   Trust folds carried from the consult:
   - approve is TWO-STEP: the operator types the route id back; no one-click
   - stop echoes the pid the screen saw (stale screens cannot kill blind)
   - every snapshot shows when it was taken (last sync)
   - asks are first-class: fallback/throwback rows render with their input id
     and evidence, because "you decide" is the daemon's contract, not a log. */

async function loadOptimus(force){
  if (S.optimus && !force) return;
  try {
    const snap = await apiGet("/api/optimus");
    S.optimus = { snap, at: new Date(), err: null, act: S.optimus?.act || null };
  } catch (e) {
    S.optimus = { snap: null, at: new Date(), err: String(e && e.message || e), act: null };
  }
  render();
}

function optChip(txt, cls){ return `<span class="chip ${cls||""}">${esc(txt)}</span>`; }

function optRouteRow(r){
  const bind = (r.department || r.charter)
    ? ` <span class="muted">[${esc(r.department || "-")} / ${esc(r.charter || "-")}]</span>` : "";
  const appr = r.status === "proposed"
    ? `<div class="opt-approve">
         <input type="text" class="wdin" placeholder="type ${esc(r.route_id)} to approve"
                data-optconfirm="${esc(r.route_id)}">
         <button class="btn" type="button" data-optapprove="${esc(r.route_id)}">Approve</button>
       </div>` : "";
  return `<div class="opt-route">
    <code>${esc(r.route_id)}</code> ${optChip(r.status, r.status === "approved" ? "ok" : "warn")}
    <code class="muted">${esc(r.pattern || "")}</code> &#8594; ${esc(r.workflow || "?")}
    <span class="muted">host=${esc(r.host || "?")}</span>${bind}${appr}</div>`;
}

SCREENS.optimus = () => {
  const o = S.optimus;
  if (!o) return `<div class="pad muted">Loading the daemon&#8217;s record&#8230;</div>`;
  if (o.err) return `<div class="pad"><p class="warn">Could not read the daemon: ${esc(o.err)}</p>
    <button class="btn" type="button" data-optrefresh>Retry</button></div>`;
  const s = o.snap;
  if (!s || !s.present) return `<div class="pad">
    <p>No daemon record yet at <code>${esc(s ? s.root : "~/.sutra-native")}</code>.</p>
    <p class="muted">Nothing is fabricated here: the screen renders only what the
    daemon has actually written. Ask something below, or start the daemon.</p>
    <p><button class="btn" type="button" data-optstart>Start daemon</button>
       <button class="btn" type="button" data-optrefresh>Refresh</button></p>
    <div class="opt-ask"><input type="text" class="wdin" id="optAskText"
      placeholder="ask the daemon (e.g. write a note on ...)">
      <button class="btn" type="button" data-optask>Ask</button></div></div>`;

  const pid = s.daemon.pid || {};
  const daemonLine = s.daemon.running
    ? `${optChip("running", "ok")} pid ${esc(String(pid.pid))} since ${esc(pid.started_at || "?")}
       <button class="btn danger" type="button" data-optstop="${esc(String(pid.pid))}">Stop pid ${esc(String(pid.pid))}</button>`
    : `${optChip("stopped", "warn")}
       <button class="btn" type="button" data-optstart>Start daemon</button>`;

  const asks = (s.asks || []).slice().reverse().slice(0, 10).map(a =>
    `<div class="opt-ask-row"><code class="muted">${esc(a.outbox_id || "")}</code>
       ${esc(a.ask_text || a.text || JSON.stringify(a).slice(0, 200))}</div>`).join("")
    || `<p class="muted">No asks waiting. When the daemon cannot handle something, it lands here — never silently.</p>`;

  const runs = (s.runs || []).slice().reverse().slice(0, 8).map(r =>
    `<div class="opt-run"><code>${esc(r.run_id || "?")}</code>
       ${optChip(r.outcome || "?", r.outcome === "pass" ? "ok" : "err")}
       ${esc(r.workflow_ref || "-")} <span class="muted">attempts ${esc(String(r.attempts ?? "?"))}</span></div>`).join("")
    || `<p class="muted">No runs recorded yet.</p>`;

  const stateBits = Object.entries(s.state_summary || {})
    .map(([k, v]) => `${esc(k)}: ${v}`).join(" &#183; ") || "nothing consumed yet";

  return `<div class="pad opt-wrap">
    <div class="opt-head">${daemonLine}
      <span class="muted">last sync ${esc(o.at.toLocaleTimeString())}</span>
      <button class="btn" type="button" data-optrefresh>Refresh</button></div>

    <h3>Ask</h3>
    <div class="opt-ask"><input type="text" class="wdin" id="optAskText"
      placeholder="ask the daemon (a registered route runs it; anything else comes back to you)">
      <button class="btn" type="button" data-optask>Ask</button></div>
    <p class="muted">pending: ${(s.pending_inputs || []).length} &#183; consumed: ${stateBits}
      ${s.inbox_malformed ? ` &#183; <span class="warn">${s.inbox_malformed} malformed line(s) quarantined</span>` : ""}</p>

    <h3>Decisions waiting on you</h3>${asks}

    <h3>Routes (the daemon&#8217;s features)</h3>
    ${(s.routes || []).map(optRouteRow).join("") || `<p class="muted">No routes yet — propose one below.</p>`}
    <details class="opt-build"><summary>Propose a new route (the builder)</summary>
      <div class="opt-form">
        ${["pattern", "workflow", "prompt_template", "department", "charter"].map(f =>
          `<input type="text" class="wdin" id="optP_${f}" placeholder="${f}">`).join("")}
        <select class="wdin" id="optP_host"><option>claude-bare</option><option>codex</option></select>
        <input type="text" class="wdin" id="optP_verify" placeholder="verify: template-id (e.g. grep-count)">
        <input type="text" class="wdin" id="optP_vargs" placeholder="verify args comma-separated (e.g. pattern=provenance,file={out},min=1)">
        <button class="btn" type="button" data-optpropose>Propose</button>
        <p class="muted">Proposing registers nothing — a route runs only after you approve it above, by typing its id.</p>
      </div></details>

    <h3>Recent runs</h3>${runs}
    ${o.act ? `<pre class="opt-act">${esc(o.act)}</pre>` : ""}
  </div>`;
};

async function optAct(label, fn){
  try {
    const r = await fn();
    S.optimus.act = label + ": " + (r && (r.out || JSON.stringify(r)) || "ok");
  } catch (e) {
    S.optimus.act = label + " FAILED: " + String(e && e.message || e);
  }
  await loadOptimus(true);
}

document.addEventListener("click", e => {
  if (e.target.closest("[data-optrefresh]")) { loadOptimus(true); return; }
  if (e.target.closest("[data-optstart]"))   { optAct("start", () => apiPost("/api/optimus/daemon/start", {})); return; }
  const stop = e.target.closest("[data-optstop]");
  if (stop) { optAct("stop", () => apiPost("/api/optimus/daemon/stop",
      { pid_confirm: parseInt(stop.dataset.optstop, 10) })); return; }
  if (e.target.closest("[data-optask]")) {
    const t = document.getElementById("optAskText");
    if (t && t.value.trim()) optAct("ask", () => apiPost("/api/optimus/ask", { text: t.value.trim() }));
    return;
  }
  const ap = e.target.closest("[data-optapprove]");
  if (ap) {
    const rid = ap.dataset.optapprove;
    const box = document.querySelector(`[data-optconfirm="${rid}"]`);
    /* operator resolved server-side (OS user, A3 single-operator) — never a
       hardcoded name in fleet code */
    optAct("approve " + rid, () => apiPost("/api/optimus/route-approve",
      { route_id: rid, confirm: box ? box.value.trim() : "" }));
    return;
  }
  if (e.target.closest("[data-optpropose]")) {
    const g = id => (document.getElementById(id) || {}).value || "";
    optAct("propose", () => apiPost("/api/optimus/route-propose", {
      pattern: g("optP_pattern"), workflow: g("optP_workflow"),
      host: g("optP_host") || "claude-bare", prompt_template: g("optP_prompt_template"),
      verify_template_id: g("optP_verify") || "file-exists", verify_version: "1",
      verify_args: g("optP_vargs") ? g("optP_vargs").split(",").map(x => x.trim()).filter(Boolean) : [],
      department: g("optP_department"), charter: g("optP_charter"),
    }));
    return;
  }
});
