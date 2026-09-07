"""tests/test_checks_editing.py — the safety net around editing.

The one guarantee that matters: rewriting one paragraph must leave every other paragraph
byte-identical. Two defences, and both are tested here. The model's reply is sanitised so it
cannot split one block into two, and then an assertion compares every untouched block and
raises if any moved.
"""
import os
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.checks import ai_writing
import importlib

# editing/__init__.py re-exports edit_block, so the name shadows the submodule.
# import_module reaches the real module regardless.
eb = importlib.import_module("seo_agent.editing.edit_block")
edit_block = eb.edit_block
from seo_agent.editing.make_diff import make_diff

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))

DOC = """# Executive education in India

First paragraph, untouched and precious.

Second paragraph, also untouched.

Third paragraph, the one we will rewrite.

Fourth paragraph, untouched again."""

print("\nediting: only the named block moves")
llm.text = lambda p, system=None: "Third paragraph, now rewritten and better."
res = edit_block(DOC, "p3", "make it punchier")
new = res["new"]
old_b, new_b = DOC.split("\n\n"), new.split("\n\n")
ok("block count is preserved", len(old_b) == len(new_b), "%d -> %d" % (len(old_b), len(new_b)))
ok("the target changed", old_b[3] != new_b[3])
ok("every other block is byte-identical",
   all(old_b[i] == new_b[i] for i in range(len(old_b)) if i != 3))
ok("it reports which block it touched", res.get("changed_blocks") == ["p3"], res.get("changed_blocks"))

print("\nediting: the model cannot smuggle in extra blocks")
llm.text = lambda p, system=None: "One line.\n\nA second paragraph it was not asked for.\n\nAnd a third."
res2 = edit_block(DOC, "p3", "rewrite it")
ok("blank lines collapsed, count still preserved",
   len(res2["new"].split("\n\n")) == len(old_b), len(res2["new"].split("\n\n")))
ok("the neighbours survived",
   res2["new"].split("\n\n")[4] == old_b[4])

print("\nediting: drift raises rather than saving quietly")
try:
    bad_map = {"p0": "a", "p1": "CHANGED", "p2": "c"}
    eb.assert_only_target_changed({"p0": "a", "p1": "b", "p2": "c"}, bad_map, "p2")
    ok("an untouched block that moved is caught", False, "no raise")
except eb.BlockDrift as e:
    ok("an untouched block that moved is caught", True)
    ok("the error names the culprit", "p1" in str(e))
try:
    eb.assert_only_target_changed({"p0": "a", "p1": "b"}, {"p0": "a", "p1": "b", "p2": "c"}, "p1")
    ok("a changed block count is caught", False, "no raise")
except eb.BlockDrift:
    ok("a changed block count is caught", True)

print("\nediting: a bad block id fails loudly")
try:
    edit_block(DOC, "p99", "x")
    ok("unknown block id raises", False)
except Exception as e:
    ok("unknown block id raises", True)
    ok("the message says how many blocks there are", "blocks" in str(e).lower(), str(e)[:70])

print("\nAI writing: the patterns are caught, with a real replacement")
BAD = ("We delve into the ever-evolving landscape of leadership.\n\n"
       "It's important to note that this is a testament to robust, seamless growth.\n\n"
       "This isn't just about training. It's about transformation - a crucial pivot.")
out = ai_writing.check(BAD)
items = out.get("items", [])
found = " ".join((i.get("what") or "") for i in items).lower()
ok("finds several", len(items) >= 5, len(items))
ok("catches delve", "delve" in found)
ok("catches robust", "robust" in found)
ok("catches the note-opener", "important to note" in found)
ok("every finding says where", all(i.get("where") for i in items))
ok("most findings suggest a replacement",
   sum(1 for i in items if i.get("fix")) >= len(items) - 1)
ok("it warns, it never blocks", out.get("status") == "warn", out.get("status"))

print("\nAI writing: clean prose is left alone")
GOOD = ("Executive programmes in India have grown quickly.\n\n"
        "Most coverage stops at rankings and fees. That leaves the real question unanswered.")
clean = ai_writing.check(GOOD)
ok("clean text passes or barely warns", len(clean.get("items", [])) <= 1,
   [i.get("what") for i in clean.get("items", [])])


print("\ndraft checks: each one fires on the fault it exists for")
from seo_agent.checks import run_checks
BAD_DRAFT = """# Executive education in India

As we discussed above, this matters a great deal.

Growth hit 47% in 2024. Nobody says where from.

See [our pricing](https://example.com/does-not-exist).

### A skipped heading level

We delve into the robust landscape."""
res = {c["name"]: c for c in run_checks("draft", BAD_DRAFT)}
ok("an invented internal link fails",
   res.get("internal_links_resolve", {}).get("status") in ("fail", "warn"),
   res.get("internal_links_resolve", {}).get("status"))
ok("an orphaned back-reference warns",
   res.get("no_orphaned_references", {}).get("status") == "warn")
ok("a skipped heading level warns",
   res.get("heading_structure", {}).get("status") == "warn")
ok("an uncited number warns",
   res.get("claims_have_sources", {}).get("status") == "warn")
ok("AI-isms warn and never fail",
   res.get("ai_writing", {}).get("status") == "warn")

print("\ndraft checks: a clean draft passes")
GOOD_DRAFT = """# Executive education in India

Programmes have grown quickly over the last five years.

## What changes afterwards

Most coverage stops at rankings and fees. That leaves the real question unanswered.

## Who it suits

Founders, and the layer of leaders directly below them."""
res2 = {c["name"]: c for c in run_checks("draft", GOOD_DRAFT)}
bad = [n for n, c in res2.items() if c["status"] == "fail"]
ok("nothing fails on clean prose", not bad, bad)

print("\ndraft checks: an edit that moved too much is caught")
one_changed = GOOD_DRAFT.replace("Founders, and the layer", "Founders, plus the layer")
two_changed = one_changed.replace("grown quickly", "grown very quickly")
r1 = {c["name"]: c for c in run_checks("draft", one_changed, previous=GOOD_DRAFT)}
r2 = {c["name"]: c for c in run_checks("draft", two_changed, previous=GOOD_DRAFT)}
ok("one changed paragraph passes",
   r1["only_targeted_block_changed"]["status"] == "pass")
ok("two changed paragraphs fail",
   r2["only_targeted_block_changed"]["status"] == "fail",
   r2["only_targeted_block_changed"]["detail"])

print("\ndraft checks: citations, the narrow way")
from seo_agent.checks import draft_checks as dc
ok("'no source in sight' is not a citation",
   dc.check_claims_have_sources("# T\n\nGrowth hit 47% with no source in sight.")["status"] == "warn")
ok("'according to X' is a citation",
   dc.check_claims_have_sources("# T\n\nGrowth hit 47%, according to NASSCOM.")["status"] == "pass")

print("\ndiff")
d = make_diff("one\ntwo\nthree", "one\ntwo CHANGED\nthree")
kinds = [x["type"] for x in d]
ok("shows an add and a remove", "add" in kinds and "remove" in kinds, kinds)
ok("keeps the unchanged context", any(k in ("same", "context") for k in kinds))

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all editing and checks pass")
