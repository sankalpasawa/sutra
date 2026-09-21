#!/usr/bin/env node
/* test_panel_token_retry.js -- a dead panel token must not silently eat a click.
 *
 * THE BUG (founder dogfood, 2026-09-21). app.py mints PANEL_TOKEN at module
 * import, so every backend restart invalidates the token baked into an already
 * open page. _origin_guard then 403s every browser-shaped mutation. The heal --
 * refreshPanelToken(), written 2026-08-25 for exactly this -- existed, but was
 * wired only into 15-shadow-overlay.js and 16-shadow-home.js, each with its own
 * private wrapper. The SHARED apiPost/apiGet in 01-state.js just threw.
 *
 * What that cost: Settings -> Access and permissions. Clicking "Full access"
 * after a `python` restart 403'd, applyPermMode parked the message in
 * S.permError, and the only renderer of S.permError is the consent dialog --
 * which is skipped once consent is on file. Five clicks over two days, nothing
 * written, nothing said.
 *
 * So the retry belongs at the shared door, and these tests hold it there:
 * a caller must not have to remember to heal.
 *
 * Run: node test_panel_token_retry.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const SRC = fs.readFileSync(path.join(__dirname, "static", "js", "01-state.js"), "utf8");

/* Take the real transport block out of 01-state.js rather than restating it.
   A copy here would pass forever while the shipped file regressed. */
function transport(){
  const from = SRC.indexOf("async function _fail(");
  const anchor = SRC.indexOf("async function apiPost(");
  const end = SRC.indexOf("\n}", SRC.indexOf("return r.json();", anchor)) + 2;
  assert.ok(from > 0 && anchor > from && end > anchor,
            "could not slice the transport block out of 01-state.js");
  return 'const API = "";\n' + SRC.slice(from, end);
}

/* One sandbox per case. `calls` records every fetch the block makes, in order,
   with the token it actually sent -- which is the whole question. */
function harness(responses, tokenAfterRefresh){
  const calls = [];
  let served = 0;
  const box = {
    console,
    document: { querySelector: () => ({ content: "STALE-TOKEN" }) },
    async fetch(url, opts){
      opts = opts || {};
      const hdrs = opts.headers || {};
      if (String(url).indexOf("/api/panel-token") >= 0){
        calls.push({ url: String(url), kind: "refresh" });
        return { ok: tokenAfterRefresh !== null, status: tokenAfterRefresh === null ? 500 : 200,
                 json: async () => ({ token: tokenAfterRefresh }) };
      }
      calls.push({ url: String(url), kind: opts.method === "POST" ? "post" : "get",
                   token: hdrs["X-Sutra-Panel"] });
      const r = responses[Math.min(served++, responses.length - 1)];
      return { ok: r.status >= 200 && r.status < 300, status: r.status,
               json: async () => r.body || {} };
    },
  };
  vm.createContext(box);
  new vm.Script(transport(), { filename: "01-state.js#transport" }).runInContext(box);
  return { box, calls };
}

let failed = 0;
async function t(name, fn){
  try { await fn(); console.log("  ok  " + name); }
  catch (e){ failed++; console.log("FAIL  " + name + "\n      " + (e && e.message)); }
}

(async () => {
console.log("test_panel_token_retry.js");

await t("a POST that 403s is retried once, with the REFRESHED token", async () => {
  const h = harness([{ status: 403 }, { status: 200, body: { ok: true } }], "FRESH-TOKEN");
  const out = await h.box.apiPost("/api/settings", { permission_mode: "bypassPermissions" });
  assert.deepStrictEqual(out, { ok: true });
  assert.deepStrictEqual(h.calls.map(c => c.kind), ["post", "refresh", "post"],
    "expected post -> refresh -> post, got " + JSON.stringify(h.calls.map(c => c.kind)));
  assert.strictEqual(h.calls[0].token, "STALE-TOKEN", "first attempt should carry the baked token");
  assert.strictEqual(h.calls[2].token, "FRESH-TOKEN",
    "the RETRY must carry the refreshed token -- retrying with the dead one heals nothing");
});

await t("a GET that 403s heals the same way", async () => {
  const h = harness([{ status: 403 }, { status: 200, body: { settings: {} } }], "FRESH-TOKEN");
  await h.box.apiGet("/api/settings");
  assert.deepStrictEqual(h.calls.map(c => c.kind), ["get", "refresh", "get"]);
  assert.strictEqual(h.calls[2].token, "FRESH-TOKEN");
});

await t("exactly ONE retry -- a server that 403s on principle is not hammered", async () => {
  const h = harness([{ status: 403 }], "FRESH-TOKEN");
  await assert.rejects(() => h.box.apiPost("/api/settings", {}));
  assert.strictEqual(h.calls.filter(c => c.kind === "post").length, 2,
    "a second 403 must surface as an error, not a third attempt");
});

await t("a refresh that itself fails surfaces the original refusal", async () => {
  const h = harness([{ status: 403 }], null);
  await assert.rejects(() => h.box.apiPost("/api/settings", {}),
    err => { assert.strictEqual(err.status, 403, "err.status must survive for callers that re-pair"); return true; });
  assert.strictEqual(h.calls.filter(c => c.kind === "post").length, 1,
    "no point retrying when the refresh did not produce a token");
});

await t("the happy path is still ONE call -- no refresh tax on every request", async () => {
  const h = harness([{ status: 200, body: { ok: 1 } }], "FRESH-TOKEN");
  await h.box.apiPost("/api/settings", {});
  assert.deepStrictEqual(h.calls.map(c => c.kind), ["post"]);
});

await t("a 500 is NOT retried -- only a refused token is a token problem", async () => {
  const h = harness([{ status: 500 }], "FRESH-TOKEN");
  await assert.rejects(() => h.box.apiPost("/api/settings", {}));
  assert.deepStrictEqual(h.calls.map(c => c.kind), ["post"]);
});

console.log(failed ? "\nFAILED " + failed : "\nALL PASS (6)");
process.exit(failed ? 1 : 0);
})();
