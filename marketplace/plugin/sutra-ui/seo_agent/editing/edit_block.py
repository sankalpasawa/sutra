"""edit_block.py — regenerate ONE block, then prove the rest of the document did not move.

This file exists because of one failure that is almost impossible to catch by reading. Hand
a model a whole draft and ask for "the same thing with the third paragraph rewritten", and
it returns a whole new draft. It retouches sentences nobody asked about, swaps a word here,
tightens a clause there. Every change is small and plausible, so nobody notices, and the
text the user approved has quietly become text they never read.

So the model never sees the document as something to hand back. It sees one block, its
neighbours as read-only context, and the instruction, and it returns that one block. The
splice happens here in code. Then every other block is compared byte for byte against what
it was, and a mismatch raises instead of saving. That assertion is the whole point of the
file: without it this is just a smaller prompt, and a smaller prompt is still a promise.

Addressing:
    markdown   blocks are paragraphs, split on blank lines, named p0, p1, p2 in order
    blueprint  blocks are sections, named by the section's own id
"""
import copy
import json
import re

from .. import llm
# The prompt loader lives with the tools because they were first to need it. Reusing it
# keeps the shared writing rules in one file: an inline copy here would drift the moment
# someone edits the ban list.
from ..tools import _shared as sh

SYSTEM = ("You are a working editor. Reply with the rewritten passage and nothing else: "
          "no preamble, no sign-off, no notes about what you changed.")

BLOCK_ID_RE = re.compile(r"^p(\d+)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


class BlockDrift(RuntimeError):
    """Raised when a block nobody asked about came back different. Never caught in here:
    the caller must see it, because the alternative is saving a document the user did not
    approve."""


# ---- splitting markdown ---------------------------------------------------------------------

def chunks(md):
    """Split markdown into alternating block and gap pieces, losing nothing.

    "".join(text for _, text in chunks(md)) == md, exactly. Reconstruction has to be exact
    or the byte-identical assertion below is measuring the splitter rather than the model.

    Blank lines inside a fenced code block are not paragraph breaks, so fences are tracked
    and a code sample stays one block instead of being torn into three.
    """
    lines = (md or "").splitlines(keepends=True)
    out, current, kind, fence = [], [], None, None
    for line in lines:
        stripped = line.strip()
        if fence is not None:
            this = "block"
            if stripped.startswith(fence):
                fence = None
        elif FENCE_RE.match(line):
            fence = stripped[:3]
            this = "block"
        else:
            this = "gap" if stripped == "" else "block"
        if kind is None:
            kind = this
        if this != kind:
            out.append((kind, "".join(current)))
            current, kind = [], this
        current.append(line)
    if current:
        out.append((kind, "".join(current)))
    return out


def blocks(md):
    """The addressable blocks, in order, exactly as they appear in the document."""
    return [text for kind, text in chunks(md) if kind == "block"]


def block_ids(md):
    return ["p%d" % i for i in range(len(blocks(md)))]


def block_map(md):
    """block id -> exact text. The unit the assertion compares."""
    return dict(zip(block_ids(md), blocks(md)))


def get_block(md, block_id):
    m = block_map(md)
    if block_id not in m:
        raise ValueError("No block %r in this document. It has %d blocks, p0 to p%d."
                         % (block_id, len(m), max(len(m) - 1, 0)))
    return m[block_id]


# ---- the safety net ---------------------------------------------------------------------------

def assert_only_target_changed(old_map, new_map, target_id):
    """Every block except the target must be byte-identical. Raise if not.

    Ordered dicts of id -> exact text, which is why the same function serves markdown
    paragraphs and blueprint sections. A changed block count counts as drift too: if an edit
    added or removed a block, every id after it now points at different text, and the user's
    next edit would land in the wrong place.
    """
    if list(old_map.keys()) != list(new_map.keys()):
        raise BlockDrift(
            "The set of blocks changed. Was %d blocks, now %d. Only %s should have changed."
            % (len(old_map), len(new_map), target_id))
    drifted = [bid for bid in old_map
               if bid != target_id and old_map[bid] != new_map[bid]]
    if drifted:
        first = drifted[0]
        raise BlockDrift(
            "%d block(s) changed that nobody asked to change: %s. Only %s was meant to move. "
            "First difference in %s:\n  was: %s\n  now: %s"
            % (len(drifted), ", ".join(drifted), target_id, first,
               old_map[first].strip()[:160], new_map[first].strip()[:160]))
    return True


# ---- splicing markdown -------------------------------------------------------------------------

def clean_block(raw, original):
    """Make the model's reply safe to splice.

    Two jobs. Strip the wrapper a model adds when it forgets not to (code fences, "Here is
    the rewritten paragraph:"), and collapse any blank line inside it. A blank line would
    split one block into two, and then p4 means something different from what it meant a
    second ago, which silently breaks the next edit the user makes.
    """
    text = (raw or "").strip()
    if text.startswith("```") or text.startswith("~~~"):
        parts = text.split("\n")
        parts = parts[1:]
        while parts and parts[-1].strip().startswith(("```", "~~~")):
            parts.pop()
        text = "\n".join(parts).strip()
    text = re.sub(r"(?is)^(?:sure[,!.]?\s*)?here(?:'s| is| are)[^\n:]{0,80}:\s*", "", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if not text:
        raise ValueError("The model returned nothing for this block.")

    # Keep the original's trailing newlines so the surrounding gaps stay exactly as they were.
    trailing = original[len(original.rstrip("\n")):]
    return text + trailing


def splice_markdown(md, block_id, new_text):
    """Put new_text in place of block_id and prove nothing else moved. Returns the document."""
    old_map = block_map(md)
    if block_id not in old_map:
        raise ValueError("No block %r in this document." % (block_id,))
    target_index = int(BLOCK_ID_RE.match(block_id).group(1))

    pieces, seen = [], -1
    for kind, text in chunks(md):
        if kind == "block":
            seen += 1
            pieces.append(new_text if seen == target_index else text)
        else:
            pieces.append(text)
    out = "".join(pieces)

    assert_only_target_changed(old_map, block_map(out), block_id)
    return out


# ---- splicing a blueprint --------------------------------------------------------------------

def section_map(blueprint):
    """section id -> canonical JSON. Sorted keys so a reordered dict is not read as a change."""
    out = {}
    for i, sec in enumerate(((blueprint or {}).get("sections") or [])):
        if isinstance(sec, dict):
            sid = str(sec.get("id") or "s%d" % (i + 1))
            out[sid] = json.dumps(sec, sort_keys=True, ensure_ascii=False)
    return out


def splice_section(blueprint, section_id, new_section):
    """Replace one section and prove the others, and the blueprint's own fields, held still."""
    old_map = section_map(blueprint)
    if section_id not in old_map:
        raise ValueError("No section %r in this blueprint. It has: %s."
                         % (section_id, ", ".join(old_map) or "none"))
    out = copy.deepcopy(blueprint)
    for i, sec in enumerate(out.get("sections") or []):
        if str(sec.get("id") or "s%d" % (i + 1)) == section_id:
            out["sections"][i] = new_section
            break

    assert_only_target_changed(old_map, section_map(out), section_id)
    # The sections are proven. The blueprint's own fields are proven here, because a model
    # handed a section has no business renaming the article.
    old_top = {k: v for k, v in (blueprint or {}).items() if k != "sections"}
    new_top = {k: v for k, v in out.items() if k != "sections"}
    if json.dumps(old_top, sort_keys=True) != json.dumps(new_top, sort_keys=True):
        raise BlockDrift("The blueprint's own fields changed while editing section %s."
                         % section_id)
    return out


# ---- the model calls ----------------------------------------------------------------------------

def _neighbours(md, block_id):
    bl = blocks(md)
    i = int(BLOCK_ID_RE.match(block_id).group(1))
    before = bl[i - 1].strip() if i > 0 else "(this is the first block in the document)"
    after = bl[i + 1].strip() if i + 1 < len(bl) else "(this is the last block in the document)"
    return before, after


def _enclosing_heading(md, block_id):
    """The heading the block sits under, so the model knows what the paragraph is for."""
    bl = blocks(md)
    i = int(BLOCK_ID_RE.match(block_id).group(1))
    for j in range(i, -1, -1):
        line = bl[j].strip()
        if line.startswith("##"):
            return line.lstrip("# ").strip()
    return "(no heading above this block)"


def _title(md):
    for b in blocks(md):
        if b.strip().startswith("# "):
            return b.strip().lstrip("# ").strip()
    return "(untitled)"


def rewrite_block(md, block_id, instruction, context=None):
    """Ask the model for one paragraph. Isolated here so the splice and the assertion above
    stay pure functions a test can drive without a model key."""
    context = context or {}
    original = get_block(md, block_id)
    before, after = _neighbours(md, block_id)
    prompt = sh.fill(
        sh.load_prompt("edit_block"),
        title=context.get("title") or _title(md),
        section=_enclosing_heading(md, block_id),
        before=before, after=after,
        block=original.strip(),
        instruction=instruction,
        voice=sh.voice_block(context.get("brand_voice")),
    )
    return clean_block(llm.text(prompt, SYSTEM), original)


def rewrite_section(blueprint, section_id, instruction, context=None):
    """Ask the model for one blueprint section, as JSON."""
    context = context or {}
    secs = (blueprint or {}).get("sections") or []
    target, others = None, []
    for i, sec in enumerate(secs):
        sid = str(sec.get("id") or "s%d" % (i + 1))
        if sid == section_id:
            target = sec
        else:
            others.append("%s: %s" % (sec.get("heading", sid), (sec.get("covers") or "")[:160]))
    if target is None:
        raise ValueError("No section %r in this blueprint." % (section_id,))

    candidates = context.get("link_candidates")
    if candidates is None:
        candidates = sh.link_candidates(topic=blueprint.get("title", ""))
    prompt = sh.fill(
        sh.load_prompt("edit_section"),
        title=blueprint.get("title", ""),
        primary=context.get("primary_keyword", ""),
        others="\n".join("- " + o for o in others) or "(this is the only section)",
        section=json.dumps(target, indent=2, ensure_ascii=False),
        instruction=instruction,
        section_id=section_id,
        link_candidates=sh.bullets(["%s  %s" % (p["url"], p.get("title", "")) for p in candidates],
                                   "(no site index, so use no internal links)"),
        voice=sh.voice_block(context.get("brand_voice")),
    )
    new_section = llm.json_call(prompt)
    if not isinstance(new_section, dict):
        raise ValueError("The model returned %s, not a section object."
                         % type(new_section).__name__)
    # The id is ours, not the model's. Letting it rename the section would move the address
    # the user just edited.
    new_section["id"] = section_id
    return new_section


# ---- the entry point -------------------------------------------------------------------------------

def edit_block(text_or_obj, block_id, instruction, context=None):
    """Rewrite one block of a draft or one section of a blueprint.

    Returns {"new": the whole document with that one block replaced,
             "changed_blocks": [the block id]}.

    Raises BlockDrift if anything else moved, ValueError if the block id does not exist or
    the model came back with nothing usable. It raises rather than returning a flag because
    the caller's next line saves the result, and a flag is something a caller can forget.
    """
    context = dict(context or {})
    block_id = (block_id or "").strip()
    if not block_id:
        raise ValueError("No block id given. Nothing to edit.")
    if not (instruction or "").strip():
        raise ValueError("No instruction given. Nothing to do.")

    if isinstance(text_or_obj, dict):
        new_section = rewrite_section(text_or_obj, block_id, instruction, context)
        return {"new": splice_section(text_or_obj, block_id, new_section),
                "changed_blocks": [block_id]}

    md = text_or_obj if isinstance(text_or_obj, str) else str(text_or_obj)
    if not BLOCK_ID_RE.match(block_id):
        raise ValueError("Block ids in markdown look like p0, p1, p2. Got %r." % (block_id,))
    new_text = rewrite_block(md, block_id, instruction, context)
    return {"new": splice_markdown(md, block_id, new_text),
            "changed_blocks": [block_id]}
