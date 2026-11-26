/* chat_view.js - the pure core of a node's chat (work package UI-6; docs/design/ui.md sections 6.5, 6.6, 7 and 10; S2-models-09, S4-fnodes-06,
   S4-fnodes-12).

   Strings in, strings out: transcript() draws a session's messages in J2's bubble look (.sb.team, .sb.me, .opts), card() draws one chat card
   (task, chart_change, approval, choice, node_approval, needs_you, team_chat, done, deliverable, answer_sources and, in a function node's working log, atom), composerState() says whether the
   message box shows, is disabled and what it says, whoLabel() names an author, and safeText() is the one door a message text goes through.
   Nothing touches the DOM, every word that came from the wire is escaped, and the markup is well formed XML.

   safeText escapes first and then allows three things the text asked for in plain marks: **bold**, `code` and line breaks. It makes no link,
   no image and no other tag, so a message cannot put markup on the page (docs/design/ui.md section 4.3). One kind of line reads more: a model's
   reply to a direct line (an agent text message with `turn` set) goes through ChatMarkdown.render (chat_markdown.js, GAP-markdown) when that
   script is on the page: escaped first too, then paragraphs, lists, code blocks, tables, headings and quotes, and still no link and no HTML.
   Every other line (the owner's, a team's, Sutra's, a note, an error, a card) keeps safeText.

   An `answer_sources` card (DV-1, Ask mode) follows a cited answer: every source the answer named with the label code gave it ("checked" or "could not find"; the page never makes one),
   a sentence that says what "checked" covers, and "Turn this into work", a button whose data-draft holds a request the page puts in the box for the owner to finish and send. An answer
   that named no source says so ("No sources given"); one whose sources are all wrong says none could be found. workDraft(card) is that request, a pure function.

   Buttons carry data-act (open-team, open-team-chat, show-node, show-change, choose, option, answer-option, answer, retry, retry-task, retry-direct, ask-to-work) and the data they need; the page that
   shows the transcript (the node panel, Home) listens for them. A link that opens a team page is a real <a href>, so it also works without a script.
   The finished report of a run (D135) is a `deliverable` card in the team's chat: the report as markdown (ChatMarkdown, folded by ChatFold.longText when long),
   the files git saw change in the owner's folder (nothing at all when git could not say) and "Open the full report", a real link to the team page's Preview tab
   for that run; the done card in the org chat gets "Open the report", the same link.

   The owner's questions to a function and its answers (J2 sync 4, D148) are lines of that function's chat, drawn by the messages route with `ask`: "q" is the
   owner's own line, labelled "You asked"; "records" and "model" are the function's answer, with a small label that says where it came from ("From its records,
   no AI call", "AI answer from its records"). Every such line carries data-ask. A note to an agent (`steer`) is drawn as it was.

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
  const ASK_WORDS = freeze({q: "You asked", records: "From its records, no AI call", model: "AI answer from its records"});          // D148: a question and where its answer came from
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

  // What the model received of each file, under the owner's line (D440): the `attachments` of the stored line (the server's receipt: name, kind, sent, chars, cut, total).
  // "Read: notes.txt (all 12,000 characters)", "Read: big.csv (first 40,000 of 90,000 characters)", "Sent as an image: shot.png", "Sent as a PDF: plan.pdf". Every word is escaped.
  function fileReceiptLine(f) {
    const name = esc(clean(f.name));
    if (f.sent === "image") return "Sent as an image: " + name;
    if (f.sent === "pdf") return "Sent as a PDF: " + name;
    if (f.sent === "reference") return "Kept as a reference file: " + name;          // D451: an image or a PDF that came with a request to the team: copied into the run, never read as text
    const sent = Number.isFinite(f.chars) ? f.chars : 0;
    const total = Number.isFinite(f.total) && f.total >= sent ? f.total : sent;
    if (f.sent === "given") return "Given to the team: " + name + (f.cut === true ? " (opening " + grouped(Math.max(0, Math.floor(sent))) + " of " + grouped(Math.max(0, Math.floor(total))) + " characters; the whole file is in the run folder)" : " (all " + grouped(Math.max(0, Math.floor(sent))) + " characters)");
    return "Read: " + name + (f.cut === true ? " (first " + grouped(Math.max(0, Math.floor(sent))) + " of " + grouped(Math.max(0, Math.floor(total))) + " characters)" : " (all " + grouped(Math.max(0, Math.floor(sent))) + " characters)");
  }
  const fileReceiptHtml = files => {
    const list = (Array.isArray(files) ? files : []).filter(f => isObj(f) && ["text", "image", "pdf", "given", "reference"].includes(f.sent)).slice(0, 10);
    const team = list.length > 0 && list.every(f => f.sent === "given" || f.sent === "reference");          // D451: the files of a request to a team
    return list.length === 0 ? "" : '<ul class="creceipt" aria-label="' + (team ? "What the team was given" : "What the model received") + '">' + list.map(f => "<li>" + fileReceiptLine(f) + "</li>").join("") + "</ul>";
  };

  // The agents address each other with a leading "@Name" (J2's chat). The owner reads the sentence, not the address, so the tag is dropped from
  // what the owner reads; a working log keeps it.
  const stripTag = value => text(value).replace(/^\s*@[\w-]+[,:]?[ \t]*/, "");

  /* ---------------------------------------------------------------- a question with options (J2's parseAsk, j2_ui.html:1070) */
  const OPTION = /^\s+Option \d+: (.*?)(?: \[adds (?:\d+ (?:units|work credits)|\$[\d,.]+)[^\]]*\])?$/;      // D423: or "[adds $10]"
  const OPTION_START = /^\s+Option \d+: /;
  const OPTION_TAIL = / \[adds (?:\d+ (?:units|work credits)|\$[\d,.]+)[^\]]*\]$/;
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
      (deptId !== "" ? ' <button type="button" class="lbtn" data-act="show-node" data-node="' + esc(deptId) + '">See it on the graph</button>' : "") + "</div>" + projectLink(c.project_id) + "</div>";
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
    const first = type === "approval" && Array.isArray(c.adds) ? c.adds[0] : null;
    const add = first && typeof first === "object" && clean(first.ref) && clean(first.name) && clean(c.change_id) ? {ref: clean(first.ref), name: clean(first.name)} : null;
    const answer = clean(ctx.answer);
    const done = answer !== "" || ctx.answered === true;
    return '<div class="ncard c-' + type + '" data-card="' + type + '"' + changeRef(c) + (done ? ' data-answered="true"' : "") + ">" +
      '<p class="sq">' + safeText(clean(c.question)) + "</p>" + (type === "approval" ? impactList(c, done) : "") +
      (done ? '<p class="canswer">' + (answer ? "You answered: <b>" + esc(answer) + "</b>" : "Answered") + "</p>"
        : '<div class="opts">' + (add ? '<button type="button" data-act="name-add" data-change="' + esc(clean(c.change_id)) + '" data-ref="' + esc(add.ref) +
            '" data-name="' + esc(add.name) + '">Name it&hellip;</button>' : "") +                 // a project is named before it is made (D427)
          options.filter(o => !add || o.id !== "yes").map(o => '<button type="button" data-act="choose" data-id="' + esc(o.id) + '" data-option="' + esc(o.label) + '">' + esc(o.label) + "</button>").join("") + "</div>") +
      "</div>";
  }

  // A question of a multi-agent project (D317, a `node_approval` card): what is asked in plain words and its answers as buttons. A button posts to the project's answer route
  // (`allow_once`, `allow_project`, `deny`) or, for a permission of the computer, to its check or skip route (`check_again`, `skip`). An answered or ended card reads "Answered".
  const NODE_ANSWER_WORDS = freeze({allow_once: "Allow once", allow_project: "Allow for this project", deny: "No", check_again: "Check again", skip: "Skip"});
  // MAN-13: the way to the project's own page, where everything about it is. Only for an id of the project shape, so a hostile word is never a link.
  function projectLink(id) {
    const project = clean(id);
    return /^prj_[0-9a-f]{12}$/.test(project) ? '<p class="plinkrow"><a class="plink" href="/p/' + esc(project) + '">Open the project</a></p>' : "";
  }
  // R6: a note about a project ends with its page address (`/p/prj_...`); the address becomes the way back into the project. Only that exact shape; a note without it comes out unchanged.
  function projectAddress(html) {
    return html.replace(/\/p\/(prj_[0-9a-f]{12})(?![0-9a-zA-Z_])/g, '<a class="plink" href="/p/$1">Open the project</a>');
  }
  // The reviewer's question is "send the steps back?" (D393): its two answers say that, not "Allow once" and "No".
  const REVIEW_ANSWER_WORDS = freeze({allow_once: "Send them back", deny: "Leave as it is"});
  function nodeApprovalCard(c, ctx) {
    const words = clean(c.kind) === "review" ? Object.assign({}, NODE_ANSWER_WORDS, REVIEW_ANSWER_WORDS) : NODE_ANSWER_WORDS;
    const done = ctx.answered === true || clean(ctx.answer) !== "";
    const options = (Array.isArray(c.options) ? c.options : []).map(clean).filter(o => hasOwn(NODE_ANSWER_WORDS, o));
    const buttons = options.map(o => '<button type="button" data-act="node-answer" data-project="' + esc(clean(c.project_id)) + '" data-approval="' + esc(clean(c.approval_id)) + '" data-item="' +
      esc(clean(c.item)) + '" data-decision="' + o + '">' + esc(words[o]) + "</button>").join("");
    return '<div class="ncard c-nodeapproval" data-card="node_approval" data-kind="' + esc(clean(c.kind)) + '" data-project="' + esc(clean(c.project_id)) + '" data-approval="' + esc(clean(c.approval_id)) + '"' +
      (done ? ' data-answered="true"' : "") + '><p class="sq">' + safeText(clean(c.question)) + "</p>" +
      (done ? '<p class="canswer">Answered</p>' : '<div class="opts">' + buttons + "</div>") + projectLink(c.project_id) + "</div>";
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

  // The org chat's pointer to a team's own chat (GAP3 dept-chats): "Started Web: [open its chat]" when a turn made the team, "Web has a question for
  // you: [open its chat]" when its Identity asked. The chip is a real <button> (focusable, Enter and Space work) that carries the team's node and chat
  // session in data-node and data-session; the page that shows the transcript opens that chat (Home switches its chat pane). The words of the
  // team are never in the card. ctx.answered closes a question pointer ("Web's question was answered"); the chip stays, so the chat can still be read.
  const chatChip = (c, label) => {
    const session = clean(c.session_id);
    const node = clean(c.node_id);
    return node === "" ? "" : '<button type="button" class="lbtn chatchip" data-act="open-team-chat" data-node="' + esc(node) + '"' + (session ? ' data-session="' + esc(session) + '"' : "") +
      ' aria-label="' + esc(label + " " + (clean(c.name) || node)) + '">' + esc(label) + "</button>";
  };

  function teamChatCard(c, ctx) {
    const name = clean(c.name) || clean(c.node_id) || "The team";
    const asking = clean(c.about) === "question";
    const done = asking && isObj(ctx) && ctx.answered === true;
    const lead = asking ? (done ? "<b>" + esc(name) + "</b>'s question was answered. " : "<b>" + esc(name) + "</b> has a question for you. ") : "Started <b>" + esc(name) + "</b>: ";
    const label = asking && !done ? "Answer in its chat" : "Open its chat";
    return '<div class="ncard c-teamchat" data-card="team_chat" data-about="' + (asking ? "question" : "started") + '" data-node="' + esc(clean(c.node_id)) + '"' +
      (clean(c.session_id) ? ' data-session="' + esc(clean(c.session_id)) + '"' : "") + (asking && Number.isInteger(c.question_message_id) ? ' data-question="' + c.question_message_id + '"' : "") +
      (done ? ' data-answered="true"' : "") + '><p class="cteam"><span class="cteamlead">' + lead.trim() + "</span>" + chatChip(c, label) + "</p></div>";
  }

  // The whole report of a run, on the team's page: its Preview tab for that run (J2's page draws a document there as a page: markdown made into html). Both ids
  // are checked here again, so an id the page does not know makes no link rather than a wrong one.
  const DEPT_ID = /^[A-Za-z0-9_.:-]{1,120}$/;
  const RUN_ID = /^j2-[A-Za-z0-9_-]{1,120}$/;
  function reportHref(dept, run) {
    const d = clean(dept);
    const r = clean(run);
    return DEPT_ID.test(d) && d !== "." && d !== ".." && RUN_ID.test(r) ? "/d/" + encodeURIComponent(d) + "/?view=detail&tab=preview&run=" + encodeURIComponent(r) : "";
  }
  const reportLink = (report, label) => {
    const href = isObj(report) ? reportHref(report.dept_id, report.run_id) : "";
    return href === "" ? "" : '<a class="lbtn" data-act="open-team" href="' + esc(href) + '">' + esc(label) + "</a>";
  };

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
      '<div class="acts">' + (projectLink(c.project_id) === "" ? retryButton(c, ctx) : "") + reportLink(c.report, "Open the report") +
      openTeam(deptId, ' data-task="' + esc(clean(c.task_id)) + '" data-dept-name="' + esc(dept) + '"') + "</div>" + projectLink(c.project_id) + "</div>";      // a step of a project is tried again by its project, never by this card (D394)
  }

  // The finished deliverable of a run in the team's chat (D135, a `deliverable` card): the report as the team wrote it, the files git saw change in the owner's
  // folder, the way to the whole report. The words that name a file's state are ours; a path is shown as the host recorded it. `changes` absent means git could
  // not say (no repository, read only, too slow): then the card says nothing about changes, not even that there were none.
  const CHANGE_WORDS = freeze({new: "new", modified: "changed", deleted: "deleted", reverted: "back to the committed version"});

  function changedFiles(changes) {
    if (!isObj(changes)) return "";
    const files = (Array.isArray(changes.files) ? changes.files : []).filter(isObj).filter(f => clean(f.path) !== "");
    const more = count(changes.more) || 0;
    if (files.length === 0 && more === 0) return '<p class="cdnone">No file in your folder changed during this run (checked with git).</p>';
    const line = f => {
      const state = clean(f.status);
      const known = hasOwn(CHANGE_WORDS, state);
      return '<li><code>' + esc(clean(f.path)) + '</code><span class="cdst st-' + (known ? state : "other") + '">' + esc(known ? CHANGE_WORDS[state] : state) + "</span></li>";
    };
    return '<div class="cdchanges"><p class="cdhead">Changed in your folder during this run (' + (files.length + more) + ")</p>" +
      '<ul class="cdfiles">' + files.map(line).join("") + (more > 0 ? '<li class="cdmore">and ' + more + " more</li>" : "") + "</ul></div>";
  }

  function deliverableCard(c) {
    const body = text(c.text);
    const href = reportHref(c.dept_id, c.run_id);
    let report = '<p class="cdnone">The report was not written: the run ended before it.</p>';
    if (body.trim() !== "") {
      const html = root.ChatMarkdown ? root.ChatMarkdown.render(body) : safeText(body);
      report = root.ChatFold && root.ChatFold.longText ? root.ChatFold.longText(body, html, {label: "Read the report"}) : html;
    }
    return '<div class="ncard c-deliverable" data-card="deliverable" data-task="' + esc(clean(c.task_id)) + '" data-run="' + esc(clean(c.run_id)) + '">' +
      '<h2 class="cdtitle">' + esc(clean(c.label) || "Report") + "</h2>" + '<div class="cdreport">' + report + "</div>" +
      (c.cut === true ? '<p class="cdcut">The report is longer than shown here. Open the full report to read all of it.</p>' : "") + changedFiles(c.changes) +
      (href !== "" ? '<div class="acts"><a class="lbtn" data-act="open-team" href="' + esc(href) + '">Open the full report</a></div>' : "") + "</div>";
  }

  // The sources of a cited answer (DV-1, an `answer_sources` card), drawn from what code decided: a label is "checked" only when the wire says exactly that, anything else is "could not
  // find". Words that came with the card (a path, a quote, a reason) are escaped; the words that say what a label means are ours.
  const MISSING = "could not find";
  const isChecked = src => clean(src.label) === "checked";
  const linesOf = src => {
    const a = count(src.start);
    const b = count(src.end);
    if (a === null) return "";
    return b === null || b === a ? "line " + a : "lines " + a + " to " + b;
  };
  const sentence = reason => { const r = clean(reason); return r === "" ? "It could not be found." : "It could not be found: " + r.charAt(0).toLowerCase() + r.slice(1) + (/[.!?]$/.test(r) ? "" : "."); };

  function sourceLine(src) {
    const ok = isChecked(src);
    const how = clean(src.how);
    const why = ok ? (how === "quote" ? "The file is there and the quoted words are on those lines." : "The file and those lines are there.") : sentence(src.reason);
    const quote = clean(src.quote) !== "" ? ' <q class="asq">' + esc(clean(src.quote)) + "</q>" : "";
    return '<li class="asrc ' + (ok ? "st-checked" : "st-missing") + '" data-label="' + (ok ? "checked" : MISSING) + '"><code class="aspath">' + esc(clean(src.path)) + "</code>" +
      (linesOf(src) !== "" ? ' <span class="asln">' + esc(linesOf(src)) + "</span>" : "") + quote + ' <span class="aslabel">' + (ok ? "checked" : MISSING) + "</span>" +
      '<small class="ashow">' + esc(why) + "</small></li>";
  }

  // "Turn this into work": the request the owner finishes in the box. It starts a sentence and stops, so it cannot be sent by habit as a finished request: it names the question that
  // was asked and the sources that were checked (up to five), and leaves the rest to the owner. At most 8000 characters, like any message.
  function workDraft(c) {
    const card = isObj(c) ? c : {};
    const question = clean(card.question).slice(0, 200);
    const files = (Array.isArray(card.sources) ? card.sources : []).filter(isObj).filter(isChecked).filter(s => clean(s.path) !== "");
    const seen = [];
    files.forEach(s => { const name = clean(s.path) + (linesOf(s) !== "" ? " (" + linesOf(s) + ")" : ""); if (!seen.includes(name)) seen.push(name); });
    const named = seen.slice(0, 5).join(", ") + (seen.length > 5 ? " and " + (seen.length - 5) + " more" : "");
    const from = question !== "" ? 'Based on my question "' + question + '"' + (named !== "" ? " and what you found in " + named : "") : (named !== "" ? "Based on what you found in " + named : "");
    return Array.from(from !== "" ? from + ", please " : "Please ").slice(0, 8000).join("");
  }

  function answerCard(c) {
    const list = (Array.isArray(c.sources) ? c.sources : []).filter(isObj);
    const ok = list.filter(isChecked).length;
    const bad = list.length - ok;
    const more = count(c.more) || 0;
    let tone = "mixed";
    let head;
    if (list.length === 0) { tone = "none"; head = "No sources given. Nothing in this answer points to a file, so none of it was checked."; }
    else if (ok === 0) { tone = "bad"; head = (list.length === 1 ? "The source could not be found" : "None of the " + list.length + " sources could be found") + ". Do not rely on this answer until you have looked yourself."; }
    else if (bad === 0) { tone = "ok"; head = (list.length === 1 ? "The source was checked." : "All " + list.length + " sources were checked."); }
    else head = ok + " of " + list.length + " sources checked; " + bad + " could not be found.";
    const tried = count(c.tried) || 0;
    const refused = tried > 0 ? '<p class="asnote asrefused">This answer also tried ' + (tried === 1 ? "one action that changes something or reaches the web" : tried + " actions that change something or reach the web") + ". Ask does not allow that.</p>" : "";
    const what = list.length === 0 ? "" : '<p class="asnote">Checked means Sutra looked: the file and the lines are there, and so are the quoted words when there are any. It does not mean the answer is right.</p>';
    return '<div class="ncard c-answer t-' + tone + '" data-card="answer_sources" data-tone="' + tone + '" data-checked="' + ok + '" data-missing="' + bad + '">' +
      '<h2 class="cdtitle">Sources</h2><p class="ashead">' + esc(head) + "</p>" +
      (list.length ? '<ul class="assrcs">' + list.map(sourceLine).join("") + "</ul>" : "") +
      (more > 0 ? '<p class="asmore">and ' + more + " more marks that were not checked.</p>" : "") + refused + what +
      '<div class="acts"><button type="button" class="lbtn" data-act="ask-to-work" data-draft="' + esc(workDraft(c)) + '" title="This only writes a request in the box for you to change and send.">Turn this into work</button></div></div>';
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
      case "node_approval": return nodeApprovalCard(value, c);
      case "needs_you": return needsYouCard(value, c);
      case "team_chat": return teamChatCard(value, c);
      case "done": return doneCard(value, c);
      case "deliverable": return deliverableCard(value);
      case "answer_sources": return answerCard(value);
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

  // The owner's request that the org chat passed on to a team (ChatMessageOut.passed_on: the id of the original in the org chat): the first line of the
  // team's chat says where it came from.
  const passedOnHtml = m => (Number.isInteger(m.passed_on) && m.passed_on > 0 ? '<small class="npassed">Passed on from your chat with Sutra</small>' : "");

  // The owner's question to a function ("q"), or the answer of the function ("records": from its records alone, "model": a model read them), or "".
  const askOf = m => (isObj(m) && hasOwn(ASK_WORDS, m.ask) ? m.ask : "");

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
      } else if ((clean(c.type) === "needs_you" || (clean(c.type) === "team_chat" && clean(c.about) === "question")) && opts.needsLoaded === true &&
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
  // transcriptItems takes the same arguments and gives [{key, html}], one per message (html is ONE element): the page draws them with Fluid.patchList,
  // which touches only the lines that changed. An empty transcript is one item, key "empty".
  function transcript(session, messages, opts) {
    return transcriptItems(session, messages, opts).map(it => it.html).join("");
  }

  function transcriptItems(session, messages, opts) {
    const s = isObj(session) ? session : {};
    const o = isObj(opts) ? opts : {};
    const list = (Array.isArray(messages) ? messages : []).filter(isObj);
    if (list.length === 0) return [{key: "empty", html: '<p class="empty nempty">' + esc(s.writable === false ? "Nothing in this log yet." : "No messages yet.") + "</p>"}];
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
    const html = (m, i) => {
      const kind = clean(m.kind) || "text";
      const who = clean(m.who);
      const cardIn = kind === "card" && isObj(m.card) ? m.card : null;
      const dept = (cardIn && clean(cardIn.dept_name)) || clean(o.deptName);
      const label = whoLabel(who, {deptName: clean(s.kind) === "org" || cardIn ? dept : ""});
      const ask = askOf(m);
      const attrs = ' data-id="' + esc(text(m.id)) + '" data-who="' + esc(who) + '" data-kind="' + esc(kind) + '" data-state="' + esc(clean(m.state) || "ok") + '"' +
        (ask !== "" ? ' data-ask="' + ask + '"' : "");
      const klass = bubbleClass(m) + (clean(m.state) === "pending" ? " pending" : "");
      if (bubbleClass(m) === "nmsg sb me") {
        const picked = /^Option (\d+)$/.exec(text(m.text).trim());
        const chosen = picked && asked && asked.qs[0] && asked.qs[0].opts[Number(picked[1]) - 1];
        const failed = clean(m.state) === "error";
        const att = attachedOf(m.text);
        return '<div class="' + klass + (failed ? " failed" : "") + '"' + attrs + ">" + passedOnHtml(m) + (ask === "q" ? '<small class="nask">' + ASK_WORDS.q + "</small>" : "") +
          safeText(chosen ? clean(chosen) : att.text) + attachedHtml(att.names) + fileReceiptHtml(m.attachments) +
          (failed ? '<div class="nerr">Something went wrong. Try again.' + (clean(s.kind) === "org" ? ' <button type="button" class="linkbtn" data-act="retry">Retry</button>' : "") + "</div>" : "") + "</div>";
      }
      if (kind === "note" || kind === "error" || bubbleClass(m) === "nmsg sys") return '<div class="' + klass + '"' + attrs + ">" + (clean(s.kind) === "org" ? projectAddress(safeText(text(m.text))) : safeText(text(m.text))) + retryOf(m) + "</div>";      // D389, D408: the app's own address, in the org chat only
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
        inner = clean(s.kind) === "org" ? projectAddress(safeText(body)) : safeText(body);      // D382, D389: in the org chat only (the app's own reply there); only that exact shape, any other text is as it was
      }
      // a settled provider turn: its tool calls fold into ONE row (ChatFold, ABS-10); nothing is drawn while the message is pending
      if (root.ChatFold && Array.isArray(m.blocks) && m.blocks.length > 0) inner += root.ChatFold.fold(m.blocks, {settled: clean(m.state) !== "pending"});
      if (ask === "records" || ask === "model") inner += '<span class="nasksrc">' + ASK_WORDS[ask] + "</span>";
      return '<div class="' + klass + '"' + attrs + "><small>" + esc(label) + "</small>" + inner + "</div>";
    };
    // opts.shell (the pages, STR-10): a direct reply is ONE node whose inside chat_live_view.js paints, live and settled alike, so the stored message takes over the live node
    const shell = o.shell === true && root.ChatLiveView && typeof root.ChatLiveView.isReply === "function" ? root.ChatLiveView : null;
    return list.map((m, i) => (shell && shell.isReply(m) ? {key: shell.keyOf(m.turn, m.attempt), html: shell.shellHtml(m.turn, m.attempt, {superseded: m.superseded === true})} :
      {key: text(m.id) !== "" ? "m" + text(m.id) : "i" + i, html: html(m, i)}));
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

  // workdirChip(wd) -> the one line under a team chat's box (D125): "Working in <last two segments>" (the full path is the tooltip) or, with no folder,
  // "No working folder: Choose" where Choose is a button that opens Settings > Working folder. `wd` is the GET /api/connectors/workdir answer; null (not
  // read, or the read failed) draws nothing.
  function workdirChip(wd) {
    if (!isObj(wd)) return "";
    const full = clean(wd.path);
    if (full === "") return 'No working folder: <button type="button" class="linkbtn" data-act="open-workdir">Choose</button>';
    const tail = full.split(/[\\/]+/).filter(Boolean).slice(-2).join("/");
    return '<span title="' + esc(full) + '">Working in ' + esc(tail || full) + "</span>";
  }

  const providerLabel = connector => (hasOwn(PROVIDERS, connector) ? PROVIDERS[connector] : clean(connector));

  const ChatView = {transcript, transcriptItems, card, answersOf, composerState, workdirChip, safeText, whoLabel, parseAsk, stripTag, providerLabel, attachedOf, fileReceiptHtml, askOf, workDraft, BUSY, ONE_AT_A_TIME, ASK_WORDS,
    PROVIDERS, PERSONA};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatView;
  else root.ChatView = ChatView;
})(globalThis);
