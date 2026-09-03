"""tags.py — the [c<id>] source tag: ONE definition, used by every step that reads or rewrites prose.

Ported verbatim from the write phase's scripts/tags.py.

A writer may put several cards behind one claim, and it writes them as one bracket:
    "...a bad hire costs 30% of first-year salary [c412]"
    "...two studies agree on the range [c4352, c1265]"
    "...three sources, no space [c11,c12,c13]"
    "...a run of consecutive cards [c221-c227]"   (also with an en or em dash)

Every step used to carry its own `\\[c\\s*(\\d+)\\]`, which matches ONLY the single-id form. The
multi-id form was therefore invisible: assemble never turned it into a numbered reference (so raw
tags shipped in the article), the blend/wrapper audits never saw those ids (so an invented one could
not be caught), and the review page never made them hoverable. 31 raw tags reached one finished
draft that way.

The RANGE form was the same bug a second time: a writer emitted "[c221–c227]" with an EN DASH, no
step matched it, and it printed raw inside a published table. A range means every id from first to
last, so it is expanded. A reversed or implausibly long range is not a range; those keep their
endpoints only.

So: match the whole bracket, then read every id inside it, expanding any range.
"""
import re

_SEP = r"[-‐-―]"                 # hyphen, non-breaking hyphen, figure/en/em dash, horizontal bar
_ONE = r"c?\s*\d+(?:\s*" + _SEP + r"\s*c?\s*\d+)?"
BLOCK = re.compile(r"\[\s*c\s*\d+(?:\s*" + _SEP + r"\s*c?\s*\d+)?"
                   r"(?:\s*,\s*" + _ONE + r")*\s*\]", re.I)
_DIGITS = re.compile(r"\d+")
_PART = re.compile(r"c?\s*(\d+)\s*(?:(" + _SEP + r")\s*c?\s*(\d+))?", re.I)

MAX_RANGE = 60          # a "range" wider than this is a mis-write, not a run of cards — keep the ends only


def _block_ids(block):
    """Every id in a matched span, in order, expanding "c221-c227" into 221..227.

    Splits on brackets AS WELL AS commas, because merge_adjacent hands this a whole RUN of touching
    blocks ("[c2675][c3709]") and not just one bracket.
    """
    out = []
    for part in re.split(r"[,\[\]]", block):
        m = _PART.search(part)
        if not m:
            continue
        a = int(m.group(1))
        if not m.group(2):                          # a plain id
            out.append(a)
            continue
        b = int(m.group(3))
        if a < b <= a + MAX_RANGE:                  # a real run of consecutive cards
            out += list(range(a, b + 1))
        else:                                       # reversed or absurd — not a range
            out += [a, b]
    return out


def ids(text):
    """Every card id referenced anywhere in `text`, in order, including repeats."""
    out = []
    for m in BLOCK.finditer(text or ""):
        out += _block_ids(m.group(0))
    return out


def id_set(text):
    return set(ids(text))


_ADJACENT = re.compile(r"(?:" + BLOCK.pattern + r")(?:\s*(?:" + BLOCK.pattern + r"))+", re.I)


def merge_adjacent(text):
    """Fuse a RUN of touching tag blocks into one: "[c2675][c3709]" -> "[c2675, c3709]".

    Writers emit both forms, and a run of separate blocks used to be substituted one block at a time,
    so a caller's de-duplication never saw the pair. Two different cards that share one source URL then
    rendered as the SAME reference number twice — the "[9][9]" (displayed as "99") seen in a real draft.
    Merging first means every caller de-dupes across the whole run, once.
    """
    def _one(m):
        ids_ = list(dict.fromkeys(_block_ids(m.group(0))))
        return "[" + ", ".join("c%d" % i for i in ids_) + "]"
    return _ADJACENT.sub(_one, text or "")


def sub(text, fn):
    """Rewrite each tag block. `fn(list_of_ids)` returns the replacement string.
    Touching blocks are fused first, so `fn` sees one run's ids together and can de-duplicate."""
    return BLOCK.sub(lambda m: fn(_block_ids(m.group(0))), merge_adjacent(text or ""))


def drop(text, unwanted):
    """Remove the given ids. A block loses only those ids; a block left empty disappears entirely."""
    unwanted = set(unwanted)

    def _one(found):
        keep = [i for i in found if i not in unwanted]
        return "[" + ", ".join("c%d" % i for i in keep) + "]" if keep else ""

    return re.sub(r"\s+([.,;:])", r"\1", re.sub(r"[ \t]{2,}", " ", sub(text, _one))).strip()
