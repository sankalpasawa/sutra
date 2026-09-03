"""brand/persona.py — builder 6: the 3-4 readers the content is written TO.

Port of 5-persona/scripts/run_persona.py. One model call with the recipe's exact prompt (lifted
verbatim into prompts/brand/persona.md) and brand-voice.md pasted in. The one rule: a persona is
the READER, never the author byline, and it is never named in the article.

Reads:  brand/brand-voice.md (its Audience Understanding section is the raw material).
Writes: brand/_work/persona/personas.json · brand/persona.md
"""
from .. import llm
from . import _common as cm

OUTPUT = "persona.md"
WORK = "_work/persona/"
FIELDS = ("name", "who", "reads", "cares_about", "depth_and_angle", "not_this")
MIN_PERSONAS, MAX_PERSONAS = 3, 4


def render(co, out):
    personas = out.get("personas") or []
    lines = ["# %s Reader Personas" % co["brand"], "",
             "> A persona is the READER we write TO — never the author byline. Think about the persona;",
             "> NEVER name or address them explicitly in the article. (persona.workflow.md, the one rule)", "",
             "| Persona | Who | Reads | Cares about | Depth & angle | Not this |",
             "|---|---|---|---|---|---|"]
    for p in personas:
        if not isinstance(p, dict):
            continue
        cells = {k: str(p.get(k, "")).replace("|", "/").replace("\n", " ") for k in FIELDS}
        lines.append("| **{name}** | {who} | {reads} | {cares_about} | {depth_and_angle} | {not_this} |".format(**cells))
    htp = out.get("how_to_pick", "")
    if not isinstance(htp, str):                     # the model sometimes returns a structured object
        htp = "\n".join("- %s: %s" % (k, v) for k, v in htp.items()) if isinstance(htp, dict) else "\n".join(map(str, htp))
    lines += ["", "## How to pick the persona for an article", htp, ""]
    return "\n".join(lines)


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept persona.md", "already built; ask for a redo to rebuild it")
        return {"files": [OUTPUT], "needs_review": []}
    voice = cm.read("brand-voice.md")
    if not voice.strip():
        raise RuntimeError("There is no brand-voice.md yet; personas derive from its Audience section.")
    out = llm.json_call(cm.fill(cm.prompt("persona"), brand_voice=voice))
    out = dict(out) if isinstance(out, dict) else {}
    personas = [p for p in (out.get("personas") or []) if isinstance(p, dict)]
    out["personas"] = personas
    notes = []
    if not (MIN_PERSONAS <= len(personas) <= MAX_PERSONAS):
        notes.append("persona.md: %d personas returned (the recipe wants %d-%d); review at the gate" % (len(personas), MIN_PERSONAS, MAX_PERSONAS))
    cm.save(WORK + "personas.json", out)
    cm.save(OUTPUT, render(co, out))
    say("Proposed the reader personas", "%d personas -> brand/persona.md; you confirm or edit them" % len(personas))
    notes.append("persona.md: confirm or edit the %d proposed personas (the recipe's one human gate)" % len(personas))
    return {"files": [OUTPUT], "needs_review": notes}
