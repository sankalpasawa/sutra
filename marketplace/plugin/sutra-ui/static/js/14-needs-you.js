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
/* Layout A (founder 2026-09-27): two lanes, what needs a decision and then
   FYI; every reason a plain sentence, never the code the row carries. */
const NY_REASON = {
  needs_founder: "Waiting for your answer",
  founder_confirm: "Waiting for your answer",
  autonomy_top_tier: "Needs your go-ahead before it runs",
  no_live_runtime: "Paused: its session closed. Resume when ready",
  error_during_execution: "Hit an error. Open to retry",
};
function nyHumanMeta(t){
  const s = String(t || "").trim();
  if (NY_REASON[s]) return NY_REASON[s];
  if (/app_restart|app restarted/i.test(s))
    return "Paused when the app restarted. Resume when ready";
  if (/^mission failed$/i.test(s)) return "Failed. Open to retry";
  if (/^mission stopped$/i.test(s)) return "Stopped. Open to retry";
  if (/^mission done$/i.test(s)) return "Done. The result is inside";
  if (/founder_confirm/i.test(s)) return "Waiting for your answer";
  const plain = s.replace(/_/g, " ");
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}
/* A stall row written before 2026-09-27 carries one generic title for every
   task; read it as what it means rather than showing it. */
const NY_OLD_STALL = /^mission may be stalled -- nothing from its session for (\d+) min/i;
function nyView(it){
  const old = NY_OLD_STALL.exec(String(it.title || ""));
  if (old) return { title: "A running task went quiet", why: "Silent for " + old[1] + " min" };
  return { title: String(it.title || it.item_id || ""),
           why: it.why_now ? nyHumanMeta(it.why_now) : "" };
}
/* the same test loadNeedsYou's alert dot uses */
function nyIsDecision(it){
  const id = String(it.item_id || "");
  return it.kind === "needs_decision" || it.kind === "rescue"
      || id.indexOf("rescue-") === 0 || id.indexOf("stall-") === 0;
}
/* one card per TASK: its mission when the row names one (a stall row's id
   does), else the old producer + title key */
function nyTaskKey(it){
  if (it.mission_id) return "m:" + it.mission_id;
  const id = String(it.item_id || "");
  if (id.indexOf("stall-") === 0 && id.length > 6) return "m:" + id.slice(6);
  return "t:" + String(it.producer || "") + "|" + String(it.title || it.item_id || "");
}
/* today reads as a clock, any other day as the day (the department tab's rule) */
const NY_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function nyWhen(ts){
  const n = Number(ts) || 0;
  if (!n) return "";
  const d = new Date(n < 1e12 ? n * 1000 : n), t = new Date();
  if (d.toDateString() !== t.toDateString()) return d.getDate() + " " + NY_MON[d.getMonth()];
  return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
}
/* decisions: the one waiting longest first; FYI: the newest first */
function nySplit(items){
  const dec = new Map(), fyi = new Map();
  for (const it of items || []) (nyIsDecision(it) ? dec : fyi).set(nyTaskKey(it), it);
  const at = it => Number(it.ts) || 0;
  return {
    decide: [...dec.values()].sort((a, b) =>
      (at(a) || Number.MAX_SAFE_INTEGER) - (at(b) || Number.MAX_SAFE_INTEGER)),
    fyi: [...fyi.values()].sort((a, b) => at(b) - at(a)),
  };
}
const NY_FYI_SHOWN = 3;
function nyAction(it){
  if (it.primary_action) return it.primary_action;
  if (String(it.item_id || "").indexOf("rescue-") === 0) return "Pick it up";
  if (String(it.item_id || "").indexOf("stall-") === 0) return "Look in";
  if (it.kind === "needs_decision") return "Open";
  return "View";
}
/* kept for any caller counting cards: one row per task, both lanes */
function nyDedupe(items){
  const lanes = nySplit(items);
  return lanes.decide.concat(lanes.fyi);
}
/* the producer is named only when it is not Shadow: on Shadow's own cards
   the tag said nothing the page did not */
function nyProdTag(it){
  const prod = String(it.producer || "");
  if (!prod || prod.toLowerCase() === "shadow") return "";
  return `<span class="nyprod">${esc(prod.charAt(0).toUpperCase() + prod.slice(1).toLowerCase())}</span>`;
}
function nyCardHtml(it){
  const v = nyView(it), act = nyAction(it), when = nyWhen(it.ts);
  /* seen = opened, not answered: the card stays, drawn lighter (founder
     2026-09-16); the state is a class so the look is css, not words */
  return `
    <div class="nycard${it.state === "seen" ? " seen" : ""}"
         data-deeplink="${escAttr(it.deep_link || "")}"
         data-itemid="${escAttr(it.item_id || "")}">
      <div class="nyhead">${nyProdTag(it)}<span class="nytitle">${esc(v.title)}</span>${
        when ? `<span class="nytime">${esc(when)}</span>` : ""}</div>
      ${v.why ? `<div class="nywhy">${esc(v.why)}</div>` : ""}
      ${act ? `<button class="btn pri nyact" type="button"
         data-nyact="${escAttr(it.item_id || "")}">${esc(act)}</button>` : ""}
    </div>`;
}
/* an update is one line: the task, what happened, when; the row opens it */
function nyFyiHtml(it){
  const v = nyView(it), when = nyWhen(it.ts);
  return `
    <div class="nyfyi${it.state === "seen" ? " seen" : ""}"
         data-deeplink="${escAttr(it.deep_link || "")}"
         data-itemid="${escAttr(it.item_id || "")}">${nyProdTag(it)}<span class="nyfyit">${esc(v.title)}</span>${
      v.why ? `<span class="nyfyiw">${esc(v.why)}</span>` : ""}${
      when ? `<span class="nytime">${esc(when)}</span>` : ""}</div>`;
}
/* both lanes; "" when there is nothing at all. A lane with nothing in it is
   not drawn: the greeting line already says nothing needs you. */
function needsYouHtml(items){
  const { decide, fyi } = nySplit(items);
  if (!decide.length && !fyi.length) return "";
  let out = "";
  if (decide.length)
    out += `<section class="nylane nydecide"><h5 class="nylaneh">Needs your decision</h5>
      <div class="nyfeed">${decide.map(nyCardHtml).join("")}</div></section>`;
  if (fyi.length){
    const all = typeof S !== "undefined" && S && S.nyFyiAll;
    const shown = all ? fyi : fyi.slice(0, NY_FYI_SHOWN);
    const more = fyi.length - shown.length;
    out += `<section class="nylane nyfyilane"><h5 class="nylaneh">FYI</h5>
      <div class="nyfyis">${shown.map(nyFyiHtml).join("")}</div>${
      more > 0 ? `<button class="btn nymore" type="button" data-nymore="1">Show ${more} more</button>` : ""}</section>`;
  }
  return out;
}

/* S60: a card click deep-links straight into the owning thread. The Shadow
   home lands in P6; until then the link records intent and moves to Focus --
   navigation, never mutation. */
function openNeedsYouItem(link, itemId){
  /* opening marks the card SEEN, never handled (founder 2026-09-16: "once
     I click on something and it takes me there, but I have not approved
     it, it should not go away"). The card stays on Now until its task
     moves on; the cached list is kept and re-stated so the card does not
     blink away before the next poll. Fire-and-forget. */
  if (itemId && typeof shadowPost === "function"){
    try {
      shadowPost("/api/shadow/feed/handle", { item_id: itemId }).catch(() => {});
    } catch (e) {}
    if (typeof S !== "undefined" && Array.isArray(S.needsYou))
      for (const it of S.needsYou)
        if (it && it.item_id === itemId && it.state === "new") it.state = "seen";
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
    /* Repaint only when the answer CHANGED. This poll answers every ~2 s on
       an idle Now screen (the 4 s ticker plus SCREENS.now's own re-poll), and
       every answer scheduled a wholesale #panes rebuild -- measured 2026-09-16
       at 410-580 ms each, once a second, on a screen where nothing had
       happened. A press that lands inside such a rebuild is queued; a press
       whose button is replaced between mousedown and mouseup never becomes a
       click. The comparison is on the serialised items, so a status flip or a
       new item still repaints; the same feed twice does not. */
    const before = S._needsYouKey;
    if (doc === "err"){ S.needsYou = S.needsYou || []; }
    else S.needsYou = doc ? (doc.items || []) : null;
    let key;
    try { key = JSON.stringify(S.needsYou); } catch (e) { key = String(Date.now()); }
    S._needsYouKey = key;
    const changed = before === undefined || key !== before;
    if (doc && typeof shadowDotAlerts === "function"){
      const alerts = (doc.items || []).filter(it => it.state === "new"
        && (it.kind === "needs_decision"
            || String(it.item_id || "").indexOf("rescue-") === 0
            || String(it.item_id || "").indexOf("stall-") === 0)).length;
      shadowDotAlerts(alerts);
    }
    if (changed && typeof scheduleRender === "function") scheduleRender();
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
  /* Layout A: Shadow's answer sits in the page, just above the box, so the
     box itself stays one row high while it is pinned to the bottom */
  const answer = (reply || cards) ? `<div class="nyasked">
    ${reply ? `<div class="shmsg shshadow nyreply">${reply}</div>` : ""}
    ${cards ? `<div class="nydrafts">${cards}</div>` : ""}
    ${(c.missions || []).length > 1 ? `<div class="nydraftacts">
      <button class="btn pri" type="button" data-nystartall="1"${
        c.busy ? " disabled" : ""}>Start all</button></div>` : ""}
  </div>` : "";
  return answer + `<div class="nyask" data-nyask="1">
    ${c.err ? `<div class="shnewerr">${esc(c.err)}</div>` : ""}
    <div class="shcompwrap">
      <textarea class="shcompose" data-nycomp="1" rows="2"
        placeholder="What do you have in mind?"${c.busy ? " disabled" : ""}>${esc(c.text || "")}</textarea>
      <button class="btn shsend" type="button" data-nysend="1"
        aria-label="Send"${c.busy ? " disabled" : ""}>↑</button>
    </div>
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
  /* intake: the box opens tasks; the server prefixes the line so Shadow
     answers with drafts, not with an answer */
  try { r = await shadowPost("/api/shadow/chat", { message: text, intake: true }); }
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
  const total = c.missions.length;
  const left = [];
  for (const m of c.missions){
    let ok = null;
    try { ok = await shadowMissionAct(m.id, "start_now"); } catch (e) { ok = null; }
    if (ok) n++; else left.push(m);
  }
  /* a draft that did not start stays on the page with its own Start, and the
     count says so (DeepSeek P2: "Started N" must never overstate) */
  c.busy = false; c.missions = left; if (!left.length) c.reply = "";
  if (typeof showNudge === "function")
    showNudge((n === total ? "Started " + n : "Started " + n + " of " + total)
              + (n === 1 ? " task" : " tasks") + " — in Focus › Shadow.");
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
    /* Layout A (founder 2026-09-27): ONE page in every state -- the
       greeting, the line that counts decisions only (an update is not a
       thing that needs you), the decisions, FYI, and the box pinned last.
       With nothing to decide the line says so and keeps the door to
       Shadow for anyone who used it. */
    const n = items ? nySplit(items).decide.length : 0;
    const hr = new Date().getHours();
    const g = hr < 12 ? "Good morning" : hr < 17 ? "Good afternoon"
                                       : "Good evening";
    const line = n
      ? `<b>${n} thing${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} you.</b> Everything else is handled.`
      : `Nothing needs you right now. <button class="nylink" type="button"
          data-nystart="1">Talk to Shadow</button>`;
    return `<div class="nynow"><div class="nygreet">${g}.</div>
      <div class="nysub">${line}</div>` +
      ((items && items.length) ? needsYouHtml(items) : "") + nowAskHtml() + `</div>`;
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
    if (t && t.dataset && t.dataset.nymore){
      /* FYI shows three; the rest on ask, until the app reloads */
      if (typeof S !== "undefined") S.nyFyiAll = true;
      if (typeof scheduleRender === "function") scheduleRender();
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
