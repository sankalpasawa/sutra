/* front_door.js - Home's front door: what needs the owner right now, then what is running and what finished (the one-front brief).

   Strings in, strings out, like heads_up_view.js: nothing touches the DOM and every word from the wire is escaped. home.js owns the fetches, the
   events and the clicks; this file only says what the front door shows for a given state and level.

     LEVELS                              ["simple", "manager", "debug"]: what the owner sees (SutraCtx.level() reads and stores it)
     buckets(departments, heads, seen)   {running, done, idle}: teams at work (working, waiting, a problem), work finished (a done team, or a
                                         Heads up "finished" row of the last day), and the rest (idle, not started). A team is in one bucket only.
     needCard(item, opts)                one card per GET /api/needs-you item: the team, how long it waited, the question, and the answer in place
                                         (option buttons, or a box and Send) with "Open" to the team page; an approval has Approve and Not now.
                                         opts {elapsedMs, busy, error}
     problemCard(row)                    one card per Heads up problem the owner has not marked "Got it": Try again, Open team, Got it
     needsHtml(state)                    the "Needs you" section: the cards, or the calm empty line with what is running
     listsHtml(state)                    "In progress" and "Done recently" (and the folded "Other teams"), each row a link to the team page
     navHtml(level)                      the extra views the level adds (Manager: org chart, workflow graph, team chats; Debug: also settings,
                                         usage and log, and the Raw AI chat hook)
     debugHtml(state)                    Debug only: the whole Heads up lane (problems, quiet teams, finished work), from HeadsUpView
     latestHtml(state)                   the last word of the org chat after the owner sent something here: a sentence, or a choice to press
     summary(state)                      "2 things need you" / "Nothing needs you right now" (the document title and the screen reader line)

   Buttons carry data-act: fd-option (data-msg, data-opt, data-text), fd-answer (data-msg), fd-approve and fd-decline (data-msg), fd-retry
   (data-task), fd-seen (data-task), fd-chat (data-node), fd-go (data-pane), fd-choose (data-msg, data-option), fd-hook (data-hook),
   fd-conversation. A team link is a real <a href="/d/<dept>/?view=simple">.
   A classic script with ONE global, FrontDoor; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ID = /^[A-Za-z0-9_.:-]{1,120}$/;
  const idOf = v => (ID.test(text(v)) ? text(v) : "");
  const teamHref = id => "/d/" + encodeURIComponent(id) + "/?view=simple";

  const LEVELS = ["simple", "manager", "debug"];
  const at = (level, min) => LEVELS.indexOf(level) >= LEVELS.indexOf(min);
  const ORG = "cs_org";
  const DONE_SHOWN = 5;
  const RUNNING = ["running", "waiting", "waiting_on_you", "fault"];
  const DONE = ["filed", "done_unchecked", "left_open"];
  const WORDS = {running: "working", waiting: "waiting", waiting_on_you: "waiting on you", fault: "has a problem", filed: "done",
    done_unchecked: "done, not checked", left_open: "done, with open items", idle: "idle", not_made: "not started"};
  const word = status => (Object.prototype.hasOwnProperty.call(WORDS, status) ? WORDS[status] : "idle");

  const HV = () => root.HeadsUpView || (typeof require === "function" ? safeRequire("./heads_up_view.js") : null);
  const CV = () => root.ChatView || (typeof require === "function" ? safeRequire("./chat_view.js") : null);
  function safeRequire(name) { try { return require(name); } catch (e) { return null; } }

  /* ---------------------------------------------------------------- the teams */
  function buckets(departments, heads, seen) {
    const out = {running: [], done: [], idle: []};
    const placed = new Set();
    (Array.isArray(departments) ? departments : []).filter(d => isObj(d) && idOf(d.id)).forEach(d => {
      const row = {id: d.id, name: clean(d.name) || d.id, status: text(d.node_status), words: word(d.node_status), purpose: clean(d.purpose)};
      if (RUNNING.includes(d.node_status)) out.running.push(row);
      else if (DONE.includes(d.node_status)) out.done.push(row);
      else out.idle.push(row);
      placed.add(d.id);
    });
    // a finished row of the last day names its work: it goes first in Done recently and takes the place of its team's plain row
    const marks = isObj(seen) ? seen : {};
    const finished = (Array.isArray(heads) ? heads : []).filter(h => isObj(h) && h.kind === "finished" && idOf(h.task_id) && marks[h.task_id] !== true);
    const fin = finished.map(h => ({id: idOf(h.dept_id), name: clean(h.dept_name) || idOf(h.dept_id) || "A team", status: "filed", words: "finished",
      work: clean(h.title) || clean(h.text), since: Number.isFinite(h.since_s) ? h.since_s : null}));
    const named = new Set(fin.map(f => f.id).filter(Boolean));
    const busy = new Set(out.running.map(r => r.id));      // a team at work again shows once, in In progress, not also under an older finished run
    out.done = fin.concat(out.done.filter(d => !named.has(d.id))).filter(d => !busy.has(d.id));
    out.idle = out.idle.filter(d => !named.has(d.id));
    return out;
  }

  /* ---------------------------------------------------------------- one card per thing that waits */
  // The question as the owner should read it: what the team said (one line), then the question(s); a question with options is answered by a button.
  function askOf(item) {
    const cv = CV();
    const raw = text(item.text);
    const strip = s => (cv ? cv.stripTag(s) : s).trim();
    const ask = cv ? cv.parseAsk(raw) : {say: raw, qs: []};
    const qs = ask.qs.map(q => ({q: strip(q.q), opts: q.opts.map(clean).filter(Boolean)})).filter(q => q.q || q.opts.length);
    const say = strip(ask.say).split("\n").map(clean).filter(Boolean);
    // "Please send these: a; b; c" is three questions (the studio lists them the same way)
    const list = qs.length === 0 && say.length ? /^(.{0,80}?:)\s*(.+;.+)$/.exec(say[say.length - 1]) : null;
    if (list) {
      say[say.length - 1] = list[1];
      list[2].split(/;\s*/).map(clean).filter(Boolean).forEach(q => qs.push({q, opts: []}));
      return {say, qs, options: Array.isArray(item.options) ? item.options.map(clean).filter(Boolean) : []};
    }
    const options = Array.isArray(item.options) && item.options.length ? item.options.map(clean).filter(Boolean)
      : (qs.length === 1 ? qs[0].opts : []);
    return {say: say.slice(0, 6), qs, options};
  }

  // "Keep going: you get more of the missing parts built" reads as a choice and what it means: the choice in bold, the meaning under it.
  function optionLabel(t) {
    const m = /^([^:]{2,40}):\s*(.+)$/.exec(t);
    return m ? "<b>" + esc(m[1]) + '</b><span class="fdoptwhy">' + esc(m[2]) + "</span>" : esc(t);
  }

  function waited(item, elapsedMs) {
    const hv = HV();
    return hv ? hv.waitedHtml(item, elapsedMs) : "";
  }

  function needCard(item, opts) {
    if (!isObj(item) || !Number.isInteger(item.message_id)) return "";
    const o = isObj(opts) ? opts : {};
    const msg = String(item.message_id);
    const busy = o.busy === true;
    const dis = busy ? " disabled" : "";
    const err = clean(o.error) ? '<p class="fderr" role="alert">' + esc(clean(o.error)) + "</p>" : "";
    if (item.kind === "approval") {
      const yes = (Array.isArray(item.options) && clean(item.options[0])) || "Yes";
      const no = (Array.isArray(item.options) && clean(item.options[1])) || "No";
      return '<article class="fdcard fdappr" data-msg="' + esc(msg) + '" data-kind="approval">' +
        '<header class="fdhead"><span class="fdwho">Approval</span>' + waited(item, o.elapsedMs) + "</header>" +
        '<p class="fdq">' + esc(clean(item.text) || "A change to your org waits for your yes.") + "</p>" + err +
        '<div class="fdacts"><button type="button" class="fdbtn fdyes" data-act="fd-approve" data-msg="' + esc(msg) + '" data-text="' + esc(yes) + '"' + dis + ">Approve</button>" +
        '<button type="button" class="fdbtn fdghost" data-act="fd-decline" data-msg="' + esc(msg) + '" data-text="' + esc(no) + '"' + dis + ">Not now</button></div></article>";
    }
    const dept = idOf(item.dept_id);
    const who = clean(item.dept_name) || dept || "A team";
    const ask = askOf(item);
    // no numbered question: the team's last line is the ask itself, so it reads as the question and what came before it as the lead-in
    const lead = ask.qs.length ? ask.say : ask.say.slice(0, -1);
    const lines = lead.map(s => '<p class="fdsay">' + esc(s) + "</p>").join("") +
      (ask.qs.length === 0 && ask.say.length ? '<p class="fdq">' + esc(ask.say[ask.say.length - 1]) + "</p>" : "") +
      (ask.qs.length > 1 ? '<ol class="fdqs">' + ask.qs.map(q => "<li>" + esc(clean(q.q)) + "</li>").join("") + "</ol>"
        : ask.qs.length === 1 && ask.qs[0].q ? '<p class="fdq">' + esc(clean(ask.qs[0].q)) + "</p>" : "");
    const body = lines || '<p class="fdq">' + esc(clean(item.text)) + "</p>";
    const answer = ask.options.length
      ? '<div class="fdopts">' + ask.options.map((t, i) => '<button type="button" class="fdbtn fdopt" data-act="fd-option" data-msg="' + esc(msg) + '" data-opt="' + (i + 1) +
        '" data-text="' + esc(t) + '"' + dis + ">" + optionLabel(t) + "</button>").join("") + "</div>"
      : '<div class="fdreply"><textarea class="fdbox" rows="1" data-msg="' + esc(msg) + '" aria-label="Your answer to ' + esc(who) + '" placeholder="Your answer"' + dis + "></textarea>" +
        '<button type="button" class="fdbtn fdyes" data-act="fd-answer" data-msg="' + esc(msg) + '"' + dis + ">Send</button></div>";
    const open = dept ? '<a class="fdopen" href="' + esc(teamHref(dept)) + '">Open ' + esc(who) + "</a>" : "";
    return '<article class="fdcard fdask" data-msg="' + esc(msg) + '" data-kind="question"' + (dept ? ' data-dept="' + esc(dept) + '"' : "") + ">" +
      '<header class="fdhead"><span class="fdwho">' + esc(who) + "</span>" + waited(item, o.elapsedMs) + "</header>" + body + err + answer +
      (open ? '<footer class="fdfoot">' + open + "</footer>" : "") + "</article>";
  }

  function problemCard(row) {
    if (!isObj(row) || row.kind !== "problem" || !idOf(row.task_id)) return "";
    const task = idOf(row.task_id);
    const dept = idOf(row.dept_id);
    const who = clean(row.dept_name) || dept || "A team";
    const hv = HV();
    const since = Number.isFinite(row.since_s) && hv ? '<small class="nwait">' + esc(row.since_s < 60 ? "just now" : hv.ageWords(row.since_s) + " ago") + "</small>" : "";
    const why = clean(row.outcome) ? '<p class="fdsay">' + esc(clean(row.outcome)) + "</p>" : "";
    const acts = [];
    if (row.retry === true) acts.push('<button type="button" class="fdbtn fdyes" data-act="fd-retry" data-task="' + esc(task) + '">Try again</button>');
    if (dept) acts.push('<a class="fdopen" href="' + esc(teamHref(dept)) + '">Open ' + esc(who) + "</a>");
    acts.push('<button type="button" class="fdbtn fdghost" data-act="fd-seen" data-task="' + esc(task) + '">Got it</button>');
    return '<article class="fdcard fdprob" data-task="' + esc(task) + '" data-kind="problem"><header class="fdhead"><span class="fdwho">' + esc(who) + "</span>" + since + "</header>" +
      '<p class="fdq">' + esc(clean(row.text) || "This work stopped.") + "</p>" + why + '<div class="fdacts">' + acts.join("") + "</div></article>";
  }

  const problemsOf = (heads, seen) => { const hv = HV(); return hv ? hv.split(heads, seen).problems : []; };

  function count(state) {
    const s = isObj(state) ? state : {};
    return (Array.isArray(s.needs) ? s.needs.filter(isObj).length : 0) + problemsOf(s.heads, s.seen).length;
  }

  function summary(state) {
    const n = count(state);
    return n === 0 ? "Nothing needs you right now" : n === 1 ? "1 thing needs you" : n + " things need you";
  }

  function needsHtml(state) {
    const s = isObj(state) ? state : {};
    const needs = Array.isArray(s.needs) ? s.needs.filter(isObj) : [];
    const answering = isObj(s.answering) ? s.answering : {};
    const errors = isObj(s.errors) ? s.errors : {};
    const cards = needs.map(i => needCard(i, {elapsedMs: s.elapsedMs, busy: answering[i.message_id] === true, error: errors[i.message_id]}))
      .concat(problemsOf(s.heads, s.seen).map(problemCard)).filter(Boolean);
    const n = cards.length;
    if (!s.loaded) return '<h2 class="fdh">Needs you</h2><p class="fdcalm">Looking&hellip;</p>';
    if (n === 0) {
      const running = buckets(s.departments, s.heads, s.seen).running;
      const now = running.length === 0 ? "Nothing is running." : running.length === 1 ? running[0].name + " is working." :
        running.length + " teams are working: " + running.slice(0, 3).map(r => r.name).join(", ") + (running.length > 3 ? " and more" : "") + ".";
      return '<h2 class="fdh">Needs you</h2><div class="fdempty"><span class="fdok" aria-hidden="true"></span><div><b>Nothing needs you right now</b><p>' + esc(now) + "</p></div></div>";
    }
    return '<h2 class="fdh">Needs you <span class="fdcount">' + n + "</span></h2>" + '<div class="fdcards">' + cards.join("") + "</div>";
  }

  /* ---------------------------------------------------------------- in progress and done */
  function teamRow(r, level, kind) {
    const href = r.id ? teamHref(r.id) : "";
    const hv = HV();
    const when = kind === "done" && r.since !== null && r.since !== undefined && hv ? (r.since < 60 ? "just now" : hv.ageWords(r.since) + " ago") : "";
    const sub = r.work ? r.work : r.purpose;
    const name = '<span class="fdname">' + esc(r.name) + "</span>" + (sub ? '<span class="fdsub">' + esc(sub) + "</span>" : "");
    const main = href ? '<a class="fdrowlink" href="' + esc(href) + '">' + name + "</a>" : '<span class="fdrowlink">' + name + "</span>";
    const chat = at(level, "manager") && r.id ? '<button type="button" class="fdchip" data-act="fd-chat" data-node="' + esc(r.id) + '">Chat</button>' : "";
    return '<li class="fdrow st-' + esc(r.status || "idle") + '"><i class="fddot" aria-hidden="true"></i>' + main +
      '<small class="fdst">' + esc(when || r.words) + "</small>" + chat + "</li>";
  }

  function listsHtml(state) {
    const s = isObj(state) ? state : {};
    const level = LEVELS.includes(s.level) ? s.level : "simple";
    const b = buckets(s.departments, s.heads, s.seen);
    const done = s.moreDone === true ? b.done : b.done.slice(0, DONE_SHOWN);
    const more = b.done.length - done.length;
    const run = '<section class="fdlist" aria-labelledby="fd-run-h"><h2 class="fdh" id="fd-run-h">In progress</h2>' +
      (b.running.length ? '<ul class="fdrows">' + b.running.map(r => teamRow(r, level, "run")).join("") + "</ul>" : '<p class="fdcalm">No team is working right now.</p>') + "</section>";
    const fin = '<section class="fdlist" aria-labelledby="fd-done-h"><h2 class="fdh" id="fd-done-h">Done recently</h2>' +
      (done.length ? '<ul class="fdrows">' + done.map(r => teamRow(r, level, "done")).join("") + "</ul>" : '<p class="fdcalm">Finished work shows here.</p>') +
      (more > 0 ? '<button type="button" class="fdmore" data-act="fd-more">' + more + " more</button>" : "") + "</section>";
    const idle = b.idle.length ? '<details class="fdidle" data-key="fd-idle"><summary>Other teams (' + b.idle.length + ")</summary><ul class=\"fdrows\">" +
      b.idle.map(r => teamRow(r, level, "idle")).join("") + "</ul></details>" : "";
    return '<div class="fdlists">' + run + fin + "</div>" + idle;
  }

  /* ---------------------------------------------------------------- what the level adds */
  function navHtml(level) {
    const l = LEVELS.includes(level) ? level : "simple";
    if (!at(l, "manager")) return "";
    const go = (pane, label) => '<button type="button" class="fdnavb" data-act="fd-go" data-pane="' + pane + '">' + label + "</button>";
    const items = [go("chart", "Org chart"), go("graph", "Workflow graph"), go("chat", "Team chats")];
    if (at(l, "debug")) {
      items.push(go("settings", "Settings"), '<a class="fdnavb" href="/console">Usage and log</a>',
        // the Raw AI chat viewer is built elsewhere (node_panel / agent views); this is where it is reached from. A page that has it listens for sutra:raw-ai-chat.
        '<button type="button" class="fdnavb" data-act="fd-hook" data-hook="raw-ai-chat" id="fd-rawchat">Raw AI chat</button>');
    }
    return items.join("");
  }

  function debugHtml(state) {
    const s = isObj(state) ? state : {};
    if (s.level !== "debug") return "";
    const hv = HV();
    const lane = hv ? hv.laneHtml(s.heads, {seen: s.seen, more: true}) : "";
    return '<section class="fddebug" aria-labelledby="fd-dbg-h"><h2 class="fdh" id="fd-dbg-h">Heads up, in full</h2>' +
      (lane || '<p class="fdcalm">No crashed work, no quiet team, nothing finished in the last day.</p>') + "</section>";
  }

  /* ---------------------------------------------------------------- the org chat's last word, after a send from here */
  function latestHtml(state) {
    const s = isObj(state) ? state : {};
    const status = clean(s.status);
    const list = Array.isArray(s.messages) ? s.messages.filter(isObj) : [];
    // Sutra's answer to the owner's last line: its words, a team that took the work, and a choice it still waits on
    let from = list.length;
    while (from > 0 && list[from - 1].role !== "user") from -= 1;
    const reply = list.slice(from);
    if (s.show !== true || (reply.length === 0 && !status)) return "";
    const parts = [];
    reply.forEach(m => {
      const card = isObj(m.card) ? m.card : null;
      const answered = isObj(s.answers) && Object.prototype.hasOwnProperty.call(s.answers, m.id);
      if (!card) {
        const said = clean(CV() ? CV().stripTag(m.text) : m.text);
        if (said) parts.push('<p class="fdsay">' + esc(said.length > 280 ? said.slice(0, 277) + "…" : said) + "</p>");
      } else if (card.type === "task" && idOf(card.dept_id)) {
        const who = clean(card.dept_name) || card.dept_id;
        parts.push('<p class="fdsay"><a class="fdopen" href="' + esc(teamHref(card.dept_id)) + '">' + esc(who) + "</a> is on it: " + esc(clean(card.title)) + "</p>");
      } else if (card.type === "choice" && Array.isArray(card.options) && !answered) {
        parts.push('<p class="fdq">' + esc(clean(card.question)) + '</p><div class="fdopts">' + card.options.filter(isObj).map(op => '<button type="button" class="fdbtn fdopt" data-act="fd-choose" data-msg="' +
          esc(String(m.id)) + '" data-option="' + esc(clean(op.id) || clean(op.label)) + '" data-text="' + esc(clean(op.label)) + '">' + esc(clean(op.label)) + "</button>").join("") + "</div>");
      }
    });
    const body = parts.join("");
    return '<div class="fdlatest" role="status"><span class="fdwho">Sutra</span>' + (status ? '<p class="fdphase">' + esc(status) + "</p>" : "") + body +
      '<button type="button" class="fdlink" data-act="fd-conversation">Open the conversation</button></div>';
  }

  const FrontDoor = {LEVELS, ORG, buckets, askOf, needCard, problemCard, needsHtml, listsHtml, navHtml, debugHtml, latestHtml, summary, count, levelAt: at};
  if (typeof module === "object" && module !== null && module.exports) module.exports = FrontDoor;
  else root.FrontDoor = FrontDoor;
})(globalThis);
