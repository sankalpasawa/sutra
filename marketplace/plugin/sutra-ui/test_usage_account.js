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

test("every early return on the CLAUDE path still carries the account", () => {
  /* Scoped to the Claude path. The screen now returns earlier for the other
     two usage kinds -- DeepSeek's own screen, and a "nothing to report" for a
     provider that publishes neither a window nor a balance -- and NEITHER may
     carry accountFold(), which reads Anthropic's account. Requiring ${acct} on
     every return would demand exactly the bug this split fixes: Claude's
     identity rendered on someone else's screen. */
  const claudeBody = usageBody.slice(usageBody.indexOf("const acct = accountFold()"));
  const returns = claudeBody.match(/return `[^`]*`/g) || [];
  assert(returns.length >= 3, "expected the Claude return branches, found " + returns.length);
  returns.forEach(r => assert(r.includes("${acct}"), "a return branch drops the account: " + r.slice(0, 60)));
});

test("the non-Claude usage screens never render Claude's account", () => {
  const preClaude = usageBody.slice(0, usageBody.indexOf("const acct = accountFold()"));
  assert(/usageKindOf\(/.test(preClaude), "the screen no longer keys on the declared kind");
  assert(!/accountFold\(\)/.test(preClaude),
         "a non-Claude branch reaches accountFold(): " + preClaude.slice(0, 200));
  assert(/kind === "none"/.test(preClaude),
         "a provider with no usage concept has no branch, so it falls into Claude's");
});

test("absent fields render as 'not reported', never as a placeholder", () => {
  assert(screens.includes("not reported"), "no 'not reported' rendering");
  assert(!/accountHtml[\s\S]*?"unknown@|example\.com/.test(screens), "a placeholder identity leaked into the card");
});

test("the plan shows raw values beside a friendly name, or instead of one", () => {
  assert(screens.includes("p.plan || rawPlan"), "raw plan values are not the fallback");
});

/* Counting render() calls to find the branches broke the moment a third
   branch was added. Brace-match the function instead, then slice by the
   branch guards themselves -- which is what these tests are actually about. */
const loadUsageBody = (() => {
  const i = boot.indexOf("async function loadUsage");
  let d = 0, start = boot.indexOf("{", i);
  for (let j = start; j < boot.length; j++) {
    if (boot[j] === "{") d++;
    else if (boot[j] === "}" && --d === 0) return boot.slice(i, j + 1);
  }
  throw new Error("could not isolate loadUsage");
})();

test("loadUsage reads /api/account on its own route", () => {
  const claude = loadUsageBody.slice(loadUsageBody.indexOf('kind === "none"'));
  assert(claude.includes('apiGet("/api/account")'), "loadUsage does not fetch /api/account");
  assert(claude.includes('apiGet("/api/usage")'), "loadUsage no longer fetches /api/usage");
  assert(claude.indexOf('apiGet("/api/account")') < claude.indexOf('apiGet("/api/usage")'),
         "account should load first");
});

test("loadUsage branches on the DECLARED usage kind, not the provider id", () => {
  /* Was `SETTINGS.provider === "deepseek"`, whose else-arm swept up every
     other provider. usage_kind is declared per provider in providers.py and
     shipped on the /api/providers row, so a provider that reports neither a
     window nor a balance gets neither instead of Claude's. */
  assert(loadUsageBody.includes("usageKindOf("), "loadUsage no longer reads the declared kind");
  assert(!/SETTINGS\.provider === "deepseek"/.test(loadUsageBody),
         "the provider-id branch is back");
  const balance = loadUsageBody.slice(loadUsageBody.indexOf('kind === "balance"'),
                                      loadUsageBody.indexOf('kind === "none"'));
  assert(balance.includes('apiGet("/api/deepseek/usage")'),
         "the balance branch does not call DeepSeek's own route");
  assert(!balance.includes('apiGet("/api/account")'),
         "the balance branch must not fetch the Claude account route");
});

test("a provider with no usage concept fetches nothing at all", () => {
  /* THE LATENT BUG. Codex is not selectable yet; the day it is, the old
     else-arm would have spent two requests reading ANTHROPIC's account and
     usage and rendered the answer as Codex's. */
  const i = loadUsageBody.indexOf('kind === "none"');
  assert(i > 0, "there is no branch for a provider with no usage concept");
  const arm = loadUsageBody.slice(i, i + 200);
  assert(/return/.test(arm), "the no-usage branch must return before any fetch");
  assert(!/apiGet/.test(arm), "the no-usage branch must not fetch anything: " + arm);
});

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
