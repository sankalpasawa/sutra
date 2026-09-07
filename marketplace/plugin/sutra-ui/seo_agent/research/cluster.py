"""cluster.py — Blueprint steps 2-3: cluster the kept cards into MECE groups, verified in code.

Ported from 13-research-structure/scripts/cluster.py. Small sets (<= CLUSTER_SINGLE_MAX): one call
that sees id + gloss. Large sets: two-level — batch, cluster each batch in parallel, then merge the
batch labels into final themes with the SAME article context. Then code guarantees every card is
placed exactly once: _dedupe keeps each id in its first cluster only, unplaced cards get one leftover
pass, anything still unplaced lands in "Unsorted (review)", and an assert confirms MECE.

Reads: kept cards + the article context. Returns [{label, card_ids}].
"""
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as _c


def _cluster_call(cards, ctx):
    lines = "\n".join("%s: %s" % (c["id"], c["gloss"]) for c in cards)
    out = llm.json_call(_c.prompt("cluster", cards=lines, **ctx))
    return (out.get("clusters") if isinstance(out, dict) else out) or []


def _dedupe(clusters, valid_ids):
    """Keep each id in its first cluster only; drop unknown ids. Returns (clusters, placed)."""
    placed, out = set(), []
    for cl in clusters or []:
        if not isinstance(cl, dict):
            continue
        ids = []
        for i in cl.get("card_ids", []) or []:
            i = _c.as_int(i)
            if i is not None and i in valid_ids and i not in placed:
                placed.add(i)
                ids.append(i)
        if ids:
            out.append({"label": str(cl.get("label") or "").strip() or "Untitled", "card_ids": ids})
    return out, placed


def _two_level(cards, ctx):
    batches = [cards[i:i + _c.CLUSTER_BATCH] for i in range(0, len(cards), _c.CLUSTER_BATCH)]

    def _do(batch):
        cl, _ = _dedupe(_cluster_call(batch, ctx), {c["id"] for c in batch})
        return cl

    provisional = []
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        for cl in ex.map(_do, batches):
            provisional += cl
    # The merge step gets the SAME article context as the batch clusterer. Without it the merger saw
    # only label strings: it could spot duplicates but had no idea what was off-spine.
    lines = "\n".join("%d: %s" % (i, p["label"]) for i, p in enumerate(provisional))
    try:
        themes = llm.json_call(_c.prompt("cluster-merge", labels=lines, **ctx)).get("themes", [])
    except Exception:  # noqa: BLE001 — keep the provisional clusters
        themes = []
    final, used = [], set()
    for th in themes or []:
        if not isinstance(th, dict):
            continue
        ids = []
        for idx in th.get("member_indices", []) or []:
            idx = _c.as_int(idx)
            if idx is not None and 0 <= idx < len(provisional) and idx not in used:
                used.add(idx)
                ids += provisional[idx]["card_ids"]
        if ids:
            final.append({"label": str(th.get("label") or "").strip() or "Untitled", "card_ids": ids})
    for i, p in enumerate(provisional):            # any provisional cluster not merged stays on its own
        if i not in used:
            final.append(p)
    return final


def run(cards, topic, angle, persona, spine_ctx, brand_oneliner):
    spine_ctx = spine_ctx or {}
    ctx = {"asset": topic, "angle": angle or topic, "spine": _c.na(spine_ctx.get("spine")),
           "about": _c.na(spine_ctx.get("about")), "not_about": _c.na(spine_ctx.get("not_about")),
           "brand": brand_oneliner, "personas": _c.personas_block(), "persona": _c.persona_str(persona)}
    valid = {c["id"] for c in cards}
    if not cards:
        return []
    raw = _cluster_call(cards, ctx) if len(cards) <= _c.CLUSTER_SINGLE_MAX else _two_level(cards, ctx)
    clusters, placed = _dedupe(raw, valid)

    missing = [c for c in cards if c["id"] not in placed]
    if missing:
        try:
            extra = _cluster_call(missing, ctx)
        except Exception:  # noqa: BLE001 — the last-resort bucket below still holds MECE
            extra = []
        extra, placed2 = _dedupe(extra, {c["id"] for c in missing})
        clusters += extra
        still = [c["id"] for c in missing if c["id"] not in placed2]
        if still:                                   # last resort so MECE always holds
            clusters.append({"label": "Unsorted (review)", "card_ids": still})

    all_ids = [i for cl in clusters for i in cl["card_ids"]]
    assert len(all_ids) == len(set(all_ids)) == len(valid), \
        "MECE broken: %d placed, %d unique, %d cards" % (len(all_ids), len(set(all_ids)), len(valid))
    return clusters
