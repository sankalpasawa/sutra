"""brand/writing_integrity.py — builder 8: the honesty contract, and the per-article SEO checklist.

The originals ship writing-integrity.md to each company's brand-context by copy, filling only Rule
1's two product-boundary slots from features.md / the company record; seo-aeo-geo-checklist.md ships
verbatim. This builder does the same:

- {{PRODUCT_IS}}: the brand one-liner from company.json, plus the Core Value Proposition names from
  features.md when it exists. Nothing else is derivable without inventing, so
- {{PRODUCT_IS_NOT}} stays a marked slot for a human unless the record carries `product_is_not`.

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


# "It is not an ATS, an HRIS, ..." style sentences the pack already contains. The boundary was
# always written down; it was simply never wired into Rule 1, so the shipped file asked a human
# for something two other files already answered (found 2026-09-09).
_NOT_RE = re.compile(
    r"(?:it|%s)\s+is\s+not\s+(?:an?\s+)?(?P<list>[^.;\n]{10,220})", re.I)


def product_is_not(co):
    """What the product is NOT, lifted from features.md or the writer brief. "" when neither says."""
    brand = re.escape((co.get("brand") or "").strip() or "the product")
    pat = re.compile(_NOT_RE.pattern % brand, re.I)
    for name in ("features.md", "writer-brief.md"):
        text = cm.read(name)
        if not text:
            continue
        best = ""
        for m in pat.finditer(text):
            phrase = " ".join(m.group("list").split())
            # the useful ones list several things; "is not finished" is a different sentence
            if phrase.count(",") >= 1 and len(phrase) > len(best):
                best = phrase
        if best:
            return best.rstrip(" ,")
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
