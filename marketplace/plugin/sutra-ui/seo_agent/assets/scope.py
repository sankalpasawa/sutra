"""assets/scope.py — builder 0: the brand scope, the one anchor all three methods judge against.

Port of `02-asset-engine/1-competitor-study` step G0, which the original calls a gate: "Distil the
brand scope (do this once, before G1)". Methods 2 and 3 load the same file (`model-other-niches`
A0, `study-trends` stage 3), which is the whole reason their verdicts can be compared later.

There is nothing to research here. Every input already exists in the brand pack, written by layer
01 from the company's own pages. This builder's only job is to compress it into the short, blunt
statement a judge can hold in its head while scoring a hundred ideas.

Reads:  brand/company.json · brand/features.md · brand/brand-voice.md · brand/persona.md
Writes: assets/scope.md
"""
from .. import llm
from ..brand import _common as bcm
from ..tools import _shared as sh
from . import _common as cm

OUTPUT = "scope.md"
FEATURES_CHARS = 9000       # of features.md; the schema's first sections carry the product truth
VOICE_CHARS = 4000          # of brand-voice.md; the pillars, not the examples


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept the brand scope", "already written; ask for a redo to rebuild it")
        return {"files": [OUTPUT], "needs_review": []}

    features = bcm.read("features.md")[:FEATURES_CHARS]
    voice = bcm.read("brand-voice.md")[:VOICE_CHARS]
    persona = bcm.read("persona.md")
    if not features.strip():
        raise RuntimeError("There is no features.md yet. The brand pack has to be built before the "
                           "asset engine can judge what this company can own.")

    doc = cm.strip_fence_safe(llm.text(sh.fill(
        cm.prompt("brand-scope"),
        brand=co["brand"], niche=co.get("niche_definition") or "",
        oneliner=co.get("brand_oneliner") or "",
        features=features, voice=voice, persona=persona or "(no personas on file)")))
    cm.save(OUTPUT, doc)

    notes = []
    # The scope is useless to a judge unless it says what is OUT. A scope that only says what the
    # company does reads as "anything vaguely related", which is how a judge ends up approving
    # everything. The original's G0 is a gate for exactly this reason.
    if "not" not in doc.lower():
        notes.append("scope.md: it never says what is OUT of scope, so the two tests will judge "
                     "generously. Worth a read.")
    say("Wrote the brand scope", "%d words; every idea from all three methods is judged against it"
        % bcm.words(doc))
    return {"files": [OUTPUT], "needs_review": notes}
