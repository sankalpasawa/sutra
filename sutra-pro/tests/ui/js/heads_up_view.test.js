"use strict";
// HeadsUpView (sutra_app/ui/static/js/heads_up_view.js): the Heads up lane and the age of what waits (gap package attention).
// The old app's 14-needs-you.js rules: two lanes, tones ask/warn/err/ok/stop, three FYI rows then "+N more", FYI never counts.
// Run with: node --test tests/ui/js/heads_up_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const HV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/heads_up_view.js"));

const tid = n => "tsk_" + String(n).padStart(12, "0");
const row = (n, kind, extra = {}) => Object.assign({kind, tone: kind === "problem" ? "err" : kind === "quiet" ? "warn" : "ok", task_id: tid(n), dept_id: "web",
  dept_name: "Web", title: "Menu", status: kind === "problem" ? "crashed" : kind === "quiet" ? "running" : "done", text: "Row " + n, outcome: "",
  at: "2026-11-04T10:00:00Z", since_s: 7200, retry: kind === "problem"}, extra);
const Q = (id, kind = "question", extra = {}) => Object.assign({message_id: id, kind, dept_name: "Web", text: "Which?", asked_at: "2026-11-04T10:00:00Z"}, extra);

// Well formed XML, as chat_view.test.js's small reader proves it: every tag closes in order, attributes are quoted once, no stray &.
function wellFormed(html) {
  const TOKEN = /<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<[^>]*>|[^<]+/y;
  const stack = [];
  let pos = 0;
  while (pos < html.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(html);
    assert.ok(m && m.index === pos, "not well formed at " + pos + ": " + html.slice(pos, pos + 60));
    pos = TOKEN.lastIndex;
    if (m[2] === undefined) {
      assert.equal(m[0].startsWith("<"), false, "a malformed tag: " + m[0]);
      assert.equal(/&(?!(?:amp|lt|gt|quot|#39);)/.test(m[0]), false, "a stray &: " + m[0]);
      continue;
    }
    const names = [...m[3].matchAll(/([\w:.-]+)="/g)].map(a => a[1]);
    assert.equal(new Set(names).size, names.length, "an attribute twice on <" + m[2] + ">");
    if (m[1] === "/") assert.equal(stack.pop(), m[2]);
    else if (m[4] !== "/") stack.push(m[2]);
  }
  assert.deepEqual(stack, [], "unclosed tags");
}

test("age words round down to the largest unit, like the server's", () => {
  assert.equal(HV.ageWords(0), "just now");
  assert.equal(HV.ageWords(59), "just now");
  assert.equal(HV.ageWords(60), "1 minute");
  assert.equal(HV.ageWords(7199), "1 hour");
  assert.equal(HV.ageWords(3 * 86400 + 5), "3 days");
  assert.equal(HV.ageWords(-5), "just now");
  assert.equal(HV.ageWords("x"), "just now");
});

test("the age of an ask grows with the time since the read and is marked stale past a day", () => {
  assert.equal(HV.waitedSeconds(Q(1, "question", {waiting_s: 100}), 30500), 130);
  assert.equal(HV.waitedSeconds(Q(1), 1000), null);                                  // the server sent no age (an old server, the fake)
  assert.equal(HV.waitedHtml(Q(1), 0), "");
  assert.equal(HV.waitedHtml(Q(1, "question", {waiting_s: 10}), 0), '<small class="nwait">asked just now</small>');
  assert.equal(HV.waitedHtml(Q(1, "question", {waiting_s: 3 * 86400, stale: true}), 0),
    '<small class="nwait stale" title="Unanswered for more than a day">waiting 3 days</small>');
  assert.match(HV.waitedHtml(Q(1, "question", {waiting_s: 86399, stale: false}), 2000), /class="nwait stale"/);   // it crossed the line since the read
  assert.match(HV.waitedHtml(Q(1, "question", {waiting_s: 3700}), 0), />waiting 1 hour</);
});

test("problems count, quiet and finished never count, and a row marked seen stops counting", () => {
  const items = [row(1, "problem"), row(2, "quiet"), row(3, "finished"), row(4, "problem"), {kind: "other", task_id: tid(5)}, row(6, "problem", {task_id: "bad id"})];
  assert.equal(HV.count([Q(1), Q(2, "approval")], items, {}), 4);
  assert.equal(HV.count([Q(1)], items, {[tid(4)]: true}), 2);
  assert.equal(HV.count(null, null, null), 0);
  const parts = HV.split(items, {[tid(2)]: true, [tid(3)]: true});
  assert.deepEqual([parts.problems.length, parts.quiet.length, parts.finished.length], [2, 1, 0]);    // a quiet row cannot be marked seen
});

test("the summary names each kind in words", () => {
  assert.equal(HV.summary([], [], {}), "");
  assert.equal(HV.summary([Q(1)], [row(1, "problem"), row(2, "problem"), row(3, "finished")], {}), "1 question, 2 to try again");
  assert.equal(HV.summary([Q(1), Q(2), Q(3, "approval")], [], {}), "2 questions, 1 approval");
});

test("the lane draws problems with Try again first, then quiet teams, then three FYI rows and +N more", () => {
  const items = [row(1, "finished"), row(2, "finished"), row(3, "quiet", {text: "Web has gone quiet", since_s: 660}), row(4, "finished"), row(5, "finished"),
    row(6, "problem", {outcome: "The team stopped unexpectedly.", tone: "err"}), row(7, "finished"), row(8, "problem", {tone: "stop"})];
  const html = HV.laneHtml(items, {seen: {}});
  wellFormed(html);
  const order = [...html.matchAll(/data-kind="(\w+)" data-task="(tsk_\d+)"/g)].map(m => m[1] + ":" + m[2].slice(-1));
  assert.deepEqual(order, ["problem:6", "problem:8", "quiet:3", "finished:1", "finished:2", "finished:4"]);
  assert.match(html, /<h3 class="nylane">Heads up<\/h3>/);
  assert.match(html, /class="huitem t-err" data-kind="problem"/);
  assert.match(html, /class="huitem t-stop"/);
  assert.match(html, /<button type="button" data-act="retry-task" data-task="tsk_000000000006">Try again<\/button>/);
  assert.match(html, /<small class="huwhy">The team stopped unexpectedly.<\/small>/);
  assert.match(html, /<small class="huwhen">silent 11 minutes<\/small>/);
  assert.match(html, /<small class="huwhen">2 hours ago<\/small>/);
  assert.match(html, /data-act="headsup-more">\+2 more<\/button>/);
  assert.match(html, /<a class="huopen" href="\/d\/web\/\?view=simple">Open team<\/a>/);
  assert.equal((html.match(/data-act="retry-task"/g) || []).length, 2);                // no Try again on a quiet team or on plain done work
  assert.equal((html.match(/data-act="headsup-seen"/g) || []).length, 5);              // Got it on everything but the quiet team
  const all = HV.laneHtml(items, {seen: {}, more: true});
  assert.equal((all.match(/data-kind="finished"/g) || []).length, 5);
  assert.doesNotMatch(all, /headsup-more/);
});

test("a row marked seen is not drawn, and an empty lane draws nothing", () => {
  assert.equal(HV.laneHtml([], {}), "");
  assert.equal(HV.laneHtml([row(1, "finished")], {seen: {[tid(1)]: true}}), "");
  assert.equal(HV.laneHtml(null), "");
});

test("every word from the wire is escaped and an id that is not an id never reaches an attribute", () => {
  const evil = row(1, "problem", {text: '<img src=x onerror="alert(1)">', outcome: "</small><script>x</script>", dept_id: 'web" onclick="x', tone: "bad<"});
  const html = HV.laneHtml([evil], {});
  wellFormed(html);
  assert.doesNotMatch(html, /<img|<script|onclick=/);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.match(html, /class="huitem t-warn"/);                                        // an unknown tone falls back
  assert.doesNotMatch(html, /huopen/);                                                // a bad team id gets no link
  assert.equal(HV.laneHtml([row(1, "problem", {task_id: '"><b>'})], {}), "");
});

test("Got it marks are kept per browser, dropped for rows that are gone, and storage that throws changes nothing", () => {
  const data = {};
  const storage = {getItem: k => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = v; }};
  assert.deepEqual(HV.loadSeen(storage), {});
  assert.equal(HV.saveSeen(storage, {[tid(1)]: true, [tid(2)]: true, "bad id": true}, [row(1, "finished")]), true);
  assert.deepEqual(JSON.parse(data[HV.SEEN_KEY]), [tid(1)]);
  assert.deepEqual(HV.loadSeen(storage), {[tid(1)]: true});
  data[HV.SEEN_KEY] = "{not json";
  assert.deepEqual(HV.loadSeen(storage), {});
  const broken = {getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }};
  assert.deepEqual(HV.loadSeen(broken), {});
  assert.equal(HV.saveSeen(broken, {[tid(1)]: true}, []), false);
  assert.deepEqual(HV.loadSeen(null), {});
});
