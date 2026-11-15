/* SectionsStore: the owner's sidebar sections ("Clients", "Internal"), named groups of projects, kept on the server (orchestrator/sections.py) so they
   survive a restart and a new port. Browser storage is never used: it is per port.

     load(api)                  GET /api/sections -> the document; any failure reads as the empty default, so the sidebar still draws
     save(doc, api)             PUT /api/sections -> Promise<{ok, data, error}>: `data` is the document as the server kept it, `error` a sentence
     assign(doc, teamId, sectionId|null)    a new document with the team in that section (and out of every other), or in none
     add(doc, name)             a new document with a section at the end (a fresh sec_ id); an empty or overlong name, or a full list, changes nothing
     rename(doc, id, name)      a new document with that section renamed (the same name rules)
     remove(doc, id)            a new document without that section; its teams go back to "All projects"
     copy(doc)                  a well formed copy (the sidebar flips `collapsed` on it)
     group(doc, teams)          [{section, teams}, ..., {section: null, teams}]: each section in order with its teams in `teams` order, then the rest

   `api` defaults to SutraCtx.api (sutra_ctx.js); a test hands in a fake. `teams` in group() is the list of team ids the sidebar shows (strings, or
   objects with an `id`), and each entry keeps its own form. A saved team the sidebar does not show is left out of the groups but kept in the document.
   The helpers never change the document they are given. Names follow the server: control characters dropped, trimmed, 1 to NAME_CHARS long.

   A classic script with ONE global, SectionsStore; in node it is module.exports. */
(function (root) {
  "use strict";

  const PATH = "/api/sections";
  const VERSION = 1;
  const MAX_SECTIONS = 30;
  const NAME_CHARS = 40;
  const CONTROL = /[\x00-\x1f\x7f-\x9f]/g;

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const empty = () => ({version: VERSION, sections: []});
  const cleanName = name => (typeof name === "string" ? name.replace(CONTROL, "").trim() : "");
  const okName = name => name.length >= 1 && name.length <= NAME_CHARS;
  const teamId = t => (typeof t === "string" ? t : isObj(t) && typeof t.id === "string" ? t.id : "");

  // A copy that is always well formed: a missing or odd document is the empty default, an odd section is dropped.
  function copy(doc) {
    const list = isObj(doc) && Array.isArray(doc.sections) ? doc.sections : [];
    return {
      version: VERSION,
      sections: list.filter(isObj).map(s => ({
        id: String(s.id || ""), name: String(s.name || ""),
        teams: Array.isArray(s.teams) ? s.teams.filter(t => typeof t === "string") : [], collapsed: s.collapsed === true,
      })),
    };
  }

  function newId(taken) {
    for (;;) {
      const id = "sec_" + Math.random().toString(36).slice(2, 8).padEnd(6, "0");
      if (!taken.has(id)) return id;
    }
  }

  const apiOf = api => api || root.SutraCtx?.api;

  async function load(api) {
    try {
      const data = await apiOf(api).get(PATH);
      return isObj(data) && Array.isArray(data.sections) ? copy(data) : empty();
    } catch (e) {
      return empty();
    }
  }

  async function save(doc, api) {
    try {
      return {ok: true, data: copy(await apiOf(api).put(PATH, copy(doc))), error: ""};
    } catch (e) {
      return {ok: false, data: null, error: String((e && e.message) || "The sections could not be saved.")};
    }
  }

  function assign(doc, team, sectionId) {
    const next = copy(doc);
    if (typeof team !== "string" || team === "") return next;
    const target = sectionId === null || sectionId === undefined ? null : next.sections.find(s => s.id === sectionId);
    if (sectionId !== null && sectionId !== undefined && !target) return copy(doc);       // an unknown section changes nothing
    next.sections.forEach(s => { s.teams = s.teams.filter(t => t !== team); });
    if (target) target.teams.push(team);
    return next;
  }

  function add(doc, name) {
    const next = copy(doc);
    const clean = cleanName(name);
    if (!okName(clean) || next.sections.length >= MAX_SECTIONS) return next;
    next.sections.push({id: newId(new Set(next.sections.map(s => s.id))), name: clean, teams: [], collapsed: false});
    return next;
  }

  function rename(doc, id, name) {
    const next = copy(doc);
    const clean = cleanName(name);
    const found = next.sections.find(s => s.id === id);
    if (found && okName(clean)) found.name = clean;
    return next;
  }

  function remove(doc, id) {
    const next = copy(doc);
    next.sections = next.sections.filter(s => s.id !== id);
    return next;
  }

  function group(doc, teams) {
    const shown = Array.isArray(teams) ? teams : [];
    const byId = new Map();
    shown.forEach(t => { const id = teamId(t); if (id && !byId.has(id)) byId.set(id, t); });
    const placed = new Set();
    const out = copy(doc).sections.map(section => {
      const mine = new Set(section.teams.filter(id => !placed.has(id)));
      mine.forEach(id => placed.add(id));
      return {section: section, teams: shown.filter(t => mine.has(teamId(t)) && byId.get(teamId(t)) === t)};
    });
    out.push({section: null, teams: shown.filter(t => !placed.has(teamId(t)) && byId.get(teamId(t)) === t)});
    return out;
  }

  const SectionsStore = {load, save, assign, add, rename, remove, group, copy, cleanName, PATH, VERSION, MAX_SECTIONS, NAME_CHARS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = SectionsStore;
  else root.SectionsStore = SectionsStore;
})(globalThis);
