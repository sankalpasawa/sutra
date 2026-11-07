/* team_find.js - the rail's search box: find a team or its work across the org (gap package chart-insight; docs/notes/GAP2-chart-insight.md; the old
   org search, 19-org2.js o2SearchHtml and o2TreeHtml).

   GET /api/find?q= answers {teams: [{team_id, team_name, node_id, kind, address, matched_on, snippet}], counts, truncated, messages: [{session_id,
   message_id, title, snippet, at, archived}]}: the teams and divisions whose name, purpose, task titles or task outcomes hold the words (best match
   first), then the chat search's messages. This file draws them, keeps the box, and says which boxes of the Org chart stay lit:

     request(q)                  {path, query} for the GET, or null: one character is not a search (the server says the same)
     html(answer)                the results: "Found in teams" (each row a link to the team's page, titled by its address "Bakery site > Menu", with the
                                 reason it matched and a snippet) then "Found in chats"; "Nothing found." when both are empty
     hits(rows) / dimming(rows, nodes)   the node ids that matched, and the ids above them (the graph's `parent` links)
     dimCss(scope, hits, ancestors)      the style rules that keep the hits lit, the ancestors in view and dim every other box and link under `scope`
     mount({input, out, api, onChange, onOpenChat, timers})   debounces the box (220 ms), reads, paints `out`, and tells onChange(rows | null) what matched
                                 -> {run(q), clear(), state(), destroy()}

   Every word of the wire is escaped; an id that is not an id is never put in a link or a style rule. A classic script with ONE global, TeamFind; in node
   it is module.exports and mounts nothing by itself. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$/;
  const SESSION = /^(cs_[0-9a-f]{12}|cs_org|cs_old_[a-z0-9]{12})$/;
  const MIN_CHARS = 2;
  const DEBOUNCE_MS = 220;
  const FIELD_WORDS = {name: "name", purpose: "purpose", task: "a task", outcome: "a task's result"};

  /* ---------------------------------------------------------------- the request */
  function request(q) {
    const words = clean(q).slice(0, 200);
    if (!words.split(" ").some(w => w.length >= MIN_CHARS)) return null;
    return {path: "/api/find", query: {q: words}};
  }

  /* ---------------------------------------------------------------- the results */
  function whyHtml(row) {
    const fields = (Array.isArray(row.matched_on) ? row.matched_on : []).map(clean).filter(f => Object.prototype.hasOwnProperty.call(FIELD_WORDS, f)).map(f => FIELD_WORDS[f]);
    const snippet = clean(row.snippet);
    return esc((fields.length ? "matched on " + fields.join(", ") : "") + (fields.length && snippet ? " · " : "") + snippet);
  }

  function teamRow(row) {
    const team = clean(row.team_id);
    const label = clean(row.address) || clean(row.team_name) || team;
    const why = '<span class="rtstat">' + whyHtml(row) + "</span>";
    return ID.test(team)
      ? '<a class="railteam rfound" href="/d/' + encodeURIComponent(team) + '/" data-dept="' + esc(team) + '" data-node="' + esc(clean(row.node_id)) + '"><span class="rtname">' + esc(label) + "</span>" + why + "</a>"
      : '<span class="railteam rfound"><span class="rtname">' + esc(label) + "</span>" + why + "</span>";
  }

  function messageRow(row) {
    const sid = clean(row.session_id);
    const inner = '<span class="rtname">' + esc(clean(row.title) || sid) + "</span><span class=\"rtstat\">" + esc(clean(row.snippet)) + (row.archived === true ? " · older chat" : "") + "</span>";
    return SESSION.test(sid) ? '<button type="button" class="railteam rfmsg" data-act="find-chat" data-sid="' + esc(sid) + '">' + inner + "</button>" : '<span class="railteam rfmsg">' + inner + "</span>";
  }

  function html(answer) {
    if (!isObj(answer)) return "";
    const teams = (Array.isArray(answer.teams) ? answer.teams : []).filter(isObj);
    const messages = (Array.isArray(answer.messages) ? answer.messages : []).filter(isObj);
    if (teams.length === 0 && messages.length === 0) return '<p class="railnone">Nothing found.</p>';
    return (teams.length ? '<p class="rfhead">Found in teams</p>' + teams.map(teamRow).join("") +
      (answer.truncated === true ? '<p class="railnone">More match: add a word to narrow it.</p>' : "") : "") +
      (messages.length ? '<p class="rfhead">Found in chats</p>' + messages.map(messageRow).join("") : "");
  }

  /* ---------------------------------------------------------------- what stays lit in the Org chart */
  const hits = rows => Array.from(new Set((Array.isArray(rows) ? rows : []).filter(isObj).map(r => clean(r.node_id)).filter(id => ID.test(id))));

  // The ids above the hits, nearest first, never a hit itself. `nodes` are the graph's ({id, parent}); a loop of parents ends. A hit the chart does not
  // hold (a division merged away since the search was made) lights nothing: kept, it would fade every box with no box lit.
  function dimming(rows, nodes) {
    const parent = new Map((Array.isArray(nodes) ? nodes : []).filter(isObj).map(n => [text(n.id), text(n.parent)]));
    const found = hits(rows).filter(id => parent.has(id));
    const lit = new Set(found);
    const above = [];
    found.forEach(id => {
      const seen = new Set([id]);
      let up = parent.get(id);
      while (up && !seen.has(up) && parent.has(up)) {
        seen.add(up);
        if (!lit.has(up) && !above.includes(up)) above.push(up);
        up = parent.get(up);
      }
    });
    return {hits: found, ancestors: above.filter(id => ID.test(id))};
  }

  // Style rules, not classes: the graph paints its boxes again on every update and a rule keeps matching them. Hits are full, the ancestors a little
  // faded, everything else dim; a link is as lit as the box it leads to.
  function dimCss(scope, hit, ancestors) {
    const lit = (Array.isArray(hit) ? hit : []).filter(id => ID.test(id));
    if (lit.length === 0 || !/^[.#\w\[\]="-]+$/.test(text(scope))) return "";
    const up = (Array.isArray(ancestors) ? ancestors : []).filter(id => ID.test(id));
    const boxes = ids => ids.map(id => scope + ' g.wnode[data-id="' + id + '"]').join(",");
    const links = (ids, attr) => ids.map(id => scope + ' path.wedge[' + attr + '="' + id + '"]').join(",");
    return scope + " g.wnode{opacity:.22}" + scope + " path.wedge{opacity:.15}" +
      (up.length ? boxes(up) + "{opacity:.7}" + links(up, "data-to") + "{opacity:.5}" : "") +
      boxes(lit) + "{opacity:1}" + links(lit, "data-to") + "{opacity:.9}";
  }

  /* ---------------------------------------------------------------- the box */
  function mount(options) {
    const o = isObj(options) ? options : {};
    const input = o.input;
    const out = o.out;
    const api = o.api;
    if (!input || !out || !api || typeof api.get !== "function") throw new TypeError("TeamFind.mount needs {input, out, api}");
    const timers = o.timers || {setTimeout: (f, ms) => root.setTimeout(f, ms), clearTimeout: t => root.clearTimeout(t)};
    const tell = rows => { if (typeof o.onChange === "function") { try { o.onChange(rows); } catch (e) { report("onChange", e); } } };
    const S = {seq: 0, timer: null, q: "", answer: null, destroyed: false, reads: 0};

    const paint = markup => { out.innerHTML = markup; out.hidden = markup === ""; };
    const cancel = () => { if (S.timer !== null) { timers.clearTimeout(S.timer); S.timer = null; } };

    function clear() {
      S.seq += 1;
      cancel();
      S.q = "";
      S.answer = null;
      paint("");
      tell(null);
    }

    function run(q) {
      cancel();
      const req = request(q);
      if (!req) { clear(); return Promise.resolve(false); }
      const mine = ++S.seq;
      S.q = req.query.q;
      S.reads += 1;
      return Promise.resolve().then(() => api.get(req.path, req.query)).then(answer => {
        if (S.destroyed || mine !== S.seq) return false;
        S.answer = isObj(answer) ? answer : null;
        paint(html(S.answer));
        tell(S.answer && Array.isArray(S.answer.teams) ? S.answer.teams : null);
        return true;
      }, () => {
        if (S.destroyed || mine !== S.seq) return false;
        S.answer = null;
        paint('<p class="railnone">Search is not available right now.</p>');
        tell(null);
        return false;
      });
    }

    input.addEventListener("input", () => {
      cancel();
      if (request(input.value) === null) { clear(); return; }
      S.timer = timers.setTimeout(() => { S.timer = null; run(input.value); }, DEBOUNCE_MS);
    });
    input.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); run(input.value); }
      else if (e.key === "Escape" && input.value !== "") { e.stopPropagation(); input.value = ""; clear(); }
    });
    out.addEventListener("click", e => {
      const b = e.target && e.target.closest ? e.target.closest("[data-act='find-chat']") : null;
      if (b && typeof o.onOpenChat === "function") { try { o.onOpenChat(b.getAttribute("data-sid")); } catch (err) { report("onOpenChat", err); } }
    });

    return {run, clear, state: () => ({q: S.q, answer: S.answer, reads: S.reads, waiting: S.timer !== null}), destroy() { S.destroyed = true; S.seq += 1; cancel(); }};
  }

  function report(where, error) {
    if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("TeamFind: " + where + " failed", error);
  }

  const TeamFind = {request, html, hits, dimming, dimCss, mount, MIN_CHARS, DEBOUNCE_MS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = TeamFind;
  else root.TeamFind = TeamFind;
})(globalThis);
