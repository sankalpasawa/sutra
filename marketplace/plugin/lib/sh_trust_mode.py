#!/usr/bin/env python3
# sh_trust_mode.py — Trust Mode for Sutra permission-gate v2.5+
#
# BUILD-LAYER: L0 (fleet)
# Charter: sutra/os/charters/PERMISSIONS.md §4 Tier 1.5 (Trust Mode)
# Review:  Claude + Codex converged GO 2026-04-27
#
# Threat model:
#   "Trust Mode assumes a single trusted local operator on a personally
#   managed machine, no adversarial prompt/file/environment injection, and
#   reserves prompts only for commands with high risk of irreversible local
#   loss, privilege escalation, or remote/shared-state mutation."
#
# Reads a shell command from stdin. Prints one JSON line:
#   {"prompt": false, "pattern": "Bash(trust-mode-auto-approve)"}  -> auto-allow
#   {"prompt": true,  "category": "...", "reason": "..."}          -> prompt
#
# Six prompt categories (anything not matching auto-approves):
#   1. Git history mutations
#   2. Privilege escalation
#   3. Recursive deletes outside safe-path allowlist
#   4. Disk/system catastrophes
#   5. Fetch-and-exec
#   6. Remote / shared-state mutations
#
# Fail-safe-to-prompt: lex errors -> prompt=true.

import json
import re
import shlex
import sys

# v2.6.1+: simplified to "catastrophic-only" rule per founder direction.
# `git` prompts only on force-push (rewrites remote history) and `clean -f*`
# (deletes untracked files irrecoverably). Everything else (commit, push, pull,
# rebase, merge, rm, mv, reset --hard, checkout, branch -d, tag -d, stash drop)
# auto-approves. All recoverable via reflog or remote.
PRIVILEGE_TOKENS = {"sudo", "su", "doas", "pkexec"}

RM_RECURSIVE_RE = re.compile(r"^rm\s+(-[a-zA-Z]*[rR][a-zA-Z]*\b|-r\b|-R\b)")
SAFE_DELETE_PATH_RE = re.compile(
    r"^(\./|/tmp/)?(dist|build|out|\.next|node_modules|\.cache|cache|tmp|\.tmp|"
    r"coverage|target|\.turbo|\.parcel-cache|\.pytest_cache|__pycache__)(/.*)?$"
)

DESTRUCTIVE_TOKENS = {"dd", "diskutil", "launchctl", "defaults", "fdisk", "parted",
                     "mount", "umount", "kextload", "kextunload"}
MKFS_RE = re.compile(r"^mkfs(\.\w+)?$")
CHMOD_R_RE = re.compile(r"\bchmod\s+-[a-zA-Z]*R[a-zA-Z]*\b")
CHOWN_R_RE = re.compile(r"\bchown\s+-[a-zA-Z]*R[a-zA-Z]*\b")

FETCH_EXEC_RE = re.compile(
    r"\b(curl|wget|fetch|http)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh|ksh|fish|dash)\b"
)

REMOTE_TOOLS = {"ssh", "scp", "rsync", "aws", "gcloud", "vercel", "supabase",
                "doctl", "fly", "heroku", "kubectl", "helm", "ansible", "terraform",
                "pulumi", "render", "railway", "netlify"}

# v2.6.1+: catastrophic-only rule for `gh`. Auto-approves everything except
# delete-class actions (`delete` / `remove` on any subcommand: gh repo delete,
# gh release delete, gh secret delete, gh secret remove, gh extension remove,
# gh issue delete, gh codespace delete, etc.). Per founder: "Unless they're
# very catastrophic, like delete." gh api auto-approves all methods (caller
# can still scope via deny rules in settings.local.json).
GH_CATASTROPHIC_ACTIONS = {"delete", "remove"}
DB_CLI_TOOLS = {"psql", "mysql", "mongo", "mongosh", "redis-cli", "sqlite3", "duckdb"}
NPM_PUBLISH_RE = re.compile(r"\b(npm|yarn|pnpm|bun)\s+publish\b")
DOCKER_PUSH_RE = re.compile(r"\bdocker\s+(push|login)\b")
PIP_PUBLISH_RE = re.compile(r"\b(pip|twine|poetry)\s+(upload|publish)\b")


def first_token(cmd):
    try:
        toks = shlex.split(cmd)
    except ValueError:
        toks = cmd.split()
    return toks[0] if toks else ""


def all_tokens(cmd):
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _git_subcmd(toks):
    if not toks or toks[0] != "git":
        return None
    i = 1
    while i < len(toks):
        t = toks[i]
        if t.startswith("--"):
            if "=" in t:
                i += 1
                continue
            if t in ("--git-dir", "--work-tree", "--namespace", "--super-prefix"):
                i += 2
                continue
            i += 1
            continue
        if t.startswith("-"):
            if t in ("-C", "-c"):
                i += 2
                continue
            i += 1
            continue
        return t
    return None


def is_git_mutation(cmd):
    """v2.6.1+: catastrophic-only. Auto-approve everything except force-push
    (rewrites/destroys remote history) and `clean -f*` (irrecoverably deletes
    untracked files). Reset --hard, branch -D, tag -d, stash drop, etc. are
    all recoverable via reflog and now auto-approve.
    """
    toks = all_tokens(cmd)
    sub = _git_subcmd(toks)
    if sub is None:
        return False
    if sub == "push" and any(f in toks for f in ("--force", "-f", "--force-with-lease")):
        return True
    if sub == "clean" and any(f in toks for f in ("-f", "-fd", "-fdx", "-fx")):
        return True
    return False


def _gh_command_and_action(toks):
    """Return (command, action) for `gh` invocation, skipping global flags.

    Examples:
      ['gh', 'pr', 'list']                      -> ('pr', 'list')
      ['gh', '--repo', 'a/b', 'label', 'list']  -> ('label', 'list')
      ['gh', 'auth', 'status']                  -> ('auth', 'status')
      ['gh']                                    -> (None, None)
      ['gh', 'help']                            -> ('help', None)
    """
    if not toks or toks[0] != "gh":
        return (None, None)
    # Flags that take a value (gh global + common per-command).
    valued_flags = {"--repo", "-R", "--hostname", "--jq", "-q",
                    "--template", "-t"}
    i = 1
    # Resolve command (first non-flag token).
    while i < len(toks):
        t = toks[i]
        if t.startswith("--"):
            if "=" in t:
                i += 1; continue
            if t in valued_flags:
                i += 2; continue
            i += 1; continue
        if t.startswith("-") and len(t) > 1:
            if t in valued_flags:
                i += 2; continue
            i += 1; continue
        break
    if i >= len(toks):
        return (None, None)
    command = toks[i]; i += 1
    # Resolve action (next non-flag token).
    while i < len(toks):
        t = toks[i]
        if t.startswith("--"):
            if "=" in t:
                i += 1; continue
            if t in valued_flags:
                i += 2; continue
            i += 1; continue
        if t.startswith("-") and len(t) > 1:
            if t in valued_flags:
                i += 2; continue
            i += 1; continue
        return (command, t)
    return (command, None)


def is_gh_mutation(cmd):
    """v2.6.1 catastrophic-only rule. Auto-approve every `gh ...` except
    delete-class actions (e.g., `gh repo delete`, `gh release delete`,
    `gh secret delete`, `gh secret remove`, `gh extension remove`,
    `gh codespace delete`, `gh issue delete`). Per founder direction:
    "Unless they're very catastrophic, like delete." `gh api` auto-approves
    all methods (caller can deny via settings.local.json deny rules).
    """
    toks = all_tokens(cmd)
    command, action = _gh_command_and_action(toks)
    if command is None or action is None:
        return False
    return action in GH_CATASTROPHIC_ACTIONS


def is_privilege(cmd):
    return first_token(cmd) in PRIVILEGE_TOKENS


def is_disk_system(cmd):
    t = first_token(cmd)
    if t in DESTRUCTIVE_TOKENS:
        return True
    if MKFS_RE.match(t):
        return True
    if CHMOD_R_RE.search(cmd):
        return True
    if CHOWN_R_RE.search(cmd):
        return True
    return False


def is_recursive_delete(cmd):
    if not RM_RECURSIVE_RE.match(cmd.strip()):
        return False
    toks = all_tokens(cmd)
    paths = [t for t in toks[1:] if not t.startswith("-")]
    if not paths:
        return True
    return not all(SAFE_DELETE_PATH_RE.match(p) for p in paths)


def is_fetch_exec(cmd):
    return bool(FETCH_EXEC_RE.search(cmd))


def is_remote_shared_state(cmd):
    t = first_token(cmd)
    if t == "gh":
        return is_gh_mutation(cmd)
    if t in REMOTE_TOOLS:
        return True
    if t in DB_CLI_TOOLS:
        return True
    if NPM_PUBLISH_RE.search(cmd):
        return True
    if DOCKER_PUSH_RE.search(cmd):
        return True
    if PIP_PUBLISH_RE.search(cmd):
        return True
    return False


def evaluate(cmd):
    if is_git_mutation(cmd):
        return ("git-mutation", "Git history mutation -- repo context user-evaluable")
    if is_privilege(cmd):
        return ("privilege", "Privilege escalation -- auth scope change")
    if is_recursive_delete(cmd):
        return ("recursive-delete", "Recursive delete outside safe-path allowlist")
    if is_disk_system(cmd):
        return ("disk-system", "Disk/system catastrophe pattern")
    if is_fetch_exec(cmd):
        return ("fetch-exec", "Fetch-and-exec pipeline (curl|sh / wget|bash)")
    if is_remote_shared_state(cmd):
        return ("remote-state", "Remote / shared-state mutation")
    return None


def main():
    cmd = sys.stdin.read().rstrip("\n")
    if not cmd.strip():
        print(json.dumps({"prompt": False, "pattern": "Bash(trust-mode-empty)"}))
        return
    result = evaluate(cmd)
    if result:
        cat, reason = result
        print(json.dumps({"prompt": True, "category": cat, "reason": reason}))
    else:
        print(json.dumps({"prompt": False,
                          "pattern": "Bash(trust-mode-auto-approve)"}))


if __name__ == "__main__":
    main()
