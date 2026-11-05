"""Atom ids for the function-node layer (function-nodes.md 2.4, engine design 4.3a).

A function atom id is `a-<sid>-<nn>`: `sid` is the library's `atom_sid(run_id, node_id)` and `nn` a counter per (run, node)
that starts at 1. EVERY open attempt consumes a number, a refused one too, so gaps in the log are normal. Ids come only from
the library's helpers (`atom_sid`, `function_atom_id`, `overhead_atom_id`); no other code in the engine builds one.
"""
import threading

from sutra_app.library.types import atom_sid, function_atom_id, function_node_id, overhead_atom_id

__all__ = ["AtomIds", "node_id_of", "run_overhead_id"]


def node_id_of(dept_id: str, function: str) -> str:
    """The graph node of a function in a department: `<dept>.<function>` (the library's `function_node_id`)."""
    return function_node_id(dept_id, function)


def run_overhead_id(run_id: str) -> str:
    """The accounting key of a model call made outside any function turn of this run (it names no atom row and no card)."""
    return overhead_atom_id(run_id)


class AtomIds:
    """The counters. One instance per run process; `next` is safe to call from several threads."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    @staticmethod
    def sid(run_id: str, node_id: str) -> str:
        """The `sid` of the atoms of one node in one run (it is also `Atom.session_id`)."""
        return atom_sid(run_id, node_id)

    def last(self, run_id: str, node_id: str) -> int:
        """The number the last open attempt of this node used (0 before the first)."""
        with self._lock:
            return self._counts.get((run_id, node_id), 0)

    def next(self, run_id: str, node_id: str) -> str:
        """Consume the next number of (run, node) and return the atom id. The number is spent even when the open that
        follows is refused. Bad ids raise the library's `IdError` before a number is spent."""
        sid = atom_sid(run_id, node_id)
        with self._lock:
            number = self._counts.get((run_id, node_id), 0) + 1
            atom_id = function_atom_id(sid, number)
            self._counts[(run_id, node_id)] = number
        return atom_id
