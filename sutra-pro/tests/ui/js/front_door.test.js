"use strict";
// FrontDoor (sutra_app/ui/static/js/front_door.js): Home, the Attention page. What needs the owner (one card per question, approval and problem,
// answered in place), then what just finished.
// Run with: node --test tests/ui/js/front_door.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const FD = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/front_door.js"));

const tid = n => "tsk_" + String(n).padStart(12, "0");
const dept = (id, status, extra = {}) => Object.assign({id, name: id[0].toUpperCase() + id.slice(1), purpose: "Make " + id, node_status: status, session_id: "cs_" + id}, extra);
const question = (id, extra = {}) => Object.assign({message_id: id, session_id: "cs_web", kind: "question", dept_id: "web", dept_name: "Web",
  text: "@Requester Which colours?", options: [], asked_at: "2026-11-12T10:00:00Z", waiting_s: 300, stale: false}, extra);
const approval = (id, extra = {}) => Object.assign({message_id: id, session_id: "cs_org", kind: "approval", dept_id: null, dept_name: "",
  text: "Add a Design team?", options: ["Yes", "No"], asked_at: "2026-11-12T10:00:00Z", waiting_s: 30}, extra);
const head = (n, kind, extra = {}) => Object.assign({kind, tone: kind === "problem" ? "err" : "ok", task_id: tid(n), dept_id: "web", dept_name: "Web",
  title: "Menu page", text: "Web: row " + n, outcome: kind === "problem" ? "The model stopped" : "", since_s: 600, retry: kind === "problem"}, extra);

test("buckets: working, waiting and a problem are in progress; done states and finished work are done; the rest is idle, each team once", () => {
  const b = FD.buckets([dept("web", "running"), dept("ads", "waiting_on_you"), dept("ops", "fault"), dept("docs", "filed"), dept("hr", "idle"), dept("pr", "not_made"),
    dept("art", "idle")], [head(1, "finished", {dept_id: "art", dept_name: "Art", title: "Logo"})], {});
  assert.deepEqual(b.running.map(r => r.id), ["web", "ads", "ops"]);
  assert.deepEqual(b.done.map(r => [r.id, r.work || ""]), [["art", "Logo"], ["docs", ""]]);
  assert.deepEqual(b.idle.map(r => r.id), ["hr", "pr"]);
  assert.equal(b.running[1].words, "waiting on you");
});

test("buckets: a team at work again is only in progress, not also done under an older finished run", () => {
  const b = FD.buckets([dept("web", "waiting_on_you")], [head(1, "finished", {dept_id: "web", dept_name: "Web", title: "Site v1"})], {});
  assert.deepEqual(b.running.map(r => r.id), ["web"]);
  assert.deepEqual(b.done, []);
});

test("a question card: the team, how long it waited, the ask, a box and Send, and Open to the team page", () => {
  const html = FD.needCard(question(7), {elapsedMs: 0});
  assert.match(html, /class="fdcard fdask" data-msg="7" data-kind="question" data-dept="web"/);
  assert.match(html, /<span class="fdwho">Web<\/span>/);
  assert.match(html, /waiting 5 minutes/);
  assert.match(html, /<p class="fdq">Which colours\?<\/p>/);                       // the @tag is gone
  assert.match(html, /<textarea class="fdbox"[^>]*data-msg="7"/);
  assert.match(html, /data-act="fd-answer" data-msg="7"/);
  assert.match(html, /<a class="fdopen" href="\/d\/web\/">Open Web<\/a>/);
});

test("a question with options is answered by its buttons, and a long option reads as the choice and what it means", () => {
  const html = FD.needCard(question(8, {text: "Keep going or finish?\n   Option 1: Keep going: more parts\n   Option 2: Finish as it is",
    options: ["Keep going: more parts", "Finish as it is"]}), {});
  assert.match(html, /data-act="fd-option" data-msg="8" data-opt="1" data-text="Keep going: more parts"><b>Keep going<\/b><span class="fdoptwhy">more parts<\/span>/);
  assert.match(html, /data-opt="2" data-text="Finish as it is">Finish as it is<\/button>/);
  assert.doesNotMatch(html, /fd-answer/);
});

test("'send these: a; b; c' becomes three numbered questions under the lead-in", () => {
  const html = FD.needCard(question(9, {text: "@Requester Before we start.\nPlease send these: Your name; Your city; Your colours"}), {});
  assert.match(html, /<p class="fdsay">Before we start\.<\/p><p class="fdsay">Please send these:<\/p><ol class="fdqs"><li>Your name<\/li><li>Your city<\/li><li>Your colours<\/li><\/ol>/);
});

test("an approval card has Approve and Not now, carrying the card's own labels, and no team link", () => {
  const html = FD.needCard(approval(11), {});
  assert.match(html, /data-kind="approval"/);
  assert.match(html, /data-act="fd-approve" data-msg="11" data-text="Yes">Approve</);
  assert.match(html, /data-act="fd-decline" data-msg="11" data-text="No">Not now</);
  assert.doesNotMatch(html, /fdopen/);
});

test("a card being answered is disabled, and a refusal shows on its own card", () => {
  const html = FD.needCard(question(7), {busy: true, error: "This team is busy"});
  assert.match(html, /<p class="fderr" role="alert">This team is busy<\/p>/);
  assert.equal((html.match(/ disabled/g) || []).length, 2);
});

test("every word from the wire is escaped", () => {
  const html = FD.needCard(question(7, {dept_name: "<b>x</b>", text: "<img src=x onerror=1>?"}), {}) + FD.finishedHtml({departments: [dept("web", "filed", {name: "<i>W</i>"})]});
  assert.doesNotMatch(html, /<b>x|<img|<i>W/);
  assert.match(html, /&lt;img src=x onerror=1&gt;\?/);
});

test("a problem card: Try again, Open the team, Got it; a problem marked Got it is gone", () => {
  const html = FD.problemCard(head(3, "problem"));
  assert.match(html, /data-act="fd-retry" data-task="tsk_000000000003">Try again/);
  assert.match(html, /href="\/d\/web\/">Open Web/);
  assert.match(html, /data-act="fd-seen"/);
  const seen = {[tid(3)]: true};
  assert.doesNotMatch(FD.needsHtml({loaded: true, needs: [], heads: [head(3, "problem")], seen, departments: []}), /fdprob/);
});

test("Needs you: questions and approvals first, then problems; the count says how many", () => {
  const html = FD.needsHtml({loaded: true, needs: [question(7), approval(11)], heads: [head(3, "problem"), head(4, "quiet")], seen: {}, departments: []});
  assert.match(html, /Needs you <span class="fdcount">3<\/span>/);
  const order = [...html.matchAll(/data-kind="(\w+)"/g)].map(m => m[1]);
  assert.deepEqual(order, ["question", "approval", "problem"]);
  assert.equal(FD.summary({needs: [question(7)], heads: [], seen: {}}), "1 thing needs you");
});

test("nothing waits: one calm line; before the first read it says it is looking", () => {
  assert.match(FD.needsHtml({loaded: false}), /Looking/);
  const calm = FD.needsHtml({loaded: true, needs: [], heads: [], departments: [dept("web", "running")]});
  assert.match(calm, /<b>Nothing needs you right now\.<\/b>/);
  assert.match(FD.needsHtml({loaded: true, needs: [], heads: [], departments: []}), /Nothing needs you right now\./);
});

test("Just finished: finished work first, each row with Open to its studio; nothing finished means no section", () => {
  const state = {departments: [dept("web", "running"), dept("docs", "filed"), dept("hr", "idle")], heads: [head(3, "finished", {dept_id: "ads", dept_name: "Ads"})], seen: {}};
  const html = FD.finishedHtml(state);
  assert.match(html, /<h2 class="fdh" id="fd-done-h">Just finished<\/h2>/);
  assert.deepEqual([...html.matchAll(/href="([^"]+)" aria-label="Open (\w+)">Open<\/a>/g)].map(m => [m[1], m[2]]), [["/d/ads/", "Ads"], ["/d/docs/", "Docs"]]);
  assert.match(html, /<small class="fdst">Done · 10 minutes ago<\/small>/);
  assert.doesNotMatch(html, /Web|Hr/);
  assert.equal(FD.finishedHtml({departments: [dept("web", "running")], heads: []}), "");
});

test("Just finished shows five, then a button for the rest", () => {
  const many = Array.from({length: 7}, (_, i) => dept("t" + i, "filed"));
  const html = FD.finishedHtml({departments: many, heads: []});
  assert.equal((html.match(/st-filed/g) || []).length, 5);
  assert.match(html, /data-act="fd-more">2 more/);
  assert.equal((FD.finishedHtml({departments: many, heads: [], moreDone: true}).match(/st-filed/g) || []).length, 7);
});

test("after a send here: one calm line while Sutra works, a choice as a Needs you card in plain words, then Watch it being built", () => {
  const sent = [{id: 3, role: "user", text: "A flyer"}];
  const working = FD.latestHtml({show: true, messages: sent, status: "Setting up your project…"});
  assert.match(working, /class="fdlatest fdwork"/);
  assert.match(working, /Setting up your project…/);
  assert.doesNotMatch(working, /fd-conversation|Reading the org chart|team/i);
  const asking = sent.concat([{id: 6, role: "agent", text: "", card: {type: "choice", question: "Which team fits best?",
    options: [{id: "web", label: "Web"}, {id: "none", label: "A new team"}]}}]);
  const card = FD.latestHtml({show: true, messages: asking});
  assert.match(card, /class="fdcard fdask fdchoice" data-msg="6"/);
  assert.match(card, /Asha needs one answer/);
  assert.match(card, /<p class="fdq">Is this for one of your projects, or something new\?<\/p>/);
  assert.match(card, /data-act="fd-choose" data-msg="6" data-option="none" data-text="A new team">Something new<\/button>/);   // the server still gets its own label
  assert.doesNotMatch(card, /fd-conversation/);
  const done = sent.concat([{id: 5, role: "agent", text: "", card: {type: "task", dept_id: "web", dept_name: "Web", title: "A flyer"}}]);
  assert.equal(FD.landing({messages: done}), "/d/web/");
  assert.equal(FD.landing({messages: asking}), "");
  const ready = FD.latestHtml({show: true, messages: done, going: true});
  assert.match(ready, /<a class="fdbtn fdyes fdwatch" href="\/d\/web\/">Watch it being built<\/a>/);
  assert.match(ready, /Taking you there/);
});

test("the faces row names the five people, from a fixed table", () => {
  const html = FD.facesHtml();
  assert.equal((html.match(/<svg class="fdface"/g) || []).length, 5);
  assert.match(html, /Asha, Mira, Kabir, Dev and Nora are ready\./);
});

test("a team's question says who asks in plain words: Asha needs one answer (or N answers)", () => {
  assert.match(FD.needCard(question(7), {}), /<b class="fdasker">Asha needs one answer<\/b>/);
  const three = FD.needCard(question(9, {text: "Before we start.\nPlease send these: Your name; Your city; Your colours"}), {});
  assert.match(three, /Asha needs 3 answers/);
  assert.match(FD.needCard(approval(11), {}), /Asha needs your OK/);
});

test("the home box (D257): an empty holder for the Budget chip beside Go, the chip script before home.js, no credits field", () => {
  const fs = require("node:fs");
  const html = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/pages/home.html"), "utf8");
  const box = html.slice(html.indexOf('<div class="fdcompose">'), html.indexOf('id="fdsend"'));
  assert.match(box, /<span id="fdbudget" style="margin-left:auto"><\/span>/);
  assert.doesNotMatch(box, /work credits|type="number"/);
  assert.ok(html.indexOf("/ui/js/budget_chip.js") > 0 && html.indexOf("/ui/js/budget_chip.js") < html.indexOf("/ui/js/home.js"));
  assert.equal(FD.budgetOf, undefined);
  const js = fs.readFileSync(path.resolve(__dirname, "../../../sutra_app/ui/static/js/home.js"), "utf8");
  assert.match(js, /choice \? \{text: body, choice\} : \{text: body, \.\.\.budget\}/);      // a budget never rides with a card answer
  assert.match(js, /send\(body, null, \{plan: true, usd_budget: usd\}\)/);
});

test("stopOf (D254): Stop while the box is empty, the card shows the work this send started, and its team has a live task", () => {
  const sent = [{id: 900, role: "user", text: "A cafe site"}, {id: 901, role: "agent", text: "", card: {type: "task", dept_id: "web", dept_name: "Web", title: "A cafe site"}}];
  const base = {show: true, messages: sent, answers: {}, box: "", departments: [dept("web", "running", {live_task_id: tid(7)}), dept("ads", "idle", {live_task_id: tid(8)})]};
  assert.deepEqual(FD.stopOf(base), {show: true, taskId: tid(7)});
  const no = {show: false, taskId: ""};
  assert.deepEqual(FD.stopOf({...base, box: "more please"}), no);                                       // typing turns it back into Go
  assert.deepEqual(FD.stopOf({...base, box: "   "}), {show: true, taskId: tid(7)});
  assert.deepEqual(FD.stopOf({...base, show: false}), no);                                              // nothing sent from this box
  assert.deepEqual(FD.stopOf({...base, departments: [dept("web", "filed", {live_task_id: null})]}), no);  // the run ended
  assert.deepEqual(FD.stopOf({...base, departments: [dept("web", "running", {live_task_id: "../x"})]}), no);
  assert.deepEqual(FD.stopOf({...base, messages: sent.slice(0, 1)}), no);                                // no team has the work yet
  const choice = {id: 902, role: "agent", text: "", card: {type: "choice", question: "Which team?", options: [{id: "web", label: "Web"}]}};
  assert.deepEqual(FD.stopOf({...base, messages: [...sent, choice]}), no);                              // the card is a question, not the work
  assert.deepEqual(FD.stopOf(null), no);
});

test("raise input (D257): a dollar question's card takes a typed amount; the option tail is stripped; no credits; every $ says API price", () => {
  const text = "@Requester The site isn't finished yet.\nThis run has used $20.40 of $20 (API price). Add $10? So far: $20 approved. 3 calls estimated: Codex reports no price." +
    "\n   Option 1: Add $10 and keep going: you get more of the missing parts built. Or type your own amount [adds $10]\n   Option 2: Finish as it is: you get the site";
  const html = FD.needCard(question(12, {text}), {});
  assert.match(html, /<input class="bchipraisein"[^>]*value="\$10"/);
  assert.match(html, /data-act="fd-raise" data-msg="12">Add and keep going/);
  assert.match(html, /3 calls estimated: Codex reports no price\./);
  assert.doesNotMatch(html, /\[adds/);
  assert.doesNotMatch(html, /credit/i);
  const shown = html.replace(/<[^>]+>/g, " ");
  for (const m of shown.matchAll(/\$\d[\d,.]*/g)) {
    const near = shown.slice(Math.max(0, m.index - 80), m.index + 120);
    assert.match(near, /API price|estimated/, `${m[0]} has API price near it`);
  }
  assert.match(FD.needCard(question(13, {options: ["Add $10 and keep going [adds $10]", "Finish"]}), {}), /data-text="Add \$10 and keep going \[adds \$10\]"><b>Add \$10 and keep going<\/b>|>Add \$10 and keep going</);
  assert.doesNotMatch(FD.needCard(question(7), {}), /bchipraise/);                    // an ordinary question has no raise input
});
