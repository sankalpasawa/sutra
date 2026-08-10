/* 10-activity.js — the global "Activity" panel.
 *
 * Sutra's equivalent of Claude Code's "Background tasks": ONE floating panel,
 * docked bottom-right, that shows all currently-running work live.
 *   - a running chat TURN  (Sutra spawns a `claude` process per turn, so an
 *     in-flight turn IS a running background process), and
 *   - a running AGENT      (a subagent doing agentic work).
 *
 * Data comes from GET /api/activity, polled every 2s. "Running" there is
 * transcript liveness == active (age <= 45s) — the same rule the SSE stream and
 * the log tail use. Stopwatches tick client-side every 1s between polls for
 * smooth counting, reseeded from elapsed_s on each poll.
 *
 * Self-contained by necessity: this module cannot touch panel.html or
 * panel.css, so it builds its own DOM on load and injects its own <style> once.
 * Classic script — shares the page globals (esc, S) with 01–09; everything it
 * adds is IIFE-scoped or `act`-prefixed. Fail-soft throughout: a fetch error is
 * a quiet "—", never a thrown interval callback, never a stacked timer.
 */
(function () {
  "use strict";
  if (window.__actMounted) return;   // double-inject guard (script loaded twice)
  window.__actMounted = true;

  var POLL_MS = 2000;
  var TICK_MS = 1000;

  var actState = { turns: [], agents: [], polledAt: 0, collapsed: false, error: false };
  var actPollTimer = null;
  var actTickTimer = null;
  var actEls = {};   // cached DOM refs

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

  // ---- style (inject once) -------------------------------------------------
  function actInjectStyle() {
    if (document.getElementById("act-style")) return;
    var css = "" +
      "#act-panel{position:fixed;right:16px;bottom:16px;z-index:9000;width:300px;max-width:calc(100vw - 32px);" +
      "font-family:var(--sans,system-ui,-apple-system,sans-serif);color:var(--ink,#f5f0e8);" +
      "background:var(--surface,#161412);border:1px solid var(--line,#2a2622);border-radius:var(--r,10px);" +
      "box-shadow:var(--shadow,0 1px 2px rgba(0,0,0,.16),0 18px 44px -18px rgba(0,0,0,.42));" +
      "overflow:hidden;font-size:12px;transition:opacity .18s ease}" +
      "#act-panel.act-idle{opacity:.82}" +
      "#act-head{display:flex;align-items:center;gap:8px;padding:9px 10px;cursor:default;" +
      "border-bottom:1px solid var(--line-soft,#221f1c);background:var(--card,#1c1a17)}" +
      "#act-panel.act-collapsed #act-head{border-bottom:0}" +
      "#act-dot{width:8px;height:8px;border-radius:50%;background:var(--faint,#6e6860);flex:0 0 auto}" +
      "#act-panel.act-live #act-dot{background:var(--ok,#5a9e6f);box-shadow:0 0 0 0 var(--ok,#5a9e6f);animation:act-pulse 1.8s ease-out infinite}" +
      "@keyframes act-pulse{0%{box-shadow:0 0 0 0 rgba(90,158,111,.45)}70%{box-shadow:0 0 0 6px rgba(90,158,111,0)}100%{box-shadow:0 0 0 0 rgba(90,158,111,0)}}" +
      "#act-title{font-weight:600;letter-spacing:.01em;flex:0 0 auto}" +
      "#act-count{min-width:18px;text-align:center;padding:1px 6px;border-radius:999px;font-size:11px;font-weight:600;" +
      "background:var(--acc-bg,rgba(196,149,106,.12));color:var(--acc,#c4956a)}" +
      "#act-panel.act-idle #act-count{background:transparent;color:var(--faint,#6e6860)}" +
      "#act-spacer{flex:1 1 auto}" +
      "#act-toggle{appearance:none;background:transparent;border:0;color:var(--muted,#8c857d);cursor:pointer;" +
      "font-size:12px;line-height:1;padding:4px 6px;border-radius:6px}" +
      "#act-toggle:hover{color:var(--ink,#f5f0e8);background:var(--acc-bg,rgba(196,149,106,.12))}" +
      "#act-toggle:focus-visible{outline:2px solid var(--acc,#c4956a);outline-offset:1px}" +
      "#act-body{max-height:min(46vh,340px);overflow-y:auto;padding:6px}" +
      "#act-panel.act-collapsed #act-body{display:none}" +
      ".act-item{display:block;padding:7px 8px;border-radius:8px}" +
      ".act-item + .act-item{margin-top:2px}" +
      ".act-item:hover{background:var(--acc-bg,rgba(196,149,106,.10))}" +
      ".act-row1{display:flex;align-items:baseline;gap:8px}" +
      ".act-name{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}" +
      ".act-time{flex:0 0 auto;font-family:var(--mono,ui-monospace,Menlo,monospace);font-size:11px;color:var(--acc,#c4956a);" +
      "font-variant-numeric:tabular-nums}" +
      ".act-meta{margin-top:1px;color:var(--muted,#8c857d);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
      ".act-meta .act-kind{color:var(--faint,#6e6860)}" +
      ".act-idle-pill{display:inline-block;padding:5px 10px;border-radius:999px;color:var(--muted,#8c857d);" +
      "background:var(--inset,#161412);font-size:11px}" +
      ".act-err{color:var(--faint,#6e6860);padding:6px 8px}";
    var st = document.createElement("style");
    st.id = "act-style";
    st.textContent = css;
    document.head.appendChild(st);
  }

  // ---- DOM build (once) ----------------------------------------------------
  function actBuild() {
    if (document.getElementById("act-panel")) return;
    var panel = document.createElement("div");
    panel.id = "act-panel";
    panel.className = "act-idle";
    panel.setAttribute("role", "region");
    panel.setAttribute("aria-label", "Activity — running work");

    var head = document.createElement("div");
    head.id = "act-head";
    var dot = document.createElement("span"); dot.id = "act-dot";
    var title = document.createElement("span"); title.id = "act-title"; title.textContent = "Activity";
    var count = document.createElement("span"); count.id = "act-count"; count.textContent = "0";
    var spacer = document.createElement("span"); spacer.id = "act-spacer";
    var toggle = document.createElement("button");
    toggle.id = "act-toggle";
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-controls", "act-body");
    toggle.setAttribute("aria-label", "Collapse activity panel");
    toggle.textContent = "▾";
    head.appendChild(dot); head.appendChild(title); head.appendChild(count);
    head.appendChild(spacer); head.appendChild(toggle);

    var body = document.createElement("div");
    body.id = "act-body";

    panel.appendChild(head); panel.appendChild(body);
    document.body.appendChild(panel);

    toggle.addEventListener("click", actToggle);

    actEls = { panel: panel, count: count, body: body, toggle: toggle };
  }

  function actToggle() {
    actState.collapsed = !actState.collapsed;
    actEls.panel.classList.toggle("act-collapsed", actState.collapsed);
    actEls.toggle.setAttribute("aria-expanded", actState.collapsed ? "false" : "true");
    actEls.toggle.setAttribute("aria-label",
      actState.collapsed ? "Expand activity panel" : "Collapse activity panel");
    actEls.toggle.textContent = actState.collapsed ? "▸" : "▾";
  }

  // ---- render --------------------------------------------------------------
  function actRender() {
    if (!actEls.panel) return;
    var turns = actState.turns || [], agents = actState.agents || [];
    var count = turns.length + agents.length;

    actEls.count.textContent = String(count);
    actEls.panel.classList.toggle("act-idle", count === 0);
    actEls.panel.classList.toggle("act-live", count > 0);

    // Header stays informative while collapsed; skip the body work.
    if (actState.collapsed) return;

    if (actState.error && count === 0) {
      actEls.body.innerHTML = '<div class="act-err">—</div>';
      return;
    }
    if (count === 0) {
      actEls.body.innerHTML = '<span class="act-idle-pill">No active work</span>';
      return;
    }

    var html = "";
    for (var i = 0; i < turns.length; i++) {
      var t = turns[i];
      var name = t.title || t.sid || "(session)";
      var meta = actBase(t.cwd) || t.sid || "";
      html += actItemHTML("turn", name, meta, t.elapsed_s);
    }
    for (var j = 0; j < agents.length; j++) {
      var a = agents[j];
      var an = a.label || a.id || "(agent)";
      var am = "in " + actShortSid(a.parent_sid);
      html += actItemHTML("agent", an, am, a.elapsed_s);
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

  // Tick only the stopwatch text, so persistent rows keep counting smoothly
  // between polls without re-rendering (and without losing scroll/hover).
  function actTick() {
    if (!actEls.body || actState.collapsed || !actState.polledAt) return;
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
        // Keep the last-known rows if we have them; otherwise show a quiet dash.
        actState.error = true;
        actRender();
      });
  }

  // ---- lifecycle -----------------------------------------------------------
  function actStart() {
    actInjectStyle();
    actBuild();
    actRender();
    actPoll();                       // immediate, don't wait a full interval
    if (actPollTimer) clearInterval(actPollTimer);
    if (actTickTimer) clearInterval(actTickTimer);
    actPollTimer = setInterval(actPoll, POLL_MS);
    actTickTimer = setInterval(actTick, TICK_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", actStart, { once: true });
  } else {
    actStart();
  }
})();
