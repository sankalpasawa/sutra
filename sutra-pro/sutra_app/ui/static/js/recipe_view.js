/* recipe_view.js - what the Recipes page draws (DV-3): strings in, strings out, no DOM, no timer, so `node --test` runs it.

   Pieces: listHtml(recipes), detailHtml(recipe, state), editHtml(draft, state), startHtml(recipe, state), versionsHtml(recipe), toLines(text), fromLines(lines).
   Every word from the wire goes through esc(). The words are the owner's: "Recipe", "Start", "Go back to this version", never "playbook", "cron" or a machine name. A classic script with ONE global,
   RecipeView; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const arr = v => (Array.isArray(v) ? v : []);
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ID = /^(rcp_[0-9a-f]{12}|starter-[a-z0-9-]{1,60})$/;
  const PARTS = Object.freeze([["procedure", "Steps, in order", true], ["specifications", "The result must be like this", false], ["advice", "Good to know", false], ["forbidden", "Never do these", false]]);

  const toLines = text => String(text || "").split("\n").map(l => l.trim()).filter(Boolean);
  const fromLines = lines => arr(lines).map(clean).filter(Boolean).join("\n");

  function listHtml(recipes) {
    const list = arr(recipes).filter(r => isObj(r) && ID.test(clean(r.id)));
    const row = r => '<li data-id="' + esc(clean(r.id)) + '"><div class="rtop"><span class="rkind">' + (r.kind === "starter" ? "Starter" : "Recipe") + '</span><b>' + esc(clean(r.title)) + "</b>" +
      '<span class="cnote">' + (r.kind === "starter" ? "ships with Sutra, read only" : r.version > 1 ? "version " + esc(r.version) : "") + "</span></div>" +
      (clean(r.overview) ? '<span class="cnote">' + esc(clean(r.overview)) + "</span>" : "") +
      '<span class="rbtns"><button type="button" data-act="open" data-id="' + esc(clean(r.id)) + '">Open</button></span></li>';
    const own = list.filter(r => r.kind !== "starter"), starters = list.filter(r => r.kind === "starter");
    return '<h2>Recipes</h2><div class="rbtns"><button type="button" class="rgo" data-act="new">New recipe</button><button type="button" data-act="import-open">Read a recipe file</button>' +
      '<button type="button" data-act="toggle-archived">Put-away recipes</button></div>' +
      (own.length ? '<ul class="rlist" aria-label="Your recipes">' + own.map(row).join("") + "</ul>" : '<p class="cempty">You have no recipes yet. Start from one below, or make a new one.</p>') +
      (starters.length ? '<h2>Starters</h2><ul class="rlist" aria-label="Starter recipes">' + starters.map(row).join("") + "</ul>" : "");
  }

  function partHtml(name, label, lines, ordered) {
    const items = arr(lines).map(clean).filter(Boolean);
    if (!items.length) return "";
    return '<div class="rpart"><h3>' + esc(label) + "</h3><" + (ordered ? "ol" : "ul") + ">" + items.map(l => "<li>" + esc(l) + "</li>").join("") + "</" + (ordered ? "ol" : "ul") + "></div>";
  }

  function versionsHtml(recipe) {
    const versions = arr(recipe && recipe.versions).filter(isObj);
    if (versions.length < 2) return "";
    return '<div class="rpart"><h3>Earlier versions</h3><ul class="rlist">' + versions.map(v => '<li><div class="rtop"><b>Version ' + esc(v.version) + "</b>" + '<span class="cnote">' + esc(clean(v.note)) + "</span>" +
      (v.version === recipe.current_version ? '<span class="pstate">this is the one in use</span>' : '<button type="button" data-act="revert" data-version="' + esc(v.version) + '">Go back to this version</button>') + "</div></li>").join("") + "</ul></div>";
  }

  function detailHtml(recipe, state) {
    if (!isObj(recipe)) return "";
    const s = isObj(state) ? state : {};
    const id = clean(recipe.id);
    const body = isObj(recipe.body) ? recipe.body : {};
    const own = recipe.kind !== "starter";
    return '<h2>' + esc(clean(recipe.title)) + '</h2><p class="cnote">' + (own ? "Your recipe" : "A starter that ships with Sutra. It cannot be changed: make a copy to change it.") + (recipe.status === "archived" ? " It is put away." : "") + "</p>" +
      (clean(body.overview) ? "<p>" + esc(clean(body.overview)) + "</p>" : "") + PARTS.map(([p, label, ordered]) => partHtml(p, label, body[p], ordered)).join("") +
      (arr(body.needs).length ? '<div class="rpart"><h3>It asks you for</h3><ol>' + arr(body.needs).filter(isObj).map(n => "<li>" + esc(clean(n.label)) + "</li>").join("") + "</ol></div>" : "") +
      (s.sent ? '<p class="rsent" role="status">' + esc(clean(s.sent)) + "</p>" : "") +
      '<div class="rbtns">' + (recipe.status === "archived" ? "" : '<button type="button" class="rgo" data-act="start-open" data-id="' + esc(id) + '">Start</button>') +
      (own ? '<button type="button" data-act="edit" data-id="' + esc(id) + '">Change</button><button type="button" data-act="archive" data-id="' + esc(id) + '" data-archived="' + (recipe.status === "archived" ? "0" : "1") + '">' +
        (recipe.status === "archived" ? "Bring it back" : "Put it away") + "</button>" : '<button type="button" data-act="copy" data-id="' + esc(id) + '">Make a copy to change</button>') +
      '<a class="ghost" href="/api/recipes/' + esc(id) + '/export" download>Save as a file</a><button type="button" data-act="close">Close</button></div>' +
      (own ? versionsHtml(recipe) : "");
  }

  function startHtml(recipe, state) {
    const needs = arr(recipe && recipe.body && recipe.body.needs).filter(isObj);
    const s = isObj(state) ? state : {};
    return '<form class="rform" data-act="start" data-id="' + esc(clean(recipe && recipe.id)) + '"><h3>Start “' + esc(clean(recipe && recipe.title)) + '”</h3>' +
      (needs.length ? needs.map((n, i) => '<label for="r-blank-' + i + '">' + esc(clean(n.label)) + '</label><input id="r-blank-' + i + '" name="blank' + i + '" maxlength="300" required>').join("") :
        '<p class="cnote">This recipe asks you for nothing.</p>') +
      (s.error ? '<p class="cerr" role="alert">' + esc(clean(s.error)) + "</p>" : "") +
      '<p class="cnote">Starting writes a request in plain words and sends it to Sutra. Sutra plans it and asks you what it needs to ask, like any request.</p>' +
      '<div class="rbtns"><button type="submit" class="rgo">Start</button><button type="button" data-act="start-cancel">Cancel</button></div></form>';
  }

  function editHtml(draft, state) {
    const d = isObj(draft) ? draft : {};
    const b = isObj(d.body) ? d.body : {};
    const s = isObj(state) ? state : {};
    return '<form class="rform" data-act="save" data-id="' + esc(clean(d.id)) + '"><h2>' + (d.id ? "Change the recipe" : "New recipe") + "</h2>" +
      (d.draft ? '<p class="cnote">This is a draft. Read it, change what you like, then save it. Nothing is saved yet.</p>' : "") +
      '<label for="r-title">Name</label><input id="r-title" name="title" maxlength="80" value="' + esc(clean(d.title)) + '" required>' +
      '<label for="r-overview">What it is for</label><textarea id="r-overview" name="overview" maxlength="600">' + esc(clean(b.overview)) + "</textarea>" +
      PARTS.map(([p, label]) => '<label for="r-' + p + '">' + esc(label) + ' (one line each)</label><textarea id="r-' + p + '" name="' + p + '">' + esc(fromLines(b[p])) + "</textarea>").join("") +
      '<label for="r-needs">What it asks you for when you start (one line each; write $1, $2 ... where the answers go)</label><textarea id="r-needs" name="needs">' + esc(fromLines(arr(b.needs).map(n => isObj(n) ? n.label : ""))) + "</textarea>" +
      '<label for="r-note">What changed (optional)</label><input id="r-note" name="note" maxlength="120">' +
      (s.error ? '<p class="cerr" role="alert">' + esc(clean(s.error)) + "</p>" : "") +
      '<div class="rbtns"><button type="submit" class="rgo">Save</button><button type="button" data-act="close">Cancel</button></div></form>';
  }

  function importHtml(state) {
    const s = isObj(state) ? state : {};
    return '<form class="rform" data-act="import"><h2>Read a recipe file</h2><label for="r-file">Paste the recipe file here (Markdown)</label><textarea id="r-file" name="markdown" maxlength="30000"></textarea>' +
      '<p class="cnote">Only a file you choose to paste. Sutra shows it as a draft first: nothing is saved until you press Save.</p>' + (s.error ? '<p class="cerr" role="alert">' + esc(clean(s.error)) + "</p>" : "") +
      '<div class="rbtns"><button type="submit" class="rgo">Read it</button><button type="button" data-act="close">Cancel</button></div></form>';
  }

  const RecipeView = {esc, ID, PARTS, toLines, fromLines, listHtml, detailHtml, startHtml, editHtml, importHtml, versionsHtml};
  if (typeof module === "object" && module !== null && module.exports) module.exports = RecipeView;
  else root.RecipeView = RecipeView;
})(globalThis);
