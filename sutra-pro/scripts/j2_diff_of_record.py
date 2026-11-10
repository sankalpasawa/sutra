#!/usr/bin/env python3
"""The difference of record between `prototypes/j2` and Sutra Pro as committed (J2 sync 4, lane V0).

    scripts/py scripts/j2_diff_of_record.py                           # print the report; exit 0 (2 when the arguments are wrong)
    scripts/py scripts/j2_diff_of_record.py --check                   # the same report; exit 0 only when nothing is left to decide or take
    scripts/py scripts/j2_diff_of_record.py --source DIR --commit ID  # an extraction you made yourself

The one reference is the folder `prototypes/j2` of this repository, at a commit. There is no second reference: no other repository
and no earlier baseline. `--source` is an extraction of that folder, made with

    git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C <new empty folder>

(never a working tree: an edited file or a `.pyc` cannot be vendored; a folder that holds a `.git` is refused). Without `--source`
the script makes the same extraction from `--commit` (default: the commit VENDORED.md names while its folder is the one HEAD has,
else the last commit that touched the folder on HEAD) into a temporary folder and removes it afterwards. `--commit` is the label the two scripts below write into what they build.

What it does, in this order:

  1. lists every file of the source and gives each one a class:
       vendored   named in the Files table of `sutra_app/engine/VENDORED.md` (the table `scripts/vendor_j2.py` writes; it names every
                  J2 path the script vendored, so this script imports nothing from it)
       page       a file `scripts/port_j2_ui.py` turns into the department page, its two harnesses or the vendored d3
       legacy     a J2 test script that has a copy in `tests/engine/legacy/`
       excluded   not carried, with a reason from the table EXCLUDED below (the reason is the decision; an empty one counts as none)
       unlisted   of a kind the vendor script carries (a code module, a seed file, a reference doc...) but not in the table yet:
                  a new J2 file nobody has vendored
       undecided  none of the above: a new J2 file nobody decided about
     and a status against the committed tree: identical (byte for byte), patched (equals what the numbered patches make of the J2
     file the copy was built from: the J2 sha256 recorded in VENDORED.md), edited (a legacy copy: Sutra edits those on purpose),
     differs (J2's file is not the one the copy was built from), missing (nothing in Sutra Pro), unverified (a generated page file
     while the port check does not pass);
  2. runs `scripts/vendor_j2.py --source <folder> --commit <id> --check` and `scripts/port_j2_ui.py --j2 <folder> --check` as
     subprocesses and reports what they say. A build that stops (an anchor that no longer matches) is reported as that, never hidden;
  3. prints a markdown report: the two checks, counts per class and status, the lists of differing, missing and stale files, and the
     exclusion table with its reasons.

`--check` exits 0 only when both checks pass AND every source file is vendored, generated, a legacy copy, or excluded with a reason,
so a new J2 file nobody decided about fails loudly. The statuses are evidence for a reader; the verdict is the two checks (they
rebuild the files and compare bytes) and the classification.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parent.parent          # the sutra-pro folder
J2_FOLDER = "prototypes/j2"                             # relative to the root of the repository that holds sutra-pro
VENDORED_MD = "sutra_app/engine/VENDORED.md"
VENDOR_SCRIPT = "scripts/vendor_j2.py"
PORT_SCRIPT = "scripts/port_j2_ui.py"
LEGACY_DIR = "tests/engine/legacy"
LEGACY_NAMES = ("j2_flow_test.py", "change_test.py", "realization_test.py", "j2_replay_size.py")
# the folders `vendor_j2.py` manages: a file in one of them that VENDORED.md does not name is stale
MANAGED = ("sutra_app/engine/agents", "sutra_app/engine/conditions", "sutra_app/engine/artifacts", "sutra_app/engine/templates",
           "sutra_app/engine/seed", "docs/reference/j2")
# what `port_j2_ui.py` writes from a J2 file: J2 path -> (path in sutra-pro, "edited" by the port's numbered edits | "verbatim")
PAGE_FILES = {
    "j2_ui.html": ("sutra_app/ui/pages/j2_ui.html", "edited"),
    "j2_ui_render.js": ("sutra_app/ui/pages/j2_ui_render.js", "edited"),
    "j2_graph_layout.js": ("sutra_app/ui/pages/j2_graph_layout.js", "edited"),
    "vendor/d3.min.js": ("sutra_app/ui/static/vendor/d3.min.js", "verbatim"),
    "vendor/d3-LICENSE": ("sutra_app/ui/static/vendor/d3-LICENSE", "verbatim"),
    "vendor/README.md": ("sutra_app/ui/static/vendor/README.md", "verbatim"),
}
IGNORED_NAMES = frozenset({"__pycache__", ".DS_Store"})

CLASSES = ("vendored", "page", "legacy", "excluded", "unlisted", "undecided")
ACCEPTED = frozenset({"vendored", "page", "legacy", "excluded"})       # classes that count as decided
STATUSES = ("identical", "patched", "edited", "differs", "unverified", "missing", "n/a")
SLOW_SECONDS = 600


class ToolError(Exception):
    """The arguments or the inputs are wrong (exit 2); not a finding."""


# ---- the exclusions ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Exclusion:
    pattern: str        # fnmatch against the path inside prototypes/j2; `*` also crosses `/`; the first match in the table wins
    group: str          # the heading the report lists it under
    reason: str         # why Sutra Pro does not carry it: the decision itself (empty = not decided)
    recorded: str       # where else it is written down (VENDORED.md 'Not vendored', design 7.4 of docs/design/j2-sync-4.md)


# Where else an exclusion is written down: "engine design 3.2" is docs/design/engine.md section 3.2 (Left out) and 3.3 (rewritten files),
# "VENDORED.md" its 'Not vendored' text, "design 7.4" docs/design/j2-sync-4.md section 7.4, "D91" the decision about excluded J2 material.
_STUDIO = ("J2's older three-agent studio (a stdlib server, its page and a mock site): not part of J2's loop, since no J2 module of the "
           "loop imports it, and nothing in Sutra imports or reads these files. Sutra serves the department page and J2's routes itself.")
_STUDIO_AT = "VENDORED.md; engine design 3.2; design 7.4; D91"
_STUDIO_ROLES = ("role files of the older studio (product, design, development, team): not the J2 team's roles, which are "
                 "agents/j2/*, and no engine code reads them.")
_STUDIO_ROLES_AT = "VENDORED.md; engine design 3.2 (design 7.4 does not name the four role files)"
_BUDGET = ("J2's budget-conflict demo (its own script, server, page and scenario files): not the J2 run flow, and nothing in Sutra "
           "uses it.")
_BUDGET_AT = "VENDORED.md; engine design 3.2; design 7.4; D91"
_SERVER = ("replaced: engine/views.py holds the one implementation of the routes (D25), engine/api serves them and "
           "sutra_app/engine/j2_server.py (Sutra's own file of the same name) is the stdlib adapter. What a J2 change adds "
           "arrives as routes and views, never as a copy of this file.")
_SERVER_AT = "VENDORED.md ('j2_server.py (WP E2)'); engine design 3.3 (rewritten); design 7.4"
_LLM = ("replaced: sutra_app/engine/llm.py is Sutra's own seam (J2's call syntax over the ModelPort, D17). J2's llm.py holds J2's own "
        "model providers; vendoring it would put a second way to a model beside the connector layer.")
_LLM_AT = "engine design 3.3 (rewritten on the ModelPort); VENDORED.md 'Not vendored' and design 7.4 do not name it"
_PLACEHOLDERS = ("never read: j2.py's _placeholders() only checks the live role files for the word PLACEHOLDER. The vendor script copies "
                 "the ten role files that are read.")
_PLACEHOLDERS_AT = "VENDORED.md; engine design 3.2"
_ENV = ("J2's own environment template (API keys and switches of its scripts). Sutra's settings are in docs/ENVIRONMENT.md and its model "
        "calls go through the connector layer, with no model API keys (D7).")
_IGNORE = "J2's ignore rules for its own folder; Sutra Pro has its own."
_REQS = "J2's pip list (anthropic, google-genai, python-docx, pydantic); Sutra's dependencies are in pyproject.toml."
_CHECKS = ("J2's runner for its flow test in two throwaway copies of its folder; the gate for the legacy copies in Sutra Pro is "
           "scripts/engine_gate.sh.")
_SHOT = "a screenshot of J2's page at the top of its folder; no file in the folder refers to it."
_DEV_AT = "engine design 3.2 (VENDORED.md says only 'the IDE and environment files'; design 7.4 does not name it)"
_MOCKS = ("HTML mock-ups of screens that are ported (the Artifacts groups, Run settings): design sketches, not engine or page code.")
_MOCKS_AT = "VENDORED.md ('docs/mocks/*.html'); design 7.4 names two of the three mocks"
_SOLAR = "an HTML mock of the team view as a solar system: a design sketch, not code."
_SOLAR_AT = ("VENDORED.md ('docs/mocks/*.html'); design 7.4 does not name it; D91 says it is kept as reference under "
             "docs/reference/j2/, but the vendor script does not carry it (a disagreement)")
_SUDOKU = ("a one-off comparison write-up with its HTML, PDF and PNG renders (the Sudoku runs): not read by any code, not a "
           "reference the engine needs.")
_SUDOKU_AT = ("engine design 3.2 (docs/*.html, docs/*.png, docs/*.pdf); D91 says explainer pages are kept as reference under "
              "docs/reference/j2/, but the vendor script does not carry them (a disagreement)")
_BUILD_ON_RUN = "a design with no code behind it (552 lines); no J2 file mentions it. The follow-up waits for J2 to ship the code."
_DOC_HTML = ("rendered explainers and trace pages of J2's design work (adaptation walkthrough, certainty flow, design-stage trace, "
             "realization brief...): not read by any code. The Markdown references that matter are carried in docs/reference/j2.")
_DOC_HTML_AT = ("engine design 3.2 (docs/*.html); D91 says the explainer pages are kept as reference under docs/reference/j2/, but "
                "the vendor script does not carry them (a disagreement)")
_DOC_FLOW = ("the picture of the J2 flow that J2's README points to (docs/j2-flow.jpg): an image, not code. The vendored README "
             "therefore points at a file Sutra Pro does not carry.")
_DOC_FLOW_AT = ("engine design 3.2 (docs/*.jpg); D91 says the flow picture is kept as reference under docs/reference/j2/, but the "
                "vendor script does not carry it (a disagreement)")
_DOC_IMAGES = ("screenshots of J2's Simple view and of its studio view (docs/ui-simple-*.png, docs/ui-studio-*.png): images, not code. "
               "J2's README points at them, so the vendored README shows no pictures; the legacy flow test copies "
               "ui-simple-start-390.png as a stand-in file and Sutra's copy generates a plain PNG instead.")
_DOC_IMAGES_AT = "engine design 3.2 (docs/*.png, docs/*.jpg)"
_DOC_PDF = "rendered PDF documents of J2's design work: not read by any code."
_DOC_PDF_AT = "engine design 3.2 (docs/*.pdf)"
_DOC_PICTURE = ("the Graphviz source and the SVG render of realization-axis.md. The vendored realization-axis.md names the .dot "
                "file as its picture, so that reference is dead in Sutra Pro.")
_DOC_PICTURE_AT = "none: engine design 3.2 lists html, png, jpg and pdf only (D91's 'explainer pages' may mean these too)"

EXCLUDED: tuple[Exclusion, ...] = (
    Exclusion("studio.py", "older studio", _STUDIO, _STUDIO_AT),
    Exclusion("server.py", "older studio", _STUDIO, _STUDIO_AT),
    Exclusion("ui.html", "older studio", _STUDIO, _STUDIO_AT),
    Exclusion("mock_site.py", "older studio", _STUDIO, _STUDIO_AT),
    Exclusion("agents/product.md", "older studio agents", _STUDIO_ROLES, _STUDIO_ROLES_AT),
    Exclusion("agents/design.md", "older studio agents", _STUDIO_ROLES, _STUDIO_ROLES_AT),
    Exclusion("agents/development.md", "older studio agents", _STUDIO_ROLES, _STUDIO_ROLES_AT),
    Exclusion("agents/team.md", "older studio agents", _STUDIO_ROLES, _STUDIO_ROLES_AT),
    Exclusion("negotiate.py", "budget-conflict demo", _BUDGET, _BUDGET_AT),
    Exclusion("negotiate_server.py", "budget-conflict demo", _BUDGET, _BUDGET_AT),
    Exclusion("negotiate_ui.html", "budget-conflict demo", _BUDGET, _BUDGET_AT),
    Exclusion("scenarios/*", "budget-conflict demo", _BUDGET, _BUDGET_AT),
    Exclusion("j2_server.py", "replaced by Sutra's own code", _SERVER, _SERVER_AT),
    Exclusion("llm.py", "replaced by Sutra's own code", _LLM, _LLM_AT),
    Exclusion("agents/j2/_placeholders/*", "placeholders", _PLACEHOLDERS, _PLACEHOLDERS_AT),
    Exclusion(".env.example", "J2 development files", _ENV, _DEV_AT),
    Exclusion(".gitignore", "J2 development files", _IGNORE, _DEV_AT),
    Exclusion("requirements.txt", "J2 development files", _REQS, _DEV_AT),
    Exclusion("run_checks.sh", "J2 development files", _CHECKS, _DEV_AT),
    Exclusion("screenshot.png", "J2 development files", _SHOT, _DEV_AT),
    Exclusion("docs/mocks/team-solar-mock.html", "solar mock", _SOLAR, _SOLAR_AT),
    Exclusion("docs/mocks/*", "mocks", _MOCKS, _MOCKS_AT),
    Exclusion("docs/sudoku-comparison/*", "sudoku comparison", _SUDOKU, _SUDOKU_AT),
    Exclusion("docs/build-on-run-design.md", "build-on-run design", _BUILD_ON_RUN, "VENDORED.md; design 7.4"),
    Exclusion("docs/*.html", "design docs (HTML)", _DOC_HTML, _DOC_HTML_AT),
    Exclusion("docs/j2-flow.jpg", "flow picture", _DOC_FLOW, _DOC_FLOW_AT),
    Exclusion("docs/*.png", "doc images", _DOC_IMAGES, _DOC_IMAGES_AT),
    Exclusion("docs/*.jpg", "doc images", _DOC_IMAGES, _DOC_IMAGES_AT),
    Exclusion("docs/*.pdf", "design docs (PDF)", _DOC_PDF, _DOC_PDF_AT),
    Exclusion("docs/*.svg", "diagram picture", _DOC_PICTURE, _DOC_PICTURE_AT),
    Exclusion("docs/*.dot", "diagram picture", _DOC_PICTURE, _DOC_PICTURE_AT),
)


def exclusion_for(path: str, table: Sequence[Exclusion] = EXCLUDED) -> Exclusion | None:
    """The first exclusion whose pattern matches `path`, or None."""
    return next((e for e in table if fnmatch.fnmatchcase(path, e.pattern)), None)


# ---- VENDORED.md --------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Row:
    """One row of the Files table: the vendored path, the J2 path, the patch ids, the J2 sha256 the copy was built from, the copy's."""
    vendored: str
    j2: str
    patches: str
    j2_sha: str
    vendored_sha: str

    @property
    def patched(self) -> bool:
        return self.patches.strip() not in ("", "-")


ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \| ([^|]+?) \| `([0-9a-f]{64})` \| `([0-9a-f]{64})` \|")


def parse_vendored_md(text: str) -> list[Row]:
    return [Row(*m.groups()) for line in text.splitlines() if (m := ROW.match(line))]


def names_commit(text: str, commit: str) -> bool:
    """True when the part of VENDORED.md above its patch table (its header) names `commit` in full or by its first seven characters."""
    header = text.split("\n## ", 1)[0]
    return bool(commit) and (commit in header or commit[:7] in header)


def vendored_commit(text: str, has_tree=lambda commit: False) -> str | None:
    """The first full commit id in the header of VENDORED.md for which `has_tree(id)` holds (a commit of this repository whose
    prototypes/j2 exists): the commit the vendored copy says it was built from. None when there is none."""
    header = text.split("\n## ", 1)[0]
    for found in re.findall(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", header):
        if has_tree(found):
            return found
    return None


# ---- the path rules ------------------------------------------------------------------------------------------------------------------
def kind_of_vendored(dest: str) -> str:
    if dest.startswith("sutra_app/engine/seed/"):
        return "seed library"
    if dest.startswith("sutra_app/engine/agents/"):
        return "role file"
    if dest.startswith("sutra_app/engine/conditions/"):
        return "condition"
    if dest == "sutra_app/engine/artifacts/types.json":
        return "artifact types"
    if dest.startswith("sutra_app/engine/templates/"):
        return "generic template"
    if dest.startswith("docs/reference/j2/"):
        return "reference doc"
    if re.fullmatch(r"sutra_app/engine/[^/]+\.py", dest):
        return "code module"
    return "other"


def slot_of(path: str) -> tuple[str, str] | None:
    """Where a J2 file of a kind the vendor script carries would live (sutra-pro path, kind), for a file VENDORED.md does not name:
    the same path rules the script follows, written here once for the report. None for a path no rule covers."""
    parts = PurePosixPath(path).parts
    if len(parts) == 1 and re.fullmatch(r"j2(_[a-z0-9]+)*\.py", path) and not path.endswith("_test.py"):
        return f"sutra_app/engine/{path}", "code module"
    if parts[:2] == ("agents", "j2") and len(parts) == 3:
        return f"sutra_app/engine/{path}", "role file"
    if parts[0] == "conditions" and len(parts) == 2:
        return f"sutra_app/engine/{path}", "condition"
    if path == "artifacts/types.json":
        return f"sutra_app/engine/{path}", "artifact types"
    if parts[0] == "templates" and len(parts) == 3 and parts[2] == "generic.json":
        return f"sutra_app/engine/{path}", "generic template"
    if parts[0] == "library":
        return f"sutra_app/engine/seed/{path}", "seed library"
    if path in ("README.md", "SETUP.md") or parts[0] == "docs":
        return f"docs/reference/j2/{path}", "reference doc"
    return None


# ---- the classification --------------------------------------------------------------------------------------------------------------
@dataclass
class Entry:
    path: str                   # inside prototypes/j2
    cls: str                    # one of CLASSES
    kind: str                   # code module, seed library, ...; the exclusion group for an excluded file
    status: str = ""            # one of STATUSES once measured
    counterpart: str = ""       # the path in sutra-pro it is compared with ("" when there is none)
    note: str = ""
    reason: str = ""            # an excluded file's reason
    recorded: str = ""          # where an exclusion is also written down
    pattern: str = ""           # the pattern of EXCLUDED that matched
    gap: int | None = None      # an edited copy: how many non-blank J2 lines are absent from it

    @property
    def decided(self) -> bool:
        return self.cls in ACCEPTED


@dataclass
class Context:
    root: Path                              # the sutra-pro folder compared with
    rows: dict[str, Row]                    # Files table of VENDORED.md by J2 path
    legacy: frozenset[str]                  # J2 test scripts that have (or should have) a copy in tests/engine/legacy
    excluded: Sequence[Exclusion] = EXCLUDED

    @classmethod
    def load(cls, root: Path, excluded: Sequence[Exclusion] = EXCLUDED) -> "Context":
        md = root / VENDORED_MD
        if not md.is_file():
            raise ToolError(f"{VENDORED_MD} is missing under the sutra-pro folder: nothing says what is vendored")
        rows: dict[str, Row] = {}
        for row in parse_vendored_md(md.read_text(encoding="utf-8")):
            rows.setdefault(row.j2, row)
        if not rows:
            raise ToolError(f"{VENDORED_MD} has no Files table")
        folder = root / LEGACY_DIR
        on_disk = {p.name for p in folder.glob("*.py")} if folder.is_dir() else set()
        return cls(root, rows, frozenset(LEGACY_NAMES) | on_disk, excluded)


def decide(path: str, ctx: Context) -> Entry:
    """The class of one J2 file, from its path alone (no bytes read): the order is VENDORED.md, the generated page, a legacy copy, an
    exclusion with a reason, a kind the vendor script carries (unlisted), and then undecided."""
    row = ctx.rows.get(path)
    if row:
        return Entry(path, "vendored", kind_of_vendored(row.vendored), counterpart=row.vendored)
    if path in PAGE_FILES:
        dest, how = PAGE_FILES[path]
        return Entry(path, "page", "page" if how == "edited" else "page asset", counterpart=dest)
    if "/" not in path and path in ctx.legacy:
        return Entry(path, "legacy", "legacy test copy", counterpart=f"{LEGACY_DIR}/{path}")
    exclusion = exclusion_for(path, ctx.excluded)
    if exclusion is not None:
        if exclusion.reason.strip():
            return Entry(path, "excluded", exclusion.group, "n/a", reason=exclusion.reason, recorded=exclusion.recorded,
                         pattern=exclusion.pattern)
        return Entry(path, "undecided", "excluded without a reason", "n/a", note=f"matches the exclusion {exclusion.pattern!r}, which has no reason")
    slot = slot_of(path)
    if slot is not None:
        return Entry(path, "unlisted", slot[1], counterpart=slot[0], note="of a kind the vendor script carries, but not in the Files table of VENDORED.md")
    return Entry(path, "undecided", "unknown", "n/a", note="no row in VENDORED.md, not a generated page file, no legacy copy, no exclusion")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def line_gap(j2: bytes, copy: bytes) -> int:
    """How many non-blank lines of the J2 file are not a line of the copy: a handful for a copy that carries only Sutra's own edits."""
    have = set(copy.decode("utf-8", "replace").splitlines())
    return sum(1 for line in j2.decode("utf-8", "replace").splitlines() if line.strip() and line not in have)


def measure(entry: Entry, data: bytes, ctx: Context, port_ok: bool | None) -> None:
    """Fill in `status`, `note` and `gap` of a decided or unlisted entry from the J2 bytes and the committed counterpart."""
    if entry.cls in ("excluded", "undecided"):
        entry.status = "n/a"
        return
    dest = ctx.root / entry.counterpart
    if not dest.is_file():
        entry.status = "missing"
        return
    copy = dest.read_bytes()
    if entry.cls == "vendored":
        row = ctx.rows[entry.path]
        if copy == data:
            entry.status = "identical"
        elif sha256(data) != row.j2_sha:
            entry.status, entry.note = "differs", "J2's file is not the one the copy was built from"
        elif not row.patched:
            entry.status, entry.note = "differs", "an unpatched copy that is not J2's file"
        elif sha256(copy) != row.vendored_sha:
            entry.status, entry.note = "differs", "the copy no longer matches its VENDORED.md hash"
        else:
            entry.status = "patched"
    elif entry.cls == "page":
        if PAGE_FILES[entry.path][1] == "verbatim":
            entry.status = "identical" if copy == data else "differs"
        else:
            entry.status = "patched" if port_ok else "unverified"
            entry.gap = line_gap(data, copy)
            if not port_ok:
                entry.note = "port_j2_ui.py --check " + ("did not pass" if port_ok is False else "was not run")
    elif entry.cls == "legacy":
        entry.status, entry.gap = "edited", line_gap(data, copy)
    else:       # unlisted: there is a file where the rules put it, but VENDORED.md does not name it
        entry.status = "identical" if copy == data else "differs"


def list_source(folder: Path) -> list[str]:
    """Every file below `folder`, as sorted posix paths relative to it. A folder that holds a `.git` is not an extraction."""
    if not folder.is_dir():
        raise ToolError(f"--source {folder} is not a folder")
    if (folder / ".git").exists():
        raise ToolError("--source holds a .git: give an extraction of prototypes/j2 (git archive), never a repository or a working tree")
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def classify(source: Path, ctx: Context, port_ok: bool | None = None, files: Iterable[str] | None = None) -> list[Entry]:
    entries = []
    for path in (sorted(files) if files is not None else list_source(source)):
        entry = decide(path, ctx)
        measure(entry, (source / path).read_bytes(), ctx, port_ok)
        entries.append(entry)
    return entries


def find_stale(ctx: Context, source_paths: set[str]) -> list[tuple[str, str]]:
    """(sutra-pro path, why) for what Sutra Pro holds on behalf of a J2 file the source no longer has."""
    stale = []
    for row in ctx.rows.values():
        if row.j2 not in source_paths:
            stale.append((row.vendored, f"VENDORED.md names J2's {row.j2}, which the source no longer has"))
    named = {row.vendored for row in ctx.rows.values()}
    for folder in MANAGED:
        base = ctx.root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(ctx.root).as_posix()
            if (path.is_file() or path.is_symlink()) and rel not in named and not IGNORED_NAMES & set(path.parts):
                stale.append((rel, "in a folder vendor_j2.py manages, but VENDORED.md does not name it"))
    legacy = ctx.root / LEGACY_DIR
    if legacy.is_dir():
        for path in sorted(legacy.glob("*.py")):
            if path.name not in source_paths:
                stale.append((f"{LEGACY_DIR}/{path.name}", f"a legacy copy of {path.name}, which the source no longer has"))
    for j2, (dest, _how) in PAGE_FILES.items():
        if j2 not in source_paths and (ctx.root / dest).is_file():
            stale.append((dest, f"generated from J2's {j2}, which the source no longer has"))
    return sorted(set(stale))


# ---- the two checks ------------------------------------------------------------------------------------------------------------------
@dataclass
class Check:
    name: str                       # "vendor_j2.py --check"
    command: str                    # the command as shown (no absolute path)
    returncode: int | None          # None: the run itself failed (missing script, timeout)
    output: str                     # stdout then stderr, with the source and root paths replaced
    outcome: str                    # ok | differences | build error | error | not run

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"

    def lines(self, prefix: str) -> list[str]:
        return [line[len(prefix):].strip() for line in self.output.splitlines() if line.startswith(prefix)]

    def summary(self) -> str:
        """The first line of output that says something (the build error, the first difference); empty when there is none."""
        return next((line.strip() for line in self.output.splitlines() if line.strip() and not line.startswith("note:")), "")


def outcome_of(returncode: int | None, output: str) -> str:
    if returncode is None:
        return "error"
    if returncode == 0:
        return "ok"
    if returncode == 2 or (returncode == 1 and "DRIFT" in output):
        return "build error"                # the script could not build what it compares with (an anchor, a missing file)
    return "differences" if returncode == 1 else "error"


def tidy(text: str, source: Path, root: Path) -> str:
    """The output with the two folders named by placeholders: a report holds no absolute path of the machine it ran on."""
    for folder, label in ((root, "<root>"), (source, "<source>")):
        for form in {str(folder), str(folder.resolve())}:
            text = text.replace(form, label)
    return text


def run_check(name: str, argv: list[str], shown: str, cwd: Path, source: Path, root: Path) -> Check:
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=SLOW_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(name, shown, None, f"could not run: {exc}", "error")
    output = tidy(done.stdout + done.stderr, source, root)
    return Check(name, shown, done.returncode, output, outcome_of(done.returncode, output))


def script_label(script: Path, root: Path) -> str:
    try:
        return script.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return f"{script.name} (a copy outside the repository)"


def port_takes_commit(script: Path, cwd: Path) -> bool:
    """True when `port_j2_ui.py --help` lists `--commit` (the flag a git archive needs, because it is not a repository)."""
    try:
        done = subprocess.run([sys.executable, str(script), "--help"], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and "--commit" in done.stdout


def run_checks(source: Path, commit: str, root: Path, vendor_script: Path, port_script: Path) -> tuple[Check, Check]:
    vendor = [sys.executable, str(vendor_script), "--source", str(source), "--commit", commit, "--dest", str(root), "--check"]
    port = [sys.executable, str(port_script), "--j2", str(source), "--root", str(root), "--check"]
    port_shown = f"{script_label(port_script, root)} --j2 <source> --root <root> --check"
    if port_takes_commit(port_script, root):
        port += ["--commit", commit]
        port_shown += " --commit <commit>"
    vendor_shown = f"{script_label(vendor_script, root)} --source <source> --commit <commit> --dest <root> --check"
    return (run_check("vendor_j2.py --check", vendor, vendor_shown, root, source, root),
            run_check("port_j2_ui.py --check", port, port_shown, root, source, root))


# ---- git ----------------------------------------------------------------------------------------------------------------------------------
def git(top: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(top), *args], capture_output=True, timeout=300)


def git_text(top: Path, *args: str) -> str | None:
    try:
        done = git(top, *args)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.decode("utf-8", "replace").strip() if done.returncode == 0 else None


def git_top(root: Path) -> Path | None:
    top = git_text(root, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def resolve_commit(top: Path | None, given: str | None, vendored_md: str = "") -> str | None:
    """The full id of `given` when this repository knows it, else `given` as it is. With no `given`: the commit VENDORED.md names when
    its prototypes/j2 is the folder HEAD has (the pin, however many commits touched the folder since: a merge can re-touch it with the
    same content), else the last commit on HEAD that touched prototypes/j2 (J2 moved on: the label then differs from the one in
    VENDORED.md, and the check says so)."""
    if top is None:
        return given
    if given:
        return git_text(top, "rev-parse", "--verify", f"{given}^{{commit}}") or given

    def tree(rev: str) -> str | None:
        return git_text(top, "rev-parse", "--verify", f"{rev}:{J2_FOLDER}")

    named = vendored_commit(vendored_md, lambda found: tree(found) is not None)
    if named and tree(named) == tree("HEAD"):
        return named
    return git_text(top, "log", "-1", "--format=%H", "HEAD", "--", J2_FOLDER) or None


def extract(top: Path, rev: str, dest: Path) -> int:
    """`git archive <rev> prototypes/j2` unpacked into the empty folder `dest` without its two leading folders; the file count."""
    try:
        done = git(top, "archive", "--format=tar", rev, J2_FOLDER)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ToolError(f"git archive failed: {exc}") from None
    if done.returncode:
        raise ToolError(f"git archive {rev} {J2_FOLDER}: {done.stderr.decode('utf-8', 'replace').strip()}")
    count = 0
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as tar:
        for member in tar:
            parts = PurePosixPath(member.name).parts
            if not member.isreg() or parts[:2] != tuple(J2_FOLDER.split("/")) or len(parts) < 3 or ".." in parts:
                continue
            target = dest.joinpath(*parts[2:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
            count += 1
    if not count:
        raise ToolError(f"{rev} has no files under {J2_FOLDER}")
    return count


def dirty_paths(top: Path | None, root: Path) -> list[str]:
    """Paths under the sutra-pro folder with uncommitted changes (the report describes the working tree)."""
    if top is None:
        return []
    try:
        done = git(top, "status", "--porcelain", "--", str(root))
    except (OSError, subprocess.SubprocessError):
        return []
    return [line[3:] for line in done.stdout.decode("utf-8", "replace").splitlines() if line.strip()] if done.returncode == 0 else []


# ---- the report ----------------------------------------------------------------------------------------------------------------------------
def table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def folder_groups(paths: Iterable[str]) -> list[str]:
    """One bullet per folder: the folder with its file names when two or more files share it, the bare path otherwise."""
    by_dir: dict[str, list[str]] = defaultdict(list)
    for path in sorted(paths):
        pure = PurePosixPath(path)
        by_dir[str(pure.parent)].append(pure.name)
    out = []
    for folder, names in by_dir.items():
        if folder == ".":
            out.append(", ".join(f"`{n}`" for n in names))
        elif len(names) == 1:
            out.append(f"`{folder}/{names[0]}`")
        else:
            out.append(f"`{folder}/`: " + ", ".join(f"`{n}`" for n in names))
    return out


def kind_lists(entries: Sequence[Entry]) -> list[str]:
    """The entries as bullets per kind, each kind with its file count and its files grouped by folder."""
    by_kind: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        by_kind[entry.kind].append(entry)
    lines = []
    for kind in sorted(by_kind):
        lines.append(f"- {kind} ({len(by_kind[kind])})")
        lines += [f"  - {group}" for group in folder_groups(e.path for e in by_kind[kind])]
    return lines


def check_lines(check: Check, cap: int = 24) -> list[str]:
    """What a check printed, in a code block; a line that only informs (`note:`) is counted, not repeated. Long output is cut."""
    shown = [line for line in check.output.splitlines() if line.strip() and not line.startswith("note:")]
    notes = sum(1 for line in check.output.splitlines() if line.startswith("note:"))
    # a long output keeps its first lines and its last one (the summary line of vendor_j2.py --check)
    body = shown if len(shown) <= cap else shown[:cap - 2] + [f"... {len(shown) - cap + 1} more line(s)", shown[-1]]
    if notes:
        body.append(f"({notes} informational note line(s) not repeated)")
    return ["```", *(body or ["(no output)"]), "```"]


def verdict(entries: Sequence[Entry], vendor: Check | None, port: Check | None) -> list[str]:
    """The reasons `--check` would exit 1; empty when it would exit 0."""
    reasons = []
    for check in (vendor, port):
        if check is None:
            reasons.append("the machinery checks were not run")
        elif not check.ok:
            reasons.append(f"{check.name}: {check.outcome}" + (f" ({check.summary()[:200]})" if check.summary() else ""))
    open_ = [e for e in entries if not e.decided]
    if open_:
        unlisted = sum(1 for e in open_ if e.cls == "unlisted")
        reasons.append(f"{len(open_)} file(s) of the source are not decided: {unlisted} of a vendored kind that VENDORED.md does not "
                       f"name, {len(open_) - unlisted} with no rule and no exclusion")
    return reasons


def render_checks(vendor: Check | None, port: Check | None) -> list[str]:
    out = ["## The two checks", ""]
    for name, check in (("vendor_j2.py --check", vendor), ("port_j2_ui.py --check", port)):
        if check is None:
            out += [f"- {name}: not run (--no-machinery)", ""]
            continue
        code = "?" if check.returncode is None else check.returncode
        out += [f"### {check.name}: " + ("ok" if check.ok else f"FAILED, {check.outcome}"), "", f"`{check.command}`, exit {code}", ""]
        out += check_lines(check) + [""]
        if check.name.startswith("vendor_j2") and check.outcome == "differences":
            n = {label: len(check.lines(label + ":")) for label in ("differs", "missing", "not in the J2 snapshot")}
            out += [f"The check names {n['differs']} file(s) that differ, {n['missing']} that are missing and "
                    f"{n['not in the J2 snapshot']} that are not in the snapshot (stale).", ""]
    return out


def render_counts(entries: Sequence[Entry]) -> list[str]:
    out = ["## Counts", ""]
    by = Counter((e.cls, e.status) for e in entries)
    shown = [s for s in STATUSES if any(by[(c, s)] for c in CLASSES)]
    rows = [[c, sum(by[(c, s)] for s in STATUSES), *(by[(c, s)] or "" for s in shown)] for c in CLASSES]
    rows.append(["all", len(entries), *(sum(by[(c, s)] for c in CLASSES) or "" for s in shown)])
    out += table(["class", "files", *shown], rows) + [""]
    carried = [e for e in entries if e.cls not in ("excluded", "undecided")]
    if carried:
        rows = []
        for kind in sorted({e.kind for e in carried}):
            mine = [e for e in carried if e.kind == kind]
            count = Counter(e.status for e in mine)
            rows.append([kind, len(mine), count["identical"] or "", (count["patched"] + count["edited"]) or "", count["differs"] or "",
                         count["unverified"] or "", count["missing"] or "", sum(1 for e in mine if e.cls == "unlisted") or ""])
        out += ["By kind (excluded files are listed at the end):", ""]
        out += table(["kind", "files", "identical", "patched or edited", "differs", "unverified", "missing", "new (not in VENDORED.md)"], rows)
        out.append("")
    gaps = [e for e in entries if e.gap is not None]
    if gaps:
        out += ["Edited copies (generated page files and legacy tests: Sutra edits them on purpose, so their bytes are not compared). "
                "Non-blank J2 lines that are not a line of the copy:", ""]
        out += [f"- `{e.path}` ({e.cls}, {e.status}): {e.gap}" for e in gaps] + [""]
    return out


def render_lists(entries: Sequence[Entry], stale: Sequence[tuple[str, str]]) -> list[str]:
    differing = [e for e in entries if e.status == "differs"]
    unverified = [e for e in entries if e.status == "unverified"]
    missing = [e for e in entries if e.status == "missing"]
    unlisted = [e for e in entries if e.cls == "unlisted"]
    undecided = [e for e in entries if e.cls == "undecided"]
    out = [f"## Differing ({len(differing)}): J2's file is not the one the committed copy was built from", ""]
    out += (kind_lists(differing) if differing else ["none"]) + [""]
    if unverified:
        out += [f"## Unverified ({len(unverified)}): generated page files while the port check does not pass", ""]
        out += kind_lists(unverified) + [""]
    out += [f"## Missing in Sutra Pro ({len(missing)}): a place where the file belongs, with nothing in it", ""]
    out += (kind_lists(missing) if missing else ["none"]) + [""]
    out += [f"## Not decided ({len(unlisted) + len(undecided)})", ""]
    if not unlisted and not undecided:
        out += ["none", ""]
    if unlisted:
        out += [f"- {len(unlisted)} file(s) of a kind the vendor script carries that VENDORED.md does not name: the script has not "
                "taken them yet (a new J2 file; the Missing list above shows where each one belongs)."]
        out += [f"  - `{e.path}`: present in Sutra Pro at `{e.counterpart}` but not in the table" for e in unlisted if e.status != "missing"]
    out += [f"- `{e.path}`: {e.note}" for e in undecided]
    out += [""] if unlisted or undecided else []
    out += [f"## Stale ({len(stale)}): held by Sutra Pro, no J2 source", ""]
    out += ([f"- `{path}`: {why}" for path, why in stale] if stale else ["none"]) + [""]
    return out


def render_exclusions(entries: Sequence[Entry], excluded: Sequence[Exclusion]) -> list[str]:
    order = {e.pattern: i for i, e in enumerate(excluded)}
    groups: dict[tuple[str, str, str], list[Entry]] = defaultdict(list)
    for e in entries:
        if e.cls == "excluded":
            groups[(e.kind, e.reason, e.recorded)].append(e)
    ranked = sorted(groups.items(), key=lambda kv: min(order.get(e.pattern, len(order)) for e in kv[1]))
    out = [f"## Excluded, with the reason ({sum(len(v) for v in groups.values())})", ""]
    rows = [[kind, len(es), ", ".join(f"`{e.path}`" for e in es[:6]) + (", ..." if len(es) > 6 else ""), reason, recorded]
            for (kind, reason, recorded), es in ranked]
    out += table(["group", "files", "which", "reason", "also written in"], rows) if rows else ["none"]
    unused = [e.pattern for e in excluded if not any(fnmatch.fnmatchcase(en.path, e.pattern) for en in entries)]
    if unused:
        out += ["", "Exclusion patterns that match no file of this source: " + ", ".join(f"`{p}`" for p in unused) + "."]
    return out + [""]


def render_report(entries: Sequence[Entry], stale: Sequence[tuple[str, str]], vendor: Check | None, port: Check | None, *, commit: str,
                  tree: str | None, origin: str, names_pin: bool | None, dirty: Sequence[str], excluded: Sequence[Exclusion]) -> str:
    out = ["# J2 difference of record", "",
           f"- Source: `{J2_FOLDER}` at commit `{commit}`" + (f" (tree `{tree}`)" if tree else "") + f", {len(entries)} files, {origin}.",
           "- Compared with: Sutra Pro as committed (the working tree of the sutra-pro folder).",
           "- VENDORED.md names this commit: " + {True: "yes", False: "no", None: "not known"}[names_pin] + "."]
    if dirty:
        out.append(f"- Warning: {len(dirty)} path(s) under sutra-pro have uncommitted changes; this report describes the working tree: "
                   + ", ".join(f"`{d}`" for d in dirty[:5]) + (", ..." if len(dirty) > 5 else "") + ".")
    out.append("")
    out += render_checks(vendor, port) + render_counts(entries) + render_lists(entries, stale) + render_exclusions(entries, excluded)
    why = verdict(entries, vendor, port)
    out += ["## Verdict (what `--check` says)", "", "PASS: both checks pass and every file is decided." if not why else "FAIL:"]
    out += [f"- {reason}" for reason in why]
    return "\n".join(out) + "\n"


# ---- main ----------------------------------------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="The difference of record between prototypes/j2 and Sutra Pro as committed.",
                                 epilog="Exit codes: 0 report printed (--check: nothing left to decide or take), 1 --check found something, "
                                        "2 the arguments or inputs are wrong.")
    ap.add_argument("--source", type=Path, help="an extraction of prototypes/j2 (git archive; never a working tree). Default: extracted "
                                                "from --commit of this repository into a temporary folder")
    ap.add_argument("--commit", help="the commit the source is (the label both scripts write; default: the commit VENDORED.md names when "
                                     "its prototypes/j2 is the one HEAD has, else the last commit on HEAD that touched prototypes/j2). "
                                     "Without --source the extraction is made from it")
    ap.add_argument("--root", type=Path, default=REPO, help="the sutra-pro folder to compare (default: the one this script is in)")
    ap.add_argument("--vendor-script", type=Path, help=f"default: <root>/{VENDOR_SCRIPT}; a copy can be given for a dry run")
    ap.add_argument("--port-script", type=Path, help=f"default: <root>/{PORT_SCRIPT}; a copy can be given for a dry run")
    ap.add_argument("--no-machinery", action="store_true", help="classify only: do not run the two checks (not with --check)")
    ap.add_argument("--check", action="store_true", help="exit 1 unless both checks pass and every source file is decided")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.check and args.no_machinery:
        ap.error("--check needs the two checks: drop --no-machinery")
    try:
        return run(args)
    except ToolError as exc:
        print(f"j2_diff_of_record: {exc}", file=sys.stderr)
        return 2


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    ctx = Context.load(root)
    md_text = (root / VENDORED_MD).read_text(encoding="utf-8")
    top = git_top(root)
    commit = resolve_commit(top, args.commit, md_text)
    if not commit:
        raise ToolError("cannot tell which commit the source is: give --commit")
    with tempfile.TemporaryDirectory(prefix="j2-src-") as tmp:
        if args.source is not None:
            source, origin = args.source, "an extraction given with --source"
            names = list_source(source)
        else:
            if top is None:
                raise ToolError("this is not inside a git repository: give --source (an extraction of prototypes/j2) and --commit")
            source = Path(tmp) / "src"
            source.mkdir()
            extract(top, commit, source)
            origin = "extracted from this repository with git archive"
            names = list_source(source)
        vendor = port = None
        if not args.no_machinery:
            vendor_script = args.vendor_script or root / VENDOR_SCRIPT
            port_script = args.port_script or root / PORT_SCRIPT
            vendor, port = run_checks(source, commit, root, vendor_script, port_script)
        port_ok = None if port is None else port.ok
        entries = classify(source, ctx, port_ok, names)
        stale = find_stale(ctx, set(names))
        tree = git_text(top, "rev-parse", f"{commit}:{J2_FOLDER}") if top else None
        print(render_report(entries, stale, vendor, port, commit=commit, tree=tree, origin=origin, names_pin=names_commit(md_text, commit),
                            dirty=dirty_paths(top, root), excluded=ctx.excluded), end="")
    if args.check and verdict(entries, vendor, port):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
