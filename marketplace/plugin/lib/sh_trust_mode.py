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

REMOTE_TOOLS = {"ssh", "scp", "rsync", "aws", "gcloud", "vercel", "supabase",
                "doctl", "fly", "heroku", "kubectl", "helm", "ansible", "terraform",
                "pulumi", "render", "railway", "netlify"}

# `gh` (GitHub CLI) is handled separately: read-only subcommands auto-approve,
# mutations prompt. Mirrors the `git` mutation-detection model.
# Action-level mutations indexed by top-level command. Read-only commands
# (label, status without args, search, browse, ...) and read actions for
# command groups below (list, view, status, diff, checks, ...) auto-approve.
GH_MUTATION_ACTIONS = {
    "repo":      {"create", "delete", "fork", "rename", "transfer", "archive",
                  "unarchive", "edit", "deploy-key", "set-default", "sync"},
    "pr":        {"create", "edit", "close", "reopen", "merge", "ready", "review",
                  "checkout", "comment", "lock", "unlock"},
    "issue":     {"create", "edit", "close", "reopen", "comment", "delete",
                  "transfer", "lock", "unlock", "pin", "unpin"},
    "release":   {"create", "edit", "delete", "upload"},
    "gist":      {"create", "edit", "delete", "rename", "clone"},
    "secret":    {"set", "delete", "remove"},
    "variable":  {"set", "delete", "remove"},
    "auth":      {"login", "logout", "refresh", "setup-git", "switch"},
    "workflow":  {"enable", "disable", "run"},
    "run":       {"cancel", "delete", "rerun"},
    "codespace": {"create", "delete", "stop", "rebuild", "edit", "ssh", "code", "cp"},
    "project":   {"create", "edit", "delete", "close", "copy",
                  "field-create", "field-delete",
                  "item-add", "item-archive", "item-create", "item-delete",
                  "item-edit"},
    "label":     {"create", "edit", "delete", "clone"},
    "alias":     {"set", "delete", "import"},
    "extension": {"install", "remove", "upgrade", "create"},
    "config":    {"set", "clear-cache"},
    "gpg-key":   {"add", "delete"},
    "ssh-key":   {"add", "delete"},
    "ruleset":   {"create", "edit", "delete"},
    "cache":     {"delete"},
    "attestation": {"verify"},
}
# Top-level commands where ANY action is treated as mutation (no safe subcmds).
GH_MUTATION_COMMANDS = set()
# Mutation HTTP methods for `gh api`.
GH_API_MUTATION_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
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


def _gh_api_is_mutation(toks):
    """gh api defaults to GET. Mutation only when --method/-X selects POST/PUT/DELETE/PATCH."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ("--method", "-X") and i + 1 < len(toks):
            if toks[i + 1].upper() in GH_API_MUTATION_METHODS:
                return True
            i += 2; continue
        if t.startswith("--method="):
            if t.split("=", 1)[1].upper() in GH_API_MUTATION_METHODS:
                return True
        if t.startswith("-X") and len(t) > 2:
            if t[2:].upper() in GH_API_MUTATION_METHODS:
                return True
        i += 1
    return False


def is_gh_mutation(cmd):
    """True if `gh ...` invokes a write/state-changing subcommand.

    Mirrors is_git_mutation: defaults to NOT-mutation (auto-approve);
    explicit mutating actions/commands listed in GH_MUTATION_ACTIONS.
    """
    toks = all_tokens(cmd)
    command, action = _gh_command_and_action(toks)
    if command is None:
        return False
    if command == "api":
        return _gh_api_is_mutation(toks)
    if command in GH_MUTATION_COMMANDS:
        return True
    actions = GH_MUTATION_ACTIONS.get(command)
    if actions is None:
        return False
    if action is None:
        return False
    return action in actions


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
