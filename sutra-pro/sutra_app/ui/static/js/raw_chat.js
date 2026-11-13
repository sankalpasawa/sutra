/* raw_chat.js - the Raw AI chat debugger of a team's run (Sutra's own; not a J2 file, and J2's page is not edited for it).

   Every AI call a run makes is one line of its calls.jsonl: the system prompt, the prompt and the raw reply, with the function, step, model and cost.
   This view lists those calls (GET /api/calls, metadata and previews only) and, for the one picked, shows the exact text as a chat
   (GET /api/call?id=): SYSTEM folded, the PROMPT as the user turn, the RAW reply as the assistant turn, monospace, each with a Copy button.
   The search box filters the list on the full text (server side) and marks the words in the open call. While the run is going, the list grows on
   its own and the agents writing right now are shown on top with their text so far (GET /api/agent-live).

   Where it shows: a "Raw AI chat" button on the team page when the viewer level is Debug (localStorage "sutra:level" = "debug"), and always
   full screen at /d/<team>/raw[?run=<id>] (that path serves the team page; this script opens the viewer there).

   A classic script with ONE global, RawChat; in node it is module.exports (the pure parts are tested) and does not start by itself.
   dept_ext.js adds it to the team page. */
(function (root) {
  "use strict";

  const LEVEL_KEY = "sutra:level";
  const POLL_MS = 2000;
  const PAGE = 300;
  const RAW_PATH = /^\/d\/[^/]+\/raw\/?$/;
  const PEOPLE = {identity: ["Asha", "--s-asha"], audit: ["Nora", "--s-nora"], adaptation: ["Planner", "--s-kabir"],
    priority: ["Budget lead", "--s-mira"], coordination: ["Scheduler", "--s-mira"], validator: ["Gatekeeper", "--s-kabir"]};

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const str = v => (typeof v === "string" ? v : v === null || v === undefined ? "" : String(v));
  const esc = v => str(v).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  /* ---------------------------------------------------------------- pure parts */
  function isDebug(storage) {
    try {
      return (storage || root.localStorage).getItem(LEVEL_KEY) === "debug";
    } catch (e) {
      return false;
    }
  }

  const onRawPath = pathname => RAW_PATH.test(str(pathname));

  // Who made a call: a person of the studio for the agents that have one, "Builder W-n" for a workflow builder, else the function's own name.
  function personOf(fn) {
    const k = str(fn);
    if (PEOPLE[k]) return {name: PEOPLE[k][0], role: k, color: PEOPLE[k][1]};
    if (/^W-\d+$/.test(k)) return {name: "Builder " + k, role: "builder", color: "--s-dev"};
    return {name: k || "call", role: "", color: "--s-muted"};
  }

  function faceHtml(fn) {
    const p = personOf(fn);
    const letters = p.name.replace(/^Builder /, "").replace(/[^A-Za-z0-9]/g, "").slice(0, 2) || "?";
    return `<span class="rc-face" style="--rc-c:var(${p.color})" aria-hidden="true">${esc(letters)}</span>`;
  }

  function fmtTokens(tokens) {
    if (!isObj(tokens)) return "";
    const n = v => (typeof v === "number" ? (v >= 10000 ? Math.round(v / 1000) + "k" : String(v)) : "?");
    return n(tokens.input) + " in / " + n(tokens.output) + " out";
  }

  const fmtUsd = usd => (typeof usd === "number" ? "$" + (usd < 0.01 ? usd.toFixed(4) : usd.toFixed(3)) : "");
  const fmtChars = n => (typeof n === "number" ? (n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n)) + " chars" : "");

  function metaBits(c) {
    const bits = [];
    if (c.step !== undefined && c.step !== null) bits.push("step " + c.step + (c.cycle ? "." + c.cycle : ""));
    if (c.model) bits.push(c.model);
    const tk = fmtTokens(c.tokens);
    if (tk) bits.push(tk);
    else if (isObj(c.chars) && typeof c.chars.total === "number") bits.push(fmtChars(c.chars.total));
    if (fmtUsd(c.usd)) bits.push(fmtUsd(c.usd));
    return bits;
  }

  function rowHtml(c, selected) {
    const p = personOf(c.fn);
    return `<button type="button" class="rc-row${selected ? " on" : ""}" data-id="${esc(c.id)}" aria-pressed="${selected ? "true" : "false"}">` +
      faceHtml(c.fn) +
      `<span class="rc-rowmain"><span class="rc-rowtop"><b>${esc(p.name)}</b>${p.role && p.role !== p.name ? `<i>${esc(p.role)}</i>` : ""}` +
      `<span class="rc-num">#${esc(c.id)}</span>${c.t ? `<time>${esc(c.t)}</time>` : ""}</span>` +
      `<span class="rc-rowmeta">${esc(metaBits(c).join(" · "))}</span>` +
      `<span class="rc-prev">${esc(c.prompt_preview || c.reply_preview || "")}</span></span></button>`;
  }

  function liveRowHtml(name, entry, selected) {
    const p = personOf(name);
    return `<button type="button" class="rc-row rc-liverow${selected ? " on" : ""}" data-live="${esc(name)}">` + faceHtml(name) +
      `<span class="rc-rowmain"><span class="rc-rowtop"><b>${esc(p.name)}</b><span class="rc-livetag">writing now</span></span>` +
      `<span class="rc-rowmeta">${esc((entry.tool ? "tool " + entry.tool + " · " : "") + fmtChars(str(entry.text).length))}</span>` +
      `<span class="rc-prev">${esc(str(entry.text).slice(-140))}</span></span></button>`;
  }

  // The text of a turn, escaped, with every place that holds `needle` (case-insensitive) in <mark>.
  function markHtml(text, needle) {
    const t = str(text);
    const n = str(needle).trim();
    if (!n) return esc(t);
    const low = t.toLowerCase();
    const want = n.toLowerCase();
    let out = "";
    let at = 0;
    for (let i = low.indexOf(want); i >= 0; i = low.indexOf(want, at)) {
      out += esc(t.slice(at, i)) + "<mark>" + esc(t.slice(i, i + n.length)) + "</mark>";
      at = i + n.length;
    }
    return out + esc(t.slice(at));
  }

  function countOf(text, needle) {
    const n = str(needle).trim().toLowerCase();
    if (!n) return 0;
    const low = str(text).toLowerCase();
    let k = 0;
    for (let i = low.indexOf(n); i >= 0; i = low.indexOf(n, i + n.length)) k += 1;
    return k;
  }

  function turnHtml(kind, label, text, needle, open) {
    const body = `<pre class="rc-pre">${markHtml(text, needle)}</pre>`;
    const copy = `<button type="button" class="rc-copy" data-copy="${esc(kind)}" aria-label="Copy the ${esc(label.toLowerCase())}">Copy</button>`;
    const size = `<span class="rc-size">${esc(fmtChars(str(text).length))}</span>`;
    if (kind === "system") {
      return `<details class="rc-turn rc-system"${open ? " open" : ""}><summary><span class="rc-label">${esc(label)}</span>${size}${copy}</summary>${body}</details>`;
    }
    return `<section class="rc-turn rc-${esc(kind)}"><header><span class="rc-label">${esc(label)}</span>${size}${copy}</header>${body}</section>`;
  }

  // One call as a chat: the head (who, what, cost), then SYSTEM (folded unless the search is in it), PROMPT (user), RAW REPLY (assistant),
  // and the parsed reply and the reason the engine took from it.
  function transcriptHtml(rec, needle) {
    if (!isObj(rec)) return `<p class="rc-empty">Pick a call on the left to see the exact text the AI was sent and what it answered.</p>`;
    const p = personOf(rec.fn);
    const bits = metaBits(rec);
    if (rec.provider) bits.push(rec.provider);
    if (typeof rec.seconds === "number") bits.push(rec.seconds + " s");
    if (rec.t) bits.push(rec.t);
    if (rec.atom) bits.push("part " + rec.atom);
    const hits = ["system", "prompt", "raw"].reduce((n, k) => n + countOf(rec[k], needle), 0);
    const parsed = isObj(rec.reply) ? JSON.stringify(rec.reply, null, 2) : "";
    return `<header class="rc-head">${faceHtml(rec.fn)}<span class="rc-headmain"><b>${esc(p.name)}</b>` +
      `<span class="rc-headsub">call #${esc(rec.id)}${p.role && p.role !== p.name ? " · " + esc(p.role) : ""}</span>` +
      `<span class="rc-headmeta">${esc(bits.join(" · "))}</span></span>` +
      (str(needle).trim() ? `<span class="rc-hits" role="status">${hits} match${hits === 1 ? "" : "es"}</span>` : "") + `</header>` +
      turnHtml("system", "SYSTEM PROMPT", rec.system, needle, countOf(rec.system, needle) > 0) +
      turnHtml("prompt", "PROMPT", rec.prompt, needle) +
      turnHtml("raw", "RAW REPLY", rec.raw, needle) +
      (parsed ? `<details class="rc-turn rc-system"><summary><span class="rc-label">PARSED REPLY</span></summary><pre class="rc-pre">${esc(parsed)}</pre></details>` : "") +
      (rec.reason ? `<p class="rc-reason"><span class="rc-label">REASON</span> ${esc(rec.reason)}</p>` : "");
  }

  function liveHtml(name, entry, needle) {
    const p = personOf(name);
    return `<header class="rc-head">${faceHtml(name)}<span class="rc-headmain"><b>${esc(p.name)}</b>` +
      `<span class="rc-headsub">writing now${entry.call ? " · call " + esc(entry.call) : ""}${entry.tool ? " · tool " + esc(entry.tool) : ""}</span></span>` +
      `<span class="rc-livetag">live</span></header>` + turnHtml("raw", "REPLY SO FAR", entry.text, needle);
  }

  /* ---------------------------------------------------------------- the view */
  const S = {el: null, dept: "", run: "", runs: [], calls: [], matched: 0, total: 0, q: "", sel: null, rec: null, live: false, agents: {},
    timer: null, seq: 0, full: false, started: false};
  const doc = () => root.document || null;
  const ctx = () => root.SutraCtx || null;
  const $ = sel => (S.el ? S.el.querySelector(sel) : null);

  function api(path, query) {
    const c = ctx();
    if (!c || !c.api) return Promise.reject(new Error("no SutraCtx"));
    return c.api.get(path, Object.assign({dept: S.dept}, S.run ? {run: S.run} : {}, query || {}));
  }

  function shell() {
    const d = doc();
    const el = d.createElement("div");
    el.id = "rawchat";
    el.className = "rc";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "Raw AI chat");
    el.hidden = true;
    el.innerHTML =
      `<header class="rc-bar"><h2>Raw AI chat</h2><span class="rc-sub" id="rc-count"></span>` +
      `<label class="rc-field"><span class="rc-vh">Run</span><select id="rc-run" aria-label="Run"></select></label>` +
      `<label class="rc-field rc-search"><span class="rc-vh">Search</span><input id="rc-q" type="search" placeholder="Search prompts and replies" aria-label="Search prompts and replies"></label>` +
      `<span class="rc-livetag" id="rc-live" hidden>live</span>` +
      `<button type="button" class="rc-close" id="rc-close" aria-label="Close the Raw AI chat">Close</button></header>` +
      `<div class="rc-body"><nav class="rc-list" id="rc-list" aria-label="AI calls"></nav>` +
      `<article class="rc-chat" id="rc-chat" tabindex="-1"><button type="button" class="rc-back" id="rc-back">← All calls</button><div id="rc-text"></div></article></div>`;
    d.body.appendChild(el);
    return el;
  }

  function paintList() {
    const list = $("#rc-list");
    if (!list) return;
    const live = Object.keys(S.agents).map(n => liveRowHtml(n, S.agents[n], S.sel === "live:" + n)).join("");
    const rows = S.calls.map(c => rowHtml(c, S.sel === c.id)).join("");
    const more = S.calls.length < S.matched ? `<button type="button" class="rc-more" id="rc-more">Show more (${S.matched - S.calls.length} left)</button>` : "";
    const none = !rows && !live ? `<p class="rc-empty">${S.q ? "No call holds that text." : "No AI calls in this run yet."}</p>` : "";
    list.innerHTML = live + rows + more + none;
    const count = $("#rc-count");
    if (count) count.textContent = S.q ? `${S.matched} of ${S.total} calls` : `${S.total} call${S.total === 1 ? "" : "s"}`;
    const tag = $("#rc-live");
    if (tag) tag.hidden = !S.live;
  }

  function paintChat() {
    const box = $("#rc-text");
    if (!box) return;
    const liveName = typeof S.sel === "string" && S.sel.startsWith("live:") ? S.sel.slice(5) : "";
    box.innerHTML = liveName && S.agents[liveName] ? liveHtml(liveName, S.agents[liveName], S.q) : transcriptHtml(S.rec, S.q);
    S.el.classList.toggle("rc-picked", S.sel !== null);
  }

  async function loadRuns() {
    try {
      const got = await api("/api/runlist");
      S.runs = isObj(got) && Array.isArray(got.runs) ? got.runs : [];
    } catch (e) {
      S.runs = [];
    }
    const sel = $("#rc-run");
    if (!sel) return;
    const opts = [`<option value="">Current run</option>`].concat(S.runs.map(r =>
      `<option value="${esc(r.id)}">${esc((r.title || r.id) + (r.status === "running" ? " (running)" : ""))}</option>`));
    if (S.run && !S.runs.some(r => r.id === S.run)) opts.push(`<option value="${esc(S.run)}">${esc(S.run)}</option>`);
    sel.innerHTML = opts.join("");
    sel.value = S.run;
  }

  async function loadCalls(append) {
    const seq = ++S.seq;
    let got;
    try {
      got = await api("/api/calls", {q: S.q || undefined, offset: append ? S.calls.length : 0, limit: append ? PAGE : Math.max(PAGE, S.calls.length)});
    } catch (e) {
      if (seq === S.seq) $("#rc-list").innerHTML = `<p class="rc-empty">The calls could not be read: ${esc(e && e.message)}</p>`;
      return;
    }
    if (seq !== S.seq || !isObj(got)) return;
    const rows = Array.isArray(got.calls) ? got.calls : [];
    S.calls = append ? S.calls.concat(rows) : rows;
    S.matched = got.matched | 0;
    S.total = got.total | 0;
    S.live = got.live === true;
    paintList();
    schedule();
  }

  async function loadLive() {
    if (!S.live) {
      S.agents = {};
      return;
    }
    try {
      const got = await api("/api/agent-live");
      S.agents = isObj(got) && isObj(got.agents) ? got.agents : {};
    } catch (e) {
      S.agents = {};
    }
  }

  async function pick(id) {
    S.sel = id;
    paintList();
    if (typeof id === "string" && id.startsWith("live:")) {
      S.rec = null;
      paintChat();
      return;
    }
    let rec;
    try {
      rec = await api("/api/call", {id: id});
    } catch (e) {
      if (S.sel === id) {
        S.rec = null;
        $("#rc-text").innerHTML = `<p class="rc-empty">That call could not be read: ${esc(e && e.message)}</p>`;
      }
      return;
    }
    if (S.sel !== id) return;
    S.rec = rec;
    paintChat();
    const chat = $("#rc-chat");
    if (chat) chat.scrollTop = 0;
  }

  function schedule() {
    if (S.timer) root.clearTimeout(S.timer);
    S.timer = null;
    if (!S.live || !S.el || S.el.hidden) return;
    S.timer = root.setTimeout(async () => {
      S.timer = null;
      await loadLive();
      await loadCalls(false);
      if (typeof S.sel === "string") paintChat();        // a live agent's text so far
    }, POLL_MS);
  }

  function copyOf(kind) {
    const liveName = typeof S.sel === "string" && S.sel.startsWith("live:") ? S.sel.slice(5) : "";
    if (liveName) return str((S.agents[liveName] || {}).text);
    return isObj(S.rec) ? str(S.rec[kind]) : "";
  }

  function copy(btn) {
    const text = copyOf(btn.getAttribute("data-copy"));
    const done = ok => {
      btn.textContent = ok ? "Copied" : "Copy failed";
      root.setTimeout(() => { btn.textContent = "Copy"; }, 1400);
    };
    try {
      root.navigator.clipboard.writeText(text).then(() => done(true), () => done(false));
    } catch (e) {
      done(false);
    }
  }

  function wire() {
    const el = S.el;
    el.addEventListener("click", e => {
      const t = e.target;
      if (!t || typeof t.closest !== "function") return;
      const row = t.closest(".rc-row");
      if (row) {
        const live = row.getAttribute("data-live");
        pick(live ? "live:" + live : Number(row.getAttribute("data-id")));
        return;
      }
      const btn = t.closest(".rc-copy");
      if (btn) {
        e.preventDefault();
        copy(btn);
        return;
      }
      if (t.closest("#rc-more")) loadCalls(true);
      else if (t.closest("#rc-back")) { S.sel = null; paintList(); el.classList.remove("rc-picked"); }
      else if (t.closest("#rc-close")) close();
    });
    let typing = null;
    $("#rc-q").addEventListener("input", e => {
      S.q = e.target.value;
      if (typing) root.clearTimeout(typing);
      typing = root.setTimeout(() => { loadCalls(false); paintChat(); }, 250);
    });
    $("#rc-run").addEventListener("change", e => {
      S.run = e.target.value;
      S.sel = S.rec = null;
      S.agents = {};
      paintChat();
      loadCalls(false).then(loadLive).then(paintList);
    });
    el.addEventListener("keydown", e => {
      if (e.key === "Escape" && !S.full) close();
    });
  }

  function open(opts) {
    const d = doc();
    if (!d || !d.body) return false;
    const c = ctx();
    S.dept = c && typeof c.dept === "string" ? c.dept : "";
    if (!S.el) {
      S.el = shell();
      wire();
    }
    if (isObj(opts) && typeof opts.run === "string") S.run = opts.run;
    S.full = isObj(opts) && opts.full === true;
    S.el.classList.toggle("rc-full", S.full);
    const closeBtn = $("#rc-close");
    if (closeBtn) closeBtn.textContent = S.full ? "Back to team" : "Close";
    S.el.hidden = false;
    d.body.classList.add("rc-open");
    paintChat();
    loadRuns();
    loadCalls(false).then(loadLive).then(paintList);
    return true;
  }

  function close() {
    if (S.full) {
      root.location.href = "./" + (S.run ? "?run=" + encodeURIComponent(S.run) : "");
      return;
    }
    if (S.el) S.el.hidden = true;
    if (S.timer) root.clearTimeout(S.timer);
    S.timer = null;
    const d = doc();
    if (d && d.body) d.body.classList.remove("rc-open");
  }

  // The entry button: shown at the Debug level only, kept in step when the level changes (another tab, or the level switch's event).
  function button() {
    const d = doc();
    if (!d || !d.body) return null;
    let b = d.getElementById("rawchat-open");
    if (!b) {
      b = d.createElement("button");
      b.type = "button";
      b.id = "rawchat-open";
      b.className = "rc-open-btn";
      b.textContent = "Raw AI chat";
      b.title = "See the exact text of every AI call of this run";
      b.addEventListener("click", () => open({}));
      d.body.appendChild(b);
    }
    b.hidden = !isDebug();
    return b;
  }

  function init() {
    if (S.started) return false;
    S.started = true;
    button();
    root.addEventListener("storage", e => { if (!e || e.key === LEVEL_KEY) button(); });
    if (doc() && doc().addEventListener) doc().addEventListener("sutra:level", button);
    const loc = root.location || {};
    if (onRawPath(loc.pathname)) {
      let run = "";
      try {
        run = new URLSearchParams(loc.search || "").get("run") || "";
      } catch (e) {
        run = "";
      }
      open({full: true, run: /^j2-[\w-]+$/.test(run) ? run : ""});
    }
    return true;
  }

  const RawChat = {init, open, close, state: () => ({open: !!(S.el && !S.el.hidden), run: S.run, calls: S.calls.length, sel: S.sel, live: S.live}),
    helpers: {isDebug, onRawPath, personOf, fmtTokens, fmtUsd, rowHtml, liveRowHtml, transcriptHtml, markHtml, countOf, esc}};

  if (typeof module === "object" && module !== null && module.exports) {
    module.exports = RawChat;
  } else {
    root.RawChat = RawChat;
    const d = doc();
    if (d) {
      if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", init);
      else init();
    }
  }
})(globalThis);
