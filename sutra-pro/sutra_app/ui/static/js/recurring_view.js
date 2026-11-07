/* recurring_view.js - the Recurring work group of Settings: a team's standing task on a schedule (gap package routines-limits;
   docs/notes/GAP2-routines-limits.md; the old app's Routines page).

   Strings in, strings out, plus the few small flows that talk to the server through an `api` the caller hands in (SutraCtx.api, or a fake in a test): this
   file touches no DOM and no timer, so `node --test` runs all of it. Every word from the wire goes through esc(). Times are read in the browser's local time,
   which is the owner's: the server's schedule words always say "(local)".

     recurringHtml(list, form)     the group from GET /api/recurring. A row per schedule: the team, its words, the cadence in words, on or paused (and why),
                                   the next due time, the last run, a "has not fired on its own yet" note, and Run now, Pause or Switch on, History and Remove
                                   (asked twice). Under the rows the add form. form {teams, draft, open, confirm, busy, error, saved}:
                                   teams [{id, name}], draft {dept_id, text, every, time, minute, weekday}, open {id: runs[]} for the rows whose history is shown,
                                   confirm the id waiting for its second click, error {id|"": sentence}
     scheduleBody(draft)           {ok, body, error}: the POST body from the add form, checked before any request is made
     runWords(run)                 one history line: "Wed 4 Nov, 9:00 AM: started on schedule, done" / "... skipped: the team is waiting for your answer"
     nextWords(iso, nowMs)         "today 9:00 AM", "tomorrow 9:00 AM", "Fri 9:00 AM" from an ISO time, in local time
     load(api) / create(api, draft) / toggle(api, rec) / runNow(api, id) / remove(api, id) / history(api, id)    -> {ok, ..., error}

   Buttons carry data-act: rec-add, rec-run, rec-toggle, rec-history, rec-delete, rec-delete-yes, rec-delete-no (data-id); the cadence is select[data-rec-every].
   A classic script with ONE global, RecurringView; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (finite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();

  const PATH = "/api/recurring";
  const ID = /^rec_[0-9a-f]{12}$/;
  const HM = /^([01]\d|2[0-3]):([0-5]\d)$/;
  const MAX_TEXT = 4000;
  const EVERY = [["hour", "Every hour"], ["day", "Every day"], ["weekdays", "Every weekday"], ["week", "Every week"]];
  const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const SHORT_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];                 // Date.getDay() order
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const RESULT = {skipped: "skipped", working: "working", waiting: "waiting for you", done: "done", open_items: "done, with open items", crashed: "ended with a problem", stopped: "stopped"};
  const TRIGGER = {schedule: "on schedule", catch_up: "as a catch-up", manual: "by you"};                 // after "started "
  const NOTE = "A team's standing task. At each due time the team gets an ordinary task with these words, at most once an hour, in your local time. " +
    "If the app was closed or the machine asleep, ONE catch-up run starts when Sutra opens, never one per missed time. A team that is still working, or waiting for you, " +
    "skips that time and the history says why. A schedule that ends with a problem three times in a row pauses itself.";

  /* ---------------------------------------------------------------- words */
  const clock12 = d => {
    const h = d.getHours();
    return (h % 12 || 12) + ":" + String(d.getMinutes()).padStart(2, "0") + " " + (h < 12 ? "AM" : "PM");
  };

  function parse(iso) {
    const ms = typeof iso === "string" ? Date.parse(iso) : NaN;
    return finite(ms) ? new Date(ms) : null;
  }

  function nextWords(iso, nowMs) {
    const d = parse(iso);
    if (d === null) return "";
    const now = new Date(finite(nowMs) ? nowMs : Date.now());
    const day = x => Date.UTC(x.getFullYear(), x.getMonth(), x.getDate());
    const apart = Math.round((day(d) - day(now)) / 86400000);
    const at = clock12(d);
    if (apart === 0) return "today " + at;
    if (apart === 1) return "tomorrow " + at;
    if (apart > 1 && apart < 7) return SHORT_DAYS[d.getDay()] + " " + at;
    return SHORT_DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()] + ", " + at;
  }

  function dueWords(iso) {
    const d = parse(iso);
    return d === null ? "" : SHORT_DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()] + ", " + clock12(d);
  }

  function runWords(run) {
    if (!isObj(run)) return "";
    const result = Object.prototype.hasOwnProperty.call(RESULT, run.result) ? RESULT[run.result] : "";
    const how = Object.prototype.hasOwnProperty.call(TRIGGER, run.trigger) ? TRIGGER[run.trigger] : "";
    const when = dueWords(run.due_at);
    const why = clean(run.reason);
    if (run.result === "skipped") return (when ? when + ": " : "") + "skipped" + (why ? ", " + why : "");
    const folded = finite(run.folded) && run.folded > 0 ? " (" + run.folded + " earlier time" + (run.folded === 1 ? "" : "s") + " folded in)" : "";
    return (when ? when + ": " : "") + "started " + how + folded + (result ? ", " + result : "");
  }

  /* ---------------------------------------------------------------- the rows */
  function runList(runs) {
    const list = Array.isArray(runs) ? runs.filter(isObj).slice(0, 5) : [];
    if (list.length === 0) return '<p class="sethint">No run yet.</p>';
    return '<ol class="recruns">' + list.map(r => '<li data-result="' + esc(clean(r.result)) + '">' + esc(runWords(r)) + "</li>").join("") + "</ol>";
  }

  function rowHtml(rec, form) {
    const id = ID.test(clean(rec.id)) ? clean(rec.id) : "";
    if (id === "") return "";
    const busy = form.busy === true ? " disabled" : "";
    const open = isObj(form.open) && Array.isArray(form.open[id]);
    const err = isObj(form.error) && form.error[id] ? '<p class="seterr" role="alert">' + esc(form.error[id]) + "</p>" : "";
    const on = rec.enabled === true;
    const state = on ? "On" : "Paused";
    const why = !on && clean(rec.paused_reason) ? '<p class="recwhy">' + esc(clean(rec.paused_reason)) + "</p>" : "";
    const next = on && clean(rec.next_due_at) ? '<span class="recnext">Next: ' + esc(nextWords(rec.next_due_at, form.now)) + "</span>" : "";
    const never = rec.never_fired_on_schedule === true
      ? '<p class="sethint">It has not fired on its own yet: a run you started by hand does not prove the schedule works.</p>' : "";
    const last = isObj(rec.last_run) ? '<p class="reclast">Last: ' + esc(runWords(rec.last_run)) + ".</p>" : '<p class="reclast">Has not run yet.</p>';
    const asking = form.confirm === id;
    return '<li class="recrow" data-id="' + esc(id) + '" data-enabled="' + (on ? "true" : "false") + '">' +
      '<div class="rechead"><b class="recteam">' + esc(clean(rec.dept_name) || clean(rec.dept_id)) + '</b><span class="setchip st-' + (on ? "ok" : "signed_out") + '">' + state + "</span>" +
      '<span class="recwhen">' + esc(clean(rec.human)) + "</span>" + next + "</div>" +
      '<p class="rectext">' + esc(clean(rec.text)) + "</p>" + why + last + never + err +
      '<div class="setacts">' +
      '<button type="button" class="ghost" data-act="rec-run" data-id="' + esc(id) + '"' + busy + ">Run now</button>" +
      '<button type="button" class="ghost" data-act="rec-toggle" data-id="' + esc(id) + '"' + busy + ">" + (on ? "Pause" : "Switch on") + "</button>" +
      '<button type="button" class="ghost" data-act="rec-history" data-id="' + esc(id) + '" aria-expanded="' + (open ? "true" : "false") + '">' + (open ? "Hide history" : "History") + "</button>" +
      (asking
        ? '<span class="recsure">Remove it? <button type="button" class="ghost" data-act="rec-delete-yes" data-id="' + esc(id) + '"' + busy + '>Yes, remove</button> ' +
          '<button type="button" class="ghost" data-act="rec-delete-no" data-id="' + esc(id) + '">No</button></span>'
        : '<button type="button" class="ghost" data-act="rec-delete" data-id="' + esc(id) + '">Remove</button>') +
      "</div>" + (open ? runList(form.open[id]) : "") + "</li>";
  }

  /* ---------------------------------------------------------------- the add form */
  const DEFAULT_DRAFT = {dept_id: "", text: "", every: "weekdays", time: "09:00", minute: "0", weekday: "0"};

  function scheduleBody(draft) {
    const d = Object.assign({}, DEFAULT_DRAFT, isObj(draft) ? draft : {});
    const dept = clean(d.dept_id);
    const text = String(d.text === undefined || d.text === null ? "" : d.text).trim();
    if (dept === "") return {ok: false, body: null, error: "Choose the team."};
    if (text === "") return {ok: false, body: null, error: "Write what the team should do each time."};
    if (text.length > MAX_TEXT) return {ok: false, body: null, error: "Keep it under " + MAX_TEXT + " characters."};
    const every = clean(d.every);
    if (!EVERY.some(e => e[0] === every)) return {ok: false, body: null, error: "A schedule runs at most once an hour: choose hour, day, weekday or week."};
    const schedule = {every};
    if (every === "hour") {
      const m = clean(d.minute);
      if (!/^\d{1,2}$/.test(m) || Number(m) > 59) return {ok: false, body: null, error: "The minute past the hour is from 0 to 59."};
      schedule.minute = Number(m);
    } else {
      const t = HM.exec(clean(d.time));
      if (!t) return {ok: false, body: null, error: "Choose a time of day, like 09:00."};
      schedule.hour = Number(t[1]);
      schedule.minute = Number(t[2]);
      if (every === "week") {
        const w = clean(d.weekday);
        if (!/^[0-6]$/.test(w)) return {ok: false, body: null, error: "Choose the day of the week."};
        schedule.weekday = Number(w);
      }
    }
    return {ok: true, body: {dept_id: dept, text, schedule}, error: ""};
  }

  function addHtml(form) {
    const d = Object.assign({}, DEFAULT_DRAFT, isObj(form.draft) ? form.draft : {});
    const teams = (Array.isArray(form.teams) ? form.teams : []).filter(t => isObj(t) && clean(t.id) !== "");
    const busy = form.busy === true ? " disabled" : "";
    const every = EVERY.some(e => e[0] === d.every) ? d.every : "weekdays";
    const err = isObj(form.error) && form.error[""] ? '<p class="seterr setgen" role="alert">' + esc(form.error[""]) + "</p>" : "";
    if (teams.length === 0) return '<h4 class="setsub">New standing task</h4><p class="setempty">No team yet. Tell Sutra what you need in the chat and a team appears.</p>';
    return '<h4 class="setsub">New standing task</h4><div class="setfields recform">' +
      '<div class="setfield"><label class="setlabel" for="setf-rec-team">Team</label><select id="setf-rec-team" data-input="rec_dept">' +
      '<option value="">Choose a team</option>' + teams.map(t => '<option value="' + esc(clean(t.id)) + '"' + (clean(t.id) === clean(d.dept_id) ? " selected" : "") + ">" + esc(clean(t.name) || clean(t.id)) + "</option>").join("") +
      "</select></div>" +
      '<div class="setfield"><label class="setlabel" for="setf-rec-every">How often</label><select id="setf-rec-every" data-rec-every data-input="rec_every">' +
      EVERY.map(e => '<option value="' + e[0] + '"' + (e[0] === every ? " selected" : "") + ">" + e[1] + "</option>").join("") + "</select></div>" +
      (every === "week" ? '<div class="setfield"><label class="setlabel" for="setf-rec-day">On</label><select id="setf-rec-day" data-input="rec_weekday">' +
        DAYS.map((n, i) => '<option value="' + i + '"' + (String(i) === clean(d.weekday) ? " selected" : "") + ">" + n + "</option>").join("") + "</select></div>" : "") +
      (every === "hour"
        ? '<div class="setfield"><label class="setlabel" for="setf-rec-minute">Minute past the hour</label><input type="number" min="0" max="59" step="1" inputmode="numeric" id="setf-rec-minute" data-input="rec_minute" value="' + esc(clean(d.minute)) + '"></div>'
        : '<div class="setfield"><label class="setlabel" for="setf-rec-time">At (your local time)</label><input type="time" id="setf-rec-time" data-input="rec_time" value="' + esc(clean(d.time)) + '"></div>') +
      "</div>" +
      '<div class="setfield recwords"><label class="setlabel" for="setf-rec-text">What the team does each time</label>' +
      '<textarea id="setf-rec-text" data-input="rec_text" rows="3" maxlength="' + MAX_TEXT + '" placeholder="Write the pipeline summary for the week">' + esc(String(d.text === undefined || d.text === null ? "" : d.text)) + "</textarea></div>" +
      err + '<div class="setacts"><button type="button" class="ghost" data-act="rec-add"' + busy + ">Add</button>" +
      '<span class="setstatus" role="status">' + (form.saved === true ? "Added." : "") + "</span></div>";
  }

  function recurringHtml(list, form) {
    const f = isObj(form) ? form : {};
    const head = '<section class="setgrp" data-group="recurring" aria-labelledby="set-recurring-h"><h3 id="set-recurring-h">Recurring work</h3><p class="setnote">' + esc(NOTE) + "</p>";
    if (!Array.isArray(list)) return head + '<p class="setempty">The standing tasks are not loaded yet.</p></section>';
    const rows = list.filter(isObj).map(r => rowHtml(r, f)).filter(Boolean);
    return head + (rows.length ? '<ul class="reclist">' + rows.join("") + "</ul>" : '<p class="setempty">Nothing is scheduled yet.</p>') + addHtml(f) + "</section>";
  }

  /* ---------------------------------------------------------------- the calls */
  const said = e => clean(e && e.message) || "That did not work. Try again.";
  const okId = id => (ID.test(clean(id)) ? clean(id) : "");

  async function load(api) {
    try {
      const answer = await api.get(PATH);
      return {ok: Array.isArray(answer), list: Array.isArray(answer) ? answer : null, error: ""};
    } catch (e) {
      return {ok: false, list: null, error: said(e)};
    }
  }

  async function create(api, draft) {
    const made = scheduleBody(draft);
    if (!made.ok) return {ok: false, rec: null, error: made.error};
    try { return {ok: true, rec: await api.post(PATH, made.body), error: ""}; } catch (e) { return {ok: false, rec: null, error: said(e)}; }
  }

  async function toggle(api, rec) {
    const id = isObj(rec) ? okId(rec.id) : "";
    if (id === "") return {ok: false, rec: null, error: "That schedule is not known."};
    try { return {ok: true, rec: await api.put(PATH + "/" + id, {enabled: rec.enabled !== true}), error: ""}; } catch (e) { return {ok: false, rec: null, error: said(e)}; }
  }

  async function runNow(api, id) {
    if (okId(id) === "") return {ok: false, run: null, error: "That schedule is not known."};
    try { return {ok: true, run: await api.post(PATH + "/" + okId(id) + "/run"), error: ""}; } catch (e) { return {ok: false, run: null, error: said(e)}; }
  }

  async function remove(api, id) {
    if (okId(id) === "") return {ok: false, error: "That schedule is not known."};
    try { await api.del(PATH + "/" + okId(id)); return {ok: true, error: ""}; } catch (e) { return {ok: false, error: said(e)}; }
  }

  async function history(api, id) {
    if (okId(id) === "") return {ok: false, runs: [], error: "That schedule is not known."};
    try {
      const runs = await api.get(PATH + "/" + okId(id) + "/runs", {limit: 5});
      return {ok: Array.isArray(runs), runs: Array.isArray(runs) ? runs : [], error: ""};
    } catch (e) {
      return {ok: false, runs: [], error: said(e)};
    }
  }

  const RecurringView = {recurringHtml, scheduleBody, runWords, nextWords, load, create, toggle, runNow, remove, history, PATH, DEFAULT_DRAFT};
  if (typeof module === "object" && module !== null && module.exports) module.exports = RecurringView;
  else root.RecurringView = RecurringView;
})(globalThis);
