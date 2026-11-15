/* agent_chats.js - the chats of a team's agents: the Agents tab, the owner's note box, the model chip and the live row (agent-sessions design 3.7;
   D130 a chat per agent per run, D131 a model and effort per agent, D132 the owner steers with a note, D133 live partials, D134 the same picker as Claude).

   Strings in, strings out, like chat_pill.js: nothing touches the DOM and every word from the wire is escaped.

     isAgent(session)               true for a function or step chat (an agent's working log)
     sourceWord(source)             "own choice", "this run", "the team", "default"
     sourceFrom(source)             "your choice", "this run", "the team", "the app's default": what the Default button says it follows
     modelWords(eff, providers)     "Claude Sonnet, high" from {provider, model, effort}; the model's own name when `providers` (the pill's list) names it
     chip(eff, providers)           the small chip of what an agent runs on and where that comes from: <span class="achip" data-source="team">
     sessionChip(session)           the chip of a chat's own choice from its record (pinned, pinned_model, pinned_effort): an archived agent chat shows this and no pill
     stateWord(state)               the word for a function node's state ("working", "done", ...)
     usageWords(usage)              "3 calls, $0.04" ("" when nothing was spent)
     purposeLines(usage)            what the calls were for (D159): [{key, calls, usd, text, hint}] for "judging 2 calls, $0.04" (the late judge: purposes plan and judge) and
                                    "questions 1 call, $0.02" (the answers in the agent's chat: agent_chat), each only when its calls are above zero
     agentsRequest(dept, run)       {method, path, query} for GET /api/teams/{dept}/agents
     runSwitcher(runs, selected)    the run <select data-act="agents-run"> over RunRef[] (newest first)
     list(rows, opts)               the Agents tab: one row per agent chat (state, the model chip, usage and, under it, what the calls were for), a button that opens it,
                                    the run switcher; opts {runs, run, loading, error}
     noteBox(info)                  the box under an agent chat's pill: "Note to Audit" and what it says ({agent, label, live, busy}). A function's chat also
                                    offers Ask (J2 sync 4, D148): info {ask: true, mode: "note" | "ask", asking, askNote} adds the Note / Ask switch and, in
                                    Ask, the question box ("Ask Audit", answered from the run's records); a run that is over has no note, only the Ask box
     boxMode(info)                  "note" or "ask": what the box shows (Ask only for a function's chat; always Ask once the run is over)
     steerRequest(sid, text)        {method, path, body} for POST /api/chats/{sid}/steer, or null for a note that is empty or over 2,000 characters
     askRequest(dept, who, q, run)  {method, path, body} for POST /api/ask?dept=, or null for an empty question, one over 2,000 characters, or a `who` that is
                                    not one of the five functions
     askProblem(err, label)         the sentence for a question that was refused or failed
     livePartial(state, event)      the live state after a `chat.partial` of an agent's session ({active, text, tool}); `done: true` ends it
     liveRow(state, label)          the row that shows the agent working: its tool line, "writing its reply" for a reply that starts with `{`, else its text

   Buttons carry data-act="open-agent" (with data-sid, data-node, data-status), "steer", "ask" and "box-mode" (with data-mode); the select carries
   data-act="agents-run".
   A classic script with ONE global, AgentChats; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const NAMES = Object.freeze({claude: "Claude", codex: "Codex"});
  const SOURCES = Object.freeze({own: "own choice", run: "this run", team: "the team", default: "default"});
  const STATES = Object.freeze({running: "working", waiting: "waiting", waiting_on_you: "waiting for you", filed: "done", done_unchecked: "done", left_open: "left open",
    fault: "stopped by a fault", not_made: "not started", idle: "idle"});
  const MAX_NOTE = 2000;
  const MAX_ASK = 2000;                // the server's own limit for a question (views.ASK_CHARS)
  const MAX_SHOWN = 4000;
  const FUNCTIONS = Object.freeze(["identity", "adaptation", "priority", "coordination", "audit"]);        // the five that have a chat of their own and can be asked
  const NO_TOKEN = "This page was opened without its access token. Reload it from the app.";

  const FROM = Object.freeze({own: "your choice", run: "this run", team: "the team", default: "the app's default"});
  const sourceWord = source => (hasOwn(SOURCES, source) ? SOURCES[source] : "");
  const sourceFrom = source => (hasOwn(FROM, source) ? FROM[source] : "");
  const stateWord = state => (hasOwn(STATES, state) ? STATES[state] : "idle");
  const providerLabel = name => (hasOwn(NAMES, name) ? NAMES[name] : clean(name));

  function modelLabel(provider, model, providers) {
    const slug = clean(model);
    if (slug === "") return "";
    const pill = (Array.isArray(providers) ? providers : []).find(p => isObj(p) && p.name === provider);
    const option = pill && Array.isArray(pill.model_options) ? pill.model_options.find(o => isObj(o) && clean(o.slug) === slug) : null;
    return option && clean(option.label) !== "" ? clean(option.label) : slug;
  }

  function modelWords(eff, providers) {
    if (!isObj(eff) || clean(eff.provider) === "") return "";
    const model = modelLabel(eff.provider, eff.model, providers);
    const effort = clean(eff.effort);
    return providerLabel(eff.provider) + (model ? " " + model : "") + (effort ? ", " + effort : "");
  }

  function chip(eff, providers) {
    const words = modelWords(eff, providers);
    if (words === "") return '<span class="achip achip-none" data-source="default">no model known yet</span>';
    const source = isObj(eff) && hasOwn(SOURCES, eff.source) ? eff.source : "default";
    return '<span class="achip" data-source="' + source + '" title="' + esc(words + " (" + sourceWord(source) + ")") + '">' + esc(words) +
      ' <small class="achip-src">' + esc(sourceWord(source)) + "</small></span>";
  }

  function sessionChip(session) {
    if (!isObj(session) || clean(session.pinned) === "") return "";
    return chip({provider: clean(session.pinned), model: clean(session.pinned_model) || null, effort: clean(session.pinned_effort) || null, source: "own"});
  }

  const isAgent = session => isObj(session) && (session.kind === "function" || session.kind === "step");

  function usageWords(usage) {
    if (!isObj(usage) || !Number.isFinite(usage.calls) || usage.calls <= 0) return "";
    const calls = usage.calls + (usage.calls === 1 ? " call" : " calls");
    return Number.isFinite(usage.usd) && usage.usd > 0 ? calls + ", $" + (usage.usd < 0.01 ? usage.usd.toFixed(4) : usage.usd.toFixed(2)) : calls;
  }

  // What the agent's calls were for (D159). `usage.by_purpose` is {purpose: {calls, usd}} for each purpose the agent's session was charged for. Two lines are drawn
  // under its usage: "judging" is the late judge's work (the purposes `plan` and `judge`, D145) and "questions" the answers given in the agent's chat (`agent_chat`,
  // D147). The rest (the agent's own turns, a helper's summary) is the usage line above it, so nothing more is said about it here.
  const PURPOSE_LINES = Object.freeze([
    Object.freeze({key: "judging", purposes: Object.freeze(["judge", "plan"]), hint: "Calls that planned or judged a workflow in this agent's turn"}),
    Object.freeze({key: "questions", purposes: Object.freeze(["agent_chat"]), hint: "Answers this agent gave to questions asked in its chat"})]);

  function purposeLines(usage) {
    const by = isObj(usage) && isObj(usage.by_purpose) ? usage.by_purpose : {};
    const out = [];
    PURPOSE_LINES.forEach(line => {
      let calls = 0;
      let usd = null;
      line.purposes.forEach(p => {
        const cell = hasOwn(by, p) && isObj(by[p]) ? by[p] : null;
        if (cell === null || !Number.isFinite(cell.calls) || cell.calls <= 0) return;
        calls += cell.calls;
        if (Number.isFinite(cell.usd)) usd = (usd === null ? 0 : usd) + cell.usd;
      });
      if (calls > 0) out.push({key: line.key, calls, usd, text: line.key + " " + usageWords({calls, usd}), hint: line.hint});
    });
    return out;
  }

  function agentsRequest(dept, run) {
    const query = clean(run) !== "" ? {run: clean(run)} : {};
    return {method: "GET", path: "/api/teams/" + encodeURIComponent(clean(dept)) + "/agents", query};
  }

  function runSwitcher(runs, selected) {
    const items = (Array.isArray(runs) ? runs : []).filter(r => isObj(r) && clean(r.run_id) !== "");
    if (items.length < 2) return "";
    const now = clean(selected) || clean(items[0].run_id);
    return '<label class="agents-run">Run <select data-act="agents-run" aria-label="Run">' + items.slice(0, 50).map((r, i) => {
      const id = clean(r.run_id);
      const word = (i === 0 ? "latest" : id) + (clean(r.status) ? " (" + clean(r.status).replace(/_/g, " ") + ")" : "");
      return '<option value="' + esc(id) + '"' + (id === now ? " selected" : "") + ">" + esc(word) + "</option>";
    }).join("") + "</select></label>";
  }

  function row(r) {
    const sid = clean(r.session_id);
    const past = clean(r.status) === "archived";
    const state = past ? "past" : (r.live === true ? "running" : clean(r.state) || "idle");
    const dot = '<span class="agent-dot" data-state="' + esc(state) + '" aria-hidden="true"></span>';
    const word = past ? "past run" : stateWord(clean(r.state));
    const usage = usageWords(r.usage);
    const purposes = purposeLines(r.usage);
    return '<li class="agent" data-kind="' + esc(clean(r.kind)) + '" data-state="' + esc(state) + '">' +
      '<button type="button" class="agent-open" data-act="open-agent" data-sid="' + esc(sid) + '" data-node="' + esc(clean(r.node_id)) + '" data-status="' +
      esc(clean(r.status)) + '" title="' + esc(clean(r.title)) + '">' + dot + '<span class="agent-name">' + esc(clean(r.label) || clean(r.agent)) + "</span>" +
      '<span class="agent-state">' + esc(word) + "</span></button>" + chip(r.effective) + (usage ? '<span class="agent-usage">' + esc(usage) + "</span>" : "") +
      (purposes.length ? '<span class="agent-purposes">' + purposes.map(p => '<span class="agent-purpose" data-line="' + p.key + '" title="' + esc(p.hint) + '">' + esc(p.text) + "</span>").join("") + "</span>" : "") + "</li>";
  }

  function list(rows, opts) {
    const o = isObj(opts) ? opts : {};
    if (clean(o.error) !== "") return '<p class="empty nempty">' + esc(clean(o.error)) + "</p>";
    if (o.loading === true) return '<p class="empty nempty">Loading…</p>';
    const items = (Array.isArray(rows) ? rows : []).filter(r => isObj(r) && clean(r.session_id) !== "");
    const switcher = runSwitcher(o.runs, o.run);
    if (items.length === 0) return (switcher ? '<div class="agents-head">' + switcher + "</div>" : "") + '<p class="empty nempty">No agent has a chat yet. Each agent gets its own chat when a run starts.</p>';
    const functions = items.filter(r => r.kind === "function");
    const steps = items.filter(r => r.kind !== "function");
    const withRun = items.find(r => isObj(r.run_pick));
    const runLine = withRun ? '<p class="agents-runpick">For this run: ' + chip(Object.assign({}, withRun.run_pick, {source: "run"})) + "</p>" : "";
    const group = (title, rs) => (rs.length ? '<h4 class="agents-h">' + esc(title) + '</h4><ul class="agents-list">' + rs.map(row).join("") + "</ul>" : "");
    return '<div class="agents">' + (switcher ? '<div class="agents-head">' + switcher + "</div>" : "") + runLine + group("The team", functions) + group("Workflows", steps) +
      '<p class="agents-note">Each agent works in a chat of its own, new for every run. Open one to choose its model or to leave it a note.</p></div>';
  }

  // What the box under an agent's pill shows: a note (the steer route) or a question (POST /api/ask). Only a function's chat offers the question; once the
  // run is over there is nothing to steer, so the question is all that is left.
  function boxMode(info) {
    const i = isObj(info) ? info : {};
    if (i.ask !== true) return "note";
    if (i.live !== true) return "ask";
    return i.mode === "ask" ? "ask" : "note";
  }

  function modeToggle(mode, label, disabled) {
    const opt = (key, word) => '<button type="button" class="ccmode-opt' + (mode === key ? " on" : "") + '" data-act="box-mode" data-mode="' + key + '" aria-pressed="' +
      String(mode === key) + '"' + (disabled ? " disabled" : "") + ">" + word + "</button>";
    return '<div class="ccmode nboxmode" role="group" aria-label="What to send to ' + esc(label) + '">' + opt("note", "Note") + opt("ask", "Ask") + "</div>";
  }

  function askBox(i, label) {
    const busy = i.asking === true;
    const said = clean(i.askNote);
    return '<div class="nnotebox naskbox"><label class="nnote-l">Ask ' + esc(label) + '</label><div class="row"><textarea class="nask-text" rows="2" maxlength="' + MAX_ASK +
      '" aria-label="Ask ' + esc(label) + '" placeholder="Ask ' + esc(label) + ' about this run"' + (busy ? " disabled" : "") + "></textarea>" +
      '<button type="button" class="send" data-act="ask"' + (busy ? " disabled" : "") + ">Ask</button></div>" +
      (busy ? '<small class="nnote-help nask-wait" role="status">Asking ' + esc(label) + "\u2026</small>"
        : '<small class="nnote-help">' + esc(label) + " answers from this run's records and cannot change the run. The question and the answer stay in this chat.</small>" +
          (said !== "" ? '<small class="nnote-help nask-note" role="status">' + esc(said) + "</small>" : "")) + "</div>";
  }

  function noteBox(info) {
    const i = isObj(info) ? info : {};
    const label = clean(i.label) || clean(i.agent) || "the agent";
    const mode = boxMode(i);
    const ask = i.ask === true;
    if (mode === "ask") {
      return (i.live === true ? modeToggle(mode, label, i.asking === true)
        : '<p class="nnote-over" role="note">That run is over. ' + esc(label) + " can no longer read a note. You can still ask it about the run.</p>") + askBox(i, label);
    }
    if (i.live !== true) return '<p class="nnote-over" role="note">That run is over. ' + esc(label) + " can no longer read a note.</p>";
    return (ask ? modeToggle(mode, label, i.busy === true) : "") + '<div class="nnotebox"><label class="nnote-l">Note to ' + esc(label) + '</label><div class="row"><textarea class="nnote-text" rows="2" maxlength="' + MAX_NOTE +
      '" aria-label="Note to ' + esc(label) + '" placeholder="Tell ' + esc(label) + ' what to do differently"' + (i.busy === true ? " disabled" : "") + "></textarea>" +
      '<button type="button" class="send" data-act="steer"' + (i.busy === true ? " disabled" : "") + ">Send note</button></div>" +
      '<small class="nnote-help">' + esc(label) + " reads this at its next step.</small></div>";
  }

  function steerRequest(sid, value) {
    const body = text(value).trim();
    if (body === "" || body.length > MAX_NOTE) return null;
    return {method: "POST", path: "/api/chats/" + encodeURIComponent(clean(sid)) + "/steer", body: {text: body}};
  }

  // The owner's question to a function (D147): one POST that the server answers from the function's records (and, when a model is connected, with a model
  // call of the function's own session). `run` is the run the chat belongs to; the server takes the page's current run for "".
  function askRequest(dept, who, value, run) {
    const question = text(value).trim();
    const fn = clean(who);
    const team = clean(dept);
    if (question === "" || question.length > MAX_ASK || team === "" || !FUNCTIONS.includes(fn)) return null;
    return {method: "POST", path: "/api/ask?dept=" + encodeURIComponent(team), body: {who: fn, q: question, run: clean(run)}};
  }

  // The words for a question that was refused: the route answers J2's {error: "..."} bodies (400 not a function, 400 question too long, 409 busy) and the
  // app's own envelope (401 bad_token, 403 read_only).
  function askProblem(err, label) {
    const e = isObj(err) ? err : {};
    const status = Number.isFinite(e.status) ? e.status : 0;
    const code = typeof e.code === "string" ? e.code : "";
    const said = clean(e.message).toLowerCase();
    const who = clean(label) || "The agent";
    if (status === 401 || code === "bad_token") return NO_TOKEN;
    if (status === 403 || code === "read_only") return "This team is read-only, so it cannot be asked.";
    if (status === 409) return who + " is still answering. Ask again in a moment.";
    if (status === 400 && said.includes("too long")) return "A question can be up to " + MAX_ASK.toLocaleString("en-US") + " characters.";
    if (status === 400 && said.includes("not a function")) return "Only the team's five functions can be asked.";
    if (status === 400) return "That question could not be sent.";
    if (status === 0 || code === "network") return "The app is not responding. Try again in a moment.";
    return "Something went wrong. Try again.";
  }

  // The live row. The server sends the agent's whole text so far with `reset: true` each time (agent_live.json is a snapshot, not a stream of pieces), and
  // `{reset: true, delta: "", done: true}` when the agent's call ends: the row goes away and the stored line arrives from the `say` event.
  const idle = () => ({active: false, text: "", tool: ""});
  function livePartial(state, event) {
    const d = isObj(event) && isObj(event.data) ? event.data : (isObj(event) ? event : {});
    if (d.done === true) return idle();
    const shown = text(d.delta);
    const tool = clean(d.tool) !== "" ? clean(d.tool) : (d.reset === true ? "" : (isObj(state) ? clean(state.tool) : ""));
    const kept = d.reset === true ? "" : (isObj(state) && state.active ? text(state.text) : "");
    const full = kept + shown;
    return {active: true, text: full.length > MAX_SHOWN ? full.slice(-MAX_SHOWN) : full, tool};
  }

  function liveRow(state, label) {
    if (!isObj(state) || state.active !== true) return "";
    const who = clean(label) || "The agent";
    const body = text(state.text);
    const raw = body.trimStart().startsWith("{");
    const tool = clean(state.tool);
    const parts = [];
    if (tool !== "") parts.push('<span class="alive-tool">' + esc(tool) + "</span>");
    if (raw) parts.push('<span class="alive-note">writing its reply</span>');
    else if (body !== "") parts.push('<div class="cstream-text">' + esc(body).replace(/\r\n|\r|\n/g, "<br/>") + "</div>");
    return '<div class="cstream agentlive" role="status" aria-live="polite"><small>' + esc(who) + " is working…</small>" + parts.join("") + "</div>";
  }

  const AgentChats = {isAgent, sourceWord, sourceFrom, modelWords, chip, sessionChip, stateWord, usageWords, purposeLines, agentsRequest, runSwitcher, list, noteBox, boxMode,
    steerRequest, askRequest, askProblem, livePartial, liveRow, idle, MAX_NOTE, MAX_ASK, FUNCTIONS, SOURCES};
  if (typeof module === "object" && module !== null && module.exports) module.exports = AgentChats;
  else root.AgentChats = AgentChats;
})(globalThis);
