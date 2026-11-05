/* fnode_view.js - the pure core of the node panel's Details tab (work package UI-6; docs/design/ui.md sections 6.4, 7 and 10;
   S3-web-05, S4-fnodes-02, -03, -05, -08, -10, -14).

   Strings in, strings out: normalize() reads the wire (a NodeDetail, or just a function node's meta) into one plain view, render() draws a
   function node's drawer from it (head, Goal, Task, Context, Work atoms, Constraints, Hands to, then the department page's Go-to-tab
   button), atomHtml() draws one work atom in J2's atom-card layout (Goal, Constraints, Context, How, Expected output, Verification, Result)
   with its status line, its tries and its plain-words pill, and functionsOf() draws the five "Functions of <Department>" chips of a
   division. Nothing touches the DOM, every word that came from the wire is escaped, and the markup is well formed XML, so the tests can
   read it with a small parser.

   normalize() is the only code that knows the names of the wire: goal, task (a string, or an object with `summary`), context, constraints,
   wait_on, hands_to and stats of a function node; id, schema, state, goal, attempt, ts_open, ts_closed, body and usage of an atom; and in
   a body the names of the library Atom (constraints[].text, context[], work.dispatch_kind, work.agent, verify.checks[], outputs, closed_by,
   reason, refusal, model) or of J2's atom/1 view (verification[], defined_output, how). `atom_count` and every unknown key are ignored.

   A classic script with ONE global, FnodeView (see sutra_ctx.js for why); in node it is module.exports. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;

  /* ---------------------------------------------------------------- small helpers */
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;                 // true only for a number that is not NaN or infinite (it does not convert)
  const text = v => (typeof v === "string" ? v : (finite(v) ? String(v) : ""));
  const round1 = n => Math.round(n * 10) / 10;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  // Words from the wire on one line: control characters and runs of white space become one space.
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const count = v => (finite(v) ? Math.max(0, Math.floor(v)) : 0);
  const amount = v => (finite(v) && v >= 0 ? v : 0);
  const orNull = v => (finite(v) && v >= 0 ? v : null);
  const group = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  // "1 call", "12 calls", "1 atom open": the number grouped by thousands, the noun singular for exactly one.
  const unit = (n, one, many) => group(n) + " " + (n === 1 ? one : many);
  const strings = list => (Array.isArray(list) ? list.map(clean).filter(Boolean) : []);
  const DOT = " \u00b7 ";

  /* ---------------------------------------------------------------- words */
  const FUNCTIONS = freeze(["identity", "adaptation", "priority", "coordination", "audit"]);
  const NAMES = freeze({identity: "Identity", adaptation: "Adaptation", priority: "Priority", coordination: "Coordination", audit: "Audit"});
  // The persona of each function: a UI constant copied from J2 (MAPLABEL.persona, j2_ui.html:1590), the same as GraphRender.PERSONA.
  const PERSONA = freeze({identity: "Client Lead", adaptation: "Strategist", priority: "Prioritiser", coordination: "Scheduler", audit: "Quality Reviewer"});
  // J2's FN_TAB (j2_map.py:27): the tab that holds each function's work.
  const FN_TAB = freeze({identity: "charter", adaptation: "workflows", priority: "conflicts", coordination: "timeline", audit: "audit"});
  // Who may hand to whom (S3-web-04(c), the patched routes, not J2's ROUTES): a UI constant used only to find "Handed from", the inverse of
  // the `hands_to` list the server sends with every function node.
  const HANDOFFS = freeze({
    identity: freeze(["adaptation", "priority", "coordination", "audit"]),
    adaptation: freeze(["priority", "identity", "audit", "coordination"]),
    priority: freeze(["adaptation", "identity", "coordination"]),
    coordination: freeze(["priority", "adaptation", "identity", "audit"]),
    audit: freeze(["identity"]),
  });
  // What a call is given, in J2's words (GIVEN, j2_ui.html:2314): the kind of each input; any other name is shown as it is, with spaces.
  const GIVEN = freeze({charter: "the charter", ledger: "the budget", workflows: "the workflow list", workflow: "its own workflow", chat: "the chat",
    task: "its task", findings: "Audit's findings", lessons: "lessons from earlier work", proposal: "the proposal", playbook: "a saved playbook"});
  // J2's MAPW (function nodes) and MAPS (the rest), j2_ui.html:1598-1599; a function that is waiting names who it waits on.
  const FUNCTION_WORDS = freeze({filed: "filed and checked", done_unchecked: "done \u00b7 checks did not pass", running: "running now",
    left_open: "left open", waiting_on_you: "waiting on you", not_made: "not made", fault: "blocked", idle: "idle"});
  const OTHER_WORDS = freeze({filed: "filed", done_unchecked: "done \u00b7 checks did not pass", running: "running now", left_open: "left open",
    waiting: "waiting", waiting_on_you: "waiting on you", fault: "fault", not_made: "not made", idle: "idle"});
  const KIND_WORDS = freeze({root: "root", department: "team", division: "division", function: "function", step: "step"});
  const TASK_WORDS = freeze({queued: "queued", starting: "starting", running: "running", waiting_user: "waiting for you", done: "done",
    done_with_open_items: "done, with open items", stopped: "stopped", crashed: "crashed"});
  const TERMINAL = freeze(["filed", "done_unchecked", "left_open", "fault"]);        // a step node whose run has ended
  const LEGEND = "open > work > verify, close; exits: refuse, abandon";             // the strip of the INSIDE EVERY NODE figure
  const MAX_ATTEMPTS = 3;                                                            // the library caps close runs at three

  // Who a function waits on: "you", a function's persona, a builder ("W-3 Builder"), or whatever else the server named.
  function whoWord(waitOn) {
    const w = clean(waitOn);
    if (w === "you") return "you";
    if (hasOwn(PERSONA, w)) return PERSONA[w];
    if (/^W-\d+$/.test(w)) return w + " Builder";
    return w || "someone";
  }

  // nodeWord(status, kind, waitOn) -> the words under a node, J2's mapState. An unknown status is idle. A function that is waiting names
  // who it waits on.
  function nodeWord(status, kind, waitOn) {
    const known = hasOwn(OTHER_WORDS, status) ? status : "idle";
    if (kind !== "function") return OTHER_WORDS[known];
    return known === "waiting" ? "waiting on " + whoWord(waitOn) : FUNCTION_WORDS[known];
  }

  const statusKey = status => (hasOwn(OTHER_WORDS, status) ? status : "idle");

  // The key of a function node: the wire `fn`, else its label, else the end of its id ("web.identity").
  function functionKey(n) {
    const id = text(n.id);
    const tail = id.slice(id.lastIndexOf(".") + 1);
    const found = [n.fn, clean(n.label).toLowerCase(), tail].find(k => typeof k === "string" && hasOwn(PERSONA, k));
    return found === undefined ? "" : found;
  }

  function givenWord(name) {
    const key = clean(name);
    return hasOwn(GIVEN, key) ? GIVEN[key] : key.replace(/_/g, " ");
  }

  /* ---------------------------------------------------------------- numbers as words */
  function secondsText(s) {
    const secs = finite(s) ? Math.max(0, s) : 0;
    return (secs < 10 ? String(round1(secs)) : group(secs)) + " s";
  }

  function money(usd) {
    if (usd === 0) return "$0.00";
    return usd < 0.01 ? "under $0.01" : "$" + usd.toFixed(2);
  }

  // usageText(usage) -> "12 calls . $0.42 . 7,000 in / 2,120 out tokens". A part that is null or missing is left out ("" when all are).
  function usageText(usage) {
    const u = isObj(usage) ? usage : {};
    const calls = orNull(u.calls);
    const usd = orNull(u.usd);
    const tokensIn = orNull(u.tokens_in);
    const tokensOut = orNull(u.tokens_out);
    const parts = [];
    if (calls !== null) parts.push(unit(Math.floor(calls), "call", "calls"));
    if (usd !== null) parts.push(money(usd));
    if (tokensIn !== null && tokensOut !== null) parts.push(group(tokensIn) + " in / " + group(tokensOut) + " out tokens");
    else if (tokensIn !== null) parts.push(group(tokensIn) + " tokens in");
    else if (tokensOut !== null) parts.push(group(tokensOut) + " tokens out");
    return parts.join(DOT);
  }

  // statsText(stats) -> "12 calls, 41 s, 1 atom open, 5 closed" and ", 1 failed" when an atom failed (a node has at most one open atom).
  function statsText(stats) {
    const s = isObj(stats) ? stats : {};
    const open = count(s.atoms_open);
    const parts = [unit(count(s.calls), "call", "calls"), secondsText(s.seconds), unit(open, "atom", "atoms") + " open", count(s.atoms_closed) + " closed"];
    if (count(s.atoms_failed) > 0) parts.push(count(s.atoms_failed) + " failed");
    return parts.join(", ");
  }

  /* ---------------------------------------------------------------- the five atom states */
  const STATE_WORDS = freeze({open: "OPEN", closed: "CLOSED", verify_failed: "VERIFY FAILED", abandoned: "ABANDONED", refused: "REFUSED"});
  const PILLS = freeze({open: "in progress", verify_failed: "the check did not pass, so nothing is marked done", closed: "goal reached, and checked",
    abandoned: "stopped on purpose, reason kept"});

  // stateWord(state) -> the status line word of one of the five display words. Any other word is shown as it came, in capitals.
  function stateWord(state) {
    const s = clean(state);
    if (hasOwn(STATE_WORDS, s)) return STATE_WORDS[s];
    return s.replace(/_/g, " ").toUpperCase() || "UNKNOWN";
  }

  // The plain-words pill: the Result row and the tooltip of the status line. `a` is a normalized atom.
  function pillText(a) {
    if (a.state === "refused") return "not started: " + (a.refusal ? a.refusal.message : "refused");
    if (a.state === "open" && a.attempt >= 1) return "in progress, attempt " + a.attempt;
    return hasOwn(PILLS, a.state) ? PILLS[a.state] : "";
  }

  /* ---------------------------------------------------------------- one atom: reading the wire */
  const itemText = x => (typeof x === "string" ? clean(x) : (isObj(x) ? clean(x.text || x.target || x.name || x.check || "") : ""));
  const items = list => (Array.isArray(list) ? list.map(itemText).filter(Boolean) : []);

  // A model named in `usage` (a list of strings or {provider, model}) or `body.model`: "Claude (sonnet)". The provider of a model that
  // is named alone is told from its family.
  function modelLabel(model, provider) {
    const m = clean(model);
    const p = clean(provider);
    if (p !== "") return (p.charAt(0).toUpperCase() + p.slice(1)) + (m ? " (" + m + ")" : "");
    if (m === "") return "";
    if (/^(claude|sonnet|opus|haiku)/i.test(m)) return "Claude (" + m + ")";
    if (/^(gpt|o\d|codex)/i.test(m)) return "Codex (" + m + ")";
    return m;
  }

  function modelsOf(usage, body) {
    const u = isObj(usage) ? usage : {};
    const named = (Array.isArray(u.models) ? u.models : []).map(m => (isObj(m) ? modelLabel(m.model, m.provider) : modelLabel(m, ""))).filter(Boolean);
    if (named.length === 0 && clean(u.model) !== "") named.push(modelLabel(u.model, u.provider));
    if (named.length === 0 && clean(body.model) !== "") named.push(modelLabel(body.model, ""));
    return named;
  }

  const TRY_WORDS = freeze({passed: "passed", failed: "failed", unrun: "not run", deferred: "deferred"});

  // One try of one check: exit_code 0 passed, another number failed; `met` of an atom/1 check is true, false or null. Evidence that starts
  // "deferred:" says the check was not judged in that try yet (a turn-phase check), so it is not called passed.
  function triesOf(results, fallbackAttempt) {
    return (Array.isArray(results) ? results : []).filter(isObj).map((r, i) => {
      const evidence = clean(r.evidence);
      let status = "unrun";
      if (r.exit_code === 0 || r.met === true) status = "passed";
      else if ((finite(r.exit_code) && r.exit_code !== 0) || r.met === false) status = "failed";
      let said = evidence;
      if (status === "passed" && /^deferred:/i.test(evidence)) {
        status = "deferred";
        said = evidence.replace(/^deferred:\s*/i, "");
      }
      return {attempt: finite(r.attempt) ? Math.floor(r.attempt) : (fallbackAttempt || i + 1), status, evidence: said, raw: evidence};
    });
  }

  // verifySentence(check) -> what a check says in words: its own text; else, for the plugin's three templates, the plugin's sentence
  // (bin/sutra-atom `_verify_sentence`); else the name of the template.
  function verifySentence(check) {
    const c = isObj(check) ? check : {};
    const said = clean(c.text);
    if (said !== "") return said;
    const template = clean(c.template);
    const args = (Array.isArray(c.args) ? c.args : []).map(a => clean(a));
    const arg = i => args[i] || "?";
    if (template === "file-exists") return "the file " + arg(0) + " exists and is not empty";
    if (template === "grep-count") return 'the text "' + arg(0) + '" appears in ' + arg(1);
    if (template === "named-test") return "the test " + arg(0) + " passes";
    return template || "a check";
  }

  function checksOf(body, builder, attempt) {
    if (builder) {         // atom/1: [{check, applies_to, method, met, evidence}], one result each
      return (Array.isArray(body.verification) ? body.verification : []).filter(isObj).map(v => ({
        sentence: clean(v.check) || clean(v.method) || "a check", template: clean(v.method), tries: triesOf([{attempt: attempt || 1, met: v.met, evidence: v.evidence}], attempt || 1)}));
    }
    const verify = isObj(body.verify) ? body.verify : {};
    return (Array.isArray(verify.checks) ? verify.checks : []).filter(isObj).map(c => ({
      sentence: verifySentence(c), template: clean(c.template), tries: triesOf(c.results, 0)}));
  }

  // The last "RECOVERED: ..." or "WAIVED: ..." among the evidence of the tries: J2 repaired, templated, dropped or accepted something on record.
  function concernOf(checks) {
    let found = null;
    checks.forEach(c => c.tries.forEach(t => {
      const m = /^(RECOVERED|WAIVED):/.exec(t.raw);
      if (m) found = {kind: m[1], text: t.raw};
    }));
    return found;
  }

  const countsOr = v => (finite(v) && v >= 0 ? v : null);

  // normalizeAtom(raw AtomOut) -> the atom as the card draws it. `state` is the display word of the wire; `status` only stands in for it in
  // old fixtures. Anything missing gives an empty list or null, never an error.
  function normalizeAtom(raw) {
    const a = isObj(raw) ? raw : {};
    const body = isObj(a.body) ? a.body : {};
    const builder = clean(a.schema) === "atom/1";
    const id = clean(a.id);
    const state = clean(a.state) || clean(a.status);
    const attempt = count(a.attempt);
    const work = isObj(body.work) ? body.work : {};
    const how = isObj(body.how) ? body.how : {};
    const checks = checksOf(body, builder, attempt);
    const refusal = isObj(body.refusal) ? {code: clean(body.refusal.code), message: clean(body.refusal.message)} : null;
    const usage = isObj(a.usage) ? {calls: countsOr(a.usage.calls), usd: countsOr(a.usage.usd), tokens_in: countsOr(a.usage.tokens_in), tokens_out: countsOr(a.usage.tokens_out)} : null;
    let kind = clean(work.dispatch_kind);
    if (builder) kind = clean(how.kind).toLowerCase() === "code" ? "bash" : "llm";
    return {
      view: "atom", id, shortId: id.slice(id.lastIndexOf(":") + 1), schema: clean(a.schema), nodeId: clean(a.node_id), state, goal: clean(a.goal), attempt,
      builder, constraints: items(body.constraints), context: items(body.context),
      kind, agent: clean(builder ? how.agent : work.agent), models: modelsOf(a.usage, body),
      outputs: builder ? items(body.defined_output) : items(body.outputs).slice(0, 1),
      checks, refusal, reason: clean(body.reason), usage, concern: concernOf(checks),
    };
  }

  const isAtomView = a => isObj(a) && a.view === "atom";
  const isView = v => isObj(v) && v.view === "fnode";

  /* ---------------------------------------------------------------- one atom: drawing it */
  const ATOM_ROWS = freeze([["goal", "Goal", "What must be true when this is done"], ["constraints", "Constraints", "What must never break"],
    ["context", "Context", "What it needs to know"], ["how", "How", "Who does the work"],
    ["expected_output", "Expected output", "What must exist when it is done"], ["verification", "Verification", "The check that proves the goal is met"],
    ["result", "Result", "What came of it"]]);

  const NONE = '<span class="empty">none</span>';
  const list = rows => (rows.length ? '<ul class="alist">' + rows.map(r => "<li>" + esc(r) + "</li>").join("") + "</ul>" : NONE);

  function howText(a) {
    if (a.kind === "bash") return "code, no AI call";
    if (a.kind === "manual") return "you";
    if (a.kind === "skill") return "a Sutra skill";
    if (a.models.length > 0) return a.models.join(", ");
    if (a.builder) return "AI builds it" + (a.agent ? ": " + a.agent : "");
    return "an AI model";
  }

  function triesHtml(a, check) {
    const rows = check.tries.map(t => '<li class="try try-' + t.status + '" data-attempt="' + t.attempt + '">attempt ' + t.attempt + ": " + TRY_WORDS[t.status] +
      (t.evidence ? ", " + esc(t.evidence) : "") + "</li>");
    const last = check.tries.reduce((n, t) => Math.max(n, t.attempt), a.attempt);
    // the next try is pending while the atom is open and tries are left
    if (a.state === "open" && last < MAX_ATTEMPTS) rows.push('<li class="try try-pending" data-attempt="' + (last + 1) + '">attempt ' + (last + 1) + ": pending</li>");
    return rows.length ? '<ul class="atries">' + rows.join("") + "</ul>" : "";
  }

  function verificationHtml(a) {
    if (a.checks.length === 0) return '<span class="empty">no check declared</span>';
    return a.checks.map(c => '<div class="acheck"' + (c.template ? ' data-template="' + esc(c.template) + '"' : "") + '><p class="asent">' + esc(c.sentence) + "</p>" + triesHtml(a, c) + "</div>").join("");
  }

  function resultHtml(a) {
    const pill = pillText(a);
    const cost = usageText(a.usage);
    const keepsReason = a.reason !== "" && (a.state === "abandoned" || a.state === "verify_failed");
    return '<span class="apill st-' + esc(a.state || "unknown") + '">' + esc(pill) + "</span>" +
      (a.concern ? '<div class="arow aconcern"><b>Concern on record</b> ' + esc(a.concern.text) + "</div>" : "") +
      (keepsReason ? '<div class="arow areason"><b>Reason</b> ' + esc(a.reason) + "</div>" : "") +
      (cost ? '<div class="arow acost">' + esc(cost) + "</div>" : "");
  }

  function atomRow(a, key) {
    if (key === "goal") return esc(a.goal);
    if (key === "constraints") return list(a.constraints);
    if (key === "context") return list(a.context);
    if (key === "how") return esc(howText(a));
    if (key === "expected_output") return list(a.outputs);
    if (key === "verification") return verificationHtml(a);
    return resultHtml(a);
  }

  // atomHtml(atom) -> one <details class="atomcard" data-state>: the summary is the status line (OPEN, CLOSED, VERIFY FAILED, ABANDONED or
  // REFUSED, with "attempt n of 3") and the goal; the rows are J2's labels. A refused atom never ran, so it has a Goal and a Result only.
  // `atom` is an AtomOut as the server sends it, or one that normalizeAtom made; `opts.open` draws the card unfolded.
  function atomHtml(atom, opts) {
    const a = isAtomView(atom) ? atom : normalizeAtom(atom);
    const known = hasOwn(STATE_WORDS, a.state);
    const shown = a.state === "refused" ? ATOM_ROWS.filter(r => r[0] === "goal" || r[0] === "result") : ATOM_ROWS;
    const tries = a.attempt >= 1 ? '<span class="aattempt">attempt ' + a.attempt + " of " + MAX_ATTEMPTS + "</span> " : "";
    return '<details class="atomcard" data-state="' + (known ? a.state : "unknown") + '" data-atom="' + esc(a.id) + '" data-key="atom-' + esc(a.id) + '"' +
      (isObj(opts) && opts.open === true ? ' open=""' : "") + "><summary>" +
      '<span class="astate st-' + (known ? a.state : "unknown") + '" title="' + esc(pillText(a)) + '">' + esc(stateWord(a.state)) + "</span> " + tries +
      '<span class="agoal">' + esc(a.goal) + '</span> <span class="code">' + esc(a.shortId) + "</span></summary>" +
      shown.map(r => '<div class="ablock" data-block="' + r[0] + '"><b title="' + esc(r[2]) + '">' + r[1] + "</b> <div>" + atomRow(a, r[0]) + "</div></div>").join("") + "</details>";
  }

  /* ---------------------------------------------------------------- the view: reading a NodeDetail */
  const STAT_KEYS = freeze(["calls", "tokens_in", "tokens_out", "atoms_open", "atoms_closed", "atoms_failed", "atoms_total"]);

  // Open atoms first, then the newest (by ts_open); the order of the server stands where these keys tie.
  function orderAtoms(atoms) {
    const rank = a => (clean(a.state) === "open" ? 0 : 1);
    const opened = a => text(a.ts_open);
    return atoms.filter(isObj).map((a, i) => [a, i])
      .sort((x, y) => rank(x[0]) - rank(y[0]) || (opened(y[0]) > opened(x[0]) ? 1 : opened(y[0]) < opened(x[0]) ? -1 : 0) || x[1] - y[1])
      .map(pair => pair[0]);
  }

  // normalize(raw) -> the view. `raw` is the answer of GET /api/graph/nodes/{id} ({node, session, atoms, usage_total, task, archived_chats}),
  // or just the `meta` of a function node. Missing stats keys count as 0, `task` may be a string or {summary}, and a key the view does
  // not name (atom_count included) is not copied.
  function normalize(raw) {
    const r = isObj(raw) ? raw : {};
    const full = isObj(r.node);
    const node = full ? r.node : {};
    const meta = full ? (isObj(node.meta) ? node.meta : {}) : r;
    const s = isObj(meta.stats) ? meta.stats : {};
    const stats = {seconds: amount(s.seconds)};
    STAT_KEYS.forEach(k => { stats[k] = count(s[k]); });
    const task = typeof meta.task === "string" ? meta.task : (isObj(meta.task) && typeof meta.task.summary === "string" ? meta.task.summary : "");
    const atoms = orderAtoms(full && Array.isArray(r.atoms) ? r.atoms : []);
    const live = isObj(r.task) ? r.task : null;
    const usage = isObj(r.usage_total) ? {calls: orNull(r.usage_total.calls), usd: orNull(r.usage_total.usd), tokens_in: orNull(r.usage_total.tokens_in), tokens_out: orNull(r.usage_total.tokens_out)} : null;
    const fn = functionKey(node);
    return {
      view: "fnode", id: clean(node.id), kind: clean(node.kind), fn, label: clean(node.label), status: clean(node.status), detail: clean(node.detail),
      deptId: clean(node.dept_id), sessionId: clean(node.chat_session_id), runId: clean(isObj(node.meta) ? node.meta.run_id : ""),
      goal: clean(meta.goal), task: clean(task), context: strings(meta.context), constraints: strings(meta.constraints),
      waitOn: clean(meta.wait_on) || null, handsTo: strings(meta.hands_to), stats,
      usage, workingFor: live ? {id: clean(live.id), title: clean(live.title), status: clean(live.status)} : null,
      atoms, atomsTotal: Math.max(stats.atoms_total, atoms.length), archivedChats: full && Array.isArray(r.archived_chats) ? r.archived_chats.filter(isObj) : [],
    };
  }

  /* ---------------------------------------------------------------- the view: drawing it */
  const section = (name, inner) => '<section class="adsec fnsec" data-sec="' + name + '">' + inner + "</section>";
  const chipLabel = fn => '<span class="fnp">' + esc(PERSONA[fn]) + '</span> <span class="fnn">' + esc(NAMES[fn]) + "</span>";
  const chip = (fn, extra) => '<button type="button" class="fnchip" data-act="fn" data-fn="' + fn + '"' + (extra || "") + ">" + chipLabel(fn) + "</button>";

  function statusChip(v) {
    const key = statusKey(v.status);
    return '<span class="nstatus st-' + key + '">' + esc(nodeWord(v.status, v.kind, v.waitOn)) + "</span>";
  }

  function headHtml(v) {
    const known = hasOwn(PERSONA, v.fn);
    const usage = usageText(v.usage);
    return section("head",
      '<h4 class="fntitle">' + (known ? '<span class="fnp">' + esc(PERSONA[v.fn]) + "</span>" + DOT + '<span class="fnn">' + esc(NAMES[v.fn]) + "</span>" : esc(v.label || "Function")) + "</h4> " +
      statusChip(v) + ' <button type="button" class="linkbtn fnchat" data-act="chat">Chat</button>' +
      (v.detail ? '<p class="fnnow">' + esc(v.detail) + "</p>" : "") +
      (usage ? '<p class="fnusage">' + esc(usage) + "</p>" : "") +
      '<p class="fncounts">' + esc(statsText(v.stats)) + "</p>");
  }

  function taskStatus(status) {
    return hasOwn(TASK_WORDS, status) ? TASK_WORDS[status] : status.replace(/_/g, " ");
  }

  // The standing task line starts with its J2 step code ("J2.c prices, checks run limits"): the code is shown small and grey, as J2's steps are.
  function taskHtml(v) {
    const m = /^(J2(?:\.[a-h])?)(?:\s+(.*))?$/.exec(v.task);
    const line = v.task === "" ? NONE : (m ? '<span class="code">' + esc(m[1]) + "</span> " + esc(m[2] || "") : esc(v.task));
    return section("task", "<h4>Task</h4>" + '<p class="fntask">' + line + "</p>" +
      (v.workingFor && v.workingFor.title ? '<p class="fnwork">Working for: ' + esc(v.workingFor.title) + (v.workingFor.status ? " (" + esc(taskStatus(v.workingFor.status)) + ")" : "") + "</p>" : "") +
      (v.waitOn ? '<p class="fnwait">Waiting on ' + esc(whoWord(v.waitOn)) + "</p>" : ""));
  }

  function atomsHtml(v, o) {
    const open = new Set(Array.isArray(o.openIds) ? o.openIds : []);
    const more = v.atomsTotal > v.atoms.length;
    return section("atoms", "<h4>Work atoms (" + v.atomsTotal + ')</h4><p class="atomlegend">' + esc(LEGEND) + "</p>" +
      (v.atoms.length ? v.atoms.map(a => atomHtml(a, {open: open.has(text(a.id))})).join("") : '<p class="empty">No work atoms yet.</p>') +
      (more ? '<button type="button" class="linkbtn fnmore" data-act="show-all">Show all (' + v.atomsTotal + ")</button>" : ""));
  }

  function handsHtml(v) {
    const known = v.handsTo.filter(f => hasOwn(HANDOFFS, f));
    const fromIds = FUNCTIONS.filter(f => HANDOFFS[f].includes(v.fn));
    const you = '<span class="fnyou">you</span>';
    const to = known.map(f => chip(f)).join(" ") + (v.fn === "identity" ? (known.length ? " " : "") + you : "");
    const from = fromIds.map(f => chip(f)).join(" ") + (v.fn === "identity" ? (fromIds.length ? " " : "") + you : "");
    return section("hands", "<h4>Hands to</h4>" + '<div class="fnchips fnto">' + (to || NONE) + "</div>" +
      (hasOwn(HANDOFFS, v.fn) ? '<p class="fnfromlab">Handed from</p><div class="fnchips fnfrom">' + (from || NONE) + "</div>" : ""));
  }

  // render(view, opts) -> the drawer of a function node. opts.withAgent: the department page (adds the "Go to the <function> tab" button and the
  // place for J2's Summary, Conversations and Thinking); without it (Home) a line sends the owner to the team page. opts.openIds: atom ids drawn unfolded.
  function render(view, opts) {
    const v = isView(view) ? view : normalize(view);
    const o = isObj(opts) ? opts : {};
    const nameOf = hasOwn(NAMES, v.fn) ? NAMES[v.fn] : "function";
    const tail = o.withAgent === true
      ? '<div class="fntail">' + (hasOwn(FN_TAB, v.fn) ? '<button type="button" class="fngo" data-act="go-tab" data-tab="' + FN_TAB[v.fn] + '">Go to the ' + esc(nameOf) + " tab</button>" : "") +
        '<div class="fnagent" data-fnagent="' + esc(v.fn) + '"></div></div>'
      : '<p class="fnfull">Full conversations and thinking: <button type="button" class="linkbtn" data-act="open-team"' +
        (v.deptId ? ' data-href="/d/' + encodeURIComponent(v.deptId) + '/?view=detail"' : "") + ">open the team page</button>.</p>";
    return headHtml(v) + section("goal", "<h4>Goal</h4><p>" + (v.goal ? esc(v.goal) : NONE) + "</p>") + taskHtml(v) +
      section("context", "<h4>What this function is given</h4>" + (v.context.length ? '<ul class="fnlist">' + v.context.map(c => "<li>" + esc(givenWord(c)) + "</li>").join("") + "</ul>" : '<span class="empty">nothing on record</span>')) +
      atomsHtml(v, o) +
      section("constraints", "<h4>Constraints</h4>" + (v.constraints.length ? '<p class="adsmall">You may not:</p><ul class="fnlist">' + v.constraints.map(c => "<li>" + esc(c) + "</li>").join("") + "</ul>" : NONE)) +
      handsHtml(v) + tail;
  }

  /* ---------------------------------------------------------------- the five functions of a department */
  // functionsOf(department, nodes) -> "Functions of <Department>": five chips, in the order identity, adaptation, priority, coordination, audit, each
  // opening that function's panel. `department` is a graph node (or its id); a function's graph node is found by (department id, fn), never by
  // reading an id, and gives the chip its status and `data-node`.
  function functionsOf(department, nodes) {
    const dep = isObj(department) ? department : {id: text(department), label: text(department)};
    const all = (Array.isArray(nodes) ? nodes : []).filter(n => isObj(n) && n.kind === "function");
    const name = clean(dep.label) || clean(dep.name) || clean(dep.id) || "this team";
    const chips = FUNCTIONS.map(fn => {
      const n = all.find(x => clean(x.dept_id) === clean(dep.id) && functionKey(x) === fn);
      const extra = ' data-dept="' + esc(clean(dep.id)) + '"' + (n ? ' data-node="' + esc(clean(n.id)) + '"' : "");
      return '<button type="button" class="fnchip' + (n ? " st-" + statusKey(n.status) : "") + '" data-act="fn" data-fn="' + fn + '"' + extra + ">" + chipLabel(fn) +
        (n ? ' <span class="fnst">' + esc(nodeWord(n.status, "function", isObj(n.meta) ? n.meta.wait_on : null)) + "</span>" : "") + "</button>";
    });
    return '<section class="adsec fnsec fnfuncs" data-sec="functions"><h4>Functions of ' + esc(name) + '</h4><div class="fnchips">' + chips.join(" ") + "</div></section>";
  }

  /* ---------------------------------------------------------------- the other kinds of node */
  // nodeHtml(raw, ctx) -> the Details tab of any node. A function node gets the drawer (render); a team, division, step or the root gets its head,
  // what it works for, the five functions of its team, its atoms (a step may hold J2's builders) and the links that belong to it.
  // ctx {nodes, withAgent, openIds}
  function nodeHtml(raw, ctx) {
    const v = isView(raw) ? raw : normalize(raw);
    const c = isObj(ctx) ? ctx : {};
    if (v.kind === "function") return render(v, c);
    const nodes = Array.isArray(c.nodes) ? c.nodes : [];
    const word = hasOwn(KIND_WORDS, v.kind) ? KIND_WORDS[v.kind] : "step";
    const usage = usageText(v.usage);
    const dept = v.kind === "department" ? nodes.find(n => isObj(n) && n.id === v.id) || {id: v.id, label: v.label} : nodes.find(n => isObj(n) && n.id === v.deptId);
    let html = section("head", '<h4 class="fntitle">' + esc(v.label || v.id || "Node") + "</h4> " + '<span class="nkind">' + esc(word) + "</span> " + statusChip(v) +
      ' <button type="button" class="linkbtn fnchat" data-act="chat">Chat</button>' + (v.detail ? '<p class="fnnow">' + esc(v.detail) + "</p>" : "") +
      (usage ? '<p class="fnusage">' + esc(usage) + "</p>" : ""));
    if (v.kind === "division") html += '<p class="fnpart">' + esc(v.label) + " is a division of " + esc(dept ? clean(dept.label) || v.deptId : v.deptId || "its team") + ".</p>";
    if (v.workingFor && v.workingFor.title) {
      html += section("task", '<p class="fnwork">Working for: ' + esc(v.workingFor.title) + (v.workingFor.status ? " (" + esc(taskStatus(v.workingFor.status)) + ")" : "") + "</p>");
    }
    if ((v.kind === "department" || v.kind === "division") && dept) html += functionsOf(dept, nodes);
    if (v.atoms.length > 0) html += atomsHtml(v, c);
    if (v.kind === "department") {
      html += '<p class="fnlinks"><button type="button" class="linkbtn" data-act="open-team" data-href="/d/' + encodeURIComponent(v.id) + '/?view=simple">Open the team page</button></p>';
    } else if (v.kind === "step" && v.deptId) {
      const run = v.runId && TERMINAL.includes(v.status) ? "&run=" + encodeURIComponent(v.runId) : "";
      html += '<p class="fnlinks"><button type="button" class="linkbtn" data-act="open-team" data-href="' + esc("/d/" + encodeURIComponent(v.deptId) + "/?view=detail" + run) + '">' +
        (run ? "Open the run" : "Open the team page") + "</button></p>";
    } else if (v.kind === "root") {
      html += '<p class="empty">The root of the org chart. Teams and their work hang from it.</p>';
    }
    return html;
  }

  const FnodeView = {
    normalize, render, atomHtml, verifySentence, stateWord, functionsOf, normalizeAtom, nodeHtml, nodeWord, usageText, statsText, pillText, taskStatus,
    FUNCTIONS, NAMES, PERSONA, FN_TAB, HANDOFFS, GIVEN, LEGEND, MAX_ATTEMPTS,
  };
  if (typeof module === "object" && module !== null && module.exports) module.exports = FnodeView;
  else root.FnodeView = FnodeView;
})(globalThis);
