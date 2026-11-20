/* project_view.js - what the project page draws (MAN-13, D326): strings in, strings out, no DOM, no timer, so `node --test` runs it.

   The second of the page's three layers (project_store.js, this file, project_page.js). Every word that comes from the wire goes through esc(); a number is a number or nothing. The
   words are the owner's: no "node", "lease" or "tier" anywhere on the page. A question is drawn as a card with its answers as buttons (`data-act`), the same words as the chat's card
   (chat_view.js, D317), so one answer means one thing wherever it is given.

   Pieces: header(), noteHtml(), cardsHtml(), graphHtml(), stepsHtml(), spendHtml(), decidedHtml(), whyHtml(), auditHtml(), messagesHtml(), page().

   A classic script with ONE global, ProjectView; in node it is module.exports. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const arr = v => (Array.isArray(v) ? v : []);
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const group = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const Store = () => (typeof require === "function" && typeof module === "object" ? require("./project_store.js") : root.ProjectStore);

  /* ---------------------------------------------------------------- words */
  const STATUS_WORDS = freeze({planning: "Planning", awaiting_approval: "Waiting for your answer", running: "Working", reviewing: "Being checked", done: "Done",
    done_with_open_items: "Done, but some steps did not finish", stopped: "Stopped", failed: "Could not finish"});
  const STATE_WORDS = freeze({planned: "Waiting its turn", awaiting_approval: "Waiting for your answer", awaiting_system: "Waiting for your computer to allow it", ready: "Ready to start",
    queued: "Waiting to start", leased: "Starting", running: "Working", handing_off: "Handing in its work", done: "Done", failed: "Did not finish", cancelled: "Cancelled", expired: "Ran out of time"});
  const ACTIVE = freeze(["leased", "running", "handing_off"]);
  const ENDED = freeze(["done", "failed", "cancelled", "expired"]);
  const FINAL = freeze(["done", "done_with_open_items", "stopped", "failed"]);
  const ANSWERS = freeze({allow_once: "Allow once", allow_project: "Allow for this project", deny: "No", check_again: "Check again", skip: "Skip"});
  const POLICY_WORDS = freeze({stop_branch: "A step that fails stops only the steps after it", stop_all: "A step that fails stops the whole project"});
  const ACTION_WORDS = freeze({
    "project.created": "Project started", "project.stopped": "Project stopped", "project.paused": "Project paused", "project.resumed": "Project continued", "project.ended": "Project finished",
    "project.decide_for_me": "Decide for me turned on", "plan.accepted": "Plan accepted", "plan.refused": "Plan refused", "plan.defaults": "Plan used its usual settings",
    "grant.issued": "A step was given its permissions", "grant.denied": "A step was refused a permission", "gate.asked": "Asked you", "gate.decided": "Answered", "gate.refused": "A question ran out",
    "approval.denied": "You said no", "system.asked": "Asked about your computer", "system.cleared": "Your computer allowed it", "system.skipped": "Skipped a permission",
    "system.late_denied": "Your computer did not allow it", "system.still_needed": "Your computer still does not allow it", "system.elevated": "Run as administrator",
    "node.spawned": "A step started", "node.leased": "A step started", "node.restarted": "A step started again", "node.expired": "A step went quiet and was stopped", "node.error": "A step had an error",
    "node.cancelled": "A step was cancelled", "node.rework": "A step was sent back", "node.heartbeat_lost": "A step went quiet", "node.lease_extended": "A step was given more time",
    "handoff.accepted": "A step handed in its work", "handoff.refused": "A step's work was not accepted", "scope.violation": "A step wrote outside its files", "scope.quarantined": "A step's work was set aside",
    "review.started": "The reviewer started", "review.loop_cap": "The reviewer stopped sending work back", "verdict.received": "The reviewer gave its opinion", "verdict.refused": "The reviewer's opinion was not accepted",
    "trigger.cap_reached": "A limit was reached", "trigger.lease_lost": "A step stopped answering", "trigger.egress_scrub": "Private words were taken out before sending"});

  const word = (table, key, fallback) => (Object.prototype.hasOwnProperty.call(table, key) ? table[key] : fallback);
  const credits = n => (Number.isFinite(n) ? group(n) + (n === 1 ? " credit" : " credits") : "");
  // "12:04" from an ISO time, in the viewer's own zone; empty for anything else.
  function clock(iso) {
    const d = typeof iso === "string" ? new Date(iso) : null;
    return d && !isNaN(d.getTime()) ? String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") : "";
  }

  /* ---------------------------------------------------------------- pieces */
  function header(snap) {
    const p = isObj(snap) && isObj(snap.project) ? snap.project : {};
    const status = word(STATUS_WORDS, p.status, "Working");
    const final = FINAL.indexOf(p.status) >= 0;
    const paused = p.paused === true && !final;
    const buttons = final ? "" :
      '<button type="button" data-act="project-pause" data-resume="' + (paused ? "1" : "0") + '">' + (paused ? "Continue" : "Pause") + "</button>" +
      '<button type="button" class="pbad" data-act="project-stop">Stop everything</button>';
    return '<h1 class="ptitle">' + esc(clean(p.title) || "A project") + '</h1><p class="pstatus" data-status="' + esc(clean(p.status)) + '">' + esc(status) + (paused ? " (paused)" : "") + "</p>" +
      (p.failure_policy ? '<p class="cnote">' + esc(word(POLICY_WORDS, p.failure_policy, "")) + (p.decide_for_me ? ". Sutra answers the questions it may for you." : ".") + "</p>" : "") +
      '<div class="pbtns">' + buttons + "</div>";
  }

  // The words about the project's end: why it stopped (the rule, the owner or a limit) when it did not finish.
  function whyHtml(snap) {
    const p = isObj(snap) && isObj(snap.project) ? snap.project : {};
    const reason = clean(p.stop_reason);
    if (!reason || (p.status !== "stopped" && p.status !== "failed" && p.status !== "done_with_open_items")) return "";
    return '<p class="pwhy" role="status"><b>Why:</b> ' + esc(reason) + "</p>";
  }

  // The static note when the installed app is not in the usual place (D322 d). Nothing for a usual place or an answer the page could not read.
  function noteHtml(location) {
    if (!isObj(location) || location.usual !== false) return "";
    const text = clean(location.note);
    return text ? '<p class="pnote" role="note">' + esc(text) + "</p>" : "";
  }

  function answerButtons(options, project, approval, item) {
    return arr(options).map(clean).filter(o => Object.prototype.hasOwnProperty.call(ANSWERS, o)).map(o =>
      '<button type="button" data-act="node-answer" data-project="' + esc(project) + '" data-approval="' + esc(approval) + '" data-item="' + esc(item) + '" data-decision="' + o + '">' + esc(ANSWERS[o]) + "</button>").join("");
  }

  // The open questions: a card for each, its answers as buttons. A permission of the computer lists its steps for this system.
  function cardsHtml(snap) {
    const s = isObj(snap) ? snap : {};
    const project = clean(isObj(s.project) ? s.project.id : "");
    const asked = arr(s.cards).filter(isObj).map(c =>
      '<div class="ncard c-nodeapproval" data-card="node_approval" data-kind="' + esc(clean(c.kind)) + '" data-approval="' + esc(clean(c.approval_id)) + '"><p class="sq">' + esc(clean(c.question)) + "</p>" +
      '<div class="opts">' + answerButtons(c.options, project, clean(c.approval_id), clean(c.item)) + "</div></div>");
    const system = arr(s.system_cards).filter(isObj).map(c => {
      const steps = arr(c.steps).map(clean).filter(Boolean);
      const affects = arr(c.affects).map(clean).filter(Boolean);
      return '<div class="ncard c-nodeapproval" data-card="system_permission" data-item="' + esc(clean(c.item)) + '" data-approval="' + esc(clean(c.approval_id)) + '">' +
        '<p class="sq">' + esc(clean(c.label) || "Your computer must allow something first.") + "</p>" +
        (steps.length ? '<ol class="psteps">' + steps.map(t => "<li>" + esc(t) + "</li>").join("") + "</ol>" : "") +
        (affects.length ? '<p class="cnote">This holds up: ' + esc(affects.join(", ")) + ". The other steps go on.</p>" : "") +
        '<div class="opts">' + answerButtons(c.options && c.options.length ? c.options : ["check_again", "skip"], project, clean(c.approval_id), clean(c.item)) + "</div></div>";
    });
    const all = asked.concat(system);
    return all.length ? '<h2>Waiting for you</h2><div class="pcards">' + all.join("") + "</div>" : "";
  }

  /* ---- the graph: steps in columns by how far they are from the start, a line for each "comes after", a dashed one for "shares files, so it waits" */
  const BOX = freeze({w: 150, h: 42, gx: 50, gy: 16});
  function graphHtml(snap) {
    const s = isObj(snap) ? snap : {};
    const nodes = arr(s.nodes).filter(n => isObj(n) && n.role !== "planner");
    if (nodes.length === 0) return "";
    const deep = Store().depths(nodes, arr(s.edges));
    const rows = {};
    const place = {};
    nodes.forEach(n => {
      const d = deep[n.id] || 0;
      rows[d] = (rows[d] || 0) + 1;
      place[n.id] = {x: d * (BOX.w + BOX.gx), y: (rows[d] - 1) * (BOX.h + BOX.gy)};
    });
    const columns = Math.max.apply(null, Object.keys(rows).map(Number)) + 1;
    const height = Math.max.apply(null, Object.keys(rows).map(k => rows[k])) * (BOX.h + BOX.gy);
    const width = columns * BOX.w + (columns - 1) * BOX.gx;
    const lines = arr(s.edges).filter(e => isObj(e) && place[e.from] && place[e.to]).map(e => {
      const a = place[e.from], b = place[e.to];
      return '<line class="pedge' + (e.kind === "conflict" ? " pconflict" : "") + '" x1="' + (a.x + BOX.w) + '" y1="' + (a.y + BOX.h / 2) + '" x2="' + b.x + '" y2="' + (b.y + BOX.h / 2) + '"/>';
    }).join("");
    const boxes = nodes.map(n => {
      const at = place[n.id];
      return '<g class="pnode" data-state="' + esc(clean(n.state)) + '" transform="translate(' + at.x + "," + at.y + ')"><rect width="' + BOX.w + '" height="' + BOX.h + '" rx="8"/>' +
        '<text x="10" y="18" class="pn1">' + esc(Store().nodeName(n)) + '</text><text x="10" y="34" class="pn2">' + esc(word(STATE_WORDS, n.state, "")) + "</text></g>";
    }).join("");
    const label = nodes.length + (nodes.length === 1 ? " step" : " steps") + " and the order they run in";
    return '<h2>The steps</h2><div class="pgraph"><svg role="img" aria-label="' + esc(label) + '" viewBox="0 0 ' + width + " " + height + '" width="' + width + '" height="' + height + '">' + lines + boxes + "</svg></div>" +
      (arr(s.edges).some(e => isObj(e) && e.kind === "conflict") ? '<p class="cnote">A dashed line means two steps use the same files, so one waits for the other.</p>' : "");
  }

  function stepsHtml(snap) {
    const s = isObj(snap) ? snap : {};
    const nodes = arr(s.nodes).filter(n => isObj(n) && n.role !== "planner");
    const byId = {};
    nodes.forEach(n => { byId[n.id] = n; });
    const items = nodes.map(n => {
      const after = arr(n.depends_on).map(id => byId[id]).filter(Boolean).map(x => Store().nodeName(x));
      const waits = arr(s.edges).filter(e => isObj(e) && e.kind === "conflict" && e.to === n.id && byId[e.from]).map(e => Store().nodeName(byId[e.from]));
      const files = arr(n.scope).map(clean).filter(Boolean);
      return '<li class="pstep" data-state="' + esc(clean(n.state)) + '" data-node="' + esc(clean(n.id)) + '"><b>' + esc(Store().nodeName(n)) + "</b> " +
        '<span class="pstate">' + esc(word(STATE_WORDS, n.state, "")) + "</span>" +
        (n.attempt > 1 ? ' <span class="cnote">(try ' + esc(n.attempt) + ")</span>" : "") +
        (after.length ? '<span class="cnote">Starts after: ' + esc(after.join(", ")) + "</span>" : "") +
        (waits.length ? '<span class="cnote">Shares files with, so waits for: ' + esc(waits.join(", ")) + "</span>" : "") +
        (files.length ? '<span class="cnote">May change: ' + esc(files.join(", ")) + "</span>" : "") +
        (clean(n.failure_reason) ? '<span class="pwhy">' + esc(clean(n.failure_reason)) + "</span>" : "") +
        (ACTIVE.indexOf(n.state) >= 0 ? '<button type="button" class="pbad" data-act="node-stop" data-node="' + esc(clean(n.id)) + '">Stop this step</button>' : "") + "</li>";
    });
    return items.length ? '<ul class="plist">' + items.join("") + "</ul>" : "";
  }

  function spendHtml(snap) {
    const s = isObj(snap) ? snap : {};
    const p = isObj(s.project) ? s.project : {};
    const calls = isObj(s.spend) ? s.spend.calls : null;
    if (!Number.isFinite(calls)) return "";
    const budget = Number.isFinite(p.budget_credits) && p.budget_credits > 0 ? p.budget_credits : null;
    const usd = isObj(s.spend) && Number.isFinite(s.spend.usd) ? s.spend.usd : null;
    return '<h2>What it has used</h2><p class="pspend"><b>' + credits(calls) + "</b>" + (budget ? " of " + credits(budget) : "") + (usd !== null ? "; about $" + usd.toFixed(2) : "") + "</p>" +
      (budget && calls >= budget ? '<p class="cnote">It has used all of its credits.</p>' : "");
  }

  // "Sutra decided for you": the questions the rule table answered while Decide for me was on, each with its answer and its reason.
  function decidedHtml(list) {
    const rows = arr(list).filter(isObj);
    if (rows.length === 0) return "";
    return '<h2>Sutra decided for you</h2><ul class="plist pdecided">' + rows.map(r =>
      '<li><b>' + (r.decision === "no" ? "Said no" : "Said yes") + "</b> " + esc(clean(r.why)) + (clock(r.at) ? ' <span class="cnote">' + esc(clock(r.at)) + "</span>" : "") + "</li>").join("") + "</ul>" +
      '<p class="cnote">Sutra never raises credits, never allows a change to your computer\'s settings and never answers a question about your computer for you.</p>';
  }

  function auditHtml(rows) {
    const list = arr(rows).filter(isObj);
    if (list.length === 0) return '<h2>What happened</h2><p class="cempty">Nothing yet.</p>';
    return '<h2>What happened</h2><ol class="plist paudit">' + list.slice().reverse().map(r =>
      '<li data-seq="' + esc(r.seq) + '"><span class="cnote">' + esc(clock(r.at)) + "</span> <b>" + esc(word(ACTION_WORDS, r.action, clean(r.action))) + "</b>" +
      (clean(r.reason) ? " <span>" + esc(clean(r.reason)) + "</span>" : "") + "</li>").join("") + "</ol>";
  }

  function textOf(body) {
    if (typeof body === "string") return clean(body);
    if (isObj(body)) return clean(body.summary || body.text || body.message || "");
    return "";
  }

  function messagesHtml(rows, snap) {
    const list = arr(rows).filter(isObj);
    if (list.length === 0) return "";
    const byId = {};
    arr(isObj(snap) ? snap.nodes : []).forEach(n => { if (isObj(n)) byId[n.id] = n; });
    const name = id => (byId[id] ? Store().nodeName(byId[id]) : "A step");
    return '<h2>What the steps said to each other</h2><ol class="plist pmsgs">' + list.map(m => {
      const from = isObj(m.from) ? m.from.node_id : "";
      const text = textOf(m.body);
      return '<li data-seq="' + esc(m.seq) + '"><b>' + esc(name(from)) + "</b> " + esc(text.length > 240 ? text.slice(0, 240) + "..." : text || "(handed in its work)") + "</li>";
    }).join("") + "</ol>";
  }

  // The whole page body, in the order the owner needs it: what waits for them first, the picture, the steps, what it cost, who decided, what happened.
  function page(state, location) {
    const S = isObj(state) ? state : {};
    if (!S.snapshot) return '<p class="' + (S.error ? "cerr" : "cempty") + '">' + esc(S.error || "Loading...") + "</p>";
    const St = Store();
    return (S.error ? '<p class="cerr" role="alert">' + esc(S.error) + "</p>" : "") + noteHtml(location) + whyHtml(S.snapshot) + cardsHtml(S.snapshot) + graphHtml(S.snapshot) + stepsHtml(S.snapshot) + spendHtml(S.snapshot) +
      decidedHtml(St.decidedList(S.audit)) + auditHtml(S.audit) + messagesHtml(S.messages, S.snapshot);
  }

  const ProjectView = {STATUS_WORDS, STATE_WORDS, ANSWERS, ACTION_WORDS, POLICY_WORDS, esc, header, whyHtml, noteHtml, cardsHtml, graphHtml, stepsHtml, spendHtml, decidedHtml, auditHtml, messagesHtml, page, clock};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ProjectView;
  else root.ProjectView = ProjectView;
})(globalThis);
