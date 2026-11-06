"use strict";
// ConsoleView (sutra_app/ui/static/js/console_view.js): the owner console at /console. The pure markup functions (money, usage, connectors,
// the Atom log, the card, health) and the controller (loads, paging, filters, the card, events, polling, the diagnostics download), driven with fakes.
// Run with: node --test tests/ui/js/console_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const CV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/console_view.js"));

const NOW = Date.UTC(2026, 10, 4, 12, 0, 0);
const flush = () => new Promise(resolve => setImmediate(resolve));
const fmt = epoch => "T" + epoch;                                       // a clock-time writer that does not depend on the machine's zone

/* ---------------------------------------------------------------- fixtures */
const REPORT = {
  period: "7d", since: "2026-10-29T00:00:00Z", include_stub: false,
  totals: {calls: 14, usd: 0.75, tokens_in: 3300, tokens_out: 460},
  providers: [
    {key: "claude", calls: 12, usd: 0.75, tokens_in: 1300, tokens_out: 160, usd_basis: ["reported"], billing: ["subscription"], notional: true},
    {key: "codex", calls: 2, usd: null, tokens_in: 2000, tokens_out: 300, usd_basis: ["unknown"], billing: ["unknown"], notional: false},
  ],
  days: [{key: "2026-11-02", calls: 3, usd: 0.25, tokens_in: 1, tokens_out: 1}, {key: "2026-11-04", calls: 11, usd: 0.5, tokens_in: 1, tokens_out: 1}],
  teams: [{key: "web", name: "Web <team>", calls: 14, usd: 0.75, tokens_in: 3300, tokens_out: 460}],
  functions: [{dept: "web", name: "Web <team>", fn: "audit", calls: 2, usd: 0.5, tokens_in: 1000, tokens_out: 100}, {dept: "web", name: "Web", fn: "identity", calls: 12, usd: 0.25, tokens_in: 2300, tokens_out: 360}],
  atoms: [
    {atom_id: "a-1", dept: "web", fn: "audit", node_id: "web.audit", calls: 2, usd: 0.5, tokens_in: 1000, tokens_out: 100, team_href: "/d/web/?tab=audit", node_href: "/?pane=graph&node=web.audit"},
    {atom_id: "a-2<x>", dept: "web", fn: "chat", node_id: null, calls: 1, usd: null, tokens_in: 5, tokens_out: null, team_href: "javascript:alert(1)", node_href: null},
  ],
};
const STATUS = {mode: "live", providers: [
  {name: "claude", installed: true, signed_in: true, health: {state: "ok"}, quota: {status: "warning", window: "five_hour", used: 0.624, resets_at: NOW / 1000 + 7800}, today: {calls: 4, tokens: 1500}},
  {name: "codex", installed: true, signed_in: false, health: {state: "signed_out"}, quota: {status: "ok", resets_at: NOW / 1000 + 900}, today: {calls: 0, tokens: 0}},
]};
const row = (seq, over) => ({seq, atom_id: "a-" + seq, node_id: seq % 2 ? "web.audit" : "web.identity", status: "closed", ts: "2026-11-04T10:" + String(seq % 60).padStart(2, "0") + ":00Z",
  body: {goal: "goal " + seq, verify: {template: "file-exists", exit_code: 0}, attempt: 1, model: "sonnet", touches: ["a.txt"], reason: null}, ...over});
const rows = (from, to) => Array.from({length: to - from + 1}, (_, i) => row(from + i));
const INFO = {version: "0.1.0", schema: 1, schema_expected: 1, data_dir: "/data", log_path: "/data/logs/server.log", db_bytes: 2048, free_bytes: 5 * 1024 ** 3, uptime_s: 3700, live_tasks: 1,
  engine_settings: {source: "data/engine.json", fields: ["budget"], env: [], problem: ""}, atom_log: {rows: 2500, last_seq: 2500}, usage_rows: 40};
const DOCTOR = {ok: false, summary: {ok: 11, warn: 1, fail: 1, skip: 1}, cached: true, age_s: 12.3, ttl_s: 30, checks: [
  {id: "python", title: "Python", status: "ok", detail: "3.11", fix: ""}, {id: "gh", title: "GitHub CLI", status: "warn", detail: "not logged in <b>", fix: "run gh auth login"},
  {id: "disk", title: "Free space", status: "fail", detail: "0.1 GB", fix: "free space"}, {id: "chrome", title: "Chrome", status: "skip", detail: "offline", fix: "ignored"}]};

/* ---------------------------------------------------------------- the pure functions */
test("money writes dollars with two places, four for a fraction of a cent, and says so when there is no figure", () => {
  assert.equal(CV.money(12.5), "$12.50");
  assert.equal(CV.money(0.0031), "$0.0031");
  assert.equal(CV.money(0.01), "$0.01");
  assert.equal(CV.money(0), "$0.00");
  assert.equal(CV.money(null), "no figure");
  assert.equal(CV.money(NaN), "no figure");
});

test("bytes, durations and the time until a reset read as words", () => {
  assert.equal(CV.bytesText(512), "512 B");
  assert.equal(CV.bytesText(2048), "2.0 KB");
  assert.equal(CV.bytesText(5 * 1024 ** 3), "5.0 GB");
  assert.equal(CV.bytesText(null), "unknown");
  assert.equal(CV.durationText(42), "42 s");
  assert.equal(CV.durationText(3700), "1 h 1 min");
  assert.equal(CV.durationText(3 * 86400), "3 days");
  assert.equal(CV.durationText(-1), "unknown");
  assert.equal(CV.untilText(NOW / 1000 + 1, NOW), "in 1 min");
  assert.equal(CV.untilText(NOW / 1000 + 3600, NOW), "in 1 h");
  assert.equal(CV.untilText(NOW / 1000 + 7800, NOW), "in 2 h 10 min");
  assert.equal(CV.untilText(NOW / 1000 + 3 * 86400, NOW), "in 3 days");
  assert.equal(CV.untilText(NOW / 1000 - 5, NOW), "now");
  assert.equal(CV.untilText(null, NOW), "");
});

test("safePath lets through a path on this origin and nothing else", () => {
  assert.equal(CV.safePath("/d/web/?tab=audit"), "/d/web/?tab=audit");
  for (const bad of ["//evil.example", "/\\evil", "javascript:alert(1)", "https://x.example/", "/a\"b", "/a<b", "", null, 5]) assert.equal(CV.safePath(bad), "", String(bad));
});

test("the picker marks the chosen period and the stub toggle follows its state", () => {
  const html = CV.periodBar({period: "30d", stub: true});
  assert.equal((html.match(/data-act="period"/g) || []).length, 4);
  assert.match(html, /data-period="30d" aria-pressed="true"/);
  assert.match(html, /data-period="today" aria-pressed="false"/);
  assert.match(html, /data-act="stub" checked/);
  assert.doesNotMatch(CV.periodBar({period: "7d", stub: false}), /checked/);
  assert.match(CV.periodBar(null), /data-period="7d" aria-pressed="true"/);
});

test("the totals show calls, Claude's dollars labelled notional for a subscription, and Codex's tokens", () => {
  const html = CV.usageHtml(REPORT, {period: "7d"}, "");
  assert.match(html, /Calls<\/span><b class="cvalue">14<\/b>/);
  assert.match(html, /Claude, usd<\/span><b class="cvalue">\$0\.75<\/b><span class="cnote">notional, subscription</);
  assert.match(html, /Codex, tokens<\/span><b class="cvalue">2,300<\/b><span class="cnote">in 2,000, out 300</);
});

test("a dollar figure that is not a subscription's carries its basis, and a provider that did not call says so", () => {
  const rate = {...REPORT, providers: [{...REPORT.providers[0], notional: false, usd_basis: ["rate_card", "reported"]}, {key: "codex", calls: 1, usd: 0.4, tokens_in: 10, tokens_out: 5, usd_basis: ["rate_card"], billing: ["api_key"], notional: false}]};
  const html = CV.usageHtml(rate, {}, "");
  assert.match(html, /\$0\.75<\/b><span class="cnote">rate card, reported</);
  assert.match(html, /in 10, out 5; \$0\.40 \(rate card\)/);
  const none = CV.usageHtml({...REPORT, providers: []}, {}, "");
  assert.match(none, /Claude, usd<\/span><b class="cvalue">none<\/b><span class="cnote">no calls in this period</);
  assert.match(none, /Codex, tokens<\/span><b class="cvalue">none<\/b>/);
});

test("a bar per day: the longest is full width, the others in proportion, by dollars first, then tokens, then calls", () => {
  const html = CV.usageHtml(REPORT, {}, "");
  assert.match(html, /data-day="2026-11-02">.*?width:50%/);
  assert.match(html, /data-day="2026-11-04">.*?width:100%/);
  assert.match(html, /Bars show dollars/);
  const tokensOnly = {...REPORT, days: [{key: "d1", calls: 1, usd: null, tokens_in: 100, tokens_out: 0}, {key: "d2", calls: 5, usd: null, tokens_in: 400, tokens_out: 0}]};
  assert.match(CV.usageHtml(tokensOnly, {}, ""), /Bars show tokens.*|width:25%/s);
  assert.match(CV.usageHtml(tokensOnly, {}, ""), /data-day="d1">.*?width:25%/);
  const callsOnly = {...REPORT, days: [{key: "d1", calls: 2, usd: null, tokens_in: null, tokens_out: null}, {key: "d2", calls: 4, usd: null, tokens_in: null, tokens_out: null}]};
  assert.match(CV.usageHtml(callsOnly, {}, ""), /Bars show calls per UTC day/);
  assert.match(CV.usageHtml({...REPORT, days: []}, {}, ""), /No calls in this period/);
  assert.match(CV.usageHtml({...REPORT, days: [{key: "d", calls: 1, usd: 0.0001, tokens_in: null, tokens_out: null}]}, {}, ""), /width:100%/);
});

test("the team table lists each team with its functions under it, and every name is escaped", () => {
  const html = CV.usageHtml(REPORT, {}, "");
  assert.match(html, /<caption>By team and function<\/caption>/);
  assert.match(html, /<tr class="cteam"><th scope="row">Web &lt;team&gt;<\/th><td>14<\/td><td>\$0\.75<\/td>/);
  assert.ok(html.indexOf('class="cteam"') < html.indexOf('<tr class="cfn"><th scope="row">audit'));
  assert.doesNotMatch(html, /<team>/);
});

test("the ten dearest atoms link to the team tab and the node, but only by a path on this origin", () => {
  const html = CV.usageHtml(REPORT, {}, "");
  assert.match(html, /<caption>Top ten atoms by cost<\/caption>/);
  assert.match(html, /<a href="\/d\/web\/\?tab=audit">Team tab<\/a> &middot; <a href="\/\?pane=graph&amp;node=web\.audit">Node<\/a>/);
  assert.doesNotMatch(html, /javascript:/);
  assert.match(html, /<code>a-2&lt;x&gt;<\/code>/);
  assert.match(html, /<td>web \/ audit<\/td>/);
  assert.match(html, /no figure/);
});

test("a failed or missing report shows its words and keeps the picker", () => {
  assert.match(CV.usageHtml(null, {}, ""), /Loading/);
  const failed = CV.usageHtml(null, {period: "all"}, "The app is not responding.");
  assert.match(failed, /role="alert">The app is not responding\./);
  assert.match(failed, /data-period="all" aria-pressed="true"/);
  assert.match(CV.usageHtml(REPORT, {}, "stale"), /role="alert">stale<[\s\S]*Calls/);
});

test("the connector rows give health, quota and today's use, and the next reset is the earliest one still to come", () => {
  const html = CV.connectorsHtml(STATUS, NOW, fmt);
  assert.match(html, /data-provider="claude"><b>Claude<\/b><span class="cchip st-ok">Ready<\/span><span class="cnote">Quota running low \(five_hour\), 62% used, resets T\d+ \(in 2 h 10 min\)<\/span>/);
  assert.match(html, /<span class="cchip st-signed_out">Not signed in<\/span>/);
  assert.match(html, /Today: 4 calls, 1,500 tokens/);
  assert.match(html, /data-next-reset="\d+">Next quota reset: T\d+ \(in 15 min, Codex\)/);
  assert.deepEqual(CV.nextReset(STATUS, NOW), {at: NOW / 1000 + 900, provider: "codex"});
  assert.equal(CV.nextReset(STATUS, NOW + 3 * 3600 * 1000), null);
  assert.match(CV.connectorsHtml(STATUS, NOW + 3 * 3600 * 1000, fmt), /No quota reset is pending\./);
});

test("a snapshot with every window of the plan gets a meter per window and the plan with its account (GAP-providers)", () => {
  const utc = ms => { const d = new Date(ms); return {day: d.getUTCDay(), date: d.getUTCDate(), month: d.getUTCMonth(), hh: d.getUTCHours(), mm: d.getUTCMinutes()}; };
  const status = {providers: [{name: "claude", installed: true, signed_in: true, billing: "subscription", plan: "max", plan_label: "Claude Max", account: "you@example.com",
    health: {state: "ok"}, today: {calls: 1, tokens: 10},
    quota: {status: "warning", window: "five_hour", used: 0.62, resets_at: NOW / 1000 + 4200, seen_at: NOW / 1000 - 60,
      windows: [{key: "five_hour", label: "5-hour", used: 0.62, resets_at: NOW / 1000 + 4200}, {key: "seven_day", label: "Weekly", used: 0.96, resets_at: NOW / 1000 + 86400 * 3}]}}]};
  const html = CV.connectorsHtml(status, NOW, fmt, utc);
  assert.match(html, /<span class="cnote">Quota running low<\/span>/);                    // the meters carry the windows; the line keeps the state
  assert.match(html, /<p class="pmplan">Claude Max, you@example\.com, counted against your plan, not billed per call<\/p><div class="pmeter"/);
  assert.match(html, /data-key="five_hour" data-sev="ok">.*62%.*resets in 1 h 10 min/);
  assert.match(html, /data-key="seven_day" data-sev="bad">.*96%/);
  assert.match(html, /as of 11:59/);
});

test("a connector that is missing, has no quota signal or an unknown state still gets a row", () => {
  const html = CV.connectorsHtml({providers: [{name: "codex", installed: false, health: {state: "ok"}}, {name: "claude", installed: true, health: {state: "weird<"}, quota: null}]}, NOW, fmt);
  assert.match(html, /<span class="cchip st-ok">Not installed<\/span>/);
  assert.match(html, /No quota signal yet/);
  assert.match(html, /weird&lt;/);
  assert.match(CV.connectorsHtml(null, NOW, fmt), /Not loaded yet/);
  assert.match(CV.connectorsHtml({providers: []}, NOW, fmt), /No connector is configured/);
});

test("filterRows applies state, check and the two UTC dates, ends included", () => {
  const data = [row(1, {status: "closed", ts: "2026-11-01T23:59:59Z"}), row(2, {status: "verify_failed", ts: "2026-11-02T00:00:00Z"}),
    row(3, {status: "closed", ts: "2026-11-03T12:00:00Z", body: {goal: "g", verify: null}}), row(4, {status: "closed", ts: "2026-11-04T00:00:01Z"})];
  const seqs = f => CV.filterRows(data, f).map(r => r.seq);
  assert.deepEqual(seqs({}), [1, 2, 3, 4]);
  assert.deepEqual(seqs({state: "closed"}), [1, 3, 4]);
  assert.deepEqual(seqs({check: "file-exists"}), [1, 2, 4]);
  assert.deepEqual(seqs({check: "(none)"}), [3]);
  assert.deepEqual(seqs({from: "2026-11-02"}), [2, 3, 4]);
  assert.deepEqual(seqs({to: "2026-11-03"}), [1, 2, 3]);
  assert.deepEqual(seqs({from: "2026-11-02", to: "2026-11-02"}), [2]);
  assert.deepEqual(seqs({state: "closed", from: "2026-11-03", check: "(none)"}), [3]);
  assert.deepEqual(CV.filterRows(null, {}), []);
});

test("pageRows shows the newest first, 25 to a page, and keeps the page inside the range", () => {
  const first = CV.pageRows(rows(1, 60), 0, 25);
  assert.equal(first.rows[0].seq, 60);
  assert.equal(first.rows.length, 25);
  assert.equal(first.pages, 3);
  const last = CV.pageRows(rows(1, 60), 2, 25);
  assert.deepEqual([last.rows[0].seq, last.rows.length], [10, 10]);
  assert.equal(CV.pageRows(rows(1, 60), 9, 25).page, 2);
  assert.equal(CV.pageRows(rows(1, 60), -3, 25).page, 0);
  assert.deepEqual(CV.pageRows([], 0, 25), {rows: [], page: 0, pages: 1});
  assert.equal(CV.pageRows(rows(1, 30), 0, 0).rows.length, 25);
});

test("the Atom log table has the ledger columns, the state chip, the check with its exit code, and a button that opens the card", () => {
  const html = CV.logHtml({rows: [row(7, {status: "verify_failed", body: {goal: "make <b>it</b>", verify: {template: "file-exists", exit_code: 2}, attempt: 2, model: "opus"}})], nodes: ["web.audit"], selected: 7});
  assert.match(html, /<caption>Atom log, newest first \(1 of 1 loaded\)<\/caption>/);
  for (const head of ["Seq", "When (UTC)", "Atom", "Node", "State", "Check", "Try", "Model", "Goal"]) assert.match(html, new RegExp('<th scope="col">' + head.replace(/[()]/g, "\\$&") + "</th>"));
  assert.match(html, /data-act="open-card" data-seq="7" aria-expanded="true">7<\/button>/);
  assert.match(html, /<tr class="lrow st-verify_failed" data-seq="7" aria-selected="true">/);
  assert.match(html, /<span class="cchip st-verify_failed">verify failed<\/span>/);
  assert.match(html, /file-exists \(exit 2\)/);
  assert.match(html, /make &lt;b&gt;it&lt;\/b&gt;/);
  assert.match(html, /<td title="2026-11-04T10:07:00Z">2026-11-04 10:07:00<\/td>/);
});

test("the Atom log shows the filters as chosen, the pager, the load-older button and the right empty words", () => {
  const data = rows(1, 60);
  const html = CV.logHtml({rows: data, nodes: ["web.audit", "web.identity"], node: "web.gone", state: "closed", check: "file-exists", from: "2026-11-01", page: 1, canLoadOlder: true, capped: false});
  assert.match(html, /<option value="web\.gone" selected>web\.gone<\/option>/);
  assert.match(html, /<option value="closed" selected>Closed<\/option>/);
  assert.match(html, /<option value="file-exists" selected>file-exists<\/option>/);
  assert.match(html, /id="f-from" value="2026-11-01"/);
  assert.match(html, /Page 2 of 3/);
  assert.match(html, /data-dir="newer">Newer/);
  assert.match(html, /data-act="log-older">Load 1000 older rows/);
  assert.doesNotMatch(CV.logHtml({rows: data, canLoadOlder: false}), /log-older/);
  assert.match(CV.logHtml({rows: data, page: 0}), /data-dir="newer" disabled/);
  assert.match(CV.logHtml({rows: data, page: 2}), /data-dir="older" disabled/);
  assert.match(CV.logHtml({rows: []}), /The Atom log is empty\./);
  assert.match(CV.logHtml({rows: data, state: "refused", from: "2030-01-01"}), /No row matches these filters\./);
  assert.match(CV.logHtml({rows: data, capped: true}), /Only the first 5000 rows/);
  assert.match(CV.logHtml({rows: [], error: "bad <e>"}), /role="alert">bad &lt;e&gt;</);
  assert.match(CV.logHtml({rows: [row(1, {body: {goal: "x", verify: null}})]}), /<option value="\(none\)">\(none\)<\/option>/);
});

test("the card of a row is the atom card when the atom was read, else the card the ledger row can give", () => {
  const r = row(4, {status: "abandoned", body: {goal: "ship <it>", verify: {template: "file-exists", exit_code: 1}, attempt: 3, model: "sonnet", touches: ["a.txt", "b.txt"], reason: "verify failed: file-exists"}});
  const full = CV.cardHtml(r, {id: "a-4"}, (atom, opts) => "<details data-atom=\"" + atom.id + "\" data-open=\"" + opts.open + "\"></details>");
  assert.match(full, /Log row 4 &middot; 2026-11-04 10:04:00 UTC &middot; abandoned &middot; web\.identity/);
  assert.match(full, /<details data-atom="a-4" data-open="true">/);
  const plain = CV.cardHtml(r, null, null);
  assert.match(plain, /<div class="atomcard ledgercard" data-state="abandoned"><b>ABANDONED<\/b>/);
  assert.match(plain, /<b>Goal<\/b> <div>ship &lt;it&gt;<\/div>/);
  assert.match(plain, /<b>Check<\/b> <div>file-exists, exit code 1<\/div>/);
  assert.match(plain, /<b>Try<\/b> <div>3 of 3<\/div>/);
  assert.match(plain, /<b>Touches<\/b> <div>a\.txt, b\.txt<\/div>/);
  assert.match(plain, /<b>Reason<\/b> <div>verify failed: file-exists<\/div>/);
  assert.doesNotMatch(CV.cardHtml(row(5, {body: {goal: "g"}}), null, null), /<b>Reason<\/b>/);
  assert.equal(CV.cardHtml(null, null, null), "");
});

test("Health lists the facts, the doctor's checks with fixes for warnings and failures only, and the two buttons", () => {
  const html = CV.healthHtml(INFO, DOCTOR, {});
  for (const [k, v] of [["Version", "0.1.0"], ["Schema", "1"], ["Data folder", "/data"], ["Log file", "/data/logs/server.log"], ["Database size", "2.0 KB"], ["Free space", "5.0 GB"],
    ["Uptime", "1 h 1 min"], ["Live tasks", "1"], ["Engine settings from", "data/engine.json (budget)"], ["Atom log", "2,500 rows"]]) {
    assert.ok(html.includes("<dt>" + k + "</dt><dd>" + v + "</dd>"), k);
  }
  assert.match(html, /data-doctor="fail">Something failed\. 11 ok, 1 warning\(s\), 1 failed, 1 skipped\. Checked 12 s ago\./);
  assert.match(html, /data-check="gh"[^>]*>.*not logged in &lt;b&gt;<span class="cfix"> Fix: run gh auth login<\/span>/);
  assert.match(html, /data-check="disk"[\s\S]*Fix: free space/);
  assert.doesNotMatch(html, /ignored/);
  assert.doesNotMatch(html.slice(html.indexOf('data-check="python"'), html.indexOf('data-check="gh"')), /Fix:/);
  assert.match(html, /data-act="doctor-refresh">Check again/);
  assert.match(html, /data-act="download">Download diagnostics/);
  assert.match(html, /no chat, prompt, site file or secret/);
});

test("Health says when the schema is not the one this build expects, when the doctor is fresh and when a load failed", () => {
  assert.match(CV.healthHtml({...INFO, schema: 2}, null, {}), /<dd>2 \(this build expects 1\)<\/dd>/);
  assert.match(CV.healthHtml(INFO, {...DOCTOR, ok: true, cached: false}, {}), /Nothing failed\. .*Checked just now\./);
  const bad = CV.healthHtml(null, null, {infoError: "no info", doctorError: "no doctor", downloadError: "no zip"});
  for (const w of ["no info", "no doctor", "no zip"]) assert.match(bad, new RegExp('role="alert">' + w));
  assert.doesNotMatch(bad, /Loading/);
  assert.match(CV.healthHtml(null, null, {}), /Loading/);
  assert.match(CV.healthHtml(INFO, null, {downloading: true}), /data-act="download" disabled>Preparing/);
  assert.match(CV.healthHtml({...INFO, engine_settings: {source: "defaults", fields: [], env: ["J2_BUDGET"], problem: "bad <json>"}}, null, {}), /defaults \[J2_BUDGET\] - unreadable: bad &lt;json&gt;/);
});

/* ---------------------------------------------------------------- the controller, with fakes */
function el(id) {
  const listeners = {};
  return {id, innerHTML: "", textContent: "", sets: 0, listeners, __html: undefined, dataset: {}, contains: () => false,
    addEventListener(type, fn) { listeners[type] = fn; }};
}
function makeDoc() {
  const els = {};
  for (const id of ["console-root", "c-usage", "c-log", "c-health", "cstate"]) els[id] = el(id);
  const doc = {els, activeElement: null, getElementById: id => els[id] || null};
  for (const id of ["c-usage", "c-log", "c-health"]) {
    let html = "";
    Object.defineProperty(els[id], "innerHTML", {get: () => html, set: v => { html = v; els[id].sets += 1; }});
  }
  return doc;
}

// A fake api: `routes` maps "path" to a value or a function (query) -> value; a thrown Error becomes a rejected call.
function makeApi(routes) {
  const calls = [];
  return {calls, get(p, query) {
    calls.push({path: p, query: query});
    const key = Object.keys(routes).find(k => p === k || (k.endsWith("*") && p.startsWith(k.slice(0, -1))));
    if (!key) return Promise.reject(Object.assign(new Error("no route " + p), {status: 404}));
    const v = routes[key];
    try { return Promise.resolve(typeof v === "function" ? v(query, p) : v); } catch (e) { return Promise.reject(e); }
  }};
}
const logRoute = all => (q) => all.filter(r => r.seq > q.after && (!q.node_id || r.node_id === q.node_id)).slice(0, q.limit);

// events fake: connect() keeps its options, coalesce() makes a function that waits for flush().
function makeEvents() {
  const state = {pending: new Map(), connected: null, closed: false, ms: []};
  return {state,
    coalesce(fn, ms) { const f = (...a) => { state.pending.set(f, () => fn(...a)); }; f.cancel = () => state.pending.delete(f); state.ms.push(ms); return f; },
    connect(opts) { state.connected = opts; return {close: () => { state.closed = true; }, state: () => "live"}; },
    flushAll() { const run = Array.from(state.pending.values()); state.pending.clear(); run.forEach(f => f()); }};
}

function setup(over) {
  const o = over || {};
  const doc = makeDoc();
  const all = o.log || rows(1, 2500);
  const api = makeApi({"/api/ops/usage": () => REPORT, "/api/connectors/status": () => STATUS, "/api/ops/info": () => INFO, "/api/ops/doctor": () => DOCTOR,
    "/api/atoms/log": logRoute(all), "/api/atoms/*": (q, p) => { if (o.noAtom) throw new Error("gone"); return {id: decodeURIComponent(p.slice(11)), goal: "the goal"}; }, ...(o.routes || {})});
  const events = makeEvents();
  const saved = [];
  const fetchCalls = [];
  const page = CV.create({doc, api, events, now: () => NOW, format: fmt, fnode: {atomHtml: (a, opts) => "<details data-atom=\"" + a.id + "\"></details>"},
    token: "tok-0123456789abcdef", save: (blob, name) => saved.push({blob, name}),
    fetch: o.fetch || (async (url, init) => { fetchCalls.push({url, init}); return {ok: true, status: 200, headers: {get: () => 'attachment; filename="diag-1.zip"'}, blob: async () => "BLOB"}; })});
  return {page, doc, api, events, saved, fetchCalls, S: page.state()};
}
const click = async (doc, target) => { doc.els["console-root"].listeners.click({target}); await flush(); };
const target = (dataset, extra) => ({dataset, closest: sel => (sel === "[data-act]" ? (dataset.act ? target(dataset, extra) : null) : null), ...extra});
const rowTarget = seq => ({dataset: {seq: String(seq)}, closest: sel => (sel === "[data-act]" ? null : {dataset: {seq: String(seq)}})});
const change = async (doc, name, value) => { doc.els["console-root"].listeners.change({target: {dataset: {filter: name}, value}}); await flush(); };
const paths = api => api.calls.map(c => c.path);

test("start loads usage, connectors, info and the doctor, then the newest window of the log, and paints the three panels", async () => {
  const t = setup();
  await t.page.start();
  assert.deepEqual(paths(t.api).slice(0, 4).sort(), ["/api/connectors/status", "/api/ops/doctor", "/api/ops/info", "/api/ops/usage"]);
  assert.deepEqual(t.api.calls.find(c => c.path === "/api/ops/usage").query, {period: "7d", include_stub: 0});
  assert.deepEqual(t.api.calls.find(c => c.path === "/api/ops/doctor").query, undefined);
  assert.match(t.doc.els["c-usage"].innerHTML, /Claude, usd.*\$0\.75/s);
  assert.match(t.doc.els["c-usage"].innerHTML, /Next quota reset/);
  assert.match(t.doc.els["c-log"].innerHTML, /Atom log, newest first \(1,000 of 1,000 loaded\)/);
  assert.match(t.doc.els["c-health"].innerHTML, /<dt>Version<\/dt><dd>0\.1\.0<\/dd>/);
});

test("the log starts at the newest window: the first read is after seq 1500 of 2500, in pages of 500 until a short page", async () => {
  const t = setup();
  await t.page.start();
  const reads = t.api.calls.filter(c => c.path === "/api/atoms/log").map(c => c.query);
  assert.deepEqual(reads, [{after: 1500, limit: 500}, {after: 2000, limit: 500}, {after: 2500, limit: 500}]);
  assert.equal(t.S.log.rows.length, 1000);
  assert.equal(t.S.log.rows[0].seq, 1501);
  assert.equal(t.S.log.canLoadOlder, true);
  assert.equal(t.S.log.loaded, true);
  assert.deepEqual(t.S.log.nodes, ["web.audit", "web.identity"]);
});

test("a small log loads whole and offers nothing older", async () => {
  const t = setup({log: rows(1, 30), routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 30, last_seq: 30}})}});
  await t.page.start();
  assert.equal(t.S.log.rows.length, 30);
  assert.equal(t.S.log.canLoadOlder, false);
  assert.doesNotMatch(t.doc.els["c-log"].innerHTML, /log-older/);
});

test("Load older rows reads the 1000 seqs below the window, puts them first once and stops at the start", async () => {
  const t = setup();
  await t.page.start();
  await click(t.doc, target({act: "log-older"}));
  assert.equal(t.S.log.after, 500);
  assert.equal(t.S.log.rows.length, 2000);
  assert.deepEqual([t.S.log.rows[0].seq, t.S.log.rows[1999].seq], [501, 2500]);
  assert.equal(new Set(t.S.log.rows.map(r => r.seq)).size, 2000);
  await t.page.loadOlder();
  assert.equal(t.S.log.after, 0);
  assert.equal(t.S.log.rows.length, 2500);
  assert.equal(t.S.log.canLoadOlder, false);
  const before = t.api.calls.length;
  await t.page.loadOlder();
  assert.equal(t.api.calls.length, before);
});

test("a poll reads only what is newer than the newest row and does not repeat a row", async () => {
  const all = rows(1, 30);
  const t = setup({log: all, routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 30, last_seq: 30}})}});
  await t.page.start();
  all.push(row(31), row(32));
  const mark = t.api.calls.length;
  await t.page.loadMoreLog();
  assert.deepEqual(t.api.calls.slice(mark).filter(c => c.path === "/api/atoms/log").map(c => c.query), [{after: 30, limit: 500}]);
  assert.equal(t.S.log.rows.length, 32);
  assert.equal(t.S.log.last, 32);
  await t.page.loadMoreLog();
  assert.equal(t.S.log.rows.length, 32);
});

test("choosing a node asks the server for that node from the start, and clearing it goes back to the newest window", async () => {
  const t = setup();
  await t.page.start();
  const mark = t.api.calls.length;
  await change(t.doc, "node", "web.audit");
  const reads = t.api.calls.slice(mark).filter(c => c.path === "/api/atoms/log").map(c => c.query);
  assert.deepEqual(reads[0], {after: 0, limit: 500, node_id: "web.audit"});
  assert.equal(t.S.log.rows.length, 1250);
  assert.ok(t.S.log.rows.every(r => r.node_id === "web.audit"));
  assert.equal(t.S.log.canLoadOlder, false);
  assert.deepEqual(t.S.log.nodes, ["web.audit", "web.identity"]);
  await click(t.doc, target({act: "clear-filters"}));
  await flush();
  assert.equal(t.S.log.node, "");
  assert.equal(t.S.log.rows.length, 1000);
  assert.equal(t.S.log.canLoadOlder, true);
});

test("a node with more rows than the cap is loaded up to the cap and says so", async () => {
  const t = setup({log: rows(1, 6000).map(r => ({...r, node_id: "web.audit"}))});
  await t.page.start();
  await change(t.doc, "node", "web.audit");
  assert.equal(t.S.log.rows.length, 5000);
  assert.equal(t.S.log.capped, true);
  assert.match(t.doc.els["c-log"].innerHTML, /Only the first 5000 rows/);
});

test("state, check and date filters work on the loaded rows without a request, and a filter goes back to page one", async () => {
  const all = rows(1, 60).map(r => (r.seq % 4 === 0 ? {...r, status: "refused"} : r));
  const t = setup({log: all, routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 60, last_seq: 60}})}});
  await t.page.start();
  await click(t.doc, target({act: "log-page", dir: "older"}));
  assert.equal(t.S.log.page, 1);
  const mark = t.api.calls.length;
  await change(t.doc, "state", "refused");
  assert.equal(t.api.calls.length, mark);
  assert.equal(t.S.log.page, 0);
  assert.match(t.doc.els["c-log"].innerHTML, /\(15 of 60 loaded\)/);
  await change(t.doc, "check", "file-exists");
  await change(t.doc, "from", "2026-11-05");
  assert.match(t.doc.els["c-log"].innerHTML, /No row matches these filters\./);
  await click(t.doc, target({act: "clear-filters"}));
  assert.match(t.doc.els["c-log"].innerHTML, /\(60 of 60 loaded\)/);
  await change(t.doc, "nonsense", "x");
  assert.equal(t.S.log.nonsense, undefined);
});

test("a row opens its card: the atom is fetched by its id and drawn, a second click closes it", async () => {
  const t = setup({log: [{...row(1), atom_id: "j2-run:W-3.a1"}], routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 1, last_seq: 1}})}});
  await t.page.start();
  await click(t.doc, target({act: "open-card", seq: "1"}));
  assert.ok(t.api.calls.some(c => c.path === "/api/atoms/j2-run%3AW-3.a1"));
  assert.match(t.doc.els["c-log"].innerHTML, /<details data-atom="j2-run:W-3\.a1"><\/details>/);
  assert.match(t.doc.els["c-log"].innerHTML, /aria-selected="true"/);
  await click(t.doc, rowTarget(1));
  assert.equal(t.S.log.selected, null);
  assert.doesNotMatch(t.doc.els["c-log"].innerHTML, /data-atom=/);
  await click(t.doc, rowTarget(1));
  assert.equal(t.S.log.selected, 1);
});

test("a log row whose atom cannot be read still opens, as the card its ledger row gives", async () => {
  const t = setup({log: rows(1, 3), noAtom: true, routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 3, last_seq: 3}})}});
  await t.page.start();
  await click(t.doc, target({act: "open-card", seq: "2"}));
  assert.match(t.doc.els["c-log"].innerHTML, /atomcard ledgercard/);
  assert.match(t.doc.els["c-log"].innerHTML, /<b>Goal<\/b> <div>goal 2<\/div>/);
  await click(t.doc, target({act: "open-card", seq: "999"}));
  assert.equal(t.S.log.selected, 2);
});

test("choosing a filter closes an open card", async () => {
  const t = setup({log: rows(1, 3), routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 3, last_seq: 3}})}});
  await t.page.start();
  await click(t.doc, target({act: "open-card", seq: "1"}));
  await change(t.doc, "state", "closed");
  assert.equal(t.S.log.selected, null);
  assert.equal(t.S.log.cardHtml, "");
});

test("the period buttons and the stub toggle read usage again with their choice", async () => {
  const t = setup();
  await t.page.start();
  await click(t.doc, target({act: "period", period: "today"}));
  await click(t.doc, target({act: "stub"}, {checked: true}));
  await click(t.doc, target({act: "period", period: "bogus"}));
  const queries = t.api.calls.filter(c => c.path === "/api/ops/usage").map(c => c.query);
  assert.deepEqual(queries.slice(1), [{period: "today", include_stub: 0}, {period: "today", include_stub: 1}, {period: "7d", include_stub: 1}]);
  assert.match(t.doc.els["c-usage"].innerHTML, /data-period="7d" aria-pressed="true"/);
});

test("a failing usage route shows its words in its panel and leaves the other panels alone", async () => {
  const t = setup({routes: {"/api/ops/usage": () => { throw Object.assign(new Error("The app is not responding."), {code: "network"}); }}});
  await t.page.start();
  assert.match(t.doc.els["c-usage"].innerHTML, /role="alert">The app is not responding\./);
  assert.match(t.doc.els["c-health"].innerHTML, /<dt>Version<\/dt>/);
  assert.match(t.doc.els["c-log"].innerHTML, /Atom log, newest first/);
  const bad = setup({routes: {"/api/ops/info": () => { throw new Error("info down"); }, "/api/ops/doctor": () => { throw new Error("doctor down"); }}});
  await bad.page.start();
  assert.match(bad.doc.els["c-health"].innerHTML, /role="alert">info down/);
  assert.match(bad.doc.els["c-health"].innerHTML, /role="alert">doctor down/);
});

test("a failing log read shows its words, and the next successful read clears them", async () => {
  let fail = true;
  const all = rows(1, 5);
  const t = setup({log: all, routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 5, last_seq: 5}}), "/api/atoms/log": q => { if (fail) throw new Error("log down"); return logRoute(all)(q); }}});
  await t.page.start();
  assert.match(t.doc.els["c-log"].innerHTML, /role="alert">log down/);
  fail = false;
  await t.page.loadMoreLog();
  assert.doesNotMatch(t.doc.els["c-log"].innerHTML, /log down/);
  assert.equal(t.S.log.rows.length, 5);
});

test("the event stream is joined on its topics with the 2 s polling fallback, and its state shows in the header", async () => {
  const t = setup();
  await t.page.start();
  const c = t.events.state.connected;
  assert.equal(c.url, "/api/events");
  assert.deepEqual(c.topics, ["usage", "atom", "connector", "task"]);
  assert.equal(c.pollMs, 2000);
  assert.equal(typeof c.pollFn, "function");
  c.onState("live");
  assert.equal(t.doc.els.cstate.textContent, "Live");
  c.onState("polling");
  assert.equal(t.doc.els.cstate.textContent, "Updating every 2 s");
  c.onState("offline");
  assert.equal(t.doc.els.cstate.textContent, "Not connected");
  assert.deepEqual(t.events.state.ms, [1000, 1000, 1000]);
});

test("usage.recorded is coalesced: many events make one refresh of usage, connectors and info", async () => {
  const t = setup();
  await t.page.start();
  const mark = t.api.calls.length;
  for (let i = 0; i < 5; i += 1) t.events.state.connected.onEvent("usage.recorded", {});
  assert.equal(t.api.calls.length, mark);
  t.events.flushAll();
  await flush();
  assert.deepEqual(paths(t.api).slice(mark).sort(), ["/api/connectors/status", "/api/ops/info", "/api/ops/usage"]);
});

test("atom.updated reads the new log rows, connector and task events read the connectors, a resync reads everything", async () => {
  const all = rows(1, 5);
  const t = setup({log: all, routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 5, last_seq: 5}})}});
  await t.page.start();
  all.push(row(6));
  let mark = t.api.calls.length;
  t.events.state.connected.onEvent("atom.updated", {});
  t.events.flushAll();
  await flush();
  assert.ok(paths(t.api).slice(mark).includes("/api/atoms/log"));
  assert.equal(t.S.log.rows.length, 6);
  for (const type of ["connector.health", "connector.switch", "connector.mode", "task.updated"]) {
    mark = t.api.calls.length;
    t.events.state.connected.onEvent(type, {});
    t.events.flushAll();
    await flush();
    assert.deepEqual(paths(t.api).slice(mark).sort(), ["/api/connectors/status", "/api/ops/info"], type);
  }
  mark = t.api.calls.length;
  t.events.state.connected.onEvent("chat.turn", {});
  t.events.flushAll();
  assert.equal(t.api.calls.length, mark);
  t.events.state.connected.onEvent("server.resync", {});
  await flush();
  assert.ok(["/api/ops/usage", "/api/connectors/status", "/api/ops/info"].every(p => paths(t.api).slice(mark).includes(p)));
});

test("the polling fallback refreshes the panels but asks the doctor only every 30 seconds", async () => {
  let clock = NOW;
  const t = setup();
  t.page = CV.create({doc: t.doc, api: t.api, events: t.events, now: () => clock, format: fmt});
  await t.page.start();
  const doctorCalls = () => t.api.calls.filter(c => c.path === "/api/ops/doctor").length;
  assert.equal(doctorCalls(), 1);
  clock += 2000;
  await t.page.refreshAll();
  assert.equal(doctorCalls(), 1);
  clock += 28000;
  await t.page.refreshAll();
  assert.equal(doctorCalls(), 2);
  assert.ok(t.api.calls.filter(c => c.path === "/api/ops/usage").length >= 3);
});

test("Check again asks the doctor to run now", async () => {
  const t = setup();
  await t.page.start();
  await click(t.doc, target({act: "doctor-refresh"}));
  assert.deepEqual(t.api.calls.filter(c => c.path === "/api/ops/doctor").map(c => c.query), [undefined, {refresh: 1}]);
});

test("the diagnostics download sends the token in the header, saves the zip under the server's name and guards a second click", async () => {
  const t = setup();
  await t.page.start();
  const first = t.page.download();
  const second = t.page.download();
  assert.match(t.doc.els["c-health"].innerHTML, /data-act="download" disabled>Preparing/);
  await Promise.all([first, second]);
  assert.equal(t.fetchCalls.length, 1);
  assert.equal(t.fetchCalls[0].url, "/api/ops/diagnostics");
  assert.equal(t.fetchCalls[0].init.headers["X-Sutra-Token"], "tok-0123456789abcdef");
  assert.deepEqual(t.saved, [{blob: "BLOB", name: "diag-1.zip"}]);
  assert.doesNotMatch(t.doc.els["c-health"].innerHTML, /Preparing/);
});

test("a refused or failed download shows the server's words and saves nothing", async () => {
  const refused = setup({fetch: async () => ({ok: false, status: 401, json: async () => ({error: {code: "bad_token", message: "A valid X-Sutra-Token header is required"}})})});
  await refused.page.start();
  await refused.page.download();
  assert.deepEqual(refused.saved, []);
  assert.match(refused.doc.els["c-health"].innerHTML, /Could not prepare the diagnostics: A valid X-Sutra-Token header is required/);
  const odd = setup({fetch: async () => ({ok: false, status: 502, json: async () => { throw new Error("not json"); }})});
  await odd.page.start();
  await odd.page.download();
  assert.match(odd.doc.els["c-health"].innerHTML, /The app answered 502\./);
  const down = setup({fetch: async () => { throw new Error("offline"); }});
  await down.page.start();
  await down.page.download();
  assert.match(down.doc.els["c-health"].innerHTML, /Could not prepare the diagnostics: offline/);
  assert.equal(down.S.downloading, false);
  const unnamed = setup({fetch: async () => ({ok: true, status: 200, headers: {get: () => ""}, blob: async () => "B"})});
  await unnamed.page.start();
  await unnamed.page.download();
  assert.equal(unnamed.saved[0].name, "sutra-pro-diagnostics.zip");
});

test("a panel is repainted only when its markup changed, and the focused control keeps focus", async () => {
  const t = setup({log: rows(1, 3), routes: {"/api/ops/info": () => ({...INFO, atom_log: {rows: 3, last_seq: 3}})}});
  await t.page.start();
  const sets = t.doc.els["c-log"].sets;
  await t.page.loadMoreLog();
  await t.page.loadMoreLog();
  assert.equal(t.doc.els["c-log"].sets, sets);
  const focused = [];
  t.doc.els["f-state"] = {focus: () => focused.push("f-state")};
  t.doc.activeElement = {id: "f-state"};
  t.doc.els["c-log"].contains = node => node === t.doc.activeElement;
  await change(t.doc, "state", "closed");
  assert.deepEqual(focused, ["f-state"]);
});

test("stop closes the stream and drops the pending refreshes", async () => {
  const t = setup();
  await t.page.start();
  t.events.state.connected.onEvent("usage.recorded", {});
  assert.equal(t.events.state.pending.size, 1);
  t.page.stop();
  assert.equal(t.events.state.closed, true);
  assert.equal(t.events.state.pending.size, 0);
  assert.equal(t.page.isStopped(), true);
});

test("the controller works without an event module: the page still loads", async () => {
  const doc = makeDoc();
  const api = makeApi({"/api/ops/usage": () => REPORT, "/api/connectors/status": () => STATUS, "/api/ops/info": () => ({...INFO, atom_log: {rows: 1, last_seq: 1}}), "/api/ops/doctor": () => DOCTOR, "/api/atoms/log": logRoute(rows(1, 1))});
  const page = CV.create({doc, api, now: () => NOW, format: fmt});
  await page.start();
  assert.match(doc.els["c-usage"].innerHTML, /\$0\.75/);
  page.stop();
});

test("the exports name the periods, the window and the polling interval the page and the server agree on", () => {
  assert.deepEqual(CV.PERIODS.map(p => p[0]), ["today", "7d", "30d", "all"]);
  assert.deepEqual([CV.WINDOW, CV.LOG_PAGE_SIZE, CV.POLL_MS, CV.USAGE_COALESCE_MS, CV.DEFAULT_PERIOD], [1000, 25, 2000, 1000, "7d"]);
  assert.deepEqual(CV.STATES.map(s => s[0]), ["closed", "verify_failed", "abandoned", "refused"]);
});
