"""tests/test_prompts_parity.py — the write-phase prompts still say what the owner wrote.

WHY THIS EXISTS. The prompts under seo_agent/prompts/write are not code, they ARE the product: the
craft of the person whose articles this machine imitates. They were copied into Sutra during the
port and then quietly stopped tracking his originals. On 2026-09-09 a diff found TWENTY prompts out
of date and 234 lines of his writing missing, including whole rules Sutra had never carried:
"PROFESSIONAL, NOT CHATTY", "PUT THE BASICS FIRST", "CONNECT THE SECTIONS", and the far stronger
"CHECK EVERY SECTION AGAINST THE HEADLINE'S PROMISE". Sutra was still carrying, as its model of good
writing, the chatty example he had deleted. Nothing failed. Nobody noticed for four days.

Silent rot is the failure this file exists to stop, and it works in two layers.

LAYER 1, THE CRAFT RULES, RUNS EVERYWHERE. A short list of literal phrases from his 5 September
edits, each pinned to the prompt it belongs in. It needs no external folder, so it runs on any
machine and in the gate. If someone re-ports an older copy of a prompt, or edits one of these rules
out, the phrase disappears and this test names the prompt and the rule.

LAYER 2, FULL PARITY, RUNS WHEN HIS ORIGINALS ARE ON THE MACHINE (the default path below, or
SEO_PROMPT_SOURCE). Every prompt Sutra shares with him is compared line by line and any difference
is reported by prompt name, EXCEPT the two kinds of difference that are deliberate and declared
here:

  1. THE STANDING-RULES BLOCK. Sutra lets a user set standing rules and appends them to every
     prompt as a {{MEMORY}} block. His workflow has no such feature, so that block is his-side
     absent by design. Stripped before comparing.
  2. THE PORT EDITS in PORT_EDITS below. His repo is one company's; Sutra serves any company. Where
     a line names his own product pages or hard-codes his own published articles, the port replaced
     it with a token the code fills. Those lines are listed one by one, with the reason. Anything
     NOT listed is drift and fails.

The distinction matters in both directions. Take his token names and every prompt breaks at runtime,
because the code fills Sutra's names. Take Sutra's older prose and his craft is lost again.

Run:  PYTHONPATH=. SEO_AGENT_NO_CLI=1 .venv/bin/python seo_agent/tests/test_prompts_parity.py
"""
import difflib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(os.path.dirname(HERE), "prompts", "write")
FORMATS = os.path.join(PROMPTS, "formats")

# His originals. One anchor, overridable, because this path only exists on his machine.
SOURCE = os.environ.get(
    "SEO_PROMPT_SOURCE",
    "/Users/devanshasawa/Desktop/SEO by Devansh/Backlink gets Automated/workflows/04-write-phase")
SRC_PROMPTS = os.path.join(SOURCE, "prompts")
SRC_FORMATS = os.path.join(SOURCE, "formats")

FAILS, PASSES = [], []


def ok(label, cond, extra=""):
    (PASSES if cond else FAILS).append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond and extra:
        for line in str(extra).splitlines():
            print("          " + line)
    return cond


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LAYER 1 — the rules he wrote on 5 September 2026, pinned to the prompt that must carry them.
#
# Each entry is (a short name for the rule, a literal phrase that only that rule contains). Keep
# the phrases SHORT and distinctive: a phrase long enough to break on a comma edit is a phrase that
# fails for the wrong reason. Add to this list whenever a rule is worth never losing again.
# ══════════════════════════════════════════════════════════════════════════════════════════════

CRAFT_RULES = {
    "readable.md": [
        ("professional, not chatty", "PROFESSIONAL, NOT CHATTY."),
        ("the banned chatty asides", 'Conversational asides ("here\'s the'),
        ("put the basics first", "PUT THE BASICS FIRST."),
        ("every section against the headline's promise",
         "CHECK EVERY SECTION AGAINST THE HEADLINE'S PROMISE."),
        ("be ruthless about off-promise sections", "Be ruthless here."),
        ("connect the sections", "CONNECT THE SECTIONS."),
        ("the TL;DR is takeaways, not a short article", "THE TL;DR is the article's takeaways"),
    ],
    "write-body.md": [
        ("the register is professional", "THE REGISTER: PROFESSIONAL."),
        ("write the way SHRM writes", "Write the way SHRM writes"),
        ("every sentence must stand on its own", "EVERY SENTENCE MUST STAND ON ITS OWN."),
    ],
    "write-heading.md": [
        ("the heading must stand alone", "THE HEADING MUST STAND ALONE."),
        ("simple beats clever", "SIMPLE BEATS CLEVER, EVERY TIME."),
        ("a product section's heading", "A PRODUCT SECTION'S HEADING IS THE PRODUCT NAME"),
        ("use the reader's own search words", "USE THE READER'S OWN SEARCH WORDS FOR THE TOPIC."),
    ],
    "heading-pass.md": [
        ("a heading that needs the article", "A HEADING THAT NEEDS THE ARTICLE."),
        ("no rhetorical questions, no quips", "NO RHETORICAL QUESTIONS, NO QUIPS, NO IDIOM."),
    ],
    "sentence-pass.md": [
        ("never split a sentence under 15 words", "A SENTENCE UNDER 15 WORDS IS NEVER SPLIT."),
        ("fragment stacks are banned", "This device used to be allowed here; it is now banned."),
        ("keep the register professional", "KEEP THE REGISTER PROFESSIONAL."),
    ],
    "fat-paragraphs.md": [
        ("a split may not strand a stub", "BOTH HALVES MUST STAND AS REAL PARAGRAPHS"),
    ],
    "wrapper.md": [
        ("define the subject inside the intro", "WHEN THE ARTICLE EXPLAINS A SUBJECT THE READER MAY NOT KNOW"),
        ("the TL;DR block", "3. THE TL;DR"),
        ("every item is a full statement", "EVERY ITEM IS A FULL STATEMENT THAT ANSWERS"),
        ("the register is professional", "THE REGISTER IS PROFESSIONAL."),
    ],
    "structure-simple.md": [
        ("stay inside the headline's promise", "STAY INSIDE THE HEADLINE'S PROMISE."),
        ("the basics come first", "THE BASICS COME FIRST."),
    ],
    "structure-comparison.md": [
        ("stay inside the headline's promise", "STAY INSIDE THE HEADLINE'S PROMISE."),
        ("the basics come first", "THE BASICS COME FIRST."),
    ],
    "structure-listicle.md": [
        ("stay inside the headline's promise", "STAY INSIDE THE HEADLINE'S PROMISE."),
        ("the basics come first", "THE BASICS COME FIRST."),
    ],
    "structure-template.md": [
        ("stay inside the headline's promise", "STAY INSIDE THE HEADLINE'S PROMISE."),
        ("the basics come first", "THE BASICS COME FIRST."),
    ],
    "formats/listicle.md": [
        ("the shape of one item", "THE SHAPE OF ONE ITEM"),
        ("no limitation line on the publisher's own product",
         "never write a limitation line for it"),
    ],
    "formats/comparison-rankings.md": [
        ("the shape of one deep dive", "THE SHAPE OF ONE DEEP DIVE"),
        ("a blog post, not a report", "THIS IS A BLOG POST, NOT A REPORT."),
        ("no limitation line on the publisher's own product",
         "never write a limitation line for it"),
    ],
    "formats/glossary.md": [
        ("the term entries are the article", "THE TERM ENTRIES ARE THE ARTICLE."),
        ("the definition of the subject leads", "the section defining the core subject itself comes FIRST"),
        ("no process or legal advice with no term at its centre",
         "with no term at its centre"),
    ],
}

# The chatty example he deleted. Sutra carried it as its MODEL of good writing until 2026-09-09,
# which is the exact opposite of the rule above it. If it ever comes back, something was reverted.
MUST_NOT_APPEAR = {
    "readable.md": [("the deleted chatty opener", 'HUMAN:  "This is where it gets expensive.')],
    "sentence-pass.md": [("the deleted fragment-stack model answer",
                          'AFTER:  "Looking away to think. A housemate crossing the frame.')],
}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LAYER 2 — the declared, deliberate differences between his copy and Sutra's.
#
# EXCLUDED_REGIONS: a stretch of a prompt that is DATA in Sutra and hard-coded in his repo. Dropped
# from both sides. Give the first line and the line that ends it (the end line itself is compared).
#
# PORT_EDITS: individual lines allowed to differ, each with the reason. A differing line is forgiven
# only when it contains one of these substrings. Anything else is drift and fails by name.
# ══════════════════════════════════════════════════════════════════════════════════════════════

EXCLUDED_REGIONS = {
    # He pastes five of his own published paragraphs in as the bar to hit. Sutra fills that from the
    # company's own articles at run time ({{WRITING_EXAMPLES}}, filled in write/readable.py), so the
    # passages themselves and the sentences that count them ("These five") cannot match and must not.
    "readable.md": [("REAL PUBLISHED ARTICLES BY", "  · The reader is")],
}

PORT_EDITS = {
    "inline-links.md": [
        ("page is pricing,", "his product pages; Sutra serves any company, so the example is generic"),
        ("is the reader who wants the", "same line, his product named"),
        ("sending them to another blog post instead wastes the moment", "reflow from the two lines above"),
    ],
    "wrapper.md": [
        ("then rank...", "the CTA example links his own product page; the port made it example.com"),
        # FORMAT_CRAFT is his 5 September wiring: wrapper.py reads formats/_craft/<archetype>.md and
        # fills the token. Sutra's wrapper.py does not pass an archetype, so the token would reach
        # the model unfilled and test_write.py would refuse it. The _craft files ARE ported, under
        # prompts/write/formats/_craft/, and its README says what is left to wire.
        ("{{ARCHETYPE}}", "his FORMAT_CRAFT wiring, not yet wired in Sutra; see formats/_craft/README.md"),
        ("{{FORMAT_CRAFT}}", "his FORMAT_CRAFT wiring, not yet wired in Sutra; see formats/_craft/README.md"),
        ("the format rules win", "part of the same FORMAT_CRAFT block"),
        ("what makes this format's wrap its own", "part of the same FORMAT_CRAFT block"),
    ],
    "wrapper-cta-retry.md": [
        ("then rank...", "the CTA example links his own product page; the port made it example.com"),
    ],
}

# PROMPTS SUTRA CARRIES IN AN ADAPTED FORM ON PURPOSE. Checked for presence, not for line parity.
# The three new stations (voices from the field, the enrich search, the replacement-source hunt)
# were built into Sutra in the same release from his prompts, but against Sutra's own tools: his
# search step assumes a search tool this app reaches differently, so the wording had to change.
# They belong to the agents that wrote them. Presence is the check that matters here.
ADAPTED = {
    "field-plan.md": "the voices station, adapted to Sutra's tools by the agent that built it",
    "field-probe.md": "the voices station, adapted to Sutra's tools by the agent that built it",
    "field-write.md": "the voices station, adapted to Sutra's tools by the agent that built it",
    "field-block.md": "the voices station, adapted to Sutra's tools by the agent that built it",
    "plan-queries.md": "the enrich search station, adapted to Sutra's browser search",
    "search-urls.md": "the enrich search station, adapted to Sutra's browser search",
    "source-queries.md": "the replacement-source hunt, adapted to Sutra's browser search",
}

# His prompts with no copy in Sutra, and why. A prompt of his that is on neither this list nor
# ADAPTED, and not in Sutra, is an unnoticed gap, which is how the last one happened, so it fails.
NOT_PORTED = {
    "extract-cards.md": "his research phase reads a STORM dossier; Sutra's research phase does not",
    "extract-winners.md": "lives in Sutra as prompts/research/extract-winners.md, not a write prompt",
    "extract-word-band.md": "his word band comes from a research-phase file Sutra does not produce",
}

# Sutra's own standing-rules block. His workflow has no such feature, so it is his-side absent by
# design and stripped before any comparison.
MEMORY_HEAD = "THE USER'S STANDING RULES."
MEMORY_TAIL = "{{MEMORY}}"
_RULE = re.compile(r"^[═─━=_-]+$")


def strip_memory(lines):
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith(MEMORY_HEAD):
            # the divider immediately above the block belongs to it
            while out and out[-1].strip() == "":
                out.pop()
            if out and _RULE.match(out[-1].strip()):
                out.pop()
            while i < len(lines) and lines[i].strip() != MEMORY_TAIL:
                i += 1
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def drop_regions(lines, regions):
    """Remove each declared region. The end marker is the first line NOT removed."""
    for start, end in regions:
        try:
            a = next(n for n, l in enumerate(lines) if l.startswith(start))
            b = next(n for n, l in enumerate(lines) if n > a and l.startswith(end))
        except StopIteration:
            continue
        lines = lines[:a] + lines[b:]
    return lines


def content(lines):
    """Blank lines and rule-off dividers carry no craft, so their width never counts as drift."""
    return [l for l in lines if l.strip() and not _RULE.match(l.strip())]


def read(path):
    return open(path, encoding="utf-8").read().splitlines()


# ══════════════════════════════════════════════════════════════════════════════════════════════
print("\nlayer 1 — his rules are in the prompts (runs everywhere)")

for rel, rules in sorted(CRAFT_RULES.items()):
    path = os.path.join(PROMPTS, rel)
    if not os.path.exists(path):
        ok("%s exists" % rel, False, "missing: " + path)
        continue
    text = open(path, encoding="utf-8").read()
    missing = [name for name, phrase in rules if phrase not in text]
    ok("%s carries all %d of his rules" % (rel, len(rules)), not missing,
       "missing: " + ", ".join(missing) if missing else "")

for rel, gone in sorted(MUST_NOT_APPEAR.items()):
    text = open(os.path.join(PROMPTS, rel), encoding="utf-8").read()
    back = [name for name, phrase in gone if phrase in text]
    ok("%s no longer carries what he deleted" % rel, not back,
       "came back: " + ", ".join(back) if back else "")

# The whole point of keeping Sutra's token names: the code fills these, his names would not.
TOKENS_THE_CODE_FILLS = {
    "readable.md": ["{{WRITING_EXAMPLES}}", "{{BRAND}}", "{{FORMAT_RULE}}", "{{ARTICLE}}"],
    "wrapper.md": ["{{BRAND}}", "{{VOICE}}", "{{FAQ_WORDS}}", "{{MEMORY}}"],
    "write-body.md": ["{{BRIEF}}", "{{FIELD}}", "{{MEMORY}}"],
    "sentence-pass.md": ["{{READER}}", "{{TEXT}}", "{{MEMORY}}"],
}
for rel, tokens in sorted(TOKENS_THE_CODE_FILLS.items()):
    text = open(os.path.join(PROMPTS, rel), encoding="utf-8").read()
    lost = [t for t in tokens if t not in text]
    ok("%s kept the token names the code fills" % rel, not lost,
       "gone: " + ", ".join(lost) if lost else "")


# ══════════════════════════════════════════════════════════════════════════════════════════════
print("\nlayer 2 — parity with his originals")

if not os.path.isdir(SRC_PROMPTS):
    print("  SKIP  his originals are not on this machine (%s)" % SOURCE)
    print("        set SEO_PROMPT_SOURCE to run the full parity check")
else:
    def compare(rel, src_path, dst_path):
        a = strip_memory(read(dst_path))
        b = read(src_path)
        regions = EXCLUDED_REGIONS.get(rel, [])
        a, b = drop_regions(a, regions), drop_regions(b, regions)
        allowed = [s for s, _why in PORT_EDITS.get(rel, [])]
        drift = []
        for line in difflib.unified_diff(content(a), content(b), lineterm="", n=0):
            if line[:1] not in "+-" or line[:3] in ("+++", "---"):
                continue
            if any(s in line for s in allowed):
                continue
            drift.append(line)
        ok("%s matches his copy" % rel, not drift, "\n".join(drift[:12]))

    shared = [n for n in sorted(os.listdir(SRC_PROMPTS))
              if n.endswith(".md") and n not in ADAPTED
              and os.path.exists(os.path.join(PROMPTS, n))]
    for n in shared:
        compare(n, os.path.join(SRC_PROMPTS, n), os.path.join(PROMPTS, n))

    for n in sorted(os.listdir(SRC_FORMATS)):
        if n.endswith(".md") and os.path.exists(os.path.join(FORMATS, n)):
            compare("formats/" + n, os.path.join(SRC_FORMATS, n), os.path.join(FORMATS, n))

    craft_src = os.path.join(SRC_FORMATS, "_craft")
    craft_dst = os.path.join(FORMATS, "_craft")
    for n in sorted(os.listdir(craft_src)):
        if n.endswith(".md") and n != "README.md" and os.path.exists(os.path.join(craft_dst, n)):
            compare("formats/_craft/" + n, os.path.join(craft_src, n), os.path.join(craft_dst, n))

    # A prompt of his that Sutra does not have, and that nobody has written down as skipped, is the
    # gap that goes unnoticed. Name it here or it fails.
    absent = sorted(n for n in os.listdir(SRC_PROMPTS)
                    if n.endswith(".md") and not os.path.exists(os.path.join(PROMPTS, n)))
    unlisted = [n for n in absent if n not in NOT_PORTED and n not in ADAPTED]
    ok("every prompt of his that Sutra lacks is a known, written-down gap", not unlisted,
       "not in NOT_PORTED: " + ", ".join(unlisted) if unlisted else "")

    stale = [n for n in NOT_PORTED if os.path.exists(os.path.join(PROMPTS, n))]
    ok("nothing is listed as not-ported that Sutra now has", not stale,
       "ported since, move it to full parity or to ADAPTED: " + ", ".join(stale) if stale else "")

    missing_adapted = [n for n in ADAPTED if not os.path.exists(os.path.join(PROMPTS, n))]
    ok("every prompt listed as adapted is actually here", not missing_adapted,
       "listed as adapted but absent: " + ", ".join(missing_adapted) if missing_adapted else "")

    print("\n  his prompts Sutra does not carry, and why:")
    for n in absent:
        print("    %-24s %s" % (n, NOT_PORTED.get(n, ADAPTED.get(n, "?"))))
    print("\n  his prompts Sutra carries in an adapted form (presence checked, wording theirs):")
    for n in sorted(ADAPTED):
        print("    %-24s %s" % (n, ADAPTED[n]))

print("\n%d checks, %d failed" % (len(PASSES) + len(FAILS), len(FAILS)))
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    sys.exit(1)
print("the write-phase prompts still say what he wrote")
