"""D451, T3: the files of a project (`orchestrator/project_files.py`, schema v10 `project_files`).

FR-7 limits and the duplicate rule, FR-9 switch, rename, remove (the bytes go only when nothing else names them), promote from a chat's file, NFR-5 extraction once, NFR-6 two writers, D426 a
deleted (hidden) project is read-only. The real store and the real database; `tenv` is the task side over a chart with the teams `web` and `sales`.
"""
from __future__ import annotations

import hashlib
import threading

import pytest
from orchestrator.test_chat_store import msg
from orchestrator.test_tasks import tenv  # noqa: F401  (a fixture)

from sutra_app.connectors import attachments as attachments_mod
from sutra_app.connectors.attachments import AttachmentStore
from sutra_app.orchestrator.errors import AppError, NotFound, ReadOnly
from sutra_app.orchestrator.project_files import Limits, ProjectFiles
from sutra_app.orchestrator.schema import SCHEMA_VERSION, TABLES


def files_of(t, **limits) -> ProjectFiles:
    return ProjectFiles(t.db, AttachmentStore(t.settings.data_dir), clock=t.clock, limits=Limits(**limits) if limits else None)


def stored(t, name: str, blob: bytes):
    return AttachmentStore(t.settings.data_dir).save(name, blob)


def add(t, pf: ProjectFiles, name: str, blob: bytes, dept: str = "web"):
    return pf.add(dept, stored(t, name, blob))


def refused(call) -> str:
    with pytest.raises(AppError) as caught:
        call()
    assert caught.value.code == "validation"
    return caught.value.message


# ---- the schema ----------------------------------------------------------------------------------------------------------------------

def test_the_database_is_at_version_ten_with_a_project_files_table_and_a_task_column(tenv):
    assert SCHEMA_VERSION == 10 and "project_files" in TABLES
    assert tenv.one("SELECT count(*) FROM project_files") == 0
    assert "input_files_json" in [r[1] for r in tenv.sql("PRAGMA table_info(tasks)")]
    assert tenv.one("SELECT input_files_json FROM tasks LIMIT 1") in (None, "[]")


# ---- add, list, the duplicate rule ----------------------------------------------------------------------------------------------------

def test_a_file_added_to_a_project_is_listed_with_its_kind_size_and_characters(tenv):
    pf = files_of(tenv)
    out = add(tenv, pf, "notes.txt", b"hello world")
    assert (out.name, out.kind, out.size, out.chars, out.enabled, out.reference_only, out.already) == ("notes.txt", "text", 11, 11, True, False, False)
    listing = pf.list("web")
    assert [f.name for f in listing.files] == ["notes.txt"] and listing.totals.files == 1 and listing.totals.bytes == 11 and listing.totals.chars == 11
    assert listing.mode == "whole" and pf.list("sales").files == []                                   # another project is untouched


def test_an_image_and_a_pdf_are_reference_only_and_have_no_characters(tenv):
    pf = files_of(tenv)
    png = add(tenv, pf, "shot.png", b"\x89PNG\r\n\x1a\n" + b"0" * 30)
    pdf = add(tenv, pf, "spec.pdf", b"%PDF-1.4\n" + b"0" * 30)
    assert (png.kind, png.chars, png.reference_only) == ("image", 0, True) and (pdf.kind, pdf.chars, pdf.reference_only) == ("pdf", 0, True)


def test_the_same_content_twice_is_one_row_and_says_it_is_already_there(tenv):
    pf = files_of(tenv)
    first = add(tenv, pf, "a.txt", b"same bytes")
    again = add(tenv, pf, "copy-of-a.txt", b"same bytes")
    assert again.id == first.id and again.already is True and len(pf.list("web").files) == 1
    assert tenv.one("SELECT count(*) FROM project_files") == 1


def test_the_fifty_first_file_is_refused_with_the_limit_in_a_sentence(tenv):
    pf = files_of(tenv)
    for n in range(50):
        add(tenv, pf, f"f{n}.txt", f"file number {n}".encode())
    said = refused(lambda: add(tenv, pf, "one-more.txt", b"one more"))
    assert "50 files" in said and "Remove one" in said
    assert len(pf.list("web").files) == 50 and pf.list("sales").files == []


def test_the_size_and_the_text_limits_name_themselves(tenv):
    pf = files_of(tenv, max_bytes=100)
    add(tenv, pf, "a.txt", b"x" * 60)
    assert "size limit" in refused(lambda: add(tenv, pf, "b.txt", b"y" * 60))
    pf = files_of(tenv, max_chars=100)
    add(tenv, pf, "c.txt", b"z" * 80, dept="sales")
    assert "text limit" in refused(lambda: add(tenv, pf, "d.txt", b"w" * 80, dept="sales"))
    assert len(pf.list("web").files) == 1 and len(pf.list("sales").files) == 1                        # the refused ones were not kept, and a limit is per project


def test_the_limits_the_page_shows_are_the_ones_the_server_checks(tenv):
    limits = files_of(tenv).list("web").limits
    assert (limits.max_files, limits.max_bytes, limits.max_chars, limits.instructions_chars) == (50, 100 * 1024 * 1024, 400_000, 4000)


# ---- FR-9: switch, rename, remove -----------------------------------------------------------------------------------------------------

def test_a_file_switched_off_is_not_used_and_one_switched_on_again_is(tenv):
    pf = files_of(tenv)
    row = add(tenv, pf, "a.txt", b"alpha")
    add(tenv, pf, "b.txt", b"beta")
    assert [r.name for r in pf.enabled("web")] == ["a.txt", "b.txt"]
    assert pf.patch("web", row.id, enabled=False).enabled is False
    assert [r.name for r in pf.enabled("web")] == ["b.txt"] and len(pf.list("web").files) == 2        # still listed: the owner can switch it back
    pf.patch("web", row.id, enabled=True)
    assert [r.name for r in pf.enabled("web")] == ["a.txt", "b.txt"]


def test_a_file_can_be_renamed_and_a_name_that_is_empty_or_holds_a_path_is_cleaned_or_refused(tenv):
    pf = files_of(tenv)
    row = add(tenv, pf, "a.txt", b"alpha")
    assert pf.patch("web", row.id, name="plan v2.txt").name == "plan v2.txt"
    assert pf.patch("web", row.id, name="../../etc/x.txt").name == "x.txt"                             # a path never survives
    assert refused(lambda: pf.patch("web", row.id, name="  "))
    with pytest.raises(NotFound):
        pf.patch("web", "pf_000000000000", enabled=False)
    with pytest.raises(NotFound):
        pf.patch("sales", row.id, enabled=False)                                                      # a file of another project is not found here


def test_removing_a_file_deletes_the_bytes_when_nothing_else_uses_them(tenv):
    pf = files_of(tenv)
    store = AttachmentStore(tenv.settings.data_dir)
    row = add(tenv, pf, "a.txt", b"only here")
    ref_id = store.save("a.txt", b"only here").id
    assert store.path_of(ref_id) is not None
    pf.remove("web", row.id)
    assert pf.list("web").files == [] and pf.enabled("web") == [] and store.path_of(ref_id) is None
    with pytest.raises(NotFound):
        pf.remove("web", row.id)


def test_the_bytes_stay_while_another_project_a_task_or_a_chat_line_still_names_them(tenv):
    pf = files_of(tenv)
    store = AttachmentStore(tenv.settings.data_dir)
    # another project holds the same content
    a = add(tenv, pf, "a.txt", b"shared by two")
    add(tenv, pf, "a.txt", b"shared by two", dept="sales")
    pf.remove("web", a.id)
    assert store.path_of(hashlib.sha256(b"shared by two").hexdigest()) is not None
    # a task's snapshot names it
    task = tenv.new("web", "use the file")
    sha = store.save("t.txt", b"in a task").id
    tenv.sql("UPDATE tasks SET input_files_json = ? WHERE id = ?", f'[{{"id":"{sha}","name":"t.txt","kind":"text","size":9,"chars":9}}]', task.id)
    row = pf.add("web", store.save("t.txt", b"in a task"))
    pf.remove("web", row.id)
    assert store.path_of(sha) is not None
    # a chat line names it
    sid = tenv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")
    sha2 = store.save("c.txt", b"in a chat line").id
    with tenv.db.tx() as tx:
        tenv.chats.post(tx, sid, msg(sid, "see c.txt", who="user", attachments=[{"id": sha2, "name": "c.txt", "kind": "text", "sent": "text", "chars": 14, "cut": False, "total": 14}]))
    row = pf.add("web", store.save("c.txt", b"in a chat line"))
    pf.remove("web", row.id)
    assert store.path_of(sha2) is not None


def test_remove_all_clears_one_project_only(tenv):
    pf = files_of(tenv)
    add(tenv, pf, "a.txt", b"a1")
    add(tenv, pf, "b.txt", b"b1")
    add(tenv, pf, "c.txt", b"c1", dept="sales")
    pf.remove_all("web")
    assert pf.list("web").files == [] and [f.name for f in pf.list("sales").files] == ["c.txt"]


# ---- promote, hidden, concurrency, extraction ----------------------------------------------------------------------------------------

def test_a_file_already_stored_for_a_chat_can_be_promoted_to_the_project(tenv):
    pf = files_of(tenv)
    ref = stored(tenv, "brief.md", b"# the brief")
    out = pf.promote("web", ref.id, "brief.md")
    assert (out.name, out.kind, out.chars, out.already) == ("brief.md", "text", 11, False)
    assert pf.promote("web", ref.id, "brief.md").already is True and len(pf.list("web").files) == 1
    with pytest.raises(NotFound):
        pf.promote("web", "0" * 64, "x.txt")


def test_a_deleted_project_is_read_only_but_still_lists_its_files(tenv):
    pf = files_of(tenv)
    row = add(tenv, pf, "a.txt", b"alpha")
    tenv.sql("UPDATE departments SET hidden_at = 1 WHERE id = 'web'")
    assert [f.name for f in pf.list("web").files] == ["a.txt"]
    with pytest.raises(ReadOnly):
        add(tenv, pf, "b.txt", b"beta")
    with pytest.raises(ReadOnly):
        pf.patch("web", row.id, enabled=False)
    with pytest.raises(ReadOnly):
        pf.remove("web", row.id)


def test_two_threads_adding_the_same_file_make_one_row(tenv):
    pf = files_of(tenv)
    ref = stored(tenv, "race.txt", b"the same file in two threads")
    got, errors = [], []

    def go() -> None:
        try:
            got.append(pf.add("web", ref).id)
        except Exception as exc:                                                                          # noqa: BLE001
            errors.append(exc)
    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(set(got)) == 1 and tenv.one("SELECT count(*) FROM project_files WHERE removed_at IS NULL") == 1


def test_a_file_is_read_once_when_added_and_never_again_to_list_or_to_choose(tenv, monkeypatch):
    seen = []
    real = attachments_mod._text_of
    monkeypatch.setattr(attachments_mod, "_text_of", lambda path, name: seen.append(name) or real(path, name))
    pf = files_of(tenv)
    add(tenv, pf, "a.txt", b"alpha beta")
    assert seen == ["a.txt"]
    pf.list("web")
    pf.enabled("web")
    pf.list("web")
    assert seen == ["a.txt"]                                                                              # listing 50 files is one query, not 50 reads
    assert pf.text_of(pf.enabled("web")[0]) == "alpha beta" and seen == ["a.txt", "a.txt"]               # the text is read when a run or a turn needs it, and only then
