"use strict";
// RulesView (sutra_app/ui/static/js/rules_view.js): a team's standing rules and practice pick on its Details tab. Strings in, strings out, and the flows over
// a fake api. GAP2 rules-notes. Run with: node --test tests/ui/js/rules_view.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const RulesView = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/rules_view.js"));
const {rulesHtml, addBody, removeBody, packBody, errorWords, loadRules, saveRules} = RulesView;

const PACKS = [
  {id: "money-movement", name: "Money movement", use_case: "A team that moves or posts money.", fits: "moves or posts money", lines: [
    {function: "identity", tag: "ask", text: "A payment above the owner's line is put to the owner."}, {function: "audit", tag: "always", text: "Reconciles every payment each morning."}]},
  {id: "product-build", name: "Product build", use_case: "A team that builds and ships a product to users.", fits: "builds and ships a product to users", lines: [
    {function: "coordination", tag: "always", text: "A shipped slice has a named person to hear back."}]},
];
const DATA = {dept_id: "web", rules: [{tag: "never", text: "Never email a client without asking."}, {tag: "always", text: "Use plain words."}], pack: null, declined: [], max_rules: 20, max_chars: 300};

test("the block says what standing rules are and that they are guidance, not a lock", () => {
  const html = rulesHtml({dept: "web", data: DATA, packs: PACKS});
  assert.match(html, /<h4>Standing rules<\/h4>/);
  assert.match(html, /Every task of the team starts with them in front, so you do not have to repeat them\. They are guidance the team reads, not a lock\./);
  assert.match(html, /data-dept="web"/);
});

test("each rule shows its kind in the owner's words and a Remove; the count and the add form follow", () => {
  const html = rulesHtml({dept: "web", data: DATA, packs: PACKS});
  assert.match(html, /<li class="rule" data-rule="0"><span class="rtag" data-tag="never">Never<\/span> Never email a client without asking\./);
  assert.match(html, /<span class="rtag" data-tag="always">Always<\/span> Use plain words\./);
  assert.match(html, /data-act="rules-remove" data-index="1"/);
  assert.match(html, /2 of 20 rules/);
  for (const [value, label] of [["always", "Always"], ["ask", "Ask me first"], ["never", "Never"]]) assert.ok(html.includes('<option value="' + value + '"'), label);
  assert.match(html, /data-act="rules-add"/);
  assert.match(html, /maxlength="300"/);
});

test("no rule says so, loading says so, a failed load shows the sentence", () => {
  assert.match(rulesHtml({dept: "web", data: {rules: [], pack: null, max_rules: 20, max_chars: 300}, packs: []}), /No rules yet\./);
  assert.match(rulesHtml({dept: "web", data: null}), /Loading/);
  assert.match(rulesHtml({dept: "web", data: null, error: "That team was not found."}), /role="alert">That team was not found\./);
  assert.doesNotMatch(rulesHtml({dept: "web", data: null}), /ruleadd/);
});

test("the practice picks: None and each pack as a pressed-state button; the chosen one lists its lines per function", () => {
  const none = rulesHtml({dept: "web", data: DATA, packs: PACKS});
  assert.match(none, /data-act="rules-pack" data-pack="" aria-pressed="true"/);
  assert.match(none, /data-pack="money-movement" aria-pressed="false"/);
  assert.doesNotMatch(none, /packlines/);
  const picked = rulesHtml({dept: "web", data: Object.assign({}, DATA, {pack: PACKS[0]}), packs: PACKS});
  assert.match(picked, /data-pack="" aria-pressed="false"/);
  assert.match(picked, /data-pack="money-movement" aria-pressed="true"/);
  assert.match(picked, /A team that moves or posts money\./);
  assert.match(picked, /<li><b>Identity<\/b>, ask me first: A payment above the owner&#39;s line is put to the owner\.<\/li>/);
  assert.match(picked, /<li><b>Audit<\/b>, always: Reconciles every payment each morning\.<\/li>/);
  assert.doesNotMatch(picked, /named person to hear back/);
  assert.match(none, /It only adds or tightens; it never loosens a rule\./);
  assert.doesNotMatch(rulesHtml({dept: "web", data: DATA, packs: []}), /Practice/);
});

test("every word from the wire is escaped", () => {
  const evil = '<img src=x onerror=alert(1)>"\'&';
  const data = {rules: [{tag: "never", text: evil}], pack: Object.assign({}, PACKS[0], {name: evil, use_case: evil, lines: [{function: "audit", tag: "never", text: evil}]}),
    max_rules: 20, max_chars: 300};
  const html = rulesHtml({dept: evil, data, packs: [Object.assign({}, PACKS[0], {name: evil, use_case: evil, lines: data.pack.lines})], error: evil, saved: evil, draft: {tag: "ask", text: evil}});
  assert.doesNotMatch(html, /<img/);
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;&quot;&#39;&amp;"));
  assert.doesNotMatch(rulesHtml({dept: "web", data: DATA, packs: PACKS, draft: {tag: "ask", text: evil}}), /<img/);
});

test("a refusal keeps what was typed beside the sentence; busy disables the buttons", () => {
  const html = rulesHtml({dept: "web", data: DATA, packs: PACKS, error: "The team already has this rule (rule 1).", draft: {tag: "ask", text: "Ask before a purchase."}});
  assert.match(html, /role="alert">The team already has this rule \(rule 1\)\./);
  assert.match(html, /<option value="ask" selected>Ask me first<\/option>/);
  assert.match(html, /data-rules-text[^>]*value="Ask before a purchase\."/);
  const busy = rulesHtml({dept: "web", data: DATA, packs: PACKS, busy: true});
  assert.match(busy, /data-act="rules-add" disabled/);
  assert.match(busy, /data-act="rules-remove" data-index="0" disabled/);
  assert.match(busy, /data-act="rules-pack" data-pack="" aria-pressed="true" disabled/);
});

test("bodies: the whole list with one line more or less, or only the pick; nothing the page cannot name is sent", () => {
  assert.deepEqual(addBody(DATA, "ask", "  Ask  before a purchase. "), {rules: [{tag: "never", text: "Never email a client without asking."},
    {tag: "always", text: "Use plain words."}, {tag: "ask", text: "Ask before a purchase."}]});
  assert.deepEqual(addBody(DATA, "bogus", "x").rules[2], {tag: "always", text: "x"});
  assert.deepEqual(removeBody(DATA, 0), {rules: [{tag: "always", text: "Use plain words."}]});
  assert.deepEqual(removeBody(DATA, 7).rules.length, 2);
  assert.deepEqual(addBody(null, "never", "Never lie."), {rules: [{tag: "never", text: "Never lie."}]});
  assert.deepEqual(packBody("money-movement"), {pack: "money-movement"});
  assert.deepEqual(packBody(""), {pack: null});
  assert.deepEqual(packBody(undefined), {pack: null});
});

test("an edit of the list says which list it was made from, so another window's save is not overwritten", () => {
  const read = {...DATA, rev: "0123456789abcdef"};
  assert.deepEqual(addBody(read, "ask", "Ask before a purchase.").rev, "0123456789abcdef");
  assert.deepEqual(removeBody(read, 0), {rules: [{tag: "always", text: "Use plain words."}], rev: "0123456789abcdef"});
  assert.deepEqual(packBody("money-movement"), {pack: "money-movement"});                         // a pick alone has no list to protect
  assert.equal("rev" in addBody(DATA, "ask", "x"), false);                                        // an answer without one (an older server) sends none
  assert.equal("rev" in addBody({...DATA, rev: ""}, "ask", "x") || "rev" in addBody({...DATA, rev: 5}, "ask", "x"), false);
  assert.equal("rev" in addBody(null, "never", "Never lie."), false);
});

test("errorWords takes the server's sentence for a refusal and a plain one otherwise", () => {
  const refused = {status: 422, message: "Some rules could not be kept", details: {violations: [{path: "rules.1.text", code: "refused", message: "That line is empty."}]}};
  assert.equal(errorWords(refused), "That line is empty.");
  assert.equal(errorWords({status: 404, message: "that team was not found", details: {}}), "that team was not found");
  assert.match(errorWords({status: 401}), /without its access token/);
  assert.equal(errorWords(undefined), "The rules could not be saved. Try again.");
});

function fakeApi(script = {}) {
  const calls = [];
  return {calls,
    get: async path => { calls.push(["get", path]); const r = script["get " + path]; if (r instanceof Error) throw r; return r === undefined ? (path === "/api/packs" ? PACKS : DATA) : r; },
    put: async (path, body) => { calls.push(["put", path, body]); const r = script["put " + path]; if (r instanceof Error) throw r; return r === undefined ? DATA : r; }};
}

test("loadRules reads the team's rules and the packs; the team id is encoded", async () => {
  const api = fakeApi();
  assert.deepEqual(await loadRules(api, "web"), {data: DATA, packs: PACKS});
  assert.deepEqual(api.calls.map(c => c[1]).sort(), ["/api/departments/web/rules", "/api/packs"]);
  const odd = fakeApi({"get /api/packs": {not: "a list"}});
  assert.deepEqual((await loadRules(odd, "a/b")).packs, []);
  assert.ok(odd.calls.some(c => c[1] === "/api/departments/a%2Fb/rules"));
});

test("saveRules puts the body and gives the answer, or the server's sentence", async () => {
  const api = fakeApi();
  assert.deepEqual(await saveRules(api, "web", {pack: "money-movement"}), {ok: true, data: DATA, error: ""});
  assert.deepEqual(api.calls[0], ["put", "/api/departments/web/rules", {pack: "money-movement"}]);
  const refusal = Object.assign(new Error("x"), {status: 422, details: {violations: [{message: "A rule cannot say it more loosely."}]}});
  assert.deepEqual(await saveRules(fakeApi({"put /api/departments/web/rules": refusal}), "web", {rules: []}), {ok: false, data: null, error: "A rule cannot say it more loosely."});
});

test("a save from a list another window changed is refused, and the list as it is now comes back to be shown", async () => {
  const now = {...DATA, rules: [{tag: "always", text: "Always quote prices in INR"}], rev: "feedfacefeedface"};
  const stale = Object.assign(new Error("The rules changed"), {status: 422, details: {violations: [{path: "rev", code: "stale_rules", message: "The rules were changed in another window. They are shown again: make your change once more."}], current: now}});
  const out = await saveRules(fakeApi({"put /api/departments/web/rules": stale}), "web", {rules: [], rev: "0123456789abcdef"});
  assert.deepEqual(out, {ok: false, data: now, error: "The rules were changed in another window. They are shown again: make your change once more."});
  const odd = Object.assign(new Error("x"), {status: 422, details: {violations: [{message: "No."}], current: "not a list"}});
  assert.equal((await saveRules(fakeApi({"put /api/departments/web/rules": odd}), "web", {rules: []})).data, null);
});
