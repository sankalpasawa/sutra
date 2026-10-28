"""The streaming guards (PRD amendment A4.7.2: STR-1, STR-2, STR-4), as tests over the source.

A stream producer builds nothing and validates nothing per frame; a streaming route has no `response_model`. Each guard passes on the
source as it is and FAILS on a planted violation (a test inserts one into a parsed copy and asks the same checker). The list of
guarded functions is itself asserted to exist, so a renamed function fails here instead of slipping out of the guard.

The guard names modules and pydantic's entry points, not common verbs: a bare `check` or `load` in an unrelated call is not a
violation (ws_chat has many helpers); `load` is one only when taken from `store`."""
import ast
import copy
import functools
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent

#: (file, qualified name) of every stream producer. The spec's `Runtime` is `SessionRuntime` in the code.
GUARDED = [
    ("app.py", "api_sessions_stream"),
    ("app.py", "sse"),
    ("app.py", "ws_chat"),
    ("session_runtime.py", "SessionRuntime._demux_turn_inner"),
    ("session_runtime.py", "SessionRuntime.demux_turn"),
    ("codex_runtime.py", "CodexRuntime.prompt_turn"),
    ("acp_runtime.py", "AcpRuntime.prompt_turn"),
]
#: names a stream body may never take an attribute from (the interface, its models, and what reads them)
FORBIDDEN_BASES = {"S", "layer_schema", "layer_models", "models_bus", "bus", "frames", "stream", "registry"}
#: the one allowed: a read of an integer, in the sessions stream
ALLOWED = {("api_sessions_stream", "models_bus", "revision")}
#: calls that build or run a validator, by the name taken
BUILD_CALLS = {"TypeAdapter", "create_model", "model_json_schema", "json_schema", "compile_all"}
VALIDATE_CALLS = {"model_validate", "model_validate_json", "validate_python", "validate_json"}


@functools.lru_cache(maxsize=None)
def _parsed(name):
    return ast.parse((HERE / name).read_text(encoding="utf-8"))


def _tree(name):
    """A fresh copy to plant into is made by _planted; a reader may share the cached one."""
    return _parsed(name)


def _names_streaming(n):
    return any(isinstance(x, ast.Name) and x.id == "StreamingResponse" for x in ast.walk(n))


def _find(tree, qual):
    """The function node for 'name' or 'Class.name' (module level or one class deep)."""
    parts = qual.split(".")
    scope = tree.body
    node = None
    for p in parts:
        node = next((n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == p), None)
        if node is None:
            return None
        scope = node.body
    return node


def _base(node):
    """The left-most name of an attribute chain: S in S.validate(...)."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def violations(fn, short, kinds=("build", "validate")):
    """What a stream producer's body takes that it may not, nested functions included: [(kind, text)]."""
    out = []
    for n in ast.walk(fn):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] + ([n.module] if isinstance(n, ast.ImportFrom) and n.module else [])
            if any(m.split(".")[0] in ("layer_schema", "layer_models") for m in mods):
                out.append(("validate", "imports %s" % ", ".join(mods)))
        elif isinstance(n, ast.Attribute):
            base = _base(n)
            if base in FORBIDDEN_BASES and (short, base, n.attr) not in ALLOWED:
                out.append(("validate", "%s.%s" % (base, n.attr)))
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in BUILD_CALLS:
                out.append(("build", name))
            elif name in VALIDATE_CALLS:
                out.append(("validate", name))
            elif name == "load" and isinstance(f, ast.Attribute) and _base(f) == "store":
                out.append(("build", "store.load"))
    return [v for v in out if v[0] in kinds]


def _guarded_nodes(trees=None):
    trees = trees or {}
    out = []
    for fname, qual in GUARDED:
        tree = trees.get(fname) or _tree(fname)
        node = _find(tree, qual)
        out.append((fname, qual, node))
    return out


# ---------------------------------------------------------------------------------------------------------------------- the list
def test_every_guarded_function_exists():
    for fname, qual, node in _guarded_nodes():
        assert node is not None, "%s: %s is gone or renamed; update the guard's list, do not let it slip out" % (fname, qual)
    app = _find(_tree("app.py"), "api_sessions_stream")
    assert any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "gen" for n in ast.walk(app)), \
        "api_sessions_stream has no nested gen"
    sse = _find(_tree("app.py"), "sse")
    assert any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "gen" for n in ast.walk(sse)), "sse has no gen"


# ----------------------------------------------------------------------------------------------------------------- STR-1 and STR-2
def test_str1_no_build_in_a_stream_body():
    for fname, qual, node in _guarded_nodes():
        assert violations(node, qual.split(".")[-1], kinds=("build",)) == [], "%s %s builds in a stream body" % (fname, qual)


def test_str2_no_validation_in_the_existing_stream_bodies():
    for fname, qual, node in _guarded_nodes():
        assert violations(node, qual.split(".")[-1], kinds=("validate",)) == [], "%s %s validates in a stream body" % (fname, qual)


def _planted(fname, qual, stmt, into=None):
    """The parsed source of `fname` with `stmt` appended to the body of `qual` (or of its nested `into`)."""
    tree = copy.deepcopy(_tree(fname))
    fn = _find(tree, qual)
    target = fn
    if into:
        target = next(n for n in ast.walk(fn) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == into)
    target.body.insert(0, ast.parse(stmt).body[0])
    ast.fix_missing_locations(tree)
    return tree, _find(tree, qual)


@pytest.mark.parametrize("stmt", ["TypeAdapter(int)", "pydantic.create_model('X')", "A.model_json_schema()", "store.load('x')",
                                  "compile_all()"])
def test_str1_names_a_planted_build_in_gen(stmt):
    _, fn = _planted("app.py", "api_sessions_stream", stmt, into="gen")
    assert violations(fn, "api_sessions_stream", kinds=("build",)), stmt


@pytest.mark.parametrize("stmt", ["S.validate('x', {})", "layer_schema.check({})", "layer_models.frames.Token()",
                                  "ad.validate_python({})", "M.model_validate_json('{}')"])
def test_str2_names_a_planted_validation_in_demux_turn_inner(stmt):
    _, fn = _planted("session_runtime.py", "SessionRuntime._demux_turn_inner", stmt)
    assert violations(fn, "_demux_turn_inner", kinds=("validate",)), stmt


def test_str2_names_a_planted_import_and_a_second_bus_name():
    _, fn = _planted("app.py", "ws_chat", "from layer_models import frames")
    assert violations(fn, "ws_chat")
    _, fn = _planted("app.py", "api_sessions_stream", "models_bus.changed_since(0)", into="gen")
    assert violations(fn, "api_sessions_stream"), "only models_bus.revision is allowed in the sessions stream"
    _, fn = _planted("app.py", "sse", "models_bus.revision()", into="gen")
    assert violations(fn, "sse"), "the allowance is for the sessions stream alone"


def test_a_bare_name_in_an_unrelated_call_is_not_a_violation():
    fn = ast.parse("async def f():\n    check(1)\n    load(2)\n    x.check()\n    json.loads('{}')\n").body[0]
    assert violations(fn, "f") == []


# --------------------------------------------------------------------------------------------------------------------------- STR-4
def _route_modules():
    """app.py and the module of every router app.py includes."""
    tree = _tree("app.py")
    mods = ["app.py"]
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "include_router" and n.args:
            a = n.args[0]
            if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and (HERE / (a.value.id + ".py")).exists():
                mods.append(a.value.id + ".py")
    return sorted(set(mods))


ROUTE_VERBS = {"get", "post", "put", "delete", "patch", "options", "head", "api_route"}


def streaming_routes_with_response_model(tree):
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _names_streaming(n):
            continue
        for d in n.decorator_list:
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_VERBS \
                    and any(k.arg == "response_model" for k in d.keywords):
                bad.append(n.name)
    return bad


def test_str4_no_response_model_on_a_streaming_route():
    mods = _route_modules()
    assert "app.py" in mods and len(mods) > 3, "the routers were not found: %s" % mods
    for m in mods:
        assert streaming_routes_with_response_model(_tree(m)) == [], m
    names = {n.name for n in ast.walk(_tree("app.py")) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _names_streaming(n)}
    assert {"api_sessions_stream", "sse"} <= names, "the guard must see both streaming routes: %s" % sorted(names)


def test_str4_names_a_planted_response_model():
    src = (HERE / "app.py").read_text(encoding="utf-8")
    planted = src.replace('@app.get("/sse/{source}")', '@app.get("/sse/{source}", response_model=dict)', 1)
    assert planted != src
    assert streaming_routes_with_response_model(ast.parse(planted)) == ["sse"]
