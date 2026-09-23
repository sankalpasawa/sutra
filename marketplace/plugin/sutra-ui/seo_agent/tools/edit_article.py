"""edit_article.py — change an article that already exists, without researching it again.

WHY THIS TOOL EXISTS (Aparna, 2026-09-23). She asked the chat to "simplify the content" and to
"make it more skimmable", and watched it start the research phase and take about an hour. Her words:
"If the request is only to refine/edit the existing content, it should ideally skip the research
phase and directly move to rewriting."

She was right, and the cause was not a bad decision by the model. The chat had NO tool that could
edit anything. Its only writing tools were run_research, build_blueprint and write_article, so the
single way it could act on "make this skimmable" was to write a new article from scratch: twelve
research questions, thirty-six searches, and an hour, to change the shape of prose that already
existed.

The Library screen has had the one-call path all along (`POST /library/{id}/ai-article` ->
library_edit.propose_article). This is that same call, given to the chat, so the same request takes
one model call from either place.

TWO THINGS IT DOES NOT DO, both deliberate:

  * IT WRITES NOTHING. Same contract as the Library button: it returns the rewrite as a PROPOSAL,
    and the person presses Use this. An agent that silently rewrote a published article on a
    one-line instruction would be a worse tool than the hour-long one it replaces.
  * IT DOES NOT RESEARCH. No new facts, no new sources, no new sections. Every guard
    propose_article already enforces still applies: headings may not drift, source tags may not be
    lost, and a figure that is in neither the article nor its evidence is refused outright.

Reads: the article's saved draft. Writes: nothing.
"""
from .. import library_edit, store
from . import _shared as sh


def _pick(item_id=None):
    """The article this instruction is about: the one named, else the one most recently saved.

    Falling back to the newest is what makes "simplify the content" work as a sentence -- she is
    looking at an article when she types it, and being asked "which one?" after an hour of waiting
    is exactly the friction this tool removes. A named id always wins.
    """
    if item_id:
        return str(item_id).strip(), store.library_get(str(item_id).strip())
    rows = [r for r in (store.library_list() or []) if int(r.get("words") or 0) > 0]
    if not rows:
        return "", None
    rows.sort(key=lambda r: str(r.get("finished_at") or r.get("created_at") or ""), reverse=True)
    top = rows[0]
    return str(top.get("id") or ""), store.library_get(str(top.get("id") or ""))


def run(ctx, instruction="", item_id=None, **_ignored):
    say = sh.reporter(ctx, "edit_article")
    instruction = str(instruction or "").strip()
    if not instruction:
        return {"summary": "Nothing to change.",
                "error": "Say what should change about the article, and I will rewrite it."}

    wanted, meta = _pick(item_id)
    if not meta:
        return {"summary": "No article to edit.",
                "error": ("There is no finished article in the Library yet. Write one first, or "
                          "name the article you mean.")}
    title = (meta.get("title") or "this article").strip()
    say("Rewriting %s" % title, "no new research: the article is rewritten as it stands")

    try:
        out = library_edit.propose_article(wanted, None, instruction)
    except Exception as e:      # noqa: BLE001 -- a drifted heading, a lost tag and an invented
        return {"summary": "The rewrite was refused.",   # figure all read the same to a person
                "error": str(e)[:400]}

    was, now = out.get("was") or "", out.get("proposed") or ""
    say("Rewrite ready", "%s words before, %s after" % (len(was.split()), len(now.split())))
    return {
        "summary": ("Rewrote %s to your instruction. Nothing is saved yet: open it in the Library "
                    "and press Use this to keep it." % title),
        "item_id": wanted, "title": title,
        "words_before": len(was.split()), "words_after": len(now.split()),
        "instruction": instruction,
        "hint": ("Tell them the rewrite is waiting in the Library and needs Use this. Do NOT run "
                 "research or write_article for an edit to an article that already exists."),
    }
