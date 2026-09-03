"""seeds.py — Step 0 (thinking): head seeds + sibling seeds + the hygiene note. No free brainstorm.

Ported from 10-dataforseo/scripts/s0_seeds.py. The original also vetted competitor proof URLs from
the asset engine's clubbed sheet for its ranked net; there is no clubbed sheet here (layer 02 is not
ported), so that part is left out and the seeds come from the title, the angle and the world alone.

Reads: topic, angle, world, company. Writes (via the tool): _work/seeds.json
{head_seeds, sibling_seeds, hygiene, seeds}.
"""
from .. import llm
from . import _common as _c


def run(topic, angle, world, company=None):
    tok = _c.company_tokens(company)
    p = _c.prompt("seeds", brand=tok["brand"], niche_definition=tok["niche_definition"],
                  asset_topic=topic, distinct_angle=angle or "(none given yet)", **_c.world_tokens(world))
    got = llm.json_call(p) or {}
    if not isinstance(got, dict):
        got = {}
    head = _c.strings(got.get("head_seeds"))
    sib = _c.strings(got.get("sibling_seeds"))
    hygiene = str(got.get("hygiene") or "").strip()
    if not head:
        # The title phrase is the anchor the prompt derives from, so it is the one seed that is
        # never a brainstorm. Without it there is nothing to expand.
        head = [topic.strip()]
    seen, seeds = set(), []
    for s in head + sib:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            seeds.append(s)
    return {"head_seeds": head, "sibling_seeds": sib, "hygiene": hygiene, "seeds": seeds}
