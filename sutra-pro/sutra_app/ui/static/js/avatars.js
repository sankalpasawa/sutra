/* avatars.js - the team's five avatars in the style the owner chose, and the ring and badge that say what a teammate is doing.

   Two things, kept apart on purpose:

   1. The STYLE (Settings & logs > Appearance > Team avatars). "classic" is the faces Sutra Pro has always drawn (front_door.js on Home, the page's
      own `face` on a team page) and is the default everywhere. "illustrated" is the portrait artwork: a picture at 32 px and up, a simple mark
      below that. The choice is kept by the server for this app profile (GET/PUT /api/appearance, orchestrator/appearance.py) and reaches a page in
      its boot block, so it survives a restart and a new port. This file puts it on <html data-avatars> as soon as it loads.
   2. The ACTIVITY of one avatar, whatever the style: `data-act` is the ring (work: a turning arc; ask: a still amber arc; done: a full ring) and
      `data-badge` the small circle at the lower right (ask "?", msg, done "✓"). avatars.css draws both; the picture itself never moves.

     Avatars.style()                     "classic" | "illustrated", from <html data-avatars> (anything else is "classic")
     Avatars.apply(style)                set it on this page, tell the other open pages of this port (a storage event), repaint a team page
     Avatars.svg(key, size, opts)        the illustrated avatar as an <svg> string. opts {cls: "av", label: true|false}
     Avatars.face(key, size, classic, opts)  the avatar in the chosen style: `classic()` is called for the classic drawing
     Avatars.ring(inner, opts)           `inner` wrapped with its activity. opts {who, act, badge, id}; no act and no badge gives `inner` back
     Avatars.sync(root)                  after a paint: a turning arc carries on from where it was (a repaint does not restart it), and a badge
                                         fades in only when it is new for that avatar (`id`)
     Avatars.adopt()                     on a team page (J2's page, never hand-edited): its `face` draws the chosen style and every render is
                                         followed by decorate(), which reads the busy / ask classes the page already sets
     Avatars.PEOPLE, STYLES, CUT, TURN_MS

   Strings in, strings out for svg/face/ring; nothing from the wire goes into the markup (the keys are a fixed table).
   A classic script with ONE global, Avatars; in node it is module.exports and touches no document. */
(function (root) {
  "use strict";

  const STYLES = ["classic", "illustrated"];
  const DEFAULT = "classic";
  const CUT = 32;                 // px: the portrait from here up, the compact mark below
  const TURN_MS = 1150;           // one turn of the working arc
  const MSG_MS = 4000;            // how long a new message from Asha shows as a badge on a team page
  const MIRROR = "sutra:avatars"; // localStorage: only so the other open pages of this port hear a change; the server file is the truth
  const IMG = "/ui/img/avatars/";
  const KEYS = ["asha", "mira", "kabir", "dev", "nora"];
  // box: where the picture sits in the 64-unit disc (x, y, side), from the handoff's portrait-masks.json. mark: the compact silhouette, then its
  // cut-outs in the disc colour (the bun, the waves, the side part, the curls and smile, the bob and glasses are what tell the five apart).
  const PEOPLE = {
    asha: {name: "Asha", role: "Client Lead", n: 1, box: [1.2, 2.4, 61.6],
      mark: "M10 51c3-5 9-8 17-10v-4c-5-3-8-8-8-13 0-4 2-8 5-10a6 6 0 1 1 9-6c7 0 13 5 13 13l4 6c1 1 0 3-2 3h-2c-1 6-4 9-8 9v3c7 2 13 5 16 10a30 30 0 0 1-44-1Z", cut: ""},
    mira: {name: "Mira", role: "Writer", n: 2, box: [0, 0, 64],
      mark: "M5 50c5-5 11-6 15-8-6-3-8-8-7-14 0-8 4-15 10-19 8-5 18-4 24 2 5 5 6 11 5 18-1 5-1 10 3 14 6 6 4 13-2 17-4 2-9 1-12-1-6 2-18 1-25-2L5 50Z",
      cut: '<path fill="D" d="M24 24c-1 3-3 5-5 6l3 2c0 5 3 8 8 8-3 2-3 6-2 9-5-3-6-7-6-10-5-1-7-5-8-8 4-2 7-4 10-7Z"/>'},
    kabir: {name: "Kabir", role: "Designer", n: 3, box: [0, 0, 64],
      mark: "M8 53c3-5 10-8 17-10v-5c-4-3-6-8-7-12l-2-2c-3-7 1-12 6-14 5-2 11-3 17-2 7 1 10 6 9 12l-2 7c-1 7-4 10-7 13v3c7 2 14 5 17 10-7 6-15 9-24 9s-17-3-24-9Z",
      cut: '<path fill="D" d="M18 19c8 0 13-2 19-6l4 4c-8 4-16 6-23 5Z"/>'},
    dev: {name: "Dev", role: "Developer", n: 4, box: [0, 0, 64],
      mark: "M7 52c3-5 10-8 18-10v-3c-3-2-5-5-6-8-4 0-7-3-7-7-2-3-1-7 2-9-1-4 2-8 6-8 2-4 7-5 11-3 3-3 8-2 11 1 5 0 8 4 8 7 4 2 5 5 4 9 1 3-1 7-4 8-1 6-4 10-9 12v2c7 2 13 5 16 9a32 32 0 0 1-50 0Z",
      cut: '<path fill="D" d="M30 34c4 1 8 1 12-1-2 4-7 6-11 4Z"/>'},
    nora: {name: "Nora", role: "Quality check", n: 5, box: [0, 0, 64],
      mark: "M7 52c4-6 9-8 18-10v-3H10l3-22c2-7 9-12 18-12 10 0 17 5 19 13l5 21H39v3c9 2 14 4 18 10a31 31 0 0 1-50 0Z",
      cut: '<circle fill="D" cx="25" cy="28" r="4.2"/><circle fill="D" cx="38.5" cy="28" r="4.2"/>'}};
  const ACTS = ["work", "ask", "done"];
  const BADGES = ["ask", "msg", "done"];

  const doc = () => (root.document && root.document.documentElement ? root.document : null);
  const valid = s => (STYLES.indexOf(s) >= 0 ? s : DEFAULT);
  const keyOf = k => (Object.prototype.hasOwnProperty.call(PEOPLE, k) ? k : "asha");
  const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  /* ---------------------------------------------------------------- the style */
  function bootStyle() {
    try { return valid(JSON.parse(doc().getElementById("sutra-boot").textContent).avatars); } catch (e) { return DEFAULT; }
  }
  function style() {
    const d = doc();
    return valid(d && d.documentElement.dataset ? d.documentElement.dataset.avatars : "");
  }
  function setStyle(s) {
    const d = doc(), v = valid(s);
    if (d && d.documentElement.dataset) d.documentElement.dataset.avatars = v;
    return v;
  }
  function apply(s) {
    const v = setStyle(s);
    try { root.localStorage.setItem(MIRROR, v); } catch (e) {}
    refresh();
    return v;
  }

  /* ---------------------------------------------------------------- the illustrated avatar */
  function svg(key, size, opts) {
    const k = keyOf(key), p = PEOPLE[k], o = opts || {}, px = Number(size) > 0 ? Number(size) : 40;
    const disc = "var(--av-d" + p.n + ")", tone = "var(--av-m" + p.n + ")";
    const aria = o.label === true ? 'role="img" aria-label="' + esc(p.name + ", " + p.role) + '"' : 'aria-hidden="true"';
    const head = '<svg class="' + esc(o.cls || "av") + ' avill" data-face="' + k + '" width="' + px + '" height="' + px + '" viewBox="0 0 64 64" ' + aria + ">" +
      '<circle cx="32" cy="32" r="32" fill="' + disc + '"/>';
    if (px < CUT) return head + '<path fill="' + tone + '" d="' + p.mark + '"/>' + p.cut.replace(/fill="D"/g, 'fill="' + disc + '"') + "</svg>";
    return head + '<image href="' + IMG + k + '.webp" x="' + p.box[0] + '" y="' + p.box[1] + '" width="' + p.box[2] + '" height="' + p.box[2] + '" preserveAspectRatio="none"/></svg>';
  }
  function face(key, size, classic, opts) {
    return style() === "illustrated" || typeof classic !== "function" ? svg(key, size, opts) : classic();
  }

  /* ---------------------------------------------------------------- the activity */
  function ring(inner, opts) {
    const o = opts || {}, act = ACTS.indexOf(o.act) >= 0 ? o.act : "", badge = BADGES.indexOf(o.badge) >= 0 ? o.badge : "";
    if (!act && !badge) return inner;
    return '<span class="avact" data-who="' + keyOf(o.who) + '"' + (act ? ' data-act="' + act + '"' : "") + (badge ? ' data-badge="' + badge + '"' : "") +
      (o.id ? ' data-avid="' + esc(o.id) + '"' : "") + ">" + inner + "</span>";
  }
  const SEEN = new Map();         // avatar id -> the badge it showed at the last sync
  function sync(scope) {
    const d = doc(), at = scope && scope.querySelectorAll ? scope : d;
    if (!at) return;
    const now = root.performance && root.performance.now ? root.performance.now() : Date.now();
    at.querySelectorAll("[data-act], [data-badge]").forEach(el => {
      if (el.dataset.act === "work") el.style.setProperty("--avd", "-" + Math.round(now % TURN_MS) + "ms"); else el.style.removeProperty("--avd");
      const id = el.dataset.avid, badge = el.dataset.badge || "";
      if (!id) return;
      if (SEEN.has(id) && SEEN.get(id) !== badge && badge) el.classList.add("avfresh");
      SEEN.set(id, badge);
    });
  }

  /* ---------------------------------------------------------------- a team page (J2's page: its markup is not ours to edit, so it is read) */
  const MATES = "#steamlist .smate[data-mate], #sdock .sface[data-mate]";
  const T = {last: null, msg: "", until: 0, timer: 0, adopted: false};
  function doneOf(s, k) {
    const ready = typeof root.isReady === "function" && root.isReady(s) === true;
    if (k === "asha") return ready;
    if (k === "nora") return ready && Array.isArray(s.audits) && s.audits.length > 0;
    const parts = ((s.studio || {}).parts || []).filter(p => p && p.person === k);
    return parts.length > 0 && parts.every(p => p.st === "done");
  }
  function newMessage(s) {        // Asha said something to the owner since the last look: true for MSG_MS
    const said = (Array.isArray(s.allChat) ? s.allChat : []).filter(m => m && m.who === "identity" && m.to_user && !m.pause);
    const id = said.length ? String(said[said.length - 1].id) : "";
    const now = Date.now();
    if (T.msg !== "" && id !== "" && id !== T.msg) T.until = now + MSG_MS;
    if (id !== "") T.msg = id; else if (T.msg === "") T.msg = "0";
    return now < T.until;
  }
  function decorate(s) {
    const d = doc();
    if (!d || !s || typeof s !== "object") return;
    T.last = s;
    const msg = newMessage(s);
    d.querySelectorAll(MATES).forEach(el => {
      const k = keyOf(el.dataset.mate), host = el.classList.contains("sface") ? el : el.querySelector(".sface");
      if (!host) return;
      const rail = host !== el, busy = el.classList.contains("busy");
      const ask = rail ? el.classList.contains("ask") : !!host.querySelector(".pip");
      const done = !busy && !ask && doneOf(s, k);
      const act = ask ? "ask" : busy ? "work" : done ? "done" : "";
      const badge = ask ? "ask" : msg && k === "asha" ? "msg" : done ? "done" : "";
      host.dataset.who = k;
      host.dataset.avid = (rail ? "rail-" : "dock-") + k;
      if (act) host.dataset.act = act; else delete host.dataset.act;
      if (badge) host.dataset.badge = badge; else delete host.dataset.badge;
    });
    sync(d);
    if (msg && !T.timer && typeof root.setTimeout === "function") {
      T.timer = root.setTimeout(() => { T.timer = 0; if (T.last) decorate(T.last); }, Math.max(50, T.until - Date.now() + 20));
    }
  }
  function refresh() {            // a team page draws again in the style of now; Home repaints itself (home.js)
    const d = doc();
    if (!d || !T.adopted) return;
    try {
      const land = d.getElementById("slfaces"), head = d.getElementById("sphav");
      if (land && land.childElementCount) land.innerHTML = KEYS.map(k => root.face(k, 40, {prop: false, label: false})).join("");
      if (head && head.childElementCount) head.innerHTML = root.face("asha", 38, {label: false});
      d.querySelectorAll("j2-plan").forEach(h => { h.__k = null; });
      if (T.last && typeof root.renderSimple === "function") root.renderSimple(T.last);
    } catch (e) {}
  }
  function adopt() {
    if (T.adopted || typeof root.face !== "function" || typeof root.renderSimple !== "function") return false;
    const classicFace = root.face, render = root.renderSimple;
    root.face = function (k, size, o) {
      if (style() !== "illustrated") return classicFace(k, size, o);
      return svg(k, size, {cls: "av", label: !(o && o.label === false)});
    };
    root.renderSimple = function (s) {
      const out = render.apply(this, arguments);
      try { decorate(s); } catch (e) {}
      return out;
    };
    T.adopted = true;
    if (style() === "illustrated") refresh();
    return true;
  }

  function start() {
    const d = doc();
    if (!d) return;
    setStyle(bootStyle());
    if (d.head && !d.querySelector('link[href$="/ui/css/avatars.css"]')) {      // a team page's <head> is J2's: the sheet is added here
      const link = d.createElement("link");
      link.rel = "stylesheet"; link.href = "/ui/css/avatars.css";
      d.head.appendChild(link);
    }
    if (typeof root.addEventListener === "function") {
      root.addEventListener("storage", e => { if (e && e.key === MIRROR && e.newValue !== style()) { setStyle(e.newValue); refresh(); } });
    }
    adopt();
  }

  const Avatars = {STYLES, DEFAULT, CUT, TURN_MS, KEYS, PEOPLE, style, setStyle, apply, bootStyle, svg, face, ring, sync, adopt, decorate, refresh, doneOf};
  if (typeof module === "object" && module !== null && module.exports) module.exports = Avatars;
  else { root.Avatars = Avatars; start(); }
})(globalThis);
