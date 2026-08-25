/* 15-shadow-overlay.js -- the Shadow overlay: dot + pill + card
   (PLAN-100 S65-S78). GATED BY THE SERVER: every capability behind
   GET /api/shadow/status; a 403 means this module mounts NOTHING -- the
   off-state invariant is "no shadow DOM exists", asserted by tests.

   ONE conversation: the card renders S.shadowThread, the same array the
   Focus home (P6) renders in full. There is no second chat state.

   Energy: nothing here polls. Status is fetched on boot and after each chat
   turn; the only timers are one-shot (pill auto-hide, nudge remove). */
"use strict";

/* attribute-context escaper (codex P2 fold): esc() is for text nodes;
   anything interpolated inside a quoted attribute goes through THIS, which
   also closes the quote-breakout vector. */
function escAttr(x){
  return String(x == null ? "" : x)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}


/* ---- pure helpers (node-tested directly) -------------------------------- */

/* S65: snap a dragged dot to the nearest corner, inside the safe zones */
function snapCorner(x, y, w, h, margin){
  const m = margin == null ? 16 : margin;
  return { left: x < w / 2 ? m : null,
           right: x < w / 2 ? null : m,
           top: y < h / 2 ? m : null,
           bottom: y < h / 2 ? null : m };
}

/* S67: at most 3 UNSOLICITED pills per hour; nudges are exempt. history is
   a list of epoch-ms; returns [allowed, prunedHistory]. */
function pillAllowed(history, now){
  const hour = 3600 * 1000;
  const recent = (history || []).filter(t => now - t < hour);
  return [recent.length < 3, recent];
}

/* S71: chips come from Shadow as text; a chip renders ONLY as verb+object
   (2-6 words, starts with a verb-looking token), max 3. Anything else falls
   back to Clarify (S72). */
function validChips(chips){
  const ok = [];
  for (const c of (chips || [])){
    const words = String(c || "").trim().split(/\s+/);
    if (words.length >= 2 && words.length <= 6 && /^[A-Za-z]/.test(words[0])){
      ok.push(words.join(" "));
      if (ok.length === 3) break;
    }
  }
  return ok;
}

/* S75: Shadow's watcher must never react to Shadow's own turns */
function isOwnTurn(text){
  return /^\[Shadow \u00b7/.test(String(text || ""));
}

/* S78: the dot's face for each status answer */
function dotState(status){
  if (!status) return { cls: "shdot-down", label: "Shadow is not watching" };
  if (status.watching) return { cls: "shdot-live", label: "Shadow is watching" };
  return { cls: "shdot-idle", label: "Shadow is idle" };
}

/* ---- state -------------------------------------------------------------- */
if (typeof S !== "undefined"){
  if (!S.shadowThread) S.shadowThread = [];   /* ONE thread, shared with P6 */
  if (S.shadowQuiet === undefined) S.shadowQuiet = false;
  if (!S._pillHistory) S._pillHistory = [];
}

/* ---- mounting (only after a 200 from status) ----------------------------- */
let _shadowStatus;

function mountShadowOverlay(){
  if (typeof document === "undefined" || typeof S === "undefined") return;
  if (S.shadowHideSession) return;                 /* S73 hide-for-session */
  if (document.querySelector && document.querySelector(".shdot")) return;
  const dot = document.createElement("div");
  const st = dotState(_shadowStatus);
  dot.className = "shdot " + st.cls;
  dot.setAttribute && dot.setAttribute("role", "button");
  dot.setAttribute && dot.setAttribute("aria-label", st.label);
  dot.setAttribute && dot.setAttribute("tabindex", "-1");  /* R3: click, not tab */
  const nb = _shadowStatus && _shadowStatus.active_missions;
  if (nb) dot.textContent = String(nb);                     /* R20: badge */
  dot.dataset && (dot.dataset.shadowdot = "1");
  if (dot.addEventListener) dot.addEventListener("click", toggleShadowCard);
  (document.body || document.documentElement).appendChild(dot);
  return dot;
}

/* the card MOUNTS (2.224.3 lesson repeated: html functions nobody renders
   are invisible). One wrapper div, replaced wholesale per state change. */
function renderShadowCard(){
  if (typeof document === "undefined" || typeof S === "undefined") return;
  const existing = document.querySelector && document.querySelector("[data-shcardwrap]");
  if (existing) existing.remove();
  if (!S.shadowCardOpen) return;
  const wrap = document.createElement("div");
  wrap.dataset && (wrap.dataset.shcardwrap = "1");
  wrap.innerHTML = shadowCardHtml();
  if (wrap.addEventListener){
    wrap.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey && ev.target
          && ev.target.dataset && ev.target.dataset.shcompose){
        ev.preventDefault && ev.preventDefault();
        const text = ev.target.value;
        ev.target.value = "";
        if (text && text.trim()) shadowSendAndRefresh(text.trim());
      }
    });
    wrap.addEventListener("click", (ev) => {
      const d = (ev.target && ev.target.dataset) || {};
      if (d.shchip) return shadowSendAndRefresh(d.shchip);
      if (d.shquiet){ S.shadowQuiet = !S.shadowQuiet; return renderShadowCard(); }
      if (d.shhidesess){
        S.shadowHideSession = true; S.shadowCardOpen = false;
        renderShadowCard();
        const dot = document.querySelector && document.querySelector(".shdot");
        if (dot && dot.remove) dot.remove();               /* R12: one control */
        return;
      }
      if (d.shstart) return shadowMissionAct(d.shstart, "start_now");
    });
  }
  (document.body || document.documentElement).appendChild(wrap);
  return wrap;
}

function toggleShadowCard(){
  if (typeof S === "undefined") return;
  S.shadowCardOpen = !S.shadowCardOpen;
  renderShadowCard();
}

async function shadowSendAndRefresh(text){
  renderShadowCard();               /* founder turn appears immediately */
  const doc = await sendToShadow(text);
  if (doc && doc.watching !== undefined){
    _shadowStatus = { watching: doc.watching,
                      permission_mode: (_shadowStatus || {}).permission_mode };
    const dot = document.querySelector && document.querySelector(".shdot");
    if (dot){ const st = dotState(_shadowStatus);
      dot.className = "shdot " + st.cls; }
  }
  renderShadowCard();
}

function bootShadowOverlay(){
  if (typeof fetch === "undefined") return;
  fetch("/api/shadow/status").then(r => {
    if (!r.ok) return null;                        /* dark: mount NOTHING */
    return r.json();
  }).then(status => {
    if (!status) return;
    _shadowStatus = status;
    mountShadowOverlay();
  }).catch(() => {});
}

/* S77: cmd-shift-S toggles the card; Esc closes (S66) */
function shadowKeyHandler(ev){
  if (ev.key === "Escape" && typeof S !== "undefined" && S.shadowCardOpen){
    S.shadowCardOpen = false;
    renderShadowCard();
    return true;
  }
  if ((ev.metaKey || ev.ctrlKey) && ev.shiftKey
      && String(ev.key).toLowerCase() === "s"){
    if (typeof S !== "undefined") S.shadowCardOpen = !S.shadowCardOpen;
    renderShadowCard();
    return true;
  }
  return false;
}

/* S70: a mission renders IN the thread as a card that updates in place --
   the state chip gates Start (only a confirmed brief can start). */
function missionCardHtml(m){
  if (!m) return "";
  const startable = m.state === "brief_confirm";
  return `<div class="shmission" data-shmission="${escAttr(m.id || "")}">
    <span class="shstate shstate-${esc(m.state || "")}">${esc(m.state || "")}</span>
    <span class="shobj">${esc(m.objective || "")}</span>
    <span class="shturns">${m.turns_used || 0}/${m.max_turns || "?"}</span>
    ${(m.done_when && m.done_when[0]) ? `<span class="shdone">done when:
      ${esc(m.done_when[0].check || "")}</span>` : ""}
    ${startable ? `<button class="btn pri" type="button"
        data-shstart="${escAttr(m.id || "")}">Start</button>` : ""}
  </div>`;
}

/* the card: compact view of the ONE thread + chips + free text always */
function shadowCardHtml(){
  const thread = (typeof S !== "undefined" && S.shadowThread) || [];
  const last = thread.slice(-6).map(t => t.mission
    ? missionCardHtml(t.mission)
    : `
    <div class="shmsg ${t.who === "founder" ? "shmine" : "shshadow"}">
      ${esc(t.text || "")}</div>`).join("");
  const chips = validChips((typeof S !== "undefined" && S.shadowChips) || []);
  const chipHtml = chips.length
    ? chips.map(c => `<button class="btn shchip" type="button"
        data-shchip="${escAttr(c)}">${esc(c)}</button>`).join("")
    : `<button class="btn shchip" type="button" data-shchip="Clarify what you meant">Clarify</button>`;
  const perm = _shadowStatus && _shadowStatus.permission_mode;
  return `<div class="shcard" data-shadowcard="1">
    <div class="shperm">sees: your sessions \u00b7 missions \u00b7 what it
      has learned${perm ? ` \u00b7 permissions: ${escAttr(perm)}` : ""}
      <button class="btn shhide" type="button" data-shquiet="1">${
        (typeof S !== "undefined" && S.shadowQuiet) ? "Unquiet" : "Quiet"}</button>
      <button class="btn shhide" type="button" data-shhidesess="1">Hide</button>
    </div>
    <div class="shlog">${last || `<div class="shempty">Ask Shadow anything.</div>`}</div>
    <div class="shchips">${chipHtml}</div>
    <textarea class="shcompose" data-shcompose="1"
      placeholder="Talk to Shadow"></textarea>
  </div>`;
}

async function sendToShadow(text){
  if (typeof S === "undefined" || typeof fetch === "undefined") return null;
  if (isOwnTurn(text)) return null;               /* S75 self-loop guard */
  if (S.shadowBusy){
    S.shadowThread.push({ who: "shadow", ts: Date.now(),
      text: "(one moment -- still answering the last message)" });
    return null;
  }
  S.shadowBusy = true;
  S.shadowThread.push({ who: "founder", text, ts: Date.now() });
  S.shadowThread.push({ who: "shadow", ts: Date.now(), busy: true,
    text: S.shadowBooted ? "thinking\u2026"
                         : "waking up (first message boots my session -- up "
                           + "to a minute)\u2026" });
  try {
    const r = await fetch("/api/shadow/chat", {
      method: "POST", headers: { "content-type": "application/json",
        "X-Sutra-Panel": (typeof panelToken === "function" ? panelToken() : "") },
      body: JSON.stringify({ message: text }) });
    S.shadowBusy = false;
    S.shadowThread = S.shadowThread.filter(t => !t.busy);
    if (!r.ok){
      S.shadowThread.push({ who: "shadow", ts: Date.now(),
        text: "(that failed: " + r.status + " -- try again, or check "
              + "Focus \u203a Shadow)" });
      return null;
    }
    S.shadowBooted = true;
    const doc = await r.json();
    S.shadowThread.push({ who: "shadow", text: doc.reply, ts: Date.now() });
    if (doc.chips) S.shadowChips = doc.chips;          /* R18: generated */
    if (doc.mission){                                   /* R19: card in-thread */
      S.shadowThread.push({ who: "shadow", mission: doc.mission,
                            ts: Date.now() });
    }
    if (doc.remembered){                                /* R6: honest inert */
      S.shadowThread.push({ who: "shadow", ts: Date.now(),
        text: "I will remember that once you confirm it in Focus > "
              + "Shadow > memory." });
    }
    return doc;
  } catch (e){
    S.shadowBusy = false;
    S.shadowThread = S.shadowThread.filter(t => !t.busy);
    S.shadowThread.push({ who: "shadow", ts: Date.now(),
      text: "(Shadow is not reachable -- is the app backend running?)" });
    return null;
  }
}

/* S67: the pill -- one line, auto-hide, rate-limited unless a nudge */
function showPill(text, opts){
  if (typeof document === "undefined" || typeof S === "undefined") return null;
  if (S.shadowQuiet) return null;                  /* S73 quiet switch */
  const isNudge = opts && opts.nudge;
  if (!isNudge){
    const [ok, pruned] = pillAllowed(S._pillHistory, Date.now());
    S._pillHistory = pruned;
    if (!ok) return null;
    S._pillHistory.push(Date.now());
  }
  const el = document.createElement("div");
  el.className = "shpill";
  el.textContent = text || "";
  (document.body || document.documentElement).appendChild(el);
  setTimeout(() => { try { el.remove(); } catch (e) {} }, 12000);
  return el;
}

if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("keydown", shadowKeyHandler);
}

/* THE BOOT CALL. Defining a boot function is not booting (the gap the
   founder saw: everything served, nothing called). Guarded so vm tests can
   load the module inert and drive boot explicitly. */
if (typeof document !== "undefined" && typeof fetch !== "undefined"
    && !(typeof globalThis !== "undefined" && globalThis.__SHADOW_NO_AUTOBOOT)){
  try { bootShadowOverlay(); } catch (e) {}
}

/* R19/R24: mission actions from any surface (card or home). */
async function shadowMissionAct(mid, action, extra){
  if (typeof fetch === "undefined") return null;
  try {
    const r = await fetch("/api/shadow/missions/" + mid + "/act", {
      method: "POST", headers: { "content-type": "application/json",
        "X-Sutra-Panel": (typeof panelToken === "function" ? panelToken() : "") },
      body: JSON.stringify(Object.assign({ action }, extra || {})) });
    const doc = r.ok ? await r.json() : null;
    if (typeof loadShadowHome === "function") loadShadowHome();
    renderShadowCard();
    return doc;
  } catch (e){ return null; }
}
