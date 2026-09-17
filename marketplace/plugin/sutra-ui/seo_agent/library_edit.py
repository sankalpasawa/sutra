"""library_edit.py — a finished article, edited by anyone on the team, one section at a time.

Reads:  library/<item_id>/{meta.json, draft.md, previous.md}, and the team's `library` row.
Writes: the same files through store.library_update / library_revert, then ONE row into the
        team's `library` table through sync.push (queued on disk first, so offline still saves).

WHAT A SECTION IS. The article split at its H1 and H2 lines: a heading and everything under it
down to the next H1 or H2. H3s stay inside their section. Text before the first heading is a
section of its own ("Opening"). Sections are numbered s0, s1, ... in order, and the same split
lives in static/js/17-agents.js (agSections) so the pencil on screen and the rewrite here address
the same text; tests/fixtures/agents-sections.json is the proof they agree.

TWO WAYS TO CHANGE A SECTION, ONE WAY TO SAVE. A person either types over the section, or asks the
model to rewrite it (propose). Neither writes anything. Both end in the same buffer on screen, and
`save` is the only writer: it takes the whole article, checks the version it was edited from is
still the current one, writes locally, then pushes the row to the team.

THE GUARDS ON AN AI REWRITE, in the order they run:
  1. the reply must still start with the section's heading, at the same level, and may not open
     a new H1/H2 (that would change the section count and move every id after it);
  2. no figure may appear that is in neither the article nor the evidence the research bought
     (the digit_guard rule, applied at the section) -- a refused proposal names the numbers;
  3. every OTHER section must be byte-identical after the splice (edit_block's assertion).

THE CONFLICT RULE. meta.version counts saves. A save carries the version it started from; if the
article is on a later version (a teammate saved meanwhile, and the poller mirrored it), or the
team's row is on a later version (the poller has not caught up yet), the save is refused with who
and when, and the caller chooses to reload or overwrite. Two saves inside the same second can
still race past this check: the row is an upsert, and the loser's edit is what the winner's
teammates then see. Small team, seconds apart: accepted, and said here so nobody assumes more.
"""
import collections
import importlib
import os
import re

from . import store, llm
from .checks import digit_guard
from .editing.make_diff import make_diff
from .tools import _shared as sh

# editing/__init__.py re-exports the edit_block FUNCTION under the submodule's name, so a plain
# `from .editing import edit_block` hands back the function. import_module reaches the module.
eb = importlib.import_module("seo_agent.editing.edit_block")

SYSTEM = ("You are a working editor. Reply with the rewritten section and nothing else: "
          "no preamble, no sign-off, no notes about what you changed.")

# A block that starts a section: one or two # marks, a space, then the heading.
SECTION_HEAD = re.compile(r"^(#{1,2})\s+(.*)$")
# Any H1/H2 line anywhere in a reply, used to refuse a rewrite that grows a new section.
ANY_HEAD = re.compile(r"^(#{1,2})\s+\S", re.M)
OPENING = "Opening"          # the label for text before the first heading


class InventedFigure(ValueError):
    """The rewrite carries a number the article never had and the evidence does not hold."""


class Conflict(Exception):
    """Somebody saved a newer version. Carries the newer row's who/when for the screen."""

    def __init__(self, current):
        super(Conflict, self).__init__("Updated by %s" % (current.get("edited_by") or "a teammate"))
        self.current = current


# ---- sections ---------------------------------------------------------------------------------------

def _head_of(block):
    first = (block or "").lstrip().split("\n", 1)[0].rstrip()
    m = SECTION_HEAD.match(first)
    return (len(m.group(1)), m.group(2).strip()) if m else (0, "")


def sections(md):
    """[{id, heading, level, text}] in document order. "".join of the pieces between and inside
    them is the document, exactly: the split is over edit_block.chunks, which loses nothing."""
    ch = eb.chunks(md or "")
    out, cur = [], None
    for i, (kind, text) in enumerate(ch):
        if kind != "block":
            continue
        level, heading = _head_of(text)
        if cur is None or level:
            cur = {"id": "s%d" % len(out), "heading": heading or OPENING, "level": level,
                   "_first": i, "_last": i}
            out.append(cur)
        else:
            cur["_last"] = i
    for s in out:
        s["text"] = "".join(t for _, t in ch[s["_first"]:s["_last"] + 1])
    return out


def section_map(md):
    return dict((s["id"], s["text"]) for s in sections(md))


def get_section(md, section_id):
    for s in sections(md):
        if s["id"] == section_id:
            return s
    raise ValueError("No section %r in this article. It has %d: %s." % (
        section_id, len(sections(md)), ", ".join(s["id"] for s in sections(md)) or "none"))


def splice(md, section_id, new_text):
    """Put new_text in place of one section and prove every other section held still."""
    target = get_section(md, section_id)
    ch = eb.chunks(md or "")
    pieces = []
    for i, (_kind, text) in enumerate(ch):
        if i == target["_first"]:
            pieces.append(new_text)
        elif target["_first"] < i <= target["_last"]:
            continue
        else:
            pieces.append(text)
    out = "".join(pieces)
    eb.assert_only_target_changed(section_map(md), section_map(out), section_id)
    return out


# ---- the AI proposal ----------------------------------------------------------------------------------

def clean_section(raw, original):
    """The model's reply made safe to splice: fences and "Here is" openers stripped, blank lines
    inside kept (a section is several paragraphs), the original's trailing newlines restored so
    the gap after the section stays exactly as it was."""
    text = (raw or "").strip()
    if text.startswith("```") or text.startswith("~~~"):
        parts = text.split("\n")[1:]
        while parts and parts[-1].strip().startswith(("```", "~~~")):
            parts.pop()
        text = "\n".join(parts).strip()
    text = re.sub(r"(?is)^(?:sure[,!.]?\s*)?here(?:'s| is| are)[^\n:]{0,80}:\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("The model returned nothing for this section.")
    trailing = original[len(original.rstrip("\n")):]
    return text + trailing


def check_heading(new_text, original):
    """Rule 1: same heading level at the top, and no second H1/H2 anywhere in the reply."""
    level, _ = _head_of(original)
    heads = ANY_HEAD.findall(new_text)
    if level:
        new_level, _ = _head_of(new_text)
        if new_level != level:
            raise ValueError("The rewrite lost the section's heading. It must start with the "
                             "same %s line." % ("#" * level))
        if len(heads) > 1:
            raise ValueError("The rewrite added a new heading, which would make a new section. "
                             "Sub-headings need three # marks.")
    elif heads:
        raise ValueError("The rewrite added a heading to the opening, which would make a new "
                         "section.")
    return True


def _allowed_figures(draft, meta):
    """Every figure the article may carry: the ones it already has, and the evidence's."""
    ctx = {"chat_id": (meta or {}).get("chat_id"), "run_id": (meta or {}).get("run_id")}
    corpus = digit_guard._corpus(ctx) or ""
    for key in ("research", "blueprint"):
        if (meta or {}).get(key):
            corpus += "\n" + digit_guard._dump(meta[key])
    return set(digit_guard._norm(f) for f in digit_guard._figures(draft + "\n" + corpus))


def check_figures(new_text, draft, meta):
    """Rule 2: a statistic in the rewrite that is in neither the article nor the evidence is
    invented, and the proposal is refused with the numbers named. Returns the check result."""
    allowed = _allowed_figures(draft, meta)
    loose = []
    from .checks import draft_checks as dc
    for block in dc.blocks(new_text):
        if dc.HEADING.match(block.strip()):
            continue
        for sentence in dc.sentences(dc.prose(block)):
            for fig in digit_guard._figures(sentence):
                if not digit_guard._is_statistic(sentence, fig):
                    continue
                if digit_guard._norm(fig) in allowed or fig in loose:
                    continue
                loose.append(fig)
    if loose:
        raise InventedFigure(
            "The rewrite brought in %s that the article and its research never had: %s. "
            "Ask for it without the number, or add the source first."
            % ("a figure" if len(loose) == 1 else "figures", ", ".join(loose[:8])))
    return {"name": "no_invented_figures", "status": "pass",
            "detail": "Every figure in the rewrite was already in the article or its evidence.",
            "items": []}


def propose(item_id, draft, section_id, instruction, model=None):
    """Ask the model for one section and return the proposal. WRITES NOTHING.

    Returns {"section_id", "heading", "was", "proposed", "draft", "diff", "checks"} where
    `draft` is the whole article with that one section replaced, ready for the buffer on
    screen. Raises ValueError (bad id, empty reply, a heading rule), InventedFigure, or
    edit_block.BlockDrift.
    """
    meta = store.library_get(item_id)
    if not meta:
        raise ValueError("That article is not in the Library.")
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("Say what should change in this section.")
    draft = draft if isinstance(draft, str) and draft.strip() else (meta.get("draft") or "")
    target = get_section(draft, section_id)
    others = ["%s%s" % ("#" * s["level"] + " " if s["level"] else "", s["heading"])
              for s in sections(draft) if s["id"] != section_id]
    prompt = sh.fill(
        sh.load_prompt("edit_article_section"),
        title=meta.get("title") or eb._title(draft),
        others="\n".join("- " + o for o in others) or "(this is the only section)",
        section=target["text"].strip(),
        instruction=instruction,
        voice=sh.voice_block(),
    )
    raw = (model or llm.text)(prompt, SYSTEM)
    new_text = clean_section(raw, target["text"])
    check_heading(new_text, target["text"])
    checks = [check_figures(new_text, draft, meta)]
    new_draft = splice(draft, section_id, new_text)
    return {"section_id": section_id, "heading": target["heading"], "was": target["text"],
            "proposed": new_text, "draft": new_draft,
            "diff": make_diff(target["text"], new_text), "checks": checks}


# ---- the whole-article AI rewrite (WP4B, Aparna, 2026-09-17) ------------------------------------------
# She asked for a whole article to be rewritten from a pasted review, not one section at a time. This is
# the same shape as propose() above -- one model call, nothing written, a diff to approve -- except there
# is no section to splice: the reply replaces the whole draft, so the guards move from "did every OTHER
# section survive" to "did every heading and every [c...] tag survive", because a style pass over the
# whole thing has no untouched sections left to compare against.

ARTICLE_SYSTEM = ("You are a working editor. Reply with the rewritten article and nothing else: "
                   "no preamble, no sign-off, no notes about what you changed.")

# Every [c1] / [c88, c91] style tag, read as the individual ids inside it, so "[c88, c91]" and
# "[c88][c91]" count as the same two tags -- a style rewrite is free to regroup them, never to
# add, drop, or lose one along the way.
CITE_GROUP = re.compile(r"\[(c\d+(?:\s*,\s*c\d+)*)\]")
CITE_ID = re.compile(r"c\d+")


def citation_ids(text):
    """Every source-tag id in the text, in order, one entry per id (a grouped tag like
    "[c88, c91]" counts as two)."""
    out = []
    for m in CITE_GROUP.finditer(text or ""):
        out.extend(CITE_ID.findall(m.group(1)))
    return out


def check_headings_unchanged(new_text, original):
    """A whole-article style rewrite may not add, drop, reorder or reword a single heading.
    Headings are decided upstream, researched against real search data; this route only touches
    the prose underneath them."""
    def heads(md):
        return [(s["level"], s["heading"]) for s in sections(md) if s["level"]]
    was, now = heads(original), heads(new_text)
    if was != now:
        raise ValueError("The rewrite changed a heading. Every heading must come back exactly as "
                         "it was, in the same order -- headings are not this route's to touch.")
    return True


def check_citations_unchanged(new_text, original):
    """Every [c...] source tag survives a style rewrite, exactly as many times as it was there
    before. A fact may move to a clearer sentence and its tag moves with it; none may be added
    or dropped along the way."""
    was, now = collections.Counter(citation_ids(original)), collections.Counter(citation_ids(new_text))
    if was != now:
        lost = sorted((was - now).elements())
        added = sorted((now - was).elements())
        bits = []
        if lost:
            bits.append("dropped %s" % ", ".join(lost))
        if added:
            bits.append("added %s" % ", ".join(added))
        raise ValueError("The rewrite changed the source tags (%s). Every [c...] tag must stay, "
                         "attached to the fact it proves." % "; ".join(bits))
    return True


def propose_article(item_id, draft, instruction, model=None):
    """Ask the model to rewrite the WHOLE article for style against the reader's feedback, and
    return the proposal. WRITES NOTHING.

    Same contract as propose() above -- nothing is written, the reply comes back as a proposal
    plus a diff, and the buffer only changes when the screen presses "Use this" -- but over the
    whole article instead of one section, so there is no splice: `proposed` IS the new draft.

    Returns {"was", "proposed", "draft", "diff", "checks"}. Raises ValueError (bad id, empty
    instruction, a heading or a source-tag drift) or InventedFigure (a new number that is in
    neither the article nor its evidence).
    """
    meta = store.library_get(item_id)
    if not meta:
        raise ValueError("That article is not in the Library.")
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("Say what should change.")
    draft = draft if isinstance(draft, str) and draft.strip() else (meta.get("draft") or "")
    if not draft.strip():
        raise ValueError("There is no article here to rewrite.")
    prompt = sh.fill(
        sh.load_prompt("write/edit-article"),
        title=meta.get("title") or eb._title(draft),
        article=draft.strip(),
        instruction=instruction,
        voice=sh.voice_block(),
    )
    raw = (model or llm.text)(prompt, ARTICLE_SYSTEM)
    new_text = clean_section(raw, draft)
    check_headings_unchanged(new_text, draft)
    check_citations_unchanged(new_text, draft)
    checks = [check_figures(new_text, draft, meta)]
    return {"was": draft, "proposed": new_text, "draft": new_text,
            "diff": make_diff(draft, new_text), "checks": checks}


# ---- the team ------------------------------------------------------------------------------------------

def _client(client=None):
    if client is not None:
        return client
    from .workspace import client as real
    return real


def actor(client=None):
    """The name stamped on this person's edits: the workspace member name when there is one."""
    try:
        return _client(client).actor() or ""
    except Exception:                       # noqa: BLE001 -- no workspace package, no settings
        return os.environ.get("USER", "").strip() or "unknown"


def actor_id(client=None):
    try:
        return str(_client(client).settings().get("member_id") or "").strip()
    except Exception:                       # noqa: BLE001
        return ""


def team_status(client=None):
    """Can this person's edit reach the team? {"configured", "member", "why"}.

    The member rule: a Mac with a workspace URL and key but no member id has not joined (the
    join is what mints the id), so its edits stay local. Row Level Security on the `library`
    table then bounds what any member can touch to this one workspace's rows.
    """
    c = _client(client)
    try:
        configured = bool(c.configured())
    except Exception:                       # noqa: BLE001
        configured = False
    if not configured:
        return {"configured": False, "member": False,
                "why": "No team workspace is connected, so this stays on this Mac. Connect one "
                       "from the Connections tab and it reaches everyone."}
    try:
        mid = str(c.settings().get("member_id") or "").strip()
    except Exception:                       # noqa: BLE001
        mid = ""
    if not mid:
        return {"configured": True, "member": False,
                "why": "You are not a member of this workspace yet, so this stays on this Mac. "
                       "Join it from the Connections tab."}
    return {"configured": True, "member": True, "why": ""}


def _remote(item_id, client):
    """The team's row for this article, or None when there is none (or we are offline: the
    caller treats both the same, and the poller is the second line of defence)."""
    try:
        return _client(client).one("library", where={"item_id": item_id},
                                   columns="item_id,title,actor,updated_at,meta")
    except Exception:                       # noqa: BLE001 -- offline, table asleep, no row
        return None


def _current_of(meta, draft=None):
    """What the screen needs to say "Updated by X just now" and offer their version."""
    return {"version": int(meta.get("version") or 0), "title": meta.get("title") or "",
            "edited_by": meta.get("edited_by") or meta.get("actor") or "",
            "edited_at": meta.get("edited_at") or meta.get("updated_at") or "",
            "draft": draft if draft is not None else meta.get("draft") or ""}


def _land_remote(item_id, row):
    """A newer team row the poller has not mirrored yet lands now, through the same door the
    poller uses, so "Load their version" has their version to load."""
    from .workspace import mirror
    try:
        mirror.apply({"id": None, "kind": "library", "op": "update", "key": item_id,
                      "payload": row, "actor": row.get("actor") or ""})
    except Exception:                       # noqa: BLE001 -- the poller will do it in a moment
        pass


def save(item_id, draft, title=None, base_version=None, force=False, client=None):
    """The one writer. Local first, then the team. Returns the meta plus `team`, or None when
    there is no such article. Raises Conflict when a newer version exists and force is off.

    `base_version` is the version the person opened. None means "do not check" (the old whole-
    article editor, and scripts), which is last-save-wins exactly as before.
    """
    it = store.library_get(item_id)
    if not it:
        return None
    have = int(it.get("version") or 0)
    team = team_status(client)
    if base_version is not None and not force:
        if have != int(base_version):
            raise Conflict(_current_of(it))
        if team["member"]:
            row = _remote(item_id, client)
            rmeta = (row or {}).get("meta") or {}
            if row and int(rmeta.get("version") or 0) > have:
                _land_remote(item_id, row)
                current = _current_of(dict(rmeta, title=row.get("title"), actor=row.get("actor"),
                                           updated_at=row.get("updated_at")),
                                      draft=row.get("body_md") or "")
                raise Conflict(current)
    who, who_id = actor(client), actor_id(client)
    meta = store.library_update(item_id, draft, title, actor=who, actor_id=who_id)
    if not meta:
        return None
    return dict(meta, team=_push(item_id, team, who, client))


def revert(item_id, client=None):
    """Undo the last save, for the team too. None when there is nothing to go back to."""
    who, who_id = actor(client), actor_id(client)
    meta = store.library_revert(item_id, actor=who, actor_id=who_id)
    if not meta:
        return None
    return dict(meta, team=_push(item_id, team_status(client), who, client))


def undo(item_id, client=None):
    """Step the Open view back one kept version, for the team too. None when this is already the
    oldest version kept (20 at most -- see store.MAX_VERSIONS)."""
    who, who_id = actor(client), actor_id(client)
    meta = store.library_undo(item_id, actor=who, actor_id=who_id)
    if not meta:
        return None
    return dict(meta, team=_push(item_id, team_status(client), who, client))


def redo(item_id, client=None):
    """Step forward one kept version, for the team too. None when there is nothing to redo: either
    nothing was undone, or a fresh edit since dropped the redo tail."""
    who, who_id = actor(client), actor_id(client)
    meta = store.library_redo(item_id, actor=who, actor_id=who_id)
    if not meta:
        return None
    return dict(meta, team=_push(item_id, team_status(client), who, client))


def _push(item_id, team, who, client):
    """The row to the team, queued on disk first. Never raises: the local save already stands."""
    if not team["member"]:
        return dict(team, synced=False, queued=False)
    try:
        from .workspace import sync, outbox
        item = sync.push("library", item_id, store.library_get(item_id), actor=who, client=client)
        left = outbox.status().get("queued") or 0
        if item is None:
            return dict(team, synced=False, queued=False,
                        why="Saved on this Mac. The team workspace could not take it yet.")
        if left:
            return dict(team, synced=False, queued=True,
                        why="Saved on this Mac. It reaches the team when the network is back.")
        return dict(team, synced=True, queued=False, why="")
    except Exception as e:                  # noqa: BLE001 -- the local save is done; say so
        return dict(team, synced=False, queued=False,
                    why="Saved on this Mac. Could not reach the team workspace: %s" % str(e)[:160])
