"""assemble.py — Step 7: the Verdict and the Build spec, the only two things the model writes.

Ported from 10-dataforseo/scripts/s7_assemble.py. Everything else in the brief is lifted from the
earlier steps by code; the completeness checks are computed in code, and a box is ticked only when
its check passes. The build spec is derived from the brand's SEO/AEO/GEO checklist; when the model
returns the word band as text, the conductor's bundle regex recovers the two numbers.

THE WORD BAND THIS STEP PRODUCES IS A MEASUREMENT, NOT A DECISION. It says how long the pages that
actually rank run. The length the article is written to is decided by a person, once, in the one
question run_research puts to them before the research conversation starts. `settle_word_band()`
below is where that answer replaces the measurement, and it is the ONLY place in the codebase that
writes the authoritative length. Everything downstream (the blueprint, gather, shape's WORD_BUDGET,
allocate_words, blend's LENGTH, readable's TARGET_WORDS) reads `build_spec.word_band` and therefore
reads the person's number.

Reads: keywords, snapshot md, winners md, the checklist. Writes (via the tool): _work/brief.json.
"""
import re

from .. import llm
from ..tools import _shared as sh
from . import _common as _c

# Tolerant of markdown around the label ('**Word band:**', 'Word band -'): match the phrase, skip any
# non-digit run, then capture the 'N,NNN-N,NNN' range. (14-research-conductor/scripts/bundle.py)
_WORD_BAND_RE = re.compile(r"Word band[^\d]{0,12}([\d,]{3,})\s*(?:-|–|—|to)\s*([\d,]{3,})", re.I)


def _kw_table(items, extra=None):
    cols = ["keyword", "vol", "KD"] + ([extra] if extra else [])
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols)
    body = "\n".join("| " + " | ".join(
        [str(i.get("keyword", "")), str(i.get("volume", "")), str(i.get("kd", ""))]
        + ([str(i.get("why", ""))] if extra else [])) + " |" for i in items)
    return head + "\n" + body


def keywords_md(final):
    """The Keywords section, rendered as the original rendered 03-keywords.md (the prompt reads it)."""
    pr = final.get("primary") or {}
    md = ["**Primary:** `%s`" % pr.get("keyword", ""),
          "- Volume: %s" % pr.get("volume"), "- KD: %s" % pr.get("kd"), "- Intent: %s" % (pr.get("intent") or "")]
    if pr.get("split_world"):
        md.append("- ⚠ Split-world phrase: part of this volume belongs to searchers in a different field "
                  "— the SERP will be mixed (see 'why').")
    md += ["- Why: %s" % pr.get("why", ""), ""]
    if final.get("variations"):
        md += ["**Variations** (rewords/synonyms of the primary — same intent; woven in-body, NO own section):", "",
               _kw_table(final["variations"]), ""]
    if final.get("secondary"):
        md += ["**Secondary** (no fixed cap — each anchors one section):", "",
               _kw_table(final["secondary"], extra="section it anchors"), ""]
    if final.get("in_body"):
        md += ["**In-body only** (core to the angle, no keyword clears the floor):"] + \
              ["- %s" % t for t in final["in_body"]] + [""]
    md += ["**Spokes** (own future articles):"] + \
          ["- %s (%s)" % (s.get("keyword"), s.get("volume")) for s in final.get("spoke_candidates", [])]
    return "\n".join(md) + "\n"


def _int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _word_band(spec, spec_text):
    """{min, max} from the structured reply, else from the text with the bundle's regex, else None."""
    wb = spec.get("word_band") if isinstance(spec, dict) else None
    if isinstance(wb, dict):
        lo, hi = _int(wb.get("min")), _int(wb.get("max"))
        if lo and hi:
            return {"min": min(lo, hi), "max": max(lo, hi)}
    if isinstance(wb, str):
        m = re.search(r"([\d,]{3,})\s*(?:-|–|—|to)\s*([\d,]{3,})", wb)
        if m:
            return {"min": _int(m.group(1)), "max": _int(m.group(2))}
    m = _WORD_BAND_RE.search(spec_text or "")
    if m:
        return {"min": _int(m.group(1)), "max": _int(m.group(2))}
    return None


# What the article is written to when nothing could be measured at all: no band came back from the
# model and none could be recovered from its text. It is only ever the SUGGESTION on the one length
# question, never a silent default, and the question says plainly that nothing was measured.
DEFAULT_WORDS = 2000

# A length a person could plausibly mean. Below 200 words it is not an article; above 20,000 it is a
# book. The same pair guards loop._resume_words, so a typed number is judged the same on both sides.
MIN_WORDS, MAX_WORDS = 200, 20000


def as_words(v):
    """A usable article length as an int, or None. Tolerant of "2,700", " 2700 " and 2700.0."""
    if isinstance(v, bool):
        return None
    try:
        n = int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None
    return n if MIN_WORDS <= n <= MAX_WORDS else None


def suggested_words(build_spec):
    """The number to offer the person: the middle of the measured band, or DEFAULT_WORDS when the
    band could not be measured.

    Deliberately NOT rounded to a tidy hundred. The question says "the average is N" and then
    offers N, so the two have to be the same number or the sentence is not true.
    """
    band = (build_spec or {}).get("word_band") or {}
    lo, hi = as_words(band.get("min")), as_words(band.get("max"))
    mid = ((lo + hi) // 2) if (lo and hi) else (lo or hi)
    return mid or DEFAULT_WORDS


def settle_word_band(build_spec, word_target):
    """Put the PERSON'S number into the build spec as the one and only word band.

    The owner, 2026-09-09: "you are not going to take the input which is there from the DataForSEO
    output file, you are going to take it from what the user has input." So the measured band moves
    to `word_band_measured`, where it stays on the record and is read by nobody, and `word_band`
    becomes the answer with min == max. Every reader downstream already takes `word_band`, which is
    why nothing else in the write phase had to learn a new key.

    Idempotent on purpose: a resumed run applies this to a build spec that may already be settled,
    and the measurement must not be overwritten by the answer on the second pass.
    """
    spec = dict(build_spec or {})
    n = as_words(word_target)
    if n is None:
        return spec
    if "word_band_measured" not in spec:
        spec["word_band_measured"] = spec.get("word_band")
    spec["word_band"] = {"min": n, "max": n}
    spec["word_band_source"] = "the person, asked once before the research conversation started"
    return spec


def run(topic, angle, final, snapshot_md, winners_md, company):
    tok = _c.company_tokens(company)
    checklist = sh.brand_file("seo-aeo-geo-checklist.md") or "(no SEO/AEO/GEO checklist on file yet)"
    kw_md = keywords_md(final)
    p = _c.prompt("assemble", brand=tok["brand"], asset_topic=topic, distinct_angle=angle or "(none given yet)",
                  keywords=kw_md, serp_snapshot=snapshot_md or "", winners=winners_md or "", checklist=checklist)
    syn = llm.json_call(p) or {}
    if not isinstance(syn, dict):
        syn = {}
    verdict = syn.get("verdict")
    if isinstance(verdict, str):
        verdict = [ln.strip().lstrip("-* ").strip() for ln in verdict.splitlines() if ln.strip()]
    verdict = _c.strings(verdict)
    spec = syn.get("build_spec")
    spec_text = spec if isinstance(spec, str) else ""
    spec = spec if isinstance(spec, dict) else {}
    build_spec = {
        "word_band": _word_band(spec, spec_text),
        "structure": _c.strings(spec.get("structure")) if spec else
                     [ln.strip().lstrip("-* ") for ln in spec_text.splitlines() if ln.strip()],
        "featured_snippet_target": str(spec.get("featured_snippet_target") or "").strip(),
        "primary_sources": _c.strings(spec.get("primary_sources")),
        "close": str(spec.get("close") or "").strip(),
        "checklist_on_file": bool(sh.brand_file("seo-aeo-geo-checklist.md")),
    }
    checks = [
        ("Anchors (title + angle)", bool(topic.strip()) and bool((angle or "").strip())),
        ("Keywords — primary + variations + secondaries + in-body", bool((final.get("primary") or {}).get("keyword"))),
        ("SERP snapshot · PAA · related", bool((snapshot_md or "").strip())),
        ("What the winners cover + gaps", bool((winners_md or "").strip())),
        ("Verdict", bool(verdict)),
        ("Build spec", bool(build_spec["word_band"] or build_spec["structure"])),
    ]
    return {"verdict": verdict, "build_spec": build_spec, "keywords_md": kw_md,
            "completeness": [{"check": label, "pass": ok} for label, ok in checks],
            "incomplete": [label for label, ok in checks if not ok]}
