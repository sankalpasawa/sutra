"""persona.py — pick the ONE reader persona for this article, from the brand's persona library.

Ported from 13-research-structure/scripts/pick_persona.py. Decided ONCE here; the card filter, the
blueprint and the writer all REUSE it (never re-pick), so research and writing target the same
reader. If knowledge/brand/persona.md is missing, a generic "practitioner, not academic" reader is
used so nothing breaks.

Reads: topic, angle, brand/persona.md. Writes (via the tool): _work/persona.json {name, lens, why}.
"""
from .. import llm
from ..tools import _shared as sh
from . import _common as _c

_FALLBACK = {"name": "", "lens": "a practitioner making a real decision about what the brand offers "
                                 "(choose / evaluate / use it), not an academic", "why": ""}


def run(topic, angle, company=None):
    doc = sh.brand_file("persona.md")
    if not doc:
        return {**_FALLBACK, "why": "no persona library on file yet (knowledge/brand/persona.md); using a generic reader"}
    tok = _c.company_tokens(company)
    p = _c.prompt("pick-persona", brand=tok["brand"], asset_title=topic, angle=angle or "", persona_doc=doc)
    try:
        got = llm.json_call(p) or {}
        got = got if isinstance(got, dict) else {}
        persona = {"name": str(got.get("name") or "").strip(),
                   "lens": str(got.get("lens") or "").strip() or _FALLBACK["lens"],
                   "why": str(got.get("why") or "").strip()}
    except Exception as e:  # noqa: BLE001 — a failed pick falls back to the generic reader, and says so
        persona = {**_FALLBACK, "why": "the persona pick failed (%s); using a generic reader" % str(e)[:80]}
    return persona
