"""spine.py — Step 2a: the WORKING SPINE, what the article argues, built from the world + the winners.

Ported from 14-research-conductor/scripts/spine.py::run(). The world was decided earlier (world.py);
this is the remaining piece. Same field-level retry as the world step; an empty spine twice is an
error, never a half spine.

Reads: topic, angle, world, the winners lists, company. Writes (via the tool): _work/spine.json.
"""
from .. import llm
from . import _common as _c


def run(topic, angle, world, lists, company):
    tok = _c.company_tokens(company)
    p = _c.prompt("build-spine", title=topic, angle=angle or "(no distinct angle recorded)",
                  brand=tok["brand"], about_brand=tok["about_brand"],
                  gaps=_c.render(lists.get("gaps_to_own")), common_h2s=_c.render(lists.get("common_h2s")),
                  drift=_c.render(lists.get("drift")), **_c.world_tokens(world))
    sp = ""
    for _ in range(2):
        got = llm.json_call(p) or {}
        sp = str(got.get("spine") or "").strip() if isinstance(got, dict) else ""
        if sp:
            break
    if not sp:
        raise RuntimeError("The spine came back empty twice; not writing a half spine.")
    return sp
