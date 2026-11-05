#!/usr/bin/env python3
"""Release tag guard: a tag is a claim about the tree, and the tree must agree (D89, D100; modelled on the old repo's guard).

    scripts/py scripts/check_release_tag.py sutra-pro-v0.2.0                        # compare with [project].version of pyproject.toml
    scripts/py scripts/check_release_tag.py sutra-pro-v0.2.0 --pyproject PATH       # another pyproject.toml
    scripts/py scripts/check_release_tag.py sutra-pro-v0.2.0-beta.1 --version 0.2.0 # compare with a version given here
    scripts/py scripts/check_release_tag.py sutra-pro-v0.2.0 --github-output "$GITHUB_OUTPUT"   # also write the release facts

A tag is accepted when it is exactly sutra-pro-vX.Y.Z or sutra-pro-vX.Y.Z-beta.N (X, Y, Z, N plain integers without leading zeros)
and X.Y.Z equals the version in pyproject.toml. The beta suffix is dropped before the comparison: one target version can be cut as
beta.1, beta.2 ... without bumping pyproject.toml each time, and only the stable tag that promotes it needs pyproject.toml at X.Y.Z.
Nothing else is a release tag: no other prefix or suffix (the old product's `vX.Y.Z-desktop` tags included: Sutra Pro shares a
repository with that product, and the `sutra-pro-` prefix is what keeps the two release pipelines apart), no spaces.

Exit status: 0 when the tag is valid and matches; 1 when it is not, or when the version cannot be read (a guard fails closed),
with one `::error::` line on stdout (a GitHub Actions annotation); 2 for a bad command line.
`check(tag, version)` is the pure function the tests drive; `release_facts(tag)` names what a release of that tag is called and
whether it is a pre-release. The release workflows run this file first, before any costly job.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"

# The tag namespace of this product inside the shared repository. The old product's workflows trigger on `v*` and read
# `releases/latest`, so a Sutra Pro tag must never start with a `v`, and a Sutra Pro release must never become "Latest" (D100).
TAG_PREFIX = "sutra-pro-"

# A plain integer: ASCII digits only (\d would accept other scripts' digits), no sign, no leading zero.
_NUM = r"(?:0|[1-9][0-9]*)"
TAG_RE = re.compile(rf"{re.escape(TAG_PREFIX)}v(?P<version>{_NUM}\.{_NUM}\.{_NUM})(?:-beta\.(?P<beta>{_NUM}))?")


def check(tag: str, version: str) -> tuple[bool, str]:
    """Is `tag` a release tag for `version`, the [project].version of pyproject.toml? Returns (ok, message).

    fullmatch, not match with a `$`: `$` also matches before a trailing newline, which would let "sutra-pro-v1.2.3\\n" through.
    """
    found = TAG_RE.fullmatch(tag)
    if found is None:
        return False, (f"tag {tag!r} is not {TAG_PREFIX}vX.Y.Z or {TAG_PREFIX}vX.Y.Z-beta.N "
                       f"(plain integers without leading zeros)")
    claimed = found.group("version")
    if claimed != version:
        return False, (
            f"tag {tag} claims {claimed} but pyproject.toml says {version}. Bump [project].version, or cut the tag that "
            f"matches it. Repairing an OLD release? Dispatch from the tag's own ref: "
            f"gh workflow run sutra-pro-release-wheel -f tag={tag} --ref {tag}"
        )
    kind = "beta, published as a pre-release" if found.group("beta") is not None else "stable"
    return True, f"tag {tag} matches pyproject.toml version {version} ({kind})"


def release_facts(tag: str) -> dict[str, str]:
    """What a release of a VALID tag is: `version` (X.Y.Z), `prerelease` ("true"/"false"), `release_name` and `tag`.

    Raises ValueError for a tag that is not a release tag; call `check` first (the workflows do, in one run of this file).
    """
    found = TAG_RE.fullmatch(tag)
    if found is None:
        raise ValueError(f"{tag!r} is not a release tag")
    beta = found.group("beta")
    name = f"Sutra Pro {found.group('version')}" + (f" beta {beta}" if beta is not None else "")
    return {"tag": tag, "version": found.group("version"), "prerelease": "true" if beta is not None else "false", "release_name": name}


def read_version(pyproject: Path = PYPROJECT) -> str:
    """The static [project].version of a pyproject.toml. Raises OSError (unreadable) or ValueError (no usable version)."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))  # TOMLDecodeError and UnicodeDecodeError are ValueErrors
    project = data.get("project")
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or not version:
        raise ValueError(f"{pyproject.name} has no static [project].version (a dynamic version cannot be guarded)")
    return version


def annotation(message: str) -> str:
    """A GitHub Actions error annotation on ONE line: the escapes stop text from starting a second workflow command."""
    return "::error::" + message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_release_tag.py", description="Check that a release tag matches pyproject.toml.")
    parser.add_argument("tag", help=f"the tag to release, for example {TAG_PREFIX}v0.2.0 or {TAG_PREFIX}v0.2.0-beta.1")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--pyproject", type=Path, default=PYPROJECT, help="the pyproject.toml to read (default: this checkout's)")
    source.add_argument("--version", help="compare with this version instead of reading pyproject.toml")
    parser.add_argument("--github-output", type=Path, default=None, metavar="FILE",
                        help="when the tag is valid, append tag, version, prerelease and release_name as key=value lines "
                             "(the file GitHub Actions calls $GITHUB_OUTPUT)")
    args = parser.parse_args(argv)
    try:
        version = args.version if args.version is not None else read_version(args.pyproject)
    except (OSError, ValueError) as err:
        print(annotation(f"cannot read the version from {args.pyproject}: {err}"))
        return 1
    ok, message = check(args.tag, version)
    print(message if ok else annotation(message))
    if ok and args.github_output is not None:
        # every value is built from validated digits and fixed words, so none can hold a newline or a second key
        with args.github_output.open("a", encoding="utf-8", newline="\n") as out:
            for key, value in release_facts(args.tag).items():
                out.write(f"{key}={value}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
