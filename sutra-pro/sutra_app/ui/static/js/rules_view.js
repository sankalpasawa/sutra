/* rules_view.js - a team's standing rules and practice pick, for the Details tab of a team (GAP2 rules-notes; the old function templates' floors).

   Strings in, strings out, plus the few small flows that talk to the server through an `api` the caller hands in (SutraCtx.api, or a fake in a test):
   this file touches no DOM and no timer, so `node --test` runs all of it. Every word from the wire goes through esc().

     rulesHtml(state) -> html           the block: what standing rules are, the owner's rules (Always, Ask me first, Never) each with Remove, the add form,
                                        the practice picks (None, Money movement, Product build) with the lines the chosen one adds for each function.
                                        state = {dept, data, packs, error, busy, saved, draft}
                                          data    the answer of GET /api/departments/{id}/rules, or null while it loads
                                          packs   the answer of GET /api/packs
                                          error   one sentence for the block ("" for none)
                                          draft   what was typed and refused, kept beside the sentence {tag, text}
     addBody(data, tag, text) / removeBody(data, index) / packBody(id)    the PUT body: the whole list with one line more or less, or just the pick
     errorWords(error) -> sentence      the server's own words for a refusal (a key, a repeat, a full list, "cannot say it more loosely"), else a fallback
     loadRules(api, dept) -> Promise<{data, packs}>   GET /api/departments/{id}/rules and GET /api/packs
     saveRules(api, dept, body) -> Promise<{ok, data, error}>          PUT /api/departments/{id}/rules

   A rule is guidance the team reads in front of every task it is given: it is not a lock, and the block says so. A pick only ADDS lines (it never loosens
   a rule); the owner's rule that says a pick's line more loosely is refused by the server in a sentence this view shows as it is.
   A classic script with ONE global, RulesView; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const enc = encodeURIComponent;

  const TAGS = Object.freeze([["always", "Always"], ["ask", "Ask me first"], ["never", "Never"]]);
  const TAG_WORD = Object.freeze(Object.fromEntries(TAGS));
  const FUNCTION_WORD = Object.freeze({identity: "Identity", adaptation: "Adaptation", priority: "Priority", coordination: "Coordination", audit: "Audit"});
  const FALLBACK = "The rules could not be saved. Try again.";
  const INTRO = "Rules you give this team once. Every task of the team starts with them in front, so you do not have to repeat them. They are guidance " +
    "the team reads, not a lock.";
  const PRACTICE_INTRO = "A starter pick adds lines for the five functions. It only adds or tightens; it never loosens a rule.";

  const path = dept => "/api/departments/" + enc(clean(dept)) + "/rules";

  /* ---------------------------------------------------------------- bodies and words */
  const rulesOf = data => (isObj(data) && Array.isArray(data.rules) ? data.rules.filter(r => isObj(r) && hasOwn(TAG_WORD, r.tag) && clean(r.text) !== "") : []);
  const plain = list => list.map(r => ({tag: r.tag, text: clean(r.text)}));

  function addBody(data, tag, text) {
    return {rules: plain(rulesOf(data)).concat([{tag: hasOwn(TAG_WORD, tag) ? tag : "always", text: clean(text)}])};
  }

  function removeBody(data, index) {
    return {rules: plain(rulesOf(data)).filter((_, i) => i !== index)};
  }

  const packBody = id => ({pack: clean(id) === "" ? null : clean(id)});

  function errorWords(error) {
    const details = isObj(error) && isObj(error.details) ? error.details : {};
    const first = Array.isArray(details.violations) ? details.violations.find(v => isObj(v) && clean(v.message) !== "") : null;
    if (first) return clean(first.message);
    if (isObj(error) && error.status === 401) return "This page was opened without its access token. Reload it from the app.";
    return clean(isObj(error) ? error.message : "") || FALLBACK;
  }

  /* ---------------------------------------------------------------- drawing */
  function ruleRow(r, i, busy) {
    return '<li class="rule" data-rule="' + i + '"><span class="rtag" data-tag="' + esc(r.tag) + '">' + esc(TAG_WORD[r.tag]) + "</span> " + esc(clean(r.text)) +
      ' <button type="button" class="linkbtn" data-act="rules-remove" data-index="' + i + '"' + (busy ? " disabled" : "") + ">Remove</button></li>";
  }

  function addForm(max, draft, busy) {
    const d = isObj(draft) ? draft : {};
    const picked = hasOwn(TAG_WORD, d.tag) ? d.tag : "always";
    return '<div class="ruleadd"><select data-rules-tag aria-label="What kind of rule">' +
      TAGS.map(t => '<option value="' + t[0] + '"' + (t[0] === picked ? " selected" : "") + ">" + esc(t[1]) + "</option>").join("") + "</select>" +
      '<input type="text" data-rules-text maxlength="' + max + '" aria-label="The rule" placeholder="For example: Never email a client without asking" value="' + esc(clean(d.text)) + '">' +
      '<button type="button" class="ghost" data-act="rules-add"' + (busy ? " disabled" : "") + ">Add</button></div>";
  }

  function packLines(pack) {
    const lines = Array.isArray(pack.lines) ? pack.lines.filter(l => isObj(l) && hasOwn(FUNCTION_WORD, l.function) && clean(l.text) !== "") : [];
    return '<ul class="fnlist packlines">' + lines.map(l => "<li><b>" + esc(FUNCTION_WORD[l.function]) + "</b>, " + esc(hasOwn(TAG_WORD, l.tag) ? TAG_WORD[l.tag].toLowerCase() : "") +
      ": " + esc(clean(l.text)) + "</li>").join("") + "</ul>";
  }

  function practiceHtml(data, packs, busy) {
    const picked = isObj(data) && isObj(data.pack) ? clean(data.pack.id) : "";
    const list = (Array.isArray(packs) ? packs : []).filter(p => isObj(p) && clean(p.id) !== "" && clean(p.name) !== "");
    if (list.length === 0) return "";
    const button = (id, label, on) => '<button type="button" class="ghost" data-act="rules-pack" data-pack="' + esc(id) + '" aria-pressed="' + (on ? "true" : "false") + '"' +
      (busy ? " disabled" : "") + ">" + esc(label) + "</button>";
    const chosen = list.find(p => clean(p.id) === picked);
    return '<h4>Practice</h4><p class="adsmall">' + esc(PRACTICE_INTRO) + '</p><div class="packpick" role="group" aria-label="Practice">' +
      button("", "None", picked === "") + list.map(p => button(clean(p.id), clean(p.name), clean(p.id) === picked)).join("") + "</div>" +
      (chosen ? '<p class="adsmall packuse">' + esc(clean(chosen.use_case)) + "</p>" + packLines(chosen) : "");
  }

  function rulesHtml(state) {
    const s = isObj(state) ? state : {};
    const data = isObj(s.data) ? s.data : null;
    const open = '<section class="adsec tmrules" data-sec="rules" data-dept="' + esc(clean(s.dept)) + '"><h4>Standing rules</h4><p class="adsmall">' + esc(INTRO) + "</p>";
    const err = clean(s.error) ? '<p class="seterr setgen" role="alert">' + esc(clean(s.error)) + "</p>" : "";
    if (data === null) return open + (err || '<p class="empty">Loading…</p>') + "</section>";
    const rules = rulesOf(data);
    const max = Number.isInteger(data.max_rules) ? data.max_rules : 20;
    const chars = Number.isInteger(data.max_chars) ? data.max_chars : 300;
    const busy = s.busy === true;
    const list = rules.length ? '<ul class="rulelist fnlist">' + rules.map((r, i) => ruleRow(r, i, busy)).join("") + "</ul>" : '<p class="empty">No rules yet.</p>';
    return open + err + list + '<p class="adsmall rulecount">' + rules.length + " of " + max + " rules</p>" + addForm(chars, s.draft, busy) +
      practiceHtml(data, s.packs, busy) + '<p class="setstatus" role="status">' + esc(clean(s.saved)) + "</p></section>";
  }

  /* ---------------------------------------------------------------- flows */
  async function loadRules(api, dept) {
    const [data, packs] = await Promise.all([api.get(path(dept)), api.get("/api/packs")]);
    return {data, packs: Array.isArray(packs) ? packs : []};
  }

  async function saveRules(api, dept, body) {
    try {
      const data = await api.put(path(dept), body);
      return {ok: true, data: isObj(data) ? data : null, error: ""};
    } catch (e) {
      return {ok: false, data: null, error: errorWords(e)};
    }
  }

  const RulesView = {rulesHtml, addBody, removeBody, packBody, errorWords, loadRules, saveRules, TAGS, INTRO};
  if (typeof module === "object" && module !== null && module.exports) module.exports = RulesView;
  else root.RulesView = RulesView;
})(globalThis);
