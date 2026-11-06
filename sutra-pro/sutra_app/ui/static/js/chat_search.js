/* chat_search.js - search, archive and attachments of a chat (work package ABS-10; absorb design 2.3).

   Strings in, strings out. The search box asks GET /api/chats/search with the scope of the panel, results show a title and a snippet, every word
   from the wire is escaped (ui.md 4.3), and archived chats are listed under "Older chats".

     request(q, scope, includeArchived)   {path, query} for the GET (a blank query asks nothing: null)
     scopeOf(session, deptId)             "node:<id>" for a node chat, "dept:<id>" for a team, "all" otherwise
     results(rows)                        the list: active matches first, "Older chats" below
     archiveButton(session)               the Archive or Un-archive button, "" where the app refuses it (the org chat, an imported chat)
     limits / checkFile(file)             the attachment limits shown to the owner and the check of one file ("" when it is fine)
     limitsNote()                         "Up to 10 files, 20 MB each: images, PDFs and text files."

   Buttons carry data-act (open-chat with data-sid and data-mid, archive, unarchive). A classic script with ONE global, ChatSearch. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ID = /^[a-z][a-z0-9_.-]{1,60}$/;
  const limits = Object.freeze({files: 10, bytes: 20 * 1024 * 1024, kinds: "images, PDFs and text files"});
  const TEXT_EXT = /\.(txt|md|markdown|csv|tsv|json|log|ya?ml|toml|ini|xml|html?|css|jsx?|tsx?|py|sql|sh|rb|go|java|rs)$/i;
  const BINARY_EXT = /\.(png|jpe?g|gif|webp|pdf)$/i;

  function request(q, scope, includeArchived) {
    const words = clean(q);
    if (words === "") return null;
    const query = {q: words.slice(0, 200), scope: /^(all|node:[a-z][a-z0-9_.-]{1,60}|dept:[a-z][a-z0-9_-]{1,40})$/.test(scope) ? scope : "all"};
    if (includeArchived === true) query.include = "archived";
    return {path: "/api/chats/search", query};
  }

  function scopeOf(session, deptId) {
    const s = isObj(session) ? session : {};
    const dept = clean(deptId);
    if (dept !== "" && ID.test(dept) && (clean(s.kind) === "department" || clean(s.kind) === "division")) return "dept:" + dept;
    const node = clean(s.node_id);
    return node !== "" && ID.test(node) && clean(s.kind) !== "org" ? "node:" + node : "all";
  }

  function row(r) {
    return '<li class="csearch-row"><button type="button" class="linkbtn" data-act="open-chat" data-sid="' + esc(clean(r.session_id)) + '" data-mid="' +
      esc(text(r.message_id)) + '"><b>' + esc(clean(r.title) || clean(r.session_id)) + "</b> <span>" + esc(clean(r.snippet)) + "</span></button></li>";
  }

  function results(rows) {
    const list = (Array.isArray(rows) ? rows : []).filter(isObj);
    if (list.length === 0) return '<p class="empty csearch-empty">Nothing found.</p>';
    const now = list.filter(r => r.archived !== true);
    const old = list.filter(r => r.archived === true);
    return (now.length ? '<ul class="csearch-list">' + now.map(row).join("") + "</ul>" : "") +
      (old.length ? '<p class="csearch-head">Older chats</p><ul class="csearch-list older">' + old.map(row).join("") + "</ul>" : "");
  }

  function archiveButton(session) {
    const s = isObj(session) ? session : {};
    const kind = clean(s.kind);
    if (kind === "org" || kind === "legacy" || s.filed_under) return "";
    return clean(s.status) === "archived"
      ? '<button type="button" class="linkbtn" data-act="unarchive" data-sid="' + esc(clean(s.id)) + '">Bring this chat back</button>'
      : '<button type="button" class="linkbtn" data-act="archive" data-sid="' + esc(clean(s.id)) + '">Archive this chat</button>';
  }

  const limitsNote = () => "Up to " + limits.files + " files, " + limits.bytes / (1024 * 1024) + " MB each: " + limits.kinds + ".";

  function checkFile(file) {
    if (!isObj(file)) return "That file could not be read.";
    const name = clean(file.name);
    if (!Number.isFinite(file.size) || file.size <= 0) return name + " is empty.";
    if (file.size > limits.bytes) return name + " is over " + limits.bytes / (1024 * 1024) + " MB.";
    if (!BINARY_EXT.test(name) && !TEXT_EXT.test(name)) return "Only " + limits.kinds + " can be attached.";
    return "";
  }

  const ChatSearch = {request, scopeOf, results, archiveButton, checkFile, limitsNote, limits};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatSearch;
  else root.ChatSearch = ChatSearch;
})(globalThis);
