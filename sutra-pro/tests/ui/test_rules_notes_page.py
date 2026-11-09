"""The pages that carry the standing rules and the owner's notes (GAP2 rules-notes). No browser: these read the files the way test_home.py does, so
the merge gate catches a script that is not loaded, loaded too late, or a hook that was lost. The views' words are tested in notes_view.test.js and
rules_view.test.js; the routes in tests/orchestrator/test_owner_notes.py and test_standing_rules.py."""
import re
from pathlib import Path

UI = Path(__file__).resolve().parents[2] / "sutra_app" / "ui"
JS = UI / "static" / "js"
HOME = (UI / "pages" / "home.html").read_text(encoding="utf-8")
HOME_JS = (JS / "home.js").read_text(encoding="utf-8")
PANEL_JS = (JS / "node_panel.js").read_text(encoding="utf-8")
DEPT_JS = (JS / "dept_ext.js").read_text(encoding="utf-8")


def scripts() -> list[str]:
    return re.findall(r'<script src="/ui/js/([\w.]+\.js)"', HOME)


def test_home_loads_the_two_views_after_settings_and_before_the_page_script():
    found = scripts()
    for name in ("notes_view.js", "rules_view.js"):
        assert (JS / name).is_file() and found.count(name) == 1, name
        assert found.index("settings_view.js") < found.index(name) < found.index("home.js"), name
    assert "root.RulesView" in PANEL_JS and "RulesView" not in PANEL_JS.split("(function (root)")[0]    # the panel reads the global when it paints, so the order is free


def test_the_settings_pane_has_the_notes_group_a_rail_button_and_the_painting_hook():
    pane = HOME.split('id="pane-settings"')[1].split("</section>")[0]
    assert '<div id="set-notes"></div>' in pane and pane.index("set-engine") < pane.index("set-notes")
    assert re.search(r'<button[^>]*data-pane="settings"[^>]*data-group="notes"[^>]*><span>Notes</span></button>', HOME)
    assert 'ctx.paint($("set-notes"), NV().notesHtml(NS))' in HOME_JS and "paintNotes();" in HOME_JS.split("function renderSettings()")[1].split("}")[0]
    assert "if (NS.data === null) loadNotes();" in HOME_JS


def test_every_note_button_the_view_draws_is_handled_by_home():
    drawn = set(re.findall(r'data-act="(note-[a-z]+)"', (JS / "notes_view.js").read_text(encoding="utf-8")))
    assert drawn == {"note-add", "note-edit", "note-save", "note-cancel", "note-forget"}
    assert 'act.indexOf("note-") === 0' in HOME_JS.split("function onSettingsClick")[1].split("/* ----")[0]
    handled = HOME_JS.split("async function noteAct")[1].split("function renderSettings")[0]
    for act in drawn - {"note-forget"}:                       # forget is the one that needs no fields: it falls to the last branch
        assert f'"{act}"' in handled, act


def test_the_rules_block_is_drawn_for_a_department_only_and_its_buttons_are_handled_by_the_panel():
    assert 'st.node.kind === "department"' in PANEL_JS.split("function paintRules")[1].split("async function loadTeamRules")[0]
    drawn = set(re.findall(r'data-act="(rules-[a-z]+)"', (JS / "rules_view.js").read_text(encoding="utf-8")))
    assert drawn == {"rules-add", "rules-remove", "rules-pack"}
    on_rules = PANEL_JS.split("async function onRules")[1].split("function paintBody")[0]
    for act in drawn:
        assert f'"{act}"' in on_rules, act
    assert 'name.indexOf("rules-") === 0' in PANEL_JS.split("function onClick")[1].split("// J2's convention")[0]
    assert "keepRulesDraft(el);\n      paintTo(el, html);\n      paintRules(el);" in PANEL_JS               # the typed rule survives a repaint of the node


def test_a_saved_add_empties_the_field_and_every_opening_reads_the_rules_again():
    """Two behaviours the node panel's glue must keep (no browser here, so the source is read): `keepRulesDraft` reads the LIVE field on every repaint,
    so a saved add that only cleared `rules.draft` would get the line just added back in the box (and a second Add then says "already has this rule");
    and the rules of a team opened before are not shown again from memory, because a pick made in the org chat since then would not show and a save
    would be built from a stale list."""
    on_rules = PANEL_JS.split("async function onRules")[1].split("function paintBody")[0]
    saved = on_rules.split("if (out.ok) {")[1].split("} else {")[0]
    assert 'field.value = ""' in saved and saved.index('field.value = ""') < saved.index("rules.saved"), "a saved add must empty the live field"
    refused = on_rules.split("} else {")[1].split("if (st && st.tab")[0]
    assert "rules.error = out.error" in refused and "if (out.data) rules.data = out.data" in refused, "a list another window changed is shown as it is now"
    assert "rules.draft = null" not in refused, "what was typed stays beside the sentence"
    assert "added = text;" in on_rules.split('name === "rules-add"')[1].split("rules-remove")[0]       # only an add empties it: a rule typed and not yet added stays
    opened = PANEL_JS.split("async function open(nodeId, tab, freshGraph, forceSid)")[1].split("paintAll();")[0]
    assert 'rules = noRules("");' in opened, "open() must forget the rules an earlier opening read"


def test_a_team_page_loads_rules_view_from_dept_ext_because_the_j2_page_is_not_edited():
    assert '"rules_view"' in DEPT_JS.split("function drawers")[1].split("if (S.panel === null)")[0]
    page = (UI / "pages" / "j2_ui.html").read_text(encoding="utf-8")
    assert "rules_view" not in page and "notes_view" not in page                                    # the frozen J2 page is untouched


def test_neither_view_nor_its_styles_reach_for_a_colour_that_is_not_a_token():
    for name in ("notes_view.js", "rules_view.js"):
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b|rgb\(|style=", (JS / name).read_text(encoding="utf-8")), name
    shell = (UI / "static" / "css" / "sutra-shell.css").read_text(encoding="utf-8").split("the owner's notes group")[1]
    panel = (UI / "static" / "css" / "sutra-panel.css").read_text(encoding="utf-8").split("the standing rules of a team")[1]
    for css in (shell, panel):
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b|rgb\(", css)
