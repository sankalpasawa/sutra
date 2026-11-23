/* budget_chip.js - the Budget chip (D257): what one run may use, in dollars (API price), on the home box and the team page's start form.

   A pill beside Go reads "$20 budget ▾". It opens a popover above it (an overlay: the row under it never moves) titled "Run budget": one row of
   pills, half, the default (tagged "default"), double and Custom, and the line "Asks before going over · estimated at API prices, not billed."
   Picked, the Custom pill itself becomes the box ("$", placeholder "amount"), in the same place in the row, and applies as you type; a bad amount
   marks the box (aria-invalid) and shows a short line under the row (aria-describedby), and changes nothing. A click outside or Esc closes it.
   A choice goes with the next request only (`usd_budget`), then the chip shows the default again. Nothing is sent for the default.

     fmt(x)                      "$20", "$12.50"
     parse(text)                 "$12.50", "12.5", "12" -> the number of dollars from 1 to 10000 with at most two decimals, else null
     presets(def)                [half, def, double], to the cent
     chipHtml(value)             the pill's words: "$20 budget ▾"
     popHtml(o)                  the popover: {def, shown, custom, typed, open, id}
     mount(el, def, source)      draws the chip in `el` and wires it; -> {value() (the chosen dollars, null for the default), reset()};
                                 source "team" ("team default") or "default" ("default") names the default for a screen reader
     raiseHtml(suggested, attrs) the raise input of a dollar question: the suggested amount filled in, "Add and keep going" (its button carries
                                 `attrs`, written by code: `data-raise` on the team page), and "API price, estimated"
     raiseFromText(text)         the suggested dollars of a question's continue option, read from its "[adds $Z]" tail; null when there is none

   Its look is `.bchip*` in sutra-panel.css (both pages link it). A classic script with ONE global, BudgetChip; in node it is module.exports. */
(function (root) {
  "use strict";

  const MIN = 1, MAX = 10000;
  const NOTE = "Asks before going over · estimated at API prices, not billed.";
  const SOURCES = {team: "team default", default: "default", request: "this request"};
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const cents = x => Math.round(x * 100) / 100;
  const BAD = "Dollars from $1 to $10,000";
  const bads = t => parse(t) === null && String(t || "").trim() !== "";   // typed, and not an amount
  let uid = 0;

  function fmt(x) {
    const n = cents(Number(x) || 0);
    return "$" + (Number.isInteger(n) ? n.toLocaleString("en-US") : n.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2}));
  }

  function parse(text) {
    const s = String(text === undefined || text === null ? "" : text).trim().replace(/^\$\s*/, "").replace(/,/g, "");
    if (!/^\d{1,5}(\.\d{1,2})?$/.test(s)) return null;
    const n = Number(s);
    return n >= MIN && n <= MAX ? n : null;
  }

  const presets = def => [cents(def / 2), cents(def), cents(def * 2)];

  const chipHtml = value => esc(fmt(value)) + ' budget <span class="bchipcaret" aria-hidden="true">&#9662;</span>';

  // o: {def, shown (the dollars in force), custom (Custom is picked), typed (the Custom box's text), open, id}
  function popHtml(o) {
    const [half, def, double] = presets(o.def), on = !o.custom && cents(o.shown), bad = !!o.custom && bads(o.typed);
    const pick = (n, words) => '<button type="button" class="bchippick" data-usd="' + n + '" aria-pressed="' + (on === n) + '">' + words + "</button>";
    return '<div class="bchippop" id="' + esc(o.id) + '" role="dialog" aria-label="Run budget"' + (o.open ? "" : " hidden") + ">" +
      '<p class="bchiptitle">Run budget</p><div class="bchiprow" role="group" aria-label="Budget for this request">' +
      pick(half, esc(fmt(half))) + pick(def, esc(fmt(def)) + ' <small class="bchiptag">default</small>') + pick(double, esc(fmt(double))) +
      (o.custom ? '<label class="bchipcustom"><span aria-hidden="true">$</span><input class="bchipown" inputmode="decimal" autocomplete="off" ' +
        'placeholder="amount" value="' + esc(o.typed || "") + '" aria-label="Another amount, in dollars"' +
        (bad ? ' aria-invalid="true" aria-describedby="' + esc(o.id) + 'err"' : "") + "></label>"
        : '<button type="button" class="bchippick" data-custom="1" aria-pressed="false">Custom</button>') +
      "</div>" + (o.custom ? '<p class="bchiperr" id="' + esc(o.id) + 'err"' + (bad ? "" : " hidden") + ">" + BAD + "</p>" : "") +
      '<p class="bchipnote">' + esc(NOTE) + "</p></div>";
  }

  // Draws the chip in `el` (a <span>) and wires it. `def` is the team's own budget (GET /api/engine/settings, effective.usd_budget); the chip is
  // only drawn once that is known, never with a placeholder. Focus goes into the popover when it opens and back to the pill when Esc or a pick closes it.
  function mount(el, def, source) {
    const id = "bchippop" + (++uid);
    let chosen = null, open = false, custom = false, typed = "";
    const shown = () => chosen === null ? def : chosen;
    const label = () => fmt(shown()) + " budget, " + (SOURCES[chosen === null ? source : "request"] || SOURCES.default);
    const focus = sel => { const f = el.querySelector && el.querySelector(sel); if (f && f.focus) f.focus(); };
    const draw = () => {
      el.innerHTML = '<span class="bchip"><button type="button" class="bchippill" aria-haspopup="dialog" aria-expanded="' + open + '" aria-controls="' + id +
        '" aria-label="' + esc(label() + ", API price") + '">' + chipHtml(shown()) + "</button>" +
        popHtml({def, shown: shown(), custom, typed, open, id}) + "</span>";
    };
    const shut = back => { open = false; draw(); if (back) focus(".bchippill"); };
    const take = n => { chosen = n === def ? null : n; };
    el.addEventListener("click", e => {
      const b = e.target.closest && e.target.closest("button");
      if (!b || !el.contains(b)) return;
      if (b.dataset.usd) { custom = false; typed = ""; take(Number(b.dataset.usd)); return shut(true); }
      if (b.dataset.custom) { custom = true; draw(); return focus(".bchipown"); }
      if (b.classList.contains("bchippill")) {
        open = !open; draw();
        focus(open ? (custom ? ".bchipown" : '.bchippick[aria-pressed="true"]') : ".bchippill");
      }
    });
    // Custom applies as you type: a good amount is the choice at once (the pill follows), a bad one marks the box and changes nothing
    el.addEventListener("input", e => {
      const box = e.target;
      if (!box || !box.classList || !box.classList.contains("bchipown")) return;
      typed = box.value;
      const n = parse(typed), bad = bads(typed), err = el.querySelector && el.querySelector(".bchiperr");
      if (bad) { box.setAttribute("aria-invalid", "true"); box.setAttribute("aria-describedby", id + "err"); }
      else { box.removeAttribute("aria-invalid"); box.removeAttribute("aria-describedby"); }
      box.setCustomValidity(bad ? BAD : "");
      if (err) err.hidden = !bad;
      if (n === null) return;
      take(n);
      const pill = el.querySelector(".bchippill");
      if (pill) { pill.innerHTML = chipHtml(shown()); pill.setAttribute("aria-label", label() + ", API price"); }
    });
    el.addEventListener("keydown", e => {
      if (!open) return;
      if (e.key === "Escape") { e.preventDefault(); return shut(true); }
      if (e.key === "Enter" && e.target && e.target.classList && e.target.classList.contains("bchipown")) {
        e.preventDefault();                                     // the team page's chip sits in its start form: Enter here never sends the request
        if (e.target.getAttribute("aria-invalid") === "true") return e.target.reportValidity();
        shut(true);
      }
    });
    // A click anywhere else closes it. The path is the one of the click itself: a redraw has already replaced the node that was clicked.
    const doc = el.ownerDocument;
    if (doc) doc.addEventListener("click", e => {
      if (!open) return;
      const path = e.composedPath ? e.composedPath() : [];
      if (path.indexOf(el) < 0 && !el.contains(e.target)) shut(false);
    });
    draw();
    return {value: () => chosen, reset: () => { chosen = null; custom = false; typed = ""; open = false; draw(); }};
  }

  function raiseHtml(suggested, attrs) {
    return '<div class="bchipraise" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0">' +
      '<input class="bchipraisein" inputmode="decimal" value="' + esc(fmt(suggested)) + '" aria-label="Dollars to add (API price)" style="width:7em">' +
      '<button type="button" class="pri" ' + (attrs || "data-raise") + ">Add and keep going</button>" +
      '<small class="bchipapi" style="opacity:.65">API price, estimated</small></div>';
  }

  function raiseFromText(text) {
    const m = /\[adds \$([\d,]+(?:\.\d{1,2})?)\]/.exec(String(text === undefined || text === null ? "" : text));
    return m ? parse(m[1]) : null;
  }

  const BudgetChip = {fmt, parse, presets, chipHtml, popHtml, mount, raiseHtml, raiseFromText, NOTE};
  if (typeof module === "object" && module !== null && module.exports) module.exports = BudgetChip;
  else root.BudgetChip = BudgetChip;
})(globalThis);
