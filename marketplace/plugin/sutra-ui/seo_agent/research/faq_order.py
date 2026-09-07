"""faq_order.py — Blueprint step 8: FAQ + order.

Ported from 13-research-structure/scripts/faq_order.py. FAQ = the PAA questions straight from the
SERP extract, deduped — code only. Order = one LLM call to sequence the H2s; accepted ONLY as a
valid permutation of the indices, otherwise the sections keep their order.
"""
from .. import llm
from . import _common as _c


def faq_from_paa(paa):
    seen, faq = set(), []
    for q in (paa or []):
        q = str(q).strip()
        k = q.lower().rstrip("?")
        if q and k not in seen:
            seen.add(k)
            faq.append(q if q.endswith("?") else q + "?")
    return faq


def valid_permutation(order, n):
    try:
        order = [int(i) for i in (order or [])]
    except (TypeError, ValueError):
        return None
    return order if sorted(order) == list(range(n)) else None


def order_sections(sections):
    if len(sections) <= 1:
        return sections
    lines = "\n".join("%d: %s" % (i, s["h2"]) for i, s in enumerate(sections))
    try:
        got = llm.json_call(_c.prompt("order", sections=lines))
        order = got.get("order") if isinstance(got, dict) else got
    except Exception:  # noqa: BLE001
        order = []
    perm = valid_permutation(order, len(sections))
    return [sections[i] for i in perm] if perm else sections


def run(sections, paa):
    return order_sections(sections), faq_from_paa(paa)
