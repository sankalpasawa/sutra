/* limits_view.js - the Limits and Notifications groups of Settings, and the one line the Needs strip shows when a limit is near (gap package
   routines-limits; docs/notes/GAP2-routines-limits.md; the old app's shadow budget banner, plan-window guard and quiet hours).

   Strings in, strings out, plus the few small flows that talk to the server through an `api` the caller hands in (SutraCtx.api, or a fake in a test):
   this file touches no DOM and no timer, so `node --test` runs all of it. Every word from the wire goes through esc().

     limitsHtml(limits, form)    the Limits group from GET /api/limits: the monthly limit (a field, the month so far as a meter, one honest sentence about
                                 what the dollars are), the plan-window guard (a switch, what the windows say, Continue). form {raw, error, busy, saved}
     noticesHtml(prefs, form)    the Notifications group from GET /api/ops/attention: quiet hours (two times) and the cap on finished notices.
                                 form {start, end, nudges, error, busy, saved} (what the owner typed is kept beside a refusal)
     stripHtml(limits)           the lines of the Needs strip: the monthly limit from 80 %, the plan window from 70 %, with Continue while the guard holds work.
                                 "" when nothing is near. Never counted on the badge: it is a state, not a question.
     parseLimit(raw)             {ok, value, error}: "" or 0 clears (value null); "10", "12.50" and "$1,250" are dollars; anything else says why
     noticesBody(form)           {ok, body, error}: the PUT body of /api/ops/attention from what was typed (both times or neither; start and end differ)
     load(api, {notices})        {limits, notices}: both reads (notices: false reads the limits only), a failed one is null
     saveLimit(api, raw) / saveGuard(api, enabled) / continueGuard(api) / saveNotices(api, form)    -> {ok, state|prefs, error}

   Buttons carry data-act: save-limit, clear-limit, guard-continue, save-notices, clear-quiet; the switch is input[data-guard]. A classic script with ONE
   global, LimitsView; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (finite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();

  const LIMITS_PATH = "/api/limits";
  const ATTENTION_PATH = "/api/ops/attention";
  const MAX_LIMIT = 100000;
  const MAX_NUDGES = 10;
  const HM = /^([01]\d|2[0-3]):([0-5]\d)$/;
  const BAD_AMOUNT = "Type a dollar amount like 10 or 12.50, or leave it empty for no limit.";
  const SPEND_NOTE = "A guard for the time you are away: when the month's spending reaches the limit, new tasks wait and a task already running finishes. " +
    "The dollars are an estimate at Claude's list price and count known dollars only. Codex calls carry no dollar figure, so on a subscription your real limit is your plan's quota.";
  const GUARD_NOTE = "Plan windows are the 5-hour and weekly limits your Claude and Codex plans report. Sutra warns from 70 %. When this switch is on, new team runs wait " +
    "from 80 % and one Continue lets them proceed until that window resets. A run already going is never stopped. With no figure yet, nothing waits.";
  const NOTICE_NOTE = "Desktop notices only reach you while Sutra is in the background. During quiet hours none is sent, but the count in the tab title and in the " +
    "Needs you strip stays. A notice that a team finished obeys the cap; a question, an approval and a problem are never capped.";

  /* ---------------------------------------------------------------- numbers and words */
  function parseLimit(raw) {
    const t = clean(raw).replace(/^\$/, "").replace(/,/g, "");
    if (t === "") return {ok: true, value: null, error: ""};
    if (!/^\d+(\.\d{1,2})?$/.test(t)) return {ok: false, value: null, error: BAD_AMOUNT};
    const n = Number(t);
    if (n === 0) return {ok: true, value: null, error: ""};
    if (n > MAX_LIMIT) return {ok: false, value: null, error: "The most is $100,000."};
    return {ok: true, value: n, error: ""};
  }

  const shownLimit = v => (finite(v) && v > 0 ? String(v) : "");
  const tone = level => (level === "over" || level === "hold" ? "bad" : (level === "warn" ? "warn" : "ok"));

  function meter(spend) {
    const pct = finite(spend.pct) ? spend.pct : 0;
    const width = Math.max(0, Math.min(100, Math.round(pct * 100)));
    return '<div class="pmeter" role="group" aria-label="Spending this month"><div class="pmw" data-sev="' + tone(spend.level) + '">' +
      '<span class="pml">This month</span><span class="pmp">' + width + '%</span><span class="pmr">' + esc(clean(spend.month)) + "</span>" +
      '<span class="pmbar" role="img" aria-label="' + width + ' percent of the monthly limit"><i style="width:' + width + '%"></i></span></div></div>';
  }

  /* ---------------------------------------------------------------- the Limits group */
  function guardWords(guard) {
    if (guard.level === "none") return "No plan window figure yet. The guard stays out of the way until a model has answered once.";
    if (guard.level === "ok") return "The plan windows have room.";
    const line = clean(guard.line);
    if (guard.holding) return line + ". New team runs wait. Press Continue to let them proceed until it resets.";
    if (guard.level === "hold" && isObj(guard.top) && guard.top.continued === true) return line + ". Continuing: work proceeds until that window resets.";
    if (guard.level === "hold" && guard.enabled !== true) return line + ". The guard is off, so nothing waits.";
    return line + ".";
  }

  function limitsHtml(limits, form) {
    const f = isObj(form) ? form : {};
    const head = '<section class="setgrp" data-group="limits" aria-labelledby="set-limits-h"><h3 id="set-limits-h">Limits</h3>';
    if (!isObj(limits) || !isObj(limits.spend) || !isObj(limits.guard)) return head + '<p class="setempty">The limits are not loaded yet.</p></section>';
    const spend = limits.spend;
    const guard = limits.guard;
    const has = finite(spend.limit) && spend.limit > 0;
    const typed = typeof f.raw === "string" ? f.raw : shownLimit(spend.limit);
    const unpriced = finite(spend.unpriced_calls) && spend.unpriced_calls > 0
      ? '<p class="sethint">' + esc(spend.unpriced_calls) + " call" + (spend.unpriced_calls === 1 ? "" : "s") + " this month had no dollar figure and " + (spend.unpriced_calls === 1 ? "is" : "are") + " not counted.</p>" : "";
    return head +
      '<h4 class="setsub">Monthly spending limit</h4><p class="setnote">' + esc(SPEND_NOTE) + "</p>" +
      '<div class="setfield" data-field="monthly_usd"><label class="setlabel" for="setf-monthly">Limit in dollars (empty means no limit)</label>' +
      '<input type="text" inputmode="decimal" id="setf-monthly" data-input="monthly_usd" autocomplete="off" value="' + esc(typed) + '" placeholder="no limit">' +
      '<button type="button" class="ghost" data-act="save-limit"' + (f.busy === true ? " disabled" : "") + ">Save limit</button>" +
      (has ? '<button type="button" class="ghost" data-act="clear-limit"' + (f.busy === true ? " disabled" : "") + ">No limit</button>" : "") +
      (f.error ? '<span class="seterr" role="alert">' + esc(f.error) + "</span>" : "") + "</div>" +
      (has ? '<p class="setlimline" data-level="' + esc(spend.level) + '">' + esc(clean(spend.line)) + "</p>" + meter(spend) : "") + unpriced +
      '<h4 class="setsub">Plan-window guard</h4><p class="setnote">' + esc(GUARD_NOTE) + "</p>" +
      '<div class="setfield" data-field="guard_enabled"><label class="setlabel" for="setf-guard">' +
      '<input type="checkbox" id="setf-guard" data-guard' + (guard.enabled === true ? " checked" : "") + (f.busy === true ? " disabled" : "") +
      "> Hold new team runs when a plan window is at 80 % or more</label></div>" +
      '<p class="setlimline" data-level="' + esc(guard.level) + '">' + esc(guardWords(guard)) + "</p>" +
      (guard.holding === true ? '<div class="setacts"><button type="button" class="ghost" data-act="guard-continue"' + (f.busy === true ? " disabled" : "") + ">Continue</button></div>" : "") +
      '<div class="setacts"><span class="setstatus" role="status">' + (f.saved === true ? "Saved." : "") + "</span></div></section>";
  }

  /* ---------------------------------------------------------------- the strip */
  function stripHtml(limits) {
    if (!isObj(limits)) return "";
    const lines = [];
    const spend = isObj(limits.spend) ? limits.spend : {};
    const guard = isObj(limits.guard) ? limits.guard : {};
    if ((spend.level === "warn" || spend.level === "over") && clean(spend.line) !== "") {
      lines.push('<p class="nylimit" data-level="' + tone(spend.level) + '">' + esc(clean(spend.line)) + "</p>");
    }
    if ((guard.level === "warn" || guard.level === "hold") && clean(guard.line) !== "") {
      const stop = guard.holding === true;
      lines.push('<p class="nylimit" data-level="' + (stop ? "bad" : "warn") + '">' + esc(clean(guard.line) + (stop ? ". New team runs wait." : "")) +
        (stop ? ' <button type="button" class="linkbtn" data-act="guard-continue">Continue</button>' : "") + "</p>");
    }
    return lines.join("");
  }

  /* ---------------------------------------------------------------- the Notifications group */
  function noticesBody(form) {
    const f = isObj(form) ? form : {};
    const start = clean(f.start);
    const end = clean(f.end);
    const body = {};
    if (start === "" && end === "") body.quiet_hours = null;
    else if (start === "" || end === "") return {ok: false, body: null, error: "Choose both times for quiet hours, or neither."};
    else if (!HM.test(start) || !HM.test(end)) return {ok: false, body: null, error: "A time of day is like 21:00."};
    else if (start === end) return {ok: false, body: null, error: "Quiet hours that start and end at the same time could mean all day or no time at all: choose different times."};
    else body.quiet_hours = {start, end};
    const n = clean(f.nudges);
    // Above the ceiling is refused, whatever its length: the field used to turn 11 to 999 into 10 and say "Saved." but refuse 1000 (QA firstrun-settings).
    if (!/^\d{1,3}$/.test(n) || Number(n) > MAX_NUDGES) return {ok: false, body: null, error: "The cap is a whole number from 0 to " + MAX_NUDGES + "."};
    body.nudges_per_hour = Number(n);
    return {ok: true, body, error: ""};
  }

  function noticesHtml(prefs, form) {
    const f = isObj(form) ? form : {};
    const head = '<section class="setgrp" data-group="notices" aria-labelledby="set-notices-h"><h3 id="set-notices-h">Notifications</h3>';
    if (!isObj(prefs)) return head + '<p class="setempty">The notification settings are not loaded yet.</p></section>';
    const quiet = isObj(prefs.quiet_hours) ? prefs.quiet_hours : {};
    const start = typeof f.start === "string" ? f.start : clean(quiet.start);
    const end = typeof f.end === "string" ? f.end : clean(quiet.end);
    const nudges = typeof f.nudges === "string" ? f.nudges : (finite(prefs.nudges_per_hour) ? String(prefs.nudges_per_hour) : "");
    const max = finite(prefs.max_nudges_per_hour) ? prefs.max_nudges_per_hour : MAX_NUDGES;
    return head + '<p class="setnote">' + esc(NOTICE_NOTE) + "</p>" +
      '<div class="setfields">' +
      '<div class="setfield" data-field="quiet_hours"><span class="setlabel" id="setf-quiet-l">Quiet hours (your local time)</span>' +
      '<span role="group" aria-labelledby="setf-quiet-l"><label>From <input type="time" data-input="quiet_start" value="' + esc(start) + '"></label> ' +
      '<label>to <input type="time" data-input="quiet_end" value="' + esc(end) + '"></label></span>' +
      '<span class="sethint">' + (prefs.quiet_now === true ? "Quiet right now." : "Leave both empty for no quiet hours. Wraps midnight when the end is earlier.") + "</span></div>" +
      '<div class="setfield" data-field="nudges_per_hour"><label class="setlabel" for="setf-nudges">Finished-work notices per hour (0 means never unasked)</label>' +
      '<input type="number" min="0" max="' + esc(max) + '" step="1" inputmode="numeric" id="setf-nudges" data-input="nudges_per_hour" value="' + esc(nudges) + '"></div>' +
      "</div>" + (f.error ? '<p class="seterr setgen" role="alert">' + esc(f.error) + "</p>" : "") +
      '<div class="setacts"><button type="button" class="ghost" data-act="save-notices"' + (f.busy === true ? " disabled" : "") + ">Save</button>" +
      (quiet.start ? '<button type="button" class="ghost" data-act="clear-quiet"' + (f.busy === true ? " disabled" : "") + ">No quiet hours</button>" : "") +
      '<span class="setstatus" role="status">' + (f.saved === true ? "Saved." : "") + "</span></div></section>";
  }

  /* ---------------------------------------------------------------- the calls */
  const said = e => clean(e && e.message) || "That did not work. Try again.";

  // load(api, {notices: false}) reads the limits only: they move with every task, the owner's quiet hours and cap only when the owner changes them.
  async function load(api, options) {
    const read = async path => { try { return await api.get(path); } catch (e) { return null; } };
    const both = !(isObj(options) && options.notices === false);
    const [limits, notices] = await Promise.all([read(LIMITS_PATH), both ? read(ATTENTION_PATH) : Promise.resolve(null)]);
    return {limits: isObj(limits) ? limits : null, notices: isObj(notices) ? notices : null};
  }

  async function put(api, path, body) {
    try { return {ok: true, state: await api.put(path, body), error: ""}; } catch (e) { return {ok: false, state: null, error: said(e)}; }
  }

  async function saveLimit(api, raw) {
    const parsed = parseLimit(raw);
    if (!parsed.ok) return {ok: false, state: null, error: parsed.error};
    return put(api, LIMITS_PATH, {monthly_usd: parsed.value});
  }

  const saveGuard = (api, enabled) => put(api, LIMITS_PATH, {guard_enabled: enabled === true});

  async function continueGuard(api) {
    try { return {ok: true, state: await api.post(LIMITS_PATH + "/continue"), error: ""}; } catch (e) { return {ok: false, state: null, error: said(e)}; }
  }

  async function saveNotices(api, form) {
    const made = noticesBody(form);
    if (!made.ok) return {ok: false, state: null, error: made.error};
    return put(api, ATTENTION_PATH, made.body);
  }

  const LimitsView = {limitsHtml, noticesHtml, stripHtml, parseLimit, noticesBody, load, saveLimit, saveGuard, continueGuard, saveNotices, LIMITS_PATH, ATTENTION_PATH};
  if (typeof module === "object" && module !== null && module.exports) module.exports = LimitsView;
  else root.LimitsView = LimitsView;
})(globalThis);
