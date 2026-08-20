"""Pattern matching for tool names, repositories and qualifiers.

Three separate matchers because the three things have different shapes:

  tool name   dotted identifier; `*` spans anything
  repository  always `owner/name`; matching is case-insensitive because GitHub
              treats owner and repo names case-insensitively
  qualifier   a path or ref: `/`-separated, so `*` must NOT cross a separator
              and `**` must. This is gitignore's distinction and getting it
              wrong is how `github.get_file(*:**/.env)` stops protecting
              anything below the repository root.
"""
import re
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=2048)
def _compile_flat(pattern: str) -> "re.Pattern":
    """Glob where `*` matches anything, including separators."""
    out = []
    for ch in pattern:
        out.append(".*" if ch == "*" else ("[^/]" if ch == "?" else re.escape(ch)))
    return re.compile("^" + "".join(out) + "$")


@lru_cache(maxsize=2048)
def _compile_path(pattern: str) -> "re.Pattern":
    """Gitignore-style glob.

    `**` crosses separators, `*` does not, `?` matches one non-separator.
    A leading `**/` also matches at depth zero, so `**/.env` matches both
    `.env` and `config/.env` -- the gitignore behaviour, and the one a reader
    of the rule expects.
    """
    body = pattern
    prefix = ""
    if body.startswith("**/"):
        body = body[3:]
        prefix = "(?:.*/)?"

    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "*":
            if body.startswith("**", i):
                # `**/` consumes the separator so it can also match zero segments.
                if body.startswith("**/", i):
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(ch))
        i += 1
    return re.compile("^" + prefix + "".join(out) + "$")


def match_tool(pattern: str, tool_name: str) -> bool:
    """Tool-name match. The pattern must match the FULL name."""
    if pattern == tool_name:
        return True
    if "*" not in pattern:
        return False
    return bool(_compile_flat(pattern).match(tool_name))


def match_repo(pattern: Optional[str], repo: Optional[str]) -> bool:
    """Repository match, case-insensitive.

    A rule with no repo pattern (the bare form) matches every repository.
    A call with no repository -- a connector-wide tool such as
    list_repositories -- is matched only by a bare rule or by `*`, never by a
    rule naming a specific repository. A rule that names a repo cannot
    accidentally authorise a call that has none.
    """
    if pattern is None:
        return True
    if repo is None:
        return pattern == "*"
    if pattern == "*":
        return True
    return bool(_compile_flat(pattern.lower()).match(repo.lower()))


def match_qualifier(pattern: Optional[str], value: Optional[str]) -> bool:
    """Path/ref match.

    A rule with no qualifier matches any value. A rule WITH a qualifier does
    not match a call that supplies none: the rule asked to be specific, so it
    fails closed rather than widening to the whole repository.
    """
    if pattern is None:
        return True
    if value is None:
        return False
    return bool(_compile_path(pattern).match(value))


def match_param(pattern_value: Optional[str], actual) -> bool:
    """Parameter match.

    A parameter the caller omits is never matched, so `Tool(draft:*)` does not
    match a call that leaves `draft` unset. The value is compared against the
    literal input before any normalisation, as Claude Code does.
    """
    if actual is None:
        return False
    if isinstance(actual, bool):
        text = "true" if actual else "false"
    else:
        text = str(actual)
    if pattern_value is None:
        return False
    if "*" not in pattern_value:
        return text == pattern_value
    return bool(_compile_flat(pattern_value).match(text))
