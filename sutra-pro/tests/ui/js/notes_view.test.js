"use strict";
// NotesView (sutra_app/ui/static/js/notes_view.js): the owner's notes group of Settings. Strings in, strings out, and the flows over a fake api.
// GAP2 rules-notes. Run with: node --test tests/ui/js/notes_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const NotesView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/notes_view.js"));
const {notesHtml, addRequest, editRequest, forgetRequest, errorWords, loadNotes, addNote, editNote, forgetNote} = NotesView;

const note = (id, group, text, expires = null, expired = false) => ({id, group, text, expires, expired});
const DATA = {
  notes: [note(1, "about-you", "I run a small cafe."), note(2, "preferences", "My brand voice is plain, no jargon."),
    note(3, "work", "Closed for the holiday.", "2026-10-01", true), note(4, "work", "Open until the new menu.", "2027-01-31")],
  groups: [{id: "about-you", label: "About you"}, {id: "work", label: "Your work"}, {id: "preferences", label: "How you like things done"}],
  per_group: 10, max_chars: 300,
};

test("the group says what notes are, lists the three kinds with their counts, and ends with the add form", () => {
  const html = notesHtml({data: DATA});
  assert.match(html, /<h3 id="set-notes-h">Notes<\/h3>/);
  assert.match(html, /Things that stay true\. Write one once and it binds at once/);
  assert.match(html, /Never type a key or a password here/);
  for (const [id, label, count] of [["about-you", "About you", 1], ["work", "Your work", 2], ["preferences", "How you like things done", 1]]) {
    const at = html.indexOf('data-notegroup="' + id + '"');
    assert.ok(at > 0, id);
    assert.match(html.slice(at, at + 200), new RegExp(label + " <small>" + count + " of 10</small>"));
  }
  assert.ok(html.indexOf("noteadd") > html.lastIndexOf("notegrp"));
  assert.match(html, /data-act="note-add"/);
  assert.match(html, /<option value="work" selected>Your work<\/option>/);
});

test("a dated note says until when; an expired one is listed, flagged and says it no longer applies, never dropped", () => {
  const html = notesHtml({data: DATA});
  assert.match(html, /Open until the new menu\.<\/span> <small class="notewhen">until 2027-01-31<\/small>/);
  assert.match(html, /<li class="note expired" data-note="3"><span class="notetext">Closed for the holiday\.<\/span> <small class="notewhen">expired 2026-10-01: it no longer applies<\/small>/);
  assert.match(html, /data-act="note-forget" data-id="3"/);
  assert.doesNotMatch(notesHtml({data: DATA}).split('data-note="1"')[1].split("</li>")[0], /notewhen/);
});

test("an empty list says so for every kind and still offers the form", () => {
  const html = notesHtml({data: {notes: [], per_group: 10, max_chars: 300}});
  assert.equal((html.match(/Nothing here yet\./g) || []).length, 3);
  assert.match(html, /data-act="note-add"/);
});

test("loading and a failed load say so, in the server's words", () => {
  assert.match(notesHtml({data: null}), /Loading/);
  assert.match(notesHtml({data: null, error: "The app is not responding."}), /role="alert">The app is not responding\./);
  assert.doesNotMatch(notesHtml({data: null, error: "x"}), /noteadd/);
});

test("every word from the wire is escaped, in the list, the fields and the sentences", () => {
  const evil = '<img src=x onerror=alert(1)>"\'&';
  const html = notesHtml({data: {notes: [note(9, "work", evil, "2027-01-01")], per_group: 10, max_chars: 300}, error: evil, saved: evil, editing: 9,
    draft: {id: 9, text: evil, expires: "2027-01-01"}});
  assert.doesNotMatch(html, /<img/);
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;&quot;&#39;&amp;"));
  const add = notesHtml({data: DATA, draft: {group: "work", text: evil}});
  assert.doesNotMatch(add, /<img/);
  assert.match(add, /value="&lt;img/);
});

test("a note being edited shows its text and date as fields with Save and Cancel; the others keep Edit and Forget", () => {
  const html = notesHtml({data: DATA, editing: 4});
  const row = html.split('data-note="4"')[1].split("</li>")[0];
  assert.match(row, /data-note-text[^>]*value="Open until the new menu\."/);
  assert.match(row, /type="date" data-note-date[^>]*value="2027-01-31"/);
  assert.match(row, /data-act="note-save" data-id="4"/);
  assert.match(row, /data-act="note-cancel"/);
  assert.match(html.split('data-note="1"')[1].split("</li>")[0], /data-act="note-edit" data-id="1"/);
  assert.match(notesHtml({data: DATA, busy: true}), /data-act="note-add" disabled/);
});

test("a refusal keeps what was typed beside the sentence", () => {
  const html = notesHtml({data: DATA, error: "Forget one first.", draft: {group: "preferences", text: "Plain words", expires: "2027-02-02"}});
  assert.match(html, /role="alert">Forget one first\./);
  assert.match(html, /<option value="preferences" selected>/);
  assert.match(html, /data-note-text[^>]*value="Plain words"/);
  assert.match(html, /data-note-date[^>]*value="2027-02-02"/);
});

test("requests: the group is one of the three, the text one clean line, the date a real shape or null, ids whole numbers", () => {
  assert.deepEqual(addRequest({group: "preferences", text: "  Plain \n words ", expires: "2027-01-31"}),
    {method: "POST", path: "/api/notes", body: {group: "preferences", text: "Plain words", expires: "2027-01-31"}});
  assert.deepEqual(addRequest({group: "nope", text: "x", expires: "tomorrow"}).body, {group: "work", text: "x", expires: null});
  assert.deepEqual(addRequest(null).body, {group: "work", text: "", expires: null});
  assert.deepEqual(editRequest(4, {text: " New ", expires: ""}), {method: "PUT", path: "/api/notes/4", body: {text: "New", expires: null}});
  assert.deepEqual(forgetRequest(4), {method: "DELETE", path: "/api/notes/4", body: null});
  assert.equal(forgetRequest("4; drop").path, "/api/notes/0");
  assert.equal(editRequest(-1, {}).path, "/api/notes/0");
});

test("errorWords takes the server's sentence for a refusal and a plain one otherwise", () => {
  const refused = {status: 422, code: "validation", message: "That note could not be kept", details: {violations: [{path: "text", code: "refused", message: "That line looks like it holds a key."}]}};
  assert.equal(errorWords(refused), "That line looks like it holds a key.");
  assert.equal(errorWords({status: 422, message: "Nope.", details: {}}), "Nope.");
  assert.match(errorWords({status: 401}), /without its access token/);
  assert.equal(errorWords(null), "That note could not be kept. Try again.");
  assert.equal(errorWords({details: {violations: [{message: "  "}]}, message: ""}), "That note could not be kept. Try again.");
});

function fakeApi(script = {}) {
  const calls = [];
  const answer = (name, path, body) => {
    calls.push([name, path, body]);
    const made = script[name + " " + path];
    if (made instanceof Error) throw made;
    return made === undefined ? (name === "get" ? DATA : null) : made;
  };
  return {calls, get: async path => answer("get", path), post: async (path, body) => answer("post", path, body), put: async (path, body) => answer("put", path, body),
    del: async path => answer("del", path)};
}

test("a write goes out as built and the list is read again", async () => {
  const api = fakeApi();
  const added = await addNote(api, {group: "work", text: "Open at nine.", expires: ""});
  assert.deepEqual(added, {ok: true, data: DATA, error: ""});
  assert.deepEqual(api.calls, [["post", "/api/notes", {group: "work", text: "Open at nine.", expires: null}], ["get", "/api/notes", undefined]]);
  const api2 = fakeApi();
  await editNote(api2, 2, {text: "x", expires: "2027-01-01"});
  await forgetNote(api2, 2);
  assert.deepEqual(api2.calls.map(c => c[0] + " " + c[1]), ["put /api/notes/2", "get /api/notes", "del /api/notes/2", "get /api/notes"]);
  assert.deepEqual(await loadNotes(fakeApi()), DATA);
});

test("a refusal gives the sentence and no second read; a failed re-read still counts as written", async () => {
  const refusal = Object.assign(new Error("That note could not be kept"), {status: 422, details: {violations: [{message: "Your work already holds 10 notes."}]}});
  const api = fakeApi({"post /api/notes": refusal});
  assert.deepEqual(await addNote(api, {text: "x"}), {ok: false, data: null, error: "Your work already holds 10 notes."});
  assert.equal(api.calls.length, 1);
  const down = Object.assign(new Error("The app is not responding."), {status: 0});
  const later = await forgetNote(fakeApi({"get /api/notes": down}), 1);
  assert.deepEqual(later, {ok: true, data: null, error: "The app is not responding."});
});

// QA firstrun-settings: an empty note was sent and the owner read pydantic's "String should have at least 1 character".
test("an empty or blank note, added or edited, sends nothing and says to write it first", async () => {
  for (const text of ["", "   ", "\n\t "]) {
    const api = fakeApi();
    assert.deepEqual(await addNote(api, {group: "work", text, expires: ""}), {ok: false, data: null, error: "Write the note first."}, JSON.stringify(text));
    assert.deepEqual(await editNote(api, 3, {text, expires: ""}), {ok: false, data: null, error: "Write the note first."}, JSON.stringify(text));
    assert.deepEqual(api.calls, [], "no request is made");
  }
  const forget = fakeApi();
  assert.equal((await forgetNote(forget, 1)).ok, true);                                      // a forget has no text and still goes
  assert.deepEqual(forget.calls.map(c => c[0] + " " + c[1]), ["del /api/notes/1", "get /api/notes"]);
});
