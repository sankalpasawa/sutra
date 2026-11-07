/* chat_draft.js - the message box keeps what the owner wrote: one draft per chat, and a box that grows with its text (work package GAP-chat-comfort).

   The owner types a long message, presses Esc, opens another node, switches a tab or reloads the page: the words come back as they were left, per
   chat, and only a send that the server accepted clears them. This is the old app's per-session composer text (S.composerText, 07-loaders.js
   inp.oninput) with the browser's storage behind it, so a reload keeps it too.

     create({storage, now})     the store; `storage` is a Storage-like object or a function that returns one (default: the page's localStorage,
                                looked up on each call), `now` a clock in ms (default Date.now). Every storage call is in try/catch: a private
                                window, a blocked or full storage just means no draft is kept, and nothing ever throws to the page.
         load(sid)              the draft of a chat, or "" (an expired one is dropped on the way)
         save(sid, text)        keep the text (true when a draft is kept); an empty or blank text removes the draft instead of writing it
         clear(sid)             forget the draft
         clearIf(sid, sent)     forget it when it is what was just sent (trimmed); a box the owner kept typing in keeps its newer words
         prune()                drop expired drafts and keep the newest MAX_CHATS
     grow(el, maxPx)            size a textarea to its text, from its CSS min-height up to maxPx (default 200), and let it scroll above that

   Only text is kept (never a file, never file bytes), at most MAX_CHARS characters (4 times the direct route's cap of 8000, so a draft the owner cannot send yet is not cut on reload), under the key sutra:draft:<sid>,
   for at most MAX_CHATS chats and TTL_DAYS days. A draft never leaves the browser. A chat id that is not a session id (letters, digits, _ and -, at
   most 64) is refused, so a hostile id cannot reach another key.

   A classic script with ONE global, ChatDraft; in node it is module.exports. */
(function (root) {
  "use strict";

  const PREFIX = "sutra:draft:";
  const MAX_CHARS = 32000;                // longer than a message can be (8000, chat_composer.js): a pasted log over the cap is kept whole, and Send then says why it cannot go
  const MAX_CHATS = 30;
  const TTL_DAYS = 14;
  const TTL_MS = TTL_DAYS * 24 * 60 * 60 * 1000;
  const MAX_PX = 200;
  const SID = /^[A-Za-z0-9_-]{1,64}$/;

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : "");
  const okSid = sid => typeof sid === "string" && SID.test(sid);

  function create(options) {
    const o = isObj(options) ? options : {};
    const now = typeof o.now === "function" ? o.now : () => Date.now();
    const storageOf = () => {
      try {
        if (typeof o.storage === "function") return o.storage();
        if (o.storage !== undefined) return o.storage;
        return root.localStorage;                       // reading the property itself throws in some blocked browsers
      } catch (e) {
        return null;
      }
    };
    const attempt = (fn, fallback) => {
      try {
        const s = storageOf();
        return s ? fn(s) : fallback;
      } catch (e) {
        return fallback;
      }
    };

    function read(s, sid) {
      const raw = s.getItem(PREFIX + sid);
      if (typeof raw !== "string") return null;
      let found;
      try { found = JSON.parse(raw); } catch (e) { return {bad: true}; }
      if (!isObj(found) || typeof found.t !== "string" || !Number.isFinite(found.at)) return {bad: true};
      return found;
    }

    function keys(s) {
      const out = [];
      const n = Number.isInteger(s.length) ? s.length : 0;
      for (let i = 0; i < n; i += 1) {
        const k = s.key(i);
        if (typeof k === "string" && k.startsWith(PREFIX)) out.push(k);
      }
      return out;
    }

    function load(sid) {
      if (!okSid(sid)) return "";
      return attempt(s => {
        const found = read(s, sid);
        if (found === null) return "";
        if (found.bad || now() - found.at > TTL_MS) { s.removeItem(PREFIX + sid); return ""; }
        return found.t.slice(0, MAX_CHARS);
      }, "");
    }

    function clear(sid) {
      if (!okSid(sid)) return false;
      return attempt(s => { s.removeItem(PREFIX + sid); return true; }, false);
    }

    function prune() {
      return attempt(s => {
        const t = now();
        const kept = [];
        keys(s).forEach(k => {
          let found = null;
          try { found = JSON.parse(s.getItem(k)); } catch (e) { found = null; }
          if (!isObj(found) || !Number.isFinite(found.at) || t - found.at > TTL_MS) s.removeItem(k);
          else kept.push([k, found.at]);
        });
        kept.sort((a, b) => b[1] - a[1]);
        kept.slice(MAX_CHATS).forEach(([k]) => s.removeItem(k));
        return Math.min(kept.length, MAX_CHATS);
      }, 0);
    }

    function save(sid, value) {
      if (!okSid(sid)) return false;
      const words = text(value);
      if (words.trim() === "") { clear(sid); return false; }      // true means a draft is kept now
      const ok = attempt(s => {
        s.setItem(PREFIX + sid, JSON.stringify({t: words.slice(0, MAX_CHARS), at: now()}));
        return true;
      }, false);
      if (ok) prune();
      return ok;
    }

    function clearIf(sid, sent) {
      const kept = load(sid);
      if (kept === "" || kept.trim() !== text(sent).trim()) return false;
      return clear(sid);
    }

    return {load, save, clear, clearIf, prune};
  }

  // grow(el, maxPx): measure at auto, then set the height in px (the CSS min-height is the floor), and scroll inside the box only above the ceiling.
  function grow(el, maxPx) {
    if (!el || !isObj(el.style)) return 0;
    const max = Number.isFinite(maxPx) && maxPx > 0 ? maxPx : MAX_PX;
    el.style.height = "auto";
    const content = Number.isFinite(el.scrollHeight) ? el.scrollHeight : 0;
    const edge = Number.isFinite(el.offsetHeight) && Number.isFinite(el.clientHeight) ? Math.max(0, el.offsetHeight - el.clientHeight) : 0;
    const want = Math.min(content + edge, max);
    el.style.height = want > 0 ? want + "px" : "";
    el.style.overflowY = content + edge > max ? "auto" : "hidden";
    return want;
  }

  const ChatDraft = {create, grow, PREFIX, MAX_CHARS, MAX_CHATS, TTL_DAYS, MAX_PX};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatDraft;
  else root.ChatDraft = ChatDraft;
})(globalThis);
