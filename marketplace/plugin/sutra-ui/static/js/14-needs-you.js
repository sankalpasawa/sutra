/* 14-needs-you.js -- the Now surface consumes the needs-you feed
   (PLAN-100 S59/S60/S62). RENDER-ONLY: this module draws cards from
   GET /api/shadow/feed and navigates; it produces nothing, decides nothing.
   With the feature dark the endpoint answers 403 and the honest placeholder
   below is what renders -- byte-for-byte the pre-existing empty state. */
"use strict";

/* attribute-context escaper (codex P2 fold): esc() is for text nodes;
   anything interpolated inside a quoted attribute goes through THIS, which
   also closes the quote-breakout vector. */
function escAttr(x){
  return String(x == null ? "" : x)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}


/* pure: items -> cards html. Pure so the node test asserts on real output
   without a DOM. */
/* mock v5 parity: cards speak founder language — never a raw enum, one card
   per thing, and every card brings an action for this moment. */
const NY_KIND = { needs_decision: "needs you", rescue: "needs you", info: "update" };
function nyHumanMeta(t){
  const s = String(t || "");
  if (/app_restart|app restarted/i.test(s))
    return "paused when the app restarted \u2014 resume when ready";
  if (/^mission failed$/i.test(s)) return "the mission failed \u2014 open to retry";
  if (/^mission stopped$/i.test(s)) return "stopped \u2014 open to retry";
  if (/^mission done$/i.test(s)) return "done \u2014 result inside";
  if (/founder_confirm/i.test(s)) return "waiting for your confirmation";
  return s.replace(/_/g, " ");
}
function nyAction(it){
  if (it.primary_action) return it.primary_action;
  if (String(it.item_id || "").indexOf("rescue-") === 0) return "Pick it up";
  if (String(it.item_id || "").indexOf("stall-") === 0) return "Look in";
  if (it.kind === "needs_decision") return "Open";
  return "View";
}
function nyDedupe(items){
  const seen = new Map();
  for (const it of items || [])
    seen.set(String(it.producer || "") + "|" + String(it.title || it.item_id || ""), it);
  return [...seen.values()];
}
function needsYouHtml(items){
  items = nyDedupe(items);
  if (!items || !items.length) return "";
  const rows = items.map(it => {
    const prod = String(it.producer || "");
    const act = nyAction(it);
    return `
    <div class="nycard" data-deeplink="${escAttr(it.deep_link || "")}"
         data-itemid="${escAttr(it.item_id || "")}">
      <div class="nyhead">
        <span class="nyprod">${esc(prod.charAt(0).toUpperCase() + prod.slice(1).toLowerCase())}</span>
        <span class="nykind">${esc(NY_KIND[it.kind] || String(it.kind || "").replace(/_/g, " "))}</span>
      </div>
      <div class="nytitle">${esc(it.title || "")}</div>
      ${it.why_now ? `<div class="nywhy">${esc(nyHumanMeta(it.why_now))}</div>` : ""}
      ${act ? `<button class="btn pri nyact" type="button"
         data-nyact="${escAttr(it.item_id || "")}">${esc(act)}</button>` : ""}
    </div>`; }).join("");
  return `<div class="nyfeed">${rows}</div>`;
}

/* S60: a card click deep-links straight into the owning thread. The Shadow
   home lands in P6; until then the link records intent and moves to Focus --
   navigation, never mutation. */
function openNeedsYouItem(link){
  if (typeof S !== "undefined") S.pendingDeepLink = link || null;
  if (typeof goDest === "function") goDest("focus");
}

/* S62: the nudge -- ephemeral, never navigates, never steals focus. */
function showNudge(text){
  if (typeof document === "undefined") return null;
  const el = document.createElement("div");
  el.className = "nudge";
  el.textContent = text || "";
  (document.body || document.documentElement).appendChild(el);
  setTimeout(() => { try { el.remove(); } catch (e) {} }, 6000);
  return el;
}

function loadNeedsYou(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S._needsYouBusy) return;
  S._needsYouBusy = true;
  fetch("/api/shadow/feed").then(r => r.ok ? r.json() : null).then(doc => {
    S._needsYouBusy = false;
    S.needsYou = doc ? (doc.items || []) : null;   /* null = feature dark */
    if (doc && typeof shadowDotAlerts === "function"){
      const alerts = (doc.items || []).filter(it => it.state === "new"
        && (it.kind === "needs_decision"
            || String(it.item_id || "").indexOf("rescue-") === 0
            || String(it.item_id || "").indexOf("stall-") === 0)).length;
      shadowDotAlerts(alerts);
    }
    if (typeof scheduleRender === "function") scheduleRender();
  }).catch(() => { S._needsYouBusy = false; S.needsYou = null; });
}

/* Override the placeholder registered in 05-chat.js: same empty state when
   the feed is dark or empty, cards when it speaks. Loading is lazy -- the
   first paint of the screen kicks the fetch; nothing polls. */
if (typeof SCREENS !== "undefined"){
  SCREENS.now = () => {
    if (typeof S !== "undefined" && S.needsYou === undefined) loadNeedsYou();
    const items = (typeof S !== "undefined" && S.needsYou) || null;
    if (items && items.length){
      /* mock v5: the module greets, then only what needs the founder */
      const n = nyDedupe(items).length;
      const hr = new Date().getHours();
      const g = hr < 12 ? "Good morning" : hr < 17 ? "Good afternoon"
                                         : "Good evening";
      return `<div class="nygreet">${g}.</div>
        <div class="nysub"><b>${n} thing${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} you.</b>
        Everything else is handled.</div>` + needsYouHtml(items);
    }
    return `
  <div class="zero"><h4>Now</h4>
    <p>Nothing needs you right now.</p>
    <p><button class="btn pri" type="button" data-nystart="1">Talk to
    Shadow</button></p>
  </div>`;
  };
}

if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (t && t.dataset && t.dataset.nystart){
      openNeedsYouItem("sutra://shadow/home");
      return;
    }
    const card = t && t.closest ? t.closest("[data-deeplink]") : null;
    if (card && !(t.closest && t.closest("[data-nyact]"))){
      openNeedsYouItem(card.dataset ? card.dataset.deeplink : null);
    }
  });
}
