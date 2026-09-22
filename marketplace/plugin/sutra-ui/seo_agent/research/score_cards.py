"""score_cards.py — Blueprint step 1b: the spine-relevance filter. Drop the off-spine tail BEFORE clustering.

Ported from 13-research-structure/scripts/score_cards.py. THE ONE TEST: does this card serve the
spine? The card is the atomic unit, so this deletes at the finest granularity. PROTECT (never
dropped, whatever the score): the judge marked `protected` (a number / % / threshold / statistic, a
sample item, a named option tied to an outcome), or the card carries a gap/competitor tag. An
unscored card is KEPT and counted. A scorer batch that fails ABORTS the step (fail closed): a
crashed scorer must not silently default its cards to keep, or a broken run produces a bloated
blueprint indistinguishable from a good one. The FLAG fires at SCORE_FLAG_PCT either way.

AND THE EXPECTED TOPICS ARE PROTECTED TOO (owner, 2026-09-22: "check if this cutting and shit was
fine actually?"). It was not. On the first real run after the demand changes shipped, this filter
dropped 242 of 534 cards and every number looked healthy -- nothing above the threshold cut, all
201 hard-data cards kept. Reading the DROPPED pile found 23 cards answering topics every ranking
page covers, including the literal definition card on an article about that very thing.

The cause was this step's own context: title, angle, spine, world and persona, and nothing about
what readers already expect. So a card that served only the expected ground scored 0 or 1 against
OUR argument and died. That is the same failure the research change had just fixed one step
earlier: the researchers were sent to collect exactly this evidence, and then it was thrown away
before the architect ever saw it, which lands the article back at "it never says what the thing
is".

So the table stakes come in, and a card that carries one is PROTECTED rather than merely scored
higher. Protection is the mechanism that already demonstrably works (201 of 201 survived that run)
and it is audited in the report; a score nudge would be invisible and untestable.

Reads: cards + the article context + the persona + the table stakes. Returns (kept_cards, report).
"""
import re

from .. import llm
from . import _common as _c

PROTECTED_TAGS = ("gap", "competitor")     # handled in code — our differentiators + competitive intel


def _norm(t):
    return " ".join(re.findall(r"[a-z0-9]+", str(t or "").lower()))


def _stake_claim(claimed, stakes):
    """The expected topic this card really answers, or "" — THE RECEIPT RULE, as code.

    The prompt says to copy a topic from the list. Trusting that is how a rescue becomes a
    loophole: a model that names a topic which is not on the list would keep any card it liked,
    and nothing downstream could tell. Same rule the plan tagger already enforces on its own tags
    -- a claim is kept only when it cites something that really exists.

    Forgiving about wording, strict about existence: a heading is long and a model will reasonably
    shorten it, so either containing the other counts, but an invention matches nothing and is
    dropped in silence.
    """
    c = _norm(claimed)
    if not c:
        return ""
    for st in stakes or []:
        n = _norm(st)
        if not n:
            continue
        if c == n or (len(c) > 8 and c in n) or (len(n) > 8 and n in c):
            return st
    return ""


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


def run(cards, topic, angle, persona, spine_ctx, brand_oneliner, table_stakes=None):
    spine_ctx = spine_ctx or {}
    stakes = [str(x).strip() for x in (table_stakes or spine_ctx.get("table_stakes") or []) if str(x).strip()]
    ctx = {"asset": topic, "angle": angle or topic, "spine": _c.na(spine_ctx.get("spine")),
           "about": _c.na(spine_ctx.get("about")), "not_about": _c.na(spine_ctx.get("not_about")),
           "brand": brand_oneliner, "personas": _c.personas_block(), "persona": _c.persona_str(persona),
           "table_stakes": "\n".join("  - " + x for x in stakes) or "  (none measured for this article)"}
    batches = [cards[i:i + _c.SCORE_BATCH] for i in range(0, len(cards), _c.SCORE_BATCH)]
    scores = {}
    # ex.map re-raises the first batch exception when iterated, so a failed batch aborts the step.
    with llm.pool() as ex:
        for res in ex.map(lambda b: _score_batch(b, ctx), batches):
            scores.update(res)

    kept, dropped, unscored = [], [], 0
    for c in cards:
        s = scores.get(c["id"], {})
        rel = _c.as_int(s.get("relevance"))
        if rel is None:
            unscored += 1                                    # judge omitted it / non-integer -> safe keep, counted
        # THREE WAYS TO BE PROTECTED, and the third is new. The judge's own `protected` covers hard
        # data; PROTECTED_TAGS covers our differentiators; `covers_stake` covers a card that answers
        # something every ranking page does. A reader who arrives expecting the basics and cannot
        # find them leaves before reaching anything we do better, so that card is worth as much as
        # a statistic even when it says nothing new.
        stake_hit = _stake_claim(s.get("covers_stake"), stakes)
        protected = bool(s.get("protected")) or (c.get("tag") in PROTECTED_TAGS) or bool(stake_hit)
        c["covers_stake"] = stake_hit or ""
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
        # What the expected ground kept alive that the spine alone would have cut. Reported, not
        # just done: this is the number that would have shown the defect on the run that found it.
        "kept_for_expected_topic": sum(1 for c in kept if c.get("covers_stake")),
        "expected_topics_seen": stakes,
        # FLAG fires on EITHER side: over-dropping OR too many unscored — both mean the filter cannot be trusted
        "FLAG": pct > _c.SCORE_FLAG_PCT or unscored_pct > _c.SCORE_FLAG_PCT,
        "dropped": sorted(dropped, key=lambda d: (d["relevance"], d["id"])),
    }
    return kept, report
