"""Chat message meta and the J2 chat line (library design section 10, S2-models-15): `MessageMeta`, the closed key set
with open values, and `RunMessage`, the payload "run_message".

The lines are J2's own, from the chat.jsonl that J2 33aeeda wrote in mock mode."""
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.library import chat as chat_module
from sutra_app.library.base import Record, aliased_fields, unbounded_fields
from sutra_app.library.chat import BASE_KEYS, META_KEYS, MessageMeta, RunMessage
from sutra_app.library.gate import GATE, Gate, GateError
from sutra_app.library.registry import REGISTRY, ModelRegistry

# the keys of library.md section 10 (the AST scan of 2026-11-04), as written there
SECTION_10 = set("""warning to_user change next done test redirect relay requester_only audience rejected checks mechanical override act
pause shaped reader affected agree keep template_route realization handoff gaps conflict auto gaps_title to options_only decision
artifact workflow proposal accept envelope version attempt register schedule human_output section workflow_cost stamp charged cycle
exchange atom audit workable playbook lessons""".split())
# found by the same scan of j2.py 33aeeda (keyword arguments of post, _say, _reply and _ask_user) after the design was written
SCAN_ADDED = {"forced_test", "lesson_test", "lesson_used", "lessons_offered", "playbook_used", "playbook_changes", "playbooks_offered",
              "board_read"}
# found by the scan of the vendored j2.py of J2 sync 4: the late judge's system lines say whose judgement they report (`judge`, D145),
# and the answer Decide for me gives in the Requester's name is flagged `auto` and carries a plain label (`auto_label`)
SYNC4_ADDED = {"judge", "auto_label"}

USER_LINE = {"id": 1, "t": "12:48:35", "who": "user", "step": 0,
             "text": "A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru."}
IDENTITY_LINE = {"id": 2, "t": "12:48:35", "who": "identity", "text": "@Requester Thanks, I have everything I need.", "step": 1,
                 "to_user": True, "requester_only": True, "audience": "user", "calls": [1]}
VALIDATOR_LINE = {"id": 4, "t": "12:48:35", "who": "validator", "step": 1, "stamp": True, "next": "adaptation",
                  "text": "@Adaptation Charter valid: statement present, 7 checkable done-when items. Work can start."}
PROPOSAL_LINE = {"id": 5, "t": "12:48:36", "who": "adaptation", "step": 2, "next": "priority", "text": "@Priority Proposal for cycle 1.",
                 "proposal": [{"id": "P-1", "name": "Scaffold", "outputs": ["#hero"], "envelope": {"money_limit": 10, "retry_limit": 1}}]}
BOARD_LINE = {"id": 9, "t": "12:49:01", "who": "W-3", "step": 6, "workflow": "W-3", "section": "W-3", "version": 4, "workflow_cost": 12,
              "human_output": "I wrote the Goals section.", "calls": [4, 5], "board_read": ["Q-1"], "text": "@Coordination I wrote the Goals section. [read Q-1]"}
JUDGE_LINE = {"id": 12, "t": "12:49:30", "who": "system", "step": 6, "judge": "W-9",          # what J2's `_late_judge` posts (sync 4, D145)
              "text": "Judge: W-9 scored 0.91, at or above the 0.80 gate; zone certain, stage build."}
AUTO_LINE = {"id": 13, "t": "12:49:40", "who": "user", "text": "Option 1", "auto": True, "auto_label": "Go with sensible choices"}
LINES = [USER_LINE, IDENTITY_LINE, VALIDATOR_LINE, PROPOSAL_LINE, BOARD_LINE, JUDGE_LINE, AUTO_LINE]
OPEN_VALUES = [True, False, 0, 3, 1.5, "", "grant", None, [], [1, "a", None], {}, {"a": {"b": [1, 2.5, "c", None]}}]


def problems(cls, data) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        cls.model_validate(data)
    return [(".".join(str(p) for p in e["loc"]), e["type"]) for e in error.value.errors()]


def deep(levels: int):
    value: object = "leaf"
    for _ in range(levels - 1):
        value = [value]
    return value


# ---- MessageMeta --------------------------------------------------------------------------------------------------

def test_the_key_set_is_the_design_list_plus_what_the_scan_of_j2_found_since():
    assert set(META_KEYS) == SECTION_10 | SCAN_ADDED | SYNC4_ADDED
    assert len(META_KEYS) == len(set(META_KEYS)) == 62
    assert set(MessageMeta.model_fields) == set(META_KEYS)


def test_the_late_judge_meta_key_is_known_takes_a_workflow_name_and_stays_in_the_stored_line():
    """D145: a chat line that J2's late judge posts says which workflow it judged (`judge="W-9"`); strict mode must accept it."""
    assert "judge" in META_KEYS and "judge" not in BASE_KEYS
    assert MessageMeta(judge="W-9").canonical_json() == '{"judge":"W-9"}'
    line = RunMessage.model_validate(JUDGE_LINE)
    assert line.judge == "W-9" and line.who == "system"
    checked = GATE.check("run_message", JUDGE_LINE)
    assert checked.model.judge == "W-9"
    assert '"judge":"W-9"' in checked.model.canonical_json()
    assert RunMessage.model_validate({k: v for k, v in JUDGE_LINE.items() if k != "judge"}).judge is None
    for value in ("W-9", "Revise W-6 Board (change 1)", None, 0):          # J2 writes the workflow's name; the key takes any JSON value like the others
        assert MessageMeta(judge=value).judge == value


def test_decide_for_mes_answer_is_flagged_auto_and_keeps_its_plain_label():
    """The answer J2 posts as the Requester's when Decide for me is on: `auto=True` and `auto_label` (what the Simple view shows)."""
    line = RunMessage.model_validate(AUTO_LINE)
    assert (line.who, line.auto, line.auto_label) == ("user", True, "Go with sensible choices")
    assert GATE.check("run_message", AUTO_LINE).model.auto_label == "Go with sensible choices"
    assert MessageMeta(auto=True, auto_label="Yes, go ahead").canonical_json() == '{"auto":true,"auto_label":"Yes, go ahead"}'
    assert RunMessage.model_validate({k: v for k, v in AUTO_LINE.items() if k != "auto_label"}).auto_label is None


def test_every_key_takes_any_json_value():
    for key in META_KEYS:
        for value in OPEN_VALUES:
            assert getattr(MessageMeta.model_validate({key: value}), key) == value, (key, value)


def test_a_key_outside_the_set_is_refused():
    assert problems(MessageMeta, {"colour": "red"}) == [("colour", "extra_forbidden")]
    for old in ("j", "check", "ok", "playbook_ids"):            # keys of earlier J2 versions, and a near miss
        assert problems(MessageMeta, {old: 1}) == [(old, "extra_forbidden")]
    assert problems(MessageMeta, {"act": "GRANT", "colour": 1, "shade": 2}) == [("colour", "extra_forbidden"), ("shade", "extra_forbidden")]


def test_a_meta_value_is_bounded_in_depth_and_must_be_json():
    assert MessageMeta(proposal=deep(32)).proposal is not None
    assert problems(MessageMeta, {"proposal": deep(33)}) == [("proposal", "value_error")]
    assert problems(MessageMeta, {"proposal": {"a": {"b": deep(32)}}}) == [("proposal", "value_error")]
    assert problems(MessageMeta, {"charged": math.inf}) == [("charged.float", "finite_number")]
    assert problems(MessageMeta, {"charged": [float("nan")]}) == [("charged.list.0.float", "finite_number")]
    assert problems(MessageMeta, {"charged": object()}) == [("charged", "invalid-json-value")]
    assert problems(MessageMeta, {"charged": (1, 2)}) == [("charged", "invalid-json-value")]          # a tuple is not JSON
    assert problems(MessageMeta, {"charged": {1: 2}}) == [("charged.dict.1.[key]", "string_type")]
    with pytest.raises(GateError):                                                                    # NaN in JSON text
        GATE.check("run_message", '{"id":1,"t":"10:00:00","who":"user","text":"x","charged":NaN}')


def test_the_canonical_json_leaves_out_the_keys_that_are_not_set():
    assert MessageMeta().canonical_json() == "{}"
    meta = MessageMeta(act="GRANT", to_user=True, charged=0, human_output="", lessons=[], next=None)
    assert meta.canonical_json() == '{"act":"GRANT","charged":0,"human_output":"","lessons":[],"to_user":true}'
    assert meta.model_dump(mode="json") == {"act": "GRANT", "to_user": True, "charged": 0, "human_output": "", "lessons": []}


def test_meta_is_frozen_and_changes_only_through_evolve():
    meta = MessageMeta(act="GRANT")
    assert meta.evolve(next="audit", act=None).canonical_json() == '{"next":"audit"}' and meta.act == "GRANT"
    assert MessageMeta.model_validate_json(meta.model_dump_json()) == meta
    with pytest.raises(ValidationError):
        meta.act = "COUNTER"
    with pytest.raises(ValidationError):
        meta.evolve(colour=1)


def test_a_record_that_holds_meta_stores_it_compactly():
    """The orchestrator's chat_message does this: a Record with a `meta` field of this class, through the gate."""
    from typing import Literal

    class Stored(Record):
        FAMILY = "stored_message"
        kind: Literal["stored_message"] = "stored_message"
        meta: MessageMeta = MessageMeta()

    registry = ModelRegistry()
    registry.register(Stored)
    checked = Gate(registry).check("stored_message", {"kind": "stored_message", "meta": {"act": "GRANT", "to_user": True}})
    assert checked.json == '{"kind":"stored_message","meta":{"act":"GRANT","to_user":true},"schema_version":1}'
    assert Gate(registry).check("stored_message", {"kind": "stored_message"}).json == '{"kind":"stored_message","meta":{},"schema_version":1}'
    with pytest.raises(GateError):
        Gate(registry).check("stored_message", {"kind": "stored_message", "meta": {"colour": 1}})


def test_a_field_called_register_works_in_both_classes():
    """`register` is also a method of every pydantic class (ABCMeta.register): the field must not turn into it."""
    assert MessageMeta().register is None and MessageMeta(register=True).register is True
    line = RunMessage(**USER_LINE)
    assert line.register is None
    assert RunMessage(**USER_LINE, register=False).register is False
    assert "register" not in line.model_dump() and RunMessage(**USER_LINE, register=True).model_dump()["register"] is True


def test_importing_the_module_raises_no_warning():
    root = Path(chat_module.__file__).resolve().parents[2]
    run = subprocess.run([sys.executable, "-W", "error", "-c", "import sutra_app.library.chat as c; c.RunMessage.model_json_schema()"],
                         capture_output=True, text=True, cwd=str(root), env={**os.environ, "PYTHONPATH": str(root)})
    assert run.returncode == 0, run.stderr


# ---- RunMessage: one line of chat.jsonl ----------------------------------------------------------------------------

@pytest.mark.parametrize("line", LINES, ids=[f"{ln['who']}-{ln['id']}" for ln in LINES])
def test_a_line_of_j2_passes_the_gate(line):
    checked = GATE.check("run_message", line)
    assert isinstance(checked.model, RunMessage) and (checked.family, checked.kind) == ("run_message", "run_message")
    assert checked.model.id == line["id"] and checked.model.text == line["text"]


def test_the_base_keys_and_the_meta_keys_sit_at_the_top_level():
    line = RunMessage.model_validate(BOARD_LINE)
    assert (line.step, line.calls, line.board_read, line.workflow, line.workflow_cost, line.who) == (6, [4, 5], ["Q-1"], "W-3", 12, "W-3")
    assert set(RunMessage.model_fields) == set(BASE_KEYS) | set(META_KEYS)
    assert BASE_KEYS == ("id", "t", "who", "text", "step", "calls", "board_read")


def test_a_line_needs_its_id_time_author_and_text():
    for key in ("id", "t", "who", "text"):
        assert problems(RunMessage, {k: v for k, v in USER_LINE.items() if k != key}) == [(key, "missing")]
    bare = RunMessage.model_validate({k: v for k, v in USER_LINE.items() if k != "step"})
    assert (bare.step, bare.calls, bare.board_read) == (None, [], [])


@pytest.mark.parametrize("change, expected", [
    ({"id": 0}, [("id", "greater_than_equal")]), ({"id": "1"}, [("id", "int_type")]), ({"id": 1.5}, [("id", "int_type")]),
    ({"t": "12:48"}, [("t", "string_pattern_mismatch")]), ({"t": "2026-11-04T12:48:35"}, [("t", "string_pattern_mismatch")]),
    ({"t": "ab:cd:ef"}, [("t", "string_pattern_mismatch")]),
    ({"who": ""}, [("who", "string_too_short")]), ({"who": "w" * 61}, [("who", "string_too_long")]),
    ({"text": "t" * 100_001}, [("text", "string_too_long")]), ({"text": None}, [("text", "string_type")]),
    ({"step": 100}, [("step", "less_than_equal")]), ({"step": -1}, [("step", "greater_than_equal")]), ({"step": "3"}, [("step", "int_type")]),
    ({"calls": ["1"]}, [("calls.0", "int_type")]), ({"calls": [0]}, [("calls.0", "greater_than_equal")]),
    ({"calls": list(range(1, 202))}, [("calls", "too_long")]),
    ({"board_read": [1]}, [("board_read.0", "string_type")]), ({"board_read": ["Q-" + "1" * 40]}, [("board_read.0", "string_too_long")]),
    ({"colour": "red"}, [("colour", "extra_forbidden")]),
])
def test_a_line_refuses(change, expected):
    assert problems(RunMessage, {**USER_LINE, **change}) == expected


def test_a_line_may_be_long_and_may_be_empty():
    assert RunMessage.model_validate({**USER_LINE, "text": "t" * 100_000}).text == "t" * 100_000
    assert RunMessage.model_validate({**USER_LINE, "text": ""}).text == ""
    assert RunMessage.model_validate({**USER_LINE, "step": 0}).step == 0 and RunMessage.model_validate({**USER_LINE, "step": 99}).step == 99
    assert RunMessage.model_validate({**USER_LINE, "step": None}).step is None


def test_the_run_header_that_opens_every_chat_jsonl_is_not_a_message():
    header = {"meta": True, "run": "20261104-124835", "output": "website", "j2_fixes": 1, "force_audit_fail": None, "mock": True}
    with pytest.raises(GateError) as error:
        GATE.check("run_message", header)
    assert {v.code for v in error.value.violations} == {"missing", "extra_forbidden"}


def test_the_canonical_form_of_a_line_leaves_out_unset_meta_and_ignores_key_order():
    checked = GATE.check("run_message", IDENTITY_LINE)
    assert '"proposal"' not in checked.json and '"next"' not in checked.json
    assert checked.json == ('{"audience":"user","board_read":[],"calls":[1],"id":2,"requester_only":true,"step":1,'
                            '"t":"12:48:35","text":"@Requester Thanks, I have everything I need.","to_user":true,"who":"identity"}')
    assert GATE.check("run_message", dict(reversed(list(IDENTITY_LINE.items())))).sha256 == checked.sha256


def test_run_message_is_a_payload_of_version_one():
    assert REGISTRY.is_payload("run_message") and REGISTRY.versions("run_message") == [1]
    assert REGISTRY.kinds("run_message") == {"run_message": RunMessage}
    with pytest.raises(GateError) as error:
        GATE.check("run_message", {**USER_LINE, "text": "t" * 1_100_000})
    assert error.value.stage == "size"


def test_both_classes_are_bounded_and_alias_nothing():
    assert unbounded_fields(MessageMeta) == [] and aliased_fields(MessageMeta) == []
    assert unbounded_fields(RunMessage) == [] and aliased_fields(RunMessage) == []


def test_the_module_lists_what_it_exports():
    assert all(hasattr(chat_module, name) for name in chat_module.__all__)
