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
     create({doc, win, Notification, storage, onOpen, minMs, timers}) -> {update(items), enable(), decline(), offered(), state()}
                              update sets the title and fires what plan() says, once per key across this browser's tabs (localStorage key
                              sutra:notified, every storage call in a try). Clicking a notice brings the window forward and calls onOpen(item).

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
  const MAX_NOTIFIED = 200;
  const PREFIX = /^\(\d+\)\s+/;

  const baseOf = title => text(title).replace(PREFIX, "");
  function titleFor(base, n) {
    const plain = baseOf(base);
    const k = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
    return k > 0 ? "(" + k + ") " + plain : plain;
  }

  function itemsOf(needs, heads, seen) {
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
      if (e.focused !== true && e.permission === "granted") notify.push(item);
    });
    return {state: {started: true, seen, settled}, notify, wakeIn};
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

    function fire(item) {
      if (!N || !claim(item.key)) return;
      try {
        const n = new N(item.title, {body: item.body, tag: "sutra-" + item.key});
        fired += 1;
        n.onclick = () => {
          try { if (win && typeof win.focus === "function") win.focus(); } catch (e) { /* nothing to focus */ }
          try { onOpen(item); } catch (e) { /* the page decides what to show */ }
          try { if (typeof n.close === "function") n.close(); } catch (e) { /* already closed */ }
        };
      } catch (e) {
        /* a browser that refuses the notice: the title still counts */
      }
    }

    function update(items) {
      last = Array.isArray(items) ? items : [];
      if (doc) doc.title = titleFor(doc.title, last.length);
      const out = plan(state, last, {now: now(), focused: focused(), permission: permission(), minMs});
      state = out.state;
      out.notify.forEach(fire);
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
      offered: () => offer(last, permission(), declined()),
      state: () => ({plan: state, items: last.length, fired, permission: permission(), waiting: timer !== null}),
    };
  }

  const ChatAttention = {titleFor, baseOf, itemsOf, plan, offer, create, MIN_MS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatAttention;
  else root.ChatAttention = ChatAttention;
})(globalThis);
