"""brand/features.py — builder 4: what the product is, from its own commercial pages, plus the
short list of pages a call to action may link to.

Port of 3-features/scripts/run_features.py + build_cta_pages.py.

Step 1 discover the commercial/product pages: code filters by the classified commercial (and stat)
       types plus the recipe's URL signals; big kinds are capped per kind by traffic (FT_KIND_CAP).
Step 2 collect the facts, one model call per page with the recipe's exact eight categories. Resumable.
Step 3 fill the schema: pure assembly. Appendix A, the consolidation method and the mapping table are
       lifted verbatim. brand/pricing.md, the facts a person typed in by hand, wins over the crawl.
Step 4 the quality gate (completeness, facts-only, consolidation), looped back to step 3, capped at 3.
Step 5 the CTA page list: code only, from the crawl. features.md is prose a model wrote; a wrong URL in
       a call to action sends a reader to the wrong page, so the link targets are never a model's. The
       file's format belongs to brand/cta.py, which the Knowledge screen writes through too, so a page
       the owner added by hand survives this rebuild instead of being overwritten by it.

Reads:  the catalogue, brand/type-roles.json, brand/brand-voice.md (pitch wording), brand/pricing.md.
Writes: brand/pricing.md (the empty form, once) · brand/_work/features/{source-pages.json, facts.json,
        gate-round-N.json, pricing-stamp.json} · brand/features.md · brand/cta-pages.md
"""
import hashlib
import json
import re

from .. import llm
from . import _common as cm
from . import cta

OUTPUT = "features.md"
CTA_OUTPUT = cta.OUTPUT          # the format, and the file name, belong to brand/cta.py
WORK = "_work/features/"

# THE FACTS A CRAWLER CANNOT REACH. Some pages draw their prices with JavaScript, so those facts
# are in neither the site catalogue nor the raw HTML; only a person with a browser can read them.
# Testlify's whole pricing table is one, verified 2026-07-20 against testlify.com/pricing/.
#
# The original called this file `_seed/features-seed.md` and had a person fill it in by hand
# (3-features/scripts/run_features.py::_seed). Sutra read the same path and called it authoritative
# while nothing could ever write it: it is not a name the Knowledge tab offers, and the API's
# filename rule rejects any path with a slash in it, so it could only ever be empty (finding 8.21).
# Renamed to pricing.md on the owner's word, 2026-09-09: "we will not call it features seed or md,
# we will call it pricing.md". Flat, at the top of the brand folder, so it is a plain name the
# Knowledge tab can open, edit and save like any other brand file.
PRICING = "pricing.md"
LEGACY_PRICING = "_seed/features-seed.md"   # what the original called it; read once, then migrated
STAMP = WORK + "pricing-stamp.json"         # the pricing.md that features.md was last filled from

FT_KIND_CAP = 25            # product/competitor pages per kind, by traffic (pricing/compare/homepage/integrations always all)
FT_BODY_CAP = 12000         # chars of one page body per facts prompt
GATE_ROUNDS = 3
VOICE_CHARS = 6000          # of brand-voice.md shown for pitch wording

_KIND_HINTS = [
    (re.compile(r"/(pricing|plans|compare)", re.I), "pricing / plans / compare"),
    (re.compile(r"alternatives|-vs-", re.I), "competitor comparison"),
    (re.compile(r"integration", re.I), "integrations"),
]
UNCAPPED = ("homepage", "pricing / plans / compare", "integrations")
FACT_KEYS = ("features", "integrations", "pricing", "competitive", "social_proof", "audience", "ctas", "faq")

# --- the CTA page list (build_cta_pages.py) -----------------------------------------------------
# A leaf page sells one test to one role. A CTA wants the hub above it.
LEAF = ("/test-library/",)
# Kinds worth linking from a close. Competitor comparisons are deliberately absent: they belong in a
# comparison article's own body, chosen by the links step, not bolted onto every article's ending.
KINDS = ("homepage", "product or feature page", "pricing / plans / compare")
# Localised and superseded duplicates of a page we already list.
SKIP = re.compile(r"/(compare-planos|comparer-les-plans|pricing-new|compare-testlify-vs-)", re.I)
# A page whose URL reads like an article, not a product. The crawler files some of these as product
# pages because they carry a product CTA block.
ARTICLEY = re.compile(r"interview-questions|-to-ask-|how-to-|top-\d", re.I)


# ---- step 1 -----------------------------------------------------------------------------------

def discover(co, say):
    rows = cm.ok_pages(co.get("language_code"))
    roles = cm.roles()
    ctypes = set((roles.get("commercial_types") or []) + (roles.get("stat_types") or []))
    if not ctypes:
        say("Commercial page types", "no type roles on file, so URL signals only")
    tmap = cm.traffic_map()
    picked = {}
    for r in rows:
        url = r["url"]
        kind = next((k for rx, k in _KIND_HINTS if rx.search(url)), None)
        if kind is None and r.get("type") in ctypes:
            kind = "homepage" if cm.is_home(url, co["domain"]) else "product or feature page"
        if kind is None and cm.is_home(url, co["domain"]):
            kind = "homepage"
        if kind:
            picked[url] = {"url": url, "kind": kind, "traffic": cm.traffic_of(r, tmap),
                           "title": r.get("title") or "", "body": (r.get("body") or "")[:FT_BODY_CAP]}
    by_kind = {}
    for p in picked.values():
        by_kind.setdefault(p["kind"], []).append(p)
    final = []
    for kind, grp in by_kind.items():
        grp.sort(key=lambda p: -p["traffic"])
        cap = len(grp) if kind in UNCAPPED else FT_KIND_CAP
        final.extend(grp[:cap])
        if len(grp) > cap:
            say("Capped a page kind", "%s: %d found, top %d by traffic kept" % (kind, len(grp), cap))
    cm.save(WORK + "source-pages.json", final)
    say("Found the product pages", "%d pages across %d kinds" % (len(final), len(by_kind)))
    return final


# ---- step 2 -----------------------------------------------------------------------------------

def collect(co, pages, say, redo=False):
    name = WORK + "facts.json"
    done = {}
    if not redo:
        for f in (cm.read(name) or []):
            if isinstance(f, dict) and f.get("url"):
                done[f["url"]] = f
    tpl = cm.prompt("extract-facts")
    todo = [p for p in pages if p["url"] not in done]
    say("Collecting the facts", "%d cached, %d pages to read, %d at a time" % (len(done), len(todo), llm.PARALLEL))

    def one(p):
        out = llm.json_call(cm.fill(tpl, brand=co["brand"], url=p["url"], kind=p["kind"], body=p["body"]))
        out = dict(out) if isinstance(out, dict) else {}
        for k in FACT_KEYS:
            v = out.get(k)
            out[k] = [str(x) for x in v if str(x).strip()] if isinstance(v, list) else ([str(v)] if v else [])
        out.update(url=p["url"], kind=p["kind"])
        return out

    for p, res, err in cm.parallel(one, todo, say, "Reading product pages", every=10):
        if err:
            say("Could not read a product page", "%s: %s" % (p["url"], str(err)[:80]))
        else:
            done[res["url"]] = res
    facts = [done[p["url"]] for p in pages if p["url"] in done]
    cm.save(name, facts)
    say("Facts pool", "%d pages" % len(facts))
    return facts


# ---- pricing.md: the human half of the facts ---------------------------------------------------

def _squash(text):
    """Whitespace collapsed, so a stray blank line is not mistaken for something somebody typed."""
    return " ".join((text or "").split())


def untouched(text, name=PRICING):
    """Is this still the blank form, with nothing typed into it?

    Compared against the template itself rather than hunting for a placeholder marker. A person who
    types their prices but leaves a line of the form's own wording behind still gets their prices
    used, which is the only direction this is allowed to be wrong in: silently dropping the one
    thing a crawler could never reach is the failure that matters.

    `name` says WHICH form, so this answers the question for the whole class of typed-in files
    rather than for pricing.md alone; brand/_common.INPUTS is the one list of them. A file that is
    not on disk reads as its blank form (cm.read), so it lands here as untouched too, which is the
    honest answer: nobody has typed in it.
    """
    return not (text or "").strip() or _squash(text) == _squash(cm.blank_form(name))


def pricing():
    """brand/pricing.md — the human-verified facts, or "" while the form is still blank.

    Falls back to the original's own path and migrates it across, once. The owner has real prices
    sitting in `_seed/features-seed.md` from before the rename and they must not be lost. The old
    file is left where it is: it is his text, and deleting somebody's file to tidy up a rename is
    not this builder's call.
    """
    text = cm.read(PRICING)
    if not untouched(text):
        return text
    old = cm.read(LEGACY_PRICING)
    if (old or "").strip():
        cm.save(PRICING, old)
        return old
    return ""


def ensure_pricing(say):
    """Put the blank form on disk when it is not there. A file that does not exist has no door in
    the Knowledge tab — nothing to open, nothing to type into — which is exactly how the seed
    stayed permanently empty. The form is instantiated the way brand/writer_brief.py instantiates
    its rulings file: present, obviously blank, and never mistaken for content by pricing()."""
    if cm.exists(PRICING):
        return False
    cm.save(PRICING, cm.blank_form(PRICING))
    say("Put out the prices form", "brand/pricing.md — type in what your site draws with JavaScript")
    return True


def _fingerprint(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _stamp():
    cm.save(STAMP, {"pricing": _fingerprint(pricing()), "at": cm.today()})


HAND_EDITED = "changed-by-hand"      # never equals a fingerprint, which is 64 hex characters


def pricing_saved():
    """Somebody saved pricing.md. Mark features.md as due a rebuild and return whether it is.

    Called from the save that a person's edit goes through. It does no model work of its own: the
    rebuild is slow, and a save must come back straight away.
    """
    if not cm.exists(OUTPUT):
        return False                 # nothing built yet; the ordinary build will read pricing.md
    cm.save(STAMP, {"pricing": HAND_EDITED, "at": cm.today()})
    return True


def pricing_stale():
    """Was features.md filled from a different pricing.md than the one on disk now?

    A MISSING stamp is not staleness. A features.md built before this stamp existed is no evidence
    that anything changed, and a rebuild costs model calls; the stamp appears the first time fill()
    runs, and from then on every change is caught.
    """
    if not cm.exists(OUTPUT):
        return False
    stamp = cm.read(STAMP)
    if not isinstance(stamp, dict) or "pricing" not in stamp:
        return False
    return stamp["pricing"] != _fingerprint(pricing())


# ---- steps 3 + 4 ------------------------------------------------------------------------------

def _pool(facts):
    blocks = []
    for f in facts:
        body = "\n".join("- %s: %s" % (k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
                         for k, v in f.items() if k not in ("url", "kind") and v)
        blocks.append("## %s  (%s)\n%s" % (f["url"], f["kind"], body))
    return "\n\n".join(blocks)


def fill(co, facts, say, redo_notes=""):
    seed = pricing()                 # HUMAN-VERIFIED facts the crawler cannot reach; authoritative
    voice = cm.read("brand-voice.md")[:VOICE_CHARS]
    p = cm.fill(cm.prompt("fill-schema"), brand=co["brand"], niche=co.get("niche_definition") or "",
                schema=cm.template("features-schema"), method=cm.template("features-method"),
                mapping=cm.template("features-mapping"), voice=voice, facts=_pool(facts), seed=seed or "(no seed file)",
                redo_notes=("\nREDO NOTES (fix these):\n%s\n" % redo_notes) if redo_notes else "")
    draft = cm.strip_fence(llm.text(p, timeout=llm.LONG_TIMEOUT))   # a whole document in one call
    cm.save(OUTPUT, draft)
    _stamp()                         # this features.md was filled from THIS pricing.md
    say("Filled features.md", "%d words%s%s" % (cm.words(draft), "; your typed-in prices were applied" if seed else "",
                                                 " (rebuilt with the gate's notes)" if redo_notes else ""))
    return draft


def _flag_notes(draft):
    n = cm.count_lines(draft, "⚑ HUMAN DECISION")
    # The flag stays IN the document, where the quality gate depends on it and a reader sees the
    # reasoning beside it. It is no longer counted at the owner: he asked for every "to confirm"
    # badge gone, and a number with a symbol in front of it is exactly that.
    return ["features.md: %d places where the pages disagreed and someone has to choose" % n] if n else []


def gate(co, draft, round_n, say):
    v = llm.json_call(cm.fill(cm.prompt("features-quality-gate"), brand=co["brand"], draft=draft))
    v = dict(v) if isinstance(v, dict) else {"sections": [], "overall_pass": False, "redo_notes": ""}
    cm.save(WORK + "gate-round-%d.json" % round_n, v)
    say("Quality gate, round %d" % round_n, "pass" if v.get("overall_pass") else "fail")
    return v


def fill_and_gate(co, facts, say):
    """Fill the schema, then the quality gate, looping back into the fill up to GATE_ROUNDS times.
    Returns (draft, notes). The first build and a pricing.md rebuild both run exactly this."""
    notes = []
    draft = fill(co, facts, say)
    for n in range(1, GATE_ROUNDS + 1):
        v = gate(co, draft, n, say)
        if v.get("overall_pass"):
            break
        if n < GATE_ROUNDS:
            draft = fill(co, facts, say, redo_notes=str(v.get("redo_notes") or ""))
        else:
            notes.append("features.md: the quality gate still failed after %d rounds; the draft ships with its verdict" % n)
    return draft, notes


def rebuild_from_pricing(co, say):
    """pricing.md changed under a features.md that was already built, so fill it again.

    NO CRAWL. _work/features/facts.json is what the pages themselves said, and a price the crawler
    could never see does not change any of it; only the fill and the gate run again. Returns None
    when those cached facts are not on file, and the caller then runs the whole builder.

    THE CHAIN IS ONE HOP, DELIBERATELY (the owner's decision, 2026-09-09):

        pricing.md  ->  features.md            rebuilt, here
        features.md ->  writing-integrity.md   NOT rebuilt, his call
                    ->  writer-brief.md        NOT rebuilt, his call

    His words: "we can skip writing integrity, we can skip the writer brief as well. So just update
    the features.md, which is used while writing the final article." write/wrapper.py opens
    features.md fresh for every article, so the writer picks up a new price with no rebuild at all.
    Do not "fix" this by extending the chain.
    """
    facts = cm.read(WORK + "facts.json")
    if not isinstance(facts, list) or not facts:
        say("Cannot rebuild from your prices alone", "the pages this pack was read from are not on file, so the whole builder runs")
        return None
    say("Your prices changed", "filling features.md again from the %d pages already read; nothing is read again" % len(facts))
    draft, notes = fill_and_gate(co, facts, say)
    notes += _flag_notes(draft)
    return {"files": [OUTPUT] + ([CTA_OUTPUT] if cm.exists(CTA_OUTPUT) else []), "needs_review": notes}


# ---- step 5: the CTA page list (code only) -----------------------------------------------------

def cta_rows(facts, pages):
    """(rows, dropped): the pages a close may link to, homepage first then by traffic, and every
    candidate that was dropped with its reason. Filtered by SHAPE, never ranked by traffic alone."""
    by_url = {p["url"]: p for p in pages}
    rows, dropped = [], []
    for f in facts:
        url, kind = f.get("url", ""), f.get("kind", "")
        why = None
        if kind not in KINDS:
            why = "kind is %s" % kind
        elif any(x in url for x in LEAF):
            why = "leaf page — one test for one role"
        elif SKIP.search(url):
            why = "localised or superseded duplicate"
        elif ARTICLEY.search(url):
            why = "reads as an article, not a product page"
        if why:
            dropped.append((url, why))
            continue
        p = by_url.get(url, {})
        feats = [x for x in (f.get("features") or []) if str(x).strip()][:3]
        rows.append({"url": url, "title": (p.get("title") or "").strip(), "traffic": int(p.get("traffic") or 0),
                     "kind": kind, "features": feats})
    rows.sort(key=lambda r: (r["kind"] != "homepage", -r["traffic"]))
    return rows, dropped


def build_cta_pages(co, facts, pages, say):
    """The crawl's half of the list. brand/cta.py merges it under the rows a person added by hand
    and does the writing, so this step never decides what the file looks like."""
    rows, dropped = cta_rows(facts, pages)
    kept, _d = cta.rebuild(co["brand"], rows, dropped)
    mine = sum(1 for r in kept if r.get("mine"))
    say("Built the CTA page list", "%d linkable pages%s, %d dropped"
        % (len(kept), (" (%d of them yours, kept)" % mine) if mine else "", len(dropped)))
    return kept, dropped


# ---- the builder ------------------------------------------------------------------------------

def run(co, say, redo=False):
    # The form first, always: a file that is not on disk has no door in the Knowledge tab, and a
    # door nobody can open is how the seed stayed empty for good.
    ensure_pricing(say)
    if cm.exists(OUTPUT) and not redo and pricing_stale():
        out = rebuild_from_pricing(co, say)
        if out is not None:
            return out
    cm.require_traffic("The product facts builder")
    if cm.exists(OUTPUT) and cm.exists(CTA_OUTPUT) and not redo:
        say("Kept features.md and cta-pages.md", "already built; ask for a redo to rebuild them")
        return {"files": [OUTPUT, CTA_OUTPUT], "needs_review": []}
    notes = []
    pages = discover(co, say)
    if not pages:
        raise RuntimeError("No commercial or product pages were found in the site index.")
    facts = collect(co, pages, say, redo=redo)
    if cm.exists(OUTPUT) and not redo:
        say("Kept features.md", "already built")
        draft = cm.read(OUTPUT)
    else:
        draft, gate_notes = fill_and_gate(co, facts, say)
        notes += gate_notes
    notes += _flag_notes(draft)
    rows, _dropped = build_cta_pages(co, facts, pages, say)
    if not rows:
        notes.append("cta-pages.md: no page survived the filters, so a close has nothing to link to")
    return {"files": [OUTPUT, CTA_OUTPUT], "needs_review": notes}
