"""proto.py -- the J2 prototype, read at its pinned commit, for the j2ui tests (UI port, package j2ui-core, step C0).

The department's UI is the prototype's page, fed by an adapter built from Sutra's records. Every test that needs the
prototype itself (its page, its constants, a pure module) reads it here, and only here:

    PIN            the pinned commit: j2ui_assets/PINNED.json source.commit once the sync script wrote it, else the constant
    repo()         the prototype's checkout: env J2_PROTOTYPE, else PINNED.json source.path, else None (never a literal path)
    skip_reason()  why a test cannot read the prototype (no checkout, no git, no pinned commit), or None
    show(name)     the bytes of a file at the pinned commit, through `git show PIN:name`
    consts(n, s)   a module-level literal of a pinned .py file (ast.literal_eval; the file is never executed)
    load(name)     a pure pinned module (j2_schema, j2_board, ...) imported from a temp copy; never j2_map or j2_realization,
                   which import llm

The prototype's working tree is never read: it moves (20 commits in 6 days) and may be dirty, and a test that compared
against it would turn red on every commit there. A test that needs the prototype skips with `pytest.skip(skip_reason())`;
`show`, `consts` and `load` do that themselves when the prototype is not there.
"""
import ast
import functools
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

UI = Path(__file__).resolve().parents[2]
PINNED_JSON = UI / "j2ui_assets" / "PINNED.json"
FALLBACK_PIN = "f9ceba15192bbd6f62047cb7288d0f291b2fbc4f"
#: modules that import llm (or others that do) and so cannot be loaded without the model client
IMPURE = ("j2_map", "j2_realization", "j2", "j2_server", "llm", "studio", "server")


def _pinned():
    try:
        return json.loads(PINNED_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _pin():
    src = _pinned().get("source")
    commit = (src or {}).get("commit") if isinstance(src, dict) else None
    return str(commit) if commit else FALLBACK_PIN


PIN = _pin()


def repo():
    """The prototype's checkout: J2_PROTOTYPE, else the path the sync script recorded, else None."""
    env = os.environ.get("J2_PROTOTYPE", "").strip()
    if env:
        return Path(os.path.expanduser(env))
    src = _pinned().get("source")
    path = (src or {}).get("path") if isinstance(src, dict) else None
    return Path(os.path.expanduser(str(path))) if path else None


def _git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


@functools.lru_cache(maxsize=None)
def _reason(repo_path, pin):
    if repo_path is None:
        return "the J2 prototype is not here: set J2_PROTOTYPE to its checkout"
    p = Path(repo_path)
    if not p.is_dir():
        return "J2_PROTOTYPE %s is not a directory" % p
    try:
        probe = _git("--version")
    except OSError:
        return "git is not installed"
    if probe.returncode != 0:
        return "git does not run"
    # a folder inside some other repository is not the prototype: its own .git must be there
    if not (p / ".git").exists():
        return "%s is not a git checkout" % p
    if _git("-C", str(p), "cat-file", "-e", "%s^{commit}" % pin).returncode != 0:
        return "the pinned commit %s is not in %s" % (pin[:12], p)
    return None


def skip_reason():
    """Why the prototype cannot be read at the pinned commit, or None when it can."""
    r = repo()
    return _reason(str(r) if r is not None else None, PIN)


def _need():
    why = skip_reason()
    if why:
        import pytest
        print("j2ui tests: " + why)
        pytest.skip(why)
    return repo()


@functools.lru_cache(maxsize=None)
def _blob(repo_path, pin, name):
    got = _git("-C", repo_path, "show", "%s:%s" % (pin, name))
    if got.returncode != 0:
        raise FileNotFoundError("%s is not in %s at %s" % (name, repo_path, pin[:12]))
    return got.stdout


def show(name):
    """The bytes of `name` at the pinned commit (git show PIN:name); skips the test when the prototype is not here."""
    return _blob(str(_need()), PIN, str(name))


def consts(name, symbol):
    """The value of a module-level literal assignment `symbol = ...` in the pinned `name` (ast.literal_eval; never run)."""
    tree = ast.parse(show(name).decode("utf-8"), filename=name)
    found = None
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == symbol for t in targets) and getattr(node, "value", None) is not None:
            found = node.value
    if found is None:
        raise KeyError("%s has no module-level %s" % (name, symbol))
    return ast.literal_eval(found)


_LOADED = {}
_TMP = []


def load(name):
    """A pure pinned module (j2_schema.py, j2_board.py, j2_artifacts.py) imported from a temp copy of its pinned bytes."""
    mod = str(name)[:-3] if str(name).endswith(".py") else str(name)
    if mod in IMPURE:
        raise ValueError("%s imports the model client and is never loaded; read its constants with consts()" % mod)
    data = show(mod + ".py")
    key = (str(repo()), PIN, mod)
    if key not in _LOADED:
        tmp = tempfile.TemporaryDirectory(prefix="j2ui-proto-")
        _TMP.append(tmp)                      # lives as long as the process
        path = Path(tmp.name) / (mod + ".py")
        path.write_bytes(data)
        spec = importlib.util.spec_from_file_location("j2proto_" + mod, str(path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _LOADED[key] = module
    return _LOADED[key]
