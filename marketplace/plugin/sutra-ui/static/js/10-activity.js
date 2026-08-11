/* 10-activity.js — the global "Activity" drawer.
 *
 * Sutra's equivalent of Claude Code's "Background tasks". A trigger button sits in
 * each chat header's top-right (`[data-act-toggle]`, rendered by sessionPane in
 * 06-render.js, carrying an `[data-act-badge]` count). Clicking it opens a
 * right-docked drawer that lists all currently-running work:
 *   - a running chat TURN  (Sutra spawns a `claude` process per turn, so an
 *     in-flight turn IS a running background process), and
 *   - a running AGENT      (a subagent doing agentic work).
 *
 * Data: GET /api/activity, polled every 2s. "Running" == transcript liveness
 * active (age <= 45s), the same rule the SSE stream and the log tail use.
 * Stopwatches tick client-side every 1s between polls, reseeded from elapsed_s.
 *
 * The drawer is non-modal (watch activity while the chat streams); close it with
 * the ×, Escape, or by re-clicking a trigger. The trigger badge is re-synced every
 * tick, so it survives the panel's frequent re-renders without a render() hook.
 *
 * Self-contained by necessity: this module cannot edit panel.css, so it injects
 * its own <style> once and builds the drawer on load. Classic script — shares the
 * page globals (esc, S) with 01–09; everything it adds is IIFE-scoped or
 * `act`-prefixed. Loaded BEFORE 09-tail.js so boot() stays the final statement
 * (test 21b). Fail-soft: a fetch error is a quiet dash, never a thrown interval.
 */
(function () {
  "use strict";
  if (window.__actMounted) return;   // double-inject guard (script loaded twice)
  window.__actMounted = true;

  var POLL_MS = 2000;
  var TICK_MS = 1000;

  var actState = { turns: [], agents: [], polledAt: 0, open: false, error: false };
  var actPollTimer = null;
  var actTickTimer = null;
  var actEls = {};   // cached drawer DOM refs

  // ---- helpers -------------------------------------------------------------
  function actBase(p) {
    var s = String(p == null ? "" : p).replace(/[\/\\]+$/, "");
    var i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
    return i >= 0 ? s.slice(i + 1) : s;
  }
  function actShortSid(sid) {
    var s = String(sid == null ? "" : sid);
    return s.length > 8 ? s.slice(0, 8) : s;
  }
  function actMMSS(secs) {
    secs = Math.max(0, secs | 0);
    var m = Math.floor(secs / 60), s = secs % 60;
    return (m < 10 ? "0" + m : "" + m) + ":" + (s < 10 ? "0" + s : "" + s);
  }
  function actEsc(x) {
    // Prefer the page's shared escaper; degrade gracefully if load order shifts.
    return (typeof esc === "function") ? esc(x)
      : String(x == null ? "" : x).replace(/[&<>"]/g, function (m) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m];
      });
  }
  function actCount() { return (actState.turns || []).length + (actState.agents || []).length; }

  // ---- style (inject once) -------------------------------------------------
  function actInjectStyle() {
    if (document.getElementById("act-style")) return;
    var css = "" +
      /* trigger button badge — the button itself is a `.ib` in the pane header */
      ".act-trigger{position:relative}" +
      ".act-trigger .act-badge{margin-left:3px;min-width:15px;height:15px;padding:0 4px;border-radius:999px;" +
      "font-size:10px;line-height:15px;font-weight:700;text-align:center;font-variant-numeric:tabular-nums;" +
      "background:var(--acc,#c4956a);color:var(--surface,#161412)}" +
      ".act-trigger.act-live{color:var(--acc,#c4956a)}" +
      ".act-trigger.act-live .act-badge{animation:act-pulse 1.8s ease-out infinite}" +
      "@keyframes act-pulse{0%{box-shadow:0 0 0 0 rgba(196,149,106,.5)}70%{box-shadow:0 0 0 5px rgba(196,149,106,0)}100%{box-shadow:0 0 0 0 rgba(196,149,106,0)}}" +
      /* right-docked drawer */
      "#act-drawer{position:fixed;top:0;right:0;height:100vh;width:340px;max-width:88vw;z-index:9000;" +
      "display:flex;flex-direction:column;transform:translateX(100%);transition:transform .2s ease;" +
      "font-family:var(--sans,system-ui,-apple-system,sans-serif);color:var(--ink,#f5f0e8);font-size:12px;" +
      "background:var(--surface,#161412);border-left:1px solid var(--line,#2a2622);" +
      "box-shadow:-18px 0 48px -26px rgba(0,0,0,.55)}" +
      "#act-drawer.act-open{transform:translateX(0)}" +
      "#act-dhead{display:flex;align-items:center;gap:8px;padding:12px;border-bottom:1px solid var(--line-soft,#221f1c);" +
      "background:var(--card,#1c1a17)}" +
      "#act-ddot{width:8px;height:8px;border-radius:50%;background:var(--faint,#6e6860);flex:0 0 auto}" +
      "#act-drawer.act-live-h #act-ddot{background:var(--ok,#5a9e6f);box-shadow:0 0 0 0 var(--ok,#5a9e6f);animation:act-pulse2 1.8s ease-out infinite}" +
      "@keyframes act-pulse2{0%{box-shadow:0 0 0 0 rgba(90,158,111,.45)}70%{box-shadow:0 0 0 6px rgba(90,158,111,0)}100%{box-shadow:0 0 0 0 rgba(90,158,111,0)}}" +
      "#act-dtitle{font-weight:600;letter-spacing:.01em;flex:0 0 auto}" +
      "#act-dcount{min-width:18px;text-align:center;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600;" +
      "background:var(--acc-bg,rgba(196,149,106,.12));color:var(--acc,#c4956a)}" +
      "#act-drawer:not(.act-live-h) #act-dcount{background:transparent;color:var(--faint,#6e6860)}" +
      "#act-dspacer{flex:1 1 auto}" +
      "#act-dclose{appearance:none;background:transparent;border:0;color:var(--muted,#8c857d);cursor:pointer;" +
      "font-size:17px;line-height:1;padding:3px 8px;border-radius:6px}" +
      "#act-dclose:hover{color:var(--ink,#f5f0e8);background:var(--acc-bg,rgba(196,149,106,.12))}" +
      "#act-dclose:focus-visible{outline:2px solid var(--acc,#c4956a);outline-offset:1px}" +
      "#act-dbody{flex:1 1 auto;overflow-y:auto;padding:8px}" +
      ".act-sec{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint,#6e6860);margin:8px 6px 4px}" +
      ".act-sec:first-child{margin-top:2px}" +
      ".act-item{display:block;padding:8px;border-radius:8px}" +
      ".act-item + .act-item{margin-top:2px}" +
      ".act-item:hover{background:var(--acc-bg,rgba(196,149,106,.10))}" +
      ".act-row1{display:flex;align-items:baseline;gap:8px}" +
      ".act-name{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}" +
      ".act-time{flex:0 0 auto;font-family:var(--mono,ui-monospace,Menlo,monospace);font-size:11px;color:var(--acc,#c4956a);" +
      "font-variant-numeric:tabular-nums}" +
      ".act-meta{margin-top:2px;color:var(--muted,#8c857d);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
      ".act-meta .act-kind{color:var(--faint,#6e6860)}" +
      ".act-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:62%;gap:6px;" +
      "color:var(--muted,#8c857d);text-align:center}" +
      ".act-empty .act-emoji{font-size:20px;opacity:.4}" +
      ".act-err{color:var(--faint,#6e6860);padding:8px}";
    var st = document.createElement("style");
    st.id = "act-style";
    st.textContent = css;
    document.head.appendChild(st);
  }

  // ---- DOM build (once) ----------------------------------------------------
  function actBuild() {
    if (document.getElementById("act-drawer")) return;
    var d = document.createElement("aside");
    d.id = "act-drawer";
    d.setAttribute("role", "dialog");
    d.setAttribute("aria-label", "Activity — running work");
    d.setAttribute("aria-hidden", "true");

    var head = document.createElement("div"); head.id = "act-dhead";
    var dot = document.createElement("span"); dot.id = "act-ddot";
    var title = document.createElement("span"); title.id = "act-dtitle"; title.textContent = "Activity";
    var count = document.createElement("span"); count.id = "act-dcount"; count.textContent = "0";
    var spacer = document.createElement("span"); spacer.id = "act-dspacer";
    var close = document.createElement("button");
    close.id = "act-dclose"; close.type = "button";
    close.setAttribute("aria-label", "Close activity"); close.textContent = "×";
    close.addEventListener("click", actClose);
    head.appendChild(dot); head.appendChild(title); head.appendChild(count);
    head.appendChild(spacer); head.appendChild(close);

    var body = document.createElement("div"); body.id = "act-dbody";

    d.appendChild(head); d.appendChild(body);
    document.body.appendChild(d);

    actEls = { drawer: d, count: count, body: body };
  }

  // ---- open / close --------------------------------------------------------
  function actOpen() {
    if (!actEls.drawer) return;
    actState.open = true;
    actEls.drawer.classList.add("act-open");
    actEls.drawer.setAttribute("aria-hidden", "false");
    actRenderBody();
  }
  function actClose() {
    if (!actEls.drawer) return;
    actState.open = false;
    actEls.drawer.classList.remove("act-open");
    actEls.drawer.setAttribute("aria-hidden", "true");
  }
  function actToggle() { actState.open ? actClose() : actOpen(); }

  // ---- render --------------------------------------------------------------
  // Keep every header trigger's badge + the drawer header in sync with state.
  // Cheap enough to run each tick, so a fresh re-render is corrected within 1s.
  function actSyncTriggers() {
    var n = actCount(), live = n > 0;
    var trigs = document.querySelectorAll("[data-act-toggle]");
    for (var i = 0; i < trigs.length; i++) {
      trigs[i].classList.toggle("act-live", live);
      var b = trigs[i].querySelector("[data-act-badge]");
      if (b) { b.textContent = String(n); b.hidden = (n === 0); }
    }
    if (actEls.count) actEls.count.textContent = String(n);
    if (actEls.drawer) actEls.drawer.classList.toggle("act-live-h", live);
  }

  function actRenderBody() {
    if (!actEls.body) return;
    var turns = actState.turns || [], agents = actState.agents || [];
    var n = turns.length + agents.length;

    if (actState.error && n === 0) {
      actEls.body.innerHTML = '<div class="act-err">Couldn\'t reach the activity feed.</div>';
      return;
    }
    if (n === 0) {
      actEls.body.innerHTML = '<div class="act-empty"><div class="act-emoji">◯</div><div>No active work</div></div>';
      return;
    }
    var html = "";
    if (turns.length) {
      html += '<div class="act-sec">Running turns</div>';
      for (var i = 0; i < turns.length; i++) {
        var t = turns[i];
        html += actItemHTML("turn", t.title || t.sid || "(session)", actBase(t.cwd) || t.sid || "", t.elapsed_s);
      }
    }
    if (agents.length) {
      html += '<div class="act-sec">Agents</div>';
      for (var j = 0; j < agents.length; j++) {
        var a = agents[j];
        html += actItemHTML("agent", a.label || a.id || "(agent)", "in " + actShortSid(a.parent_sid), a.elapsed_s);
      }
    }
    actEls.body.innerHTML = html;
  }

  function actItemHTML(kind, name, meta, elapsedS) {
    var base = Math.max(0, elapsedS | 0);
    var kindLabel = kind === "turn" ? "turn" : "agent";
    return '<div class="act-item">' +
      '<div class="act-row1">' +
      '<span class="act-name">' + actEsc(name) + '</span>' +
      '<span class="act-time" data-base="' + base + '">' + actMMSS(base) + '</span>' +
      '</div>' +
      '<div class="act-meta"><span class="act-kind">' + kindLabel + '</span> · ' + actEsc(meta) + '</div>' +
      '</div>';
  }

  function actRender() {
    actSyncTriggers();
    if (actState.open) actRenderBody();
  }

  // Tick the stopwatches (only when the drawer is open) + keep badges fresh.
  function actTick() {
    actSyncTriggers();
    if (!actState.open || !actEls.body || !actState.polledAt) return;
    var drift = Math.floor((Date.now() - actState.polledAt) / 1000);
    if (drift < 0) drift = 0;
    var spans = actEls.body.querySelectorAll(".act-time");
    for (var i = 0; i < spans.length; i++) {
      var b = parseInt(spans[i].getAttribute("data-base"), 10) || 0;
      spans[i].textContent = actMMSS(b + drift);
    }
  }

  // ---- poll ----------------------------------------------------------------
  function actPoll() {
    fetch("/api/activity", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (d) {
        actState.turns = Array.isArray(d && d.turns) ? d.turns : [];
        actState.agents = Array.isArray(d && d.agents) ? d.agents : [];
        actState.polledAt = Date.now();
        actState.error = false;
        actRender();
      })
      .catch(function () {
        actState.error = true;
        actRender();
      });
  }

  // ---- event wiring (delegated, survives re-renders) -----------------------
  function actOnClick(e) {
    var t = e.target && e.target.closest ? e.target.closest("[data-act-toggle]") : null;
    if (t) { e.preventDefault(); actToggle(); }
  }
  function actOnKey(e) {
    if ((e.key === "Escape" || e.key === "Esc") && actState.open) actClose();
  }

  // ---- lifecycle -----------------------------------------------------------
  function actStart() {
    actInjectStyle();
    actBuild();
    actSyncTriggers();
    actPoll();                       // immediate, don't wait a full interval
    if (actPollTimer) clearInterval(actPollTimer);
    if (actTickTimer) clearInterval(actTickTimer);
    actPollTimer = setInterval(actPoll, POLL_MS);
    actTickTimer = setInterval(actTick, TICK_MS);
    document.addEventListener("click", actOnClick);
    document.addEventListener("keydown", actOnKey);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", actStart, { once: true });
  } else {
    actStart();
  }
})();
