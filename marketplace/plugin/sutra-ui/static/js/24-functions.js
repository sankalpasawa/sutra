/* 24-functions.js -- the department's five functions, all at once: the All five overview (PRD M1.8, screen S2).

   The five as one system: what each is doing, who it waits on, what it spends today, and its last act, so the owner
   sees in one look who holds the turn and whether anything needs them. Built on the decision log's default for MK-8
   ("build as the PRD specifies"). It registers no destination: 22-website.js's viewer hands its "five" tab here, and
   20-dept.js's list column carries the All five row; 19-org2.js's strip carries the compact progress line, which
   opens it (S4, compact form).

   It reads the five functions' read (functions_view.py, through 22-website.js wbFv) and the board (wbLoadBoard), and
   writes nothing: every card is a way into a pane, never a write. Arrow keys move between the cards; Enter opens one.

   Copy discipline is the department screen's: names, never paths; no counts at rest (a bar, never a number); status
   never by colour alone (a word or a badge goes with it); every class prefixed `fv` has a rule in panel.css, tokens
   only (test_website.js M1.8). */

const FV_ORDER = ["identity", "adaptation", "priority", "coordination", "audit"];
/* each function's purpose, in a line (PRD S2) */
const FV_PURPOSE = {
  identity: "hears you, keeps the goal and the rules",
  adaptation: "proposes the work the goal needs",
  priority: "prices the work, holds the budget",
  coordination: "says who goes first, one at a time",
  audit: "reads the result against done-when"
};
const FV_DOT = { working: "breath", waiting: "wait", waiting_on_you: "warn", fault: "block", quiet: "off" };
const FV_PILL = { done: "done", now: "now", next: "next", skipped: "skip" };

function fvName(fn){ return fn.charAt(0).toUpperCase() + fn.slice(1); }
/* the cycle in words, in full (S4): the words, eight step pills, and the rounds once there are any */
function fvProgressHtml(cyc){
  if (!cyc) return "";
  const done = cyc.state === "done";
  const words = (cyc.round ? "Round " + cyc.round + " · " : "") + (cyc.says || "");
  const mark = done ? wbDot("ok") : (cyc.state === "stopped" ? wbDot("off") : `<i class="dpdot breath" aria-hidden="true"></i>`);
  const pills = (cyc.steps || []).map(p => {
    const k = FV_PILL[p.state] || "next", tick = k === "done" ? "✓ " : (k === "skip" ? "- " : "");
    const tip = p.last ? [p.name, p.last.summary, wbWhen(p.last.at)].filter(Boolean).join(" · ") : p.name;
    return `<span class="fvpill ${k}" title="${wbEsc(tip)}">${k === "now" ? `<i class="dpdot breath" aria-hidden="true"></i>` : ""}${wbEsc(tick + p.name)}</span>`;
  }).join("");
  const ceiling = cyc.ceiling && cyc.ceiling.rounds ? Number(cyc.ceiling.rounds) : 0;
  const rounds = cyc.round && ceiling ? `<span class="fvrounds" title="${wbEsc("Round " + cyc.round + " of " + ceiling)}">` +
    Array.from({ length: ceiling }, (_, i) => `<i class="${i + 1 < cyc.round ? "on" : (i + 1 === cyc.round ? "now" : "")}"></i>`).join("") + `</span>` : "";
  return `<div class="fvprog wb"><div class="fvsays">${mark}<b aria-live="polite">${wbEsc(words)}</b>` +
    (cyc.needs_you ? `<span class="wbchip ask">needs you</span>` : "") + `</div>` +
    (pills ? `<div class="fvpills">${pills}</div>` : "") + rounds + `</div>`;
}
/* one function's strip: what later milestones add for each; today the plan (Adaptation) and the line with the
   engine that has the turn (Coordination), off the Map's own read */
function fvStrip(fn, m){
  const engs = (m && m.engines) || [];
  if (!engs.length) return "";
  if (fn === "adaptation") return `<div class="wbstep fvstripe">${engs.map(e => wbChip(e.name)).join("")}</div>`;
  if (fn === "coordination"){
    const run = ((m.status && m.status.running) || []).map(r => r.engine);
    return `<div class="wbstep fvstripe">${engs.map(e => wbChip(e.name, run.indexOf(e.name) >= 0 ? "on" : "")).join("")}</div>`;
  }
  return "";
}
function fvCardHtml(node, m, stopped){
  const fn = node.fn, name = node.name || fvName(fn);
  /* the read's own word, the one the Map, the list and the pane print: 'stopped' on every card of a stopped department */
  const word = stopped ? "stopped" : (node.word || node.state);
  const dot = stopped ? "off" : (FV_DOT[node.state] || "off");
  const badge = node.state === "waiting_on_you" ? "?" : (node.state === "fault" ? "!" : "");
  let now;
  if (node.state === "waiting_on_you") now = `<span class="wbchip ask" data-wbtab="chat">waits on you</span> ${wbEsc(node.line || "")}`;
  else if (node.state === "waiting" && node.waits_on) now = `<span class="wbchip" ${node.waits_on === "Root" ? "" : `data-wbfn="${wbEsc(String(node.waits_on).toLowerCase())}"`}>waits on ${wbEsc(node.waits_on)}</span>`;
  else now = `<b>${wbEsc(word)}</b>${node.line || node.why ? ": " + wbEsc(node.why || node.line) : ""}`;
  const last = node.last ? `<div class="dpchk">last: ${wbEsc(node.last.what || "")}${node.last.at ? " · " + wbEsc(wbWhen(node.last.at)) : ""}</div>` : "";
  const spend = node.spend || {};
  return `<button type="button" class="fvcard fn-${wbEsc(fn)} wb${stopped ? " still" : ""}" data-wbfn="${wbEsc(fn)}" data-fvcard="${wbEsc(fn)}" ` +
    `aria-label="${wbEsc(name + " · " + word)}">` +
    `<span class="fvhead">${typeof wb2Mark === "function" ? wb2Mark(fn) : ""}<b>${wbEsc(name)}</b>` +
    (badge ? `<b class="dpfnb ${dot}" aria-hidden="true">${badge}</b>` : "") + `<i class="dpdot ${dot}" aria-hidden="true"></i></span>` +
    `<span class="fvpurpose">${wbEsc(FV_PURPOSE[fn] || "")}</span>` +
    `<span class="fvnow">${now}</span>` +
    `<span class="fvtoday"><span class="dpk">Today</span>${dpBar(Math.max(0, Math.min(1, Number(spend.share) || 0)))}</span>` +
    last + fvStrip(fn, m) + `</button>`;
}
/* cell six: the last three messages between the functions, from the board, and the way to all of them */
function fvBetweenHtml(ref){
  const st = wbS(), b = st.board[ref];
  if (!b) wbLoadBoard(ref);
  const names = FV_ORDER.map(fvName), posts = [];
  ((b && b.threads) || []).forEach(t => (t.posts || []).forEach(p => {
    if (names.indexOf(p.src) >= 0 && (p.dst || []).some(d => names.indexOf(d) >= 0)) posts.push(Object.assign({ thread: t.id }, p));
  }));
  posts.sort((a, c) => c.n - a.n);
  const rows = posts.slice(0, 3).map(p => `<button type="button" class="fvmsg wb" data-wbtab="board" data-wbthread="${wbEsc(p.thread)}">` +
    `<i class="fvbar fn-${wbEsc(String(p.src).toLowerCase())}"></i>${wbChip(p.src)}<span class="wbarrow">&rarr;</span>${wbChip((p.dst || []).join(", "))}` +
    `<span class="dpchk">${wbEsc(p.line || p.word || "")}</span></button>`).join("");
  return `<div class="fvcard fvbetween wb"><span class="fvhead"><b>Between them</b></span>` +
    (b ? (rows || dpQuiet("Nothing between them yet")) : dpSkel()) +
    `<button type="button" class="o2more wb" data-wbtab="board">All messages &rsaquo;</button></div>`;
}
/* the overview itself: the Map's head, the progress block, then the six cells */
function fvAllHtml(n, m){
  const fv = wbFv(n.ref), head = typeof wb2Head === "function" ? wb2Head(n, m) : "";
  if (fv === null) return head + `<div class="fvgrid">${FV_ORDER.map(() => `<div class="fvcard fvskel">${dpSkel()}</div>`).join("")}</div>`;
  if (!fv || fv.failed) return head + `<div class="fvgrid fverr">${dpQuiet("Could not read")}<button type="button" class="o2more wb" data-wbfvretry="1">Try again</button></div>`;
  const cyc = fv.cycle || {}, stopped = !!(fv.stopped || cyc.state === "stopped");
  let top = fvProgressHtml(cyc);
  if (cyc.state === "not_started")
    top = `<div class="fvprog wb"><div class="fvsays">${wbDot("off")}<b>Not started</b></div>` +
      `<div class="dpoffer"><button type="button" class="btn" data-dpj2start="1">Start</button></div></div>`;
  if (stopped)
    top = `<div class="fvprog wb"><div class="fvsays">${wbDot("off")}<b>Stopped by you</b></div>` +
      `<div class="dpoffer">${wbBtn("Start", `data-wbresume="1"`, "dpstamp")}</div></div>`;
  const nodes = FV_ORDER.map(fn => (fv.functions || []).filter(x => x.fn === fn)[0] || { fn, name: fvName(fn), state: "quiet", word: "quiet" });
  return head + top + `<div class="fvgrid" role="list">${nodes.map(x => fvCardHtml(x, m, stopped)).join("")}${fvBetweenHtml(n.ref)}</div>`;
}
/* S4, compact: the progress line in the department's strip, after the parent's name; it opens All five. It hides
   when there is no read, or the read failed. */
function fvStripHtml(ref){
  if (typeof wbFnView !== "function") return "";
  const fv = wbFnView(ref);
  if (!fv || fv.failed || !fv.cycle || !fv.cycle.says) return "";
  const c = fv.cycle, mark = c.state === "done" ? wbDot("ok") : (c.state === "stopped" ? wbDot("off") : `<i class="dpdot breath" aria-hidden="true"></i>`);
  return `<button type="button" class="fvline wb" data-wbtab="five">${mark}<span>${wbEsc((c.round ? "Round " + c.round + " · " : "") + c.says)}</span>` +
    (c.needs_you ? `<span class="wbchip ask">needs you</span>` : "") + `</button>`;
}

/* ── keys: the arrow keys move between the cards; Enter opens one (a card is a button) ─────────────────────────── */
if (typeof document !== "undefined" && document.addEventListener){
  document.addEventListener("keydown", (ev) => {
    const t = ev.target;
    if (!t || !t.dataset || t.dataset.fvcard === undefined || !t.closest) return;
    const dirs = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    if (!(ev.key in dirs)) return;
    const grid = t.closest(".fvgrid");
    const cards = grid && grid.querySelectorAll ? Array.prototype.slice.call(grid.querySelectorAll("[data-fvcard]")) : [];
    const i = cards.indexOf(t), next = cards[(i + dirs[ev.key] + cards.length) % (cards.length || 1)];
    if (next && next.focus){ ev.preventDefault(); next.focus(); }
  });
}
