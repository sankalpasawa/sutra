"use strict";
// RecurringView (sutra_app/ui/static/js/recurring_view.js): the Recurring work group of Settings (gap package routines-limits).
// Run with: node --test tests/ui/js/recurring_view.test.js
process.env.TZ = "UTC";                                            // times are read in the browser's local time: pin it for the test
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const RV = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/recurring_view.js"));

const ID = "rec_0123456789ab";
const NOW = Date.UTC(2026, 10, 4, 10, 0);                          // Wed 4 Nov 2026, 10:00 UTC
const rec = (over = {}) => ({
  id: ID, dept_id: "web", dept_name: "Web", text: "Write the pipeline summary", schedule: {every: "weekdays", hour: 9, minute: 0, weekday: 0},
  human: "Every weekday at 9:00 AM (local)", enabled: true, paused_reason: "", next_due_at: "2026-11-05T09:00:00Z", created_at: "2026-11-01T08:00:00Z",
  last_run: null, never_fired_on_schedule: false, ...over,
});
const run = (over = {}) => ({id: 1, due_at: "2026-11-04T09:00:00Z", at: "2026-11-04T09:00:20Z", trigger: "schedule", result: "done", task_id: "tsk_000000000001", folded: 0, reason: "", ...over});
const TEAMS = [{id: "web", name: "Web"}, {id: "sales", name: "Sales"}];
const form = (over = {}) => ({teams: TEAMS, now: NOW, ...over});

function fakeApi(answers = {}) {
  const calls = [];
  const make = method => async (p, body) => {
    calls.push({method, path: p, body});
    const a = answers[method + " " + p];
    if (a instanceof Error) throw a;
    return a === undefined ? {} : a;
  };
  return {get: make("GET"), post: make("POST"), put: make("PUT"), del: make("DELETE"), calls};
}

// ---- words ------------------------------------------------------------------------------------------------------------------------------

test("nextWords reads an ISO time as today, tomorrow, a weekday or a date, in local time", () => {
  assert.equal(RV.nextWords("2026-11-04T15:30:00Z", NOW), "today 3:30 PM");
  assert.equal(RV.nextWords("2026-11-05T09:00:00Z", NOW), "tomorrow 9:00 AM");
  assert.equal(RV.nextWords("2026-11-07T00:05:00Z", NOW), "Sat 12:05 AM");
  assert.equal(RV.nextWords("2026-11-20T12:00:00Z", NOW), "Fri 20 Nov, 12:00 PM");
  for (const bad of ["", "soon", null, undefined, 5]) assert.equal(RV.nextWords(bad, NOW), "", String(bad));
});

test("runWords says what happened to a due time, honestly", () => {
  assert.equal(RV.runWords(run()), "Wed 4 Nov, 9:00 AM: started on schedule, done");
  assert.equal(RV.runWords(run({result: "open_items"})), "Wed 4 Nov, 9:00 AM: started on schedule, done, with open items");
  assert.equal(RV.runWords(run({result: "crashed"})), "Wed 4 Nov, 9:00 AM: started on schedule, ended with a problem");
  assert.equal(RV.runWords(run({result: "waiting"})), "Wed 4 Nov, 9:00 AM: started on schedule, waiting for you");
  assert.equal(RV.runWords(run({trigger: "manual", result: "working"})), "Wed 4 Nov, 9:00 AM: started by you, working");
  assert.equal(RV.runWords(run({trigger: "catch_up", folded: 2, result: "working"})), "Wed 4 Nov, 9:00 AM: started as a catch-up (2 earlier times folded in), working");
  assert.equal(RV.runWords(run({trigger: "catch_up", folded: 1})), "Wed 4 Nov, 9:00 AM: started as a catch-up (1 earlier time folded in), done");
  assert.equal(RV.runWords(run({result: "skipped", reason: "the team is waiting for your answer", task_id: null})),
    "Wed 4 Nov, 9:00 AM: skipped, the team is waiting for your answer");
  assert.equal(RV.runWords(null), "");
});

test("the group's heading can take focus (tabindex -1): home.js leaves the keyboard there when the control it was on is gone", () => {
  assert.match(RV.recurringHtml([], form()), /<h3 id="set-recurring-h" tabindex="-1">Recurring work<\/h3>/);
});

test("a folded count that reached the cap is told as many, not as an exact figure", () => {
  assert.equal(RV.runWords(run({trigger: "catch_up", folded: 71})), "Wed 4 Nov, 9:00 AM: started as a catch-up (71 earlier times folded in), done");
  assert.equal(RV.runWords(run({trigger: "catch_up", folded: 1998})), "Wed 4 Nov, 9:00 AM: started as a catch-up (1998 earlier times folded in), done");
  assert.equal(RV.runWords(run({trigger: "catch_up", folded: 1999})), "Wed 4 Nov, 9:00 AM: started as a catch-up (many earlier times folded in), done");
  assert.equal(RV.runWords(run({trigger: "catch_up", folded: 5000})), "Wed 4 Nov, 9:00 AM: started as a catch-up (many earlier times folded in), done");
});

test("a run held back by a limit is queued and waiting on the limit, never started or working", () => {
  assert.equal(RV.runWords(run({trigger: "manual", result: "held"})), "Wed 4 Nov, 9:00 AM: queued by you, waiting on a limit");
  assert.equal(RV.runWords(run({result: "held"})), "Wed 4 Nov, 9:00 AM: queued on schedule, waiting on a limit");
  assert.equal(RV.runWords(run({trigger: "catch_up", folded: 2, result: "held"})), "Wed 4 Nov, 9:00 AM: queued as a catch-up (2 earlier times folded in), waiting on a limit");
  const html = RV.recurringHtml([rec({last_run: run({trigger: "manual", result: "held"})})], form());
  assert.match(html, /Last: Wed 4 Nov, 9:00 AM: queued by you, waiting on a limit\./);
  assert.doesNotMatch(/<p class="reclast">[^<]*<\/p>/.exec(html)[0], /started|working/);
});

// ---- the group ------------------------------------------------------------------------------------------------------------------------------

test("not loaded yet is said, and an empty list says nothing is scheduled and still offers the form", () => {
  assert.match(RV.recurringHtml(null, form()), /not loaded yet/);
  const empty = RV.recurringHtml([], form());
  assert.match(empty, /data-group="recurring"/);
  assert.match(empty, /Nothing is scheduled yet/);
  assert.match(empty, /data-act="rec-add"/);
  assert.match(empty, /ONE catch-up run starts when Sutra opens, never one per missed time/);
  assert.match(empty, /at most once an hour, in your local time/);
});

test("a row shows the team, the words, the cadence, the next time, the last run and its buttons", () => {
  const html = RV.recurringHtml([rec({last_run: run({result: "working"})})], form());
  assert.match(html, /<b class="recteam">Web<\/b>/);
  assert.match(html, /st-ok">On</);
  assert.match(html, /Every weekday at 9:00 AM \(local\)/);
  assert.match(html, /Next: tomorrow 9:00 AM/);
  assert.match(html, /Write the pipeline summary/);
  assert.match(html, /Last: Wed 4 Nov, 9:00 AM: started on schedule, working\./);
  for (const act of ["rec-run", "rec-toggle", "rec-history", "rec-delete"]) assert.match(html, new RegExp('data-act="' + act + '" data-id="' + ID + '"'));
  assert.match(html, />Pause</);
  assert.doesNotMatch(html, /fired on its own/);
});

test("a paused schedule says why, offers Switch on and shows no next time; a crash pause is in the app's words", () => {
  const html = RV.recurringHtml([rec({enabled: false, next_due_at: null, paused_reason: "Paused after 3 runs in a row ended with a problem. Look at the team's last attempts, then switch it on again."})], form());
  assert.match(html, /st-signed_out">Paused</);
  assert.match(html, /Paused after 3 runs in a row ended with a problem/);
  assert.match(html, />Switch on</);
  assert.doesNotMatch(html, /Next:/);
  const byOwner = RV.recurringHtml([rec({enabled: false, next_due_at: null, paused_reason: ""})], form());
  assert.doesNotMatch(byOwner, /class="recwhy"/);
});

test("a schedule that only ever ran by hand carries the note that a green manual run proves nothing", () => {
  assert.match(RV.recurringHtml([rec({never_fired_on_schedule: true, last_run: run({trigger: "manual", result: "done"})})], form()), /has not fired on its own yet/);
  assert.match(RV.recurringHtml([rec()], form()), /Has not run yet/);
});

test("Remove asks twice; history opens a row and lists at most five runs", () => {
  const first = RV.recurringHtml([rec()], form());
  assert.match(first, />Remove</);
  assert.doesNotMatch(first, /Yes, remove/);
  const asking = RV.recurringHtml([rec()], form({confirm: ID}));
  assert.match(asking, /Remove it\?/);
  assert.match(asking, /data-act="rec-delete-yes" data-id="rec_0123456789ab"/);
  assert.match(asking, /data-act="rec-delete-no"/);
  const runs = [1, 2, 3, 4, 5, 6, 7].map(n => run({id: n}));
  const open = RV.recurringHtml([rec()], form({open: {[ID]: runs}}));
  assert.match(open, /aria-expanded="true">Hide history</);
  assert.equal((open.match(/<li data-result=/g) || []).length, 5);
  assert.match(RV.recurringHtml([rec()], form({open: {[ID]: []}})), /No run yet/);
  assert.match(RV.recurringHtml([rec()], form({open: {}})), /aria-expanded="false">History</);
});

test("a row's own refusal is shown inside the row, and busy disables the buttons that change things", () => {
  const html = RV.recurringHtml([rec()], form({error: {[ID]: "The team is still working on its current task. Try again when it is free"}, busy: true}));
  assert.match(html, /role="alert">The team is still working/);
  assert.match(html, /data-act="rec-run"[^>]* disabled/);
  assert.match(html, /data-act="rec-toggle"[^>]* disabled/);
});

test("every word from the wire is escaped, and a row with a bad id is not drawn", () => {
  const evil = '<img src=x onerror="alert(1)">';
  const html = RV.recurringHtml([rec({dept_name: evil, text: evil, human: evil, paused_reason: evil, enabled: false, last_run: run({reason: evil, result: "skipped"})})],
    form({teams: [{id: "web", name: evil}], draft: {text: evil, dept_id: "web", every: "weekdays"}, error: {"": evil}, open: {[ID]: [run({reason: evil, result: "skipped"})]}}));
  assert.equal(html.includes("<img"), false);
  assert.match(html, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.equal(RV.recurringHtml([rec({id: '"><script>'})], form()).includes("<script>"), false);
  assert.match(RV.recurringHtml([rec({id: "nope"})], form()), /Nothing is scheduled yet/);
});

// ---- the add form -------------------------------------------------------------------------------------------------------------------------

test("the add form follows the cadence: a time for day, a day and a time for week, a minute for hour", () => {
  const day = RV.recurringHtml([], form({draft: {every: "day"}}));
  assert.match(day, /data-input="rec_time" value="09:00"/);
  assert.doesNotMatch(day, /rec_weekday|rec_minute/);
  const week = RV.recurringHtml([], form({draft: {every: "week", weekday: "4", time: "08:30"}}));
  assert.match(week, /<option value="4" selected>Friday<\/option>/);
  assert.match(week, /data-input="rec_time" value="08:30"/);
  const hour = RV.recurringHtml([], form({draft: {every: "hour", minute: "15"}}));
  assert.match(hour, /data-input="rec_minute" value="15"/);
  assert.doesNotMatch(hour, /rec_time/);
  for (const html of [day, week, hour]) {
    assert.match(html, /<option value="hour"/);
    assert.doesNotMatch(html, /minutes?<\/option>|seconds?<\/option>/);                                    // no cadence below an hour is offered
  }
});

test("the team select lists the teams, keeps the chosen one and says so when there is no team", () => {
  const html = RV.recurringHtml([], form({draft: {dept_id: "sales"}}));
  assert.match(html, /<option value="sales" selected>Sales<\/option>/);
  assert.match(html, /<option value="web">Web<\/option>/);
  assert.match(RV.recurringHtml([], form({teams: []})), /No team yet/);
});

test("scheduleBody builds the body the server wants and refuses what it would refuse, before any request", () => {
  const ok = RV.scheduleBody({dept_id: "web", text: "  Write it  ", every: "weekdays", time: "09:05"});
  assert.deepEqual(ok, {ok: true, body: {dept_id: "web", text: "Write it", schedule: {every: "weekdays", hour: 9, minute: 5}}, error: ""});
  assert.deepEqual(RV.scheduleBody({dept_id: "web", text: "x", every: "week", time: "21:30", weekday: "4"}).body.schedule, {every: "week", hour: 21, minute: 30, weekday: 4});
  assert.deepEqual(RV.scheduleBody({dept_id: "web", text: "x", every: "hour", minute: "15"}).body.schedule, {every: "hour", minute: 15});
  assert.deepEqual(RV.scheduleBody({dept_id: "web", text: "x", every: "day", time: "00:00"}).body.schedule, {every: "day", hour: 0, minute: 0});
  assert.match(RV.scheduleBody({dept_id: "", text: "x"}).error, /Choose the team/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "   "}).error, /Write what the team should do/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "x".repeat(4001)}).error, /under 4000 characters/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "x", every: "minute"}).error, /at most once an hour/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "x", every: "day", time: "9:00"}).error, /time of day, like 09:00/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "x", every: "day", time: ""}).error, /time of day/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "x", every: "hour", minute: "60"}).error, /0 to 59/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "x", every: "hour", minute: "-1"}).error, /0 to 59/);
  assert.match(RV.scheduleBody({dept_id: "web", text: "x", every: "week", time: "09:00", weekday: "7"}).error, /day of the week/);
  assert.equal(RV.scheduleBody({dept_id: "web", text: "x"}).ok, true);                                     // the defaults are weekdays at 09:00
});

// ---- the calls ----------------------------------------------------------------------------------------------------------------------------

test("create posts the checked body and sends nothing for a form it refuses", async () => {
  const api = fakeApi({"POST /api/recurring": rec()});
  const made = await RV.create(api, {dept_id: "web", text: "Write it", every: "day", time: "07:00"});
  assert.equal(made.ok, true);
  assert.deepEqual(api.calls[0], {method: "POST", path: "/api/recurring", body: {dept_id: "web", text: "Write it", schedule: {every: "day", hour: 7, minute: 0}}});
  const refused = await RV.create(api, {dept_id: "", text: "x"});
  assert.equal(refused.ok, false);
  assert.equal(api.calls.length, 1);
});

test("toggle flips the switch, run now and remove use their routes, history asks for five", async () => {
  const api = fakeApi({["PUT /api/recurring/" + ID]: rec({enabled: false}), ["POST /api/recurring/" + ID + "/run"]: run({trigger: "manual"}),
    ["GET /api/recurring/" + ID + "/runs"]: [run()]});
  await RV.toggle(api, rec({enabled: true}));
  await RV.toggle(api, rec({enabled: false}));
  assert.deepEqual(api.calls.map(c => c.body), [{enabled: false}, {enabled: true}]);
  assert.equal((await RV.runNow(api, ID)).run.trigger, "manual");
  assert.equal((await RV.remove(api, ID)).ok, true);
  assert.equal((await RV.history(api, ID)).runs.length, 1);
  assert.deepEqual(api.calls.slice(2).map(c => [c.method, c.path]), [["POST", "/api/recurring/" + ID + "/run"], ["DELETE", "/api/recurring/" + ID], ["GET", "/api/recurring/" + ID + "/runs"]]);
  assert.deepEqual(api.calls[4].body, {limit: 5});
});

test("an id that is not an id never reaches the network, and a server refusal comes back in its own words", async () => {
  const api = fakeApi({["POST /api/recurring/" + ID + "/run"]: Object.assign(new Error("The team is still working on its current task. Try again when it is free"), {status: 409})});
  for (const bad of ["", "web", "rec_../x", "rec_0123456789abc", null]) {
    assert.equal((await RV.runNow(api, bad)).ok, false);
    assert.equal((await RV.remove(api, bad)).ok, false);
    assert.equal((await RV.history(api, bad)).ok, false);
  }
  assert.equal((await RV.toggle(api, {id: "x", enabled: true})).ok, false);
  assert.equal(api.calls.length, 0);
  const busy = await RV.runNow(api, ID);
  assert.deepEqual([busy.ok, busy.error], [false, "The team is still working on its current task. Try again when it is free"]);
});

test("load returns the list, or says it could not", async () => {
  assert.deepEqual((await RV.load(fakeApi({"GET /api/recurring": [rec()]}))).list.length, 1);
  const down = await RV.load(fakeApi({"GET /api/recurring": new Error("")}));
  assert.deepEqual([down.ok, down.list, down.error], [false, null, "That did not work. Try again."]);
  assert.equal((await RV.load(fakeApi({"GET /api/recurring": {not: "a list"}}))).ok, false);
});
