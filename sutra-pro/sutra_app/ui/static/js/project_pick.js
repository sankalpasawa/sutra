/* The start heading's project picker (named projects, R1.8 to R1.10). One classic script, one global: ProjectPick.

   A team page reads "What should we make in <Project>?"; the project name, underlined (no box, as in Codex), opens the list of projects
   (picking another one opens its page) and "+ New project…" (the Create project box). Attention reads the same, starting on the last project
   picked, else the first one. There is no "Let Sutra choose" (the owner's call, 23 Nov): only with no project at all is the heading plain
   "What should we make?", and then a prompt goes to the org chat.

   heading(projects, pick, opts), menuHtml(projects, pick, opts), pickOf(projects, pick), refusal(status, name) are pure (the node tests);
   mount(el, {projects, pick, attention, onPick}) draws the heading into `el` and opens the list under it. `onPick(id)` gets a project id
   or "+new" for New project. */
(function (root) {
  "use strict";

  const NEW = "+new";
  const FILES = "+files";                  // "Project files and memory" (D451): opens the panel of the picked project
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const clean = v => (typeof v === "string" ? v.replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim() : "");
  const list = projects => (Array.isArray(projects) ? projects : []).filter(p => isObj(p) && clean(p.id));

  // The pick as shown: the picked project while it is in the list, else the first project (deleted since, or never picked); "" with none.
  function pickOf(projects, pick) {
    const id = clean(pick);
    const all = list(projects);
    return id && all.some(p => p.id === id) ? id : (all[0] ? all[0].id : "");
  }

  function heading(projects, pick, opts) {
    const id = pickOf(projects, pick);
    const found = list(projects).find(p => p.id === id);
    if (found) {
      return 'What should we make in <button type="button" class="pp-name" aria-haspopup="menu" aria-expanded="false">' + esc(clean(found.name) || found.id) + "</button>?";
    }
    return "What should we make?";
  }

  function menuHtml(projects, pick, opts) {
    const o = isObj(opts) ? opts : {};
    const id = pickOf(projects, pick);
    const item = (value, label, on) => '<button type="button" class="pp-item" role="menuitemradio" aria-checked="' + String(on) + '" data-pp="' + esc(value) + '">' + label + "</button>";
    return '<div class="pp-menu" role="menu" aria-label="Where this goes">' +
      list(projects).map(p => item(p.id, esc(clean(p.name) || p.id), p.id === id)).join("") +
      (id ? '<button type="button" class="pp-item pp-files" role="menuitem" data-pp="' + FILES + '">Project files and memory</button>' : "") +
      '<button type="button" class="pp-item pp-new" role="menuitem" data-pp="' + NEW + '">+ New project&hellip;</button></div>';
  }

  // A send to a picked project that the server refused, in plain words ("" when the status is not one of these two).
  function refusal(status, name) {
    if (status === 409) return clean(name) + " is working. Wait for it or stop it.";
    if (status === 403) return "This project was deleted.";
    return "";
  }

  /* ---------------------------------------------------------------- the heading on the page */
  function mount(el, options) {
    if (!el || !el.ownerDocument) return null;
    const doc = el.ownerDocument;
    let state = Object.assign({projects: [], pick: "", attention: false, onPick: null}, isObj(options) ? options : {});
    let menu = null;

    function close(focusBack) {
      if (!menu) return;
      if (menu.parentNode) menu.parentNode.removeChild(menu);
      menu = null;
      const b = el.querySelector(".pp-name");
      if (b) { b.setAttribute("aria-expanded", "false"); if (focusBack && b.focus) b.focus(); }
    }
    function draw() {
      close(false);
      el.innerHTML = heading(state.projects, state.pick, state);
      el.classList.add("pp-head");
    }
    function openMenu() {
      const b = el.querySelector(".pp-name");
      if (!b) return;
      menu = doc.createElement("div");
      menu.className = "pp-wrap";
      menu.innerHTML = menuHtml(state.projects, state.pick, state);
      el.appendChild(menu);
      b.setAttribute("aria-expanded", "true");
      const on = menu.querySelector('[aria-checked="true"]') || menu.querySelector("button");
      if (on && on.focus) on.focus();
    }
    el.addEventListener("click", e => {
      const b = e.target && e.target.closest ? e.target.closest("button") : null;
      if (!b) return;
      if (b.classList.contains("pp-name")) { e.preventDefault(); if (menu) close(true); else openMenu(); return; }
      if (b.dataset && "pp" in b.dataset) {
        e.preventDefault();
        const value = b.dataset.pp;
        close(true);
        if (typeof state.onPick === "function") state.onPick(value);
      }
    });
    el.addEventListener("keydown", e => {
      if (!menu) return;
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const items = Array.from(menu.querySelectorAll("button"));
      const at = items.indexOf(doc.activeElement);
      const next = items[(at + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length];
      if (next) { e.preventDefault(); next.focus(); }
    });
    doc.addEventListener("click", e => { if (menu && !el.contains(e.target)) close(false); });
    draw();
    return {
      set(next) { state = Object.assign(state, isObj(next) ? next : {}); draw(); },
      pick: () => pickOf(state.projects, state.pick),
      close: () => close(false),
    };
  }

  const ProjectPick = {heading, menuHtml, pickOf, refusal, mount, NEW, FILES};
  if (typeof module === "object" && module.exports) module.exports = ProjectPick;
  else root.ProjectPick = ProjectPick;
})(globalThis);
