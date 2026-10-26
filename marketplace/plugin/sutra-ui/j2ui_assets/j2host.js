/* j2host.js -- the one script the Sutra app adds around the J2 prototype's page (scripts/sync_j2_ui.py, substitution S2).
   The page is served from the app's own origin, whose guard wants the panel token on every write. This wraps fetch: a
   call that is not a GET or HEAD carries X-Sutra-Panel, and on a 403 the token is read again once and the call retried
   (the rule of apiPost in static/js/01-state.js). Nothing else. */
(function () {
  var plain = window.fetch.bind(window), token = "";
  function read(again) {
    if (token && !again) return Promise.resolve(token);
    return plain("/api/panel-token", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (j) { token = (j && j.token) || token; return token; })
      .catch(function () { return token; });
  }
  window.fetch = function (input, init) {
    var req = input instanceof Request ? input : null;
    var method = String((init && init.method) || (req && req.method) || "GET").toUpperCase();
    if (method === "GET" || method === "HEAD") return plain(input, init);
    function send(t) {
      var h = new Headers((init && init.headers) || (req && req.headers) || {});
      h.set("X-Sutra-Panel", t);
      return plain(req ? req.clone() : input, Object.assign({}, init, { headers: h }));
    }
    return read(false).then(send).then(function (r) { return r.status === 403 ? read(true).then(send) : r; });
  };
})();
