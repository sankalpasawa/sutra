"""score_cards.py — Blueprint step 1b: the spine-relevance filter. Drop the off-spine tail BEFORE clustering.

Ported from 13-research-structure/scripts/score_cards.py. THE ONE TEST: does this card serve the
spine? The card is the atomic unit, so this deletes at the finest granularity. PROTECT (never
dropped, whatever the score): the judge marked `protected` (a number / % / threshold / statistic, a
sample item, a named option tied to an outcome), or the card carries a gap/competitor tag. An
unscored card is KEPT and counted. A scorer batch that fails ABORTS the step (fail closed): a
crashed scorer must not silently default its cards to keep, or a broken run produces a bloated
blueprint indistinguishable from a good one. The FLAG fires at SCORE_FLAG_PCT either way.

Reads: cards + the article context + the persona. Returns (kept_cards, report).
"""
import re
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as _c

PROTECTED_TAGS = ("gap", "competitor")     # handled in code — our differentiators + competitive intel


def _card_line(c):
    txt = re.sub(r"\s+", " ", (c.get("verbatim") or c.get("gloss") or "")).strip()[:260]
    src = (c.get("source_urls") or [None])[0] or "-"
    return "%s | %s | %s | %s" % (c["id"], c.get("tag"), src, txt)


def _score_batch(batch, ctx):
    """RAISES on failure, so run() aborts the whole step rather than defaulting the batch to keep."""
    p = _c.prompt("score-cards", cards="\n".join(_card_line(c) for c in batch), **ctx)
    out = llm.json_call(p)
    rows = out.get("scores", []) if isinstance(out, dict) else out
    return {int(r["id"]): r for r in (rows or []) if isinstance(r, dict) and _c.as_int(r.get("id")) is not None}


def run(cards, topic, angle, persona, spine_ctx, brand_oneliner):
    spine_ctx = spine_ctx or {}
    ctx = {"asset": topic, "angle": angle or topic, "spine": _c.na(spine_ctx.get("spine")),
           "about": _c.na(spine_ctx.get("about")), "not_about": _c.na(spine_ctx.get("not_about")),
           "brand": brand_oneliner, "personas": _c.personas_block(), "persona": _c.persona_str(persona)}
    batches = [cards[i:i + _c.SCORE_BATCH] for i in range(0, len(cards), _c.SCORE_BATCH)]
    scores = {}
    # ex.map re-raises the first batch exception when iterated, so a failed batch aborts the step.
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        for res in ex.map(lambda b: _score_batch(b, ctx), batches):
            scores.update(res)

    kept, dropped, unscored = [], [], 0
    for c in cards:
        s = scores.get(c["id"], {})
        rel = _c.as_int(s.get("relevance"))
        if rel is None:
            unscored += 1                                    # judge omitted it / non-integer -> safe keep, counted
        protected = bool(s.get("protected")) or (c.get("tag") in PROTECTED_TAGS)
        c["relevance"] = rel
        c["protected"] = protected
        if not protected and rel is not None and rel <= _c.SCORE_KEEP_THRESH:
            dropped.append({"id": c["id"], "tag": c.get("tag"), "gloss": c.get("gloss"),
                            "relevance": rel, "reason": str(s.get("reason") or "")})
        else:
            kept.append(c)

    total = len(cards)
    pct = round(100 * len(dropped) / total, 2) if total else 0.0
    unscored_pct = round(100 * unscored / total, 2) if total else 0.0
    report = {
        "total_cards": total, "kept_count": len(kept), "dropped_count": len(dropped),
        "dropped_pct_of_cards": pct, "keep_threshold": _c.SCORE_KEEP_THRESH,
        "unscored_count": unscored, "unscored_pct_of_cards": unscored_pct,
        "flag_threshold_pct": _c.SCORE_FLAG_PCT,
        # FLAG fires on EITHER side: over-dropping OR too many unscored — both mean the filter cannot be trusted
        "FLAG": pct > _c.SCORE_FLAG_PCT or unscored_pct > _c.SCORE_FLAG_PCT,
        "dropped": sorted(dropped, key=lambda d: (d["relevance"], d["id"])),
    }
    return kept, report
