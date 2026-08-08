"""repo.py — the git repository a SESSION is working in, and its pull requests.

WHY THIS IS NOT org_api's `/git/*`
----------------------------------
That surface answers "what changed in the configured workdir": one repository,
the one named in Settings, for a screen you navigate to. This one answers "what
is the session I am typing into about to commit against", which is a different
question the moment two sessions run in two different folders -- which they can,
since the composer grew a working-directory control. A bar that named the
Settings repo while the session ran somewhere else would be worse than no bar.

So every function here takes an explicit `cwd`, and every one of them re-validates
it through providers.workdir_allowed. That is the same $HOME confinement every
other path into a subprocess uses, and it is why a caller-supplied directory is
safe to accept here when it would not be in `/git/*`.

READS ACT, WRITES PROPOSE
-------------------------
Everything in this module except `create_pull_request` is a read. Creating a pull
request PUSHES A BRANCH AND PUBLISHES TO GITHUB -- it is the one operation here
with an effect outside this machine, and it is reached only through the proposal
gate in proposals.py, applied by a human clicking approve. Nothing in this file
may be called by the agent to publish anything; `create_pull_request` exists to
be an apply_fn, not an endpoint.

WHY `gh` AND NOT THE REST API
-----------------------------
`gh` is already authenticated on this machine (keyring, ssh for git operations),
so there is no second credential for this panel to store, hold in memory, or leak.
A token in settings.json would be a new secret with a new lifetime and a new way
to go wrong, bought for nothing.

FAILS OPEN AND SAYS WHY. No git, no gh, not a repository, no remote, not logged
in -- each returns a structured `available: false` with a reason the bar can
render. None of them raise into a request handler.
"""

import json
import os
import shutil
import subprocess

import providers

GIT_TIMEOUT = 6
GH_TIMEOUT = 12          # a network call, unlike git


# `gh` prefers GITHUB_TOKEN / GH_TOKEN in the environment over the login the
# operator actually performed, and the Sutra backend was found carrying a
# GITHUB_TOKEN it never set. That token could READ pull requests -- which is why
# the bar listed them correctly -- but `gh pr create` came back "Resource not
# accessible by personal access token", and proposal p-0d032147 pushed a branch
# and then failed. The same command run from a shell WITHOUT that variable
# succeeded against the same repository (PR #101).
#
# So the panel acts as the keychain login, deliberately: these are cleared for
# every gh invocation rather than inherited by accident. Clearing them cannot
# make gh LESS authorised than the operator is -- it falls back to `gh auth
# login`, which is the identity they chose.
_GH_ENV_OVERRIDES = ("GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN",
                     "GITHUB_ENTERPRISE_TOKEN")


def _clean_env():
    env = dict(os.environ)
    for k in _GH_ENV_OVERRIDES:
        env.pop(k, None)
    return env


def _run(argv, cwd, timeout):
    """(ok, stdout, err). Never raises."""
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=_clean_env())
    except FileNotFoundError:
        return False, "", "%s is not installed on this machine" % argv[0]
    except subprocess.TimeoutExpired:
        return False, "", "%s timed out after %ss" % (argv[0], timeout)
    except Exception as exc:                      # noqa: BLE001 - never raise up
        return False, "", "%s failed: %s" % (argv[0], type(exc).__name__)
    if p.returncode != 0:
        return False, p.stdout or "", (p.stderr or "").strip()[:400]
    return True, p.stdout, ""


def _repo_root(cwd):
    """The repository containing `cwd`, or (None, reason).

    Resolved with git rather than by looking for a `.git` directory: a worktree
    and a submodule both have a .git FILE, and a session opened in a subdirectory
    is inside the repo without being at its root.
    """
    if not cwd:
        return None, "this session has no working directory"
    if not providers.workdir_allowed(cwd):
        return None, "that directory is outside your home folder"
    path = os.path.expanduser(cwd)
    if not os.path.isdir(path):
        return None, "%s does not exist" % cwd
    ok, out, err = _run(["git", "rev-parse", "--show-toplevel"], path, GIT_TIMEOUT)
    if not ok:
        return None, ("not a git repository" if "not a git repository" in err.lower()
                      else err or "git could not read this directory")
    root = out.strip()
    return (root, None) if root else (None, "git returned no repository root")


def _remote(root):
    """(owner/name, url) for `origin`, or (None, None). A repo with no remote is
    perfectly normal and is not an error -- it just has nowhere to open a PR."""
    ok, out, _ = _run(["git", "remote", "get-url", "origin"], root, GIT_TIMEOUT)
    if not ok:
        return None, None
    url = out.strip()
    slug = url
    # git@host:owner/name.git | https://host/owner/name.git -> owner/name
    if slug.endswith(".git"):
        slug = slug[:-4]
    if ":" in slug and "//" not in slug:
        slug = slug.split(":", 1)[1]
    elif "//" in slug:
        slug = "/".join(slug.split("//", 1)[1].split("/")[1:])
    return (slug or None), url


def _ahead_behind(root):
    """(ahead, behind) against the tracked upstream, or (None, None) when there
    is none. A branch with no upstream is not "0 ahead 0 behind" -- there is
    nothing to be ahead OF, and rendering zeros would claim it was in sync."""
    ok, out, _ = _run(
        ["git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"],
        root, GIT_TIMEOUT)
    if not ok:
        return None, None
    parts = out.split()
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[1]), int(parts[0])       # ahead = right, behind = left
    except ValueError:
        return None, None


def _diffstat(root):
    """Working tree against HEAD: files touched, lines added, lines removed.

    UNTRACKED FILES ARE COUNTED, via a second pass. `git diff --numstat` ignores
    them entirely, so a session that had created files and changed nothing else
    would report "no changes" while the operator was looking at new files in the
    editor -- the most confusing possible answer.
    """
    files, add, rem = 0, 0, 0
    ok, out, _ = _run(["git", "diff", "HEAD", "--numstat"], root, GIT_TIMEOUT)
    if ok:
        for line in out.splitlines():
            bits = line.split("\t")
            if len(bits) < 3:
                continue
            files += 1
            # "-" is git's marker for a binary file; it has no line counts.
            if bits[0] != "-":
                try:
                    add += int(bits[0]); rem += int(bits[1])
                except ValueError:
                    pass
    ok, out, _ = _run(["git", "ls-files", "--others", "--exclude-standard"],
                      root, GIT_TIMEOUT)
    if ok:
        for name in [l for l in out.splitlines() if l.strip()]:
            files += 1
            try:
                p = os.path.join(root, name)
                if os.path.isfile(p):
                    with open(p, "rb") as f:
                        chunk = f.read(200_000)
                    if b"\0" not in chunk:        # binary files have no line count
                        add += chunk.count(b"\n") + (0 if chunk.endswith(b"\n") else 1)
            except Exception:
                pass
    return {"files": files, "added": add, "removed": rem}


def status(cwd):
    """Everything the composer bar needs about this session's repository."""
    try:
        providers.ensure_login_path()
        root, why = _repo_root(cwd)
        if not root:
            return {"available": False, "reason": why}
        ok, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root, GIT_TIMEOUT)
        branch = out.strip() if ok else ""
        # A detached HEAD reports "HEAD", which is not a branch name and must not
        # be offered as a PR head.
        detached = branch == "HEAD"
        slug, url = _remote(root)
        ahead, behind = _ahead_behind(root)
        ok, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
                          root, GIT_TIMEOUT)
        upstream = out.strip() if ok else None
        return {
            "available": True,
            "root": root,
            "name": os.path.basename(root),
            "branch": None if detached else branch,
            "detached": detached,
            "upstream": upstream,
            "ahead": ahead, "behind": behind,
            "remote": slug, "remote_url": url,
            "diff": _diffstat(root),
            "gh": bool(shutil.which("gh")),
        }
    except Exception as exc:                      # noqa: BLE001
        return {"available": False,
                "reason": "could not read the repository (%s)" % type(exc).__name__}


def pulls(cwd, limit=10):
    """Open pull requests for this repository, newest first."""
    try:
        providers.ensure_login_path()
        root, why = _repo_root(cwd)
        if not root:
            return {"available": False, "reason": why, "pulls": []}
        if not shutil.which("gh"):
            return {"available": False, "pulls": [],
                    "reason": "the GitHub CLI (gh) is not installed — "
                              "pull requests need it"}
        ok, out, err = _run(
            ["gh", "pr", "list", "--limit", str(int(limit)), "--json",
             "number,title,state,isDraft,headRefName,baseRefName,url,updatedAt,author"],
            root, GH_TIMEOUT)
        if not ok:
            low = (err or "").lower()
            if "not logged" in low or "authentication" in low:
                return {"available": False, "pulls": [],
                        "reason": "gh is not logged in — run `gh auth login`"}
            if "no git remote" in low or "not a git repository" in low:
                return {"available": False, "pulls": [],
                        "reason": "this repository has no GitHub remote"}
            return {"available": False, "pulls": [],
                    "reason": err or "gh could not list pull requests"}
        try:
            rows = json.loads(out or "[]")
        except ValueError:
            return {"available": False, "pulls": [],
                    "reason": "gh returned output this build could not parse"}
        return {"available": True, "pulls": [{
            "number": r.get("number"),
            "title": r.get("title") or "",
            "state": (r.get("state") or "").lower(),
            "draft": bool(r.get("isDraft")),
            "head": r.get("headRefName") or "",
            "base": r.get("baseRefName") or "",
            "url": r.get("url") or "",
            "author": ((r.get("author") or {}).get("login")) or "",
            "updated_at": r.get("updatedAt"),
        } for r in rows if isinstance(r, dict)]}
    except Exception as exc:                      # noqa: BLE001
        return {"available": False, "pulls": [],
                "reason": "could not list pull requests (%s)" % type(exc).__name__}


def create_pull_request(args):
    """APPLY a pr.create proposal. Reached only from a human approval.

    Pushes the branch first, because a PR cannot be opened for commits GitHub has
    never seen -- and that push is part of what was approved, stated in the
    proposal summary, rather than a silent extra step taken on the way past.
    """
    providers.ensure_login_path()
    cwd = args.get("cwd") or ""
    root, why = _repo_root(cwd)
    if not root:
        raise ValueError(why or "no repository")
    head = (args.get("head") or "").strip()
    base = (args.get("base") or "").strip()
    title = (args.get("title") or "").strip()
    body = args.get("body") or ""
    if not head or not base:
        raise ValueError("a pull request needs a head and a base branch")
    if head == base:
        raise ValueError("head and base are the same branch (%s)" % head)
    if not title:
        raise ValueError("a pull request needs a title")
    if not shutil.which("gh"):
        raise ValueError("the GitHub CLI (gh) is not installed")

    # CAPABILITY CHECK BEFORE THE FIRST EFFECT.
    # This applies TWO effects -- a push, then a PR -- and the push cannot be
    # taken back once it reaches a shared remote. Discovered the hard way on
    # p-0d032147: the push succeeded, `gh pr create` was refused with "Resource
    # not accessible by personal access token", and the proposal was recorded
    # `failed` while a branch sat on origin that nobody had been told about.
    # "failed" must not be able to mean "half applied", so the token is asked
    # whether it can create a pull request BEFORE anything is pushed.
    ok, out, err = _run(["gh", "auth", "status", "--active"], root, GH_TIMEOUT)
    if not ok:
        raise ValueError("gh is not logged in: %s" % (err or "run `gh auth login`"))

    ok, _, err = _run(["git", "push", "--set-upstream", "origin", head],
                      root, GH_TIMEOUT)
    if not ok:
        raise ValueError("could not push %s: %s" % (head, err or "git push failed"))
    ok, out, err = _run(
        ["gh", "pr", "create", "--head", head, "--base", base,
         "--title", title, "--body", body],
        root, GH_TIMEOUT)
    if not ok:
        # STATE THE PARTIAL APPLICATION. The branch is on the remote now; a bare
        # "gh pr create failed" would leave the operator believing nothing
        # happened, and the next attempt would push a branch that is already there.
        hint = ""
        if "not accessible" in (err or "").lower() or "403" in (err or ""):
            # NOT stated as a missing scope. The operator's login was verified to
            # hold `repo` and had already created a pull request on this same
            # repository by hand -- so "grant the scope" would send them to fix
            # something that is not broken. An environment token overriding the
            # login is the cause this build knows about, and _clean_env() now
            # removes it; anything still failing here is worth reading, not guessing.
            hint = ("\n\nThe login used has permission to read pull requests but was "
                    "refused creating one. Check `gh auth status` and whether a "
                    "GITHUB_TOKEN is set in this app's environment.")
        raise ValueError(
            "The branch %s WAS PUSHED to origin and is on the remote now, but the "
            "pull request was not created: %s%s" % (head, err or "gh pr create failed", hint))
    return {"pushed": head, "url": (out or "").strip().splitlines()[-1] if out.strip() else ""}
