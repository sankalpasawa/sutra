"""topic_gate.py — Step 1b: is this topic ours, and what is the real angle?

Ported from 14-research-conductor/scripts/topic_gate.py. TWO CALLS, NOT ONE, AND THE ORDER MATTERS.
  1. IS THIS OURS? Sees the brand scope, who ranks (WITHOUT the gap line), Google's answer, and what
     every page covers. It deliberately does NOT see the gaps: hand a judge a list of openings and it
     talks itself into "worth doing". Fails OPEN: a gate that drops topics on a malformed reply is
     worse than one that lets one through, because the article is reviewed and a dropped topic is not.
  2. WHAT IS THE ANGLE? Only when the first says yes. Sees the gaps and REPLACES the given angle.

The brand scope here is the company record's one-liner plus its niche definition (the original read
the asset engine's brand-scope.md, which this agent does not have).

Reads: topic, angle, the snapshot, the winners lists, company. Writes (via the tool): _work/topic-gate.json.
"""
from .. import llm
from . import _common as _c


def brand_scope(company):
    parts = [company.get("brand_oneliner") or "", company.get("niche_definition") or ""]
    parts = [p.strip() for p in parts if p and p.strip()]
    return "\n".join("- " + p for p in parts)


def run(topic, angle, snapshot, lists, company):
    tok = _c.company_tokens(company)
    scope = brand_scope(company)
    common = _c.render(lists.get("common_h2s"))
    aio = (snapshot.get("ai_overview_text") or "").strip() or "(no AI Overview captured for this search)"
    verdict = {"relevant": True, "why": "", "angle": angle or "", "angle_changed": False,
               "why_changed": "", "angle_before": angle or ""}
    if not scope:
        verdict["why"] = "not judged — no brand scope on file (add a one-line description and a niche to the company record)"
        return verdict

    # ---- call 1: is this ours? ------------------------------------------------------------
    p1 = _c.prompt("topic-relevance", brand=tok["brand"], brand_scope=scope,
                   who_ranks=snapshot.get("who_ranks_text") or "(no ranking summary captured)",
                   ai_overview=aio, common_topics=common)
    got = llm.json_call(p1) or {}
    if not isinstance(got, dict) or "relevant" not in got:
        verdict["why"] = "not judged — the relevance call returned no verdict, so the topic passes"
        got = {"relevant": True}
    else:
        verdict["why"] = str(got.get("why") or "").strip()
    verdict["relevant"] = bool(got.get("relevant"))
    if not verdict["relevant"]:
        return verdict

    # ---- call 2: what is the real angle? --------------------------------------------------
    p2 = _c.prompt("topic-angle", brand=tok["brand"], old_angle=angle or "(none recorded)",
                   gaps=_c.render(lists.get("gaps_to_own")), common_topics=common, ai_overview=aio)
    new, got2 = "", {}
    for _ in range(2):                      # a parse-clean reply with an empty field still slips through
        got2 = llm.json_call(p2) or {}
        got2 = got2 if isinstance(got2, dict) else {}
        new = str(got2.get("angle") or "").strip()
        if new:
            break
    if new:
        verdict.update(angle=new, angle_changed=new != (angle or ""),
                       why_changed=str(got2.get("why_changed") or "").strip())
    return verdict
