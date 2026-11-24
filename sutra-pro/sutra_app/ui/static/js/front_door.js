/* front_door.js - Home, the Attention page: the "What should we make?" box, then what needs the owner (each card answered in place), then what
   just finished.

   Strings in, strings out, like heads_up_view.js: nothing touches the DOM and every word from the wire is escaped. home.js owns the fetches, the
   events and the clicks; this file only says what Attention shows for a given state.

     buckets(departments, heads, seen)   {running, done, idle}: teams at work (working, waiting, a problem), work finished (a done team, or a
                                         Heads up "finished" row of the last day), and the rest (idle, not started). A team is in one bucket only.
     needCard(item, opts)                one card per GET /api/needs-you item: the team, how long it waited, the question, and the answer in place
                                         (option buttons, or a box and Send) with "Open" to the team page; an approval has Approve and Not now.
                                         opts {elapsedMs, busy, error}
     problemCard(row)                    one card per Heads up problem the owner has not marked "Got it": Try again, Open, Got it
     needsHtml(state)                    "Needs you": the cards, or the calm line "Nothing needs you right now."
     finishedHtml(state)                 "Just finished": the work finished lately, each row with Open (nothing when there is none)
     latestHtml(state)                   under the box, after the owner sent something there: one calm line, a choice to press, or the way to the work
     summary(state)                      "2 things need you" / "Nothing needs you right now" (the document title and the screen reader line)
     stopOf(state)                       D420: {show, taskId}: the box's Go is Stop while the box is empty and the card under it shows the work it
                                         just started ("Your project is set up") whose team has a live task; D424: plus `project` when that work
                                         is a step of a multi-agent project

   Buttons carry data-act: fd-option (data-msg, data-opt, data-text), fd-answer (data-msg), fd-raise (data-msg, D423: the typed dollars beside it), fd-approve and fd-decline (data-msg), fd-retry
   (data-task), fd-seen (data-task), fd-choose (data-msg, data-option), fd-more. A team link is a real <a href="/d/<dept>/">.
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
  const teamHref = id => "/d/" + encodeURIComponent(id) + "/";

  const ORG = "cs_org";
  const DONE_SHOWN = 5;
  const RUNNING = ["running", "waiting", "waiting_on_you", "fault"];
  const DONE = ["filed", "done_unchecked", "left_open"];
  const WORDS = {running: "working", waiting: "waiting", waiting_on_you: "waiting on you", fault: "has a problem", filed: "done",
    done_unchecked: "done, not checked", left_open: "done, with open items", idle: "idle", not_made: "not started"};
  const word = status => (Object.prototype.hasOwnProperty.call(WORDS, status) ? WORDS[status] : "idle");

  // What a status reads as: everyday words a first-time owner knows, no "team", "org" or engine terms.
  const PLAIN = {running: "Being made", waiting: "Waiting its turn", waiting_on_you: "Needs your answer", fault: "Something broke", filed: "Done",
    done_unchecked: "Done", left_open: "Done, with open items", idle: "Paused", not_made: "Not started", finished: "Done"};
  const plain = (status, fallback) => (Object.prototype.hasOwnProperty.call(PLAIN, status) ? PLAIN[status] : fallback);

  /* ---------------------------------------------------------------- the faces (the studio's five people, the same drawings as the team page) */
  // A fixed table: nothing from the wire goes into the SVG. Colours are the --av-* and --s-av tokens of sutra-front.css.
  const PEOPLE = {
    asha: {name: "Asha", n: 1, hair: "bun"}, mira: {name: "Mira", n: 2, hair: "long"}, kabir: {name: "Kabir", n: 3, hair: "short"},
    dev: {name: "Dev", n: 4, hair: "curly"}, nora: {name: "Nora", n: 5, hair: "bob"}};
  const KEYS = ["asha", "mira", "kabir", "dev", "nora"];
  function hairOf(style, h) {
    return {bun: '<circle cx="32" cy="9" r="6" fill="' + h + '"/><path d="M18 26c0-10 6-15 14-15s14 5 14 15c-3-5-8-7-14-7s-11 2-14 7z" fill="' + h + '"/>',
      long: '<path d="M17 28c0-11 6-17 15-17s15 6 15 17v14c-3 2-5 2-6 0V27c-3-4-6-5-9-5s-6 1-9 5v15c-1 2-3 2-6 0z" fill="' + h + '"/>',
      short: '<path d="M19 25c-1-9 5-14 13-14s14 4 13 14c-2-4-6-6-13-6s-11 2-13 6z" fill="' + h + '"/>',
      curly: [[22, 17], [28, 13], [35, 13], [41, 17], [20, 23], [44, 23]].map(([x, y]) => '<circle cx="' + x + '" cy="' + y + '" r="5.5" fill="' + h + '"/>').join(""),
      bob: '<path d="M18 30c-1-12 5-19 14-19s15 7 14 19h-5c0-5-1-9-3-11-3 2-8 3-15 3-1 2-1 5-1 8z" fill="' + h + '"/>'}[style] || "";
  }
  // The style is the owner's (Settings & logs > Appearance > Team avatars, avatars.js): "classic" is the drawing below and the default; without
  // avatars.js (node, an old page) it is always the drawing below.
  const AV = () => root.Avatars || null;
  function face(key, size) {
    const av = AV();
    return av && av.style() === "illustrated" ? av.svg(key, size, {cls: "fdface", label: false}) : classicFace(key, size);
  }
  // Asha with what she is doing around her (avatars.js draws it for either style): act "work" a turning arc, "ask" a still amber arc, "done" a full
  // ring; badge "ask" | "msg" | "done" at the lower right. The words beside her always say the same thing, so nothing depends on the ring.
  function asha(size, act, badge, id) {
    const av = AV(), drawn = face("asha", size);
    return av ? av.ring(drawn, {who: "asha", act, badge, id}) : drawn;
  }
  function classicFace(key, size) {
    const p = PEOPLE[key] || PEOPLE.asha;
    const skin = "var(--av-s" + p.n + ")", h = "var(--av-h" + p.n + ")", shirt = "var(--av-t" + p.n + ")";
    const back = p.hair === "long" || p.hair === "bob";
    return '<svg class="fdface" width="' + size + '" height="' + size + '" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="31" fill="var(--s-av)"/>' +
      (back ? hairOf(p.hair, h) : "") + '<path d="M12 64c1-11 9-17 20-17s19 6 20 17z" fill="' + shirt + '"/><rect x="28" y="38" width="8" height="9" rx="3" fill="' + skin + '"/>' +
      '<circle cx="32" cy="27" r="13" fill="' + skin + '"/>' + (back ? '<path d="M20 24c3-4 7-5 12-5s9 1 12 5c-1-7-6-11-12-11s-11 4-12 11z" fill="' + h + '"/>' : hairOf(p.hair, h)) +
      '<circle cx="27.5" cy="28" r="1.6" fill="var(--av-line)"/><circle cx="36.5" cy="28" r="1.6" fill="var(--av-line)"/>' +
      '<path d="M28 33c2 2 6 2 8 0" stroke="var(--av-line)" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>';
  }
  // The row under the box: the five faces and who they are.
  function facesHtml() {
    return '<div class="fdfaces"><span class="fdfacerow">' + KEYS.map(k => face(k, 40)).join("") + '</span><span class="fdteam">' +
      KEYS.slice(0, -1).map(k => PEOPLE[k].name).join(", ") + " and " + PEOPLE[KEYS[KEYS.length - 1]].name + " are ready.</span></div>";
  }

  const HV = () => root.HeadsUpView || (typeof require === "function" ? safeRequire("./heads_up_view.js") : null);
  const CV = () => root.ChatView || (typeof require === "function" ? safeRequire("./chat_view.js") : null);
  const BC = () => root.BudgetChip || (typeof require === "function" ? safeRequire("./budget_chip.js") : null);
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
    t = String(t).replace(/ \[adds [^\]]*\]$/, "");      // D423: the "[adds $Z]" tail is the engine's, not the owner's words
    const m = /^([^:]{2,40}):\s*(.+)$/.exec(t);
    return m ? "<b>" + esc(m[1]) + '</b><span class="fdoptwhy">' + esc(m[2]) + "</span>" : esc(t);
  }

  function waited(item, elapsedMs) {
    const hv = HV();
    return hv ? hv.waitedHtml(item, elapsedMs) : "";
  }

  // The project an approval would start (D427): {ref, name} of the card's first add, or null.
  const addOf = item => {
    const add = isObj(item) && Array.isArray(item.adds) ? item.adds[0] : null;
    return isObj(add) && clean(add.ref) && clean(add.name) && clean(item.change_id) ? {ref: clean(add.ref), name: clean(add.name)} : null;
  };

  function needCard(item, opts) {
    if (!isObj(item) || !Number.isInteger(item.message_id)) return "";
    const o = isObj(opts) ? opts : {};
    const msg = String(item.message_id);
    const busy = o.busy === true;
    const dis = busy ? " disabled" : "";
    const err = clean(o.error) ? '<p class="fderr" role="alert">' + esc(clean(o.error)) + "</p>" : "";
    if (item.kind === "approval") {
      // `adds` (D427): the project the org chat would start; its first entry is the one the Create project box names
      const yes = (Array.isArray(item.options) && clean(item.options[0])) || "Yes";
      const no = (Array.isArray(item.options) && clean(item.options[1])) || "No";
      return '<article class="fdcard fdappr" data-msg="' + esc(msg) + '" data-kind="approval">' +
        '<header class="fdhead">' + asha(36, "ask", "ask") + '<span class="fdhw"><b class="fdasker">' + "Asha needs your OK" +
          '</b></span>' + waited(item, o.elapsedMs) + "</header>" +
        '<p class="fdq">' + esc(clean(item.text) || "A change to your org waits for your yes.") + "</p>" + err +
        '<div class="fdacts">' + (addOf(item)
          ? '<button type="button" class="fdbtn fdyes" data-act="fd-name" data-change="' + esc(clean(item.change_id)) + '" data-ref="' + esc(addOf(item).ref) +
            '" data-name="' + esc(addOf(item).name) + '"' + dis + ">Name it&hellip;</button>"                      // a project is named before it is made (D427)
          : '<button type="button" class="fdbtn fdyes" data-act="fd-approve" data-msg="' + esc(msg) + '" data-text="' + esc(yes) + '"' + dis + ">Approve</button>") +
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
    // D423: a dollar raise question also takes a typed amount, the suggested one filled in (its "[adds $Z]" tail in the question text)
    const add = BC() && !busy ? BC().raiseFromText(item.text) : null;
    const raise = add !== null ? BC().raiseHtml(add, 'data-act="fd-raise" data-msg="' + esc(msg) + '"') : "";
    const open = dept ? '<a class="fdopen" href="' + esc(teamHref(dept)) + '">Open ' + esc(who) + "</a>" : "";
    return '<article class="fdcard fdask" data-msg="' + esc(msg) + '" data-kind="question"' + (dept ? ' data-dept="' + esc(dept) + '"' : "") + ">" +
      '<header class="fdhead">' + asha(36, "ask", "ask") + '<span class="fdhw"><b class="fdasker">' + (ask.qs.length > 1 ? "Asha needs " + ask.qs.length + " answers" : "Asha needs one answer") +
      '</b><span class="fdwho">' + esc(who) + "</span></span>" + waited(item, o.elapsedMs) + "</header>" + body + err + answer + raise +
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
    if (!s.loaded) return '<h2 class="fdh" id="fd-needs-h">Needs you</h2><p class="fdcalm">Looking&hellip;</p>';
    if (n === 0) return '<h2 class="fdh" id="fd-needs-h">Needs you</h2><div class="fdempty"><span class="fdok" aria-hidden="true"></span><div><b>Nothing needs you right now.</b></div></div>';
    return '<h2 class="fdh" id="fd-needs-h">Needs you <span class="fdcount">' + n + "</span></h2>" + '<div class="fdcards">' + cards.join("") + "</div>";
  }

  /* ---------------------------------------------------------------- just finished */
  function finishedRow(r) {
    const hv = HV();
    const when = r.since !== null && r.since !== undefined && hv ? (r.since < 60 ? "just now" : hv.ageWords(r.since) + " ago") : "";
    const sub = r.work ? r.work : r.purpose;
    const words = r.words === "finished" ? "Done" : plain(r.status, r.words);
    return '<li class="fdrow st-' + esc(r.status || "filed") + '"><i class="fddot" aria-hidden="true"></i><span class="fdrowlink"><span class="fdname">' + esc(r.name) + "</span>" +
      (sub ? '<span class="fdsub">' + esc(sub) + "</span>" : "") + '</span><small class="fdst">' + esc(when ? "Done · " + when : words) + "</small>" +
      (r.id ? '<a class="fdbtn fdopenbtn" href="' + esc(teamHref(r.id)) + '" aria-label="Open ' + esc(r.name) + '">Open</a>' : "") + "</li>";
  }

  function finishedHtml(state) {
    const s = isObj(state) ? state : {};
    const done = buckets(s.departments, s.heads, s.seen).done;
    if (done.length === 0) return "";
    const shown = s.moreDone === true ? done : done.slice(0, DONE_SHOWN);
    const more = done.length - shown.length;
    return '<h2 class="fdh" id="fd-done-h">Just finished</h2><ul class="fdrows">' + shown.map(finishedRow).join("") + "</ul>" +
      (more > 0 ? '<button type="button" class="fdmore" data-act="fd-more">' + more + " more</button>" : "");
  }

  /* ---------------------------------------------------------------- the org chat's last word, after a send from here */
  // What Sutra said back to the owner's last line: {reply, task, choice}. task is the first work card with a team (where the work now lives),
  // choice the first choice card not answered yet.
  function replyOf(s) {
    const list = Array.isArray(s.messages) ? s.messages.filter(isObj) : [];
    let from = list.length;
    while (from > 0 && list[from - 1].role !== "user") from -= 1;
    const reply = list.slice(from);
    const answered = m => isObj(s.answers) && Object.prototype.hasOwnProperty.call(s.answers, m.id);
    const task = reply.find(m => isObj(m.card) && m.card.type === "task" && idOf(m.card.dept_id)) || null;
    const choice = reply.find(m => isObj(m.card) && m.card.type === "choice" && Array.isArray(m.card.options) && !answered(m)) || null;
    return {reply, task, choice};
  }

  // Where the front door's own send should take the owner: the team page of the work it started, or "" while there is none yet.
  function landing(state) {
    const r = replyOf(isObj(state) ? state : {});
    return r.task ? teamHref(r.task.card.dept_id) : "";
  }

  // The choice card as a Needs you card: the question and one button per option. At Simple the question is put in everyday words.
  function choiceCard(m, simple) {
    const card = m.card;
    const opts = card.options.filter(isObj);
    const q = simple && /team/i.test(clean(card.question)) ? "Is this for one of your projects, or something new?" : clean(card.question);
    const label = op => { const t = clean(op.label); return simple && /^(a new team|none of these)$/i.test(t) ? "Something new" : t; };
    return '<article class="fdcard fdask fdchoice" data-msg="' + esc(String(m.id)) + '" data-kind="choice"><header class="fdhead">' + asha(36, "ask", "ask") +
      '<span class="fdhw"><b class="fdasker">Asha needs one answer</b><span class="fdwho">Before we start</span></span></header>' +
      '<p class="fdq">' + esc(q) + '</p><div class="fdopts">' + opts.map(op => '<button type="button" class="fdbtn fdopt" data-act="fd-choose" data-msg="' +
      esc(String(m.id)) + '" data-option="' + esc(clean(op.id) || clean(op.label)) + '" data-text="' + esc(clean(op.label)) + '">' + esc(label(op)) + "</button>").join("") +
      "</div></article>";
  }

  // One calm card, one line. While Sutra works, what it is doing now; a question as a Needs you card; once the work has a home, a big
  // "Watch it being built" that goes there (s.going: the page is on its way there by itself).
  function latestSimple(s, r, status) {
    if (r.choice) return choiceCard(r.choice, true);
    if (r.task) {
      const href = teamHref(r.task.card.dept_id);
      const what = clean(r.task.card.title) || clean(r.task.card.dept_name) || "Your project";
      return '<div class="fdlatest fdready" role="status">' + asha(44, "done", "done", "fd-latest") + '<div class="fdlw"><b class="fdlh">Your project is set up</b><p class="fdline">' +
        esc(what.length > 120 ? what.slice(0, 117) + "…" : what) + "</p>" + (s.going === true ? '<p class="fdgo">Taking you there&hellip;</p>' : "") +
        '</div><a class="fdbtn fdyes fdwatch" href="' + esc(href) + '">Watch it being built</a></div>';
    }
    if (clean(s.error)) return '<div class="fdlatest fdoops" role="alert"><div class="fdlw"><b class="fdlh">That did not go through</b><p class="fdline">' + esc(clean(s.error)) + "</p></div></div>";
    if (!status && r.reply.length === 0) return "";
    const said = r.reply.map(m => clean(CV() ? CV().stripTag(m.text) : m.text)).filter(Boolean).pop() || "";
    const line = status || (said.length > 160 ? said.slice(0, 157) + "…" : said) || "Getting your project ready…";
    return '<div class="fdlatest fdwork" role="status">' + asha(44, status ? "work" : "", status ? "" : "msg", "fd-latest") + '<div class="fdlw"><b class="fdlh">' + (status ? "Asha is on it" : "Asha says") +
      '</b><p class="fdline">' + esc(line) + "</p></div></div>";      // the arc around Asha is the one moving cue; the line says what she is doing
  }

  function latestHtml(state) {
    const s = isObj(state) ? state : {};
    const status = clean(s.status);
    const r = replyOf(s);
    if (s.show !== true || (r.reply.length === 0 && !status && !clean(s.error))) return "";
    return latestSimple(s, r, status);
  }

  // D420: Go is Stop while the box is empty, the card under it shows the work this send started (latestSimple's r.task, no choice before it)
  // and that team has a live task. state: latestHtml's, plus {box, departments}.
  const TASK_ID = /^tsk_[0-9a-f]{12}$/;
  function stopOf(state) {
    const s = isObj(state) ? state : {};
    const r = replyOf(s);
    const team = s.show === true && !r.choice && r.task && Array.isArray(s.departments) ? s.departments.find(d => isObj(d) && d.id === r.task.card.dept_id) : null;
    const id = team ? text(team.live_task_id) : "";
    if (text(s.box).trim() !== "" || !TASK_ID.test(id)) return {show: false, taskId: ""};
    const project = idOf(r.task.card.project_id);      // D424: a step of a project: Stop stops the whole project (main's project stop), not this one step
    return project ? {show: true, taskId: id, project} : {show: true, taskId: id};
  }

  // The project to name next (D427): the first approval in `needs` that would start one and whose change is not in `opened`; null when none.
  function addToName(needs, opened) {
    const seen = isObj(opened) ? opened : {};
    for (const item of Array.isArray(needs) ? needs : []) {
      const add = isObj(item) && item.kind === "approval" ? addOf(item) : null;
      if (add && !seen[clean(item.change_id)]) return {change_id: clean(item.change_id), ref: add.ref, name: add.name};
    }
    return null;
  }

  const FrontDoor = {ORG, stopOf, buckets, askOf, needCard, problemCard, needsHtml, finishedHtml, latestHtml, landing, facesHtml, face, classicFace, summary, count, addToName};
  if (typeof module === "object" && module !== null && module.exports) module.exports = FrontDoor;
  else root.FrontDoor = FrontDoor;
})(globalThis);
