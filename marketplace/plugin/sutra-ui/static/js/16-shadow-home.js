/* 16-shadow-home.js -- Focus > Shadow: the full view of the ONE thread
   (PLAN-100 S81-S90). Same S.shadowThread the overlay card renders; same
   server truth for missions, watches, memory. Renders honestly dark when
   the status endpoint answers non-200. */
"use strict";

/* one POST path for shadow surfaces: panel token attached, and a single
   retry after a token refresh -- the page outlives backend restarts. */
async function shadowPost(url, body){
  const go = () => fetch(url, { method: "POST",
    headers: { "content-type": "application/json",
      "X-Sutra-Panel": (typeof panelToken === "function" ? panelToken() : "") },
    body: JSON.stringify(body) });
  let r = await go();
  if (r.status === 403 && typeof refreshPanelToken === "function"
      && await refreshPanelToken()){
    r = await go();
  }
  return r;
}


/* attribute-context escaper (codex P2 fold): esc() is for text nodes;
   anything interpolated inside a quoted attribute goes through THIS, which
   also closes the quote-breakout vector. */
function escAttr(x){
  return String(x == null ? "" : x)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}


/* S83: ONE plane, two tabs, live counts. Pure. */
function shadowPlaneHtml(watching, missions, tab){
  const active = missions.filter(m =>
    ["running", "queued", "paused", "brief_confirm"].includes(m.state));
  const t = tab === "working" ? "working" : "watching";
  const head = `<div class="shtabs">
    <button class="btn shtab ${t === "watching" ? "on" : ""}" type="button"
      data-shtab="watching">Watching \u00b7 ${watching.length}</button>
    <button class="btn shtab ${t === "working" ? "on" : ""}" type="button"
      data-shtab="working">Working \u00b7 ${active.length}</button></div>`;
  if (t === "watching"){
    const rows = watching.map(sid => `
      <div class="shwatchrow" data-shwatch="${escAttr(sid)}">
        <span class="shobj">${esc(sid)}</span>
        <button class="btn" type="button" data-shunwatch="${escAttr(sid)}">Stop watching</button>
      </div>`).join("");
    return head + `<div class="shplane">${rows ||
      `<div class="shempty">Shadow is not watching any session yet.</div>`}</div>`;
  }
  const rows = active.map(m => `
    <div class="shmissionrow" data-shmissionrow="${escAttr(m.id)}">
      ${missionCardHtml(m)}
      <span class="shrowacts">
        ${m.state === "queued" ? `<button class="btn" type="button"
            data-shact="start_now" data-shmid="${escAttr(m.id)}">Start now</button>
          <button class="btn" type="button" data-shact="drop"
            data-shmid="${escAttr(m.id)}">Drop</button>` : ""}
        ${m.state === "paused" ? `<button class="btn" type="button"
            data-shact="resume" data-shmid="${escAttr(m.id)}">Resume</button>` : ""}
        ${["running", "paused"].includes(m.state) ? `<button class="btn"
            type="button" data-shact="stop" data-shmid="${escAttr(m.id)}">Stop</button>` : ""}
      </span>
    </div>`).join("");
  const finished = missions.filter(m =>
    ["failed", "stopped"].includes(m.state)).slice(-5).reverse();
  const fin = finished.map(m => `
    <div class="shmissionrow shfinished" data-shmissionrow="${escAttr(m.id)}">
      ${missionCardHtml(m)}
      <span class="shrowacts">
        <button class="btn" type="button" data-shact="retry"
          data-shmid="${escAttr(m.id)}">Retry</button>
        ${m.target_session ? `<button class="btn" type="button"
          data-shtakeover="${escAttr(m.target_session)}">Take over</button>` : ""}
      </span>
    </div>`).join("");
  return head + `<div class="shplane">${rows ||
    `<div class="shempty">No missions in flight.</div>`}${fin ? `
    <div class="shfinhead">Recent finished</div>` + fin : ""}</div>`;
}

/* S86/S87: the memory section. Unconfirmed rows are visibly inert; one tap
   confirms; revoke is the undo (archive-never-delete: revoked stays listed,
   struck through). */
function shadowMemoryHtml(rows){
  const items = (rows || []).map(r => {
    const dead = !!r.revoked_at;
    const inert = !r.confirmed && !dead;
    return `<div class="shmem ${dead ? "shmem-dead" : ""}" data-shmem="${escAttr(r.id)}">
      <span class="shprec">${esc(r.precedence || "")}</span>
      <span class="shmemtext">${esc(r.text || "")}</span>
      ${inert ? `<span class="shinert">unconfirmed \u00b7 inert</span>
        <button class="btn pri" type="button" data-shconfirm="${escAttr(r.id)}">Confirm</button>` : ""}
      ${r.confirmed && !dead ? `<button class="btn" type="button"
        data-shrevoke="${escAttr(r.id)}">Revoke</button>` : ""}
      ${dead ? `<span class="shinert">revoked</span>` : ""}
    </div>`;
  }).join("");
  return `<div class="shmemory">${items ||
    `<div class="shempty">Shadow has learned nothing yet. Confirmed
     instructions appear here.</div>`}</div>`;
}

/* the full thread: every message, mission cards inline, composer */
function shadowHomeHtml(){
  const dark = typeof S === "undefined" || S.shadowHomeDark;
  if (dark) return `
  <div class="zero"><h4>Shadow</h4>
    <p>Shadow is not enabled. Turn it on in Settings to get a chief of
    staff watching your sessions.</p></div>`;
  const thread = (S.shadowThread || []).map(t => `
    <div class="shmsg ${t.who === "founder" ? "shmine" : "shshadow"}">
      ${esc(t.text || "")}</div>`).join("");
  return `<div class="shhome">
    <div class="shthread">${thread ||
      `<div class="shempty">Ask Shadow anything \u2014 it sees your
       sessions, your missions, and what it has learned.</div>`}</div>
    ${shadowPlaneHtml(S.shadowWatching || [], S.shadowMissions || [],
                      S.shadowTab)}
    ${shadowMemoryHtml(S.shadowMemory || [])}
    <textarea class="shcompose" data-shhomecompose="1"
      placeholder="Talk to Shadow"></textarea>
  </div>`;
}

async function loadShadowHome(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  try {
    const st = await fetch("/api/shadow/status");
    if (!st.ok){ S.shadowHomeDark = true; return; }
    S.shadowHomeDark = false;
    const [w, m, i] = await Promise.all([
      fetch("/api/shadow/watches").then(r => r.ok ? r.json() : { watches: [] }),
      fetch("/api/shadow/missions").then(r => r.ok ? r.json() : { missions: [] }),
      fetch("/api/shadow/instructions").then(r => r.ok ? r.json()
                                                       : { instructions: [] }),
    ]);
    S.shadowWatching = w.watches || [];
    S.shadowMissions = m.missions || [];
    S.shadowMemory = i.instructions || [];
    if (typeof scheduleRender === "function") scheduleRender();
  } catch (e){ S.shadowHomeDark = true; }
}

if (typeof SCREENS !== "undefined"){
  SCREENS.shadow = () => {
    if (typeof S !== "undefined" && S.shadowHomeDark === undefined){
      loadShadowHome();
      return `<div class="zero"><h4>Shadow</h4><p>Looking\u2026</p></div>`;
    }
    return shadowHomeHtml();
  };
}
if (typeof TITLES !== "undefined"){
  TITLES.shadow = ["Shadow",
    "your chief of staff \u00b7 one conversation, everywhere"];
}

/* The home controls act (they rendered un-wired before -- the recurring
   disease, now cured surface by surface). One delegated listener. */
if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    const d = (ev.target && ev.target.dataset) || {};
    if (d.shtab){ if (typeof S !== "undefined") S.shadowTab = d.shtab;
      if (typeof scheduleRender === "function") scheduleRender(); return; }
    if (d.shtakeover){
      /* navigation, never mutation: land the founder where the delegate
         session can be resumed by hand */
      if (typeof S !== "undefined")
        S.pendingDeepLink = "sutra://session/" + d.shtakeover;
      if (typeof goDest === "function") goDest("chats");
      return;
    }
    if (d.shact && d.shmid) return shadowMissionAct(d.shmid, d.shact);
    if (d.shstart) return shadowMissionAct(d.shstart, "start_now");
    if (d.shunwatch) return shadowWatchSet(d.shunwatch, false);
    if (d.shconfirm) return shadowInstructionAct(d.shconfirm, "confirm");
    if (d.shrevoke) return shadowInstructionAct(d.shrevoke, "revoke");
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && ev.target && ev.target.dataset
        && ev.target.dataset.shhomecompose){
      ev.preventDefault && ev.preventDefault();
      const text = ev.target.value; ev.target.value = "";
      if (text && text.trim() && typeof sendToShadow === "function"){
        sendToShadow(text.trim()).then(() => {
          if (typeof loadShadowHome === "function") loadShadowHome();
          if (typeof scheduleRender === "function") scheduleRender();
        });
        if (typeof scheduleRender === "function") scheduleRender();
      }
    }
  });
}

async function shadowWatchSet(sid, watch){
  if (typeof fetch === "undefined") return;
  try {
    await shadowPost("/api/shadow/watches", "/api/shadow/watches");
  } catch (e) {}
  loadShadowHome();
}

async function shadowInstructionAct(id, action){
  if (typeof fetch === "undefined") return;
  try {
    await shadowPost("/api/shadow/instructions", "/api/shadow/instructions");
  } catch (e) {}
  loadShadowHome();
}
