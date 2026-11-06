/* chat_markdown.js - a model's direct reply drawn as formatted text (package GAP-markdown; docs/design/ui.md section 4.3).

   Strings in, strings out, like chat_view.js: nothing touches the DOM. The text is UNTRUSTED (whatever a model wrote), so the order of the work is
   the whole safety argument:
     1. control characters are dropped and the WHOLE text is escaped (& < > " ') before anything else is done to it. After that no "<" of the
        text survives, so nothing in it can become an element, and no attribute value is ever taken from it (the one attribute with a value
        from the text, an ordered list's `start`, is digits only);
     2. only then is markdown read, line by line, and the only tags written are the ones this file authors: p br strong em del code pre h3 h4
        h5 h6 ul ol li blockquote hr table thead tbody tr th td, and two wrappers (div.cmd around a reply, div.cmd-tw around a table).
   No link, no image, no HTML: `[label](url)` and a bare address stay plain text, so ui.md 4.3 ("no links, no HTML") still holds and the page
   still makes no external URL. The markup is well formed XML (<br/>, <hr/>), which the XML reader of the tests proves.

     render(text, {streaming})   the html of a reply inside <div class="cmd">, or "" for an empty one. Blocks: paragraphs (a single line break is
                                 a <br/>, as in safeText), fenced code (``` or ~~~; an unclosed fence runs to the end of the text, so a streamed
                                 fence is code from its first line and the row does not reshape when the fence closes), headings (# to ######,
                                 drawn h3 to h6 inside a chat bubble), lists (- * + and 1. 1), nested by indent, an ordered list keeps its first
                                 number), tables (a header row then a |---| separator with as many cells; : aligns a column; the table scrolls
                                 sideways in its wrapper), quotes (>), rules (--- *** ___). Inline: `code`, **bold**, __bold__, *italic*,
                                 _italic_, ~~struck~~, and a backslash before a mark keeps the mark. streaming: true first applies hold().
     hold(text)                  the streamed text without the lines that would re-shape when the next line arrives: an unfinished last line
                                 that looks like a table row, and a finished last line that looks like a table header whose separator has not
                                 arrived yet. Inside an open fence nothing is held (it is code either way).
     fenceAt(text)               the fence left open at the end of `text` ("```", "~~~~", ...), or "". chat_pill.js uses it when it cuts a long
                                 stream, so the part it keeps still reads as code where it was code.

   Bounded on hostile input: each line is looked at a fixed number of times and no regular expression can backtrack along a line; lists nest at
   most 6 deep, quotes 4 deep, a table has at most 50 columns, and a row is never padded (output grows with the input, never faster).
   A classic script with ONE global, ChatMarkdown (see sutra_ctx.js for why); in node it is module.exports. */
(function (root) {
  "use strict";

  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  // every control character but the tab and the line break goes: XML cannot carry them, and \u0000 marks the parked spans of inline()
  const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;
  const normal = v => text(v).replace(/\r\n?/g, "\n").replace(CONTROL, "");
  const MAX_LIST_DEPTH = 6;
  const MAX_QUOTE_DEPTH = 4;
  const MAX_COLUMNS = 50;

  /* ---------------------------------------------------------------- what a line is (each works on a raw or an escaped line alike) */
  const blank = line => line.trim() === "";

  // columns of leading white space (a tab moves to the next multiple of 4)
  function indentOf(line) {
    let n = 0;
    for (let i = 0; i < line.length; i += 1) {
      if (line[i] === " ") n += 1;
      else if (line[i] === "\t") n += 4 - (n % 4);
      else break;
    }
    return n;
  }

  // An opening fence: three or more ` or ~ after any indent (a fence in a list item is indented); a ` fence's info string has no `.
  const FENCE_OPEN = /^([ \t]*)(`{3,}|~{3,})(.*)$/;
  const FENCE_CLOSE = /^[ \t]*(`{3,}|~{3,})[ \t]*$/;

  function fenceOpen(line) {
    const m = FENCE_OPEN.exec(line);
    if (!m || (m[2][0] === "`" && m[3].indexOf("`") >= 0)) return null;
    return {indent: indentOf(m[1]), marker: m[2]};
  }

  // A closing fence: the same character, at least as many, nothing after it.
  function closes(line, marker) {
    const m = FENCE_CLOSE.exec(line);
    return m !== null && m[1][0] === marker[0] && m[1].length >= marker.length;
  }

  function fenceAt(value) {
    let open = "";
    for (const line of normal(value).split("\n")) {
      if (open !== "") { if (closes(line, open)) open = ""; }
      else { const f = fenceOpen(line); if (f) open = f.marker; }
    }
    return open;
  }

  function isRule(line) {
    if (indentOf(line) > 3) return false;
    const s = line.replace(/[ \t]/g, "");
    return s.length >= 3 && /^(?:-+|\*+|_+)$/.test(s);
  }

  // A heading: one to six # and a space; its level, its words without a closing run of #. Empty words are not a heading.
  function heading(line) {
    const m = /^ {0,3}(#{1,6})(?=[ \t]|$)/.exec(line);
    if (!m) return null;
    let words = line.slice(m[0].length).trim();
    let end = words.length;
    while (end > 0 && words[end - 1] === "#") end -= 1;
    if (end < words.length && (end === 0 || words[end - 1] === " " || words[end - 1] === "\t")) words = words.slice(0, end).trim();
    return words === "" ? null : {level: m[1].length, words};
  }

  // A quote line, on the ESCAPED text: ">" is "&gt;" there.
  const QUOTE = /^ {0,3}&gt; ?/;
  const isQuote = line => QUOTE.test(line);

  const BULLET = /^([ \t]*)([-*+])[ \t]+(.*)$/;
  const NUMBER = /^([ \t]*)(\d{1,9})[.)][ \t]+(.*)$/;

  function listItem(line) {
    if (isRule(line)) return null;                                       // "- - -" and "* * *" are rules, not items
    let m = BULLET.exec(line);
    if (m) return {indent: indentOf(m[1]), ordered: false, start: 1, words: m[3]};
    m = NUMBER.exec(line);
    if (m) return {indent: indentOf(m[1]), ordered: true, start: Number(m[2]), words: m[3]};
    return null;
  }

  // The cells of a table row: split at every | that is not written \|, without the outer pipes.
  function cells(line) {
    let s = line.trim();
    if (s.startsWith("|")) s = s.slice(1);
    if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
    const out = [];
    let cell = "";
    for (let i = 0; i < s.length; i += 1) {
      if (s[i] === "\\" && s[i + 1] === "|") { cell += "|"; i += 1; }
      else if (s[i] === "|") { out.push(cell.trim()); cell = ""; }
      else cell += s[i];
    }
    out.push(cell.trim());
    return out;
  }

  // The separator row under a table's header: every cell is dashes with an optional colon at either end. -> the alignment of each column.
  function separator(line) {
    if (line.indexOf("|") < 0 || line.indexOf("-") < 0) return null;
    for (let i = 0; i < line.length; i += 1) if ("|-: \t".indexOf(line[i]) < 0) return null;
    const out = [];
    for (const c of cells(line)) {
      if (!/^:?-+:?$/.test(c)) return null;
      out.push(c.endsWith(":") ? (c.startsWith(":") ? "c" : "r") : "");
    }
    return out;
  }

  function tableAt(lines, i) {
    if (lines[i].indexOf("|") < 0 || i + 1 >= lines.length) return null;
    const aligns = separator(lines[i + 1]);
    if (!aligns || aligns.length > MAX_COLUMNS) return null;
    const head = cells(lines[i]);
    return head.length === aligns.length ? {head, aligns} : null;
  }

  // A line that looks like a table row while it streams: it starts with a pipe or has two of them.
  function tableShaped(line) {
    if (line.trim().startsWith("|")) return true;
    const first = line.indexOf("|");
    return first >= 0 && line.indexOf("|", first + 1) >= 0;
  }

  /* ---------------------------------------------------------------- inline marks, on one ESCAPED line */
  // code spans: a run of n backticks up to the next run of exactly n (CommonMark); a run with no partner stays as it is, and a backslash before
  // a run makes its first backtick plain (the rest of the run may still open a span; inside a span a backslash is just a character). Each
  // length keeps a pointer into its own list of runs that only moves forward, so the whole line is one pass.
  function codeSpans(line, park) {
    const runs = [];
    const byLen = new Map();
    const RUN = /`+/g;
    let m;
    while ((m = RUN.exec(line)) !== null) {
      if (!byLen.has(m[0].length)) byLen.set(m[0].length, []);
      byLen.get(m[0].length).push(runs.length);
      runs.push({at: m.index, len: m[0].length});
    }
    const ptr = new Map();
    const partner = (k, len) => {
      const list = byLen.get(len);
      if (!list) return -1;
      let p = ptr.get(len) || 0;
      while (p < list.length && list[p] <= k) p += 1;
      ptr.set(len, p);
      return p < list.length ? list[p] : -1;
    };
    let out = "";
    let pos = 0;
    let k = 0;
    while (k < runs.length) {
      let at = runs[k].at;
      let len = runs[k].len;
      if (at > 0 && line[at - 1] === "\\") { at += 1; len -= 1; }
      const j = len > 0 ? partner(k, len) : -1;
      if (j < 0) { k += 1; continue; }
      let code = line.slice(at + len, runs[j].at);
      if (code.length >= 2 && code[0] === " " && code[code.length - 1] === " " && code.trim() !== "") code = code.slice(1, -1);
      out += line.slice(pos, at) + park("<code>" + code + "</code>");
      pos = runs[j].at + runs[j].len;
      k = j + 1;
    }
    return out + line.slice(pos);
  }

  // A mark's words hold plain text and, at most, WHOLE elements made by an earlier pass, never a lone "<": so a mark never opens in one element
  // and closes in another, and the markup stays well formed whatever the text. Italic and struck words are plain text, bold words may hold
  // whole italics, and a last italic pass may hold whole bolds. The words start and end with a character that is not a space; * and _ do not
  // open inside a word (2*3*4 and snake_case stay as written).
  const EM = "<em>[^<]*<\\/em>";
  const STRONG = "<strong>(?:[^<]|" + EM + ")*?<\\/strong>";
  const EM_STAR = /(^|[^*\w])\*(?![\s*])([^*<]*?[^\s*<])\*(?![*\w])/g;
  const EM_LINE = /(^|[^_\w])_(?![\s_])([^_<]*?[^\s_<])_(?![_\w])/g;
  const STRONG_STAR = new RegExp("\\*\\*(?=[^\\s*])((?:[^*<]|" + EM + ")*?(?:[^\\s*<]|" + EM + "))\\*\\*", "g");
  const STRONG_LINE = new RegExp("(^|[^_\\w])__(?=[^\\s_])((?:[^_<]|" + EM + ")*?(?:[^\\s_<]|" + EM + "))__(?![_\\w])", "g");
  const EM_AROUND = new RegExp("(^|[^*\\w])\\*(?![\\s*])((?:[^*<]|" + STRONG + ")*?(?:[^\\s*<]|" + STRONG + "))\\*(?![*\\w])", "g");
  const STRUCK = /~~(?=[^\s~])([^~<]*?[^\s~<])~~/g;
  const ESCAPED_MARK = /\\([\\`*_~|#+.!()[\]-])/g;
  const PARKED = /\u0000(\d+)\u0000/g;

  function inline(line) {
    const parked = [];
    const park = html => "\u0000" + (parked.push(html) - 1) + "\u0000";
    let s = codeSpans(line, park);
    s = s.replace(ESCAPED_MARK, (m, c) => park(c));
    s = s.replace(EM_STAR, "$1<em>$2</em>").replace(EM_LINE, "$1<em>$2</em>")
      .replace(STRONG_STAR, "<strong>$1</strong>").replace(STRONG_LINE, "$1<strong>$2</strong>")
      .replace(EM_AROUND, "$1<em>$2</em>").replace(STRUCK, "<del>$1</del>");
    return s.replace(PARKED, (m, n) => parked[Number(n)]);
  }

  /* ---------------------------------------------------------------- blocks, on the ESCAPED lines */
  function dropIndent(line, n) {
    let i = 0;
    while (i < n && i < line.length && (line[i] === " " || line[i] === "\t")) i += 1;
    return line.slice(i);
  }

  function codeBlock(lines, i, fence) {
    const body = [];
    let j = i + 1;
    while (j < lines.length && !closes(lines[j], fence.marker)) { body.push(dropIndent(lines[j], fence.indent)); j += 1; }
    while (body.length > 0 && blank(body[body.length - 1])) body.pop();
    return {html: '<pre class="cmd-pre"><code>' + body.join("\n") + "</code></pre>", next: j < lines.length ? j + 1 : j};
  }

  const ALIGN = {c: ' class="cmd-ac"', r: ' class="cmd-ar"', "": ""};

  function tableBlock(lines, i, table) {
    const {head, aligns} = table;
    const cell = (tag, words, k) => "<" + tag + ALIGN[aligns[k]] + ">" + inline(words) + "</" + tag + ">";
    let j = i + 2;
    const rows = [];
    while (j < lines.length && !blank(lines[j]) && lines[j].indexOf("|") >= 0) {
      rows.push("<tr>" + cells(lines[j]).slice(0, head.length).map((w, k) => cell("td", w, k)).join("") + "</tr>");
      j += 1;
    }
    return {html: '<div class="cmd-tw"><table class="cmd-t"><thead><tr>' + head.map((w, k) => cell("th", w, k)).join("") + "</tr></thead>" +
      (rows.length ? "<tbody>" + rows.join("") + "</tbody>" : "") + "</table></div>", next: j};
  }

  // A list, nested by indent: a deeper item opens a list inside the open item, a shallower one closes lists until one fits. An indented line
  // that is not an item goes on the open item's words; blank lines between items keep the list (and its numbers) going.
  function listBlock(lines, i) {
    let html = "";
    const stack = [];                                                    // the open lists, outermost first: {indent, ordered}; each has an open <li>
    const close = () => { html += "</li>" + (stack.pop().ordered ? "</ol>" : "</ul>"); };
    const open = item => {
      html += item.ordered ? '<ol class="cmd-l"' + (item.start !== 1 ? ' start="' + item.start + '"' : "") + ">" : '<ul class="cmd-l">';
      stack.push({indent: item.indent, ordered: item.ordered});
    };
    const place = item => {
      while (stack.length > 1 && item.indent < stack[stack.length - 1].indent) close();
      const top = stack[stack.length - 1];
      if (!top || (item.indent > top.indent && stack.length < MAX_LIST_DEPTH)) open(item);
      else if (top.ordered !== item.ordered) { close(); open(item); }
      else html += "</li>";
      html += "<li>" + inline(item.words.trim());
    };
    const goesOn = line => !blank(line) && indentOf(line) > 0 && !fenceOpen(line);
    let j = i;
    while (j < lines.length) {
      const item = listItem(lines[j]);
      if (item) { place(item); j += 1; continue; }
      if (goesOn(lines[j])) { html += "<br/>" + inline(lines[j].trim()); j += 1; continue; }
      if (!blank(lines[j])) break;
      let k = j;
      while (k < lines.length && blank(lines[k])) k += 1;
      if (k < lines.length && listItem(lines[k])) { j = k; continue; }
      if (k < lines.length && goesOn(lines[k])) { html += "<br/>"; j = k; continue; }
      break;
    }
    while (stack.length > 0) close();
    return {html, next: j};
  }

  const startsBlock = (lines, i) => fenceOpen(lines[i]) !== null || isRule(lines[i]) || heading(lines[i]) !== null || isQuote(lines[i]) ||
    listItem(lines[i]) !== null || tableAt(lines, i) !== null;

  function blocks(lines, depth) {
    let out = "";
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (blank(line)) { i += 1; continue; }
      const fence = fenceOpen(line);
      if (fence) { const r = codeBlock(lines, i, fence); out += r.html; i = r.next; continue; }
      if (isRule(line)) { out += '<hr class="cmd-hr"/>'; i += 1; continue; }
      const h = heading(line);
      if (h) {
        const tag = "h" + Math.min(6, h.level + 2);
        out += "<" + tag + ' class="cmd-h">' + inline(h.words) + "</" + tag + ">";
        i += 1;
        continue;
      }
      if (isQuote(line)) {
        const inner = [];
        while (i < lines.length && isQuote(lines[i])) { inner.push(lines[i].replace(QUOTE, "")); i += 1; }
        out += '<blockquote class="cmd-q">' + (depth + 1 < MAX_QUOTE_DEPTH ? blocks(inner, depth + 1) : inner.map(l => inline(l.trim())).join("<br/>")) + "</blockquote>";
        continue;
      }
      const table = tableAt(lines, i);
      if (table) { const r = tableBlock(lines, i, table); out += r.html; i = r.next; continue; }
      if (listItem(line)) { const r = listBlock(lines, i); out += r.html; i = r.next; continue; }
      const para = [inline(line.trim())];                              // a paragraph: up to a blank line or the start of another block
      i += 1;
      while (i < lines.length && !blank(lines[i]) && !startsBlock(lines, i)) { para.push(inline(lines[i].trim())); i += 1; }
      out += '<p class="cmd-p">' + para.join("<br/>") + "</p>";
    }
    return out;
  }

  /* ---------------------------------------------------------------- streaming */
  function hold(value) {
    const t = normal(value);
    const lines = t.split("\n");
    const finished = t.endsWith("\n");
    if (finished) lines.pop();                                           // the "" after the last line break
    const inFence = upto => fenceAt(lines.slice(0, upto).join("\n")) !== "";
    let held = false;
    if (!finished && lines.length > 0 && tableShaped(lines[lines.length - 1]) && !inFence(lines.length - 1)) { lines.pop(); held = true; }
    if (finished || held) {
      const n = lines.length;
      // a header row waits for its separator: it is the last line, it looks like a row, and the line above it does not
      if (n > 0 && tableShaped(lines[n - 1]) && (n === 1 || !tableShaped(lines[n - 2])) && !inFence(n - 1)) { lines.pop(); held = true; }
    }
    if (!held) return t;
    return lines.length === 0 ? "" : lines.join("\n") + "\n";
  }

  function render(value, opts) {
    const o = opts !== null && typeof opts === "object" ? opts : {};
    const source = o.streaming === true ? hold(value) : normal(value);
    const html = blocks(esc(source).split("\n"), 0);
    return html === "" ? "" : '<div class="cmd">' + html + "</div>";
  }

  const ChatMarkdown = {render, hold, fenceAt, MAX_COLUMNS, MAX_LIST_DEPTH, MAX_QUOTE_DEPTH};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatMarkdown;
  else root.ChatMarkdown = ChatMarkdown;
})(globalThis);
