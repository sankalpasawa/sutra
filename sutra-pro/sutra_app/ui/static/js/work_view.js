/* work_view.js - what the Work page draws (DV-2, docs/design/devin-parity.md): strings in, strings out, no DOM, no timer, so `node --test` runs it.

   Pieces: filtersHtml(tags, filter, statuses), listHtml(items, state), summaryHtml(summary), tagsFromText(text), tagsToText(tags).
   Every word from the wire goes through esc(); a link is a link only when it is a path on this origin of the two shapes the server makes (`/d/<team>/` and `/p/prj_...`). The words are the owner's:
   "Task", "Project", "How did it go?", never a machine name. A classic script with ONE global, WorkView; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const arr = v => (Array.isArray(v) ? v : []);
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const KIND_WORDS = Object.freeze({task: "Task", project: "Project"});
  const STATUS_ORDER = Object.freeze(["running", "starting", "queued", "blocked", "waiting_user", "awaiting_approval", "planning", "reviewing", "done", "done_with_open_items", "stopped", "crashed", "failed", "cancelled"]);
  const STATUS_WORDS = Object.freeze({blocked: "Waiting for another step", queued: "Waiting to start", starting: "Starting", running: "Working", waiting_user: "Waiting for your answer",
    done: "Done", done_with_open_items: "Done, with some things left open", stopped: "Stopped", crashed: "Did not finish", cancelled: "Cancelled", planning: "Planning",
    awaiting_approval: "Waiting for your answer", reviewing: "Being checked", failed: "Could not finish"});
  const LINK = /^\/(?:d\/[A-Za-z0-9_.:-]{1,120}\/|p\/prj_[0-9a-f]{12})$/;

  // "cafe, weekly" -> ["cafe", "weekly"]; the server decides what a tag may be, this only splits and drops empties.
  function tagsFromText(text) {
    return String(text || "").split(",").map(t => t.trim()).filter(Boolean);
  }
  const tagsToText = tags => arr(tags).map(clean).filter(Boolean).join(", ");

  function filtersHtml(tags, filter, statuses) {
    const f = isObj(filter) ? filter : {};
    const options = ['<option value="">Any state</option>'].concat(STATUS_ORDER.filter(s => arr(statuses).indexOf(s) >= 0).map(s =>
      '<option value="' + esc(s) + '"' + (f.status === s ? " selected" : "") + ">" + esc(STATUS_WORDS[s] || s) + "</option>"));
    const chips = arr(tags).filter(isObj).map(t => '<button type="button" class="wtag" data-act="filter-tag" data-tag="' + esc(clean(t.tag)) + '" aria-pressed="' + (f.tag === t.tag ? "true" : "false") + '">' +
      esc(clean(t.tag)) + " (" + esc(Number.isFinite(t.count) ? t.count : 0) + ")</button>").join("");
    return '<div class="wfind"><input type="search" id="w-q" maxlength="200" placeholder="Find work by words" aria-label="Find work by words" value="' + esc(clean(f.q)) + '">' +
      '<select id="w-status" aria-label="State">' + options.join("") + "</select></div>" + (chips ? '<div class="wtags" aria-label="Tags">' + chips + "</div>" : "");
  }

  function tagChips(tags) {
    const list = arr(tags).map(clean).filter(Boolean);
    return list.length ? '<span class="wtags">' + list.map(t => '<span class="wtag" data-tag="' + esc(t) + '">' + esc(t) + "</span>").join("") + "</span>" : "";
  }

  function when(iso) {
    const d = typeof iso === "string" ? new Date(iso) : null;
    return d && !isNaN(d.getTime()) ? d.toLocaleDateString(undefined, {day: "numeric", month: "short"}) : "";
  }

  function summaryHtml(summary) {
    if (summary === "loading") return '<div class="wsum" role="status"><p>Working it out&hellip;</p></div>';
    if (!isObj(summary)) return "";
    if (typeof summary.error === "string") return '<div class="wsum" role="alert"><p>' + esc(clean(summary.error)) + "</p></div>";
    const lines = arr(summary.lines).map(clean).filter(Boolean);
    const steps = arr(summary.steps).filter(isObj).map(s => "<li><b>" + esc(clean(s.name)) + "</b> " + esc(clean(s.state_word)) + (s.calls ? ", " + esc(s.calls) + (s.calls === 1 ? " credit" : " credits") : "") +
      (Number.isFinite(s.usd) ? ", about $" + esc(s.usd.toFixed(2)) : "") + (s.tries > 1 ? ", " + esc(s.tries) + " tries" : "") + "</li>").join("");
    return '<div class="wsum" data-summary="' + esc(clean(summary.project_id)) + '">' + lines.map(l => "<p>" + esc(l) + "</p>").join("") + (steps ? '<ul class="plist">' + steps + "</ul>" : "") + "</div>";
  }

  function editForm(item) {
    return '<form class="wedit" data-act="tags-save" data-kind="' + esc(item.kind) + '" data-id="' + esc(item.id) + '"><label class="cnote" for="w-tags-' + esc(item.id) + '">Tags, separated by commas</label>' +
      '<input id="w-tags-' + esc(item.id) + '" name="tags" value="' + esc(tagsToText(item.tags)) + '" maxlength="300"><button type="submit">Save</button><button type="button" data-act="tags-cancel">Cancel</button></form>';
  }

  function listHtml(items, state) {
    const s = isObj(state) ? state : {};
    const list = arr(items).filter(isObj);
    if (list.length === 0) return '<p class="cempty">' + (s.filtered ? "Nothing matches." : "Nothing yet. Work you ask Sutra for shows up here.") + "</p>";
    const more = s.more ? '<p class="cnote">Showing the newest ' + esc(list.length) + ". " + '<button type="button" data-act="show-more">Show more</button></p>' : "";
    return '<ul class="plist wlist">' + list.map(item => {
      const id = clean(item.id);
      const link = typeof item.link === "string" && LINK.test(item.link) ? item.link : "";
      const title = clean(item.title) || "Untitled";
      const editing = s.editing === id;
      const sum = isObj(s.summaries) ? s.summaries[id] : undefined;
      return '<li class="witem" data-kind="' + esc(clean(item.kind)) + '" data-id="' + esc(id) + '"><div class="wtop"><span class="wkind">' + esc(KIND_WORDS[item.kind] || "Work") + "</span>" +
        (link ? '<a href="' + esc(link) + '">' + esc(title) + "</a>" : "<b>" + esc(title) + "</b>") + '<span class="pstate">' + esc(clean(item.status_word) || STATUS_WORDS[item.status] || "") + "</span>" +
        (clean(item.team) ? '<span class="cnote">' + esc(clean(item.team)) + "</span>" : "") + (when(item.created_at) ? '<span class="cnote">' + esc(when(item.created_at)) + "</span>" : "") + "</div>" +
        (editing ? editForm(item) : tagChips(item.tags) + '<span class="wedit"><button type="button" data-act="tags-edit" data-id="' + esc(id) + '">' + (arr(item.tags).length ? "Change tags" : "Add tags") + "</button>" +
          (item.kind === "project" ? '<button type="button" data-act="how" data-id="' + esc(id) + '">How did it go?</button>' : "") + "</span>") + summaryHtml(sum) + "</li>";
    }).join("") + "</ul>" + more;
  }

  const WorkView = {esc, KIND_WORDS, STATUS_WORDS, STATUS_ORDER, tagsFromText, tagsToText, filtersHtml, listHtml, summaryHtml};
  if (typeof module === "object" && module !== null && module.exports) module.exports = WorkView;
  else root.WorkView = WorkView;
})(globalThis);
