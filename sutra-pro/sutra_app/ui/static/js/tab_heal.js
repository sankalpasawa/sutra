/* tab_heal.js - a page that outlives a restart (gap package welcome-settings, item 5; the old app's "a dead panel token must not silently eat a click").

   The launch token is random per launch and never on disk (D81), so a server restart kills the token of every tab that is still open: the live stream
   reconnects and refetches (reads need no token), the page looks healthy, and every write is refused with 401 `bad_token`. This file lets the page get
   the fresh token the only way a page ever gets one, from its own boot block, and repeat the one write that failed. No new server route: the token still
   reaches a page only through the boot block (D81).

     parseBoot(html, expect) -> {token, page, dept} | null   reads <script type="application/json" id="sutra-boot"> of an HTML text. Accepts only a block of
                                         the same page kind and the same team as `expect` ({page, dept}), a token of at least 16 characters, and a text of at
                                         most MAX_CHARS; anything else is null (a page that is not this page never hands over its token)
     heal(ctx, fetchFn, options) -> Promise<boolean>   GET <this page's own path and query> (cache no-store, same origin, through `fetchFn`, the page's
                                         ORIGINAL fetch so the token is never added to it) and put the new token in ctx.boot.token. True when the token changed.
                                         False when it could not: the old token is left as it was, so the caller's existing "opened without its access token"
                                         banner stays. One heal at a time (callers that arrive while one runs share it) and at most one in 60 s, so a server
                                         that keeps refusing cannot make a loop. `options` ({now, location}) are for a test.
     isDead(error) -> boolean            an ApiError that is the 401 `bad_token`
     reset()                             forget the guard (a test)

   sutra_ctx.js calls this lazily (send() and the fetch wrapper repeat a refused write once); without this file the page behaves as before.
   A classic script with ONE global, TabHeal; in node it is module.exports. */
(function (root) {
  "use strict";

  const MAX_CHARS = 2 * 1024 * 1024;
  const GUARD_MS = 60 * 1000;
  const MIN_TOKEN = 16;                                  // boot.py TOKEN_MIN_LENGTH
  const BLOCK = /<script\b[^>]*\bid\s*=\s*["']sutra-boot["'][^>]*>([\s\S]*?)<\/script\s*>/i;
  const ROOT_RELATIVE = /^\/(?![\/\\])[^\u0000-\u001f]*$/;       // one leading slash, never "//host" or "/\host" (the same rule as sutra_ctx.js)
  const state = {last: 0, inflight: null};

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);

  function parseBoot(html, expect) {
    if (typeof html !== "string" || html.length > MAX_CHARS || !isObj(expect)) return null;
    const found = BLOCK.exec(html);
    if (found === null) return null;
    let boot;
    try {
      boot = JSON.parse(found[1]);
    } catch (e) {
      return null;
    }
    if (!isObj(boot) || typeof boot.token !== "string" || boot.token.length < MIN_TOKEN) return null;
    if (typeof expect.page !== "string" || boot.page !== expect.page) return null;
    if ((typeof boot.dept === "string" ? boot.dept : "") !== (typeof expect.dept === "string" ? expect.dept : "")) return null;
    return {token: boot.token, page: boot.page, dept: typeof boot.dept === "string" ? boot.dept : ""};
  }

  const isDead = error => isObj(error) && error.status === 401 && error.code === "bad_token";

  function pagePath(loc) {
    const path = isObj(loc) && typeof loc.pathname === "string" ? loc.pathname : "";
    const query = isObj(loc) && typeof loc.search === "string" ? loc.search : "";
    const url = path + query;
    return ROOT_RELATIVE.test(url) ? url : "";
  }

  function heal(ctx, fetchFn, options) {
    const o = isObj(options) ? options : {};
    if (state.inflight !== null) return state.inflight;
    const now = typeof o.now === "function" ? o.now() : Date.now();
    if (state.last !== 0 && now - state.last < GUARD_MS) return Promise.resolve(false);
    const url = pagePath(o.location || root.location);
    if (!isObj(ctx) || !isObj(ctx.boot) || typeof fetchFn !== "function" || url === "") return Promise.resolve(false);
    state.last = now;
    const run = (async () => {
      try {
        const res = await fetchFn(url, {method: "GET", cache: "no-store", credentials: "same-origin", headers: {Accept: "text/html"}});
        if (!res || res.status !== 200) return false;
        const html = await res.text();
        const parsed = parseBoot(html, {page: ctx.boot.page, dept: ctx.boot.dept});
        if (parsed === null || parsed.token === ctx.boot.token) return false;       // the same token again is no cure: the caller must not retry
        ctx.boot.token = parsed.token;
        return true;
      } catch (e) {
        return false;
      }
    })();
    state.inflight = run;                                              // set after the call, cleared when it settles (run never rejects)
    run.then(() => { if (state.inflight === run) state.inflight = null; });
    return run;
  }

  function reset() {
    state.last = 0;
    state.inflight = null;
  }

  const TabHeal = {parseBoot, heal, isDead, reset, GUARD_MS, MAX_CHARS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = TabHeal;
  else root.TabHeal = TabHeal;
})(globalThis);
