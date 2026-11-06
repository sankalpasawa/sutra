"""Code that stands in for the model: the keyword fallback, the status report and the template lines (orchestrator 5.2, 5.3).

    fallback_plan(text, chart)        T5: when a stage fails three times (or the call cap is reached): the one department whose name and
                                      purpose share at least 2 words with the request and more than any other, else a list of candidates
    candidates(chart, text, ids=)     up to 3 teams to offer in a `choice` card (the named ids first, then the best word overlap)
    status_report(chart, tasks)       the answer to a question about progress, built from the chart and the tasks (with `now`, how long a
                                      team has waited for the owner: gap package attention)
    LINES / line(key, **kw)           every Sutra sentence of the org chat; no model sentence is ever shown
    matches_template(text)            True when `text` is made only of those sentences (what the no-prose test asks)

`tokens(text)` is lowercase `[a-z0-9]{3,}` minus a fixed stop-word list (`textutil`). A department's score is the number of words
the request shares with its name and purpose.
"""
import re
import string
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sutra_app.library.org_chart import OrgChart, OrgNode
from sutra_app.orchestrator.textutil import tokens
from sutra_app.orchestrator.waiting import age_words

__all__ = [
    "LINES", "STATUS_HEADER", "NO_TEAMS", "NONE_OF_THESE", "Candidate", "Fallback", "TaskLine", "line", "names_phrase",
    "matches_template", "candidates", "fallback_plan", "status_report", "MIN_SCORE",
]

MIN_SCORE = 2
STATUS_HEADER = "Here is where things stand."
NO_TEAMS = "There are no teams yet. Tell me what you need and I will set one up."
NONE_OF_THESE = "None of these"

# Every sentence Sutra says in the org chat (design 5.2). `{x}` are filled by code from names in the chart.
LINES: dict[str, str] = {
    "greeting": "Hello. Tell me what you need and I will give it to the right team.",          # ChartStore.bootstrap posts it (GREETING)
    "add": "I set up a {name} team and gave it your request.",
    "add_only": "I set up a {name} team.",
    "reuse": "I gave this to the {name} team.",
    "move": "I moved {x} under {y}.",
    "merge": "I merged {a} into {b}.",
    "split": "I split {a} into {a} and {b}.",
    "rename": "I renamed {a} to {b}.",
    "purpose": "I updated the purpose of {a}.",
    "none": "I could not tell which team should take this. Which fits best?",
    "smalltalk": "Tell me what you need and I will give it to the right team.",
    "choice": "Which team fits best?",
    "approve_merge": "Merge {a} into {b}? Their chats and history stay available.",
    "approve_split": "Split {a} into {a} and {b}? Their chats and history stay available.",
    "declined": "Okay, I left the chart as it was.",
    "already": "That was already decided.",
    "rejected": "I did not change anything: {reason}",
    "busy": "{reason}",
    "no_connector": "I can't reach Claude or Codex right now ({hint}). Nothing was changed.",
    "stale": "The chart changed while I was thinking. Please send that again.",
    "save_failed": "I could not save that. Nothing was changed.",
    "task_failed": "I could not start that work: {reason}",
    "failed": "Something went wrong on my side. Nothing was changed. Please try again.",
}
_SPECIAL = {"busy": r".+? is busy with .+?"}          # {reason} alone would match anything: the rules' sentence has this shape


def line(key: str, **values: str) -> str:
    """One Sutra sentence. A missing or an unknown value is a KeyError / ValueError, so a typo is found by the tests."""
    template = LINES[key]
    wanted = {field for _, field, _, _ in string.Formatter().parse(template) if field}
    if wanted != set(values):
        raise ValueError(f"line {key!r} takes {sorted(wanted)}, got {sorted(values)}")
    return template.format(**values)


def names_phrase(names: Sequence[str]) -> str:
    """`Web`, `Web and Sales`, `Web, Sales and Leads`."""
    items = [n for n in names if n]
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _pattern(key: str) -> str:
    if key in _SPECIAL:
        return _SPECIAL[key]
    parts = []
    for text, name, _, _ in string.Formatter().parse(LINES[key]):
        parts.append(re.escape(text))
        if name:
            parts.append(r".+?")
    return "".join(parts)


_ONE = "|".join(f"(?:{_pattern(key)})" for key in LINES)
_ALL = re.compile(rf"^(?:{_ONE})(?: (?:{_ONE}))*$", re.S)


def matches_template(text: str) -> bool:
    """True when `text` is one or more of the sentences in `LINES` (joined by single spaces), a status report, the no-team line, or a
    single word of a card option. This is what makes 'no model prose in the org chat' testable."""
    stripped = text.strip()
    if stripped.startswith(STATUS_HEADER) or stripped == NO_TEAMS:
        return True
    return _ALL.match(stripped) is not None


# ---- candidates and the keyword fallback ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    kind: str                  # department | division
    score: int = 0


@dataclass(frozen=True)
class Fallback:
    """`reuse` is set when the keywords settle it; otherwise `candidates` (at most 3, best first) go to a `choice` card."""

    reuse: Candidate | None
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TaskLine:
    dept_id: str
    title: str
    status: str
    since: int | None = None          # for a team waiting for the owner, when it asked (epoch seconds of its open question)


def _score(node: OrgNode, wanted: frozenset[str]) -> int:
    return len(wanted & tokens(f"{node.name} {node.purpose}"))


def candidates(chart: OrgChart, text: str, *, ids: Iterable[str] = (), limit: int = 3) -> list[Candidate]:
    """Up to `limit` teams to offer. The named `ids` come first (those the chart holds as a department or division, in the given
    order), then departments by word overlap with `text` (ties keep chart order)."""
    wanted = tokens(text)
    out: list[Candidate] = []
    for node_id in ids:
        node = chart.node(node_id)
        if node is not None and node.kind in ("department", "division") and all(c.id != node.id for c in out):
            out.append(Candidate(node.id, node.name, node.kind, _score(node, wanted)))
    departments = [n for n in chart.nodes if n.kind == "department" and all(c.id != n.id for c in out)]
    ranked = sorted(departments, key=lambda n: (-_score(n, wanted), chart.nodes.index(n)))
    out.extend(Candidate(n.id, n.name, n.kind, _score(n, wanted)) for n in ranked)
    return out[:limit]


def fallback_plan(text: str, chart: OrgChart) -> Fallback | None:
    """T5. None when the chart has no department at all. Else the best department when its score is at least 2 and above the
    runner-up's, otherwise the top 3 candidates for a `choice` card (F3)."""
    departments = [n for n in chart.nodes if n.kind == "department"]
    if not departments:
        return None
    top = candidates(chart, text, limit=3)
    best = top[0]
    runner_up = top[1].score if len(top) > 1 else -1
    if best.score >= MIN_SCORE and best.score > runner_up:
        return Fallback(reuse=best, candidates=tuple(top))
    return Fallback(reuse=None, candidates=tuple(top))


# ---- the status report --------------------------------------------------------------------------------------------------

_LIVE = {"starting": "starting {t}", "running": "working on {t}", "waiting_user": "waiting for you on {t}",
         "queued": "{t} is queued", "blocked": "{t} is waiting for another team"}
_LAST = {"done": "last finished {t}", "done_with_open_items": "finished {t} with open items", "stopped": "stopped {t}",
         "crashed": "{t} ran into trouble", "cancelled": "{t} was cancelled"}


def status_report(chart: OrgChart, tasks: Sequence[TaskLine], *, now: int | None = None) -> str:
    """The answer to 'where are things': one line per department, built from the chart and the tasks (oldest first). A team's
    line says what it is doing, else what it last finished, else that it has nothing yet. With `now`, a team waiting for the owner
    also says for how long ('waiting for you on "Menu" for 2 days'), from the time it asked."""
    departments = [n for n in chart.nodes if n.kind == "department"]
    if not departments:
        return NO_TEAMS
    rows = [STATUS_HEADER]
    for dept in departments:
        mine = [t for t in tasks if t.dept_id == dept.id]
        live = [t for t in mine if t.status in _LIVE]
        if live:
            current = next((t for t in live if t.status in ("starting", "running", "waiting_user")), live[0])
            text = _LIVE[current.status].format(t=f'"{current.title}"')
            if current.status == "waiting_user" and now is not None and current.since is not None and now - current.since >= 60:
                text += f" for {age_words(now - current.since)}"
        elif mine:
            text = _LAST.get(mine[-1].status, "last task {t}").format(t=f'"{mine[-1].title}"')
        else:
            text = "nothing yet"
        rows.append(f"- {dept.name}: {text}.")
    return "\n".join(rows)
