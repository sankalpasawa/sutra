"""D242: the protocol every AI agent is told to follow (sutra-pro/AGENTS.md and the pointers to it) must stay true. It names scripts, documents, flags and the two apps'
identities; a rename that leaves one of them behind fails here, so the file an agent reads first is never the file that lies.
"""
import contextlib
import io
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
AGENTS = ROOT / "AGENTS.md"
sys.path.insert(0, str(ROOT / "scripts"))
import install_app                                                             # noqa: E402
import release                                                                 # noqa: E402

CHANNELS = json.loads((ROOT / "desktop" / "src" / "channels.json").read_text(encoding="utf-8"))
IN_A_REPOSITORY = (REPO / ".git").exists() and (REPO / "CLAUDE.md").is_file()      # the pointers at the repository root are not in an sdist or a bare copy


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def help_of(main, *argv) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as stop:
        main([*argv, "--help"])
    assert stop.value.code == 0
    return out.getvalue()


def test_the_protocol_is_where_every_tool_looks_and_the_pointers_lead_to_it():
    assert AGENTS.is_file() and text(AGENTS).startswith("# Sutra Pro: how any AI agent changes, tries, pushes and releases it")
    assert text(ROOT / "CLAUDE.md").strip() == "@AGENTS.md", "Claude Code imports the one file"
    if not IN_A_REPOSITORY:
        pytest.skip("the pointers at the repository root are not part of this copy")
    assert "sutra-pro/AGENTS.md" in text(REPO / "AGENTS.md"), "Codex, Cursor, Copilot and others read AGENTS.md at the root"
    assert "@AGENTS.md" in text(REPO / "GEMINI.md"), "Gemini CLI reads GEMINI.md"
    assert "sutra-pro/AGENTS.md" in text(REPO / "CLAUDE.md"), "Claude Code started at the root meets it too"


def test_the_protocol_says_the_three_things_the_owner_asked_for():
    body = text(AGENTS)
    assert "scripts/py scripts/install_app.py beta" in body, "a change can be tried by installing a beta locally"
    assert "scripts/py scripts/release.py" in body and "install_app.py release" in body, "a release is published on GitHub and then installed locally"
    assert "never published" in body.lower() or "never publish" in body.lower(), "the beta is local only"
    for name in (CHANNELS["stable"]["appName"] + ".app", CHANNELS["beta"]["appName"] + ".app", CHANNELS["stable"]["appId"], CHANNELS["beta"]["appId"],
                 "~/" + CHANNELS["stable"]["dataDirName"], "~/" + CHANNELS["beta"]["dataDirName"]):
        assert name in body, f"{name} (the two apps are installed together, so the protocol names both)"
    assert re.search(r"push", body, re.I) and "scripts/gate.sh" in body


def test_every_file_and_script_the_protocol_names_exists():
    body = text(AGENTS)
    missing = []
    for path in set(re.findall(r"`((?:scripts|docs|desktop|tests)/[\w./-]+?)`", body)):
        if "X.Y.Z" in path:                                                    # a name to fill in: docs/release-notes/X.Y.Z.md
            continue
        if not (ROOT / path).exists() and not (IN_A_REPOSITORY and (REPO / path).exists()):      # scripts/ownership-audit.sh is the repository's, not this folder's
            missing.append(path)
    for target in re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", body):
        if not target.startswith("http") and not (ROOT / target).exists():
            missing.append(target)
    assert not missing, f"AGENTS.md names files that are not there: {sorted(set(missing))}"


def test_every_option_the_protocol_and_the_release_doc_show_is_a_real_option():
    install_help = help_of(install_app.main) + " ".join(help_of(install_app.main, sub) for sub in ("beta", "release", "status"))
    release_help = help_of(release.main)
    doc = text(ROOT / "docs" / "RELEASE.md")
    section = doc[doc.index("## One Mac, two apps"):doc.index("## Cut a release")]
    other_tools = {"--channel", "--latest", "--notes-file", "--ref"}              # the packager's, gh's: shown beside ours, not ours
    seen = set()
    for name, words in (("AGENTS.md", text(AGENTS)), ("RELEASE.md", section)):
        for span in re.findall(r"`([^`\n]+)`", words):
            for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", span):
                if flag in other_tools:
                    continue
                seen.add(flag)
                assert flag in install_help + release_help, f"{name} shows {flag}, which neither install_app.py nor release.py has: `{span}`"
    assert {"--force", "--dry-run"} <= seen, f"the documents show these options: {sorted(seen)}"
    # the subcommands the protocol shows exist
    for sub in re.findall(r"install_app\.py (beta|release|status)", text(AGENTS)):
        assert help_of(install_app.main, sub)


def test_the_release_document_describes_the_two_apps_and_the_notes_folder_is_documented():
    doc = text(ROOT / "docs" / "RELEASE.md")
    assert "## One Mac, two apps: the beta and the release (D242)" in doc
    assert "docs/release-notes/X.Y.Z.md" in doc
    assert (ROOT / "docs" / "release-notes" / "README.md").is_file(), "release.py asks for a notes file per release; the folder says what goes in it"
    for name in (CHANNELS["beta"]["appName"], CHANNELS["beta"]["dataDirName"], CHANNELS["beta"]["appId"]):
        assert name in doc, name


def test_nothing_the_protocol_ships_names_a_person_or_a_home_folder():
    files = [AGENTS, ROOT / "CLAUDE.md", ROOT / "docs" / "release-notes" / "README.md", ROOT / "scripts" / "install_app.py", ROOT / "scripts" / "release.py",
             ROOT / "scripts" / "make_beta_icon.py", ROOT / "desktop" / "src" / "channel.js", ROOT / "desktop" / "src" / "channels.json"]
    for path in files:
        assert "/Users/" not in text(path), f"{path.name} holds a home folder path (write ~)"
