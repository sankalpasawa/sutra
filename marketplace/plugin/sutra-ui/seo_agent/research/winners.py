"""winners.py — Step 5: read the winning pages (free), write "What the winners cover", then lift the
three lists out of it verbatim.

Ported from 10-dataforseo/scripts/s5_pages.py + s5b_winners.py and the conductor's
spine._competitor_read (prompts/extract-winners.md). Pages are read with a plain HTTP request:
h1-h3 (up to 15) and a word count; a page that fails three tries is skipped and noted, never faked.

Reads: the read-list, angle, primary, company. Writes (via the tool): _work/pages.json, _work/winners.json.
"""
import json
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as _c
from . import web


def read_pages(urls, demo=False, say=None):
    """{url: {word_count, headings, title, attempts} | {error}} — the page TEXT is kept in a separate
    key so the winners prompt sees only the structure the original saw."""
    out = {}

    def _one(u):
        if demo:
            return u, web.demo_page(u)
        try:
            return u, web.fetch(u)
        except Exception as e:  # noqa: BLE001 — skipped and noted, never faked
            return u, {"error": str(e)[:80]}

    with ThreadPoolExecutor(max_workers=_c.PAGE_FETCH_WORKERS) as ex:
        for u, page in ex.map(_one, urls):
            out[u] = page
            if say:
                if page.get("error"):
                    say("Could not read %s" % _c.bare_domain(u), page["error"])
                else:
                    say("Read %s" % _c.bare_domain(u),
                        "%s words, %s headings" % (format(page.get("word_count", 0), ","), len(page.get("headings") or [])))
    return out


def structure_only(pages):
    """What the winners prompt reads: url → {word_count, headings} (plus the error where one failed)."""
    slim = {}
    for u, p in (pages or {}).items():
        slim[u] = {"error": p["error"]} if p.get("error") else \
            {"word_count": p.get("word_count"), "headings": p.get("headings") or []}
    return slim


def write_up(pages, angle, primary, company, paa=None):
    """The study, and the gap list inside it.

    `paa` is the People Also Ask questions off the SERP snapshot, and it is what makes a gap a gap
    (owner, 2026-09-22). The prompt used to ask for gaps "judged against the distinct angle", which
    handed our own angle back as an opportunity: on Recruiting Metrics that produced two whole
    sections on the four-fifths rule, which nobody searching "recruiting metrics" had asked for,
    while Source of Hire and Offer Acceptance Rate -- covered by every ranking page -- were dropped
    entirely. A gap must now name a reader who wants it, and the PAA is where that reader is
    visible.

    A missing PAA becomes a plain note rather than an empty block: "(none captured)" tells the
    model there is no demand signal to point at, which correctly makes a gap HARDER to claim,
    where an empty string would read as a formatting slip and be ignored.
    """
    tok = _c.company_tokens(company)
    asked = [str(q).strip() for q in (paa or []) if str(q).strip()]
    p = _c.prompt("winners", brand=tok["brand"], distinct_angle=angle or "(none given yet)",
                  primary_keyword=primary, parsed_pages=json.dumps(structure_only(pages), indent=2),
                  paa="\n".join("- " + q for q in asked) or "(none captured for this search)")
    return (llm.text(p) or "").rstrip()


def extract(md):
    """The four things lifted VERBATIM out of the study: format, gaps_to_own, common_h2s, drift."""
    got = llm.json_call(_c.prompt("extract-winners", winners=md)) or {}
    if not isinstance(got, dict):
        got = {}
    return {"format": str(got.get("format") or "").strip(),
            "gaps_to_own": _c.strings(got.get("gaps_to_own")),
            "common_h2s": _c.strings(got.get("winners_common_h2s")),
            "drift": _c.strings(got.get("winners_drift"))}


def route_format(format_label, title="", angle="", winners_study=""):
    """The winners' free-text page-format guess -> one of the 8 write-phase archetypes, with a
    one-line reason. ONE AI call, made ONCE, at the run_research checkpoint right after this study
    (moved from write/fmt_router.py, deleted 2026-09-16 with the write-phase "route" step it used to
    be: the archetype is now decided once, by a person, at the checkpoint, never re-routed while
    writing). Also used, as a fallback only, to settle an old or resumed run's decisions file.

    An unknown reply is a ValueError: the architect cannot shape an article to a format that does
    not exist, and a silent default here would hide that the model misbehaved.
    """
    from ..write import _common as wc     # lazy: write/ does not import research/ back
    out = llm.json_call(_c.prompt("format-archetype",
                                  format=(format_label or "").strip() or "(none given)",
                                  title=(title or "").strip() or "(none given)",
                                  angle=(angle or "").strip() or "(none given)",
                                  winners=(winners_study or "").strip() or "(not available)")) or {}
    arch = str(out.get("archetype") or "").strip()
    why = str(out.get("why") or "").strip()
    if arch not in wc.ARCHETYPES:
        raise ValueError("the format router returned an unknown archetype %r for format %r"
                         % (arch, format_label))
    return arch, why
