/* chat_scroll.js - reading older messages is never interrupted (work package GAP-chat-comfort).

   A transcript follows its newest line until the reader moves up; then it stays where the reader is, a pill says how many messages arrived below,
   and a click takes the reader to the newest. A message the owner just sent always goes to the bottom. A chat that is closed and opened again
   comes back where it was read. This is the old app's parking (06-render.js _sessUserIntent and the scroll listener, founder: "when I go up,
   suddenly they go down"), its "New reply below" pill (01-state.js showJumpPill) and its pane memory (07-loaders.js paneScrollMem), with a count.

     idle()                       {parked: false, seenId: 0, pill: 0}: a reader that follows the newest line
     intent(state, event)         the next state after one input: {type: "wheel", deltaY} | {type: "touch"} | {type: "key", key} |
                                  {type: "scroll", top, prevTop, dist, lastId}. A wheel-up, a finger on the transcript, PageUp, ArrowUp or Home
                                  parks the reader at the gesture; a scroll that moved up is the reader's; a scroll that ends within SLOP px of
                                  the bottom follows again (the pill goes, everything up to lastId counts as seen).
     plan({parked, atBottom, grew, newCount, own, pill})
                                  {scroll: "bottom" | "keep", pill} for one repaint: the owner's own send goes to the bottom; nothing changed keeps
                                  everything; a parked reader, or one who was not at the bottom, keeps the place and sees the count; else bottom.
     settle(state, plan, dist, lastId)
                                  the state after that repaint: at the bottom (or the new lines fit in view, dist <= SLOP) nothing is unseen and
                                  the reader follows again; else the pill of the plan
     newCount(messages, seenId)   how many messages have an id above the last one the reader saw (a local, unsent line has no number: not counted)
     lastId(messages)             the highest numeric id
     pillHtml(n)                  "" for 0, else the button "1 new message below" / "N new messages below" (data-act="jump-latest")
     distance(el)                 px between the bottom of the view and the bottom of the content
     watch(el, onIntent)          listens on the transcript element (wheel, touchmove, keydown, scroll) and hands each input to onIntent as
                                  an event for intent(); returns a function that stops listening
     pin(el, following)           keeps a follower at the bottom when the transcript's box changes size (ResizeObserver; a no-op without it);
                                  returns a function that stops it
     behavior(matchMedia)         "auto" under prefers-reduced-motion, else "smooth": how the pill's jump scrolls
     remember(map, sid, view)     keep {top, pinned, seenId} of a chat being closed (view {top, scrollHeight, clientHeight, seenId}); a Map
                                  of at most MAX_REMEMBERED chats
     restore(map, sid, view)      {top (clamped to the new height), parked: true, seenId} for a chat that was read above its bottom, else null
                                  (a chat that was at its bottom opens at its bottom); the place is used once

   A classic script with ONE global, ChatScroll; in node it is module.exports. Nothing here reads the wire except numbers; pillHtml writes only
   digits and fixed words. */
(function (root) {
  "use strict";

  const SLOP = 24;
  const MAX_REMEMBERED = 50;
  const UP_KEYS = Object.freeze({PageUp: true, ArrowUp: true, Home: true});

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const num = v => (Number.isFinite(v) ? v : 0);
  const idOf = m => (isObj(m) && typeof m.id === "number" && Number.isFinite(m.id) ? m.id : null);

  const idle = () => ({parked: false, seenId: 0, pill: 0});

  function state(s) {
    const x = isObj(s) ? s : {};
    return {parked: x.parked === true, seenId: num(x.seenId), pill: Math.max(0, Math.floor(num(x.pill)))};
  }

  function intent(prev, event) {
    const s = state(prev);
    const e = isObj(event) ? event : {};
    if (e.type === "wheel") return num(e.deltaY) < 0 ? Object.assign(s, {parked: true}) : s;
    if (e.type === "touch") return Object.assign(s, {parked: true});
    if (e.type === "key") return UP_KEYS[e.key] === true ? Object.assign(s, {parked: true}) : s;
    if (e.type === "scroll") {
      if (num(e.dist) <= SLOP) return {parked: false, seenId: Math.max(s.seenId, num(e.lastId)), pill: 0};
      if (num(e.top) < num(e.prevTop) - 1) return Object.assign(s, {parked: true});
      return s;
    }
    return s;
  }

  function plan(input) {
    const p = isObj(input) ? input : {};
    const pill = Math.max(0, Math.floor(num(p.pill)));
    if (p.own === true) return {scroll: "bottom", pill: 0};
    if (p.grew !== true) return {scroll: "keep", pill};
    if (p.parked === true || p.atBottom === false) return {scroll: "keep", pill: Math.max(0, Math.floor(num(p.newCount)))};
    return {scroll: "bottom", pill: 0};
  }

  // The state after a repaint that followed `p` (from plan): at the bottom (scrolled there, or the new lines fit in view) everything is seen.
  function settle(prev, p, dist, last) {
    const s = state(prev);
    const q = isObj(p) ? p : {};
    if (q.scroll === "bottom" || num(dist) <= SLOP) return {parked: false, seenId: Math.max(s.seenId, num(last)), pill: 0};
    return Object.assign(s, {pill: Math.max(0, Math.floor(num(q.pill)))});
  }

  function lastId(messages) {
    return (Array.isArray(messages) ? messages : []).reduce((n, m) => { const id = idOf(m); return id !== null && id > n ? id : n; }, 0);
  }

  function newCount(messages, seenId) {
    const seen = num(seenId);
    return (Array.isArray(messages) ? messages : []).filter(m => { const id = idOf(m); return id !== null && id > seen; }).length;
  }

  function pillHtml(n) {
    const count = Math.max(0, Math.floor(num(n)));
    if (count === 0) return "";
    const words = count === 1 ? "1 new message below" : count + " new messages below";
    return '<button type="button" class="cjump-btn" data-act="jump-latest" aria-label="' + words + ', go to the newest">' + words + "</button>";
  }

  function distance(el) {
    if (!el) return 0;
    return Math.max(0, num(el.scrollHeight) - num(el.clientHeight) - num(el.scrollTop));
  }

  function watch(el, onIntent) {
    if (!el || typeof el.addEventListener !== "function" || typeof onIntent !== "function") return () => {};
    let prevTop = num(el.scrollTop);
    const passive = {passive: true};
    const handlers = [
      ["wheel", e => onIntent({type: "wheel", deltaY: e && e.deltaY}), passive],
      ["touchmove", () => onIntent({type: "touch"}), passive],
      ["keydown", e => onIntent({type: "key", key: e && e.key}), undefined],      // only while focus is inside the transcript: the box's own ArrowUp never parks
      ["scroll", () => { const top = num(el.scrollTop); const ev = {type: "scroll", top, prevTop, dist: distance(el)}; prevTop = top; onIntent(ev); }, passive],
    ];
    handlers.forEach(([type, fn, o]) => el.addEventListener(type, fn, o));
    return () => handlers.forEach(([type, fn, o]) => el.removeEventListener(type, fn, o));
  }

  // A follower stays at the bottom when the transcript's box changes size (the message box grows, a row appears under it): ResizeObserver.
  function pin(el, following) {
    const RO = root.ResizeObserver;
    if (!el || typeof RO !== "function" || typeof following !== "function") return () => {};
    const ro = new RO(() => { if (following()) el.scrollTop = el.scrollHeight; });
    ro.observe(el);
    return () => ro.disconnect();
  }

  function behavior(matchMedia) {
    try {
      return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    } catch (e) {
      return "auto";
    }
  }

  function remember(map, sid, view) {
    if (!(map instanceof Map) || typeof sid !== "string" || sid === "" || !isObj(view)) return null;
    const top = Math.max(0, num(view.top));
    const pinned = num(view.scrollHeight) - num(view.clientHeight) - top <= SLOP;
    map.delete(sid);
    map.set(sid, {top, pinned, seenId: num(view.seenId)});
    while (map.size > MAX_REMEMBERED) map.delete(map.keys().next().value);
    return map.get(sid);
  }

  function restore(map, sid, view) {
    if (!(map instanceof Map) || !map.has(sid)) return null;
    const mem = map.get(sid);
    map.delete(sid);
    if (!isObj(mem) || mem.pinned) return null;
    const v = isObj(view) ? view : {};
    const max = Math.max(0, num(v.scrollHeight) - num(v.clientHeight));
    return {top: Math.min(num(mem.top), max), parked: true, seenId: num(mem.seenId)};
  }

  const ChatScroll = {idle, intent, plan, settle, lastId, newCount, pillHtml, distance, watch, pin, behavior, remember, restore, SLOP, MAX_REMEMBERED};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatScroll;
  else root.ChatScroll = ChatScroll;
})(globalThis);
