/* doc_frame.js - the team page's side of the document reader (D455).

   A Markdown file in Files is shown by the document reader (sutra_app/engine/doc_reader.py) in the page's sandboxed frame: an opaque
   origin that cannot read the page's Appearance setting, cannot download and cannot keep state across a reload. This script is the
   page's half of a small message protocol with it; every message carries `sutraDoc: 1`.

     frame -> page   {type: "ready", name}            the reader loaded: the page answers with the theme and the view mode kept for `name`
                     {type: "mode", mode, name}        Preview or Markdown was picked: kept for `name` while the page is open
                     {type: "download", href, file}    a Download menu item: the page downloads `href`, only an /api/artifact?... address
     page -> frame   {type: "theme", theme}            "light" | "dark", sent again whenever the page's data-theme changes (Light, Dark,
                                                       System), so the open file, its view mode and its scroll stay as they are
                     {type: "mode", mode}              the kept view mode

   Pure core (no DOM): DocFrame.theme(root), DocFrame.downloadHref(href), DocFrame.handle(state, msg) -> replies.
   Glue: DocFrame.install(root) on a page; result_view.js loads this file. A classic script with ONE global, DocFrame; in node it is
   module.exports. */
(function (root) {
  "use strict";

  const MODES = ["preview", "source"];

  // The page's theme as the reader takes it: the data-theme on <html> (j2_ui.html sets it from Light, Dark or System), light by default.
  function theme(rootDoc) {
    const t = rootDoc && rootDoc.documentElement && rootDoc.documentElement.dataset ? rootDoc.documentElement.dataset.theme : "";
    return t === "dark" ? "dark" : "light";
  }

  // Only the run's own files, as /api/artifact serves them (the same downloads Files already offers); anything else is refused.
  function downloadHref(href) {
    const s = typeof href === "string" ? href : "";
    if (!/^\/api\/artifact\?[^#\s]*$/.test(s)) return null;
    let q;
    try { q = new URLSearchParams(s.slice(s.indexOf("?") + 1)); } catch (e) { return null; }
    const name = q.get("name") || "";
    if (!name || name.split("/").includes("..") || !/\.(md|docx)$/i.test(name)) return null;
    return s;
  }

  // What the page answers to one message from a reader: a list of messages for that frame. `state.modes` keeps the view mode per file.
  function handle(state, msg, themeNow) {
    if (!msg || msg.sutraDoc !== 1 || typeof msg.type !== "string") return [];
    const name = typeof msg.name === "string" ? msg.name : "";
    if (msg.type === "ready") {
      const out = [{sutraDoc: 1, type: "theme", theme: themeNow}];
      const mode = name && state.modes[name];
      if (mode) out.push({sutraDoc: 1, type: "mode", mode});
      return out;
    }
    if (msg.type === "mode" && name && MODES.includes(msg.mode)) state.modes[name] = msg.mode;
    return [];
  }

  function frames(d) {
    return Array.from(d.querySelectorAll("iframe")).map(f => { try { return f.contentWindow; } catch (e) { return null; } }).filter(Boolean);
  }

  function install(win) {
    const d = win && win.document;
    if (!d || win.__docFrame) return false;
    win.__docFrame = true;
    const state = {modes: {}};
    const post = (w, m) => { try { w.postMessage(m, "*"); } catch (e) { /* a frame that went away */ } };
    win.addEventListener("message", e => {
      const msg = e.data;
      if (!msg || msg.sutraDoc !== 1 || !frames(d).includes(e.source)) return;      // only the page's own frames
      if (msg.type === "download") {
        const href = downloadHref(msg.href);
        if (!href) return;
        const a = d.createElement("a");
        a.href = href;
        a.download = String(msg.file || "").split("/").pop().replace(/[^\w.\- ]/g, "_") || "download";
        a.hidden = true;
        d.body.appendChild(a);
        a.click();
        a.remove();
        return;
      }
      handle(state, msg, theme(d)).forEach(m => post(e.source, m));
    });
    let last = theme(d);
    const tell = () => {
      const now = theme(d);
      if (now === last) return;
      last = now;
      frames(d).forEach(w => post(w, {sutraDoc: 1, type: "theme", theme: now}));
    };
    if (typeof win.MutationObserver === "function") new win.MutationObserver(tell).observe(d.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
    return true;
  }

  const DocFrame = {theme, downloadHref, handle, install};
  if (typeof module === "object" && module !== null && module.exports) module.exports = DocFrame;
  else { root.DocFrame = DocFrame; install(root); }
})(globalThis);
