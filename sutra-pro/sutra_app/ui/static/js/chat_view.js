/* chat_view.js - the pure core of a node's chat (work package UI-6; docs/design/ui.md sections 6.5, 6.6, 7 and 10; S2-models-09, S4-fnodes-06,
   S4-fnodes-12).

   Strings in, strings out: transcript() draws a session's messages in J2's bubble look (.sb.team, .sb.me, .opts), card() draws one chat card
   (task, chart_change, approval, choice, needs_you, done and, in a function node's working log, atom), composerState() says whether the
   message box shows, is disabled and what it says, whoLabel() names an author, and safeText() is the one door a message text goes through.
   Nothing touches the DOM, every word that came from the wire is escaped, and the markup is well formed XML.

   safeText escapes first and then allows three things the text asked for in plain marks: **bold**, `code` and line breaks. It makes no link,
   no image and no other tag, so a message cannot put markup on the page (docs/design/ui.md section 4.3). One kind of line reads more: a model's
   reply to a direct line (an agent text message with `turn` set) goes through ChatMarkdown.render (chat_markdown.js, GAP-markdown) when that
   script is on the page: escaped first too, then paragraphs, lists, code blocks, tables, headings and quotes, and still no link and no HTML.
   Every other line (the owner's, a team's, Sutra's, a note, an error, a card) keeps safeText.

   Buttons carry data-act (open-team, show-node, show-change, choose, option, answer-option, answer, retry, retry-task, retry-direct) and the data they need; the page that
   shows the transcript (the node panel, Home) listens for them. A link that opens a team page is a real <a href>, so it also works without a script.

   A classic script with ONE global, ChatView (see sutra_ctx.js for why); in node it is module.exports. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;

  /* ---------------------------------------------------------------- small helpers */
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const text = v => (typeof v === "string" ? v : (finite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  // Words from the wire on one line: control characters and runs of white space become one space.
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const DOT = " \u00b7 ";

  /* ---------------------------------------------------------------- words */
  // The author labels (docs/design/ui.md 6.5). The owner reads prose from an Identity only; every other label belongs to a record written by code
  // (Sutra) or to a function's working log and J2's Detailed view.
  const WHO = freeze({user: "You", sutra: "Sutra", identity: "Client Lead (Identity)", adaptation: "Strategist (Adaptation)", priority: "Prioritiser (Priority)",
    coordination: "Scheduler (Coordination)", audit: "Quality Reviewer (Audit)", validator: "Validator", system: "System"});
  const PERSONA = freeze({identity: "Client Lead", adaptation: "Strategist", priority: "Prioritiser", coordination: "Scheduler", audit: "Quality Reviewer"});
  const PROVIDERS = freeze({claude: "Claude", codex: "Codex", stub: "stub"});
  const TASK_WORDS = freeze({queued: "queued", starting: "starting", running: "running", waiting_user: "waiting for you", done: "done",
    done_with_open_items: "done, with open items", stopped: "stopped", crashed: "crashed"});
  const KIND_WORDS = freeze({department: "team", division: "division", root: "root", function: "function", step: "step"});
  const BUSY = "The team is working. You can write again when it asks you something or is done";
  const ONE_AT_A_TIME = "I answer your messages one at a time.";
  const DEFAULT_PLACEHOLDER = "Write a message\u2026";

  // whoLabel(who, ctx) -> "Client Lead (Identity)". ctx {deptName}: the department's name goes in front of an Identity ("Web . Client Lead
  // (Identity)") where the author would otherwise be unclear, in the org chat and on cards. W-3 is "W-3 Builder". An author this table does not
  // know ("team:designer") is shown as it came, without the "team:".
  function whoLabel(who, ctx) {
    const w = clean(who);
    let base;
    if (hasOwn(WHO, w)) base = WHO[w];
    else if (/^W-\d+$/.test(w)) base = w + " Builder";
    else base = w.replace(/^team:/i, "");
    const dept = isObj(ctx) ? clean(ctx.deptName) : "";
    return w === "identity" && dept !== "" ? dept + DOT + base : base;
  }

  /* ---------------------------------------------------------------- safeText */
  // safeText(text) -> html. Escapes every character that could open a tag, then `code` and **bold** (never across a code span or a line) and line
  // breaks. The only tags it can write are <b>, <code> and <br/>.
  function safeText(value) {
    const escaped = esc(text(value));
    return escaped.split(/(`[^`\n]+`)/).map((part, i) => (i % 2 === 1 ? "<code>" + part.slice(1, -1) + "</code>" : part.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")))
      .join("").replace(/\r\n|\r|\n/g, "<br/>");
  }

  // An owner's direct line that carried files ends with "(attached: a.png, b.pdf)" (orchestrator/direct_turns.py attached_line): attachedOf splits it
  // into the words and the names, so the bubble shows the names as chips and a Retry sends the words alone.
  const ATTACHED = /\n\(attached: ([^\n]+)\)$/;
  function attachedOf(value) {
    const t = text(value);
    const m = ATTACHED.exec(t);
    if (!m) return {text: t, names: []};
    return {text: t.slice(0, m.index), names: m[1].split(", ").map(clean).filter(Boolean).slice(0, 10)};
  }
  const FILE_TILE = name => (/\.(png|jpe?g|gif|webp)$/i.test(name) || name === "an image" ? "IMG" : (/\.pdf$/i.test(name) || name === "a PDF" ? "PDF" : "TXT"));
  const attachedHtml = names => (names.length === 0 ? "" : '<ul class="cattached" aria-label="Attached files">' +
    names.map(n => '<li><span class="cctile" aria-hidden="true">' + FILE_TILE(n) + "</span>" + esc(n) + "</li>").join("") + "</ul>");

  // The agents address each other with a leading "@Name" (J2's chat). The owner reads the sentence, not the address, so the tag is dropped from
  // what the owner reads; a working log keeps it.
  const stripTag = value => text(value).replace(/^\s*@[\w-]+[,:]?[ \t]*/, "");

  /* ---------------------------------------------------------------- a question with options (J2's parseAsk, j2_ui.html:1070) */
  const OPTION = /^\s+Option \d+: (.*?)(?: \[adds \d+ (?:units|work credits)[^\]]*\])?$/;
  const OPTION_START = /^\s+Option \d+: /;
  const OPTION_TAIL = / \[adds \d+ (?:units|work credits)[^\]]*\]$/;
  const NOT_A_QUESTION = /^-|^Still not right|^Some parts|^I couldn't tell/;

  // parseAsk(text) -> {say, qs: [{q, opts}]} from "@Requester say\n1. question\n   Option 1: text" (one unnumbered question: the line above its
  // options). Lines after the first question that are neither a question nor an option are dropped, as J2 drops them.
  function parseAsk(value) {
    const qs = [];
    const say = [];
    text(value).split("\n").forEach(line => {
      let m;
      if ((m = line.match(/^(\d+)\. (.*)$/))) qs.push({q: m[2], opts: []});
      else if ((m = line.match(OPTION)) && qs.length) qs[qs.length - 1].opts.push(m[1]);
      else if (OPTION_START.test(line) && !qs.length) {
        const q = say.length && !NOT_A_QUESTION.test(say[say.length - 1]) ? say.pop() : "";
        qs.push({q, opts: [line.replace(OPTION_START, "").replace(OPTION_TAIL, "")]});
      } else if (!qs.length) say.push(line);
    });
    return {say: say.join("\n"), qs};
  }

  function optionButtons(ask, i) {
    return '<div class="opts" data-q="' + (i + 1) + '" data-n="' + ask.qs.length + '">' + ask.qs[i].opts.map((o, j) =>
      '<button type="button" data-act="option" data-opt="' + (j + 1) + '">' + esc(clean(o)) + "</button>").join("") + "</div>";
  }

  // The inside of a question's bubble: what the agent said, the question once and its option buttons (no numbered list) when the question is
  // still open; a question without options is a numbered list.
  function askHtml(value, live) {
    const ask = parseAsk(value);
    const say = stripTag(ask.say).trim();
    let html = say === "" ? "" : safeText(say);
    if (ask.qs.length === 1 || ask.qs.some(q => q.opts.length)) {
      ask.qs.forEach((q, i) => { html += '<p class="sq">' + safeText(stripTag(q.q)) + "</p>" + (live && q.opts.length ? optionButtons(ask, i) : ""); });
    } else if (ask.qs.length) {
      html += "<ol>" + ask.qs.map(q => "<li>" + safeText(stripTag(q.q)) + "</li>").join("") + "</ol>";
    }
    return html;
  }

  /* ---------------------------------------------------------------- cards */
  const taskWord = status => (hasOwn(TASK_WORDS, status) ? TASK_WORDS[status] : clean(status).replace(/_/g, " "));
  const teamHref = (deptId, view) => "/d/" + encodeURIComponent(deptId) + "/?view=" + (view || "simple");
  const nameOf = item => (isObj(item) ? clean(item.name) || clean(item.id) : clean(item));

  function openTeam(deptId, extra) {
    return deptId !== "" ? '<a class="lbtn" data-act="open-team" href="' + esc(teamHref(deptId)) + '">Open the team</a>'
      : '<button type="button" class="lbtn" data-act="open-team"' + (extra || "") + ">Open the team</button>";
  }

  function taskCard(c) {
    const dept = clean(c.dept_name);
    const deptId = clean(c.dept_id);
    const status = clean(c.status);
    return '<div class="ncard ready c-task" data-card="task" data-task="' + esc(clean(c.task_id)) + '" data-dept="' + esc(deptId) + '">' +
      "<h2>Your " + (dept ? esc(dept) + " " : "") + "team is on it</h2>" +
      '<p class="ctitle">' + esc(clean(c.title)) + (status ? ' <span class="cstat st-' + esc(status) + '">' + esc(taskWord(status)) + "</span>" : "") + "</p>" +
      '<div class="acts">' + openTeam(deptId, ' data-task="' + esc(clean(c.task_id)) + '"') +
      (deptId !== "" ? ' <button type="button" class="lbtn" data-act="show-node" data-node="' + esc(deptId) + '">See it on the graph</button>' : "") + "</div></div>";
  }

  // The lists of a chart_change card: {id, name, kind} added, {id, name, from_name, to_name} moved, {id, name, into_name} merged. A plain id is
  // a name too (the older shape).
  function changeLines(c) {
    const lines = [];
    (Array.isArray(c.added) ? c.added : []).forEach(x => {
      const kind = isObj(x) ? clean(x.kind) : "";
      lines.push(["Added", nameOf(x) + (kind ? " (" + (hasOwn(KIND_WORDS, kind) ? KIND_WORDS[kind] : kind) + ")" : "")]);
    });
    (Array.isArray(c.moved) ? c.moved : []).forEach(x => {
      const route = isObj(x) && (clean(x.from_name) || clean(x.to_name)) ? ", from " + (clean(x.from_name) || "its place") + " to " + (clean(x.to_name) || "a new place") : "";
      lines.push(["Moved", nameOf(x) + route]);
    });
    (Array.isArray(c.archived) ? c.archived : []).forEach(x => lines.push(["Merged", nameOf(x) + (isObj(x) && clean(x.into_name) ? " into " + clean(x.into_name) : "")]));
    return lines;
  }

  function changeRef(c) {
    const id = clean(c.change_id);
    const m = /(\d+)$/.exec(id);
    const seq = finite(c.seq) ? c.seq : (finite(c.change_seq) ? c.change_seq : (m ? Number(m[1]) : null));
    return (id !== "" ? ' data-change="' + esc(id) + '"' : "") + (seq !== null ? ' data-seq="' + seq + '"' : "");
  }

  function chartChangeCard(c) {
    const lines = changeLines(c);
    return '<div class="ncard c-chart" data-card="chart_change" data-decision="' + esc(clean(c.decision)) + '" data-pending="' + (c.pending === true) + '"' + changeRef(c) + ">" +
      '<p class="csum">' + esc(clean(c.summary)) + "</p>" +
      (lines.length ? '<ul class="clist">' + lines.map(l => "<li>" + l[0] + ": " + esc(l[1]) + "</li>").join("") + "</ul>" : "") +
      (c.pending === true ? '<p class="cpend">Waiting for your yes or no.</p>' : "") +
      '<div class="acts"><button type="button" class="lbtn" data-act="show-change"' + changeRef(c) + ">Show in the org chart</button></div></div>";
  }

  // Options are {id, label} or plain strings; the label text is what is sent back (docs/design/orchestrator.md 3.3).
  function optionList(options) {
    return (Array.isArray(options) ? options : []).map(o => (isObj(o) ? {id: clean(o.id), label: clean(o.label) || clean(o.id)} : {id: "", label: clean(o)})).filter(o => o.label !== "");
  }

  // What a yes would do (ApprovalCard.impact, written by code in orchestrator/reorg_preview.py): at most 8 lines of 160 characters, shown while the card is open.
  const impactList = (c, done) => {
    const lines = done || !Array.isArray(c.impact) ? [] : c.impact.map(clean).filter(Boolean).slice(0, 8).map(l => l.slice(0, 160));
    return lines.length ? '<ul class="cimpact" aria-label="What a yes would do">' + lines.map(l => "<li>" + esc(l) + "</li>").join("") + "</ul>" : "";
  };

  function choiceCard(c, ctx, type) {
    const options = optionList(c.options);
    const answer = clean(ctx.answer);
    const done = answer !== "" || ctx.answered === true;
    return '<div class="ncard c-' + type + '" data-card="' + type + '"' + changeRef(c) + (done ? ' data-answered="true"' : "") + ">" +
      '<p class="sq">' + safeText(clean(c.question)) + "</p>" + (type === "approval" ? impactList(c, done) : "") +
      (done ? '<p class="canswer">' + (answer ? "You answered: <b>" + esc(answer) + "</b>" : "Answered") + "</p>"
        : '<div class="opts">' + options.map(o => '<button type="button" data-act="choose" data-id="' + esc(o.id) + '" data-option="' + esc(o.label) + '">' + esc(o.label) + "</button>").join("") + "</div>") +
      "</div>";
  }

  // The team's Identity question, as it said it. The answer goes to the DEPARTMENT's session (data-session, from ctx.deptSession), never to the org chat.
  function needsYouCard(c, ctx) {
    const dept = clean(c.dept_name);
    const ask = parseAsk(c.text);
    const labels = optionList(c.options).map(o => o.label);
    const options = labels.length ? labels : (ask.qs.length ? ask.qs[0].opts.map(clean) : []);
    const say = stripTag(ask.say).trim();
    const question = ask.qs.map(q => stripTag(q.q)).filter(Boolean).join("\n");
    const body = [say, question].filter(Boolean).join("\n") || stripTag(c.text).trim();
    const answered = ctx.answered === true;
    const session = clean(ctx.deptSession);
    return '<div class="ncard c-needs" data-card="needs_you" data-dept="' + esc(clean(c.dept_id)) + '" data-question="' + esc(clean(c.question_message_id)) + '"' +
      (session ? ' data-session="' + esc(session) + '"' : "") + (answered ? ' data-answered="true"' : "") + ">" +
      '<h2 class="cask">' + (dept ? esc(dept) + " has a question for you" : "A team has a question for you") + "</h2>" +
      '<p class="cquestion">' + safeText(body) + "</p>" +
      (answered ? '<p class="canswer">Answered</p>'
        : (options.length ? '<div class="opts" data-n="1">' + options.map((o, i) => '<button type="button" data-act="answer-option" data-opt="' + (i + 1) + '" data-text="' + esc(o) + '">' + esc(o) + "</button>").join("") + "</div>" : "") +
          '<div class="row cans"><textarea class="canswerbox" aria-label="Your answer" placeholder="Or type your own answer\u2026"></textarea><button type="button" class="send" data-act="answer">Answer</button></div>') +
      "</div>";
  }

  const DONE_TONE = freeze({done: "ok", done_with_open_items: "warn", crashed: "bad", stopped: "bad"});
  const DONE_HEAD = freeze({done: "is done", done_with_open_items: "is done, with some things left open", crashed: "ran into a problem", stopped: "was stopped"});

  // Try again on a done card while the Heads up lane offers it (ctx.retry, from opts.retryTasks): it goes when the task was retried or replaced.
  const retryButton = (c, ctx) => (isObj(ctx) && ctx.retry === true && /^tsk_[0-9a-f]{12}$/.test(clean(c.task_id)) ?
    '<button type="button" class="lbtn" data-act="retry-task" data-task="' + esc(clean(c.task_id)) + '">Try again</button>' : "");

  function doneCard(c, ctx) {
    const status = clean(c.status);
    const tone = hasOwn(DONE_TONE, status) ? DONE_TONE[status] : "warn";
    const dept = clean(c.dept_name);
    const deptId = clean(c.dept_id);
    return '<div class="ncard ' + (tone === "bad" ? "oops" : "ready") + " " + tone + ' c-done" data-card="done" data-tone="' + tone + '" data-task="' + esc(clean(c.task_id)) + '">' +
      "<h2>Your " + (dept ? esc(dept) + " " : "") + "team " + esc(hasOwn(DONE_HEAD, status) ? DONE_HEAD[status] : taskWord(status)) + "</h2>" +
      '<p class="ctitle">' + esc(clean(c.title)) + "</p>" + (clean(c.outcome) ? '<p class="coutcome">' + safeText(clean(c.outcome)) + "</p>" : "") +
      receiptLine(c.receipt) +
      '<div class="acts">' + retryButton(c, ctx) + openTeam(deptId, ' data-task="' + esc(clean(c.task_id)) + '" data-dept-name="' + esc(dept) + '"') + "</div></div>";
  }

  // The receipt of a finished task, evidence only (GAP-model-quality): "Attempt 2 . Took 6 min . about $0.42 . 7 of 8 items passed their checks".
  // No dollar figure under half a cent (the old rule) and "about", because the ledger's figure is a floor (a failed call has no cost); without
  // one, the tokens (a Codex-only task); no atoms, no checks part, so the card never gives a verdict it was not given. No receipt, nothing.
  const count = v => (finite(v) && v >= 0 ? Math.floor(v) : null);
  const grouped = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  function tookText(seconds) {
    const s = Math.floor(seconds);
    if (s < 60) return s + " s";
    const m = Math.floor(s / 60);
    if (m < 60) return m + " min";
    const h = Math.floor(m / 60);
    return h < 48 ? h + " h" + (m % 60 ? " " + (m % 60) + " min" : "") : Math.floor(h / 24) + " days";
  }
  function receiptLine(r) {
    if (!isObj(r)) return "";
    const parts = [];
    const attempt = count(r.attempt);
    const seconds = count(r.seconds);
    const tokens = count(r.tokens);
    const total = count(r.checks_total);
    if (attempt !== null && attempt >= 2) parts.push("Attempt " + attempt);
    if (seconds !== null) parts.push("Took " + tookText(seconds));
    if (finite(r.usd) && r.usd >= 0.005) parts.push("about $" + r.usd.toFixed(2));
    else if (tokens !== null && tokens > 0) parts.push(grouped(tokens) + " tokens");
    if (total !== null && total > 0) parts.push(Math.min(count(r.checks_passed) || 0, total) + " of " + total + " items passed their checks");
    return parts.length ? '<p class="creceipt">' + esc(parts.join(DOT)) + "</p>" : "";
  }

  // A function node's own working log gets one card per atom transition (a record written by code): its label as the title, the goal and the rows.
  function atomCard(c) {
    const outcome = clean(c.outcome);
    const rows = (Array.isArray(c.rows) ? c.rows : []).filter(isObj);
    return '<div class="ncard c-atom o-' + esc(outcome || "unknown") + '" data-card="atom" data-outcome="' + esc(outcome) + '" data-atom="' + esc(clean(c.atom_id)) + '">' +
      '<h4 class="alabel">' + esc(clean(c.label) || outcome.toUpperCase()) + "</h4>" + (clean(c.goal) ? '<p class="agoal">' + esc(clean(c.goal)) + "</p>" : "") +
      (rows.length ? "<dl>" + rows.map(r => "<dt>" + esc(clean(r.label)) + "</dt><dd>" + esc(clean(r.text)) + "</dd>").join("") + "</dl>" : "") + "</div>";
  }

  // A card of a type this module does not know is plain text: the first sentence the card carries, or nothing.
  function plainCard(c) {
    const said = ["text", "summary", "title", "question", "message", "label"].map(k => clean(c[k])).find(Boolean) || "";
    return '<div class="ncard c-unknown" data-card="unknown">' + safeText(said) + "</div>";
  }

  // card(card, ctx) -> html of one card. ctx {deptName, answered, answer, deptSession, sessionKind}: `answered` and `answer` close an approval, a
  // choice or a needs_you card; an atom card is drawn only in a function node's session (ctx.sessionKind "function"; elsewhere it is plain text).
  function card(value, ctx) {
    if (!isObj(value)) return "";
    const c = isObj(ctx) ? ctx : {};
    switch (clean(value.type)) {
      case "task": return taskCard(value);
      case "chart_change": return chartChangeCard(value);
      case "approval": return choiceCard(value, c, "approval");
      case "choice": return choiceCard(value, c, "choice");
      case "needs_you": return needsYouCard(value, c);
      case "done": return doneCard(value, c);
      case "atom": return c.sessionKind === "function" ? atomCard(value) : plainCard(Object.assign({}, value, {text: clean(value.label) + (clean(value.goal) ? ": " + clean(value.goal) : "")}));
      default: return plainCard(value);
    }
  }

  /* ---------------------------------------------------------------- the transcript */
  // The class of a message: the owner's own line, a note (a merge, a move), an error, a log line of the system, or a bubble of the team.
  function bubbleClass(m) {
    const kind = clean(m.kind) || "text";
    if (kind === "error") return "nmsg oops";
    if (kind === "note") return "nmsg note";
    if (clean(m.role) === "user" || clean(m.who) === "user") return "nmsg sb me";
    if (clean(m.who) === "system" && kind === "text") return "nmsg sys";
    return "nmsg sb team";
  }

  // answersOf(messages, o) -> {message id: the answer}: the cards of a transcript the owner has dealt with, for transcript()'s `answers`. An answer is
  // the words of the owner line that answered ("Yes"), or "" for a card that reads just "Answered". o {local, needs, needsLoaded}: `local` is what the
  // owner clicked on this page; a card the server says was answered (`answered_by`, the owner line of a pressed button; an approval decided without
  // one points at itself, so it has no words) is answered after a reload too; and a team question that the list of /api/needs-you no longer holds is
  // answered, once that list was read.
  function answersOf(messages, o) {
    const opts = isObj(o) ? o : {};
    const list = Array.isArray(messages) ? messages.filter(isObj) : [];
    const needs = Array.isArray(opts.needs) ? opts.needs.filter(isObj) : [];
    const out = Object.assign({}, isObj(opts.local) ? opts.local : {});
    list.forEach(m => {
      if (clean(m.kind) !== "card" || !isObj(m.card) || hasOwn(out, m.id)) return;
      const c = m.card;
      if (m.answered_by !== null && m.answered_by !== undefined) {
        const line = list.find(x => x.id === m.answered_by && x.id !== m.id && (clean(x.role) === "user" || clean(x.who) === "user"));
        out[m.id] = line ? clean(line.text) : "";
      } else if (clean(c.type) === "needs_you" && opts.needsLoaded === true &&
        !needs.some(n => String(n.message_id) === String(c.question_message_id) && (!n.dept_id || !c.dept_id || n.dept_id === c.dept_id))) {
        out[m.id] = "";
      }
    });
    return out;
  }

  // A model's reply to the owner's direct line (D115): ChatMessageOut.turn names the line it answers. Its error line and notes are not replies.
  const directReply = m => clean(m.role) === "agent" && (clean(m.kind) || "text") === "text" && Number.isInteger(m.turn) && m.turn > 0;

  // transcript(session, messages, opts) -> the html of every message, oldest first. session {kind, writable, status}; opts {deptName, live, answers,
  // deptSessions}: `deptName` is the department the session belongs to, `live` false closes every question, `answers` maps a message id to the
  // answer the owner gave an approval, a choice or a needs_you card, `deptSessions` maps a department id to its session id (a needs_you card answers
  // there). Option buttons are on only for the last open question of a session the owner can write in. In an org session and on cards, an Identity
  // carries the department's name. opts.retryTasks {task_id: true} puts Try again (data-act retry-task) on those tasks' done cards (gap attention).
  function transcript(session, messages, opts) {
    const s = isObj(session) ? session : {};
    const o = isObj(opts) ? opts : {};
    const list = (Array.isArray(messages) ? messages : []).filter(isObj);
    if (list.length === 0) return '<p class="empty nempty">' + esc(s.writable === false ? "Nothing in this log yet." : "No messages yet.") + "</p>";
    const answers = isObj(o.answers) ? o.answers : {};
    const sessions = isObj(o.deptSessions) ? o.deptSessions : {};
    const canAnswer = o.live !== false && s.writable !== false && clean(s.status) !== "archived";
    let lastOpen = -1;
    list.forEach((m, i) => { if (clean(m.kind) === "question" && (m.answered_by === null || m.answered_by === undefined)) lastOpen = i; });
    // a direct turn that failed offers Retry while its line is the owner's newest (a later line makes an old retry confusing)
    const lastOwn = list.reduce((n, m) => ((clean(m.role) === "user" || clean(m.who) === "user") && Number.isInteger(m.id) && m.id > n ? m.id : n), 0);
    const retryOf = m => (canAnswer && clean(m.kind) === "error" && Number.isInteger(m.turn) && m.turn === lastOwn
      ? ' <button type="button" class="linkbtn" data-act="retry-direct" data-turn="' + m.turn + '">Retry</button>' : "");
    const log = clean(s.kind) === "function" || clean(s.kind) === "step";                 // a working log shows the agents' addresses as they are
    let asked = null;
    return list.map((m, i) => {
      const kind = clean(m.kind) || "text";
      const who = clean(m.who);
      const cardIn = kind === "card" && isObj(m.card) ? m.card : null;
      const dept = (cardIn && clean(cardIn.dept_name)) || clean(o.deptName);
      const label = whoLabel(who, {deptName: clean(s.kind) === "org" || cardIn ? dept : ""});
      const attrs = ' data-id="' + esc(text(m.id)) + '" data-who="' + esc(who) + '" data-kind="' + esc(kind) + '" data-state="' + esc(clean(m.state) || "ok") + '"';
      const klass = bubbleClass(m) + (clean(m.state) === "pending" ? " pending" : "");
      if (bubbleClass(m) === "nmsg sb me") {
        const picked = /^Option (\d+)$/.exec(text(m.text).trim());
        const chosen = picked && asked && asked.qs[0] && asked.qs[0].opts[Number(picked[1]) - 1];
        const failed = clean(m.state) === "error";
        const att = attachedOf(m.text);
        return '<div class="' + klass + (failed ? " failed" : "") + '"' + attrs + ">" + safeText(chosen ? clean(chosen) : att.text) + attachedHtml(att.names) +
          (failed ? '<div class="nerr">Something went wrong. Try again.' + (clean(s.kind) === "org" ? ' <button type="button" class="linkbtn" data-act="retry">Retry</button>' : "") + "</div>" : "") + "</div>";
      }
      if (kind === "note" || kind === "error" || bubbleClass(m) === "nmsg sys") return '<div class="' + klass + '"' + attrs + ">" + safeText(text(m.text)) + retryOf(m) + "</div>";
      if (cardIn) {
        const ctx = {deptName: dept, sessionKind: clean(s.kind), answer: answers[m.id], answered: answers[m.id] !== undefined,
          deptSession: sessions[clean(cardIn.dept_id)], retry: isObj(o.retryTasks) && o.retryTasks[clean(cardIn.task_id)] === true};
        return '<div class="' + klass + '"' + attrs + "><small>" + esc(label) + "</small>" + card(cardIn, ctx) + "</div>";
      }
      const body = log ? text(m.text) : stripTag(m.text);
      let inner;
      if (kind === "question" && !log) {
        asked = parseAsk(body);
        inner = askHtml(body, canAnswer && i === lastOpen);
      } else if (directReply(m) && root.ChatMarkdown) {
        inner = root.ChatMarkdown.render(text(m.text));                 // as the model wrote it: an "@name" at its start is not an agent's address
      } else {
        inner = safeText(body);
      }
      // a settled provider turn: its tool calls fold into ONE row (ChatFold, ABS-10); nothing is drawn while the message is pending
      if (root.ChatFold && Array.isArray(m.blocks) && m.blocks.length > 0) inner += root.ChatFold.fold(m.blocks, {settled: clean(m.state) !== "pending"});
      return '<div class="' + klass + '"' + attrs + "><small>" + esc(label) + "</small>" + inner + "</div>";
    }).join("");
  }

  /* ---------------------------------------------------------------- the message box */
  // composerState(session, turn) -> {hidden, disabled, placeholder, note}. session is a ChatSessionOut ({kind, title, writable, status, note}), turn
  // {busy, asking, blocked}: `busy` the team of a department or division chat is working (the server would answer 409), `asking` a question is open,
  // `blocked` a sentence that closes the box for another reason (no access token, the app is not responding). First match wins:
  //   no session            hidden
  //   archived              hidden, the session's own note ("Merged into Web")
  //   not writable          hidden, "Read-only: this is the working log of <persona or title>."
  //   blocked               shown, disabled, the sentence
  //   busy                  org chat: open, "I answer your messages one at a time."; a department or division: disabled with the server's sentence
  //   otherwise             open; "Or type your own answer..." while a question is open, else "Write a message..."
  function composerState(session, turn) {
    const none = {hidden: true, disabled: true, placeholder: "", note: ""};
    if (!isObj(session)) return none;
    const t = isObj(turn) ? turn : {};
    if (clean(session.status) === "archived") {
      return {hidden: true, disabled: true, placeholder: "", note: clean(session.note) || "This chat is archived. Its history stays available."};
    }
    if (session.writable !== true) {
      const title = clean(session.title);
      const lower = title.toLowerCase();
      const who = hasOwn(PERSONA, lower) ? PERSONA[lower] : title;
      return {hidden: true, disabled: true, placeholder: "", note: "Read-only: this is the working log of " + (who || "this node") + "."};
    }
    const placeholder = t.asking === true ? "Or type your own answer\u2026" : DEFAULT_PLACEHOLDER;
    if (clean(t.blocked) !== "") return {hidden: false, disabled: true, placeholder, note: clean(t.blocked)};
    if (t.busy === true) {
      if (clean(session.kind) === "org") return {hidden: false, disabled: false, placeholder, note: ONE_AT_A_TIME};
      return {hidden: false, disabled: true, placeholder: "The team is working\u2026", note: BUSY};
    }
    return {hidden: false, disabled: false, placeholder, note: ""};
  }

  const providerLabel = connector => (hasOwn(PROVIDERS, connector) ? PROVIDERS[connector] : clean(connector));

  const ChatView = {transcript, card, answersOf, composerState, safeText, whoLabel, parseAsk, stripTag, providerLabel, attachedOf, BUSY, ONE_AT_A_TIME, PROVIDERS, PERSONA};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatView;
  else root.ChatView = ChatView;
})(globalThis);
