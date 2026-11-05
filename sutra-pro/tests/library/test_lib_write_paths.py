"""Stores accept only checked objects (library design 3.4 and 14, decision D41; work package L8).

An AST test over an explicit list of store files (`write_paths.txt`): every public method whose name starts with a write verb
(put, insert, append, save, upsert, post, record, apply) must take a parameter annotated `Checked` (alone, `Checked[X]`,
`Checked | None`, `Optional[Checked]`), unless `write_allowlist.txt` names it with the reason. The glob
`sutra_app/**/store*.py` matches none of the orchestrator's files, so the list is explicit, and a listed file that does not exist
fails the test (a moved store cannot make the scan go quiet)."""
import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VERBS = re.compile(r"^(put|insert|append|save|upsert|post|record|apply)")


def read_list(path: Path) -> list[tuple[str, str, str]]:
    """(first word, rest of the line before `#`, comment) of each non-comment line."""
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line, _, comment = raw.partition("  #")
        if line.strip() and not line.lstrip().startswith("#"):
            word, _, rest = line.strip().partition(" ")
            out.append((word, rest.strip(), comment.strip()))
    return out


def mentions_checked(annotation: ast.AST | None) -> bool:
    if annotation is None:
        return False
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id == "Checked":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "Checked":
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"\bChecked\b", node.value):
            return True
    return False


def _checks(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "check" for n in ast.walk(node))


def _self_calls(node: ast.AST) -> set[str]:
    return {n.func.attr for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}


def write_methods(source: str):
    """(qualified name, takes Checked, checks inside) of every public write-verb function of a module. "Checks inside" follows
    the calls a method makes on `self` (a helper of the same class), because a public method often hands on to a private one."""
    tree = ast.parse(source)
    found = []

    def visit_class(cls: ast.ClassDef):
        methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

        def checks_inside(name: str, seen: set[str]) -> bool:
            if name in seen or name not in methods:
                return False
            seen.add(name)
            return _checks(methods[name]) or any(checks_inside(other, seen) for other in _self_calls(methods[name]))
        for node in cls.body:
            if isinstance(node, ast.ClassDef):
                visit_class(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_") and VERBS.match(node.name):
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs + [a for a in (node.args.vararg, node.args.kwarg) if a]
                found.append((f"{cls.name}.{node.name}", any(mentions_checked(a.annotation) for a in args), checks_inside(node.name, set())))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            visit_class(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_") and VERBS.match(node.name):
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs + [a for a in (node.args.vararg, node.args.kwarg) if a]
            found.append((node.name, any(mentions_checked(a.annotation) for a in args), _checks(node)))
    return found


def listed_files() -> list[tuple[Path, bool]]:
    return [(REPO / word, rest == "pending") for word, rest, _ in read_list(HERE / "write_paths.txt")]


def allowed() -> dict[tuple[str, str], str]:
    out = {}
    for word, _, comment in read_list(HERE / "write_allowlist.txt"):
        path, _, name = word.partition(":")
        out[(path, name)] = comment
    return out


# ============================================ the scanner itself ============================================================
SAMPLE = '''
class Store:
    def put(self, c: Checked[Thing]): ...
    def put_two(self, c: "Checked[Thing]"): ...
    def upsert(self, tx, c: Checked | None = None): ...
    def save(self, *, body: Optional[lib.Checked]): ...
    def append_row(self, row: dict): ...
    def record(self, x: int): ...
    def apply(self, c): self.gate.check("x", c)
    def _put_private(self, row): ...
    def get(self, id): ...
    def postal(self, c: str): ...
def insert_all(rows): ...
class Other:
    def apply_two(self, c): return self._inner(c)
    def _inner(self, c): return self._deeper(c)
    def _deeper(self, c): return GATE.check("x", c)
    def post_it(self, c): return self._plain(c)
    def _plain(self, c): return c
'''


def test_the_scanner_finds_the_write_verbs_and_the_checked_parameters():
    assert write_methods(SAMPLE) == [
        ("Store.put", True, False), ("Store.put_two", True, False), ("Store.upsert", True, False), ("Store.save", True, False),
        ("Store.append_row", False, False), ("Store.record", False, False), ("Store.apply", False, True),
        ("Store.postal", False, False), ("insert_all", False, False), ("Other.apply_two", False, True), ("Other.post_it", False, False)]


def test_the_scanner_ignores_private_methods_and_non_write_verbs():
    names = [n for n, _, _ in write_methods(SAMPLE)]
    assert "Store._put_private" not in names and "Store.get" not in names


# ============================================ the real stores ===============================================================
def test_the_list_names_the_eight_store_files_and_all_but_pending_ones_exist():
    files = listed_files()
    assert [p.name for p, _ in files] == ["chart.py", "chats.py", "atoms.py", "usage.py", "graph.py", "tasks.py", "departments.py", "nodes.py"]
    missing = [p.name for p, pending in files if not pending and not p.is_file()]
    assert missing == [], f"listed store files that do not exist: {missing}"
    assert [p.name for p, pending in files if pending] == ["tasks.py"]


def test_every_public_write_method_of_a_store_takes_a_checked_object_or_is_allowed():
    allow, offenders, scanned = allowed(), [], 0
    for path, _ in listed_files():
        if not path.is_file():
            continue
        rel = path.relative_to(REPO).as_posix()
        for name, takes, _ in write_methods(path.read_text(encoding="utf-8")):
            scanned += 1
            if not takes and (rel, name) not in allow:
                offenders.append(f"{rel}:{name}")
    assert scanned >= 8, "the scan found almost no write methods: it is not looking at the stores"
    assert offenders == [], f"write methods without a Checked parameter and without an allowlist line: {offenders}"


def test_every_allowlist_line_names_a_real_method_that_would_otherwise_fail_and_gives_its_reason():
    listed = {p.relative_to(REPO).as_posix(): p for p, _ in listed_files()}
    for (rel, name), reason in allowed().items():
        assert rel in listed and listed[rel].is_file(), f"{rel} is not a listed store file"
        methods = {n: (takes, calls) for n, takes, calls in write_methods(listed[rel].read_text(encoding="utf-8"))}
        assert name in methods, f"{rel}:{name} is not a public write method (remove the line)"
        takes, calls = methods[name]
        assert not takes, f"{rel}:{name} takes a Checked object now: remove its allowlist line"
        assert reason.startswith(("gated:", "read:")) and len(reason) > 12, f"{rel}:{name} needs a 'gated:' or 'read:' reason"
        if reason.startswith("gated:"):
            assert calls, f"{rel}:{name} is allowed because it checks inside, but its body calls no .check(...)"


def test_the_stores_that_must_use_the_gate_each_call_it_somewhere():
    for path, _ in listed_files():
        if path.is_file() and path.name not in ("departments.py",):
            text = path.read_text(encoding="utf-8")
            assert "GATE" in text or "Checked" in text, f"{path.name} neither imports the gate nor takes Checked objects"
