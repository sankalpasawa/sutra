"""The seed sync learns J2's run templates and the two provenance keys of J2 1adb8ecd (J2 sync 6, D185). Offline; real files in a temp
folder; the seeds are made by hand (`seedlib`), so none of this depends on what the app ships. The rule is D144's, still: the sync only
adds. A run template the library has is left alone (its `used_by` is the library's own), a folder or a row that is missing is restored
or adopted, one with another spec is reported and kept, and a family J2 renamed is added beside the old one, never in its place."""
import json
import logging
import shutil
from pathlib import Path

import pytest
from seedlib import (
    entry_of, folders, key_of, make_library, read, row_of, run_template_row, sha_of, snapshot, version_row, write, write_run_template,
)

from sutra_app.ops import doctor

PROBLEM = ("prd", "problem", "acme-problem")
SKY = run_template_row("sky-site", "Sky site", run="j2-20261103-100001")
ACME = run_template_row("acme-docs", "acme docs", run="j2-20261103-100002", mock=False)
ZED = run_template_row("zed-site", "Zed site", run="j2-20261103-100003")
LOCAL = run_template_row("owner-made", "Owner made", run="j2-20261104-090000", used_by=3)


def index_of(library: Path) -> dict:
    return read(library / "index.json")


def ids(library: Path) -> list[str]:
    return [r["id"] for r in index_of(library).get("run_templates", [])]


def seeded(tmp_path: Path, seed_rows, have_rows=None, **kw) -> tuple[Path, Path, Path]:
    seed = make_library(tmp_path / "seed", {PROBLEM: {1: sha_of("a")}}, run_templates=seed_rows)
    data = tmp_path / "data"
    library = make_library(data / "library", {PROBLEM: {1: sha_of("a")}}, run_templates=have_rows, **kw)
    return seed, data, library


# ---- adding --------------------------------------------------------------------------------------------------------------------

def test_a_library_without_run_templates_gains_the_seeds_rows_and_folders(tmp_path):
    seed, data, library = seeded(tmp_path, [ZED, ACME, SKY])
    assert "run_templates" not in index_of(library)
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert sorted(report["run_templates"]) == ["acme-docs", "sky-site", "zed-site"]
    assert ids(library) == ["acme-docs", "sky-site", "zed-site"]                       # J2's order: by name, case-insensitive
    for rid in ids(library):
        assert (library / "run-templates" / rid / "template.json").read_bytes() == (seed / "run-templates" / rid / "template.json").read_bytes()
        assert (library / "run-templates" / rid / "schema.json").is_file()
    assert index_of(library)["run_templates"][0] == ACME and report["skipped"] == []
    assert not [f for f in folders(library) if ".sync-" in f or ".tmp" in f]            # nothing half-copied was left beside them


def test_the_owners_run_templates_stay_and_the_seeds_are_added_in_name_order(tmp_path):
    seed, data, library = seeded(tmp_path, [ZED, SKY], [LOCAL])
    doctor.sync_seed_library(data, seed)
    assert ids(library) == ["owner-made", "sky-site", "zed-site"]
    assert row_of_run_template(library, "owner-made") == LOCAL


def row_of_run_template(library: Path, rid: str) -> dict:
    return next(r for r in index_of(library)["run_templates"] if r["id"] == rid)


def test_a_run_template_the_library_has_is_left_alone_even_when_the_seed_differs(tmp_path):
    mine = dict(SKY, used_by=7, description="owner edited")
    seed, data, library = seeded(tmp_path, [SKY], [mine])
    (library / "run-templates" / "sky-site" / "template.json").write_text('{"owner": "changed"}\n', encoding="utf-8")
    before = snapshot(library)
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert snapshot(library) == before and report["run_templates"] == [] and report["skipped"] == []
    assert row_of_run_template(library, "sky-site")["used_by"] == 7


def test_a_second_sync_changes_nothing_byte_for_byte(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY, ACME, ZED], [LOCAL])
    doctor.sync_seed_library(data, seed)
    once, dirs = snapshot(library), folders(library)
    report: dict = {}
    assert doctor.sync_seed_library(data, seed, report=report) == []
    assert snapshot(library) == once and folders(library) == dirs
    assert report["run_templates"] == [] and report["renamed"] == {} and report["skipped"] == []


# ---- the four states of a missing row or folder -------------------------------------------------------------------------------

def test_a_row_whose_folder_is_gone_gets_the_folder_back_and_keeps_its_row(tmp_path):
    mine = dict(SKY, used_by=4)
    seed, data, library = seeded(tmp_path, [SKY], [mine])
    shutil.rmtree(library / "run-templates" / "sky-site")
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert report["run_templates"] == ["sky-site"]
    assert (library / "run-templates" / "sky-site" / "template.json").read_bytes() == (seed / "run-templates" / "sky-site" / "template.json").read_bytes()
    assert row_of_run_template(library, "sky-site")["used_by"] == 4


def test_a_folder_with_no_row_is_adopted_when_it_is_the_seeds_run_template(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY])
    write_run_template(library, SKY, marker="mine")
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert report["run_templates"] == ["sky-site"] and ids(library) == ["sky-site"]
    assert json.loads((library / "run-templates" / "sky-site" / "template.json").read_text())["note"] == "mine"      # the folder is the owner's


def test_a_folder_with_no_row_and_another_run_template_inside_is_left_alone_and_reported(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY])
    write_run_template(library, dict(SKY, made_from_run="j2-20261105-000000"), marker="other")
    before = snapshot(library / "run-templates")
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert snapshot(library / "run-templates") == before and report["run_templates"] == [] and "run_templates" not in index_of(library)
    assert [(s["template"], s["version"]) for s in report["skipped"]] == [("run-templates/sky-site", None)]
    assert "another run template" in report["skipped"][0]["why"]


def test_a_seed_row_without_a_folder_or_with_an_unsafe_id_is_not_followed(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY, ZED, run_template_row("up-down", "Up down")])
    shutil.rmtree(seed / "run-templates" / "zed-site")
    doc = read(seed / "index.json")
    doc["run_templates"].append(run_template_row("../escape", "Escape"))
    doc["run_templates"].append(run_template_row("Not A Slug", "Bad"))
    write(seed / "index.json", doc)
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert sorted(report["run_templates"]) == ["sky-site", "up-down"] and ids(library) == ["sky-site", "up-down"]
    assert [(s["template"], s["why"]) for s in report["skipped"]] == [("run-templates/zed-site", "the seed has no folder for it")]
    assert not (library.parent / "escape").exists() and not (library / "run-templates" / ".." / "escape").exists()


def test_a_run_template_row_whose_folder_cannot_be_restored_is_reported(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY], [SKY])
    shutil.rmtree(library / "run-templates" / "sky-site")
    shutil.rmtree(seed / "run-templates" / "sky-site")
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert report["run_templates"] == [] and "missing here" in report["skipped"][0]["why"]


def test_a_damaged_run_templates_value_is_reported_and_the_rest_still_syncs(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY])
    doc = index_of(library)
    doc["run_templates"] = {"not": "a list"}
    write(library / "index.json", doc)
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert index_of(library)["run_templates"] == {"not": "a list"} and report["run_templates"] == []
    assert any("`run_templates` is not a list" in s["why"] for s in report["skipped"])


def test_a_seed_with_no_run_templates_adds_no_key_to_the_library(tmp_path):
    seed, data, library = seeded(tmp_path, None)
    doctor.sync_seed_library(data, seed)
    assert "run_templates" not in index_of(library) and not (library / "run-templates").exists()


# ---- provenance and renames -----------------------------------------------------------------------------------------------------

def test_renamed_from_and_adapted_from_are_added_where_absent_and_never_changed(tmp_path):
    sha = sha_of("a")
    seed_row = dict(version_row(PROBLEM, 1, sha), renamed_from="Acme Problem@1", adapted_from="Other Problem@2")
    seed = make_library(tmp_path / "seed", {PROBLEM: {1: sha}})
    doc = read(seed / "index.json")
    entry_of(doc, PROBLEM)["versions"] = [seed_row]
    write(seed / "index.json", doc)
    meta = read(seed / PROBLEM[0] / PROBLEM[1] / PROBLEM[2] / "v1" / "meta.json")
    meta.update(renamed_from="Acme Problem@1", adapted_from="Other Problem@2")
    write(seed / PROBLEM[0] / PROBLEM[1] / PROBLEM[2] / "v1" / "meta.json", meta)
    data = tmp_path / "data"
    library = make_library(data / "library", {PROBLEM: {1: sha}})
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    label = "/".join(PROBLEM) + "@v1"
    assert report["filled"] == {label: ["adapted_from", "renamed_from"]}
    row = row_of(index_of(library), PROBLEM, 1)
    assert row["renamed_from"] == "Acme Problem@1" and row["adapted_from"] == "Other Problem@2"
    stored = read(library / PROBLEM[0] / PROBLEM[1] / PROBLEM[2] / "v1" / "meta.json")
    assert stored["renamed_from"] == "Acme Problem@1" and stored["adapted_from"] == "Other Problem@2"
    # the owner's own value is never changed
    row["renamed_from"] = "Mine@9"
    doc = index_of(library)
    entry_of(doc, PROBLEM)["versions"][0]["renamed_from"] = "Mine@9"
    write(library / "index.json", doc)
    report2: dict = {}
    doctor.sync_seed_library(data, seed, report=report2)
    assert row_of(index_of(library), PROBLEM, 1)["renamed_from"] == "Mine@9" and report2["filled"] == {}


def test_a_family_renamed_upstream_is_added_beside_the_old_one_and_listed_as_renamed(tmp_path):
    sha = sha_of("moved")
    old_key, new_key = ("hld", "components", "acme-components"), ("hld", "components", "flow-components")
    data = tmp_path / "data"
    library = make_library(data / "library", {old_key: {7: sha}})
    seed = make_library(tmp_path / "seed", {new_key: {1: sha}})
    doc = read(seed / "index.json")
    row_of(doc, new_key, 1)["renamed_from"] = "acme-components@7"
    write(seed / "index.json", doc)
    before = snapshot(library / "hld" / "components" / "acme-components")
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert report["templates"] == ["hld/components/flow-components"]
    assert report["renamed"] == {"hld/components/flow-components@v1": "acme-components@7"}
    after = index_of(library)
    assert [key_of(e) for e in after["templates"]] == sorted([new_key, old_key])
    assert snapshot(library / "hld" / "components" / "acme-components") == before
    assert row_of(after, old_key, 7)["sha"] == sha and row_of(after, new_key, 1)["sha"] == sha        # one spec, two families: nothing moved
    assert doctor.sync_seed_library(data, seed) == []


# ---- the checks, the command and the start ----------------------------------------------------------------------------------------

def test_missing_seed_run_templates_is_what_the_sync_adds_and_it_writes_nothing(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY, ZED], [SKY])
    before, dirs = snapshot(library), folders(library)
    assert doctor.missing_seed_run_templates(data, seed) == ["zed-site"]
    assert snapshot(library) == before and folders(library) == dirs
    doctor.sync_seed_library(data, seed)
    assert doctor.missing_seed_run_templates(data, seed) == []
    assert doctor.missing_seed_run_templates(tmp_path / "nowhere", seed) == []


def test_the_doctor_check_warns_about_missing_run_templates_and_names_the_command(tmp_path):
    seed, data, library = seeded(tmp_path, [SKY, ZED], [SKY])
    check = doctor._check_library(data, seed)
    assert check.status == "warn" and "1 seed run template(s)" in check.detail and "zed-site" in check.detail
    assert "config sync-library" in check.fix
    doctor.sync_seed_library(data, seed)
    again = doctor._check_library(data, seed)
    assert again.status == "ok" and "run templates" in again.detail


def test_a_data_folder_without_a_library_gets_the_whole_seed_with_its_run_templates(tmp_path):
    seed = make_library(tmp_path / "seed", {PROBLEM: {1: sha_of("a")}}, run_templates=[SKY, ACME])
    data = tmp_path / "data"
    data.mkdir()
    report: dict = {}
    doctor.sync_seed_library(data, seed, report=report)
    assert sorted(report["run_templates"]) == ["acme-docs", "sky-site"] and report["renamed"] == {}
    assert sorted(ids(data / "library")) == ["acme-docs", "sky-site"] and (data / "library" / "run-templates" / "sky-site" / "schema.json").is_file()


def test_the_start_up_sync_runs_again_when_the_seed_index_changed_and_logs_the_run_templates(tmp_path, caplog):
    seed, data, library = seeded(tmp_path, [SKY])
    with caplog.at_level(logging.INFO, logger="sutra_app.ops.doctor"):
        first = doctor.sync_seed_once(data, seed)
    assert first and first["run_templates"] == ["sky-site"] and "1 run template(s)" in caplog.text
    assert doctor.sync_seed_once(data, seed) is None                                       # the marker holds: nothing is done twice
    doc = read(seed / "index.json")
    doc["run_templates"].append(ZED)
    write(seed / "index.json", doc)
    write_run_template(seed, ZED, marker="seed")
    second = doctor.sync_seed_once(data, seed)
    assert second and second["run_templates"] == ["zed-site"] and ids(library) == ["sky-site", "zed-site"]


def test_the_command_says_which_run_templates_were_added_and_which_versions_were_renamed(tmp_path, monkeypatch, capsys):
    from sutra_app.ops import cli
    sha = sha_of("moved")
    old_key, new_key = ("hld", "components", "acme-components"), ("hld", "components", "flow-components")
    data = tmp_path / "data"
    make_library(data / "library", {old_key: {7: sha}})
    seed = make_library(tmp_path / "seed", {new_key: {1: sha}}, run_templates=[SKY])
    doc = read(seed / "index.json")
    row_of(doc, new_key, 1)["renamed_from"] = "acme-components@7"
    write(seed / "index.json", doc)
    monkeypatch.setattr(doctor, "seed_dir", lambda: seed)
    code = cli.main(["config", "sync-library", "--data-dir", str(data)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Added 1 run template(s): sky-site" in out
    assert "1 added version(s) were renamed upstream" in out and "hld/components/flow-components@v1 (was acme-components@7)" in out
