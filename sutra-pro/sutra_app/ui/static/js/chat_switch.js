/* chat_switch.js - the chat switcher of Home's chat column (gap package dept-chats; docs/notes/GAP3-dept-chats.md).

   Home's left column holds ONE chat at a time: the org chat (cs_org), or the own chat of a team the org chat made. Every team has its own session,
   so the owner can read it, answer it and ask its model there without the org chat in the way. This module is the strings of the switcher; the
   DOM half is home.js (it shows the team's chat with the node panel's own Chat tab).

   Strings in, strings out, like chat_view.js: nothing touches the DOM and every word from the wire is escaped.

     entries(departments, graph, needs)    the chats the owner can switch to: the org chat first, then each team (GET /api/departments) followed by
                                           its divisions (the division nodes of GET /api/graph, which name their team in `dept_id`). Each entry is
                                           {id, node, kind: org|department|division, label, parent, waiting}; `id` is the chat session, `waiting` the
                                           number of the team's questions that wait for the owner (GET /api/needs-you, by session). A row without
                                           a usable id or chat is dropped.
     bar(entries, activeId)                the tab strip: one button per entry (data-act switch-chat, data-session, data-node), the active one
                                           aria-selected and named; "" when the org chat is the only chat
     heading(entries, activeId)            "Chat with Sutra" / "Chat with Web", the words of the pane's label
     nextIndex(key, count, current)        the tab a key moves to (ArrowLeft, ArrowRight, Home, End), or -1 for any other key
     entryOf(entries, key)                 the entry whose chat session or node is `key` (or null)

   A classic script with ONE global, ChatSwitch; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ID = /^[A-Za-z0-9_.:-]{1,120}$/;
  const idOf = v => (ID.test(text(v)) ? text(v) : "");

  const ORG = "cs_org";
  const ORG_LABEL = "Sutra";
  const MAX_LABEL = 40;

  const short = label => (label.length > MAX_LABEL ? label.slice(0, MAX_LABEL - 1) + "…" : label);
  const list = v => (Array.isArray(v) ? v.filter(isObj) : []);

  function waitingBy(needs) {
    const out = {};
    list(needs).forEach(n => {
      const sid = idOf(n.session_id);
      if (sid !== "" && n.kind !== "approval") out[sid] = (out[sid] || 0) + 1;
    });
    return out;
  }

  function entries(departments, graph, needs) {
    const waiting = waitingBy(needs);
    const out = [{id: ORG, node: "root", kind: "org", label: ORG_LABEL, parent: "", waiting: 0}];
    const seen = new Set([ORG]);
    const nodes = isObj(graph) && Array.isArray(graph.nodes) ? graph.nodes.filter(isObj) : [];
    const divisions = nodes.filter(n => n.kind === "division" && idOf(n.id) !== "" && idOf(n.chat_session_id) !== "");
    list(departments).forEach(d => {
      const node = idOf(d.id);
      const sid = idOf(d.session_id);
      if (node === "" || sid === "" || seen.has(sid)) return;
      seen.add(sid);
      out.push({id: sid, node, kind: "department", label: clean(d.name) || node, parent: "", waiting: waiting[sid] || 0});
      divisions.filter(n => idOf(n.dept_id) === node).forEach(n => {
        const dsid = idOf(n.chat_session_id);
        if (seen.has(dsid)) return;
        seen.add(dsid);
        out.push({id: dsid, node: idOf(n.id), kind: "division", label: clean(n.label) || idOf(n.id), parent: clean(d.name) || node, waiting: waiting[dsid] || 0});
      });
    });
    return out;
  }

  function entryOf(items, key) {
    const k = text(key);
    return (Array.isArray(items) ? items : []).find(e => isObj(e) && (e.id === k || e.node === k)) || null;
  }

  function heading(items, activeId) {
    const e = entryOf(items, activeId) || entryOf(items, ORG);
    return "Chat with " + (e ? clean(e.label) : ORG_LABEL);
  }

  function tab(e, active) {
    const label = short(clean(e.label));
    const badge = e.waiting > 0 ? '<span class="csbadge" aria-label="' + e.waiting + (e.waiting === 1 ? " question waits" : " questions wait") + '">' + e.waiting + "</span>" : "";
    const title = e.kind === "division" && e.parent ? ' title="' + esc("A division of " + e.parent) + '"' : "";
    return '<button type="button" role="tab" class="cstab' + (active ? " on" : "") + '" id="cstab-' + esc(e.id) + '" data-act="switch-chat" data-session="' + esc(e.id) +
      '" data-node="' + esc(e.node) + '" data-kind="' + esc(e.kind) + '" aria-selected="' + active + '" tabindex="' + (active ? 0 : -1) + '"' + title + ">" +
      esc(label) + badge + "</button>";
  }

  function bar(items, activeId) {
    const all = (Array.isArray(items) ? items : []).filter(e => isObj(e) && idOf(e.id) !== "");
    if (all.length < 2) return "";
    const current = all.some(e => e.id === activeId) ? activeId : ORG;
    return all.map(e => tab(e, e.id === current)).join("");
  }

  function nextIndex(key, count, current) {
    const n = Number(count);
    const i = Number(current);
    if (!Number.isInteger(n) || n < 1 || !Number.isInteger(i)) return -1;
    if (key === "ArrowRight") return (i + 1) % n;
    if (key === "ArrowLeft") return (i - 1 + n) % n;
    if (key === "Home") return 0;
    if (key === "End") return n - 1;
    return -1;
  }

  const ChatSwitch = {entries, bar, heading, nextIndex, entryOf, ORG};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatSwitch;
  else root.ChatSwitch = ChatSwitch;
})(globalThis);
