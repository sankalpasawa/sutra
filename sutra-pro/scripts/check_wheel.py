#!/usr/bin/env python3
"""Wheel check: the wheel is the product, so look inside it (D86, D88, D89).

    scripts/py scripts/check_wheel.py dist/*.whl [--root DIR]

For every wheel given it asserts that
  1. every glob of [tool.setuptools.package-data] in pyproject.toml matches at least one member of the wheel whose source file
     exists in the tree under --root (default: this checkout). A data file the wheel forgot is found by the first user: from
     the checkout it is simply there, so no test run from the checkout can see it missing;
  2. entry_points.txt declares  sutra-pro = sutra_app.__main__:main  under [console_scripts] (the command of D88);
  3. METADATA Name is sutra-pro.
It reports every problem it finds, not only the first, as `::error::` lines (GitHub Actions annotations). Exit status: 0 when
every wheel is clean, 1 when any is not, 2 for a bad command line.

The globs are expanded over the source tree with the same `glob.glob(..., recursive=True)` that setuptools uses for package data
(`*` stays inside one directory, `**` crosses directories, a leading dot is hidden), and the wheel is then asked whether it
holds the files the expansion found. So a glob that matches nothing in the tree is a problem of its own: it cannot ship anything.
"""
from __future__ import annotations

import argparse
import configparser
import glob
import sys
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DIST_NAME = "sutra-pro"
SCRIPT_NAME = "sutra-pro"
SCRIPT_TARGET = "sutra_app.__main__:main"


def _dig(data: object, *keys: str) -> object:
    """data[k1][k2]... where every level must be a table; None as soon as one is not."""
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data


def source_dir(pyproject: dict, package: str) -> PurePosixPath:
    """Where a package lives in the tree: its dotted name as a path, moved by [tool.setuptools.package-dir] when present."""
    mapping = _dig(pyproject, "tool", "setuptools", "package-dir")
    mapping = mapping if isinstance(mapping, dict) else {}
    if package in mapping:
        return PurePosixPath(mapping[package])
    return PurePosixPath(mapping.get("", "."), *package.split("."))


def package_data_problems(pyproject: dict, root: Path, names: set[str]) -> list[str]:
    """Check 1: every package-data glob has a source file in the tree under `root` and that file is a member of the wheel."""
    table = _dig(pyproject, "tool", "setuptools", "package-data")
    if not isinstance(table, dict) or not table:
        return ["pyproject.toml has no [tool.setuptools.package-data]: the wheel would carry none of the data files"]
    problems = []
    for package, patterns in table.items():
        if "*" in package:
            problems.append(f"package-data key {package!r} is not supported: name the package")
            continue
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            problems.append(f"package-data of {package} is not a list of globs")
            continue
        where = source_dir(pyproject, package)
        tree = root / where
        in_wheel = PurePosixPath(*package.split("."))
        for pattern in patterns:
            files = sorted(
                Path(found).as_posix()
                for found in glob.glob(pattern, root_dir=tree, recursive=True)
                if (tree / found).is_file()
            )
            if not files:
                problems.append(f"package-data glob {pattern!r} of {package} matches no file in the tree (under {where}/)")
            elif not any(f"{in_wheel}/{name}" in names for name in files):
                problems.append(
                    f"package-data glob {pattern!r} of {package} matches {len(files)} file(s) in the tree "
                    f"(for example {files[0]}) but not one of them is in the wheel"
                )
    return problems


def entry_point_problems(text: str | None) -> list[str]:
    """Check 2: entry_points.txt declares the console script sutra-pro with the right target."""
    if text is None:
        return ["the wheel has no entry_points.txt, so it declares no console script"]
    parser = configparser.ConfigParser(delimiters=("=",), interpolation=None, strict=False)
    parser.optionxform = str  # command names are case-sensitive
    try:
        parser.read_string(text)
    except configparser.Error as err:
        return [f"entry_points.txt cannot be parsed: {err}"]
    scripts = dict(parser.items("console_scripts")) if parser.has_section("console_scripts") else {}
    if SCRIPT_NAME not in scripts:
        return [f"entry_points.txt declares no console script {SCRIPT_NAME!r} (it declares: {sorted(scripts) or 'none'})"]
    if scripts[SCRIPT_NAME] != SCRIPT_TARGET:
        return [f"console script {SCRIPT_NAME} points at {scripts[SCRIPT_NAME]!r}, expected {SCRIPT_TARGET!r}"]
    return []


def name_problems(text: str | None) -> list[str]:
    """Check 3: METADATA Name is the distribution name."""
    if text is None:
        return ["the wheel has no METADATA"]
    name = Parser().parsestr(text, headersonly=True).get("Name")
    if name != DIST_NAME:
        return [f"METADATA Name is {name!r}, expected {DIST_NAME!r}"]
    return []


def check_wheel(wheel: Path, root: Path = ROOT) -> list[str]:
    """Every problem found in `wheel`, checked against the tree at `root`. An empty list means the wheel is clean."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            dist_infos = sorted({n.split("/", 1)[0] for n in names if n.split("/", 1)[0].endswith(".dist-info")})

            def read(member: str) -> str | None:
                path = f"{dist_infos[0]}/{member}" if len(dist_infos) == 1 else None
                return archive.read(path).decode("utf-8") if path in names else None

            metadata, entry_points = read("METADATA"), read("entry_points.txt")
    except (OSError, ValueError, zipfile.BadZipFile) as err:  # ValueError: a member that is not UTF-8 text
        return [f"cannot read the wheel: {err}"]
    problems = []
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        problems.append(f"cannot read pyproject.toml under {root}: {err}")
    else:
        problems += package_data_problems(pyproject, root, names)
    if len(dist_infos) != 1:
        found = f": {', '.join(dist_infos)}" if dist_infos else ""
        problems.append(f"expected exactly one *.dist-info directory in the wheel, found {len(dist_infos)}{found}")
    return problems + entry_point_problems(entry_points) + name_problems(metadata)


def annotation(message: str) -> str:
    """A GitHub Actions error annotation on ONE line: the escapes stop text from starting a second workflow command."""
    return "::error::" + message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_wheel.py", description="Check what is inside a built sutra-pro wheel.")
    parser.add_argument("wheels", nargs="+", type=Path, metavar="WHEEL", help="the wheel(s) to check, for example dist/*.whl")
    parser.add_argument("--root", type=Path, default=ROOT, help="the source tree the wheel was built from (default: this checkout)")
    args = parser.parse_args(argv)
    failed = False
    for wheel in args.wheels:
        problems = check_wheel(wheel, args.root)
        for problem in problems:
            print(annotation(f"{wheel.name}: {problem}"))
        if not problems:
            print(f"ok: {wheel.name}: every package-data glob has its files, console script {SCRIPT_NAME} -> {SCRIPT_TARGET}, "
                  f"Name {DIST_NAME}")
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
