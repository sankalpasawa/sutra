#!/usr/bin/env python3
"""Port J2's department page to the app (work package UI-2; docs/design/ui.md section 5 and docs/design/j2-sync.md).

    scripts/py scripts/port_j2_ui.py --j2 /path/to/J2_Prototype            # write the ported files
    scripts/py scripts/port_j2_ui.py --j2 /path/to/J2_Prototype --check    # write nothing; exit 1 when the committed files
                                                                          # differ from a fresh port
    scripts/py scripts/port_j2_ui.py --e13-json                            # the E13 wording pairs as JSON (page_render.test.js)

The page is J2's `j2_ui.html` with 18 edits (E1 to E13 and the Run settings edits E14 to E18). Every edit is `Edit(id, old, new, count)`: `old` is a literal or a
compiled regex and `count` is the number of places it must match in J2's file. A count that is not met means J2 changed under
the port: the port stops, names every edit that no longer matches and writes nothing. Re-port; never hand-edit the copy.

What it writes, under `sutra_app/ui/` of the repository the script lives in (or `--root`):
    pages/j2_ui.html            the page after the 18 edits
    pages/j2_ui_render.js       J2's render harness, three small changes (sutra_ctx.js runs first; d3 and its tag test move)
    pages/j2_graph_layout.js    J2's layout harness, one change (sutra_ctx.js runs first)
    static/css/j2.css           the page's `<style>` block, byte for byte (the leading newline included)
    static/css/run-settings.css the styles of Run settings (edits E14 to E18)
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
    '<link rel="stylesheet" href="/ui/css/j2.css"><link rel="stylesheet" href="/ui/css/run-settings.css">',
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

# ----------------------------------------------------------------------------------------------------------------------
# E14 to E18: Run settings as the old Sutra repository's copy of the prototype has it (commit e7800503, docs/design/j2-sync-3.md).
# J2's own repository has the older tab (a theme switch, a "What to build" list, a "Saved runs" list and a link back to the Simple
# view). The new tab is two cards: Appearance (three swatch cards) and Runs (a status filter with counts, a search over title, brief
# and run id, rows grouped by date, 20 at a time), fed by `GET /api/runlist` (patch P13 of scripts/vendor_j2.py). Dropped: "What to
# build" (the Simple view's start page still has it: its `.outsel` select and `POST /api/output` stay) and "Back to simple view" (the
# rail's Chat item is that way). The old copy's Simple-view redesign is NOT ported: J2's repository does not have it.
# The styles are a fifth file, static/css/run-settings.css, so that j2.css stays J2's `<style>` block byte for byte.
# ----------------------------------------------------------------------------------------------------------------------
RUN_SETTINGS_CSS = r'''/* Run settings (page edits E14 to E18 of scripts/port_j2_ui.py; patch P13 serves /api/runlist): appearance cards and the run list.
   Written by the port script, not part of J2's `<style>` block (j2.css stays byte for byte J2's). Colours are the page's theme tokens;
   the two swatch colours are the same in both themes on purpose (they show what each theme looks like). */
:root{--swlight:#fbf8f3;--swdark:#1f1c18}
#pane-runsettings .runset{display:flex;flex-direction:column;gap:14px;align-items:stretch}
.rssec{background:var(--panel2);border:1px solid var(--line);border-radius:14px;padding:14px 16px}.rssec h3{margin:0 0 2px;font-size:15px}.rssec>p{margin:0 0 10px;color:var(--muted);font-size:13px}
.themecards{display:flex;flex-wrap:wrap;gap:8px}.themecards button{display:flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:12px;padding:9px 14px;font:inherit;cursor:pointer;min-width:104px}
.themecards button[aria-pressed=true]{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent);font-weight:600}
.themecards .sw{width:30px;height:20px;border-radius:6px;border:1px solid var(--line)}.sw-l{background:var(--swlight)}.sw-d{background:var(--swdark)}.sw-s{background:linear-gradient(90deg,var(--swlight) 50%,var(--swdark) 50%)}
.rtop{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:10px}.rtop h3{margin:0}.rtop h3 small{font-weight:400;color:var(--muted);font-size:12.5px;margin-left:6px}
.rtop input{margin-left:auto;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:10px;padding:7px 10px;font:inherit;width:220px;max-width:100%}
.newrun{background:var(--accent);color:var(--on);border:0;border-radius:10px;padding:8px 14px;font:inherit;font-weight:600;cursor:pointer}
.rfil{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}.rfil button{border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:99px;padding:4px 11px;font:inherit;font-size:12.5px;cursor:pointer}
.rfil button i{font-style:normal;margin-left:3px}.rfil button[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.runlist{max-height:min(62vh,640px);overflow:auto;display:grid;gap:8px;align-content:start;grid-auto-rows:max-content;padding-right:2px}
.rgrp{position:sticky;top:0;z-index:1;background:var(--panel2);font-size:11.5px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);padding:6px 2px 4px}
.runrow{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center;border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:9px 14px;cursor:pointer;text-align:left;font:inherit;color:var(--ink);width:100%}
.runrow:hover{border-color:var(--accent)}.runrow.cur{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,var(--panel))}
.runrow .ric{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--bg);color:var(--muted)}.runrow.cur .ric{color:var(--accent)}
.runrow .rmid{min-width:0;display:grid;grid-template-columns:auto minmax(0,1fr);column-gap:10px;align-items:baseline}
.runrow .rt{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.runrow code{font:12px var(--mono);color:var(--muted);background:var(--bg);border-radius:6px;padding:1px 6px;justify-self:start;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.runrow .rm{grid-column:1/-1;color:var(--muted);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.runrow .rr{display:flex;gap:8px;align-items:center}.runrow .ropen{font-size:12.5px;color:var(--accent);font-weight:600}.runrow.cur .ropen{color:var(--ink)}
.rst{font-size:11.5px;border-radius:99px;padding:2px 9px;white-space:nowrap}.rst.done{background:color-mix(in srgb,var(--ok) 16%,var(--panel));color:color-mix(in srgb,var(--ok) 55%,var(--ink))}
.rst.stopped{background:color-mix(in srgb,var(--warm2) 18%,var(--panel));color:color-mix(in srgb,var(--bad) 55%,var(--ink))}.rst.running{background:color-mix(in srgb,var(--accent) 16%,var(--panel));color:color-mix(in srgb,var(--accent) 55%,var(--ink))}
.rst.running::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);margin-right:5px;animation:rpulse 1.2s infinite}@keyframes rpulse{50%{opacity:.3}}
.runmore{margin:4px auto 2px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:99px;padding:7px 16px;font:inherit;font-size:13px;cursor:pointer}
.runnone{color:var(--muted);font-size:13px;padding:8px}
@media (max-width:600px){.runrow{grid-template-columns:auto minmax(0,1fr);gap:8px 10px;padding:8px 10px}.runrow .rr{grid-column:2}.rtop input{margin-left:0;flex:1 1 140px}.rssec{padding:12px}}
@media (prefers-reduced-motion:reduce){.rst.running::before{animation:none}}
'''
E14_OLD = r'''      <div class="runset">
        <div class="appear" id="appear">Appearance <span class="seg" role="group" aria-label="Appearance"><button type="button" data-themepick="light" aria-pressed="false">Light</button><button type="button" data-themepick="dark" aria-pressed="true">Dark</button><button type="button" data-themepick="system" aria-pressed="false">System</button></span></div>
        <label>What to build <select id="outsel" class="outsel" aria-label="What to build"></select></label>
        <label>Saved runs <select id="runsel" class="ghost" aria-label="Open a saved run"><option value="">Live run</option></select></label>
        <div class="runact"><button class="ghost" id="reset">New run</button> <a href="?view=simple" class="slink" id="to-simple">Back to simple view</a></div>
      </div>
'''
E14_NEW = r'''      <div class="runset">
        <section class="rssec" id="appear"><h3>Appearance</h3><p>Applies to this browser only.</p>
          <div class="themecards" role="group" aria-label="Appearance"><button type="button" data-themepick="light" aria-pressed="false"><span class="sw sw-l"></span>Light</button><button type="button" data-themepick="dark" aria-pressed="true"><span class="sw sw-d"></span>Dark</button><button type="button" data-themepick="system" aria-pressed="false"><span class="sw sw-s"></span>System</button></div></section>
        <section class="rssec runsec" aria-labelledby="runsh"><div class="rtop"><h3 id="runsh">Runs <small id="runcount"></small></h3><input type="search" id="runq" placeholder="Search runs" aria-label="Search runs by title, brief or run ID" autocomplete="off"><button type="button" class="newrun" id="reset">+ New run</button></div>
          <div class="rfil" role="group" aria-label="Filter by status"><button type="button" data-rf="all" aria-pressed="true">All <i></i></button><button type="button" data-rf="running" aria-pressed="false">Running <i></i></button><button type="button" data-rf="done" aria-pressed="false">Done <i></i></button><button type="button" data-rf="stopped" aria-pressed="false">Stopped <i></i></button></div>
          <div class="runlist" id="runlist"></div></section>
      </div>
'''
E15_OLD = r'''    if ($("outsel").__v !== s.output + s.total){ $("outsel").__v = s.output + s.total; $("outsel").innerHTML = outOptions(s); }
    $("outsel").disabled = !!s.total || !!s.saved;
'''
E16_OLD = r'''$("to-simple").onclick = e => { e.preventDefault(); setView("simple", true); };
'''
E17_OLD = r'''// Saved runs: pick one to open it read-only; the URL keeps ?run= so it can be reloaded or shared locally.
(async () => { try { const r = await (await fetch("/api/runs")).json();
  RUNLIST = r.runs || [];                 // the same list the Board story's compare picker offers
  $("runsel").innerHTML = `<option value="">Live run (${esc(r.live)})</option>` + r.runs.filter(x => x.id !== r.live)
    .map(x => `<option value="${esc(x.id)}">${esc(x.id)} · ${esc(x.status)} · ${esc(x.brief.slice(0, 50))}</option>`).join("");
  $("runsel").value = viewRun;
  if (!$("pane-story").hidden || STORY.entries.length) paint($("pane-story"), renderStory()); } catch (e) {} })();
$("runsel").onchange = () => { location.search = $("runsel").value ? "?run=" + encodeURIComponent($("runsel").value) : ""; };
'''
E17_NEW = r'''// Saved runs: the Board story's compare picker (/api/runs).
(async () => { try { const r = await (await fetch("/api/runs")).json();
  RUNLIST = r.runs || [];
  if (!$("pane-story").hidden || STORY.entries.length) paint($("pane-story"), renderStory()); } catch (e) {} })();
// Run settings' run list (/api/runlist, patch P13: every saved run of this team from its records), newest first under date headings; 20 at a time;
// status chips with counts, a search over title, brief and run id. Opening a run keeps the other URL parameters (the view), not the tab.
const RUNS = {all: [], live: "", f: "all", q: "", show: 20};
const RUNICON = {web: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 9h18"/><circle cx="6.5" cy="6.5" r=".6" fill="currentColor"/><circle cx="9" cy="6.5" r=".6" fill="currentColor"/></svg>`,
  doc: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 15.5h6"/></svg>`};
const runCur = () => viewRun || RUNS.live;
const runHref = id => { const q = new URLSearchParams(location.search); if (id) q.set("run", id); else q.delete("run"); q.delete("tab"); const s = q.toString(); return s ? "?" + s : ""; };
function runGroup(w){ if (!w) return "Older"; const t = new Date(), d = new Date(w), a = new Date(t.getFullYear(), t.getMonth(), t.getDate()), b = new Date(d.getFullYear(), d.getMonth(), d.getDate()), n = Math.round((a - b) / 864e5);
  return n <= 0 ? "Today" : n === 1 ? "Yesterday" : n < 7 ? "This week" : d.getMonth() === t.getMonth() && d.getFullYear() === t.getFullYear() ? "Earlier this month" : "Older"; }
const runWhen = w => { if (!w) return ""; const d = new Date(w); return d.toLocaleDateString("en-GB", {day: "numeric", month: "short", year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric"}) + " · " + w.slice(11, 16); };
const runShown = () => { const q = RUNS.q.trim().toLowerCase(); return RUNS.all.filter(x => (RUNS.f === "all" || x.status === RUNS.f) && (!q || (x.title + " " + x.brief + " " + x.id).toLowerCase().includes(q))); };
function renderRuns(){
  const L = runShown(), cur = runCur(); let h = "", g = "";
  document.querySelectorAll("[data-rf]").forEach(b => { b.querySelector("i").textContent = b.dataset.rf === "all" ? RUNS.all.length : RUNS.all.filter(x => x.status === b.dataset.rf).length;
    b.setAttribute("aria-pressed", String(b.dataset.rf === RUNS.f)); });
  $("runcount").textContent = L.length === RUNS.all.length ? plural(L.length, "run") : `${L.length} of ${plural(RUNS.all.length, "run")}`;
  L.slice(0, RUNS.show).forEach(x => { const G = runGroup(x.when); if (G !== g){ g = G; h += `<div class="rgrp">${G}</div>`; }
    const me = x.id === cur;
    h += `<button type="button" class="runrow${me ? " cur" : ""}" data-openrun="${esc(x.id)}"${me ? ' aria-current="true"' : ""} aria-label="${esc(x.title)}, ${esc(x.id)}, ${esc(x.status)}${me ? ", open now" : ""}"><span class="ric">${RUNICON[x.output === "website" ? "web" : "doc"]}</span>`
      + `<span class="rmid"><span class="rt">${esc(x.title)}</span><code>${esc(x.id)}</code><span class="rm">${esc([runWhen(x.when), x.brief].filter(Boolean).join(" · "))}</span></span>`
      + `<span class="rr"><span class="rst ${esc(x.status)}">${esc(x.status)}</span><span class="ropen">${me ? "Open now" : "Open"}</span></span></button>`; });
  if (L.length > RUNS.show) h += `<button type="button" class="runmore" id="runmore">Show ${Math.min(20, L.length - RUNS.show)} more · ${L.length - RUNS.show} left</button>`;
  $("runlist").innerHTML = h || `<div class="runnone">No runs match.</div>`;
}
(async () => { try { const r = await (await fetch("/api/runlist", {cache: "no-store"})).json(); RUNS.all = r.runs || []; RUNS.live = r.live || ""; } catch (e) {} renderRuns(); })();
$("runlist").addEventListener("click", e => {
  if (e.target.closest("#runmore")){ RUNS.show += 20; return renderRuns(); }
  const b = e.target.closest("[data-openrun]"); if (!b) return;
  if (b.dataset.openrun === runCur()) return showTab("map");      // the run already open
  location.search = runHref(b.dataset.openrun === RUNS.live ? "" : b.dataset.openrun); });
document.querySelectorAll("[data-rf]").forEach(b => b.onclick = () => { RUNS.f = b.dataset.rf; RUNS.show = 20; renderRuns(); });
$("runq").addEventListener("input", () => { RUNS.q = $("runq").value; RUNS.show = 20; renderRuns(); });
'''
E18_OLD = 'runsettings: "What to build, which run to open, and a new run."'
E18_NEW = 'runsettings: "How the app looks, and which run you are looking at."'
RUN_SETTINGS_EDITS: tuple[Edit, ...] = (
    Edit("E14", E14_OLD, E14_NEW, 1),          # the pane: two cards instead of the select lists
    Edit("E15", E15_OLD, "", 1),               # poll() filled and disabled the "What to build" select that is gone
    Edit("E16", E16_OLD, "", 1),               # the "Back to simple view" link is gone
    Edit("E17", E17_OLD, E17_NEW, 1),          # the saved-runs select becomes the run list
    Edit("E18", E18_OLD, E18_NEW, 1),          # the tab's hint
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
    ported = apply_edits(page, PAGE_EDITS + RUN_SETTINGS_EDITS, J2_PAGE)       # E1 matched exactly once, so the block is there
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
        "static/css/run-settings.css": RUN_SETTINGS_CSS,
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
        print(f"ok: the {len(PAGE_EDITS) + len(RUN_SETTINGS_EDITS)} anchors of the 18 page edits match their counts, and the {len(files)} committed files equal a fresh port of J2 {commit}")
        return 0
    write_files(args.root, files)
    print(f"ported J2 {commit}: wrote {len(files)} files under {UI_DIR}")
    for path, data in sorted(files.items()):
        print(f"  {path} ({len(data):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
