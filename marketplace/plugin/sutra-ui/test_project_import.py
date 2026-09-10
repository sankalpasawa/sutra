"""test_project_import.py -- Claude projects become departments, correctly.

Run:  .venv/bin/python -m pytest test_project_import.py -q
      (or plain: .venv/bin/python test_project_import.py)

The tests that matter here are the ones about DATA LOSS and WRONG ADDRESSES:
a project whose real path is recovered from the transcript rather than decoded
from the lossy folder name; scratch paths that must never become departments;
and a resolver that answers with the nearest department rather than a true but
useless ancestor. The registry ones run against an isolated SUTRA_NATIVE_HOME
so they never touch the operator's own tree.
"""
import json
import os
import tempfile
from pathlib import Path

import pytest


def _fresh_engine(tmp):
    """project_import + placement_engine bound to an isolated registry.

    SUTRA_NATIVE_HOME is read at import time by the engine, so the modules are
    re-imported after the env var is set rather than merely patched."""
    import importlib
    import sys
    os.environ["SUTRA_NATIVE_HOME"] = str(tmp)
    for mod in ("placement_engine", "project_import"):
        if mod in sys.modules:
            del sys.modules[mod]
    import placement_engine as E
    import project_import as P
    importlib.reload(E)
    return P, E


def _session(dirpath, name, cwd, extra_lines=0):
    """A minimal Claude transcript: a preamble line with no cwd, then a line
    carrying it -- the real shape (cwd appears on line 2, not line 1)."""
    dirpath.mkdir(parents=True, exist_ok=True)
    f = dirpath / (name + ".jsonl")
    lines = [json.dumps({"type": "summary"})]
    lines += [json.dumps({"type": "noise", "i": i}) for i in range(extra_lines)]
    lines.append(json.dumps({"type": "user", "cwd": cwd}))
    f.write_text("\n".join(lines) + "\n")
    return f


# ------------------------------------------------------------- discovery ---

def test_cwd_comes_from_the_transcript_not_the_folder_name(tmp_path):
    """The folder name is lossy: "-a-b-ai-dev-manager" cannot be decoded back
    to a path, because "-" is both the separator and a literal character. The
    real cwd is read out of the file, so a directory containing spaces or
    hyphens survives intact."""
    import project_import as P
    projects = tmp_path / "projects"
    real = "/Users/x/Desktop/UI design documents."      # spaces AND a trailing dot
    _session(projects / "-Users-x-Desktop-UI-design-documents-", "s1", real)

    kept, _ = P.discover(projects_dir=projects, home="/Users/x",
                             desktop_dir=tmp_path/"nodesk", config_path=tmp_path/"nocfg")

    assert [r["cwd"] for r in kept] == [real]


def test_scratch_and_home_are_never_departments(tmp_path):
    """13 of 38 folders on the founder's machine were /private/tmp scratchpads
    and one was the home directory itself. Importing either buries the real
    projects; the home directory additionally would parent everything under
    it via the containment rule."""
    import project_import as P
    projects = tmp_path / "projects"
    _session(projects / "-private-tmp-scratch", "s1", "/private/tmp/scratch")
    _session(projects / "-Users-x", "s2", "/Users/x")
    _session(projects / "-Users-x-work-real", "s3", "/Users/x/work/real")

    kept, skipped = P.discover(projects_dir=projects, home="/Users/x",
                             desktop_dir=tmp_path/"nodesk", config_path=tmp_path/"nocfg")

    assert [r["cwd"] for r in kept] == ["/Users/x/work/real"]
    assert {s["why"] for s in skipped} == {"scratch path", "home directory, not a project"}


def test_an_empty_transcript_folder_no_source_claims_is_not_a_project(tmp_path):
    """An empty ~/.claude/projects folder has no cwd to recover. If no OTHER
    store names it either, nothing on the machine claims it exists, so it is
    not discovered at all -- there is no reason to state about a project that
    no source asserts."""
    import project_import as P
    projects = tmp_path / "projects"
    (projects / "-Users-x-empty").mkdir(parents=True)
    _session(projects / "-Users-x-real", "s1", "/Users/x/real")

    kept, skipped = P.discover(projects_dir=projects, home="/Users/x",
                             desktop_dir=tmp_path/"nodesk", config_path=tmp_path/"nocfg")

    assert [r["cwd"] for r in kept] == ["/Users/x/real"]
    assert skipped == []


def test_a_project_with_no_sessions_still_counts_if_the_config_remembers_it(tmp_path):
    """The case that broke the first version. hokage-desk, kaguya,
    nakama-cli-suite and sovereign-ai have no transcripts on the founder's
    machine and ARE projects -- ~/.claude.json remembers them, and Claude
    lists them. Reading only the transcript folders lost every one."""
    import project_import as P
    cfg = tmp_path / "claude.json"
    cfg.write_text(json.dumps({"projects": {"/Users/x/work/kaguya": {}}}))

    kept, _ = P.discover(projects_dir=tmp_path / "noprojects", home="/Users/x",
                         desktop_dir=tmp_path / "nodesk", config_path=cfg)

    assert [r["cwd"] for r in kept] == ["/Users/x/work/kaguya"]
    assert kept[0]["sessions"] == 0
    assert kept[0]["sources"] == ["config"]


def test_a_desktop_only_project_is_found(tmp_path):
    """bahi-khata, cover-letter and lenovo-case-study exist ONLY in the desktop
    app's session store. Missing that store is what made the department list
    disagree with the project list the operator was looking at."""
    import project_import as P
    desk = tmp_path / "desk" / "acct" / "ws"
    desk.mkdir(parents=True)
    (desk / "local_a.json").write_text(json.dumps(
        {"sessionId": "local_a", "cwd": "/Users/x/work/bahi-khata"}))
    (desk / "local_b.json").write_text(json.dumps(
        {"sessionId": "local_b", "cwd": "/Users/x/work/bahi-khata"}))

    kept, _ = P.discover(projects_dir=tmp_path / "noprojects", home="/Users/x",
                         desktop_dir=tmp_path / "desk", config_path=tmp_path / "nocfg")

    assert [r["cwd"] for r in kept] == ["/Users/x/work/bahi-khata"]
    assert kept[0]["sessions"] == 2, "both desktop sessions must count"


def test_a_worktree_folds_into_the_repo_it_belongs_to(tmp_path):
    """A worktree is a checkout OF a repo, not a project beside it. Left alone
    it becomes a department named after a generated branch slug
    ("zen-hodgkin-87a245"), which is noise the operator never created."""
    import project_import as P
    desk = tmp_path / "desk" / "acct" / "ws"
    desk.mkdir(parents=True)
    # originCwd is what the desktop store records for a worktree session.
    (desk / "local_a.json").write_text(json.dumps(
        {"sessionId": "local_a",
         "cwd": "/Users/x/work/portfolio/.claude/worktrees/zen-hodgkin-87a245",
         "originCwd": "/Users/x/work/portfolio"}))
    cfg = tmp_path / "claude.json"
    # the config stores the RAW worktree path, so it is collapsed here too
    cfg.write_text(json.dumps({"projects": {
        "/Users/x/work/portfolio/.claude/worktrees/zen-hodgkin-87a245": {}}}))

    kept, _ = P.discover(projects_dir=tmp_path / "noprojects", home="/Users/x",
                         desktop_dir=tmp_path / "desk", config_path=cfg)

    assert [r["cwd"] for r in kept] == ["/Users/x/work/portfolio"]
    assert kept[0]["sources"] == ["config", "desktop"], \
        "both stores must fold onto the same repo, not two departments"


def test_sessions_sum_across_stores_for_one_project(tmp_path):
    """One project worked on from both the CLI and the desktop app has its
    counts added, not overwritten -- the count is what the department heading
    shows, and a heading that reports half the work is wrong."""
    import project_import as P
    projects = tmp_path / "projects"
    _session(projects / "-Users-x-work-sutra", "s1", "/Users/x/work/sutra")
    _session(projects / "-Users-x-work-sutra", "s2", "/Users/x/work/sutra")
    desk = tmp_path / "desk" / "acct" / "ws"
    desk.mkdir(parents=True)
    (desk / "local_a.json").write_text(json.dumps(
        {"sessionId": "local_a", "cwd": "/Users/x/work/sutra"}))

    kept, _ = P.discover(projects_dir=projects, home="/Users/x",
                         desktop_dir=tmp_path / "desk", config_path=tmp_path / "nocfg")

    assert len(kept) == 1, "one project, not one per store"
    assert kept[0]["sessions"] == 3, "2 CLI + 1 desktop"
    assert kept[0]["sources"] == ["cli", "desktop"]


def test_discovery_survives_an_unreadable_store(tmp_path):
    """A corrupt session file or config must not stop the import -- onboarding
    runs this at boot, and one bad file cannot be allowed to leave an operator
    with no departments at all."""
    import project_import as P
    desk = tmp_path / "desk" / "acct" / "ws"
    desk.mkdir(parents=True)
    (desk / "broken.json").write_text("{not json")
    (desk / "local_a.json").write_text(json.dumps(
        {"sessionId": "local_a", "cwd": "/Users/x/work/good"}))
    cfg = tmp_path / "claude.json"
    cfg.write_text("{also not json")

    kept, _ = P.discover(projects_dir=tmp_path / "noprojects", home="/Users/x",
                         desktop_dir=tmp_path / "desk", config_path=cfg)

    assert [r["cwd"] for r in kept] == ["/Users/x/work/good"]


def test_cwd_is_found_past_a_long_preamble(tmp_path):
    """Bounded read: cwd is looked for in the first CWD_SCAN_LINES lines. A
    transcript that buries it deeper is reported as having none rather than
    costing a full scan of a 900-session folder."""
    import project_import as P
    projects = tmp_path / "projects"
    _session(projects / "-Users-x-near", "s1", "/Users/x/near", extra_lines=5)
    _session(projects / "-Users-x-far", "s2", "/Users/x/far",
             extra_lines=P.CWD_SCAN_LINES + 5)

    kept, skipped = P.discover(projects_dir=projects, home="/Users/x",
                             desktop_dir=tmp_path/"nodesk", config_path=tmp_path/"nocfg")

    assert [r["cwd"] for r in kept] == ["/Users/x/near"]
    assert skipped == [], "a transcript with no recoverable cwd names no project"


# --------------------------------------------------------------- identity ---

def test_no_company_name_is_hardcoded_in_the_import_path():
    """The regression this exists for. The root default was the literal
    "Asawa Inc." -- the founder's own holding -- so a stranger installing Sutra
    got someone else's company as the root of THEIR org. A default that names
    another company is a mislabel, not a default."""
    import ast
    import inspect
    import project_import as P
    # CODE, not prose: the module's own docstrings name "Asawa Inc." to explain
    # why it is gone, and a substring check over the source fails on that.
    tree = ast.parse(inspect.getsource(P))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings]
    for bad in ("Asawa", "Sutra Inc", "Sutra OS"):
        hits = [s for s in literals if bad in s]
        assert not hits, "a company name is hardcoded in code: %r" % hits


def test_default_org_name_prefers_the_accounts_full_name(monkeypatch):
    """Most specific rung: the OS account's full name."""
    import pwd
    import project_import as P
    fake = pwd.struct_passwd(("tchandrakar", "x", 501, 20, "Tishant",
                              "/Users/tchandrakar", "/bin/zsh"))
    monkeypatch.setattr(pwd, "getpwuid", lambda _uid: fake)
    monkeypatch.delenv("SUTRA_ORG_NAME", raising=False)
    assert P.default_org_name() == "Tishant"


def test_default_org_name_takes_only_the_first_gecos_field(monkeypatch):
    """GECOS is historically "Full Name,Office,Phone". Rendering the whole
    field would put a phone number in the company name."""
    import pwd
    import project_import as P
    fake = pwd.struct_passwd(("u", "x", 501, 20, "Ada Lovelace,Room 5,x1234",
                              "/Users/u", "/bin/zsh"))
    monkeypatch.setattr(pwd, "getpwuid", lambda _uid: fake)
    monkeypatch.delenv("SUTRA_ORG_NAME", raising=False)
    assert P.default_org_name() == "Ada Lovelace"


def test_default_org_name_falls_back_to_the_login_name(monkeypatch):
    """Second rung: an account with no full name set still has a login name."""
    import pwd
    import project_import as P
    fake = pwd.struct_passwd(("tchandrakar", "x", 501, 20, "",
                              "/Users/tchandrakar", "/bin/zsh"))
    monkeypatch.setattr(pwd, "getpwuid", lambda _uid: fake)
    monkeypatch.delenv("SUTRA_ORG_NAME", raising=False)
    assert P.default_org_name() == "tchandrakar"


def test_default_org_name_never_returns_empty(monkeypatch):
    """Last rung. An empty root name would make the engine mint a node called
    "Root" and the footer read "CEO of Root" -- worse than saying nothing."""
    import pwd
    import project_import as P
    def boom(_uid):
        raise KeyError("no such user")
    monkeypatch.setattr(pwd, "getpwuid", boom)
    for var in ("SUTRA_ORG_NAME", "USER", "LOGNAME"):
        monkeypatch.delenv(var, raising=False)
    assert P.default_org_name() == P.FALLBACK_ORG_NAME
    assert P.default_org_name().strip()


def test_org_name_can_be_overridden_by_env(monkeypatch):
    """An operator whose company is not their own name needs one lever that
    does not require editing code -- and the tests need it to be deterministic."""
    import pwd
    import project_import as P
    def boom(_uid):
        raise KeyError("no such user")
    monkeypatch.setattr(pwd, "getpwuid", boom)
    monkeypatch.setenv("SUTRA_ORG_NAME", "Acme Ltd")
    assert P.default_org_name() == "Acme Ltd"


def test_the_root_is_minted_with_the_derived_name(monkeypatch):
    """End to end: no root_name passed, so the tree's root must carry the
    derived company rather than any literal."""
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh_engine(Path(tmp))
        monkeypatch.setenv("SUTRA_ORG_NAME", "Derived Co")
        monkeypatch.delenv("PLACEMENT_ROOT_NAME", raising=False)
        root_ref, _rows = P.apply_forest(
            P.build_forest([{"cwd": "/d/sutra", "sessions": 1}]))
        root = E.load_domains()[root_ref]
        assert root["name"] == "Derived Co"
        assert root["parent_ref"] is None


# ------------------------------------------------------------- repo names ---

class _Run:
    """A fake `git` that answers from a dict, so these tests never shell out."""
    def __init__(self, toplevel=None, url=None, raises=False):
        self.toplevel, self.url, self.raises = toplevel, url, raises

    def __call__(self, args):
        if self.raises:
            raise OSError("git not found")
        class R:
            pass
        r = R()
        r.stdout = (self.toplevel if "--show-toplevel" in args else self.url) or ""
        return r


def test_repo_name_uses_the_remote_at_the_repo_root():
    """Claude labels a project by its GitHub repo: the founder's folder
    `live-contest-event-leaderboard` shows in Claude as
    `live-contest-event-dashboard`, which is the repo name."""
    import project_import as P
    run = _Run(toplevel="/w/live-contest-event-leaderboard",
               url="git@github.com:tchandrakar/live-contest-event-dashboard.git")
    assert P.repo_name("/w/live-contest-event-leaderboard", _run=run) \
        == "live-contest-event-dashboard"


def test_repo_name_refuses_a_subdirectory_of_a_repo():
    """THE case that would have shipped a collision. A subdirectory reports its
    PARENT's remote, so `sutra/marketplace/plugin/sutra-ui` would be renamed
    "Sutra" -- and mint_domain's name-dedupe would then fold it into the real
    Sutra department. Same for `sovereign-ai/plans`."""
    import project_import as P
    run = _Run(toplevel="/w/sutra", url="git@github.com:x/sutra.git")
    assert P.repo_name("/w/sutra/marketplace/plugin/sutra-ui", _run=run) == ""


@pytest.mark.parametrize("url,want", [
    ("git@github.com:owner/repo.git",       "repo"),
    ("https://github.com/owner/repo.git",   "repo"),
    ("https://github.com/owner/repo",       "repo"),
    ("git://example.com/owner/repo.git",    "repo"),
    ("https://gitlab.com/g/sub/repo.git",   "repo"),      # not GitHub
    ("/srv/git/repo.git",                   "repo"),      # local path remote
    ("git@github.com:repo.git",             "repo"),      # no owner segment
])
def test_repo_name_parses_every_remote_url_form(url, want):
    import project_import as P
    assert P.repo_name("/w/r", _run=_Run(toplevel="/w/r", url=url)) == want


@pytest.mark.parametrize("run", [
    _Run(toplevel="", url=""),                 # not a repo
    _Run(toplevel="/w/r", url=""),             # a repo with no remote
    _Run(raises=True),                         # no git binary at all
])
def test_repo_name_fails_soft_to_the_folder_name(run):
    """"We did not learn a better name" is never an error: onboarding runs this
    at boot across every project, and one missing git must not stop it."""
    import project_import as P
    assert P.repo_name("/w/r", _run=run) == ""


def test_build_forest_names_from_the_repo_but_nests_by_path(monkeypatch):
    """The rename must not disturb the tree: nesting is still by directory
    containment, only the LABEL comes from the remote."""
    import project_import as P
    monkeypatch.setattr(P, "repo_name",
                        lambda cwd, _run=None:
                        "live-contest-event-dashboard"
                        if cwd.endswith("leaderboard") else "")
    rows = P.build_forest([
        {"cwd": "/d", "sessions": 1},
        {"cwd": "/d/live-contest-event-leaderboard", "sessions": 1}])
    by = {r["cwd"]: r for r in rows}
    assert by["/d/live-contest-event-leaderboard"]["name"] == "Live Contest Event Dashboard"
    assert by["/d/live-contest-event-leaderboard"]["parent_cwd"] == "/d", \
        "the label changed; the tree position must not"


# ------------------------------------------------------------------ names ---

@pytest.mark.parametrize("path,want", [
    ("/a/asawa-holding",                  "Asawa Holding"),
    ("/a/sutra/marketplace/plugin/sutra-ui", "Sutra UI"),
    ("/a/cp-study",                       "CP Study"),
    ("/a/viral-engine-ai",                "Viral Engine AI"),
    ("/a/UI design documents.",           "UI Design Documents"),   # trailing sep dropped
    ("/a/bahi_khata",                     "Bahi Khata"),
    ("/a/trailing/",                      "Trailing"),
])
def test_humanize(path, want):
    import project_import as P
    assert P.humanize(path) == want


# ----------------------------------------------------------------- nesting ---

def test_nesting_attaches_to_the_nearest_ancestor_not_the_shallowest(tmp_path):
    """sutra-ui is contained by BOTH development and sutra. Longest-prefix
    wins, so it lands under sutra -- attaching it to development would be a
    true containment and the wrong department."""
    import project_import as P
    kept = [{"cwd": "/d", "sessions": 3, "folder": "d"},
            {"cwd": "/d/sutra", "sessions": 41, "folder": "s"},
            {"cwd": "/d/sutra/mp/sutra-ui", "sessions": 3, "folder": "u"},
            {"cwd": "/elsewhere", "sessions": 1, "folder": "e"}]

    by_cwd = {r["cwd"]: r for r in P.build_forest(kept)}

    assert by_cwd["/d"]["parent_cwd"] is None
    assert by_cwd["/elsewhere"]["parent_cwd"] is None
    assert by_cwd["/d/sutra"]["parent_cwd"] == "/d"
    assert by_cwd["/d/sutra/mp/sutra-ui"]["parent_cwd"] == "/d/sutra"


def test_forest_is_ordered_parents_before_children(tmp_path):
    """apply_forest mints in one pass and looks its parent up in a dict filled
    by earlier iterations. A child arriving first would silently parent to the
    root instead of failing, so the ordering is load-bearing."""
    import project_import as P
    kept = [{"cwd": "/d/sutra/mp/ui", "sessions": 1, "folder": "u"},
            {"cwd": "/d", "sessions": 1, "folder": "d"},
            {"cwd": "/d/sutra", "sessions": 1, "folder": "s"}]

    seen = []
    for row in P.build_forest(kept):
        if row["parent_cwd"] is not None:
            assert row["parent_cwd"] in seen, "child minted before its parent"
        seen.append(row["cwd"])


def test_a_sibling_prefix_is_not_a_parent():
    """String-prefix without a separator is the classic bug: "/d/sutra-ui"
    starts with "/d/sutra" but is a sibling, not a child."""
    import project_import as P
    kept = [{"cwd": "/d/sutra", "sessions": 1, "folder": "a"},
            {"cwd": "/d/sutra-ui", "sessions": 1, "folder": "b"}]

    by_cwd = {r["cwd"]: r for r in P.build_forest(kept)}

    assert by_cwd["/d/sutra-ui"]["parent_cwd"] is None


# ---------------------------------------------------------------- resolve ---

def test_department_for_cwd_picks_the_nearest_department():
    """The question a chat asks. Three departments contain the path; the
    answer is the most specific one."""
    import project_import as P
    depts = {"/d": {"name": "Development"},
             "/d/sutra": {"name": "Sutra"},
             "/d/sutra/mp/ui": {"name": "Sutra UI"}}

    assert P.department_for_cwd("/d/sutra/mp/ui", depts)["name"] == "Sutra UI"
    assert P.department_for_cwd("/d/sutra/other", depts)["name"] == "Sutra"
    assert P.department_for_cwd("/d/loose", depts)["name"] == "Development"


def test_department_for_cwd_returns_none_rather_than_guessing():
    """teamsutra.py:110 states the rule for tasks -- "A department may be null
    and MUST be null rather than guessed: a wrong address is the failure the
    placement layer exists to remove." Chats get the same rule."""
    import project_import as P
    depts = {"/d/sutra": {"name": "Sutra"}}

    assert P.department_for_cwd("/somewhere/else", depts) is None
    assert P.department_for_cwd("", depts) is None
    assert P.department_for_cwd(None, depts) is None


def test_sibling_prefix_does_not_resolve():
    """Same separator bug as the nesting test, on the read path."""
    import project_import as P
    depts = {"/d/sutra": {"name": "Sutra"}}

    assert P.department_for_cwd("/d/sutra-ui", depts) is None


# ------------------------------------------------------- registry round-trip ---

def test_import_is_idempotent_and_links_the_second_time():
    """The founder's stated requirement: "If the department already exists, it
    links to the existing one." That behaviour is mint_domain's dedupe
    (placement_engine.py:386), so this proves the importer actually relies on
    it -- same refs, nothing created twice."""
    with tempfile.TemporaryDirectory() as tmp:
        P, _E = _fresh_engine(Path(tmp))
        forest = P.build_forest([
            {"cwd": "/d", "sessions": 2, "folder": "d"},
            {"cwd": "/d/sutra", "sessions": 5, "folder": "s"}])

        _root1, first = P.apply_forest(forest, root_name="Test Co")
        _root2, second = P.apply_forest(forest, root_name="Test Co")

        assert all(r["created"] for r in first)
        assert not any(r["created"] for r in second)
        assert ([r["ref"] for r in first] == [r["ref"] for r in second])


def test_import_writes_the_cwd_join_key():
    """The cwd on the domain record is what department_for_cwd reads. Without
    it a department exists but no chat can ever resolve to it."""
    with tempfile.TemporaryDirectory() as tmp:
        P, _E = _fresh_engine(Path(tmp))
        forest = P.build_forest([{"cwd": "/d/sutra", "sessions": 1, "folder": "s"}])

        P.apply_forest(forest, root_name="Test Co")

        found = P.department_for_cwd("/d/sutra/deep/inside")
        assert found is not None and found["name"] == "Sutra"
        assert found["source"] == "claude-project"


def test_sync_never_wipes():
    """sync() is the boot path. A boot path that can delete a registry is one
    crash-loop away from deleting it repeatedly, so wiping stays behind the
    CLI's explicit --wipe --i-have-a-backup and must not be reachable here.
    Asserted against the source: a call added later would pass a behavioural
    test that happened not to have a department worth deleting."""
    import ast
    import inspect
    import project_import as P
    # A CALL, not a mention: sync's own docstring names wipe_registry to say
    # it is deliberately not reachable, and a substring check fails on that.
    tree = ast.parse(inspect.getsource(P.sync))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "wipe_registry" not in called, "sync must never call wipe_registry"


def test_sync_adds_a_new_project_without_disturbing_the_existing_tree():
    """The onboarding contract: run it, run it again, then let a new project
    appear and run once more. Nothing is recreated, nothing is lost, and the
    new one shows up on its own -- no operator step, no model in the loop."""
    with tempfile.TemporaryDirectory() as tmp:
        P, _E = _fresh_engine(Path(tmp))
        first = P.apply_forest(P.build_forest([
            {"cwd": "/d", "sessions": 1},
            {"cwd": "/d/sutra", "sessions": 1}]), root_name="Test Co")[1]
        again = P.apply_forest(P.build_forest([
            {"cwd": "/d", "sessions": 1},
            {"cwd": "/d/sutra", "sessions": 1}]), root_name="Test Co")[1]
        grown = P.apply_forest(P.build_forest([
            {"cwd": "/d", "sessions": 1},
            {"cwd": "/d/sutra", "sessions": 1},
            {"cwd": "/d/brand-new", "sessions": 1}]), root_name="Test Co")[1]

        assert all(r["created"] for r in first)
        assert not any(r["created"] for r in again), "a second run must create nothing"
        made = [r["name"] for r in grown if r["created"]]
        assert made == ["Brand New"], "only the new project is minted"
        # the untouched two keep the refs they were first given
        refs = {r["cwd"]: r["ref"] for r in first}
        for r in grown:
            if r["cwd"] in refs:
                assert r["ref"] == refs[r["cwd"]], "an existing department must keep its ref"


def test_renaming_a_project_renames_the_department_instead_of_minting_a_second():
    """The bug the git-remote naming exposed. mint_domain dedupes by (parent,
    NAME), so once repo_name() started labelling a project after its remote,
    the import minted a SECOND department and orphaned the first -- two domains
    claiming one cwd, which makes department_for_cwd pick between them at
    random. A department's identity is its cwd; the name is just a label."""
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh_engine(Path(tmp))
        first = P.apply_forest(P.build_forest(
            [{"cwd": "/d/leaderboard", "sessions": 1}]), root_name="Co")[1]
        original_ref = first[0]["ref"]

        # same project, new label (as if a git remote appeared)
        forest = P.build_forest([{"cwd": "/d/leaderboard", "sessions": 1}])
        forest[0]["name"] = "Dashboard"
        _root, second = P.apply_forest(forest, root_name="Co")

        live = {r["ref"]: r for r in E.load_domains().values() if r.get("cwd")}
        assert len(live) == 1, "a rename must not mint a second department"
        assert second[0]["ref"] == original_ref, "the ref must survive a rename"
        assert not second[0]["created"]
        assert E.load_domains()[original_ref]["name"] == "Dashboard"
        assert second[0].get("renamed_from") == "Leaderboard"


def test_two_departments_never_claim_the_same_cwd():
    """The consequence that made the duplicate dangerous: imported_departments
    is keyed by cwd, so a second department on the same directory silently
    wins or loses at random."""
    with tempfile.TemporaryDirectory() as tmp:
        P, _E = _fresh_engine(Path(tmp))
        P.apply_forest(P.build_forest([{"cwd": "/d/x", "sessions": 1}]), root_name="Co")
        f2 = P.build_forest([{"cwd": "/d/x", "sessions": 1}])
        f2[0]["name"] = "Renamed"
        P.apply_forest(f2, root_name="Co")

        depts = P.imported_departments()
        cwds = [d["cwd"] for d in depts.values()]
        assert len(cwds) == len(set(cwds)), "one cwd, one department"


def test_the_true_session_count_is_stored_on_the_department():
    """The heading count must be the department's real size, not the number of
    chats the panel has paged in -- it read 90 for a project with 941."""
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh_engine(Path(tmp))
        _root, rows = P.apply_forest(
            P.build_forest([{"cwd": "/d/big", "sessions": 941}]), root_name="Co")
        assert E.load_domains()[rows[0]["ref"]]["sessions"] == 941


def test_wipe_removes_data_but_keeps_lock_files():
    """Removing a .lock another process holds orphans its flock. The wipe
    deletes records only."""
    with tempfile.TemporaryDirectory() as tmp:
        P, _E = _fresh_engine(Path(tmp))
        root = Path(tmp)
        for sub in ("domains", "charters", "placements"):
            (root / sub).mkdir(parents=True, exist_ok=True)
            (root / sub / "rec.json").write_text("{}")
        (root / "domains" / "RESTRUCTURE.lock").write_text("")

        removed = P.wipe_registry(home_dir=root)

        assert removed == {"domains": 1, "charters": 1, "placements": 1}
        assert (root / "domains" / "RESTRUCTURE.lock").exists()
        assert not (root / "domains" / "rec.json").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
