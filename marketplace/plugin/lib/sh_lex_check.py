#!/usr/bin/env python3
# sh_lex_check.py — shell-aware safety check for Sutra permission-gate v2.4+
#
# BUILD-LAYER: L0 (fleet)
# Charter: sutra/os/charters/PERMISSIONS.md §4 Tier 1.5
# Plan:    holding/research/2026-04-25-permission-gate-compositional-reads-plan.md
# Review:  codex rounds 1-10 GO (2026-04-25) + Claude plan-eng-review GO
#
# Reads a shell command from stdin. Prints one JSON line to stdout:
#   {"safe": bool, "reason": str, "segments": [[argv], ...], "pattern": str}
#
# Five gates (enforced in order, short-circuit on first failure):
#   Gate 1 — pre-tokenization hard rejects
#   Gate 2 — env shadowing (caller hook responsibility)
#   Gate 3 — shlex tokenize + fold stderr-redirects + reject remaining < > & etc.
#   Gate 4 — segment on allowed pipeline ops (; && || |)
#   Gate 5 — per-primitive argv validation
#
# Fail-safe-to-prompt: every error path prints safe=false so the caller
# falls through to the normal permission dialog. Never auto-denies.

import json
import shlex
import sys

PIPELINE_OPS = {";", "&&", "||", "|"}

HARD_REJECT_SUBSTRINGS = (
    "$(", "`", "<(", ">(", "<<", "bash -c", "sh -c", "zsh -c",
    " eval ", " exec ",
)
HARD_REJECT_STARTS = ("eval ", "exec ")

FORBIDDEN_POST_FOLD_TOKENS = {">", "<", "&", ">>", "<<", ">|", "&>", ">&"}


def hard_reject(cmd):
    for ch in cmd:
        if ord(ch) < 0x20 and ch not in (" ", "\t"):
            return "control-char"
    if "\r" in cmd:
        return "cr-in-command"
    for s in HARD_REJECT_SUBSTRINGS:
        if s in cmd:
            return "forbidden-substring: " + repr(s)
    for s in HARD_REJECT_STARTS:
        if cmd.lstrip().startswith(s):
            return "forbidden-start: " + repr(s)
    return ""


def fold_stderr_redirects(tokens):
    """Codex round 2 fix: shlex splits 2>&1 -> ['2','>&','1'] and
    2>/dev/null -> ['2','>','/dev/null']. Remove these 3-token sequences."""
    out = []
    i = 0
    n = len(tokens)
    while i < n:
        if (i + 2 < n and tokens[i] == '2' and
                tokens[i + 1] == '>&' and tokens[i + 2] == '1'):
            i += 3
            continue
        if (i + 2 < n and tokens[i] == '2' and
                tokens[i + 1] == '>' and tokens[i + 2] == '/dev/null'):
            i += 3
            continue
        out.append(tokens[i])
        i += 1
    return out


def contains_forbidden_ops(tokens):
    for t in tokens:
        if t in FORBIDDEN_POST_FOLD_TOKENS:
            return t
    return ""


def split_segments(tokens):
    segs = [[]]
    for t in tokens:
        if t in PIPELINE_OPS:
            segs.append([])
        else:
            segs[-1].append(t)
    return [s for s in segs if s]


def _deny_flags(argv, bad_prefixes):
    for a in argv:
        for bad in bad_prefixes:
            if a == bad or a.startswith(bad + "="):
                return "bad-flag: " + a
    return ""


# Charter-normative validators. Each comment gives the denylist from
# PERMISSIONS.md §4 Tier 1.5. "-" = no denylist.
def v_ls(argv):       return _deny_flags(argv, ())                                              # charter: -
def v_cat(argv):      return _deny_flags(argv, ())                                              # charter: -
def v_head(argv):     return _deny_flags(argv, ())                                              # charter: -
def v_wc(argv):       return _deny_flags(argv, ())                                              # charter: -
def v_echo(argv):     return ""                                                                 # charter: -
def v_pwd(argv):      return ""                                                                 # charter: -
def v_whoami(argv):   return ""                                                                 # charter: -
def v_which(argv):    return ""                                                                 # charter: -
def v_basename(argv): return ""                                                                 # charter: -
def v_dirname(argv):  return ""                                                                 # charter: -
def v_realpath(argv): return ""                                                                 # charter: -
def v_cut(argv):      return ""                                                                 # charter: -
def v_grep(argv):     return _deny_flags(argv, ("--devices",))                                  # charter: --devices=


def v_printf(argv):
    """printf: reject -v (write to shell var) AND %n directive (bytes-so-far
    write). Allow escaped %%n by stripping %% before checking."""
    for a in argv:
        if a == "-v" or a.startswith("-v="):
            return "bad-flag: -v (writes to shell var)"
        defanged = a.replace("%%", "")
        if "%n" in defanged:
            return "bad-format: %n directive not allowed (write primitive)"
    return ""


def v_date(argv):
    return _deny_flags(argv, ("-s", "--set", "-d", "--date"))


def v_tail(argv):
    bad = ("-F", "--retry")
    for a in argv:
        if a in bad or a.startswith("--follow=name"):
            return "bad-flag: " + a
    return ""


def v_uniq(argv):
    positional = [a for a in argv if not a.startswith("-")]
    if len(positional) > 1:
        return "uniq rejects 2 positional args (second is output file)"
    return ""


def v_tr(argv):
    positional = [a for a in argv if not a.startswith("-")]
    if len(positional) > 2:
        return "tr rejects >2 positional args (file args not allowed)"
    return ""


def v_column(argv):
    return _deny_flags(argv, ("-J",))


VALIDATORS = {
    "ls": v_ls, "cat": v_cat, "head": v_head, "tail": v_tail, "wc": v_wc,
    "echo": v_echo, "printf": v_printf, "pwd": v_pwd, "date": v_date,
    "whoami": v_whoami, "which": v_which, "basename": v_basename,
    "dirname": v_dirname, "realpath": v_realpath,
    "grep": v_grep, "cut": v_cut, "uniq": v_uniq,
    "tr": v_tr, "column": v_column,
}


def result(safe, reason="", segments=None, pattern=""):
    return json.dumps({
        "safe": bool(safe),
        "reason": reason,
        "segments": segments or [],
        "pattern": pattern,
    })


def main():
    cmd = sys.stdin.read().rstrip("\n")
    if not cmd.strip():
        print(result(False, "empty"))
        return

    r = hard_reject(cmd)
    if r:
        print(result(False, r))
        return

    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError as e:
        print(result(False, "lex-error: " + str(e)))
        return

    tokens = fold_stderr_redirects(tokens)

    op = contains_forbidden_ops(tokens)
    if op:
        print(result(False, "forbidden-op: " + op))
        return

    segs = split_segments(tokens)
    if not segs:
        print(result(False, "no-segments"))
        return

    cmd_names = []
    argv_out = []
    for argv in segs:
        if not argv:
            print(result(False, "empty-segment"))
            return
        name = argv[0]
        if name not in VALIDATORS:
            print(result(False, "not-allowlisted: " + name))
            return
        why = VALIDATORS[name](argv[1:])
        if why:
            print(result(False, name + "-rejected: " + why))
            return
        cmd_names.append(name)
        argv_out.append(argv)

    pattern = "Bash(compositional-read:" + "+".join(cmd_names) + ")"
    print(result(True, "", argv_out, pattern))


if __name__ == "__main__":
    main()
