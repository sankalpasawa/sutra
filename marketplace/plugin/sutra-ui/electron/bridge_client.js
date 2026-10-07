/* window.sutra for a browser tab served by the browser-mode gateway.
 *
 * Same shape as preload.js, so the panel runs unchanged: every verb resolves to
 * what the matching ipcRenderer.invoke() resolves to. The transport is a
 * same-origin POST to /__sutra/bridge/<verb>; the session cookie rides along
 * automatically and is HttpOnly, so this script never sees it.
 *
 * Served by browser_mode.js with the VERBS placeholder below replaced by the
 * verbs the running app actually offers. Loaded first in every page, before the panel's
 * own scripts, because the panel reads window.sutra at parse time.
 */
(function () {
  "use strict";
  if (window.sutra) return;              // an Electron preload already provided it
  var VERBS = __SUTRA_BRIDGE_VERBS__;

  function call(verb, args) {
    return fetch("/__sutra/bridge/" + verb, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "x-sutra-bridge": "1" },
      body: JSON.stringify({ args: args }),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.ok) return j.result;
        return { ok: false, error: (j && j.error) || ("the app refused (" + r.status + ")") };
      });
    }, function () {
      return { ok: false, error: "Sutra is not running. Open it again from the app." };
    });
  }

  var api = { desktop: true, browser: true };
  VERBS.forEach(function (verb) {
    api[verb] = function () { return call(verb, Array.prototype.slice.call(arguments, 0, 4)); };
  });

  /* The preload's one push channel. One EventSource, opened on first use. */
  var source = null;
  api.onUpdateStaged = function (cb) {
    if (!source) source = new EventSource("/__sutra/events");
    source.addEventListener("sutra:update-staged", function (e) {
      try { cb(JSON.parse(e.data)); } catch (err) {}
    });
  };

  Object.freeze(api);
  Object.defineProperty(window, "sutra", { value: api, writable: false, configurable: false });
})();
