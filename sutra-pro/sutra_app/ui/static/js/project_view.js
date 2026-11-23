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
    "project.decide_for_me": "Decide for me turned on", "project.slept": "Your computer was asleep or closed", "plan.accepted": "Plan accepted", "plan.refused": "Plan refused",
    "plan.defaults": "Plan used its usual settings", "grant.issued": "A step was given what it may do", "grant.denied": "A step was refused something", "gate.asked": "Asked you",
    "gate.decided": "A question was answered", "gate.refused": "A question was not answered in time", "approval.denied": "You said no", "system.asked": "Asked about your computer",
    "system.cleared": "Your computer allowed it", "system.skipped": "Skipped something your computer must allow", "system.late_denied": "Your computer did not allow it",
    "system.still_needed": "Your computer still does not allow it", "system.elevated": "Sutra was opened as administrator",
    "node.spawned": "A step started", "node.leased": "A step is about to start", "node.restarted": "A step started again", "node.retry": "A step was tried again", "node.expired": "A step went quiet and was stopped",
    "node.error": "A step had a problem", "node.cancelled": "A step was cancelled", "node.rework": "A step was sent back", "node.heartbeat_lost": "A step went quiet",
    "node.lease_extended": "A step was given more time", "node.done": "A step finished", "node.failed": "A step did not finish",
    "handoff.accepted": "A step handed in its work", "handoff.refused": "A step's work was not accepted",
    "scope.violation": "A step changed files that were not its own", "scope.quarantined": "A step's work was set aside", "scope.unchecked": "Sutra could not check which files this step changed",
    "review.started": "The reviewer started", "review.loop_cap": "The reviewer was not asked again", "verdict.received": "The reviewer gave its opinion", "verdict.refused": "The reviewer's opinion could not be used",
    "tool.used": "A step used a tool", "tool.pending": "A step's list of tools is being written", "tool.logged": "A step's list of tools was written", "trigger.cap_reached": "A step reached a limit", "trigger.lease_lost": "A step stopped answering",
    "trigger.egress_scrub": "Private words were taken out of a step's messages again and again", "trigger.project_wall": "The project ran too long", "trigger.project_usd": "The project spent more than you set",
    "trigger.project_month": "Your monthly limit was reached", "node.stopped": "A step was stopped", "kill": "The kill switch was used", "pause": "Everything was paused", "resume": "Everything was continued",
    "plan.empty": "The plan had no steps", "plan.malformed": "The plan could not be read", "plan.owner_access": "The plan needed more than your folder setting allows", "plan.too_big": "The plan was too big"});
  // Reasons that are not plain words are not shown, or are put into words here. Everything else the server wrote in plain words is shown as it is.
  const NO_REASON = freeze(["tool.pending", "tool.logged", "grant.issued", "node.spawned", "node.leased", "node.heartbeat_lost", "node.lease_extended", "plan.accepted", "node.done", "kill", "pause", "resume"]);
  const OPINION_WORDS = freeze({approve: "approves of the work", changes: "asks for changes", reject: "does not approve of the work"});
  // Why something was stopped, in the words the owner uses (D383): the engine says "Stopped: stopped on request" whoever asked, the server says "stopped by the kill switch" or "stopped by you". `project` is the
  // project row, so a step the engine only says was "stopped on request" gets the reason the whole project was stopped for.
  function stopWords(reason, project) {
    const raw = clean(reason).replace(/^stopped:\s*/i, "").replace(/[.\s]+$/, "");
    const low = raw.toLowerCase();
    if (!raw) return "";
    if (/kill switch|kill file/.test(low)) return "The kill switch was used";
    if (/^waiting task .* did not finish$/.test(low)) return "The step before it did not finish";
    if (low === "stopped by you" || low === "reset by you") return "You stopped it";
    if (low === "stopped on request") {
      const why = isObj(project) && project.status === "stopped" ? clean(project.stop_reason) : "";
      return why && !/^stopped on request$/i.test(why.replace(/^stopped:\s*/i, "")) ? stopWords(why, null) : "It was stopped before it finished";
    }
    return raw.charAt(0).toUpperCase() + raw.slice(1);
  }
  const sentence = text => (text && !/[.!?]$/.test(text) ? text + "." : text);
  // What a tool row says: its kind, the file when there is one, how many times ("run, 7 times" is "ran commands 7 times").
  const TOOL_VERBS = freeze({read: "read", edit: "changed", run: "ran commands", search: "searched", web: "used the web", sutra: "looked at Sutra's own data", github: "read GitHub", other: "used a tool"});
  const GIT_NAMES = freeze(["HEAD", "index", "COMMIT_EDITMSG", "ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD", "packed-refs"]);     // bare names inside a repository's .git folder (no other bare name is guessed at)
  const OWN_FILES = freeze({"project.md": "its report", "report.md": "its report"});
  function toolWords(reason) {
    const m = /^(read|edit|run|search|web|sutra|github|other)(?: (.+?))?, (\d+) times?$/.exec(clean(reason));
    if (!m) return "A step used a tool";
    const times = Number(m[3]);
    const verb = TOOL_VERBS[m[1]];
    const n = times === 1 ? "once" : times + " times";
    if (m[1] === "read" && GIT_NAMES.indexOf(m[2]) >= 0) return "A step looked at the folder's history, " + n;                 // the repository's own files (D405)
    if (m[1] === "edit") return "A step wrote " + (OWN_FILES[m[2]] || m[2] || "a file") + ", " + n;
    const what = m[1] === "read" ? " " + m[2] : "";
    return "A step " + verb + what + (m[1] === "run" || m[1] === "web" ? " " : ", ") + n;
  }
  function reasonWords(row, project) {
    const action = clean(row.action);
    const reason = clean(row.reason);
    if (!reason || NO_REASON.indexOf(action) >= 0) return "";
    if (action === "tool.used") return "";                         // the words are in the heading (toolWords)
    if (action === "project.stopped" || action === "node.stopped" || action === "node.cancelled") return stopWords(reason, project);
    if (action === "project.ended") return word(STATUS_WORDS, reason, "");
    if (action === "verdict.received") return word(OPINION_WORDS, reason, "");
    if (action === "gate.decided") return reason.startsWith("decided_by owner") ? "you answered" : reason.replace(/^decided_by rule:decide_for_me:?\s*/, "Sutra answered for you: ").replace(/^(Sutra answered for you: )[a-z0-9_]+:\s*/, "$1");
    if (action === "handoff.accepted") return "";                    // the count was of every file of the run folder, plumbing included: the messages below say what it made (D394)
    return reason;
  }

  const word = (table, key, fallback) => (Object.prototype.hasOwnProperty.call(table, key) ? table[key] : fallback);
  const credits = n => (Number.isFinite(n) ? group(n) + (n === 1 ? " credit" : " credits") : "");
  // "12:04" from an ISO time, in the viewer's own zone; empty for anything else.
  function clock(iso) {
    const d = typeof iso === "string" ? new Date(iso) : null;
    return d && !isNaN(d.getTime()) ? String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") : "";
  }

  /* ---------------------------------------------------------------- pieces */
  // The steps that wait for an answer to a question of the engine itself (D401), as a set of step ids.
  const asking = snap => { const ids = {}; arr(isObj(snap) ? snap.questions : []).filter(isObj).forEach(q => { ids[clean(q.node_id)] = true; }); return ids; };
  function header(snap) {
    const p = isObj(snap) && isObj(snap.project) ? snap.project : {};
    const waiting = Object.keys(asking(snap)).length > 0 && (p.status === "running" || p.status === "reviewing");
    const status = waiting ? "Waiting for your answer" : word(STATUS_WORDS, p.status, "Working");
    const final = FINAL.indexOf(p.status) >= 0;
    const paused = p.paused === true && !final;
    const held = paused && arr(isObj(snap) ? snap.cards : []).some(c => isObj(c) && c.kind === "scope_violation");          // a question about files nobody owns holds it: Continue would be refused (N-3)
    const buttons = final ? "" :
      (held ? "" : '<button type="button" data-act="project-pause" data-resume="' + (paused ? "1" : "0") + '">' + (paused ? "Continue" : "Pause") + "</button>") +
      '<button type="button" class="pbad" data-act="project-stop">Stop everything</button>';
    const request = clean(isObj(snap) ? snap.request : "");
    const full = request && request !== clean(p.title) && request.length > clean(p.title).length - 1 ? '<details class="prequest"><summary>Your request</summary><p>' + esc(request) + "</p></details>" : "";
    return '<h1 class="ptitle">' + esc(clean(p.title) || "A project") + '</h1>' + full + '<p class="pstatus" data-status="' + esc(clean(p.status)) + '">' + esc(status) + (paused ? " (paused)" : "") + "</p>" +
      (held ? '<p class="cnote" role="status">It is held until you answer the question below about files. It goes on when you do.</p>' : "") +
      (p.failure_policy ? '<p class="cnote">' + esc(word(POLICY_WORDS, p.failure_policy, "")) + (p.decide_for_me ? ". Sutra answers the questions it may for you." : ".") + "</p>" : "") +
      '<div class="pbtns">' + buttons + "</div>";
  }

  // The words about the project's end: why it stopped (the rule, the owner or a limit) when it did not finish.
  function whyHtml(snap) {
    const p = isObj(snap) && isObj(snap.project) ? snap.project : {};
    const reason = clean(p.stop_reason);
    if (!reason || (p.status !== "stopped" && p.status !== "failed" && p.status !== "done_with_open_items" && p.status !== "done")) return "";
    return '<p class="pwhy" role="status"><b>Why:</b> ' + esc(sentence(stopWords(reason, null))) + "</p>";
  }

  // The static note when the installed app is not in the usual place (D322 d). Nothing for a usual place or an answer the page could not read.
  function noteHtml(location) {
    if (!isObj(location) || location.usual !== false) return "";
    const text = clean(location.note);
    return text ? '<p class="pnote" role="note">' + esc(text) + "</p>" : "";
  }

  // The reviewer's question is "send the steps back?" (D393): its two answers say that, not "Allow once" and "No".
  const REVIEW_ANSWERS = freeze({allow_once: "Send them back", deny: "Leave as it is"});
  function answerButtons(options, project, approval, item, kind) {
    const words = kind === "review" ? Object.assign({}, ANSWERS, REVIEW_ANSWERS) : ANSWERS;
    return arr(options).map(clean).filter(o => Object.prototype.hasOwnProperty.call(ANSWERS, o)).map(o =>
      '<button type="button" data-act="node-answer" data-project="' + esc(project) + '" data-approval="' + esc(approval) + '" data-item="' + esc(item) + '" data-decision="' + o + '">' + esc(words[o]) + "</button>").join("");
  }

  // The open questions: a card for each, its answers as buttons. A permission of the computer lists its steps for this system.
  function cardsHtml(snap) {
    const s = isObj(snap) ? snap : {};
    const project = clean(isObj(s.project) ? s.project.id : "");
    const asked = arr(s.cards).filter(isObj).map(c =>
      '<div class="ncard c-nodeapproval" data-card="node_approval" data-kind="' + esc(clean(c.kind)) + '" data-approval="' + esc(clean(c.approval_id)) + '"><p class="sq">' + esc(clean(c.question)) + "</p>" +
      '<div class="opts">' + answerButtons(c.options, project, clean(c.approval_id), clean(c.item), clean(c.kind)) + "</div></div>");
    const system = arr(s.system_cards).filter(isObj).map(c => {
      const steps = arr(c.steps).map(clean).filter(Boolean);
      const affects = arr(c.affects).map(clean).filter(Boolean);
      return '<div class="ncard c-nodeapproval" data-card="system_permission" data-item="' + esc(clean(c.item)) + '" data-approval="' + esc(clean(c.approval_id)) + '">' +
        '<p class="sq">' + esc(clean(c.label) || "Your computer must allow something first.") + "</p>" +
        (steps.length ? '<ol class="psteps">' + steps.map(t => "<li>" + esc(t) + "</li>").join("") + "</ol>" : "") +
        (affects.length ? '<p class="cnote">This holds up: ' + esc(affects.join(", ")) + ". The other steps go on.</p>" : "") +
        '<div class="opts">' + answerButtons(c.options && c.options.length ? c.options : ["check_again", "skip"], project, clean(c.approval_id), clean(c.item)) + "</div></div>";
    });
    const engine = arr(s.questions).filter(isObj).map(q => {
      const options = arr(q.options).map(clean).filter(Boolean).slice(0, 20);
      const buttons = options.map((text, i) => '<button type="button" data-act="step-answer" data-session="' + esc(clean(q.session_id)) + '" data-text="Option ' + (i + 1) + '">' + esc(text.length > 160 ? text.slice(0, 159) + "\u2026" : text) + "</button>").join("");
      return '<div class="ncard c-nodeapproval" data-card="step_question" data-message="' + esc(clean(q.message_id)) + '"><p class="sq">' + esc(clean(q.text).replace(/\s*Option \d+:.*$/, "")) + "</p>" +
        (buttons ? '<div class="opts">' + buttons + "</div>" : '<p class="cnote">Answer it in that team\'s chat.</p>') + "</div>";
    });
    const all = asked.concat(system, engine);
    return all.length ? '<h2>Waiting for you</h2><div class="pcards">' + all.join("") + "</div>" : "";
  }

  /* ---- the graph: steps in columns by how far they are from the start, a line for each "comes after", a dashed one for "shares files, so it waits". Drawn twice (D383): left to right, and top to
     bottom for a phone (CSS shows one of them), so the picture never needs a sideways scroll. */
  const BOX = freeze({w: 150, h: 42, gx: 50, gy: 16});
  const short = (text, n) => (text.length > n ? text.slice(0, n - 1).trimEnd() + "\u2026" : text);
  function drawGraph(nodes, edges, deep, vertical, ask) {
    const rows = {};
    const place = {};
    nodes.forEach(n => {
      const d = deep[n.id] || 0;
      rows[d] = (rows[d] || 0) + 1;
      const along = d * (vertical ? BOX.h + BOX.gx : BOX.w + BOX.gx);
      const across = (rows[d] - 1) * (vertical ? BOX.w + BOX.gy : BOX.h + BOX.gy);
      place[n.id] = vertical ? {x: across, y: along} : {x: along, y: across};
    });
    const depth = Object.keys(rows).length;
    const widest = Math.max.apply(null, Object.keys(rows).map(k => rows[k]));
    const width = vertical ? widest * BOX.w + (widest - 1) * BOX.gy : depth * BOX.w + (depth - 1) * BOX.gx;
    const height = vertical ? depth * BOX.h + (depth - 1) * BOX.gx : widest * BOX.h + (widest - 1) * BOX.gy;
    const lines = edges.filter(e => isObj(e) && place[e.from] && place[e.to]).map(e => {
      const a = place[e.from], b = place[e.to];
      const ends = vertical ? [a.x + BOX.w / 2, a.y + BOX.h, b.x + BOX.w / 2, b.y] : [a.x + BOX.w, a.y + BOX.h / 2, b.x, b.y + BOX.h / 2];
      return '<line class="pedge' + (e.kind === "conflict" ? " pconflict" : "") + '" x1="' + ends[0] + '" y1="' + ends[1] + '" x2="' + ends[2] + '" y2="' + ends[3] + '"/>';
    }).join("");
    const boxes = nodes.map(n => {
      const at = place[n.id];
      const name = Store().nodeName(n);
      return '<g class="pnode" data-state="' + esc(clean(n.state)) + '" transform="translate(' + at.x + "," + at.y + ')"><title>' + esc(name) + '</title><rect width="' + BOX.w + '" height="' + BOX.h + '" rx="8"/>' +
        '<text x="10" y="18" class="pn1">' + esc(short(name, 21)) + '</text><text x="10" y="34" class="pn2">' + esc(ask[n.id] ? "Waiting for your answer" : word(STATE_WORDS, n.state, "")) + "</text></g>";
    }).join("");
    return {width, height, body: lines + boxes};
  }
  function graphHtml(snap) {
    const s = isObj(snap) ? snap : {};
    const nodes = arr(s.nodes).filter(n => isObj(n) && n.role !== "planner");
    if (nodes.length === 0) return "";
    const edges = arr(s.edges);
    const deep = Store().depths(nodes, edges);
    const label = nodes.length + (nodes.length === 1 ? " step" : " steps") + " and the order they run in";
    const svg = (g, klass, hidden) => '<svg class="' + klass + '" ' + (hidden ? 'aria-hidden="true"' : 'role="img" aria-label="' + esc(label) + '"') + ' viewBox="0 0 ' + g.width + " " + g.height + '" width="' + g.width + '" height="' + g.height + '">' + g.body + "</svg>";
    return '<h2>The steps</h2><div class="pgraph">' + svg(drawGraph(nodes, edges, deep, false, asking(s)), "pflow-h", false) + svg(drawGraph(nodes, edges, deep, true, asking(s)), "pflow-v", true) + "</div>" +
      (edges.some(e => isObj(e) && e.kind === "conflict") ? '<p class="cnote">A dashed line means two steps use the same files, so one waits for the other.</p>' : "");
  }

  // What one step used, in the owner's units: calls, minutes, about how many dollars (D395). Nothing before it has made a call.
  function usedHtml(n) {
    if (!Number.isFinite(n.calls) || n.calls <= 0) return "";
    const parts = [n.calls + (n.calls === 1 ? " call" : " calls")];
    if (Number.isFinite(n.minutes)) parts.push(n.minutes < 1 ? "under a minute" : (n.minutes >= 10 ? Math.round(n.minutes) : n.minutes) + (n.minutes === 1 ? " minute" : " minutes"));
    parts.push(Number.isFinite(n.usd) ? "about $" + n.usd.toFixed(2) : "no price yet");          // calls with no dollar figure (Codex) are not "$0.00" (D406)
    return '<span class="cnote pused">Used: ' + esc(parts.join(", ")) + "</span>";
  }

  function stepsHtml(snap) {
    const s = isObj(snap) ? snap : {};
    const nodes = arr(s.nodes).filter(n => isObj(n) && n.role !== "planner");
    const byId = {};
    const ask = asking(s);
    nodes.forEach(n => { byId[n.id] = n; });
    const items = nodes.map(n => {
      const after = arr(n.depends_on).map(id => byId[id]).filter(Boolean).map(x => Store().nodeName(x));
      const waits = arr(s.edges).filter(e => isObj(e) && e.kind === "conflict" && e.to === n.id && byId[e.from]).map(e => Store().nodeName(byId[e.from]));
      const files = arr(n.scope).map(clean).filter(Boolean);
      return '<li class="pstep" data-state="' + esc(clean(n.state)) + '" data-node="' + esc(clean(n.id)) + '"><b>' + esc(Store().nodeName(n)) + "</b> " +
        '<span class="pstate">' + esc(ask[n.id] ? "Waiting for your answer" : word(STATE_WORDS, n.state, "")) + "</span>" +
        (n.attempt > 1 ? ' <span class="cnote">(try ' + esc(n.attempt) + ")</span>" : "") + usedHtml(n) +
        (after.length ? '<span class="cnote">Starts after: ' + esc(after.join(", ")) + "</span>" : "") +
        (waits.length ? '<span class="cnote">Shares files with, so waits for: ' + esc(waits.join(", ")) + "</span>" : "") +
        (files.length ? '<span class="cnote">May change: ' + esc(files.join(", ")) + "</span>" : "") +
        (clean(n.failure_reason) ? '<span class="pwhy">' + esc(sentence(stopWords(n.failure_reason, s.project))) + "</span>" : "") +
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
    const unpriced = isObj(s.spend) && Number.isFinite(s.spend.unpriced) && s.spend.unpriced > 0 ? s.spend.unpriced : 0;
    return '<h2>What it has used</h2><p class="pspend"><b>' + credits(calls) + "</b>" + (budget ? " of " + credits(budget) : "") + (usd !== null ? "; about $" + usd.toFixed(2) : "") + "</p>" +
      (usd !== null ? '<p class="cnote">The dollars are an estimate at list price. They include the planning of the project' + (unpriced ? "; " + (unpriced === 1 ? "1 call has" : unpriced + " calls have") + " no price, so it may be a little more" : "") + ".</p>" : "") +
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

  function auditHtml(rows, project) {
    const list = arr(rows).filter(isObj);
    if (list.length === 0) return '<h2>What happened</h2><p class="cempty">Nothing yet.</p>';
    const tools = list.some(r => r.action === "tool.used" && !/^other,/.test(clean(r.reason)));          // a tool of no kind (the engine's own PROPOSE) says nothing the owner can use (D394)
    return '<h2>What happened</h2>' + (tools ? '<p class="cnote">What a step used is written down when the step ends, so those lines carry the time it ended.</p>' : "") +
      '<ol class="plist paudit">' + list.filter(r => !(r.action === "tool.used" && /^other,/.test(clean(r.reason)))).slice().reverse().map(r => {
        const label = r.action === "tool.used" ? toolWords(r.reason) : word(ACTION_WORDS, r.action, "Something happened");
        const detail = reasonWords(r, project);
        return '<li data-seq="' + esc(r.seq) + '"><span class="cnote">' + esc(clock(r.at)) + "</span> <b>" + esc(label) + "</b>" + (detail ? " <span>" + esc(detail) + "</span>" : "") + "</li>";
      }).join("") + "</ol>";
  }

  // The run's own plumbing is not what a step produced: its files are the engine's, so a hand-off names only the rest (D383).
  const PLUMBING = freeze(["agent_live.json", "artifacts.json", "atoms.json", "audits.json", "autofix.json", "calls.jsonl", "changes.json", "chat.jsonl", "choices.json", "conditions.json", "conflicts.json",
    "deliverable.json", "events.jsonl", "goal.json", "handoff.accepted.json", "handoff.json", "inbox.jsonl", "live.json", "map.json", "needs.json", "node_context.json", "output.json", "outputs.jsonl",
    "receipts.jsonl", "report.json", "report.md", "run.stderr.log", "run.stdout.log", "settings.json", "snapshot.json", "status.json", "summary.json", "summary.txt", "task.json", "timing.json",
    "tools.jsonl", "trace.jsonl", "verdict.json", "workflows.json"]);          // the same list as `ENGINE_FILES` in engine/host/handoff.py, which a test keeps equal (D399)
  const ENGINE_WORDS = /rubric|done-when|necessary condition|workflow|\batoms?\b|\bJ2\b|checks? (?:pass|fail)/i;
  const names = (list, n) => (list.length <= n ? list.join(", ") : list.slice(0, n).join(", ") + " and " + (list.length - n) + " more");
  // What a hand-off says in plain words: that the step handed in its work, and which files it made. What the engine wrote as the step's summary is not shown (it is the engine's words).
  function handoffText(body) {
    const files = arr(body.files).map(f => (isObj(f) ? clean(f.path) : "")).filter(f => f && PLUMBING.indexOf(f) < 0);
    const changed = arr(body.changes).map(clean).filter(Boolean);
    const open = body.status === "done_with_open_items";
    return "handed in its work" + (open ? ", with some things left open" : "") + (files.length ? ". It wrote " + names(files.map(f => OWN_FILES[f] || f), 4) : "") + "." +
      (changed.length ? " It changed " + (changed.length === 1 ? "1 file" : changed.length + " files") + " in your folder: " + names(changed, 3) + "." : "");
  }
  function textOf(body) {
    if (typeof body === "string") return ENGINE_WORDS.test(body) ? "" : clean(body);
    if (isObj(body)) {
      if (Array.isArray(body.files) && typeof body.node_id === "string") return handoffText(body);
      const said = clean(body.summary || body.text || body.message || "");
      return ENGINE_WORDS.test(said) ? "" : said;
    }
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
      const opinion = isObj(m.body) && Object.prototype.hasOwnProperty.call(OPINION_WORDS, m.body.verdict) ? "gave its opinion: " + OPINION_WORDS[m.body.verdict] + ". " : "";
      const text = opinion + textOf(m.body);
      return '<li data-seq="' + esc(m.seq) + '"><b>' + esc(name(from)) + "</b> " + esc(text.length > 240 ? text.slice(0, 240) + "..." : text || "(handed in its work)") + "</li>";
    }).join("") + "</ol>";
  }

  // The whole page body, in the order the owner needs it: what waits for them first, the picture, the steps, what it cost, who decided, what happened.
  function page(state, location) {
    const S = isObj(state) ? state : {};
    if (!S.snapshot) return '<p class="' + (S.error ? "cerr" : "cempty") + '">' + esc(S.error || "Loading...") + "</p>";
    const St = Store();
    return (S.error ? '<p class="cerr" role="alert">' + esc(S.error) + "</p>" : "") + noteHtml(location) + whyHtml(S.snapshot) + cardsHtml(S.snapshot) + graphHtml(S.snapshot) + stepsHtml(S.snapshot) + spendHtml(S.snapshot) +
      decidedHtml(St.decidedList(S.audit)) + auditHtml(S.audit, S.snapshot.project) + messagesHtml(S.messages, S.snapshot);
  }

  const ProjectView = {reasonWords, stopWords, toolWords, handoffText, PLUMBING, STATUS_WORDS, STATE_WORDS, ANSWERS, ACTION_WORDS, POLICY_WORDS, esc, header, whyHtml, noteHtml, cardsHtml, graphHtml, stepsHtml, spendHtml, decidedHtml, auditHtml, messagesHtml, page, clock};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ProjectView;
  else root.ProjectView = ProjectView;
})(globalThis);
