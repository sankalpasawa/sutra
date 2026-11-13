/* function_chat.js - the questions asked of a function, and its answers, in J2's chat panel (J2 sync 4; docs/design/j2-sync-4.md D147, D148 and 4.4).

   J2's panel keeps this viewer's questions and their answers in page memory (`QA`, a list the page script owns) and loses them with the page. In Sutra a
   question to a function is a line of that function's OWN chat session and the answer the next line (POST /api/ask stores both, with the references
   `ask:<id>` and `ask:<id>:records|model`; the messages route draws them as `ask: "q" | "records" | "model"`), so the node panel's chat and J2's panel show
   ONE transcript. This module fills `QA` from that session. J2's page calls it from `loadFeed` (page edit E21), before it paints the feed.

     hydrate(QA, who, run[, options])   async. Reads the function's session of that run (GET /api/teams/{dept}/agents[?run=], the row whose `agent` is
                                        `who` and `kind` is "function"), then its messages (GET /api/chats/{sid}/messages, pages of 200, at most 5 pages a
                                        call, only what is new since the last call), pairs every `q` line with the next `records` or `model` line, and
                                        replaces, IN PLACE, every entry of `QA` for `who` that is not waiting for an answer with the stored ones:
                                          {who, q, a, from: "records" | "model", t, at, n, id}   (J2's own entry, `t` and `at` as "HH:MM:SS")
                                        A question with no answer line becomes `a: "No answer was stored."` with `from: ""`, unless it is in flight: an
                                        entry the page asked a moment ago (`a == null`, "Thinking...") stays exactly as it is and its stored question is not
                                        added a second time. Every stored entry gets `n` = the length of the feed (so it sits after the records the run
                                        has now), read from `options.feed` or, in the page, from J2's own `FEED`.
                                        Resolves true when the list was replaced, false (and the list is untouched) on any failure, when there is no
                                        function chat for that run (the validator is code; an agent that did not work in the run has none), or when a
                                        newer call for the same function started meanwhile. `options` {api, dept, feed} stand in for SutraCtx in a test.
     askPath(dept)                      "/api/ask?dept=<dept>": the route the node panel's Ask box posts to (the page's own box posts /api/ask, and the
                                        fetch wrapper adds the team).
     pairs(messages)                    [{q, a}] of the ask lines of a session in id order; `a` is null for a question nothing answered.
     entryOf(pair, who, n)              one entry of `QA` for a pair.

   A classic script with ONE global, FunctionChat (see sutra_ctx.js for why); in node it is module.exports. It needs SutraCtx, read when used. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const enc = encodeURIComponent;

  const FUNCTIONS = Object.freeze(["identity", "adaptation", "priority", "coordination", "audit"]);        // the five that have a chat session of their own
  const PAGE = 200;                  // messages per request (the server's own cap)
  const MAX_PAGES = 5;               // never more than 1,000 messages for one call
  const NO_ANSWER = "No answer was stored.";
  const NO_TEXT = "No answer came back.";

  const askPath = dept => "/api/ask?dept=" + enc(clean(dept));

  /* ---------------------------------------------------------------- pure parts */
  const asked = m => isObj(m) && (m.ask === "q" || m.ask === "records" || m.ask === "model");
  const idOf = m => (Number.isFinite(Number(m && m.id)) ? Number(m.id) : 0);
  const same = (a, b) => text(a).split(/\s+/).filter(Boolean).join(" ") === text(b).split(/\s+/).filter(Boolean).join(" ");

  // The server holds one question per session at a time, so the lines alternate: q, answer, q, answer. A question that the next question follows has no
  // answer line (the app stopped while it was being answered); an answer with no question before it is not a pair.
  function pairs(messages) {
    const lines = (Array.isArray(messages) ? messages : []).filter(asked).sort((a, b) => idOf(a) - idOf(b));
    const out = [];
    let open = null;
    lines.forEach(m => {
      if (m.ask === "q") {
        if (open !== null) out.push({q: open, a: null});
        open = m;
      } else if (open !== null) {
        out.push({q: open, a: m});
        open = null;
      }
    });
    if (open !== null) out.push({q: open, a: null});
    return out;
  }

  // J2 writes the time of a line as new Date().toTimeString().slice(0, 8); the panel shows its first five characters.
  function clockOf(iso) {
    const d = new Date(text(iso));
    return Number.isNaN(d.getTime()) ? "" : d.toTimeString().slice(0, 8);
  }

  function entryOf(pair, who, n) {
    const answer = pair.a;
    return {who, q: text(pair.q.text), a: answer ? (text(answer.text) || NO_TEXT) : NO_ANSWER, from: answer ? (answer.ask === "model" ? "model" : "records") : "",
      t: clockOf(pair.q.at), at: answer ? clockOf(answer.at) : "", n: Number.isInteger(n) && n > 0 ? n : 0, id: idOf(pair.q)};
  }

  // The length of J2's feed: its `FEED` object (a top-level `const` of the page script, so another classic script reads it by its bare name) when it has
  // found the function's records, else 0, as J2 itself counts a question's place.
  function feedLength(o) {
    const feed = o.feed !== undefined ? o.feed : (typeof FEED !== "undefined" ? FEED : null);        // eslint-disable-line no-undef
    return isObj(feed) && feed.found === true && Array.isArray(feed.events) ? feed.events.length : 0;
  }

  /* ---------------------------------------------------------------- reading the session */
  const newest = new Map();          // function -> the latest hydrate call: an older call that finishes late must not undo a newer one
  const memo = new Map();            // session id -> {last, lines}: the ask lines read so far, and the id of the last message looked at

  async function sessionOf(api, dept, who, run) {
    const rows = await api.get("/api/teams/" + enc(dept) + "/agents", run !== "" ? {run} : {});
    if (!Array.isArray(rows)) throw new Error("bad_payload");
    const row = rows.find(r => isObj(r) && r.agent === who && r.kind === "function" && clean(r.session_id) !== "");
    return row ? clean(row.session_id) : "";
  }

  // Only what is new: the lines of a session never change and ids only grow, so the next call asks for what comes after the last id it saw.
  async function asksOf(api, sid) {
    const known = memo.get(sid) || {last: 0, lines: []};
    let cursor = known.last;
    const fresh = [];
    for (let page = 0; page < MAX_PAGES; page += 1) {
      const r = await api.get("/api/chats/" + enc(sid) + "/messages", {after: cursor, limit: PAGE});
      if (!isObj(r) || !Array.isArray(r.messages)) throw new Error("bad_payload");
      const list = r.messages.filter(isObj);
      list.forEach(m => { if (asked(m)) fresh.push(m); });
      const last = list.reduce((n, m) => Math.max(n, idOf(m)), cursor);
      const more = list.length >= PAGE && last > cursor;
      cursor = last;
      if (!more) break;
    }
    const have = new Set(known.lines.map(idOf));
    const lines = known.lines.concat(fresh.filter(m => !have.has(idOf(m))));
    memo.set(sid, {last: cursor, lines});
    return lines;
  }

  /* ---------------------------------------------------------------- hydrate */
  async function hydrate(QA, who, run, options) {
    const o = isObj(options) ? options : {};
    const c = root.SutraCtx || null;
    const api = o.api || (c ? c.api : null);
    const dept = clean(o.dept !== undefined ? o.dept : (c ? c.dept : ""));
    const fn = clean(who);
    if (!Array.isArray(QA) || !api || typeof api.get !== "function" || dept === "" || !FUNCTIONS.includes(fn)) return false;
    const mine = (newest.get(fn) || 0) + 1;
    newest.set(fn, mine);
    const inFlight = list => list.filter(x => isObj(x) && x.who === fn && x.a == null);
    const before = inFlight(QA);
    let lines;
    try {
      const sid = await sessionOf(api, dept, fn, clean(run));
      if (sid === "") return false;
      lines = await asksOf(api, sid);
    } catch (e) {
      return false;
    }
    if (newest.get(fn) !== mine) return false;
    // what was in flight when the call began, and what is now: all of them keep their place and their words; each takes its stored question with it
    const keep = new Set(before.concat(inFlight(QA)));
    const stored = pairs(lines);
    const taken = new Set();
    keep.forEach(k => {
      const at = stored.findIndex((p, i) => !taken.has(i) && same(p.q.text, k.q));
      if (at >= 0) taken.add(at);
    });
    const n = feedLength(o);
    const entries = stored.filter((p, i) => !taken.has(i)).map(p => entryOf(p, fn, n));
    const others = QA.filter(x => !isObj(x) || x.who !== fn);
    const kept = QA.filter(x => keep.has(x));
    QA.splice(0, QA.length, ...others, ...entries, ...kept);
    return true;
  }

  const FunctionChat = {hydrate, askPath, pairs, entryOf, clockOf, FUNCTIONS, NO_ANSWER, PAGE, MAX_PAGES};
  if (typeof module === "object" && module !== null && module.exports) module.exports = FunctionChat;
  else root.FunctionChat = FunctionChat;
})(globalThis);
