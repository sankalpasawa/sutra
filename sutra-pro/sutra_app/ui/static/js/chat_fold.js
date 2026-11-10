/* chat_fold.js - a settled turn's tool calls folded into ONE row (work package ABS-10; absorb design 2.2 rule 7; the old "condense").

   A presentation fold of tool noise, not a model summary: "12 tool calls: 8 read, 3 run, 1 failed" that opens into the cards. While the turn is
   still streaming (settled false) nothing is drawn at the top. Strings in, strings out; every word from the wire is escaped; no message text
   becomes markup. A cut text says it was cut.

     summarize(blocks)   {calls, kinds: {read, edit, run, search, web, other}, failed, hidden}
     line(blocks)        "12 tool calls: 8 read, 3 run, 1 failed" ("" when the turn made no tool call)
     fold(blocks, {settled})   the <details> row, or "" (streaming, or no tool call)
     longText(raw, html, {limit, label})   a long text's html folded in ONE <details> whose summary names the text's `## ` headings ("Read the report
                               (Findings, Changes, Outcome)"); a short text is returned as it is (D135: the finished report in the team's chat)

   A classic script with ONE global, ChatFold; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : "");
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const KINDS = Object.freeze(["read", "edit", "run", "search", "web", "other"]);
  const SHOWN = 200;           // cards inside one fold; the rest is counted
  const RESULT_CHARS = 2000;

  const list = blocks => (Array.isArray(blocks) ? blocks.filter(isObj) : []);

  function summarize(blocks) {
    const kinds = {};
    KINDS.forEach(k => { kinds[k] = 0; });
    let calls = 0;
    let failed = 0;
    list(blocks).forEach(b => {
      if (b.type === "tool_use") {
        calls += 1;
        kinds[hasOwn(kinds, b.kind) ? b.kind : "other"] += 1;
      } else if (b.type === "tool_result" && b.is_error === true) {
        failed += 1;
      }
    });
    return {calls, kinds, failed, hidden: Math.max(0, list(blocks).filter(b => b.type === "tool_use" || b.type === "tool_result").length - SHOWN)};
  }

  function line(blocks) {
    const s = summarize(blocks);
    if (s.calls === 0) return "";
    const parts = KINDS.filter(k => s.kinds[k] > 0).map(k => s.kinds[k] + " " + k);
    if (s.failed > 0) parts.push(s.failed + " failed");
    return s.calls + " tool call" + (s.calls === 1 ? "" : "s") + ": " + parts.join(", ");
  }

  function card(b) {
    const kind = hasOwn({read: 1, edit: 1, run: 1, search: 1, web: 1, other: 1}, b.kind) ? b.kind : "other";
    const name = clean(b.name);
    if (b.type === "tool_use") {
      return '<li class="cfold-item kind-' + kind + '"><b>' + esc(name || kind) + "</b>" + (clean(b.text) ? " <code>" + esc(clean(b.text)) + "</code>" : "") + "</li>";
    }
    if (b.type === "tool_result") {
      const body = text(b.text).slice(0, RESULT_CHARS);
      const cut = b.truncated === true || text(b.text).length > RESULT_CHARS ? ' <small class="cfold-cut">(cut)</small>' : "";
      return '<li class="cfold-item result' + (b.is_error === true ? " failed" : "") + '"><small>' + (b.is_error === true ? "failed" : "result") +
        "</small>" + cut + (body === "" ? "" : '<pre class="cfold-out">' + esc(body) + "</pre>") + "</li>";
    }
    if (b.type === "thinking") return '<li class="cfold-item think"><small>thinking</small> ' + esc(clean(b.text)) + "</li>";
    return "";
  }

  function fold(blocks, opts) {
    const o = isObj(opts) ? opts : {};
    if (o.settled !== true) return "";
    const label = line(blocks);
    if (label === "") return "";
    const items = list(blocks).filter(b => b.type !== "text").map(card).filter(Boolean);
    const more = items.length > SHOWN ? '<li class="cfold-more">and ' + (items.length - SHOWN) + " more</li>" : "";
    return '<details class="cfold"><summary>' + esc(label) + '</summary><ul class="cfold-list">' + items.slice(0, SHOWN).join("") + more + "</ul></details>";
  }

  // A long TEXT folded (D135): the report a team wrote is read in its chat, but a page of it does not push the conversation away. `html` is the text already
  // drawn by its own renderer (ChatMarkdown), so it is trusted here as every caller's html is; `raw` is only counted and read for its `## ` headings. A fold of
  // a reading, never a summary by a model.
  const TEXT_FOLD_AT = 1400;           // characters a text may have before it is folded
  const HEADINGS_NAMED = 8;
  const HEADING = /^##[ \t]+(.+?)[ \t]*#*[ \t]*$/gm;

  function headings(raw) {
    const names = [];
    for (const m of text(raw).matchAll(HEADING)) {
      const name = clean(m[1]);
      if (name !== "" && !names.includes(name)) names.push(name);
    }
    return names;
  }

  function longText(raw, html, opts) {
    const o = isObj(opts) ? opts : {};
    const limit = Number.isFinite(o.limit) && o.limit > 0 ? o.limit : TEXT_FOLD_AT;
    const body = text(html);
    if (body === "" || text(raw).length <= limit) return body;
    const names = headings(raw);
    const label = (clean(o.label) || "Read the full text") +
      (names.length ? " (" + names.slice(0, HEADINGS_NAMED).join(", ") + (names.length > HEADINGS_NAMED ? ", \u2026" : "") + ")" : "");
    return '<details class="cfold cfold-text"><summary>' + esc(label) + "</summary>" + body + "</details>";
  }

  const ChatFold = {summarize, line, fold, longText, headings, KINDS, TEXT_FOLD_AT};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatFold;
  else root.ChatFold = ChatFold;
})(globalThis);
