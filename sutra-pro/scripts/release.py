#!/usr/bin/env python3
"""Publish a Sutra Pro release on GitHub, then install it on this Mac (D242). The steps of docs/RELEASE.md, in one command that stops at the first thing wrong.

    scripts/py scripts/release.py                        the next PATCH version after the newest stable `sutra-pro-vX.Y.Z` tag
    scripts/py scripts/release.py --bump minor           X.Y+1.0 (or --bump major)
    scripts/py scripts/release.py --version 1.2.3        exactly that version
    scripts/py scripts/release.py --dry-run              say what would happen and change nothing (it does fetch)

Run it in a checkout whose HEAD is what should ship (everything of origin/main merged in) and whose tracked files are committed. It then:

  1. fetches origin and its tags, and refuses when origin/main has commits HEAD lacks, or when the version is already tagged (somebody released it: install it with
     `scripts/py scripts/install_app.py release TAG` instead), or when the release workflows changed since the last release (docs/RELEASE.md: a beta tag first);
  2. sets the version in pyproject.toml, sutra_app/__init__.py, desktop/package.json and its lock (nothing to do when they already say it) and commits that
     with docs/release-notes/X.Y.Z.md, which must exist: what is new, in a few plain lines, starting `### What is new in X.Y.Z` (`--no-notes` releases without);
  3. waits for a green `sutra-pro-ci` run on exactly that commit (it pushes the branch release/X.Y.Z for the run when none exists): the release workflows
     build and verify the artifacts, they do not run the test gate again;
  4. pushes HEAD to main (a fast-forward: it stops when main moved meanwhile), tags it `sutra-pro-vX.Y.Z` (annotated) and pushes the tag;
  5. watches the three release runs (wheel, macOS, Windows) of that commit until all are done; any failure stops here and names the run;
  6. checks the release: not a draft, not a pre-release, not "Latest" (that belongs to the older product), every asset and its checksum there; puts the release
     notes in front of the release text the workflows wrote;
  7. installs the published release on this Mac (scripts/install_app.py release TAG), unless `--no-install`.

The tag is never moved or deleted. A failed release leg is repaired as docs/RELEASE.md says (`gh workflow run ... -f tag=TAG --ref TAG`), not by a new tag.

GitHub: git and gh run without GITHUB_TOKEN / GH_TOKEN in their environment when `gh` is signed in on this machine (a token that cannot open pull requests or read secrets
would be used first otherwise); with no such login the environment is left as it is.

Exit status: 0 done; 1 a step failed (one `error:` line); 2 bad command line; 3 the release is out but the stable app was busy, so it is not installed yet.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import install_app                                                           # noqa: E402  (the install step, the command runner, the tag pattern)

REPO = install_app.REPO
TAG = install_app.TAG
RELEASE_WORKFLOWS = ("sutra-pro-release-wheel", "sutra-pro-release-macos", "sutra-pro-release-windows")
CI_WORKFLOW = "sutra-pro-ci"
CI_TIMEOUT_S = 90 * 60
RELEASE_TIMEOUT_S = 120 * 60
POLL_S = 30


class ReleaseError(Exception):
    """A step failed; `str(error)` is the one line the owner reads."""


def say(text: str) -> None:
    print(text, flush=True)


# ---------------------------------------------------------------- versions (pure)

def parse_tag(tag: str) -> Optional[tuple[int, int, int]]:
    found = TAG.match(tag)
    return tuple(int(part) for part in found.groups()) if found else None            # type: ignore[return-value]


def newest_version(tags: Sequence[str]) -> Optional[tuple[int, int, int]]:
    versions = [parsed for parsed in (parse_tag(tag.strip()) for tag in tags) if parsed]
    return max(versions) if versions else None


def next_version(latest: tuple[int, int, int], bump: str) -> str:
    major, minor, patch = latest
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ReleaseError(f"--bump is patch, minor or major, not {bump!r}")


def as_text(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


VERSION_FILES = (("pyproject.toml", 1), ("sutra_app/__init__.py", 1), ("desktop/package.json", 1), ("desktop/package-lock.json", 2))
VERSION_LINE = {
    "pyproject.toml": re.compile(r'^(version = ")([^"]+)(")', re.M),
    "sutra_app/__init__.py": re.compile(r'^(__version__ = ")([^"]+)(")', re.M),
    "desktop/package.json": re.compile(r'^(  "version": ")([^"]+)(")', re.M),
    "desktop/package-lock.json": re.compile(r'^((?:  |      )"version": ")([^"]+)(")', re.M),     # the top of the file, and packages[""]
}


def versions_in(root: Path) -> dict[str, list[str]]:
    """The version each file says, as `{file: [versions]}` (the lock file says it twice)."""
    found = {}
    for name, _count in VERSION_FILES:
        text = (root / name).read_text(encoding="utf-8")
        found[name] = [match.group(2) for match in VERSION_LINE[name].finditer(text)][: dict(VERSION_FILES)[name]]
    return found


def set_version(root: Path, version: str) -> list[str]:
    """Write `version` into the four files, keeping everything else of them as it is; the names of the files that changed."""
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ReleaseError(f"the version must be X.Y.Z (plain integers), not {version!r}")
    changed = []
    for name, count in VERSION_FILES:
        path = root / name
        text = path.read_text(encoding="utf-8")
        seen = {"n": 0}

        def swap(match: re.Match) -> str:
            seen["n"] += 1
            return match.group(0) if seen["n"] > count else f"{match.group(1)}{version}{match.group(3)}"

        updated = VERSION_LINE[name].sub(swap, text)
        if seen["n"] < count:
            raise ReleaseError(f"{name} does not carry {count} version line(s) the way this script reads them: set the version by hand")
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="")
            changed.append(name)
    return changed


# ---------------------------------------------------------------- commands

run = install_app.run
_network: dict[str, Optional[dict]] = {}


def network_env() -> Optional[dict]:
    """None (leave the environment as it is), or the environment without GITHUB_TOKEN and GH_TOKEN when `gh` is signed in without them: such a token (a
    pipeline's, a limited one) is used by git's credential helper and by gh before the login, and cannot do what a release needs."""
    if "env" not in _network:
        _network["env"] = None
        if os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"):
            clean = {key: value for key, value in os.environ.items() if key not in ("GITHUB_TOKEN", "GH_TOKEN")}
            if run(["gh", "auth", "status"], env=clean, timeout=60).returncode == 0:
                _network["env"] = clean
    return _network["env"]


def git(*args: str, check: bool = True, network: bool = False, timeout: float = 600) -> str:
    done = run(["git", "-C", str(ROOT), *args], env=network_env() if network else None, timeout=timeout)
    if check and done.returncode != 0:
        raise ReleaseError(f"git {' '.join(args[:3])} failed: {(done.stderr or done.stdout).strip()[-300:]}")
    return done.stdout.strip()


def gh(*args: str, check: bool = True, timeout: float = 300) -> str:
    done = run(["gh", *args, "-R", REPO] if args[0] != "api" else ["gh", *args], env=network_env(), timeout=timeout)
    if check and done.returncode != 0:
        raise ReleaseError(f"gh {' '.join(args[:3])} failed: {(done.stderr or done.stdout).strip()[-300:]}")
    return done.stdout.strip()


def json_of(text: str):
    import json
    try:
        return json.loads(text or "null")
    except ValueError as error:
        raise ReleaseError(f"gh answered something that is not JSON: {text[:120]!r}") from error


def sleep(seconds: float) -> None:
    time.sleep(seconds)


# ---------------------------------------------------------------- the steps

def check_checkout() -> None:
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ReleaseError("tracked files have uncommitted changes: commit them (or put them aside) first, a release ships a commit")
    git("fetch", "origin", "--tags", "--prune", "--force", network=True)
    if run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", "origin/main", "HEAD"]).returncode != 0:
        raise ReleaseError("origin/main has commits that HEAD lacks: merge it (git merge origin/main), run the tests, and try again")


def release_tags() -> list[str]:
    return [line for line in git("tag", "--list", "sutra-pro-v*").splitlines() if line]


def workflows_changed_since(tag: str) -> list[str]:
    """The workflow files of this product that differ between `tag` and HEAD (`:/` names a path from the top of the repository, not from this folder)."""
    files = git("diff", "--name-only", tag, "HEAD", "--", *(f":/.github/workflows/{name}.yml" for name in (CI_WORKFLOW, *RELEASE_WORKFLOWS)))
    return [line for line in files.splitlines() if line]


def decide_version(args: argparse.Namespace) -> tuple[str, Optional[str]]:
    """(the version to release, the newest stable tag so far)."""
    tags = release_tags()
    latest = newest_version(tags)
    if args.version:
        wanted = args.version
        if parse_tag(f"sutra-pro-v{wanted}") is None:
            raise ReleaseError(f"--version must be X.Y.Z (plain integers), not {wanted!r}")
    else:
        if latest is None:
            raise ReleaseError("there is no stable sutra-pro-vX.Y.Z tag to count on: name the version with --version")
        wanted = next_version(latest, args.bump)
    tag = f"sutra-pro-v{wanted}"
    if tag in tags or git("ls-remote", "--tags", "--refs", "origin", f"refs/tags/{tag}", network=True):
        raise ReleaseError(f"{tag} already exists: it was released (by somebody else, or by an earlier run). Install it with "
                           f"scripts/py scripts/install_app.py release {tag}, or pick another version")
    if latest is not None and parse_tag(tag) <= latest:                          # type: ignore[operator]
        raise ReleaseError(f"{wanted} is not newer than the newest release, {as_text(latest)}")
    return wanted, (f"sutra-pro-v{as_text(latest)}" if latest else None)


def notes_path(root: Path, version: str) -> Path:
    return root / "docs" / "release-notes" / f"{version}.md"


def commit_version(root: Path, version: str, *, notes: bool, trailers: Sequence[str]) -> bool:
    """Set the version and commit it with the notes; False when the tree already said it and nothing needed committing."""
    paths = set_version(root, version)                              # git runs in this folder, so a path is what the folder calls it
    if notes:
        paths.append(f"docs/release-notes/{version}.md")
    if not paths:
        return False
    git("add", "--", *paths)
    if not git("diff", "--cached", "--name-only"):                  # the files already said it and the notes were committed: nothing to commit
        return False
    message = f"Release: version {version} (pyproject, package, desktop package and lock)\n\n" + "\n".join(trailers)
    git("commit", "-m", message.strip() + "\n")
    return True


def ci_state(sha: str) -> tuple[str, str]:
    """('success' | 'pending' | 'failed' | 'none', a url to look at) of the sutra-pro-ci runs of exactly this commit."""
    rows = json_of(gh("run", "list", "--workflow", CI_WORKFLOW, "--commit", sha, "--json", "databaseId,status,conclusion,url", "--limit", "20")) or []
    if not rows:
        return "none", ""
    if any(row["conclusion"] == "success" and row["status"] == "completed" for row in rows):
        return "success", rows[0]["url"]
    if any(row["status"] != "completed" for row in rows):
        return "pending", rows[0]["url"]
    return "failed", rows[0]["url"]


def wait_for_ci(sha: str, version: str) -> None:
    state, url = ci_state(sha)
    if state == "success":
        say(f"{CI_WORKFLOW} is green for {sha[:8]}")
        return
    if state == "none":
        say(f"no {CI_WORKFLOW} run exists for {sha[:8]}: pushing release/{version} to start one")
        git("push", "origin", f"{sha}:refs/heads/release/{version}", network=True)
    deadline = time.monotonic() + CI_TIMEOUT_S
    while time.monotonic() < deadline:
        sleep(POLL_S)
        state, url = ci_state(sha)
        if state == "success":
            say(f"{CI_WORKFLOW} is green for {sha[:8]}")
            return
        if state == "failed":
            raise ReleaseError(f"{CI_WORKFLOW} failed for {sha[:8]}: {url}. Fix it, commit, and run this again (nothing was tagged)")
    raise ReleaseError(f"{CI_WORKFLOW} was still running after {CI_TIMEOUT_S // 60} minutes: {url}. Run this again when it is done")


def land_and_tag(version: str, sha: str) -> str:
    tag = f"sutra-pro-v{version}"
    on_main = git("rev-parse", "origin/main") == sha
    if not on_main:
        pushed = run(["git", "-C", str(ROOT), "push", "origin", f"{sha}:refs/heads/main"], env=network_env(), timeout=600)
        if pushed.returncode != 0:
            raise ReleaseError("pushing to main was refused (main moved, or it is protected): "
                               f"{(pushed.stderr or pushed.stdout).strip()[-250:]}. Merge origin/main, rerun the tests, and try again")
        say(f"main is now {sha[:8]}")
    git("tag", "-a", tag, "-m", f"Sutra Pro {version}", sha)
    git("push", "origin", f"refs/tags/{tag}", network=True)
    say(f"tagged {tag} ({sha[:8]}) and pushed the tag")
    return tag


def wait_for_release_runs(tag: str, sha: str) -> None:
    deadline = time.monotonic() + RELEASE_TIMEOUT_S
    last = ""
    while time.monotonic() < deadline:
        rows = json_of(gh("run", "list", "--branch", tag, "--json", "databaseId,workflowName,status,conclusion,headSha,url", "--limit", "30")) or []
        mine = {row["workflowName"]: row for row in rows if row["headSha"] == sha and row["workflowName"] in RELEASE_WORKFLOWS}
        failed = [row for row in mine.values() if row["status"] == "completed" and row["conclusion"] != "success"]
        if failed:
            raise ReleaseError("; ".join(f"{row['workflowName']} {row['conclusion']}: {row['url']}" for row in failed)
                               + f". Repair as docs/RELEASE.md says (gh workflow run <workflow> -f tag={tag} --ref {tag}); the tag stays")
        if set(mine) == set(RELEASE_WORKFLOWS) and all(row["status"] == "completed" for row in mine.values()):
            say("the wheel, macOS and Windows release runs are green")
            return
        progress = ", ".join(f"{name.replace('sutra-pro-release-', '')} {mine[name]['status'] if name in mine else 'not started'}" for name in RELEASE_WORKFLOWS)
        if progress != last:
            say(f"release runs: {progress}")
            last = progress
        sleep(POLL_S)
    raise ReleaseError(f"the release runs of {tag} did not finish within {RELEASE_TIMEOUT_S // 60} minutes: gh run list --branch {tag} -R {REPO}")


def required_assets(version: str) -> list[str]:
    names = ["Sutra-Pro-arm64.dmg", "Sutra-Pro-x86_64.dmg", "Sutra-Pro-Setup-x64.exe", "Sutra-Pro-win-x64.zip", f"sutra_pro-{version}-py3-none-any.whl",
             "sutra_pro-py3-none-any.whl"]
    return names + [name + ".sha256" for name in names]


def check_release(tag: str, version: str) -> dict:
    release = json_of(gh("release", "view", tag, "--json", "assets,isDraft,isPrerelease,url,body,tagName"))
    if release.get("isDraft") or release.get("isPrerelease"):
        raise ReleaseError(f"{tag} is a draft or a pre-release: {release.get('url')}")
    missing = sorted(set(required_assets(version)) - {asset["name"] for asset in release.get("assets", [])})
    if missing:
        raise ReleaseError(f"the release {tag} lacks assets: {', '.join(missing)} ({release.get('url')})")
    latest = json_of(gh("release", "list", "--json", "tagName,isLatest", "--limit", "10")) or []
    if any(row["isLatest"] and row["tagName"] == tag for row in latest):
        raise ReleaseError(f"{tag} is marked Latest, which belongs to the older product (D100): {release.get('url')}")
    return release


def put_notes_in_front(tag: str, version: str, root: Path, release: dict) -> bool:
    path = notes_path(root, version)
    if not path.is_file():
        return False
    notes = path.read_text(encoding="utf-8").strip()
    body = release.get("body") or ""
    if not notes or notes in body:
        return False
    with tempfile.TemporaryDirectory() as folder:
        file = Path(folder) / "notes.md"
        file.write_text(notes + "\n\n" + body, encoding="utf-8")
        gh("release", "edit", tag, "--notes-file", str(file), "--latest=false")
    return True


# ---------------------------------------------------------------- the command

def release(args: argparse.Namespace) -> int:
    root = ROOT
    check_checkout()
    version, last = decide_version(args)
    tag = f"sutra-pro-v{version}"
    if last and not args.allow_workflow_changes:
        changed = workflows_changed_since(last)
        if changed:
            raise ReleaseError(f"the release workflows changed since {last} ({', '.join(changed)}): docs/RELEASE.md asks for a beta tag "
                               f"(sutra-pro-v{version}-beta.1) first, to see them run. Do that, then run this with --allow-workflow-changes")
    notes = not args.no_notes
    if notes and not notes_path(root, version).is_file():
        raise ReleaseError(f"write the release notes first: sutra-pro/docs/release-notes/{version}.md (a few plain lines about what is new, starting "
                           f"`### What is new in {version}`), or release without them with --no-notes")
    sha = git("rev-parse", "HEAD")
    if args.dry_run:
        say(f"dry run: nothing is committed, pushed or tagged. Release {version} of {sha[:8]} (the last release was {last or 'none'}) would:")
        say(f"  1. set the version to {version} in " + ", ".join(name for name, _ in VERSION_FILES) + (" and commit it with the notes" if notes else ""))
        say(f"  2. wait for a green {CI_WORKFLOW} run of that commit (pushing release/{version} to start one)")
        say(f"  3. push it to main, tag {tag} (annotated), push the tag")
        say("  4. watch " + ", ".join(RELEASE_WORKFLOWS))
        say("  5. check the assets and that it is not Latest" + (", put the notes in front of the release text" if notes else ""))
        say("  6. install it here: scripts/install_app.py release " + tag if not args.no_install else "  6. (not installed here: --no-install)")
        say("version files now say: " + "; ".join(f"{name} {', '.join(found)}" for name, found in versions_in(root).items()))
        return 0
    if commit_version(root, version, notes=notes, trailers=args.trailer):
        say(f"committed the version {version}" + (" and the release notes" if notes else ""))
    sha = git("rev-parse", "HEAD")
    wait_for_ci(sha, version)
    tag = land_and_tag(version, sha)
    wait_for_release_runs(tag, sha)
    published = check_release(tag, version)
    if notes and put_notes_in_front(tag, version, root, published):
        say("the release notes are in front of the release text")
    say(f"released: {published['url']}")
    if args.no_install:
        return 0
    return install_app.install_release(tag, install_app.DEFAULT_INSTALL_DIR if not args.install_dir else args.install_dir, force=args.force)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a Sutra Pro release on GitHub, then install it on this Mac.")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--bump", choices=("patch", "minor", "major"), default="patch", help="which number counts up from the newest release (default patch)")
    choice.add_argument("--version", default=None, help="the exact version, X.Y.Z")
    parser.add_argument("--no-notes", action="store_true", help="release without docs/release-notes/X.Y.Z.md")
    parser.add_argument("--no-install", action="store_true", help="publish only; do not install the release on this Mac")
    parser.add_argument("--install-dir", type=Path, default=None, help="where the app is installed (default /Applications)")
    parser.add_argument("--force", action="store_true", help="at the install step: quit the running app even when it is working")
    parser.add_argument("--allow-workflow-changes", action="store_true", help="the release workflows changed since the last release and a beta tag has already shown them working")
    parser.add_argument("--trailer", action="append", default=[], help="a line for the end of the version commit's message (repeatable), e.g. a Co-Authored-By line")
    parser.add_argument("--dry-run", action="store_true", help="say what would happen and change nothing")
    args = parser.parse_args(argv)
    try:
        return release(args)
    except install_app.Busy as error:
        print(f"error: the release is published, but {error}", file=sys.stderr)
        return install_app.BUSY
    except (ReleaseError, install_app.InstallError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
