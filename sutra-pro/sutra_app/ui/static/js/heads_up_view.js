/* heads_up_view.js - the Heads up lane beside Needs you, and how long each ask has waited (gap package attention; docs/notes/GAP-attention.md).

   Strings in, strings out, like chat_view.js: nothing touches the DOM and every word from the wire is escaped.

     split(items, seen)              {problems, quiet, finished} of GET /api/heads-up; a row the owner marked "Got it" (seen[task_id]) and a row of
                                     an unknown kind are dropped
     count(needs, items, seen)       what the badge, the tab title and the pill count: every question and approval, plus every problem not marked
                                     seen. A quiet team and finished work never count.
     summary(needs, items, seen)     "1 question, 2 to try again" (the strip's one-glance line), "" when nothing counts
     ageWords(seconds)               "3 days", "5 minutes", "just now" (the same words as the server's waiting.age_words)
     waitedSeconds(item, elapsedMs)  how long a needs-you item has waited by now: the server's waiting_s plus the time since that read
     waitedHtml(item, elapsedMs)     '<small class="nwait">waiting 3 days</small>', marked stale past 24 h; "" when the server sent no age
     laneHtml(items, opts)           the lane: problems with Try again, quiet teams, then finished work (FYI_SHOWN of them unless opts.more,
                                     then a "+N more" button). opts {seen, more}. "" when there is nothing to show.
     loadSeen(storage), saveSeen(storage, seen, items)   the "Got it" marks, per browser (localStorage key sutra:headsup:seen); every
                                     storage call is in a try, a mark of a row that is gone is dropped on save

   Buttons carry data-act: retry-task (data-task), headsup-seen (data-task), headsup-more. A team link is a real <a href="/d/<dept>/">.
   A classic script with ONE global, HeadsUpView; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ID = /^[A-Za-z0-9_.:-]{1,120}$/;
  const idOf = v => (ID.test(text(v)) ? text(v) : "");

  const FYI_SHOWN = 3;                 // the old app's NY_FYI_SHOWN
  const STALE_S = 24 * 3600;           // waiting.ASK_STALE_S
  const SEEN_KEY = "sutra:headsup:seen";
  const MAX_SEEN = 200;
  const KINDS = ["problem", "quiet", "finished"];
  const TONES = ["err", "stop", "warn", "ok"];
  const UNITS = [[86400, "day"], [3600, "hour"], [60, "minute"]];

  function ageWords(seconds) {
    const whole = Math.floor(Number(seconds));
    if (!Number.isFinite(whole)) return "just now";
    for (const [size, unit] of UNITS) {
      if (whole >= size) {
        const n = Math.floor(whole / size);
        return n + " " + unit + (n === 1 ? "" : "s");
      }
    }
    return "just now";
  }

  const rows = items => (Array.isArray(items) ? items.filter(i => isObj(i) && KINDS.includes(i.kind) && idOf(i.task_id) !== "") : []);
  const seenMap = seen => (isObj(seen) ? seen : {});

  function split(items, seen) {
    const marks = seenMap(seen);
    const out = {problems: [], quiet: [], finished: []};
    rows(items).forEach(i => {
      if (i.kind !== "quiet" && marks[i.task_id] === true) return;
      ({problem: out.problems, quiet: out.quiet, finished: out.finished})[i.kind].push(i);
    });
    return out;
  }

  const needList = needs => (Array.isArray(needs) ? needs.filter(isObj) : []);

  function count(needs, items, seen) {
    return needList(needs).length + split(items, seen).problems.length;
  }

  function summary(needs, items, seen) {
    const list = needList(needs);
    const questions = list.filter(n => n.kind !== "approval").length;
    const approvals = list.length - questions;
    const problems = split(items, seen).problems.length;
    const parts = [];
    if (questions) parts.push(questions + " question" + (questions === 1 ? "" : "s"));
    if (approvals) parts.push(approvals + " approval" + (approvals === 1 ? "" : "s"));
    if (problems) parts.push(problems + " to try again");
    return parts.join(", ");
  }

  function waitedSeconds(item, elapsedMs) {
    if (!isObj(item) || !Number.isFinite(item.waiting_s)) return null;
    const extra = Number.isFinite(elapsedMs) && elapsedMs > 0 ? Math.floor(elapsedMs / 1000) : 0;
    return Math.max(0, item.waiting_s) + extra;
  }

  function waitedHtml(item, elapsedMs) {
    const s = waitedSeconds(item, elapsedMs);
    if (s === null) return "";
    const stale = item.stale === true || s >= STALE_S;
    const words = s < 60 ? "asked just now" : "waiting " + ageWords(s);
    return '<small class="nwait' + (stale ? " stale" : "") + '"' + (stale ? ' title="Unanswered for more than a day"' : "") + ">" + esc(words) + "</small>";
  }

  function teamLink(i) {
    const dept = idOf(i.dept_id);
    return dept ? '<a class="huopen" href="/d/' + encodeURIComponent(dept) + '/?view=simple">Open team</a>' : "";
  }

  function rowHtml(i) {
    const tone = TONES.includes(i.tone) ? i.tone : "warn";
    const task = idOf(i.task_id);
    const since = Number.isFinite(i.since_s) ? i.since_s : null;
    const when = since === null ? "" : (i.kind === "quiet" ? "silent " + ageWords(since) : (since < 60 ? "just now" : ageWords(since) + " ago"));
    const why = i.kind === "problem" && clean(i.outcome) ? '<small class="huwhy">' + esc(clean(i.outcome)) + "</small>" : "";
    const acts = [];
    if (i.retry === true && i.kind !== "quiet") acts.push('<button type="button" data-act="retry-task" data-task="' + esc(task) + '">Try again</button>');
    const link = teamLink(i);
    if (link) acts.push(link);
    if (i.kind !== "quiet") acts.push('<button type="button" class="linkbtn" data-act="headsup-seen" data-task="' + esc(task) + '">Got it</button>');
    return '<div class="huitem t-' + tone + '" data-kind="' + esc(i.kind) + '" data-task="' + esc(task) + '"><span class="hutext">' + esc(clean(i.text)) + "</span>" +
      (when ? '<small class="huwhen">' + esc(when) + "</small>" : "") + why + '<span class="huacts">' + acts.join("") + "</span></div>";
  }

  function laneHtml(items, opts) {
    const o = isObj(opts) ? opts : {};
    const parts = split(items, o.seen);
    const fyi = o.more === true ? parts.finished : parts.finished.slice(0, FYI_SHOWN);
    const hidden = parts.finished.length - fyi.length;
    const shown = parts.problems.concat(parts.quiet, fyi);
    if (shown.length === 0) return "";
    return '<div class="hulane" role="group" aria-label="Heads up"><h3 class="nylane">Heads up</h3>' + shown.map(rowHtml).join("") +
      (hidden > 0 ? '<button type="button" class="linkbtn humore" data-act="headsup-more">+' + hidden + " more</button>" : "") + "</div>";
  }

  function loadSeen(storage) {
    try {
      const raw = storage && typeof storage.getItem === "function" ? storage.getItem(SEEN_KEY) : null;
      const list = JSON.parse(raw || "[]");
      const out = {};
      (Array.isArray(list) ? list : []).forEach(id => { if (idOf(id)) out[id] = true; });
      return out;
    } catch (e) {
      return {};
    }
  }

  // Only marks of rows still listed are kept (a mark outlives its row by nothing), newest last, at most MAX_SEEN.
  function saveSeen(storage, seen, items) {
    const listed = new Set(rows(items).map(i => i.task_id));
    const keep = Object.keys(seenMap(seen)).filter(id => seen[id] === true && idOf(id) && (listed.size === 0 || listed.has(id))).slice(-MAX_SEEN);
    try {
      if (storage && typeof storage.setItem === "function") storage.setItem(SEEN_KEY, JSON.stringify(keep));
      return true;
    } catch (e) {
      return false;
    }
  }

  const HeadsUpView = {split, count, summary, ageWords, waitedSeconds, waitedHtml, laneHtml, loadSeen, saveSeen, FYI_SHOWN, SEEN_KEY};
  if (typeof module === "object" && module !== null && module.exports) module.exports = HeadsUpView;
  else root.HeadsUpView = HeadsUpView;
})(globalThis);
