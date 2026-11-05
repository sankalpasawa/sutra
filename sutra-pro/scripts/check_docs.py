#!/usr/bin/env python3
"""Doc check (GAP-DOCS, gap G16): the operator documents must say what the code does.

    scripts/py scripts/check_docs.py                 prints one line per problem and exits 1; "docs check: ok" and exit 0 when clean

It reads docs/GETTING-STARTED.md, docs/OPERATIONS.md, docs/TROUBLESHOOTING.md and docs/ENVIRONMENT.md (the four documents), plus README.md
and docs/DESIGN.md when they exist (commands and links only), and checks:

  commands      every `sutra-pro ...`, `python -m sutra_app ...` or `scripts/run.sh ...` written in a code block or a code span names a real command,
                and every `--flag` in it is in the real `--help` output of that command (help is produced by the real parser, not by a copy).
                A table row whose first cell is such a command is checked the same way against the flags in its other cells.
  coverage      the other way round: every command of the real parser and every flag of every command is documented somewhere in the four documents.
  environment   every name of config.ENV_NAMES, of EngineSettings (engine.spec.ENV_NAMES), the override key, the five SMTP names, the browser and model
                names and every SUTRA_* name found in the source has a row `| `NAME` | ...` in ENVIRONMENT.md; its field name, default, and (engine)
                locked and task flags are the ones the code has.
  failures      TROUBLESHOOTING.md has a `### F<n>` entry per row F<n> of the failure table of docs/design/orchestrator.md, a `### Doctor: `<id>``
                entry per doctor check, and a row per API error code (with its HTTP status) and per connector error code (with its kind).
  links         every relative link `[text](path#anchor)` of the scanned files points at a file or folder that exists and, for a Markdown target,
                at a heading that exists.

Exit status: 0 clean, 1 problems. The checks are importable (`run_checks`, `check_commands`, `check_environment`, `check_troubleshooting`,
`check_links`) so that tests/test_docs.py can feed them broken text.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                        # run by hand with a bare python: the checkout's code first
    sys.path.insert(0, str(ROOT))

DOCS = ("docs/GETTING-STARTED.md", "docs/OPERATIONS.md", "docs/TROUBLESHOOTING.md", "docs/ENVIRONMENT.md")
ALSO_SCANNED = ("README.md", "docs/DESIGN.md")       # commands and links only; skipped when absent
SOURCE_GLOBS = ("sutra_app/**/*.py", "scripts/macos/launcher.sh", "scripts/build_macos_app.py")
NOT_ENV_NAMES = frozenset({"SUTRA_NAMES"})           # a Python constant of ops/envfile.py that looks like a variable
CMD_RE = re.compile(r"^(?:\$\s+)?(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*(sutra-pro|python -m sutra_app|scripts/run\.sh)(?=\s|$)(.*)$")
STOPPERS = frozenset({"|", "||", "&&", ";", ">", ">>", "<", "&", "2>&1"})
FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
NAME_RE = re.compile(r"\bSUTRA_[A-Z0-9]+(?:_[A-Z0-9]+)*\b")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LINK_RE = re.compile(r"(?<!\!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SPAN_RE = re.compile(r"`([^`\n]+)`")
Path_ = tuple[str, ...]


# ---- markdown helpers --------------------------------------------------------------------------------------------------------------

def split_fences(text: str) -> list[tuple[int, str, bool]]:
    """(line number, line, inside a fenced code block) for every line. The fence lines themselves count as inside."""
    out = []
    inside = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            out.append((number, line, True))
            inside = not inside
            continue
        out.append((number, line, inside))
    return out


def slugify(heading: str) -> str:
    """The anchor GitHub makes of a heading: lower case, punctuation dropped, spaces to hyphens."""
    plain = heading.strip().lower().replace("`", "")
    plain = re.sub(r"[^\w\- ]", "", plain)
    return plain.replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    seen: dict[str, int] = {}
    anchors = set()
    for _, line, fenced in split_fences(text):
        match = None if fenced else HEADING_RE.match(line)
        if match:
            slug = slugify(match.group(2))
            n = seen.get(slug, 0)
            seen[slug] = n + 1
            anchors.add(slug if n == 0 else f"{slug}-{n}")
    return anchors


def table_cells(line: str) -> list[str] | None:
    """The cells of a Markdown table row (an escaped `\\|` stays inside its cell), or None for a line that is not a row."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    body = stripped[1:-1].replace("\\|", "\x00")
    return [cell.replace("\x00", "|").strip() for cell in body.split("|")]


def first_span(cell: str) -> str | None:
    match = SPAN_RE.search(cell)
    return match.group(1) if match else None


# ---- the real command line ---------------------------------------------------------------------------------------------------------

class RealCli:
    """The commands of `sutra-pro` as the program itself reports them: the parser tree and the `--help` text."""

    def __init__(self) -> None:
        from sutra_app.ops import cli
        self._cli = cli
        self._parser = cli.build_parser()

    def _parser_of(self, words: Path_):
        if words and words[0] == "serve":
            words = words[1:]
        if not words:
            from sutra_app.main import build_parser
            return build_parser()
        parser = self._parser
        for word in words:
            sub = next((a for a in parser._actions if hasattr(a, "choices") and isinstance(a.choices, dict)), None)
            if sub is None or word not in sub.choices:
                raise KeyError(word)
            parser = sub.choices[word]
        return parser

    def children(self, words: Path_) -> list[str]:
        """The sub-commands at this level; empty for a command that takes none. The root also has `serve`."""
        if words == ("serve",):
            return []
        try:
            parser = self._parser if not words else self._parser_of(words)
        except KeyError:
            return []
        sub = next((a for a in parser._actions if hasattr(a, "choices") and isinstance(a.choices, dict)), None)
        names = list(sub.choices) if sub is not None else []
        return (["serve"] + names) if not words else names

    def help(self, words: Path_) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                if not words or words == ("serve",):
                    self._cli.dispatch(["--help"])
                else:
                    self._cli.main([*words, "--help"])
            except SystemExit:
                pass
        return buf.getvalue()

    def flags(self, words: Path_) -> set[str]:
        """Every `--flag` the command defines, `--help` left out."""
        parser = self._parser_of(words)
        found = {opt for action in parser._actions for opt in action.option_strings if opt.startswith("--")}
        return found - {"--help"}

    def leaves(self) -> list[Path_]:
        """Every command that runs something: `serve` as the empty path, then each leaf of the tree."""
        out: list[Path_] = [()]

        def walk(prefix: Path_) -> None:
            names = self.children(prefix)
            if not names:
                if prefix:
                    out.append(prefix)
                return
            for name in names:
                if name != "serve":
                    walk((*prefix, name))
        walk(())
        return out


# ---- commands ----------------------------------------------------------------------------------------------------------------------

def snippets(text: str) -> Iterator[tuple[int, str]]:
    """(line, text) of every code line of a fenced block and every inline code span outside one."""
    for number, line, fenced in split_fences(text):
        if fenced:
            if not line.lstrip().startswith("```"):
                yield number, line.strip()
            continue
        for span in SPAN_RE.findall(line.replace("\\|", "\x00")):
            yield number, span.replace("\x00", "|")


def parse_command(snippet: str) -> list[str] | None:
    """The words after `sutra-pro` (or its twins) up to a shell operator or a comment, or None when the snippet is not a command."""
    match = CMD_RE.match(snippet.strip())
    if not match:
        return None
    rest = match.group(2)
    try:
        tokens = shlex.split(rest)
    except ValueError:
        tokens = rest.split()
    out = []
    for token in tokens:
        if token in STOPPERS or token.startswith("#"):
            break
        out.append(token)
    return out


def _placeholder(token: str) -> bool:
    return token[:1] in "[<{" or token == "..." or "|" in token


def resolve(cli, tokens: list[str]) -> tuple[Path_, str | None]:
    """(the command path, a problem). Leading words that are not flags walk the command tree; the rest are arguments."""
    words: list[str] = []
    for token in tokens:
        if token.startswith("-") or _placeholder(token):
            break
        names = cli.children(tuple(words))
        if not names:
            break                                    # an argument of a command that takes sub-commands no more
        if token not in names:
            where = "sutra-pro " + " ".join(words) if words else "sutra-pro"
            return tuple(words), f"`{token}` is not a command of `{where.strip()}` (it has: {', '.join(names)})"
        words.append(token)
        if token == "serve":
            words.pop()                              # `serve` is the same as no word
            break
    return tuple(words), None


def check_flags(cli, words: Path_, flags: list[str], where: str) -> list[str]:
    help_text = cli.help(words)
    known = set(FLAG_RE.findall(help_text))
    label = "sutra-pro " + " ".join(words) if words else "sutra-pro"
    return [f"{where}: flag {flag} is not in `{label.strip()} --help`" for flag in flags if flag not in known]


def command_facts(cli, name: str, text: str) -> tuple[list[str], dict[Path_, set[str]], set[Path_]]:
    """(problems, flags documented per command path, command paths documented) for one document."""
    problems: list[str] = []
    documented: dict[Path_, set[str]] = {}
    seen: set[Path_] = set()

    def add(message: str) -> None:
        if message not in problems:
            problems.append(message)

    def take(where: str, tokens: list[str], extra_flags: list[str]) -> None:
        words, problem = resolve(cli, tokens)
        if problem:
            add(f"{where}: {problem}")
            return
        seen.add(words)
        flags = sorted({t.split("=", 1)[0] for t in tokens if re.match(r"--[a-z]", t)} | set(extra_flags))
        for message in check_flags(cli, words, flags, where):
            add(message)
        documented.setdefault(words, set()).update(flags)

    for number, line, fenced in split_fences(text):
        row = None if fenced else table_cells(line)
        head = first_span(row[0]) if row else None
        tokens = parse_command(head) if head else None
        if row and tokens is not None:                   # | `sutra-pro stop` | `--json`, `--wait S` | ... |
            flags = sorted({f for cell in row[1:] for span in SPAN_RE.findall(cell) for f in FLAG_RE.findall(span)})
            take(f"{name}:{number}", tokens, flags)
    for number, snippet in snippets(text):
        tokens = parse_command(snippet)
        if tokens is not None:
            take(f"{name}:{number}", tokens, [])
    return problems, documented, seen


def check_commands(cli, docs: Mapping[str, str]) -> list[str]:
    """Every command and flag written in the documents exists (all scanned files)."""
    problems: list[str] = []
    for name, text in docs.items():
        problems += command_facts(cli, name, text)[0]
    return problems


def check_coverage(cli, docs: Mapping[str, str]) -> list[str]:
    """Every command and every flag of the real program is written down in the four documents."""
    documented: dict[Path_, set[str]] = {}
    seen: set[Path_] = set()
    for name, text in docs.items():
        if name not in DOCS:
            continue
        _, flags, paths = command_facts(cli, name, text)
        seen |= paths
        for path, found in flags.items():
            documented.setdefault(path, set()).update(found)
    problems = []
    for leaf in cli.leaves():
        label = "sutra-pro " + " ".join(leaf) if leaf else "sutra-pro (the server)"
        if leaf not in seen:
            problems.append(f"coverage: the command `{label.strip()}` is not documented (no code span or table row starts with it)")
            continue
        for flag in sorted(cli.flags(leaf) - documented.get(leaf, set())):
            problems.append(f"coverage: the flag {flag} of `{label.strip()}` is not documented")
    return problems


# ---- environment -------------------------------------------------------------------------------------------------------------------

def default_text(value: object) -> str:
    """How ENVIRONMENT.md writes a default: `1`/`0` for a flag, `unset` for nothing, whole numbers without a decimal point."""
    if value is None or value == "":
        return "unset"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _same_default(cell: str, expected: str) -> bool:
    span = first_span(cell)
    if span is None:
        return False
    if span == expected:
        return True
    try:
        return float(span) == float(expected)
    except ValueError:
        return False


def scan_source_names(root: Path) -> set[str]:
    """Every `SUTRA_*` name that the source of the app and its launchers mention."""
    found: set[str] = set()
    for pattern in SOURCE_GLOBS:
        for path in sorted(root.glob(pattern)):
            try:
                found |= set(NAME_RE.findall(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
    return found - NOT_ENV_NAMES


def env_rows(text: str) -> dict[str, list[str]]:
    """`NAME` -> its table row (all cells) for every row of the text whose first cell is exactly one code span."""
    rows: dict[str, list[str]] = {}
    for _, line, fenced in split_fences(text):
        cells = None if fenced else table_cells(line)
        if cells and re.fullmatch(r"`[A-Za-z][A-Za-z0-9_]*`", cells[0]):
            rows[cells[0].strip("`")] = cells
    return rows


def check_environment(text: str, root: Path = ROOT, name: str = "docs/ENVIRONMENT.md") -> list[str]:
    from sutra_app.config import ENV_NAMES as APP_NAMES, OVERRIDE_KEY_NAME, Settings
    from sutra_app.engine.paths import SMTP_VARS
    from sutra_app.engine.spec import ENV_NAMES as ENGINE_NAMES, LOCKED_FIELDS, TASK_SETTING_KEYS, EngineSettings
    from sutra_app.connectors.claude import MODEL_ENV_NAMES
    from sutra_app.ops.browser import BROWSER_APP_ENV

    rows = env_rows(text)
    problems: list[str] = []

    def need(var: str) -> list[str] | None:
        if var not in rows:
            problems.append(f"{name}: the variable {var} has no row (| `{var}` | ...)")
            return None
        return rows[var]

    for field, var in APP_NAMES.items():
        row = need(var)
        if row is None:
            continue
        if len(row) < 3 or first_span(row[1]) != field:
            problems.append(f"{name}: {var} must name the field `{field}` in its second cell")
            continue
        info = Settings.model_fields[field]
        if info.is_required() or info.default_factory is not None:
            continue                                                   # the default is computed (a path, a random token)
        expected = default_text(info.default)
        if not _same_default(row[2], expected):
            problems.append(f"{name}: {var} default is `{expected}` in the code, the document says {row[2]!r}")
    for field in EngineSettings.model_fields:
        var = ENGINE_NAMES[field]
        row = need(var)
        if row is None:
            continue
        if len(row) < 6 or first_span(row[1]) != field:
            problems.append(f"{name}: {var} must name the field `{field}` in its second cell and have the columns Default, Locked, Task")
            continue
        expected = default_text(EngineSettings.model_fields[field].default)
        if not _same_default(row[2], expected):
            problems.append(f"{name}: {var} default is `{expected}` in the code, the document says {row[2]!r}")
        for label, cell, truth in (("Locked", row[3], field in LOCKED_FIELDS), ("Task", row[4], ENGINE_NAMES[field] in TASK_SETTING_KEYS)):
            if cell.strip().lower() != ("yes" if truth else "no"):
                problems.append(f"{name}: {var} column {label} must be {'yes' if truth else 'no'}, the document says {cell!r}")
    for var in (OVERRIDE_KEY_NAME, *SMTP_VARS, BROWSER_APP_ENV, *MODEL_ENV_NAMES):
        need(var)
    for var in sorted(scan_source_names(root)):
        need(var)
    return list(dict.fromkeys(problems))


# ---- troubleshooting ---------------------------------------------------------------------------------------------------------------

def failure_codes(root: Path = ROOT) -> list[str]:
    """F1, F2, ... as the failure table of the orchestrator design lists them (F1 to F10 when the file cannot be read)."""
    try:
        text = (root / "docs/design/orchestrator.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    codes = re.findall(r"^\| (F\d+) \|", text, flags=re.M)
    return codes or [f"F{n}" for n in range(1, 11)]


def check_troubleshooting(text: str, root: Path = ROOT, name: str = "docs/TROUBLESHOOTING.md") -> list[str]:
    from sutra_app.connectors.errors import ERROR_CLASSES
    from sutra_app.ops.doctor import CHECK_IDS
    from sutra_app.orchestrator.errors import STATUS_BY_CODE

    problems: list[str] = []
    headings = [m.group(2) for _, line, fenced in split_fences(text) if not fenced and (m := HEADING_RE.match(line))]
    for code in failure_codes(root):
        if not any(re.match(rf"{code}\b", h) for h in headings):
            problems.append(f"{name}: there is no entry `### {code} ...` for the failure {code}")
    for check_id in CHECK_IDS:
        if not any(re.fullmatch(rf"Doctor:\s*`{check_id}`", h) for h in headings):
            problems.append(f"{name}: there is no entry `### Doctor: `{check_id}`` for the doctor check {check_id}")
    api: dict[str, str] = {}
    conn: dict[str, str] = {}
    for _, line, fenced in split_fences(text):
        cells = None if fenced else table_cells(line)
        if cells and len(cells) >= 2 and re.fullmatch(r"`[a-z_]+`", cells[0]):
            (api if cells[1].isdigit() else conn)[cells[0].strip("`")] = cells[1]
    for code, status in STATUS_BY_CODE.items():
        if code not in api:
            problems.append(f"{name}: the API error code `{code}` has no row (| `{code}` | {status} | ...)")
        elif api[code] != str(status):
            problems.append(f"{name}: the API error code `{code}` is HTTP {status} in the code, the document says {api[code]}")
    for code, cls in ERROR_CLASSES.items():
        if code not in conn:
            problems.append(f"{name}: the connector error code `{code}` has no row (| `{code}` | {cls.kind} | ...)")
        elif conn[code] != cls.kind:
            problems.append(f"{name}: the connector error code `{code}` is kind {cls.kind} in the code, the document says {conn[code]}")
    return problems


# ---- links -------------------------------------------------------------------------------------------------------------------------

def check_links(name: str, text: str, root: Path = ROOT, read: Callable[[Path], str] | None = None) -> list[str]:
    """Relative links of one document: the target must exist and a `#anchor` must be a heading of a Markdown target."""
    read = read or (lambda p: p.read_text(encoding="utf-8"))
    problems: list[str] = []
    here = (root / name).parent
    own = anchors_of(text)
    for number, line, fenced in split_fences(text):
        if fenced:
            continue
        for target in LINK_RE.findall(re.sub(r"`[^`\n]*`", "", line)):
            if re.match(r"[a-z][a-z0-9+.-]*:", target, flags=re.I):
                continue                                                # http:, https:, mailto:
            path_part, _, fragment = target.partition("#")
            where = f"{name}:{number}"
            if not path_part:
                if fragment and fragment not in own:
                    problems.append(f"{where}: dead link {target}: no heading `{fragment}` in this document")
                continue
            resolved = (here / path_part).resolve()
            if not resolved.exists():
                problems.append(f"{where}: dead link {target}: {path_part} does not exist")
            elif fragment and resolved.is_file() and resolved.suffix == ".md":
                try:
                    if fragment not in anchors_of(read(resolved)):
                        problems.append(f"{where}: dead link {target}: no heading `{fragment}` in {path_part}")
                except OSError:
                    problems.append(f"{where}: dead link {target}: {path_part} cannot be read")
    return problems


# ---- the whole check ---------------------------------------------------------------------------------------------------------------

def load_docs(root: Path, overrides: Mapping[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    docs: dict[str, str] = {}
    problems: list[str] = []
    for name in (*DOCS, *ALSO_SCANNED):
        if overrides and name in overrides:
            docs[name] = overrides[name]
            continue
        path = root / name
        if not path.is_file():
            if name in DOCS:
                problems.append(f"{name}: the document is missing")
            continue
        docs[name] = path.read_text(encoding="utf-8")
    return docs, problems


def run_checks(root: Path = ROOT, overrides: Mapping[str, str] | None = None, cli=None) -> list[str]:
    """All problems, in a stable order. `overrides` replaces the text of named documents (the tests' way to feed broken text)."""
    docs, problems = load_docs(root, overrides)
    cli = cli or RealCli()
    problems += check_commands(cli, docs)
    problems += check_coverage(cli, docs)
    if "docs/ENVIRONMENT.md" in docs:
        problems += check_environment(docs["docs/ENVIRONMENT.md"], root)
    if "docs/TROUBLESHOOTING.md" in docs:
        problems += check_troubleshooting(docs["docs/TROUBLESHOOTING.md"], root)
    for name, text in docs.items():
        problems += check_links(name, text, root)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that the operator documents match the code (commands, flags, environment, failures, links).")
    parser.add_argument("--root", type=Path, default=ROOT, help="the checkout to check (default: this one)")
    args = parser.parse_args(argv)
    problems = run_checks(args.root.resolve())
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        print(f"docs check: {len(problems)} problem(s)")
        return 1
    print(f"docs check: ok ({len(DOCS)} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
