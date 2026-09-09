"""find_prompt.py — "this isn't coming out right": which prompt owns the complaint.

WHAT THIS IS FOR. The craft of this agent is in its prompts, and the Prompts tab lets the owner
edit any of them. The gap was finding the right one. Told "the intros are too long" or "it keeps
writing in threes", a person has to know that intros live in `write/wrapper` and rhythm lives in
`write/sentence-pass` before the tab is any use at all. Fourteen prompts is not many, but knowing
which of them owns a sentence you disliked in a finished article is a different question.

So this tool hands the model the map: every editable prompt, the station it runs in, what it is
responsible for, and, when a name is given, its full current text.

WHAT IT DELIBERATELY DOES NOT DO. It does not call a model, and it does not write anything. The
division is the owner's and it is the whole design:

    the agent PROPOSES, the person EDITS.

An agent that silently rewrites its own instructions is a thing nobody can debug: the article
changes, the prompt changed, and there is no record of who decided. So the agent reads the prompt,
names the step, quotes the wording that is causing the problem and proposes a replacement IN CHAT.
The person then opens the Prompts tab and makes the edit, or does not. Every change to the craft
stays a human decision with a human behind it.

The save-side guards live in prompts/store.py and are unchanged: an edit that drops or invents a
{{TOKEN}} is refused, and Reset deletes the override rather than restoring a backup.

Reads:  prompts/store.py (the catalogue and the live text). Nothing else.
Writes: nothing.
"""
from ..prompts import store as ps

# Which station each prompt runs in. Grounded in ps.FLOW, not invented: the eight rulebooks are a
# station of their own that the architect obeys, and all six writing prompts sit in the writer.
# Kept as a mapping from the group key rather than per-prompt, so adding a prompt to a group in
# store.py does not need a second edit here.
STATION = {
    "formats": ("The format rules", "Read before the architect designs anything. The rulebook for "
                                    "one shape decides what a section of that shape must contain."),
    "writing": ("Writer", "The stations that put words on the page and then edit them."),
}

# Only ONE rulebook is in play for any given article: the router picks the archetype and that
# archetype's rulebook is the one that ran. Saying so stops the model proposing an edit to
# "glossary" because the complaint was about an article that was routed to "listicle".
ROUTED_NOTE = ("Only one of the eight format rules runs per article: the one the router chose for "
               "that article's shape. The Library's Format column says which. Do not propose an "
               "edit to a rulebook that did not run.")


def _rows():
    """Every editable prompt, with its station, in the order the Prompts tab shows them."""
    out = []
    for g in ps.GROUPS:
        label, why = STATION.get(g["key"], (g["title"], g["note"]))
        for name, title, note in g["prompts"]:
            out.append({"name": name, "title": title, "owns": note, "station": label,
                        "station_is_for": why, "edited": ps.is_edited(name)})
    return out


def run(ctx, name=""):
    """No name: the whole map, so the model can work out which step owns the complaint.
    A name: that prompt's full current text, so the model can quote it and propose a change."""
    name = str(name or "").strip()

    if not name:
        rows = _rows()
        return {
            "prompts": rows,
            "count": len(rows),
            "routed_note": ROUTED_NOTE,
            "next": ("Work out which ONE of these owns what the user disliked, then call "
                     "find_prompt again with its name to read the wording."),
        }

    if not ps.known(name):
        # A wrong name is the model guessing at a path. Give it the real list back rather than an
        # error it cannot act on.
        return {"error": "There is no editable prompt called %r." % name,
                "prompts": [{"name": r["name"], "title": r["title"]} for r in _rows()]}

    one = ps.one(name)
    return {
        "name": one["name"],
        "title": one["title"],
        "owns": one["note"],
        "text": one["text"],
        "edited": one["edited"],
        "lines": one["lines"],
        "words": one["words"],
        "tokens": one["tokens"],
        "how_to_change_it": (
            "You do not edit this. Quote the exact lines that are causing the problem, say in one "
            "sentence why they produce what the user saw, and propose the replacement wording. "
            "Then tell them to open the Prompts tab and find \"%s\", where they can make the edit "
            "and save it. The very next article uses their version." % one["title"]),
        "token_rule": (
            "A {{TOKEN}} is a blank the code fills before the model sees the prompt. This prompt "
            "has %d of them: %s. A saved edit that loses one, or adds one, is refused. Never "
            "propose wording that drops a token."
            % (len(one["tokens"]), ", ".join(one["tokens"]) or "none")),
    }
