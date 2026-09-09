#!/usr/bin/env node
/*
 * test_provider_intent.js -- "use Codex" switches the chat; "Codex" does not.
 *
 * WHAT THIS PROTECTS. An in-chat provider request moves the chat permanently
 * and replays the entire conversation to the other vendor, which costs real
 * tokens on a real account. So a false positive is not a cosmetic bug, and the
 * bar for matching is an INSTRUCTION, never a mention. Every case below that
 * asserts `null` is a sentence a person could plausibly type in a chat about
 * providers -- discussing them, asking about them, refusing them, or naming a
 * source file after one -- and none of them may move anything.
 *
 * BEHAVIOURAL, on the real bytes. detectProviderIntent and its two helpers are
 * extracted from static/js/02-helpers.js and evaluated, so this tests the
 * shipped function rather than a copy of its rules. The alias map is the shape
 * providers.provider_aliases() emits (asserted against the real thing by
 * test_provider_intent_aliases in test_provider_detect.py).
 *
 * Run: node test_provider_intent.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const helpers = fs.readFileSync(
  path.join(__dirname, "static", "js", "02-helpers.js"), "utf8");

let pass = 0, fail = 0;
const test = (n, f) => { try { f(); console.log("ok   - " + n); pass++; }
                         catch (e) { console.log("FAIL - " + n + "\n       " + e.message); fail++; } };
const assert = (c, m) => { if (!c) throw new Error(m || "assertion failed"); };

/* ── extract the shipped function, exactly as test_provider_switch.js does ─── */

function grab(src, name) {
  const start = src.indexOf("function " + name + "(");
  assert(start >= 0, "could not find function " + name);
  let i = src.indexOf("{", start), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error("unbalanced braces reading " + name);
}

function grabVar(src, name) {
  const start = src.indexOf("var " + name + " =");
  assert(start >= 0, "could not find var " + name);
  const end = src.indexOf(";\n", start);
  assert(end > start, "unterminated var " + name);
  return src.slice(start, end + 1);
}

const ctx = vm.createContext({});
vm.runInContext([
  grabVar(helpers, "PROVIDER_INTENT_PREFIX"),
  grabVar(helpers, "PROVIDER_INTENT_QUESTION"),
  grabVar(helpers, "PROVIDER_INTENT_NEGATION"),
  grab(helpers, "stripProviderNoise"),
  grab(helpers, "providerIntentFrames"),
  grab(helpers, "providerIntentOpensWithDirective"),
  grab(helpers, "detectProviderIntent"),
].join("\n"), ctx);

/* The shape providers.provider_aliases() emits. */
const ALIASES = {
  "claude": "claude", "claude code": "claude",
  "codex": "codex", "openai codex": "codex",
  "gemini": "gemini", "gemini cli": "gemini",
  "deepseek": "deepseek", "deep seek": "deepseek",
};
/* gemini is catalogued but has no chat adapter, so it is never runnable. */
const RUNNABLE = ["claude", "codex", "deepseek"];

const detect = (t) => ctx.detectProviderIntent(t, ALIASES, RUNNABLE);

const switches = (text, target) => test(
  "SWITCH  " + JSON.stringify(text), () => {
    const r = detect(text);
    assert(r, "no intent detected");
    assert(!r.ambiguous, "read as ambiguous: " + JSON.stringify(r));
    assert(r.ready === true, "not marked ready: " + JSON.stringify(r));
    assert(r.target === target,
           "expected " + target + " got " + JSON.stringify(r));
  });

const ignores = (text, why) => test(
  "IGNORE  " + JSON.stringify(text) + "  (" + why + ")", () => {
    const r = detect(text);
    assert(r === null, "switched anyway: " + JSON.stringify(r));
  });

/* ── 1. the five v1 frames must switch ───────────────────────────────────── */

switches("use Codex", "codex");
switches("Use Codex", "codex");
switches("use codex for this", "codex");
switches("Using Codex, implement this", "codex");
switches("using codex implement the parser", "codex");
switches("switch to Codex", "codex");
switches("switch this chat to Codex", "codex");
switches("change to codex", "codex");
switches("move over to codex", "codex");
switches("run this in Codex", "codex");
switches("do this in codex", "codex");
switches("handle that with codex", "codex");
switches("Codex: implement this", "codex");
switches("codex, implement this", "codex");
switches("@codex do this", "codex");

/* the founder's round trip: back to Claude the same way */
switches("Use Claude for this", "claude");
switches("switch to claude", "claude");
switches("using Claude Code, review this", "claude");
switches("use DeepSeek", "deepseek");
switches("use deep seek for this", "deepseek");
switches("use OpenAI Codex", "codex");

/* a small politeness prefix is still an instruction */
switches("please use Codex", "codex");
switches("ok, use codex", "codex");
switches("let's use codex", "codex");

/* ── 2. a bare mention must NOT switch ───────────────────────────────────── */

ignores("Codex", "a bare name is not an instruction");
ignores("codex", "same, lowercased");
ignores("Claude and Codex disagree about this", "discussion");
ignores("I read that Codex is good at Rust", "discussion");
ignores("compare Codex and Claude for me", "discussion");
ignores("the Codex adapter landed last week", "discussion");
ignores("add codex to the provider list", "an instruction about codex, not to it");
ignores("Codex support is what I want to build", "discussion");

/* ── 3. code, paths and identifiers ──────────────────────────────────────── */

ignores("fix the bug in codex_runtime.py", "identifier + file path");
ignores("use codex_runtime.py to trace this", "the alias is inside an identifier");
ignores("look at providers.codex and tell me", "dotted attribute");
ignores("install @openai/codex first", "package path");
ignores("run this in `codex`", "inline code");
ignores("check qa/fake_codex_agent.py", "path");
ignores("```\nuse codex\n```", "fenced code block");
ignores("the docs say \"use Codex\" but I disagree", "quoted discussion");

/* ── 3b. an INSTRUCTION whose payload is a question ──────────────────────────
   Found in manual testing, not by a test: "Using Codex, what is 17 x 6?" was
   rejected outright because the message ends in "?", so nothing switched,
   Claude answered 102, and the pane truthfully badged itself Claude. The
   question guard was reading the shape of the PAYLOAD instead of the shape of
   the request. A message that OPENS with a directive and carries something
   after it is an order, whatever punctuation it ends with. */

switches("Using Codex, what is 17 × 6?", "codex");
switches("Using Codex, what is 17 x 6?", "codex");
switches("use Codex, what is 17 x 6?", "codex");
switches("Codex: what is 17 x 6?", "codex");
switches("switch to Codex, then explain?", "codex");
switches("@codex what is 17 x 6?", "codex");
switches("Use Claude, what is 17 x 6?", "claude");

/* ── 4. questions ────────────────────────────────────────────────────────── */

ignores("why did Codex fail?", "question");
ignores("why did Codex fail", "question without the mark");
ignores("what does Codex think about this", "question");
ignores("should I use Codex?", "question");
ignores("can we use codex?", "question");
ignores("is codex better here?", "question");
ignores("use Codex?", "hedged: a directive with no payload after it");
ignores("use Codex ?", "same, with a space before the mark");
ignores("using codex?", "same");
ignores("how do I run this in Codex?", "question");

/* ── 5. negation ─────────────────────────────────────────────────────────── */

ignores("don't use Codex", "negated");
ignores("do not use Codex", "negated");
ignores("never use codex for this", "negated");
ignores("avoid using codex here", "negated");
ignores("instead of using codex, do it yourself", "negated");
ignores("rather than using codex, explain it", "negated");
ignores("no need to use codex", "negated");
ignores("stop using codex", "negated");

/* ── 6. ambiguity and readiness ──────────────────────────────────────────── */

test("two providers named in one message is NOT a switch", () => {
  const r = detect("use Codex, then switch to Claude");
  assert(r && r.ambiguous === true, "expected ambiguous, got " + JSON.stringify(r));
  assert(r.targets.length === 2, "expected two targets: " + JSON.stringify(r));
});

test("a negated provider does not make a second one ambiguous", () => {
  /* "don't use Claude, use Codex" -- the negation applies to claude only, so
     this stays a clean single-target switch to codex. */
  const r = detect("don't use Claude, use Codex");
  assert(r && !r.ambiguous, "read as ambiguous: " + JSON.stringify(r));
  assert(r.target === "codex", "expected codex, got " + JSON.stringify(r));
});

test("a provider with no adapter is recognised but NOT ready", () => {
  const r = detect("use Gemini");
  assert(r, "gemini was not recognised at all -- the operator gets silence");
  assert(r.target === "gemini", JSON.stringify(r));
  assert(r.ready === false, "gemini must never be selectable: " + JSON.stringify(r));
});

test("readiness comes from the caller's list, not from this function", () => {
  const r = ctx.detectProviderIntent("use Codex", ALIASES, ["claude"]);
  assert(r.target === "codex" && r.ready === false,
         "a runnable list without codex must mark it not ready: " + JSON.stringify(r));
});

test("an unknown name is not a provider", () => {
  assert(detect("use Mistral") === null);
  assert(detect("use GPT") === null, "model/vendor names are not provider ids in v1");
  assert(detect("use opus") === null, "opus is a MODEL, not a provider");
  assert(detect("use sonnet") === null, "sonnet is a MODEL, not a provider");
});

test("empty and whitespace input is null, not a crash", () => {
  assert(detect("") === null);
  assert(detect("   ") === null);
  assert(detect(null) === null);
  assert(detect(undefined) === null);
});

test("a missing alias map is survivable", () => {
  assert(ctx.detectProviderIntent("use Codex", null, RUNNABLE) === null,
         "with no aliases nothing can match, and that must not throw");
});

/* ── 7. word boundaries ──────────────────────────────────────────────────── */

ignores("use codexes", "not the provider name");
ignores("use codexlike tooling", "not the provider name");

console.log("\n" + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
