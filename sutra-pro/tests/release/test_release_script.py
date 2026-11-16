"""scripts/release.py (D242): the steps of docs/RELEASE.md as one command that stops at the first thing wrong.

git and gh are answered by a scripted fake (`FakeHub`) over a temporary copy of the version files, so what is tested is the order and the conditions: nothing reaches
`main` before CI is green, nothing is tagged before `main` has it, the notes go in only after the release runs are green, an existing tag is never touched, and a
failure at any step stops with a sentence that names it.
"""
import difflib
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import install_app                                                             # noqa: E402
import release as rel                                                          # noqa: E402

COPIED = ("pyproject.toml", "sutra_app/__init__.py", "desktop/package.json", "desktop/package-lock.json")
OLD_SHA, NEW_SHA = "a" * 40, "b" * 40


def make_tree(tmp_path: Path, version: str = "0.6.1") -> Path:
    """A folder with the four version files of the real tree (set to `version`) and nothing else."""
    tree = tmp_path / "tree"
    for name in COPIED:
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tree / name)
    rel.set_version(tree, version)
    return tree


# ================================================================ versions

def test_a_tag_is_stable_when_it_is_exactly_three_plain_integers():
    assert rel.parse_tag("sutra-pro-v0.6.1") == (0, 6, 1)
    assert rel.parse_tag("sutra-pro-v10.20.30") == (10, 20, 30)
    for bad in ("sutra-pro-v0.6.1-beta.1", "v0.6.1", "sutra-pro-v01.2.3", "sutra-pro-v1.2", "sutra-pro-v1.2.3.4", "sutra-pro-v1.2.x", ""):
        assert rel.parse_tag(bad) is None, bad


def test_the_newest_version_is_the_largest_number_and_next_counts_up_one_part():
    tags = ["sutra-pro-v0.9.0", "sutra-pro-v0.10.0", "sutra-pro-v0.10.1-beta.2", "sutra-pro-v0.2.7", "v9.9.9"]
    assert rel.newest_version(tags) == (0, 10, 0)
    assert rel.newest_version(["sutra-pro-v1.0.0-beta.1"]) is None
    assert rel.next_version((0, 6, 1), "patch") == "0.6.2"
    assert rel.next_version((0, 6, 1), "minor") == "0.7.0"
    assert rel.next_version((0, 6, 1), "major") == "1.0.0"
    with pytest.raises(rel.ReleaseError):
        rel.next_version((0, 6, 1), "huge")


def test_setting_the_version_changes_the_version_lines_and_nothing_else(tmp_path):
    tree = make_tree(tmp_path, "0.6.1")
    before = {name: (tree / name).read_text(encoding="utf-8") for name in COPIED}
    changed = rel.set_version(tree, "9.8.7")
    assert sorted(changed) == sorted(COPIED)
    expected_lines = {"pyproject.toml": 1, "sutra_app/__init__.py": 1, "desktop/package.json": 1, "desktop/package-lock.json": 2}
    for name in COPIED:
        after = (tree / name).read_text(encoding="utf-8")
        edits = [line for line in difflib.unified_diff(before[name].splitlines(), after.splitlines(), lineterm="", n=0) if line[:1] in "+-" and line[:3] not in ("+++", "---")]
        assert len(edits) == 2 * expected_lines[name], f"{name}: {edits}"
        assert all("9.8.7" in line or "0.6.1" in line for line in edits), edits
        assert after.count("9.8.7") == expected_lines[name]
    assert {name: found for name, found in rel.versions_in(tree).items()} == {name: ["9.8.7"] * expected_lines[name] for name in COPIED}
    assert rel.set_version(tree, "9.8.7") == [], "when the files already say it, nothing is written"


def test_a_version_that_is_not_three_plain_integers_is_refused_and_so_is_a_file_that_lost_its_line(tmp_path):
    tree = make_tree(tmp_path)
    for bad in ("1.2", "1.2.3-beta.1", "v1.2.3", "01.2.3", ""):
        with pytest.raises(rel.ReleaseError, match="X.Y.Z"):
            rel.set_version(tree, bad)
    (tree / "sutra_app" / "__init__.py").write_text("no version here\n")
    with pytest.raises(rel.ReleaseError, match="by hand"):
        rel.set_version(tree, "1.2.3")


def test_the_real_tree_says_one_version_in_all_four_places():
    found = rel.versions_in(ROOT)
    assert len({version for versions in found.values() for version in versions}) == 1, found
    assert len(found["desktop/package-lock.json"]) == 2


# ================================================================ the fake GitHub

class FakeHub:
    def __init__(self, tree: Path):
        self.tree = tree
        self.calls: list[list[str]] = []
        self.tags = ["sutra-pro-v0.6.0", "sutra-pro-v0.6.1", "sutra-pro-v0.6.1-beta.1"]
        self.remote_tags: list[str] = []
        self.head = OLD_SHA
        self.origin_main = OLD_SHA
        self.dirty = ""
        self.is_ancestor = True
        self.workflow_diff = ""
        self.staged: list[str] = []
        self.ci = [[]]                                       # what `gh run list --workflow sutra-pro-ci` answers, call after call (the last one repeats)
        self.runs = []                                       # what `gh run list --branch <tag>` answers, call after call
        self.release = {"isDraft": False, "isPrerelease": False, "url": "https://example.test/release", "tagName": "sutra-pro-v0.6.2", "body": "DOWNLOAD TABLE",
                        "assets": []}
        self.latest = [{"tagName": "v2.307.1-desktop", "isLatest": True}]
        self.push_main_ok = True
        self.edited_body = None

    def run(self, args, *, timeout=None, cwd=None, env=None):
        args = [str(item) for item in args]
        self.calls.append(args)
        if args[0] == "git":
            code, out, err = self.git(args[3:])
        elif args[0] == "gh":
            code, out, err = self.gh(args[1:])
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, code, out, err)

    def git(self, a):
        if a[:2] == ["status", "--porcelain"]:
            return 0, self.dirty, ""
        if a[0] in ("fetch", "commit"):
            if a[0] == "commit":
                self.head = NEW_SHA
                self.staged = []
            return 0, "", ""
        if a[0] == "merge-base":
            return (0 if self.is_ancestor else 1), "", ""
        if a[:2] == ["tag", "--list"]:
            return 0, "\n".join(self.tags), ""
        if a[0] == "ls-remote":
            return 0, "\n".join(f"{NEW_SHA}\t{ref}" for ref in self.remote_tags if ref in a[-1]), ""
        if a[0] == "diff" and "--cached" in a:
            return 0, "\n".join(self.staged), ""
        if a[0] == "diff":
            return 0, self.workflow_diff, ""
        if a[0] == "add":
            self.staged = [path for path in a[2:] if path != "docs/release-notes/0.6.2.md" or not self.notes_committed()]
            return 0, "", ""
        if a[:2] == ["rev-parse", "HEAD"]:
            return 0, self.head + "\n", ""
        if a[:2] == ["rev-parse", "origin/main"]:
            return 0, self.origin_main + "\n", ""
        if a[0] == "push":
            if a[-1].endswith(":refs/heads/main"):
                if not self.push_main_ok:
                    return 1, "", "remote: error: GH006: Protected branch update failed"
                self.origin_main = a[-1].split(":")[0]
            return 0, "", ""
        if a[:2] == ["tag", "-a"]:
            self.tags.append(a[2])
            return 0, "", ""
        raise AssertionError(a)

    committed_notes = False

    def notes_committed(self):
        return self.committed_notes

    def gh(self, a):
        if a[:2] == ["run", "list"] and "--workflow" in a:
            rows = self.ci[0] if len(self.ci) == 1 else self.ci.pop(0)
            return 0, json_text(rows), ""
        if a[:2] == ["run", "list"] and "--branch" in a:
            rows = self.runs[0] if len(self.runs) == 1 else self.runs.pop(0)
            return 0, json_text(rows), ""
        if a[:2] == ["release", "view"]:
            return 0, json_text(self.release), ""
        if a[:2] == ["release", "list"]:
            return 0, json_text(self.latest), ""
        if a[:2] == ["release", "edit"]:
            self.edited_body = Path(a[a.index("--notes-file") + 1]).read_text(encoding="utf-8")
            assert "--latest=false" in a
            return 0, "", ""
        raise AssertionError(a)


def json_text(value):
    import json
    return json.dumps(value)


def ci_row(status, conclusion=""):
    return {"databaseId": 1, "status": status, "conclusion": conclusion, "url": "https://example.test/ci/1"}


def release_rows(sha, **conclusions):
    return [{"databaseId": index, "workflowName": name, "status": "completed", "conclusion": conclusions.get(name, "success"), "headSha": sha,
             "url": f"https://example.test/run/{name}"} for index, name in enumerate(rel.RELEASE_WORKFLOWS)]


def all_assets(version):
    return [{"name": name} for name in rel.required_assets(version)]


@pytest.fixture
def hub(tmp_path, monkeypatch):
    tree = make_tree(tmp_path, "0.6.1")
    (tree / "docs" / "release-notes").mkdir(parents=True)
    (tree / "docs" / "release-notes" / "0.6.2.md").write_text("### What is new in 0.6.2\n\n- A thing.\n", encoding="utf-8")
    fake = FakeHub(tree)
    fake.release["assets"] = all_assets("0.6.2")
    fake.runs = [release_rows(NEW_SHA)]
    fake.ci = [[], [ci_row("in_progress")], [ci_row("completed", "success")]]
    installed = []
    monkeypatch.setattr(rel, "ROOT", tree)
    monkeypatch.setattr(rel, "run", fake.run)
    monkeypatch.setattr(rel, "network_env", lambda: None)
    monkeypatch.setattr(rel, "sleep", lambda seconds: None)
    monkeypatch.setattr(rel.install_app, "install_release", lambda tag, install_dir, **kw: installed.append((tag, install_dir, kw)) or 0)
    fake.installed = installed
    return fake


def go(*argv):
    return rel.main(list(argv))


def verbs(fake):
    """The calls that change something, in order, as short strings."""
    out = []
    for call in fake.calls:
        if call[0] == "git":
            sub = call[3:]
            if sub[0] in ("add", "commit"):
                out.append(sub[0])
            elif sub[0] == "push":
                out.append("push " + sub[-1].split(":")[-1].replace("refs/heads/", "").replace("refs/tags/", "tag "))
            elif sub[:2] == ["tag", "-a"]:
                out.append("tag " + sub[2])
        elif call[:3] == ["gh", "release", "edit"]:
            out.append("notes")
    return out


# ================================================================ the happy path

def test_a_release_is_committed_tested_landed_tagged_watched_noted_and_installed_in_that_order(hub, capsys):
    assert go("--trailer", "Co-Authored-By: A Helper <helper@example.test>") == 0
    assert verbs(hub) == ["add", "commit", "push release/0.6.2", "push main", "tag sutra-pro-v0.6.2", "push tag sutra-pro-v0.6.2", "notes"]
    assert rel.versions_in(hub.tree) == {name: ["0.6.2"] * (2 if name.endswith("lock.json") else 1) for name in COPIED}
    commit = next(call for call in hub.calls if call[3:4] == ["commit"])
    assert "Release: version 0.6.2" in commit[5] and commit[5].rstrip().endswith("Co-Authored-By: A Helper <helper@example.test>")
    added = next(call for call in hub.calls if call[3:4] == ["add"])
    assert sorted(added[5:]) == sorted([*COPIED, "docs/release-notes/0.6.2.md"]), "exactly the version files and the notes, never `git add -A`"
    tagged = next(call for call in hub.calls if call[3:5] == ["tag", "-a"])
    assert tagged[-1] == NEW_SHA and tagged[6] == "-m" and tagged[5] == "sutra-pro-v0.6.2", "an annotated tag on the commit CI tested"
    assert hub.edited_body == "### What is new in 0.6.2\n\n- A thing.\n\nDOWNLOAD TABLE", "the notes are in front of what the workflows wrote"
    assert hub.installed == [("sutra-pro-v0.6.2", install_app.DEFAULT_INSTALL_DIR, {"force": False})]
    out = capsys.readouterr().out
    assert "released: https://example.test/release" in out


def test_a_version_the_files_already_say_is_not_committed_again_and_green_ci_is_not_waited_for(hub):
    rel.set_version(hub.tree, "0.6.2")
    hub.committed_notes = True
    hub.ci = [[ci_row("completed", "success")]]
    hub.head = hub.origin_main = NEW_SHA
    assert go("--no-install") == 0
    assert verbs(hub) == ["add", "tag sutra-pro-v0.6.2", "push tag sutra-pro-v0.6.2", "notes"], "no commit, no branch, no push to main: it all was there already"
    assert hub.installed == []


def test_bump_and_version_choose_the_number(hub):
    hub.release["assets"] = all_assets("0.7.0")
    hub.release["tagName"] = "sutra-pro-v0.7.0"
    (hub.tree / "docs" / "release-notes" / "0.7.0.md").write_text("### What is new in 0.7.0\n")
    assert go("--bump", "minor", "--dry-run") == 0
    assert any("v0.7.0" in " ".join(call) for call in hub.calls if call[:3] == ["git", "-C", str(hub.tree)] and call[3] == "ls-remote")
    assert go("--version", "3.0.0", "--no-notes", "--dry-run") == 0
    with pytest.raises(SystemExit):
        go("--bump", "minor", "--version", "1.2.3")


def test_a_dry_run_changes_nothing(hub, capsys):
    before = {name: (hub.tree / name).read_text() for name in COPIED}
    assert go("--dry-run") == 0
    assert verbs(hub) == []
    assert {name: (hub.tree / name).read_text() for name in COPIED} == before
    out = capsys.readouterr().out
    assert "Release 0.6.2" in out and "sutra-pro-v0.6.2" in out and "dry run" in out


# ================================================================ what stops it

def refused(hub, capsys, *argv, match, code=1):
    assert go(*argv) == code
    err = capsys.readouterr().err
    assert match in err, err
    return err


def test_uncommitted_changes_and_an_origin_main_that_is_ahead_stop_it_before_anything_else(hub, capsys):
    hub.dirty = " M sutra_app/x.py"
    refused(hub, capsys, match="uncommitted")
    hub.dirty = ""
    hub.is_ancestor = False
    refused(hub, capsys, match="merge it")
    assert verbs(hub) == []


def test_a_version_that_is_already_tagged_points_at_the_install_command_and_is_never_touched(hub, capsys):
    hub.remote_tags = ["refs/tags/sutra-pro-v0.6.2"]
    err = refused(hub, capsys, match="already exists")
    assert "install_app.py release sutra-pro-v0.6.2" in err
    assert verbs(hub) == []
    hub.remote_tags = []
    refused(hub, capsys, "--version", "0.6.1", match="already exists")
    refused(hub, capsys, "--version", "0.5.9", "--no-notes", match="not newer")


def test_release_workflows_that_changed_since_the_last_release_need_a_beta_tag_first(hub, capsys):
    hub.workflow_diff = ".github/workflows/sutra-pro-release-macos.yml"
    err = refused(hub, capsys, match="beta tag")
    assert "sutra-pro-release-macos.yml" in err and "--allow-workflow-changes" in err
    assert verbs(hub) == []
    assert go("--allow-workflow-changes") == 0


def test_the_notes_are_required_unless_the_release_goes_without(hub, capsys):
    (hub.tree / "docs" / "release-notes" / "0.6.2.md").unlink()
    refused(hub, capsys, match="release notes")
    assert verbs(hub) == []
    assert go("--no-notes", "--no-install") == 0
    assert "notes" not in verbs(hub)


def test_a_red_ci_run_stops_before_main_and_before_the_tag(hub, capsys):
    hub.ci = [[ci_row("completed", "failure")]]
    err = refused(hub, capsys, match="failed")
    assert "nothing was tagged" in err and "https://example.test/ci/1" in err
    assert "push main" not in verbs(hub) and not any(verb.startswith("tag ") for verb in verbs(hub))


def test_a_ci_run_that_never_finishes_is_given_up_on_without_a_tag(hub, capsys, monkeypatch):
    hub.ci = [[ci_row("in_progress")]]
    ticks = iter(range(0, 10**7, 1800))
    monkeypatch.setattr(rel, "time", types.SimpleNamespace(monotonic=lambda: next(ticks)))          # only this module's clock, not the one pytest itself reads
    refused(hub, capsys, match="still running")
    assert not any(verb.startswith("tag ") for verb in verbs(hub))


def test_a_main_that_moved_or_is_protected_stops_before_the_tag(hub, capsys):
    hub.push_main_ok = False
    refused(hub, capsys, match="pushing to main was refused")
    assert not any(verb.startswith("tag ") for verb in verbs(hub))


def test_a_failed_release_run_names_the_workflow_and_keeps_the_tag(hub, capsys):
    hub.runs = [release_rows(NEW_SHA, **{"sutra-pro-release-windows": "failure"})]
    err = refused(hub, capsys, match="sutra-pro-release-windows failure")
    assert "gh workflow run" in err and "the tag stays" in err
    assert "notes" not in verbs(hub) and hub.installed == []


def test_the_release_runs_are_waited_for_until_all_three_are_done(hub, capsys):
    partial = [row for row in release_rows(NEW_SHA)[:1]]
    running = [{**row, "status": "in_progress", "conclusion": ""} for row in release_rows(NEW_SHA)[1:]]
    other_commit = release_rows("c" * 40)
    hub.runs = [other_commit, partial + running, release_rows(NEW_SHA)]
    assert go("--no-install") == 0
    out = capsys.readouterr().out
    assert "release runs: wheel completed, macos in_progress, windows in_progress" in out


def test_a_release_that_lacks_an_asset_or_is_a_draft_or_is_latest_is_refused(hub, capsys):
    def untagged():
        hub.tags = [tag for tag in hub.tags if tag != "sutra-pro-v0.6.2"]          # the fake remembers the tag a refused run made; the next try starts from the same state

    hub.release["assets"] = [asset for asset in all_assets("0.6.2") if asset["name"] != "Sutra-Pro-arm64.dmg"]
    refused(hub, capsys, match="lacks assets: Sutra-Pro-arm64.dmg")
    untagged()
    hub.release["assets"] = all_assets("0.6.2")
    hub.release["isPrerelease"] = True
    refused(hub, capsys, match="draft or a pre-release")
    untagged()
    hub.release["isPrerelease"] = False
    hub.latest = [{"tagName": "sutra-pro-v0.6.2", "isLatest": True}]
    refused(hub, capsys, match="marked Latest")
    assert hub.installed == []


def test_a_busy_app_leaves_the_release_published_and_says_so(hub, capsys, monkeypatch):
    def busy(tag, install_dir, **kw):
        raise install_app.Busy("Sutra Pro.app is working")

    monkeypatch.setattr(rel.install_app, "install_release", busy)
    assert go() == install_app.BUSY
    err = capsys.readouterr().err
    assert "the release is published, but" in err and "working" in err
    assert "notes" in verbs(hub), "the release itself was finished before the install was tried"


def test_force_and_the_install_folder_reach_the_install_step(hub):
    assert go("--force", "--install-dir", "/somewhere") == 0
    assert hub.installed == [("sutra-pro-v0.6.2", Path("/somewhere"), {"force": True})]


# ================================================================ the login

def test_a_pipeline_token_is_left_out_when_gh_is_signed_in_without_it(monkeypatch):
    rel._network.clear()
    monkeypatch.setenv("GITHUB_TOKEN", "limited")
    monkeypatch.setenv("GH_TOKEN", "limited")
    seen = []

    def run(args, *, timeout=None, cwd=None, env=None):
        seen.append((args, env))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(rel, "run", run)
    env = rel.network_env()
    assert env is not None and "GITHUB_TOKEN" not in env and "GH_TOKEN" not in env and "PATH" in env
    assert seen[0][0] == ["gh", "auth", "status"] and seen[0][1] is env
    rel._network.clear()

    def signed_out(args, *, timeout=None, cwd=None, env=None):
        return subprocess.CompletedProcess(args, 1, "", "not logged in")

    monkeypatch.setattr(rel, "run", signed_out)
    assert rel.network_env() is None, "with no login of its own the environment is left as it is"
    rel._network.clear()
    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.delenv("GH_TOKEN")
    monkeypatch.setattr(rel, "run", run)
    assert rel.network_env() is None
    rel._network.clear()
