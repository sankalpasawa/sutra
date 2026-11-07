"""The offline demo's reply book: the stub answers the chat agent's stages from the owner's message (D97, work package GAP-DEMO).

    demo_book()      a `DemoBook` for `connectors.factory.build_router(..., replybook=...)`; only `--offline` uses it

Every reply is computed from the prompt text of the call, which carries the owner's message (`OWNER REQUEST:`) and the chart digest
(`CHART ...:`), so the replies are deterministic and agree with each other:

    decide   a department of the digest that shares a keyword with the message (name or goal) is reused, else a team is added
    change   one `AddOp` under the root: a department named from the first 2 to 4 words of the message, its goal the message
    assign   one assignment: the goal is the message, the target the department the change added (or the reused one)
    retry    the chat agent asks the same stage again with the reasons appended, so the same reply comes back

Replies are built with the closed library models and dumped as JSON; nothing is invented. A `ReplyBook` reply takes no arguments, so
`DemoStub` (the stub the factory builds for this book, `connector_class`) puts the prompt of the current call in a ContextVar first.
"""
import contextvars
import re
from dataclasses import dataclass

from sutra_app.connectors.stub import ReplyBook, StubConnector
from sutra_app.library.org_chart import AddOp, ChartChangeRequest, NewNode
from sutra_app.library.types import clip
from sutra_app.orchestrator.agent.replies import AssignmentDraft, AssignmentPlan, ChatDecision
from sutra_app.orchestrator.textutil import STOP_WORDS, one_line_title

__all__ = ["DemoBook", "DemoStub", "demo_book", "FUNCTION", "topic_name"]

FUNCTION = "chat_agent"
PURPOSE_CHARS = 120                       # the digest shows this much of a department's goal
FILLER = frozenset({"team", "general"})   # words this module adds itself: they never count as a keyword
_PROMPT: contextvars.ContextVar[str] = contextvars.ContextVar("demo_prompt", default="")
_WORD = re.compile(r"[a-z0-9]{3,}")
# the message ends where the next block of the prompt starts: the owner-notes block (when there are notes) or the line after it
_MESSAGE = re.compile(r"OWNER REQUEST:\n(.*?)\n(?:OWNER NOTES \(|MODELS:|YOUR DECISION:|Write the assignments)", re.S)
_DIGEST = re.compile(r"CHART(?: AFTER THE CHANGE| \(revision \d+\)):\n(.*?)\n(?:CONVERSATION|MODELS:)", re.S)
_ROOT = re.compile(r"Root id: ([^\s]+?)\.(?:\s|$)")


@dataclass(frozen=True)
class _Dept:
    id: str
    name: str
    purpose: str


def _words(text: str) -> list[str]:
    """The meaningful words of `text` in the order they are written, each once."""
    return list(dict.fromkeys(w for w in _WORD.findall(text.lower()) if w not in STOP_WORDS))


def topic_name(message: str) -> str:
    """The name of a new team: the first 2 to 4 meaningful words of the message, capitalised ('A website for my cafe' ->
    'Website Cafe'). One word gets 'Team' after it, none gives 'General Team'."""
    words = _words(message)[:4]
    if len(words) < 2:
        words += ["team"] if words else ["general", "team"]
    return " ".join(word.capitalize() for word in words)


def _read(prompt: str) -> tuple[str, str, list[_Dept]]:
    """`(message, root id, departments)` of a chat agent prompt (decide, change or assign, with or without the retry text)."""
    asked = _MESSAGE.search(prompt)
    if asked is None:
        raise ValueError("the demo book answers the chat agent's prompts only: no OWNER REQUEST in this one")
    digest = _DIGEST.search(prompt)
    lines = digest.group(1).splitlines() if digest else []
    root = _ROOT.search(lines[0]) if lines else None
    depts = []
    for line in lines:
        parts = [p.strip() for p in line.split(" | ")]
        if line[:1] not in (" ", "") and len(parts) >= 3 and not line.startswith("Org chart"):
            depts.append(_Dept(parts[0], parts[1], parts[2]))
    return asked.group(1), root.group(1) if root else "root", depts


def _best(message: str, depts: list[_Dept]) -> tuple[_Dept | None, int]:
    """The department that shares most keywords with the message (a tie: the exact topic name, then the newest) and that count."""
    wanted = set(_words(message)) - FILLER
    topic = topic_name(message)
    scored = [(len(wanted & (set(_words(f"{d.name} {d.purpose}")) - FILLER)), d.name == topic, i, d) for i, d in enumerate(depts)]
    if not scored:
        return None, 0
    score, _, _, best = max(scored, key=lambda s: s[:3])
    return best, score


def _draft(message: str, dept_id: str) -> AssignmentDraft:
    text = " ".join(message.split())
    return AssignmentDraft(ref="a1", dept=dept_id, title=one_line_title(text, 60) or "Your request", brief=clip(text, 2000) or "Your request")


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def decide() -> dict:
    message, _, depts = _read(_PROMPT.get())
    team, score = _best(message, depts)
    if team is not None and score > 0:
        return _dump(ChatDecision(intent="new_task", change="reuse", reuse_nodes=[team.id], assignments=[_draft(message, team.id)],
                                  why=f"The request shares words with the {team.name} team."))
    return _dump(ChatDecision(intent="new_task", change="add", why="No team fits this request yet."))


def change() -> dict:
    message, root, _ = _read(_PROMPT.get())
    name = topic_name(message)
    node = NewNode(ref="$team", kind="department", name=name, purpose=clip(" ".join(message.split()), PURPOSE_CHARS), parent=root)
    return _dump(ChartChangeRequest(reason=f"No team fits this request, so I set up the {name} team.", ops=[AddOp(node=node)]))


def assign() -> dict:
    message, _, depts = _read(_PROMPT.get())
    team, _ = _best(message, depts)
    if team is None:
        raise ValueError("the demo book found no department to assign to")
    return _dump(AssignmentPlan(assignments=[_draft(message, team.id)]))


class DemoStub(StubConnector):
    """The plain stub, except that the prompt of the call being answered is visible to the book's replies."""

    def _resolve(self, plan, schema):
        token = _PROMPT.set(plan.prompt)
        try:
            return super()._resolve(plan, schema)
        finally:
            _PROMPT.reset(token)


class DemoBook(ReplyBook):
    """A `ReplyBook` that asks the factory for a `DemoStub`."""

    connector_class = DemoStub


def demo_book() -> DemoBook:
    """One entry per stage of the chat agent; the retry of a stage is that stage's call again, so it needs none of its own."""
    return DemoBook({(FUNCTION, "decide"): decide, (FUNCTION, "change"): change, (FUNCTION, "assign"): assign})
