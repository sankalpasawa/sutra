"""Chat message meta and the J2 chat line (library design section 10, S2-models-15, D47).

Two shapes had one name, `chat_message`. Now:

    run_message   (a payload, here)           J2's chat.jsonl line: `id t who text step calls board_read` and the meta
                                              keys at the top level. The engine process checks it on `post()` through
                                              `gate_record`, so it is defined here and the engine never imports the server.
    chat_message  (a record, the orchestrator) the stored server message; its `meta` object is a `MessageMeta`.

`MessageMeta` is the closed key set of J2's message meta with open values. J2 attaches meta by keyword at `post`, `_say`,
`_reply` and `_ask_user`; the keys below are what an AST scan of J2's j2.py (33aeeda, 2026-11-04) found, and they are the
design's list (section 10) plus the ones the scan found since: `forced_test`, `lesson_test`, `lesson_used`,
`lessons_offered`, `playbook_used`, `playbook_changes`, `playbooks_offered` and `board_read` (J2's `post` adds it to the
meta itself), and, from J2 1adb8ecd, `humans_only`, `run_template` and `content_door`. A key outside the set is refused, so a new J2 key is found by a test, not by a lost field. The values are
open: any JSON value, bounded in depth (J2 puts a bool, a number, a workflow id, a list or a whole proposal under one
key, and `change` is a flag on the Requester's line and a board id on another).

The canonical JSON of a `MessageMeta` leaves out the keys that are not set, so a stored message carries only its meta.
The first line of a chat.jsonl file is not a message: it is the run header `{"meta": true, "run": ...}` and is not a
`run_message`; it is a `RunHeader` (closed, J2 1adb8ecd adds `by`: who ran it, which the app fixes with `J2_RUN_BY`).
"""
import warnings
from typing import Annotated, Any, Final, Literal

from pydantic import AfterValidator, Field, JsonValue, StringConstraints, model_serializer

from .base import Value
from .registry import REGISTRY

__all__ = ["MetaValue", "MessageMeta", "RunMessage", "RunHeader", "ChatBlock", "BASE_KEYS", "META_KEYS", "HEADER_KEYS"]

_MAX_DEPTH: Final = 32
_MAX_TEXT: Final = 100_000          # a chat line: J2 shows a summary above 60,000 characters of chat (CHAT_FULL_CHARS)


def _bounded_json(value: Any) -> Any:
    """A meta value is any JSON value (pydantic's JsonValue: finite numbers, string keys), at most 32 levels deep. Walked
    with a stack, so a deep value cannot exhaust Python's own."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > _MAX_DEPTH:
            raise ValueError(f"a meta value may be nested at most {_MAX_DEPTH} levels deep")
        if isinstance(item, list):
            stack.extend((sub, depth + 1) for sub in item)
        elif isinstance(item, dict):
            stack.extend((sub, depth + 1) for sub in item.values())
    return value


MetaValue = Annotated[JsonValue, AfterValidator(_bounded_json)]


class ChatBlock(Value):
    """One typed block of a provider turn (absorb design 2.3): text, thinking, a tool call or its result. The set of types is closed.
    `kind` says what a tool call was (for the fold); a cut text says it was cut (`truncated`)."""

    type: Literal["text", "thinking", "tool_use", "tool_result"]
    kind: Literal["read", "edit", "run", "search", "web", "other"] = "other"
    name: Annotated[str, StringConstraints(max_length=200)] = ""
    text: Annotated[str, StringConstraints(max_length=_MAX_TEXT)] = ""
    truncated: bool = False
    is_error: bool = False


# A field called `register` shadows `ABCMeta.register` (every pydantic class has that metaclass). pydantic warns once, for
# the class that declares the field, and it takes the metaclass method for the DEFAULT of the inherited field in a
# subclass: RunMessage().register would be a bound method. So the warning is silenced here, where it is understood,
# and RunMessage declares `register` again (below), which makes pydantic read its own default.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=r'Field name "register" ', category=UserWarning)
    class MessageMeta(Value):
        """The meta keys of a J2 chat message. Every key is optional and holds any JSON value; no other key is allowed."""

        # who the message is for, and where it goes next
        next: MetaValue = None
        audience: MetaValue = None
        to_user: MetaValue = None
        requester_only: MetaValue = None
        relay: MetaValue = None
        redirect: MetaValue = None
        shaped: MetaValue = None
        auto: MetaValue = None
        auto_label: MetaValue = None
        to: MetaValue = None
        handoff: MetaValue = None
        # the questions to the Requester (Identity's pauses) and the owner's override
        act: MetaValue = None
        pause: MetaValue = None
        options_only: MetaValue = None
        gaps: MetaValue = None
        gaps_title: MetaValue = None
        override: MetaValue = None
        # what was decided
        decision: MetaValue = None
        accept: MetaValue = None
        agree: MetaValue = None
        keep: MetaValue = None
        done: MetaValue = None
        change: MetaValue = None
        stamp: MetaValue = None
        rejected: MetaValue = None
        workable: MetaValue = None
        warning: MetaValue = None
        test: MetaValue = None
        # workflows, their cost, their checks and the conflicts between agents
        workflow: MetaValue = None
        section: MetaValue = None
        version: MetaValue = None
        attempt: MetaValue = None
        cycle: MetaValue = None
        exchange: MetaValue = None
        conflict: MetaValue = None
        register: MetaValue = None
        schedule: MetaValue = None
        envelope: MetaValue = None
        workflow_cost: MetaValue = None
        charged: MetaValue = None
        proposal: MetaValue = None
        checks: MetaValue = None
        atom: MetaValue = None
        audit: MetaValue = None
        mechanical: MetaValue = None
        # the documents, the realization plan and the template routing
        artifact: MetaValue = None
        human_output: MetaValue = None
        realization: MetaValue = None
        judge: MetaValue = None
        template_route: MetaValue = None
        # the message board (a reader of a changed document and who it affects)
        reader: MetaValue = None
        affected: MetaValue = None
        board_read: MetaValue = None
        # memory: the lessons and playbooks Adaptation was offered and used
        lessons: MetaValue = None
        lessons_offered: MetaValue = None
        lesson_used: MetaValue = None
        lesson_test: MetaValue = None
        playbook: MetaValue = None
        playbooks_offered: MetaValue = None
        playbook_used: MetaValue = None
        playbook_changes: MetaValue = None
        # the test switch J2_FORCE_AUDIT_FAIL: the item number it forced
        forced_test: MetaValue = None
        # run templates, auto-reuse and the content door (J2 1adb8ecd): a line only the humans read, the run template a line
        # is about ({id, selected, of}) and the content door's decision for one section ({workflow, door, rule, section})
        humans_only: MetaValue = None
        run_template: MetaValue = None
        content_door: MetaValue = None

        @model_serializer(mode="wrap")
        def _only_what_is_set(self, handler: Any) -> dict[str, Any]:
            """Leave out the meta keys that hold nothing: 60 nulls on every stored message would say nothing."""
            return {key: value for key, value in handler(self).items() if value is not None}

    class RunMessage(MessageMeta):
        """One line of J2's chat.jsonl (the message dict of `J2Run.post`, J2:3008): the base keys, then the meta keys at the
        top level. `step` is J2's step number (0 to 8), `calls` the ids of the AI calls behind the message (calls.jsonl),
        `board_read` the board ids the author had just read."""

        id: Annotated[int, Field(ge=1)]
        t: Annotated[str, StringConstraints(pattern=r"^[0-9]{2}:[0-9]{2}:[0-9]{2}$")]          # J2's strftime("%H:%M:%S")
        who: Annotated[str, StringConstraints(min_length=1, max_length=60)]
        text: Annotated[str, StringConstraints(max_length=_MAX_TEXT)]
        step: Annotated[int, Field(ge=0, le=99)] | None = None
        calls: Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=200)] = []
        board_read: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=40)]], Field(max_length=100)] = []
        register: MetaValue = None          # declared again on purpose: see the note above this block


class RunHeader(Value):
    """The first line of chat.jsonl (J2 `post`, message 1): which mode and model produced the run, and since J2 1adb8ecd who ran
    it (`by`, J2 `run_author()`: `J2_RUN_BY`, else the git or system user name). Closed; every key but `meta` and `run` is
    optional so a run of an older J2 reads. `by` is a name, never a path."""

    meta: Literal[True]
    run: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    output: MetaValue = None
    j2_fixes: MetaValue = None
    force_audit_fail: MetaValue = None
    force_question: MetaValue = None
    test_lessons: MetaValue = None
    realization: MetaValue = None
    provider: MetaValue = None
    model: MetaValue = None
    mock: bool | None = None
    by: Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[^/\\\x00-\x1f]+$")] | None = None


REGISTRY.register_payload("run_message", 1, RunMessage)
REGISTRY.register_payload("run_header", 1, RunHeader)

BASE_KEYS: Final = ("id", "t", "who", "text", "step", "calls", "board_read")
META_KEYS: Final = tuple(MessageMeta.model_fields)
HEADER_KEYS: Final = tuple(RunHeader.model_fields)
