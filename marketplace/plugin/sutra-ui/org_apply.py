"""org_apply.py -- commit a drag-and-drop reorg plan to the registry.

WHY THIS EXISTS
The Departments studio composes a plan by dragging one department onto another
(03-org.js): each drop is a MOVE, live-validated with blocking rings and held in
a draft. Until now the only way to COMMIT that plan was to copy a CLI string --
there was no Apply. Founder, 2026-09-13: the drop should edit the linkage.

WHY IT IS ITS OWN MODULE
org_api.py is read-mostly by design and test_forbidden_calls.py fails the build
if it names `restructure` (or any other engine mutator). Apply must call
`restructure`, so it lives here -- the same reason project_import.py lives apart
to call `mint_domain`. org_api's route calls apply_moves(), which is not a
forbidden name, so the gate stays green.

THE ONE INVARIANT: ONLY A MOVE, NOTHING OUTSIDE THE REGISTRY
The founder's constraint is "drag and drop should only edit the linkages inside
Sutra; nothing outside Sutra will change." A MOVE is exactly that and no more:
`restructure("move", ...)` sets one domain record's `parent_ref` and appends an
audit line, both under SUTRA_NATIVE_HOME (placement_engine _restructure_locked).
It re-mints ZERO placements (I-P8), touches no project directory, no ~/.claude
transcript, no git repo, no file on disk outside the registry. This module
enforces the constraint STRUCTURALLY: it refuses any op that is not a move, so
there is no code path here that could reach rename/merge/delete/retire or write
anything but a parent_ref. A wrong op is rejected before the registry is read.
"""
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402
import reorg_sim              # noqa: E402


class ApplyRefused(Exception):
    """The plan did not pass validation, so nothing was written. Carries the
    blocking findings the studio already knows how to render."""
    def __init__(self, message, blocks=None):
        super().__init__(message)
        self.blocks = blocks or []


def _normalise(ops):
    """The ops we will apply, or a ValueError naming the first bad one.

    THE STRUCTURAL GUARD. Every op must be a move with a ref and a target.
    Anything else -- a rename, a delete, a stray key -- is refused here, before
    load_domains() is even called, so 'only a move' is not a convention the rest
    of the function has to remember but a precondition it can assume."""
    if not isinstance(ops, list) or not ops:
        raise ValueError("no moves to apply")
    clean = []
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise ValueError("op %d is not an object" % i)
        if op.get("op") != "move":
            raise ValueError(
                "op %d is %r; only 'move' may be applied here -- drag-and-drop "
                "edits linkages and nothing else" % (i, op.get("op")))
        ref, target = op.get("ref"), op.get("target")
        if not ref or not target:
            raise ValueError("op %d is missing ref or target" % i)
        if ref == target:
            raise ValueError("op %d moves a department onto itself" % i)
        clean.append({"op": "move", "ref": ref, "target": target})
    return clean


def validate(ops, base=None, now_ms=None):
    """Run the SAME server-side check the studio's rings show, against a fresh
    registry read. Returns the blocking findings (empty == safe to apply).

    Fresh read every call: a plan composed minutes ago must be judged against
    the tree as it is now, not as it was captured. `base` carries the draft's
    fingerprint so a concurrent mint since then raises ORG-010 (drift) rather
    than applying onto a tree the operator was not looking at."""
    clean = _normalise(ops)
    domains = E.load_domains()
    placements = E.all_placements()
    # DRIFT (ORG-010) is computed by the CALLER, not by simulate: it fires only
    # when base carries {"_mismatch": True}. /org/simulate derives that from the
    # domain-index row count, and apply must derive it the SAME way or it would
    # never catch a tree that gained a department while the operator dragged --
    # the exact "hazard is staleness" the old no-Apply note warned about.
    base_mismatch = None
    if base and base.get("domain_index_lines") is not None \
            and base["domain_index_lines"] != len(E._read_jsonl(E.DOMAIN_INDEX)):
        base_mismatch = {"_mismatch": True}
    sim = reorg_sim.simulate(clean, domains, charters=None,
                             placements=placements, base=base_mismatch, now_ms=now_ms)
    return [f for f in sim.get("findings", []) if f.get("sev") == "block"]


def apply_moves(ops, base=None, now_ms=None):
    """Commit a validated batch of MOVEs. Returns what changed.

    Order: guard (moves only) -> validate against the live tree -> refuse if
    anything blocks -> apply each move under the engine's restructure lock.
    restructure() itself re-rejects cycles, so a race that slips past validate
    still cannot orphan a subtree.

    Raises ValueError for a malformed plan and ApplyRefused (with the blocking
    findings) for a plan that no longer validates -- in both cases the registry
    is untouched, because nothing is written until every move has cleared."""
    clean = _normalise(ops)
    blocks = validate(clean, base=base, now_ms=now_ms)
    if blocks:
        raise ApplyRefused(
            "plan no longer validates: %s"
            % ", ".join(sorted({b.get("code", "?") for b in blocks})),
            blocks=blocks)

    applied = []
    for op in clean:
        before = (E.load_domains().get(op["ref"]) or {}).get("parent_ref")
        E.restructure("move", op["ref"], target=op["target"])
        after = (E.load_domains().get(op["ref"]) or {}).get("parent_ref")
        applied.append({"ref": op["ref"], "target": op["target"],
                        "parent_before": before, "parent_after": after})
    return {"applied": True, "count": len(applied), "moves": applied}
