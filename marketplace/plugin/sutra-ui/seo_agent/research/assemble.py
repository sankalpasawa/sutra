"""assemble.py — Step 7: the Verdict and the Build spec, the only two things the model writes.

Ported from 10-dataforseo/scripts/s7_assemble.py. Everything else in the brief is lifted from the
earlier steps by code; the completeness checks are computed in code, and a box is ticked only when
its check passes. The build spec is derived from the brand's SEO/AEO/GEO checklist; when the model
returns the word band as text, the conductor's bundle regex recovers the two numbers.

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
