"""UI-2: the port of J2's department page (docs/design/ui.md section 5, S3-web-10, docs/design/j2-sync-4.md part 4: D137, D138, D139, D141).

Three groups, none of them needs a browser or the J2 source:
  1. the committed files (sutra_app/ui/pages/j2_ui.html, static/css/j2.css, static/vendor/*, the two harness copies, and the frozen
     static/css/j2-shell.css that Home and the console keep): edit by edit (the 28 page edits) against a table written out here, and
     the invariants the design lists;
  2. scripts/port_j2_ui.py on a miniature J2 built below: the same table holds for what the script produces, J2 drift stops the
     port, `--check`, `--commit`, J2 is never written, two ports give the same bytes;
  3. opt in with SUTRA_J2_CHECKOUT=<an extraction of prototypes/j2 of this repository>: a fresh port of it equals the committed files
     (the acceptance command does the same: scripts/py scripts/port_j2_ui.py --j2 <that folder> --commit <its commit> --check).
The table is a second, independent statement of the edits: a typo in the script's own table cannot also be a typo here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "sutra_app" / "ui"
SCRIPT = ROOT / "scripts" / "port_j2_ui.py"

_spec = importlib.util.spec_from_file_location("port_j2_ui", SCRIPT)
port = importlib.util.module_from_spec(_spec)
sys.modules["port_j2_ui"] = port
_spec.loader.exec_module(port)

SANDBOX = "allow-scripts allow-forms allow-popups"
MODULES = ["sutra_events", "graph_layout", "chart_marks", "graph_render", "graph_view", "orgchart_view", "fnode_view",
           "chat_view", "node_panel", "function_chat", "output_pick", "dept_ext"]
# The 30 exact data routes of the page (J2's server since sync 4: sutra_ctx.js J2_EXACT), written out again here. The page calls 28 of
# them: it no longer calls /api/artifacts (the Artifacts pane reads the groups) or /api/output (output_pick.js posts it).
J2_API = ["state", "runs", "runlist", "changes", "call", "preview", "docs", "map", "plan", "plan-map", "library", "catalog", "run-templates",
          "artifacts", "artifacts/tree", "artifacts/groups", "artifact", "agent", "activity", "code", "story", "board", "audits", "refs", "say",
          "ask", "output", "reset", "playbooks/clear", "lessons/clear"]
NOT_FETCHED = {"artifacts", "output"}
EXTERNAL_REF = re.compile(r"""(?:src|href|action|poster|data-src)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE)
INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)
# D138: Home and the console keep the style sheet of the previous sync, frozen. The whole file (one comment line of its own, then the old
# sheet's bytes) and the old sheet alone (everything after the first line) are pinned, so neither can move by accident.
SHELL_SHA256 = "0ed39b658bade4a2f4e34a96beb933aaa48a30d92f9ffd67ebd8c4ccf8ef6e75"
PREVIOUS_J2_CSS_SHA256 = "fb49d7c823393ecb902056cb788f4cd618fe47acb32ad39cd1067c16c8445c03"


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


PAGE = read(UI / "pages" / "j2_ui.html")


# ----------------------------------------------------------------------------------------------------------------------
# The table: per edit, what the ported page holds (fragment, how many times) and what it no longer holds.
# A fragment sometimes spans a neighbouring line: that pins where the new text was put.
# ----------------------------------------------------------------------------------------------------------------------
EDIT_IDS = ["E1", "E2a", "E2b", "E3", "E4", "E5", "E6a", "E6b", "E7", "E8", "E9", "E9b", "E10", "E11", "E12", "E13a", "E13b", "E13c", "E13d",
            "E19", "E20a", "E20b", "E20c", "E20d", "E20e", "E20f", "E21", "E22"]
COUNTS = {edit: 1 for edit in EDIT_IDS} | {"E13b": 3, "E20d": 2}
E1_HEAD = ('<link rel="stylesheet" href="/ui/css/j2.css">\n'
           '<link rel="stylesheet" href="/ui/css/sutra-graph.css"><link rel="stylesheet" href="/ui/css/sutra-panel.css">\n'
           "<!--SUTRA-BOOT-->\n"
           '<script src="/ui/js/sutra_ctx.js"></script>\n'
           "<script>/* the viewer's Appearance before the first paint")
E5_STRIP = ('<div id="sview">\n'
            '  <div class="shome"><a href="/" id="to-home-s">← All teams</a><b id="deptchip-s"></b></div>\n'
            '  <section class="sland" id="sland" aria-label="Start">')
E6A_SHOWTAB = ('const full = name === "map" || name === "graph" || name === "orgchart"; document.querySelector("#dview .wbar").hidden = full;'
               ' document.querySelector("#dview .work").classList.toggle("mapfit", full); railReveal(name);')
E6B_PANES = ('"report","rundetails","runsettings","graph","orgchart"].forEach(t => $("pane-"+t).hidden = t !== name);\n'
             "  SutraCtx.tab(name);\n}")
RAIL_NAV = '<nav class="rail tabs" id="rail" aria-label="Detailed view sections">\n'
E7_HOME = (RAIL_NAV + '  <div class="railhome">\n'
           '    <a class="ri s-home" href="/" id="to-home" aria-label="All teams, back to Home" data-name="All teams" data-role="back to Home">')
E7_TABS = ['<button type="button" role="tab" class="ri s-graph" data-tab="graph" aria-selected="false"'
           ' aria-label="Workflow graph, the team\'s nodes and their chats"',
           '<button type="button" role="tab" class="ri s-org" data-tab="orgchart" aria-selected="false"'
           ' aria-label="Org chart, every team and how they connect"']
E7_END = '  </div>\n  <div class="rsep" aria-hidden="true"></div>\n  <button type="button" class="ri s-map" data-ri="map"'
E9B_ESC = '!$("detail").open && $("agentdrawer").hidden && !document.body.classList.contains("nodeopen")) chatSet(false);'
E12_TAIL = ("poll();\n</script>\n" + "".join(f'<script src="/ui/js/{name}.js"></script>\n' for name in MODULES) + "</body>\n</html>")
E21_HYDRATE = ("Object.assign(FEED, v); } } catch (e) {}\n"
               "  try { if (window.FunctionChat) await FunctionChat.hydrate(QA, CHATFN, viewRun); } catch (e) {}\n"
               "  paintFeed();")

CASES = {
    "E1": ([(E1_HEAD, 1)], ["fonts.googleapis.com", "<style>\n/* Theme", ":root{color-scheme:dark", "</style>\n<script>/* the viewer", "run-settings.css"]),
    "E2a": ([(f'<iframe id="frame" title="Website preview" data-src="/site/latest" sandbox="{SANDBOX}"></iframe>', 1)],
            ['title="Website preview" src=']),
    "E2b": ([(f'<iframe id="sframe" title="Your result" sandbox="{SANDBOX}"></iframe>', 1)],
            ['<iframe id="sframe" title="Your result"></iframe>']),
    "E3": ([('<script src="/ui/vendor/d3.min.js"></script>', 1)], ['<script src="vendor/d3.min.js">']),
    "E4": ([('const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "")'
             ' + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : "");', 1)],
           ["const runQ = () => viewRun ?"]),
    "E5": ([(E5_STRIP, 1)], ['<div id="sview">\n  <section class="sland"', "stitle"]),
    "E6a": ([(E6A_SHOWTAB, 1)], ['.hidden = name === "map"; document.querySelector("#dview .work")']),
    "E6b": ([(E6B_PANES, 1)], ['"runsettings"].forEach']),
    "E7": ([(E7_HOME, 1), ('    <b class="rdept" id="deptchip"></b>\n', 1), (E7_TABS[0], 1), (E7_TABS[1], 1), (E7_END, 1)],
           ['aria-label="Detailed view sections">\n  <button type="button" class="ri s-map"']),
    "E8": ([('<div class="pane" id="pane-map"></div>\n'
             '    <div class="pane" id="pane-graph" hidden></div><div class="pane" id="pane-orgchart" hidden></div>\n'
             '    <div class="pane" id="pane-style" hidden></div>', 1)],
           ['id="pane-map"></div>\n    <div class="pane" id="pane-style"']),
    "E9": ([('<aside id="agentdrawer" class="agentdrawer" hidden role="dialog" aria-labelledby="adtitle"></aside>\n'
             '<aside id="nodepanel" class="agentdrawer" hidden role="dialog" aria-labelledby="nptitle"></aside>\n'
             '<dialog id="detail">', 1)],
           ['aria-labelledby="adtitle"></aside>\n<dialog']),
    "E9b": ([(E9B_ESC, 1)], ['$("agentdrawer").hidden) chatSet(false);']),
    "E10": ([('return `j2pos:${SutraCtx.dept}:${(typeof viewRun !== "undefined" && viewRun) || "live"}:${v}`;', 1)],
            ["return `j2pos:${(typeof viewRun"]),
    "E11": ([("async function openAgent(id){\n  if (window.NodePanel && NodePanel.wants(id)) return NodePanel.openFunction(id);\n"
              '  if (MAPPIN){ MAPPIN = ""; paintMap(); }', 1)],
            ["async function openAgent(id){\n  if (MAPPIN)"]),
    "E12": ([(E12_TAIL, 1)], ["poll();\n</script>\n</body>"]),
    "E13a": ([("How the Prioritiser priced the work each cycle", 1)], ["How the Prioritiser ranked"]),
    "E13b": ([("no pricing records", 3)], ["no ranking records"]),
    "E13c": ([("No pricing records in this run", 1)], ["No ranking records"]),
    "E13d": ([("Funded, in registration order; Coordination sets the run order", 1)], ["Funded, in the order it ranked them"]),
    "E19": ([('    <div class="soutpick" id="soutpick"></div>\n    <div class="schips" id="schips"></div>\n', 1)],
            ['</form>\n    <div class="schips"', 'id="outsel"', "OUTS", "EFFOUT", "PICKEDOUT"]),
    "E20a": ([("`${SutraCtx.libraryPath}?q=${encodeURIComponent(t.name)}`", 1)], ["`/library?q="]),
    "E20b": ([("const libHref = (art, sec, name, ver) => `${SutraCtx.libraryPath}?open=", 1)], ["`/library?open="]),
    "E20c": ([("const runHref = id => `${SutraCtx.pagePath}?run=${encodeURIComponent(id)}&view=detail&tab=library`;", 1)],
             ["`/?run=${encodeURIComponent(id)}&view=detail"]),
    "E20d": ([("SutraCtx.onLibrary()", 2), ("if (SutraCtx.onLibrary()) return;", 1), ("const CAT = {on: SutraCtx.onLibrary(), ", 1)],
             ['location.pathname === "/library"']),
    "E20e": ([("const back = view => `${SutraCtx.pagePath}?${viewRun", 1)], ["const back = view => `/?${viewRun"]),
    "E20f": ([('data-catgo="${SutraCtx.libraryPath}${viewRun', 1)], ['data-catgo="/library']),
    "E21": ([(E21_HYDRATE, 1)], ["Object.assign(FEED, v); } } catch (e) {}\n  paintFeed();"]),
    "E22": ([('runsettings: "appearance and saved runs"};', 1)], ["appearance, what to build, saved runs"]),
}


def check_case(page: str, case: str) -> None:
    present, gone = CASES[case]
    for fragment, count in present:
        assert page.count(fragment) == count, f"{case}: {fragment[:70]!r} expected {count} time(s), found {page.count(fragment)}"
    for fragment in gone:
        assert fragment not in page, f"{case}: {fragment[:70]!r} is still in the page"


# ======================================================================================================================
# 1. The committed files
# ======================================================================================================================
@pytest.mark.parametrize("case", EDIT_IDS)
def test_edit_is_in_the_committed_page(case):
    check_case(PAGE, case)


def test_there_are_twenty_eight_edits_and_every_one_has_a_case_here():
    assert len(EDIT_IDS) == len(set(EDIT_IDS)) == 28 and sorted(CASES) == sorted(EDIT_IDS)
    assert [COUNTS[f"E13{letter}"] for letter in "abcd"] == [1, 3, 1, 1] and COUNTS["E20d"] == 2
    assert sum(1 for count in COUNTS.values() if count == 1) == 26


def test_the_retired_edits_left_nothing_behind():
    # E14 to E18 (Run settings: J2's own is native now) and E19a to E19c (the start select, OUTS and /api/output moved to a module)
    for gone in ('id="outsel"', 'id="to-simple"', "What to build", "EFFOUT", "PICKEDOUT", "/api/engine/settings", 'id="stitle"', 'id="sotype"',
                 "run-settings.css"):
        assert gone not in PAGE, gone
    assert 'id="runlist"' in PAGE and 'id="runq"' in PAGE and 'class="rsec"' in PAGE            # J2's own Run settings is there instead
    assert not (UI / "static" / "css" / "run-settings.css").exists()


def test_the_priorities_wording_changed_but_internal_names_did_not():
    assert "ranking" not in PAGE and "it ranked" not in PAGE
    assert "c.ranked" in PAGE and "ranked: ws.filter" in PAGE


def test_exactly_two_attribute_less_inline_scripts_and_the_page_script_is_the_last():
    scripts = INLINE_SCRIPT.findall(PAGE)
    assert len(scripts) == 2
    assert scripts[0].startswith("/* the viewer's Appearance before the first paint")
    assert scripts[1].startswith("\nconst WHO = {") and "function showTab(name)" in scripts[1] and scripts[1].rstrip().endswith("poll();")
    assert PAGE.index('<script src="/ui/vendor/d3.min.js"></script>') < PAGE.index(scripts[1]) < PAGE.index('<script src="/ui/js/sutra_events.js">')
    assert all("<script" not in script for script in scripts[:1])  # the first writes no script tag, so the pattern above cannot be fooled


def test_the_boot_marker_is_in_the_head_before_the_context_script_and_occurs_once():
    head = PAGE[:PAGE.index("</head>")]
    assert PAGE.count("<!--SUTRA-BOOT-->") == 1 and head.count("<!--SUTRA-BOOT-->") == 1
    assert head.index("<!--SUTRA-BOOT-->") < head.index('<script src="/ui/js/sutra_ctx.js"></script>') < head.index("<script>")


def test_the_page_loads_the_modules_of_e12_in_order_and_dept_ext_is_the_last():
    tail = PAGE[PAGE.index(INLINE_SCRIPT.findall(PAGE)[1]):]
    assert re.findall(r'<script src="/ui/js/(\w+)\.js"></script>', tail) == MODULES
    assert MODULES.index("function_chat") < MODULES.index("output_pick") < MODULES.index("dept_ext") == len(MODULES) - 1


def test_every_module_the_page_loads_is_in_the_static_folder():
    # function_chat.js and output_pick.js come from the modules lane (E2): this test is red on this lane alone and green once it is merged
    missing = [name for name in MODULES if not (UI / "static" / "js" / f"{name}.js").is_file()]
    assert missing == [], f"the page loads modules that are not in sutra_app/ui/static/js: {missing}"


def test_no_external_url_in_the_markup_and_no_cdn():
    assert not EXTERNAL_REF.search(PAGE)
    assert "googleapis" not in PAGE
    assert not re.search(r"url\(\s*[\"']?\s*(?:https?:)?//", PAGE)


def test_every_link_of_the_markup_is_a_hash_a_root_path_or_one_of_the_page_s_own_url_helpers():
    hrefs = re.findall(r'href="([^"]*)"', PAGE)
    own = ("${artUrl(", "${libHref(", "${runHref(", "${href}")          # template expressions over the helpers that E4 and E20 made team-aware
    odd = [h for h in hrefs if h != "#" and not h.startswith("/") and not h.startswith(own)]
    assert odd == [], odd
    assert not any(h.startswith("?") for h in hrefs)                  # J2's old relative "?view=" links are gone with the old Simple-view title
    assert hrefs.count("/") == 2                                      # the two ways back to Home (E5, E7); nothing else points at the root


def test_ids_of_the_page_are_unique():
    markup = PAGE[PAGE.index("<body"):PAGE.index('<script src="/ui/vendor/d3.min.js">')]
    ids = re.findall(r'\sid="([^"]+)"', markup)
    assert len(ids) > 100 and sorted({i for i in ids if ids.count(i) > 1}) == []


def test_both_preview_iframes_wait_for_their_src_or_the_page_and_are_sandboxed_without_same_origin():
    tags = {m.group(1): m.group(0) for m in re.finditer(r'<iframe id="(sframe|frame)"[^>]*>', PAGE)}
    assert sorted(tags) == ["frame", "sframe"]
    for tag in tags.values():
        assert f'sandbox="{SANDBOX}"' in tag and "allow-same-origin" not in tag
        assert not re.search(r'(?<![-\w])src=', tag)
    assert 'data-src="/site/latest"' in tags["frame"] and "data-src" not in tags["sframe"]       # sframe's src is set by the page, with runQ()
    assert "$(\"sframe\").src = `/site/${sframeKey}?t=${Date.now()}${runQ()}`" in PAGE


def test_the_rail_strip_is_the_first_thing_in_the_rail_and_outside_the_flyout_pool():
    rail = PAGE[PAGE.index(RAIL_NAV):PAGE.index("</nav>", PAGE.index(RAIL_NAV))]
    strip = rail[:rail.index('<div class="rsep"')]
    assert strip.count('class="ri s-home"') == 1 and strip.count('id="to-home"') == 1 and strip.count('id="deptchip"') == 1
    assert re.findall(r'data-tab="(\w+)"', strip) == ["graph", "orgchart"]
    assert re.findall(r'role="tab"', strip) == ["role=\"tab\""] * 2 and strip.count('aria-selected="false"') == 2
    assert 'href="/"' in strip and strip.count('<span class="rlbl" aria-hidden="true">') == 3          # a hover label each (J2's `.rlbl`)
    assert strip.index("to-home") < strip.index("deptchip") < strip.index('data-tab="graph"') < strip.index('data-tab="orgchart"')
    assert rail.index('class="ri s-map"') > len(strip)                                                   # J2's own items come after
    assert 'data-tab="graph"' not in rail[rail.index('id="railsub"'):] and 'data-tab="orgchart"' not in rail[rail.index('id="railsub"'):]
    assert PAGE.count('data-tab="graph"') == 1 and PAGE.count('data-tab="orgchart"') == 1


def test_the_simple_view_strip_and_the_output_place_are_inside_the_start_area():
    sview = PAGE[PAGE.index('<div id="sview">'):PAGE.index('<section class="swork"')]
    assert sview.index('class="shome"') < sview.index('id="sland"') and sview.count('id="to-home-s"') == 1 and sview.count('id="deptchip-s"') == 1
    sland = sview[sview.index('id="sland"'):]
    assert sland.index('id="lform"') < sland.index('id="soutpick"') < sland.index('id="schips"')       # the chips are after the box, the choice before them


def fetch_sites(script: str) -> list[str]:
    """The first argument of every fetch( call of the page script: quote and bracket aware, up to the top-level comma."""
    sites = []
    for match in re.finditer(r"(?<![\w$.])fetch\(", script):
        depth, quote, i = 0, None, match.end()
        while i < len(script):
            c = script[i]
            if quote:
                if c == "\\":
                    i += 2
                    continue
                if c == quote:
                    quote = None
            elif c in "\"'`":
                quote = c
            elif c in "([{":
                depth += 1
            elif c in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif c == "," and depth == 0:
                break
            i += 1
        sites.append(script[match.end():i])
    return sites


def test_every_fetch_goes_to_a_j2_route_or_through_artUrl_so_the_wrapper_covers_the_whole_page():
    sites = fetch_sites(INLINE_SCRIPT.findall(PAGE)[1])
    assert len(sites) == 32 and sites.count("artUrl(f)") == 1
    routes = set()
    for site in sites:
        if site == "artUrl(f)":
            routes.add("artifact")
            continue
        path = re.match(r"[`\"](/[^?$`\"]*)", site)
        assert path, site
        route = path.group(1)
        assert route.startswith("/api/"), site
        if route == "/api/library/":                                  # one template version: /api/library/<artifact>/<section>/<slug>/v<N>
            continue
        assert route[len("/api/"):] in J2_API, site
        routes.add(route[len("/api/"):])
    assert routes == set(J2_API) - NOT_FETCHED                       # 28 routes, and never /api/artifacts or /api/output
    assert "const artUrl = f => `/api/artifact?name=${encodeURIComponent(f)}${runQ()}`;" in PAGE


def test_the_page_uses_no_transport_the_fetch_wrapper_could_not_cover_and_none_the_csp_would_have_to_allow():
    for word in ("XMLHttpRequest", "EventSource", "WebSocket", "sendBeacon", "new Worker", "eval(", "new Function", "document.cookie", "setInterval",
                 "blob:", "data:"):
        assert word not in PAGE, word
    assert PAGE.count("localStorage") == 23 and PAGE.count("navigator.clipboard") == 3


def test_the_style_sheet_is_the_moved_style_block_and_the_page_holds_none_of_it():
    css = read(UI / "static" / "css" / "j2.css")
    assert css.startswith("\n/* Theme: every colour of the page is a token here, a warm dark set (the default)")
    assert css.endswith("}\n") and ":root{color-scheme:dark;" in css and css.count("{") == css.count("}")
    assert "url(" not in css and "@import" not in css and "http" not in css
    assert ":root{color-scheme:dark;" not in PAGE and "/* Theme:" not in PAGE


def sheets_of(page: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="/ui/css/([\w.-]+\.css)"', read(UI / "pages" / page))


def test_the_team_page_takes_the_regenerated_sheet_and_home_and_the_console_keep_the_frozen_one():
    assert sheets_of("j2_ui.html") == ["j2.css", "sutra-graph.css", "sutra-panel.css"]
    assert sheets_of("home.html") == ["j2-shell.css", "sutra-graph.css", "sutra-panel.css", "sutra-shell.css"]
    assert sheets_of("console.html") == ["j2-shell.css", "sutra-panel.css", "sutra-console.css"]
    for page in ("j2_ui.html", "home.html", "console.html"):
        assert all((UI / "static" / "css" / name).is_file() for name in sheets_of(page)), page


def test_j2_shell_css_is_the_previous_sheet_frozen_and_pinned_and_the_port_never_writes_it():
    raw = (UI / "static" / "css" / "j2-shell.css").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHELL_SHA256
    first, _, rest = raw.partition(b"\n")
    assert hashlib.sha256(rest).hexdigest() == PREVIOUS_J2_CSS_SHA256            # everything after its own first line is the old j2.css
    assert first.startswith(b"/* j2-shell.css:") and first.endswith(b"*/") and b"D138" in first
    assert b"Sutra-owned" in first and b"Not generated" in first
    assert b"url(" not in raw and b"http" not in raw.replace(first, b"") and b"@import" not in raw
    assert raw != (UI / "static" / "css" / "j2.css").read_bytes() and raw.count(b"\n/* Theme:") == 1


def test_the_vendored_d3_is_the_unchanged_7_9_0_build_with_its_licence_and_readme():
    d3 = (UI / "static" / "vendor" / "d3.min.js").read_bytes()
    assert hashlib.sha256(d3).hexdigest() == "f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539"
    assert d3.startswith(b"// https://d3js.org v7.9.0")
    assert "Permission to use, copy, modify, and/or distribute this software" in read(UI / "static" / "vendor" / "d3-LICENSE")
    assert read(UI / "static" / "vendor" / "README.md").startswith("d3 7.9.0 (https://d3js.org)")


def test_the_render_harness_copy_runs_sutra_ctx_first_and_reads_d3_from_the_static_folder():
    text = read(UI / "pages" / "j2_ui_render.js")
    ctx_run = 'vm.runInContext(fs.readFileSync(ctxfile, "utf8"), ctx);'
    assert text.count(ctx_run) == 1 and text.count("vm.runInContext(scripts[scripts.length - 1][1], ctx);") == 1
    assert text.index(ctx_run) < text.index("vm.runInContext(scripts[scripts.length - 1][1], ctx);")
    assert 'const ctxfile = require("path").join(__dirname, "..", "static", "js", "sutra_ctx.js");' in text
    assert 'require("path").join(__dirname, "..", "static", "vendor", "d3.min.js")' in text
    assert r'/<script src="\/ui\/vendor\/d3\.min\.js"><\/script>/.test(src)' in text
    assert 'join(__dirname, "vendor"' not in text and r'<script src="vendor\/d3' not in text


def test_the_layout_harness_copy_runs_sutra_ctx_first_and_needs_nothing_else():
    text = read(UI / "pages" / "j2_graph_layout.js")
    page_run = "vm.runInContext(scripts[scripts.length - 1][1], ctx);"
    assert text.count(page_run) == 1 and text.count('vm.runInContext(fs.readFileSync(ctxfile, "utf8"), ctx);') == 1
    assert text.index('vm.runInContext(fs.readFileSync(ctxfile, "utf8"), ctx);') < text.index(page_run)
    assert "d3" not in text


# ======================================================================================================================
# 2. scripts/port_j2_ui.py on a miniature J2
# ======================================================================================================================
MINI_CSS = "\n/* Theme: a miniature, with a middle dot · and a trailing newline */\n:root{color-scheme:dark;--bg:#111}\n"
MINI_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>J2 Department</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Mini&display=swap">
<style>@@CSS@@</style>
<script>/* the viewer's Appearance before the first paint (Run settings sets it): light, dark or system; dark by default */
document.documentElement.dataset.theme = "dark";</script>
</head>
<body class="simple">
<div id="sview">
  <section class="sland" id="sland" aria-label="Start">
    <form class="sbox" id="lform"><textarea id="lbox"></textarea></form>
    <div class="schips" id="schips"></div>
  </section>
  <section class="swork" id="swork" hidden>
    <div class="sprev" id="sprevbox"><div class="sframe" id="sframebox"><iframe id="sframe" title="Your result"></iframe></div></div>
  </section>
</div>
<div id="dview">
<nav class="rail tabs" id="rail" aria-label="Detailed view sections">
  <button type="button" class="ri s-map" data-ri="map" aria-expanded="false"><span class="rlbl">Map</span></button>
  <button type="button" class="ri s-chat" id="gochat"><span class="rlbl">Simple view</span></button>
  <div class="rfly" id="rfly" hidden><div class="railsub" id="railsub"></div></div>
</nav>
    <div class="pane preview" id="pane-preview" hidden><iframe id="frame" title="Website preview" src="/site/latest"></iframe></div>
    <div class="pane" id="pane-map"></div>
    <div class="pane" id="pane-style" hidden></div>
<aside id="agentdrawer" class="agentdrawer" hidden role="dialog" aria-labelledby="adtitle"></aside>
<dialog id="detail"></dialog>
</div>
<script src="vendor/d3.min.js"></script>
<script>
const WHO = {user: ["Requester (you)", "R"]};
const runQ = () => viewRun ? "&run=" + encodeURIComponent(viewRun) : "";
async function loadFeed(force){
  try { const r = await fetch(`/api/activity?who=${CHATFN}${runQ()}`); if (r.ok){ const v = await r.json();
    for (const k of Object.keys(FEED)) delete FEED[k]; Object.assign(FEED, v); } } catch (e) {}
  paintFeed();
}
const TABHINT = {priorities: "How the Prioritiser ranked the work each cycle, what it deferred and why.", runsettings: "How the app looks, and which run you are looking at."};
function showTab(name){
  $("wtitle").textContent = name;
  ["wcrumb", "wcnt"].forEach(i => $(i).hidden = !crumb); document.querySelector("#dview .wbar").hidden = name === "map"; document.querySelector("#dview .work").classList.toggle("mapfit", name === "map"); railReveal(name);
  ["preview","goal","workflows","conflicts","priorities","timeline","audit","charter","docs","artifacts","board","library","story","map","style","lessons","playbooks","report","rundetails","runsettings"].forEach(t => $("pane-"+t).hidden = t !== name);
}
const motionKey = svg => {
  return `j2pos:${(typeof viewRun !== "undefined" && viewRun) || "live"}:${v}`; };
async function openAgent(id){
  if (MAPPIN){ MAPPIN = ""; paintMap(); }
}
const libLink = t => t.artifact ? libHref(t.artifact) : `/library?q=${encodeURIComponent(t.name)}`;
const libHref = (art, sec, name, ver) => `/library?open=${encodeURIComponent(art)}`;
const runHref = id => `/?run=${encodeURIComponent(id)}&view=detail&tab=library`;
function setView(v){
  if (location.pathname === "/library") return;      // the catalog page keeps its own ?view=
}
const CAT = {on: location.pathname === "/library", loaded: false};
const back = view => `/?${viewRun ? "run=" + encodeURIComponent(viewRun) + "&" : ""}view=${view}`;
const railItem = `<button type="button" class="rgo" data-catgo="/library${viewRun ? "?run=" + encodeURIComponent(viewRun) : ""}" aria-current="${CAT.on}">Shared library</button>`;
const RAILDIM = {priorities: s => !prioModel(s).has && "no ranking records"};
function prioModel(s){ return {status: !has ? "no ranking records" : "some"}; }
function renderPriorities(s){
  if (!p.has) return `<p class="empty">No ranking records in this run: nothing was recorded.</p>`;
  return `<h4>Funded, in the order it ranked them</h4>`;
}
const railStatus = s => ({prio: p.has ? "n credits" : "no ranking records"});
const TABSUB = {rundetails: "run id, model, budget", runsettings: "appearance, what to build, saved runs"};
document.addEventListener("keydown", e => { if (e.key === "Escape" && CHAT.on && !document.body.classList.contains("simple") && !(RAIL && RAIL.open) && !$("detail").open && $("agentdrawer").hidden) chatSet(false); });
if (!CAT.on) poll();
</script>
</body>
</html>
""".replace("@@CSS@@", MINI_CSS)
MINI_RENDER = r"""// mini render harness
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(html, "utf8"), scripts = [...src.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const d3file = require("path").join(__dirname, "vendor", "d3.min.js");      // the page's one library
if (/<script src="vendor\/d3\.min\.js"><\/script>/.test(src) && fs.existsSync(d3file)) vm.runInContext(fs.readFileSync(d3file, "utf8"), ctx);
vm.runInContext(scripts[scripts.length - 1][1], ctx);
const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
"""
MINI_LAYOUT = r"""// mini layout harness
const fs = require("fs"), vm = require("vm");
const scripts = [...fs.readFileSync(process.argv[2], "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)];
vm.runInContext(scripts[scripts.length - 1][1], ctx);
const maps = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
"""
MINI_D3 = b"// https://d3js.org v7.9.0 mini\r\n(function(){})();\xc2\xb7\n"          # CRLF and a middle dot: copied byte for byte
MINI_LICENSE = b"ISC mini licence\n"
MINI_README = b"d3 7.9.0 mini readme\r\n"
OUTPUTS = ["pages/j2_graph_layout.js", "pages/j2_ui.html", "pages/j2_ui_render.js", "static/css/j2.css",
           "static/vendor/README.md", "static/vendor/d3-LICENSE", "static/vendor/d3.min.js"]
PIN = "00efb179e21cb79fae157a0679e819921ac37726"


def make_j2(base: Path, **replace: tuple[tuple[str, str], ...]) -> Path:
    """An extraction of prototypes/j2 in miniature. `replace` swaps text in a file: page=((old, new), ...), render=..., layout=..."""
    j2 = base / "j2"
    (j2 / "vendor").mkdir(parents=True)
    texts = {"page": MINI_PAGE, "render": MINI_RENDER, "layout": MINI_LAYOUT}
    for key, pairs in replace.items():
        for old, new in pairs:
            assert old in texts[key], old
            texts[key] = texts[key].replace(old, new)
    (j2 / "j2_ui.html").write_bytes(texts["page"].encode())
    (j2 / "j2_ui_render.js").write_bytes(texts["render"].encode())
    (j2 / "j2_graph_layout.js").write_bytes(texts["layout"].encode())
    (j2 / "vendor" / "d3.min.js").write_bytes(MINI_D3)
    (j2 / "vendor" / "d3-LICENSE").write_bytes(MINI_LICENSE)
    (j2 / "vendor" / "README.md").write_bytes(MINI_README)
    return j2


def tree(base: Path) -> dict[str, bytes]:
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


def run(capsys, *args) -> tuple[int, str, str]:
    code = port.main([str(a) for a in args])
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture()
def ported(tmp_path, capsys):
    """A miniature J2 ported into an empty repository root: (j2, root)."""
    j2, root = make_j2(tmp_path), tmp_path / "repo"
    root.mkdir()
    assert run(capsys, "--j2", j2, "--root", root)[0] == 0
    return j2, root


def test_the_miniature_holds_every_anchor_of_the_design_table_the_counts_it_states():
    for edit in port.PAGE_EDITS:
        assert edit.found(MINI_PAGE) == COUNTS[edit.id], edit.id


def test_the_port_writes_the_seven_files_under_sutra_app_ui_and_never_the_frozen_sheet(ported):
    _, root = ported
    assert sorted(tree(root)) == sorted(f"sutra_app/ui/{name}" for name in OUTPUTS)
    assert not any("j2-shell" in name or "run-settings" in name for name in tree(root))


@pytest.mark.parametrize("case", EDIT_IDS)
def test_the_ported_miniature_page_holds_every_edit(ported, case):
    check_case(read(ported[1] / "sutra_app" / "ui" / "pages" / "j2_ui.html"), case)


def test_the_style_sheet_is_the_style_block_inner_text_byte_for_byte(ported):
    assert (ported[1] / "sutra_app/ui/static/css/j2.css").read_bytes() == MINI_CSS.encode()


def test_the_vendor_files_are_copied_byte_for_byte(ported):
    vendor = ported[1] / "sutra_app/ui/static/vendor"
    assert (vendor / "d3.min.js").read_bytes() == MINI_D3
    assert (vendor / "d3-LICENSE").read_bytes() == MINI_LICENSE and (vendor / "README.md").read_bytes() == MINI_README


def test_the_harness_copies_get_exactly_their_documented_changes(ported):
    pages = ported[1] / "sutra_app/ui/pages"
    ctx_load = ('const ctxfile = require("path").join(__dirname, "..", "static", "js", "sutra_ctx.js");'
                "      // the page's first script (SutraCtx), run in the stub as the browser runs it, before the page script\n"
                'vm.runInContext(fs.readFileSync(ctxfile, "utf8"), ctx);\n')
    run_page = "vm.runInContext(scripts[scripts.length - 1][1], ctx);\n"
    assert read(pages / "j2_ui_render.js") == (MINI_RENDER
        .replace('"vendor", "d3.min.js"', '"..", "static", "vendor", "d3.min.js"')
        .replace(r'/<script src="vendor\/d3\.min\.js"><\/script>/', r'/<script src="\/ui\/vendor\/d3\.min\.js"><\/script>/')
        .replace(run_page, ctx_load + run_page))
    assert read(pages / "j2_graph_layout.js") == MINI_LAYOUT.replace(run_page, ctx_load + run_page)


def test_a_second_port_gives_the_same_bytes(tmp_path, capsys):
    j2, other = make_j2(tmp_path), tmp_path / "other"
    first = tmp_path / "first"
    assert run(capsys, "--j2", j2, "--root", first)[0] == 0 and run(capsys, "--j2", j2, "--root", other)[0] == 0
    assert run(capsys, "--j2", j2, "--root", other)[0] == 0           # over its own output: still the same
    assert tree(first) == tree(other)


def test_check_is_quiet_about_files_in_step_and_writes_nothing(ported, capsys):
    j2, root = ported
    before = tree(root)
    code, out, err = run(capsys, "--j2", j2, "--root", root, "--check")
    assert (code, err) == (0, "") and out.startswith("ok: the 28 anchors of the page edits match their counts, ")
    assert "and the 7 committed files equal a fresh port of J2 " in out
    assert tree(root) == before


def test_check_fails_and_names_a_changed_file(ported, capsys):
    j2, root = ported
    page = root / "sutra_app/ui/pages/j2_ui.html"
    page.write_bytes(page.read_bytes() + b" ")
    code, out, err = run(capsys, "--j2", j2, "--root", root, "--check")
    assert code == 1 and out == "" and "differ from a fresh port" in err and "differs: sutra_app/ui/pages/j2_ui.html" in err
    assert err.count("differs:") == 1 and "missing:" not in err


def test_check_notices_a_change_in_each_of_the_seven_files(ported, capsys):
    j2, root = ported
    for name in OUTPUTS:
        target = root / "sutra_app/ui" / name
        original = target.read_bytes()
        target.write_bytes(original[:-1] + (b"!" if original[-1:] != b"!" else b"?"))
        code, _, err = run(capsys, "--j2", j2, "--root", root, "--check")
        assert code == 1 and err.count("differs:") == 1 and f"differs: sutra_app/ui/{name}\n" in err, name
        target.write_bytes(original)
    assert run(capsys, "--j2", j2, "--root", root, "--check")[0] == 0


def test_check_fails_and_names_a_missing_file_and_does_not_create_it(ported, capsys):
    j2, root = ported
    (root / "sutra_app/ui/static/css/j2.css").unlink()
    code, _, err = run(capsys, "--j2", j2, "--root", root, "--check")
    assert code == 1 and "missing: sutra_app/ui/static/css/j2.css" in err
    assert not (root / "sutra_app/ui/static/css/j2.css").exists()


def test_check_on_an_empty_root_reports_every_file_missing(tmp_path, capsys):
    root = tmp_path / "empty"
    root.mkdir()
    code, _, err = run(capsys, "--j2", make_j2(tmp_path), "--root", root, "--check")
    assert code == 1 and err.count("missing:") == 7 and tree(root) == {}


def test_the_port_replaces_files_that_are_there(ported, capsys):
    j2, root = ported
    page = root / "sutra_app/ui/pages/j2_ui.html"
    page.write_bytes(b"hand edited")
    assert run(capsys, "--j2", j2, "--root", root)[0] == 0
    assert run(capsys, "--j2", j2, "--root", root, "--check")[0] == 0 and page.read_bytes() != b"hand edited"


def test_the_port_prints_what_it_wrote(tmp_path, capsys):
    root = tmp_path / "repo"
    code, out, _ = run(capsys, "--j2", make_j2(tmp_path), "--root", root)
    assert code == 0 and out.startswith("ported J2 ") and "wrote 7 files under sutra_app/ui" in out
    assert "pages/j2_ui.html (" in out and "static/vendor/d3.min.js (" in out


def test_the_commit_flag_names_the_commit_in_short_form_in_both_modes(tmp_path, capsys):
    j2, root = make_j2(tmp_path), tmp_path / "repo"
    code, out, _ = run(capsys, "--j2", j2, "--commit", PIN, "--root", root)
    assert code == 0 and out.startswith(f"ported J2 {PIN[:7]}: wrote 7 files")
    code, out, err = run(capsys, "--j2", j2, "--commit", PIN, "--root", root, "--check")
    assert (code, err) == (0, "") and out.endswith(f"equal a fresh port of J2 {PIN[:7]}\n")
    page = root / "sutra_app/ui/pages/j2_ui.html"
    page.write_bytes(page.read_bytes() + b" ")
    assert f"differ from a fresh port of J2 {PIN[:7]}:" in run(capsys, "--j2", j2, "--commit", PIN, "--root", root, "--check")[2]


def test_an_extraction_has_no_repository_to_ask_so_without_the_flag_the_commit_is_unknown(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(port.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("git")))
    assert port.j2_commit(make_j2(tmp_path)) == "unknown"
    assert port.j2_commit(make_j2(tmp_path / "other"), PIN) == PIN[:7]          # the flag needs no git at all
    assert port.j2_commit(make_j2(tmp_path / "third"), "  " + PIN + "\n") == PIN[:7]


def test_drift_stops_the_port_names_every_edit_with_its_counts_and_writes_nothing(tmp_path, capsys):
    j2 = make_j2(tmp_path, page=(("const runQ = () => viewRun ?", "const runQ = () => viewRunX ?"),
                                 ("async function openAgent(id){", "async function openAgentX(id){")))
    root = tmp_path / "repo"
    code, out, err = run(capsys, "--j2", j2, "--root", root)
    assert code == 1 and out == "" and not root.exists()
    assert err.startswith("DRIFT: J2's j2_ui.html no longer matches the port:\n")
    assert "  E4: expected 1 match, found 0\n" in err and "  E11: expected 1 match, found 0\n" in err
    assert "E1:" not in err and "E2a:" not in err and "No file was written" in err


def test_an_anchor_that_appears_twice_is_drift_too(tmp_path, capsys):
    d3_tag = '<script src="vendor/d3.min.js"></script>'
    j2 = make_j2(tmp_path, page=((d3_tag, d3_tag + "\n" + d3_tag),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and "  E3: expected 1 match, found 2\n" in err


def test_each_of_the_two_iframes_has_its_own_edit(tmp_path, capsys):
    j2 = make_j2(tmp_path, page=(('<iframe id="frame" title="Website preview" src="/site/latest"></iframe>', ""),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and "  E2a: expected 1 match, found 0\n" in err and "E2b" not in err
    j2 = make_j2(tmp_path / "b", page=(('<iframe id="sframe" title="Your result"></iframe>', '<iframe id="sframe" title="Your result" src="/site/latest"></iframe>'),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo2")
    assert code == 1 and "  E2b: expected 1 match, found 0\n" in err and "E2a" not in err


def test_the_counts_that_are_not_one_are_checked_both_ways(tmp_path, capsys):
    # E13b is three places (the tab's empty line, its status and the rail's status), E20d two (setView and the catalog's CAT.on)
    one_less = MINI_PAGE.replace('"no ranking records"', '"no ranking record"', 1)
    j2 = make_j2(tmp_path, page=((MINI_PAGE, one_less),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and "  E13b: expected 3 matches, found 2\n" in err
    j2 = make_j2(tmp_path / "b", page=(('if (location.pathname === "/library") return;', 'if (location.pathname === "/lib") return;'),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo2")
    assert code == 1 and "  E20d: expected 2 matches, found 1\n" in err
    j2 = make_j2(tmp_path / "c", page=(("</script>\n</body>", "</script>\n</body>\n<script>1</script>\n</body>"),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo3")
    assert code == 1 and "  E12: expected 1 match, found 2\n" in err


def test_a_page_without_the_font_and_style_block_is_drift_in_e1(tmp_path, capsys):
    j2 = make_j2(tmp_path, page=(("<style>", "<style data-x>"),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and "  E1: expected 1 match, found 0\n" in err


def test_the_style_block_that_page_script_writes_into_svg_can_never_be_taken_for_the_page_style(tmp_path, capsys):
    svg = "const svgStyle = `<svg><style>.a{fill:red}</style></svg>`;\n"
    j2 = make_j2(tmp_path, page=(("if (!CAT.on) poll();\n</script>", svg + "if (!CAT.on) poll();\n</script>"),))
    root = tmp_path / "repo"
    assert run(capsys, "--j2", j2, "--root", root)[0] == 0
    assert (root / "sutra_app/ui/static/css/j2.css").read_bytes() == MINI_CSS.encode()
    assert svg in read(root / "sutra_app/ui/pages/j2_ui.html")


def test_a_drifted_harness_stops_the_port_in_the_same_way(tmp_path, capsys):
    j2 = make_j2(tmp_path, render=(('"vendor", "d3.min.js"', '"lib", "d3.min.js"'),), layout=(("scripts[scripts.length - 1][1]", "scripts[0][1]"),))
    code, out, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and out == "" and err.startswith("DRIFT: J2's j2_ui_render.js no longer matches the port:\n  H2: expected 1 match, found 0\n")
    assert not (tmp_path / "repo").exists()
    (j2 / "j2_ui_render.js").write_bytes(MINI_RENDER.encode())
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and err.startswith("DRIFT: J2's j2_graph_layout.js no longer matches the port:\n  H1: expected 1 match, found 0\n")


def test_a_folder_that_is_not_an_extraction_of_prototypes_j2_exits_two_and_names_what_is_missing(tmp_path, capsys):
    j2 = make_j2(tmp_path)
    (j2 / "vendor" / "d3.min.js").unlink()
    (j2 / "j2_ui.html").unlink()
    code, out, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 2 and out == "" and err == f"error: {j2} is not an extraction of prototypes/j2: missing j2_ui.html, vendor/d3.min.js\n"
    assert not (tmp_path / "repo").exists()


def test_without_j2_the_script_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as stop:
        port.main([])
    assert stop.value.code == 2 and "--j2 is required" in capsys.readouterr().err


def test_the_help_and_the_docstring_say_what_j2_is_and_name_no_other_source(capsys):
    with pytest.raises(SystemExit):
        port.main(["--help"])
    help_text = capsys.readouterr().out
    assert "prototypes/j2" in help_text and "--commit" in help_text
    assert "prototypes/j2" in port.__doc__ and "git archive" in port.__doc__ and "--commit" in port.__doc__


def test_j2_is_only_read(tmp_path, capsys):
    j2 = make_j2(tmp_path)
    before = tree(j2)
    for path in [j2, *j2.rglob("*")]:
        path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        assert run(capsys, "--j2", j2, "--root", tmp_path / "repo")[0] == 0
        assert run(capsys, "--j2", j2, "--root", tmp_path / "repo", "--check")[0] == 0
    finally:
        for path in [j2, *j2.rglob("*")]:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    assert tree(j2) == before and sorted(p.name for p in j2.iterdir()) == ["j2_graph_layout.js", "j2_ui.html", "j2_ui_render.js", "vendor"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_flag_wins_over_the_head_of_a_repository_the_folder_happens_to_sit_in(tmp_path, capsys):
    j2 = make_j2(tmp_path)
    assert port.j2_commit(j2) == "unknown"                                             # a scratch folder is in no repository
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    git = lambda *args: subprocess.run(["git", "-C", str(j2), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True, env=env)
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "mini j2")
    head = subprocess.run(["git", "-C", str(j2), "rev-parse", "HEAD"], capture_output=True, text=True, env=env).stdout.strip()
    assert port.j2_commit(j2) == head[:7]                                              # no flag: git answers
    assert port.j2_commit(j2, PIN) == PIN[:7] != head[:7]                              # the flag names the pin
    assert f"ported J2 {head[:7]}:" in run(capsys, "--j2", j2, "--root", tmp_path / "repo")[1]
    assert f"ported J2 {PIN[:7]}:" in run(capsys, "--j2", j2, "--commit", PIN, "--root", tmp_path / "repo2")[1]


def test_a_missing_git_does_not_stop_the_port(tmp_path, capsys, monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(port.subprocess, "run", no_git)
    code, out, _ = run(capsys, "--j2", make_j2(tmp_path), "--root", tmp_path / "repo")
    assert code == 0 and out.startswith("ported J2 unknown:")


# ----------------------------------------------------------------------------------------------------------------------
# The script's own table
# ----------------------------------------------------------------------------------------------------------------------
def test_e13_words_are_the_four_pairs_of_the_design_and_the_script_prints_them_as_json(capsys):
    assert port.E13_WORDS == (
        ("How the Prioritiser ranked the work each cycle", "How the Prioritiser priced the work each cycle", 1),
        ("no ranking records", "no pricing records", 3),
        ("No ranking records in this run", "No pricing records in this run", 1),
        ("Funded, in the order it ranked them", "Funded, in registration order; Coordination sets the run order", 1),
    )
    code, out, _ = run(capsys, "--e13-json")
    assert code == 0 and json.loads(out) == [list(pair) for pair in port.E13_WORDS]


def test_the_edit_table_has_the_design_ids_and_counts():
    assert [(edit.id, edit.count) for edit in port.PAGE_EDITS] == [(edit, COUNTS[edit]) for edit in EDIT_IDS]
    assert len(port.PAGE_EDITS) == 28
    assert [(e.id, e.count) for e in port.RENDER_EDITS] == [("H1", 1), ("H2", 1), ("H3", 1)]
    assert [(e.id, e.count) for e in port.LAYOUT_EDITS] == [("H1", 1)]
    for retired in ("RUN_SETTINGS_EDITS", "OUTPUT_EDITS", "RUN_SETTINGS_CSS"):
        assert not hasattr(port, retired), retired


def test_the_modules_of_e12_are_the_ones_the_design_lists_in_order():
    assert list(port.MODULES) == MODULES


def test_no_edit_looks_for_text_another_edit_writes():
    for edit in port.PAGE_EDITS + port.RENDER_EDITS:
        for other in port.PAGE_EDITS + port.RENDER_EDITS:
            if other is not edit and isinstance(edit.old, str):
                assert edit.old not in other.new, (edit.id, other.id)


# ======================================================================================================================
# 3. The real extraction of prototypes/j2 (opt in)
# ======================================================================================================================
J2_CHECKOUT = os.environ.get("SUTRA_J2_CHECKOUT")


@pytest.mark.skipif(not J2_CHECKOUT, reason="set SUTRA_J2_CHECKOUT=<an extraction of prototypes/j2 of this repository> to compare with the real J2")
def test_a_fresh_port_of_the_real_j2_equals_the_committed_files_and_leaves_j2_alone(capsys):
    j2 = Path(J2_CHECKOUT)
    watched = [j2 / name for name in port.J2_FILES]
    before = [p.read_bytes() for p in watched]
    code, out, err = run(capsys, "--j2", j2, "--commit", PIN, "--check")
    assert (code, err) == (0, ""), out + err
    assert out.startswith("ok: the 28 anchors of the page edits match their counts, and the 7 committed files equal a fresh port of J2 ")
    assert [p.read_bytes() for p in watched] == before
