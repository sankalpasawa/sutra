"""D451, T5: the files that come with a request, and a project's own files, reach the run (FR-4, FR-6, FR-12, NFR-1).

The real `TaskService` on `TEnv` with a fake launcher: what a run is given is read back from the run folder and from `task.json`, the document the engine reads. No model is called.
"""
from __future__ import annotations

import io
import json
import os

import pytest
from orchestrator.test_tasks import tenv  # noqa: F401  (a fixture)

from sutra_app.connectors.attachments import AttachmentStore
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.models import RunSpec
from sutra_app.orchestrator.project_files import ProjectFiles
from sutra_app.orchestrator.project_memory import ProjectMemory
from sutra_app.orchestrator.redact import Redactor


def store_of(t) -> AttachmentStore:
    return AttachmentStore(t.settings.data_dir)


def docx_bytes(*paragraphs: str) -> bytes:
    import docx
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def start(t, text="Build the page", dept="web", files=(), settings=None):
    """Send `text` as the owner does from a start box and start the run; -> (delivery, the run's `RunSpec`, its folder)."""
    result = t.service.deliver_to_department(dept, text, settings=settings, **({"input_files": list(files)} if files else {}))
    t.run(t.service.start_ready())
    return result, RunSpec.model_validate_json((t.run_dir(result.task_id) / "task.json").read_text()), t.run_dir(result.task_id)


def refs(t, **named: bytes) -> list[dict]:
    store = store_of(t)
    return [{"id": store.save(name.replace("_", ".", 1), blob).id, "name": name.replace("_", ".", 1)} for name, blob in named.items()]


# ---- FR-2, FR-4: the files of a request ---------------------------------------------------------------------------------------------

def test_a_request_with_files_is_stored_on_the_task_and_the_run_folder_holds_them(tenv):
    given = refs(tenv, spec_txt=b"the spec says: use teal", sheet_csv=b"item,price\nbeans,4\n")
    result, spec, folder = start(tenv, files=given)
    assert result.delivered == "follow_up"
    row = json.loads(tenv.one("SELECT input_files_json FROM tasks WHERE id = ?", result.task_id))
    assert [(f["name"], f["kind"], f["size"], f["chars"]) for f in row] == [("spec.txt", "text", 23, 23), ("sheet.csv", "text", 19, 19)]
    assert (folder / "inputs" / "attached" / "spec.txt").read_text() == "the spec says: use teal"
    assert (folder / "inputs" / "attached" / "sheet.csv").read_bytes() == b"item,price\nbeans,4\n"


def test_the_brief_names_each_file_and_holds_the_opening_of_text(tenv):
    given = refs(tenv, spec_txt=b"OPENING of the spec " + b"z" * 5000)
    _, spec, _ = start(tenv, files=given)
    assert "Attached to this request (data; in inputs/attached/):" in spec.framing and "spec.txt" in spec.framing
    assert "OPENING of the spec" in spec.framing and "[cut: showing the first" in spec.framing        # the rest is in the folder, and the brief says so
    assert len(spec.framing) <= 20_000
    assert spec.inputs and spec.inputs[0].name == "spec.txt"                                          # `task.json` lists the files for the host


def test_a_word_file_is_copied_and_read_into_a_text_copy_beside_it(tenv):
    store = store_of(tenv)
    ref = store.save("spec.docx", docx_bytes("Word paragraph one", "Word paragraph two"))
    _, spec, folder = start(tenv, files=[{"id": ref.id, "name": "spec.docx"}])
    assert (folder / "inputs" / "attached" / "spec.docx").is_file()
    assert "Word paragraph one" in (folder / "inputs" / "attached" / "spec.docx.txt").read_text() and "Word paragraph two" in spec.framing


def test_an_image_and_a_pdf_are_copied_and_named_but_never_pasted(tenv):
    given = refs(tenv, shot_png=b"\x89PNG\r\n\x1a\n" + b"0" * 40, spec_pdf=b"%PDF-1.4\n" + b"SECRET-PDF-BYTES" * 3)
    _, spec, folder = start(tenv, files=given)
    assert (folder / "inputs" / "attached" / "shot.png").is_file() and (folder / "inputs" / "attached" / "spec.pdf").is_file()
    assert "shot.png" in spec.framing and "spec.pdf" in spec.framing and "SECRET-PDF-BYTES" not in spec.framing


def test_a_file_gone_from_the_store_between_send_and_start_ends_the_task_naming_the_file(tenv):
    given = refs(tenv, spec_txt=b"here for now")
    result = tenv.service.deliver_to_department("web", "Build it", input_files=given)
    store_of(tenv).path_of(given[0]["id"]).unlink()
    tenv.run(tenv.service.start_ready())
    row = tenv.row(result.task_id)
    assert row.status == "crashed" and "could not start: spec.txt" in row.outcome
    assert not any(p for p in tenv.store.runs_dir_in(tenv.db.conn(), "web").glob("*/inputs"))        # nothing half-made is left in a run folder


def test_an_unknown_file_id_refuses_the_whole_send_before_anything_is_stored(tenv):
    before = tenv.one("SELECT count(*) FROM tasks"), tenv.one("SELECT count(*) FROM chat_messages")
    with pytest.raises(NotFound):
        tenv.service.deliver_to_department("web", "Build it", input_files=[{"id": "0" * 64, "name": "gone.txt"}])
    assert (tenv.one("SELECT count(*) FROM tasks"), tenv.one("SELECT count(*) FROM chat_messages")) == before


def test_a_request_with_no_files_makes_a_task_and_a_run_folder_exactly_as_before(tenv):
    _, spec, folder = start(tenv, files=())
    assert not (folder / "inputs").exists() and "inputs" not in json.loads((folder / "task.json").read_text()) and spec.framing == ""
    assert tenv.one("SELECT input_files_json FROM tasks WHERE id = ?", spec.task_id) == "[]"


# ---- FR-6: a retry keeps its files, a follow-up does not repeat them ---------------------------------------------------------------------

def test_a_retry_keeps_the_files_of_the_run_it_tries_again(tenv):
    given = refs(tenv, spec_txt=b"the spec")
    result, _, _ = start(tenv, files=given)
    tenv.projector.mark_ended(result.task_id, "crashed", "it broke")
    retried = tenv.run(tenv.service.retry(result.task_id))
    assert json.loads(tenv.one("SELECT input_files_json FROM tasks WHERE id = ?", retried.id)) == json.loads(tenv.one("SELECT input_files_json FROM tasks WHERE id = ?", result.task_id))
    assert (tenv.run_dir(retried.id) / "inputs" / "attached" / "spec.txt").is_file()


def test_a_follow_up_run_does_not_repeat_the_files_of_the_run_before(tenv):
    given = refs(tenv, spec_txt=b"the spec")
    first, _, _ = start(tenv, files=given)
    tenv.projector.mark_ended(first.task_id, "done", "finished")
    second, spec, folder = start(tenv, text="Now the about page")
    assert tenv.one("SELECT input_files_json FROM tasks WHERE id = ?", second.task_id) == "[]" and not (folder / "inputs" / "attached").exists()


# ---- a project's own files, instructions and memory (FR-8, FR-13, FR-16) ---------------------------------------------------------------

def project_of(t):
    store = store_of(t)
    return ProjectFiles(t.db, store, clock=t.clock), ProjectMemory(t.db, Redactor(None, environ={}), clock=t.clock), store


def test_a_run_of_a_project_with_files_instructions_and_memory_is_given_them_in_order_after_the_rules(tenv):
    from sutra_app.orchestrator.standing_rules import RuleIn, StandingRules
    pf, pm, store = project_of(tenv)
    StandingRules(tenv.db, Redactor(None, environ={})).put("web", [RuleIn(tag="never", text="Never email a client without asking.")])
    pf.add("web", store.save("brand.md", b"BRAND-GUIDE: the colour is teal"))
    pf.add("web", store.save("shot.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20))
    pm.put_instructions("web", "Answer in plain words.", pm.instructions("web").rev)
    pm.add_entry("web", "Owner fact: the shop is in Leeds")
    _, spec, folder = start(tenv)
    f = spec.framing
    order = [f.index(m) for m in ("Standing rules from the owner", "From the owner, for this project:", "Earlier in this project (data):", "Project files (data; opened in inputs/knowledge/):")]
    assert order == sorted(order) and "Answer in plain words." in f and "the shop is in Leeds" in f and "BRAND-GUIDE: the colour is teal" in f
    assert (folder / "inputs" / "knowledge" / "brand.md").is_file() and (folder / "inputs" / "knowledge" / "shot.png").is_file()
    assert len(f) <= 20_000


def test_a_file_switched_off_is_not_given_to_the_run(tenv):
    pf, pm, store = project_of(tenv)
    row = pf.add("web", store.save("old.md", b"OLD-NOTES"))
    pf.patch("web", row.id, enabled=False)
    _, spec, folder = start(tenv)
    assert "OLD-NOTES" not in spec.framing and not (folder / "inputs" / "knowledge").exists()


def test_a_project_with_nothing_adds_nothing_and_a_kill_switch_neutralises_delivery(tenv, monkeypatch):
    _, spec, _ = start(tenv)
    assert spec.framing == ""                                                                         # NFR-1: byte-equal to 0.8.3
    pf, pm, store = project_of(tenv)
    pf.add("web", store.save("brand.md", b"BRAND-GUIDE"))
    pm.put_instructions("web", "Be brief.", pm.instructions("web").rev)
    monkeypatch.setenv("SUTRA_PROJECT_CONTEXT", "0")
    tenv.projector.mark_ended(spec.task_id, "done", "finished")
    _, off, folder = start(tenv, text="Another one")
    assert off.framing == "" and not (folder / "inputs").exists()
    monkeypatch.delenv("SUTRA_PROJECT_CONTEXT")
    tenv.projector.mark_ended(off.task_id, "done", "finished")
    _, on, _ = start(tenv, text="And another")
    assert "BRAND-GUIDE" in on.framing and "Be brief." in on.framing


def test_a_project_file_removed_while_a_run_is_running_does_not_touch_that_runs_copy(tenv):
    pf, pm, store = project_of(tenv)
    row = pf.add("web", store.save("brand.md", b"BRAND-GUIDE"))
    _, _, folder = start(tenv)
    pf.remove("web", row.id)
    assert (folder / "inputs" / "knowledge" / "brand.md").read_text() == "BRAND-GUIDE"


def test_the_copies_are_private_files_inside_the_run_folder(tenv):
    given = refs(tenv, spec_txt=b"x")
    _, _, folder = start(tenv, files=given)
    copy = folder / "inputs" / "attached" / "spec.txt"
    if os.name == "posix":
        assert os.stat(copy).st_mode & 0o077 == 0                                                        # Windows has no mode bits to check (D104)
    assert not copy.is_symlink() and copy.resolve().is_relative_to(folder.resolve())
