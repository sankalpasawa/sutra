#!/usr/bin/env python3
"""Port J2's department page to the app (docs/design/ui.md section 5; docs/design/j2-sync-4.md part 4, D136 and D137).

The J2 source is the folder `prototypes/j2` of this repository, at a pinned commit, extracted (never the working tree: an edited
file would be ported) into a new, empty folder:

    export J2SRC="$(mktemp -d)"
    git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C "$J2SRC"

    scripts/py scripts/port_j2_ui.py --j2 "$J2SRC" --commit <commit>            # write the ported files
    scripts/py scripts/port_j2_ui.py --j2 "$J2SRC" --commit <commit> --check    # write nothing; exit 1 when the committed files
                                                                               # differ from a fresh port
    scripts/py scripts/port_j2_ui.py --e13-json                                 # the E13 wording pairs as JSON (page_render.test.js)

`--j2` is always such an extraction. `--commit` names the commit it was taken from: a `git archive` folder is not a repository, so
the script cannot ask git; without the flag it asks git about the folder and says "unknown" when that fails.

The page is J2's `j2_ui.html` with 33 edits (E1 to E13, E19 to E23; the letters E2a to E2c, E9b and E20a to E20i count). Every edit is `Edit(id, old, new, count)`:
`old` is a literal or a compiled regex and `count` is the number of places it must match in J2's file. Every count is checked against
J2's own text first, so no edit anchors on another edit's output. A count that is not met means J2 changed under the port: the port
stops, names every edit that no longer matches and writes nothing. Re-port; never hand-edit the copy.

What it writes, under `sutra_app/ui/` of the repository the script lives in (or `--root`):
    pages/j2_ui.html            the page after the 33 edits
    pages/j2_ui_render.js       J2's render harness, three small changes (sutra_ctx.js runs first; d3 and its tag test move)
    pages/j2_graph_layout.js    J2's layout harness, one change (sutra_ctx.js runs first)
    static/css/j2.css           the page's `<style>` block, byte for byte (the leading newline included)
    static/vendor/              d3.min.js, d3-LICENSE and README.md, byte for byte

Home and the console do not take `j2.css`: they link `static/css/j2-shell.css`, a Sutra-owned copy of the previous sheet that this
script never writes (D138).

J2 is only read, never written, and the port is deterministic (no clock, no random): two runs give the same bytes.
Exit codes: 0 ported or in step, 1 J2 drifted or the committed files differ, 2 not an extraction of prototypes/j2.
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

# J2 files read, relative to the extraction of prototypes/j2
J2_PAGE = "j2_ui.html"
J2_RENDER = "j2_ui_render.js"
J2_LAYOUT = "j2_graph_layout.js"
J2_VENDOR = ("d3.min.js", "d3-LICENSE", "README.md")
J2_FILES = (J2_PAGE, J2_RENDER, J2_LAYOUT, *(f"vendor/{name}" for name in J2_VENDOR))

# The modules the department page loads after its own script, in this order (E12); all under /ui/js/.
MODULES = ("sutra_events", "graph_layout", "chart_marks", "graph_render", "graph_view", "orgchart_view", "fnode_view",
           "chat_view", "node_panel", "function_chat", "output_pick", "dept_ext")

SANDBOX = "allow-scripts allow-forms allow-popups"      # the second layer behind the engine's sandbox header (S3-web-14)


class PortError(Exception):
    """The port cannot run (not an extraction of prototypes/j2)."""


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
# E1: the Google Fonts link and the `<style>` block (J2 lines 7-668) become three style sheets, the boot marker and the
# context script. The pattern also captures the block's inner text, which is j2.css. It ends at the first-paint theme
# script, so the `<style>` that J2's page script writes into generated SVG (a string, far below) can never match.
# Home and the console link j2-shell.css instead (D138); the team page is the only one that takes the regenerated j2.css.
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
# never orders. Four literal pairs with their counts (internal names such as `ranked`, `TRANK` and `rank` stay). "no ranking
# records" is in three places now: the tab's own empty line, its status and the rail's status line (`railStatus`). The parity
# test applies the same pairs to J2's goldens, so it imports them from here.
E13_WORDS: tuple[tuple[str, str, int], ...] = (
    ("How the Prioritiser ranked the work each cycle", "How the Prioritiser priced the work each cycle", 1),
    ("no ranking records", "no pricing records", 3),
    ("No ranking records in this run", "No pricing records in this run", 1),
    ("Funded, in the order it ranked them", "Funded, in registration order; Coordination sets the run order", 1),
)

# E7: the strip at the top of the icon rail (D137, design 4.3): the way back to Home, the team's name and the two Sutra views.
# It sits outside `#railsub`, so J2's flyout model never lists it and nothing is shown twice; it is inside `.tabs`, so J2's own
# handlers open the two panes (`showTab`, `setView`) and `aria-selected` follows `showTab`. `.ri` and `.rlbl` give the buttons
# J2's size and hover label. The icons carry their own stroke attributes, so they draw before any style sheet rule applies.
_ICON = 'viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"'
E7_STRIP = _lines(
    '  <div class="railhome">',
    '    <a class="ri s-home" href="/" id="to-home" aria-label="All teams, back to Home" data-name="All teams" data-role="back to Home">'
    f'<svg {_ICON}><path d="M32 24H15M23 15l-9 9 9 9"/></svg>'
    '<span class="rlbl" aria-hidden="true">All teams<small>back to Home</small></span></a>',
    '    <b class="rdept" id="deptchip"></b>',
    '    <button type="button" role="tab" class="ri s-graph" data-tab="graph" aria-selected="false"'
    ' aria-label="Workflow graph, the team\'s nodes and their chats" data-name="Workflow graph" data-role="the team\'s nodes and their chats">'
    f'<svg {_ICON}><circle cx="12" cy="13" r="5"/><circle cx="36" cy="13" r="5"/><circle cx="24" cy="36" r="5"/><path d="M17 13h14M15 18l7 14M33 18l-7 14"/></svg>'
    '<span class="rlbl" aria-hidden="true">Workflow graph<small>the team\'s nodes and their chats</small></span></button>',
    '    <button type="button" role="tab" class="ri s-org" data-tab="orgchart" aria-selected="false"'
    ' aria-label="Org chart, every team and how they connect" data-name="Org chart" data-role="every team and how they connect">'
    f'<svg {_ICON}><rect x="16" y="7" width="16" height="11" rx="2.5"/><rect x="5" y="31" width="16" height="11" rx="2.5"/>'
    '<rect x="27" y="31" width="16" height="11" rx="2.5"/><path d="M24 18v6M13 31v-7h22v7"/></svg>'
    '<span class="rlbl" aria-hidden="true">Org chart<small>every team and how they connect</small></span></button>',
    "  </div>",
    '  <div class="rsep" aria-hidden="true"></div>',
    "",
)

_RAIL_NAV = '<nav class="rail tabs" id="rail" aria-label="Detailed view sections">\n'
_SVIEW_OPEN = '<div id="sview">\n  <section class="sland" id="sland" aria-label="Start">'
_AGENT_DRAWER = '<aside id="agentdrawer" class="agentdrawer" hidden role="dialog" aria-labelledby="adtitle"></aside>'
_E6A_OLD = ('document.querySelector("#dview .wbar").hidden = name === "map"; document.querySelector("#dview .work").classList.toggle("mapfit", name === "map");'
            " railReveal(name);")
_E6A_NEW = ('const full = name === "map" || name === "graph" || name === "orgchart"; document.querySelector("#dview .wbar").hidden = full;'
            ' document.querySelector("#dview .work").classList.toggle("mapfit", full); railReveal(name);')
_E6B_OLD = '"report","rundetails","runsettings"].forEach(t => $("pane-"+t).hidden = t !== name);'
_E9B_OLD = '!$("detail").open && $("agentdrawer").hidden) chatSet(false);'
_E21_OLD = _lines("for (const k of Object.keys(FEED)) delete FEED[k]; Object.assign(FEED, v); } } catch (e) {}", "  paintFeed();")
_LIBRARY_PATH = "location.pathname === \"/library\""
# E23: the studio adds a Google Fonts link to a generated document when it can read the frame (sFrameSetup). The app has no CDN and no web font
# (UI-D3, the same reason E1 drops J2's own link), and under the frame sandbox (D83) the document cannot be read, so the line never ran here.
_E23_OLD = ('if (d.querySelector("h2") && !d.querySelector("[class]")){ const fl = d.createElement("link"); fl.rel = "stylesheet"; '
            'fl.href = "https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,600&family=Fraunces:opsz,wght@9..144,500;9..144,600&display=swap"; '
            '(d.head || d.body).appendChild(fl); }')

PAGE_EDITS: tuple[Edit, ...] = (
    Edit("E1", STYLE_BLOCK, E1_NEW, 1),
    # E2: the two preview iframes get a sandbox (no allow-same-origin: a generated page cannot read the page's token, D83). `frame` also gets
    # data-src (sutra_ctx.js sets src plus ?dept= at DOMContentLoaded); `sframe` has no src in J2's markup, the page sets it with runQ() (E4)
    Edit("E2a", re.compile(r'<iframe id="frame" title="([^"]*)" src="/site/latest"></iframe>'),
         rf'<iframe id="frame" title="\1" data-src="/site/latest" sandbox="{SANDBOX}"></iframe>', 1),
    Edit("E2b", '<iframe id="sframe" title="Your result"></iframe>',
         f'<iframe id="sframe" title="Your result" sandbox="{SANDBOX}"></iframe>', 1),
    # E2c: the studio loads a new version into a second frame behind the first and swaps the two (their ids change places), so both get it
    Edit("E2c", '<iframe id="sframe2" class="next" title="Your result, next version" tabindex="-1" aria-hidden="true"></iframe>',
         f'<iframe id="sframe2" class="next" title="Your result, next version" tabindex="-1" aria-hidden="true" sandbox="{SANDBOX}"></iframe>', 1),
    # E3: d3 is served under /ui/vendor/; the relative path would resolve to /d/{dept}/vendor/
    Edit("E3", '<script src="vendor/d3.min.js"></script>', '<script src="/ui/vendor/d3.min.js"></script>', 1),
    # E4: the one place every URL-in-HTML site takes the run from now also carries the department
    Edit("E4", 'const runQ = () => viewRun ? "&run=" + encodeURIComponent(viewRun) : "";',
         'const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "")'
         ' + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : "");', 1),
    # E5: a strip at the top of the Simple view (above the start page and above the studio): back to All teams and the team's name. Its class is
    # not `shome`: J2's studio has a button of that name in its top bar ("New project") with a generic rule for it.
    Edit("E5", _SVIEW_OPEN,
         _lines('<div id="sview">',
                '  <div class="steamstrip"><a href="/" id="to-home-s">← All teams</a><b id="deptchip-s"></b></div>',
                '  <section class="sland" id="sland" aria-label="Start">'), 1),
    # E6: showTab knows the two new panes, gives them the whole work area (no title bar, like the Map) and tells SutraCtx
    Edit("E6a", _E6A_OLD, _E6A_NEW, 1),
    Edit("E6b", _E6B_OLD, _lines('"report","rundetails","runsettings","graph","orgchart"].forEach(t => $("pane-"+t).hidden = t !== name);',
                                 "  SutraCtx.tab(name);"), 1),
    # E7: the rail gets the way back to Home, the team's name and the two new tabs (outside #railsub: no RAILSEC edit)
    Edit("E7", _RAIL_NAV, _RAIL_NAV + E7_STRIP, 1),
    # E8: the two panes, after #pane-map
    Edit("E8", '    <div class="pane" id="pane-map"></div>\n',
         '    <div class="pane" id="pane-map"></div>\n'
         '    <div class="pane" id="pane-graph" hidden></div><div class="pane" id="pane-orgchart" hidden></div>\n', 1),
    # E9: the node panel, after the Agent drawer
    Edit("E9", _AGENT_DRAWER, _AGENT_DRAWER + '\n<aside id="nodepanel" class="agentdrawer" hidden role="dialog" aria-labelledby="nptitle"></aside>', 1),
    # E9b: Esc with the node panel open closes only the node panel (J2's own handler would close the chat panel behind it too)
    Edit("E9b", _E9B_OLD, '!$("detail").open && $("agentdrawer").hidden && !document.body.classList.contains("nodeopen")) chatSet(false);', 1),
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
    # E19: the place for the per-request output choice on the start page (D139): first in its row of options, beside "Decide for me" (the chips are
    # examples that fill the box, and sit inside the form next to Start); the module output_pick.js fills it
    Edit("E19", '<div class="slrow">', '<div class="slrow"><div class="soutpick" id="soutpick"></div>', 1),
    # E20: the template library is a page of the team, not of the root (D141): every root path J2 builds goes through SutraCtx
    Edit("E20a", "`/library?q=${encodeURIComponent(t.name)}`", "`${SutraCtx.libraryPath}?q=${encodeURIComponent(t.name)}`", 1),
    Edit("E20b", "const libHref = (art, sec, name, ver) => `/library?open=", "const libHref = (art, sec, name, ver) => `${SutraCtx.libraryPath}?open=", 1),
    Edit("E20c", "const runHref = id => `/?run=${encodeURIComponent(id)}&view=detail&tab=library`;",
         "const runHref = id => `${SutraCtx.pagePath}?run=${encodeURIComponent(id)}&view=detail&tab=library`;", 1),
    Edit("E20d", _LIBRARY_PATH, "SutraCtx.onLibrary()", 2),       # `setView` and the catalog's `CAT.on`
    Edit("E20e", "const back = view => `/?${viewRun", "const back = view => `${SutraCtx.pagePath}?${viewRun", 1),
    Edit("E20f", 'data-catgo="/library${viewRun', 'data-catgo="${SutraCtx.libraryPath}${viewRun', 1),
    # the studio's start page: a static link (no script can write the team into markup, so it is relative: /d/<id>/ gives /d/<id>/library, and
    # J2's own root gives /library), the Recent work list, and New project, which goes back to the start page
    Edit("E20g", '<a class="slink" href="/library?view=detail">Template library</a>', '<a class="slink" href="library?view=detail">Template library</a>', 1),
    Edit("E20h", '`<a href="/?run=${encodeURIComponent(x.id)}&view=simple">', '`<a href="${SutraCtx.pagePath}?run=${encodeURIComponent(x.id)}&view=simple">', 1),
    Edit("E20i", 'location.href = "/?view=simple"', 'location.href = SutraCtx.pagePath + "?view=simple"', 2),
    # E21: the function chat's questions and answers are lines of the function's own session (D148): loadFeed fills J2's QA list from it
    Edit("E21", _E21_OLD,
         _lines("for (const k of Object.keys(FEED)) delete FEED[k]; Object.assign(FEED, v); } } catch (e) {}",
                "  try { if (window.FunctionChat) await FunctionChat.hydrate(QA, CHATFN, viewRun); } catch (e) {}",
                "  paintFeed();"), 1),
    # E22: J2's own hint of the Run settings item still says the pane has "what to build"; it has Appearance and the saved runs
    Edit("E22", 'runsettings: "appearance, what to build, saved runs"};', 'runsettings: "appearance and saved runs"};', 1),
    Edit("E23", _E23_OLD, "/* no web fonts in the app (UI-D3): the studio's Google Fonts link is not added to a generated document */", 1),
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
        raise PortError(f"{j2} is not an extraction of prototypes/j2: missing {', '.join(missing)}")
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
            problems.append(f"missing: {(UI_DIR / path).as_posix()}")
        elif target.read_bytes() != data:
            problems.append(f"differs: {(UI_DIR / path).as_posix()}")
    return problems


def j2_commit(j2: Path, commit: str | None = None) -> str:
    """The commit the extraction was taken from, short. `commit` (the --commit flag) wins: a `git archive` folder is not a repository, and one
    that sits inside another repository would answer with that repository's HEAD. Without the flag: `git rev-parse` of the folder, or
    'unknown' when git or a repository is missing. Read-only (`git rev-parse` writes nothing)."""
    if commit:
        return commit.strip()[:7]
    try:
        done = subprocess.run(["git", "-C", str(j2), "rev-parse", "--short=7", "HEAD"],
                              capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):       # no git, not a repository, or a hung git
        return "unknown"
    return done.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Port J2's department page to the app (UI-2; sync 4, D137).")
    parser.add_argument("--j2", type=Path, help="an extraction of prototypes/j2 of this repository (read only)")
    parser.add_argument("--commit", help="the commit the extraction was taken from (a git archive folder cannot tell)")
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
    commit = j2_commit(args.j2, args.commit)
    if args.check:
        problems = differences(args.root, files)
        if problems:
            print(f"The committed files differ from a fresh port of J2 {commit}:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        print(f"ok: the {len(PAGE_EDITS)} anchors of the page edits match their counts, and the {len(files)} committed files equal a fresh port of J2 {commit}")
        return 0
    write_files(args.root, files)
    print(f"ported J2 {commit}: wrote {len(files)} files under {UI_DIR}")
    for path, data in sorted(files.items()):
        print(f"  {path} ({len(data):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
