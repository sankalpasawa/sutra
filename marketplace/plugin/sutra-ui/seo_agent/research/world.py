"""world.py — Step 0b: the WORLD statement, before any research has been done.

Ported from 14-research-conductor/scripts/spine.py::world(). One AI call from the TITLE plus the
brand alone. THE ANGLE IS DELIBERATELY NOT PASSED: measured across three real runs it leaked, and a
world narrowed by an angle then drops keywords for being off-ANGLE while reporting them as off-WORLD.
The prompt's job is homonyms and neighbouring subjects, and the title plus the brand answer that.

Reads: the topic title, the company record. Writes (via the tool): _work/world.json {about, not_about}.
"""
from .. import llm
from . import _common as _c

FIELD_RETRIES = 2    # a reply that PARSES but has an empty field slips past the JSON retry; retry the field twice


def run(topic, company=None):
    tok = _c.company_tokens(company)
    p = _c.prompt("world", title=topic, brand=tok["brand"], about_brand=tok["about_brand"])
    w = {}
    for _ in range(1 + FIELD_RETRIES):
        got = llm.json_call(p) or {}
        if not isinstance(got, dict):
            got = {}
        w = {k: str(got.get(k) or "").strip() for k in ("about", "not_about")}
        if all(w.values()):
            break
    missing = [k for k, v in w.items() if not v]
    if missing:
        raise RuntimeError("The world statement came back with an empty %s %d times; not writing a half world."
                           % (" and ".join(missing), 1 + FIELD_RETRIES))
    return w
