/* 14-needs-you.js -- the Now surface consumes the needs-you feed
   (PLAN-100 S59/S60/S62). RENDER-ONLY: this module draws cards from
   GET /api/shadow/feed and navigates; it produces nothing, decides nothing.
   With the feature dark the endpoint answers 403 and the honest placeholder
   below is what renders -- byte-for-byte the pre-existing empty state. */
"use strict";

/* pure: items -> cards html. Pure so the node test asserts on real output
   without a DOM. */
function needsYouHtml(items){
  if (!items || !items.length) return "";
  const rows = items.map(it => `
    <div class="nycard" data-deeplink="${esc(it.deep_link || "")}"
         data-itemid="${esc(it.item_id || "")}">
      <div class="nyhead">
        <span class="nyprod">${esc(it.producer || "")}</span>
        <span class="nykind">${esc(it.kind || "")}</span>
      </div>
      <div class="nytitle">${esc(it.title || "")}</div>
      ${it.why_now ? `<div class="nywhy">${esc(it.why_now)}</div>` : ""}
      ${it.primary_action ? `<button class="btn pri nyact" type="button"
         data-nyact="${esc(it.item_id || "")}">${esc(it.primary_action)}</button>` : ""}
    </div>`).join("");
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
    if (items && items.length) return needsYouHtml(items);
    return `
  <div class="zero"><h4>Now</h4>
    <p>Nothing needs you right now.</p>
  </div>`;
  };
}

if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("click", (ev) => {
    const t = ev.target;
    const card = t && t.closest ? t.closest("[data-deeplink]") : null;
    if (card && !(t.closest && t.closest("[data-nyact]"))){
      openNeedsYouItem(card.dataset ? card.dataset.deeplink : null);
    }
  });
}
