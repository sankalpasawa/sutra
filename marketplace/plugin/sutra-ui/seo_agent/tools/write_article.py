"""write_article.py — write the draft, one section per model call.

One call for a whole 1500-word article gets truncated, drifts off the blueprint, and loses
the voice by the third heading. One call per section does not. The cost is continuity, so
every call is handed the headings written so far and the tail of the draft, and told to
carry on rather than repeat.

A failed section does not kill the run. It is recorded in the draft as a gap and named in
the result, because a draft with one hole in it is worth more than nothing.
"""
import re

from .. import store
from .. import llm
from . import _shared as sh

TAIL_CHARS = 1800        # how much of the draft so far each section sees
SYSTEM = ("You are a working writer. Reply with the prose that was asked for and nothing "
          "else: no preamble, no sign-off, no notes about what you did.")

# Words the prompts ban. Checked after the fact so we can report what slipped through
# instead of quietly rewriting the model's sentences. Matched on the stem, because the
# word that actually gets past a prompt is usually the inflected one: "leverages", not
# "leverage". "navigate" is banned in the prompt but not checked here, since the literal
# sense is fine and this check cannot tell the two apart.
BANNED = ("delve", "leverage", "robust", "seamless", "landscape", "realm", "testament",
          "underscore", "tapestry", "crucial", "vital", "moreover", "furthermore")
_STEMS = {"delve": "delv", "leverage": "leverag", "underscore": "underscor",
          "tapestry": "tapestr"}
_BANNED_RE = re.compile(r"\b(" + "|".join(_STEMS.get(w, w) for w in BANNED) + r")\w*",
                        re.IGNORECASE)


def _strip_heading(body, heading):
    """Models sometimes write the heading anyway. One copy is enough, and the assembler
    already adds it."""
    want = (heading or "").strip().lower().rstrip(":")
    lines = (body or "").strip().split("\n")
    while lines and (not lines[0].strip()
                     or lines[0].lstrip("#*_ ").strip().rstrip(":").lower() == want):
        lines.pop(0)
    return "\n".join(lines).strip()


def _fix_dashes(text):
    """The one rule worth enforcing after the fact. Everything else we only report,
    because rewriting a model's sentence by regex does more harm than the word did."""
    # A dash opening a line is a bullet, not punctuation. Drop it rather than comma it.
    text = re.sub(r"(?m)^\s*[\u2014\u2013]\s*", "", text or "")
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)
    return re.sub(r",\s*,", ",", text)


def _banned_found(text):
    return sorted({m.group(0).lower() for m in _BANNED_RE.finditer(text or "")})


def run(ctx):
    chat_id, run_id = ctx["chat_id"], ctx["run_id"]
    say = sh.reporter(ctx, "write_article")

    blueprint = store.load_artifact(chat_id, run_id, "blueprint.json")
    if not blueprint:
        return {"summary": "No blueprint to write from.",
                "error": "blueprint.json is missing for this run. Run build_blueprint first."}
    sections = blueprint.get("sections") or []
    if not sections:
        return {"summary": "The blueprint has no sections.",
                "error": "blueprint.json has an empty sections list. Rebuild it."}

    research = store.load_artifact(chat_id, run_id, "research.json") or {}
    voice = sh.voice_block()
    title = blueprint.get("title") or research.get("topic") or "Untitled"
    primary = blueprint.get("primary_keyword") or ""
    tpl = sh.load_prompt("write_section")

    written, headings, failed = [], [], []
    for i, section in enumerate(sections, start=1):
        heading = section.get("heading", "Section %d" % i)
        say("Writing: %s" % heading,
            "Section %d of %d, about %s words" % (i, len(sections), section.get("words", "?")))

        so_far = "\n\n".join(w["body"] for w in written)
        prompt = sh.fill(
            tpl,
            company=sh.company_name(), title=title,
            angle=research.get("recommended_angle") or blueprint.get("meta_description", ""),
            primary=primary or "(none)",
            secondary=", ".join(blueprint.get("secondary_keywords") or []) or "(none)",
            heading=heading, covers=section.get("covers", ""),
            words=section.get("words", 250), index=i, total=len(sections),
            links=sh.bullets(["%s -> %s" % (l.get("anchor", ""), l.get("url", ""))
                              for l in (section.get("internal_links") or [])],
                             empty="(none for this section)"),
            paa=sh.bullets(research.get("people_also_ask"), empty="(none)"),
            covered=sh.bullets(research.get("what_they_all_cover"), empty="(not analysed)"),
            gap=research.get("the_gap") or "(no gap analysis)",
            voice=voice,
            headings_so_far=", ".join(headings) or "(this is the first section)",
            tail=so_far[-TAIL_CHARS:] if so_far else "(nothing written yet)",
        )
        try:
            body = llm.text(prompt, SYSTEM)
        except Exception as e:
            failed.append(heading)
            say("Section failed: %s" % heading, str(e)[:160])
            continue

        body = _fix_dashes(_strip_heading(body, heading))
        if not body:
            failed.append(heading)
            say("Section came back empty: %s" % heading, "Left as a gap in the draft")
            continue

        written.append({"heading": heading, "body": body})
        headings.append(heading)

    if not written:
        return {"summary": "Nothing got written.",
                "error": "Every section failed at the model call. Check the model key and retry."}

    parts = ["# " + title, ""]
    for w in written:
        parts += ["## " + w["heading"], "", w["body"], ""]
    for heading in failed:
        parts += ["## " + heading, "", "_This section did not get written. Ask me to retry it._", ""]
    draft = "\n".join(parts).strip() + "\n"

    store.save_artifact(chat_id, run_id, "draft.md", draft)

    words = len(draft.split())
    slipped = _banned_found(draft)
    if slipped:
        say("Words to check before publishing", ", ".join(slipped))
    say("Draft saved", "%s words" % format(words, ","))

    summary = "%s words across %s" % (format(words, ","),
                                      sh.plural(len(written), "section"))
    if failed:
        summary += ". %s failed: %s" % (sh.plural(len(failed), "section"), ", ".join(failed))
    out = {"summary": summary, "artifact": "draft.md"}
    if slipped:
        out["note"] = "Banned words slipped through: " + ", ".join(slipped)
    return out
