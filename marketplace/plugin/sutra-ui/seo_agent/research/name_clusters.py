"""name_clusters.py — Blueprint step 4: name + split each cluster into an H2 (+ H3s).

Ported from 13-research-structure/scripts/name_clusters.py. One parallel call per cluster with the
article context (title, angle, about/not-about), because a naming call that sees only the cards
defaults to the one shape that fits anything, a question, and that shape reaches the reader. Code
guarantees every member card lands under the H2 or exactly one H3 (local MECE).

Reads: clusters + cards. Returns [{h2, job, card_ids, h3:[{h3, card_ids}]}].
"""
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as _c


def _name_one(cluster, gloss_by_id, ctx):
    members = cluster["card_ids"]
    lines = "\n".join("%s: %s" % (i, gloss_by_id.get(i, "")) for i in members)
    try:
        r = llm.json_call(_c.prompt("name-cluster", cards=lines, **ctx))
        r = r if isinstance(r, dict) else {}
    except Exception:  # noqa: BLE001 — the cluster label is the working H2
        r = {"h2": cluster["label"], "h3": [], "card_ids": members}
    mset = set(members)
    placed, h3 = set(), []
    for sub in r.get("h3", []) or []:
        if not isinstance(sub, dict):
            continue
        ids = [i for i in (_c.as_int(x) for x in (sub.get("card_ids") or [])) if i in mset and i not in placed]
        placed.update(ids)
        if ids:
            h3.append({"h3": str(sub.get("h3") or "").strip() or "Untitled", "card_ids": ids})
    direct = [i for i in (_c.as_int(x) for x in (r.get("card_ids") or [])) if i in mset and i not in placed]
    placed.update(direct)
    direct += [i for i in members if i not in placed]        # nothing lost
    return {"h2": str(r.get("h2") or "").strip() or cluster["label"],
            "job": str(r.get("job") or "").strip() or cluster["label"],
            "card_ids": direct, "h3": h3}


def run(clusters, cards, topic, angle, spine_ctx):
    spine_ctx = spine_ctx or {}
    ctx = {"asset": topic or _c.NOT_AVAILABLE, "angle": (angle or topic) or _c.NOT_AVAILABLE,
           "about": _c.na(spine_ctx.get("about")), "not_about": _c.na(spine_ctx.get("not_about"))}
    gloss_by_id = {c["id"]: c["gloss"] for c in cards}
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        return list(ex.map(lambda cl: _name_one(cl, gloss_by_id, ctx), clusters))
