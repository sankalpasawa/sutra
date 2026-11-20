/* budget_chip.js - the Budget chip (D257): what one run may use, in dollars (API price), on the home box and the team page's start form.

   "Budget: $20 API price (team default) · change" opens a small menu: half, the default, double, or a typed amount; then
   "The team stops and asks you before going over." and "API price, estimated. Runs use your Claude subscription; nobody is billed this amount."
   A choice goes with the next request only (`usd_budget`), then the chip shows the default again. Nothing is sent for the default.

     fmt(x)                      "$20", "$12.50"
     parse(text)                 "$12.50", "12.5", "12" -> the number of dollars from 1 to 10000 with at most two decimals, else null
     presets(def)                [half, def, double], to the cent
     chipHtml({value, source})   the chip's line; source "team" ("team default"), "default" ("default") or "request" ("this request")
     menuHtml(value)             the four choices and the two lines
     mount(el, def, source)      draws the chip in `el` and wires it; -> {value() (the chosen dollars, null for the default), reset()}

   A classic script with ONE global, BudgetChip; in node it is module.exports. Every amount on screen says "API price". */
(function (root) {
  "use strict";

  const MIN = 1, MAX = 10000;
  const STOPS = "The team stops and asks you before going over.";
  const NOT_BILLED = "API price, estimated. Runs use your Claude subscription; nobody is billed this amount.";
  const SOURCES = {team: "team default", default: "default", request: "this request"};
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const cents = x => Math.round(x * 100) / 100;

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

  function chipHtml(o) {
    const value = o && Number.isFinite(o.value) ? o.value : null;
    const source = SOURCES[o && o.source] || SOURCES.default;
    return '<summary class="bchipline" aria-label="Budget, API price">Budget: <b>' + esc(value === null ? "" : fmt(value)) +
      '</b> <small class="bchipapi" style="opacity:.65">API price</small> (' + esc(source) + ") &middot; change</summary>";
  }

  function menuHtml(value) {
    const [half, def, double] = presets(value);
    const pick = (n, label) => '<button type="button" class="bchippick" data-usd="' + n + '">' + esc(label) + "</button>";
    return '<div class="bchipmenu" role="group" aria-label="Budget for this request" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:6px 0">' +
      pick(half, fmt(half)) + pick(def, fmt(def) + " (default)") + pick(double, fmt(double)) +
      '<label style="display:flex;gap:4px;align-items:center">Other <input class="bchipown" inputmode="decimal" placeholder="$" aria-label="Another amount, in dollars" style="width:6em"></label>' +
      '<button type="button" class="bchipuse">Use</button>' +
      '<p class="bchipnote" style="flex-basis:100%;margin:2px 0;font-size:12px">' + esc(STOPS) + "</p>" +
      '<p class="bchipnote" style="flex-basis:100%;margin:0;font-size:12px;opacity:.75">' + esc(NOT_BILLED) + "</p></div>";
  }

  // Draws the chip in `el` (a <span>) and wires it. `def` is the team's own budget (GET /api/engine/settings, effective.usd_budget); the chip is
  // only drawn once that is known, never with a placeholder. A bad typed amount marks the input and changes nothing.
  function mount(el, def, source) {
    let chosen = null;
    const draw = () => {
      const shown = chosen === null ? def : chosen;
      el.innerHTML = '<details class="bchip" style="display:inline-block;font-size:13px">' + chipHtml({value: shown, source: chosen === null ? source : "request"}) +
        menuHtml(def) + "</details>";
    };
    const take = n => { chosen = n === def ? null : n; draw(); };
    el.addEventListener("click", e => {
      const b = e.target.closest && e.target.closest("button");
      if (!b || !el.contains(b)) return;
      if (b.dataset.usd) return take(Number(b.dataset.usd));
      if (b.classList.contains("bchipuse")) {
        const box = el.querySelector(".bchipown"), n = parse(box && box.value);
        if (n === null) {
          if (box) { box.setAttribute("aria-invalid", "true"); box.setCustomValidity("Dollars from $1 to $10,000"); box.reportValidity(); }
          return;
        }
        take(n);
      }
    });
    draw();
    return {value: () => chosen, reset: () => { chosen = null; draw(); }};
  }

  const BudgetChip = {fmt, parse, presets, chipHtml, menuHtml, mount, STOPS, NOT_BILLED};
  if (typeof module === "object" && module !== null && module.exports) module.exports = BudgetChip;
  else root.BudgetChip = BudgetChip;
})(globalThis);
