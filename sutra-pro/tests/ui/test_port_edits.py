"""UI-2: the port of J2's department page (docs/design/ui.md section 5, S3-web-10, docs/design/j2-sync.md).

Three groups, none of them needs a browser or the J2 checkout:
  1. the committed files (sutra_app/ui/pages/j2_ui.html, static/css/j2.css, static/vendor/*, the two harness copies): edit by
     edit (E1 to E13) against a table written out here, and the invariants the design lists;
  2. scripts/port_j2_ui.py on a miniature J2 built below: the same table holds for what the script produces, J2 drift stops the
     port, `--check`, J2 is never written, two ports give the same bytes;
  3. opt in with SUTRA_J2_CHECKOUT=<J2 checkout>: a fresh port of the real J2 equals the committed files (the work package's
     acceptance command does the same: scripts/py scripts/port_j2_ui.py --j2 <J2 checkout> --check).
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
           "chat_view", "node_panel", "dept_ext"]
# J2's 23 data routes (j2_server.py) and the prefix of the template viewer's route
J2_API = {"state", "runs", "call", "preview", "docs", "map", "plan", "library", "run-templates", "artifacts", "artifacts/tree",
          "artifact", "agent", "code", "story", "board", "audits", "refs", "say", "output", "reset", "playbooks/clear",
          "lessons/clear"}
E19_API = {"engine/settings"}          # edit E19: the start page's output select reads the engine's default (GET /api/engine/settings?dept=)
P13_API = {"runlist", "changes"}          # patch P13: read-only routes J2's own repository does not have (Run settings' run list)
EXTERNAL_REF = re.compile(r"""(?:src|href|action|poster|data-src)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE)
INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


PAGE = read(UI / "pages" / "j2_ui.html")


# ----------------------------------------------------------------------------------------------------------------------
# The table: per edit, what the ported page holds (fragment, how many times) and what it no longer holds.
# A fragment sometimes spans a neighbouring line: that pins where the new text was put.
# ----------------------------------------------------------------------------------------------------------------------
E1_HEAD = ('<link rel="stylesheet" href="/ui/css/j2.css"><link rel="stylesheet" href="/ui/css/run-settings.css">\n'
           '<link rel="stylesheet" href="/ui/css/sutra-graph.css"><link rel="stylesheet" href="/ui/css/sutra-panel.css">\n'
           "<!--SUTRA-BOOT-->\n"
           '<script src="/ui/js/sutra_ctx.js"></script>\n'
           "<script>/* the viewer's Appearance before the first paint")
E6_SHOWTAB = ('  const full = name === "map" || name === "graph" || name === "orgchart";\n'
              '  $("backmap").hidden = full; document.querySelector("#dview .wbar").hidden = full;'
              ' document.querySelector("#dview .work").classList.toggle("mapfit", full); if (name !== "map") railReveal(name);\n')
E6_PANES = ('"report","rundetails","runsettings","graph","orgchart"].forEach(t => $("pane-"+t).hidden = t !== name);\n'
            "  SutraCtx.tab(name);\n}")
E7_RAIL = ('<nav class="rail tabs" id="rail" role="tablist" aria-label="Sections" aria-orientation="vertical">\n'
           '  <div class="railhome"><a href="/" id="to-home">\u2190 All teams</a><b id="deptchip"></b></div>\n'
           '  <button role="tab" data-tab="map" aria-selected="true"><span>Map</span></button>\n'
           '  <button role="tab" data-tab="graph" aria-selected="false"><span>Workflow graph</span></button>\n'
           '  <button role="tab" data-tab="orgchart" aria-selected="false"><span>Org chart</span></button>\n'
           '  <button type="button" id="gochat">')
E12_TAIL = ("poll();\n</script>\n" + "".join(f'<script src="/ui/js/{name}.js"></script>\n' for name in MODULES) + "</body>\n</html>")

CASES = {
    "E1": ([(E1_HEAD, 1)], ["fonts.googleapis.com", "<style>\n/* Theme", ":root{color-scheme:dark", "</style>\n<script>/* the viewer"]),
    "E2": ([(f'<iframe id="sframe" title="Your website" data-src="/site/latest" sandbox="{SANDBOX}"></iframe>', 1),
            (f'<iframe id="frame" title="Website preview" data-src="/site/latest" sandbox="{SANDBOX}"></iframe>', 1)],
           ['title="Your website" src=', 'title="Website preview" src=']),
    "E3": ([('<script src="/ui/vendor/d3.min.js"></script>', 1)], ['<script src="vendor/d3.min.js">']),
    "E4": ([('const runQ = () => (viewRun ? "&run=" + encodeURIComponent(viewRun) : "")'
             ' + (SutraCtx.dept ? "&dept=" + encodeURIComponent(SutraCtx.dept) : "");', 1)],
           ["const runQ = () => viewRun ?"]),
    "E5": ([('$("stitle").textContent = SutraCtx.boot.dept_label || (s.doc ? "Your document team" : "Your website team");', 1)],
           ['$("stitle").textContent = s.doc']),
    "E6": ([(E6_SHOWTAB, 1), (E6_PANES, 1)], ['$("backmap").hidden = name === "map"', '"runsettings"].forEach']),
    "E7": ([(E7_RAIL, 1)], ['aria-orientation="vertical">\n  <button role="tab" data-tab="map"']),
    "E8": ([('<div class="pane" id="pane-map"></div>\n'
             '    <div class="pane" id="pane-graph" hidden></div><div class="pane" id="pane-orgchart" hidden></div>\n'
             '    <div class="pane" id="pane-style" hidden></div>', 1)],
           ['id="pane-map"></div>\n    <div class="pane" id="pane-style"']),
    "E9": ([('<aside id="agentdrawer" class="agentdrawer" hidden role="dialog" aria-labelledby="adtitle"></aside>\n'
             '<aside id="nodepanel" class="agentdrawer" hidden role="dialog" aria-labelledby="nptitle"></aside>\n'
             '<dialog id="detail">', 1)],
           ['aria-labelledby="adtitle"></aside>\n<dialog']),
    "E10": ([('return `j2pos:${SutraCtx.dept}:${(typeof viewRun !== "undefined" && viewRun) || "live"}:${v}`;', 1)],
            ["return `j2pos:${(typeof viewRun"]),
    "E11": ([("async function openAgent(id){\n  if (window.NodePanel && NodePanel.wants(id)) return NodePanel.openFunction(id);\n"
              '  if (MAPPIN){ MAPPIN = ""; paintMap(); }', 1)],
            ["async function openAgent(id){\n  if (MAPPIN)"]),
    "E12": ([(E12_TAIL, 1)], ["poll();\n</script>\n</body>"]),
    "E14": ([('<section class="rssec" id="appear"><h3>Appearance</h3>', 1), ('<div class="runlist" id="runlist"></div></section>', 1),
             ('<button type="button" class="newrun" id="reset">+ New run</button>', 1), ('data-rf="stopped"', 1),
             ('<button type="button" data-themepick="system" aria-pressed="false"><span class="sw sw-s"></span>System</button>', 1)],
            ['id="outsel"', 'id="runsel"', 'id="to-simple"', "Back to simple view", '<div class="appear"', "Saved runs <select"]),
    "E15": ([], ['$("outsel")']),
    "E16": ([], ['$("to-simple")']),
    "E17": ([('const RUNS = {all: [], live: "", f: "all", q: "", show: 20};', 1), ('fetch("/api/runlist", {cache: "no-store"})', 1),
             ("const runHref = id =>", 1), ("// Saved runs: the Board story's compare picker (/api/runs).", 1)],
            ['$("runsel")', "Saved runs: pick one to open it read-only"]),
    "E18": ([('runsettings: "How the app looks, and which run you are looking at."', 1)], ["What to build, which run to open"]),
    "E19a": ([('const OUTS = [["auto", "Let the team decide"], ["website", "Website"], ["prd", "PRD document"], ["project", "Project work"]];', 1)],
             ['const OUTS = [["website", "Website"], ["prd", "PRD document"]];']),
    "E19b": ([('let EFFOUT = "", PICKEDOUT = "";', 1), ('fetch("/api/engine/settings"', 1), ("const cur = PICKEDOUT || ", 1)],
             ['const outOptions = s => OUTS.map(']),
    "E19c": ([("  PICKEDOUT = e.target.value;\n  await fetch(\"/api/output\"", 1)], []),
    "E13a": ([("How the Prioritiser priced the work each cycle", 1)], ["How the Prioritiser ranked"]),
    "E13b": ([("no pricing records", 2)], ["no ranking records"]),
    "E13c": ([("No pricing records in this run", 1)], ["No ranking records"]),
    "E13d": ([("Funded, in registration order; Coordination sets the run order", 1)], ["Funded, in the order it ranked them"]),
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
@pytest.mark.parametrize("case", sorted(CASES))
def test_edit_is_in_the_committed_page(case):
    check_case(PAGE, case)


def test_there_are_nineteen_edits_and_e13_is_four_pairs_with_the_counts_one_two_one_one():
    assert sorted({re.sub(r"[a-d]$", "", case) for case in CASES}, key=lambda c: int(c[1:])) == [f"E{n}" for n in range(1, 20)]
    assert [CASES[f"E13{letter}"][0][0][1] for letter in "abcd"] == [1, 2, 1, 1]


def test_the_priorities_wording_changed_but_internal_names_did_not():
    assert "ranking" not in PAGE and "it ranked" not in PAGE
    assert "c.ranked" in PAGE and "ranked: ws.filter" in PAGE


def test_exactly_two_attribute_less_inline_scripts_and_the_page_script_is_the_last():
    scripts = INLINE_SCRIPT.findall(PAGE)
    assert len(scripts) == 2
    assert scripts[0].startswith("/* the viewer's Appearance before the first paint")
    assert scripts[1].startswith("\nconst WHO = {") and "function showTab(name)" in scripts[1] and scripts[1].rstrip().endswith("poll();")
    assert PAGE.index('<script src="/ui/vendor/d3.min.js"></script>') < PAGE.index(scripts[1]) < PAGE.index('<script src="/ui/js/sutra_events.js">')
    assert all("<script" not in script for script in scripts)  # neither writes a script tag, so the pattern above cannot be fooled


def test_the_boot_marker_is_in_the_head_before_the_context_script_and_occurs_once():
    head = PAGE[:PAGE.index("</head>")]
    assert PAGE.count("<!--SUTRA-BOOT-->") == 1 and head.count("<!--SUTRA-BOOT-->") == 1
    assert head.index("<!--SUTRA-BOOT-->") < head.index('<script src="/ui/js/sutra_ctx.js"></script>') < head.index("<script>")


def test_no_external_url_in_the_markup_and_no_cdn():
    assert not EXTERNAL_REF.search(PAGE)
    assert "googleapis" not in PAGE
    assert not re.search(r"url\(\s*[\"']?\s*(?:https?:)?//", PAGE)


def test_the_one_query_only_link_stays_relative_and_everything_else_in_href_is_a_hash_a_root_path_or_a_template():
    hrefs = re.findall(r'href="([^"]*)"', PAGE)
    assert hrefs.count("?view=detail") == 1 and hrefs.count("?view=simple") == 0       # E14 took "Back to simple view" away (the rail's Chat is the way)
    odd = [h for h in hrefs if h not in {"?view=detail", "#"} and not h.startswith("/")]
    assert odd == [], odd


def test_both_preview_iframes_wait_for_their_src_and_are_sandboxed_without_same_origin():
    tags = {m.group(1): m.group(0) for m in re.finditer(r'<iframe id="(sframe|frame)"[^>]*>', PAGE)}
    assert sorted(tags) == ["frame", "sframe"]
    for tag in tags.values():
        assert 'data-src="/site/latest"' in tag and f'sandbox="{SANDBOX}"' in tag
        assert not re.search(r'(?<![-\w])src=', tag) and "allow-same-origin" not in tag


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
    assert len(sites) == 30 and sites.count("artUrl(f)") == 2
    for site in sites:
        if site == "artUrl(f)":
            continue
        path = re.match(r"[`\"](/[^?$`\"]*)", site)
        assert path, site
        route = path.group(1)
        assert route.startswith("/api/") and (route[len("/api/"):] in J2_API | P13_API | E19_API or route == "/api/library/"), site
    assert "const artUrl = f => `/api/artifact?name=${encodeURIComponent(f)}${runQ()}`;" in PAGE


def test_the_page_uses_no_transport_the_fetch_wrapper_could_not_cover():
    for word in ("XMLHttpRequest", "EventSource", "WebSocket", "sendBeacon", "new Worker", "eval("):
        assert word not in PAGE, word


def test_the_style_sheet_is_the_moved_style_block_and_the_page_holds_none_of_it():
    css = read(UI / "static" / "css" / "j2.css")
    assert css.startswith("\n/* Theme: every colour of the page is a token here, a warm dark set (the default)")
    assert css.endswith("}\n") and ":root{color-scheme:dark;" in css and css.count("{") == css.count("}")
    assert "url(" not in css and "@import" not in css and "http" not in css
    assert ":root{color-scheme:dark;" not in PAGE and "/* Theme:" not in PAGE


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
MINI_CSS = "\n/* Theme: a miniature, with a middle dot \u00b7 and a trailing newline */\n:root{color-scheme:dark;--bg:#111}\n"
MINI_PAGE = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>J2 Department</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Mini&display=swap">
<style>{MINI_CSS}</style>
<script>/* the viewer's Appearance before the first paint (Run settings sets it): light, dark or system; dark by default */
document.documentElement.dataset.theme = "dark";</script>
</head>
<body class="simple">
<div id="sview">
  <header class="shead"><b id="stitle">Your website team</b><a href="?view=detail" class="slink" id="to-detail">See how it works</a></header>
  <section class="sprev"><iframe id="sframe" title="Your website" src="/site/latest"></iframe></section>
</div>
<div id="dview">
<nav class="rail tabs" id="rail" role="tablist" aria-label="Sections" aria-orientation="vertical">
  <button role="tab" data-tab="map" aria-selected="true"><span>Map</span></button>
  <button type="button" id="gochat"><span>Chat</span></button>
  <div class="railsub" id="railsub"></div>
</nav>
    <div class="pane preview" id="pane-preview" hidden><iframe id="frame" title="Website preview" src="/site/latest"></iframe></div>
    <div class="pane" id="pane-map"></div>
    <div class="pane" id="pane-style" hidden></div>
    <div class="pane" id="pane-runsettings" hidden>
@@E14@@    </div>
</div>
<aside id="agentdrawer" class="agentdrawer" hidden role="dialog" aria-labelledby="adtitle"></aside>
<dialog id="detail"></dialog>
<script src="vendor/d3.min.js"></script>
<script>
const WHO = {{user: ["Requester (you)", "R"]}};
const runQ = () => viewRun ? "&run=" + encodeURIComponent(viewRun) : "";
@@E19A@@
@@E19B@@
@@E19C@@
function renderSimple(s){{
  $("stitle").textContent = s.doc ? "Your document team" : "Your website team";
}}
const TABHINT = {{priorities: "How the Prioritiser ranked the work each cycle, what it deferred and why.", runsettings: "What to build, which run to open, and a new run."}};
function showTab(name){{
  $("wtitle").textContent = name;
  $("backmap").hidden = name === "map"; document.querySelector("#dview .wbar").hidden = name === "map"; document.querySelector("#dview .work").classList.toggle("mapfit", name === "map"); if (name !== "map") railReveal(name);
  ["preview","goal","workflows","conflicts","priorities","timeline","audit","charter","docs","artifacts","board","library","story","map","style","lessons","playbooks","report","rundetails","runsettings"].forEach(t => $("pane-"+t).hidden = t !== name);
}}
const motionKey = svg => {{
  return `j2pos:${{(typeof viewRun !== "undefined" && viewRun) || "live"}}:${{v}}`; }};
async function openAgent(id){{
  if (MAPPIN){{ MAPPIN = ""; paintMap(); }}
}}
const RAILSTATUS = {{priorities: s => !prioModel(s).has && "no ranking records"}};
function prioModel(s){{ return {{status: !has ? "no ranking records" : "some"}}; }}
function renderPriorities(s){{
  if (!p.has) return `<p class="empty">No ranking records in this run: nothing was recorded.</p>`;
  return `<h4>Funded, in the order it ranked them</h4>`;
}}
@@E15@@@@E16@@@@E17@@poll();
</script>
</body>
</html>
"""
MINI_PAGE = (MINI_PAGE.replace("@@E14@@", port.E14_OLD).replace("@@E15@@", port.E15_OLD).replace("@@E16@@", port.E16_OLD)
             .replace("@@E17@@", port.E17_OLD).replace("@@E19A@@", port.E19A_OLD).replace("@@E19B@@", port.E19B_OLD)
             .replace("@@E19C@@", port.E19C_OLD))
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
           "static/css/run-settings.css", "static/vendor/README.md", "static/vendor/d3-LICENSE", "static/vendor/d3.min.js"]


def make_j2(base: Path, **replace: tuple[tuple[str, str], ...]) -> Path:
    """A J2 checkout in miniature. `replace` swaps text in a file: page=((old, new), ...), render=..., layout=..."""
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


def test_the_port_writes_the_eight_files_under_sutra_app_ui(ported):
    _, root = ported
    assert sorted(tree(root)) == sorted(f"sutra_app/ui/{name}" for name in OUTPUTS)


@pytest.mark.parametrize("case", sorted(CASES))
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
    assert (code, err) == (0, "") and out.startswith("ok: ") and "8 committed files equal a fresh port of J2 " in out
    assert tree(root) == before


def test_check_fails_and_names_a_changed_file(ported, capsys):
    j2, root = ported
    page = root / "sutra_app/ui/pages/j2_ui.html"
    page.write_bytes(page.read_bytes() + b" ")
    code, out, err = run(capsys, "--j2", j2, "--root", root, "--check")
    assert code == 1 and out == "" and "differ from a fresh port" in err and "differs: sutra_app/ui/pages/j2_ui.html" in err
    assert err.count("differs:") == 1 and "missing:" not in err


def test_check_notices_a_change_in_each_of_the_eight_files(ported, capsys):
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
    assert code == 1 and err.count("missing:") == 8 and tree(root) == {}


def test_the_port_replaces_files_that_are_there(ported, capsys):
    j2, root = ported
    page = root / "sutra_app/ui/pages/j2_ui.html"
    page.write_bytes(b"hand edited")
    assert run(capsys, "--j2", j2, "--root", root)[0] == 0
    assert run(capsys, "--j2", j2, "--root", root, "--check")[0] == 0 and page.read_bytes() != b"hand edited"


def test_the_port_prints_what_it_wrote(tmp_path, capsys):
    root = tmp_path / "repo"
    code, out, _ = run(capsys, "--j2", make_j2(tmp_path), "--root", root)
    assert code == 0 and out.startswith("ported J2 ") and "wrote 8 files under sutra_app/ui" in out
    assert "pages/j2_ui.html (" in out and "static/vendor/d3.min.js (" in out


def test_drift_stops_the_port_names_every_edit_with_its_counts_and_writes_nothing(tmp_path, capsys):
    j2 = make_j2(tmp_path, page=(("const runQ = () => viewRun ?", "const runQ = () => viewRunX ?"),
                                 ("async function openAgent(id){", "async function openAgentX(id){")))
    root = tmp_path / "repo"
    code, out, err = run(capsys, "--j2", j2, "--root", root)
    assert code == 1 and out == "" and not root.exists()
    assert err.startswith("DRIFT: J2's j2_ui.html no longer matches the port:\n")
    assert "  E4: expected 1 match, found 0\n" in err and "  E11: expected 1 match, found 0\n" in err
    assert "E1:" not in err and "E2:" not in err and "No file was written" in err


def test_an_anchor_that_appears_twice_is_drift_too(tmp_path, capsys):
    d3_tag = '<script src="vendor/d3.min.js"></script>'
    j2 = make_j2(tmp_path, page=((d3_tag, d3_tag + "\n" + d3_tag),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and "  E3: expected 1 match, found 2\n" in err


def test_the_two_iframes_are_both_needed_for_e2(tmp_path, capsys):
    j2 = make_j2(tmp_path, page=(('<iframe id="frame" title="Website preview" src="/site/latest"></iframe>', ""),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and "  E2: expected 2 matches, found 1\n" in err


def test_a_page_without_the_font_and_style_block_is_drift_in_e1(tmp_path, capsys):
    j2 = make_j2(tmp_path, page=(("<style>", "<style data-x>"),))
    code, _, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 1 and "  E1: expected 1 match, found 0\n" in err


def test_the_style_block_that_page_script_writes_into_svg_can_never_be_taken_for_the_page_style(tmp_path, capsys):
    svg = "const svgStyle = `<svg><style>.a{fill:red}</style></svg>`;\n"
    j2 = make_j2(tmp_path, page=(("poll();\n</script>", svg + "poll();\n</script>"),))
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


def test_a_folder_that_is_not_a_j2_checkout_exits_two_and_names_what_is_missing(tmp_path, capsys):
    j2 = make_j2(tmp_path)
    (j2 / "vendor" / "d3.min.js").unlink()
    (j2 / "j2_ui.html").unlink()
    code, out, err = run(capsys, "--j2", j2, "--root", tmp_path / "repo")
    assert code == 2 and out == "" and err == f"error: {j2} is not a J2 checkout: missing j2_ui.html, vendor/d3.min.js\n"
    assert not (tmp_path / "repo").exists()


def test_without_j2_the_script_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as stop:
        port.main([])
    assert stop.value.code == 2 and "--j2 is required" in capsys.readouterr().err


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
def test_the_j2_commit_is_reported_in_short_form_and_unknown_when_it_is_not_a_repository(tmp_path, capsys):
    j2 = make_j2(tmp_path)
    assert port.j2_commit(j2) == "unknown"
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    git = lambda *args: subprocess.run(["git", "-C", str(j2), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True, env=env)
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "mini j2")
    head = subprocess.run(["git", "-C", str(j2), "rev-parse", "HEAD"], capture_output=True, text=True, env=env).stdout.strip()
    assert port.j2_commit(j2) == head[:7]
    assert f"ported J2 {head[:7]}:" in run(capsys, "--j2", j2, "--root", tmp_path / "repo")[1]


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
        ("no ranking records", "no pricing records", 2),
        ("No ranking records in this run", "No pricing records in this run", 1),
        ("Funded, in the order it ranked them", "Funded, in registration order; Coordination sets the run order", 1),
    )
    code, out, _ = run(capsys, "--e13-json")
    assert code == 0 and json.loads(out) == [list(pair) for pair in port.E13_WORDS]


def test_the_edit_table_has_the_design_ids_and_counts():
    counts = {edit.id: edit.count for edit in port.PAGE_EDITS}
    assert list(counts) == ["E1", "E2", "E3", "E4", "E5", "E6a", "E6b", "E7", "E8", "E9", "E10", "E11", "E12",
                            "E13a", "E13b", "E13c", "E13d"]
    assert [(e.id, e.count) for e in port.OUTPUT_EDITS] == [("E19a", 1), ("E19b", 1), ("E19c", 1)]
    assert counts["E2"] == 2 and [counts[f"E13{x}"] for x in "abcd"] == [1, 2, 1, 1]
    assert all(count == 1 for edit, count in counts.items() if edit not in {"E2", "E13b"})
    assert [(e.id, e.count) for e in port.RENDER_EDITS] == [("H1", 1), ("H2", 1), ("H3", 1)]
    assert [(e.id, e.count) for e in port.LAYOUT_EDITS] == [("H1", 1)]


def test_no_edit_looks_for_text_another_edit_writes():
    for edit in port.PAGE_EDITS + port.RENDER_EDITS:
        for other in port.PAGE_EDITS + port.RENDER_EDITS:
            if other is not edit and isinstance(edit.old, str):
                assert edit.old not in other.new, (edit.id, other.id)


# ======================================================================================================================
# 3. The real J2 (opt in)
# ======================================================================================================================
J2_CHECKOUT = os.environ.get("SUTRA_J2_CHECKOUT")


@pytest.mark.skipif(not J2_CHECKOUT, reason="set SUTRA_J2_CHECKOUT=<J2 checkout> to compare with the real J2")
def test_a_fresh_port_of_the_real_j2_equals_the_committed_files_and_leaves_j2_alone(capsys):
    j2 = Path(J2_CHECKOUT)
    watched = [j2 / name for name in port.J2_FILES]
    before = [p.read_bytes() for p in watched]
    code, out, err = run(capsys, "--j2", j2, "--check")
    assert (code, err) == (0, ""), out + err
    assert [p.read_bytes() for p in watched] == before
