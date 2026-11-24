"use strict";
// Avatars (sutra_app/ui/static/js/avatars.js): the style (classic by default), the illustrated avatar at both sizes, the activity ring wrapper,
// the sync after a paint, and the team-page hook (its `face` and `renderSimple` are wrapped, its busy and ask classes are read).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const STATIC = path.resolve(__dirname, "../../../sutra_app/ui/static");
const FILE = path.join(STATIC, "js/avatars.js");
const A = require(FILE);
const FD = require(path.join(STATIC, "js/front_door.js"));

test("in node there is no page: the style is classic and nothing is touched", () => {
  assert.equal(A.style(), "classic");
  assert.equal(A.setStyle("illustrated"), "illustrated");       // the answer is the checked value; with no document nothing keeps it
  assert.equal(A.style(), "classic");
  assert.equal(A.bootStyle(), "classic");
  assert.deepEqual(A.STYLES, ["classic", "illustrated"]);
  assert.deepEqual(A.KEYS, ["asha", "mira", "kabir", "dev", "nora"]);
});

test("the illustrated avatar is the portrait from 32 px up and the compact mark below, on that person's own disc", () => {
  for (const [i, key] of A.KEYS.entries()) {
    const big = A.svg(key, 40, {cls: "fdface"}), small = A.svg(key, 16, {cls: "av"});
    assert.match(big, new RegExp('^<svg class="fdface avill" data-face="' + key + '" width="40" height="40" viewBox="0 0 64 64" aria-hidden="true">'));
    assert.ok(big.includes('fill="var(--av-d' + (i + 1) + ')"') && big.includes('<image href="/ui/img/avatars/' + key + '.webp"'), key);
    assert.ok(!big.includes("<path"), "the portrait has no mark");
    assert.ok(small.includes('fill="var(--av-m' + (i + 1) + ')"') && !small.includes("<image"), key);
    assert.ok(!/fill="D"/.test(small), "every cut-out got the disc colour");
    assert.ok(fs.statSync(path.join(STATIC, "img/avatars", key + ".webp")).size > 2000, key + ".webp is in the package");
  }
  assert.ok(A.svg("asha", 32).includes("<image") && !A.svg("asha", 31).includes("<image"), "the cut is 32 px");
  assert.equal(A.CUT, 32);
});

test("a label is opt-in, an unknown key is Asha, and nothing from the caller reaches the markup unescaped", () => {
  assert.ok(A.svg("nora", 44, {label: true}).includes('role="img" aria-label="Nora, Quality check"'));
  assert.ok(A.svg("nora", 44, {label: false}).includes('aria-hidden="true"'));
  assert.ok(A.svg('"><script>', 40).includes('data-face="asha"'));
  assert.ok(!A.svg("asha", 40, {cls: '"><b>'}).includes("<b>"));
  assert.ok(A.svg("asha", "x").includes('width="40"'));
});

test("face() draws the classic one unless the style is illustrated", () => {
  assert.equal(A.face("mira", 40, () => "CLASSIC"), "CLASSIC");
  assert.ok(A.face("mira", 40, null).includes("avill"), "with no classic drawing to call there is only the illustrated one");
});

test("ring() wraps an avatar with its activity and gives a quiet one back as it was", () => {
  assert.equal(A.ring("<svg/>", {}), "<svg/>");
  assert.equal(A.ring("<svg/>", {who: "asha", act: "resting", badge: "zzz"}), "<svg/>");
  assert.equal(A.ring("<svg/>", {who: "asha", act: "work", id: "fd-latest"}), '<span class="avact" data-who="asha" data-act="work" data-avid="fd-latest"><svg/></span>');
  assert.equal(A.ring("<svg/>", {who: "dev", act: "done", badge: "done"}), '<span class="avact" data-who="dev" data-act="done" data-badge="done"><svg/></span>');
  assert.equal(A.ring("<svg/>", {who: "nobody", badge: "msg"}), '<span class="avact" data-who="asha" data-badge="msg"><svg/></span>');
});

test("Home's faces stay the classic drawing in node, byte for byte what front_door.js always drew", () => {
  const html = FD.facesHtml();
  assert.equal((html.match(/<svg class="fdface" /g) || []).length, 5);
  assert.ok(!html.includes("avill") && !html.includes("<image"));
});

// ---- a page: a small document, enough for the style, sync and the team-page hook
function el(attrs) {
  const cls = new Set((attrs.cls || "").split(" ").filter(Boolean)), props = {};
  return {dataset: Object.assign({}, attrs.data), kids: attrs.kids || {}, innerHTML: attrs.html || "", childElementCount: attrs.html ? 1 : 0,
    classList: {contains: c => cls.has(c), add: c => cls.add(c), has: c => cls.has(c)},
    style: {setProperty: (k, v) => { props[k] = v; }, removeProperty: k => { delete props[k]; }, props},
    querySelector(sel) { return this.kids[sel] || null; }};
}
function page(boot, extra) {
  const html = el({}), added = [], listeners = {}, stored = {};
  const mates = [], byId = {"sutra-boot": {textContent: boot}};
  const document = {documentElement: html, head: {appendChild: n => added.push(n)}, createElement: () => ({}), getElementById: id => byId[id] || null,
    querySelector: () => null,
    querySelectorAll: sel => (sel.includes(".smate") ? mates : sel.includes("data-act") ? mates.map(m => m.host).filter(h => h.dataset.act || h.dataset.badge) : [])};
  const sandbox = Object.assign({document, performance: {now: () => 2500}, localStorage: {setItem: (k, v) => { stored[k] = v; }},
    addEventListener: (name, fn) => { listeners[name] = fn; }, setTimeout: () => 1, Date, JSON, Math, Map, Object, Array, Number, String, RegExp}, extra || {});
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(FILE, "utf8"), sandbox, {filename: "avatars.js"});
  return {sandbox, html, added, listeners, stored, mates, byId};
}
function mate(key, cls, pip) {
  const host = el({cls: "sface", kids: pip ? {".pip": {}} : {}});
  const row = el({cls: "smate " + cls, data: {mate: key}, kids: {".sface": host}});
  row.host = host;
  return row;
}

test("a page takes the style from its boot block, classic for anything else, and adds the sheet once", () => {
  const ill = page('{"avatars":"illustrated"}');
  assert.equal(ill.html.dataset.avatars, "illustrated");
  assert.equal(ill.sandbox.Avatars.style(), "illustrated");
  assert.equal(ill.added.length, 1);
  assert.equal(ill.added[0].href, "/ui/css/avatars.css");
  for (const boot of ['{"avatars":"photo"}', "{}", "not json", '{"avatars":7}']) assert.equal(page(boot).html.dataset.avatars, "classic", boot);
});

test("apply() changes this page and tells the other pages of this port; a storage event from one of them changes this page", () => {
  const p = page("{}");
  assert.equal(p.sandbox.Avatars.apply("illustrated"), "illustrated");
  assert.deepEqual([p.html.dataset.avatars, p.stored["sutra:avatars"]], ["illustrated", "illustrated"]);
  p.listeners.storage({key: "sutra:avatars", newValue: "classic"});
  assert.equal(p.html.dataset.avatars, "classic");
  p.listeners.storage({key: "j2theme", newValue: "illustrated"});
  assert.equal(p.html.dataset.avatars, "classic");
  assert.equal(p.sandbox.Avatars.apply("anything"), "classic");
});

test("on a team page the page's own face is kept for classic and replaced for illustrated, with the label the caller asked for", () => {
  const calls = [];
  const p = page("{}", {face: (k, size, o) => { calls.push([k, size]); return "CLASSIC-" + k; }, renderSimple: () => "rendered"});
  assert.equal(p.sandbox.face("kabir", 42, {label: false}), "CLASSIC-kabir");
  p.sandbox.Avatars.setStyle("illustrated");
  const drawn = p.sandbox.face("kabir", 42, {label: false});
  assert.ok(drawn.startsWith('<svg class="av avill" data-face="kabir" width="42"') && drawn.includes('aria-hidden="true"'));
  assert.ok(p.sandbox.face("kabir", 22).includes('role="img" aria-label="Kabir, Designer"'), "the page's default is a labelled face");
  assert.deepEqual(calls, [["kabir", 42]]);
  assert.equal(p.sandbox.Avatars.adopt(), false, "a second adopt wraps nothing twice");
});

test("after a render each teammate's avatar says what the page's own classes say: working, asking, done", () => {
  const p = page("{}", {face: () => "", renderSimple: () => "rendered", isReady: s => s.ready === true});
  p.mates.push(mate("asha", "ask"), mate("mira", "busy"), mate("kabir", ""), mate("dev", ""), mate("nora", ""));
  const parts = [{person: "mira", st: "doing"}, {person: "kabir", st: "done"}, {person: "kabir", st: "done"}, {person: "dev", st: "done"}, {person: "dev", st: "next"}];
  assert.equal(p.sandbox.renderSimple({studio: {parts}, allChat: []}), "rendered");
  const got = Object.fromEntries(p.mates.map(m => [m.dataset.mate, [m.host.dataset.act || "", m.host.dataset.badge || "", m.host.dataset.avid]]));
  assert.deepEqual(got, {asha: ["ask", "ask", "rail-asha"], mira: ["work", "", "rail-mira"], kabir: ["done", "done", "rail-kabir"], dev: ["", "", "rail-dev"], nora: ["", "", "rail-nora"]});
  assert.equal(p.mates[1].host.style.props["--avd"], "-200ms", "the arc carries on from the shared clock (2500 ms into 1150 ms turns)");
  assert.equal(p.mates[0].host.style.props["--avd"], undefined);

  // the project is ready: Asha is done, and Nora too once she has checked it; nobody who is busy is ever "done"
  p.mates.length = 0;
  p.mates.push(mate("asha", ""), mate("nora", ""), mate("mira", "busy"));
  p.sandbox.renderSimple({ready: true, audits: [{}], studio: {parts: [{person: "mira", st: "done"}]}, allChat: []});
  assert.deepEqual(p.mates.map(m => m.host.dataset.act), ["done", "done", "work"]);
});

test("a new message from Asha shows as a badge without hiding that she is working, and an old one never does", () => {
  const p = page("{}", {face: () => "", renderSimple: () => "", isReady: () => false});
  p.mates.push(mate("asha", "busy"), mate("mira", ""));
  const said = id => ({who: "identity", to_user: true, id});
  p.sandbox.renderSimple({allChat: [said(1)]});
  assert.deepEqual([p.mates[0].host.dataset.act, p.mates[0].host.dataset.badge], ["work", undefined], "what was already said when the page opened is not news");
  p.sandbox.renderSimple({allChat: [said(1), said(2)]});
  assert.deepEqual([p.mates[0].host.dataset.act, p.mates[0].host.dataset.badge], ["work", "msg"]);
  assert.equal(p.mates[1].host.dataset.badge, undefined, "only Asha speaks to the owner");
  assert.ok(p.mates[0].host.classList.has("avfresh"), "a badge that is new for this avatar fades in");
});

test("the sheet: tokens in both themes, one badge anchor, and motion only when the viewer allows it", () => {
  const css = fs.readFileSync(path.join(STATIC, "css/avatars.css"), "utf8");
  const dark = css.match(/:root \{([^}]*)\}/)[1], light = css.match(/:root\[data-theme=light\] \{([^}]*)\}/)[1];
  const names = block => (block.match(/--av-[a-z0-9]+(?=:)/g) || []).sort();
  assert.deepEqual(names(dark), names(light));
  assert.equal(names(dark).length, 18);
  assert.ok(/left: 80%; top: 76%;[^}]*width: 28%; height: 28%;/.test(css), "the owner's badge position");
  assert.equal((css.match(/left: 80%/g) || []).length, 1, "every badge shares it");
  const motion = css.slice(css.indexOf("@media (prefers-reduced-motion: no-preference)"));
  const before = css.slice(0, css.indexOf("@keyframes avturn"));
  assert.ok(motion.includes("avturn var(--dur-turn) linear infinite") && motion.includes("var(--avd, 0ms)"));
  const panel = fs.readFileSync(path.join(STATIC, "css/sutra-panel.css"), "utf8");
  assert.ok(panel.includes("--dur-turn:" + A.TURN_MS + "ms"), "the turn the sheet draws is the turn sync() counts in");
  assert.ok(!/animation: av/.test(before), "no animation outside the no-preference block");
});

test("the sheet's ring and text colours keep their contrast in both themes", () => {
  const css = fs.readFileSync(path.join(STATIC, "css/avatars.css"), "utf8"), front = fs.readFileSync(path.join(STATIC, "css/sutra-front.css"), "utf8");
  const tokens = (src, re) => Object.fromEntries([...src.match(re)[1].matchAll(/(--[a-z0-9-]+):(#[0-9a-fA-F]{6})/g)].map(m => [m[1], m[2]]));
  const lum = hex => { const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  for (const [name, re] of [["dark", /:root \{([^}]*)\}/], ["light", /:root\[data-theme=light\] \{([^}]*)\}/]]) {
    const av = tokens(css, re), s = tokens(front, re);
    for (const bg of ["--s-bg", "--s-surface", "--s-surface2"]) {
      for (const ring of ["--av-c1", "--av-c2", "--av-c3", "--av-c4", "--av-c5", "--av-ask"]) assert.ok(ratio(av[ring], s[bg]) >= 3, `${name}: ${ring} on ${bg} is ${ratio(av[ring], s[bg]).toFixed(2)}`);
    }
    for (let n = 1; n <= 5; n++) {
      assert.ok(ratio(av["--av-m" + n], av["--av-d" + n]) >= 3, `${name}: the mark of ${n} on its disc`);
      assert.ok(ratio(s["--s-surface"], av["--av-c" + n]) >= 3, `${name}: the tick on the badge of ${n}`);
    }
    assert.ok(ratio(av["--av-askink"], av["--av-askbg"]) >= 4.5, `${name}: the question mark`);
  }
});

test("Home's card under the box shows Asha's activity around her, and the words alone still say it", () => {
  const sent = [{id: 3, role: "user", text: "A flyer"}];
  const asking = sent.concat([{id: 6, role: "agent", text: "", card: {type: "choice", question: "Which team fits best?", options: [{id: "web", label: "Web"}, {id: "none", label: "A new team"}]}}]);
  const done = sent.concat([{id: 5, role: "agent", text: "", card: {type: "task", dept_id: "web", dept_name: "Web", title: "A flyer"}}]);
  const said = sent.concat([{id: 4, role: "agent", text: "I have what I need."}]);
  const states = () => ({working: FD.latestHtml({show: true, messages: sent, status: "Setting up your project…"}), asking: FD.latestHtml({show: true, messages: asking}),
    ready: FD.latestHtml({show: true, messages: done}), update: FD.latestHtml({show: true, messages: said})});
  const plain = states();
  for (const html of Object.values(plain)) assert.ok(!html.includes("avact") && !html.includes("fdspin"), "without avatars.js there is no ring, and the old spinner is gone");
  globalThis.Avatars = A;
  try {
    const ringed = states();
    assert.match(ringed.working, /<span class="avact" data-who="asha" data-act="work" data-avid="fd-latest"><svg class="fdface"/);
    assert.match(ringed.working, /<b class="fdlh">Asha is on it<\/b><p class="fdline">Setting up your project…<\/p>/);
    assert.match(ringed.asking, /<header class="fdhead"><span class="avact" data-who="asha" data-act="ask" data-badge="ask"><svg class="fdface"/);
    assert.match(ringed.asking, /Asha needs one answer/);
    assert.match(ringed.ready, /<span class="avact" data-who="asha" data-act="done" data-badge="done" data-avid="fd-latest">/);
    assert.match(ringed.ready, /Your project is set up/);
    assert.match(ringed.update, /<span class="avact" data-who="asha" data-badge="msg" data-avid="fd-latest">/);
    assert.match(ringed.update, /<b class="fdlh">Asha says<\/b>/);
    const strip = html => html.replace(/<span class="avact"[^>]*>(<svg[\s\S]*?<\/svg>)<\/span>/g, "$1");
    for (const k of Object.keys(plain)) assert.equal(strip(ringed[k]), plain[k], k + ": the ring wraps the face and changes nothing else");
  } finally { delete globalThis.Avatars; }
});

test("while a run is going and the page marks nobody busy, the arc is around Asha; once someone is marked, or she asks, it is not", () => {
  const p = page("{}", {face: () => "", renderSimple: () => "", isReady: () => false});
  const acts = () => p.mates.map(m => m.host.dataset.act || "-").join(" ");
  p.mates.push(mate("asha", ""), mate("mira", ""), mate("nora", ""));
  p.sandbox.renderSimple({status: "running", allChat: []});
  assert.equal(acts(), "work - -", "the request is being read: nobody is marked, so it is the lead's work");
  p.sandbox.renderSimple({status: "waiting", allChat: []});
  assert.equal(acts(), "- - -", "nothing is running");
  p.mates.length = 0;
  p.mates.push(mate("asha", ""), mate("mira", "busy"));
  p.sandbox.renderSimple({status: "running", allChat: []});
  assert.equal(acts(), "- work", "Mira is at work: the arc is hers alone");
  p.mates.length = 0;
  p.mates.push(mate("asha", "ask"), mate("mira", ""));
  p.sandbox.renderSimple({status: "running", allChat: []});
  assert.equal(acts(), "ask -", "a question for the owner outranks the arc");
});
