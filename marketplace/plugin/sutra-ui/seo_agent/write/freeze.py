"""freeze.py — Planner step 4: the final gate. Checks the verified plan's SHAPE, then stamps it.

HARD flags (structural breakage, the plan is NOT frozen): no sections · a section with zero H3s · an H3
with zero cards · missing h1 / primary keyword / archetype · word band missing or zero.
SOFT notes (recorded, never blocking): a hard-hole (a gap / table-stake / PAA question no H3 serves) ·
fewer than 3 sections · source verification cut more than 15 cards · cards left unverified.
Shape checks only: every judgment already happened upstream. Freeze is a bouncer, not a judge.
"""


def run(plan, police=None):
    police = police or {}
    hard, soft = [], []
    secs = plan.get("sections") or []
    if not secs:
        hard.append("no sections")
    if not plan.get("h1"):
        hard.append("missing h1")
    if not plan.get("primary_keyword"):
        hard.append("missing primary keyword")
    if not plan.get("format_archetype"):
        hard.append("missing format archetype")
    wb = plan.get("word_band") or {}
    if not wb.get("min") or not wb.get("max"):
        hard.append("word band missing/zero")
    for s in secs:
        if not s.get("h3s"):
            hard.append("section with zero H3s: %s" % (s.get("h2") or "?")[:50])
        for h in s.get("h3s") or []:
            if not h.get("card_ids"):
                hard.append("H3 with zero cards: %s" % (h.get("h3") or "?")[:50])

    served = {t for s in secs for h in s.get("h3s", []) for t in h.get("tags", [])}
    for kind, key in [("gap", "gaps_to_own"), ("common-h2", "winners_common_h2s"), ("paa", "paa_pool")]:
        for item in plan.get(key) or []:
            if "%s: %s" % (kind, item) not in served:
                soft.append("HOLE (%s): %s" % (kind, item[:70]))
    if len(secs) < 3:
        soft.append("only %d sections" % len(secs))
    cuts = len(police.get("cut") or [])
    if cuts > 15:
        soft.append("source verification cut %d cards" % cuts)
    unchecked = len(police.get("needs_source") or []) + len(police.get("kept_unsourced") or [])
    if unchecked:
        soft.append("%d card(s) kept without a checked source; still in the plan" % unchecked)
    unloadable = len(police.get("unverifiable_kept") or [])
    if unloadable > 20:
        soft.append("%d cards kept with sources that would not load; verify before publishing" % unloadable)
    return {"hard": hard, "soft": soft, "plan": None if hard else plan}
