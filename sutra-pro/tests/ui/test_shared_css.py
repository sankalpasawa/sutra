"""Which style sheet styles which page (J2 sync 4, D138; docs/design/j2-sync-4.md 4.6).

The team page links the sheet that scripts/port_j2_ui.py regenerates from J2 (`j2.css`); Home and the console link `j2-shell.css`, a frozen copy of
the sheet of the previous sync, because they are built on the old Simple-view skeleton. Five classes Sutra's own code uses (`barbadge`, `has-site`,
`railoff`, `smain`, `stoggle`) exist only in the old sheet, and the new rail rule would apply to Home's `<nav id="rail">`.

What this file guards is the mismatch, not the hooks: a class that a page (its markup and the modules it loads) uses and that SOME sheet of the
page's family styles, but that the page does not load. A class that no sheet styles is a script hook (a state, a test handle) and is not looked at.
  * Home and the console: families `j2-shell.css` and the `sutra-*.css` sheets (never the regenerated `j2.css`: its names mean other rules);
  * the team page: `j2.css` and the `sutra-*.css` sheets (never `j2-shell.css`).
It also pins what the page edits add to J2's markup: each class they introduce is styled by a sheet of the team page, or is a declared hook.
No browser and no J2 source is needed.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "sutra_app" / "ui"
CSS = UI / "static" / "css"
JS = UI / "static" / "js"
PAGES = UI / "pages"

_spec = importlib.util.spec_from_file_location("port_j2_ui", ROOT / "scripts" / "port_j2_ui.py")
port = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("port_j2_ui", port)
_spec.loader.exec_module(port)

WORD = re.compile(r"-?[A-Za-z_][\w-]*")
SHELL_FAMILY = ("j2-shell.css", "sutra-graph.css", "sutra-panel.css", "sutra-shell.css", "sutra-console.css")
TEAM_FAMILY = ("j2.css", "sutra-graph.css", "sutra-panel.css", "sutra-shell.css", "sutra-console.css")
FAMILY = {"home.html": SHELL_FAMILY, "console.html": SHELL_FAMILY, "j2_ui.html": TEAM_FAMILY}
# The five classes of D138: used by Home, styled by the frozen sheet and by no Sutra sheet.
OLD_SHEET_ONLY = ("barbadge", "has-site", "railoff", "smain", "stoggle")
# What the first run of this test found on the console, and which has nothing to do with the stylesheet freeze: heads_up_view.js (loaded by the
# console page) draws classes that only sutra-shell.css (Home's sheet) styles. Listed, so that a new one fails and a fix has to say so here.
KNOWN_STRANDED = {"console.html": {"huacts", "huitem", "hulane", "humore", "huopen", "hutext", "huwhen", "huwhy", "nwait", "nylane"}}
# Classes the page edits add that no sheet styles on purpose: the rail's icon buttons carry J2's `s-<name>` naming (J2 animates its own by it) and
# the three new ones have no animation of their own.
HOOKS = {"s-home", "s-graph", "s-org"}


# ----------------------------------------------------------------------------------------------------------------------
# reading: the classes a sheet styles, the classes markup and scripts use
# ----------------------------------------------------------------------------------------------------------------------
def classes_styled_by(css: str) -> set[str]:
    """Every class in a rule's selector (at any depth of @media and @supports; @keyframes and @font-face have no selectors; declarations and
    comments are not read)."""
    text = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    out: set[str] = set()
    head: list[str] = []
    for char in text:
        if char == "{":
            selector = "".join(head).strip()
            head = []
            if selector and not selector.startswith("@"):
                selector = re.sub(r"\[[^\]]*\]", " ", selector)       # an attribute selector's value is not a class
                out.update(match.group(1) for match in re.finditer(r"\.(-?[A-Za-z_][\w-]*)", selector))
        elif char in "};":
            head = []
        else:
            head.append(char)
    return out


def words(text: str) -> set[str]:
    return {token for token in text.split() if WORD.fullmatch(token)}


def classes_in_markup(html: str) -> set[str]:
    return {token for match in re.finditer(r'class="([^"]*)"', html) for token in words(match.group(1))}


def without_templates(js: str) -> str:
    """The text with every `${...}` of a template literal taken out (innermost first): what stands in them are other words, and their own quotes
    would end a class attribute early."""
    for _ in range(8):
        shorter = re.sub(r"\$\{[^{}]*\}", " ", js)
        if shorter == js:
            break
        js = shorter
    return js


def classes_in_script(js: str) -> set[str]:
    """What a script puts on an element: class="..." in a string (the `${...}` pieces of a template are dropped), a className assignment, a
    classList.add or classList.toggle with a literal."""
    out: set[str] = set()
    js = without_templates(js)
    for match in re.finditer(r'class=\\?"((?:[^"\\]|\\.)*?)\\?"', js):
        out |= words(match.group(1))
    for match in re.finditer(r"className\s*=\s*([\"'`])((?:(?!\1).)*)\1", js):
        out |= words(match.group(2))
    for match in re.finditer(r"classList\.(?:add|toggle)\(\s*[\"']([A-Za-z_-][\w-]*)[\"']", js):
        out.add(match.group(1))
    return out


def sheets_of(page: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="/ui/css/([\w.-]+\.css)"', (PAGES / page).read_text(encoding="utf-8"))


def modules_of(page: str) -> list[str]:
    return re.findall(r'<script src="/ui/js/([\w.]+)\.js"', (PAGES / page).read_text(encoding="utf-8"))


STYLED = {path.name: classes_styled_by(path.read_text(encoding="utf-8")) for path in sorted(CSS.glob("*.css"))}


def used_by(page: str) -> set[str]:
    """The classes the page's own markup (Home and the console; the team page's markup is J2's, with the edits added below) and every module it
    loads put on elements."""
    used = set() if page == "j2_ui.html" else classes_in_markup((PAGES / page).read_text(encoding="utf-8"))
    for module in modules_of(page):
        source = JS / f"{module}.js"
        if source.is_file():                       # a module that is not there yet is a different test's finding (test_port_edits.py)
            used |= classes_in_script(source.read_text(encoding="utf-8"))
    return used


# ----------------------------------------------------------------------------------------------------------------------
# the readers themselves
# ----------------------------------------------------------------------------------------------------------------------
def test_the_reader_of_a_sheet_finds_every_class_of_a_selector_and_nothing_else():
    css = """/* .not-a-class { } */
    .a, .b:hover > .c::before{color:red}
    @media (max-width:600px){ #x .d:not(.e), [data-k=".f"]{margin:0} .g{padding:0}}
    @keyframes spin{from{opacity:0}to{opacity:1}} @font-face{font-family:x}
    .h{background:url(a.png);width:.5em;transition:opacity .2s}
    :is(.i,.j-k){left:0}"""
    assert classes_styled_by(css) == {"a", "b", "c", "d", "e", "g", "h", "i", "j-k"}


def test_the_readers_of_markup_and_scripts_find_what_is_put_on_an_element():
    assert classes_in_markup('<a class="x  y-z" href="#"></a><b class="${nope} q"></b>') == {"x", "y-z", "q"}
    js = r'''el.className = "p q"; n.classList.add("r"); n.classList.toggle("s", on); const h = `<i class="t ${v ? "u" : ""} w">`;
    const e = "<b class=\"x\">"; other.classList.contains("never"); const dyn = `${kind}`;'''
    assert classes_in_script(js) == {"p", "q", "r", "s", "t", "w", "x"}       # "u" is in a ${...}: another word, not a class of the element


# ----------------------------------------------------------------------------------------------------------------------
# the pages and their sheets
# ----------------------------------------------------------------------------------------------------------------------
def test_each_page_links_its_own_sheet_and_the_frozen_one_is_for_home_and_the_console_only():
    assert sheets_of("j2_ui.html")[0] == "j2.css" and "j2-shell.css" not in sheets_of("j2_ui.html")
    for page in ("home.html", "console.html"):
        assert sheets_of(page)[0] == "j2-shell.css" and "j2.css" not in sheets_of(page), page
    for page, family in FAMILY.items():
        assert set(sheets_of(page)) <= set(family), (page, sheets_of(page))
        assert all((CSS / name).is_file() for name in sheets_of(page)), page


@pytest.mark.parametrize("page", sorted(FAMILY))
def test_no_class_a_page_uses_is_styled_only_by_a_sheet_the_page_does_not_load(page):
    family = set().union(*(STYLED[name] for name in FAMILY[page]))
    loaded = set().union(*(STYLED[name] for name in sheets_of(page)))
    stranded = {name for name in used_by(page) if name in family and name not in loaded}
    assert stranded == KNOWN_STRANDED.get(page, set()), f"{page} uses classes that only a sheet it does not load styles: {sorted(stranded)}"


def test_the_five_classes_only_the_old_sheet_styles_are_homes_and_the_frozen_sheet_has_them():
    sutra_sheets = set().union(*(STYLED[name] for name in STYLED if name.startswith("sutra-")))
    home = used_by("home.html")
    for name in OLD_SHEET_ONLY:
        assert name in STYLED["j2-shell.css"], name
        assert name not in sutra_sheets, f"{name} is styled by a Sutra sheet now: it no longer needs the frozen sheet"
        assert name in home, f"Home no longer uses {name}"
    # D138 in one line: were Home on the regenerated sheet, the classes it relies on would be styled by a sheet it does not load
    loaded_if_regenerated = STYLED["j2.css"] | sutra_sheets
    assert {name for name in OLD_SHEET_ONLY if name not in loaded_if_regenerated} <= set(OLD_SHEET_ONLY)


def edit_classes() -> set[str]:
    """The classes the page edits write into J2's markup (the replacement texts of the edits; E21 and the like write none)."""
    return {token for edit in port.PAGE_EDITS if "class=" in edit.new for token in classes_in_markup(edit.new)}


def test_the_classes_the_page_edits_add_are_styled_for_the_team_page_or_declared_hooks():
    # lane E2 writes the rules for the strips and the output place (steamstrip, railhome, rdept, soutpick): red on this lane alone, green once it is merged
    added = edit_classes()
    assert {"railhome", "rdept", "steamstrip", "soutpick", "rsep", "ri", "rlbl", "s-home", "s-graph", "s-org", "next"} <= added
    styled = set().union(*(STYLED[name] for name in sheets_of("j2_ui.html")))
    assert {name for name in added if name not in styled} <= HOOKS, sorted(name for name in added if name not in styled and name not in HOOKS)
    assert "shome" not in added            # J2's studio owns that name: its New project button has a generic rule (E5)


def test_every_hook_declared_here_is_a_class_an_edit_adds_and_no_sheet_styles_it():
    assert HOOKS <= edit_classes()
    family = set().union(*(STYLED[name] for name in TEAM_FAMILY))
    assert not (HOOKS & family), sorted(HOOKS & family)        # a hook that gets a rule stops being one: remove it from the list
