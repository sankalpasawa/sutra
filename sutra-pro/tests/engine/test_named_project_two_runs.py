"""Named projects Phase 2, task 14 (CUJs 6 and 7): two runs of one project. Run 1 does project work and saves its result into the project
folder; the owner edits that file by hand; run 2 (a follow-up) continues run 1, starts from the owner's edit, and writes back only what it
changed. Every other file in the folder stays byte-identical, and run 1's own folder is never written again."""
import hashlib
import json
import os

from sutra_app.connectors.workdir import WorkFolder

from test_engine_host import chat, j2, trace   # noqa: F401  (the J2 fixture)

FIRST = "j2-20261123-090000-aaaa"
SECOND = "j2-20261123-100000-bbbb"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_second_prompt_starts_from_the_owners_edit_and_changes_only_what_it_changes(j2, make_run_dir, data_dir, tmp_path):
    from test_engine_project import BRIEF, QUIET, go
    folder = tmp_path / "Pulse"
    folder.mkdir()
    (folder / "README.md").write_text("the owner's own readme\n", encoding="utf-8")      # never Sutra's: never read, never written
    WorkFolder(data_dir, dept_id="web").set(str(folder), access="edit")

    first = make_run_dir(run_id=FIRST, user_text=BRIEF, settings=QUIET)
    go(first)
    assert (folder / "project.md").read_bytes() == (first / "project.md").read_bytes()
    first_tree = {p: sha(p) for p in first.rglob("*") if p.is_file()}

    edited = (folder / "project.md").read_text(encoding="utf-8") + "\nOwner's note: keep the digest at 08:30.\n"
    (folder / "project.md").write_text(edited, encoding="utf-8")
    readme = sha(folder / "README.md")

    second = make_run_dir(run_id=SECOND, user_text="Change the digest time to 08:30.", settings=QUIET, seed_from=FIRST)
    go(second)

    assert not trace(second, "seed.refused"), "run 2 continues run 1 (R2.1)"
    [seed] = trace(second, "seed.folder")
    assert seed["data"]["edited"] == ["project.md"], "run 2 started from the owner's edit (R2.2)"
    assert [m for m in chat(second) if m["text"].startswith("Starting from your edits in ")]
    assert sha(folder / "README.md") == readme, "a file Sutra never wrote is never touched (R2.4)"
    manifest = json.loads((folder / ".sutra" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["project.md"] == sha(folder / "project.md"), "the manifest follows what Sutra wrote last"
    record = json.loads((second / "export.json").read_text())
    assert record["outside"] == [], "the owner's edit was the starting point, so writing back over it is Sutra's own change (R2.3)"
    assert {p: sha(p) for p in first.rglob("*") if p.is_file() and p.name not in ("trace.jsonl",)} == \
        {p: h for p, h in first_tree.items() if p.name not in ("trace.jsonl",)}, "run 1's folder is history (R2.5)"
    assert sorted(os.listdir(folder)) == [".sutra", "README.md", "project.md"], "nothing is deleted, nothing of Sutra's records arrives"
