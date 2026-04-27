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

GIT_MUTATION_SUBCMDS = {"commit", "push", "pull", "rebase", "merge", "rm", "mv"}
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

REMOTE_TOOLS = {"gh", "ssh", "scp", "rsync", "aws", "gcloud", "vercel", "supabase",
                "doctl", "fly", "heroku", "kubectl", "helm", "ansible", "terraform",
                "pulumi", "render", "railway", "netlify"}
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
    toks = all_tokens(cmd)
    sub = _git_subcmd(toks)
    if sub is None:
        return False
    if sub in GIT_MUTATION_SUBCMDS:
        return True
    if sub == "reset" and "--hard" in toks:
        return True
    if sub == "checkout":
        if "--" in toks:
            return False
        return True
    if sub == "push" and any(f in toks for f in ("--force", "-f", "--force-with-lease")):
        return True
    if sub == "stash" and len(toks) > 2 and "drop" in toks:
        return True
    if sub == "branch" and any(f in toks for f in ("-D", "-d", "--delete")):
        return True
    if sub == "tag" and "-d" in toks:
        return True
    if sub == "clean" and any(f in toks for f in ("-f", "-fd", "-fdx", "-fx")):
        return True
    return False


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
