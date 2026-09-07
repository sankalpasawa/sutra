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


def run(co, say, redo=False):
    files = []
    if cm.exists(OUTPUT) and not redo:
        say("Kept writing-integrity.md", "already built; ask for a redo to rebuild it")
    else:
        rec = store.knowledge("brand/company.json") or {}
        is_ = product_is(co) or SLOT_IS
        is_not = (rec.get("product_is_not") or "").strip() or SLOT_IS_NOT
        cm.save(OUTPUT, cm.fill(cm.template("writing-integrity"), brand=co["brand"], product_is=is_, product_is_not=is_not))
        say("Instantiated writing-integrity.md",
            "Rule 1's product boundary %s" % ("filled from the record and features.md" if is_ != SLOT_IS else "left as a marked slot"))
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
