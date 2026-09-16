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
function openNeedsYouItem(link, itemId){
  /* opening retires the card (fire-and-forget); the feed reloads lazily */
  if (itemId && typeof shadowPost === "function"){
    try {
      shadowPost("/api/shadow/feed/handle", { item_id: itemId })
        .then(() => { if (typeof S !== "undefined") S.needsYou = undefined; })
        .catch(() => {});
    } catch (e) {}
  }
  if (typeof S !== "undefined") S.pendingDeepLink = link || null;
  if (typeof shadowRouteDeepLink === "function")
    return shadowRouteDeepLink(link);
  if (typeof goDest === "function") goDest("focus");
}

/* S62: the nudge -- ephemeral, never navigates, never steals focus.
   `ms` is OPTIONAL and defaults to the 6000 every existing caller was written
   against: a second surface wanting a shorter life is not a reason to shorten
   theirs. */
function showNudge(text, ms){
  if (typeof document === "undefined") return null;
  const el = document.createElement("div");
  el.className = "nudge";
  el.textContent = text || "";
  (document.body || document.documentElement).appendChild(el);
  setTimeout(() => { try { el.remove(); } catch (e) {} }, ms || 6000);
  return el;
}

function loadNeedsYou(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return;
  if (S._needsYouBusy) return;
  S._needsYouBusy = true;
  fetch("/api/shadow/feed").then(r => r.ok ? r.json()
      : (r.status === 403 ? null : "err")).then(doc => {
    S._needsYouBusy = false;
    /* survey fold: 403 = feature dark (null); any OTHER failure keeps the
       last known items instead of masquerading as an empty feed */
    if (doc === "err"){ S.needsYou = S.needsYou || []; }
    else S.needsYou = doc ? (doc.items || []) : null;
    if (doc && typeof shadowDotAlerts === "function"){
      const alerts = (doc.items || []).filter(it => it.state === "new"
        && (it.kind === "needs_decision"
            || String(it.item_id || "").indexOf("rescue-") === 0
            || String(it.item_id || "").indexOf("stall-") === 0)).length;
      shadowDotAlerts(alerts);
    }
    if (typeof scheduleRender === "function") scheduleRender();
  }).catch(() => { S._needsYouBusy = false;
    S.needsYou = S.needsYou || []; });
}

/* ── v4: THE BOX (SHADOW-V3 v3.3, ADR-043) ─────────────────────────────
   "What do you have in mind?" is Shadow's one way in on Now. One message
   goes to the Now chat (POST /api/shadow/chat); the reply is Shadow's prose
   and one draft card per task it split out (`missions`, one fence per
   task). Start each card, or Start all. The cards above stay render-only;
   nothing here decides anything -- the drafts are the server's records. */
function nowChat(){
  const S_ = (typeof S !== "undefined") ? S : {};
  if (!S_.nowChat)
    S_.nowChat = { text: "", busy: false, err: null, reply: "", missions: [] };
  return S_.nowChat;
}

function nowAskHtml(){
  const c = nowChat();
  const cards = (c.missions || []).map(m =>
    (typeof missionCardHtml === "function") ? missionCardHtml(m) : "").join("");
  const reply = c.reply
    ? ((typeof shadowProseHtml === "function") ? shadowProseHtml(c.reply) : esc(c.reply))
    : "";
  return `<div class="nyask" data-nyask="1">
    <div class="shcompwrap">
      <textarea class="shcompose" data-nycomp="1" rows="2"
        placeholder="What do you have in mind?"${c.busy ? " disabled" : ""}>${esc(c.text || "")}</textarea>
      <button class="btn shsend" type="button" data-nysend="1"
        aria-label="Send"${c.busy ? " disabled" : ""}>↑</button>
    </div>
    ${reply ? `<div class="shmsg shshadow nyreply">${reply}</div>` : ""}
    ${cards ? `<div class="nydrafts">${cards}</div>` : ""}
    ${(c.missions || []).length > 1 ? `<div class="nydraftacts">
      <button class="btn pri" type="button" data-nystartall="1"${
        c.busy ? " disabled" : ""}>Start all</button></div>` : ""}
    ${c.err ? `<div class="shnewerr">${esc(c.err)}</div>` : ""}
  </div>`;
}

async function nowSend(){
  if (typeof fetch === "undefined" || typeof S === "undefined") return null;
  const c = nowChat();
  const text = String(c.text || "").trim();
  if (!text || c.busy) return null;
  c.busy = true; c.err = null;
  if (typeof scheduleRender === "function") scheduleRender();
  let r = null;
  try { r = await shadowPost("/api/shadow/chat", { message: text }); }
  catch (e){ r = null; }
  let body = null;
  try { body = (r && r.ok) ? await r.json() : null; } catch (e){ body = null; }
  c.busy = false;
  if (!body){
    c.err = r ? "Shadow could not take that (" + r.status + ")."
              : "Could not reach Shadow.";
  } else {
    c.text = "";
    c.reply = body.reply || "";
    c.missions = Array.isArray(body.missions) ? body.missions
               : (body.mission ? [body.mission] : []);
  }
  if (typeof scheduleRender === "function") scheduleRender();
  return body;
}

async function nowStartAll(){
  const c = nowChat();
  if (c.busy || !(c.missions || []).length
      || typeof shadowMissionAct !== "function") return 0;
  c.busy = true;
  if (typeof scheduleRender === "function") scheduleRender();
  let n = 0;
  for (const m of c.missions){
    try { if (await shadowMissionAct(m.id, "start_now")) n++; } catch (e) {}
  }
  c.busy = false; c.missions = []; c.reply = "";
  if (typeof showNudge === "function")
    showNudge("Started " + n + (n === 1 ? " task" : " tasks")
              + " — in Focus › Shadow.");
  if (typeof scheduleRender === "function") scheduleRender();
  return n;
}

/* Override the placeholder registered in 05-chat.js: same empty state when
   the feed is dark or empty, cards when it speaks.

   Loading is lazy -- the first paint of the screen kicks the fetch -- and
   from 2026-09-15 it also REFRESHES while the screen is open, at most once
   every NY_POLL_MS. Same defect and same cure as Shadow home: the feed
   producer already emits a needs_decision row the moment a mission blocks
   (shadow_runner's emit_mission_feed), but this consumer read once and
   cached, so a founder sitting on Now never saw it arrive.

   Conservative on purpose: one read every four seconds, never one per
   frame, only for the ACTIVE screen, and loadNeedsYou's own _needsYouBusy
   guard still drops anything that would overlap an in-flight fetch. What
   counts as NEEDS YOU is untouched -- this only changes WHEN the same list
   is fetched. */
const NY_POLL_MS = 4000;
let nyAt = 0;

/* Same missing driver, same cure as Shadow home: SCREENS.now only runs when
   render() runs, and render() is event-driven rather than a loop, so the
   throttle below never came round on an idle screen. This interval is the
   heartbeat; it calls loadNeedsYou() directly (whose completion already
   calls scheduleRender()) and clears itself the moment Now is no longer the
   active screen, mirroring ensureRunTicker in 01-state.js. loadNeedsYou's
   own _needsYouBusy guard still drops anything overlapping an in-flight
   fetch, and what qualifies as NEEDS YOU is untouched. */
let _nyTicker = null;

function nyOnScreen(){
  const S_ = (typeof S !== "undefined") ? S : {};
  return S_.screen === "now";
}

function ensureNeedsYouTicker(){
  if (_nyTicker || typeof setInterval === "undefined") return;
  _nyTicker = setInterval(() => {
    if (!nyOnScreen()){
      if (typeof clearInterval === "function") clearInterval(_nyTicker);
      _nyTicker = null;
      return;
    }
    try { loadNeedsYou(); } catch (e) {}
  }, NY_POLL_MS);
}

if (typeof SCREENS !== "undefined"){
  SCREENS.now = () => {
    ensureNeedsYouTicker();
    const nyNow = (typeof Date !== "undefined") ? Date.now() : 0;
    if (typeof S !== "undefined" && S.needsYou === undefined){
      nyAt = nyNow;
      loadNeedsYou();
    } else if (typeof S !== "undefined" && nyNow - nyAt >= NY_POLL_MS){
      nyAt = nyNow;
      loadNeedsYou();
    }
    const items = (typeof S !== "undefined" && S.needsYou) || null;
    if (items && items.length){
      /* mock v5: the module greets, then only what needs the founder */
      const n = nyDedupe(items).length;
      const hr = new Date().getHours();
      const g = hr < 12 ? "Good morning" : hr < 17 ? "Good afternoon"
                                         : "Good evening";
      return `<div class="nygreet">${g}.</div>
        <div class="nysub"><b>${n} thing${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} you.</b>
        Everything else is handled.</div>` + needsYouHtml(items) + nowAskHtml();
    }
    /* v4: when nothing needs you, the box is the page (the door to Shadow
       stays for anyone who used it) */
    return `
  <div class="zero"><h4>Now</h4>
    <p>Nothing needs you right now.</p>
    <p><button class="btn pri" type="button" data-nystart="1">Talk to
    Shadow</button></p>
  </div>` + nowAskHtml();
  };
}

if (typeof document !== "undefined" && document.addEventListener){
  /* v4: the box -- Enter sends (Shift+Enter is a newline), the text is kept
     across the background re-renders, and a draft started on its own card
     leaves the box's list (the start itself is the overlay's existing hook) */
  document.addEventListener("keydown", (ev) => {
    const d = (ev.target && ev.target.dataset) || {};
    if (ev.key === "Enter" && !ev.shiftKey && d.nycomp){
      ev.preventDefault && ev.preventDefault();
      nowChat().text = ev.target.value;
      nowSend();
    }
  });
  document.addEventListener("input", (ev) => {
    const d = (ev.target && ev.target.dataset) || {};
    if (d.nycomp) nowChat().text = ev.target.value;
  });
  document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (t && t.dataset && t.dataset.nystart){
      openNeedsYouItem("sutra://shadow/home");
      return;
    }
    if (t && t.dataset && t.dataset.nysend){ nowSend(); return; }
    if (t && t.dataset && t.dataset.nystartall){ nowStartAll(); return; }
    if (t && t.dataset && t.dataset.shstart){
      const c = nowChat();
      const mine = (c.missions || []).some(m => m.id === t.dataset.shstart);
      if (mine){
        /* a draft the box drew: this module starts it (the same existing
           action every Start uses) and stops the other document listeners
           from starting it a second time */
        c.missions = c.missions.filter(m => m.id !== t.dataset.shstart);
        if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();
        if (typeof shadowMissionAct === "function")
          shadowMissionAct(t.dataset.shstart, "start_now");
        if (typeof scheduleRender === "function") scheduleRender();
        return;
      }
    }
    /* the ACTION BUTTON routes too (founder's dead Open, root-caused
       2026-08-26: this branch excluded data-nyact and nothing else ever
       handled it -- the pill was dead by leftover design) */
    const act = t && t.closest ? t.closest("[data-nyact]") : null;
    if (act){
      const host = act.closest ? act.closest("[data-deeplink]") : null;
      openNeedsYouItem(host && host.dataset ? host.dataset.deeplink : null,
                       act.dataset.nyact
                         || (host && host.dataset ? host.dataset.itemid : null));
      return;
    }
    const card = t && t.closest ? t.closest("[data-deeplink]") : null;
    if (card){
      openNeedsYouItem(card.dataset ? card.dataset.deeplink : null,
                       card.dataset ? card.dataset.itemid : null);
    }
  });
}
