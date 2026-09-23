/* ── 21-library.js — the Library: the kinds a department is built from ──────
   Founder, 2026-09-23: "within each part there can be tabs -- about the
   things, and about all the premade lists of things", and "make sure to fit
   the design system of the Mac app".

   ONE renderer for all seven shelves. A shelf is a head, the app's own .tabs
   pair, and one pane:

     About        how one is made (the ways + what governs the making) and
                  what one is made of (the record's own parts)
     The list     the premade ones, with a tag filter above and the same tags
                  on every row

   Every control here is one the app already ships: .tabs .dptabs for the pair
   (panel.css:595, placed by the department card), .dptag for a tag, .btn for
   an action. The .lb rules in panel.css are LAYOUT ONLY -- this screen
   introduces no second control, so it inherits every theme, accent and
   dark-mode rule already written.

   Rows come from /api/library (library_api.py), which is a projection of the
   template repository, the routine records and the work-atom ledger. This
   file never decides what a row MEANS: the payload carries the row's state
   and its action, and the renderer draws them.

   Writes: none. `Use` files the same org.template ask the department card
   files, through the proposal path (LIB-6).
*/

/* ── state ───────────────────────────────────────────────────────────────
   Per shelf and per session, in memory: which tab is open, which tag is
   picked, which row is open (LIB-12). A view is not a record, so none of it
   is written to the browser's storage. */
const LIB_SHELVES = ["identity", "adaptation", "priority", "coordination", "audit",
                     "engines", "work-item"];
const LIB_STATE = { shelf: {}, tab: {}, tag: {}, open: {}, busy: {}, err: {} };

function libEsc(x){
  return (typeof esc === "function") ? esc(x)
    : String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}
function libRender(){ if (typeof render === "function") render(); }

/* screen id <-> shelf id. The rail rows carry data-screen, so the screen name
   is the shelf name with one prefix, and nothing else in the app has to know
   about the mapping. */
function libShelfOf(screen){
  const s = String(screen || "");
  return s.indexOf("lib-") === 0 ? s.slice(4) : "";
}
function libScreenOf(shelf){ return "lib-" + shelf; }

/* ── registration ────────────────────────────────────────────────────────
   Seven screens, one per shelf, all drawn by libScreenHtml. TITLES gets a row
   in the same breath: render() destructures TITLES[S.screen], so a SCREENS
   entry without one is a TypeError (the lesson 19-org2.js records). */
function libEnsureRegistered(){
  if (typeof SCREENS === "undefined" || typeof TITLES === "undefined") return;
  for (const sh of LIB_SHELVES){
    const id = libScreenOf(sh);
    if (SCREENS[id]) continue;
    SCREENS[id] = (function(shelf){ return function(){ return libScreenHtml(shelf); }; })(sh);
    TITLES[id] = ["Library", ""];
  }
}

/* ── data ────────────────────────────────────────────────────────────────
   One fetch per shelf, kept for the session. A shelf that cannot read its
   record says so on the screen and is not cached, so the next visit retries. */
function libLoad(shelf){
  if (!shelf || LIB_STATE.shelf[shelf] || LIB_STATE.busy[shelf]) return;
  LIB_STATE.busy[shelf] = true;
  const url = "/api/library/shelf/" + encodeURIComponent(shelf);
  const go = (typeof api === "function") ? api(url) : fetch(url).then(r => r.json());
  Promise.resolve(go).then(function(d){
    LIB_STATE.busy[shelf] = false;
    if (!d || d.error){ LIB_STATE.err[shelf] = (d && d.error) || "no answer"; }
    else { LIB_STATE.shelf[shelf] = d; LIB_STATE.err[shelf] = ""; }
    libRender();
  }).catch(function(e){
    LIB_STATE.busy[shelf] = false;
    LIB_STATE.err[shelf] = String((e && e.message) || e || "no answer");
    libRender();
  });
}

function libTab(shelf){ return LIB_STATE.tab[shelf] || "about"; }
function libTag(shelf){ return LIB_STATE.tag[shelf] || ""; }

/* ── the head ────────────────────────────────────────────────────────────*/
function libHeadHtml(head, shelf){
  const tabs = (head.tabs && head.tabs.length === 2) ? head.tabs : ["About", "Templates"];
  const on = libTab(shelf);
  return `
  <div class="lbhead"><h2>${libEsc(head.name || shelf)}</h2>
    ${head.kind ? `<span class="dptag">${libEsc(head.kind)}</span>` : ""}</div>
  ${head.line ? `<p class="lbsub">${libEsc(head.line)}</p>` : ""}
  <div class="lbtabrow lbtabs">
    <div class="tabs dptabs">
      <button type="button" data-libtab="about" data-libshelf="${libEsc(shelf)}"
        aria-pressed="${on === "about"}">${libEsc(tabs[0])}</button>
      <button type="button" data-libtab="list" data-libshelf="${libEsc(shelf)}"
        aria-pressed="${on === "list"}">${libEsc(tabs[1])}</button>
    </div>
    ${head.count_line ? `<span class="lbtabcount">${libEsc(head.count_line)}</span>` : ""}
  </div>`;
}

/* ── the About pane ──────────────────────────────────────────────────────*/
function libSecHtml(label){
  return `<div class="lbsec"><span class="dpk">${libEsc(label)}</span><hr></div>`;
}

function libWaysHtml(ways){
  if (!ways || !ways.length) return "";
  return `<div class="lbways">` + ways.map(w => `
    <div class="lbway"><h4>${libEsc(w.name)}</h4>
      <p>${libEsc(w.does)}</p>
      <p class="lbthen">${libEsc(w.lands)}</p></div>`).join("") + `</div>`;
}

function libSettingsHtml(rows){
  if (!rows || !rows.length) return "";
  return `<table class="lbset">
    <tr><th>Setting</th><th>What it decides</th><th>Now</th></tr>` +
    rows.map(s => `<tr><td>${libEsc(s.name)}</td><td>${libEsc(s.decides)}</td>
      <td>${libEsc(s.now)}</td></tr>`).join("") + `</table>`;
}

function libPartsHtml(parts){
  if (!parts || !parts.length) return "";
  return `<div class="lbpart">` + parts.map(p => `
    <div class="lbpname">${libEsc(p.name)}<span>${libEsc(p.caption || "")}</span></div>
    <div class="lbpval">${libEsc(p.says || "")}${
      p.example ? ` <em>&ldquo;${libEsc(String(p.example).slice(0, 220))}&rdquo;</em>` : ""}</div>`
  ).join("") + `</div>`;
}

function libAboutHtml(about){
  if (!about) return "";
  return libSecHtml("How one is made") + libWaysHtml(about.ways)
    + libSecHtml("What governs the making") + libSettingsHtml(about.settings)
    + libSecHtml("What one is made of") + libPartsHtml(about.parts)
    + (about.note ? `<p class="lbnote">${libEsc(about.note)}</p>` : "");
}

/* ── the list pane ───────────────────────────────────────────────────────
   The filter chips and the rows carry the SAME tags: what narrows the list is
   what labels a row (LIB-4). Filtering happens here because the payload is
   already in hand (LIB-5). */
function libFilterHtml(list, shelf){
  const tags = list.tags || [];
  if (!tags.length) return "";
  const on = libTag(shelf);
  const n = (list.rows || []).length;
  return `<div class="lbfilter"><span class="lbfl">${libEsc(list.tag_label || "Tags")}</span>
    <span class="dptag${on ? "" : " on"}" data-libtag="" data-libshelf="${libEsc(shelf)}"
      role="button" tabindex="0">All ${n}</span>` +
    tags.map(t => `<span class="dptag${on === t ? " on" : ""}" data-libtag="${libEsc(t)}"
      data-libshelf="${libEsc(shelf)}" role="button" tabindex="0">${libEsc(t)}</span>`).join("")
    + `</div>`;
}

function libRowsOf(list, shelf){
  const on = libTag(shelf);
  const rows = list.rows || [];
  return on ? rows.filter(r => (r.tags || []).indexOf(on) >= 0) : rows;
}

function libOpenHtml(shelf, row){
  const d = LIB_STATE.open[shelf];
  if (!d || d.id !== row.id) return "";
  if (d.loading) return `<div class="lbopen"><h5>Opening</h5></div>`;
  const keeps = d.keeps || [], adds = d.adds || [], where = d.where || [];
  return `<div class="lbopen">
    ${(keeps.length || adds.length) ? `<h5>What it always does</h5><ul>
      ${keeps.length ? `<li>The ${keeps.length} it keeps from ${libEsc(d.parent || "the one above")}, unchanged.</li>` : ""}
      ${adds.map(a => `<li><b>adds</b> ${libEsc(a)}</li>`).join("")}
    </ul>` : ""}
    ${where.length ? `<h5>Where it is in use</h5><ul>${
      where.map(w => `<li>${libEsc(w)}</li>`).join("")}</ul>` : ""}
    ${(!keeps.length && !adds.length && !where.length)
      ? `<h5>Nothing more on record</h5>` : ""}
  </div>`;
}

function libListHtml(list, shelf){
  if (!list) return "";
  const rows = libRowsOf(list, shelf);
  if (!rows.length){
    return libFilterHtml(list, shelf) + `<p class="lbnote">${
      (list.rows || []).length ? "No row carries that tag." : "Nothing on this shelf yet."}</p>`;
  }
  return libFilterHtml(list, shelf) + `<div class="lbmade">` + rows.map(r => {
    const dead = r.state === "to-build";
    const open = LIB_STATE.open[shelf] && LIB_STATE.open[shelf].id === r.id;
    return `<div class="lbrow${dead ? " tobuild" : ""}${open ? " on" : ""}"
        data-librow="${libEsc(r.id)}" data-libshelf="${libEsc(shelf)}">
      <b>${libEsc(r.name)}${r.sub ? `<span>${libEsc(r.sub)}</span>` : ""}</b>
      <span class="lbuse">${libEsc(r.use || "")}</span>
      <span class="lbtags">${(r.tags || []).map(t =>
        `<span class="dptag">${libEsc(t)}</span>`).join("")}</span>
      <span class="lbfloor">${libEsc(r.right || "")}</span>
      <button class="btn${r.state === "in-use" ? " dpstamp" : ""}" type="button"
        data-libuse="${libEsc(r.id)}" data-libshelf="${libEsc(shelf)}"
        ${dead ? "disabled" : ""}>${libEsc(r.action || "Use")}</button>
    </div>` + libOpenHtml(shelf, r);
  }).join("") + `</div>`
    + (list.note ? `<p class="lbnote">${libEsc(list.note)}</p>` : "");
}

/* ── the screen ──────────────────────────────────────────────────────────*/
function libScreenHtml(shelf){
  libLoad(shelf);
  const d = LIB_STATE.shelf[shelf];
  if (LIB_STATE.err[shelf]){
    return `<div class="lbpage"><div class="lbhead"><h2>${libEsc(shelf)}</h2></div>
      <p class="lbsub">This shelf cannot read its record: ${libEsc(LIB_STATE.err[shelf])}</p></div>`;
  }
  if (!d) return `<div class="lbpage"><p class="lbsub">Reading the shelf…</p></div>`;
  const pane = libTab(shelf) === "list"
    ? libListHtml(d.list, shelf) : libAboutHtml(d.about);
  return `<div class="lbpage">${libHeadHtml(d.head || {}, shelf)}
    <div class="lbpane">${pane}</div></div>`;
}

/* ── opening a row ───────────────────────────────────────────────────────
   A second read, because what a row ADDS to its parent is computed from two
   records and belongs on the server (LLD, narrowing). */
function libOpenRow(shelf, id){
  const cur = LIB_STATE.open[shelf];
  if (cur && cur.id === id){ LIB_STATE.open[shelf] = null; libRender(); return; }
  LIB_STATE.open[shelf] = { id: id, loading: true };
  libRender();
  const url = "/api/library/shelf/" + encodeURIComponent(shelf)
    + "/item/" + encodeURIComponent(id);
  const go = (typeof api === "function") ? api(url) : fetch(url).then(r => r.json());
  Promise.resolve(go).then(function(d){
    LIB_STATE.open[shelf] = Object.assign({ id: id }, d || {}, { loading: false });
    libRender();
  }).catch(function(){
    LIB_STATE.open[shelf] = { id: id, loading: false, error: "could not open" };
    libRender();
  });
}

/* ── using one ───────────────────────────────────────────────────────────
   The ONE write, and it is not a write here: it files the same org.template
   ask the department card files, and the owner stamps it. A shelf that is not
   a function has nothing to pick, so its action opens the thing instead. */
function libUse(shelf, id){
  if (LIB_SHELVES.indexOf(shelf) < 0) return;
  const isFunction = ["identity", "adaptation", "priority", "coordination", "audit"]
    .indexOf(shelf) >= 0;
  if (!isFunction){
    if (typeof toast === "function") toast("Open it from the department that runs it.");
    return;
  }
  const ref = (typeof dpRef === "function" && dpRef())
    || (typeof S !== "undefined" && S.ui && S.ui.deptRef) || "";
  if (!ref){
    if (typeof toast === "function")
      toast("Open a department first: a template is picked for one department.");
    return;
  }
  const body = { kind: "org.template", args: { ref: ref, function: shelf, template: id } };
  const go = (typeof api === "function")
    ? api("/api/org2/request", { method: "POST", body: JSON.stringify(body) })
    : fetch("/api/org2/request", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(r => r.json());
  Promise.resolve(go).then(function(d){
    if (typeof toast === "function")
      toast(d && d.error ? String(d.error) : "Filed as an ask for you to stamp.");
  }).catch(function(e){
    if (typeof toast === "function") toast(String((e && e.message) || e));
  });
}

/* ── clicks ──────────────────────────────────────────────────────────────
   One delegated listener on the app, mounted the way 10-activity.js and
   17-agents.js self-mount, so the tail's boot() stays the final statement. */
function libWire(){
  if (typeof document === "undefined" || !document.addEventListener) return;
  document.addEventListener("click", function(e){
    const t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    const tab = t.closest("[data-libtab]");
    if (tab){
      LIB_STATE.tab[tab.getAttribute("data-libshelf")] = tab.getAttribute("data-libtab");
      libRender(); return;
    }
    const tag = t.closest("[data-libtag]");
    if (tag){
      const sh = tag.getAttribute("data-libshelf");
      const v = tag.getAttribute("data-libtag");
      LIB_STATE.tag[sh] = (LIB_STATE.tag[sh] === v) ? "" : v;
      libRender(); return;
    }
    const use = t.closest("[data-libuse]");
    if (use){
      if (use.disabled) return;
      libUse(use.getAttribute("data-libshelf"), use.getAttribute("data-libuse"));
      return;
    }
    const row = t.closest("[data-librow]");
    if (row){
      libOpenRow(row.getAttribute("data-libshelf"), row.getAttribute("data-librow"));
    }
  });
}

libEnsureRegistered();
libWire();

if (typeof module !== "undefined" && module.exports){
  module.exports = { LIB_SHELVES, LIB_STATE, libShelfOf, libScreenOf, libHeadHtml,
                     libAboutHtml, libListHtml, libScreenHtml, libRowsOf, libTab };
}
