"""test_routine_links.py -- a routine run is a chat, and the rail must say so.

A run writes a real transcript and reports its session id, so these rows were
always in the list and looked exactly like hand-started work -- 1,009 of 1,208
on the founder's machine. These tests pin the join and the ways it can quietly
go wrong: a runs tree in the wrong place, a half-written output (a third of
runs fail), and a cache that does not notice a new run.
"""
import json
import tempfile
from pathlib import Path

import pytest

import routine_links as R


def _routine(root, rid, runs):
    """runs: list of (session_id|None, outcome)."""
    d = root / rid
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "index.jsonl", "w") as fh:
        for i, (sid, outcome) in enumerate(runs):
            name = "run-%d.out" % i
            fh.write(json.dumps({"id": rid, "outcome": outcome,
                                 "started_at": "2026-09-13T09:0%d:00" % i,
                                 "output_file": name}) + "\n")
            (d / name).write_text("{}" if sid is None
                                  else json.dumps({"session_id": sid, "result": "x"}))
    return d


def test_a_run_links_its_session_to_its_routine():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _routine(root, "si-feedback-sync", [("sid-a", "ok"), ("sid-b", "failed")])
        m = R.by_session(root, _force=True)
        assert m["sid-a"]["routine"] == "si-feedback-sync"
        assert m["sid-a"]["outcome"] == "ok"
        assert m["sid-b"]["outcome"] == "failed"


def test_a_run_whose_output_is_not_json_is_skipped_not_fatal():
    """A third of this operator's runs fail, and a failed run may write no JSON
    at all. One unreadable output must not cost the whole map."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        d = _routine(root, "r", [("sid-ok", "ok"), (None, "failed")])
        (d / "run-1.out").write_text("Traceback: exploded before claude spoke")
        m = R.by_session(root, _force=True)
        assert m["sid-ok"]["routine"] == "r"
        assert len(m) == 1, "the torn run is skipped, the good one survives"


def test_a_missing_runs_tree_is_empty_not_an_error():
    """The path that actually bit: ~/.sutra-ui/routines/runs looks right and
    does not exist; the runner writes to ~/.sutra-ui/runs."""
    with tempfile.TemporaryDirectory() as tmp:
        assert R.by_session(Path(tmp) / "nope", _force=True) == {}


def test_attach_tags_rows_and_states_the_absence():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _routine(root, "r", [("sid-a", "ok")])
        R.by_session(root, _force=True)
        rows = [{"id": "sid-a"}, {"id": "hand-started"}]
        R.attach(rows, root)
        assert rows[0]["routine"]["routine"] == "r"
        assert rows[1]["routine"] is None, "a non-routine chat says so, not KeyError"


def test_the_cache_notices_a_new_run():
    """Cached on the index mtimes because a rail refresh must not re-read every
    run -- but a routine that just fired has to appear."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        d = _routine(root, "r", [("sid-a", "ok")])
        assert set(R.by_session(root, _force=True)) == {"sid-a"}
        # a second run appends to the index and writes its own output
        (d / "run-9.out").write_text(json.dumps({"session_id": "sid-b"}))
        with open(d / "index.jsonl", "a") as fh:
            fh.write(json.dumps({"id": "r", "outcome": "ok",
                                 "output_file": "run-9.out"}) + "\n")
        assert "sid-b" in R.by_session(root, _force=True)


def test_summary_counts_runs_without_reading_outputs():
    """The health line beside a routine. A routine with runs and zero successes
    is a different thing from one that fails sometimes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _routine(root, "never-works", [("s1", "failed"), ("s2", "failed")])
        _routine(root, "fine", [("s3", "ok"), ("s4", "failed")])
        s = R.summary(root)
        assert s["never-works"] == {"runs": 2, "ok": 0, "failed": 2}
        assert s["fine"] == {"runs": 2, "ok": 1, "failed": 1}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_the_default_scope_lists_routine_runs_as_sutras_own(monkeypatch):
    """The release blocker. With chat_scope at its default the rail listed only
    chat_store's panel chats, and 0 of 1,207 routine runs were in that index --
    so every fresh install opened an EMPTY Routines view. Routine runs are
    launched by Sutra's own runner, so they belong in the default list."""
    import app as A
    import session_reader as sr
    import chat_store
    import routine_links

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "projects" / "-w-repo"
        proj.mkdir(parents=True)
        (proj / "run-sid.jsonl").write_text('{"cwd":"/w/repo"}\n')
        (proj / "panel-sid.jsonl").write_text('{"cwd":"/w/repo"}\n')
        (proj / "vscode-sid.jsonl").write_text('{"cwd":"/w/repo"}\n')

        monkeypatch.setattr(sr, "PROJECTS", Path(tmp) / "projects")
        monkeypatch.setattr(sr, "index", lambda: {
            "run-sid": {"project": "-w-repo"},
            "panel-sid": {"project": "-w-repo"},
            "vscode-sid": {"project": "-w-repo"}})
        monkeypatch.setattr(chat_store, "index", lambda: {"claude:panel-sid": "sutra-1"})
        monkeypatch.setattr(routine_links, "by_session",
                            lambda *a, **k: {"run-sid": {"routine": "r"}})

        ids = {c[2] for c in A._owned_transcripts()}
        assert "panel-sid" in ids, "a chat started in the panel is Sutra's own"
        assert "run-sid" in ids, "a routine run is Sutra's own too"
        assert "vscode-sid" not in ids, "another tool's transcript still stays out"


def test_a_broken_runs_tree_does_not_empty_the_default_rail(monkeypatch):
    import app as A
    import chat_store
    import session_reader as sr
    import routine_links

    def boom(*a, **k):
        raise OSError("runs tree unreadable")
    monkeypatch.setattr(routine_links, "by_session", boom)
    monkeypatch.setattr(chat_store, "index", lambda: {})
    monkeypatch.setattr(sr, "index", lambda: {})
    assert A._owned_transcripts() == [], "fails soft to the panel chats alone"
