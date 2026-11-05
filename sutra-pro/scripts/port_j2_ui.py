#!/usr/bin/env python3
"""Port J2's department page to the app (work package UI-2; docs/design/ui.md section 5 and docs/design/j2-sync.md).

    scripts/py scripts/port_j2_ui.py --j2 /path/to/J2_Prototype            # write the ported files
    scripts/py scripts/port_j2_ui.py --j2 /path/to/J2_Prototype --check    # write nothing; exit 1 when the committed files
                                                                          # differ from a fresh port
    scripts/py scripts/port_j2_ui.py --e13-json                            # the E13 wording pairs as JSON (page_render.test.js)

The page is J2's `j2_ui.html` with 13 edits (E1 to E13). Every edit is `Edit(id, old, new, count)`: `old` is a literal or a
compiled regex and `count` is the number of places it must match in J2's file. A count that is not met means J2 changed under
the port: the port stops, names every edit that no longer matches and writes nothing. Re-port; never hand-edit the copy.

What it writes, under `sutra_app/ui/` of the repository the script lives in (or `--root`):
    pages/j2_ui.html            the page after the 13 edits
    pages/j2_ui_render.js       J2's render harness, three small changes (sutra_ctx.js runs first; d3 and its tag test move)
    pages/j2_graph_layout.js    J2's layout harness, one change (sutra_ctx.js runs first)
    static/css/j2.css           the page's `<style>` block, byte for byte (the leading newline included)
    static/vendor/              d3.min.js, d3-LICENSE and README.md, byte for byte

J2 is only read, never written, and the port is deterministic (no clock, no random): two runs give the same bytes.
Exit codes: 0 ported or in step, 1 J2 drifted or the committed files differ, 2 not a J2 checkout.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parent.parent
UI_DIR = Path("sutra_app") / "ui"      # where the outputs go, relative to the repository root

# J2 files read, relative to the J2 checkout
J2_PAGE = "j2_ui.html"
J2_RENDER = "j2_ui_render.js"
J2_LAYOUT = "j2_graph_layout.js"
J2_VENDOR = ("d3.min.js", "d3-LICENSE", "README.md")
J2_FILES = (J2_PAGE, J2_RENDER, J2_LAYOUT, *(f"vendor/{name}" for name in J2_VENDOR))

# The modules the department page loads after its own script, in this order (E12); all under /ui/js/.
MODULES = ("sutra_events", "graph_layout", "chart_marks", "graph_render", "graph_view", "orgchart_view", "fnode_view",
           "chat_view", "node_panel", "dept_ext")

SANDBOX = "allow-scripts allow-forms allow-popups"      # the second layer behind the engine's sandbox header (S3-web-14)


class PortError(Exception):
    """The port cannot run (not a J2 checkout)."""


class DriftError(PortError):
    """J2 changed: one or more edits no longer match the stated number of places."""


class Edit(NamedTuple):
    id: str
    old: str | re.Pattern[str]              # a literal, or a compiled regex (then `new` is a match template: \1, \g<name>)
    new: str
    count: int                              # how many places `old` must match in J2's file

    def found(self, text: str) -> int:
        return len(self.old.findall(text)) if isinstance(self.old, re.Pattern) else text.count(self.old)

    def apply(self, text: str) -> str:
        if isinstance(self.old, re.Pattern):
            return self.old.sub(lambda match: match.expand(self.new), text)
        return text.replace(self.old, self.new)


def _lines(*parts: str) -> str:
    return "\n".join(parts)


# ----------------------------------------------------------------------------------------------------------------------
# E1: the Google Fonts link and the `<style>` block (J2 lines 7-319) become three style sheets, the boot marker and the
# context script. The pattern also captures the block's inner text, which is j2.css. It ends at the first-paint theme
# script, so the `<style>` that J2's page script writes into generated SVG (a string, far below) can never match.
# ----------------------------------------------------------------------------------------------------------------------
STYLE_BLOCK = re.compile(
    r'<link rel="stylesheet" href="https://fonts\.googleapis\.com/[^"]*">\n<style>(?P<css>.*?)</style>\n(?=<script>/\* the viewer)',
    re.DOTALL,
)
E1_NEW = _lines(
    '<link rel="stylesheet" href="/ui/css/j2.css">',
    '<link rel="stylesheet" href="/ui/css/sutra-graph.css"><link rel="stylesheet" href="/ui/css/sutra-panel.css">',
    "<!--SUTRA-BOOT-->",
    '<script src="/ui/js/sutra_ctx.js"></script>',
    "",
)

# E13: the Priorities tab says "ranked"; the final function-node spec (FN-28) and the owner's rule say Priority prices and
# never orders. Four literal pairs with their counts (internal names such as `ranked`, `TRANK` and `rank` stay). The parity
# test applies the same pairs to J2's goldens, so it imports them from here.
E13_WORDS: tuple[tuple[str, str, int], ...] = (
    ("How the Prioritiser ranked the work each cycle", "How the Prioritiser priced the work each cycle", 1),
    ("no ranking records", "no pricing records", 2),
    ("No ranking records in this run", "No pricing records in this run", 1),
    ("Funded, in the order it ranked them", "Funded, in registration order; Coordination sets the run order", 1),
)

PAGE_EDITS: tuple[Edit, ...] = (
    Edit("E1", STYLE_BLOCK, E1_NEW, 1),
    # E2: the two preview iframes get data-src (sutra_ctx.js sets src plus ?dept= at DOMContentLoaded) and a sandbox
    Edit("E2", re.compile(r'<iframe id="(sframe|frame)" title="([^"]*)" src="/site/latest"></iframe>'),
         rf'<iframe id="\1" title="\2" data-src="/site/latest" sandbox="{SANDBOX}"></iframe>', 2),
    # E3: d3 is served under /ui/vendor/; the relative path would resolve to /d/{dept}/vendor/
    Edit("E3", '<script src="vendor/d3.min.js"></script>', '<script src="/ui/vendor/d3.min.js"></script>', 1),
    # E4: the one place every URL-in-HTML site takes the run from now also carries the department
    Edit("E4", 'const runQ = () => viewRun ? "&run=" + encodeURIComponent(viewRun) : "";',
         'const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "")'
         ' + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : "");', 1),
    # E5: the Simple view title shows the department
    Edit("E5", '$("stitle").textContent = s.doc ? "Your document team" : "Your website team";',
         '$("stitle").textContent = SutraCtx.boot.dept_label || (s.doc ? "Your document team" : "Your website team");', 1),
    # E6: showTab knows the two new panes, hides the map title bar for them too, and tells SutraCtx
    Edit("E6a", '  $("backmap").hidden = name === "map"; document.querySelector("#dview .wbar").hidden = name === "map";'
                ' document.querySelector("#dview .work").classList.toggle("mapfit", name === "map");'
                ' if (name !== "map") railReveal(name);',
         _lines('  const full = name === "map" || name === "graph" || name === "orgchart";',
                '  $("backmap").hidden = full; document.querySelector("#dview .wbar").hidden = full;'
                ' document.querySelector("#dview .work").classList.toggle("mapfit", full); if (name !== "map") railReveal(name);'), 1),
    Edit("E6b", '"report","rundetails","runsettings"].forEach(t => $("pane-"+t).hidden = t !== name);',
         _lines('"report","rundetails","runsettings","graph","orgchart"].forEach(t => $("pane-"+t).hidden = t !== name);',
                "  SutraCtx.tab(name);"), 1),
    # E7: the rail gets the way back to Home, the department chip and the two new tabs (outside #railsub: no RAILSEC edit)
    Edit("E7", _lines('<nav class="rail tabs" id="rail" role="tablist" aria-label="Sections" aria-orientation="vertical">',
                      '  <button role="tab" data-tab="map" aria-selected="true"><span>Map</span></button>', ""),
         _lines('<nav class="rail tabs" id="rail" role="tablist" aria-label="Sections" aria-orientation="vertical">',
                '  <div class="railhome"><a href="/" id="to-home">\u2190 All teams</a><b id="deptchip"></b></div>',
                '  <button role="tab" data-tab="map" aria-selected="true"><span>Map</span></button>',
                '  <button role="tab" data-tab="graph" aria-selected="false"><span>Workflow graph</span></button>',
                '  <button role="tab" data-tab="orgchart" aria-selected="false"><span>Org chart</span></button>', ""), 1),
    # E8: the two panes, after #pane-map
    Edit("E8", '    <div class="pane" id="pane-map"></div>\n',
         '    <div class="pane" id="pane-map"></div>\n'
         '    <div class="pane" id="pane-graph" hidden></div><div class="pane" id="pane-orgchart" hidden></div>\n', 1),
    # E9: the node panel, after the Agent drawer
    Edit("E9", '<aside id="agentdrawer" class="agentdrawer" hidden role="dialog" aria-labelledby="adtitle"></aside>',
         '<aside id="agentdrawer" class="agentdrawer" hidden role="dialog" aria-labelledby="adtitle"></aside>\n'
         '<aside id="nodepanel" class="agentdrawer" hidden role="dialog" aria-labelledby="nptitle"></aside>', 1),
    # E10: Map pins per department (two departments' live runs must not share pins)
    Edit("E10", 'return `j2pos:${(typeof viewRun !== "undefined" && viewRun) || "live"}:${v}`;',
         'return `j2pos:${SutraCtx.dept}:${(typeof viewRun !== "undefined" && viewRun) || "live"}:${v}`;', 1),
    # E11: a function chip opens the node panel when it wants it
    Edit("E11", "async function openAgent(id){\n",
         "async function openAgent(id){\n  if (window.NodePanel && NodePanel.wants(id)) return NodePanel.openFunction(id);\n", 1),
    # E12: the new modules, after the page script and before </body>
    Edit("E12", "</script>\n</body>",
         "</script>\n" + "".join(f'<script src="/ui/js/{name}.js"></script>\n' for name in MODULES) + "</body>", 1),
    # E13: Priorities wording (four pairs)
    *(Edit(f"E13{letter}", old, new, count) for letter, (old, new, count) in zip("abcd", E13_WORDS)),
)

# The harnesses. Their command lines and JSON output do not change (docs/design/ui.md section 5, "The two harnesses").
_CTX_LOAD = _lines(
    'const ctxfile = require("path").join(__dirname, "..", "static", "js", "sutra_ctx.js");'
    "      // the page's first script (SutraCtx), run in the stub as the browser runs it, before the page script",
    'vm.runInContext(fs.readFileSync(ctxfile, "utf8"), ctx);',
    "",
)
_RUN_PAGE = "vm.runInContext(scripts[scripts.length - 1][1], ctx);"
RENDER_EDITS: tuple[Edit, ...] = (
    Edit("H1", _RUN_PAGE + "\n", _CTX_LOAD + _RUN_PAGE + "\n", 1),
    Edit("H2", 'require("path").join(__dirname, "vendor", "d3.min.js")',
         'require("path").join(__dirname, "..", "static", "vendor", "d3.min.js")', 1),
    Edit("H3", r'/<script src="vendor\/d3\.min\.js"><\/script>/', r'/<script src="\/ui\/vendor\/d3\.min\.js"><\/script>/', 1),
)
LAYOUT_EDITS: tuple[Edit, ...] = (Edit("H1", _RUN_PAGE + "\n", _CTX_LOAD + _RUN_PAGE + "\n", 1),)


# ----------------------------------------------------------------------------------------------------------------------
# The port
# ----------------------------------------------------------------------------------------------------------------------
def apply_edits(text: str, edits: tuple[Edit, ...], what: str) -> str:
    """Apply `edits` in order. Every edit's count is checked against the original text first, so one error names all of them."""
    wrong = [(edit, edit.found(text)) for edit in edits if edit.found(text) != edit.count]
    if wrong:
        lines = [f"  {edit.id}: expected {edit.count} match{'es' if edit.count != 1 else ''}, found {got}" for edit, got in wrong]
        raise DriftError(f"J2's {what} no longer matches the port:\n" + "\n".join(lines))
    for edit in edits:
        text = edit.apply(text)
    return text


def port_page(page: str) -> tuple[str, str]:
    """(the ported page, j2.css) for J2's page text. j2.css is the inner text of the `<style>` block that E1 removes."""
    ported = apply_edits(page, PAGE_EDITS, J2_PAGE)       # E1 matched exactly once, so the block is there
    return ported, STYLE_BLOCK.search(page).group("css")


def read_j2(j2: Path) -> dict[str, bytes]:
    missing = [name for name in J2_FILES if not (j2 / name).is_file()]
    if missing:
        raise PortError(f"{j2} is not a J2 checkout: missing {', '.join(missing)}")
    return {name: (j2 / name).read_bytes() for name in J2_FILES}


def build(j2: Path) -> dict[str, bytes]:
    """Every output file, as {path relative to sutra_app/ui: bytes}. Reads J2, writes nothing."""
    source = read_j2(j2)

    def text(name: str) -> str:
        return source[name].decode("utf-8")

    page, css = port_page(text(J2_PAGE))
    outputs = {
        "pages/j2_ui.html": page,
        "pages/j2_ui_render.js": apply_edits(text(J2_RENDER), RENDER_EDITS, J2_RENDER),
        "pages/j2_graph_layout.js": apply_edits(text(J2_LAYOUT), LAYOUT_EDITS, J2_LAYOUT),
        "static/css/j2.css": css,
    }
    files = {path: body.encode("utf-8") for path, body in outputs.items()}
    files.update({f"static/vendor/{name}": source[f"vendor/{name}"] for name in J2_VENDOR})
    return files


def write_files(root: Path, files: dict[str, bytes]) -> None:
    for path, data in files.items():
        target = root / UI_DIR / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def differences(root: Path, files: dict[str, bytes]) -> list[str]:
    """The files that are missing or differ from a fresh port, one line each."""
    problems = []
    for path, data in sorted(files.items()):
        target = root / UI_DIR / path
        if not target.is_file():
            problems.append(f"missing: {UI_DIR / path}")
        elif target.read_bytes() != data:
            problems.append(f"differs: {UI_DIR / path}")
    return problems


def j2_commit(j2: Path) -> str:
    """J2's HEAD, short; 'unknown' when it is not a git checkout. Read-only (`git rev-parse` writes nothing)."""
    try:
        done = subprocess.run(["git", "-C", str(j2), "rev-parse", "--short=7", "HEAD"],
                              capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):       # no git, not a repository, or a hung git
        return "unknown"
    return done.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Port J2's department page to the app (UI-2).")
    parser.add_argument("--j2", type=Path, help="the J2 prototype checkout (read only)")
    parser.add_argument("--root", type=Path, default=REPO, help="the repository to write into (default: the one this script is in)")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 when the files differ from a fresh port")
    parser.add_argument("--e13-json", action="store_true", help="print the E13 wording pairs as JSON and exit")
    args = parser.parse_args(argv)
    if args.e13_json:
        print(json.dumps([list(pair) for pair in E13_WORDS]))
        return 0
    if args.j2 is None:
        parser.error("--j2 is required")
    try:
        files = build(args.j2)
    except DriftError as error:
        print(f"DRIFT: {error}\nNo file was written. Update the edit table in scripts/port_j2_ui.py, then port again.", file=sys.stderr)
        return 1
    except PortError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    commit = j2_commit(args.j2)
    if args.check:
        problems = differences(args.root, files)
        if problems:
            print(f"The committed files differ from a fresh port of J2 {commit}:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        print(f"ok: the {len(PAGE_EDITS)} anchors of the 13 page edits match their counts, and the {len(files)} committed files equal a fresh port of J2 {commit}")
        return 0
    write_files(args.root, files)
    print(f"ported J2 {commit}: wrote {len(files)} files under {UI_DIR}")
    for path, data in sorted(files.items()):
        print(f"  {path} ({len(data):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
