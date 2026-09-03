"""brand/features.py — builder 4: what the product is, from its own commercial pages, plus the
short list of pages a call to action may link to.

Port of 3-features/scripts/run_features.py + build_cta_pages.py.

Step 1 discover the commercial/product pages: code filters by the classified commercial (and stat)
       types plus the recipe's URL signals; big kinds are capped per kind by traffic (FT_KIND_CAP).
Step 2 collect the facts, one model call per page with the recipe's exact eight categories. Resumable.
Step 3 fill the schema: pure assembly. Appendix A, the consolidation method and the mapping table are
       lifted verbatim. A human-verified seed (brand/_seed/features-seed.md), when present, wins.
Step 4 the quality gate (completeness, facts-only, consolidation), looped back to step 3, capped at 3.
Step 5 the CTA page list: code only, from the crawl. features.md is prose a model wrote; a wrong URL in
       a call to action sends a reader to the wrong page, so the link targets are never a model's.

Reads:  the catalogue, brand/type-roles.json, brand/brand-voice.md (pitch wording), brand/_seed/features-seed.md.
Writes: brand/_work/features/{source-pages.json, facts.json, gate-round-N.json} · brand/features.md · brand/cta-pages.md
"""
import json
import re

from .. import llm
from . import _common as cm

OUTPUT = "features.md"
CTA_OUTPUT = "cta-pages.md"
WORK = "_work/features/"

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
DROPPED_SHOWN = 60


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


# ---- steps 3 + 4 ------------------------------------------------------------------------------

def _pool(facts):
    blocks = []
    for f in facts:
        body = "\n".join("- %s: %s" % (k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
                         for k, v in f.items() if k not in ("url", "kind") and v)
        blocks.append("## %s  (%s)\n%s" % (f["url"], f["kind"], body))
    return "\n\n".join(blocks)


def fill(co, facts, say, redo_notes=""):
    seed = cm.read("_seed/features-seed.md")     # HUMAN-VERIFIED facts the crawler cannot reach; authoritative
    voice = cm.read("brand-voice.md")[:VOICE_CHARS]
    p = cm.fill(cm.prompt("fill-schema"), brand=co["brand"], niche=co.get("niche_definition") or "",
                schema=cm.template("features-schema"), method=cm.template("features-method"),
                mapping=cm.template("features-mapping"), voice=voice, facts=_pool(facts), seed=seed or "(no seed file)",
                redo_notes=("\nREDO NOTES (fix these):\n%s\n" % redo_notes) if redo_notes else "")
    draft = cm.strip_fence(llm.text(p, timeout=llm.LONG_TIMEOUT))   # a whole document in one call
    cm.save(OUTPUT, draft)
    say("Filled features.md", "%d words%s%s" % (cm.words(draft), "; the human-verified seed was applied" if seed else "",
                                                 " (rebuilt with the gate's notes)" if redo_notes else ""))
    return draft


def gate(co, draft, round_n, say):
    v = llm.json_call(cm.fill(cm.prompt("features-quality-gate"), brand=co["brand"], draft=draft))
    v = dict(v) if isinstance(v, dict) else {"sections": [], "overall_pass": False, "redo_notes": ""}
    cm.save(WORK + "gate-round-%d.json" % round_n, v)
    say("Quality gate, round %d" % round_n, "pass" if v.get("overall_pass") else "fail")
    return v


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
    rows, dropped = cta_rows(facts, pages)
    out = ["# %s — pages a call to action may link to" % co["brand"], "",
           "Built by code from the site crawl. Every URL here was fetched and is live.",
           "The close of an article links to ONE of these and nothing else.", "",
           "%d pages. %d candidates were dropped; the reasons are at the foot." % (len(rows), len(dropped)), ""]
    for r in rows:
        out.append("## %s" % (r["title"] or r["url"]))
        out.append("- Page: %s" % r["url"])
        out.append("- Kind: %s  ·  %s visits a month" % (r["kind"], format(r["traffic"], ",")))
        for x in r["features"]:
            out.append("- %s" % x)
        out.append("")
    out += ["---", "", "## Dropped, and why", ""]
    out += ["- %s  — %s" % (u, w) for u, w in dropped[:DROPPED_SHOWN]]
    if len(dropped) > DROPPED_SHOWN:
        out.append("- ... and %d more" % (len(dropped) - DROPPED_SHOWN))
    cm.save(CTA_OUTPUT, "\n".join(out) + "\n")
    say("Built the CTA page list", "%d linkable pages, %d dropped" % (len(rows), len(dropped)))
    return rows, dropped


# ---- the builder ------------------------------------------------------------------------------

def run(co, say, redo=False):
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
        draft = fill(co, facts, say)
        for n in range(1, GATE_ROUNDS + 1):
            v = gate(co, draft, n, say)
            if v.get("overall_pass"):
                break
            if n < GATE_ROUNDS:
                draft = fill(co, facts, say, redo_notes=str(v.get("redo_notes") or ""))
            else:
                notes.append("features.md: the quality gate still failed after %d rounds; the draft ships with its verdict" % n)
    n_flags = cm.count_lines(draft, "⚑ HUMAN DECISION")
    if n_flags:
        notes.append("features.md: %d ⚑ HUMAN DECISION flags to settle" % n_flags)
    rows, _dropped = build_cta_pages(co, facts, pages, say)
    if not rows:
        notes.append("cta-pages.md: no page survived the filters, so a close has nothing to link to")
    return {"files": [OUTPUT, CTA_OUTPUT], "needs_review": notes}
