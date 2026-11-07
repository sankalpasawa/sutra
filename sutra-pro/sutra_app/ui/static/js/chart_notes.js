/* chart_notes.js - the "Chart notes" panel of the Org chart pane (gap package chart-insight; docs/notes/GAP2-chart-insight.md; the old Health panel,
   19-org2.js o2HealthHtml).

   Strings in, strings out. GET /api/chart/notes answers {notes: [{kind, nodes: [{id, label}], words, say}], total}: two teams or divisions that look
   alike, a node with no purpose written, a team nobody has used for 60 days. This file draws them under the change log in names, never in codes:

     html(out)            the whole section: a heading, one line per note and, when nothing is flagged, "Nothing flagged". "" when `out` is not an answer.
                          A label inside `words` is a button (data-note-node="<id>") that opens that node's card; the line to act on is words the owner
                          can say to the chat agent ("merge Menu page into Pages"), or nothing for a note that is information only.
     sentenceHtml(note)   one note's sentence with its labels as buttons (escaped; a label that is not in the words stays plain text)
     addressOf(nodes, id) "Bakery site > Menu": the names from the team down to the node, for the card of a deep division ("" for a team or the root)
     INFO                 the sentence that says plainly that the notes change nothing

   Every word from the wire is escaped. The notes are information only: only divisions can be merged and a team is never archived or moved, so a note
   about two teams has no sentence to say. A classic script with ONE global, ChartNotes; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,119}$/;
  const MAX_NOTES = 20;
  const INFO = "These notes change nothing. To act on one, say it to Sutra in the chat.";

  // The sentence of a note with each label (in order) turned into a button; a label that is not in the words stays plain text.
  function sentenceHtml(note) {
    const n = isObj(note) ? note : {};
    const words = clean(n.words);
    const nodes = (Array.isArray(n.nodes) ? n.nodes : []).filter(isObj);
    let out = "";
    let at = 0;
    nodes.forEach(node => {
      const label = clean(node.label);
      const id = clean(node.id);
      const found = label === "" ? -1 : words.indexOf(label, at);
      if (found < 0 || !ID.test(id)) return;
      out += esc(words.slice(at, found)) + '<button type="button" class="linkbtn ocnodebtn" data-note-node="' + esc(id) + '">' + esc(label) + "</button>";
      at = found + label.length;
    });
    return out + esc(words.slice(at));
  }

  function noteHtml(note) {
    const kind = /^(overlap|no_purpose|quiet)$/.test(clean(note.kind)) ? clean(note.kind) : "other";
    const say = clean(note.say);
    return '<li class="ocnote k-' + kind + '"><span class="ocsent">' + sentenceHtml(note) + "</span>" +
      (say !== "" ? ' <span class="ocsay">Say: &ldquo;' + esc(say) + "&rdquo;</span>" : "") + "</li>";
  }

  function html(out) {
    if (!isObj(out) || !Array.isArray(out.notes)) return "";
    const notes = out.notes.filter(n => isObj(n) && clean(n.words) !== "").slice(0, MAX_NOTES);
    const total = Number.isFinite(out.total) && out.total >= notes.length ? Math.floor(out.total) : notes.length;
    const more = total - notes.length;
    return '<h4>Chart notes</h4>' +
      (notes.length ? '<ul class="ocnotelist">' + notes.map(noteHtml).join("") + "</ul>" +
        (more > 0 ? '<p class="ocmore">' + esc(more) + (more === 1 ? " more note is not shown." : " more notes are not shown.") + "</p>" : "") +
        '<p class="ocinfo">' + esc(INFO) + "</p>"
        : '<p class="ocnone">Nothing flagged</p>');
  }

  // "Bakery site > Menu": the team and the divisions down to the node. Nodes are the graph's ({id, label, parent, kind}); a team or the root has no address.
  function addressOf(nodes, id) {
    const list = (Array.isArray(nodes) ? nodes : []).filter(isObj);
    const byId = new Map(list.map(n => [text(n.id), n]));
    const chain = [];
    const seen = new Set();
    let current = byId.get(text(id));
    while (current && !seen.has(text(current.id)) && text(current.kind) !== "root") {
      seen.add(text(current.id));
      chain.push(clean(current.label) || text(current.id));
      current = byId.get(text(current.parent));
    }
    return chain.length > 1 ? chain.reverse().join(" > ") : "";
  }

  const ChartNotes = {html, sentenceHtml, addressOf, INFO, MAX_NOTES};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChartNotes;
  else root.ChartNotes = ChartNotes;
})(globalThis);
