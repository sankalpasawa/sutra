"""brand/writing_integrity.py — builder 8: the honesty contract, and the per-article SEO checklist.

The originals ship writing-integrity.md to each company's brand-context by copy, filling only Rule
1's two product-boundary slots from features.md / the company record; seo-aeo-geo-checklist.md ships
verbatim. This builder does the same:

- {{PRODUCT_IS}}: the brand one-liner from company.json, plus the Core Value Proposition names from
  features.md when it exists.
- {{PRODUCT_IS_NOT}}: the boundary sentence the pack already wrote down, lifted out of features.md
  or the writer brief. The record's own `product_is_not` outranks both. When no file states a
  boundary the slot stays marked for a human: the machine never invents one.

Writes: brand/writing-integrity.md · brand/seo-aeo-geo-checklist.md (verbatim copy)
"""
import re

from .. import store
from . import _common as cm

OUTPUT = "writing-integrity.md"
CHECKLIST = "seo-aeo-geo-checklist.md"
SLOT_IS = "⚑ HUMAN DECISION: state what the product IS (fill from features.md / the one-liner)"
SLOT_IS_NOT = "⚑ HUMAN DECISION: list what the product is NOT (never imply it owns these)"
MAX_PROPS = 5


def product_is(co):
    parts = []
    if (co.get("brand_oneliner") or "").strip():
        parts.append(co["brand_oneliner"].strip())
    feats = cm.read("features.md")
    names = [n.strip() for n in re.findall(r"^### \d+\.\s+\*\*(.+?)\*\*", feats, re.M)]
    names = [n for n in names if "[" not in n][:MAX_PROPS]
    if names:
        parts.append("its core capabilities (from features.md): " + "; ".join(names))
    return " — ".join(parts)


# "Testlify is not another ATS" style sentences the pack already contains. The boundary was always
# written down; it was simply never wired into Rule 1, so the shipped file asked a human for
# something two other files already answered (found 2026-09-09).
#
# Every piece of this pattern is load-bearing, and each one is here because the first version got
# it wrong. Verified 2026-09-09 against a 96-minute rebuild on the owner's real 12,318-page site,
# where the slot shipped unfilled while the answer sat in writer-brief.md:
#
#  * CASE-SENSITIVE, and "It" only at the start of a sentence. Compiled re.I with a bare `it`, the
#    pattern matched inside any word: the one thing it found in features.md was the middle of
#    "...ity where inclusion is not only valued but prioritized", which is a sentence about
#    workplace inclusion and not a product boundary at all.
#  * The BRAND stays case-insensitive, scoped to its own group, because a company record may spell
#    it "testlify" while the pages say "Testlify".
#  * A floor of 3 characters, not 10. The only true boundary in the owner's whole pack is
#    "another ATS", and "an ATS" is six characters; a ten-character floor rejects the real answers
#    and keeps only the wordy ones.
#  * NO comma rule. It used to demand a list of several things, which no honest boundary sentence
#    has to be, and which is why the real one never got through. That rule was also the only thing
#    keeping the "inclusion" false positive out, so one bug was hiding the other; both go together.
#  * The article strip does not fire on "another", because there is no space after "an". That is
#    deliberate and left alone: "another ATS" is how a person would say it.
_NOT_RE = (r"(?:(?:^|(?<=[.\n]\s))It|(?i:%s))\s+is\s+not\s+(?:an?\s+)?(?P<list>[^.;\n]{3,220})")

# A sentence that says the product is not ONLY something is a rhetorical flourish about how much
# it does, not a line drawn around what it does not do. "It is not just a test library" is a boast.
_RHETORIC = ("only", "just", "merely")


def product_is_not(co):
    """What the product is NOT, lifted from features.md or the writer brief. "" when neither says.

    Never invents. An empty answer is the right answer when the pack does not state a boundary,
    and the caller leaves Rule 1's slot marked for a person to fill.
    """
    brand = re.escape((co.get("brand") or "").strip() or "the product")
    pat = re.compile(_NOT_RE % brand)
    for name in ("features.md", "writer-brief.md"):
        text = cm.read(name)
        if not text:
            continue
        best = ""
        for m in pat.finditer(text):
            phrase = " ".join(m.group("list").split()).rstrip(" ,")
            words = set(re.findall(r"[a-z]+", phrase.lower()))
            if words & set(_RHETORIC):
                continue
            if len(phrase) > len(best):
                best = phrase
        if best:
            return best
    return ""


def strip_frontmatter(text):
    """The template carries the workflow's own frontmatter (type, scope, ships_to, a path into a
    repo this app has no idea about). It is meaningless to a person reading the file in Knowledge,
    so it does not ship."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def run(co, say, redo=False):
    files = []
    if cm.exists(OUTPUT) and not redo:
        say("Kept writing-integrity.md", "already built; ask for a redo to rebuild it")
    else:
        rec = store.knowledge("brand/company.json") or {}
        is_ = product_is(co) or SLOT_IS
        is_not = (rec.get("product_is_not") or "").strip() or product_is_not(co) or SLOT_IS_NOT
        cm.save(OUTPUT, strip_frontmatter(
            cm.fill(cm.template("writing-integrity"), brand=co["brand"], product_is=is_, product_is_not=is_not)))
        say("Instantiated writing-integrity.md",
            "Rule 1: what it is %s; what it is not %s"
            % ("filled from the record and features.md" if is_ != SLOT_IS else "left as a marked slot",
               "filled from the pack" if is_not != SLOT_IS_NOT else "left as a marked slot"))
    files.append(OUTPUT)
    if not cm.exists(CHECKLIST) or redo:
        cm.save(CHECKLIST, cm.template("seo-aeo-geo-checklist"))
        say("Copied the SEO / AEO / GEO checklist", "verbatim, the per-article gate")
    files.append(CHECKLIST)
    notes = []
    n = cm.count_lines(cm.read(OUTPUT), "⚑ HUMAN DECISION")
    if n:
        notes.append("writing-integrity.md: %d product-boundary slots to fill (Rule 1)" % n)
    return {"files": files, "needs_review": notes}
