"""test_forbidden_calls.py -- provable-negative static test (SAFETY rule 2).

The new /api/org/* + /api/classify surface (org_api.py) and its pure-function
helper (reorg_sim.py) may call ONLY the whitelisted placement_engine reader/
writer set. This test greps both files for the FORBIDDEN mutator names and
FAILS if any appear as a call on the placement_engine module (however it is
imported/aliased) -- mirroring the design doc's own privacy-split test
pattern (a provable negative, not a trust-me comment).

Scope note: this deliberately matches `<alias>.<name>(` where `<alias>` is
resolved from this file's own `import placement_engine as <alias>` line (or
the un-aliased `placement_engine.<name>(`), NOT any bare `<name>(` -- a bare
match would also flag unrelated stdlib/3rd-party calls that happen to share
a name (e.g. `pathlib.Path.resolve()`, `str.repair()`-shaped user code, etc),
which is a false positive, not a safety finding. The engine functions this
test forbids are ONLY reachable through the placement_engine module object,
so gating on that alias is precise, not just convenient.

Run: .venv/bin/python -m pytest test_forbidden_calls.py -q
     (or plain: .venv/bin/python test_forbidden_calls.py)
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

FILES_UNDER_TEST = [
    HERE / "org_api.py",
    HERE / "reorg_sim.py",
]

# The exact mutator names SAFETY rule 2 forbids.
FORBIDDEN_CALLS = [
    "resolve", "mint_domain", "restructure", "retire", "unretire",
    "charter_retire", "charter_reassign", "consolidate", "reconcile",
    "repair", "verify_charters",
]

_IMPORT_ALIAS_RE = re.compile(
    r"^\s*import\s+placement_engine\s+as\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)


def _engine_aliases(text):
    """Every name this file binds `placement_engine` to (usually just one,
    e.g. "E" in org_api.py), plus the unaliased module name itself so
    `placement_engine.retire(...)` is also caught."""
    aliases = set(_IMPORT_ALIAS_RE.findall(text))
    if re.search(r"^\s*import\s+placement_engine\s*$", text, re.M):
        aliases.add("placement_engine")
    return aliases


def _find_forbidden_calls(text, aliases, name):
    """Return every `<alias>.<name>(` call site, alias in `aliases`."""
    hits = []
    for alias in aliases:
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])" + re.escape(alias) + r"\." + re.escape(name) + r"\s*\(")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append((lineno, line.strip()))
    return hits


def test_no_forbidden_mutator_calls():
    violations = []
    for path in FILES_UNDER_TEST:
        text = path.read_text(encoding="utf-8")
        aliases = _engine_aliases(text)
        for name in FORBIDDEN_CALLS:
            for lineno, line in _find_forbidden_calls(text, aliases, name):
                violations.append("%s:%s calls forbidden mutator %r -> %s" %
                                   (path.name, lineno, name, line))

    assert not violations, (
        "Forbidden mutator call(s) found in the org_api/reorg_sim surface "
        "(SAFETY rule 2 -- these files may read the registry and write "
        "exactly one placement via write_placement(), nothing else):\n  "
        + "\n  ".join(violations)
    )


def test_files_exist():
    for path in FILES_UNDER_TEST:
        assert path.exists(), "%s is missing" % path


def test_org_api_declares_its_engine_import():
    """Guard the test itself: if org_api.py stops doing
    `import placement_engine as E`, this test's alias-detection silently
    stops checking anything -- fail loudly instead of passing vacuously."""
    text = (HERE / "org_api.py").read_text(encoding="utf-8")
    assert _engine_aliases(text), (
        "org_api.py no longer has a detectable `import placement_engine as "
        "<alias>` line -- the forbidden-call grep above would silently check "
        "nothing. Update this test's alias detection alongside the import."
    )


if __name__ == "__main__":
    test_files_exist()
    test_org_api_declares_its_engine_import()
    test_no_forbidden_mutator_calls()
    print("OK: no forbidden mutator calls in", [p.name for p in FILES_UNDER_TEST])
