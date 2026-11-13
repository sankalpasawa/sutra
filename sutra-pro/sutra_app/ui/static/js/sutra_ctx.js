/* sutra_ctx.js - the context every Sutra page shares (work package UI-3; docs/design/ui.md sections 4.2, 5 E2, 7 and 8).

   A classic script, loaded first in <head>, before J2's page script. It exposes ONE global, SutraCtx, and nothing else:
   J2's page script declares many top-level names (esc, paint, $, md, ...) and a second declaration of one of them is a
   SyntaxError, so every helper below lives inside this function.

   Everything it reads from the page is guarded or inside a try, so the file also loads in J2's stub DOM (no location.pathname,
   no document.dispatchEvent, no CustomEvent, no Headers, no window) and in node (module.exports). Globals are read when they
   are used, never captured at load, so a page or a test can swap them. */
(function (root) {
  "use strict";

  const TOKEN_HEADER = "X-Sutra-Token";
  // The generic URL-id rule of /d/{dept}/ (D72, S3-web-13); the same text as URL_ID_PATTERN in sutra_app/ui/boot.py.
  const ID_RULE = /^[A-Za-z0-9_.:-]{1,120}$/;
  const PATH_DEPT = /^\/d\/([A-Za-z0-9_.:-]+)(?:\/|$)/;      // the length is checked by isId
  // A URL that stays on this origin: one leading slash, then not "/" or "\" (browsers read "/\host" as "//host"), and no
  // control character (the URL parser drops tabs and newlines, so "/<tab>/host" would become "//host" too). The token and
  // `dept` are only ever added to such a URL.
  const ROOT_RELATIVE = /^\/(?![\/\\])[^\u0000-\u001f]*$/;

  const URL_PARTS = /^([^?#]*)(?:\?([^#]*))?(#[\s\S]*)?$/;      // path, query without its ?, fragment with its #

  const isId = v => typeof v === "string" && v !== "." && v !== ".." && ID_RULE.test(v);
  const isRootRelative = v => typeof v === "string" && ROOT_RELATIVE.test(v);

  /* ---------------------------------------------------------------- J2's data routes (j2_server.py) */
  // The 33 exact pathnames of J2's page (32 under /api/, and the studio's /view) and the five prefixes (S3-web-15; J2 sync 4, D140). Ten are
  // newer than the first port: /api/runlist and /api/changes (patch P13 until sync 4, J2's own routes since), /api/plan-map, /api/catalog,
  // /api/artifacts/groups, /api/activity, /api/ask and, with the studio, /api/record, /api/settings, /view and the /doc/ prefix. The
  // orchestrator's own routes (/api/runs/{run_id}, /api/chart, /api/graph, /api/schemas/..., /api/tasks, /api/engine/settings, ...) match none
  // of them, so they never get `dept`.
  const J2_EXACT = ["/api/state", "/api/runs", "/api/runlist", "/api/changes", "/api/call", "/api/preview", "/api/docs", "/api/map",
    "/api/plan", "/api/plan-map", "/api/library", "/api/catalog", "/api/run-templates", "/api/artifacts", "/api/artifacts/tree",
    "/api/artifacts/groups", "/api/artifact", "/api/agent", "/api/activity", "/api/record", "/api/code", "/api/story", "/api/board",
    "/api/audits", "/api/refs", "/api/timing", "/api/say", "/api/ask", "/api/output", "/api/settings", "/api/reset", "/api/playbooks/clear",
    "/api/lessons/clear", "/view"];
  const J2_PREFIXES = ["/api/library/", "/site/", "/file/", "/shot/", "/doc/"];
  const J2_EXACT_SET = new Set(J2_EXACT);
  const J2_PATHS = Object.freeze({
    exact: Object.freeze(J2_EXACT.slice()),
    prefixes: Object.freeze(J2_PREFIXES.slice()),
    // `pathname` is the path alone, without a query or fragment.
    matches: pathname => typeof pathname === "string" && (J2_EXACT_SET.has(pathname) || J2_PREFIXES.some(p => pathname.startsWith(p))),
  });

  /* ---------------------------------------------------------------- errors */
  const DEFAULT_MESSAGES = new Map([
    ["bad_payload", "The app sent an answer that could not be read."],
    ["network", "The app is not responding."],
    ["bad_path", "An API path starts with a single slash."],
  ]);

  // What every api call rejects with: {status, code, message, details}. `status` is 0 when no answer came. A server error
  // fills it from the envelope {error: {code, message, details}} (S3-web-15); `new ApiError("bad_payload")` is the short
  // form the views use for an answer of the wrong shape (X5).
  class ApiError extends Error {
    constructor(init) {
      const o = typeof init === "string" ? {code: init} : (init !== null && typeof init === "object" ? init : {});
      const code = typeof o.code === "string" && o.code !== "" ? o.code : "error";
      super(typeof o.message === "string" && o.message !== "" ? o.message : (DEFAULT_MESSAGES.get(code) || code));
      this.name = "ApiError";
      this.status = Number.isInteger(o.status) ? o.status : 0;
      this.code = code;
      this.details = o.details !== null && typeof o.details === "object" ? o.details : {};
    }
  }

  /* ---------------------------------------------------------------- boot and department */
  // The JSON block the server writes at the boot marker (sutra_app/ui/boot.py). Anything else gives {}: no document, no block,
  // a stub element (its text is "", undefined or a function), bad JSON, or JSON that is not an object. Every one of those
  // throws below, and the catch answers.
  function readBoot() {
    try {
      const value = JSON.parse(root.document.getElementById("sutra-boot").textContent);
      return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch (e) {
      return {};
    }
  }

  function deptFromPath() {
    const m = PATH_DEPT.exec(root.location?.pathname);        // no location, or none with a pathname (J2's stub): no match
    return m && isId(m[1]) ? m[1] : "";
  }

  // Home belongs to no team. A team page takes the team from the server's block, else from its own path.
  function pickDept(boot) {
    if (boot.page === "home") return "";
    return isId(boot.dept) ? boot.dept : deptFromPath();
  }

  const boot = readBoot();
  const ctx = {boot: boot, dept: pickDept(boot), currentTab: ""};
  // The team page's own address and its template library's (D141): /d/<id>/ and /d/<id>/library. The id rule (isId) keeps an id safe to
  // write into a path as it is. J2's stub DOM and Home have no team, so they get J2's own "/" and "/library": the render harness then
  // behaves as J2's page does.
  ctx.pagePath = ctx.dept ? "/d/" + ctx.dept + "/" : "/";
  ctx.libraryPath = ctx.pagePath + "library";
  const state = {origFetch: null};     // window.fetch before installFetch(window) wrapped it; `api` calls this one
  const tokenOf = () => (typeof ctx.boot.token === "string" ? ctx.boot.token : "");

  /* ---------------------------------------------------------------- small helpers */
  const ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ESCAPES[c]);
  }

  function cssEscape(s) {
    return typeof root.CSS?.escape === "function" ? root.CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&");
  }

  // J2's paint: leave a pane alone when its HTML is unchanged, and when it changes reopen the <details data-key> the viewer
  // had open. Returns whether the DOM was touched. No element: nothing to paint.
  function paint(el, html) {
    if (!el || el.__html === html) return false;
    const open = new Set(Array.from(el.querySelectorAll("details[open][data-key]"), d => d.dataset.key));
    el.innerHTML = html;
    el.__html = html;
    open.forEach(key => {
      const d = el.querySelector('details[data-key="' + cssEscape(key) + '"]');
      if (d) d.open = true;
    });
    return true;
  }

  // The run in ?run= (J2's viewRun); "" is the live run.
  function run() {
    try {
      return new root.URLSearchParams(root.location.search).get("run") || "";
    } catch (e) {
      return "";                      // no location, or no URLSearchParams
    }
  }

  // Whether the page on screen is the team's template library (J2 asked `location.pathname === "/library"`). A trailing slash does not matter,
  // nor does a percent-encoded character of the id; no location (J2's stub DOM, node) is never the library.
  function onLibrary() {
    const pathname = root.location?.pathname;
    return typeof pathname === "string" && safeDecode(pathname).replace(/\/$/, "") === ctx.libraryPath;
  }

  // Set the current tab first (the department page reads it when it starts, because J2 shows a ?tab= pane at parse time,
  // before the module scripts run), then tell the page with `sutra:tab` {detail: {name}} when the DOM can. J2's stub DOM
  // has no dispatchEvent (the call throws and the answer is false) and no CustomEvent, and nothing a listener or the DOM does
  // may break J2's showTab. True when dispatched.
  function tab(name) {
    ctx.currentTab = typeof name === "string" ? name : String(name ?? "");
    if (typeof root.CustomEvent !== "function") return false;
    const event = new root.CustomEvent("sutra:tab", {detail: {name: ctx.currentTab}, bubbles: true});
    try {
      root.document.dispatchEvent(event);
      return true;
    } catch (e) {
      return false;
    }
  }

  /* ---------------------------------------------------------------- the department on J2's calls */
  function safeDecode(s) {
    try {
      return decodeURIComponent(s);
    } catch (e) {
      return s;
    }
  }

  function hasParam(query, name) {
    return query.split("&").some(part => {
      const eq = part.indexOf("=");
      return safeDecode(eq < 0 ? part : part.slice(0, eq)) === name;
    });
  }

  // `dept=<id>` appended to a root-relative URL whose path is one of J2's, unless it already carries one. Everything else
  // (other paths, /ui/..., absolute URLs, no department) comes back as it was. Only appended: the query is not re-encoded.
  function withDept(url) {
    if (!ctx.dept || !isRootRelative(url)) return url;
    const [, path, query = "", fragment = ""] = URL_PARTS.exec(url);
    if (!J2_PATHS.matches(path) || hasParam(query, "dept")) return url;
    const glue = query === "" || query.endsWith("&") ? "" : "&";
    return path + "?" + query + glue + "dept=" + encodeURIComponent(ctx.dept) + fragment;
  }

  /* ---------------------------------------------------------------- the fetch wrapper for J2's own calls */
  function methodOf(init) {
    const m = init?.method;
    return typeof m === "string" && m !== "" ? m.toUpperCase() : "GET";
  }

  const needsToken = method => method !== "GET" && method !== "HEAD" && method !== "OPTIONS";

  // A server restart kills the launch token of a page that stays open (tab_heal.js, gap package welcome-settings): a write refused with 401 `bad_token` gets
  // the fresh token from the page's own boot block and is repeated ONCE. tab_heal.js is looked up when needed (a global in the page, a require in node); without
  // it, or when the heal fails, the refusal is passed on as before and the page shows its "opened without its access token" banner.
  function healer() {
    if (root.TabHeal) return root.TabHeal;
    if (typeof module === "object" && module !== null && module.exports && typeof require === "function") {
      try { return require("./tab_heal.js"); } catch (e) { return null; }
    }
    return null;
  }
  async function healToken() {
    const h = healer();
    if (!h) return false;
    try { return (await h.heal(ctx, state.origFetch || root.fetch)) === true; } catch (e) { return false; }
  }

  // A copy of `init` (an object: it names the write method) whose headers carry the token; one the caller set is kept.
  // Headers as a Headers object, a list of pairs or a plain object; `init` itself is not changed.
  function withToken(init, token) {
    const lower = TOKEN_HEADER.toLowerCase();
    const h = init.headers;
    let headers;
    if (typeof root.Headers === "function" && h instanceof root.Headers) {
      headers = new root.Headers(h);
      if (!headers.has(TOKEN_HEADER)) headers.set(TOKEN_HEADER, token);
    } else if (Array.isArray(h)) {
      headers = h.slice();
      if (!h.some(pair => Array.isArray(pair) && String(pair[0]).toLowerCase() === lower)) headers.push([TOKEN_HEADER, token]);
    } else {
      headers = h !== null && typeof h === "object" ? Object.assign({}, h) : {};
      if (!Object.keys(headers).some(k => k.toLowerCase() === lower)) headers[TOKEN_HEADER] = token;
    }
    return Object.assign({}, init, {headers: headers});
  }

  // Wrap win.fetch once. A root-relative URL gets `dept` when it is one of J2's paths (withDept) and, with a method other
  // than GET, HEAD or OPTIONS, X-Sutra-Token (D81), whatever its path. A Request object and an absolute URL pass through
  // untouched, so the token never leaves this origin. False when there is nothing to wrap or it is wrapped already.
  function installFetch(win) {
    if (!win || typeof win.fetch !== "function" || win.fetch.sutraWrapped === true) return false;
    const original = win.fetch;
    const wrapped = function sutraFetch(input, init) {
      const token = tokenOf();
      const signed = token !== "" && isRootRelative(input) && needsToken(methodOf(init));
      const first = original.call(win, withDept(input), signed ? withToken(init, token) : init);
      // J2's own writes heal too: a 401 `bad_token` (read from a clone, the caller still gets its response) is repeated once with the fresh token, and only
      // when the body can be sent again (none, or a string)
      if (!signed || !(init.body === undefined || typeof init.body === "string")) return first;
      return first.then(async res => {
        if (!res || res.status !== 401 || typeof res.clone !== "function") return res;
        let dead = false;
        try { dead = (await res.clone().json())?.error?.code === "bad_token"; } catch (e) { dead = false; }
        if (!dead || !(await healToken())) return res;
        return original.call(win, withDept(input), withToken(init, tokenOf()));
      });
    };
    wrapped.sutraWrapped = true;
    if (win === root) state.origFetch = original;
    win.fetch = wrapped;
    return true;
  }

  /* ---------------------------------------------------------------- api: the orchestrator's routes */
  function queryString(query) {
    if (query === undefined || query === null) return "";
    if (typeof query === "string") return query.replace(/^\?/, "");
    return Object.keys(query)
      .filter(k => query[k] !== undefined && query[k] !== null)
      .map(k => encodeURIComponent(k) + "=" + encodeURIComponent(String(query[k])))
      .join("&");
  }

  function buildUrl(path, query) {
    if (!isRootRelative(path)) throw new ApiError({code: "bad_path", details: {path: typeof path === "string" ? path : typeof path}});
    const qs = queryString(query);
    if (qs === "") return path;
    return path + (path.indexOf("?") < 0 ? "?" : (path.endsWith("?") || path.endsWith("&") ? "" : "&")) + qs;
  }

  // A server answer that is not an error is JSON, or empty (204). An error is the envelope {error: {code, message, details}};
  // anything else (J2's {error: "text"}, a FastAPI {detail: "text"}, a proxy page) becomes code http_<status>.
  // The one server sentence that is always reworded: a write refused with the dead launch token (401 `bad_token`) says "A valid X-Sutra-Token header is
  // required", which names a header the owner cannot act on. Every view prints `e.message` beside its field, so the ApiError itself says what to do.
  const NO_TOKEN = "This page was opened without its access token. Reload it from the app.";

  function failure(status, data) {
    const err = data?.error;
    if (typeof err?.code === "string" && err.code !== "") {
      const message = status === 401 && err.code === "bad_token" ? NO_TOKEN : err.message;
      return new ApiError({status: status, code: err.code, message: message, details: err.details});
    }
    const sentence = typeof err === "string" ? err : (typeof data?.detail === "string" ? data.detail : "");
    return new ApiError({status: status, code: "http_" + status, message: sentence || "The app answered " + status + "."});
  }

  // These calls never go through the wrapper above: they carry the token themselves and must never get `dept`.
  async function send(method, path, query, body, repeated) {
    const url = buildUrl(path, query);
    const init = {method: method, cache: "no-store", headers: {Accept: "application/json"}};
    if (needsToken(method)) {
      if (tokenOf() !== "") init.headers[TOKEN_HEADER] = tokenOf();
      if (body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body);
      }
    }
    let res;
    let text;
    try {
      res = await (state.origFetch || root.fetch)(url, init);
      text = await res.text();
    } catch (e) {
      throw new ApiError({status: 0, code: "network", details: {reason: String((e && e.message) || e)}});
    }
    const blank = text.trim() === "";
    let data = null;
    let readable = blank;
    if (!blank) {
      try {
        data = JSON.parse(text);
        readable = true;
      } catch (e) {
        readable = false;
      }
    }
    if (res.status >= 200 && res.status < 300) {
      if (!readable) throw new ApiError({status: res.status, code: "bad_payload"});
      return data;
    }
    const refused = failure(res.status, data);
    if (!repeated && needsToken(method) && refused.status === 401 && refused.code === "bad_token" && (await healToken())) return send(method, path, query, body, true);
    throw refused;
  }

  const api = {
    get: (path, query) => send("GET", path, query),
    post: (path, body) => send("POST", path, undefined, body),
    put: (path, body) => send("PUT", path, undefined, body),
    del: path => send("DELETE", path),
  };

  /* ---------------------------------------------------------------- the two preview iframes (E2) */
  // The page markup holds data-src, not src, so the frame never asks for /site/latest without a department. A frame that
  // already has a src (J2 assigned it first) is left alone.
  function fillFrames() {
    try {
      Array.from(root.document.querySelectorAll("iframe[data-src]")).forEach(frame => {
        const from = frame.getAttribute("data-src");
        if (from && !frame.getAttribute("src")) frame.setAttribute("src", withDept(from));
      });
    } catch (e) {
      /* no document to search (a stub, node), or a frame that cannot be read */
    }
  }

  Object.assign(ctx, {run: run, esc: esc, paint: paint, tab: tab, api: api, installFetch: installFetch, withDept: withDept,
    onLibrary: onLibrary, J2_PATHS: J2_PATHS, ApiError: ApiError});

  // A team page wraps J2's fetch calls; Home has none.
  if (boot.page === "dept" && typeof root.fetch === "function") installFetch(root);
  if (root.document?.readyState === "loading") root.document.addEventListener("DOMContentLoaded", fillFrames);
  else fillFrames();

  if (typeof module === "object" && module !== null && module.exports) module.exports = ctx;
  else root.SutraCtx = ctx;
})(globalThis);
