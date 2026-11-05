"""One JSON extractor (S1-contracts-18, S2-models-12): the library owns `extract_json` and `close_json`; the engine and the connectors
re-export the same objects, and nothing else in the app defines a second copy."""
import ast
import json
from pathlib import Path

import pytest

from sutra_app.connectors import jsonio
from sutra_app.engine import llm
from sutra_app.library import replies

APP = Path(replies.__file__).resolve().parents[1]
NAMES = ("extract_json", "close_json")
REPLIES = {
    "plain": ('{"a": 1}', {"a": 1}),
    "fenced": ('Here you go:\n```json\n{"a": [1, 2], "b": "x"}\n```\nDone.', {"a": [1, 2], "b": "x"}),
    "prose around": ('Sure! {"ok": true, "n": 3} Hope that helps.', {"ok": True, "n": 3}),
    "cut off": ('{"a": "text that stops', {"a": "text that stops"}),
    "cut off in a list": ('{"items": [1, 2, {"k": "v"', {"items": [1, 2, {"k": "v"}]}),
}


@pytest.mark.parametrize("name", NAMES)
def test_the_three_names_are_the_same_object(name):
    assert getattr(llm, name) is getattr(replies, name) is getattr(jsonio, name)


@pytest.mark.parametrize("name", NAMES)
def test_the_function_lives_in_the_library(name):
    assert Path(getattr(replies, name).__code__.co_filename).resolve() == Path(replies.__file__).resolve()


def test_no_other_module_of_the_app_defines_an_extractor():
    """An AST walk over every module: a `def extract_json`/`close_json` (or a private twin) anywhere but the library is a second copy."""
    twins = {name: [] for name in NAMES}
    for path in sorted(APP.rglob("*.py")):
        if "seed" in path.parts or path == Path(replies.__file__).resolve():
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.lstrip("_") in NAMES:
                twins[node.name.lstrip("_")].append(f"{path.relative_to(APP)}:{node.lineno}")
    assert twins == {name: [] for name in NAMES}


def test_the_j2_engine_modules_call_the_shared_function_through_llm():
    """j2.py calls `llm.extract_json(...)`: neither it nor the realization module may bind a name of its own."""
    from sutra_app.engine import j2, j2_change, j2_realization
    for module in (j2, j2_change, j2_realization):
        assert not any(hasattr(module, name) for name in NAMES), module.__name__
        assert module.llm is llm


@pytest.mark.parametrize("case", sorted(REPLIES))
def test_every_door_reads_a_reply_the_same_way(case):
    text, want = REPLIES[case]
    assert llm.extract_json(text) == replies.extract_json(text) == jsonio.extract_json(text) == want
    assert jsonio.parse_reply(text) == want
    assert replies.ReplyParser._object_from(text) == want                           # the library's parser reads it the same way


def test_a_reply_that_holds_no_object_fails_the_same_way_everywhere():
    for door in (llm.extract_json, replies.extract_json, jsonio.extract_json):
        with pytest.raises(ValueError):
            door("no json here at all")
    with pytest.raises(jsonio.InvalidJsonError):
        jsonio.parse_reply("no json here at all")


def test_close_json_closes_what_a_cut_off_reply_left_open():
    closed = replies.close_json('{"a": [1, 2')
    assert json.loads(closed) == {"a": [1, 2]}
    assert llm.close_json('{"a": [1, 2') == closed == jsonio.close_json('{"a": [1, 2')
