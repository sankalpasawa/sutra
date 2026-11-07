"use strict";
// ChatView (sutra_app/ui/static/js/chat_view.js): a node's transcript in J2's bubble look, the chat cards (text, task, chart_change, approval, choice,
// needs_you, done and the atom card of a function node's log), who wrote a line, whether the message box shows, and the one door a message text goes through.
// docs/design/ui.md sections 6.5, 6.6, 7 and 10; S2-models-09, S4-fnodes-06, S4-fnodes-12.
// Run with: node --test tests/ui/js/chat_view.test.js
//
// The markup is parsed by a small XML reader below, so "well formed" is proved and the tests can ask for elements instead of matching text.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.resolve(__dirname, "../../../sutra_app/ui/static/js");
const FILE = path.join(JS, "chat_view.js");
const ChatView = require(FILE);
const {transcript, card, composerState, safeText, whoLabel, parseAsk, stripTag, providerLabel} = ChatView;
const fixture = name => JSON.parse(fs.readFileSync(path.resolve(__dirname, "../fixtures", name), "utf8"));
const ORG = fixture("chat-org.json");
const DEPT = fixture("chat-dept.json");
const DIVISION = fixture("chat-division.json");
const IDENTITY_LOG = fixture("chat-identity.json");

const DOT = " \u00b7 ";
const clone = value => JSON.parse(JSON.stringify(value));

/* ---------------------------------------------------------------- a small XML reader */
const ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"};
function decode(text, where) {
  assert.equal(/&(?!(?:amp|lt|gt|quot|#39);)/.test(text), false, `a stray & in ${where}: ${text.slice(0, 80)}`);
  return text.replace(/&(?:amp|lt|gt|quot|#39);/g, m => ENTITY[m]);
}
function parse(markup) {
  const root = {tag: "#root", attrs: {}, children: [], text: "", content: []};
  const stack = [root];
  const TOKEN = /<(\/?)([A-Za-z][\w:-]*)((?:\s+[\w:.-]+="[^"<]*")*)\s*(\/?)>|<[^>]*>|[^<]+/y;
  let pos = 0;
  while (pos < markup.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(markup);
    assert.ok(m && m.index === pos, `not well formed at ${pos}: ${markup.slice(pos, pos + 80)}`);
    pos = TOKEN.lastIndex;
    const top = stack[stack.length - 1];
    if (m[2] === undefined) {
      assert.equal(m[0].startsWith("<"), false, `a malformed tag: ${m[0].slice(0, 80)}`);
      const piece = decode(m[0], "text");
      top.text += piece;
      top.content.push(piece);
      continue;
    }
    if (m[1] === "/") {
      assert.equal(top.tag, m[2], `</${m[2]}> closes <${top.tag}>`);
      stack.pop();
      continue;
    }
    const attrs = {};
    for (const a of m[3].matchAll(/([\w:.-]+)="([^"<]*)"/g)) {
      assert.equal(a[1] in attrs, false, `attribute ${a[1]} twice on <${m[2]}>`);
      attrs[a[1]] = decode(a[2], "attribute " + a[1]);
    }
    const node = {tag: m[2], attrs, children: [], text: "", content: []};
    top.children.push(node);
    top.content.push(node);
    if (m[4] !== "/") stack.push(node);
  }
  assert.equal(stack.length, 1, "unclosed tags: " + stack.slice(1).map(n => n.tag).join(" "));
  return root;
}
const walk = (node, fn) => { fn(node); node.children.forEach(c => walk(c, fn)); };
function selectOne(node, selector) {          // tag.class.class[attr][attr=value], one compound
  const m = /^([a-zA-Z0-9]*)((?:\.[\w-]+)*)((?:\[[\w:.-]+(?:=[^\]]*)?\])*)$/.exec(selector);
  assert.ok(m, "selector " + selector);
  const classes = m[2].split(".").filter(Boolean);
  const attrs = [...m[3].matchAll(/\[([\w:.-]+)(?:=([^\]]*))?\]/g)].map(a => [a[1], a[2]]);
  const out = [];
  walk(node, n => {
    if (n === node || n.tag === "#root") return;
    if (m[1] !== "" && n.tag !== m[1]) return;
    const have = (n.attrs.class || "").split(/\s+/);
    if (!classes.every(c => have.includes(c))) return;
    if (!attrs.every(([k, v]) => (v === undefined ? k in n.attrs : n.attrs[k] === v))) return;
    out.push(n);
  });
  return out;
}
function select(node, selector) {             // compounds separated by spaces are descendants
  let found = [node];
  selector.trim().split(/\s+/).forEach(part => {
    const next = [];
    found.forEach(f => selectOne(f, part).forEach(n => { if (!next.includes(n)) next.push(n); }));
    found = next;
  });
  return found;
}
const one = (node, selector) => { const found = select(node, selector); assert.equal(found.length, 1, `${selector}: ${found.length} found`); return found[0]; };
const textOf = node => node.content.map(c => (typeof c === "string" ? c : (c.tag === "br" ? "\n" : textOf(c)))).join("");
const dom = html => parse(html);
const tags = html => [...html.matchAll(/<\/?([A-Za-z][\w:-]*)/g)].map(m => m[1].toLowerCase());

/* ---------------------------------------------------------------- data */
const msg = (over = {}) => ({id: 1, session_id: "cs_x", role: "agent", who: "identity", kind: "text", text: "Hello", card: null, pause: null, answered_by: null, task_id: null, state: "ok", at: "2026-11-04T10:00:00Z", ...over});
const writable = (over = {}) => ({id: "cs_x", node_id: "web", kind: "department", title: "Web", writable: true, status: "active", connector: "claude", note: "", ...over});
const logOf = (over = {}) => ({id: "cs_log", node_id: "web.adaptation", kind: "function", title: "Adaptation", writable: false, status: "active", connector: "claude", note: "", ...over});
const ASK = "@Requester Should the menu show prices?\n   Option 1: Yes, show the prices\n   Option 2: No, names only";

/* ================================================================ safeText */
test("safeText escapes every character that could open a tag or an attribute", () => {
  assert.equal(safeText(`<script>alert("x")</script> & 'q'`), "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#39;q&#39;");
  assert.equal(safeText("<img src=x onerror=alert(1)>").includes("<img"), false);
  assert.equal(safeText('"><svg onload=1>').includes("<svg"), false);
});

test("safeText makes **bold**, `code` and line breaks and nothing else", () => {
  assert.equal(safeText("a **bold** word"), "a <b>bold</b> word");
  assert.equal(safeText("run `ls -la` now"), "run <code>ls -la</code> now");
  assert.equal(safeText("one\ntwo\r\nthree\rfour"), "one<br/>two<br/>three<br/>four");
  assert.equal(safeText("**a** and **b**"), "<b>a</b> and <b>b</b>");
  assert.equal(safeText("**bold** then `code`"), "<b>bold</b> then <code>code</code>");
});

test("safeText never lets a mark reach across a code span or a line", () => {
  assert.equal(safeText("`x**` and **y**"), "<code>x**</code> and <b>y</b>");
  assert.equal(safeText("**a\nb**"), "**a<br/>b**");
  assert.equal(safeText("**open only"), "**open only");
  assert.equal(safeText("a ` b"), "a ` b");
  assert.equal(safeText("`**not bold**`"), "<code>**not bold**</code>");
  assert.equal(safeText("**bold with `code` inside**"), "**bold with <code>code</code> inside**");
  assert.equal(safeText("****"), "****");
});

test("safeText makes no link and no image", () => {
  const html = safeText("see https://example.com or <a href=\"https://evil.example\">here</a> ![x](y.png) [t](https://u.example)");
  assert.deepEqual(tags(html), []);
  assert.equal(html.includes("<a "), false);
});

test("safeText can only write b, code and br, whatever it is given", () => {
  const hostile = ["<b onclick=1>x</b>", "</code><script>", "`<b>`", "**<i>**", "&lt;script&gt;", "<<script>script>", "\u0000<a>", "<!-- x -->", "<![CDATA[x]]>", "```", "** `a` **`b`**"];
  hostile.forEach(input => {
    const html = safeText(input);
    tags(html).forEach(t => assert.ok(["b", "code", "br"].includes(t), `${t} from ${JSON.stringify(input)}`));
    parse(html);
  });
});

test("safeText takes any value: numbers are digits, everything else is empty", () => {
  assert.equal(safeText(null), "");
  assert.equal(safeText(undefined), "");
  assert.equal(safeText(42), "42");
  assert.equal(safeText({}), "");
  assert.equal(safeText([1]), "");
  assert.equal(safeText(""), "");
});

/* ================================================================ whoLabel */
test("whoLabel: every label of the design", () => {
  const table = {user: "You", sutra: "Sutra", identity: "Client Lead (Identity)", adaptation: "Strategist (Adaptation)", priority: "Prioritiser (Priority)",
    coordination: "Scheduler (Coordination)", audit: "Quality Reviewer (Audit)", validator: "Validator", system: "System"};
  Object.entries(table).forEach(([who, label]) => assert.equal(whoLabel(who), label, who));
  assert.equal(whoLabel("W-3"), "W-3 Builder");
  assert.equal(whoLabel("W-12"), "W-12 Builder");
});

test("whoLabel: the department's name goes in front of an Identity, and of nobody else", () => {
  assert.equal(whoLabel("identity", {deptName: "Web"}), "Web" + DOT + "Client Lead (Identity)");
  assert.equal(whoLabel("identity", {deptName: "  "}), "Client Lead (Identity)");
  assert.equal(whoLabel("identity", {}), "Client Lead (Identity)");
  assert.equal(whoLabel("identity", null), "Client Lead (Identity)");
  ["user", "sutra", "adaptation", "priority", "coordination", "audit", "validator", "system", "W-3"].forEach(who => {
    assert.equal(whoLabel(who, {deptName: "Web"}), whoLabel(who), who);
  });
});

test("whoLabel: an author the table does not know is shown as it came, without 'team:'", () => {
  assert.equal(whoLabel("team:designer"), "designer");
  assert.equal(whoLabel("Team:Writer"), "Writer");
  assert.equal(whoLabel("somebody"), "somebody");
  assert.equal(whoLabel("W-x"), "W-x");
  assert.equal(whoLabel(""), "");
  assert.equal(whoLabel(undefined), "");
  assert.equal(whoLabel("  Identity  "), "Identity");
});

test("stripTag drops the leading address of one agent to another and nothing else", () => {
  assert.equal(stripTag("@Requester Thanks. I have what I need."), "Thanks. I have what I need.");
  assert.equal(stripTag("@Adaptation, here is the charter"), "here is the charter");
  assert.equal(stripTag("  @W-3: build it"), "build it");
  assert.equal(stripTag("Ask @Requester later"), "Ask @Requester later");
  assert.equal(stripTag("no tag"), "no tag");
  assert.equal(stripTag("@Requester"), "");
  assert.equal(stripTag(null), "");
  assert.equal(stripTag("@Requester\nnext line"), "\nnext line");
});

test("providerLabel: Claude, Codex or stub", () => {
  assert.equal(providerLabel("claude"), "Claude");
  assert.equal(providerLabel("codex"), "Codex");
  assert.equal(providerLabel("stub"), "stub");
  assert.equal(providerLabel(null), "");
  assert.equal(providerLabel("other  one"), "other one");
});

/* ================================================================ parseAsk: a question with options (J2's own reader) */
test("parseAsk reads one unnumbered question: the line above its options", () => {
  const a = parseAsk(ASK);
  assert.deepEqual(a, {say: "", qs: [{q: "@Requester Should the menu show prices?", opts: ["Yes, show the prices", "No, names only"]}]});
});

test("parseAsk reads numbered questions, each with its options, and what was said before them", () => {
  const a = parseAsk("@Requester I need two things.\n1. Which colour?\n   Option 1: Warm\n   Option 2: Cool\n2. Which font?\n   Option 1: Serif\n   Option 2: Sans");
  assert.equal(a.say, "@Requester I need two things.");
  assert.deepEqual(a.qs, [{q: "Which colour?", opts: ["Warm", "Cool"]}, {q: "Which font?", opts: ["Serif", "Sans"]}]);
});

test("parseAsk cuts the price tag off an option and keeps a line that is not a question", () => {
  const a = parseAsk("- Still a list item\n   Option 1: Add a blog [adds 3 units]\n   Option 2: Skip it");
  assert.deepEqual(a.qs, [{q: "", opts: ["Add a blog", "Skip it"]}]);
  assert.equal(a.say, "- Still a list item");
  assert.deepEqual(parseAsk("1. Q?\n   Option 1: A [adds 2 work credits per page]").qs[0].opts, ["A"]);
});

test("parseAsk drops a line that comes after the first question and is neither a question nor an option", () => {
  assert.deepEqual(parseAsk("1. First?\n   Option 1: yes\nstray line\n2. Second?").qs.map(q => q.q), ["First?", "Second?"]);
  assert.equal(parseAsk("1. First?\nstray").say, "");
  assert.deepEqual(parseAsk(null), {say: "", qs: []});
  assert.deepEqual(parseAsk("just words\nmore words"), {say: "just words\nmore words", qs: []});
});

/* ================================================================ transcript: bubbles */
test("the owner's lines are .sb.me and the team's are .sb.team with who wrote them", () => {
  const doc = dom(transcript(writable(), [msg({id: 1, role: "user", who: "user", text: "A website for my cafe"}), msg({id: 2, text: "@Requester Thanks. I have what I need."})]));
  const me = one(doc, "div.nmsg.sb.me");
  assert.equal(textOf(me), "A website for my cafe");
  assert.equal(me.attrs["data-id"], "1");
  assert.equal(me.attrs["data-who"], "user");
  assert.equal(select(me, "small").length, 0);
  const team = one(doc, "div.nmsg.sb.team");
  assert.equal(textOf(one(team, "small")), "Client Lead (Identity)");
  assert.equal(textOf(team), "Client Lead (Identity)Thanks. I have what I need.");
  assert.equal(team.attrs["data-id"], "2");
  assert.equal(team.attrs["data-who"], "identity");
  assert.equal(team.attrs["data-kind"], "text");
  assert.equal(team.attrs["data-state"], "ok");
});

test("a department chat reads the sentence, not the address: the leading @Requester is dropped", () => {
  const doc = dom(transcript(writable(), DEPT.messages.map(m => ({...m, answered_by: m.answered_by}))));
  assert.equal(textOf(select(doc, "div.nmsg")[3]), "Client Lead (Identity)Thanks. I have what I need and the team is starting.");
});

test("a working log shows the agents' addresses as they are, with the label of each author", () => {
  const doc = dom(transcript(logOf(), IDENTITY_LOG.messages));
  const texts = select(doc, "div.nmsg").map(textOf);
  assert.ok(texts.includes("Client Lead (Identity)@Adaptation Charter recorded from the brief; it had enough to work."));
  assert.ok(texts.includes("ValidatorValidator: the charter has 2 done-when items, 3 are needed."));
  const sys = select(doc, "div.nmsg.sys");
  assert.equal(textOf(sys[0]), "The team started on your request.");
  assert.equal(sys.length, 2);
});

test("every message is one element with its id, author, kind and state", () => {
  const doc = dom(transcript(logOf(), IDENTITY_LOG.messages));
  const bubbles = select(doc, "div.nmsg");
  assert.equal(bubbles.length, IDENTITY_LOG.messages.length);
  assert.deepEqual(bubbles.map(b => b.attrs["data-id"]), IDENTITY_LOG.messages.map(m => String(m.id)));
  assert.deepEqual(bubbles.map(b => b.attrs["data-state"]), IDENTITY_LOG.messages.map(() => "ok"));
});

test("a note sits in the middle, an error is a red card, a pending line is dimmed", () => {
  const doc = dom(transcript(writable(), [msg({id: 1, who: "system", kind: "note", text: "Merged into Web"}), msg({id: 2, kind: "error", who: "sutra", text: "Something broke"}),
    msg({id: 3, role: "user", who: "user", text: "wait", state: "pending"})]));
  assert.equal(textOf(one(doc, "div.nmsg.note")), "Merged into Web");
  assert.equal(textOf(one(doc, "div.nmsg.oops")), "Something broke");
  const pending = one(doc, "div.nmsg.pending");
  assert.equal(pending.attrs["data-state"], "pending");
  assert.ok(pending.attrs.class.includes("sb me"));
});

test("an owner's line that failed shows its error line, and a Retry only in the org chat", () => {
  const failed = msg({id: 2, role: "user", who: "user", text: "Make a site", state: "error"});
  const inOrg = one(dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, [failed])), "div.nmsg.failed");
  assert.equal(textOf(one(inOrg, "div.nerr")), "Something went wrong. Try again. Retry");
  assert.equal(one(inOrg, "div.nerr button").attrs["data-act"], "retry");
  const inDept = one(dom(transcript(writable(), [failed])), "div.nmsg.failed");
  assert.equal(textOf(one(inDept, "div.nerr")), "Something went wrong. Try again.");
  assert.equal(select(inDept, "button").length, 0);
});

test("a message from the wire is escaped and may use **bold**, `code` and line breaks", () => {
  const bad = `<script>x()</script> **b** \`c\`\nnext`;
  const doc = dom(transcript(writable(), [msg({text: bad}), msg({id: 2, role: "user", who: "user", text: bad}), msg({id: 3, who: "<i>x</i>", text: "t"})]));
  const bubbles = select(doc, "div.nmsg");
  assert.equal(select(doc, "script").length, 0);
  assert.equal(textOf(bubbles[0]), "Client Lead (Identity)<script>x()</script> b c\nnext");
  assert.equal(select(bubbles[0], "b").length, 1);
  assert.equal(select(bubbles[0], "code").length, 1);
  assert.equal(textOf(bubbles[1]), "<script>x()</script> b c\nnext");
  assert.equal(textOf(one(bubbles[2], "small")), "<i>x</i>");
});

test("an empty session says so, in words that fit the kind of session", () => {
  assert.equal(textOf(one(dom(transcript(writable(), [])), "p.nempty")), "No messages yet.");
  assert.equal(textOf(one(dom(transcript(logOf(), [])), "p.nempty")), "Nothing in this log yet.");
  assert.equal(textOf(one(dom(transcript(null, null)), "p.nempty")), "No messages yet.");
});

test("garbage in the list is skipped and the rest still draws", () => {
  const html = transcript(writable(), [null, 4, "x", [], msg({id: 9}), {id: 10, kind: "weird", who: null, text: 5}, {id: 11, kind: "card", card: null, text: "plain"}]);
  const doc = dom(html);
  assert.deepEqual(select(doc, "div.nmsg").map(b => b.attrs["data-id"]), ["9", "10", "11"]);
  assert.equal(textOf(select(doc, "div.nmsg")[1]), "5");
  assert.equal(transcript(null, [msg()]).includes("undefined"), false);
});

/* ================================================================ transcript: a question and its options */
const question = (over = {}) => msg({id: 2, kind: "question", text: ASK, pause: "info", ...over});

test("an open question shows its options as buttons, once, and no numbered list", () => {
  const doc = dom(transcript(writable(), [msg({id: 1, role: "user", who: "user", text: "A cafe site"}), question()]));
  const bubble = one(doc, "div.nmsg[data-kind=question]");
  assert.equal(textOf(one(bubble, "p.sq")), "Should the menu show prices?");
  const group = one(bubble, "div.opts");
  assert.equal(group.attrs["data-q"], "1");
  assert.equal(group.attrs["data-n"], "1");
  const buttons = select(group, "button");
  assert.deepEqual(buttons.map(textOf), ["Yes, show the prices", "No, names only"]);
  assert.deepEqual(buttons.map(b => b.attrs["data-opt"]), ["1", "2"]);
  assert.deepEqual(buttons.map(b => b.attrs["data-act"]), ["option", "option"]);
  assert.equal(select(bubble, "ol").length, 0);
});

test("a question that was answered keeps its words and loses its buttons", () => {
  const doc = dom(transcript(writable(), [question({answered_by: 3}), msg({id: 3, role: "user", who: "user", text: "Option 2"})]));
  assert.equal(select(doc, "div.opts").length, 0);
  assert.equal(textOf(one(doc, "p.sq")), "Should the menu show prices?");
});

test("only the last open question has buttons, and only where the owner can write", () => {
  const two = [question({id: 2}), question({id: 4, text: ASK.replace("show prices", "list allergens")})];
  const doc = dom(transcript(writable(), two));
  assert.equal(select(doc, "div.opts").length, 1);
  assert.equal(select(select(doc, "div.nmsg")[0], "div.opts").length, 0);
  assert.equal(select(select(doc, "div.nmsg")[1], "div.opts").length, 1);
  assert.equal(select(dom(transcript(logOf(), [question()])), "div.opts").length, 0);
  assert.equal(select(dom(transcript(writable({writable: false}), [question()])), "div.opts").length, 0);
  assert.equal(select(dom(transcript(writable({status: "archived"}), [question()])), "div.opts").length, 0);
  assert.equal(select(dom(transcript(writable(), [question()], {live: false})), "div.opts").length, 0);
  assert.equal(select(dom(transcript(writable(), [question()], {live: true})), "div.opts").length, 1);
});

test("an owner's 'Option 2' is shown as the option it picked", () => {
  const doc = dom(transcript(writable(), [question({answered_by: 3}), msg({id: 3, role: "user", who: "user", text: "Option 2"}), msg({id: 4, role: "user", who: "user", text: "Option 7"})]));
  const lines = select(doc, "div.nmsg.me").map(textOf);
  assert.deepEqual(lines, ["No, names only", "Option 7"]);
  assert.deepEqual(select(dom(transcript(writable(), [msg({id: 1, role: "user", who: "user", text: "Option 1"})])), "div.me").map(textOf), ["Option 1"]);
});

test("several questions each get their buttons, numbered, with the count of questions", () => {
  const text = "@Requester Two things.\n1. Which colour?\n   Option 1: Warm\n   Option 2: Cool\n2. Which font?\n   Option 1: Serif";
  const doc = dom(transcript(writable(), [question({text})]));
  const groups = select(doc, "div.opts");
  assert.deepEqual(groups.map(g => [g.attrs["data-q"], g.attrs["data-n"]]), [["1", "2"], ["2", "2"]]);
  assert.deepEqual(select(doc, "p.sq").map(textOf), ["Which colour?", "Which font?"]);
  assert.equal(textOf(select(doc, "div.nmsg")[0]).startsWith("Client Lead (Identity)Two things."), true);
});

test("questions with no options are a numbered list, and a plain sentence stays a sentence", () => {
  const list = dom(transcript(writable(), [question({text: "@Requester Tell me more.\n1. Who is it for?\n2. When is it due?"})]));
  assert.deepEqual(select(list, "ol li").map(textOf), ["Who is it for?", "When is it due?"]);
  assert.equal(select(list, "div.opts").length, 0);
  const sentence = dom(transcript(writable(), [question({text: "@Requester Anything else?"})]));
  assert.equal(textOf(select(sentence, "div.nmsg")[0]), "Client Lead (Identity)Anything else?");
});

test("a working log keeps a question as it was written and offers no buttons", () => {
  const doc = dom(transcript(logOf(), [question()]));
  assert.equal(select(doc, "div.opts").length, 0);
  assert.equal(select(doc, "p.sq").length, 0);
  assert.equal(textOf(select(doc, "div.nmsg")[0]), "Client Lead (Identity)" + ASK.replace(/\n/g, "\n"));
});

/* ================================================================ transcript: cards, and who is named on them */
test("on the org chat an Identity carries its department's name, and a card gives the name it carries", () => {
  const doc = dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, ORG.messages.slice(0, 6), {deptSessions: {web: "cs_5e0a77b19c3d"}}));
  const bubbles = select(doc, "div.nmsg");
  assert.equal(textOf(one(bubbles[3], "small")), "Sutra");
  assert.equal(textOf(one(bubbles[5], "small")), "Web" + DOT + "Client Lead (Identity)");
  assert.equal(one(bubbles[5], "div.ncard").attrs["data-session"], "cs_5e0a77b19c3d");
});

test("outside the org chat a plain Identity line has no department in front, but a card does", () => {
  const plain = dom(transcript(writable(), [msg()], {deptName: "Web"}));
  assert.equal(textOf(one(plain, "small")), "Client Lead (Identity)");
  const withCard = dom(transcript(writable(), [msg({kind: "card", card: {type: "needs_you", dept_id: "web", dept_name: "Web", question_message_id: 2, text: "Q?", options: []}})]));
  assert.equal(textOf(one(withCard, "small")), "Web" + DOT + "Client Lead (Identity)");
  const orgText = dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, [msg()], {deptName: "Web"}));
  assert.equal(textOf(one(orgText, "small")), "Web" + DOT + "Client Lead (Identity)");
});

test("an answered approval or choice shows the answer the owner gave, and an open one its buttons", () => {
  const messages = [msg({id: 20, who: "sutra", kind: "card", card: ORG.messages[19].card}), msg({id: 22, who: "sutra", kind: "card", card: ORG.messages[21].card})];
  const open = dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, messages));
  assert.equal(select(open, "button[data-act=choose]").length, 2 + 3);
  const answered = dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, messages, {answers: {20: "Yes"}}));
  assert.equal(select(select(answered, "div.nmsg")[0], "button").length, 0);
  assert.equal(textOf(one(select(answered, "div.nmsg")[0], "p.canswer")), "You answered: Yes");
  assert.equal(select(select(answered, "div.nmsg")[1], "button").length, 3);
});

test("answersOf closes an approval or choice the server says was answered, with the words of the owner line that answered it", () => {
  // QA org-chat-teams: after a reload the transcript only had `answered_by`, which Home read as a question's; the card came back with Yes and No
  const owner = (id, over = {}) => msg({id, role: "user", who: "user", text: "Yes", ...over});
  const messages = [
    msg({id: 20, who: "sutra", kind: "card", card: ORG.messages[19].card, answered_by: 21}), owner(21, {text: "No"}),
    msg({id: 22, who: "sutra", kind: "card", card: ORG.messages[21].card}),
    msg({id: 23, who: "sutra", kind: "card", card: ORG.messages[19].card, answered_by: 23}),          // decided without a button: it points at itself
    msg({id: 24, who: "sutra", kind: "card", card: ORG.messages[21].card, answered_by: 99}),          // the answering line is not in the list
  ];
  const answers = ChatView.answersOf(messages, {});
  assert.deepEqual(answers, {20: "No", 23: "", 24: ""});
  const html = dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, messages, {answers}));
  const rows = select(html, "div.nmsg").filter(row => row.attrs["data-kind"] === "card");
  assert.deepEqual(rows.map(row => select(row, "button").length), [0, 3, 0, 0]);
  assert.equal(textOf(one(rows[0], "p.canswer")), "You answered: No");
  assert.equal(textOf(one(rows[2], "p.canswer")), "Answered");
});

test("answersOf keeps what the owner clicked here, and closes a team question that /api/needs-you no longer lists once it was read", () => {
  const question = msg({id: 6, kind: "card", card: ORG.messages[5].card});
  const asked = ORG.messages[5].card.question_message_id;
  assert.deepEqual(ChatView.answersOf([question], {needsLoaded: false, needs: []}), {});
  assert.deepEqual(ChatView.answersOf([question], {needsLoaded: true, needs: [{message_id: asked}]}), {});
  assert.deepEqual(ChatView.answersOf([question], {needsLoaded: true, needs: []}), {6: ""});
  assert.deepEqual(ChatView.answersOf([question], {needsLoaded: true, needs: [], local: {6: "Option 1"}}), {6: "Option 1"});
  assert.deepEqual(ChatView.answersOf([question, msg({id: 7})], {local: {7: "x"}}), {7: "x"});
  assert.deepEqual(ChatView.answersOf(null, null), {});
});

test("a needs_you card answered in the transcript reads Answered", () => {
  const messages = [msg({id: 6, kind: "card", card: ORG.messages[5].card})];
  const doc = dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, messages, {answers: {6: "Option 1"}}));
  assert.equal(textOf(one(doc, "p.canswer")), "Answered");
  assert.equal(select(doc, "textarea").length, 0);
});

test("an atom card is drawn in a function node's log and is plain text anywhere else", () => {
  const atomMsg = IDENTITY_LOG.messages[1];
  const inLog = dom(transcript(logOf(), [atomMsg]));
  assert.equal(one(inLog, "div.ncard").attrs["data-card"], "atom");
  const elsewhere = dom(transcript(writable(), [atomMsg]));
  assert.equal(one(elsewhere, "div.ncard").attrs["data-card"], "unknown");
  assert.equal(textOf(one(elsewhere, "div.ncard")), "ATOM REFUSED: done");
});

/* ================================================================ card */
test("a task card is the hand-over: the team is on it, with a link to the team and a button to the graph", () => {
  const c = dom(card({type: "task", task_id: "tsk_a1b2c3d4e5f6", dept_id: "web", dept_name: "Web", title: "Coffee shop landing page", status: "running"}));
  const root = one(c, "div.ncard");
  assert.ok(root.attrs.class.includes("ready"));
  assert.equal(root.attrs["data-card"], "task");
  assert.equal(textOf(one(root, "h2")), "Your Web team is on it");
  assert.equal(textOf(one(root, "p.ctitle")), "Coffee shop landing page running");
  const link = one(root, "a[data-act=open-team]");
  assert.equal(link.attrs.href, "/d/web/?view=simple");
  assert.equal(textOf(link), "Open the team");
  const show = one(root, "button[data-act=show-node]");
  assert.equal(show.attrs["data-node"], "web");
  assert.equal(textOf(show), "See it on the graph");
});

test("a task card with no department id is a button with no link, and one with no name still reads well", () => {
  const root = one(dom(card({type: "task", task_id: "tsk_1", title: "Menu", status: "waiting_user"})), "div.ncard");
  assert.equal(textOf(one(root, "h2")), "Your team is on it");
  assert.equal(select(root, "a").length, 0);
  assert.equal(one(root, "button[data-act=open-team]").attrs["data-task"], "tsk_1");
  assert.equal(select(root, "button[data-act=show-node]").length, 0);
  assert.equal(textOf(one(root, "span.cstat")), "waiting for you");
});

test("a team id in a link is encoded and escaped", () => {
  const html = card({type: "task", dept_id: 'a b"<c', dept_name: "X", title: "t"});
  assert.equal(one(dom(html), "a").attrs.href, "/d/a%20b%22%3Cc/?view=simple");
  assert.equal(html.includes('"<c'), false);
});

test("a chart_change card: the summary, what was added, moved and merged, and a button to the org chart", () => {
  const c = one(dom(card(ORG.messages[14].card)), "div.ncard");
  assert.equal(c.attrs["data-card"], "chart_change");
  assert.equal(c.attrs["data-decision"], "rearrange");
  assert.equal(c.attrs["data-pending"], "false");
  assert.equal(c.attrs["data-change"], "chg-0005");
  assert.equal(c.attrs["data-seq"], "5");
  assert.equal(textOf(one(c, "p.csum")), "Added the Content team and moved Menu into it");
  assert.deepEqual(select(c, "li").map(textOf), ["Added: Content (team)", "Moved: Menu, from Web to Content"]);
  const button = one(c, "button[data-act=show-change]");
  assert.equal(textOf(button), "Show in the org chart");
  assert.equal(button.attrs["data-change"], "chg-0005");
  assert.equal(button.attrs["data-seq"], "5");
  assert.equal(select(c, "p.cpend").length, 0);
});

test("a chart_change card that waits for the owner says so, and lists a merge", () => {
  const c = one(dom(card(ORG.messages[18].card)), "div.ncard");
  assert.equal(c.attrs["data-pending"], "true");
  assert.equal(textOf(one(c, "p.cpend")), "Waiting for your yes or no.");
  assert.deepEqual(select(c, "li").map(textOf), ["Merged: FAQ into Menu"]);
});

test("a chart_change card finds its sequence number in change_id, seq or change_seq, and reads the older plain-id lists", () => {
  const seq = c => one(dom(card({type: "chart_change", summary: "s", ...c})), "div.ncard").attrs["data-seq"];
  assert.equal(seq({change_id: "chg-0012"}), "12");
  assert.equal(seq({seq: 7}), "7");
  assert.equal(seq({change_seq: 9}), "9");
  assert.equal(seq({seq: 3, change_id: "chg-0012"}), "3");
  assert.equal(seq({}), undefined);
  const old = one(dom(card({type: "chart_change", summary: "s", added: ["web"], moved: ["menu"], archived: ["faq"]})), "div.ncard");
  assert.deepEqual(select(old, "li").map(textOf), ["Added: web", "Moved: menu", "Merged: faq"]);
  const odd = one(dom(card({type: "chart_change", summary: "s", added: [{id: "x", name: "X", kind: "weird"}], moved: [{id: "m", name: "M", from_name: "A"}, {id: "n", name: "N", to_name: "B"}]})), "div.ncard");
  assert.deepEqual(select(odd, "li").map(textOf), ["Added: X (weird)", "Moved: M, from A to a new place", "Moved: N, from its place to B"]);
});

test("an approval card asks its question and sends the label of the option as the answer", () => {
  const c = one(dom(card(ORG.messages[19].card)), "div.ncard");
  assert.equal(c.attrs["data-card"], "approval");
  assert.equal(c.attrs["data-change"], "chg-0006");
  assert.equal(textOf(one(c, "p.sq")), "Merge FAQ into Menu? FAQ's chat is filed under Menu.");
  const buttons = select(c, "button");
  assert.deepEqual(buttons.map(textOf), ["Yes", "No"]);
  assert.deepEqual(buttons.map(b => b.attrs["data-option"]), ["Yes", "No"]);
  assert.deepEqual(buttons.map(b => b.attrs["data-id"]), ["yes", "no"]);
  assert.deepEqual(buttons.map(b => b.attrs["data-act"]), ["choose", "choose"]);
});

test("a choice card offers its teams and 'None of these'", () => {
  const c = one(dom(card(ORG.messages[21].card)), "div.ncard");
  assert.equal(c.attrs["data-card"], "choice");
  assert.equal(textOf(one(c, "p.sq")), "Which team fits best?");
  assert.deepEqual(select(c, "button").map(textOf), ["Web", "Content", "None of these"]);
  assert.deepEqual(select(c, "button").map(b => b.attrs["data-id"]), ["web", "content", "none"]);
});

test("options may be plain strings; a card with no options has no buttons", () => {
  assert.deepEqual(select(dom(card({type: "choice", question: "Q?", options: ["A", "B", ""]})), "button").map(b => b.attrs["data-option"]), ["A", "B"]);
  assert.equal(select(dom(card({type: "choice", question: "Q?"})), "button").length, 0);
  assert.equal(select(dom(card({type: "approval", question: "Q?", options: "no"})), "button").length, 0);
});

test("an answered approval or choice shows the answer and no buttons", () => {
  const answered = one(dom(card(ORG.messages[19].card, {answer: "No"})), "div.ncard");
  assert.equal(textOf(one(answered, "p.canswer")), "You answered: No");
  assert.equal(select(answered, "button").length, 0);
  assert.equal(answered.attrs["data-answered"], "true");
  const bare = one(dom(card(ORG.messages[21].card, {answered: true})), "div.ncard");
  assert.equal(textOf(one(bare, "p.canswer")), "Answered");
  assert.equal(select(bare, "button").length, 0);
  assert.equal("data-answered" in one(dom(card(ORG.messages[21].card)), "div.ncard").attrs, false);
});

test("a needs_you card is the team's Identity question as it asked it, with option buttons and a box, answered to the DEPARTMENT's session", () => {
  const c = one(dom(card(ORG.messages[5].card, {deptSession: "cs_5e0a77b19c3d"})), "div.ncard");
  assert.equal(c.attrs["data-card"], "needs_you");
  assert.equal(c.attrs["data-dept"], "web");
  assert.equal(c.attrs["data-question"], "2");
  assert.equal(c.attrs["data-session"], "cs_5e0a77b19c3d");
  assert.equal(textOf(one(c, "h2")), "Web has a question for you");
  assert.equal(textOf(one(c, "p.cquestion")), "Should the menu show prices?");
  const buttons = select(c, "button[data-act=answer-option]");
  assert.deepEqual(buttons.map(textOf), ["Yes, show the prices", "No, names only"]);
  assert.deepEqual(buttons.map(b => b.attrs["data-opt"]), ["1", "2"]);
  assert.deepEqual(buttons.map(b => b.attrs["data-text"]), ["Yes, show the prices", "No, names only"]);
  assert.equal(select(c, "textarea").length, 1);
  assert.equal(textOf(one(c, "button[data-act=answer]")), "Answer");
  assert.equal(JSON.stringify(c).includes("cs_org"), false);
});

test("a needs_you card with no session to name carries none, and never names the org chat", () => {
  const c = one(dom(card(ORG.messages[5].card)), "div.ncard");
  assert.equal("data-session" in c.attrs, false);
  assert.equal(card(ORG.messages[5].card, {deptSession: "  "}).includes("data-session"), false);
});

test("a needs_you card takes its options from the text when the card names none", () => {
  const c = one(dom(card({type: "needs_you", dept_id: "web", dept_name: "Web", question_message_id: 4, text: ASK, options: []})), "div.ncard");
  assert.deepEqual(select(c, "button[data-act=answer-option]").map(textOf), ["Yes, show the prices", "No, names only"]);
  const free = one(dom(card({type: "needs_you", dept_id: "web", dept_name: "", question_message_id: 4, text: "@Requester What name should the cafe use?"})), "div.ncard");
  assert.equal(textOf(one(free, "h2")), "A team has a question for you");
  assert.equal(textOf(one(free, "p.cquestion")), "What name should the cafe use?");
  assert.equal(select(free, "div.opts").length, 0);
  assert.equal(select(free, "textarea").length, 1);
});

test("an answered needs_you card reads Answered and has no box", () => {
  const c = one(dom(card(ORG.messages[5].card, {answered: true})), "div.ncard");
  assert.equal(textOf(one(c, "p.canswer")), "Answered");
  assert.equal(select(c, "textarea").length, 0);
  assert.equal(select(c, "button").length, 0);
  assert.equal(c.attrs["data-answered"], "true");
});

test("a done card is green when done, amber with open items, red when it crashed or stopped, with a way to the team", () => {
  const base = {type: "done", task_id: "tsk_b7c8d9e0f1a2", dept_name: "Content", title: "Menu page copy", outcome: "Done: the menu page copy is ready."};
  const tone = status => one(dom(card({...base, status})), "div.ncard");
  const done = tone("done");
  assert.equal(done.attrs["data-tone"], "ok");
  assert.ok(done.attrs.class.includes("ready") && !done.attrs.class.includes("oops"));
  assert.equal(textOf(one(done, "h2")), "Your Content team is done");
  assert.equal(textOf(one(done, "p.ctitle")), "Menu page copy");
  assert.equal(textOf(one(done, "p.coutcome")), "Done: the menu page copy is ready.");
  const open = tone("done_with_open_items");
  assert.equal(open.attrs["data-tone"], "warn");
  assert.equal(textOf(one(open, "h2")), "Your Content team is done, with some things left open");
  ["crashed", "stopped"].forEach(status => {
    const bad = tone(status);
    assert.equal(bad.attrs["data-tone"], "bad");
    assert.ok(bad.attrs.class.includes("oops"));
  });
  assert.equal(textOf(one(tone("crashed"), "h2")), "Your Content team ran into a problem");
  assert.equal(textOf(one(tone("stopped"), "h2")), "Your Content team was stopped");
  assert.equal(tone("weird_state").attrs["data-tone"], "warn");
  assert.equal(textOf(one(tone("weird_state"), "h2")), "Your Content team weird state");
});

test("a done card links to the team by id when it has one, and otherwise by name", () => {
  const withId = one(dom(card({type: "done", task_id: "t", dept_id: "content", dept_name: "Content", title: "t", status: "done"})), "div.ncard");
  assert.equal(one(withId, "a[data-act=open-team]").attrs.href, "/d/content/?view=simple");
  const byName = one(dom(card(ORG.messages[16].card)), "div.ncard");
  assert.equal(select(byName, "a").length, 0);
  const button = one(byName, "button[data-act=open-team]");
  assert.equal(button.attrs["data-dept-name"], "Content");
  assert.equal(button.attrs["data-task"], "tsk_b7c8d9e0f1a2");
});

// The receipt (GAP-model-quality): what a finished task cost and took, evidence only.
const DONE = {type: "done", task_id: "tsk_b7c8d9e0f1a2", dept_name: "Content", title: "Menu page copy", status: "done", outcome: "Done."};
const receiptOf = receipt => { const found = select(dom(card({...DONE, receipt})), "p.creceipt"); return found.length ? textOf(found[0]) : null; };

test("a done card's receipt says what the task took and cost and how many items passed their checks", () => {
  assert.equal(receiptOf({usd: 0.42, tokens: 1800, seconds: 372, checks_passed: 7, checks_total: 8, attempt: null}),
    "Took 6 min" + DOT + "about $0.42" + DOT + "7 of 8 items passed their checks");
  assert.equal(receiptOf({usd: 1.5, tokens: null, seconds: 60, checks_passed: 2, checks_total: 3, attempt: 2}),
    "Attempt 2" + DOT + "Took 1 min" + DOT + "about $1.50" + DOT + "2 of 3 items passed their checks");
  assert.equal(receiptOf({usd: null, tokens: 4900, seconds: 3900, checks_passed: 0, checks_total: 0}), "Took 1 h 5 min" + DOT + "4,900 tokens");
  assert.equal(receiptOf({seconds: 200000}), "Took 2 days");
});

test("a receipt shows no dollars under half a cent, no checks when the team recorded none, and nothing when it has nothing to say", () => {
  assert.equal(receiptOf({usd: 0.004, tokens: 900, seconds: 45, checks_passed: 0, checks_total: 0}), "Took 45 s" + DOT + "900 tokens");
  assert.equal(receiptOf({usd: 0.0049, tokens: null, seconds: 5, checks_passed: 0, checks_total: 0}), "Took 5 s");
  assert.equal(receiptOf({usd: 0.005, seconds: 5}), "Took 5 s" + DOT + "about $0.01");
  assert.equal(receiptOf({usd: null, tokens: null, seconds: null, checks_passed: 0, checks_total: 0, attempt: null}), null);
  assert.equal(receiptOf({checks_passed: 9, checks_total: 3}), "3 of 3 items passed their checks");
  assert.equal(receiptOf({attempt: 1, seconds: 1}), "Took 1 s");                                  // a first attempt is not named
});

test("a done card without a receipt is drawn byte for byte as before the receipt existed", () => {
  const before = '<div class="ncard ready ok c-done" data-card="done" data-tone="ok" data-task="tsk_b7c8d9e0f1a2"><h2>Your Content team is done</h2>' +
    '<p class="ctitle">Menu page copy</p><p class="coutcome">Done.</p><div class="acts"><button type="button" class="lbtn" data-act="open-team"' +
    ' data-task="tsk_b7c8d9e0f1a2" data-dept-name="Content">Open the team</button></div></div>';
  assert.equal(card(DONE), before);
  assert.equal(card({...DONE, receipt: null}), before);
  assert.equal(card({...DONE, receipt: "Took 6 min"}), before);
});

test("a receipt from the wire is escaped, takes numbers only and stays well formed", () => {
  const bad = `<script>alert("x")</script>`;
  const html = card({...DONE, receipt: {usd: bad, tokens: bad, seconds: bad, checks_passed: bad, checks_total: bad, attempt: bad}});
  assert.equal(html.includes("<script"), false);
  assert.equal(select(parse(html), "p.creceipt").length, 0);
  const mixed = card({...DONE, receipt: {usd: "0.42", tokens: -5, seconds: 61.9, checks_passed: "7", checks_total: 8, attempt: Infinity}});
  assert.equal(textOf(one(parse(mixed), "p.creceipt")), "Took 1 min" + DOT + "0 of 8 items passed their checks");
});

test("an atom card of a function node: its label is the title, then the goal and the rows", () => {
  const c = one(dom(card(IDENTITY_LOG.messages[1].card, {sessionKind: "function"})), "div.ncard");
  assert.equal(c.attrs["data-card"], "atom");
  assert.equal(c.attrs["data-outcome"], "refused");
  assert.equal(c.attrs["data-atom"], "a-a810960e61-01");
  assert.equal(textOf(one(c, "h4")), "ATOM REFUSED");
  assert.equal(textOf(one(c, "p.agoal")), "done");
  assert.deepEqual(select(c, "dt").map(textOf), ["Reason"]);
  assert.deepEqual(select(c, "dd").map(textOf), ["goal is banal ('done'): state the observable outcome"]);
  const opened = one(dom(card(IDENTITY_LOG.messages[2].card, {sessionKind: "function"})), "div.ncard");
  assert.deepEqual(select(opened, "dt").map(textOf), ["Done when", "Done by"]);
  assert.ok(opened.attrs.class.includes("o-opened"));
  const bare = one(dom(card({type: "atom", outcome: "closed"}, {sessionKind: "function"})), "div.ncard");
  assert.equal(textOf(one(bare, "h4")), "CLOSED");
  assert.equal(select(bare, "dl").length, 0);
});

test("the atom card is plain text outside a function node's session", () => {
  const html = card(IDENTITY_LOG.messages[1].card, {sessionKind: "department"});
  assert.equal(one(dom(html), "div.ncard").attrs["data-card"], "unknown");
  assert.equal(card(IDENTITY_LOG.messages[1].card).includes("c-atom"), false);
  assert.equal(card(IDENTITY_LOG.messages[1].card, {sessionKind: "function"}).includes("c-atom"), true);
});

test("a card of a type this module does not know is plain text, and no card at all is nothing", () => {
  assert.equal(textOf(one(dom(card({type: "poll", title: "Pick a <b>colour</b>"})), "div.ncard")), "Pick a <b>colour</b>");
  assert.equal(textOf(one(dom(card({type: "x", text: "first", summary: "second"})), "div.ncard")), "first");
  assert.equal(textOf(one(dom(card({type: "x"})), "div.ncard")), "");
  assert.equal(card({type: "poll", title: "<script>"}).includes("<script"), false);
  [null, undefined, 4, "x", [], [{type: "task"}]].forEach(value => assert.equal(card(value), ""));
});

test("cards escape every word of the wire and stay well formed", () => {
  const bad = `<script>alert("x")</script> & 'q'`;
  const cards = [
    {type: "task", task_id: bad, dept_id: bad, dept_name: bad, title: bad, status: bad},
    {type: "chart_change", change_id: bad, decision: bad, summary: bad, added: [{name: bad, kind: bad}], moved: [{name: bad, from_name: bad, to_name: bad}], archived: [{name: bad, into_name: bad}], pending: true},
    {type: "approval", change_id: bad, question: bad, options: [{id: bad, label: bad}]},
    {type: "choice", question: bad, options: [bad]},
    {type: "needs_you", dept_id: bad, dept_name: bad, question_message_id: bad, text: bad, options: [bad]},
    {type: "done", task_id: bad, dept_id: bad, dept_name: bad, title: bad, status: bad, outcome: bad},
    {type: "atom", atom_id: bad, outcome: bad, label: bad, goal: bad, rows: [{label: bad, text: bad}]},
  ];
  cards.forEach(c => {
    const html = card(c, {sessionKind: "function", deptSession: bad, answer: bad});
    assert.equal(html.includes("<script"), false, c.type);
    parse(html);
  });
});

/* ================================================================ composerState */
test("a session the owner can write in has a box with J2's placeholder", () => {
  assert.deepEqual(composerState(writable()), {hidden: false, disabled: false, placeholder: "Write a message\u2026", note: ""});
  assert.deepEqual(composerState(writable({kind: "division", title: "FAQ"}), {}), {hidden: false, disabled: false, placeholder: "Write a message\u2026", note: ""});
  assert.equal(composerState(writable(), {asking: true}).placeholder, "Or type your own answer\u2026");
});

test("a function's working log is read-only and names the persona; a step's log names the step", () => {
  const strategist = composerState(logOf());
  assert.deepEqual(strategist, {hidden: true, disabled: true, placeholder: "", note: "Read-only: this is the working log of Strategist."});
  const personas = {Identity: "Client Lead", Adaptation: "Strategist", Priority: "Prioritiser", Coordination: "Scheduler", Audit: "Quality Reviewer"};
  Object.entries(personas).forEach(([title, persona]) => assert.equal(composerState(logOf({title})).note, `Read-only: this is the working log of ${persona}.`));
  assert.equal(composerState({kind: "step", title: "Coffee shop landing page", writable: false, status: "active"}).note, "Read-only: this is the working log of Coffee shop landing page.");
  assert.equal(composerState({kind: "step", writable: false, status: "active"}).note, "Read-only: this is the working log of this node.");
  assert.equal(composerState({kind: "department", writable: "yes", status: "active"}).hidden, true);
});

test("an archived session hides the box and shows its own note", () => {
  const merged = composerState({kind: "division", title: "FAQ", writable: false, status: "archived", note: "Merged into Menu"});
  assert.deepEqual(merged, {hidden: true, disabled: true, placeholder: "", note: "Merged into Menu"});
  assert.equal(composerState({kind: "division", writable: true, status: "archived", note: ""}).note, "This chat is archived. Its history stays available.");
  assert.equal(composerState({kind: "division", writable: true, status: "archived", note: "x"}).hidden, true);
});

test("when the team is working its chat is closed with the server's sentence; the org chat stays open and queues", () => {
  const busy = composerState(writable(), {busy: true});
  assert.deepEqual(busy, {hidden: false, disabled: true, placeholder: "The team is working\u2026", note: "The team is working. You can write again when it asks you something or is done"});
  assert.equal(busy.note, ChatView.BUSY);
  assert.equal(composerState(writable({kind: "division"}), {busy: true}).disabled, true);
  const org = composerState({id: "cs_org", kind: "org", title: "Sutra", writable: true, status: "active"}, {busy: true});
  assert.deepEqual(org, {hidden: false, disabled: false, placeholder: "Write a message\u2026", note: "I answer your messages one at a time."});
  assert.equal(composerState(writable(), {busy: false}).disabled, false);
  assert.equal(composerState(writable(), {busy: "yes"}).disabled, false);
});

test("a blocked box is shown and closed with the reason", () => {
  const blocked = composerState(writable(), {blocked: "This page was opened without its access token. Reload it from the app."});
  assert.deepEqual(blocked, {hidden: false, disabled: true, placeholder: "Write a message\u2026", note: "This page was opened without its access token. Reload it from the app."});
  assert.equal(composerState(writable(), {blocked: "x", busy: true}).note, "x");
  assert.equal(composerState(writable(), {blocked: "   "}).disabled, false);
});

test("a read-only or archived session stays closed whatever the turn says", () => {
  assert.equal(composerState(logOf(), {busy: false, asking: true, blocked: ""}).hidden, true);
  assert.equal(composerState({kind: "division", writable: true, status: "archived"}, {busy: true, blocked: "x"}).hidden, true);
});

test("no session means no box", () => {
  [null, undefined, "x", 3, []].forEach(session => assert.deepEqual(composerState(session), {hidden: true, disabled: true, placeholder: "", note: ""}));
});

/* ================================================================ how the file loads */
test("the script loads as a classic script with one global and no other name, and as a module", () => {
  const sandbox = {};
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(FILE, "utf8"), sandbox);
  assert.deepEqual(Object.keys(sandbox), ["globalThis", "ChatView"]);
  assert.equal(sandbox.ChatView.safeText("**x**"), "<b>x</b>");
  assert.deepEqual(Object.keys(ChatView).sort(), Object.keys(sandbox.ChatView).sort());
});

test("the source is plain ASCII (the dot and the ellipsis are escapes)", () => {
  assert.equal(/[^\x00-\x7f]/.test(fs.readFileSync(FILE, "utf8")), false);
});

/* ================================================================ GAP-chat-comfort: the end of a direct turn, the files of an owner's line */
const owner = (id, t) => msg({id, role: "user", who: "user", text: t});
const ender = over => msg(Object.assign({role: "agent", who: "sutra"}, over));

test("a stopped direct turn reads as the kept reply and a calm note, never a red card", () => {
  const doc = dom(transcript(writable(), [owner(10, "Write the menu"), ender({id: 11, kind: "text", text: "Starters, mains", turn: 10}),
    ender({id: 12, kind: "note", text: "Stopped. What was written is kept.", turn: 10})]));
  assert.equal(textOf(one(doc, "div.nmsg.note")), "Stopped. What was written is kept.");
  assert.equal(select(doc, "div.nmsg.oops").length, 0);
  assert.equal(select(doc, "button").length, 0);
  assert.match(textOf(one(doc, "div.nmsg.team")), /Starters, mains/);
});

test("a direct error has Retry while its line is the owner's newest; a team error, an older one or a read-only chat has none", () => {
  const failed = [owner(10, "Write the menu"), ender({id: 11, kind: "text", text: "Start", turn: 10}), ender({id: 12, kind: "error", text: "Claude stopped unexpectedly (exit 137)", turn: 10})];
  const doc = dom(transcript(writable(), failed));
  const retry = one(doc, "div.nmsg.oops button");
  assert.deepEqual([retry.attrs["data-act"], retry.attrs["data-turn"], textOf(retry)], ["retry-direct", "10", "Retry"]);
  assert.equal(textOf(one(doc, "div.nmsg.oops")), "Claude stopped unexpectedly (exit 137) Retry");
  assert.equal(select(dom(transcript(writable(), [owner(10, "x"), ender({id: 11, kind: "error", text: "Something broke"})])), "button").length, 0);   // not a direct turn
  assert.equal(select(dom(transcript(writable(), failed.concat([owner(13, "never mind")]))), "button").length, 0);
  assert.equal(select(dom(transcript(writable(), failed, {live: false})), "button").length, 0);
  assert.equal(select(dom(transcript(writable({writable: false}), failed)), "button").length, 0);
  assert.equal(select(dom(transcript({id: "cs_org", kind: "org", writable: true, status: "active"}, failed)), "button[data-act=retry-direct]").length, 1);
});

test("the error and the note from the wire are escaped; a forged turn cannot write into the button", () => {
  const html = transcript(writable(), [owner(10, "x"), ender({id: 11, kind: "error", text: "<img src=x onerror=alert(1)>", turn: 10}),
    ender({id: 12, kind: "note", text: "<script>x()</script>", turn: '10" onclick="x'})]);
  assert.doesNotMatch(html, /<img|<script|onclick/);
  dom(html);
});

test("an owner's line with files shows the words and the names as chips; the record line itself is not shown", () => {
  const doc = dom(transcript(writable(), [owner(10, "read these\n(attached: menu.txt, shot 1.png, a PDF)")]));
  const me = one(doc, "div.nmsg.me");
  assert.deepEqual(select(me, "ul.cattached li").map(textOf), ["TXTmenu.txt", "IMGshot 1.png", "PDFa PDF"]);
  assert.equal(textOf(me).startsWith("read these"), true);
  assert.equal(textOf(me).includes("(attached:"), false);
  assert.deepEqual(ChatView.attachedOf("hello\n(attached: a.png)"), {text: "hello", names: ["a.png"]});
  assert.deepEqual(ChatView.attachedOf("(attached: a.png)"), {text: "(attached: a.png)", names: []});         // a line of its own, not a record
  assert.deepEqual(ChatView.attachedOf("hello"), {text: "hello", names: []});
  const hostile = transcript(writable(), [owner(10, "x\n(attached: <b onmouseover=1>.png)")]);
  assert.doesNotMatch(hostile, /<b /);
  dom(hostile);
});

// ---------------------------------------------------------------- transcriptItems (gap package fluid): the same lines, one item each, for Fluid.patchList
test("fluid. transcriptItems is the transcript cut into one keyed element per message, and an empty one is one item", () => {
  const session = ORG.session;
  const items = ChatView.transcriptItems(session, ORG.messages, {deptName: ""});
  assert.equal(items.map(i => i.html).join(""), transcript(session, ORG.messages, {deptName: ""}), "joined, the items are the transcript");
  assert.equal(items.length, ORG.messages.length);
  assert.deepEqual(items.map(i => i.key), ORG.messages.map(m => "m" + m.id), "a message is keyed by its id");
  items.forEach(i => assert.match(i.html, /^<div class="nmsg[^"]*"/, "one element per item"));
  assert.equal(new Set(items.map(i => i.key)).size, items.length);
  const empty = ChatView.transcriptItems(session, [], {});
  assert.deepEqual(empty.map(i => i.key), ["empty"]);
  assert.equal(empty[0].html, transcript(session, [], {}));
  const noIds = ChatView.transcriptItems(session, [{kind: "text", who: "sutra", text: "a"}, {kind: "text", who: "sutra", text: "b"}], {});
  assert.deepEqual(noIds.map(i => i.key), ["i0", "i1"], "a line without an id is keyed by its place");
});
