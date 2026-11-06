"use strict";
// PlanMeter (sutra_app/ui/static/js/plan_meter.js): a bar per usage window with its percent and reset time, the plan in words, and how old the
// figure is (GAP-providers). Re-expresses the old app's test_usage_account.js: the 80 and 95 edges, no bar for an absent figure, the reset words.
// Run with: node --test tests/ui/js/plan_meter.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const PM = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/plan_meter.js"));

const NOW = Date.UTC(2026, 10, 6, 12, 0, 0);          // a Friday
const S = NOW / 1000;
const MIN = 60;
const HOUR = 3600;
// a clock that does not depend on the machine's zone: UTC fields
const utc = ms => { const d = new Date(ms); return {day: d.getUTCDay(), date: d.getUTCDate(), month: d.getUTCMonth(), hh: d.getUTCHours(), mm: d.getUTCMinutes()}; };
const QUOTA = {status: "warning", window: "five_hour", used: 0.62, resets_at: S + HOUR + 10 * MIN, source: "rate_limit_event", seen_at: S - 300,
  windows: [{key: "five_hour", label: "5-hour", used: 0.62, resets_at: S + HOUR + 10 * MIN}, {key: "seven_day", label: "Weekly", used: 0.81, resets_at: S + 4 * 24 * HOUR}]};

test("the bar turns amber from 80 % and red from 95 % (the old thresholds)", () => {
  assert.equal(PM.severity(0), "ok");
  assert.equal(PM.severity(0.7999), "ok");
  assert.equal(PM.severity(0.8), "warn");
  assert.equal(PM.severity(0.9499), "warn");
  assert.equal(PM.severity(0.95), "bad");
  assert.equal(PM.severity(1.2), "bad");
});

test("an absent figure is never painted as a healthy 0 %", () => {
  for (const used of [null, undefined, "", "0.9", true, false, NaN, Infinity, -0.1, {}]) assert.equal(PM.severity(used), "unknown", String(used));
  const html = PM.windowHtml({key: "five_hour", label: "5-hour", used: null, resets_at: S + 25 * MIN}, NOW, utc);
  assert.match(html, /data-sev="unknown"><span class="pml">5-hour<\/span><span class="pmp">no figure<\/span><span class="pmr">resets in 25 min<\/span><\/div>/);
  assert.equal(html.includes("pmbar"), false);                                         // no bar at all: an empty bar is a claim
});

test("the reset words: minutes, then hours, then the weekday, then the date", () => {
  assert.equal(PM.resetText(S + 25 * MIN, NOW, utc), "resets in 25 min");
  assert.equal(PM.resetText(S + 20, NOW, utc), "resets in 1 min");
  assert.equal(PM.resetText(S + HOUR + 10 * MIN, NOW, utc), "resets in 1 h 10 min");
  assert.equal(PM.resetText(S + 2 * HOUR, NOW, utc), "resets in 2 h");
  assert.equal(PM.resetText(S + 4 * HOUR + 59 * MIN + 45, NOW, utc), "resets in 5 h");          // never "4 h 60 min"
  assert.equal(PM.resetText(S + 23 * HOUR + 59 * MIN, NOW, utc), "resets in 23 h 59 min");
  assert.equal(PM.resetText(S + 30 * HOUR, NOW, utc), "resets Sat 18:00");
  assert.equal(PM.resetText(S + 6 * 24 * HOUR + 3 * HOUR, NOW, utc), "resets Thu 15:00");
  assert.equal(PM.resetText(S + 10 * 24 * HOUR, NOW, utc), "resets 16 Nov 12:00");
  assert.equal(PM.resetText(null, NOW, utc), "");
  assert.equal(PM.resetText("soon", NOW, utc), "");
});

test("a window whose reset time has passed reads reset instead of a stale percent", () => {
  assert.equal(PM.resetText(S - 1, NOW, utc), "reset");
  const html = PM.windowHtml({key: "seven_day", label: "Weekly", used: 0.82, resets_at: S - 60}, NOW, utc);
  assert.match(html, /data-sev="reset"><span class="pml">Weekly<\/span><span class="pmp">reset<\/span><\/div>/);
  assert.equal(html.includes("82"), false);
});

test("one row per window, each with its percent, its reset and a bar that says the same in words", () => {
  const html = PM.meterHtml(QUOTA, NOW, {when: utc});
  assert.match(html, /^<div class="pmeter" role="group" aria-label="Plan usage">/);
  assert.match(html, /<div class="pmw" data-key="five_hour" data-sev="ok"><span class="pml">5-hour<\/span><span class="pmp">62%<\/span><span class="pmr">resets in 1 h 10 min<\/span><span class="pmbar" role="img" aria-label="5-hour at 62 percent"><i style="width:62%"><\/i><\/span><\/div>/);
  assert.match(html, /data-key="seven_day" data-sev="warn"><span class="pml">Weekly<\/span><span class="pmp">81%<\/span><span class="pmr">resets Tue 12:00<\/span>/);
  assert.match(html, /<p class="pmasof">as of 11:55<\/p><\/div>$/);
  assert.ok(html.indexOf("five_hour") < html.indexOf("seven_day"));
});

test("a bar never runs past its track, and an over-full window still says its number", () => {
  const html = PM.windowHtml({key: "five_hour", label: "5-hour", used: 1.04, resets_at: S + 600}, NOW, utc);
  assert.match(html, /data-sev="bad">.*<span class="pmp">104%<\/span>.*width:100%/);
});

test("an older snapshot with one window still draws that window", () => {
  const legacy = {status: "ok", window: "five_hour", used: 0.09, resets_at: S + 600, source: "rate_limit_event"};
  assert.deepEqual(PM.windowsOf(legacy), [{key: "five_hour", label: "5-hour", used: 0.09, resets_at: S + 600}]);
  assert.match(PM.meterHtml(legacy, NOW, {when: utc}), /<span class="pml">5-hour<\/span><span class="pmp">9%<\/span>/);
  assert.equal(PM.meterHtml(legacy, NOW, {when: utc}).includes("pmasof"), false);          // no seen_at, no "as of"
  assert.deepEqual(PM.windowsOf({status: "unknown", source: "none"}), []);
  assert.equal(PM.meterHtml(null, NOW), "");
  assert.equal(PM.meterHtml({windows: []}, NOW), "");
});

test("the figure says how old it is, with the day once it is older than a day", () => {
  assert.equal(PM.asOf({seen_at: S - 300}, NOW, utc), "as of 11:55");
  assert.equal(PM.asOf({seen_at: S - 2 * 24 * HOUR}, NOW, utc), "as of 4 Nov 12:00");
  assert.equal(PM.asOf({}, NOW, utc), "");
  assert.equal(PM.asOf({seen_at: "yesterday"}, NOW, utc), "");
});

test("the plan line names the plan, the account and how the plan is billed", () => {
  assert.equal(PM.planLine({plan_label: "Claude Max", account: "you@example.com", billing: "subscription"}),
    "Claude Max, you@example.com, counted against your plan, not billed per call");
  assert.equal(PM.planLine({plan_label: "ChatGPT Go", billing: "subscription"}), "ChatGPT Go, counted against your plan, not billed per call");
  assert.equal(PM.planLine({billing: "unknown"}), "");
  assert.equal(PM.planLine({billing: "toString"}), "");
  assert.equal(PM.planLine(null), "");
});

test("every word from the wire is written as text, and a key that is not a key names nothing", () => {
  const html = PM.meterHtml({windows: [{key: '"><svg onload=alert(1)>', label: '<img src=x onerror="alert(1)">', used: 0.5, resets_at: S + 600}]}, NOW, {when: utc});
  assert.equal(/<img|<svg/.test(html), false);
  assert.match(html, /data-key=""/);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.equal(PM.planLine({plan_label: "<b>Max</b>\u0000\n"}), "<b>Max</b>");                 // a line of text; the caller escapes it
});

test("the default clock is the browser's local time", () => {
  const t = PM.clockOf(NOW);
  const d = new Date(NOW);
  assert.deepEqual(t, {day: d.getDay(), date: d.getDate(), month: d.getMonth(), hh: d.getHours(), mm: d.getMinutes()});
});
