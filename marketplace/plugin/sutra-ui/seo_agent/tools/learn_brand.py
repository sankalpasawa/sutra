"""learn_brand.py — build the brand pack: how this company writes and what it sells, from its own pages.

The port of the workflow's Layer 01 (brand context). Eleven builders run in the original order, each
one a module in brand/, each writing its files under knowledge/brand/ before the next one reads them:

     0 type-roles         what THIS company's page types hold (stat / story / commercial / editorial)
     1 brand-facts        stats.md · stories.md (machine drafts, marked; the human confirms by editing)
     2 brand-voice        page-shortlist.md · brand-voice.md (+ the one-liner into company.json)
     3 style-guide        style-guide.md
     4 features           pricing.md (the form you type prices into) · features.md · cta-pages.md
     5 writing-examples   writing-examples.md
     6 persona            persona.md
     7 writing-integrity  writing-integrity.md · seo-aeo-geo-checklist.md
     8 writer-brief       writer-brief.md · writer-brief-rulings.md
     9 brand-cards        brand-cards.json
    10 field-sources      field-sources.md

The original's twelfth was `voices`, which laid out voices.md for the team to fill in with their
bylines. Deleted 2026-09-09 on the owner's word: "remove completely everything about the byline
questions, everything from Sutra for now."

Resumable: a builder whose files exist is skipped unless `redo` is set or `only` names it. One
builder failing is said and the rest still run (a later builder that needs the missing file says so
itself). The human gates of the original are checkpoints here: everything is saved, and
`needs_review` lists what a person still has to confirm, so the agent can show the pack.
"""
from .. import store
from ..brand import (brand_cards, brand_facts, brand_voice, features, field_sources, pack, persona,
                     style_guide, type_roles, writer_brief, writing_examples, writing_integrity)
from . import _shared as sh

# (key, module, the files that mark it done), in the original's run order
BUILDERS = [
    ("type-roles", type_roles, ["type-roles.json"]),
    ("brand-facts", brand_facts, ["stats.md", "stories.md"]),
    ("brand-voice", brand_voice, ["brand-voice.md"]),
    ("style-guide", style_guide, ["style-guide.md"]),
    ("features", features, ["features.md", "cta-pages.md"]),   # and brand/pricing.md, the form
    ("writing-examples", writing_examples, ["writing-examples.md"]),
    ("persona", persona, ["persona.md"]),
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
    # Say it once, at the top, rather than four builders each raising the same thing. Five of the
    # twelve choose which pages to learn from by traffic; with none measured they would learn the
    # brand from whatever page sorts first.
    from ..brand import _common as _cm
    if not _cm.have_traffic():
        return {"summary": "The brand pack was not built: there is no measured search traffic.",
                "error": ("Five of the builders (the voice, the style guide, the product facts, the "
                          "worked examples and the call-to-action pages) choose which of your pages "
                          "to learn from by how much search traffic each one gets. There is none on "
                          "file, so they would learn your brand from whatever page happens to sort "
                          "first. Connect DataForSEO and run the site read again, or import a "
                          "traffic file in Knowledge. I will not guess at this.")}
    wanted = _only(only)
    redo = bool(redo)

    files, needs_review, built, skipped, failed = [], [], [], [], []
    for key, mod, outputs in BUILDERS:
        if wanted and key not in wanted:
            continue
        force = redo or key in wanted
        # brand-facts decides per file whether a draft is due (a confirmed file is never touched),
        # so it always gets a look. features gets one too when brand/pricing.md has changed under
        # it: somebody typed in a price the crawler cannot see, and features.md is the file that
        # has to carry it. That rebuild reuses the pages already read, so it costs no crawl.
        # The rest are done once their files exist.
        always_look = key == "brand-facts" or (key == "features" and features.pricing_stale())
        if not force and not always_look and all(sh.brand_file(f) or store.knowledge("brand/" + f) for f in outputs):
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
