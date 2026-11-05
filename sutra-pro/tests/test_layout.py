"""Repository layout rules the merge gate enforces for every work package."""
from collections import defaultdict
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def _package_root(path: Path) -> Path:
    """The directory pytest puts on sys.path for this test file (prepend mode): the first parent without __init__.py."""
    d = path.parent
    while (d / "__init__.py").exists() and d != TESTS.parent:
        d = d.parent
    return d


def test_test_module_basenames_are_unique_unless_packaged():
    """Two test modules with one basename collide at collection unless their folder is a package (has __init__.py)."""
    by_name = defaultdict(list)
    for path in TESTS.rglob("test_*.py"):
        if "fixtures" in path.parts or "__pycache__" in path.parts:
            continue
        if (path.parent / "__init__.py").exists():
            continue  # imported as <package>.<module>, so the basename may repeat in another package
        by_name[path.name].append(str(path.relative_to(TESTS.parent)))
    clashes = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    assert not clashes, f"test modules share a basename and their folders are not packages: {clashes}"


def test_no_test_file_sits_outside_tests():
    root = TESTS.parent
    stray = [str(p.relative_to(root)) for p in (root / "sutra_app").rglob("test_*.py")]
    assert not stray, f"test files belong under tests/: {stray}"
