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

/* Customer-voice helpers (P0). Honesty folds from the 2026-08-24 consult:
   the matcher is described truthfully ("starts with"), pass renders as
   "Done — checked" only because a pinned check actually ran, and raw
   evidence stays one glance away in muted text — friendly never means
   hidden. The route id at the approve boundary stays exact and technical:
   it IS the trust gate. */
function optWhen(pattern){
  const m = /^\^\((\w+(?:\|\w+)*)\)\s?/.exec(pattern || "");
  if (m) return "when your ask starts with " + m[1].split("|").map(w => `“${w}”`).join(" or ");
  const m2 = /^\^(\w+)\s?/.exec(pattern || "");
  if (m2) return `when your ask starts with “${m2[1]}”`;
  return null;
}
function optAskRow(a){
  const raw = a.ask_text || a.text || "";
  let kind = "your call", body = raw;
  const m = /^\[daemon:(\w+)\] input ([\w./-]+): ([\s\S]*)$/.exec(raw);
  if (m){
    kind = m[1] === "fallback" ? "new kind of request" : "couldn’t finish this";
    body = m[3];
  }
  return `<div class="opt-ask-row">${optChip(kind, "warn")} ${esc(body.slice(0, 260))}
    <div class="muted" style="font-size:11px">${esc(a.outbox_id || "")}</div></div>`;
}
function optRunRow(r){
  let took = "";
  if (r.ts_open && r.ts_close){
    const s0 = Date.parse(r.ts_open), s1 = Date.parse(r.ts_close);
    if (!isNaN(s0) && !isNaN(s1)) took = ` · took ${Math.max(1, Math.round((s1 - s0) / 1000))}s`;
  }
  const done = r.outcome === "pass";
  return `<div class="opt-run">${optChip(done ? "Done — checked" : "Handed back to you", done ? "ok" : "err")}
    ${esc((r.workflow_ref || "").split("@")[0] || "work")}${esc(took)}
    <span class="muted" style="font-size:11px">${esc(r.run_id || "")}</span></div>`;
}

function optRouteRow(r){
  const bind = (r.department || r.charter)
    ? `<div class="muted">${esc(r.department || "")}${r.department && r.charter ? " · " : ""}${esc(r.charter || "")}</div>` : "";
  const when = optWhen(r.pattern);
  const live = r.status === "approved";
  const appr = !live
    ? `<div class="opt-approve">
         <span class="muted">To switch this on, type its code <code>${esc(r.route_id)}</code>:</span>
         <input type="text" class="wdin" placeholder="${esc(r.route_id)}"
                data-optconfirm="${esc(r.route_id)}">
         <button class="btn" type="button" data-optapprove="${esc(r.route_id)}">Switch on</button>
       </div>` : "";
  return `<div class="opt-route">
    <b>${esc((r.workflow || "?").split("@")[0])}</b> ${optChip(live ? "on" : "waiting for you", live ? "ok" : "warn")}
    <div>${when ? esc(when) : `matches <code class="muted">${esc(r.pattern || "")}</code>`}</div>
    ${bind}
    <div class="muted" style="font-size:11px">${esc(r.route_id)} · runs on ${esc(r.host || "?")}</div>${appr}</div>`;
}

SCREENS.optimus = () => {
  const o = S.optimus;
  if (!o) return `<div class="pad muted">Loading the daemon&#8217;s record&#8230;</div>`;
  if (o.err) return `<div class="pad"><p class="warn">Could not read the daemon: ${esc(o.err)}</p>
    <button class="btn" type="button" data-optrefresh>Retry</button></div>`;
  const s = o.snap;
  if (!s || !s.present) return `<div class="pad">
    <p><b>Optimus hasn’t done anything yet.</b></p>
    <p class="muted">This screen only ever shows what really happened — nothing here is
    ever made up. Wake Optimus and ask for something to get started.</p>
    <p><button class="btn" type="button" data-optstart>Wake Optimus</button>
       <button class="btn" type="button" data-optrefresh>Refresh</button></p>
    <div class="opt-ask"><input type="text" class="wdin" id="optAskText"
      placeholder="Tell Optimus what you need… (try: write a note on …)">
      <button class="btn" type="button" data-optask>Ask</button></div></div>`;

  const pid = s.daemon.pid || {};
  const daemonLine = s.daemon.running
    ? `${optChip("Optimus is awake", "ok")}
       <button class="btn danger" type="button" data-optstop="${esc(String(pid.pid))}"
               title="process ${esc(String(pid.pid))} on this Mac, since ${esc(pid.started_at || "?")}">Put to sleep (${esc(String(pid.pid))})</button>`
    : `${optChip("Optimus is asleep", "warn")}
       <button class="btn" type="button" data-optstart>Wake Optimus</button>`;

  const asks = (s.asks || []).slice().reverse().slice(0, 10).map(optAskRow).join("")
    || `<p class="muted">Nothing needs you right now. Whenever Optimus can’t handle
        something on its own, it appears here — never silently dropped.</p>`;

  const runs = (s.runs || []).slice().reverse().slice(0, 8).map(optRunRow).join("")
    || `<p class="muted">Nothing finished yet.</p>`;

  const stateBits = Object.entries(s.state_summary || {})
    .map(([k, v]) => `${esc(k)}: ${v}`).join(" &#183; ") || "nothing consumed yet";

  return `<div class="pad opt-wrap">
    <div class="opt-head">${daemonLine}
      <span class="muted">last sync ${esc(o.at.toLocaleTimeString())}</span>
      <button class="btn" type="button" data-optrefresh>Refresh</button></div>

    <h3>Ask Optimus</h3>
    <div class="opt-ask"><input type="text" class="wdin" id="optAskText"
      placeholder="Tell Optimus what you need… (things it knows run by themselves; anything else comes back to you)">
      <button class="btn" type="button" data-optask>Ask</button></div>
    <p class="muted">${(s.pending_inputs || []).length ? `${(s.pending_inputs || []).length} waiting in line · ` : ""}so far: ${stateBits}
      ${s.inbox_malformed ? ` · <span class="warn">${s.inbox_malformed} garbled request(s) set aside</span>` : ""}</p>

    <h3>Waiting on you</h3>${asks}

    <h3>What Optimus knows how to do</h3>
    ${(s.routes || []).map(optRouteRow).join("") || `<p class="muted">Nothing yet — teach it something below.</p>`}
    <details class="opt-build"><summary>Teach Optimus something new</summary>
      <div class="opt-form">
        <input type="text" class="wdin" id="optP_pattern" placeholder="When an ask starts with… (e.g. ^reconcile )">
        <input type="text" class="wdin" id="optP_workflow" placeholder="Do it the registered way… (e.g. W-emi-reconcile@1.0.0)">
        <input type="text" class="wdin" id="optP_prompt_template" placeholder="Tell the worker what to do… (use {text} and {out})">
        <input type="text" class="wdin" id="optP_department" placeholder="Which department is this for? (optional)">
        <input type="text" class="wdin" id="optP_charter" placeholder="Under which charter? (optional)">
        <select class="wdin" id="optP_host"><option>claude-bare</option><option>codex</option></select>
        <details><summary class="muted">Advanced: how Optimus checks its own work</summary>
          <input type="text" class="wdin" id="optP_verify" placeholder="check type (e.g. grep-count)">
          <input type="text" class="wdin" id="optP_vargs" placeholder="check details (e.g. pattern=provenance,file={out},min=1)">
        </details>
        <button class="btn" type="button" data-optpropose>Suggest it</button>
        <p class="muted">Suggesting changes nothing — a new ability only switches on after you
        approve it above by typing its code. That step is deliberately yours alone.</p>
      </div></details>

    <h3>Recently done</h3>${runs}
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
