/* chat_attention.js - the count in the tab title and one desktop notice per new thing that needs the owner (gap package attention;
   docs/notes/GAP-attention.md; the old app's agNotify rules, 17-agents.js).

     titleFor(base, n)        "(2) Sutra"; 0 gives the base back; a "(N) " already in front is replaced, never stacked
     baseOf(title)            the title without a leading "(N) "
     itemsOf(needs, heads, seen)   one entry per question or approval of GET /api/needs-you ("q:<message id>") and per Heads up problem the
                              owner has not marked seen ("p:<task id>"): {key, title, body, ref}. The words are fixed here; a team name is one
                              line without control characters.
     plan(state, items, env)  pure: -> {state, notify, wakeIn}. env {now (ms), focused, permission, minMs}.
                                - the first call is not news: everything listed then is settled silently;
                                - a new key becomes due minMs (20 s) after it was first seen, so a question answered within seconds makes no
                                  noise; wakeIn (ms) says when the next one falls due, null when none waits;
                                - a due key is settled once: announced only when the window is not focused and permission is "granted",
                                  otherwise silently (the owner is looking, or said no).
     offer(items, permission, declined)   true when the page should offer to turn notices on: something waits, the browser has not asked yet
                              ("default") and the owner did not say No thanks. Permission is asked only from that offer's button (a click),
                              never on load, and never again after a No.
     create({doc, win, Notification, storage, onOpen, minMs, timers, prefs, now}) -> {update(items), enable(), decline(), offered(), state()}
                              update sets the title and fires what plan() says, once per key across this browser's tabs (localStorage key
                              sutra:notified, every storage call in a try). Clicking a notice brings the window forward and calls onOpen(item).

   Gap package routines-limits (quiet hours and an hourly cap; docs/notes/GAP2-routines-limits.md; the old app's shadow overlay rules):
     windowActive(window, at)       the twin of ops/attention_prefs.window_active, run against tests/fixtures/quiet_hours_cases.json by both lanes:
                              {start, end} in HH:MM, inclusive at the start, exclusive at the end, wrapping midnight; no window is never quiet;
                              `at` is "HH:MM", minutes after midnight or a Date (local time)
     cleanQuiet(value)              the window as stored, or null for anything that is not one (start == end included)
     nudgeAllowed(history, nowMs, perHour)   a rolling hour: true while fewer than perHour pings were sent in the last 60 minutes. An unknown rate
                              (not a whole number) and a rate of 0 both say no: AN UNKNOWN RATE SUPPRESSES.
     itemsOf(needs, heads, seen, {finished: true})   also one "f:<task id>" item per Heads up row of finished work: a notice that a team is done.
     plan() env gains quiet (bool), nudgesPerHour (number or null) and history (ms of the finished pings of the last hour). During quiet hours nothing is
                              pushed; a finished notice also needs the cap; a question, an approval and a crash obey quiet hours only. A key that
                              falls due while quiet or over the cap is settled silently (no catch-up notice when quiet ends: the count in the title,
                              the strip and the pill never went away). plan() also returns `history`.
     create(...prefs) -> prefs() answers {quiet: {start, end} | null, nudges: number | null} (null or missing nudges: unknown, finished pings are
                              suppressed); the history of finished pings is kept in localStorage sutra:nudges so a reload does not refund the budget.
                              The count in the title is the questions, approvals and problems, never the finished notices.

   Nothing here sends anything anywhere: the Notification API is the browser's own. A classic script with ONE global, ChatAttention; in node it
   is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const cut = (v, n) => (v.length > n ? v.slice(0, n - 1) + "…" : v);

  const MIN_MS = 20000;                 // the old AG_NOTIFY_MIN_MS: a short wait stays silent
  const NOTIFIED_KEY = "sutra:notified";
  const DECLINED_KEY = "sutra:notify";
  const NUDGES_KEY = "sutra:nudges";
  const MAX_NOTIFIED = 200;
  const MAX_NUDGES = 50;
  const HOUR_MS = 3600000;
  const PREFIX = /^\(\d+\)\s+/;
  const HM = /^([01]\d|2[0-3]):([0-5]\d)$/;

  const baseOf = title => text(title).replace(PREFIX, "");
  function titleFor(base, n) {
    const plain = baseOf(base);
    const k = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
    return k > 0 ? "(" + k + ") " + plain : plain;
  }

  const isFinished = item => isObj(item) && /^f:/.test(text(item.key));

  // ---- quiet hours and the hourly cap (the twin of sutra_app/ops/attention_prefs.py)
  const minutesOf = hm => { const m = HM.exec(text(hm)); return m ? Number(m[1]) * 60 + Number(m[2]) : null; };

  function cleanQuiet(value) {
    if (!isObj(value) || Object.keys(value).length !== 2 || !hasOwn(value, "start") || !hasOwn(value, "end")) return null;
    const s = minutesOf(value.start);
    const e = minutesOf(value.end);
    if (s === null || e === null || typeof value.start !== "string" || typeof value.end !== "string" || s === e) return null;
    return {start: value.start, end: value.end};
  }

  function windowActive(window, at) {
    const w = cleanQuiet(window);
    if (w === null) return false;                                    // no window, or one that is not a window, is never quiet
    let minute;
    if (at instanceof Date) minute = at.getHours() * 60 + at.getMinutes();
    else if (typeof at === "string") minute = minutesOf(at);
    else minute = Number.isFinite(at) ? Math.floor(at) : null;
    if (minute === null) return false;
    const s = minutesOf(w.start);
    const e = minutesOf(w.end);
    return s < e ? (minute >= s && minute < e) : (minute >= s || minute < e);
  }

  function nudgeAllowed(history, nowMs, perHour) {
    if (typeof perHour !== "number" || !Number.isInteger(perHour) || perHour <= 0) return false;       // unknown or zero: stay quiet
    const recent = (Array.isArray(history) ? history : []).filter(t => Number.isFinite(t) && nowMs - t < HOUR_MS && nowMs - t >= 0);
    return recent.length < perHour;
  }

  function itemsOf(needs, heads, seen, opts) {
    const marks = isObj(seen) ? seen : {};
    const out = [];
    (Array.isArray(needs) ? needs : []).filter(isObj).forEach(n => {
      const id = text(n.message_id);
      if (!/^\d{1,16}$/.test(id)) return;
      const team = cut(clean(n.dept_name), 80);
      const body = n.kind === "approval" ? "Sutra needs your approval for a change to the org chart" :
        (team ? team + " has a question for you" : "A team has a question for you");
      out.push({key: "q:" + id, title: "Sutra", body, ref: {kind: n.kind === "approval" ? "approval" : "question", message_id: Number(id)}});
    });
    (Array.isArray(heads) ? heads : []).filter(h => isObj(h) && h.kind === "problem").forEach(h => {
      const id = text(h.task_id);
      if (!/^tsk_[0-9a-f]{12}$/.test(id) || marks[id] === true) return;
      out.push({key: "p:" + id, title: "Sutra", body: cut(clean(h.text), 200) || "A team ran into a problem", ref: {kind: "problem", task_id: id}});
    });
    if (isObj(opts) && opts.finished === true) {                       // a team is done: the one kind of notice the hourly cap governs
      (Array.isArray(heads) ? heads : []).filter(h => isObj(h) && h.kind === "finished").forEach(h => {
        const id = text(h.task_id);
        if (!/^tsk_[0-9a-f]{12}$/.test(id) || marks[id] === true) return;
        out.push({key: "f:" + id, title: "Sutra", body: cut(clean(h.text), 200) || "A team finished its work", ref: {kind: "finished", task_id: id}});
      });
    }
    return out;
  }

  function plan(state, items, env) {
    const e = isObj(env) ? env : {};
    const now = Number.isFinite(e.now) ? e.now : 0;
    const minMs = Number.isFinite(e.minMs) && e.minMs >= 0 ? e.minMs : MIN_MS;
    const s = isObj(state) && state.started === true ? state : {started: false, seen: {}, settled: {}};
    const seen = {};
    const settled = {};
    const notify = [];
    const history = (Array.isArray(e.history) ? e.history : []).filter(t => Number.isFinite(t) && now - t < HOUR_MS && now - t >= 0);
    let wakeIn = null;
    (Array.isArray(items) ? items : []).filter(i => isObj(i) && text(i.key) !== "").forEach(item => {
      const k = item.key;
      if (!s.started) {                                     // first sight is not news
        seen[k] = now;
        settled[k] = true;
        return;
      }
      seen[k] = hasOwn(s.seen, k) ? s.seen[k] : now;
      if (hasOwn(s.settled, k)) {
        settled[k] = true;
        return;
      }
      const due = seen[k] + minMs;
      if (now < due) {
        wakeIn = wakeIn === null ? due - now : Math.min(wakeIn, due - now);
        return;
      }
      settled[k] = true;
      if (e.focused === true || e.permission !== "granted" || e.quiet === true) return;       // looking, said no, or quiet hours: settled silently
      if (!isFinished(item)) notify.push(item);                                                // a question, an approval, a crash: quiet hours only
      else if (nudgeAllowed(history, now, e.nudgesPerHour)) { notify.push(item); history.push(now); }     // finished work: the hourly cap too
    });
    return {state: {started: true, seen, settled}, notify, wakeIn, history};
  }

  const offer = (items, permission, declined) => Array.isArray(items) && items.length > 0 && permission === "default" && declined !== true;

  function readList(storage, key) {
    try {
      const list = JSON.parse((storage && storage.getItem(key)) || "[]");
      return Array.isArray(list) ? list.filter(k => typeof k === "string") : [];
    } catch (e) {
      return [];
    }
  }

  function create(options) {
    const o = isObj(options) ? options : {};
    const doc = o.doc || root.document || null;
    const win = o.win || root;
    const N = o.Notification !== undefined ? o.Notification : (typeof root.Notification === "function" ? root.Notification : null);
    const storage = o.storage !== undefined ? o.storage : (() => { try { return root.localStorage; } catch (e) { return null; } })();
    const timers = o.timers || {setTimeout: (f, ms) => setTimeout(f, ms), clearTimeout: t => clearTimeout(t)};
    const minMs = Number.isFinite(o.minMs) ? o.minMs : MIN_MS;
    const onOpen = typeof o.onOpen === "function" ? o.onOpen : () => {};
    const now = typeof o.now === "function" ? o.now : () => Date.now();
    let state = null;
    let last = [];
    let timer = null;
    let fired = 0;

    const permission = () => (N && typeof N.permission === "string" ? N.permission : "unsupported");
    const focused = () => { try { return !!(doc && typeof doc.hasFocus === "function" && doc.hasFocus()); } catch (e) { return true; } };
    const declined = () => { try { return !!storage && storage.getItem(DECLINED_KEY) === "off"; } catch (e) { return false; } };

    // Once per key in this browser: another tab may have announced it already.
    function claim(key) {
      const list = readList(storage, NOTIFIED_KEY);
      if (list.includes(key)) return false;
      try { if (storage) storage.setItem(NOTIFIED_KEY, JSON.stringify(list.concat([key]).slice(-MAX_NOTIFIED))); } catch (e) { /* storage may be blocked */ }
      return true;
    }

    // true when a notice was made (false: no Notification API, another tab announced it, or the browser refused)
    function fire(item) {
      if (!N || !claim(item.key)) return false;
      try {
        const n = new N(item.title, {body: item.body, tag: "sutra-" + item.key});
        fired += 1;
        n.onclick = () => {
          try { if (win && typeof win.focus === "function") win.focus(); } catch (e) { /* nothing to focus */ }
          try { onOpen(item); } catch (e) { /* the page decides what to show */ }
          try { if (typeof n.close === "function") n.close(); } catch (e) { /* already closed */ }
        };
        return true;
      } catch (e) {
        return false;                    // a browser that refuses the notice: the title still counts
      }
    }

    // The owner's quiet hours and rate (routines-limits). Whatever cannot be read is unknown: no window (speak), no rate (finished pings suppressed).
    const readPrefs = () => { try { const p = typeof o.prefs === "function" ? o.prefs() : null; return isObj(p) ? p : {}; } catch (e) { return {}; } };
    const readHistory = () => {
      try { const list = JSON.parse((storage && storage.getItem(NUDGES_KEY)) || "[]"); return Array.isArray(list) ? list.filter(Number.isFinite) : []; } catch (e) { return []; }
    };
    const saveHistory = list => { try { if (storage) storage.setItem(NUDGES_KEY, JSON.stringify(list.slice(-MAX_NUDGES))); } catch (e) { /* storage may be blocked */ } };

    function update(items) {
      last = Array.isArray(items) ? items : [];
      const counted = last.filter(i => !isFinished(i));                  // finished notices are never counted: they are news, not a debt
      if (doc) doc.title = titleFor(doc.title, counted.length);
      const prefs = readPrefs();
      const at = now();
      const out = plan(state, last, {now: at, focused: focused(), permission: permission(), minMs, quiet: windowActive(prefs.quiet, new Date(at)),
        nudgesPerHour: prefs.nudges, history: readHistory()});
      state = out.state;
      const announced = out.notify.filter(fire);
      const unspent = out.notify.filter(isFinished).length - announced.filter(isFinished).length;       // a ping nobody saw does not use the hour's budget
      if (unspent > 0) out.history.splice(out.history.length - unspent, unspent);
      if (out.notify.some(isFinished)) saveHistory(out.history);
      if (timer !== null) timers.clearTimeout(timer);
      timer = out.wakeIn === null ? null : timers.setTimeout(() => { timer = null; update(last); }, out.wakeIn + 50);
      return out;
    }

    function enable() {
      if (!N || typeof N.requestPermission !== "function") return Promise.resolve(permission());
      try {
        return Promise.resolve(N.requestPermission()).then(() => permission(), () => permission());
      } catch (e) {
        return Promise.resolve(permission());
      }
    }

    function decline() {
      try { if (storage) storage.setItem(DECLINED_KEY, "off"); } catch (e) { /* storage may be blocked: the offer comes back next load */ }
    }

    return {
      update, enable, decline,
      offered: () => offer(last.filter(i => !isFinished(i)), permission(), declined()),
      state: () => ({plan: state, items: last.filter(i => !isFinished(i)).length, fired, permission: permission(), waiting: timer !== null}),
    };
  }

  const ChatAttention = {titleFor, baseOf, itemsOf, plan, offer, create, windowActive, cleanQuiet, nudgeAllowed, minutesOf, MIN_MS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatAttention;
  else root.ChatAttention = ChatAttention;
})(globalThis);
