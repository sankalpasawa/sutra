#!/usr/bin/env node
/*
 * test_usage_account.js -- the Account card sits FIRST on Settings > Usage.
 *
 * Founder ask (2026-08-25): which Claude account the panel runs on, before
 * how much of it is used. Source-level assertions, like test_update_banner.js:
 * cruder than a DOM, but they fail on the change that demotes the card below
 * the limits, drops the "not reported" rendering, or stops loading the account
 * alongside the usage windows.
 *
 * Run: node test_usage_account.js
 */
const fs = require("fs");
const path = require("path");
const screens = fs.readFileSync(path.join(__dirname, "static/js/04-screens.js"), "utf8");
const boot = fs.readFileSync(path.join(__dirname, "static/js/08-boot.js"), "utf8");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m); };

const usageStart = screens.indexOf("SCREENS.usage = () =>");
const usageEnd = screens.indexOf("SCREENS.git = () =>", usageStart);
const usageBody = screens.slice(usageStart, usageEnd);

test("the usage screen renders the account fold", () => {
  assert(usageStart > 0 && usageEnd > usageStart, "could not isolate SCREENS.usage");
  assert(usageBody.includes("accountFold()"), "SCREENS.usage does not call accountFold()");
  assert(screens.includes('fold("usage.account"'), "no usage.account fold");
});

test("the account comes BEFORE the plan limits", () => {
  const acct = usageBody.indexOf("accountFold()");
  const limits = usageBody.indexOf('fold("usage.limits"');
  assert(acct >= 0 && limits > acct, "account fold is not ahead of the limits fold");
});

test("every early return still carries the account", () => {
  const returns = usageBody.match(/return `[^`]*`/g) || [];
  assert(returns.length >= 4, "expected the four return branches, found " + returns.length);
  returns.forEach(r => assert(r.includes("${acct}"), "a return branch drops the account: " + r.slice(0, 60)));
});

test("absent fields render as 'not reported', never as a placeholder", () => {
  assert(screens.includes("not reported"), "no 'not reported' rendering");
  assert(!/accountHtml[\s\S]*?"unknown@|example\.com/.test(screens), "a placeholder identity leaked into the card");
});

test("the plan shows raw values beside a friendly name, or instead of one", () => {
  assert(screens.includes("p.plan || rawPlan"), "raw plan values are not the fallback");
});

test("loadUsage reads /api/account on its own route", () => {
  const i = boot.indexOf("async function loadUsage");
  const body = boot.slice(i, boot.indexOf("render();", i));
  assert(body.includes('apiGet("/api/account")'), "loadUsage does not fetch /api/account");
  assert(body.includes('apiGet("/api/usage")'), "loadUsage no longer fetches /api/usage");
  assert(body.indexOf('apiGet("/api/account")') < body.indexOf('apiGet("/api/usage")'),
         "account should load first");
});

/* ── the spend cap is money, and money has units ────────────────────────────
   The live payload carries monthly_limit=2000 next to decimal_places=2 and an
   explicit spend.limit of {amount_minor:2000, currency:"USD", exponent:2} --
   twenty dollars. The panel printed the bare 2000 with no currency, so a $20
   cap read as a $2000 one. Confirmed against the real cache on this machine. */
function loadSpendLimitText(){
  const m = screens.match(/function spendLimitText[\s\S]*?\n}/);
  assert(m, "spendLimitText is gone from 04-screens.js");
  // eslint-disable-next-line no-eval
  return eval("(" + m[0].replace(/^function /, "function ") + ")");
}

test("the monthly cap renders as money, from the payload's own units", () => {
  const f = loadSpendLimitText();
  assert(f({monthly_limit: 2000, decimal_places: 2, currency: "USD"},
      {spend: {limit: {amount_minor: 2000, currency: "USD", exponent: 2}}}) === "20.00 USD",
         "got " + JSON.stringify(f({monthly_limit: 2000, decimal_places: 2, currency: "USD"},
      {spend: {limit: {amount_minor: 2000, currency: "USD", exponent: 2}}})) + " want " + "20.00 USD");
});

test("it falls back to monthly_limit + decimal_places when spend is absent", () => {
  const f = loadSpendLimitText();
  assert(f({monthly_limit: 2000, decimal_places: 2, currency: "USD"}, {}) === "20.00 USD",
         "got " + JSON.stringify(f({monthly_limit: 2000, decimal_places: 2, currency: "USD"}, {})) + " want " + "20.00 USD");
});

test("a bare number is never rendered as the cap", () => {
  const f = loadSpendLimitText();
  const out = f({monthly_limit: 2000, decimal_places: 2, currency: "USD"}, {});
  assert(!/^2000/.test(out), "the raw minor-unit figure reached the screen: " + out);
});

test("no cap says so rather than showing zero", () => {
  const f = loadSpendLimitText();
  assert(f({monthly_limit: null}, {}) === "no limit set",
         "got " + JSON.stringify(f({monthly_limit: null}, {})) + " want " + "no limit set");
});

test("the server passes the units through", () => {
  const py = fs.readFileSync(path.join(__dirname, "usage.py"), "utf8");
  assert(/"decimal_places":/.test(py), "decimal_places must reach the client");
  assert(/"spend":/.test(py), "the explicit spend object must reach the client");
});

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
