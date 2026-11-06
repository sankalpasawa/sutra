/* plan_meter.js - the plan meters of a provider: one bar per usage window with its percent and its reset time, the plan in words, and how
   old the figure is (GAP-providers; the old app's 04-screens.js usageBarSev, usageResetText and usageAllCardHtml).

   Strings in, strings out, like chat_view.js: nothing touches the DOM, nothing keeps a timer, and every word from the wire is escaped.

     severity(used)                  "ok" under 80 %, "warn" from 80 %, "bad" from 95 % (the old thresholds), "unknown" when there is no figure
     resetText(at, nowMs, when)      "resets in 25 min", "resets in 1 h 10 min", "resets Fri 09:00", "resets 7 Nov 09:00"; "reset" once the time has
                                     passed; "" when no time is known. `at` is epoch seconds; `when(ms)` gives {day, date, month, hh, mm} (local time)
     windowsOf(quota)                the windows to draw: `quota.windows`, else the one window of an older snapshot (window, used, resets_at)
     windowHtml(w, nowMs, when)      one row: label, percent, reset words and a bar. A window whose reset has passed reads "reset" instead of a
                                     stale percent; a window with no figure draws no bar (an empty bar is a claim)
     planLine(entry)                 "Claude Max, you@example.com, counted against your plan, not billed per call" from plan_label, account, billing
     asOf(quota, nowMs, when)        "as of 14:05" (the day too when the figure is older than a day) from `seen_at`; "" without it
     meterHtml(quota, nowMs, opts)   the block: a row per window, then the "as of" line; "" when the snapshot has no window. opts {when}
     clockOf(ms)                     the default `when`: the browser's local time

   A classic script with ONE global, PlanMeter; in node it is module.exports. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : "").replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const two = n => (n < 10 ? "0" : "") + n;

  const WARN = 80;
  const BAD = 95;
  const DAYS = freeze(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]);
  const MONTHS = freeze(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]);
  const LABELS = freeze({five_hour: "5-hour", seven_day: "Weekly", thirty_day: "Monthly", one_day: "Daily"});
  const BILLING = freeze({subscription: "counted against your plan, not billed per call", api_key: "billed per call"});
  const HOUR = 3600000;
  const DAY = 24 * HOUR;

  // A figure that is absent is absent: null, a bool or a string never reads as 0 %.
  const percentOf = used => (typeof used === "number" && finite(used) && used >= 0 ? used * 100 : null);

  function severity(used) {
    const pct = percentOf(used);
    if (pct === null) return "unknown";
    return pct >= BAD ? "bad" : (pct >= WARN ? "warn" : "ok");
  }

  function clockOf(ms) {
    const d = new Date(ms);
    return {day: d.getDay(), date: d.getDate(), month: d.getMonth(), hh: d.getHours(), mm: d.getMinutes()};
  }
  const timeOf = t => two(t.hh) + ":" + two(t.mm);

  // Under an hour: minutes. Under a day: hours and minutes. Under a week: the weekday and the time. Beyond: the date and the time.
  function resetText(at, nowMs, when) {
    if (typeof at !== "number" || !finite(at) || !finite(nowMs)) return "";
    const clock = typeof when === "function" ? when : clockOf;
    const ms = at * 1000;
    const d = ms - nowMs;
    if (d <= 0) return "reset";
    if (d < HOUR) return "resets in " + Math.max(1, Math.round(d / 60000)) + " min";
    if (d < DAY) {
      let h = Math.floor(d / HOUR);
      let m = Math.round((d - h * HOUR) / 60000);
      if (m === 60) { h += 1; m = 0; }                  // the last half minute of an hour is the next hour, never "4 h 60 min"
      return "resets in " + h + " h" + (m ? " " + m + " min" : "");
    }
    const t = clock(ms);
    if (d < 7 * DAY) return "resets " + DAYS[t.day] + " " + timeOf(t);
    return "resets " + t.date + " " + MONTHS[t.month] + " " + timeOf(t);
  }

  const keyOf = v => (typeof v === "string" && /^[a-z0-9_]{1,40}$/.test(v) ? v : "");
  const labelOf = (label, key) => clean(label) || LABELS[key] || (key ? key.replace(/_/g, " ") : "Limit");

  function windowsOf(quota) {
    if (!isObj(quota)) return [];
    const list = Array.isArray(quota.windows) ? quota.windows.filter(isObj) : [];
    if (list.length) return list;
    const key = keyOf(quota.window);
    if (key === "" && percentOf(quota.used) === null) return [];
    return [{key: key, label: labelOf("", key), used: quota.used, resets_at: quota.resets_at}];
  }

  function windowHtml(w, nowMs, when) {
    const key = keyOf(w && w.key);
    const label = labelOf(w && w.label, key);
    const reset = resetText(w && w.resets_at, nowMs, when);
    const passed = reset === "reset";
    const pct = passed ? null : percentOf(w && w.used);
    const sev = passed ? "reset" : severity(w && w.used);
    const shown = passed ? "reset" : (pct === null ? "no figure" : Math.round(pct) + "%");
    const bar = pct === null ? "" : '<span class="pmbar" role="img" aria-label="' + esc(label) + " at " + Math.round(pct) + ' percent"><i style="width:' +
      Math.min(100, Math.max(0, Math.round(pct))) + '%"></i></span>';
    return '<div class="pmw" data-key="' + esc(key) + '" data-sev="' + sev + '"><span class="pml">' + esc(label) + '</span><span class="pmp">' + esc(shown) +
      "</span>" + (passed || reset === "" ? "" : '<span class="pmr">' + esc(reset) + "</span>") + bar + "</div>";
  }

  function planLine(entry) {
    const e = isObj(entry) ? entry : {};
    const billing = typeof e.billing === "string" && Object.prototype.hasOwnProperty.call(BILLING, e.billing) ? BILLING[e.billing] : "";
    return [clean(e.plan_label), clean(e.account), billing].filter(Boolean).join(", ");
  }

  function asOf(quota, nowMs, when) {
    const seen = isObj(quota) ? quota.seen_at : null;
    if (typeof seen !== "number" || !finite(seen) || seen <= 0) return "";
    const clock = typeof when === "function" ? when : clockOf;
    const t = clock(seen * 1000);
    const old = finite(nowMs) && nowMs - seen * 1000 >= DAY;
    return "as of " + (old ? t.date + " " + MONTHS[t.month] + " " : "") + timeOf(t);
  }

  function meterHtml(quota, nowMs, opts) {
    const o = isObj(opts) ? opts : {};
    const windows = windowsOf(quota);
    if (windows.length === 0) return "";
    const seen = asOf(quota, nowMs, o.when);
    return '<div class="pmeter" role="group" aria-label="Plan usage">' + windows.map(w => windowHtml(w, nowMs, o.when)).join("") +
      (seen ? '<p class="pmasof">' + esc(seen) + "</p>" : "") + "</div>";
  }

  const PlanMeter = {severity, resetText, windowsOf, windowHtml, planLine, asOf, meterHtml, clockOf, WARN, BAD};
  if (typeof module === "object" && module !== null && module.exports) module.exports = PlanMeter;
  else root.PlanMeter = PlanMeter;
})(globalThis);
