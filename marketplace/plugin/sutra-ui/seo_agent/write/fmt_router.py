"""fmt_router.py — the format router: one article -> one of the 8 archetypes, by ONE AI call.

The whole routing brain (the 8 archetype definitions, the usual label->archetype table, the news-vs-data
care rule) lives in prompts/write/route-archetype.md, not here. This file only fills the prompt's blanks,
makes the one call, and validates the answer against ARCHETYPES. An unknown answer is a ValueError: the
architect cannot shape an article to a format that does not exist.
"""
from .. import llm
from . import _common as C


def winners_block(research):
    """The router's read of the winners study, rebuilt from the research brief's structured fields."""
    w = (research or {}).get("winners") or {}
    lines = []
    if w.get("format"):
        lines.append("Page format the winners confirm works: %s" % w["format"])
    if w.get("common_h2s"):
        lines.append("Headings the winning pages share: " + "; ".join(str(x) for x in w["common_h2s"]))
    if w.get("gaps_to_own"):
        lines.append("Gaps no winning page covers: " + "; ".join(str(x) for x in w["gaps_to_own"]))
    if w.get("drift"):
        lines.append("Where winners drift from the intent: " + "; ".join(str(x) for x in w["drift"]))
    return "\n".join(lines)


def route(format_name, title="", angle="", winners_study=""):
    """format label (+ title/angle/winners context) -> archetype. ONE AI call, validated against ARCHETYPES."""
    out = llm.json_call(C.prompt("route-archetype",
                                 format=(format_name or "").strip() or "(none given)",
                                 title=(title or "").strip() or "(none given)",
                                 angle=(angle or "").strip() or "(none given)",
                                 winners=(winners_study or "").strip() or "(not available)")) or {}
    arch = str(out.get("archetype") or "").strip()
    if arch not in C.ARCHETYPES:
        raise ValueError("router returned an unknown archetype %r for format %r" % (arch, format_name))
    return arch


def run(inputs, research, say=lambda *a: None):
    """The blueprint's archetype when it names a known one; otherwise route it."""
    a = inputs["group_a"]
    arch = str(a.get("format_archetype") or "").strip()
    if arch in C.ARCHETYPES:
        say("Format already decided", arch)
        return {"archetype": arch, "routed": False}
    fmt = a.get("format_label") or ""
    if not fmt:
        say("No format on file", "Deciding the article's shape from the title, angle and what already ranks")
    arch = route(fmt, title=a.get("title", ""), angle=a.get("angle", ""),
                 winners_study=winners_block(research))
    say("Format decided", arch)
    return {"archetype": arch, "routed": True}
