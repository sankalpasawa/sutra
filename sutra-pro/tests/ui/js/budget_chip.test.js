"use strict";
// BudgetChip (sutra_app/ui/static/js/budget_chip.js), D257: the Budget chip in dollars (API price) on the home box and the team page:
// a pill ("$20 budget ▾") and a popover above it.
// Run with: node --test tests/ui/js/budget_chip.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const BC = require(path.resolve(__dirname, "../../../sutra_app/ui/static/js/budget_chip.js"));

test("format: whole dollars bare, cents to two places", () => {
  assert.equal(BC.fmt(20), "$20");
  assert.equal(BC.fmt(12.5), "$12.50");
  assert.equal(BC.fmt(1.25), "$1.25");
  assert.equal(BC.fmt(10000), "$10,000");
});

test("parse: dollars from 1 to 10000 with at most two decimals, with or without $", () => {
  for (const [t, n] of [["$12.50", 12.5], ["12.5", 12.5], ["12", 12], [" $ 20 ", 20], ["1", 1], ["10000", 10000], ["$1,000", 1000]]) assert.equal(BC.parse(t), n, t);
  for (const t of ["", "0", "0.99", "10001", "12.345", "abc", "-5", "1e3", null, undefined]) assert.equal(BC.parse(t), null, String(t));
});

test("presets: half, the default and double ($20 -> $10 / $20 / $40)", () => {
  assert.deepEqual(BC.presets(20), [10, 20, 40]);
  assert.deepEqual(BC.presets(25), [12.5, 25, 50]);
});

test("pill: the amount, then budget and a caret; no source text and no credits", () => {
  const text = html => html.replace(/<[^>]+>/g, "").replace(/&#9662;/g, "▾").replace(/\s+/g, " ").trim();
  assert.equal(text(BC.chipHtml(20)), "$20 budget ▾");
  assert.equal(text(BC.chipHtml(12.5)), "$12.50 budget ▾");
  assert.doesNotMatch(BC.chipHtml(20), /credit|default|change|▶/i);
});

test("popover: Run budget, $10 · $20 (default tag) · $40 · Custom, the one muted line", () => {
  const text = html => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  const html = BC.popHtml({def: 20, shown: 20, custom: false, open: true, id: "p1"});
  assert.match(html, /^<div class="bchippop" id="p1" role="dialog" aria-label="Run budget">/);
  assert.equal(text(html), "Run budget $10 $20 default $40 Custom Asks before going over · estimated at API prices, not billed.");
  assert.deepEqual([...html.matchAll(/data-usd="([^"]+)"/g)].map(m => m[1]), ["10", "20", "40"]);
  assert.deepEqual([...html.matchAll(/<button type="button" class="bchippick"[^>]*aria-pressed="(true|false)"/g)].map(m => m[1]), ["false", "true", "false", "false"]);
  assert.doesNotMatch(html, /bchipown|bchipuse|credit/i);                                  // no box until Custom, and no Use button ever
  assert.match(BC.popHtml({def: 20, shown: 20, custom: false, open: false, id: "p1"}), /aria-label="Run budget" hidden>/);
});

test("popover: a picked preset is the pressed one; Custom shows the $ box in the row with what was typed", () => {
  const pressed = html => [...html.matchAll(/class="bchippick" (?:data-usd="([^"]+)"|data-custom="1") aria-pressed="true"/g)].map(m => m[1] || "custom");
  assert.deepEqual(pressed(BC.popHtml({def: 20, shown: 40, custom: false, open: true, id: "p"})), ["40"]);
  const custom = BC.popHtml({def: 20, shown: 25, custom: true, typed: "25<", open: true, id: "p"});
  assert.deepEqual(pressed(custom), ["custom"]);
  assert.match(custom, /<div class="bchiprow"[^>]*>.*<label class="bchipcustom"><span aria-hidden="true">\$<\/span><input class="bchipown"[^>]*value="25&lt;"[^>]*><\/label><\/div>/);
});

test("mount: picks, Custom as you type (bad marks the box and changes nothing), reset; Esc closes", () => {
  // a small stand-in for the page: the delegated listeners get events whose target is a button or the box
  const on = {}, el = {innerHTML: "", addEventListener: (k, f) => { on[k] = f; }, contains: () => true, querySelector: () => null};
  const btn = data => ({dataset: data, classList: {contains: c => c === "bchippill" && data.pill}, closest() { return this; }});
  const chip = BC.mount(el, 20, "team");
  assert.match(el.innerHTML, /aria-expanded="false"/);
  assert.match(el.innerHTML, /aria-label="\$20 budget, team default, API price"/);
  on.click({target: btn({pill: true})});
  assert.match(el.innerHTML, /aria-expanded="true"/);
  assert.doesNotMatch(el.innerHTML, /role="dialog" aria-label="Run budget" hidden/);
  on.keydown({key: "Escape", preventDefault() {}});
  assert.match(el.innerHTML, /aria-expanded="false"/);
  on.click({target: btn({usd: "40"})});
  assert.equal(chip.value(), 40);
  on.click({target: btn({usd: "20"})});
  assert.equal(chip.value(), null);                                                     // the default is never sent
  on.click({target: btn({custom: "1"})});
  const attrs = {};
  const box = v => ({value: v, classList: {contains: c => c === "bchipown"}, setAttribute: (k, x) => { attrs[k] = x; }, removeAttribute: k => { delete attrs[k]; },
                     setCustomValidity: m => { attrs.validity = m; }});
  on.input({target: box("12.5")});
  assert.equal(chip.value(), 12.5);
  on.input({target: box("0.5")});
  assert.equal(chip.value(), 12.5);                                                     // a bad amount changes nothing
  assert.equal(attrs["aria-invalid"], "true");
  assert.equal(attrs.validity, "Dollars from $1 to $10,000");
  on.input({target: box("$1,000")});
  assert.equal(chip.value(), 1000);
  assert.equal(attrs["aria-invalid"], undefined);
  assert.match(el.innerHTML, /class="bchipown"/);                                       // the box stays in the row while it is typed in
  chip.reset();
  assert.equal(chip.value(), null);
  assert.match(el.innerHTML, /\$20 budget/);
  assert.doesNotMatch(el.innerHTML, /bchipown/);
});

test("raise input: the suggested dollars filled in, Add and keep going, the API price note", () => {
  const html = BC.raiseHtml(10);
  assert.match(html, /<input class="bchipraisein"[^>]*value="\$10"/);
  assert.match(html, /<button type="button" class="pri" data-raise>Add and keep going<\/button>/);
  assert.match(html, /API price, estimated/);
  assert.match(BC.raiseHtml(12.5, 'data-act="fd-raise" data-msg="7"'), /value="\$12\.50"[\s\S]*data-act="fd-raise" data-msg="7">Add and keep going/);
});

test("raiseFromText: the continue option's [adds $Z] tail, else null (a credits tail is not a dollar raise)", () => {
  const q = "This run has used $20.40 of $20 (API price). Add $10? So far: $20 approved.\n   Option 1: Add $10 and keep going: more [adds $10]\n   Option 2: Finish as it is";
  assert.equal(BC.raiseFromText(q), 10);
  assert.equal(BC.raiseFromText("Option 1: Add $1,250.50 [adds $1,250.50]"), 1250.5);
  assert.equal(BC.raiseFromText("Option 1: Add 30 work credits [adds 30 work credits]"), null);
  assert.equal(BC.raiseFromText(null), null);
});
