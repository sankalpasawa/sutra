"""`python -m sutra_app.library.export [--check]`: write or diff the schema files (library design 3.3, flow F5).

Writes `<family>.v<N>.json` (the JSON Schema of each version of each family, sorted keys, indent 2) and `index.json`
(`{family: {version: [kinds]}}`) into `docs/schemas/` (or `SUTRA_SCHEMA_DIR`, or `--dir`). `--check` writes nothing and
exits 1 when the directory differs from a fresh export, so a breaking change without a version bump cannot merge.

The files are generated documentation and a drift guard; nothing reads them at run time. The export is deterministic:
families and versions are sorted, kinds keep their registration order.
"""
import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path

from .registry import REGISTRY, ModelRegistry

__all__ = ["DEFAULT_DIR", "schema_dir", "render", "write", "check", "load_registry", "main"]

# sutra_app/library/export.py -> the repo root; the export is a development tool and runs from a checkout
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "docs" / "schemas"
_SCHEMA_FILE = re.compile(r"[a-z][a-z0-9_.-]*\.v[0-9]+\.json")      # what an export owns in the top of the directory


def schema_dir(explicit: str | os.PathLike | None = None) -> Path:
    """The target directory: the argument, else SUTRA_SCHEMA_DIR, else docs/schemas of the checkout."""
    chosen = explicit or os.environ.get("SUTRA_SCHEMA_DIR")
    return Path(chosen) if chosen else DEFAULT_DIR


def _dump(obj: object, *, sort_keys: bool) -> str:
    return json.dumps(obj, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"


def render(registry: ModelRegistry = REGISTRY) -> dict[str, str]:
    """file name -> text for every file an export holds."""
    files: dict[str, str] = {}
    index: dict[str, dict[str, list[str]]] = {}
    for family in registry.families():
        index[family] = {}
        for version in registry.versions(family):
            files[f"{family}.v{version}.json"] = _dump(registry.json_schema(family, version), sort_keys=True)
            index[family][str(version)] = list(registry.kinds(family, version))
    files["index.json"] = _dump(index, sort_keys=False)
    return files


def check(directory: str | os.PathLike, registry: ModelRegistry = REGISTRY) -> list[str]:
    """What differs between `directory` and a fresh export: `missing: f`, `differs: f`, `stale: f`; [] when equal."""
    root = Path(directory)
    fresh = render(registry)
    problems: list[str] = []
    for name, text in fresh.items():
        path = root / name
        if not path.is_file():
            problems.append(f"missing: {name}")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"differs: {name}")
    if root.is_dir():
        for path in sorted(root.iterdir()):
            if path.is_file() and _SCHEMA_FILE.fullmatch(path.name) and path.name not in fresh:
                problems.append(f"stale: {path.name}")
    return problems


def write(directory: str | os.PathLike, registry: ModelRegistry = REGISTRY) -> list[str]:
    """Write a fresh export into `directory` (created if needed) and remove its stale `*.v<N>.json` files. Returns
    what changed, as `wrote: f` and `removed: f`; [] when the directory was already up to date."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    fresh = render(registry)
    changed: list[str] = []
    for name, text in fresh.items():
        path = root / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8", newline="\n")
            changed.append(f"wrote: {name}")
    for path in sorted(root.iterdir()):
        if path.is_file() and _SCHEMA_FILE.fullmatch(path.name) and path.name not in fresh:
            path.unlink()
            changed.append(f"removed: {path.name}")
    return changed


def load_registry() -> ModelRegistry:
    """The app's registry with every library module imported (`sutra_app.library.all`, once it exists)."""
    try:
        importlib.import_module("sutra_app.library.all")
    except ModuleNotFoundError as exc:
        if exc.name != "sutra_app.library.all":      # a module `all` itself needs is missing: that is a real error
            raise
    return REGISTRY


def main(argv: list[str] | None = None, registry: ModelRegistry | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sutra_app.library.export",
        description="Write the JSON Schema of every registered family to docs/schemas/, or with --check diff it.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if the directory is out of date")
    parser.add_argument("--dir", default=None, help="target directory (default: SUTRA_SCHEMA_DIR, else docs/schemas)")
    args = parser.parse_args(argv)
    reg = registry if registry is not None else load_registry()
    directory = schema_dir(args.dir)
    if args.check:
        problems = check(directory, reg)
        if problems:
            print(f"schema drift in {directory}:")
            for line in problems:
                print(f"  {line}")
            print("review the change, then run: python -m sutra_app.library.export")
            return 1
        print(f"{directory}: up to date ({len(render(reg))} files)")
        return 0
    changed = write(directory, reg)
    for line in changed:
        print(line)
    print(f"{directory}: {'updated' if changed else 'already up to date'} ({len(render(reg))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
