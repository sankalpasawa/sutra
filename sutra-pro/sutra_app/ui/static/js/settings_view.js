/* settings_view.js - the Settings pane of Home: the Appearance, Connectors and Engine groups (work package UI-7; docs/design/ui.md sections 3.3,
   6.6, 7, 8 and 10; S1-contracts-03, S1-contracts-08, S3-web-06; D18).

   Strings in, strings out, plus the few small flows that talk to the server through an `api` the caller hands in (SutraCtx.api, or a fake in a
   test): this file touches no DOM, no timer of its own and no global but its own, so `node --test` runs all of it.

     engineHtml(settings, {scope, departments, errors, values, saved, busy}) -> html   the Engine group: a toggle or a number field for every `editable`
                                          field of GET /api/engine/settings, every `locked` field read-only with the note "edit data/engine.json",
                                          a scope select (all teams, or one team), and the line "Changes apply to the next run."
                                          (`values` are what the owner typed, kept beside a refusal)
     engineBody(settings, form) -> {set, unset}   the PUT body: only the fields that changed; a field that goes back to the value of the layer
                                          below (defaults for all teams; defaults and the all-teams file for one team) is `unset`
     engineErrors(error) -> {field: sentence}      what a 422 `validation` names, key "" for a sentence about the whole form
     connectorsHtml(health, state) -> html        the Connectors group from GET /api/health: a row per provider with Test and, for codex only, Sign in
     signInState(prev, answer) -> {step, url, code, expires_in, message}   the sign-in reducer (start answer, poll answer, an error)
     appearanceHtml(pref) -> html                 the Appearance group: Light | Dark | System (localStorage j2theme, one choice for both pages)

     testConnector(api, provider) -> Promise<{provider, ok, seconds, message, line}>       POST /api/connectors/{provider}/test
     signIn(api, {onState, sleep, pollMs}) -> {done, cancel}   POST /api/connectors/codex/sign-in, GET ...{id} until signed_in, failed or expired, DELETE
     watchHealth(api, onHealth, onError) -> {onEvent(type), refetch()}   GET /api/health again on connector.health, connector.switch, connector.mode
     loadEngine(api, scope) / saveEngine(api, settings, scope, form)     GET and PUT /api/engine/settings; `dept` is put in the query by hand and
                                          left out for all teams (these paths are outside J2_PATHS, so the fetch wrapper never adds it)

   There is no control to pin a chat to a provider in v1 (S1-contracts-08). Every word from the wire goes through esc(); a sign-in link is a link
   only when it is https.

   A classic script with ONE global, SettingsView; in node it is module.exports. */
(function (root) {
  "use strict";

  /* ---------------------------------------------------------------- small helpers */
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (finite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const enc = encodeURIComponent;
  const freeze = Object.freeze;

  const ENGINE_PATH = "/api/engine/settings";
  const HEALTH_PATH = "/api/health";
  const NOTE_LOCKED = "edit data/engine.json";
  const NOTE_NEXT_RUN = "Changes apply to the next run.";
  const HEALTH_EVENTS = freeze(["connector.health", "connector.switch", "connector.mode"]);
  const SIGN_IN_GRACE_S = 30;      // seconds past `expires_in` after which the page stops asking by itself
  const POLL_MS = 2000;
  const THEMES = freeze([["light", "Light"], ["dark", "Dark"], ["system", "System"]]);

  /* ---------------------------------------------------------------- the engine fields */
  // [label, hint] for every field of EngineSettings (sutra_app/engine/spec.py). A field this table does not know is shown under its own name.
  const FIELD_TEXT = freeze({
    output: ["What to build", "The kind of result a new run makes"],
    fixes: ["Fix pass", "Let a run make a second pass to repair what the checks refused"],
    budget: ["Budget", "Work credits one run may spend"],
    budget_cap: ["Budget cap", "The most a run may spend; empty means twice the budget"],
    max_cycles: ["Most cycles", "How many build and check rounds one run may take"],
    limit_add: ["Credits added on a raised limit", "What a raised limit adds to the budget"],
    bargain_minutes: ["Bargaining time (minutes)", "How long the functions may bargain over a conflict"],
    bargain_calls: ["Bargaining calls", "How many model calls the bargaining may use"],
    max_turns: ["Most turns", "How many turns one run may take"],
    chat_full_chars: ["Chat kept in full (characters)", "Older chat is shortened beyond this"],
    delay: ["Pause between calls (seconds)", "A wait before each model call"],
    rates: ["Price the work", "Priority prices each piece of work"],
    slim: ["Shorter prompts", "Send each function only what it needs"],
    memory: ["Remember lessons", "Keep lessons from earlier runs"],
    realization: ["Realization pass", "Adaptation plans how each result is made"],
    change: ["Change requests", "Allow a change request on a finished run"],
    board: ["Board story", "Show the Board and its story"],
    artifact_schema: ["Artifact schema", "Check artifacts against their schema"],
    template_library: ["Template library", "Builders use the template library"],
    tap_min: ["Smallest tap target (px)", "The least size a button may have on a phone"],
    send_mode: ["Email sending", "dry-run writes no email"],
    send_cap: ["Emails per run", ""],
    milestone_emails: ["Milestone emails", ""],
    test_email: ["Test email address", ""],
    test_slack_target: ["Test Slack target", ""],
    chrome: ["Chrome path", ""],
    force_audit_fail: ["Force audit failures", "A test switch"],
    force_audit_note: ["Forced audit note", "A test switch"],
    force_question: ["Forced question", "A test switch"],
    memory_test_lessons: ["Test lessons", "A test switch"],
  });
  const CHOICES = freeze({output: freeze(["website", "prd", "hld", "lld"])});
  const FLAGS01 = freeze(["fixes"]);                   // 0 or 1 on the wire, a toggle on the page
  const FLOATS = freeze(["bargain_minutes", "delay"]); // JSON cannot tell 15.0 from 15, so the float fields are named
  const NULLABLE = freeze(["budget_cap"]);             // empty means "not set" (null)
  const GROUPS = freeze({appearance: "Appearance", connectors: "Connectors", engine: "Engine"});

  const textOf = field => (hasOwn(FIELD_TEXT, field) ? FIELD_TEXT[field] : [field.replace(/_/g, " "), ""]);

  // The kind of control a field gets, from its default: toggle (boolean), flag (0/1), choice (a closed list), int, float, nullint (int or empty), text.
  function kindOf(field, defaults) {
    if (hasOwn(CHOICES, field)) return "choice";
    if (FLAGS01.includes(field)) return "flag";
    if (NULLABLE.includes(field)) return "nullint";
    const v = isObj(defaults) ? defaults[field] : undefined;
    if (typeof v === "boolean") return "toggle";
    if (typeof v === "number") return FLOATS.includes(field) ? "float" : "int";
    return "text";
  }

  // parseValue(kind, raw, field) -> {ok, value}. A form hands strings (an input's value) or ready values; anything that does not read is not ok.
  function parseValue(kind, raw, field) {
    switch (kind) {
      case "toggle":
        if (typeof raw === "boolean") return {ok: true, value: raw};
        if (raw === "true" || raw === "false") return {ok: true, value: raw === "true"};
        return {ok: false};
      case "flag":
        if (typeof raw === "boolean") return {ok: true, value: raw ? 1 : 0};
        if (raw === 0 || raw === 1) return {ok: true, value: raw};
        if (raw === "0" || raw === "1") return {ok: true, value: Number(raw)};
        return {ok: false};
      case "choice":
        return typeof raw === "string" && CHOICES[field].includes(raw) ? {ok: true, value: raw} : {ok: false};
      case "int":
      case "float": {
        const s = typeof raw === "number" ? String(raw) : (typeof raw === "string" ? raw.trim() : "");
        if (s === "" || !/^-?\d+(\.\d+)?$/.test(s)) return {ok: false};
        const n = Number(s);
        return finite(n) && (kind === "float" || Number.isInteger(n)) ? {ok: true, value: n} : {ok: false};
      }
      case "nullint":
        if (raw === null || raw === undefined || (typeof raw === "string" && raw.trim() === "")) return {ok: true, value: null};
        return parseValue("int", raw, field);
      default:
        return typeof raw === "string" ? {ok: true, value: raw} : {ok: false};
    }
  }

  const same = (a, b) => a === b;

  // The layers below the one being edited: for all teams, the defaults; for one team (the answer has `department`), the defaults and the all-teams file.
  const scopedAnswer = settings => isObj(settings) && isObj(settings.department);
  const layerOf = settings => (scopedAnswer(settings) ? settings.department : (isObj(settings) && isObj(settings.global) ? settings.global : {}));
  function baseOf(settings) {
    const defaults = isObj(settings.defaults) ? settings.defaults : {};
    return scopedAnswer(settings) ? Object.assign({}, defaults, isObj(settings.global) ? settings.global : {}) : defaults;
  }
  const listOf = v => (Array.isArray(v) ? v.filter(f => typeof f === "string") : []);

  // engineBody(settings, form) -> {set, unset}. `form` maps a field to what the page holds now. Only editable fields are looked at, only a
  // changed one is sent, and a field that goes back to the value of the layer below is removed from this layer (when this layer holds it) instead
  // of being pinned. A value that does not read is left out (engineErrors tells the page which).
  function engineBody(settings, form) {
    const body = {set: {}, unset: []};
    if (!isObj(settings) || !isObj(form)) return body;
    const defaults = isObj(settings.defaults) ? settings.defaults : {};
    const effective = isObj(settings.effective) ? settings.effective : defaults;
    const base = baseOf(settings);
    const layer = layerOf(settings);
    listOf(settings.editable).forEach(field => {
      if (!hasOwn(form, field)) return;
      const parsed = parseValue(kindOf(field, defaults), form[field], field);
      if (!parsed.ok) return;
      const start = hasOwn(effective, field) ? effective[field] : defaults[field];
      if (same(parsed.value, start === undefined ? null : start)) return;
      if (same(parsed.value, base[field] === undefined ? null : base[field]) && hasOwn(layer, field)) body.unset.push(field);
      else body.set[field] = parsed.value;
    });
    return body;
  }

  // The fields of the form whose text cannot be read, with the sentence for each ({} when all read).
  function formProblems(settings, form) {
    const problems = {};
    if (!isObj(settings) || !isObj(form)) return problems;
    const defaults = isObj(settings.defaults) ? settings.defaults : {};
    listOf(settings.editable).forEach(field => {
      if (!hasOwn(form, field)) return;
      const kind = kindOf(field, defaults);
      if (!parseValue(kind, form[field], field).ok) {
        problems[field] = kind === "int" || kind === "nullint" ? "Write a whole number." : (kind === "float" ? "Write a number." : "This value is not valid.");
      }
    });
    return problems;
  }

  // engineErrors(error) -> {field: sentence}. A 422 `validation` lists violations {path: "set.budget", code, message}; the field is the part of
  // the path after the first dot. Anything else is one sentence for the whole form under the key "".
  function engineErrors(error) {
    const out = {};
    const details = isObj(error) && isObj(error.details) ? error.details : {};
    const list = Array.isArray(details.violations) ? details.violations : [];
    list.forEach(v => {
      if (!isObj(v)) return;
      const path = clean(v.path);
      const field = path.indexOf(".") >= 0 ? path.slice(path.indexOf(".") + 1) : path;
      const sentence = clean(v.message) || clean(error.message) || "This value was refused.";
      if (field !== "" && !hasOwn(out, field)) out[field] = sentence;
    });
    if (Object.keys(out).length === 0) out[""] = clean(isObj(error) ? error.message : "") || "The settings could not be saved.";
    return out;
  }

  /* ---------------------------------------------------------------- Engine group */
  const showValue = v => (v === null || v === undefined || v === "" ? "(empty)" : (v === true ? "on" : (v === false ? "off" : String(v))));

  function fieldInput(field, kind, value, id) {
    const common = ' id="' + id + '" name="' + esc(field) + '" data-input="' + esc(field) + '"';
    if (kind === "toggle") return '<input type="checkbox"' + common + (value === true ? " checked" : "") + ">";
    if (kind === "flag") return '<input type="checkbox"' + common + (value === 1 || value === true ? " checked" : "") + ">";
    if (kind === "choice") {
      const options = CHOICES[field].includes(value) ? CHOICES[field] : CHOICES[field].concat(value === undefined || value === null ? [] : [String(value)]);
      return "<select" + common + ">" + options.map(o => '<option value="' + esc(o) + '"' + (o === value ? " selected" : "") + ">" + esc(o) + "</option>").join("") + "</select>";
    }
    if (kind === "int" || kind === "nullint") {
      return '<input type="number" step="1" inputmode="numeric"' + common + ' value="' + (value === null || value === undefined ? "" : esc(value)) + '"' +
        (kind === "nullint" ? ' placeholder="not set"' : "") + ">";
    }
    if (kind === "float") return '<input type="number" step="any" inputmode="decimal"' + common + ' value="' + esc(value === undefined || value === null ? "" : value) + '">';
    return '<input type="text" maxlength="500"' + common + ' value="' + esc(value === undefined || value === null ? "" : value) + '">';
  }

  function sourceOf(settings, field) {
    if (scopedAnswer(settings) && hasOwn(settings.department, field)) return "team";
    if (isObj(settings.global) && hasOwn(settings.global, field)) return "all";
    return "default";
  }
  const SOURCE_TAG = freeze({team: "set for this team", all: "set for all teams", default: ""});

  function editableRow(settings, field, errors, shown) {
    const defaults = isObj(settings.defaults) ? settings.defaults : {};
    const effective = isObj(settings.effective) ? settings.effective : defaults;
    const kind = kindOf(field, defaults);
    const [label, hint] = textOf(field);
    const id = "setf-" + field;
    const source = sourceOf(settings, field);
    const value = hasOwn(shown, field) ? shown[field] : (hasOwn(effective, field) ? effective[field] : defaults[field]);
    return '<div class="setfield" data-field="' + esc(field) + '" data-locked="false" data-kind="' + kind + '" data-source="' + source + '">' +
      '<label class="setlabel" for="' + id + '">' + esc(label) + "</label>" + fieldInput(field, kind, value, id) +
      (SOURCE_TAG[source] ? '<span class="settag">' + SOURCE_TAG[source] + "</span>" : "") +
      (hint ? '<span class="sethint">' + esc(hint) + "</span>" : "") +
      (errors[field] ? '<span class="seterr" role="alert">' + esc(errors[field]) + "</span>" : "") + "</div>";
  }

  function lockedRow(settings, field) {
    const effective = isObj(settings.effective) ? settings.effective : {};
    const [label] = textOf(field);
    return '<div class="setfield" data-field="' + esc(field) + '" data-locked="true">' +
      '<span class="setlabel">' + esc(label) + '</span><span class="setvalue" data-readonly="true">' + esc(showValue(effective[field])) + "</span>" +
      '<span class="setlock">' + NOTE_LOCKED + "</span></div>";
  }

  function scopeSelect(scope, departments) {
    const list = (Array.isArray(departments) ? departments : []).filter(d => isObj(d) && clean(d.id) !== "");
    const chosen = clean(scope);
    const options = [{id: "", name: "All teams"}].concat(list.map(d => ({id: clean(d.id), name: clean(d.name) || clean(d.id)})));
    if (chosen !== "" && !options.some(o => o.id === chosen)) options.push({id: chosen, name: chosen});
    return '<label class="setscope">Applies to <select data-scope aria-label="Applies to">' +
      options.map(o => '<option value="' + esc(o.id) + '"' + (o.id === chosen ? " selected" : "") + ">" + esc(o.name) + "</option>").join("") + "</select></label>";
  }

  function engineHtml(settings, options) {
    const o = isObj(options) ? options : {};
    const errors = isObj(o.errors) ? o.errors : {};
    const values = isObj(o.values) ? o.values : {};
    const head = '<section class="setgrp" data-group="engine" aria-labelledby="set-engine-h"><h3 id="set-engine-h">' + GROUPS.engine + "</h3>";
    if (!isObj(settings) || !Array.isArray(settings.editable)) {
      return head + '<p class="setnote">' + NOTE_NEXT_RUN + '</p><p class="setempty">The engine settings are not loaded yet.</p></section>';
    }
    const scoped = clean(o.scope) !== "";
    const editable = listOf(settings.editable);
    const locked = listOf(settings.locked);
    return head + '<p class="setnote">' + NOTE_NEXT_RUN + (scoped ? " These values are for this team only." : " These values are for every team.") + "</p>" +
      scopeSelect(o.scope, o.departments) +
      (errors[""] ? '<p class="seterr setgen" role="alert">' + esc(errors[""]) + "</p>" : "") +
      '<div class="setfields">' + editable.map(f => editableRow(settings, f, errors, values)).join("") + "</div>" +
      (locked.length ? '<h4 class="setsub">Locked</h4><div class="setfields setlocked">' + locked.map(f => lockedRow(settings, f)).join("") + "</div>" : "") +
      '<div class="setacts"><button type="button" class="ghost" data-act="save-engine"' + (o.busy === true ? " disabled" : "") + ">Save</button>" +
      '<span class="setstatus" role="status">' + (o.saved === true ? "Saved. " + NOTE_NEXT_RUN : "") + "</span></div></section>";
  }

  /* ---------------------------------------------------------------- Appearance group */
  function appearanceHtml(pref) {
    const now = THEMES.some(t => t[0] === pref) ? pref : "dark";
    return '<section class="setgrp" data-group="appearance" aria-labelledby="set-appearance-h"><h3 id="set-appearance-h">' + GROUPS.appearance + "</h3>" +
      '<div class="appear"><span class="seg" role="group" aria-label="Appearance">' +
      THEMES.map(t => '<button type="button" data-themepick="' + t[0] + '" aria-pressed="' + (t[0] === now) + '">' + t[1] + "</button>").join("") +
      '</span><span class="sethint">One choice for every page. System follows your device.</span></div></section>';
  }

  /* ---------------------------------------------------------------- sign-in */
  const NO_SIGNIN = freeze({step: "idle", url: "", code: "", expires_in: 0, message: ""});
  const SIGNIN_WORDS = freeze({
    pending: "Open the link and type the code.",
    signed_in: "Signed in.",
    failed: "Sign in did not work. Try again.",
    expired: "The code ran out. Press Sign in for a new one.",
    cancelled: "Sign in cancelled.",
  });

  // signInState(prev, answer) -> {step, url, code, expires_in, message}, step one of idle, pending, signed_in, failed, expired, cancelled, error.
  //   a start answer {id, url, code, expires_in}  -> pending, with the link and the code
  //   a poll answer {state}                        -> pending keeps the link and the code; signed_in, failed, expired and cancelled end it
  //   an error (anything with a message)           -> error, with the server's sentence
  function signInState(prev, answer) {
    const before = isObj(prev) && typeof prev.step === "string" ? prev : NO_SIGNIN;
    const keep = {url: clean(before.url), code: clean(before.code), expires_in: finite(before.expires_in) ? before.expires_in : 0};
    const end = (step, message) => ({step, url: "", code: "", expires_in: 0, message: message || SIGNIN_WORDS[step]});
    if (!isObj(answer) && !(answer instanceof Error)) return before;
    if (answer instanceof Error || (typeof answer.message === "string" && !hasOwn(answer, "state") && !hasOwn(answer, "url"))) {
      return end("error", clean(answer.message) || "Sign in could not start.");
    }
    if (hasOwn(answer, "url") || hasOwn(answer, "code")) {
      return {step: "pending", url: clean(answer.url), code: clean(answer.code), expires_in: finite(answer.expires_in) && answer.expires_in > 0 ? Math.floor(answer.expires_in) : 0,
        message: SIGNIN_WORDS.pending};
    }
    switch (answer.state) {
      case "pending": return Object.assign({step: "pending", message: SIGNIN_WORDS.pending}, keep);
      case "signed_in": return end("signed_in");
      case "failed": return end("failed");
      case "expired": return end("expired");
      case "cancelled": return end("cancelled");
      default: return end("error", "The app answered something unexpected. Try again.");
    }
  }

  /* ---------------------------------------------------------------- Connectors group */
  const PROVIDER_NAMES = freeze({claude: "Claude", codex: "Codex"});
  const HEALTH_WORDS = freeze({ok: "Ready", signed_out: "Not signed in", degraded: "Limited"});
  const providerName = p => (hasOwn(PROVIDER_NAMES, p) ? PROVIDER_NAMES[p] : clean(p));

  function healthChip(c) {
    if (c.installed === false) return ["missing", "Not installed"];
    const state = isObj(c.health) ? clean(c.health.state) : "";
    if (state === "") return [c.signed_in === false ? "signed_out" : "ok", c.signed_in === false ? HEALTH_WORDS.signed_out : HEALTH_WORDS.ok];
    return [state, hasOwn(HEALTH_WORDS, state) ? HEALTH_WORDS[state] : state.replace(/_/g, " ")];
  }

  const secondsLine = seconds => (finite(seconds) ? "Worked in " + seconds.toFixed(1) + " s" : "Worked");

  function testLine(entry) {
    if (!isObj(entry)) return "";
    if (entry.step === "running") return "Testing…";
    if (entry.step === "ok") return secondsLine(entry.seconds);
    if (entry.step === "error") return clean(entry.message) || "The test did not pass.";
    return "";
  }

  function signInBox(s) {
    if (!isObj(s) || s.step === "idle") return "";
    const link = /^https:\/\//i.test(s.url) ? '<a class="sulink" href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(s.url) + "</a>" : esc(s.url);
    const minutes = s.expires_in >= 60 ? Math.round(s.expires_in / 60) : 0;
    const body = s.step === "pending"
      ? "<p>" + esc(s.message) + "</p>" + (s.url ? '<p class="silink">Link: ' + link + "</p>" : "") +
        (s.code ? '<p class="sicodeline">Code: <code class="sicode">' + esc(s.code) + "</code></p>" : "") +
        (minutes ? '<p class="sethint">The code works for about ' + minutes + " minutes.</p>" : "") +
        '<button type="button" class="ghost" data-act="cancel" data-provider="codex">Cancel</button>'
      : "<p>" + esc(s.message) + "</p>";
    return '<div class="signin" data-step="' + esc(s.step) + '" role="status">' + body + "</div>";
  }

  function providerOrder(connectors) {
    const names = Object.keys(connectors);
    return ["claude", "codex"].filter(n => names.includes(n)).concat(names.filter(n => n !== "claude" && n !== "codex").sort());
  }

  function connectorRow(name, c, state) {
    const [tone, word] = healthChip(c);
    const test = isObj(state) && isObj(state.test) && isObj(state.test[name]) ? state.test[name] : {step: "idle"};
    const signin = name === "codex" && isObj(state) && isObj(state.signin) ? state.signin : NO_SIGNIN;
    const detail = [clean(c.detail), c.version ? "version " + clean(c.version) : "", isObj(c.health) && clean(c.health.reason) && tone !== "signed_out" ? clean(c.health.reason) : ""]
      .filter(Boolean).join(" · ");
    const line = testLine(test);
    return '<div class="setconn" data-provider="' + esc(name) + '" data-state="' + esc(tone) + '">' +
      '<div class="sethead"><b>' + esc(providerName(name)) + '</b><span class="setchip st-' + esc(tone) + '">' + esc(word) + "</span></div>" +
      (detail ? '<p class="setdetail">' + esc(detail) + "</p>" : "") +
      '<div class="setacts"><button type="button" class="ghost" data-act="test" data-provider="' + esc(name) + '"' + (test.step === "running" ? " disabled" : "") + ">Test</button>" +
      (name === "codex" ? '<button type="button" class="ghost" data-act="signin" data-provider="codex"' + (signin.step === "pending" ? " disabled" : "") + ">Sign in</button>" : "") +
      '<span class="settest" data-step="' + esc(test.step) + '" role="status">' + esc(line) + "</span></div>" + signInBox(signin) + "</div>";
  }

  // connectorsHtml(health, state). health is GET /api/health ({connectors: {claude: {...}, codex: {...}}}); state {test: {provider: {step, seconds, message}},
  // signin: signInState}. A row for every provider the answer holds, Claude first, then Codex; only the Codex row has Sign in.
  function connectorsHtml(health, state) {
    const connectors = isObj(health) && isObj(health.connectors) ? health.connectors : null;
    const head = '<section class="setgrp" data-group="connectors" aria-labelledby="set-connectors-h"><h3 id="set-connectors-h">' + GROUPS.connectors + "</h3>";
    if (connectors === null) return head + '<p class="setempty">The connectors are not loaded yet.</p></section>';
    return head + '<p class="setnote">The models Sutra talks to. Test makes one tiny call.</p>' +
      providerOrder(connectors).map(n => connectorRow(n, isObj(connectors[n]) ? connectors[n] : {}, state)).join("") + "</section>";
  }

  /* ---------------------------------------------------------------- flows (the caller hands in the api) */
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

  // Test: one POST. A 200 is a pass with its seconds; the error envelope's `message` (the server's user sentence) is the reason it did not.
  async function testConnector(api, provider) {
    const name = clean(provider);
    try {
      const answer = await api.post("/api/connectors/" + enc(name) + "/test");
      if (isObj(answer) && answer.ok === false) {
        const message = clean(answer.message) || clean(isObj(answer.error) ? answer.error.message : "") || "The test did not pass.";
        return {provider: name, ok: false, seconds: null, message, line: message};
      }
      const seconds = isObj(answer) && finite(answer.seconds) ? answer.seconds : null;
      return {provider: name, ok: true, seconds, message: "", line: secondsLine(seconds)};
    } catch (e) {
      const message = clean(e && e.message) || "The test could not run.";
      return {provider: name, ok: false, seconds: null, message, line: message};
    }
  }

  // Sign in (Codex only): POST starts it and answers the link and the one-time code, GET .../{id} is asked every `pollMs` until the state is
  // signed_in, failed or expired, DELETE stops it. `onState(state)` hears every step as a signInState. `done` settles with the last state.
  function signIn(api, options) {
    const o = isObj(options) ? options : {};
    const sleep = typeof o.sleep === "function" ? o.sleep : wait;
    const pollMs = finite(o.pollMs) && o.pollMs > 0 ? o.pollMs : POLL_MS;
    let state = NO_SIGNIN;
    let id = "";
    let cancelled = false;
    let removed = false;
    const emit = next => {
      state = next;
      if (typeof o.onState === "function") {
        try { o.onState(state); } catch (e) { /* a listener must not stop the sign-in */ }
      }
    };
    const stop = async () => {
      if (removed || id === "") return;
      removed = true;
      try { await api.del("/api/connectors/codex/sign-in/" + enc(id)); } catch (e) { /* it was over already */ }
    };
    const done = (async () => {
      let start;
      try {
        start = await api.post("/api/connectors/codex/sign-in");
      } catch (e) {
        emit(signInState(state, e));
        return state;
      }
      id = isObj(start) ? clean(start.id) : "";
      if (id === "") {
        emit(signInState(state, {message: "Sign in could not start."}));
        return state;
      }
      if (cancelled) { await stop(); return state; }
      emit(signInState(null, start));
      let waited = 0;
      while (state.step === "pending" && !cancelled) {
        await sleep(pollMs);
        waited += pollMs;
        if (cancelled) break;
        let answer;
        try {
          answer = await api.get("/api/connectors/codex/sign-in/" + enc(id));
        } catch (e) {
          if (!cancelled) emit(signInState(state, e));
          break;
        }
        if (cancelled) break;
        emit(signInState(state, answer));
        if (state.step === "pending" && state.expires_in > 0 && waited >= (state.expires_in + SIGN_IN_GRACE_S) * 1000) emit(signInState(state, {state: "expired"}));
      }
      return state;
    })();
    async function cancel() {
      if (cancelled || (state.step !== "pending" && id !== "")) return state;
      cancelled = true;
      await stop();
      emit(signInState(state, {state: "cancelled"}));
      return state;
    }
    return {done, cancel, state: () => state};
  }

  // The rows of the Connectors group stay current: one connector event is one GET /api/health. Other events do nothing.
  function watchHealth(api, onHealth, onError) {
    async function refetch() {
      try {
        const answer = await api.get(HEALTH_PATH);
        if (typeof onHealth === "function") onHealth(answer);
        return answer;
      } catch (e) {
        if (typeof onError === "function") onError(e);
        return null;
      }
    }
    return {refetch, onEvent: type => (HEALTH_EVENTS.includes(type) ? refetch() : undefined)};
  }

  /* ---------------------------------------------------------------- the Engine group's calls */
  // `dept` goes in the query by hand: these paths are not J2's, so the page's fetch wrapper never adds it. No scope is every team.
  const enginePath = scope => (clean(scope) === "" ? ENGINE_PATH : ENGINE_PATH + "?dept=" + enc(clean(scope)));
  const loadEngine = (api, scope) => api.get(enginePath(scope));

  // saveEngine(api, settings, scope, form) -> {ok, settings, unchanged, errors}. Nothing changed means no request.
  async function saveEngine(api, settings, scope, form) {
    const problems = formProblems(settings, form);
    if (Object.keys(problems).length) return {ok: false, settings, unchanged: false, errors: problems};
    const body = engineBody(settings, form);
    if (Object.keys(body.set).length === 0 && body.unset.length === 0) return {ok: true, settings, unchanged: true, errors: {}};
    try {
      const answer = await api.put(enginePath(scope), body);
      return {ok: true, settings: isObj(answer) ? answer : settings, unchanged: false, errors: {}};
    } catch (e) {
      return {ok: false, settings, unchanged: false, errors: engineErrors(e)};
    }
  }

  const SettingsView = {
    engineHtml, engineBody, engineErrors, formProblems, connectorsHtml, signInState, appearanceHtml,
    testConnector, signIn, watchHealth, loadEngine, saveEngine, enginePath, testLine, kindOf, parseValue,
    HEALTH_EVENTS, NOTE_LOCKED, NOTE_NEXT_RUN,
  };
  if (typeof module === "object" && module !== null && module.exports) module.exports = SettingsView;
  else root.SettingsView = SettingsView;
})(globalThis);
