"""test_function_templates.py -- the function templates repository (sutra-ui/function-templates).

Every department has five functions; a template brings one to life. Each function has a
Default, and use-case templates derive from it narrowing-only: a derived floor carries every
line of its parent's floor word for word, and may add lines. This file is the law for that
folder: shape, ids, the narrowing-only rule, the chat brief's placeholders and cap, and the
screen words (no founder-only ids, no refs, never the record word the screen does not say).

Reads files only; touches no registry.
"""
import json
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "function-templates")
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
KEYS = {"id", "function", "name", "version", "derives_from", "use_case", "floor", "choices",
        "reads", "may_propose", "schedule", "checks", "chat_brief"}
LIST_KEYS = ("floor", "choices", "reads", "may_propose", "checks")
PLACEHOLDERS = ("{department}", "{goal}", "{done}", "{rules}", "{owner}", "{folder}")
BRIEF_MAX = 3000
FORBIDDEN_WORD = re.compile(r"\bcharters?\b", re.I)
FORBIDDEN_ID = re.compile(r"\b(?:DS|D|A|R|LOCK|AMEND)-?\d|dref-", re.I)


def _files():
    out = []
    for fn in FUNCTIONS:
        d = os.path.join(ROOT, fn)
        if os.path.isdir(d):
            out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")]
    return out


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _all():
    return {os.path.relpath(p, ROOT)[:-5]: _load(p) for p in _files()}


def _strings(t):
    for k in sorted(KEYS - {"version", "derives_from"}):
        v = t[k]
        for s in (v if isinstance(v, list) else [v]):
            yield k, s


def test_every_function_has_a_default():
    for fn in FUNCTIONS:
        assert os.path.isfile(os.path.join(ROOT, fn, "default.json")), fn + " has no default.json"


def test_no_stray_folders():
    extra = [d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)) and d not in FUNCTIONS]
    assert not extra, "folders that are not one of the five functions: %s" % extra


@pytest.mark.parametrize("path", _files(), ids=lambda p: os.path.relpath(p, ROOT))
def test_shape(path):
    t = _load(path)
    assert set(t) == KEYS, "keys differ: missing %s, extra %s" % (sorted(KEYS - set(t)), sorted(set(t) - KEYS))
    rel = os.path.relpath(path, ROOT)[:-5]
    fn, slug = rel.split(os.sep)
    assert t["id"] == fn + "/" + slug
    assert t["function"] == fn
    assert isinstance(t["version"], int) and t["version"] >= 1
    for k in ("name", "use_case", "schedule", "chat_brief"):
        assert isinstance(t[k], str) and t[k].strip(), k + " is empty"
    for k in LIST_KEYS:
        assert isinstance(t[k], list) and t[k], k + " is empty"
        assert all(isinstance(x, str) and x.strip() for x in t[k]), k + " has a blank line"
        assert len(set(t[k])) == len(t[k]), k + " repeats a line"
    if slug == "default":
        assert t["derives_from"] is None
        assert t["name"] == "Default"
    else:
        assert t["derives_from"] == fn + "/default", "a use-case template derives from its function's default"


@pytest.mark.parametrize("path", [p for p in _files() if not p.endswith("default.json")],
                         ids=lambda p: os.path.relpath(p, ROOT))
def test_narrowing_only(path):
    t = _load(path)
    parent = _all()[t["derives_from"].replace("/", os.sep)]
    missing = [line for line in parent["floor"] if line not in t["floor"]]
    assert not missing, "dropped or reworded floor lines of %s: %s" % (t["derives_from"], missing)
    assert len(t["floor"]) > len(parent["floor"]), "a use-case template adds at least one floor line"
    assert set(parent["checks"]) <= set(t["checks"]), "a use-case template keeps every check of its default"


@pytest.mark.parametrize("path", _files(), ids=lambda p: os.path.relpath(p, ROOT))
def test_chat_brief(path):
    b = _load(path)["chat_brief"]
    assert len(b) <= BRIEF_MAX, "chat brief is %d characters, cap %d" % (len(b), BRIEF_MAX)
    for ph in PLACEHOLDERS:
        assert b.count(ph) == 1, "placeholder %s appears %d times" % (ph, b.count(ph))
    left = re.sub(r"\{(department|goal|done|rules|owner|folder)\}", "", b)
    assert "{" not in left and "}" not in left, "an unknown placeholder"
    assert b.rstrip().endswith("?"), "the brief ends by asking the owner one question"
    assert "never" in b.lower(), "the brief says what the function never does"


@pytest.mark.parametrize("path", _files(), ids=lambda p: os.path.relpath(p, ROOT))
def test_screen_words(path):
    for k, s in _strings(_load(path)):
        assert not FORBIDDEN_WORD.search(s), "%s uses a word the screen does not say: %r" % (k, s[:80])
        assert not FORBIDDEN_ID.search(s), "%s carries a founder-only id or a ref: %r" % (k, s[:80])


def test_a_check_is_never_a_score():
    for rel, t in _all().items():
        for k, s in _strings(t):
            low = s.lower()
            if "score" in low:
                assert "never a score" in low or "as a score" in low or "into a score" in low, \
                    "%s %s treats a check as a score: %r" % (rel, k, s[:80])


def test_readme_lists_every_template():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    for rel in _all():
        assert "`%s.json`" % rel.replace(os.sep, "/") in readme, rel + " is not in the README table"
