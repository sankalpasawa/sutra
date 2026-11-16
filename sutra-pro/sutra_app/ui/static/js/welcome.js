/* welcome.js - the first-run welcome card of Home (gap package welcome-settings, item 1; the old app's onboarding dialog, on live readings).

   Strings in, strings out, plus one small mount that touches the DOM through a `doc` the caller hands in (so `node --test` drives all of it with a
   fake). Nothing here runs by itself: home.js calls `Welcome.start(doc, api)` once from boot().

     welcomeHtml(facts) -> html          the dialog box (mount puts it in the full-screen #swelcome): four numbered facts, every value a reading of this machine (GET /api/ops/welcome): which model can
                                         answer (a provider that cannot shows its reason and the doctor's fix line, never the word "Ready"), where the
                                         data lives with its size and free space and the backup command, what leaves the machine, what runs alone
     humanBytes(n) -> "12.3 MB"          sizes in words ("unknown" for a number that is not one)
     load(api) -> Promise<{seen, facts}|null>   GET /api/ops/welcome; any failure is null (a card must never break the page)
     acknowledge(api) -> Promise<boolean>       POST /api/ops/welcome/seen (the token travels in SutraCtx.api); the owner's "Got it", stored on the server
     mount(doc, facts, api) -> {el, gotIt, notNow, close}   the card, mounted on <body> OUTSIDE #sview (a re-render of Home cannot tear it down):
                                         role=dialog aria-modal, focus goes to "Got it", Tab stays inside, Esc is "Not now". "Not now" removes the card
                                         for this page load only and writes nothing anywhere (no server call, no storage). "Got it" removes it and
                                         asks the server to remember; a write that fails still closes the card (the owner did say it).
     start(doc, api) -> Promise<controller|null>  load, then mount when the owner has not said Got it and there are facts to show

   Every word from the wire goes through esc(). The copy never says an API key is used: Sutra refuses one (D34). A classic script with ONE global,
   Welcome; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const NAMES = Object.freeze({claude: "Claude", codex: "Codex", stub: "The built-in stub"});
  const nameOf = n => (Object.prototype.hasOwnProperty.call(NAMES, n) ? NAMES[n] : clean(n));

  function humanBytes(n) {
    if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return "unknown";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = n;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
    return (i === 0 ? String(Math.round(v)) : v.toFixed(1)) + " " + units[i];
  }

  /* ---------------------------------------------------------------- the four facts */
  function modelRow(m) {
    const name = nameOf(m.name);
    if (m.state === "ready") return '<li class="swmodel" data-state="ready"><b>' + esc(name) + '</b> <span class="swchip st-ok">Ready</span></li>';
    if (m.state === "stub") return '<li class="swmodel" data-state="stub"><b>' + esc(name) + '</b> <span class="swwhy">' + esc(clean(m.why)) + "</span></li>";
    const fix = clean(m.fix);
    return '<li class="swmodel" data-state="' + esc(m.state === "blocked" ? "blocked" : "not_ready") + '"><b>' + esc(name) + '</b> <span class="swchip st-bad">' +
      (m.state === "blocked" ? "Waiting" : "Cannot answer") + '</span> <span class="swwhy">' + esc(clean(m.why)) + "</span>" +
      (fix ? '<span class="swfix">To fix it: <code>' + esc(fix) + "</code></span>" : "") + "</li>";
  }

  function modelsFact(models) {
    const rows = (Array.isArray(models) ? models : []).filter(isObj);
    const answering = rows.some(m => m.state === "ready" || m.state === "stub");
    const head = rows.length === 0 ? "Sutra could not read which models are installed on this machine."
      : (answering ? "These models can answer on this machine:" : "Nothing can answer yet. Until one of these is set up, a message will not get a reply:");
    return '<p>' + esc(head) + "</p>" + (rows.length ? '<ul class="swmodels">' + rows.map(modelRow).join("") + "</ul>" : "");
  }

  function dataFact(data) {
    const d = isObj(data) ? data : {};
    const where = clean(d.dir);
    return "<p>" + (where ? 'Everything lives in one folder: <code class="swdir">' + esc(where) + "</code>." : "Everything lives in one folder on this computer.") + "</p>" +
      "<p>The database is " + esc(humanBytes(d.db_bytes)) + "; " + esc(humanBytes(d.free_bytes)) + " is free on that disk." +
      (clean(d.backup) ? " Back it up any time with <code>" + esc(clean(d.backup)) + "</code>." : "") + "</p>";
  }

  function egressFact(egress) {
    const e = isObj(egress) ? egress : {};
    return "<p>Your messages go only to the Claude or Codex program on this computer, signed in with your own subscription. Sutra never uses an API key " +
      "and refuses one if it finds it.</p>" +
      (e.scrub === false ? "" : "<p>Anything shaped like a key, token or password is removed from a chat message before it leaves. A team's own prompts go out as written, " +
        "so keep keys out of a brief: Sutra only notes, without the text, that one was seen. No usage data is sent to Sutra.</p>") +
      updateFact(e.auto_update);
  }

  // The automatic update check (gap package autoupdate): what it asks, how often, and where it is switched off. Absent from an older server's answer: no paragraph.
  function updateFact(auto) {
    if (!isObj(auto)) return "";
    if (auto.on !== true) return "<p>The automatic check for a newer Sutra Pro is switched off (Settings, About). Sutra Pro then asks GitHub for releases only when you press Check for updates.</p>";
    return "<p>The Sutra Pro desktop app asks GitHub for the list of Sutra Pro releases about a minute after it opens and every 6 hours. It is one request, and nothing about you or your files is sent. " +
      "If a newer version is found it is downloaded only to be checked, and installed only when you say so. You can turn this off in Settings, About. " +
      "The command line and a browser-only start never check by themselves" + (auto.desktop === false ? ", and this copy was not started by the desktop app, so it makes no automatic check" : "") + ".</p>";
  }

  function autonomyFact(a) {
    const x = isObj(a) ? a : {};
    const budget = Number.isFinite(x.budget) ? "inside a budget of " + x.budget + " work credits for each run" : "inside a budget for each run";
    const mail = x.send_mode === "live" ? "Emails a team writes are sent for real (you can change that in Settings, Engine)."
      : (x.send_mode === "dry-run" ? "Emails a team writes are drafts only: nothing is sent." : "");
    return "<p>Teams plan and work by themselves " + esc(budget) + ". When one needs a decision or hits a limit it asks you in the " +
      "<b>Needs you</b> strip and waits; it does not guess." + "</p>" + (mail ? "<p>" + esc(mail) + "</p>" : "");
  }

  function welcomeHtml(facts) {
    const f = isObj(facts) ? facts : {};
    const step = (n, title, body) => '<section class="swfact"><h3><span class="swnum" aria-hidden="true">' + n + "</span> " + esc(title) + "</h3>" + body + "</section>";
    return '<div class="swbox" role="dialog" aria-modal="true" aria-labelledby="swtitle" tabindex="-1">' +
      '<h2 id="swtitle">Welcome to Sutra</h2><p class="swlead">Four things to know before your first message. The first two were read from this computer just now.</p>' +
      step(1, "Which model answers", modelsFact(f.models)) + step(2, "Where your files are", dataFact(f.data)) +
      step(3, "What leaves this computer", egressFact(f.egress)) + step(4, "What Sutra does alone, and what it asks", autonomyFact(f.autonomy)) +
      '<div class="swacts"><button type="button" class="ghost swgot" data-act="welcome-gotit">Got it</button>' +
      '<button type="button" class="linkbtn swlater" data-act="welcome-later">Not now</button>' +
      '<span class="sethint">Got it hides this for good. Not now hides it until you reload.</span></div></div>';
  }

  /* ---------------------------------------------------------------- the server half */
  async function load(api) {
    try {
      const answer = await api.get("/api/ops/welcome");
      return isObj(answer) && typeof answer.seen === "boolean" ? {seen: answer.seen, facts: isObj(answer.facts) ? answer.facts : null} : null;
    } catch (e) {
      return null;
    }
  }

  async function acknowledge(api) {
    try {
      const answer = await api.post("/api/ops/welcome/seen", {});
      return isObj(answer) && answer.seen === true;
    } catch (e) {
      return false;
    }
  }

  /* ---------------------------------------------------------------- the card */
  function mount(doc, facts, api) {
    const el = doc.createElement("div");
    el.id = "swelcome";
    el.className = "swelcome";
    el.innerHTML = welcomeHtml(facts);
    const before = doc.activeElement || null;
    let open = true;
    const close = () => {
      if (!open) return false;
      open = false;
      if (el.parentNode) el.parentNode.removeChild(el);
      if (before && typeof before.focus === "function") { try { before.focus(); } catch (e) { /* the element is gone */ } }
      return true;
    };
    const notNow = () => close();                       // this load only: nothing is written anywhere
    const gotIt = async () => {
      if (!open) return false;
      const ok = await acknowledge(api);
      close();
      return ok;
    };
    const focusables = () => Array.from(el.querySelectorAll("button"));
    el.addEventListener("click", e => {
      const b = e.target && e.target.closest ? e.target.closest("button[data-act]") : null;
      if (!b) return;
      if (b.dataset.act === "welcome-gotit") gotIt();
      else if (b.dataset.act === "welcome-later") notNow();
    });
    el.addEventListener("keydown", e => {
      if (e.key === "Escape") { e.preventDefault(); notNow(); return; }
      if (e.key !== "Tab") return;
      const list = focusables();
      if (list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      const active = doc.activeElement;
      if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
    });
    doc.body.appendChild(el);
    const primary = el.querySelector('[data-act="welcome-gotit"]');
    // the card is read from its top: focusing "Got it" (at the bottom) must not scroll the heading out of view
    if (primary && typeof primary.focus === "function") primary.focus({preventScroll: true});
    return {el, gotIt, notNow, close, isOpen: () => open};
  }

  async function start(doc, api) {
    const answer = await load(api);
    if (answer === null || answer.seen || answer.facts === null) return null;
    return mount(doc, answer.facts, api);
  }

  const Welcome = {welcomeHtml, humanBytes, load, acknowledge, mount, start};
  if (typeof module === "object" && module !== null && module.exports) module.exports = Welcome;
  else root.Welcome = Welcome;
})(globalThis);
