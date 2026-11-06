"""How long the owner has kept a team waiting, and why a queued task is not starting (gap package attention; docs/notes/GAP-attention.md).

    age_words(3 * 86400)                              # "3 days"
    ask_state(asked_at, now)                          # (waiting_s, stale): stale from ASK_STALE_S (24 h) of waiting
    why_waiting(busy_status="waiting_user", ...)      # "waiting for your answer: the team's current task asked you something"

Pure: no clock, no database. Everything is derived at read time from times the store already holds (a question's `at`, the counts
of live tasks), so nothing is scheduled and nothing is stored. An unanswered question holds the team's one live slot, so the owner is
told plainly when a task waits on the owner rather than on the machine.
"""

__all__ = ["ASK_STALE_S", "age_words", "ask_state", "why_waiting", "TEAM_BUSY", "OWNER_BUSY"]

ASK_STALE_S = 24 * 3600            # a question unanswered this long is "stale" (marked on the strip; nothing else changes)
TEAM_BUSY = "waiting for the team to finish its current task"
OWNER_BUSY = "waiting for your answer: the team's current task asked you something"

_UNITS = ((86400, "day"), (3600, "hour"), (60, "minute"))


def age_words(seconds: int | float) -> str:
    """A whole duration in plain words, rounded down to its largest unit: "just now" under a minute, then "1 minute", "5 hours",
    "3 days". A negative or broken value is "just now" (a clock that moved back must not print a minus)."""
    try:
        whole = int(seconds)
    except (TypeError, ValueError, OverflowError):
        return "just now"
    for size, unit in _UNITS:
        if whole >= size:
            n = whole // size
            return f"{n} {unit}" + ("" if n == 1 else "s")
    return "just now"


def ask_state(asked_at: int, now: int, stale_s: int = ASK_STALE_S) -> tuple[int, bool]:
    """(seconds the question has waited, whether that is past `stale_s`). A question from the future (clock skew) has waited 0 s."""
    waited = max(0, int(now) - int(asked_at))
    return waited, waited >= int(stale_s)


def why_waiting(*, busy_status: str | None, working: int, live: int, max_runs: int, max_live: int) -> str:
    """The detail of a queued task that may not start. `busy_status` is the status of the live task of the SAME department (None when
    the team has none); `working` counts tasks starting or running, `live` adds the ones waiting for the owner. Empty when nothing
    stops it (the caller starts it).

        the team's live task waits for the owner     -> OWNER_BUSY (it is the owner's answer, not the team, that is missing)
        the team's live task is working              -> TEAM_BUSY
        every working slot is taken                  -> "waiting for a free slot (3 teams working)"
        every live slot is taken by waiting teams    -> "waiting for a free slot: 12 teams are waiting for your answers" (with the
                                                        working count in front when some work)"""
    if busy_status == "waiting_user":
        return OWNER_BUSY
    if busy_status is not None:
        return TEAM_BUSY
    if working >= max_runs:
        return f"waiting for a free slot ({working} teams working)"
    if live >= max_live:
        asking = max(0, live - working)
        teams = f"{asking} team{'' if asking == 1 else 's'} {'is' if asking == 1 else 'are'} waiting for your answers"
        return "waiting for a free slot: " + (teams if working == 0 else f"{working} teams working, {teams}")
    return ""
