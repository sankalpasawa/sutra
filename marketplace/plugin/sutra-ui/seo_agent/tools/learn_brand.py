"""learn_brand.py — build the brand pack: how this company writes and what it sells, from its own pages.

The port of the workflow's Layer 01 (brand context). Twelve builders run in the original order, each
one a module in brand/, each writing its files under knowledge/brand/ before the next one reads them:

     0 type-roles         what THIS company's page types hold (stat / story / commercial / editorial)
     1 brand-facts        stats.md · stories.md · opinions.md (⚠️ candidates; the human confirms)
     2 brand-voice        page-shortlist.md · brand-voice.md (+ the one-liner into company.json)
     3 style-guide        style-guide.md
     4 features           features.md · cta-pages.md
     5 writing-examples   writing-examples.md
     6 persona            persona.md
     7 voices             voices.md (the team's byline questionnaire)
     8 writing-integrity  writing-integrity.md · seo-aeo-geo-checklist.md
     9 writer-brief       writer-brief.md · writer-brief-rulings.md
    10 brand-cards        brand-cards.json
    11 field-sources      field-sources.md

Resumable: a builder whose files exist is skipped unless `redo` is set or `only` names it. One
builder failing is said and the rest still run (a later builder that needs the missing file says so
itself). The human gates of the original are checkpoints here: everything is saved, and
`needs_review` lists what a person still has to confirm, so the agent can show the pack.
"""
from .. import store
from ..brand import (brand_cards, brand_facts, brand_voice, features, field_sources, pack, persona,
                     style_guide, type_roles, voices, writer_brief, writing_examples, writing_integrity)
from . import _shared as sh

# (key, module, the files that mark it done), in the original's run order
BUILDERS = [
    ("type-roles", type_roles, ["type-roles.json"]),
    ("brand-facts", brand_facts, ["stats.md", "stories.md", "opinions.md"]),
    ("brand-voice", brand_voice, ["brand-voice.md"]),
    ("style-guide", style_guide, ["style-guide.md"]),
    ("features", features, ["features.md", "cta-pages.md"]),
    ("writing-examples", writing_examples, ["writing-examples.md"]),
    ("persona", persona, ["persona.md"]),
    ("voices", voices, ["voices.md"]),
    ("writing-integrity", writing_integrity, ["writing-integrity.md", "seo-aeo-geo-checklist.md"]),
    ("writer-brief", writer_brief, ["writer-brief.md"]),
    ("brand-cards", brand_cards, ["brand-cards.json"]),
    ("field-sources", field_sources, ["field-sources.md"]),
]
KEYS = [k for k, _m, _f in BUILDERS]


def _only(only):
    if not only:
        return set()
    if isinstance(only, str):
        only = [o for o in only.replace(";", ",").split(",")]
    wanted = {str(o).strip().lower().replace("_", "-") for o in only if str(o).strip()}
    unknown = sorted(wanted - set(KEYS))
    if unknown:
        raise ValueError("Unknown builder name(s): %s. Known: %s" % (", ".join(unknown), ", ".join(KEYS)))
    return wanted


def run(ctx, redo=False, only=None):
    say = sh.reporter(ctx, "learn_brand")
    index = store.knowledge("site_index.json")
    if not index or not (index.get("pages") if isinstance(index, dict) else index):
        raise RuntimeError("There is no site index yet. Run index_site first, then learn_brand.")
    co = sh.company()
    wanted = _only(only)
    redo = bool(redo)

    files, needs_review, built, skipped, failed = [], [], [], [], []
    for key, mod, outputs in BUILDERS:
        if wanted and key not in wanted:
            continue
        force = redo or key in wanted
        # brand-facts decides per file whether a draft is due (a confirmed file is never touched), so
        # it always gets a look; the others are done once their files exist.
        if not force and key != "brand-facts" and all(sh.brand_file(f) or store.knowledge("brand/" + f) for f in outputs):
            say("Already built: %s" % key, ", ".join(outputs))
            files += outputs
            skipped.append(key)
            continue
        say("Building %s" % key, "")
        try:
            out = mod.run(co, say, redo=force) or {}
        except Exception as e:      # noqa: BLE001 - one builder failing must not lose the other eleven
            say("%s failed" % key, str(e)[:200])
            failed.append(key)
            needs_review.append("%s: did not finish (%s)" % (key, str(e)[:160]))
            continue
        files += out.get("files") or outputs
        needs_review += out.get("needs_review") or []
        built.append(key)
        if key == "brand-voice":
            co = sh.company()          # the one-liner and niche may have just been filled in

    seen, uniq = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    parts = []
    if built:
        parts.append("built %s" % ", ".join(built))
    if skipped:
        parts.append("kept %d already built" % len(skipped))
    if failed:
        parts.append("%s did not finish" % ", ".join(failed))
    summary = "Brand pack: %s. %d files under knowledge/brand/." % ("; ".join(parts) or "nothing to do", len(uniq))
    if needs_review:
        summary += " %d things need your review." % len(needs_review)
    return {"summary": summary, "files": uniq, "needs_review": needs_review, "artifact": None,
            "pack": pack.summary()}
