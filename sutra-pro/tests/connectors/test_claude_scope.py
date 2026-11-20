"""A step with a write scope (MAN-10): the claude argv allows the edit tools only inside its paths, `.git` stays denied, a call with no scope gets exactly the tools it always got."""
from sutra_app.connectors.claude import _folder_tools
from sutra_app.connectors.workdir import DOT_GIT_DENY, EDIT_TOOLS, GIT_READ, Folder


def test_a_folder_with_a_scope_allows_the_edit_tools_only_inside_its_paths_and_keeps_git_denied():
    offered, allowed, denied = _folder_tools(Folder("/work", edit=True, scope=("site/", "docs/readme.md")))
    assert "Edit(site)" in allowed and "Edit(site/**)" in allowed and "Edit(docs/readme.md)" in allowed
    assert not any(tool in allowed for tool in EDIT_TOOLS) and all(rule in allowed for rule in GIT_READ)           # no blanket Edit, Write or MultiEdit
    assert all(rule in denied for rule in DOT_GIT_DENY) and all(tool in offered for tool in EDIT_TOOLS)


def test_a_folder_with_no_scope_gets_the_tools_it_always_got():
    assert _folder_tools(Folder("/work", edit=True)) == _folder_tools(Folder("/work", edit=True, scope=()))
    offered, allowed, denied = _folder_tools(Folder("/work", edit=True))
    assert all(tool in allowed for tool in EDIT_TOOLS)


def test_a_read_only_folder_ignores_a_scope():
    assert _folder_tools(Folder("/work", edit=False, scope=("site/",))) == _folder_tools(Folder("/work", edit=False))


def test_the_router_gives_a_node_call_its_scope_and_any_other_call_none(tmp_path):
    from sutra_app.connectors.models import ConnectorConfig
    from sutra_app.connectors.router import Router
    from sutra_app.connectors.stub import StubConnector
    from sutra_app.connectors.workdir import WorkFolder
    from sutra_app.engine.port import CallTag
    from test_orchestrator_port import policy
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy())
    router.folders = WorkFolder(cfg.data_dir, cfg.resolved_work_root())
    (tmp_path / "p").mkdir()
    router.folders.set(str(tmp_path / "p"), access="edit")
    router.node_scope = ("site/",)
    assert router.folder_for(CallTag(workspace="edit", node_id="nd_" + "a" * 12, node_role="worker")).scope == ("site/",)
    assert router.folder_for(CallTag(workspace="edit")).scope == ()                                      # a call that is not a node's
