/* attention_pill.js - a small "2 need you" pill in the corner of every page but Home (gap package attention; docs/notes/GAP-attention.md; the old
   app's corner card, 15-shadow-overlay.js applyDotState).

     pillHtml({count, problems, fresh})   '<a class="apill fresh" href="/" aria-label="2 need you, 1 to try again">2 need you <small>1 to try again</small></a>';
                                          "" when nothing counts. `fresh` (the count went up since the last paint) pulses it once; a calm pill is
                                          "quiet" and still shows the count: quiet stands the alarm down, it never hides the news.
     mount(host, {api, attention, storage, pollMs, hiddenPollMs, timers, doc})   reads GET /api/needs-you and GET /api/heads-up and paints the pill
                                          into `host`, then reads again every pollMs (5 s) while the page is in front and every hiddenPollMs (15 s)
                                          while it is not, and at once when it comes back to the front. With ChatAttention it also keeps the count in
                                          the tab title and sends the desktop notices. -> {refresh(), first, state(), destroy()}
     start()                              on a team page or the console (SutraCtx.boot.page "dept" or "console"): a fixed corner host appended
                                          to the body, then mount. Home has the strip and the badge, so the pill never starts there.

   It reads, it does not listen: a page keeps ONE event stream (the team page's views share theirs, DeptExt), and an open stream holds one of the
   browser's few connections to this host for as long as the tab is open. The count is the one Home shows (HeadsUpView.count): every question and
   approval plus every problem not marked "Got it". The link is to Home, where both lanes are. A classic script with ONE global, AttentionPill; in
   node it is module.exports and does not start by itself. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const whole = v => (Number.isFinite(v) && v > 0 ? Math.floor(v) : 0);
  const POLL_MS = 5000;
  const HIDDEN_POLL_MS = 15000;

  function pillHtml(state) {
    const s = isObj(state) ? state : {};
    const count = whole(s.count);
    if (count === 0) return "";
    const problems = Math.min(whole(s.problems), count);
    const words = count + (count === 1 ? " needs you" : " need you");
    const extra = problems > 0 ? problems + " to try again" : "";
    return '<a class="apill' + (s.fresh === true ? " fresh" : " quiet") + '" href="/" aria-label="' + esc(words + (extra ? ", " + extra : "")) + '">' +
      esc(words) + (extra ? " <small>" + esc(extra) + "</small>" : "") + "</a>";
  }

  function report(where, error) {
    if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("AttentionPill: " + where + " failed", error);
  }

  function storage() {
    try { return root.localStorage; } catch (e) { return null; }
  }

  function mount(host, options) {
    const o = isObj(options) ? options : {};
    const api = o.api;
    const HV = o.view || root.HeadsUpView || null;
    const doc = o.doc !== undefined ? o.doc : (root.document || null);
    const timers = o.timers || {setTimeout: (f, ms) => setTimeout(f, ms), clearTimeout: t => clearTimeout(t)};
    const pollMs = Number.isFinite(o.pollMs) && o.pollMs > 0 ? o.pollMs : POLL_MS;
    const hiddenMs = Number.isFinite(o.hiddenPollMs) && o.hiddenPollMs > 0 ? o.hiddenPollMs : HIDDEN_POLL_MS;
    const S = {needs: [], heads: [], shown: 0, painted: false, fetches: 0, timer: null, closed: false};
    const seen = () => (HV && typeof HV.loadSeen === "function" ? HV.loadSeen(o.storage !== undefined ? o.storage : storage()) : {});
    const counted = () => {
      const marks = seen();
      return {count: HV ? HV.count(S.needs, S.heads, marks) : S.needs.length, problems: HV ? HV.split(S.heads, marks).problems.length : 0, marks};
    };
    const hidden = () => !!(doc && doc.visibilityState === "hidden");

    function paint() {
      if (S.closed) return;
      const c = counted();
      const html = pillHtml({count: c.count, problems: c.problems, fresh: S.painted && c.count > S.shown});      // what was there on load is not news
      S.shown = c.count;
      S.painted = true;
      if (host) {
        host.innerHTML = html;
        host.hidden = html === "";
      }
      const att = o.attention;
      if (att && root.ChatAttention) {
        try { att.update(root.ChatAttention.itemsOf(S.needs, S.heads, c.marks)); } catch (e) { report("attention", e); }
      }
    }

    function schedule() {
      if (S.closed) return;
      if (S.timer !== null) timers.clearTimeout(S.timer);
      S.timer = timers.setTimeout(() => { S.timer = null; refresh().catch(e => report("refresh", e)); }, hidden() ? hiddenMs : pollMs);
    }

    // Both lists at once; one that cannot be read keeps what the pill had. The next read is scheduled whatever happened.
    async function refresh() {
      if (!api || S.closed) return false;
      S.fetches += 1;
      try {
        const [needs, heads] = await Promise.allSettled([api.get("/api/needs-you"), api.get("/api/heads-up")]);
        if (needs.status === "fulfilled") S.needs = Array.isArray(needs.value) ? needs.value.filter(isObj) : [];
        if (heads.status === "fulfilled") S.heads = Array.isArray(heads.value) ? heads.value.filter(isObj) : [];
        paint();
        return needs.status === "fulfilled" && heads.status === "fulfilled";
      } finally {
        schedule();
      }
    }

    const onVisible = () => { if (!hidden()) refresh().catch(e => report("refresh", e)); };
    if (doc && typeof doc.addEventListener === "function") doc.addEventListener("visibilitychange", onVisible);
    const first = refresh().catch(e => { report("refresh", e); return false; });

    function destroy() {
      S.closed = true;
      if (S.timer !== null) timers.clearTimeout(S.timer);
      S.timer = null;
      if (doc && typeof doc.removeEventListener === "function") doc.removeEventListener("visibilitychange", onVisible);
    }

    return {refresh, first, destroy, state: () => ({count: counted().count, shown: S.shown, fetches: S.fetches, waiting: S.timer !== null, closed: S.closed})};
  }

  let started = null;
  function start() {
    if (started !== null) return started;
    const doc = root.document;
    const ctx = root.SutraCtx;
    if (!doc || !doc.body || !ctx || !ctx.api) return null;
    const host = doc.createElement("div");
    host.id = "attnpill";
    host.className = "apillhost";
    host.setAttribute("role", "status");
    host.hidden = true;
    doc.body.appendChild(host);
    const attention = root.ChatAttention ? root.ChatAttention.create({}) : null;
    started = mount(host, {api: ctx.api, attention});
    return started;
  }

  const AttentionPill = {pillHtml, mount, start, POLL_MS, HIDDEN_POLL_MS};
  if (typeof module === "object" && module !== null && module.exports) {
    module.exports = AttentionPill;
  } else {
    root.AttentionPill = AttentionPill;
    const page = root.SutraCtx && isObj(root.SutraCtx.boot) ? root.SutraCtx.boot.page : "";
    if ((page === "dept" || page === "console") && root.document) {
      if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", start);
      else start();
    }
  }
})(globalThis);
