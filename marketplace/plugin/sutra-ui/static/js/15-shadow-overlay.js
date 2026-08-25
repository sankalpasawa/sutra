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
  dot.setAttribute && dot.setAttribute("tabindex", "0");
  dot.dataset && (dot.dataset.shadowdot = "1");
  (document.body || document.documentElement).appendChild(dot);
  return dot;
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
    return true;
  }
  if ((ev.metaKey || ev.ctrlKey) && ev.shiftKey
      && String(ev.key).toLowerCase() === "s"){
    if (typeof S !== "undefined") S.shadowCardOpen = !S.shadowCardOpen;
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
    ${startable ? `<button class="btn pri" type="button"
        data-shstart="${escAttr(m.id || "")}">Start</button>` : ""}
  </div>`;
}

/* the card: compact view of the ONE thread + chips + free text always */
function shadowCardHtml(){
  const thread = (typeof S !== "undefined" && S.shadowThread) || [];
  const last = thread.slice(-6).map(t => `
    <div class="shmsg ${t.who === "founder" ? "shmine" : "shshadow"}">
      ${esc(t.text || "")}</div>`).join("");
  const chips = validChips((typeof S !== "undefined" && S.shadowChips) || []);
  const chipHtml = chips.length
    ? chips.map(c => `<button class="btn shchip" type="button"
        data-shchip="${escAttr(c)}">${esc(c)}</button>`).join("")
    : `<button class="btn shchip" type="button" data-shchip="Clarify what you meant">Clarify</button>`;
  const perm = _shadowStatus && _shadowStatus.permission_mode;
  return `<div class="shcard" data-shadowcard="1">
    ${perm ? `<div class="shperm">permissions: ${esc(perm)}</div>` : ""}
    <div class="shlog">${last || `<div class="shempty">Ask Shadow anything.</div>`}</div>
    <div class="shchips">${chipHtml}</div>
    <textarea class="shcompose" data-shcompose="1"
      placeholder="Talk to Shadow"></textarea>
  </div>`;
}

async function sendToShadow(text){
  if (typeof S === "undefined" || typeof fetch === "undefined") return null;
  if (isOwnTurn(text)) return null;               /* S75 self-loop guard */
  S.shadowThread.push({ who: "founder", text, ts: Date.now() });
  try {
    const r = await fetch("/api/shadow/chat", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: text }) });
    if (!r.ok){
      S.shadowThread.push({ who: "shadow",
        text: "(Shadow is not watching right now)", ts: Date.now() });
      return null;
    }
    const doc = await r.json();
    S.shadowThread.push({ who: "shadow", text: doc.reply, ts: Date.now() });
    return doc;
  } catch (e){
    S.shadowThread.push({ who: "shadow",
      text: "(Shadow is not reachable)", ts: Date.now() });
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
