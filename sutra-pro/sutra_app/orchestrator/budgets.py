"""Slices and ceilings of a project (multi-agent nodes, MAN-9; D271, D272, D294, D300): pure functions, no database.

    slices = make_slices([120, 80, 0], ceiling=300)        # a share of the project's credits for each step; the sum is never over the ceiling
    moved  = move_unspent(slices, spent, 300, donor=0, taker=1, amount=20)

A slice is the work credits one node's run starts with (`J2_BUDGET`) and may not go past (`J2_BUDGET_CAP`): the node cannot raise it itself (P25, D251: a raise is the Requester's own). The project's
ceiling is the sum of the slices (`projects.budget_credits`). Unspent credits of one node may move to another inside the ceiling and never beyond it; nothing here can raise the ceiling, and Decide
for me cannot either (D294). `egress_scrubs` counts, per node, the audit rows of `egress.jsonl` in which something was scrubbed (D303: the same node three times ends it).
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

__all__ = ["DEFAULT_SLICE", "SCRUB_LIMIT", "make_slices", "unspent", "move_unspent", "egress_scrubs"]

DEFAULT_SLICE = 100                      # the work credits a step's run starts with when nobody said otherwise (J2_BUDGET's default; D300)
SCRUB_LIMIT = 3                          # the same node's prompts scrubbed this many times end the node (D303)
_TAIL_BYTES = 2 * 1024 * 1024            # how much of the end of egress.jsonl is read


def make_slices(wants: Sequence[int], ceiling: int | None = None) -> list[int]:
    """One slice per step: what the step wants (at least 1; anything that is not a whole number counts as the default), and, when `ceiling` is given and the wants add up to more, every slice cut
    in proportion (never below 1 while the ceiling allows one for each) so that the sum is never over the ceiling."""
    asked = [max(1, w) if isinstance(w, int) and not isinstance(w, bool) else DEFAULT_SLICE for w in wants]
    if ceiling is None or sum(asked) <= ceiling:
        return asked
    ceiling = max(0, int(ceiling))
    if ceiling < len(asked):                                   # not even one credit each: the first steps get one, the rest none
        return [1 if index < ceiling else 0 for index in range(len(asked))]
    total = sum(asked)
    cut = [max(1, w * ceiling // total) for w in asked]
    while sum(cut) > ceiling:                                  # the minimum of one can overshoot: take from the largest
        cut[cut.index(max(cut))] -= 1
    return cut


def unspent(slice_credits: int, spent: int) -> int:
    return max(0, int(slice_credits) - max(0, int(spent)))


def move_unspent(slices: Sequence[int], spent: Sequence[int], ceiling: int, donor: int, taker: int, amount: int) -> list[int]:
    """Move `amount` credits from the unspent part of `donor`'s slice to `taker`'s. Only whole, positive amounts the donor has not spent, between two different steps, and only while the sum stays
    inside the ceiling: anything else returns the slices unchanged. The sum never changes, so the ceiling is never raised."""
    out = list(slices)
    if not (0 <= donor < len(out) and 0 <= taker < len(out)) or donor == taker or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return out
    if amount > unspent(out[donor], spent[donor] if donor < len(spent) else 0) or sum(out) > ceiling:
        return out
    out[donor] -= amount
    out[taker] += amount
    return out


def egress_scrubs(path: str | Path, node_ids: Sequence[str] | None = None) -> dict[str, int]:
    """Per node id, how many rows of the egress audit file say something was scrubbed (`shapes` is not empty). Only the end of the file is read; a line that is not a row is skipped; a node that has
    none is absent. `node_ids` limits the answer to those nodes."""
    wanted = set(node_ids) if node_ids is not None else None
    counts: dict[str, int] = {}
    try:
        size = Path(path).stat().st_size
        with open(path, "rb") as handle:
            handle.seek(max(0, size - _TAIL_BYTES))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return counts
    for line in tail.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        node = row.get("node") if isinstance(row, dict) else None
        if isinstance(node, str) and row.get("shapes") and (wanted is None or node in wanted):
            counts[node] = counts.get(node, 0) + 1
    return counts
