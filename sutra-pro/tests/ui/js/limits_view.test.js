"use strict";
// LimitsView (sutra_app/ui/static/js/limits_view.js): the Limits and Notifications groups of Settings and the strip line (gap package routines-limits).
// Run with: node --test tests/ui/js/limits_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const LV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/limits_view.js"));

const spend = (over = {}) => ({limit: null, spent: 0, pct: null, level: "none", unpriced_calls: 0, month: "2026-11", month_ends_at: "2026-12-01T00:00:00Z", line: "", ...over});
const guard = (over = {}) => ({enabled: false, level: "none", holding: false, top: null, line: "", windows: [], ...over});
const state = (s = {}, g = {}) => ({spend: spend(s), guard: guard(g)});
const WARN = state({limit: 10, spent: 8.2, pct: 0.82, level: "warn", line: "About $8.20 of your $10 monthly limit"});
const OVER = state({limit: 10, spent: 10.2, pct: 1.02, level: "over", line: "This month's spending limit is used up: about $10.20 of your $10 monthly limit. New tasks wait until you raise it or the month ends"});
const HOLD = state({}, {enabled: true, level: "hold", holding: true, line: "Claude weekly window is at 83%, resets Fri 09:00", top: {continued: false}});

function fakeApi(answers = {}) {
  const calls = [];
  const make = method => async (path, body) => {
    calls.push({method, path, body});
    const a = answers[method + " " + path];
    if (a instanceof Error) throw a;
    return a === undefined ? {} : a;
  };
  return {get: make("GET"), put: make("PUT"), post: make("POST"), calls};
}

// ---- the amount -----------------------------------------------------------------------------------------------------------------------

test("parseLimit: empty and zero clear the limit, dollars parse, anything else says why", () => {
  for (const clear of ["", "  ", "0", "0.00", "$0", null, undefined]) assert.deepEqual(LV.parseLimit(clear), {ok: true, value: null, error: ""}, String(clear));
  assert.equal(LV.parseLimit("10").value, 10);
  assert.equal(LV.parseLimit(" $12.50 ").value, 12.5);
  assert.equal(LV.parseLimit("$1,250").value, 1250);
  assert.equal(LV.parseLimit("100000").value, 100000);
  for (const bad of ["-5", "ten", "1.234", "1e3", "NaN", "10 dollars", "1.", ".5"]) {
    const r = LV.parseLimit(bad);
    assert.equal(r.ok, false, bad);
    assert.match(r.error, /dollar amount/);
  }
  assert.equal(LV.parseLimit("100001").error, "The most is $100,000.");
});

// ---- the Limits group -----------------------------------------------------------------------------------------------------------------

test("not loaded yet is said, not drawn", () => {
  assert.match(LV.limitsHtml(null, {}), /not loaded yet/);
  assert.match(LV.limitsHtml({spend: {}}, {}), /not loaded yet/);
});

test("with no limit the field is empty, there is no meter and the honest sentence about dollars is there", () => {
  const html = LV.limitsHtml(state(), {});
  assert.match(html, /data-group="limits"/);
  assert.match(html, /value="" placeholder="no limit"/);
  assert.doesNotMatch(html, /class="pmeter"/);
  assert.doesNotMatch(html, /data-act="clear-limit"/);
  assert.match(html, /an estimate at Claude&#39;s list price/);                              // an apostrophe is escaped like every other wire character
  assert.match(html, /Codex calls carry no dollar figure/);
  assert.match(html, /a task already running finishes/);
});

test("with a limit the field holds it, the line and the meter show the month, and No limit appears", () => {
  const html = LV.limitsHtml(WARN, {});
  assert.match(html, /value="10"/);
  assert.match(html, /About \$8\.20 of your \$10 monthly limit/);
  assert.match(html, /data-sev="warn"/);
  assert.match(html, /<i style="width:82%">/);
  assert.match(html, /data-act="clear-limit"/);
  const over = LV.limitsHtml(OVER, {});
  assert.match(over, /data-sev="bad"/);
  assert.match(over, /width:100%/);                                                         // past the limit, the bar stops at the end
  assert.match(over, /New tasks wait until you raise it/);
  assert.match(LV.limitsHtml(state({limit: 10, spent: 3, pct: 0.3, level: "ok", line: "About $3 of your $10 monthly limit"}), {}), /data-sev="ok"/);
});

test("calls that carry no dollar figure are counted out loud", () => {
  assert.match(LV.limitsHtml(state({limit: 10, spent: 1, pct: 0.1, level: "ok", unpriced_calls: 3, line: "x"}), {}), /3 calls this month had no dollar figure and are not counted/);
  assert.match(LV.limitsHtml(state({limit: 10, spent: 1, pct: 0.1, level: "ok", unpriced_calls: 1, line: "x"}), {}), /1 call this month had no dollar figure and is not counted/);
  assert.doesNotMatch(LV.limitsHtml(WARN, {}), /no dollar figure and/);
});

test("what the owner typed stays beside the refusal, and busy disables the buttons", () => {
  const html = LV.limitsHtml(WARN, {raw: "ten", error: "Type a dollar amount like 10 or 12.50, or leave it empty for no limit.", busy: true, saved: false});
  assert.match(html, /value="ten"/);
  assert.match(html, /role="alert">Type a dollar amount/);
  assert.equal((html.match(/ disabled/g) || []).length >= 3, true);
  assert.match(LV.limitsHtml(WARN, {saved: true}), /role="status">Saved\./);
});

test("the guard group tells each state in words and offers Continue only while work is held", () => {
  assert.match(LV.limitsHtml(state(), {}), /No plan window figure yet/);
  assert.match(LV.limitsHtml(state({}, {level: "ok"}), {}), /The plan windows have room/);
  const warn = LV.limitsHtml(state({}, {level: "warn", line: "Claude 5-hour window is at 72%, resets 14:05"}), {});
  assert.match(warn, /Claude 5-hour window is at 72%, resets 14:05\./);
  assert.doesNotMatch(warn, /data-act="guard-continue"/);
  const held = LV.limitsHtml(HOLD, {});
  assert.match(held, /New team runs wait\. Press Continue/);
  assert.match(held, /data-act="guard-continue"/);
  assert.match(held, /id="setf-guard" data-guard checked/);
  const off = LV.limitsHtml(state({}, {enabled: false, level: "hold", line: "Claude weekly window is at 83%"}), {});
  assert.match(off, /The guard is off, so nothing waits/);
  assert.doesNotMatch(off, / checked/);
  const kept = LV.limitsHtml(state({}, {enabled: true, level: "hold", holding: false, line: "Claude weekly window is at 83%", top: {continued: true}}), {});
  assert.match(kept, /Continuing: work proceeds until that window resets/);
  assert.doesNotMatch(kept, /data-act="guard-continue"/);
});

test("every word from the wire is escaped", () => {
  const evil = '<img src=x onerror="alert(1)">';
  const html = LV.limitsHtml(state({limit: 10, spent: 9, pct: 0.9, level: "warn", line: evil, month: evil}, {level: "warn", line: evil}), {raw: evil, error: evil});
  assert.equal(html.includes("<img"), false);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  const strip = LV.stripHtml(state({level: "warn", line: evil}, {level: "hold", holding: true, line: evil}));
  assert.equal(strip.includes("<img"), false);
  const prefs = LV.noticesHtml({quiet_hours: {start: evil, end: evil}, nudges_per_hour: evil, quiet_now: false, max_nudges_per_hour: evil}, {error: evil});
  assert.equal(prefs.includes("<img"), false);
  assert.match(LV.limitsHtml(state({limit: 10, spent: 1, pct: Number.NaN, level: "ok", line: "x"}), {}), /width:0%/);                // a bad number draws nothing wild
});

// ---- the strip --------------------------------------------------------------------------------------------------------------------------

test("the strip is empty until a limit is near, then one line each", () => {
  assert.equal(LV.stripHtml(null), "");
  assert.equal(LV.stripHtml(state()), "");
  assert.equal(LV.stripHtml(state({limit: 10, spent: 3, pct: 0.3, level: "ok", line: "About $3 of your $10 monthly limit"}, {level: "ok"})), "");
  const warn = LV.stripHtml(WARN);
  assert.match(warn, /<p class="nylimit" data-level="warn">About \$8\.20 of your \$10 monthly limit<\/p>/);
  assert.match(LV.stripHtml(OVER), /data-level="bad">This month&#39;s spending limit is used up/);
  const plan = LV.stripHtml(state({}, {level: "warn", line: "Claude weekly window is at 74%, resets Fri 09:00"}));
  assert.match(plan, /Claude weekly window is at 74%, resets Fri 09:00<\/p>/);
  assert.doesNotMatch(plan, /Continue/);
  const held = LV.stripHtml(HOLD);
  assert.match(held, /data-level="bad">Claude weekly window is at 83%, resets Fri 09:00\. New team runs wait\. <button type="button" class="linkbtn" data-act="guard-continue">Continue<\/button>/);
  assert.equal((LV.stripHtml(state({level: "over", limit: 1, line: "a"}, {level: "hold", holding: true, line: "b"})).match(/class="nylimit"/g) || []).length, 2);
  assert.doesNotMatch(LV.stripHtml(state({}, {level: "hold", holding: false, line: "Claude weekly window is at 83%"})), /Continue/);        // guard off: told, nothing to continue
});

// ---- the Notifications group --------------------------------------------------------------------------------------------------------------

test("noticesBody: both times or neither, different, 24-hour, and a whole cap that the ceiling refuses to pass", () => {
  assert.deepEqual(LV.noticesBody({start: "21:00", end: "08:00", nudges: "3"}), {ok: true, body: {quiet_hours: {start: "21:00", end: "08:00"}, nudges_per_hour: 3}, error: ""});
  assert.deepEqual(LV.noticesBody({start: "", end: "", nudges: "0"}).body, {quiet_hours: null, nudges_per_hour: 0});                     // 0 stays 0
  assert.equal(LV.noticesBody({start: "21:00", end: "08:00", nudges: "10"}).body.nudges_per_hour, 10);                                 // the ceiling itself is fine
  for (const over of ["11", "50", "99", "999"]) {                                                                                       // QA firstrun-settings: these were silently saved as 10
    const refused = LV.noticesBody({start: "", end: "", nudges: over});
    assert.deepEqual([refused.ok, refused.body], [false, null], over);
    assert.match(refused.error, /whole number from 0 to 10/, over);
  }
  assert.match(LV.noticesBody({start: "21:00", end: "", nudges: "3"}).error, /both times for quiet hours, or neither/);
  assert.match(LV.noticesBody({start: "", end: "08:00", nudges: "3"}).error, /both times/);
  assert.match(LV.noticesBody({start: "9:00", end: "17:00", nudges: "3"}).error, /like 21:00/);
  assert.match(LV.noticesBody({start: "25:00", end: "17:00", nudges: "3"}).error, /like 21:00/);
  assert.match(LV.noticesBody({start: "10:00", end: "10:00", nudges: "3"}).error, /all day or no time at all/);
  for (const bad of ["", "-1", "2.5", "three", "1000"]) assert.match(LV.noticesBody({start: "", end: "", nudges: bad}).error, /whole number from 0 to 10/, bad);
});

test("the Notifications group holds the stored choices, keeps typed ones beside an error and offers No quiet hours only when there is a window", () => {
  assert.match(LV.noticesHtml(null, {}), /not loaded yet/);
  const prefs = {quiet_hours: {start: "21:00", end: "08:00"}, nudges_per_hour: 3, quiet_now: true, max_nudges_per_hour: 10};
  const html = LV.noticesHtml(prefs, {});
  assert.match(html, /data-group="notices"/);
  assert.match(html, /data-input="quiet_start" value="21:00"/);
  assert.match(html, /data-input="quiet_end" value="08:00"/);
  assert.match(html, /max="10" step="1" inputmode="numeric" id="setf-nudges" data-input="nudges_per_hour" value="3"/);
  assert.match(html, /Quiet right now\./);
  assert.match(html, /data-act="clear-quiet"/);
  const none = LV.noticesHtml({quiet_hours: null, nudges_per_hour: 0, quiet_now: false, max_nudges_per_hour: 10}, {});
  assert.doesNotMatch(none, /data-act="clear-quiet"/);
  assert.match(none, /value="0"/);                                                                   // 0 shows as 0, not as empty
  assert.match(none, /Leave both empty for no quiet hours/);
  const typed = LV.noticesHtml(prefs, {start: "10:00", end: "10:00", nudges: "4", error: "Pick different times."});
  assert.match(typed, /data-input="quiet_start" value="10:00"/);
  assert.match(typed, /role="alert">Pick different times\./);
  assert.match(LV.noticesHtml(prefs, {saved: true}), /role="status">Saved\./);
  assert.match(html, /never capped/);                                                               // a question, an approval and a problem are not capped
});

test("the headings of Limits and Notifications can take focus (tabindex -1): home.js leaves the keyboard there when the control it was on is gone", () => {
  assert.match(LV.limitsHtml(state(), {}), /<h3 id="set-limits-h" tabindex="-1">Limits<\/h3>/);
  assert.match(LV.limitsHtml(null, {}), /<h3 id="set-limits-h" tabindex="-1">Limits<\/h3>/);
  assert.match(LV.noticesHtml({quiet_hours: null, nudges_per_hour: 3}, {}), /<h3 id="set-notices-h" tabindex="-1">Notifications<\/h3>/);
});

test("'Quiet right now.' follows the clock the page hands in, not the answer the server gave when it was read", () => {
  const prefs = {quiet_hours: {start: "21:00", end: "08:00"}, nudges_per_hour: 3, quiet_now: true, max_nudges_per_hour: 10};
  assert.match(LV.noticesHtml(prefs, {}), /Quiet right now\./);                                      // no clock handed in: the server's reading
  assert.doesNotMatch(LV.noticesHtml(prefs, {quietNow: false}), /Quiet right now\./);               // the window ended since the read
  assert.match(LV.noticesHtml(prefs, {quietNow: false}), /Leave both empty for no quiet hours/);
  const idle = {quiet_hours: {start: "21:00", end: "08:00"}, nudges_per_hour: 3, quiet_now: false, max_nudges_per_hour: 10};
  assert.match(LV.noticesHtml(idle, {quietNow: true}), /Quiet right now\./);                         // the window began since the read
  assert.match(LV.noticesHtml(idle, {quietNow: "yes"}), /Leave both empty/);                         // only a real boolean overrides the server
});

// ---- the calls -----------------------------------------------------------------------------------------------------------------------------

test("saveLimit sends the dollars, null to clear, and nothing at all for an amount it refuses", async () => {
  const api = fakeApi({"PUT /api/limits": WARN});
  const ok = await LV.saveLimit(api, "$10");
  assert.deepEqual([ok.ok, ok.state === WARN, ok.error], [true, true, ""]);
  assert.deepEqual(api.calls, [{method: "PUT", path: "/api/limits", body: {monthly_usd: 10}}]);
  await LV.saveLimit(api, "");
  assert.deepEqual(api.calls[1].body, {monthly_usd: null});
  const refused = await LV.saveLimit(api, "ten");
  assert.equal(refused.ok, false);
  assert.match(refused.error, /dollar amount/);
  assert.equal(api.calls.length, 2);
});

test("a refusal from the server is shown in the server's words, and a dead server in plain ones", async () => {
  const api = fakeApi({"PUT /api/limits": Object.assign(new Error("The request was refused"), {status: 422})});
  assert.deepEqual(await LV.saveLimit(api, "10"), {ok: false, state: null, error: "The request was refused"});
  const dead = fakeApi({"PUT /api/limits": new Error("")});
  assert.equal((await LV.saveGuard(dead, true)).error, "That did not work. Try again.");
});

test("saveGuard and continueGuard use the routes the server serves", async () => {
  const api = fakeApi({"PUT /api/limits": state({}, {enabled: true}), "POST /api/limits/continue": HOLD});
  assert.equal((await LV.saveGuard(api, true)).ok, true);
  assert.equal((await LV.saveGuard(api, "yes")).ok, true);
  assert.deepEqual(api.calls.map(c => [c.method, c.path, c.body]), [["PUT", "/api/limits", {guard_enabled: true}], ["PUT", "/api/limits", {guard_enabled: false}]]);
  const kept = await LV.continueGuard(api);
  assert.equal(kept.state, HOLD);
  assert.deepEqual(api.calls[2], {method: "POST", path: "/api/limits/continue", body: undefined});
});

test("saveNotices sends the body noticesBody makes, and nothing for a form it refuses", async () => {
  const api = fakeApi({"PUT /api/ops/attention": {quiet_hours: null, nudges_per_hour: 0}});
  assert.equal((await LV.saveNotices(api, {start: "", end: "", nudges: "0"})).ok, true);
  assert.deepEqual(api.calls[0], {method: "PUT", path: "/api/ops/attention", body: {quiet_hours: null, nudges_per_hour: 0}});
  assert.equal((await LV.saveNotices(api, {start: "10:00", end: "10:00", nudges: "3"})).ok, false);
  assert.equal(api.calls.length, 1);
});

test("load reads both and tolerates a failing one", async () => {
  const ok = await LV.load(fakeApi({"GET /api/limits": WARN, "GET /api/ops/attention": {nudges_per_hour: 3}}));
  assert.equal(ok.limits, WARN);
  assert.deepEqual(ok.notices, {nudges_per_hour: 3});
  const half = await LV.load(fakeApi({"GET /api/limits": new Error("down"), "GET /api/ops/attention": {nudges_per_hour: 3}}));
  assert.deepEqual([half.limits, half.notices], [null, {nudges_per_hour: 3}]);
  const none = await LV.load(fakeApi({"GET /api/limits": [1], "GET /api/ops/attention": "text"}));
  assert.deepEqual([none.limits, none.notices], [null, null]);
});

test("load can read the limits alone, which is what an event or the minute tick asks for", async () => {
  const api = fakeApi({"GET /api/limits": WARN, "GET /api/ops/attention": {nudges_per_hour: 3}});
  const got = await LV.load(api, {notices: false});
  assert.deepEqual([got.limits === WARN, got.notices], [true, null]);
  assert.deepEqual(api.calls.map(c => c.path), ["/api/limits"]);
});
