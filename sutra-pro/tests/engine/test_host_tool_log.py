"""The host's part of the tool-call audit (MAN-14, D327): a run that is a node of a project gives its router a log in the run folder; every other run, and a port without a router, is left exactly as it was."""
from pathlib import Path
from types import SimpleNamespace

from sutra_app.engine.host.loop import Host
from sutra_app.engine.host.toollog import ToolLog, log_path


RUN = "j2-20261104-100000-bbbb"


def watch(*, node, router, run_dir):
    port = SimpleNamespace(router=router) if router is not None else object()
    host = SimpleNamespace(port=port, task=SimpleNamespace(node=node, run_id=RUN), paths=SimpleNamespace(run_dir=Path(run_dir) / "run", data_dir=Path(run_dir)) if run_dir is not None else None)
    Host._watch_tools(host)


def test_a_node_run_gives_its_router_a_log_in_its_run_folder(tmp_path):
    router = SimpleNamespace(on_tool=None)
    watch(node=object(), router=router, run_dir=tmp_path)
    assert isinstance(router.on_tool, ToolLog) and router.on_tool.path == log_path(tmp_path, RUN) and tmp_path / "run" not in router.on_tool.path.parents          # the log is outside the step's own folder (PB-6)
    router.on_tool(SimpleNamespace(node_id="nd_0123456789ab"), "Read", "read", "a.txt")
    assert log_path(tmp_path, RUN).read_text().count("\n") == 1


def test_a_run_that_is_no_node_a_port_with_no_router_and_a_host_with_no_paths_are_left_alone(tmp_path):
    router = SimpleNamespace(on_tool=None)
    watch(node=None, router=router, run_dir=tmp_path)
    assert router.on_tool is None and not log_path(tmp_path, RUN).exists()
    watch(node=object(), router=None, run_dir=tmp_path)                                        # no error, nothing to hook
    watch(node=object(), router=router, run_dir=None)
    assert router.on_tool is None
