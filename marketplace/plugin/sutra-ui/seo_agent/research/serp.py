"""serp.py — Step 4: the live SERP on the primary keyword, then the SERP-snapshot write-up.

Ported from 10-dataforseo/scripts/s4_serp.py + s4b_snapshot.py. The SERP is read once, with the
AI Overview block loaded. The snapshot is an LLM structuring pass in a FIXED shape; the ```readlist
block it appends is parsed in code (exactly 3 URLs, else the raw top-3), and the on/off-angle
lists are parsed out of the markdown in code so the brief carries them as data.

Reads: the primary keyword, topic, angle, world, company.
Writes (via the tool): _work/serp.json {extract, cost}, _work/snapshot.json.
"""
import json
import re

from .. import llm
from .. import llm
from ..tools import dfs
from . import _common as _c


def fetch(primary, company):
    got = dfs.serp_advanced(primary, depth=_c.SERP_DEPTH, paa_click_depth=_c.PAA_CLICK_DEPTH, ai_overview=True,
                            location_name=company.get("location_name") or "United States",
                            language_code=company.get("language_code") or "en")
    return {"extract": got.get("extract") or {}, "cost": got.get("cost") or 0.0, "demo": bool(got.get("demo"))}


def same_article(keyword, extract, topic, world, company=None):
    """Would somebody searching this keyword recognise our article as the right kind of page?

    (ok, why). Fails OPEN in every direction: no pages, an unreadable reply, an exception -- all
    answer yes. A check that cannot run must never be the reason a run stops, and the cost of a
    false rejection is a worse keyword, which is the thing this exists to prevent.

    WHY IT EXISTS (owner, 2026-09-22). The keyword judge is told to take the highest-volume head
    term that clears difficulty, and nothing ever asked whether a page ranking for it would be THIS
    article. "Skills Assessment: From Resume Claim to Cut Score" was built on "behavioral interview
    questions" (12,100/mo), so the winners it studied were "30 questions to ask" listicles and every
    demand signal for the run -- table stakes, format, gaps, the rewritten angle -- came from the
    wrong article. The run cost $0.44 of DataForSEO and hours of model time researching something
    else. One model call here is the cheapest guard in the engine.
    """
    rows = [r for r in (extract or {}).get("top_organic") or [] if isinstance(r, dict) and r.get("url")]
    if not rows:
        return True, "no ranking pages came back, so there is nothing to check against"
    listed = "\n".join("- %s\n  %s" % ((r.get("title") or "(no title)").strip(), r["url"])
                        for r in rows[:10])
    try:
        got = llm.json_call(_c.prompt("same-article", topic=_c.na(topic),
                                      keyword=keyword, ranking_pages=listed,
                                      **_c.world_tokens(world))) or {}
    except Exception as e:      # noqa: BLE001 -- see "fails OPEN" above
        return True, "the check could not run (%s)" % str(e)[:80]
    if not isinstance(got, dict) or "same_article" not in got:
        return True, "the check gave no verdict, so the keyword stands"
    return bool(got.get("same_article")), str(got.get("why") or "").strip()


def _readlist(text, extract):
    """The fenced ```readlist block the prompt appends, kept to URLs that are really in the extract;
    exactly PAGES_TO_READ of them, topped up from the raw top organic when the model gave fewer."""
    real = [r["url"] for r in (extract.get("top_organic") or []) if r.get("url")]
    urls = []
    if "```readlist" in text:
        block = text.split("```readlist", 1)[1].split("```", 1)[0]
        for ln in block.splitlines():
            u = ln.strip()
            if u.startswith("http") and u in real and u not in urls:
                urls.append(u)
    for u in real:
        if len(urls) >= _c.PAGES_TO_READ:
            break
        if u not in urls:
            urls.append(u)
    return urls[:_c.PAGES_TO_READ]


def parse_snapshot(md):
    """The fixed-shape sections, as lists, so the brief carries them as data."""
    who = _c.md_section(md, r"Who ranks:")
    who_lines = [ln for ln in who.splitlines() if not re.match(r"\s*-\s*Open gap\b", ln, re.I)]
    gap_lines = [ln for ln in who.splitlines() if re.match(r"\s*-\s*Open gap\b", ln, re.I)]
    return {
        "who_ranks_text": "\n".join(who_lines).strip(),      # WITHOUT the gap line (the topic gate must not see it)
        "open_gap": re.sub(r"^\s*-\s*Open gap:?\s*", "", gap_lines[0], flags=re.I).strip() if gap_lines else "",
        "featured_snippet_text": _c.md_section(md, r"Featured snippet:"),
        "ai_overview_text": _c.md_section(md, r"AI Overview"),
        "paa_on": _c.md_items(_c.md_section(md, r"PAA\W+on-angle")),
        "paa_off": _c.md_items(_c.md_section(md, r"PAA\W+off-angle")),
        "related_on": _c.md_items(_c.md_section(md, r"Related searches\W+on-angle")),
        "related_off": _c.md_items(_c.md_section(md, r"Related searches\W+off-angle")),
    }


def snapshot(extract, topic, angle, world, primary, company):
    tok = _c.company_tokens(company)
    p = _c.prompt("serp-snapshot", brand=tok["brand"], domain=tok["domain"], asset_topic=topic,
                  distinct_angle=angle or "(none given yet)", primary_keyword=primary,
                  serp_extract=json.dumps(extract, indent=2), **_c.world_tokens(world))
    text = llm.text(p) or ""
    urls = _readlist(text, extract)
    md = text.split("```readlist")[0].rstrip()          # strip the machine block from the human doc
    out = {"md": md, "readlist": urls}
    out.update(parse_snapshot(md))
    return out
