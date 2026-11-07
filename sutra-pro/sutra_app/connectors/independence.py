"""Independent audit: the checker is not the maker (GAP2 rules-notes; the old money-movement floor "one makes, another checks", for models).

    independence = Independence()
    independence.note(ctx, "claude")        # a call of a builder ("W-3") of run R was served by claude
    independence.avoid_for(ctx)             # for a call of Audit of run R: the providers that served R's builders ([] for any other call)
    independence.builders("R")              # the same set, for the note the router writes

The router puts `avoid_for(ctx)` into the plan's soft `avoid` (those providers are tried LAST) when `defaults.independent_audit` is on, so Audit's
judgement of a run is made by the other closed model than the one that built the work: Claude built, Codex audits, and the reverse. When the other
model is unavailable (signed out, out of quota) the audit still runs, on the same one, and the router's note says it was not independent. A team
pinned with the chat pill, or a router restricted to one provider, keeps its provider and the note says so too. Off by default: whether Codex passes
Audit's reply checks as often as Claude is not measured (gaps G07, G14).

The tag is what J2's calls already carry (`CallTag.function`: `W-<n>` for a builder, `audit` for Audit) and `CallTag.run_id` keeps one run's builders
apart from another's; nothing in the engine changes. The memory is bounded (the newest `RUNS_KEPT` runs) and thread-safe like the health book.
"""
import threading
from collections import OrderedDict
from typing import Any

__all__ = ["Independence", "RUNS_KEPT", "NOT_INDEPENDENT"]

RUNS_KEPT = 256
CLOSED_MODELS = ("claude", "codex")                # the stub and anything else never counts as a maker or a checker
NOT_INDEPENDENT = "not independent: the audit ran on the model that built the work, because the other one was not used"


class Independence:
    def __init__(self, *, runs_kept: int = RUNS_KEPT) -> None:
        self._lock = threading.Lock()
        self._built: OrderedDict[str, set[str]] = OrderedDict()           # run id -> the providers that served its builders' calls
        self._kept = max(1, runs_kept)

    @staticmethod
    def _tag(ctx: Any) -> tuple[str, str]:
        tag = getattr(ctx, "tag", None)
        return str(getattr(tag, "run_id", "") or ""), str(getattr(tag, "function", "") or "")

    def note(self, ctx: Any, provider: str) -> None:
        """Remember that `provider` served a builder's call of this run. Any other call, provider or run-less call is ignored."""
        run_id, function = self._tag(ctx)
        if not run_id or not function.startswith("W-") or provider not in CLOSED_MODELS:
            return
        with self._lock:
            self._built.setdefault(run_id, set()).add(provider)
            self._built.move_to_end(run_id)
            while len(self._built) > self._kept:
                self._built.popitem(last=False)

    def builders(self, run_id: str) -> frozenset[str]:
        with self._lock:
            return frozenset(self._built.get(run_id, ()))

    def avoid_for(self, ctx: Any) -> list[str]:
        """The providers to try last for this call: those that built the run's work, when this is a call of Audit; else []."""
        run_id, function = self._tag(ctx)
        if function != "audit" or not run_id:
            return []
        return sorted(self.builders(run_id))
