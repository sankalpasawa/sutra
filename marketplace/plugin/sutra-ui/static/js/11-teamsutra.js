/* 11-teamsutra.js — the Ask Sutra selection bubble.

   Select text anywhere in the panel and a small button appears beside it;
   clicking it opens a chat already briefed with the department the selection
   belongs to. This module OWNS only the selection layer — the seeded chat it
   opens lives in 03-org.js (openTeamsutraChat), the same shape as Balance's.

   Built on the 10-activity.js pattern, the one precedent in this codebase for
   a component that does not participate in render(): IIFE, double-inject
   guard, self-injected <style>, a node on document.body (render() rewrites
   #panes wholesale on every streaming token — anything inside it is destroyed
   constantly), delegated document listeners, DOMContentLoaded self-start, and
   a module-owned Escape handler exactly like actOnKey.

   DEPARTMENT RESOLUTION IS DOM-FIRST AND NEVER GUESSED. The resolver walks up
   from the selection's Range.commonAncestorContainer — not from the mouseup
   target, which can land on chrome the selection never touched. When nothing
   resolves, the answer is null and the bubble says "no department": a wrong
   address is the exact failure the placement layer exists to remove.

   Known dead zone, by construction: the terminal and preview panes are
   <iframe>s — separate documents this listener cannot see into. */
(function () {
  "use strict";
  if (window.__tsMounted) return;      // double-inject guard
  window.__tsMounted = true;

  var tsEl = null;                     // the bubble node, mounted once on body
  var tsCurrent = null;                // {text, domainRef, domainLabel, screen, sessionId}

  // ---- style ---------------------------------------------------------------
  function tsInjectStyle() {
    if (document.getElementById("ts-style")) return;
    var st = document.createElement("style");
    st.id = "ts-style";
    st.textContent =
      "#ts-bubble{position:fixed;z-index:60;display:none;align-items:center;gap:6px;" +
      "background:var(--acc);color:var(--on-acc);border:none;border-radius:7px;" +
      "padding:5px 10px;font:600 12px var(--sans);cursor:pointer;" +
      "box-shadow:0 8px 22px -8px rgba(0,0,0,.45)}" +
      "#ts-bubble .ts-dept{font-weight:400;opacity:.75;max-width:180px;overflow:hidden;" +
      "text-overflow:ellipsis;white-space:nowrap}" +
      "#ts-bubble:focus-visible{outline:2px solid var(--ink);outline-offset:2px}";
    document.head.appendChild(st);
  }

  // ---- chrome exclusion ----------------------------------------------------
  /* A selection that starts or ends inside interactive chrome is not prose the
     user is asking about. The list is everything the recon named: composer
     inputs, buttons, menus, popovers, the rail, the side chat, the activity
     drawer, and this bubble itself. */
  var TS_CHROME = "input, textarea, select, button, .smenu, .upop, nav.rail, " +
                  ".composer, .sidewrap, #act-drawer, #ts-bubble";
  function tsInChrome(node) {
    if (!node) return true;
    var el = node.nodeType === 1 ? node : node.parentElement;
    return !el || !!(el.closest && el.closest(TS_CHROME));
  }

  // ---- department resolution ----------------------------------------------
  /* Walk up from `el`. Order matters: per-turn provenance first (a chat
     session holds MANY placements; the pane header only reflects the LAST
     turn, so the pane is never consulted), then the org surfaces where
     identity is real DOM, then charter rows. [data-ref] is trusted only on
     the departments screen — the same attribute appears on routing-chart
     nodes inside chat, where it means something else. */
  function tsResolve(el) {
    if (!el) return null;
    var t = el.closest && el.closest("[data-turn-domain]");
    if (t && t.getAttribute("data-turn-domain")) {
      return { ref: t.getAttribute("data-turn-domain"), kind: "turn" };
    }
    if (typeof S !== "undefined" && S.screen === "departments") {
      var d = el.closest && el.closest("[data-ref]");
      if (d && d.getAttribute("data-ref")) {
        return { ref: d.getAttribute("data-ref"), kind: "tile" };
      }
    }
    var dir = el.closest && el.closest('[id^="dir-"]');
    if (dir) return { ref: dir.id.slice(4), kind: "directory" };
    var ch = el.closest && el.closest("[data-charter]");
    if (ch && ch.getAttribute("data-charter")) {
      return { charter: ch.getAttribute("data-charter"), kind: "charter" };
    }
    return null;                       // honest null — never S.sel guesswork
  }

  function tsLabelFor(res) {
    if (!res) return "no department";
    if (res.charter) return "charter " + res.charter.slice(0, 10);
    try {
      if (typeof byRef === "function") {
        var d = byRef(res.ref);
        if (d && d.name) {
          return (typeof dPath === "function" ? dPath(res.ref) + " " : "") + d.name;
        }
      }
    } catch (e) { /* resolution stays best-effort; the ref alone is still true */ }
    return res.ref;
  }

  // ---- show / hide ---------------------------------------------------------
  function tsBuild() {
    if (tsEl) return;
    tsEl = document.createElement("button");
    tsEl.id = "ts-bubble";
    tsEl.type = "button";
    tsEl.setAttribute("aria-label", "Ask Sutra about the selected text");
    document.body.appendChild(tsEl);
    tsEl.addEventListener("click", tsAsk);
  }

  function tsHide() {
    tsCurrent = null;
    if (tsEl) tsEl.style.display = "none";
  }

  function tsShowFor(sel) {
    var text = String(sel.toString() || "").trim();
    if (!text || text.length < 3) { tsHide(); return; }
    var range;
    try { range = sel.getRangeAt(0); } catch (e) { tsHide(); return; }
    var anchor = range.commonAncestorContainer;
    if (tsInChrome(anchor)) { tsHide(); return; }
    var el = anchor.nodeType === 1 ? anchor : anchor.parentElement;
    var res = tsResolve(el);
    var rect = range.getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) { tsHide(); return; }
    tsCurrent = {
      text: text.slice(0, 4000),
      domainRef: res && res.ref ? res.ref : null,
      charterId: res && res.charter ? res.charter : null,
      domainLabel: tsLabelFor(res),
      screen: (typeof S !== "undefined" && S.screen) || null,
      sessionId: (function () {
        var p = el && el.closest && el.closest(".pane[data-sess]");
        return p ? p.getAttribute("data-sess") : null;
      })(),
    };
    tsBuild();
    tsEl.innerHTML = "&#9679; Ask Sutra <span class=\"ts-dept\"></span>";
    tsEl.querySelector(".ts-dept").textContent = tsCurrent.domainLabel;
    /* Below the selection, clamped to the viewport. position:fixed, so the
       rect's viewport coordinates are used as-is. */
    var x = Math.max(8, Math.min(rect.left, window.innerWidth - 220));
    var y = Math.min(rect.bottom + 8, window.innerHeight - 44);
    tsEl.style.left = x + "px";
    tsEl.style.top = y + "px";
    tsEl.style.display = "inline-flex";
  }

  // ---- events --------------------------------------------------------------
  /* mouseup + a deferred read: the selection object is not final until after
     the event settles. Also fires on dblclick word-select (which ends in a
     mouseup) and keyboard selection via the selectionchange fallback below. */
  function tsOnMouseUp(e) {
    if (e.target && e.target.closest && e.target.closest("#ts-bubble")) return;
    setTimeout(function () {
      var sel = window.getSelection && window.getSelection();
      if (!sel || sel.isCollapsed) { tsHide(); return; }
      tsShowFor(sel);
    }, 0);
  }
  function tsOnSelectionChange() {
    /* Keyboard selection (Shift+Arrow) never fires mouseup. Only the
       COLLAPSE path hides eagerly here; showing stays on keyup/mouseup so
       the bubble does not flicker while a drag is still in progress. */
    var sel = window.getSelection && window.getSelection();
    if (!sel || sel.isCollapsed) tsHide();
  }
  function tsOnKeyUp(e) {
    if (e.key !== "Shift" && !(e.key && e.key.indexOf("Arrow") === 0)) return;
    var sel = window.getSelection && window.getSelection();
    if (sel && !sel.isCollapsed) tsShowFor(sel);
  }
  function tsOnKey(e) {
    if ((e.key === "Escape" || e.key === "Esc") && tsCurrent) tsHide();
  }

  // ---- the ask -------------------------------------------------------------
  function tsAsk() {
    if (!tsCurrent) return;
    var ctx = tsCurrent;
    tsHide();
    if (typeof window.openTeamsutraChat === "function") {
      window.openTeamsutraChat(ctx);
    } else if (typeof console !== "undefined" && console.warn) {
      /* 03-org.js not loaded or predates this module — say so rather than
         silently doing nothing. */
      console.warn("[teamsutra] openTeamsutraChat is not available; selection kept:", ctx.text.slice(0, 80));
    }
  }

  // ---- lifecycle -----------------------------------------------------------
  function tsStart() {
    tsInjectStyle();
    document.addEventListener("mouseup", tsOnMouseUp);
    document.addEventListener("selectionchange", tsOnSelectionChange);
    document.addEventListener("keyup", tsOnKeyUp);
    document.addEventListener("keydown", tsOnKey);
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", tsStart, { once: true });
    } else {
      tsStart();
    }
  }

  /* Exposed for the test harness only. */
  window.__tsResolve = tsResolve;
  window.__tsInChrome = tsInChrome;
})();
