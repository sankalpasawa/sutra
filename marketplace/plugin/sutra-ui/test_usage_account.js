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

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
