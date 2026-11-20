"use strict";
// BudgetChip (sutra_app/ui/static/js/budget_chip.js), D257: the Budget chip in dollars (API price) on the home box and the team page.
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

test("chip text: the amount, API price beside it, where it comes from, and change", () => {
  const text = html => html.replace(/<[^>]+>/g, "").replace(/&middot;/g, "·").replace(/\s+/g, " ").trim();
  assert.equal(text(BC.chipHtml({value: 20, source: "team"})), "Budget: $20 API price (team default) · change");
  assert.equal(text(BC.chipHtml({value: 20, source: "default"})), "Budget: $20 API price (default) · change");
  assert.equal(text(BC.chipHtml({value: 40, source: "request"})), "Budget: $40 API price (this request) · change");
  assert.doesNotMatch(BC.chipHtml({value: 20, source: "team"}), /credit/i);
});

test("menu: the three presets, another amount, and both lines", () => {
  const html = BC.menuHtml(20);
  assert.deepEqual([...html.matchAll(/data-usd="([^"]+)"/g)].map(m => m[1]), ["10", "20", "40"]);
  assert.match(html, /\$20 \(default\)/);
  assert.match(html, /class="bchipown"/);
  assert.match(html, /The team stops and asks you before going over\./);
  assert.match(html, /API price, estimated\. Runs use your Claude subscription; nobody is billed this amount\./);
  assert.doesNotMatch(html, /credit/i);
});
