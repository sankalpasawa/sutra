/* notes_view.js - the owner's notes, a group of the Settings pane (GAP2 rules-notes; the old app's "what Shadow knows", the owner-typed half).

   Strings in, strings out, plus the few small flows that talk to the server through an `api` the caller hands in (SutraCtx.api, or a fake in a test):
   this file touches no DOM and no timer, so `node --test` runs all of it. Every word from the wire goes through esc().

     notesHtml(state) -> html          the group: what notes are, one list per kind (About you, Your work, How you like things done) with its count,
                                       each note's date ("until 2027-01-31", or "expired 2026-10-01: it no longer applies" in the muted tone, never
                                       dropped), Edit and Forget, then the add form. state = {data, error, editing, draft, busy, saved}
                                         data     the answer of GET /api/notes, or null while it loads
                                         error    one sentence for the whole group ("" for none)
                                         editing  the id of the note whose text and date are open as fields, or 0
                                         draft    what was typed and refused, kept beside the sentence {group, text, expires}
     addRequest(form) / editRequest(id, form) / forgetRequest(id)    {method, path, body} for POST, PUT and DELETE /api/notes
     errorWords(error) -> sentence     the server's own words for a refusal (a key, a full list, a repeat, a past date), else a plain fallback
     loadNotes(api) -> Promise<data>   GET /api/notes
     addNote(api, form) / editNote(api, id, form) / forgetNote(api, id) -> Promise<{ok, data, error}>   the write, then the list read again

   A note says what stays true ("my brand voice is plain, no jargon"); it binds as soon as it is written. A key, a token or a password is refused by the
   server and never kept; a full list refuses a new line and removes nothing. A classic script with ONE global, NotesView; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();

  const PATH = "/api/notes";
  const GROUPS = Object.freeze([["about-you", "About you"], ["work", "Your work"], ["preferences", "How you like things done"]]);
  const LABEL = Object.freeze(Object.fromEntries(GROUPS));
  const FALLBACK = "That note could not be kept. Try again.";
  const INTRO = "Things that stay true. Write one once and it binds at once: Sutra passes the ones that matter to a team in the brief it writes, and the " +
    "direct chats see them. Nothing is guessed. Never type a key or a password here.";

  /* ---------------------------------------------------------------- requests and words */
  const idOf = id => (Number.isInteger(id) && id > 0 ? id : 0);
  const dateOf = v => (/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(clean(v)) ? clean(v) : null);

  function addRequest(form) {
    const f = isObj(form) ? form : {};
    return {method: "POST", path: PATH, body: {group: hasOwn(LABEL, f.group) ? f.group : "work", text: clean(f.text), expires: dateOf(f.expires)}};
  }

  // An edit sends the text and the date as they stand; an empty date field makes the note undated.
  function editRequest(id, form) {
    const f = isObj(form) ? form : {};
    return {method: "PUT", path: PATH + "/" + idOf(id), body: {text: clean(f.text), expires: dateOf(f.expires)}};
  }

  const forgetRequest = id => ({method: "DELETE", path: PATH + "/" + idOf(id), body: null});

  function errorWords(error) {
    const details = isObj(error) && isObj(error.details) ? error.details : {};
    const first = Array.isArray(details.violations) ? details.violations.find(v => isObj(v) && clean(v.message) !== "") : null;
    if (first) return clean(first.message);
    if (isObj(error) && error.status === 401) return "This page was opened without its access token. Reload it from the app.";
    return clean(isObj(error) ? error.message : "") || FALLBACK;
  }

  /* ---------------------------------------------------------------- drawing */
  const notesOf = data => (isObj(data) && Array.isArray(data.notes) ? data.notes.filter(n => isObj(n) && Number.isInteger(n.id) && hasOwn(LABEL, n.group)) : []);

  function dateWords(n) {
    const when = dateOf(n.expires);
    if (when === null) return "";
    return n.expired === true ? "expired " + when + ": it no longer applies" : "until " + when;
  }

  function noteRow(n, o) {
    if (o.editing === n.id) {
      const d = isObj(o.draft) && o.draft.id === n.id ? o.draft : {text: n.text, expires: n.expires};
      return '<li class="note editing" data-note="' + n.id + '"><input type="text" data-note-text maxlength="' + o.max + '" aria-label="The note" value="' + esc(clean(d.text)) + '">' +
        '<input type="date" data-note-date aria-label="Stops applying on" value="' + esc(dateOf(d.expires) || "") + '">' +
        '<button type="button" class="ghost" data-act="note-save" data-id="' + n.id + '"' + (o.busy ? " disabled" : "") + '>Save</button> ' +
        '<button type="button" class="linkbtn" data-act="note-cancel">Cancel</button></li>';
    }
    const when = dateWords(n);
    return '<li class="note' + (n.expired === true ? " expired" : "") + '" data-note="' + n.id + '"><span class="notetext">' + esc(clean(n.text)) + "</span>" +
      (when ? ' <small class="notewhen">' + esc(when) + "</small>" : "") +
      ' <button type="button" class="linkbtn" data-act="note-edit" data-id="' + n.id + '">Edit</button>' +
      ' <button type="button" class="linkbtn" data-act="note-forget" data-id="' + n.id + '">Forget</button></li>';
  }

  function groupHtml(id, label, notes, o) {
    const mine = notes.filter(n => n.group === id);
    return '<div class="notegrp" data-notegroup="' + id + '"><h4 class="setsub">' + esc(label) + ' <small>' + mine.length + " of " + o.per + "</small></h4>" +
      (mine.length ? '<ul class="notelist">' + mine.map(n => noteRow(n, o)).join("") + "</ul>" : '<p class="setempty">Nothing here yet.</p>') + "</div>";
  }

  function addForm(o) {
    const d = isObj(o.draft) && !hasOwn(o.draft, "id") ? o.draft : {};
    const picked = hasOwn(LABEL, d.group) ? d.group : "work";
    return '<div class="noteadd"><select data-note-group aria-label="What kind of note">' +
      GROUPS.map(g => '<option value="' + g[0] + '"' + (g[0] === picked ? " selected" : "") + ">" + esc(g[1]) + "</option>").join("") + "</select>" +
      '<input type="text" data-note-text maxlength="' + o.max + '" aria-label="The note" placeholder="For example: My brand voice is plain, with no jargon" value="' + esc(clean(d.text)) + '">' +
      '<input type="date" data-note-date aria-label="Stops applying on (optional)" value="' + esc(dateOf(d.expires) || "") + '">' +
      '<button type="button" class="ghost" data-act="note-add"' + (o.busy ? " disabled" : "") + ">Add</button></div>";
  }

  function notesHtml(state) {
    const s = isObj(state) ? state : {};
    const data = isObj(s.data) ? s.data : null;
    const o = {editing: idOf(s.editing), draft: s.draft, busy: s.busy === true, per: data && Number.isInteger(data.per_group) ? data.per_group : 10,
      max: data && Number.isInteger(data.max_chars) ? data.max_chars : 300};
    const head = '<section class="setgrp" data-group="notes" aria-labelledby="set-notes-h"><h3 id="set-notes-h">Notes</h3><p class="setnote">' + esc(INTRO) + "</p>";
    if (data === null) return head + (clean(s.error) ? '<p class="seterr setgen" role="alert">' + esc(clean(s.error)) + "</p>" : '<p class="setempty">Loading…</p>') + "</section>";
    const notes = notesOf(data);
    return head + (clean(s.error) ? '<p class="seterr setgen" role="alert">' + esc(clean(s.error)) + "</p>" : "") +
      GROUPS.map(g => groupHtml(g[0], g[1], notes, o)).join("") + addForm(o) +
      '<p class="setstatus" role="status">' + esc(clean(s.saved)) + "</p></section>";
  }

  /* ---------------------------------------------------------------- flows */
  const loadNotes = api => api.get(PATH);

  async function send(api, req) {
    try {
      await (req.method === "POST" ? api.post(req.path, req.body) : req.method === "PUT" ? api.put(req.path, req.body) : api.del(req.path));
    } catch (e) {
      return {ok: false, data: null, error: errorWords(e)};
    }
    try {
      return {ok: true, data: await loadNotes(api), error: ""};
    } catch (e) {
      return {ok: true, data: null, error: errorWords(e)};
    }
  }

  const addNote = (api, form) => send(api, addRequest(form));
  const editNote = (api, id, form) => send(api, editRequest(id, form));
  const forgetNote = (api, id) => send(api, forgetRequest(id));

  const NotesView = {notesHtml, addRequest, editRequest, forgetRequest, errorWords, loadNotes, addNote, editNote, forgetNote, GROUPS, INTRO};
  if (typeof module === "object" && module !== null && module.exports) module.exports = NotesView;
  else root.NotesView = NotesView;
})(globalThis);
